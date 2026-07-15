"""Post-close screening workflow API.

This module is intentionally a thin orchestration layer. It combines existing
data-health, hot-sector, ETF, mean-reversion, pair-trading, and risk checks into
one result that the UI can show as a practical post-close shortlist.
"""

from __future__ import annotations

import asyncio
import math
import logging
import json
import sys
import time
from datetime import date, datetime, timedelta
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
from db.screening_history import (
    save_run,
    get_last_n_runs,
    get_recent_runs,
    update_verification,
    get_latest_buyable,
)
from utils.code_normalization import normalize_stock_code

router = APIRouter()
FACTOR_SCORE_BUY_THRESHOLD = 0.5
FACTOR_SCORE_DRAG_THRESHOLD = -0.5
DEFAULT_CANDIDATE_TOP_N = 15  # 盘后选股默认候选数
SCREENING_RISK_CODE_LIMIT = 8  # 风险摘要只取前 N 只（默认关闭，见 include_risk）
CIRCUIT_BREAKER_WIN_RATE = 0.40
CIRCUIT_BREAKER_MIN_PERIODS = 3
CN_DATA_DIR = Path.home() / ".qlib" / "qlib_data" / "cn_data"

# Async task store (same pattern as backtest) — eliminates browser HTTP timeout
from db.task_store import TaskStore

screening_task_store = TaskStore(
    Path.home() / ".qlib" / "screening_run_tasks.db",
    table_name="screening_run_tasks",
)
try:
    screening_task_store.init_db()
except Exception:
    pass

# Last-resort only when no stock-pool history exists
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


def _extract_close_series(prices) -> list[float]:
    """Normalize Qlib D.features output to a list of finite closes."""
    if prices is None or getattr(prices, "empty", True):
        return []
    try:
        if "$close" in prices.columns:
            series = prices["$close"]
        else:
            series = prices.iloc[:, 0]
        # MultiIndex may leave instrument level; dropna and flatten
        values = [float(v) for v in series.dropna().tolist() if float(v) > 0]
        return values
    except Exception:
        return []


def verify_run_t5(run: dict, *, persist: bool = True) -> dict | None:
    """Compute T+5 win_rate and avg_t5_return for one screening history row.

    win_rate and avg_t5_return are ALWAYS separate metrics (never copy wr into return).
    """
    try:
        buyable = json.loads(run.get("top_buyable_json") or "[]")
    except Exception:
        return None
    if not buyable:
        return None

    run_date = str(run.get("run_date") or "")
    if not run_date:
        return None

    try:
        from qlib.data import D

        cal = list(D.calendar(freq="day"))
        cal_str = [str(d)[:10] for d in cal]
        if run_date not in cal_str:
            return None
        idx = cal_str.index(run_date)
        t5_idx = idx + 5
        if t5_idx >= len(cal_str):
            # T+5 not yet available
            return None
        t5_date = cal_str[t5_idx]
    except Exception:
        return None

    wins = 0
    returns: list[float] = []
    stock_results: list[dict] = []
    for stock in buyable:
        code = stock.get("code", "")
        if not code:
            continue
        try:
            try:
                qlib_code = normalize_stock_code(code, target="qlib")
            except Exception:
                qlib_code = code
            prices = D.features([qlib_code], ["$close"], start_time=run_date, end_time=t5_date)
            closes = _extract_close_series(prices)
            if len(closes) < 2:
                continue
            t0, t5 = closes[0], closes[-1]
            if t0 <= 0:
                continue
            ret = t5 / t0 - 1.0
            returns.append(ret)
            if ret > 0:
                wins += 1
            stock_results.append({
                "code": qlib_code,
                "name": stock.get("name"),
                "t5_return": round(ret, 4),
                "hit": ret > 0,
            })
        except Exception:
            continue

    if not returns:
        return None

    wr = wins / len(returns)
    avg_ret = sum(returns) / len(returns)
    if persist:
        update_verification(run_date, wr, avg_ret)
    return {
        "run_date": run_date,
        "win_rate": round(wr, 4),
        "avg_t5_return": round(avg_ret, 4),
        "stocks": len(returns),
        "won": wins,
        "t5_date": t5_date,
        "stock_details": stock_results,
    }


