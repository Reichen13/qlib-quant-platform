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

    def test_generated_strategy_can_be_applied_to_backtest_params(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "ai-strategy" / "index.tsx").read_text(encoding="utf-8")
        mapper_path = ROOT / "src" / "lib" / "ai-strategy-backtest.ts"
        self.assertTrue(mapper_path.exists(), "AI策略生成结果需要有独立映射函数供模型回测复用")
        mapper_source = mapper_path.read_text(encoding="utf-8")

        self.assertIn("mapAiStrategyParamsToBacktestParams", mapper_source)
        self.assertIn("hold_num", mapper_source)
        self.assertIn("topK", mapper_source)
        self.assertIn("turnover", mapper_source)
        self.assertIn("rebalance", mapper_source)
        self.assertIn("max_position", mapper_source)
        self.assertIn("singlePosition", mapper_source)

        self.assertIn("setBacktestParams", store_source)
        self.assertIn("setBacktestActiveTab", store_source)

        self.assertIn("mapAiStrategyParamsToBacktestParams", page_source)
        self.assertIn("handleApplyGeneratedToBacktest", page_source)
        self.assertIn("setBacktestParams", page_source)
        self.assertIn('navigate("/backtest")', page_source)
        self.assertIn("用此策略跑回测", page_source)

    def test_ai_strategy_page_surfaces_linked_backtest_result(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "ai-strategy" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("backtestDraft", store_source)
        self.assertIn("backtestResult", page_source)
        self.assertIn("最近回测验证", page_source)
        self.assertIn("total_return", page_source)
        self.assertIn("max_drawdown", page_source)
        self.assertIn("sharpe_ratio", page_source)

    def test_screening_workflow_receives_generated_ai_strategy_context(self):
        page_source = (ROOT / "src" / "pages" / "screening-workflow" / "index.tsx").read_text(encoding="utf-8")
        api_source = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("aiStrategyParams.backtestDraft", page_source)
        self.assertIn("generated_strategy", page_source)
        self.assertIn("已纳入AI生成策略", page_source)
        self.assertIn("generated_strategy?:", api_source)

    def test_generated_strategy_can_be_saved_as_local_template(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "ai-strategy" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("savedTemplates", store_source)
        self.assertIn("handleSaveGeneratedAsTemplate", page_source)
        self.assertIn("保存到策略模板", page_source)
        self.assertIn("local-generated", page_source)

    def test_optimized_candidate_can_be_applied_to_backtest_params(self):
        page_source = (ROOT / "src" / "pages" / "ai-strategy" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("handleApplyOptimizedToBacktest", page_source)
        self.assertIn("用此参数跑回测", page_source)
        self.assertIn("optimizeResult.candidates.map", page_source)


if __name__ == "__main__":
    unittest.main()
