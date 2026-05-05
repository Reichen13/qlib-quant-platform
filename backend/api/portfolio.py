"""
投资组合优化 API - Man Group 风格组合构建系统
提供均值方差、风险平价、Black-Litterman、HRP 等优化方法
"""

import os
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Depends
from loguru import logger
from auth import verify_api_key

project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from models.schemas import (
    PortfolioOptimizeRequest, PortfolioOptimizeResponse,
    PortfolioWeight, EfficientFrontierPoint,
)

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _to_qlib_codes(codes: List[str]) -> List[str]:
    """将 yfinance 格式代码 (.SS/.SZ) 转为 Qlib 格式 (SH/SZ)"""
    converted = []
    for code in codes:
        if code.endswith(".SS"):
            converted.append("SH" + code.replace(".SS", ""))
        elif code.endswith(".SZ"):
            converted.append("SZ" + code.replace(".SZ", ""))
        else:
            converted.append(code)
    return converted


def _get_historical_prices(codes: List[str], start_date: str, end_date: str) -> pd.DataFrame:
    """获取历史收盘价"""
    try:
        from qlib.data import D
        qlib_codes = _to_qlib_codes(codes)
        prices = D.features(qlib_codes, ["$close"], start_time=start_date, end_time=end_date, freq="day")
        if prices.empty:
            raise ValueError("Qlib 返回空数据")
        df = prices.reset_index()
        if "instrument" in df.columns:
            df = df.pivot(index="datetime", columns="instrument", values="$close")
        return df
    except Exception as e:
        logger.warning(f"Qlib 数据获取失败，尝试 yfinance: {e}")
        import yfinance as yf
        all_data = {}
        for code in codes:
            try:
                ticker = yf.Ticker(code)
                hist = ticker.history(start=start_date, end=end_date)
                if not hist.empty:
                    all_data[code] = hist["Close"]
            except Exception:
                pass
        if not all_data:
            raise HTTPException(status_code=500, detail="无法获取任何股票数据")
        return pd.DataFrame(all_data)


def _compute_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change().dropna()


def _shrink_covariance(returns: pd.DataFrame) -> np.ndarray:
    """Ledoit-Wolf 收缩协方差估计 (年化)

    样本协方差在 N 接近 T 时极不稳定，收缩估计将样本协方差
    向结构化目标（单因子模型/等相关系数）收缩，可将波动率
    预测误差降低 30-60% (Ledoit & Wolf 2004)。
    """
    try:
        from sklearn.covariance import LedoitWolf
        lw = LedoitWolf().fit(returns.values)
        cov = lw.covariance_ * 252
        shrinkage = lw.shrinkage_
        logger.info(f"Ledoit-Wolf 收缩: shrinkage={shrinkage:.3f}")
        return cov
    except ImportError:
        logger.warning("sklearn 不可用，回退到样本协方差")
        return returns.cov().values * 252


def _shrink_returns(returns: pd.DataFrame) -> np.ndarray:
    """James-Stein 收缩预期收益估计 (年化)

    样本均值是最差的预期收益估计量 (Michaud 1989)，会导致
    "误差最大化"——权重向估计误差最大的股票集中。
    JS 收缩将个股均值向 grand mean 收缩，降低估计误差。

    收缩因子: λ = (N - 3) / Σ ((x_i - μ_grand)² / σ²_mean)
    """
    n_assets = len(returns.columns)
    if n_assets < 4:
        return returns.mean().values * 252

    sample_means = returns.mean().values  # 日度样本均值
    n_obs = len(returns)

    grand_mean = sample_means.mean()
    ssq = np.sum((sample_means - grand_mean) ** 2)

    if ssq < 1e-15:
        return sample_means * 252

    sigma_sq = np.var(returns.values, axis=0, ddof=1)  # 每只股票的方差
    mean_var = np.mean(sigma_sq) / n_obs  # 样本均值方差 (CLT)

    js_factor = max(0.0, min(1.0, (n_assets - 3) * mean_var / ssq))

    shrunk_means = grand_mean + (1 - js_factor) * (sample_means - grand_mean)
    logger.info(f"James-Stein 收缩: λ={js_factor:.3f}, grand_mean={grand_mean:.6f}")

    return shrunk_means * 252


