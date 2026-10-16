from datetime import datetime

import pytest

import settings


@pytest.fixture
def make_event():
    """Flat match dict like providers.sportsapipro._parse() returns."""
    def _make(**kw):
        ev = {
            "uid": "1", "summary": "Barcelona - Sevilla", "status": "notstarted",
            "is_home": False, "team": "Barcelona", "opponent": "Sevilla",
            "goals_for": None, "goals_against": None,
            "competition": "LaLiga", "stadium": "Ramón Sánchez-Pizjuán",
            "city": "Sevilla", "country": "Spain",
            "local_dt": datetime(2026, 9, 19, 22, 30),
            "utc_dt": datetime(2026, 9, 19, 19, 0),
        }
        ev.update(kw)
        return ev
    return _make


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "t.db")
    from storage import sqlite as db
    db.init_db()
    return db
