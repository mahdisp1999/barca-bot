"""SQLite layer: usage log, users directory, sent-reminder bookkeeping,
and the match state (watched matches and sent results). One file: DB_PATH.

Knows nothing about Telegram. Writes are best-effort: a database error is
logged but never stops the bot. Connections are short-lived (one per operation)
because handlers and jobs run concurrently.
Timestamps are naive local time in settings.LOCAL_TZ, ISO-8601.

Old files (usage.db, bot_state.json) are imported ONCE on the first start.
"""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator, Optional

import settings

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 5

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

-- v4: one row per (match, alert_type, kickoff, user_id) so every allowed user
-- gets the reminder/result exactly once.
CREATE TABLE IF NOT EXISTS match_alerts (
    match_uid  TEXT    NOT NULL,
    alert_type TEXT    NOT NULL,   -- '5m' | '10m' | ... | 'result'
    kickoff    TEXT    NOT NULL,
    user_id    INTEGER NOT NULL,
    sent       INTEGER NOT NULL DEFAULT 0,
    sent_at    TEXT    NOT NULL,
    PRIMARY KEY (match_uid, alert_type, kickoff, user_id)
);

-- v5: matches waiting for their result (was bot_state.json "watched").
CREATE TABLE IF NOT EXISTS watched_matches (
    match_uid TEXT PRIMARY KEY,
    kickoff   TEXT NOT NULL,
    summary   TEXT NOT NULL
);

-- v5: results already sent, in order (was bot_state.json "result_sent").
CREATE TABLE IF NOT EXISTS result_sent (
    seq       INTEGER PRIMARY KEY AUTOINCREMENT,
    match_uid TEXT NOT NULL
);

-- v5: small key/value facts, e.g. legacy_imported (migration done once).
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
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
    """Create tables and import old data once. Called at startup (fail fast)."""
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")  # persistent, so set once here
        # match_alerts changed shape in v4 (per-user rows). It only de-duplicates
        # reminders, so dropping the old table is safe (worst case: one repeated
        # reminder per user).
        if conn.execute("PRAGMA user_version").fetchone()[0] < 4:
            conn.execute("DROP TABLE IF EXISTS match_alerts")
        conn.executescript(_SCHEMA)
        _import_legacy(conn)
    logger.info("دیتابیس لاگ آماده است: %s", settings.DB_PATH)


def cleanup_old_data(alert_days: int, log_days: int) -> dict:
    """Retention: old reminder rows and old usage_log rows (message texts, user ids)."""
    try:
        with connect() as conn:
            a = conn.execute("DELETE FROM match_alerts WHERE sent_at < ?", (_cutoff(alert_days),))
            log = conn.execute("DELETE FROM usage_log WHERE ts < ?", (_cutoff(log_days),))
            return {"alerts": a.rowcount, "log": log.rowcount}
    except sqlite3.Error as e:
        logger.exception("خطا در پاک‌سازی داده‌های قدیمی: %s", e)
        return {"alerts": 0, "log": 0}


# ---------- one-time import of the old files ----------

def _import_legacy(conn: sqlite3.Connection) -> None:
    """Runs once. Copies usage.db and bot_state.json into this database."""
    if conn.execute("SELECT 1 FROM meta WHERE key = 'legacy_imported'").fetchone():
        return
    if settings.LEGACY_DB_PATH.is_file():
        _copy_legacy_db(conn)
    if settings.LEGACY_STATE_FILE.is_file():
        _copy_legacy_state(conn)
    conn.execute("INSERT INTO meta (key, value) VALUES ('legacy_imported', ?)", (now_iso(),))
    logger.info("داده‌ی نسخه‌ی قبلی به %s منتقل شد.", settings.DB_PATH)


def _copy_legacy_db(conn: sqlite3.Connection) -> None:
    src = sqlite3.connect(str(settings.LEGACY_DB_PATH), timeout=5)
    try:
        cols = ",".join(_LOG_COLUMNS)
        rows = src.execute(f"SELECT {cols} FROM usage_log ORDER BY id").fetchall()
        conn.executemany(
            f"INSERT INTO usage_log ({cols}) VALUES ({','.join('?' * len(_LOG_COLUMNS))})",
            rows,
        )
        users = src.execute(
            "SELECT user_id, username, first_name, first_seen, last_seen, "
            "total_events, denied_count, last_command FROM users"
        ).fetchall()
        conn.executemany(
            "INSERT OR REPLACE INTO users (user_id, username, first_name, first_seen, last_seen, "
            "total_events, denied_count, last_command) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [tuple(u) for u in users],
        )
        # Old match_alerts before v4 had another shape: skip it (worst case: one repeated reminder).
        if src.execute("PRAGMA user_version").fetchone()[0] >= 4:
            alerts = src.execute(
                "SELECT match_uid, alert_type, kickoff, user_id, sent, sent_at FROM match_alerts"
            ).fetchall()
            conn.executemany(
                "INSERT OR IGNORE INTO match_alerts (match_uid, alert_type, kickoff, user_id, sent, sent_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [tuple(a) for a in alerts],
            )
    finally:
        src.close()


