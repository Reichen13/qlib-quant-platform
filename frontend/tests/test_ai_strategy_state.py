import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AiStrategyStateTests(unittest.TestCase):
    def test_ai_strategy_state_is_persisted_in_app_store(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "ai-strategy" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("export interface AiStrategyParams", store_source)
        self.assertIn("aiStrategyParams: AiStrategyParams", store_source)
        self.assertIn("setAiStrategyParams", store_source)
        self.assertIn("aiStrategyParams: state.aiStrategyParams", store_source)

        self.assertIn("useAppStore", page_source)
        self.assertIn("aiStrategyParams", page_source)
        self.assertIn("setAiStrategyParams", page_source)
        self.assertIn("<Tabs value={activeTab} onValueChange=", page_source)
        self.assertNotIn('const [nlInput, setNlInput] = useState("")', page_source)
        self.assertNotIn("const [generated, setGenerated] = useState<any>(null)", page_source)
        self.assertNotIn('const [holdingsInput, setHoldingsInput] = useState("")', page_source)
        self.assertNotIn("const [analysis, setAnalysis] = useState<any>(null)", page_source)
        self.assertNotIn('const [optimizeStrategy, setOptimizeStrategy] = useState("")', page_source)
        self.assertNotIn("const [optimizeResult, setOptimizeResult] = useState<any>(null)", page_source)


if __name__ == "__main__":
    unittest.main()
