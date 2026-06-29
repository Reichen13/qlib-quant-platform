"""
AI 策略 API

- GET  /api/ai-strategy/templates     策略模板库
- POST /api/ai-strategy/generate      NL→策略生成
- POST /api/ai-strategy/analyze       持仓分析建议
- POST /api/ai-strategy/optimize      AI 驱动参数优化
"""

import json
import re
from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

router = APIRouter()


# ── 请求/响应模型 ──

class NLStrategyRequest(BaseModel):
    description: str = Field(..., min_length=5, description="自然语言策略描述")
    use_deep: bool = Field(default=False, description="是否使用深度推理")
    api_key: Optional[str] = Field(default=None, description="用户 API Key（可选，优先级高于服务器配置）")
    base_url: Optional[str] = Field(default=None, description="用户 Base URL（可选）")
    quick_model: Optional[str] = Field(default=None, description="快速模型名称（可选）")
    deep_model: Optional[str] = Field(default=None, description="深度模型名称（可选）")


class StrategyTemplate(BaseModel):
    id: str
    name: str
    description: str
    category: str  # trend, momentum, value, mean_reversion, factor_rotation
    default_params: dict


class PortfolioHolding(BaseModel):
    code: str
    name: str = ""
    weight: float
    cost: Optional[float] = None


class StrategyAnalyzeRequest(BaseModel):
    holdings: list[PortfolioHolding]
    total_capital: float = Field(default=1_000_000, ge=1, description="总资金")
    risk_tolerance: str = Field(default="moderate", description="风险偏好: conservative/moderate/aggressive")
    api_key: Optional[str] = Field(default=None, description="用户 API Key（可选）")
    base_url: Optional[str] = Field(default=None, description="用户 Base URL（可选）")
    quick_model: Optional[str] = Field(default=None, description="快速模型名称（可选）")
    deep_model: Optional[str] = Field(default=None, description="深度模型名称（可选）")


class StrategyOptimizeRequest(BaseModel):
    strategy_type: str = Field(..., description="策略类型")
    param_ranges: dict = Field(default={}, description="参数范围")
    start_date: Optional[str] = Field(default=None, description="优化回测起始日期")
    api_key: Optional[str] = Field(default=None, description="用户 API Key（可选）")
    base_url: Optional[str] = Field(default=None, description="用户 Base URL（可选）")
    quick_model: Optional[str] = Field(default=None, description="快速模型名称（可选）")
    deep_model: Optional[str] = Field(default=None, description="深度模型名称（可选）")


class AIScreeningSignalsRequest(BaseModel):
    candidates: list[str] | None = Field(default=None, description="可选：要联动评分的股票代码")


# ── 策略模板库 ──

