import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone

from wellness_cli.db import Message, WellnessDB


class WellnessDBTests(unittest.TestCase):
    def _message(self, session_id="session-1", content="Been nervous as hell"):
        return Message(
            id=None,
            session_id=session_id,
            role="user",
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def test_connection_allows_cross_thread_message_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "threaded.db")
            db = WellnessDB(path)
            errors = []

            def worker():
                try:
                    db.save_message(self._message())
                except Exception as exc:  # pragma: no cover - regression capture
                    errors.append(exc)

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()

            try:
                self.assertEqual(errors, [])
                messages = db.get_session_messages("session-1")
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0].content, "Been nervous as hell")
            finally:
                db.close()

    def test_accepts_in_memory_and_relative_paths(self):
        memory_db = WellnessDB(":memory:")
        try:
            memory_db.save_message(self._message(content="In memory"))
            self.assertEqual(memory_db.get_stats()["total_messages"], 1)
        finally:
            memory_db.close()

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                relative_db = WellnessDB("local.db")
                try:
                    relative_db.save_message(self._message(content="Relative path"))
                finally:
                    relative_db.close()
                self.assertTrue(os.path.exists("local.db"))
            finally:
                os.chdir(old_cwd)

    def test_persists_messages_after_reopen(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "persisted.db")
            db = WellnessDB(path)
            try:
                db.save_message(self._message(content="First session"))
            finally:
                db.close()

            reopened = WellnessDB(path)
            try:
                messages = reopened.get_session_messages("session-1")
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0].content, "First session")
                self.assertEqual(reopened.get_stats()["total_messages"], 1)
            finally:
                reopened.close()

    def test_get_all_session_ids_preserves_insertion_order(self):
        memory_db = WellnessDB(":memory:")
        try:
            memory_db.save_message(self._message(session_id="session-a", content="first"))
            memory_db.save_message(self._message(session_id="session-b", content="second"))
            memory_db.save_message(self._message(session_id="session-a", content="third"))
            self.assertEqual(memory_db.get_all_session_ids(), ["session-a", "session-b"])
        finally:
            memory_db.close()


if __name__ == "__main__":
    unittest.main()
