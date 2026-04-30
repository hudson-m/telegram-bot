import sqlite3
import os
import time

DB_PATH = os.environ.get("DB_PATH", "history.db")


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def add_note(user_id: int, content: str) -> int:
    with _get_db() as conn:
        cur = conn.execute(
            "INSERT INTO notes (user_id, content, created_at) VALUES (?, ?, ?)",
            (user_id, content.strip(), time.time())
        )
        return cur.lastrowid


def search_notes(user_id: int, query: str) -> list[tuple]:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM notes WHERE user_id = ? AND content LIKE ? ORDER BY created_at DESC LIMIT 10",
            (user_id, f"%{query}%")
        ).fetchall()
    return rows


def list_notes(user_id: int) -> list[tuple]:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at FROM notes WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
            (user_id,)
        ).fetchall()
    return rows


def delete_note(user_id: int, note_id: int):
    with _get_db() as conn:
        conn.execute(
            "DELETE FROM notes WHERE id = ? AND user_id = ?",
            (note_id, user_id)
        )
