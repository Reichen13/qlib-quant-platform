"""
深度学习 API

- GET  /api/dl-models/list       模型列表
- POST /api/dl-models/train      训练模型
- GET  /api/dl-models/status/{id} 训练状态
"""

from fastapi import APIRouter, HTTPException
from loguru import logger

from core.dl_models import (
    get_available_models,
    start_training,
    get_training_status,
    start_prediction,
    get_prediction_status,
    get_latest_prediction,
)

router = APIRouter()


@router.get("/list")
async def list_models():
    """获取可用深度学习模型列表"""
    models = get_available_models()
    return {
        "total": len(models),
        "models": models,
    }


@router.post("/train")
async def train_model(model_name: str, config: dict | None = None):
    """训练深度学习模型（桩实现）

    注意: 完整训练需要 PyTorch + Qlib 完整依赖环境。
    当前版本返回模型配置信息供参考。
    """
    if model_name not in ["alstm", "hist", "transformer", "tra", "gru"]:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的模型: {model_name}。可选: alstm, hist, transformer, tra, ddg_da",
        )

    try:
        task_id = start_training(model_name, config)
        status = get_training_status(task_id)
        logger.info(f"DL 训练任务: {model_name}, task_id={task_id}")
        return {"task_id": task_id, **status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status/{task_id}")
async def training_status(task_id: str):
    """获取训练任务状态"""
    status = get_training_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"未找到训练任务: {task_id}")
    return {"task_id": task_id, **status}

@router.post("/predict/{model_name}")
async def predict_model(model_name: str, top_n: int = 20):
    """使用已训练的 DL 模型对最新数据运行预测，返回预测得分最高的 N 只股票。"""
    try:
        task_id = start_prediction(model_name, top_n)
        status = get_prediction_status(task_id)
        logger.info(f"DL 预测任务: {model_name}, task_id={task_id}")
        return {"task_id": task_id, **status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/predict/status/{task_id}")
async def prediction_status(task_id: str):
    """查询预测任务状态。"""
    status = get_prediction_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"未找到预测任务: {task_id}")
    return {"task_id": task_id, **status}


@router.get("/predict/latest/{model_name}")
async def latest_prediction(model_name: str):
    """获取某个模型最近一次完成的预测结果。"""
    result = get_latest_prediction(model_name)
    if not result:
        raise HTTPException(status_code=404, detail=f"模型 {model_name} 还没有完成的预测")
    return result


@router.get("/signal")
async def dl_signal(top_n: int = 10):
    """获取所有已训练模型的最新预测信号，汇总到一个列表。

    对每个已训练模型取前 top_n 只，合并后按预测得分排序。
    """
    models = get_available_models()
    all_signals = []
    for m in models:
        if not m.get("is_trained"):
            continue
        pred = get_latest_prediction(m["id"])
        if not pred or "predictions" not in pred:
            continue
        for item in pred["predictions"][:top_n]:
            all_signals.append({
                **item,
                "model": m["id"],
                "model_name": m["full_name"],
                "pred_date": pred.get("pred_date", ""),
            })

    all_signals.sort(key=lambda x: x["score"], reverse=True)

    active_models = [m["id"] for m in models if m.get("is_trained")]
    return {
        "total": len(all_signals),
        "active_models": active_models,
        "signals": all_signals[:top_n * len(active_models)] if active_models else [],
    }
