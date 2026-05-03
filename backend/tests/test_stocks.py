import unittest

from backend.api import stocks


class StockMarketTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        stocks._full_name_cache = {
            "SH600519": "贵州茅台",
            "SZ000001": "平安银行",
        }
        stocks._cache_loaded = True

    async def test_search_returns_sh_market_for_prefixed_sh_code(self):
        response = await stocks.search_stocks("茅台")

        self.assertEqual(response["results"][0]["code"], "SH600519")
        self.assertEqual(response["results"][0]["market"], "SH")

    async def test_stock_info_returns_sh_market_for_prefixed_sh_code(self):
        response = await stocks.get_stock_info("SH600519")

        self.assertEqual(response.code, "SH600519")
        self.assertEqual(response.market, "SH")


if __name__ == "__main__":
    unittest.main()
