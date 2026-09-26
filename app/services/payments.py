"""کدام روش های شارژ به کدام کاربر نشان داده می شود.

کارت به کارت فقط برای کاربر فارسی زبان است (کارت بانکی ایران). کاربرهای
انگلیسی، روسی و چینی فقط با کریپتو (TON / USDT) و Telegram Stars شارژ
می کنند. زبان، همان زبانی است که کاربر در ربات انتخاب کرده؛ ایرانی ای که
انگلیسی انتخاب کرده با برگشتن به فارسی دوباره کارت به کارت را می بیند.

هر روش فقط وقتی هست که تنظیم شده باشد: کارت بدون شماره کارت، کریپتو بدون
آدرس کیف پول و نرخ، و Stars بدون نرخ ستاره نشان داده نمی شوند.

ادمین هم هر روش را جدا روشن و خاموش می کند (pay_*_on). خاموش کردن فقط
شروع پرداخت تازه را می بندد؛ فاکتور کریپتو یا Stars که قبلا ساخته و پرداخت
شده، همچنان تسویه می شود تا پول کسی گم نشود.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app import i18n

if TYPE_CHECKING:
    from app.db import Database

CARD, CRYPTO, STARS = "card", "crypto", "stars"
METHODS = (CARD, CRYPTO, STARS)
TITLES = {CARD: "کارت به کارت", CRYPTO: "کریپتو (TON Connect)", STARS: "Telegram Stars"}
_KEY = {CARD: "pay_card_on", CRYPTO: "pay_crypto_on", STARS: "pay_stars_on"}


async def is_on(db: "Database", method: str) -> bool:
    """کلید ادمین برای این روش؛ پیش فرض روشن."""
    return (await db.get_setting(_KEY[method], "1") or "1") != "0"


async def set_on(db: "Database", method: str, on: bool) -> None:
    await db.set_setting(_KEY[method], "1" if on else "0")


async def switches(db: "Database") -> list[dict]:
    return [{"key": m, "title": TITLES[m], "on": await is_on(db, m)} for m in METHODS]


async def card_ok(db: "Database", lang: str | None = None) -> bool:
    """کارت به کارت برای این کاربر مجاز و روشن است؟"""
    return card_allowed(lang) and await is_on(db, CARD)


def card_allowed(lang: str | None = None) -> bool:
    return (lang or i18n.get_lang()) == "fa"


async def available(db: "Database", lang: str | None = None, telegram_id: int | None = None) -> list[str]:
    from app.services import crypto, stars

    out = []
    if await card_ok(db, lang) and await db.get_setting("card_number", ""):
        out.append(CARD)
    # روی testnet فقط ادمین (سکه تست مجانی است ولی شارژ واقعی می دهد)
    if crypto.allowed_for(telegram_id) and await is_on(db, CRYPTO) and await crypto.configured(db):
        out.append(CRYPTO)
    if await is_on(db, STARS) and await stars.enabled(db):
        out.append(STARS)
    return out
