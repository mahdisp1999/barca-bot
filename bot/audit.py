"""Group-1 inbound logger + global error handler."""
import traceback

from telegram import Update
from telegram.ext import ContextTypes

import db
from access import user_fields
from config import logger


async def log_inbound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log every inbound update without replying (runs after group-0 handlers)."""
    if not update.effective_user:
        return

    msg = update.message
    text = msg.text if msg else None
    command = None
    kind = "unknown"
    if text and text.startswith("/"):
        command = text.split()[0][1:].split("@")[0]
        kind = "command"

    db.log_event(
        kind=kind,
        direction="inbound",
        command=command,
        text_sent=text,
        **user_fields(update),
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    exc = context.error
    if exc is None:
        return
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.exception(f"خطای هندلر: {exc}")
    fields = user_fields(update) if isinstance(update, Update) else {}
    db.log_event(
        kind="system",
        direction="inbound",
        delivery="failed",
        error=str(exc),
        text_sent=tb[-2000:],
        **fields,
    )
