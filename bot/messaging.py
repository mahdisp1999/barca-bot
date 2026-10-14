"""Send helpers: every outbound message is logged to the DB."""
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

import db
import state_store
from access import user_fields
from config import ADMIN_ID, logger


async def send_tracked(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    *,
    kind: str = "command",
    command: Optional[str] = None,
    user_id: Optional[int] = None,
    match_uid: Optional[str] = None,
    parse_mode: Optional[str] = None,
) -> bool:
    """Send a message and log the exact text + delivery result."""
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode=parse_mode
        )
    except Exception as e:
        db.log_event(
            kind=kind,
            direction="outbound",
            command=command,
            user_id=user_id,
            chat_id=chat_id,
            text_sent=text,
            delivery="failed",
            error=str(e),
            match_uid=match_uid,
        )
        logger.error(f"خطا در ارسال پیام: {e}")
        return False

    db.log_event(
        kind=kind,
        direction="outbound",
        command=command,
        user_id=user_id,
        chat_id=chat_id,
        text_sent=text,
        delivery="sent",
        match_uid=match_uid,
    )
    if chat_id == ADMIN_ID:
        state_store.touch_message_time()  # feeds the "12h since last message" rule
    return True


async def reply_tracked(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    kind: str = "command",
    command: Optional[str] = None,
    parse_mode: Optional[str] = None,
) -> bool:
    """Reply to the requesting user + log."""
    fields = user_fields(update)
    return await send_tracked(
        context,
        fields["chat_id"],
        text,
        kind=kind,
        command=command,
        user_id=fields["user_id"],
        parse_mode=parse_mode,
    )
