"""Pure formatting helpers (Persian digits, Jalali date, remaining time). No I/O."""
from datetime import datetime, timedelta

JALALI_MONTH_NAMES = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]

PERSIAN_WEEKDAYS = {
    "Saturday": "شنبه",
    "Sunday": "یکشنبه",
    "Monday": "دوشنبه",
    "Tuesday": "سه‌شنبه",
    "Wednesday": "چهارشنبه",
    "Thursday": "پنجشنبه",
    "Friday": "جمعه",
}


def to_persian_num(n: int) -> str:
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    return "".join(persian_digits[int(c)] for c in str(n))


def gregorian_to_jalali(gy: int, gm: int, gd: int):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        + gd
        + g_d_m[gm - 1]
    )
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def to_jalali_str(dt: datetime) -> str:
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    weekday = PERSIAN_WEEKDAYS.get(dt.strftime("%A"), "")
    return f"{weekday} {jd} {JALALI_MONTH_NAMES[jm - 1]} {jy}".strip()


def format_remaining_time(diff: timedelta) -> str:
    """
    < 24h  -> hours + minutes   (e.g. "۵ ساعت و ۱۰ دقیقه دیگر")
    >= 24h -> days + hours only (e.g. "۲ روز و ۳ ساعت دیگر")
    """
    total_minutes = max(int(diff.total_seconds() // 60), 0)
    days, rem = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(rem, 60)

    if days > 0:
        if hours:
            return f"{to_persian_num(days)} روز و {to_persian_num(hours)} ساعت دیگر"
        return f"{to_persian_num(days)} روز دیگر"

    if hours and minutes:
        return f"{to_persian_num(hours)} ساعت و {to_persian_num(minutes)} دقیقه دیگر"
    if hours:
        return f"{to_persian_num(hours)} ساعت دیگر"
    return f"{to_persian_num(minutes)} دقیقه دیگر"


def opponent_of(summary: str) -> str:
    """Strip Barcelona's name from the event title, leaving the opponent."""
    return (
        summary.replace("FC Barcelona", "")
        .replace("Barcelona", "")
        .replace("vs", "")
        .replace("VS", "")
        .strip(" -|")
    )


def next_match_block(next_match: dict, now: datetime) -> str:
    """The 'next match' text block shared by /status and the automatic status."""
    diff = next_match["local_dt"] - now
    return (
        f"⏳ **بازی بعدی:** {next_match['local_dt'].strftime('%Y-%m-%d %H:%M')}\n"
        f"🗓️ **تاریخ شمسی:** {to_jalali_str(next_match['local_dt'])}\n"
        f"📅 {next_match['summary']}\n"
        f"⏰ **{format_remaining_time(diff)}**\n"
        f"🏟️ زمین: {next_match.get('location', 'نامشخص')}\n"
    )
