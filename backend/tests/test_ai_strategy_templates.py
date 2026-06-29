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


class AIStrategyTemplateTests(unittest.TestCase):
    def test_keeps_classic_templates_and_adds_recent_a_share_hot_templates(self):
        from backend.api.ai_strategy import STRATEGY_TEMPLATES

        ids = {template["id"] for template in STRATEGY_TEMPLATES}

        self.assertGreaterEqual(len(STRATEGY_TEMPLATES), 13)
        self.assertTrue({
            "ma_cross",
            "momentum_breakout",
            "value_select",
            "mean_reversion",
            "factor_rotation",
        }.issubset(ids))
        self.assertTrue({
            "dividend_low_vol_csi",
            "ai_compute_semiconductor_momentum",
            "low_altitude_robotics_theme",
            "export_leader_quality_growth",
            "policy_catalyst_theme_rotation",
        }.issubset(ids))


if __name__ == "__main__":
    unittest.main()
