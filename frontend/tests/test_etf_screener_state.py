import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EtfScreenerStateTests(unittest.TestCase):
    def test_etf_screener_uses_persisted_app_store_state(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "etf-screener" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("export interface EtfScreenerParams", store_source)
        self.assertIn("etfScreenerParams: EtfScreenerParams", store_source)
        self.assertIn("setEtfScreenerParams", store_source)
        self.assertIn("etfScreenerParams: state.etfScreenerParams", store_source)

        self.assertIn("useAppStore", page_source)
        self.assertIn("etfScreenerParams", page_source)
        self.assertNotIn('useState("")', page_source)
        self.assertNotIn('useState("全部")', page_source)
        self.assertNotIn('useState("change-desc")', page_source)
        self.assertNotIn('useState<"core" | "all">("core")', page_source)


    def test_etf_screener_does_not_overclaim_unavailable_universe_size(self):
        page_source = (ROOT / "src" / "pages" / "etf-screener" / "index.tsx").read_text(encoding="utf-8")

        self.assertNotIn("全量300+", page_source)
        self.assertNotIn("核心50", page_source)
        self.assertIn("可计算", page_source)


if __name__ == "__main__":
    unittest.main()
