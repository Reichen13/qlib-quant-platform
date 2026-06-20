"""
ETF 轮动 API
优先使用本地 Qlib ETF 日线数据，外部行情仅作为备用。
"""

import time
from pathlib import Path
from datetime import date, timedelta
from typing import Dict
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
def _is_etf_code(code: str) -> bool:
    code = code.upper()
    return (
        code.startswith("SH51")
        or code.startswith("SH56")
        or code.startswith("SH58")
        or code.startswith("SZ159")
        or code.startswith("SZ16")
    )


def _normalize_qlib_code(raw_code: str) -> str:
    code = raw_code.strip().upper()
    if code.startswith("SH.") or code.startswith("SZ."):
        prefix, pure = code.split(".", 1)
        return f"{prefix}{pure}"
    return code


def _discover_local_etf_codes() -> list[str]:
    features_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "features"
    if not features_dir.exists():
        return []
    codes = []
    try:
        for child in features_dir.iterdir():
            code = _normalize_qlib_code(child.name)
            if _is_etf_code(code):
                codes.append(code)
    except Exception as exc:
        logger.warning(f"读取本地 ETF 特征目录失败: {exc}")
    return sorted(set(codes))


def _get_etf_universe() -> dict[str, str]:
    universe = dict(ETF_LIST)
    for code in _discover_local_etf_codes():
        universe.setdefault(code, code)
    return dict(sorted(universe.items()))


def _get_etf_name(code: str) -> str:
    return _get_etf_universe().get(code, code)


_cache: Dict[str, tuple[float, Dict[str, pd.DataFrame]]] = {}
CACHE_TTL = 300  # 5 分钟


def _to_yf_code(code: str) -> str:
    """Qlib 代码格式 → yfinance 格式"""
    pure = code.replace("SH", "").replace("SZ", "")
    return f"{pure}.SS" if code.startswith("SH") else f"{pure}.SZ"


def _read_latest_calendar_date() -> str | None:
    cal_path = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "calendars" / "day.txt"
    if not cal_path.exists():
        return None
    try:
        lines = [line.strip() for line in cal_path.read_text().splitlines() if line.strip()]
        return lines[-1] if lines else None
    except Exception as exc:
        logger.warning(f"读取 Qlib 日历失败: {exc}")
        return None


def _etf_type(name: str) -> str:
    if any(k in name for k in ["300", "500", "科创", "创业"]):
        return "宽基"
    if any(k in name for k in ["证券", "银行", "红利"]):
        return "金融"
    if any(k in name for k in ["医药", "CXO"]):
        return "医药"
    if any(k in name for k in ["新能源", "光伏"]):
        return "新能源"
    if any(k in name for k in ["芯片", "计算机", "5G", "通信"]):
        return "科技"
    if any(k in name for k in ["军工"]):
        return "国防"
    if any(k in name for k in ["有色"]):
        return "资源"
    if any(k in name for k in ["白酒"]):
        return "消费"
    return "其他"


def _fetch_etf_history_from_qlib(code: str, period: str = "6mo") -> pd.DataFrame | None:
    """从本地 Qlib 读取单只 ETF 历史行情。"""
    try:
        from qlib.data import D

        latest_date = _read_latest_calendar_date()
        end_dt = pd.to_datetime(latest_date).date() if latest_date else date.today()
        start_dt = end_dt - timedelta(days=190 if period == "6mo" else 365)

        df = D.features(
            [code],
            ["$open", "$high", "$low", "$close", "$volume", "$money", "$amount"],
            start_time=start_dt.strftime("%Y-%m-%d"),
            end_time=end_dt.strftime("%Y-%m-%d"),
            freq="day",
        )
        if df is None or df.empty or "$close" not in df.columns:
            return None

        data = df.reset_index()
        if "datetime" in data.columns:
            data = data.set_index("datetime")

        hist = pd.DataFrame({
            "Open": data.get("$open"),
            "High": data.get("$high"),
            "Low": data.get("$low"),
            "Close": data.get("$close"),
            "Volume": data.get("$volume"),
            "Money": data.get("$money"),
            "Amount": data.get("$amount"),
        }).dropna(subset=["Close"])

        if hist.empty:
            return None
        return hist.sort_index()
    except Exception as exc:
        logger.warning(f"Qlib 获取 ETF {code} 失败: {exc}")
        return None


def _fetch_etf_history_from_yfinance(code: str, period: str = "6mo") -> pd.DataFrame | None:
    """通过 yfinance 获取单只 ETF 的历史行情（备用）。"""
    import yfinance as yf
    yf_code = _to_yf_code(code)
    try:
        ticker = yf.Ticker(yf_code)
        hist = ticker.history(period=period)
        if hist.empty or "Close" not in hist.columns:
            return None
        return hist
    except Exception as e:
        logger.warning(f"yfinance 获取 {code} 失败: {e}")
        return None


