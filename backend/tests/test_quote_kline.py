import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.api import quote


class QuoteKlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_quote_filters_zero_ohlc_rows_and_resamples_weekly(self):
        dates = pd.to_datetime([
            "2026-04-27",
            "2026-04-28",
            "2026-04-29",
            "2026-04-30",
            "2026-05-06",
            "2026-05-07",
        ])
        index = pd.MultiIndex.from_product([["SH600519"], dates], names=["instrument", "datetime"])
        df = pd.DataFrame(
            {
                "$open": [0, 0, 0, 1400, 1365, 1375],
                "$high": [0, 0, 0, 1401, 1379, 1388],
                "$low": [0, 0, 0, 1380, 1360, 1370],
                "$close": [0, 0, 0, 1385, 1375, 1371],
                "$volume": [0, 0, 0, 100, 200, 300],
                "$money": [None, None, None, None, None, None],
            },
            index=index,
        )

        fake_qlib = types.ModuleType("qlib")
        fake_qlib_data = types.ModuleType("qlib.data")
        fake_qlib_data.D = Mock()
        fake_qlib_data.D.features.return_value = df
        fake_stock_names = types.ModuleType("stock_names")
        fake_stock_names.get_stock_name = Mock(return_value="贵州茅台")

        with patch.dict(sys.modules, {
            "qlib": fake_qlib,
            "qlib.data": fake_qlib_data,
            "stock_names": fake_stock_names,
        }), patch.object(quote, "get_calendar_range", return_value=("2026-01-01", "2026-05-07")):
            response = await quote.get_quote(
                "600519",
                start_date=None,
                end_date=None,
                frequency="weekly",
                indicators=True,
            )

        self.assertEqual(response.code, "SH600519")
        self.assertEqual(response.name, "贵州茅台")
        self.assertEqual(len(response.data), 2)
        self.assertEqual(str(response.data[0].date), "2026-05-01")
        self.assertEqual(response.data[0].open, 1400)
        self.assertEqual(response.data[0].close, 1385)
        self.assertEqual(response.data[1].volume, 500)

    async def test_stock_info_accepts_plain_bj_code(self):
        ticker = Mock()
        ticker.info = {
            "currentPrice": 12.5,
            "previousClose": 12.0,
            "fiftyTwoWeekHigh": 15.0,
            "fiftyTwoWeekLow": 9.0,
            "marketCap": 1_000_000,
            "volume": 1000,
        }
        fake_yfinance = types.ModuleType("yfinance")
        fake_yfinance.Ticker = Mock(return_value=ticker)
        fake_stock_names = types.ModuleType("stock_names")
        fake_stock_names.get_stock_name = Mock(return_value="BJ Test")
        fake_stock_names.get_transparency_level = Mock(return_value="MEDIUM")

        with patch.dict(sys.modules, {
            "yfinance": fake_yfinance,
            "stock_names": fake_stock_names,
        }):
            response = await quote.get_stock_info_quote("920118")

        fake_yfinance.Ticker.assert_called_once_with("920118.BJ")
        self.assertEqual(response["code"], "BJ920118")
        self.assertEqual(response["market"], "BJ")
        self.assertEqual(response["change"], 0.5)


if __name__ == "__main__":
    unittest.main()
