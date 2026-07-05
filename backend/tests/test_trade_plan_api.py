import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import trade_plan


class TradePlanApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(trade_plan.router, prefix="/api/trade-plan")
        self.client = TestClient(app)

    def test_turtle_route_builds_plan_from_supplied_entry_and_atr(self):
        response = self.client.post("/api/trade-plan/turtle", json={
            "account_equity": 100000,
            "risk_percent": 0.01,
            "candidates": [{
                "code": "600519",
                "name": "贵州茅台",
                "entry_price": 100,
                "atr": 2,
                "target_price": 112,
            }],
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["plans"][0]["code"], "SH600519")
        self.assertEqual(data["plans"][0]["unit_shares"], 200)
        self.assertEqual(data["plans"][0]["verdict"], "可执行")

    def test_turtle_route_derives_entry_and_atr_from_quote_data(self):
        fake_quote = {
            "code": "SZ000001",
            "name": "平安银行",
            "data": [
                {"high": 10.5, "low": 9.5, "close": 10.0},
                {"high": 11.0, "low": 10.0, "close": 10.5},
                {"high": 11.5, "low": 10.5, "close": 11.0},
                {"high": 12.0, "low": 11.0, "close": 11.5},
                {"high": 12.5, "low": 11.5, "close": 12.0},
            ],
        }

        async def fake_get_quote(*args, **kwargs):
            return fake_quote

        with patch.object(trade_plan, "get_quote", fake_get_quote):
            response = self.client.post("/api/trade-plan/turtle", json={
                "account_equity": 100000,
                "risk_percent": 0.01,
                "candidates": [{"code": "000001", "target_price": 15}],
            })

        self.assertEqual(response.status_code, 200)
        plan = response.json()["plans"][0]
        self.assertEqual(plan["code"], "SZ000001")
        self.assertEqual(plan["entry_price"], 12.0)
        self.assertGreater(plan["atr"], 0)
        self.assertEqual(plan["data_status"], "derived")


if __name__ == "__main__":
    unittest.main()
