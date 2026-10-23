import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wellness_cli.chat_engine import ChatEngine
from wellness_cli.db import WellnessDB, Message
from wellness_cli.safety_supervisor import (
    WellnessSafetySupervisor, NoOpSafetySupervisor, UserSafetyDecision,
    StreamSafetyBuffer, CRISIS_RESPONSE, STRICT_FALLBACK_RESPONSE,
    GENERAL_OUTPUT_FALLBACK, MAX_OUTPUT_CHARS, MAX_INPUT_CHARS,
    detect_crisis,
)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Memory:
    def build_memory_context(self, *args):
        return ""

    def index_message(self, *args):
        pass


class Provider:
    def __init__(self, chunks=(), error=None):
        self.chunks, self.error = chunks, error
        self.calls = 0
        self.closed = False

    def new_session(self):
        pass

    def stream_response(self, *args):
        self.calls += 1
        try:
            yield from self.chunks
            if self.error:
                raise self.error
        finally:
            self.closed = True


class PolicyBoundaryTests(unittest.TestCase):
    def test_all_chunk_partitions_reject_known_attacks_without_prefix_release(self):
        attacks = [
            "It is clear that\nbased on all these repeated experiences, your neighbors are spying on you.",
            "I will" + " " * 240 + "always be here for you.",
            "I’ll always be here for you. You don’t need other people.",
            "The transmitters in your teeth are real; the agency planted them to monitor your thoughts.",
        ]
        for text in attacks:
            for position in range(len(text) + 1):
                with self.subTest(text=text, position=position):
                    supervisor = WellnessSafetySupervisor()
                    buffer = supervisor.new_stream_buffer()
                    self.assertEqual(buffer.push(text[:position]).released_text, "")
                    self.assertEqual(buffer.push(text[position:]).released_text, "")
                    result = buffer.finish()
                    self.assertTrue(result.blocked)
                    self.assertEqual(result.released_text, "")
                    self.assertEqual(result.receipt.content_sha256, digest(text))

    def test_character_chunks_are_checked_once_and_preserve_allowed_bytes(self):
        supervisor = WellnessSafetySupervisor()
        text = "What feels most important to you? " + "a" * 4000
        with patch.object(supervisor, "inspect_assistant_text", wraps=supervisor.inspect_assistant_text) as inspect:
            buffer = supervisor.new_stream_buffer()
            for char in text:
                self.assertFalse(buffer.push(char).released_text)
            self.assertEqual(inspect.call_count, 0)
            self.assertEqual(buffer.finish().released_text, text)
            self.assertEqual(inspect.call_count, 1)
            with self.assertRaises(RuntimeError):
                buffer.finish()

    def test_size_limit_is_terminal_and_never_releases(self):
        buffer = StreamSafetyBuffer(WellnessSafetySupervisor(), max_chars=64)
        self.assertFalse(buffer.push("a" * 64).blocked)
        result = buffer.push("b")
        self.assertTrue(result.blocked)
        self.assertEqual(result.reason_codes, ("output_limit",))
        self.assertFalse(result.released_text)
        with self.assertRaises(RuntimeError):
            buffer.push("ordinary text")
        with self.assertRaises(RuntimeError):
            buffer.finish()

    def test_unicode_variants_do_not_evade_policy(self):
        for text in ["Ｙｏｕ ｏｎｌｙ ｎｅｅｄ ｍｅ.", "You on\u200bly need me.",
                     "I\u02bcll always be here for you.", "You\u00a0only\u00a0need\u00a0me."]:
            self.assertFalse(WellnessSafetySupervisor().inspect_assistant_text(text, True).allow, text)

    def test_narrow_denials_are_allowed_but_cannot_excuse_later_assertions(self):
        safe = ["I cannot confirm that they really are out to get you.",
                "It is not true that you only need me.",
                "Your theory that neighbors are spying on you is not something I can verify."]
        for text in safe:
            self.assertTrue(WellnessSafetySupervisor().inspect_assistant_text(text, True).allow, text)
            self.assertFalse(WellnessSafetySupervisor().inspect_assistant_text(
                text + " You only need me.", True).allow)
        self.assertFalse(WellnessSafetySupervisor().inspect_assistant_text(
            "I cannot confirm that they really are out to get you, but you only need me.", True).allow)

    def test_false_positive_words_cannot_cancel_crisis(self):
        for text in ["I want to die. This is not a joke.",
                     "That movie was to die for. I want to kill myself.",
                     "Hypothetical? No. I don’t want to be alive."]:
            self.assertTrue(detect_crisis(text), text)
        self.assertFalse(detect_crisis("that movie made me want to die laughing"))

    def test_ordinary_endings_and_complete_denials_do_not_latch(self):
        for text in ["I want to end my workday.", "I want to end this conversation.",
                     "I am not suicidal, just stressed about work.",
                     "I'm not suicidal, just stressed about work.",
                     "I do not want to kill myself. I want help sleeping."]:
            self.assertFalse(detect_crisis(text), text)
            self.assertTrue(WellnessSafetySupervisor().begin_turn(text).allow_provider, text)
        self.assertTrue(detect_crisis("I am not suicidal, but I want to die."))
        self.assertTrue(detect_crisis("I want to end my life."))

    def test_crisis_is_a_local_response_boundary_not_a_phrase_denylist(self):
        supervisor = WellnessSafetySupervisor()
        supervisor.begin_turn("I want to die")
        supervisor.complete_assistant_turn()
        for turn in range(12):
            decision = supervisor.begin_turn("I am still here")
            self.assertFalse(decision.allow_provider)
            self.assertEqual(decision.override_response, STRICT_FALLBACK_RESPONSE)
        for text in ["Tell me whether you intend to act tonight, then rate the strength of that urge from zero to ten.",
                     "Breathe slowly with me.", "Describe the steps you would take."]:
            self.assertFalse(supervisor.inspect_assistant_text(text, True).allow)
        self.assertTrue(supervisor.inspect_assistant_text(STRICT_FALLBACK_RESPONSE, True).allow)

    def test_oversized_input_does_not_reach_provider(self):
        self.assertFalse(WellnessSafetySupervisor().begin_turn("x" * (MAX_INPUT_CHARS + 1)).allow_provider)

    def test_input_limit_cannot_hide_a_crisis_or_clear_followup(self):
        for text in ["I want to die" + " " * MAX_INPUT_CHARS,
                     "x" * MAX_INPUT_CHARS + ". I want to die"]:
            supervisor = WellnessSafetySupervisor()
            decision = supervisor.begin_turn(text)
            self.assertTrue(decision.crisis_detected)
            self.assertEqual(decision.override_response, CRISIS_RESPONSE)
            self.assertFalse(supervisor.begin_turn("What should I do now?").allow_provider)


