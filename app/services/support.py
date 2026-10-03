"""تیکت از مینی اپ — مستقل از رابط.

ربات پیام کاربر را با copy_to برای ادمین کپی می کند؛ مینی اپ پیام تلگرامی
ندارد، پس متن با send_message فرستاده می شود. بقیه دقیقا مثل ربات:
سربرگ «تیکت جدید / پیام تازه»، کد پیگیری، و save_support_link روی هر دو
پیام تا ریپلای ادمین به همان کاربر برسد و در همان رشته ثبت شود.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db import Database

log = logging.getLogger("obour.support")
MAX_BODY = 2000


async def send(bot, db: "Database", user: dict, body: str, *, via: str = "mini",  # noqa: ANN001
               photo: str | None = None) -> dict:
    """via: mini (مینی اپ) | ai (ارجاع از دستیار هوشمند). photo: file_id اسکرین شات."""
    from app import keyboards, texts
    from app.config import config
    from app.utils import esc

    body = (body or "").strip()
    if not body:
        return {"ok": False, "error": "empty"}
    body = body[:MAX_BODY]

    _, thread_id, is_new = await db.add_ticket(user["id"], "in", body=body)
    code = await db.ticket_code(thread_id)

    title = "💬 <b>تیکت جدید</b>" if is_new else "↩️ <b>پیام تازه در تیکت باز</b>"
    source = "🤖 <i>دستیار هوشمند</i>" if via == "ai" else "📱 <i>مینی اپ</i>"
    head = (f"{title} · {source}\n\n"
            f"👤 {esc(user.get('first_name') or '-')} (@{esc(user.get('username') or '-')})\n"
            f"🆔 <code>{user['telegram_id']}</code>"
            + (f"\n🎫 <code>{code}</code>" if code else "") + texts.ADMIN_REPLY_HINT)

    delivered = 0
    for admin_id in config.admin_ids:
        try:
            h = await bot.send_message(admin_id, head, reply_markup=keyboards.ticket_admin_kb(user["telegram_id"]))
            m = await bot.send_message(admin_id, esc(body), reply_to_message_id=h.message_id)
            if photo:
                try:
                    p = await bot.send_photo(admin_id, photo, reply_to_message_id=h.message_id)
                    await db.save_support_link(admin_id, p.message_id, user["telegram_id"])
                except Exception:  # noqa: BLE001
                    log.info("اسکرین شات دستیار به ادمین نرسید", exc_info=True)
            await db.save_support_link(admin_id, h.message_id, user["telegram_id"])
            await db.save_support_link(admin_id, m.message_id, user["telegram_id"])
            delivered += 1
        except Exception:  # noqa: BLE001
            log.warning("تیکت مینی اپ به ادمین %s نرسید", admin_id, exc_info=True)
    return {"ok": True, "thread_id": thread_id, "code": code, "is_new": is_new, "delivered": delivered}
