import sys
import unittest
from pathlib import Path

import pandas as pd


backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.api import hot, pair


def make_qlib_frame(values: dict[str, list[float]], field: str = "$close") -> pd.DataFrame:
    rows = []
    index = []
    dates = pd.date_range("2026-06-01", periods=max(len(v) for v in values.values()), freq="D")
    for code, series in values.items():
        for dt, value in zip(dates, series):
            index.append((code, dt))
            rows.append(value)
    return pd.DataFrame(
        {field: rows},
        index=pd.MultiIndex.from_tuples(index, names=["instrument", "datetime"]),
    )


class QlibMultiIndexMetricTests(unittest.TestCase):
    def test_pair_extracts_series_from_instrument_level(self):
        frame = make_qlib_frame({
            "SH600036": [10.0, 10.5, 11.0],
            "SZ000001": [5.0, 5.2, 5.4],
        })

        series = pair._instrument_field_series(frame, "SH600036", "$close")

        self.assertEqual(list(series), [10.0, 10.5, 11.0])
        self.assertEqual(series.index.name, "datetime")

    def test_hot_sector_change_uses_each_stock_first_and_last_valid_close(self):
        frame = make_qlib_frame({
            "SH600584": [10.0, 11.0, 12.0],
            "SZ002371": [20.0, 21.0, 22.0],
        })

        change_pct, stock_count = hot._sector_change_from_qlib_frame(
            frame,
            ["SH600584", "SZ002371"],
        )

        self.assertEqual(stock_count, 2)
        self.assertAlmostEqual(change_pct, 15.0)


if __name__ == "__main__":
    unittest.main()
