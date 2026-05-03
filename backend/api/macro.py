"""
宏观策略 API - Bridgewater 风格宏观仪表板
使用 yfinance 获取宏观指标，进行市场状态分类和全天候配置
"""

from datetime import date, datetime, timedelta
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException
from loguru import logger

from models.schemas import (
    MacroIndicator, MacroRegimeRequest, MacroRegimeResponse,
    AllocationAsset, AllocationResponse,
)

router = APIRouter()

# ── 宏观指标配置 ──
INDICATOR_CONFIG = {
    "SP500": {"symbol": "^GSPC", "name": "标普500", "type": "growth"},
    "Nasdaq": {"symbol": "^IXIC", "name": "纳斯达克", "type": "growth"},
    "VIX": {"symbol": "^VIX", "name": "波动率指数", "type": "risk"},
    "10Y_Yield": {"symbol": "^TNX", "name": "10年美债收益率", "type": "rates"},
    "USD_Index": {"symbol": "DX-Y.NYB", "name": "美元指数", "type": "currency"},
    "Gold": {"symbol": "GC=F", "name": "黄金期货", "type": "commodity"},
    "Oil": {"symbol": "CL=F", "name": "原油期货", "type": "commodity"},
    "Russell2000": {"symbol": "^RUT", "name": "罗素2000", "type": "growth"},
}


def _fetch_macro_data() -> dict:
    """使用 yfinance 获取宏观指标数据"""
    import yfinance as yf

    symbols = list(set(c["symbol"] for c in INDICATOR_CONFIG.values()))
    indicators = {}

    try:
        for key, cfg in INDICATOR_CONFIG.items():
            try:
                ticker = yf.Ticker(cfg["symbol"])
                hist = ticker.history(period="1y")
                if hist.empty:
                    logger.warning(f"未获取到 {cfg['name']} 数据")
                    continue

                current = hist["Close"].iloc[-1]
                # 20日变动
                if len(hist) >= 21:
                    prev_20d = hist["Close"].iloc[-21]
                    change_pct = ((current - prev_20d) / prev_20d) * 100
                else:
                    change_pct = 0

                # Z-Score (vs 252日)
                if len(hist) >= 252:
                    hist_1y = hist["Close"].iloc[-252:]
                    z_score = (current - hist_1y.mean()) / (hist_1y.std() or 1)
                else:
                    z_score = 0

                # 趋势判断 (20日均线 vs 60日均线)
                ma20 = hist["Close"].iloc[-20:].mean() if len(hist) >= 20 else current
                ma60 = hist["Close"].iloc[-60:].mean() if len(hist) >= 60 else current
                trend = "up" if ma20 > ma60 else "down"

                indicators[key] = MacroIndicator(
                    name=cfg["name"],
                    symbol=cfg["symbol"],
                    value=round(float(current), 2),
                    change_pct=round(float(change_pct), 2),
                    trend=trend,
                    z_score=round(float(z_score), 2),
                )
            except Exception as e:
                logger.warning(f"获取 {cfg['name']} 失败: {e}")
                continue

    except Exception as e:
        logger.error(f"宏观数据获取失败: {e}")
        raise HTTPException(status_code=500, detail=f"宏观数据获取失败: {str(e)}")

    return indicators


def _compute_regime_scores(indicators: dict) -> dict:
    """
    计算增长/通胀得分
    增长因子: SP500趋势 + 纳斯达克趋势 + 罗素2000趋势
    通胀/风险因子: VIX水平 + 原油趋势 + 黄金趋势 + 美元强度
    """
    # 增长得分
    growth_z = 0
    growth_count = 0
    for key in ["SP500", "Nasdaq", "Russell2000"]:
        if key in indicators:
            ind = indicators[key]
            # 20日涨跌幅 + Z-score 综合
            score = (ind.change_pct / 5) * 0.6 + ind.z_score * 0.4
            growth_z += score
            growth_count += 1

    if growth_count > 0:
        growth_z = growth_z / growth_count
    growth_score = max(-2, min(2, growth_z))

    # 通胀/风险得分
    inflation_z = 0
    inflation_count = 0
    for key in ["Oil", "Gold", "VIX"]:
        if key in indicators:
            ind = indicators[key]
            if key == "VIX":
                # VIX>25为高风险，<15为低风险
                score = (ind.value - 20) / 10
            else:
                score = (ind.change_pct / 5) * 0.6 + ind.z_score * 0.4
            inflation_z += score
            inflation_count += 1

    if inflation_count > 0:
        inflation_z = inflation_z / inflation_count
    inflation_score = max(-2, min(2, inflation_z))

    # 确定状态象限
    if growth_score >= 0 and inflation_score <= 0:
        quadrant = "Q1"
        regime = "recovery"
        regime_label = "复苏期"
    elif growth_score >= 0 and inflation_score > 0:
        quadrant = "Q2"
        regime = "overheat"
        regime_label = "过热期"
    elif growth_score < 0 and inflation_score <= 0:
        quadrant = "Q3"
        regime = "deflation"
        regime_label = "通缩期"
    else:
        quadrant = "Q4"
        regime = "stagflation"
        regime_label = "滞胀期"

    # 置信度
    confidence = 0.5 + abs(growth_score) * 0.1 + abs(inflation_score) * 0.1
    confidence = min(0.95, confidence)

    return {
        "growth_score": round(growth_score, 2),
        "inflation_score": round(inflation_score, 2),
        "regime": regime,
        "regime_label": regime_label,
        "confidence": round(confidence, 2),
        "quadrant": quadrant,
    }


