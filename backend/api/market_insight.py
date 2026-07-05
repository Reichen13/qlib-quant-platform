"""市场洞察 API — 概念板块 / 资金流向 / 龙虎榜"""

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from backend.services.market_data import fetch_concept_boards, fetch_stock_fund_flow, fetch_dragon_tiger

router = APIRouter()


@router.get("/stocks/{code}/concepts")
async def get_stock_concepts(code: str):
    """获取个股的概念板块归属（行业+概念+地域，含BK码+涨跌幅+龙头股）"""
    try:
        result = fetch_concept_boards(code)
        return result
    except Exception as e:
        logger.error(f"概念板块查询失败 {code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stocks/{code}/fund-flow")
async def get_stock_fund_flow(code: str, days: int = Query(5, ge=1, le=30)):
    """获取个股资金流向（日级：主力/超大单/大单净流入）"""
    try:
        result = fetch_stock_fund_flow(code, days=days)
        return result
    except Exception as e:
        logger.error(f"资金流向查询失败 {code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dragon-tiger")
async def get_dragon_tiger(code: str = Query("", description="股票代码（空=全市场）"), limit: int = Query(20, ge=5, le=100)):
    """获取龙虎榜数据（全市场 或 指定个股）"""
    try:
        result = fetch_dragon_tiger(code=code, page_size=limit)
        return result
    except Exception as e:
        logger.error(f"龙虎榜查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
