"""
持仓管理 API — 增删查改用户持仓
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from db.position_store import position_store

router = APIRouter()


class PositionUpsert(BaseModel):
    code: str = Field(..., description="股票代码，如 SH600519")
    name: str = Field(default="", description="股票名称")
    shares: int = Field(..., ge=0, description="持仓股数")
    cost_price: float = Field(..., gt=0, description="成本价")
    stop_loss_price: Optional[float] = Field(default=None, description="止损价")
    buy_date: str = Field(default="", description="买入日期 YYYY-MM-DD")
    notes: str = Field(default="", description="备注")


@router.get("")
async def list_positions():
    """获取全部持仓"""
    return {"positions": position_store.list_all(), "count": len(position_store.list_all())}


@router.get("/{code}")
async def get_position(code: str):
    """获取单只持仓"""
    pos = position_store.get_by_code(code)
    if not pos:
        raise HTTPException(status_code=404, detail=f"未找到持仓: {code}")
    return pos


@router.post("")
async def create_or_update_position(body: PositionUpsert):
    """新增或更新持仓"""
    if body.shares <= 0:
        position_store.delete(body.code)
        return {"code": body.code, "deleted": True, "message": "股数为 0，已删除"}
    result = position_store.upsert(
        code=body.code, name=body.name, shares=body.shares,
        cost_price=body.cost_price, stop_loss_price=body.stop_loss_price,
        buy_date=body.buy_date, notes=body.notes,
    )
    return result


@router.delete("/{code}")
async def delete_position(code: str):
    """删除单只持仓"""
    ok = position_store.delete(code)
    if not ok:
        raise HTTPException(status_code=404, detail=f"未找到持仓: {code}")
    return {"code": code, "deleted": True}


@router.delete("")
async def clear_positions():
    """清空全部持仓"""
    count = position_store.delete_all()
    return {"deleted": count, "message": f"已清空 {count} 条持仓记录"}
