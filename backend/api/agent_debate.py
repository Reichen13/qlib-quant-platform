"""
多智能体辩论 API

- POST /api/agent/analyze    单股多智能体分析
- GET  /api/agent/report/{id} 获取分析报告
- GET  /api/agent/memory/{code} 历史记忆
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from loguru import logger

router = APIRouter()

# 内存报告存储
_report_store: dict = {}


def _check_llm():
    try:
        from core.llm_client import get_llm_config
        if not get_llm_config().is_configured:
            raise HTTPException(
                status_code=503,
                detail="LLM 未配置。请设置 LLM_BASE_URL 和 LLM_API_KEY 环境变量。",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


def _run_analysis_task(task_id: str, code: str):
    """后台运行多智能体分析"""
    try:
        from core.multi_agent import get_orchestrator
        orch = get_orchestrator()
        report = orch.run_full_pipeline(code)
        _report_store[task_id] = {
            "status": "completed",
            "report": report.model_dump(),
        }
    except Exception as e:
        logger.error(f"多智能体分析失败 ({task_id}): {e}")
        _report_store[task_id] = {
            "status": "failed",
            "error": str(e),
        }


@router.post("/analyze")
async def analyze_stock(
    code: str,
    background_tasks: BackgroundTasks,
    async_mode: bool = True,
):
    """单股多智能体分析

    Args:
        code: yfinance 格式代码，如 "600519.SS"
        async_mode: 是否异步执行（默认 true）

    Returns:
        task_id 用于后续查询报告
    """
    _check_llm()

    import uuid
    task_id = str(uuid.uuid4())[:8]

    if async_mode:
        background_tasks.add_task(_run_analysis_task, task_id, code)
        _report_store[task_id] = {"status": "running"}
        return {
            "task_id": task_id,
            "code": code,
            "status": "running",
            "message": "多智能体分析已启动，请使用 task_id 查询结果",
        }
    else:
        # 同步模式
        from core.multi_agent import get_orchestrator
        orch = get_orchestrator()
        report = orch.run_full_pipeline(code)
        _report_store[task_id] = {
            "status": "completed",
            "report": report.model_dump(),
        }
        return {
            "task_id": task_id,
            "code": code,
            "status": "completed",
            "report": report.model_dump(),
        }


@router.get("/report/{task_id}")
async def get_report(task_id: str):
    """获取多智能体分析报告

    Args:
        task_id: analyze 端点返回的任务 ID
    """
    entry = _report_store.get(task_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"未找到任务: {task_id}")
    return {"task_id": task_id, **entry}


@router.get("/memory/{code}")
async def get_memory(code: str):
    """获取股票的历史分析记忆

    Args:
        code: yfinance 格式代码
    """
    try:
        from core.multi_agent import get_orchestrator
        orch = get_orchestrator()
        memory = orch.get_memory(code)
        return {
            "code": code,
            "has_memory": bool(memory),
            "memory": memory if memory else "暂无分析记录",
        }
    except Exception as e:
        return {"code": code, "has_memory": False, "error": str(e)}
