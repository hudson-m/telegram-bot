import sqlite3
import os
from crypto import encrypt, decrypt

DB_PATH = os.environ.get("DB_PATH", "history.db")


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shopping_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            added_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def add_item(user_id: int, item: str):
    import time
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO shopping_list (user_id, item, added_at) VALUES (?, ?, ?)",
            (user_id, encrypt(item.strip()), time.time())
        )


def list_items(user_id: int) -> list[tuple]:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, item FROM shopping_list WHERE user_id = ? ORDER BY added_at",
            (user_id,)
        ).fetchall()
    return [(row[0], decrypt(row[1])) for row in rows]


def remove_item(user_id: int, item_id: int):
    with _get_db() as conn:
        conn.execute(
            "DELETE FROM shopping_list WHERE id = ? AND user_id = ?",
            (item_id, user_id)
        )


def clear_list(user_id: int):
    with _get_db() as conn:
        conn.execute("DELETE FROM shopping_list WHERE user_id = ?", (user_id,))
