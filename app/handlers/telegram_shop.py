"""پرمیوم و استارز تلگرام (MarketApp) داخل ربات.

منطق قیمت، گیرنده، ساخت و بررسی سفارش در app/services/marketapp.py است؛ اینجا فقط
گفتگوی ربات:

    فروشگاه ← 💎 پرمیوم و استارز ← پرمیوم یا استارز ← گیرنده (خودم، اخیر یا یوزرنیم)
    ← پلن یا بسته (یا تعداد دلخواه) ← تایید ← نتیجه

فعلا خرید نمایشی است (marketapp.DEMO): همه مسیر API واقعی است جز امضا و ارسال
تراکنش، هیچ پولی کم نمی شود و هر صفحه ای که به خرید می رسد این را به کاربر می گوید.

گیرنده، نوع و مقدار در داده FSM می مانند (fsm_storage ماندگار است)؛ تایید نهایی
دوباره قیمت و گیرنده را بدون کش از API می خواند.
"""
from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app import features, keyboards, texts
from app.db import Database
from app.i18n import t as _t
from app.services import marketapp as mk
from app.states import TgShop
from app.ui import edit_or_send
from app.utils import esc

log = logging.getLogger("obour.tgshop")
router = Router(name="tgshop")

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# متنی که اصلا شبیه یوزرنیم نیست (مثلا کاربر از منو رفته و حالا چیز دیگری می نویسد)
_LOOKS_LIKE_USERNAME = re.compile(r"\s*(https?://)?(t\.me/)?@?[A-Za-z0-9_.]{1,40}\s*")


def _demo(demo: bool) -> str:
    return texts.TG_DEMO_NOTE if demo else ""


def _product(kind: str) -> str:
    return "⭐ تلگرام پرمیوم" if kind == mk.PREMIUM else "🌟 استارز"


def _title(kind: str, amount: int) -> str:
    return mk.order_title({"kind": kind, "amount": amount})


async def _gate(call: CallbackQuery, db: Database, user: dict) -> bool:
    """بخش خاموش یا هنوز تنظیم نشده؛ False یعنی پاسخ داده شد و ادامه نده."""
    if not features.is_on("shop_telegram"):
        await call.answer(texts.SECTION_OFF, show_alert=True)
        return False
    if not await mk.ready(db):
        await edit_or_send(call.message, texts.TG_SOON.format(balance=f"{user['balance']:,}"),
                           keyboards.tg_back_kb("buy"))
        await call.answer()
        return False
    return True


async def show_hub(message: Message, db: Database, user: dict) -> None:
    demo = await mk.mode(db) == mk.DEMO
    await edit_or_send(
        message,
        texts.TG_HUB.format(balance=f"{user['balance']:,}", demo=_demo(demo),
                            min_stars=f"{mk.STARS_MIN:,}", max_stars=f"{mk.STARS_MAX:,}"),
        keyboards.tg_hub_kb(),
    )


@router.callback_query(F.data == "tg")
async def cb_hub(call: CallbackQuery, db: Database, user: dict, state: FSMContext) -> None:
    await state.set_state(None)
    if not await _gate(call, db, user):
        return
    await show_hub(call.message, db, user)
    await call.answer()


@router.callback_query(F.data.in_({"tg:k:premium", "tg:k:stars"}))
async def cb_kind(call: CallbackQuery, db: Database, user: dict, state: FSMContext) -> None:
    if not await _gate(call, db, user):
        return
    kind = call.data.split(":")[2]
    await state.set_state(TgShop.waiting_recipient)
    await state.update_data(tg_kind=kind)
    me = mk.clean_username(call.from_user.username or "")
    recents = await db.user_tg_recipients(user["id"])
    await edit_or_send(call.message, texts.TG_ASK_RECIPIENT.format(product=_product(kind)),
                       keyboards.tg_recipient_kb(kind, me, recents))
    await call.answer()


@router.callback_query(F.data.startswith("tg:r:"))
async def cb_recipient(call: CallbackQuery, db: Database, user: dict, state: FSMContext) -> None:
    if not await _gate(call, db, user):
        return
    try:
        _, _, kind, username = call.data.split(":", 3)
    except ValueError:
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)
    await call.answer()
    await _offer(call.message, db, user, state, kind, username, edit=True)