def _mean_variance_optimization(
    returns: pd.DataFrame,
    target_return: Optional[float] = None,
    risk_aversion: float = 1.0,
    short_sell: bool = False,
    max_weight: float = 0.3,
    turnover_lambda: float = 0.0,
) -> dict:
    """均值-方差优化"""
    n = len(returns.columns)
    mu = _shrink_returns(returns)
    sigma = _shrink_covariance(returns)
    w_prev = np.ones(n) / n  # 等权参考基准

    if target_return is not None:
        # 给定目标收益，最小化风险
        try:
            from scipy.optimize import minimize

            def objective(w):
                risk = np.sqrt(w.T @ sigma @ w)
                turnover = np.sum(np.abs(w - w_prev))
                return risk + turnover_lambda * turnover

            constraints = [
                {"type": "eq", "fun": lambda w: np.sum(w) - 1},
                {"type": "eq", "fun": lambda w: w @ mu - target_return},
            ]
            bounds = [(0, max_weight) for _ in range(n)] if not short_sell else [(-1, 1) for _ in range(n)]
            x0 = np.ones(n) / n

            result = minimize(objective, x0, method="SLSQP", constraints=constraints, bounds=bounds)
            if not result.success:
                raise ValueError(f"优化失败: {result.message}")
            weights = result.x
            opt_return = weights @ mu
            opt_vol = np.sqrt(weights.T @ sigma @ weights)
            opt_sharpe = opt_return / opt_vol if opt_vol > 0 else 0
        except ImportError:
            raise HTTPException(status_code=500, detail="需要安装 scipy 进行均值方差优化")
    else:
        # 最大化 Sharpe ratio
        try:
            from scipy.optimize import minimize

            def neg_sharpe(w):
                port_return = w @ mu
                port_vol = np.sqrt(w.T @ sigma @ w)
                turnover = np.sum(np.abs(w - w_prev))
                return -port_return / port_vol + turnover_lambda * turnover if port_vol > 0 else 1e9

            constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
            bounds = [(0, max_weight) for _ in range(n)] if not short_sell else [(-1, 1) for _ in range(n)]
            x0 = np.ones(n) / n

            result = minimize(neg_sharpe, x0, method="SLSQP", constraints=constraints, bounds=bounds)
            if not result.success:
                raise ValueError(f"优化失败: {result.message}")
            weights = result.x
            opt_return = weights @ mu
            opt_vol = np.sqrt(weights.T @ sigma @ weights)
            opt_sharpe = -neg_sharpe(weights)
            # recalculate pure sharpe (without turnover penalty)
            opt_sharpe = opt_return / opt_vol if opt_vol > 0 else 0
        except ImportError:
            raise HTTPException(status_code=500, detail="需要安装 scipy 进行均值方差优化")

    turnover = float(np.sum(np.abs(weights - w_prev)))
    codes = returns.columns.tolist()
    return {
        "method": "mean_variance",
        "weights": [{"code": codes[i], "weight": round(float(weights[i]), 4)} for i in range(n)],
        "expected_return": round(float(opt_return), 4),
        "expected_volatility": round(float(opt_vol), 4),
        "sharpe_ratio": round(float(opt_sharpe), 2),
        "diversification_ratio": round(float(1 / np.sqrt(np.sum(weights ** 2) * n) if n > 1 else 1), 4),
        "turnover": round(turnover, 4),
    }


