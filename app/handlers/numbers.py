"""شماره مجازی (SMSBurner): گرفتن شماره خارجی و کد تایید، داخل ربات.

منطق خرید، قیمت و استرداد در app/services/numbers_shop.py است؛ اینجا فقط
گفتگوی ربات:

    فروشگاه ← شماره مجازی ← سرویس (پرطرفدارها یا همه سرویس ها)
    ← کشور (ارزان ترین اول) ← تایید ← شماره + منتظر کد
    ← کد خودکار می رسد (یا «بررسی کد»)؛ «لغو» = برگشت پول

هیچ حالت FSM لازم نیست: هر انتخاب یک callback است و موقع خرید، قیمت و
موجودی دوباره و بدون کش از سرویس دهنده خوانده می شود.

کد پیامک را یک پایشگر پس زمینه می گیرد (مثل پایشگر پرداخت کریپتو). زیر
Passenger ممکن است پروسه خوابانده شود؛ پس کران خودکار هم هر دور همین
پایش را اجرا می کند و دکمه «بررسی کد» همیشه هست.
"""
from __future__ import annotations

import asyncio
import logging
import math

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app import features, i18n, keyboards, texts
from app.canboso import CanbosoError
from app.db import Database
from app.i18n import t as _t
from app.services import numbers_shop as ns
from app.ui import edit_or_send
from app.utils import esc, now

log = logging.getLogger("obour.numbers")
router = Router(name="numbers")

PAGE = keyboards.NUM_PAGE


# ═══════════════════ نمایش سفارش ═══════════════════


def _minutes_left(order: dict) -> int:
    from datetime import datetime

    try:
        end = datetime.fromisoformat(order["expires_at"])
    except (TypeError, ValueError):
        return 0
    return max(0, math.ceil((end - now()).total_seconds() / 60))


def order_view(order: dict) -> tuple[str, InlineKeyboardMarkup]:
    """متن و دکمه های یک سفارش بر اساس وضعیتش (به زبان جاری)."""
    st = order["status"]
    base = {
        "service": esc(order.get("service_name") or ""),
        "flag": ns.flag(order["country"]),
        "country": esc(ns.country_title(order["country"], order.get("country_name") or "")),
        "phone": esc(order.get("phone") or "-"),
        "code": order["code"],
    }
    price = f"{int(order['price']):,}"
    if st == ns.ACTIVE:
        return texts.NUM_ACTIVE.format(left=_minutes_left(order), **base), keyboards.num_active_kb(order["id"])
    if st == ns.COMPLETED:
        extra = (order.get("sms_text") or "").strip()
        sms_text = f"💬 <blockquote expandable>{esc(extra)}</blockquote>\n" if extra and extra != order.get("sms_code") else ""
        return (texts.NUM_CODE.format(sms_code=esc(order.get("sms_code") or "-"), sms_text=sms_text, **base),
                keyboards.num_done_kb(order["service_id"]))
    if st == ns.REFUNDED:
        return texts.NUM_REFUNDED.format(price=price, **base), keyboards.num_done_kb(order["service_id"])
    if st == ns.FAILED:
        return texts.NUM_FAILED_REFUNDED.format(price=price), keyboards.num_done_kb(order["service_id"])
    return texts.NUM_PENDING_REVIEW.format(code=order["code"]), keyboards.num_back_kb("num:mine")


async def notify_event(bot, db: Database, r: dict) -> None:  # noqa: ANN001
    """کد رسید یا پول برگشت: به خریدار، به زبان خودش، همراه به روز کردن پیام قبلی."""
    order = r.get("order") or {}
    user = await db.get_user(order.get("user_id")) if order else None
    if not user:
        return
    with i18n.using(i18n.lang_of(user)):
        text, kb = order_view(order)
    if order.get("chat_id") and order.get("message_id"):
        try:
            await bot.edit_message_text(text, chat_id=order["chat_id"], message_id=order["message_id"], reply_markup=kb)
        except Exception:  # noqa: BLE001  (پیام پاک شده یا تغییری نکرده)
            pass
    try:
        # پیام تازه، چون ویرایش نوتیف نمی دهد و کاربر شاید توی اپ دیگری منتظر کد باشد
        await bot.send_message(int(user["telegram_id"]), text, reply_markup=kb)
    except Exception:  # noqa: BLE001
        log.warning("نتیجه سفارش شماره %s به خریدار نرسید", order.get("code"))


