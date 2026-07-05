"""
模型回测 API - 基于 Qlib 真实回测框架
"""

import os
import importlib.util
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List, Optional
import pandas as pd
import numpy as np
import uuid
import json
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import Response
from loguru import logger

# 全局禁用多进程（必须在 import qlib 之前设置）
os.environ['NUMBA_NUM_THREADS'] = '1'
os.environ['QLIB_NO_MULTI_PROCESS'] = '1'
os.environ['JOBLIB_START_METHOD'] = 'spawn' if os.name == 'nt' else 'forkserver'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ.setdefault('MLFLOW_ALLOW_FILE_STORE', 'true')

from models.schemas import (
    BacktestParams, BacktestResponse,
    StockRecommendation, EquityPoint, DrawdownPoint,
    AttributionPoint, AttributionSummary,
)

router = APIRouter()

# 导入核心模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from stock_names import get_stock_name
from db.task_store import task_store

INTERRUPTED_TASK_ERROR = "回测任务已中断：服务重启或后台进程退出，请重新提交回测。"
ALPHA158_LABEL_LOOKAHEAD_STEPS = 2
SUPPORTED_BACKTEST_MODELS = {
    "lightgbm": {"dependency": None, "label": "LightGBM"},
    "xgboost": {"dependency": "xgboost", "label": "XGBoost"},
}


def validate_backtest_model_available(model: str) -> str:
    normalized = str(model or "lightgbm").lower()
    if normalized not in SUPPORTED_BACKTEST_MODELS:
        raise HTTPException(status_code=400, detail=f"暂不支持的回测模型: {model}")
    model_info = SUPPORTED_BACKTEST_MODELS[normalized]
    dependency = model_info["dependency"]
    if dependency and importlib.util.find_spec(dependency) is None:
        raise HTTPException(
            status_code=400,
            detail=f"当前服务器未安装 {model_info['label']}，请先使用 LightGBM 回测。",
        )
    return normalized


from core.compat import fix_parallel_ext


