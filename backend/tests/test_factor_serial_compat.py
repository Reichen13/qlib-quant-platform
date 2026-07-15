import unittest
from pathlib import Path
import sys

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.core import compat


class FactorSerialCompatTests(unittest.TestCase):
    def test_force_serial_joblib_is_idempotent(self):
        # 不应抛异常；无 qlib 时静默跳过
        compat.force_serial_joblib(n_jobs=1)
        compat.force_serial_joblib(n_jobs=1)

    def test_factors_module_uses_force_serial(self):
        source = (backend_dir / "api" / "factors.py").read_text(encoding="utf-8")
        self.assertIn("force_serial_joblib", source)
        self.assertIn("_fail_stale_factor_task", source)
        self.assertNotIn("for pct in range(25, 96, 5)", source)
        self.assertIn("progress_cb", source)


if __name__ == "__main__":
    unittest.main()
