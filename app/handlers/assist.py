"""دستیار هوش مصنوعی در ربات.

کاربر: گفتگوی پشتیبانی و عیب یابی (با اسکرین شات)، پیشنهاد پلن، دستیار
فروشگاه. ادمین: پیش نویس جواب تیکت، بررسی رسید، تست، گزارش و حدس نام.

همه تماس ها داخل همان آپدیت انجام می شود (نه تسک پس زمینه): زیر
Passenger پروسه بعد از جواب وبهوک ممکن است بخوابد و تسک نیمه کاره بماند.
سقف انتظار AI_TIMEOUT کمتر از مهلت ۵۰ ثانیه ای وبهوک است.
"""
from __future__ import annotations

import io
import logging

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app import i18n, keyboards, texts
from app.db import Database
from app.i18n import t as _t
from app.keyboards import is_admin
from app.services import assistant
from app.services.assistant import AIError
from app.states import Assist
from app.ui import edit_or_send
from app.utils import esc

log = logging.getLogger("obour.assist")
router = Router(name="assist")

MAX_TURNS = 10


async def _download(bot, file_id: str) -> bytes:  # noqa: ANN001
    f = await bot.get_file(file_id)
    buf = await bot.download_file(f.file_path, destination=io.BytesIO())
    return buf.getvalue() if hasattr(buf, "getvalue") else bytes(buf)


async def _typing(message: Message) -> None:
    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    except Exception:  # noqa: BLE001
        pass


# ═══════════════════ گفتگوی پشتیبانی و عیب یابی ═══════════════════

@router.callback_query(F.data.in_({"aih", "aih:fix"}))
async def cb_assist_start(call: CallbackQuery, state: FSMContext) -> None:
    if not assistant.ready("ai_support"):
        return await call.answer(texts.ASSIST_DOWN, show_alert=True)
    mode = "fix" if call.data == "aih:fix" else "chat"
    await state.set_state(Assist.chatting)
    await state.update_data(ai_mode=mode, ai_hist=[])
    await edit_or_send(call.message, texts.ASSIST_FIX_INTRO if mode == "fix" else texts.ASSIST_INTRO,
                       keyboards.assist_chat_kb())
    await call.answer()


@router.message(Assist.chatting, F.text | F.photo)
async def msg_assist(message: Message, db: Database, state: FSMContext, user: dict) -> None:
    if (message.text or "").startswith("/"):
        return
    data = await state.get_data()
    hist: list[dict] = list(data.get("ai_hist") or [])
    mode = data.get("ai_mode") or "chat"
    body = (message.caption or message.text or "").strip()[:1500]

    if not assistant.ready("ai_support"):
        return await message.answer(texts.ASSIST_DOWN, reply_markup=keyboards.assist_chat_kb())
    if not await assistant.allowed(db, user["id"]):
        return await message.answer(texts.ASSIST_LIMIT, reply_markup=keyboards.assist_chat_kb())

    await _typing(message)
    image = None
    if message.photo:
        try:
            image = await _download(message.bot, message.photo[-1].file_id)
        except Exception:  # noqa: BLE001
            log.info("دانلود عکس برای دستیار نشد", exc_info=True)
        # بعدا اگر به پشتیبانی ارجاع شد، ادمین خود عکس را هم ببیند
        await state.update_data(ai_photo=message.photo[-1].file_id)

    try:
        answer = await assistant.support_reply(db, user, hist, body, image=image, mode=mode)
    except AIError as exc:
        log.info("دستیار جواب نداد: %s", exc)
        return await message.answer(texts.ASSIST_DOWN, reply_markup=keyboards.assist_chat_kb())

    hist.append({"role": "user", "text": body or "[screenshot]"})
    hist.append({"role": "assistant", "text": answer[:1200]})
    await state.update_data(ai_hist=hist[-MAX_TURNS * 2:])
    await message.answer("🤖 " + assistant.to_html(answer), reply_markup=keyboards.assist_chat_kb())


@router.callback_query(F.data == "aih:esc")
async def cb_assist_escalate(call: CallbackQuery, db: Database, state: FSMContext, user: dict) -> None:
    """ارجاع به پشتیبانی انسانی با خلاصه گفتگو."""
    from app.services import support

    data = await state.get_data()
    hist = list(data.get("ai_hist") or [])
    photo = data.get("ai_photo")
    await state.clear()
    if not hist:
        # هنوز چیزی نپرسیده: همان مسیر معمول تیکت
        from app.handlers.start import cb_ticket_new

        return await cb_ticket_new(call, db, state, user)
    await call.answer(_t("در حال ارسال..."))
    summary = await assistant.escalate_summary(db, user, hist)
    last = next((h["text"] for h in reversed(hist) if h.get("role") == "user"), "")
    body = f"🤖 ارجاع از دستیار هوشمند\n\n📝 خلاصه:\n{summary}\n\n💬 آخرین پیام کاربر:\n{last}"
    r = await support.send(call.bot, db, user, body, via="ai", photo=photo)
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await call.message.answer(texts.ASSIST_ESCALATED.format(code=r.get("code") or "-"),
                              reply_markup=keyboards.tickets_kb())


