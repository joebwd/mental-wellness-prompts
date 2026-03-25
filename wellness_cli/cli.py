"""
Rich CLI interface with a mascot-driven, cozy terminal aesthetic.

Design language:
  - Moss / honey / blossom palette
  - A simple mascot that shows up in startup and loading states
  - Rounded surfaces and badge-based hierarchy
  - Light motion only where it adds feedback
"""

import queue
import re
import sys
import threading
import time
from typing import Callable, Dict, Generator, List, Optional

from rich.cells import cell_len
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.measure import Measurement
from rich.padding import Padding
from rich.panel import Panel
from rich.segment import Segment
from rich.text import Text
from rich.table import Table
from rich.prompt import Prompt, IntPrompt
from rich.style import Style
from rich.box import ROUNDED, HEAVY
from rich.progress import Progress, SpinnerColumn, TextColumn

from .db import WellnessDB, MoodEntry
from .surveys import (
    QUICK_CHECKIN, DEEP_CHECKIN, SurveyQuestion,
    interpret_scores, mood_sparkline, mood_trend_analysis,
)


# ── Surface Styles ──────────────────────────────────────────────────

RETRO_BOX = ROUNDED
THICK_BOX = HEAVY


# ── Color Palette ────────────────────────────────────────────────────

COLORS = {
    "primary":    "#a8d683",
    "primary_dim":"#79a85b",
    "green":      "#c9e9a8",
    "green_dim":  "#9bcf75",
    "green_dark": "#25361d",
    "amber":      "#f4c67b",
    "amber_dim":  "#d99f4f",
    "accent":     "#f2a7a0",
    "white":      "#fff8ee",
    "text":       "#efe5d5",
    "dim":        "#c7b7a1",
    "faint":      "#7c6d5f",
    "border":     "#5c4d40",
    "surface":    "#1d1916",
    "surface_alt":"#28231f",
    "crisis":     "#ff8fab",
    "crisis_dim": "#cb5b79",
    "hp_high":    "#9bcf75",
    "hp_mid":     "#f4c67b",
    "hp_low":     "#ff8fab",
    "user_text":  "#fff1d4",
    "ai_text":    "#edf7de",
    "ai_border":  "#95c86d",
    "prompt":     "#f4c67b",
}

S = {
    "green":      Style(color=COLORS["green"], bold=True),
    "green_dim":  Style(color=COLORS["green_dim"]),
    "amber":      Style(color=COLORS["amber"], bold=True),
    "amber_dim":  Style(color=COLORS["amber_dim"]),
    "text":       Style(color=COLORS["text"]),
    "dim":        Style(color=COLORS["dim"]),
    "faint":      Style(color=COLORS["faint"]),
    "white":      Style(color=COLORS["white"]),
    "crisis":     Style(color=COLORS["crisis"], bold=True),
    "user":       Style(color=COLORS["user_text"]),
    "ai":         Style(color=COLORS["ai_text"]),
    "border":     Style(color=COLORS["border"]),
    "prompt":     Style(color=COLORS["prompt"], bold=True),
    "header":     Style(color=COLORS["white"], bold=True),
    "accent":     Style(color=COLORS["accent"], bold=True),
    "warm":       Style(color=COLORS["amber"]),
    "soft":       Style(color=COLORS["primary"]),
    "calm":       Style(color=COLORS["green"]),
    "success":    Style(color=COLORS["hp_high"], bold=True),
    "panel_text": Style(color=COLORS["text"]),
}

console = Console(highlight=False)


# ── Brand System ────────────────────────────────────────────────────

BRAND_NAME = "Moss"
BRAND_SUBTITLE = "mental wellness companion"
BRAND_TAGLINE = "A tiny moss sprite for calmer check-ins, reflection, and memory."
BRAND_BLURB = "Soft on the eyes, local by default, and built to keep the thread warm between conversations."
BRAND_COMMANDS = ("moss",)

MASCOT_IDLE = [
    "   \\|/",
    "  `-*-'",
    "  (o o)",
    "  /)_(\\",
    '   " "',
]

MASCOT_THINKING = [
    [
        "   \\|/",
        "  `-*-'",
        "  (o o)",
        "  /)_(\\",
        '   " "',
    ],
    [
        "   .|.",
        "  `-*-'",
        "  (o o)",
        "  /)_(\\",
        '   " "',
    ],
    [
        "   /|\\",
        "  `-*-'",
        "  (o o)",
        "  /)_(\\",
        '   " "',
    ],
    [
        "   .|.",
        "  `-*-'",
        "  (- -)",
        "  /)_(\\",
        '   " "',
    ],
]

MASCOT_REPLY = [
    "   \\|/",
    "  `-*-'",
    "  (^ ^)",
    "  /)_(\\",
    '   " "',
]

THINKING_LINES = [
    "gathering a gentle reply",
    "sorting through the thread",
    "finding the steady words",
    "keeping your place warm",
]

PROCESSING_LINES = [
    "tucking this conversation into memory",
    "pressing the useful details flat",
    "watering the profile notes",
    "leaving the room tidy",
]

WORDMARK_FRAMES = [
    ("  ", "  ", COLORS["primary"]),
    ("(", ")", COLORS["amber"]),
    ("<", ">", COLORS["accent"]),
    ("{", "}", COLORS["green_dim"]),
    ("<", ">", COLORS["accent"]),
    ("(", ")", COLORS["amber"]),
]

WORDMARK_BLIPS = ["~", "~~", "~~~", " ~~", "  ~", " ~~"]

FOOTER_PULSE_FRAMES = [
    "o....",
    "oo...",
    ".oo..",
    "..oo.",
    "...oo",
    "....o",
]

FOOTER_LINES = {
    "thinking": [
        "roots listening in real time",
        "leafing through the thread",
        "sprouting the next sentence",
        "keeping the canopy lively",
    ],
    "processing": [
        "packing away the useful bits",
        "pressing notes into the moss bed",
        "watering the long-term memory",
        "tidying the trail behind the turn",
    ],
}


# ── Screen Control ───────────────────────────────────────────────────

def clear_screen():
    """Clear the terminal — fresh screen, no scrollback clutter."""
    console.clear()


# ── Layout Helpers ───────────────────────────────────────────────────

def _content_width(max_width: int = 88, margin: int = 6) -> int:
    return max(24, min(max_width, console.width - margin))


def _tone_color(tone: str) -> str:
    return {
        "primary": COLORS["primary_dim"],
        "success": COLORS["green_dim"],
        "warning": COLORS["amber"],
        "accent": COLORS["accent"],
        "danger": COLORS["crisis"],
        "muted": COLORS["border"],
    }.get(tone, COLORS["border"])


def _badge(label: str, tone: str = "primary") -> Text:
    bg = {
        "primary": COLORS["primary"],
        "success": COLORS["green_dim"],
        "warning": COLORS["amber"],
        "accent": COLORS["accent"],
        "danger": COLORS["crisis"],
        "muted": COLORS["faint"],
    }.get(tone, COLORS["primary"])
    fg = COLORS["surface"] if tone != "muted" else COLORS["white"]
    return Text(f" {label.upper()} ", style=Style(color=fg, bgcolor=bg, bold=True))


