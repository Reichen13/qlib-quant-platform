import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StockPoolStateTests(unittest.TestCase):
    def test_stock_pool_selected_pool_is_persisted_in_app_store(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "stock-pool" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("export interface StockPoolParams", store_source)
        self.assertIn("stockPoolParams: StockPoolParams", store_source)
        self.assertIn("setStockPoolParams", store_source)
        self.assertIn("stockPoolParams: state.stockPoolParams", store_source)

        self.assertIn("useAppStore", page_source)
        self.assertIn("stockPoolParams", page_source)
        self.assertNotIn("const [selectedPool, setSelectedPool] = useState<string | null>(null)", page_source)


if __name__ == "__main__":
    unittest.main()
