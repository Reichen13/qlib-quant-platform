"""
ETF 轮动 API
基于真实 yfinance 数据的 ETF 动量信号
"""

import time
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List, Dict
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException
from loguru import logger

from models.schemas import ETFSignalResponse, ETFInfo

router = APIRouter()

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ETF 列表（保留作为参考数据）
ETF_LIST = {
    "SH510300": "沪深300ETF",
    "SH510500": "中证500ETF",
    "SH512880": "证券ETF",
    "SH512010": "医药ETF",
    "SH512690": "白酒ETF",
    "SH515030": "新能源车ETF",
    "SH512660": "军工ETF",
    "SH512400": "有色金属ETF",
    "SH512480": "计算机ETF",
    "SH512760": "CXO ETF",
    "SH512800": "银行ETF",
    "SH512890": "红利ETF",
    "SH515050": "5GETF",
    "SH515880": "通信ETF",
    "SH516110": "光伏ETF",
    "SH516160": "新能源ETF",
    "SH588000": "科创50ETF",
    "SZ159995": "芯片ETF",
    "SZ159915": "创业板ETF",
    "SZ159949": "创业板50ETF",
}

# ── 缓存 ──
_cache: Dict[str, tuple[float, pd.DataFrame]] = {}
CACHE_TTL = 300  # 5 分钟


def _to_yf_code(code: str) -> str:
    """Qlib 代码格式 → yfinance 格式"""
    pure = code.replace("SH", "").replace("SZ", "")
    return f"{pure}.SS" if code.startswith("SH") else f"{pure}.SZ"


def _fetch_etf_prices(code: str, period: str = "3mo") -> pd.Series | None:
    """获取单只 ETF 的历史收盘价"""
    import yfinance as yf
    yf_code = _to_yf_code(code)
    try:
        ticker = yf.Ticker(yf_code)
        hist = ticker.history(period=period)
        if hist.empty or "Close" not in hist.columns:
            return None
        return hist["Close"]
    except Exception as e:
        logger.warning(f"yfinance 获取 {code} 失败: {e}")
        return None


def _fetch_all_etf_prices(period: str = "3mo") -> Dict[str, pd.Series]:
    """批量获取所有 ETF 收盘价（单次网络调用）"""
    import yfinance as yf
    yf_codes = [_to_yf_code(c) for c in ETF_LIST]
    code_map = {_to_yf_code(c): c for c in ETF_LIST}

    try:
        data = yf.download(yf_codes, period=period, progress=False, auto_adjust=True)
        if data.empty:
            logger.warning("yfinance 批量下载返回空数据")
            return {}

        result = {}
        if "Close" in data.columns:
            closes = data["Close"]
            for yf_code in yf_codes:
                if yf_code in closes.columns:
                    series = closes[yf_code].dropna()
                    if not series.empty:
                        result[code_map[yf_code]] = series
        return result
    except Exception as e:
        logger.warning(f"yfinance 批量下载失败: {e}")
        return {}


def _get_cached_prices() -> Dict[str, pd.Series]:
    """获取缓存的 ETF 价格数据"""
    now = time.time()
    cache_key = "all_etfs"
    if cache_key in _cache:
        ts, cached = _cache[cache_key]
        if now - ts < CACHE_TTL:
            return cached
    prices = _fetch_all_etf_prices()
    if prices:
        _cache[cache_key] = (now, prices)
    return prices


