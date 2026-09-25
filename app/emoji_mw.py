"""میان افزار خروجی: اعمال ایموجی سفارشی روی همه پیام های ربات.

به جای اینکه در ده ها جای کد دستی apply_emoji صدا زده شود، این لایه روی
خود کلاینت تلگرام می نشیند و هر متن و کپشنی که ربات می فرستد را قبل از
ارسال پردازش می کند. این تضمین می کند هیچ پیامی جا نمی ماند.
"""
from __future__ import annotations

import logging
from typing import Any

from aiogram import BaseMiddleware
from aiogram.client.session.middlewares.base import NextRequestMiddlewareType
from aiogram.methods import Response, TelegramMethod

log = logging.getLogger("obour.emoji_mw")

# متدهایی که متن یا کپشن دارند
_TEXT_FIELDS = ("text", "caption")


class EmojiOutgoingMiddleware(BaseMiddleware):
    """روی هر متن/کپشن خروجی: تضمین جهت راست به چپ + جایگزینی ایموجی سفارشی."""

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType,
        bot: Any,  # noqa: ANN401
        method: TelegramMethod,
    ) -> Response:
        try:
            self._apply(method)
        except Exception:  # noqa: BLE001
            # ایموجی تزئینی است؛ هرگز نباید جلوی ارسال پیام را بگیرد
            log.warning("اعمال ایموجی ناموفق بود", exc_info=True)
        return await make_request(bot, method)

    @staticmethod
    def _apply(method: TelegramMethod) -> None:
        from app.texts import apply_emoji, ensure_rtl

        # پاپ آپ ها (answerCallbackQuery) نه HTML را پردازش می کنند و نه
        # ایموجی سفارشی را پشتیبانی می کنند؛ هرچه بفرستیم عینا نمایش
        # داده می شود. بدون این استثنا، کاربر داخل پاپ آپ تگ خام
        # <tg-emoji ...> می دید.
        if type(method).__name__ == "AnswerCallbackQuery":
            return

        for field in _TEXT_FIELDS:
            value = getattr(method, field, None)
            if isinstance(value, str) and value:
                # راست به چپ سازی همیشه اجرا می شود (وابسته به تنظیم
                # ایموجی سفارشی نیست)؛ ایموجی فقط وقتی چیزی سفارشی
                # شده باشد کاری انجام می دهد.
                new = apply_emoji(ensure_rtl(value))
                if new != value:
                    object.__setattr__(method, field, new)
