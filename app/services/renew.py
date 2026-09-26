"""تمدید یک سرویس با همان پلن قبلی — مستقل از رابط.

ربات (handlers/services.py) و مینی اپ هر دو از همین تابع رد می شوند.
ترتیب امن همان ترتیب قبلی ربات است:

  ۱. تراکنش «در انتظار» با کلید یکتا (ضد دابل کلیک)
  ۲. وضعیت فعلی سرویس روی پنل خوانده می شود (برای برگشت امن)
  ۳. تمدید روی پنل؛ اگر جواب مبهم بود، از خود پنل پرسیده می شود که
     واقعا اعمال شده یا نه
  ۴. کسر اتمیک موجودی؛ اگر نشد، تمدید روی پنل برگردانده می شود
  ۵. ثبت انقضای تازه و پاک شدن هشدارهای دوره قبل
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.config import config
from app.panel import PanelAmbiguous, PanelError, PanelSafeError, gb_bytes
from app.utils import after_days, renew_days

if TYPE_CHECKING:
    from app.db import Database
    from app.panel import Panel

log = logging.getLogger("obour.renew")

NOT_RENEWABLE = "not_renewable"   # سرویس دلخواه یا تست؛ پلنی پشتش نیست
PLAN_GONE = "plan_gone"
PANEL_BUSY = "panel_busy"
LOCKED = "locked"
DUPLICATE = "duplicate"
NOT_ON_PANEL = "not_on_panel"
PANEL_ERROR = "panel_error"
INSUFFICIENT = "insufficient"


@dataclass
class RenewResult:
    ok: bool
    error: str = ""
    txn_id: int | None = None
    price: int = 0
    days: int = 0
    expire_at: str = ""
    balance: int = 0


def _expire_num(panel_user) -> float:  # noqa: ANN001
    """تاریخ انقضای کاربر پنل به عدد (نوعش بین نسخه های پنل فرق می کند)."""
    value = getattr(panel_user, "expire", None)
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        return value.timestamp()
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return 0.0


async def plan_of(db: "Database", service: dict) -> tuple[dict | None, str]:
    """پلنی که این سرویس با آن تمدید می شود، یا (None، علت)."""
    if not service.get("plan_id"):
        return None, NOT_RENEWABLE
    plan = await db.get_plan(service["plan_id"])
    if not plan or not plan["is_active"]:
        return None, PLAN_GONE
    return plan, ""


def total_days(service: dict, plan: dict) -> int:
    return renew_days(service["expire_at"], plan["duration_days"], config.renew_keep_remaining)


async def renew(db: "Database", panel: "Panel | None", user: dict, service: dict, *, idem: str) -> RenewResult:
    """تمدید با قفل پرداخت کاربر."""
    plan, err = await plan_of(db, service)
    if plan is None:
        return RenewResult(False, err)
    if panel is None:
        return RenewResult(False, PANEL_BUSY)
    lock = f"pay:{user['id']}"
    if not await db.acquire_lock(lock):
        return RenewResult(False, LOCKED)
    try:
        return await run(db, panel, user, service, plan, idem=idem)
    finally:
        await db.release_lock(lock)


async def run(db: "Database", panel: "Panel", user: dict, service: dict, plan: dict, *, idem: str) -> RenewResult:
    """بدنه تمدید؛ فرض بر این است که قفل گرفته شده."""
    price = int(plan["price"])
    txn_id = await db.insert_transaction(user["id"], "purchase", -price, idem_key=idem)
    if txn_id is None:
        return RenewResult(False, DUPLICATE)

    try:
        before = await panel.get_user(service["panel_username"])
    except PanelError:
        await db.fail_transaction(txn_id, "خواندن وضعیت پنل ناموفق")
        return RenewResult(False, PANEL_ERROR, txn_id)
    if before is None:
        # سرویس روی پنل نیست. تمدید بی معنی است و نباید پول کسر شود.
        await db.fail_transaction(txn_id, "سرویس روی پنل پیدا نشد")
        log.error("renew: panel user %s not found", service["panel_username"])
        return RenewResult(False, NOT_ON_PANEL, txn_id)

    days = total_days(service, plan)
    before_expire = _expire_num(before)

    try:
        await panel.renew(service["panel_username"], gb_bytes(plan["data_gb"]), days)
    except PanelSafeError as exc:
        await db.fail_transaction(txn_id, f"panel rejected: {exc}")
        return RenewResult(False, PANEL_ERROR, txn_id)
    except PanelAmbiguous as exc:
        # شاید تمدید انجام شده باشد. اگر بی بررسی لغو کنیم، کاربر سرویس
        # تمدید شده رایگان می گیرد.
        log.error("renew AMBIGUOUS for %s", service["panel_username"], exc_info=True)
        try:
            after = await panel.get_user(service["panel_username"])
        except Exception:  # noqa: BLE001
            after = None
        if not (after is not None and _expire_num(after) > before_expire + 60):
            await db.fail_transaction(txn_id, f"panel ambiguous, not applied: {exc}")
            return RenewResult(False, PANEL_ERROR, txn_id)

    if not await db.atomic_debit(user["id"], price):
        reverted = await panel.revert_renew(
            service["panel_username"], before.data_limit, getattr(before, "expire", None)
        )
        if not reverted:
            log.error("برگشت تمدید ناموفق - سرویس %s تمدید شد ولی پول کسر نشد", service["panel_username"])
        await db.fail_transaction(txn_id, "موجودی کافی نبود")
        return RenewResult(False, INSUFFICIENT, txn_id, price)

    expire = after_days(days).isoformat(timespec="seconds")
    await db.update_service_expire(int(service["id"]), expire)
    # هشدارهای حجم و انقضا برای دوره جدید باید دوباره ارسال شوند
    await db.reset_service_warnings(int(service["id"]))
    if not await db.approve_purchase(txn_id):
        log.error("تراکنش تمدید %s در حالت pending نبود", txn_id)
    fresh = await db.get_user(user["id"])
    return RenewResult(True, "", txn_id, price, days, expire, int(fresh["balance"]) if fresh else 0)
