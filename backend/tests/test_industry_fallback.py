import sys
import types
import unittest
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.api import industry


class IndustryFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_industries_falls_back_when_akshare_disconnects(self):
        fake_akshare = types.ModuleType("akshare")

        def raise_disconnect():
            raise ConnectionError("remote disconnected")

        fake_akshare.stock_board_industry_name_em = raise_disconnect
        original_akshare = sys.modules.get("akshare")
        sys.modules["akshare"] = fake_akshare
        try:
            result = await industry.list_industries()
        finally:
            if original_akshare is None:
                sys.modules.pop("akshare", None)
            else:
                sys.modules["akshare"] = original_akshare

        self.assertGreater(result["total"], 0)
        self.assertEqual(result["data_status"], "fallback")
        self.assertEqual(result["source"], "local_sector_definitions")
        self.assertIn("industries", result)
        self.assertIn("warning", result)


if __name__ == "__main__":
    unittest.main()
