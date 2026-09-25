"""مدیریت وبهوک تلگرام از خط فرمان.

  python manage_webhook.py set      ثبت وبهوک + فهرست دستورها
  python manage_webhook.py commands ثبت فقط فهرست دستورها
  python manage_webhook.py info     نمایش وضعیت فعلی وبهوک
  python manage_webhook.py delete   حذف وبهوک (برگشت به polling)
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


async def main() -> None:
    action = (sys.argv[1] if len(sys.argv) > 1 else "info").lower()
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
                allowed_updates=["message", "callback_query", "my_chat_member"],
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
    asyncio.run(main())
