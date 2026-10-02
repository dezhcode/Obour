"""بررسی نرخ های tgju.org روی همین سرور.

    python check_tgju.py

ajax.json را از tgju می گیرد و نشان می دهد ربات چه نرخی برداشت می کند:
دلار، تتر و تون به تومان، و کلید دقیق هرکدام در فایل tgju. همه کلیدهای
مربوط به دلار، تتر و تون هم با قیمت خامشان چاپ می شوند تا اگر tgju نام
کلیدی را عوض کرد، بشود درست را در تنظیم tgju_key_usd / tgju_key_usdt /
tgju_key_ton گذاشت. خروجی کامل در tgju_dump.json کنار همین فایل ذخیره
می شود. فقط می خواند؛ چیزی در دیتابیس عوض نمی شود.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


async def main() -> None:
    from app.services import market

    try:
        doc = await market._download()
    except Exception as exc:  # noqa: BLE001
        print(f"tgju خوانده نشد: {exc}")
        print("اگر سرور خارج از ایران است ممکن است tgju آن را ببندد؛ TON_PROXY در .env را امتحان کن.")
        sys.exit(1)
    cur = market.current(doc)
    q = market.parse(doc)
    print(f"tgju: {len(cur)} کلید خوانده شد\n")
    for k, t in (("usd", "دلار"), ("usdt", "تتر"), ("ton", "تون کوین")):
        v = q.get(k) or 0
        print(f"{t:<10} {v:>14,} تومان   کلید: {q['keys'].get(k, '— پیدا نشد')}")
    print("\nکلیدهای مرتبط (قیمت خام):")
    pat = re.compile(r"dollar|usd|tether|ton|open.?network", re.I)
    for k in sorted(cur):
        if pat.search(k):
            item = cur[k]
            p = item.get("p") if isinstance(item, dict) else item
            print(f"  {k:<40} {p}")
    with open(os.path.join(HERE, "tgju_dump.json"), "w", encoding="utf-8") as fh:
        json.dump({"parsed": q, "related": {k: cur[k] for k in cur if pat.search(k)}}, fh, ensure_ascii=False, indent=2)
    print("\nذخیره شد: tgju_dump.json")


if __name__ == "__main__":
    asyncio.run(main())
