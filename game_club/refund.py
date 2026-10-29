"""برگرداندن امتیازهای قدیمی AsoTas (پول واقعی) به کیف پول عبور، یک بار بعد از آمدن سکه.

    python -m game_club.refund              فقط پیش نمایش: چند نفر، چند امتیاز، چند تومان
    python -m game_club.refund --apply      برگرداندن واقعی (هر امتیاز --rate تومان، پیش فرض ۵۰۰)

با آمدن سکه، موجودی امتیاز هر بازیکن یک بار به legacy_points رفت (db.py) و میزهای امتیازی قدیمی هم
جایزه و برگشت ورودی شان را همان جا می ریزند. این ابزار:
  ۱. صف و میزهای امتیازی قدیمی را که هنوز شروع نشده اند می بندد (ورودی به legacy_points برمی گردد)؛
  ۲. اگر میز امتیازی قدیمی هنوز در جریان است، کاری نمی کند و می گوید چند دقیقه بعد دوباره اجرا شود؛
  ۳. برگشت هایی که دفعهٔ قبل وسط کار قطع شده اند را تمام می کند؛
  ۴. legacy_points هر بازیکن را با نرخ --rate تومان به کیف پول عبور می ریزد (هر بازیکن یک ردیف obour در دفتر).
دوباره اجرا کردن بی خطر است: کسی که legacy_points ندارد کاری ندارد و واریز عبور idem دارد.
بازیکنی که حساب عبور ندارد (یا مسدود است) سر جایش می ماند و فهرستش چاپ می شود.
"""
from __future__ import annotations

import argparse
import asyncio
import json

RATE = 500


async def run(apply: bool, rate: int) -> int:
    from app.config import config
    from app.db import Database

    from . import bridge, service
    from .config import gc
    from .db import GCDatabase

    gdb = GCDatabase(gc.db_path)
    odb = Database(config.db_path)
    await gdb.connect()
    await odb.connect()
    try:
        playing = await gdb.all("SELECT id FROM matches WHERE status = 'playing' AND json_extract(cfg, '$.mode') = 'stake'")
        lobbies = await gdb.all("SELECT id FROM matches WHERE status = 'lobby' AND json_extract(cfg, '$.mode') = 'stake'")
        queued = [r for r in await gdb.all("SELECT tg_id, cfg FROM queue WHERE claimed IS NULL")
                  if json.loads(r["cfg"]).get("mode") == "stake"]
        rows = await gdb.all("SELECT tg_id, legacy_points FROM players WHERE legacy_points > 0 ORDER BY legacy_points DESC")
        total = sum(r["legacy_points"] for r in rows)
        print(f"نرخ: هر امتیاز {rate:,} تومان")
        print(f"بازیکن با امتیاز قدیمی: {len(rows)} نفر · {total:,} امتیاز · {total * rate:,} تومان")
        print(f"میز امتیازی قدیمی: {len(playing)} در جریان · {len(lobbies)} منتظر بازیکن · {len(queued)} نفر در صف")
        for r in rows[:15]:
            print(f"  {r['tg_id']}: {r['legacy_points']:,} امتیاز ← {r['legacy_points'] * rate:,} تومان")
        if not apply:
            print("فقط پیش نمایش بود؛ برای برگرداندن واقعی همین را با --apply اجرا کن")
            return 0
        if playing:
            print("هنوز میز امتیازی قدیمی در جریان است؛ چند دقیقه بعد که تمام شد دوباره اجرا کن (ورودی ها به legacy_points برمی گردند)")
            return 2
        for m in lobbies:
            await service.admin_close(gdb, m["id"])
        for r in queued:
            await service.queue_leave(gdb, r["tg_id"])
        fixed = await bridge.finish_pending(gdb, odb)
        if fixed:
            print(f"{fixed} برگشت نیمه کارهٔ قبلی تمام شد")
        rows = await gdb.all("SELECT tg_id FROM players WHERE legacy_points > 0")
        paid, toman, missing = 0, 0, []
        for r in rows:
            got = await bridge.refund_legacy(gdb, odb, r["tg_id"], rate)
            if got is None:
                missing.append(r["tg_id"])
            elif got:
                paid, toman = paid + 1, toman + got
        print(f"برگشت به کیف عبور: {paid} نفر · {toman:,} تومان")
        if missing:
            print(f"{len(missing)} نفر حساب عبور ندارند (یا مسدودند) و امتیازشان ماند: {', '.join(map(str, missing[:50]))}")
        return 0
    finally:
        await gdb.close()
        await odb.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="برگرداندن امتیازهای قدیمی AsoTas به کیف پول عبور")
    ap.add_argument("--apply", action="store_true", help="برگرداندن واقعی (بدونش فقط پیش نمایش)")
    ap.add_argument("--rate", type=int, default=RATE, help="هر امتیاز چند تومان (پیش فرض ۵۰۰)")
    a = ap.parse_args()
    if a.rate <= 0:
        ap.error("--rate باید مثبت باشد")
    raise SystemExit(asyncio.run(run(a.apply, a.rate)))


if __name__ == "__main__":
    main()
