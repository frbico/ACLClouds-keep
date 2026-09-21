import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("/data/aclkeep.db")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL
            );
            """
        )


def get_value(key: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_value(key: str, value) -> None:
    if value is None:
        value = ""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO kv(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )


def get_bool(key: str, default: bool = False) -> bool:
    raw = get_value(key, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def set_bool(key: str, value: bool) -> None:
    set_value(key, "1" if value else "0")


def add_event(level: str, message: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events(created_at, level, message) VALUES(?, ?, ?)",
            (utc_now_iso(), level, message),
        )
        conn.execute(
            """
            DELETE FROM events
            WHERE id NOT IN (
                SELECT id FROM events ORDER BY id DESC LIMIT 500
            )
            """
        )


def list_events(limit: int = 100):
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, level, message FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