def _copy_legacy_state(conn: sqlite3.Connection) -> None:
    try:
        with open(settings.LEGACY_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("bot_state.json قدیمی خوانده نشد و نادیده گرفته شد: %s", e)
        return
    if not isinstance(data, dict):
        return
    watched = data.get("watched") or {}
    conn.executemany(
        "INSERT OR REPLACE INTO watched_matches (match_uid, kickoff, summary) VALUES (?, ?, ?)",
        [(uid, e["ts"], e["summary"]) for uid, e in watched.items()],
    )
    conn.executemany(
        "INSERT INTO result_sent (match_uid) VALUES (?)",
        [(uid,) for uid in (data.get("result_sent") or [])],
    )


# ---------- match state (watched + result_sent) ----------

def load_state() -> dict:
    """Returns {'watched': {uid: {ts, summary}}, 'result_sent': [uid, ...]}."""
    try:
        with connect(readonly=True) as conn:
            watched = {
                r["match_uid"]: {"ts": r["kickoff"], "summary": r["summary"]}
                for r in conn.execute("SELECT match_uid, kickoff, summary FROM watched_matches")
            }
            sent = [
                r["match_uid"]
                for r in conn.execute("SELECT match_uid FROM result_sent ORDER BY seq")
            ]
        return {"watched": watched, "result_sent": sent}
    except sqlite3.Error as e:
        logger.exception("خطا در خواندن وضعیت بازی‌ها: %s", e)
        return {"watched": {}, "result_sent": []}


def save_state(state: dict) -> None:
    """Writes the whole state again (it is small). Best-effort."""
    try:
        with connect() as conn:
            conn.execute("DELETE FROM watched_matches")
            conn.executemany(
                "INSERT INTO watched_matches (match_uid, kickoff, summary) VALUES (?, ?, ?)",
                [(uid, e["ts"], e["summary"]) for uid, e in state["watched"].items()],
            )
            conn.execute("DELETE FROM result_sent")
            conn.executemany(
                "INSERT INTO result_sent (match_uid) VALUES (?)",
                [(uid,) for uid in state["result_sent"]],
            )
    except sqlite3.Error as e:
        logger.exception("خطا در ذخیره‌ی وضعیت بازی‌ها: %s", e)


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

def alert_pending(match_uid: str, alert_type: str, kickoff: str, user_id: int) -> bool:
    """True if this reminder still has to be sent to this user.

    Registers the reminder on first sight (atomic INSERT OR IGNORE), so it
    survives restarts. On a database error it answers True (better a repeated
    reminder than a missing one).
    """
    try:
        with connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO match_alerts "
                "(match_uid, alert_type, kickoff, user_id, sent, sent_at) "
                "VALUES (?, ?, ?, ?, 0, ?)",
                (match_uid, alert_type, kickoff, user_id, now_iso()),
            )
            row = conn.execute(
                "SELECT sent FROM match_alerts "
                "WHERE match_uid=? AND alert_type=? AND kickoff=? AND user_id=?",
                (match_uid, alert_type, kickoff, user_id),
            ).fetchone()
            return not row["sent"]
    except sqlite3.Error as e:
        logger.exception("خطا در بررسی وضعیت هشدار: %s", e)
        return True


def mark_alert_sent(match_uid: str, alert_type: str, kickoff: str, user_id: int) -> None:
    try:
        with connect() as conn:
            conn.execute(
                "UPDATE match_alerts SET sent = 1, sent_at = ? "
                "WHERE match_uid=? AND alert_type=? AND kickoff=? AND user_id=?",
                (now_iso(), match_uid, alert_type, kickoff, user_id),
            )
    except sqlite3.Error as e:
        logger.exception("خطا در به‌روزرسانی وضعیت هشدار: %s", e)


def last_sent_at(user_id: int) -> Optional[datetime]:
    """زمان آخرین پیام موفق ربات به این کاربر (از usage_log)."""
    try:
        with connect(readonly=True) as conn:
            row = conn.execute(
                "SELECT MAX(ts) AS t FROM usage_log "
                "WHERE user_id = ? AND direction = 'outbound' AND delivery = 'sent'",
                (user_id,),
            ).fetchone()
        return datetime.fromisoformat(row["t"]) if row["t"] else None
    except sqlite3.Error as e:
        logger.exception("خطا در خواندن آخرین پیام کاربر %s: %s", user_id, e)
        return None


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