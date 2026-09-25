"""اندپوینت های مینی اپ - فاز یک، همه فقط خواندنی.

هیچ تابعی در این فایل چیزی را نمی نویسد. حتی get_or_create_user هم
صدا زده نمی شود: اگر کاربری هنوز /start نزده باشد، مینی اپ او را به
ربات می فرستد. این عمدی است - ثبت نام، پذیرش قوانین و عضویت اجباری
همه در ربات اتفاق می افتد و مینی اپ نباید از کنارشان رد شود.
"""
from __future__ import annotations

import asyncio
import logging
import time

from typing import TYPE_CHECKING

from app import apps, features, referral, texts
from app.config import config
from app.utils import (
    days_left,
    is_expired,
    service_status,
    track_code,
    usage_percent,
)
from app.services import charge as charge_svc
from app.services import purchase as purchase_svc
from app.services import support as support_svc
from app.webapp.auth import WebAppUser

if TYPE_CHECKING:  # فقط برای type hint؛ در زمان اجرا وارد نمی شود
    from app.db import Database
    from app.panel import Panel

log = logging.getLogger("obour.webapp")

# کش کوتاه مصرف: service_id -> (used, data_limit, monotonic)
# پنل کند است (تا ۸ ثانیه تایم اوت) و کاربر در مینی اپ بین تب ها
# بالا و پایین می رود. بدون این کش، هر برگشت به «سرویس ها» یک دور
# کامل درخواست به پنل می زند.
_usage_cache: dict[int, tuple[int, int | None, float]] = {}
_USAGE_TTL = 45.0


