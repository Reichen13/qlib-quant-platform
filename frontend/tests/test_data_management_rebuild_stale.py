import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DataManagementRebuildStaleTests(unittest.TestCase):
    def test_data_management_exposes_stale_repair_update_option(self):
        page_source = (ROOT / "src" / "pages" / "data-management" / "index.tsx").read_text(encoding="utf-8")
        api_source = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("repairStale", page_source)
        self.assertIn("targetCodes", page_source)
        self.assertIn("指定股票代码", page_source)
        self.assertIn("rebuildStale", api_source)
        self.assertIn("rebuild_stale", api_source)
        self.assertIn("codes:", api_source)

    def test_etf_and_index_status_copy_does_not_overstate_update_coverage(self):
        page_source = (ROOT / "src" / "pages" / "data-management" / "index.tsx").read_text(encoding="utf-8")

        self.assertNotIn("全市场 ETF 日线数据", page_source)
        self.assertNotIn("全市场 ETF (300+)", page_source)
        self.assertNotIn("主要指数日线数据", page_source)
        self.assertNotIn("主要指数 (12个)", page_source)
        self.assertIn("ETF/指数暂按 Qlib 状态代理展示，尚未接入独立更新", page_source)
        self.assertIn("待接入独立更新", page_source)


    def test_stock_coverage_copy_does_not_hardcode_outdated_universe_size(self):
        page_source = (ROOT / "src" / "pages" / "data-management" / "index.tsx").read_text(encoding="utf-8")

        self.assertNotIn("3800+", page_source)
        self.assertIn("以状态卡实际覆盖数量为准", page_source)


if __name__ == "__main__":
    unittest.main()
