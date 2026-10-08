"""نقطه ورود ربات عبور برای اجرای مستقیم.

  python main.py            اجرا با polling (تست محلی یا سرور اختصاصی)

روی هاست سی پنل این فایل اجرا نمی شود؛ آنجا passenger_wsgi.py نقطه ورود است.
"""
from __future__ import annotations

import asyncio
import logging

from app.config import config
from app.runtime import build, setup_logging

setup_logging()
log = logging.getLogger("obour")


async def main() -> None:
    if not config.bot_token:
        raise SystemExit("BOT_TOKEN در فایل .env تنظیم نشده است")

    dp, bot, db, panel = build()
    await db.connect()

    from app import emoji as emo

    await emo.load(db)

    from app import effects

    await effects.load(db)
    await bot.delete_webhook(drop_pending_updates=True)

    from app.commands import setup_commands

    await setup_commands(bot)

    if panel:
        healthy = await panel.health()
        log.info("panel health: %s", "OK" if healthy else "FAILED")

    async def _cleanup_loop() -> None:
        """در حالت polling پروسه همیشه زنده است، پس یک حلقه واقعی داریم.

        (زیر Passenger این ممکن نیست و به جایش app/autocron.py در حاشیه
        آپدیت ها کار می کند.)
        """
        from app import autocron

        while True:
            try:
                n = await db.purge_expired_amounts()
                if n:
                    log.info("purged %s expired reserved amounts", n)
                await autocron.maybe_run(bot, db)
                await autocron.ai_round(bot, db)
            except Exception:  # noqa: BLE001
                log.warning("cleanup failed", exc_info=True)
            await asyncio.sleep(120)

    asyncio.create_task(_cleanup_loop())

    # ربات Game Club (اگر توکنش در .env هست) کنار عبور روی همین loop.
    # در حالت polling فقط خود ربات کار می کند؛ مینی اپ و API آن زیر
    # Passenger (passenger_wsgi.py، مسیر /gc) سرو می شوند.
    from game_club.config import gc as gc_cfg

    if gc_cfg.token:
        from game_club.bot import gcrt

        g = await gcrt.ensure()
        await g.bot.delete_webhook(drop_pending_updates=True)
        asyncio.create_task(g.dp.start_polling(g.bot, handle_signals=False))
        log.info("Game Club bot started (polling)")

    log.info("Obour bot started (polling)")

    try:
        await dp.start_polling(bot)
    finally:
        await db.close()
        if panel:
            await panel.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
