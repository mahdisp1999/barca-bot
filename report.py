#!/usr/bin/env python3
"""گزارش‌گیری فقط‌خواندنی از usage.db — بدون هیچ وابستگی اضافی.

نمونه:
    python report.py                     # خلاصه‌ی آماری
    python report.py --days 7            # رویدادهای ۷ روز اخیر
    python report.py --user 243649523    # تاریخچه‌ی یک کاربر
    python report.py --kind denied       # فقط تلاش‌های غیرمجاز
    python report.py --command status    # فیلتر بر اساس دستور
    python report.py --raw 50            # ۵۰ ردیف خام آخر
    python report.py --csv out.csv       # خروجی CSV
"""

import argparse
import csv
import os
import sqlite3
import sys
from datetime import datetime, timedelta

DB_PATH = os.getenv(
    "DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage.db")
)


def connect_ro() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fmt_event(r) -> str:
    who = r["username"] or r["first_name"] or "?"
    return (
        f"{r['ts']} | {who} ({r['user_id']}) | {r['direction']:>8} | "
        f"{r['kind']:<7} | {r['command'] or '-':<12} | {r['delivery'] or '-'}"
    )


def print_summary(conn) -> None:
    total = conn.execute("SELECT COUNT(*) FROM usage_log").fetchone()[0]
    users = conn.execute("SELECT COUNT(DISTINCT user_id) FROM usage_log").fetchone()[0]
    cutoff24 = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    cutoff7 = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    n24 = conn.execute(
        "SELECT COUNT(*) FROM usage_log WHERE ts >= ?", (cutoff24,)
    ).fetchone()[0]
    n7 = conn.execute(
        "SELECT COUNT(*) FROM usage_log WHERE ts >= ?", (cutoff7,)
    ).fetchone()[0]

    print("=== خلاصه‌ی استفاده از ربات ===")
    print(f"کل رویدادها : {total}")
    print(f"کاربران یکتا: {users}")
    print(f"۲۴ ساعت اخیر: {n24}")
    print(f"۷ روز اخیر  : {n7}")

    print("\n--- بر اساس نوع ---")
    for r in conn.execute(
        "SELECT kind, COUNT(*) n FROM usage_log GROUP BY kind ORDER BY n DESC"
    ):
        print(f"  {r['kind']:<8}: {r['n']}")

    print("\n--- بر اساس دستور ---")
    for r in conn.execute(
        "SELECT COALESCE(command,'—') c, COUNT(*) n FROM usage_log "
        "GROUP BY command ORDER BY n DESC"
    ):
        print(f"  {r['c']:<14}: {r['n']}")

    print("\n--- کاربران ---")
    for r in conn.execute(
        "SELECT * FROM users ORDER BY total_events DESC, last_seen DESC"
    ):
        who = r["username"] or r["first_name"] or "?"
        denied = f" | رد: {r['denied_count']}" if r["denied_count"] else ""
        print(
            f"  {who} ({r['user_id']}) — {r['total_events']} رویداد{denied}\n"
            f"      اولین: {r['first_seen']}  آخرین: {r['last_seen']}  "
            f"آخرین دستور: {r['last_command'] or '-'}"
        )


def run_query(conn, args) -> None:
    sql = "SELECT * FROM usage_log WHERE 1=1"
    params = []
    if args.days:
        cutoff = (datetime.now() - timedelta(days=args.days)).isoformat(
            timespec="seconds"
        )
        sql += " AND ts >= ?"
        params.append(cutoff)
    if args.user:
        sql += " AND user_id = ?"
        params.append(args.user)
    if args.command:
        sql += " AND command = ?"
        params.append(args.command)
    if args.kind:
        sql += " AND kind = ?"
        params.append(args.kind)
    sql += " ORDER BY id DESC"
    if args.raw:
        sql += " LIMIT ?"
        params.append(args.raw)

    rows = conn.execute(sql, params).fetchall()
    if not rows:
        print("هیچ رویدادی یافت نشد.")
        return

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(rows[0].keys())
            writer.writerows([tuple(r) for r in rows])
        print(f"✅ {len(rows)} ردیف در {args.csv} ذخیره شد.")
    else:
        for r in rows:
            print(fmt_event(r))
            if r["text_sent"]:
                preview = r["text_sent"].replace("\n", " ⏎ ")
                if len(preview) > 160:
                    preview = preview[:160] + "…"
                print(f"      └─ {preview}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="گزارش‌گیری فقط‌خواندنی از usage.db"
    )
    parser.add_argument("--days", type=int, help="فقط رویدادهای N روز اخیر")
    parser.add_argument("--user", type=int, help="فیلتر بر اساس user_id")
    parser.add_argument("--command", help="فیلتر بر اساس نام دستور")
    parser.add_argument(
        "--kind", help="فیلتر بر اساس نوع (command/alert/status/system/unknown/denied)"
    )
    parser.add_argument("--raw", type=int, help="تعداد ردیف خام آخر")
    parser.add_argument("--csv", metavar="PATH", help="ذخیره‌ی خروجی در CSV")
    args = parser.parse_args()

    if not os.path.isfile(DB_PATH):
        sys.exit(f"❌ دیتابیس یافت نشد: {DB_PATH}")

    conn = connect_ro()
    try:
        if any([args.days, args.user, args.command, args.kind, args.raw, args.csv]):
            run_query(conn, args)
        else:
            print_summary(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
