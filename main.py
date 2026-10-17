"""Entry point:  python main.py"""
import logging
import sys

import settings
from storage import sqlite as db

logger = logging.getLogger("barca-bot")


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
    )
    # httpx logs every request URL at INFO, and the Telegram URL contains the bot token.
    for noisy in ("httpx", "httpcore", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if not settings.TOKEN or settings.TOKEN == "your_bot_token_here":
        logger.error("توکن تنظیم نشده است (TELEGRAM_BOT_TOKEN در .env).")
        sys.exit(1)
    if not settings.ADMIN_ID:
        logger.warning("TELEGRAM_ADMIN_ID تنظیم نشده — /usage بسته است.")
    if not settings.ALLOWED_IDS:
        logger.warning("ALLOWED_USERS و TELEGRAM_ADMIN_ID خالی‌اند — پیام خودکاری ارسال نمی‌شود.")
    if not settings.SPORTS_API_KEY:
        logger.warning("SPORTS_API_KEY تنظیم نشده — داده‌ی بازی‌ها دریافت نمی‌شود.")

    db.init_db()
    removed = db.cleanup_old_data(settings.ALERT_RETENTION_DAYS, settings.LOG_RETENTION_DAYS)
    logger.info("پاک‌سازی داده‌ی قدیمی: %s", removed)

    from app import build_application  # imported late so config errors show first

    application = build_application()
    logger.info("ربات آماده است.")
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()