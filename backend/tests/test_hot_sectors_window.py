"""Hot sector ranking must use exact N trading-day windows (no +20 padding)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.api import hot


class HotSectorsWindowTests(unittest.TestCase):
    def test_days_one_uses_previous_trading_day_only(self):
        # calendar indices 0..10; end=10, days=1 => start must be 9
        calendar = [f"2026-01-{i:02d}" for i in range(1, 12)]

        captured = {}

        def fake_bins(codes, start_index, end_index):
            captured["start"] = start_index
            captured["end"] = end_index
            return 1.23, 3

        with patch.object(hot, "_load_calendar", return_value=calendar), \
             patch.object(hot, "_sector_change_from_local_bins", side_effect=fake_bins):
            # hot._build_hot_sectors does: from core.sector_definitions import get_sectors_qlib
            import core.sector_definitions as sd
            with patch.object(sd, "get_sectors_qlib", return_value={"测试": ["SH600000"]}):
                result = hot._build_hot_sectors(1)

        self.assertEqual(captured["end"], 10)
        self.assertEqual(captured["start"], 9)  # NOT 10 - 1 - 20
        self.assertEqual(result.sectors[0].change_pct, 1.23)

    def test_point_return_helper(self):
        # start 100 -> end 90 => -10%
        with patch.object(hot, "_load_close_at_calendar_index", side_effect=lambda code, idx: {8: 100.0, 9: 90.0}.get(idx)):
            pct, n = hot._sector_change_from_local_bins(["SH600000"], 8, 9)
        self.assertEqual(n, 1)
        self.assertEqual(pct, -10.0)


if __name__ == "__main__":
    unittest.main()
