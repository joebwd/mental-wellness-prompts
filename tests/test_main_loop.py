from contextlib import ExitStack
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from wellness_cli import __main__ as app


class FakeDB:
    def get_stats(self):
        return {
            "total_sessions": 1,
            "total_messages": 0,
            "facts_learned": 0,
            "mood_entries": 0,
        }

    def close(self):
        pass


class FakeVault:
    def __init__(self):
        self.lock_calls = []

    def lock(self, session):
        self.lock_calls.append(session)


class FakeIdentityManager:
    def __init__(self):
        self.vault = FakeVault()

    def get_vault(self, _identity_id):
        return self.vault


class FakeGovernedActions:
    def __init__(self, available=True):
        self.available = available
        self.started_sessions = []
        self.ended_sessions = []

    def start_session(self, session_id):
        self.started_sessions.append(session_id)
        return self.available

    def end_session(self, session_id):
        self.ended_sessions.append(session_id)
        return self.available


class FakeEngine:
    def __init__(self):
        self.messages = []
        self.send_calls = []
        self.started_sessions = []
        self.cancel_calls = 0

    def start_session(self, session_id):
        self.started_sessions.append(session_id)

    def send_message(self, text):
        self.send_calls.append(text)
        return iter(["steady"])

    def cancel_pending_response(self):
        self.cancel_calls += 1

    def get_message_count(self):
        return 0


