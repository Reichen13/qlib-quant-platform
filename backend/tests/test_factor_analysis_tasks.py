import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import sys
import types

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

if "loguru" not in sys.modules:
    logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        add=lambda *args, **kwargs: None,
        remove=lambda *args, **kwargs: None,
    )
    sys.modules["loguru"] = types.SimpleNamespace(logger=logger)

from fastapi import FastAPI
from backend.api import factors
from backend.db.task_store import TaskStore
from backend.models.schemas import FactorAnalysisResponse, FactorIC


class FactorAnalysisTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.tmp_dir.name) / "factor_tasks.db", table_name="factor_analysis_tasks")
        self.store.init_db()
        self.store_patch = patch.object(factors, "factor_task_store", self.store, create=True)
        self.store_patch.start()
        app = FastAPI()
        app.include_router(factors.router, prefix="/api/factors")
        self.client = TestClient(app)

    def tearDown(self):
        self.store_patch.stop()
        self.tmp_dir.cleanup()

    def test_submit_and_status_returns_persisted_result(self):
        result = FactorAnalysisResponse(
            start_date="2026-01-01",
            end_date="2026-01-31",
            predict_period=5,
            factors=[
                FactorIC(factor="KMID", ic=0.12, rank_ic=0.12, icir=1.5, category="K线"),
            ],
            summary={"total_factors": 1},
        )

        def fast_analysis(_params, progress_cb=None):
            if progress_cb:
                progress_cb(40, "mid")
            return result

        with patch.object(factors, "_run_factor_analysis", side_effect=fast_analysis):
            submit = self.client.post(
                "/api/factors/analyze/submit",
                json={
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "predict_period": 5,
                    "top_k": 20,
                },
            )

            self.assertEqual(submit.status_code, 200)
            task_id = submit.json()["task_id"]

            status = None
            for _ in range(40):
                status = self.client.get(f"/api/factors/analyze/status/{task_id}")
                if status.json().get("status") == "completed":
                    break
                time.sleep(0.05)

        self.assertIsNotNone(status)
        self.assertEqual(status.status_code, 200)
        body = status.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["progress"], 100)
        self.assertEqual(body["result"]["factors"][0]["factor"], "KMID")

    def test_submit_returns_before_long_analysis_finishes(self):
        result = FactorAnalysisResponse(
            start_date="2026-01-01",
            end_date="2026-01-31",
            predict_period=5,
            factors=[
                FactorIC(factor="KMID", ic=0.12, rank_ic=0.12, icir=1.5, category="kline"),
            ],
            summary={"total_factors": 1},
        )
        release_analysis = threading.Event()

        def slow_analysis(_params, progress_cb=None):
            if progress_cb:
                progress_cb(30, "waiting")
            release_analysis.wait(timeout=3)
            return result

        with patch.object(factors, "_run_factor_analysis", side_effect=slow_analysis):
            started = time.monotonic()
            submit = self.client.post(
                "/api/factors/analyze/submit",
                json={
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "predict_period": 5,
                    "top_k": 20,
                },
            )
            elapsed = time.monotonic() - started

            self.assertEqual(submit.status_code, 200)
            self.assertLess(elapsed, 1.0)
            task_id = submit.json()["task_id"]

            status = self.client.get(f"/api/factors/analyze/status/{task_id}")
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["status"], "running")

            release_analysis.set()
            for _ in range(40):
                status = self.client.get(f"/api/factors/analyze/status/{task_id}")
                if status.json().get("status") == "completed":
                    break
                time.sleep(0.05)

        self.assertEqual(status.json()["status"], "completed")

    def test_missing_task_returns_404(self):
        status = self.client.get("/api/factors/analyze/status/not-found")

        self.assertEqual(status.status_code, 404)

    def test_stale_running_task_marked_failed_on_status(self):
        task_id = "stale-zombie-task"
        # 超过 FACTOR_TASK_STALE_MINUTES（45）无心跳
        old = (datetime.now(timezone.utc) - timedelta(minutes=50)).isoformat()
        self.store.create_task(task_id, "{}")
        # 直接改时间戳模拟僵尸
        import sqlite3
        conn = sqlite3.connect(self.store._db_path)
        conn.execute(
            f"UPDATE {self.store._table_name} SET status='running', progress=45, created_at=?, updated_at=? WHERE task_id=?",
            (old, old, task_id),
        )
        conn.commit()
        conn.close()

        status = self.client.get(f"/api/factors/analyze/status/{task_id}")
        self.assertEqual(status.status_code, 200)
        body = status.json()
        self.assertEqual(body["status"], "failed")
        self.assertIn("中断", body["error"])


if __name__ == "__main__":
    unittest.main()
