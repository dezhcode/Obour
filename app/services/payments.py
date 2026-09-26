"""کدام روش های شارژ به کدام کاربر نشان داده می شود.

کارت به کارت فقط برای کاربر فارسی زبان است (کارت بانکی ایران). کاربرهای
انگلیسی، روسی و چینی فقط با کریپتو (TON / USDT) و Telegram Stars شارژ
می کنند. زبان، همان زبانی است که کاربر در ربات انتخاب کرده؛ ایرانی ای که
انگلیسی انتخاب کرده با برگشتن به فارسی دوباره کارت به کارت را می بیند.

هر روش فقط وقتی هست که تنظیم شده باشد: کارت بدون شماره کارت، کریپتو بدون
آدرس کیف پول و نرخ، و Stars بدون نرخ ستاره نشان داده نمی شوند.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app import i18n

if TYPE_CHECKING:
    from app.db import Database

CARD, CRYPTO, STARS = "card", "crypto", "stars"


def card_allowed(lang: str | None = None) -> bool:
    return (lang or i18n.get_lang()) == "fa"


async def available(db: "Database", lang: str | None = None, telegram_id: int | None = None) -> list[str]:
    from app.services import crypto, stars

    out = []
    if card_allowed(lang) and await db.get_setting("card_number", ""):
        out.append(CARD)
    # روی testnet فقط ادمین (سکه تست مجانی است ولی شارژ واقعی می دهد)
    if crypto.allowed_for(telegram_id) and await crypto.configured(db):
        out.append(CRYPTO)
    if await stars.enabled(db):
        out.append(STARS)
    return out
