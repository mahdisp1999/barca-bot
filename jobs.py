"""Scheduled jobs. Command handlers never import this module.

Two ticks:
  check_reminders  every minute. Reads the cached match list only (no API quota).
  check_results    every 10 minutes. Result messages + the automatic status.
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta

from telegram.ext import ContextTypes

import settings
from bot_io.messaging import send_tracked
from formatting import status
from services import matches, tracking
from services import state as state_store
from storage import sqlite as db

logger = logging.getLogger(__name__)


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    if not settings.ADMIN_ID:
        return
    now = matches.now_local()
    events = await asyncio.to_thread(matches.upcoming)
    horizon = max(settings.REMINDER_MINUTES)

    last, last_loaded = None, False
    # Any match inside the horizon counts, not only "today": a 00:30 kick-off
    # needs its 60-minute reminder at 23:30 of the previous day.
    for ev in matches.starting_within(events, now, horizon):
        minutes_left = (ev["local_dt"] - now).total_seconds() / 60
        due = matches.due_reminder(minutes_left, settings.REMINDER_MINUTES, settings.REMINDER_GRACE_MIN)
        if due is None:
            continue

        alert_type = f"{due}m"
        kickoff = ev["local_dt"].isoformat(timespec="minutes")
        if not db.alert_pending(ev["uid"], alert_type, kickoff):
            continue

        if not last_loaded:
            last, last_loaded = await asyncio.to_thread(matches.last_result), True
        ok = await send_tracked(
            context, settings.ADMIN_ID, status.reminder_message(due, last, ev, now),
            kind="alert", command="match_alert", user_id=settings.ADMIN_ID,
            match_uid=ev["uid"], parse_mode="HTML",
        )
        if ok:
            logger.info("هشدار ارسال شد (%s): %s", alert_type, ev["summary"])
            db.mark_alert_sent(ev["uid"], alert_type, kickoff)


async def check_results(context: ContextTypes.DEFAULT_TYPE):
    if not settings.ADMIN_ID:
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
            ok = await send_tracked(
                context, settings.ADMIN_ID, status.result_message(ev, now),
                kind="alert", command="match_result", user_id=settings.ADMIN_ID,
                match_uid=uid, parse_mode="HTML",
            )
            if ok:
                logger.info("نتیجه‌ی بازی ارسال شد: %s", ev["summary"])
                tracking.mark_sent(state, uid)
                changed = True

    if changed:
        state_store.save()
    await _auto_status(context, state, events, now)


async def _auto_status(context, state: dict, events: list, now: datetime) -> None:
    """Send the status unprompted when the next match is close and the admin has
    not received any message for a while."""
    nxt = matches.next_match(events, now)
    if not nxt or nxt["local_dt"] - now >= timedelta(hours=settings.AUTO_STATUS_WINDOW_H):
        return
    # time.time() is epoch-based, so it does not depend on the server's timezone.
    if time.time() - state.get("last_bot_message_time", 0) < settings.AUTO_STATUS_QUIET_H * 3600:
        return

    last = await asyncio.to_thread(matches.last_result)
    ok = await send_tracked(
        context, settings.ADMIN_ID, status.status_message(last, nxt, now),
        kind="status", command="auto_status", user_id=settings.ADMIN_ID, parse_mode="HTML",
    )
    if ok:
        logger.info("وضعیت خودکار ارسال شد.")