def _panel_title(label: str, tone: str = "primary", trailing: Optional[str] = None) -> Text:
    title = Text()
    badge = _badge(label, tone)
    title.append(badge.plain, style=badge.style)
    if trailing:
        title.append(f" {trailing}", style=S["dim"])
    return title


def _inline_badges(items: List[tuple[str, str]]) -> Text:
    row = Text()
    for idx, (label, tone) in enumerate(items):
        if idx:
            row.append(" ")
        badge = _badge(label, tone)
        row.append(badge.plain, style=badge.style)
    return row


def _surface_panel(
    renderable,
    title: Optional[str] = None,
    tone: str = "primary",
    width: Optional[int] = None,
    padding: tuple[int, int] = (1, 2),
    box_style=ROUNDED,
    title_align: str = "left",
    expand: bool = False,
):
    return Panel(
        renderable,
        title=_panel_title(title, tone) if title else None,
        title_align=title_align,
        box=box_style,
        border_style=Style(color=_tone_color(tone)),
        padding=padding,
        width=width,
        expand=expand,
    )


def _render_mascot(lines: List[str], mood: str = "idle") -> Text:
    line_colors = {
        "idle": [COLORS["primary"], COLORS["primary_dim"], COLORS["white"], COLORS["green"], COLORS["dim"]],
        "thinking": [COLORS["amber"], COLORS["primary"], COLORS["white"], COLORS["green"], COLORS["dim"]],
        "reply": [COLORS["green"], COLORS["green_dim"], COLORS["white"], COLORS["green"], COLORS["dim"]],
        "processing": [COLORS["amber"], COLORS["accent"], COLORS["white"], COLORS["green"], COLORS["dim"]],
    }.get(mood, [COLORS["primary"]] * 5)

    art = Text()
    for idx, line in enumerate(lines):
        if idx:
            art.append("\n")
        art.append(line, style=Style(color=line_colors[min(idx, len(line_colors) - 1)], bold=idx < 3))
    return art


def _split_panel_with_mascot(
    mascot: Text,
    content,
    mascot_width: int = 10,
):
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(width=mascot_width)
    grid.add_column(ratio=1)
    grid.add_row(mascot, content)
    return grid


class _RightTaggedPanel:
    """Panel variant with a right-aligned bottom tag and an unbroken footer line."""

    def __init__(
        self,
        renderable,
        *,
        tag_label: str,
        tag_style,
        width: int,
        border_style,
        box=ROUNDED,
        padding: tuple[int, int] = (0, 1),
    ) -> None:
        self.renderable = renderable
        self.tag_label = tag_label
        self.tag_style = tag_style
        self.width = width
        self.border_style = border_style
        self.box = box
        self.padding = padding

    def __rich_measure__(self, console, options) -> Measurement:
        width = min(options.max_width, self.width)
        return Measurement(width, width)

    def __rich_console__(self, console, options):
        width = min(options.max_width, self.width)
        box = self.box.substitute(options, safe=console.safe_box)
        border_style = console.get_style(self.border_style)
        renderable = Padding(self.renderable, self.padding) if any(self.padding) else self.renderable
        child_options = options.update(width=width - 2, highlight=False)
        lines = console.render_lines(renderable, child_options)

        yield Segment(box.get_top([width - 2]), border_style)
        yield Segment.line()

        for line in lines:
            yield Segment(box.mid_left, border_style)
            yield from line
            yield Segment(box.mid_right, border_style)
            yield Segment.line()

        tag_label = self.tag_label.replace("\n", " ").expandtabs()
        max_label_width = max(1, width - 5)
        if cell_len(tag_label) > max_label_width:
            tag_text = Text(tag_label)
            tag_text.truncate(max_label_width)
            tag_label = tag_text.plain

        fill_width = max(0, width - 5 - cell_len(tag_label))
        yield Segment(box.bottom_left, border_style)
        if fill_width:
            yield Segment(box.bottom * fill_width, border_style)
        yield Segment(" ", self.tag_style)
        yield Segment(tag_label, self.tag_style)
        yield Segment(" ", self.tag_style)
        yield Segment(box.bottom, border_style)
        yield Segment(box.bottom_right, border_style)
        yield Segment.line()


def _animated_wordmark(frame_idx: int) -> Text:
    left, right, accent = WORDMARK_FRAMES[frame_idx % len(WORDMARK_FRAMES)]
    blip = WORDMARK_BLIPS[frame_idx % len(WORDMARK_BLIPS)]

    text = Text()
    text.append(left, style=Style(color=accent, bold=True))
    text.append("moss", style=Style(color=COLORS["primary"], bold=True))
    text.append(right, style=Style(color=accent, bold=True))
    text.append("  ")
    text.append(blip, style=S["faint"])
    return text


def _animated_footer(frame_idx: int, mode: str = "thinking") -> Text:
    pulse = FOOTER_PULSE_FRAMES[frame_idx % len(FOOTER_PULSE_FRAMES)]
    caption_pool = FOOTER_LINES.get(mode, FOOTER_LINES["thinking"])
    caption = caption_pool[frame_idx % len(caption_pool)]

    text = Text()
    text.append(pulse, style=Style(color=COLORS["primary_dim"], bold=True))
    text.append("  ", style=S["faint"])
    text.append(caption, style=S["faint"])
    return text


def _metric_text(items: List[tuple[str, int]]) -> Text:
    text = Text()
    for idx, (label, value) in enumerate(items):
        if idx:
            text.append("  •  ", style=S["faint"])
        text.append(str(value), style=Style(color=COLORS["white"], bold=True))
        text.append(f" {label}", style=S["dim"])
    return text


def _score_color(val: int) -> str:
    if val <= 3:
        return COLORS["hp_low"]
    if val <= 6:
        return COLORS["hp_mid"]
    return COLORS["hp_high"]


def _score_bar(val: int, total: int = 10) -> str:
    return "█" * val + "·" * max(0, total - val)


def _progress_bar(step: int, total_steps: int, width: int = 18) -> str:
    filled = min(width, int((step / max(total_steps, 1)) * width))
    return "●" * filled + "·" * max(0, width - filled)


def show_notice(message: str, tone: str = "muted"):
    labels = {
        "success": "Ready",
        "warning": "Heads up",
        "danger": "Urgent",
        "accent": "Info",
        "primary": "Info",
        "muted": "Note",
    }
    line = Text()
    badge = _badge(labels.get(tone, "Note"), tone)
    line.append(badge.plain, style=badge.style)
    line.append(
        f" {message}",
        style=S["text"] if tone in {"success", "warning", "danger", "accent", "primary"} else S["dim"],
    )
    console.print(line)


def show_provider_status(provider_name: str, model: str):
    line = Text()
    badge = _badge(provider_name, "accent")
    line.append(badge.plain, style=badge.style)
    line.append(f" {model}", style=S["white"])
    line.append(f"  {BRAND_NAME} is listening with local memory turned on", style=S["dim"])
    console.print(line)


