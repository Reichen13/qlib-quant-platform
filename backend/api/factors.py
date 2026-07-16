"""
因子分析 API - 完整 Alpha158 因子体系 (Qlib 原生)
"""

import json
import os
import uuid
import threading
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from typing import Callable, List, Optional
import pandas as pd
import numpy as np
import random
from fastapi import APIRouter, HTTPException
from loguru import logger

from models.schemas import FactorAnalysisRequest, FactorAnalysisResponse, FactorIC
from core.factor_utils import (
    load_industry_mapping,
    neutralize_factor,
    compute_enhanced_ic_stats,
    compute_industry_weighted_ic,
    cluster_factors_by_ic,
)
from core.alpha158_cache import load_cached_features, save_features_cache
from core.compat import force_serial_joblib

def _save_icir_cache(factors_ics: list):
    try:
        import pandas as pd
        cache_dir = Path.home() / ".qlib" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / "factor_icir.parquet"
        df_data = [{"factor": f.factor, "icir": f.icir, "ic": f.ic} for f in factors_ics]
        df = pd.DataFrame(df_data)
        df.to_parquet(cache_path, index=False)
        logger.info(f"ICIR cache saved: {len(df)} factors -> {cache_path}")
    except Exception as e:
        logger.warning(f"ICIR cache save failed: {e}")

from db.task_store import TaskStore

router = APIRouter()
factor_task_store = TaskStore(Path.home() / ".qlib" / "factor_analysis_tasks.db", table_name="factor_analysis_tasks")

# 因子分析在后台线程跑；无心跳超时视为僵尸（Alpha158 生成可能很久，靠心跳续命）
FACTOR_TASK_STALE_MINUTES = 45
FACTOR_TASK_MAX_MINUTES = 90
FACTOR_TASK_HEARTBEAT_SECONDS = 20
INTERRUPTED_FACTOR_ERROR = "因子分析任务已中断：服务重启或后台进程退出，请重新提交分析。"

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

