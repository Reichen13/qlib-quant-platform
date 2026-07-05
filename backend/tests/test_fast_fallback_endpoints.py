import unittest
import sys
import types
from pathlib import Path
from unittest.mock import patch

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

if "loguru" not in sys.modules:
    logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        add=lambda *args, **kwargs: None,
        remove=lambda *args, **kwargs: None,
    )
    sys.modules["loguru"] = types.SimpleNamespace(logger=logger)

if "yfinance" not in sys.modules:
    fake_yfinance = types.SimpleNamespace(
        Ticker=lambda *args, **kwargs: None,
        download=lambda *args, **kwargs: None,
    )
    sys.modules["yfinance"] = fake_yfinance

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

        self.assertEqual(response.etfs, [])
        self.assertEqual(response.top_buy, [])
        self.assertEqual(response.top_sell, [])
        self.assertIn("轮动信号暂不可用", response.warning)

    async def test_etf_pages_do_not_make_slow_external_or_per_code_fallbacks(self):
        etf._cache.clear()
        with patch.object(etf, "_fetch_all_etf_history_from_qlib", return_value={}), \
             patch.object(etf, "_fetch_all_etf_history_from_yfinance", side_effect=AssertionError("bulk yfinance should not be called")), \
             patch.object(etf, "_fetch_etf_history", side_effect=AssertionError("per-code ETF fallback should not be called")):
            signals = await etf.get_etf_signals(days=20)
            listing = await etf.list_etfs()

        self.assertEqual(signals.etfs, [])
        self.assertEqual(signals.top_buy, [])
        self.assertEqual(signals.top_sell, [])
        self.assertGreater(listing["total"], 0)
        self.assertTrue(all(item["data_status"] == "unavailable" for item in listing["etfs"]))

    async def test_pair_list_uses_real_metric_calculation(self):
        fake_metrics = {
            **pair.PAIR_DEFINITIONS[0],
            "correlation": 0.88,
            "pValue": 0.05,
            "zScore": 1.2,
            "signal": "关注",
            "status": "观察中",
            "data_status": "ok",
        }
        with patch.object(pair, "_cached_or_unavailable_pair_metrics", return_value=fake_metrics) as calc:
            response = await pair.list_pairs()

        self.assertEqual(calc.call_count, len(pair.get_all_pair_definitions()))
        self.assertGreater(len(response["pairs"]), 0)
        self.assertEqual(response["pairs"][0]["correlation"], 0.88)
        self.assertEqual(response["shown"], len(response["pairs"]))
        self.assertEqual(response["total"], len(pair.get_all_pair_definitions()))

    async def test_pair_metric_success_marks_data_status_ok(self):
        pair._pair_cache.clear()
        with patch.object(pair, "calc_correlation_from_qlib", return_value=0.88), \
             patch.object(pair, "calc_zscore_from_qlib", return_value=1.2):
            metrics = pair._compute_pair_metrics(pair.PAIR_DEFINITIONS[0])

        self.assertEqual(metrics["data_status"], "ok")

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
