"""配对交易模块

实现统计套利策略：
1. 选择同行业股票对
2. 检验协整关系
3. 计算 Z-score
4. 生成交易信号
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from datetime import timedelta


@dataclass
class PairSignal:
    """配对交易信号"""
    pair: str
    stock1: str
    stock2: str
    zscore: float
    spread: float
    signal: str  # 'long_spread', 'short_spread', 'close', 'hold'
    confidence: float
    correlation: float


def calc_correlation(df1: pd.DataFrame, df2: pd.DataFrame, period: int = 60) -> float:
    """计算两只股票的相关性

    Args:
        df1: 股票1的OHLCV数据
        df2: 股票2的OHLCV数据
        period: 计算周期

    Returns:
        相关系数
    """
    if df1.empty or df2.empty:
        return 0.0

    # 对齐日期
    common_index = df1.index.intersection(df2.index)
    if len(common_index) < period:
        return 0.0

    returns1 = df1.loc[common_index, 'close'].pct_change().dropna()
    returns2 = df2.loc[common_index, 'close'].pct_change().dropna()

    if len(returns1) < period:
        return 0.0

    # 使用最近period天的数据
    corr = returns1.tail(period).corr(returns2.tail(period))
    return corr if not np.isnan(corr) else 0.0


def check_cointegration(df1: pd.DataFrame, df2: pd.DataFrame,
                        threshold: float = 0.05) -> Tuple[bool, float]:
    """检验两只股票的协整关系

    使用简化的Engle-Granger两步法：
    1. 对价格序列进行线性回归：y = alpha + beta * x
    2. 检验残差是否平稳（残差的标准差相对于价格的比例）

    Args:
        df1: 股票1的OHLCV数据
        df2: 股票2的OHLCV数据
        threshold: 协整检验阈值

    Returns:
        (是否协整, 协整统计量)
    """
    if df1.empty or df2.empty:
        return False, 0.0

    # 对齐日期
    common_index = df1.index.intersection(df2.index)
    if len(common_index) < 30:
        return False, 0.0

    price1 = df1.loc[common_index, 'close'].values
    price2 = df2.loc[common_index, 'close'].values

    # 简单的线性回归求beta
    # beta = cov(x,y) / var(x)
    beta = np.cov(price1, price2)[0, 1] / np.var(price2)
    alpha = np.mean(price1) - beta * np.mean(price2)

    # 计算残差
    residuals = price1 - (alpha + beta * price2)

    # 简化的平稳性检验：计算残差的均值回复速度
    # 如果残差有均值回复特性，则认为是协整的
    spread_std = np.std(residuals)
    price_std = np.std(price1)

    # 协整统计量：残差标准差与价格标准差的比值
    coint_stat = spread_std / price_std if price_std > 0 else 1.0

    # 阈值判断
    is_cointegrated = coint_stat < threshold

    return is_cointegrated, coint_stat


def calc_zscore(spread: pd.Series, window: int = 20) -> pd.Series:
    """计算价差的 Z-score

    Args:
        spread: 价差序列
        window: 移动窗口

    Returns:
        Z-score序列
    """
    mean = spread.rolling(window=window).mean()
    std = spread.rolling(window=window).std()
    zscore = (spread - mean) / std
    return zscore


def calc_spread(df1: pd.DataFrame, df2: pd.DataFrame,
                beta: Optional[float] = None) -> pd.Series:
    """计算两只股票的价差

    Args:
        df1: 股票1的OHLCV数据
        df2: 股票2的OHLCV数据
        beta: 对冲比率，如果为None则自动计算

    Returns:
        价差序列
    """
    # 对齐日期
    common_index = df1.index.intersection(df2.index)

    price1 = df1.loc[common_index, 'close']
    price2 = df2.loc[common_index, 'close']

    if beta is None:
        # 计算对冲比率
        beta = np.cov(price1, price2)[0, 1] / np.var(price2)

    spread = price1 - beta * price2
    spread.index = common_index

    return spread


def generate_pair_signal(df1: pd.DataFrame, df2: pd.DataFrame,
                         entry_threshold: float = 2.0,
                         exit_threshold: float = 0.5,
                         lookback: int = 20) -> PairSignal:
    """生成配对交易信号

    Args:
        df1: 股票1的OHLCV数据
        df2: 股票2的OHLCV数据
        entry_threshold: 入场阈值（Z-score）
        exit_threshold: 出场阈值（Z-score）
        lookback: 回看周期

    Returns:
        配对交易信号
    """
    # 获取股票代码
    code1 = df1.iloc[-1]['code'] if 'code' in df1.columns else 'Stock1'
    code2 = df2.iloc[-1]['code'] if 'code' in df2.columns else 'Stock2'

    # 计算相关性
    correlation = calc_correlation(df1, df2, period=lookback)

    # 计算价差
    spread = calc_spread(df1, df2)
    current_spread = spread.iloc[-1]

    # 计算Z-score
    zscore_series = calc_zscore(spread, window=lookback)
    current_zscore = zscore_series.iloc[-1]

    # 生成信号
    if current_zscore > entry_threshold:
        signal = 'short_spread'  # 价差过高，做空价差（做空stock1，做多stock2）
        confidence = min(abs(current_zscore) / 3, 1.0)
    elif current_zscore < -entry_threshold:
        signal = 'long_spread'   # 价差过低，做多价差（做多stock1，做空stock2）
        confidence = min(abs(current_zscore) / 3, 1.0)
    elif abs(current_zscore) < exit_threshold:
        signal = 'close'         # 价差回归，平仓
        confidence = 1.0
    else:
        signal = 'hold'          # 观望
        confidence = 0.0

    return PairSignal(
        pair=f"{code1}/{code2}",
        stock1=code1,
        stock2=code2,
        zscore=current_zscore,
        spread=current_spread,
        signal=signal,
        confidence=confidence,
        correlation=correlation
    )


def recommend_pairs(stocks_dict: Dict[str, pd.DataFrame],
                   sector: str,
                   min_correlation: float = 0.7,
                   max_pairs: int = 10) -> List[Tuple[str, str, float]]:
    """推荐配对交易组合

    Args:
        stocks_dict: 股票代码到数据的映射
        sector: 行业名称
        min_correlation: 最小相关性阈值
        max_pairs: 最大返回对数

    Returns:
        推荐的配对列表 [(stock1, stock2, correlation), ...]
    """
    codes = list(stocks_dict.keys())
    if len(codes) < 2:
        return []

    recommendations = []

    # 两两组合计算相关性
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            code1, code2 = codes[i], codes[j]
            df1 = stocks_dict[code1]
            df2 = stocks_dict[code2]

            corr = calc_correlation(df1, df2)

            if corr >= min_correlation:
                # 检查协整关系
                is_cointegrated, coint_stat = check_cointegration(df1, df2)
                if is_cointegrated:
                    recommendations.append((code1, code2, corr))

    # 按相关性排序
    recommendations.sort(key=lambda x: x[2], reverse=True)

    return recommendations[:max_pairs]


def get_default_pairs() -> Dict[str, List[Tuple[str, str]]]:
    """获取默认的配对交易组合（基于同行业）

    Returns:
        行业到配对的映射
    """
    return {
        "金融": [
            ("SH600036", "SH600016"),  # 招商银行 vs 民生银行
            ("SH601398", "SH601288"),  # 工商银行 vs 农业银行
            ("SH601318", "SH601166"),  # 中国平安 vs 兴业银行
        ],
        "科技": [
            ("SZ000725", "SZ002415"),  # 京东方A vs 海康威视
            ("SZ300750", "SZ002460"),  # 宁德时代 vs 赣锋锂业
            ("SH688981", "SH688012"),  # 中芯国际 vs 中微公司
        ],
        "医药": [
            ("SH600276", "SH600196"),  # 恒瑞医药 vs 复星医药
            ("SZ000538", "SH600436"),  # 云南白药 vs 片仔癀
            ("SZ300760", "SZ300015"),  # 迈瑞医疗 vs 爱尔眼科
        ],
        "消费": [
            ("SH600519", "SZ000858"),  # 贵州茅台 vs 五粮液
            ("SZ000333", "SH600887"),  # 美的集团 vs 伊利股份
            ("SZ002304", "SZ000895"),  # 洋河股份 vs 双汇发展
        ],
    }
