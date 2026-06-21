import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

if "loguru" not in sys.modules:
    logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
        add=lambda *args, **kwargs: None,
        remove=lambda *args, **kwargs: None,
    )
    sys.modules["loguru"] = types.SimpleNamespace(logger=logger)

from backend.api import dashboard


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_strategy_signals_are_marked_as_derived_without_fake_stock_counts(self):
        fake_sectors = types.ModuleType("api.sectors")
        fake_sectors._get_all_stock_prices = lambda: {
            "SH600001": {"change_pct": 1.2},
            "SH600002": {"change_pct": 0.8},
            "SH600003": {"change_pct": -0.4},
        }
        fake_definitions = types.ModuleType("core.sector_definitions")
        fake_definitions.SECTOR_DEFINITIONS = {
            "行业A": ["SH600001", "SH600002"],
            "行业B": ["SH600003"],
        }

        with patch.dict(sys.modules, {
            "api.sectors": fake_sectors,
            "core.sector_definitions": fake_definitions,
        }):
            result = await dashboard.get_dashboard_summary()

        self.assertGreater(len(result["strategy_signals"]), 0)
        for signal in result["strategy_signals"]:
            self.assertNotIn("stocks_count", signal)
            self.assertEqual(signal["data_status"], "derived")
            self.assertEqual(signal["source"], "sector_proxy")

    async def test_summary_uses_etf_history_for_signals(self):
        fake_etf = types.ModuleType("api.etf")
        fake_etf._get_cached_history = lambda: {
            "SH510300": pd.DataFrame({"Close": [1.0 + i * 0.01 for i in range(12)]})
        }
        fake_etf._get_etf_universe = lambda: {"SH510300": "沪深300ETF"}
        fake_etf.compute_signal = lambda prices, days=20: ("buy", 3.2, 1.5)

        with patch.dict(sys.modules, {"api.etf": fake_etf}):
            result = await dashboard.get_dashboard_summary()

        self.assertEqual(result["etf_signals"], [{
            "name": "沪深300ETF",
            "code": "SH510300",
            "change_pct": 3.2,
            "signal": "buy",
        }])


if __name__ == "__main__":
    unittest.main()
