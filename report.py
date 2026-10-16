#!/usr/bin/env python3
"""Read-only usage report from usage.db (terminal).

    python report.py                     # summary
    python report.py --days 7            # events of the last 7 days
    python report.py --user 243649523    # one user's history
    python report.py --kind denied       # denied attempts only
    python report.py --command status    # one command
    python report.py --raw 50            # last 50 raw rows
    python report.py --csv out.csv       # CSV export (combines with the filters)

The database path comes from settings (DB_PATH in .env, default usage.db in the project root).
"""
import argparse
import csv
import sys

import settings
from services import reports
from storage import sqlite as db


def main() -> None:
    p = argparse.ArgumentParser(description="گزارش‌گیری فقط‌خواندنی از usage.db")
    p.add_argument("--days", type=int, help="فقط رویدادهای N روز اخیر")
    p.add_argument("--user", type=int, help="فیلتر بر اساس user_id")
    p.add_argument("--command", help="فیلتر بر اساس نام دستور")
    p.add_argument("--kind", help="command/alert/status/system/unknown/denied")
    p.add_argument("--raw", type=int, help="تعداد ردیف خام آخر")
    p.add_argument("--csv", metavar="PATH", help="ذخیره‌ی خروجی در CSV")
    args = p.parse_args()

    if not settings.DB_PATH.is_file():
        sys.exit(f"❌ دیتابیس یافت نشد: {settings.DB_PATH}")

    if not any([args.days, args.user, args.command, args.kind, args.raw, args.csv]):
        print(reports.build_summary())
        return

    rows = db.query_events(
        days=args.days, user_id=args.user, command=args.command,
        kind=args.kind, limit=args.raw,
    )
    if not rows:
        print("هیچ رویدادی یافت نشد.")
        return

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(rows[0].keys())
            w.writerows([tuple(r) for r in rows])
        print(f"✅ {len(rows)} ردیف در {args.csv} ذخیره شد.")
        return

    for r in rows:
        print(reports.format_event(r))
        if r["text_sent"]:
            preview = r["text_sent"].replace("\n", " ⏎ ")
            print(f"      └─ {preview[:160]}{'…' if len(preview) > 160 else ''}")


if __name__ == "__main__":
    main()
