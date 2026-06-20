import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DlModelsStateTests(unittest.TestCase):
    def test_dl_model_training_state_is_persisted_in_app_store(self):
        store_source = (ROOT / "src" / "stores" / "app-store.ts").read_text(encoding="utf-8")
        page_source = (ROOT / "src" / "pages" / "dl-models" / "index.tsx").read_text(encoding="utf-8")

        self.assertIn("export interface DlModelsParams", store_source)
        self.assertIn("dlModelsParams: DlModelsParams", store_source)
        self.assertIn("setDlModelsParams", store_source)
        self.assertIn("dlModelsParams: state.dlModelsParams", store_source)

        self.assertIn("useAppStore", page_source)
        self.assertIn("dlModelsParams", page_source)
        self.assertIn("setDlModelsParams", page_source)
        self.assertIn("api.dlModels.status", page_source)
        self.assertNotIn("const [training, setTraining] = useState<string | null>(null)", page_source)
        self.assertNotIn("const [trainResult, setTrainResult] = useState<any>(null)", page_source)


if __name__ == "__main__":
    unittest.main()
