"""bot_state.json, loaded ONCE and shared in memory.

Every module gets the same dict, so there are no stale copies overwriting each
other, and no file read per job tick / per command.
"""
import json
import os
import time

from config import BASE_DIR, logger

STATE_FILE = os.path.join(BASE_DIR, "bot_state.json")

_DEFAULTS = {
    "last_download_time": 0,
    "last_match_uid": "",
    "last_match_summary": "",
    "cooldown_until": 0,
    "match_ended": False,
    "match_ended_time": 0,
}

_state = None


def get() -> dict:
    global _state
    if _state is None:
        data = {}
        if os.path.isfile(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                data = {}
        # Time of the last message of ANY kind sent to the admin.
        # Seeded from the old key so existing installs keep their timing.
        if "last_bot_message_time" not in data:
            data["last_bot_message_time"] = data.get("last_status_send_time", 0)
        for k, v in _DEFAULTS.items():
            data.setdefault(k, v)
        _state = data
    return _state


def save() -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(get(), f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error(f"خطا در ذخیره وضعیت: {e}")


def touch_message_time() -> None:
    get()["last_bot_message_time"] = time.time()
    save()
