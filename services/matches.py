"""Match logic on top of the provider. Pure helpers take `events` and `now`
explicitly, so they are easy to test; only upcoming()/finished()/snapshot() do I/O."""
from datetime import datetime
from typing import List, Optional

import settings
from providers import sportsapipro as api

# Statuses for which a match will not be played at its listed time.
INACTIVE_STATUSES = {"canceled", "cancelled", "postponed", "abandoned"}


def now_local() -> datetime:
    """Current time in LOCAL_TZ as a naive datetime (compares with event times)."""
    return datetime.now(settings.LOCAL_TZ).replace(tzinfo=None)


# ---------- I/O (blocking: call through asyncio.to_thread) ----------

def upcoming(force: bool = False) -> list:
    return api.load_upcoming(force)


def finished(force: bool = False) -> list:
    return api.load_finished(force)


def refresh() -> bool:
    return api.refresh()


def last_result() -> Optional[dict]:
    return last_finished(finished())


def snapshot() -> tuple:
    """(latest finished match or None, upcoming matches)."""
    return last_result(), upcoming()


# ---------- pure helpers ----------

def _active(events: list) -> list:
    return [e for e in events if e.get("status") not in INACTIVE_STATUSES]


def next_match(events: list, now: datetime) -> Optional[dict]:
    return next((e for e in _active(events) if e["local_dt"] > now), None)


def starting_within(events: list, now: datetime, minutes: int) -> List[dict]:
    """Matches that kick off between now and `minutes` from now (any day)."""
    out = []
    for e in _active(events):
        left = (e["local_dt"] - now).total_seconds() / 60
        if 0 <= left <= minutes:
            out.append(e)
    return out


def last_finished(events: list) -> Optional[dict]:
    """Most recent finished match that has a score (events sorted oldest -> newest)."""
    for e in reversed(events):
        if e.get("goals_for") is not None and e.get("goals_against") is not None:
            return e
    return None


def find_finished(events: list, uid: str) -> Optional[dict]:
    return next((e for e in events if e["uid"] == uid), None)


def due_reminder(minutes_left: float, reminder_minutes: list, grace: int) -> Optional[int]:
    """Which reminder (if any) should fire now.

    A reminder `m` is due when m - grace < minutes_left <= m. Being a few minutes
    late is fine; a reminder that is older than that is skipped, not sent stale.
    """
    for m in sorted(reminder_minutes):
        if m - grace < minutes_left <= m:
            return m
    return None
