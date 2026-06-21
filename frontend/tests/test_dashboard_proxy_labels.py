import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DashboardProxyLabelTests(unittest.TestCase):
    def test_strategy_signal_ui_does_not_display_fake_stock_counts(self):
        page_source = (ROOT / "src" / "pages" / "dashboard" / "index.tsx").read_text(encoding="utf-8")

        self.assertNotIn("s.stocks_count", page_source)
        self.assertIn("s.data_status === \"derived\"", page_source)
        self.assertIn("板块代理", page_source)


if __name__ == "__main__":
    unittest.main()
