"""Post-close screening workflow API.

This module is intentionally a thin orchestration layer. It combines existing
data-health, hot-sector, ETF, mean-reversion, pair-trading, and risk checks into
one result that the UI can show as a practical post-close shortlist.
"""

from __future__ import annotations

import math
import logging
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from loguru import logger
except ModuleNotFoundError:
    logger = logging.getLogger(__name__)

backend_dir = str(Path(__file__).resolve().parents[1])
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from models.schemas import RiskAnalysisRequest
from db.screening_history import save_run, get_last_n_runs, get_recent_runs, update_verification
from utils.code_normalization import normalize_stock_code



def _check_circuit_breaker(warnings):
    try:
        import json, numpy as np, qlib
        from qlib.data import D
        runs = get_last_n_runs(n=3, min_age_days=5)
        if len(runs) < 3:
            return
        all_winrates = []
        for run in runs:
            buyable = json.loads(run["top_buyable_json"])
            if not buyable:
                continue
            run_date = run["run_date"]
            try:
                cal = list(D.calendar(freq="day"))
                cal_str = [str(d)[:10] for d in cal]
                if run_date not in cal_str:
                    continue
                idx = cal_str.index(run_date)
                t5_idx = min(idx + 5, len(cal_str) - 1)
                t5_date = cal_str[t5_idx]
                if t5_date == run_date:
                    continue
            except Exception:
                continue
            wins = 0
            total = 0
            for stock in buyable:
                code = stock.get("code", "")
                if not code:
                    continue
                try:
                    prices = D.features([code], ["$close"], start_time=run_date, end_time=t5_date)
                    if prices is None or prices.empty:
                        continue
                    cs = prices["$close"]
                    if len(cs) < 2:
                        continue
                    t0 = float(cs.iloc[0])
                    t5 = float(cs.iloc[-1])
                    if t0 <= 0:
                        continue
                    total += 1
                    if (t5 / t0 - 1) > 0:
                        wins += 1
                except Exception:
                    continue
            if total == 0:
                continue
            wr = wins / total
            all_winrates.append(wr)
            update_verification(run_date, wr, wr)
        if len(all_winrates) >= 3 and all(w < 0.4 for w in all_winrates):
            warnings.append("circuit_breaker: rolling_3_period_win_rate_below_40pct")
    except Exception as e:
        logger.warning(f"Circuit breaker failed: {e}")

router = APIRouter()
FACTOR_SCORE_BUY_THRESHOLD = 0.5
FACTOR_SCORE_DRAG_THRESHOLD = -0.5


DEFAULT_CANDIDATES = [
    "002156",
    "600487",
    "600522",
    "300196",
    "600584",
    "600176",
    "002080",
]

DEFAULT_CANDIDATE_NAMES = {
    "SZ002156": "通富微电",
    "SH600487": "亨通光电",
    "SH600522": "中天科技",
    "SZ300196": "长海股份",
    "SH600584": "长电科技",
    "SH600176": "中国巨石",
    "SZ002080": "中材科技",
}


class ScreeningRunRequest(BaseModel):
    candidates: list[str] | None = Field(default=None, description="Stock codes to screen")
    include_llm: bool = Field(default=False, description="Reserved for optional heavy LLM review")
    risk_start_date: str | None = Field(default=None, description="Risk window start date")
    risk_end_date: str | None = Field(default=None, description="Risk window end date")
    generated_strategy: dict | None = Field(default=None, description="Optional AI-generated strategy params")


def _json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _json_safe(value.model_dump())
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (date,)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _resolve_candidate_name(code: str, source_name: str | None = None) -> str:
    """Prefer known Chinese names for default candidates, then use source names."""
    normalized = normalize_stock_code(code, target="qlib")
    fallback_name = DEFAULT_CANDIDATE_NAMES.get(normalized)
    if fallback_name:
        return fallback_name

    name = str(source_name or "").strip()
    plain_code = normalize_stock_code(normalized, target="plain")
    if name and normalized not in name and plain_code not in name:
        return name
    return name or normalized