STRATEGY_TEMPLATES: list[dict] = [
    {
        "id": "ma_cross",
        "name": "均线交叉策略",
        "description": "当短期均线上穿长期均线时买入，下穿时卖出。经典趋势跟踪策略。",
        "category": "trend",
        "default_params": {
            "fast_period": 5,
            "slow_period": 20,
            "hold_num": 20,
            "turnover": 5,
        },
    },
    {
        "id": "momentum_breakout",
        "name": "动量突破策略",
        "description": "买入N日内涨幅最大的股票，定期轮换。基于强者恒强的动量效应。",
        "category": "momentum",
        "default_params": {
            "lookback_days": 20,
            "hold_num": 15,
            "turnover": 5,
            "stop_loss": -0.08,
        },
    },
    {
        "id": "value_select",
        "name": "价值选股策略",
        "description": "买入ROE>15%且PE<行业均值的低估值股票，每月调仓。格雷厄姆-巴菲特式价值投资。",
        "category": "value",
        "default_params": {
            "min_roe": 0.15,
            "max_pe_ratio": 20,
            "hold_num": 20,
            "turnover": 21,
        },
    },
    {
        "id": "mean_reversion",
        "name": "均值回归策略",
        "description": "买入RSI<30的超卖股票，待回归均值后卖出。基于价格向均值回归的统计规律。",
        "category": "mean_reversion",
        "default_params": {
            "rsi_threshold": 30,
            "bollinger_period": 20,
            "hold_num": 10,
            "turnover": 3,
        },
    },
    {
        "id": "factor_rotation",
        "name": "因子轮动策略",
        "description": "动态选择近期IC/ICIR最高的因子，每两周切换因子组合。适应市场风格切换。",
        "category": "factor_rotation",
        "default_params": {
            "top_factors": 10,
            "rotation_period": 10,
            "hold_num": 30,
            "turnover": 10,
        },
    },
    {
        "id": "low_volatility",
        "name": "低波动异常策略",
        "description": "买入低波动、低Beta的防御型股票，适合震荡市。低风险稳定收益。",
        "category": "mean_reversion",
        "default_params": {
            "vol_window": 60,
            "min_beta": -0.5,
            "max_beta": 0.8,
            "hold_num": 25,
            "turnover": 21,
        },
    },
    {
        "id": "dual_thrust",
        "name": "双推力通道策略",
        "description": "基于N日最高价/最低价构建通道，突破上轨做多。海龟交易法则变种。",
        "category": "trend",
        "default_params": {
            "lookback": 20,
            "k1": 0.7,
            "k2": 0.7,
            "hold_num": 10,
            "turnover": 5,
        },
    },
    {
        "id": "quality_growth",
        "name": "质量成长策略",
        "description": "买入毛利率>30%、净利润增速>20%的高质量成长股，季度调仓。",
        "category": "value",
        "default_params": {
            "min_gross_margin": 0.30,
            "min_profit_growth": 0.20,
            "hold_num": 15,
            "turnover": 63,
        },
    },
    {
        "id": "dividend_low_vol_csi",
        "name": "红利低波防御策略",
        "description": "筛选高股息率、低波动、现金流稳定的央国企和成熟行业龙头，适合震荡市和利率下行阶段。",
        "category": "value",
        "default_params": {
            "min_dividend_yield": 0.03,
            "max_volatility": 0.25,
            "min_cashflow_quality": 0.6,
            "hold_num": 20,
            "turnover": 21,
        },
    },
    {
        "id": "ai_compute_semiconductor_momentum",
        "name": "AI算力半导体动量策略",
        "description": "围绕AI算力、半导体设备、先进封装和国产替代方向，结合成交额放大与20日动量筛选强趋势标的。",
        "category": "momentum",
        "default_params": {
            "theme_keywords": ["AI算力", "半导体", "先进封装", "国产替代"],
            "lookback_days": 20,
            "min_amount_rank": 0.3,
            "hold_num": 12,
            "turnover": 5,
            "stop_loss": -0.08,
        },
    },
    {
        "id": "low_altitude_robotics_theme",
        "name": "低空经济机器人主题策略",
        "description": "跟踪低空经济、人形机器人、智能制造等政策和产业催化主题，要求主题强度、量能和价格趋势同时确认。",
        "category": "factor_rotation",
        "default_params": {
            "theme_keywords": ["低空经济", "机器人", "智能制造"],
            "theme_strength_min": 0.65,
            "volume_ratio_min": 1.2,
            "hold_num": 10,
            "turnover": 5,
            "stop_loss": -0.10,
        },
    },
    {
        "id": "export_leader_quality_growth",
        "name": "出海龙头质量成长策略",
        "description": "筛选海外收入占比提升、盈利质量稳定、ROE较高的制造业出海龙头，兼顾汇率和全球需求弹性。",
        "category": "value",
        "default_params": {
            "min_roe": 0.12,
            "min_profit_growth": 0.15,
            "min_export_exposure": 0.25,
            "hold_num": 15,
            "turnover": 21,
            "max_position": 0.08,
        },
    },
    {
        "id": "policy_catalyst_theme_rotation",
        "name": "政策催化主题轮动策略",
        "description": "在新质生产力、设备更新、国企改革、消费刺激等政策催化主题之间轮动，选择近10日强度最高且未极端超买的方向。",
        "category": "factor_rotation",
        "default_params": {
            "theme_keywords": ["新质生产力", "设备更新", "国企改革", "消费刺激"],
            "rotation_period": 10,
            "rsi_max": 75,
            "hold_num": 20,
            "turnover": 10,
        },
    },
]


