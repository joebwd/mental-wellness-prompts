#!/usr/bin/env python3
"""
Crisis Detection Supervisor

A multi-tier crisis detection system for mental wellness applications.

Features:
- Multi-tier detection (regex, ML screening, contextual analysis)
- Circuit breaker for repeated crisis events
- State management with caching
- Multilingual support (10+ languages)
- Comprehensive audit trail

License: MIT
Author: Community Edition
Version: 2.0.0
"""

import asyncio
import hashlib
import json
import logging
import re
import sys
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Allow the documented direct-script invocation as well as package imports.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from wellness_cli.safety_supervisor import COMPLETE_DENIAL_RE, normalize_policy_text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================


class CrisisSeverity(Enum):
    """Crisis severity levels with numeric values for comparison"""

    NONE = (0, "none")
    LOW = (1, "low")
    MODERATE = (2, "moderate")
    HIGH = (3, "high")
    CRITICAL = (4, "critical")

    def __init__(self, level: int, label: str):
        self.level = level
        self.label = label

    def __gt__(self, other):
        return self.level > other.level

    def __ge__(self, other):
        return self.level >= other.level


class CrisisCategory(Enum):
    """Categories of crisis indicators"""

    SUICIDAL_IDEATION = "suicidal_ideation"
    SELF_HARM = "self_harm"
    HOPELESSNESS = "hopelessness"
    DEATH_IDEATION = "death_ideation"
    INDIRECT_SUICIDAL = "indirect_suicidal"
    FAREWELL = "farewell"
    PLANNING = "planning"
    MEANS = "means"


class RecommendedAction(Enum):
    """Recommended actions based on crisis detection"""

    PROCEED = "proceed"  # Continue normal conversation
    MONITOR = "monitor"  # Log and continue with monitoring
    INTERRUPT = "interrupt"  # Immediate intervention required


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Bypass normal flow, go to crisis resources
    HALF_OPEN = "half_open"  # Testing if user has stabilized


@dataclass
class CrisisPattern:
    """Crisis detection pattern definition"""

    pattern: str
    severity: CrisisSeverity
    category: CrisisCategory
    language: str = "en"
    is_direct: bool = True
    confidence_weight: float = 1.0
    cultural_context: Optional[str] = None
    requires_context: bool = False


@dataclass
class CrisisDetectionResult:
    """Comprehensive crisis detection result"""

    severity: CrisisSeverity
    confidence: float
    indicators: List[str] = field(default_factory=list)
    categories: Set[CrisisCategory] = field(default_factory=set)
    requires_resources: bool = False
    recommended_action: RecommendedAction = RecommendedAction.PROCEED
    detection_method: str = "unknown"
    latency_ms: float = 0
    language: str = "en"
    context_modifier: Optional[str] = None
    reasoning: Optional[str] = None
    cache_hit: bool = False


@dataclass
class CrisisResource:
    """Crisis resource definition"""

    name: str
    phone: Optional[str] = None
    text: Optional[str] = None
    web: Optional[str] = None
    availability: str = "24/7"
    languages: List[str] = field(default_factory=lambda: ["en"])
    specialties: List[str] = field(default_factory=list)
    priority: int = 0  # Lower number = higher priority


@dataclass
class UserCrisisState:
    """User crisis state tracking (Pillar 1: non-expiring post-crisis guardrails)"""

    user_id: str
    state: CircuitState = CircuitState.CLOSED
    crisis_count: int = 0
    last_crisis_time: Optional[datetime] = None
    window_started_time: Optional[datetime] = None
    resources_shown_time: Optional[datetime] = None
    post_crisis_messages: int = 0
    post_crisis_latched: bool = False
    never_expires: bool = True
    severity_history: List[CrisisSeverity] = field(default_factory=list)

    def should_bypass_analysis(self, window_minutes: int = 30) -> bool:
        """Use the canonical circuit decision, never infer risk from a raw count.

        ``window_minutes`` remains accepted for API compatibility. Evidence
        windows and optional recovery are owned by CircuitBreaker; an isolated
        MODERATE observation must not become an indefinite crisis interruption.
        """
        return self.post_crisis_latched or self.state == CircuitState.OPEN


# ============================================================================
# PATTERN DEFINITIONS
# ============================================================================