def summarize_factor_analysis_result(result: dict | None, task: dict | None = None, top_n: int = 10) -> dict:
    """Summarize the latest completed factor-analysis task for screening."""
    if not result:
        return {"status": "unavailable", "message": "暂无已完成的因子分析结果"}

    factors = result.get("factors") or []
    factors_sorted = sorted(
        factors,
        key=lambda item: abs(_safe_float(item.get("ic"))),
        reverse=True,
    )
    top_factors = [
        {
            "factor": item.get("factor"),
            "ic": _safe_float(item.get("ic")),
            "rank_ic": _safe_float(item.get("rank_ic")),
            "icir": _safe_float(item.get("icir")),
            "category": item.get("category"),
        }
        for item in factors_sorted[:top_n]
        if item.get("factor")
    ]
    avg_abs_ic = (
        sum(abs(_safe_float(item.get("ic"))) for item in factors) / len(factors)
        if factors
        else 0.0
    )
    summary = result.get("summary") or {}
    best = top_factors[0] if top_factors else {}
    label_available_until = summary.get("label_available_until") or result.get("label_available_until")
    is_leak_safe_for_screening = bool(label_available_until)
    return _json_safe({
        "status": "available",
        "task_id": (task or {}).get("task_id"),
        "updated_at": (task or {}).get("updated_at"),
        "start_date": result.get("start_date"),
        "end_date": result.get("end_date"),
        "predict_period": result.get("predict_period"),
        "label_available_until": label_available_until,
        "signal_as_of": summary.get("signal_as_of") or result.get("end_date"),
        "is_leak_safe_for_screening": is_leak_safe_for_screening,
        "neutralized": summary.get("neutralized"),
        "neutralize_method": summary.get("neutralize_method"),
        "factor_count": len(factors),
        "effective_factors": summary.get("effective_factors"),
        "positive_factors": summary.get("positive_factors"),
        "negative_factors": summary.get("negative_factors"),
        "avg_abs_ic": round(avg_abs_ic, 4),
        "best_factor": best.get("factor"),
        "best_ic": best.get("ic"),
        "top_factors": top_factors,
    })


def attach_factor_scores_to_candidates(candidates: list[dict], factor_scores: dict[str, dict] | None) -> list[dict]:
    """Attach composite factor scores to candidates by normalized code."""
    if not factor_scores:
        return candidates

    enriched = []
    for candidate in candidates:
        item = dict(candidate)
        try:
            code = normalize_stock_code(item.get("code"), target="qlib")
        except Exception:
            code = str(item.get("code") or "")
        signal = factor_scores.get(code)
        if signal:
            item["factor_signal"] = _json_safe({
                **signal,
                "source": signal.get("source") or "latest_factor_analysis",
            })
        enriched.append(item)
    return enriched


def attach_generated_strategy_fit(candidates: list[dict], generated_strategy: dict | None) -> list[dict]:
    """Attach deterministic fit notes from an AI-generated strategy."""
    if not generated_strategy:
        return candidates

    raw_params = generated_strategy.get("params") if isinstance(generated_strategy.get("params"), dict) else generated_strategy
    params = raw_params if isinstance(raw_params, dict) else {}
    hold_num = int(_safe_float(params.get("hold_num"), len(candidates)))
    hold_num = max(1, min(hold_num, len(candidates) or 1))

    def rank_score(candidate: dict) -> float:
        ai_strategy = candidate.get("ai_strategy") or {}
        factor_signal = candidate.get("factor_signal") or {}
        return (
            _safe_float(ai_strategy.get("score"))
            + _safe_float(factor_signal.get("score")) * 10
            + max(min(_safe_float(candidate.get("change_pct")), 6), -6)
        )

    selected = {
        normalize_stock_code(item.get("code"), target="qlib")
        for item in sorted(candidates, key=rank_score, reverse=True)[:hold_num]
    }

    enriched = []
    for candidate in candidates:
        item = dict(candidate)
        code = normalize_stock_code(item.get("code"), target="qlib")
        is_selected = code in selected
        item["generated_strategy"] = {
            "status": "included",
            "fit": "selected" if is_selected else "watch",
            "hold_num": hold_num,
            "reason": "进入AI生成策略候选排名" if is_selected else "未进入AI生成策略优先候选",
        }
        enriched.append(item)
    return enriched


