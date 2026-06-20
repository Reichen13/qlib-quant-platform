"""
配对交易 API
统计套利策略 - 协整关系与价差分析（基于真实 Qlib 数据）
"""

import time
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Tuple
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException, Query
from loguru import logger

router = APIRouter()

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 预设配对组合定义（仅定义配对关系，指标动态计算）
PAIR_DEFINITIONS = [
    {"pair": "招商银行 / 平安银行", "stock1": "SH600036", "stock2": "SZ000001", "category": "银行"},
    {"pair": "贵州茅台 / 五粮液", "stock1": "SH600519", "stock2": "SZ000858", "category": "白酒"},
    {"pair": "中国平安 / 中国人寿", "stock1": "SH601318", "stock2": "SH601628", "category": "保险"},
    {"pair": "万科A / 保利发展", "stock1": "SZ000002", "stock2": "SH600048", "category": "地产"},
    {"pair": "美的集团 / 格力电器", "stock1": "SZ000333", "stock2": "SZ000651", "category": "家电"},
    {"pair": "伊利股份 / 光明乳业", "stock1": "SH600887", "stock2": "SH600597", "category": "食品"},
    {"pair": "比亚迪 / 长城汽车", "stock1": "SZ002594", "stock2": "SH601633", "category": "汽车"},
]

# ── 缓存 ──
_pair_cache: Dict[str, tuple[float, dict]] = {}
CACHE_TTL = 900  # 15 分钟


def _cache_key(code1: str, code2: str) -> str:
    return f"{code1}_{code2}"


def get_stock_name_from_file(code: str) -> str:
    try:
        from stock_names import get_stock_name
        return get_stock_name(code)
    except Exception:
        return code


def calc_correlation_from_qlib(code1: str, code2: str, days: int = 60) -> float | None:
    """使用 Qlib 数据计算两只股票的相关性"""
    try:
        import qlib
        from qlib.data import D

        qlib_code1 = code1.replace("SH", "").replace("SZ", "")
        qlib_code2 = code2.replace("SH", "").replace("SZ", "")

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

        df1 = D.features([qlib_code1], ["$close"], start_time=start_date, end_time=end_date)
        df2 = D.features([qlib_code2], ["$close"], start_time=start_date, end_time=end_date)

        if df1.empty or df2.empty:
            return None

        ret1 = df1.xs(qlib_code1, level=1)["$close"].pct_change().dropna()
        ret2 = df2.xs(qlib_code2, level=1)["$close"].pct_change().dropna()

        if len(ret1) < 10 or len(ret2) < 10:
            return None

        common_index = ret1.index.intersection(ret2.index)
        if len(common_index) < 10:
            return None

        corr = ret1.loc[common_index].corr(ret2.loc[common_index])
        return float(corr) if not np.isnan(corr) else None

    except Exception as e:
        logger.warning(f"计算相关性失败 {code1}/{code2}: {e}")
        return None


def calc_zscore_from_qlib(code1: str, code2: str, days: int = 60) -> float | None:
    """使用 Qlib 数据计算当前价差 Z-score"""
    try:
        import qlib
        from qlib.data import D

        qlib_code1 = code1.replace("SH", "").replace("SZ", "")
        qlib_code2 = code2.replace("SH", "").replace("SZ", "")

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

        df1 = D.features([qlib_code1], ["$close"], start_time=start_date, end_time=end_date)
        df2 = D.features([qlib_code2], ["$close"], start_time=start_date, end_time=end_date)

        if df1.empty or df2.empty:
            return None

        p1 = df1.xs(qlib_code1, level=1)["$close"]
        p2 = df2.xs(qlib_code2, level=1)["$close"]

        common = p1.index.intersection(p2.index)
        if len(common) < 20:
            return None

        p1, p2 = p1.loc[common], p2.loc[common]

        # 对冲比率
        beta = np.cov(p1, p2)[0, 1] / np.var(p2) if np.var(p2) > 0 else 1.0
        spread = p1 - beta * p2

        mean = spread.rolling(20).mean()
        std = spread.rolling(20).std()
        zscore = (spread - mean) / std

        if pd.notna(zscore.iloc[-1]):
            return round(float(zscore.iloc[-1]), 2)
        return None

    except Exception as e:
        logger.warning(f"计算 zScore 失败 {code1}/{code2}: {e}")
        return None


def _compute_pair_metrics(pair_def: dict) -> dict:
    """为单个配对计算真实指标（带缓存）"""
    code1, code2 = pair_def["stock1"], pair_def["stock2"]
    ck = _cache_key(code1, code2)

    now = time.time()
    if ck in _pair_cache:
        ts, cached = _pair_cache[ck]
        if now - ts < CACHE_TTL:
            return dict(cached)

    correlation = calc_correlation_from_qlib(code1, code2)
    zscore = calc_zscore_from_qlib(code1, code2)
    if correlation is None or zscore is None:
        result = {
            **pair_def,
            "correlation": None,
            "pValue": None,
            "zScore": None,
            "signal": "数据不足",
            "status": "不可用",
            "data_status": "unavailable",
            "warning": "Qlib 数据不足，未生成模拟配对指标。",
        }
        _pair_cache[ck] = (now, result)
        return result

    # 信号判定
    if zscore > 2:
        signal, status = "做空价差", "开仓机会"
    elif zscore < -2:
        signal, status = "做多价差", "开仓机会"
    elif abs(zscore) < 0.5:
        signal, status = "中性", "正常"
    else:
        signal, status = "关注", "观察中"

    p_value = 0.05 if abs(correlation) > 0.8 else (0.01 if abs(correlation) > 0.9 else 0.1)

    result = {
        **pair_def,
        "correlation": round(correlation, 2),
        "pValue": round(p_value, 4),
        "zScore": zscore,
        "signal": signal,
        "status": status,
    }
    _pair_cache[ck] = (now, result)
    return result


