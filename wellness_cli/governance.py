"""
PangoClaw sidecar integration for governed wellness side effects.

Main conversational safety stays in Python inside Moss. This module is a
translation layer for governed side effects only:

- memory.extract_facts
- memory.summarize_session
- profile.refine
- export.transcript
- onboarding.followup_question
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from .db import GovernanceEvent


DEFAULT_PANGOCLAW_SOCKET = "/tmp/pangoclaw.sock"
DEFAULT_TIMEOUT_SECS = 2.0
DEFAULT_AGENT_ID = "moss-cli"
STATUS_CACHE_TTL_SECS = 2.0
MAX_SIDECAR_CONTENT_BYTES = 900_000


class GovernanceTransportError(RuntimeError):
    """Raised when the local sidecar cannot be reached or returns invalid data."""


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    """Minimal HTTP client that connects over a Unix domain socket."""

    def __init__(self, socket_path: str, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


@dataclass(frozen=True)
class SidecarStatus:
    ready: bool
    policy_name: str = ""
    enforcement_mode: str = ""
    reason: str = ""


@dataclass(frozen=True)
class GovernanceDecision:
    allowed: bool
    status: str
    reason: str = ""
    receipt_id: Optional[str] = None
    policy_name: str = ""
    replacement_text: Optional[str] = None


@dataclass(frozen=True)
class GovernedActionResult:
    executed: bool
    value: Any
    decision: GovernanceDecision


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _safe_json(value: Any) -> str:
    try:
        return _json_dumps(value)
    except (TypeError, ValueError):
        return _json_dumps({"unserializable": str(value)})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _result_summary(value: Any) -> Dict[str, Any]:
    if value is None:
        return {"type": "none"}

    if isinstance(value, str):
        return {
            "type": "text",
            "chars": len(value),
            "sha256": _sha256_text(value),
        }

    try:
        serialized = _json_dumps(value)
    except (TypeError, ValueError):
        return {"type": type(value).__name__}

    return {
        "type": "json",
        "chars": len(serialized),
        "sha256": _sha256_text(serialized),
    }


class PangoClawSidecarClient:
    """HTTP-over-Unix-socket client for the local PangoClaw sidecar."""

    def __init__(
        self,
        socket_path: Optional[str] = None,
        timeout_secs: float = DEFAULT_TIMEOUT_SECS,
    ):
        self.socket_path = os.path.expanduser(
            socket_path or os.environ.get("PANGOCLAW_SOCKET", DEFAULT_PANGOCLAW_SOCKET)
        )
        self.timeout_secs = float(timeout_secs)
        self._cached_status = SidecarStatus(ready=False, reason="status not checked")
        self._status_checked_at = 0.0

    @property
    def available(self) -> bool:
        return self.status().ready

    def status(self, force: bool = False) -> SidecarStatus:
        now = time.monotonic()
        if (
            not force
            and self._status_checked_at
            and (now - self._status_checked_at) < STATUS_CACHE_TTL_SECS
        ):
            return self._cached_status

        if not os.path.exists(self.socket_path):
            self._cached_status = SidecarStatus(
                ready=False,
                reason=f"PangoClaw socket not found at {self.socket_path}",
            )
            self._status_checked_at = now
            return self._cached_status

        try:
            response = self._request_json("GET", "/status")
        except GovernanceTransportError as exc:
            self._cached_status = SidecarStatus(ready=False, reason=str(exc))
            self._status_checked_at = now
            return self._cached_status

        policy = response.get("policy") if isinstance(response, dict) else None
        self._cached_status = SidecarStatus(
            ready=bool(response.get("ready")),
            policy_name=str(policy.get("name") or "") if isinstance(policy, dict) else "",
            enforcement_mode=(
                str(policy.get("enforcement_mode") or "") if isinstance(policy, dict) else ""
            ),
            reason="",
        )
        self._status_checked_at = now
        return self._cached_status

    def before_tool_call(
        self,
        *,
        tool_name: str,
        params: Dict[str, Any],
        session_id: str,
        provenance: str,
        user_initiated: bool,
        is_user_request: bool,
        agent_id: str = DEFAULT_AGENT_ID,
    ) -> GovernanceDecision:
        status = self.status(force=True)
        if not status.ready:
            return GovernanceDecision(
                allowed=False,
                status="unavailable",
                reason=status.reason or "PangoClaw unavailable",
                policy_name=status.policy_name,
            )

        try:
            body = self._request_json(
                "POST",
                "/gate/before-tool-call",
                {
                    "toolName": tool_name,
                    "params": params,
                    "provenance": provenance,
                    "userInitiated": user_initiated,
                    "isUserRequest": is_user_request,
                    "sessionId": session_id,
                    "agentId": agent_id,
                },
            )
        except GovernanceTransportError as exc:
            return GovernanceDecision(
                allowed=False,
                status="unavailable",
                reason=str(exc),
                policy_name=status.policy_name,
            )

        blocked = bool(body.get("block"))
        return GovernanceDecision(
            allowed=not blocked,
            status="blocked" if blocked else "approved",
            reason=str(body.get("blockReason") or ""),
            policy_name=status.policy_name,
        )

    def after_tool_call(
        self,
        *,
        tool_name: str,
        params: Dict[str, Any],
        session_id: str,
        result: Any = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
        agent_id: str = DEFAULT_AGENT_ID,
    ) -> bool:
        status = self.status(force=True)
        if not status.ready:
            return False

        try:
            self._request_json(
                "POST",
                "/gate/after-tool-call",
                {
                    "toolName": tool_name,
                    "params": params,
                    "result": result,
                    "error": error,
                    "durationMs": duration_ms,
                    "sessionId": session_id,
                    "agentId": agent_id,
                },
            )
            return True
        except GovernanceTransportError:
            return False

    def message_sending(self, *, content: Any) -> GovernanceDecision:
        status = self.status(force=True)
        if not status.ready:
            return GovernanceDecision(
                allowed=False,
                status="unavailable",
                reason=status.reason or "PangoClaw unavailable",
                policy_name=status.policy_name,
            )

        try:
            body = self._request_json(
                "POST",
                "/gate/message-sending",
                {"content": content},
            )
        except GovernanceTransportError as exc:
            return GovernanceDecision(
                allowed=False,
                status="unavailable",
                reason=str(exc),
                policy_name=status.policy_name,
            )

        cancelled = bool(body.get("cancel"))
        return GovernanceDecision(
            allowed=not cancelled,
            status="blocked_output" if cancelled else "approved",
            reason=(
                "PangoClaw blocked outbound content"
                if cancelled
                else str(body.get("reason") or "")
            ),
            policy_name=status.policy_name,
            replacement_text=str(body.get("content") or "") if cancelled else None,
        )

    def start_session(self, session_id: str, agent_id: str = DEFAULT_AGENT_ID) -> bool:
        return self._session_call("/session/start", session_id=session_id, agent_id=agent_id)

    def end_session(self, session_id: str, agent_id: str = DEFAULT_AGENT_ID) -> bool:
        return self._session_call("/session/end", session_id=session_id, agent_id=agent_id)

    def _session_call(self, path: str, *, session_id: str, agent_id: str) -> bool:
        status = self.status(force=True)
        if not status.ready:
            return False
        try:
            self._request_json(
                "POST",
                path,
                {
                    "sessionId": session_id,
                    "agentId": agent_id,
                },
            )
            return True
        except GovernanceTransportError:
            return False

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        body = _json_dumps(payload) if payload is not None else None
        conn = UnixSocketHTTPConnection(self.socket_path, self.timeout_secs)
        try:
            headers = {"content-type": "application/json"} if body is not None else {}
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            raw = response.read().decode("utf-8")
        except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError) as exc:
            raise GovernanceTransportError(f"PangoClaw sidecar unavailable: {exc}") from exc
        finally:
            conn.close()

        if response.status >= 400:
            raise GovernanceTransportError(
                f"PangoClaw sidecar error {response.status}: {raw or 'empty response'}"
            )

        if not raw.strip():
            return {}

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GovernanceTransportError("PangoClaw returned invalid JSON") from exc

        if not isinstance(parsed, dict):
            raise GovernanceTransportError("PangoClaw returned a non-object response")
        return parsed


class GovernedWellnessActions:
    """Fail-closed wrapper for side effects that require local governance."""

    def __init__(
        self,
        db,
        client: Optional[PangoClawSidecarClient] = None,
        agent_id: str = DEFAULT_AGENT_ID,
    ):
        self.db = db
        self.client = client or PangoClawSidecarClient()
        self.agent_id = agent_id

    @property
    def available(self) -> bool:
        return self.client.available

    def start_session(self, session_id: str) -> bool:
        return self.client.start_session(session_id=session_id, agent_id=self.agent_id)

    def end_session(self, session_id: str) -> bool:
        return self.client.end_session(session_id=session_id, agent_id=self.agent_id)

    def extract_facts(
        self,
        *,
        prompt: str,
        session_id: str,
        message_count: int,
        crisis_stage: str,
        oneshot_fn: Callable[[str], Any],
    ) -> GovernedActionResult:
        return self._run_oneshot_action(
            action="memory.extract_facts",
            prompt=prompt,
            session_id=session_id,
            provenance="planner_autonomous",
            user_initiated=False,
            is_user_request=False,
            metadata={
                "message_count": message_count,
                "crisis_stage": crisis_stage,
                "prompt_chars": len(prompt),
                "prompt_sha256": _sha256_text(prompt),
            },
            oneshot_fn=oneshot_fn,
        )

    def summarize_session(
        self,
        *,
        prompt: str,
        session_id: str,
        message_count: int,
        crisis_stage: str,
        oneshot_fn: Callable[[str], Any],
    ) -> GovernedActionResult:
        return self._run_oneshot_action(
            action="memory.summarize_session",
            prompt=prompt,
            session_id=session_id,
            provenance="planner_autonomous",
            user_initiated=False,
            is_user_request=False,
            metadata={
                "message_count": message_count,
                "crisis_stage": crisis_stage,
                "prompt_chars": len(prompt),
                "prompt_sha256": _sha256_text(prompt),
            },
            oneshot_fn=oneshot_fn,
        )

    def refine_profile(
        self,
        *,
        prompt: str,
        session_id: str,
        message_count: int,
        crisis_stage: str,
        oneshot_fn: Callable[[str], Any],
    ) -> GovernedActionResult:
        return self._run_oneshot_action(
            action="profile.refine",
            prompt=prompt,
            session_id=session_id,
            provenance="planner_autonomous",
            user_initiated=False,
            is_user_request=False,
            metadata={
                "message_count": message_count,
                "crisis_stage": crisis_stage,
                "prompt_chars": len(prompt),
                "prompt_sha256": _sha256_text(prompt),
            },
            oneshot_fn=oneshot_fn,
        )

    def onboarding_followup_question(
        self,
        *,
        prompt: str,
        session_id: str,
        answers_seen: int,
        last_key: str,
        oneshot_fn: Callable[[str], Any],
    ) -> GovernedActionResult:
        return self._run_oneshot_action(
            action="onboarding.followup_question",
            prompt=prompt,
            session_id=session_id,
            provenance="planner_autonomous",
            user_initiated=False,
            is_user_request=False,
            metadata={
                "answers_seen": answers_seen,
                "last_key": last_key,
                "prompt_chars": len(prompt),
                "prompt_sha256": _sha256_text(prompt),
            },
            oneshot_fn=oneshot_fn,
            scan_output=True,
        )

    def export_transcript(self, *, export_path: str, messages: list[dict]) -> GovernedActionResult:
        payload = _json_dumps(messages)
        params = {
            "export_path": export_path,
            "message_count": len(messages),
            "payload_bytes": len(payload.encode("utf-8")),
            "payload_sha256": _sha256_text(payload),
        }
        decision = self.client.before_tool_call(
            tool_name="export.transcript",
            params=params,
            session_id="export",
            provenance="user_request",
            user_initiated=True,
            is_user_request=True,
            agent_id=self.agent_id,
        )
        self._record_event(
            action="export.transcript",
            decision=decision,
            session_id="export",
            metadata={"phase": "before_tool_call", "params": params},
        )
        if not decision.allowed:
            return GovernedActionResult(False, None, decision)

        if len(payload.encode("utf-8")) > MAX_SIDECAR_CONTENT_BYTES:
            blocked = GovernanceDecision(
                allowed=False,
                status="blocked_output",
                reason="Export payload exceeds the local sidecar scan limit",
                policy_name=decision.policy_name,
            )
            self._record_event(
                action="export.transcript",
                decision=blocked,
                session_id="export",
                metadata={"phase": "message_sending", "payload_bytes": len(payload.encode("utf-8"))},
            )
            self.client.after_tool_call(
                tool_name="export.transcript",
                params=params,
                session_id="export",
                error=blocked.reason,
                agent_id=self.agent_id,
            )
            return GovernedActionResult(False, None, blocked)

        outbound = self.client.message_sending(content=payload)
        if not outbound.allowed:
            self._record_event(
                action="export.transcript",
                decision=outbound,
                session_id="export",
                metadata={"phase": "message_sending", "payload_bytes": len(payload.encode("utf-8"))},
            )
            self.client.after_tool_call(
                tool_name="export.transcript",
                params=params,
                session_id="export",
                error=outbound.reason,
                agent_id=self.agent_id,
            )
            return GovernedActionResult(False, None, outbound)

        started = time.monotonic()
        try:
            export_dir = os.path.dirname(export_path)
            if export_dir:
                os.makedirs(export_dir, exist_ok=True)
            with open(export_path, "w", encoding="utf-8") as handle:
                json.dump(messages, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
        except OSError as exc:
            error_decision = GovernanceDecision(
                allowed=True,
                status="error",
                reason=str(exc),
                policy_name=decision.policy_name,
            )
            self._record_event(
                action="export.transcript",
                decision=error_decision,
                session_id="export",
                metadata={"phase": "write_failed", "params": params},
            )
            self.client.after_tool_call(
                tool_name="export.transcript",
                params=params,
                session_id="export",
                error=str(exc),
                duration_ms=int((time.monotonic() - started) * 1000),
                agent_id=self.agent_id,
            )
            return GovernedActionResult(False, None, error_decision)

        duration_ms = int((time.monotonic() - started) * 1000)
        self.client.after_tool_call(
            tool_name="export.transcript",
            params=params,
            session_id="export",
            result={"export_path": export_path, "message_count": len(messages)},
            duration_ms=duration_ms,
            agent_id=self.agent_id,
        )
        completed = GovernanceDecision(
            allowed=True,
            status="completed",
            reason="",
            policy_name=decision.policy_name,
        )
        self._record_event(
            action="export.transcript",
            decision=completed,
            session_id="export",
            metadata={
                "phase": "after_tool_call",
                "duration_ms": duration_ms,
                "params": params,
            },
        )
        return GovernedActionResult(True, export_path, completed)

    def _run_oneshot_action(
        self,
        *,
        action: str,
        prompt: str,
        session_id: str,
        provenance: str,
        user_initiated: bool,
        is_user_request: bool,
        metadata: Dict[str, Any],
        oneshot_fn: Callable[[str], Any],
        scan_output: bool = False,
    ) -> GovernedActionResult:
        params = dict(metadata)
        decision = self.client.before_tool_call(
            tool_name=action,
            params=params,
            session_id=session_id,
            provenance=provenance,
            user_initiated=user_initiated,
            is_user_request=is_user_request,
            agent_id=self.agent_id,
        )
        self._record_event(
            action=action,
            decision=decision,
            session_id=session_id,
            metadata={"phase": "before_tool_call", "params": params},
        )
        if not decision.allowed:
            return GovernedActionResult(False, None, decision)

        started = time.monotonic()
        try:
            value = oneshot_fn(prompt)
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            error_decision = GovernanceDecision(
                allowed=True,
                status="error",
                reason=str(exc),
                policy_name=decision.policy_name,
            )
            self.client.after_tool_call(
                tool_name=action,
                params=params,
                session_id=session_id,
                error=str(exc),
                duration_ms=duration_ms,
                agent_id=self.agent_id,
            )
            self._record_event(
                action=action,
                decision=error_decision,
                session_id=session_id,
                metadata={"phase": "after_tool_call", "params": params, "duration_ms": duration_ms},
            )
            return GovernedActionResult(False, None, error_decision)

        duration_ms = int((time.monotonic() - started) * 1000)

        if scan_output and value:
            serialized = value if isinstance(value, str) else _safe_json(value)
            if len(serialized.encode("utf-8")) > MAX_SIDECAR_CONTENT_BYTES:
                output_decision = GovernanceDecision(
                    allowed=False,
                    status="blocked_output",
                    reason="Generated output exceeds the local sidecar scan limit",
                    policy_name=decision.policy_name,
                )
            else:
                output_decision = self.client.message_sending(content=serialized)

            if not output_decision.allowed:
                self.client.after_tool_call(
                    tool_name=action,
                    params=params,
                    session_id=session_id,
                    error=output_decision.reason,
                    duration_ms=duration_ms,
                    agent_id=self.agent_id,
                )
                self._record_event(
                    action=action,
                    decision=output_decision,
                    session_id=session_id,
                    metadata={
                        "phase": "message_sending",
                        "params": params,
                        "duration_ms": duration_ms,
                    },
                )
                return GovernedActionResult(False, None, output_decision)

        self.client.after_tool_call(
            tool_name=action,
            params=params,
            session_id=session_id,
            result=_result_summary(value),
            duration_ms=duration_ms,
            agent_id=self.agent_id,
        )
        completed = GovernanceDecision(
            allowed=True,
            status="completed",
            reason="",
            policy_name=decision.policy_name,
        )
        self._record_event(
            action=action,
            decision=completed,
            session_id=session_id,
            metadata={
                "phase": "after_tool_call",
                "params": params,
                "duration_ms": duration_ms,
                "result": _result_summary(value),
            },
        )
        return GovernedActionResult(True, value, completed)

    def _record_event(
        self,
        *,
        action: str,
        decision: GovernanceDecision,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        if not hasattr(self.db, "save_governance_event"):
            return

        event = GovernanceEvent(
            id=None,
            action=action,
            status=decision.status,
            session_id=session_id,
            receipt_id=decision.receipt_id,
            reason=decision.reason,
            policy_name=decision.policy_name,
            metadata_json=_safe_json(metadata or {}),
            created_at=_now_iso(),
        )
        try:
            self.db.save_governance_event(event)
        except Exception:
            pass
