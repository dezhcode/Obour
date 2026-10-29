"""پل AsoTas به عبور. تنها جایی که به دیتابیس عبور دست می زند.

هر دو سرویس روی یک پروسه و یک event loop اند، پس پل یک فراخوانی مستقیم
تابع است، نه درخواست شبکه. در عبور فقط از توابع اتمیک خود عبور استفاده
می شود (atomic_credit / insert_transaction با idem_key)، تا قواعد مالی عبور یک جا بماند.

از وقتی سکه پول داخل بازی است (و فقط با بازی یا خرید درون برنامه ای جمع می شود)، تنها کار پل
برگرداندن امتیازهای قدیمی (legacy_points، پول واقعی) به کیف پول عبور است (refund.py).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .db import GCDatabase

if TYPE_CHECKING:
    from app.db import Database

log = logging.getLogger("gameclub.bridge")


async def obour_account(odb: "Database", tg: int) -> dict | None:
    u = await odb.get_user_by_tg(tg)
    if not u or u.get("is_blocked"):
        return None
    return u


async def _to_obour_wallet(odb: "Database", user: dict, toman: int, idem: str) -> None:
    """تومان به کیف عبور؛ تراکنش idem دارد تا تکرار دو بار شارژ نکند."""
    txn = await odb.insert_transaction(user["id"], "gameclub_points", toman, status="approved", idem_key=idem)
    if txn is not None:
        await odb.atomic_credit(user["id"], toman)


async def refund_legacy(gdb: GCDatabase, odb: "Database", tg: int, rate: int) -> int | None:
    """همهٔ امتیاز قدیمی این بازیکن با نرخ rate تومان به کیف عبور؛ تومان برگشته (۰ اگر چیزی نبود).

    ترتیب: کم شدن legacy_points و ردیف دفتر pending در یک تراکنش ← واریز به عبور با idem همان ردیف ← done.
    اگر وسط کار قطع شد، finish_pending همان واریز را با همان idem دوباره می زند (عبور دو بار واریز نمی کند).
    None یعنی بازیکن حساب عبور ندارد (یا مسدود است) و امتیازش سر جایش ماند.
    """
    p = await gdb.get_player(tg) or {}
    pts = int(p.get("legacy_points") or 0)
    if pts <= 0:
        return 0
    user = await obour_account(odb, tg)
    if not user:
        return None
    n = await gdb.one("SELECT COUNT(*) AS n FROM ledger WHERE tg_id = ? AND kind = 'obour'", (tg,))
    idem = f"obour:{tg}:{int(n['n'] if n else 0) + 1}"
    toman = pts * rate
    lid = await gdb.take_legacy(tg, pts, f"برگشت {pts} امتیاز به کیف عبور ({toman} تومان)", str(toman), idem)
    if lid is None:
        return 0
    await _to_obour_wallet(odb, user, toman, "gcr:" + idem)
    await gdb.set_ledger_status(lid, "done")
    log.info("امتیاز قدیمی AsoTas برگشت: کاربر %s، %s امتیاز، %s تومان", tg, pts, toman)
    return toman


async def finish_pending(gdb: GCDatabase, odb: "Database") -> int:
    """برگشت هایی که وسط کار قطع شده اند (امتیاز کم شده ولی done نشده): واریز با همان idem و done."""
    done = 0
    for row in await gdb.all("SELECT * FROM ledger WHERE kind = 'obour' AND status = 'pending'"):
        user = await obour_account(odb, row["tg_id"])
        if not user or not str(row["ref"]).isdigit():
            continue
        await _to_obour_wallet(odb, user, int(row["ref"]), "gcr:" + row["idem"])
        await gdb.set_ledger_status(row["id"], "done")
        done += 1
    return done
