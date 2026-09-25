"""روشن و خاموش کردن بخش های ربات از پنل ادمین.

چرا یک ماژول جدا؟
هر بخش فروشگاه (کانفیگ، هوش مصنوعی، ساخت دلخواه، تست رایگان و...) باید
بدون دیپلوی قابل خاموش کردن باشد - مثلا وقتی پنل خوابیده، وقتی موجودی
تمام شده، یا وقتی هنوز آماده عرضه نیست.

مقدارها در همان جدول settings ذخیره می شوند و در حافظه کش می شوند تا
هر بار رندر منو یک کوئری اضافه نزند.
"""
from __future__ import annotations

import logging

from app.db import Database

log = logging.getLogger("obour.features")

# کلید -> (عنوان در پنل، توضیح کوتاه، پیش فرض روشن؟)
FEATURES: dict[str, tuple[str, str, bool]] = {
    "shop_vpn": ("🌐 فروش کانفیگ", "پلن های اینترنت آزاد", True),
    "shop_ai": ("🤖 خدمات هوش مصنوعی", "اشتراک جمنای و مانند آن", False),
    "shop_custom": ("🎛 ساخت سرویس دلخواه", "انتخاب حجم و مدت توسط کاربر", True),
    "shop_locations": ("🌍 سرورها و لوکیشن ها", "صفحه معرفی لوکیشن ها", True),
    "shop_trial": ("🎁 تست رایگان", "سرویس آزمایشی برای کاربر تازه", True),
    "shop_wallet": ("💰 شارژ کیف پول", "شارژ دستی با رسید", True),
    "shop_referral": ("🤝 هم سفرها", "دعوت دوستان و پاداش", True),
}

_cache: dict[str, bool] = {}


def _key(name: str) -> str:
    return f"feature_{name}"


async def load(db: Database) -> None:
    """خواندن وضعیت همه بخش ها هنگام بالا آمدن ربات."""
    _cache.clear()
    for name, (_title, _desc, default) in FEATURES.items():
        raw = await db.get_setting(_key(name), "")
        _cache[name] = (raw == "1") if raw in ("0", "1") else default
    off = [n for n, v in _cache.items() if not v]
    if off:
        log.info("بخش های خاموش: %s", ", ".join(off))


def is_on(name: str) -> bool:
    """آیا این بخش برای کاربرها فعال است؟

    اگر کلید ناشناخته باشد True برمی گردد - یعنی قابلیت تازه ای که
    هنوز در فهرست ثبت نشده، به طور پیش فرض کار می کند و چیزی خاموش
    نمی ماند.
    """
    if name not in FEATURES:
        return True
    if name not in _cache:
        return FEATURES[name][2]
    return _cache[name]


async def set_on(db: Database, name: str, value: bool) -> None:
    await db.set_setting(_key(name), "1" if value else "0")
    _cache[name] = value
    log.info("بخش %s %s شد", name, "روشن" if value else "خاموش")


async def toggle(db: Database, name: str) -> bool:
    new = not is_on(name)
    await set_on(db, name, new)
    return new


def summary() -> list[tuple[str, str, bool]]:
    """(کلید، عنوان، روشن؟) برای صفحه پنل ادمین."""
    return [(name, FEATURES[name][0], is_on(name)) for name in FEATURES]
