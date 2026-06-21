import sys
import types
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch


backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.core import multi_agent


class EmptyFrame:
    empty = True


class FakeD:
    calls = []

    @classmethod
    def features(cls, codes, fields, start, end):
        cls.calls.append((codes, fields, start, end))
        return EmptyFrame()


class MultiAgentCodeNormalizationTests(unittest.TestCase):
    def setUp(self):
        FakeD.calls = []

    def _patch_quote_dependencies(self):
        fake_numpy = types.SimpleNamespace(nan=float("nan"), isnan=lambda value: False)
        fake_pandas = types.SimpleNamespace(
            Timedelta=lambda days: timedelta(days=days),
        )
        fake_qlib = types.SimpleNamespace()
        fake_qlib_data = types.SimpleNamespace(D=FakeD)
        return patch.dict(sys.modules, {
            "numpy": fake_numpy,
            "pandas": fake_pandas,
            "qlib": fake_qlib,
            "qlib.data": fake_qlib_data,
        })

    def test_format_indicators_uses_star_market_qlib_code(self):
        with self._patch_quote_dependencies():
            multi_agent._format_indicators("688981.SS")

        self.assertEqual(FakeD.calls[0][0], ["SH688981"])

    def test_format_indicators_keeps_beijing_exchange_code(self):
        with self._patch_quote_dependencies():
            multi_agent._format_indicators("920118.BJ")

        self.assertEqual(FakeD.calls[0][0], ["BJ920118"])


if __name__ == "__main__":
    unittest.main()