# ── 辅助函数 ──

def _check_llm_available(api_key: Optional[str] = None):
    """检查 LLM 是否可用。如果用户提供了 api_key 则始终可用。"""
    if api_key:
        return True
    try:
        from core.llm_client import get_llm_config
        if not get_llm_config().is_configured:
            raise HTTPException(
                status_code=503,
                detail="LLM 未配置。请在设置页面输入您的 API Key，或联系管理员配置服务器。",
            )
        return True
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM 不可用: {e}")


def _get_llm_client(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    quick_model: Optional[str] = None,
    deep_model: Optional[str] = None,
):
    """获取 LLM 客户端（优先使用用户 key）"""
    if api_key:
        from core.llm_client import create_llm_client
        return create_llm_client(
            api_key=api_key,
            base_url=base_url or "",
            quick_model=quick_model or "",
            deep_model=deep_model or "",
        )
    from core.llm_client import get_llm_client
    return get_llm_client()


def _parse_strategy_params(llm_text: str) -> dict:
    """从 LLM 输出中解析策略参数 JSON"""
    json_match = re.search(r"\{[\s\S]*\"model\"[\s\S]*\}", llm_text)
    if not json_match:
        json_match = re.search(r"\{[\s\S]*\}", llm_text)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        number = float(value)
        if number != number:
            return default
        return number
    except (TypeError, ValueError):
        return default


def score_screening_candidate(candidate: dict) -> dict:
    """Score a screening candidate with deterministic strategy rules.

    This makes the AI Strategy module usable without relying only on LLM text:
    it reads real screening signals such as mean reversion, factor score and
    daily change, then returns a reusable strategy score.
    """
    item = dict(candidate)
    mean_reversion = item.get("mean_reversion") or {}
    factor_signal = item.get("factor_signal") or {}

    score = 45.0
    votes: list[dict] = []
    cautions: list[str] = []

    factor_score = _safe_float(factor_signal.get("score"))
    factor_rank = int(_safe_float(factor_signal.get("rank"), 999))
    if "score" in factor_signal:
        if factor_score >= 0.75 and factor_rank <= 5:
            score += 25
            votes.append({"strategy": "factor_rotation", "signal": "support", "reason": "复合因子排名靠前"})
        elif factor_score >= 0.25:
            score += 12
            votes.append({"strategy": "factor_rotation", "signal": "watch", "reason": "复合因子为正"})
        elif factor_score <= -0.5:
            score -= 18
            cautions.append("复合因子拖累明显")

    rsi = _safe_float(mean_reversion.get("rsi"), 50)
    bollinger_position = _safe_float(mean_reversion.get("bollingerPosition"), 0.5)
    signal = str(mean_reversion.get("signal") or "")
    if 40 <= rsi <= 68 and 0.25 <= bollinger_position <= 0.75:
        score += 15
        votes.append({"strategy": "mean_reversion", "signal": "support", "reason": "未处于明显超买区"})
    elif rsi <= 35 or bollinger_position <= 0.2 or "超卖" in signal:
        score += 8
        votes.append({"strategy": "mean_reversion", "signal": "watch", "reason": "处于修复观察区"})
    elif rsi >= 75 or bollinger_position >= 0.9 or "超买" in signal:
        score -= 25
        cautions.append("均值回归指标显示超买")

    change_pct = _safe_float(item.get("change_pct"))
    if 0.5 <= change_pct <= 6.5:
        score += 10
        votes.append({"strategy": "momentum", "signal": "support", "reason": "动量温和且未极端冲高"})
    elif change_pct >= 9.5:
        score -= 20
        cautions.append("涨幅接近涨停，追高风险较大")
    elif change_pct < -4:
        score -= 8
        cautions.append("短线跌幅较大，需等待企稳")

    score = max(0, min(100, round(score, 1)))
    if score >= 65 and not cautions:
        recommendation = "buyable"
        action = "保留"
    elif score >= 55:
        recommendation = "wait"
        action = "等待"
    elif score <= 35:
        recommendation = "avoid"
        action = "降级"
    else:
        recommendation = "watch"
        action = "观察"

    item["ai_strategy"] = {
        "status": "available",
        "score": score,
        "recommendation": recommendation,
        "action": action,
        "votes": votes,
        "cautions": cautions,
        "reason": "；".join([v["reason"] for v in votes] + cautions) or "信号不足，先观察",
    }
    return item


