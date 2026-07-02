"""
主题热点 API
"""

from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from models.schemas import HotSectorsResponse, SectorInfo, SectorDetailResponse

router = APIRouter()

# 导入核心模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def get_calendar_range():
    """获取 Qlib 日历范围"""
    cal_path = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "calendars" / "day.txt"
    if not cal_path.exists():
        return None, None
    with open(cal_path) as f:
        lines = [l.strip() for l in f if l.strip()]
    if not lines:
        return None, None
    return lines[0], lines[-1]


def _instrument_field_series(df: pd.DataFrame, code: str, field: str) -> pd.Series:
    if df is None or df.empty or field not in df.columns:
        return pd.Series(dtype="float64")
    try:
        if isinstance(df.index, pd.MultiIndex):
            level = "instrument" if "instrument" in (df.index.names or []) else 0
            series = df.xs(code, level=level)[field]
        else:
            series = df[field]
        return pd.to_numeric(series, errors="coerce").dropna().sort_index()
    except Exception:
        return pd.Series(dtype="float64")


def _sector_change_from_qlib_frame(df: pd.DataFrame, stock_codes: list[str]) -> tuple[float | None, int]:
    changes = []
    for code in stock_codes:
        close = _instrument_field_series(df, code, "$close")
        if len(close) < 2:
            continue
        first_price = float(close.iloc[0])
        last_price = float(close.iloc[-1])
        if first_price > 0:
            changes.append((last_price - first_price) / first_price)
    if not changes:
        return None, 0
    return round(float(np.mean(changes)) * 100, 2), len(changes)


def _load_calendar() -> list[str]:
    cal_path = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "calendars" / "day.txt"
    if not cal_path.exists():
        return []
    with open(cal_path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def _load_close_prices(code: str, start_index: int, end_index: int) -> pd.Series:
    bin_path = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "features" / code.lower() / "close.day.bin"
    if not bin_path.exists():
        return pd.Series(dtype="float64")

    values = np.fromfile(bin_path, dtype="float32")
    if len(values) <= 1:
        return pd.Series(dtype="float64")

    bin_start_index = int(values[0])
    data = values[1:]
    slice_start = max(start_index - bin_start_index, 0)
    slice_end = min(end_index - bin_start_index + 1, len(data))
    if slice_start >= slice_end:
        return pd.Series(dtype="float64")

    return pd.to_numeric(pd.Series(data[slice_start:slice_end]), errors="coerce").dropna()


def _sector_change_from_local_bins(stock_codes: list[str], start_index: int, end_index: int) -> tuple[float | None, int]:
    changes = []
    for code in stock_codes:
        close = _load_close_prices(code, start_index, end_index)
        if len(close) < 2:
            continue
        first_price = float(close.iloc[0])
        last_price = float(close.iloc[-1])
        if first_price > 0:
            changes.append((last_price - first_price) / first_price)
    if not changes:
        return None, 0
    return round(float(np.mean(changes)) * 100, 2), len(changes)


def _build_hot_sectors(days: int) -> HotSectorsResponse:
    try:
        calendar = _load_calendar()
        if not calendar:
            raise RuntimeError("calendar data is unavailable")

        end_index = len(calendar) - 1
        start_index = max(0, end_index - days - 20)
        end_date = pd.to_datetime(calendar[end_index])

        from core.sector_definitions import get_sectors_qlib

        sector_results = []
        for sector_name, stock_codes in get_sectors_qlib().items():
            change_pct, stock_count = _sector_change_from_local_bins(stock_codes, start_index, end_index)
            if change_pct is None:
                continue
            sector_results.append(SectorInfo(
                name=sector_name,
                change_pct=change_pct,
                volume=stock_count,
                stock_count=stock_count,
            ))

        sector_results.sort(key=lambda x: x.change_pct, reverse=True)

        return HotSectorsResponse(
            date=end_date.date(),
            sectors=sector_results,
        )

    except Exception as e:
        raise RuntimeError(f"failed to get sector data: {e}") from e


@router.get("/sectors", response_model=HotSectorsResponse)
async def get_hot_sectors(
    days: int = Query(default=10, ge=1, le=60, description="period days")
):
    """Return hot sector ranking without blocking the API event loop."""
    try:
        return await run_in_threadpool(_build_hot_sectors, days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sector/{sector_name}/stocks")
async def get_sector_stocks(
    sector_name: str,
    days: int = Query(default=10, ge=1, le=60, description="统计周期（天）")
):
    """
    获取指定板块内的股票涨跌幅
    """
    try:
        from stock_names import get_stock_name, get_transparency_level
        import qlib
        from qlib.data import D
        from core.sector_definitions import get_sectors_qlib

        # 板块股票池（统一数据源）
        sector_stocks = get_sectors_qlib()

        if sector_name not in sector_stocks:
            raise HTTPException(status_code=404, detail=f"板块不存在: {sector_name}")

        stock_codes = sector_stocks[sector_name]

        # 获取最新日期
        _, end_date_str = get_calendar_range()
        if not end_date_str:
            raise HTTPException(status_code=500, detail="无法获取日历数据")

        end_date = pd.to_datetime(end_date_str)
        start_date = end_date - timedelta(days=days + 20)

        # 获取股票数据
        df = D.features(
            stock_codes,
            ["$close", "$volume"],
            start_time=start_date.strftime("%Y-%m-%d"),
            end_time=end_date.strftime("%Y-%m-%d")
        )

        if df.empty:
            return {"sector": sector_name, "stocks": []}

        results = []

        from models.schemas import SectorStockInfo

        for code in stock_codes:
            close = _instrument_field_series(df, code, "$close")
            if len(close) < 2 or float(close.iloc[0]) <= 0:
                continue
            volume = _instrument_field_series(df, code, "$volume")
            change_pct = (float(close.iloc[-1]) - float(close.iloc[0])) / float(close.iloc[0]) * 100
            vol = float(volume.iloc[-1]) if len(volume) else 0
            results.append(SectorStockInfo(
                code=code,
                name=get_stock_name(code),
                change_pct=round(change_pct, 2),
                volume=vol,
                factor_score=None
            ))

        # 按涨跌幅排序
        results.sort(key=lambda x: x.change_pct, reverse=True)

        return {
            "sector": sector_name,
            "stocks": results
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取板块股票失败: {str(e)}")
