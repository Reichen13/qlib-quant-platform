import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NewsAnalysisStateTests(unittest.TestCase):
    def test_news_analysis_uses_persisted_app_store_state(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "news-analysis" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("export interface NewsAnalysisParams", store_source)
        self.assertIn("newsAnalysisParams: NewsAnalysisParams", store_source)
        self.assertIn("setNewsAnalysisParams", store_source)
        self.assertIn("newsAnalysisParams: state.newsAnalysisParams", store_source)

        self.assertIn("useAppStore", page_source)
        self.assertIn("newsAnalysisParams", page_source)
        self.assertNotIn('const [searchCode, setSearchCode] = useState("")', page_source)
        self.assertNotIn('const [activeCode, setActiveCode] = useState("")', page_source)


if __name__ == "__main__":
    unittest.main()
