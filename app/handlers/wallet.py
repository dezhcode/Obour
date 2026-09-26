"""کیف پول و شارژ کارت به کارت + جریان تایید ادمین (بخش ۵.۳ و ۱۵.۲ سند)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from app import i18n, keyboards, texts, ui
from app.config import config
from app.db import Database
from app.states import Wallet
from app.ui import edit_or_send
from app.utils import esc, fmt_dt, now_str
from app.i18n import t as _t
from app.services import crypto as crypto_svc
from app.services import payments
from app.services import stars as stars_svc

log = logging.getLogger("obour.wallet")
router = Router(name="wallet")
# پرداخت های تلگرام (Stars) روتر جدا دارند که قبل از همه ثبت می شود؛ تا هیچ
# هندلر state داری (مثلا وسط یک کار ادمین) پیام پرداخت موفق را نگیرد.
pay_router = Router(name="payments")


async def wallet_view(db: Database, user: dict) -> tuple[str, object]:
    """صفحه کیف پول، بسته به زبان کاربر.

    فارسی: مبلغ های کارت به کارت و زیرش کریپتو و Stars. بقیه زبان ها
    کارت به کارت ندارند (کارت ایرانی ندارند)؛ فقط انتخاب روش.
    """
    min_charge = int(await db.get_setting("min_charge", "50000"))
    methods = await payments.available(db, telegram_id=user["telegram_id"])
    fmt = {"balance": f"{user['balance']:,}", "min_charge": f"{min_charge:,}"}
    if payments.CARD in methods:
        return texts.WALLET.format(**fmt), keyboards.wallet_amounts(
            crypto=payments.CRYPTO in methods, stars=payments.STARS in methods)
    return texts.WALLET_INTL.format(**fmt), keyboards.wallet_methods(
        crypto=payments.CRYPTO in methods, stars=payments.STARS in methods)


@router.callback_query(F.data == "wal")
async def cb_wallet(call: CallbackQuery, db: Database, user: dict) -> None:
    body, kb = await wallet_view(db, user)
    await edit_or_send(call.message, body, kb)
    await call.answer()


async def _card_blocked(call_or_msg, db: Database) -> bool:  # noqa: ANN001
    """کارت به کارت برای کاربر غیر فارسی بسته است، حتی با callback دستی؛
    و وقتی ادمین خاموشش کرده، برای همه."""
    if await payments.card_ok(db):
        return False
    text = (_t("کارت به کارت فقط برای کاربرهای ایران است. از TON / USDT یا Stars استفاده کن.")
            if not payments.card_allowed() else _t("کارت به کارت فعلا غیرفعال است. از روش دیگری شارژ کن."))
    if isinstance(call_or_msg, CallbackQuery):
        await call_or_msg.answer(text, show_alert=True)
    else:
        await call_or_msg.answer(text)
    return True


async def _send_card(
    message: Message,
    db: Database,
    state: FSMContext,
    user: dict,
    amount: int,
    edit: bool = False,
    confirm_step: bool = False,
    exact_amount: int | None = None,
) -> None:
    """ساخت مبلغ یکتا، ثبت تراکنش در انتظار، و نمایش اطلاعات کارت.

    سه رقم آخر مبلغ تصادفی است تا ادمین از روی رسید بفهمد مال کیست.
    مبلغ رزرو شده config.charge_ttl_minutes دقیقه اعتبار دارد (منقضی ها
    پاک می شوند). با تایید مبلغ، مهلت از نو شروع می شود.
    """

    async def _out(text: str, markup=None) -> None:  # noqa: ANN001
        if edit:
            await edit_or_send(message, text, markup)
        else:
            await message.answer(text, reply_markup=markup)

    card_number = await db.get_setting("card_number")
    card_holder = await db.get_setting("card_holder")
    bank_name = await db.get_setting("bank_name")

    if not card_number:
        await state.clear()
        log.warning("شماره کارت در تنظیمات ثبت نشده - جریان شارژ متوقف شد")
        return await _out(texts.CARD_NOT_SET, keyboards.back_menu())

    exact = exact_amount or await db.reserve_amount(user["id"], amount, ttl_minutes=config.charge_ttl_minutes)
    if exact is None:
        await state.clear()
        return await _out(texts.AMOUNT_BUSY, keyboards.back_menu())

    # مرحله اول: تایید مبلغ اختصاصی. هنوز تراکنشی ثبت نمی شود.
    if confirm_step:
        await state.update_data(pending_amount=exact)
        return await _out(
            texts.AMOUNT_CONFIRM.format(amount=f"{exact:,}", rial=f"{exact * 10:,}",
                                        minutes=config.charge_ttl_minutes),
            keyboards.amount_confirm_kb(exact),
        )

    # هر تلاش شارژ کلید یکتای خودش را دارد (مبلغ + زمان). مبلغ یکتا
    # خودش تضمین می کند دو درخواست باز با یک عدد وجود نداشته باشد.
    txn_id = await db.insert_transaction(
        user_id=user["id"],
        type_="charge",
        amount=exact,
        status="pending",
        idem_key=f"charge:{user['id']}:{exact}:{now_str()}",
    )
    if txn_id is None:
        await db.release_amount(exact)
        await state.clear()
        return await _out(texts.AMOUNT_BUSY, keyboards.back_menu())

    await state.set_state(Wallet.waiting_receipt)
    await state.update_data(txn_id=txn_id, amount=exact)

    await _out(
        texts.CARD_INFO.format(
            amount=f"{exact:,}",
            rial=f"{exact * 10:,}",
            card_number=card_number,
            card_holder=card_holder or "-",
            bank_name=bank_name or "-",
            minutes=config.charge_ttl_minutes,
        ),
        keyboards.card_kb_v2(card_number, exact, txn_id),
    )


async def _start_charge(call: CallbackQuery, db: Database, state: FSMContext, amount: int) -> None:
    """مرحله اول: نمایش مبلغ اختصاصی برای تایید."""
    if await _card_blocked(call, db):
        return
    user = await db.get_user_by_tg(call.from_user.id)
    if not user:
        return await call.answer(_t("یه بار /start بزن و دوباره امتحان کن."), show_alert=True)
    min_charge = int(await db.get_setting("min_charge", "50000"))
    if amount < min_charge:
        return await call.answer(
            _t("حداقل شارژ {amount} تومانه.", amount=f"{min_charge:,}"), show_alert=True
        )
    await _send_card(call.message, db, state, user, amount, edit=True, confirm_step=True)


@router.callback_query(F.data.startswith("wal:go:"))
async def cb_amount_confirmed(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    """مرحله دوم: کاربر مبلغ را تایید کرد، حالا اطلاعات کارت را می بیند.

    مبلغ با آنچه در state رزرو شده تطبیق داده می شود تا کسی نتواند با
    دستکاری callback مبلغ دلخواه بسازد.
    """
    if await _card_blocked(call, db):
        return
    try:
        exact = int(call.data.split(":")[2])
    except (IndexError, ValueError):
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)

    data = await state.get_data()
    reserved = data.get("pending_amount")
    if reserved != exact:
        # مبلغ با رزرو نمی خواند (دستکاری یا جلسه منقضی)
        await state.clear()
        return await call.answer(
            _t("این درخواست معتبر نیست. دوباره از کیف پول شروع کن."), show_alert=True
        )

    # تایید نهایی که این مبلغ واقعا برای همین کاربر رزرو شده
    owner = await db.find_by_amount(exact)
    user = await db.get_user_by_tg(call.from_user.id)
    if not owner or owner["user_id"] != user["id"]:
        await state.clear()
        return await call.answer(
            _t("مهلت این مبلغ تموم شده. دوباره امتحان کن."), show_alert=True
        )

    # مهلت از لحظه دیدن شماره کارت شمرده می شود، نه از مرحله تایید
    await db.extend_amount(exact, user["id"], config.charge_ttl_minutes)
    await _send_card(
        call.message, db, state, user, exact, edit=True, exact_amount=exact
    )
    await call.answer()


@router.callback_query(F.data.startswith("wal:c:"))
async def cb_charge_preset(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    amount = int(call.data.split(":")[2])
    await _start_charge(call, db, state, amount)
    await call.answer()


@router.callback_query(F.data == "wal:custom")
async def cb_charge_custom(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    if await _card_blocked(call, db):
        return
    min_charge = int(await db.get_setting("min_charge", "50000"))
    await state.set_state(Wallet.waiting_amount)
    prompt = await edit_or_send(
        call.message,
        texts.WALLET.format(
            balance=f"{(await db.get_user_by_tg(call.from_user.id))['balance']:,}",
            min_charge=f"{min_charge:,}",
        ),
        keyboards.back_menu(),
    )
    # آیدی پیام سوال را نگه می داریم تا بعد از دریافت مبلغ، همان ویرایش شود
    await state.update_data(prompt_id=prompt.message_id if prompt else None)
    await call.answer()


@router.message(Wallet.waiting_amount, F.text)
async def txt_custom_amount(message: Message, db: Database, state: FSMContext) -> None:
    """دریافت مبلغ دستی.

    پیام کاربر پاک می شود و همان پیامی که مبلغ را پرسیده بود ویرایش
    می شود، تا چت تمیز بماند و مبلغ تایپ شده باقی نماند.
    """
    if await _card_blocked(message, db):
        return await state.clear()
    min_charge = int(await db.get_setting("min_charge", "50000"))
    raw = message.text.strip().replace(",", "").replace("،", "")
    data = await state.get_data()
    prompt_id = data.get("prompt_id")

    if not raw.isdigit() or int(raw) < min_charge:
        await ui.consume(message)  # ورودی نامعتبر هم پاک شود
        return await message.answer(
            texts.INVALID_AMOUNT.format(min_charge=f"{min_charge:,}")
        )

    await ui.consume(message)
    user = await db.get_user_by_tg(message.from_user.id)

    # پیام سوال قبلی را برمی داریم تا چت تمیز بماند، بعد مرحله بعد را می فرستیم
    if prompt_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_id)
        except Exception:  # noqa: BLE001
            pass
    await _send_card(message, db, state, user, int(raw), confirm_step=True)


@router.callback_query(F.data.startswith("wal:paid:"))
async def cb_paid(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    """کاربر گفت واریز کردم. زمان ثبت می شود تا مبنای یادآوری باشد."""
    txn_id = int(call.data.split(":")[2])
    user = await db.get_user_by_tg(call.from_user.id)
    if not await db.mark_paid(txn_id, user["id"]):
        return await call.answer(_t("این درخواست دیگه فعال نیست."), show_alert=True)

    txn = await db.get_transaction(txn_id)
    await state.set_state(Wallet.waiting_receipt)
    await state.update_data(txn_id=txn_id, amount=txn["amount"])
    await edit_or_send(
        call.message,
        texts.PAID_CLICKED.format(
            amount=f"{txn['amount']:,}", time=fmt_dt(now_str())
        ),
        keyboards.awaiting_receipt_kb(txn_id),
    )
    await call.answer(_t("ثبت شد ✅"))


@router.callback_query(F.data.startswith("wal:cancel:"))
async def cb_cancel_charge(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    """لغو شارژ: مبلغ آزاد می شود و یادآوری فرستاده نمی شود."""
    txn_id = int(call.data.split(":")[2])
    user = await db.get_user_by_tg(call.from_user.id)
    txn = await db.cancel_charge(txn_id, user["id"])
    await state.clear()
    if txn is None:
        return await call.answer(_t("این درخواست قبلا بسته شده."), show_alert=True)
    await edit_or_send(call.message, texts.CHARGE_CANCELLED, keyboards.back_menu())
    await call.answer(_t("لغو شد"))


@router.message(Wallet.waiting_receipt, F.photo)
async def photo_receipt(message: Message, db: Database, state: FSMContext) -> None:
    data = await state.get_data()
    txn_id = data.get("txn_id")
    if not txn_id:
        await state.clear()
        return await message.answer(_t("یه اشتباهی پیش اومد. دوباره از کیف پول شروع کن."))

    # تراکنش باید مال همین کاربر و هنوز باز باشد. بدون این بررسی، یک
    # آیدی جا مانده در state می توانست رسید را به تراکنش بسته شده بچسباند.
    txn = await db.get_transaction(txn_id)
    me = await db.get_user_by_tg(message.from_user.id)
    if not txn or not me or txn["user_id"] != me["id"] or txn["status"] != "pending":
        await state.clear()
        return await message.answer(_t("این درخواست شارژ دیگه باز نیست. از کیف پول شروع کن."))

    await db.set_receipt(txn_id, message.photo[-1].file_id)
    await state.clear()

    user = await db.get_user(txn["user_id"])
    # کد پیگیری همین جا داده می شود تا کاربر برای سوال بعدی دستش پر باشد
    code = (await db.get_transaction(txn_id) or {}).get("code")
    await message.answer(
        texts.RECEIVED + (texts.CODE_LINE.format(code=code) if code else "")
    )

    for admin_id in config.admin_ids:
        try:
            await message.bot.send_photo(
                admin_id,
                photo=message.photo[-1].file_id,
                caption=texts.ADMIN_CHARGE_REQ.format(
                    name=esc(user.get("first_name") or "-"),
                    username=esc(user.get("username") or "-"),
                    telegram_id=user["telegram_id"],
                    amount=f"{txn['amount']:,}",
                    balance=f"{user['balance']:,}",
                ),
                reply_markup=keyboards.admin_charge_kb(txn_id),
            )
        except Exception:  # noqa: BLE001
            log.warning("charge notify to admin %s failed", admin_id, exc_info=True)



# ═══════════════════ شارژ با کریپتو (TON / USDT) ═══════════════════
# منطق فاکتور، نرخ و تایید در app/services/crypto.py است؛ اینجا فقط
# گفتگوی ربات. تایید خودکار است: پایشگر تراکنش را روی زنجیره می بیند.


async def _crypto_home(message: Message, db: Database, user: dict, edit: bool = True) -> None:
    min_charge = int(await db.get_setting("min_charge", "50000"))
    body = texts.CRYPTO_WALLET.format(balance=f"{user['balance']:,}", min_charge=f"{min_charge:,}")
    if edit:
        await edit_or_send(message, body, keyboards.crypto_amounts())
    else:
        await message.answer(body, reply_markup=keyboards.crypto_amounts())


@router.callback_query(F.data == "cw")
async def cb_crypto(call: CallbackQuery, db: Database, state: FSMContext, user: dict) -> None:
    if not crypto_svc.allowed_for(user["telegram_id"]) or not await payments.is_on(db, payments.CRYPTO):
        return await call.answer(_t("پرداخت کریپتو فعلا فعال نیست."), show_alert=True)
    await state.clear()
    await _crypto_home(call.message, db, user)
    await call.answer()


@router.callback_query(F.data == "cw:custom")
async def cb_crypto_custom(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Wallet.crypto_amount)
    await call.answer(_t("مبلغ رو به تومان بفرست."), show_alert=True)


async def _crypto_pick(message: Message, db: Database, amount: int, edit: bool) -> None:
    """نمایش مبلغ هر ارز برای این مبلغ تومانی."""
    min_charge = int(await db.get_setting("min_charge", "50000"))
    if amount < min_charge:
        text = texts.INVALID_AMOUNT.format(min_charge=f"{min_charge:,}")
        return await (edit_or_send(message, text, keyboards.crypto_amounts()) if edit else message.answer(text))
    quotes = await crypto_svc.quote(db, amount)
    if not quotes:
        text = _t("نرخ ارزها هنوز تنظیم نشده. کمی بعد دوباره امتحان کن.")
        return await (edit_or_send(message, text, keyboards.crypto_amounts()) if edit else message.answer(text))
    icons = {"TON": "💎", "USDT": "💵"}
    lines = "\n".join(f"{icons[a]} <b>{q['amount']} {a}</b>" for a, q in quotes.items())
    body = texts.CRYPTO_PICK.format(amount=f"{amount:,}", lines=lines)
    kb = keyboards.crypto_assets(amount, quotes)
    if edit:
        await edit_or_send(message, body, kb)
    else:
        await message.answer(body, reply_markup=kb)


@router.callback_query(F.data.startswith("cw:a:"))
async def cb_crypto_amount(call: CallbackQuery, db: Database) -> None:
    try:
        amount = int(call.data.split(":")[2])
    except (IndexError, ValueError):
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)
    await _crypto_pick(call.message, db, amount, edit=True)
    await call.answer()


@router.message(Wallet.crypto_amount, F.text)
async def txt_crypto_amount(message: Message, db: Database, state: FSMContext) -> None:
    raw = message.text.strip().replace(",", "").replace("،", "")
    raw = raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    await ui.consume(message)
    if not raw.isdigit():
        min_charge = int(await db.get_setting("min_charge", "50000"))
        return await message.answer(texts.INVALID_AMOUNT.format(min_charge=f"{min_charge:,}"))
    await state.clear()
    await _crypto_pick(message, db, int(raw), edit=False)


def _invoice_text(inv: dict) -> str:
    body = texts.CRYPTO_INVOICE.format(
        code=inv["code"], toman=f"{inv['toman']:,}",
        crypto=crypto_svc.fmt_units(inv["units"], inv["asset"]), asset=inv["asset"],
        address=crypto_svc.pay_address(), minutes=config.crypto_invoice_minutes,
    )
    if inv["asset"] == crypto_svc.USDT:
        body += texts.CRYPTO_USDT_NOTE
    if crypto_svc.testnet():
        body += texts.CRYPTO_TESTNET_NOTE
    return body


def _invoice_kb(inv: dict):  # noqa: ANN202
    from app import webapp as _webapp

    wa = _webapp.url()
    return keyboards.crypto_invoice_kb(
        inv, crypto_svc.tonkeeper_link(inv), crypto_svc.pay_address(),
        crypto_svc.fmt_units(inv["units"], inv["asset"]),
        webapp_url=f"{wa}#crypto" if wa else "",
    )


@router.callback_query(F.data.startswith("cw:p:"))
async def cb_crypto_invoice(call: CallbackQuery, db: Database, user: dict) -> None:
    try:
        _, _, amount, asset = call.data.split(":")
        amount = int(amount)
    except ValueError:
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)
    r = await crypto_svc.create_invoice(db, user, amount, asset, source="bot")
    if not r["ok"]:
        msg = {
            crypto_svc.OFF: "پرداخت کریپتو فعلا فعال نیست.",
            crypto_svc.NO_RATE: "نرخ این ارز الان در دسترس نیست. ارز دیگه رو امتحان کن.",
            crypto_svc.TOO_LARGE: "مبلغ بیش از حد مجاز است",
        }.get(r["error"], "انجام نشد")
        if r["error"] == crypto_svc.TOO_SMALL:
            return await call.answer(_t("حداقل شارژ {amount} تومانه.", amount=f"{r['min']:,}"), show_alert=True)
        return await call.answer(_t(msg), show_alert=True)
    inv = r["invoice"]
    await edit_or_send(call.message, _invoice_text(inv), _invoice_kb(inv))
    crypto_svc.ensure_watcher(db, call.bot)
    await call.answer()


@router.callback_query(F.data.startswith("cw:chk:"))
async def cb_crypto_check(call: CallbackQuery, db: Database, user: dict) -> None:
    try:
        inv_id = int(call.data.split(":")[2])
    except (IndexError, ValueError):
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)
    inv = await db.get_crypto_invoice(inv_id)
    if not inv or inv["user_id"] != user["id"]:
        return await call.answer(_t("این درخواست دیگه فعال نیست."), show_alert=True)
    if inv["status"] == "pending":
        await crypto_svc.scan(db, call.bot)
        inv = await db.get_crypto_invoice(inv_id)
    if inv["status"] == "paid":
        fresh = await db.get_user(user["id"])
        await edit_or_send(call.message, texts.CRYPTO_PAID.format(
            amount=f"{inv['toman']:,}", crypto=crypto_svc.fmt_units(inv["paid_units"], inv["asset"]),
            asset=inv["asset"], balance=f"{fresh['balance']:,}", code=inv["code"],
        ), keyboards.back_menu())
        return await call.answer(_t("شارژ شد ✅"))
    if inv["status"] == "underpaid":
        return await call.answer(_t("مبلغ رسیده کمتر از فاکتور بود؛ پشتیبانی بررسی می کنه."), show_alert=True)
    if inv["status"] == "cancelled":
        return await call.answer(_t("این درخواست قبلا بسته شده."), show_alert=True)
    crypto_svc.ensure_watcher(db, call.bot)
    await call.answer(
        _t("هنوز پرداختی با این کامنت نرسیده. اگه پرداخت کردی، چند ثانیه دیگه دوباره بزن."),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("cw:x:"))
async def cb_crypto_cancel(call: CallbackQuery, db: Database, user: dict) -> None:
    try:
        inv_id = int(call.data.split(":")[2])
    except (IndexError, ValueError):
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)
    if not await db.cancel_crypto_invoice(inv_id, user["id"]):
        return await call.answer(_t("این درخواست قبلا بسته شده."), show_alert=True)
    await edit_or_send(call.message, texts.CHARGE_CANCELLED, keyboards.back_menu())
    await call.answer(_t("لغو شد"))


# ═══════════════════ شارژ با Telegram Stars ═══════════════════
# ستاره ها را خود تلگرام می گیرد؛ ما فاکتور می سازیم، pre_checkout را تایید
# می کنیم و با successful_payment کیف پول تومانی را شارژ می کنیم.


async def _stars_home(message: Message, db: Database, user: dict, edit: bool = True) -> None:
    rate = await stars_svc.rate(db)
    min_charge = int(await db.get_setting("min_charge", "50000"))
    body = texts.STARS_WALLET.format(balance=f"{user['balance']:,}", min_charge=f"{min_charge:,}", rate=f"{rate:,}")
    kb = keyboards.stars_amounts(rate)
    if edit:
        await edit_or_send(message, body, kb)
    else:
        await message.answer(body, reply_markup=kb)


@router.callback_query(F.data == "sw")
async def cb_stars(call: CallbackQuery, db: Database, state: FSMContext, user: dict) -> None:
    if not await stars_svc.enabled(db) or not await payments.is_on(db, payments.STARS):
        return await call.answer(_t("پرداخت با Stars فعلا فعال نیست."), show_alert=True)
    await state.clear()
    await _stars_home(call.message, db, user)
    await call.answer()


@router.callback_query(F.data == "sw:custom")
async def cb_stars_custom(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Wallet.stars_amount)
    await call.answer(_t("مبلغ رو به تومان بفرست."), show_alert=True)


async def _stars_invoice(message: Message, db: Database, user: dict, amount: int) -> str | None:
    """فاکتور ستاره را در چت می فرستد. خروجی: متن خطا، یا None."""
    r = await stars_svc.create(db, user, amount, source="bot")
    if not r["ok"]:
        if r["error"] == stars_svc.TOO_SMALL:
            return _t("حداقل شارژ {amount} تومانه.", amount=f"{r['min']:,}")
        if r["error"] == stars_svc.TOO_LARGE:
            return _t("سقف هر پرداخت با Stars {amount} تومانه.", amount=f"{r.get('max', 0):,}")
        return _t("پرداخت با Stars فعلا فعال نیست.")
    await stars_svc.send_invoice(message.bot, message.chat.id, r["invoice"])
    return None


@router.callback_query(F.data.startswith("sw:a:"))
async def cb_stars_amount(call: CallbackQuery, db: Database, user: dict) -> None:
    try:
        amount = int(call.data.split(":")[2])
    except (IndexError, ValueError):
        return await call.answer(_t("درخواست نامعتبر."), show_alert=True)
    err = await _stars_invoice(call.message, db, user, amount)
    await call.answer(err or "", show_alert=bool(err))


@router.message(Wallet.stars_amount, F.text)
async def txt_stars_amount(message: Message, db: Database, state: FSMContext, user: dict) -> None:
    raw = message.text.strip().replace(",", "").replace("،", "")
    raw = raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    await ui.consume(message)
    if not raw.isdigit():
        min_charge = int(await db.get_setting("min_charge", "50000"))
        return await message.answer(texts.INVALID_AMOUNT.format(min_charge=f"{min_charge:,}"))
    await state.clear()
    err = await _stars_invoice(message, db, user, int(raw))
    if err:
        await message.answer(err)


@pay_router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, db: Database) -> None:
    """تلگرام پیش از کم کردن ستاره می پرسد. باید ظرف ۱۰ ثانیه جواب داد."""
    user = await db.get_user_by_tg(query.from_user.id)
    with i18n.using(i18n.lang_of(user, query.from_user.language_code)):
        err = await stars_svc.check_pre_checkout(
            db, query.invoice_payload, query.from_user.id, query.total_amount, query.currency,
        )
    if err:
        await query.answer(ok=False, error_message=err)
    else:
        await query.answer(ok=True)


@pay_router.message(F.successful_payment)
async def on_successful_payment(message: Message, db: Database) -> None:
    pay = message.successful_payment
    inv = await stars_svc.settle(
        db, message.bot, payload=pay.invoice_payload, telegram_id=message.from_user.id,
        total=pay.total_amount, currency=pay.currency, charge_id=pay.telegram_payment_charge_id,
    )
    if inv is None:
        return
    await message.answer(texts.STARS_PAID.format(
        stars=inv["stars"], amount=f"{inv['toman']:,}", balance=f"{inv['balance']:,}",
    ), reply_markup=keyboards.back_menu())
