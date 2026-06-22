import ast
import sys
import unittest
from pathlib import Path


backend_dir = Path(__file__).resolve().parents[1]
project_root = backend_dir.parent
for path in (str(project_root), str(backend_dir)):
    if path not in sys.path:
        sys.path.insert(0, path)


class BacktestAuthBoundaryTests(unittest.TestCase):
    def test_backtest_router_is_user_feature_and_does_not_require_global_api_key(self):
        source = (backend_dir / "api" / "backtest.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        router_assignments = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "router" for target in node.targets)
        ]
        self.assertEqual(len(router_assignments), 1)

        call = router_assignments[0].value
        self.assertIsInstance(call, ast.Call)
        keyword_names = {keyword.arg for keyword in call.keywords}
        self.assertNotIn("dependencies", keyword_names)


if __name__ == "__main__":
    unittest.main()
