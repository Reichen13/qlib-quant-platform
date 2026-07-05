"""市场情绪 API — 整合龙虎榜/北向资金/指数/行业/解禁/概念板块"""

from fastapi import APIRouter, HTTPException
from loguru import logger
from backend.services.sentiment_data import fetch_market_sentiment

router = APIRouter()


@router.get("/overview")
async def get_sentiment_overview():
    """获取市场情绪全维度数据"""
    try:
        result = fetch_market_sentiment()
        return result
    except Exception as e:
        logger.error(f"市场情绪获取失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
