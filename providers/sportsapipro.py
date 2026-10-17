"""Match data from SportsAPI Pro (Football V2). No Telegram, no formatting.

Public API:
  load_upcoming(force=False) -> list   upcoming matches, oldest first (cached)
  load_finished(force=False) -> list   finished matches with a score, oldest first (cached)
  refresh() -> bool                    re-fetch both feeds; True only if both succeeded

Each event is a flat dict, see _parse(). The API quota is shared across all
sports of the account, so:
  * every call is cached, and the cache is also saved to settings.CACHE_FILE,
    so a restart (or an API outage) never leaves the bot without data;
  * after a failure the API is left alone for a while (back-off). HTTP 429
    honours the Retry-After header; otherwise the wait doubles per failure.
    While backed off, callers silently get the last good data.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from providers import ics as ics_fallback

import httpx

import settings

logger = logging.getLogger(__name__)

_cache = {
    "next": {"at": 0.0, "events": []},
    "last": {"at": 0.0, "events": []},
}
_locks = {"next": threading.Lock(), "last": threading.Lock()}
_refresh_lock = threading.Lock()
_disk_lock = threading.Lock()
_last_refresh = 0.0
_warned = set()

# Back-off is global (not per feed) because the quota is shared by both feeds.
_blocked_until = 0.0
_fail_streak = 0


def _local_now() -> datetime:
    return datetime.now(settings.LOCAL_TZ).replace(tzinfo=None)


def _ttl(kind: str) -> int:
    """'next' is refreshed more often on match day (kick-off close)."""
    if kind == "next":
        now = _local_now()
        for e in _cache["next"]["events"]:
            mins = (e["local_dt"] - now).total_seconds() / 60
            if -30 <= mins <= settings.NEAR_KICKOFF_WINDOW_MIN:
                return settings.NEAR_KICKOFF_TTL
        return settings.CACHE_TTL_NEXT
    return settings.CACHE_TTL_LAST


def _warn_once(key: str, msg: str, *args) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning(msg, *args)


def _d(value) -> dict:
    return value if isinstance(value, dict) else {}


# ---------- disk cache ----------

def _dump(ev: dict) -> dict:
    return {**ev, "local_dt": ev["local_dt"].isoformat(), "utc_dt": ev["utc_dt"].isoformat()}


def _undump(ev: dict) -> dict:
    return {**ev, "local_dt": datetime.fromisoformat(ev["local_dt"]),
            "utc_dt": datetime.fromisoformat(ev["utc_dt"])}


def _save_disk() -> None:
    data = {"blocked_until": _blocked_until, "fail_streak": _fail_streak}
    for kind, entry in _cache.items():
        data[kind] = {"at": entry["at"], "events": [_dump(e) for e in entry["events"]]}
    tmp = str(settings.CACHE_FILE) + ".tmp"
    try:
        with _disk_lock:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, settings.CACHE_FILE)
    except OSError as e:
        logger.warning("ذخیره‌ی کش روی دیسک ممکن نشد: %s", e)


def _load_disk() -> None:
    """Restore the last good data at startup. A broken file is simply ignored."""
    global _blocked_until, _fail_streak
    try:
        with open(settings.CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for kind in _cache:
            entry = data.get(kind) or {}
            events = [_undump(e) for e in entry.get("events", [])]
            events.sort(key=lambda e: e["local_dt"])
            _cache[kind] = {"at": float(entry.get("at", 0.0)), "events": events}
        _blocked_until = float(data.get("blocked_until", 0.0))
        _fail_streak = int(data.get("fail_streak", 0))
    except FileNotFoundError:
        return
    except Exception as e:  # corrupt / old format: start empty
        logger.warning("فایل کش خوانده نشد و نادیده گرفته شد: %s", e)


# ---------- API ----------

def _register_failure(kind: str, err: Exception, status: Optional[int] = None,
                      retry_after: Optional[str] = None) -> None:
    """Log once and push the next allowed API call into the future."""
    global _blocked_until, _fail_streak
    _fail_streak += 1
    if status == 429:
        wait = int(retry_after) if retry_after and retry_after.isdigit() else \
            settings.RATE_LIMIT_BACKOFF * 2 ** (_fail_streak - 1)
    else:
        wait = settings.RETRY_AFTER_FAILURE * 2 ** (_fail_streak - 1)
    wait = min(max(wait, settings.RETRY_AFTER_FAILURE), settings.MAX_BACKOFF)
    _blocked_until = time.time() + wait
    logger.error("خطا در دریافت رویدادهای %s از API: %s — تا %d دقیقه‌ی دیگر دوباره تلاش نمی‌شود.",
                 kind, err, max(wait // 60, 1))
    _save_disk()


def _fetch(kind: str) -> Optional[list]:
    """Call the API. Returns the raw event list, or None on failure / back-off."""
    global _fail_streak
    if not settings.SPORTS_API_KEY:
        logger.error("SPORTS_API_KEY تنظیم نشده است.")
        return None
    if time.time() < _blocked_until:
        return None  # backed off: callers fall back to the cached data

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
        events = body["data"]["events"]
    except httpx.HTTPStatusError as e:
        _register_failure(kind, e, e.response.status_code, e.response.headers.get("Retry-After"))
        return None
    except Exception as e:
        _register_failure(kind, e)
        return None
    _fail_streak = 0
    return events


def _parse(ev: dict) -> Optional[dict]:
    """One raw API event -> the flat dict the rest of the bot uses.

    `team` / `opponent` / `goals_for` / `goals_against` are relative to TEAM_ID,
    so nothing outside this file needs to know who is home or away.
    """
    raw_ts = ev.get("startTimestamp")
    if raw_ts is None:
        return None
    try:
        ts = int(raw_ts)
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
    """Fetch one feed into the cache. On failure the old data is kept untouched."""
    raw = _fetch(kind)
    if raw is None:
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
    _cache[kind] = {"at": time.time(), "events": parsed}
    _save_disk()
    return True


def _events(kind: str, force: bool = False) -> list:
    with _locks[kind]:
        if force or time.time() - _cache[kind]["at"] >= _ttl(kind):
            _load(kind)  # خطا؟ داده‌ی قبلی نگه داشته می‌شود
        if not _cache[kind]["events"]:
            # پلن B: API برای این لیست هیچ داده‌ای ندارد
            return ics_fallback.fallback(kind)
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


_load_disk()