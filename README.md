# ⚽ barca-bot — ربات یادآور بازی‌های بارسلونا

ربات تلگرام (Python) که:

- 📅 بازی‌های بارسلونا را از **SportsAPI Pro** می‌گیرد،
- ⏰ قبل از هر بازی به ادمین **یادآوری** می‌فرستد،
- 📊 بعد از پایان بازی **نتیجه** را می‌فرستد،
- 🗓️ با `/status` آخرین نتیجه و بازی بعدی را (با تاریخ شمسی و میلادی) نشان می‌دهد،
- 🗒️ همه‌ی تعامل‌ها را در SQLite ثبت می‌کند،
- 🔐 فقط به کاربران مجاز جواب می‌دهد.

طراحی و تصمیم‌ها: [`Architecture.md`](./Architecture.md)

---

## 🚀 راه‌اندازی سریع

```bash
python -m venv .venv
source .venv/bin/activate            # ویندوز: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # و مقدارها را پر کن
python main.py
```

- ✅ بدون `PYTHONPATH`، از هر جایی که بخواهی اجرا کن (مسیر فایل‌ها از روی محل `settings.py` پیدا می‌شود).
- ✅ `.env`، `usage.db` و `bot_state.json` همه در **ریشه‌ی پروژه** هستند.
- ✅ با اجرای موفق این پیام را می‌بینی: `ربات آماده است.`

### 📦 پیش‌نیازها

