"""بررسی رسید کارت به کارت و اعلام به ادمین ها؛ مشترک ربات و مینی اپ.

ترتیب:
۱. تکراری بودن، قطعی و بدون هوش مصنوعی: همان کد پیگیری یا همان عکس
   (هش) روی شارژ دیگری که در انتظار یا تایید شده است.
۲. اگر «بررسی خودکار رسید» روشن باشد: دو بررسی مستقل هوش مصنوعی
   (assistant.receipt_verdict). فقط اگر همه موارد دقیقا مطابق باشد تایید،
   فقط اگر ایراد قطعی باشد رد؛ هر شکی = تصمیم با ادمین.
۳. پیام به ادمین ها: عکس + مشخصات + گزارش. اگر تصمیم با ادمین است،
   دکمه های تایید/رد/تکراری هم می آیند.

هیچ خطایی (قطعی وب سرویس، عکس ناخوانا) به تایید نمی رسد؛ بدترین حالت
همان بررسی دستی قدیمی است.
"""
from __future__ import annotations

import hashlib
import html
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db import Database

log = logging.getLogger("obour.receipts")

AUTO_FEATURE = "ai_receipt_auto"
SYSTEM_ADMIN = 0  # decided_by برای تصمیم های خودکار


def auto_on() -> bool:
    from app import features
    from app.services import assistant

    return assistant.configured() and features.is_on(AUTO_FEATURE)


async def _download(bot, file_id: str) -> bytes:  # noqa: ANN001
    import io

    f = await bot.get_file(file_id)
    buf = await bot.download_file(f.file_path, destination=io.BytesIO())
    return buf.getvalue() if hasattr(buf, "getvalue") else bytes(buf)


