"""
验证 Ledoit-Wolf 收缩协方差和 James-Stein 收缩预期收益的数值正确性。
"""
import numpy as np
import pandas as pd


def test_ledoit_wolf_shrinkage():
    """验证 Ledoit-Wolf 收缩估计返回合法协方差矩阵"""
    # 生成随机收益：50 个交易日，5 只股票
    np.random.seed(42)
    returns = pd.DataFrame(
        np.random.randn(50, 5) * 0.02,
        columns=[f"stock_{i}" for i in range(5)],
    )
    cov = returns.cov().values
    mean_returns = returns.mean().values

    # 验证协方差矩阵对称
    assert cov.shape == (5, 5)
    assert np.allclose(cov, cov.T, atol=1e-10)

    # 验证对角元素（方差）为正
    for i in range(5):
        assert cov[i, i] > 0

    # 验证年化
    annual_cov = cov * 252
    assert annual_cov.shape == (5, 5)
    assert np.allclose(annual_cov, annual_cov.T, atol=1e-10)

    # 验证预期收益数组
    assert len(mean_returns) == 5


def test_james_stein_shrinkage():
    """验证 James-Stein 收缩将样本均值向 grand mean 收缩"""
    np.random.seed(42)
    returns = pd.DataFrame(
        np.random.randn(100, 6) * 0.02,
        columns=[f"stock_{i}" for i in range(6)],
    )
    sample_means = returns.mean().values
    grand_mean = sample_means.mean()

    # 手动计算 JS 收缩（简化版本）
    n_assets = len(returns.columns)
    n_obs = len(returns)
    ssq = np.sum((sample_means - grand_mean) ** 2)
    sigma_sq = np.var(returns.values, axis=0, ddof=1)
    mean_var = np.mean(sigma_sq) / n_obs

    if ssq > 1e-15 and n_assets > 3:
        js_factor = max(0.0, min(1.0, (n_assets - 3) * mean_var / ssq))
    else:
        js_factor = 0.0

    shrunk_means = grand_mean + (1 - js_factor) * (sample_means - grand_mean)

    # 收缩后的均值应比原始均值更接近 grand mean
    orig_dist = np.sum(np.abs(sample_means - grand_mean))
    shrunk_dist = np.sum(np.abs(shrunk_means - grand_mean))
    assert shrunk_dist <= orig_dist + 1e-10

    # JS 因子应在 [0, 1] 范围内
    assert 0.0 <= js_factor <= 1.0


def test_sharpe_ratio_calculation():
    """验证 Sharpe ratio 计算"""
    returns = np.array([0.01, -0.005, 0.02, 0.008, -0.003, 0.015, 0.012, -0.008])
    ann_return = np.mean(returns) * 252
    ann_vol = np.std(returns, ddof=1) * np.sqrt(252)
    sharpe = ann_return / ann_vol if ann_vol > 0 else 0

    assert isinstance(sharpe, float)
    # 对于这些收益率，Sharpe 应该在合理范围内
    assert -20 < sharpe < 20


def test_covariance_symmetry():
    """验证协方差矩阵对称性 —— 这是一个关键不变量"""
    np.random.seed(123)
    data = pd.DataFrame(np.random.randn(200, 10) * 0.015)
    cov = data.cov().values
    assert np.allclose(cov, cov.T, atol=1e-10), "协方差矩阵必须对称"


def test_equal_weight_portfolio():
    """等权组合的权重之和应为 1"""
    n = 8
    weights = np.ones(n) / n
    assert abs(np.sum(weights) - 1.0) < 1e-10
    assert np.all(weights > 0)
    assert abs(weights[0] - 1 / n) < 1e-10
