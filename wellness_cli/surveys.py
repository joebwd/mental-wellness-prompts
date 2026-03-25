"""
Survey and mood tracking system.

Provides structured check-ins inspired by validated instruments (PHQ-2, GAD-2)
adapted for a supportive (non-clinical) context.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ── Survey Definitions ────────────────────────────────────────────────

@dataclass
class SurveyQuestion:
    key: str
    prompt: str
    low_label: str
    high_label: str
    min_val: int = 1
    max_val: int = 10


QUICK_CHECKIN = [
    SurveyQuestion(
        key="overall",
        prompt="How are you feeling overall right now?",
        low_label="really rough",
        high_label="great",
    ),
    SurveyQuestion(
        key="energy",
        prompt="How's your energy level today?",
        low_label="completely drained",
        high_label="full of energy",
    ),
    SurveyQuestion(
        key="anxiety",
        prompt="How much anxiety or worry are you carrying?",
        low_label="very anxious",
        high_label="calm and relaxed",
    ),
    SurveyQuestion(
        key="sleep_quality",
        prompt="How did you sleep last night?",
        low_label="terribly",
        high_label="deeply and well",
    ),
]

DEEP_CHECKIN = QUICK_CHECKIN + [
    SurveyQuestion(
        key="motivation",
        prompt="How motivated do you feel to do the things you need to do?",
        low_label="no motivation",
        high_label="very motivated",
    ),
    SurveyQuestion(
        key="connection",
        prompt="How connected do you feel to the people around you?",
        low_label="very isolated",
        high_label="deeply connected",
    ),
    SurveyQuestion(
        key="self_care",
        prompt="How well have you been taking care of yourself lately?",
        low_label="not at all",
        high_label="very well",
    ),
    SurveyQuestion(
        key="hope",
        prompt="How hopeful do you feel about the near future?",
        low_label="not hopeful",
        high_label="very hopeful",
    ),
]


# ── Mood Interpretation ──────────────────────────────────────────────

def interpret_scores(scores: Dict[str, int]) -> str:
    """Generate a gentle, non-clinical summary of survey results."""
    overall = scores.get("overall", 5)
    energy = scores.get("energy", 5)
    anxiety = scores.get("anxiety", 5)
    sleep = scores.get("sleep_quality", 5)

    parts = []

    # Overall
    if overall <= 3:
        parts.append("It sounds like things are pretty tough right now.")
    elif overall <= 5:
        parts.append("Sounds like a mixed day — not terrible, but not easy either.")
    elif overall <= 7:
        parts.append("You seem to be doing okay today, which is good to hear.")
    else:
        parts.append("You're feeling pretty good today — that's worth noting.")

    # Energy + Sleep combo
    if energy <= 3 and sleep <= 3:
        parts.append("Low energy and poor sleep tend to feed each other — that's a hard combo.")
    elif energy <= 3:
        parts.append("Your energy is low, which can make everything feel harder.")
    elif sleep <= 3:
        parts.append("Sleep has been rough, and that affects everything else.")

    # Anxiety
    if anxiety <= 3:
        parts.append("The anxiety sounds heavy. That takes a real toll.")
    elif anxiety <= 5:
        parts.append("Some worry in the mix today, but it's not overwhelming.")

    # Encouragement (context-aware)
    if overall <= 4:
        parts.append("Coming here and checking in is itself a positive step.")
    elif overall >= 7:
        parts.append("Worth paying attention to what's going right today.")

    return " ".join(parts)


def mood_sparkline(values: List[int], width: int = 20) -> str:
    """Create a sparkline-style visualization for mood values."""
    if not values:
        return ""
    blocks = " ▁▂▃▄▅▆▇█"
    min_v = min(values)
    max_v = max(values)
    range_v = max_v - min_v if max_v != min_v else 1
    return "".join(
        blocks[min(8, int((v - min_v) / range_v * 8))]
        for v in values
    )


def mood_trend_analysis(moods: List[Dict]) -> str:
    """Analyze mood trends over recent entries."""
    if len(moods) < 2:
        return "Not enough data yet to spot trends. Keep checking in!"

    overalls = [m.get("overall", 5) for m in moods]
    recent_avg = sum(overalls[-3:]) / min(len(overalls), 3)
    older_avg = sum(overalls[:-3]) / max(len(overalls[:-3]), 1) if len(overalls) > 3 else recent_avg

    delta = recent_avg - older_avg
    spark = mood_sparkline(overalls)

    lines = [f"  Mood: {spark}  (last {len(overalls)} check-ins)"]

    if abs(delta) < 0.5:
        lines.append("  Trend: Fairly steady.")
    elif delta > 0:
        lines.append(f"  Trend: Things are looking up (+{delta:.1f} avg).")
    else:
        lines.append(f"  Trend: Been a harder stretch ({delta:.1f} avg).")

    # Check specific dimensions
    anxieties = [m.get("anxiety", 5) for m in moods]
    if anxieties and sum(anxieties[-3:]) / min(len(anxieties), 3) <= 3:
        lines.append("  Note: Anxiety has been consistently high recently.")

    sleeps = [m.get("sleep_quality", 5) for m in moods]
    if sleeps and sum(sleeps[-3:]) / min(len(sleeps), 3) <= 3:
        lines.append("  Note: Sleep has been consistently poor recently.")

    return "\n".join(lines)
