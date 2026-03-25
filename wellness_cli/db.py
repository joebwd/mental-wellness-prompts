"""
Database layer — SQLite storage for conversations, messages, user facts, and mood surveys.
"""

import json
import sqlite3
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from .paths import get_db_path


@dataclass
class Message:
    id: Optional[int]
    session_id: str
    role: str          # "user" | "assistant"
    content: str
    timestamp: str
    crisis_flag: bool = False
    mood_score: Optional[int] = None


@dataclass
class UserFact:
    id: Optional[int]
    key: str            # e.g. "sleep_issue", "anxiety_trigger", "name"
    value: str
    source_session: str
    confidence: float   # 0.0-1.0
    created_at: str
    updated_at: str


@dataclass
class MoodEntry:
    id: Optional[int]
    session_id: str
    timestamp: str
    overall: int         # 1-10
    energy: int          # 1-10
    anxiety: int         # 1-10
    sleep_quality: int   # 1-10
    notes: str = ""


@dataclass
class SessionSummary:
    id: Optional[int]
    session_id: str
    summary: str
    key_topics: str       # JSON list
    mood_start: Optional[int]
    mood_end: Optional[int]
    created_at: str


@dataclass
class GovernanceEvent:
    id: Optional[int]
    action: str
    status: str
    session_id: str
    receipt_id: Optional[str]
    reason: str
    policy_name: str
    metadata_json: str
    created_at: str


