import unittest
import sys
from pathlib import Path
from unittest.mock import patch

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.api import etf, index, pair, sectors


class FastFallbackEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_sector_performance_does_not_require_yfinance(self):
        with patch.object(sectors.yf, "Ticker", side_effect=AssertionError("yfinance should not be called")):
            response = await sectors.get_sector_performance(days=10)

        self.assertGreater(len(response["sectors"]), 0)
        self.assertIn("industry", response["sectors"][0])
        self.assertIn("change_pct", response["sectors"][0])

    async def test_sector_stocks_does_not_require_yfinance(self):
        with patch.object(sectors.yf, "Ticker", side_effect=AssertionError("yfinance should not be called")):
            response = await sectors.get_sector_stocks("半导体")

        self.assertEqual(response["industry"], "半导体")
        self.assertGreater(len(response["stocks"]), 0)
        self.assertIn("name", response["stocks"][0])

    async def test_etf_signals_does_not_require_yfinance(self):
        with patch("yfinance.Ticker", side_effect=AssertionError("yfinance should not be called")):
            response = await etf.get_etf_signals(days=20)

        self.assertGreater(len(response.etfs), 0)
        self.assertIn(response.etfs[0].signal, {"buy", "hold", "sell"})

    async def test_pair_list_does_not_recalculate_qlib_correlations(self):
        with patch.object(pair, "calc_correlation_from_qlib", side_effect=AssertionError("qlib should not be called")) as calc:
            response = await pair.list_pairs()

        calc.assert_not_called()
        self.assertGreater(len(response["pairs"]), 0)
        self.assertEqual(response["total"], len(response["pairs"]))

    async def test_index_performance_reports_unavailable_when_data_source_unavailable(self):
        with patch.object(index.provider, "_get_bs_client", return_value=None), \
             patch.object(index, "_qlib_index_performance", return_value=None):
            response = await index.get_index_performance(index="hs300", days=30)

        self.assertEqual(response["index"], "hs300")
        self.assertEqual(response["data"], [])
        self.assertIsNone(response["summary"]["current_price"])
        self.assertEqual(response["source"], "unavailable")
        self.assertIn("未生成合成数据", response["warning"])

    async def test_index_comparison_marks_unavailable_without_zero_filling(self):
        async def fake_performance(index: str, days: int):
            if index == "sz50":
                return index_module_unavailable(index, days)
            return {
                "index": index,
                "period_days": days,
                "data": [{"close": 1}],
                "summary": {
                    "total_return": 1.2,
                    "avg_daily_change": 0.1,
                    "max_drawdown": -0.5,
                    "current_price": 100.0,
                },
                "source": "qlib",
            }

        def index_module_unavailable(idx: str, days: int):
            return {
                "index": idx,
                "period_days": days,
                "data": [],
                "summary": {
                    "total_return": 0,
                    "avg_daily_change": 0,
                    "max_drawdown": 0,
                    "current_price": None,
                },
                "source": "unavailable",
                "warning": "暂无可靠指数行情数据，未生成合成数据。",
            }

        with patch.object(index, "get_index_performance", side_effect=fake_performance):
            response = await index.compare_indices()

        sz50 = next(item for item in response["comparison"] if item["code"] == "sz50")
        self.assertIsNone(sz50["total_return"])
        self.assertIsNone(sz50["avg_daily_change"])
        self.assertIsNone(sz50["max_drawdown"])
        self.assertEqual(sz50["source"], "unavailable")
        self.assertIn("未生成合成数据", sz50["warning"])


if __name__ == "__main__":
    unittest.main()
