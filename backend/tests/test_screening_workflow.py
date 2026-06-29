import unittest


class ScreeningWorkflowTests(unittest.TestCase):
    def test_classifies_agent_buy_as_keep_but_waits_when_overbought(self):
        from backend.api.screening import classify_candidate

        result = classify_candidate({
            "code": "SH600487",
            "name": "亨通光电",
            "change_pct": 1.46,
            "mean_reversion": {
                "rsi": 73.9,
                "bollingerPosition": 0.84,
                "signal": "超买",
                "strength": "强",
            },
            "agent": {
                "status": "completed",
                "rating": "买入",
                "risk_level": "medium",
            },
        })

        self.assertEqual(result["action"], "保留")
        self.assertEqual(result["bucket"], "wait_for_pullback")
        self.assertIn("超买", result["reason"])

    def test_downgrades_limit_up_without_agent_confirmation(self):
        from backend.api.screening import classify_candidate

        result = classify_candidate({
            "code": "SH600176",
            "name": "中国巨石",
            "change_pct": 9.99,
            "mean_reversion": {
                "rsi": 88.7,
                "bollingerPosition": 1.08,
                "signal": "超买",
                "strength": "强",
            },
            "agent": {"status": "missing"},
        })

        self.assertEqual(result["action"], "降级")
        self.assertEqual(result["bucket"], "watch_only")
        self.assertIn("涨幅过大", result["reason"])

    def test_classifies_overbought_without_agent_as_wait_for_pullback(self):
        from backend.api.screening import classify_candidate

        result = classify_candidate({
            "code": "SZ002156",
            "name": "通富微电",
            "change_pct": 2.1,
            "mean_reversion": {
                "rsi": 55.2,
                "bollingerPosition": 0.97,
                "signal": "超买",
                "strength": "中",
            },
            "agent": {"status": "missing"},
        })

        self.assertEqual(result["action"], "等待")
        self.assertEqual(result["bucket"], "wait_for_pullback")

    def test_default_candidate_name_fallback_uses_chinese_name(self):
        from backend.api.screening import _resolve_candidate_name

        self.assertEqual(_resolve_candidate_name("SH600487", "SH600487(沪市)"), "亨通光电")
        self.assertEqual(_resolve_candidate_name("SZ002156", "SZ002156(深市)"), "通富微电")

    def test_factor_supported_candidate_can_be_buyable(self):
        from backend.api.screening import classify_candidate

        result = classify_candidate({
            "code": "SZ300196",
            "name": "长海股份",
            "change_pct": 1.2,
            "mean_reversion": {
                "rsi": 53.9,
                "bollingerPosition": 0.50,
                "signal": "关注",
                "strength": "弱",
            },
            "factor_signal": {
                "score": 0.82,
                "rank": 1,
                "source": "latest_factor_analysis",
            },
            "agent": {"status": "missing"},
        })

        self.assertEqual(result["bucket"], "buyable")
        self.assertIn("因子", result["reason"])

    def test_ai_strategy_supported_candidate_can_be_buyable(self):
        from backend.api.screening import classify_candidate

        result = classify_candidate({
            "code": "SZ300196",
            "name": "长海股份",
            "change_pct": 1.2,
            "mean_reversion": {
                "rsi": 52.0,
                "bollingerPosition": 0.45,
                "signal": "关注",
            },
            "ai_strategy": {
                "status": "available",
                "score": 72,
                "recommendation": "buyable",
            },
            "agent": {"status": "missing"},
        })

        self.assertEqual(result["bucket"], "buyable")
        self.assertIn("AI", result["reason"])

    def test_generated_strategy_fit_can_promote_ai_supported_candidate(self):
        from backend.api.screening import attach_generated_strategy_fit, classify_candidate

        candidates = attach_generated_strategy_fit(
            [
                {
                    "code": "SZ300196",
                    "name": "长海股份",
                    "change_pct": 1.2,
                    "mean_reversion": {"rsi": 52.0, "bollingerPosition": 0.45, "signal": "关注"},
                    "ai_strategy": {"status": "available", "score": 60, "recommendation": "watch"},
                    "agent": {"status": "missing"},
                }
            ],
            {"params": {"hold_num": 10, "turnover": 20}},
        )

        result = classify_candidate(candidates[0])

        self.assertEqual(candidates[0]["generated_strategy"]["fit"], "selected")
        self.assertEqual(result["bucket"], "buyable")
        self.assertIn("AI生成策略", result["reason"])

    def test_attaches_factor_scores_to_candidates(self):
        from backend.api.screening import attach_factor_scores_to_candidates

        candidates = [
            {"code": "SZ300196", "name": "长海股份"},
            {"code": "SH600487", "name": "亨通光电"},
        ]

        enriched = attach_factor_scores_to_candidates(
            candidates,
            {
                "SZ300196": {"score": 0.82, "rank": 1},
                "SH600487": {"score": -0.24, "rank": 2},
            },
        )

        self.assertEqual(enriched[0]["factor_signal"]["score"], 0.82)
        self.assertEqual(enriched[0]["factor_signal"]["rank"], 1)
        self.assertEqual(enriched[1]["factor_signal"]["score"], -0.24)

    def test_summarizes_latest_factor_analysis_result(self):
        from backend.api.screening import summarize_factor_analysis_result

        summary = summarize_factor_analysis_result({
            "start_date": "2026-03-25",
            "end_date": "2026-06-24",
            "predict_period": 5,
            "factors": [
                {"factor": "STD30", "ic": 0.086, "rank_ic": 0.086, "icir": 0.44, "category": "波动率"},
                {"factor": "WVMA60", "ic": -0.072, "rank_ic": -0.072, "icir": -0.85, "category": "加权成交量"},
            ],
            "summary": {
                "effective_factors": 45,
                "positive_factors": 78,
                "negative_factors": 79,
                "label_available_until": "2026-06-19",
            },
        })

        self.assertEqual(summary["status"], "available")
        self.assertEqual(summary["end_date"], "2026-06-24")
        self.assertEqual(summary["label_available_until"], "2026-06-19")
        self.assertTrue(summary["is_leak_safe_for_screening"])
        self.assertEqual(summary["best_factor"], "STD30")
        self.assertEqual(summary["effective_factors"], 45)
        self.assertEqual(len(summary["top_factors"]), 2)

    def test_latest_factor_analysis_without_label_metadata_is_not_used_for_screening(self):
        from backend.api.screening import _compute_candidate_factor_scores, summarize_factor_analysis_result

        warnings = []
        summary = summarize_factor_analysis_result({
            "start_date": "2026-03-25",
            "end_date": "2026-06-24",
            "predict_period": 5,
            "factors": [
                {"factor": "STD30", "ic": 0.086, "rank_ic": 0.086, "icir": 0.44, "category": "波动率"},
            ],
            "summary": {"effective_factors": 45},
        })

        scores = _compute_candidate_factor_scores(["SZ300196"], summary, warnings)

        self.assertFalse(summary["is_leak_safe_for_screening"])
        self.assertEqual(scores, {})
        self.assertTrue(any("未来函数" in item or "前向收益" in item for item in warnings))

    def test_builds_summary_buckets_from_candidates(self):
        from backend.api.screening import build_screening_summary

        summary = build_screening_summary(
            data_health={"overall_status": "healthy"},
            hot_sectors=[{"name": "半导体", "change_pct": 6.21}],
            etf_signals=[{"code": "SZ159995", "name": "芯片ETF", "signal": "buy", "change_pct": 14.48}],
            pair_signals=[{"pair": "招商银行 / 平安银行", "signal": "做多价差"}],
            candidates=[
                {
                    "code": "SH600487",
                    "name": "亨通光电",
                    "change_pct": 1.46,
                    "mean_reversion": {"rsi": 73.9, "signal": "超买", "strength": "强"},
                    "agent": {"status": "completed", "rating": "买入"},
                },
                {
                    "code": "SH600176",
                    "name": "中国巨石",
                    "change_pct": 9.99,
                    "mean_reversion": {"rsi": 88.7, "signal": "超买", "strength": "强"},
                    "agent": {"status": "missing"},
                },
            ],
            risk_summary={"sharpe_ratio": 1.2},
            factor_summary={"status": "available", "best_factor": "STD30"},
        )

        self.assertEqual(summary["data_health"]["overall_status"], "healthy")
        self.assertEqual(summary["factor_summary"]["best_factor"], "STD30")
        self.assertEqual(summary["hot_sectors"][0]["name"], "半导体")
        self.assertEqual(summary["etf_signals"][0]["code"], "SZ159995")
        self.assertEqual(summary["pair_signals"][0]["signal"], "做多价差")
        self.assertEqual(len(summary["buckets"]["wait_for_pullback"]), 1)
        self.assertEqual(len(summary["buckets"]["watch_only"]), 1)


if __name__ == "__main__":
    unittest.main()
