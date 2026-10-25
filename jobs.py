"""Scheduled jobs. Command handlers never import this module.

Every automatic message goes to EVERY recipient (ALLOWED_USERS + admin), and
each user is tracked separately in the database, so nobody gets a message twice
and one failed delivery never blocks the others.

Three jobs:
  daily_sync       once a day. Fresh match list.
  check_reminders  every minute. Reads the cached match list only (no API quota).
  check_results    every 10 minutes. Result messages + the automatic status.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from telegram.ext import ContextTypes

import settings
from bot_io.access import recipients
from bot_io.messaging import send_tracked
from formatting import status
from services import matches, tracking
from services import state as state_store
from storage import sqlite as db

logger = logging.getLogger(__name__)

# user_id -> when the last automatic status was attempted (not persisted on purpose:
# it only stops us from retrying an unreachable user on every 10-minute tick).
_auto_attempt: Dict[int, datetime] = {}


def _kickoff_key(ev: dict) -> str:
    """Part of the de-dup key: if the kick-off time changes, reminders fire again."""
    return ev["local_dt"].isoformat(timespec="minutes")


async def _broadcast(
    context: ContextTypes.DEFAULT_TYPE, users: List[int], text: str, *,
    kind: str, command: str, match_uid: Optional[str] = None,
) -> Dict[int, bool]:
    """Send the same text to each user separately; returns {user_id: delivered}."""
    out = {}
    for uid in users:
        out[uid] = await send_tracked(
            context, uid, text, kind=kind, command=command,
            user_id=uid, match_uid=match_uid, parse_mode="HTML",
        )
        await asyncio.sleep(0.05)  # stay far below Telegram's broadcast limit
    return out


async def daily_sync(context):
    await asyncio.to_thread(matches.upcoming, True)  # force = a fresh request


# ---------- reminders ----------

def _due(ev: dict, now: datetime):
    minutes_left = (ev["local_dt"] - now).total_seconds() / 60
    return matches.due_reminder(minutes_left, settings.REMINDER_MINUTES, settings.REMINDER_GRACE_MIN)


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    users = recipients()
    if not users:
        return
    now = matches.now_local()
    events = await asyncio.to_thread(matches.upcoming)
    horizon = max(settings.REMINDER_MINUTES)

    last, last_loaded = None, False
    # Any match inside the horizon counts, not only "today": a 00:30 kick-off
    # needs its 60-minute reminder at 23:30 of the previous day.
    for ev in matches.starting_within(events, now, horizon):
        due = _due(ev, now)
        if due is None:
            continue
# فقط اگر نزدیک ساعت بازی هستیم force کن، وگرنه از کش بخوان
        mins_to_kick = (ev["local_dt"] - now).total_seconds() / 60
        fresh = await asyncio.to_thread(matches.upcoming, mins_to_kick <= 120)
        alert_type = f"{due}m"
        kickoff = _kickoff_key(ev)
        pending = [u for u in users if db.alert_pending(ev["uid"], alert_type, kickoff, u)]
        if not pending:
            continue

        # Somebody still needs this reminder: re-check the kick-off time once, so a
        # rescheduled match never produces a wrong message. (If the API is down the
        # cached list comes back, which is fine.)
        fresh = await asyncio.to_thread(matches.upcoming, True)
        ev = next((e for e in fresh if e["uid"] == ev["uid"]), None)
        if ev is None or _due(ev, now) != due or _kickoff_key(ev) != kickoff:
            continue

        if not last_loaded:
            last, last_loaded = await asyncio.to_thread(matches.last_result), True
        text = status.reminder_message(
            due, last, ev, now, settings.HIDE_LAST_RESULT_WITHIN_MIN,
            night_from=settings.NIGHT_FROM,
        )
        sent = await _broadcast(
            context, pending, text, kind="alert", command="match_alert", match_uid=ev["uid"]
        )
        for uid, ok in sent.items():
            if ok:
                db.mark_alert_sent(ev["uid"], alert_type, kickoff, uid)
        logger.info("هشدار %s برای %d/%d کاربر ارسال شد: %s",
                    alert_type, sum(sent.values()), len(sent), ev["summary"])


# ---------- results + automatic status ----------

async def check_results(context: ContextTypes.DEFAULT_TYPE):
    users = recipients()
    if not users:
        return
    state = state_store.get()
    tracking.ensure_keys(state)
    now = matches.now_local()

    events = await asyncio.to_thread(matches.upcoming)
    changed = tracking.watch_new(state, events)

    for _, entry in tracking.drop_expired(state, now):
        logger.warning("نتیجه‌ی بازی دریافت نشد و رها شد: %s", entry["summary"])
        changed = True

    due = tracking.due_uids(state, now)
    if due:
        # One fresh fetch per tick, however many matches are waiting.
        finished = await asyncio.to_thread(matches.finished, True)
        for uid in due:
            ev = matches.find_finished(finished, uid)
            if ev is None:
                continue
            kickoff = _kickoff_key(ev)
            pending = [u for u in users if db.alert_pending(uid, "result", kickoff, u)]
            if pending:
                sent = await _broadcast(
                    context, pending, status.result_message(ev, now),
                    kind="alert", command="match_result", match_uid=uid,
                )
                for u, ok in sent.items():
                    if ok:
                        db.mark_alert_sent(uid, "result", kickoff, u)
                if not all(sent.values()):
                    continue  # keep watching: the next tick retries only the failed users
                logger.info("نتیجه‌ی بازی ارسال شد: %s", ev["summary"])
            tracking.mark_sent(state, uid)
            changed = True

    if changed:
        state_store.save()
    await _auto_status(context, users, events, now)


async def _auto_status(context, users: List[int], events: list, now: datetime) -> None:
    """Send the next-match status to every user who has been silent for too long.

    Per user: the match is closer than AUTO_STATUS_WINDOW_H and the last message
    that really reached THAT user is older than AUTO_STATUS_QUIET_H (or there is
    none). The last-message time comes from usage_log, which records every
    message the bot sends, so it survives restarts.
    """
    nxt = matches.next_match(events, now)
    if not nxt or nxt["local_dt"] - now >= timedelta(hours=settings.AUTO_STATUS_WINDOW_H):
        return

    quiet = timedelta(hours=settings.AUTO_STATUS_QUIET_H)
    retry = timedelta(hours=settings.AUTO_STATUS_RETRY_H)
    targets = []
    for uid in users:
        last_sent = db.last_sent_at(uid)
        if last_sent is not None and now - last_sent < quiet:
            continue
        tried = _auto_attempt.get(uid)
        if tried is not None and now - tried < retry:
            continue
        targets.append(uid)
    if not targets:
        return

    last = await asyncio.to_thread(matches.last_result)
    text = status.status_message(
        last, nxt, now, settings.HIDE_LAST_RESULT_WITHIN_MIN,
        night_from=settings.NIGHT_FROM,
    )
    for uid in targets:
        _auto_attempt[uid] = now
    sent = await _broadcast(context, targets, text, kind="status", command="auto_status")
    logger.info("وضعیت خودکار برای %d/%d کاربر ارسال شد.", sum(sent.values()), len(sent))