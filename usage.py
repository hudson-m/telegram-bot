import sqlite3
import os
import time

DB_PATH = os.environ.get("DB_PATH", "history.db")

PRICING = {
    "claude-sonnet-4-6":        {"input": 3.0,  "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
}


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cost_usd REAL NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def log_usage(model: str, input_tokens: int, output_tokens: int):
    prices = PRICING.get(model, {"input": 3.0, "output": 15.0})
    cost = (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO api_usage (model, input_tokens, output_tokens, cost_usd, created_at) VALUES (?, ?, ?, ?, ?)",
            (model, input_tokens, output_tokens, cost, time.time())
        )


def get_daily_usage(days: int = 30) -> list[dict]:
    since = time.time() - days * 86400
    with _get_db() as conn:
        rows = conn.execute("""
            SELECT date(created_at, 'unixepoch', 'localtime') as day,
                   SUM(input_tokens) as input_tokens,
                   SUM(output_tokens) as output_tokens,
                   SUM(cost_usd) as cost_usd
            FROM api_usage
            WHERE created_at >= ?
            GROUP BY day
            ORDER BY day
        """, (since,)).fetchall()
    return [{"day": r[0], "input_tokens": r[1], "output_tokens": r[2], "cost_usd": round(r[3], 4)} for r in rows]


def get_totals() -> dict:
    now = time.time()
    with _get_db() as conn:
        def query(since):
            row = conn.execute(
                "SELECT SUM(input_tokens), SUM(output_tokens), SUM(cost_usd) FROM api_usage WHERE created_at >= ?",
                (since,)
            ).fetchone()
            return {"input_tokens": row[0] or 0, "output_tokens": row[1] or 0, "cost_usd": round(row[2] or 0, 4)}
        return {
            "today":    query(now - 86400),
            "week":     query(now - 7 * 86400),
            "month":    query(now - 30 * 86400),
            "all_time": query(0),
        }
