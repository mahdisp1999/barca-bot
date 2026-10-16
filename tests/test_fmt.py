from datetime import date, timedelta

from formatting import fmt


def test_jalali_known_dates():
    assert fmt.gregorian_to_jalali(2025, 3, 21) == (1404, 1, 1)
    assert fmt.gregorian_to_jalali(2025, 3, 20) == (1403, 12, 30)  # 1403 is a leap year
    assert fmt.gregorian_to_jalali(2026, 3, 21) == (1405, 1, 1)
    assert fmt.gregorian_to_jalali(2026, 9, 23) == (1405, 7, 1)
    assert fmt.gregorian_to_jalali(2026, 9, 19) == (1405, 6, 28)


def test_jalali_string_uses_persian_digits_and_weekday():
    assert fmt.jalali_date_str(date(2026, 9, 19)) == "شنبه ۲۸ شهریور ۱۴۰۵"


def test_gregorian_string():
    assert fmt.gregorian_date_str(date(2026, 9, 19)) == "۱۹ سپتامبر ۲۰۲۶"


def test_remaining_time():
    assert fmt.format_remaining_time(timedelta(days=1, hours=19, minutes=30)) == "۱ روز و ۱۹ ساعت دیگر"
    assert fmt.format_remaining_time(timedelta(days=2)) == "۲ روز دیگر"
    assert fmt.format_remaining_time(timedelta(hours=5, minutes=10)) == "۵ ساعت و ۱۰ دقیقه دیگر"
    assert fmt.format_remaining_time(timedelta(minutes=7)) == "۷ دقیقه دیگر"
    assert fmt.format_remaining_time(timedelta(seconds=10)) == "کمتر از ۱ دقیقه دیگر"
    assert fmt.format_remaining_time(timedelta(minutes=-5)) == "کمتر از ۱ دقیقه دیگر"


def test_fa_digits():
    assert fmt.fa_digits("22:30") == "۲۲:۳۰"