# ── 全天候配置方案 (Bridgewater All-Weather) ──
ALLOCATION_MAP = {
    "recovery": {
        "allocation": [
            AllocationAsset(asset="股票", weight=0.35, reason="经济增长向好，股票受益最大"),
            AllocationAsset(asset="信用债", weight=0.25, reason="信用环境改善，利差收窄"),
            AllocationAsset(asset="国债", weight=0.20, reason="分散风险，提供下行保护"),
            AllocationAsset(asset="商品", weight=0.10, reason="适度配置实物资产"),
            AllocationAsset(asset="黄金", weight=0.10, reason="通胀对冲，尾部风险保护"),
        ],
        "risk_level": "进取",
        "summary": "复苏期经济增长加速，通胀温和，是配置风险资产的最佳阶段。建议增持股票和信用债，适度配置商品和黄金作为分散工具。",
    },
    "overheat": {
        "allocation": [
            AllocationAsset(asset="商品", weight=0.30, reason="通胀上行，商品直接受益"),
            AllocationAsset(asset="黄金", weight=0.20, reason="通胀对冲，避险需求增加"),
            AllocationAsset(asset="TIPS", weight=0.20, reason="通胀保值债券直接对冲通胀"),
            AllocationAsset(asset="股票", weight=0.15, reason="精选定价能力强的行业龙头"),
            AllocationAsset(asset="现金", weight=0.15, reason="应对紧缩政策冲击"),
        ],
        "risk_level": "保守",
        "summary": "过热期通胀压力上升，央行可能收紧政策。建议降低股票仓位，增持商品、黄金和通胀保值债券(TIPS)，保留现金应对波动。",
    },
    "deflation": {
        "allocation": [
            AllocationAsset(asset="国债", weight=0.35, reason="避险需求推高国债价格"),
            AllocationAsset(asset="投资级债", weight=0.25, reason="高评级企业债相对安全"),
            AllocationAsset(asset="现金", weight=0.20, reason="流动性为王，等待机会"),
            AllocationAsset(asset="黄金", weight=0.10, reason="避险和对冲极端风险"),
            AllocationAsset(asset="股票", weight=0.10, reason="精选防御型板块"),
        ],
        "risk_level": "保守",
        "summary": "通缩期经济增长放缓，物价下跌。建议大幅增持国债和高等级信用债，保留现金储备，仅配置少量防御型股票。",
    },
    "stagflation": {
        "allocation": [
            AllocationAsset(asset="黄金", weight=0.25, reason="滞胀环境下的最佳避险资产"),
            AllocationAsset(asset="现金", weight=0.25, reason="保持流动性，等待转机"),
            AllocationAsset(asset="TIPS", weight=0.20, reason="通胀保值债券提供确定性收益"),
            AllocationAsset(asset="短债", weight=0.15, reason="短期债券利率敏感度低"),
            AllocationAsset(asset="商品", weight=0.15, reason="能源和农产品具刚性需求"),
        ],
        "risk_level": "保守",
        "summary": "滞胀是投资环境最恶劣的阶段（增长放缓+通胀高企）。建议以黄金和现金为主，配置通胀保值债券和短期国债，尽量减少股票配置。",
    },
}


