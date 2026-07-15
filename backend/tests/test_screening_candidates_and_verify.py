import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

# Import the same module object used by the API (db.* path on sys.path)
from db import screening_history as sh  # noqa: E402
from api import screening as screening_api  # noqa: E402


class ScreeningHistoryAgeFilterTests(unittest.TestCase):
    def test_get_last_n_runs_respects_min_age_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmpdir := tmp) / "screening_history.db"
            with patch.object(sh, "DB_PATH", db_path):
                sh.init_db()
                today = date.today()
                sh.save_run(today.isoformat(), [{"code": "SH600000"}])
                old = (today - timedelta(days=10)).isoformat()
                sh.save_run(old, [{"code": "SH600519"}])

                aged = sh.get_last_n_runs(n=5, min_age_days=5)
                dates = [r["run_date"] for r in aged]
                self.assertIn(old, dates)
                self.assertNotIn(today.isoformat(), dates)

    def test_update_verification_keeps_win_rate_and_return_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "screening_history.db"
            with patch.object(sh, "DB_PATH", db_path):
                sh.init_db()
                day = "2026-06-01"
                sh.save_run(day, [{"code": "SH600000"}], candidate_source={"source": "stock_pool"})
                sh.update_verification(day, win_rate=0.4, avg_t5_return=-0.012)
                rows = sh.get_recent_runs(limit=1)
                self.assertEqual(rows[0]["win_rate_verified"], 0.4)
                self.assertEqual(rows[0]["avg_t5_return"], -0.012)
                self.assertNotEqual(rows[0]["win_rate_verified"], rows[0]["avg_t5_return"])


class ResolveCandidatesTests(unittest.TestCase):
    def test_request_candidates_win(self):
        codes, meta = screening_api.resolve_screening_candidates(
            ["600519", "000001"],
            top_n=10,
            warnings=[],
        )
        self.assertEqual(codes, ["600519", "000001"])
        self.assertEqual(meta["source"], "request")

    def test_stock_pool_source_used_when_history_exists(self):
        with patch.object(
            screening_api,
            "load_latest_pool_candidates",
            return_value=(
                ["600519.SS", "000858.SZ"],
                {
                    "source": "stock_pool",
                    "pool_id": "p1",
                    "pool_name": "主池",
                    "as_of": "2026-07-08",
                    "count": 2,
                    "top_n": 30,
                },
            ),
        ):
            warnings: list[str] = []
            codes, meta = screening_api.resolve_screening_candidates(None, warnings=warnings)
            self.assertEqual(codes, ["600519.SS", "000858.SZ"])
            self.assertEqual(meta["source"], "stock_pool")
            self.assertTrue(any("股票池" in w for w in warnings))

    def test_hardcoded_fallback_when_no_pool(self):
        with patch.object(screening_api, "load_latest_pool_candidates", return_value=([], None)):
            warnings: list[str] = []
            codes, meta = screening_api.resolve_screening_candidates(None, warnings=warnings)
            self.assertEqual(codes, screening_api.DEFAULT_CANDIDATES)
            self.assertEqual(meta["source"], "hardcoded_fallback")
            self.assertTrue(any("硬编码" in w for w in warnings))


class VerifyRunT5Tests(unittest.TestCase):
    def test_verify_run_persists_separate_metrics(self):
        run = {
            "run_date": "2026-06-01",
            "top_buyable_json": json.dumps([
                {"code": "SH600000", "name": "浦发"},
                {"code": "SH600519", "name": "茅台"},
            ]),
        }

        class FakeD:
            @staticmethod
            def calendar(freq="day"):
                base = date(2026, 6, 1)
                return [base + timedelta(days=i) for i in range(10)]

            @staticmethod
            def features(codes, fields, start_time=None, end_time=None):
                import pandas as pd

                code = codes[0]
                # 600000 up, 600519 down
                if "600000" in code:
                    closes = [10.0, 10.5, 10.8, 11.0, 11.2, 11.5]
                else:
                    closes = [100.0, 99.0, 98.0, 97.0, 96.0, 95.0]
                idx = pd.date_range("2026-06-01", periods=len(closes), freq="D")
                return pd.DataFrame({"$close": closes}, index=idx)

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "screening_history.db"
            import types

            qlib_mod = types.ModuleType("qlib")
            qlib_data = types.ModuleType("qlib.data")
            qlib_data.D = FakeD
            with patch.object(sh, "DB_PATH", db_path), patch.dict(
                sys.modules,
                {"qlib": qlib_mod, "qlib.data": qlib_data},
            ):
                sh.init_db()
                sh.save_run(run["run_date"], json.loads(run["top_buyable_json"]))
                stats = screening_api.verify_run_t5(run, persist=True)

                self.assertIsNotNone(stats)
                self.assertEqual(stats["stocks"], 2)
                self.assertEqual(stats["won"], 1)
                self.assertAlmostEqual(stats["win_rate"], 0.5, places=4)
                self.assertAlmostEqual(
                    stats["avg_t5_return"],
                    ((11.5 / 10 - 1) + (95 / 100 - 1)) / 2,
                    places=4,
                )
                rows = sh.get_recent_runs(1)
                self.assertEqual(rows[0]["win_rate_verified"], stats["win_rate"])
                self.assertEqual(rows[0]["avg_t5_return"], stats["avg_t5_return"])
                self.assertNotEqual(rows[0]["win_rate_verified"], rows[0]["avg_t5_return"])


class CircuitBreakerTests(unittest.TestCase):
    def test_circuit_breaker_activates_on_three_low_win_rates(self):
        fake_stats = [
            {"run_date": "2026-05-01", "win_rate": 0.2, "avg_t5_return": -0.01, "stocks": 5, "won": 1},
            {"run_date": "2026-05-08", "win_rate": 0.3, "avg_t5_return": -0.02, "stocks": 5, "won": 1},
            {"run_date": "2026-05-15", "win_rate": 0.1, "avg_t5_return": -0.03, "stocks": 5, "won": 0},
        ]
        calls = {"i": 0}

        def fake_verify(run, persist=True):
            i = calls["i"]
            calls["i"] += 1
            if i < len(fake_stats):
                return fake_stats[i]
            return None

        with patch.object(screening_api, "get_last_n_runs", return_value=[{}, {}, {}]), patch.object(
            screening_api, "verify_run_t5", side_effect=fake_verify
        ):
            warnings: list[str] = []
            result = screening_api._check_circuit_breaker(warnings)
            self.assertTrue(result["active"])
            self.assertTrue(any("circuit_breaker" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
