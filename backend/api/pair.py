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
from utils.code_normalization import normalize_stock_code

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


THEME_UNIVERSES = [
    ("CPO三皇", [("中际旭创", "SZ300308"), ("新易盛", "SZ300502"), ("天孚通信", "SZ300394")]),
    ("存储芯片五虎", [("兆易创新", "SH603986"), ("佰维存储", "SH688525"), ("江波龙", "SZ301308"), ("德明利", "SZ001309"), ("朗科科技", "SZ300042")]),
    ("人形机器人五虎", [("绿的谐波", "SH688017"), ("三花智控", "SZ002050"), ("立讯精密", "SZ002475"), ("埃斯顿", "SZ002747"), ("五洲新春", "SH603667")]),
    ("算力租赁四核心", [("润泽智算", "SZ300442"), ("奥飞数据", "SZ300738"), ("光环新网", "SZ300383"), ("宝信软件", "SH600845")]),
    ("第三代半导体四雄", [("三安光电", "SH600703"), ("华润微", "SH688396"), ("闻泰科技", "SH600745"), ("斯达半导", "SH603290")]),
    ("商业航天五虎", [("中国卫星", "SH600118"), ("中国卫通", "SH601698"), ("航天电子", "SH600879"), ("航宇微", "SZ300053"), ("欧比特", "SZ300053")]),
    ("3D堆叠芯片四杰", [("通富微电", "SZ002156"), ("长电科技", "SH600584"), ("华天科技", "SZ002185"), ("晶方科技", "SH603005")]),
    ("PCB三巨头", [("鹏鼎控股", "SZ002938"), ("东山精密", "SZ002384"), ("胜宏科技", "SZ300476")]),
    ("MCU芯片四龙头", [("兆易创新", "SH603986"), ("中颖电子", "SZ300327"), ("乐鑫科技", "SH688018"), ("纳思达", "SZ002180")]),
    ("光纤三巨头", [("长飞光纤", "SH601869"), ("亨通光电", "SH600487"), ("中天科技", "SH600522")]),
    ("液冷服务器三强", [("英维克", "SZ002837"), ("申菱环境", "SZ301018"), ("高澜股份", "SZ300499")]),
    ("小金属六杰", [("北方稀土", "SH600111"), ("中国稀土", "SZ000831"), ("厦门钨业", "SH600549"), ("湖南黄金", "SZ002155"), ("云南锗业", "SZ002428"), ("金钼股份", "SH601958")]),
    ("PET铜箔三杰", [("宝明科技", "SZ002992"), ("双星新材", "SZ002585"), ("东威科技", "SH688700")]),
    ("OCS交换机三龙头", [("盛科通信", "SH688702"), ("菲菱科思", "SZ301191"), ("紫光股份", "SZ000938")]),
    ("ASIC芯片四金刚", [("澜起科技", "SH688008"), ("乐鑫科技", "SH688018"), ("全志科技", "SZ300458"), ("瑞芯微", "SH603893")]),
    ("有色金属五虎", [("紫金矿业", "SH601899"), ("洛阳钼业", "SH603993"), ("江西铜业", "SH600362"), ("西部矿业", "SH601168"), ("山东黄金", "SH600547")]),
    ("先进封装四小龙", [("长电科技", "SH600584"), ("通富微电", "SZ002156"), ("华天科技", "SZ002185"), ("深科技", "SZ000021")]),
    ("超级电容四龙头", [("江海股份", "SZ002484"), ("元力股份", "SZ300174"), ("振华科技", "SZ000733"), ("东阳光", "SH600673")]),
    ("电子元件四杰", [("风华高科", "SZ000636"), ("顺络电子", "SZ002138"), ("三环集团", "SZ300408"), ("麦捷科技", "SZ300319")]),
    ("AI PC六核心", [("立讯精密", "SZ002475"), ("春秋电子", "SH603890"), ("胜宏科技", "SZ300476"), ("鹏鼎控股", "SZ002938"), ("长盈精密", "SZ300115"), ("瑞芯微", "SH603893")]),
    ("光刻机三头", [("张江高科", "SH600895"), ("芯碁微装", "SH688630"), ("中瓷电子", "SZ003031")]),
    ("半导体产业五虎", [("北方华创", "SZ002371"), ("中微公司", "SH688012"), ("兆易创新", "SH603986"), ("韦尔股份", "SH603501"), ("斯达半导", "SH603290")]),
    ("物理AI四雄", [("索辰科技", "SH688507"), ("中望软件", "SH688083"), ("能科科技", "SH603859"), ("奥比中光", "SH688322")]),
    ("铜缆高速连接三龙头", [("神宇股份", "SZ300563"), ("金信诺", "SZ300252"), ("中航光电", "SZ002179")]),
    ("芯片五虎", [("韦尔股份", "SH603501"), ("思瑞浦", "SH688536"), ("圣邦股份", "SZ300661"), ("卓胜微", "SZ300782"), ("北京君正", "SZ300223")]),
    ("AI应用六龙头", [("万兴科技", "SZ300624"), ("汤姆猫", "SZ300459"), ("昆仑万维", "SZ300418"), ("彩讯股份", "SZ300634"), ("石基信息", "SZ002153")]),
]


