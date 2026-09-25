"""پیگیری: کد پیگیری، خط زمانی، سوابق مالی و وضعیت تیکت.

چرا کد پیگیری؟ تا کاربر به جای «پولم چی شد؟» یک کد بفرستد و هم خودش
هم ادمین در یک نگاه بفهمند کدام درخواست است و کجای کار مانده.

کدها از روی آیدی ردیف ساخته می شوند (یکتا) به علاوه دو حرف تصادفی
(غیرقابل حدس). مالکیت هر کد همیشه بررسی می شود، مگر کاربر ادمین باشد.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app import keyboards, richtable, texts, ui
from app.config import config
from app.db import Database
from app.states import Track
from app.ui import edit_or_send
from app.utils import esc, fmt_dt, normalize_code
from app.i18n import t as _t

log = logging.getLogger("obour.track")
router = Router(name="track")

PAGE_SIZE = 10  # ردیف در هر صفحه سوابق

_ICONS = {
    "charge": "💳",
    "purchase": "🛒",
    "referral": "🎁",
    "admin_adjust": "🛠",
}


def _amount(txn: dict) -> str:
    """مبلغ با علامت. خریدها منفی ذخیره می شوند."""
    value = int(txn["amount"])
    sign = "−" if value < 0 else "+"
    return f"{sign}{abs(value):,}"


def _kind_title(txn: dict) -> str:
    return texts.TXN_KIND.get(txn["type"], txn["type"])


def _status_title(txn: dict) -> str:
    return texts.TXN_STATUS.get(txn["status"], txn["status"])


def _timeline(txn: dict) -> str:
    """خط زمانی یک تراکنش بر اساس ستون های زمانی که پر شده اند."""
    steps: list[tuple[str, str | None]] = [(_t("ثبت درخواست"), txn["created_at"])]
    if txn["type"] == "charge":
        steps.append((_t("اعلام واریز"), txn.get("paid_at")))
        steps.append(
            (_t("ارسال رسید"), txn["created_at"] if txn.get("receipt_file_id") else None)
        )
    if txn.get("cancelled_at"):
        steps.append((_t("لغو توسط تو"), txn["cancelled_at"]))
    elif txn["status"] == "approved":
        steps.append((_t("تایید"), txn.get("decided_at")))
    elif txn["status"] == "rejected":
        steps.append((_t("رد شدن"), txn.get("decided_at")))
    elif txn["status"] == "failed":
        steps.append((_t("توقف با خطا"), txn.get("decided_at")))
    else:
        steps.append((_t("بررسی پشتیبانی"), None))

    lines = []
    for title, when in steps:
        mark = "✅" if when else "⏳"
        tail = f" · \u2068{fmt_dt(when)}\u2069" if when else " · " + _t("هنوز انجام نشده")
        lines.append(f"├ {mark} \u2068{title}\u2069{tail}")
    return "\n".join(lines)


async def _show_txn(message: Message, db: Database, txn: dict) -> None:
    note = ""
    if txn["type"] == "charge" and txn["status"] == "pending" and txn.get("receipt_file_id"):
        pos = await db.charge_queue_position(txn["id"])
        note = texts.TRACK_QUEUE.format(pos=pos)
    if txn["status"] in ("rejected", "failed") and txn.get("reject_reason"):
        note += texts.TRACK_REJECT.format(reason=esc(txn["reject_reason"]))
    await edit_or_send(
        message,
        texts.TRACK_TXN.format(
            code=txn.get("code") or txn["id"],
            kind=_kind_title(txn),
            amount=_amount(txn),
            timeline=_timeline(txn),
            note=note,
            status=_status_title(txn),
        ),
        keyboards.track_result_kb(),
    )


async def _show_ticket_track(
    message: Message, ticket: dict, db: Database | None = None, as_admin: bool = False
) -> None:
    """صفحه پیگیری یک تیکت.

    اگر بیننده ادمین باشد، این پیام هم به کاربر گره می خورد؛ یعنی
    ادمین می تواند مستقیم روی همین پیام ریپلای کند و جوابش به کاربر
    برسد - بدون اینکه دنبال پیام اصلی تیکت بگردد.
    """
    status = ticket.get("status") or "open"
    steps = [(_t("ارسال تیکت"), ticket["created_at"])]
    steps.append((_t("پاسخ پشتیبانی"), ticket["created_at"] if status == "answered" else None))
    if status == "closed":
        steps.append((_t("بسته شدن"), ticket.get("closed_at")))
    lines = [
        f"├ {'✅' if when else '⏳'} \u2068{title}\u2069"
        + (f" · \u2068{fmt_dt(when)}\u2069" if when else " · " + _t("در انتظار"))
        for title, when in steps
    ]
    body = (ticket.get("body") or texts.TICKET_PHOTO)[:200]
    sent = await edit_or_send(
        message,
        texts.TRACK_TICKET.format(
            code=ticket.get("code") or ticket["id"],
            timeline="\n".join(lines),
            body=esc(body),
            note="",
            status=texts.TICKET_STATUS.get(status, status),
        ),
        keyboards.track_result_kb("ticket", ticket["id"]),
    )
    if db is not None and as_admin and ticket.get("user_tg_id"):
        try:
            await db.save_support_link(
                message.chat.id, sent.message_id, int(ticket["user_tg_id"])
            )
        except Exception:  # noqa: BLE001
            log.debug("گره زدن پیام پیگیری به کاربر نشد", exc_info=True)


async def _show_ai_order_track(message: Message, order: dict) -> None:
    """صفحه پیگیری یک سفارش هوش مصنوعی."""
    import json

    provider_line = ""
    if order.get("provider_order_id"):
        provider_line = f"{_t('کد نزد سرویس دهنده')}: {order['provider_order_id']}\n"

    links_line = ""
    if order.get("products"):
        try:
            items = json.loads(order["products"])
            links_line = "\n" + _t("لینک تحویل") + ":\n" + "\n".join(f"<code>{p}</code>" for p in items) + "\n"
        except Exception:  # noqa: BLE001
            pass

    await edit_or_send(
        message,
        texts.AI_TRACK.format(
            code=order["code"],
            status=texts.AI_STATUS.get(order["status"], order["status"]),
            title=order["title"],
            price=f"{order['price']:,}",
            when=fmt_dt(order["created_at"]),
            provider_line=provider_line,
            links_line=links_line,
        ),
        keyboards.ai_track_kb(order["id"], bool(order.get("provider_order_id"))),
    )


async def _lookup(message: Message, db: Database, user: dict, raw: str) -> bool:
    """جستجوی کد و نمایش نتیجه. False یعنی پیدا نشد."""
    code = normalize_code(raw)
    is_admin = user["telegram_id"] in config.admin_ids

    txn = await db.transaction_by_code(code)
    if txn and (is_admin or txn["user_id"] == user["id"]):
        await _show_txn(message, db, txn)
        return True

    ticket = await db.ticket_by_code(code)
    if ticket and (is_admin or ticket["user_id"] == user["id"]):
        await _show_ticket_track(message, ticket, db, as_admin=is_admin)
        return True

    ai_order = await db.ai_order_by_code(code)
    if ai_order and (is_admin or ai_order["user_id"] == user["id"]):
        await _show_ai_order_track(message, ai_order)
        return True

    await edit_or_send(
        message,
        texts.TRACK_NOT_FOUND.format(code=esc(code or "-")),
        keyboards.track_kb(),
    )
    return False


# ---------- ورودی ها ----------
@router.message(Command("track"))
async def cmd_track(
    message: Message,
    command: CommandObject,
    db: Database,
    state: FSMContext,
    user: dict,
) -> None:
    """/track یا /track OB-4F2K9"""
    await state.clear()
    if command.args:
        return await _lookup(message, db, user, command.args)
    await state.set_state(Track.waiting_code)
    await message.answer(texts.TRACK_ASK, reply_markup=keyboards.track_kb())


@router.callback_query(F.data == "track")
async def cb_track(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Track.waiting_code)
    await edit_or_send(call.message, texts.TRACK_ASK, keyboards.track_kb())
    await call.answer()


@router.message(Track.waiting_code, F.text)
async def txt_track_code(
    message: Message, db: Database, state: FSMContext, user: dict
) -> None:
    """کد تایپ شده. پیام کاربر پاک می شود تا چت تمیز بماند."""
    raw = message.text.strip()
    if raw.startswith("/"):
        await state.clear()
        return
    await ui.consume(message)
    await state.clear()
    await _lookup(message, db, user, raw)


# ---------- سوابق ----------
async def _history(
    message: Message, db: Database, user: dict, kind: str, page: int
) -> None:
    real_kind = None if kind == "all" else kind
    total = await db.count_transactions(user["id"], real_kind)
    items = await db.user_transactions(
        user["id"], limit=PAGE_SIZE, offset=page * PAGE_SIZE, kind=real_kind
    )
    if not items:
        return await edit_or_send(message, texts.HISTORY_EMPTY, keyboards.back_menu())

    shown = f"{page * PAGE_SIZE + 1}-{page * PAGE_SIZE + len(items)}"
    markup = keyboards.history_kb(
        items, kind, page, has_next=(page + 1) * PAGE_SIZE < total
    )

    # صفحه سوابق ماهیتا جدولی است؛ اول جدول واقعی Rich Message را
    # امتحان می کنیم (Bot API 10.1+). اگر کلاینت کاربر یا سرور Bot API
    # (self-hosted قدیمی و مانند آن) پشتیبانی نکند، خطا می گیریم و به
    # همان قالب متنی قبلی برمی گردیم - کاربر چیزی از دست نمی دهد.
    try:
        rich = richtable.table(
            headers=[_t("نوع"), _t("مبلغ"), _t("کد"), _t("تاریخ"), _t("وضعیت")],
            rows=[
                [
                    texts.TXN_KIND.get(t["type"], t["type"]),
                    _amount(t),
                    str(t.get("code") or t["id"]),
                    fmt_dt(t["created_at"]),
                    texts.TXN_STATUS.get(t["status"], t["status"]),
                ]
                for t in items
            ],
            caption="🗂 " + _t("سوابق - {shown} از {total} مورد", shown=shown, total=total),
        )
        await ui.edit_or_send_rich(message, rich, markup)
        return
    except Exception:  # noqa: BLE001
        log.warning("جدول سوابق (Rich Message) کار نکرد، نسخه متنی جایگزین شد", exc_info=True)

    rows = [
        texts.HISTORY_ROW.format(
            icon=_ICONS.get(t["type"], "🧾"),
            kind=texts.TXN_KIND.get(t["type"], t["type"]),
            amount=_amount(t),
            code=t.get("code") or t["id"],
            when=fmt_dt(t["created_at"]),
            status=texts.TXN_STATUS.get(t["status"], t["status"]),
        )
        for t in items
    ]
    await edit_or_send(
        message,
        texts.HISTORY.format(shown=shown, total=total, rows="\n\n".join(rows)),
        markup,
    )


@router.callback_query(F.data == "hist")
async def cb_history(call: CallbackQuery, db: Database, user: dict) -> None:
    await _history(call.message, db, user, "all", 0)
    await call.answer()


@router.callback_query(F.data.startswith("hist:f:"))
async def cb_history_filter(call: CallbackQuery, db: Database, user: dict) -> None:
    await _history(call.message, db, user, call.data.split(":")[2], 0)
    await call.answer()


@router.callback_query(F.data.startswith("hist:p:"))
async def cb_history_page(call: CallbackQuery, db: Database, user: dict) -> None:
    _, _, kind, page = call.data.split(":")
    await _history(call.message, db, user, kind, max(0, int(page)))
    await call.answer()


@router.callback_query(F.data.startswith("hist:v:"))
async def cb_history_item(call: CallbackQuery, db: Database, user: dict) -> None:
    txn = await db.get_transaction(int(call.data.split(":")[2]))
    if not txn or txn["user_id"] != user["id"]:
        return await call.answer(_t("این مورد پیدا نشد."), show_alert=True)
    await _show_txn(call.message, db, txn)
    await call.answer()


# ---------- تیکت ها ----------
@router.callback_query(F.data == "sup:tk")
async def cb_ticket_list(call: CallbackQuery, db: Database, user: dict) -> None:
    items = await db.ticket_threads(user["id"], limit=8)
    if not items:
        await edit_or_send(
            call.message, texts.TICKETS_STATUS_EMPTY, keyboards.tickets_kb()
        )
        return await call.answer()

    markup = keyboards.ticket_list_kb(items)

    # فهرست تیکت ها هم ماهیتا جدولی است؛ اول جدول واقعی Rich Message.
    try:
        rich = richtable.table(
            headers=[_t("وضعیت"), _t("کد"), _t("پیام"), _t("زمان"), _t("پاسخ")],
            rows=[
                [
                    texts.TICKET_STATUS.get(t.get("status") or "open", _t("🟡 باز")),
                    str(t.get("code") or t["id"]),
                    (t.get("body") or texts.TICKET_PHOTO)[:60],
                    fmt_dt(t["created_at"]),
                    str(t.get("replies") or 0),
                ]
                for t in items
            ],
            caption="🎫 " + _t("تیکت های من - {n} مورد", n=len(items)),
        )
        await ui.edit_or_send_rich(call.message, rich, markup)
        return await call.answer()
    except Exception:  # noqa: BLE001
        log.warning("جدول تیکت ها (Rich Message) کار نکرد، نسخه متنی جایگزین شد", exc_info=True)

    rows = []
    for t in items:
        body = (t.get("body") or texts.TICKET_PHOTO)[:60]
        rows.append(
            texts.TICKET_ROW.format(
                status=texts.TICKET_STATUS.get(t.get("status") or "open", _t("🟡 باز")),
                code=t.get("code") or t["id"],
                body=esc(body),
                when=fmt_dt(t["created_at"]),
                replies=t.get("replies") or 0,
            )
        )
    await edit_or_send(
        call.message,
        texts.TICKETS_STATUS.format(count=len(items), rows="\n\n".join(rows)),
        markup,
    )
    await call.answer()


@router.callback_query(F.data.startswith("tk:v:"))
async def cb_ticket_view(call: CallbackQuery, db: Database, user: dict) -> None:
    ticket_id = int(call.data.split(":")[2])
    messages = await db.ticket_messages(ticket_id, user["id"])
    if not messages or messages[0]["direction"] != "in":
        return await call.answer(_t("این تیکت پیدا نشد."), show_alert=True)

    head = messages[0]
    rows = []
    for m in messages:
        body = esc((m.get("body") or texts.TICKET_PHOTO)[:250])
        tpl = texts.TICKET_IN if m["direction"] == "in" else texts.TICKET_OUT
        rows.append(tpl.format(time=fmt_dt(m["created_at"]), body=body))
    await db.mark_tickets_read(user["id"])

    status = head.get("status") or "open"
    await edit_or_send(
        call.message,
        texts.TICKET_VIEW.format(
            code=head.get("code") or head["id"],
            status=texts.TICKET_STATUS.get(status, status),
            when=fmt_dt(head["created_at"]),
            rows="\n\n".join(rows),
        ),
        keyboards.ticket_view_kb(ticket_id, closed=status == "closed"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("tk:close:"))
async def cb_ticket_close(call: CallbackQuery, db: Database, user: dict) -> None:
    ticket_id = int(call.data.split(":")[2])
    if not await db.close_ticket(ticket_id, user["id"]):
        return await call.answer(_t("این تیکت قبلا بسته شده."), show_alert=True)
    await call.answer(texts.TICKET_CLOSED, show_alert=True)
    await cb_ticket_list(call, db, user)


@router.callback_query(F.data.startswith("tk:bump:"))
async def cb_ticket_bump(call: CallbackQuery, db: Database, user: dict) -> None:
    """پیگیری: یادآوری تیکت به ادمین ها.

    با قفل ۳۰ دقیقه ای محدود می شود تا به ابزار اسپم تبدیل نشود.
    """
    ticket_id = int(call.data.split(":")[2])
    messages = await db.ticket_messages(ticket_id, user["id"])
    if not messages:
        return await call.answer(_t("این تیکت پیدا نشد."), show_alert=True)
    head = messages[0]
    if (head.get("status") or "open") == "closed":
        return await call.answer(_t("این تیکت بسته شده."), show_alert=True)

    if not await db.acquire_lock(f"bump:{ticket_id}", ttl_seconds=1800):
        return await call.answer(texts.TICKET_BUMP_TOO_SOON, show_alert=True)

    body = esc((head.get("body") or texts.TICKET_PHOTO)[:300])
    sent = 0
    for admin_id in config.admin_ids:
        try:
            await call.bot.send_message(
                admin_id,
                texts.ADMIN_TICKET_BUMP.format(
                    name=esc(user.get("first_name") or "-"),
                    username=esc(user.get("username") or "-"),
                    telegram_id=user["telegram_id"],
                    code=head.get("code") or head["id"],
                    body=body,
                ),
            )
            sent += 1
        except Exception:  # noqa: BLE001
            log.warning("پیگیری تیکت به ادمین %s نرفت", admin_id, exc_info=True)
    await call.answer(
        texts.TICKET_BUMP_SENT if sent else _t("پشتیبانی در دسترس نیست، بعدا امتحان کن."),
        show_alert=True,
    )
