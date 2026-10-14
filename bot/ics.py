"""Calendar layer: download, parse (cached), and match lookups.

Speed notes:
  * load_events() only re-parses when the file's mtime changes.
  * local_dt is computed once at parse time; events are kept sorted.
  * Commands never download; the job refreshes hourly (in a thread).
"""
import os
import re
from datetime import datetime
from typing import Optional

import requests
import urllib3
from icalendar import Calendar

from config import ICS_DOWNLOAD_INTERVAL, ICS_PATH, ICS_URL, logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_last_download_time = 0
_cache = {"mtime": None, "events": []}


def download_ics() -> bool:
    """Download the .ics. On failure, keep the cached file and report success."""
    global _last_download_time
    try:
        r = requests.get(
            ICS_URL,
            timeout=30,
            verify=False,  # required by this host
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Bot/1.0)"},
        )
        r.raise_for_status()
        tmp = ICS_PATH + ".tmp"
        with open(tmp, "wb") as f:
            f.write(r.content)
        os.replace(tmp, ICS_PATH)  # atomic: readers never see a half-written file
        _last_download_time = datetime.now().timestamp()
        logger.info("فایل تقویم به‌روز شد (SSL verification غیرفعال).")
        return True
    except Exception as e:
        if os.path.isfile(ICS_PATH):
            logger.warning(
                f"خطا در دریافت تقویم اما فایل کش موجود است، ادامه می‌دهیم: {e}"
            )
            return True
        logger.error(f"خطا در دریافت تقویم و فایل قبلی موجود نیست: {e}")
        return False


def should_download_ics(force: bool = False) -> bool:
    if force:
        return True
    return datetime.now().timestamp() - _last_download_time >= ICS_DOWNLOAD_INTERVAL


def load_events() -> list:
    """Cached, sorted events, each with a naive-local 'local_dt'. Never downloads
    unless the file does not exist yet (first run)."""
    if not os.path.isfile(ICS_PATH):
        download_ics()
        if not os.path.isfile(ICS_PATH):
            return []

    mtime = os.path.getmtime(ICS_PATH)
    if _cache["mtime"] == mtime:
        return _cache["events"]

    with open(ICS_PATH, "rb") as f:
        cal = Calendar.from_ical(f.read())

    events = []
    for component in cal.walk():
        if component.name == "VEVENT":
            start = component.get("DTSTART").dt
            if isinstance(start, datetime):
                local_dt = (
                    start.astimezone().replace(tzinfo=None)
                    if start.tzinfo is not None
                    else start
                )
                events.append({
                    "summary": str(component.get("SUMMARY")),
                    "dtstart": start,
                    "local_dt": local_dt,
                    "location": str(component.get("LOCATION", "")),
                    "uid": str(component.get("UID", "")),
                })
    events.sort(key=lambda e: e["local_dt"])
    _cache["mtime"] = mtime
    _cache["events"] = events
    return events


def find_today_matches(events: list) -> list:
    today = datetime.now().date()
    return [ev for ev in events if ev["local_dt"].date() == today]


def find_next_match(events: list) -> Optional[dict]:
    now_local = datetime.now()
    for ev in events:  # sorted ascending
        if ev["local_dt"] > now_local:
            return ev
    return None


def find_last_result(events: list) -> Optional[dict]:
    now_local = datetime.now()
    for ev in reversed(events):  # sorted ascending
        if ev["local_dt"] < now_local:
            return ev
    return None


def get_last_match_info(events: list) -> tuple:
    """Returns (formatted last match, location) or (None, None)."""
    last_result = find_last_result(events)
    if not last_result:
        return None, None

    summary = last_result["summary"]
    location = last_result.get("location", "نامشخص")

    # e.g. "Athletic de Bilbao - FC Barcelona (0-1)"
    match = re.search(r"(.+?)\s*\((\d+)\s*-\s*(\d+)\)", summary)

    if match:
        team1_raw = match.group(1).strip()
        score1 = match.group(2)
        score2 = match.group(3)
        if " - " in team1_raw:
            team1, team2 = team1_raw.split(" - ", 1)
            formatted_summary = f"{team2.strip()} {score2} | {score1} {team1.strip()}"
        else:
            formatted_summary = summary
    else:
        formatted_summary = summary

    return formatted_summary, location
