import asyncio

from telegram import Update
from telegram.ext import ContextTypes

from access import DENY_TEXT, authorize
from ics import download_ics
from messaging import reply_tracked


async def sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorize(update, "sync"):
        await reply_tracked(update, context, DENY_TEXT, command="sync")
        return

    # blocking HTTP call -> worker thread, so the bot stays responsive
    if await asyncio.to_thread(download_ics):
        await reply_tracked(update, context, "✅ تقویم به‌روز شد.", command="sync")
    else:
        await reply_tracked(update, context, "❌ خطا در دریافت تقویم.", command="sync")
