"""Quote data API."""

from datetime import timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from models.schemas import IndicatorData, QuoteData, QuoteResponse
from utils.code_normalization import normalize_stock_code

router = APIRouter()

import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def get_calendar_range():
    """Return local Qlib calendar start and end date strings."""
    cal_path = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "calendars" / "day.txt"
    if not cal_path.exists():
        return None, None
    with open(cal_path, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    if not lines:
        return None, None
    return lines[0], lines[-1]


def _normalize_code(code: str) -> str:
    return normalize_stock_code(code, target="qlib")


def _normalize_yfinance_code(code: str) -> str:
    return normalize_stock_code(code, target="yf")


def _default_start_date(end_dt: pd.Timestamp, frequency: str) -> pd.Timestamp:
    default_days = {
        "daily": 365,
        "weekly": 365 * 3,
        "monthly": 365 * 5,
    }[frequency]
    return end_dt - timedelta(days=default_days)


def _row_adjust_divisor(close: float, row_factor: float | None, latest_real_factor: float) -> float:
    """Per-row divisor to convert stored price toward user-facing forward price.

    Canonical storage: back-adjusted close with cumulative factor > 1.
    Explicit factor≈1.0 rows are treated as already market/forward scale (do not divide).
    When $factor column is missing, fall back to latest real cumulative factor.
    """
    if row_factor is not None:
        if row_factor > 1.01:
            return row_factor
        # placeholder / forward tail written with factor=1.0
        return 1.0
    if latest_real_factor > 1.01 and close > 0:
        fwd = close / latest_real_factor
        if fwd >= 1.0:
            return latest_real_factor
    return 1.0


def _build_price_frame(df: pd.DataFrame, code: str = "") -> pd.DataFrame:
    """Build user-facing forward-adjusted price frame from Qlib OHLC (+ optional $factor)."""
    from core.price_adjust import get_latest_factor

    latest_real_factor = get_latest_factor(code) if code else 1.0
    has_factor_col = "$factor" in df.columns
    records = []
    for idx, row in df.iterrows():
        date_val = idx[1] if isinstance(idx, tuple) else idx
        o = float(row["$open"]) if pd.notna(row["$open"]) else 0.0
        h = float(row["$high"]) if pd.notna(row["$high"]) else 0.0
        l = float(row["$low"]) if pd.notna(row["$low"]) else 0.0
        c = float(row["$close"]) if pd.notna(row["$close"]) else 0.0

        row_factor = None
        if has_factor_col and pd.notna(row.get("$factor")):
            try:
                row_factor = float(row["$factor"])
            except (TypeError, ValueError):
                row_factor = None

        adj = _row_adjust_divisor(c, row_factor, latest_real_factor)

        records.append({
            "date": pd.to_datetime(date_val),
            "open": round(o / adj, 2) if o else 0.0,
            "high": round(h / adj, 2) if h else 0.0,
            "low": round(l / adj, 2) if l else 0.0,
            "close": round(c / adj, 2) if c else 0.0,
            "volume": float(row["$volume"]) if pd.notna(row["$volume"]) else 0.0,
            "amount": float(row["$money"]) if pd.notna(row["$money"]) else None,
        })

    price_df = pd.DataFrame(records).sort_values("date")
    if price_df.empty:
        return price_df

    valid_ohlc = price_df[["open", "high", "low", "close"]].abs().sum(axis=1) > 0
    return price_df[valid_ohlc].copy()


def _resample_price_frame(price_df: pd.DataFrame, frequency: str) -> pd.DataFrame:
    if frequency == "daily":
        return price_df

    rule = "W-FRI" if frequency == "weekly" else "M"
    return (
        price_df.set_index("date")
        .resample(rule)
        .agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "amount": "sum",
        })
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
    )


def _to_quote_data(price_df: pd.DataFrame) -> list[QuoteData]:
    return [
        QuoteData(
            date=pd.to_datetime(row["date"]).date(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]) if pd.notna(row["volume"]) else 0.0,
            amount=float(row["amount"]) if pd.notna(row["amount"]) else None,
        )
        for _, row in price_df.iterrows()
    ]


