"""
LLM 配置 API — 用户自主配置 LLM 提供商和 API Key

POST /api/llm/test   — 测试连接（用用户提供的 key 发一个简短请求）
GET  /api/llm/status  — 返回服务器是否配置了默认 LLM
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.llm_client import create_llm_client, get_llm_config

router = APIRouter(prefix="/api/llm", tags=["llm"])


class LLMTestRequest(BaseModel):
    api_key: str
    base_url: str = ""
    quick_model: str = ""
    deep_model: str = ""


class LLMTestResponse(BaseModel):
    ok: bool
    model: str = ""
    message: str = ""


class LLMStatusResponse(BaseModel):
    server_configured: bool
    server_quick_model: str = ""
    server_deep_model: str = ""
    message: str = ""


@router.post("/test", response_model=LLMTestResponse)
async def test_connection(body: LLMTestRequest):
    """用用户提供的 API key 发送一个简短请求，验证连接是否正常。"""
    if not body.api_key:
        return LLMTestResponse(ok=False, message="API Key 不能为空")

    try:
        client = create_llm_client(
            api_key=body.api_key,
            base_url=body.base_url,
            quick_model=body.quick_model,
            deep_model=body.deep_model,
        )
        llm = client.get_quick_llm()
        # 发送一个最小请求来验证连接
        response = llm.invoke("Hi")
        content = response.content if hasattr(response, "content") else str(response)

        model_used = client.config.quick_model
        return LLMTestResponse(
            ok=True,
            model=model_used,
            message=f"连接成功，模型 {model_used} 正常响应",
        )
    except Exception as e:
        error_msg = str(e)
        # 截断过长的错误信息
        if len(error_msg) > 300:
            error_msg = error_msg[:300] + "..."
        return LLMTestResponse(ok=False, message=f"连接失败: {error_msg}")


@router.get("/status", response_model=LLMStatusResponse)
async def llm_status():
    """返回服务器级 LLM 配置状态。"""
    config = get_llm_config()
    if config.is_configured:
        return LLMStatusResponse(
            server_configured=True,
            server_quick_model=config.quick_model,
            server_deep_model=config.deep_model,
            message="服务器已配置默认 LLM",
        )
    else:
        return LLMStatusResponse(
            server_configured=False,
            message="服务器未配置默认 LLM，请在设置页面输入您的 API Key",
        )
