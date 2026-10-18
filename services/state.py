"""وضعیت ربات: بازی‌های منتظر نتیجه (watched) و نتیجه‌های ارسال‌شده (result_sent).

این داده‌ها در barca_data.db نگه داشته می‌شوند. این ماژول فقط یک رابط ساده
(get و save) دارد و خودش به SQLite دست نمی‌زند؛ کار را storage/sqlite.py می‌کند.
زمان آخرین پیام هر کاربر هم از همان دیتابیس (usage_log) خوانده می‌شود.
"""
from storage import sqlite as db

_state = None


def get() -> dict:
    """داده‌ی وضعیت را یک‌بار از دیتابیس می‌خواند و در حافظه نگه می‌دارد."""
    global _state
    if _state is None:
        _state = db.load_state()
    return _state


def save() -> None:
    """وضعیت فعلی را در دیتابیس ذخیره می‌کند."""
    db.save_state(get())