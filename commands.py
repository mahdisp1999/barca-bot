"""All bot commands in one file.

To add a command: write a handler `async def cmd_x(update, context)` and add one
line to COMMANDS. Access control, the menu (set_my_commands) and the audit
logger all read from that table, so there is nothing else to keep in sync.
Handlers contain only the command's logic; the access check is added by
build_handlers().
"""
import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, List

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import settings
from bot_io.access import DENY_TEXT, authorize, can_use, recipients
from bot_io.messaging import broadcast_tracked, reply_tracked
from formatting import fmt, status
from services import matches, reports


# ---------- handlers ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id if update.effective_user else None
    lines = ["🤖 ربات ردیاب مسابقات بارسلونا فعال است!", "", "دستورات موجود:"]
    for c in COMMANDS:
        if can_use(uid, c.admin_only):  # admin-only commands are hidden from others
            lines.append(f"/{c.name} - {c.description}")
    reminders = "، ".join(f"{fmt.fa_digits(m)} دقیقه‌ای" for m in settings.REMINDER_MINUTES)
    lines += ["", f"🔔 یادآوری خودکار در بازه‌های: {reminders} قبل از شروع بازی"]
    await reply_tracked(update, context, "\n".join(lines), command="start")


async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # blocking HTTP calls -> worker thread, so the bot stays responsive
    ok = await asyncio.to_thread(matches.refresh)
    if not ok:  # API unavailable: the saved data is still good enough to show
        ok = bool(await asyncio.to_thread(matches.upcoming))
    if ok:
        await reply_tracked(update, context, "✅ اطلاعات بازی‌ها به‌روز شد.", command="sync")
    else:
        await reply_tracked(update, context, "❌ خطا در دریافت اطلاعات از API.", command="sync")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last, events = await asyncio.to_thread(matches.snapshot)
    now = matches.now_local()
    # نتیجه‌ی قبلی وقتی بازی بعدی نزدیک است پنهان می‌شود؛ برچسب روز هم از تنظیمات می‌آید
    text = status.status_message(
        last, matches.next_match(events, now), now,
        hide_last_within_min=settings.HIDE_LAST_RESULT_WITHIN_MIN,
        night_from=settings.NIGHT_FROM,
    )
    await reply_tracked(update, context, text, command="status", parse_mode="HTML")


async def cmd_broadcast_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فقط ادمین (جدول COMMANDS این را کنترل می‌کند).
    همان متن /status را همان لحظه برای همه‌ی کاربران مجاز می‌فرستد."""
    users = recipients()
    if not users:  # هیچ گیرنده‌ای تعریف نشده
        await reply_tracked(
            update, context,
            "⚠️ گیرنده‌ای تعریف نشده است. ALLOWED_USERS و TELEGRAM_ADMIN_ID را چک کنید.",
            command="broadcast_status",
        )
        return

    # همان متنی که /status نشان می‌دهد
    last, events = await asyncio.to_thread(matches.snapshot)
    now = matches.now_local()
    text = status.status_message(
        last, matches.next_match(events, now), now,
        hide_last_within_min=settings.HIDE_LAST_RESULT_WITHIN_MIN,
        night_from=settings.NIGHT_FROM,
    )

    delivered = await broadcast_tracked(
        context, users, text, kind="status", command="broadcast_status", parse_mode="HTML",
    )
    await reply_tracked(
        update, context,
        f"✅ برای {fmt.fa_digits(delivered)} از {fmt.fa_digits(len(users))} کاربر ارسال شد.",
        command="broadcast_status",
    )


async def cmd_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin only (enforced by the table): shows other users' ids and names."""
    args = context.args or []
    if len(args) >= 2 and args[0] == "user":
        try:
            target = int(args[1])
        except ValueError:
            await reply_tracked(update, context, "❌ شناسه‌ی کاربر باید عدد باشد.", command="usage")
            return
        text = reports.user_history_text(target)
    elif args and args[0].isdigit():
        text = reports.recent_text(max(1, min(int(args[0]), 100)))
    else:
        text = reports.build_summary()
    await reply_tracked(update, context, text, command="usage")


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reply_tracked(update, context, "✅ ربات فعال است.", command="health")


# ---------- the table ----------

@dataclass(frozen=True)
class Command:
    name: str
    description: str  # shown in the Telegram menu and in /start
    handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]
    admin_only: bool = False


COMMANDS: List[Command] = [
    Command("start", "شروع", cmd_start),
    Command("sync", "به‌روزرسانی اطلاعات بازی‌ها", cmd_sync, admin_only=True),
    Command("status", "وضعیت: آخرین نتیجه و بازی بعدی", cmd_status),
    Command("broadcast_status", "ارسال وضعیت به همه‌ی کاربران مجاز (فقط ادمین)",
            cmd_broadcast_status, admin_only=True),
    Command("usage", "گزارش استفاده از ربات (فقط ادمین)", cmd_usage, admin_only=True),
    Command("health", "وضعیت سلامت ربات", cmd_health, admin_only=True),
]
REGISTRY = {c.name: c for c in COMMANDS}


def _guarded(cmd: Command) -> CommandHandler:
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not authorize(update, cmd.name, admin_only=cmd.admin_only):
            await reply_tracked(update, context, DENY_TEXT, command=cmd.name)
            return
        await cmd.handler(update, context)

    return CommandHandler(cmd.name, handler)


def build_handlers() -> List[CommandHandler]:
    return [_guarded(c) for c in COMMANDS]