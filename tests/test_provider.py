import settings
from providers import sportsapipro as api

RAW = {
    "id": 42, "startTimestamp": 1789844400,  # 2026-09-19 19:00 UTC
    "status": {"type": "finished"},
    "homeTeam": {"id": 2833, "name": "Sevilla"},
    "awayTeam": {"id": 2817, "name": "Barcelona"},
    "homeScore": {"current": 1}, "awayScore": {"current": 3},
    "tournament": {"name": "LaLiga, Regular Season", "uniqueTournament": {"name": "LaLiga"}},
    "venue": {"stadium": {"name": "Ramón Sánchez-Pizjuán"}, "city": {"name": "Sevilla"},
              "country": {"name": "Spain"}},
}


def test_parse_is_relative_to_team():
    ev = api._parse(RAW)
    assert ev["is_home"] is False
    assert (ev["team"], ev["opponent"]) == ("Barcelona", "Sevilla")
    assert (ev["goals_for"], ev["goals_against"]) == (3, 1)
    assert ev["competition"] == "LaLiga"
    assert (ev["stadium"], ev["city"], ev["country"]) == ("Ramón Sánchez-Pizjuán", "Sevilla", "Spain")
    assert ev["utc_dt"].hour == 19 and ev["local_dt"].hour == 22 and ev["local_dt"].minute == 30


def test_parse_tolerates_missing_fields():
    ev = api._parse({"id": 1, "startTimestamp": 1789844400, "homeTeam": {"id": 2817}})
    assert ev["stadium"] == "" and ev["competition"] == "" and ev["goals_for"] is None
    assert api._parse({"id": 1}) is None  # no timestamp


def test_failed_fetch_keeps_old_data(monkeypatch):
    monkeypatch.setattr(api, "_fetch", lambda kind: [RAW])
    api._cache["last"]["at"] = 0
    assert len(api.load_finished(force=True)) == 1
    monkeypatch.setattr(api, "_fetch", lambda kind: None)
    assert len(api.load_finished(force=True)) == 1  # stale data survives a failure


def test_last_feed_keeps_only_finished_with_score(monkeypatch):
    unfinished = dict(RAW, id=43, status={"type": "inprogress"})
    monkeypatch.setattr(api, "_fetch", lambda kind: [RAW, unfinished])
    assert [e["uid"] for e in api.load_finished(force=True)] == ["42"]


def test_refresh_is_throttled(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "_fetch", lambda kind: calls.append(kind) or [RAW])
    monkeypatch.setattr(api, "_last_refresh", 0.0)
    assert api.refresh() is True and len(calls) == 2
    assert api.refresh() is True and len(calls) == 2  # second call served from cache
