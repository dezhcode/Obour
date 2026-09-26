"""فروش خدمات هوش مصنوعی از canboso — مستقل از رابط.

ترتیب خرید عمدی است، چون تحویل **برگشت ناپذیر** است:

    ۱. قفل کاربر
    ۲. محصول و قیمت تازه (بدون کش) از سرویس دهنده
    ۳. موجودی *ما* نزد سرویس دهنده بررسی می شود
    ۴. کسر اتمیک از کیف پول کاربر
    ۵. سفارش pending با Idempotency-Key و خود درخواست ثبت می شود ← قبل از تماس
    ۶. خرید
    ۷. موفق → تحویل (یا «در انتظار فروشنده» برای محصولات slot)
       قطعا انجام نشد → پول برمی گردد
       مبهم → unknown؛ پول برنمی گردد و ادمین با «بررسی دوباره» همان
       درخواست را با همان کلید می فرستد: اگر انجام شده بود همان پاسخ
       برمی گردد، وگرنه همان لحظه انجام می شود. پس هیچ وقت دوبار خرید
       نمی شود و پول هیچ کس گم نمی شود.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import TYPE_CHECKING

from app import i18n, pricing, texts
from app.canboso import Canboso, CanbosoError, CanbosoNoFunds, CanbosoUnknown, accounts_of, is_waiting
from app.config import config
from app.utils import esc

if TYPE_CHECKING:
    from app.db import Database

log = logging.getLogger("obour.ai")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# نتیجه خرید
DELIVERED = "delivered"
PROCESSING = "processing"
UNKNOWN = "unknown"
FAILED = "failed"
NO_FUNDS = "no_funds"
UNAVAILABLE = "unavailable"
INSUFFICIENT = "insufficient"
LOCKED = "locked"
NOT_CONFIGURED = "not_configured"
BAD_INPUT = "bad_input"


async def api_key(db: "Database") -> str:
    """کلید از .env (CANBOSO_API_KEY)، وگرنه همان که ادمین در پنل گذاشته."""
    return config.canboso_api_key or (await db.get_setting("ai_api_key", "") or "").strip()


async def client(db: "Database") -> Canboso:
    return Canboso(await api_key(db))


# ═══════════════════ محصول ═══════════════════


def requirements(p: dict) -> dict:
    req = p.get("purchaseRequirements") or {}
    months = [int(m) for m in (req.get("allowedMonths") or []) if str(m).isdigit()]
    return {
        "email": bool(req.get("customerEmail")) or p.get("productType") == "slot",
        "months": months if req.get("slotMonths") else [],
    }


def stock_of(p: dict) -> int | None:
    """None یعنی سرویس دهنده عددی نداده (محدودیت اعلام نشده)."""
    av = (p.get("availability") or {}).get("available")
    try:
        return None if av is None else int(av)
    except (TypeError, ValueError):
        return None


def available(p: dict) -> bool:
    s = stock_of(p)
    price = (p.get("price") or {}).get("amount")
    return price not in (None, "") and (s is None or s > 0)


def cost_of(p: dict, months: int | None = None) -> float:
    """هزینه ما به ارز کیف پول. برای اشتراک ماهانه، قیمت × تعداد ماه."""
    amount = float((p.get("price") or {}).get("amount") or 0)
    return amount * (months or 1)


def currency_of(p: dict, wallet: str) -> str:
    return str((p.get("price") or {}).get("currency") or wallet or "USD").upper()


# ═══════════════════ نمایش و موجودی ═══════════════════

VISIBLE_KEY = "ai_products_on"


async def enabled_ids(db: "Database") -> set[str] | None:
    """محصولاتی که ادمین روشن کرده. None یعنی هنوز انتخابی نشده: همه روشن.

    وقتی ادمین اولین بار چیزی را خاموش کند، فهرست صریح می شود و از آن به
    بعد محصول تازه سرویس دهنده تا ادمین روشنش نکند دیده نمی شود.
    """
    raw = await db.get_setting(VISIBLE_KEY, "")
    if not raw:
        return None
    try:
        return {str(x) for x in json.loads(raw)}
    except (TypeError, ValueError):
        return None


async def set_visible(db: "Database", pid: str, on: bool, all_ids: list[str]) -> None:
    ids = await enabled_ids(db)
    ids = set(all_ids) if ids is None else ids
    (ids.add if on else ids.discard)(str(pid))
    await db.set_setting(VISIBLE_KEY, json.dumps(sorted(ids)))


async def set_all_visible(db: "Database", ids: list[str]) -> None:
    await db.set_setting(VISIBLE_KEY, json.dumps(sorted(str(x) for x in ids)))


def wallet_units(bal: dict | None, cost: float, currency: str) -> int | None:
    """با موجودی کیف پول ما نزد سرویس دهنده چند عدد از این هزینه خریدنی است.

    None یعنی نمی دانیم (موجودی خوانده نشد یا ارزش فرق دارد)؛ آن وقت سقفی
    نمی گذاریم و بررسی تازه قبل از خرید، جلوی خرید بی پول را می گیرد.
    """
    if bal is None or cost <= 0 or (bal.get("currency") and bal["currency"] != currency):
        return None
    return max(0, int(bal["balance"] // cost))


def effective_stock(api_stock: int | None, wallet: int | None) -> int | None:
    """موجودی نمایشی = کمترینِ موجودی خود سرویس دهنده و تعدادی که پولمان
    می رسد. اگر API بگوید ۵ و پول ۱۰ تا برسد، ۵؛ اگر API ناموجود بگوید،
    هر قدر هم پول باشد ناموجود؛ و برعکس."""
    known = [x for x in (api_stock, wallet) if x is not None]
    return min(known) if known else None


async def catalog(db: "Database", force: bool = False, admin: bool = False) -> dict:
    """محصولات با قیمت تومانی و موجودی واقعی. {"currency", "balance", "items"}.

    admin=True محصولات خاموش و بی نرخ را هم برمی گرداند (با visible و
    priced)، به همراه پاسخ خام هر محصول برای مقایسه.
    کلید، نرخ و... اگر تنظیم نباشد CanbosoError بالا می رود.
    """
    cfg = await pricing.load(db)
    cb = await client(db)
    try:
        if not cb.configured:
            raise CanbosoError("کلید API تنظیم نشده")
        data = await cb.catalog(force=force)
        bal = await cb.balance(force=force)
    finally:
        await cb.close()
    ids = await enabled_ids(db)
    items = []
    for p in data["products"]:
        pid = str(p["productId"])
        visible = ids is None or pid in ids
        cur = currency_of(p, data["currency"])
        priced = pricing.is_configured(cfg, cur)
        if not admin and (not visible or not priced):
            continue
        req = requirements(p)
        api_stock = stock_of(p)
        has_price = (p.get("price") or {}).get("amount") not in (None, "")
        # ماه هایی که پول ما برایشان می رسد (برای کاربر فقط همین ها)
        def fits(m: int) -> bool:
            w = wallet_units(bal, cost_of(p, m), cur)
            return w is None or w > 0
        months = [m for m in req["months"] if fits(m)]
        first = (months or req["months"] or [None])[0]
        wallet = wallet_units(bal, cost_of(p, first), cur)
        stock = effective_stock(api_stock, wallet)
        if req["months"] and not months:
            stock = 0
        price_of = (lambda c: pricing.compute(c, cfg, cur).final) if priced else (lambda c: 0)
        item = {
            "id": pid,
            "name": str(p.get("name") or ""),
            "description": str(p.get("description") or ""),
            "type": str(p.get("productType") or "account"),
            "stock": stock,
            "api_stock": api_stock,
            "wallet_stock": wallet,
            "available": has_price and (stock is None or stock > 0),
            "visible": visible,
            "priced": priced,
            "currency": cur,
            "cost": cost_of(p, first),
            "price": price_of(cost_of(p, first)),
            "months": req["months"] if admin else months,
            "month_prices": {m: price_of(cost_of(p, m)) for m in (req["months"] if admin else months)},
            "needs_email": req["email"],
        }
        if admin:
            item["raw"] = p
        items.append(item)
    return {"currency": data["currency"], "balance": bal, "items": items}


# ═══════════════════ خرید ═══════════════════


async def buy(
    db: "Database", bot, user: dict, product_id: str, *,  # noqa: ANN001
    months: int | None = None, email: str | None = None,
) -> dict:
    """{"status": ..., "order": ردیف سفارش, "price": ..., "result": پاسخ سرویس دهنده}."""
    lock = f"ai:{user['id']}"
    if not await db.acquire_lock(lock, ttl_seconds=120):
        return {"status": LOCKED}
    cb = await client(db)
    try:
        if not cb.configured:
            return {"status": NOT_CONFIGURED}
        cfg = await pricing.load(db)
        try:
            cat = await cb.catalog(force=True)
        except CanbosoError as exc:
            log.warning("خواندن محصولات canboso نشد: %s", exc)
            return {"status": FAILED, "error": str(exc)}
        p = next((x for x in cat["products"] if str(x.get("productId")) == str(product_id)), None)
        ids = await enabled_ids(db)
        if p is None or not available(p) or (ids is not None and str(product_id) not in ids):
            return {"status": UNAVAILABLE, "name": (p or {}).get("name") or ""}
        req = requirements(p)
        if req["months"] and months not in req["months"]:
            return {"status": BAD_INPUT}
        if req["email"] and not (email and EMAIL_RE.match(email)):
            return {"status": BAD_INPUT}
        currency = currency_of(p, cat["currency"])
        if not pricing.is_configured(cfg, currency):
            return {"status": NOT_CONFIGURED}
        cost = cost_of(p, months if req["months"] else None)
        b = pricing.compute(cost, cfg, currency)

        # موجودی خودمان قبل از کسر پول کاربر
        bal = await cb.balance()
        if bal is not None and bal["currency"] in ("", currency) and bal["balance"] < cost:
            await _alert_admins(bot, texts.AI_ADMIN_NO_FUNDS.format(
                error=f"موجودی {bal['balance']:g} {currency} است و این سفارش {cost:g} لازم دارد"))
            return {"status": UNAVAILABLE, "name": p.get("name") or ""}

        if not await db.atomic_debit(user["id"], b.final):
            return {"status": INSUFFICIENT, "price": b.final}
        txn_id = await db.insert_transaction(user["id"], "ai_purchase", -b.final, status="approved")
        order = await db.create_ai_order(
            user_id=user["id"], service_id=str(product_id), title=str(p.get("name") or "AI"),
            quantity=1, usd_cost=cost, price=b.final, txn_id=txn_id,
        )
        request = {"product_id": str(product_id), "months": months if req["months"] else None,
                   "email": email if req["email"] else None, "expected_cost": cost}
        idem = f"obour-{order['code']}-{uuid.uuid4().hex[:16]}"
        await db.set_ai_request(order["id"], idem, json.dumps(request, ensure_ascii=False), currency)
        order = await db.get_ai_order(order["id"])
        return await _send(db, bot, cb, user, order, first=True)
    finally:
        await cb.close()
        await db.release_lock(lock)


async def resolve(db: "Database", bot, order: dict) -> dict:  # noqa: ANN001
    """سفارش مبهم (یا pending جا مانده) را با همان Idempotency-Key دوباره می پرسد."""
    if order["status"] not in (UNKNOWN, "pending") or not order.get("idem_key"):
        return {"status": order["status"], "order": order}
    user = await db.get_user(order["user_id"])
    cb = await client(db)
    try:
        return await _send(db, bot, cb, user, order, first=False)
    finally:
        await cb.close()


async def _send(db: "Database", bot, cb: Canboso, user: dict, order: dict, *, first: bool) -> dict:  # noqa: ANN001
    req = json.loads(order.get("request") or "{}")
    try:
        result = await cb.purchase(
            req["product_id"], idempotency_key=order["idem_key"], quantity=1,
            customer_email=req.get("email"), slot_months=req.get("months"),
        )
    except CanbosoUnknown as exc:
        await db.finish_ai_order(order["id"], UNKNOWN, error=str(exc))
        log.error("سفارش هوش مصنوعی مبهم ماند: %s (%s)", order["code"], exc)
        if first:
            await _alert_admins(bot, texts.AI_ADMIN_UNKNOWN.format(
                code=order["code"], user=user["telegram_id"], price=f"{order['price']:,}", error=esc(str(exc)[:120])))
        return {"status": UNKNOWN, "order": await db.get_ai_order(order["id"])}
    except CanbosoNoFunds as exc:
        await _refund(db, user, order, "موجودی سرویس دهنده تمام شد")
        await _alert_admins(bot, texts.AI_ADMIN_NO_FUNDS.format(error=esc(str(exc)[:150])))
        return {"status": NO_FUNDS, "order": await db.get_ai_order(order["id"])}
    except CanbosoError as exc:
        await _refund(db, user, order, str(exc))
        log.warning("سفارش هوش مصنوعی %s انجام نشد: %s", order["code"], exc)
        return {"status": FAILED, "order": await db.get_ai_order(order["id"]), "error": str(exc)}

    o = result.get("order") or {}
    status = PROCESSING if is_waiting(result) and not accounts_of(result) else DELIVERED
    delivery = {
        "accounts": accounts_of(result),
        "email": o.get("customerEmail") or req.get("email"),
        "months": o.get("slotMonths") or req.get("months"),
        "payment": result.get("payment") or {},
        "fulfillment": o.get("fulfillmentStatus") or o.get("status"),
    }
    await db.finish_ai_order(order["id"], status, provider_order_id=str(o.get("orderCode") or ""),
                             products=json.dumps(delivery, ensure_ascii=False))
    log.info("سفارش هوش مصنوعی %s: %s", order["code"], status)

    # اگر هزینه واقعی بیشتر از برآورد شد (مثلا تخفیف یا قیمت ماهانه)،
    # از کاربر چیزی اضافه کم نمی شود؛ فقط ادمین باخبر می شود.
    try:
        paid = float((result.get("payment") or {}).get("amount") or 0)
        if paid > float(req.get("expected_cost") or 0) * 1.001:
            await _alert_admins(bot, f"⚠️ هزینه واقعی سفارش <code>{order['code']}</code> بیشتر از برآورد بود: "
                                     f"{paid:g} به جای {float(req.get('expected_cost') or 0):g}")
    except (TypeError, ValueError):
        pass
    return {"status": status, "order": await db.get_ai_order(order["id"]), "result": result}


async def _refund(db: "Database", user: dict, order: dict, reason: str) -> None:
    await db.atomic_credit(user["id"], int(order["price"]))
    await db.insert_transaction(user["id"], "refund", int(order["price"]), status="approved")
    await db.finish_ai_order(order["id"], FAILED, error=reason)


async def _alert_admins(bot, body: str) -> None:  # noqa: ANN001
    if bot is None:
        return
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(admin_id, body)
        except Exception:  # noqa: BLE001
            log.debug("خبر دادن به ادمین %s نشد", admin_id, exc_info=True)


# ═══════════════════ نمایش تحویل ═══════════════════


def delivery_of(order: dict) -> dict:
    """اطلاعات تحویل ذخیره شده. سفارش های سرویس دهنده قبلی لیست لینک بودند."""
    raw = order.get("products")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if isinstance(data, list):
        return {"links": [str(x) for x in data]}
    return data if isinstance(data, dict) else {}


def delivery_html(order: dict) -> str:
    """متن تحویل برای ربات: حساب ها با نام کاربری و رمز قابل کپی."""
    d = delivery_of(order)
    lines: list[str] = []
    for i, a in enumerate(d.get("accounts") or [], 1):
        head = f"👤 {i}. " if len(d.get("accounts") or []) > 1 else "👤 "
        lines.append(head + i18n.t("نام کاربری") + f": <code>{esc(a.get('user') or '-')}</code>")
        lines.append("🔑 " + i18n.t("رمز") + f": <code>{esc(a.get('password') or '-')}</code>")
        if a.get("verifyEmail"):
            lines.append("📧 " + i18n.t("ایمیل بازیابی") + f": <code>{esc(a['verifyEmail'])}</code>")
        if a.get("expiryText"):
            lines.append("⏳ " + i18n.t("انقضا") + f": {esc(a['expiryText'])}")
        if a.get("otherInfo"):
            lines.append("ℹ️ " + esc(a["otherInfo"]))
        lines.append("")
    for link in d.get("links") or []:
        lines.append(f"<code>{esc(link)}</code>")
    if not lines and d.get("email"):
        lines.append("📧 " + i18n.t("فعال سازی روی ایمیل") + f": <code>{esc(d['email'])}</code>")
    return "\n".join(lines).strip()