class ApiError(Exception):
    """خطای قابل نمایش به کاربر. status کد HTTP است."""

    def __init__(self, message: str, status: int = 400, code: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


# ═══════════════════ کمکی ها ═══════════════════


async def _require_user(db: "Database", wuser: WebAppUser) -> dict:
    """ردیف کاربر در دیتابیس. نبودنش یعنی هنوز /start نزده."""
    user = await db.get_user_by_tg(wuser.id)
    if not user:
        raise ApiError("هنوز ربات را استارت نکرده ای", 404, "no_account")
    if user["is_blocked"]:
        raise ApiError("دسترسی این حساب بسته شده است", 403, "blocked")
    return user


async def _panel_usage(
    panel: "Panel | None", db: "Database", service: dict
) -> tuple[int, int | None, str]:
    """(مصرف، سقف، منبع). منبع: panel | cache | snapshot | none.

    اگر پنل در دسترس نباشد، به جای صفر نشان دادن، آخرین عکس روزانه
    خوانده می شود و به کاربر گفته می شود که عدد تازه نیست.
    """
    sid = service["id"]
    hit = _usage_cache.get(sid)
    if hit and (time.monotonic() - hit[2]) < _USAGE_TTL:
        return hit[0], hit[1], "cache"

    if panel is not None:
        try:
            pu = await panel.get_user(service["panel_username"])
            if pu is not None:
                used = int(pu.used_traffic or 0)
                limit = pu.data_limit
                _usage_cache[sid] = (used, limit, time.monotonic())
                return used, limit, "panel"
        except Exception:  # noqa: BLE001
            log.warning("خواندن مصرف از پنل نشد (service=%s)", sid, exc_info=True)

    history = await db.usage_history(sid, days=1)
    if history:
        return int(history[-1]["used_bytes"] or 0), history[-1]["data_limit"], "snapshot"

    gb = service.get("data_gb") or 0
    return 0, (int(gb) * 1024**3 if gb else None), "none"


def _service_card(service: dict, used: int, limit: int | None, source: str) -> dict:
    status = service_status(
        service["expire_at"], used, limit, service.get("duration_days")
    )
    return {
        "id": service["id"],
        "title": service.get("label") or f"سرویس {service['id']}",
        "status": status,
        "used_bytes": used,
        "limit_bytes": limit,
        "percent": usage_percent(used, limit),
        "expire_at": service["expire_at"],
        "days_left": max(0, days_left(service["expire_at"])),
        "expired": is_expired(service["expire_at"]),
        "created_at": service["created_at"],
        "fresh": source in ("panel", "cache"),
    }


# ═══════════════════ اندپوینت ها ═══════════════════


async def bootstrap(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    """اولین درخواست مینی اپ: کاربر، شمارنده ها، و بخش های روشن."""
    user = await _require_user(db, wuser)

    services = await db.user_services(user["id"])
    active = sum(1 for s in services if not is_expired(s["expire_at"]))
    unread = await db.unread_replies(user["id"])
    bot_username = await db.get_setting("bot_username", "")

    return {
        "user": {
            "telegram_id": user["telegram_id"],
            "name": user.get("first_name") or wuser.first_name or "کاربر",
            "username": user.get("username") or wuser.username or "",
            "balance": int(user["balance"]),
            "joined_at": user["created_at"],
            "rules_accepted": bool(user.get("rules_accepted_at")),
            "trial_used": bool(user.get("free_trial_used")),
        },
        "counters": {
            "services_total": len(services),
            "services_active": active,
            "unread_replies": unread,
        },
        "features": {
            key: features.is_on(key)
            for key in ("shop_vpn", "shop_ai", "shop_custom", "shop_trial",
                        "shop_wallet", "shop_referral", "shop_locations")
        },
        "bot": {
            "username": bot_username,
            "link": f"https://t.me/{bot_username}" if bot_username else "",
        },
        "readonly": False,
    }


async def services_list(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    """فهرست سرویس ها با مصرف زنده.

    مصرف همه سرویس ها موازی خوانده می شود، نه پشت سر هم. کاربری با
    چهار سرویس نباید چهار برابر یک نفر صبر کند.
    """
    user = await _require_user(db, wuser)
    services = await db.user_services(user["id"])
    if not services:
        return {"items": []}

    results = await asyncio.gather(
        *[_panel_usage(panel, db, s) for s in services], return_exceptions=True
    )

    items = []
    for service, res in zip(services, results):
        if isinstance(res, BaseException):
            used, limit, source = 0, None, "none"
        else:
            used, limit, source = res
        items.append(_service_card(service, used, limit, source))
    return {"items": items}


async def service_detail(
    db: "Database", panel: "Panel | None", wuser: WebAppUser, service_id: int
) -> dict:
    """جزئیات یک سرویس + لینک ساب + لینک های اتصال سریع + نمودار مصرف."""
    user = await _require_user(db, wuser)
    service = await db.get_service(service_id)
    # بررسی مالکیت حیاتی است: شناسه سرویس عدد ساده است و بدون این خط
    # هر کسی می توانست با /api/service?id=1 لینک ساب دیگران را بخواند.
    if not service or service["user_id"] != user["id"] or not service["is_active"]:
        raise ApiError("سرویس پیدا نشد", 404, "not_found")

    used, limit, source = await _panel_usage(panel, db, service)
    card = _service_card(service, used, limit, source)

    history = await db.usage_history(service_id, days=8)
    daily = []
    prev = None
    for row in history:
        cur = int(row["used_bytes"] or 0)
        # عکس ها تجمعی اند؛ مصرف هر روز اختلاف دو عکس پیاپی است
        daily.append({"day": row["day"], "bytes": max(0, cur - prev) if prev is not None else 0})
        prev = cur

    sub_url = service["sub_url"]
    import_links = []
    if apps.is_allowed_sub(sub_url):
        # از همان سازنده لینکی استفاده می شود که ربات استفاده می کند.
        # نسخه قبلی این جا لینک را دستی می ساخت و نام سرویس را encode
        # نمی کرد؛ نامی با & یا + یا # لینک را می شکست.
        for key, (label, _tpl) in apps.APPS.items():
            url = apps.import_link(key, sub_url, card["title"])
            if url:
                import_links.append({"key": key, "label": label, "url": url})

    return {
        **card,
        "panel_username": service["panel_username"],
        "sub_url": sub_url,
        "qr_url": f"qr?id={service_id}",
        "import_links": import_links,
        "daily": daily[1:],  # روز اول فقط مبنای اختلاف است
        "usage_source": source,
    }


async def wallet(
    db: "Database", panel: "Panel | None", wuser: WebAppUser,
    offset: int = 0, kind: str | None = None,
) -> dict:
    """موجودی و سوابق مالی با صفحه بندی."""
    user = await _require_user(db, wuser)
    limit = 12
    offset = max(0, min(offset, 5000))
    rows = await db.user_transactions(user["id"], limit=limit, offset=offset, kind=kind)
    total = await db.count_transactions(user["id"], kind=kind)

    items = []
    for row in rows:
        items.append({
            "id": row["id"],
            "type": row["type"],
            "status": row["status"],
            "amount": int(row["amount"]),
            "code": row.get("code") or track_code("OB", row["id"]),
            "created_at": row["created_at"],
            "reject_reason": row.get("reject_reason") or "",
        })
    return {
        "balance": int(user["balance"]),
        "items": items,
        "offset": offset,
        "total": total,
        "has_more": offset + limit < total,
    }


async def plans(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    """ویترین فروشگاه. خرید در فاز یک انجام نمی شود.

    هر پلن یک deep link به ربات دارد؛ کاربر روی «خرید» بزند، مینی اپ
    بسته می شود و همان صفحه پلن در ربات باز می شود. یعنی مسیر پرداخت
    دقیقا همان مسیر آزموده شده می ماند.
    """
    await _require_user(db, wuser)
    if not features.is_on("shop_vpn"):
        return {"categories": [], "disabled": True}

    bot_username = await db.get_setting("bot_username", "")
    categories = await db.shop_categories()
    out = []
    for cat in categories:
        rows = await db.active_plans(cat["id"])
        if not rows:
            continue
        out.append({
            "id": cat["id"],
            "title": cat["title"],
            "emoji": cat.get("emoji") or "📦",
            "plans": [
                {
                    "id": p["id"],
                    "title": p["title"],
                    "data_gb": p["data_gb"],
                    "duration_days": p["duration_days"],
                    "price": int(p["price"]),
                    "badge": p.get("badge") or "",
                    "buy_link": (
                        f"https://t.me/{bot_username}?start=plan_{p['id']}"
                        if bot_username else ""
                    ),
                }
                for p in rows
            ],
        })
    return {"categories": out, "disabled": False, "locations": texts.LOCATION_INFO}


async def referral(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    """صفحه هم سفرها."""
    user = await _require_user(db, wuser)
    if not features.is_on("shop_referral"):
        raise ApiError("این بخش فعلا خاموش است", 403, "feature_off")

    stats = await db.referral_stats(user["telegram_id"], user["id"])
    bot_username = await db.get_setting("bot_username", "")
    log_rows = await db.referral_log(user["id"], limit=10)

    return {
        "link": (
            f"https://t.me/{bot_username}?start=ref_{user['telegram_id']}"
            if bot_username else ""
        ),
        "percent": config.ref_percent,
        "stats": stats,
        "log": [
            {
                "reward": int(r["reward"]),
                "order_amount": int(r["order_amount"] or 0),
                "kind": r.get("kind") or "",
                "created_at": r["created_at"],
                "name": r.get("first_name") or "کاربر",
            }
            for r in log_rows
        ],
    }


async def tickets(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    """فهرست گفتگوهای پشتیبانی با آخرین پیام و تعداد پاسخ.

    خواندن فهرست، پیام های خوانده نشده را هم علامت خورده می کند - همان
    کاری که باز کردن بخش پشتیبانی در ربات می کند. اگر این کار را نکنیم،
    نشانگر قرمز روی هدر می ماند حتی بعد از اینکه کاربر پاسخ را دید.
    """
    user = await _require_user(db, wuser)
    threads = await db.ticket_threads(user["id"], limit=20)
    await db.mark_tickets_read(user["id"])
    return {
        "items": [
            {
                "id": t["id"],
                "code": t.get("code") or track_code("TK", t["id"]),
                "status": t.get("status") or "open",
                "created_at": t["created_at"],
                "last_at": t.get("last_at") or t["created_at"],
                "replies": int(t.get("replies") or 0),
                "preview": (t.get("body") or "").strip()[:90] or "بدون متن",
                "has_photo": bool(t.get("file_id")),
            }
            for t in threads
        ]
    }


async def ticket_thread(
    db: "Database", panel: "Panel | None", wuser: WebAppUser, ticket_id: int
) -> dict:
    """گفتگوی کامل یک تیکت. پاسخ دادن همچنان در ربات است.

    مالکیت با user_id در خود کوئری چک می شود؛ ticket_messages بدون آن
    پیام های تیکت هر کسی را می داد.
    """
    user = await _require_user(db, wuser)
    rows = await db.ticket_messages(ticket_id, user["id"])
    if not rows:
        raise ApiError("تیکت پیدا نشد", 404, "not_found")

    root = rows[0]
    messages = [
        {
            # in = پیام کاربر، out = پاسخ پشتیبانی
            "side": "user" if r.get("direction") == "in" else "support",
            "body": (r.get("body") or "").strip(),
            "has_photo": bool(r.get("file_id")),
            "created_at": r["created_at"],
        }
        for r in rows
    ]
    return {
        "id": root["id"],
        "code": root.get("code") or track_code("TK", root["id"]),
        "status": root.get("status") or "open",
        "created_at": root["created_at"],
        "messages": messages,
    }


def qr_svg(data: str) -> bytes:
    """QR ساده به صورت SVG.

    قاب برند (qr_png) برای پیام های ربات است؛ داخل مینی اپ فقط یک QR
    تمیز لازم است که سریع خوانده شود. SVG هم سبک تر از PNG است و هم
    روی هر تراکم پیکسلی لبه تیز می ماند - که برای QR مهم است، چون
    ماژول های نرم شده را دوربین بعضی گوشی ها سخت می خواند.

    پس زمینه سفید صریح دارد: QR روی زمینه تیره خوانده نمی شود و نباید
    به تم صفحه وابسته باشد.
    """
    import qrcode

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=2
    )
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)

    # ماژول های هر ردیف در یک path ادغام می شوند تا فایل کوچک بماند
    parts = []
    for y, row in enumerate(matrix):
        x = 0
        while x < n:
            if row[x]:
                run = x
                while run < n and row[run]:
                    run += 1
                parts.append(f"M{x} {y}h{run - x}v1h-{run - x}z")
                x = run
            else:
                x += 1

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" '
        f'width="{n * 8}" height="{n * 8}" shape-rendering="crispEdges">'
        f'<rect width="{n}" height="{n}" fill="#fff"/>'
        f'<path d="{"".join(parts)}" fill="#000"/></svg>'
    ).encode("utf-8")


async def qr_payload(
    db: "Database", panel: "Panel | None", wuser: WebAppUser, service_id: int
) -> str:
    """لینک ساب برای ساخت QR. مالکیت اینجا هم سنجیده می شود."""
    user = await _require_user(db, wuser)
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"] or not service["is_active"]:
        raise ApiError("سرویس پیدا نشد", 404, "not_found")
    return service["sub_url"]


async def ai_catalog(
    db: "Database", panel: "Panel | None", wuser: WebAppUser
) -> dict:
    """محصولات هوش مصنوعی برای نمایش در مینی اپ.

    سفارش نهایی عمدا در ربات می ماند: قیمت این محصولات دلاری است و به
    موجودی لحظه ای فروشنده بستگی دارد، پس یک مسیر پرداخت دوم برایش
    درست کردن ریسکی است که ارزشش را ندارد. مینی اپ فقط ویترین است.
    """
    user = await _require_user(db, wuser)
    if not features.is_on("shop_ai"):
        return {"enabled": False, "items": [], "banner": False}

    bot_username = await db.get_setting("bot_username", "")
    has_banner = bool(await db.get_setting("webapp_ai_banner", ""))

    items: list[dict] = []
    try:
        from app.warzone import Warzone

        key = await db.get_setting("ai_api_key", "")
        if key:
            products = await Warzone(key).products()
            for pr in products or []:
                items.append({
                    "id": str(pr.get("id") or pr.get("service_id") or ""),
                    "title": pr.get("title") or pr.get("name") or "محصول",
                    "price": pr.get("price_toman") or pr.get("price") or 0,
                    "stock": pr.get("stock"),
                    "order_link": (
                        f"https://t.me/{bot_username}?start=ai_{pr.get('id')}"
                        if bot_username else ""
                    ),
                })
    except Exception:  # noqa: BLE001
        # نبود کاتالوگ نباید صفحه را بشکند؛ ویترین خالی بهتر از خطاست.
        log.warning("کاتالوگ هوش مصنوعی خوانده نشد", exc_info=True)

    orders = await db.user_ai_orders(user["id"], limit=5)
    return {
        "enabled": True,
        "banner": has_banner,
        "items": items,
        "orders": [
            {
                "id": o["id"],
                "title": o.get("title") or "سفارش",
                "status": o.get("status") or "pending",
                "code": o.get("code") or "",
                "price": int(o.get("price") or 0),
                "created_at": o["created_at"],
            }
            for o in orders
        ],
        "bot_link": f"https://t.me/{bot_username}" if bot_username else "",
    }


def _latin(text: str) -> str:
    """ارقام فارسی و عربی متن های ربات به لاتین، برای یکدستی مینی اپ."""
    return (text or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


async def topup_info(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    """اطلاعات صفحه شارژ: حداقل، مبلغ های آماده، و درخواست باز قبلی."""
    user = await _require_user(db, wuser)
    card = await charge_svc.card(db)
    prev = await charge_svc.open_request(db, user)
    return {
        "enabled": bool(card["number"]),
        "min": await charge_svc.min_charge(db),
        "presets": list(charge_svc.PRESETS),
        "card": card if prev else None,   # کارت فقط وقتی مبلغ رزرو شده نشان داده می شود
        "open": ({"txn_id": prev["id"], "amount": int(prev["amount"]), "created_at": prev["created_at"]} if prev else None),
    }


_CHARGE_ERR = {
    charge_svc.CARD_NOT_SET: (503, "شماره کارت هنوز تنظیم نشده؛ با پشتیبانی تماس بگیر"),
    charge_svc.TOO_SMALL: (400, "مبلغ کمتر از حداقل شارژ است"),
    charge_svc.TOO_LARGE: (400, "مبلغ بیش از حد مجاز است"),
    charge_svc.AMOUNT_BUSY: (409, "الان مبلغ آزاد پیدا نشد، چند لحظه بعد امتحان کن"),
    charge_svc.NOT_OPEN: (409, "این درخواست شارژ دیگر باز نیست"),
    charge_svc.BAD_IMAGE: (400, "فقط عکس رسید (JPG یا PNG) تا ۳ مگابایت"),
    charge_svc.NO_ADMIN: (503, "رسید به پشتیبانی نرسید؛ دوباره امتحان کن"),
    charge_svc.ALREADY_SENT: (409, "رسید این شارژ قبلا فرستاده شده و در حال بررسی است"),
}


def _charge_error(r: dict) -> None:
    status, msg = _CHARGE_ERR.get(r.get("error"), (400, "انجام نشد"))
    if r.get("error") == charge_svc.TOO_SMALL and r.get("min"):
        msg = f"حداقل شارژ {r['min']:,} تومان است"
    raise ApiError(msg, status, r.get("error") or "")


async def topup_start(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, amount: int) -> dict:
    user = await _require_user(db, wuser)
    r = await charge_svc.start(db, user, amount)
    if not r["ok"]:
        _charge_error(r)
    return {"txn_id": r["txn_id"], "amount": r["amount"], "card": await charge_svc.card(db), "resumed": r.get("resumed", False)}


async def topup_receipt(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, txn_id: int, image: bytes, bot=None) -> dict:  # noqa: ANN001
    user = await _require_user(db, wuser)
    r = await charge_svc.attach_receipt(bot, db, user, txn_id, image)
    if not r["ok"]:
        _charge_error(r)
    return {"ok": True, "code": r.get("code"), "amount": r["amount"]}


async def rules(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    user = await _require_user(db, wuser)
    return {
        "enabled": await db.get_setting("rules_enabled", "1") == "1",
        "text": _latin(await db.get_setting("rules_text", "") or ""),
        "accepted": bool(user.get("rules_accepted_at")),
        "accepted_at": user.get("rules_accepted_at"),
    }


async def rules_accept(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    user = await _require_user(db, wuser)
    await db.accept_rules(user["id"])
    return {"ok": True}


async def guide(db: "Database", panel: "Panel | None", wuser: WebAppUser) -> dict:
    """راهنمای اتصال؛ همان متن های ربات، با ارقام لاتین."""
    await _require_user(db, wuser)
    from app import texts
    names = {"android": "اندروید", "ios": "آیفون", "windows": "ویندوز", "mac": "مک", "linux": "لینوکس"}
    items = []
    for key, body in getattr(texts, "GUIDE", {}).items():
        lines = _latin(body).strip().split("\n")
        items.append({"key": key, "title": names.get(key, lines[0].strip()), "body": "\n".join(lines[1:]).strip()})
    return {"items": items}


async def ticket_send(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, body: str, bot=None) -> dict:  # noqa: ANN001
    user = await _require_user(db, wuser)
    body = (body or "").strip()
    if len(body) < 2:
        raise ApiError("پیام خیلی کوتاه است", 400, "empty")
    r = await support_svc.send(bot, db, user, body)
    if not r["ok"]:
        raise ApiError("پیام خالی است", 400, "empty")
    return {"ok": True, "thread_id": r["thread_id"], "code": r["code"], "is_new": r["is_new"]}


# ═══════════════════ نوشتن ═══════════════════


async def purchase(
    db: "Database",
    panel: "Panel | None",
    wuser: WebAppUser,
    *,
    plan_id: int,
    nonce: str,
    bot=None,  # noqa: ANN001
) -> dict:
    """خرید از مینی اپ.

    منطق خرید اینجا نیست: همان app/services/purchase.py است که ربات
    هم از آن رد می شود. کار این تابع فقط دروازه بانی و ترجمه است.

    دروازه ها عمدا همان هایی اند که ربات دارد. مینی اپ نباید راه میانبر
    باشد: اگر کاربر قوانین را نپذیرفته یا بخش فروش خاموش است، همان طور
    متوقف می شود که در ربات می شد.
    """
    user = await _require_user(db, wuser)

    if not features.is_on("shop_vpn"):
        raise ApiError("فروشگاه فعلا خاموش است", 403, "feature_off")

    # دروازه قوانین - همان شرطی که میان افزار ربات می سنجد
    if not user.get("rules_accepted_at"):
        if await db.get_setting("rules_enabled", "1") == "1":
            raise ApiError("اول باید قوانین را در ربات بپذیری", 403, "rules")

    plan = await db.get_plan(plan_id)
    if not plan or not plan["is_active"]:
        raise ApiError("این پلن دیگر موجود نیست", 404, "plan_unavailable")

    # idem از nonce کلاینت ساخته می شود. کلاینت برای هر بار زدن دکمه
    # «تایید» یک nonce تازه می سازد، پس دابل کلیک و ارسال دوباره روی
    # شبکه ضعیف یک خرید می شود، ولی خرید بعدی کاربر آزاد است.
    idem = f"wa:{wuser.id}:{nonce}"[:120]

    result = await purchase_svc.purchase(
        db, panel, user, plan, label="", idem=idem, discount=None
    )

    if not result.ok:
        status, msg = _PURCHASE_ERRORS.get(
            result.error, (400, "خرید انجام نشد")
        )
        raise ApiError(msg, status, result.error)

    # پاداش معرف. خطایش داخل خودش لاگ می شود و خرید را نمی شکند.
    if bot is not None:
        try:
            await referral.reward_purchase(
                bot, db, user, result.price, result.txn_id,
                f"سرویس {plan['title']} رو خرید",
            )
        except Exception:  # noqa: BLE001
            log.warning("پاداش معرف ثبت نشد txn=%s", result.txn_id, exc_info=True)

    return {
        "ok": True,
        "service_id": result.service_id,
        "sub_url": result.sub_url,
        "title": result.label or f"سرویس {result.service_id}",
        "price": result.price,
        "balance": result.balance_after,
        "plan": {"title": plan["title"], "data_gb": plan["data_gb"],
                 "duration_days": plan["duration_days"]},
    }


# کد خطای سرویس -> (کد HTTP، متنی که کاربر مینی اپ می بیند)
_PURCHASE_ERRORS = {
    purchase_svc.PLAN_UNAVAILABLE: (404, "این پلن دیگر موجود نیست"),
    purchase_svc.PANEL_BUSY: (503, "پنل در دسترس نیست، چند دقیقه دیگر امتحان کن"),
    purchase_svc.LOCKED: (409, "یه پرداخت همین حالا در جریانه"),
    purchase_svc.DUPLICATE: (409, "این خرید در حال پردازشه"),
    purchase_svc.NAME_FAILED: (502, "ساخت سرویس نشد، پولی کم نشده"),
    purchase_svc.PANEL_ERROR: (502, "ساخت سرویس نشد، پولی کم نشده"),
    purchase_svc.INSUFFICIENT: (402, "موجودی کیف پولت کافی نیست"),
}


# نگاشت مسیر -> تابع. فقط همین ها در دسترس اند.
ROUTES = {
    "bootstrap": bootstrap,
    "services": services_list,
    "wallet": wallet,
    "plans": plans,
    "referral": referral,
    "tickets": tickets,
    "ai": ai_catalog,
    "topup": topup_info,
    "rules": rules,
    "guide": guide,
}

__all__ = ["ROUTES", "ApiError", "service_detail", "ticket_thread", "qr_payload", "qr_svg", "purchase"]
