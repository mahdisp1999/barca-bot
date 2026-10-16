"""Match data from SportsAPI Pro (Football V2). No Telegram, no formatting.

Public API:
  load_upcoming(force=False) -> list   upcoming matches, oldest first (cached)
  load_finished(force=False) -> list   finished matches with a score, oldest first (cached)
  refresh() -> bool                    re-fetch both feeds; True only if both succeeded

Each event is a flat dict, see _parse(). The API quota is shared across all
sports of the account, so every call is cached and failures are retried gently.
"""
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

import settings

logger = logging.getLogger(__name__)

_cache = {
    "next": {"at": 0.0, "events": []},
    "last": {"at": 0.0, "events": []},
}
_locks = {"next": threading.Lock(), "last": threading.Lock()}
_TTL = {"next": settings.CACHE_TTL_NEXT, "last": settings.CACHE_TTL_LAST}
_refresh_lock = threading.Lock()
_last_refresh = 0.0
_warned = set()


def _warn_once(key: str, msg: str, *args) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning(msg, *args)


def _d(value) -> dict:
    return value if isinstance(value, dict) else {}


def _fetch(kind: str) -> Optional[list]:
    """Call the API. Returns the raw event list, or None on any failure."""
    if not settings.SPORTS_API_KEY:
        logger.error("SPORTS_API_KEY تنظیم نشده است.")
        return None

    url = f"{settings.SPORTS_API_BASE_URL}/teams/{settings.TEAM_ID}/events/{kind}/0"
    try:
        r = httpx.get(
            url, headers={"x-api-key": settings.SPORTS_API_KEY}, timeout=settings.REQUEST_TIMEOUT
        )
        remaining = r.headers.get("X-RateLimit-Remaining")
        if remaining and remaining.isdigit() and int(remaining) < 20:
            logger.warning("سهمیه‌ی API رو به اتمام است (%s درخواست مانده)", remaining)
        r.raise_for_status()
        body = r.json()
        if not body.get("success"):
            raise ValueError(f"success=false: {str(body)[:200]}")
        return body["data"]["events"]
    except Exception as e:
        logger.error("خطا در دریافت رویدادهای %s از API: %s", kind, e)
        return None


def _parse(ev: dict) -> Optional[dict]:
    """One raw API event -> the flat dict the rest of the bot uses.

    `team` / `opponent` / `goals_for` / `goals_against` are relative to TEAM_ID,
    so nothing outside this file needs to know who is home or away.
    """
    try:
        ts = int(ev.get("startTimestamp"))
    except (TypeError, ValueError):
        return None

    home, away = _d(ev.get("homeTeam")), _d(ev.get("awayTeam"))
    home_id, away_id = str(home.get("id", "")), str(away.get("id", ""))
    if settings.TEAM_ID not in (home_id, away_id):
        _warn_once(
            "team-mismatch",
            "TEAM_ID=%s در هیچ‌کدام از دو تیم بازی نیست؛ TEAM_ID را با پاسخ واقعی API چک کنید.",
            settings.TEAM_ID,
        )
    is_home = home_id == settings.TEAM_ID

    home_name = home.get("name") or "نامشخص"
    away_name = away.get("name") or "نامشخص"
    home_goals = _d(ev.get("homeScore")).get("current")
    away_goals = _d(ev.get("awayScore")).get("current")

    tournament = _d(ev.get("tournament"))
    competition = _d(tournament.get("uniqueTournament")).get("name") or tournament.get("name") or ""

    venue = _d(ev.get("venue"))
    stadium = _d(venue.get("stadium")).get("name") or venue.get("name") or ""

    return {
        "uid": str(ev.get("id", "")),
        "summary": f"{home_name} - {away_name}",
        "status": _d(ev.get("status")).get("type", ""),  # e.g. "notstarted", "finished"
        "is_home": is_home,
        "team": home_name if is_home else away_name,
        "opponent": away_name if is_home else home_name,
        "goals_for": home_goals if is_home else away_goals,
        "goals_against": away_goals if is_home else home_goals,
        "competition": competition,
        "stadium": stadium,
        "city": _d(venue.get("city")).get("name") or "",
        "country": _d(venue.get("country")).get("name") or "",
        "local_dt": datetime.fromtimestamp(ts, settings.LOCAL_TZ).replace(tzinfo=None),
        "utc_dt": datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None),
    }


def _load(kind: str) -> bool:
    """Fetch one feed into the cache. On failure the old data is kept."""
    entry = _cache[kind]
    raw = _fetch(kind)
    if raw is None:
        # Retry sooner than the normal TTL, but not on every single call.
        entry["at"] = time.time() - _TTL[kind] + settings.RETRY_AFTER_FAILURE
        return False

    parsed = [p for p in (_parse(e) for e in raw if isinstance(e, dict)) if p]
    parsed.sort(key=lambda e: e["local_dt"])
    if kind == "last":
        parsed = [
            e for e in parsed
            if e["status"] == "finished"
            and e["goals_for"] is not None
            and e["goals_against"] is not None
        ]
    entry["at"] = time.time()
    entry["events"] = parsed
    return True


def _events(kind: str, force: bool = False) -> list:
    # The lock makes concurrent callers share one fetch instead of each hitting the API.
    with _locks[kind]:
        if force or time.time() - _cache[kind]["at"] >= _TTL[kind]:
            _load(kind)
        return list(_cache[kind]["events"])


def load_upcoming(force: bool = False) -> list:
    return _events("next", force)


def load_finished(force: bool = False) -> list:
    return _events("last", force)


def refresh() -> bool:
    """Re-fetch both feeds (used by /sync). Calls within MIN_REFRESH_INTERVAL of the
    last successful refresh are answered from the cache, to protect the quota."""
    global _last_refresh
    with _refresh_lock:
        if time.time() - _last_refresh < settings.MIN_REFRESH_INTERVAL:
            return True
        ok = True
        for kind in ("next", "last"):
            with _locks[kind]:
                ok = _load(kind) and ok
        if ok:
            _last_refresh = time.time()
        return ok
