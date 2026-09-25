"""درج پلن های سند (بخش ۳) + تنظیمات اولیه.

استفاده:  python seed_plans.py
نکته: نیازی به User Template نیست. ربات سرویس ها را مستقیم با
حجم و مدت خود پلن روی پنل می سازد. فقط PANEL_GROUP_ID لازم است.
"""
from __future__ import annotations

import asyncio
import sys

# سازگاری با کنسول های غیر UTF-8 (ویندوز)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from app.config import config
from app.db import Database

# دسته بندی از روی duration_days انجام می شود:
#   ۱ تا ۳ روز  -> روزانه
#   ۴ تا ۱۴ روز -> هفتگی
#   ۱۵ روز بالا -> ماهانه
#
# اصل قیمت گذاری کوتاه مدت: حجم را سخاوتمندانه بده ولی قیمت را زیر
# حداقل معقول نیاور. هزینه واقعی تو حجم است نه مدت، و کاربر در یک روز
# نمی تواند ۵ گیگ مصرف کند. حداقل قیمت ۱۵ هزار تا سود هر تراکنش
# ارزش وقت پشتیبانی را داشته باشد.
PLANS = [
    # (title, data_gb, duration_days, price, badge)
    # ---------- روزانه ----------
    ("رهگذر", 5, 1, 19_000, None),
    ("گذر سه روزه", 10, 3, 35_000, None),
    # ---------- هفتگی ----------
    ("گذرگاه", 10, 7, 39_000, None),
    ("شتاب", 20, 7, 69_000, "best"),
    # ---------- ماهانه ----------
    ("آغاز", 5, 30, 25_000, None),
    ("یاور", 10, 30, 45_000, None),
    ("رهنورد", 20, 30, 79_000, "best"),     # برچسب پرفروش ترین
    ("پیشرو", 30, 30, 99_000, None),
    ("جهان نورد", 60, 30, 179_000, None),
    ("بی کران", 100, 30, 279_000, None),
]


async def main() -> None:
    db = Database(config.db_path)
    await db.connect()

    # کلید تشخیص «همین پلن» زوج (حجم، مدت) است نه فقط حجم.
    # قبلا فقط حجم بود و چون ۱۰ گیگ هم در روزانه هست هم هفتگی هم ماهانه،
    # پلن دوم به جای اینکه ساخته شود، پلن اول را بازنویسی می کرد.
    existing = {(p["data_gb"], p["duration_days"]): p for p in await db.all_plans()}

    # دسته هر پلن همان جا تعیین می شود. اگر category_id خالی بماند، پلن
    # در فروشگاه دیده نمی شود (فروشگاه بر اساس دسته چیده شده است).
    cats = {c["title"]: c["id"] for c in await db.categories()}

    def category_for(days: int) -> int | None:
        if days <= 3:
            return cats.get("روزانه")
        if days <= 14:
            return cats.get("هفتگی")
        return cats.get("ماهانه")

    for title, gb, days, price, badge in PLANS:
        cid = category_for(days)
        found = existing.get((gb, days))
        if found:
            await db.update_plan(
                found["id"], title=title, price=price, badge=badge,
                category_id=found["category_id"] or cid,
            )
            print(f"updated: {title} ({gb} گیگ / {days} روز)")
        else:
            await db.execute(
                """INSERT INTO plans(title, data_gb, duration_days, price, badge, is_active, category_id)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (title, gb, days, price, badge, cid),
            )
            print(f"inserted: {title} ({gb} گیگ / {days} روز)")

    missing = [p["title"] for p in await db.all_plans() if not p["category_id"]]
    if missing:
        print("\nهشدار: این پلن ها دسته ندارند و در فروشگاه دیده نمی شوند:")
        print("  " + "، ".join(missing))
        print("  از پنل ادمین -> دسته بندی، دسته شان را انتخاب کن.")

    print("\nپلن ها آماده شدند. مطمئن شو PANEL_GROUP_ID در فایل env تنظیم شده باشد.")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
