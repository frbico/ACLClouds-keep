import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path("/data/aclkeep.db")

ACCOUNT_FIELDS = {
    "name",
    "cookie_enc",
    "enabled",
    "project_url",
    "remaining_minutes",
    "last_check_at",
    "last_renew_at",
    "next_check_at",
    "last_status",
    "last_message",
}


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
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                cookie_enc TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                project_url TEXT NOT NULL DEFAULT '',
                remaining_minutes TEXT NOT NULL DEFAULT '',
                last_check_at TEXT NOT NULL DEFAULT '',
                last_renew_at TEXT NOT NULL DEFAULT '',
                next_check_at TEXT NOT NULL DEFAULT '',
                last_status TEXT NOT NULL DEFAULT 'never',
                last_message TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_accounts_enabled_next_check
                ON accounts(enabled, next_check_at);
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


def _account_dict(row) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["enabled"] = bool(item.get("enabled"))
    return item


def count_accounts() -> int:
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM accounts").fetchone()
    return int(row["c"] if row else 0)


def list_accounts(include_disabled: bool = True) -> list[dict[str, Any]]:
    sql = "SELECT * FROM accounts"
    args: tuple[Any, ...] = ()
    if not include_disabled:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY id ASC"
    with connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_account_dict(row) for row in rows]


def get_account(account_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return _account_dict(row)


def create_account(
    name: str,
    cookie_enc: str,
    *,
    enabled: bool = True,
    project_url: str = "",
    remaining_minutes: str = "",
    last_check_at: str = "",
    last_renew_at: str = "",
    next_check_at: str = "",
    last_status: str = "never",
    last_message: str = "",
) -> int:
    now = utc_now_iso()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO accounts(
                name, cookie_enc, enabled, project_url, remaining_minutes,
                last_check_at, last_renew_at, next_check_at,
                last_status, last_message, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                cookie_enc,
                1 if enabled else 0,
                project_url,
                str(remaining_minutes or ""),
                last_check_at,
                last_renew_at,
                next_check_at,
                last_status,
                last_message,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)


def update_account(account_id: int, **fields) -> bool:
    clean = {k: v for k, v in fields.items() if k in ACCOUNT_FIELDS}
    if not clean:
        return get_account(account_id) is not None

    if "enabled" in clean:
        clean["enabled"] = 1 if bool(clean["enabled"]) else 0
    for key, value in list(clean.items()):
        if value is None:
            clean[key] = ""

    clean["updated_at"] = utc_now_iso()
    assignments = ", ".join(f"{key} = ?" for key in clean)
    values = [clean[key] for key in clean]
    values.append(account_id)

    with connect() as conn:
        cur = conn.execute(
            f"UPDATE accounts SET {assignments} WHERE id = ?",
            values,
        )
    return cur.rowcount > 0


def delete_account(account_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    return cur.rowcount > 0


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
