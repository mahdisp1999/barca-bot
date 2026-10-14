# ساختار فایل‌های پروژه

```txt
.
├── .env                  # 🔑 تنظیمات و secretها (دستی ساخته می‌شه؛ توی Git نمی‌ره)
├── .gitignore            # .env، usage.db*، bot_state.json، barcelona.ics، __pycache__
├── Architecture.md       # معماری، مدل داده، جریان‌ها، تصمیم‌ها
├── README.md             # نصب، پیکربندی، اجرا، عیب‌یابی
├── project_structure.md  # همین فایل
├── barcelona_sample.ics  # تقویم نمونه برای تست آفلاین
├── db.py                 # ⭐ لایه‌ی داده (SQLite): اسکیما، لاگ، هشدارها، کوئری‌های گزارش
├── report.py             # گزارش فقط‌خواندنی از ترمینال (جدا از ربات، بدون import از پروژه)
├── usage.db*             # 🗄️ تولید خودکار (usage_log، users، match_alerts + فایل‌های WAL)
├── bot_state.json        # 💾 تولید خودکار (وضعیت موقت ربات)
├── barcelona.ics         # 📅 تولید خودکار (کش تقویم دانلودشده)
└── bot/                  # 📦 پکیج فعال ربات
    ├── __init__.py       # خالی؛ فقط علامت پکیج
    ├── bot.py            # 🚀 نقطه‌ی ورود: فقط سیم‌کشی (Application، هندلرها، JobQueue)
    ├── config.py         # .env + ثابت‌ها (TOKEN، ADMIN_ID، ALLOWED_IDS، REMINDER_MINUTES، ...)
    ├── access.py         # is_allowed / authorize / user_fields + لاگ تلاش‌های غیرمجاز
    ├── audit.py          # log_inbound (group 1) و on_error
    ├── messaging.py      # send_tracked / reply_tracked: تنها مسیر ارسال + لاگ
    ├── cmd_start.py      # /start
    ├── cmd_status.py     # /status
    ├── cmd_sync.py       # /sync
    ├── cmd_usage.py      # /usage (فقط ادمین)
    ├── jobs.py           # check_matches هر ۶۰۰ ثانیه: یادآوری، نتیجه‌ی بازی، وضعیت خودکار
    ├── ics.py            # دانلود، پارس با کش و پیدا کردن بازی‌ها
    ├── fmt.py            # اعداد فارسی، تاریخ شمسی، زمان باقی‌مانده، نام حریف
    └── state_store.py    # bot_state.json یک‌بار-بارگذاری و مشترک در حافظه
```

## 📌 نکته‌ها

1. **اجرا:** `python bot/bot.py` از هر پوشه‌ای (فقط همین؛ `python -m bot.bot` کار نمی‌کنه).
   - ایمپورت‌ها فلت‌اند (`import db`، `from config import ...`). وقتی اسکریپت اجرا می‌شه، پوشه‌ی `bot/` خودکار توی مسیر ایمپورت هست و اولِ `bot/bot.py` ریشه‌ی پروژه (برای `db.py`) اضافه می‌شه. **نیازی به `PYTHONPATH` نیست.**
2. **ریشه‌ی پروژه:** `BASE_DIR` توی `config.py` پوشه‌ی بالای `bot/` رو نشون می‌ده؛ پس `.env`، `bot_state.json`، `barcelona.ics` و `usage.db` (از طریق `db.py`) همه کنار هم توی ریشه‌ان.
3. **جهت وابستگی‌ها:** `bot.py → cmd_* → (access, messaging, ics, fmt) → (db, state_store, config)`. `jobs.py` همین الگو رو داره و هندلرهای دستور هرگز `jobs` رو import نمی‌کنن.
4. **فایل‌های تولیدشده** (`usage.db*`، `bot_state.json`، `barcelona.ics`) نباید commit بشن.
5. **قدیمی‌ها:** اگه هنوز `bot.py` تک‌فایلیِ ریشه یا پوشه‌ی `old_bot/` رو داری، جزو پروژه‌ی فعال نیستن. بهتره پاکشون کنی (یا بیرون از ریشه نگه داری) تا با `bot/bot.py` قاطی نشن.
6. **گزارش‌گیری:** `/usage` توی تلگرام برای خلاصه‌ی سریع، `report.py` توی ترمینال برای فیلتر و CSV.
