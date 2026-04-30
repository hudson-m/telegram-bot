import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "history.db")


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_reminders (
            event_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (event_id, user_id)
        )
    """)
    conn.commit()
    return conn


def is_reminder_sent(user_id: int, event_id: str) -> bool:
    with _get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM sent_reminders WHERE event_id = ? AND user_id = ?",
            (event_id, user_id)
        ).fetchone()
    return row is not None


def mark_reminder_sent(user_id: int, event_id: str):
    with _get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sent_reminders (event_id, user_id) VALUES (?, ?)",
            (event_id, user_id)
        )
