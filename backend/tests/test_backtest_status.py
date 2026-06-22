import sys
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch


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

from backend.api import backtest


class BacktestStatusTests(unittest.IsolatedAsyncioTestCase):
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


if __name__ == "__main__":
    unittest.main()
