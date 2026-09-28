"""
Persistent session + feedback storage.

CHANGES from the technical assessment (section 2.5):
  - "Volatile session storage": sessions previously lived only in a Python
    dict and vanished on restart / were not shared across processes. This
    module uses SQLite (sqlite3.connect(..., check_same_thread=False) with
    a lock) so session state survives a server restart and is safe under
    FastAPI's threaded request handling. This is still a single-file local
    database appropriate for a prototype -- production should move to
    Redis/Postgres as noted in the README.
  - "Non-functional feedback": /api/feedback previously returned success
    without saving anything. Feedback is now written to a real table.
  - Adds a `pending` flag per session used to reject duplicate/overlapping
    submissions (assessment: "Users can submit repeated messages while a
    request is still running").
"""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "sessions.db"

_lock = threading.Lock()
_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
_conn.execute("PRAGMA journal_mode=WAL")


def _init_db():
    with _lock:
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at REAL,
                state_json TEXT,
                pending INTEGER DEFAULT 0
            )
        """)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                ts REAL
            )
        """)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                message_id TEXT,
                helpful INTEGER,
                ts REAL
            )
        """)
        _conn.commit()


_init_db()


def create_session() -> str:
    session_id = str(uuid.uuid4())
    with _lock:
        _conn.execute(
            "INSERT INTO sessions (session_id, created_at, state_json, pending) VALUES (?, ?, ?, 0)",
            (session_id, time.time(), json.dumps({})),
        )
        _conn.commit()
    return session_id


def session_exists(session_id: str) -> bool:
    with _lock:
        cur = _conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
        return cur.fetchone() is not None


def get_state(session_id: str) -> dict:
    with _lock:
        cur = _conn.execute("SELECT state_json FROM sessions WHERE session_id = ?", (session_id,))
        row = cur.fetchone()
    if not row:
        return {}
    return json.loads(row[0])


def set_state(session_id: str, state: dict):
    with _lock:
        _conn.execute(
            "UPDATE sessions SET state_json = ? WHERE session_id = ?",
            (json.dumps(state), session_id),
        )
        _conn.commit()


def try_acquire_pending(session_id: str) -> bool:
    """Returns True if this call acquired the 'pending' lock for the
    session (i.e. no other request is currently being processed for it).
    Used to reject duplicate/overlapping submissions."""
    with _lock:
        cur = _conn.execute("SELECT pending FROM sessions WHERE session_id = ?", (session_id,))
        row = cur.fetchone()
        if not row:
            return False
        if row[0]:
            return False
        _conn.execute("UPDATE sessions SET pending = 1 WHERE session_id = ?", (session_id,))
        _conn.commit()
        return True


def release_pending(session_id: str):
    with _lock:
        _conn.execute("UPDATE sessions SET pending = 0 WHERE session_id = ?", (session_id,))
        _conn.commit()


def delete_session(session_id: str) -> bool:
    with _lock:
        cur = _conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
        exists = cur.fetchone() is not None
        _conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        _conn.execute("DELETE FROM history WHERE session_id = ?", (session_id,))
        _conn.commit()
    return exists


def append_history(session_id: str, role: str, content: str):
    with _lock:
        _conn.execute(
            "INSERT INTO history (session_id, role, content, ts) VALUES (?, ?, ?, ?)",
            (session_id, role, content, time.time()),
        )
        _conn.commit()


def save_feedback(session_id: str, message_id: Optional[str], helpful: bool):
    with _lock:
        _conn.execute(
            "INSERT INTO feedback (session_id, message_id, helpful, ts) VALUES (?, ?, ?, ?)",
            (session_id, message_id, int(helpful), time.time()),
        )
        _conn.commit()


def count_sessions() -> int:
    with _lock:
        cur = _conn.execute("SELECT COUNT(*) FROM sessions")
        return cur.fetchone()[0]
