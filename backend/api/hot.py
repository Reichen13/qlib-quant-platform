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


def _load_close_at_calendar_index(code: str, cal_index: int) -> float | None:
    """读取某日历索引上的收盘价；无效则返回 None。"""
    bin_path = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "features" / code.lower() / "close.day.bin"
    if not bin_path.exists():
        return None

    values = np.fromfile(bin_path, dtype="float32")
    if len(values) <= 1:
        return None

    bin_start_index = int(values[0])
    data = values[1:]
    offset = cal_index - bin_start_index
    if offset < 0 or offset >= len(data):
        return None
    price = float(data[offset])
    if not np.isfinite(price) or price <= 0:
        return None
    return price


def _load_close_prices(code: str, start_index: int, end_index: int) -> pd.Series:
    """兼容旧调用：返回 [start, end] 切片（含端点）。优先用点查价。"""
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


def _sector_change_from_local_bins(
    stock_codes: list[str],
    start_index: int,
    end_index: int,
) -> tuple[float | None, int]:
    """按交易日索引计算涨跌幅： (P[end] - P[start]) / P[start]。

    days=1 时 start=end-1，即为 1 日涨跌，不再额外 padding。
    """
    if end_index <= start_index:
        return None, 0

    changes = []
    for code in stock_codes:
        first_price = _load_close_at_calendar_index(code, start_index)
        last_price = _load_close_at_calendar_index(code, end_index)
        if first_price is None or last_price is None:
            continue
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
        # N 个交易日涨跌：用 end 与 end-N 两点，禁止 +20 的错误 padding
        start_index = end_index - int(days)
        if start_index < 0:
            raise RuntimeError(f"calendar too short for days={days}")
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

        calendar = _load_calendar()
        if not calendar:
            raise HTTPException(status_code=500, detail="无法获取日历数据")
        end_index = len(calendar) - 1
        start_index = end_index - int(days)
        if start_index < 0:
            raise HTTPException(status_code=400, detail=f"日历过短，无法计算 {days} 日涨跌")

        # 优先本地 bin 按交易日索引取价，避免自然日 +20 错窗
        results = []
        from models.schemas import SectorStockInfo

        for code in stock_codes:
            first_price = _load_close_at_calendar_index(code, start_index)
            last_price = _load_close_at_calendar_index(code, end_index)
            if first_price is None or last_price is None:
                continue
            change_pct = (last_price - first_price) / first_price * 100
            # 成交量仍走 Qlib（可选，失败则为 0）
            vol = 0.0
            try:
                vol_df = D.features(
                    [code],
                    ["$volume"],
                    start_time=calendar[end_index],
                    end_time=calendar[end_index],
                )
                vol_s = _instrument_field_series(vol_df, code, "$volume")
                if len(vol_s):
                    vol = float(vol_s.iloc[-1])
            except Exception:
                vol = 0.0
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
