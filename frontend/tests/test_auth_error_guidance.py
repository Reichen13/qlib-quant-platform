import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AuthErrorGuidanceTests(unittest.TestCase):
    def test_api_client_parses_json_detail_errors(self):
        source = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("parseErrorMessage", source)
        self.assertIn("detail", source)
        self.assertIn("服务器管理 Key", source)

    def test_risk_page_guides_user_to_configure_admin_key(self):
        source = (ROOT / "src" / "pages" / "risk" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("isAuthError", source)
        self.assertIn("服务器管理 Key", source)
        self.assertIn("数据管理", source)

    def test_backtest_page_guides_user_to_configure_admin_key(self):
        source = (ROOT / "src" / "pages" / "backtest" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("isAuthError", source)
        self.assertIn("服务器管理 Key", source)
        self.assertIn("数据管理", source)
        self.assertIn("返回修改参数", source)


if __name__ == "__main__":
    unittest.main()