class PatternDatabase:
    """Comprehensive crisis pattern database"""

    @staticmethod
    def get_patterns() -> Dict[str, List[CrisisPattern]]:
        """Get all crisis detection patterns by language"""
        return {
            "en": [
                # Critical - Direct suicidal ideation
                CrisisPattern(
                    r"\b(kill\s+myself|end\s+my\s+life|commit\s+suicide|take\s+my\s+life)\b",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.SUICIDAL_IDEATION,
                ),
                CrisisPattern(
                    r"\b(want\s+to\s+die|ready\s+to\s+die|better\s+off\s+dead)\b",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.SUICIDAL_IDEATION,
                ),
                CrisisPattern(
                    r"\b(going\s+to\s+kill|about\s+to\s+end|planning\s+to\s+die)\b",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.PLANNING,
                ),
                # Critical - Means and methods
                CrisisPattern(
                    r"\b(overdose|hang\s+myself|jump\s+off|cut\s+my\s+wrists)\b",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.MEANS,
                ),
                CrisisPattern(
                    r"\b(gun\s+to\s+my\s+head|pills\s+to\s+end|poison\s+myself)\b",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.MEANS,
                ),
                # High - Strong ideation
                CrisisPattern(
                    r"\b(suicidal|want\s+to\s+hurt\s+myself|self[\s-]?harm)\b",
                    CrisisSeverity.HIGH,
                    CrisisCategory.SELF_HARM,
                ),
                CrisisPattern(
                    r"\b(no\s+reason\s+to\s+live|life\s+isn't\s+worth|can't\s+go\s+on)\b",
                    CrisisSeverity.HIGH,
                    CrisisCategory.HOPELESSNESS,
                ),
                CrisisPattern(
                    r"\b(end\s+it\s+all|end\s+the\s+pain|make\s+it\s+stop)\b",
                    CrisisSeverity.HIGH,
                    CrisisCategory.INDIRECT_SUICIDAL,
                ),
                # High - Farewell indicators
                CrisisPattern(
                    r"\b(goodbye\s+forever|this\s+is\s+goodbye|final\s+goodbye)\b",
                    CrisisSeverity.HIGH,
                    CrisisCategory.FAREWELL,
                ),
                CrisisPattern(
                    r"\b(won't\s+be\s+around|see\s+you\s+on\s+the\s+other\s+side)\b",
                    CrisisSeverity.HIGH,
                    CrisisCategory.FAREWELL,
                ),
                # Moderate - Distress signals
                CrisisPattern(
                    r"\b(can't\s+take\s+it|can't\s+cope|breaking\s+point)\b",
                    CrisisSeverity.MODERATE,
                    CrisisCategory.HOPELESSNESS,
                    confidence_weight=0.8,
                ),
                CrisisPattern(
                    r"\b(wish\s+I\s+was\s+dead|rather\s+be\s+dead|death\s+sounds)\b",
                    CrisisSeverity.MODERATE,
                    CrisisCategory.DEATH_IDEATION,
                    confidence_weight=0.8,
                ),
                CrisisPattern(
                    r"\b(no\s+way\s+out|trapped|no\s+escape|hopeless)\b",
                    CrisisSeverity.MODERATE,
                    CrisisCategory.HOPELESSNESS,
                    confidence_weight=0.7,
                ),
                # Indirect/Metaphorical
                CrisisPattern(
                    r"\b(end\s+of\s+the\s+road|final\s+curtain|last\s+stop)\b",
                    CrisisSeverity.MODERATE,
                    CrisisCategory.INDIRECT_SUICIDAL,
                    is_direct=False,
                    confidence_weight=0.6,
                ),
                CrisisPattern(
                    r"\b(disappear\s+forever|cease\s+to\s+exist|fade\s+away)\b",
                    CrisisSeverity.MODERATE,
                    CrisisCategory.INDIRECT_SUICIDAL,
                    is_direct=False,
                    confidence_weight=0.6,
                ),
            ],
            "es": [  # Spanish
                CrisisPattern(
                    r"\b(quiero\s+morir|matarme|suicidarme|quitarme\s+la\s+vida)\b",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.SUICIDAL_IDEATION,
                    language="es",
                ),
                CrisisPattern(
                    r"\b(no\s+puedo\s+más|no\s+quiero\s+vivir|mejor\s+muerto)\b",
                    CrisisSeverity.HIGH,
                    CrisisCategory.HOPELESSNESS,
                    language="es",
                ),
                CrisisPattern(
                    r"\b(acabar\s+con\s+todo|terminar\s+con\s+esto)\b",
                    CrisisSeverity.HIGH,
                    CrisisCategory.INDIRECT_SUICIDAL,
                    language="es",
                ),
                CrisisPattern(
                    r"\b(sin\s+esperanza|desesperado|no\s+hay\s+salida)\b",
                    CrisisSeverity.MODERATE,
                    CrisisCategory.HOPELESSNESS,
                    language="es",
                ),
            ],
            "fr": [  # French
                CrisisPattern(
                    r"\b(je\s+veux\s+mourir|me\s+suicider|me\s+tuer|en\s+finir)\b",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.SUICIDAL_IDEATION,
                    language="fr",
                ),
                CrisisPattern(
                    r"\b(plus\s+de\s+raison\s+de\s+vivre|mieux\s+vaut\s+mourir)\b",
                    CrisisSeverity.HIGH,
                    CrisisCategory.HOPELESSNESS,
                    language="fr",
                ),
                CrisisPattern(
                    r"\b(désespéré|sans\s+espoir|ne\s+peux\s+plus)\b",
                    CrisisSeverity.MODERATE,
                    CrisisCategory.HOPELESSNESS,
                    language="fr",
                ),
            ],
            "zh": [  # Chinese Simplified
                CrisisPattern(
                    r"(我想死|自杀|结束生命|不想活)",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.SUICIDAL_IDEATION,
                    language="zh",
                ),
                CrisisPattern(
                    r"(活不下去|生不如死|没有希望)",
                    CrisisSeverity.HIGH,
                    CrisisCategory.HOPELESSNESS,
                    language="zh",
                ),
                CrisisPattern(
                    r"(绝望|撑不下去|崩溃)",
                    CrisisSeverity.MODERATE,
                    CrisisCategory.HOPELESSNESS,
                    language="zh",
                ),
            ],
            "de": [  # German
                CrisisPattern(
                    r"\b(ich\s+will\s+sterben|selbstmord|mich\s+umbringen|mich\s+töten)\b",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.SUICIDAL_IDEATION,
                    language="de",
                ),
                CrisisPattern(
                    r"\b(keinen\s+grund\s+zu\s+leben|hoffnungslos|verzweifelt)\b",
                    CrisisSeverity.HIGH,
                    CrisisCategory.HOPELESSNESS,
                    language="de",
                ),
            ],
            "pt": [  # Portuguese
                CrisisPattern(
                    r"\b(quero\s+morrer|me\s+matar|suicidar|tirar\s+minha\s+vida)\b",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.SUICIDAL_IDEATION,
                    language="pt",
                ),
                CrisisPattern(
                    r"\b(não\s+aguento\s+mais|sem\s+esperança|desesperado)\b",
                    CrisisSeverity.MODERATE,
                    CrisisCategory.HOPELESSNESS,
                    language="pt",
                ),
            ],
            "ja": [  # Japanese
                CrisisPattern(
                    r"(死にたい|自殺|消えたい|終わりにしたい)",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.SUICIDAL_IDEATION,
                    language="ja",
                ),
                CrisisPattern(
                    r"(生きる意味がない|希望がない|絶望)",
                    CrisisSeverity.HIGH,
                    CrisisCategory.HOPELESSNESS,
                    language="ja",
                ),
            ],
            "ar": [  # Arabic
                CrisisPattern(
                    r"(أريد أن أموت|انتحار|أقتل نفسي)",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.SUICIDAL_IDEATION,
                    language="ar",
                ),
                CrisisPattern(
                    r"(لا أمل|يائس|لا أستطيع الاستمرار)",
                    CrisisSeverity.HIGH,
                    CrisisCategory.HOPELESSNESS,
                    language="ar",
                ),
            ],
            "it": [  # Italian
                CrisisPattern(
                    r"\b(voglio\s+morire|suicidarmi|uccidermi|farla\s+finita)\b",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.SUICIDAL_IDEATION,
                    language="it",
                ),
                CrisisPattern(
                    r"\b(non\s+ce\s+la\s+faccio|disperato|senza\s+speranza)\b",
                    CrisisSeverity.MODERATE,
                    CrisisCategory.HOPELESSNESS,
                    language="it",
                ),
            ],
            "ko": [  # Korean
                CrisisPattern(
                    r"(죽고\s*싶|자살|삶을\s*끝내고\s*싶)",
                    CrisisSeverity.CRITICAL,
                    CrisisCategory.SUICIDAL_IDEATION,
                    language="ko",
                ),
                CrisisPattern(
                    r"(희망이\s*없|절망적|더\s*이상\s*못)",
                    CrisisSeverity.HIGH,
                    CrisisCategory.HOPELESSNESS,
                    language="ko",
                ),
            ],
        }

    @staticmethod
    def get_false_positive_patterns() -> List[str]:
        """Patterns that commonly trigger false positives"""
        return [
            # Exact idiom spans only. Never suppress an entire disclosure merely
            # because unrelated text mentions a joke, game, phone, or battery.
            r"\b(?:kill|killing)\s+time\b",
            r"\b(?:die|dying)\s+(?:laughing|of\s+(?:laughter|embarrassment|boredom))\b",
            r"\bto\s+die\s+for\b",
            r"\bdrop[\s-]?dead\s+gorgeous\b",
            r"\bkilling\s+it\b",
        ]


