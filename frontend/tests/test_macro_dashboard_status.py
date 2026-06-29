import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MacroDashboardStatusTests(unittest.TestCase):
    def test_macro_dashboard_surfaces_partial_data_status(self):
        page_source = (ROOT / "src" / "pages" / "macro-dashboard" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("data_status", page_source)
        self.assertIn("中国宏观数据源当前为部分可用", page_source)
        self.assertIn('allocationData?.summary || "暂无配置数据"', page_source)

    def test_macro_api_uses_longer_timeout_for_external_data_sources(self):
        api_source = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("api/macro/indicators`, { timeoutMs: 60_000 }", api_source)
        self.assertIn("api/macro/regime`, {", api_source)
        self.assertIn("timeoutMs: 60_000", api_source)
        self.assertIn("api/macro/history?months=${months}`, { timeoutMs: 60_000 }", api_source)


if __name__ == "__main__":
    unittest.main()
