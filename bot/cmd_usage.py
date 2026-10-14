"""/usage — admin only report."""
from telegram import Update
from telegram.ext import ContextTypes

import db
from access import DENY_TEXT, user_fields
from config import ADMIN_ID
from messaging import reply_tracked

MSG_LIMIT = 4096


def _chunks(text: str, limit: int = MSG_LIMIT) -> list:
    return [text[i : i + limit] for i in range(0, len(text), limit)] or [""]


def _fmt_event(row) -> str:
    who = row["username"] or row["first_name"] or "?"
    return (
        f"{row['ts'][5:16]} | {who} ({row['user_id']}) | "
        f"{row['direction']:>8} | {row['kind']} | {row['command'] or '-'} | "
        f"{row['delivery'] or '-'}"
    )


def build_usage_summary() -> str:
    lines = [
        "📊 گزارش استفاده از ربات",
        "",
        f"کل رویدادها: {db.total_events()}",
        f"کاربران یکتا: {db.distinct_users()}",
        f"۲۴ ساعت اخیر: {db.events_count_since(1)}",
        f"۷ روز اخیر: {db.events_count_since(7)}",
    ]

    kinds = db.counts_by("kind")
    if kinds:
        lines += ["", "بر اساس نوع:"]
        lines += [f"  {k}: {v}" for k, v in kinds.items()]

    cmds = db.counts_by("command")
    if cmds:
        lines += ["", "بر اساس دستور:"]
        lines += [f"  {k}: {v}" for k, v in cmds.items()]

    top = db.top_users(10)
    if top:
        lines += ["", "فعال‌ترین کاربران:"]
        for u in top:
            who = u["username"] or u["first_name"] or "?"
            denied = f" | رد: {u['denied_count']}" if u["denied_count"] else ""
            lines.append(
                f"  {who} ({u['user_id']}) — {u['total_events']} رویداد{denied}"
            )
    return "\n".join(lines)


async def usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only: shows other users' ids and names."""
    user_id = update.effective_user.id if update.effective_user else None
    if ADMIN_ID and user_id != ADMIN_ID:
        fields = user_fields(update)
        db.log_event(
            kind="denied",
            direction="inbound",
            command="usage",
            allowed=False,
            delivery="denied",
            **fields,
        )
        # same keyword set as access.authorize() uses for upsert_user
        db.upsert_user(
            user_id=fields["user_id"],
            username=fields["username"],
            first_name=fields["first_name"],
            command="usage",
            denied=True,
        )
        await reply_tracked(update, context, DENY_TEXT, command="usage")
        return

    args = context.args or []

    if args and args[0] == "user" and len(args) > 1:
        try:
            target = int(args[1])
        except ValueError:
            await reply_tracked(
                update, context, "❌ شناسه‌ی کاربر باید عدد باشد.", command="usage"
            )
            return
        rows = db.events_for_user(target, 50)
        text = f"👤 تاریخچه‌ی کاربر {target}:\n" + "\n".join(_fmt_event(r) for r in rows)
    elif args and args[0].isdigit():
        rows = db.recent_events(int(args[0]))
        text = f"🕒 {len(rows)} رویداد اخیر:\n" + "\n".join(_fmt_event(r) for r in rows)
    else:
        text = build_usage_summary()

    for part in _chunks(text):
        await reply_tracked(update, context, part, command="usage")
