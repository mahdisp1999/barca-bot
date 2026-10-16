"""Usage-report text, shared by the /usage command and report.py. No Telegram."""
from storage import sqlite as db


def format_event(row) -> str:
    who = row["username"] or row["first_name"] or "?"
    return (
        f"{row['ts'][5:16]} | {who} ({row['user_id']}) | "
        f"{row['direction']:>8} | {row['kind']} | {row['command'] or '-'} | "
        f"{row['delivery'] or '-'}"
    )


def build_summary() -> str:
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
        lines += ["", "بر اساس نوع:"] + [f"  {k}: {v}" for k, v in kinds.items()]
    cmds = db.counts_by("command")
    if cmds:
        lines += ["", "بر اساس دستور:"] + [f"  {k}: {v}" for k, v in cmds.items()]
    top = db.top_users(10)
    if top:
        lines += ["", "فعال‌ترین کاربران:"]
        for u in top:
            who = u["username"] or u["first_name"] or "?"
            denied = f" | رد: {u['denied_count']}" if u["denied_count"] else ""
            lines.append(f"  {who} ({u['user_id']}) — {u['total_events']} رویداد{denied}")
    return "\n".join(lines)


def recent_text(limit: int) -> str:
    rows = db.query_events(limit=limit)
    if not rows:
        return "رویدادی ثبت نشده است."
    return f"🕒 {len(rows)} رویداد اخیر:\n" + "\n".join(format_event(r) for r in rows)


def user_history_text(user_id: int, limit: int = 50) -> str:
    rows = db.query_events(user_id=user_id, limit=limit)
    if not rows:
        return f"رویدادی برای کاربر {user_id} ثبت نشده است."
    return f"👤 تاریخچه‌ی کاربر {user_id}:\n" + "\n".join(format_event(r) for r in rows)
