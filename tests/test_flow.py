"""End-to-end flows with a fake bot: no network, no Telegram."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import settings
import jobs
import commands
import audit
from services import matches, state as state_store


@pytest.fixture
def env(tmp_db, monkeypatch, make_event):
    monkeypatch.setattr(settings, "ADMIN_ID", 111)
    monkeypatch.setattr(settings, "ALLOWED_IDS", {111, 222})
    monkeypatch.setattr(state_store, "_state", None)
    now = datetime(2026, 9, 19, 21, 25)
    ev = make_event(uid="m1", local_dt=now + timedelta(minutes=30))
    last = make_event(uid="old", status="finished", is_home=True, opponent="Racing Santander",
                      goals_for=7, goals_against=2, local_dt=now - timedelta(days=4))
    monkeypatch.setattr(matches, "now_local", lambda: now)
    monkeypatch.setattr(matches, "upcoming", lambda force=False: [ev])
    monkeypatch.setattr(matches, "finished", lambda force=False: [last])
    ctx = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()), args=[])
    return SimpleNamespace(db=tmp_db, ctx=ctx, now=now, ev=ev, last=last, mp=monkeypatch)


def test_reminder_sent_once(env):
    asyncio.run(jobs.check_reminders(env.ctx))
    asyncio.run(jobs.check_reminders(env.ctx))  # next tick: must not repeat
    assert env.ctx.bot.send_message.await_count == 1
    kwargs = env.ctx.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 111 and "۳۰ دقیقه تا شروع بازی" in kwargs["text"]
    assert "راسینگ سانتاندر" in kwargs["text"] and "سویا" in kwargs["text"]
    assert len(env.db.query_events(kind="alert")) == 1


def test_result_sent_after_90_minutes(env):
    kick = env.now - timedelta(minutes=100)
    done = dict(env.ev, uid="m1", status="finished", goals_for=3, goals_against=1, local_dt=kick)
    env.mp.setattr(matches, "upcoming", lambda force=False: [])
    env.mp.setattr(matches, "finished", lambda force=False: [done])
    state = state_store.get()
    state["watched"] = {"m1": {"ts": kick.isoformat(), "summary": "Sevilla - Barcelona"}}
    state["result_sent"] = []
    state["last_bot_message_time"] = 9e12  # silence the auto status
    asyncio.run(jobs.check_results(env.ctx))
    text = env.ctx.bot.send_message.await_args.kwargs["text"]
    assert "نتیجه بازی" in text and "۳ - ۱" in text
    assert state["watched"] == {} and state["result_sent"] == ["m1"]


def _update(user_id, text="/status"):
    user = SimpleNamespace(id=user_id, username="u", first_name="U")
    chat = SimpleNamespace(id=user_id, type="private")
    return SimpleNamespace(effective_user=user, effective_chat=chat,
                           message=SimpleNamespace(text=text))


def _run_command(name, update, ctx):
    handler = next(h for h in commands.build_handlers() if name in h.commands)
    asyncio.run(handler.callback(update, ctx))


def test_status_command_for_allowed_user(env):
    _run_command("status", _update(222), env.ctx)
    text = env.ctx.bot.send_message.await_args.kwargs["text"]
    assert "نتیجه آخرین بازی" in text and "بازی بعدی" in text


def test_denied_user_is_logged_once(env):
    _run_command("status", _update(999), env.ctx)
    asyncio.run(audit.log_inbound(_update(999), env.ctx))  # group-1 logger runs after
    assert env.ctx.bot.send_message.await_args.kwargs["text"] == "⚠️ دسترسی ندارید."
    inbound = [r for r in env.db.query_events() if r["direction"] == "inbound"]
    assert len(inbound) == 1 and inbound[0]["kind"] == "denied"


def test_usage_is_admin_only_even_for_allowed_users(env):
    _run_command("usage", _update(222, "/usage"), env.ctx)
    assert env.ctx.bot.send_message.await_args.kwargs["text"] == "⚠️ دسترسی ندارید."
    inbound = [r for r in env.db.query_events() if r["direction"] == "inbound"]
    asyncio.run(audit.log_inbound(_update(222, "/usage"), env.ctx))
    assert len([r for r in env.db.query_events() if r["direction"] == "inbound"]) == len(inbound)
    _run_command("usage", _update(111, "/usage"), env.ctx)
    assert "گزارش استفاده" in env.ctx.bot.send_message.await_args.kwargs["text"]


def test_usage_closed_when_admin_not_configured(env):
    env.mp.setattr(settings, "ADMIN_ID", 0)
    _run_command("usage", _update(222, "/usage"), env.ctx)
    assert env.ctx.bot.send_message.await_args.kwargs["text"] == "⚠️ دسترسی ندارید."


def test_broadcast_status_sends_to_all_allowed_users(env):
    _run_command("broadcast_status", _update(111, "/broadcast_status"), env.ctx)
    calls = env.ctx.bot.send_message.await_args_list
    # دو پیام وضعیت (برای ادمین و کاربر ۲۲۲) + یک پیام خلاصه برای ادمین
    assert len(calls) == 3
    assert [calls[0].kwargs["chat_id"], calls[1].kwargs["chat_id"]] == [111, 222]
    assert "نتیجه آخرین بازی" in calls[0].kwargs["text"]
    assert "۲ از ۲" in calls[2].kwargs["text"]


def test_broadcast_status_is_admin_only(env):
    _run_command("broadcast_status", _update(222, "/broadcast_status"), env.ctx)
    calls = env.ctx.bot.send_message.await_args_list
    assert len(calls) == 1  # فقط پیام «دسترسی ندارید»
    assert calls[0].kwargs["chat_id"] == 222
    assert calls[0].kwargs["text"] == "⚠️ دسترسی ندارید."


def test_broadcast_status_hidden_from_regular_users(env):
    _run_command("start", _update(222, "/start"), env.ctx)
    assert "/broadcast_status" not in env.ctx.bot.send_message.await_args.kwargs["text"]
    _run_command("start", _update(111, "/start"), env.ctx)
    assert "/broadcast_status" in env.ctx.bot.send_message.await_args.kwargs["text"]


def test_broadcast_status_without_recipients(env):
    env.mp.setattr(commands, "recipients", lambda: [])
    _run_command("broadcast_status", _update(111, "/broadcast_status"), env.ctx)
    calls = env.ctx.bot.send_message.await_args_list
    assert len(calls) == 1  # فقط پیام خطا به ادمین
    assert calls[0].kwargs["chat_id"] == 111
    assert "گیرنده" in calls[0].kwargs["text"]