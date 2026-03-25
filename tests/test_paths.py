import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wellness_cli.paths import (
    get_home_dir,
    load_startup_preferences,
    load_storage_choice,
    reset_all_storage_state,
    save_startup_preferences,
    save_storage_choice,
    storage_has_state,
)


class StorageChoiceTests(unittest.TestCase):
    def test_bootstrap_choice_sets_home_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bootstrap = os.path.join(tmpdir, "bootstrap.json")
            local_home = os.path.join(tmpdir, "local-store")
            with patch.dict(
                os.environ,
                {
                    "MOSS_BOOTSTRAP_CONFIG": bootstrap,
                    "MOSS_LOCAL_HOME_DIR": os.path.join(tmpdir, "unused-local-default"),
                    "MOSS_ICLOUD_HOME_DIR": os.path.join(tmpdir, "unused-icloud-default"),
                },
                clear=False,
            ):
                save_storage_choice(local_home, kind="local")

                choice = load_storage_choice()
                self.assertIsNotNone(choice)
                self.assertEqual(choice["kind"], "local")
                self.assertEqual(choice["home_dir"], local_home)
                self.assertEqual(get_home_dir(), local_home)

    def test_home_override_beats_bootstrap_choice(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bootstrap = os.path.join(tmpdir, "bootstrap.json")
            chosen_home = os.path.join(tmpdir, "chosen-home")
            override_home = os.path.join(tmpdir, "override-home")
            with patch.dict(
                os.environ,
                {
                    "MOSS_BOOTSTRAP_CONFIG": bootstrap,
                    "MOSS_LOCAL_HOME_DIR": os.path.join(tmpdir, "unused-local-default"),
                    "MOSS_ICLOUD_HOME_DIR": os.path.join(tmpdir, "unused-icloud-default"),
                },
                clear=False,
            ):
                save_storage_choice(chosen_home, kind="local")
                with patch.dict(os.environ, {"MOSS_HOME_DIR": override_home}, clear=False):
                    self.assertEqual(get_home_dir(), override_home)

    def test_startup_preferences_share_bootstrap_file_with_storage_choice(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bootstrap = os.path.join(tmpdir, "bootstrap.json")
            local_home = os.path.join(tmpdir, "local-store")
            with patch.dict(
                os.environ,
                {
                    "MOSS_BOOTSTRAP_CONFIG": bootstrap,
                    "MOSS_LOCAL_HOME_DIR": os.path.join(tmpdir, "unused-local-default"),
                    "MOSS_ICLOUD_HOME_DIR": os.path.join(tmpdir, "unused-icloud-default"),
                },
                clear=False,
            ):
                save_storage_choice(local_home, kind="local")
                save_startup_preferences(
                    provider="codex",
                    model="gpt-5.4",
                    pangoclaw_mode="off",
                )

                choice = load_storage_choice()
                prefs = load_startup_preferences()

                self.assertEqual(choice["home_dir"], local_home)
                self.assertEqual(prefs["provider"], "codex")
                self.assertEqual(prefs["model"], "gpt-5.4")
                self.assertEqual(prefs["pangoclaw_mode"], "off")

    def test_storage_has_state_detects_registry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertFalse(storage_has_state(tmpdir))
            Path(tmpdir, "users.json").write_text("[]\n", encoding="utf-8")
            self.assertTrue(storage_has_state(tmpdir))

    def test_reset_all_storage_state_clears_known_locations_and_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bootstrap = os.path.join(tmpdir, "bootstrap.json")
            local_home = os.path.join(tmpdir, "local-store")
            icloud_home = os.path.join(tmpdir, "icloud-store")
            with patch.dict(
                os.environ,
                {
                    "MOSS_BOOTSTRAP_CONFIG": bootstrap,
                    "MOSS_LOCAL_HOME_DIR": local_home,
                    "MOSS_ICLOUD_HOME_DIR": icloud_home,
                },
                clear=False,
            ):
                Path(local_home).mkdir(parents=True, exist_ok=True)
                Path(local_home, "users.json").write_text("[]\n", encoding="utf-8")
                Path(icloud_home).mkdir(parents=True, exist_ok=True)
                Path(icloud_home, "users.json").write_text("[]\n", encoding="utf-8")
                save_storage_choice(icloud_home, kind="icloud")

                reset_all_storage_state()

                self.assertFalse(os.path.exists(local_home))
                self.assertFalse(os.path.exists(icloud_home))
                self.assertFalse(os.path.exists(bootstrap))


if __name__ == "__main__":
    unittest.main()
