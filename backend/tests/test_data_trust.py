import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from core import data_trust  # noqa: E402
from core.data_trust import apply_untrusted_screening_block, evaluate_data_trust  # noqa: E402


def _write_stock(feature_root: Path, code: str, closes: list[float], factors: list[float], start_idx: int = 0):
    stock = feature_root / code
    stock.mkdir(parents=True, exist_ok=True)
    np.array([float(start_idx), *closes], dtype="<f").tofile(stock / "close.day.bin")
    np.array([float(start_idx), *factors], dtype="<f").tofile(stock / "factor.day.bin")


class DataTrustTests(unittest.TestCase):
    def test_evaluate_flags_severe_tail_splice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "cn_data"
            cal = data_dir / "calendars"
            feats = data_dir / "features"
            cal.mkdir(parents=True)
            feats.mkdir(parents=True)
            (cal / "day.txt").write_text("2026-07-01\n2026-07-02\n2026-07-03\n", encoding="utf-8")

            # 8 clean stocks + 2 spliced => 20% severe ratio > 2% threshold
            for i in range(8):
                _write_stock(
                    feats,
                    f"sh6000{i:02d}",
                    closes=[100.0, 101.0, 102.0],
                    factors=[2.0, 2.0, 2.0],
                )
            _write_stock(
                feats,
                "sh600100",
                closes=[200.0, 201.0, 10.0],  # -95% jump with factor collapse
                factors=[5.0, 5.0, 1.0],
            )
            _write_stock(
                feats,
                "sz000001",
                closes=[150.0, 151.0, 8.0],
                factors=[4.0, 4.0, 1.0],
            )

            with patch.object(data_trust, "CACHE_PATH", root / "trust.json"):
                report = evaluate_data_trust(data_dir=data_dir, max_sample=50, use_cache=False)

            self.assertFalse(report["trusted"])
            self.assertFalse(report["trading_allowed"])
            self.assertGreater(report["metrics"]["severe_splice_ratio"], 0.02)
            self.assertTrue(any("severe_tail_splice" in r for r in report["reasons"]))

    def test_evaluate_trusted_when_factors_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "cn_data"
            cal = data_dir / "calendars"
            feats = data_dir / "features"
            cal.mkdir(parents=True)
            feats.mkdir(parents=True)
            (cal / "day.txt").write_text("2026-07-01\n2026-07-02\n2026-07-03\n", encoding="utf-8")
            for i in range(60):
                _write_stock(
                    feats,
                    f"sh600{i:03d}",
                    closes=[100.0 + i * 0.01, 101.0, 102.0],
                    factors=[2.5, 2.5, 2.5],
                )

            with patch.object(data_trust, "CACHE_PATH", root / "trust.json"):
                report = evaluate_data_trust(data_dir=data_dir, max_sample=100, use_cache=False)

            self.assertTrue(report["trusted"])
            self.assertTrue(report["trading_allowed"])
            self.assertEqual(report["status"], "trusted")

    def test_apply_untrusted_screening_block_clears_buyable(self):
        result = {
            "buckets": {
                "buyable": [{"code": "SH600519", "score": 1.0, "bucket": "buyable"}],
                "watch_only": [],
            },
            "candidates": [{"code": "SH600519", "bucket": "buyable", "score": 1.0}],
            "warnings": [],
        }
        report = {"message": "dirty", "reasons": ["severe_tail_splice_ratio=40%"], "metrics": {}, "checked_at": "t"}
        blocked = apply_untrusted_screening_block(result, report)
        self.assertEqual(blocked["buckets"]["buyable"], [])
        self.assertEqual(len(blocked["buckets"]["watch_only"]), 1)
        self.assertFalse(blocked["trading_allowed"])
        self.assertTrue(any("DATA_UNTRUSTED" in w for w in blocked["warnings"]))


if __name__ == "__main__":
    unittest.main()