async def send_order(bot, db: Database, order: dict) -> None:  # noqa: ANN001
    """وقتی خرید از مینی اپ بوده: صفحه سفارش در چت ربات هم می آید (و به روز می شود)."""
    user = await db.get_user(order["user_id"])
    if not user:
        return
    with i18n.using(i18n.lang_of(user)):
        text, kb = order_view(order)
    try:
        m = await bot.send_message(int(user["telegram_id"]), text, reply_markup=kb)
        await db.update_number_order(order["id"], chat_id=m.chat.id, message_id=m.message_id)
    except Exception:  # noqa: BLE001
        log.warning("صفحه سفارش شماره %s به خریدار نرسید", order.get("code"))
    ensure_watcher(db, bot)


# ═══════════════════ پایشگر کد ═══════════════════

_watcher: asyncio.Task | None = None


async def sweep(db: Database, bot) -> int:  # noqa: ANN001
    """یک دور پایش همه شماره های منتظر کد. تعداد سفارش های باز را برمی گرداند."""
    orders = await ns.active_orders(db)
    if not orders:
        return 0
    sb = await ns.client(db)
    try:
        for o in orders:
            try:
                r = await ns.check(db, o, sb)
            except Exception:  # noqa: BLE001
                log.warning("پایش سفارش شماره %s خطا داد", o.get("code"), exc_info=True)
                continue
            if r.get("event"):
                await notify_event(bot, db, r)
    finally:
        await sb.close()
    return len(orders)


def ensure_watcher(db: Database, bot) -> None:  # noqa: ANN001
    """تا وقتی شماره منتظر کد هست، هر چند ثانیه یک بار می پرسد؛ بعد خودش تمام می شود."""
    global _watcher
    if _watcher is not None and not _watcher.done():
        return
    try:
        _watcher = asyncio.get_running_loop().create_task(_watch(db, bot))
    except RuntimeError:
        pass


async def _watch(db: Database, bot) -> None:  # noqa: ANN001
    idle = 0
    while True:
        try:
            open_n = await sweep(db, bot)
        except Exception:  # noqa: BLE001
            log.warning("پایش شماره مجازی خطا داد", exc_info=True)
            open_n = 1
        idle = 0 if open_n else idle + 1
        if idle >= 2:
            return
        await asyncio.sleep(6)


# ═══════════════════ فهرست سرویس و کشور ═══════════════════


async def _gate(call: CallbackQuery, db: Database, user: dict) -> bool:
    """بخش خاموش یا هنوز تنظیم نشده؛ False یعنی پاسخ داده شد و ادامه نده."""
    if not features.is_on("shop_numbers"):
        await call.answer(texts.SECTION_OFF, show_alert=True)
        return False
    if not await ns.ready(db):
        await edit_or_send(call.message, texts.NUM_SOON.format(balance=f"{user['balance']:,}"),
                           keyboards.num_back_kb("buy"))
        await call.answer()
        return False
    return True


async def _catalog(message: Message, db: Database, back: str = "buy") -> dict | None:
    try:
        return await ns.catalog(db)
    except CanbosoError as exc:
        log.warning("کاتالوگ شماره مجازی خوانده نشد: %s", exc)
        await edit_or_send(message, texts.NUM_PROVIDER_DOWN, keyboards.num_back_kb(back))
        return None


