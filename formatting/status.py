"""Builds the Telegram messages (HTML) from flat match dicts. Pure: no I/O.

A match dict (see providers/sportsapipro.py) has: team, opponent, is_home,
goals_for, goals_against, competition, stadium, city, country, local_dt, utc_dt.
`now` is always passed in, so everything here is easy to test.
"""
import html
from datetime import datetime
from typing import Optional

from formatting import fmt, names

esc = html.escape


def _outcome(gf: int, ga: int, team: str) -> tuple:
    """(icon, sentence) that depends on the result."""
    diff = gf - ga
    if diff > 0:
        if diff >= 3:
            return "✅", f"{team} با یک پیروزی پرگل حریف را شکست داد"
        if diff == 2:
            return "✅", f"{team} با دو گل اختلاف حریف را شکست داد"
        return "✅", f"{team} با اختلاف یک گل پیروز شد"
    if diff == 0:
        if gf == 0:
            return "🤝", "بازی با تساوی بدون گل تمام شد"
        return "🤝", "بازی با تساوی تمام شد"
    if diff <= -3:
        return "❌", f"{team} شکست سنگینی خورد"
    if diff == -1:
        return "❌", f"{team} با اختلاف یک گل شکست خورد"
    return "❌", f"{team} شکست خورد"


def _days_ago(kickoff: datetime, now: datetime) -> str:
    days = (now.date() - kickoff.date()).days
    if days <= 0:
        return "امروز"
    if days == 1:
        return "دیروز"
    return f"{fmt.fa_digits(days)} روز پیش"


def _stadium_line(ev: dict) -> str:
    stadium = ev.get("stadium") or ""
    if not stadium:
        return "نامشخص"
    city, country = ev.get("city") or "", ev.get("country") or ""
    text = esc(stadium)
    if city and country:
        text += f" در شهر {esc(city)}، {esc(country)}"
    elif city:
        text += f" در شهر {esc(city)}"
    return text


def result_block(ev: dict, now: datetime, title: str = "نتیجه آخرین بازی") -> str:
    team = names.team_fa(ev["team"]) or ev["team"]
    team_short = names.team_fa(ev["team"], short=True) or team
    opponent = names.team_fa(ev["opponent"]) or ev["opponent"]
    gf, ga = ev["goals_for"], ev["goals_against"]
    icon, outcome = _outcome(gf, ga, team_short)

    stadium = esc(ev["stadium"]) if ev.get("stadium") else ""
    if ev["is_home"]:
        where = f"در ورزشگاه خانگی {stadium}" if stadium else "در ورزشگاه خانگی"
    else:
        where = f"در زمین حریف ({stadium})" if stadium else "در زمین حریف"

    date_fa = fmt.jalali_date_str(ev["local_dt"].date())
    return "\n".join([
        f"⚽️ <b>{title}:</b>",
        f"{icon} {esc(team)} {fmt.fa_digits(gf)} - {fmt.fa_digits(ga)} {esc(opponent)} "
        f"({date_fa} - {_days_ago(ev['local_dt'], now)})",
        f"🏟️ این بازی {where} انجام شد و {esc(outcome)}.",
        f"🏆 رقابت: {esc(names.competition_fa(ev['competition']))}",
    ])


def next_block(ev: dict, now: datetime) -> str:
    fa = names.team_fa(ev["opponent"])
    opponent = f"{esc(fa)} ({esc(ev['opponent'])})" if fa else esc(ev["opponent"])
    side = "بازی خانگی (Home)" if ev["is_home"] else "بازی در خانه حریف (Away)"
    local, utc = ev["local_dt"], ev["utc_dt"]
    return "\n".join([
        "🔜 <b>بازی بعدی:</b>",
        f"🏆 رقابت: {esc(names.competition_fa(ev['competition']))}",
        f"⚔️ حریف: {opponent} - {side}",
        # f"🏟️ ورزشگاه: {_stadium_line(ev)}",
        f"📆 تاریخ: {fmt.jalali_date_str(local.date())}، ({fmt.gregorian_date_str(local.date())})",
        # The bot is for Iranian users, so the local time is always labelled "Iran time".
        f"⏰ ساعت: حدود ساعت {fmt.fa_digits(f'{local:%H:%M}')} به وقت ایران "
        f"({fmt.fa_digits(f'{utc:%H:%M}')} به وقت جهانی UTC)",
        f"⏳ {fmt.format_remaining_time(local - now)}",
    ])


def _too_close(nxt: Optional[dict], now: datetime, window: Optional[int]) -> bool:
    """True if the next match starts within `window` minutes. None = no limit."""
    if window is None or not nxt:
        return False
    return (nxt["local_dt"] - now).total_seconds() / 60 <= window


def status_message(
    last: Optional[dict], nxt: Optional[dict], now: datetime,
    hide_last_within_min: Optional[int] = None,
) -> str:
    if _too_close(nxt, now, hide_last_within_min):
        last = None  # close to kick-off: only the next match is shown
    blocks = []
    if last:
        blocks.append(result_block(last, now))
    if nxt:
        blocks.append(next_block(nxt, now))
    return "\n\n".join(blocks) or "📅 اطلاعاتی برای نمایش وجود ندارد."


def result_message(ev: dict, now: datetime) -> str:
    """The message sent automatically when a match has just finished."""
    return result_block(ev, now, title="نتیجه بازی")


def _reminder_label(minutes: int) -> str:
    if minutes % 60 == 0 and minutes < 120:
        return f"⏰ <b>{fmt.fa_digits(minutes // 60)} ساعت تا شروع بازی!</b>"
    return f"⏰ <b>{fmt.fa_digits(minutes)} دقیقه تا شروع بازی!</b>"


def reminder_message(
    minutes: int, last: Optional[dict], nxt: dict, now: datetime,
    hide_last_within_min: Optional[int] = None,
) -> str:
    return (
        f"{_reminder_label(minutes)}\n\n"
        f"{status_message(last, nxt, now, hide_last_within_min)}"
    )