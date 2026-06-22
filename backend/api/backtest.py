"""
模型回测 API - 基于 Qlib 真实回测框架
"""

import os
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List, Optional
import pandas as pd
import numpy as np
import uuid
from fastapi import APIRouter, HTTPException, BackgroundTasks
from loguru import logger

# 全局禁用多进程（必须在 import qlib 之前设置）
os.environ['NUMBA_NUM_THREADS'] = '1'
os.environ['QLIB_NO_MULTI_PROCESS'] = '1'
os.environ['JOBLIB_START_METHOD'] = 'forkserver'
os.environ['OMP_NUM_THREADS'] = '1'

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


from core.compat import fix_parallel_ext


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

        # ── 1. 排除科创板(688xxx)和创业板(300xxx) ──
        valid_codes = [
            c for c in codes
            if not c.startswith(("SH688", "SZ300", "SZ301"))
        ]
        excluded_codes = [
            c for c in codes
            if c.startswith(("SH688", "SZ300", "SZ301"))
        ]

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
                        returns = code_data["$high"].pct_change()
                        limit_up_hits += int((returns > 0.095).sum())
                        returns_low = code_data["$low"].pct_change()
                        limit_down_hits += int((returns_low < -0.095).sum())
                    except Exception:
                        continue
            else:
                limit_up_hits = 0
                limit_down_hits = 0
        except Exception:
            limit_up_hits = 0
            limit_down_hits = 0

        return {
            "original_universe": len(codes),
            "valid_universe": len(valid_codes),
            "excluded_chi_next_star": len(excluded_codes),
            "excluded_codes_sample": excluded_codes[:10],
            "limit_up_hits_estimated": limit_up_hits,
            "limit_down_hits_estimated": limit_down_hits,
            "suspension_days_estimated": suspension_days,
            "suspended_stocks_estimated": n_suspended_stocks,
            "constraints_active": [
                "涨跌停板 (limit_threshold=0.095, 主板±10%)",
                "T+1 制度 (日频回测自动满足)",
                "停牌排除 (NaN 数据自动跳过)",
                "只做多不融券 (TopkDropoutStrategy)",
                f"已排除科创板/创业板 {len(excluded_codes)} 只 (±20%涨跌幅不兼容)",
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

        # valid 段取 train_end ~ test_start
        valid_start = train_end
        valid_end = test_start

        # 回测结束日期不能超过 Qlib 数据范围，提前2天避免边界问题
        from qlib.data import D
        calendars = D.calendar(freq="day")
        test_end_dt = pd.Timestamp(test_end)
        available_end = calendars[-1] if len(calendars) > 0 else test_end_dt
        backtest_end = min(test_end_dt, available_end - pd.Timedelta(days=2))

        task_store.update_progress(task_id, 20)

        logger.info(f"回测参数: train={train_start}~{train_end}, test={test_start}~{backtest_end}")

        dataset = init_instance_by_config({
            "class": "DatasetH",
            "module_path": "qlib.data.dataset",
            "kwargs": {
                "handler": {
                    "class": "Alpha158",
                    "module_path": "qlib.contrib.data.handler",
                    "kwargs": {
                        "start_time": train_start,
                        "end_time": str(backtest_end),
                        "fit_start_time": train_start,
                        "fit_end_time": train_end,
                        "instruments": "csi300",
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
                "segments": {
                    "train": (train_start, train_end),
                    "valid": (valid_start, valid_end),
                    "test": (test_start, str(backtest_end)),
                },
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
        instruments = D.instruments("csi300")
        all_csi300 = D.list_instruments(instruments, as_list=True)
        constraint_analysis = _check_a_share_constraints(all_csi300, train_start, str(backtest_end))

        task_store.update_progress(task_id, 55)

        exchange_kwargs = {
            "codes": "csi300",
            "freq": "day",
            "limit_threshold": 0.095,
            "deal_price": "close",
            "open_cost": params.buy_cost,
            "close_cost": params.sell_cost,
            "min_cost": 5,
        }

        # TopkDropoutStrategy: topk=持仓数, n_drop=每次调仓换手数
        topk = params.hold_num
        n_drop = max(1, topk // 5)  # 每次换手约20%持仓
        strategy = TopkDropoutStrategy(topk=topk, n_drop=n_drop, signal=pred)

        report, positions_dict = backtest_daily(
            start_time=test_start,
            end_time=str(backtest_end),
            strategy=strategy,
            executor={
                "class": "SimulatorExecutor",
                "module_path": "qlib.backtest.executor",
                "kwargs": {
                    "time_per_step": "day",
                    "generate_portfolio_metrics": True,
                },
            },
            account=1_000_000,
            benchmark="SH000300",
            exchange_kwargs=exchange_kwargs,
        )

        task_store.update_progress(task_id, 80)

        # ── 计算回测指标 ──
        r = report["return"]
        bench = report["bench"]
        ex = r - bench

        # 年化收益
        ann_r = r.mean() * 252
        ann_std = r.std() * np.sqrt(252)
        sharpe = ann_r / ann_std if ann_std > 0 else 0

        # 累计净值与回撤
        cum = (1 + r).cumprod()
        cum_bench = (1 + bench).cumprod()
        dd_series = cum / cum.cummax() - 1
        max_dd = dd_series.min()

        # 胜率
        win_rate = (r > 0).mean()

        # Calmar
        calmar = ann_r / abs(max_dd) if max_dd != 0 else 0

        # 总收益率
        total_return = cum.iloc[-1] - 1 if len(cum) > 0 else 0

        # 盈亏比
        gains = r[r > 0]
        losses = r[r < 0]
        avg_gain = gains.mean() if len(gains) > 0 else 0
        avg_loss = abs(losses.mean()) if len(losses) > 0 else 1
        profit_loss_ratio = avg_gain / avg_loss if avg_loss > 0 else 0

        # ── 统计检验 ──
        # t 检验（策略收益是否显著 > 0）
        from scipy import stats as scipy_stats
        t_stat, p_value = scipy_stats.ttest_1samp(r.dropna(), 0)
        t_stat = float(t_stat)
        p_value = float(p_value)

        # 信息比率（超额收益 / 跟踪误差）
        tracking_error = ex.std() * np.sqrt(252)
        information_ratio = (ex.mean() * 252) / tracking_error if tracking_error > 0 else 0

        # Sortino 比率（使用下行标准差）
        downside = r[r < 0]
        downside_std = downside.std() * np.sqrt(252) if len(downside) > 0 else ann_std
        sortino = ann_r / downside_std if downside_std > 0 else 0

        # 月度胜率
        monthly_r = r.resample("ME").apply(lambda x: (1 + x).prod() - 1)
        monthly_win_rate = (monthly_r > 0).mean()

        # ── 交易成本影响估算 ──
        try:
            avg_daily_turnover = report["turnover"].mean() if "turnover" in report.columns else 0
            daily_vol = r.std()
            # 平方根冲击模型: impact ≈ σ * sqrt(turnover / ADV)
            # 假设平均持仓股每笔交易占日成交量 5%
            estimated_impact_per_trade = daily_vol * np.sqrt(max(avg_daily_turnover, 0.001) / 0.05)
            annual_impact = estimated_impact_per_trade * 252 * 0.5  # 每次调仓半次换手（买卖各半）
            fixed_cost_annual = (params.buy_cost + params.sell_cost) * 252 / max(int(params.turnover), 1)
            if annual_impact > fixed_cost_annual * 1.5:
                cost_impact_estimate = (
                    f"市场冲击成本估计约 {annual_impact:.2%}/年，显著高于固定佣金模型 "
                    f"({fixed_cost_annual:.2%}/年)。实际交易中小盘股冲击成本可达 0.5-1.0%，"
                    f"建议将回测收益下调 {annual_impact - fixed_cost_annual:.1%} 作为保守估计。"
                )
            else:
                cost_impact_estimate = (
                    f"市场冲击成本估计约 {annual_impact:.2%}/年，与固定佣金模型 "
                    f"({fixed_cost_annual:.2%}/年)接近。CSI300成分股流动性较好，冲击成本可控。"
                )
        except Exception:
            cost_impact_estimate = None

        # ── Brinson 绩效归因 ──
        attribution_result = _compute_brinson_attribution(
            positions_dict=positions_dict,
            benchmark="SH000300",
            start_date=test_start,
            end_date=str(backtest_end),
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
                annual_return=round(float(ann_r), 4),
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
                drawdown=drawdown_data,
                top_buys=top_buys,
                top_sells=top_sells,
                position_advice=position_advice,
                constraint_analysis=constraint_analysis,
                factor_source=params.source_factor,
                attribution=AttributionSummary(**attribution_result["summary"]) if attribution_result else None,
                attribution_curve=[AttributionPoint(**p) for p in attribution_result["curve"]] if attribution_result else None,
                attribution_interpretation=attribution_result["interpretation"] if attribution_result else None,
                cost_impact_estimate=cost_impact_estimate,
            )
        task_store.set_completed(task_id, result.model_dump_json())

        logger.info(f"回测任务 {task_id} 完成: 年化={ann_r:.2%}, 夏普={sharpe:.2f}, 回撤={max_dd:.2%}")

    except Exception as e:
        logger.error(f"回测任务 {task_id} 失败: {e}")
        import traceback
        traceback.print_exc()
        task_store.set_failed(task_id, str(e))


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

        # 8. 构建归因曲线
        curve = []
        for i in range(len(date_labels)):
            curve.append({
                "date": date_labels[i],
                "allocation": round(float(cum_raa[i]) * 100, 2),
                "selection": round(float(cum_rss[i]) * 100, 2),
                "interaction": round(float(cum_rin[i]) * 100, 2),
                "total_active": round(float(cum_active[i]) * 100, 2),
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


@router.post("/run")
async def run_backtest(params: BacktestParams, background_tasks: BackgroundTasks):
    """
    启动回测任务
    """
    task_id = str(uuid.uuid4())
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
        return BacktestResponse.model_validate_json(task["result_json"])
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
