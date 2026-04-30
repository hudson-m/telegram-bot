import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "history.db")


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_reminders (
            event_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            reminder_type TEXT NOT NULL DEFAULT 'soon',
            PRIMARY KEY (event_id, user_id, reminder_type)
        )
    """)
    conn.commit()
    return conn


def is_reminder_sent(user_id: int, event_id: str, reminder_type: str = "soon") -> bool:
    with _get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM sent_reminders WHERE event_id = ? AND user_id = ? AND reminder_type = ?",
            (event_id, user_id, reminder_type)
        ).fetchone()
    return row is not None


def mark_reminder_sent(user_id: int, event_id: str, reminder_type: str = "soon"):
    with _get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sent_reminders (event_id, user_id, reminder_type) VALUES (?, ?, ?)",
            (event_id, user_id, reminder_type)
        )


def _ensure_filter_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminder_filters (
            user_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            PRIMARY KEY (user_id, keyword)
        )
    """)
    conn.commit()


def block_keyword(user_id: int, keyword: str):
    with _get_db() as conn:
        _ensure_filter_table(conn)
        conn.execute(
            "INSERT OR IGNORE INTO reminder_filters (user_id, keyword) VALUES (?, ?)",
            (user_id, keyword.lower().strip())
        )


def unblock_keyword(user_id: int, keyword: str):
    with _get_db() as conn:
        _ensure_filter_table(conn)
        conn.execute(
            "DELETE FROM reminder_filters WHERE user_id = ? AND keyword = ?",
            (user_id, keyword.lower().strip())
        )


def get_blocked_keywords(user_id: int) -> list[str]:
    with _get_db() as conn:
        _ensure_filter_table(conn)
        rows = conn.execute(
            "SELECT keyword FROM reminder_filters WHERE user_id = ?",
            (user_id,)
        ).fetchall()
    return [r[0] for r in rows]


def is_event_blocked(user_id: int, event_summary: str) -> bool:
    keywords = get_blocked_keywords(user_id)
    summary_lower = event_summary.lower()
    return any(kw in summary_lower for kw in keywords)