def attach_ai_strategy_scores_to_candidates(candidates: list[dict]) -> list[dict]:
    return [score_screening_candidate(candidate) for candidate in candidates]


def summarize_ai_strategy_scores(candidates: list[dict]) -> dict:
    scored = [c.get("ai_strategy") or {} for c in candidates if (c.get("ai_strategy") or {}).get("status") == "available"]
    if not scored:
        return {"status": "unavailable", "message": "暂无 AI 策略联动评分"}
    avg_score = sum(_safe_float(item.get("score")) for item in scored) / len(scored)
    buckets = {
        "buyable": sum(1 for item in scored if item.get("recommendation") == "buyable"),
        "wait": sum(1 for item in scored if item.get("recommendation") == "wait"),
        "watch": sum(1 for item in scored if item.get("recommendation") == "watch"),
        "avoid": sum(1 for item in scored if item.get("recommendation") == "avoid"),
    }
    return {
        "status": "available",
        "average_score": round(avg_score, 1),
        "buckets": buckets,
        "top": sorted(
            [
                {
                    "code": candidate.get("code"),
                    "name": candidate.get("name"),
                    "score": (candidate.get("ai_strategy") or {}).get("score"),
                    "recommendation": (candidate.get("ai_strategy") or {}).get("recommendation"),
                }
                for candidate in candidates
                if (candidate.get("ai_strategy") or {}).get("status") == "available"
            ],
            key=lambda item: _safe_float(item.get("score")),
            reverse=True,
        )[:10],
    }


# ── 端点 ──

@router.get("/templates")
async def get_templates():
    """获取策略模板库"""
    return {
        "total": len(STRATEGY_TEMPLATES),
        "templates": STRATEGY_TEMPLATES,
    }


@router.post("/screening-signals")
async def get_ai_screening_signals(req: AIScreeningSignalsRequest | None = None):
    """Run AI Strategy scoring on post-close screening candidates."""
    req = req or AIScreeningSignalsRequest()
    warnings: list[str] = []
    try:
        from . import screening
        from utils.code_normalization import normalize_stock_code

        raw_candidates = req.candidates or screening.DEFAULT_CANDIDATES
        codes = [normalize_stock_code(code, target="qlib") for code in raw_candidates]
        factor_result, factor_task = screening._load_latest_completed_factor_result(warnings)
        factor_summary = screening.summarize_factor_analysis_result(factor_result, factor_task)
        factor_scores = screening._compute_candidate_factor_scores(codes, factor_summary, warnings)
        candidates = await screening._collect_candidates(codes, warnings, factor_scores)
        scored = attach_ai_strategy_scores_to_candidates(candidates)
        return {
            "run_date": date.today().isoformat(),
            "summary": summarize_ai_strategy_scores(scored),
            "candidates": scored,
            "warnings": warnings,
        }
    except Exception as exc:
        logger.warning(f"AI 策略选股联动失败: {exc}")
        raise HTTPException(status_code=500, detail=f"AI 策略选股联动失败: {exc}")