def show_text_panel(title: str, body: str, tone: str = "primary", width: Optional[int] = None):
    console.print(
        _surface_panel(
            Text(body, style=S["text"]),
            title=title,
            tone=tone,
            width=width or _content_width(),
        )
    )


# ── Animation Helpers ────────────────────────────────────────────────

import math


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colors. t in [0, 1]."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


# Pulse palette for the thinking throb — cycles smoothly between these
_THROB_COLORS = [
    COLORS["primary"],      # moss green
    COLORS["primary_dim"],  # darker green
    COLORS["amber"],        # warm amber
    COLORS["accent"],       # blossom pink
    COLORS["primary"],      # back to green
]


def _throb_color(frame_idx: int, speed: float = 0.15) -> str:
    """Return a smoothly pulsing color based on frame index."""
    t = (math.sin(frame_idx * speed) + 1) / 2  # 0..1 sinusoidal
    # Walk through the color stops
    n = len(_THROB_COLORS) - 1
    segment = t * n
    i = min(int(segment), n - 1)
    local_t = segment - i
    return _lerp_color(_THROB_COLORS[i], _THROB_COLORS[i + 1], local_t)


def _throb_style(frame_idx: int, bold: bool = True) -> Style:
    """Return a Style with the current throb color."""
    return Style(color=_throb_color(frame_idx), bold=bold)


def _ansi(hex_color: str) -> str:
    """Hex to ANSI true-color escape for raw terminal writes."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16)
    return f"38;2;{r};{g};{b}"


def _raw(text: str, color: str = None):
    """Write raw text to stdout with optional color."""
    if color:
        sys.stdout.write(f"\033[{_ansi(color)}m{text}\033[0m")
    else:
        sys.stdout.write(text)
    sys.stdout.flush()


CURSOR_FRAMES = ["█", "▉", "▊", "▋", "▌", "▍", "▎", " "]

# Health bar characters
HP_FULL = "█"
HP_EMPTY = "░"


def typewriter(text: str, color: str = None, delay: float = 0.012):
    """Type out text character by character — CRT style."""
    for ch in text:
        _raw(ch, color)
        if ch not in (" ", "\n"):
            time.sleep(delay)
    sys.stdout.write("\n")
    sys.stdout.flush()


def scanline_reveal(text: str, color: str = None, width: int = 0):
    """Reveal text with a scanline sweep effect."""
    if not width:
        width = len(text)
    for i in range(len(text) + 1):
        line = text[:i] + "▓" * min(2, width - i) + " " * max(0, width - i - 2)
        sys.stdout.write(f"\r")
        _raw(line[:width], color)
        time.sleep(0.008)
    sys.stdout.write("\n")
    sys.stdout.flush()


class RetroSpinner:
    """Backwards-compatible spinner helper."""

    def __init__(self, label: str = "LOADING"):
        self._label = label
        self._running = False
        self._progress = None
        self._task_id = None

    def stop(self):
        self._running = False
        if self._progress is not None:
            self._progress.stop()
            self._progress = None

    def start(self):
        self._running = True
        self._progress = Progress(
            SpinnerColumn(style=Style(color=COLORS["primary"])),
            TextColumn("[progress.description]{task.description}", style=S["dim"]),
            console=console,
            transient=True,
        )
        self._progress.start()
        self._task_id = self._progress.add_task(self._label, total=None)


# ── Display Functions ────────────────────────────────────────────────

def _chat_width() -> int:
    return _content_width(max_width=84, margin=10)


def show_banner():
    """Display the startup banner."""
    clear_screen()
    console.print()
    copy = Group(
        Text(BRAND_NAME, style=Style(color=COLORS["white"], bold=True)),
        Text(BRAND_SUBTITLE, style=S["accent"]),
        Text(BRAND_TAGLINE, style=S["text"]),
        Text(BRAND_BLURB, style=S["dim"]),
        _inline_badges([
            ("local-first", "primary"),
            ("private memory", "success"),
            ("gentle threadkeeping", "accent"),
        ]),
        Text(f"Launch with ./{BRAND_COMMANDS[0]}.", style=S["faint"]),
        Text("Use /help for commands, /checkin for a quick pulse, or just start typing.", style=S["dim"]),
    )
    console.print(
        _surface_panel(
            _split_panel_with_mascot(_render_mascot(MASCOT_IDLE, mood="idle"), copy),
            title=BRAND_NAME,
            tone="primary",
            width=_content_width(max_width=94, margin=6),
            padding=(1, 2),
        )
    )
    console.print()


def show_help():
    """Display slash commands."""
    console.print()

    cmds = [
        ("/checkin",   "Quick mood check-in"),
        ("/deep",      "Deep well-being survey"),
        ("/mood",      "View mood history & trends"),
        ("/soul",      "View your profile"),
        ("/memory",    "What I remember about you"),
        ("/stats",     "Usage statistics"),
        ("/clear",     "New conversation"),
        ("/switch",    "Switch identity and re-auth"),
        ("/export",    "Export history"),
        ("/name",      "Update your name"),
        ("/help",      "This menu"),
        ("/quit",      "End session & save"),
    ]

    table = Table(box=None, show_header=True, padding=(0, 1), expand=True)
    table.add_column("Command", style=S["accent"], no_wrap=True, width=14)
    table.add_column("Use It For", style=S["text"])
    for cmd, desc in cmds:
        table.add_row(cmd, desc)

    console.print(
        _surface_panel(
            table,
            title="Commands",
            tone="accent",
            width=_content_width(max_width=84, margin=8),
            padding=(1, 2),
        )
    )
    console.print(Text("Slash commands are optional. You can always just talk normally.", style=S["dim"]))


def show_first_time_welcome():
    """Welcome for new users."""
    console.print()

    body = Group(
        Text(f"Meet {BRAND_NAME}, your small moss sprite for the terminal.", style=Style(color=COLORS["white"], bold=True)),
        Text(
            "Share as much or as little as you want. I can help you sort through what is going on and keep useful context for later.",
            style=S["text"],
        ),
        Text(
            "I am supportive, not clinical. If something sounds urgent, I will point you to real-world help quickly.",
            style=S["dim"],
        ),
        _inline_badges([
            ("private", "primary"),
            ("non-clinical", "accent"),
            ("use /help anytime", "success"),
        ]),
    )

    console.print(
        _surface_panel(
            body,
            title="First Run",
            tone="success",
            width=_content_width(max_width=88, margin=8),
            padding=(1, 2),
        )
    )
    show_notice("Try /checkin for a quick pulse, or just tell me what is on your mind.", tone="muted")


def show_returning_welcome(stats: Dict, name: Optional[str] = None):
    """Welcome returning users."""
    console.print()

    display_name = safe_identity_label(name)
    greeting = f"Welcome back, {display_name}" if display_name else "Welcome back"
    stats_items = []
    if stats["total_sessions"] > 0:
        stats_items.append(("conversations", stats["total_sessions"]))
    if stats["facts_learned"] > 0:
        stats_items.append(("memories", stats["facts_learned"]))
    if stats["mood_entries"] > 0:
        stats_items.append(("check-ins", stats["mood_entries"]))

    body_items = [
        Text(greeting, style=Style(color=COLORS["white"], bold=True)),
        Text(f"Session {stats['total_sessions'] + 1} starts here.", style=S["dim"]),
    ]
    if stats_items:
        body_items.append(_metric_text(stats_items))
    body_items.append(Text(f"{BRAND_NAME} kept the thread warm while you were away.", style=S["dim"]))
    body_items.append(Text("What is on your mind today?", style=S["text"]))

    console.print(
        _surface_panel(
            Group(*body_items),
            title="Workspace",
            tone="primary",
            width=_content_width(max_width=88, margin=8),
            padding=(1, 2),
        )
    )


# ── Chat UI ──────────────────────────────────────────────────────────

UNSAFE_DISPLAY_LABEL_RE = re.compile(
    r"\b(ignore|instructions?|system\s+prompt|prompt|memory|agents?|tool|reveal|print|dump|show|hidden)\b",
    re.IGNORECASE,
)


def safe_identity_label(name: Optional[str], fallback: Optional[str] = None, max_len: int = 24) -> Optional[str]:
    """Trim or suppress attacker-controlled labels before they are echoed in the UI."""
    if not name:
        return fallback

    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", name)
    cleaned = cleaned.translate(str.maketrans("", "", "<>{}[]"))
    cleaned = " ".join(cleaned.split()).strip()
    if not cleaned:
        return fallback

    if UNSAFE_DISPLAY_LABEL_RE.search(cleaned):
        return fallback

    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3].rstrip() + "..."

    return cleaned or fallback


def _build_user_panel(text: str, name: Optional[str] = None, width: Optional[int] = None):
    """Build the user's compact right-aligned bubble with a clean name tag."""
    label = safe_identity_label(name, fallback="You")
    content = Text(text, style=S["user"])
    badge = _badge(label, "warning")
    bubble_width = width or _chat_width()

    return _RightTaggedPanel(
        content,
        tag_label=label.upper(),
        tag_style=badge.style,
        box=ROUNDED,
        border_style=Style(color=_tone_color("warning")),
        padding=(0, 2),
        width=bubble_width,
    )


