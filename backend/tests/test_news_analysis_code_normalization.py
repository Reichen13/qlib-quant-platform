import unittest
import sys
from pathlib import Path
from unittest.mock import patch


backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.api import news_analysis


class FakeFetcher:
    def __init__(self):
        self.calls = []

    def fetch_for_stock(self, code, days=7):
        self.calls.append((code, days))
        return []


class FakeExtractor:
    is_available = False

    def __init__(self):
        self.calls = []

    def extract_events(self, code, news):
        self.calls.append((code, news))
        return []


class NewsAnalysisCodeNormalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_sentiment_accepts_plain_a_share_code(self):
        fetcher = FakeFetcher()
        with patch.object(news_analysis, "get_news_fetcher", return_value=fetcher):
            response = await news_analysis.get_stock_news_sentiment("600519", days=7)

        self.assertEqual(fetcher.calls, [("600519.SS", 7)])
        self.assertEqual(response["code"], "600519.SS")

    async def test_events_accepts_plain_star_market_code(self):
        fetcher = FakeFetcher()
        extractor = FakeExtractor()
        with patch.object(news_analysis, "get_news_fetcher", return_value=fetcher), \
             patch.object(news_analysis, "get_event_extractor", return_value=extractor):
            response = await news_analysis.get_stock_events("688981", days=30)

        self.assertEqual(fetcher.calls, [("688981.SS", 30)])
        self.assertEqual(extractor.calls, [("688981.SS", [])])
        self.assertEqual(response["code"], "688981.SS")


if __name__ == "__main__":
    unittest.main()
