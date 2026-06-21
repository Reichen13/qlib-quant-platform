import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LlmRequestModelTests(unittest.TestCase):
    def test_llm_features_send_user_selected_model_names(self):
        source = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")

        self.assertIn('localStorage.getItem("qlib-llm-quick-model")', source)
        self.assertIn('localStorage.getItem("qlib-llm-deep-model")', source)
        self.assertGreaterEqual(source.count("quick_model"), 4)
        self.assertGreaterEqual(source.count("deep_model"), 4)


if __name__ == "__main__":
    unittest.main()
