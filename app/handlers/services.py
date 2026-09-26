"""سرویس های من: نمایش مصرف زنده، QR و تمدید (بخش ۵.۴ سند).

نکات تمدید (مهم):
- روزهای باقی مانده سوخت نمی شود (قابل تنظیم با RENEW_KEEP_REMAINING).
  عددی که به پنل داده می شود و عددی که در دیتابیس می نشیند دقیقا یکی
  است تا تاریخ انقضای پنل و ربات از هم جدا نشوند.
- تشخیص «آیا تمدید اعمال شد؟» با تاریخ انقضا سنجیده می شود نه با حجم.
  در نسخه قبلی با data_limit سنجیده می شد و چون تمدید با همان پلن همان
  حجم را می گذارد، همیشه «اعمال نشده» تشخیص داده می شد: یعنی سرویس
  تمدید شده بود ولی پول کسر نمی شد.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, LinkPreviewOptions, Message

from app import referral, effects, keyboards, texts, ui
from app.config import config
from app.db import Database
from app.panel import Panel, PanelError, sub_url_of
from app.states import Service
from app.ui import edit_or_send
from app.utils import (
    TZ,
    esc,
    fmt_data,
    is_expired,
    qr_png,
    renew_days,
    service_status,
    time_left_text,
    usage_bar,
    usage_percent,
)
from app.i18n import t as _t

log = logging.getLogger("obour.services")
router = Router(name="services")


@router.callback_query(F.data == "svc")
async def cb_services(call: CallbackQuery, db: Database, user: dict) -> None:
    # جواب زودهنگام کالبک: این صفحه فقط از دیتابیس می خواند و سریع است،
    # ولی اگر ورکر پشت یک کار دیگر مانده باشد، تیک چرخان روی دکمه
    # برگشت بی خود می ماند.
    try:
        await call.answer()
    except Exception:  # noqa: BLE001
        pass
    services = await db.user_services(user["id"])
    if not services:
        return await edit_or_send(
            call.message, texts.SERVICES_EMPTY, keyboards.back_menu()
        )
    await edit_or_send(
        call.message,
        texts.SERVICES_LIST.format(count=len(services)),
        keyboards.services_kb(services),
    )


def _status_of(service: dict, used: int, data_limit: int | None) -> str:
    return texts.SVC_STATUS[
        service_status(
            service["expire_at"], used, data_limit, service.get("duration_days")
        )
    ]


# کش کوتاه مصرف: (used, data_limit, زمان خواندن) به ازای هر سرویس.
# هدف این نیست که عدد همیشه تازه باشد؛ هدف این است که باز کردن صفحه
# سرویس فوری باشد. پنل زیر کلادفلر گاهی ۵۲۲ می دهد و تا ۸ ثانیه طول
# می کشد - بدون کش، کاربر هر بار همان مدت منتظر می ماند.
_USAGE_TTL = 90  # ثانیه
_usage_cache: dict[int, tuple[int, int | None, float]] = {}


def invalidate_usage(service_id: int) -> None:
    """باطل کردن کش مصرف یک سرویس.

    بعد از تمدید یا ابطال لینک، عدد قبلی دیگر معتبر نیست و کاربر باید
    بلافاصله وضعیت تازه را ببیند، نه عدد تا ۹۰ ثانیه قدیمی.
    """
    _usage_cache.pop(service_id, None)


def _cached_usage(service_id: int) -> tuple[int, int | None] | None:
    hit = _usage_cache.get(service_id)
    if not hit:
        return None
    used, limit, ts = hit
    if (time.monotonic() - ts) > _USAGE_TTL:
        return None
    return used, limit


def _detail_body(service: dict, title: str, used: int, data_limit: int | None) -> str:
    return texts.SERVICE_DETAIL.format(
        name=esc((service["label"] or "").strip() or f"{_t('سرویس')} {service['id']}"),
        title=esc(title),
        status=_status_of(service, used, data_limit),
        bar=usage_bar(used, data_limit),
        percent=usage_percent(used, data_limit),
        used=fmt_data(used),
        total=fmt_data(data_limit),
        time_left=time_left_text(service["expire_at"]),
    )


@router.callback_query(F.data.startswith("svc:v:"))
async def cb_service_detail(
    call: CallbackQuery, db: Database, panel: Panel | None, user: dict
) -> None:
    """صفحه یک سرویس.

    دو مرحله ای است تا باز شدن فوری باشد:
    ۱. صفحه با آخرین عدد شناخته شده (کش یا آخرین عکس روزانه) نمایش
       داده می شود - بدون هیچ انتظاری.
    ۲. بعد مصرف تازه از پنل خوانده می شود و اگر فرق داشت، همان پیام
       ویرایش می شود.

    قبلا مرحله ۲ اول انجام می شد و کاربر تا پاسخ پنل (گاهی ۸ تا ۲۰
    ثانیه، یا تایم اوت ۵۲۲) پشت صفحه منتظر می ماند.
    """
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"]:
        await edit_or_send(call.message, _t("این سرویس پیدا نشد."), keyboards.back_menu())
        return await call.answer()

    # کالبک را همین اول جواب می دهیم: اعتبارش حدود ۱۵ ثانیه است و اگر
    # آخر کار جواب بدهیم «query is too old» می گیریم.
    try:
        await call.answer()
    except Exception:  # noqa: BLE001
        pass

    title = _t("سرویس")
    plan = await db.get_plan(service["plan_id"]) if service["plan_id"] else None
    if plan:
        title = plan["title"]

    markup = keyboards.service_detail_kb(service_id, service["sub_url"], deletable=True)
    preview = LinkPreviewOptions(is_disabled=True)

    # ---------- مرحله ۱: نمایش فوری ----------
    cached = _cached_usage(service_id)
    if cached is None:
        # کش نداریم؛ آخرین عکس روزانه مصرف (اگر کرون گرفته باشد)
        history = await db.usage_history(service_id, days=1)
        if history:
            cached = (
                int(history[-1]["used_bytes"] or 0),
                history[-1]["data_limit"],
            )
    shown_used, shown_limit = cached if cached else (0, None)
    msg = await edit_or_send(
        call.message,
        _detail_body(service, title, shown_used, shown_limit),
        markup,
        link_preview_options=preview,
    )

    # اگر کش تازه بود، همین کافی است - سراغ پنل نمی رویم
    if _cached_usage(service_id) is not None:
        return
    if panel is None:
        return

    # ---------- مرحله ۲: در پس زمینه ----------
    # مهم: این کار نباید داخل همین هندلر await شود. زیر Passenger، هر
    # آپدیت تلگرام یک درخواست HTTP است و ورکر تا پایان هندلر بلاک
    # می ماند؛ یعنی اگر اینجا ۸ ثانیه منتظر پنل بمانیم، کلیک بعدی کاربر
    # (مثلا دکمه برگشت) هم پشت همین صف می ماند و دیر باز می شود.
    # با تسک پس زمینه، هندلر فورا تمام می شود و به روزرسانی عدد جدا
    # ادامه پیدا می کند.
    asyncio.create_task(
        _refresh_usage(
            msg, service, title, markup, preview, panel, (shown_used, shown_limit),
            had_data=cached is not None,
        )
    )


async def _refresh_usage(  # noqa: PLR0913
    msg,  # noqa: ANN001
    service: dict,
    title: str,
    markup,  # noqa: ANN001
    preview,  # noqa: ANN001
    panel: Panel,
    shown: tuple[int, int | None],
    had_data: bool,
) -> None:
    """خواندن مصرف تازه و به روزرسانی پیام - جدا از مسیر اصلی.

    اگر پنل جواب ندهد و عدد قبلی هم نداشته باشیم، به کاربر می گوییم
    سرور در دسترس نیست؛ وگرنه سکوت می کنیم و همان عدد قبلی می ماند.
    """
    service_id = int(service["id"])
    shown_used, shown_limit = shown
    try:
        # سقف زمانی مستقل: حتی اگر مهلت پنل بالا تنظیم شده باشد، این
        # تسک نباید بی نهایت زنده بماند.
        pu = await asyncio.wait_for(
            panel.get_user(service["panel_username"]),
            timeout=min(config.panel_timeout, 10),
        )
    except (PanelError, asyncio.TimeoutError) as exc:
        log.warning("خواندن مصرف %s نشد: %s", service["panel_username"], exc)
        if not had_data:
            # هیچ عددی نداشتیم که نشان بدهیم - کاربر باید بداند چرا
            try:
                await edit_or_send(
                    msg,
                    _detail_body(service, title, shown_used, shown_limit)
                    + texts.PANEL_BUSY_NOTE,
                    markup,
                    link_preview_options=preview,
                )
            except Exception:  # noqa: BLE001
                log.debug("درج هشدار در دسترس نبودن سرور نشد", exc_info=True)
        return
    except Exception:  # noqa: BLE001
        log.exception("خطای غیرمنتظره در خواندن مصرف %s", service_id)
        return

    if pu is None:
        return
    used = pu.used_traffic or 0
    data_limit = pu.data_limit
    _usage_cache[service_id] = (used, data_limit, time.monotonic())

    if (used, data_limit) == (shown_used, shown_limit):
        return  # چیزی عوض نشده، ویرایش بی مورد نمی کنیم
    try:
        await edit_or_send(
            msg,
            _detail_body(service, title, used, data_limit),
            markup,
            link_preview_options=preview,
        )
    except Exception:  # noqa: BLE001
        log.debug("به روزرسانی مصرف روی پیام انجام نشد", exc_info=True)


@router.callback_query(F.data.startswith("svc:use:"))
async def cb_service_usage(
    call: CallbackQuery, db: Database, panel: Panel | None, user: dict
) -> None:
    """نمودار مصرف روزهای اخیر + پیش بینی اتمام حجم."""
    from app import usage as usage_mod

    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"]:
        return await call.answer(_t("این سرویس پیدا نشد."), show_alert=True)

    name = esc((service["label"] or "").strip() or f"{_t('سرویس')} {service_id}")

    # عکس امروز را همین حالا می گیریم تا کاربر منتظر کرون فردا نماند
    if panel is not None:
        try:
            pu = await panel.get_user(service["panel_username"])
            if pu is not None:
                await db.record_usage(
                    service_id,
                    datetime.now(TZ).strftime("%Y-%m-%d"),
                    pu.used_traffic or 0,
                    pu.data_limit,
                )
        except PanelError:
            pass

    rows = await db.usage_history(service_id, days=8)
    report = usage_mod.forecast(rows, service)
    if not report["has_data"]:
        await edit_or_send(
            call.message,
            texts.USAGE_NO_DATA.format(name=name),
            keyboards.usage_kb(service_id),
        )
        return await call.answer()

    verdict = texts.USAGE_VERDICT[report["verdict"]].format(
        days=report["days_to_empty"] or 0, left=report["days_to_expire"]
    )
    await edit_or_send(
        call.message,
        texts.USAGE_REPORT.format(
            name=name,
            chart=report["chart"],
            average=fmt_data(report["average"]),
            used=fmt_data(report["used"]),
            total=fmt_data(report["limit"] or None),
            verdict=verdict,
        ),
        keyboards.usage_kb(service_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("svc:qr:"))
async def cb_service_qr(call: CallbackQuery, db: Database, user: dict) -> None:
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"]:
        return await call.answer(_t("سرویس پیدا نشد."), show_alert=True)
    if not service["sub_url"]:
        return await call.answer(_t("لینک این سرویس ثبت نشده."), show_alert=True)
    photo = BufferedInputFile(qr_png(service["sub_url"]), filename="obour_qr.png")
    await call.message.answer_photo(
        photo, caption=_t("📷 QR لینک سرویس"), reply_markup=keyboards.qr_kb()
    )
    await call.answer()


# ==================== تمدید ====================
def _expire_num(panel_user) -> float:  # noqa: ANN001
    """تاریخ انقضای کاربر پنل به عدد.

    نوع این فیلد بین نسخه های پنل فرق می کند (timestamp، datetime یا
    رشته)، پس همه حالت ها به عدد تبدیل می شوند تا قابل مقایسه باشند.
    """
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


@router.callback_query(F.data.startswith("svc:rnw:"))
async def cb_renew_confirm(call: CallbackQuery, db: Database, user: dict) -> None:
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"] or not service["plan_id"]:
        return await call.answer(_t("این سرویس قابل تمدید نیست."), show_alert=True)
    plan = await db.get_plan(service["plan_id"])
    if not plan:
        return await call.answer(_t("پلن این سرویس دیگه موجود نیست."), show_alert=True)
    body = texts.RENEW_CONFIRM.format(
        number=service["id"],
        title=esc(plan["title"]),
        price=f"{plan['price']:,}",
        balance=f"{user['balance']:,}",
    )
    if config.renew_keep_remaining:
        total = renew_days(service["expire_at"], plan["duration_days"], True)
        extra = total - plan["duration_days"]
        if extra > 0:
            body += "\n\n<i>" + _t("{extra} روز باقی مانده فعلیت هم اضافه می شه.", extra=extra) + "</i>"
    await edit_or_send(call.message, body, keyboards.renew_confirm_kb(service_id))
    await call.answer()


@router.callback_query(F.data.startswith("svc:rnwok:"))
async def cb_renew_confirm_ok(
    call: CallbackQuery, db: Database, panel: Panel | None, user: dict
) -> None:
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"] or not service["plan_id"]:
        return await call.answer(_t("این سرویس قابل تمدید نیست."), show_alert=True)
    if panel is None:
        return await call.answer(texts.PANEL_BUSY_ALERT, show_alert=True)
    plan = await db.get_plan(service["plan_id"])
    if not plan or not plan["is_active"]:
        return await call.answer(_t("پلن این سرویس دیگه فعال نیست."), show_alert=True)

    lock = f"pay:{user['id']}"
    if not await db.acquire_lock(lock):
        return await call.answer(
            _t("یه پرداخت همین حالا در جریانه. چند لحظه صبر کن."), show_alert=True
        )
    try:
        await _do_renew(call, db, panel, user, service, plan)
    finally:
        await db.release_lock(lock)


async def _do_renew(
    call: CallbackQuery,
    db: Database,
    panel: Panel,
    user: dict,
    service: dict,
    plan: dict,
) -> None:
    """تمدید؛ منطق در app/services/renew.py است (مینی اپ هم همان را صدا می زند)."""
    from app.services import renew as renew_svc

    await ui.working(call.message, texts.building(name=esc(user.get("first_name") or "")))
    r = await renew_svc.run(db, panel, user, service, plan, idem=f"rnw:{call.id}")
    if not r.ok:
        if r.error == renew_svc.DUPLICATE:
            return await call.answer(_t("این تمدید در حال پردازشه."), show_alert=True)
        if r.error == renew_svc.NOT_ON_PANEL:
            return await call.message.edit_text(
                _t("این سرویس روی سرور پیدا نشد. به پشتیبانی خبر بده تا درستش کنیم."),
                reply_markup=keyboards.back_menu(),
            )
        if r.error == renew_svc.INSUFFICIENT:
            return await call.message.edit_text(texts.INSUFFICIENT, reply_markup=keyboards.insufficient_kb())
        return await call.message.edit_text(texts.PANEL_ERROR, reply_markup=keyboards.back_menu())
    txn_id = r.txn_id

    service_id = int(service["id"])
    fresh = await db.get_user(user["id"])
    body = texts.renew_success(balance=f"{fresh['balance']:,}")
    markup = keyboards.service_detail_kb(service_id, service["sub_url"])
    # پیام تازه می فرستیم نه ویرایش، چون افکت فقط روی ارسال سوار می شود
    fx = effects.kwargs(effects.PURCHASE, call.message.chat.id)
    for attempt_fx in ((fx, {}) if fx else ({},)):
        try:
            await call.message.answer(body, reply_markup=markup, **attempt_fx)
            try:
                await call.message.delete()
            except Exception:  # noqa: BLE001
                pass
            break
        except Exception as exc:  # noqa: BLE001
            if attempt_fx:
                effects.disable(effects.PURCHASE, str(exc))
                continue
            await call.message.edit_text(body, reply_markup=markup)

    invalidate_usage(service_id)

    # پاداش معرف برای تمدید هم داده می شود (درآمد تکرارشونده معرف)
    await referral.reward_purchase(
        call.bot, db, user, int(plan["price"]), txn_id, "سرویسش رو تمدید کرد"
    )
    await call.answer()


# ==================== دستگاه های متصل (HWID) ====================
async def _owned(call: CallbackQuery, db: Database, user: dict) -> dict | None:
    """سرویس متعلق به همین کاربر. None یعنی پیدا نشد یا مال او نیست."""
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"]:
        await call.answer(_t("این سرویس پیدا نشد."), show_alert=True)
        return None
    return service


async def _show_devices(
    call: CallbackQuery, service: dict, panel: Panel, note: str = ""
) -> None:
    from app import devices as dev

    name = esc((service["label"] or "").strip() or f"{_t('سرویس')} {service['id']}")
    try:
        rows = await panel.get_hwids(service["panel_username"])
    except PanelError as exc:
        log.warning("خواندن دستگاه های %s نشد: %s", service["panel_username"], exc)
        rows = None
    if rows is None:
        # پنل این قابلیت را ندارد یا خاموش است. کاربر نباید پیام فنی ببیند.
        return await edit_or_send(
            call.message,
            texts.DEVICES_UNAVAILABLE,
            keyboards.service_detail_kb(service["id"], service["sub_url"], True),
        )
    if not rows:
        return await edit_or_send(
            call.message,
            texts.DEVICES_EMPTY.format(name=name),
            keyboards.devices_kb(service["id"], has_devices=False),
        )

    limit = 0
    try:
        pu = await panel.get_user(service["panel_username"])
        limit = dev.limit_of(pu) if pu else 0
    except PanelError:
        pass

    if not note and limit and len(rows) >= limit:
        note = texts.DEVICES_NOTE_FULL

    markup = keyboards.devices_kb(service["id"], has_devices=True)
    caption = (
        f"📱 {_t('دستگاه های متصل')} - {name} - {len(rows)} {_t('دستگاه')}"
        + (f" {_t('از')} {limit}" if limit else "")
    )

    # این صفحه هم آماری/جدولی است؛ همان الگوی سوابق: اول جدول واقعی،
    # اگر نشد نسخه متنی.
    try:
        from app import richtable

        rich = richtable.table(
            headers=[_t("دستگاه"), _t("سیستم عامل"), _t("آخرین اتصال")],
            rows=[list(dev.columns(r)) for r in rows[:20]],
            caption=caption,
        )
        await ui.edit_or_send_rich(call.message, rich, markup)
        return
    except Exception:  # noqa: BLE001
        log.warning(
            "جدول دستگاه ها (Rich Message) کار نکرد، نسخه متنی جایگزین شد", exc_info=True
        )

    lines = [
        texts.DEVICE_ROW.format(
            icon=dev.icon_and_os(r)[0],
            title=esc(dev.title(r)),
            last=dev.last_seen(r),
        )
        for r in rows[:10]
    ]
    await edit_or_send(
        call.message,
        texts.DEVICES.format(
            name=name,
            count=len(rows),
            limit=f" {_t('از')} {limit}" if limit else "",
            rows="\n\n".join(lines),
            note=note,
        ),
        keyboards.devices_kb(service["id"], has_devices=True),
    )


@router.callback_query(F.data.startswith("svc:dev:"))
async def cb_devices(
    call: CallbackQuery, db: Database, panel: Panel | None, user: dict
) -> None:
    service = await _owned(call, db, user)
    if not service:
        return
    if panel is None:
        return await call.answer(texts.PANEL_BUSY_ALERT, show_alert=True)
    await _show_devices(call, service, panel)
    await call.answer()


@router.callback_query(F.data.startswith("svc:devout:"))
async def cb_devices_kick_ask(
    call: CallbackQuery, db: Database, panel: Panel | None, user: dict
) -> None:
    service = await _owned(call, db, user)
    if not service:
        return
    if panel is None:
        return await call.answer(texts.PANEL_BUSY_ALERT, show_alert=True)
    rows = await panel.get_hwids(service["panel_username"]) or []
    await edit_or_send(
        call.message,
        texts.DEVICES_KICK_ASK.format(count=len(rows)),
        keyboards.devices_kick_kb(service["id"]),
    )
    await call.answer()


@router.callback_query(F.data.startswith("svc:devoutok:"))
async def cb_devices_kick(
    call: CallbackQuery, db: Database, panel: Panel | None, user: dict
) -> None:
    """خروج همه دستگاه ها.

    قفل کوتاه دارد تا با چند کلیک پشت سر هم، پنل زیر بار درخواست نرود.
    """
    service = await _owned(call, db, user)
    if not service:
        return
    if panel is None:
        return await call.answer(texts.PANEL_BUSY_ALERT, show_alert=True)
    if not await db.acquire_lock(f"hwid:{service['id']}", ttl_seconds=60):
        return await call.answer(texts.DEVICES_BUSY, show_alert=True)

    if not await panel.reset_hwids(service["panel_username"]):
        await edit_or_send(
            call.message,
            texts.DEVICES_KICK_FAILED,
            keyboards.devices_kb(service["id"], has_devices=True),
        )
        return await call.answer()

    await call.answer(texts.DEVICES_KICKED, show_alert=True)
    await _show_devices(call, service, panel)


@router.callback_query(F.data.startswith("svc:devnew:"))
async def cb_devices_reset_ask(call: CallbackQuery, db: Database, user: dict) -> None:
    service = await _owned(call, db, user)
    if not service:
        return
    name = esc((service["label"] or "").strip() or f"{_t('سرویس')} {service['id']}")
    await edit_or_send(
        call.message,
        texts.DEVICES_RESET_ASK.format(name=name),
        keyboards.devices_reset_kb(service["id"]),
    )
    await call.answer()


@router.callback_query(F.data.startswith("svc:devnewok:"))
async def cb_devices_reset(
    call: CallbackQuery, db: Database, panel: Panel | None, user: dict
) -> None:
    """خروج دستگاه ها + لینک تازه.

    ترتیب مهم است: اول دستگاه ها پاک می شوند بعد لینک باطل می شود. اگر
    ابطال لینک شکست بخورد، لینک قدیمی کاربر سر جایش است و فقط دستگاه ها
    خارج شده اند؛ برعکسش یعنی کاربر لینک تازه بگیرد ولی ظرفیت دستگاهش
    هنوز پر باشد.
    """
    service = await _owned(call, db, user)
    if not service:
        return
    if panel is None:
        return await call.answer(texts.PANEL_BUSY_ALERT, show_alert=True)
    if not await db.acquire_lock(f"hwid:{service['id']}", ttl_seconds=60):
        return await call.answer(texts.DEVICES_BUSY, show_alert=True)

    working = await ui.working(call.message, texts.DEVICES_WORKING)
    kicked = await panel.reset_hwids(service["panel_username"])

    fresh = await panel.revoke_sub(service["panel_username"])
    if fresh is None:
        # لینک عوض نشد؛ لینک ذخیره شده را هم دست نمی زنیم
        await edit_or_send(
            working,
            texts.SERVICE_RELINK_FAILED,
            keyboards.devices_kb(service["id"], has_devices=True),
        )
        return await call.answer()

    new_sub = sub_url_of(fresh, panel.base_url)
    await db.update_service_sub(service["id"], new_sub)
    invalidate_usage(service["id"])

    name = esc((service["label"] or "").strip() or f"{_t('سرویس')} {service['id']}")
    await edit_or_send(
        working,
        texts.DEVICES_RESET_DONE.format(
            name=name,
            kicked=(
                _t("همه دستگاه ها خارج شدن و ")
                if kicked
                else _t("دستگاه ها پاک نشدن ولی ")
            ),
            sub_url=esc(new_sub),
        ),
        keyboards.service_detail_kb(service["id"], new_sub, True),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    await call.answer(_t("انجام شد"))


# ==================== ابطال لینک ساب ====================
@router.callback_query(F.data.startswith("svc:relink:"))
async def cb_service_relink_ask(call: CallbackQuery, db: Database, user: dict) -> None:
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"]:
        return await call.answer(_t("سرویس پیدا نشد."), show_alert=True)
    name = esc((service["label"] or "").strip() or f"{_t('سرویس')} {service['id']}")
    await edit_or_send(
        call.message,
        texts.SERVICE_RELINK_ASK.format(name=name),
        keyboards.service_relink_kb(service_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("svc:relinkok:"))
async def cb_service_relink_ok(
    call: CallbackQuery, db: Database, panel: Panel | None, user: dict
) -> None:
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"]:
        return await call.answer(_t("سرویس پیدا نشد."), show_alert=True)
    if panel is None:
        return await call.answer(texts.PANEL_BUSY_ALERT, show_alert=True)

    # پنل ممکن است در دسترس نباشد (۵۲۲/تایم اوت). قبلا استثنا تا بالا
    # می رفت و کاربر هیچ پاسخی نمی گرفت؛ حالا همان پیام «انجام نشد».
    try:
        fresh = await panel.revoke_sub(service["panel_username"])
    except PanelError as exc:
        log.warning("revoke_sub برای %s نشد: %s", service["panel_username"], exc)
        fresh = None
    if fresh is None:
        await edit_or_send(
            call.message,
            texts.SERVICE_RELINK_FAILED,
            keyboards.service_detail_kb(service_id, service["sub_url"], True),
        )
        return await call.answer()

    new_sub = sub_url_of(fresh, panel.base_url)
    await db.update_service_sub(service_id, new_sub)
    invalidate_usage(service_id)

    name = esc((service["label"] or "").strip() or f"{_t('سرویس')} {service['id']}")
    await edit_or_send(
        call.message,
        texts.SERVICE_RELINKED.format(name=name, sub_url=esc(new_sub)),
        keyboards.service_detail_kb(service_id, new_sub, True),
    )
    await call.answer(_t("لینک عوض شد"))


# ==================== حذف سرویس ====================
@router.callback_query(F.data.startswith("svc:del:"))
async def cb_service_delete_ask(call: CallbackQuery, db: Database, user: dict) -> None:
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"]:
        return await call.answer(_t("سرویس پیدا نشد."), show_alert=True)

    name = esc((service["label"] or "").strip() or f"{_t('سرویس')} {service['id']}")
    body = texts.SERVICE_DELETE_ASK.format(name=name)
    # اگر سرویس هنوز اعتبار دارد، هشدار جدی تری نشان می دهیم تا کاربر
    # اشتباهی سرویس فعالی را که پولش را داده پاک نکند.
    if not is_expired(service["expire_at"]):
        body += texts.SERVICE_DELETE_ACTIVE_WARN
    await edit_or_send(call.message, body, keyboards.service_delete_kb(service_id))
    await call.answer()


@router.callback_query(F.data.startswith("svc:delok:"))
async def cb_service_delete_ok(
    call: CallbackQuery, db: Database, panel: Panel | None, user: dict
) -> None:
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"]:
        return await call.answer(_t("سرویس پیدا نشد."), show_alert=True)

    # اول از پنل، بعد از دیتابیس. اگر ترتیب برعکس بود و حذف از پنل
    # شکست می خورد، سرویس از لیست کاربر می رفت ولی روی سرور زنده
    # می ماند و حجم مصرف می کرد.
    if panel is not None:
        if not await panel.remove(service["panel_username"]):
            log.error("حذف از پنل ناموفق: %s", service["panel_username"])
            return await edit_or_send(
                call.message,
                texts.SERVICE_DELETE_FAILED,
                keyboards.service_detail_kb(service_id, service["sub_url"], True),
            )

    name = esc((service["label"] or "").strip() or f"{_t('سرویس')} {service['id']}")
    await db.delete_service(service_id, user["id"])

    services = await db.user_services(user["id"])
    if services:
        await edit_or_send(
            call.message,
            texts.SERVICE_DELETED.format(name=name),
            keyboards.services_kb(services),
        )
    else:
        await edit_or_send(
            call.message, texts.SERVICES_EMPTY, keyboards.back_menu()
        )
    await call.answer(_t("حذف شد"))


# ==================== انتخاب نام برای سرویس ====================
@router.callback_query(F.data.startswith("svc:nm:"))
async def cb_service_rename(
    call: CallbackQuery, db: Database, user: dict, state: FSMContext
) -> None:
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service or service["user_id"] != user["id"]:
        return await call.answer(_t("سرویس پیدا نشد."), show_alert=True)

    await state.set_state(Service.waiting_name)
    await state.update_data(service_id=service_id)
    await edit_or_send(call.message, texts.SERVICE_NAME_ASK, keyboards.back_menu())
    await call.answer()


@router.message(Service.waiting_name, F.text)
async def txt_service_name(
    message: Message, db: Database, user: dict, state: FSMContext
) -> None:
    data = await state.get_data()
    service_id = data.get("service_id")
    if not service_id:
        await state.clear()
        return await message.answer(_t("یه اشتباهی پیش اومد. دوباره از سرویس های من شروع کن."))

    raw = (message.text or "").strip()
    if len(raw) > 30:
        return await message.answer(texts.SERVICE_NAME_TOO_LONG)

    clear = raw.lower() in ("حذف", "پاک", "-", "delete", "clear", "удалить", "删除")
    label = None if clear else raw

    if not await db.set_service_label(service_id, user["id"], label):
        await state.clear()
        return await message.answer(_t("سرویس پیدا نشد."))

    await state.clear()
    await message.answer(
        texts.SERVICE_NAME_CLEARED
        if clear
        else texts.SERVICE_NAME_OK.format(name=esc(label))
    )

    services = await db.user_services(user["id"])
    await message.answer(
        texts.SERVICES_LIST.format(count=len(services)),
        reply_markup=keyboards.services_kb(services),
    )