- Python 3.9 یا بالاتر
- توکن ربات از [@BotFather](https://t.me/BotFather) و آیدی عددی خودت (مثلاً از [@userinfobot](https://t.me/userinfobot))
- کلید API از SportsAPI Pro
- اگر تلگرام فیلتر است، آدرس پروکسی Bot API را در `BOT_API_BASE_URL` بگذار

---

## 🔧 تنظیمات (`.env`)

| متغیر | الزامی؟ | توضیح |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | ✅ | توکن ربات |
| `TELEGRAM_ADMIN_ID` | ✅ | گیرنده‌ی هشدارها و تنها کاربر `/usage`. اگر خالی باشد هشدار نمی‌رود و `/usage` برای همه بسته است |
| `SPORTS_API_KEY` | ✅ | کلید SportsAPI Pro |
| `ALLOWED_USERS` | توصیه می‌شود | آیدی‌های مجاز با کاما. ادمین خودکار مجاز است |
| `TEAM_ID` | ❌ | پیش‌فرض `2817`. ⚠️ با پاسخ واقعی API تأیید کن |
| `LOCAL_TZ` | ❌ | پیش‌فرض `Asia/Tehran` |
| `REMINDER_MINUTES` | ❌ | پیش‌فرض `5,10,15,30,60` |
| `BOT_API_BASE_URL` | ❌ | آدرس پروکسی Bot API |
| `DB_PATH` / `STATE_FILE` | ❌ | مسیر نسبی یعنی نسبت به ریشه‌ی پروژه |
| `LOG_RETENTION_DAYS` | ❌ | پیش‌فرض `180`؛ لاگ قدیمی‌تر خودکار پاک می‌شود |

⚠️ اگر `ALLOWED_USERS` و `TELEGRAM_ADMIN_ID` هر دو خالی باشند، همه می‌توانند از ربات استفاده کنند.

---

## 💬 دستورها

| دستور | چه کسی | کار |
| :--- | :--- | :--- |
| `/start` | مجازها | پیام خوش‌آمد و لیست دستورها |
| `/status` | مجازها | آخرین نتیجه + بازی بعدی |
| `/sync` | مجازها | بازخوانی از API (حداکثر هر ۳۰ ثانیه یک‌بار واقعاً به API می‌رود) |
| `/usage` | **فقط ادمین** | آمار کلی |
| `/usage 20` | ادمین | ۲۰ رویداد آخر (حداکثر ۱۰۰) |
| `/usage user 123456` | ادمین | تاریخچه‌ی یک کاربر |

### نمونه‌ی خروجی `/status`

```
⚽️ نتیجه آخرین بازی:
✅ بارسلونا ۷ - ۲ راسینگ سانتاندر (شنبه ۴ مهر ۱۴۰۵ - ۴ روز پیش)
🏟️ این بازی در ورزشگاه خانگی Spotify Camp Nou انجام شد و بارسا با یک پیروزی پرگل حریف را شکست داد.
🏆 رقابت: لالیگا

🔜 بازی بعدی:
🏆 رقابت: لالیگا
⚔️ حریف: سویا (Sevilla) - بازی در خانه حریف (Away)
🏟️ ورزشگاه: Ramón Sánchez-Pizjuán در شهر Sevilla، Spain
📆 تاریخ: شنبه ۲۸ شهریور ۱۴۰۵، (۱۹ سپتامبر ۲۰۲۶)
⏰ ساعت: حدود ساعت ۲۲:۳۰ به وقت ایران (۱۹:۰۰ به وقت جهانی UTC)
⏳ ۱ روز و ۱۹ ساعت دیگر
```

متن نتیجه (پیروزی، تساوی، شکست، پرگل و...) بر اساس نتیجه‌ی بازی ساخته می‌شود.

---

## 🔔 هشدارهای خودکار (فقط ادمین)

- **یادآوری:** هر دقیقه از روی کش چک می‌شود (بدون مصرف سهمیه‌ی API). هر یادآوری برای هر بازی فقط یک بار می‌رود، حتی بعد از ری‌استارت. اگر بازی عقب بیفتد، یادآوری‌های جدید برای زمان جدید می‌رود.
- **نتیجه:** ۹۰ دقیقه بعد از شروع بازی، هر ۱۰ دقیقه چک می‌شود و فقط وقتی API بگوید بازی `finished` است نتیجه می‌رود. بعد از ۶ ساعت بی‌نتیجه، بازی رها می‌شود.
- **وضعیت خودکار:** اگر کمتر از ۲۴ ساعت به بازی بعدی مانده و ۱۲ ساعت است پیامی به ادمین نرفته.

---

## 🗂️ ساختار پروژه

```
barca-bot/
├── main.py              ← نقطه ورود: python main.py
├── app.py               ← ساخت Application، ثبت هندلرها و job ها
├── settings.py          ← .env، مسیرها، ثابت‌ها (به هیچ ماژول دیگری وابسته نیست)
├── commands.py          ← همه‌ی دستورها + جدول COMMANDS
├── jobs.py              ← یادآوری، نتیجه، وضعیت خودکار
├── audit.py             ← لاگ ورودی و خطای سراسری
├── report.py            ← گزارش ترمینالی (فقط خواندن)
├── services/            ← منطق کسب‌وکار (بدون تلگرام)
│   ├── matches.py       ← بازی بعدی، یادآوری، نتیجه
│   ├── tracking.py      ← بازی‌هایی که منتظر نتیجه‌اند
│   ├── state.py         ← bot_state.json
│   └── reports.py       ← متن گزارش استفاده
├── providers/
│   └── sportsapipro.py  ← API + کش
├── storage/
│   └── sqlite.py        ← usage.db
├── formatting/
│   ├── fmt.py           ← ارقام فارسی، تاریخ شمسی، زمان باقی‌مانده
│   ├── names.py         ← نام فارسی تیم‌ها و رقابت‌ها
│   └── status.py        ← قالب پیام‌ها
├── bot_io/              ← هر چیزی که به تلگرام وصل است
│   ├── access.py        ← کنترل دسترسی
│   └── messaging.py     ← تنها مسیر ارسال پیام
├── tests/
├── .env, usage.db, bot_state.json   ← ریشه (تولید/ساخته توسط تو)
└── requirements.txt, .env.example, .gitignore
```

### ➕ اضافه کردن یک دستور

۱. در `commands.py` یک تابع `async def cmd_x(update, context)` بنویس.
۲. یک خط به `COMMANDS` اضافه کن. منو، کنترل دسترسی و لاگ خودکار به‌روز می‌شوند.

### 🇮🇷 اضافه کردن نام فارسی تیم یا رقابت

در `formatting/names.py` به `TEAMS_FA` یا `_COMPETITIONS` یک خط اضافه کن. اگر نامی نباشد، همان نام انگلیسی نشان داده می‌شود و چیزی خراب نمی‌شود.

---

## 🧪 تست

```bash
pip install pytest
python -m pytest
```

شامل تست تبدیل تاریخ شمسی، قالب پیام‌ها، پنجره‌ی یادآوری، پارس داده‌ی API، دیتابیس و مهاجرت آن، جریان کامل یادآوری و نتیجه، و رعایت قانون وابستگی لایه‌ها.

---

## 📈 گزارش از ترمینال

```bash
python report.py                    # خلاصه
python report.py --days 7           # رویدادهای ۷ روز اخیر
python report.py --user 243649523   # تاریخچه‌ی یک کاربر
python report.py --kind denied      # تلاش‌های غیرمجاز
python report.py --csv out.csv      # خروجی CSV
```

---

## 🖥️ اجرای دائمی (systemd)

`/etc/systemd/system/barca-bot.service`:

```ini
[Unit]
Description=Barca Telegram Bot
After=network-online.target

[Service]
WorkingDirectory=/path/to/barca-bot
ExecStart=/path/to/barca-bot/.venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now barca-bot
journalctl -u barca-bot -f
```

---

## 🔄 مهاجرت از ساختار قبلی

```bash
git commit -am "before restructure"     # برگشت‌پذیر باشد
rm -rf old_bot bot ics.py bot.py project_structure.md barcelona.ics
# فایل‌های این پروژه را در ریشه کپی کن، بعد:
mv bot/.env . ; mv bot/bot_state.json .   # اگر داشتی (قبل از حذف پوشه‌ی bot)
pip install -r requirements.txt
python main.py
```

- `usage.db` همان‌جا که هست می‌ماند و خودکار مهاجرت می‌شود (جدول `match_alerts` ساخته‌ی دوباره می‌شود؛ بدترین حالت یک یادآوری تکراری است).
- کلیدهای قدیمی `bot_state.json` هنگام اولین بارگذاری پاک می‌شوند.
- `ICS` و `MATCH_SOURCE` حذف شده‌اند. اگر در `.env` داری، بی‌اثرند.

---

## 🩺 عیب‌یابی

| مشکل | علت / راه‌حل |
| :--- | :--- |
| `توکن تنظیم نشده است` | `TELEGRAM_BOT_TOKEN` را در `.env` (ریشه) بگذار |
| `JobQueue غیرفعال است` | `pip install "python-telegram-bot[job-queue]"` |
| `SPORTS_API_KEY تنظیم نشده است` | کلید را در `.env` بگذار |
| `TEAM_ID ... در هیچ‌کدام از دو تیم بازی نیست` | `TEAM_ID` اشتباه است؛ پاسخ API را چک کن |
| هشدار نمی‌رود | `TELEGRAM_ADMIN_ID` خالی است، یا زمانش نرسیده |
| `/status` اطلاعاتی نشان نمی‌دهد | `/sync` بزن و لاگ خطای API را ببین |
| `database is locked` | دو نمونه‌ی ربات هم‌زمان اجرا شده‌اند |
| می‌خواهی یادآوری دوباره برود | `sqlite3 usage.db "DELETE FROM match_alerts WHERE match_uid='...';"` |

چک سریع پاسخ API (برای تأیید `TEAM_ID`، رقابت و ورزشگاه):

```bash
curl -H "x-api-key: $SPORTS_API_KEY" https://api.sportsapipro.com/v2/football/teams/2817/events/next/0
```

---

## 🛡️ امنیت و حریم خصوصی

- `.env`، `usage.db*` و `bot_state.json` در `.gitignore` هستند. کلید API و توکن را هرگز در Git نگذار.
- `usage.db` متن پیام‌ها و نام و آیدی کاربران را دارد؛ مثل داده‌ی شخصی با آن رفتار کن. لاگ‌های قدیمی‌تر از `LOG_RETENTION_DAYS` خودکار پاک می‌شوند.
- لاگ‌های `httpx` خاموش شده‌اند، چون آدرس درخواست‌های تلگرام شامل توکن ربات است.