@router.get("/indicators")
async def get_macro_indicators():
    """
    获取宏观指标面板数据
    使用 yfinance 获取 VIX、SP500、国债收益率、黄金、原油等关键指标
    """
    try:
        indicators = _fetch_macro_data()

        # 衍生指标
        derived = {}
        if "10Y_Yield" in indicators:
            derived["yield_level"] = "高" if indicators["10Y_Yield"].value > 4.5 else "中" if indicators["10Y_Yield"].value > 3 else "低"
        if "VIX" in indicators:
            vix_val = indicators["VIX"].value
            derived["fear_level"] = "恐慌" if vix_val > 30 else "担忧" if vix_val > 20 else "平静"
        if "SP500" in indicators and "Gold" in indicators:
            # 股票 vs 黄金比价
            derived["risk_on_ratio"] = round(indicators["SP500"].value / indicators["Gold"].value, 2)

        return {
            "indicators": list(indicators.values()),
            "derived": derived,
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"宏观指标获取失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"宏观指标获取失败: {str(e)}")


@router.post("/regime")
async def classify_regime(request: MacroRegimeRequest):
    """
    市场状态分类 - 增长/通胀 2x2 矩阵
    基于宏观指标数据对当前市场状态进行分类
    """
    try:
        indicators = _fetch_macro_data()
        regime = _compute_regime_scores(indicators)

        return MacroRegimeResponse(
            growth_score=regime["growth_score"],
            inflation_score=regime["inflation_score"],
            regime=regime["regime"],
            regime_label=regime["regime_label"],
            confidence=regime["confidence"],
            quadrant=regime["quadrant"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"状态分类失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"状态分类失败: {str(e)}")


@router.post("/allocation")
async def get_allocation(request: MacroRegimeRequest):
    """
    基于当前状态的全天候配置建议
    参考 Bridgewater All-Weather 四宫格框架
    """
    try:
        indicators = _fetch_macro_data()
        regime = _compute_regime_scores(indicators)
        regime_type = regime["regime"]

        allocation_config = ALLOCATION_MAP.get(regime_type, ALLOCATION_MAP["recovery"])

        return AllocationResponse(
            regime=regime_type,
            regime_label=regime["regime_label"],
            allocation=allocation_config["allocation"],
            risk_level=allocation_config["risk_level"],
            summary=allocation_config["summary"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"配置建议失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"配置建议失败: {str(e)}")


@router.get("/history")
async def get_regime_history(months: int = 12):
    """
    获取历史状态演变
    每月末重新评估状态，返回时间序列
    """
    try:
        import yfinance as yf

        history = []
        today = date.today()

        # 使用 SP500 和 VIX 的历史数据估算状态演变
        try:
            sp500 = yf.Ticker("^GSPC")
            sp500_hist = sp500.history(period=f"{months + 3}mo")
            vix = yf.Ticker("^VIX")
            vix_hist = vix.history(period=f"{months + 3}mo")
        except Exception:
            # yfinance 失败时返回空
            return {"history": [], "message": "无法获取历史数据"}

        if sp500_hist.empty or vix_hist.empty:
            return {"history": [], "message": "历史数据为空"}

        # 每月评估一次
        for month_offset in range(months, -1, -1):
            eval_date = today - timedelta(days=30 * month_offset)
            # 找到最接近的交易日
            sp500_before = sp500_hist[sp500_hist.index <= pd.Timestamp(eval_date)]
            if sp500_before.empty:
                continue

            eval_ts = sp500_before.index[-1]
            sp500_slice = sp500_hist[sp500_hist.index <= eval_ts].tail(60)
            vix_slice = vix_hist[vix_hist.index <= eval_ts].tail(60)

            if len(sp500_slice) < 20 or len(vix_slice) < 20:
                continue

            # 增长: SP500 20日涨跌幅
            sp500_current = sp500_slice["Close"].iloc[-1]
            sp500_20d_ago = sp500_slice["Close"].iloc[-min(21, len(sp500_slice))]
            growth_20d = (sp500_current - sp500_20d_ago) / sp500_20d_ago * 100

            # 通胀/风险: VIX 水平
            vix_current = vix_slice["Close"].iloc[-1]
            vix_score = (vix_current - 20) / 10

            # 映射到得分
            growth_score = max(-2, min(2, growth_20d / 5))
            inflation_score = max(-2, min(2, vix_score))

            # 状态
            if growth_score >= 0 and inflation_score <= 0:
                regime = "recovery"
                label = "复苏期"
            elif growth_score >= 0 and inflation_score > 0:
                regime = "overheat"
                label = "过热期"
            elif growth_score < 0 and inflation_score <= 0:
                regime = "deflation"
                label = "通缩期"
            else:
                regime = "stagflation"
                label = "滞胀期"

            history.append({
                "date": str(eval_ts.date()),
                "growth_score": round(growth_score, 2),
                "inflation_score": round(inflation_score, 2),
                "regime": regime,
                "regime_label": label,
            })

        return {"history": history}

    except Exception as e:
        logger.error(f"历史状态获取失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"历史状态获取失败: {str(e)}")
