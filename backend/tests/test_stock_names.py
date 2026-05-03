import unittest
from unittest.mock import patch

import stock_names


class StockNameTests(unittest.TestCase):
    def setUp(self):
        stock_names._NAME_CACHE.clear()

    def test_unknown_prefixed_sh_code_uses_local_market_fallback(self):
        name = stock_names.get_stock_name("SH600010")

        self.assertEqual(name, "SH600010(沪市)")

    def test_unknown_code_does_not_call_yfinance(self):
        with patch.object(stock_names.yf, "Ticker") as ticker:
            stock_names.get_stock_name("SH600010")

        ticker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