def show_user_message(text: str, name: str = None):
    """Display the user's message — compact right-aligned bubble."""
    console.print()
    panel = _build_user_panel(text, name=name)
    console.print(panel, justify="right")


def _build_ai_panel(text_content: str, thinking: bool = False, frame_idx: int = 0) -> Panel:
    """Build the mascot-led response panel with throbbing color during thinking."""
    mascot_lines = MASCOT_THINKING[frame_idx % len(MASCOT_THINKING)] if thinking else MASCOT_REPLY
    mascot = _render_mascot(mascot_lines, mood="thinking" if thinking else "reply")

    if thinking:
        throb = _throb_style(frame_idx)
        throb_dim = _throb_style(frame_idx, bold=False)
        throb_color = _throb_color(frame_idx)

        status = Text(
            f"{BRAND_NAME} is {THINKING_LINES[frame_idx % len(THINKING_LINES)]}…",
            style=throb_dim,
        )
        logo = _animated_wordmark(frame_idx)
        body = Text(text_content or "", style=S["ai"])
        # Pulsing cursor on the body text
        if not text_content:
            body = Text("thinking", style=throb_dim)
        footer = _animated_footer(frame_idx, mode="thinking")
        content = Group(status, logo, body, footer)

        return Panel(
            _split_panel_with_mascot(mascot, content),
            title=_panel_title(BRAND_NAME, "primary"),
            title_align="left",
            box=ROUNDED,
            border_style=Style(color=throb_color),
            padding=(1, 2),
            width=_chat_width(),
        )
    else:
        content = Text(text_content, style=S["ai"])
        return Panel(
            _split_panel_with_mascot(mascot, content),
            title=_panel_title(BRAND_NAME, "success"),
            title_align="left",
            box=ROUNDED,
            border_style=Style(color=COLORS["ai_border"]),
            padding=(1, 2),
            width=_chat_width(),
        )


def stream_ai_response(chunks, on_interrupt=None) -> str:
    """Stream AI response with animated mascot updates."""
    full_text = ""
    pending: "queue.Queue[object]" = queue.Queue()
    sentinel = object()
    errors = []

    console.print()

    def _read_stream():
        try:
            for chunk in chunks:
                pending.put(chunk)
        except Exception as exc:  # pragma: no cover - defensive surface for provider failures
            errors.append(exc)
        finally:
            pending.put(sentinel)

    worker = threading.Thread(target=_read_stream, daemon=True)
    worker.start()

    frame_idx = 0
    finished = False

    try:
        with Live(
            _build_ai_panel(thinking=True, text_content="", frame_idx=frame_idx),
            console=console,
            refresh_per_second=12,
            transient=True,
        ) as live:
            while not finished:
                while True:
                    try:
                        item = pending.get_nowait()
                    except queue.Empty:
                        break

                    if item is sentinel:
                        finished = True
                        break

                    full_text += item

                preview = full_text + CURSOR_FRAMES[frame_idx % len(CURSOR_FRAMES)] if not finished else full_text
                live.update(_build_ai_panel(preview, thinking=not finished, frame_idx=frame_idx))
                if finished:
                    break
                frame_idx += 1
                time.sleep(0.08)
    except KeyboardInterrupt:
        if callable(on_interrupt):
            on_interrupt()
        worker.join(timeout=1.0)
        raise

    worker.join(timeout=1.0)

    if errors:
        raise errors[0]

    console.print(_build_ai_panel(full_text.strip(), frame_idx=frame_idx))

    return full_text


def show_crisis_banner():
    """Display crisis resources with high visibility."""
    console.print()

    resources = [
        ("US", "988", "Suicide & Crisis Lifeline"),
        ("US", "Text HOME to 741741", "Crisis Text Line"),
        ("UK", "116 123", "Samaritans"),
        ("CA", "1-833-456-4566", "Talk Suicide"),
        ("AU", "13 11 14", "Lifeline"),
        ("EU", "112", "Emergency"),
        ("", "", ""),
        ("LGBTQ+", "1-866-488-7386", "Trevor Project"),
        ("Vets", "988 then Press 1", ""),
        ("Trans", "877-565-8860", "Trans Lifeline"),
    ]

    table = Table(box=None, show_header=False, padding=(0, 1), expand=True)
    table.add_column("Region", style=S["white"], width=12, no_wrap=True)
    table.add_column("Contact", style=S["crisis"], width=22)
    table.add_column("Service", style=S["text"])

    intro = Text(
        "If you might act on thoughts of self-harm or you feel unsafe, stop here and contact live support now.",
        style=Style(color=COLORS["white"], bold=True),
    )

    for region, number, label in resources:
        if not region:
            table.add_row("", "", "")
            continue
        table.add_row(region, number, label)

    body = Group(
        intro,
        Text("Texting or calling is enough. If you can, reach out to someone near you too.", style=S["dim"]),
        Text(""),
        table,
    )

    console.print(
        _surface_panel(
            body,
            title="Urgent Support",
            tone="danger",
            width=_content_width(max_width=94, margin=6),
            padding=(1, 2),
            box_style=THICK_BOX,
        )
    )


