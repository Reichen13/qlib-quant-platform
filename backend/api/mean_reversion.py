"""
均值回归 API
超买超卖扫描 - RSI + 布林带双重指标
"""

from pathlib import Path
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from utils.code_normalization import normalize_stock_code

router = APIRouter()

# 导入核心模块
import sys


def get_stock_name(code: str) -> str:
    """获取股票名称"""
    try:
        # 尝试从 stock_names 导入
        from stock_names import get_stock_name as get_name
        return get_name(code)
    except:
        # 如果失败，使用代码作为名称
        return code


def _safe_json_float(value, digits: int | None = None) -> float | None:
    """将数值转为 JSON 安全的有限 float；nan/inf 返回 None。"""
    try:
        if value is None:
            return None
        f = float(value)
        if not np.isfinite(f):
            return None
        if digits is not None:
            return round(f, digits)
        return f
    except (TypeError, ValueError):
        return None


def calc_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """计算 RSI 指标（loss=0 时安全处理，避免 nan/inf）"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # loss=0 且 gain>0 → RSI=100；两者都为 0 → 中性 50
    rsi = pd.Series(np.where(
        loss == 0,
        np.where(gain == 0, 50.0, 100.0),
        100.0 - (100.0 / (1.0 + gain / loss)),
    ), index=prices.index)
    return rsi.replace([np.inf, -np.inf], np.nan)


def calc_bollinger_bands(prices: pd.Series, period: int = 20, std_dev: int = 2) -> Dict:
    """计算布林带"""
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)

    # 计算价格在布林带中的位置 (0-1)；带宽为 0 时取中位
    band_width = (upper - lower).replace(0, np.nan)
    bb_position = (prices - lower) / band_width
    bb_position = bb_position.replace([np.inf, -np.inf], np.nan).fillna(0.5)

    return {
        "upper": upper,
        "middle": sma,
        "lower": lower,
        "position": bb_position
    }


def _is_a_share_feature_dir(name: str) -> bool:
    code = name.lower()
    return (
        code.startswith("sh6")
        or code.startswith("sz0")
        or code.startswith("sz3")
        or code.startswith("bj4")
        or code.startswith("bj8")
        or code.startswith("bj920")
    )


def _get_scan_universe() -> list[str]:
    data_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data"
    feature_dir = data_dir / "features"
    if feature_dir.exists():
        codes = []
        for stock_dir in feature_dir.iterdir():
            if stock_dir.is_dir() and _is_a_share_feature_dir(stock_dir.name):
                try:
                    codes.append(normalize_stock_code(stock_dir.name, target="qlib"))
                except ValueError:
                    continue
        if codes:
            return list(dict.fromkeys(codes))

    # 回退：核心研究池 core650（兼容旧文件名 csi300.txt）
    from core.universe import instruments_path, ensure_core650_instruments
    ensure_core650_instruments(data_dir)
    pool_file = instruments_path(data_dir, "core650")
    if pool_file.exists():
        with open(pool_file, encoding="utf-8") as f:
            return [
                normalize_stock_code(line.strip().split("\t")[0], target="qlib")
                for line in f
                if line.strip()
            ]
    return []


def scan_mean_reversion_signals(
    stock_codes: List[str],
    rsi_threshold: int = 70,
    bollinger_period: int = 20
) -> List[Dict]:
    """
    扫描均值回归信号

    Args:
        stock_codes: 股票代码列表
        rsi_threshold: RSI 阈值（默认 70，超买/超卖分别为 70/30）
        bollinger_period: 布林带周期

    Returns:
        信号列表
    """
    try:
        import qlib
        from qlib.data import D

        signals = []
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

        scan_codes = stock_codes or _get_scan_universe()

        for code in scan_codes[:200]:  # 控制单次扫描耗时
            try:
                # 获取价格数据
                df = D.features(
                    [code],
                    ["$close"],
                    start_time=start_date,
                    end_time=end_date
                )

                if df.empty:
                    continue

                prices = df.xs(code, level=0)["$close"]

                if len(prices) < 30:
                    continue

                # 计算 RSI
                rsi = calc_rsi(prices)
                current_rsi = _safe_json_float(rsi.iloc[-1], digits=1)

                # 计算布林带
                bb = calc_bollinger_bands(prices, bollinger_period)
                bb_pos = _safe_json_float(bb["position"].iloc[-1], digits=2)

                # 指标不可用则跳过，避免 JSON nan 导致 500
                if current_rsi is None or bb_pos is None:
                    continue

                # 确定信号
                signal = "关注"
                strength = "弱"
                score = 50

                # RSI 超买/超卖判断
                is_overbought_rsi = current_rsi > rsi_threshold
                is_oversold_rsi = current_rsi < (100 - rsi_threshold)

                # 布林带超买/超卖判断
                is_overbought_bb = bb_pos > 0.8
                is_oversold_bb = bb_pos < 0.2

                # 综合判断
                if is_overbought_rsi and is_overbought_bb:
                    signal = "超买"
                    strength = "强"
                    score = 85
                elif is_oversold_rsi and is_oversold_bb:
                    signal = "超卖"
                    strength = "强"
                    score = 80
                elif is_overbought_rsi or is_overbought_bb:
                    signal = "超买"
                    strength = "中"
                    score = 70
                elif is_oversold_rsi or is_oversold_bb:
                    signal = "超卖"
                    strength = "中"
                    score = 72
                else:
                    # 接近阈值
                    if current_rsi > 60 or bb_pos > 0.7:
                        score = 65
                    elif current_rsi < 40 or bb_pos < 0.3:
                        score = 60

                signals.append({
                    "code": code,
                    "name": get_stock_name(code),
                    "rsi": current_rsi,
                    "bollingerPosition": bb_pos,
                    "signal": signal,
                    "score": score,
                    "strength": strength
                })

            except Exception as e:
                logger.debug(f"处理股票 {code} 失败: {e}")
                continue

        return signals

    except Exception as e:
        logger.error(f"扫描均值回归信号失败: {e}")
        return []


@router.get("/scan")
async def scan_signals(
    rsi_threshold: int = Query(70, description="RSI 阈值", ge=50, le=90),
    bollinger_period: int = Query(20, description="布林带周期", ge=10, le=30)
):
    """
    扫描超买超卖信号

    返回基于 RSI 和布林带的均值回归信号
    """
    try:
        signals = scan_mean_reversion_signals(
            stock_codes=[],
            rsi_threshold=rsi_threshold,
            bollinger_period=bollinger_period
        )

        return {
            "signals": signals,
            "total": len(signals),
            "overbought": len([s for s in signals if s["signal"] == "超买"]),
            "oversold": len([s for s in signals if s["signal"] == "超卖"]),
            "watch": len([s for s in signals if s["signal"] == "关注"]),
            "date": datetime.now().strftime("%Y-%m-%d")
        }

    except Exception as e:
        logger.error(f"扫描信号失败: {e}")
        return {
            "signals": [],
            "total": 0,
            "overbought": 0,
            "oversold": 0,
            "watch": 0,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "data_status": "unavailable",
            "warning": "Qlib 数据源暂时不可用，未返回示例或模拟信号。",
        }

@router.get("/stock/{code}")
async def get_stock_signal(
    code: str,
    rsi_threshold: int = Query(70, description="RSI 阈值"),
    bollinger_period: int = Query(20, description="布林带周期")
):
    """
    获取单只股票的均值回归信号
    """
    try:
        import qlib
        from qlib.data import D

        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

        df = D.features(
            [code],
            ["$close"],
            start_time=start_date,
            end_time=end_date
        )

        if df.empty:
            raise HTTPException(status_code=404, detail="无法获取股票数据")

        prices = df.xs(code, level=0)["$close"]

        # 计算指标
        rsi = calc_rsi(prices)
        bb = calc_bollinger_bands(prices, bollinger_period)

        current_rsi = _safe_json_float(rsi.iloc[-1], digits=1)
        bb_pos = _safe_json_float(bb["position"].iloc[-1], digits=2)
        price = _safe_json_float(prices.iloc[-1], digits=4)
        if current_rsi is None or bb_pos is None or price is None:
            raise HTTPException(status_code=404, detail="指标数据无效（价格序列不足或含缺失）")

        # 确定信号
        is_overbought_rsi = current_rsi > rsi_threshold
        is_oversold_rsi = current_rsi < (100 - rsi_threshold)
        is_overbought_bb = bb_pos > 0.8
        is_oversold_bb = bb_pos < 0.2

        if is_overbought_rsi and is_overbought_bb:
            signal = "超买"
            strength = "强"
        elif is_oversold_rsi and is_oversold_bb:
            signal = "超卖"
            strength = "强"
        elif is_overbought_rsi or is_overbought_bb:
            signal = "超买"
            strength = "中"
        elif is_oversold_rsi or is_oversold_bb:
            signal = "超卖"
            strength = "中"
        else:
            signal = "关注"
            strength = "弱"

        return {
            "code": code,
            "name": get_stock_name(code),
            "rsi": current_rsi,
            "bollingerPosition": bb_pos,
            "signal": signal,
            "strength": strength,
            "price": price,
            "rsiThreshold": rsi_threshold,
            "bollingerPeriod": bollinger_period
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取股票信号失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_summary():
    """
    获取均值回归信号汇总
    """
    try:
        # 获取当前扫描结果
        result = await scan_signals(rsi_threshold=70, bollinger_period=20)

        # 计算统计信息
        signals = result.get("signals", [])

        avg_rsi = 0.0
        if signals:
            rsi_vals = [s["rsi"] for s in signals if s.get("rsi") is not None]
            if rsi_vals:
                avg_rsi = sum(rsi_vals) / len(rsi_vals)

        return {
            "overbought": result.get("overbought", 0),
            "oversold": result.get("oversold", 0),
            "watch": result.get("watch", 0),
            "total": result.get("total", 0),
            "avgRsi": _safe_json_float(avg_rsi, digits=1) or 0.0,
            "date": datetime.now().strftime("%Y-%m-%d")
        }

    except Exception as e:
        logger.error(f"获取汇总失败: {e}")
        return {
            "overbought": 0,
            "oversold": 0,
            "watch": 0,
            "total": 0,
            "avgRsi": 50.0,
            "date": datetime.now().strftime("%Y-%m-%d")
        }
