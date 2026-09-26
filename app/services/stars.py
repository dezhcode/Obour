"""شارژ کیف پول با Telegram Stars (ارز XTR).

جریان:
  ۱. کاربر مبلغ تومانی را انتخاب می کند؛ تعداد ستاره از نرخ ادمین
     (تومان به ازای هر ستاره) ساخته و روی فاکتور ثابت می شود.
  ۲. تلگرام خودش صفحه پرداخت را نشان می دهد (در ربات با send_invoice، در
     مینی اپ با لینک فاکتور و Telegram.WebApp.openInvoice).
  ۳. تلگرام پیش از کم کردن ستاره pre_checkout_query می فرستد؛ فاکتور
     بررسی و تایید می شود. بعد پیام successful_payment می رسد و همان جا
     کیف پول تومانی کاربر شارژ می شود.

برای ستاره provider_token لازم نیست و پول (ستاره) به حساب خود ربات می رود؛
برداشتش از Fragment است.

نکته مهم: وبهوک باید pre_checkout_query را هم بگیرد (runtime خودش درستش
می کند). اگر به آن جواب داده نشود، پرداخت بعد از ۱۰ ثانیه شکست می خورد.
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from app import i18n, texts
from app.config import config
from app.services import charge as charge_svc
from app.utils import esc

if TYPE_CHECKING:
    from app.db import Database

log = logging.getLogger("obour.stars")

CURRENCY = "XTR"
# سقف ستاره یک فاکتور در تلگرام
MAX_STARS = 10_000

OFF = "off"
TOO_SMALL = charge_svc.TOO_SMALL
TOO_LARGE = charge_svc.TOO_LARGE


async def rate(db: "Database") -> int:
    """تومان به ازای هر ستاره؛ ۰ یعنی Stars خاموش."""
    try:
        return max(0, int(float((await db.get_setting("stars_rate", "0") or "0").replace(",", ""))))
    except ValueError:
        return 0


async def enabled(db: "Database") -> bool:
    return await rate(db) > 0


def stars_for(toman: int, r: int) -> int:
    return max(1, math.ceil(toman / r))


def payload_of(inv: dict) -> str:
    return f"st:{inv['id']}"


async def create(db: "Database", user: dict, toman: int, source: str) -> dict:
    r = await rate(db)
    if not r:
        return {"ok": False, "error": OFF}
    min_c = await charge_svc.min_charge(db)
    if toman < min_c:
        return {"ok": False, "error": TOO_SMALL, "min": min_c}
    stars = stars_for(toman, r)
    if toman > charge_svc.MAX_CHARGE or stars > MAX_STARS:
        return {"ok": False, "error": TOO_LARGE, "max": MAX_STARS * r}
    inv_id = await db.create_stars_invoice(user_id=user["id"], toman=toman, stars=stars, source=source)
    return {"ok": True, "invoice": await db.get_stars_invoice(inv_id)}


def _invoice_args(inv: dict) -> dict:
    from aiogram.types import LabeledPrice

    title = i18n.t("شارژ کیف پول")
    return {
        "title": title[:32],
        "description": i18n.t("{amount} تومان به کیف پول عبور اضافه می شود.", amount=f"{inv['toman']:,}")[:255],
        "payload": payload_of(inv),
        "currency": CURRENCY,
        "prices": [LabeledPrice(label=title[:32], amount=int(inv["stars"]))],
    }


async def invoice_link(bot, inv: dict) -> str:  # noqa: ANN001
    """لینک فاکتور برای openInvoice مینی اپ."""
    return await bot.create_invoice_link(**_invoice_args(inv))


async def send_invoice(bot, chat_id: int, inv: dict) -> None:  # noqa: ANN001
    await bot.send_invoice(chat_id=chat_id, **_invoice_args(inv))


async def _find(db: "Database", payload: str, telegram_id: int, total: int, currency: str) -> dict | None:
    """فاکتوری که این پرداخت برایش است، اگر همه چیز با هم بخواند."""
    if currency != CURRENCY or not (payload or "").startswith("st:"):
        return None
    try:
        inv = await db.get_stars_invoice(int(payload[3:]))
    except ValueError:
        return None
    if not inv or int(inv["stars"]) != int(total):
        return None
    user = await db.get_user(inv["user_id"])
    if not user or int(user["telegram_id"]) != int(telegram_id):
        return None
    return inv


async def check_pre_checkout(db: "Database", payload: str, telegram_id: int, total: int, currency: str) -> str:
    """پیش از کم شدن ستاره. خروجی خالی یعنی تایید، وگرنه متن خطا برای کاربر."""
    inv = await _find(db, payload, telegram_id, total, currency)
    if inv is None:
        return i18n.t("این فاکتور معتبر نیست. از کیف پول دوباره شروع کن.")
    if inv["status"] != "pending":
        return i18n.t("این فاکتور قبلا پرداخت شده.")
    return ""


async def settle(db: "Database", bot, *, payload: str, telegram_id: int, total: int,  # noqa: ANN001
                 currency: str, charge_id: str) -> dict | None:
    """پرداخت موفق: فاکتور بسته و کیف پول شارژ می شود. خروجی: فاکتور، یا None."""
    inv = await _find(db, payload, telegram_id, total, currency)
    if inv is None:
        log.error("پرداخت ستاره بدون فاکتور معتبر: payload=%r charge=%s", payload, charge_id)
        await _alert_admins(bot, f"⚠️ پرداخت ستاره بدون فاکتور معتبر\npayload: {esc(payload)}\ncharge: <code>{esc(charge_id)}</code>")
        return None
    if not await db.settle_stars_invoice(inv["id"], charge_id):
        return None
    txn_id = await db.insert_transaction(
        user_id=inv["user_id"], type_="charge", amount=int(inv["toman"]),
        status="approved", idem_key=f"stars:{inv['id']}",
    )
    if txn_id is None:
        log.error("تراکنش شارژ ستاره تکراری بود invoice=%s", inv["id"])
        return None
    if not await db.atomic_credit(inv["user_id"], int(inv["toman"])):
        log.error("شارژ ستاره به موجودی اضافه نشد invoice=%s", inv["id"])
    await db.set_stars_txn(inv["id"], txn_id)
    user = await db.get_user(inv["user_id"])
    log.info("شارژ ستاره: %s ⭐ -> %s تومان کاربر %s", inv["stars"], inv["toman"], inv["user_id"])
    with i18n.using("fa"):
        body = texts.ADMIN_STARS_IN.format(
            name=esc(user.get("first_name") or "-"), telegram_id=user["telegram_id"],
            stars=inv["stars"], amount=f"{inv['toman']:,}", charge=esc(charge_id),
        )
    await _alert_admins(bot, body)
    return {**inv, "status": "paid", "balance": int(user["balance"])}


async def _alert_admins(bot, body: str) -> None:  # noqa: ANN001
    if bot is None:
        return
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(admin_id, body)
        except Exception:  # noqa: BLE001
            log.warning("گزارش ستاره به ادمین %s نرسید", admin_id)


def public(inv: dict) -> dict:
    return {"id": inv["id"], "toman": inv["toman"], "stars": inv["stars"], "status": inv["status"]}
