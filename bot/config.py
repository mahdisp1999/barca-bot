"""Environment loading + constants. Pure setup, no business logic."""
import logging
import os

import db

# Project root (parent of bot/): .env, bot_state.json, barcelona.ics and
# usage.db all live there, next to db.py.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env_file():
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.isfile(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(
                        key.strip(), val.strip().strip('"').strip("'")
                    )


load_env_file()

# DB_PATH must be applied after .env is loaded (db.py is imported before it).
_env_db_path = os.getenv("DB_PATH")
if _env_db_path and not os.path.isabs(_env_db_path):
    _env_db_path = os.path.join(db._BASE_DIR, _env_db_path)
if _env_db_path:
    db.DB_PATH = _env_db_path

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("barca-bot")

# ---------- settings ----------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))
ALLOWED_USERS = [
    int(x.strip()) for x in os.getenv("ALLOWED_USERS", "").split(",") if x.strip()
]
# Single source of truth for access control: allowed users + admin
ALLOWED_IDS = set(ALLOWED_USERS) | ({ADMIN_ID} if ADMIN_ID else set())
BOT_API_BASE_URL = os.getenv(
    "BOT_API_BASE_URL", "https://tg-proxy.mmsalehpoor.workers.dev/bot"
)
ICS_URL = "https://ics.fixtur.es/v2/fc-barcelona.ics"
ICS_PROXY_URL = os.getenv("ICS_PROXY_URL", BOT_API_BASE_URL)
ICS_PATH = os.path.join(BASE_DIR, "barcelona.ics")
ICS_DOWNLOAD_INTERVAL = 3600  # seconds

# Minutes-before-kickoff at which a reminder is sent, e.g. "5,10,15,30,60"
_DEFAULT_REMINDERS = [5, 10, 15, 30, 60]
_reminder_minutes_str = os.getenv("REMINDER_MINUTES", "5,10,15,30,60")
try:
    REMINDER_MINUTES = sorted(
        int(m.strip()) for m in _reminder_minutes_str.split(",") if m.strip()
    )
except ValueError:
    logger.warning(
        f"REMINDER_MINUTES نامعتبر: {_reminder_minutes_str!r} — از پیش‌فرض ۵,۱۰,۱۵,۳۰,۶۰ استفاده می‌شود."
    )
    REMINDER_MINUTES = list(_DEFAULT_REMINDERS)
if not REMINDER_MINUTES:
    REMINDER_MINUTES = list(_DEFAULT_REMINDERS)
