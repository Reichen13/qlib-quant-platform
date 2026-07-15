import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from api import quote  # noqa: E402


class QuotePriceAdjustTests(unittest.TestCase):
    def test_back_adjusted_row_with_real_factor_is_divided(self):
        idx = pd.MultiIndex.from_tuples(
            [("SH600519", pd.Timestamp("2026-07-03"))],
            names=["instrument", "datetime"],
        )
        df = pd.DataFrame(
            {
                "$open": [9000.0],
                "$high": [9200.0],
                "$low": [8900.0],
                "$close": [9160.0],
                "$volume": [1.0],
                "$money": [1.0],
                "$factor": [7.669],
            },
            index=idx,
        )
        with patch("core.price_adjust.get_latest_factor", return_value=7.669):
            out = quote._build_price_frame(df, "SH600519")
        self.assertAlmostEqual(out.iloc[0]["close"], 9160.0 / 7.669, places=1)

    def test_placeholder_factor_tail_not_divided_by_historical_factor(self):
        idx = pd.MultiIndex.from_tuples(
            [("SH600519", pd.Timestamp("2026-07-08"))],
            names=["instrument", "datetime"],
        )
        df = pd.DataFrame(
            {
                "$open": [1190.0],
                "$high": [1210.0],
                "$low": [1180.0],
                "$close": [1199.0],
                "$volume": [1.0],
                "$money": [1.0],
                "$factor": [1.0],
            },
            index=idx,
        )
        with patch("core.price_adjust.get_latest_factor", return_value=7.669):
            out = quote._build_price_frame(df, "SH600519")
        # 1199/7.669 ≈ 156 — would be wrong market price; should keep ~1199
        self.assertAlmostEqual(out.iloc[0]["close"], 1199.0, places=1)


if __name__ == "__main__":
    unittest.main()