@router.post("/generate")
async def generate_strategy(req: NLStrategyRequest):
    """NL→策略：将自然语言描述转换为回测参数

    示例输入: "买入沪深300成分股中ROE>15%且处于60日均线以上的股票，每月调仓"
    """
    _check_llm_available(req.api_key)

    client = _get_llm_client(req.api_key, req.base_url, req.quick_model, req.deep_model)

    # 构建 prompt
    templates_desc = "\n".join(
        f"- {t['name']}: {t['description']}"
        for t in STRATEGY_TEMPLATES
    )

    try:
        from datetime import date
        today = date.today()
        train_start = date(today.year - 2, today.month, 1).isoformat()
        train_end = (today - timedelta(days=today.day + 30)).isoformat()
        if train_end.month == 12:
            train_end = train_end.replace(year=train_end.year, month=12, day=31)
        else:
            train_end = train_end.replace(day=1) - timedelta(days=1)
        test_start = train_end.replace(day=1) + timedelta(days=32)
        test_start = test_start.replace(day=1)
        test_end = (today - timedelta(days=1)).isoformat()
    except Exception:
        train_start = "2024-01-01"
        train_end = "2025-06-30"
        test_start = "2025-07-01"
        test_end = date.today().isoformat()

    prompt = f"""你是一个量化策略专家。用户描述了一个交易策略，请将其转换为 Qlib 回测参数。

用户描述: "{req.description}"

可参考的策略模板:
{templates_desc}

请返回一个 JSON 对象，包含以下字段（使用标准回测参数格式）:
- model: 模型类型 ("lightgbm" 或 "xgboost")
- train_start: 训练开始日期 (建议 {train_start})
- train_end: 训练结束日期 (建议 {train_end})
- test_start: 测试开始日期 (建议 {test_start})
- test_end: 测试结束日期 (建议 {test_end})
- hold_num: 持仓股票数 (1-50)
- turnover: 调仓周期（交易日）
- max_position: 单票最大仓位 (0.01-0.3)
- stop_loss: 止损比例（负数，如 -0.08）
- buy_cost: 买入成本 (0.0003 即万分之三)
- sell_cost: 卖出成本 (0.0003)
- signal_logic: 信号逻辑的 Python 伪代码描述
- interpretation: 对用户策略的解读和实现思路 (中文，100字以内)
- warnings: 需要注意的风险点列表

只返回 JSON，不要包含其他文字。"""

    llm = client.get_deep_llm() if req.use_deep else client.get_quick_llm()
    response = llm.invoke(prompt)
    text = response.content if hasattr(response, "content") else str(response)

    logger.info(f"AI 策略生成: {req.description[:50]}...")

    params = _parse_strategy_params(text)

    if not params:
        return {
            "raw_output": text,
            "params": None,
            "warning": "无法解析 LLM 输出为结构化参数，请查看 raw_output",
        }

    return {
        "params": params,
        "raw_output": None,
    }


