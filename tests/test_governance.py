import json
import os
import socketserver
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler
from typing import Optional
from unittest.mock import patch

from wellness_cli import __main__ as app
from wellness_cli.db import Message, WellnessDB
from wellness_cli.governance import (
    GovernedWellnessActions,
    GovernanceDecision,
    PangoClawSidecarClient,
)


class FakeClient:
    def __init__(
        self,
        before_decision: GovernanceDecision,
        message_decision: Optional[GovernanceDecision] = None,
        available: bool = True,
    ):
        self.before_decision = before_decision
        self.message_decision = message_decision or GovernanceDecision(
            allowed=True,
            status="approved",
            reason="",
            policy_name=before_decision.policy_name,
        )
        self.available = available
        self.before_calls = []
        self.after_calls = []
        self.message_calls = []
        self.started_sessions = []
        self.ended_sessions = []

    def before_tool_call(self, **kwargs):
        self.before_calls.append(kwargs)
        return self.before_decision

    def after_tool_call(self, **kwargs):
        self.after_calls.append(kwargs)
        return self.available

    def message_sending(self, **kwargs):
        self.message_calls.append(kwargs)
        return self.message_decision

    def start_session(self, session_id, agent_id):
        self.started_sessions.append((session_id, agent_id))
        return self.available

    def end_session(self, session_id, agent_id):
        self.ended_sessions.append((session_id, agent_id))
        return self.available


class SidecarHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        return

    def _read_json(self):
        length = int(self.headers.get("content-length", "0"))
        payload = self.rfile.read(length) if length else b"{}"
        return json.loads(payload.decode("utf-8"))

    def _write_json(self, status, payload):
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        self.server.calls.append((self.command, self.path, None))
        if self.path == "/status":
            self._write_json(
                200,
                {
                    "ready": True,
                    "policy": {
                        "name": "Local Sidecar Policy",
                        "enforcement_mode": "enforce",
                    },
                },
            )
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self):
        body = self._read_json()
        self.server.calls.append((self.command, self.path, body))

        if self.path == "/gate/before-tool-call":
            if body.get("toolName") == "blocked.tool":
                self._write_json(200, {"block": True, "blockReason": "blocked by policy"})
            else:
                self._write_json(200, {"block": False, "blockReason": ""})
            return

        if self.path == "/gate/after-tool-call":
            self._write_json(200, {})
            return

        if self.path == "/gate/message-sending":
            content = body.get("content")
            if isinstance(content, str) and "secret" in content.lower():
                self._write_json(
                    200,
                    {
                        "cancel": True,
                        "content": "[PangoClaw] Outbound message blocked by output gate.",
                    },
                )
            else:
                self._write_json(200, {})
            return

        if self.path in {"/session/start", "/session/end"}:
            self._write_json(200, {})
            return

        self._write_json(404, {"error": "not found"})


class UnixHTTPServer(socketserver.UnixStreamServer):
    allow_reuse_address = True