def _parse_date_value(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        try:
            return value.date()
        except Exception:
            pass
    return datetime.fromisoformat(str(value)[:10]).date()


def _normalize_calendar(calendars) -> list[date]:
    dates = sorted({_parse_date_value(item) for item in calendars})
    if not dates:
        raise ValueError("交易日历为空，无法构建防未来函数回测区间")
    return dates


def _calendar_on_or_after(calendars: list[date], target: date) -> date:
    for item in calendars:
        if item >= target:
            return item
    raise ValueError(f"交易日历中找不到不早于 {target.isoformat()} 的日期")


def _calendar_on_or_before(calendars: list[date], target: date) -> date:
    for item in reversed(calendars):
        if item <= target:
            return item
    raise ValueError(f"交易日历中找不到不晚于 {target.isoformat()} 的日期")


def _calendar_shift(calendars: list[date], base: date, steps: int) -> date:
    try:
        idx = calendars.index(base)
    except ValueError as exc:
        raise ValueError(f"交易日 {base.isoformat()} 不在日历中") from exc
    shifted = idx + steps
    if shifted < 0 or shifted >= len(calendars):
        raise ValueError(f"交易日历不足，无法从 {base.isoformat()} 偏移 {steps} 个交易日")
    return calendars[shifted]


def _calendar_next(calendars: list[date], base: date) -> date | None:
    try:
        return _calendar_shift(calendars, base, 1)
    except ValueError:
        return None


def build_leak_safe_segments(
    train_start: str | date,
    train_end: str | date,
    test_start: str | date,
    backtest_end: str | date,
    calendars,
    label_lookahead_steps: int = ALPHA158_LABEL_LOOKAHEAD_STEPS,
) -> dict[str, tuple[str, str]]:
    """Build non-overlapping Qlib segments with an embargo for forward labels.

    Alpha158's default label looks ahead two trading steps. The last training or
    validation feature date must therefore leave those future label dates outside
    the next segment.
    """
    calendar = _normalize_calendar(calendars)
    train_start_dt = _calendar_on_or_after(calendar, _parse_date_value(train_start))
    requested_train_end = _calendar_on_or_before(calendar, _parse_date_value(train_end))
    test_start_dt = _calendar_on_or_after(calendar, _parse_date_value(test_start))
    test_end_dt = _calendar_on_or_before(calendar, _parse_date_value(backtest_end))

    if test_start_dt > test_end_dt:
        raise ValueError("测试开始日期晚于回测结束日期")

    last_pre_test_label_date = _calendar_shift(calendar, test_start_dt, -(label_lookahead_steps + 1))
    safe_train_end = min(requested_train_end, last_pre_test_label_date)
    if train_start_dt > safe_train_end:
        raise ValueError("训练区间在防未来函数缓冲后为空，请拉开训练结束和测试开始日期")

    segments: dict[str, tuple[str, str]] = {
        "train": (train_start_dt.isoformat(), safe_train_end.isoformat()),
        "test": (test_start_dt.isoformat(), test_end_dt.isoformat()),
    }

    valid_start = _calendar_next(calendar, requested_train_end)
    valid_end = last_pre_test_label_date
    if valid_start and valid_start <= valid_end:
        train_end_before_valid = _calendar_shift(calendar, valid_start, -(label_lookahead_steps + 1))
        safe_train_end = min(requested_train_end, train_end_before_valid)
        if train_start_dt <= safe_train_end:
            segments["train"] = (train_start_dt.isoformat(), safe_train_end.isoformat())
            segments["valid"] = (valid_start.isoformat(), valid_end.isoformat())

    return segments


def build_selected_factor_warning(selected_factors: list[str] | None) -> str | None:
    if not selected_factors:
        return None
    factors = ", ".join(str(item) for item in selected_factors if item)
    suffix = f"（来源因子：{factors}）" if factors else ""
    return f"当前结果使用完整 Alpha158 特征训练，不是单因子专属回测{suffix}。"


def mark_interrupted_backtest_tasks(limit: int = 200) -> int:
    """Mark persisted running tasks as failed after a service restart.

    FastAPI BackgroundTasks run in the current process. If the backend restarts,
    those workers are gone, so persisted "running" tasks cannot finish.
    """
    marked = 0
    task_store.init_db()
    for task in task_store.list_tasks(limit=limit):
        if task.get("status") != "running":
            continue
        task_store.set_failed(task["task_id"], INTERRUPTED_TASK_ERROR)
        marked += 1
    return marked


def _check_a_share_constraints(codes: list, start_date: str, end_date: str) -> dict:
    """
    预检 A 股交易约束，返回诊断报告

    检测内容:
    1. 涨跌停: 统计触及涨跌停板的股票/天数
    2. 停牌: 统计停牌日数
    3. 科创板/创业板: 自动排除（±20% 涨跌幅）
    """
    try:
        from qlib.data import D

        # ── 1. 按板块分类（不再硬排除科创/创业，回测已用动态阈值兼容 ±20%）──
        chi_next_codes = [
            c for c in codes
            if c.startswith(("SH688", "SZ300", "SZ301"))
        ]
        valid_codes = list(codes)  # 全部保留，涨跌停按板块阈值分别统计
        excluded_codes = []

        # ── 2. 停牌检测 ──
        try:
            close_df = D.features(valid_codes, ["$close"], start_time=start_date, end_time=end_date, freq="day")
            # 停牌表现为价格不变（连续相同收盘价）或 NaN
            if close_df is not None and not close_df.empty:
                close_unstacked = close_df.reset_index().pivot(
                    index="datetime", columns="instrument", values="$close"
                ) if "instrument" in close_df.reset_index().columns else close_df

                # 检测完全 NaN 的日期（整个期间无交易）
                n_dates = len(close_unstacked) if hasattr(close_unstacked, '__len__') else 0
                suspension_days = 0
                if n_dates > 0:
                    # 连续 2 天收盘价完全相同视为停牌
                    for col in close_unstacked.columns:
                        pct_changes = close_unstacked[col].pct_change().fillna(0)
                        zero_move = (pct_changes == 0).sum()
                        if zero_move > n_dates * 0.5:
                            suspension_days += int(zero_move)

                n_suspended_stocks = int(
                    (close_unstacked.isna().mean() > 0.8).sum()
                ) if hasattr(close_unstacked, 'isna') else 0
            else:
                suspension_days = 0
                n_suspended_stocks = 0
        except Exception:
            suspension_days = 0
            n_suspended_stocks = 0

        # ── 3. 涨跌停检测 ──
        try:
            high_df = D.features(valid_codes, ["$high", "$low"], start_time=start_date, end_time=end_date, freq="day")
            if high_df is not None and not high_df.empty:
                # 用当日涨跌幅判断是否触及涨跌停
                limit_up_hits = 0
                limit_down_hits = 0
                for code in valid_codes[:50]:  # 抽样检测
                    try:
                        code_data = high_df.xs(code, level="instrument")
                        # 按板块动态阈值：科创/创业 ±20%，主板 ±10%
                        thr = 0.195 if code.startswith(("SH688", "SZ300", "SZ301")) else 0.095
                        returns = code_data["$high"].pct_change()
                        limit_up_hits += int((returns > thr).sum())
                        returns_low = code_data["$low"].pct_change()
                        limit_down_hits += int((returns_low < -thr).sum())
                    except Exception:
                        continue
            else:
                limit_up_hits = 0
                limit_down_hits = 0
        except Exception:
            limit_up_hits = 0
            limit_down_hits = 0

        has_chi_next = bool(chi_next_codes)
        limit_label = "±20%(科创创业兼容)" if has_chi_next else "±10%(主板)"
        return {
            "original_universe": len(codes),
            "valid_universe": len(valid_codes),
            "excluded_chi_next_star": 0,  # 不再排除，已用动态阈值兼容
            "chi_next_star_count": len(chi_next_codes),
            "limit_threshold_used": 0.195 if has_chi_next else 0.095,
            "limit_up_hits_estimated": limit_up_hits,
            "limit_down_hits_estimated": limit_down_hits,
            "suspension_days_estimated": suspension_days,
            "suspended_stocks_estimated": n_suspended_stocks,
            "constraints_active": [
                f"涨跌停板 (limit_threshold={0.195 if has_chi_next else 0.095}, {limit_label})",
                "T+1 制度 (日频回测自动满足)",
                "停牌排除 (NaN 数据自动跳过)",
                "只做多不融券 (TopkDropoutStrategy)",
                f"已兼容科创板/创业板 {len(chi_next_codes)} 只 (动态阈值±20%)" if has_chi_next else "无科创板/创业板",
            ],
        }
    except Exception as e:
        logger.warning(f"A 股约束检测跳过: {e}")
        return {
            "constraints_active": [
                "涨跌停板 (limit_threshold=0.095)",
                "T+1 制度 (日频回测)",
                "停牌排除 (NaN 自动跳过)",
                "只做多不融券",
            ],
            "warning": f"约束检测未运行: {e}",
        }


def run_backtest_task(task_id: str, params: BacktestParams):
    """
    执行回测任务（后台运行）- 使用真实 Qlib 框架

    A 股约束处理：
    - 涨跌停: Qlib exchange limit_threshold=0.095 处理主板 ±10%
    - T+1: 日频回测自然满足 T+1 约束
    - 停牌: Qlib 对停牌股票返回 NaN，自然排除
    - 做空限制: TopkDropoutStrategy 只做多
    - 科创板/创业板: 自动排除（±20% 涨跌幅不匹配 0.095 阈值）
    """
    try:
        params.model = validate_backtest_model_available(params.model)
        task_store.init_db()
        if task_store.get_task(task_id) is None:
            task_store.create_task(task_id, params.model_dump_json())

        import qlib
        from qlib.utils import init_instance_by_config
        from qlib.contrib.evaluate import backtest_daily
        from qlib.contrib.strategy import TopkDropoutStrategy

        # 单线程模式，避免多进程冲突
        qlib.config.N_PROC = 1

        # 修复 ParallelExt 兼容性
        fix_parallel_ext()

        task_store.update_progress(task_id, 10)

        # ── 构建数据集（Alpha158 因子） ──
        train_start = str(params.train_start)
        train_end = str(params.train_end)
        test_start = str(params.test_start)
        test_end = str(params.test_end)

        # 回测结束日期不能超过 Qlib 数据范围，提前2天避免边界问题
        from qlib.data import D
        calendars = D.calendar(freq="day")
        test_end_dt = pd.Timestamp(test_end)
        available_end = calendars[-1] if len(calendars) > 0 else test_end_dt
        backtest_end = min(test_end_dt, available_end - pd.Timedelta(days=2))
        segments = build_leak_safe_segments(
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            backtest_end=str(backtest_end),
            calendars=calendars,
        )
        safe_train_start, safe_train_end = segments["train"]
        safe_test_start, safe_backtest_end = segments["test"]

        task_store.update_progress(task_id, 20)

        logger.info(f"回测参数: segments={segments}")

        dataset = init_instance_by_config({
            "class": "DatasetH",
            "module_path": "qlib.data.dataset",
            "kwargs": {
                "handler": {
                    "class": "Alpha158",
                    "module_path": "qlib.contrib.data.handler",
                    "kwargs": {
                        "start_time": safe_train_start,
                        "end_time": safe_backtest_end,
                        "fit_start_time": safe_train_start,
                        "fit_end_time": safe_train_end,
                        "instruments": params.universe,
                        "infer_processors": [
                            {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
                            {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
                        ],
                        "learn_processors": [
                            {"class": "DropnaLabel"},
                            {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
                        ],
                        "process_type": "independent",
                    },
                },
                "segments": segments,
            },
        })

        task_store.update_progress(task_id, 40)

        # ── 训练模型（轻量化配置以加速回测） ──
        if params.model == "xgboost":
            model = init_instance_by_config({
                "class": "XGBModel",
                "module_path": "qlib.contrib.model.xgboost",
                "kwargs": {
                    "n_estimators": 100,
                    "max_depth": 5,
                    "learning_rate": 0.1,
                    "nthread": 1,
                }
            })
        else:
            # 默认 LightGBM（精简版）
            model = init_instance_by_config({
                "class": "LGBModel",
                "module_path": "qlib.contrib.model.gbdt",
                "kwargs": {
                    "loss": "mse",
                    "colsample_bytree": 0.8879,
                    "learning_rate": 0.2,
                    "subsample": 0.8789,
                    "lambda_l1": 205.6999,
                    "lambda_l2": 580.9768,
                    "max_depth": 6,
                    "num_leaves": 80,
                    "n_estimators": 100,
                    "num_threads": 1,
                }
            })

        model.fit(dataset)
        pred = model.predict(dataset)

        # ── 如果指定了因子子集，过滤预测数据的特征列 ──
        if params.selected_factors and len(params.selected_factors) > 0:
            logger.info(f"使用指定因子子集: {params.selected_factors}")
            # Alpha158 handler 已经生成了全部特征
            # 预测是通过模型对全部特征做 inference 的，所以过滤效果在模型层面有限
            # 如果要真正只用指定因子，需要在训练前过滤 handler 输出
            # 这里记录因子来源用于结果展示

        task_store.update_progress(task_id, 60)

        # ── 执行回测 ──
        # 获取沪深300成分股并运行A股约束检测
        instruments = D.instruments(params.universe)
        logger.info(f"回测股票池: {params.universe}, 成分数: {len(D.list_instruments(instruments, as_list=True))}")
        all_csi300 = D.list_instruments(instruments, as_list=True)
        constraint_analysis = _check_a_share_constraints(all_csi300, safe_train_start, safe_backtest_end)

        task_store.update_progress(task_id, 65)

        # 涨跌停阈值：Qlib 0.9.7 exchange 支持 flat float 阈值
        # 分板阈值通过 universe 过滤 + 单阈值近似实现：
        # - 沪深300/中证500(主板为主): 0.099(±10%)
        # - 全市场/含科创板创业板: 0.195(±20%宽松阈值，避免误判)
        has_chi_next = any(
            c.startswith(("SH688", "SZ300", "SZ301"))
            for c in all_csi300
        )
        limit_threshold = 0.195 if (params.universe == "all" or has_chi_next) else 0.099
        logger.info(f"涨跌停阈值: {limit_threshold} (universe={params.universe}, 含科创创业={has_chi_next})")

        exchange_kwargs = {
            "codes": params.universe,
            "freq": "day",
            "limit_threshold": limit_threshold,
            "deal_price": "close",
            "open_cost": params.buy_cost,
            "close_cost": params.sell_cost,
            "min_cost": 5,
            # volume_threshold/impact_cost reserved for future Qlib upgrade
        }

        # TopkDropoutStrategy: topk=持仓数, n_drop=每次调仓换手数
        topk = params.hold_num
        n_drop = max(1, topk // 5)  # 每次换手约20%持仓
        strategy = TopkDropoutStrategy(topk=topk, n_drop=n_drop, signal=pred)

        task_store.update_progress(task_id, 70)

        report, positions_dict = backtest_daily(
            start_time=safe_test_start,
            end_time=safe_backtest_end,
            strategy=strategy,
            executor={
                "class": "SimulatorExecutor",
                "module_path": "qlib.backtest.executor",
                "kwargs": {
                    "time_per_step": "day",
                    "generate_portfolio_metrics": True,
                },
            },
            account=params.account,
            benchmark="SH000300",
            exchange_kwargs=exchange_kwargs,
        )

        task_store.update_progress(task_id, 80)

        # ── 计算回测指标（毛收益 vs 净收益） ──
        r = report["return"]  # 毛收益（Qlib 返回的日收益，未扣 cost）
        bench = report["bench"]
        cost = report["cost"] if "cost" in report.columns else pd.Series(0.0, index=r.index)
        r_net = r - cost  # 净收益：扣除佣金+印花税+冲击成本的日收益
        ex = r - bench

        # 毛收益指标（旧口径，保留以展示摩擦成本）
        ann_r = r.mean() * 252
        ann_std = r.std() * np.sqrt(252)
        sharpe = ann_r / ann_std if ann_std > 0 else 0

        # 净收益指标（新口径，真实可执行收益）
        ann_r_net = r_net.mean() * 252
        sharpe_net = ann_r_net / ann_std if ann_std > 0 else 0

        # 累计净值（毛 vs 净两条线）
        cum = (1 + r).cumprod()
        cum_net = (1 + r_net).cumprod()
        cum_bench = (1 + bench).cumprod()
        dd_series = cum / cum.cummax() - 1
        max_dd = dd_series.min()

        # 累计交易成本
        cumulative_cost = float(cost.sum())

        # 胜率（按净收益）
        win_rate = (r_net > 0).mean()

        # Calmar（按净收益）
        calmar = ann_r_net / abs(max_dd) if max_dd != 0 else 0

        # 总收益率（毛+净）
        total_return = cum.iloc[-1] - 1 if len(cum) > 0 else 0
        net_total_return = cum_net.iloc[-1] - 1 if len(cum_net) > 0 else 0

        # 盈亏比（按净收益）
        gains = r_net[r_net > 0]
        losses = r_net[r_net < 0]
        avg_gain = gains.mean() if len(gains) > 0 else 0
        avg_loss = abs(losses.mean()) if len(losses) > 0 else 1
        profit_loss_ratio = avg_gain / avg_loss if avg_loss > 0 else 0

        # ── 统计检验 ──
        # t 检验（策略收益是否显著 > 0）
        from scipy import stats as scipy_stats
        t_stat, p_value = scipy_stats.ttest_1samp(r_net.dropna(), 0)
        t_stat = float(t_stat)
        p_value = float(p_value)

        # 信息比率（超额收益 / 跟踪误差）
        tracking_error = (r_net - bench).std() * np.sqrt(252)
        information_ratio = ((r_net - bench).mean() * 252) / tracking_error if tracking_error > 0 else 0

        # Sortino 比率（使用下行标准差）
        downside = r_net[r_net < 0]
        downside_std = downside.std() * np.sqrt(252) if len(downside) > 0 else ann_std
        sortino = ann_r / downside_std if downside_std > 0 else 0

        # 月度胜率
        monthly_r = r_net.resample("ME").apply(lambda x: (1 + x).prod() - 1)
        monthly_win_rate = (monthly_r > 0).mean()

        # ── 交易成本影响估算 ──
        # 注：turnover 调仓周期参数当前未接入 Qlib TopkDropoutStrategy（日频回测默认每日评估）
        try:
            avg_daily_turnover = report["turnover"].mean() if "turnover" in report.columns else 0
            daily_vol = r.std()
            # 平方根冲击模型（修正版）: 单次冲击 ≈ σ * sqrt(participation_rate)
            # participation_rate 取持仓占日成交的比例，保守估计 2%（不再用 Qlib turnover 直接除）
            participation_rate = 0.02
            estimated_impact_per_trade = daily_vol * np.sqrt(participation_rate)
            # 年化：按实际调仓频率，不是每天。调仓周期 params.turnover 天一次。
            rebalance_days = max(int(params.turnover), 1)
            trades_per_year = 252 / rebalance_days
            annual_impact = estimated_impact_per_trade * trades_per_year * 0.5  # 每次调仓半次换手
            # 钳制到合理区间：单次冲击不超 1%，年化不超 50%（避免短窗口高换手放大成荒诞值）
            estimated_impact_per_trade = min(float(estimated_impact_per_trade), 0.01)
            annual_impact = min(float(annual_impact), 0.5)
            fixed_cost_annual = (params.buy_cost + params.sell_cost) * trades_per_year
            if annual_impact > fixed_cost_annual * 1.5:
                cost_impact_estimate = (
                    f"市场冲击成本估计约 {annual_impact:.2%}/年（单次约 {estimated_impact_per_trade:.2%}，"
                    f"每 {rebalance_days} 天调仓），高于固定佣金 ({fixed_cost_annual:.2%}/年)。"
                    f"小盘股实际冲击可达 0.5-1.0%/次，建议据此下调回测收益。"
                )
            else:
                cost_impact_estimate = (
                    f"市场冲击成本估计约 {annual_impact:.2%}/年，与固定佣金 ({fixed_cost_annual:.2%}/年)接近，"
                    f"流动性可控。"
                )
        except Exception:
            cost_impact_estimate = None

        # ── Brinson 绩效归因 ──
        attribution_result = _compute_brinson_attribution(
            positions_dict=positions_dict,
            benchmark="SH000300",
            start_date=safe_test_start,
            end_date=safe_backtest_end,
            instruments=instruments,
        )

        task_store.update_progress(task_id, 90)

        # ── 生成净值曲线 ──
        equity_data = []
        for i in range(len(cum)):
            dt = cum.index[i]
            equity_data.append(EquityPoint(
                date=dt.strftime("%Y-%m-%d") if hasattr(dt, 'strftime') else str(dt),
                value=round(float(cum.iloc[i]), 4),
                benchmark=round(float(cum_bench.iloc[i]), 4),
            ))

        # ── 生成回撤曲线 ──
        drawdown_data = []
        for i in range(len(dd_series)):
            dt = dd_series.index[i]
            drawdown_data.append(DrawdownPoint(
                date=dt.strftime("%Y-%m-%d") if hasattr(dt, 'strftime') else str(dt),
                value=round(float(dd_series.iloc[i]) * 100, 2),
            ))

        # ── 生成买卖推荐（含归因上下文）──
        attr_ind_map = attribution_result.get("industry_map", {}) if attribution_result else {}
        attr_ind_contrib = attribution_result.get("summary", {}).get("by_industry", {}) if attribution_result else {}
        attr_main = attribution_result.get("main_driver", "") if attribution_result else ""

        top_buys = []
        top_sells = []
        result_warnings = []
        selected_factor_warning = build_selected_factor_warning(params.selected_factors)
        if selected_factor_warning:
            result_warnings.append(selected_factor_warning)

        try:
            pred_df = pred.reset_index()
            pred_df.columns = ['日期', '代码', '预测得分']

            latest_date = pred_df['日期'].max()
            latest_pred = pred_df[pred_df['日期'] == latest_date].copy()
            latest_pred = latest_pred.sort_values('预测得分', ascending=False)

            # 买入推荐 (Top K)
            for _, row in latest_pred.head(topk).iterrows():
                code = str(row['代码']).upper()
                score = float(row['预测得分'])
                name = get_stock_name(code)
                reason = _generate_buy_reason(score, name, code, attr_ind_map, attr_ind_contrib, attr_main)
                top_buys.append(StockRecommendation(
                    code=code,
                    name=name,
                    score=round(score * 100, 2),
                    reason=reason,
                ))

            # 卖出推荐 (Bottom K)
            for _, row in latest_pred.tail(min(10, len(latest_pred) // 2)).iterrows():
                code = str(row['代码']).upper()
                score = float(row['预测得分'])
                name = get_stock_name(code)
                reason = _generate_sell_reason(score, name, code, attr_ind_map, attr_ind_contrib, attr_main)
                top_sells.append(StockRecommendation(
                    code=code,
                    name=name,
                    score=round(score * 100, 2),
                    reason=reason,
                ))
        except Exception as e:
            logger.warning(f"生成推荐失败: {e}，跳过推荐生成")

        # ── 仓位建议 ──
        if win_rate > 0.6 and sharpe > 1.5:
            position_advice = "建议仓位 70-80%，策略表现优秀"
        elif win_rate > 0.55 and sharpe > 1.0:
            position_advice = "建议仓位 60-70%，策略表现良好"
        elif win_rate > 0.5:
            position_advice = "建议仓位 50-60%，策略表现一般"
        else:
            position_advice = "建议仓位 30-40%，策略表现较弱，注意风控"

        result = BacktestResponse(
                task_id=task_id,
                status="completed",
                progress=100,
                total_return=round(float(total_return), 4),
                net_total_return=round(float(net_total_return), 4),
                annual_return=round(float(ann_r), 4),
                net_annual_return=round(float(ann_r_net), 4),
                sharpe_ratio=round(float(sharpe), 2),
                calmar_ratio=round(float(calmar), 2),
                max_drawdown=round(float(max_dd), 4),
                win_rate=round(float(win_rate), 4),
                profit_loss_ratio=round(float(profit_loss_ratio), 2),
                t_statistic=round(t_stat, 4),
                p_value=round(p_value, 4),
                information_ratio=round(float(information_ratio), 2),
                sortino_ratio=round(float(sortino), 2),
                monthly_win_rate=round(float(monthly_win_rate), 4),
                equity=equity_data,
                net_equity=net_equity_data,
                drawdown=drawdown_data,
                top_buys=top_buys,
                top_sells=top_sells,
                position_advice=position_advice,
                constraint_analysis=constraint_analysis,
                factor_source=params.source_factor,
                attribution=_build_safe_attribution_summary(attribution_result) if attribution_result else None,
                attribution_curve=_build_safe_attribution_curve(attribution_result) if attribution_result else None,
                attribution_interpretation=attribution_result["interpretation"] if attribution_result else None,
                cost_impact_estimate=cost_impact_estimate,
                cumulative_cost=round(cumulative_cost, 4),
                price_adjustment_note="后复权历史价 × 复权因子，面向用户价格已换算前复权（=真实市价）",
                warnings=result_warnings or None,
            )
        task_store.set_completed(task_id, result.model_dump_json())

        logger.info(f"回测任务 {task_id} 完成: 年化={ann_r:.2%}, 夏普={sharpe:.2f}, 回撤={max_dd:.2%}")

    except Exception as e:
        logger.error(f"回测任务 {task_id} 失败: {e}")
        import traceback
        traceback.print_exc()
        task_store.set_failed(task_id, str(e))


def _build_safe_attribution_curve(attribution_result):
    """归因曲线防御性清洗：NaN/None/inf 归零，避免 Pydantic float 校验失败。"""
    def _clean(val):
        try:
            v = float(val)
            return round(v, 2) if np.isfinite(v) else 0.0
        except Exception:
            return 0.0

    curve = []
    for p in attribution_result.get("curve", []):
        curve.append(AttributionPoint(
            date=p.get("date", ""),
            allocation=_clean(p.get("allocation", 0)),
            selection=_clean(p.get("selection", 0)),
            interaction=_clean(p.get("interaction", 0)),
            total_active=_clean(p.get("total_active", 0)),
        ))
    return curve


def _build_safe_attribution_summary(attribution_result):
    """归因汇总防御性清洗：None/NaN 归零，避免 BacktestResponse 顶层 float 校验失败。"""
    summary = dict(attribution_result.get("summary", {}) or {})
    for key in ("allocation_effect", "selection_effect", "interaction_effect", "total_active_return"):
        val = summary.get(key)
        try:
            v = float(val)
            summary[key] = round(v, 2) if np.isfinite(v) else 0.0
        except Exception:
            summary[key] = 0.0
    by_industry = summary.get("by_industry") or {}
    clean_by_industry = {}
    for ind, vals in by_industry.items():
        if not isinstance(vals, dict):
            continue
        clean_vals = {}
        for k in ("allocation", "selection"):
            try:
                v = float(vals.get(k))
                clean_vals[k] = round(v, 2) if np.isfinite(v) else 0.0
            except Exception:
                clean_vals[k] = 0.0
        clean_by_industry[ind] = clean_vals
    summary["by_industry"] = clean_by_industry if clean_by_industry else None
    return AttributionSummary(**summary)


def _safe_validate_backtest_response(result_json_str):
    """读取路径防御：把 result_json 里归因相关的 None/NaN float 清洗后再校验。

    兼容历史任务数据（归因字段可能为 None），避免 status 接口 500。
    """
    import json as _json
    try:
        return BacktestResponse.model_validate_json(result_json_str)
    except Exception:
        data = _json.loads(result_json_str)
        attribution = data.get("attribution")
        if isinstance(attribution, dict):
            for key in ("allocation_effect", "selection_effect", "interaction_effect", "total_active_return"):
                val = attribution.get(key)
                try:
                    v = float(val)
                    attribution[key] = round(v, 2) if np.isfinite(v) else 0.0
                except Exception:
                    attribution[key] = 0.0
            by_industry = attribution.get("by_industry") or {}
            for ind, vals in by_industry.items():
                if isinstance(vals, dict):
                    for k in ("allocation", "selection"):
                        try:
                            v = float(vals.get(k))
                            vals[k] = round(v, 2) if np.isfinite(v) else 0.0
                        except Exception:
                            vals[k] = 0.0
        curve = data.get("attribution_curve")
        if isinstance(curve, list):
            for point in curve:
                if isinstance(point, dict):
                    for k in ("allocation", "selection", "interaction", "total_active"):
                        try:
                            v = float(point.get(k))
                            point[k] = round(v, 2) if np.isfinite(v) else 0.0
                        except Exception:
                            point[k] = 0.0
        return BacktestResponse.model_validate(data)


def _compute_brinson_attribution(
    positions_dict: dict,
    benchmark: str,
    start_date: str,
    end_date: str,
    instruments,
) -> Optional[dict]:
    """
    Brinson 绩效归因 — 将超额收益分解为配置效应、选股效应、交互效应

    基准采用 CSI300 等权近似（cn_data 不含成分股权重数据）
    """
    try:
        from qlib.data import D
        from backend.core.factor_utils import load_industry_mapping

        # 1. 获取交易日历和成分股
        calendars = D.calendar(freq="day")
        dates = sorted([
            d for d in calendars
            if pd.Timestamp(start_date) <= d <= pd.Timestamp(end_date)
        ])

        if len(dates) < 5:
            return None

        all_csi300 = D.list_instruments(instruments, as_list=True)

        # 2. 加载行业映射
        industry_map = load_industry_mapping(all_csi300)
        if not industry_map:
            return None

        # 3. 获取日收益
        close_raw = D.features(
            all_csi300, ["$close"],
            start_time=start_date, end_time=end_date, freq="day",
        )
        if close_raw is None or close_raw.empty:
            return None

        close_df = close_raw.reset_index().pivot(
            index="datetime", columns="instrument", values="$close"
        )
        daily_returns = close_df.pct_change().fillna(0)

        # 4. 构建每日持仓权重（前向填充）
        pos_weights_series = {}
        for dt_key in sorted(positions_dict.keys()):
            pos = positions_dict[dt_key]
            w = pos.get_stock_weight_dict(only_stock=False)
            w_filtered = {k: v for k, v in w.items() if k in all_csi300 and v > 0}
            if w_filtered:
                total = sum(w_filtered.values())
                w_filtered = {k: v / total for k, v in w_filtered.items()}
            pos_weights_series[dt_key] = w_filtered

        # 前向填充到所有交易日
        last_weights = {}
        filled_weights = {}
        for d in dates:
            if d in pos_weights_series:
                last_weights = pos_weights_series[d]
            filled_weights[d] = last_weights.copy() if last_weights else {}

        # 5. 逐日归因
        daily_raa = []  # 配置效应
        daily_rss = []  # 选股效应
        daily_rin = []  # 交互效应
        daily_active_return = []
        date_labels = []
        industry_contrib = {}  # {industry: {"allocation": cum, "selection": cum}}

        for d in dates:
            if d not in daily_returns.index:
                continue

            pw = filled_weights.get(d, {})
            if not pw:
                continue

            day_ret = daily_returns.loc[d]

            # 构建行业映射: code -> industry
            held_codes = list(pw.keys())
            held_industries = {}
            for c in held_codes:
                ind = industry_map.get(c, "其他")
                held_industries[c] = ind

            # CSI300 成分股当日的行业归属（等权基准）
            valid_csi = [c for c in all_csi300 if c in day_ret.index and pd.notna(day_ret[c])]
            if len(valid_csi) < 5:
                continue

            csi_industries = {}
            for c in valid_csi:
                csi_industries[c] = industry_map.get(c, "其他")

            # 6. 计算 Q1-Q4
            # 等权基准行业权重
            n_bench = len(valid_csi)
            bench_ind_weight = {}
            bench_ind_return = {}
            for c in valid_csi:
                ind = csi_industries[c]
                bench_ind_weight[ind] = bench_ind_weight.get(ind, 0) + 1.0 / n_bench
                bench_ind_return[ind] = bench_ind_return.get(ind, 0) + day_ret[c] / n_bench
            for ind in bench_ind_return:
                if bench_ind_weight[ind] > 0:
                    bench_ind_return[ind] /= bench_ind_weight[ind]

            # 策略行业权重和收益
            port_ind_weight = {}
            port_ind_return = {}
            for c, w in pw.items():
                if c not in day_ret.index or pd.isna(day_ret[c]):
                    continue
                ind = held_industries.get(c, "其他")
                port_ind_weight[ind] = port_ind_weight.get(ind, 0) + w
                port_ind_return[ind] = port_ind_return.get(ind, 0) + w * day_ret[c]
            for ind in port_ind_return:
                if port_ind_weight[ind] > 0:
                    port_ind_return[ind] /= port_ind_weight[ind]

            # Q1 = sum(bench_weight_i * bench_return_i) — 基准收益
            # Q2 = sum(port_weight_i * bench_return_i) — 配置收益
            # Q3 = sum(bench_weight_i * port_return_i) — 选股收益
            # Q4 = sum(port_weight_i * port_return_i) — 实际策略收益
            all_inds = set(list(bench_ind_weight.keys()) + list(port_ind_weight.keys()))

            Q1 = sum(bench_ind_weight.get(i, 0) * bench_ind_return.get(i, 0) for i in all_inds)
            Q2 = sum(port_ind_weight.get(i, 0) * bench_ind_return.get(i, 0) for i in all_inds)
            Q3 = sum(bench_ind_weight.get(i, 0) * port_ind_return.get(i, 0) for i in all_inds)
            Q4 = sum(port_ind_weight.get(i, 0) * port_ind_return.get(i, 0) for i in all_inds)

            raa = Q2 - Q1
            rss = Q3 - Q1
            rin = Q4 - Q3 - Q2 + Q1

            daily_raa.append(raa)
            daily_rss.append(rss)
            daily_rin.append(rin)
            daily_active_return.append(Q4 - Q1)
            date_labels.append(d.strftime("%Y-%m-%d"))

            # 行业贡献
            for ind in all_inds:
                bw = bench_ind_weight.get(ind, 0)
                pw_i = port_ind_weight.get(ind, 0)
                br = bench_ind_return.get(ind, 0)
                pr = port_ind_return.get(ind, 0)
                alloc_c = (pw_i - bw) * br  # 行业配置贡献
                selec_c = bw * (pr - br)    # 行业选股贡献
                if ind not in industry_contrib:
                    industry_contrib[ind] = {"allocation": 0.0, "selection": 0.0}
                industry_contrib[ind]["allocation"] += alloc_c
                industry_contrib[ind]["selection"] += selec_c

        if len(daily_raa) < 5:
            return None

        # 7. 累计归因（乘法复合）
        raa_arr = np.array(daily_raa)
        rss_arr = np.array(daily_rss)
        rin_arr = np.array(daily_rin)
        active_arr = np.array(daily_active_return)

        cum_raa = (1 + raa_arr).cumprod() - 1
        cum_rss = (1 + rss_arr).cumprod() - 1
        cum_rin = (1 + rin_arr).cumprod() - 1
        cum_active = (1 + active_arr).cumprod() - 1

        # 8. 构建归因曲线（防御性清洗：NaN/inf 归零，避免 Pydantic float 校验失败）
        def _safe_pct(val):
            v = float(val) * 100
            if not np.isfinite(v):
                return 0.0
            return round(v, 2)

        curve = []
        for i in range(len(date_labels)):
            curve.append({
                "date": date_labels[i],
                "allocation": _safe_pct(cum_raa[i]),
                "selection": _safe_pct(cum_rss[i]),
                "interaction": _safe_pct(cum_rin[i]),
                "total_active": _safe_pct(cum_active[i]),
            })

        # 9. 行业贡献（乘以100转为百分比）
        by_industry = {}
        for ind, v in sorted(industry_contrib.items(),
                             key=lambda x: abs(x[1]["allocation"] + x[1]["selection"]),
                             reverse=True):
            by_industry[ind] = {
                "allocation": round(v["allocation"] * 100, 2),
                "selection": round(v["selection"] * 100, 2),
            }

        # 10. 汇总
        alloc_term = float(cum_raa[-1]) * 100
        selec_term = float(cum_rss[-1]) * 100
        inter_term = float(cum_rin[-1]) * 100
        total_term = float(cum_active[-1]) * 100

        # 11. 解读文本
        if abs(alloc_term) > abs(selec_term):
            main_type = "行业配置"
            main_val = alloc_term
        else:
            main_type = "选股能力"
            main_val = selec_term

        if total_term > 0:
            interp = (
                f"回测期间，策略相对CSI300基准取得了 {total_term:.2f}% 的超额收益。"
                f"其中，{main_type}是主要贡献来源（{main_val:+.2f}%）。"
            )
        else:
            interp = (
                f"回测期间，策略相对CSI300基准落后 {abs(total_term):.2f}%。"
                f"其中，{main_type}是主要拖累因素（{main_val:+.2f}%）。"
            )

        if abs(inter_term) > abs(total_term) * 0.1:
            interp += f"交互效应为 {inter_term:+.2f}%，表明行业配置与选股之间存在一定协同/抵消。"
        else:
            interp += "配置与选股的交互效应较小，两者较为独立。"

        interp += "（注：基准采用CSI300等权近似，非真实市值加权。）"

        return {
            "summary": {
                "allocation_effect": round(alloc_term, 2),
                "selection_effect": round(selec_term, 2),
                "interaction_effect": round(inter_term, 2),
                "total_active_return": round(total_term, 2),
                "by_industry": by_industry if by_industry else None,
            },
            "curve": curve,
            "interpretation": interp,
            "industry_map": industry_map,
            "main_driver": main_type,
        }

    except Exception as e:
        logger.warning(f"Brinson 归因计算失败: {e}")
        return None


def _generate_buy_reason(score: float, name: str, code: str = "",
                          industry_map: dict = None, industry_contrib: dict = None,
                          main_driver: str = "") -> str:
    """生成买入推荐理由（含 Brinson 归因上下文）"""
    base = ""
    if score > 0.05:
        base = f"{name} Alpha158 综合评分领先，模型预测收益显著为正"
    elif score > 0.02:
        base = f"{name} 因子信号偏强，多因子模型看好"
    else:
        base = f"{name} 评分排名靠前，建议关注"

    # 加入归因上下文
    if industry_map and code in industry_map:
        industry = industry_map[code]
        if industry_contrib and industry in industry_contrib:
            contrib = industry_contrib[industry]
            selec = contrib.get("selection", 0)
            alloc = contrib.get("allocation", 0)
            if selec > 0.5:
                base += f"，所在行业「{industry}」选股贡献 +{selec:.1f}%"
            elif selec < -0.5:
                base += f"，所在行业「{industry}」选股贡献 {selec:.1f}%"
            if alloc < -0.5:
                base += f"（配置效应 {alloc:.1f}%，建议控制仓位）"
        elif main_driver == "行业配置":
            base += f"，本期超额收益主要来自行业配置效应"

    return base


def _generate_sell_reason(score: float, name: str, code: str = "",
                           industry_map: dict = None, industry_contrib: dict = None,
                           main_driver: str = "") -> str:
    """生成卖出推荐理由（含 Brinson 归因上下文）"""
    base = ""
    if score < -0.05:
        base = f"{name} 模型预测收益显著为负，建议回避"
    elif score < -0.02:
        base = f"{name} 因子信号偏弱，预测收益下行"
    else:
        base = f"{name} 评分排名靠后，建议减仓"

    if industry_map and code in industry_map:
        industry = industry_map[code]
        if industry_contrib and industry in industry_contrib:
            contrib = industry_contrib[industry]
            selec = contrib.get("selection", 0)
            if selec < -0.5:
                base += f"，所在行业「{industry}」选股效应为负（{selec:.1f}%）"

    return base


def _format_report_percent(value) -> str:
    if value is None:
        return "暂无可靠数据"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "暂无可靠数据"


def _format_report_number(value) -> str:
    if value is None:
        return "暂无可靠数据"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "暂无可靠数据"


def build_backtest_markdown_report(task: dict) -> str:
    result = json.loads(task.get("result_json") or "{}")
    params = json.loads(task.get("params_json") or "{}")
    lines = [
        "# 回测报告",
        "",
        f"- 任务 ID：{task.get('task_id', '未知')}",
        f"- 状态：{task.get('status', '未知')}",
        f"- 创建时间：{task.get('created_at') or '暂无可靠数据'}",
        f"- 更新时间：{task.get('updated_at') or '暂无可靠数据'}",
        "",
        "## 参数摘要",
        "",
    ]

    if params:
        for key in sorted(params):
            lines.append(f"- {key}：{params[key]}")
    else:
        lines.append("- 暂无可靠参数记录")

    lines.extend([
        "",
        "## 核心指标",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| 总收益率 | {_format_report_percent(result.get('total_return'))} |",
        f"| 年化收益率 | {_format_report_percent(result.get('annual_return'))} |",
        f"| 最大回撤 | {_format_report_percent(result.get('max_drawdown'))} |",
        f"| 夏普比率 | {_format_report_number(result.get('sharpe_ratio'))} |",
        f"| 胜率 | {_format_report_percent(result.get('win_rate'))} |",
    ])

    if result.get("cost_impact_estimate"):
        lines.extend(["", "## 交易成本提示", "", str(result["cost_impact_estimate"])])

    if result.get("position_advice"):
        lines.extend(["", "## 仓位建议", "", str(result["position_advice"])])

    top_buys = result.get("top_buys") or []
    if top_buys:
        lines.extend(["", "## 推荐关注", "", "| 代码 | 名称 | 分数 | 理由 |", "| --- | --- | ---: | --- |"])
        for item in top_buys[:10]:
            lines.append(
                f"| {item.get('code', '')} | {item.get('name', '')} | {_format_report_number(item.get('score'))} | {item.get('reason', '')} |"
            )

    warnings = result.get("warnings") or []
    if warnings:
        lines.extend(["", "## 风险与缺口", ""])
        for warning in warnings:
            lines.append(f"- {warning}")

    lines.extend([
        "",
        "---",
        "本报告由本地 Qlib 量化平台根据已保存的回测结果生成，仅供研究复盘，不构成投资建议。",
    ])
    return "\n".join(lines) + "\n"


@router.post("/run")
async def run_backtest(params: BacktestParams, background_tasks: BackgroundTasks):
    """
    启动回测任务
    """
    params.model = validate_backtest_model_available(params.model)
    task_id = str(uuid.uuid4())
    try:
        task_store.init_db()
        task_store.create_task(task_id, params.model_dump_json())
    except Exception as e:
        logger.error(f"创建回测任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建回测任务失败: {e}")

    background_tasks.add_task(run_backtest_task, task_id, params)

    return {
        "task_id": task_id,
        "status": "running",
        "message": "回测任务已启动"
    }


@router.get("/status/{task_id}")
async def get_backtest_status(task_id: str):
    """
    获取回测任务状态
    """
    task = task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task["status"] == "completed" and task["result_json"]:
        return _safe_validate_backtest_response(task["result_json"])
    elif task["status"] == "failed":
        return BacktestResponse(
            task_id=task_id,
            status="failed",
            error=task["error"]
        )
    else:
        return BacktestResponse(
            task_id=task_id,
            status="running",
            progress=task["progress"]
        )


@router.get("/report/{task_id}.md")
async def export_backtest_report(task_id: str):
    """导出已完成回测的 Markdown 报告。"""
    task = task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.get("status") != "completed" or not task.get("result_json"):
        raise HTTPException(status_code=400, detail="只有已完成且包含结果的回测任务可以导出报告")

    markdown = build_backtest_markdown_report(task)
    filename = f"backtest-report-{task_id}.md"
    return Response(
        content=markdown.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/tasks/{task_id}")
async def delete_backtest_task(task_id: str):
    """
    删除回测任务
    """
    task_store.delete_task(task_id)
    return {"message": "任务已删除"}


@router.get("/tasks")
async def list_backtest_tasks(limit: int = 50):
    """获取历史回测任务列表"""
    tasks = task_store.list_tasks(limit)
    return {"tasks": tasks, "total": len(tasks)}