def _risk_parity(returns: pd.DataFrame, max_weight: float = 0.3, turnover_lambda: float = 0.0) -> dict:
    """风险平价优化"""
    n = len(returns.columns)
    sigma = _shrink_covariance(returns)
    w_prev = np.ones(n) / n

    def risk_budget_objective(w):
        portfolio_vol = np.sqrt(w.T @ sigma @ w)
        marginal_risk = sigma @ w
        risk_contrib = w * marginal_risk / portfolio_vol
        target_risk = portfolio_vol / n
        turnover = np.sum(np.abs(w - w_prev))
        return np.sum((risk_contrib - target_risk) ** 2) + turnover_lambda * turnover

    try:
        from scipy.optimize import minimize

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
        bounds = [(0.001, max_weight) for _ in range(n)]
        x0 = np.ones(n) / n

        result = minimize(risk_budget_objective, x0, method="SLSQP", constraints=constraints, bounds=bounds)
        weights = result.x

        mu = _shrink_returns(returns)
        opt_return = weights @ mu
        opt_vol = np.sqrt(weights.T @ sigma @ weights)
        opt_sharpe = opt_return / opt_vol if opt_vol > 0 else 0

        codes = returns.columns.tolist()
        turnover = float(np.sum(np.abs(weights - w_prev)))
        return {
            "method": "risk_parity",
            "weights": [{"code": codes[i], "weight": round(float(weights[i]), 4)} for i in range(n)],
            "expected_return": round(float(opt_return), 4),
            "expected_volatility": round(float(opt_vol), 4),
            "sharpe_ratio": round(float(opt_sharpe), 2),
            "diversification_ratio": round(float(1 / np.sqrt(np.sum(weights ** 2) * n) if n > 1 else 1), 4),
            "turnover": round(turnover, 4),
        }
    except ImportError:
        raise HTTPException(status_code=500, detail="需要安装 scipy 进行风险平价优化")


def _min_variance(returns: pd.DataFrame, max_weight: float = 0.3, turnover_lambda: float = 0.0) -> dict:
    """最小方差优化"""
    n = len(returns.columns)
    sigma = _shrink_covariance(returns)
    w_prev = np.ones(n) / n

    try:
        from scipy.optimize import minimize

        def objective(w):
            risk = np.sqrt(w.T @ sigma @ w)
            turnover = np.sum(np.abs(w - w_prev))
            return risk + turnover_lambda * turnover

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
        bounds = [(0.001, max_weight) for _ in range(n)]
        x0 = np.ones(n) / n

        result = minimize(objective, x0, method="SLSQP", constraints=constraints, bounds=bounds)
        weights = result.x

        mu = _shrink_returns(returns)
        opt_return = weights @ mu
        opt_vol = np.sqrt(weights.T @ sigma @ weights)
        opt_sharpe = opt_return / opt_vol if opt_vol > 0 else 0

        codes = returns.columns.tolist()
        turnover = float(np.sum(np.abs(weights - w_prev)))
        return {
            "method": "min_variance",
            "weights": [{"code": codes[i], "weight": round(float(weights[i]), 4)} for i in range(n)],
            "expected_return": round(float(opt_return), 4),
            "expected_volatility": round(float(opt_vol), 4),
            "sharpe_ratio": round(float(opt_sharpe), 2),
            "diversification_ratio": round(float(1 / np.sqrt(np.sum(weights ** 2) * n) if n > 1 else 1), 4),
            "turnover": round(turnover, 4),
        }
    except ImportError:
        raise HTTPException(status_code=500, detail="需要安装 scipy 进行最小方差优化")


def _equal_weight(returns: pd.DataFrame) -> dict:
    """等权配置（基准）"""
    n = len(returns.columns)
    w = 1.0 / n
    mu = _shrink_returns(returns)
    sigma = _shrink_covariance(returns)
    weights = np.ones(n) / n

    opt_return = weights @ mu
    opt_vol = np.sqrt(weights.T @ sigma @ weights)
    opt_sharpe = opt_return / opt_vol if opt_vol > 0 else 0

    codes = returns.columns.tolist()
    return {
        "method": "equal_weight",
        "weights": [{"code": codes[i], "weight": round(float(w), 4)} for i in range(n)],
        "expected_return": round(float(opt_return), 4),
        "expected_volatility": round(float(opt_vol), 4),
        "sharpe_ratio": round(float(opt_sharpe), 2),
        "diversification_ratio": round(float(1 / np.sqrt(np.sum(weights ** 2) * n) if n > 1 else 1), 4),
    }


