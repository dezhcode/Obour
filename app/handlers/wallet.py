"""کیف پول و شارژ کارت به کارت + جریان تایید ادمین (بخش ۵.۳ و ۱۵.۲ سند)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app import keyboards, texts, ui
from app.config import config
from app.db import Database
from app.states import Wallet
from app.ui import edit_or_send
from app.utils import esc, fmt_dt, now_str
from app.i18n import t as _t

log = logging.getLogger("obour.wallet")
router = Router(name="wallet")


@router.callback_query(F.data == "wal")
async def cb_wallet(call: CallbackQuery, db: Database, user: dict) -> None:
    min_charge = int(await db.get_setting("min_charge", "50000"))
    await edit_or_send(
        call.message,
        texts.WALLET.format(balance=f"{user['balance']:,}", min_charge=f"{min_charge:,}"),
        keyboards.wallet_amounts(),
    )
    await call.answer()


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

