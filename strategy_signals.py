"""策略信号汇总模块

整合多个策略的交易信号，提供统一的信号格式和汇总视图。
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Literal
from enum import Enum


class SignalType(Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class StrategyType(Enum):
    """策略类型"""
    FACTOR = "factor"           # 因子策略
    THEME = "theme"             # 主题轮动
    ETF = "etf"                 # ETF轮动
    MEAN_REVERSION = "mean_reversion"  # 均值回归
    MOMENTUM = "momentum"       # 趋势跟踪
    PAIR_TRADING = "pair_trading"      # 配对交易


@dataclass
class StrategySignal:
    """单一策略信号"""
    strategy: StrategyType
    code: str
    name: str
    signal: SignalType
    confidence: float          # 0-1，信号置信度
    score: float               # 策略评分
    price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ConsolidatedSignal:
    """汇总信号"""
    code: str
    name: str
    buy_signals: List[StrategySignal] = field(default_factory=list)
    sell_signals: List[StrategySignal] = field(default_factory=list)
    hold_signals: List[StrategySignal] = field(default_factory=list)
    net_confidence: float = 0.0     # 净置信度
    consensus: SignalType = SignalType.HOLD
    current_price: Optional[float] = None


class SignalConsolidator:
    """信号汇总器"""

    def __init__(self):
        self.signals: List[StrategySignal] = []
        self.consolidated: Dict[str, ConsolidatedSignal] = {}

    def add_signal(self, signal: StrategySignal):
        """添加单个信号"""
        self.signals.append(signal)

    def add_signals(self, signals: List[StrategySignal]):
        """批量添加信号"""
        self.signals.extend(signals)

    def consolidate(self) -> Dict[str, ConsolidatedSignal]:
        """汇总所有信号"""
        # 按代码分组
        grouped: Dict[str, List[StrategySignal]] = {}
        for sig in self.signals:
            code = sig.code
            if code not in grouped:
                grouped[code] = []
            grouped[code].append(sig)

        # 计算汇总信号
        self.consolidated = {}
        for code, sigs in grouped.items():
            buy_sigs = [s for s in sigs if s.signal == SignalType.BUY]
            sell_sigs = [s for s in sigs if s.signal == SignalType.SELL]
            hold_sigs = [s for s in sigs if s.signal == SignalType.HOLD]

            # 计算净置信度
            buy_conf = sum(s.confidence for s in buy_sigs)
            sell_conf = sum(s.confidence for s in sell_sigs)
            net_conf = buy_conf - sell_conf

            # 确定共识信号
            if net_conf > 0.5:
                consensus = SignalType.BUY
            elif net_conf < -0.5:
                consensus = SignalType.SELL
            else:
                consensus = SignalType.HOLD

            # 获取股票名称和当前价格
            name = sigs[0].name if sigs else ""
            price = sigs[0].price if sigs else None

            self.consolidated[code] = ConsolidatedSignal(
                code=code,
                name=name,
                buy_signals=buy_sigs,
                sell_signals=sell_sigs,
                hold_signals=hold_sigs,
                net_confidence=net_conf,
                consensus=consensus,
                current_price=price
            )

        return self.consolidated

    def get_top_picks(self, n: int = 10) -> List[ConsolidatedSignal]:
        """获取最佳买入推荐"""
        self.consolidate()
        buy_signals = [
            s for s in self.consolidated.values()
            if s.consensus == SignalType.BUY
        ]
        buy_signals.sort(key=lambda x: x.net_confidence, reverse=True)
        return buy_signals[:n]

    def get_top_sells(self, n: int = 10) -> List[ConsolidatedSignal]:
        """获取最佳卖出推荐"""
        self.consolidate()
        sell_signals = [
            s for s in self.consolidated.values()
            if s.consensus == SignalType.SELL
        ]
        sell_signals.sort(key=lambda x: x.net_confidence)
        return sell_signals[:n]

    def detect_conflicts(self) -> List[Dict]:
        """检测冲突信号（同时有买入和卖出建议）"""
        self.consolidate()
        conflicts = []

        for code, sig in self.consolidated.items():
            if sig.buy_signals and sig.sell_signals:
                conflicts.append({
                    'code': code,
                    'name': sig.name,
                    'buy_strategies': [s.strategy.value for s in sig.buy_signals],
                    'sell_strategies': [s.strategy.value for s in sig.sell_signals],
                    'net_confidence': sig.net_confidence,
                })

        return conflicts

    def clear(self):
        """清空所有信号"""
        self.signals = []
        self.consolidated = {}


def create_factor_signal(code: str, name: str, score: float,
                        price: float = None) -> StrategySignal:
    """创建因子策略信号

    Args:
        code: 股票代码
        name: 股票名称
        score: 因子得分（通常在-1到1之间）
        price: 当前价格

    Returns:
        策略信号
    """
    # 将因子得分转换为信号和置信度
    abs_score = abs(score)
    if score > 0.1:
        signal = SignalType.BUY
        confidence = min(abs_score, 1.0)
    elif score < -0.1:
        signal = SignalType.SELL
        confidence = min(abs_score, 1.0)
    else:
        signal = SignalType.HOLD
        confidence = 0.0

    return StrategySignal(
        strategy=StrategyType.FACTOR,
        code=code,
        name=name,
        signal=signal,
        confidence=confidence,
        score=score,
        price=price,
        reason=f"因子得分: {score:.4f}"
    )


def create_mean_reversion_signal(code: str, name: str, rsi: float,
                                 bb_position: float, price: float = None) -> StrategySignal:
    """创建均值回归信号

    Args:
        code: 股票代码
        name: 股票名称
        rsi: RSI值（0-100）
        bb_position: 布林带位置（0-1，0=下轨，1=上轨）
        price: 当前价格

    Returns:
        策略信号
    """
    # 综合RSI和布林带位置
    rsi_signal = 0
    if rsi < 30:
        rsi_signal = 1  # 超卖，买入
    elif rsi > 70:
        rsi_signal = -1  # 超买，卖出

    bb_signal = 0
    if bb_position < 0.2:
        bb_signal = 1  # 接近下轨，买入
    elif bb_position > 0.8:
        bb_signal = -1  # 接近上轨，卖出

    combined = rsi_signal + bb_signal

    if combined >= 1:
        signal = SignalType.BUY
        confidence = min(abs(combined) / 2, 1.0)
    elif combined <= -1:
        signal = SignalType.SELL
        confidence = min(abs(combined) / 2, 1.0)
    else:
        signal = SignalType.HOLD
        confidence = 0.0

    return StrategySignal(
        strategy=StrategyType.MEAN_REVERSION,
        code=code,
        name=name,
        signal=signal,
        confidence=confidence,
        score=combined,
        price=price,
        reason=f"RSI: {rsi:.1f}, 布林带位置: {bb_position:.2f}"
    )


def create_momentum_signal(code: str, name: str, ma200_above: bool,
                          ma_trend: str, price: float = None) -> StrategySignal:
    """创建趋势跟踪信号

    Args:
        code: 股票代码
        name: 股票名称
        ma200_above: 是否在200日均线上方
        ma_trend: MA趋势 ('bullish', 'bearish', 'neutral')
        price: 当前价格

    Returns:
        策略信号
    """
    score = 0
    if ma200_above:
        score += 1

    if ma_trend == 'bullish':
        score += 1
    elif ma_trend == 'bearish':
        score -= 1

    if score >= 1:
        signal = SignalType.BUY
        confidence = min(score / 2, 1.0)
    elif score <= -1:
        signal = SignalType.SELL
        confidence = min(abs(score) / 2, 1.0)
    else:
        signal = SignalType.HOLD
        confidence = 0.0

    return StrategySignal(
        strategy=StrategyType.MOMENTUM,
        code=code,
        name=name,
        signal=signal,
        confidence=confidence,
        score=score,
        price=price,
        reason=f"MA200上方: {ma200_above}, 趋势: {ma_trend}"
    )


def create_etf_signal(code: str, name: str, composite_score: float,
                     pred_return: float, price: float = None) -> StrategySignal:
    """创建ETF轮动信号

    Args:
        code: ETF代码
        name: ETF名称
        composite_score: 综合评分（0-1）
        pred_return: 预测收益(%)
        price: 当前价格

    Returns:
        策略信号
    """
    if composite_score > 0.6:
        signal = SignalType.BUY
        confidence = composite_score
    elif composite_score < 0.35:
        signal = SignalType.SELL
        confidence = 1 - composite_score
    else:
        signal = SignalType.HOLD
        confidence = 0.0

    return StrategySignal(
        strategy=StrategyType.ETF,
        code=code,
        name=name,
        signal=signal,
        confidence=confidence,
        score=composite_score,
        price=price,
        target_price=pred_return,
        reason=f"综合评分: {composite_score:.3f}, 预测收益: {pred_return:.2f}%"
    )


def format_signals_for_display(consolidated: List[ConsolidatedSignal]) -> pd.DataFrame:
    """格式化信号用于显示

    Args:
        consolidated: 汇总信号列表

    Returns:
        格式化的DataFrame
    """
    data = []
    for sig in consolidated:
        buy_strats = ", ".join([s.strategy.value for s in sig.buy_signals])
        sell_strats = ", ".join([s.strategy.value for s in sig.sell_signals])

        data.append({
            '代码': sig.code,
            '名称': sig.name,
            '共识信号': sig.consensus.value,
            '净置信度': f"{sig.net_confidence:+.2f}",
            '买入策略': buy_strats if buy_strats else '-',
            '卖出策略': sell_strats if sell_strats else '-',
            '当前价格': f"{sig.current_price:.2f}" if sig.current_price else '-',
        })

    return pd.DataFrame(data)
