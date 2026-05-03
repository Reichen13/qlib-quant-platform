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
    StockRecommendation, EquityPoint, DrawdownPoint
)

router = APIRouter()

# 导入核心模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from stock_names import get_stock_name

# 回测任务存储（生产环境应使用 Redis）
backtest_tasks = {}


def _fix_parallel_ext():
    """修复 Qlib 0.9.6 与 joblib 1.5+ 的兼容性问题
    joblib 1.5+ 将 _backend_args 改名为 _backend_kwargs，
    导致 Qlib 的 ParallelExt 访问 _backend_args 时 AttributeError。
    """
    try:
        from qlib.utils.paral import ParallelExt
        from joblib._parallel_backends import MultiprocessingBackend

        def _new_init(self, *args, **kwargs):
            maxtasksperchild = kwargs.pop("maxtasksperchild", None)
            super(ParallelExt, self).__init__(*args, **kwargs)
            # 兼容新旧版本 joblib
            backend_args = getattr(self, '_backend_kwargs', getattr(self, '_backend_args', None))
            if backend_args is not None and isinstance(self._backend, MultiprocessingBackend):
                backend_args["maxtasksperchild"] = maxtasksperchild

        ParallelExt.__init__ = _new_init
        logger.info("ParallelExt 兼容性补丁已应用 (joblib 1.5+)")
    except Exception as e:
        logger.warning(f"ParallelExt 补丁失败: {e}")


def run_backtest_task(task_id: str, params: BacktestParams):
    """
    执行回测任务（后台运行）- 使用真实 Qlib 框架
    """
    try:
        backtest_tasks[task_id] = {
            "status": "running",
            "progress": 5,
            "result": None,
            "error": None
        }

        import qlib
        from qlib.utils import init_instance_by_config
        from qlib.contrib.evaluate import backtest_daily
        from qlib.contrib.strategy import TopkDropoutStrategy

        # 单线程模式，避免多进程冲突
        qlib.config.N_PROC = 1

        # 修复 ParallelExt 兼容性
        _fix_parallel_ext()

        backtest_tasks[task_id]["progress"] = 10

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

        backtest_tasks[task_id]["progress"] = 20

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

        backtest_tasks[task_id]["progress"] = 40

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

        backtest_tasks[task_id]["progress"] = 60

        # ── 执行回测 ──
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

        report, _ = backtest_daily(
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

        backtest_tasks[task_id]["progress"] = 80

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

        backtest_tasks[task_id]["progress"] = 90

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

        # ── 生成买卖推荐 ──
        top_buys = []
        top_sells = []

        try:
            pred_df = pred.reset_index()
            pred_df.columns = ['日期', '代码', '预测得分']

            # 取最新日期的预测
            latest_date = pred_df['日期'].max()
            latest_pred = pred_df[pred_df['日期'] == latest_date].copy()
            latest_pred = latest_pred.sort_values('预测得分', ascending=False)

            # 买入推荐 (Top K)
            for _, row in latest_pred.head(topk).iterrows():
                code = str(row['代码']).upper()
                score = float(row['预测得分'])
                name = get_stock_name(code)
                reason = _generate_buy_reason(score, name)
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
                reason = _generate_sell_reason(score, name)
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

        backtest_tasks[task_id] = {
            "status": "completed",
            "progress": 100,
            "result": BacktestResponse(
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
                equity=equity_data,
                drawdown=drawdown_data,
                top_buys=top_buys,
                top_sells=top_sells,
                position_advice=position_advice,
            ),
            "error": None
        }

        logger.info(f"回测任务 {task_id} 完成: 年化={ann_r:.2%}, 夏普={sharpe:.2f}, 回撤={max_dd:.2%}")

    except Exception as e:
        logger.error(f"回测任务 {task_id} 失败: {e}")
        import traceback
        traceback.print_exc()
        backtest_tasks[task_id] = {
            "status": "failed",
            "progress": 0,
            "result": None,
            "error": str(e)
        }


def _generate_buy_reason(score: float, name: str) -> str:
    """生成买入推荐理由"""
    if score > 0.05:
        return f"{name} Alpha158 综合评分领先，模型预测收益显著为正"
    elif score > 0.02:
        return f"{name} 因子信号偏强，多因子模型看好"
    else:
        return f"{name} 评分排名靠前，建议关注"


def _generate_sell_reason(score: float, name: str) -> str:
    """生成卖出推荐理由"""
    if score < -0.05:
        return f"{name} 模型预测收益显著为负，建议回避"
    elif score < -0.02:
        return f"{name} 因子信号偏弱，预测收益下行"
    else:
        return f"{name} 评分排名靠后，建议减仓"


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
    if task_id not in backtest_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = backtest_tasks[task_id]

    if task["status"] == "completed" and task["result"]:
        return task["result"]
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
    if task_id in backtest_tasks:
        del backtest_tasks[task_id]
        return {"message": "任务已删除"}
    else:
        raise HTTPException(status_code=404, detail="任务不存在")