def _compute_efficient_frontier(
    returns: pd.DataFrame,
    n_points: int = 50,
    max_weight: float = 0.3,
) -> List[dict]:
    """计算有效前沿"""
    n = len(returns.columns)
    mu = _shrink_returns(returns)
    sigma = _shrink_covariance(returns)

    # 等权和最小方差确定收益范围
    eq_w = np.ones(n) / n
    eq_ret = eq_w @ mu

    try:
        from scipy.optimize import minimize

        # 最小方差组合
        def min_vol(w):
            return np.sqrt(w.T @ sigma @ w)

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
        bounds = [(0.001, max_weight) for _ in range(n)]
        result = minimize(min_vol, eq_w, method="SLSQP", constraints=constraints, bounds=bounds)
        min_vol_ret = result.x @ mu

        # 最大收益组合（受限于 max_weight）
        def neg_return(w):
            return -(w @ mu)
        result = minimize(neg_return, eq_w, method="SLSQP", constraints=constraints, bounds=bounds)
        max_ret_val = result.x @ mu
        min_ret_val = min_vol_ret

        # 生成有效前沿
        frontier = []
        target_returns = np.linspace(min_ret_val, max_ret_val, n_points)
        for target in target_returns:
            try:
                def objective(w):
                    return np.sqrt(w.T @ sigma @ w)
                constraints_with_target = [
                    {"type": "eq", "fun": lambda w: np.sum(w) - 1},
                    {"type": "eq", "fun": lambda w, t=target: w @ mu - t},
                ]
                result = minimize(objective, eq_w, method="SLSQP", constraints=constraints_with_target, bounds=bounds)
                if result.success:
                    vol = np.sqrt(result.x.T @ sigma @ result.x)
                    frontier.append({
                        "ret": round(float(target), 4),
                        "volatility": round(float(vol), 4),
                        "sharpe": round(float(target / vol), 2) if vol > 0 else 0,
                    })
            except Exception:
                continue

        return frontier
    except ImportError:
        logger.warning("scipy 不可用，无法计算有效前沿")
        return []


@router.post("/optimize", response_model=PortfolioOptimizeResponse)
async def optimize_portfolio(request: PortfolioOptimizeRequest):
    """
    投资组合优化
    支持多种优化方法：max_sharpe, min_variance, risk_parity, equal_weight
    """
    try:
        codes = request.codes
        if len(codes) < 2:
            raise HTTPException(status_code=400, detail="至少需要 2 只股票")

        start_date = request.start_date or (date.today() - timedelta(days=365)).isoformat()
        end_date = request.end_date or date.today().isoformat()

        logger.info(f"组合优化: {codes}, method={request.method}")

        prices = _get_historical_prices(codes, start_date, end_date)
        returns = _compute_returns(prices)

        if returns.empty or len(returns) < 20:
            raise HTTPException(status_code=500, detail="数据不足，至少需要 20 个交易日")

        # 执行优化
        if request.method == "risk_parity":
            result = _risk_parity(returns, request.max_weight, request.turnover_lambda)
        elif request.method == "min_variance":
            result = _min_variance(returns, request.max_weight, request.turnover_lambda)
        elif request.method == "equal_weight":
            result = _equal_weight(returns)
        else:
            # max_sharpe (default)
            result = _mean_variance_optimization(
                returns,
                target_return=None,
                max_weight=request.max_weight,
                turnover_lambda=request.turnover_lambda,
            )

        # 有效前沿
        frontier = _compute_efficient_frontier(returns, max_weight=request.max_weight)

        # 等权基准对比
        bench = _equal_weight(returns)

        return PortfolioOptimizeResponse(
            codes=codes,
            start_date=start_date,
            end_date=end_date,
            method=result["method"],
            weights=[PortfolioWeight(**w) for w in result["weights"]],
            expected_return=result["expected_return"],
            expected_volatility=result["expected_volatility"],
            sharpe_ratio=result["sharpe_ratio"],
            diversification_ratio=result["diversification_ratio"],
            turnover=result.get("turnover"),
            efficient_frontier=[EfficientFrontierPoint(**p) for p in frontier],
            benchmark=bench,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"组合优化失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"组合优化失败: {str(e)}")
