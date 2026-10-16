"""SQLite layer: usage log, users directory, sent-reminder bookkeeping.

Knows nothing about Telegram. Writes are best-effort: a database error is
logged but never stops the bot. Connections are short-lived (one per operation)
because handlers and jobs run concurrently.
Timestamps are naive local time in settings.LOCAL_TZ, ISO-8601.
"""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Iterator, Optional

import settings

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 3

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS usage_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT    NOT NULL,
    kind       TEXT    NOT NULL,   -- command | alert | status | system | unknown | denied
    direction  TEXT    NOT NULL,   -- inbound | outbound
    command    TEXT,
    user_id    INTEGER,
    username   TEXT,
    first_name TEXT,
    chat_id    INTEGER,
    chat_type  TEXT,
    text_sent  TEXT,
    allowed    INTEGER NOT NULL DEFAULT 1,
    delivery   TEXT,               -- sent | failed | denied | skipped
    error      TEXT,
    match_uid  TEXT,
    extra      TEXT                -- free-form JSON
);

CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY,
    username     TEXT,
    first_name   TEXT,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    total_events INTEGER NOT NULL DEFAULT 0,
    denied_count INTEGER NOT NULL DEFAULT 0,
    last_command TEXT
);

CREATE INDEX IF NOT EXISTS idx_usage_log_ts      ON usage_log(ts);
CREATE INDEX IF NOT EXISTS idx_usage_log_user_id ON usage_log(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_log_kind    ON usage_log(kind);

-- v3: kickoff is part of the key, so a rescheduled match gets fresh reminders.
CREATE TABLE IF NOT EXISTS match_alerts (
    match_uid  TEXT    NOT NULL,
    alert_type TEXT    NOT NULL,   -- e.g. '10m'
    kickoff    TEXT    NOT NULL,   -- local ISO kick-off time (minutes precision)
    sent       INTEGER NOT NULL DEFAULT 0,
    sent_at    TEXT    NOT NULL,
    PRIMARY KEY (match_uid, alert_type, kickoff)
);

PRAGMA user_version = {SCHEMA_VERSION};
"""

_LOG_COLUMNS = (
    "ts", "kind", "direction", "command", "user_id", "username", "first_name",
    "chat_id", "chat_type", "text_sent", "allowed", "delivery", "error",
    "match_uid", "extra",
)


def _now() -> datetime:
    return datetime.now(settings.LOCAL_TZ).replace(tzinfo=None)


def now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _cutoff(days: int) -> str:
    return (_now() - timedelta(days=days)).isoformat(timespec="seconds")


@contextmanager
def connect(readonly: bool = False) -> Iterator[sqlite3.Connection]:
    """Short-lived connection. Use readonly=True for reporting."""
    path = settings.DB_PATH
    if readonly:
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5)
    else:
        conn = sqlite3.connect(str(path), timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables. Called once at startup (fail fast)."""
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")  # persistent, so set once here
        # match_alerts changed shape in v3. It only de-duplicates reminders, so
        # dropping the old table is safe (worst case: one repeated reminder).
        if conn.execute("PRAGMA user_version").fetchone()[0] < 3:
            conn.execute("DROP TABLE IF EXISTS match_alerts")
        conn.executescript(_SCHEMA)
    logger.info("دیتابیس لاگ آماده است: %s", settings.DB_PATH)


def cleanup_old_data(alert_days: int, log_days: int) -> dict:
    """Retention: old reminder rows and old usage_log rows (message texts, user ids)."""
    try:
        with connect() as conn:
            a = conn.execute("DELETE FROM match_alerts WHERE sent_at < ?", (_cutoff(alert_days),))
            l = conn.execute("DELETE FROM usage_log WHERE ts < ?", (_cutoff(log_days),))
            return {"alerts": a.rowcount, "log": l.rowcount}
    except sqlite3.Error as e:
        logger.exception("خطا در پاک‌سازی داده‌های قدیمی: %s", e)
        return {"alerts": 0, "log": 0}


# ---------- writing ----------

def log_event(
    *,
    kind: str,
    direction: str,
    command: Optional[str] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    chat_id: Optional[int] = None,
    chat_type: Optional[str] = None,
    text_sent: Optional[str] = None,
    allowed: bool = True,
    delivery: Optional[str] = None,
    error: Optional[str] = None,
    match_uid: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """Insert one usage_log row. Best-effort: never raises."""
    row: dict = {
        "ts": now_iso(), "kind": kind, "direction": direction, "command": command,
        "user_id": user_id, "username": username, "first_name": first_name,
        "chat_id": chat_id, "chat_type": chat_type, "text_sent": text_sent,
        "allowed": 1 if allowed else 0, "delivery": delivery, "error": error,
        "match_uid": match_uid,
        "extra": json.dumps(extra, ensure_ascii=False) if extra else None,
    }
    try:
        with connect() as conn:
            conn.execute(
                f"INSERT INTO usage_log ({','.join(_LOG_COLUMNS)}) "
                f"VALUES ({','.join('?' * len(_LOG_COLUMNS))})",
                [row[c] for c in _LOG_COLUMNS],
            )
    except sqlite3.Error as e:
        logger.exception("خطا در ثبت رویداد (%s/%s): %s", kind, direction, e)


def upsert_user(
    *,
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    command: Optional[str] = None,
    denied: bool = False,
) -> None:
    ts = now_iso()
    try:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO users
                    (user_id, username, first_name, first_seen, last_seen,
                     total_events, denied_count, last_command)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username     = excluded.username,
                    first_name   = excluded.first_name,
                    last_seen    = excluded.last_seen,
                    total_events = total_events + 1,
                    denied_count = denied_count + excluded.denied_count,
                    last_command = COALESCE(excluded.last_command, last_command)
                """,
                (user_id, username, first_name, ts, ts, 1 if denied else 0, command),
            )
    except sqlite3.Error as e:
        logger.exception("خطا در به‌روزرسانی کاربر %s: %s", user_id, e)


# ---------- reminder bookkeeping ----------

def alert_pending(match_uid: str, alert_type: str, kickoff: str) -> bool:
    """True if this reminder still has to be sent.

    Registers the reminder on first sight (atomic INSERT OR IGNORE), so it
    survives restarts. On a database error it answers True (better a repeated
    reminder than a missing one).
    """
    try:
        with connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO match_alerts (match_uid, alert_type, kickoff, sent, sent_at) "
                "VALUES (?, ?, ?, 0, ?)",
                (match_uid, alert_type, kickoff, now_iso()),
            )
            row = conn.execute(
                "SELECT sent FROM match_alerts WHERE match_uid=? AND alert_type=? AND kickoff=?",
                (match_uid, alert_type, kickoff),
            ).fetchone()
            return not row["sent"]
    except sqlite3.Error as e:
        logger.exception("خطا در بررسی وضعیت هشدار: %s", e)
        return True


def mark_alert_sent(match_uid: str, alert_type: str, kickoff: str) -> None:
    try:
        with connect() as conn:
            conn.execute(
                "UPDATE match_alerts SET sent = 1, sent_at = ? "
                "WHERE match_uid=? AND alert_type=? AND kickoff=?",
                (now_iso(), match_uid, alert_type, kickoff),
            )
    except sqlite3.Error as e:
        logger.exception("خطا در به‌روزرسانی وضعیت هشدار: %s", e)


# ---------- reading (for /usage and report.py) ----------

def query_events(
    *,
    days: Optional[int] = None,
    user_id: Optional[int] = None,
    command: Optional[str] = None,
    kind: Optional[str] = None,
    limit: Optional[int] = None,
) -> list:
    sql, params = "SELECT * FROM usage_log WHERE 1=1", []
    if days:
        sql += " AND ts >= ?"
        params.append(_cutoff(days))
    if user_id is not None:
        sql += " AND user_id = ?"
        params.append(user_id)
    if command:
        sql += " AND command = ?"
        params.append(command)
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    sql += " ORDER BY id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with connect(readonly=True) as conn:
        return conn.execute(sql, params).fetchall()


def counts_by(field: str) -> dict:
    """Event counts grouped by one whitelisted column."""
    if field not in ("kind", "command", "direction", "delivery"):
        raise ValueError(f"ستون غیرمجاز: {field}")
    with connect(readonly=True) as conn:
        rows = conn.execute(
            f"SELECT COALESCE({field}, '—') AS key, COUNT(*) AS n "
            f"FROM usage_log GROUP BY {field} ORDER BY n DESC"
        ).fetchall()
    return {r["key"]: r["n"] for r in rows}


def top_users(limit: int = 10) -> list:
    with connect(readonly=True) as conn:
        return conn.execute(
            "SELECT * FROM users ORDER BY total_events DESC, last_seen DESC LIMIT ?", (limit,)
        ).fetchall()


def total_events() -> int:
    with connect(readonly=True) as conn:
        return conn.execute("SELECT COUNT(*) FROM usage_log").fetchone()[0]


def distinct_users() -> int:
    with connect(readonly=True) as conn:
        return conn.execute("SELECT COUNT(DISTINCT user_id) FROM usage_log").fetchone()[0]


def events_count_since(days: int) -> int:
    with connect(readonly=True) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM usage_log WHERE ts >= ?", (_cutoff(days),)
        ).fetchone()[0]
