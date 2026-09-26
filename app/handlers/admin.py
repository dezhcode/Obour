"""پنل ادمین: داشبورد، تایید شارژ، مدیریت کاربر، پلن ها، تنظیمات، پیام همگانی."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject

from app import i18n, broadcast, effects, features, polls
from app import emoji as emo
from app import keyboards, texts, ui
from app.config import config
from app.db import Database
from app.keyboards import is_admin
from app.panel import Panel, PanelError
from app.services import admin_ops
from app.states import Admin
from app.ui import edit_or_send
from app.utils import (
    TZ,
    esc,
    fmt_data,
    fmt_dt,
    now_str,
    service_status,
    time_left_text,
    usage_bar,
    usage_percent,
)

log = logging.getLogger("obour.admin")
router = Router(name="admin")


class AdminOnly(BaseFilter):
    """فیلتر سطح روتر: هیچ آپدیتی بدون ادمین بودن وارد این فایل نمی شود.

    چرا حیاتی است؟
    کال بک دیتا از سمت کاربر می آید و با کلاینت های غیررسمی می توان هر
    رشته ای فرستاد. اگر این فیلتر نباشد، یک کاربر عادی می تواند
    chg:ok:<id> بفرستد و رسید خودش را تایید کند یا با adm:uadd موجودی
    خودش را بالا ببرد. چک کردن تک تک هندلرها فراموش شدنی است، پس یک بار
    روی خود روتر بسته می شود.
    """

    async def __call__(self, event: TelegramObject) -> bool:  # noqa: D102
        # این فیلتر روی *هر* آپدیتی که به روتر ادمین می رسد اجرا می شود،
        # و چون روتر ادمین زود ثبت شده، یعنی روی هر کلیک هر کاربری.
        # پس اینجا فقط True/False برمی گردانیم و هیچ پیامی نمی دهیم؛
        # در غیر این صورت کاربر عادی با هر دکمه ای که بزند پیام
        # «این بخش مخصوص مدیره» می گیرد، حتی روی دکمه های خودش.
        user = getattr(event, "from_user", None)
        return user is not None and is_admin(user.id)


router.message.filter(AdminOnly())
router.callback_query.filter(AdminOnly())


# ---------- تست افکت ----------
@router.message(F.text.regexp(r"^/fx(\s|$)"))
async def cmd_effect_test(message: Message) -> None:
    """تست یک آیدی افکت بدون نیاز به دپلوی دوباره.

        /fx                  -> آیدی های فعلی .env را تست می کند
        /fx 5046509860389126442  -> یک آیدی دلخواه را تست می کند

    ربات ها فقط افکت های رایگان را می توانند بفرستند. اگر آیدی مال یک
    افکت پریمیوم باشد، تلگرام PREMIUM_ACCOUNT_REQUIRED برمی گرداند.
    با این دستور می شود آیدی ها را یکی یکی امتحان کرد و آن هایی را که
    کار می کنند در .env گذاشت.
    """
    parts = (message.text or "").split()
    if len(parts) > 1:
        targets = [(f"دلخواه {parts[1]}", parts[1])]
    else:
        # مقدار فعلی واقعی تست می شود: اگر از پنل ادمین override شده،
        # همان تست می شود، نه لزوما مقدار .env
        targets = [
            (f"تست رایگان ({effects.source('trial')})", effects.current_id("trial")),
            (f"شارژ ({effects.source('charge')})", effects.current_id("charge")),
            (f"خرید/تمدید ({effects.source('purchase')})", effects.current_id("purchase")),
        ]

    lines = []
    for name, eid in targets:
        if not eid:
            lines.append(f"⚪️ {name} — تنظیم نشده")
            continue
        try:
            await message.answer(f"نمونه افکت: {name}", message_effect_id=eid)
            lines.append(f"✅ {name} — <code>{eid}</code>")
        except TypeError:
            lines.append("❌ نسخه aiogram از افکت پشتیبانی نمی کند")
            break
        except Exception as exc:  # noqa: BLE001
            reason = str(exc)
            if "PREMIUM" in reason.upper():
                reason = "افکت پریمیوم است، ربات نمی تواند بفرستد"
            lines.append(f"❌ {name} — {esc(reason)[:80]}")

    await message.answer(
        "╮── 🎬 تست افکت\n│   نتیجه\n\n"
        + "\n".join(lines)
        + "\n\n╯─ فقط افکت های بدون قفل در تلگرام قابل استفاده اند."
    )


def _version_str() -> str:
    from app.version import VERSION

    return VERSION


async def _cron_line(db: Database) -> str:
    """خط وضعیت کران برای داشبورد.

    اگر بیش از دو ساعت از آخرین اجرا گذشته باشد هشدار می دهد. بازه دو
    ساعت عمدا از فاصله پیشنهادی کران (۱۵ دقیقه) خیلی بیشتر است تا یک
    تاخیر معمولی یا ریستارت، هشدار کاذب نسازد.
    """
    last = await db.get_setting("last_cron_at")
    if not last:
        return texts.ADMIN_CRON_NEVER
    try:
        when = datetime.fromisoformat(last)
        stale = (datetime.now(TZ) - when) > timedelta(hours=2)
    except (ValueError, TypeError):
        return texts.ADMIN_CRON_NEVER
    tpl = texts.ADMIN_CRON_STALE if stale else texts.ADMIN_CRON_OK
    return tpl.format(when=fmt_dt(last))


# ---------- داشبورد ----------
@router.message(F.text.regexp(r"^/admin$"))
async def cmd_admin(message: Message, db: Database) -> None:
    stats = await db.dashboard_stats()
    await message.answer(
        texts.ADMIN_DASH.format(
            total_users=stats["total_users"],
            active_services=stats["active_services"],
            today_sales=f"{stats['today_sales']:,}",
            pending_count=stats["pending_count"],
            cron=await _cron_line(db),
        ),
        reply_markup=keyboards.admin_dash_kb(),
    )


@router.callback_query(F.data == "adm")
async def cb_admin(call: CallbackQuery, db: Database) -> None:
    stats = await db.dashboard_stats()
    await edit_or_send(
        call.message,
        texts.ADMIN_DASH.format(
            total_users=stats["total_users"],
            active_services=stats["active_services"],
            today_sales=f"{stats['today_sales']:,}",
            pending_count=stats["pending_count"],
            cron=await _cron_line(db) + f"\n\n🏷 نسخه {_version_str()}",
        ),
        keyboards.admin_dash_kb(),
    )
    await call.answer()


async def _notify_user(bot, telegram_id: int, body: str, effect: str = "", lang: str | None = None) -> str:  # noqa: ANN001
    """خبر دادن به کاربر؛ خروجی خالی یعنی موفق، وگرنه علت شکست (admin_ops)."""
    return await admin_ops.notify_user(bot, telegram_id, body, effect=effect, lang=lang)


# ---------- تایید شارژ (مهم ترین بخش) ----------
@router.callback_query(F.data == "adm:chg")
async def cb_admin_charges(call: CallbackQuery, db: Database) -> None:
    """فهرست شارژهای در انتظار، با یک دکمه شیشه ای برای هر رسید."""
    pending = await db.pending_charges()
    if not pending:
        await edit_or_send(
            call.message, texts.ADMIN_NO_PENDING, keyboards.admin_dash_kb()
        )
        return await call.answer()

    items = [
        texts.ADMIN_PENDING_ROW.format(
            name=esc((t.get("first_name") or "-").strip()),
            amount=f"{t['amount']:,}",
            code=t.get("code") or f"#{t['id']}",
            when=fmt_dt(t["created_at"]),
        )
        for t in pending[:10]
    ]
    await edit_or_send(
        call.message,
        texts.ADMIN_PENDING_LIST.format(count=len(pending), items="\n\n".join(items)),
        keyboards.admin_pending_kb(pending),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:chgv:"))
async def cb_admin_charge_view(call: CallbackQuery, db: Database) -> None:
    """باز کردن یک رسید از فهرست پنل: خود عکس فیش دوباره فرستاده می شود.

    هدف این است که ادمین برای پیدا کردن فیش، لای پیام های قدیمی ربات
    نگردد. پیام فهرست حذف می شود و جایش عکس رسید با همان دکمه های
    تایید/رد می آید - به علاوه دکمه برگشت به فهرست.
    """
    # کالبک «adm:chgv:<id>» سه بخش دارد، پس آیدی ایندکس ۲ است. قبلا
    # ۳ نوشته شده بود و هر کلیک IndexError می داد - همان «مشکلی پیش اومد».
    txn_id = int(call.data.split(":")[2])
    txn = await db.get_transaction(txn_id)
    if not txn or txn["status"] != "pending":
        await call.answer(texts.ADMIN_CHARGE_GONE, show_alert=True)
        return await cb_admin_charges(call, db)

    user = await db.get_user(txn["user_id"])
    caption = texts.ADMIN_CHARGE_REVIEW.format(
        name=esc((user.get("first_name") or "-").strip()),
        username=esc(user.get("username") or "-"),
        telegram_id=user["telegram_id"],
        amount=f"{txn['amount']:,}",
        code=txn.get("code") or f"#{txn['id']}",
        when=fmt_dt(txn["created_at"]),
        balance=f"{user['balance']:,}",
    )
    markup = keyboards.admin_charge_kb(txn_id, from_panel=True)

    file_id = txn.get("receipt_file_id")
    if not file_id:
        # رسیدی ثبت نشده (نباید پیش بیاید چون pending_charges فیلتر دارد،
        # ولی اگر از جای دیگری صدا زده شد، متن جایگزین می شود)
        await edit_or_send(call.message, caption, markup)
        return await call.answer()

    try:
        await call.message.delete()
    except Exception:  # noqa: BLE001
        pass
    await call.bot.send_photo(
        chat_id=call.message.chat.id,
        photo=file_id,
        caption=caption,
        reply_markup=markup,
    )
    await call.answer()


@router.callback_query(F.data.startswith("chg:ok:"))
async def cb_charge_approve(call: CallbackQuery, db: Database) -> None:
    txn_id = int(call.data.split(":")[2])
    r = await admin_ops.approve_charge(call.bot, db, txn_id, call.from_user.id)
    if not r["ok"]:
        return await call.answer("این رسید قبلا بررسی شده.", show_alert=True)

    try:
        await call.message.edit_reply_markup(reply_markup=None)
        if call.message.caption is not None:
            await call.message.edit_caption(
                caption=(call.message.caption or "")
                + "\n\n"
                + texts.ADMIN_DECIDED.format(time=fmt_dt(now_str()))
            )
        else:
            await call.message.edit_text(
                text=(call.message.text or "") + "\n\n"
                + texts.ADMIN_DECIDED.format(time=fmt_dt(now_str()))
            )
    except Exception:  # noqa: BLE001
        pass

    err = r["notify_err"]
    if err:
        # شارژ انجام شده ولی کاربر خبر ندارد؛ ادمین باید همین حالا بداند
        await call.answer(
            f"شارژ شد ✅ ولی پیام به کاربر نرسید:\n{err}", show_alert=True
        )
        return
    await call.answer("تایید شد ✅")


@router.callback_query(F.data.startswith("chg:dup:"))
async def cb_charge_duplicate(call: CallbackQuery, db: Database) -> None:
    txn_id = int(call.data.split(":")[2])
    r = await admin_ops.duplicate_charge(call.bot, db, txn_id, call.from_user.id)
    if not r["ok"]:
        return await call.answer("این رسید قبلا بررسی شده.", show_alert=True)
    notify_err = r["notify_err"]
    # ثبت وضعیت روی پیام (بخش ۱۵.۲ سند): جلوگیری از بررسی دوباره
    try:
        await call.message.edit_caption(
            caption=(call.message.caption or "")
            + "\n\n"
            + texts.ADMIN_DUP.format(time=fmt_dt(now_str())),
            reply_markup=None,
        )
    except Exception:  # noqa: BLE001
        await call.message.edit_reply_markup(reply_markup=None)
    await call.answer(
        f"ثبت شد 🔁 ولی پیام به کاربر نرسید:\n{notify_err}" if notify_err else "ثبت شد 🔁",
        show_alert=bool(notify_err),
    )


async def _finalize_reject(
    bot,  # noqa: ANN001
    db: Database,
    txn_id: int,
    admin_id: int,
    reason: str,
    chat_id: int,
    message_id: int,
    old_text: str,
    is_caption: bool,
) -> tuple[bool, str | None]:
    """رد یک شارژ - چه با دلیل آماده، چه با دلیل دستی تایپ شده.

    هر دو مسیر (دکمه دلیل آماده و پیام متنی دلیل دستی) به این تابع
    می رسند تا رفتار (اطلاع به کاربر، ثبت روی پیام رسید) یک جا بماند
    و دوباره نویسی نشود.

    خروجی: (موفق بود؟، خطای اطلاع رسانی به کاربر یا None)
    False در جای اول یعنی این رسید قبلا بررسی شده بود.
    """
    r = await admin_ops.reject_charge(bot, db, txn_id, admin_id, reason)
    if not r["ok"]:
        return False, None
    notify_err = r["notify_err"]
    suffix = "\n\n" + texts.ADMIN_DECIDED_REJ.format(reason=reason, time=fmt_dt(now_str()))
    try:
        if is_caption:
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=(old_text or "") + suffix,
                reply_markup=None,
            )
        else:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=(old_text or "") + suffix,
                reply_markup=None,
            )
    except Exception:  # noqa: BLE001
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except Exception:  # noqa: BLE001
            pass
    return True, notify_err


@router.callback_query(F.data.startswith("chg:back:"))
async def cb_charge_back(call: CallbackQuery) -> None:
    """برگشت از صفحه دلایل رد به همان سه دکمه تایید/رد/تکراری.

    قبلا این دکمه به لیست شارژهای در انتظار می رفت و روی پیام رسید
    (که عکس است، نه متن) با edit_text خطا می داد. حالا فقط کیبورد
    همین پیام را به حالت اول برمی گرداند.
    """
    txn_id = int(call.data.split(":")[2])
    try:
        await call.message.edit_reply_markup(
            reply_markup=keyboards.admin_charge_kb(txn_id)
        )
    except Exception:  # noqa: BLE001
        pass
    await call.answer()


@router.callback_query(F.data.startswith("chg:no:"))
async def cb_charge_reject(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    parts = call.data.split(":")
    txn_id = int(parts[2])
    if len(parts) < 4:
        # نمایش دلایل آماده + گزینه دلیل دستی
        await call.message.edit_reply_markup(
            reply_markup=keyboards.admin_reject_reasons_kb(txn_id)
        )
        return await call.answer()

    reason_code = parts[3]
    if reason_code == "custom":
        # دلیل دستی: عنوان رد را از ادمین در پیام بعدی می گیریم
        await state.set_state(Admin.waiting_reject_reason)
        await state.update_data(
            txn_id=txn_id,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            old_text=call.message.caption or call.message.text or "",
            is_caption=call.message.caption is not None,
        )
        await call.message.answer(texts.ADMIN_REJECT_REASON_PROMPT)
        return await call.answer()

    reason = texts.REJECT_REASONS.get(reason_code, reason_code)
    ok, notify_err = await _finalize_reject(
        call.bot,
        db,
        txn_id,
        call.from_user.id,
        reason,
        call.message.chat.id,
        call.message.message_id,
        call.message.caption or call.message.text or "",
        call.message.caption is not None,
    )
    if not ok:
        return await call.answer("این رسید قبلا بررسی شده.", show_alert=True)
    await call.answer(
        f"رد شد ❌ ولی پیام به کاربر نرسید:\n{notify_err}" if notify_err else "رد شد ❌",
        show_alert=bool(notify_err),
    )


@router.message(Admin.waiting_reject_reason, F.text)
async def txt_reject_reason(message: Message, db: Database, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    reason = message.text.strip()[:300]
    if not reason:
        return await message.answer("یه متن بفرست؛ همین که تایپ کنی برای کاربر ارسال می شه.")
    ok, notify_err = await _finalize_reject(
        message.bot,
        db,
        data["txn_id"],
        message.from_user.id,
        reason,
        data["chat_id"],
        data["message_id"],
        data.get("old_text", ""),
        data.get("is_caption", True),
    )
    if not ok:
        return await message.answer("این رسید قبلا بررسی شده.")
    await message.answer(
        f"رد شد ❌ ولی پیام به کاربر نرسید:\n{notify_err}" if notify_err else "رد شد ❌"
    )


# ---------- مدیریت کاربر ----------
@router.callback_query(F.data == "adm:usr")
async def cb_admin_user(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.waiting_user_query)
    await call.message.edit_text(
        "آیدی عددی، یوزرنیم، یا مبلغ رسید را بفرست:\n\n"
        "<i>اگر مبلغ رسید را بفرستی (مثلا 20072)، صاحبش را پیدا می کنم.</i>",
        reply_markup=keyboards.admin_dash_kb(),
    )
    await call.answer()


@router.message(Admin.waiting_user_query, F.text)
async def txt_user_query(message: Message, db: Database, state: FSMContext) -> None:
    await state.clear()
    query = message.text.strip().lstrip("@").replace(",", "").replace("،", "")
    user = None
    if query.isdigit():
        n = int(query)
        user = await db.get_user_by_tg(n)
        # اگر آیدی نبود، شاید مبلغ رسید باشد
        if not user:
            pending = await db.find_by_amount(n)
            if pending:
                user = await db.get_user(pending["user_id"])
                if user:
                    await message.answer(
                        f"🔎 مبلغ {n:,} تومان متعلق به این کاربر است:"
                    )
    if not user:
        row = await db.fetchone(
            "SELECT * FROM users WHERE username = ?", (query,)
        )
        user = dict(row) if row else None
    if not user:
        return await message.answer(texts.ADMIN_USER_NOT_FOUND)

    svc = await db.user_services(user["id"])
    await message.answer(
        texts.ADMIN_USER_PROFILE.format(
            name=esc(user.get("first_name") or "-"),
            username=esc(user.get("username") or "-"),
            telegram_id=user["telegram_id"],
            balance=f"{user['balance']:,}",
            created_at=fmt_dt(user["created_at"]),
            services_count=len(svc),
            blocked="مسدود 🚫" if user["is_blocked"] else "عادی",
        ),
        reply_markup=keyboards.admin_user_kb(user["telegram_id"], bool(user["is_blocked"])),
    )


@router.callback_query(F.data.startswith("adm:ub:"))
async def cb_toggle_block(call: CallbackQuery, db: Database) -> None:
    tg_id = int(call.data.split(":")[2])
    user = await db.get_user_by_tg(tg_id)
    if not user:
        return await call.answer("کاربر پیدا نشد.", show_alert=True)
    new_state = 0 if user["is_blocked"] else 1
    if not await admin_ops.set_blocked(db, tg_id, bool(new_state), call.from_user.id):
        return await call.answer("ادمین را نمی شود مسدود کرد.", show_alert=True)
    await call.answer("مسدود شد 🚫" if new_state else "رفع مسدودی شد ✅")
    await cb_admin_user_refresh(call, db, tg_id)


async def cb_admin_user_refresh(call: CallbackQuery, db: Database, tg_id: int) -> None:
    user = await db.get_user_by_tg(tg_id)
    svc = await db.user_services(user["id"])
    try:
        await call.message.edit_text(
            texts.ADMIN_USER_PROFILE.format(
                name=esc(user.get("first_name") or "-"),
                username=esc(user.get("username") or "-"),
                telegram_id=user["telegram_id"],
                balance=f"{user['balance']:,}",
                created_at=fmt_dt(user["created_at"]),
                services_count=len(svc),
                blocked="مسدود 🚫" if user["is_blocked"] else "عادی",
            ),
            reply_markup=keyboards.admin_user_kb(user["telegram_id"], bool(user["is_blocked"])),
        )
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("adm:uadd:"))
async def cb_manual_add(call: CallbackQuery, state: FSMContext) -> None:
    tg_id = int(call.data.split(":")[2])
    await state.set_state(Admin.waiting_balance_delta)
    await state.update_data(tg_id=tg_id, direction="add")
    await call.message.answer(texts.ADMIN_BALANCE_PROMPT_ADD)
    await call.answer()


@router.callback_query(F.data.startswith("adm:usub:"))
async def cb_manual_sub(call: CallbackQuery, state: FSMContext) -> None:
    tg_id = int(call.data.split(":")[2])
    await state.set_state(Admin.waiting_balance_delta)
    await state.update_data(tg_id=tg_id, direction="sub")
    await call.message.answer(texts.ADMIN_BALANCE_PROMPT_SUB)
    await call.answer()


@router.message(Admin.waiting_balance_delta, F.text)
async def txt_manual_balance(message: Message, db: Database, state: FSMContext) -> None:
    raw = message.text.strip().replace(",", "")
    if not raw.isdigit() or int(raw) <= 0:
        return await message.answer("لطفا یه عدد مثبت به تومان بفرست.")
    data = await state.get_data()
    await state.clear()
    r = await admin_ops.adjust_balance(
        message.bot, db, int(data["tg_id"]), int(raw), data["direction"] == "add", message.from_user.id,
    )
    if not r["ok"]:
        return await message.answer(r["error"])
    note = texts.ADMIN_BALANCE_DONE.format(balance=f"{r['balance']:,}")
    if r["notify_err"]:
        note += f"\n\n⚠️ پیام به کاربر نرسید: {esc(r['notify_err'])}"
    await message.answer(note)


# ---------- مدیریت پلن ها ----------
@router.callback_query(F.data == "adm:groups")
async def cb_admin_groups(call: CallbackQuery, panel: Panel | None) -> None:
    """نمایش گروه هایی که سرویس ها با آن ساخته می شوند (کش تازه می شود)."""
    if panel is None:
        return await call.answer("پنل تنظیم نشده است.", show_alert=True)
    await call.answer("در حال خواندن از پنل...")
    try:
        ids = await panel.fetch_group_ids(force=True)
    except Exception as exc:  # noqa: BLE001
        return await call.message.edit_text(
            f"خواندن گروه ها ناموفق بود:\n{exc}",
            reply_markup=keyboards.admin_setting_kb(),
        )
    mode = "همه گروه های پنل" if panel.uses_all_groups else "گروه مشخص"
    await call.message.edit_text(
        "🌐 گروه های پنل\n\n"
        f"حالت: {mode}\n"
        f"تعداد: {len(ids)}\n"
        f"آیدی ها: {', '.join(map(str, ids))}\n\n"
        "سرویس های جدید با همین گروه ها ساخته می شوند.",
        reply_markup=keyboards.admin_setting_kb(),
    )


# ==================== لیست کاربران ====================
_USERS_PER_PAGE = 8


@router.callback_query(F.data.startswith("adm:ulist:"))
async def cb_users_list(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    parts = call.data.split(":")
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    sort = parts[3] if len(parts) > 3 else "recent"
    users, total = await db.users_page(page, _USERS_PER_PAGE, sort)
    labels = dict(keyboards.USER_SORTS)
    pages = max(1, -(-total // _USERS_PER_PAGE))
    await edit_or_send(
        call.message,
        texts.ADMIN_USERS_LIST.format(
            total=total,
            page=page + 1,
            pages=pages,
            sort=labels.get(sort, sort),
        ),
        keyboards.admin_users_kb(users, page, total, _USERS_PER_PAGE, sort),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:u:"))
async def cb_user_detail(call: CallbackQuery, db: Database) -> None:
    """پروفایل کامل یک کاربر."""
    tg_id = int(call.data.split(":")[2])
    user = await db.get_user_by_tg(tg_id)
    if not user:
        return await call.answer("کاربر پیدا نشد.", show_alert=True)
    st = await db.user_summary(user["id"])
    await edit_or_send(
        call.message,
        texts.ADMIN_USER_FULL.format(
            name=esc(user.get("first_name") or "بی نام"),
            username=f"@{esc(user['username'])}" if user.get("username") else "",
            telegram_id=tg_id,
            joined=fmt_dt(user["created_at"]),
            status="مسدود 🚫" if user["is_blocked"] else "فعال ✅",
            balance=f"{user['balance']:,}",
            charged=f"{st.get('charged', 0):,}",
            spent=f"{st.get('spent', 0):,}",
            pending=st.get("pending", 0),
            services=st.get("services", 0),
            referrals=st.get("referrals", 0),
            trial="گرفته ✅" if user["free_trial_used"] else "نگرفته",
        ),
        keyboards.admin_user_kb(tg_id, bool(user["is_blocked"])),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:usvc:"))
async def cb_user_services(call: CallbackQuery, db: Database) -> None:
    """سرویس های یک کاربر از دید ادمین."""
    tg_id = int(call.data.split(":")[2])
    user = await db.get_user_by_tg(tg_id)
    if not user:
        return await call.answer("کاربر پیدا نشد.", show_alert=True)

    name = esc((user.get("first_name") or "بی نام").strip())
    services = await db.user_services(user["id"])
    if not services:
        await edit_or_send(
            call.message,
            texts.ADMIN_USER_SERVICES_EMPTY.format(name=name),
            keyboards.admin_user_services_kb(tg_id, []),
        )
        return await call.answer()

    rows = []
    for sv in services[:10]:
        plan = await db.get_plan(sv["plan_id"]) if sv["plan_id"] else None
        rows.append(
            texts.ADMIN_USER_SERVICE_ROW.format(
                status=texts.SVC_STATUS[
                    service_status(sv["expire_at"], 0, None, sv.get("duration_days"))
                ],
                label=esc((sv.get("label") or "").strip() or f"سرویس {sv['id']}"),
                plan=esc(plan["title"]) if plan else "دلخواه",
                used="؟",  # مصرف لحظه ای فقط در صفحه جزئیات خوانده می شود
                total=f"{sv['data_gb']} GB" if sv.get("data_gb") else "نامحدود",
                left=time_left_text(sv["expire_at"]),
            )
        )
    await edit_or_send(
        call.message,
        texts.ADMIN_USER_SERVICES.format(
            name=name, count=len(services), rows="\n\n".join(rows)
        ),
        keyboards.admin_user_services_kb(tg_id, services),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:svcv:"))
async def cb_admin_service_detail(
    call: CallbackQuery, db: Database, panel: Panel | None
) -> None:
    """جزئیات یک سرویس از دید ادمین: مصرف زنده + لینک ساب.

    لینک ساب اینجا نشان داده می شود تا اگر کاربری گفت «لینکم گم شده»،
    بدون اینکه از او بخواهی کاری کند، مستقیم برایش بفرستی.
    """
    service_id = int(call.data.split(":")[2])
    service = await db.get_service(service_id)
    if not service:
        return await call.answer("این سرویس پیدا نشد.", show_alert=True)

    try:
        await call.answer()
    except Exception:  # noqa: BLE001
        pass

    owner = await db.get_user(service["user_id"])
    plan = await db.get_plan(service["plan_id"]) if service["plan_id"] else None

    used, limit, note = 0, None, ""
    if panel is not None:
        try:
            pu = await panel.get_user(service["panel_username"])
            if pu is not None:
                used, limit = pu.used_traffic or 0, pu.data_limit
        except PanelError as exc:
            log.warning("خواندن مصرف %s نشد: %s", service["panel_username"], exc)
            note = "\n⚠️ مصرف از پنل خوانده نشد (سرور در دسترس نیست).\n"

    await edit_or_send(
        call.message,
        texts.ADMIN_SERVICE_DETAIL.format(
            label=esc((service.get("label") or "").strip() or f"سرویس {service_id}"),
            status=texts.SVC_STATUS[
                service_status(service["expire_at"], used, limit, service.get("duration_days"))
            ],
            owner=esc((owner.get("first_name") or "بی نام").strip()) if owner else "-",
            telegram_id=owner["telegram_id"] if owner else 0,
            plan=esc(plan["title"]) if plan else "دلخواه",
            panel_username=esc(service["panel_username"]),
            bar=usage_bar(used, limit),
            percent=usage_percent(used, limit),
            used=fmt_data(used),
            total=fmt_data(limit),
            left=time_left_text(service["expire_at"]),
            expire=fmt_dt(service["expire_at"]),
            sub_url=esc(service["sub_url"] or "-"),
            note=note,
        ),
        keyboards.admin_service_kb(
            service_id,
            owner["telegram_id"] if owner else 0,
            service["sub_url"] or "",
        ),
    )


# ==================== کد تخفیف ====================
def _fmt_discount(d: dict, stats: dict) -> str:
    return texts.ADMIN_DISCOUNT.format(
        code=d["code"],
        kind="درصدی" if d["kind"] == "percent" else "مبلغ ثابت",
        amount=f"{d['amount']}٪" if d["kind"] == "percent" else f"{d['amount']:,} تومان",
        max_uses=f"{d['max_uses']:,}" if d["max_uses"] else "نامحدود",
        per_user=d["per_user_limit"],
        min_amount=f"{d['min_amount']:,} تومان" if d["min_amount"] else "ندارد",
        expires=fmt_dt(d["expires_at"]) if d["expires_at"] else "بدون انقضا",
        status="فعال ✅" if d["is_active"] else "غیرفعال 🔕",
        uses=stats["uses"],
        users=stats["users"],
        saved=f"{stats['saved']:,}",
        revenue=f"{stats['revenue']:,}",
    )


async def _dsc_home(message: Message, db: Database) -> None:
    items = await db.discounts()
    await edit_or_send(
        message,
        texts.ADMIN_DISCOUNTS.format(count=len(items)),
        keyboards.admin_discounts_kb(items),
    )


async def _dsc_view(message: Message, db: Database, did: int) -> None:
    d = await db.get_discount(did)
    if not d:
        return await _dsc_home(message, db)
    stats = await db.discount_stats(did)
    await edit_or_send(
        message, _fmt_discount(d, stats), keyboards.admin_discount_kb(did, bool(d["is_active"]))
    )


@router.callback_query(F.data == "adm:dsc")
async def cb_dsc(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await _dsc_home(call.message, db)
    await call.answer()


@router.callback_query(F.data == "adm:dsc:new")
async def cb_dsc_new(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.waiting_discount_new)
    await edit_or_send(call.message, texts.ADMIN_DISCOUNT_NEW, keyboards.back_admin_kb())
    await call.answer()


@router.message(Admin.waiting_discount_new)
async def msg_dsc_new(message: Message, db: Database, state: FSMContext) -> None:
    parts = (message.text or "").strip().replace(",", "").replace("،", "").split()
    if len(parts) < 3:
        return await message.answer(texts.ADMIN_DISCOUNT_BAD)
    code, kind_raw, amount = parts[0], parts[1].lower(), parts[2]
    if kind_raw not in ("p", "f", "percent", "fixed") or not amount.isdigit():
        return await message.answer(texts.ADMIN_DISCOUNT_BAD)
    kind = "percent" if kind_raw in ("p", "percent") else "fixed"
    amount_i = int(amount)
    if kind == "percent" and not 1 <= amount_i <= 100:
        return await message.answer("درصد باید بین ۱ تا ۱۰۰ باشه.")

    max_uses = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
    expires = None
    if len(parts) > 4 and parts[4].isdigit():
        expires = (datetime.now(TZ) + timedelta(days=int(parts[4]))).isoformat(
            timespec="seconds"
        )

    did = await db.create_discount(code, kind, amount_i, max_uses, expires)
    await state.clear()
    if did is None:
        return await message.answer(texts.ADMIN_DISCOUNT_DUP.format(code=code.upper()))
    await message.answer(texts.ADMIN_DISCOUNT_CREATED.format(code=code.upper()))
    await _dsc_view(message, db, did)


@router.callback_query(F.data.startswith("adm:dsc:tg:"))
async def cb_dsc_toggle(call: CallbackQuery, db: Database) -> None:
    did = int(call.data.split(":")[3])
    d = await db.get_discount(did)
    if d:
        await db.update_discount(did, is_active=0 if d["is_active"] else 1)
    await _dsc_view(call.message, db, did)
    await call.answer("تغییر کرد")


@router.callback_query(F.data.startswith("adm:dsc:del:yes:"))
async def cb_dsc_del(call: CallbackQuery, db: Database) -> None:
    did = int(call.data.split(":")[4])
    await db.delete_discount(did)
    await call.answer("حذف شد")
    await call.message.answer(texts.ADMIN_DISCOUNT_DELETED)
    await _dsc_home(call.message, db)


@router.callback_query(F.data.startswith("adm:dsc:del:"))
async def cb_dsc_del_ask(call: CallbackQuery, db: Database) -> None:
    did = int(call.data.split(":")[3])
    d = await db.get_discount(did)
    if not d:
        return await call.answer()
    stats = await db.discount_stats(did)
    await edit_or_send(
        call.message,
        texts.ADMIN_DISCOUNT_DEL_ASK.format(code=d["code"], uses=stats["uses"]),
        keyboards.admin_discount_del_kb(did),
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^adm:dsc:\d+$"))
async def cb_dsc_view(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await _dsc_view(call.message, db, int(call.data.split(":")[2]))
    await call.answer()


# ==================== مدیریت دسته بندی ====================
async def _cats_home(message: Message, db: Database) -> None:
    cats = await db.categories()
    for c in cats:
        c["n"] = await db.category_plan_count(c["id"])
    await edit_or_send(
        message,
        texts.ADMIN_CATS.format(count=len(cats)),
        keyboards.admin_cats_kb(cats),
    )


async def _cat_view(message: Message, db: Database, cid: int) -> None:
    cat = await db.get_category(cid)
    if not cat:
        return await _cats_home(message, db)
    cats = await db.categories()
    idx = next((i for i, c in enumerate(cats) if c["id"] == cid), 0)
    await edit_or_send(
        message,
        texts.ADMIN_CAT.format(
            emoji=cat["emoji"],
            title=cat["title"],
            status="فعال ✅" if cat["is_active"] else "غیرفعال 🔕",
            plans=await db.category_plan_count(cid),
            order=idx + 1,
        ),
        keyboards.admin_cat_kb(
            cid, bool(cat["is_active"]), idx == 0, idx == len(cats) - 1
        ),
    )


@router.callback_query(F.data == "adm:cats")
async def cb_cats(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await _cats_home(call.message, db)
    await call.answer()


@router.callback_query(F.data == "adm:cat:new")
async def cb_cat_new(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.waiting_cat_new)
    await edit_or_send(call.message, texts.ADMIN_CAT_NEW, keyboards.back_admin_kb())
    await call.answer()


@router.message(Admin.waiting_cat_new)
async def msg_cat_new(message: Message, db: Database, state: FSMContext) -> None:
    title = (message.text or "").strip()
    await ui.consume(message)
    if not title:
        return await message.answer("نام خالیه. دوباره بفرست.")
    cid = await db.create_category(title)
    await state.clear()
    await message.answer(texts.ADMIN_SAVED_SHORT)
    await _cat_view(message, db, cid)


@router.callback_query(F.data.startswith("adm:cat:f:"))
async def cb_cat_field(call: CallbackQuery, state: FSMContext) -> None:
    _, _, _, field, cid = call.data.split(":")
    if field not in texts.ADMIN_CAT_ASK:
        return await call.answer()
    await state.set_state(Admin.waiting_cat_field)
    await state.update_data(cat_id=int(cid), cat_field=field)
    await edit_or_send(
        call.message, texts.ADMIN_CAT_ASK[field], keyboards.back_admin_kb()
    )
    await call.answer()


@router.message(Admin.waiting_cat_field)
async def msg_cat_field(message: Message, db: Database, state: FSMContext) -> None:
    data = await state.get_data()
    cid, field = data.get("cat_id"), data.get("cat_field")
    value = (message.text or "").strip()
    await ui.consume(message)
    if not cid or not field or not value:
        await state.clear()
        return await message.answer("یه اشتباهی پیش اومد. دوباره شروع کن.")
    if field == "sort_order":
        if not value.isdigit():
            return await message.answer("لطفا یه عدد بفرست.")
        await db.update_category(cid, sort_order=int(value))
    else:
        await db.update_category(cid, **{field: value[:40]})
    await state.clear()
    await message.answer(texts.ADMIN_SAVED_SHORT)
    await _cat_view(message, db, cid)


@router.callback_query(F.data.startswith("adm:cat:tg:"))
async def cb_cat_toggle(call: CallbackQuery, db: Database) -> None:
    cid = int(call.data.split(":")[3])
    cat = await db.get_category(cid)
    if cat:
        await db.update_category(cid, is_active=0 if cat["is_active"] else 1)
    await _cat_view(call.message, db, cid)
    await call.answer("تغییر کرد")


@router.callback_query(F.data.startswith("adm:cat:mv:"))
async def cb_cat_move(call: CallbackQuery, db: Database) -> None:
    _, _, _, direction, cid = call.data.split(":")
    await db.move_category(int(cid), int(direction))
    await _cat_view(call.message, db, int(cid))
    await call.answer("جابه جا شد")


@router.callback_query(F.data.startswith("adm:cat:del:yes:"))
async def cb_cat_delete(call: CallbackQuery, db: Database) -> None:
    cid = int(call.data.split(":")[4])
    await db.delete_category(cid)
    await call.answer("حذف شد")
    await call.message.answer(texts.ADMIN_CAT_DELETED)
    await _cats_home(call.message, db)


@router.callback_query(F.data.startswith("adm:cat:del:"))
async def cb_cat_delete_ask(call: CallbackQuery, db: Database) -> None:
    cid = int(call.data.split(":")[3])
    cat = await db.get_category(cid)
    if not cat:
        return await call.answer()
    await edit_or_send(
        call.message,
        texts.ADMIN_CAT_DEL_ASK.format(
            title=cat["title"], plans=await db.category_plan_count(cid)
        ),
        keyboards.admin_cat_del_kb(cid),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:cat:plans:"))
async def cb_cat_plans(call: CallbackQuery, db: Database) -> None:
    await _cat_plans(call, db, int(call.data.split(":")[3]))


async def _cat_plans(call: CallbackQuery, db: Database, cid: int) -> None:
    plans = [
        dict(r)
        for r in await db.fetchall(
            "SELECT * FROM plans WHERE category_id = ? ORDER BY data_gb", (cid,)
        )
    ]
    cat = await db.get_category(cid)
    await edit_or_send(
        call.message,
        f"{esc(cat['emoji'])} <b>{esc(cat['title'])}</b>\n\n{len(plans)} پلن",
        keyboards.admin_cat_plans_kb(cid, plans),
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^adm:cat:\d+$"))
async def cb_cat_view(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await _cat_view(call.message, db, int(call.data.split(":")[2]))
    await call.answer()


# ==================== مدیریت پلن ====================
async def _plan_view(message: Message, db: Database, pid: int) -> None:
    plan = await db.get_plan(pid)
    if not plan:
        return await _cats_home(message, db)
    cat = await db.get_category(plan["category_id"]) if plan["category_id"] else None
    per_gb = int(plan["price"] / plan["data_gb"]) if plan["data_gb"] else 0
    await edit_or_send(
        message,
        texts.ADMIN_PLAN.format(
            fire="🔥 " if plan.get("badge") else "",
            title=plan["title"],
            category=f"{cat['emoji']} {cat['title']}" if cat else "بدون دسته ⚠️",
            data=plan["data_gb"],
            days=plan["duration_days"],
            price=f"{plan['price']:,}",
            per_gb=f"{per_gb:,}",
            status="فعال ✅" if plan["is_active"] else "غیرفعال 🔕",
        ),
        keyboards.admin_plan_kb(pid, bool(plan["is_active"]), bool(plan.get("badge"))),
    )


@router.callback_query(F.data.startswith("adm:pln:new:"))
async def cb_plan_new(call: CallbackQuery, state: FSMContext) -> None:
    cid = int(call.data.split(":")[3])
    await state.set_state(Admin.waiting_plan_new)
    await state.update_data(new_plan_cat=cid)
    await edit_or_send(call.message, texts.ADMIN_PLAN_NEW, keyboards.back_admin_kb())
    await call.answer()


@router.message(Admin.waiting_plan_new)
async def msg_plan_new(message: Message, db: Database, state: FSMContext) -> None:
    data = await state.get_data()
    cid = data.get("new_plan_cat")
    parts = (message.text or "").strip().replace(",", "").replace("،", "").split()
    if len(parts) < 4:
        return await message.answer(texts.ADMIN_PLAN_BAD_FORMAT)
    *title_parts, gb, days, price = parts
    title = " ".join(title_parts)
    if not (gb.isdigit() and days.isdigit() and price.isdigit()) or not title:
        return await message.answer(texts.ADMIN_PLAN_BAD_FORMAT)
    pid = await db.insert(
        """INSERT INTO plans(title, data_gb, duration_days, price, is_active, category_id)
           VALUES(?, ?, ?, ?, 1, ?)""",
        (title, int(gb), int(days), int(price), cid),
    )
    await state.clear()
    await message.answer(texts.ADMIN_PLAN_CREATED.format(title=esc(title)))
    await _plan_view(message, db, pid)


@router.callback_query(F.data.startswith("adm:pln:f:"))
async def cb_plan_field(call: CallbackQuery, state: FSMContext) -> None:
    _, _, _, field, pid = call.data.split(":")
    if field not in texts.ADMIN_PLAN_ASK:
        return await call.answer()
    await state.set_state(Admin.waiting_plan_field)
    await state.update_data(plan_id=int(pid), plan_field=field)
    await edit_or_send(
        call.message, texts.ADMIN_PLAN_ASK[field], keyboards.back_admin_kb()
    )
    await call.answer()


@router.message(Admin.waiting_plan_field)
async def msg_plan_field(message: Message, db: Database, state: FSMContext) -> None:
    data = await state.get_data()
    pid, field = data.get("plan_id"), data.get("plan_field")
    value = (message.text or "").strip().replace(",", "").replace("،", "")
    await ui.consume(message)
    if not pid or not field or not value:
        await state.clear()
        return await message.answer("یه اشتباهی پیش اومد. دوباره شروع کن.")
    if field != "title":
        if not value.isdigit() or int(value) <= 0:
            return await message.answer("لطفا یه عدد مثبت بفرست.")
        value = int(value)
    await db.update_plan(pid, **{field: value})
    await state.clear()
    await message.answer(texts.ADMIN_SAVED_SHORT)
    await _plan_view(message, db, pid)


@router.callback_query(F.data.startswith("adm:pln:tg:"))
async def cb_plan_toggle(call: CallbackQuery, db: Database) -> None:
    pid = int(call.data.split(":")[3])
    plan = await db.get_plan(pid)
    if plan:
        await db.update_plan(pid, is_active=0 if plan["is_active"] else 1)
    await _plan_view(call.message, db, pid)
    await call.answer("تغییر کرد")


@router.callback_query(F.data.startswith("adm:pln:badge:"))
async def cb_plan_badge(call: CallbackQuery, db: Database) -> None:
    """برچسب پرفروش ترین. در هر دسته فقط یک پلن می تواند برچسب داشته باشد."""
    pid = int(call.data.split(":")[3])
    plan = await db.get_plan(pid)
    if not plan:
        return await call.answer()
    if plan.get("badge"):
        await db.update_plan(pid, badge=None)
    else:
        if plan["category_id"]:
            await db.execute(
                "UPDATE plans SET badge = NULL WHERE category_id = ?",
                (plan["category_id"],),
            )
        await db.update_plan(pid, badge="best")
    await _plan_view(call.message, db, pid)
    await call.answer("تغییر کرد")


@router.callback_query(F.data.startswith("adm:pln:cat:set:"))
async def cb_plan_cat_set(call: CallbackQuery, db: Database) -> None:
    _, _, _, _, pid, cid = call.data.split(":")
    await db.update_plan(int(pid), category_id=int(cid))
    await _plan_view(call.message, db, int(pid))
    await call.answer("دسته عوض شد")


@router.callback_query(F.data.startswith("adm:pln:cat:"))
async def cb_plan_cat(call: CallbackQuery, db: Database) -> None:
    pid = int(call.data.split(":")[3])
    cats = await db.categories()
    await edit_or_send(
        call.message, "دسته جدید رو انتخاب کن:", keyboards.admin_plan_move_kb(pid, cats)
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:pln:back:"))
async def cb_plan_back(call: CallbackQuery, db: Database) -> None:
    pid = int(call.data.split(":")[3])
    plan = await db.get_plan(pid)
    if plan and plan["category_id"]:
        # قبلا call.data دستکاری می شد؛ آپدیت تلگرام یک مدل است و
        # تغییر دادنش شکننده است. حالا مستقیم تابع مشترک صدا زده می شود.
        return await _cat_plans(call, db, int(plan["category_id"]))
    await _cats_home(call.message, db)
    await call.answer()


@router.callback_query(F.data.regexp(r"^adm:pln:\d+$"))
async def cb_plan_view(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await _plan_view(call.message, db, int(call.data.split(":")[2]))
    await call.answer()



# ==================== مدیریت قوانین ====================
async def _rules_home(message: Message, db: Database) -> None:
    enabled = await db.get_setting("rules_enabled", "1") == "1"
    rules = await db.get_setting("rules_text", "")
    row = await db.fetchone(
        "SELECT COUNT(*) AS total,"
        " SUM(CASE WHEN rules_accepted_at IS NOT NULL THEN 1 ELSE 0 END) AS ok"
        " FROM users"
    )
    preview = (rules[:300] + "...") if len(rules) > 300 else (rules or "-")
    await edit_or_send(
        message,
        texts.ADMIN_RULES_HOME.format(
            status="فعال ✅" if enabled else "غیرفعال 🔕",
            accepted=row["ok"] or 0,
            total=row["total"] or 0,
            preview=preview,
        ),
        keyboards.admin_rules_kb(enabled),
    )


# ---------- خدمات هوش مصنوعی ----------
async def _ai_home(message: Message, db: Database) -> None:
    from app import pricing

    from app.services import ai_shop

    cfg = await pricing.load(db)
    key = await ai_shop.api_key(db)
    stats = await db.ai_stats()

    # موجودی نزد سرویس دهنده را همین جا نشان می دهیم، نه پشت یک دکمه.
    # اگر صفر باشد هیچ خریدی موفق نمی شود، پس این مهم ترین عدد این
    # صفحه است و باید اول دیده شود.
    wallet = "—"
    if key:
        from app.handlers.ai import _client

        wz = await _client(db)
        try:
            bal = await wz.balance()
            if bal is not None:
                wallet = (bal["text"] or f"{bal['balance']:g} {bal['currency']}") + (" ⚠️ خالی" if bal["balance"] <= 0 else "")
            else:
                wallet = "خوانده نشد"
        except Exception:  # noqa: BLE001
            wallet = "خوانده نشد"
        finally:
            await wz.close()
    lines = []
    for field, (title, default, _d) in pricing.FIELDS.items():
        val = cfg.get(field, 0)
        shown = f"{int(val):,}" if val >= 1000 else f"{val:g}"
        lines.append(f"├ {title}: \u2068{shown}\u2069")
    await edit_or_send(
        message,
        texts.ADMIN_AI.format(
            key=("از .env ✅" if config.canboso_api_key else "تنظیم شده ✅") if key else "تنظیم نشده ❌",
            wallet=wallet,
            fields="\n".join(lines),
            delivered=stats.get("delivered") or 0,
            unknown=stats.get("unknown") or 0,
            revenue=f"{stats.get('revenue') or 0:,}",
        ),
        keyboards.admin_ai_kb(bool(key)),
    )


@router.callback_query(F.data == "adm:ai")
async def cb_ai_home(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await _ai_home(call.message, db)
    await call.answer()


@router.callback_query(F.data == "adm:ai:key")
async def cb_ai_key(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.waiting_ai_field)
    await state.update_data(ai_field="ai_api_key")
    await edit_or_send(call.message, texts.ADMIN_AI_KEY_ASK, None)
    await call.answer()


@router.callback_query(F.data.startswith("adm:ai:f:"))
async def cb_ai_field(call: CallbackQuery, state: FSMContext) -> None:
    from app import pricing

    field = call.data.split(":")[3]
    if field not in pricing.FIELDS:
        return await call.answer("این تنظیم پیدا نشد.", show_alert=True)
    title, default, desc = pricing.FIELDS[field]
    await state.set_state(Admin.waiting_ai_field)
    await state.update_data(ai_field=field)
    await edit_or_send(
        call.message,
        texts.ADMIN_AI_FIELD_ASK.format(title=title, desc=desc, default=default),
        None,
    )
    await call.answer()


@router.message(Admin.waiting_ai_field, F.text)
async def msg_ai_field(message: Message, db: Database, state: FSMContext) -> None:
    from app import pricing

    data = await state.get_data()
    field = data.get("ai_field")
    await state.clear()
    raw = message.text.strip()

    if field == "ai_api_key":
        await db.set_setting("ai_api_key", raw)
        # کلید می تواند پول خرج کند: پیام حاوی آن پاک می شود
        try:
            await message.delete()
        except Exception:  # noqa: BLE001
            pass
        await message.answer(texts.ADMIN_AI_KEY_SAVED)
        return await _ai_home(message, db)

    try:
        value = float(raw.replace(",", "").replace("،", ""))
        if value < 0:
            raise ValueError
    except ValueError:
        return await message.answer("یک عدد معتبر بفرست.")
    await db.set_setting(field, str(int(value) if value.is_integer() else value))
    await message.answer(texts.ADMIN_AI_SAVED)
    await _ai_home(message, db)


@router.callback_query(F.data == "adm:ai:preview")
async def cb_ai_preview(call: CallbackQuery, db: Database) -> None:
    """قیمت همه محصولات canboso با تنظیمات فعلی: قیمت API ← قیمت کاربر."""
    from app import pricing
    from app.canboso import CanbosoError
    from app.services import ai_shop

    try:
        cat = await ai_shop.catalog(db, force=True)
    except CanbosoError as exc:
        return await call.answer(f"خواندن محصولات نشد: {exc}", show_alert=True)
    if not cat["items"]:
        return await call.answer("محصولی نیامد؛ نرخ ارز کیف پول (دلار یا دونگ) را تنظیم کرده ای؟", show_alert=True)
    cfg = await pricing.load(db)
    rows = []
    for x in cat["items"][:25]:
        b = pricing.compute(x["cost"], cfg, x["currency"])
        stock = "∞" if x["stock"] is None else x["stock"]
        rows.append(f"• <b>{esc(x['name'])}</b> ({stock})\n   {x['cost']:g} {x['currency']} → {b.final:,} تومان"
                    + (f" · سود {b.net_profit:,}" if b.net_profit else ""))
    first = pricing.compute(cat["items"][0]["cost"], cfg, cat["items"][0]["currency"])
    await call.message.answer("🧮 <b>قیمت محصولات برای کاربر</b>\n\n" + "\n".join(rows) + "\n\n" + pricing.explain(first))
    await call.answer()


@router.callback_query(F.data == "adm:ai:balance")
async def cb_ai_balance(call: CallbackQuery, db: Database) -> None:
    from app.handlers.ai import _client

    wz = await _client(db)
    bal = await wz.balance()
    await wz.close()
    await call.answer(
        f"موجودی شما نزد canboso: {bal['text'] or bal['balance']}" if bal is not None
        else "موجودی خوانده نشد.",
        show_alert=True,
    )


@router.callback_query(F.data == "adm:ai:restock")
async def cb_ai_restock(call: CallbackQuery, db: Database) -> None:
    """اعلام موجود شدن به همه کسانی که ثبت نام کرده بودند.

    این دستی است، نه خودکار: بعد از این همه لاگ، اعتماد به «موجودی
    الان مثبت است» فقط با تایید خود ادمین معنا دارد، نه با یک بررسی
    خودکار که ممکن است لحظه‌ای اشتباه کند.
    """
    people = await db.ai_waitlist_all()
    if not people:
        return await call.answer("فهرست انتظار خالیه.", show_alert=True)

    sent = 0
    for row in people:
        try:
            with i18n.using(i18n.lang_of(row)):
                await call.bot.send_message(int(row["telegram_id"]), texts.AI_RESTOCKED)
            sent += 1
        except Exception:  # noqa: BLE001
            pass
    await db.ai_waitlist_clear()
    await call.answer(f"به {sent} نفر خبر داده شد ✅", show_alert=True)


@router.callback_query(F.data == "adm:ai:unknown")
async def cb_ai_unknown(call: CallbackQuery, db: Database) -> None:
    """سفارش هایی که وضعیتشان مبهم مانده و دست ادمین را می خواهند."""
    rows = await db.ai_orders_by_status("unknown") + [
        o for o in await db.ai_orders_by_status("pending") if o.get("idem_key")
    ]
    if not rows:
        return await call.answer("سفارش مبهمی نیست ✅", show_alert=True)
    body = "\n\n".join(
        texts.ADMIN_AI_UNKNOWN_ROW.format(
            code=o["code"],
            user=o["telegram_id"],
            price=f"{o['price']:,}",
            when=fmt_dt(o["created_at"]),
            error=esc((o.get("error") or "-")[:60]),
        )
        for o in rows
    )
    await edit_or_send(
        call.message,
        texts.ADMIN_AI_UNKNOWN_LIST.format(count=len(rows), rows=body),
        keyboards.admin_ai_unknown_kb(rows),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:ai:rs:"))
async def cb_ai_resolve(call: CallbackQuery, db: Database) -> None:
    """سفارش مبهم را با همان Idempotency-Key از canboso دوباره می پرسد.

    اگر اولی انجام شده بود همان پاسخ برمی گردد و تحویل می شود؛ اگر نه،
    همین حالا انجام می شود (پول کاربر از قبل کم شده) یا اگر قطعا ممکن
    نیست، پولش برمی گردد. در هر حال خریدار خبردار می شود.
    """
    from app.handlers.ai import notify_buyer
    from app.services import ai_shop

    order = await db.get_ai_order(int(call.data.split(":")[3]))
    if not order:
        return await call.answer("سفارش پیدا نشد.", show_alert=True)
    await call.answer("در حال پرسیدن از canboso…")
    r = await ai_shop.resolve(db, call.bot, order)
    await notify_buyer(call.bot, db, r)
    label = {
        ai_shop.DELIVERED: "✅ تحویل شد و برای کاربر فرستاده شد",
        ai_shop.PROCESSING: "⏳ پذیرفته شد؛ در انتظار فروشنده",
        ai_shop.FAILED: "↩️ انجام نشد؛ پول کاربر برگشت",
        ai_shop.NO_FUNDS: "↩️ موجودی canboso کم است؛ پول کاربر برگشت",
        ai_shop.UNKNOWN: "🔎 هنوز مبهم است؛ کمی بعد دوباره امتحان کن",
    }.get(r["status"], r["status"])
    await call.message.answer(f"سفارش <code>{order['code']}</code>: {label}")
    await cb_ai_unknown(call, db)


# ---------- بخش های ربات ----------
@router.callback_query(F.data == "adm:feat")
async def cb_features(call: CallbackQuery) -> None:
    items = features.summary()
    on = sum(1 for _, _, v in items if v)
    await edit_or_send(
        call.message,
        texts.ADMIN_FEATURES.format(on=on, off=len(items) - on),
        keyboards.admin_features_kb(items),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:feat:"))
async def cb_feature_toggle(call: CallbackQuery, db: Database) -> None:
    key = call.data.split(":")[2]
    if key not in features.FEATURES:
        return await call.answer("این بخش پیدا نشد.", show_alert=True)
    new = await features.toggle(db, key)
    await call.answer("روشن شد ✅" if new else "خاموش شد 🔴")
    await cb_features(call)


# ---------- پیام برگشت ----------
async def _winback_home(message: Message, db: Database) -> None:
    custom = await db.get_setting("winback_text", "")
    await edit_or_send(
        message,
        texts.ADMIN_WINBACK_HOME.format(
            state="متن دلخواه" if custom else "متن پیش فرض",
            current=esc(custom) if custom else esc(
                texts.winback(name="کاربر", code="COMEBACK")
            ),
        ),
        keyboards.admin_winback_kb(bool(custom)),
    )


@router.callback_query(F.data == "adm:wb")
async def cb_winback_home(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await _winback_home(call.message, db)
    await call.answer()


@router.callback_query(F.data == "adm:wb:edit")
async def cb_winback_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.waiting_winback)
    await edit_or_send(call.message, texts.ADMIN_WINBACK_EDIT, None)
    await call.answer()


@router.callback_query(F.data == "adm:wb:preview")
async def cb_winback_preview(call: CallbackQuery, db: Database) -> None:
    """پیام را دقیقا همان طور که کاربر می بیند نشان می دهد."""
    custom = await db.get_setting("winback_text", "")
    name = esc((call.from_user.first_name or "کاربر").strip())
    await call.message.answer(
        texts.winback(custom, name=name, code="COMEBACK"),
        reply_markup=keyboards.winback_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "adm:wb:reset")
async def cb_winback_reset(call: CallbackQuery, db: Database) -> None:
    await db.set_setting("winback_text", "")
    await call.answer(texts.ADMIN_WINBACK_RESET, show_alert=True)
    await _winback_home(call.message, db)


@router.message(Admin.waiting_winback)
async def msg_winback_text(message: Message, db: Database, state: FSMContext) -> None:
    text = (message.html_text or message.text or "").strip()
    if not text:
        return await message.answer("متن خالیه. دوباره بفرست.")
    await state.clear()
    if text in ("پیش فرض", "پیشفرض", "default"):
        await db.set_setting("winback_text", "")
        await message.answer(texts.ADMIN_WINBACK_RESET)
    else:
        await db.set_setting("winback_text", text)
        await message.answer(texts.ADMIN_WINBACK_SAVED)
    await _winback_home(message, db)


@router.callback_query(F.data == "adm:rules")
async def cb_rules_home(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await _rules_home(call.message, db)
    await call.answer()


@router.callback_query(F.data == "adm:rules:toggle")
async def cb_rules_toggle(call: CallbackQuery, db: Database) -> None:
    enabled = await db.get_setting("rules_enabled", "1") == "1"
    await db.set_setting("rules_enabled", "0" if enabled else "1")
    await _rules_home(call.message, db)
    await call.answer("غیرفعال شد" if enabled else "فعال شد")


@router.callback_query(F.data == "adm:rules:preview")
async def cb_rules_preview(call: CallbackQuery, db: Database) -> None:
    """نمایش قوانین همان طور که کاربر می بیند."""
    rules = await db.get_setting("rules_text", "")
    await call.message.answer(
        texts.RULES_INTRO.format(name="کاربر") + "\n\n" + rules,
        reply_markup=keyboards.rules_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "adm:rules:edit")
async def cb_rules_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.waiting_rules)
    await edit_or_send(
        call.message, texts.ADMIN_RULES_EDIT, keyboards.admin_rules_kb(True)
    )
    await call.answer()


@router.message(Admin.waiting_rules)
async def msg_rules_text(message: Message, db: Database, state: FSMContext) -> None:
    text = (message.html_text or message.text or "").strip()
    if not text:
        return await message.answer("متن خالیه. دوباره بفرست.")
    await db.set_setting("rules_text", text)
    await state.clear()
    await message.answer(texts.ADMIN_RULES_SAVED)
    await _rules_home(message, db)


@router.callback_query(F.data == "adm:rules:reset")
async def cb_rules_reset_ask(call: CallbackQuery, db: Database) -> None:
    row = await db.fetchone(
        "SELECT COUNT(*) AS n FROM users WHERE rules_accepted_at IS NOT NULL"
    )
    await edit_or_send(
        call.message,
        texts.ADMIN_RULES_RESET_ASK.format(count=row["n"] or 0),
        keyboards.admin_rules_reset_confirm_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "adm:rules:reset:yes")
async def cb_rules_reset_do(call: CallbackQuery, db: Database) -> None:
    n = await db.reset_all_rules()
    await call.answer("انجام شد")
    await call.message.answer(texts.ADMIN_RULES_RESET_DONE.format(count=n))
    await _rules_home(call.message, db)


# ==================== مدیریت ایموجی ====================
@router.callback_query(F.data == "adm:emo")
async def cb_emoji_home(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    custom = sum(1 for k in emo.CATALOG if emo.custom_id(k))
    await edit_or_send(
        call.message,
        texts.ADMIN_EMOJI_HOME.format(count=custom, total=len(emo.CATALOG)),
        keyboards.emoji_categories_kb(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:emo:c:"))
async def cb_emoji_category(call: CallbackQuery) -> None:
    category = call.data.split(":", 3)[3]
    await _emoji_page(call, category, 0)


@router.callback_query(F.data.startswith("adm:emo:pg:"))
async def cb_emoji_page(call: CallbackQuery) -> None:
    """صفحه بعد و قبل فهرست یک دسته."""
    _, _, _, page, category = call.data.split(":", 4)
    await _emoji_page(call, category, int(page))


async def _emoji_page(call: CallbackQuery, category: str, page: int) -> None:
    items = emo.titles_by_category().get(category, [])
    pages = max(1, (len(items) + keyboards.EMOJI_PAGE - 1) // keyboards.EMOJI_PAGE)
    done = sum(1 for key, _e, _t in items if emo.custom_id(key))
    await edit_or_send(
        call.message,
        texts.ADMIN_EMOJI_LIST.format(
            category=category, done=done, total=len(items),
            page=min(page, pages - 1) + 1, pages=pages,
        ),
        keyboards.emoji_list_kb(category, page),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:emo:e:"))
async def cb_emoji_edit(call: CallbackQuery, state: FSMContext) -> None:
    """شروع ویرایش یک ایموجی: منتظر دریافت ایموجی پریمیوم."""
    key = call.data.split(":", 3)[3]
    if key not in emo.CATALOG:
        return await call.answer("این ایموجی وجود نداره.", show_alert=True)
    _, title, _cat = emo.CATALOG[key]
    await state.set_state(Admin.waiting_emoji)
    await state.update_data(emoji_key=key)
    await edit_or_send(
        call.message,
        texts.ADMIN_EMOJI_EDIT.format(title=title, current=emo.text(key)),
        keyboards.emoji_edit_kb(key, bool(emo.custom_id(key))),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:emo:r:"))
async def cb_emoji_reset(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    """بازگشت یک ایموجی به حالت پیش فرض."""
    key = call.data.split(":", 3)[3]
    if key not in emo.CATALOG:
        return await call.answer("این ایموجی وجود نداره.", show_alert=True)
    await emo.reset_emoji(db, key)
    await state.clear()
    _, title, cat = emo.CATALOG[key]
    await edit_or_send(
        call.message,
        texts.ADMIN_EMOJI_RESET.format(title=title),
        keyboards.emoji_list_kb(cat),
    )
    await call.answer("برگشت به پیش فرض")


@router.message(Admin.waiting_emoji)
async def msg_emoji_received(message: Message, db: Database, state: FSMContext) -> None:
    """دریافت ایموجی پریمیوم و ثبت آن.

    آیدی ایموجی از entity های پیام استخراج می شود. ایموجی معمولی
    entity ندارد پس رد می شود.
    """
    data = await state.get_data()
    key = data.get("emoji_key")
    if not key or key not in emo.CATALOG:
        await state.clear()
        return await message.answer("یه اشتباهی پیش اومد. دوباره از تنظیمات شروع کن.")

    entities = message.entities or []
    emoji_id = next(
        (e.custom_emoji_id for e in entities if e.type == "custom_emoji"), None
    )
    if not emoji_id:
        return await message.answer(texts.ADMIN_EMOJI_NOT_PREMIUM)

    await emo.set_emoji(db, key, emoji_id)
    await state.clear()
    _, title, cat = emo.CATALOG[key]
    await message.answer(
        texts.ADMIN_EMOJI_SAVED.format(title=title, sample=emo.text(key)),
        reply_markup=keyboards.emoji_list_kb(cat),
    )


@router.callback_query(F.data == "adm:set")
async def cb_admin_settings(call: CallbackQuery, db: Database) -> None:
    await call.message.edit_text(
        texts.ADMIN_SETTINGS.format(
            card_number=await db.get_setting("card_number") or "-",
            card_holder=await db.get_setting("card_holder") or "-",
            bank_name=await db.get_setting("bank_name") or "-",
            min_charge=f"{int(await db.get_setting('min_charge', '50000')):,}",
            **await _crypto_settings_lines(db),
        ),
        reply_markup=keyboards.admin_setting_kb(),
    )
    await call.answer()


async def _crypto_settings_lines(db: Database) -> dict:
    from app.services import crypto

    if not crypto.enabled():
        state = "خاموش · TON_RECEIVE_ADDRESS در .env خالی یا نامعتبر است"
    else:
        net = "🧪 testnet (فقط ادمین ها می بینند)" if crypto.testnet() else "mainnet"
        usdt = "USDT روشن" if crypto.usdt_master() else "USDT خاموش (TON_USDT_MASTER)"
        state = f"روشن · {net} · {usdt}\n<code>{crypto.pay_address()}</code>"
    manual_ton = await db.get_setting("crypto_ton_rate", "0") or "0"
    r = await crypto.rates(db)
    ton = f"{r['TON']:,}" if r["TON"] else "نامعلوم"
    rates = (
        f"تتر: {int(await db.get_setting('crypto_usdt_rate', '0') or 0):,} · "
        f"TON: {ton}{' (خودکار)' if manual_ton in ('', '0') else ''} · "
        f"کارمزد: {await crypto.fee_percent(db):g}٪"
    )
    stars_rate = int(await db.get_setting("stars_rate", "0") or 0)
    stars_line = f"هر ستاره = {stars_rate:,} تومان" if stars_rate else "خاموش (نرخ ستاره تعیین نشده)"
    return {"crypto_state": state, "crypto_rates": rates, "stars_line": stars_line}


@router.callback_query(F.data.startswith("adm:set:"))
async def cb_admin_set_field(call: CallbackQuery, state: FSMContext) -> None:
    field = call.data.split(":")[2]
    await state.set_state(Admin.waiting_setting)
    await state.update_data(setting=field)
    await call.message.answer(texts.ADMIN_SET_PROMPT.get(field, "مقدار جدید را بفرست:"))
    await call.answer()


@router.message(Admin.waiting_setting, F.text)
async def txt_admin_setting(message: Message, db: Database, state: FSMContext) -> None:
    """ذخیره یک تنظیم.

    توجه: state فقط بعد از ذخیره موفق پاک می شود. قبلا اول پاک می شد و
    اگر مقدار نامعتبر بود، «دوباره بفرست» عملا کار نمی کرد.
    """
    data = await state.get_data()
    field = data.get("setting")
    if not field:
        await state.clear()
        return await message.answer("یه اشتباهی پیش اومد. دوباره از تنظیمات شروع کن.")
    value = (message.text or "").strip()
    if field == "price" and data.get("plan_id"):
        if not value.isdigit():
            return await message.answer("لطفا یه عدد بفرست.")
        await db.update_plan(int(data["plan_id"]), price=int(value))
    elif field == "data_gb" and data.get("plan_id"):
        if not value.isdigit() or int(value) <= 0:
            return await message.answer("لطفا حجم را به گیگ و به صورت عدد بفرست.")
        await db.update_plan(int(data["plan_id"]), data_gb=int(value))
    elif field in admin_ops.SETTING_FIELDS:
        ok, msg = await admin_ops.save_setting(db, field, value, message.from_user.id)
        if not ok:
            return await message.answer(msg)
    else:
        await state.clear()
        return await message.answer("این فیلد قابل ویرایش نیست.")
    await state.clear()
    await message.answer(texts.ADMIN_SAVED)


# ---------- مدیریت افکت پیام ----------
_EFFECT_TITLES = {
    "trial": "تست رایگان",
    "charge": "شارژ کیف پول",
    "purchase": "خرید و تمدید سرویس",
}


@router.callback_query(F.data == "adm:fx")
async def cb_effects_home(call: CallbackQuery) -> None:
    sources = {k: effects.source(k) == "دیتابیس" for k in _EFFECT_TITLES}
    await edit_or_send(
        call.message, texts.ADMIN_EFFECTS_HOME, keyboards.admin_effects_kb(sources)
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:fx:"))
async def cb_effect_view(call: CallbackQuery, state: FSMContext) -> None:
    kind = call.data.split(":")[2]
    if kind not in _EFFECT_TITLES:
        return await call.answer()
    await state.clear()
    current = effects.current_id(kind)
    await edit_or_send(
        call.message,
        texts.ADMIN_EFFECT_EDIT.format(
            title=_EFFECT_TITLES[kind],
            source=effects.source(kind),
            current=current or "(تنظیم نشده)",
        ),
        keyboards.admin_effect_edit_kb(kind, effects.source(kind) == "دیتابیس"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:fxset:"))
async def cb_effect_capture_ask(call: CallbackQuery, state: FSMContext) -> None:
    kind = call.data.split(":")[2]
    if kind not in _EFFECT_TITLES:
        return await call.answer()
    await state.set_state(Admin.waiting_effect_capture)
    await state.update_data(fx_kind=kind)
    await edit_or_send(
        call.message,
        texts.ADMIN_EFFECT_ASK.format(title=_EFFECT_TITLES[kind]),
        keyboards.admin_effect_capture_kb(kind),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:fxclear:"))
async def cb_effect_clear(call: CallbackQuery, db: Database) -> None:
    kind = call.data.split(":")[2]
    if kind not in _EFFECT_TITLES:
        return await call.answer()
    await effects.clear_override(db, kind)
    current = effects.current_id(kind)
    await edit_or_send(
        call.message,
        texts.ADMIN_EFFECT_EDIT.format(
            title=_EFFECT_TITLES[kind],
            source=effects.source(kind),
            current=current or "(تنظیم نشده)",
        ),
        keyboards.admin_effect_edit_kb(kind, effects.source(kind) == "دیتابیس"),
    )
    await call.answer(texts.ADMIN_EFFECT_CLEARED)


@router.message(Admin.waiting_effect_capture)
async def msg_effect_capture(message: Message, db: Database, state: FSMContext) -> None:
    """استخراج افکت از پیامی که ادمین فرستاده و ذخیره اش."""
    data = await state.get_data()
    kind = data.get("fx_kind")
    if kind not in _EFFECT_TITLES:
        await state.clear()
        return await message.answer("یه اشتباهی پیش اومد. دوباره از تنظیمات شروع کن.")

    eid = getattr(message, "effect_id", None)
    if not eid:
        return await message.answer(texts.ADMIN_EFFECT_NO_ID)

    await effects.set_override(db, kind, eid)
    await state.clear()
    await message.answer(
        texts.ADMIN_EFFECT_SAVED.format(title=_EFFECT_TITLES[kind]),
        reply_markup=keyboards.admin_effect_edit_kb(kind, True),
    )


# ---------- پیام همگانی ----------
# طراحی: به جای گرفتن فقط متن، *هر* پیامی که ادمین بفرستد (متن، عکس،
# فوروارد از جای دیگر) به عنوان منبع ذخیره می شود و با copy_message به
# همه کاربران کپی می شود. این یک تیر و چند نشان است:
#   - عکس/ویدیو/فایل هم پشتیبانی می شود، نه فقط متن
#   - ایموجی پریمیوم و فرمت متن (بولد و ...) دست نخورده کپی می شود،
#     چون copy_message خود entity های تلگرام را عینا منتقل می کند
#   - اگر پیام منبع خودش یک فوروارد باشد، می شود انتخاب کرد که با
#     برچسب «فوروارد شده از ...» برود یا بدون آن


async def _render_broadcast_builder(
    message: Message, state: FSMContext, fresh: bool = False
) -> None:
    """نمایش صفحه سازنده پیام همگانی.

    fresh=True یعنی حتما پیام تازه بفرست و به پیام فعلی دست نزن - برای
    وقتی که پیام فعلی همان منبع ارسال است و نباید حذف شود.
    """
    data = await state.get_data()
    btn_type = data.get("bc_btn_type")
    label = data.get("bc_btn_label", "")
    color = keyboards.BROADCAST_STYLES.get(data.get("bc_btn_style") or "none", "بدون رنگ")
    if btn_type == "url":
        button = f"🔗 {label} · {color}"
    elif btn_type == "plan":
        button = f"🛒 {label} · {color}"
    elif btn_type == "page":
        button = f"📄 {label} · {color}"
    else:
        button = "بدون دکمه"
    pin = "روشن ✅" if data.get("bc_pin") else "خاموش"
    source_line = ""
    if data.get("bc_is_forward"):
        mode = "با نمایش منبع" if data.get("bc_show_source") else "بدون نمایش منبع"
        source_line = f"📤 حالت فوروارد: {mode}\n"

    body = texts.ADMIN_BROADCAST_BUILDER.format(
        preview=data.get("bc_preview", "(بدون پیش نمایش متنی)"),
        button=button,
        pin=pin,
        source_line=source_line,
    )
    markup = keyboards.admin_broadcast_builder_kb(
        has_button=bool(btn_type), has_forward_src=bool(data.get("bc_is_forward"))
    )
    if fresh:
        await message.answer(body, reply_markup=markup)
    else:
        await edit_or_send(message, body, markup)


@router.callback_query(F.data == "adm:bc")
async def cb_broadcast(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.waiting_broadcast)
    await state.update_data(
        bc_chat_id=None,
        bc_message_id=None,
        bc_preview=None,
        bc_is_forward=False,
        bc_show_source=False,
        bc_btn_type=None,
        bc_btn_label=None,
        bc_btn_url=None,
        bc_btn_plan_id=None,
        bc_target=None,   # مقصد پیش فرض: همه کاربرها (نه کانال)
        bc_poll_id=None,
        bc_pin=False,
    )
    await edit_or_send(call.message, texts.ADMIN_BROADCAST_ASK, keyboards.admin_broadcast_ask_kb())
    await call.answer()


@router.callback_query(F.data == "adm:bccancel")
async def cb_broadcast_cancel(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await cb_admin(call, db)


@router.message(Admin.waiting_broadcast)
async def msg_broadcast_source(message: Message, state: FSMContext) -> None:
    """گرفتن پیام منبع همگانی - هر نوع محتوایی."""
    is_forward = getattr(message, "forward_origin", None) is not None or bool(
        getattr(message, "forward_from_chat", None) or getattr(message, "forward_from", None)
    )
    preview = (message.html_text or message.caption or "").strip()
    if not preview:
        preview = "(بدون متن - فقط رسانه)"
    elif len(preview) > 500:
        preview = preview[:500] + "…"

    await state.update_data(
        bc_chat_id=message.chat.id,
        bc_message_id=message.message_id,
        bc_preview=preview,
        bc_is_forward=is_forward,
        bc_show_source=is_forward,
    )
    # مهم: پیام سازنده باید یک پیام *تازه* باشد، نه ویرایش/جایگزینی
    # همین پیامی که ادمین فرستاده. ارسال همگانی با copy_message از روی
    # همین پیام انجام می شود؛ اگر edit_or_send آن را حذف کند (که برای
    # پیام رسانه ای دقیقا همین کار را می کند)، موقع ارسال تلگرام
    # می گوید «message to copy not found» و هیچ چیز فرستاده نمی شود.
    await _render_broadcast_builder(message, state, fresh=True)


@router.callback_query(F.data == "adm:bcback")
async def cb_broadcast_back(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.waiting_broadcast)
    await _render_broadcast_builder(call.message, state)
    await call.answer()


@router.callback_query(F.data == "adm:bcpin")
async def cb_broadcast_pin_toggle(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data(bc_pin=not data.get("bc_pin"))
    await _render_broadcast_builder(call.message, state)
    await call.answer()


@router.callback_query(F.data == "adm:bcsrc")
async def cb_broadcast_src_toggle(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data(bc_show_source=not data.get("bc_show_source"))
    await _render_broadcast_builder(call.message, state)
    await call.answer()


@router.callback_query(F.data == "adm:bcbtnrm")
async def cb_broadcast_btn_remove(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(bc_btn_type=None, bc_btn_label=None, bc_btn_url=None, bc_btn_plan_id=None)
    await _render_broadcast_builder(call.message, state)
    await call.answer()


@router.callback_query(F.data == "adm:bcbtn")
async def cb_broadcast_btn_menu(call: CallbackQuery, state: FSMContext) -> None:
    await edit_or_send(
        call.message, texts.ADMIN_BROADCAST_BTN_MENU, keyboards.admin_broadcast_btn_menu_kb()
    )
    await call.answer()


@router.callback_query(F.data == "adm:bcbtn:url")
async def cb_broadcast_btn_url_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(bc_btn_type="url")
    await state.set_state(Admin.waiting_broadcast_btn_label)
    await edit_or_send(call.message, texts.ADMIN_BROADCAST_BTN_LABEL_ASK, keyboards.admin_broadcast_btn_menu_kb())
    await call.answer()


@router.message(Admin.waiting_broadcast_btn_label, F.text)
async def msg_broadcast_btn_label(message: Message, state: FSMContext) -> None:
    """عنوان دکمه.

    دو مسیر به اینجا می رسد: ساخت دکمه لینک (که بعدش آدرس را می پرسد)،
    و تغییر عنوان دکمه ای که از قبل انتخاب شده (که همان جا تمام می شود).
    پرچم bc_label_only این دو را از هم جدا می کند.
    """
    label = message.text.strip()[:40]
    if not label:
        return await message.answer("یه متن کوتاه بفرست.")
    data = await state.get_data()
    await state.update_data(bc_btn_label=label)

    if data.get("bc_label_only"):
        await state.update_data(bc_label_only=False)
        await state.set_state(Admin.waiting_broadcast)
        return await _render_broadcast_builder(message, state)

    await state.set_state(Admin.waiting_broadcast_btn_url)
    await message.answer(texts.ADMIN_BROADCAST_BTN_URL_ASK, reply_markup=keyboards.admin_broadcast_btn_menu_kb())


@router.message(Admin.waiting_broadcast_btn_url, F.text)
async def msg_broadcast_btn_url(message: Message, state: FSMContext) -> None:
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("t.me/")):
        return await message.answer(texts.ADMIN_BROADCAST_BTN_URL_BAD)
    if url.startswith("t.me/"):
        url = "https://" + url
    await state.update_data(bc_btn_url=url)
    await state.set_state(Admin.waiting_broadcast)
    await _render_broadcast_builder(message, state)


@router.callback_query(F.data == "adm:bcbtn:plan")
async def cb_broadcast_btn_plan_start(call: CallbackQuery, db: Database) -> None:
    plans = await db.active_plans()
    if not plans:
        return await call.answer("پلن فعالی وجود نداره.", show_alert=True)
    await edit_or_send(
        call.message, texts.ADMIN_BROADCAST_PLAN_PICK, keyboards.admin_broadcast_plan_pick_kb(plans)
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:bcplan:"))
async def cb_broadcast_btn_plan_pick(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    plan_id = int(call.data.split(":")[2])
    plan = await db.get_plan(plan_id)
    if not plan:
        return await call.answer("این پلن پیدا نشد.", show_alert=True)
    await state.update_data(
        bc_btn_type="plan", bc_btn_plan_id=plan_id, bc_btn_label=f"🛒 خرید {plan['title']}"
    )
    await state.set_state(Admin.waiting_broadcast)
    await _render_broadcast_builder(call.message, state)
    await call.answer()


@router.callback_query(F.data == "adm:bcbtn:style")
async def cb_broadcast_btn_style_menu(call: CallbackQuery, state: FSMContext) -> None:
    """تغییر رنگ دکمه ای که از قبل انتخاب شده."""
    data = await state.get_data()
    if not data.get("bc_btn_type"):
        return await call.answer("اول یک دکمه انتخاب کن.", show_alert=True)
    await edit_or_send(
        call.message, texts.ADMIN_BROADCAST_STYLE_PICK, keyboards.admin_broadcast_style_kb()
    )
    await call.answer()


@router.callback_query(F.data == "adm:bcbtn:page")
async def cb_broadcast_btn_page_menu(call: CallbackQuery) -> None:
    """فهرست صفحه های ربات برای دکمه پیام همگانی."""
    await edit_or_send(
        call.message,
        texts.ADMIN_BROADCAST_PAGE_PICK,
        keyboards.admin_broadcast_page_pick_kb(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:bcpage:"))
async def cb_broadcast_btn_page_pick(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":")[2]
    dest = keyboards.BROADCAST_DESTS.get(key)
    if not dest:
        return await call.answer("این صفحه پیدا نشد.", show_alert=True)
    callback_data, title = dest
    await state.update_data(
        bc_btn_type="page", bc_btn_cb=callback_data, bc_btn_label=title
    )
    # بعد از انتخاب صفحه، رنگ را می پرسیم
    await edit_or_send(
        call.message, texts.ADMIN_BROADCAST_STYLE_PICK, keyboards.admin_broadcast_style_kb()
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:bcstyle:"))
async def cb_broadcast_btn_style(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":")[2]
    await state.update_data(bc_btn_style=None if key == "none" else key)
    await state.set_state(Admin.waiting_broadcast)
    await _render_broadcast_builder(call.message, state)
    await call.answer()


@router.callback_query(F.data == "adm:bclabel")
async def cb_broadcast_btn_label_edit(call: CallbackQuery, state: FSMContext) -> None:
    """تغییر عنوان دکمه ای که قبلا انتخاب شده."""
    data = await state.get_data()
    if not data.get("bc_btn_type"):
        return await call.answer("اول یک دکمه انتخاب کن.", show_alert=True)
    await state.set_state(Admin.waiting_broadcast_btn_label)
    await state.update_data(bc_label_only=True)
    await edit_or_send(call.message, texts.ADMIN_BROADCAST_LABEL_ASK, None)
    await call.answer()


async def _outgoing_markup(db: Database, data: dict, for_channel: bool = False):  # noqa: ANN201
    """کیبورد نهایی پیامی که بیرون می رود.

    دو نکته مهم که قبلا اشتباه بود:

    ۱. copy_message کیبورد پیام اصلی را کپی *نمی کند*. برای نظرسنجی،
       دکمه ها باید جدا ساخته و پاس داده شوند - وگرنه کاربر فقط متن
       نظرسنجی را می دید بدون هیچ دکمه ای.

    ۲. در کانال، دکمه callback کار درستی نمی کند: با زدنش کاربر همان
       جا در کانال می ماند و محتوا آنجا عوض می شود. برای کانال باید
       لینک عمیق به خود ربات ساخت تا کاربر وارد چت خصوصی شود.
    """
    poll_id = data.get("bc_poll_id")
    if poll_id:
        poll = await db.get_poll(int(poll_id))
        if poll:
            if for_channel:
                return await _deep_link_markup(
                    db, [(f"📊 {poll['question'][:40]}", f"poll_{poll_id}")]
                )
            options = await db.poll_options(int(poll_id))
            return polls.poll_kb(poll, options)

    markup = _broadcast_markup(data)
    if for_channel and data.get("bc_btn_type") in ("page", "plan"):
        # دکمه صفحه/پلن در کانال باید لینک عمیق شود
        label = data.get("bc_btn_label") or "باز کردن"
        if data.get("bc_btn_type") == "page":
            payload = f"page_{_page_payload(data.get('bc_btn_cb', 'menu'))}"
        else:
            payload = f"plan_{data.get('bc_btn_plan_id')}"
        return await _deep_link_markup(
            db, [(label, payload)], style=data.get("bc_btn_style")
        )
    return markup


def _page_payload(callback_data: str) -> str:
    """تبدیل callback_data به کلید امن برای لینک عمیق (بدون : و فاصله)."""
    return callback_data.replace(":", "-")


async def _deep_link_markup(db: Database, items: list, style: str | None = None):  # noqa: ANN001, ANN201
    """دکمه هایی که کاربر را به چت خصوصی ربات می برند.

    لینک عمیق t.me/<bot>?start=<payload> است؛ ربات payload را می خواند
    و همان صفحه را در چت خصوصی باز می کند.
    """
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    from app.keyboards import _add  # noqa: PLC2701

    username = await db.get_setting("bot_username", "")
    if not username:
        return None
    kb = InlineKeyboardBuilder()
    for label, payload in items:
        _add(
            kb,
            label[:64],
            style=style,
            url=f"https://t.me/{username}?start={payload}",
        )
    kb.adjust(1)
    return kb.as_markup()


def _broadcast_markup(data: dict):  # noqa: ANN201
    """دکمه شیشه ای زیر پیام همگانی، بر اساس تنظیمات ادمین."""
    btn_type = data.get("bc_btn_type")
    style = data.get("bc_btn_style")
    label = data.get("bc_btn_label")
    if btn_type == "url" and data.get("bc_btn_url"):
        return keyboards.single_url_button(label or "لینک", data["bc_btn_url"], style)
    if btn_type == "plan" and data.get("bc_btn_plan_id"):
        return keyboards.single_callback_button(
            label or "خرید", f"buy:p:{data['bc_btn_plan_id']}", style
        )
    if btn_type == "page" and data.get("bc_btn_cb"):
        return keyboards.single_callback_button(
            label or "باز کردن", data["bc_btn_cb"], style
        )
    return None


@router.callback_query(F.data == "adm:bcsend")
async def cb_broadcast_send(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    """ثبت کار ارسال همگانی و پیش بردن بخشی از آن همین حالا.

    قبلا این کار یک asyncio.create_task بود. زیر Passenger جواب نمی داد:
    به محض اینکه پاسخ درخواست وبهوک برمی گشت، پروسه خوابانده می شد و
    تسک نصفه می ماند - پیام «در حال ارسال» روی صفحه می ماند و به
    کاربرها چیزی نمی رسید.

    حالا کار در دیتابیس ثبت می شود، بخشی از آن در همین درخواست پیش
    می رود (تا حدی که وقت درخواست اجازه می دهد) و باقی اش در هر اجرای
    کران ادامه پیدا می کند.
    """
    data = await state.get_data()
    await state.clear()
    src_chat, src_msg = data.get("bc_chat_id"), data.get("bc_message_id")
    if not src_chat or not src_msg:
        return await call.answer("پیامی برای ارسال پیدا نشد.", show_alert=True)

    # مقصد کانال: یک پیام است، نه ارسال گروهی - پس مسیرش کاملا جداست
    if data.get("bc_target") == "channel":
        channel = await db.get_setting("channel_id", "") or config.channel_id
        if not channel:
            return await call.answer(
                "اول آیدی کانال را در تنظیمات بگذار.", show_alert=True
            )
        try:
            sent = await call.bot.copy_message(
                chat_id=channel,
                from_chat_id=int(src_chat),
                message_id=int(src_msg),
                reply_markup=await _outgoing_markup(db, data, for_channel=True),
            )
            if data.get("bc_pin"):
                try:
                    await call.bot.pin_chat_message(
                        chat_id=channel, message_id=sent.message_id
                    )
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            log.warning("پست در کانال نشد: %s", exc)
            return await call.answer(f"نشد: {exc}", show_alert=True)
        await call.answer("منتشر شد ✅")
        return await call.message.answer(
            "📣 در کانال منتشر شد.", reply_markup=keyboards.admin_dash_kb()
        )

    if await db.active_broadcast():
        return await call.answer(
            "یک ارسال همگانی هنوز تمام نشده. صبر کن تا تمام شود.", show_alert=True
        )

    # پیام گزارش: اگر پیام فعلی متنی نباشد (مثلا پیش نمایش عکس)،
    # edit_text خطا می دهد. قبلا همین خطا کل هندلر را می ترکاند و کار
    # اصلا ثبت نمی شد - یعنی ارسال بی صدا انجام نمی شد.
    try:
        report = await call.message.edit_text("⏳ در حال آماده سازی...")
    except Exception:  # noqa: BLE001
        report = await call.message.answer("⏳ در حال آماده سازی...")

    try:
        job_id = await db.create_broadcast(
            src_chat_id=int(src_chat),
            src_message_id=int(src_msg),
            show_source=bool(data.get("bc_show_source")),
            pin=bool(data.get("bc_pin")),
            markup_json=broadcast.markup_to_json(await _outgoing_markup(db, data)),
            report_chat_id=report.chat.id,
            report_message_id=report.message_id,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("ثبت کار ارسال همگانی نشد")
        await call.answer()
        return await report.edit_text(f"❌ ثبت ارسال انجام نشد:\n<code>{esc(str(exc))}</code>")

    log.info("کار ارسال همگانی %s ثبت شد", job_id)
    await call.answer("شروع شد")

    # تا ۲۰ ثانیه از همین درخواست را خرج ارسال می کنیم. برای ربات های
    # کوچک یعنی کار همین جا تمام می شود؛ برای بقیه، کران/خودپینگ ادامه
    # می دهد. هر خطایی اینجا برای ادمین گزارش می شود، نه فقط در لاگ -
    # چون شکست بی صدا در این بخش سخت ترین چیز برای عیب یابی است.
    try:
        result = await broadcast.run_chunk(call.bot, db, budget=20.0)
    except Exception as exc:  # noqa: BLE001
        log.exception("اجرای ارسال همگانی شکست خورد")
        return await report.edit_text(
            f"❌ ارسال شروع شد ولی با خطا متوقف شد:\n<code>{esc(str(exc))}</code>\n\n"
            "با /bc می توانی دوباره ادامه اش بدهی."
        )

    if result and not result.get("done"):
        try:
            await report.answer(
                "ℹ️ این تکه تمام شد ولی ارسال هنوز ادامه دارد.\n"
                "بقیه اش خودکار (هر ربع ساعت) ادامه پیدا می کند، "
                "یا با /bc دستی جلو ببر."
            )
        except Exception:  # noqa: BLE001
            pass


# ==================== نظرسنجی ====================
@router.callback_query(F.data == "adm:polls")
async def cb_polls(call: CallbackQuery, db: Database) -> None:
    polls = await db.list_polls()
    body = texts.ADMIN_POLLS_EMPTY if not polls else texts.ADMIN_POLLS.format(
        count=len(polls)
    )
    await edit_or_send(call.message, body, keyboards.admin_polls_kb(polls))
    await call.answer()


@router.callback_query(F.data == "adm:pollnew")
async def cb_poll_new(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.waiting_poll_question)
    await edit_or_send(call.message, texts.ADMIN_POLL_ASK_Q, None)
    await call.answer()


@router.message(Admin.waiting_poll_question, F.text)
async def msg_poll_question(message: Message, state: FSMContext) -> None:
    q = message.text.strip()[:200]
    if not q:
        return await message.answer("یه سوال بفرست.")
    await state.update_data(poll_q=q)
    await state.set_state(Admin.waiting_poll_options)
    await message.answer(texts.ADMIN_POLL_ASK_OPTS)


@router.message(Admin.waiting_poll_options, F.text)
async def msg_poll_options(message: Message, db: Database, state: FSMContext) -> None:
    """گزینه ها، هر کدام در یک خط.

    اگر خط با یک ایموجی کاتالوگ شروع شود (مثل ✅ یا 🔥)، همان مسیر
    ایموجی سفارشی بقیه دکمه ها روی آن هم اعمال می شود.
    """
    opts = [ln.strip()[:60] for ln in message.text.splitlines() if ln.strip()]
    if len(opts) < 2:
        return await message.answer("حداقل دو گزینه لازمه، هر کدوم توی یک خط.")
    if len(opts) > 8:
        return await message.answer("حداکثر هشت گزینه.")

    data = await state.get_data()
    await state.clear()
    poll_id = await db.create_poll(data["poll_q"], opts)
    poll = await db.get_poll(poll_id)
    results = await db.poll_results(poll_id)
    await message.answer(
        polls.admin_report(poll, results, await db.poll_breakdown(poll_id)),
        reply_markup=keyboards.admin_poll_kb(poll_id, True),
    )


@router.callback_query(F.data.startswith("adm:pollv:"))
async def cb_poll_view(call: CallbackQuery, db: Database) -> None:
    poll_id = int(call.data.split(":")[2])
    poll = await db.get_poll(poll_id)
    if not poll:
        return await call.answer("این نظرسنجی پیدا نشد.", show_alert=True)
    await edit_or_send(
        call.message,
        polls.admin_report(
            poll, await db.poll_results(poll_id), await db.poll_breakdown(poll_id)
        ),
        keyboards.admin_poll_kb(poll_id, bool(poll["is_open"])),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:polltog:"))
async def cb_poll_toggle(call: CallbackQuery, db: Database) -> None:
    poll_id = int(call.data.split(":")[2])
    poll = await db.get_poll(poll_id)
    if not poll:
        return await call.answer("پیدا نشد.", show_alert=True)
    await db.set_poll_open(poll_id, not bool(poll["is_open"]))
    await call.answer("بسته شد" if poll["is_open"] else "باز شد")
    await cb_poll_view(call, db)


@router.callback_query(F.data.startswith("adm:pollfmt:"))
async def cb_poll_format(call: CallbackQuery) -> None:
    poll_id = int(call.data.split(":")[2])
    await edit_or_send(
        call.message, texts.ADMIN_POLL_FORMAT, keyboards.admin_poll_format_kb(poll_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:polllay:"))
async def cb_poll_layout(call: CallbackQuery, db: Database) -> None:
    _, _, poll_id, layout = call.data.split(":")
    await db.execute("UPDATE polls SET layout = ? WHERE id = ?", (layout, int(poll_id)))
    await call.answer("چیدمان عوض شد")
    await cb_poll_view(call, db)


@router.callback_query(F.data.startswith("adm:pollcol:"))
async def cb_poll_color(call: CallbackQuery, db: Database) -> None:
    _, _, poll_id, key = call.data.split(":")
    await db.execute(
        "UPDATE polls SET style = ? WHERE id = ?",
        (None if key == "none" else key, int(poll_id)),
    )
    await call.answer("رنگ عوض شد")
    await cb_poll_view(call, db)


@router.callback_query(F.data.startswith("adm:pollbc:"))
async def cb_poll_broadcast(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    """فرستادن نظرسنجی به همه کاربرها.

    نظرسنجی خودش پیام و دکمه دارد، پس مثل پیام همگانی معمولی از یک
    پیام منبع کپی نمی شود؛ یک پیام تازه در چت ادمین ساخته می شود و
    همان کپی می شود.
    """
    poll_id = int(call.data.split(":")[2])
    text, markup = await polls.view(db, poll_id)
    if not text:
        return await call.answer("این نظرسنجی پیدا نشد.", show_alert=True)

    src = await call.message.answer(text, reply_markup=markup)
    await state.set_state(Admin.waiting_broadcast)
    await state.update_data(
        bc_chat_id=src.chat.id,
        bc_message_id=src.message_id,
        bc_preview="نظرسنجی",
        bc_is_forward=False,
        bc_show_source=False,
        bc_poll_id=poll_id,
    )
    await _render_broadcast_builder(src, state, fresh=True)
    await call.answer()


# ==================== پست در کانال ====================
@router.my_chat_member()
async def on_bot_membership(event, db: Database) -> None:  # noqa: ANN001
    """ثبت خودکار کانال هایی که ربات در آن ها ادمین می شود.

    Bot API متدی برای «فهرست کانال های من» ندارد. ولی هر بار وضعیت
    عضویت ربات عوض شود، این رویداد می آید - پس همان لحظه ثبت می کنیم
    و بعدا می شود از فهرست انتخابشان کرد.
    """
    chat = event.chat
    if chat.type not in ("channel", "supergroup", "group"):
        return
    status = event.new_chat_member.status
    can_post = status == "administrator" and bool(
        getattr(event.new_chat_member, "can_post_messages", True)
    )
    if status in ("left", "kicked") or not can_post:
        await db.forget_channel(chat.id)
        log.info("کانال %s (%s) از فهرست برداشته شد", chat.title, chat.id)
        return
    await db.save_channel(
        chat.id, chat.title or "-", chat.username or "", chat.type, True
    )
    log.info("کانال %s (%s) ثبت شد", chat.title, chat.id)



@router.callback_query(F.data == "adm:ch")
async def cb_channel(call: CallbackQuery, db: Database) -> None:
    """فهرست کانال هایی که ربات در آن ها ادمین است."""
    channels = await db.bot_channels()
    active = await db.get_setting("channel_id", "") or config.channel_id

    if not channels and not active:
        await edit_or_send(
            call.message, texts.ADMIN_CHANNEL_NONE, keyboards.admin_channel_kb(False)
        )
        return await call.answer()

    rows = "\n\n".join(
        texts.ADMIN_CHANNEL_ROW.format(
            mark="🔹" if str(c["chat_id"]) == str(active) else "▫️",
            title=esc(c["title"] or "-"),
            handle=("@" + c["username"]) if c["username"] else str(c["chat_id"]),
        )
        for c in channels
    ) or "—"
    await edit_or_send(
        call.message,
        texts.ADMIN_CHANNEL.format(count=len(channels), rows=rows),
        keyboards.admin_channels_kb(channels, active),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:chpick:"))
async def cb_channel_pick(call: CallbackQuery, db: Database) -> None:
    """انتخاب کانال فعال برای پست ها."""
    chat_id = call.data.split(":")[2]
    await db.set_setting("channel_id", chat_id)
    await call.answer("کانال فعال عوض شد")
    await cb_channel(call, db)


@router.callback_query(F.data == "adm:chnew")
async def cb_channel_post_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.waiting_channel_post)
    await edit_or_send(call.message, texts.ADMIN_CHANNEL_ASK, None)
    await call.answer()


@router.message(Admin.waiting_channel_post)
async def msg_channel_post(message: Message, db: Database, state: FSMContext) -> None:
    """پست کانال: همان سازنده پیام همگانی، فقط مقصد فرق دارد."""
    await state.set_state(Admin.waiting_broadcast)
    await state.update_data(
        bc_chat_id=message.chat.id,
        bc_message_id=message.message_id,
        bc_preview=(message.text or message.caption or "رسانه")[:60],
        bc_is_forward=False,
        bc_show_source=False,
        bc_target="channel",
    )
    await _render_broadcast_builder(message, state, fresh=True)


@router.callback_query(F.data.startswith("adm:pollch:"))
async def cb_poll_to_channel(call: CallbackQuery, db: Database) -> None:
    """نظرسنجی مستقیم در کانال."""
    poll_id = int(call.data.split(":")[2])
    channel = await db.get_setting("channel_id", "") or config.channel_id
    if not channel:
        return await call.answer(
            "اول آیدی کانال را در تنظیمات بگذار.", show_alert=True
        )
    text, _ = await polls.view(db, poll_id)
    if not text:
        return await call.answer("پیدا نشد.", show_alert=True)
    poll = await db.get_poll(poll_id)
    # در کانال دکمه callback کار درستی نمی کند (کاربر همان جا می ماند)،
    # پس یک دکمه لینک عمیق می گذاریم که او را به ربات می برد تا رای بدهد.
    markup = await _deep_link_markup(
        db, [(f"🗳 رای بده", f"poll_{poll_id}")]
    )
    try:
        await call.bot.send_message(chat_id=channel, text=text, reply_markup=markup)
    except Exception as exc:  # noqa: BLE001
        log.warning("پست نظرسنجی در کانال نشد: %s", exc)
        return await call.answer(f"نشد: {exc}", show_alert=True)
    await call.answer("در کانال منتشر شد ✅", show_alert=True)


# ==================== ریست کاربر ====================
@router.callback_query(F.data.startswith("adm:uresetask:"))
async def cb_user_reset_ask(call: CallbackQuery, db: Database) -> None:
    tg_id = int(call.data.split(":")[2])
    user = await db.get_user_by_tg(tg_id)
    if not user:
        return await call.answer("کاربر پیدا نشد.", show_alert=True)
    svc = await db.user_services(user["id"])
    await edit_or_send(
        call.message,
        texts.ADMIN_USER_RESET_ASK.format(
            name=esc((user.get("first_name") or "بی نام").strip()),
            telegram_id=tg_id,
            balance=f"{user['balance']:,}",
            services=len(svc),
        ),
        keyboards.admin_user_reset_kb(tg_id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:ureset:"))
async def cb_user_reset(call: CallbackQuery, db: Database, panel: Panel | None) -> None:
    """پاک کردن کاربر تا دفعه بعد مثل کاربر تازه باشد.

    soft: فقط ردپای ربات پاک می شود؛ سرویس ها روی پنل دست نخورده
    می مانند (لینک کاربر همچنان کار می کند ولی در ربات دیده نمی شود).
    hard: سرویس ها از پنل هم حذف می شوند - برگشت ناپذیر.
    """
    _, _, tg_id_s, mode = call.data.split(":")
    tg_id = int(tg_id_s)
    user = await db.get_user_by_tg(tg_id)
    if not user:
        return await call.answer("کاربر پیدا نشد.", show_alert=True)

    await call.answer()
    removed_panel = 0
    if mode == "hard" and panel is not None:
        for sv in await db.user_services(user["id"]):
            try:
                if await panel.remove(sv["panel_username"]):
                    removed_panel += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("حذف %s از پنل نشد: %s", sv["panel_username"], exc)

    stats = await db.purge_user(user["id"])
    log.info("کاربر %s ریست شد (%s): %s", tg_id, mode, stats)
    await edit_or_send(
        call.message,
        texts.ADMIN_USER_RESET_DONE.format(
            telegram_id=tg_id,
            services=stats.get("services", 0),
            txns=stats.get("transactions", 0),
            panel=removed_panel,
        ),
        keyboards.admin_dash_kb(),
    )


@router.message(Command("version"))
async def cmd_version(message: Message) -> None:
    """/version — چه نسخه ای واقعا روی سرور اجرا می شود.

    هر مورد ❌ یعنی آن فایل روی سرور جایگزین نشده. این دستور بعد از
    چند بار «این که قبلا درست شده بود» اضافه شد.
    """
    from app import version

    await message.answer(version.report())


@router.message(Command("locimg"))
async def cmd_locations_image(
    message: Message, command: CommandObject, db: Database
) -> None:
    """/locimg — تنظیم عکس صفحه «سرورها و لوکیشن ها».

    سه حالت:
    - روی یک عکس ریپلای کن و /locimg بزن → همان عکس ذخیره می شود
    - /locimg <آدرس عکس> → آدرس عمومی ذخیره می شود
    - /locimg off → عکس برداشته می شود و صفحه متنی می ماند

    file_id بهتر از آدرس است: روی سرور خود تلگرام است، پس سریع تر
    بارگذاری می شود و به در دسترس بودن هاست تو وابسته نیست.
    """
    arg = (command.args or "").strip()

    if arg.lower() in ("off", "حذف", "پاک"):
        await db.set_setting("locations_photo", "")
        return await message.answer("عکس صفحه لوکیشن ها برداشته شد.")

    photo_ref = ""
    if message.reply_to_message and message.reply_to_message.photo:
        # بزرگ ترین نسخه عکس را می گیریم
        photo_ref = message.reply_to_message.photo[-1].file_id
    elif arg.startswith(("http://", "https://")):
        photo_ref = arg

    if not photo_ref:
        current = await db.get_setting("locations_photo", "")
        err = await db.get_setting("locations_photo_error", "")
        kind = (
            "آدرس اینترنتی"
            if current.startswith(("http://", "https://"))
            else "file_id"
        ) if current else ""
        state = (
            f"الان تنظیم شده ({kind}):\n<code>{esc(current[:80])}</code>"
            if current
            else "الان عکسی تنظیم نشده."
        )
        err_line = (
            f"\n\n⚠️ آخرین خطای نمایش عکس:\n<code>{esc(err)}</code>" if err else ""
        )
        return await message.answer(
            f"{state}{err_line}\n\n"
            "برای تنظیم: روی یک عکس ریپلای کن و <code>/locimg</code> بزن،\n"
            "یا <code>/locimg https://...</code>\n"
            "برای برداشتن: <code>/locimg off</code>\n\n"
            "<b>اگر عکس نمایش داده نمی شود:</b> به جای ریپلای روی عکس، "
            "یک <b>آدرس اینترنتی</b> بده. مسیر جایگزین (پیش نمایش لینک) "
            "فقط با آدرس کار می کند و روی همه کلاینت ها جواب می دهد."
        )

    await db.set_setting("locations_photo", photo_ref)
    await db.set_setting("locations_photo_error", "")   # خطای قبلی منقضی شد
    is_url = photo_ref.startswith(("http://", "https://"))
    await message.answer(
        "✅ ثبت شد. صفحه «سرورها و لوکیشن ها» را باز کن تا ببینی.\n\n"
        + (
            "چون آدرس اینترنتی دادی، اگر روش اول (Rich Message) کار نکند، "
            "خودکار به پیش نمایش لینک برمی گردد - یعنی در هر صورت عکس را "
            "می بینی."
            if is_url
            else "⚠️ چون file_id دادی، فقط روش Rich Message کار می کند. "
            "اگر عکس نیامد، دوباره <code>/locimg</code> بزن تا علت دقیق را "
            "ببینی، و بهتر است به جایش یک آدرس اینترنتی بدهی."
        )
    )


@router.message(Command("bc"))
async def cmd_broadcast_status(message: Message, db: Database) -> None:
    """/bc — وضعیت ارسال همگانی و ادامه دادن دستی آن.

    اگر ارسالی نیمه کاره مانده (معمولا چون کران کار نمی کند)، این دستور
    هم وضعیتش را نشان می دهد و هم یک تکه دیگر را همین جا پیش می برد.
    """
    job = await db.active_broadcast()
    if not job:
        row = await db.fetchone(
            "SELECT * FROM broadcast_jobs ORDER BY id DESC LIMIT 1"
        )
        if not row:
            return await message.answer("تا حالا ارسال همگانی ثبت نشده.")
        last = dict(row)
        return await message.answer(
            f"آخرین ارسال (#{last['id']}) وضعیت: {last['status']}\n"
            f"✅ {last['sent']} · 🚫 {last['blocked']} · ⚠️ {last['failed']} "
            f"از {last['total']}"
        )

    done = job["sent"] + job["failed"] + job["blocked"]
    await message.answer(
        f"⏳ ارسال #{job['id']} در جریان است: {done} از {job['total']}\n"
        f"✅ {job['sent']} · 🚫 {job['blocked']} · ⚠️ {job['failed']}\n\n"
        "الان یک تکه دیگر را پیش می برم..."
    )
    result = await broadcast.run_chunk(message.bot, db, budget=25.0)
    if result and result.get("done"):
        await message.answer("ارسال تمام شد ✅")
    else:
        await message.answer(
            "این تکه تمام شد. اگر هنوز باقی مانده، یا دوباره /bc بزن یا "
            "کران را درست کن (وضعیتش را در /admin می بینی)."
        )


# ---------- ابزار بررسی دستگاه ها ----------
@router.message(Command("hwid"))
async def cmd_hwid(
    message: Message, command: CommandObject, db: Database, panel: Panel | None
) -> None:
    """/hwid — دیدن دستگاه های ثبت شده یک سرویس روی پنل.

    ورودی می تواند نام کاربری پنل، آیدی تلگرام کاربر، یا شماره سرویس
    (#12) باشد. آیدی تلگرام و شماره سرویس از روی دیتابیس به نام پنل
    ترجمه می شوند - چون پنل فقط نام کاربری خودش را می شناسد.

    برای عیب یابی است: اگر کاربری گفت «دستگاه هام درست نشون داده نمی شه»
    یا می خواهی بدانی HWID روی پنلت اصلا فعال هست یا نه، با این دستور
    خروجی خام و روش دسترسی (SDK یا REST) را می بینی.
    """
    query = (command.args or "").strip()
    if not query:
        return await message.answer(
            "یکی از این ها را بده:\n"
            "<code>/hwid obour_12345_1</code> (نام پنل)\n"
            "<code>/hwid 105679917</code> (آیدی تلگرام کاربر)\n"
            "<code>/hwid #12</code> (شماره سرویس)"
        )
    if panel is None:
        return await message.answer("پنل در دسترس نیست.")

    # ورودی را به نام کاربری پنل تبدیل می کنیم. قبلا هرچه می دادی
    # همان را مستقیم به پنل می فرستاد؛ اگر آیدی تلگرام می دادی، پنل
    # طبیعتا ۴۰۴ می داد و به نظر می رسید قابلیت کار نمی کند.
    username, source = query, "نام پنل"
    if query.startswith("@"):
        # یوزرنیم تلگرام: از دیتابیس به کاربر و بعد به سرویسش می رسیم.
        # قبلا همین رشته مستقیم به پنل می رفت و ۴۲۲ می گرفت.
        row = await db.fetchone(
            "SELECT * FROM users WHERE username = ?", (query.lstrip("@"),)
        )
        if not row:
            return await message.answer("کاربری با این یوزرنیم در ربات نیست.")
        services = await db.user_services(dict(row)["id"])
        if not services:
            return await message.answer("این کاربر سرویسی ندارد.")
        if len(services) > 1:
            rows = "\n".join(
                f"• <code>/hwid #{sv['id']}</code> — "
                f"{esc((sv.get('label') or '').strip() or sv['panel_username'])}"
                for sv in services[:10]
            )
            return await message.answer(
                f"این کاربر {len(services)} سرویس دارد. کدام؟\n\n{rows}"
            )
        username, source = services[0]["panel_username"], f"تنها سرویس {query}"
    elif query.startswith("#") and query[1:].isdigit():
        service = await db.get_service(int(query[1:]))
        if not service:
            return await message.answer("سرویسی با این شماره پیدا نشد.")
        username, source = service["panel_username"], f"سرویس #{query[1:]}"
    elif query.isdigit():
        owner = await db.get_user_by_tg(int(query))
        if owner:
            services = await db.user_services(owner["id"])
            if not services:
                return await message.answer("این کاربر سرویسی ندارد.")
            if len(services) > 1:
                rows = "\n".join(
                    f"• <code>/hwid #{sv['id']}</code> — "
                    f"{esc((sv.get('label') or '').strip() or sv['panel_username'])}"
                    for sv in services[:10]
                )
                return await message.answer(
                    f"این کاربر {len(services)} سرویس دارد. کدام؟\n\n{rows}"
                )
            username = services[0]["panel_username"]
            source = f"تنها سرویس کاربر {query}"

    from app import devices as dev

    trace: list[str] = []
    rows = await panel.get_hwids(username, trace=trace)
    if rows is None:
        # همه حدس های متد/مسیر را نشان می دهیم تا معلوم شود دقیقا کجا
        # گیر کرده - اگر یکی از این ها 401/403 داد یعنی مسیر درست است
        # ولی کلید API دسترسی ندارد؛ اگر همه 404 دادند یعنی این پنل
        # اصلا این اندپوینت را ندارد.
        detail = "\n".join(f"· {t}" for t in trace) or "(هیچ متد یا مسیری قابل امتحان نبود)"
        return await message.answer(
            f"پنل این اطلاعات را نداد.\n"
            f"نام کاربری امتحان شده: <code>{esc(username)}</code> ({source})\n\n"
            "اگر همه ۴۰۴ هستند یعنی یا این نام روی پنل نیست، یا HWID "
            "روی پنلت خاموش است.\n\n" + detail
        )
    if not rows:
        return await message.answer("قابلیت فعال است ولی هنوز دستگاهی ثبت نشده.")

    lines = [
        f"├ {dev.icon_and_os(r)[0]} {esc(dev.title(r))} · {dev.last_seen(r)}"
        for r in rows[:15]
    ]
    await message.answer(
        texts.ADMIN_DEVICES.format(
            username=esc(username),
            count=len(rows),
            how=esc(panel.hwid_capability()),
            rows="\n".join(lines),
        )
    )


# ---------- پاسخ ادمین به پیام پشتیبانی ----------
@router.message(F.reply_to_message)
async def admin_support_reply(message: Message, db: Database) -> None:
    """پاسخ ادمین به تیکت.

    این هندلر عمدا فقط با فیلتر AdminOnly کار می کند؛ در نسخه قبلی
    بدون فیلتر روتر بود و ریپلای کاربران عادی را هم «هندل شده» حساب
    می کرد، پس پیام آن ها هیچ وقت به پشتیبانی نمی رسید.
    """
    user_tg = await db.get_support_link(
        message.from_user.id, message.reply_to_message.message_id
    )
    if not user_tg:
        return
    # متن ادمین هم escape می شود: اگر < یا & در متن باشد، تلگرام کل پیام
    # را رد می کند و کاربر پاسخی نمی گیرد.
    body = esc((message.caption or message.text or "").strip())
    user = await db.get_user_by_tg(user_tg)
    # پاسخ روی همان پیامی که کاربر فرستاده بود ریپلای می شود تا بفهمد
    # جواب کدام سوالش است. اگر پیام قدیمی پاک شده باشد، تلگرام خطا
    # می دهد و بدون ریپلای دوباره تلاش می کنیم.
    reply_to = await db.last_user_msg_id(user["id"]) if user else None
    try:
        async def _deliver(rt: int | None) -> None:
            if body and not message.photo:
                with i18n.using(i18n.lang_of(user)):
                    await message.bot.send_message(
                        user_tg,
                        texts.SUPPORT_REPLY_GOT.format(body=body),
                        reply_to_message_id=rt,
                    )
            else:
                await message.copy_to(user_tg, reply_to_message_id=rt)

        try:
            await _deliver(reply_to)
        except Exception:  # noqa: BLE001
            await _deliver(None)  # پیام اصلی پیدا نشد، بدون ریپلای
        # ثبت در تاریخچه تیکت تا کاربر بعدا هم ببیند
        if user:
            # آخرین تیکت باز همین کاربر پاسخ داده شده علامت می خورد تا
            # در «تیکت های من» وضعیتش سبز شود
            open_ticket = await db.open_thread(user["id"])
            if open_ticket and (open_ticket.get("status") or "open") == "open":
                await db.set_ticket_status(open_ticket["id"], "answered")
            # پاسخ به همان رشته گفتگوی باز می چسبد؛ اگر تیکت بازی نباشد
            # (مثلا ادمین بی مقدمه پیام می دهد) خودش رشته تازه می شود.
            await db.add_ticket(
                user["id"],
                "out",
                body=body or None,
                file_id=message.photo[-1].file_id if message.photo else None,
                admin_id=message.from_user.id,
                thread_id=int(open_ticket["id"]) if open_ticket else None,
            )
        await message.answer(texts.ADMIN_REPLY_SENT)
    except Exception:  # noqa: BLE001
        await message.answer("ارسال نشد. کاربر ربات را بلاک کرده.")





# ═══════════════════ مینی اپ ═══════════════════


async def _download_to_static(bot, file_id: str, name: str) -> tuple[bool, str]:  # noqa: ANN001
    """فایل تلگرام را می گیرد و کنار مینی اپ می نشاند.

    چرا دانلود و نه نگه داشتن file_id؟ مینی اپ یک صفحه وب است و
    file_id را نمی تواند نمایش دهد. تبدیلش به لینک هم هر بار یک
    درخواست به تلگرام می خواهد و آن لینک ساعتی منقضی می شود. پس یک بار
    دانلود می کنیم و از هاست خودمان سرو می شود.
    """
    import os

    from app.webapp.wsgi import STATIC_DIR

    try:
        info = await bot.get_file(file_id)
        buf = await bot.download_file(info.file_path)
        data = buf.read()
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"

    if not data:
        return False, "فایل خالی بود"
    try:
        os.makedirs(STATIC_DIR, exist_ok=True)
        with open(os.path.join(STATIC_DIR, name), "wb") as fh:
            fh.write(data)
    except OSError as exc:
        return False, f"نوشتن روی دیسک نشد: {exc}"
    return True, f"{len(data) // 1024} کیلوبایت"


@router.message(Command("wafont"))
async def cmd_webapp_font(
    message: Message, command: CommandObject, db: Database
) -> None:
    """/wafont — تنظیم فونت مینی اپ با آپلود فایل.

    فایل woff2 را به صورت «سند» (نه عکس) بفرست و روی آن ریپلای کن.
    woff2 از ttf کوچک تر است و برای وب ساخته شده؛ ttf هم پذیرفته
    می شود ولی چند برابر حجم دارد و صفحه را کند می کند.
    """
    arg = (command.args or "").strip().lower()
    import os

    from app.webapp.wsgi import STATIC_DIR

    path = os.path.join(STATIC_DIR, "custom-font.woff2")

    if arg in ("off", "حذف", "پاک"):
        try:
            os.remove(path)
        except OSError:
            pass
        await db.set_setting("webapp_font", "")
        return await message.answer(
            "فونت اختصاصی برداشته شد. مینی اپ به فونت پیش فرض برمی گردد."
        )

    doc = message.reply_to_message.document if message.reply_to_message else None
    if not doc:
        current = await db.get_setting("webapp_font", "")
        state = (
            f"الان تنظیم شده: <code>{esc(current)}</code>"
            if current and os.path.isfile(path)
            else "الان فونت اختصاصی تنظیم نشده."
        )
        return await message.answer(
            f"{state}\n\n"
            "برای تنظیم: فایل فونت را به صورت <b>سند</b> بفرست، روی آن "
            "ریپلای کن و <code>/wafont</code> بزن.\n"
            "برای برداشتن: <code>/wafont off</code>\n\n"
            "<b>woff2</b> بهترین انتخاب است. ttf هم کار می کند ولی چند "
            "برابر حجم دارد و صفحه را کند می کند."
        )

    fname = (doc.file_name or "").lower()
    if not fname.endswith((".woff2", ".woff", ".ttf", ".otf")):
        return await message.answer(
            "فقط woff2، woff، ttf یا otf. فایل را به صورت سند بفرست، نه عکس."
        )
    if (doc.file_size or 0) > 3 * 1024 * 1024:
        return await message.answer(
            "فایل بزرگ تر از ۳ مگابایت است. یک نسخه subset شده فارسی بگیر."
        )

    ok, note = await _download_to_static(message.bot, doc.file_id, "custom-font.woff2")
    if not ok:
        return await message.answer(f"ذخیره نشد:\n<code>{esc(note)}</code>")

    await db.set_setting("webapp_font", doc.file_name or "custom-font")
    await message.answer(
        f"✅ فونت نشست ({note}).\n\n"
        "مینی اپ را ببند و دوباره باز کن. اگر تغییری ندیدی یعنی مرورگر "
        "نسخه قبلی را کش کرده؛ چند دقیقه بعد درست می شود."
    )


@router.message(Command("wabanner"))
async def cmd_webapp_banner(
    message: Message, command: CommandObject, db: Database
) -> None:
    """/wabanner — بنر ۱۶:۹ بخش هوش مصنوعی در مینی اپ.

    روی یک عکس ریپلای کن. نسبت ۱۶:۹ توصیه می شود چون قاب مینی اپ
    همین نسبت را دارد؛ عکس با نسبت دیگر از بالا و پایین بریده می شود.
    """
    arg = (command.args or "").strip().lower()
    import os

    from app.webapp.wsgi import STATIC_DIR

    path = os.path.join(STATIC_DIR, "ai-banner.jpg")

    if arg in ("off", "حذف", "پاک"):
        try:
            os.remove(path)
        except OSError:
            pass
        await db.set_setting("webapp_ai_banner", "")
        return await message.answer("بنر برداشته شد.")

    photo = message.reply_to_message.photo if message.reply_to_message else None
    if not photo:
        has = os.path.isfile(path)
        return await message.answer(
            ("بنر تنظیم شده است." if has else "بنری تنظیم نشده.")
            + "\n\nبرای تنظیم: روی یک عکس ریپلای کن و <code>/wabanner</code> بزن.\n"
            "برای برداشتن: <code>/wabanner off</code>\n\n"
            "نسبت <b>۱۶:۹</b> بده (مثلا ۱۲۸۰×۷۲۰). نسبت دیگر از بالا و "
            "پایین بریده می شود."
        )

    ok, note = await _download_to_static(message.bot, photo[-1].file_id, "ai-banner.jpg")
    if not ok:
        return await message.answer(f"ذخیره نشد:\n<code>{esc(note)}</code>")

    await db.set_setting("webapp_ai_banner", "1")
    await message.answer(f"✅ بنر نشست ({note}). بخش هوش مصنوعی مینی اپ را ببین.")
