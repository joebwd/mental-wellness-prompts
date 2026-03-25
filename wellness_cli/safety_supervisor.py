"""
Deterministic wellness-specific safety supervision for the main chat path.

This module keeps conversational safety in Python:
  - classify inbound user text before a provider call
  - track explicit session-level crisis state
  - hold back streamed model output until it clears policy checks
  - replace blocked content with local safe fallback text
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Protocol, Sequence, Tuple


# ── Crisis Detection ──────────────────────────────────────────────────

CRISIS_PATTERNS = [
    r"\b(i\s+(?:just\s+|really\s+|sometimes\s+)?want\s+to\s+die)\b",
    r"\b(kill(ing)?\s+(my|him|her|them)?self)\b",
    r"\b(end\s+(my|it\s+all|this)\s*(life)?)\b",
    r"\b(suicid[ea]l?)\b",
    r"\b(don'?t\s+want\s+to\s+(live|be\s+alive|exist|be\s+here))\b",
    r"\b(better\s+off\s+(without\s+me|dead|if\s+i))\b",
    r"\b(no\s+(point|reason)\s+(in\s+living|anymore|to\s+go\s+on|to\s+live))\b",
    r"\b(life\s+(isn'?t|is\s+not)\s+worth\s+living)\b",
    r"\b(can'?t\s+(go\s+on|take\s+(it|this)\s+anymore|do\s+this\s+anymore))\b",
    r"\b((won'?t|will\s+not)\s+be\s+around\s+much\s+longer)\b",
    r"\b(getting\s+my\s+affairs\s+in\s+order)\b",
    r"\b(planning\s+to\s+(hurt|harm|kill))\b",
    r"\b(i'?m\s+(going\s+to|gonna)\s+(hurt|harm|kill)\s+(my|him|her|them)?self)\b",
    r"\b(i\s+want\s+to\s+hurt\s+(my|him|her|them)?self)\b",
    r"\b(i\s+wish\s+i\s+(was|were)\s+dead)\b",
    r"\b(i\s+(already\s+)?(took|taken)\s+(a\s+)?(handful|bunch|lot)\s+of\s+(pills|tablets|meds|medications?))\b",
    r"\b(i\s+cut\s+myself)\b",
    r"\b(self[\s-]?harm(ed|ing)?)\b",
    r"\b(i\s+(might|want\s+to|am\s+going\s+to|gonna)\s+(hurt|harm|kill)\s+someone)\b",
    r"\b(goodbye\s+forever)\b",
    r"\b(help\s+me\s+(kill|hurt)\s+(myself|someone))\b",
    r"\b(how\s+do\s+i\s+(kill|hurt)\s+(myself|someone))\b",
    r"\b(best\s+way\s+to\s+(kill|hurt)\s+(myself|someone))\b",
]

CRISIS_RE = re.compile("|".join(CRISIS_PATTERNS), re.IGNORECASE)

FALSE_POSITIVE_PATTERNS = [
    r"(movie|film|book|song|show|game|character)\b.*\b(die|kill|dead)",
    r"(joke|kidding|just\s+saying|hypothetical)",
    r"(kill\s+it|killing\s+it|kill\s+time|die\s+laughing|to\s+die\s+for)",
]
FALSE_POSITIVE_RE = re.compile("|".join(FALSE_POSITIVE_PATTERNS), re.IGNORECASE)


def detect_crisis(text: str) -> bool:
    """Return True when text likely reflects acute self-harm or violence risk."""
    if not text:
        return False
    if not CRISIS_RE.search(text):
        return False
    if FALSE_POSITIVE_RE.search(text):
        return False
    return True


# ── Wellness Policy Heuristics ───────────────────────────────────────

SELF_HARM_OR_VIOLENCE_INSTRUCTION_PATTERNS = [
    r"\b(how|ways?|steps?|best\s+way|safest\s+way|help\s+me)\b.{0,40}\b(kill|hurt|harm|cut|overdose|poison|stab|shoot|strangle)\b",
    r"\b(take|use|mix|tie|hang|jump|slice|stab|shoot)\b.{0,40}\b(yourself|myself|someone|them)\b",
    r"\b(hide|cover\s+up|conceal)\b.{0,30}\b(cuts?|self[\s-]?harm|bruises?|injur(?:y|ies)|overdose)\b",
    r"\b(don'?t\s+tell|keep\s+it\s+secret|make\s+it\s+look\s+like)\b.{0,30}\b(self[\s-]?harm|suicide|violence|injur(?:y|ies)|overdose)\b",
]
SELF_HARM_OR_VIOLENCE_INSTRUCTION_RE = re.compile(
    "|".join(SELF_HARM_OR_VIOLENCE_INSTRUCTION_PATTERNS),
    re.IGNORECASE | re.DOTALL,
)

MEDICATION_ADVICE_PATTERNS = [
    r"\b(start|stop|increase|decrease|double|halve|skip|take|switch|taper)\b.{0,45}\b(medication|medications|meds|dose|dosage|mg|milligrams?|pill|tablet|prescription)\b",
    r"\b(start|stop|increase|decrease|double|halve|skip|take|switch|taper)\b.{0,45}\b(sertraline|fluoxetine|prozac|zoloft|lexapro|citalopram|escitalopram|adderall|vyvanse|ritalin|wellbutrin|bupropion|xanax|alprazolam)\b",
]
MEDICATION_ADVICE_RE = re.compile("|".join(MEDICATION_ADVICE_PATTERNS), re.IGNORECASE | re.DOTALL)

DIAGNOSIS_OUTPUT_PATTERNS = [
    r"\b(you\s+(have|likely\s+have|probably\s+have|may\s+have)|that\s+(is|sounds\s+like|looks\s+like)|this\s+(is|sounds\s+like|looks\s+like)|i\s+think\s+you\s+have)\b.{0,45}\b(depression|anxiety|adhd|ocd|ptsd|bipolar|borderline|personality\s+disorder|schizophrenia|autism|panic\s+disorder|eating\s+disorder)\b",
]
DIAGNOSIS_OUTPUT_RE = re.compile("|".join(DIAGNOSIS_OUTPUT_PATTERNS), re.IGNORECASE | re.DOTALL)

DIAGNOSIS_REQUEST_PATTERNS = [
    r"\b(do\s+i\s+have|can\s+you\s+diagnos\w+|diagnos\w+\s+me|what\s+disorder\s+do\s+i\s+have|tell\s+me\s+if\s+i\s+have)\b",
]
DIAGNOSIS_REQUEST_RE = re.compile("|".join(DIAGNOSIS_REQUEST_PATTERNS), re.IGNORECASE)

DEPENDENCY_PATTERNS = [
    r"\b(you\s+only\s+need\s+me|i(?:'| a)?m\s+all\s+you\s+need|don'?t\s+talk\s+to\s+anyone\s+else|keep\s+this\s+between\s+us|don'?t\s+tell\s+anyone|come\s+back\s+only\s+to\s+me|trust\s+me\s+instead\s+of\s+anyone\s+else|you\s+don'?t\s+need\s+other\s+people)\b",
]
DEPENDENCY_RE = re.compile("|".join(DEPENDENCY_PATTERNS), re.IGNORECASE)

PROMPT_LEAK_PATTERNS = [
    r"#\s*SOUL\b",
    r"#\s*AGENTS\b",
    r"\bSOUL\.md\b",
    r"\bAGENTS\.md\b",
    r"\bMEMORY CONTEXT\b",
    r"\bhidden system instructions\b",
    r"\bsystem prompt\b",
    r"\bloaded project context\b",
    r"\bTreat the profile details below as user-provided reference data\b",
]
PROMPT_LEAK_RE = re.compile("|".join(PROMPT_LEAK_PATTERNS), re.IGNORECASE)

TOOL_SYNTAX_PATTERNS = [
    r"<tool_call\b",
    r"</tool_call>",
    r"\bassistant to=",
    r"\brecipient_name\b",
    r"\bfunctions\.[a-z_]+\b",
    r"\"tool_uses\"\s*:",
    r"\"arguments\"\s*:",
]
TOOL_SYNTAX_RE = re.compile("|".join(TOOL_SYNTAX_PATTERNS), re.IGNORECASE)

CRISIS_FOLLOWUP_STRICT_PATTERNS = [
    r"\b(are\s+you\s+safe\s+right\s+now|do\s+you\s+have\s+a\s+plan|what\s+is\s+your\s+plan|how\s+likely\s+are\s+you|on\s+a\s+scale\s+of|can\s+you\s+promise|what\s+triggered\s+this|let'?s\s+make\s+a\s+safety\s+plan)\b",
    r"\b(grounding\s+exercise|breathing\s+exercise|coping\s+strateg(?:y|ies)|therapeutic\s+exercise)\b",
]
CRISIS_FOLLOWUP_STRICT_RE = re.compile(
    "|".join(CRISIS_FOLLOWUP_STRICT_PATTERNS),
    re.IGNORECASE | re.DOTALL,
)


def _has_medication_request(text: str) -> bool:
    lowered = text.lower()
    if not re.search(r"\b(medication|medications|meds|dose|dosage|mg|milligrams?|pill|tablet|prescription)\b", lowered):
        return False
    return bool(re.search(r"\b(should\s+i|can\s+i|is\s+it\s+okay\s+to|how\s+much|what\s+dose|increase|decrease|stop|start|skip|double|mix)\b", lowered))


def _has_prompt_leak_request(text: str) -> bool:
    lowered = text.lower()
    if not re.search(r"\b(system prompt|hidden instructions|soul|agents|memory context|internal prompt|rules)\b", lowered):
        return False
    return bool(re.search(r"\b(show|tell|reveal|quote|print|dump|leak|what\s+are)\b", lowered))


def _has_tool_syntax_request(text: str) -> bool:
    return bool(TOOL_SYNTAX_RE.search(text))


# ── State + Decisions ────────────────────────────────────────────────

class CrisisStage(str, Enum):
    NORMAL = "normal"
    CRISIS_TURN = "crisis_turn"
    CRISIS_FOLLOWUP = "crisis_followup"


@dataclass
class CrisisState:
    stage: CrisisStage = CrisisStage.NORMAL
    trigger_count: int = 0
    last_trigger_text: str = ""

    @property
    def strict_mode(self) -> bool:
        return self.stage != CrisisStage.NORMAL


@dataclass(frozen=True)
class UserSafetyDecision:
    allow_provider: bool
    crisis_detected: bool = False
    override_response: str | None = None
    reason_codes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class AssistantSafetyDecision:
    allow: bool
    safe_fallback: str | None = None
    reason_codes: Tuple[str, ...] = ()


@dataclass
class StreamSafetyResult:
    released_text: str = ""
    blocked: bool = False
    safe_fallback: str | None = None
    reason_codes: Tuple[str, ...] = ()


CRISIS_RESPONSE = (
    "I'm really glad you said it out loud. Please contact live support now: 988 in the US, "
    "116 123 in the UK, 13 11 14 in Australia, or text HOME to 741741. If you can, reach out "
    "to someone near you too."
)

HARM_REFUSAL_RESPONSE = (
    "I can't help with hurting yourself, hurting someone, or hiding that kind of harm. "
    "Please contact live support now: 988 in the US, or text HOME to 741741. If you can, "
    "reach out to someone nearby too."
)

MEDICATION_RESPONSE = (
    "I can't advise on medication or dosing. A doctor, pharmacist, or urgent care clinician "
    "is the right place for that. If it feels urgent, contact them now."
)

DIAGNOSIS_RESPONSE = (
    "I can't diagnose what this is. A licensed clinician can help sort that out. If you want, "
    "tell me what feels most noticeable and I can help you put it into words."
)

PROMPT_BOUNDARY_RESPONSE = (
    "I can't share internal instructions, memory internals, or tool syntax. Tell me what you "
    "need in plain language and I'll stay with that."
)

STRICT_FALLBACK_RESPONSE = (
    "I want to keep this brief and safe. Please lean on live human support too: 988 in the US, "
    "or text HOME to 741741. If someone nearby can be with you, contact them now."
)

GENERAL_OUTPUT_FALLBACK = (
    "I need to keep this practical and safe. Tell me what feels hardest right now, and if there's "
    "immediate danger, contact live support or someone nearby now."
)


def _dedupe_codes(codes: Sequence[str]) -> Tuple[str, ...]:
    seen = set()
    ordered: List[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return tuple(ordered)


class StreamSafetyBuffer:
    """Hold back streamed text so unsafe content can be blocked before release."""

    _BOUNDARY_RE = re.compile(r"(?:[.!?](?:[\"')\]]+)?\s+|\n+)")

    def __init__(
        self,
        supervisor: "WellnessSafetySupervisor",
        holdback_chars: int = 48,
        force_release_chars: int = 240,
    ):
        self.supervisor = supervisor
        self.holdback_chars = holdback_chars
        self.force_release_chars = force_release_chars
        self.buffer = ""
        self.released = ""

    def _release_cutoff(self) -> int:
        if self.supervisor.is_crisis_active:
            return 0

        if len(self.buffer) <= self.holdback_chars:
            return 0

        max_release = len(self.buffer) - self.holdback_chars
        boundary_cutoff = 0
        for match in self._BOUNDARY_RE.finditer(self.buffer[:max_release]):
            boundary_cutoff = match.end()

        if boundary_cutoff:
            return boundary_cutoff

        if len(self.buffer) >= self.force_release_chars:
            return max_release

        return 0

    def push(self, chunk: str) -> StreamSafetyResult:
        self.buffer += chunk
        assessment = self.supervisor.inspect_assistant_text(self.buffer, final=False)
        if not assessment.allow:
            self.buffer = ""
            return StreamSafetyResult(
                blocked=True,
                safe_fallback=assessment.safe_fallback,
                reason_codes=assessment.reason_codes,
            )

        releasable = ""
        cutoff = self._release_cutoff()
        if cutoff:
            releasable = self.buffer[:cutoff]
            self.buffer = self.buffer[cutoff:]
            self.released += releasable

        return StreamSafetyResult(released_text=releasable)

    def finish(self) -> StreamSafetyResult:
        assessment = self.supervisor.inspect_assistant_text(self.buffer, final=True)
        if not assessment.allow:
            self.buffer = ""
            return StreamSafetyResult(
                blocked=True,
                safe_fallback=assessment.safe_fallback,
                reason_codes=assessment.reason_codes,
            )

        releasable = self.buffer
        self.buffer = ""
        self.released += releasable
        return StreamSafetyResult(released_text=releasable)


class NoOpStreamSafetyBuffer:
    """Pass-through stream buffer for embeddings that disable chat supervision."""

    def push(self, chunk: str) -> StreamSafetyResult:
        return StreamSafetyResult(released_text=chunk)

    def finish(self) -> StreamSafetyResult:
        return StreamSafetyResult()


class SafetySupervisor(Protocol):
    """Minimal interface ChatEngine needs from a safety supervisor."""

    crisis_state: CrisisState

    @property
    def is_crisis_active(self) -> bool:
        ...

    def reset(self):
        ...

    def begin_turn(self, user_text: str) -> UserSafetyDecision:
        ...

    def complete_assistant_turn(self):
        ...

    def prompt_guidance(self) -> str:
        ...

    def new_stream_buffer(self):
        ...

    def inspect_assistant_text(self, text: str, final: bool) -> AssistantSafetyDecision:
        ...


class WellnessSafetySupervisor:
    """Session-aware, rule-first supervision for the chat path."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._crisis_state = CrisisState()

    @property
    def crisis_state(self) -> CrisisState:
        return self._crisis_state

    @property
    def is_crisis_active(self) -> bool:
        return self._crisis_state.strict_mode

    def begin_turn(self, user_text: str) -> UserSafetyDecision:
        codes: List[str] = []
        crisis = detect_crisis(user_text)
        if crisis:
            self._crisis_state.stage = CrisisStage.CRISIS_TURN
            self._crisis_state.trigger_count += 1
            self._crisis_state.last_trigger_text = user_text
            codes.append("crisis")
            return UserSafetyDecision(
                allow_provider=False,
                crisis_detected=True,
                override_response=CRISIS_RESPONSE,
                reason_codes=_dedupe_codes(codes),
            )

        if SELF_HARM_OR_VIOLENCE_INSTRUCTION_RE.search(user_text):
            codes.append("harm_instruction")
            if not self._crisis_state.strict_mode:
                self._crisis_state.stage = CrisisStage.CRISIS_FOLLOWUP
            return UserSafetyDecision(
                allow_provider=False,
                override_response=HARM_REFUSAL_RESPONSE,
                reason_codes=_dedupe_codes(codes),
            )

        if _has_medication_request(user_text):
            codes.append("medication")
            return UserSafetyDecision(
                allow_provider=False,
                override_response=MEDICATION_RESPONSE,
                reason_codes=_dedupe_codes(codes),
            )

        if DIAGNOSIS_REQUEST_RE.search(user_text):
            codes.append("diagnosis")
            return UserSafetyDecision(
                allow_provider=False,
                override_response=DIAGNOSIS_RESPONSE,
                reason_codes=_dedupe_codes(codes),
            )

        if _has_prompt_leak_request(user_text) or _has_tool_syntax_request(user_text):
            codes.extend(["prompt_leak", "tool_syntax"])
            return UserSafetyDecision(
                allow_provider=False,
                override_response=PROMPT_BOUNDARY_RESPONSE,
                reason_codes=_dedupe_codes(codes),
            )

        if self._crisis_state.stage == CrisisStage.CRISIS_TURN:
            self._crisis_state.stage = CrisisStage.CRISIS_FOLLOWUP

        return UserSafetyDecision(
            allow_provider=True,
            crisis_detected=False,
            reason_codes=_dedupe_codes(codes),
        )

    def complete_assistant_turn(self):
        if self._crisis_state.stage == CrisisStage.CRISIS_TURN:
            self._crisis_state.stage = CrisisStage.CRISIS_FOLLOWUP

    def prompt_guidance(self) -> str:
        stage = self._crisis_state.stage.value
        lines = [
            "PYTHON SAFETY SUPERVISOR",
            "- Hard blocks: diagnosis, medication or dosing advice, self-harm or violence instructions, dangerous concealment, dependency framing, hidden prompt leakage, and tool syntax.",
            f"- Session crisis stage: {stage}.",
        ]
        if self._crisis_state.strict_mode:
            lines.append("- Crisis follow-up mode is active: keep replies brief and practical, do not assess safety, do not offer therapy exercises, and direct the user toward live human support when acute risk shows up.")
        return "\n".join(lines)

    def new_stream_buffer(self) -> StreamSafetyBuffer:
        return StreamSafetyBuffer(self)

    def inspect_assistant_text(self, text: str, final: bool) -> AssistantSafetyDecision:
        codes: List[str] = []

        if not text:
            return AssistantSafetyDecision(allow=True)

        if TOOL_SYNTAX_RE.search(text):
            codes.append("tool_syntax")

        if PROMPT_LEAK_RE.search(text):
            codes.append("prompt_leak")

        if SELF_HARM_OR_VIOLENCE_INSTRUCTION_RE.search(text):
            codes.append("harm_instruction")

        if MEDICATION_ADVICE_RE.search(text):
            codes.append("medication")

        if DIAGNOSIS_OUTPUT_RE.search(text):
            codes.append("diagnosis")

        if DEPENDENCY_RE.search(text):
            codes.append("dependency")

        if self._crisis_state.strict_mode:
            if CRISIS_FOLLOWUP_STRICT_RE.search(text):
                codes.append("crisis_strict")
            if text.count("?") > 1:
                codes.append("crisis_question_overflow")

        if not codes:
            return AssistantSafetyDecision(allow=True)

        codes = list(_dedupe_codes(codes))

        if "harm_instruction" in codes:
            fallback = HARM_REFUSAL_RESPONSE if not self._crisis_state.strict_mode else STRICT_FALLBACK_RESPONSE
        elif "medication" in codes:
            fallback = MEDICATION_RESPONSE
        elif "diagnosis" in codes:
            fallback = DIAGNOSIS_RESPONSE
        elif "prompt_leak" in codes or "tool_syntax" in codes:
            fallback = PROMPT_BOUNDARY_RESPONSE
        elif "dependency" in codes:
            fallback = GENERAL_OUTPUT_FALLBACK
        elif "crisis_strict" in codes or "crisis_question_overflow" in codes:
            fallback = STRICT_FALLBACK_RESPONSE
        else:
            fallback = GENERAL_OUTPUT_FALLBACK

        return AssistantSafetyDecision(
            allow=False,
            safe_fallback=fallback,
            reason_codes=tuple(codes),
        )


class NoOpSafetySupervisor:
    """Disable Python chat supervision for non-wellness embeddings or tests."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._crisis_state = CrisisState()

    @property
    def crisis_state(self) -> CrisisState:
        return self._crisis_state

    @property
    def is_crisis_active(self) -> bool:
        return False

    def begin_turn(self, user_text: str) -> UserSafetyDecision:
        return UserSafetyDecision(allow_provider=True)

    def complete_assistant_turn(self):
        return None

    def prompt_guidance(self) -> str:
        return ""

    def new_stream_buffer(self) -> NoOpStreamSafetyBuffer:
        return NoOpStreamSafetyBuffer()

    def inspect_assistant_text(self, text: str, final: bool) -> AssistantSafetyDecision:
        return AssistantSafetyDecision(allow=True)