# ── Survey UI ────────────────────────────────────────────────────────

def run_survey(questions: List[SurveyQuestion], title: str = "Check-In") -> Optional[Dict[str, int]]:
    """Run survey with clearer prompts and spacing.

    Returns scores dict, or ``None`` if the user quits (Ctrl-C twice or
    types ``/quit``).
    """
    console.print()
    console.print(
        _surface_panel(
            Group(
                Text(title, style=Style(color=COLORS["white"], bold=True)),
                Text("Answer with a number. Ctrl-C to skip a question, twice to quit.", style=S["dim"]),
            ),
            title="Check-In",
            tone="primary",
            width=_content_width(max_width=86, margin=10),
            padding=(1, 2),
        )
    )

    scores = {}
    last_was_skip = False
    for i, q in enumerate(questions, 1):
        scale = Text()
        scale.append(f"{q.low_label}  ", style=S["dim"])
        for n in range(q.min_val, q.max_val + 1):
            c = _score_color(n)
            scale.append(f" {n} ", style=Style(color=c))
        scale.append(f"  {q.high_label}", style=S["dim"])

        console.print(
            _surface_panel(
                Group(
                    Text(f"Question {i} of {len(questions)}", style=S["dim"]),
                    Text(q.prompt, style=Style(color=COLORS["white"], bold=True)),
                    scale,
                ),
                title="Prompt",
                tone="accent",
                width=_content_width(max_width=82, margin=12),
                padding=(1, 2),
            )
        )

        while True:
            try:
                val = IntPrompt.ask(
                    f"[{COLORS['amber']}]your rating {q.min_val}-{q.max_val} ›[/{COLORS['amber']}]",
                    console=console,
                )
                if q.min_val <= val <= q.max_val:
                    scores[q.key] = val
                    last_was_skip = False
                    break
                show_notice(f"Enter a value between {q.min_val} and {q.max_val}.", tone="muted")
            except ValueError:
                show_notice("Skipped. I will use a neutral score for this one.", tone="muted")
                scores[q.key] = 5
                last_was_skip = False
                break
            except KeyboardInterrupt:
                if last_was_skip:
                    show_notice("Check-in cancelled.", tone="muted")
                    return None
                show_notice("Skipped. Press Ctrl-C again to quit the check-in.", tone="muted")
                scores[q.key] = 5
                last_was_skip = True
                break
        console.print()

    return scores


def show_survey_results(scores: Dict[str, int]):
    """Display survey results as compact metric cards."""
    console.print()

    labels = {
        "overall": "Overall",
        "energy": "Energy",
        "anxiety": "Anxiety",
        "sleep_quality": "Sleep",
        "motivation": "Motivation",
        "connection": "Connection",
        "self_care": "Self-care",
        "hope": "Hope",
    }

    tiles = []
    for key, val in scores.items():
        label = labels.get(key, key.replace("_", " ").title())
        color = _score_color(val)
        tile_body = Group(
            Text(label, style=S["dim"]),
            Text(f"{val}/10", style=Style(color=color, bold=True)),
            Text(_score_bar(val), style=Style(color=color)),
        )
        tiles.append(
            Panel(
                tile_body,
                box=ROUNDED,
                border_style=Style(color=color),
                padding=(1, 2),
            )
        )

    console.print(Columns(tiles, equal=True, expand=True))

    interpretation = interpret_scores(scores)
    console.print(
        _surface_panel(
            Text(interpretation, style=S["text"]),
            title="Read on This",
            tone="primary",
            width=_content_width(max_width=92, margin=8),
            padding=(1, 2),
        )
    )


# ── Mood History ─────────────────────────────────────────────────────

def show_mood_history(moods: List[MoodEntry]):
    """Display mood history and trends."""
    if not moods:
        console.print(
            _surface_panel(
                Text("No mood entries yet. Try /checkin to record your first one.", style=S["dim"]),
                title="Mood History",
                tone="muted",
                width=_content_width(max_width=82, margin=10),
                padding=(1, 2),
            )
        )
        return

    console.print()

    table = Table(
        box=RETRO_BOX,
        border_style=Style(color=COLORS["border"]),
        show_header=True,
        padding=(0, 1),
    )
    table.add_column("DATE", style=S["dim"], min_width=10)
    table.add_column("OVR", justify="center")
    table.add_column("NRG", justify="center")
    table.add_column("ANX", justify="center")
    table.add_column("SLP", justify="center")

    for m in moods[-10:]:
        date = m.timestamp[:10]
        table.add_row(
            date,
            _score_colored(m.overall),
            _score_colored(m.energy),
            _score_colored(m.anxiety),
            _score_colored(m.sleep_quality),
        )

    console.print(Panel(
        table,
        title=_panel_title("Mood History", "primary"),
        title_align="left",
        box=RETRO_BOX,
        border_style=Style(color=COLORS["primary_dim"]),
        padding=(1, 1),
    ))

    # Sparklines
    overall_vals = [m.overall for m in moods]
    energy_vals = [m.energy for m in moods]
    anxiety_vals = [m.anxiety for m in moods]
    sleep_vals = [m.sleep_quality for m in moods]

    spark_text = Text()
    spark_text.append("  OVR  ", style=S["dim"])
    spark_text.append(mood_sparkline(overall_vals), style=S["amber"])
    spark_text.append(f"  avg {sum(overall_vals)/len(overall_vals):.1f}\n", style=S["dim"])
    spark_text.append("  NRG  ", style=S["dim"])
    spark_text.append(mood_sparkline(energy_vals), style=S["green"])
    spark_text.append(f"  avg {sum(energy_vals)/len(energy_vals):.1f}\n", style=S["dim"])
    spark_text.append("  ANX  ", style=S["dim"])
    spark_text.append(mood_sparkline(anxiety_vals), style=S["crisis"])
    spark_text.append(f"  avg {sum(anxiety_vals)/len(anxiety_vals):.1f}\n", style=S["dim"])
    spark_text.append("  SLP  ", style=S["dim"])
    spark_text.append(mood_sparkline(sleep_vals), style=S["green_dim"])
    spark_text.append(f"  avg {sum(sleep_vals)/len(sleep_vals):.1f}", style=S["dim"])

    console.print(Panel(
        spark_text,
        title=_panel_title("Trend Snapshot", "success"),
        title_align="left",
        box=RETRO_BOX,
        border_style=Style(color=COLORS["border"]),
        padding=(0, 1),
    ))

    mood_dicts = [{"overall": m.overall, "energy": m.energy,
                   "anxiety": m.anxiety, "sleep_quality": m.sleep_quality}
                  for m in moods]
    analysis = mood_trend_analysis(mood_dicts)
    console.print(
        _surface_panel(
            Text(analysis, style=S["text"]),
            title="What It Suggests",
            tone="accent",
            width=_content_width(max_width=92, margin=8),
            padding=(1, 2),
        )
    )


