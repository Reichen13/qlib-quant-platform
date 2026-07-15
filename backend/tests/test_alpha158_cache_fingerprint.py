import json
import sys
import tempfile
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

from core import alpha158_cache as cache  # noqa: E402


def _write_fake_cn_data(root: Path, close_val: float = 10.0, factor_val: float = 2.0):
    cal = root / "calendars"
    feat = root / "features" / "sh600519"
    cal.mkdir(parents=True)
    feat.mkdir(parents=True)
    (cal / "day.txt").write_text("2026-07-01\n2026-07-02\n2026-07-03\n", encoding="utf-8")
    np.array([0.0, close_val, close_val + 0.1, close_val + 0.2], dtype="<f").tofile(feat / "close.day.bin")
    np.array([0.0, factor_val, factor_val, factor_val], dtype="<f").tofile(feat / "factor.day.bin")


class Alpha158FingerprintTests(unittest.TestCase):
    def test_fingerprint_changes_when_bin_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "cn_data"
            _write_fake_cn_data(data_dir, close_val=10.0)
            cache.invalidate_fingerprint_cache()
            fp1 = cache.compute_data_fingerprint(data_dir)
            # Mutate close bin
            stock = data_dir / "features" / "sh600519"
            np.array([0.0, 99.0, 100.0, 101.0], dtype="<f").tofile(stock / "close.day.bin")
            cache.invalidate_fingerprint_cache()
            fp2 = cache.compute_data_fingerprint(data_dir)
            self.assertNotEqual(fp1, fp2)

    def test_cache_miss_after_data_fingerprint_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "cn_data"
            cache_dir = Path(tmp) / "alpha158_cache"
            _write_fake_cn_data(data_dir)
            idx = pd.MultiIndex.from_product(
                [pd.date_range("2026-01-01", periods=5), ["SH600519"]],
                names=["datetime", "instrument"],
            )
            df = pd.DataFrame({"KMID": np.arange(5, dtype=float)}, index=idx)

            with patch.object(cache, "CN_DATA_DIR", data_dir), patch.object(
                cache, "CACHE_DIR", cache_dir
            ):
                cache.invalidate_fingerprint_cache()
                cache.save_features_cache(df, "2026-01-01", "2026-01-31", "core650")
                hit = cache.load_cached_features("2026-01-01", "2026-01-31", "core650", max_age_hours=48)
                self.assertIsNotNone(hit)
                self.assertEqual(len(hit), 5)

                # Simulate data update
                np.array([0.0, 1.0, 2.0, 3.0], dtype="<f").tofile(
                    data_dir / "features" / "sh600519" / "close.day.bin"
                )
                cache.invalidate_fingerprint_cache()
                miss = cache.load_cached_features("2026-01-01", "2026-01-31", "core650", max_age_hours=48)
                self.assertIsNone(miss)

    def test_clear_all_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "alpha158_cache"
            cache_dir.mkdir()
            (cache_dir / "abc_features.parquet").write_bytes(b"x")
            (cache_dir / "abc_features.meta.json").write_text("{}", encoding="utf-8")
            with patch.object(cache, "CACHE_DIR", cache_dir):
                n = cache.clear_all_cache()
            self.assertGreaterEqual(n, 2)
            self.assertEqual(list(cache_dir.glob("*")), [])


if __name__ == "__main__":
    unittest.main()