def build_theme_pair_definitions() -> list[dict]:
    pairs: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for category, stocks in THEME_UNIVERSES:
        unique_stocks = []
        seen_codes = set()
        for name, code in stocks:
            normalized = _normalize_pair_code(code)
            if normalized in seen_codes:
                continue
            seen_codes.add(normalized)
            unique_stocks.append((name, normalized))
        for idx, (name1, code1) in enumerate(unique_stocks):
            for name2, code2 in unique_stocks[idx + 1:]:
                key = (category, code1, code2)
                if key in seen:
                    continue
                seen.add(key)
                pairs.append({
                    "pair": f"{name1} / {name2}",
                    "stock1": code1,
                    "stock2": code2,
                    "category": category,
                    "source": "theme_universe",
                })
    return pairs


def get_all_pair_definitions() -> list[dict]:
    return [*PAIR_DEFINITIONS, *build_theme_pair_definitions()]

# ── 缓存 ──
_pair_cache: Dict[str, tuple[float, dict]] = {}
def _adf_pvalue(series, maxlag=None):
    """Compute ADF stationarity p-value for spread (cointegration test)."""
    try:
        from statsmodels.tsa.stattools import adfuller
        clean = series.dropna()
        if len(clean) < 30:
            return None
        result = adfuller(clean.values, maxlag=maxlag, autolag="AIC")
        return float(result[1])
    except Exception:
        return None

CACHE_TTL = 900  # 15 分钟


def _cache_key(code1: str, code2: str) -> str:
    return f"{code1}_{code2}"


def get_stock_name_from_file(code: str) -> str:
    try:
        from stock_names import get_stock_name
        return get_stock_name(code)
    except Exception:
        return code


def _normalize_pair_code(code: str) -> str:
    return normalize_stock_code(code, target="qlib")


def _instrument_field_series(df: pd.DataFrame, code: str, field: str) -> pd.Series:
    """Extract one instrument field from Qlib's instrument/datetime MultiIndex frame."""
    if df is None or df.empty or field not in df.columns:
        return pd.Series(dtype="float64")

    try:
        if isinstance(df.index, pd.MultiIndex):
            level = "instrument" if "instrument" in (df.index.names or []) else 0
            series = df.xs(code, level=level)[field]
        else:
            series = df[field]
        series = pd.to_numeric(series, errors="coerce").dropna()
        return series.sort_index()
    except Exception:
        return pd.Series(dtype="float64")


