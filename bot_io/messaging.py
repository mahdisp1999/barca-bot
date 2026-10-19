"""The only way messages leave the bot: every part is logged with its delivery result."""
import asyncio
import logging
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from bot_io.access import user_fields
from storage import sqlite as db

logger = logging.getLogger(__name__)

# Telegram's hard limit is 4096 characters. Keep a safety margin.
MAX_CHARS = 4000


def split_message(text: str) -> list:
    """Split on line breaks, so an HTML tag (always on one line) is never cut."""
    if len(text) <= MAX_CHARS:
        return [text]
    parts, buf = [], ""
    for line in text.split("\n"):
        # A single line longer than the limit is hard-cut as a last resort.
        while len(line) > MAX_CHARS:
            if buf:
                parts.append(buf)
                buf = ""
            parts.append(line[:MAX_CHARS])
            line = line[MAX_CHARS:]
        candidate = f"{buf}\n{line}" if buf else line
        if buf and len(candidate) > MAX_CHARS:
            parts.append(buf)
            buf = line
        else:
            buf = candidate
    if buf:
        parts.append(buf)
    return parts


async def _send_one(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, *,
    kind: str, command: Optional[str], user_id: Optional[int],
    match_uid: Optional[str], parse_mode: Optional[str],
) -> bool:
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    except Exception as e:
        db.log_event(
            kind=kind, direction="outbound", command=command, user_id=user_id,
            chat_id=chat_id, text_sent=text, delivery="failed", error=str(e),
            match_uid=match_uid,
        )
        logger.error("خطا در ارسال پیام: %s", e)
        return False

    db.log_event(
        kind=kind, direction="outbound", command=command, user_id=user_id,
        chat_id=chat_id, text_sent=text, delivery="sent", match_uid=match_uid,
    )
    return True


async def send_tracked(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, *,
    kind: str = "command", command: Optional[str] = None,
    user_id: Optional[int] = None, match_uid: Optional[str] = None,
    parse_mode: Optional[str] = None,
) -> bool:
    """Send (split if too long) and log each part. True only if every part was sent."""
    all_ok = True
    for part in split_message(text):
        ok = await _send_one(
            context, chat_id, part, kind=kind, command=command,
            user_id=user_id, match_uid=match_uid, parse_mode=parse_mode,
        )
        all_ok = all_ok and ok
    return all_ok


async def broadcast_tracked(
    context: ContextTypes.DEFAULT_TYPE, chat_ids: list, text: str, *,
    kind: str, command: str, parse_mode: Optional[str] = None,
) -> int:
    """همان متن را جداگانه به هر گیرنده می‌فرستد و هر ارسال را لاگ می‌کند.
    خروجی: تعداد کسانی که پیام به آن‌ها رسیده."""
    delivered = 0
    for chat_id in chat_ids:
        ok = await send_tracked(
            context, chat_id, text, kind=kind, command=command,
            user_id=chat_id, parse_mode=parse_mode,
        )
        if ok:
            delivered += 1
        await asyncio.sleep(0.05)  # کمی مکث تا از محدودیت تلگرام رد نشویم
    return delivered


async def reply_tracked(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, *,
    kind: str = "command", command: Optional[str] = None,
    parse_mode: Optional[str] = None,
) -> bool:
    fields = user_fields(update)
    return await send_tracked(
        context, fields["chat_id"], text, kind=kind, command=command,
        user_id=fields["user_id"], parse_mode=parse_mode,
    )