os.environ['NUMBA_NUM_THREADS'] = '1'
os.environ['QLIB_NO_MULTI_PROCESS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['JOBLIB_MULTIPROCESSING'] = '0'
os.environ['LOKY_MAX_CPU_COUNT'] = '1'

# ── 因子类别映射（基于 Alpha158 命名前缀）──
FACTOR_CATEGORIES = {
    "KMID": "K线", "KLEN": "K线", "KMID2": "K线",
    "KUP": "K线", "KUP2": "K线", "KLOW": "K线", "KLOW2": "K线",
    "KSFT": "K线", "KSFT2": "K线",
    "OPEN": "价格", "HIGH": "价格", "LOW": "价格", "VWAP": "价格",
    "ROC": "动量", "MA": "均线", "STD": "波动率",
    "BETA": "Beta", "RSQR": "R²", "RESI": "残差",
    "MAX": "极值", "MIN": "极值", "QTLU": "分位数", "QTLD": "分位数",
    "RANK": "排名", "RSV": "RSV", "IMAX": "极值位置", "IMIN": "极值位置",
    "IMXD": "极值距离", "CORR": "相关性", "CORD": "相关性",
    "CNTP": "计数", "CNTN": "计数", "CNTD": "计数",
    "SUMP": "求和", "SUMN": "求和", "SUMD": "求和",
    "VMA": "成交量均线", "VSTD": "成交量波动", "WVMA": "加权成交量",
    "VSUMP": "成交量求和", "VSUMN": "成交量求和", "VSUMD": "成交量求和",
}


def _get_factor_category(name: str) -> str:
    """根据因子名称前缀推断类别"""
    for prefix, category in FACTOR_CATEGORIES.items():
        if name.startswith(prefix):
            return category
    return "其他"


def _sample_stocks(codes: list, n: int = 150) -> list:
    """随机抽样股票代码，避免样本选择偏差，固定种子保证可复现"""
    random.seed(42)
    return random.sample(codes, min(n, len(codes)))


ProgressCallback = Optional[Callable[[int, str], None]]


def _emit_progress(progress_cb: ProgressCallback, progress: int, message: str = "") -> None:
    if progress_cb is None:
        return
    try:
        progress_cb(int(max(0, min(99, progress))), message)
    except Exception as e:
        logger.debug(f"进度回调失败: {e}")


def _parse_task_time(value: object) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _fail_stale_factor_task(task: dict) -> Optional[dict]:
    """若 running 任务超时/无心跳，标记失败并返回最新 task。"""
    if not task or task.get("status") != "running":
        return task

    now = datetime.now(timezone.utc)
    created = _parse_task_time(task.get("created_at"))
    updated = _parse_task_time(task.get("updated_at")) or created
    task_id = task.get("task_id")
    if not task_id:
        return task

    if created and now - created > timedelta(minutes=FACTOR_TASK_MAX_MINUTES):
        msg = (
            f"因子分析超时（已运行超过 {FACTOR_TASK_MAX_MINUTES} 分钟）。"
            "常见原因：Alpha158 生成卡死或服务曾重启。请缩短日期区间后重试。"
        )
        factor_task_store.set_failed(task_id, msg)
        return factor_task_store.get_task(task_id)

    if updated and now - updated > timedelta(minutes=FACTOR_TASK_STALE_MINUTES):
        factor_task_store.set_failed(task_id, INTERRUPTED_FACTOR_ERROR)
        return factor_task_store.get_task(task_id)

    return task


def _run_factor_analysis(params: FactorAnalysisRequest, progress_cb: ProgressCallback = None):
    """
    因子 IC 分析 - 完整 Alpha158 因子 (Qlib 原生)

    使用 Qlib 的 Alpha158 handler 生成全部 158 个因子，
    然后计算每个因子的 Spearman Rank IC 和 ICIR。
    """
    try:
        import qlib
        from qlib.data import D
        from qlib.utils import init_instance_by_config

        qlib.config.N_PROC = 1
        force_serial_joblib(n_jobs=1)
        _emit_progress(progress_cb, 10, "初始化 Qlib / 串行并行后端")

        start_str = str(params.start_date)
        end_str = str(params.end_date)
        pred_period = params.predict_period

        logger.info(f"Alpha158 因子分析: {start_str}~{end_str}, 预测期={pred_period}天")

        # ── 1. 尝试从缓存加载 Alpha158 特征 ──
        _emit_progress(progress_cb, 15, "检查 Alpha158 特征缓存")
        df_features = load_cached_features(start_str, end_str, "core650")

        if df_features is None:
            # ── 缓存未命中，使用 Qlib 原生 Alpha158 handler 生成 ──
            _emit_progress(progress_cb, 25, "缓存未命中，开始生成 Alpha158（可能数分钟）")
            logger.info("Alpha158 缓存未命中，开始串行生成特征")

            # joblib threading 后端，避免 daemon 线程内 spawn 子进程卡死
            try:
                from joblib import parallel_backend
                backend_cm = parallel_backend("threading", n_jobs=1)
            except Exception:
                from contextlib import nullcontext
                backend_cm = nullcontext()

            with backend_cm:
                dataset = init_instance_by_config({
                    "class": "DatasetH",
                    "module_path": "qlib.data.dataset",
                    "kwargs": {
                        "handler": {
                            "class": "Alpha158",
                            "module_path": "qlib.contrib.data.handler",
                            "kwargs": {
                                "start_time": start_str,
                                "end_time": end_str,
                                "fit_start_time": start_str,
                                "fit_end_time": end_str,
                                "instruments": "core650",
                            },
                        },
                        "segments": {
                            "test": (start_str, end_str),
                        },
                    },
                })

                _emit_progress(progress_cb, 45, "Alpha158 handler 就绪，准备特征矩阵")
                logger.info("Alpha158 数据集构建完成")

                df_features = dataset.prepare("test", col_set="feature")

                # 如果 prepare 不可用，直接从 handler 获取
                if df_features is None or (hasattr(df_features, 'empty') and df_features.empty):
                    handler = dataset.handler
                    df_features = handler.fetch(col_set="feature")

            if df_features is not None and not df_features.empty:
                save_features_cache(df_features, start_str, end_str, "core650")
                _emit_progress(progress_cb, 55, "Alpha158 特征已写入缓存")
        else:
            _emit_progress(progress_cb, 50, "命中 Alpha158 特征缓存")

        if df_features is None or df_features.empty:
            raise HTTPException(status_code=500, detail="Alpha158 因子数据为空")

        logger.info(f"特征数据: {df_features.shape}, 列数: {len(df_features.columns)}")
        _emit_progress(progress_cb, 58, f"特征就绪 shape={df_features.shape}")

        # ── 3. 获取收盘价计算前向收益 ──
        stock_codes = _sample_stocks(df_features.index.get_level_values("instrument").unique().tolist())
        raw_df = D.features(stock_codes, ["$close"], start_time=start_str, end_time=end_str)

        if raw_df is None or raw_df.empty:
            raise HTTPException(status_code=500, detail="无法获取收盘价数据")

        # ── 4. 计算前向收益 ──
        _emit_progress(progress_cb, 62, "计算前向收益")
        dates = sorted(raw_df.index.get_level_values("datetime").unique())
        n_dates = len(dates)

        if n_dates <= pred_period + 5:
            raise HTTPException(
                status_code=400,
                detail=f"交易日不足 ({n_dates} 天)，至少需要 {pred_period + 5} 天"
            )

        # 构建前向收益 Series
        future_returns = {}
        for code in stock_codes:
            try:
                prices = raw_df.xs(code, level="instrument")["$close"].sort_index()
                ret = prices.pct_change(pred_period, fill_method=None).shift(-pred_period)
                for dt, val in ret.items():
                    if not np.isnan(val):
                        future_returns[(code, dt)] = val
            except Exception:
                continue

        fr_series = pd.Series(future_returns, name="future_return")
        fr_series.index = pd.MultiIndex.from_tuples(fr_series.index, names=["instrument", "datetime"])
        label_dates = sorted(fr_series.index.get_level_values("datetime").unique()) if not fr_series.empty else []
        label_available_until = str(label_dates[-1])[:10] if label_dates else None

        # ── 5. 加载行业映射；评估中性化是否真的可做（避免 158 次无效重试）──
        _emit_progress(progress_cb, 68, "加载行业映射")
        all_codes = df_features.index.get_level_values("instrument").unique().tolist()
        industry_map = load_industry_mapping(all_codes)
        valid_ind_count = sum(1 for v in industry_map.values() if v and v != "未知")
        quality_warnings: list[str] = []

        neutralize_method = params.neutralize if params.neutralize and params.neutralize != "none" else None
        market_cap_data = None
        if neutralize_method:
            needs_industry = neutralize_method in ("industry", "industry+market_cap")
            needs_mcap = "market_cap" in neutralize_method
            if needs_industry and valid_ind_count < 10:
                quality_warnings.append(
                    f"行业映射有效仅 {valid_ind_count}/{len(industry_map)}，行业中性化已跳过"
                )
                if neutralize_method == "industry":
                    neutralize_method = None
                elif neutralize_method == "industry+market_cap":
                    neutralize_method = "market_cap"
            if neutralize_method and needs_mcap:
                # 市值只加载一次；逐因子调用 Baostock 会把 70% 卡死数小时
                _emit_progress(progress_cb, 69, "预加载市值（仅一次）")
                from core.factor_utils import _load_market_cap
                dates_all = df_features.index.get_level_values("datetime").unique()
                market_cap_data = _load_market_cap(
                    all_codes,
                    str(dates_all.min())[:10],
                    str(dates_all.max())[:10],
                )
                if not market_cap_data:
                    quality_warnings.append("市值数据不可用，市值中性化已跳过")
                    if neutralize_method == "market_cap":
                        neutralize_method = None
                    elif neutralize_method == "industry+market_cap":
                        neutralize_method = "industry" if valid_ind_count >= 10 else None
            if neutralize_method:
                logger.info(
                    f"启用中性化 method={neutralize_method}, "
                    f"行业有效={valid_ind_count}, 市值股票={len(market_cap_data or {})}"
                )
            else:
                logger.warning("中性化请求已全部跳过（数据不足），按原始因子计算 IC")

        do_industry_contrib = valid_ind_count >= 15
        if not do_industry_contrib:
            quality_warnings.append("行业映射不足，已跳过行业 IC 分解（加速）")

        # ── 6. 计算每个因子的 Spearman Rank IC ──
        from scipy.stats import spearmanr

        factors_ics = []
        feature_names = [str(c) for c in df_features.columns]
        all_daily_ics = {}  # 收集所有因子的 daily IC 用于聚类
        n_features = max(len(feature_names), 1)

        # 计算全部158个因子IC/ICIR,仅前端返回时截断top_k
        for idx, feat_name in enumerate(feature_names):
            try:
                # 每个因子都推进进度，避免长时间停在 70%
                pct = 70 + int(24 * (idx + 1) / n_features)
                if idx == 0 or (idx + 1) % 2 == 0 or idx + 1 == n_features:
                    _emit_progress(progress_cb, pct, f"计算因子 IC {idx + 1}/{n_features}")

                feat_col = df_features[feat_name] if feat_name in df_features.columns else df_features.iloc[:, feature_names.index(feat_name)]

                # ── 可选中性化（市值已预加载）──
                feat_for_ic = feat_col
                if neutralize_method:
                    feat_for_ic = neutralize_factor(
                        feat_col,
                        industry_map,
                        method=neutralize_method,
                        market_cap_data=market_cap_data,
                    )

                # 按日期计算 daily IC（对齐后 groupby，避免双层 xs 过慢）
                daily_ics = []
                try:
                    common_idx = feat_for_ic.index.intersection(fr_series.index)
                    if len(common_idx) >= 15:
                        aligned = pd.DataFrame({
                            "f": feat_for_ic.loc[common_idx].astype(float),
                            "r": fr_series.loc[common_idx].astype(float),
                        }).replace([np.inf, -np.inf], np.nan).dropna()
                        if not aligned.empty:
                            for _, g in aligned.groupby(level="datetime"):
                                if len(g) < 15:
                                    continue
                                fv_vals = g["f"].values
                                fr_vals = g["r"].values
                                if len(fv_vals) < 15:
                                    continue
                                ic, _ = spearmanr(fv_vals, fr_vals)
                                if not np.isnan(ic):
                                    daily_ics.append(float(ic))
                except Exception as e:
                    logger.debug(f"因子 {feat_name} 批量 IC 失败，回退逐日: {e}")
                    test_dates = df_features.index.get_level_values("datetime").unique()
                    for dt in test_dates:
                        try:
                            fv = feat_for_ic.xs(dt, level="datetime").dropna()
                            fr = fr_series.xs(dt, level="datetime").dropna()
                            common = fv.index.intersection(fr.index)
                            if len(common) < 15:
                                continue
                            fv_vals = fv[common].values
                            fr_vals = fr[common].values
                            valid = np.isfinite(fv_vals) & np.isfinite(fr_vals)
                            fv_vals = fv_vals[valid]
                            fr_vals = fr_vals[valid]
                            if len(fv_vals) < 15:
                                continue
                            ic, _ = spearmanr(fv_vals, fr_vals)
                            if not np.isnan(ic):
                                daily_ics.append(ic)
                        except Exception:
                            continue

                if daily_ics:
                    all_daily_ics[feat_name] = daily_ics  # 保存用于聚类
                    mean_ic = np.mean(daily_ics)
                    std_ic = np.std(daily_ics)
                    icir = mean_ic / std_ic if std_ic > 0 else 0

                    # ── 增强 IC 统计 ──
                    enhanced = compute_enhanced_ic_stats(daily_ics)

                    # ── 行业加权 IC（仅在有有效行业时计算）──
                    ind_contrib = None
                    if do_industry_contrib:
                        ind_contrib = compute_industry_weighted_ic(
                            feat_col if neutralize_method != "industry" else feat_for_ic,
                            fr_series, industry_map
                        )

                    factors_ics.append(FactorIC(
                        factor=feat_name,
                        ic=round(float(mean_ic), 4),
                        rank_ic=round(float(mean_ic), 4),
                        icir=round(float(icir), 2),
                        category=_get_factor_category(feat_name),
                        skewness=enhanced.get("skewness"),
                        kurtosis=enhanced.get("kurtosis"),
                        t_statistic=enhanced.get("t_statistic"),
                        p_value=enhanced.get("p_value"),
                        information_ratio=enhanced.get("information_ratio"),
                        ic_autocorr=enhanced.get("ic_autocorr"),
                        industry_contribution=ind_contrib if ind_contrib else None,
                    ))

            except Exception as e:
                logger.warning(f"因子 {feat_name} IC 计算失败: {e}")
                continue

        # 按 |IC| 排序
        factors_ics.sort(key=lambda x: abs(x.ic), reverse=True)

        _emit_progress(progress_cb, 96, "写入 ICIR 缓存并聚类")
        _save_icir_cache(factors_ics)

        # ── 因子层次聚类降维 ──
        icir_map = {f.factor: f.icir for f in factors_ics}
        cluster_result = cluster_factors_by_ic(all_daily_ics, icir_map, threshold=0.7)

        logger.info(f"Alpha158 因子分析完成: {len(factors_ics)}/{len(feature_names)} 个因子有有效 IC")

        display_factors = factors_ics[:params.top_k]
        return FactorAnalysisResponse(
            start_date=params.start_date,
            end_date=params.end_date,
            predict_period=params.predict_period,
            factors=display_factors,
            summary={
                "total_factors": len(factors_ics),
                "total_alpha158": len(feature_names),
                "positive_factors": sum(1 for f in factors_ics if f.ic > 0),
                "negative_factors": sum(1 for f in factors_ics if f.ic < 0),
                "best_factor": factors_ics[0].factor if factors_ics else None,
                "neutralized": bool(neutralize_method),
                "neutralize_method": neutralize_method,
                "neutralize_requested": params.neutralize if params.neutralize and params.neutralize != "none" else None,
                "quality_warnings": quality_warnings,
                "effective_factors": cluster_result["n_effective"],
                "factor_reduction_pct": cluster_result["reduction_pct"],
                "clusters": cluster_result["clusters"],
                "label_available_until": label_available_until,
                "factor_window_start": start_str,
                "factor_window_end": end_str,
                "signal_as_of": end_str,
                "leakage_guard": "factor IC uses realized forward returns; screening may use it only with label_available_until metadata",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"因子分析失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"因子分析失败: {str(e)}")


@router.post("/analyze")
def analyze_factors(params: FactorAnalysisRequest):
    """
    兼容旧前端的同步因子分析接口。
    新前端优先使用 /analyze/submit + /analyze/status/{task_id}。
    """
    return _run_factor_analysis(params)


def _run_factor_analysis_task(task_id: str, params: FactorAnalysisRequest):
    """后台执行因子分析：真实阶段进度 + 心跳刷新 updated_at。"""
    stop_heartbeat = threading.Event()
    latest_progress = [8]

    def _heartbeat() -> None:
        """长耗时 Alpha158 期间也持续刷新 updated_at，避免被误判为僵尸。"""
        while not stop_heartbeat.wait(FACTOR_TASK_HEARTBEAT_SECONDS):
            try:
                factor_task_store.update_progress(task_id, int(latest_progress[0]))
            except Exception:
                return

    try:
        # 任务已在 submit 时 create；此处只推进进度
        factor_task_store.set_running(task_id, 8)
        hb = threading.Thread(
            target=_heartbeat,
            daemon=True,
            name=f"factor-heartbeat-{task_id[:8]}",
        )
        hb.start()

        def _on_progress(progress: int, message: str = "") -> None:
            try:
                latest_progress[0] = int(max(0, min(99, progress)))
                factor_task_store.update_progress(task_id, latest_progress[0])
                if message:
                    logger.info(f"因子分析 {task_id[:8]} [{latest_progress[0]}%] {message}")
            except Exception as e:
                logger.debug(f"更新因子进度失败: {e}")

        result = _run_factor_analysis(params, progress_cb=_on_progress)
        # 避免 nan 写入 JSON 后前端/状态接口解析失败
        payload = result.model_dump(mode="json")
        factor_task_store.set_completed(task_id, json.dumps(payload, ensure_ascii=False, allow_nan=False))
        logger.info(f"因子分析任务 {task_id[:8]} 完成")
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        factor_task_store.set_failed(task_id, detail)
    except ValueError as e:
        # allow_nan=False 触发时给出可读错误
        logger.error(f"因子分析任务 {task_id} 序列化失败: {e}")
        factor_task_store.set_failed(task_id, f"结果含无效数值(nan/inf): {e}")
    except Exception as e:
        logger.error(f"因子分析任务 {task_id} 失败: {e}")
        factor_task_store.set_failed(task_id, str(e))
    finally:
        stop_heartbeat.set()


def _start_factor_analysis_thread(task_id: str, params: FactorAnalysisRequest):
    thread = threading.Thread(
        target=_run_factor_analysis_task,
        args=(task_id, params),
        daemon=True,
        name=f"factor-analysis-{task_id[:8]}",
    )
    thread.start()
    return thread


@router.post("/analyze/submit")
def submit_factor_analysis(params: FactorAnalysisRequest):
    """提交因子分析后台任务，避免页面切换导致长请求丢失。"""
    try:
        factor_task_store.init_db()
    except Exception as e:
        logger.warning(f"因子任务库初始化失败: {e}")

    task_id = str(uuid.uuid4())
    factor_task_store.create_task(task_id, params.model_dump_json())
    _start_factor_analysis_thread(task_id, params)

    return {
        "task_id": task_id,
        "status": "running",
        "progress": 5,
        "message": "因子分析任务已启动（串行 Alpha158 + 真实阶段进度）",
    }


@router.get("/analyze/status/{task_id}")
def get_factor_analysis_status(task_id: str):
    """查询因子分析后台任务状态；自动识别僵尸/超时任务。"""
    try:
        factor_task_store.init_db()
    except Exception as e:
        logger.warning(f"因子任务库初始化失败: {e}")

    task = factor_task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在，请重新提交分析")

    task = _fail_stale_factor_task(task) or task

    if task["status"] == "completed" and task.get("result_json"):
        return {
            "task_id": task_id,
            "status": "completed",
            "progress": 100,
            "result": FactorAnalysisResponse.model_validate_json(task["result_json"]),
        }
    if task["status"] == "failed":
        return {
            "task_id": task_id,
            "status": "failed",
            "progress": int(task.get("progress") or 0),
            "error": task.get("error") or "因子分析失败",
        }

    return {
        "task_id": task_id,
        "status": "running",
        "progress": int(task.get("progress") or 0),
    }


@router.get("/list")
async def list_factors():
    """获取完整 Alpha158 因子列表"""
    from qlib.contrib.data.handler import Alpha158

    fields, names = Alpha158.get_feature_config(Alpha158)

    factors = []
    categories = {
        "KMID": "K线", "KLEN": "K线", "KMID2": "K线",
        "KUP": "K线", "KUP2": "K线", "KLOW": "K线", "KLOW2": "K线",
        "KSFT": "K线", "KSFT2": "K线",
        "OPEN": "价格", "HIGH": "价格", "LOW": "价格", "VWAP": "价格",
        "ROC": "动量", "MA": "均线", "STD": "波动率",
        "BETA": "Beta", "RSQR": "R²", "RESI": "残差",
        "MAX": "极值", "MIN": "极值", "QTLU": "分位数", "QTLD": "分位数",
        "RANK": "排名", "RSV": "RSV", "IMAX": "极值位置", "IMIN": "极值位置",
        "IMXD": "极值距离", "CORR": "相关性", "CORD": "相关性",
        "CNTP": "计数", "CNTN": "计数", "CNTD": "计数",
        "SUMP": "求和", "SUMN": "求和", "SUMD": "求和",
        "VMA": "成交量均线", "VSTD": "成交量波动", "WVMA": "加权成交量",
        "VSUMP": "成交量求和", "VSUMN": "成交量求和", "VSUMD": "成交量求和",
    }

    for name in names:
        cat = "其他"
        for prefix, category in categories.items():
            if name.startswith(prefix):
                cat = category
                break
        factors.append({"name": name, "category": cat})

    return {"total": len(factors), "factors": factors}


@router.post("/correlation")
def factor_correlation(request: FactorAnalysisRequest):
    """
    因子相关性分析
    计算因子 IC 序列之间的相关性矩阵，用于识别冗余因子
    """
    try:
        import qlib
        from qlib.data import D

        start_date = request.start_date.isoformat()
        end_date = request.end_date.isoformat()
        pred_period = request.predict_period

        # 使用 Qlib Alpha158 计算因子暴露
        handler_conf = {
            "class": "Alpha158",
            "module_path": "qlib.contrib.data.handler",
            "kwargs": {
                "start_time": start_date,
                "end_time": end_date,
                "fit_start_time": start_date,
                "fit_end_time": end_date,
                "instruments": "core650",
                "infer_processors": [
                    {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
                    {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
                ],
                "learn_processors": [
                    {"class": "DropnaLabel"},
                    {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
                ],
            },
        }

        from qlib.utils import init_instance_by_config
        handler = init_instance_by_config(handler_conf)

        # 获取因子数据
        instruments = D.instruments("core650")
        df = handler.fetch()

        if df is None or df.empty:
            raise HTTPException(status_code=400, detail="因子数据为空")

        # 计算各因子的截面 Spearman Rank IC
        factor_names = [c for c in df.columns if c.startswith(("KMID", "KLEN", "KMIN", "KMAX", "BETA",
                "RSQR", "RESI", "MAX", "MIN", "IMXD", "CNTP", "SUMP", "VMA", "VSTD", "WVMA",
                "STD", "ROC", "MA", "EMA", "MAD", "RANK", "QTLU", "QTLD", "CORD", "CORR",
                "CORD", "CORR", "STD", "SKEW", "KURT", "RSV", "BIAS", "VEMA", "VSUMP"))]

        if not factor_names:
            # fallback: take all feature columns
            factor_names = [c for c in df.columns if c not in ("$close", "$volume", "$open", "$high", "$low")]

        if len(factor_names) < 2:
            raise HTTPException(status_code=400, detail=f"可用因子数不足: {len(factor_names)}")

        # 只取前 30 个因子以减少计算时间
        factor_names = factor_names[:30]

        # 计算各因子 IC 序列
        ic_series = {}
        for fname in factor_names:
            try:
                factor_data = df[[fname]].copy()
                # 简单 IC：各时间截面的 rank correlation
                ics = []
                dates = sorted(df.index.get_level_values(0).unique())
                for i, dt in enumerate(dates[:-pred_period]):
                    try:
                        cross = df.loc[dt]
                        future_idx = dates.index(dt) + pred_period
                        if future_idx < len(dates):
                            future_dt = dates[future_idx]
                            future_ret = df.loc[future_dt].get("$close", None)
                            if future_ret is not None and fname in cross.columns:
                                from scipy import stats as scipy_stats
                                valid = cross[fname].dropna()
                                if len(valid) > 10:
                                    ic, _ = scipy_stats.spearmanr(valid, future_ret.reindex(valid.index).dropna()[:len(valid)])
                                    ics.append(ic)
                    except Exception:
                        continue
                if len(ics) > 10:
                    ic_series[fname] = pd.Series(ics)
            except Exception:
                continue

        if len(ic_series) < 2:
            raise HTTPException(status_code=400, detail="无法计算足够的 IC 序列")

        # 计算 IC 相关性矩阵
        ic_df = pd.DataFrame(ic_series)
        corr = ic_df.corr()

        result = []
        names = corr.columns.tolist()
        for i, n1 in enumerate(names):
            for j, n2 in enumerate(names):
                if i < j:
                    result.append({
                        "factor1": n1,
                        "factor2": n2,
                        "correlation": round(float(corr.loc[n1, n2]), 4),
                    })

        return {
            "factors": names,
            "correlations": result,
            "total_pairs": len(result),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"因子相关性分析失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"因子相关性分析失败: {str(e)}")


@router.get("/{factor_name}/quantile-returns")
def factor_quantile_returns(
    factor_name: str,
    start_date: str,
    end_date: str,
    predict_period: int = 5,
    num_quantiles: int = 5,
):
    """
    因子分组收益分析 (Quantile Returns)

    按因子值将股票分为 N 组，计算每组的等权前向收益。
    WorldQuant 因子验收标准第一条：monotonic quantile returns。
    """
    try:
        import qlib
        from qlib.data import D
        from qlib.utils import init_instance_by_config

        qlib.config.N_PROC = 1
        fix_parallel_ext()

        logger.info(f"分组收益: {factor_name}, {start_date}~{end_date}, {num_quantiles}组")

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
                        "instruments": "core650",
                    },
                },
                "segments": {"test": (start_date, end_date)},
            },
        })

        df_features = dataset.prepare("test", col_set="feature")
        if df_features is None or df_features.empty:
            handler = dataset.handler
            df_features = handler.fetch(col_set="feature")

        if factor_name not in df_features.columns:
            raise HTTPException(status_code=404, detail=f"因子 {factor_name} 不存在")

        feat_col = df_features[factor_name]

        # 获取收盘价计算前向收益
        stock_codes = _sample_stocks(df_features.index.get_level_values("instrument").unique().tolist())
        raw_df = D.features(stock_codes, ["$close"], start_time=start_date, end_time=end_date)

        future_returns = {}
        for code in stock_codes:
            try:
                prices = raw_df.xs(code, level="instrument")["$close"].sort_index()
                ret = prices.pct_change(predict_period).shift(-predict_period)
                for dt, val in ret.items():
                    if not np.isnan(val):
                        future_returns[(code, dt)] = val
            except Exception:
                continue

        fr_series = pd.Series(future_returns)
        fr_series.index = pd.MultiIndex.from_tuples(fr_series.index, names=["instrument", "datetime"])

        # 逐日期分组计算收益
        test_dates = sorted(df_features.index.get_level_values("datetime").unique())
        quantile_labels = [f"Q{i+1}" for i in range(num_quantiles)]
        daily_quantile_returns = {q: [] for q in quantile_labels}

        for dt in test_dates:
            try:
                fv = feat_col.xs(dt, level="datetime").dropna()
                fr = fr_series.xs(dt, level="datetime").dropna()
                common = fv.index.intersection(fr.index)
                if len(common) < num_quantiles * 3:
                    continue

                fv_common = fv[common]
                fr_common = fr[common]

                # 按因子值分 N 组
                quantile_bins = pd.qcut(fv_common, num_quantiles, labels=False, duplicates="drop")
                if quantile_bins.nunique() < num_quantiles:
                    continue

                for q_idx in range(num_quantiles):
                    mask = quantile_bins == q_idx
                    if mask.sum() > 0:
                        avg_ret = fr_common[mask].mean()
                        if not np.isnan(avg_ret):
                            daily_quantile_returns[quantile_labels[q_idx]].append(avg_ret)
            except Exception:
                continue

        # 计算各分组的平均收益
        quantile_result = []
        for q_label in quantile_labels:
            returns = daily_quantile_returns[q_label]
            mean_ret = float(np.mean(returns)) if returns else 0.0
            std_ret = float(np.std(returns)) if returns else 0.0
            n_dates = len(returns)
            quantile_result.append({
                "quantile": q_label,
                "mean_return": round(mean_ret, 6),
                "std_return": round(std_ret, 6),
                "n_dates": n_dates,
            })

        # 计算多空收益差 (Q5 - Q1)
        long_short = round(quantile_result[-1]["mean_return"] - quantile_result[0]["mean_return"], 6) if len(quantile_result) >= 2 else 0

        # 检查单调性
        returns_seq = [q["mean_return"] for q in quantile_result]
        is_monotonic = all(x <= y for x, y in zip(returns_seq, returns_seq[1:])) or all(x >= y for x, y in zip(returns_seq, returns_seq[1:]))

        logger.info(f"分组收益完成: {factor_name}, 多空收益差={long_short}, 单调性={'是' if is_monotonic else '否'}")

        return {
            "factor": factor_name,
            "num_quantiles": num_quantiles,
            "predict_period": predict_period,
            "quantile_returns": quantile_result,
            "long_short_spread": long_short,
            "is_monotonic": is_monotonic,
            "interpretation": (
                "因子值越大的组收益越高，多空收益显著" if is_monotonic and long_short > 0
                else "因子值越大的组收益越低，具有反转效应" if is_monotonic and long_short < 0
                else "分组收益不单调，因子预测能力可能不稳定"
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"分组收益计算失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"分组收益计算失败: {str(e)}")


@router.post("/decay")
def factor_decay(request: FactorAnalysisRequest):
    """
    因子 IC 衰减分析 - 计算不同预测周期下的 IC 变化
    多周期: 1, 3, 5, 10, 20 日
    """
    try:
        from scipy.stats import spearmanr
        import qlib
        from qlib.data import D
        from qlib.utils import init_instance_by_config

        periods = [1, 3, 5, 10, 20]
        start_str = str(request.start_date)
        end_str = str(request.end_date)
        top_k = min(request.top_k, 15)

        qlib.config.N_PROC = 1
        fix_parallel_ext()

        logger.info(f"因子衰减分析: {start_str}~{end_str}, Top {top_k}")

        # 先用单次 analyze 获取 Top 因子列表
        dataset = init_instance_by_config({
            "class": "DatasetH",
            "module_path": "qlib.data.dataset",
            "kwargs": {
                "handler": {
                    "class": "Alpha158",
                    "module_path": "qlib.contrib.data.handler",
                    "kwargs": {
                        "start_time": start_str,
                        "end_time": end_str,
                        "fit_start_time": start_str,
                        "fit_end_time": end_str,
                        "instruments": "core650",
                    },
                },
                "segments": {"test": (start_str, end_str)},
            },
        })

        df_features = dataset.prepare("test", col_set="feature")
        if df_features is None or df_features.empty:
            handler = dataset.handler
            df_features = handler.fetch(col_set="feature")

        if df_features is None or df_features.empty:
            raise HTTPException(status_code=500, detail="因子数据为空")

        # 获取收盘价
        stock_codes = _sample_stocks(df_features.index.get_level_values("instrument").unique().tolist())
        raw_df = D.features(stock_codes, ["$close"], start_time=start_str, end_time=end_str)

        # 获取特征列名（只用前 top_k 个）
        feature_names = [str(c) for c in df_features.columns]

        # 计算每个周期下每个因子的 IC
        decay_data = []
        for feat_name in feature_names:
            feat_col = df_features[feat_name] if feat_name in df_features.columns else df_features.iloc[:, feature_names.index(feat_name)]
            ic_values = []

            for period in periods:
                # 计算该周期的前向收益
                future_returns = {}
                for code in stock_codes:
                    try:
                        prices = raw_df.xs(code, level="instrument")["$close"].sort_index()
                        ret = prices.pct_change(period).shift(-period)
                        for dt, val in ret.items():
                            if not np.isnan(val):
                                future_returns[(code, dt)] = val
                    except Exception:
                        continue

                fr_series = pd.Series(future_returns, name="future_return")
                fr_series.index = pd.MultiIndex.from_tuples(fr_series.index, names=["instrument", "datetime"])

                # 计算每日 IC
                daily_ics = []
                test_dates = df_features.index.get_level_values("datetime").unique()
                for dt in test_dates:
                    try:
                        fv = feat_col.xs(dt, level="datetime").dropna()
                        fr = fr_series.xs(dt, level="datetime").dropna()
                        common = fv.index.intersection(fr.index)
                        if len(common) < 15:
                            continue
                        fv_vals = fv[common].values
                        fr_vals = fr[common].values
                        valid = np.isfinite(fv_vals) & np.isfinite(fr_vals)
                        if valid.sum() < 15:
                            continue
                        ic, _ = spearmanr(fv_vals[valid], fr_vals[valid])
                        if not np.isnan(ic):
                            daily_ics.append(ic)
                    except Exception:
                        continue

                mean_ic = np.mean(daily_ics) if daily_ics else 0
                ic_values.append(round(float(mean_ic), 4))

            decay_data.append({"factor": feat_name, "ic_values": ic_values})

        logger.info(f"因子衰减分析完成: {len(decay_data)} 个因子")

        return {
            "factors": [d["factor"] for d in decay_data],
            "periods": periods,
            "decay_data": decay_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"因子衰减分析失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"因子衰减分析失败: {str(e)}")


@router.post("/combine")
def combine_signals(request: FactorAnalysisRequest):
    """
    信号组合 - 从 Top N 因子构建 IC 加权复合评分
    """
    try:
        from scipy.stats import spearmanr, zscore
        import qlib
        from qlib.data import D
        from qlib.utils import init_instance_by_config

        top_n = min(request.top_k, 15)
        start_str = str(request.start_date)
        end_str = str(request.end_date)

        qlib.config.N_PROC = 1
        fix_parallel_ext()

        logger.info(f"信号组合: {start_str}~{end_str}, Top {top_n}")

        dataset = init_instance_by_config({
            "class": "DatasetH",
            "module_path": "qlib.data.dataset",
            "kwargs": {
                "handler": {
                    "class": "Alpha158",
                    "module_path": "qlib.contrib.data.handler",
                    "kwargs": {
                        "start_time": start_str,
                        "end_time": end_str,
                        "fit_start_time": start_str,
                        "fit_end_time": end_str,
                        "instruments": "core650",
                    },
                },
                "segments": {"test": (start_str, end_str)},
            },
        })

        df_features = dataset.prepare("test", col_set="feature")
        if df_features is None or df_features.empty:
            handler = dataset.handler
            df_features = handler.fetch(col_set="feature")

        feature_names = [str(c) for c in df_features.columns[:top_n]]

        stock_codes = _sample_stocks(df_features.index.get_level_values("instrument").unique().tolist())
        raw_df = D.features(stock_codes, ["$close"], start_time=start_str, end_time=end_str)

        pred_period = request.predict_period

        # 计算每个因子的 IC 权重
        factor_weights = []
        for feat_name in feature_names:
            feat_col = df_features[feat_name] if feat_name in df_features.columns else df_features.iloc[:, feature_names.index(feat_name)]

            future_returns = {}
            for code in stock_codes:
                try:
                    prices = raw_df.xs(code, level="instrument")["$close"].sort_index()
                    ret = prices.pct_change(pred_period).shift(-pred_period)
                    for dt, val in ret.items():
                        if not np.isnan(val):
                            future_returns[(code, dt)] = val
                except Exception:
                    continue

            fr_series = pd.Series(future_returns)
            fr_series.index = pd.MultiIndex.from_tuples(fr_series.index, names=["instrument", "datetime"])

            daily_ics = []
            test_dates = df_features.index.get_level_values("datetime").unique()
            for dt in test_dates:
                try:
                    fv = feat_col.xs(dt, level="datetime").dropna()
                    fr = fr_series.xs(dt, level="datetime").dropna()
                    common = fv.index.intersection(fr.index)
                    if len(common) < 15:
                        continue
                    valid = np.isfinite(fv[common].values) & np.isfinite(fr[common].values)
                    if valid.sum() < 15:
                        continue
                    ic, _ = spearmanr(fv[common].values[valid], fr[common].values[valid])
                    if not np.isnan(ic):
                        daily_ics.append(ic)
                except Exception:
                    continue

            mean_ic = np.mean(daily_ics) if daily_ics else 0
            factor_weights.append({"factor": feat_name, "ic": round(float(mean_ic), 4), "abs_weight": abs(mean_ic)})

        # 归一化权重
        total_abs_ic = sum(fw["abs_weight"] for fw in factor_weights) or 1
        for fw in factor_weights:
            fw["weight"] = round(fw["abs_weight"] / total_abs_ic, 4)

        factor_weights.sort(key=lambda x: x["weight"], reverse=True)

        # 获取最近一个交易日的复合评分
        last_date = sorted(df_features.index.get_level_values("datetime").unique())[-1]
        composite_scores = []

        for code in _sample_stocks(stock_codes, 100):
            try:
                score = 0
                for fw in factor_weights[:10]:
                    feat_name = fw["factor"]
                    feat_col = df_features[feat_name] if feat_name in df_features.columns else df_features.iloc[:, feature_names.index(feat_name)]
                    try:
                        val = feat_col.xs((code, last_date), level=("instrument", "datetime"))
                        if not np.isnan(val):
                            # Z-score normalize the factor value
                            all_vals = feat_col.dropna()
                            if len(all_vals) > 10:
                                z_val = (val - all_vals.mean()) / (all_vals.std() or 1)
                                direction = 1 if fw["ic"] > 0 else -1
                                score += direction * z_val * fw["weight"]
                    except Exception:
                        continue

                composite_scores.append({"code": code, "score": round(float(score), 4)})
            except Exception:
                continue

        composite_scores.sort(key=lambda x: x["score"], reverse=True)

        logger.info(f"信号组合完成: {len(factor_weights)} 个因子, {len(composite_scores)} 只股票")

        return {
            "date": str(last_date),
            "factor_weights": factor_weights[:10],
            "top_stocks": composite_scores[:10],
            "all_stocks": composite_scores,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"信号组合失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"信号组合失败: {str(e)}")


@router.get("/{factor_name}/detail")
def factor_detail(factor_name: str, start_date: str, end_date: str, predict_period: int = 5):
    """
    单因子详情 - 每日 IC 序列和因子暴露时序
    """
    try:
        from scipy.stats import spearmanr
        import qlib
        from qlib.data import D
        from qlib.utils import init_instance_by_config

        qlib.config.N_PROC = 1
        fix_parallel_ext()

        logger.info(f"因子详情: {factor_name}, {start_date}~{end_date}")

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
                        "instruments": "core650",
                    },
                },
                "segments": {"test": (start_date, end_date)},
            },
        })

        df_features = dataset.prepare("test", col_set="feature")
        if df_features is None or df_features.empty:
            handler = dataset.handler
            df_features = handler.fetch(col_set="feature")

        if factor_name not in df_features.columns:
            raise HTTPException(status_code=404, detail=f"因子 {factor_name} 不存在")

        feat_col = df_features[factor_name]

        # 计算每日 IC
        stock_codes = _sample_stocks(df_features.index.get_level_values("instrument").unique().tolist())
        raw_df = D.features(stock_codes, ["$close"], start_time=start_date, end_time=end_date)

        future_returns = {}
        for code in stock_codes:
            try:
                prices = raw_df.xs(code, level="instrument")["$close"].sort_index()
                ret = prices.pct_change(predict_period).shift(-predict_period)
                for dt, val in ret.items():
                    if not np.isnan(val):
                        future_returns[(code, dt)] = val
            except Exception:
                continue

        fr_series = pd.Series(future_returns)
        fr_series.index = pd.MultiIndex.from_tuples(fr_series.index, names=["instrument", "datetime"])

        daily_ic_records = []
        test_dates = sorted(df_features.index.get_level_values("datetime").unique())

        for dt in test_dates:
            try:
                fv = feat_col.xs(dt, level="datetime").dropna()
                fr = fr_series.xs(dt, level="datetime").dropna()
                common = fv.index.intersection(fr.index)
                if len(common) < 15:
                    continue
                valid = np.isfinite(fv[common].values) & np.isfinite(fr[common].values)
                if valid.sum() < 15:
                    continue
                ic, _ = spearmanr(fv[common].values[valid], fr[common].values[valid])
                if not np.isnan(ic):
                    daily_ic_records.append({
                        "date": str(dt),
                        "ic": round(float(ic), 4),
                        "n_stocks": int(valid.sum()),
                    })
            except Exception:
                continue

        # 因子均值时序
        factor_mean_series = []
        for dt in test_dates:
            try:
                vals = feat_col.xs(dt, level="datetime").dropna()
                factor_mean_series.append({
                    "date": str(dt),
                    "value": round(float(vals.mean()), 6),
                    "std": round(float(vals.std()), 6),
                })
            except Exception:
                continue

        mean_ic = np.mean([r["ic"] for r in daily_ic_records]) if daily_ic_records else 0
        std_ic = np.std([r["ic"] for r in daily_ic_records]) if daily_ic_records else 0

        return {
            "factor": factor_name,
            "category": _get_factor_category(factor_name),
            "mean_ic": round(float(mean_ic), 4),
            "std_ic": round(float(std_ic), 4),
            "icir": round(float(mean_ic / std_ic), 2) if std_ic > 0 else 0,
            "daily_ics": daily_ic_records,
            "factor_series": factor_mean_series,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"因子详情失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"因子详情失败: {str(e)}")
