"""لایه‌ی داده: دفتر حسابرسی استفاده از ربات (usage audit log).

فقط از کتابخانه‌ی استاندارد پایتون استفاده می‌کند (sqlite3).
این ماژول هیچ اطلاعی از تلگرام ندارد؛ bot.py یک dict ساده به آن می‌دهد.

قراردادها (مطابق Architecture.md):
- مُهر زمانی: naive و محلی، ISO-8601 (هم‌راستا با datetime.now() در کل پروژه)
- اتصال SQLite: کوتاه‌مدت به ازای هر عملیات (Job Queue و هندلرها هم‌زمان‌اند)
- نوشتن: best-effort — خطای دیتابیس هرگز نباید ربات را از کار بیندازد
"""

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# مسیر نسبی بر اساس پوشه‌ی پروژه تفسیر می‌شود، نه پوشه‌ی فعلی اجرا
DB_PATH = os.getenv("DB_PATH", "usage.db")
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.join(_BASE_DIR, DB_PATH)
SCHEMA_VERSION = 2

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
    extra      TEXT                -- JSON آزاد
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

CREATE TABLE IF NOT EXISTS match_alerts (
    match_uid  TEXT    NOT NULL,          -- UID یکتا هر بازی از فایل ICS
    alert_type TEXT    NOT NULL,           -- مثال: '5m' | '10m' | '30m' | '60m' (دقیقه‌های یادآوری)
    sent_at    TEXT    NOT NULL,           -- زمان ارسال (ISO-8601 محلی)
    sent       INTEGER NOT NULL DEFAULT 0, -- 1 اگر موفق، 0 اگر هنوز ارسال نشده/شکست‌خورده
    match_key  TEXT    NOT NULL,           -- کلید ترکیبی یکتا برای هشدار
    PRIMARY KEY (match_uid, alert_type)
);

CREATE INDEX IF NOT EXISTS idx_match_alerts_match_uid ON match_alerts(match_uid);

