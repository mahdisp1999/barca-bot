"""Settings: .env loading, paths and constants.

Imports nothing from this project, so it can never be part of an import cycle.
Real environment variables win over values in .env.
"""
import logging
import os
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo
from datetime import time

_log = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_env_file(ROOT_DIR / ".env")


def _int(name: str, default: int = 0) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        _log.warning("مقدار نامعتبر برای %s: %r — پیش‌فرض %s استفاده می‌شود.", name, raw, default)
        return default


def _int_list(name: str) -> List[int]:
    out = []
    for part in os.getenv(name, "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            _log.warning("مقدار نامعتبر در %s نادیده گرفته شد: %r", name, part)
    return out


def _path(name: str, default: str) -> Path:
    p = Path(os.getenv(name, default))
    return p if p.is_absolute() else ROOT_DIR / p


# ---------- Telegram ----------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_ID = _int("TELEGRAM_ADMIN_ID", 0)
ALLOWED_USERS = _int_list("ALLOWED_USERS")
# Single source of truth for access control: allowed users + admin.
# Empty set => everybody is allowed (a warning is logged at startup).
ALLOWED_IDS = set(ALLOWED_USERS) | ({ADMIN_ID} if ADMIN_ID else set())
# Telegram is filtered in Iran, so the default goes through the author's proxy.
BOT_API_BASE_URL = os.getenv(
    "BOT_API_BASE_URL", "https://tg-proxy.mmsalehpoor.workers.dev/bot"
)

# ---------- football data (SportsAPI Pro) ----------
SPORTS_API_KEY = os.getenv("SPORTS_API_KEY", "")
SPORTS_API_BASE_URL = os.getenv(
    "SPORTS_API_BASE_URL", "https://api.sportsapipro.com/v2/football"
).rstrip("/")
TEAM_ID = os.getenv("TEAM_ID", "2817").strip()  # FC Barcelona (verify with a real response)
LOCAL_TZ = ZoneInfo(os.getenv("LOCAL_TZ", "Asia/Tehran"))
REQUEST_TIMEOUT = 10  # seconds
CACHE_TTL_NEXT = 24 * 3600  # seconds; the API quota is shared, so cache hard
CACHE_TTL_LAST = 6 * 3600  # results are fetched with force=True by the result job
RETRY_AFTER_FAILURE = 60  # base back-off after a failed call (doubles per failure)
RATE_LIMIT_BACKOFF = 15 * 60  # first back-off after HTTP 429 (when no Retry-After header)
MAX_BACKOFF = 3600  # back-off never exceeds this (seconds)
MIN_REFRESH_INTERVAL = 30  # /sync spam protection (seconds)
DAILY_SYNC_AT = time(8, 0, tzinfo=LOCAL_TZ)
NEAR_KICKOFF_WINDOW_MIN = 120   # از این فاصله به بعد روز بازی حساب میشه
NEAR_KICKOFF_TTL = 10 * 60      # کش روز بازی

# ---------- reminders / results ----------
_DEFAULT_REMINDERS = [5, 10, 15, 30, 60]
REMINDER_MINUTES = sorted({m for m in _int_list("REMINDER_MINUTES") if m > 0}) or list(
    _DEFAULT_REMINDERS
)
REMINDER_GRACE_MIN = 3  # a reminder may be at most this many minutes late
REMINDER_CHECK_INTERVAL = 60  # seconds; cache-only, costs no API quota
RESULT_CHECK_INTERVAL = 600  # seconds; may call the API
RESULT_CHECK_AFTER_MIN = 90  # start looking for a result this long after kick-off
RESULT_GIVE_UP_AFTER_H = 6  # postponed/abandoned matches are dropped after this
RESULT_HISTORY = 50  # how many already-sent result uids to remember
AUTO_STATUS_WINDOW_H = 24  # auto status when the next match is closer than this...
AUTO_STATUS_QUIET_H = 12  # ...and THAT USER got no message for this long
AUTO_STATUS_RETRY_H = 1  # do not retry an auto status to the same user more often than this

# ---------- storage ----------
DB_PATH = _path("DB_PATH", "usage.db")
STATE_FILE = _path("STATE_FILE", "bot_state.json")
CACHE_FILE = _path("CACHE_FILE", "api_cache.json")  # last good API data, survives restarts
LOG_RETENTION_DAYS = _int("LOG_RETENTION_DAYS", 180)
ALERT_RETENTION_DAYS = 30

# ---------- ICS calendar ----------
# آدرس فایل ICS باشگاه بارسلونا (یا هر منبع دلخواه دیگر).
# مثال: "https://www.fcbarcelona.com/calendar.ics"
ICS_URL = os.getenv("ICS_URL", "").strip()
# مسیر ذخیرهٔ فایل ICS دانلودشده روی دیسک؛ نسبی از ROOT_DIR یا مطلق.
ICS_PATH = _path("ICS_PATH", "barcelona.ics")
# فاصلهٔ زمانی بین دو دانلود متوالی فایل ICS، بر حسب ثانیه.
# پیشنهاد: 6 * 3600 (هر ۶ ساعت) یا 12 * 3600 (هر ۱۲ ساعت) برای مصرف کم.
ICS_DOWNLOAD_INTERVAL = _int("ICS_DOWNLOAD_INTERVAL", 6 * 3600)
