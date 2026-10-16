"""Builds the Telegram Application: handlers, error handler, scheduled jobs."""
from telegram import BotCommand
from telegram.ext import Application, ApplicationBuilder, MessageHandler, filters

import audit
import commands
import jobs
import settings


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands([BotCommand(c.name, c.description) for c in commands.COMMANDS])


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
    app.job_queue.run_repeating(
        jobs.check_reminders, interval=settings.REMINDER_CHECK_INTERVAL, first=10, name="reminders"
    )
    app.job_queue.run_repeating(
        jobs.check_results, interval=settings.RESULT_CHECK_INTERVAL, first=5, name="results"
    )
    return app
