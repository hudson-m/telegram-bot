import sqlite3
import json
import time
import os

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


def get_history(user_id: int) -> list:
    with _get_db() as conn:
        row = conn.execute(
            "SELECT messages, updated_at FROM conversations WHERE user_id = ?",
            (user_id,)
        ).fetchone()
    if not row:
        return []
    messages, updated_at = row
    return json.loads(messages)


def save_history(user_id: int, messages: list):
    trimmed = messages[-MAX_MESSAGES:] if len(messages) > MAX_MESSAGES else messages
    with _get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO conversations (user_id, messages, updated_at) VALUES (?, ?, ?)",
            (user_id, json.dumps(trimmed), time.time())
        )


def clear_history(user_id: int):
    with _get_db() as conn:
        conn.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
