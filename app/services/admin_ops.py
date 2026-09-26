"""کارهای ادمین، مستقل از رابط.

پنل ادمین ربات و پنل ادمین مینی اپ هر دو از همین توابع رد می شوند؛ پس
تایید یک رسید، رد کردنش، تغییر موجودی و ذخیره یک تنظیم در هر دو جا دقیقا
یک رفتار دارد (همان اطلاع به کاربر، به زبان خودش، همان قفل های اتمیک).

هیچ تابعی اینجا خودش بررسی نمی کند که صدازننده ادمین است؛ آن کار دروازه
است (فیلتر ادمین روتر ربات، و is_admin در API مینی اپ).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app import effects, i18n, texts
from app.config import config

if TYPE_CHECKING:
    from app.db import Database

log = logging.getLogger("obour.admin")


def is_admin(telegram_id: int | None) -> bool:
    return bool(telegram_id) and int(telegram_id) in config.admin_ids


async def notify_user(bot, telegram_id: int, body: str, effect: str = "", lang: str | None = None) -> str:  # noqa: ANN001
    """خبر به کاربر؛ خروجی خالی یعنی رسید، وگرنه علت شکست."""
    from aiogram.exceptions import TelegramForbiddenError

    if bot is None:
        return "ربات در دسترس نیست"
    fx = effects.kwargs(effect, telegram_id) if effect else {}
    for attempt_fx in ((fx, {}) if fx else ({},)):
        try:
            with i18n.using(lang):
                await bot.send_message(telegram_id, body, **attempt_fx)
            return ""
        except TelegramForbiddenError:
            log.warning("کاربر %s ربات را بلاک کرده", telegram_id)
            return "کاربر ربات را بلاک کرده"
        except Exception as exc:  # noqa: BLE001
            if attempt_fx:
                effects.disable(effect, str(exc))
                continue
            log.error("ارسال پیام به کاربر %s ناموفق بود", telegram_id, exc_info=True)
            return str(exc)[:80]
    return "نامشخص"


# ═══════════════════ رسیدهای شارژ ═══════════════════


async def approve_charge(bot, db: "Database", txn_id: int, admin_id: int) -> dict:  # noqa: ANN001
    """{ok, user, amount, notify_err} یا {ok: False} اگر قبلا بررسی شده."""
    txn = await db.decide_transaction(txn_id, "approved", admin_id)
    if txn is None:
        return {"ok": False}
    if not await db.atomic_credit(txn["user_id"], txn["amount"]):
        log.error("credit failed after approval txn=%s", txn_id)
    # مبلغ یکتا آزاد شود تا دوباره قابل استفاده باشد و جدول پر نشود
    await db.release_amount(txn["amount"])
    fresh = await db.get_user(txn["user_id"])
    lang = i18n.lang_of(fresh)
    with i18n.using(lang):
        body = texts.CHARGE_APPROVED.format(amount=f"{txn['amount']:,}", balance=f"{fresh['balance']:,}")
    err = await notify_user(bot, int(fresh["telegram_id"]), body, effect=effects.CHARGE, lang=lang)
    log.info("ادمین %s شارژ %s (%s تومان) را تایید کرد", admin_id, txn_id, txn["amount"])
    return {"ok": True, "user": fresh, "amount": txn["amount"], "notify_err": err}


async def reject_charge(bot, db: "Database", txn_id: int, admin_id: int, reason: str) -> dict:  # noqa: ANN001
    """رد با دلیل (فارسی، همان که ادمین دید). دلیل آماده به زبان کاربر می رود."""
    txn = await db.decide_transaction(txn_id, "rejected", admin_id, reason=reason)
    if txn is None:
        return {"ok": False}
    await db.release_amount(txn["amount"])
    user = await db.get_user(txn["user_id"])
    lang = i18n.lang_of(user)
    fa_reasons = texts.__dict__["REJECT_REASONS"]
    code = next((k for k, v in fa_reasons.items() if v == reason), None)
    with i18n.using(lang):
        user_reason = texts.REJECT_REASONS[code] if code else reason
        body = texts.CHARGE_REJECTED.format(reason=user_reason)
    err = await notify_user(bot, int(user["telegram_id"]), body, lang=lang)
    log.info("ادمین %s شارژ %s را رد کرد: %s", admin_id, txn_id, reason)
    return {"ok": True, "user": user, "notify_err": err}


async def duplicate_charge(bot, db: "Database", txn_id: int, admin_id: int) -> dict:  # noqa: ANN001
    txn = await db.decide_transaction(txn_id, "rejected", admin_id, reason="رسید تکراری")
    if txn is None:
        return {"ok": False}
    await db.release_amount(txn["amount"])
    user = await db.get_user(txn["user_id"])
    lang = i18n.lang_of(user)
    with i18n.using(lang):
        body = texts.DUP_RECEIPT
    err = await notify_user(bot, int(user["telegram_id"]), body, lang=lang)
    log.info("ادمین %s شارژ %s را تکراری زد", admin_id, txn_id)
    return {"ok": True, "user": user, "notify_err": err}


# ═══════════════════ کاربر ═══════════════════


async def find_user(db: "Database", query: str) -> tuple[dict | None, str]:
    """آیدی عددی، یوزرنیم، یا مبلغ رسید. خروجی: (کاربر، توضیح پیدا شدن)."""
    q = (query or "").strip().lstrip("@").replace(",", "").replace("،", "")
    q = q.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if not q:
        return None, ""
    if q.isdigit():
        n = int(q)
        user = await db.get_user_by_tg(n)
        if user:
            return user, ""
        pending = await db.find_by_amount(n)
        if pending:
            user = await db.get_user(pending["user_id"])
            if user:
                return user, f"مبلغ {n:,} تومان متعلق به این کاربر است"
    row = await db.fetchone("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (q,))
    return (dict(row) if row else None), ""


async def adjust_balance(bot, db: "Database", telegram_id: int, amount: int, add: bool, admin_id: int) -> dict:  # noqa: ANN001
    """افزودن یا کسر دستی. {ok, balance, amount, notify_err} یا {ok: False, error}."""
    if amount <= 0:
        return {"ok": False, "error": "لطفا یه عدد مثبت به تومان بفرست."}
    user = await db.get_user_by_tg(telegram_id)
    if not user:
        return {"ok": False, "error": "کاربر پیدا نشد."}
    if add:
        if not await db.atomic_credit(user["id"], amount):
            return {"ok": False, "error": "افزودن موجودی انجام نشد."}
        await db.insert_transaction(user["id"], "admin_adjust", amount, status="approved")
        done = amount
    else:
        # مبلغ از موجودی تازه خوانده می شود، و تراکنش فقط در صورت موفقیت
        # کسر ثبت می شود تا گزارش مالی دروغ نگوید.
        done = min(amount, int(user["balance"]))
        if done <= 0 or not await db.atomic_debit(user["id"], done):
            return {"ok": False, "error": "موجودی کاربر به اندازه کافی نبود."}
        await db.insert_transaction(user["id"], "admin_adjust", -done, status="approved")
    fresh = await db.get_user(user["id"])
    lang = i18n.lang_of(fresh)
    with i18n.using(lang):
        if add:
            body = texts.CHARGE_APPROVED.format(amount=f"{done:,}", balance=f"{fresh['balance']:,}")
        else:
            body = texts.BALANCE_TAKEN.format(amount=f"{done:,}", balance=f"{fresh['balance']:,}")
    err = await notify_user(bot, int(user["telegram_id"]), body,
                            effect=effects.CHARGE if add else "", lang=lang)
    log.info("ادمین %s موجودی کاربر %s را %s%s کرد", admin_id, telegram_id, "+" if add else "-", done)
    return {"ok": True, "balance": int(fresh["balance"]), "amount": done, "notify_err": err}


async def set_blocked(db: "Database", telegram_id: int, blocked: bool, admin_id: int) -> bool:
    if is_admin(telegram_id):
        return False                      # ادمین خودش را قفل نکند
    rc = await db.execute("UPDATE users SET is_blocked = ? WHERE telegram_id = ?", (1 if blocked else 0, telegram_id))
    log.info("ادمین %s کاربر %s را %s", admin_id, telegram_id, "مسدود کرد" if blocked else "آزاد کرد")
    return rc == 1


# ═══════════════════ تنظیمات ═══════════════════

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٫", "0123456789.")

# فیلدهایی که از پنل (ربات یا مینی اپ) قابل تغییرند
SETTING_FIELDS = (
    "card_number", "card_holder", "bank_name", "min_charge",
    "stars_rate", "crypto_usdt_rate", "crypto_ton_rate", "crypto_fee_percent",
)


def clean_setting(field: str, value: str) -> tuple[bool, str]:
    """(درست است؟، مقدار تمیز یا متن خطا)."""
    value = (value or "").strip()
    if field == "min_charge":
        clean = value.replace(",", "").replace("،", "").translate(_FA_DIGITS)
        if not clean.isdigit() or int(clean) < 1000:
            return False, "لطفا یه عدد بزرگ تر از ۱۰۰۰ بفرست."
        return True, str(int(clean))
    if field in ("crypto_usdt_rate", "crypto_ton_rate", "stars_rate"):
        clean = value.replace(",", "").replace("،", "").translate(_FA_DIGITS)
        if not clean.isdigit():
            return False, "لطفا یه عدد (تومان) بفرست."
        return True, str(int(clean))
    if field == "crypto_fee_percent":
        clean = value.replace("٪", "").replace("%", "").translate(_FA_DIGITS)
        try:
            fee = float(clean)
        except ValueError:
            return False, "لطفا یه عدد بین ۰ تا ۵۰ بفرست."
        if not 0 <= fee <= 50:
            return False, "لطفا یه عدد بین ۰ تا ۵۰ بفرست."
        return True, f"{fee:g}"
    if field == "card_number":
        digits = "".join(ch for ch in value.translate(_FA_DIGITS) if ch.isdigit())
        if len(digits) != 16:
            return False, "شماره کارت باید ۱۶ رقم باشه. دوباره بفرست:"
        return True, digits
    if field in ("card_holder", "bank_name"):
        return True, value[:60]
    return False, "این فیلد قابل ویرایش نیست."


async def save_setting(db: "Database", field: str, value: str, admin_id: int) -> tuple[bool, str]:
    if field not in SETTING_FIELDS:
        return False, "این فیلد قابل ویرایش نیست."
    ok, clean = clean_setting(field, value)
    if ok:
        await db.set_setting(field, clean)
        log.info("ادمین %s تنظیم %s را عوض کرد", admin_id, field)
    return ok, clean