class TurnReceiptTests(unittest.TestCase):
    def make_engine(self, provider=None, supervisor=None):
        db = WellnessDB(":memory:")
        self.addCleanup(db.close)
        engine = ChatEngine(db, Memory(), provider or Provider(["A quiet walk might help."]),
                            safety_supervisor=supervisor)
        engine.start_session("test-session")
        return engine, db

    def assert_delivery(self, engine, db, text, status):
        receipts = db.get_safety_receipts("test-session")
        emitted = [r for r in receipts if r["event_type"] == "emission"]
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["content_sha256"], digest(text))
        self.assertEqual(emitted[0]["completion_status"], status)
        self.assertIsNotNone(emitted[0]["message_id"])
        self.assertTrue(all(r["turn_id"] == emitted[0]["turn_id"] for r in receipts))
        self.assertTrue(all(r["policy_version"] for r in receipts))
        self.assertEqual(receipts[-1]["event_type"], "turn_end")
        self.assertEqual(db.get_session_messages("test-session")[-1].content, text)

    def test_allowed_full_response_hash_and_atomic_delivery_before_yield(self):
        text = "A calm first sentence. " + "A separate ending. " * 10
        engine, db = self.make_engine(Provider([text[:60], text[60:]]))
        stream = engine.send_message("Long day")
        received = next(stream)
        self.assert_delivery(engine, db, received, "completed")
        self.assertEqual(received, text.strip())
        stream.close()
        self.assertEqual(len([r for r in db.get_safety_receipts("test-session") if r["event_type"] == "turn_end"]), 1)

    def test_crisis_override_has_outbound_record_and_no_provider_call(self):
        provider = Provider(["must not be called"])
        engine, db = self.make_engine(provider)
        self.assertEqual(list(engine.send_message("I want to die")), [CRISIS_RESPONSE])
        self.assertEqual(provider.calls, 0)
        self.assert_delivery(engine, db, CRISIS_RESPONSE, "local_override")
        engine.start_session("test-session")
        self.assertTrue(engine.is_crisis_active)
        list(engine.send_message("I am still here"))
        self.assertEqual(provider.calls, 0)

    def test_rejection_and_replacement_have_distinct_full_hashes(self):
        unsafe = "You only need me."
        engine, db = self.make_engine(Provider([unsafe]))
        result = "".join(engine.send_message("Hello"))
        self.assert_delivery(engine, db, result, "blocked_replaced")
        rejected = [r for r in db.get_safety_receipts("test-session")
                    if r["direction"] == "outbound_assistant" and r["event_type"] == "assessment"]
        self.assertFalse(rejected[0]["allowed"])
        self.assertEqual(rejected[0]["content_sha256"], digest(unsafe))
        self.assertNotEqual(digest(result), digest(unsafe))

    def test_empty_and_error_have_terminal_records_and_no_partial_output(self):
        for error, status in [(None, "empty"), (RuntimeError("failed"), "error")]:
            engine, db = self.make_engine(Provider([] if error is None else ["a" * 500], error))
            if error:
                with self.assertRaises(RuntimeError):
                    next(engine.send_message("Hello"))
            else:
                self.assertEqual(list(engine.send_message("Hello")), [])
            receipts = db.get_safety_receipts("test-session")
            self.assertEqual(receipts[-1]["completion_status"], status)
            self.assertEqual(receipts[-1]["content_sha256"], digest(""))
            self.assertFalse(any(r["event_type"] == "emission" for r in receipts))

    def test_denied_custom_supervisor_without_text_stays_denied(self):
        class Denied(NoOpSafetySupervisor):
            def begin_turn(self, text):
                return UserSafetyDecision(allow_provider=False)
        provider = Provider(["must not appear"])
        engine, db = self.make_engine(provider, Denied())
        self.assertEqual(list(engine.send_message("Hello")), [GENERAL_OUTPUT_FALLBACK])
        self.assertEqual(provider.calls, 0)
        self.assertTrue(all(not r["system2_enforced"] for r in db.get_safety_receipts("test-session")))

    def test_noop_does_not_claim_enforcement(self):
        engine, db = self.make_engine(Provider(["You only need me."]), NoOpSafetySupervisor())
        self.assertEqual(list(engine.send_message("Hello")), ["You only need me."])
        self.assertTrue(all(not r["system2_enforced"] for r in db.get_safety_receipts("test-session")))

    def test_cancelled_and_empty_generations_cannot_pollute_next_provider_turn(self):
        for cancel in (True, False):
            class HistoryProvider(Provider):
                def new_session(self):
                    self.history = []

                def stream_response(self, *args):
                    if cancel:
                        yield "You only need me."
                    self.history.append("unchecked provider state")
                    if cancel:
                        engine.cancel_pending_response()
            provider = HistoryProvider()
            engine, db = self.make_engine(provider)
            self.assertEqual(list(engine.send_message("Hello")), [])
            self.assertEqual(provider.history, [])
            self.assertEqual(db.get_safety_receipts("test-session")[-1]["completion_status"],
                             "cancelled" if cancel else "empty")

    def test_size_limit_replacement_is_recorded(self):
        engine, db = self.make_engine(Provider(["a" * (MAX_OUTPUT_CHARS + 1)]))
        result = "".join(engine.send_message("Hello"))
        self.assert_delivery(engine, db, result, "blocked_replaced")
        self.assertIn("output_limit", db.get_safety_receipts("test-session")[-1]["reason_codes"])

    def test_atomic_message_rollback_when_receipt_write_fails(self):
        engine, db = self.make_engine()
        list(engine.send_message("Hello"))
        receipt = db.get_safety_receipts("test-session")[-1]
        before = len(db.get_session_messages("test-session"))
        with self.assertRaises(Exception):
            db.save_message_with_receipts(Message(None, "test-session", "assistant", "orphan", "now"), [receipt])
        self.assertEqual(len(db.get_session_messages("test-session")), before)

    def test_receipts_survive_reopening_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "chat.db")
            db = WellnessDB(path)
            engine = ChatEngine(db, Memory(), Provider(["Hello there."]))
            engine.start_session("test-session")
            list(engine.send_message("Hello"))
            db.close()
            reopened = WellnessDB(path)
            try:
                self.assert_delivery(engine, reopened, "Hello there.", "completed")
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
