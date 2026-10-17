"""bot_state.json, loaded ONCE and shared in memory.
Keys: watched, result_sent (see services/tracking.py).
The time of the last message to each user is NOT kept here: it is read from the
database (storage.sqlite.last_sent_at), so it is per user and survives restarts.
"""
import json
import logging
import os

import settings

logger = logging.getLogger(__name__)

# Keys written by older versions; dropped on load.
_OBSOLETE = (
    "last_download_time", "last_match_uid", "last_match_summary", "cooldown_until",
    "match_ended", "match_ended_time", "last_status_send_time", "last_bot_message_time",
)

_state = None

def get() -> dict:
    global _state
    if _state is None:
        data = {}
        if settings.STATE_FILE.is_file():
            try:
                with open(settings.STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                data = {}
        if not isinstance(data, dict):
            data = {}
        for key in _OBSOLETE:
            data.pop(key, None)
        _state = data
    return _state


def save() -> None:
    """Atomic write: a crash never leaves a half-written file."""
    tmp = str(settings.STATE_FILE) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(get(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, settings.STATE_FILE)
    except OSError as e:
        logger.error("خطا در ذخیره وضعیت: %s", e)