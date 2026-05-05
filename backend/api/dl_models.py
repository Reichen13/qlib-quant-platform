"""
深度学习 API

- GET  /api/dl-models/list       模型列表
- POST /api/dl-models/train      训练模型
- GET  /api/dl-models/status/{id} 训练状态
"""

from fastapi import APIRouter, HTTPException
from loguru import logger

from core.dl_models import get_available_models, start_training, get_training_status

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
    if model_name not in ["alstm", "hist", "transformer", "tra", "ddg_da"]:
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
