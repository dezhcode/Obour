"""مدیریت وبهوک تلگرام از خط فرمان.

  python manage_webhook.py set      ثبت وبهوک + فهرست دستورها
  python manage_webhook.py commands ثبت فقط فهرست دستورها
  python manage_webhook.py info     نمایش وضعیت فعلی وبهوک
  python manage_webhook.py delete   حذف وبهوک (برگشت به polling)

ربات Game Club:
  python manage_webhook.py gc-set   ثبت وبهوک + دستورها + دکمه منو (مینی اپ)
  python manage_webhook.py gc-info  نمایش وضعیت فعلی وبهوک
"""
from __future__ import annotations

import asyncio
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from app.config import config
from app.runtime import make_session

from aiogram import Bot


async def game_club(action: str) -> None:
    from game_club.bot import setup
    from game_club.config import gc

    if not gc.token:
        raise SystemExit("GAME_CLUB_BOT_TOKEN تنظیم نشده است")
    bot = Bot(token=gc.token, session=make_session())
    try:
        if action == "gc-set":
            print(await setup(bot))
        info = await bot.get_webhook_info()
        me = await bot.get_me()
        print(f"\nربات            : @{me.username}")
        print(f"آدرس فعلی وبهوک : {info.url or '-'}")
        print(f"آپدیت های معلق  : {info.pending_update_count}")
        print(f"آخرین خطا       : {info.last_error_message or '-'}")
        if gc.username and gc.username.lower() != (me.username or "").lower():
            print(f"\nهشدار: GAME_CLUB_BOT_USERNAME={gc.username} ولی توکن مال @{me.username} است")
        if info.url and info.url != gc.webhook_url:
            print(f"\nهشدار: آدرس ثبت شده با .env فرق دارد. انتظار: {gc.webhook_url}")
    finally:
        await bot.session.close()


async def main() -> None:
    action = (sys.argv[1] if len(sys.argv) > 1 else "info").lower()
    if action.startswith("gc-"):
        await game_club(action)
        return
    if not config.bot_token:
        raise SystemExit("BOT_TOKEN تنظیم نشده است")

    bot = Bot(token=config.bot_token, session=make_session())
    try:
        if action == "set":
            if not config.webhook_base_url:
                raise SystemExit("WEBHOOK_BASE_URL تنظیم نشده است")
            if not config.webhook_secret:
                raise SystemExit("WEBHOOK_SECRET تنظیم نشده است (برای امنیت الزامی است)")
            await bot.set_webhook(
                url=config.webhook_url,
                secret_token=config.webhook_secret,
                drop_pending_updates=True,
                allowed_updates=list(config.allowed_updates),
            )
            print(f"وبهوک ثبت شد: {config.webhook_url}")

            from app.commands import PUBLIC_COMMANDS, setup_commands

            await setup_commands(bot)
            print(f"فهرست دستورها ثبت شد: {len(PUBLIC_COMMANDS)} مورد")

        elif action == "commands":
            from app.commands import PUBLIC_COMMANDS, setup_commands

            await setup_commands(bot)
            print(f"فهرست دستورها ثبت شد: {len(PUBLIC_COMMANDS)} مورد")

        elif action == "delete":
            await bot.delete_webhook(drop_pending_updates=False)
            print("وبهوک حذف شد")

        info = await bot.get_webhook_info()
        me = await bot.get_me()
        print(f"\nربات            : @{me.username}")
        print(f"آدرس فعلی وبهوک : {info.url or '-'}")
        print(f"آپدیت های معلق  : {info.pending_update_count}")
        print(f"آخرین خطا       : {info.last_error_message or '-'}")
        if info.url and info.url != config.webhook_url:
            print(f"\nهشدار: آدرس ثبت شده با .env فرق دارد. انتظار: {config.webhook_url}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    from aiogram.exceptions import TelegramAPIError, TelegramNetworkError

    try:
        asyncio.run(main())
    except TelegramNetworkError as e:
        raise SystemExit(f"تلگرام در دسترس نیست: {e}\nاگر هاست به api.telegram.org راه ندارد TG_PROXY یا TG_API_BASE را در .env بگذار.") from None
    except TelegramAPIError as e:
        raise SystemExit(f"تلگرام خطا داد: {e}") from None
