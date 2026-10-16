"""Persian names for teams and competitions. Unknown names fall back to the
original (English) text, so a missing entry never breaks a message.

To add a team: put its normalized English name (lowercase, no accents, no
punctuation, no 'fc'/'cf') on the left. Names come from the API as-is.
"""
import re
import unicodedata
from typing import Optional

_NOISE = {"fc", "cf"}


def _key(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    words = [w for w in re.split(r"[^a-z0-9]+", text) if w and w not in _NOISE]
    return " ".join(words)


TEAMS_FA = {
    "barcelona": "بارسلونا",
    "real madrid": "رئال مادرید",
    "atletico madrid": "اتلتیکو مادرید",
    "sevilla": "سویا",
    "valencia": "والنسیا",
    "villarreal": "ویارئال",
    "athletic club": "اتلتیک بیلبائو",
    "athletic bilbao": "اتلتیک بیلبائو",
    "real sociedad": "رئال سوسیه‌داد",
    "real betis": "رئال بتیس",
    "girona": "ژیرونا",
    "osasuna": "اوساسونا",
    "getafe": "ختافه",
    "celta vigo": "سلتا ویگو",
    "rayo vallecano": "رایو وایه‌کانو",
    "mallorca": "مایورکا",
    "espanyol": "اسپانیول",
    "alaves": "آلاوس",
    "levante": "لوانته",
    "elche": "التچه",
    "real oviedo": "رئال اوویدو",
    "racing santander": "راسینگ سانتاندر",
    "paris saint germain": "پاری‌سن‌ژرمن",
    "bayern munich": "بایرن مونیخ",
    "borussia dortmund": "بوروسیا دورتموند",
    "manchester city": "منچسترسیتی",
    "manchester united": "منچستریونایتد",
    "liverpool": "لیورپول",
    "arsenal": "آرسنال",
    "chelsea": "چلسی",
    "tottenham hotspur": "تاتنهام",
    "inter": "اینتر",
    "inter milan": "اینتر",
    "ac milan": "میلان",
    "juventus": "یوونتوس",
    "napoli": "ناپولی",
    "atalanta": "آتالانتا",
    "benfica": "بنفیکا",
    "porto": "پورتو",
    "ajax": "آژاکس",
}

# Short form used inside sentences ("بارسا با یک پیروزی ...").
TEAMS_SHORT_FA = {"barcelona": "بارسا"}

# (substring of the normalized competition name, Persian name). Order matters.
_COMPETITIONS = [
    ("uefa super cup", "سوپرکاپ اروپا"),
    ("champions league", "لیگ قهرمانان اروپا"),
    ("europa league", "لیگ اروپا"),
    ("conference league", "لیگ کنفرانس اروپا"),
    ("copa del rey", "کوپا دل ری"),
    ("supercopa", "سوپرکاپ اسپانیا"),
    ("super cup", "سوپرکاپ"),
    ("club world cup", "جام باشگاه‌های جهان"),
    ("laliga 2", "لالیگا ۲"),
    ("laliga", "لالیگا"),
    ("la liga", "لالیگا"),
    ("primera division", "لالیگا"),
    ("friendl", "بازی دوستانه"),
]


def team_fa(name: str, short: bool = False) -> Optional[str]:
    key = _key(name)
    if short and key in TEAMS_SHORT_FA:
        return TEAMS_SHORT_FA[key]
    return TEAMS_FA.get(key)


def competition_fa(name: str) -> str:
    if not name:
        return "نامشخص"
    key = _key(name)
    for needle, fa in _COMPETITIONS:
        if needle in key:
            return fa
    return name
