"""
行业板块 API - 基于 yfinance 真实数据
使用成分股真实涨跌幅计算板块表现
板块定义统一来自 core.sector_definitions
"""

import time
from typing import List, Dict
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.sector_definitions import SECTOR_DEFINITIONS  # noqa: E402

router = APIRouter()

# ── 缓存 ──
_cache: Dict[str, tuple[float, dict]] = {}
CACHE_TTL = 300  # 5 分钟


def _to_qlib_code(yf_code: str) -> str:
    pure_code = yf_code.split(".")[0]
    return f"SH{pure_code}" if yf_code.endswith(".SS") else f"SZ{pure_code}"


def _stock_name(yf_code: str) -> str:
    try:
        from stock_names import get_stock_name
        return get_stock_name(_to_qlib_code(yf_code))
    except Exception:
        return _to_qlib_code(yf_code)


def _get_all_stock_prices(period: str = "1mo") -> Dict[str, dict]:
    """批量获取所有板块成分股的价格数据（单次 yfinance 调用）"""
    now = time.time()
    cache_key = "sector_prices"
    if cache_key in _cache:
        ts, cached = _cache[cache_key]
        if now - ts < CACHE_TTL:
            return cached

    # 收集所有唯一样本股代码
    all_codes = list(set(
        code for codes in SECTOR_DEFINITIONS.values() for code in codes
    ))

    try:
        data = yf.download(all_codes, period=period, progress=False, auto_adjust=True)
        if data.empty or "Close" not in data.columns:
            logger.warning("yfinance 板块数据批量下载返回空")
            return {}

        closes = data["Close"]
        result = {}
        for code in all_codes:
            if code in closes.columns:
                series = closes[code].dropna()
                if len(series) >= 2:
                    price = float(series.iloc[-1])
                    prev_price = float(series.iloc[-2])
                    result[code] = {
                        "price": price,
                        "change_pct": round((price - prev_price) / prev_price * 100, 2),
                        "volume": float(data["Volume"][code].iloc[-1]) if "Volume" in data.columns and code in data["Volume"].columns else 0,
                    }

        _cache[cache_key] = (now, result)
        return result
    except Exception as e:
        logger.warning(f"yfinance 批量获取板块数据失败: {e}")
        return {}


@router.get("/performance")
async def get_sector_performance(days: int = Query(5, description="统计周期（天）")):
    """
    获取各行业板块涨跌幅排行（基于成分股真实数据）
    """
    try:
        all_prices = _get_all_stock_prices()
        end_date = datetime.now()

        sector_performance = []
        for sector_name, stock_codes in SECTOR_DEFINITIONS.items():
            changes = []
            for code in stock_codes:
                info = all_prices.get(code)
                if info:
                    changes.append(info["change_pct"])

            avg_change = round(float(np.mean(changes)), 2) if changes else 0.0

            sector_performance.append({
                "industry": sector_name,
                "change_pct": avg_change,
                "stock_count": len(stock_codes),
                "data_available": len(changes),
            })

        sector_performance.sort(key=lambda x: x["change_pct"], reverse=True)

        return {
            "date": end_date.strftime("%Y-%m-%d"),
            "period_days": days,
            "sectors": sector_performance,
        }

    except Exception as e:
        logger.error(f"获取板块表现失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stocks")
async def get_sector_stocks(sector: str = Query(..., description="板块名称")):
    """
    获取指定板块的股票列表（基于真实数据）
    """
    if sector not in SECTOR_DEFINITIONS:
        raise HTTPException(status_code=404, detail=f"板块 '{sector}' 不存在")

    all_prices = _get_all_stock_prices()
    stock_codes = SECTOR_DEFINITIONS[sector]

    stocks = []
    for code in stock_codes:
        info = all_prices.get(code, {})
        stocks.append({
            "code": _to_qlib_code(code),
            "name": _stock_name(code),
            "price": info.get("price", 0),
            "change_pct": info.get("change_pct", 0.0),
        })

    return {
        "industry": sector,
        "count": len(stocks),
        "stocks": stocks,
    }


@router.get("/list")
async def list_sectors():
    """获取所有支持的板块列表"""
    sectors = [
        {"name": name, "count": len(codes), "description": f"{name}板块"}
        for name, codes in SECTOR_DEFINITIONS.items()
    ]
    return {"total": len(sectors), "industries": sectors}
