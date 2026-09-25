"""هندلر شروع، منوی اصلی و پشتیبانی."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app import keyboards, polls, richtable, texts, ui
from app.config import config
from app.db import Database
from app.keyboards import is_admin
from app.states import Support
from app.ui import edit_or_send
from app.utils import esc, fmt_dt
from app.i18n import t as _t

log = logging.getLogger("obour.start")
router = Router(name="start")


async def show_menu(target: Message, user: dict, edit: bool = False) -> None:
    """نمایش منوی اصلی.

    edit=True یعنی از دکمه بازگشت آمده ایم و باید همان پیام ویرایش شود،
    نه اینکه پیام تازه ساخته شود و چت پر از منوی تکراری شود.
    """
    fn = texts.welcome if not user.get("balance") else texts.welcome_back
    trial_available = config.trial_enabled and not user.get("free_trial_used")
    text = fn(
        name=esc(user.get("first_name") or _t("دوست من")),
        balance=f"{user['balance']:,}",
    )
    markup = keyboards.main_menu(trial_available)

    if edit:
        await edit_or_send(target, text, markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(F.data == "rules:ok")
async def cb_rules_accept(call: CallbackQuery, db: Database, user: dict) -> None:
    """تایید قوانین و ورود به منوی اصلی."""
    await db.accept_rules(user["id"])
    fresh = await db.get_user(user["id"])
    await call.answer(_t("ممنون ✅"))
    try:
        await call.message.delete()
    except Exception:  # noqa: BLE001
        pass
    await call.message.answer(texts.RULES_ACCEPTED)
    await show_menu(call.message, fresh)


@router.callback_query(F.data == "lang")
async def cb_lang_menu(call: CallbackQuery, user: dict) -> None:
    """عوض کردن زبان از منوی اصلی."""
    await edit_or_send(call.message, texts.LANG_PICK, keyboards.lang_kb(user.get("lang")))
    await call.answer()


@router.callback_query(F.data.startswith("lang:"))
async def cb_lang_pick(call: CallbackQuery, db: Database, user: dict) -> None:
    """ثبت زبان. کاربر تازه بعدش قوانین را می بیند، بقیه منوی اصلی را."""
    from app import i18n
    from app.middlewares import rules_body

    lang = i18n.normalize(call.data.split(":", 1)[1])
    if not lang:
        return await call.answer()
    first_time = not user.get("lang")
    await db.set_user_lang(user["id"], lang)
    i18n.set_lang(lang)
    fresh = await db.get_user(user["id"]) or {**user, "lang": lang}
    await call.answer(f"{i18n.FLAGS[lang]} {i18n.NAMES[lang]}")

    needs_rules = (
        first_time and not fresh.get("rules_accepted_at") and not is_admin(call.from_user.id)
        and await db.get_setting("rules_enabled", "1") == "1"
    )
    if needs_rules:
        return await edit_or_send(call.message, await rules_body(db, fresh), keyboards.rules_kb())
    await show_menu(call.message, fresh, edit=True)


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, user: dict) -> None:
    if call.message:
        await show_menu(call.message, user, edit=True)
    await call.answer()


@router.callback_query(F.data == "sup")
async def cb_support(call: CallbackQuery, db: Database, state: FSMContext, user: dict) -> None:
    await state.clear()
    tickets = await db.user_tickets(user["id"], limit=1)
    unread = await db.unread_replies(user["id"])
    note = (
        texts.SUPPORT_UNREAD.format(n=unread) if unread else texts.SUPPORT_NO_UNREAD
    )
    await edit_or_send(
        call.message,
        texts.SUPPORT.format(unread=note),
        keyboards.support_kb(bool(tickets)),
    )
    await call.answer()


@router.callback_query(F.data == "sup:new")
async def cb_ticket_new(
    call: CallbackQuery, db: Database, state: FSMContext, user: dict
) -> None:
    """شروع پیام به پشتیبانی.

    اگر کاربر تیکت بازی داشته باشد، صریح می گوییم پیامش به همان تیکت
    اضافه می شود - نه اینکه بی خبر تیکت تازه بسازیم. این همان رفتاری
    است که سایت های پشتیبانی دارند.
    """
    await state.set_state(Support.waiting_message)
    current = await db.open_thread(user["id"])
    if current:
        body = texts.SUPPORT_ASK_EXISTING.format(
            code=current.get("code") or current["id"]
        )
    else:
        body = texts.SUPPORT_ASK
    await edit_or_send(call.message, body, keyboards.ticket_cancel_kb())
    await call.answer()


@router.callback_query(F.data.startswith("pv:"))
async def cb_poll_vote(call: CallbackQuery, db: Database, user: dict) -> None:
    """ثبت رای کاربر روی نظرسنجی.

    رای قابل تغییر است: اگر گزینه دیگری بزند جایگزین می شود، و اگر
    همان گزینه قبلی را بزند فقط پیام کوتاه می گیرد (بدون ویرایش بی مورد
    که تلگرام هم آن را «message is not modified» می داند).
    """
    _, poll_id_s, option_id_s = call.data.split(":")
    poll_id, option_id = int(poll_id_s), int(option_id_s)

    poll = await db.get_poll(poll_id)
    if not poll:
        return await call.answer(_t("این نظرسنجی دیگه در دسترس نیست."), show_alert=True)
    if not poll["is_open"]:
        return await call.answer(_t("رای گیری این نظرسنجی بسته شده."), show_alert=True)

    changed = await db.poll_vote(poll_id, option_id, user["id"])
    if not changed:
        return await call.answer(_t("همین گزینه رو قبلا انتخاب کرده بودی."))

    text, markup = await polls.view(db, poll_id, user["id"])
    try:
        await edit_or_send(call.message, text, markup)
    except Exception:  # noqa: BLE001
        log.debug("به روزرسانی نظرسنجی روی پیام انجام نشد", exc_info=True)
    await call.answer(_t("رایت ثبت شد ✅"))


@router.callback_query(F.data == "sup:list")
async def cb_tickets(call: CallbackQuery, db: Database, user: dict) -> None:
    """تاریخچه گفتگو با پشتیبانی: هر پیامی که کاربر یا ادمین رد و بدل کرده."""
    items = await db.user_tickets(user["id"])
    if not items:
        await edit_or_send(call.message, texts.TICKETS_EMPTY, keyboards.tickets_kb())
        return await call.answer()

    markup = keyboards.tickets_kb()
    await db.mark_tickets_read(user["id"])

    # فهرست پیام های رفت و برگشت هم ماهیتا جدولی است (از کی، چی، کی).
    try:
        rich = richtable.table(
            headers=[_t("از"), _t("پیام"), _t("زمان")],
            rows=[
                [
                    _t("تو") if t["direction"] == "in" else _t("پشتیبانی"),
                    (t["body"] or texts.TICKET_PHOTO)[:80],
                    fmt_dt(t["created_at"]),
                ]
                for t in items
            ],
            caption=_t("💬 گفتگوهای تو با پشتیبانی"),
        )
        await ui.edit_or_send_rich(call.message, rich, markup)
        return await call.answer()
    except Exception:  # noqa: BLE001
        log.warning("جدول گفتگو (Rich Message) کار نکرد، نسخه متنی جایگزین شد", exc_info=True)

    lines = [texts.TICKETS_HEADER]
    for t in items:
        body = t["body"] or texts.TICKET_PHOTO
        if len(body) > 200:
            body = body[:200] + "..."
        body = esc(body)
        tpl = texts.TICKET_IN if t["direction"] == "in" else texts.TICKET_OUT
        lines.append(tpl.format(time=fmt_dt(t["created_at"]), body=body))
    await edit_or_send(
        call.message, "\n\n".join(lines), markup
    )
    await call.answer()


@router.message(Support.waiting_message, F.photo | F.text)
async def msg_ticket(message: Message, db: Database, state: FSMContext, user: dict) -> None:
    """دریافت تیکت کاربر و ارسال به ادمین ها."""
    await state.clear()
    body = (message.caption or message.text or "").strip()
    file_id = message.photo[-1].file_id if message.photo else None
    if not body and not file_id:
        return await message.answer(_t("پیام خالیه. دوباره بفرست."))
    _, thread_id, is_new = await db.add_ticket(
        user["id"], "in", body=body, file_id=file_id, user_msg_id=message.message_id
    )
    await _forward_to_support(
        message, user, db, await db.ticket_code(thread_id), is_new=is_new
    )


@router.message(F.photo | F.video | F.document)
async def media_fallback(message: Message, db: Database, user: dict) -> None:
    """عکس / فایل خارج از جریان شارژ = تیکت پشتیبانی."""
    if is_admin(message.from_user.id):
        return
    file_id = message.photo[-1].file_id if message.photo else None
    _, thread_id, is_new = await db.add_ticket(
        user["id"], "in", body=message.caption, file_id=file_id,
        user_msg_id=message.message_id,
    )
    await _forward_to_support(
        message, user, db, await db.ticket_code(thread_id), is_new=is_new
    )


@router.message(F.text)
async def text_fallback(message: Message, db: Database, user: dict) -> None:
    """هر متن ناشناخته = تیکت پشتیبانی.

    دستورها (هر چیزی که با / شروع شود) تیکت نمی شوند: با فیلتر ادمین روی
    روتر ادمین، دستور /admin کاربر عادی به اینجا می رسد و نباید به عنوان
    پیام پشتیبانی برای ادمین فرستاده شود.
    """
    if is_admin(message.from_user.id):
        return
    if (message.text or "").startswith("/"):
        return await message.answer(
            _t("این دستور رو نمی شناسم. از منوی پایین استفاده کن."),
            reply_markup=keyboards.back_menu(),
        )
    _, thread_id, is_new = await db.add_ticket(
        user["id"], "in", body=message.text, user_msg_id=message.message_id
    )
    await _forward_to_support(
        message, user, db, await db.ticket_code(thread_id), is_new=is_new
    )


async def _forward_to_support(
    message: Message, user: dict, db, code: str | None = None, is_new: bool = True  # noqa: ANN001
) -> None:
    """ارسال تیکت به ادمین ها با راهنمای ریپلای.

    کد پیگیری هم در سربرگ ادمین می آید و هم به کاربر داده می شود، تا
    هر دو طرف بتوانند بعدا به همین تیکت ارجاع بدهند.
    """
    # تاریخچه گفتگو با همین کاربر، تا ادمین بداند درباره چه چیزی حرف
    # می زنند بدون اینکه جای دیگری را باز کند.
    history: list[dict] = []
    if db is not None:
        try:
            history = await db.recent_ticket_history(user["id"], limit=6)
        except Exception:  # noqa: BLE001
            log.debug("خواندن تاریخچه تیکت نشد", exc_info=True)

    # سربرگ می گوید تیکت تازه است یا ادامه گفتگوی باز - تا ادمین
    # نپندارد کاربر چند تیکت جدا زده.
    head_title = "💬 <b>تیکت جدید</b>" if is_new else "↩️ <b>پیام تازه در تیکت باز</b>"
    head_text = (
        f"{head_title}\n\n"
        + f"👤 {esc(user.get('first_name') or '-')} "
        + f"(@{esc(user.get('username') or '-')})\n"
        + f"🆔 <code>{user['telegram_id']}</code>"
        + (f"\n🎫 <code>{code}</code>" if code else "")
        + texts.ADMIN_REPLY_HINT
    )

    for admin_id in config.admin_ids:
        try:
            header = None
            if history:
                # جدول تاریخچه: اول Rich Message، اگر نشد متنی
                try:
                    rich = richtable.table(
                        headers=[_t("از"), _t("پیام"), _t("زمان")],
                        rows=[
                            [
                                "کاربر" if h["direction"] == "in" else "پشتیبانی",
                                (h.get("body") or texts.TICKET_PHOTO)[:60],
                                fmt_dt(h["created_at"]),
                            ]
                            for h in history
                        ],
                        caption="گفتگوهای قبلی با این کاربر",
                    )
                    header = await message.bot.send_rich_message(
                        chat_id=admin_id, rich_message=rich
                    )
                    header = await message.bot.send_message(admin_id, head_text)
                except Exception:  # noqa: BLE001
                    lines = "\n".join(
                        f"{'👤' if h['direction'] == 'in' else '🛡'} "
                        f"{esc((h.get('body') or texts.TICKET_PHOTO)[:60])} "
                        f"· {fmt_dt(h['created_at'])}"
                        for h in history
                    )
                    header = await message.bot.send_message(
                        admin_id,
                        head_text + "\n\n📋 <b>گفتگوهای قبلی</b>\n" + lines,
                    )
            if header is None:
                header = await message.bot.send_message(admin_id, head_text)

            copied = await message.copy_to(admin_id, reply_to_message_id=header.message_id)
            if db is not None:
                await db.save_support_link(admin_id, header.message_id, user["telegram_id"])
                await db.save_support_link(admin_id, copied.message_id, user["telegram_id"])
        except Exception as exc:  # noqa: BLE001
            log.warning("support forward to %s failed: %s", admin_id, exc)
    if is_new:
        body_out = texts.SUPPORT_SENT + (
            texts.CODE_LINE.format(code=code) if code else ""
        )
    else:
        # کاربر باید بداند پیامش تیکت تازه نساخته
        body_out = texts.TICKET_APPENDED.format(code=code or "-")
    await message.answer(body_out, reply_markup=keyboards.tickets_kb())
