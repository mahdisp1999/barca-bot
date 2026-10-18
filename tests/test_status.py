from datetime import datetime, timedelta

from formatting import names, status

NOW = datetime(2026, 9, 30, 12, 0)


def test_win_at_home(make_event):
    ev = make_event(is_home=True, opponent="Racing Santander", goals_for=7, goals_against=2,
                    stadium="Spotify Camp Nou", status="finished",
                    local_dt=datetime(2026, 9, 26, 22, 0))
    text = status.result_block(ev, NOW)
    assert "بارسلونا ۷ - ۲ راسینگ سانتاندر" in text
    assert "شنبه ۴ مهر ۱۴۰۵" in text and "۴ روز پیش" in text
    assert "در ورزشگاه خانگی Spotify Camp Nou" in text
    assert "پیروزی پرگل" in text and "✅" in text
    assert "لالیگا" in text


def test_draw_and_loss_text_is_dynamic(make_event):
    draw = status.result_block(make_event(goals_for=1, goals_against=1), NOW)
    assert "🤝" in draw and "تساوی" in draw and "در زمین حریف" in draw
    loss = status.result_block(make_event(goals_for=0, goals_against=1), NOW)
    assert "❌" in loss and "شکست" in loss


def test_next_block(make_event):
    now = datetime(2026, 9, 18, 3, 0)
    text = status.next_block(make_event(), now)
    assert "سویا (Sevilla)" in text and "(Away)" in text
    assert "شنبه ۲۸ شهریور ۱۴۰۵، (۱۹ سپتامبر ۲۰۲۶)" in text
    assert "۲۲:۳۰ به وقت ایران (۱۹:۰۰ به وقت جهانی UTC)" in text
    assert "۱ روز و ۱۹ ساعت دیگر" in text
    assert "شهر Sevilla، Spain" in text


def test_html_is_escaped(make_event):
    text = status.next_block(make_event(opponent="A<b>&B", stadium="X<script>"), NOW)
    assert "<script>" not in text and "A<b>" not in text


def test_missing_data_does_not_crash(make_event):
    text = status.next_block(make_event(stadium="", city="", country="", competition=""), NOW)
    assert "نامشخص" in text
    assert status.status_message(None, None, NOW).startswith("📅")


def test_reminder_label(make_event):
    assert "۱ ساعت" in status.reminder_message(60, None, make_event(), NOW)
    assert "۱۰ دقیقه" in status.reminder_message(10, None, make_event(), NOW)


def test_last_result_hidden_within_window(make_event):
    last = make_event(status="finished", goals_for=2, goals_against=0, is_home=True,
                      local_dt=datetime(2026, 9, 26, 22, 0))
    close = make_event(local_dt=NOW + timedelta(minutes=100))  # 100 min to kick-off
    far = make_event(local_dt=NOW + timedelta(minutes=121))    # 121 min to kick-off
    # within 120 minutes: no previous result
    assert "نتیجه آخرین بازی" not in status.reminder_message(60, last, close, NOW, 120)
    # more than 120 minutes: previous result is shown as before
    assert "نتیجه آخرین بازی" in status.reminder_message(60, last, far, NOW, 120)
    # no window given: old behaviour
    assert "نتیجه آخرین بازی" in status.reminder_message(60, last, close, NOW)


def test_names_fallback():
    assert names.team_fa("FC Barcelona") == "بارسلونا"
    assert names.team_fa("Unknown Town") is None
    assert names.competition_fa("UEFA Champions League") == "لیگ قهرمانان اروپا"
    assert names.competition_fa("Supercopa de España") == "سوپرکاپ اسپانیا"
    assert names.competition_fa("UEFA Super Cup") == "سوپرکاپ اروپا"
    assert names.competition_fa("Some Cup") == "Some Cup"