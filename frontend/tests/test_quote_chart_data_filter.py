import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class QuoteChartDataFilterTests(unittest.TestCase):
    def test_quote_page_filters_zero_ohlc_rows_before_charting(self):
        source = (ROOT / "src" / "pages" / "quote" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("filterValidOhlcRows", source)
        self.assertIn("validOhlc", source)
        self.assertIn("quoteData.data.filter(filterValidOhlcRows)", source)


if __name__ == "__main__":
    unittest.main()
