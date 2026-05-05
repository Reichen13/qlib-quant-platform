"""
API Key 认证
基于 X-API-Key header 的简单认证中间件
开发模式（未配置 API_KEY 环境变量）下不启用认证
"""

import os
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    """验证 API Key

    如果未配置 API_KEY 环境变量，允许所有请求（开发模式）。
    否则要求请求头 X-API-Key 匹配。
    """
    expected = os.getenv("API_KEY")
    if not expected:
        return  # 开发模式：允许所有
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 API Key，请在请求头 X-API-Key 中提供",
        )
    if api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key",
        )
