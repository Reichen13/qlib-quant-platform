import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.db import report_store


class ReportStoreTests(unittest.TestCase):
    def test_list_reports_returns_recent_agent_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "agent_reports.db"
            with patch.object(report_store, "DB_PATH", db_path):
                report_store._init_db()
                report_store.save_report(
                    "agent-task",
                    "600519.SH",
                    "completed",
                    report={"pm_decision": {"rating": "BUY", "thesis": "长期竞争优势较强"}},
                )
                reports = report_store.list_reports()

        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["task_id"], "agent-task")
        self.assertEqual(reports[0]["code"], "600519.SH")
        self.assertEqual(reports[0]["status"], "completed")
        self.assertEqual(reports[0]["rating"], "BUY")
        self.assertIn("长期竞争优势", reports[0]["thesis"])
        self.assertIn("created_at", reports[0])


if __name__ == "__main__":
    unittest.main()
