from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

import ics
from access import DENY_TEXT, authorize
from fmt import next_match_block, opponent_of
from messaging import reply_tracked


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorize(update, "status"):
        await reply_tracked(update, context, DENY_TEXT, command="status")
        return

    events = ics.load_events()
    matches = ics.find_today_matches(events)
    last_summary, last_location = ics.get_last_match_info(events)

    msg = ""

    if last_summary:
        msg += f"📊 **آخرین بازی:**\n{last_summary}\n📍 زمین: {last_location}\n\n"

    if matches:
        msg += "⚽️ **مسابقه امشب/امروز:**\n"
        for m in matches:
            opponent = opponent_of(m["summary"])
            msg += f"• حریف: {opponent if opponent else m['summary']} | ساعت: {m['local_dt'].strftime('%H:%M')}\n"
            msg += f"📍 زمین: {m.get('location', 'نامشخص')}\n"
    else:
        next_match = ics.find_next_match(events)
        if next_match:
            msg += next_match_block(next_match, datetime.now())
        else:
            msg += "📅 بازی آینده‌ای یافت نشد."

    await reply_tracked(update, context, msg, command="status", parse_mode="Markdown")