class WellnessDB:
    """SQLite database for the wellness companion."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_db_path()
        db_dir = os.path.dirname(self.db_path)
        if self.db_path != ":memory:" and db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._lock = threading.RLock()
        self._closed = False
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            cur = self.conn.cursor()
            cur.executescript("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    crisis_flag BOOLEAN DEFAULT 0,
                    mood_score INTEGER
                );

                CREATE TABLE IF NOT EXISTS user_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source_session TEXT NOT NULL,
                    confidence REAL DEFAULT 0.8,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS mood_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    overall INTEGER NOT NULL,
                    energy INTEGER NOT NULL,
                    anxiety INTEGER NOT NULL,
                    sleep_quality INTEGER NOT NULL,
                    notes TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS session_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    summary TEXT NOT NULL,
                    key_topics TEXT DEFAULT '[]',
                    mood_start INTEGER,
                    mood_end INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS governance_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    receipt_id TEXT,
                    reason TEXT DEFAULT '',
                    policy_name TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
                CREATE INDEX IF NOT EXISTS idx_mood_timestamp ON mood_entries(timestamp);
                CREATE INDEX IF NOT EXISTS idx_facts_key ON user_facts(key);
                CREATE INDEX IF NOT EXISTS idx_governance_action ON governance_events(action);
            """)
            self.conn.commit()

    # ── Messages ──────────────────────────────────────────────────────

    def save_message(self, msg: Message) -> int:
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO messages (session_id, role, content, timestamp, crisis_flag, mood_score)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (msg.session_id, msg.role, msg.content, msg.timestamp,
                 msg.crisis_flag, msg.mood_score),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_session_messages(self, session_id: str) -> List[Message]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
            return [Message(**dict(r)) for r in rows]

    def get_recent_messages(self, limit: int = 50) -> List[Message]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [Message(**dict(r)) for r in reversed(rows)]

    def get_all_messages(self) -> List[Message]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM messages ORDER BY timestamp",
            ).fetchall()
            return [Message(**dict(r)) for r in rows]

    def count_sessions(self) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(DISTINCT session_id) as c FROM messages"
            ).fetchone()
            return row["c"] if row else 0

    def get_all_session_ids(self) -> List[str]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT session_id FROM messages GROUP BY session_id ORDER BY MIN(rowid)"
            ).fetchall()
            return [r["session_id"] for r in rows]

    # ── User Facts ────────────────────────────────────────────────────

    def save_fact(self, fact: UserFact) -> int:
        with self._lock:
            # Upsert — update if same key+value exists
            existing = self.conn.execute(
                "SELECT id FROM user_facts WHERE key = ? AND value = ?",
                (fact.key, fact.value),
            ).fetchone()
            if existing:
                self.conn.execute(
                    "UPDATE user_facts SET confidence = ?, updated_at = ? WHERE id = ?",
                    (fact.confidence, fact.updated_at, existing["id"]),
                )
                self.conn.commit()
                return existing["id"]
            cur = self.conn.execute(
                """INSERT INTO user_facts (key, value, source_session, confidence, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (fact.key, fact.value, fact.source_session, fact.confidence,
                 fact.created_at, fact.updated_at),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_facts(self, key: Optional[str] = None) -> List[UserFact]:
        with self._lock:
            if key:
                rows = self.conn.execute(
                    "SELECT * FROM user_facts WHERE key = ? ORDER BY confidence DESC",
                    (key,),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM user_facts ORDER BY updated_at DESC"
                ).fetchall()
            return [UserFact(**dict(r)) for r in rows]

    def get_all_facts_summary(self) -> str:
        facts = self.get_facts()
        if not facts:
            return ""
        lines = []
        for f in facts:
            lines.append(f"- {f.key}: {f.value} (confidence: {f.confidence:.1f})")
        return "\n".join(lines)

    # ── Mood Entries ──────────────────────────────────────────────────

    def save_mood(self, entry: MoodEntry) -> int:
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO mood_entries (session_id, timestamp, overall, energy, anxiety, sleep_quality, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (entry.session_id, entry.timestamp, entry.overall, entry.energy,
                 entry.anxiety, entry.sleep_quality, entry.notes),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_recent_moods(self, limit: int = 14) -> List[MoodEntry]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM mood_entries ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [MoodEntry(**dict(r)) for r in reversed(rows)]

    def get_mood_trend(self, days: int = 7) -> List[MoodEntry]:
        return self.get_recent_moods(days)

    # ── Session Summaries ─────────────────────────────────────────────

    def save_summary(self, summary: SessionSummary) -> int:
        with self._lock:
            cur = self.conn.execute(
                """INSERT OR REPLACE INTO session_summaries
                   (session_id, summary, key_topics, mood_start, mood_end, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (summary.session_id, summary.summary, summary.key_topics,
                 summary.mood_start, summary.mood_end, summary.created_at),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_recent_summaries(self, limit: int = 10) -> List[SessionSummary]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM session_summaries ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [SessionSummary(**dict(r)) for r in reversed(rows)]

    def get_all_summaries(self) -> List[SessionSummary]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM session_summaries ORDER BY created_at",
            ).fetchall()
            return [SessionSummary(**dict(r)) for r in rows]

    def get_summary(self, session_id: str) -> Optional[SessionSummary]:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM session_summaries WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return SessionSummary(**dict(row)) if row else None

    # ── User Profile ──────────────────────────────────────────────────

    def set_profile(self, key: str, value: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO user_profile (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )
            self.conn.commit()

    def get_profile(self, key: str) -> Optional[str]:
        with self._lock:
            row = self.conn.execute(
                "SELECT value FROM user_profile WHERE key = ?", (key,),
            ).fetchone()
            return row["value"] if row else None

    def get_full_profile(self) -> Dict[str, str]:
        with self._lock:
            rows = self.conn.execute("SELECT key, value FROM user_profile").fetchall()
            return {r["key"]: r["value"] for r in rows}

    # ── Governance Audit ─────────────────────────────────────────────

    def save_governance_event(self, event: GovernanceEvent) -> int:
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO governance_events
                   (action, status, session_id, receipt_id, reason, policy_name, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.action,
                    event.status,
                    event.session_id,
                    event.receipt_id,
                    event.reason,
                    event.policy_name,
                    event.metadata_json,
                    event.created_at,
                ),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_governance_events(self, limit: int = 100) -> List[GovernanceEvent]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM governance_events ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [GovernanceEvent(**dict(r)) for r in rows]

    # ── Stats ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            msg_count = self.conn.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
            session_count = self.count_sessions()
            fact_count = self.conn.execute("SELECT COUNT(*) as c FROM user_facts").fetchone()["c"]
            mood_count = self.conn.execute("SELECT COUNT(*) as c FROM mood_entries").fetchone()["c"]
            return {
                "total_messages": msg_count,
                "total_sessions": session_count,
                "facts_learned": fact_count,
                "mood_entries": mood_count,
            }

    def close(self):
        with self._lock:
            if self._closed:
                return
            self.conn.close()
            self._closed = True