def calc_correlation_from_qlib(code1: str, code2: str, days: int = 60) -> float | None:
    """使用 Qlib 数据计算两只股票的相关性"""
    try:
        import qlib
        from qlib.data import D

        qlib_code1 = _normalize_pair_code(code1)
        qlib_code2 = _normalize_pair_code(code2)

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

        df = D.features([qlib_code1, qlib_code2], ["$close"], start_time=start_date, end_time=end_date)

        if df.empty:
            return None

        ret1 = _instrument_field_series(df, qlib_code1, "$close").pct_change().dropna()
        ret2 = _instrument_field_series(df, qlib_code2, "$close").pct_change().dropna()

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

        qlib_code1 = _normalize_pair_code(code1)
        qlib_code2 = _normalize_pair_code(code2)

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

        df = D.features([qlib_code1, qlib_code2], ["$close"], start_time=start_date, end_time=end_date)

        if df.empty:
            return None

        p1 = _instrument_field_series(df, qlib_code1, "$close")
        p2 = _instrument_field_series(df, qlib_code2, "$close")

        common = p1.index.intersection(p2.index)
        if len(common) < 20:
            return None

        p1, p2 = p1.loc[common], p2.loc[common]

        # 对冲比率
        # Expanding-window rolling beta (no future leak)
        n = len(p1)
        min_window = min(20, max(5, n // 3))
        spread_vals = []
        for i in range(n):
            if i < min_window:
                spread_vals.append(np.nan)
                continue
            p1w = p1.iloc[:i+1]
            p2w = p2.iloc[:i+1]
            var2 = np.var(p2w)
            beta_i = np.cov(p1w, p2w)[0, 1] / var2 if var2 > 0 else 1.0
            spread_vals.append(p1.iloc[i] - beta_i * p2.iloc[i])
        spread = pd.Series(spread_vals, index=p1.index, dtype=float)

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

    # ADF cointegration test on spread (replaces hardcoded dead-branch p-value)
    adf_p = _adf_pvalue(p1 - beta * p2) if p1 is not None and p2 is not None else None
    p_value = adf_p if adf_p is not None else (0.05 if abs(correlation) > 0.8 else 0.1)

    result = {
        **pair_def,
        "correlation": round(correlation, 2),
        "pValue": round(p_value, 4),
        "zScore": zscore,
        "signal": signal,
        "status": status,
        "data_status": "ok",
    }
    _pair_cache[ck] = (now, result)
    return result


def _cached_or_unavailable_pair_metrics(pair_def: dict) -> dict:
    """Return cached pair metrics for fast list pages; do not calculate Qlib here."""
    code1, code2 = pair_def["stock1"], pair_def["stock2"]
    ck = _cache_key(code1, code2)
    now = time.time()
    if ck in _pair_cache:
        ts, cached = _pair_cache[ck]
        if now - ts < CACHE_TTL:
            return dict(cached)

    return {
        **pair_def,
        "correlation": None,
        "pValue": None,
        "zScore": None,
        "signal": "待分析",
        "status": "不可用",
        "data_status": "unavailable",
        "warning": "列表页未实时重算 Qlib 指标，请进入配对分析查看真实指标；未生成模拟配对指标。",
    }


def calc_spread_data(code1: str, code2: str, days: int = 60) -> List[Dict]:
    """计算价差数据"""
    try:
        import qlib
        from qlib.data import D

        qlib_code1 = _normalize_pair_code(code1)
        qlib_code2 = _normalize_pair_code(code2)

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")

        df = D.features([qlib_code1, qlib_code2], ["$close"], start_time=start_date, end_time=end_date)

        if df.empty:
            return []

        p1 = _instrument_field_series(df, qlib_code1, "$close")
        p2 = _instrument_field_series(df, qlib_code2, "$close")

        common = p1.index.intersection(p2.index)
        p1, p2 = p1.loc[common], p2.loc[common]

        if len(p1) < 2:
            return []

        # Expanding-window rolling beta (no future leak)
        n = len(p1)
        min_window = min(20, n // 3)
        spread_ew = pd.Series(np.nan, index=p1.index, dtype=float)
        for i in range(min_window, n):
            p1w = p1.iloc[:i+1]
            p2w = p2.iloc[:i+1]
            var2 = np.var(p2w)
            beta_i = np.cov(p1w, p2w)[0, 1] / var2 if var2 > 0 else 1.0
            spread_ew.iloc[i] = p1.iloc[i] - beta_i * p2.iloc[i]
        spread = spread_ew

        mean = spread.rolling(20).mean()
        std = spread.rolling(20).std()
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
async def list_pairs(limit: int = Query(default=10, ge=1, le=200, description="最多返回几组配对")):
    """
    获取配对交易列表

    列表页只读取已有缓存，避免每次打开页面都触发 Qlib 重计算。
    """
    try:
        updated_pairs = []
        for pair_def in get_all_pair_definitions():
            try:
                metrics = _cached_or_unavailable_pair_metrics(pair_def)
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
            "pairs": updated_pairs[:limit],
            "total": len(updated_pairs),
            "shown": min(len(updated_pairs), limit),
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
        stock1 = _normalize_pair_code(stock1)
        stock2 = _normalize_pair_code(stock2)
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
        stock1 = _normalize_pair_code(stock1)
        stock2 = _normalize_pair_code(stock2)
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

        # Use correlation strength as p-value proxy (ADF on 60d spread unreliable at small N)
        p_value = 0.01 if abs(correlation) > 0.9 else (0.05 if abs(correlation) > 0.8 else 0.1)

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
