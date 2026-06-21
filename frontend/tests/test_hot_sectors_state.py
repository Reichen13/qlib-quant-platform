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


if __name__ == "__main__":
    unittest.main()
