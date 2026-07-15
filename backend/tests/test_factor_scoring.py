import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from core.factor_scoring import score_with_signed_icir  # noqa: E402


class FactorScoringTests(unittest.TestCase):
    def test_negative_icir_inverts_factor_direction(self):
        # Two stocks, one factor: higher raw value should rank LOWER when ICIR < 0
        df = pd.DataFrame(
            {"MOM": [1.0, 3.0], "VOL": [0.0, 0.0]},
            index=["SH600000", "SH600519"],
        )
        scores = score_with_signed_icir(
            df,
            icir_map={"MOM": -0.5, "VOL": 0.0},
            ic_map={"MOM": -0.05, "VOL": 0.0},
        )
        # After z-score, SH600519 has higher MOM; negative weight => lower score
        self.assertLess(scores["SH600519"], scores["SH600000"])

    def test_positive_icir_preserves_direction(self):
        df = pd.DataFrame(
            {"MOM": [1.0, 3.0]},
            index=["SH600000", "SH600519"],
        )
        scores = score_with_signed_icir(df, icir_map={"MOM": 0.4}, ic_map={"MOM": 0.03})
        self.assertGreater(scores["SH600519"], scores["SH600000"])

    def test_equal_weight_zscore_when_no_icir(self):
        df = pd.DataFrame(
            {"A": [1.0, 2.0, 3.0], "B": [3.0, 2.0, 1.0]},
            index=["X", "Y", "Z"],
        )
        scores = score_with_signed_icir(df, icir_map={}, ic_map={})
        # Equal-weight mean of z-scores: middle stock near 0
        self.assertTrue(np.isfinite(scores["Y"]))


if __name__ == "__main__":
    unittest.main()
