"""Middleware های ربات: ثبت کاربر، مسدودی، و محدودیت نرخ."""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from . import i18n
from .keyboards import is_admin


async def rules_body(db: Any, user: dict) -> str:  # noqa: ANN401
    """متن صفحه قوانین. متن خود قوانین را ادمین نوشته و ترجمه نمی شود."""
    from app import texts
    from app.utils import esc

    rules = await db.get_setting("rules_text", "")
    return texts.RULES_INTRO.format(
        name=esc(user.get("first_name") or i18n.t("دوست من"))
    ) + "\n\n" + rules


class UserMiddleware(BaseMiddleware):
    """ثبت / لود کاربر و بررسی مسدودی (غیر ادمین ها)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db = data.get("db")
        tg_user = data.get("event_from_user")
        if not db or not tg_user or tg_user.is_bot:
            return await handler(event, data)

        deep_link = None
        if isinstance(event, Message) and event.text and event.text.startswith("/start"):
            parts = event.text.split(maxsplit=1)
            if len(parts) == 2 and parts[1].startswith("ref_"):
                deep_link = parts[1][4:]

        referred_by = None
        if deep_link and deep_link.isdigit():
            ref = int(deep_link)
            if ref != tg_user.id:
                referred_by = ref

        user = await db.get_or_create_user(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            referred_by=referred_by,
        )
        data["user"] = user
        # زبان همین آپدیت؛ همه texts.X و دکمه ها از اینجا به بعد به این زبان اند
        i18n.set_lang(i18n.lang_of(user, getattr(tg_user, "language_code", None)))

        if user["is_blocked"] and not is_admin(tg_user.id):
            if isinstance(event, Message):
                await event.answer(i18n.t("دسترسی شما موقتا محدود شده است."))
            elif isinstance(event, CallbackQuery):
                await event.answer(i18n.t("دسترسی شما موقتا محدود شده است."), show_alert=True)
            return None

        # پیام پرداخت موفق (Stars) هیچ وقت نباید پشت دروازه ها بماند؛
        # ستاره کم شده و کیف پول باید همین حالا شارژ شود.
        if isinstance(event, Message) and event.successful_payment:
            return await handler(event, data)

        # دروازه زبان: کاربر تازه اول زبانش را انتخاب می کند، بعد قوانین
        if await self._lang_block(event, user, tg_user):
            return None

        # دروازه قوانین: کاربر جدید تا تایید نکند به بقیه بخش ها نمی رسد.
        if await self._rules_block(event, data, db, user, tg_user):
            return None

        return await handler(event, data)

    @staticmethod
    async def _lang_block(event: TelegramObject, user: dict, tg_user: Any) -> bool:  # noqa: ANN401
        """True یعنی هنوز زبان انتخاب نشده و صفحه انتخاب نشان داده شد.

        پیشنهاد (تیک خورده) زبانی است که از تلگرام کاربر حدس زده شده و
        متن صفحه به همان زبان است.
        """
        if user.get("lang"):
            return False
        if isinstance(event, CallbackQuery) and (event.data or "").startswith("lang"):
            return False
        from app import keyboards, texts

        guess = i18n.detect(getattr(tg_user, "language_code", None))
        if isinstance(event, CallbackQuery):
            await event.answer()
            await event.message.answer(texts.LANG_PICK, reply_markup=keyboards.lang_kb(guess))
        elif isinstance(event, Message):
            await event.answer(texts.LANG_PICK, reply_markup=keyboards.lang_kb(guess))
        return True

    @staticmethod
    async def _rules_block(
        event: TelegramObject,
        data: dict[str, Any],
        db: Any,  # noqa: ANN401
        user: dict,
        tg_user: Any,  # noqa: ANN401
    ) -> bool:
        """True یعنی جریان متوقف شود چون قوانین تایید نشده.

        ادمین ها و خود دکمه تایید مستثنا هستند تا قفل نشوند.
        """
        if user.get("rules_accepted_at") or is_admin(tg_user.id):
            return False
        if await db.get_setting("rules_enabled", "1") != "1":
            return False

        # اجازه عبور به خود عمل تایید، و به عوض کردن زبان
        if isinstance(event, CallbackQuery) and (
            event.data == "rules:ok" or (event.data or "").startswith("lang")
        ):
            return False

        from app import keyboards

        body = await rules_body(db, user)

        if isinstance(event, CallbackQuery):
            await event.answer()
            await event.message.answer(body, reply_markup=keyboards.rules_kb())
        elif isinstance(event, Message):
            await event.answer(body, reply_markup=keyboards.rules_kb())
        return True


class ThrottleMiddleware(BaseMiddleware):
    """محدودیت نرخ ساده (ضد اسپم و دابل کلیک).

    دیکشنری زمان ها هر چند دقیقه پاکسازی می شود. قبلا هیچ وقت پاک
    نمی شد و روی ربات پرکاربر آرام آرام حافظه پروسه را پر می کرد.
    """

    _MAX_ENTRIES = 5000

    def __init__(self, delay: float = 0.4) -> None:
        self.delay = delay
        self._last: dict[int, float] = {}
        self._last_cleanup = time.monotonic()

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < 300 and len(self._last) < self._MAX_ENTRIES:
            return
        self._last_cleanup = now
        stale = [uid for uid, ts in self._last.items() if now - ts > 60]
        for uid in stale:
            self._last.pop(uid, None)
        if len(self._last) > self._MAX_ENTRIES:
            self._last.clear()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        # پرداخت موفق هرگز دور ریخته نمی شود، هر قدر هم پشت سر هم باشد
        if isinstance(event, Message) and event.successful_payment:
            return await handler(event, data)
        if tg_user:
            now = time.monotonic()
            self._cleanup(now)
            last = self._last.get(tg_user.id, 0.0)
            if now - last < self.delay:
                if isinstance(event, CallbackQuery):
                    await event.answer("یه کم آروم تر 😊", show_alert=False)
                return None
            self._last[tg_user.id] = now
        return await handler(event, data)
