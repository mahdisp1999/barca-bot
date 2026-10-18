import sqlite3

import settings


def test_alert_dedupe_and_reschedule(tmp_db):
    db = tmp_db
    assert db.alert_pending("m1", "10m", "2026-09-19T22:30", 1) is True
    assert db.alert_pending("m1", "10m", "2026-09-19T22:30", 1) is True   # not sent yet
    db.mark_alert_sent("m1", "10m", "2026-09-19T22:30", 1)
    assert db.alert_pending("m1", "10m", "2026-09-19T22:30", 1) is False  # sent: no repeat
    assert db.alert_pending("m1", "10m", "2026-09-19T23:30", 1) is True   # rescheduled: new reminder
    assert db.alert_pending("m1", "5m", "2026-09-19T22:30", 1) is True    # other reminder type


def test_log_and_queries(tmp_db):
    db = tmp_db
    db.log_event(kind="command", direction="inbound", command="status", user_id=1, extra={"k": "v"})
    db.log_event(kind="denied", direction="inbound", command="usage", user_id=2)
    db.upsert_user(user_id=1, username="a", command="status")
    db.upsert_user(user_id=1, username="a", command="sync")
    assert db.total_events() == 2 and db.distinct_users() == 2
    assert len(db.query_events(kind="denied")) == 1
    assert len(db.query_events(user_id=1)) == 1
    assert db.counts_by("kind") == {"command": 1, "denied": 1}
    assert db.top_users()[0]["total_events"] == 2


def test_cleanup_old_data(tmp_db):
    db = tmp_db
    with db.connect() as conn:
        conn.execute("INSERT INTO usage_log (ts, kind, direction) VALUES ('2000-01-01T00:00:00','command','inbound')")
    db.log_event(kind="command", direction="inbound")
    assert db.cleanup_old_data(30, 180)["log"] == 1
    assert db.total_events() == 1


def test_migrates_old_alert_table(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE match_alerts (match_uid TEXT NOT NULL, alert_type TEXT NOT NULL, "
        "sent_at TEXT NOT NULL, sent INTEGER NOT NULL DEFAULT 0, match_key TEXT NOT NULL, "
        "PRIMARY KEY (match_uid, alert_type)); PRAGMA user_version = 2;"
    )
    conn.close()
    monkeypatch.setattr(settings, "DB_PATH", path)
    monkeypatch.setattr(settings, "LEGACY_DB_PATH", tmp_path / "no-legacy.db")
    monkeypatch.setattr(settings, "LEGACY_STATE_FILE", tmp_path / "no-state.json")
    from storage import sqlite as db
    db.init_db()
    with db.connect() as c:
        cols = [r["name"] for r in c.execute("PRAGMA table_info(match_alerts)")]
        assert "kickoff" in cols
        assert c.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION