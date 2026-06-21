import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

if "pandas" not in sys.modules:
    sys.modules["pandas"] = types.SimpleNamespace(notna=lambda value: value is not None)
if "numpy" not in sys.modules:
    sys.modules["numpy"] = types.SimpleNamespace(nan=float("nan"), isnan=lambda value: False)
if "loguru" not in sys.modules:
    logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
    )
    sys.modules["loguru"] = types.SimpleNamespace(logger=logger)

from backend.api import pair


class PairCodeNormalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_spread_accepts_plain_a_share_codes(self):
        with patch.object(pair, "calc_spread_data", return_value=[]) as calc:
            response = await pair.get_spread(stock1="600036", stock2="000001", days=60)

        calc.assert_called_once_with("SH600036", "SZ000001", 60)
        self.assertEqual(response["stock1"], "SH600036")
        self.assertEqual(response["stock2"], "SZ000001")

    async def test_analyze_accepts_plain_a_share_codes(self):
        with patch.object(pair, "calc_correlation_from_qlib", return_value=None) as corr, \
             patch.object(pair, "calc_zscore_from_qlib", return_value=None) as zscore, \
             patch.object(pair, "calc_spread_data", return_value=[]) as spread:
            response = await pair.analyze_pair(stock1="600036", stock2="000001")

        corr.assert_called_once_with("SH600036", "SZ000001")
        zscore.assert_called_once_with("SH600036", "SZ000001")
        spread.assert_called_once_with("SH600036", "SZ000001")
        self.assertEqual(response["stock1"], "SH600036")
        self.assertEqual(response["stock2"], "SZ000001")


if __name__ == "__main__":
    unittest.main()
