import sys
import types
import unittest
from pathlib import Path


backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

if "loguru" not in sys.modules:
    logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    sys.modules["loguru"] = types.SimpleNamespace(logger=logger)


class AIStrategyScreeningTests(unittest.TestCase):
    def test_scores_candidate_from_real_screening_signals(self):
        from backend.api.ai_strategy import score_screening_candidate

        scored = score_screening_candidate({
            "code": "SZ300196",
            "name": "长海股份",
            "change_pct": 2.1,
            "mean_reversion": {
                "rsi": 54.0,
                "bollingerPosition": 0.48,
                "signal": "关注",
            },
            "factor_signal": {
                "score": 0.86,
                "rank": 1,
                "matched_factors": 6,
            },
        })

        self.assertEqual(scored["ai_strategy"]["status"], "available")
        self.assertGreaterEqual(scored["ai_strategy"]["score"], 65)
        self.assertEqual(scored["ai_strategy"]["recommendation"], "buyable")
        self.assertTrue(scored["ai_strategy"]["votes"])

    def test_penalizes_overheated_candidate_even_with_factor_support(self):
        from backend.api.ai_strategy import score_screening_candidate

        scored = score_screening_candidate({
            "code": "SH600176",
            "name": "中国巨石",
            "change_pct": 9.9,
            "mean_reversion": {
                "rsi": 88.0,
                "bollingerPosition": 1.08,
                "signal": "超买",
            },
            "factor_signal": {
                "score": 0.9,
                "rank": 1,
                "matched_factors": 5,
            },
        })

        self.assertLess(scored["ai_strategy"]["score"], 65)
        self.assertIn(scored["ai_strategy"]["recommendation"], {"wait", "avoid"})


if __name__ == "__main__":
    unittest.main()
