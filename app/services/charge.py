"""شارژ کیف پول — مستقل از رابط.

همان ترتیب ربات (handlers/wallet.py):
  ۱. مبلغ یکتا رزرو می شود (سه رقم آخر تصادفی، ۳۰ دقیقه اعتبار) تا ادمین
     از روی رسید بفهمد پرداخت مال کیست
  ۲. تراکنش شارژ «در انتظار» ثبت می شود
  ۳. کاربر رسید را می فرستد؛ برای ادمین ها با همان کیبورد تایید/رد ربات
     فرستاده می شود

تایید و افزودن پول به موجودی عوض نشده: همان دکمه ادمین در ربات. این
فایل هیچ پولی جابه جا نمی کند، فقط درخواست می سازد.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db import Database

log = logging.getLogger("obour.charge")

PRESETS = (50_000, 100_000, 200_000)
MAX_CHARGE = 50_000_000       # سقف منطقی؛ جلوی عدد اشتباه (یک صفر اضافه) را می گیرد
MAX_RECEIPT = 3 * 1024 * 1024

CARD_NOT_SET = "card_not_set"
TOO_SMALL = "too_small"
TOO_LARGE = "too_large"
AMOUNT_BUSY = "amount_busy"
NOT_OPEN = "not_open"
BAD_IMAGE = "bad_image"
NO_ADMIN = "no_admin"
ALREADY_SENT = "already_sent"


async def card(db: "Database") -> dict:
    return {
        "number": await db.get_setting("card_number", "") or "",
        "holder": await db.get_setting("card_holder", "") or "",
        "bank": await db.get_setting("bank_name", "") or "",
    }


async def min_charge(db: "Database") -> int:
    try:
        return int(await db.get_setting("min_charge", "50000"))
    except (TypeError, ValueError):
        return 50_000


async def open_request(db: "Database", user: dict) -> dict | None:
    """آخرین درخواست شارژ باز بدون رسید، اگر هنوز در مهلت است.

    کاربری که مینی اپ را وسط پرداخت بسته، با باز کردن دوباره باید همان
    مبلغ یکتا را ببیند، نه اینکه یک مبلغ تازه رزرو شود و اولی بلاتکلیف
    بماند.
    """
    row = await db.fetchone(
        """SELECT id, amount, created_at FROM transactions
           WHERE user_id = ? AND type = 'charge' AND status = 'pending'
             AND (receipt_file_id IS NULL OR receipt_file_id = '')
           ORDER BY id DESC LIMIT 1""",
        (user["id"],),
    )
    if not row:
        return None
    row = dict(row)
    # مبلغ باید هنوز برای همین کاربر رزرو باشد
    owner = await db.find_by_amount(int(row["amount"]))
    if not owner or owner["user_id"] != user["id"]:
        return None
    return row


async def start(db: "Database", user: dict, amount: int) -> dict:
    """رزرو مبلغ یکتا و ثبت درخواست. خروجی: {ok, error?, txn_id, amount}."""
    c = await card(db)
    if not c["number"]:
        return {"ok": False, "error": CARD_NOT_SET}
    lo = await min_charge(db)
    if amount < lo:
        return {"ok": False, "error": TOO_SMALL, "min": lo}
    if amount > MAX_CHARGE:
        return {"ok": False, "error": TOO_LARGE}

    # درخواست باز قبلی را دوباره استفاده کن، مگر مبلغش فرق دارد
    prev = await open_request(db, user)
    if prev and abs(int(prev["amount"]) - amount) < 1000:
        return {"ok": True, "txn_id": prev["id"], "amount": int(prev["amount"]), "resumed": True}

    exact = await db.reserve_amount(user["id"], amount)
    if exact is None:
        return {"ok": False, "error": AMOUNT_BUSY}
    txn_id = await db.insert_transaction(
        user_id=user["id"], type_="charge", amount=exact, status="pending",
        idem_key=f"charge:{user['id']}:{exact}:{datetime.now().isoformat(timespec='seconds')}",
    )
    if txn_id is None:
        await db.release_amount(exact)
        return {"ok": False, "error": AMOUNT_BUSY}
    return {"ok": True, "txn_id": txn_id, "amount": exact, "resumed": False}


def _image_kind(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


async def attach_receipt(bot, db: "Database", user: dict, txn_id: int, image: bytes) -> dict:  # noqa: ANN001
    """رسید را به تراکنش می چسباند و برای ادمین ها می فرستد."""
    from aiogram.types import BufferedInputFile

    from app import keyboards, texts
    from app.config import config
    from app.utils import esc

    txn = await db.get_transaction(txn_id)
    # تراکنش باید مال همین کاربر و هنوز باز باشد - همان بررسی ربات
    if not txn or txn["user_id"] != user["id"] or txn["status"] != "pending" or txn["type"] != "charge":
        return {"ok": False, "error": NOT_OPEN}
    # رسید دوم روی همان تراکنش دوباره برای ادمین ها نمی رود. ربات این را
    # با پاک کردن وضعیت گفتگو بعد از رسید اول می بندد؛ مینی اپ وضعیت
    # گفتگو ندارد، پس صریح بسته می شود.
    if txn.get("receipt_file_id"):
        return {"ok": False, "error": ALREADY_SENT}
    if not image or len(image) > MAX_RECEIPT or not _image_kind(image):
        return {"ok": False, "error": BAD_IMAGE}
    if not config.admin_ids:
        return {"ok": False, "error": NO_ADMIN}

    fresh = await db.get_user(user["id"]) or user
    caption = texts.ADMIN_CHARGE_REQ.format(
        name=esc(fresh.get("first_name") or "-"), username=esc(fresh.get("username") or "-"),
        telegram_id=fresh["telegram_id"], amount=f"{txn['amount']:,}", balance=f"{fresh['balance']:,}",
    ) + "\n\n📱 <i>از مینی اپ</i>"

    # عکس یک بار آپلود می شود؛ برای ادمین های بعدی file_id همان پیام
    file_id: str | None = None
    sent_any = False
    for admin_id in config.admin_ids:
        try:
            photo = file_id or BufferedInputFile(image, filename=f"receipt.{_image_kind(image)}")
            msg = await bot.send_photo(admin_id, photo=photo, caption=caption,
                                       reply_markup=keyboards.admin_charge_kb(txn_id))
            sent_any = True
            if not file_id and msg.photo:
                file_id = msg.photo[-1].file_id
        except Exception:  # noqa: BLE001
            log.warning("رسید به ادمین %s نرسید", admin_id, exc_info=True)
    if not sent_any or not file_id:
        return {"ok": False, "error": NO_ADMIN}

    await db.set_receipt(txn_id, file_id)
    code = (await db.get_transaction(txn_id) or {}).get("code")
    return {"ok": True, "code": code, "amount": int(txn["amount"])}