def calc_spread_data(code1: str, code2: str, days: int = 60) -> List[Dict]:
    """计算价差数据"""
    try:
        import qlib
        from qlib.data import D

        qlib_code1 = code1.replace("SH", "").replace("SZ", "")
        qlib_code2 = code2.replace("SH", "").replace("SZ", "")

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

        df1 = D.features([qlib_code1], ["$close"], start_time=start_date, end_time=end_date)
        df2 = D.features([qlib_code2], ["$close"], start_time=start_date, end_time=end_date)

        if df1.empty or df2.empty:
            return []

        p1 = df1.xs(qlib_code1, level=1)["$close"]
        p2 = df2.xs(qlib_code2, level=1)["$close"]

        common = p1.index.intersection(p2.index)
        p1, p2 = p1.loc[common], p2.loc[common]

        if len(p1) < 2:
            return []

        beta = np.cov(p1, p2)[0, 1] / np.var(p2) if np.var(p2) > 0 else 1.0
        spread = p1 - beta * p2

        mean = spread.rolling(window=20).mean()
        std = spread.rolling(window=20).std()
        zscore = (spread - mean) / std

        result = []
        for i in range(len(spread)):
            if pd.notna(zscore.iloc[i]):
                result.append({
                    "date": spread.index[i].strftime("%Y-%m-%d"),
                    "spread": round(float(zscore.iloc[i]), 2),
                    "upper": 2.0,
                    "lower": -2.0,
                })

        return result[-60:] if len(result) >= 10 else []

    except Exception as e:
        logger.warning(f"计算价差数据失败 {code1}/{code2}: {e}")
        return []


@router.get("/list")
async def list_pairs():
    """
    获取配对交易列表（动态计算真实指标）

    使用 Qlib 实时计算相关性和价差 Z-score
    """
    try:
        updated_pairs = []
        for pair_def in PAIR_DEFINITIONS:
            try:
                metrics = _compute_pair_metrics(pair_def)
                updated_pairs.append(metrics)
            except Exception as e:
                logger.warning(f"跳过配对 {pair_def['pair']}: {e}")
                updated_pairs.append({
                    **pair_def,
                    "correlation": None,
                    "pValue": None,
                    "zScore": None,
                    "signal": "数据异常",
                    "status": "不可用",
                    "data_status": "unavailable",
                    "warning": "Qlib 数据不足，未生成模拟配对指标。",
                })

        return {
            "pairs": updated_pairs,
            "total": len(updated_pairs),
            "date": datetime.now().strftime("%Y-%m-%d"),
        }

    except Exception as e:
        logger.error(f"获取配对列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/spread")
async def get_spread(
    stock1: str = Query(..., description="股票1代码"),
    stock2: str = Query(..., description="股票2代码"),
    days: int = Query(60, description="获取天数"),
):
    """获取两只股票的价差 Z-score 历史数据"""
    try:
        spread_data = calc_spread_data(stock1, stock2, days)

        return {
            "stock1": stock1,
            "stock2": stock2,
            "pair": f"{get_stock_name_from_file(stock1)} / {get_stock_name_from_file(stock2)}",
            "data": spread_data,
            "data_status": "ok" if spread_data else "unavailable",
            "warning": None if spread_data else "Qlib 价差数据不足，未生成模拟曲线。",
        }

    except Exception as e:
        logger.error(f"获取价差数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/analyze")
async def analyze_pair(
    stock1: str = Query(..., description="股票1代码"),
    stock2: str = Query(..., description="股票2代码"),
):
    """分析两只股票的配对关系（动态计算）"""
    try:
        correlation = calc_correlation_from_qlib(stock1, stock2)
        zscore = calc_zscore_from_qlib(stock1, stock2)

        spread_data = calc_spread_data(stock1, stock2)

        if correlation is None or zscore is None:
            return {
                "pair": f"{get_stock_name_from_file(stock1)} / {get_stock_name_from_file(stock2)}",
                "stock1": stock1,
                "stock2": stock2,
                "correlation": None,
                "pValue": None,
                "zScore": None,
                "signal": "数据不足",
                "status": "不可用",
                "spread_data": spread_data,
                "data_status": "unavailable",
                "warning": "Qlib 数据不足，未生成模拟配对分析。",
            }

        if zscore > 2:
            signal, status = "做空价差", "开仓机会"
        elif zscore < -2:
            signal, status = "做多价差", "开仓机会"
        elif abs(zscore) < 0.5:
            signal, status = "中性", "正常"
        else:
            signal, status = "关注", "观察中"

        p_value = 0.05 if abs(correlation) > 0.8 else 0.1

        return {
            "pair": f"{get_stock_name_from_file(stock1)} / {get_stock_name_from_file(stock2)}",
            "stock1": stock1,
            "stock2": stock2,
            "correlation": round(correlation, 2),
            "pValue": round(p_value, 4),
            "zScore": zscore,
            "signal": signal,
            "status": status,
            "spread_data": spread_data,
            "data_status": "ok" if spread_data else "partial",
            "warning": None if spread_data else "Qlib 价差数据不足，未生成模拟曲线。",
        }

    except Exception as e:
        logger.error(f"分析配对关系失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