def _load_latest_completed_factor_result(warnings: list[str]) -> tuple[dict, dict | None]:
    """Read the latest completed factor-analysis task from the task store."""
    try:
        from .factors import factor_task_store

        factor_task_store.init_db()
        for task in factor_task_store.list_tasks(limit=20):
            if task.get("status") != "completed":
                continue
            full_task = factor_task_store.get_task(task["task_id"]) or task
            result_json = full_task.get("result_json")
            if not result_json:
                continue
            return json.loads(result_json), full_task
        return {}, None
    except Exception as exc:
        logger.warning(f"Screening factor result load failed: {exc}")
        warnings.append(f"因子分析结果读取失败：{exc}")
        return {}, None


def _compute_candidate_factor_scores(codes: list[str], factor_summary: dict, warnings: list[str]) -> dict[str, dict]:
    """Compute candidate-relative composite factor scores from latest top factors."""
    if factor_summary.get("status") != "available":
        return {}
    if not factor_summary.get("is_leak_safe_for_screening"):
        warnings.append("最新因子分析缺少前向收益标签可用日期，已跳过自动因子打分以避免未来函数风险。")
        return {}

    top_factors = [item for item in factor_summary.get("top_factors", []) if item.get("factor")]
    if not top_factors:
        return {}

    try:
        import pandas as pd
        import numpy as np
        import qlib
        from qlib.utils import init_instance_by_config
        from core.compat import fix_parallel_ext

        qlib.config.N_PROC = 1
        fix_parallel_ext()

        normalized_codes = [normalize_stock_code(code, target="qlib") for code in codes]
        start_date = factor_summary.get("start_date")
        end_date = factor_summary.get("end_date")
        if not start_date or not end_date:
            return {}

        dataset = init_instance_by_config({
            "class": "DatasetH",
            "module_path": "qlib.data.dataset",
            "kwargs": {
                "handler": {
                    "class": "Alpha158",
                    "module_path": "qlib.contrib.data.handler",
                    "kwargs": {
                        "start_time": start_date,
                        "end_time": end_date,
                        "fit_start_time": start_date,
                        "fit_end_time": end_date,
                        "instruments": normalized_codes,
                    },
                },
                "segments": {"test": (start_date, end_date)},
            },
        })

        df_features = dataset.prepare("test", col_set="feature")
        if df_features is None or df_features.empty:
            handler = dataset.handler
            df_features = handler.fetch(col_set="feature")
        if df_features is None or df_features.empty:
            return {}

        dates = sorted(df_features.index.get_level_values("datetime").unique())
        if not dates:
            return {}
        last_date = dates[-1]
        day_features = df_features.xs(last_date, level="datetime")

        total_weight = sum(abs(_safe_float(item.get("ic"))) for item in top_factors) or 1.0
        composite = {code: 0.0 for code in normalized_codes}
        matched = {code: 0 for code in normalized_codes}

        for item in top_factors:
            factor = item.get("factor")
            if factor not in day_features.columns:
                continue

            values = pd.to_numeric(day_features[factor], errors="coerce").reindex(normalized_codes)
            values = values.replace([np.inf, -np.inf], np.nan)
            if values.dropna().shape[0] < 2:
                continue

            std = float(values.std() or 0)
            if std == 0:
                continue

            zscores = (values - float(values.mean())) / std
            direction = 1 if _safe_float(item.get("ic")) >= 0 else -1
            weight = abs(_safe_float(item.get("ic"))) / total_weight
            for code in normalized_codes:
                value = zscores.get(code)
                if pd.notna(value):
                    composite[code] += float(value) * direction * weight
                    matched[code] += 1

        ranked = sorted(composite.items(), key=lambda pair: pair[1], reverse=True)
        result = {}
        for rank, (code, score) in enumerate(ranked, start=1):
            if matched.get(code, 0) == 0:
                continue
            result[code] = {
                "score": round(float(score), 4),
                "rank": rank,
                "matched_factors": matched[code],
                "top_factor_count": len(top_factors),
                "as_of": str(last_date),
                "source": "latest_factor_analysis",
            }
        return result
    except Exception as exc:
        logger.warning(f"Screening factor scoring failed: {exc}")
        warnings.append(f"复合因子评分计算失败：{exc}")
        return {}


