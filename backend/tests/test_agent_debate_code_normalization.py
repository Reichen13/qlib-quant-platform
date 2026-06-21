import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.api import agent_debate


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    def get_memory(self, code: str) -> str:
        self.calls.append(code)
        return f"memory:{code}"


class AgentDebateCodeNormalizationTests(unittest.IsolatedAsyncioTestCase):
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
