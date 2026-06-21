import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DashboardStateTests(unittest.TestCase):
    def test_dashboard_strategy_sliders_use_persisted_app_store_state(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "dashboard" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("dashboardStrategyValues: Record<string, number>", store_source)
        self.assertIn("setDashboardStrategyValue", store_source)
        self.assertIn("dashboardStrategyValues: state.dashboardStrategyValues", store_source)

        self.assertIn("useAppStore", page_source)
        self.assertIn("dashboardStrategyValues", page_source)
        self.assertIn("setDashboardStrategyValue", page_source)
        self.assertNotIn("const [strategies, setStrategies] = useState(strategySliders)", page_source)


if __name__ == "__main__":
    unittest.main()