def _calculate_indicators(quote_data: list[QuoteData]) -> list[IndicatorData]:
    indicator_data = []
    if len(quote_data) < 20:
        return indicator_data

    closes = [item.close for item in quote_data]
    dates = [item.date for item in quote_data]

    for i in range(len(quote_data)):
        indicator = IndicatorData(date=dates[i])

        if i >= 4:
            indicator.ma5 = round(sum(closes[i - 4:i + 1]) / 5, 2)
        if i >= 9:
            indicator.ma10 = round(sum(closes[i - 9:i + 1]) / 10, 2)
        if i >= 19:
            indicator.ma20 = round(sum(closes[i - 19:i + 1]) / 20, 2)
        if i >= 59:
            indicator.ma60 = round(sum(closes[i - 59:i + 1]) / 60, 2)

        if i >= 14:
            gains = []
            losses = []
            for j in range(i - 13, i + 1):
                diff = closes[j] - closes[j - 1]
                if diff > 0:
                    gains.append(diff)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(-diff)

            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            if avg_loss == 0:
                indicator.rsi = 100
            else:
                rs = avg_gain / avg_loss
                indicator.rsi = round(100 - (100 / (1 + rs)), 2)

        indicator_data.append(indicator)

    return indicator_data


@router.get("/{code}", response_model=QuoteResponse)
async def get_quote(
    code: str,
    start_date: Optional[str] = Query(default=None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="End date YYYY-MM-DD"),
    frequency: str = Query(default="daily", description="K-line period: daily/weekly/monthly"),
    indicators: bool = Query(default=True, description="Whether to calculate indicators"),
):
    """Return OHLCV quote data from local Qlib data."""
    try:
        from qlib.data import D
        from stock_names import get_stock_name

        frequency = frequency.lower().strip()
        if frequency not in {"daily", "weekly", "monthly"}:
            raise HTTPException(status_code=400, detail="frequency must be daily, weekly, or monthly")

        code_upper = _normalize_code(code)
        _, latest_date_str = get_calendar_range()
        if not latest_date_str:
            raise HTTPException(status_code=500, detail="Cannot read Qlib calendar data")

        end_dt = pd.to_datetime(end_date) if end_date else pd.to_datetime(latest_date_str)
        start_dt = pd.to_datetime(start_date) if start_date else _default_start_date(end_dt, frequency)

        try:
            df = D.features(
                [code_upper],
                ["$open", "$high", "$low", "$close", "$volume", "$money", "$factor"],
                start_time=start_dt.strftime("%Y-%m-%d"),
                end_time=end_dt.strftime("%Y-%m-%d"),
            )
        except Exception:
            df = D.features(
                [code_upper],
                ["$open", "$high", "$low", "$close", "$volume", "$money"],
                start_time=start_dt.strftime("%Y-%m-%d"),
                end_time=end_dt.strftime("%Y-%m-%d"),
            )

        if df.empty:
            raise HTTPException(status_code=404, detail=f"No quote data for {code_upper}")

        price_df = _build_price_frame(df, code_upper)
        if price_df.empty:
            raise HTTPException(status_code=404, detail=f"No valid K-line data for {code_upper}")

        price_df = _resample_price_frame(price_df, frequency)
        quote_data = _to_quote_data(price_df)
        indicator_data = _calculate_indicators(quote_data) if indicators else None

        return QuoteResponse(
            code=code_upper,
            name=get_stock_name(code_upper),
            data=quote_data,
            indicators=indicator_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get quote data: {str(e)}")


@router.get("/{code}/info")
async def get_stock_info_quote(code: str):
    """Return basic quote-page stock information."""
    try:
        import yfinance as yf
        from stock_names import get_stock_name, get_transparency_level

        code_upper = _normalize_code(code)
        yf_code = _normalize_yfinance_code(code)

        ticker = yf.Ticker(yf_code)
        info = ticker.info
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")
        previous_close = info.get("previousClose")

        return {
            "code": code_upper,
            "name": get_stock_name(code_upper),
            "market": code_upper[:2],
            "transparency": get_transparency_level(code_upper),
            "price": current_price,
            "change": round(current_price - previous_close, 2) if current_price and previous_close else None,
            "change_percent": round(((current_price - previous_close) / previous_close) * 100, 2)
            if current_price and previous_close else None,
            "high_52w": info.get("fiftyTwoWeekHigh"),
            "low_52w": info.get("fiftyTwoWeekLow"),
            "market_cap": info.get("marketCap"),
            "volume": info.get("volume"),
        }

    except Exception as e:
        from stock_names import get_stock_name, get_transparency_level

        code_upper = _normalize_code(code)
        return {
            "code": code_upper,
            "name": get_stock_name(code_upper),
            "market": code_upper[:2],
            "transparency": get_transparency_level(code_upper),
            "price": None,
            "change": None,
            "change_percent": None,
            "error": str(e),
        }
