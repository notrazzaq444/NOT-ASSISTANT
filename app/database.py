"""SQLite persistence layer.

Users are identified by Firebase UID (a string). No passwords stored here.
Conversations belong to a user via their Firebase UID.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from .config import get_settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    uid TEXT PRIMARY KEY,
    email TEXT,
    display_name TEXT,
    photo_url TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(uid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, id);

CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
    ON conversations(user_id, updated_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db_path() -> Path:
    p = Path(get_settings().db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path(), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()


# ---------- Users ----------

def upsert_user(
    uid: str,
    email: Optional[str],
    display_name: Optional[str],
    photo_url: Optional[str],
) -> dict:
    """Insert or refresh a user from Firebase claims. Returns the stored row."""
    ts = _now()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT uid, is_admin, created_at FROM users WHERE uid = ?", (uid,)
        ).fetchone()

        if existing is None:
            # First ever user becomes admin automatically.
            is_admin = 1 if count_users() == 0 else 0
            conn.execute(
                "INSERT INTO users "
                "(uid, email, display_name, photo_url, is_admin, created_at, last_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uid, email, display_name, photo_url, is_admin, ts, ts),
            )
        else:
            conn.execute(
                "UPDATE users SET email = ?, display_name = ?, photo_url = ?, "
                "last_seen_at = ? WHERE uid = ?",
                (email, display_name, photo_url, ts, uid),
            )
    return get_user(uid)  # type: ignore[return-value]


def get_user(uid: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT uid, email, display_name, photo_url, is_admin, "
            "created_at, last_seen_at FROM users WHERE uid = ?",
            (uid,),
        ).fetchone()
    return dict(row) if row else None


def count_users() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return int(row["n"])


# ---------- Conversations ----------

def create_conversation(user_id: str, title: str = "New chat") -> dict:
    ts = _now()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (user_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, title.strip()[:120] or "New chat", ts, ts),
        )
        cid = cur.lastrowid
    return get_conversation(cid, user_id)  # type: ignore[return-value]


def get_conversation(cid: int, user_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (cid, user_id),
        ).fetchone()
        if row is None:
            return None
        msgs = conn.execute(
            "SELECT id, role, content, created_at FROM messages "
            "WHERE conversation_id = ? ORDER BY id ASC",
            (cid,),
        ).fetchall()
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "messages": [dict(m) for m in msgs],
    }


def list_conversations(user_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id)
                       AS message_count
            FROM conversations c
            WHERE c.user_id = ?
            ORDER BY c.updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def rename_conversation(cid: int, user_id: str, title: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (title.strip()[:120], _now(), cid, user_id),
        )
        return cur.rowcount > 0


def delete_conversation(cid: int, user_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (cid, user_id),
        )
        return cur.rowcount > 0


def clear_all_conversations(user_id: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE user_id = ?", (user_id,)
        )
        return cur.rowcount


# ---------- Messages ----------

def add_message(cid: int, role: str, content: str) -> dict:
    ts = _now()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (cid, role, content, ts),
        )
        mid = cur.lastrowid
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, cid)
        )
    return {"id": mid, "role": role, "content": content, "created_at": ts}


def get_messages(cid: int, limit: Optional[int] = None) -> list[dict]:
    with _connect() as conn:
        if limit is None:
            rows = conn.execute(
                "SELECT id, role, content, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY id ASC",
                (cid,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, role, content, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
                (cid, limit),
            ).fetchall()
            rows = list(reversed(rows))
    return [dict(r) for r in rows]


def count_messages(cid: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?",
            (cid,),
        ).fetchone()
    return int(row["n"])