# ═══════════════════ پیشنهاد پلن ═══════════════════

@router.callback_query(F.data.in_({"aip", "aip:new"}))
async def cb_recommend(call: CallbackQuery, db: Database, user: dict) -> None:
    if not assistant.ready("ai_recommend"):
        return await call.answer(texts.ASSIST_DOWN, show_alert=True)
    force = call.data == "aip:new"
    if force and not await assistant.allowed(db, user["id"]):
        return await call.answer(texts.ASSIST_LIMIT, show_alert=True)
    await call.answer(texts.ASSIST_THINKING)
    try:
        rec = await assistant.recommend(db, user, force=force)
    except AIError as exc:
        log.info("پیشنهاد پلن نشد: %s", exc)
        return await call.message.answer(texts.ASSIST_DOWN, reply_markup=keyboards.back_menu())
    plan = await db.get_plan(rec["plan_id"]) if rec.get("plan_id") else None
    await call.message.answer(
        texts.ASSIST_REC.format(body=assistant.to_html(rec["text"])),
        reply_markup=keyboards.assist_recommend_kb(plan if plan and plan.get("is_active") else None),
    )


# ═══════════════════ دستیار فروشگاه ═══════════════════

@router.callback_query(F.data == "ais")
async def cb_shop_help(call: CallbackQuery, state: FSMContext) -> None:
    if not assistant.ready("ai_shop_help"):
        return await call.answer(texts.ASSIST_DOWN, show_alert=True)
    await state.set_state(Assist.shop_query)
    await edit_or_send(call.message, texts.ASSIST_SHOP_ASK, keyboards.back_to_shop_kb())
    await call.answer()


@router.message(Assist.shop_query, F.text)
async def msg_shop_help(message: Message, db: Database, state: FSMContext, user: dict) -> None:
    from app.handlers.ai import _items

    if (message.text or "").startswith("/"):
        return
    if not await assistant.allowed(db, user["id"]):
        await state.clear()
        return await message.answer(texts.ASSIST_LIMIT, reply_markup=keyboards.back_to_shop_kb())
    await _typing(message)
    items = await _items(db)
    if not items:
        await state.clear()
        return await message.answer(texts.AI_PROVIDER_DOWN, reply_markup=keyboards.back_to_shop_kb())
    try:
        r = await assistant.shop_pick(db, user, message.text or "", items)
    except AIError as exc:
        log.info("دستیار فروشگاه جواب نداد: %s", exc)
        return await message.answer(texts.ASSIST_DOWN, reply_markup=keyboards.back_to_shop_kb())
    await state.clear()
    by_id = {str(i["id"]): i for i in items}
    picks = [by_id[i] for i in r["ids"] if i in by_id]
    body = assistant.to_html(r["text"]) or texts.ASSIST_SHOP_NONE
    if not picks:
        body = texts.ASSIST_SHOP_NONE + ("\n\n" + assistant.to_html(r["text"]) if r["text"] else "")
    await message.answer(texts.ASSIST_SHOP_RESULT.format(body=body), reply_markup=keyboards.assist_shop_kb(picks))


# ═══════════════════ ادمین: پیش نویس جواب تیکت ═══════════════════

@router.callback_query(F.data.startswith("aid:"))
async def cb_ticket_draft(call: CallbackQuery, db: Database) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    user_tg = int(call.data.split(":")[1])
    target = await db.get_user_by_tg(user_tg)
    if not target:
        return await call.answer("کاربر پیدا نشد", show_alert=True)
    await call.answer("✨ در حال نوشتن پیش نویس...")
    try:
        with i18n.using(i18n.lang_of(target)):
            draft = await assistant.ticket_draft(db, target)
    except AIError as exc:
        return await call.message.answer(f"پیش نویس ساخته نشد: {esc(str(exc))}")
    msg = await call.message.answer(
        "✨ <b>پیش نویس جواب</b> برای "
        f"{esc(assistant.display_name(target))} (<code>{user_tg}</code>)\n\n"
        f"{esc(draft)}\n\n"
        "<i>✏️ برای ویرایش: روی همین پیام ریپلای کن و متن نهایی رو بفرست.</i>",
        reply_markup=keyboards.ticket_draft_kb(user_tg),
    )
    # ریپلای روی پیش نویس = جواب ویرایش شده به همان کاربر
    await db.save_support_link(call.from_user.id, msg.message_id, user_tg)
    await db.ai_cache_set(f"draft:{call.from_user.id}:{msg.message_id}", draft)


