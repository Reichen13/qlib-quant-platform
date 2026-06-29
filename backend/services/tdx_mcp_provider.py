"""
Optional Tongdaxin MCP data source.

This provider is intentionally disabled unless both TDX_API_KEY and the
specific MCP tool name are configured in the server environment. API keys are
never stored in code or returned by status helpers.
"""

from __future__ import annotations

import json
import os
import urllib.request
import uuid
from typing import Any

from loguru import logger


DEFAULT_TDX_MCP_URL = "https://mcp.tdx.com.cn:3001/mcp"
DEFAULT_TDX_WENDA_TOOL = "tdx_wenda_quotes"


class TdxMcpProvider:
    def __init__(
        self,
        url: str = DEFAULT_TDX_MCP_URL,
        api_key: str | None = None,
        stock_list_tool: str | None = None,
        wenda_tool: str | None = None,
        timeout: float = 15.0,
    ):
        self.url = url.rstrip("/")
        self.api_key = api_key or ""
        self.stock_list_tool = stock_list_tool or ""
        self.wenda_tool = wenda_tool or DEFAULT_TDX_WENDA_TOOL
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "TdxMcpProvider":
        return cls(
            url=os.getenv("TDX_MCP_URL", DEFAULT_TDX_MCP_URL),
            api_key=os.getenv("TDX_API_KEY"),
            stock_list_tool=os.getenv("TDX_MCP_STOCK_LIST_TOOL"),
            wenda_tool=os.getenv("TDX_MCP_WENDA_TOOL", DEFAULT_TDX_WENDA_TOOL),
            timeout=float(os.getenv("TDX_MCP_TIMEOUT", "15")),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def can_fetch_stock_list(self) -> bool:
        return self.is_configured and bool(self.stock_list_tool)

    def safe_status(self) -> dict[str, Any]:
        return {
            "configured": self.is_configured,
            "url": self.url,
            "stock_list_tool": self.stock_list_tool or None,
            "stock_list_enabled": self.can_fetch_stock_list,
            "wenda_tool": self.wenda_tool,
        }

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        if not self.is_configured:
            raise RuntimeError("TDX MCP is not configured")

        session_id = self._initialize_session()
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments or {},
            },
        }
        body, _ = self._post_json(payload, session_id=session_id)
        if body.get("error"):
            raise RuntimeError(str(body["error"]))
        return self._extract_result(body.get("result"))

    def list_tools(self) -> list[dict[str, Any]]:
        if not self.is_configured:
            return []

        try:
            session_id = self._initialize_session()
            body, _ = self._post_json({
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tools/list",
                "params": {},
            }, session_id=session_id)
            tools = body.get("result", {}).get("tools", [])
            return tools if isinstance(tools, list) else []
        except Exception as exc:
            logger.warning(f"TDX MCP tools/list unavailable: {exc}")
            return []

    def query(
        self,
        question: str,
        market_range: str = "AG",
        page: int | str = 1,
        size: int | str = 10,
        tool_name: str | None = None,
    ) -> Any:
        return self.call_tool(tool_name or self.wenda_tool, {
            "question": question,
            "range": market_range,
            "page": str(page),
            "size": str(size),
        })

    def _initialize_session(self) -> str | None:
        body, session_id = self._post_json({
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {
                    "name": "qlib-quant-platform",
                    "version": "1.0",
                },
            },
        })
        if body.get("error"):
            raise RuntimeError(str(body["error"]))
        return session_id

    def _post_json(self, payload: dict[str, Any], session_id: str | None = None) -> tuple[dict[str, Any], str | None]:
        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
            "tdx-api-key": self.api_key,
        }
        if session_id:
            headers["mcp-session-id"] = session_id

        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            raw_body = response.read().decode("utf-8")
            response_session_id = response.headers.get("mcp-session-id")

        return self._decode_response(raw_body), response_session_id

    @staticmethod
    def _decode_response(raw_body: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw_body)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass

        for line in raw_body.splitlines():
            if not line.startswith("data:"):
                continue
            data = line.split(":", 1)[1].strip()
            if not data:
                continue
            try:
                parsed = json.loads(data)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        return {}

    def get_all_stocks(self) -> list[dict[str, Any]]:
        if not self.can_fetch_stock_list:
            return []
        try:
            result = self.call_tool(self.stock_list_tool)
            return self._parse_stock_list(result)
        except Exception as exc:
            logger.warning(f"TDX MCP stock list unavailable: {exc}")
            return []

    @staticmethod
    def _extract_result(result: Any) -> Any:
        if isinstance(result, dict) and isinstance(result.get("content"), list):
            for item in result["content"]:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if not text:
                    continue
                try:
                    return json.loads(text)
                except Exception:
                    return text
        return result

    @classmethod
    def _parse_stock_list(cls, payload: Any) -> list[dict[str, Any]]:
        rows = cls._extract_rows(payload)
        stocks: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = cls._normalize_stock_code(
                row.get("code")
                or row.get("symbol")
                or row.get("security_code")
                or row.get("ts_code")
                or ""
            )
            if not code or code in seen:
                continue
            seen.add(code)
            stocks.append({
                "code": code,
                "code_name": row.get("code_name") or row.get("name") or row.get("security_name") or code,
                "trade_status": str(row.get("trade_status") or row.get("status") or "1"),
                "source": "tdx_mcp",
            })
        return stocks

    @classmethod
    def _extract_rows(cls, payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("stocks", "data", "items", "result", "list"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _normalize_stock_code(raw_code: str) -> str | None:
        code = str(raw_code).strip().upper()
        if not code:
            return None
        if "." in code:
            left, right = code.split(".", 1)
            if left in {"SH", "SZ", "BJ"}:
                market, symbol = left.lower(), right
            elif right in {"SH", "SZ", "BJ"}:
                market, symbol = right.lower(), left
            else:
                return None
        elif code.startswith("SH") or code.startswith("SZ") or code.startswith("BJ"):
            market, symbol = code[:2].lower(), code[2:]
        else:
            symbol = code
            if symbol.startswith("6"):
                market = "sh"
            elif symbol.startswith("0") or symbol.startswith("3"):
                market = "sz"
            elif symbol.startswith(("4", "8")) or symbol.startswith("920"):
                market = "bj"
            else:
                return None

        symbol = symbol[:6]
        if len(symbol) != 6 or not symbol.isdigit():
            return None
        normalized = f"{market}.{symbol}"
        if (
            normalized.startswith("sh.6")
            or normalized.startswith("sz.0")
            or normalized.startswith("sz.3")
            or normalized.startswith("bj.4")
            or normalized.startswith("bj.8")
            or normalized.startswith("bj.920")
        ):
            return normalized
        return None
