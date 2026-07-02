import sys
import tempfile
from types import SimpleNamespace
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

fake_logger = SimpleNamespace(info=lambda *args, **kwargs: None,
                              warning=lambda *args, **kwargs: None,
                              error=lambda *args, **kwargs: None)
sys.modules.setdefault("loguru", SimpleNamespace(logger=fake_logger))
sys.modules.setdefault("stock_names", SimpleNamespace(get_stock_name=lambda code: code))
sys.modules.setdefault("pandas", SimpleNamespace())
sys.modules.setdefault("numpy", SimpleNamespace())

from backend.api import backtest
from backend.db.task_store import TaskStore
from backend.models.schemas import BacktestParams


class BacktestStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_backtest_allows_local_mlflow_file_store(self):
        self.assertEqual(backtest.os.environ.get("MLFLOW_ALLOW_FILE_STORE"), "true")

    async def test_leak_safe_segments_purge_train_valid_test_boundaries(self):
        calendars = [
            pd
            for pd in (
                date(2025, 3, 24),
                date(2025, 3, 25),
                date(2025, 3, 26),
                date(2025, 3, 27),
                date(2025, 3, 28),
                date(2025, 3, 31),
                date(2025, 4, 1),
                date(2025, 4, 2),
                date(2025, 4, 3),
                date(2025, 4, 4),
            )
        ]

        segments = backtest.build_leak_safe_segments(
            train_start="2025-03-24",
            train_end="2025-03-31",
            test_start="2025-04-01",
            backtest_end="2025-04-04",
            calendars=calendars,
            label_lookahead_steps=2,
        )

        self.assertEqual(segments["train"], ("2025-03-24", "2025-03-27"))
        self.assertNotIn("valid", segments)
        self.assertEqual(segments["test"], ("2025-04-01", "2025-04-04"))

    async def test_selected_factor_warning_discloses_full_alpha158_model(self):
        warning = backtest.build_selected_factor_warning(["KMID"])

        self.assertIn("完整 Alpha158", warning)
        self.assertIn("不是单因子专属回测", warning)

    async def test_backtest_progress_does_not_regress_after_prediction(self):
        source = Path(backtest.__file__).read_text(encoding="utf-8")

        self.assertNotIn("update_progress(task_id, 55)", source)
        self.assertIn("update_progress(task_id, 65)", source)
        self.assertIn("update_progress(task_id, 70)", source)

    async def test_run_creates_status_record_before_background_task_runs(self):
        params = BacktestParams(
            train_start=date(2025, 1, 1),
            train_end=date(2025, 3, 31),
            test_start=date(2025, 4, 1),
            test_end=date(2025, 4, 30),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store = TaskStore(Path(tmpdir) / "backtest_tasks.db", table_name="backtest_tasks_test")
            store.init_db()

            with patch.object(backtest, "task_store", store):
                response = await backtest.run_backtest(params, BackgroundTasks())
                task = store.get_task(response["task_id"])

        self.assertIsNotNone(task)
        self.assertEqual(task["status"], "running")
        self.assertEqual(task["progress"], 5)

    async def test_run_rejects_xgboost_when_dependency_is_missing_before_creating_task(self):
        params = BacktestParams(
            model="xgboost",
            train_start=date(2025, 1, 1),
            train_end=date(2025, 3, 31),
            test_start=date(2025, 4, 1),
            test_end=date(2025, 4, 30),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            store = TaskStore(Path(tmpdir) / "backtest_tasks.db", table_name="backtest_tasks_test")
            store.init_db()

            with patch.object(backtest, "task_store", store), \
                 patch.object(backtest.importlib.util, "find_spec", return_value=None):
                with self.assertRaises(Exception) as ctx:
                    await backtest.run_backtest(params, BackgroundTasks())

            tasks = store.list_tasks()

        self.assertEqual(tasks, [])
        self.assertIn("XGBoost", str(ctx.exception))

    async def test_marks_interrupted_running_tasks_as_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TaskStore(Path(tmpdir) / "backtest_tasks.db", table_name="backtest_tasks_test")
            store.init_db()
            store.create_task("running-task", "{}")
            store.create_task("completed-task", "{}")
            store.set_completed("completed-task", "{\"ok\": true}")

            with patch.object(backtest, "task_store", store):
                marked = backtest.mark_interrupted_backtest_tasks()
                running_task = store.get_task("running-task")
                completed_task = store.get_task("completed-task")

        self.assertEqual(marked, 1)
        self.assertEqual(running_task["status"], "failed")
        self.assertIn("服务重启", running_task["error"])
        self.assertEqual(completed_task["status"], "completed")

    async def test_running_status_returns_progress_without_result_json(self):
        task = {
            "task_id": "task-running",
            "status": "running",
            "progress": 35,
            "result_json": None,
            "error": None,
        }

        with patch.object(backtest.task_store, "get_task", return_value=task):
            response = await backtest.get_backtest_status("task-running")

        self.assertEqual(response.task_id, "task-running")
        self.assertEqual(response.status, "running")
        self.assertEqual(response.progress, 35)
        self.assertIsNone(response.error)

    async def test_failed_status_returns_error_without_result_json(self):
        task = {
            "task_id": "task-failed",
            "status": "failed",
            "progress": 0,
            "result_json": None,
            "error": "model training failed",
        }

        with patch.object(backtest.task_store, "get_task", return_value=task):
            response = await backtest.get_backtest_status("task-failed")

        self.assertEqual(response.task_id, "task-failed")
        self.assertEqual(response.status, "failed")
        self.assertEqual(response.error, "model training failed")


    async def test_running_backtest_report_export_is_rejected(self):
        task = {
            "task_id": "task-running",
            "status": "running",
            "progress": 50,
            "result_json": None,
            "params_json": "{}",
            "error": None,
        }

        with patch.object(backtest.task_store, "get_task", return_value=task):
            with self.assertRaises(Exception) as ctx:
                await backtest.export_backtest_report("task-running")

        self.assertIn("已完成", str(ctx.exception))

    async def test_completed_backtest_report_exports_markdown(self):
        result_json = """{
            "task_id": "task-report",
            "status": "completed",
            "total_return": 0.1234,
            "annual_return": 0.2345,
            "sharpe_ratio": 1.56,
            "max_drawdown": -0.0789,
            "win_rate": 0.61,
            "top_buys": [{"code": "600519", "name": "贵州茅台", "score": 0.91, "reason": "质量较高"}],
            "position_advice": "控制单票仓位，分批建仓",
            "warnings": ["样本区间较短"]
        }"""
        task = {
            "task_id": "task-report",
            "status": "completed",
            "progress": 100,
            "result_json": result_json,
            "params_json": "{}",
            "error": None,
            "created_at": "2026-07-02T10:00:00",
            "updated_at": "2026-07-02T10:05:00",
        }

        with patch.object(backtest.task_store, "get_task", return_value=task):
            response = await backtest.export_backtest_report("task-report")

        self.assertEqual(response.media_type, "text/markdown; charset=utf-8")
        body = response.body.decode("utf-8")
        self.assertIn("# 回测报告", body)
        self.assertIn("task-report", body)
        self.assertIn("总收益率", body)
        self.assertIn("12.34%", body)
        self.assertIn("贵州茅台", body)
        self.assertIn("样本区间较短", body)


if __name__ == "__main__":
    unittest.main()
