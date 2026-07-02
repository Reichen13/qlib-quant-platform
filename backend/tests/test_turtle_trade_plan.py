import unittest

from backend.core.turtle_trade import (
    calculate_atr,
    build_turtle_plan,
)


class TurtleTradePlanTests(unittest.TestCase):
    def test_calculate_atr_uses_true_range_average(self):
        candles = [
            {"high": 11.0, "low": 9.0, "close": 10.0},
            {"high": 12.0, "low": 10.0, "close": 11.0},
            {"high": 13.0, "low": 10.5, "close": 12.0},
        ]

        atr = calculate_atr(candles, period=3)

        self.assertAlmostEqual(atr, 2.1667, places=4)

    def test_build_turtle_plan_sizes_units_from_one_percent_risk(self):
        plan = build_turtle_plan(
            code="SH600519",
            name="贵州茅台",
            account_equity=100_000,
            risk_percent=0.01,
            entry_price=100.0,
            atr=2.0,
            target_price=112.0,
        )

        self.assertEqual(plan["code"], "SH600519")
        self.assertEqual(plan["name"], "贵州茅台")
        self.assertEqual(plan["entry_price"], 100.0)
        self.assertEqual(plan["atr"], 2.0)
        self.assertEqual(plan["risk_budget"], 1000.0)
        self.assertEqual(plan["unit_shares"], 250)
        self.assertEqual(plan["unit_position_value"], 25000.0)
        self.assertEqual(plan["max_units"], 4)
        self.assertEqual(plan["max_shares"], 1000)
        self.assertEqual(plan["initial_stop"], 96.0)
        self.assertEqual(plan["add_on_prices"], [101.0, 102.0, 103.0])
        self.assertEqual(plan["reward_risk_ratio"], 3.0)
        self.assertEqual(plan["verdict"], "可执行")

    def test_build_turtle_plan_defaults_target_to_minimum_reward_risk(self):
        plan = build_turtle_plan(
            code="SH600519",
            name="贵州茅台",
            account_equity=100_000,
            risk_percent=0.01,
            entry_price=100.0,
            atr=2.0,
        )

        self.assertEqual(plan["target_price"], 108.0)
        self.assertEqual(plan["reward_risk_ratio"], 2.0)
        self.assertEqual(plan["target_source"], "auto_min_reward_risk")
        self.assertNotIn("缺少有效目标价，无法确认盈亏比", plan["warnings"])
        self.assertEqual(plan["verdict"], "可执行")

    def test_build_turtle_plan_rejects_poor_reward_risk(self):
        plan = build_turtle_plan(
            code="SZ000001",
            name="平安银行",
            account_equity=100_000,
            risk_percent=0.01,
            entry_price=10.0,
            atr=1.0,
            target_price=12.0,
        )

        self.assertEqual(plan["reward_risk_ratio"], 1.0)
        self.assertEqual(plan["verdict"], "不建议执行")
        self.assertIn("盈亏比低于 2:1", plan["warnings"])

    def test_build_turtle_plan_does_not_reject_exact_minimum_reward_risk_due_to_float_noise(self):
        plan = build_turtle_plan(
            code="SZ000001",
            name="平安银行",
            account_equity=100_000,
            risk_percent=0.01,
            entry_price=10.16,
            atr=0.2371,
        )

        self.assertEqual(plan["reward_risk_ratio"], 2.0)
        self.assertEqual(plan["verdict"], "可执行")
        self.assertNotIn("盈亏比低于 2:1", plan["warnings"])

    def test_build_turtle_plan_handles_small_accounts_without_zero_risk(self):
        plan = build_turtle_plan(
            code="SZ300308",
            name="中际旭创",
            account_equity=5_000,
            risk_percent=0.005,
            entry_price=200.0,
            atr=20.0,
            target_price=260.0,
        )

        self.assertEqual(plan["unit_shares"], 1)
        self.assertGreater(plan["planned_unit_risk"], plan["risk_budget"])
        self.assertIn("单股最小买入数量已超过单笔风险预算", plan["warnings"])


if __name__ == "__main__":
    unittest.main()