@router.message(TgShop.waiting_recipient, F.text)
async def msg_recipient(message: Message, db: Database, user: dict, state: FSMContext) -> None:
    if not _LOOKS_LIKE_USERNAME.fullmatch(message.text or ""):
        # حالت جا مانده؛ پیام مال جریان دیگری است
        await state.set_state(None)
        raise SkipHandler
    kind = (await state.get_data()).get("tg_kind") or mk.PREMIUM
    await _offer(message, db, user, state, kind, message.text or "", edit=False)


async def _offer(message: Message, db: Database, user: dict, state: FSMContext, kind: str, raw: str,
                 edit: bool) -> None:
    """گیرنده را با API بررسی می کند و پلن ها یا بسته ها را با قیمت تومانی نشان می دهد."""
    kind = kind if kind in mk.KINDS else mk.PREMIUM
    say = (lambda t, kb: edit_or_send(message, t, kb)) if edit else (lambda t, kb: message.answer(t, reply_markup=kb))
    rcp = await mk.recipient(db, kind, raw)
    if not rcp["ok"]:
        # در همان حالت انتظار می مانیم تا یوزرنیم دیگری بفرستد
        await state.set_state(TgShop.waiting_recipient)
        await state.update_data(tg_kind=kind)
        return await say(texts.TG_RECIPIENT_BAD.format(username=esc(raw.strip()[:40]), message=esc(_t(rcp["message"]))),
                         keyboards.tg_back_kb(f"tg:k:{kind}"))
    try:
        cat = await mk.catalog(db)
    except mk.MarketAppError as exc:
        log.warning("قیمت های MarketApp خوانده نشد: %s", exc)
        return await say(texts.TG_PROVIDER_DOWN, keyboards.tg_back_kb("tg"))
    await state.set_state(None)
    await state.update_data(tg_kind=kind, tg_rcp=rcp["username"], tg_rcp_name=rcp["name"])
    demo = await mk.mode(db) == mk.DEMO
    common = {"name": esc(rcp["name"]), "username": rcp["username"], "balance": f"{user['balance']:,}",
              "demo": _demo(demo)}
    if kind == mk.PREMIUM:
        lines = []
        for p in sorted(cat["premium"], key=lambda x: -x["months"]):
            best = " 🔥" if p["months"] == cat["best"] else ""
            lines.append(f"<b>⁨{p['months']}⁩ ماه</b>: ⁨{p['price']:,}⁩ تومان (ماهی ⁨{p['per_month']:,}⁩){best}")
        await say(texts.TG_PREMIUM.format(plans="\n".join(lines), **common),
                  keyboards.tg_premium_kb(cat["premium"], cat["best"]))
    else:
        await say(texts.TG_STARS.format(per_star=f"{round(cat['per_star']):,}", min_stars=f"{mk.STARS_MIN:,}",
                                        max_stars=f"{mk.STARS_MAX:,}", **common),
                  keyboards.tg_stars_kb(cat["packs"]))


@router.callback_query(F.data.startswith("tg:p:") | F.data.startswith("tg:s:"))
async def cb_pick(call: CallbackQuery, db: Database, user: dict, state: FSMContext) -> None:
    if not await _gate(call, db, user):
        return
    kind = mk.PREMIUM if call.data.startswith("tg:p:") else mk.STARS
    amount = mk.valid_amount(kind, call.data.split(":")[2])
    if amount is None:
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)
    await call.answer()
    await _confirm(call.message, db, user, state, kind, amount, edit=True)


@router.callback_query(F.data == "tg:sc")
async def cb_custom(call: CallbackQuery, db: Database, user: dict, state: FSMContext) -> None:
    if not await _gate(call, db, user):
        return
    data = await state.get_data()
    if not data.get("tg_rcp"):
        return await cb_hub(call, db, user, state)
    await state.set_state(TgShop.waiting_qty)
    await edit_or_send(call.message, texts.TG_ASK_QTY.format(username=data["tg_rcp"], min_stars=f"{mk.STARS_MIN:,}",
                                                             max_stars=f"{mk.STARS_MAX:,}"),
                       keyboards.tg_back_kb(f"tg:r:{mk.STARS}:{data['tg_rcp']}"))
    await call.answer()


@router.message(TgShop.waiting_qty, F.text)
async def msg_qty(message: Message, db: Database, user: dict, state: FSMContext) -> None:
    digits = re.sub(r"\D", "", (message.text or "").translate(_FA_DIGITS))
    if not digits:
        await state.set_state(None)
        raise SkipHandler
    amount = mk.valid_amount(mk.STARS, digits)
    if amount is None:
        return await message.answer(_t(mk.MESSAGES[mk.BAD_AMOUNT]))
    await state.set_state(None)
    await _confirm(message, db, user, state, mk.STARS, amount, edit=False)


