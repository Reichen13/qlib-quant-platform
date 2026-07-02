import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for item in (str(project_root), str(backend_dir)):
    if item not in sys.path:
        sys.path.insert(0, item)

from backend.api import system
from backend.db.task_store import TaskStore


class SystemApiTests(unittest.TestCase):
    def test_environment_check_reports_runtime_data_and_dependencies(self):
        result = system.environment_check()

        self.assertIn("python", result)
        self.assertIn("executable", result["python"])
        self.assertIn("version", result["python"])
        self.assertIn("dependencies", result)
        self.assertIn("pyqlib", result["dependencies"])
        self.assertIn("frontend", result)
        self.assertIn("node_modules", result["frontend"])
        self.assertIn("qlib_data", result)
        self.assertIn("exists", result["qlib_data"])
        self.assertIn(result["overall_status"], {"healthy", "warning"})

    def test_module_available_handles_modules_without_spec(self):
        with patch.object(system.importlib.util, "find_spec", side_effect=ValueError("missing spec")):
            self.assertFalse(system._module_available("pandas"))

    def test_task_center_lists_backtest_tasks_from_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TaskStore(Path(tmpdir) / "tasks.db", table_name="backtest_tasks_test")
            store.init_db()
            store.create_task("task-1", '{"model":"lightgbm"}')
            store.update_progress("task-1", 35)

            with patch.object(system, "backtest_task_store", store):
                result = system.task_center()

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["tasks"][0]["task_id"], "task-1")
        self.assertEqual(result["tasks"][0]["type"], "backtest")
        self.assertEqual(result["tasks"][0]["status"], "running")
        self.assertEqual(result["tasks"][0]["progress"], 35)
        self.assertEqual(result["tasks"][0]["params"]["model"], "lightgbm")

    def test_task_center_adds_backtest_action_urls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TaskStore(Path(tmpdir) / "tasks.db", table_name="backtest_tasks_test")
            store.init_db()
            store.create_task("task-actions", '{"model":"lightgbm"}')
            store.set_completed("task-actions", '{"task_id":"task-actions","status":"completed"}')

            with patch.object(system, "backtest_task_store", store):
                result = system.task_center()

        task = result["tasks"][0]
        self.assertEqual(task["detail_url"], "/api/backtest/status/task-actions")
        self.assertEqual(task["report_url"], "/api/backtest/report/task-actions.md")

    def test_task_center_lists_agent_reports_with_open_url(self):
        reports = [
            {
                "task_id": "agent-task-1",
                "code": "600519.SH",
                "status": "completed",
                "created_at": "2026-07-02T11:00:00",
                "rating": "BUY",
                "thesis": "长期竞争优势较强",
            }
        ]

        with patch.object(system, "list_agent_reports", return_value=reports):
            result = system.task_center()

        task = next(item for item in result["tasks"] if item["task_id"] == "agent-task-1")
        self.assertEqual(task["type"], "agent_report")
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["params"]["code"], "600519.SH")
        self.assertEqual(task["detail_url"], "/api/agent/report/agent-task-1")
        self.assertEqual(task["report_url"], "/api/agent/report/agent-task-1")


if __name__ == "__main__":
    unittest.main()
