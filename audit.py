"""Group-1 inbound logger + global error handler."""
import logging
import traceback

from telegram import Update
from telegram.ext import ContextTypes

from bot_io.access import can_use, user_fields
from commands import REGISTRY
from storage import sqlite as db

logger = logging.getLogger(__name__)


async def log_inbound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log every inbound message without replying (runs after the group-0 handlers)."""
    if not update.effective_user:
        return

    msg = update.message
    text = msg.text if msg else None
    command, kind = None, "unknown"
    if text and text.startswith("/"):
        command = text.split()[0][1:].split("@")[0]
        kind = "command"

    fields = user_fields(update)
    cmd = REGISTRY.get(command)
    if cmd and not can_use(fields["user_id"], cmd.admin_only):
        return  # access.authorize() already logged this attempt as kind='denied'

    db.log_event(kind=kind, direction="inbound", command=command, text_sent=text, **fields)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    exc = context.error
    if exc is None:
        return
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("خطای هندلر: %s\n%s", exc, tb)
    fields = user_fields(update) if isinstance(update, Update) else {}
    db.log_event(
        kind="system", direction="inbound", delivery="failed",
        error=str(exc), text_sent=tb[-2000:], **fields,
    )
