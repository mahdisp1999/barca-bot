"""Access control + audit of denied attempts."""
from telegram import Update

import settings
from storage import sqlite as db
import logging

logger = logging.getLogger(__name__)

DENY_TEXT = "⚠️ دسترسی ندارید."


def is_admin(user_id: int) -> bool:
    return bool(settings.ADMIN_ID) and user_id == settings.ADMIN_ID


def recipients() -> list:
    """همه‌ی کاربران مجاز (ادمین داخل ALLOWED_IDS هست)."""
    if settings.ALLOWED_IDS:
        return sorted(settings.ALLOWED_IDS)
    return [settings.ADMIN_ID] if settings.ADMIN_ID else []


def can_use(user_id, admin_only: bool = False) -> bool:
    """Admin-only commands need TELEGRAM_ADMIN_ID to be set; an empty allow-list
    means everybody may use the normal commands."""
    if user_id is None:
        return False
    if admin_only:
        return is_admin(user_id)
    return not settings.ALLOWED_IDS or user_id in settings.ALLOWED_IDS


def user_fields(update: Update) -> dict:
    u, c = update.effective_user, update.effective_chat
    return {
        "user_id": u.id if u else None,
        "username": u.username if u else None,
        "first_name": u.first_name if u else None,
        "chat_id": c.id if c else None,
        "chat_type": c.type if c else None,
    }


def authorize(update: Update, command: str, admin_only: bool = False) -> bool:
    """Command-level check. Allowed uses update the user directory; denied
    attempts are always logged (exactly once, see audit.log_inbound)."""
    fields = user_fields(update)
    if can_use(fields["user_id"], admin_only):
        db.upsert_user(
            user_id=fields["user_id"], username=fields["username"],
            first_name=fields["first_name"], command=command,
        )
        return True

    db.log_event(
        kind="denied", direction="inbound", command=command,
        allowed=False, delivery="denied", **fields,
    )
    if fields["user_id"] is not None:
        db.upsert_user(
            user_id=fields["user_id"], username=fields["username"],
            first_name=fields["first_name"], command=command, denied=True,
        )
    logger.warning("دسترسی غیرمجاز: کاربر %s دستور /%s", fields["user_id"], command)
    return False
