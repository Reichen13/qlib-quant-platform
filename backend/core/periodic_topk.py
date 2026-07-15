"""Periodic TopkDropout strategy for true multi-day rebalance cadence.

Qlib's TopkDropoutStrategy evaluates every trading day. Wrapping it so that
non-rebalance days emit empty trade decisions (hold) makes `turnover` (N days)
a real backtest parameter instead of UI-only documentation.
"""

from __future__ import annotations

from typing import Any

from loguru import logger


def build_periodic_topk_strategy(
    *,
    topk: int,
    n_drop: int,
    signal: Any,
    rebalance_days: int = 1,
):
    """Return a TopkDropoutStrategy that only trades every `rebalance_days` steps."""
    from qlib.contrib.strategy import TopkDropoutStrategy
    from qlib.backtest.decision import TradeDecisionWO

    rebalance_days = max(1, int(rebalance_days))
    topk = max(1, int(topk))
    n_drop = max(1, min(int(n_drop), topk))

    class PeriodicTopkDropoutStrategy(TopkDropoutStrategy):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.rebalance_days = rebalance_days
            self._decision_count = 0
            self._hold_days = 0
            self._trade_days = 0

        def generate_trade_decision(self, execute_result=None):
            # Prefer calendar step index when available (stable across restarts of logic)
            step_idx = None
            try:
                cal = getattr(self, "trade_calendar", None)
                if cal is not None and hasattr(cal, "get_trade_step"):
                    step_idx = int(cal.get_trade_step())
            except Exception:
                step_idx = None
            if step_idx is None:
                step_idx = self._decision_count
            self._decision_count += 1

            if self.rebalance_days > 1 and (step_idx % self.rebalance_days) != 0:
                self._hold_days += 1
                return TradeDecisionWO([], self)

            self._trade_days += 1
            return super().generate_trade_decision(execute_result)

    strategy = PeriodicTopkDropoutStrategy(topk=topk, n_drop=n_drop, signal=signal)
    logger.info(
        f"PeriodicTopkDropout: topk={topk}, n_drop={n_drop}, "
        f"rebalance_days={rebalance_days} (non-rebalance days hold)"
    )
    return strategy


def resolve_n_drop(hold_num: int, rebalance_days: int = 1) -> int:
    """Default drop count: ~20% of book per rebalance event."""
    hold_num = max(1, int(hold_num))
    rebalance_days = max(1, int(rebalance_days))
    # Keep fraction of book rotated per rebalance roughly stable (~20%)
    n_drop = max(1, hold_num // 5)
    return min(n_drop, hold_num)