async def show_hub(message: Message, db: Database, user: dict) -> None:
    cat = await _catalog(message, db)
    if cat is None:
        return
    services = ns.services_of(cat)
    popular = [s for s in services if s["slug"] in ns.POPULAR][:12] or services[:12]
    await edit_or_send(message, texts.NUM_HUB.format(balance=f"{user['balance']:,}"), keyboards.num_hub_kb(popular))


@router.callback_query(F.data == "num")
async def cb_hub(call: CallbackQuery, db: Database, user: dict) -> None:
    if not await _gate(call, db, user):
        return
    await show_hub(call.message, db, user)
    await call.answer()


@router.callback_query(F.data == "num:cats")
async def cb_cats(call: CallbackQuery, db: Database, user: dict) -> None:
    if not await _gate(call, db, user):
        return
    cat = await _catalog(call.message, db, "num")
    if cat is None:
        return await call.answer()
    services = ns.services_of(cat)
    counts: dict[str, int] = {}
    for s in services:
        counts[s["category"]] = counts.get(s["category"], 0) + 1
    cats = [{"key": k, "title": ns.cat_title(k)[0], "emoji": ns.cat_title(k)[1], "count": n}
            for k, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    await edit_or_send(call.message, texts.NUM_CATS.format(count=len(services)), keyboards.num_cats_kb(cats))
    await call.answer()


@router.callback_query(F.data.startswith("num:c:"))
async def cb_cat(call: CallbackQuery, db: Database, user: dict) -> None:
    if not await _gate(call, db, user):
        return
    try:
        _, _, key, page_s = call.data.split(":", 3)
        page = max(0, int(page_s))
    except ValueError:
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)
    cat = await _catalog(call.message, db, "num")
    if cat is None:
        return await call.answer()
    items = sorted((s for s in ns.services_of(cat) if s["category"] == key), key=lambda s: s["name"].lower())
    if not items:
        return await call.answer(texts.NUM_EMPTY_CAT, show_alert=True)
    pages = ns.pages(len(items), PAGE)
    page = min(page, pages - 1)
    title, emoji = ns.cat_title(key)
    await edit_or_send(
        call.message,
        texts.NUM_SERVICES.format(emoji=emoji, title=_t(title), count=len(items), page=page + 1, pages=pages),
        keyboards.num_services_kb(items[page * PAGE:(page + 1) * PAGE], key, page, pages),
    )
    await call.answer()


async def show_countries(message: Message, db: Database, user: dict, service_id: str, page: int = 0) -> bool:
    """کشورهای یک سرویس؛ False اگر سرویس شماره ای ندارد."""
    cat = await _catalog(message, db, "num")
    if cat is None:
        return True
    rows = ns.countries_of(cat, service_id)
    if not rows:
        await edit_or_send(message, texts.NUM_UNAVAILABLE, keyboards.num_back_kb("num"))
        return True
    pages = ns.pages(len(rows), PAGE)
    page = max(0, min(page, pages - 1))
    await edit_or_send(
        message,
        texts.NUM_COUNTRIES.format(service=esc(rows[0]["service"]), balance=f"{user['balance']:,}",
                                   page=page + 1, pages=pages),
        keyboards.num_countries_kb(rows[page * PAGE:(page + 1) * PAGE], service_id, page, pages),
    )
    return True


@router.callback_query(F.data.startswith("num:s:"))
async def cb_service(call: CallbackQuery, db: Database, user: dict) -> None:
    if not await _gate(call, db, user):
        return
    try:
        _, _, sid, page_s = call.data.split(":", 3)
        page = int(page_s)
    except ValueError:
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)
    await show_countries(call.message, db, user, sid, page)
    await call.answer()


