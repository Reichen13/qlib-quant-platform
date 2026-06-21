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
        self.assertIn("FRONTEND_BUNDLE_COPY_OK", script)


if __name__ == "__main__":
    unittest.main()
