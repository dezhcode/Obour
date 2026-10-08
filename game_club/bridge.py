"""پل Game Club به عبور. تنها جایی که به دیتابیس و پنل عبور دست می زند.

هر دو سرویس روی یک پروسه و یک event loop اند، پس پل یک فراخوانی مستقیم
تابع است، نه درخواست شبکه. در عبور فقط از توابع اتمیک خود عبور استفاده
می شود (atomic_debit / atomic_credit / insert_transaction با idem_key و
سرویس خرید purchase)، تا قواعد مالی عبور یک جا بماند.

سه کار:
  charge   تومان از کیف پول عبور کم و امتیاز در Game Club اضافه می شود
  buy      امتیاز کم، همان مبلغ به کیف عبور و بلافاصله خرید پلن
  transfer امتیاز کم و تومان به کیف پول عبور اضافه می شود
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from .config import gc
from .db import GCDatabase
from .service import GCError, spend

if TYPE_CHECKING:
    from app.db import Database

log = logging.getLogger("gameclub.bridge")


def points_for(toman: int) -> int:
    return max(1, math.ceil(toman / gc.point_toman))


async def obour_account(odb: "Database", tg: int) -> dict | None:
    u = await odb.get_user_by_tg(tg)
    if not u or u.get("is_blocked"):
        return None
    return u


async def charge(gdb: GCDatabase, odb: "Database", tg: int, points: int, idem: str) -> dict:
    """شارژ امتیاز از کیف پول عبور. همان idem دوباره = همان نتیجه."""
    if points not in gc.charge_packs:
        raise GCError("bad_pack")
    toman = points * gc.point_toman
    key = "charge:" + idem
    lid = await gdb.add_ledger(tg, "charge", points, "شارژ از کیف پول عبور", "obour", key, status="pending")
    if lid is None:
        row = await gdb.ledger_by_idem(key)
        return {"ok": bool(row and row["status"] == "done"), "points": points}
    user = await obour_account(odb, tg)
    if not user:
        await gdb.set_ledger_status(lid, "failed")
        raise GCError("no_obour")
    lock = f"pay:{user['id']}"
    if not await odb.acquire_lock(lock):
        await gdb.set_ledger_status(lid, "failed")
        raise GCError("busy")
    try:
        if not await odb.atomic_debit(user["id"], toman):
            await gdb.set_ledger_status(lid, "failed")
            raise GCError("obour_insufficient", balance=int(user["balance"]), need=toman)
        await odb.insert_transaction(user["id"], "gameclub_charge", -toman, status="approved", idem_key="gc:" + idem)
    finally:
        await odb.release_lock(lock)
    await gdb.player(tg)
    await gdb.credit(tg, points)
    await gdb.set_ledger_status(lid, "done")
    log.info("شارژ Game Club: کاربر %s، %s امتیاز (%s تومان)", tg, points, toman)
    return {"ok": True, "points": points, "toman": toman}


async def plans(odb: "Database") -> list[dict]:
    out = []
    for p in await odb.active_plans():
        price = int(p.get("price") or 0)
        if price <= 0:
            continue
        out.append({"id": p["id"], "title": p["title"], "gb": p.get("data_gb"), "days": p.get("duration_days"),
                    "price": price, "points": points_for(price)})
    return out


async def _to_obour_wallet(odb: "Database", user: dict, toman: int, idem: str) -> None:
    """تومان به کیف عبور؛ تراکنش idem دارد تا تکرار دو بار شارژ نکند."""
    txn = await odb.insert_transaction(user["id"], "gameclub_points", toman, status="approved", idem_key=idem)
    if txn is not None:
        await odb.atomic_credit(user["id"], toman)


async def transfer(gdb: GCDatabase, odb: "Database", tg: int, points: int, idem: str) -> dict:
    if points <= 0 or points > 1_000_000:
        raise GCError("bad_amount")
    user = await obour_account(odb, tg)
    if not user:
        raise GCError("no_obour")
    if not await spend(gdb, tg, points, "transfer", "انتقال به کیف پول عبور", "obour", "transfer:" + idem):
        raise GCError("insufficient")
    toman = points * gc.point_toman
    await _to_obour_wallet(odb, user, toman, "gct:" + idem)
    return {"ok": True, "points": points, "toman": toman}


async def buy(gdb: GCDatabase, odb: "Database", panel, bot, tg: int, plan_id: int, idem: str) -> dict:  # noqa: ANN001
    """خرید پلن عبور با امتیاز.

    ترتیب: امتیاز کم می شود، معادلش به کیف عبور می رود، و همان لحظه سرویس
    خرید عبور (با قفل و ترتیب امن خودش) پلن را می سازد. اگر ساخت پلن
    شکست بخورد پول گم نمی شود: در کیف پول عبور می ماند و کاربر خبر دارد.
    """
    from app.services import purchase as purchase_svc

    plan = await odb.get_plan(int(plan_id))
    if not plan or not plan.get("is_active"):
        raise GCError("plan_unavailable")
    user = await obour_account(odb, tg)
    if not user:
        raise GCError("no_obour")
    pts = points_for(int(plan["price"]))
    toman = pts * gc.point_toman
    # همان درخواست دوباره رسید (دابل کلیک، شبکه): نتیجه قبلی، بدون خرید دوم
    prev = await gdb.ledger_by_idem("shop:" + idem)
    if prev:
        return {"ok": prev["status"] == "done", "repeat": True, "title": plan["title"]}
    if not await spend(gdb, tg, pts, "shop", f"خرید: {plan['title']}"[:120], f"plan:{plan['id']}", "shop:" + idem):
        raise GCError("insufficient")
    await _to_obour_wallet(odb, user, toman, "gcp:" + idem)
    fresh = await odb.get_user(user["id"])
    res = await purchase_svc.purchase(odb, panel, fresh, plan, idem="gcbuy:" + idem)
    if not res.ok:
        log.warning("خرید Game Club ساخته نشد (%s)؛ %s تومان در کیف عبور کاربر %s ماند", res.error, toman, tg)
        return {"ok": False, "error": res.error, "credited": toman}
    await _deliver(bot, tg, res)
    return {"ok": True, "service_id": res.service_id, "title": plan["title"]}


async def _deliver(bot, tg: int, res) -> None:  # noqa: ANN001
    """تحویل در ربات عبور، همان قالب خرید خود عبور (QR + متن + دکمه ها)."""
    if bot is None:
        return
    try:
        from aiogram.types import BufferedInputFile

        from app import keyboards, texts
        from app.utils import esc, qr_png

        caption = texts.buy_success(sub_url=res.sub_url, balance=f"{res.balance_after:,}",
                                    name=esc(res.label) or f"سرویس {res.service_id}")
        kb = keyboards.service_detail_kb(res.service_id, res.sub_url)
        try:
            await bot.send_photo(tg, BufferedInputFile(qr_png(res.sub_url), filename="obour_sub.png"),
                                 caption=caption, reply_markup=kb)
        except Exception:  # noqa: BLE001
            await bot.send_message(tg, caption, reply_markup=kb, disable_web_page_preview=True)
    except Exception:  # noqa: BLE001
        log.warning("تحویل خرید Game Club در ربات عبور نشد", exc_info=True)