def classify_candidate(candidate: dict) -> dict:
    """Classify one candidate into a user-facing action bucket."""
    mean_reversion = candidate.get("mean_reversion") or {}
    agent = candidate.get("agent") or {}
    signal = str(mean_reversion.get("signal") or "")
    strength = str(mean_reversion.get("strength") or "")
    rating = str(agent.get("rating") or "")
    agent_status = str(agent.get("status") or "missing")

    rsi = _safe_float(mean_reversion.get("rsi"))
    bollinger_position = _safe_float(mean_reversion.get("bollingerPosition"), 0.5)
    change_pct = _safe_float(candidate.get("change_pct"))
    factor_signal = candidate.get("factor_signal") or {}
    has_factor_signal = "score" in factor_signal
    factor_score = _safe_float(factor_signal.get("score"))
    factor_rank = int(_safe_float(factor_signal.get("rank"), 999))
    factor_supported = has_factor_signal and factor_score >= FACTOR_SCORE_BUY_THRESHOLD and factor_rank <= 5
    factor_drag = has_factor_signal and factor_score <= FACTOR_SCORE_DRAG_THRESHOLD
    ai_strategy = candidate.get("ai_strategy") or {}
    ai_status = str(ai_strategy.get("status") or "missing")
    ai_score = _safe_float(ai_strategy.get("score"))
    ai_recommendation = str(ai_strategy.get("recommendation") or "")
    ai_supported = ai_status == "available" and ai_score >= 65 and ai_recommendation == "buyable"
    ai_wait = ai_status == "available" and ai_score >= 55 and ai_recommendation in {"wait", "buyable"}
    ai_drag = ai_status == "available" and (ai_score <= 35 or ai_recommendation == "avoid")
    generated_strategy = candidate.get("generated_strategy") or {}
    generated_supported = (
        str(generated_strategy.get("fit") or "") == "selected"
        and ai_status == "available"
        and ai_score >= 60
    )

    is_overbought = "超买" in signal or rsi >= 70 or bollinger_position >= 0.8
    is_extreme_overbought = rsi >= 85 or bollinger_position >= 1.05
    is_oversold = "超卖" in signal or rsi <= 35 or bollinger_position <= 0.2
    is_watch_signal = "关注" in signal
    has_agent_confirmation = agent_status == "completed" and any(word in rating for word in ["买入", "增持", "保留"])
    is_limit_like = change_pct >= 9.5

    if is_limit_like and not has_agent_confirmation:
        action = "降级"
        bucket = "watch_only"
        reason = "涨幅过大且缺少智能体确认，避免追高。"
    elif is_extreme_overbought:
        action = "降级"
        bucket = "watch_only"
        reason = "极端超买区间，短线追买性价比不足。"
    elif has_agent_confirmation and is_overbought:
        action = "保留"
        bucket = "wait_for_pullback"
        reason = f"智能体有正面确认，但均值回归指标显示{signal or '超买'}，等待回调更稳。"
    elif is_overbought:
        action = "等待"
        bucket = "wait_for_pullback"
        reason = f"均值回归指标显示{signal or '超买'}，趋势仍强但当前更适合等回调。"
    elif has_agent_confirmation and not is_overbought:
        action = "保留"
        bucket = "buyable"
        reason = "智能体确认且未处于明显超买区间。"
    elif generated_supported and not is_overbought:
        action = "保留"
        bucket = "buyable"
        reason = f"AI生成策略纳入决策链，候选适配度较高（AI策略分{ai_score:.0f}分），且未处于明显超买区间。"
    elif ai_supported and not is_overbought:
        action = "保留"
        bucket = "buyable"
        reason = f"AI策略联动评分较高（{ai_score:.0f}分），且未处于明显超买区间。"
    elif ai_wait and is_overbought:
        action = "等待"
        bucket = "wait_for_pullback"
        reason = f"AI策略联动评分尚可（{ai_score:.0f}分），但均值回归指标偏热，等待回调。"
    elif factor_supported:
        action = "保留"
        bucket = "buyable"
        reason = f"复合因子评分靠前（第{factor_rank}名，得分{factor_score:.2f}），且未处于明显超买区间。"
    elif is_oversold or is_watch_signal:
        action = "观察"
        bucket = "mean_reversion_watch"
        reason = "均值回归指标处于可观察区间，等待更清晰的修复或回落信号。"
    elif factor_drag:
        action = "观察"
        bucket = "watch_only"
        reason = f"复合因子评分靠后（得分{factor_score:.2f}），暂不进入优先候选。"
    elif ai_drag:
        action = "观察"
        bucket = "watch_only"
        reason = f"AI策略联动评分偏低（{ai_score:.0f}分），暂不进入优先候选。"
    else:
        action = "观察"
        bucket = "watch_only"
        reason = "缺少足够强的买入确认，先放入观察。"

    return {
        **candidate,
        "action": action,
        "bucket": bucket,
        "reason": reason,
    }


