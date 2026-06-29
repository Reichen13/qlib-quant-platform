import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BacktestTaskStateTests(unittest.TestCase):
    def test_backtest_task_state_is_persisted_in_app_store(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "backtest" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("backtestTaskId: string | null", store_source)
        self.assertIn("backtestResult:", store_source)
        self.assertIn("setBacktestTaskState", store_source)
        self.assertIn("backtestTaskId: state.backtestTaskId", store_source)

        self.assertIn("backtestTaskId", page_source)
        self.assertIn("setBacktestTaskState", page_source)
        self.assertIn('result.status === "running"', page_source)
        self.assertIn("taskId: result.task_id", page_source)
        self.assertNotIn("const [pollingTaskId", page_source)
        self.assertNotIn("const [result", page_source)

    def test_backtest_warnings_are_typed_and_displayed(self):
        api_source = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "backtest" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("warnings?: string[]", api_source)
        self.assertIn("result.warnings", page_source)
        self.assertIn("AlertTriangle", page_source)


if __name__ == "__main__":
    unittest.main()
