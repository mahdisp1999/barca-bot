"""Pure formatting helpers: Persian digits, Jalali/Gregorian dates, remaining time.
No I/O and no project imports."""
from datetime import date, timedelta

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
GREGORIAN_MONTHS = [
    "ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن",
    "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
]
# date.weekday(): Monday == 0. Index based, so it never depends on the server locale.
WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def fa_digits(value) -> str:
    """'12:30' / 45 / '2026' -> Persian digits."""
    return str(value).translate(_FA_DIGITS)


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple:
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


def jalali_date_str(d: date) -> str:
    """e.g. 'شنبه ۲۸ شهریور ۱۴۰۵'"""
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    return f"{WEEKDAYS[d.weekday()]} {fa_digits(jd)} {JALALI_MONTHS[jm - 1]} {fa_digits(jy)}"


def gregorian_date_str(d: date) -> str:
    """e.g. '۱۹ سپتامبر ۲۰۲۶'"""
    return f"{fa_digits(d.day)} {GREGORIAN_MONTHS[d.month - 1]} {fa_digits(d.year)}"


def format_remaining_time(diff: timedelta) -> str:
    """
    >= 24h -> days + hours only   ("۱ روز و ۱۹ ساعت دیگر")
    <  24h -> hours + minutes     ("۵ ساعت و ۱۰ دقیقه دیگر")
    """
    total_minutes = max(int(diff.total_seconds() // 60), 0)
    days, rem = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(rem, 60)

    if days:
        if hours:
            return f"{fa_digits(days)} روز و {fa_digits(hours)} ساعت دیگر"
        return f"{fa_digits(days)} روز دیگر"
    if hours and minutes:
        return f"{fa_digits(hours)} ساعت و {fa_digits(minutes)} دقیقه دیگر"
    if hours:
        return f"{fa_digits(hours)} ساعت دیگر"
    if minutes:
        return f"{fa_digits(minutes)} دقیقه دیگر"
    return "کمتر از ۱ دقیقه دیگر"