def build_screening_summary(
    *,
    data_health: dict,
    hot_sectors: list[dict],
    etf_signals: list[dict],
    pair_signals: list[dict],
    candidates: list[dict],
    risk_summary: dict | None = None,
    factor_summary: dict | None = None,
    ai_strategy_summary: dict | None = None,
    warnings: list[str] | None = None,
    include_llm: bool = False,
) -> dict:
    classified = [classify_candidate(candidate) for candidate in candidates]
    buckets = {
        "buyable": [],
        "wait_for_pullback": [],
        "mean_reversion_watch": [],
        "watch_only": [],
        "excluded": [],
    }
    for candidate in classified:
        buckets.setdefault(candidate["bucket"], []).append(candidate)

    return _json_safe({
        "run_date": date.today().isoformat(),
        "data_health": data_health,
        "hot_sectors": hot_sectors,
        "etf_signals": etf_signals,
        "pair_signals": pair_signals,
        "risk_summary": risk_summary or {},
        "factor_summary": factor_summary or {"status": "unavailable"},
        "ai_strategy_summary": ai_strategy_summary or {"status": "unavailable"},
        "candidates": classified,
        "buckets": buckets,
        "llm_review": {
            "included": include_llm,
            "status": "skipped",
            "message": "默认流程不调用大模型；需要时可在候选池稳定后再做复核。",
        },
        "warnings": warnings or [],
    })


async def _collect_data_health(warnings: list[str]) -> dict:
    try:
        from .data import data_health_check

        health = _json_safe(await data_health_check(include_external=False))
        _append_data_integrity_warnings(health, warnings)
        return health
    except Exception as exc:
        logger.warning(f"Screening data health failed: {exc}")
        warnings.append(f"数据健康检查失败：{exc}")
        return {"overall_status": "unknown", "error": str(exc)}


def _append_data_integrity_warnings(health: dict, warnings: list[str]) -> None:
    """把数据完整性问题转成用户可见 warning，修复完成后自动消失。"""
    if not isinstance(health, dict):
        return
    sources = health.get("sources") or {}
    adjustment = sources.get("price_adjustment") or {}
    factor_status = adjustment.get("factor_field_status")
    if factor_status in {"placeholder_1.0", "mixed_real_and_placeholder", "missing"}:
        warnings.append(
            "数据未完成复权重建（factor 为占位或缺失），回测/信号暂不可作为下单依据"
        )
    stocks = sources.get("stocks") or {}
    if isinstance(stocks, dict) and (
        stocks.get("effective_value_density", 1.0) < 0.8
        or stocks.get("hollow_count", 0) > 0
    ):
        warnings.append(
            "检测到空心股票或日线断层，数据修复完成前请勿按信号实盘下单"
        )


async def _collect_hot_sectors(warnings: list[str]) -> list[dict]:
    try:
        from .hot import get_hot_sectors

        response = await get_hot_sectors(days=10)
        sectors = getattr(response, "sectors", [])
        return _json_safe(sectors[:10])
    except Exception as exc:
        logger.warning(f"Screening hot sectors failed: {exc}")
        warnings.append(f"热点板块读取失败：{exc}")
        return []


async def _collect_etf_signals(warnings: list[str]) -> list[dict]:
    try:
        from .etf import get_etf_signals

        response = await get_etf_signals(days=20)
        etfs = getattr(response, "etfs", [])
        return _json_safe(etfs[:10])
    except Exception as exc:
        logger.warning(f"Screening ETF signals failed: {exc}")
        warnings.append(f"ETF 信号读取失败：{exc}")
        return []


