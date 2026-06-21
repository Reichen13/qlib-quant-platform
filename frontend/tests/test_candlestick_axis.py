import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CandlestickAxisTests(unittest.TestCase):
    def test_candlestick_chart_uses_manual_price_autoscale(self):
        source = (ROOT / "src" / "components" / "charts" / "candlestick-chart.tsx").read_text(encoding="utf-8")

        self.assertIn("buildPriceAutoscaleInfo", source)
        self.assertIn("autoscaleInfoProvider", source)
        self.assertIn("priceRange", source)
        self.assertIn("margins", source)


if __name__ == "__main__":
    unittest.main()
