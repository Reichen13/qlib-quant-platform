import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

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

    async def test_stock_list_can_fallback_to_qlib_feature_universe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            feature_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data" / "features"
            for code in ("sh600519", "sz000001", "sz300750", "sh688981", "sh510300"):
                stock_dir = feature_dir / code
                stock_dir.mkdir(parents=True)
                (stock_dir / "close.day.bin").write_bytes(b"fake")

            stocks._full_name_cache = {}
            stocks._cache_loaded = False
            with patch("backend.api.stocks.Path.home", return_value=Path(tmpdir)), \
                 patch("backend.api.stocks._load_stock_names_from_provider", return_value={}):
                response = await stocks.get_stock_list()

        codes = {item.code for item in response.stocks}
        self.assertEqual(response.total, 4)
        self.assertIn("SH600519", codes)
        self.assertIn("SZ000001", codes)
        self.assertIn("SZ300750", codes)
        self.assertIn("SH688981", codes)
        self.assertNotIn("SH510300", codes)


if __name__ == "__main__":
    unittest.main()
