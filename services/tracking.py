"""Which matches are waiting for a result. Pure functions over the shared state dict.

The API may stop listing a match once it has started, so every upcoming match is
remembered in state["watched"] = {uid: {"ts": iso, "summary": str}} until its
result has been sent (or it is given up on).
"""
from datetime import datetime, timedelta
from typing import List, Tuple

import settings
from services.matches import INACTIVE_STATUSES


def ensure_keys(state: dict) -> None:
    state.setdefault("watched", {})
    state.setdefault("result_sent", [])


def _kickoff(entry: dict) -> datetime:
    return datetime.fromisoformat(entry["ts"])


def watch_new(state: dict, events: list) -> bool:
    """Remember upcoming matches. True if the state changed."""
    watched, done = state["watched"], set(state["result_sent"])
    changed = False
    for ev in events:
        uid = ev["uid"]
        if uid in watched or uid in done or ev.get("status") in INACTIVE_STATUSES:
            continue
        watched[uid] = {"ts": ev["local_dt"].isoformat(), "summary": ev["summary"]}
        changed = True
    return changed


def drop_expired(state: dict, now: datetime) -> List[Tuple[str, dict]]:
    """Remove matches that never got a result within RESULT_GIVE_UP_AFTER_H."""
    limit = timedelta(hours=settings.RESULT_GIVE_UP_AFTER_H)
    gone = [(uid, e) for uid, e in state["watched"].items() if now - _kickoff(e) > limit]
    for uid, _ in gone:
        del state["watched"][uid]
    return gone


def due_uids(state: dict, now: datetime) -> List[str]:
    """Matches old enough that their result may be available."""
    after = timedelta(minutes=settings.RESULT_CHECK_AFTER_MIN)
    return [uid for uid, e in state["watched"].items() if now - _kickoff(e) >= after]


def mark_sent(state: dict, uid: str) -> None:
    state["watched"].pop(uid, None)
    state["result_sent"] = (state["result_sent"] + [uid])[-settings.RESULT_HISTORY:]
