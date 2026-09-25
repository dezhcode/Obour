"""فهرست دستورهای ربات و ثبت آن روی تلگرام.

این فهرست همان چیزی است که کاربر با زدن دکمه منو (کنار فیلد تایپ) و با
تایپ / می بیند. ثبتش یک بار کافی است و تلگرام آن را نگه می دارد، ولی
اجرای دوباره بی خطر است.

از سه جا ثبت می شود:
  python manage_webhook.py set          هنگام ثبت وبهوک
  GET  <آدرس اپ>/setcommands?key=...    روی هاست سی پنل
  python main.py                        هنگام اجرای polling
"""
from __future__ import annotations

import logging

from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)

from .config import config

log = logging.getLogger("obour.commands")

# (دستور، توضیح) - ترتیب همان ترتیبی است که کاربر می بیند
PUBLIC_COMMANDS: list[tuple[str, str]] = [
    ("start", "شروع و منوی اصلی"),
    ("buy", "خرید سرویس"),
    ("account", "سرویس های من"),
    ("wallet", "کیف پول و شارژ"),
    ("test", "دریافت تست رایگان"),
    ("help", "راهنمای اتصال"),
    ("track", "پیگیری با کد"),
    ("support", "پشتیبانی"),
    ("lang", "زبان"),
]

# دستورهای اضافه ای که فقط ادمین ها در منوی خودشان می بینند
ADMIN_COMMANDS: list[tuple[str, str]] = PUBLIC_COMMANDS + [
    ("admin", "پنل مدیریت"),
    ("fx", "تست افکت پیام"),
    ("hwid", "دستگاه های یک سرویس"),
    ("bc", "وضعیت ارسال همگانی"),
    ("locimg", "عکس صفحه لوکیشن ها"),
    ("version", "نسخه ربات و بررسی نصب"),
]


def _build(items: list[tuple[str, str]]) -> list[BotCommand]:
    return [BotCommand(command=c, description=d) for c, d in items]


def _build_lang(items: list[tuple[str, str]], lang: str) -> list[BotCommand]:
    from . import i18n

    with i18n.using(lang):
        return [BotCommand(command=c, description=i18n.t(d)) for c, d in items]


async def setup_commands(bot) -> None:  # noqa: ANN001
    """ثبت فهرست دستورها روی تلگرام.

    خطاها فقط لاگ می شوند؛ نبودن منوی دستورها نباید جلوی بالا آمدن ربات
    را بگیرد.
    """
    try:
        await bot.set_my_commands(
            _build(PUBLIC_COMMANDS), scope=BotCommandScopeAllPrivateChats()
        )
        log.info("فهرست دستورها ثبت شد: %s مورد", len(PUBLIC_COMMANDS))
        # همین فهرست به زبان اپ تلگرام کاربر. تلگرام بر اساس language_code
        # خود اپ انتخاب می کند، نه زبانی که کاربر در ربات برگزیده.
        for lang in ("en", "ru", "zh"):
            await bot.set_my_commands(
                _build_lang(PUBLIC_COMMANDS, lang),
                scope=BotCommandScopeAllPrivateChats(),
                language_code=lang,
            )
    except Exception:  # noqa: BLE001
        log.warning("ثبت فهرست دستورها ناموفق بود", exc_info=True)
        return

    for admin_id in config.admin_ids:
        try:
            await bot.set_my_commands(
                _build(ADMIN_COMMANDS), scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except Exception:  # noqa: BLE001
            # ادمینی که هنوز ربات را استارت نکرده، چت ندارد. مهم نیست.
            log.info("ثبت دستورهای ادمین برای %s انجام نشد", admin_id)