def _score_colored(val: int) -> str:
    if val <= 3:
        return f"[{COLORS['hp_low']}]{val}[/{COLORS['hp_low']}]"
    elif val <= 6:
        return f"[{COLORS['hp_mid']}]{val}[/{COLORS['hp_mid']}]"
    else:
        return f"[{COLORS['hp_high']}]{val}[/{COLORS['hp_high']}]"


# ── Memory Display ───────────────────────────────────────────────────

def show_memory(db: WellnessDB):
    """Display remembered profile, facts, and summaries."""
    facts = db.get_facts()
    summaries = db.get_recent_summaries(5)
    profile = db.get_full_profile()

    console.print()

    if profile:
        prof_text = Text()
        for k, v in profile.items():
            if k.startswith("_"):
                continue
            prof_text.append(f"  {k.upper()}: ", style=S["amber"])
            prof_text.append(f"{v}\n", style=S["text"])
        console.print(Panel(
            prof_text,
            title=_panel_title("Profile", "primary"),
            title_align="left",
            box=RETRO_BOX,
            border_style=Style(color=COLORS["primary_dim"]),
            padding=(0, 1),
        ))

    if facts:
        facts_table = Table(
            box=None,
            show_header=True,
            padding=(0, 1),
            show_edge=False,
        )
        facts_table.add_column("KEY", style=S["amber"], min_width=16)
        facts_table.add_column("VALUE", style=S["text"])
        facts_table.add_column("CONF", justify="center", style=S["dim"], max_width=6)

        for f in facts[:20]:
            conf_bar = "█" * int(f.confidence * 5) + "░" * (5 - int(f.confidence * 5))
            facts_table.add_row(f.key, f.value, conf_bar)

        console.print(Panel(
            facts_table,
            title=_panel_title("Memory", "accent"),
            title_align="left",
            box=RETRO_BOX,
            border_style=Style(color=COLORS["amber_dim"]),
            padding=(1, 1),
        ))
    else:
        console.print(
            _surface_panel(
                Text("No saved details yet. Keep talking and I will build context over time.", style=S["dim"]),
                title="Memory",
                tone="muted",
                width=_content_width(max_width=84, margin=10),
                padding=(1, 2),
            )
        )

    if summaries:
        sum_text = Text()
        for s in summaries:
            date = s.created_at[:10]
            sum_text.append(f"  [{date}] ", style=S["dim"])
            sum_text.append(f"{s.summary}\n", style=S["text"])
            if s.key_topics:
                sum_text.append(f"            {s.key_topics}\n", style=S["amber_dim"])
        console.print(Panel(
            sum_text,
            title=_panel_title("Recent Sessions", "success"),
            title_align="left",
            box=RETRO_BOX,
            border_style=Style(color=COLORS["border"]),
            padding=(0, 1),
        ))


# ── Stats Display ────────────────────────────────────────────────────

def show_stats(stats: Dict):
    """Display top-level usage metrics."""
    console.print()

    items = [
        ("Sessions", stats["total_sessions"]),
        ("Messages", stats["total_messages"]),
        ("Memories", stats["facts_learned"]),
        ("Check-ins", stats["mood_entries"]),
    ]
    tiles = []
    for label, value in items:
        tone = "primary" if label in {"Sessions", "Messages"} else "success"
        color = _tone_color(tone)
        tiles.append(
            Panel(
                Group(
                    Text(label, style=S["dim"]),
                    Text(str(value), style=Style(color=COLORS["white"], bold=True)),
                ),
                box=ROUNDED,
                border_style=Style(color=color),
                padding=(1, 2),
            )
        )

    console.print(
        _surface_panel(
            Text("A quick look at how much history and context your companion has built.", style=S["dim"]),
            title="Activity",
            tone="primary",
            width=_content_width(max_width=92, margin=8),
            padding=(1, 2),
        )
    )
    console.print(Columns(tiles, equal=True, expand=True))


# ── Session End ──────────────────────────────────────────────────────

def show_session_end():
    """Render the session close message."""
    console.print()
    console.print(
        _surface_panel(
            Group(
                Text("Session saved.", style=Style(color=COLORS["white"], bold=True)),
                Text(f"Take care. {BRAND_NAME} will be here whenever you want to pick this up again.", style=S["dim"]),
            ),
            title="Signed Off",
            tone="success",
            width=_content_width(max_width=72, margin=12),
            padding=(1, 2),
        )
    )
    console.print()


def _build_processing_panel(message: str, step: int, total_steps: int) -> Panel:
    frame_idx = step % len(MASCOT_THINKING)
    throb = _throb_style(step)
    throb_color = _throb_color(step)
    content = Group(
        Text(message, style=Style(color=COLORS["white"], bold=True)),
        _animated_wordmark(frame_idx),
        Text(f"{BRAND_NAME} is {PROCESSING_LINES[frame_idx % len(PROCESSING_LINES)]}.", style=_throb_style(step, bold=False)),
        Text(_progress_bar(step + 1, total_steps), style=Style(color=throb_color, bold=True)),
        _animated_footer(frame_idx, mode="processing"),
    )
    return Panel(
        _split_panel_with_mascot(
            _render_mascot(MASCOT_THINKING[frame_idx], mood="processing"),
            content,
        ),
        title=_panel_title(BRAND_NAME, "accent"),
        title_align="left",
        box=ROUNDED,
        border_style=Style(color=throb_color),
        padding=(1, 2),
        width=_content_width(max_width=80, margin=12),
    )


def show_processing(message: str = "Saving learnings from this conversation..."):
    """Show a short mascot-led progress animation."""
    total_steps = 20
    console.print()
    with Live(
        _build_processing_panel(message, 0, total_steps),
        console=console,
        refresh_per_second=12,
        transient=True,
    ) as live:
        for step in range(total_steps):
            live.update(_build_processing_panel(message, step, total_steps))
            time.sleep(0.05)
    show_notice("Tucked away.", tone="success")


def show_autosave_start():
    """Non-intrusive autosave indicator — just a faint right-aligned print, no Live context."""
    line = Text()
    badge = _badge("Autosave", "muted")
    line.append(badge.plain, style=badge.style)
    line.append(" memory checkpoint…", style=S["faint"])
    console.print(line, justify="right")


def show_autosave_done():
    """Brief transient completion notice — no blocking sleep."""
    done_line = Text()
    badge = _badge("Autosave", "success")
    done_line.append(badge.plain, style=badge.style)
    done_line.append(" checkpoint saved", style=S["faint"])
    console.print(done_line, justify="right")


# ── Onboarding ───────────────────────────────────────────────────────