async def _confirm(message: Message, db: Database, user: dict, state: FSMContext, kind: str, amount: int,
                   edit: bool) -> None:
    say = (lambda t, kb: edit_or_send(message, t, kb)) if edit else (lambda t, kb: message.answer(t, reply_markup=kb))
    data = await state.get_data()
    rcp, name = data.get("tg_rcp"), data.get("tg_rcp_name") or data.get("tg_rcp")
    if not rcp:
        return await say(texts.TG_ASK_RECIPIENT.format(product=_product(kind)), keyboards.tg_back_kb("tg"))
    try:
        q = await mk.quote(db, kind, amount)
    except mk.MarketAppError as exc:
        log.warning("قیمت MarketApp خوانده نشد: %s", exc)
        return await say(texts.TG_PROVIDER_DOWN, keyboards.tg_back_kb("tg"))
    await state.update_data(tg_kind=kind, tg_amount=amount)
    demo = await mk.mode(db) == mk.DEMO
    bal, price = int(user["balance"]), q["price"]
    common = {"title": _title(kind, amount), "name": esc(name), "username": rcp, "price": f"{price:,}",
              "demo": _demo(demo)}
    if bal >= price:
        text = texts.TG_CONFIRM.format(after=f"{bal - price:,}", **common)
    else:
        text = texts.TG_CONFIRM_LOW.format(balance=f"{bal:,}", short=f"{price - bal:,}", **common)
    if not demo and bal < price:
        return await say(text, keyboards.tg_back_kb("wal"))
    await say(text, keyboards.tg_confirm_kb(price, demo))


@router.callback_query(F.data == "tg:ok")
async def cb_ok(call: CallbackQuery, db: Database, user: dict, state: FSMContext) -> None:
    if not await _gate(call, db, user):
        return
    data = await state.get_data()
    kind, amount, rcp = data.get("tg_kind"), data.get("tg_amount"), data.get("tg_rcp")
    if kind not in mk.KINDS or not amount or not rcp:
        return await cb_hub(call, db, user, state)
    await call.answer()
    await edit_or_send(call.message, texts.TG_WORKING, None)
    r = await mk.buy(db, user, kind, rcp, amount)
    title = _title(kind, int(amount))
    if not r["ok"]:
        return await edit_or_send(call.message, texts.TG_FAILED.format(title=title, message=esc(_t(r["message"]))),
                                  keyboards.tg_back_kb(f"tg:k:{kind}"))
    await state.update_data(tg_amount=None)
    o = r["order"]
    await edit_or_send(
        call.message,
        texts.TG_DEMO_DONE.format(title=title, name=esc(o["recipient_name"] or o["recipient"]), username=o["recipient"],
                                  code=o["code"], price=f"{o['price']:,}"),
        keyboards.tg_done_kb(kind),
    )


@router.callback_query(F.data == "tg:mine")
async def cb_mine(call: CallbackQuery, db: Database, user: dict) -> None:
    if not features.is_on("shop_telegram"):
        return await call.answer(texts.SECTION_OFF, show_alert=True)
    orders = await db.user_tg_orders(user["id"], limit=10)
    if not orders:
        await edit_or_send(call.message, texts.TG_ORDERS_EMPTY, keyboards.tg_back_kb("tg"))
        return await call.answer()
    rows = []
    for o in orders:
        tag = "🧪 نمایشی" if o["mode"] == mk.DEMO else ("✅" if o["status"] == "completed" else o["status"])
        rows.append(f"• {mk.order_title(o)} → @{o['recipient']} · ⁨{o['price']:,}⁩ · <code>{o['code']}</code> {tag}")
    await edit_or_send(call.message, texts.TG_ORDERS.format(count=len(orders), rows="\n".join(rows)),
                       keyboards.tg_back_kb("tg"))
    await call.answer()


async def open_from_start(message: Message, db: Database, user: dict) -> bool:
    """لینک عمیق start=tg (دکمه مینی اپ). False = بخش آماده نیست."""
    if not features.is_on("shop_telegram") or not await mk.ready(db):
        return False
    sent = await message.answer("…")
    await show_hub(sent, db, user)
    return True


__all__ = ["router", "open_from_start", "show_hub"]
