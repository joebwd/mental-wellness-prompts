"""
Reusable factory and feature-toggle helpers for Moss embeddings.

This keeps the CLI thin while giving other Python applications a small,
dependency-friendly API surface.
"""

import json
from dataclasses import dataclass
from typing import Optional

from .chat_engine import ChatEngine
from .governance import GovernedWellnessActions
from .memory import MemoryStore
from .providers import Provider
from .safety_supervisor import NoOpSafetySupervisor, SafetySupervisor, WellnessSafetySupervisor


@dataclass(frozen=True)
class MossFeatureFlags:
    """Feature toggles for CLI and library consumers."""

    enable_dynamic_onboarding_followups: bool = True
    max_dynamic_onboarding_questions: int = 2
    enable_safety_supervisor: bool = True


def build_safety_supervisor(
    enabled: bool = True,
    supervisor: Optional[SafetySupervisor] = None,
) -> SafetySupervisor:
    """Return the configured supervisor implementation for the chat path."""
    if supervisor is not None:
        return supervisor
    if enabled:
        return WellnessSafetySupervisor()
    return NoOpSafetySupervisor()


def build_chat_engine(
    *,
    db,
    memory: MemoryStore,
    provider: Provider,
    soul_profile=None,
    governed_actions: Optional[GovernedWellnessActions] = None,
    safety_supervisor: Optional[SafetySupervisor] = None,
    feature_flags: Optional[MossFeatureFlags] = None,
) -> ChatEngine:
    """Construct a ChatEngine with explicit feature toggles."""
    flags = feature_flags or MossFeatureFlags()
    return ChatEngine(
        db=db,
        memory=memory,
        provider=provider,
        soul_profile=soul_profile,
        safety_supervisor=build_safety_supervisor(
            enabled=flags.enable_safety_supervisor,
            supervisor=safety_supervisor,
        ),
        governed_actions=governed_actions,
    )


def build_dynamic_onboarding_generator(
    engine: ChatEngine,
    governed_actions: Optional[GovernedWellnessActions],
    feature_flags: Optional[MossFeatureFlags] = None,
):
    """
    Return an optional governed follow-up generator for onboarding.

    Library and CLI callers can omit this entirely to use only the fixed
    onboarding questions.
    """
    flags = feature_flags or MossFeatureFlags()
    if not flags.enable_dynamic_onboarding_followups or not governed_actions:
        return None

    state = {
        "dynamic_count": 0,
        "max_dynamic": max(0, int(flags.max_dynamic_onboarding_questions)),
    }

    if state["max_dynamic"] <= 0:
        return None

    def generate(answers: dict):
        if state["dynamic_count"] >= state["max_dynamic"]:
            return None

        keys = list(answers.keys())
        if not keys:
            return None
        last_key = keys[-1]
        last_answer = answers[last_key]

        if len(last_answer.split()) < 5:
            return None

        if last_key == "name":
            return None

        prompt = f"""You are onboarding a new user for a mental wellness companion app.
They just answered a question. Based on their answer, generate ONE short follow-up question
that would help you understand them better.

Rules:
- Keep it under 15 words
- Make it feel natural and conversational, not clinical
- Don't repeat or rephrase what they said
- Don't ask about preferences or style — ask about their life
- If their answer is complete and doesn't warrant follow-up, respond with just: SKIP

Their previous answers: {json.dumps(answers)}
Their most recent answer (to "{last_key}"): "{last_answer}"

Respond with ONLY the follow-up question, or SKIP. Nothing else."""

        try:
            result = governed_actions.onboarding_followup_question(
                prompt=prompt,
                session_id=engine.session_id or "onboarding",
                answers_seen=len(answers),
                last_key=last_key,
                oneshot_fn=engine._call_oneshot,
            )
            question_text = result.value if result.executed else None
            if not question_text or "SKIP" in question_text.upper() or len(question_text) > 100:
                return None

            question = question_text.strip().strip('"').strip("'")
            if not question or question.upper() == "SKIP":
                return None

            state["dynamic_count"] += 1
            return {
                "prompt": question,
                "key": f"dynamic_{state['dynamic_count']}",
                "analysis_hint": "dynamic",
            }
        except Exception:
            return None

    return generate
