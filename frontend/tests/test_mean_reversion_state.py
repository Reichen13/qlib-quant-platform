import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MeanReversionStateTests(unittest.TestCase):
    def test_mean_reversion_parameters_are_persisted_in_app_store(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "mean-reversion" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("export interface MeanReversionParams", store_source)
        self.assertIn("meanReversionParams: MeanReversionParams", store_source)
        self.assertIn("setMeanReversionParams", store_source)
        self.assertIn("meanReversionParams: state.meanReversionParams", store_source)

        self.assertIn("useAppStore", page_source)
        self.assertIn("meanReversionParams", page_source)
        self.assertIn("setMeanReversionParams", page_source)
        self.assertIn("<Tabs value={activeTab} onValueChange=", page_source)
        self.assertNotIn('const [searchQuery, setSearchQuery] = useState("")', page_source)
        self.assertNotIn('const [rsiThreshold, setRsiThreshold] = useState("70")', page_source)
        self.assertNotIn('const [bollingerPeriod, setBollingerPeriod] = useState("20")', page_source)
        self.assertNotIn('const [scanType, setScanType] = useState<"both" | "rsi" | "bollinger">("both")', page_source)


if __name__ == "__main__":
    unittest.main()
