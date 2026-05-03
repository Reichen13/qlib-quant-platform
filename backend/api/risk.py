"""
风险管理 API - Two Sigma 风格风险管理系统
提供 VaR、压力测试、相关性矩阵、头寸规模等风险管理功能
"""

import os
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from loguru import logger

# 添加路径
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from models.schemas import (
    RiskAnalysisRequest, RiskAnalysisResponse,
    RiskMetrics, StressTestResult, CorrelationItem,
    PositionSizingResult,
)

router = APIRouter()


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
    """获取历史收盘价数据"""
    try:
        from qlib.data import D
        qlib_codes = _to_qlib_codes(codes)
        prices = D.features(
            qlib_codes,
            ["$close"],
            start_time=start_date,
            end_time=end_date,
            freq="day",
        )
        if prices.empty:
            raise ValueError("Qlib 返回空数据")

        df = prices.reset_index()
        # pivot to wide format: date x instrument
        if "instrument" in df.columns:
            df = df.pivot(index="datetime", columns="instrument", values="$close")
        return df
    except Exception as e:
        logger.warning(f"Qlib 数据获取失败, 尝试 yfinance: {e}")
        return _get_prices_yfinance(codes, start_date, end_date)


def _get_prices_yfinance(codes: List[str], start_date: str, end_date: str) -> pd.DataFrame:
    """通过 yfinance 获取历史价格"""
    import yfinance as yf
    all_data = {}
    for code in codes:
        try:
            ticker = yf.Ticker(code)
            hist = ticker.history(start=start_date, end=end_date)
            if not hist.empty:
                all_data[code] = hist["Close"]
        except Exception as e:
            logger.warning(f"yfinance 获取 {code} 失败: {e}")
    if not all_data:
        raise HTTPException(status_code=500, detail="无法获取任何股票数据")
    return pd.DataFrame(all_data)


def _compute_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """计算日收益率"""
    return prices.pct_change().dropna()


def _compute_var(returns: pd.Series, confidence: float = 0.95, method: str = "historical") -> dict:
    """计算 VaR (Value at Risk)"""
    if method == "historical":
        var = np.percentile(returns.dropna(), (1 - confidence) * 100)
    elif method == "parametric":
        from scipy import stats
        mu = returns.mean()
        sigma = returns.std()
        var = mu + sigma * stats.norm.ppf(1 - confidence)
    else:
        var = np.percentile(returns.dropna(), (1 - confidence) * 100)

    cvar = returns[returns <= var].mean() if len(returns[returns <= var]) > 0 else var

    return {
        "var": round(float(var), 6),
        "cvar": round(float(cvar), 6),
        "confidence": confidence,
        "method": method,
    }


def _compute_stress_tests(returns: pd.DataFrame) -> List[dict]:
    """计算压力测试场景"""
    scenarios = []

    if returns.empty:
        return scenarios

    # 平均收益率序列（等权组合）
    portfolio_returns = returns.mean(axis=1)

    # 1. 历史最大回撤场景
    cum = (1 + portfolio_returns).cumprod()
    dd = cum / cum.cummax() - 1
    max_dd_idx = dd.idxmin()
    max_dd = dd.min()
    scenarios.append({
        "name": "历史最大回撤",
        "description": "回溯期内组合经历的最大回撤",
        "impact": round(float(max_dd) * 100, 2),
        "scenario_type": "historical",
    })

    # 2. 2008 金融危机模拟（年化 -50%，波动率 60%）
    scenarios.append({
        "name": "2008 金融危机",
        "description": "模拟 2008 年金融危机情景：股市暴跌 50%，波动率飙升",
        "impact": round(float(np.mean(portfolio_returns) * 252 * 0.5 * 100 - np.std(portfolio_returns) * np.sqrt(252) * 100 * 2), 2),
        "scenario_type": "hypothetical",
    })

    # 3. 2015 A股股灾（年化 -40%，高波动）
    scenarios.append({
        "name": "2015 A股股灾",
        "description": "模拟 2015 年 A 股市场异常波动",
        "impact": round(float(np.percentile(portfolio_returns, 1) * 252 * 100), 2),
        "scenario_type": "historical_proxy",
    })

    # 4. 2020 新冠疫情冲击
    scenarios.append({
        "name": "2020 新冠疫情",
        "description": "模拟疫情导致的市场恐慌性下跌",
        "impact": round(float(np.percentile(portfolio_returns, 5) * 60 * 100), 2),
        "scenario_type": "historical_proxy",
    })

    # 5. 利率冲击（加息 200bp）
    scenarios.append({
        "name": "利率冲击 +200bp",
        "description": "央行意外加息 200 基点，债券和股票同时承压",
        "impact": round(float(portfolio_returns.mean() * 252 * 100 * 0.7 - 5), 2),
        "scenario_type": "hypothetical",
    })

    return scenarios


