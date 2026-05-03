"""
散户订单流因子模块

基于论文《量化交易的市场价值效应——信息优势的作用》
实现散户订单流、信息透明度等新因子
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple


def calc_retail_outflow(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    计算散户订单流出指标

    原理:
    - 散户交易往往导致日内高波动与成交额背离
    - 散户集中流出时，日内振幅大但成交额相对较小

    Args:
        df: 包含 high, low, close, volume 列的 DataFrame
        window: 计算窗口

    Returns:
        散户流出指标 (正值表示流出，负值表示流入)
    """
    if df.empty or len(df) < window:
        return pd.Series()

    # 日内振幅
    df = df.copy()
    df['intraday_range'] = (df['high'] - df['low']) / df['close']

    # 成交额的变动率
    df['volume_change'] = df['volume'].pct_change()

    # 振幅与成交额的背离 (散户特征)
    df['divergence'] = df['intraday_range'] - df['volume_change'].rolling(window).std()

    # 滚动均值
    retail_outflow = df['divergence'].rolling(window).mean()

    return retail_outflow


def calc_volatility_regime(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    计算波动率制度 (市场状态识别)

    用于识别极端行情，在尾部风险高时降低仓位
    """
    if df.empty or len(df) < window:
        return pd.Series()

    returns = df['close'].pct_change()
    volatility = returns.rolling(window).std()

    # 归一化波动率
    vol_mean = volatility.rolling(window * 2).mean()
    vol_regime = (volatility - vol_mean) / vol_mean

    return vol_regime


def calc_tail_risk_metric(df: pd.DataFrame, window: int = 60) -> Dict[str, float]:
    """
    计算尾部风险指标

    返回:
        - tail_risk: 尾部风险 (负收益的5%分位数)
        - skewness: 收益偏度
        - max_drawdown: 最大回撤
        - risk_level: 风险等级 (LOW/MEDIUM/HIGH)
    """
    if df.empty or len(df) < window:
        return {"tail_risk": 0, "skewness": 0, "max_drawdown": 0, "risk_level": "UNKNOWN"}

    returns = df['close'].pct_change().dropna()

    # 尾部风险 (最差的5%日子)
    tail_risk = returns.quantile(0.05)

    # 偏度
    skewness = returns.skew()

    # 最大回撤
    cum_returns = (1 + returns).cumprod()
    running_max = cum_returns.cummax()
    drawdown = (cum_returns - running_max) / running_max
    max_drawdown = drawdown.min()

    # 风险等级
    if tail_risk < -0.05 or max_drawdown < -0.20:
        risk_level = "HIGH"
    elif tail_risk < -0.03 or max_drawdown < -0.15:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "tail_risk": tail_risk,
        "skewness": skewness,
        "max_drawdown": max_drawdown,
        "risk_level": risk_level
    }


def calc_momentum_signal(df: pd.DataFrame, short: int = 5, long: int = 20) -> float:
    """
    计算动量信号

    正值表示上涨动量，负值表示下跌动量
    """
    if df.empty or len(df) < long:
        return 0.0

    recent_return = df['close'].pct_change(short).iloc[-1]
    long_return = df['close'].pct_change(long).iloc[-1]

    # 短期动量与长期趋势的结合
    signal = recent_return * 0.7 + long_return * 0.3

    return signal


def calc_retail_sentiment(df: pd.DataFrame, window: int = 20) -> Dict[str, float]:
    """
    计算散户情绪指标

    返回:
        - sentiment_score: 情绪得分 (0-100)
        - sentiment_level: 情绪等级 (FEAR/NEUTRAL/GREED)
    """
    if df.empty or len(df) < window:
        return {"sentiment_score": 50, "sentiment_level": "NEUTRAL"}

    # RSI
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    current_rsi = rsi.iloc[-1]

    # 成交量活跃度
    volume_ma = df['volume'].rolling(window).mean()
    volume_ratio = df['volume'].iloc[-1] / volume_ma.iloc[-1]

    # 综合情绪得分
    sentiment_score = current_rsi * 0.6 + min(volume_ratio * 50, 40)

    if current_rsi < 30:
        sentiment_level = "FEAR"  # 恐慌，可能是买入机会
    elif current_rsi > 70:
        sentiment_level = "GREED"  # 贪婪，注意风险
    else:
        sentiment_level = "NEUTRAL"

    return {
        "sentiment_score": sentiment_score,
        "sentiment_level": sentiment_level,
        "rsi": current_rsi,
        "volume_ratio": volume_ratio
    }


def calc_position_size(capital: float, risk_level: str, max_position_pct: float = 0.02) -> float:
    """
    根据风险等级计算建议仓位

    Args:
        capital: 总资金
        risk_level: 风险等级 (LOW/MEDIUM/HIGH)
        max_position_pct: 单只股票最大仓位比例 (默认2%)

    Returns:
        建议单只股票仓位金额
    """
    risk_multiplier = {
        "LOW": 1.0,      # 低风险，正常仓位
        "MEDIUM": 0.7,   # 中等风险，降低仓位
        "HIGH": 0.4,     # 高风险，大幅降低仓位
        "UNKNOWN": 0.5   # 未知，保守
    }

    multiplier = risk_multiplier.get(risk_level, 0.5)
    return capital * max_position_pct * multiplier


def calc_portfolio_stop_loss(risk_levels: Dict[str, str],
                            base_stop_loss: float = -0.08) -> float:
    """
    根据组合整体风险计算动态止损位

    Args:
        risk_levels: 各股票的风险等级字典 {code: risk_level}
        base_stop_loss: 基础止损位 (默认-8%)

    Returns:
        动态止损位
    """
    if not risk_levels:
        return base_stop_loss

    # 统计各风险等级数量
    high_count = sum(1 for r in risk_levels.values() if r == "HIGH")
    medium_count = sum(1 for r in risk_levels.values() if r == "MEDIUM")
    total = len(risk_levels)

    if total == 0:
        return base_stop_loss

    # 高风险股票占比
    high_ratio = high_count / total

    # 动态调整止损
    if high_ratio > 0.5:
        return -0.05  # 高风险占比高，收紧止损到-5%
    elif high_ratio > 0.3:
        return -0.06  # 适度收紧
    else:
        return base_stop_loss


class RetailFactorCollector:
    """散户因子收集器 - 用于批量计算多只股票的因子"""

    def __init__(self):
        self.factors = {}

    def collect_stock_factors(self, code: str, df: pd.DataFrame) -> Dict[str, float]:
        """
        收集单只股票的所有因子

        Returns:
            因子字典 {
                "retail_outflow": 散户流出指标,
                "momentum": 动量信号,
                "sentiment_score": 情绪得分,
                "tail_risk": 尾部风险,
                "risk_level": 风险等级,
                "volatility_regime": 波动率制度,
            }
        """
        if df.empty or len(df) < 20:
            return {"code": code, "error": "数据不足"}

        retail_outflow = calc_retail_outflow(df)
        momentum = calc_momentum_signal(df)
        sentiment = calc_retail_sentiment(df)
        tail_risk = calc_tail_risk_metric(df)
        vol_regime = calc_volatility_regime(df)

        return {
            "code": code,
            "retail_outflow": retail_outflow.iloc[-1] if not retail_outflow.empty else 0,
            "momentum": momentum,
            "sentiment_score": sentiment["sentiment_score"],
            "sentiment_level": sentiment["sentiment_level"],
            "tail_risk": tail_risk["tail_risk"],
            "risk_level": tail_risk["risk_level"],
            "max_drawdown": tail_risk["max_drawdown"],
            "volatility_regime": vol_regime.iloc[-1] if not vol_regime.empty else 0,
            "rsi": sentiment.get("rsi", 50),
        }

    def rank_by_retail_opportunity(self, factors_list: List[Dict]) -> pd.DataFrame:
        """
        根据散户流出机会排序

        逻辑:
        - 散户流出高 (retail_outflow > 0)
        - 动量差但可能超卖 (momentum < 0 但不极端)
        - 情绪恐慌 (sentiment_level = FEAR)

        Returns:
            排序后的 DataFrame
        """
        df = pd.DataFrame(factors_list)

        if df.empty or "error" in df.columns:
            return pd.DataFrame()

        # 计算机会得分
        df['opportunity_score'] = 0

        # 散户流出得分 (越高越好)
        df['opportunity_score'] += np.clip(df['retail_outflow'] * 10, 0, 30)

        # 恐慌情绪加分
        df.loc[df['sentiment_level'] == 'FEAR', 'opportunity_score'] += 20
        df.loc[df['sentiment_level'] == 'NEUTRAL', 'opportunity_score'] += 10

        # 低风险加分
        df.loc[df['risk_level'] == 'LOW', 'opportunity_score'] += 15
        df.loc[df['risk_level'] == 'MEDIUM', 'opportunity_score'] += 5

        # 动量调整 (适度负动量表示超卖)
        df['opportunity_score'] -= np.clip(df['momentum'] * 5, -10, 10)

        # 排序
        df = df.sort_values('opportunity_score', ascending=False)

        return df


def calc_transaction_cost_adjustment(returns: pd.Series,
                                     buy_cost: float = 0.0005,
                                     sell_cost: float = 0.0015,
                                     turnover: float = 0.5) -> float:
    """
    计算交易成本调整后的收益

    Args:
        returns: 原始收益序列
        buy_cost: 买入成本 (默认0.05%)
        sell_cost: 卖出成本 (默认0.15%)
        turnover: 换手率 (默认50%)

    Returns:
        调整后的年化收益
    """
    ann_return = returns.mean() * 252

    # 交易成本损失
    cost_impact = (buy_cost + sell_cost) * turnover

    return ann_return - cost_impact


def estimate_realistic_return(backtest_return: float,
                             cost_adjustment: float = 0.005,
                             slippage: float = 0.002) -> float:
    """
    估算真实可行的收益

    基于论文分析，回测收益通常需要打折
    """
    # 回测收益打5-7折
    discount_factor = 0.6

    # 减去成本
    realistic = backtest_return * discount_factor - cost_adjustment - slippage

    return realistic
