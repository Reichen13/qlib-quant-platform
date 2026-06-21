import sys
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

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
        exception=lambda *args, **kwargs: None,
        add=lambda *args, **kwargs: None,
        remove=lambda *args, **kwargs: None,
    )
    sys.modules["loguru"] = types.SimpleNamespace(logger=logger)

from backend.api import data
from backend.db.task_store import TaskStore


class DataApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.tmp_dir.name) / "data_update_tasks.db", table_name="data_update_tasks_test")
        self.store.init_db()
        self.store_patch = patch.object(data, "data_update_task_store", self.store)
        self.store_patch.start()
        data._update_tasks.clear()

    async def asyncTearDown(self):
        data._update_tasks.clear()
        self.store_patch.stop()
        self.tmp_dir.cleanup()

    async def test_health_does_not_call_baostock_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            (qlib_dir / "features" / "sh600519").mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text("2026-06-18\n", encoding="utf-8")
            (qlib_dir / "instruments" / "csi300.txt").write_text("sh600519\t2020-01-01\t2026-06-18\n", encoding="utf-8")

            with patch.object(Path, "home", return_value=Path(tmpdir)), \
                 patch.object(data, "_check_baostock_industry", side_effect=AssertionError("baostock should not be called")):
                response = await data.data_health_check()

        self.assertIn("sources", response)
        self.assertEqual(response["sources"]["baostock_industry"]["status"], "unknown")
        self.assertIn("stocks", response["sources"])

    async def test_stocks_health_uses_latest_feature_bin_date_not_calendar_tail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            stock_dir = qlib_dir / "features" / "sh600519"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text(
                "2026-05-06\n2026-05-07\n2026-05-08\n",
                encoding="utf-8",
            )
            (qlib_dir / "instruments" / "csi300.txt").write_text(
                "sh600519\t2020-01-01\t2026-06-18\n",
                encoding="utf-8",
            )
            np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / "close.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_stocks_data()

        self.assertEqual(response["last_date"], "2026-05-06")

    async def test_qlib_health_uses_feature_bin_date_not_calendar_tail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            stock_dir = qlib_dir / "features" / "sh600519"
            (qlib_dir / "calendars").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text(
                "2026-05-06\n2026-05-07\n2026-05-08\n",
                encoding="utf-8",
            )
            np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / "close.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_qlib_data()

        self.assertEqual(response["last_date"], "2026-05-06")

    async def test_stocks_health_counts_unique_instruments_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            stock_dir = qlib_dir / "features" / "sh600519"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text("2026-06-18\n", encoding="utf-8")
            (qlib_dir / "instruments" / "csi300.txt").write_text(
                "SH600519\t2020-01-01\t2026-06-18\n"
                "sh600519\t2020-01-01\t2026-06-18\n"
                "SZ000001\t2020-01-01\t2026-06-18\n",
                encoding="utf-8",
            )
            np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / "close.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_stocks_data()

        self.assertEqual(response["total"], 1)
        self.assertEqual(response["raw_total"], 1)
        self.assertEqual(response["duplicate_count"], 0)
        self.assertEqual(response["csi300_total"], 2)
        self.assertEqual(response["csi300_raw_total"], 3)
        self.assertEqual(response["csi300_duplicate_count"], 1)

    async def test_stocks_health_ignores_older_feature_bin_when_newer_sample_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            old_stock_dir = qlib_dir / "features" / "sh600000"
            new_stock_dir = qlib_dir / "features" / "sh600519"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            old_stock_dir.mkdir(parents=True)
            new_stock_dir.mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text(
                "2026-05-06\n2026-05-07\n2026-05-08\n",
                encoding="utf-8",
            )
            (qlib_dir / "instruments" / "csi300.txt").write_text(
                "sh600519\t2020-01-01\t2026-06-18\n",
                encoding="utf-8",
            )
            np.array([0.0, 10.0], dtype="<f").tofile(old_stock_dir / "close.day.bin")
            np.array([0.0, 10.0, 11.0], dtype="<f").tofile(new_stock_dir / "close.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_stocks_data()

        self.assertEqual(response["last_date"], "2026-05-07")

    async def test_stocks_health_uses_representative_date_when_only_one_stock_updated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text(
                "2026-05-06\n2026-05-07\n2026-06-18\n",
                encoding="utf-8",
            )
            (qlib_dir / "instruments" / "csi300.txt").write_text(
                "sh600519\t2020-01-01\t2026-06-18\n",
                encoding="utf-8",
            )
            for idx in range(9):
                stock_dir = qlib_dir / "features" / f"sh60000{idx}"
                stock_dir.mkdir(parents=True)
                np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / "close.day.bin")
            latest_dir = qlib_dir / "features" / "sh600519"
            latest_dir.mkdir(parents=True)
            np.array([0.0, 10.0, 11.0, 12.0], dtype="<f").tofile(latest_dir / "close.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_stocks_data()

        self.assertEqual(response["last_date"], "2026-05-06")
        self.assertEqual(response["sample_latest_date"], "2026-06-18")

    async def test_start_update_returns_task_and_records_status(self):
        data._update_tasks.clear()

        with patch.object(data, "_resolve_update_script", return_value=Path(__file__)), \
             patch.object(data, "_start_update_thread") as start_thread:
            response = await data.start_data_update(
                data.DataUpdateRequest(type="stocks", max_stocks=1)
            )

        self.assertEqual(response["status"], "running")
        self.assertIn(response["task_id"], data._update_tasks)
        start_thread.assert_called_once()

    async def test_start_update_persists_task_status(self):
        with patch.object(data, "_resolve_update_script", return_value=Path(__file__)), \
             patch.object(data, "_start_update_thread"):
            response = await data.start_data_update(
                data.DataUpdateRequest(type="stocks", max_stocks=1)
            )

        persisted = self.store.get_task(response["task_id"])

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["status"], "running")
        self.assertEqual(persisted["progress"], 5)
        self.assertIn("数据更新任务已排队", json.loads(persisted["result_json"])["message"])

    async def test_start_update_uses_actual_stock_latest_date_by_default(self):
        data._update_tasks.clear()

        with patch.object(data, "_resolve_update_script", return_value=Path(__file__)), \
             patch.object(data, "_get_stock_latest_trade_date", return_value="2026-05-06"), \
             patch.object(data, "_start_update_thread") as start_thread:
            await data.start_data_update(data.DataUpdateRequest(type="stocks", max_stocks=1))

        command = start_thread.call_args.args[1]
        self.assertIn("--start", command)
        self.assertEqual(command[command.index("--start") + 1], "2026-05-06")

    async def test_start_update_can_pass_rebuild_stale_flag(self):
        data._update_tasks.clear()

        with patch.object(data, "_resolve_update_script", return_value=Path(__file__)), \
             patch.object(data, "_start_update_thread") as start_thread:
            await data.start_data_update(
                data.DataUpdateRequest(type="stocks", max_stocks=1, rebuild_stale=True)
            )

        command = start_thread.call_args.args[1]
        self.assertIn("--rebuild-stale", command)

    async def test_update_progress_returns_existing_task(self):
        data._update_tasks.clear()
        data._update_tasks["task-1"] = {
            "task_id": "task-1",
            "type": "stocks",
            "status": "running",
            "progress": 10,
            "message": "更新中",
            "started_at": "2026-06-19T00:00:00",
        }

        response = await data.get_data_update_progress("task-1")

        self.assertEqual(response["task_id"], "task-1")
        self.assertEqual(response["status"], "running")

    async def test_running_process_is_rejected(self):
        data._update_tasks.clear()
        data._update_tasks["task-1"] = {
            "task_id": "task-1",
            "type": "stocks",
            "status": "running",
            "progress": 10,
            "message": "更新中",
            "started_at": "2026-06-19T00:00:00",
        }

        with self.assertRaises(data.HTTPException) as ctx:
            await data.start_data_update(data.DataUpdateRequest(type="stocks"))

        self.assertEqual(ctx.exception.status_code, 409)

    async def test_update_key_is_required_when_server_api_key_missing(self):
        with patch.dict(data.os.environ, {}, clear=True):
            with self.assertRaises(data.HTTPException) as ctx:
                await data.require_data_update_key()

        self.assertEqual(ctx.exception.status_code, 503)

    async def test_etf_update_is_rejected_until_script_is_available(self):
        data._update_tasks.clear()

        with self.assertRaises(data.HTTPException) as ctx:
            await data.start_data_update(data.DataUpdateRequest(type="etf"))

        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
