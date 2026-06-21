import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PairTradingStateTests(unittest.TestCase):
    def test_pair_trading_uses_persisted_app_store_state(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "pair-trading" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("export interface PairTradingParams", store_source)
        self.assertIn("pairTradingParams: PairTradingParams", store_source)
        self.assertIn("setPairTradingParams", store_source)
        self.assertIn("pairTradingParams: state.pairTradingParams", store_source)

        self.assertIn("useAppStore", page_source)
        self.assertIn("pairTradingParams", page_source)
        self.assertNotIn("const [selectedPair, setSelectedPair] = useState<any>(null)", page_source)
        self.assertNotIn('const [selectedCategory, setSelectedCategory] = useState("全部")', page_source)


if __name__ == "__main__":
    unittest.main()
