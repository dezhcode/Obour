"""پنل ادمین مینی اپ.

فقط برای کسانی که آیدی تلگرامشان در ADMIN_IDS است. آیدی از initData امضا
شده تلگرام می آید (در wsgi با توکن ربات تایید می شود)، پس جعل پذیر نیست.
هر تابع اینجا اول _require_admin را صدا می زند؛ برای غیر ادمین جواب «پیدا
نشد» است تا حتی وجود این بخش هم معلوم نشود.

منطق کارها در app/services/admin_ops.py است و همان است که پنل ادمین
ربات استفاده می کند. بخش هایی که فرم پیچیده دارند (ارسال همگانی،
نظرسنجی، ایموجی، افکت، هوش مصنوعی، دسته ها) در همان ربات می مانند.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app import features, i18n, texts
from app.services import payments as payments_svc
from app.services import admin_ops
from app.services import crypto as crypto_svc
from app.services import stars as stars_svc
from app.utils import days_left, is_expired, now_str, service_status
from app.webapp.api import ApiError
from app.webapp.auth import WebAppUser

if TYPE_CHECKING:
    from app.db import Database
    from app.panel import Panel

log = logging.getLogger("obour.webapp.admin")


def _require_admin(wuser: WebAppUser) -> None:
    if not admin_ops.is_admin(wuser.id):
        log.warning("درخواست پنل ادمین از غیر ادمین: %s", wuser.id)
        raise ApiError("not found", 404, "not_found")
    # پنل ادمین فارسی است، مثل ربات
    i18n.set_lang("fa")


def _user_card(u: dict, extra: dict | None = None) -> dict:
    return {
        "telegram_id": u["telegram_id"], "name": u.get("first_name") or "-",
        "username": u.get("username") or "", "balance": int(u["balance"]),
        "blocked": bool(u.get("is_blocked")), "created_at": u.get("created_at"),
        "lang": u.get("lang") or "", "is_admin": admin_ops.is_admin(u["telegram_id"]),
        **(extra or {}),
    }


# ═══════════════════ داشبورد ═══════════════════


async def home(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    _require_admin(wuser)
    st = await db.dashboard_stats()
    today_charges = await db.fetchone(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM transactions "
        "WHERE type = 'charge' AND status = 'approved' AND substr(created_at, 1, 10) = ?",
        (now_str()[:10],),
    )
    return {
        "users": st["total_users"], "active_services": st["active_services"],
        "today_sales": int(st["today_sales"]), "today_charges": int(today_charges["s"]),
        "pending": st["pending_count"],
    }


# ═══════════════════ رسیدها ═══════════════════


async def charges(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    _require_admin(wuser)
    rows = await db.pending_charges(limit=50)
    return {
        "items": [{
            "id": t["id"], "amount": int(t["amount"]), "code": t.get("code") or f"#{t['id']}",
            "created_at": t["created_at"], "paid_at": t.get("paid_at"),
            "user": {"telegram_id": t["telegram_id"], "name": t.get("first_name") or "-",
                     "username": t.get("username") or "", "balance": int(t.get("balance") or 0)},
        } for t in rows],
        "reasons": dict(texts.__dict__["REJECT_REASONS"]),
    }


async def receipt(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, txn_id: int, bot=None) -> tuple[bytes, str]:  # noqa: ANN001
    """عکس رسید از تلگرام (file_id) خوانده و مستقیم داده می شود."""
    _require_admin(wuser)
    txn = await db.get_transaction(txn_id)
    if not txn or not txn.get("receipt_file_id") or bot is None:
        raise ApiError("رسید پیدا نشد", 404, "not_found")
    f = await bot.get_file(txn["receipt_file_id"])
    buf = await bot.download_file(f.file_path)
    data = buf.read() if hasattr(buf, "read") else bytes(buf)
    ctype = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    return data, ctype


async def charge_action(db: "Database", panel: "Panel | None", wuser: WebAppUser, *,
                        txn_id: int, action: str, reason: str = "", bot=None) -> dict:  # noqa: ANN001
    _require_admin(wuser)
    if action == "approve":
        r = await admin_ops.approve_charge(bot, db, txn_id, wuser.id)
    elif action == "dup":
        r = await admin_ops.duplicate_charge(bot, db, txn_id, wuser.id)
    elif action == "reject":
        reasons = texts.__dict__["REJECT_REASONS"]
        text = reasons.get(reason) or (reason or "").strip()[:200]
        if not text:
            raise ApiError("دلیل رد را بنویس", 400, "bad_request")
        r = await admin_ops.reject_charge(bot, db, txn_id, wuser.id, text)
    else:
        raise ApiError("کار نامعتبر", 400, "bad_request")
    if not r["ok"]:
        raise ApiError("این رسید قبلا بررسی شده", 409, "decided")
    return {"ok": True, "notify_err": r.get("notify_err") or ""}


# ═══════════════════ کاربران ═══════════════════


async def users(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, q: str = "", page: int = 0) -> dict:
    _require_admin(wuser)
    if q.strip():
        user, note = await admin_ops.find_user(db, q)
        return {"items": [_user_card(user)] if user else [], "note": note, "total": 1 if user else 0}
    rows, total = await db.users_page(page=max(0, page), per_page=20)
    return {"items": [_user_card(u, {"services": u.get("svc", 0), "spent": int(u.get("spent") or 0)}) for u in rows],
            "total": total, "note": ""}


async def user_detail(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, telegram_id: int) -> dict:
    _require_admin(wuser)
    u = await db.get_user_by_tg(telegram_id)
    if not u:
        raise ApiError("کاربر پیدا نشد", 404, "not_found")
    summary = await db.user_summary(u["id"])
    svcs = await db.user_services(u["id"])
    return _user_card(u, {
        **{k: int(v or 0) for k, v in summary.items()},
        "services_list": [{
            "id": s["id"], "title": s.get("label") or s.get("panel_username") or f"#{s['id']}",
            "expire_at": s.get("expire_at"), "expired": is_expired(s.get("expire_at")),
        } for s in svcs[:20]],
    })


async def balance(db: "Database", panel: "Panel | None", wuser: WebAppUser, *,
                  telegram_id: int, amount: int, add: bool, bot=None) -> dict:  # noqa: ANN001
    _require_admin(wuser)
    r = await admin_ops.adjust_balance(bot, db, telegram_id, amount, add, wuser.id)
    if not r["ok"]:
        raise ApiError(r["error"], 400, "bad_request")
    return {"ok": True, "balance": r["balance"], "notify_err": r["notify_err"]}


async def block(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, telegram_id: int, blocked: bool) -> dict:
    _require_admin(wuser)
    if not await admin_ops.set_blocked(db, telegram_id, blocked, wuser.id):
        raise ApiError("این کاربر را نمی شود مسدود کرد", 400, "bad_request")
    return {"ok": True, "blocked": blocked}


# ═══════════════════ پلن ها ═══════════════════


async def plans(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    _require_admin(wuser)
    cats = await db.categories()
    items = await db.all_plans()
    out = []
    for c in cats + [{"id": None, "title": "بدون دسته", "emoji": "", "is_active": 1}]:
        ps = [p for p in items if p.get("category_id") == c["id"]]
        if ps or c["id"] is not None:
            out.append({"id": c["id"], "title": c["title"], "emoji": c.get("emoji") or "", "active": bool(c["is_active"]),
                        "plans": [{"id": p["id"], "title": p["title"], "price": int(p["price"]),
                                   "data_gb": p["data_gb"], "duration_days": p["duration_days"],
                                   "active": bool(p["is_active"]), "badge": p.get("badge") or ""} for p in ps]})
    return {"categories": out}


_PLAN_FIELDS = {"price": (0, 1_000_000_000), "data_gb": (1, 100_000), "duration_days": (1, 3650)}


async def plan_update(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, plan_id: int, fields: dict) -> dict:
    _require_admin(wuser)
    plan = await db.get_plan(plan_id)
    if not plan:
        raise ApiError("پلن پیدا نشد", 404, "not_found")
    clean: dict = {}
    for k, v in (fields or {}).items():
        if k == "is_active":
            clean[k] = 1 if v else 0
        elif k in _PLAN_FIELDS:
            try:
                n = int(str(v).replace(",", ""))
            except ValueError:
                raise ApiError("عدد نامعتبر", 400, "bad_request") from None
            lo, hi = _PLAN_FIELDS[k]
            if not lo <= n <= hi:
                raise ApiError("عدد خارج از محدوده است", 400, "bad_request")
            clean[k] = n
    if not clean:
        raise ApiError("چیزی برای ذخیره نیست", 400, "bad_request")
    await db.update_plan(plan_id, **clean)
    log.info("ادمین %s پلن %s را عوض کرد: %s", wuser.id, plan_id, clean)
    return {"ok": True}


# ═══════════════════ تنظیمات ═══════════════════


async def settings(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    _require_admin(wuser)
    values = {f: await db.get_setting(f, "") or "" for f in admin_ops.SETTING_FIELDS}
    values.setdefault("min_charge", "50000")
    if not values["min_charge"]:
        values["min_charge"] = "50000"
    return {
        "values": values,
        "features": [{"key": k, "title": t, "desc": d, "on": features.is_on(k)}
                     for k, (t, d, _default) in features.FEATURES.items()],
        "crypto": {"enabled": crypto_svc.enabled(), "testnet": crypto_svc.testnet(),
                   "address": crypto_svc.pay_address(), "usdt": bool(crypto_svc.usdt_master())},
        "stars": await stars_svc.enabled(db),
        "pay": await payments_svc.switches(db),
    }


async def setting_save(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, field: str, value: str) -> dict:
    _require_admin(wuser)
    ok, msg = await admin_ops.save_setting(db, field, value, wuser.id)
    if not ok:
        raise ApiError(msg, 400, "bad_request")
    return {"ok": True, "value": msg}


async def feature_set(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, key: str, on: bool) -> dict:
    _require_admin(wuser)
    if key not in features.FEATURES:
        raise ApiError("این بخش پیدا نشد", 404, "not_found")
    await features.set_on(db, key, bool(on))
    log.info("ادمین %s بخش %s را %s کرد", wuser.id, key, "روشن" if on else "خاموش")
    return {"ok": True, "on": features.is_on(key)}


async def pay_set(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, key: str, on: bool) -> dict:
    """روشن/خاموش کردن یک روش شارژ کیف پول."""
    from app.services import payments

    _require_admin(wuser)
    if key not in payments.METHODS:
        raise ApiError("این روش پیدا نشد", 404, "not_found")
    await payments.set_on(db, key, bool(on))
    log.info("ادمین %s روش پرداخت %s را %s کرد", wuser.id, key, "روشن" if on else "خاموش")
    return {"ok": True, "on": await payments.is_on(db, key)}


async def ai_products(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    """محصولات canboso برای ادمین: نمایش، قیمت و سه عدد موجودی."""
    from app.canboso import CanbosoError
    from app.services import ai_shop

    _require_admin(wuser)
    if not await ai_shop.api_key(db):
        return {"configured": False, "items": [], "wallet": None}
    try:
        cat = await ai_shop.catalog(db, force=True, admin=True)
    except CanbosoError as exc:
        return {"configured": True, "error": str(exc), "items": [], "wallet": None}
    bal = cat["balance"]
    return {
        "configured": True,
        "wallet": ({"text": bal["text"] or f"{bal['balance']:g} {bal['currency']}", "amount": bal["balance"],
                    "currency": bal["currency"]} if bal else None),
        "items": [dict({k: x[k] for k in ("id", "name", "type", "kind", "brand", "visible", "priced", "available", "stock",
                                          "api_stock", "wallet_stock", "currency", "cost", "price", "months", "category",
                                          "auto_category", "category_set", "guide", "provider_image")},
                       image=ai_shop.image_url(x["image"]), description=x["description"][:1500]) for x in cat["items"]],
        "categories": [{"key": k, "title": t} for k, (t, _e) in ai_shop.CATEGORIES.items()],
    }


async def ai_meta_set(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, pid: str,
                      category=None, guide=None) -> dict:  # noqa: ANN001
    """دسته ("" = خودکار) و آموزش فعال سازی ("" = توضیح سرویس دهنده)."""
    from app.services import ai_shop

    _require_admin(wuser)
    if not pid:
        raise ApiError("محصول مشخص نیست", 400, "bad_request")
    fields = {}
    if category is not None:
        category = str(category)
        if category and category not in ai_shop.CATEGORIES:
            raise ApiError("این دسته وجود ندارد", 400, "bad_request")
        fields["category"] = category or None
    if guide is not None:
        fields["guide"] = str(guide).strip()[:3000] or None
    await db.set_product_meta(pid, **fields)
    log.info("ادمین %s تنظیمات محصول %s را عوض کرد: %s", wuser.id, pid, list(fields))
    return {"ok": True}


async def ai_image_set(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, pid: str,
                       image: str = "", fetch: bool = False, remove: bool = False) -> dict:
    """تصویر محصول: آپلود (data URL)، برداشتن تصویر خود canboso، یا حذف."""
    import base64
    import binascii

    from app.services import ai_shop

    _require_admin(wuser)
    if not pid:
        raise ApiError("محصول مشخص نیست", 400, "bad_request")
    if remove:
        await ai_shop.remove_image(db, pid)
        return {"ok": True, "image": ""}
    if fetch:
        try:
            cat = await ai_shop.catalog(db, admin=True)
        except Exception as exc:  # noqa: BLE001
            raise ApiError("خواندن محصولات نشد", 502, "provider") from exc
        item = next((x for x in cat["items"] if x["id"] == pid), None)
        path = (item or {}).get("provider_image") or ""
        if not path:
            raise ApiError("canboso برای این محصول تصویری ندارد", 404, "no_image")
        import httpx

        url = path if path.startswith("http") else "https://canboso.com" + ("" if path.startswith("/") else "/") + path
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http:
                r = await http.get(url)
            data = r.content if r.status_code == 200 else b""
        except Exception as exc:  # noqa: BLE001
            raise ApiError("دریافت تصویر از canboso نشد", 502, "fetch") from exc
    else:
        raw = image.split(",", 1)[1] if image.startswith("data:") else image
        try:
            data = base64.b64decode(raw, validate=True)
        except (ValueError, binascii.Error):
            data = b""
    try:
        name = await ai_shop.save_image(db, pid, data)
    except ValueError as exc:
        raise ApiError("فقط عکس JPG، PNG یا WEBP تا ۳ مگابایت", 400, "bad_image") from exc
    log.info("ادمین %s تصویر محصول %s را گذاشت", wuser.id, pid)
    return {"ok": True, "image": ai_shop.image_url(name)}


async def ai_product_set(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, pid: str, on: bool, all_: bool = False) -> dict:
    """نمایش یک محصول (یا همه) را روشن/خاموش می کند."""
    from app.canboso import CanbosoError
    from app.services import ai_shop

    _require_admin(wuser)
    try:
        cat = await ai_shop.catalog(db, admin=True)
    except CanbosoError as exc:
        raise ApiError(f"خواندن محصولات نشد: {exc}", 502, "provider") from exc
    ids = [x["id"] for x in cat["items"]]
    if all_:
        await ai_shop.set_all_visible(db, ids if on else [])
    else:
        if pid not in ids:
            raise ApiError("این محصول دیگر در canboso نیست", 404, "not_found")
        await ai_shop.set_visible(db, pid, bool(on), ids)
    return {"ok": True}


# ═══════════════════ مانیتورینگ ═══════════════════
# فهرست کامل کاربران، سرویس ها با جزئیات، سفارش های هوش مصنوعی و خریدها.
# همه فقط خواندنی اند؛ کارهای روی کاربر همان های بالا هستند.

PER_PAGE = 30


def _who(r: dict) -> dict:
    return {"telegram_id": r.get("telegram_id"), "name": r.get("first_name") or "-", "username": r.get("username") or ""}


def _svc_row(s: dict) -> dict:
    """سرویس برای فهرست؛ مصرف از آخرین عکس روزانه (بدون تماس با پنل)."""
    limit = s.get("snap_limit")
    if limit is None and s.get("data_gb"):
        limit = int(s["data_gb"]) * 1024**3
    used = int(s.get("snap_used") or 0)
    exp = s.get("expire_at")
    return {
        "id": s["id"], "title": s.get("label") or s.get("panel_username") or f"#{s['id']}",
        "panel_username": s.get("panel_username") or "", "plan": s.get("plan_title") or "",
        "used": used, "limit": limit, "expire_at": exp, "created_at": s.get("created_at"),
        "days_left": max(0, days_left(exp)) if exp else 0, "expired": is_expired(exp),
        "status": service_status(exp, used, limit, s.get("duration_days")),
        "user": _who(s),
    }


async def monitor(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    _require_admin(wuser)
    st = await db.admin_monitor_stats()
    return {k: int(v or 0) for k, v in st.items()}


async def users_all(db: "Database", panel: "Panel | None", wuser: WebAppUser, *,
                    q: str = "", page: int = 0, flt: str = "all", sort: str = "recent") -> dict:
    _require_admin(wuser)
    rows, total = await db.admin_users(page=max(0, page), per_page=PER_PAGE, flt=flt, sort=sort, q=q.strip())
    return {
        "items": [_user_card(u, {"services": int(u.get("svc") or 0), "services_on": int(u.get("svc_on") or 0),
                                 "ai": int(u.get("ai_n") or 0), "spent": int(u.get("spent") or 0)}) for u in rows],
        "total": total, "page": page, "more": (page + 1) * PER_PAGE < total,
    }


async def user_full(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, telegram_id: int) -> dict:
    """کاربر با همه سرویس ها، سفارش های هوش مصنوعی و تراکنش های اخیر."""
    from app.webapp.api import _ai_order_out

    _require_admin(wuser)
    u = await db.get_user_by_tg(telegram_id)
    if not u:
        raise ApiError("کاربر پیدا نشد", 404, "not_found")
    summary = await db.user_summary(u["id"])
    svcs, _ = await db.admin_services(per_page=50, flt="all", user_id=u["id"])
    ai, _ = await db.admin_ai_orders(per_page=20, user_id=u["id"])
    txns = await db.user_transactions(u["id"], limit=20)
    return _user_card(u, {
        **{k: int(v or 0) for k, v in summary.items()},
        "services_list": [_svc_row(s) for s in svcs],
        "ai_orders": [_ai_order_out(o) for o in ai],
        "transactions": [{"id": t["id"], "type": t["type"], "amount": int(t["amount"]), "status": t["status"],
                          "code": t.get("code") or "", "created_at": t["created_at"]} for t in txns],
    })


async def services_list(db: "Database", panel: "Panel | None", wuser: WebAppUser, *,
                        q: str = "", page: int = 0, flt: str = "active") -> dict:
    _require_admin(wuser)
    rows, total = await db.admin_services(page=max(0, page), per_page=PER_PAGE, flt=flt, q=q.strip())
    return {"items": [_svc_row(s) for s in rows], "total": total, "page": page,
            "more": (page + 1) * PER_PAGE < total}


async def service_full(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, service_id: int) -> dict:
    """جزئیات کامل سرویس با آمار زنده پنل (اگر در دسترس باشد)."""
    _require_admin(wuser)
    s = await db.fetchone(
        """SELECT s.*, u.telegram_id, u.first_name, u.username, p.title AS plan_title, p.price AS plan_price
           FROM services s JOIN users u ON u.id = s.user_id LEFT JOIN plans p ON p.id = s.plan_id
           WHERE s.id = ?""", (service_id,))
    if not s:
        raise ApiError("سرویس پیدا نشد", 404, "not_found")
    s = dict(s)
    out = _svc_row(s)
    live = {"source": "none"}
    if panel is not None:
        try:
            pu = await panel.get_user(s["panel_username"])
            if pu is not None:
                st = getattr(pu.status, "value", pu.status)
                live = {
                    "source": "panel", "status": str(st or ""), "used": int(pu.used_traffic or 0),
                    "limit": pu.data_limit, "lifetime": int(getattr(pu, "lifetime_used_traffic", 0) or 0),
                    "online_at": str(pu.online_at) if getattr(pu, "online_at", None) else "",
                    "hwid_limit": getattr(pu, "hwid_limit", None),
                }
                out.update(used=live["used"], limit=live["limit"],
                           status=service_status(s["expire_at"], live["used"], live["limit"], s.get("duration_days")))
        except Exception:  # noqa: BLE001
            log.warning("آمار زنده سرویس %s از پنل خوانده نشد", service_id, exc_info=True)
            live = {"source": "error"}
    hist = await db.usage_history(service_id, days=15)
    daily, prev = [], None
    for row in hist:
        cur = int(row["used_bytes"] or 0)
        daily.append({"day": row["day"], "bytes": max(0, cur - prev) if prev is not None else 0})
        prev = cur
    out.update({
        "sub_url": s.get("sub_url") or "", "data_gb": s.get("data_gb"), "duration_days": s.get("duration_days"),
        "plan_price": int(s.get("plan_price") or 0), "live": live, "daily": daily[1:],
        "warn_data_at": s.get("warn_data_at"), "warn_expire_at": s.get("warn_expire_at"),
    })
    return out


async def ai_orders_list(db: "Database", panel: "Panel | None", wuser: WebAppUser, *,
                         status: str = "", page: int = 0) -> dict:
    from app.webapp.api import _ai_order_out

    _require_admin(wuser)
    rows, total = await db.admin_ai_orders(page=max(0, page), per_page=PER_PAGE, status=status)
    return {"items": [{**_ai_order_out(o), "user": _who(o)} for o in rows], "total": total, "page": page,
            "more": (page + 1) * PER_PAGE < total}


async def ai_order_full(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, order_id: int) -> dict:
    from app.webapp.api import _ai_order_out

    _require_admin(wuser)
    o = await db.get_ai_order(order_id)
    if not o:
        raise ApiError("سفارش پیدا نشد", 404, "not_found")
    u = await db.get_user(o["user_id"]) or {}
    return {**_ai_order_out(o, full=True), "user": _who(u), "error": o.get("error") or "",
            "cost": o.get("usd_cost"), "cost_currency": o.get("cost_currency") or "USD"}


async def purchases(db: "Database", panel: "Panel | None", wuser: WebAppUser, *,
                    kind: str = "all", page: int = 0) -> dict:
    _require_admin(wuser)
    rows, total = await db.admin_purchases(page=max(0, page), per_page=PER_PAGE, kind=kind)
    return {"items": [{
        "id": t["id"], "amount": -int(t["amount"]), "code": t.get("code") or "", "created_at": t["created_at"],
        "kind": "ai" if t["type"] == "ai_purchase" else "service",
        "title": t.get("ai_title") or "", "ai_id": t.get("ai_id"), "ai_status": t.get("ai_status") or "",
        "user": _who(t),
    } for t in rows], "total": total, "page": page, "more": (page + 1) * PER_PAGE < total}


READ = {"admin": home, "admin/charges": charges, "admin/plans": plans, "admin/settings": settings,
        "admin/ai": ai_products, "admin/monitor": monitor}
