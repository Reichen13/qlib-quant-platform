import sys
import types
import unittest
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
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
        class FakeSector:
            def __init__(self, name, change_pct, stock_count):
                self.name = name
                self.change_pct = change_pct
                self.stock_count = stock_count

        class FakeHotResponse:
            sectors = [
                FakeSector("行业A", 1.0, 2),
                FakeSector("行业B", -0.4, 1),
            ]

        async def fake_get_hot_sectors(days=10):
            return FakeHotResponse()

        fake_sectors = types.ModuleType("api.sectors")
        fake_sectors._get_all_stock_prices = lambda: (_ for _ in ()).throw(
            AssertionError("Dashboard should not use the slow yfinance sector path")
        )
        fake_hot = types.ModuleType("api.hot")
        fake_hot.get_hot_sectors = fake_get_hot_sectors

        with patch.dict(sys.modules, {
            "api.sectors": fake_sectors,
            "api.hot": fake_hot,
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

    async def test_summary_returns_json_serializable_numbers(self):
        fake_etf = types.ModuleType("api.etf")
        fake_etf._get_cached_history = lambda: {
            "SH510300": pd.DataFrame({"Close": [1.0 + i * 0.01 for i in range(12)]})
        }
        fake_etf._get_etf_universe = lambda: {"SH510300": "沪深300ETF"}
        fake_etf.compute_signal = lambda prices, days=20: ("buy", np.float32(3.2), np.float32(1.5))

        with patch.dict(sys.modules, {"api.etf": fake_etf}):
            result = await dashboard.get_dashboard_summary()

        json.dumps(result, ensure_ascii=False)
        self.assertIs(type(result["etf_signals"][0]["change_pct"]), float)


if __name__ == "__main__":
    unittest.main()
