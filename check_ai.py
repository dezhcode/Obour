"""بررسی دستیار هوش مصنوعی روی همین سرور.

    python check_ai.py

نشان می دهد چرا بخش هوشمند در ربات و مینی اپ دیده می شود یا نه:
۱. آیا AI_API_KEY از فایل .env خوانده شده (خود کلید چاپ نمی شود)
۲. کدام بخش ها از پنل ادمین روشن اند
۳. یک درخواست واقعی به وب سرویس و زمان جوابش
فقط می خواند؛ چیزی در دیتابیس عوض نمی شود.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


async def main() -> None:
    from app import features
    from app.config import config
    from app.db import Database
    from app.services import assistant

    env = os.path.join(HERE, ".env")
    print(f"فایل .env: {'پیدا شد' if os.path.isfile(env) else 'پیدا نشد!'} ({env})")
    if os.path.isfile(env):
        with open(env, encoding="utf-8", errors="replace") as fh:
            lines = [ln.strip() for ln in fh if ln.strip().startswith("AI_API_KEY")]
        if not lines:
            print("  خط AI_API_KEY در .env نیست. این خط را اضافه کن:  AI_API_KEY=کلید")
        elif len(lines) > 1:
            print("  AI_API_KEY چند بار در .env آمده؛ فقط یکی نگه دار (آخری خالی است؟)")
    key = config.ai_api_key
    print(f"AI_API_KEY: {'تنظیم شده (' + str(len(key)) + ' کاراکتر)' if key else 'خالی — همه بخش های هوشمند پنهان اند'}")
    print(f"AI_BASE_URL: {config.ai_base_url}")

    db = Database(config.db_path)
    await db.connect()
    await features.load(db)
    print("\nبخش ها:")
    for k in ("ai_support", "ai_recommend", "ai_shop_help", "ai_names", "ai_report"):
        print(f"  {'🟢' if features.is_on(k) else '⚪️'} {k}  {features.FEATURES[k][0]}")
    await db.close()

    if not key:
        sys.exit(1)
    print("\nدرخواست آزمایشی به وب سرویس ...")
    t0 = time.monotonic()
    try:
        out = await assistant.ask("Reply with exactly: OK", timeout=60)
        print(f"🟢 جواب آمد ({time.monotonic() - t0:.1f} ثانیه): {out[:80]}")
        print("\nاگر مینی اپ هنوز چیزی نشان نمی دهد: ری استارت (touch tmp/restart.txt) و مینی اپ را کامل ببند و باز کن.")
    except assistant.AIError as exc:
        print(f"🔴 خطا ({exc.code}): {exc}")
        if exc.code == "auth":
            print("کلید اشتباه است.")
        elif exc.code == "network":
            print("هاست به وب سرویس وصل نشد؛ اگر لازم است AI_PROXY را در .env بگذار.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