@router.callback_query(F.data.startswith("num:b:"))
async def cb_confirm(call: CallbackQuery, db: Database, user: dict) -> None:
    if not await _gate(call, db, user):
        return
    try:
        _, _, sid, cc = call.data.split(":", 3)
    except ValueError:
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)
    cat = await _catalog(call.message, db, "num")
    if cat is None:
        return await call.answer()
    row = ns.row_of(cat, sid, cc)
    if row is None:
        await edit_or_send(call.message, texts.NUM_UNAVAILABLE, keyboards.num_back_kb(f"num:s:{sid}:0"))
        return await call.answer()
    await edit_or_send(
        call.message,
        texts.NUM_CONFIRM.format(service=esc(row["service"]), flag=ns.flag(cc),
                                 country=esc(ns.country_title(cc, row["country"])),
                                 price=f"{row['price']:,}", balance=f"{user['balance']:,}"),
        keyboards.num_confirm_kb(row["price"] <= int(user["balance"]), sid, cc),
    )
    await call.answer()


# ═══════════════════ خرید ═══════════════════


async def show_buy_result(message: Message, db: Database, bot, r: dict, sid: str) -> None:  # noqa: ANN001
    """پیام نتیجه خرید (برای خریدار، به زبان خودش)."""
    status, order = r["status"], r.get("order") or {}
    if status in (ns.ACTIVE, ns.COMPLETED):
        text, kb = order_view(order)
        m = await edit_or_send(message, text, kb)
        try:
            await db.update_number_order(order["id"], chat_id=m.chat.id, message_id=m.message_id)
        except Exception:  # noqa: BLE001
            pass
        if status == ns.ACTIVE:
            ensure_watcher(db, bot)
        return
    kb = keyboards.num_back_kb(f"num:s:{sid}:0")
    if status == ns.UNKNOWN:
        body, kb = texts.NUM_PENDING_REVIEW.format(code=order.get("code", "")), keyboards.num_back_kb("num:mine")
    elif status == ns.INSUFFICIENT:
        body, kb = texts.INSUFFICIENT, keyboards.insufficient_kb()
    elif status == ns.UNAVAILABLE:
        body = texts.NUM_UNAVAILABLE
    elif status in (ns.NO_FUNDS, ns.PROVIDER_ERROR) and order:
        body = texts.NUM_FAILED_REFUNDED.format(price=f"{int(order['price']):,}")
    elif status == ns.LOCKED:
        body = texts.NUM_IN_PROGRESS
    elif status == ns.NOT_CONFIGURED:
        body = texts.NUM_NOT_CONFIGURED
    else:
        body = texts.NUM_PROVIDER_DOWN
    await edit_or_send(message, body, kb)


@router.callback_query(F.data.startswith("num:go:"))
async def cb_buy(call: CallbackQuery, db: Database, user: dict) -> None:
    if not await _gate(call, db, user):
        return
    try:
        _, _, sid, cc = call.data.split(":", 3)
    except ValueError:
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)
    await call.answer()
    await edit_or_send(call.message, texts.NUM_WORKING, None)
    try:
        r = await ns.buy(db, call.bot, user, sid, cc)
    except Exception:  # noqa: BLE001
        log.exception("خرید شماره مجازی شکست خورد")
        return await edit_or_send(call.message, texts.NUM_PROVIDER_DOWN, keyboards.num_back_kb(f"num:s:{sid}:0"))
    await show_buy_result(call.message, db, call.bot, r, sid)


# ═══════════════════ پیگیری، لغو، سفارش ها ═══════════════════


async def _own(call: CallbackQuery, db: Database, user: dict, oid: str) -> dict | None:
    try:
        order = await db.get_number_order(int(oid))
    except ValueError:
        order = None
    if not order or order["user_id"] != user["id"]:
        await call.answer(texts.NUM_NO_ORDER, show_alert=True)
        return None
    return order


@router.callback_query(F.data.startswith("num:o:"))
async def cb_order(call: CallbackQuery, db: Database, user: dict) -> None:
    order = await _own(call, db, user, call.data[len("num:o:"):])
    if order is None:
        return
    text, kb = order_view(order)
    await edit_or_send(call.message, text, kb)
    await call.answer()