# ============================================================================
# DETECTOR INTERFACES
# ============================================================================


class BaseDetector(ABC):
    """Abstract base class for crisis detectors"""

    @abstractmethod
    async def detect(
        self, text: str, context: Optional[List[str]] = None
    ) -> CrisisDetectionResult:
        """Detect crisis indicators in text"""
        pass


class RegexDetector(BaseDetector):
    """High-performance regex-based crisis detection"""

    def __init__(self):
        self.patterns_db = PatternDatabase()
        self.patterns = self.patterns_db.get_patterns()
        self.false_positives = self.patterns_db.get_false_positive_patterns()
        self.compiled_false_positives = [
            re.compile(p, re.IGNORECASE) for p in self.false_positives
        ]

    async def detect(
        self, text: str, context: Optional[List[str]] = None
    ) -> CrisisDetectionResult:
        """Fast regex-based detection (<1ms target)"""
        start_time = time.time()

        # Remove only exact harmless idioms; continue checking the rest of the
        # same message so an idiom cannot veto a separate crisis disclosure.
        screened_text = COMPLETE_DENIAL_RE.sub("[explicit denial]", normalize_policy_text(text))
        for pattern in self.compiled_false_positives:
            screened_text = pattern.sub(" ", screened_text)
        had_idiom = screened_text != text

        # Detect language (simplified - in production, use proper language detection)
        language = self._detect_language(text)
        # Script detection is only a display hint. It must not decide which
        # safety patterns are eligible: mixed-language disclosures are common.
        patterns = [pattern for language_patterns in self.patterns.values()
                    for pattern in language_patterns]

        # Check patterns
        matched_patterns: List[Tuple[CrisisPattern, re.Match]] = []
        for pattern in patterns:
            regex = re.compile(pattern.pattern, re.IGNORECASE)
            if match := regex.search(screened_text):
                matched_patterns.append((pattern, match))

        # No matches
        if not matched_patterns:
            return CrisisDetectionResult(
                severity=CrisisSeverity.NONE,
                confidence=0.90,
                detection_method="regex_false_positive" if had_idiom else "regex_no_match",
                language=language,
                latency_ms=(time.time() - start_time) * 1000,
            )

        # Calculate severity and confidence
        max_severity = max(p.severity for p, _ in matched_patterns)
        language = next(p.language for p, _ in matched_patterns if p.severity == max_severity)
        categories = {p.category for p, _ in matched_patterns}
        indicators = [
            match.group() for _, match in matched_patterns[:5]
        ]  # Top 5 matches

        # Confidence based on pattern count and weights
        base_confidence = min(0.95, 0.6 + (len(matched_patterns) * 0.15))
        weighted_confidence = base_confidence * max(
            p.confidence_weight for p, _ in matched_patterns
        )

        # Determine action
        if max_severity >= CrisisSeverity.HIGH:
            action = RecommendedAction.INTERRUPT
            requires_resources = True
        elif max_severity == CrisisSeverity.MODERATE:
            action = RecommendedAction.MONITOR
            requires_resources = False
        else:
            action = RecommendedAction.PROCEED
            requires_resources = False

        return CrisisDetectionResult(
            severity=max_severity,
            confidence=weighted_confidence,
            indicators=indicators,
            categories=categories,
            requires_resources=requires_resources,
            recommended_action=action,
            detection_method=f"regex_{language}",
            language=language,
            latency_ms=(time.time() - start_time) * 1000,
        )

    def _is_false_positive(self, text: str) -> bool:
        """Check if text matches false positive patterns"""
        text_lower = text.lower()
        return any(
            pattern.search(text_lower) for pattern in self.compiled_false_positives
        )

    def _detect_language(self, text: str) -> str:
        """Simple language detection based on character sets"""
        # Simplified detection - in production, use proper library
        if re.search(r"[\u4e00-\u9fff]", text):  # Chinese characters
            return "zh"
        elif re.search(r"[\u0600-\u06ff]", text):  # Arabic
            return "ar"
        elif re.search(r"[\u3040-\u309f\u30a0-\u30ff]", text):  # Japanese
            return "ja"
        elif re.search(r"[\uac00-\ud7af]", text):  # Korean
            return "ko"
        # For European languages, would need more sophisticated detection
        return "en"  # Default to English


class MLDetector(BaseDetector):
    """Machine Learning based crisis detection (stub for actual implementation)"""

    def __init__(self, model_config: Optional[Dict] = None):
        self.config = model_config or {}
        self.tier1_timeout = self.config.get("tier1_timeout", 0.2)  # 200ms
        self.tier2_timeout = self.config.get("tier2_timeout", 0.4)  # 400ms

    async def detect(
        self, text: str, context: Optional[List[str]] = None
    ) -> CrisisDetectionResult:
        """ML-based detection with two-tier approach"""
        start_time = time.time()

        try:
            # Tier 1: Fast screening (e.g., Llama 3.1 8B)
            tier1_result = await self._tier1_screening(text)

            # If clearly safe, return immediately
            if tier1_result["classification"] == "SAFE":
                return CrisisDetectionResult(
                    severity=CrisisSeverity.NONE,
                    confidence=tier1_result.get("confidence", 0.85),
                    detection_method="ml_tier1_safe",
                    latency_ms=(time.time() - start_time) * 1000,
                )

            # Tier 2: Detailed analysis for CONCERN/CRISIS cases
            tier2_result = await self._tier2_analysis(text, context)

            return self._convert_ml_result(
                tier2_result, (time.time() - start_time) * 1000
            )

        except asyncio.TimeoutError:
            # Fallback on timeout
            return CrisisDetectionResult(
                severity=CrisisSeverity.MODERATE,  # Conservative fallback
                confidence=0.5,
                detection_method="ml_timeout_fallback",
                recommended_action=RecommendedAction.MONITOR,
                latency_ms=(time.time() - start_time) * 1000,
            )

    async def _tier1_screening(self, text: str) -> Dict:
        """Fast initial screening - implement with your ML service"""
        # This is a stub - implement with actual ML service
        await asyncio.sleep(0.1)  # Simulate network call
        return {"classification": "CONCERN", "confidence": 0.75}

    async def _tier2_analysis(self, text: str, context: Optional[List[str]]) -> Dict:
        """Detailed contextual analysis - implement with your ML service"""
        # This is a stub - implement with actual ML service
        await asyncio.sleep(0.2)  # Simulate network call
        return {
            "severity": "moderate",
            "confidence": 0.82,
            "suicidal_ideation": False,
            "self_harm_intent": False,
            "immediacy": "passive",
            "reasoning": "User expressing distress but no immediate danger",
        }

    def _convert_ml_result(
        self, ml_result: Dict, latency_ms: float
    ) -> CrisisDetectionResult:
        """Convert ML service result to standard format"""
        severity_map = {
            "none": CrisisSeverity.NONE,
            "low": CrisisSeverity.LOW,
            "moderate": CrisisSeverity.MODERATE,
            "high": CrisisSeverity.HIGH,
            "critical": CrisisSeverity.CRITICAL,
        }

        severity = severity_map.get(
            ml_result.get("severity", "none"), CrisisSeverity.NONE
        )

        action_map = {
            "none": RecommendedAction.PROCEED,
            "low": RecommendedAction.PROCEED,
            "moderate": RecommendedAction.MONITOR,
            "high": RecommendedAction.INTERRUPT,
            "critical": RecommendedAction.INTERRUPT,
        }

        return CrisisDetectionResult(
            severity=severity,
            confidence=ml_result.get("confidence", 0.5),
            requires_resources=severity >= CrisisSeverity.HIGH,
            recommended_action=action_map.get(
                ml_result.get("severity", "none"), RecommendedAction.PROCEED
            ),
            detection_method="ml_tier2",
            reasoning=ml_result.get("reasoning"),
            latency_ms=latency_ms,
        )


