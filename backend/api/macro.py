"""
宏观策略 API - Bridgewater 风格宏观仪表板
使用 akshare 获取宏观指标，进行市场状态分类和全天候配置
"""

from datetime import date, datetime, timedelta
import asyncio
from typing import Optional
import pandas as pd
import numpy as np
from fastapi import APIRouter, HTTPException
from loguru import logger

from models.schemas import (
    MacroIndicator, MacroRegimeRequest, MacroRegimeResponse,
    AllocationAsset, AllocationResponse,
)

router = APIRouter()

MACRO_FETCH_TIMEOUT_SECONDS = 8


async def _fetch_macro_with_timeout(fetcher, label: str) -> tuple[dict, str | None]:
    try:
        data = await asyncio.wait_for(asyncio.to_thread(fetcher), timeout=MACRO_FETCH_TIMEOUT_SECONDS)
        return data, None
    except TimeoutError:
        logger.warning(f"{label} 宏观数据源超时，已降级为空数据")
        return {}, f"{label} 宏观数据源超时，暂时无法显示实时数据"
    except Exception as exc:
        logger.warning(f"{label} 宏观数据源获取失败: {exc}")
        return {}, f"{label} 宏观数据源获取失败：{exc}"


# ── 美国宏观指标配置（保留用于美股/ETF 策略）──
US_INDICATOR_CONFIG = {
    "SP500": {"name": "标普500", "type": "growth"},
    "Nasdaq": {"name": "纳斯达克", "type": "growth"},
    "Volatility": {"name": "SP500波动率", "type": "risk"},
    "10Y_Yield": {"name": "10年美债收益率", "type": "rates"},
    "USD_Index": {"name": "美元指数", "type": "currency"},
    "Gold": {"name": "黄金期货", "type": "commodity"},
    "Oil": {"name": "原油期货", "type": "commodity"},
    "DJI": {"name": "道琼斯", "type": "growth"},
}

