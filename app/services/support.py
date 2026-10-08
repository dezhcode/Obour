"""تیکت پشتیبانی — مستقل از رابط (مینی اپ، دستیار هوشمند، ربات).

مدل حرفه ای: هر تیکت موضوع، دسته، اولویت و «مورد مرتبط» (سرویس، سفارش یا
تراکنش) دارد و کاربر می تواند چند تیکت باز داشته باشد. پیام تازه به تیکتی
می چسبد که کاربر در آن است (thread_id)؛ ریپلای ادمین هم به همان تیکتی می رسد
که پیامش را دیده (support_links.thread_id).

ربات پیام کاربر را با copy_to برای ادمین کپی می کند؛ این جا پیام تلگرامی
نداریم، پس متن (و عکس) با send_message / send_photo فرستاده می شود.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db import Database

log = logging.getLogger("obour.support")
MAX_BODY = 2000
MAX_SUBJECT = 120
MAX_IMAGE = 5 * 1024 * 1024

# کلید -> (عنوان، آیکون مینی اپ)
CATEGORIES: dict[str, tuple[str, str]] = {
    "vpn": ("کانفیگ و اتصال", "globe"),
    "ai": ("اشتراک هوش مصنوعی", "spark"),
    "number": ("شماره مجازی", "phone"),
    "visa": ("ویزا کارت", "card"),
    "pay": ("پرداخت و کیف پول", "wallet"),
    "account": ("حساب کاربری", "user"),
    "other": ("سایر موارد", "chat"),
}
PRIORITIES: dict[str, str] = {"normal": "عادی", "high": "مهم", "urgent": "فوری"}
PRIORITY_MARK = {"normal": "", "high": "🟠 ", "urgent": "🔴 "}

# خطاها
EMPTY, NOT_FOUND, CLOSED, BAD_IMAGE = "empty", "not_found", "closed", "bad_image"


def clean_meta(subject: str | None, category: str | None, priority: str | None, related: str | None
               ) -> tuple[str | None, str | None, str | None, str | None]:
    subject = (subject or "").strip()[:MAX_SUBJECT] or None
    category = category if category in CATEGORIES else ("other" if subject else None)
    priority = priority if priority in PRIORITIES else ("normal" if subject else None)
    related = (related or "").strip()
    if related and not (related.split(":", 1)[0] in ("svc", "ai", "tx") and related.split(":", 1)[-1].isdigit()):
        related = ""
    return subject, category, priority, related or None


async def describe_related(db: "Database", user_id: int, related: str | None) -> dict | None:
    """«svc:12» / «ai:5» / «tx:34» -> {"kind", "id", "title", "sub"} فقط اگر مال همین کاربر باشد."""
    if not related or ":" not in related:
        return None
    kind, _, rid = related.partition(":")
    if not rid.isdigit():
        return None
    rid_i = int(rid)
    if kind == "svc":
        s = await db.fetchone("SELECT * FROM services WHERE id = ? AND user_id = ?", (rid_i, user_id))
        if s:
            s = dict(s)
            return {"kind": "svc", "id": rid_i, "title": (s.get("label") or "").strip() or f"سرویس {rid_i}",
                    "sub": "کانفیگ"}
    elif kind == "ai":
        o = await db.fetchone("SELECT * FROM ai_orders WHERE id = ? AND user_id = ?", (rid_i, user_id))
        if o:
            o = dict(o)
            return {"kind": "ai", "id": rid_i, "title": o.get("title") or o.get("product_name") or f"سفارش {rid_i}",
                    "sub": o.get("code") or "سفارش هوش مصنوعی"}
    elif kind == "tx":
        t = await db.fetchone("SELECT * FROM transactions WHERE id = ? AND user_id = ?", (rid_i, user_id))
        if t:
            t = dict(t)
            return {"kind": "tx", "id": rid_i, "title": f"{int(t.get('amount') or 0):,} تومان",
                    "sub": t.get("code") or f"تراکنش {rid_i}"}
    return None


def _image_kind(data: bytes) -> str | None:
    from app.services.charge import _image_kind as kind

    return kind(data)


async def send(bot, db: "Database", user: dict, body: str, *, via: str = "mini",  # noqa: ANN001
               photo: str | None = None, image: bytes | None = None, thread_id: int | None = None,
               subject: str | None = None, category: str | None = None,
               priority: str | None = None, related: str | None = None) -> dict:
    """پیام پشتیبانی.

    thread_id: پاسخ کاربر در یک تیکت مشخص. بدون آن، اگر موضوع داده شده باشد
    تیکت تازه ساخته می شود؛ وگرنه (دستیار هوشمند) به تیکت باز قبلی می چسبد.
    photo: file_id تلگرامی (اسکرین شات دستیار)؛ image: بایت های عکس از مینی اپ.
    """
    from aiogram.types import BufferedInputFile

    from app import keyboards, texts
    from app.config import config
    from app.utils import esc

    body = (body or "").strip()[:MAX_BODY]
    if image is not None and (not image or len(image) > MAX_IMAGE or not _image_kind(image)):
        return {"ok": False, "error": BAD_IMAGE}
    if not body and not image and not photo:
        return {"ok": False, "error": EMPTY}

    subject, category, priority, related = clean_meta(subject, category, priority, related)
    if thread_id:
        root = await db.thread_root(thread_id, user["id"])
        if not root:
            return {"ok": False, "error": NOT_FOUND}
        if (root.get("status") or "open") == "closed":
            return {"ok": False, "error": CLOSED}
        msg_id, thread_id, _ = await db.add_ticket(user["id"], "in", body=body or None, thread_id=thread_id)
        is_new = False
    elif subject:
        thread_id, _code = await db.create_thread(user["id"], body or None, subject=subject, category=category,
                                                  priority=priority, related=related, via=via)
        msg_id, is_new = thread_id, True
    else:
        msg_id, thread_id, is_new = await db.add_ticket(user["id"], "in", body=body or None)
        if is_new:
            await db.execute("UPDATE tickets SET via = ? WHERE id = ?", (via, thread_id))
    root = await db.thread_root(thread_id) or {}
    code = root.get("code") or await db.ticket_code(thread_id)

    title = "💬 <b>تیکت جدید</b>" if is_new else "↩️ <b>پیام تازه در تیکت</b>"
    source = {"ai": "🤖 <i>دستیار هوشمند</i>", "bot": "🤖 <i>ربات</i>"}.get(via, "📱 <i>مینی اپ</i>")
    meta = []
    if root.get("subject"):
        meta.append(f"📌 <b>{esc(root['subject'])}</b>")
    if root.get("category") in CATEGORIES:
        meta.append(f"🗂 {CATEGORIES[root['category']][0]}")
    if root.get("priority") in PRIORITIES:
        meta.append(f"{PRIORITY_MARK.get(root['priority']) or '⚪️ '}اولویت: {PRIORITIES[root['priority']]}")
    rel = await describe_related(db, user["id"], root.get("related"))
    if rel:
        meta.append(f"🔗 {esc(rel['sub'])} · {esc(rel['title'])}")
    head = (f"{title} · {source}\n\n"
            + ("\n".join(meta) + "\n\n" if meta else "")
            + f"👤 {esc(user.get('first_name') or '-')} (@{esc(user.get('username') or '-')})\n"
            f"🆔 <code>{user['telegram_id']}</code>"
            + (f"\n🎫 <code>{code}</code>" if code else "") + texts.ADMIN_REPLY_HINT)

    delivered = 0
    stored_photo = photo
    for admin_id in config.admin_ids:
        try:
            h = await bot.send_message(admin_id, head, reply_markup=keyboards.ticket_admin_kb(user["telegram_id"]))
            await db.save_support_link(admin_id, h.message_id, user["telegram_id"], thread_id)
            if body:
                m = await bot.send_message(admin_id, esc(body), reply_to_message_id=h.message_id)
                await db.save_support_link(admin_id, m.message_id, user["telegram_id"], thread_id)
            pic = stored_photo or (BufferedInputFile(image, filename="ticket.jpg") if image else None)
            if pic:
                try:
                    p = await bot.send_photo(admin_id, pic, reply_to_message_id=h.message_id)
                    await db.save_support_link(admin_id, p.message_id, user["telegram_id"], thread_id)
                    if not stored_photo and p.photo:
                        # یک بار آپلود؛ بقیه ادمین ها و نمایش در مینی اپ با همین file_id
                        stored_photo = p.photo[-1].file_id
                except Exception:  # noqa: BLE001
                    log.info("عکس تیکت به ادمین %s نرسید", admin_id, exc_info=True)
            delivered += 1
        except Exception:  # noqa: BLE001
            log.warning("تیکت به ادمین %s نرسید", admin_id, exc_info=True)
    if stored_photo:
        await db.execute("UPDATE tickets SET file_id = ? WHERE id = ?", (stored_photo, msg_id))
    return {"ok": True, "thread_id": thread_id, "code": code, "is_new": is_new, "delivered": delivered}


async def close(db: "Database", user: dict, thread_id: int) -> bool:
    return await db.close_ticket(thread_id, user["id"])