async def _collect_pair_signals(warnings: list[str]) -> list[dict]:
    try:
        from .pair import list_pairs

        response = await list_pairs()
        pairs = response.get("pairs", []) if isinstance(response, dict) else []
        return _json_safe(pairs[:10])
    except Exception as exc:
        logger.warning(f"Screening pair signals failed: {exc}")
        warnings.append(f"配对交易信号读取失败：{exc}")
        return []


async def _collect_candidates(codes: list[str], warnings: list[str], factor_scores: dict[str, dict] | None = None) -> list[dict]:
    from .mean_reversion import get_stock_signal

    candidates = []
    for raw_code in codes:
        try:
            code = normalize_stock_code(raw_code, target="qlib")
            signal = await get_stock_signal(code=code, rsi_threshold=70, bollinger_period=20)
            signal_data = _json_safe(signal)
            candidate = {
                "code": code,
                "name": _resolve_candidate_name(code, signal_data.get("name")),
                "price": signal_data.get("price"),
                "change_pct": signal_data.get("change_pct", 0),
                "mean_reversion": signal_data,
                "agent": {"status": "missing"},
            }
            candidates.append(candidate)
        except Exception as exc:
            logger.warning(f"Screening candidate {raw_code} failed: {exc}")
            warnings.append(f"{raw_code} 均值回归信号读取失败：{exc}")
            try:
                code = normalize_stock_code(raw_code, target="qlib")
            except Exception:
                code = raw_code
            candidates.append({
                "code": code,
                "name": _resolve_candidate_name(code),
                "mean_reversion": {"status": "unavailable"},
                "agent": {"status": "missing"},
                "warning": str(exc),
            })
    return attach_factor_scores_to_candidates(candidates, factor_scores)


async def _collect_risk_summary(codes: list[str], start_date: str | None, end_date: str | None, warnings: list[str]) -> dict:
    try:
        from .risk import analyze_risk

        if not start_date:
            start_date = (date.today() - timedelta(days=120)).isoformat()
        request = RiskAnalysisRequest(codes=codes, start_date=start_date, end_date=end_date)
        response = await analyze_risk(request)
        data = _json_safe(response)
        metrics = data.get("metrics", {})
        return {
            "codes": data.get("codes", []),
            "start_date": data.get("start_date"),
            "end_date": data.get("end_date"),
            "metrics": metrics,
            "position_sizing": data.get("position_sizing", {}),
        }
    except Exception as exc:
        logger.warning(f"Screening risk summary failed: {exc}")
        warnings.append(f"组合风险分析失败：{exc}")
        return {"status": "unavailable", "error": str(exc)}


@router.post("/run")
async def run_screening_workflow(request: ScreeningRunRequest | None = None):
    request = request or ScreeningRunRequest()
    warnings: list[str] = []
    raw_candidates = request.candidates or DEFAULT_CANDIDATES
    codes = []
    for raw_code in raw_candidates:
        try:
            codes.append(normalize_stock_code(raw_code, target="qlib"))
        except Exception as exc:
            warnings.append(f"股票代码格式不支持：{raw_code}（{exc}）")

    data_health = await _collect_data_health(warnings)
    hot_sectors = await _collect_hot_sectors(warnings)
    etf_signals = await _collect_etf_signals(warnings)
    pair_signals = await _collect_pair_signals(warnings)
    factor_result, factor_task = _load_latest_completed_factor_result(warnings)
    factor_summary = summarize_factor_analysis_result(factor_result, factor_task)
    factor_scores = _compute_candidate_factor_scores(codes, factor_summary, warnings)
    candidates = await _collect_candidates(codes, warnings, factor_scores)
    try:
        from .ai_strategy import attach_ai_strategy_scores_to_candidates, summarize_ai_strategy_scores

        candidates = attach_ai_strategy_scores_to_candidates(candidates)
        candidates = attach_generated_strategy_fit(candidates, request.generated_strategy)
        ai_strategy_summary = summarize_ai_strategy_scores(candidates)
    except Exception as exc:
        logger.warning(f"Screening AI strategy scoring failed: {exc}")
        warnings.append(f"AI策略联动评分失败：{exc}")
        ai_strategy_summary = {"status": "unavailable", "error": str(exc)}
    risk_summary = await _collect_risk_summary(
        codes,
        request.risk_start_date,
        request.risk_end_date,
        warnings,
    )

    if request.include_llm:
        warnings.append("已收到 include_llm=true，但第一版工作流暂不自动消耗大模型额度。")

    result = build_screening_summary(
        data_health=data_health,
        hot_sectors=hot_sectors,
        etf_signals=etf_signals,
        pair_signals=pair_signals,
        candidates=candidates,
        risk_summary=risk_summary,
        factor_summary=factor_summary,
        ai_strategy_summary=ai_strategy_summary,
        warnings=warnings,
        include_llm=request.include_llm,
    )

    try:
        import json
        buyable = (result.get("buckets") or {}).get("buyable", [])
        if buyable:
            top5 = sorted(buyable, key=lambda x: x.get("score", 0) or 0, reverse=True)[:5]
            top5_min = [{"code": s.get("code"), "name": s.get("name"), "score": s.get("score")} for s in top5]
            save_run(date.today().isoformat(), top5_min)
    except Exception as e:
        logger.warning(f"History save failed: {e}")

    _check_circuit_breaker(warnings)
    if warnings:
        existing = result.get("warnings") or []
        result["warnings"] = existing + [w for w in warnings if w not in existing]

    return result


