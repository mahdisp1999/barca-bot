"""Builds the Telegram Application: handlers, error handler, scheduled jobs."""
from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeAllPrivateChats
from telegram.ext import Application, ApplicationBuilder, MessageHandler, filters

import logging
import audit
import commands
import jobs
import settings
from storage import sqlite as db

logger = logging.getLogger(__name__)

async def _sync_user_names(app: Application) -> None:
    """نام همه‌ی کاربران مجاز را یک‌بار از تلگرام می‌گیرد و در جدول users ذخیره می‌کند.

    تلگرام فقط به کاربری که قبلاً /start زده جواب می‌دهد. بقیه رد می‌شوند و در لاگ ثبت می‌شوند.
    """
    for uid in sorted(settings.ALLOWED_IDS):
        try:
            chat = await app.bot.get_chat(uid)
        except Exception as e:
            logger.warning("نام کاربر %s از تلگرام گرفته نشد: %s", uid, e)
            continue
        db.save_user_names(
            user_id=uid, username=chat.username, first_name=chat.first_name,
        )


async def _post_init(app: Application) -> None:
    # Admin gets all commands
    await app.bot.set_my_commands(
        [BotCommand(c.name, c.description) for c in commands.COMMANDS],
        scope=BotCommandScopeChat(chat_id=settings.ADMIN_ID)
    )
    # Regular users get only /start and /status
    await app.bot.set_my_commands(
        [BotCommand("start", "Start the bot"), BotCommand("status", "Check your status")],
        scope=BotCommandScopeAllPrivateChats()
    )
    await _sync_user_names(app)


def build_application() -> Application:
    app = (
        ApplicationBuilder()
        .token(settings.TOKEN)
        .base_url(settings.BOT_API_BASE_URL)
        .post_init(_post_init)
        .build()
    )

    # group 0: commands (access-checked)
    for handler in commands.build_handlers():
        app.add_handler(handler)
    # group 1: log every inbound message (never replies)
    app.add_handler(MessageHandler(filters.ALL, audit.log_inbound), group=1)
    app.add_error_handler(audit.on_error)

    if app.job_queue is None:
        raise RuntimeError(
            'JobQueue غیرفعال است؛ بدون آن یادآوری کار نمی‌کند. نصب: pip install "python-telegram-bot[job-queue]"'
        )
    app.job_queue.run_daily(jobs.daily_sync, time=settings.DAILY_SYNC_AT, name="daily_sync")
    app.job_queue.run_repeating(
        jobs.check_reminders, interval=settings.REMINDER_CHECK_INTERVAL, first=10, name="reminders"
    )
    app.job_queue.run_repeating(
        jobs.check_results, interval=settings.RESULT_CHECK_INTERVAL, first=5, name="results"
    )
    return app