@router.callback_query(F.data.startswith("aids:"))
async def cb_ticket_draft_send(call: CallbackQuery, db: Database) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    user_tg = int(call.data.split(":")[1])
    draft = await db.ai_cache_get(f"draft:{call.from_user.id}:{call.message.message_id}", 7 * 86400)
    target = await db.get_user_by_tg(user_tg)
    if not draft or not target:
        return await call.answer("پیش نویس پیدا نشد؛ دوباره بساز.", show_alert=True)
    reply_to = await db.last_user_msg_id(target["id"])
    body = esc(draft)
    try:
        with i18n.using(i18n.lang_of(target)):
            text = texts.SUPPORT_REPLY_GOT.format(body=body)
        try:
            await call.bot.send_message(user_tg, text, reply_to_message_id=reply_to)
        except Exception:  # noqa: BLE001
            await call.bot.send_message(user_tg, text)
    except Exception as exc:  # noqa: BLE001
        return await call.answer(f"ارسال نشد: {exc}"[:190], show_alert=True)
    open_ticket = await db.open_thread(target["id"])
    if open_ticket and (open_ticket.get("status") or "open") == "open":
        await db.set_ticket_status(open_ticket["id"], "answered")
    await db.add_ticket(target["id"], "out", body=body, admin_id=call.from_user.id,
                        thread_id=int(open_ticket["id"]) if open_ticket else None)
    await db.ai_cache_del(f"draft:{call.from_user.id}:{call.message.message_id}")
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await call.answer("📤 ارسال شد")


# ═══════════════════ ادمین: بررسی رسید ═══════════════════

@router.callback_query(F.data.startswith("aircp:"))
async def cb_receipt_check(call: CallbackQuery, db: Database) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    txn = await db.get_transaction(int(call.data.split(":")[1]))
    if not txn or not txn.get("receipt_file_id"):
        return await call.answer("رسیدی برای بررسی نیست", show_alert=True)
    await call.answer("🔍 در حال خواندن رسید...")
    try:
        image = await _download(call.bot, txn["receipt_file_id"])
        r = await assistant.receipt_check(db, txn, image)
    except AIError as exc:
        return await call.message.answer(f"بررسی هوشمند نشد: {esc(str(exc))}")
    except Exception:  # noqa: BLE001
        log.warning("بررسی رسید شکست خورد", exc_info=True)
        return await call.message.answer("بررسی هوشمند نشد؛ عکس رسید خوانده نشد.")
    await call.message.reply(assistant.receipt_html(r))


# ═══════════════════ ادمین: تنظیمات دستیار ═══════════════════

async def _admin_text(db: Database) -> str:
    from datetime import datetime

    from app.config import config
    from app.utils import TZ

    on = assistant.configured()
    usage = await db.ai_usage(datetime.now(TZ).date().isoformat())
    total = sum(v["n"] for v in usage.values())
    bad = sum(v["bad"] for v in usage.values())
    limit = await db.get_setting(assistant.DAILY_LIMIT_KEY, str(assistant.DAILY_LIMIT_DEFAULT))
    from app import features

    feats = "\n".join(
        f"{'🟢' if features.is_on(k) else '⚪️'} {features.FEATURES[k][0]}"
        for k in ("ai_support", "ai_recommend", "ai_shop_help", "ai_names", "ai_report")
    )
    return (
        "🧠 <b>دستیار هوشمند</b>\n\n"
        + ("🟢 کلید تنظیم شده" if on else "🔴 کلید تنظیم نشده — AI_API_KEY را در فایل .env هاست بگذار و ری استارت کن")
        + f"\n🌐 <code>{esc(config.ai_base_url)}</code>\n"
        f"🔢 سقف روزانه هر کاربر: {limit}\n"
        f"📈 درخواست های امروز: {total}" + (f" (ناموفق {bad})" if bad else "") + "\n\n"
        + feats
        + "\n\n<i>بررسی رسید و پیش نویس تیکت برای ادمین ها همیشه روشن است.</i>"
    )


@router.callback_query(F.data == "aia")
async def cb_admin_assist(call: CallbackQuery, db: Database) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    await edit_or_send(call.message, await _admin_text(db), keyboards.admin_assist_kb(assistant.configured()))
    await call.answer()


@router.callback_query(F.data.in_({"aia:test", "aia:rep", "aia:names"}))
async def cb_admin_assist_action(call: CallbackQuery, db: Database) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    action = call.data.split(":")[1]
    await call.answer("⏳ ...")
    try:
        if action == "test":
            import time

            t0 = time.monotonic()
            out = await assistant.ask("Reply with exactly: OK", kind="test", db=db, timeout=30)
            await call.message.answer(f"🟢 وب سرویس جواب داد ({time.monotonic() - t0:.1f} ثانیه):\n<code>{esc(out[:200])}</code>")
        elif action == "rep":
            await call.message.answer(await assistant.daily_report(db))
        else:
            n = await assistant.guess_names(db, limit=25)
            await call.message.answer(f"👤 نام {n} کاربر حدس زده شد." if n else "کاربری برای حدس نام نماند (یا بخش خاموش است).")
    except AIError as exc:
        await call.message.answer(f"🔴 خطا: {esc(str(exc))} ({exc.code})")
