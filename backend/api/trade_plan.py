"""Trade planning API.

The endpoints in this module create risk-management plans only. They do not
place orders and do not provide personalized investment advice.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

backend_dir = str(Path(__file__).resolve().parents[1])
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from api.quote import get_quote
from core.turtle_trade import calculate_atr, build_turtle_plan
from stock_names import get_stock_name
from utils.code_normalization import normalize_stock_code

router = APIRouter()


class TurtleCandidate(BaseModel):
    code: str = Field(..., description="Stock code")
    name: str | None = Field(default=None, description="Optional display name")
    entry_price: float | None = Field(default=None, gt=0, description="Planned entry price")
    atr: float | None = Field(default=None, gt=0, description="ATR/N value")
    target_price: float | None = Field(default=None, gt=0, description="Optional target price")
    source: str | None = Field(default=None, description="Candidate source module")


class TurtlePlanRequest(BaseModel):
    account_equity: float = Field(default=100000, gt=0, description="Account equity")
    risk_percent: float = Field(default=0.01, gt=0, le=0.05, description="Risk per unit")
    max_units: int = Field(default=4, ge=1, le=8, description="Maximum Turtle units")
    atr_period: int = Field(default=20, ge=2, le=60, description="ATR lookback period")
    min_reward_risk: float = Field(default=2.0, gt=0, le=10, description="Minimum reward/risk ratio")
    candidates: list[TurtleCandidate] = Field(default_factory=list, description="Candidates to plan")


def _as_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    return {
        "high": getattr(item, "high", None),
        "low": getattr(item, "low", None),
        "close": getattr(item, "close", None),
    }


async def _derive_candidate_inputs(candidate: TurtleCandidate, atr_period: int) -> tuple[str, str, float, float, str, str | None]:
    normalized_code = normalize_stock_code(candidate.code, target="qlib")
    name = candidate.name or get_stock_name(normalized_code)
    entry_price = candidate.entry_price
    atr = candidate.atr
    warning: str | None = None
    data_status = "provided" if entry_price and atr else "derived"

    if entry_price and atr:
        return normalized_code, name, entry_price, atr, data_status, warning

    quote_response = await get_quote(normalized_code, start_date=None, end_date=None, frequency="daily", indicators=False)
    quote_dict = _as_dict(quote_response)
    rows = [_as_dict(row) for row in quote_dict.get("data", [])]
    if not rows:
        raise ValueError("缺少可用于计算 ATR 的行情数据")

    last_close = rows[-1].get("close")
    if entry_price is None:
        entry_price = float(last_close)
    if atr is None:
        atr = calculate_atr(rows, period=atr_period)
    if atr is None or atr <= 0:
        raise ValueError("ATR 计算失败，行情数据不足")

    name = candidate.name or quote_dict.get("name") or name
    return normalized_code, name, float(entry_price), float(atr), data_status, warning


@router.post("/turtle")
async def create_turtle_trade_plan(request: TurtlePlanRequest):
    """Create Turtle-style money-management plans for candidate symbols."""
    if not request.candidates:
        raise HTTPException(status_code=400, detail="请至少提供一个候选标的")

    plans: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for candidate in request.candidates:
        try:
            code, name, entry_price, atr, data_status, warning = await _derive_candidate_inputs(candidate, request.atr_period)
            plan = build_turtle_plan(
                code=code,
                name=name,
                account_equity=request.account_equity,
                risk_percent=request.risk_percent,
                entry_price=entry_price,
                atr=atr,
                target_price=candidate.target_price,
                max_units=request.max_units,
                min_reward_risk=request.min_reward_risk,
            )
            plan["source"] = candidate.source or "manual"
            plan["data_status"] = data_status
            if warning:
                plan["warnings"].append(warning)
            plans.append(plan)
        except Exception as exc:
            errors.append({
                "code": candidate.code,
                "message": str(exc),
            })

    return {
        "method": "turtle",
        "account_equity": request.account_equity,
        "risk_percent": request.risk_percent,
        "total": len(plans),
        "plans": plans,
        "errors": errors,
        "disclaimer": "本结果仅用于交易计划和风险测算，不构成投资建议，也不会自动下单。",
    }
