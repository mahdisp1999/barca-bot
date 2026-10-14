"""API-based event layer: fetches next/last events from sportsapi.

Replaces the .ics calendar download with direct API calls.
"""
import os
from datetime import datetime
from typing import Optional

import requests
from config import logger

API_KEY = os.getenv("SPORTS_API_KEY", "YOUR_API_KEY")
BASE_URL = "https://api.sportsapipro.com/v2/football"
TEAM_ID = "2817"  # FC Barcelona


def _get_events(kind: str) -> list:
    """
    Fetch events from API.
    kind: "next" or "last"
    Returns a list of event dicts.
    """
    url = f"{BASE_URL}/team/{TEAM_ID}/events/{kind}/0"
    headers = {"x-api-key": API_KEY}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        raw_events = data.get("events", [])
        return raw_events
    except Exception as e:
        logger.error(f"خطا در دریافت رویدادها از API ({kind}): {e}")
        return []


def _parse_event(ev: dict) -> dict:
    """
    Parse a raw API event into the same format as ics.py events.
    """
    home = ev.get("homeTeam", {}).get("name", "نامشخص")
    away = ev.get("awayTeam", {}).get("name", "نامشخص")
    venue = ev.get("venue", {}).get("stadium", {}).get("name", "نامشخص")
    ts = ev.get("startTimestamp")  # Unix epoch

    # Convert Unix timestamp to datetime
    local_dt = datetime.fromtimestamp(ts) if ts else None

    # Create a summary similar to ICS format
    summary = f"{home} - {away}"

    return {
        "summary": summary,
        "local_dt": local_dt,
        "location": venue,
        "uid": str(ev.get("id", "")),
        "startTimestamp": ts,
    }


def load_events() -> list:
    """
    Load next upcoming events.
    Returns a list of parsed events, sorted by time.
    """
    raw_events = _get_events("next")
    parsed = [_parse_event(ev) for ev in raw_events]
    # Filter out events without valid timestamp
    parsed = [ev for ev in parsed if ev["local_dt"] is not None]
    parsed.sort(key=lambda e: e["local_dt"])
    return parsed


def find_today_matches(events: list) -> list:
    """Find events happening today."""
    today = datetime.now().date()
    return [ev for ev in events if ev["local_dt"] and ev["local_dt"].date() == today]


def find_next_match(events: list) -> Optional[dict]:
    """Find the next upcoming match."""
    now_local = datetime.now()
    for ev in events:
        if ev["local_dt"] and ev["local_dt"] > now_local:
            return ev
    return None


def find_last_result(events: list) -> Optional[dict]:
    """Find the last completed match."""
    # For last results, we need to fetch from API separately
    raw_events = _get_events("last")
    parsed = [_parse_event(ev) for ev in raw_events]
    parsed = [ev for ev in parsed if ev["local_dt"] is not None]
    
    now_local = datetime.now()
    for ev in reversed(parsed):
        if ev["local_dt"] < now_local:
            return ev
    return None


def get_last_match_info(events: list) -> tuple:
    """
    Returns (formatted last match, location) or (None, None).
    """
    last_result = find_last_result(events)
    if not last_result:
        return None, None

    summary = last_result["summary"]
    location = last_result.get("location", "نامشخص")

    # Parse score if available
    import re
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


def should_download_ics(force: bool = False) -> bool:
    """
    For compatibility: always return True to trigger refresh.
    """
    return True


def download_ics() -> bool:
    """
    For compatibility: simulate download by fetching latest data.
    """
    try:
        # Fetch both next and last to ensure data is fresh
        _get_events("next")
        _get_events("last")
        logger.info("داده‌ها از API به‌روز شدند.")
        return True
    except Exception as e:
        logger.error(f"خطا در به‌روزرسانی از API: {e}")
        return False