class GovernanceTests(unittest.TestCase):
    def test_governed_extract_facts_uses_sidecar_tool_routes_and_logs_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = WellnessDB(os.path.join(tmpdir, "governance.db"))
            client = FakeClient(
                GovernanceDecision(
                    allowed=True,
                    status="approved",
                    reason="ok",
                    policy_name="wellness-side-effects",
                )
            )
            actions = GovernedWellnessActions(db=db, client=client)

            try:
                result = actions.extract_facts(
                    prompt="facts prompt",
                    session_id="session-1",
                    message_count=8,
                    crisis_stage="normal",
                    oneshot_fn=lambda prompt: "[]",
                )
                self.assertTrue(result.executed)
                self.assertEqual(result.value, "[]")
                self.assertEqual(len(client.before_calls), 1)
                self.assertEqual(client.before_calls[0]["tool_name"], "memory.extract_facts")
                self.assertEqual(client.before_calls[0]["provenance"], "planner_autonomous")
                self.assertEqual(len(client.after_calls), 1)
                self.assertEqual(client.after_calls[0]["tool_name"], "memory.extract_facts")

                statuses = [event.status for event in db.get_governance_events()]
                self.assertIn("approved", statuses)
                self.assertIn("completed", statuses)
            finally:
                db.close()

    def test_governed_actions_fail_closed_when_sidecar_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = WellnessDB(os.path.join(tmpdir, "governance-unavailable.db"))
            client = FakeClient(
                GovernanceDecision(
                    allowed=False,
                    status="unavailable",
                    reason="PangoClaw sidecar unavailable",
                ),
                available=False,
            )
            actions = GovernedWellnessActions(db=db, client=client)
            called = {"oneshot": 0}

            try:
                result = actions.summarize_session(
                    prompt="summary prompt",
                    session_id="session-1",
                    message_count=8,
                    crisis_stage="crisis_followup",
                    oneshot_fn=lambda prompt: called.__setitem__("oneshot", called["oneshot"] + 1),
                )
                self.assertFalse(result.executed)
                self.assertEqual(called["oneshot"], 0)
                self.assertEqual(len(client.after_calls), 0)

                events = db.get_governance_events()
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].status, "unavailable")
            finally:
                db.close()

    def test_onboarding_followup_question_is_blocked_by_message_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = WellnessDB(os.path.join(tmpdir, "followup-blocked.db"))
            client = FakeClient(
                GovernanceDecision(
                    allowed=True,
                    status="approved",
                    reason="ok",
                    policy_name="wellness-side-effects",
                ),
                message_decision=GovernanceDecision(
                    allowed=False,
                    status="blocked_output",
                    reason="PangoClaw blocked outbound content",
                    policy_name="wellness-side-effects",
                    replacement_text="[PangoClaw] Outbound message blocked by output gate.",
                ),
            )
            actions = GovernedWellnessActions(db=db, client=client)

            try:
                result = actions.onboarding_followup_question(
                    prompt="follow-up prompt",
                    session_id="onboarding",
                    answers_seen=3,
                    last_key="stress",
                    oneshot_fn=lambda prompt: "Here is a secret follow-up",
                )
                self.assertFalse(result.executed)
                self.assertEqual(len(client.message_calls), 1)
                self.assertEqual(len(client.after_calls), 1)
                self.assertEqual(client.after_calls[0]["error"], "PangoClaw blocked outbound content")

                statuses = [event.status for event in db.get_governance_events()]
                self.assertIn("approved", statuses)
                self.assertIn("blocked_output", statuses)
            finally:
                db.close()

    def test_export_is_governed_and_writes_when_approved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = WellnessDB(os.path.join(tmpdir, "export.db"))
            db.save_message(
                Message(
                    id=None,
                    session_id="session-1",
                    role="user",
                    content="hello",
                    timestamp="2026-03-21T00:00:00+00:00",
                )
            )
            export_path = os.path.join(tmpdir, "wellness_export.json")
            client = FakeClient(
                GovernanceDecision(
                    allowed=True,
                    status="approved",
                    reason="ok",
                    policy_name="wellness-side-effects",
                )
            )
            actions = GovernedWellnessActions(db=db, client=client)

            try:
                with patch.object(app, "get_plain_export_path", return_value=export_path), \
                     patch.object(app.cli, "show_notice") as show_notice:
                    app._export(db, actions)

                self.assertTrue(os.path.exists(export_path))
                with open(export_path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                self.assertEqual(len(payload), 1)
                self.assertEqual(payload[0]["content"], "hello")
                self.assertEqual(client.before_calls[0]["tool_name"], "export.transcript")
                self.assertEqual(len(client.message_calls), 1)
                self.assertEqual(len(client.after_calls), 1)
                self.assertTrue(any("Exported 1 messages" in call.args[0] for call in show_notice.call_args_list))
            finally:
                db.close()

    def test_export_is_blocked_when_message_gate_denies_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = WellnessDB(os.path.join(tmpdir, "export-blocked.db"))
            export_path = os.path.join(tmpdir, "wellness_export.json")
            client = FakeClient(
                GovernanceDecision(
                    allowed=True,
                    status="approved",
                    reason="ok",
                    policy_name="wellness-side-effects",
                ),
                message_decision=GovernanceDecision(
                    allowed=False,
                    status="blocked_output",
                    reason="PangoClaw blocked outbound content",
                    policy_name="wellness-side-effects",
                ),
            )
            actions = GovernedWellnessActions(db=db, client=client)

            try:
                with patch.object(app, "get_plain_export_path", return_value=export_path), \
                     patch.object(app.cli, "show_notice") as show_notice:
                    app._export(db, actions)

                self.assertFalse(os.path.exists(export_path))
                self.assertEqual(len(client.before_calls), 1)
                self.assertEqual(len(client.message_calls), 1)
                self.assertEqual(len(client.after_calls), 1)
                self.assertTrue(any("Export blocked:" in call.args[0] for call in show_notice.call_args_list))
            finally:
                db.close()

    def test_session_lifecycle_delegates_to_sidecar_client(self):
        client = FakeClient(
            GovernanceDecision(allowed=True, status="approved", reason="", policy_name="local"),
        )
        actions = GovernedWellnessActions(db=object(), client=client)

        self.assertTrue(actions.start_session("session-1"))
        self.assertTrue(actions.end_session("session-1"))
        self.assertEqual(client.started_sessions, [("session-1", "moss-cli")])
        self.assertEqual(client.ended_sessions, [("session-1", "moss-cli")])


class PangoClawClientContractTests(unittest.TestCase):
    def test_unix_socket_client_matches_sidecar_route_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = os.path.join(tmpdir, "pangoclaw.sock")
            server = UnixHTTPServer(socket_path, SidecarHandler)
            server.calls = []
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                client = PangoClawSidecarClient(socket_path=socket_path, timeout_secs=1.0)

                status = client.status(force=True)
                self.assertTrue(status.ready)
                self.assertEqual(status.policy_name, "Local Sidecar Policy")
                self.assertEqual(status.enforcement_mode, "enforce")

                decision = client.before_tool_call(
                    tool_name="memory.extract_facts",
                    params={"message_count": 4},
                    session_id="session-1",
                    provenance="planner_autonomous",
                    user_initiated=False,
                    is_user_request=False,
                    agent_id="moss-cli",
                )
                self.assertTrue(decision.allowed)

                self.assertTrue(
                    client.after_tool_call(
                        tool_name="memory.extract_facts",
                        params={"message_count": 4},
                        session_id="session-1",
                        result={"chars": 2},
                        duration_ms=12,
                        agent_id="moss-cli",
                    )
                )

                clean = client.message_sending(content="Clean outbound content")
                self.assertTrue(clean.allowed)

                blocked = client.message_sending(content="This contains a secret")
                self.assertFalse(blocked.allowed)
                self.assertEqual(blocked.status, "blocked_output")

                self.assertTrue(client.start_session("session-1"))
                self.assertTrue(client.end_session("session-1"))

                paths = [(method, path) for method, path, _ in server.calls]
                self.assertIn(("GET", "/status"), paths)
                self.assertIn(("POST", "/gate/before-tool-call"), paths)
                self.assertIn(("POST", "/gate/after-tool-call"), paths)
                self.assertIn(("POST", "/gate/message-sending"), paths)
                self.assertIn(("POST", "/session/start"), paths)
                self.assertIn(("POST", "/session/end"), paths)

                before_body = next(
                    body for method, path, body in server.calls
                    if method == "POST" and path == "/gate/before-tool-call"
                )
                self.assertEqual(before_body["toolName"], "memory.extract_facts")
                self.assertEqual(before_body["provenance"], "planner_autonomous")
                self.assertEqual(before_body["sessionId"], "session-1")
                self.assertEqual(before_body["agentId"], "moss-cli")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=1)
                if os.path.exists(socket_path):
                    os.unlink(socket_path)


if __name__ == "__main__":
    unittest.main()