@router.get("/report")
async def get_screening_report():
    try:
        import json, numpy as np, qlib
        from qlib.data import D
        runs = get_recent_runs(limit=20)
        if not runs:
            return {"status": "unavailable", "message": "no_screening_history"}

        period_results = []
        all_winrates = []
        all_returns = []
        for run in runs:
            buyable = json.loads(run["top_buyable_json"])
            if not buyable:
                continue
            run_date = run["run_date"]
            try:
                cal = list(D.calendar(freq="day"))
                cal_str = [str(d)[:10] for d in cal]
                if run_date not in cal_str:
                    continue
                idx = cal_str.index(run_date)
                t5_idx = min(idx + 5, len(cal_str) - 1)
                t5_date = cal_str[t5_idx]
                if t5_date == run_date:
                    continue
            except Exception:
                continue
            wins = 0
            total = 0
            returns = []
            stock_results = []
            for stock in buyable:
                code = stock.get("code", "")
                if not code:
                    continue
                try:
                    prices = D.features([code], ["$close"], start_time=run_date, end_time=t5_date)
                    if prices is None or prices.empty:
                        continue
                    cs = prices["$close"]
                    if len(cs) < 2:
                        continue
                    t0 = float(cs.iloc[0])
                    t5 = float(cs.iloc[-1])
                    if t0 <= 0:
                        continue
                    ret = (t5 / t0) - 1
                    total += 1
                    returns.append(ret)
                    if ret > 0:
                        wins += 1
                    stock_results.append({"code": code, "name": stock.get("name"), "t5_return": round(ret, 4), "hit": ret > 0})
                except Exception:
                    continue
            if total == 0:
                continue
            wr = wins / total
            avg_ret = sum(returns) / len(returns)
            all_winrates.append(wr)
            all_returns.append(avg_ret)
            period_results.append({"run_date": run_date, "win_rate": round(wr, 4), "avg_t5_return": round(avg_ret, 4), "stocks": total, "won": wins, "stock_details": stock_results})
            update_verification(run_date, wr, avg_ret)

        if not period_results:
            return {"status": "insufficient_data", "message": "not_enough_history"}

        rolling_20_wr = round(float(np.mean(all_winrates)) if all_winrates else 0, 4)
        rolling_20_avg_ret = round(float(np.mean(all_returns)) if all_returns else 0, 4)
        recent_3_wr = all_winrates[-3:] if len(all_winrates) >= 3 else all_winrates
        recent_3_avg = round(float(np.mean(recent_3_wr)) if recent_3_wr else 0, 4)
        cb_active = len(recent_3_wr) >= 3 and all(w < 0.4 for w in recent_3_wr)

        return {
            "status": "available",
            "total_runs": len(runs),
            "periods_with_data": len(period_results),
            "rolling_20_win_rate": rolling_20_wr,
            "rolling_20_avg_t5_return": rolling_20_avg_ret,
            "recent_3_win_rate": recent_3_avg,
            "circuit_breaker_active": cb_active,
            "suggestion": "defensive" if cb_active else ("normal" if rolling_20_wr >= 0.5 else "cautious"),
            "period_details": period_results,
        }
    except Exception as e:
        logger.error(f"Report failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
