import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

_module_home = tempfile.TemporaryDirectory()
os.environ["HOME"] = _module_home.name
os.environ["USERPROFILE"] = _module_home.name

from backend.core import stock_pool  # noqa: E402


class FakeProvider:
    def get_index_stocks(self, index: str):
        raise AssertionError("refresh_pool should use the full-market stock list, not hs300")

    def get_all_stocks(self):
        return [
            {"code": "sh.600519", "code_name": "贵州茅台", "trade_status": "1"},
            {"code": "sz.000858", "code_name": "五粮液", "trade_status": "1"},
            {"code": "sz.000333", "code_name": "美的集团", "trade_status": "1"},
        ]

    def get_industry(self, code: str):
        return {"industry": "消费"}


class EmptyProvider:
    def get_index_stocks(self, index: str):
        return []

    def get_all_stocks(self):
        return []

    def get_industry(self, code: str):
        return None


class StockPoolRefreshTests(unittest.TestCase):
    def test_refresh_pool_reports_real_input_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_pools.db"
            with patch.object(stock_pool, "DB_PATH", db_path):
                stock_pool._init_db()
                conn = stock_pool._get_db()
                conn.execute(
                    "INSERT INTO pools (id, name, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    ("pool1", "测试股票池", json.dumps({}), "2026-06-20T00:00:00", "2026-06-20T00:00:00"),
                )
                conn.commit()
                conn.close()

                engine = stock_pool.StockPoolEngine()
                engine._provider = FakeProvider()
                with patch.object(engine, "execute_layer2", return_value=[
                    {"code": "600519.SS", "score": 0.9, "rank": 1},
                    {"code": "000858.SZ", "score": 0.8, "rank": 2},
                ]):
                    result = engine.refresh_pool("pool1")

        self.assertEqual(result["stats"]["input_count"], 3)
        self.assertEqual(result["stats"]["post_layer3"], 2)

    def test_simple_layer2_returns_empty_when_no_real_price_data(self):
        engine = stock_pool.StockPoolEngine()
        fake_qlib_data = SimpleNamespace(D=SimpleNamespace(features=lambda *args, **kwargs: None))

        with patch.dict(sys.modules, {"qlib": SimpleNamespace(), "qlib.data": fake_qlib_data}):
            result = engine._execute_layer2_simple(["600519.SS", "000858.SZ"])

        self.assertEqual(result, [])

    def test_refresh_pool_does_not_use_example_codes_when_universe_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_pools.db"
            with patch.object(stock_pool, "DB_PATH", db_path):
                stock_pool._init_db()
                conn = stock_pool._get_db()
                conn.execute(
                    "INSERT INTO pools (id, name, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    ("pool2", "空股票池", json.dumps({}), "2026-06-20T00:00:00", "2026-06-20T00:00:00"),
                )
                conn.commit()
                conn.close()

                engine = stock_pool.StockPoolEngine()
                engine._provider = EmptyProvider()
                result = engine.refresh_pool("pool2")

        self.assertEqual(result["constituents"], [])
        self.assertEqual(result["stats"]["input_count"], 0)
        self.assertEqual(result["warning"], "暂无可靠股票范围数据，未生成示例股票池。")

    def test_refresh_pool_uses_all_stocks_without_300_cap(self):
        class LargeProvider:
            def get_index_stocks(self, index: str):
                raise AssertionError("refresh_pool should not request hs300 first")

            def get_all_stocks(self):
                return [
                    {
                        "code": f"sh.{600000 + i:06d}",
                        "code_name": f"测试{i}",
                        "trade_status": "1",
                    }
                    for i in range(350)
                ]

            def get_industry(self, code: str):
                return {"industry": "测试"}

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "stock_pools.db"
            with patch.object(stock_pool, "DB_PATH", db_path):
                stock_pool._init_db()
                conn = stock_pool._get_db()
                conn.execute(
                    "INSERT INTO pools (id, name, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    ("pool3", "全市场股票池", json.dumps({}), "2026-06-20T00:00:00", "2026-06-20T00:00:00"),
                )
                conn.commit()
                conn.close()

                engine = stock_pool.StockPoolEngine()
                engine._provider = LargeProvider()
                with patch.object(engine, "execute_layer2", return_value=[]):
                    result = engine.refresh_pool("pool3")

        self.assertEqual(result["stats"]["input_count"], 350)
        self.assertEqual(result["stats"]["post_layer1"], 350)


if __name__ == "__main__":
    unittest.main()
