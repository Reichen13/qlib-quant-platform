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


class FakeMcpResponse:
    def __init__(self, body, session_id=None):
        self._body = body.encode("utf-8")
        self.headers = {}
        if session_id:
            self.headers["mcp-session-id"] = session_id

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


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
        self.assertEqual(status["wenda_tool"], "tdx_wenda_quotes")
        self.assertNotIn("test-placeholder-key", str(status))

    def test_call_tool_uses_official_mcp_session_and_sse_response(self):
        responses = [
            FakeMcpResponse(
                'event: message\n'
                'data: {"result":{"protocolVersion":"2025-06-18"},"jsonrpc":"2.0","id":1}\n',
                session_id="session-1",
            ),
            FakeMcpResponse(
                'event: message\n'
                'data: {"result":{"content":[{"type":"text","text":"{\\"meta\\":{\\"code\\":0},\\"data\\":[[\\"600519\\"]] }"}]},"jsonrpc":"2.0","id":2}\n',
                session_id="session-1",
            ),
        ]
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            return responses.pop(0)

        provider = TdxMcpProvider(api_key="test-placeholder-key", timeout=3)
        with patch("backend.services.tdx_mcp_provider.urllib.request.urlopen", side_effect=fake_urlopen):
            result = provider.call_tool("tdx_wenda_quotes", {"question": "贵州茅台最新行情"})

        self.assertEqual(result["meta"]["code"], 0)
        self.assertEqual(result["data"][0][0], "600519")
        self.assertEqual(requests[0].headers.get("Accept"), "application/json, text/event-stream")
        self.assertNotIn("Mcp-session-id", requests[0].headers)
        self.assertEqual(requests[1].headers.get("Mcp-session-id"), "session-1")

    def test_query_uses_default_official_wenda_tool(self):
        provider = TdxMcpProvider(api_key="test-placeholder-key")
        with patch.object(provider, "call_tool", return_value={"ok": True}) as call_tool:
            result = provider.query("贵州茅台600519最新行情", size=5)

        self.assertEqual(result, {"ok": True})
        call_tool.assert_called_once_with("tdx_wenda_quotes", {
            "question": "贵州茅台600519最新行情",
            "range": "AG",
            "page": "1",
            "size": "5",
        })

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
