"""Scheduled job (every 10 min). Command handlers never import this module."""
import asyncio
from datetime import datetime

from telegram.ext import ContextTypes

import db
import ics
import state_store
from config import ADMIN_ID, REMINDER_MINUTES, logger
from fmt import next_match_block, opponent_of, to_persian_num
from messaging import send_tracked


async def check_matches(context: ContextTypes.DEFAULT_TYPE):
    state = state_store.get()
    now = datetime.now()
    now_ts = now.timestamp()

    # ── Part 0: hourly calendar refresh (blocking HTTP -> worker thread) ──
    if ics.should_download_ics():
        await asyncio.to_thread(ics.download_ics)

    # ── Part 1: 60 min after a match ended -> refresh calendar + send result ──
    if state.get("match_ended") and state.get("match_ended_time"):
        elapsed = now_ts - state["match_ended_time"]
        if elapsed >= 3600:
            logger.info("۶۰ دقیقه از اتمام بازی گذشت. آپدیت تقویم...")
            if await asyncio.to_thread(ics.download_ics):
                events = ics.load_events()
                last_summary, last_location = ics.get_last_match_info(events)
                if last_summary:
                    msg = (
                        f"📊 **آخرین نتیجه بازی:**\n"
                        f"{last_summary}\n"
                        f"🏟️ زمین: {last_location}\n"
                    )
                    if ADMIN_ID != 0:
                        ok = await send_tracked(
                            context,
                            ADMIN_ID,
                            msg,
                            kind="alert",
                            command="match_result",
                            user_id=ADMIN_ID,
                            match_uid=state.get("last_match_uid"),
                            parse_mode="Markdown",
                        )
                        if ok:
                            logger.info(f"نتیجه آخرین بازی ارسال شد: {last_summary}")

                    state["match_ended"] = False
                    state["match_ended_time"] = 0
                    state["last_match_summary"] = last_summary
                    state_store.save()
            else:
                logger.error("خطا در آپدیت تقویم بعد از اتمام بازی")

    events = ics.load_events()

    # ── Part 2: today's matches -> reminders ──
    matches = ics.find_today_matches(events)
    if matches:
        await _handle_today_matches(context, state, events, matches, now, now_ts)

    # ── Part 3: automatic status (runs even if the match is tomorrow) ──
    await _auto_status(context, state, events, now)


async def _handle_today_matches(context, state, events, matches, now, now_ts):
    last_summary, last_location = ics.get_last_match_info(events)

    last_match_text = ""
    if last_summary:
        last_match_text = (
            f"📊 **آخرین بازی:**\n{last_summary}\n🏟️ زمین: {last_location}\n\n"
        )

    for match in matches:
        match_time = match["local_dt"]
        total_seconds = (match_time - now).total_seconds()
        match_uid = match.get("uid", "")

        if total_seconds < 0:
            # kick-off passed: remember it so Part 1 can fetch the result later
            if match_uid and state.get("last_match_uid") != match_uid:
                logger.info(f"بازی تمام شد: {match['summary']}")
                state["match_ended"] = True
                state["match_ended_time"] = now_ts
                state["last_match_uid"] = match_uid
                state["last_match_summary"] = match["summary"]
                state_store.save()
                db.log_event(
                    kind="system",
                    direction="inbound",
                    command="match_ended",
                    delivery="skipped",
                    match_uid=match_uid,
                    text_sent=match["summary"],
                )
            continue

        match_key = f"{match['summary']}_{match_time.strftime('%Y%m%d%H%M')}"
        minutes_remaining = total_seconds / 60

        # A reminder fires when remaining time is within ±5 min of a configured value.
        alert_type = None
        alert_text = None
        for reminder_min in REMINDER_MINUTES:
            if abs(minutes_remaining - reminder_min) <= 5:
                alert_type = f"{reminder_min}m"
                fa_min = to_persian_num(reminder_min)
                if reminder_min % 60 == 0 and reminder_min < 120:
                    alert_text = f"⏰ **{to_persian_num(reminder_min // 60)} ساعت تا شروع بازی!**"
                else:
                    alert_text = f"⏰ **{fa_min} دقیقه تا شروع بازی!**"
                break

        if (
            alert_type
            and ADMIN_ID != 0
            and not db.is_alert_sent(match_uid, alert_type, match_key)
        ):
            opponent = opponent_of(match["summary"])
            text = (
                f"{last_match_text}"
                f"{alert_text}\n\n"
                f"⚽️ **مسابقه امشب/امروز:**\n"
                f"• حریف: {opponent if opponent else match['summary']} | ساعت: {match_time.strftime('%H:%M')}\n"
                f"🏟️ زمین: {match.get('location', 'نامشخص')}"
            )
            ok = await send_tracked(
                context,
                ADMIN_ID,
                text,
                kind="alert",
                command="match_alert",
                user_id=ADMIN_ID,
                match_uid=match_uid,
                parse_mode="Markdown",
            )
            if ok:
                logger.info(f"هشدار ارسال شد ({alert_type}): {match['summary']}")
                db.mark_alert_sent(match_uid, alert_type, match_key)


async def _auto_status(context, state, events, now):
    """Send the status unprompted when <24h to kick-off AND >12h since the
    bot's last message to the admin (of any kind: reply, alert, status)."""
    if ADMIN_ID == 0:
        return
    next_match = ics.find_next_match(events)
    if not next_match:
        return

    if (next_match["local_dt"] - now).total_seconds() >= 24 * 3600:
        return
    if now.timestamp() - state.get("last_bot_message_time", 0) < 12 * 3600:
        return

    msg = ""
    last_summary, last_location = ics.get_last_match_info(events)
    if last_summary:
        msg += (
            f"📊 **آخرین بازی:**\n"
            f"{last_summary}\n"
            f"📍 زمین: {last_location}\n\n"
        )
    msg += next_match_block(next_match, now)

    # send_tracked() refreshes last_bot_message_time on success
    ok = await send_tracked(
        context,
        ADMIN_ID,
        msg,
        kind="status",
        command="auto_status",
        user_id=ADMIN_ID,
        parse_mode="Markdown",
    )
    if ok:
        logger.info("وضعیت خودکار ارسال شد.")