def _compute_correlation_matrix(returns: pd.DataFrame) -> List[dict]:
    """计算相关性矩阵"""
    if returns.shape[1] < 2:
        return []

    corr = returns.corr()
    result = []
    codes = corr.columns.tolist()

    for i, c1 in enumerate(codes):
        for j, c2 in enumerate(codes):
            if i < j:
                result.append({
                    "stock1": c1,
                    "stock2": c2,
                    "correlation": round(float(corr.loc[c1, c2]), 4),
                })

    return result


def _kelly_criterion(returns: pd.Series, risk_free_rate: float = 0.02) -> dict:
    """计算 Kelly 最优仓位"""
    mu = returns.mean() * 252
    sigma = returns.std() * np.sqrt(252)
    excess_return = mu - risk_free_rate

    if sigma == 0:
        return {"kelly_fraction": 0, "half_kelly": 0, "quarter_kelly": 0}

    kelly = excess_return / (sigma ** 2)
    kelly = max(0, min(kelly, 1))  # clamp to [0, 1]

    return {
        "kelly_fraction": round(float(kelly), 4),
        "half_kelly": round(float(kelly / 2), 4),
        "quarter_kelly": round(float(kelly / 4), 4),
        "annual_return": round(float(mu), 4),
        "annual_volatility": round(float(sigma), 4),
        "sharpe": round(float(excess_return / sigma), 4) if sigma > 0 else 0,
    }


