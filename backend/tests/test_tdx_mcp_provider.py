import os
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

try:
    import pandas  # noqa: F401
except Exception:
    if "pandas" not in sys.modules:
        sys.modules["pandas"] = types.SimpleNamespace(DataFrame=object)

from backend.services.data_provider import DataProvider
from backend.services.tdx_mcp_provider import TdxMcpProvider


class FakeTdxProvider:
    def get_all_stocks(self):
        return [
            {"code": "sh.600519", "code_name": "贵州茅台", "trade_status": "1", "source": "tdx_mcp"},
            {"code": "sz.000001", "code_name": "平安银行", "trade_status": "1", "source": "tdx_mcp"},
        ]


class TdxMcpProviderTests(unittest.TestCase):
    def test_from_env_is_disabled_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = TdxMcpProvider.from_env()

        self.assertFalse(provider.is_configured)
        self.assertEqual(provider.get_all_stocks(), [])
        self.assertNotIn("api", provider.safe_status())

    def test_safe_status_does_not_expose_api_key(self):
        with patch.dict(os.environ, {
            "TDX_API_KEY": "test-placeholder-key",
            "TDX_MCP_STOCK_LIST_TOOL": "stock_list",
        }, clear=True):
            provider = TdxMcpProvider.from_env()

        status = provider.safe_status()

        self.assertTrue(status["configured"])
        self.assertEqual(status["stock_list_tool"], "stock_list")
        self.assertNotIn("test-placeholder-key", str(status))

    def test_data_provider_prefers_tdx_stock_list_when_available(self):
        provider = DataProvider()

        with patch.object(provider, "_get_tdx_provider", return_value=FakeTdxProvider()), \
             patch.object(provider, "_get_bs_client", side_effect=AssertionError("baostock should not be called")):
            stocks = provider.get_all_stocks()

        self.assertEqual(len(stocks), 2)
        self.assertEqual(stocks[0]["code"], "sh.600519")
        self.assertEqual(stocks[0]["source"], "tdx_mcp")

    def test_data_provider_uses_shared_code_normalization_for_baostock_codes(self):
        self.assertEqual(DataProvider._to_baostock_code("600519"), "sh.600519")
        self.assertEqual(DataProvider._to_baostock_code("600519.SS"), "sh.600519")
        self.assertEqual(DataProvider._to_baostock_code("300750"), "sz.300750")
        self.assertEqual(DataProvider._to_baostock_code("688981"), "sh.688981")
        self.assertEqual(DataProvider._from_baostock_code("sh.688981"), "SH688981")

    def test_tdx_stock_list_keeps_beijing_exchange_codes(self):
        payload = {
            "data": [
                {"code": "430047", "name": "北交所样本一"},
                {"code": "BJ830799", "name": "北交所样本二"},
                {"code": "920118.BJ", "name": "北交所样本三"},
            ]
        }

        stocks = TdxMcpProvider._parse_stock_list(payload)

        self.assertEqual([s["code"] for s in stocks], ["bj.430047", "bj.830799", "bj.920118"])


if __name__ == "__main__":
    unittest.main()