PRAGMA user_version = {SCHEMA_VERSION};
"""

_LOG_COLUMNS = (
    "ts", "kind", "direction", "command", "user_id", "username", "first_name",
    "chat_id", "chat_type", "text_sent", "allowed", "delivery", "error",
    "match_uid", "extra",
)


def now_iso() -> str:
    """مُهر زمانی محلی به صورت ISO-8601."""
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect(readonly: bool = False) -> Iterator[sqlite3.Connection]:
    """اتصال کوتاه‌مدت به دیتابیس. برای گزارش‌گیری از readonly=True استفاده کنید."""
    if readonly:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """ساخت جداول و ایندکس‌ها. در main() صدا زده می‌شود (fail fast)."""
    with connect() as conn:
        conn.executescript(_SCHEMA)
    logger.info(f"دیتابیس لاگ آماده است: {DB_PATH}")


# ---------- نوشتن ----------

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
    """درج یک ردیف در usage_log. best-effort: هیچ استثنایی به بیرون نمی‌دهد."""
    row: dict[str, Any] = {
        "ts": now_iso(),
        "kind": kind,
        "direction": direction,
        "command": command,
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "chat_id": chat_id,
        "chat_type": chat_type,
        "text_sent": text_sent,
        "allowed": 1 if allowed else 0,
        "delivery": delivery,
        "error": error,
        "match_uid": match_uid,
        "extra": extra,
    }
    try:
        values = [row[c] for c in _LOG_COLUMNS]
        with connect() as conn:
            conn.execute(
                f"INSERT INTO usage_log ({','.join(_LOG_COLUMNS)}) "
                f"VALUES ({','.join('?' * len(_LOG_COLUMNS))})",
                values,
            )
    except sqlite3.Error as e:
        logger.exception(f"خطا در ثبت رویداد ({kind}/{direction}): {e}")


def upsert_user(
    *,
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    command: Optional[str] = None,
    denied: bool = False,
) -> None:
    """به‌روزرسانی دایرکتوری کاربران. best-effort."""
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
                (
                    user_id, username, first_name, ts, ts,
                    1 if denied else 0, command,
                ),
            )
    except sqlite3.Error as e:
        logger.exception(f"خطا در به‌روزرسانی کاربر {user_id}: {e}")


# ---------- match_alerts helpers ----------

def is_alert_sent(match_uid: str, alert_type: str, match_key: str) -> bool:
    """بررسی اینکه آیا یک هشدار خاص برای بازی ارسال شده است یا نه.

    استفاده می‌شود تا از ارسال تکراری هشدارها بعد از ریستارت ربات جلوگیری شود.
    """
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT sent FROM match_alerts WHERE match_uid = ? AND alert_type = ?",
                (match_uid, alert_type),
            ).fetchone()
            # اگر ردیف وجود نداشت، هشدر هنوز ارسال نشده — ثبت اولیه می‌کنیم
            if row is None:
                conn.execute(
                    "INSERT INTO match_alerts (match_uid, alert_type, sent_at, sent, match_key) "
                    "VALUES (?, ?, ?, 0, ?)",
                    (match_uid, alert_type, now_iso(), match_key),
                )
                return False
            # اگر sent = 0 بود، یعنی قبلاً در حالت شکست‌خورده یا در انتظار — دوباره سعی شود
            # اگر sent = 1 بود یعنی موفق بوده
            return bool(row["sent"])
    except sqlite3.Error as e:
        logger.exception(f"خطا در بررسی وضعیت هشدار: {e}")
        return False


def mark_alert_sent(match_uid: str, alert_type: str, match_key: str) -> None:
    """علامت‌گذاری یک هشدار به عنوان موفق‌ارسالی در دیتابیس."""
    try:
        with connect() as conn:
            conn.execute(
                "UPDATE match_alerts SET sent = 1, sent_at = ? "
                "WHERE match_uid = ? AND alert_type = ? AND match_key = ?",
                (now_iso(), match_uid, alert_type, match_key),
            )
    except sqlite3.Error as e:
        logger.exception(f"خطا در به‌روزرسانی وضعیت هشدار: {e}")


def cleanup_old_alerts(days: int = 30) -> int:
    """حذف هشدارهای قدیمی‌تر از N روز. برای جلوگیری از رشد نامحدود دیتابیس."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    try:
        with connect() as conn:
            cur = conn.execute(
                "DELETE FROM match_alerts WHERE sent_at < ?", (cutoff,)
            )
            return cur.rowcount if cur.rowcount is not None else 0
    except sqlite3.Error as e:
        logger.exception(f"خطا در پاک‌سازی هشدارهای قدیمی: {e}")
        return 0
# --------------------------------


# ---------- خواندن (برای /usage و report.py) ----------

def recent_events(limit: int = 20) -> list:
    with connect(readonly=True) as conn:
        return conn.execute(
            "SELECT * FROM usage_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


def events_since(days: int) -> list:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with connect(readonly=True) as conn:
        return conn.execute(
            "SELECT * FROM usage_log WHERE ts >= ? ORDER BY id DESC", (cutoff,)
        ).fetchall()


def events_for_user(user_id: int, limit: int = 50) -> list:
    with connect(readonly=True) as conn:
        return conn.execute(
            "SELECT * FROM usage_log WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


def counts_by(field: str) -> dict:
    """شمارش رویدادها بر اساس یک ستون امن (field باید از لیست مجاز باشد)."""
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
            "SELECT * FROM users ORDER BY total_events DESC, last_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()


def all_users() -> list:
    with connect(readonly=True) as conn:
        return conn.execute(
            "SELECT * FROM users ORDER BY last_seen DESC"
        ).fetchall()


def total_events() -> int:
    with connect(readonly=True) as conn:
        return conn.execute("SELECT COUNT(*) FROM usage_log").fetchone()[0]


def distinct_users() -> int:
    with connect(readonly=True) as conn:
        return conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM usage_log"
        ).fetchone()[0]


def events_count_since(days: int) -> int:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with connect(readonly=True) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM usage_log WHERE ts >= ?", (cutoff,)
        ).fetchone()[0]