# ── 中国宏观指标配置 ──
CN_INDICATOR_CONFIG = {
    "CN_PMI_Mfg": {"name": "制造业PMI", "type": "growth"},
    "CN_PMI_NonMfg": {"name": "非制造业PMI", "type": "growth"},
    "CN_M2": {"name": "M2同比增速", "type": "liquidity"},
    "CN_SHIBOR_ON": {"name": "SHIBOR隔夜", "type": "rates"},
    "CN_SHIBOR_1M": {"name": "SHIBOR 1月", "type": "rates"},
    "CN_Bond_10Y": {"name": "10年中债收益率", "type": "rates"},
    "CN_North_Flow": {"name": "北向资金净流入", "type": "flow"},
    "CN_Gold": {"name": "黄金(人民币)", "type": "commodity"},
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


def _parse_cn_period(value) -> pd.Timestamp:
    """解析 akshare 常见的中文月份/日期字段。"""
    text = str(value).strip()
    text = text.replace("月份", "").replace("年", "-").replace("月", "-01")
    return pd.to_datetime(text, errors="coerce")


def _series_by_date(df: pd.DataFrame, value_col: str, date_col: str) -> pd.Series:
    data = df[[date_col, value_col]].copy()
    data["_date"] = data[date_col].map(_parse_cn_period)
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna(subset=["_date", value_col]).sort_values("_date")
    return data.set_index("_date")[value_col]


def _indicator_from_series(
    series: pd.Series,
    *,
    name: str,
    symbol: str,
    threshold: Optional[float] = None,
    change_as_diff: bool = False,
    precision: int = 2,
) -> Optional[MacroIndicator]:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None

    latest = float(values.iloc[-1])
    prev = float(values.iloc[-2]) if len(values) > 1 else latest
    if change_as_diff:
        change = latest - prev
    else:
        change = ((latest - prev) / abs(prev)) * 100 if prev != 0 else 0
    hist = values.tail(252 if len(values) > 60 else 24)
    z = (latest - hist.mean()) / (hist.std() or 1) if len(hist) > 1 else 0

    if threshold is not None:
        trend = "up" if latest >= threshold else "down"
    else:
        ma = values.tail(min(20, len(values))).mean()
        trend = "up" if latest >= ma else "down"

    return MacroIndicator(
        name=name,
        symbol=symbol,
        value=round(latest, precision),
        change_pct=round(float(change), 2),
        trend=trend,
        z_score=round(float(z), 2),
    )


def _fetch_sp500() -> pd.DataFrame:
    """获取标普500历史数据 (akshare)"""
    import akshare as ak
    df = ak.index_us_stock_sina(symbol=".INX")
    df = _to_datetime_index(df, "date")
    return df


# ═══════════════════════════════════════════════════════════
# 中国宏观指标获取
# ═══════════════════════════════════════════════════════════

def _fetch_china_macro_data() -> dict:
    """使用 akshare 获取 A 股核心宏观指标"""
    import akshare as ak

    indicators = {}

    # 1. 制造业 PMI
    try:
        pmi_df = ak.macro_china_pmi()
        if not pmi_df.empty:
            if {"指标", "今值"}.issubset(pmi_df.columns):
                pmi_mfg = pmi_df[pmi_df["指标"] == "制造业PMI"].copy()
                series = pd.to_numeric(pmi_mfg["今值"], errors="coerce").dropna().tail(24)
            else:
                series = _series_by_date(pmi_df, "制造业-指数", "月份").tail(24)
            indicator = _indicator_from_series(series, name="制造业PMI", symbol="PMI", threshold=50)
            if indicator:
                indicators["CN_PMI_Mfg"] = indicator
                logger.info(f"中国制造业PMI: {indicator.value}")
    except Exception as e:
        logger.warning(f"获取中国PMI失败: {e}")

    # 2. 非制造业 PMI
    try:
        pmi_df = ak.macro_china_pmi()
        if not pmi_df.empty:
            if {"指标", "今值"}.issubset(pmi_df.columns):
                pmi_nonmfg = pmi_df[pmi_df["指标"] == "非制造业PMI"].copy()
                series = pd.to_numeric(pmi_nonmfg["今值"], errors="coerce").dropna().tail(24)
            else:
                series = _series_by_date(pmi_df, "非制造业-指数", "月份").tail(24)
            indicator = _indicator_from_series(series, name="非制造业PMI", symbol="NMI", threshold=50)
            if indicator:
                indicators["CN_PMI_NonMfg"] = indicator
                logger.info(f"中国非制造业PMI: {indicator.value}")
    except Exception as e:
        logger.warning(f"获取非制造业PMI失败: {e}")

    # 3. M2 货币供应
    try:
        m2_df = ak.macro_china_money_supply()
        if not m2_df.empty:
            if "货币和准货币(M2)-同比增长" in m2_df.columns:
                series = _series_by_date(m2_df, "货币和准货币(M2)-同比增长", "月份")
            elif "M2" in m2_df.columns:
                raw = pd.to_numeric(m2_df["M2"], errors="coerce").dropna()
                series = raw.pct_change() * 100
            else:
                series = pd.Series(dtype="float64")
            indicator = _indicator_from_series(
                series,
                name="M2同比增速",
                symbol="M2",
                threshold=8,
                change_as_diff=True,
            )
            if indicator:
                indicators["CN_M2"] = indicator
                logger.info(f"M2同比增速: {indicator.value:.1f}%")
    except Exception as e:
        logger.warning(f"获取M2失败: {e}")

    # 4. SHIBOR 利率
    try:
        shibor_func = getattr(ak, "macro_china_shibor", None) or getattr(ak, "macro_china_shibor_all", None)
        if shibor_func:
            shibor_df = shibor_func()
            if not shibor_df.empty:
                on_col = "O/N" if "O/N" in shibor_df.columns else "O/N-定价"
                one_month_col = "1M" if "1M" in shibor_df.columns else "1M-定价"
                date_col = "日期" if "日期" in shibor_df.columns else shibor_df.columns[0]
                if on_col in shibor_df.columns:
                    indicator = _indicator_from_series(
                        _series_by_date(shibor_df, on_col, date_col),
                        name="SHIBOR隔夜",
                        symbol="SHIBOR",
                        precision=4,
                    )
                    if indicator:
                        indicators["CN_SHIBOR_ON"] = indicator
                        logger.info(f"SHIBOR隔夜: {indicator.value:.2f}%")
                if one_month_col in shibor_df.columns:
                    indicator = _indicator_from_series(
                        _series_by_date(shibor_df, one_month_col, date_col),
                        name="SHIBOR 1月",
                        symbol="SHIBOR1M",
                        precision=4,
                    )
                    if indicator:
                        indicators["CN_SHIBOR_1M"] = indicator
    except Exception as e:
        logger.warning(f"获取SHIBOR失败: {e}")

    # 5. 10年中债收益率
    try:
        try:
            bond_df = ak.bond_china_close_return()
        except Exception:
            bond_df = ak.bond_china_yield()
        if not bond_df.empty:
            if "曲线名称" in bond_df.columns:
                bond_df = bond_df[bond_df["曲线名称"].astype(str).str.contains("国债", na=False)]
            date_col = "日期" if "日期" in bond_df.columns else None
            ten_year_col = None
            for col in bond_df.columns:
                if "10" in str(col) and "年" in str(col):
                    ten_year_col = col
                    break

            if ten_year_col:
                series = _series_by_date(bond_df, ten_year_col, date_col) if date_col else pd.to_numeric(bond_df[ten_year_col], errors="coerce")
                if not series.empty and isinstance(series.index, pd.DatetimeIndex):
                    latest_date = series.index[-1]
                    if latest_date < pd.Timestamp(datetime.now() - timedelta(days=180)):
                        logger.warning(f"中债收益率数据过旧: {latest_date.date()}")
                        series = pd.Series(dtype="float64")
                indicator = _indicator_from_series(
                    series,
                    name="10年中债收益率",
                    symbol="CN10Y",
                    precision=4,
                )
                if indicator:
                    indicators["CN_Bond_10Y"] = indicator
                    logger.info(f"10年中债收益率: {indicator.value:.2f}%")
    except Exception as e:
        logger.warning(f"获取中债收益率失败: {e}")

    # 6. 北向资金净流入
    try:
        if hasattr(ak, "stock_hsgt_north_net_flow_in_em"):
            north_df = ak.stock_hsgt_north_net_flow_in_em()
            date_col = north_df.columns[0]
            flow_col = north_df.columns[1] if len(north_df.columns) > 1 else north_df.columns[0]
            if date_col == flow_col:
                flow_col = north_df.columns[-1]
            north_df[date_col] = pd.to_datetime(north_df[date_col])
            north_flow = north_df.set_index(date_col)[flow_col].dropna().astype(float)
            if len(north_flow) >= 20:
                latest = float(north_flow.iloc[-1])
                recent_20d = north_flow.iloc[-20:]
                total_20d = recent_20d.sum()
                trend_20d = recent_20d.sum()
                z = ((latest - north_flow.mean()) / (north_flow.std() or 1))
                indicators["CN_North_Flow"] = MacroIndicator(
                    name="北向资金净流入", symbol="NORTH",
                    value=round(latest / 1e8, 2),
                    change_pct=round(total_20d / 1e8, 2),
                    trend="up" if trend_20d > 0 else "down",
                    z_score=round(float(z), 2),
                )
                logger.info(f"北向资金净流入: {latest:.0f}元 (20日: {total_20d:.0f}元)")
        elif hasattr(ak, "stock_hsgt_fund_flow_summary_em"):
            north_df = ak.stock_hsgt_fund_flow_summary_em()
            if not north_df.empty and {"资金方向", "成交净买额"}.issubset(north_df.columns):
                north_rows = north_df[north_df["资金方向"].astype(str).str.contains("北向", na=False)]
                flows = pd.to_numeric(north_rows["成交净买额"], errors="coerce").dropna()
                if not flows.empty:
                    latest = float(flows.sum())
                    indicators["CN_North_Flow"] = MacroIndicator(
                        name="北向资金净流入",
                        symbol="NORTH",
                        value=round(latest, 2),
                        change_pct=0,
                        trend="up" if latest > 0 else "down",
                        z_score=0,
                    )
                    logger.info(f"北向资金净流入汇总: {latest:.2f}亿")
    except Exception as e:
        logger.warning(f"获取北向资金失败: {e}")

    # 7. 黄金(人民币计价) - 使用全球黄金价格，美元/人民币折算
    try:
        gold_df = ak.futures_foreign_hist(symbol="GC")
        if not gold_df.empty:
            gold_df = _to_datetime_index(gold_df, "date")
            gold_close = gold_df["close"]
            indicators["CN_Gold"] = _compute_indicator(gold_close, "黄金(人民币)", "GC=F")
            logger.info("黄金(人民币): {:.2f}".format(gold_close.iloc[-1]))
    except Exception as e:
        logger.warning(f"获取黄金数据失败: {e}")

    return indicators


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

    返回两个市场组：
    - china_indicators: A 股核心宏观指标（PMI/M2/SHIBOR/中债/北向资金）
    - us_indicators: 美国宏观指标（标普/纳斯达克/美债/美元等）
    """
    try:
        us_result, china_result = await asyncio.gather(
            _fetch_macro_with_timeout(_fetch_macro_data, "美国"),
            _fetch_macro_with_timeout(_fetch_china_macro_data, "中国"),
        )
        us_indicators, us_warning = us_result
        china_indicators, china_warning = china_result

        # ── 中国衍生指标 ──
        cn_derived = {}
        if "CN_PMI_Mfg" in china_indicators:
            pmi = china_indicators["CN_PMI_Mfg"].value
            cn_derived["pmi_level"] = "扩张" if pmi > 50 else "收缩"
            cn_derived["pmi_trend"] = "上升" if china_indicators["CN_PMI_Mfg"].trend == "up" else "下降"
        if "CN_M2" in china_indicators:
            m2 = china_indicators["CN_M2"].value
            cn_derived["liquidity"] = "宽松" if m2 > 10 else "中性" if m2 > 8 else "偏紧"
        if "CN_North_Flow" in china_indicators:
            flow = china_indicators["CN_North_Flow"]
            cn_derived["north_flow_trend"] = "持续流入" if flow.change_pct > 0 else "净流出"
        if "CN_Bond_10Y" in china_indicators:
            yield_val = china_indicators["CN_Bond_10Y"].value
            cn_derived["yield_level"] = "高" if yield_val > 3.5 else "中" if yield_val > 2.5 else "低"

        # ── 美国衍生指标 ──
        us_derived = {}
        if "10Y_Yield" in us_indicators:
            us_derived["yield_level"] = "高" if us_indicators["10Y_Yield"].value > 4.5 else "中" if us_indicators["10Y_Yield"].value > 3 else "低"
        if "Volatility" in us_indicators:
            vol_val = us_indicators["Volatility"].value
            us_derived["fear_level"] = "恐慌" if vol_val > 30 else "担忧" if vol_val > 20 else "平静"
        if "SP500" in us_indicators and "Gold" in us_indicators:
            us_derived["risk_on_ratio"] = round(us_indicators["SP500"].value / us_indicators["Gold"].value, 2)

        missing_cn = [
            config["name"]
            for key, config in CN_INDICATOR_CONFIG.items()
            if key not in china_indicators
        ]
        missing_us = [
            config["name"]
            for key, config in US_INDICATOR_CONFIG.items()
            if key not in us_indicators
        ]

        return {
            "china_indicators": list(china_indicators.values()),
            "us_indicators": list(us_indicators.values()),
            "china_derived": cn_derived,
            "us_derived": us_derived,
            "data_status": {
                "china": {
                    "status": "ok" if not missing_cn else "partial" if china_indicators else "unavailable",
                    "available": len(china_indicators),
                    "missing": missing_cn,
                },
                "us": {
                    "status": "ok" if not missing_us else "partial" if us_indicators else "unavailable",
                    "available": len(us_indicators),
                    "missing": missing_us,
                },
            },
            "warnings": [
                warning for warning in [
                    china_warning,
                    us_warning,
                    f"中国宏观数据源缺少：{'、'.join(missing_cn)}" if missing_cn else None,
                    f"美国宏观数据源缺少：{'、'.join(missing_us)}" if missing_us else None,
                ] if warning
            ],
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"宏观指标获取失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"宏观指标获取失败: {str(e)}")


def _compute_cn_regime_scores(indicators: dict) -> dict:
    """
    基于中国宏观指标计算增长/流动性得分

    中国版四象限：增长维度(PMI) vs 流动性维度(M2/SHIBOR)
    """
    growth_z = 0
    growth_count = 0
    for key in ["CN_PMI_Mfg", "CN_PMI_NonMfg"]:
        if key in indicators:
            ind = indicators[key]
            # PMI > 50 扩张, < 50 收缩
            growth_z += (ind.value - 50) / 5
            growth_count += 1

    if growth_count > 0:
        growth_z = growth_z / growth_count
    growth_score = max(-2, min(2, growth_z))

    # 流动性/通胀维度
    inflation_z = 0
    inflation_count = 0
    for key in ["CN_M2", "CN_SHIBOR_ON"]:
        if key in indicators:
            ind = indicators[key]
            if key == "CN_SHIBOR_ON":
                # SHIBOR 高 = 流动性紧
                score = (2.0 - ind.value) / 2
            else:
                # M2 同比增速
                score = (ind.value - 8) / 4
            inflation_z += score
            inflation_count += 1

    if inflation_count > 0:
        inflation_z = inflation_z / inflation_count
    if growth_count == 0 or inflation_count == 0:
        missing = []
        if growth_count == 0:
            missing.append("PMI")
        if inflation_count == 0:
            missing.append("M2/SHIBOR")
        return {
            "growth_score": 0.0,
            "inflation_score": 0.0,
            "regime": "unknown",
            "regime_label": "数据不足",
            "confidence": 0.0,
            "quadrant": "Q0",
            "warnings": [f"中国宏观关键指标不足：缺少 {'、'.join(missing)}，暂不生成明确宏观状态。"],
        }
    inflation_score = max(-2, min(2, inflation_z))

    # 象限
    if growth_score >= 0 and inflation_score >= 0:
        quadrant = "Q1"
        regime = "recovery"
        regime_label = "复苏扩张期"
    elif growth_score < 0 and inflation_score >= 0:
        quadrant = "Q2"
        regime = "overheat"
        regime_label = "流动性宽松期"
    elif growth_score < 0 and inflation_score < 0:
        quadrant = "Q3"
        regime = "deflation"
        regime_label = "紧缩减速期"
    else:
        quadrant = "Q4"
        regime = "stagflation"
        regime_label = "紧货币扩张期"

    confidence = 0.5 + abs(growth_score) * 0.1 + abs(inflation_score) * 0.1
    confidence = min(0.95, confidence)

    return {
        "growth_score": round(growth_score, 2),
        "inflation_score": round(inflation_score, 2),
        "regime": regime,
        "regime_label": regime_label,
        "confidence": round(confidence, 2),
        "quadrant": quadrant,
        "warnings": [],
    }


@router.post("/regime")
async def classify_regime(request: MacroRegimeRequest, market: str = "china"):
    """
    市场状态分类 - 增长 vs 通胀/流动性 2x2 矩阵

    参数 market:
    - "china": 使用中国宏观指标（PMI/M2/SHIBOR，默认）
    - "us": 使用美国宏观指标（标普/纳斯达克/波动率）
    """
    try:
        if market == "us":
            indicators, warning = await _fetch_macro_with_timeout(_fetch_macro_data, "美国")
            regime = _compute_regime_scores(indicators)
        else:
            indicators, warning = await _fetch_macro_with_timeout(_fetch_china_macro_data, "中国")
            regime = _compute_cn_regime_scores(indicators)
        if warning:
            regime["warnings"] = [*regime.get("warnings", []), warning]

        return MacroRegimeResponse(
            growth_score=regime["growth_score"],
            inflation_score=regime["inflation_score"],
            regime=regime["regime"],
            regime_label=regime["regime_label"],
            confidence=regime["confidence"],
            quadrant=regime["quadrant"],
            warnings=regime.get("warnings") or None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"状态分类失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"状态分类失败: {str(e)}")


# ── 中国宏观状态的全天候配置 ──
CN_ALLOCATION_MAP = {
    "recovery": {
        "allocation": [
            AllocationAsset(asset="A股股票", weight=0.35, reason="PMI扩张期，企业盈利改善"),
            AllocationAsset(asset="可转债", weight=0.20, reason="股性偏强，进可攻退可守"),
            AllocationAsset(asset="利率债", weight=0.20, reason="分散风险，提供下行保护"),
            AllocationAsset(asset="黄金", weight=0.15, reason="对冲全球不确定性"),
            AllocationAsset(asset="北向资金重仓股", weight=0.10, reason="外资持续流入受益"),
        ],
        "risk_level": "进取",
        "summary": "PMI扩张+流动性宽松，是A股最佳配置阶段。建议增持股票和可转债，关注北向资金持续流入的行业龙头。",
    },
    "overheat": {
        "allocation": [
            AllocationAsset(asset="短久期信用债", weight=0.30, reason="流动性充裕，信用利差收窄"),
            AllocationAsset(asset="黄金", weight=0.25, reason="通胀预期上行，避险需求增加"),
            AllocationAsset(asset="A股防御板块", weight=0.20, reason="消费/医药防御型行业"),
            AllocationAsset(asset="货基/现金", weight=0.15, reason="应对政策微调"),
            AllocationAsset(asset="商品ETF", weight=0.10, reason="受益于流动性宽松"),
        ],
        "risk_level": "中性",
        "summary": "流动性宽松但PMI放缓，市场缺乏方向。建议债股均衡配置，降低波动较大的成长股仓位。",
    },
    "deflation": {
        "allocation": [
            AllocationAsset(asset="利率债", weight=0.35, reason="经济下行期避险首选"),
            AllocationAsset(asset="货基/现金", weight=0.25, reason="保持流动性，等待底部信号"),
            AllocationAsset(asset="高股息股票", weight=0.15, reason="防御型配置，获取股息收益"),
            AllocationAsset(asset="黄金", weight=0.15, reason="对冲极端风险"),
            AllocationAsset(asset="短债", weight=0.10, reason="短久期降低利率风险"),
        ],
        "risk_level": "保守",
        "summary": "PMI收缩+流动性偏紧，A股承压。建议大幅增持债券和现金，仅配置少量高股息防御型股票。",
    },
    "stagflation": {
        "allocation": [
            AllocationAsset(asset="黄金", weight=0.30, reason="货币紧缩期最佳避险资产"),
            AllocationAsset(asset="货基/现金", weight=0.25, reason="保持流动性，等待政策转向"),
            AllocationAsset(asset="短久期利率债", weight=0.20, reason="短端受益于紧缩政策"),
            AllocationAsset(asset="商品ETF", weight=0.15, reason="能源和农产品具刚性需求"),
            AllocationAsset(asset="A股周期股", weight=0.10, reason="精选受益于价格上行的周期行业"),
        ],
        "risk_level": "保守",
        "summary": "PMI扩张但流动性偏紧，市场分化严重。建议以黄金和现金为主，重点关注受益于价格上涨的周期板块。",
    },
}


@router.post("/allocation")
async def get_allocation(request: MacroRegimeRequest, market: str = "china"):
    """
    基于当前状态的配置建议 (默认为中国宏观视角)

    参数 market:
    - "china": 使用中国宏观指标和A股配置方案（默认）
    - "us": 使用美国宏观指标和全天候配置方案
    """
    try:
        if market == "us":
            indicators, warning = await _fetch_macro_with_timeout(_fetch_macro_data, "美国")
            regime = _compute_regime_scores(indicators)
            if warning:
                regime["warnings"] = [*regime.get("warnings", []), warning]
            allocation_config = ALLOCATION_MAP.get(regime["regime"], ALLOCATION_MAP["recovery"])
        else:
            indicators, warning = await _fetch_macro_with_timeout(_fetch_china_macro_data, "中国")
            regime = _compute_cn_regime_scores(indicators)
            if warning:
                regime["warnings"] = [*regime.get("warnings", []), warning]
            if regime["regime"] == "unknown":
                return AllocationResponse(
                    regime=regime["regime"],
                    regime_label=regime["regime_label"],
                    allocation=[],
                    risk_level="待确认",
                    summary="中国宏观关键指标不足，暂不生成全天候配置建议。请先确认 PMI、M2 或 SHIBOR 数据源是否恢复。",
                    warnings=regime.get("warnings") or None,
                )
            allocation_config = CN_ALLOCATION_MAP.get(regime["regime"], CN_ALLOCATION_MAP["recovery"])

        return AllocationResponse(
            regime=regime["regime"],
            regime_label=regime["regime_label"],
            allocation=allocation_config["allocation"],
            risk_level=allocation_config["risk_level"],
            summary=allocation_config["summary"],
            warnings=regime.get("warnings") or None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"配置建议失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"配置建议失败: {str(e)}")


@router.get("/history")
async def get_regime_history(months: int = 12, market: str = "china"):
    """
    获取历史状态演变
    每月末重新评估状态，返回时间序列

    参数 market:
    - "china": 中国宏观指标历史（默认）
    - "us": 美国宏观指标历史
    """
    try:
        import akshare as ak

        history = []
        today = date.today()

        if market == "us":
            # 美国宏观历史（基于SP500）
            try:
                sp500_df = ak.index_us_stock_sina(symbol=".INX")
                sp500_df = _to_datetime_index(sp500_df, "date")
            except Exception as e:
                logger.warning(f"akshare 获取 SP500 历史失败: {e}")
                return {"history": [], "message": "无法获取历史数据"}

            if sp500_df.empty:
                return {"history": [], "message": "历史数据为空"}

            for month_offset in range(months, -1, -1):
                eval_date = today - timedelta(days=30 * month_offset)
                before = sp500_df[sp500_df.index <= pd.Timestamp(eval_date)]
                if before.empty:
                    continue
                eval_ts = before.index[-1]
                sp500_slice = sp500_df[sp500_df.index <= eval_ts].tail(60)
                if len(sp500_slice) < 20:
                    continue
                sp500_current = sp500_slice["close"].iloc[-1]
                sp500_20d_ago = sp500_slice["close"].iloc[-min(21, len(sp500_slice))]
                growth_20d = (sp500_current - sp500_20d_ago) / sp500_20d_ago * 100
                returns = sp500_slice["close"].pct_change().dropna()
                vol_20d = returns.rolling(20).std().iloc[-1] * (252 ** 0.5) * 100 if len(returns) >= 20 else 15
                vix_score = (vol_20d - 22) / 12
                growth_score = max(-2, min(2, growth_20d / 5))
                inflation_score = max(-2, min(2, vix_score))
                if growth_score >= 0 and inflation_score <= 0:
                    regime, label = "recovery", "复苏期"
                elif growth_score >= 0 and inflation_score > 0:
                    regime, label = "overheat", "过热期"
                elif growth_score < 0 and inflation_score <= 0:
                    regime, label = "deflation", "通缩期"
                else:
                    regime, label = "stagflation", "滞胀期"
                history.append({
                    "date": str(eval_ts.date()),
                    "growth_score": round(growth_score, 2),
                    "inflation_score": round(inflation_score, 2),
                    "regime": regime,
                    "regime_label": label,
                })
        else:
            # 中国宏观历史（基于PMI）
            try:
                pmi_df = ak.macro_china_pmi()
                if pmi_df.empty:
                    return {"history": [], "message": "无法获取中国PMI历史数据"}
                if {"指标", "今值"}.issubset(pmi_df.columns):
                    pmi_mfg = pmi_df[pmi_df["指标"] == "制造业PMI"].copy()
                    if pmi_mfg.empty:
                        return {"history": [], "message": "无制造业PMI数据"}
                    pmi_mfg["今值"] = pd.to_numeric(pmi_mfg["今值"], errors="coerce")
                    pmi_mfg = pmi_mfg.dropna(subset=["今值"]).tail(months + 1)
                    rows = [
                        (str(row.get("日期", "")), float(row["今值"]))
                        for _, row in pmi_mfg.iterrows()
                    ]
                elif {"月份", "制造业-指数"}.issubset(pmi_df.columns):
                    series = _series_by_date(pmi_df, "制造业-指数", "月份").tail(months + 1)
                    rows = [(idx.strftime("%Y-%m"), float(value)) for idx, value in series.items()]
                else:
                    return {"history": [], "message": "无制造业PMI数据"}
                for row_date, pmi_val in rows:
                    growth_score = max(-2, min(2, (pmi_val - 50) / 5))
                    inflation_score = 0  # 流动性维度简化处理
                    if growth_score >= 0 and inflation_score >= 0:
                        regime, label = "recovery", "复苏扩张期"
                    elif growth_score < 0 and inflation_score >= 0:
                        regime, label = "overheat", "流动性宽松期"
                    elif growth_score < 0 and inflation_score < 0:
                        regime, label = "deflation", "紧缩减速期"
                    else:
                        regime, label = "stagflation", "紧货币扩张期"
                    history.append({
                        "date": row_date,
                        "growth_score": round(growth_score, 2),
                        "inflation_score": round(inflation_score, 2),
                        "regime": regime,
                        "regime_label": label,
                    })
            except Exception as e:
                logger.warning(f"中国宏观历史数据获取失败: {e}")
                return {"history": [], "message": f"无法获取中国宏观历史数据: {e}"}

        return {"history": history}

    except Exception as e:
        logger.error(f"历史状态获取失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"历史状态获取失败: {str(e)}")
