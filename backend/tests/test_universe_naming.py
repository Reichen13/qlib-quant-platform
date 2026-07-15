import sys
import tempfile
import unittest
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

from core.universe import (  # noqa: E402
    DEFAULT_UNIVERSE,
    resolve_universe,
    universe_label,
    ensure_core650_instruments,
)


class UniverseNamingTests(unittest.TestCase):
    def test_default_is_core650(self):
        self.assertEqual(DEFAULT_UNIVERSE, "core650")

    def test_legacy_csi300_maps_to_core650(self):
        self.assertEqual(resolve_universe("csi300"), "core650")
        self.assertEqual(resolve_universe("CSI300"), "core650")

    def test_label_does_not_say_official_csi300(self):
        label = universe_label("core650")
        self.assertIn("核心研究池", label)
        self.assertNotIn("沪深300", label)

    def test_legacy_label_still_not_official_name(self):
        label = universe_label("csi300")
        self.assertIn("核心研究池", label)

    def test_ensure_copies_from_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inst = root / "instruments"
            inst.mkdir(parents=True)
            (inst / "csi300.txt").write_text("SH600519\t2020-01-01\t2026-07-08\n", encoding="utf-8")
            path = ensure_core650_instruments(root)
            self.assertIsNotNone(path)
            self.assertTrue((inst / "core650.txt").exists())
            self.assertIn("SH600519", (inst / "core650.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