@router.post("/analyze", response_model=RiskAnalysisResponse)
async def analyze_risk(request: RiskAnalysisRequest):
    """
    综合风险分析
    分析投资组合的各类风险指标
    """
    try:
        codes = request.codes
        if not codes:
            # 默认使用 CSI300 成分股中的代表性股票
            codes = ["600519.SS", "000858.SZ", "601318.SS", "000333.SZ", "600036.SS"]

        start_date = request.start_date or (date.today() - timedelta(days=365)).isoformat()
        end_date = request.end_date or date.today().isoformat()

        logger.info(f"风险分析: {codes}, {start_date} ~ {end_date}")

        prices = _get_historical_prices(codes, start_date, end_date)
        returns = _compute_returns(prices)

        if returns.empty:
            raise HTTPException(status_code=500, detail="无法计算收益率，数据不足")

        # 等权组合收益率
        portfolio_returns = returns.mean(axis=1)

        # 基本指标
        annual_return = float(portfolio_returns.mean() * 252)
        annual_vol = float(portfolio_returns.std() * np.sqrt(252))
        sharpe = annual_return / annual_vol if annual_vol > 0 else 0

        # 回撤
        cum = (1 + portfolio_returns).cumprod()
        dd = cum / cum.cummax() - 1
        max_dd = float(dd.min())

        # Calmar
        calmar = annual_return / abs(max_dd) if max_dd != 0 else 0

        # 胜率
        win_rate = float((portfolio_returns > 0).mean())

        # VaR
        var_95 = _compute_var(portfolio_returns, 0.95)
        var_99 = _compute_var(portfolio_returns, 0.99)

        # 波动率锥（不同窗口的波动率）
        vol_cone = {}
        for window in [5, 10, 20, 60]:
            rolling_vol = portfolio_returns.rolling(window).std() * np.sqrt(252)
            vol_cone[f"{window}日"] = {
                "min": round(float(rolling_vol.min()), 4),
                "max": round(float(rolling_vol.max()), 4),
                "current": round(float(rolling_vol.iloc[-1]), 4) if len(rolling_vol) > 0 else 0,
            }

        # 相关性
        correlations = _compute_correlation_matrix(returns)
        avg_corr = round(float(np.mean([c["correlation"] for c in correlations])), 4) if correlations else 0

        # 压力测试
        stress_tests = _compute_stress_tests(returns)

        # 仓位建议
        kelly = _kelly_criterion(portfolio_returns)

        metrics = RiskMetrics(
            annual_return=round(annual_return, 4),
            annual_volatility=round(annual_vol, 4),
            sharpe_ratio=round(sharpe, 2),
            calmar_ratio=round(calmar, 2),
            max_drawdown=round(max_dd, 4),
            win_rate=round(win_rate, 4),
            var_95=var_95["var"],
            cvar_95=var_95["cvar"],
            var_99=var_99["var"],
            cvar_99=var_99["cvar"],
            avg_correlation=avg_corr,
            vol_cone=vol_cone,
        )

        # 回撤曲线数据
        drawdown_data = []
        for dt_idx in range(len(dd)):
            dt = dd.index[dt_idx]
            drawdown_data.append({
                "date": dt.strftime("%Y-%m-%d") if hasattr(dt, 'strftime') else str(dt),
                "value": round(float(dd.iloc[dt_idx]) * 100, 2),
            })

        # 净值曲线
        equity_data = []
        for dt_idx in range(len(cum)):
            dt = cum.index[dt_idx]
            equity_data.append({
                "date": dt.strftime("%Y-%m-%d") if hasattr(dt, 'strftime') else str(dt),
                "value": round(float(cum.iloc[dt_idx]), 4),
            })

        stress_results = [
            StressTestResult(**s) for s in stress_tests
        ]
        correlation_items = [
            CorrelationItem(**c) for c in correlations[:30]
        ]

        # 仓位建议文案
        if sharpe > 1.5 and max_dd > -0.1:
            risk_level = "低风险"
            risk_suggestion = "策略表现优秀，可适度加大仓位至 70-80%"
        elif sharpe > 1.0 and max_dd > -0.2:
            risk_level = "中等风险"
            risk_suggestion = "策略表现良好，建议仓位 50-70%，注意回撤控制"
        elif sharpe > 0.5:
            risk_level = "中高风险"
            risk_suggestion = "风险收益比一般，建议轻仓 30-50%，严格止损"
        else:
            risk_level = "高风险"
            risk_suggestion = "策略风险较高，建议观望或极小仓位试探"

        return RiskAnalysisResponse(
            codes=codes,
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
            stress_tests=stress_results,
            correlations=correlation_items,
            position_sizing=PositionSizingResult(
                kelly_fraction=kelly["kelly_fraction"],
                half_kelly=kelly["half_kelly"],
                quarter_kelly=kelly["quarter_kelly"],
                risk_level=risk_level,
                suggestion=risk_suggestion,
            ),
            equity=equity_data,
            drawdown=drawdown_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"风险分析失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"风险分析失败: {str(e)}")


@router.post("/stress-test")
async def run_stress_test(request: RiskAnalysisRequest):
    """专项压力测试"""
    try:
        codes = request.codes or ["600519.SS", "000858.SZ", "601318.SS", "000333.SZ", "600036.SS"]
        start_date = request.start_date or (date.today() - timedelta(days=365)).isoformat()
        end_date = request.end_date or date.today().isoformat()

        prices = _get_historical_prices(codes, start_date, end_date)
        returns = _compute_returns(prices)

        stress_tests = _compute_stress_tests(returns)
        return {"codes": codes, "stress_tests": stress_tests}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-checklist")
async def get_daily_checklist():
    """每日风险检查清单"""
    return {
        "checklist": [
            {"id": 1, "item": "检查持仓股票的 VaR 是否在限额内", "category": "仓位风险", "priority": "high"},
            {"id": 2, "item": "确认单票仓位不超过总资产的 5%", "category": "仓位风险", "priority": "high"},
            {"id": 3, "item": "检查行业集中度，单一行业不超过 30%", "category": "集中度风险", "priority": "high"},
            {"id": 4, "item": "确认总杠杆率在安全线以内", "category": "杠杆风险", "priority": "medium"},
            {"id": 5, "item": "检查止损单是否已设置并有效", "category": "止损管理", "priority": "high"},
            {"id": 6, "item": "确认流动性覆盖率 > 1.5x", "category": "流动性风险", "priority": "medium"},
            {"id": 7, "item": "检查配对交易的相关性是否稳定", "category": "策略风险", "priority": "medium"},
            {"id": 8, "item": "确认无重大事件/公告影响持仓", "category": "事件风险", "priority": "medium"},
            {"id": 9, "item": "检查回撤是否触发减仓线", "category": "回撤控制", "priority": "high"},
            {"id": 10, "item": "记录当日操作日志和风险事件", "category": "合规记录", "priority": "low"},
        ]
    }
