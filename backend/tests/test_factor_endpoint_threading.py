import unittest
from pathlib import Path


class FactorEndpointThreadingTests(unittest.TestCase):
    def test_heavy_factor_endpoints_are_sync_functions(self):
        source = (Path(__file__).resolve().parents[1] / "api" / "factors.py").read_text(encoding="utf-8")
        heavy_names = [
            "analyze_factors",
            "factor_correlation",
            "factor_quantile_returns",
            "factor_decay",
            "combine_signals",
            "factor_detail",
        ]

        for name in heavy_names:
            with self.subTest(handler=name):
                self.assertIn(f"def {name}", source)
                self.assertNotIn(f"async def {name}", source)


if __name__ == "__main__":
    unittest.main()
