import sys
import types
import unittest
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

import pandas as pd

from backend.api import etf, mean_reversion, pair


def make_history(rows: int = 12) -> pd.DataFrame:
    return pd.DataFrame({
        "Close": [1.0 + i * 0.01 for i in range(rows)],
        "Volume": [1000.0 + i for i in range(rows)],
        "Money": [100000.0 + i * 100 for i in range(rows)],
    })


class NoMockMarketFallbackTests(unittest.IsolatedAsyncioTestCase):
    def test_mean_reversion_universe_prefers_local_full_market_features(self):
        feature_dirs = [
            Path("/tmp/qlib-test/.qlib/qlib_data/cn_data/features/sh600519"),
            Path("/tmp/qlib-test/.qlib/qlib_data/cn_data/features/sz000001"),
            Path("/tmp/qlib-test/.qlib/qlib_data/cn_data/features/sz300750"),
            Path("/tmp/qlib-test/.qlib/qlib_data/cn_data/features/sh688981"),
            Path("/tmp/qlib-test/.qlib/qlib_data/cn_data/features/bj920118"),
            Path("/tmp/qlib-test/.qlib/qlib_data/cn_data/features/sh510300"),
        ]

        with patch.object(mean_reversion.Path, "home", return_value=Path("/tmp/qlib-test")):
            with patch.object(mean_reversion.Path, "exists", return_value=True), \
                 patch.object(mean_reversion.Path, "is_dir", return_value=True), \
                 patch.object(mean_reversion.Path, "iterdir", return_value=feature_dirs):
                universe = mean_reversion._get_scan_universe()

        self.assertEqual(universe, ["SH600519", "SZ000001", "SZ300750", "SH688981", "BJ920118"])

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
        self.assertIn("轮动信号暂不可用", response.warning)

    def test_etf_history_prefers_local_qlib_before_yfinance(self):
        local_history = make_history()

        with patch.object(etf, "_fetch_all_etf_history_from_qlib", return_value={"SH510300": local_history}), \
             patch.object(etf, "_fetch_all_etf_history_from_yfinance", return_value={}) as yf_fetch:
            result = etf._fetch_all_etf_history()

        self.assertIn("SH510300", result)
        yf_fetch.assert_called_once()

    def test_etf_universe_discovers_local_qlib_etf_feature_dirs(self):
        with patch.object(etf.Path, "home", return_value=Path("/tmp/qlib-test")):
            with patch.object(etf.Path, "exists", return_value=True), \
                 patch.object(etf.Path, "iterdir", return_value=[
                     Path("/tmp/qlib-test/.qlib/qlib_data/cn_data/features/sh510300"),
                     Path("/tmp/qlib-test/.qlib/qlib_data/cn_data/features/sh563000"),
                     Path("/tmp/qlib-test/.qlib/qlib_data/cn_data/features/sz159915"),
                     Path("/tmp/qlib-test/.qlib/qlib_data/cn_data/features/sh600519"),
                 ]):
                universe = etf._get_etf_universe()

        self.assertIn("SH510300", universe)
        self.assertIn("SH563000", universe)
        self.assertIn("SZ159915", universe)
        self.assertNotIn("SH600519", universe)
        self.assertEqual(universe["SH563000"], "SH563000")

    def test_fetch_all_etf_history_from_qlib_uses_discovered_universe(self):
        local_history = make_history()

        with patch.object(etf, "_get_etf_universe", return_value={
            "SH510300": "沪深300ETF",
            "SH563000": "SH563000",
        }, create=True), \
             patch.object(etf, "_fetch_etf_history_from_qlib", return_value=local_history):
            result = etf._fetch_all_etf_history_from_qlib()

        self.assertEqual(set(result), {"SH510300", "SH563000"})

    def test_compute_etf_metrics_accepts_discovered_etf_code(self):
        with patch.object(etf, "_get_etf_universe", return_value={"SH563000": "SH563000"}, create=True):
            info = etf._compute_etf_metrics("SH563000", make_history(), days=5)

        self.assertIsNotNone(info)
        self.assertEqual(info.code, "SH563000")
        self.assertEqual(info.name, "SH563000")


if __name__ == "__main__":
    unittest.main()