def run_onboarding(questions: list, dynamic_generator: Callable = None) -> Dict[str, str]:
    """
    Run onboarding Q&A with optional dynamic follow-up questions.
    """
    clear_screen()
    console.print()

    intro = Group(
        Text("Let’s make this feel like yours.", style=Style(color=COLORS["white"], bold=True)),
        Text(
            f"{BRAND_NAME} will ask a few short questions so future conversations start with better context. Answer briefly, skip anything, and keep it as personal as you want.",
            style=S["text"],
        ),
        _inline_badges([
            ("5-7 questions", "primary"),
            ("smart follow-ups", "accent"),
            ("local profile only", "success"),
        ]),
    )
    console.print(
        _surface_panel(
            intro,
            title="Onboarding",
            tone="primary",
            width=_content_width(max_width=90, margin=8),
            padding=(1, 2),
        )
    )
    console.print()

    answers = {}
    asked = 0
    max_questions = 7
    question_queue = list(questions)

    while question_queue and asked < max_questions:
        q = question_queue.pop(0)
        asked += 1

        console.print(
            _surface_panel(
                Group(
                    Text(f"Question {asked} of {max_questions}", style=S["dim"]),
                    Text(q["prompt"], style=Style(color=COLORS["white"], bold=True)),
                ),
                title="Prompt",
                tone="accent",
                width=_content_width(max_width=82, margin=12),
                padding=(1, 2),
            )
        )

        try:
            answer = Prompt.ask(
                f"[{COLORS['amber']}]you ›[/{COLORS['amber']}]",
                console=console,
            )
            answers[q["key"]] = answer.strip() if answer else ""
        except (KeyboardInterrupt, EOFError):
            break

        console.print()

        if dynamic_generator and asked < max_questions:
            followup = dynamic_generator(answers)
            if followup and isinstance(followup, dict) and "prompt" in followup:
                question_queue.insert(0, followup)

    name = answers.get("name", "").strip()
    display_name = safe_identity_label(name)
    if display_name:
        show_notice(
            f"Profile created for {display_name}. {BRAND_NAME} will keep shaping this gently over time.",
            tone="success",
        )
    elif name:
        show_notice(f"Profile created. {BRAND_NAME} will keep shaping this gently over time.", tone="success")
    console.print()

    return answers


def show_startup_wizard_intro():
    """Introduce the guided startup wizard."""
    clear_screen()
    console.print()
    console.print(
        _surface_panel(
            Group(
                Text("Let’s set up Moss before the chat starts.", style=Style(color=COLORS["white"], bold=True)),
                Text(
                    "This wizard covers model access, governed side effects, encrypted storage, and whether to continue with an existing profile or refresh the onboarding.",
                    style=S["text"],
                ),
                _inline_badges([
                    ("provider + model", "accent"),
                    ("pangoclaw mode", "warning"),
                    ("vault + profile", "success"),
                ]),
            ),
            title="Setup Wizard",
            tone="primary",
            width=_content_width(max_width=96, margin=8),
            padding=(1, 2),
        )
    )
    console.print()


def choose_provider(providers: List[Dict[str, str]], default: Optional[str] = None) -> str:
    """Choose which AI provider the wizard should use."""
    console.print()

    intro = Text(
        "Pick the CLI backend Moss should use for the main conversation. Only ready providers can be selected here.",
        style=S["text"],
    )

    table = Table(box=None, show_header=True, padding=(0, 1), expand=True)
    table.add_column("Provider", style=S["white"], width=14)
    table.add_column("CLI", style=S["text"], width=14)
    table.add_column("Auth", style=S["text"], width=16)
    table.add_column("Notes", style=S["dim"])

    available_choices = []
    for row in providers:
        cli_status = "installed" if row.get("installed") else "missing"
        auth_status = "ready" if row.get("available") else (
            "login needed" if row.get("installed") else "not checked"
        )
        notes = row.get("detail") or row.get("fix") or ""
        table.add_row(row["value"], cli_status, auth_status, notes)
        if row.get("available"):
            available_choices.append(row["value"])

    console.print(
        _surface_panel(
            Group(intro, Text(""), table),
            title="Provider",
            tone="accent",
            width=_content_width(max_width=104, margin=8),
            padding=(1, 2),
        )
    )

    if not available_choices:
        return ""

    fallback = default if default in available_choices else available_choices[0]
    return Prompt.ask(
        f"[{COLORS['amber']}]choose provider[/{COLORS['amber']}]",
        console=console,
        choices=available_choices,
        default=fallback,
    )


def choose_pangoclaw_mode(socket_path: str, status: Dict[str, str], default: str = "auto") -> str:
    """Choose whether to use PangoClaw-governed side effects."""
    console.print()

    state_line = (
        f"Sidecar ready at {socket_path}"
        if status.get("ready")
        else f"Not ready at {socket_path}: {status.get('reason') or 'socket unavailable'}"
    )

    table = Table(box=None, show_header=True, padding=(0, 1), expand=True)
    table.add_column("Mode", style=S["white"], width=10)
    table.add_column("What Happens", style=S["text"])

    table.add_row(
        "auto",
        "Use PangoClaw whenever the local sidecar is reachable. Governed follow-ups, profile refinement, and /export stay available.",
    )
    table.add_row(
        "off",
        "Disable PangoClaw explicitly for this startup profile. Chat still works, but governed follow-ups, memory refinement, and /export stay paused.",
    )

    console.print(
        _surface_panel(
            Group(
                Text(
                    "Choose whether governed side effects should route through the local PangoClaw sidecar.",
                    style=S["text"],
                ),
                Text(state_line, style=S["dim"]),
                Text(""),
                table,
            ),
            title="Governance",
            tone="warning",
            width=_content_width(max_width=104, margin=8),
            padding=(1, 2),
        )
    )

    return Prompt.ask(
        f"[{COLORS['amber']}]pangoclaw mode[/{COLORS['amber']}]",
        console=console,
        choices=["auto", "off"],
        default=default if default in {"auto", "off"} else "auto",
    )


def choose_profile_start(name: Optional[str] = None) -> str:
    """Choose whether to continue with an existing profile or refresh onboarding."""
    console.print()
    label = safe_identity_label(name, fallback="your current profile")

    table = Table(box=None, show_header=True, padding=(0, 1), expand=True)
    table.add_column("Mode", style=S["white"], width=12)
    table.add_column("What Happens", style=S["text"])
    table.add_row("continue", "Keep the existing profile and drop into chat.")
    table.add_row("re_onboard", "Ask the onboarding questions again and refresh the profile before chat.")

    console.print(
        _surface_panel(
            Group(
                Text(
                    f"Moss found {label}. Choose whether to continue with it or re-run onboarding before the session starts.",
                    style=S["text"],
                ),
                Text(""),
                table,
            ),
            title="Profile Start",
            tone="success",
            width=_content_width(max_width=104, margin=8),
            padding=(1, 2),
        )
    )

    return Prompt.ask(
        f"[{COLORS['amber']}]profile start[/{COLORS['amber']}]",
        console=console,
        choices=["continue", "re_onboard"],
        default="continue",
    )


