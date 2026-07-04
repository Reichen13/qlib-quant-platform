import sys
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

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
        exception=lambda *args, **kwargs: None,
        add=lambda *args, **kwargs: None,
        remove=lambda *args, **kwargs: None,
    )
    sys.modules["loguru"] = types.SimpleNamespace(logger=logger)

from backend.api import data
from backend.db.task_store import TaskStore


class FakeConfiguredTdxProvider:
    is_configured = True

    def safe_status(self):
        return {
            "configured": True,
            "url": "https://mcp.tdx.com.cn:3001/mcp",
            "stock_list_tool": None,
            "stock_list_enabled": False,
            "wenda_tool": "tdx_wenda_quotes",
        }

    def list_tools(self):
        raise AssertionError("TDX MCP should not be called by default")


class DataApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.tmp_dir.name) / "data_update_tasks.db", table_name="data_update_tasks_test")
        self.store.init_db()
        self.store_patch = patch.object(data, "data_update_task_store", self.store)
        self.store_patch.start()
        data._update_tasks.clear()

    async def asyncTearDown(self):
        data._update_tasks.clear()
        self.store_patch.stop()
        self.tmp_dir.cleanup()

    async def test_health_does_not_call_baostock_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            (qlib_dir / "features" / "sh600519").mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text("2026-06-18\n", encoding="utf-8")
            (qlib_dir / "instruments" / "csi300.txt").write_text("sh600519\t2020-01-01\t2026-06-18\n", encoding="utf-8")

            with patch.object(Path, "home", return_value=Path(tmpdir)), \
                 patch.object(data, "_check_baostock_industry", side_effect=AssertionError("baostock should not be called")), \
                 patch("services.tdx_mcp_provider.TdxMcpProvider.from_env", return_value=FakeConfiguredTdxProvider()):
                response = await data.data_health_check()

        self.assertIn("sources", response)
        self.assertEqual(response["sources"]["baostock_industry"]["status"], "unknown")
        self.assertEqual(response["sources"]["tdx_mcp"]["status"], "unknown")
        self.assertTrue(response["sources"]["tdx_mcp"]["configured"])
        self.assertIn("stocks", response["sources"])

    async def test_stocks_health_uses_latest_feature_bin_date_not_calendar_tail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            stock_dir = qlib_dir / "features" / "sh600519"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text(
                "2026-05-06\n2026-05-07\n2026-05-08\n",
                encoding="utf-8",
            )
            (qlib_dir / "instruments" / "csi300.txt").write_text(
                "sh600519\t2020-01-01\t2026-06-18\n",
                encoding="utf-8",
            )
            np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / "close.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_stocks_data()

        self.assertEqual(response["last_date"], "2026-05-06")

    async def test_stocks_health_flags_sparse_close_bins(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            stock_dir = qlib_dir / "features" / "sh600519"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text(
                "2026-05-06\n2026-05-07\n2026-05-08\n2026-05-11\n",
                encoding="utf-8",
            )
            (qlib_dir / "instruments" / "csi300.txt").write_text(
                "sh600519\t2020-01-01\t2026-05-11\n",
                encoding="utf-8",
            )
            np.array([0.0, 10.0, np.nan, np.nan, np.nan], dtype="<f").tofile(stock_dir / "close.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_stocks_data()

        self.assertEqual(response["status"], "error")
        self.assertLess(response["effective_value_density"], 0.8)
        self.assertEqual(response["max_consecutive_nan"], 3)
        self.assertIn("有效值密度", response["message"])

    async def test_qlib_health_uses_feature_bin_date_not_calendar_tail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            stock_dir = qlib_dir / "features" / "sh600519"
            (qlib_dir / "calendars").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text(
                "2026-05-06\n2026-05-07\n2026-05-08\n",
                encoding="utf-8",
            )
            np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / "close.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_qlib_data()

        self.assertEqual(response["last_date"], "2026-05-06")

    async def test_adjustment_health_flags_placeholder_factor_field(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            stock_dir = qlib_dir / "features" / "sh600519"
            (qlib_dir / "calendars").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text(
                "2026-06-18\n2026-06-19\n2026-06-22\n",
                encoding="utf-8",
            )
            np.array([0.0, 10.0, 10.2, 10.3], dtype="<f").tofile(stock_dir / "close.day.bin")
            np.array([0.0, 1.0, 1.0, 1.0], dtype="<f").tofile(stock_dir / "factor.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_price_adjustment_policy()

        self.assertEqual(response["status"], "warning")
        self.assertEqual(response["adjustment_mode"], "qfq_price_with_placeholder_factor")
        self.assertEqual(response["factor_field_status"], "placeholder_1.0")
        self.assertIn("前复权", response["message"])

    async def test_adjustment_health_flags_mixed_factor_when_latest_values_are_mostly_one(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            (qlib_dir / "features").mkdir(parents=True)
            for idx in range(5):
                stock_dir = qlib_dir / "features" / f"sh6000{idx}"
                stock_dir.mkdir(parents=True)
                np.array([0.0, 10.0, 10.2, 10.3], dtype="<f").tofile(stock_dir / "close.day.bin")
                np.array([0.0, 0.5, 0.8, 1.0], dtype="<f").tofile(stock_dir / "factor.day.bin")
            stock_dir = qlib_dir / "features" / "sh600099"
            stock_dir.mkdir(parents=True)
            np.array([0.0, 10.0, 10.2, 10.3], dtype="<f").tofile(stock_dir / "close.day.bin")
            np.array([0.0, 0.5, 0.8, 0.9], dtype="<f").tofile(stock_dir / "factor.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_price_adjustment_policy()

        self.assertEqual(response["status"], "warning")
        self.assertEqual(response["factor_field_status"], "mixed_real_and_placeholder")

    async def test_adjustment_health_returns_suspect_jump_examples(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            stock_dir = qlib_dir / "features" / "sh600519"
            (qlib_dir / "calendars").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text(
                "2026-06-18\n2026-06-19\n2026-06-22\n",
                encoding="utf-8",
            )
            np.array([0.0, 10.0, 15.0, 15.2], dtype="<f").tofile(stock_dir / "close.day.bin")
            np.array([0.0, 1.0, 1.0, 1.0], dtype="<f").tofile(stock_dir / "factor.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_price_adjustment_policy()

        self.assertEqual(response["possible_unadjusted_jump_count"], 1)
        self.assertEqual(response["suspect_examples"][0]["code"], "sh600519")
        self.assertEqual(response["suspect_examples"][0]["date"], "2026-06-19")
        self.assertGreater(response["suspect_examples"][0]["jump_pct"], 0.49)

    async def test_adjustment_health_ignores_index_feature_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text(
                "2026-06-18\n2026-06-19\n2026-06-22\n",
                encoding="utf-8",
            )
            index_dir = qlib_dir / "features" / "sh000300"
            index_dir.mkdir(parents=True)
            np.array([0.0, 10.0, 30.0, 30.2], dtype="<f").tofile(index_dir / "close.day.bin")
            np.array([0.0, 1.0, 1.0, 1.0], dtype="<f").tofile(index_dir / "factor.day.bin")
            stock_dir = qlib_dir / "features" / "sh600519"
            stock_dir.mkdir(parents=True)
            np.array([0.0, 10.0, 10.1, 10.2], dtype="<f").tofile(stock_dir / "close.day.bin")
            np.array([0.0, 1.0, 1.0, 1.0], dtype="<f").tofile(stock_dir / "factor.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_price_adjustment_policy()

        self.assertEqual(response["sample_size"], 1)
        self.assertEqual(response["possible_unadjusted_jump_count"], 0)
        self.assertEqual(response["suspect_examples"], [])

    async def test_health_includes_price_adjustment_policy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            stock_dir = qlib_dir / "features" / "sh600519"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text("2026-06-18\n", encoding="utf-8")
            (qlib_dir / "instruments" / "csi300.txt").write_text("sh600519\t2020-01-01\t2026-06-18\n", encoding="utf-8")
            np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / "close.day.bin")
            np.array([0.0, 1.0], dtype="<f").tofile(stock_dir / "factor.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)), \
                 patch("services.tdx_mcp_provider.TdxMcpProvider.from_env", return_value=FakeConfiguredTdxProvider()):
                response = await data.data_health_check()

        self.assertIn("price_adjustment", response["sources"])
        self.assertEqual(response["sources"]["price_adjustment"]["factor_field_status"], "placeholder_1.0")

    async def test_stocks_health_counts_unique_instruments_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            stock_dir = qlib_dir / "features" / "sh600519"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            stock_dir.mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text("2026-06-18\n", encoding="utf-8")
            (qlib_dir / "instruments" / "csi300.txt").write_text(
                "SH600519\t2020-01-01\t2026-06-18\n"
                "sh600519\t2020-01-01\t2026-06-18\n"
                "SZ000001\t2020-01-01\t2026-06-18\n",
                encoding="utf-8",
            )
            np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / "close.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_stocks_data()

        self.assertEqual(response["total"], 1)
        self.assertEqual(response["raw_total"], 1)
        self.assertEqual(response["duplicate_count"], 0)
        self.assertEqual(response["csi300_total"], 2)
        self.assertEqual(response["csi300_raw_total"], 3)
        self.assertEqual(response["csi300_duplicate_count"], 1)

    async def test_stocks_health_counts_beijing_exchange_feature_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text("2026-06-18\n", encoding="utf-8")
            (qlib_dir / "instruments" / "csi300.txt").write_text("", encoding="utf-8")
            for code in ("sh600519", "sz300750", "bj430047", "bj830799", "bj920118"):
                stock_dir = qlib_dir / "features" / code
                stock_dir.mkdir(parents=True)
                np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / "close.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_stocks_data()

        self.assertEqual(response["total"], 5)

    async def test_stocks_health_ignores_older_feature_bin_when_newer_sample_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            old_stock_dir = qlib_dir / "features" / "sh600000"
            new_stock_dir = qlib_dir / "features" / "sh600519"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            old_stock_dir.mkdir(parents=True)
            new_stock_dir.mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text(
                "2026-05-06\n2026-05-07\n2026-05-08\n",
                encoding="utf-8",
            )
            (qlib_dir / "instruments" / "csi300.txt").write_text(
                "sh600519\t2020-01-01\t2026-06-18\n",
                encoding="utf-8",
            )
            np.array([0.0, 10.0], dtype="<f").tofile(old_stock_dir / "close.day.bin")
            np.array([0.0, 10.0, 11.0], dtype="<f").tofile(new_stock_dir / "close.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_stocks_data()

        self.assertEqual(response["last_date"], "2026-05-07")

    async def test_stocks_health_uses_representative_date_when_only_one_stock_updated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            qlib_dir = Path(tmpdir) / ".qlib" / "qlib_data" / "cn_data"
            (qlib_dir / "calendars").mkdir(parents=True)
            (qlib_dir / "instruments").mkdir(parents=True)
            (qlib_dir / "calendars" / "day.txt").write_text(
                "2026-05-06\n2026-05-07\n2026-06-18\n",
                encoding="utf-8",
            )
            (qlib_dir / "instruments" / "csi300.txt").write_text(
                "sh600519\t2020-01-01\t2026-06-18\n",
                encoding="utf-8",
            )
            for idx in range(9):
                stock_dir = qlib_dir / "features" / f"sh60000{idx}"
                stock_dir.mkdir(parents=True)
                np.array([0.0, 10.0], dtype="<f").tofile(stock_dir / "close.day.bin")
            latest_dir = qlib_dir / "features" / "sh600519"
            latest_dir.mkdir(parents=True)
            np.array([0.0, 10.0, 11.0, 12.0], dtype="<f").tofile(latest_dir / "close.day.bin")

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                response = data._check_stocks_data()

        self.assertEqual(response["last_date"], "2026-05-06")
        self.assertEqual(response["sample_latest_date"], "2026-06-18")

    async def test_start_update_returns_task_and_records_status(self):
        data._update_tasks.clear()

        with patch.object(data, "_resolve_update_script", return_value=Path(__file__)), \
             patch.object(data, "_start_update_thread") as start_thread:
            response = await data.start_data_update(
                data.DataUpdateRequest(type="stocks", max_stocks=1)
            )

        self.assertEqual(response["status"], "running")
        self.assertIn(response["task_id"], data._update_tasks)
        start_thread.assert_called_once()

    async def test_start_update_persists_task_status(self):
        with patch.object(data, "_resolve_update_script", return_value=Path(__file__)), \
             patch.object(data, "_start_update_thread"):
            response = await data.start_data_update(
                data.DataUpdateRequest(type="stocks", max_stocks=1)
            )

        persisted = self.store.get_task(response["task_id"])

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["status"], "running")
        self.assertEqual(persisted["progress"], 5)
        self.assertIn("数据更新任务已排队", json.loads(persisted["result_json"])["message"])

    async def test_start_update_uses_actual_stock_latest_date_by_default(self):
        data._update_tasks.clear()

        with patch.object(data, "_resolve_update_script", return_value=Path(__file__)), \
             patch.object(data, "_get_stock_latest_trade_date", return_value="2026-05-06"), \
             patch.object(data, "_start_update_thread") as start_thread:
            await data.start_data_update(data.DataUpdateRequest(type="stocks", max_stocks=1))

        command = start_thread.call_args.args[1]
        self.assertIn("--start", command)
        self.assertEqual(command[command.index("--start") + 1], "2026-05-06")

    async def test_start_update_can_pass_rebuild_stale_flag(self):
        data._update_tasks.clear()

        with patch.object(data, "_resolve_update_script", return_value=Path(__file__)), \
             patch.object(data, "_start_update_thread") as start_thread:
            await data.start_data_update(
                data.DataUpdateRequest(type="stocks", max_stocks=1, rebuild_stale=True)
            )

        command = start_thread.call_args.args[1]
        self.assertIn("--rebuild-stale", command)

    async def test_start_update_can_pass_overwrite_existing_flag(self):
        data._update_tasks.clear()

        with patch.object(data, "_resolve_update_script", return_value=Path(__file__)), \
             patch.object(data, "_start_update_thread") as start_thread:
            await data.start_data_update(data.DataUpdateRequest(type="stocks", max_stocks=1, overwrite_existing=True))

        command = start_thread.call_args.args[1]
        self.assertIn("--overwrite-existing", command)

    async def test_start_update_can_pass_target_stock_codes(self):
        data._update_tasks.clear()

        with patch.object(data, "_resolve_update_script", return_value=Path(__file__)), \
             patch.object(data, "_start_update_thread") as start_thread:
            await data.start_data_update(
                data.DataUpdateRequest(
                    type="stocks",
                    codes=["600519", "300750", "688981"],
                    rebuild_stale=True,
                )
            )

        command = start_thread.call_args.args[1]
        self.assertIn("--rebuild-stale", command)
        self.assertEqual(command.count("--code"), 3)
        self.assertIn("sh600519", command)
        self.assertIn("sz300750", command)
        self.assertIn("sh688981", command)


    async def test_fast_update_core_pool_passes_priority_codes(self):
        data._update_tasks.clear()

        with patch.object(data, "_resolve_update_script", return_value=Path(__file__)), \
             patch.object(data, "_get_stock_latest_trade_date", return_value="2026-07-01"), \
             patch.object(data, "_get_core_update_codes", return_value=["sh600519", "sz000001", "sh510050"]), \
             patch.object(data, "_start_update_thread") as start_thread:
            response = await data.start_data_update(data.DataUpdateRequest(type="core", rebuild_stale=True))

        self.assertEqual(response["status"], "running")
        self.assertEqual(response["mode"], "core")
        command = start_thread.call_args.args[1]
        self.assertIn("--start", command)
        self.assertEqual(command[command.index("--start") + 1], "2026-07-01")
        self.assertIn("--rebuild-stale", command)
        self.assertEqual(command.count("--code"), 3)
        self.assertIn("sh600519", command)
        self.assertIn("sz000001", command)
        self.assertIn("sh510050", command)

    async def test_data_freshness_matrix_explains_sources_and_adjustment_policy(self):
        with patch.object(data, "_check_stocks_data", return_value={
            "last_date": "2026-07-01",
            "sample_latest_date": "2026-07-02",
            "sample_latest_coverage": 0.34,
            "status": "normal",
            "lag_days": 1,
        }), patch.object(data, "_check_price_adjustment_policy", return_value={
            "status": "warning",
            "adjustment_mode": "qfq_price_with_mixed_factor",
            "message": "mixed factor",
        }):
            result = await data.data_freshness_matrix()

        self.assertEqual(result["canonical_price_adjustment"], "front_adjusted")
        self.assertGreaterEqual(len(result["modules"]), 6)
        by_key = {item["key"]: item for item in result["modules"]}
        self.assertEqual(by_key["quote"]["primary_source"], "qlib")
        self.assertEqual(by_key["backtest"]["price_adjustment"], "front_adjusted")
        self.assertEqual(by_key["macro"]["primary_source"], "external")
        self.assertFalse(by_key["macro"]["uses_qlib_daily_bar"])
        self.assertIn("coverage", result)

    async def test_update_progress_returns_existing_task(self):
        data._update_tasks.clear()
        data._update_tasks["task-1"] = {
            "task_id": "task-1",
            "type": "stocks",
            "status": "running",
            "progress": 10,
            "message": "更新中",
            "started_at": "2026-06-19T00:00:00",
        }

        response = await data.get_data_update_progress("task-1")

        self.assertEqual(response["task_id"], "task-1")
        self.assertEqual(response["status"], "running")

    async def test_update_progress_falls_back_to_persisted_task(self):
        data._update_tasks.clear()
        self.store.create_task("task-1", json.dumps({"type": "stocks"}, ensure_ascii=False))
        self.store.set_running(
            "task-1",
            35,
            json.dumps({
                "task_id": "task-1",
                "type": "stocks",
                "status": "running",
                "progress": 35,
                "message": "正在更新 Qlib 数据",
            }, ensure_ascii=False),
        )

        response = await data.get_data_update_progress("task-1")

        self.assertEqual(response["task_id"], "task-1")
        self.assertEqual(response["status"], "running")
        self.assertEqual(response["progress"], 35)

    async def test_running_process_is_rejected(self):
        data._update_tasks.clear()
        data._update_tasks["task-1"] = {
            "task_id": "task-1",
            "type": "stocks",
            "status": "running",
            "progress": 10,
            "message": "更新中",
            "started_at": "2026-06-19T00:00:00",
        }

        with self.assertRaises(data.HTTPException) as ctx:
            await data.start_data_update(data.DataUpdateRequest(type="stocks"))

        self.assertEqual(ctx.exception.status_code, 409)

    async def test_update_key_is_required_when_server_api_key_missing(self):
        with patch.dict(data.os.environ, {}, clear=True):
            with self.assertRaises(data.HTTPException) as ctx:
                await data.require_data_update_key()

        self.assertEqual(ctx.exception.status_code, 503)

    async def test_etf_update_is_rejected_until_script_is_available(self):
        data._update_tasks.clear()

        with self.assertRaises(data.HTTPException) as ctx:
            await data.start_data_update(data.DataUpdateRequest(type="etf"))

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_completed_update_refreshes_runtime_caches(self):
        data._update_tasks.clear()
        task_id = "task-refresh"

        with patch.object(data, "_refresh_runtime_after_update", return_value={"qlib_reloaded": True, "cache_cleared": True}) as refresh_hook:
            data._save_task(
                task_id,
                task_id=task_id,
                type="stocks",
                status="running",
                progress=30,
                message="更新中",
            )
            data._save_task(
                task_id,
                status="completed",
                progress=100,
                message="更新完成",
                finished_at="2026-06-23T09:00:00",
            )

        refresh_hook.assert_called()
        persisted = self.store.get_task(task_id)
        self.assertIsNotNone(persisted)
        result = json.loads(persisted["result_json"])
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["runtime_refresh"]["qlib_reloaded"])
        self.assertTrue(result["runtime_refresh"]["cache_cleared"])

    async def test_runtime_refresh_removes_alpha158_disk_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / ".qlib" / "alpha158_cache"
            cache_dir.mkdir(parents=True)
            (cache_dir / "stale.parquet").write_text("old", encoding="utf-8")

            with patch.object(Path, "home", return_value=Path(tmpdir)), \
                 patch.object(data, "_reload_qlib_runtime", return_value={"qlib_reloaded": True}):
                result = data._refresh_runtime_after_update()

        self.assertFalse(cache_dir.exists())
        self.assertIn("alpha158_cache", result["cleared"])


if __name__ == "__main__":
    unittest.main()
