import sys
import unittest
from pathlib import Path
from unittest.mock import patch

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

import pandas as pd

from backend.api import etf, mean_reversion, pair


class NoMockMarketFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_mean_reversion_scan_reports_unavailable_instead_of_mock_signals(self):
        with patch.object(mean_reversion, "scan_mean_reversion_signals", side_effect=RuntimeError("qlib unavailable")):
            response = await mean_reversion.scan_signals(rsi_threshold=70, bollinger_period=20)

        self.assertEqual(response["signals"], [])
        self.assertEqual(response["total"], 0)
        self.assertEqual(response["data_status"], "unavailable")
        self.assertIn("warning", response)

    async def test_pair_spread_returns_empty_data_instead_of_random_series(self):
        with patch.object(pair, "calc_spread_data", return_value=[]):
            response = await pair.get_spread(stock1="SH600036", stock2="SZ000001", days=60)

        self.assertEqual(response["data"], [])
        self.assertEqual(response["data_status"], "unavailable")
        self.assertIn("warning", response)

    async def test_pair_analyze_requires_real_metrics(self):
        with patch.object(pair, "calc_correlation_from_qlib", return_value=None), \
             patch.object(pair, "calc_zscore_from_qlib", return_value=None), \
             patch.object(pair, "calc_spread_data", return_value=[]):
            response = await pair.analyze_pair(stock1="SH600036", stock2="SZ000001")

        self.assertIsNone(response["correlation"])
        self.assertIsNone(response["pValue"])
        self.assertIsNone(response["zScore"])
        self.assertEqual(response["status"], "不可用")
        self.assertEqual(response["data_status"], "unavailable")

    async def test_etf_signals_reports_unavailable_instead_of_mock_signals(self):
        with patch.object(etf, "_get_cached_history", return_value={}), \
             patch.object(etf, "_fetch_etf_history", return_value=None):
            response = await etf.get_etf_signals(days=20)

        self.assertEqual(response.etfs, [])
        self.assertEqual(response.top_buy, [])
        self.assertEqual(response.top_sell, [])
        self.assertIn("未生成模拟", response.warning)

    def test_etf_history_prefers_local_qlib_before_yfinance(self):
        local_history = pd.DataFrame({
            "Close": [1.0] * 12,
            "Volume": [1000.0] * 12,
        })

        with patch.object(etf, "_fetch_all_etf_history_from_qlib", return_value={"SH510300": local_history}), \
             patch.object(etf, "_fetch_all_etf_history_from_yfinance", return_value={}) as yf_fetch:
            result = etf._fetch_all_etf_history()

        self.assertIn("SH510300", result)
        yf_fetch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
