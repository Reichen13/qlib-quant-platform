import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AgentDebateStateTests(unittest.TestCase):
    def test_agent_debate_task_state_is_persisted_in_app_store(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "agent-debate" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("export interface AgentDebateParams", store_source)
        self.assertIn("agentDebateParams: AgentDebateParams", store_source)
        self.assertIn("setAgentDebateParams", store_source)
        self.assertIn("agentDebateParams: state.agentDebateParams", store_source)

        self.assertIn("useAppStore", page_source)
        self.assertIn("agentDebateParams", page_source)
        self.assertIn("agentDebateTaskId", page_source)
        self.assertIn("errorMessage", store_source)
        self.assertIn("errorMessage", page_source)
        self.assertIn("r.error", page_source)
        self.assertIn('status === "error" || status === "failed"', page_source)
        self.assertIn("setAgentDebateParams", page_source)
        self.assertNotIn("const [, setTaskId]", page_source)
        self.assertNotIn('const [status, setStatus] = useState<string>("idle")', page_source)
        self.assertNotIn("const [report, setReport] = useState<any>(null)", page_source)


if __name__ == "__main__":
    unittest.main()
