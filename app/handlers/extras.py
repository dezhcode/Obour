"""تست رایگان، ساخت دلخواه، راهنما و هم سفرها (بخش ۵.۲، ۵.۵، ۵.۶، ۵.۷ سند)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

from app import features, effects, join, keyboards, referral, texts, ui
from app.config import config
from app.db import Database
from app.ui import edit_or_send
from app.keyboards import CUSTOM_DAY_STEPS, CUSTOM_GB_STEPS
from app.states import Buy
from app.panel import (
    Panel,
    PanelAmbiguous,
    PanelSafeError,
    gb_bytes,
    mb_bytes,
    sub_url_of,
)
from app.utils import after_days, custom_price, esc, fmt_dt, price_per_gb
from app.i18n import t as _t

log = logging.getLogger("obour.extras")
router = Router(name="extras")

_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


# ==================== تست رایگان ====================
async def _join_gate(call: CallbackQuery, target: str = "trial") -> bool:
    """True یعنی کاربر عضو نیست و صفحه عضویت نشانش داده شد.

    اگر ربات در کانال ادمین نباشد، join.missing خالی برمی گردد و
    کاربر بدون معطلی رد می شود؛ خطای تنظیمات نباید جلوی تست را بگیرد.
    """
    if not join.required():
        return False
    missing = await join.missing(call.bot, call.from_user.id)
    if not missing:
        return False
    await edit_or_send(
        call.message, texts.JOIN_REQUIRED, keyboards.join_kb(missing, target)
    )
    await call.answer()
    return True


@router.callback_query(F.data.startswith("join:ck:"))
async def cb_join_check(call: CallbackQuery, user: dict) -> None:
    """دکمه «عضو شدم»: دوباره بررسی می کند و در صورت موفقیت برمی گردد."""
    target = call.data.split(":")[2] if call.data.count(":") >= 2 else "trial"
    missing = await join.missing(call.bot, call.from_user.id)
    if missing:
        return await call.answer(texts.JOIN_STILL_MISSING, show_alert=True)
    await call.answer(texts.JOIN_OK)
    if target == "trial":
        if user["free_trial_used"]:
            return await edit_or_send(
                call.message, texts.TRIAL_USED, keyboards.back_menu()
            )
        return await edit_or_send(
            call.message,
            texts.TRIAL_OFFER.format(size=config.trial_mb, days=config.trial_days),
            keyboards.trial_kb(),
        )
    await edit_or_send(call.message, texts.TRIAL_USED, keyboards.back_menu())


@router.callback_query(F.data == "trial")
async def cb_trial(call: CallbackQuery, user: dict) -> None:
    if not features.is_on("shop_trial"):
        return await call.answer(texts.SECTION_OFF, show_alert=True)
    if not config.trial_enabled:
        return await call.answer(_t("تست رایگان فعلا غیرفعاله."), show_alert=True)
    if user["free_trial_used"]:
        await edit_or_send(call.message, texts.TRIAL_USED, keyboards.back_menu())
        return await call.answer()
    if await _join_gate(call):
        return
    await call.message.edit_text(
        texts.TRIAL_OFFER.format(size=config.trial_mb, days=config.trial_days),
        reply_markup=keyboards.trial_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "trial:ok")
async def cb_trial_ok(
    call: CallbackQuery, db: Database, panel: Panel | None, user: dict
) -> None:
    if not config.trial_enabled:
        return await call.answer(_t("تست رایگان فعلا غیرفعاله."), show_alert=True)
    if panel is None:
        return await call.answer(texts.PANEL_BUSY_ALERT, show_alert=True)
    if await _join_gate(call):
        return

    # قفل عملیات: جلوی دو کلیک همزمان را می گیرد
    lock = f"pay:{user['id']}"
    if not await db.acquire_lock(lock):
        return await call.answer(_t("یه لحظه صبر کن، در حال انجامه."), show_alert=True)
    try:
        await _make_trial(call, db, panel, user)
    finally:
        await db.release_lock(lock)


async def _make_trial(
    call: CallbackQuery, db: Database, panel: Panel, user: dict
) -> None:
    # قفل اتمیک: هر کاربر فقط یک بار
    if not await db.mark_trial_used(user["id"]):
        await edit_or_send(call.message, texts.TRIAL_USED, keyboards.back_menu())
        return await call.answer()

    await ui.working(call.message, texts.building(name=esc(user.get("first_name") or "")))

    try:
        panel_username = await db.free_panel_username(user["telegram_id"], user["id"])
    except Exception:  # noqa: BLE001
        await db.execute("UPDATE users SET free_trial_used = 0 WHERE id = ?", (user["id"],))
        log.exception("trial username failed for %s", user["telegram_id"])
        return await call.message.edit_text(
            texts.PANEL_ERROR, reply_markup=keyboards.back_menu()
        )
    try:
        resp = await panel.create_service(
            username=panel_username,
            data_bytes=mb_bytes(config.trial_mb),
            days=config.trial_days,
            note=f"obour trial tg:{user['telegram_id']}",
        )
    except PanelSafeError:
        # ساخته نشد -> فلگ تست پس داده شود تا کاربر ضرر نکند
        await db.execute("UPDATE users SET free_trial_used = 0 WHERE id = ?", (user["id"],))
        log.error("trial create rejected for %s", user["telegram_id"], exc_info=True)
        return await call.message.edit_text(
            texts.PANEL_ERROR, reply_markup=keyboards.back_menu()
        )
    except PanelAmbiguous:
        log.error("trial create AMBIGUOUS for %s", panel_username, exc_info=True)
        try:
            created = await panel.get_user(panel_username)
        except Exception:  # noqa: BLE001
            created = None
        if created is None:
            await db.execute(
                "UPDATE users SET free_trial_used = 0 WHERE id = ?", (user["id"],)
            )
            return await call.message.edit_text(
                texts.PANEL_ERROR, reply_markup=keyboards.back_menu()
            )
        resp = created

    sub_url = sub_url_of(resp, panel.base_url)
    service_id = await db.insert_service(
        user_id=user["id"],
        plan_id=None,
        panel_username=panel_username,
        sub_url=sub_url,
        data_gb=0,
        duration_days=config.trial_days,
        expire_at=after_days(config.trial_days).isoformat(timespec="seconds"),
    )
    await ui.deliver(
        call.message,
        caption=texts.TRIAL_SUCCESS.format(
            size=config.trial_mb, days=config.trial_days, sub_url=sub_url
        ),
        sub_url=sub_url,
        reply_markup=keyboards.service_detail_kb(service_id, sub_url),
        filename="obour_trial.png",
        effect=effects.TRIAL,
    )

    # هدایت به خرید بعد از تست (بخش ۱۳ سند)
    try:
        await call.message.answer(
            texts.TRIAL_AFTER.format(name=user.get("first_name") or _t("دوست من")),
            reply_markup=keyboards.trial_after_kb(),
        )
    except Exception:  # noqa: BLE001
        log.warning("trial after message failed", exc_info=True)
    await call.answer()


# ==================== ساخت دلخواه ====================
def _steps(gi: int, di: int) -> tuple[int, int]:
    gi = max(0, min(gi, len(CUSTOM_GB_STEPS) - 1))
    di = max(0, min(di, len(CUSTOM_DAY_STEPS) - 1))
    return CUSTOM_GB_STEPS[gi], CUSTOM_DAY_STEPS[di]


async def _show_builder(call: CallbackQuery, user: dict, gi: int, di: int) -> None:
    gb, days = _steps(gi, di)
    price = custom_price(gb, days, config.custom_rate_per_gb)
    await call.message.edit_text(
        texts.CUSTOM_BUILDER.format(
            data=gb,
            days=days,
            price=f"{price:,}",
            per_gb=f"{price_per_gb(price, gb):,}",
            balance=f"{user['balance']:,}",
        ),
        reply_markup=keyboards.custom_builder_kb(gb, days),
    )


@router.callback_query(F.data == "cst")
async def cb_custom(call: CallbackQuery, user: dict) -> None:
    if not features.is_on("shop_custom"):
        return await call.answer(texts.SECTION_OFF, show_alert=True)
    await _show_builder(call, user, 1, 4)  # پیش فرض ۱۰ گیگ / ۳۰ روز
    await call.answer()


@router.callback_query(F.data.in_({"cst:noop", "noop"}))
async def cb_noop(call: CallbackQuery) -> None:
    """دکمه نمایشی. اگر نسخه aiogram دکمه غیرفعال نداشته باشد اینجا می افتد."""
    await call.answer()


@router.callback_query(F.data.startswith(("cst:gb:", "cst:dy:")))
async def cb_custom_adjust(call: CallbackQuery, user: dict) -> None:
    _, _, gi, di = call.data.split(":")
    gb, days = _steps(int(gi), int(di))
    price = custom_price(gb, days, config.custom_rate_per_gb)
    await _show_builder(call, user, int(gi), int(di))
    # بازخورد فوری روی خود دکمه، بدون معطل ماندن برای رندر پیام
    await ui.toast(call, f"{gb} {_t('گیگ')} · {days} {_t('روز')} — {price:,} {_t('تومان')}")


@router.callback_query(F.data.startswith("cst:ok:"))
async def cb_custom_confirm(call: CallbackQuery, user: dict) -> None:
    _, _, gi, di = call.data.split(":")
    gb, days = _steps(int(gi), int(di))
    price = custom_price(gb, days, config.custom_rate_per_gb)
    if user["balance"] < price:
        await call.message.edit_text(
            texts.INSUFFICIENT, reply_markup=keyboards.insufficient_kb()
        )
        return await call.answer()
    await call.message.edit_text(
        texts.CUSTOM_CONFIRM.format(
            data=gb,
            days=days,
            price=f"{price:,}",
            balance=f"{user['balance']:,}",
            balance_after=f"{user['balance'] - price:,}",
        ),
        reply_markup=keyboards.custom_confirm_kb(int(gi), int(di)),
    )
    await call.answer()


@router.callback_query(F.data.startswith("cst:go:"))
async def cb_custom_buy(call: CallbackQuery, state: FSMContext) -> None:
    """مرحله اسم سرویس برای ساخت دلخواه، قبل از پرداخت."""
    _, _, gi, di = call.data.split(":")
    await state.set_state(Buy.waiting_custom_name)
    await state.update_data(custom_gi=int(gi), custom_di=int(di))
    await edit_or_send(
        call.message,
        texts.SERVICE_NAME_BEFORE_BUY,
        keyboards.service_name_kb(f"cst:gb:{gi}:{di}", skip_data="cnm:skip"),
    )
    await call.answer()


@router.callback_query(Buy.waiting_custom_name, F.data == "cnm:skip")
async def cb_custom_skip_name(
    call: CallbackQuery, db: Database, panel: Panel | None, state: FSMContext, user: dict
) -> None:
    await _start_custom(call.message, db, panel, state, user, "", f"cst:{call.id}", call)


@router.message(Buy.waiting_custom_name, F.text)
async def msg_custom_service_name(
    message: Message, db: Database, panel: Panel | None, state: FSMContext, user: dict
) -> None:
    """اسم سرویس برای خرید دلخواه."""
    raw = (message.text or "").strip()
    if len(raw) > 30:
        return await message.answer(texts.SERVICE_NAME_TOO_LONG)
    idem = f"cst:m{message.chat.id}:{message.message_id}"
    await _start_custom(message, db, panel, state, user, raw, idem)


async def _start_custom(
    message: Message,
    db: Database,
    panel: Panel | None,
    state: FSMContext,
    user: dict,
    label: str,
    idem: str,
    call: CallbackQuery | None = None,
) -> None:
    data = await state.get_data()
    await state.set_state(None)
    if panel is None:
        return await message.answer(texts.PANEL_BUSY_ALERT)
    if data.get("custom_gi") is None:
        return await message.answer(_t("یه اشتباهی پیش اومد. دوباره از فروشگاه شروع کن."))
    gb, days = _steps(int(data["custom_gi"]), int(data["custom_di"]))
    price = custom_price(gb, days, config.custom_rate_per_gb)

    lock = f"pay:{user['id']}"
    if not await db.acquire_lock(lock):
        msg = _t("یه پرداخت همین حالا در جریانه. چند لحظه صبر کن.")
        if call:
            return await call.answer(msg, show_alert=True)
        return await message.answer(msg)
    try:
        await _make_custom(message, db, panel, user, gb, days, price, label, idem, call)
    finally:
        await db.release_lock(lock)


async def _make_custom(
    message: Message,
    db: Database,
    panel: Panel,
    user: dict,
    gb: int,
    days: int,
    price: int,
    label: str,
    idem: str,
    call: CallbackQuery | None = None,
) -> None:
    txn_id = await db.insert_transaction(
        user["id"], "purchase", -price, idem_key=idem
    )
    if txn_id is None:
        if call:
            return await call.answer(_t("این خرید در حال پردازشه."), show_alert=True)
        return await message.answer(_t("این خرید در حال پردازشه."))

    working = await ui.working(
        message, texts.building(name=esc(user.get("first_name") or ""))
    )

    try:
        panel_username = await db.free_panel_username(
            user["telegram_id"], user["id"], label, taken=panel.username_taken
        )
    except Exception:  # noqa: BLE001
        await db.fail_transaction(txn_id, "نام سرویس ساخته نشد")
        log.exception("custom username failed for %s", user["telegram_id"])
        return await _fail(working, texts.PANEL_ERROR)
    try:
        from app.services.purchase import _create_with_retry

        resp, panel_username = await _create_with_retry(
            db,
            panel,
            user,
            label,
            panel_username,
            data_bytes=gb_bytes(gb),
            days=days,
            note=f"obour custom tg:{user['telegram_id']}",
        )
    except PanelSafeError as exc:
        await db.fail_transaction(txn_id, f"panel rejected: {exc}")
        log.error("custom create rejected for %s", user["telegram_id"], exc_info=True)
        return await _fail(working, texts.PANEL_ERROR)
    except PanelAmbiguous as exc:
        log.error("custom create AMBIGUOUS for %s", panel_username, exc_info=True)
        try:
            created = await panel.get_user(panel_username)
        except Exception:  # noqa: BLE001
            created = None
        if created is None:
            await db.fail_transaction(txn_id, f"panel ambiguous, not created: {exc}")
            return await _fail(working, texts.PANEL_ERROR)
        resp = created

    # کسر اتمیک
    if not await db.atomic_debit(user["id"], price):
        await panel.remove(panel_username)
        await db.fail_transaction(txn_id, "موجودی کافی نبود")
        return await _fail(working, texts.INSUFFICIENT, keyboards.insufficient_kb())
    if not await db.approve_purchase(txn_id):
        log.error("تراکنش %s در حالت pending نبود", txn_id)

    sub_url = sub_url_of(resp, panel.base_url)
    service_id = await db.insert_service(
        user_id=user["id"],
        plan_id=None,
        panel_username=panel_username,
        sub_url=sub_url,
        data_gb=gb,
        duration_days=days,
        expire_at=after_days(days).isoformat(timespec="seconds"),
    )
    if label:
        await db.set_service_label(service_id, user["id"], label)

    fresh = await db.get_user(user["id"])
    await ui.deliver(
        working,
        caption=texts.buy_success(
            sub_url=sub_url,
            balance=f"{fresh['balance']:,}",
            name=esc(label) or f"{_t('سرویس')} {service_id}",
        ),
        sub_url=sub_url,
        reply_markup=keyboards.service_detail_kb(service_id, sub_url),
        effect=effects.PURCHASE,
    )
    # پاداش معرف (اگر این کاربر با لینک کسی آمده باشد)
    await referral.reward_purchase(
        working.bot, db, user, price, txn_id, "یک سرویس دلخواه ساخت"
    )
    if call:
        await call.answer()


async def _fail(message: Message, body: str, markup=None) -> None:  # noqa: ANN001
    """نمایش خطا روی همان پیام «در حال آماده سازی»."""
    try:
        await message.edit_text(body, reply_markup=markup or keyboards.back_menu())
    except Exception:  # noqa: BLE001
        await message.answer(body, reply_markup=markup or keyboards.back_menu())


# ==================== راهنما و سوالات پرتکرار ====================
@router.callback_query(F.data == "guide")
async def cb_guide(call: CallbackQuery) -> None:
    await edit_or_send(call.message, texts.GUIDE_INTRO, keyboards.guide_kb())
    await call.answer()


@router.callback_query(F.data.startswith("gd:"))
async def cb_guide_device(call: CallbackQuery) -> None:
    key = call.data.split(":")[1]
    body = texts.GUIDE.get(key)
    if not body:
        return await call.answer()
    await edit_or_send(call.message, body, keyboards.guide_back_kb())
    await call.answer()


@router.callback_query(F.data == "faq")
async def cb_faq(call: CallbackQuery) -> None:
    await edit_or_send(call.message, texts.FAQ_INTRO, keyboards.faq_kb())
    await call.answer()


@router.callback_query(F.data.startswith("faq:"))
async def cb_faq_item(call: CallbackQuery) -> None:
    key = call.data.split(":")[1]
    body = texts.FAQ.get(key)
    if not body:
        return await call.answer()
    await edit_or_send(call.message, body, keyboards.faq_back_kb())
    await call.answer()


# ==================== هم سفرها ====================
def _referral_rule() -> str:
    """متن قانون پاداش، بر اساس تنظیمات env."""
    if not config.ref_enabled or config.ref_percent <= 0:
        if config.ref_enabled and config.ref_first_bonus > 0:
            return texts.REFERRAL_RULE_BONUS.format(
                percent=0, bonus=f"{config.ref_first_bonus:,}"
            )
        return texts.REFERRAL_RULE_OFF
    if config.ref_first_bonus > 0:
        return texts.REFERRAL_RULE_BONUS.format(
            percent=config.ref_percent, bonus=f"{config.ref_first_bonus:,}"
        )
    return texts.REFERRAL_RULE.format(percent=config.ref_percent)


@router.callback_query(F.data == "ref")
async def cb_referral(call: CallbackQuery, db: Database, user: dict) -> None:
    if not features.is_on("shop_referral"):
        return await call.answer(texts.SECTION_OFF, show_alert=True)
    me = await call.bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user['telegram_id']}"
    st = await db.referral_stats(user["telegram_id"], user["id"])
    await edit_or_send(
        call.message,
        texts.REFERRAL.format(
            link=link,
            joined=st["joined"],
            buyers=st["buyers"],
            month=f"{st['month']:,}",
            total=f"{st['total']:,}",
            rule=_referral_rule(),
        ),
        keyboards.referral_kb(link, has_log=bool(st["rewards"])),
        link_preview_options=_NO_PREVIEW,
    )
    await call.answer()


@router.callback_query(F.data == "ref:log")
async def cb_referral_log(call: CallbackQuery, db: Database, user: dict) -> None:
    """گزارش آخرین پاداش ها."""
    rows = await db.referral_log(user["id"], limit=10)
    if not rows:
        await edit_or_send(
            call.message, texts.REFERRAL_LOG_EMPTY, keyboards.referral_log_kb()
        )
        return await call.answer()

    lines = [
        texts.REFERRAL_LOG_ROW.format(
            name=esc((r["first_name"] or _t("هم سفر")).strip())[:20],
            reward=f"{r['reward']:,}",
            when=fmt_dt(r["created_at"]),
        )
        for r in rows
    ]
    total = sum(r["reward"] for r in rows)
    await edit_or_send(
        call.message,
        texts.REFERRAL_LOG.format(
            count=len(rows), rows="\n".join(lines), total=f"{total:,}"
        ),
        keyboards.referral_log_kb(),
    )
    await call.answer()


# ==================== اتصال سریع ====================
@router.callback_query(F.data.regexp(r"^cn:\d+$"))
async def cb_connect(call: CallbackQuery, db: Database, user: dict) -> None:
    """انتخاب دستگاه."""
    service_id = int(call.data.split(":")[1])
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"]:
        return await call.answer(_t("این سرویس پیدا نشد."), show_alert=True)
    name = (service.get("label") or "").strip() or f"{_t('سرویس')} {service_id}"
    await edit_or_send(
        call.message,
        texts.CONNECT_PICK.format(name=esc(name)),
        keyboards.connect_platform_kb(service_id),
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^cn:\d+:[a-z]+$"))
async def cb_connect_platform(call: CallbackQuery, db: Database, user: dict) -> None:
    """دکمه های یک کلیکی برنامه ها."""
    from app.apps import PLATFORMS

    _, sid, platform = call.data.split(":")
    service = await db.get_service(int(sid))
    if not service or service["user_id"] != user["id"]:
        return await call.answer(_t("این سرویس پیدا نشد."), show_alert=True)
    emoji, title, _apps = PLATFORMS.get(platform, ("📱", "دستگاه", ()))
    title = _t(title)
    name = (service.get("label") or "").strip() or f"Obour-{sid}"

    markup, one_click = keyboards.connect_apps_kb(
        int(sid), platform, service["sub_url"], name
    )
    body = (texts.CONNECT_APPS if one_click else texts.CONNECT_MANUAL).format(
        emoji=emoji, platform=title
    )
    await edit_or_send(call.message, body, markup, link_preview_options=_NO_PREVIEW)
    await call.answer()
