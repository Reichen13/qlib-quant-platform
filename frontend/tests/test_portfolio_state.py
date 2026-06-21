import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PortfolioStateTests(unittest.TestCase):
    def test_portfolio_parameters_are_persisted_in_app_store(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "portfolio" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("export interface PortfolioParams", store_source)
        self.assertIn("portfolioParams: PortfolioParams", store_source)
        self.assertIn("setPortfolioParams", store_source)
        self.assertIn("portfolioParams: state.portfolioParams", store_source)

        self.assertIn("portfolioParams", page_source)
        self.assertIn("setPortfolioParams", page_source)
        self.assertIn("portfolioErrorMessage", page_source)
        self.assertIn("data-management", page_source)
        self.assertNotIn('const [method, setMethod] = useState("max_sharpe")', page_source)
        self.assertNotIn("const [maxWeight, setMaxWeight] = useState(30)", page_source)
        self.assertNotIn("const [turnoverLambda, setTurnoverLambda] = useState(0)", page_source)


if __name__ == "__main__":
    unittest.main()