def _fetch_etf_history(code: str, period: str = "6mo") -> pd.DataFrame | None:
    """获取单只 ETF 历史行情：本地 Qlib 优先，yfinance 备用。"""
    hist = _fetch_etf_history_from_qlib(code, period)
    if hist is not None and len(hist) >= 10:
        return hist
    return _fetch_etf_history_from_yfinance(code, period)


def _fetch_etf_prices(code: str, period: str = "6mo") -> pd.Series | None:
    """获取单只 ETF 的历史收盘价"""
    hist = _fetch_etf_history(code, period)
    if hist is None:
        return None
    return hist["Close"]


def _fetch_all_etf_history_from_qlib(period: str = "6mo") -> Dict[str, pd.DataFrame]:
    """从本地 Qlib 批量读取 ETF 行情。"""
    result = {}
    for code in _get_etf_universe():
        hist = _fetch_etf_history_from_qlib(code, period)
        if hist is not None and len(hist) >= 10:
            result[code] = hist
    return result


def _fetch_all_etf_history_from_yfinance(period: str = "6mo") -> Dict[str, pd.DataFrame]:
    """批量获取所有 ETF 行情（单次网络调用，备用）

    Returns:
        code -> DataFrame(Open/High/Low/Close/Volume)
    """
    import yfinance as yf
    universe = _get_etf_universe()
    yf_codes = [_to_yf_code(c) for c in universe]
    code_map = {_to_yf_code(c): c for c in universe}

    try:
        data = yf.download(yf_codes, period=period, progress=False, auto_adjust=True)
        if data.empty:
            logger.warning("yfinance 批量下载返回空数据")
            return {}

        result: Dict[str, pd.DataFrame] = {}
        for yf_code in yf_codes:
            columns = {}
            for field in ["Open", "High", "Low", "Close", "Volume"]:
                if field in data.columns and yf_code in data[field].columns:
                    columns[field] = data[field][yf_code]
            if "Close" in columns:
                df = pd.DataFrame(columns).dropna(subset=["Close"])
                if not df.empty:
                    result[code_map[yf_code]] = df

        return result
    except Exception as e:
        logger.warning(f"yfinance 批量下载失败: {e}")
        return {}


def _fetch_all_etf_history(period: str = "6mo") -> Dict[str, pd.DataFrame]:
    """获取 ETF 行情：先用本地 Qlib，缺失部分再尝试 yfinance 补充。"""
    result = _fetch_all_etf_history_from_qlib(period)
    missing_codes = [code for code in _get_etf_universe() if code not in result]

    if missing_codes:
        yf_history = _fetch_all_etf_history_from_yfinance(period)
        for code in missing_codes:
            hist = yf_history.get(code)
            if hist is not None and len(hist) >= 10:
                result[code] = hist

    return result


def _get_cached_history() -> Dict[str, pd.DataFrame]:
    """获取缓存的 ETF 行情数据"""
    now = time.time()
    cache_key = "all_etfs"
    if cache_key in _cache:
        ts, cached_history = _cache[cache_key]
        if now - ts < CACHE_TTL:
            return cached_history
    history = _fetch_all_etf_history()
    if history:
        _cache[cache_key] = (now, history)
    return history


def compute_signal(prices: pd.Series, days: int = 20) -> tuple[str, float, float | None]:
    """
    基于真实价格计算 ETF 动量信号

    信号逻辑（风险调整动量）：
    - 计算 days 日涨跌幅
    - 动量分数 = 年化收益率 / 年化波动率
    - 加分：价格在 60 日均线之上
    - buy: score >= 2.0, sell: score <= -1.0, else hold
    """
    if len(prices) <= days:
        return "hold", 0.0, None

    # days 日涨跌幅
    change_pct = (prices.iloc[-1] / prices.iloc[-days] - 1) * 100

    # 波动率（日度 → 年化）
    daily_returns = prices.pct_change().dropna()
    if len(daily_returns) < 10:
        return "hold", round(float(change_pct), 2), None

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


def _period_change(prices: pd.Series, days: int) -> float | None:
    if len(prices) <= days:
        return None
    value = (prices.iloc[-1] / prices.iloc[-days] - 1) * 100
    return round(float(value), 2)


