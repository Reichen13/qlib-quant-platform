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

    def __init__(self):
        self.rows = [
            [
                "2026-05-07",
                "sh.600519",
                "1375.00",
                "1388.00",
                "1370.01",
                "1371.05",
                "4046147",
                "5573286314.86",
            ]
        ]
        self.index = -1

    def next(self):
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self):
        return self.rows[self.index]


class FakeBaostockModule:
    def login(self):
        return types.SimpleNamespace(error_code="0", error_msg="success")

    def logout(self):
        return None

    def query_history_k_data_plus(self, code, fields, start_date, end_date, frequency, adjustflag):
        return FakeBaostockResult()


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
    def test_extend_calendar_rewrites_unsorted_duplicate_calendar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "cn_data"
            (data_dir / "calendars").mkdir(parents=True)
            cal_path = data_dir / "calendars" / "day.txt"
            cal_path.write_text(
                "2026-06-22\n2026-06-23\n2026-06-24\n2025-10-24\n",
                encoding="utf-8",
            )

            with patch.object(update_cn_data, "DATA_DIR", data_dir):
                calendar = update_cn_data.extend_calendar(["2026-06-24", "2026-06-25"])

            calendar_text = cal_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(calendar, ["2025-10-24", "2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25"])
        self.assertEqual(calendar_text, calendar)

    def test_beijing_exchange_code_conversions(self):
        self.assertEqual(update_cn_data.qlib_to_yf("bj430047"), "430047.BJ")
        self.assertEqual(update_cn_data.yf_to_baostock("430047.BJ"), "bj.430047")

    def test_fetch_falls_back_to_baostock_when_yfinance_is_empty(self):
        with patch.object(update_cn_data.yf, "Ticker", FakeYfinanceTicker, create=True), \
             patch.object(update_cn_data, "fetch_tencent", return_value=pd.DataFrame()), \
             patch.dict(sys.modules, {"baostock": FakeBaostockModule()}):
            df = update_cn_data.fetch("600519.SS", "2026-05-06", "2026-06-18")

        self.assertFalse(df.empty)
        self.assertEqual(list(df.index), ["2026-05-07"])
        self.assertEqual(float(df.loc["2026-05-07", "close"]), 1371.05)
        self.assertEqual(float(df.loc["2026-05-07", "amount"]), 5573286314.86)

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

    def test_fetch_falls_back_to_tencent_before_eastmoney(self):
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

        with patch.object(update_cn_data.yf, "Ticker", FakeYfinanceTicker, create=True), \
             patch.object(update_cn_data, "fetch_baostock", return_value=pd.DataFrame()), \
             patch.object(update_cn_data, "fetch_tencent", return_value=tencent_frame), \
             patch.object(update_cn_data, "fetch_eastmoney", side_effect=AssertionError("Eastmoney should not be called")):
            df = update_cn_data.fetch("600519.SS", "2026-06-18", "2026-06-22")

        self.assertEqual(list(df.index), ["2026-06-22"])
        self.assertEqual(float(df.loc["2026-06-22", "close"]), 1241.41)

    def test_fetch_falls_back_to_eastmoney_when_yfinance_and_baostock_are_empty(self):
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

        with patch.object(update_cn_data.yf, "Ticker", FakeYfinanceTicker, create=True), \
             patch.object(update_cn_data, "fetch_baostock", return_value=pd.DataFrame()), \
             patch.object(update_cn_data, "fetch_tencent", return_value=pd.DataFrame(), create=True), \
             patch.object(update_cn_data, "fetch_eastmoney", return_value=eastmoney_frame):
            df = update_cn_data.fetch("600519.SS", "2026-06-18", "2026-06-22")

        self.assertEqual(list(df.index), ["2026-06-22"])
        self.assertEqual(float(df.loc["2026-06-22", "close"]), 1388.5)

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

    def test_overwrite_existing_repairs_nonzero_prices_but_preserves_factor(self):
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
                    overwrite_existing=True,
                )

            close_raw = np.fromfile(stock_dir / "close.day.bin", dtype="<f")
            factor_raw = np.fromfile(stock_dir / "factor.day.bin", dtype="<f")

        self.assertEqual(changed, 2)
        self.assertEqual(list(close_raw), [0.0, 1395.0, 1396.0, 101.0])
        self.assertEqual(list(factor_raw), [0.0, 0.5, 0.5, 0.5])


if __name__ == "__main__":
    unittest.main()
