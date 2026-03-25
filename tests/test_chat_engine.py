import os
import tempfile
import threading
import time
import unittest

from wellness_cli.chat_engine import ChatEngine, FALLBACK_SYSTEM_PROMPT
from wellness_cli.db import WellnessDB
from wellness_cli.safety_supervisor import CRISIS_RESPONSE, STRICT_FALLBACK_RESPONSE


class RecordingMemory:
    def __init__(self, fail_build=False, fail_index=False, fail_store=False):
        self.fail_build = fail_build
        self.fail_index = fail_index
        self.fail_store = fail_store
        self.indexed = []
        self.stored_summaries = []

    def build_memory_context(self, user_message, session_id):
        if self.fail_build:
            raise RuntimeError("memory context unavailable")
        return ""

    def index_message(self, message_id, session_id, role, content, timestamp):
        if self.fail_index:
            raise RuntimeError("index failure")
        self.indexed.append((message_id, session_id, role, content))

    def extract_facts_prompt(self, conversation):
        return "facts"

    def extract_summary_prompt(self, conversation):
        return "summary"

    def store_extracted_facts(self, facts_json, session_id):
        if self.fail_store:
            raise RuntimeError("fact storage failure")

    def store_session_summary(self, summary_json, session_id, mood_start=None, mood_end=None):
        if self.fail_store:
            raise RuntimeError("summary storage failure")
        self.stored_summaries.append((summary_json, session_id, mood_start, mood_end))


class SlowProvider:
    def __init__(self):
        self.cleaned_up = threading.Event()
        self.new_session_calls = 0

    def new_session(self):
        self.new_session_calls += 1

    def stream_response(self, user_text, system_prompt, turn_count):
        try:
            yield (
                "hello there, staying with the safe words for now. "
                "This is still a calm and grounded reply that keeps streaming"
            )
            time.sleep(0.05)
            yield " world"
        finally:
            self.cleaned_up.set()

    def oneshot(self, prompt):
        return None


class FailingProvider:
    def __init__(self):
        self.cleaned_up = threading.Event()

    def new_session(self):
        pass

    def stream_response(self, user_text, system_prompt, turn_count):
        try:
            yield (
                "partial reply that is long enough to stream safely. "
                "This stays grounded long enough for the stream guard to release some text."
            )
            raise RuntimeError("provider failed")
        finally:
            self.cleaned_up.set()

    def oneshot(self, prompt):
        return None


class StaticProvider:
    def __init__(self, response="ack"):
        self.response = response
        self.new_session_calls = 0
        self.system_prompts = []

    def new_session(self):
        self.new_session_calls += 1

    def stream_response(self, user_text, system_prompt, turn_count):
        self.system_prompts.append(system_prompt)
        yield self.response

    def oneshot(self, prompt):
        if prompt == "facts":
            return "[]"
        if prompt == "summary":
            return '{"summary":"brief","topics":[]}'
        return None


class TrackingProvider:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.calls = 0
        self.cleaned_up = threading.Event()
        self.new_session_calls = 0

    def new_session(self):
        self.new_session_calls += 1

    def stream_response(self, user_text, system_prompt, turn_count):
        self.calls += 1
        try:
            for chunk in self.chunks:
                yield chunk
        finally:
            self.cleaned_up.set()

    def oneshot(self, prompt):
        return None


