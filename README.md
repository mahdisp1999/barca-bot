# ⚽ barca-bot — ربات یادآور بازی‌های بارسلونا

یه ربات تلگرام (Python) که:

- 📅 تقویم بازی‌های بارسلونا رو از فایل ICS می‌گیره،
- ⏰ قبل از هر بازی بهت **یادآوری** می‌فرسته،
- 📊 با `/status` آخرین نتیجه و بازی بعدی (با تاریخ شمسی) رو نشون می‌ده،
- 🗒️ همه‌ی تعامل‌ها (کی، چی زد، ربات چی جواب داد، کی رد شد) رو توی SQLite ثبت می‌کنه،
- 🔐 فقط به کاربران مجاز جواب می‌ده.

جزئیات طراحی: [`Architecture.md`](./Architecture.md) · توضیح تک‌تک فایل‌ها: [`project_structure.md`](./project_structure.md)

---

## 🧰 ۱. پیش‌نیازها

- Python 3.9 یا بالاتر
- یه **توکن ربات** از [@BotFather](https://t.me/BotFather)
- **آیدی عددی** تلگرام خودت (مثلاً از [@userinfobot](https://t.me/userinfobot)) برای نقش ادمین
- دسترسی به Bot API (اگه تلگرام توی شبکه‌ات فیلتره، از پروکسی‌ای مثل Cloudflare Worker استفاده کن و آدرسش رو توی `BOT_API_BASE_URL` بذار)

### 📦 وابستگی‌ها

```bash
python -m venv .venv
source .venv/bin/activate          # ویندوز: .venv\Scripts\activate
pip install "python-telegram-bot[job-queue]" requests urllib3 icalendar
```

> ⚠️ `[job-queue]` مهمه. بدون اون، یادآوری‌ها کار نمی‌کنن و ربات فقط warning «JobQueue غیرفعال است» می‌ده.
> دیتابیس فقط از `sqlite3` استاندارد پایتون استفاده می‌کنه؛ چیز اضافه‌ای لازم نیست.

---

## 🔧 ۲. تنظیمات (`.env`)

توی **ریشه‌ی پروژه** (کنار `db.py`؛ نه توی `bot/`) یه فایل `.env` بساز:

```env
TELEGRAM_BOT_TOKEN=123456:ABC-your-token
TELEGRAM_ADMIN_ID=111111111
ALLOWED_USERS=222222222,333333333

# اختیاری
BOT_API_BASE_URL=https://your-proxy.example.workers.dev/bot
REMINDER_MINUTES=5,10,15,30,60
DB_PATH=usage.db
```

| متغیر | الزامی؟ | توضیح |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | ✅ | توکن ربات |
| `TELEGRAM_ADMIN_ID` | ✅ | گیرنده‌ی هشدارها + تنها کسی که `/usage` می‌زنه |
| `ALLOWED_USERS` | توصیه می‌شه | آیدی‌های مجاز با کاما. ادمین خودکار مجازه |
| `BOT_API_BASE_URL` | ❌ | آدرس پروکسی Bot API |
| `REMINDER_MINUTES` | ❌ | چند دقیقه قبل از بازی یادآوری بره (پیش‌فرض `5,10,15,30,60`) |
| `DB_PATH` | ❌ | مسیر دیتابیس (نسبی = نسبت به پوشه‌ی پروژه) |

⚠️ **اگه `ALLOWED_USERS` و `TELEGRAM_ADMIN_ID` هر دو خالی باشن، همه‌ی دنیا می‌تونن از ربات استفاده کنن.** موقع شروع یه warning توی کنسول می‌بینی.

💡 متغیر محیط واقعی روی `.env` برتری داره (برای سرور/Docker خوبه).

---

## ▶️ ۳. اجرا

```bash
python bot/bot.py
```

از هر پوشه‌ای می‌تونی اجراش کنی؛ ایمپورت‌ها خودشون درست می‌شن و `PYTHONPATH` لازم نیست. (فقط با `python bot/bot.py`؛ `python -m bot.bot` کار نمی‌کنه.)

اگه همه‌چی درست باشه این رو می‌بینی: `ربات آماده است.`

چیزایی که موقع بالا اومدن خودکار اتفاق می‌افته:

- ساخت `usage.db` (توی ریشه) و جدول‌ها
- پاک‌سازی هشدارهای قدیمی‌تر از ۳۰ روز
- ست شدن منوی دستورها توی تلگرام
- شروع job هر ۱۰ دقیقه (اولین اجرا ۵ ثانیه بعد)
- اولین دانلود تقویم (اگه `barcelona.ics` نباشه)

### 🖥️ اجرای دائمی (سرور لینوکسی با systemd)

فایل `/etc/systemd/system/barca-bot.service`:

```ini
[Unit]
Description=Barca Telegram Bot
After=network-online.target

[Service]
WorkingDirectory=/path/to/project
ExecStart=/path/to/project/.venv/bin/python bot/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now barca-bot
journalctl -u barca-bot -f      # لاگ زنده
```

---

## 💬 ۴. دستورهای ربات

| دستور | کی؟ | چیکار می‌کنه |
| :--- | :--- | :--- |
| `/start` | مجازها | پیام خوش‌آمد + لیست دستورها + بازه‌های یادآوری |
| `/status` | مجازها | آخرین نتیجه + بازی امروز یا بازی بعدی (تاریخ میلادی/شمسی و زمان باقی‌مانده) |
| `/sync` | مجازها | دانلود دستی تقویم |
| `/usage` | **فقط ادمین** | خلاصه‌ی آمار استفاده |
| `/usage 20` | ادمین | ۲۰ رویداد آخر |
| `/usage user 123456` | ادمین | تاریخچه‌ی یه کاربر (۵۰ رویداد آخر) |

کاربر غیرمجاز فقط «⚠️ دسترسی ندارید.» می‌گیره و تلاشش ثبت می‌شه.

---

## 🔔 ۵. هشدارهای خودکار (فقط برای ادمین)

- **یادآوری قبل از بازی:** هر مقدار توی `REMINDER_MINUTES` (با تلورانس ±۵ دقیقه). هر هشدار برای هر بازی **فقط یک‌بار** می‌ره، حتی اگه ربات ری‌استارت بشه.
- **وضعیت خودکار:** وقتی کمتر از ۲۴ ساعت به بازی مونده و ۱۲ ساعت از آخرین پیام ربات به ادمین گذشته.
- **نتیجه‌ی بازی:** حدود ۶۰ دقیقه بعد از شروع بازی، تقویم دوباره دانلود می‌شه و آخرین نتیجه می‌ره. (توضیح محدودیتش توی بخش ۱۲ `Architecture.md`)
- تقویم هر ساعت یه‌بار خودکار به‌روز می‌شه؛ دستورها هرگز دانلود نمی‌کنن (فقط `/sync`).

---

## 📈 ۶. گزارش‌گیری از ترمینال (`report.py`)

فقط‌خواندنیه؛ حتی وقتی ربات داره می‌نویسه هم امنه. هیچ وابستگی‌ای هم نداره.

```bash
python report.py                    # خلاصه‌ی آماری
python report.py --days 7           # رویدادهای ۷ روز اخیر
python report.py --user 243649523   # تاریخچه‌ی یه کاربر
python report.py --kind denied      # فقط تلاش‌های غیرمجاز
python report.py --command status   # فقط یه دستور
python report.py --raw 50           # ۵۰ ردیف آخر
python report.py --csv out.csv      # خروجی CSV (با فیلترها قابل ترکیبه)
```

مقدارهای `--kind`: `command` · `alert` · `status` · `system` · `unknown` · `denied`

دیتابیس رو جای دیگه نگه می‌داری؟ `DB_PATH=/path/to/usage.db python report.py`

### 🔍 کوئری مستقیم (اختیاری)

```bash
sqlite3 usage.db "SELECT ts, user_id, command, delivery FROM usage_log ORDER BY id DESC LIMIT 10;"
```

---

## 🗂️ ۷. ساختار پروژه

```
.
├── bot/                 ← پکیج فعال (bot.py = نقطه‌ی ورود، cmd_*.py، jobs.py، ics.py، ...)
├── db.py                ← لایه‌ی داده (SQLite)
├── report.py            ← گزارش از ترمینال
├── .env                 ← تنظیمات (توی Git نذار!)
├── usage.db*            ← تولید خودکار
├── bot_state.json       ← تولید خودکار
└── barcelona.ics        ← تقویم کش‌شده (تولید خودکار)
```

همه‌ی فایل‌های بالا (غیر از `bot/`) توی **ریشه‌ی پروژه** هستن. توضیح تک‌تک فایل‌ها: [`project_structure.md`](./project_structure.md). `bot.py` تک‌فایلیِ قدیمی و `old_bot/` جزو پروژه‌ی فعال نیستن؛ اگه داری‌شون پاکشون کن.

برای تست محلی بدون اینترنت، `barcelona_sample.ics` یه نمونه‌ی آماده‌ست.

---

## 🛡️ ۸. امنیت و حریم خصوصی

- `.gitignore` باید حتماً این‌ها رو داشته باشه (فایل آماده‌ش توی پروژه هست):
  ```
  .env
  usage.db*
  bot_state.json
  barcelona.ics
  __pycache__/
  ```
- `usage.db` متن پیام‌های کاربرها و آیدی/نام‌شون رو نگه می‌داره؛ مثل داده‌ی شخصی باهاش رفتار کن.
- `/usage` عمداً فقط برای ادمینه چون آیدی و نام بقیه رو نشون می‌ده.
- دانلود تقویم با `verify=False` انجام می‌شه (میزبان لازم داره)؛ چیز حساسی توش نیست ولی بدون تأیید SSL ـه.

---

## 🩺 ۹. عیب‌یابی

| مشکل | علت/راه‌حل |
| :--- | :--- |
| `توکن تنظیم نشده است.` | `TELEGRAM_BOT_TOKEN` توی `.env` نیست یا هنوز `your_bot_token_here` ـه |
| `ModuleNotFoundError: db` / `config` | ربات رو با `python -m bot.bot` یا از یه نسخه‌ی کپی‌شده‌ی ناقص اجرا کردی. دستور درست: `python bot/bot.py` و `db.py` باید کنار پوشه‌ی `bot/` باشه |
| هشدار نمی‌ره | `[job-queue]` نصب نیست، `TELEGRAM_ADMIN_ID` صفره، یا هنوز زمانش نرسیده (پنجره ±۵ دقیقه) |
| ربات جواب نمی‌ده | آیدی‌ت توی `ALLOWED_USERS` نیست، یا Bot API/پروکسی در دسترس نیست |
| `Can't parse entities` توی لاگ | اسم حریف/ورزشگاه کاراکتر `_` یا `*` داره (محدودیت Markdown قدیمی؛ `Architecture.md` بخش ۱۲) |
| `/status` می‌گه بازی‌ای نیست | تقویم قدیمیه یا خالیه → `/sync` بزن |
| `database is locked` | دو نمونه از ربات هم‌زمان در حال اجرا هستن؛ فقط یکی رو نگه دار |
| می‌خوام هشدار یه بازی دوباره بره | ردیفش رو از جدول `match_alerts` پاک کن: `sqlite3 usage.db "DELETE FROM match_alerts WHERE match_uid='...';"` |

---

## 🧾 ۱۰. خلاصه

- `.env` رو پر کن → `python bot/bot.py` → توی تلگرام `/start` بزن.
- هشدارها خودکار می‌رن و تکراری نمی‌شن.
- آمار: `/usage` توی تلگرام یا `python report.py` توی ترمینال.
- طراحی و تصمیم‌ها: `Architecture.md`.
