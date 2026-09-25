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
            except Exception:  # noqa: BLE001
                log.warning("cleanup failed", exc_info=True)
            await asyncio.sleep(120)

    asyncio.create_task(_cleanup_loop())
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
