"""خرید خدمات هوش مصنوعی از canboso (کاتالوگ کامل، نه یک محصول ثابت).

منطق خرید، قیمت و حل سفارش مبهم در app/services/ai_shop.py است؛ اینجا
فقط گفتگوی ربات:

    فروشگاه ← خدمات هوش مصنوعی ← فهرست محصولات (قیمت تومانی روی دکمه)
    ← کارت محصول ← [مدت] ← [ایمیل] ← تایید ← خرید و تحویل

اطلاعات انتخاب شده (محصول، مدت، ایمیل) در FSM نگه داشته می شود و موقع
خرید، محصول و قیمت دوباره از خود سرویس دهنده خوانده می شود.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app import features, i18n, keyboards, pricing, texts, ui
from app.canboso import CanbosoError
from app.db import Database
from app.i18n import t as _t
from app.services import ai_shop
from app.states import AiShop
from app.ui import edit_or_send
from app.utils import esc

log = logging.getLogger("obour.ai")
router = Router(name="ai")


async def _client(db: Database):  # noqa: ANN202
    """برای پنل ادمین (موجودی)."""
    return await ai_shop.client(db)


async def _items(db: Database) -> list[dict] | None:
    try:
        return (await ai_shop.catalog(db))["items"]
    except CanbosoError as exc:
        log.warning("کاتالوگ canboso خوانده نشد: %s", exc)
        return None


async def show_catalog(message: Message, db: Database, user: dict) -> None:
    """صفحه خدمات هوش مصنوعی (از فروشگاه ربات صدا زده می شود)."""
    items = await _items(db)
    if items is None:
        return await edit_or_send(message, texts.AI_PROVIDER_DOWN, keyboards.back_to_shop_kb())
    if not items:
        return await edit_or_send(message, texts.AI_SHOP_SOON.format(balance=f"{user['balance']:,}"),
                                  keyboards.back_to_shop_kb())
    await edit_or_send(
        message,
        texts.AI_SHOP.format(count=len(items), balance=f"{user['balance']:,}"),
        keyboards.ai_shop_kb(items),
    )


@router.callback_query(F.data == "ai:buy")
async def cb_ai_catalog(call: CallbackQuery, db: Database, user: dict) -> None:
    if not features.is_on("shop_ai"):
        return await call.answer(texts.SECTION_OFF, show_alert=True)
    await show_catalog(call.message, db, user)
    await call.answer()


async def _item(db: Database, pid: str) -> dict | None:
    items = await _items(db)
    return next((x for x in items or [] if x["id"] == pid), None)


def _card(item: dict, balance: int) -> str:
    stock = texts.AI_STOCK.format(n=item["stock"]) if item["stock"] is not None else texts.AI_STOCK_OPEN
    desc = esc(item["description"].strip())[:700]
    price = f"{item['price']:,}" if not item["months"] else f"{min(item['month_prices'].values()):,}+"
    return texts.AI_PRODUCT.format(
        name=esc(item["name"]), stock=stock,
        description=(desc + "\n\n") if desc else "",
        how=texts.AI_HOW.get(item.get("kind") or item["type"], texts.AI_HOW["account"]),
        price=price, balance=f"{balance:,}",
    )


@router.callback_query(F.data.startswith("ai:p:"))
async def cb_ai_product(call: CallbackQuery, db: Database, state: FSMContext, user: dict) -> None:
    """کارت یک محصول."""
    if not features.is_on("shop_ai"):
        return await call.answer(texts.SECTION_OFF, show_alert=True)
    pid = call.data[len("ai:p:"):]
    item = await _item(db, pid)
    if item is None:
        return await call.answer(texts.AI_UNAVAILABLE, show_alert=True)
    if not item["available"]:
        await edit_or_send(call.message, texts.AI_TEMP_UNAVAILABLE, keyboards.ai_notify_kb())
        return await call.answer()
    await state.clear()
    await state.update_data(ai_pid=pid)
    await edit_or_send(call.message, _card(item, int(user["balance"])), keyboards.ai_product_kb(item, int(user["balance"])))
    await call.answer()


async def product_from_start(message: Message, db: Database, state: FSMContext, user: dict, pid: str) -> bool:
    """کارت محصول از لینک عمیق start=ai_<id> (دکمه مینی اپ). False = پیدا نشد."""
    item = await _item(db, pid)
    if item is None:
        return False
    if not item["available"]:
        await message.answer(texts.AI_TEMP_UNAVAILABLE, reply_markup=keyboards.ai_notify_kb())
        return True
    await state.update_data(ai_pid=pid)
    await message.answer(_card(item, int(user["balance"])), reply_markup=keyboards.ai_product_kb(item, int(user["balance"])))
    return True


async def _ask_email(message: Message, state: FSMContext, name: str, edit: bool = True) -> None:
    await state.set_state(AiShop.waiting_email)
    body = texts.AI_ASK_EMAIL.format(name=esc(name))
    if edit:
        await edit_or_send(message, body, keyboards.back_to_shop_kb())
    else:
        await message.answer(body, reply_markup=keyboards.back_to_shop_kb())


async def _confirm(message: Message, db: Database, state: FSMContext, user: dict, edit: bool = True) -> None:
    """صفحه تایید نهایی با خلاصه انتخاب ها."""
    data = await state.get_data()
    item = await _item(db, data.get("ai_pid") or "")
    if item is None or not item["available"]:
        return await edit_or_send(message, texts.AI_TEMP_UNAVAILABLE, keyboards.ai_notify_kb())
    months = data.get("ai_months")
    price = item["month_prices"].get(months, item["price"]) if item["months"] else item["price"]
    details = ""
    if months:
        details += "🗓 " + _t("مدت") + f": <b>{months}</b> " + _t("ماه") + "\n"
    if data.get("ai_email"):
        details += "📧 " + _t("ایمیل") + f": <code>{esc(data['ai_email'])}</code>\n"
    body = texts.AI_CONFIRM.format(name=esc(item["name"]), details=(details + "\n") if details else "",
                                   price=f"{price:,}", balance=f"{user['balance']:,}")
    kb = keyboards.ai_confirm_kb(price <= int(user["balance"]))
    if edit:
        await edit_or_send(message, body, kb)
    else:
        await message.answer(body, reply_markup=kb)


@router.callback_query(F.data.startswith("ai:m:"))
async def cb_ai_months(call: CallbackQuery, db: Database, state: FSMContext, user: dict) -> None:
    """انتخاب مدت برای اشتراک ماهانه."""
    try:
        _, _, pid, m = call.data.split(":", 3)
        months = int(m)
    except ValueError:
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)
    item = await _item(db, pid)
    if item is None or months not in item["months"]:
        return await call.answer(texts.AI_UNAVAILABLE, show_alert=True)
    await state.update_data(ai_pid=pid, ai_months=months)
    if item["month_prices"][months] > int(user["balance"]):
        await _confirm(call.message, db, state, user)
    elif item["needs_email"]:
        await _ask_email(call.message, state, item["name"])
    else:
        await _confirm(call.message, db, state, user)
    await call.answer()


@router.callback_query(F.data.startswith("ai:e:"))
async def cb_ai_email(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    pid = call.data[len("ai:e:"):]
    item = await _item(db, pid)
    if item is None:
        return await call.answer(texts.AI_UNAVAILABLE, show_alert=True)
    await state.update_data(ai_pid=pid)
    await _ask_email(call.message, state, item["name"])
    await call.answer()


@router.message(AiShop.waiting_email, F.text)
async def msg_ai_email(message: Message, db: Database, state: FSMContext, user: dict) -> None:
    email = (message.text or "").strip()
    if not ai_shop.EMAIL_RE.match(email) or len(email) > 120:
        return await message.answer(texts.AI_BAD_EMAIL)
    await ui.consume(message)
    await state.set_state(None)
    await state.update_data(ai_email=email)
    await _confirm(message, db, state, user, edit=False)


@router.callback_query(F.data.startswith("ai:ok:"))
async def cb_ai_buy_direct(call: CallbackQuery, db: Database, state: FSMContext, user: dict) -> None:
    """خرید مستقیم محصولی که ورودی اضافه نمی خواهد."""
    pid = call.data[len("ai:ok:"):]
    await state.update_data(ai_pid=pid, ai_months=None, ai_email=None)
    await _buy(call, db, state, user)


@router.callback_query(F.data == "ai:go")
async def cb_ai_buy_confirmed(call: CallbackQuery, db: Database, state: FSMContext, user: dict) -> None:
    await _buy(call, db, state, user)


async def _buy(call: CallbackQuery, db: Database, state: FSMContext, user: dict) -> None:
    if not features.is_on("shop_ai"):
        return await call.answer(texts.SECTION_OFF, show_alert=True)
    data = await state.get_data()
    pid = data.get("ai_pid")
    if not pid:
        return await call.answer(_t("یه اشتباهی پیش اومد. دوباره از فروشگاه شروع کن."), show_alert=True)
    await call.answer()
    await edit_or_send(call.message, texts.AI_WORKING, None)
    try:
        r = await ai_shop.buy(db, call.bot, user, pid, months=data.get("ai_months"), email=data.get("ai_email"))
    except Exception:  # noqa: BLE001
        log.exception("خرید هوش مصنوعی شکست خورد")
        return await edit_or_send(call.message, texts.AI_PROVIDER_DOWN, keyboards.back_to_shop_kb())
    await state.clear()
    await show_result(call.message, r)


async def show_result(message: Message, r: dict, edit: bool = True) -> None:
    """پیام نتیجه خرید (برای خریدار، به زبان خودش)."""
    status, order = r["status"], r.get("order") or {}
    kb = keyboards.back_to_shop_kb()
    if status == ai_shop.DELIVERED:
        body = texts.AI_DELIVERED.format(name=esc(order["title"]), delivery=ai_shop.delivery_html(order) or "—",
                                         code=order["code"], provider_code=order.get("provider_order_id") or "-")
        kb = keyboards.ai_delivered_kb()
    elif status == ai_shop.PROCESSING:
        email = ai_shop.delivery_of(order).get("email") or "-"
        body = texts.AI_ACCEPTED.format(name=esc(order["title"]), email=esc(email), code=order["code"],
                                        provider_code=order.get("provider_order_id") or "-")
        kb = keyboards.ai_delivered_kb()
    elif status == ai_shop.UNKNOWN:
        body = texts.AI_PENDING_REVIEW.format(code=order["code"])
    elif status in (ai_shop.FAILED, ai_shop.NO_FUNDS) and order:
        body = texts.AI_FAILED_REFUNDED.format(price=f"{order['price']:,}")
    elif status == ai_shop.INSUFFICIENT:
        body, kb = texts.INSUFFICIENT, keyboards.insufficient_kb()
    elif status == ai_shop.UNAVAILABLE:
        body, kb = texts.AI_TEMP_UNAVAILABLE, keyboards.ai_notify_kb()
    elif status == ai_shop.LOCKED:
        body = texts.AI_IN_PROGRESS
    elif status == ai_shop.NOT_CONFIGURED:
        body = texts.AI_NOT_CONFIGURED
    else:
        body = texts.AI_PROVIDER_DOWN
    if edit:
        await edit_or_send(message, body, kb)
    else:
        await message.answer(body, reply_markup=kb)


@router.callback_query(F.data == "ai:notify")
async def cb_ai_notify_me(call: CallbackQuery, db: Database, user: dict) -> None:
    """ثبت نام در فهرست انتظار موجود شدن."""
    added = await db.ai_waitlist_add(user["id"])
    await call.answer(
        _t("باشه، به محض موجود شدن خبرت می کنیم ✅") if added
        else _t("قبلا ثبت نامت رو داشتیم، صبر کن 🔔"),
        show_alert=True,
    )


@router.callback_query(F.data == "ai:mine")
async def cb_ai_orders(call: CallbackQuery, db: Database, user: dict) -> None:
    """سفارش های هوش مصنوعی کاربر، با اطلاعات تحویل."""
    orders = await db.user_ai_orders(user["id"])
    if not orders:
        await edit_or_send(call.message, texts.AI_ORDERS_EMPTY, keyboards.back_to_shop_kb())
        return await call.answer()
    blocks = []
    for o in orders:
        info = ai_shop.delivery_html(o)
        provider = f" · {o['provider_order_id']}" if o.get("provider_order_id") else ""
        blocks.append(texts.AI_ORDER_ROW.format(
            status=texts.AI_STATUS.get(o["status"], o["status"]),
            title=esc(o["title"]), code=o["code"] + provider, price=f"{o['price']:,}",
            links=("\n" + info) if info and o["status"] in (ai_shop.DELIVERED, ai_shop.PROCESSING) else "",
        ))
    await edit_or_send(call.message, texts.AI_ORDERS.format(count=len(orders), rows="\n\n".join(blocks)),
                       keyboards.back_to_shop_kb())
    await call.answer()


async def notify_buyer(bot, db: Database, r: dict) -> None:  # noqa: ANN001
    """بعد از «بررسی دوباره» ادمین، نتیجه به خود خریدار (به زبان او) می رسد."""
    order = r.get("order") or {}
    user = await db.get_user(order.get("user_id")) if order else None
    if not user or r["status"] not in (ai_shop.DELIVERED, ai_shop.PROCESSING, ai_shop.FAILED, ai_shop.NO_FUNDS):
        return
    with i18n.using(i18n.lang_of(user)):
        if r["status"] == ai_shop.DELIVERED:
            body = texts.AI_DELIVERED.format(name=esc(order["title"]), delivery=ai_shop.delivery_html(order) or "—",
                                             code=order["code"], provider_code=order.get("provider_order_id") or "-")
        elif r["status"] == ai_shop.PROCESSING:
            body = texts.AI_ACCEPTED.format(name=esc(order["title"]), email=esc(ai_shop.delivery_of(order).get("email") or "-"),
                                            code=order["code"], provider_code=order.get("provider_order_id") or "-")
        else:
            body = texts.AI_FAILED_REFUNDED.format(price=f"{order['price']:,}")
    try:
        await bot.send_message(int(user["telegram_id"]), body)
    except Exception:  # noqa: BLE001
        log.warning("نتیجه سفارش %s به خریدار نرسید", order.get("code"))


__all__ = ["router", "show_catalog", "show_result", "notify_buyer", "pricing"]
