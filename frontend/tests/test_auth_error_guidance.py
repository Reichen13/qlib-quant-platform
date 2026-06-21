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
        self.assertIn("请在本页填写服务器管理 Key", source)

    def test_risk_page_can_save_admin_key_without_leaving_page(self):
        source = (ROOT / "src" / "pages" / "risk" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn('localStorage.getItem("qlib-admin-api-key")', source)
        self.assertIn('localStorage.setItem("qlib-admin-api-key"', source)
        self.assertIn("请输入服务器 API_KEY", source)
        self.assertIn("请在本页填写服务器管理 Key", source)

    def test_portfolio_page_can_save_admin_key_without_leaving_page(self):
        source = (ROOT / "src" / "pages" / "portfolio" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn('localStorage.getItem("qlib-admin-api-key")', source)
        self.assertIn('localStorage.setItem("qlib-admin-api-key"', source)
        self.assertIn("请输入服务器 API_KEY", source)
        self.assertIn("请在本页填写服务器管理 Key", source)

    def test_backtest_page_guides_user_to_configure_admin_key(self):
        source = (ROOT / "src" / "pages" / "backtest" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("isAuthError", source)
        self.assertIn("服务器管理 Key", source)
        self.assertIn("请在本页填写服务器管理 Key", source)
        self.assertIn("返回修改参数", source)

    def test_backtest_page_can_save_admin_key_without_leaving_page(self):
        source = (ROOT / "src" / "pages" / "backtest" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn('localStorage.getItem("qlib-admin-api-key")', source)
        self.assertIn('localStorage.setItem("qlib-admin-api-key"', source)
        self.assertIn("请输入服务器 API_KEY", source)

    def test_backtest_auth_failure_can_retry_from_results_card(self):
        source = (ROOT / "src" / "pages" / "backtest" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn('data-testid="backtest-auth-retry-key"', source)
        self.assertIn("保存 Key 并重试", source)
        self.assertIn("onClick={runBacktest}", source)


if __name__ == "__main__":
    unittest.main()