def _compute_etf_metrics(code: str, hist: pd.DataFrame, days: int = 20) -> ETFInfo | None:
    prices = hist["Close"].dropna()
    if len(prices) < 10:
        return None

    signal, change_pct, momentum_score = compute_signal(prices, days)
    daily_returns = prices.pct_change().dropna()
    ann_vol = float(daily_returns.std() * np.sqrt(252)) if len(daily_returns) >= 10 else None
    ann_return = float(daily_returns.mean() * 252) if len(daily_returns) >= 10 else None
    sharpe = round(ann_return / ann_vol, 2) if ann_vol and ann_vol > 0 else None
    above_ma20 = None
    if len(prices) >= 20:
        above_ma20 = 1.0 if prices.iloc[-1] > prices.rolling(20).mean().iloc[-1] else 0.0

    volume = None
    amount = None
    if "Volume" in hist.columns:
        volumes = hist["Volume"].dropna()
        if not volumes.empty:
            volume = float(volumes.iloc[-1])
    if "Money" in hist.columns:
        money = hist["Money"].dropna()
        if not money.empty:
            amount = float(money.iloc[-1])
    if amount is None and "Amount" in hist.columns:
        amount_values = hist["Amount"].dropna()
        if not amount_values.empty:
            amount = float(amount_values.iloc[-1])
    if amount is None and volume is not None:
        amount = volume * float(prices.iloc[-1])

    name = _get_etf_name(code)
    return ETFInfo(
        code=code,
        name=name,
        type=_etf_type(name),
        price=round(float(prices.iloc[-1]), 3),
        change_pct=change_pct,
        volume=round(volume or 0, 0),
        amount=round(amount / 100_000_000, 2) if amount is not None else None,
        change_5d=_period_change(prices, 5),
        change_10d=_period_change(prices, 10),
        change_20d=_period_change(prices, 20),
        sharpe=sharpe,
        above_ma20=above_ma20,
        volatility=round(ann_vol, 4) if ann_vol is not None else None,
        momentum_score=momentum_score,
        pe=None,
        size=None,
        excess_return=None,
        signal=signal,
    )


@router.get("/signals", response_model=ETFSignalResponse)
async def get_etf_signals(days: int = 20):
    """
    获取 ETF 轮动信号（真实数据）

    基于本地 Qlib 或备用外部行情计算动量信号
    """
    try:
        all_history = _get_cached_history()
        etfs = []
        top_buy = []
        top_sell = []

        for code, name in _get_etf_universe().items():
            hist = all_history.get(code)
            if hist is None or len(hist) < 10:
                # 降级：单独获取
                hist = _fetch_etf_history(code)
                if hist is None or len(hist) < 10:
                    continue

            etf_info = _compute_etf_metrics(code, hist, days)
            if etf_info is None:
                continue
            etfs.append(etf_info)

            if etf_info.signal == "buy":
                top_buy.append(code)
            elif etf_info.signal == "sell":
                top_sell.append(code)

        if not etfs:
            return ETFSignalResponse(
                date=date.today(),
                etfs=[],
                top_buy=[],
                top_sell=[],
                warning="暂无可靠 ETF 行情数据，未生成模拟轮动信号。",
            )

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
    """获取 ETF 列表及可计算的真实行情指标"""
    all_history = _get_cached_history()
    etfs = []
    missing = []
    for code, name in _get_etf_universe().items():
        hist = all_history.get(code)
        if hist is None or len(hist) < 10:
            hist = _fetch_etf_history(code)
        if hist is None or len(hist) < 10:
            missing.append(code)
            etfs.append({
                "code": code,
                "name": name,
                "type": _etf_type(name),
                "data_status": "unavailable",
                "warning": "无法获取 ETF 行情数据",
            })
            continue
        metrics = _compute_etf_metrics(code, hist)
        if metrics is not None:
            etfs.append(metrics.model_dump())
    warning = None
    if missing:
        warning = f"{len(missing)} 只 ETF 暂无可靠行情数据，相关指标显示为空。"
    return {"total": len(etfs), "etfs": etfs, "warning": warning}


@router.get("/{code}/quote")
async def get_etf_quote(code: str):
    """获取单个 ETF 行情"""
    code_upper = code.upper().strip()
    universe = _get_etf_universe()

    if code_upper not in universe:
        pure = code_upper.replace("SH", "").replace("SZ", "")
        for c in universe:
            if pure in c:
                code_upper = c
                break

    if code_upper not in universe:
        raise HTTPException(status_code=404, detail="ETF 不存在")

    hist = _fetch_etf_history(code_upper)

    if hist is None or len(hist) < 2:
        return {"code": code_upper, "name": universe[code_upper], "error": "无数据"}

    prices = hist["Close"].dropna()
    signal, change_pct, _ = compute_signal(prices)
    volume = None
    amount = None
    if "Volume" in hist.columns:
        volumes = hist["Volume"].dropna()
        if not volumes.empty:
            volume = float(volumes.iloc[-1])
    if "Money" in hist.columns:
        money = hist["Money"].dropna()
        if not money.empty:
            amount = float(money.iloc[-1])
    if amount is None and "Amount" in hist.columns:
        amount_values = hist["Amount"].dropna()
        if not amount_values.empty:
            amount = float(amount_values.iloc[-1])
    if amount is None and volume is not None:
        amount = volume * float(prices.iloc[-1])

    return {
        "code": code_upper,
        "name": universe[code_upper],
        "price": float(prices.iloc[-1]),
        "change": float(prices.iloc[-1] - prices.iloc[-2]),
        "change_pct": float((prices.iloc[-1] - prices.iloc[-2]) / prices.iloc[-2] * 100),
        "high": float(prices.max()),
        "low": float(prices.min()),
        "volume": volume,
        "amount": round(amount / 100_000_000, 2) if amount is not None else None,
        "signal": signal,
    }
