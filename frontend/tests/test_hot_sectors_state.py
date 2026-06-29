import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HotSectorsStateTests(unittest.TestCase):
    def test_hot_sectors_uses_persisted_app_store_state(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "hot-sectors" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("export interface HotSectorsParams", store_source)
        self.assertIn("hotSectorsParams: HotSectorsParams", store_source)
        self.assertIn("setHotSectorsParams", store_source)
        self.assertIn("hotSectorsParams: state.hotSectorsParams", store_source)

        self.assertIn("useAppStore", page_source)
        self.assertIn("hotSectorsParams", page_source)
        self.assertNotIn('const [period, setPeriod] = useState("10d")', page_source)
        self.assertNotIn("const [expandedSector, setExpandedSector] = useState<string | null>(null)", page_source)

    def test_hot_sectors_page_uses_hot_api_not_legacy_sector_proxy(self):
        page_source = (ROOT / "src" / "pages" / "hot-sectors" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("api.hot.sectors(period)", page_source)
        self.assertIn("api.hot.sectorStocks(expandedSector!)", page_source)
        self.assertNotIn("api.sectors.performance", page_source)
        self.assertNotIn("api.sectors.stocks", page_source)


if __name__ == "__main__":
    unittest.main()
