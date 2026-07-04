import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import numpy as np

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

sys.modules.setdefault("yfinance", types.SimpleNamespace())

import update_cn_data


class EmptyFrame:
    empty = True


class FakeRefFrame:
    empty = False
    index = ["2026-05-07"]


class FakeYfinanceTicker:
    def __init__(self, code):
        self.code = code

    def history(self, start, end, auto_adjust=True):
        return pd.DataFrame()


class FakeBaostockResult:
    error_code = "0"
    error_msg = "success"

    def __init__(self, rows=None):
        self.rows = rows if rows is not None else [
            [
                "2026-05-07",
                "sh.600519",
                "1375.00",
                "1388.00",
                "1370.01",
                "1371.05",
                "4046147",
                "5573286314.86",
            ],
        ]
        self.index = -1

    def next(self):
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self):
        return self.rows[self.index]


class FakeAdjustFactorResult:
    error_code = "0"
    error_msg = "success"
    fields = ["code", "dividOperateDate", "foreAdjustFactor", "backAdjustFactor", "adjustFactor"]

    def __init__(self):
        # baostock backAdjustFactor 本身就是从上市日起的累积值（实测单调递增）
        self.rows = [
            ["sh.600519", "2014-06-24", "0.166", "6.015655", "6.015655"],
            ["sh.600519", "2015-06-23", "0.1588", "6.295967", "6.295967"],
            ["sh.600519", "2025-07-16", "0.0784", "12.763991", "12.763991"],
        ]
        self.index = -1

    def next(self):
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self):
        return self.rows[self.index]


class FakeBaostockModule:
    def __init__(self):
        self.adjustflags = []
        self.adjust_factor_called = False
        self.adjust_factor_windows = []

    def login(self):
        return types.SimpleNamespace(error_code="0", error_msg="success")

    def logout(self):
        return None

    def query_history_k_data_plus(self, code, fields, start_date, end_date, frequency, adjustflag):
        self.adjustflags.append(adjustflag)
        return FakeBaostockResult(self._history_rows(start_date, end_date))

    @staticmethod
    def _history_rows(start_date: str, end_date: str):
        # 原始价（不复权）合成行：覆盖 2014 事件前后与 2026 增量两个窗口
        rows_by_date = {
            "2014-06-23": ["2014-06-23", "sh.600519", "120.0", "121.0", "119.0", "120.0", "100000", "12000000.0"],
            "2014-06-24": ["2014-06-24", "sh.600519", "121.0", "122.0", "120.0", "121.0", "110000", "13310000.0"],
            "2026-05-07": ["2026-05-07", "sh.600519", "1375.00", "1388.00", "1370.01", "1371.05", "4046147", "5573286314.86"],
        }
        return [rows_by_date[d] for d in sorted(rows_by_date) if start_date <= d <= end_date]

    def query_adjust_factor(self, code, start_date, end_date):
        self.adjust_factor_called = True
        self.adjust_factor_windows.append((start_date, end_date))
        return FakeAdjustFactorResult()


class FakeEastmoneyResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return (
            b'{"data":{"klines":['
            b'"2026-06-22,1370.00,1388.50,1390.00,1368.00,1234567,1690000000"'
            b']}}'
        )


class FakeTencentResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return (
            b'{"code":0,"data":{"sh600519":{"day":['
            b'["2026-06-22","1214.31","1241.41","1252.80","1205.00","58251"]'
            b']}}}'
        )


