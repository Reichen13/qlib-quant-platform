"""A-share stock code normalization helpers."""

from __future__ import annotations


def _market_from_symbol(symbol: str) -> str:
    if symbol.startswith(("6", "5")):
        return "SH"
    if symbol.startswith(("0", "2", "3")):
        return "SZ"
    if symbol.startswith(("4", "8")) or symbol.startswith("920"):
        return "BJ"
    raise ValueError(f"Unsupported A-share code: {symbol}")


def normalize_stock_code(code: str, target: str = "qlib") -> str:
    """Normalize A-share stock codes into common project formats.

    Accepted inputs include plain six-digit codes, SH/SZ-prefixed codes,
    sh./sz. Baostock codes, and .SS/.SZ yfinance codes.
    """
    raw = str(code or "").strip().upper()
    if not raw:
        raise ValueError("Stock code is empty")

    market: str
    symbol: str
    if raw.endswith(".SS") or raw.endswith(".SZ") or raw.endswith(".BJ"):
        symbol, suffix = raw.split(".", 1)
        market = {"SS": "SH", "SZ": "SZ", "BJ": "BJ"}[suffix]
    elif raw.startswith("SH.") or raw.startswith("SZ.") or raw.startswith("BJ."):
        prefix, symbol = raw.split(".", 1)
        market = prefix
    elif raw.startswith("SH") or raw.startswith("SZ") or raw.startswith("BJ"):
        market, symbol = raw[:2], raw[2:]
    else:
        symbol = raw
        market = _market_from_symbol(symbol)

    symbol = symbol.strip()[:6]
    if len(symbol) != 6 or not symbol.isdigit():
        raise ValueError(f"Unsupported stock code: {code}")

    target_lower = target.lower()
    if target_lower == "qlib" or target_lower == "api":
        return f"{market}{symbol}"
    if target_lower == "yf" or target_lower == "yfinance":
        return f"{symbol}.SS" if market == "SH" else f"{symbol}.{market}"
    if target_lower == "baostock":
        return f"{market.lower()}.{symbol}"
    if target_lower == "plain":
        return symbol

    raise ValueError(f"Unsupported target format: {target}")


def normalize_stock_codes(codes: list[str], target: str = "qlib") -> list[str]:
    return [normalize_stock_code(code, target=target) for code in codes]
