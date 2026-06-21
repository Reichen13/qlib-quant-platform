import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DeployVerificationScriptTests(unittest.TestCase):
    def test_verify_script_checks_frontend_bundle_contains_current_copy(self):
        script = (ROOT / "scripts" / "verify_current_fixes.sh").read_text(encoding="utf-8")

        self.assertIn("Frontend bundle version check", script)
        self.assertIn("去数据管理配置 Key", script)
        self.assertIn("ETF/指数暂按 Qlib 状态代理展示", script)
        self.assertIn("指定股票代码", script)
        self.assertIn("用于提交模型回测", script)
        self.assertIn("用于提交风险分析", script)
        self.assertIn("用于提交组合优化", script)
        self.assertIn("FRONTEND_BUNDLE_COPY_OK", script)

    def test_verify_script_checks_backend_llm_model_params(self):
        script = (ROOT / "scripts" / "verify_current_fixes.sh").read_text(encoding="utf-8")

        self.assertIn("Backend LLM model parameter check", script)
        self.assertIn("/openapi.json", script)
        self.assertIn("quick_model", script)
        self.assertIn("deep_model", script)
        self.assertIn("BACKEND_LLM_MODEL_PARAMS_OK", script)


if __name__ == "__main__":
    unittest.main()