class UpdateCnDataTests(unittest.TestCase):
    def setUp(self):
        update_cn_data._BAOSTOCK = None
        update_cn_data._BAOSTOCK_LOGGED_IN = False

    def test_extend_calendar_rejects_calendar_reorder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            (data_dir / "calendars").mkdir(parents=True)
            cal_path = data_dir / "calendars" / "day.txt"
            cal_path.write_text(
                "2026-06-22\n2026-06-23\n2026-06-24\n2025-10-24\n",
                encoding="utf-8",
            )

            with patch.object(update_cn_data, "DATA_DIR", data_dir):
                with self.assertRaisesRegex(ValueError, "日历只能尾部追加"):
                    update_cn_data.extend_calendar(["2026-06-24", "2026-06-25"])

            calendar_text = cal_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(calendar_text, ["2026-06-22", "2026-06-23", "2026-06-24", "2025-10-24"])

    def test_extend_calendar_allows_tail_append_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            (data_dir / "calendars").mkdir(parents=True)
            cal_path = data_dir / "calendars" / "day.txt"
            cal_path.write_text("2026-06-22\n2026-06-23\n", encoding="utf-8")

            with patch.object(update_cn_data, "DATA_DIR", data_dir):
                calendar = update_cn_data.extend_calendar(["2026-06-23", "2026-06-24"])

            calendar_text = cal_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(calendar, ["2026-06-22", "2026-06-23", "2026-06-24"])
        self.assertEqual(calendar_text, calendar)

    def test_beijing_exchange_code_conversions(self):
        self.assertEqual(update_cn_data.qlib_to_yf("bj430047"), "430047.BJ")
        self.assertEqual(update_cn_data.yf_to_baostock("430047.BJ"), "bj.430047")

    def test_fetch_falls_back_to_baostock_when_yfinance_is_empty(self):
        """写入链路只能用 baostock；backAdjustFactor 是累积值（不连乘），factor=阶梯生效值。"""
        fake_baostock = FakeBaostockModule()
        with patch.object(update_cn_data, "fetch_tencent", return_value=pd.DataFrame()), \
             patch.object(update_cn_data, "fetch_yfinance", return_value=pd.DataFrame()), \
             patch.object(update_cn_data, "fetch_eastmoney", return_value=pd.DataFrame()), \
             patch.dict(sys.modules, {"baostock": fake_baostock}):
            df = update_cn_data.fetch("600519.SS", "2026-05-06", "2026-06-18")

        self.assertFalse(df.empty)
        self.assertEqual(list(df.index), ["2026-05-07"])
        # 2026-05-07 落在最后一个事件 2025-07-16 之后，生效累积因子 = 12.763991
        # close = 原始价 1371.05 × 12.763991 ≈ 17502.5
        self.assertAlmostEqual(float(df.loc["2026-05-07", "close"]), 1371.05 * 12.763991, places=2)
        self.assertEqual(float(df.loc["2026-05-07", "amount"]), 5573286314.86)
        # factor = 阶梯生效的累积后复权因子（baostock 返回值，不再连乘）
        self.assertAlmostEqual(float(df.loc["2026-05-07", "factor"]), 12.763991, places=4)
        self.assertTrue(fake_baostock.adjust_factor_called)
        # 写入链路只允许原始价口径拉取
        self.assertEqual(fake_baostock.adjustflags, ["3"])
        # 复权因子查询窗口必须从上市日起，不能跟随抓取窗口（否则增量更新断层）
        factor_start = fake_baostock.adjust_factor_windows[0][0]
        self.assertLess(factor_start, "2020-01-01", msg=f"因子查询起点应远早于抓取窗口，实际={factor_start}")

    def test_fetch_uses_step_function_not_cumulative_product_for_factor(self):
        """baostock backAdjustFactor 已是累积值，必须用阶梯函数而非连乘。"""
        fake_baostock = FakeBaostockModule()
        with patch.object(update_cn_data, "fetch_tencent", return_value=pd.DataFrame()), \
             patch.object(update_cn_data, "fetch_yfinance", return_value=pd.DataFrame()), \
             patch.object(update_cn_data, "fetch_eastmoney", return_value=pd.DataFrame()), \
             patch.dict(sys.modules, {"baostock": fake_baostock}):
            df = update_cn_data.fetch("600519.SS", "2014-06-20", "2014-06-25")

        # 2014-06-24 之前生效因子 = 1.0；2014-06-24 起生效 = 6.015655
        self.assertAlmostEqual(float(df.loc["2014-06-23", "factor"]), 1.0, places=6)
        self.assertAlmostEqual(float(df.loc["2014-06-24", "factor"]), 6.015655, places=4)
        # 连乘 bug 下 2014-06-24 会是 6.015655，但后续事件会指数爆炸；
        # 这里只测首事件，但阶梯语义已成立（= baostock 原值，非连乘前序）

    def test_fetch_does_not_write_from_non_baostock_sources(self):
        """腾讯/东财/yfinance 即便能取到数据，也不能进入写入链路。"""
        update_cn_data._BAOSTOCK = None
        update_cn_data._BAOSTOCK_LOGGED_IN = False
        tainted = pd.DataFrame(
            {"open": [1.0], "close": [1.0], "high": [1.0], "low": [1.0],
             "volume": [1.0], "amount": [1.0], "factor": [1.0]},
            index=["2026-05-07"],
        )
        with patch.object(update_cn_data, "fetch_tencent", return_value=tainted), \
             patch.object(update_cn_data, "fetch_yfinance", return_value=tainted), \
             patch.object(update_cn_data, "fetch_eastmoney", return_value=tainted), \
             patch.dict(sys.modules, {"baostock": types.SimpleNamespace(login=lambda: None, logout=lambda: None)}):
            df = update_cn_data.fetch("600519.SS", "2026-05-06", "2026-06-18")

        self.assertTrue(df.empty)

    def test_fetch_eastmoney_parses_daily_kline_rows(self):
        with patch.object(update_cn_data.urllib.request, "urlopen", return_value=FakeEastmoneyResponse()):
            df = update_cn_data.fetch_eastmoney("600519.SS", "2026-06-18", "2026-06-22")

        self.assertFalse(df.empty)
        self.assertEqual(list(df.index), ["2026-06-22"])
        self.assertEqual(float(df.loc["2026-06-22", "open"]), 1370.0)
        self.assertEqual(float(df.loc["2026-06-22", "close"]), 1388.5)
        self.assertEqual(float(df.loc["2026-06-22", "amount"]), 1690000000.0)

    def test_fetch_tencent_parses_daily_kline_rows(self):
        with patch.object(update_cn_data.urllib.request, "urlopen", return_value=FakeTencentResponse()):
            df = update_cn_data.fetch_tencent("600519.SS", "2026-06-18", "2026-06-22")

        self.assertFalse(df.empty)
        self.assertEqual(list(df.index), ["2026-06-22"])
        self.assertEqual(float(df.loc["2026-06-22", "open"]), 1214.31)
        self.assertEqual(float(df.loc["2026-06-22", "close"]), 1241.41)
        self.assertEqual(float(df.loc["2026-06-22", "volume"]), 5825100.0)
        self.assertEqual(round(float(df.loc["2026-06-22", "amount"]), 2), 7231337391.0)

    def test_fetch_ignores_tencent_and_eastmoney_for_writes(self):
        """fetch() 写入链路只允许 baostock；即使 tencent/eastmoney 有数据也不采用。"""
        tencent_frame = pd.DataFrame(
            {
                "open": [1214.31],
                "close": [1241.41],
                "high": [1252.8],
                "low": [1205.0],
                "volume": [5825100.0],
                "amount": [7230011991.0],
                "factor": [1.0],
            },
            index=["2026-06-22"],
        )

        with patch.object(update_cn_data, "fetch_baostock", return_value=pd.DataFrame()), \
             patch.object(update_cn_data, "fetch_tencent", return_value=tencent_frame), \
             patch.object(update_cn_data, "fetch_eastmoney", side_effect=AssertionError("Eastmoney should not be called")):
            df = update_cn_data.fetch("600519.SS", "2026-06-18", "2026-06-22")

        self.assertTrue(df.empty)

    def test_fetch_eastmoney_remains_available_as_validation_helper(self):
        """fetch_eastmoney 解析能力保留，用于重建后对照校验，但不进入 fetch() 写入链路。"""
        eastmoney_frame = pd.DataFrame(
            {
                "open": [1370.0],
                "close": [1388.5],
                "high": [1390.0],
                "low": [1368.0],
                "volume": [1234567.0],
                "amount": [1690000000.0],
                "factor": [1.0],
            },
            index=["2026-06-22"],
        )

        with patch.object(update_cn_data, "fetch_baostock", return_value=pd.DataFrame()), \
             patch.object(update_cn_data, "fetch_tencent", return_value=pd.DataFrame(), create=True), \
             patch.object(update_cn_data, "fetch_eastmoney", return_value=eastmoney_frame):
            df = update_cn_data.fetch("600519.SS", "2026-06-18", "2026-06-22")

        # 写入链路不应采用东财
        self.assertTrue(df.empty)

        # 但解析函数本身仍可用
        with patch.object(update_cn_data.urllib.request, "urlopen", return_value=FakeEastmoneyResponse()):
            parsed = update_cn_data.fetch_eastmoney("600519.SS", "2026-06-18", "2026-06-22")
        self.assertFalse(parsed.empty)
        self.assertEqual(float(parsed.loc["2026-06-22", "close"]), 1388.5)

    def test_update_returns_failure_when_reference_data_unavailable(self):
        with patch.object(update_cn_data, "fetch", return_value=EmptyFrame()):
            exit_code = update_cn_data.update(start="2026-05-06", end="2026-05-07", max_stocks=1)

        self.assertEqual(exit_code, 2)

    def test_update_returns_failure_when_no_feature_files_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            (data_dir / "calendars").mkdir(parents=True)
            (data_dir / "instruments").mkdir(parents=True)
            (data_dir / "features").mkdir(parents=True)
            (data_dir / "calendars" / "day.txt").write_text("2026-05-06\n", encoding="utf-8")

            with patch.object(update_cn_data, "DATA_DIR", data_dir), \
                 patch.object(update_cn_data, "fetch", return_value=FakeRefFrame()):
                exit_code = update_cn_data.update(start="2026-05-06", end="2026-05-07", max_stocks=1)

        self.assertEqual(exit_code, 3)

    def test_update_returns_failure_when_all_stocks_fetch_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            stock_dir = data_dir / "features" / "sh600519"
            (data_dir / "calendars").mkdir(parents=True)
            (data_dir / "instruments").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (data_dir / "calendars" / "day.txt").write_text("2026-05-06\n", encoding="utf-8")
            (stock_dir / "close.day.bin").write_bytes(b"placeholder")

            def fake_fetch(code, start, end):
                return FakeRefFrame() if code == "510300.SS" else EmptyFrame()

            with patch.object(update_cn_data, "DATA_DIR", data_dir), \
                 patch.object(update_cn_data, "fetch", side_effect=fake_fetch), \
                 patch.object(update_cn_data.time, "sleep"):
                exit_code = update_cn_data.update(start="2026-05-06", end="2026-05-07", max_stocks=1)

        self.assertEqual(exit_code, 4)

    def test_sample_update_does_not_update_instruments_end_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            stock_dir = data_dir / "features" / "sh600519"
            (data_dir / "calendars").mkdir(parents=True)
            (data_dir / "instruments").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (data_dir / "calendars" / "day.txt").write_text("2026-05-06\n", encoding="utf-8")
            (data_dir / "instruments" / "csi300.txt").write_text(
                "sh600519\t2020-01-01\t2026-05-06\n",
                encoding="utf-8",
            )
            import numpy as np

            for field in update_cn_data.FIELDS + update_cn_data.EXTRA_FIELDS:
                np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / f"{field}.day.bin")

            stock_frame = pd.DataFrame(
                {
                    "open": [11.0],
                    "close": [12.0],
                    "high": [13.0],
                    "low": [10.0],
                    "volume": [100.0],
                    "amount": [1200.0],
                    "factor": [1.0],
                },
                index=["2026-05-07"],
            )

            with patch.object(update_cn_data, "DATA_DIR", data_dir), \
                 patch.object(update_cn_data, "fetch", return_value=stock_frame), \
                 patch.object(update_cn_data.time, "sleep"):
                exit_code = update_cn_data.update(start="2026-05-06", end="2026-05-07", max_stocks=1)

            instrument_text = (data_dir / "instruments" / "csi300.txt").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 0)
        self.assertIn("2026-05-06", instrument_text)
        self.assertNotIn("2026-05-07", instrument_text)

    def test_update_can_filter_specific_codes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            (data_dir / "calendars").mkdir(parents=True)
            (data_dir / "instruments").mkdir(parents=True)
            for code in ("sh600519", "sz300750"):
                stock_dir = data_dir / "features" / code
                stock_dir.mkdir(parents=True)
                for field in update_cn_data.FIELDS + update_cn_data.EXTRA_FIELDS:
                    np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / f"{field}.day.bin")
            (data_dir / "calendars" / "day.txt").write_text("2026-05-06\n", encoding="utf-8")

            stock_frame = pd.DataFrame(
                {
                    "open": [11.0],
                    "close": [12.0],
                    "high": [13.0],
                    "low": [10.0],
                    "volume": [100.0],
                    "amount": [1200.0],
                    "factor": [1.0],
                },
                index=["2026-05-06"],
            )
            fetched_codes = []

            def fake_fetch(code, start, end):
                fetched_codes.append(code)
                return stock_frame

            with patch.object(update_cn_data, "DATA_DIR", data_dir), \
                 patch.object(update_cn_data, "fetch", side_effect=fake_fetch), \
                 patch.object(update_cn_data.time, "sleep"):
                exit_code = update_cn_data.update(
                    start="2026-05-06",
                    end="2026-05-07",
                    max_stocks=None,
                    codes=["sz300750"],
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("300750.SZ", fetched_codes)
        self.assertNotIn("600519.SS", fetched_codes)

    def test_update_filters_provider_rows_after_requested_end_date(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            stock_dir = data_dir / "features" / "sh600519"
            (data_dir / "calendars").mkdir(parents=True)
            (data_dir / "instruments").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (data_dir / "calendars" / "day.txt").write_text("2026-06-22\n", encoding="utf-8")
            (data_dir / "instruments" / "csi300.txt").write_text(
                "sh600519\t2020-01-01\t2026-06-22\n",
                encoding="utf-8",
            )
            for field in update_cn_data.FIELDS + update_cn_data.EXTRA_FIELDS:
                np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / f"{field}.day.bin")

            provider_frame = pd.DataFrame(
                {
                    "open": [11.0, 99.0],
                    "close": [12.0, 100.0],
                    "high": [13.0, 101.0],
                    "low": [10.0, 98.0],
                    "volume": [100.0, 900.0],
                    "amount": [1200.0, 90000.0],
                    "factor": [1.0, 1.0],
                },
                index=["2026-06-23", "2026-06-24"],
            )

            with patch.object(update_cn_data, "DATA_DIR", data_dir), \
                 patch.object(update_cn_data, "fetch", return_value=provider_frame), \
                 patch.object(update_cn_data.time, "sleep"):
                exit_code = update_cn_data.update(
                    start="2026-06-22",
                    end="2026-06-23",
                    max_stocks=None,
                )

            calendar_text = (data_dir / "calendars" / "day.txt").read_text(encoding="utf-8")
            instrument_text = (data_dir / "instruments" / "csi300.txt").read_text(encoding="utf-8")
            close_raw = np.fromfile(stock_dir / "close.day.bin", dtype="<f")

        self.assertEqual(exit_code, 0)
        self.assertIn("2026-06-23", calendar_text)
        self.assertNotIn("2026-06-24", calendar_text)
        self.assertIn("2026-06-23", instrument_text)
        self.assertNotIn("2026-06-24", instrument_text)
        self.assertEqual(float(close_raw[-1]), 12.0)

    def test_rebuild_stale_short_bin_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            stock_dir = data_dir / "features" / "sz300750"
            (data_dir / "calendars").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            calendar = [f"2026-01-{day:02d}" for day in range(1, 29)]
            calendar += [f"2026-02-{day:02d}" for day in range(1, 29)]
            calendar += [f"2026-03-{day:02d}" for day in range(1, 29)]
            (data_dir / "calendars" / "day.txt").write_text("\n".join(calendar) + "\n", encoding="utf-8")
            for field in update_cn_data.FIELDS + update_cn_data.EXTRA_FIELDS:
                np.array([0.0, 99.0], dtype="<f").tofile(stock_dir / f"{field}.day.bin")

            df = pd.DataFrame(
                {
                    "open": [11.0, 12.0],
                    "close": [21.0, 22.0],
                    "high": [31.0, 32.0],
                    "low": [10.0, 11.0],
                    "volume": [100.0, 200.0],
                    "amount": [2100.0, 4400.0],
                    "factor": [1.0, 1.0],
                },
                index=["2026-03-01", "2026-03-02"],
            )

            with patch.object(update_cn_data, "DATA_DIR", data_dir), \
                 patch.object(update_cn_data, "REBUILD_GAP_THRESHOLD", 10):
                appended = update_cn_data.append_to_bin(
                    "sz300750",
                    df,
                    calendar,
                    rebuild_stale=True,
                )

            raw = np.fromfile(stock_dir / "close.day.bin", dtype="<f")

        self.assertEqual(appended, 2)
        self.assertEqual(int(raw[0]), calendar.index("2026-03-01"))
        self.assertEqual(float(raw[-1]), 22.0)

    def test_rebuild_stale_repairs_existing_zero_ohlc_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            stock_dir = data_dir / "features" / "sh600519"
            (data_dir / "calendars").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            calendar = ["2026-03-20", "2026-03-23", "2026-03-24"]
            (data_dir / "calendars" / "day.txt").write_text("\n".join(calendar) + "\n", encoding="utf-8")

            for field in update_cn_data.FIELDS + update_cn_data.EXTRA_FIELDS:
                np.array([0.0, 0.0, 0.0, 1300.0], dtype="<f").tofile(stock_dir / f"{field}.day.bin")

            df = pd.DataFrame(
                {
                    "open": [1400.0, 1401.0],
                    "close": [1395.0, 1396.0],
                    "high": [1410.0, 1411.0],
                    "low": [1380.0, 1381.0],
                    "volume": [100.0, 200.0],
                    "amount": [139500.0, 279200.0],
                    "factor": [1.0, 1.0],
                },
                index=["2026-03-20", "2026-03-23"],
            )

            with patch.object(update_cn_data, "DATA_DIR", data_dir):
                changed = update_cn_data.append_to_bin(
                    "sh600519",
                    df,
                    calendar,
                    rebuild_stale=True,
                )

            open_raw = np.fromfile(stock_dir / "open.day.bin", dtype="<f")
            close_raw = np.fromfile(stock_dir / "close.day.bin", dtype="<f")

        self.assertEqual(changed, 2)
        self.assertEqual(list(open_raw), [0.0, 1400.0, 1401.0, 1300.0])
        self.assertEqual(list(close_raw), [0.0, 1395.0, 1396.0, 1300.0])

    def test_overwrite_existing_repairs_nonzero_prices_and_factor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            stock_dir = data_dir / "features" / "sh600519"
            (data_dir / "calendars").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            calendar = ["2026-03-20", "2026-03-23", "2026-03-24"]
            (data_dir / "calendars" / "day.txt").write_text("\n".join(calendar) + "\n", encoding="utf-8")

            for field in update_cn_data.FIELDS + ["amount"]:
                np.array([0.0, 99.0, 100.0, 101.0], dtype="<f").tofile(stock_dir / f"{field}.day.bin")
            np.array([0.0, 0.5, 0.5, 0.5], dtype="<f").tofile(stock_dir / "factor.day.bin")

            df = pd.DataFrame(
                {
                    "open": [1400.0, 1401.0],
                    "close": [1395.0, 1396.0],
                    "high": [1410.0, 1411.0],
                    "low": [1380.0, 1381.0],
                    "volume": [100.0, 200.0],
                    "amount": [139500.0, 279200.0],
                    "factor": [12.76, 12.76],
                },
                index=["2026-03-20", "2026-03-23"],
            )

            with patch.object(update_cn_data, "DATA_DIR", data_dir):
                changed = update_cn_data.append_to_bin(
                    "sh600519",
                    df,
                    calendar,
                    rebuild_stale=True,
                    overwrite_existing=True,
                )

            close_raw = np.fromfile(stock_dir / "close.day.bin", dtype="<f")
            factor_raw = np.fromfile(stock_dir / "factor.day.bin", dtype="<f")

        self.assertEqual(changed, 2)
        # close 因 overwrite 被重写为 df 新值
        self.assertEqual(list(close_raw), [0.0, 1395.0, 1396.0, 101.0])
        # factor 在新方案下也是真数据，overwrite 时一并重写（不再被保护为占位符）
        self.assertEqual(list(factor_raw), [0.0, 12.76, 12.76, 0.5])

    def test_append_rejects_mixed_adjustment_regime_overlap(self):
        """对旧前复权目录误跑后复权增量，重叠日相对偏差 >0.5% 必须拒绝追加。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            stock_dir = data_dir / "features" / "sh600519"
            (data_dir / "calendars").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            calendar = ["2026-03-20", "2026-03-23", "2026-03-24", "2026-03-25"]
            (data_dir / "calendars" / "day.txt").write_text("\n".join(calendar) + "\n", encoding="utf-8")

            # 现有 bin：旧前复权口径，2026-03-23 close=10.0
            for field in update_cn_data.FIELDS + ["amount"]:
                np.array([0.0, 9.0, 10.0, 10.5], dtype="<f").tofile(stock_dir / f"{field}.day.bin")
            np.array([0.0, 1.0, 1.0, 1.0], dtype="<f").tofile(stock_dir / "factor.day.bin")

            # 新数据：后复权口径，重叠日 2026-03-23 close=127.6（与旧值 10.0 偏差远超 0.5%）
            df = pd.DataFrame(
                {
                    "open": [120.0, 128.0],
                    "close": [127.6, 129.0],
                    "high": [130.0, 131.0],
                    "low": [119.0, 127.0],
                    "volume": [100.0, 200.0],
                    "amount": [12760.0, 25800.0],
                    "factor": [12.76, 12.76],
                },
                index=["2026-03-23", "2026-03-25"],
            )

            with patch.object(update_cn_data, "DATA_DIR", data_dir):
                appended = update_cn_data.append_to_bin("sh600519", df, calendar)

        self.assertEqual(appended, 0)

    def test_full_rebuild_writes_complete_bin_from_scratch(self):
        """--full-rebuild 从零构造完整 bin：start_idx=上市首日日历索引，按日历逐日填，缺失填 NaN。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data_new"
            (data_dir / "calendars").mkdir(parents=True)
            (data_dir / "instruments").mkdir(parents=True)
            (data_dir / "features" / "sh600000").mkdir(parents=True)
            calendar = ["2014-06-20", "2014-06-23", "2014-06-24", "2014-06-25", "2014-06-26"]
            (data_dir / "calendars" / "day.txt").write_text("\n".join(calendar) + "\n", encoding="utf-8")

            # 仅 3 个交易日有数据，中间和首尾缺失
            df = pd.DataFrame(
                {
                    "open": [120.0, 121.0, 123.0],
                    "close": [121.0, 122.0, 124.0],
                    "high": [122.0, 123.0, 125.0],
                    "low": [119.0, 120.0, 122.0],
                    "volume": [1000.0, 1100.0, 1200.0],
                    "amount": [121000.0, 134200.0, 148800.0],
                    "factor": [1.0, 6.015655, 6.015655],
                },
                index=["2014-06-23", "2014-06-24", "2014-06-25"],
            )

            with patch.object(update_cn_data, "DATA_DIR", data_dir):
                written = update_cn_data.full_rebuild_stock("sh600000", df, calendar)

            import numpy as np
            close_raw = np.fromfile(data_dir / "features" / "sh600000" / "close.day.bin", dtype="<f")
            factor_raw = np.fromfile(data_dir / "features" / "sh600000" / "factor.day.bin", dtype="<f")

        self.assertEqual(written, 7)  # 七个字段整文件覆盖
        # start_idx = df 首日 2014-06-23 在日历中的索引 = 1
        self.assertEqual(int(close_raw[0]), 1)
        # 长度 = 1(start_idx) + (日历尾idx4 - df首日idx1 + 1) = 1 + 4 = 5
        self.assertEqual(len(close_raw), 5)
        # close: [start_idx=1, 06-23=121, 06-24=122, 06-25=124, 06-26=NaN]
        self.assertAlmostEqual(float(close_raw[1]), 121.0)  # 2014-06-23
        self.assertAlmostEqual(float(close_raw[2]), 122.0)  # 2014-06-24
        self.assertAlmostEqual(float(close_raw[3]), 124.0)  # 2014-06-25
        self.assertFalse(np.isfinite(close_raw[4]))         # 2014-06-26 缺失
        # factor 阶梯：2014-06-23=1.0，2014-06-24 起=6.015655
        self.assertAlmostEqual(float(factor_raw[1]), 1.0, places=4)
        self.assertAlmostEqual(float(factor_raw[2]), 6.015655, places=4)

    def test_full_rebuild_overwrites_existing_bin_completely(self):
        """--full-rebuild 整文件覆盖，不走 repair+append；旧 bin 的错误 start_idx 被丢弃。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data_new"
            stock_dir = data_dir / "features" / "sh600519"
            (data_dir / "calendars").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            calendar = ["2026-03-20", "2026-03-23", "2026-03-24"]
            (data_dir / "calendars" / "day.txt").write_text("\n".join(calendar) + "\n", encoding="utf-8")

            # 旧 bin：错误的 start_idx=9999 + 1999 幽灵段
            import numpy as np
            np.array([9999.0, 1459.0, 1500.0], dtype="<f").tofile(stock_dir / "close.day.bin")

            df = pd.DataFrame(
                {"open": [10.0], "close": [11.0], "high": [12.0], "low": [9.0],
                 "volume": [100.0], "amount": [1100.0], "factor": [12.76]},
                index=["2026-03-20"],
            )

            with patch.object(update_cn_data, "DATA_DIR", data_dir):
                written = update_cn_data.full_rebuild_stock("sh600519", df, calendar)

            close_raw = np.fromfile(stock_dir / "close.day.bin", dtype="<f")

        self.assertEqual(int(close_raw[0]), 0)  # 新 start_idx，不再是 9999
        self.assertEqual(len(close_raw), 4)  # 1 + 3 日历天
        self.assertAlmostEqual(float(close_raw[1]), 11.0)  # 2026-03-20

    def test_overlap_check_warns_when_no_overlap_in_incremental_mode(self):
        """非重建模式下，抓取窗口与现有数据无重叠日时应 warning（防护不形同虚设）。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            stock_dir = data_dir / "features" / "sh600519"
            (data_dir / "calendars").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            calendar = ["2026-03-20", "2026-03-23", "2026-03-24", "2026-03-25"]
            (data_dir / "calendars" / "day.txt").write_text("\n".join(calendar) + "\n", encoding="utf-8")

            # 现有 bin 覆盖到 2026-03-23（end_idx=1）
            import numpy as np
            for field in update_cn_data.FIELDS + ["amount", "factor"]:
                np.array([0.0, 10.0, 11.0], dtype="<f").tofile(stock_dir / f"{field}.day.bin")

            # 新数据全部 > end_idx（2026-03-24 起，无重叠）→ overlap_checks=0 → warning
            df = pd.DataFrame(
                {"open": [12.0], "close": [12.5], "high": [13.0], "low": [12.0],
                 "volume": [200.0], "amount": [2500.0], "factor": [1.0]},
                index=["2026-03-24"],
            )

            import io, contextlib
            buf = io.StringIO()
            with patch.object(update_cn_data, "DATA_DIR", data_dir), contextlib.redirect_stdout(buf):
                result = update_cn_data._check_overlap_consistency("sh600519", df, calendar)
            output = buf.getvalue()

        # 无重叠不拦截合法增量（result 仍 None），但打印 warning
        self.assertIsNone(result)
        self.assertIn("无重叠日", output)


if __name__ == "__main__":
    unittest.main()
