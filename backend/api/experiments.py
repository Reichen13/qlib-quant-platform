"""MLflow 实验管理 API — 查看回测实验历史与对比"""

import os
os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
import mlflow
from mlflow.tracking import MlflowClient
from pathlib import Path

router = APIRouter()
TRACKING_URI = f"file:///{Path.home()}/.qlib/mlruns"
mlflow.set_tracking_uri(TRACKING_URI)


@router.get("/experiments")
async def list_experiments():
    """列出所有实验（策略名称）及其最新运行摘要"""
    try:
        client = MlflowClient(tracking_uri=TRACKING_URI)
        experiments = []
        for exp in client.search_experiments():
            runs = client.search_runs(
                experiment_ids=[exp.experiment_id],
                order_by=["start_time DESC"],
                max_results=5,
            )
            run_summaries = []
            for r in runs:
                run_summaries.append({
                    "run_id": r.info.run_id,
                    "run_name": r.info.run_name,
                    "start_time": str(r.info.start_time),
                    "metrics": r.data.metrics,
                    "tags": r.data.tags,
                })
            experiments.append({
                "experiment_id": exp.experiment_id,
                "name": exp.name,
                "artifact_location": exp.artifact_location,
                "runs": run_summaries,
            })
        return {"experiments": experiments, "total": len(experiments)}
    except Exception as e:
        logger.error(f"获取实验列表失败: {e}")
        return {"experiments": [], "total": 0, "warning": str(e)}


@router.get("/experiments/{experiment_id}/runs")
async def list_runs(
    experiment_id: str,
    limit: int = Query(50, ge=5, le=200),
    sort_by: str = Query("metrics.sharpe_ratio", description="排序字段"),
):
    """列出指定实验的所有运行记录，按指标排序"""
    try:
        client = MlflowClient(tracking_uri=TRACKING_URI)
        runs = client.search_runs(
            experiment_ids=[experiment_id],
            order_by=[f"{sort_by} DESC"],
            max_results=limit,
        )
        records = []
        for r in runs:
            records.append({
                "run_id": r.info.run_id,
                "run_name": r.info.run_name,
                "start_time": str(r.info.start_time),
                "metrics": r.data.metrics,
                "params": r.data.params,
                "tags": r.data.tags,
            })
        return {"runs": records, "total": len(records)}
    except Exception as e:
        logger.error(f"获取运行列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/best")
async def get_best_runs(
    metric: str = Query("metrics.sharpe_ratio", description="排序指标"),
    limit: int = Query(10, ge=1, le=50),
    regime: str = Query("", description="市场环境过滤：bull/correction/bear/neutral"),
):
    """获取全局最佳运行——可跨实验、可按市场环境过滤"""
    try:
        client = MlflowClient(tracking_uri=TRACKING_URI)
        all_runs = []
        for exp in client.search_experiments():
            filter_str = ""
            if regime:
                filter_str = f"tags.market_regime = '{regime}'"
            runs = client.search_runs(
                experiment_ids=[exp.experiment_id],
                filter_string=filter_str,
                order_by=[f"{metric} DESC"],
                max_results=limit * 2,
            )
            for r in runs:
                all_runs.append({
                    "run_id": r.info.run_id,
                    "experiment": exp.name,
                    "run_name": r.info.run_name,
                    "start_time": str(r.info.start_time),
                    "metrics": r.data.metrics,
                    "params": r.data.params,
                    "tags": r.data.tags,
                })
        all_runs.sort(key=lambda x: x["metrics"].get(metric.replace("metrics.", ""), 0), reverse=True)
        return {"runs": all_runs[:limit], "total": len(all_runs), "filtered_by": {"metric": metric, "regime": regime}}
    except Exception as e:
        logger.error(f"获取最佳运行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regimes")
async def get_available_regimes():
    """列出所有已记录的市场环境标签及其计数"""
    try:
        client = MlflowClient(tracking_uri=TRACKING_URI)
        regime_counts = {}
        for exp in client.search_experiments():
            runs = client.search_runs(experiment_ids=[exp.experiment_id], max_results=500)
            for r in runs:
                tag = r.data.tags.get("market_regime", "unknown")
                regime_counts[tag] = regime_counts.get(tag, 0) + 1
        return {"regimes": [
            {"regime": k, "count": v}
            for k, v in sorted(regime_counts.items(), key=lambda x: -x[1])
        ]}
    except Exception as e:
        logger.error(f"获取市场环境标签失败: {e}")
        return {"regimes": [], "warning": str(e)}
