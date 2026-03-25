import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from wellness_cli.db import Message, WellnessDB
from wellness_cli.vault import DEFAULT_IDENTITY_ID, IdentityManager, InvalidPassphraseError, VaultManager


class VaultManagerTests(unittest.TestCase):
    def test_create_and_unlock_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"MOSS_HOME_DIR": tmpdir}, clear=False):
                vault = VaultManager()
                session = vault.create("secret-passphrase")

                db = WellnessDB()
                db.save_message(
                    Message(
                        id=None,
                        session_id="session-1",
                        role="user",
                        content="hello there",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                )
                db.close()
                vault.lock(session)

                self.assertTrue(vault.has_vault())
                self.assertTrue(os.path.exists(vault.data_path))

                unlocked = vault.unlock("secret-passphrase")
                reopened = WellnessDB()
                try:
                    messages = reopened.get_all_messages()
                    self.assertEqual(len(messages), 1)
                    self.assertEqual(messages[0].content, "hello there")
                finally:
                    reopened.close()
                    vault.lock(unlocked)

    def test_wrong_passphrase_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"MOSS_HOME_DIR": tmpdir}, clear=False):
                vault = VaultManager()
                session = vault.create("correct horse battery staple")
                db = WellnessDB()
                db.close()
                vault.lock(session)

                with self.assertRaises(InvalidPassphraseError):
                    vault.unlock("wrong passphrase")

    def test_legacy_plaintext_db_is_migrated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"MOSS_HOME_DIR": tmpdir}, clear=False):
                legacy_db_path = os.path.join(tmpdir, "wellness.db")
                legacy_db = WellnessDB(db_path=legacy_db_path)
                legacy_db.save_message(
                    Message(
                        id=None,
                        session_id="session-legacy",
                        role="user",
                        content="legacy message",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                )
                legacy_db.close()

                vault = VaultManager()
                session = vault.create("migrate-me", migrate_legacy=True)

                self.assertFalse(os.path.exists(legacy_db_path))

                migrated = WellnessDB()
                try:
                    messages = migrated.get_all_messages()
                    self.assertEqual(len(messages), 1)
                    self.assertEqual(messages[0].content, "legacy message")
                finally:
                    migrated.close()
                    vault.lock(session)


class IdentityManagerTests(unittest.TestCase):
    def test_creates_distinct_identity_ids(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = IdentityManager(app_home=tmpdir)
            first = manager.create_identity("Joe")
            second = manager.create_identity("Joe")

            self.assertEqual(first.id, "joe")
            self.assertEqual(second.id, "joe-2")
            self.assertEqual(len(manager.list_identities()), 2)

    def test_migrates_legacy_root_vault_into_default_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root_vault = VaultManager(home_dir=tmpdir)
            session = root_vault.create("secret")
            db = WellnessDB(db_path=session.db_path)
            db.save_message(
                Message(
                    id=None,
                    session_id="session-1",
                    role="user",
                    content="root vault data",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )
            db.close()
            root_vault.lock(session)

            manager = IdentityManager(app_home=tmpdir)
            identities = manager.list_identities()

            self.assertEqual(len(identities), 1)
            self.assertEqual(identities[0].id, DEFAULT_IDENTITY_ID)
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "vault.json")))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "users", DEFAULT_IDENTITY_ID, "vault.json")))


if __name__ == "__main__":
    unittest.main()
