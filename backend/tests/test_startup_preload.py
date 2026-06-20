import importlib
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)


class StartupPreloadTests(unittest.TestCase):
    def test_industry_mapping_preload_runs_in_daemon_thread(self):
        main = importlib.import_module("backend.main")
        started = []

        class FakeThread:
            def __init__(self, target, name, daemon):
                self.target = target
                self.name = name
                self.daemon = daemon

            def start(self):
                started.append(self)

        with patch.object(threading, "Thread", FakeThread):
            main._preload_industry_mapping_background()

        self.assertEqual(len(started), 1)
        self.assertEqual(started[0].name, "industry-mapping-preload")
        self.assertTrue(started[0].daemon)


if __name__ == "__main__":
    unittest.main()
