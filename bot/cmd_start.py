from telegram import Update
from telegram.ext import ContextTypes

from access import DENY_TEXT, authorize
from config import REMINDER_MINUTES
from fmt import to_persian_num
from messaging import reply_tracked


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorize(update, "start"):
        await reply_tracked(update, context, DENY_TEXT, command="start")
        return

    await reply_tracked(
        update,
        context,
        "🤖 ربات ردیاب مسابقات بارسلونا فعال است!\n\n"
        "دستورات موجود:\n"
        "/sync - به‌روزرسانی تقویم\n"
        "/status - وضعیت امروز\n"
        "/usage - گزارش استفاده (فقط ادمین)\n\n"
        "🔔 یادآوری خودکار در بازه‌های: "
        + ", ".join(f"{to_persian_num(m)} دقیقه‌ای" for m in REMINDER_MINUTES)
        + " قبل از شروع بازی",
        command="start",
    )