@router.post("/analyze")
async def analyze_strategy(req: StrategyAnalyzeRequest):
    """策略分析：LLM 分析当前持仓并给出调整建议"""
    _check_llm_available(req.api_key)

    client = _get_llm_client(req.api_key, req.base_url, req.quick_model, req.deep_model)

    holdings_desc = "\n".join(
        f"- {h.code} ({h.name}): 权重 {h.weight:.1%}"
        + (f", 成本 {h.cost}" if h.cost else "")
        for h in req.holdings
    )

    total_weight = sum(h.weight for h in req.holdings)
    n_stocks = len(req.holdings)

    risk_map = {
        "conservative": "保守型（低风险承受能力，偏好稳定收益）",
        "moderate": "稳健型（中等风险承受能力，追求风险调整后收益）",
        "aggressive": "激进型（高风险承受能力，追求高收益）",
    }

    prompt = f"""你是一个投资组合顾问。请分析以下A股持仓并提供专业建议。

风险偏好: {risk_map.get(req.risk_tolerance, "稳健型")}
总资金: {req.total_capital:,.0f} 元
总仓位: {total_weight:.1%}
持仓数量: {n_stocks} 只

当前持仓:
{holdings_desc}

请从以下角度分析:
1. 持仓结构评估（集中度、行业分布、风险暴露）
2. 调仓建议（增持/减持/清仓哪些，并说明理由）
3. 仓位管理建议（当前仓位是否合理，建议目标仓位）
4. 风险提示（当前持仓的主要风险点）

请以 JSON 格式返回:
{{
  "overall_assessment": "总体评估（1-3句话，中文）",
  "structure_score": 0-100 的结构得分,
  "risk_score": 0-100 的风险得分,
  "suggestions": [
    {{"code": "代码", "action": "add/reduce/close/hold", "target_weight": 0.15, "reason": "理由"}}
  ],
  "target_total_position": 0.7（建议总仓位）,
  "risk_alerts": ["风险点1", "风险点2"],
  "market_opinion": "当前市场环境判断（中文，50字以内）"
}}

只返回 JSON。"""

    llm = client.get_quick_llm()
    response = llm.invoke(prompt)
    text = response.content if hasattr(response, "content") else str(response)

    json_match = re.search(r"\{[\s\S]*\}", text)
    if json_match:
        try:
            result = json.loads(json_match.group(0))
            return {"analysis": result}
        except json.JSONDecodeError:
            pass

    return {"analysis": {"overall_assessment": text[:500], "raw": True}}


@router.post("/optimize")
async def optimize_strategy(req: StrategyOptimizeRequest):
    """AI 驱动参数优化：LLM 提议参数候选 → 返回建议的参数组合

    注: 完整闭环需要与回测引擎集成。当前版本 LLM 基于经验建议参数候选，
    用户可手动将这些参数提交到回测端点进行验证。
    """
    _check_llm_available(req.api_key)

    client = _get_llm_client(req.api_key, req.base_url, req.quick_model, req.deep_model)

    # 找匹配的模板
    template = None
    for t in STRATEGY_TEMPLATES:
        if t["id"] == req.strategy_type.replace(" ", "_").lower():
            template = t
            break

    template_info = ""
    if template:
        template_info = f"\n策略模板默认参数: {json.dumps(template['default_params'], ensure_ascii=False)}"
        if not req.param_ranges:
            req.param_ranges = template["default_params"]

    param_desc = json.dumps(req.param_ranges, ensure_ascii=False) if req.param_ranges else "未指定"

    prompt = f"""你是一个量化策略参数优化专家。

策略类型: {req.strategy_type}{template_info}

用户指定的参数搜索范围: {param_desc}

请基于你的金融市场知识和量化经验，建议 5 组有代表性的参数组合进行测试。

返回 JSON 数组（5个元素），每个元素格式:
{{
  "name": "参数组描述（如'高持仓集中'、'低换手保守'等）",
  "params": {{参数名: 值}},
  "rationale": "选择这组参数的理由（中文，1句话）",
  "expected_characteristics": "预期表现特征（如'高收益高波动'）（中文，1句话）"
}}

只返回 JSON 数组。"""

    llm = client.get_quick_llm()
    response = llm.invoke(prompt)
    text = response.content if hasattr(response, "content") else str(response)

    json_match = re.search(r"\[[\s\S]*\]", text)
    candidates = []
    if json_match:
        try:
            candidates = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    return {
        "strategy_type": req.strategy_type,
        "candidates": candidates,
        "suggestion": (
            "请将上述参数组合分别提交到 /api/backtest/start 进行回测，"
            "比较各项指标后选择最优参数。"
        ),
    }