def compute_signal(prices: pd.Series, days: int = 20) -> tuple[str, float, float]:
    """
    基于真实价格计算 ETF 动量信号

    信号逻辑（风险调整动量）：
    - 计算 days 日涨跌幅
    - 动量分数 = 年化收益率 / 年化波动率
    - 加分：价格在 60 日均线之上
    - buy: score >= 2.0, sell: score <= -1.0, else hold
    """
    if len(prices) < max(days, 60):
        return "hold", 0.0, 0.0

    # days 日涨跌幅
    change_pct = (prices.iloc[-1] / prices.iloc[-min(days, len(prices))] - 1) * 100

    # 波动率（日度 → 年化）
    daily_returns = prices.pct_change().dropna()
    if len(daily_returns) < 10:
        return "hold", change_pct, 0.0

    ann_vol = daily_returns.std() * np.sqrt(252)
    ann_return = daily_returns.mean() * 252

    # 风险调整动量分数
    momentum_score = ann_return / ann_vol if ann_vol > 0 else 0

    # 趋势加分：60 日均线之上
    if len(prices) >= 60:
        ma60 = prices.rolling(60).mean().iloc[-1]
        if prices.iloc[-1] > ma60:
            momentum_score += 0.5

    if momentum_score >= 2.0:
        signal = "buy"
    elif momentum_score <= -1.0:
        signal = "sell"
    else:
        signal = "hold"

    return signal, round(change_pct, 2), round(float(momentum_score), 2)


@router.get("/signals", response_model=ETFSignalResponse)
async def get_etf_signals(days: int = 20):
    """
    获取 ETF 轮动信号（真实数据）

    基于 yfinance 实时行情计算动量信号
    """
    try:
        all_prices = _get_cached_prices()
        etfs = []
        top_buy = []
        top_sell = []

        for code, name in ETF_LIST.items():
            prices = all_prices.get(code)
            if prices is None or len(prices) < 10:
                # 降级：单独获取
                prices = _fetch_etf_prices(code)
                if prices is None or len(prices) < 10:
                    continue

            current_price = round(float(prices.iloc[-1]), 3)
            signal, change_pct, _ = compute_signal(prices, days)
            volume = round(float(len(prices)), 0)  # 近似成交量（缺失时用数据长度占位）

            etf_info = ETFInfo(
                code=code,
                name=name,
                price=current_price,
                change_pct=change_pct,
                volume=volume,
                signal=signal,
            )
            etfs.append(etf_info)

            if signal == "buy":
                top_buy.append(code)
            elif signal == "sell":
                top_sell.append(code)

        if not etfs:
            raise HTTPException(status_code=500, detail="无法获取任何 ETF 行情数据")

        etfs.sort(key=lambda x: x.change_pct, reverse=True)

        return ETFSignalResponse(
            date=date.today(),
            etfs=etfs,
            top_buy=top_buy[:5],
            top_sell=top_sell[:5],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 ETF 信号失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取 ETF 信号失败: {str(e)}")


@router.get("/list")
async def list_etfs():
    """获取 ETF 列表"""
    etfs = [
        {"code": code, "name": name, "type": "宽基" if "300" in name or "500" in name or "科创" in name or "创业" in name else "行业"}
        for code, name in ETF_LIST.items()
    ]
    return {"total": len(etfs), "etfs": etfs}


@router.get("/{code}/quote")
async def get_etf_quote(code: str):
    """获取单个 ETF 行情"""
    code_upper = code.upper().strip()

    if code_upper not in ETF_LIST:
        pure = code_upper.replace("SH", "").replace("SZ", "")
        for c in ETF_LIST:
            if pure in c:
                code_upper = c
                break

    if code_upper not in ETF_LIST:
        raise HTTPException(status_code=404, detail="ETF 不存在")

    prices = _fetch_etf_prices(code_upper)

    if prices is None or len(prices) < 2:
        return {"code": code_upper, "name": ETF_LIST[code_upper], "error": "无数据"}

    signal, change_pct, _ = compute_signal(prices)

    return {
        "code": code_upper,
        "name": ETF_LIST[code_upper],
        "price": float(prices.iloc[-1]),
        "change": float(prices.iloc[-1] - prices.iloc[-2]),
        "change_pct": float((prices.iloc[-1] - prices.iloc[-2]) / prices.iloc[-2] * 100),
        "high": float(prices.max()),
        "low": float(prices.min()),
        "volume": float(len(prices)),  # yfinance 日线数据的行数作为近似
        "signal": signal,
    }
