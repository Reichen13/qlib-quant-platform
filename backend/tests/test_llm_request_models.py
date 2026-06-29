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

if "loguru" not in sys.modules:
    logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
    )
    sys.modules["loguru"] = types.SimpleNamespace(logger=logger)


class LlmRequestModelTests(unittest.TestCase):
    def test_ai_strategy_uses_user_selected_model_names(self):
        from backend.api import ai_strategy

        with patch("core.llm_client.create_llm_client", return_value="client") as create_client:
            client = ai_strategy._get_llm_client(
                api_key="user-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                quick_model="qwen-turbo",
                deep_model="qwen-plus",
            )

        self.assertEqual(client, "client")
        create_client.assert_called_once_with(
            api_key="user-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            quick_model="qwen-turbo",
            deep_model="qwen-plus",
        )

    def test_agent_debate_accepts_user_selected_model_query_params(self):
        source = (backend_dir / "api" / "agent_debate.py").read_text(encoding="utf-8")

        self.assertIn("quick_model: Optional[str] = None", source)
        self.assertIn("deep_model: Optional[str] = None", source)
        self.assertIn("quick_model=quick_model", source)
        self.assertIn("deep_model=deep_model", source)
        self.assertIn("AgentAnalyzeRequest", source)
        self.assertIn("request.api_key", source)


if __name__ == "__main__":
    unittest.main()
