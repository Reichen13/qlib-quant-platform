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

    def test_theme_universe_generates_pair_candidates(self):
        candidates = pair.build_theme_pair_definitions()
        cpo_pairs = [item for item in candidates if item["category"] == "CPO三皇"]

        self.assertEqual(len(cpo_pairs), 3)
        self.assertIn({
            "pair": "中际旭创 / 新易盛",
            "stock1": "SZ300308",
            "stock2": "SZ300502",
            "category": "CPO三皇",
            "source": "theme_universe",
        }, cpo_pairs)
        self.assertGreater(len(candidates), len(pair.PAIR_DEFINITIONS))

    async def test_pair_list_does_not_recalculate_all_theme_pairs(self):
        with patch.object(pair, "_cached_or_unavailable_pair_metrics", side_effect=lambda item: item) as cached:
            response = await pair.list_pairs()

        self.assertGreater(response["total"], len(pair.PAIR_DEFINITIONS))
        self.assertEqual(cached.call_count, response["total"])


if __name__ == "__main__":
    unittest.main()