class MainLoopTests(unittest.TestCase):
    def test_plain_text_input_is_sent_to_chat_engine(self):
        fake_db = FakeDB()
        fake_soul = SimpleNamespace(exists=True, name="Joe")
        fake_provider = SimpleNamespace(name="claude", model="opus", check_auth=lambda: None)
        fake_engine = FakeEngine()
        fake_governed_actions = FakeGovernedActions()
        fake_identity = SimpleNamespace(id="identity-1", label="Joe")
        fake_identity_manager = FakeIdentityManager()
        fake_vault_session = object()

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    app,
                    "load_startup_preferences",
                    return_value={"provider": "claude", "model": "opus", "pangoclaw_mode": "auto"},
                )
            )
            stack.enter_context(patch.object(app, "_configure_storage_home", return_value="/tmp/moss-home"))
            stack.enter_context(patch.object(app, "IdentityManager", return_value=fake_identity_manager))
            stack.enter_context(patch.object(app, "_choose_identity", return_value=fake_identity))
            stack.enter_context(patch.object(app, "_unlock_or_create_vault", return_value=fake_vault_session))
            stack.enter_context(patch.object(app, "WellnessDB", return_value=fake_db))
            stack.enter_context(patch.object(app, "MemoryStore"))
            stack.enter_context(patch.object(app, "SoulProfile", return_value=fake_soul))
            stack.enter_context(patch.object(app, "_build_governed_actions", return_value=fake_governed_actions))
            stack.enter_context(patch.object(app, "get_provider", return_value=fake_provider))
            stack.enter_context(patch.object(app, "build_chat_engine", return_value=fake_engine))
            stack.enter_context(patch.object(app, "_end_session"))
            stack.enter_context(patch.object(app, "detect_crisis", return_value=False))
            stack.enter_context(patch.object(app.cli, "choose_model", return_value="opus"))
            stack.enter_context(patch.object(app.cli, "show_banner"))
            stack.enter_context(patch.object(app.cli, "show_notice"))
            stack.enter_context(patch.object(app.cli, "show_provider_status"))
            stack.enter_context(patch.object(app.cli, "show_returning_welcome"))
            stack.enter_context(patch.object(app.cli, "show_soul_loaded"))
            show_user_message = stack.enter_context(patch.object(app.cli, "show_user_message"))
            stream_ai_response = stack.enter_context(
                patch.object(app.cli, "stream_ai_response", return_value="steady")
            )
            stack.enter_context(patch.object(app.cli, "get_user_input", side_effect=["hello moss", "/quit"]))
            stack.enter_context(patch("sys.argv", ["moss"]))
            exit_code = app.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake_engine.send_calls, ["hello moss"])
        show_user_message.assert_called_once_with("hello moss", name="Joe")
        stream_ai_response.assert_called_once()
        self.assertEqual(len(fake_engine.started_sessions), 1)
        self.assertEqual(len(fake_governed_actions.started_sessions), 1)
        self.assertEqual(fake_identity_manager.vault.lock_calls, [fake_vault_session])

    def test_no_dynamic_onboarding_flag_skips_followup_generator(self):
        fake_db = FakeDB()
        fake_soul = SimpleNamespace(exists=False, name="Joe", store_onboarding=lambda answers: None)
        fake_provider = SimpleNamespace(name="claude", model="opus", check_auth=lambda: None)
        fake_engine = FakeEngine()
        fake_governed_actions = FakeGovernedActions()
        fake_identity = SimpleNamespace(id="identity-1", label="Joe")
        fake_identity_manager = FakeIdentityManager()
        fake_vault_session = object()

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    app,
                    "load_startup_preferences",
                    return_value={"provider": "claude", "model": "opus", "pangoclaw_mode": "auto"},
                )
            )
            stack.enter_context(patch.object(app, "_configure_storage_home", return_value="/tmp/moss-home"))
            stack.enter_context(patch.object(app, "IdentityManager", return_value=fake_identity_manager))
            stack.enter_context(patch.object(app, "_choose_identity", return_value=fake_identity))
            stack.enter_context(patch.object(app, "_unlock_or_create_vault", return_value=fake_vault_session))
            stack.enter_context(patch.object(app, "WellnessDB", return_value=fake_db))
            stack.enter_context(patch.object(app, "MemoryStore"))
            stack.enter_context(patch.object(app, "SoulProfile", return_value=fake_soul))
            stack.enter_context(patch.object(app, "_build_governed_actions", return_value=fake_governed_actions))
            stack.enter_context(patch.object(app, "get_provider", return_value=fake_provider))
            stack.enter_context(patch.object(app, "build_chat_engine", return_value=fake_engine))
            stack.enter_context(patch.object(app, "_end_session"))
            stack.enter_context(patch.object(app.cli, "choose_model", return_value="opus"))
            stack.enter_context(patch.object(app.cli, "show_banner"))
            stack.enter_context(patch.object(app.cli, "show_notice"))
            stack.enter_context(patch.object(app.cli, "show_provider_status"))
            stack.enter_context(patch.object(app.cli, "show_soul_loaded"))
            run_onboarding = stack.enter_context(
                patch.object(app.cli, "run_onboarding", return_value={"name": "Joe"})
            )
            store_onboarding = stack.enter_context(patch.object(fake_soul, "store_onboarding"))
            stack.enter_context(patch.object(app.cli, "clear_screen"))
            stack.enter_context(patch("time.sleep"))
            stack.enter_context(patch.object(app.cli, "get_user_input", side_effect=["/quit"]))
            stack.enter_context(patch("sys.argv", ["moss", "--no-dynamic-onboarding"]))
            exit_code = app.main()

        self.assertEqual(exit_code, 0)
        self.assertIsNone(run_onboarding.call_args.kwargs["dynamic_generator"])
        store_onboarding.assert_called_once_with({"name": "Joe"})

    def test_unsafe_disable_supervisor_flag_is_forwarded_to_factory(self):
        fake_db = FakeDB()
        fake_soul = SimpleNamespace(exists=True, name="Joe")
        fake_provider = SimpleNamespace(name="claude", model="opus", check_auth=lambda: None)
        fake_engine = FakeEngine()
        fake_governed_actions = FakeGovernedActions()
        fake_identity = SimpleNamespace(id="identity-1", label="Joe")
        fake_identity_manager = FakeIdentityManager()
        fake_vault_session = object()

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    app,
                    "load_startup_preferences",
                    return_value={"provider": "claude", "model": "opus", "pangoclaw_mode": "auto"},
                )
            )
            stack.enter_context(patch.object(app, "_configure_storage_home", return_value="/tmp/moss-home"))
            stack.enter_context(patch.object(app, "IdentityManager", return_value=fake_identity_manager))
            stack.enter_context(patch.object(app, "_choose_identity", return_value=fake_identity))
            stack.enter_context(patch.object(app, "_unlock_or_create_vault", return_value=fake_vault_session))
            stack.enter_context(patch.object(app, "WellnessDB", return_value=fake_db))
            stack.enter_context(patch.object(app, "MemoryStore"))
            stack.enter_context(patch.object(app, "SoulProfile", return_value=fake_soul))
            stack.enter_context(patch.object(app, "_build_governed_actions", return_value=fake_governed_actions))
            stack.enter_context(patch.object(app, "get_provider", return_value=fake_provider))
            build_chat_engine = stack.enter_context(
                patch.object(app, "build_chat_engine", return_value=fake_engine)
            )
            stack.enter_context(patch.object(app, "_end_session"))
            stack.enter_context(patch.object(app.cli, "choose_model", return_value="opus"))
            stack.enter_context(patch.object(app.cli, "show_banner"))
            show_notice = stack.enter_context(patch.object(app.cli, "show_notice"))
            stack.enter_context(patch.object(app.cli, "show_provider_status"))
            stack.enter_context(patch.object(app.cli, "show_returning_welcome"))
            stack.enter_context(patch.object(app.cli, "show_soul_loaded"))
            stack.enter_context(patch.object(app.cli, "get_user_input", side_effect=["/quit"]))
            stack.enter_context(patch("sys.argv", ["moss", "--unsafe-disable-safety-supervisor"]))
            exit_code = app.main()

        self.assertEqual(exit_code, 0)
        feature_flags = build_chat_engine.call_args.kwargs["feature_flags"]
        self.assertFalse(feature_flags.enable_safety_supervisor)
        self.assertTrue(any("safety supervisor disabled" in call.args[0].lower() for call in show_notice.call_args_list))

    def test_setup_command_runs_wizard_and_respects_pangoclaw_choice(self):
        fake_db = FakeDB()
        fake_soul = SimpleNamespace(exists=True, name="Joe")
        fake_provider = SimpleNamespace(name="codex", model="gpt-5.4", check_auth=lambda: None)
        fake_engine = FakeEngine()
        fake_governed_actions = FakeGovernedActions(available=False)
        fake_identity = SimpleNamespace(id="identity-1", label="Joe")
        fake_identity_manager = FakeIdentityManager()
        fake_vault_session = object()

        with ExitStack() as stack:
            stack.enter_context(patch.object(app, "load_startup_preferences", return_value={}))
            stack.enter_context(
                patch.object(
                    app,
                    "_run_startup_wizard",
                    return_value={"provider": "codex", "model": "gpt-5.4", "pangoclaw_mode": "off"},
                )
            )
            stack.enter_context(patch.object(app, "_configure_storage_home", return_value="/tmp/moss-home"))
            stack.enter_context(patch.object(app, "IdentityManager", return_value=fake_identity_manager))
            stack.enter_context(patch.object(app, "_choose_identity", return_value=fake_identity))
            stack.enter_context(patch.object(app, "_unlock_or_create_vault", return_value=fake_vault_session))
            stack.enter_context(patch.object(app, "WellnessDB", return_value=fake_db))
            stack.enter_context(patch.object(app, "MemoryStore"))
            stack.enter_context(patch.object(app, "SoulProfile", return_value=fake_soul))
            stack.enter_context(patch.object(app, "_build_governed_actions", return_value=fake_governed_actions))
            get_provider = stack.enter_context(patch.object(app, "get_provider", return_value=fake_provider))
            stack.enter_context(patch.object(app, "build_chat_engine", return_value=fake_engine))
            stack.enter_context(patch.object(app, "_end_session"))
            stack.enter_context(patch.object(app.cli, "show_banner"))
            stack.enter_context(patch.object(app.cli, "clear_screen"))
            show_notice = stack.enter_context(patch.object(app.cli, "show_notice"))
            stack.enter_context(patch.object(app.cli, "show_provider_status"))
            show_returning_welcome = stack.enter_context(patch.object(app.cli, "show_returning_welcome"))
            stack.enter_context(patch.object(app.cli, "show_soul_loaded"))
            choose_profile_start = stack.enter_context(
                patch.object(app.cli, "choose_profile_start", return_value="continue")
            )
            stack.enter_context(patch.object(app.cli, "get_user_input", side_effect=["/quit"]))
            stack.enter_context(patch("sys.argv", ["moss", "setup"]))
            exit_code = app.main()

        self.assertEqual(exit_code, 0)
        get_provider.assert_called_with("codex", "gpt-5.4")
        choose_profile_start.assert_called_once_with("Joe")
        show_returning_welcome.assert_called_once()
        self.assertTrue(any("pangoclaw disabled" in call.args[0].lower() for call in show_notice.call_args_list))


if __name__ == "__main__":
    unittest.main()
