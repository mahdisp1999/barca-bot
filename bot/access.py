"""Access control + audit of denied attempts."""
from telegram import Update

import db
from config import ALLOWED_IDS, logger

DENY_TEXT = "⚠️ دسترسی ندارید."


def is_allowed(user_id: int) -> bool:
    if not ALLOWED_IDS:
        return True  # empty list => everyone is allowed
    return user_id in ALLOWED_IDS


def user_fields(update: Update) -> dict:
    """Common user/chat fields extracted from an update."""
    u = update.effective_user
    c = update.effective_chat
    return {
        "user_id": u.id if u else None,
        "username": u.username if u else None,
        "first_name": u.first_name if u else None,
        "chat_id": c.id if c else None,
        "chat_type": c.type if c else None,
    }


def authorize(update: Update, command: str) -> bool:
    """Command-level access check. Unauthorized attempts are always logged."""
    fields = user_fields(update)
    if is_allowed(fields["user_id"]):
        db.upsert_user(
            user_id=fields["user_id"],
            username=fields["username"],
            first_name=fields["first_name"],
            command=command,
        )
        return True

    db.log_event(
        kind="denied",
        direction="inbound",
        command=command,
        allowed=False,
        delivery="denied",
        **fields,
    )
    db.upsert_user(
        user_id=fields["user_id"],
        username=fields["username"],
        first_name=fields["first_name"],
        command=command,
        denied=True,
    )
    logger.warning(f"دسترسی غیرمجاز: کاربر {fields['user_id']} دستور /{command}")
    return False
