import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AgentDebateLlmRequestTests(unittest.TestCase):
    def test_agent_debate_does_not_put_llm_key_in_url_query(self):
        api_source = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")
        match = re.search(r"agent:\s*\{(?P<body>[\s\S]*?)\n\s*\},\n\n\s*// 深度学习模型", api_source)
        self.assertIsNotNone(match)
        agent_api = match.group("body")

        self.assertIn("body: JSON.stringify", agent_api)
        self.assertNotIn('params.append("api_key"', agent_api)
        self.assertNotIn('params.append("base_url"', agent_api)
        self.assertNotIn('params.append("quick_model"', agent_api)
        self.assertNotIn('params.append("deep_model"', agent_api)


if __name__ == "__main__":
    unittest.main()
