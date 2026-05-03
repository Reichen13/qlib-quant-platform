"""
宏观策略 API - Bridgewater 风格宏观仪表板
使用 akshare 获取宏观指标，进行市场状态分类和全天候配置
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
    "SP500": {"name": "标普500", "type": "growth"},
    "Nasdaq": {"name": "纳斯达克", "type": "growth"},
    "Volatility": {"name": "SP500波动率", "type": "risk"},
    "10Y_Yield": {"name": "10年美债收益率", "type": "rates"},
    "USD_Index": {"name": "美元指数", "type": "currency"},
    "Gold": {"name": "黄金期货", "type": "commodity"},
    "Oil": {"name": "原油期货", "type": "commodity"},
    "DJI": {"name": "道琼斯", "type": "growth"},
}


def _to_datetime_index(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """统一将日期列转为 DatetimeIndex"""
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col)
    return df


def _compute_indicator(close: pd.Series, name: str, symbol: str) -> MacroIndicator:
    """基于收盘价序列计算宏观指标"""
    current = close.iloc[-1]
    if len(close) >= 21:
        prev_20d = close.iloc[-21]
        change_pct = ((current - prev_20d) / prev_20d) * 100
    else:
        change_pct = 0

    if len(close) >= 252:
        hist_1y = close.iloc[-252:]
        z_score = round(float((current - hist_1y.mean()) / (hist_1y.std() or 1)), 2)
    else:
        z_score = 0

    ma20 = close.iloc[-20:].mean() if len(close) >= 20 else current
    ma60 = close.iloc[-60:].mean() if len(close) >= 60 else current
    trend = "up" if ma20 > ma60 else "down"

    return MacroIndicator(
        name=name,
        symbol=symbol,
        value=round(float(current), 2),
        change_pct=round(float(change_pct), 2),
        trend=trend,
        z_score=z_score,
    )


def _fetch_sp500() -> pd.DataFrame:
    """获取标普500历史数据 (akshare)"""
    import akshare as ak
    df = ak.index_us_stock_sina(symbol=".INX")
    df = _to_datetime_index(df, "date")
    return df


def _fetch_macro_data() -> dict:
    """使用 akshare 获取宏观指标数据"""
    import akshare as ak

    indicators = {}

    # 1. 标普500 (最先获取，后续波动率计算依赖)
    sp500_df = None
    try:
        sp500_df = _fetch_sp500()
        indicators["SP500"] = _compute_indicator(sp500_df["close"], "标普500", "^GSPC")
        logger.info("标普500: {:.2f}".format(sp500_df["close"].iloc[-1]))
    except Exception as e:
        logger.warning(f"获取标普500失败: {e}")

    # 2. 纳斯达克
    try:
        nasdaq_df = ak.index_us_stock_sina(symbol=".IXIC")
        nasdaq_df = _to_datetime_index(nasdaq_df, "date")
        indicators["Nasdaq"] = _compute_indicator(nasdaq_df["close"], "纳斯达克", "^IXIC")
        logger.info("纳斯达克: {:.2f}".format(nasdaq_df["close"].iloc[-1]))
    except Exception as e:
        logger.warning(f"获取纳斯达克失败: {e}")

    # 3. SP500波动率 (替代VIX)
    try:
        if sp500_df is not None and not sp500_df.empty:
            vol_df = sp500_df
        else:
            vol_df = _fetch_sp500()
        returns = vol_df["close"].pct_change().dropna()
        vol_20d = returns.rolling(20).std() * (252 ** 0.5) * 100
        if len(vol_20d) >= 20:
            current_vol = vol_20d.iloc[-1]
            prev_20d_vol = vol_20d.iloc[-21] if len(vol_20d) >= 21 else current_vol
            change_pct = ((current_vol - prev_20d_vol) / prev_20d_vol) * 100 if prev_20d_vol != 0 else 0
            z_score = round(float((current_vol - vol_20d.mean()) / (vol_20d.std() or 1)), 2)
            trend = "down" if current_vol < vol_20d.mean() else "up"
            indicators["Volatility"] = MacroIndicator(
                name="SP500波动率",
                symbol="^VIX(proxy)",
                value=round(float(current_vol), 2),
                change_pct=round(float(change_pct), 2),
                trend=trend,
                z_score=z_score,
            )
            logger.info("SP500波动率: {:.1f}%".format(current_vol))
    except Exception as e:
        logger.warning(f"计算波动率失败: {e}")

    # 4. 10年美债收益率
    try:
        bond_df = ak.bond_zh_us_rate()
        bond_df = _to_datetime_index(bond_df, "日期")
        yield_col = "美国国债收益率10年"
        if yield_col in bond_df.columns:
            bond_close = bond_df[yield_col].dropna()
            if len(bond_close) > 0:
                indicators["10Y_Yield"] = _compute_indicator(bond_close, "10年美债收益率", "^TNX")
                logger.info("10年美债: {:.2f}%".format(bond_close.iloc[-1]))
    except Exception as e:
        logger.warning(f"获取美债收益率失败: {e}")

    # 5. 美元指数
    try:
        usd_df = ak.index_global_hist_em(symbol="美元指数")
        usd_df = _to_datetime_index(usd_df, "日期")
        indicators["USD_Index"] = _compute_indicator(usd_df["最新价"], "美元指数", "DX-Y.NYB")
        logger.info("美元指数: {:.2f}".format(usd_df["最新价"].iloc[-1]))
    except Exception as e:
        logger.warning(f"获取美元指数失败: {e}")

    # 6. 黄金期货
    try:
        gold_df = ak.futures_foreign_hist(symbol="GC")
        gold_df = _to_datetime_index(gold_df, "date")
        indicators["Gold"] = _compute_indicator(gold_df["close"], "黄金期货", "GC=F")
        logger.info("黄金期货: {:.2f}".format(gold_df["close"].iloc[-1]))
    except Exception as e:
        logger.warning(f"获取黄金期货失败: {e}")

    # 7. 原油期货
    try:
        oil_df = ak.futures_foreign_hist(symbol="CL")
        oil_df = _to_datetime_index(oil_df, "date")
        indicators["Oil"] = _compute_indicator(oil_df["close"], "原油期货", "CL=F")
        logger.info("原油期货: {:.2f}".format(oil_df["close"].iloc[-1]))
    except Exception as e:
        logger.warning(f"获取原油期货失败: {e}")

    # 8. 道琼斯 (替代罗素2000)
    try:
        dji_df = ak.index_us_stock_sina(symbol=".DJI")
        dji_df = _to_datetime_index(dji_df, "date")
        indicators["DJI"] = _compute_indicator(dji_df["close"], "道琼斯", "^DJI")
        logger.info("道琼斯: {:.2f}".format(dji_df["close"].iloc[-1]))
    except Exception as e:
        logger.warning(f"获取道琼斯失败: {e}")

    return indicators


def _compute_regime_scores(indicators: dict) -> dict:
    """
    计算增长/通胀得分
    增长因子: SP500趋势 + 纳斯达克趋势 + 道琼斯趋势
    通胀/风险因子: SP500波动率 + 原油趋势 + 黄金趋势 + 美元强度
    """
    # 增长得分
    growth_z = 0
    growth_count = 0
    for key in ["SP500", "Nasdaq", "DJI"]:
        if key in indicators:
            ind = indicators[key]
            score = (ind.change_pct / 5) * 0.6 + ind.z_score * 0.4
            growth_z += score
            growth_count += 1

    if growth_count > 0:
        growth_z = growth_z / growth_count
    growth_score = max(-2, min(2, growth_z))

    # 通胀/风险得分
    inflation_z = 0
    inflation_count = 0
    for key in ["Oil", "Gold", "Volatility"]:
        if key in indicators:
            ind = indicators[key]
            if key == "Volatility":
                # 波动率>30高风险，<15低风险
                score = (ind.value - 22) / 12
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
    使用 akshare 获取标普500、纳斯达克、美债收益率、美元指数、黄金、原油等关键指标
    """
    try:
        indicators = _fetch_macro_data()

        derived = {}
        if "10Y_Yield" in indicators:
            derived["yield_level"] = "高" if indicators["10Y_Yield"].value > 4.5 else "中" if indicators["10Y_Yield"].value > 3 else "低"
        if "Volatility" in indicators:
            vol_val = indicators["Volatility"].value
            derived["fear_level"] = "恐慌" if vol_val > 30 else "担忧" if vol_val > 20 else "平静"
        if "SP500" in indicators and "Gold" in indicators:
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
        import akshare as ak

        history = []
        today = date.today()

        # 获取 SP500 历史数据
        try:
            sp500_df = ak.index_us_stock_sina(symbol=".INX")
            sp500_df = _to_datetime_index(sp500_df, "date")
        except Exception as e:
            logger.warning(f"akshare 获取 SP500 历史失败: {e}")
            return {"history": [], "message": "无法获取历史数据"}

        if sp500_df.empty:
            return {"history": [], "message": "历史数据为空"}

        # 每月评估一次
        for month_offset in range(months, -1, -1):
            eval_date = today - timedelta(days=30 * month_offset)
            before = sp500_df[sp500_df.index <= pd.Timestamp(eval_date)]
            if before.empty:
                continue

            eval_ts = before.index[-1]
            sp500_slice = sp500_df[sp500_df.index <= eval_ts].tail(60)

            if len(sp500_slice) < 20:
                continue

            # 增长: SP500 20日涨跌幅
            sp500_current = sp500_slice["close"].iloc[-1]
            sp500_20d_ago = sp500_slice["close"].iloc[-min(21, len(sp500_slice))]
            growth_20d = (sp500_current - sp500_20d_ago) / sp500_20d_ago * 100

            # 通胀/风险: SP500 20日波动率
            returns = sp500_slice["close"].pct_change().dropna()
            vol_20d = returns.rolling(20).std().iloc[-1] * (252 ** 0.5) * 100 if len(returns) >= 20 else 15
            vix_score = (vol_20d - 22) / 12

            growth_score = max(-2, min(2, growth_20d / 5))
            inflation_score = max(-2, min(2, vix_score))

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
