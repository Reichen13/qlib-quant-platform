import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DataManagementRebuildStaleTests(unittest.TestCase):
    def test_data_management_exposes_stale_repair_update_option(self):
        page_source = (ROOT / "src" / "pages" / "data-management" / "index.tsx").read_text(encoding="utf-8")
        api_source = (ROOT / "src" / "lib" / "api.ts").read_text(encoding="utf-8")

        self.assertIn("repairStale", page_source)
        self.assertIn("rebuildStale", api_source)
        self.assertIn("rebuild_stale", api_source)


if __name__ == "__main__":
    unittest.main()
