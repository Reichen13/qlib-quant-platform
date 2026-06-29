import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd


backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.core import multi_agent


class FakeD:
    calls = []

    @classmethod
    def features(cls, codes, fields, start_time=None, end_time=None, **kwargs):
        cls.calls.append((codes, fields, start_time, end_time, kwargs))
        dates = pd.date_range("2026-03-02", periods=80, freq="B")
        close = np.linspace(40.0, 56.0, len(dates)) + np.sin(np.arange(len(dates))) * 0.4
        volume = np.linspace(80_000_000, 160_000_000, len(dates))
        return pd.DataFrame(
            {
                "$close": close,
                "$volume": volume,
            },
            index=pd.MultiIndex.from_product(
                [["SH601318"], dates],
                names=["instrument", "datetime"],
            ),
        )


class MultiAgentIndicatorTests(unittest.TestCase):
    def setUp(self):
        FakeD.calls = []

    def test_format_indicators_reads_qlib_instrument_index_and_outputs_technical_summary(self):
        fake_qlib = types.SimpleNamespace()
        fake_qlib_data = types.SimpleNamespace(D=FakeD)

        with patch.dict(sys.modules, {"qlib": fake_qlib, "qlib.data": fake_qlib_data}):
            summary = multi_agent._format_indicators("601318.SS")

        self.assertEqual(FakeD.calls[0][0], ["SH601318"])
        self.assertIn("$close", FakeD.calls[0][1])
        self.assertIn("$volume", FakeD.calls[0][1])
        self.assertNotIn("暂不可用", summary)
        self.assertIn("最新收盘价", summary)
        self.assertIn("RSI(14)", summary)
        self.assertIn("MA5", summary)
        self.assertIn("MA60", summary)
        self.assertIn("MACD", summary)
        self.assertIn("成交量", summary)
        self.assertIn("量比", summary)
        self.assertIn("趋势", summary)


if __name__ == "__main__":
    unittest.main()
