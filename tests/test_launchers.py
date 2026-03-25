from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent


class LauncherTests(unittest.TestCase):
    def test_moss_launcher_checks_imports_and_runs_module(self):
        content = (ROOT / "moss").read_text()

        self.assertIn("HF_HUB_DISABLE_PROGRESS_BARS=1", content)
        self.assertIn('importlib.import_module(name)', content)
        self.assertIn('python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" >/dev/null 2>&1', content)
        self.assertIn('python3 -m wellness_cli "$@"', content)

    def test_only_moss_launcher_exists(self):
        self.assertFalse((ROOT / "mosschat").exists())
        self.assertFalse((ROOT / "chat").exists())


if __name__ == "__main__":
    unittest.main()