async def process(bot, db: "Database", txn_id: int, *, image: bytes | None = None,  # noqa: ANN001
                  source: str = "bot", use_ai: bool = True) -> dict:
    """بررسی و اعلام. {"ok", "decision": approved|rejected|duplicate|manual, "file_id"}"""
    from aiogram.types import BufferedInputFile

    from app import keyboards, texts
    from app.config import config
    from app.services import admin_ops, assistant
    from app.services.assistant import AIError
    from app.utils import esc

    txn = await db.get_transaction(txn_id)
    if not txn or txn["type"] != "charge" or txn["status"] != "pending":
        return {"ok": False, "decision": "closed"}
    if not await db.claim_review(txn_id):
        return {"ok": True, "decision": "already"}

    file_id = txn.get("receipt_file_id")
    if image is None and file_id:
        try:
            image = await _download(bot, file_id)
        except Exception:  # noqa: BLE001
            log.warning("دانلود رسید %s نشد", txn_id, exc_info=True)
    digest = hashlib.sha256(image).hexdigest() if image else ""
    if digest:
        await db.set_receipt_meta(txn_id, receipt_hash=digest)
    ref = assistant.clean_ref(txn.get("ref_code"))

    # ── ۱. تکراری (قطعی)
    dup_lines: list[str] = []
    other = await db.charge_with_ref(ref, txn_id)
    if other:
        dup_lines.append(f"⚠️ کد پیگیری <code>{ref}</code> قبلا روی شارژ {html.escape(other.get('code') or '#' + str(other['id']))} "
                         f"({'تایید شده' if other['status'] == 'approved' else 'در انتظار'}) ثبت شده")
    same_img = await db.charge_with_hash(digest, txn_id)
    if same_img:
        dup_lines.append(f"⚠️ همین عکس قبلا برای شارژ {html.escape(same_img.get('code') or '#' + str(same_img['id']))} فرستاده شده")

    auto = use_ai and auto_on()
    decision, verdict, ai_err = "manual", None, ""
    if dup_lines and auto:
        decision = "duplicate"
    elif auto and image:
        try:
            verdict = await assistant.receipt_verdict(db, txn, image, ref=ref, need_ref=source != "mini")
            # کدی که هوش مصنوعی روی رسید دیده، روی شارژ دیگری هست؟
            for r in {assistant.clean_ref(x) for x in (verdict["data"].get("ref_codes") or [])} - {"", ref}:
                o = await db.charge_with_ref(r, txn_id)
                if o:
                    dup_lines.append(f"⚠️ کد پیگیری روی رسید (<code>{r}</code>) متعلق به شارژ {html.escape(o.get('code') or '#' + str(o['id']))} است")
            read = sorted({assistant.clean_ref(x) for x in (verdict["data"].get("ref_codes") or [])} - {""})
            if not ref and read:
                # کد خوانده شده ثبت می شود تا رسیدهای بعدی با آن سنجیده شوند
                await db.set_receipt_meta(txn_id, ref_code=read[0])
            if dup_lines:
                decision = "duplicate"
            elif verdict["decision"] == "approve":
                decision = "approved"
            elif verdict["decision"] == "reject":
                decision = "rejected"
        except AIError as exc:
            ai_err = f"{exc} ({exc.code})"
        except Exception as exc:  # noqa: BLE001
            log.warning("بررسی خودکار رسید %s شکست خورد", txn_id, exc_info=True)
            ai_err = type(exc).__name__
    elif auto and not image:
        ai_err = "عکس رسید خوانده نشد"

    # ── ۲. اعمال تصمیم خودکار
    applied = None
    if decision == "approved":
        applied = await admin_ops.approve_charge(bot, db, txn_id, SYSTEM_ADMIN)
    elif decision == "rejected":
        reasons = texts.__dict__["REJECT_REASONS"]
        applied = await admin_ops.reject_charge(bot, db, txn_id, SYSTEM_ADMIN, reasons.get(verdict["reason"]) or reasons["invalid"])
    elif decision == "duplicate":
        applied = await admin_ops.duplicate_charge(bot, db, txn_id, SYSTEM_ADMIN)
    if applied is not None and not applied.get("ok"):
        decision = "manual"  # همزمان ادمین تصمیم گرفته بود
    log.info("رسید %s: %s%s", txn_id, decision, f" (خطای هوش مصنوعی: {ai_err})" if ai_err else "")

    # ── ۳. پیام به ادمین ها
    user = await db.get_user(txn["user_id"]) or {}
    caption = texts.ADMIN_CHARGE_REQ.format(
        name=esc(user.get("first_name") or "-"), username=esc(user.get("username") or "-"),
        telegram_id=user.get("telegram_id", "-"), amount=f"{txn['amount']:,}", balance=f"{int(user.get('balance') or 0):,}",
    )
    caption += f"\n\n🔖 کد پیگیری کاربر: <code>{ref}</code>" if ref else "\n\n🔖 کد پیگیری: <i>نفرستاده</i>"
    caption += f"\n💵 مبلغ به ریال: <code>{int(txn['amount']) * 10:,}</code>"
    if source == "mini":
        caption += "\n📱 <i>از مینی اپ</i>"
    head = {
        "approved": "🤖 <b>تایید خودکار شد</b> و کیف پول شارژ شد",
        "rejected": "🤖 <b>رد خودکار شد</b>",
        "duplicate": "🤖 <b>رسید تکراری؛ خودکار رد شد</b>",
    }.get(decision, "")
    if head:
        caption = head + "\n\n" + caption
    report_parts = list(dup_lines)
    if verdict:
        report_parts.append(assistant.receipt_html(verdict))
    if ai_err:
        report_parts.append(f"❔ بررسی خودکار انجام نشد: {html.escape(ai_err)} — تصمیم با شما")
    report = "\n\n".join(report_parts)
    markup = keyboards.admin_charge_kb(txn_id) if decision == "manual" else None

    sent_any = False
    for admin_id in config.admin_ids:
        try:
            photo = file_id or BufferedInputFile(image or b"", filename="receipt.jpg")
            msg = await bot.send_photo(admin_id, photo=photo, caption=caption[:1024], reply_markup=markup)
            sent_any = True
            if not file_id and msg.photo:
                file_id = msg.photo[-1].file_id
                await db.set_receipt(txn_id, file_id)
            if report:
                await bot.send_message(admin_id, report[:4000], reply_to_message_id=msg.message_id)
        except Exception:  # noqa: BLE001
            log.warning("رسید %s به ادمین %s نرسید", txn_id, admin_id, exc_info=True)
    return {"ok": True, "decision": decision, "file_id": file_id, "sent": sent_any}


async def process_late(bot, db: "Database", *, use_ai: bool) -> int:  # noqa: ANN001
    """رسیدهایی که کاربر بعد از عکس، کد پیگیری را نفرستاد."""
    n = 0
    for t in await db.receipts_unreviewed(older_than_minutes=10, limit=5 if use_ai else 20):
        r = await process(bot, db, t["id"], source="late", use_ai=use_ai)
        n += r.get("decision") not in ("already", "closed")
    return n
