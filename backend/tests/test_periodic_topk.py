import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from core.periodic_topk import resolve_n_drop  # noqa: E402


class ResolveNDropTests(unittest.TestCase):
    def test_default_is_about_20_percent(self):
        self.assertEqual(resolve_n_drop(30), 6)
        self.assertEqual(resolve_n_drop(5), 1)
        self.assertEqual(resolve_n_drop(1), 1)

    def test_n_drop_capped_by_topk(self):
        self.assertLessEqual(resolve_n_drop(3), 3)


class PeriodicStrategyTests(unittest.TestCase):
    def test_hold_on_non_rebalance_days(self):
        # Lightweight mock of TopkDropoutStrategy parent
        class FakeParent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.trade_calendar = MagicMock()
                self._calls = 0

            def generate_trade_decision(self, execute_result=None):
                self._calls += 1
                return f"TRADE-{self._calls}"

        with patch("qlib.contrib.strategy.TopkDropoutStrategy", FakeParent), patch(
            "qlib.backtest.decision.TradeDecisionWO",
            side_effect=lambda orders, strategy: ("HOLD", orders, strategy),
        ):
            from core.periodic_topk import build_periodic_topk_strategy

            strategy = build_periodic_topk_strategy(
                topk=10,
                n_drop=2,
                signal=None,
                rebalance_days=3,
            )
            strategy.trade_calendar.get_trade_step.side_effect = [0, 1, 2, 3, 4]

            d0 = strategy.generate_trade_decision()
            d1 = strategy.generate_trade_decision()
            d2 = strategy.generate_trade_decision()
            d3 = strategy.generate_trade_decision()

            self.assertEqual(d0, "TRADE-1")  # step 0 rebalance
            self.assertEqual(d1[0], "HOLD")  # step 1 hold
            self.assertEqual(d2[0], "HOLD")  # step 2 hold
            self.assertEqual(d3, "TRADE-2")  # step 3 rebalance


if __name__ == "__main__":
    unittest.main()
