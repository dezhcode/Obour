"""افکت پیام (Message Effects) روی پیام های ربات.

تلگرام از Bot API 7.2 اجازه می دهد پیام با یک افکت تصویری فرستاده شود
(همان انیمیشن هایی مثل 🎉 و 🎊 که هنگام ارسال روی پیام پخش می شوند).

سه محدودیت مهم که رفتار این فایل را شکل داده:

۱. افکت فقط روی **چت خصوصی** کار می کند. در گروه و کانال نادیده گرفته
   می شود یا خطا می دهد.
۲. افکت فقط روی متدهای **ارسال** قابل تنظیم است (sendMessage و
   sendPhoto و ...). با ویرایش پیام (editMessageText) نمی شود افکت
   اضافه کرد. پس هر جایی که می خواهیم افکت داشته باشیم، باید پیام
   **تازه** فرستاده شود نه اینکه پیام قبلی ویرایش شود.
۳. اگر نسخه aiogram قدیمی باشد و پارامتر را نشناسد، باید بی سروصدا
   کنار گذاشته شود تا ربات نخوابد. افکت تزئینی است و هیچ وقت نباید
   جلوی تحویل سرویس یا اطلاع رسانی شارژ را بگیرد.

آیدی افکت ها دو منبع دارند: پیش فرض `.env` و override دیتابیس. مقدار
دیتابیس اگر تنظیم شده باشد اولویت دارد، چون از پنل ادمین (بخش «تنظیم
افکت با پیام») تنظیم می شود و باید بدون دپلوی دوباره اثر بگذارد.
"""
from __future__ import annotations

import logging

from .config import config

log = logging.getLogger("obour.effects")

# کلید -> آیدی افکت
TRIAL = "trial"
CHARGE = "charge"
PURCHASE = "purchase"


def _supported() -> bool:
    """آیا نسخه aiogram پارامتر message_effect_id را می شناسد؟"""
    try:
        from aiogram.methods import SendMessage

        return "message_effect_id" in getattr(SendMessage, "model_fields", {})
    except Exception:  # noqa: BLE001
        return False


_SUPPORTED: bool | None = None

# افکت هایی که تلگرام رد کرده. تا وقتی آیدی تازه ای برایشان تنظیم شود
# دیگر امتحان نمی شوند.
_DISABLED: set[str] = set()

# override های دیتابیس (تنظیم شده از پنل ادمین). خالی یعنی از .env
# استفاده کن. مثل app/emoji.py یک بار در بوت بارگذاری و در حافظه
# نگه داشته می شود تا هر ارسال به دیتابیس نزند.
_overrides: dict[str, str] = {}

_SETTING_KEY = {TRIAL: "effect_trial", CHARGE: "effect_charge", PURCHASE: "effect_purchase"}

# کلید ماندگار «این افکت را تلگرام رد کرد». بدون این، خاموش شدن فقط در
# حافظه همان پروسه می ماند و زیر Passenger که پروسه مدام از نو ساخته
# می شود، هر بار دوباره امتحان و دوباره رد می شود - یعنی هر تحویل
# سرویس یک درخواست شکست خورده اضافه دارد.
_REJECTED_KEY = {
    TRIAL: "effect_trial_rejected",
    CHARGE: "effect_charge_rejected",
    PURCHASE: "effect_purchase_rejected",
}


async def load(db) -> None:  # noqa: ANN001
    """بارگذاری override های ذخیره شده در دیتابیس، هنگام بوت."""
    _overrides.clear()
    for kind, key in _SETTING_KEY.items():
        value = await db.get_setting(key, "")
        if value:
            _overrides[kind] = value
    if _overrides:
        log.info("افکت های سفارشی از دیتابیس بارگذاری شد: %s مورد", len(_overrides))

    # افکت هایی که قبلا تلگرام ردشان کرده، همان اول خاموش می مانند
    _DISABLED.clear()
    for kind, key in _REJECTED_KEY.items():
        if await db.get_setting(key, ""):
            _DISABLED.add(kind)
    if _DISABLED:
        log.info(
            "افکت های رد شده (خاموش): %s - برای فعال کردن دوباره، "
            "از پنل ادمین آیدی تازه بگذار",
            ", ".join(sorted(_DISABLED)),
        )


async def set_override(db, kind: str, eid: str) -> None:  # noqa: ANN001
    """ذخیره آیدی تازه از پنل ادمین.

    وقتی آیدی تازه تنظیم می شود، اگر قبلا به خاطر رد شدن خاموش شده بود
    دوباره فعال می شود - آیدی جدید ممکن است رایگان باشد.
    """
    key = _SETTING_KEY.get(kind)
    if not key:
        raise ValueError(f"kind نامعتبر: {kind}")
    await db.set_setting(key, eid)
    _overrides[kind] = eid
    _DISABLED.discard(kind)
    # آیدی تازه یعنی فرصت دوباره: رکورد «رد شد» پاک می شود
    rejected = _REJECTED_KEY.get(kind)
    if rejected:
        await db.set_setting(rejected, "")