def show_soul_loaded(name: Optional[str] = None):
    """Brief note that soul profile was loaded."""
    label = safe_identity_label(name)
    if label:
        show_notice(f"{BRAND_NAME} loaded {label}'s profile.", tone="muted")
    else:
        show_notice(f"{BRAND_NAME} loaded your profile.", tone="muted")


def prompt_text(label: str, default: Optional[str] = None) -> str:
    return Prompt.ask(
        f"[{COLORS['amber']}]{label}[/{COLORS['amber']}]",
        console=console,
        default=default,
    )


def prompt_secret(label: str, confirm: bool = False) -> str:
    """Prompt for a hidden passphrase."""
    while True:
        first = Prompt.ask(
            f"[{COLORS['amber']}]{label}[/{COLORS['amber']}]",
            console=console,
            password=True,
        )
        if not first:
            show_notice("The vault password cannot be empty.", tone="danger")
            continue

        if not confirm:
            return first

        second = Prompt.ask(
            f"[{COLORS['amber']}]confirm {label}[/{COLORS['amber']}]",
            console=console,
            password=True,
        )
        if first == second:
            return first

        show_notice("The two vault passwords did not match. Try again.", tone="danger")


def choose_identity(identities: List[Dict[str, str]], allow_new: bool = True) -> str:
    """Let the user pick an identity or create a new one."""
    console.print()
    table = Table(box=None, show_header=True, padding=(0, 1), expand=True)
    table.add_column("#", style=S["accent"], width=4, no_wrap=True)
    table.add_column("Identity", style=S["white"])
    table.add_column("Last Used", style=S["dim"])

    for idx, row in enumerate(identities, start=1):
        last_used = row.get("last_used_at") or row.get("created_at") or "never"
        table.add_row(str(idx), row["label"], last_used[:19])

    if allow_new:
        table.add_row("0", "Create new identity", "set password twice")

    console.print(
        _surface_panel(
            table,
            title="Identities",
            tone="accent",
            width=_content_width(max_width=90, margin=8),
            padding=(1, 2),
        )
    )

    choices = ["0"] if allow_new else []
    choices.extend(str(i) for i in range(1, len(identities) + 1))
    choice = Prompt.ask(
        f"[{COLORS['amber']}]choose identity[/{COLORS['amber']}]",
        console=console,
        choices=choices,
        default="1" if identities else "0",
    )
    return choice


def choose_storage_location(
    local_path: str,
    icloud_path: str,
    local_has_data: bool = False,
    icloud_has_data: bool = False,
) -> str:
    """Choose where sealed vault files should live."""
    console.print()

    intro = Text(
        "Choose where Moss should keep sealed encrypted vault files. Unlocked runtime files stay local to this Mac either way.",
        style=S["text"],
    )
    if local_has_data or icloud_has_data:
        intro.append(
            " Existing data was found, so pick the store you want to open.",
            style=S["dim"],
        )

    table = Table(box=None, show_header=True, padding=(0, 1), expand=True)
    table.add_column("#", style=S["accent"], width=4, no_wrap=True)
    table.add_column("Storage", style=S["white"], width=20)
    table.add_column("Use It For", style=S["text"])
    table.add_column("Path", style=S["dim"])

    local_label = "existing data found" if local_has_data else "default"
    icloud_label = "existing data found" if icloud_has_data else "backup / sync"
    table.add_row("1", f"Local only ({local_label})", "Keeps encrypted vaults only on this Mac", local_path)
    table.add_row("2", f"iCloud Drive ({icloud_label})", "Syncs only encrypted vault files through iCloud", icloud_path)

    console.print(
        _surface_panel(
            Group(intro, Text(""), table),
            title="Vault Storage",
            tone="accent",
            width=_content_width(max_width=104, margin=8),
            padding=(1, 2),
        )
    )
    console.print(Text("If you use iCloud, avoid opening the same identity on two Macs at once.", style=S["dim"]))

    return Prompt.ask(
        f"[{COLORS['amber']}]where should encrypted vaults live[/{COLORS['amber']}]",
        console=console,
        choices=["1", "2"],
        default="1",
    )


def choose_model(provider_name: str, models: List[Dict[str, str]], default: str) -> str:
    """Choose a model for the current provider."""
    console.print()

    intro = Text(
        f"Choose which {provider_name} model Moss should use for this session.",
        style=S["text"],
    )
    intro.append(" Press enter for the best default.", style=S["dim"])

    table = Table(box=None, show_header=True, padding=(0, 1), expand=True)
    table.add_column("#", style=S["accent"], width=4, no_wrap=True)
    table.add_column("Model", style=S["white"], width=28)
    table.add_column("Use It For", style=S["text"])

    default_choice = "1"
    for idx, row in enumerate(models, start=1):
        label = row["label"]
        if row["value"] == default:
            label = f"{label} (default)"
            default_choice = str(idx)
        table.add_row(str(idx), label, row["detail"])

    console.print(
        _surface_panel(
            Group(intro, Text(""), table),
            title="Model Choice",
            tone="accent",
            width=_content_width(max_width=104, margin=8),
            padding=(1, 2),
        )
    )

    choice = Prompt.ask(
        f"[{COLORS['amber']}]choose model[/{COLORS['amber']}]",
        console=console,
        choices=[str(i) for i in range(1, len(models) + 1)],
        default=default_choice,
    )
    return models[int(choice) - 1]["value"]


def show_setup_result(checks: list[dict]):
    """Display setup diagnostic results.

    Each check is a dict with keys: name, ok (bool), detail (str).
    """
    console.print()

    table = Table(box=None, show_header=False, padding=(0, 1), expand=False)
    table.add_column("Status", width=4, no_wrap=True)
    table.add_column("Check", style=S["white"], min_width=24)
    table.add_column("Detail", style=S["dim"])

    for check in checks:
        icon = Text("pass", style=S["success"]) if check["ok"] else Text("FAIL", style=S["crisis"])
        table.add_row(icon, Text(check["name"]), Text(check.get("detail", "")))

    panel = Panel(
        table,
        title=_panel_title(f"{BRAND_NAME} setup", "primary"),
        title_align="left",
        box=ROUNDED,
        border_style=Style(color=COLORS["primary_dim"]),
        padding=(1, 2),
        width=_chat_width(),
    )
    console.print(panel)

    failed = [c for c in checks if not c["ok"]]
    if failed:
        console.print()
        for c in failed:
            fix = c.get("fix")
            if fix:
                show_notice(f'{c["name"]}: {fix}', tone="warning")
    else:
        console.print()
        show_notice("All checks passed. Run ./moss to start.", tone="success")
    console.print()


def get_user_input() -> str:
    """Get user input with a cleaner prompt."""
    try:
        return Prompt.ask(
            f"\n[{COLORS['amber']}]you ›[/{COLORS['amber']}]",
            console=console,
        )
    except (KeyboardInterrupt, EOFError):
        return "/quit"
