import sqlite3
import json
import time
import os
from crypto import encrypt, decrypt

DB_PATH = os.environ.get("DB_PATH", "history.db")
MAX_MESSAGES = 20


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            user_id INTEGER PRIMARY KEY,
            messages TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def _sanitize_messages(messages: list) -> list:
    # Remove orphaned tool_result/assistant entries from the start.
    # This can happen when MAX_MESSAGES trimming cuts the assistant tool_use
    # message but leaves the matching user tool_result as the first entry.
    while messages:
        first = messages[0]
        role = first.get("role")
        content = first.get("content", "")
        is_orphaned_tool_result = (
            role == "user"
            and isinstance(content, list)
            and bool(content)
            and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
        )
        if role == "assistant" or is_orphaned_tool_result:
            messages = messages[1:]
        else:
            break
    return messages


def get_history(user_id: int) -> list:
    with _get_db() as conn:
        row = conn.execute(
            "SELECT messages, updated_at FROM conversations WHERE user_id = ?",
            (user_id,)
        ).fetchone()
    if not row:
        return []
    messages, updated_at = row
    return _sanitize_messages(json.loads(decrypt(messages)))


def save_history(user_id: int, messages: list):
    trimmed = messages[-MAX_MESSAGES:] if len(messages) > MAX_MESSAGES else messages
    trimmed = _sanitize_messages(list(trimmed))
    with _get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO conversations (user_id, messages, updated_at) VALUES (?, ?, ?)",
            (user_id, encrypt(json.dumps(trimmed)), time.time())
        )


def clear_history(user_id: int):
    with _get_db() as conn:
        conn.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
