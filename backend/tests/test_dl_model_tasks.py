import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)

if "loguru" not in sys.modules:
    logger = types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        debug=lambda *args, **kwargs: None,
    )
    sys.modules["loguru"] = types.SimpleNamespace(logger=logger)

from backend.core import dl_models
from backend.db.task_store import TaskStore


class DLModelTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.store = TaskStore(Path(self.tmp_dir.name) / "dl_training_tasks.db", table_name="dl_training_tasks_test")
        self.store.init_db()
        self.store_patch = patch.object(dl_models, "dl_training_task_store", self.store, create=True)
        self.model_base_patch = patch.object(dl_models, "MODEL_BASE", Path(self.tmp_dir.name) / "dl_models")
        self.store_patch.start()
        self.model_base_patch.start()
        dl_models._training_tasks.clear()

    def tearDown(self):
        dl_models._training_tasks.clear()
        self.model_base_patch.stop()
        self.store_patch.stop()
        self.tmp_dir.cleanup()

    def test_start_training_persists_initial_status(self):
        fake_thread = Mock()

        with patch.object(dl_models.threading, "Thread", return_value=fake_thread):
            task_id = dl_models.start_training("alstm", {"n_epochs": 3})

        persisted = self.store.get_task(task_id)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted["status"], "running")
        self.assertGreaterEqual(persisted["progress"], 0)
        payload = json.loads(persisted["result_json"])
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["model"], "alstm")
        self.assertEqual(payload["config"]["n_epochs"], 3)
        fake_thread.start.assert_called_once()

    def test_get_training_status_returns_persisted_task_when_memory_is_empty(self):
        payload = {
            "status": "running",
            "model": "alstm",
            "config": {"n_epochs": 5},
            "started_at": "2026-06-20T10:00:00",
            "progress": 0.35,
            "message": "training",
        }
        self.store.create_task("task-1", json.dumps({"model": "alstm"}, ensure_ascii=False))
        self.store.set_running("task-1", 35, json.dumps(payload, ensure_ascii=False))
        dl_models._training_tasks.clear()

        status = dl_models.get_training_status("task-1")

        self.assertIsNotNone(status)
        self.assertEqual(status["status"], "running")
        self.assertEqual(status["model"], "alstm")
        self.assertEqual(status["progress"], 0.35)
        self.assertEqual(status["message"], "training")

    def test_missing_training_status_returns_none(self):
        self.assertIsNone(dl_models.get_training_status("not-found"))


if __name__ == "__main__":
    unittest.main()