@router.callback_query(F.data.startswith("num:chk:"))
async def cb_check(call: CallbackQuery, db: Database, user: dict) -> None:
    order = await _own(call, db, user, call.data[len("num:chk:"):])
    if order is None:
        return
    if order["status"] != ns.ACTIVE:
        text, kb = order_view(order)
        await edit_or_send(call.message, text, kb)
        return await call.answer()
    r = await ns.check(db, order)
    order = r["order"]
    text, kb = order_view(order)
    await edit_or_send(call.message, text, kb)
    await db.update_number_order(order["id"], chat_id=call.message.chat.id, message_id=call.message.message_id)
    if order["status"] == ns.ACTIVE:
        ensure_watcher(db, call.bot)
        await call.answer(texts.NUM_STILL_WAITING if r["status"] != ns.PROVIDER_ERROR else texts.NUM_PROVIDER_DOWN)
    else:
        await call.answer()


@router.callback_query(F.data.startswith("num:x:"))
async def cb_cancel_ask(call: CallbackQuery, db: Database, user: dict) -> None:
    order = await _own(call, db, user, call.data[len("num:x:"):])
    if order is None:
        return
    if order["status"] != ns.ACTIVE:
        text, kb = order_view(order)
        await edit_or_send(call.message, text, kb)
        return await call.answer()
    await edit_or_send(call.message, texts.NUM_CANCEL_ASK.format(price=f"{int(order['price']):,}"),
                       keyboards.num_cancel_ask_kb(order["id"]))
    await call.answer()


@router.callback_query(F.data.startswith("num:xy:"))
async def cb_cancel(call: CallbackQuery, db: Database, user: dict) -> None:
    order = await _own(call, db, user, call.data[len("num:xy:"):])
    if order is None:
        return
    r = await ns.cancel(db, order)
    order = r.get("order") or order
    if r["status"] in (ns.CANT_CANCEL, ns.PROVIDER_ERROR):
        text, kb = order_view(order)
        await edit_or_send(call.message, text, kb)
        return await call.answer(texts.NUM_CANT_CANCEL.format(error=r.get("error") or "-"), show_alert=True)
    text, kb = order_view(order)
    await edit_or_send(call.message, text, kb)
    await call.answer()


@router.callback_query(F.data == "num:mine")
async def cb_mine(call: CallbackQuery, db: Database, user: dict) -> None:
    orders = await db.user_number_orders(user["id"], limit=10)
    if not orders:
        await edit_or_send(call.message, texts.NUM_ORDERS_EMPTY, keyboards.num_orders_kb([]))
        return await call.answer()
    blocks = []
    for o in orders:
        code_line = ""
        if o["status"] == ns.COMPLETED and o.get("sms_code"):
            code_line = f"\n│  🔑 <code>{esc(o['sms_code'])}</code>"
        blocks.append(texts.NUM_ORDER_ROW.format(
            status=texts.NUM_STATUS.get(o["status"], o["status"]), service=esc(o.get("service_name") or ""),
            flag=ns.flag(o["country"]), phone=esc(o.get("phone") or "-"),
            price=f"{int(o['price']):,}", code_line=code_line))
    await edit_or_send(call.message, texts.NUM_ORDERS.format(count=len(orders), rows="\n\n".join(blocks)),
                       keyboards.num_orders_kb([o for o in orders if o["status"] == ns.ACTIVE]))
    await call.answer()


async def open_from_start(message: Message, db: Database, user: dict, payload: str) -> bool:
    """لینک عمیق start=num یا start=num_<service_id> (دکمه مینی اپ). False = بخش آماده نیست."""
    if not features.is_on("shop_numbers") or not await ns.ready(db):
        return False
    sent = await message.answer("…")
    sid = payload[len("num_"):] if payload.startswith("num_") else ""
    if sid.isdigit():
        await show_countries(sent, db, user, sid)
    else:
        await show_hub(sent, db, user)
    return True


__all__ = ["router", "sweep", "ensure_watcher", "notify_event", "send_order", "order_view", "open_from_start"]