# ============================================================================
# CACHE MANAGER
# ============================================================================


class CacheManager:
    """In-memory cache for detection results"""

    def __init__(self, ttl_seconds: int = 300):  # 5 minutes default
        self.cache: Dict[str, Tuple[CrisisDetectionResult, datetime]] = {}
        self.ttl = timedelta(seconds=ttl_seconds)

    def get(self, key: str) -> Optional[CrisisDetectionResult]:
        """Get cached result if not expired"""
        if key in self.cache:
            result, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.ttl:
                # A cache read must not mutate the classification used by other
                # turns. Per-user state is applied after retrieval.
                return replace(
                    result, cache_hit=True,
                    indicators=list(result.indicators), categories=set(result.categories),
                )
            else:
                del self.cache[key]
        return None

    def set(self, key: str, result: CrisisDetectionResult):
        """Cache a result"""
        self.cache[key] = (
            replace(result, cache_hit=False,
                    indicators=list(result.indicators), categories=set(result.categories)),
            datetime.now(),
        )

    def create_key(self, text: str, context: Optional[List[str]] = None) -> str:
        """Create cache key from text and context"""
        # Structured encoding prevents text/context delimiter collisions. Keep
        # all supplied context because an installed ML detector can inspect it.
        content = json.dumps([text, context or []], ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(content.encode()).hexdigest()


# ============================================================================
# CIRCUIT BREAKER
# ============================================================================


class CircuitBreaker:
    """Track qualifying crisis evidence and a separate post-crisis latch.

    HIGH/CRITICAL opens immediately. Repeated MODERATE observations open at the
    configured threshold within the evidence window. The default latch never
    expires until reset at an explicit session boundary. ``never_expires=False``
    is an opt-in recovery mode, not the default wellness policy.
    """

    def __init__(
        self,
        threshold: int = 3,
        window_seconds: int = 1800,
        recovery_seconds: int = 900,
        never_expires: bool = True,
    ):
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
            raise ValueError("threshold must be a positive integer")
        if window_seconds <= 0 or recovery_seconds <= 0:
            raise ValueError("window and recovery must be positive")
        if not isinstance(never_expires, bool):
            raise ValueError("never_expires must be a boolean")
        self.threshold = threshold
        self.window = timedelta(seconds=window_seconds)
        self.recovery = timedelta(seconds=recovery_seconds)
        self.never_expires = never_expires
        self.states: Dict[str, UserCrisisState] = {}

    def _new_state(self, user_id: str) -> UserCrisisState:
        return UserCrisisState(user_id=user_id, never_expires=self.never_expires)

    def record_crisis(self, user_id: str, severity: CrisisSeverity) -> UserCrisisState:
        """Apply a classification to this user, independent of cache origin."""
        state = self.get_state(user_id)
        if not severity >= CrisisSeverity.MODERATE:
            return state
        now = datetime.now()
        # The evidence window applies before opening even in permanent mode.
        # Permanence describes the latch, not accumulation of unrelated history.
        if (not state.should_bypass_analysis() and state.window_started_time
                and now - state.window_started_time >= self.window):
            state.crisis_count = 0
            state.severity_history.clear()
            state.window_started_time = None
        if state.window_started_time is None:
            state.window_started_time = now

        state.crisis_count = min(state.crisis_count + 1, self.threshold)
        state.last_crisis_time = now
        state.severity_history.append(severity)
        state.severity_history = state.severity_history[-self.threshold:]
        if severity >= CrisisSeverity.HIGH or state.crisis_count >= self.threshold:
            state.state = CircuitState.OPEN
            state.post_crisis_latched = self.never_expires
        return state

    def get_state(self, user_id: str) -> UserCrisisState:
        """Apply opt-in recovery; the default permanent latch never decays."""
        if user_id not in self.states:
            self.states[user_id] = self._new_state(user_id)
        state = self.states[user_id]
        if (not state.never_expires and state.state == CircuitState.OPEN
                and state.last_crisis_time
                and datetime.now() - state.last_crisis_time >= self.recovery):
            state.state = CircuitState.HALF_OPEN
            state.post_crisis_latched = False
            state.crisis_count = 0
            state.severity_history.clear()
            state.window_started_time = None
        return state

    def reset(self, user_id: str):
        """Explicit session reset, retaining this breaker's configuration."""
        if user_id in self.states:
            self.states[user_id] = self._new_state(user_id)


# ============================================================================
# RESOURCE MANAGER
# ============================================================================


class ResourceManager:
    """Crisis resource management system"""

    def __init__(self):
        self.resources = self._load_resources()

    def _load_resources(self) -> Dict[str, List[CrisisResource]]:
        """Load comprehensive crisis resources database"""
        return {
            "US": [
                # Universal US Resources
                CrisisResource(
                    name="988 Suicide & Crisis Lifeline",
                    phone="988",
                    text="988",
                    web="https://988lifeline.org",
                    languages=["en", "es"],
                    priority=1
                ),
                CrisisResource(
                    name="Crisis Text Line",
                    text="HOME to 741741",
                    web="https://crisistextline.org",
                    languages=["en"],
                    priority=2
                ),
                CrisisResource(
                    name="SAMHSA National Helpline",
                    phone="1-800-662-4357",
                    web="https://samhsa.gov",
                    languages=["en", "es"],
                    priority=3
                ),
                CrisisResource(
                    name="National Domestic Violence Hotline",
                    phone="1-800-799-7233",
                    text="START to 22522",
                    web="https://thehotline.org",
                    languages=["en", "es"],
                    specialties=["domestic_violence"],
                    priority=4
                ),
                # Language-Specific Resources
                CrisisResource(
                    name="Línea de Crisis Hispana",
                    phone="1-888-628-9454",
                    web="https://suicidioprevencion.org",
                    languages=["es"],
                    priority=5
                ),
                CrisisResource(
                    name="Asian LifeNet Hotline",
                    phone="1-877-990-8585",
                    web="https://aalp.org/lifenet",
                    languages=["zh", "ko", "ja", "hi", "vi", "en"],
                    specialties=["asian_community"],
                    priority=6
                ),
                CrisisResource(
                    name="Mental Health Association for Chinese Communities",
                    phone="1-800-881-8502",
                    web="https://mhacc.org",
                    languages=["zh", "en"],
                    specialties=["chinese_community"],
                    priority=7
                ),
                # Community-Specific Resources
                CrisisResource(
                    name="Trevor Lifeline",
                    phone="1-866-488-7386",
                    text="START to 678678",
                    web="https://thetrevorproject.org",
                    languages=["en", "es"],
                    specialties=["lgbtq", "youth"],
                    priority=8
                ),
                CrisisResource(
                    name="Trans Lifeline",
                    phone="1-877-565-8860",
                    web="https://translifeline.org",
                    languages=["en", "es"],
                    specialties=["transgender"],
                    priority=9
                ),
                CrisisResource(
                    name="Veterans Crisis Line",
                    phone="1-800-273-8255",
                    text="838255",
                    web="https://veteranscrisisline.net",
                    languages=["en", "es"],
                    specialties=["veterans"],
                    priority=10
                ),
                CrisisResource(
                    name="StrongHearts Native Helpline",
                    phone="1-844-762-8483",
                    web="https://strongheartshelpline.org",
                    languages=["en"],
                    specialties=["native_american", "domestic_violence"],
                    priority=11
                ),
            ],

            # United Kingdom
            "GB": [
                CrisisResource(
                    name="Samaritans",
                    phone="116 123",
                    web="https://samaritans.org",
                    languages=["en"],
                    priority=1
                ),
                CrisisResource(
                    name="Shout Crisis Text Line",
                    text="SHOUT to 85258",
                    web="https://giveusashout.org",
                    languages=["en"],
                    priority=2
                ),
            ],
            "UK": [  # Alias for GB
                CrisisResource(
                    name="Samaritans",
                    phone="116 123",
                    web="https://samaritans.org",
                    languages=["en"],
                    priority=1
                ),
                CrisisResource(
                    name="Shout Crisis Text Line",
                    text="SHOUT to 85258",
                    web="https://giveusashout.org",
                    languages=["en"],
                    priority=2
                ),
            ],

            # Canada
            "CA": [
                CrisisResource(
                    name="Talk Suicide Canada",
                    phone="1-833-456-4566",
                    text="TALK to 45645",
                    web="https://talksuicide.ca",
                    languages=["en", "fr"],
                    priority=1
                ),
                CrisisResource(
                    name="Kids Help Phone",
                    phone="1-800-668-6868",
                    text="CONNECT to 686868",
                    web="https://kidshelpphone.ca",
                    languages=["en", "fr"],
                    specialties=["youth"],
                    priority=2
                ),
            ],

            # Australia
            "AU": [
                CrisisResource(
                    name="Lifeline Australia",
                    phone="13 11 14",
                    text="0477 13 11 14",
                    web="https://lifeline.org.au",
                    languages=["en"],
                    priority=1
                ),
            ],

            # France
            "FR": [
                CrisisResource(
                    name="3114 - Numéro National de Prévention du Suicide",
                    phone="3114",
                    web="https://3114.fr",
                    languages=["fr"],
                    priority=1
                ),
                CrisisResource(
                    name="SOS Amitié",
                    phone="09 72 39 40 50",
                    web="https://sos-amitie.com",
                    languages=["fr"],
                    priority=2
                ),
            ],

            # Germany
            "DE": [
                CrisisResource(
                    name="Telefonseelsorge",
                    phone="0800 111 0 111",
                    web="https://telefonseelsorge.de",
                    languages=["de"],
                    priority=1
                ),
                CrisisResource(
                    name="Nummer gegen Kummer",
                    phone="116 111",
                    web="https://nummergegenkummer.de",
                    languages=["de"],
                    specialties=["youth", "parents"],
                    priority=2
                ),
            ],

            # Spain
            "ES": [
                CrisisResource(
                    name="024 - Línea de Atención a la Conducta Suicida",
                    phone="024",
                    web="https://024.es",
                    languages=["es"],
                    priority=1
                ),
                CrisisResource(
                    name="Teléfono de la Esperanza",
                    phone="717 003 717",
                    web="https://telefonodelaesperanza.org",
                    languages=["es"],
                    priority=2
                ),
            ],

            # Italy
            "IT": [
                CrisisResource(
                    name="Telefono Amico Italia",
                    phone="02 2327 2327",
                    web="https://telefonoamico.it",
                    languages=["it"],
                    priority=1
                ),
            ],

            # Netherlands
            "NL": [
                CrisisResource(
                    name="113 Zelfmoordpreventie",
                    phone="113",
                    web="https://113.nl",
                    languages=["nl"],
                    priority=1
                ),
            ],

            # Belgium
            "BE": [
                CrisisResource(
                    name="Centre de Prévention du Suicide",
                    phone="0800 32 123",
                    web="https://preventionsuicide.be",
                    languages=["fr", "nl"],
                    priority=1
                ),
            ],

            # Austria
            "AT": [
                CrisisResource(
                    name="Telefonseelsorge Österreich",
                    phone="142",
                    web="https://telefonseelsorge.at",
                    languages=["de"],
                    priority=1
                ),
            ],

            # Switzerland
            "CH": [
                CrisisResource(
                    name="Die Dargebotene Hand",
                    phone="143",
                    web="https://143.ch",
                    languages=["de", "fr", "it"],
                    priority=1
                ),
            ],

            # Ireland
            "IE": [
                CrisisResource(
                    name="Samaritans Ireland",
                    phone="116 123",
                    web="https://samaritans.ie",
                    languages=["en"],
                    priority=1
                ),
            ],

            # Sweden
            "SE": [
                CrisisResource(
                    name="Mind Självmordslinjen",
                    phone="90101",
                    web="https://mind.se",
                    languages=["sv"],
                    priority=1
                ),
            ],

            # Denmark
            "DK": [
                CrisisResource(
                    name="Kirkens SOS",
                    phone="70 201 201",
                    web="https://kirkens-sos.dk",
                    languages=["da"],
                    priority=1
                ),
            ],

            # Norway
            "NO": [
                CrisisResource(
                    name="Mental Helse",
                    phone="116 123",
                    web="https://mentalhelse.no",
                    languages=["no"],
                    priority=1
                ),
            ],

            # Finland
            "FI": [
                CrisisResource(
                    name="Crisis Line",
                    phone="09 2525 0111",
                    web="https://mieli.fi",
                    languages=["fi", "sv"],
                    priority=1
                ),
            ],

            # Poland
            "PL": [
                CrisisResource(
                    name="Fundacja ITAKA",
                    phone="22 654 11 11",
                    web="https://itaka.org.pl",
                    languages=["pl"],
                    priority=1
                ),
            ],

            # Czech Republic
            "CZ": [
                CrisisResource(
                    name="Linka bezpečí",
                    phone="116 111",
                    web="https://linkabezpeci.cz",
                    languages=["cs"],
                    specialties=["youth"],
                    priority=1
                ),
            ],

            # Hungary
            "HU": [
                CrisisResource(
                    name="Kék Vonal",
                    phone="116 123",
                    web="https://kek-vonal.hu",
                    languages=["hu"],
                    priority=1
                ),
            ],

            # Japan
            "JP": [
                CrisisResource(
                    name="TELL Lifeline",
                    phone="03-5774-0992",
                    web="https://telljp.com",
                    languages=["en", "ja"],
                    priority=1
                ),
            ],

            # South Korea
            "KR": [
                CrisisResource(
                    name="Korea Suicide Prevention Center",
                    phone="1393",
                    web="https://spckorea.or.kr",
                    languages=["ko"],
                    priority=1
                ),
            ],

            # India
            "IN": [
                CrisisResource(
                    name="AASRA",
                    phone="91-22-27546669",
                    web="https://aasra.info",
                    languages=["en", "hi"],
                    priority=1
                ),
            ],

            # Singapore
            "SG": [
                CrisisResource(
                    name="Samaritans of Singapore",
                    phone="1767",
                    web="https://sos.org.sg",
                    languages=["en"],
                    priority=1
                ),
            ],

            # New Zealand
            "NZ": [
                CrisisResource(
                    name="Lifeline Aotearoa",
                    phone="0800 543 354",
                    text="HELP to 4357",
                    web="https://lifeline.org.nz",
                    languages=["en"],
                    priority=1
                ),
            ],

            # Mexico
            "MX": [
                CrisisResource(
                    name="Línea de la Vida",
                    phone="800 911 2000",
                    web="https://lineadelavida.gob.mx",
                    languages=["es"],
                    priority=1
                ),
            ],

            # Brazil
            "BR": [
                CrisisResource(
                    name="Centro de Valorização da Vida",
                    phone="188",
                    web="https://cvv.org.br",
                    languages=["pt"],
                    priority=1
                ),
            ],

            # Argentina
            "AR": [
                CrisisResource(
                    name="Centro de Asistencia al Suicida",
                    phone="135",
                    web="https://casbuenosaires.com.ar",
                    languages=["es"],
                    priority=1
                ),
            ],
        }

    def get_resources(
        self,
        country_code: str,
        language: str = "en",
        severity: CrisisSeverity = CrisisSeverity.HIGH,
    ) -> List[CrisisResource]:
        """Get appropriate resources for country and severity"""
        resources = self.resources.get(country_code, self.resources.get("US", []))

        # Filter by language support
        filtered = [
            r for r in resources if language in r.languages or "en" in r.languages
        ]

        # Sort by priority
        filtered.sort(key=lambda x: x.priority)

        # Return top 3 for high/critical, top 2 for moderate
        limit = 3 if severity >= CrisisSeverity.HIGH else 2
        return filtered[:limit]

    def format_resources(
        self,
        resources: List[CrisisResource],
        severity: CrisisSeverity,
        language: str = "en",
    ) -> str:
        """Format resources into response message"""
        templates = {
            "en": {
                CrisisSeverity.CRITICAL: "I'm very concerned about your safety. Please reach out for immediate support:",
                CrisisSeverity.HIGH: "I hear you're in pain. Please consider reaching out for support:",
                CrisisSeverity.MODERATE: "If you're feeling overwhelmed, support is available:",
            },
            "es": {
                CrisisSeverity.CRITICAL: "Estoy muy preocupado por tu seguridad. Por favor busca apoyo inmediato:",
                CrisisSeverity.HIGH: "Escucho que estás sufriendo. Por favor considera buscar apoyo:",
                CrisisSeverity.MODERATE: "Si te sientes abrumado, hay apoyo disponible:",
            },
        }

        intro = templates.get(language, templates["en"]).get(
            severity, "Support is available:"
        )

        lines = [intro, ""]
        for resource in resources:
            lines.append(f"• {resource.name}")
            if resource.phone:
                lines.append(f"  📞 Call: {resource.phone}")
            if resource.text:
                lines.append(f"  💬 Text: {resource.text}")
            if resource.web:
                lines.append(f"  🌐 Web: {resource.web}")
            lines.append("")

        return "\n".join(lines)


# ============================================================================
# ANALYTICS
# ============================================================================


class AnalyticsLogger:
    """Analytics and audit trail logging"""

    def __init__(self, buffer_size: int = 100):
        self.events = deque(maxlen=buffer_size)
        self.metrics = {
            "total_detections": 0,
            "crisis_detections": 0,
            "false_positives": 0,
            "cache_hits": 0,
            "avg_latency_ms": 0,
            "detections_by_severity": {s.label: 0 for s in CrisisSeverity},
        }

    async def log_detection(
        self, user_id: str, result: CrisisDetectionResult, message_excerpt: str
    ):
        """Log a crisis detection event"""
        # Hash user ID for privacy
        user_hash = hashlib.sha256(user_id.encode()).hexdigest()[:16]

        event = {
            "timestamp": datetime.now().isoformat(),
            "user_hash": user_hash,
            "severity": result.severity.label,
            "confidence": result.confidence,
            "categories": [c.value for c in result.categories],
            "action": result.recommended_action.value,
            "detection_method": result.detection_method,
            "language": result.language,
            "latency_ms": result.latency_ms,
            "cache_hit": result.cache_hit,
            "message_excerpt": message_excerpt[:100],  # First 100 chars only
        }

        self.events.append(event)
        self._update_metrics(result)

        # Log to file/database in production
        logger.info(f"Crisis detection: {event}")

    def _update_metrics(self, result: CrisisDetectionResult):
        """Update running metrics"""
        self.metrics["total_detections"] += 1

        if result.severity >= CrisisSeverity.MODERATE:
            self.metrics["crisis_detections"] += 1

        if result.cache_hit:
            self.metrics["cache_hits"] += 1

        self.metrics["detections_by_severity"][result.severity.label] += 1

        # Update rolling average latency
        current_avg = self.metrics["avg_latency_ms"]
        n = self.metrics["total_detections"]
        self.metrics["avg_latency_ms"] = (
            (current_avg * (n - 1)) + result.latency_ms
        ) / n

    def get_metrics(self) -> Dict:
        """Get current metrics"""
        return self.metrics.copy()


# ============================================================================
# MAIN SUPERVISOR
# ============================================================================


class CrisisDetectionSupervisor:
    """
    Reference crisis detection supervisor for template projects.

    Orchestrates multiple detection layers with caching, circuit breaking,
    and comprehensive analytics.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # Initialize components
        self.regex_detector = RegexDetector()
        self.ml_detector = MLDetector(self.config.get("ml_config"))
        self.cache_manager = CacheManager(ttl_seconds=self.config.get("cache_ttl", 300))
        self.circuit_breaker = CircuitBreaker(
            threshold=self.config.get("circuit_threshold", 3),
            window_seconds=self.config.get("circuit_window", 1800),
            recovery_seconds=self.config.get("circuit_recovery", 900),
            never_expires=self.config.get("never_expires", True),
        )
        self.resource_manager = ResourceManager()
        self.analytics = AnalyticsLogger()

        # Configuration
        self.enable_ml = self.config.get("enable_ml", True)
        self.target_latency_ms = self.config.get("target_latency_ms", 300)

    async def detect(
        self,
        text: str,
        user_id: str,
        context: Optional[List[str]] = None,
        country_code: str = "US",
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main detection entry point with full orchestration.

        Returns complete detection result with resources if needed.
        """
        start_time = time.time()

        # Check circuit breaker
        user_state = self.circuit_breaker.get_state(user_id)
        if user_state.should_bypass_analysis():
            # Go straight to resources
            return await self._create_crisis_response(
                user_id=user_id,
                severity=max(user_state.severity_history, key=lambda item: item.level),
                country_code=country_code,
                language=language or "en",
                bypassed=True,
            )

        # Check cache
        cache_key = self.cache_manager.create_key(text, context)
        cached_result = self.cache_manager.get(cache_key)
        if cached_result:
            return await self._apply_result(
                cached_result, text, user_id, country_code, language,
            )

        # Failed/late peers cannot discard completed positive detections.
        if self.enable_ml:
            results, complete = await self._run_detectors(text, context)
            if not complete:
                # Unknown detector coverage is not evidence of low risk. Keep
                # all positive signals and mark the partial result explicitly.
                results.append(self._create_fallback_result())
            final_result = self._fuse_results(results)
            if not complete:
                final_result.context_modifier = "partial_detection"
        else:
            final_result = await self.regex_detector.detect(text, context)
            complete = True

        # Update latency
        final_result.latency_ms = (time.time() - start_time) * 1000

        # Do not reuse a result produced while a detector was unavailable.
        if complete:
            self.cache_manager.set(cache_key, final_result)

        return await self._apply_result(
            final_result, text, user_id, country_code, language,
        )

    async def _run_detectors(
        self, text: str, context: Optional[List[str]],
    ) -> Tuple[List[CrisisDetectionResult], bool]:
        """Collect peers independently and drain cooperative cancellation.

        The detection deadline plus a 50ms cleanup budget bounds waiting on a
        late peer. Python cannot forcibly terminate cancellation-resistant code;
        such a task is detached with an exception-consuming callback and its
        result cannot populate the shared cache.
        """
        tasks = [
            asyncio.create_task(self.regex_detector.detect(text, context)),
            asyncio.create_task(self.ml_detector.detect(text, context)),
        ]
        completed = set()
        try:
            completed, _ = await asyncio.wait(
                tasks, timeout=max(0, self.target_latency_ms) / 1000,
            )
        finally:
            pending = [task for task in tasks if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                _, resistant = await asyncio.wait(pending, timeout=0.05)
                for task in resistant:
                    task.cancel()
                    task.add_done_callback(self._consume_task_outcome)
            # Consume every already-finished exception, including completion
            # during cancellation cleanup, so no task warning leaks out.
            for task in tasks:
                if task.done() and task not in completed:
                    self._consume_task_outcome(task)

        results = []
        for task in tasks:
            if task not in completed or task.cancelled():
                continue
            try:
                result = task.result()
            except Exception:
                logger.warning("Crisis detector unavailable; retaining other detector results")
                continue
            if not isinstance(result, CrisisDetectionResult):
                logger.warning("Crisis detector returned invalid result")
                continue
            results.append(result)
        return results, len(results) == len(tasks)

    @staticmethod
    def _consume_task_outcome(task: asyncio.Task) -> None:
        if not task.cancelled():
            task.exception()

    async def _apply_result(
        self, result: CrisisDetectionResult, text: str, user_id: str,
        country_code: str, language: Optional[str],
    ) -> Dict[str, Any]:
        """Every classification, including cache hits, crosses this boundary."""
        # Transition before any await so logging cannot prevent the latch.
        state = self.circuit_breaker.record_crisis(user_id, result.severity)
        if state.should_bypass_analysis() and not result.requires_resources:
            # A repeated-MODERATE threshold can require resources without
            # claiming that the current message was classified HIGH.
            result = replace(result, requires_resources=True,
                             recommended_action=RecommendedAction.INTERRUPT)
        try:
            await self.analytics.log_detection(user_id, result, text)
        except Exception:
            logger.warning("Crisis analytics unavailable; returning safety decision")
        return self._format_response(result, user_id, country_code, language)

    def _fuse_results(
        self, results: List[CrisisDetectionResult]
    ) -> CrisisDetectionResult:
        """Fuse multiple detection results into final decision"""
        if not results:
            return self._create_fallback_result()

        # Get highest severity
        max_severity = max(r.severity for r in results)

        # Confidence belongs to the selected severity, not a contradictory
        # lower-severity detector with a larger uncalibrated score.
        max_confidence = max(r.confidence for r in results if r.severity == max_severity)

        # Combine indicators and categories
        all_indicators = []
        all_categories = set()
        for r in results:
            all_indicators.extend(r.indicators)
            all_categories.update(r.categories)

        # No detector may erase a stronger positive crisis signal. Preserve
        # provenance for review rather than treating ML confidence as veto power.
        reasoning = "; ".join(
            f"{r.detection_method}: {r.severity.label} ({r.confidence:.3f})"
            + (f"; {r.reasoning}" if r.reasoning else "")
            for r in results
        )

        # Determine action
        if max_severity >= CrisisSeverity.HIGH:
            action = RecommendedAction.INTERRUPT
            requires_resources = True
        elif max_severity == CrisisSeverity.MODERATE:
            action = RecommendedAction.MONITOR
            requires_resources = False
        else:
            action = RecommendedAction.PROCEED
            requires_resources = False

        return CrisisDetectionResult(
            severity=max_severity,
            confidence=max_confidence,
            indicators=all_indicators[:5],  # Top 5
            categories=all_categories,
            requires_resources=requires_resources,
            recommended_action=action,
            detection_method="fusion",
            reasoning=reasoning,
        )

    def _create_fallback_result(self) -> CrisisDetectionResult:
        """Create safe fallback result on error"""
        return CrisisDetectionResult(
            severity=CrisisSeverity.MODERATE,
            confidence=0.5,
            recommended_action=RecommendedAction.MONITOR,
            detection_method="fallback",
        )

    async def _create_crisis_response(
        self,
        user_id: str,
        severity: CrisisSeverity,
        country_code: str,
        language: str,
        bypassed: bool = False,
    ) -> Dict:
        """Create crisis response with resources"""
        resources = self.resource_manager.get_resources(
            country_code, language, severity
        )
        message = self.resource_manager.format_resources(resources, severity, language)

        return {
            "detection": {
                # No new text classification was performed on a latched turn.
                "severity": None if bypassed else severity.label,
                "prior_severity": severity.label if bypassed else None,
                "action": RecommendedAction.INTERRUPT.value,
                "bypassed_analysis": bypassed,
                "basis": "crisis_history" if bypassed else "current_classification",
            },
            "resources": [
                {"name": r.name, "phone": r.phone, "text": r.text, "web": r.web}
                for r in resources
            ],
            "message": message,
            "user_state": {
                "circuit_state": self.circuit_breaker.get_state(user_id).state.value
            },
        }

    def _format_response(
        self,
        result: CrisisDetectionResult,
        user_id: str,
        country_code: str,
        language: Optional[str],
    ) -> Dict:
        """Format final response"""
        response = {
            "detection": {
                "severity": result.severity.label,
                "confidence": result.confidence,
                "action": result.recommended_action.value,
                "categories": [c.value for c in result.categories],
                "latency_ms": result.latency_ms,
                "cache_hit": result.cache_hit,
                "method": result.detection_method,
                "coverage": result.context_modifier or "complete",
            }
        }

        # Add reasoning if available
        if result.reasoning:
            response["detection"]["reasoning"] = result.reasoning

        # Add resources if needed
        if result.requires_resources:
            lang = language or result.language
            resources = self.resource_manager.get_resources(
                country_code, lang, result.severity
            )
            response["resources"] = [
                {"name": r.name, "phone": r.phone, "text": r.text, "web": r.web}
                for r in resources
            ]
            response["message"] = self.resource_manager.format_resources(
                resources, result.severity, lang
            )

        # Add user state
        response["user_state"] = {
            "circuit_state": self.circuit_breaker.get_state(user_id).state.value
        }

        # Add metrics
        response["metrics"] = self.analytics.get_metrics()

        return response


# ============================================================================
# DEMO AND TESTING
# ============================================================================


async def main():
    """Demonstrate the crisis detection system"""

    print("=" * 80)
    print("CRISIS DETECTION SUPERVISOR - PRODUCTION ARCHITECTURE DEMO")
    print("=" * 80)

    # Initialize supervisor
    supervisor = CrisisDetectionSupervisor(
        {
            "enable_ml": True,  # Set to False to use regex only
            "target_latency_ms": 300,
            "cache_ttl": 300,
            "circuit_threshold": 3,
        }
    )

    # Test cases
    test_cases = [
        ("I want to kill myself", "user1", "Critical - Direct suicidal ideation"),
        ("This deadline is killing me", "user2", "False positive - should not trigger"),
        (
            "I can't take this anymore, I want to die",
            "user3",
            "High severity - multiple indicators",
        ),
        ("Je veux mourir", "user4", "French - I want to die"),
        ("我想死", "user5", "Chinese - I want to die"),
        ("I'm feeling stressed about work", "user6", "Normal stress - no crisis"),
        ("Goodbye everyone, this is my last message", "user7", "Farewell indicator"),
        ("I'm at my breaking point", "user8", "Moderate distress"),
    ]

    print("\n" + "=" * 80)
    print("TESTING CRISIS DETECTION")
    print("=" * 80)

    for text, user_id, description in test_cases:
        print(f"\n{'─' * 60}")
        print(f"Test: {description}")
        print(f"User: {user_id}")
        print(f'Text: "{text}"')
        print(f"{'─' * 60}")

        result = await supervisor.detect(text=text, user_id=user_id, country_code="US")

        detection = result["detection"]
        print(f"Severity: {detection['severity'].upper()}")
        print(f"Confidence: {detection['confidence']:.2%}")
        print(f"Action: {detection['action']}")
        print(f"Latency: {detection['latency_ms']:.1f}ms")
        print(f"Method: {detection['method']}")

        if detection.get("categories"):
            print(f"Categories: {', '.join(detection['categories'])}")

        if result.get("resources"):
            print(f"\n🚨 CRISIS RESOURCES PROVIDED:")
            print(result.get("message", ""))

        # Circuit state
        print(f"Circuit State: {result['user_state']['circuit_state']}")

    # Test circuit breaker
    print("\n" + "=" * 80)
    print("TESTING CIRCUIT BREAKER")
    print("=" * 80)

    print("\nSimulating repeated crisis events for user...")

    crisis_user = "crisis_test_user"
    crisis_messages = [
        "I want to end it all",
        "I can't go on",
        "This is too much, I want to die",
    ]

    for i, msg in enumerate(crisis_messages):
        print(f'\nMessage {i + 1}: "{msg}"')
        result = await supervisor.detect(msg, crisis_user, country_code="US")
        print(f"Circuit State: {result['user_state']['circuit_state']}")
        print(
            f"Bypassed Analysis: {result['detection'].get('bypassed_analysis', False)}"
        )

    # Show analytics
    print("\n" + "=" * 80)
    print("ANALYTICS SUMMARY")
    print("=" * 80)

    metrics = supervisor.analytics.get_metrics()
    print(f"\nTotal Detections: {metrics['total_detections']}")
    print(f"Crisis Detections: {metrics['crisis_detections']}")
    print(
        f"Cache Hit Rate: {metrics['cache_hits'] / max(1, metrics['total_detections']):.1%}"
    )
    print(f"Avg Latency: {metrics['avg_latency_ms']:.1f}ms")
    print("\nDetections by Severity:")
    for severity, count in metrics["detections_by_severity"].items():
        if count > 0:
            print(f"  {severity}: {count}")


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════════════╗
║     CRISIS DETECTION SUPERVISOR                                    ║
║                                                                    ║
║                                                                    ║
║  Features:                                                         ║
║  • Regex patterns (multi-language examples)                       ║
║  • ML detection (two-tier: screening + analysis)                  ║
║  • Circuit breaker (prevents overload from repeated crises)       ║
║  • Result caching (SHA-256 based, 5min TTL)                       ║
║  • State management (tracks user crisis history)                  ║
║  • Resource database (50+ countries, multiple contact methods)    ║
║                                                                    ║
║  Architecture:                                                     ║
║  Tier 0: Regex patterns (<1ms)                                    ║
║  Tier 1: Fast ML screening (100-200ms)                            ║
║  Tier 2: Contextual analysis (200-400ms)                          ║
║                                                                    ║
║  This is a community example demonstrating the architecture.       ║
║  Customize detectors, resources, and models for your use case.    ║
╚════════════════════════════════════════════════════════════════════╝
    """)

    asyncio.run(main())
