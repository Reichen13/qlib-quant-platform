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


class MacroDataAdapterTests(unittest.IsolatedAsyncioTestCase):
    def _fake_akshare(self):
        return types.SimpleNamespace(
            macro_china_pmi=lambda: pd.DataFrame([
                {"月份": "2026年05月份", "制造业-指数": 49.5, "制造业-同比增长": -1.0, "非制造业-指数": 50.2, "非制造业-同比增长": 0.1},
                {"月份": "2026年06月份", "制造业-指数": 50.4, "制造业-同比增长": 0.5, "非制造业-指数": 51.1, "非制造业-同比增长": 0.4},
            ]),
            macro_china_money_supply=lambda: pd.DataFrame([
                {"月份": "2026年05月份", "货币和准货币(M2)-同比增长": 7.9},
                {"月份": "2026年06月份", "货币和准货币(M2)-同比增长": 8.3},
            ]),
            macro_china_shibor_all=lambda: pd.DataFrame([
                {"日期": "2026-06-23", "O/N-定价": 1.455, "1M-定价": 1.425},
                {"日期": "2026-06-24", "O/N-定价": 1.408, "1M-定价": 1.430},
            ]),
            bond_china_yield=lambda: pd.DataFrame([
                {"曲线名称": "中债国债收益率曲线", "日期": "2026-06-24", "10年": 2.02},
            ]),
            stock_hsgt_fund_flow_summary_em=lambda: pd.DataFrame([
                {"交易日": "2026-06-24", "资金方向": "北向", "成交净买额": 12.5},
                {"交易日": "2026-06-24", "资金方向": "南向", "成交净买额": 20.0},
            ]),
            futures_foreign_hist=lambda symbol: pd.DataFrame(),
        )

    async def test_fetch_china_macro_data_accepts_current_akshare_wide_tables(self):
        from backend.api import macro

        with patch.dict(sys.modules, {"akshare": self._fake_akshare()}):
            indicators = macro._fetch_china_macro_data()

        self.assertEqual(indicators["CN_PMI_Mfg"].value, 50.4)
        self.assertEqual(indicators["CN_PMI_NonMfg"].value, 51.1)
        self.assertEqual(indicators["CN_M2"].value, 8.3)
        self.assertEqual(indicators["CN_SHIBOR_ON"].value, 1.408)
        self.assertEqual(indicators["CN_SHIBOR_1M"].value, 1.43)
        self.assertEqual(indicators["CN_Bond_10Y"].value, 2.02)
        self.assertEqual(indicators["CN_North_Flow"].value, 12.5)

    async def test_history_accepts_current_akshare_wide_pmi_table(self):
        from backend.api import macro

        with patch.dict(sys.modules, {"akshare": self._fake_akshare()}):
            response = await macro.get_regime_history(months=2)

        self.assertEqual(len(response["history"]), 2)
        self.assertEqual(response["history"][-1]["date"], "2026-06")
        self.assertEqual(response["history"][-1]["growth_score"], 0.08)

    def test_cn_regime_is_unknown_when_core_indicators_are_missing(self):
        from backend.api import macro

        regime = macro._compute_cn_regime_scores({})

        self.assertEqual(regime["regime"], "unknown")
        self.assertEqual(regime["regime_label"], "数据不足")
        self.assertEqual(regime["confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()
