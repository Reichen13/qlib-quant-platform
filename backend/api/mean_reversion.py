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


def calc_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """计算 RSI 指标"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_bollinger_bands(prices: pd.Series, period: int = 20, std_dev: int = 2) -> Dict:
    """计算布林带"""
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)

    # 计算价格在布林带中的位置 (0-1)
    bb_position = (prices - lower) / (upper - lower)
    bb_position = bb_position.fillna(0.5)

    return {
        "upper": upper,
        "middle": sma,
        "lower": lower,
        "position": bb_position
    }


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

        # 获取 CSI300 成分股
        csi300_file = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "instruments" / "csi300.txt"

        if csi300_file.exists():
            with open(csi300_file) as f:
                stock_codes = [line.strip().split('\t')[0] for line in f if line.strip()][:100]
        else:
            # 默认股票列表
            stock_codes = [
                "SH600519", "SZ000858", "SH600036", "SZ000001",
                "SH601318", "SZ000002", "SZ000333", "SZ002594",
                "SH600276", "SZ300750", "SH600887", "SH600000",
            ]

        for code in stock_codes[:50]:  # 限制扫描数量
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
                current_rsi = rsi.iloc[-1]

                # 计算布林带
                bb = calc_bollinger_bands(prices, bollinger_period)
                bb_pos = bb["position"].iloc[-1]

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
                    "rsi": round(float(current_rsi), 1),
                    "bollingerPosition": round(float(bb_pos), 2),
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

        current_rsi = float(rsi.iloc[-1])
        bb_pos = float(bb["position"].iloc[-1])

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
            "rsi": round(current_rsi, 1),
            "bollingerPosition": round(bb_pos, 2),
            "signal": signal,
            "strength": strength,
            "price": float(prices.iloc[-1]),
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

        avg_rsi = 0
        if signals:
            avg_rsi = sum(s["rsi"] for s in signals) / len(signals)

        return {
            "overbought": result.get("overbought", 0),
            "oversold": result.get("oversold", 0),
            "watch": result.get("watch", 0),
            "total": result.get("total", 0),
            "avgRsi": round(avg_rsi, 1),
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