async def clear_override(db, kind: str) -> None:  # noqa: ANN001
    """برگشت به مقدار .env برای این افکت."""
    key = _SETTING_KEY.get(kind)
    if not key:
        return
    await db.set_setting(key, "")
    _overrides.pop(kind, None)
    _DISABLED.discard(kind)
    rejected = _REJECTED_KEY.get(kind)
    if rejected:
        await db.set_setting(rejected, "")


def disable(kind: str, reason: str) -> None:
    """خاموش کردن یک افکت پس از رد شدن توسط تلگرام.

    بدون این، هر خرید یک درخواست اضافه به تلگرام می فرستد که قطعا
    شکست می خورد و بعد دوباره بدون افکت تلاش می شود - یعنی هر تحویل
    سرویس دو برابر طول می کشد.

    خاموشی در دیتابیس هم ثبت می شود تا بعد از ریستارت پروسه دوباره
    امتحان نشود. ثبت در پس زمینه انجام می شود چون این تابع از مسیرهای
    همگام هم صدا زده می شود.
    """
    if kind in _DISABLED:
        return
    _DISABLED.add(kind)
    _persist_rejected(kind, reason)
    log.error(
        "افکت «%s» توسط تلگرام رد شد و خاموش شد: %s. "
        "علت معمول: آیدی افکت مال یک افکت پریمیوم است و ربات ها فقط "
        "افکت های رایگان را می توانند بفرستند. یک افکت بدون قفل انتخاب "
        "کن و آیدی اش را در .env بگذار.",
        kind,
        reason,
    )


def _persist_rejected(kind: str, reason: str) -> None:
    """ثبت «رد شد» در دیتابیس، بدون بلاک کردن مسیر ارسال.

    اگر حلقه رویداد در حال اجرا باشد یک تسک پس زمینه می سازیم؛ اگر نه
    (مثلا در اسکریپت کران)، بی سروصدا رد می شویم - بدترین حالت این است
    که دفعه بعد یک بار دیگر امتحان شود.
    """
    import asyncio

    key = _REJECTED_KEY.get(kind)
    if not key:
        return

    async def _write() -> None:
        try:
            from app.runtime import runtime

            db = getattr(runtime, "db", None)
            if db is not None:
                await db.set_setting(key, reason[:200] or "rejected")
        except Exception:  # noqa: BLE001
            log.debug("ثبت ماندگار خاموشی افکت %s انجام نشد", kind, exc_info=True)

    try:
        asyncio.get_running_loop().create_task(_write())
    except RuntimeError:
        pass


def effect_id(kind: str) -> str | None:
    """آیدی افکت یا None (اگر تنظیم نشده یا پشتیبانی نمی شود)."""
    global _SUPPORTED
    if _SUPPORTED is None:
        _SUPPORTED = _supported()
        if not _SUPPORTED:
            log.info("نسخه aiogram افکت پیام را پشتیبانی نمی کند، نادیده گرفته شد")
    if not _SUPPORTED or kind in _DISABLED:
        return None
    value = _overrides.get(kind) or {
        TRIAL: config.effect_trial,
        CHARGE: config.effect_charge,
        PURCHASE: config.effect_purchase,
    }.get(kind, "")
    return value or None


def current_id(kind: str) -> str:
    """آیدی فعلی این افکت (بدون توجه به خاموش بودن)، برای نمایش در پنل."""
    return _overrides.get(kind) or {
        TRIAL: config.effect_trial,
        CHARGE: config.effect_charge,
        PURCHASE: config.effect_purchase,
    }.get(kind, "")


def source(kind: str) -> str:
    """«دیتابیس» یا «env» - برای نمایش در پنل ادمین."""
    return "دیتابیس" if kind in _overrides else "env"


def kwargs(kind: str, chat_id: int | None = None) -> dict:
    """پارامتر آماده برای پاس دادن به متدهای ارسال.

    اگر افکت در دسترس نباشد دیکشنری خالی برمی گردد، پس صدازننده
    می تواند بدون شرط `**effects.kwargs(...)` را باز کند.

    chat_id مثبت یعنی چت خصوصی؛ آیدی منفی مال گروه و کانال است و افکت
    آنجا معنا ندارد.
    """
    if chat_id is not None and chat_id < 0:
        return {}
    eid = effect_id(kind)
    return {"message_effect_id": eid} if eid else {}
