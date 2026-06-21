"""
多智能体辩论 API

- POST /api/agent/analyze    单股多智能体分析
- GET  /api/agent/report/{id} 获取分析报告
- GET  /api/agent/memory/{code} 历史记忆

报告通过 SQLite 持久化存储，服务重启不丢失。
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from loguru import logger
from utils.code_normalization import normalize_stock_code

router = APIRouter()

# 内存缓存（加速查询），持久化在 SQLite
_report_cache: dict = {}


def _check_llm(api_key: Optional[str] = None):
    if api_key:
        return
    try:
        from core.llm_client import get_llm_config
        if not get_llm_config().is_configured:
            raise HTTPException(
                status_code=503,
                detail="LLM 未配置。请在设置页面输入您的 API Key。",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


def _run_analysis_task(task_id: str, code: str, api_key: Optional[str] = None, base_url: Optional[str] = None):
    """后台运行多智能体分析"""
    try:
        from core.multi_agent import get_orchestrator
        from core.llm_client import create_llm_client
        from db.report_store import save_report

        orch = get_orchestrator()
        if api_key:
            orch.set_llm_client(create_llm_client(api_key=api_key, base_url=base_url or ""))

        report = orch.run_full_pipeline(code)
        report_dict = report.model_dump()
        _report_cache[task_id] = {"status": "completed", "report": report_dict}
        save_report(task_id, code, "completed", report=report_dict)
    except Exception as e:
        logger.error(f"多智能体分析失败 ({task_id}): {e}")
        _report_cache[task_id] = {"status": "failed", "error": str(e)}
        from db.report_store import save_report
        save_report(task_id, code, "failed", error=str(e))


@router.post("/analyze")
async def analyze_stock(
    code: str,
    background_tasks: BackgroundTasks,
    async_mode: bool = True,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
):
    """单股多智能体分析

    Args:
        code: yfinance 格式代码，如 "600519.SS"
        async_mode: 是否异步执行（默认 true）
        api_key: 用户 API Key（可选，优先级高于服务器配置）
        base_url: 用户 Base URL（可选）

    Returns:
        task_id 用于后续查询报告
    """
    _check_llm(api_key)
    code = normalize_stock_code(code, target="yf")

    import uuid
    task_id = str(uuid.uuid4())[:8]

    # 初始状态写入持久化
    from db.report_store import save_report
    save_report(task_id, code, "running")

    if async_mode:
        background_tasks.add_task(_run_analysis_task, task_id, code, api_key, base_url)
        _report_cache[task_id] = {"status": "running"}
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
        if api_key:
            from core.llm_client import create_llm_client
            orch.set_llm_client(create_llm_client(api_key=api_key, base_url=base_url or ""))
        report = orch.run_full_pipeline(code)
        report_dict = report.model_dump()
        _report_cache[task_id] = {
            "status": "completed",
            "report": report_dict,
        }
        save_report(task_id, code, "completed", report=report_dict)
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
    # 先查缓存
    entry = _report_cache.get(task_id)
    if entry:
        return {"task_id": task_id, **entry}

    # 缓存未命中，查持久化
    from db.report_store import get_report
    persisted = get_report(task_id)
    if not persisted:
        raise HTTPException(status_code=404, detail=f"未找到任务: {task_id}")

    # 回填缓存
    _report_cache[task_id] = {
        k: v for k, v in persisted.items() if k != "task_id" and k != "code"
    }
    return persisted


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
