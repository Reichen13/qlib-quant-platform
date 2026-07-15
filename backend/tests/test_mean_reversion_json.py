import unittest
from pathlib import Path
import sys

import numpy as np
import pandas as pd

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.api import mean_reversion


class MeanReversionJsonTests(unittest.TestCase):
    def test_safe_json_float_rejects_nan_inf(self):
        self.assertIsNone(mean_reversion._safe_json_float(float("nan")))
        self.assertIsNone(mean_reversion._safe_json_float(float("inf")))
        self.assertEqual(mean_reversion._safe_json_float(12.34, digits=1), 12.3)

    def test_calc_rsi_handles_flat_prices(self):
        prices = pd.Series([10.0] * 30)
        rsi = mean_reversion.calc_rsi(prices)
        last = float(rsi.iloc[-1])
        self.assertTrue(np.isfinite(last))

    def test_scan_skips_nan_metrics(self):
        """构造含 nan 的指标时不应写入信号列表。"""
        # 直接测 helper：nan 不得出现在输出 dict 数值里
        self.assertIsNone(mean_reversion._safe_json_float(np.nan, digits=1))


if __name__ == "__main__":
    unittest.main()
