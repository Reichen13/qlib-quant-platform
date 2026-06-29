import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks
from fastapi import HTTPException


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
        exception=lambda *args, **kwargs: None,
    )
    sys.modules["loguru"] = types.SimpleNamespace(logger=logger)

from backend.api import agent_debate


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    def get_memory(self, code: str) -> str:
        self.calls.append(code)
        return f"memory:{code}"


class AgentDebateCodeNormalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_analyze_rejects_invalid_code_before_llm_check(self):
        with patch.object(agent_debate, "_check_llm", side_effect=AssertionError("LLM check should not run")):
            with self.assertRaises(HTTPException) as ctx:
                await agent_debate.analyze_stock(BackgroundTasks(), code="not-a-code")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("\u80a1\u7968\u4ee3\u7801\u683c\u5f0f\u4e0d\u652f\u6301", ctx.exception.detail)

    async def test_analyze_accepts_plain_star_market_code(self):
        fake_report_store = types.SimpleNamespace(save_report=lambda *args, **kwargs: None)
        background_tasks = BackgroundTasks()

        with patch.object(agent_debate, "_check_llm", return_value=None), \
             patch.dict(sys.modules, {"db.report_store": fake_report_store}):
            response = await agent_debate.analyze_stock(background_tasks, code="688981")

        self.assertEqual(response["code"], "688981.SS")
        self.assertEqual(response["status"], "running")

    async def test_memory_accepts_prefixed_a_share_code(self):
        orch = FakeOrchestrator()
        fake_module = types.SimpleNamespace(get_orchestrator=lambda: orch)

        with patch.dict(sys.modules, {"core.multi_agent": fake_module}):
            response = await agent_debate.get_memory("SH600519")

        self.assertEqual(orch.calls, ["600519.SS"])
        self.assertEqual(response["code"], "600519.SS")
        self.assertEqual(response["memory"], "memory:600519.SS")

    async def test_memory_accepts_plain_star_market_code(self):
        orch = FakeOrchestrator()
        fake_module = types.SimpleNamespace(get_orchestrator=lambda: orch)

        with patch.dict(sys.modules, {"core.multi_agent": fake_module}):
            response = await agent_debate.get_memory("688981")

        self.assertEqual(orch.calls, ["688981.SS"])
        self.assertEqual(response["code"], "688981.SS")


if __name__ == "__main__":
    unittest.main()
