import sys
import unittest
from pathlib import Path


backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)


class CodeNormalizationTests(unittest.TestCase):
    def test_plain_a_share_codes_are_normalized_by_leading_digits(self):
        from backend.utils.code_normalization import normalize_stock_code

        self.assertEqual(normalize_stock_code("600519", target="qlib"), "SH600519")
        self.assertEqual(normalize_stock_code("300750", target="qlib"), "SZ300750")
        self.assertEqual(normalize_stock_code("688981", target="qlib"), "SH688981")

    def test_supported_output_formats(self):
        from backend.utils.code_normalization import normalize_stock_code

        self.assertEqual(normalize_stock_code("SH600519", target="yf"), "600519.SS")
        self.assertEqual(normalize_stock_code("300750.SZ", target="baostock"), "sz.300750")
        self.assertEqual(normalize_stock_code("sh.688981", target="api"), "SH688981")

    def test_rejects_unknown_code_shape(self):
        from backend.utils.code_normalization import normalize_stock_code

        with self.assertRaises(ValueError):
            normalize_stock_code("ABC123", target="qlib")


if __name__ == "__main__":
    unittest.main()
