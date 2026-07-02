"""Deterministic Turtle-style trade plan calculations.

This module only produces planning numbers. It does not place orders and does
not make investment recommendations.
"""

from __future__ import annotations

import math
from typing import Any


def _round_money(value: float) -> float:
    return round(float(value), 2)


def calculate_atr(candles: list[dict[str, Any]], period: int = 20) -> float | None:
    """Calculate ATR from candles containing high, low, and close values."""
    if period <= 0 or len(candles) < 2:
        return None

    true_ranges: list[float] = []
    previous_close: float | None = None
    for candle in candles:
        try:
            high = float(candle["high"])
            low = float(candle["low"])
            close = float(candle["close"])
        except (KeyError, TypeError, ValueError):
            previous_close = None
            continue

        if not all(math.isfinite(value) and value > 0 for value in (high, low, close)):
            previous_close = None
            continue

        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        true_ranges.append(true_range)
        previous_close = close

    if not true_ranges:
        return None

    selected = true_ranges[-period:]
    return round(sum(selected) / len(selected), 4)


def build_turtle_plan(
    *,
    code: str,
    name: str | None = None,
    account_equity: float,
    risk_percent: float,
    entry_price: float,
    atr: float,
    target_price: float | None = None,
    max_units: int = 4,
    min_reward_risk: float = 2.0,
) -> dict[str, Any]:
    """Build a Turtle-style money-management plan for one long candidate."""
    if account_equity <= 0:
        raise ValueError("account_equity must be positive")
    if not 0 < risk_percent <= 0.05:
        raise ValueError("risk_percent must be between 0 and 0.05")
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    if atr <= 0:
        raise ValueError("atr must be positive")
    if max_units < 1:
        raise ValueError("max_units must be at least 1")

    risk_budget = account_equity * risk_percent
    stop_distance = 2 * atr
    raw_unit_shares = math.floor(risk_budget / stop_distance)
    unit_shares = max(1, raw_unit_shares)
    planned_unit_risk = unit_shares * stop_distance
    unit_position_value = unit_shares * entry_price
    max_shares = unit_shares * max_units
    max_position_value = unit_position_value * max_units
    initial_stop = entry_price - stop_distance
    add_on_prices = [entry_price + 0.5 * atr * step for step in range(1, max_units)]

    target_source = "provided" if target_price is not None else "auto_min_reward_risk"
    if target_price is None:
        target_price = entry_price + stop_distance * min_reward_risk

    reward_risk_ratio: float | None = None
    if target_price is not None and target_price > entry_price:
        reward_risk_ratio = (target_price - entry_price) / stop_distance

    warnings: list[str] = []
    if planned_unit_risk > risk_budget:
        warnings.append("单股最小买入数量已超过单笔风险预算")
    if reward_risk_ratio is None:
        warnings.append("目标价无效，无法确认盈亏比")
    elif reward_risk_ratio < (min_reward_risk - 1e-9):
        warnings.append(f"盈亏比低于 {min_reward_risk:g}:1")
    if max_position_value > account_equity:
        warnings.append("满额加仓后的名义仓位超过账户总资金")

    verdict = "可执行" if not warnings else "不建议执行"

    return {
        "code": code,
        "name": name or code,
        "method": "turtle",
        "direction": "long",
        "account_equity": _round_money(account_equity),
        "risk_percent": round(float(risk_percent), 4),
        "risk_budget": _round_money(risk_budget),
        "entry_price": _round_money(entry_price),
        "atr": round(float(atr), 4),
        "n_value": round(float(atr), 4),
        "stop_distance": _round_money(stop_distance),
        "initial_stop": _round_money(max(initial_stop, 0.0)),
        "unit_shares": int(unit_shares),
        "unit_position_value": _round_money(unit_position_value),
        "planned_unit_risk": _round_money(planned_unit_risk),
        "max_units": int(max_units),
        "max_shares": int(max_shares),
        "max_position_value": _round_money(max_position_value),
        "add_on_prices": [_round_money(price) for price in add_on_prices],
        "target_price": _round_money(target_price) if target_price is not None else None,
        "target_source": target_source,
        "reward_risk_ratio": round(reward_risk_ratio, 2) if reward_risk_ratio is not None else None,
        "min_reward_risk": float(min_reward_risk),
        "verdict": verdict,
        "warnings": warnings,
        "plan_text": (
            f"以 {entry_price:.2f} 附近为观察入场价，单单位 {unit_shares} 股，"
            f"初始止损 {max(initial_stop, 0.0):.2f}，每 0.5N 考虑加仓，最多 {max_units} 个单位。"
        ),
    }