def _check_circuit_breaker(warnings: list[str] | None = None) -> dict:
    """Evaluate rolling 3-period win-rate circuit breaker.

    Prefer already-verified rows in SQLite to avoid re-querying Qlib on every screening run.
    """
    result = {
        "active": False,
        "periods_checked": 0,
        "recent_win_rates": [],
        "recent_avg_t5_returns": [],
        "message": None,
    }
    try:
        runs = get_last_n_runs(n=12, min_age_days=5)
        verified: list[dict] = []
        for run in runs:
            wr = run.get("win_rate_verified")
            avg_ret = run.get("avg_t5_return")
            if wr is not None and avg_ret is not None and run.get("verified_at"):
                verified.append({
                    "run_date": run.get("run_date"),
                    "win_rate": float(wr),
                    "avg_t5_return": float(avg_ret),
                })
            else:
                stats = verify_run_t5(run, persist=True)
                if not stats:
                    continue
                verified.append(stats)
            if len(verified) >= CIRCUIT_BREAKER_MIN_PERIODS:
                break

        result["periods_checked"] = len(verified)
        result["recent_win_rates"] = [v["win_rate"] for v in verified]
        result["recent_avg_t5_returns"] = [v["avg_t5_return"] for v in verified]

        if (
            len(verified) >= CIRCUIT_BREAKER_MIN_PERIODS
            and all(v["win_rate"] < CIRCUIT_BREAKER_WIN_RATE for v in verified[:CIRCUIT_BREAKER_MIN_PERIODS])
        ):
            result["active"] = True
            result["message"] = (
                f"circuit_breaker: rolling_{CIRCUIT_BREAKER_MIN_PERIODS}_period_win_rate_below_"
                f"{int(CIRCUIT_BREAKER_WIN_RATE * 100)}pct"
            )
            if warnings is not None:
                warnings.append(result["message"])
                warnings.append(
                    "策略近3期 T+5 胜率均低于40%，建议暂停新开仓，进入观察期"
                )
    except Exception as e:
        logger.warning(f"Circuit breaker failed: {e}")
        result["error"] = str(e)
    return result


def load_latest_pool_candidates(top_n: int = DEFAULT_CANDIDATE_TOP_N) -> tuple[list[str], dict | None]:
    """Load Top-N codes from the most recent stock-pool refresh history."""
    try:
        from core.stock_pool import _get_db

        conn = _get_db()
        row = conn.execute(
            """
            SELECT h.pool_id, h.date, h.constituents_json, p.name AS pool_name, p.updated_at
            FROM pool_history h
            JOIN pools p ON p.id = h.pool_id
            ORDER BY h.date DESC, p.updated_at DESC
            LIMIT 1
            """
        ).fetchone()
        conn.close()
        if not row:
            return [], None

        constituents = json.loads(row["constituents_json"] or "[]")
        if not isinstance(constituents, list) or not constituents:
            return [], None

        def _sort_key(item: dict):
            rank = item.get("rank")
            score = item.get("score")
            try:
                rank_v = int(rank) if rank is not None else 10_000
            except Exception:
                rank_v = 10_000
            try:
                score_v = -float(score) if score is not None else 0.0
            except Exception:
                score_v = 0.0
            return (rank_v, score_v)

        ordered = sorted(
            [c for c in constituents if isinstance(c, dict) and c.get("code")],
            key=_sort_key,
        )
        codes: list[str] = []
        for item in ordered[: max(int(top_n), 1)]:
            codes.append(str(item["code"]))
        meta = {
            "source": "stock_pool",
            "pool_id": row["pool_id"],
            "pool_name": row["pool_name"],
            "as_of": row["date"],
            "count": len(codes),
            "top_n": top_n,
        }
        return codes, meta
    except Exception as e:
        logger.warning(f"load_latest_pool_candidates failed: {e}")
        return [], None


