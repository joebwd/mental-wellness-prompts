import os
import unittest
from unittest import mock
from types import SimpleNamespace

from wellness_cli import memory


class FakeEmbeddingFunction:
    def __init__(self):
        self.tqdm_calls = []
        self.tqdm = self._tqdm

    def _tqdm(self, *args, **kwargs):
        self.tqdm_calls.append(kwargs.copy())
        return {"args": args, "kwargs": kwargs}


class FakeClient:
    def __init__(self, collection=None):
        self.calls = []
        self.collection = collection or FakeCollection()

    def get_or_create_collection(self, **kwargs):
        self.calls.append(kwargs)
        return self.collection


class FakeCollection:
    def __init__(self):
        self.upsert_calls = []

    def upsert(self, **kwargs):
        self.upsert_calls.append(kwargs)


class FakeDB:
    def __init__(self, messages=None, summaries=None):
        self._messages = messages or []
        self._summaries = summaries or []

    def get_all_messages(self):
        return self._messages

    def get_all_summaries(self):
        return self._summaries


class MemoryStoreTests(unittest.TestCase):
    def test_build_quiet_embedding_function_disables_progress(self):
        fake_embedding = FakeEmbeddingFunction()

        with mock.patch.object(memory, "ONNXMiniLM_L6_V2", return_value=fake_embedding) as ctor, \
             mock.patch.object(memory, "hf_disable_progress_bars") as disable:
            old_value = os.environ.pop("HF_HUB_DISABLE_PROGRESS_BARS", None)
            try:
                embedding = memory._build_quiet_embedding_function()
            finally:
                if old_value is not None:
                    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = old_value

        ctor.assert_called_once_with()
        disable.assert_called_once_with()
        embedding.tqdm(desc="download")
        self.assertEqual(fake_embedding.tqdm_calls, [{"desc": "download", "disable": True}])
        self.assertEqual(os.environ["HF_HUB_DISABLE_PROGRESS_BARS"], old_value or "1")

    def test_memory_store_uses_quiet_embedding_function(self):
        fake_client = FakeClient()
        fake_embedding = object()
        fake_db = FakeDB()

        with mock.patch.object(memory.chromadb, "EphemeralClient", return_value=fake_client) as client_ctor, \
             mock.patch.object(memory, "_build_quiet_embedding_function", return_value=fake_embedding) as build_embedding:
            store = memory.MemoryStore(db=fake_db)

        client_ctor.assert_called_once_with()
        build_embedding.assert_called_once_with()
        self.assertIs(store.embedding_function, fake_embedding)
        self.assertEqual(fake_client.calls[0]["embedding_function"], fake_embedding)
        self.assertEqual(fake_client.calls[0]["name"], "wellness_messages")

    def test_memory_store_rebuilds_index_from_db_state(self):
        fake_collection = FakeCollection()
        fake_client = FakeClient(collection=fake_collection)
        fake_db = FakeDB(
            messages=[
                SimpleNamespace(
                    id=1,
                    session_id="session-1",
                    role="user",
                    content="this should be indexed",
                    timestamp="2026-03-21T12:00:00+00:00",
                ),
                SimpleNamespace(
                    id=2,
                    session_id="session-1",
                    role="assistant",
                    content="no",
                    timestamp="2026-03-21T12:01:00+00:00",
                ),
            ],
            summaries=[
                SimpleNamespace(
                    session_id="session-1",
                    summary="summary text",
                    created_at="2026-03-21T12:05:00+00:00",
                )
            ],
        )

        with mock.patch.object(memory.chromadb, "EphemeralClient", return_value=fake_client), \
             mock.patch.object(memory, "_build_quiet_embedding_function", return_value=object()):
            memory.MemoryStore(db=fake_db)

        self.assertEqual(len(fake_collection.upsert_calls), 1)
        call = fake_collection.upsert_calls[0]
        self.assertEqual(call["ids"], ["msg-1", "summary-session-1"])
        self.assertEqual(call["documents"], ["this should be indexed", "summary text"])
        self.assertEqual(
            call["metadatas"],
            [
                {
                    "session_id": "session-1",
                    "role": "user",
                    "timestamp": "2026-03-21T12:00:00+00:00",
                    "message_id": "1",
                },
                {
                    "session_id": "session-1",
                    "role": "summary",
                    "timestamp": "2026-03-21T12:05:00+00:00",
                    "message_id": "0",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
