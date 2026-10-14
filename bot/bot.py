"""Entry point: wiring only. All logic lives in the small modules."""
import os
import sys

# Run as `python bot/bot.py`: sys.path[0] is bot/, so the sibling modules
# resolve as-is. db.py lives one level up, so add the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

import db
from audit import log_inbound, on_error
from cmd_start import start
from cmd_status import status
from cmd_sync import sync
from cmd_usage import usage
from config import ALLOWED_USERS, BOT_API_BASE_URL, TOKEN, logger
from jobs import check_matches


async def post_init_callback(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start", "شروع"),
        BotCommand("sync", "به‌روزرسانی"),
        BotCommand("status", "وضعیت امروز"),
        BotCommand("usage", "گزارش استفاده از ربات"),
    ])


def main() -> None:
    if not TOKEN or TOKEN == "your_bot_token_here":
        logger.error("توکن تنظیم نشده است.")
        return

    db.init_db()
    db.cleanup_old_alerts(days=30)

    if not ALLOWED_USERS:
        logger.warning("ALLOWED_USERS خالی است — همه‌ی کاربران مجاز هستند.")

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .base_url(BOT_API_BASE_URL)
        .post_init(post_init_callback)
        .build()
    )

    # group 0: commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sync", sync))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("usage", usage))

    # group 1: log every inbound update (no reply)
    app.add_handler(MessageHandler(filters.ALL, log_inbound), group=1)

    app.add_error_handler(on_error)

    if app.job_queue:
        app.job_queue.run_repeating(check_matches, interval=600, first=5)
    else:
        logger.warning("JobQueue غیرفعال است.")

    logger.info("ربات آماده است.")
    app.run_polling()


if __name__ == "__main__":
    main()
