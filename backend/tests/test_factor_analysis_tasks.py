import tempfile
import unittest
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
    )
    sys.modules["loguru"] = types.SimpleNamespace(logger=logger)

from fastapi import FastAPI
from backend.api import factors
from backend.db.task_store import TaskStore
from backend.models.schemas import FactorAnalysisResponse, FactorIC


class FactorAnalysisTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.tmp_dir.name) / "factor_tasks.db")
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

        with patch.object(factors, "_run_factor_analysis", return_value=result):
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

        status = self.client.get(f"/api/factors/analyze/status/{task_id}")

        self.assertEqual(status.status_code, 200)
        body = status.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["progress"], 100)
        self.assertEqual(body["result"]["factors"][0]["factor"], "KMID")

    def test_missing_task_returns_404(self):
        status = self.client.get("/api/factors/analyze/status/not-found")

        self.assertEqual(status.status_code, 404)


if __name__ == "__main__":
    unittest.main()