class ChatEngineTests(unittest.TestCase):
    def test_blank_soul_profile_falls_back_to_supportive_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "blank-soul.db")
            db = WellnessDB(path)
            provider = StaticProvider(response="steady")

            class BlankSoul:
                def get_soul_prompt(self):
                    return "   "

                def get_agents_prompt(self):
                    return "   "

            engine = ChatEngine(db=db, memory=RecordingMemory(), provider=provider, soul_profile=BlankSoul())
            engine.start_session("session-1")

            try:
                self.assertEqual(list(engine.send_message("hello")), ["steady"])
                self.assertTrue(provider.system_prompts[0].startswith(FALLBACK_SYSTEM_PROMPT))
                self.assertIn("PYTHON SAFETY SUPERVISOR", provider.system_prompts[0])
            finally:
                db.close()

    def test_broken_soul_profile_falls_back_to_supportive_prompt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "broken-soul.db")
            db = WellnessDB(path)
            provider = StaticProvider(response="steady")

            class BrokenSoul:
                def get_soul_prompt(self):
                    raise RuntimeError("soul unavailable")

                def get_agents_prompt(self):
                    raise RuntimeError("agents unavailable")

            engine = ChatEngine(db=db, memory=RecordingMemory(), provider=provider, soul_profile=BrokenSoul())
            engine.start_session("session-1")

            try:
                self.assertEqual(list(engine.send_message("hello")), ["steady"])
                self.assertTrue(provider.system_prompts[0].startswith(FALLBACK_SYSTEM_PROMPT))
                self.assertIn("PYTHON SAFETY SUPERVISOR", provider.system_prompts[0])
            finally:
                db.close()

    def test_partial_soul_profile_is_used_before_onboarding_is_complete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "partial-soul.db")
            db = WellnessDB(path)
            provider = StaticProvider(response="steady")

            class PartialSoul:
                exists = False

                def get_soul_prompt(self):
                    return "PARTIAL SOUL"

                def get_agents_prompt(self):
                    return "AGENTS"

            engine = ChatEngine(db=db, memory=RecordingMemory(), provider=provider, soul_profile=PartialSoul())
            engine.start_session("session-1")

            try:
                self.assertEqual(list(engine.send_message("hello")), ["steady"])
                self.assertIn("PARTIAL SOUL", provider.system_prompts[0])
                self.assertIn("AGENTS", provider.system_prompts[0])
                self.assertNotIn("A steady, grounded companion.", provider.system_prompts[0])
            finally:
                db.close()

    def test_cancelled_stream_does_not_write_after_db_close(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "cancel.db")
            db = WellnessDB(path)
            provider = SlowProvider()
            engine = ChatEngine(db=db, memory=RecordingMemory(), provider=provider, soul_profile=None)
            engine.start_session("session-1")

            chunks = []
            errors = []
            first_chunk_seen = threading.Event()

            def worker():
                try:
                    for chunk in engine.send_message("Need a minute"):
                        chunks.append(chunk)
                        first_chunk_seen.set()
                except Exception as exc:
                    errors.append(exc)

            thread = threading.Thread(target=worker)
            thread.start()

            self.assertTrue(first_chunk_seen.wait(1))
            engine.cancel_pending_response()
            db.close()
            thread.join(1)

            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertTrue(chunks)
            self.assertTrue("".join(chunks).startswith("hello"))
            self.assertTrue(provider.cleaned_up.wait(1))

            reopened = WellnessDB(path)
            try:
                messages = reopened.get_session_messages("session-1")
                self.assertEqual([(msg.role, msg.content) for msg in messages], [("user", "Need a minute")])
            finally:
                reopened.close()

    def test_provider_failure_keeps_only_user_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "provider-failure.db")
            db = WellnessDB(path)
            provider = FailingProvider()
            engine = ChatEngine(db=db, memory=RecordingMemory(), provider=provider, soul_profile=None)
            engine.start_session("session-1")

            stream = engine.send_message("Rough day")
            self.assertTrue(next(stream).startswith("partial"))
            with self.assertRaisesRegex(RuntimeError, "provider failed"):
                next(stream)

            try:
                messages = db.get_session_messages("session-1")
                self.assertEqual([(msg.role, msg.content) for msg in messages], [("user", "Rough day")])
                self.assertTrue(provider.cleaned_up.is_set())
            finally:
                db.close()

    def test_start_session_separates_conversations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sessions.db")
            db = WellnessDB(path)
            provider = StaticProvider(response="steady")
            engine = ChatEngine(db=db, memory=RecordingMemory(), provider=provider, soul_profile=None)

            engine.start_session("session-1")
            self.assertEqual(list(engine.send_message("First")), ["steady"])

            engine.start_session("session-2")
            self.assertEqual(list(engine.send_message("Second")), ["steady"])

            try:
                session_1 = db.get_session_messages("session-1")
                session_2 = db.get_session_messages("session-2")
                self.assertEqual([(msg.role, msg.content) for msg in session_1], [("user", "First"), ("assistant", "steady")])
                self.assertEqual([(msg.role, msg.content) for msg in session_2], [("user", "Second"), ("assistant", "steady")])
                self.assertEqual(provider.new_session_calls, 2)
            finally:
                db.close()

    def test_memory_failures_do_not_abort_chat(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "memory-failure.db")
            db = WellnessDB(path)
            provider = StaticProvider(response="still here")
            memory = RecordingMemory(fail_build=True, fail_index=True)
            engine = ChatEngine(db=db, memory=memory, provider=provider, soul_profile=None)
            engine.start_session("session-1")

            self.assertEqual(list(engine.send_message("Talk to me")), ["still here"])

            try:
                messages = db.get_session_messages("session-1")
                self.assertEqual([(msg.role, msg.content) for msg in messages], [("user", "Talk to me"), ("assistant", "still here")])
            finally:
                db.close()

    def test_end_session_ignores_memory_storage_failures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "end-session.db")
            db = WellnessDB(path)
            provider = StaticProvider(response="steady")
            memory = RecordingMemory(fail_store=True)
            engine = ChatEngine(db=db, memory=memory, provider=provider, soul_profile=None)
            engine.start_session("session-1")

            engine.messages = [
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
                {"role": "assistant", "content": "four"},
            ]

            try:
                engine.end_session()
            finally:
                db.close()

    def test_end_session_passes_mood_delta_to_summary_storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "summary-mood.db")
            db = WellnessDB(path)
            provider = StaticProvider(response="steady")
            memory = RecordingMemory()
            engine = ChatEngine(db=db, memory=memory, provider=provider, soul_profile=None)
            engine.start_session("session-1")

            engine.messages = [
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
                {"role": "assistant", "content": "four"},
            ]

            try:
                engine.end_session(mood_start=3, mood_end=7)
                self.assertEqual(memory.stored_summaries, [('{"summary":"brief","topics":[]}', "session-1", 3, 7)])
            finally:
                db.close()

    def test_crisis_input_short_circuits_provider_with_local_response(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "crisis.db")
            db = WellnessDB(path)
            provider = TrackingProvider(["this should never stream"])
            engine = ChatEngine(db=db, memory=RecordingMemory(), provider=provider, soul_profile=None)
            engine.start_session("session-1")

            try:
                self.assertEqual(list(engine.send_message("I want to die tonight")), [CRISIS_RESPONSE])
                self.assertEqual(provider.calls, 0)
                self.assertTrue(engine.is_crisis_active)
                messages = db.get_session_messages("session-1")
                self.assertEqual([m.role for m in messages], ["user", "assistant"])
                self.assertTrue(messages[0].crisis_flag)
            finally:
                db.close()

    def test_unsafe_stream_output_is_blocked_and_provider_session_resets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "blocked-output.db")
            db = WellnessDB(path)
            provider = TrackingProvider([
                "I hear that this is a lot to carry right now. ",
                "You only need me for this.",
            ])
            engine = ChatEngine(db=db, memory=RecordingMemory(), provider=provider, soul_profile=None)
            engine.start_session("session-1")

            try:
                response = "".join(engine.send_message("I feel overwhelmed"))
                self.assertNotIn("You only need me", response)
                self.assertIn("I need to keep this practical and safe.", response)
                self.assertTrue(provider.cleaned_up.wait(1))
                self.assertEqual(provider.new_session_calls, 2)
                stored = db.get_session_messages("session-1")[-1].content
                self.assertEqual(stored, response.strip())
            finally:
                db.close()

    def test_crisis_followup_blocks_assessment_language(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "crisis-followup.db")
            db = WellnessDB(path)
            provider = TrackingProvider(["Are you safe right now? Do you have a plan?"])
            engine = ChatEngine(db=db, memory=RecordingMemory(), provider=provider, soul_profile=None)
            engine.start_session("session-1")

            try:
                self.assertEqual(list(engine.send_message("I want to die")), [CRISIS_RESPONSE])
                followup = "".join(engine.send_message("I am still here"))
                self.assertEqual(followup, STRICT_FALLBACK_RESPONSE)
                self.assertTrue(engine.is_crisis_active)
            finally:
                db.close()

    def test_crisis_followup_does_not_leak_partial_stream_before_block(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "crisis-followup-stream.db")
            db = WellnessDB(path)
            provider = TrackingProvider([
                "I'm going to keep this brief and avoid the parts that would check risk or give a ",
                "grounding exercise.",
            ])
            engine = ChatEngine(db=db, memory=RecordingMemory(), provider=provider, soul_profile=None)
            engine.start_session("session-1")

            try:
                self.assertEqual(list(engine.send_message("I want to die")), [CRISIS_RESPONSE])
                chunks = list(engine.send_message("I'm still here"))
                followup = "".join(chunks)
                self.assertEqual(followup, STRICT_FALLBACK_RESPONSE)
                self.assertEqual(chunks, [STRICT_FALLBACK_RESPONSE])
                self.assertNotIn("avoid the parts", followup)
            finally:
                db.close()

    def test_clean_stream_still_reaches_user_and_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "clean-stream.db")
            db = WellnessDB(path)
            provider = TrackingProvider([
                "This reply stays grounded and practical for you right now. ",
                "We can keep it simple.",
            ])
            engine = ChatEngine(db=db, memory=RecordingMemory(), provider=provider, soul_profile=None)
            engine.start_session("session-1")

            try:
                response = "".join(engine.send_message("Talk to me"))
                self.assertEqual(
                    response,
                    "This reply stays grounded and practical for you right now. We can keep it simple.",
                )
                stored = db.get_session_messages("session-1")[-1].content
                self.assertEqual(stored, response)
            finally:
                db.close()

    def test_clean_stream_still_releases_completed_sentences_midstream(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "clean-stream-sentences.db")
            db = WellnessDB(path)
            provider = TrackingProvider([
                "This reply stays grounded and practical for you right now. We can keep it simple and work one step at a time. ",
                "Still here with you.",
            ])
            engine = ChatEngine(db=db, memory=RecordingMemory(), provider=provider, soul_profile=None)
            engine.start_session("session-1")

            try:
                stream = engine.send_message("Talk to me")
                first = next(stream)
                second = next(stream)
                self.assertEqual(first, "This reply stays grounded and practical for you right now. ")
                self.assertEqual(
                    first + second,
                    "This reply stays grounded and practical for you right now. "
                    "We can keep it simple and work one step at a time. Still here with you.",
                )
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