def resolve_screening_candidates(
    request_candidates: list[str] | None,
    *,
    top_n: int = DEFAULT_CANDIDATE_TOP_N,
    warnings: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Resolve candidate codes: request > stock-pool TopN > hardcoded fallback."""
    if request_candidates:
        meta = {
            "source": "request",
            "count": len(request_candidates),
            "top_n": top_n,
        }
        return list(request_candidates), meta

    codes, meta = load_latest_pool_candidates(top_n=top_n)
    if codes and meta:
        if warnings is not None:
            warnings.append(
                f"候选来自股票池「{meta.get('pool_name')}」Top{len(codes)}"
                f"（刷新日 {meta.get('as_of')}）"
            )
        return codes, meta

    if warnings is not None:
        warnings.append(
            "无股票池历史，回退硬编码候选名单；请先在「智能股票池」刷新一次以启用真实选股"
        )
    return list(DEFAULT_CANDIDATES), {
        "source": "hardcoded_fallback",
        "count": len(DEFAULT_CANDIDATES),
        "top_n": top_n,
    }


class ScreeningRunRequest(BaseModel):
    candidates: list[str] | None = Field(default=None, description="Stock codes to screen")
    include_llm: bool = Field(default=False, description="Reserved for optional heavy LLM review")
    risk_start_date: str | None = Field(default=None, description="Risk window start date")
    risk_end_date: str | None = Field(default=None, description="Risk window end date")
    generated_strategy: dict | None = Field(default=None, description="Optional AI-generated strategy params")
    allow_untrusted_data: bool = Field(
        default=False,
        description="若为 true，数据不可信时仍返回诊断结果，但买入桶仍会被清空",
    )
    candidate_top_n: int = Field(
        default=DEFAULT_CANDIDATE_TOP_N,
        ge=5,
        le=50,
        description="未传 candidates 时，从最新股票池取 TopN",
    )
    include_risk: bool = Field(
        default=False,
        description="是否计算组合风险摘要（较慢，默认关闭以避免超时）",
    )
    include_pairs: bool = Field(
        default=False,
        description="是否拉取配对信号（较慢，默认关闭）",
    )
    async_mode: bool = Field(
        default=True,
        description="异步任务模式：立即返回 task_id，前端轮询 /status（推荐，避免超时）",
    )


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


def _code_to_feature_dir(code: str) -> str:
    c = str(code).strip()
    if "." in c:  # 600519.SS
        try:
            return normalize_stock_code(c, target="qlib").lower()
        except Exception:
            pass
    return c.lower()


def _read_recent_closes_from_bin(code: str, lookback: int = 60) -> list[float] | None:
    """Read recent close prices directly from Qlib bin — no D.features / joblib.

    This avoids Windows joblib spawn hang that made screening exceed 90s.
    """
    import numpy as np

    feature_name = _code_to_feature_dir(code)
    bin_path = CN_DATA_DIR / "features" / feature_name / "close.day.bin"
    if not bin_path.exists():
        # try uppercase qlib form folder variants
        alt = feature_name
        if feature_name.startswith("sh") or feature_name.startswith("sz"):
            pass
        bin_path = CN_DATA_DIR / "features" / alt / "close.day.bin"
        if not bin_path.exists():
            return None
    try:
        raw = np.fromfile(str(bin_path), dtype="<f")
        if len(raw) < 3:
            return None
        vals = raw[1:]
        valid = vals[np.isfinite(vals) & (vals > 0)]
        if len(valid) < 20:
            return None
        return [float(x) for x in valid[-lookback:]]
    except Exception:
        return None


def _signal_from_closes(
    code: str,
    closes: list[float],
    *,
    rsi_threshold: int = 70,
    bollinger_period: int = 20,
) -> dict | None:
    import pandas as pd
    from api.mean_reversion import calc_rsi, calc_bollinger_bands, get_stock_name

    if len(closes) < max(bollinger_period, 15):
        return None
    prices = pd.Series(closes)
    rsi = calc_rsi(prices)
    bb = calc_bollinger_bands(prices, bollinger_period)
    current_rsi = float(rsi.iloc[-1])
    bb_pos = float(bb["position"].iloc[-1])
    if not math.isfinite(current_rsi):
        current_rsi = 50.0
    if not math.isfinite(bb_pos):
        bb_pos = 0.5

    is_overbought_rsi = current_rsi > rsi_threshold
    is_oversold_rsi = current_rsi < (100 - rsi_threshold)
    is_overbought_bb = bb_pos > 0.8
    is_oversold_bb = bb_pos < 0.2
    if is_overbought_rsi and is_overbought_bb:
        signal, strength = "超买", "强"
    elif is_oversold_rsi and is_oversold_bb:
        signal, strength = "超卖", "强"
    elif is_overbought_rsi or is_overbought_bb:
        signal, strength = "超买", "中"
    elif is_oversold_rsi or is_oversold_bb:
        signal, strength = "超卖", "中"
    else:
        signal, strength = "关注", "弱"

    last = float(prices.iloc[-1])
    prev = float(prices.iloc[-2]) if len(prices) >= 2 else last
    change_pct = ((last / prev) - 1.0) * 100 if prev > 0 else 0.0
    try:
        from core.price_adjust import to_forward_price
        display_price = float(to_forward_price(last, code))
    except Exception:
        display_price = last

    return {
        "code": code,
        "name": get_stock_name(code),
        "rsi": round(current_rsi, 1),
        "bollingerPosition": round(bb_pos, 2),
        "signal": signal,
        "strength": strength,
        "price": round(display_price, 2),
        "change_pct": round(change_pct, 2),
        "rsiThreshold": rsi_threshold,
        "bollingerPeriod": bollinger_period,
        "status": "ok",
        "source": "bin",
    }


def _batch_mean_reversion_signals(
    codes: list[str],
    *,
    rsi_threshold: int = 70,
    bollinger_period: int = 20,
) -> dict[str, dict]:
    """Fast mean-reversion via local close.day.bin (no Qlib Dataset multiprocessing)."""
    if not codes:
        return {}
    out: dict[str, dict] = {}
    for raw in list(dict.fromkeys(codes)):
        try:
            code = normalize_stock_code(raw, target="qlib")
        except Exception:
            code = str(raw)
        closes = _read_recent_closes_from_bin(code, lookback=60)
        if not closes:
            continue
        sig = _signal_from_closes(
            code,
            closes,
            rsi_threshold=rsi_threshold,
            bollinger_period=bollinger_period,
        )
        if sig:
            out[code] = sig
    return out


def _collect_candidates_sync(
    codes: list[str],
    warnings: list[str],
    factor_scores: dict[str, dict] | None = None,
) -> list[dict]:
    """Sync candidate build (safe for background thread)."""
    t0 = time.perf_counter()
    signal_map = _batch_mean_reversion_signals(codes)
    elapsed = time.perf_counter() - t0
    logger.info(f"screening bin mean-reversion: {len(signal_map)}/{len(codes)} in {elapsed:.2f}s")

    candidates = []
    for raw_code in codes:
        try:
            code = normalize_stock_code(raw_code, target="qlib")
        except Exception:
            code = str(raw_code)
        signal_data = signal_map.get(code)
        if signal_data:
            candidates.append({
                "code": code,
                "name": _resolve_candidate_name(code, signal_data.get("name")),
                "price": signal_data.get("price"),
                "change_pct": signal_data.get("change_pct", 0),
                "mean_reversion": signal_data,
                "agent": {"status": "missing"},
            })
        else:
            warnings.append(f"{code} 均值回归信号暂不可用（本地bin无效）")
            candidates.append({
                "code": code,
                "name": _resolve_candidate_name(code),
                "mean_reversion": {"status": "unavailable"},
                "agent": {"status": "missing"},
                "warning": "mean_reversion_unavailable",
            })
    return attach_factor_scores_to_candidates(candidates, factor_scores)


async def _collect_candidates(codes: list[str], warnings: list[str], factor_scores: dict[str, dict] | None = None) -> list[dict]:
    return await asyncio.to_thread(_collect_candidates_sync, codes, warnings, factor_scores)


async def _collect_risk_summary(codes: list[str], start_date: str | None, end_date: str | None, warnings: list[str]) -> dict:
    try:
        from .risk import analyze_risk

        limited = codes[:SCREENING_RISK_CODE_LIMIT]
        if len(codes) > SCREENING_RISK_CODE_LIMIT:
            warnings.append(
                f"风险摘要仅用前{SCREENING_RISK_CODE_LIMIT}只候选加速计算（共{len(codes)}只）"
            )
        if not limited:
            return {"status": "unavailable", "message": "no_codes"}

        if not start_date:
            start_date = (date.today() - timedelta(days=120)).isoformat()
        request = RiskAnalysisRequest(codes=limited, start_date=start_date, end_date=end_date)
        # Risk can hang on external fallback; bound wait
        response = await asyncio.wait_for(analyze_risk(request), timeout=25.0)
        data = _json_safe(response)
        metrics = data.get("metrics", {})
        return {
            "codes": data.get("codes", []),
            "start_date": data.get("start_date"),
            "end_date": data.get("end_date"),
            "metrics": metrics,
            "position_sizing": data.get("position_sizing", {}),
        }
    except asyncio.TimeoutError:
        logger.warning("Screening risk summary timed out after 25s")
        warnings.append("组合风险分析超时（25s），已跳过")
        return {"status": "timeout", "error": "risk_timeout_25s"}
    except Exception as exc:
        logger.warning(f"Screening risk summary failed: {exc}")
        warnings.append(f"组合风险分析失败：{exc}")
        return {"status": "unavailable", "error": str(exc)}


async def _timed(coro, timeout_s: float, default, warnings: list[str], label: str):
    try:
        return await asyncio.wait_for(coro, timeout=timeout_s)
    except asyncio.TimeoutError:
        warnings.append(f"{label}超时（{timeout_s:.0f}s），已跳过")
        return default
    except Exception as e:
        warnings.append(f"{label}失败：{e}")
        return default


async def execute_screening_workflow(request: ScreeningRunRequest) -> dict:
    """Core screening logic (used by sync and async runners)."""
    warnings: list[str] = []
    run_t0 = time.perf_counter()

    trust_report = None
    try:
        from core.data_trust import evaluate_data_trust

        # Smaller sample for speed on cold cache; cache hit is instant
        trust_report = evaluate_data_trust(max_sample=120)
        if not trust_report.get("trusted"):
            warnings.append(f"DATA_UNTRUSTED: {trust_report.get('message')}")
            if not request.allow_untrusted_data:
                warnings.append("data_trust: buyable signals will be cleared")
    except Exception as exc:
        warnings.append(f"data_trust 评估失败：{exc}")

    raw_candidates, candidate_source = resolve_screening_candidates(
        request.candidates,
        top_n=request.candidate_top_n,
        warnings=warnings,
    )
    codes: list[str] = []
    for raw_code in raw_candidates:
        try:
            codes.append(normalize_stock_code(raw_code, target="qlib"))
        except Exception as exc:
            warnings.append(f"股票代码格式不支持：{raw_code}（{exc}）")

    health_w: list[str] = []
    hot_w: list[str] = []
    etf_w: list[str] = []
    pair_w: list[str] = []

    # Bound each side-channel; pair/risk are optional (slow)
    coros = [
        _timed(_collect_data_health(health_w), 12.0, {"overall_status": "unknown"}, warnings, "数据健康"),
        _timed(_collect_hot_sectors(hot_w), 10.0, [], warnings, "热点板块"),
        _timed(_collect_etf_signals(etf_w), 10.0, [], warnings, "ETF信号"),
    ]
    if request.include_pairs:
        coros.append(_timed(_collect_pair_signals(pair_w), 8.0, [], warnings, "配对信号"))

    gathered = await asyncio.gather(*coros)
    data_health = gathered[0]
    hot_sectors = gathered[1]
    etf_signals = gathered[2]
    pair_signals = gathered[3] if request.include_pairs else []
    for part in (health_w, hot_w, etf_w, pair_w):
        warnings.extend(part)

    factor_result, factor_task = _load_latest_completed_factor_result(warnings)
    factor_summary = summarize_factor_analysis_result(factor_result, factor_task)
    factor_scores = _compute_candidate_factor_scores(codes, factor_summary, warnings)

    # Candidates from local bins (fast, no joblib)
    cand_w: list[str] = []
    candidates = await _collect_candidates(codes, cand_w, factor_scores)
    warnings.extend(cand_w)

    risk_summary: dict = {"status": "skipped", "message": "include_risk=false"}
    if request.include_risk:
        risk_w: list[str] = []
        risk_summary = await _timed(
            _collect_risk_summary(codes, request.risk_start_date, request.risk_end_date, risk_w),
            15.0,
            {"status": "timeout"},
            warnings,
            "组合风险",
        )
        warnings.extend(risk_w)

    try:
        from .ai_strategy import attach_ai_strategy_scores_to_candidates, summarize_ai_strategy_scores

        candidates = attach_ai_strategy_scores_to_candidates(candidates)
        candidates = attach_generated_strategy_fit(candidates, request.generated_strategy)
        ai_strategy_summary = summarize_ai_strategy_scores(candidates)
    except Exception as exc:
        logger.warning(f"Screening AI strategy scoring failed: {exc}")
        warnings.append(f"AI策略联动评分失败：{exc}")
        ai_strategy_summary = {"status": "unavailable", "error": str(exc)}

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
    result["candidate_source"] = candidate_source

    if trust_report is not None:
        result["data_trust"] = {
            "trusted": trust_report.get("trusted"),
            "status": trust_report.get("status"),
            "metrics": trust_report.get("metrics"),
            "reasons": trust_report.get("reasons"),
            "checked_at": trust_report.get("checked_at"),
        }
        result["trading_allowed"] = bool(trust_report.get("trading_allowed"))
        if not trust_report.get("trusted"):
            from core.data_trust import apply_untrusted_screening_block

            result = apply_untrusted_screening_block(result, trust_report)

    try:
        buyable = (result.get("buckets") or {}).get("buyable", [])
        if buyable and (trust_report is None or trust_report.get("trusted")):
            top5 = sorted(
                buyable,
                key=lambda x: (
                    float(x.get("score") or 0),
                    float((x.get("factor_signal") or {}).get("score") or 0),
                ),
                reverse=True,
            )[:5]
            top5_min = [
                {
                    "code": s.get("code"),
                    "name": s.get("name"),
                    "score": s.get("score"),
                    "reason": s.get("reason"),
                    "bucket": s.get("bucket"),
                }
                for s in top5
            ]
            save_run(date.today().isoformat(), top5_min, candidate_source=candidate_source)
            result["saved_buyable_top5"] = top5_min
    except Exception as e:
        logger.warning(f"History save failed: {e}")

    breaker = _check_circuit_breaker(warnings)
    result["circuit_breaker"] = breaker
    if breaker.get("active"):
        buckets = dict(result.get("buckets") or {})
        buyable = list(buckets.get("buyable") or [])
        watch = list(buckets.get("watch_only") or [])
        for item in buyable:
            moved = dict(item)
            moved["action"] = "降级"
            moved["bucket"] = "watch_only"
            moved["reason"] = "熔断：近3期推荐 T+5 胜率过低，暂停新开仓"
            watch.append(moved)
        buckets["buyable"] = []
        buckets["watch_only"] = watch
        result["buckets"] = buckets
        result["trading_allowed"] = False
        new_candidates = []
        for c in result.get("candidates") or []:
            row = dict(c)
            if row.get("bucket") == "buyable":
                row["bucket"] = "watch_only"
                row["action"] = "降级"
                row["reason"] = "熔断：近3期推荐 T+5 胜率过低，暂停新开仓"
            new_candidates.append(row)
        result["candidates"] = new_candidates

    if warnings:
        existing = result.get("warnings") or []
        result["warnings"] = existing + [w for w in warnings if w not in existing]

    result["timing"] = {
        "total_seconds": round(time.perf_counter() - run_t0, 2),
        "candidate_count": len(codes),
    }
    logger.info(
        f"screening execute done in {result['timing']['total_seconds']}s "
        f"candidates={len(codes)} source={candidate_source.get('source')}"
    )
    return result


def _run_screening_task(task_id: str, request_data: dict) -> None:
    """Background worker for async screening."""
    try:
        screening_task_store.update_progress(task_id, 15)
        request = ScreeningRunRequest(**(request_data or {}))
        # Run async core in a fresh event loop inside the worker thread
        result = asyncio.run(execute_screening_workflow(request))
        screening_task_store.set_completed(task_id, json.dumps(result, ensure_ascii=False, default=str))
        logger.info(f"screening task {task_id} completed")
    except Exception as e:
        logger.exception(f"screening task {task_id} failed: {e}")
        screening_task_store.set_failed(task_id, str(e))


@router.post("/run")
async def run_screening_workflow(request: ScreeningRunRequest | None = None):
    """Run post-close screening.

    Default async_mode=true: returns {task_id, status:running} immediately.
    Poll GET /api/screening/status/{task_id} until completed.
    Set async_mode=false for legacy one-shot (may still time out in browser).
    """
    import uuid
    import threading

    request = request or ScreeningRunRequest()

    if not request.async_mode:
        return await execute_screening_workflow(request)

    task_id = str(uuid.uuid4())
    try:
        screening_task_store.init_db()
        screening_task_store.create_task(
            task_id,
            json.dumps(request.model_dump(), ensure_ascii=False, default=str),
        )
    except Exception as e:
        logger.error(f"create screening task failed: {e}")
        raise HTTPException(status_code=500, detail=f"创建筛选任务失败: {e}")

    thread = threading.Thread(
        target=_run_screening_task,
        args=(task_id, request.model_dump(mode="json")),
        name=f"screening-{task_id[:8]}",
        daemon=True,
    )
    thread.start()

    return {
        "task_id": task_id,
        "status": "running",
        "progress": 5,
        "message": "盘后选股任务已启动，请轮询 /api/screening/status/{task_id}",
        "async": True,
    }


@router.get("/status/{task_id}")
async def get_screening_task_status(task_id: str):
    """Poll async screening task status."""
    task = screening_task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    status = task.get("status") or "unknown"
    progress = int(task.get("progress") or 0)
    base = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "error": task.get("error"),
    }
    if status == "completed" and task.get("result_json"):
        try:
            result = json.loads(task["result_json"])
        except Exception:
            result = {}
        # Flatten result fields for frontend convenience + keep wrapper
        if isinstance(result, dict):
            return {**result, **base, "result": result}
        return {**base, "result": result}
    if status == "failed":
        return base
    return base


@router.get("/report")
async def get_screening_report():
    """Rolling T+5 verification report for saved buyable recommendations."""
    try:
        import numpy as np

        runs = get_recent_runs(limit=20)
        if not runs:
            return {"status": "unavailable", "message": "no_screening_history"}

        period_results = []
        all_winrates = []
        all_returns = []
        # Oldest-first for chronological rolling stats in recent_3
        for run in reversed(runs):
            stats = verify_run_t5(run, persist=True)
            if not stats:
                continue
            all_winrates.append(stats["win_rate"])
            all_returns.append(stats["avg_t5_return"])
            period_results.append(stats)

        if not period_results:
            return {
                "status": "insufficient_data",
                "message": "not_enough_history_or_t5_not_ready",
                "total_runs": len(runs),
            }

        rolling_20_wr = round(float(np.mean(all_winrates)) if all_winrates else 0, 4)
        rolling_20_avg_ret = round(float(np.mean(all_returns)) if all_returns else 0, 4)
        recent_3_wr = all_winrates[-3:] if len(all_winrates) >= 3 else all_winrates
        recent_3_ret = all_returns[-3:] if len(all_returns) >= 3 else all_returns
        recent_3_avg_wr = round(float(np.mean(recent_3_wr)) if recent_3_wr else 0, 4)
        recent_3_avg_ret = round(float(np.mean(recent_3_ret)) if recent_3_ret else 0, 4)
        cb_active = (
            len(recent_3_wr) >= CIRCUIT_BREAKER_MIN_PERIODS
            and all(w < CIRCUIT_BREAKER_WIN_RATE for w in recent_3_wr)
        )

        return {
            "status": "available",
            "total_runs": len(runs),
            "periods_with_data": len(period_results),
            "rolling_20_win_rate": rolling_20_wr,
            "rolling_20_avg_t5_return": rolling_20_avg_ret,
            "recent_3_win_rate": recent_3_avg_wr,
            "recent_3_avg_t5_return": recent_3_avg_ret,
            "circuit_breaker_active": cb_active,
            "suggestion": (
                "defensive" if cb_active else ("normal" if rolling_20_wr >= 0.5 else "cautious")
            ),
            "period_details": list(reversed(period_results)),  # newest first for UI
        }
    except Exception as e:
        logger.error(f"Report failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
