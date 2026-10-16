from datetime import datetime, timedelta

from services import matches, tracking
import settings

NOW = datetime(2026, 9, 18, 12, 0)
REMS = [5, 10, 15, 30, 60]


def test_due_reminder_windows():
    assert matches.due_reminder(60, REMS, 3) == 60
    assert matches.due_reminder(58.5, REMS, 3) == 60
    assert matches.due_reminder(56, REMS, 3) is None      # between windows
    assert matches.due_reminder(10, REMS, 3) == 10
    assert matches.due_reminder(4.2, REMS, 3) == 5
    assert matches.due_reminder(2.5, REMS, 3) == 5
    assert matches.due_reminder(0.5, REMS, 3) is None    # too late: stale reminders are skipped
    assert matches.due_reminder(-1, REMS, 3) is None      # already started


def test_every_reminder_fires_once_with_one_minute_ticks():
    fired = set()
    for t in range(61 * 60, 0, -60):  # one tick per minute, 61 min -> 0
        due = matches.due_reminder(t / 60, REMS, 3)
        if due:
            fired.add(due)
    assert fired == set(REMS)


def test_starting_within_crosses_midnight(make_event):
    ev = make_event(local_dt=datetime(2026, 9, 19, 0, 30))
    assert matches.starting_within([ev], datetime(2026, 9, 18, 23, 35), 60) == [ev]
    assert matches.starting_within([ev], datetime(2026, 9, 18, 20, 0), 60) == []


def test_next_match_skips_started_and_postponed(make_event):
    past = make_event(uid="a", local_dt=NOW - timedelta(hours=1))
    postponed = make_event(uid="b", local_dt=NOW + timedelta(hours=1), status="postponed")
    ok = make_event(uid="c", local_dt=NOW + timedelta(days=1))
    assert matches.next_match([past, postponed, ok], NOW)["uid"] == "c"


def test_last_finished_needs_score(make_event):
    a = make_event(uid="a", goals_for=1, goals_against=0)
    b = make_event(uid="b", goals_for=None, goals_against=None)
    assert matches.last_finished([a, b])["uid"] == "a"
    assert matches.last_finished([]) is None


def test_tracking_flow(make_event):
    state = {}
    tracking.ensure_keys(state)
    ev = make_event(uid="m1", local_dt=NOW)
    assert tracking.watch_new(state, [ev]) is True
    assert tracking.watch_new(state, [ev]) is False
    assert tracking.due_uids(state, NOW + timedelta(minutes=89)) == []
    assert tracking.due_uids(state, NOW + timedelta(minutes=90)) == ["m1"]
    tracking.mark_sent(state, "m1")
    assert state["watched"] == {} and state["result_sent"] == ["m1"]
    assert tracking.watch_new(state, [ev]) is False  # already done, not re-watched


def test_tracking_gives_up(make_event):
    state = {}
    tracking.ensure_keys(state)
    tracking.watch_new(state, [make_event(uid="m1", local_dt=NOW)])
    later = NOW + timedelta(hours=settings.RESULT_GIVE_UP_AFTER_H, minutes=1)
    assert [u for u, _ in tracking.drop_expired(state, later)] == ["m1"]
    assert state["watched"] == {}
