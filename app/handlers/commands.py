"""هندلر دستورهای اسلشی (/buy، /wallet، ...).

چرا یک روتر جدا و چرا اول از همه ثبت می شود؟
اگر کاربر وسط یک جریان باشد (مثلا منتظر وارد کردن مبلغ شارژ یا کد
تخفیف)، هندلر همان جریان هر متنی را می گیرد - از جمله دستورها. نتیجه
این می شد که کاربر گیر بیفتد و /start هم جوابش ندهد. این روتر قبل از
بقیه ثبت می شود و اول از همه state را پاک می کند، پس دستورها همیشه راه
خروج مطمئنی هستند.
"""
from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app import join, keyboards, polls, texts
from app.config import config
from app.db import Database
from app.handlers.start import show_menu

log = logging.getLogger("obour.commands")
router = Router(name="commands")


@router.message(CommandStart())
async def cmd_start(
    message: Message, command: CommandObject, db: Database, state: FSMContext, user: dict
) -> None:
    """شروع - با پشتیبانی از لینک عمیق.

    دکمه های زیر پست کانال نمی توانند callback باشند (کاربر در کانال
    می ماند و محتوا آنجا عوض می شود)، پس لینک عمیق می شوند:
    t.me/<bot>?start=page_loc | plan_12 | poll_3
    اینجا payload خوانده و همان صفحه در چت خصوصی باز می شود.
    """
    await state.clear()
    payload = (command.args or "").strip()

    if payload.startswith("page_"):
        target = payload[5:].replace("-", ":")
        return await _open_page(message, db, user, target)
    if payload.startswith("plan_") and payload[5:].isdigit():
        plan = await db.get_plan(int(payload[5:]))
        if plan:
            from app.handlers.buy import show_plan_from_start

            return await show_plan_from_start(message, db, user, plan)
    if payload.startswith("poll_") and payload[5:].isdigit():
        text, markup = await polls.view(db, int(payload[5:]), user["id"])
        if text:
            return await message.answer(text, reply_markup=markup)

    await show_menu(message, user)


async def _open_page(message: Message, db: Database, user: dict, target: str) -> None:
    """باز کردن یکی از صفحه های ربات از روی لینک عمیق."""
    if target == "buy":
        return await _shop(message, db, user)
    if target == "loc":
        photo = await db.get_setting("locations_photo", "")
        if not photo and config.webhook_base_url:
            photo = f"{config.webhook_base_url.rstrip('/')}/img/locations.jpg"
        if photo.startswith(("http://", "https://")):
            from aiogram.types import LinkPreviewOptions

            return await message.answer(
                f'<a href="{photo}">\u2060</a>' + texts.LOCATIONS,
                reply_markup=keyboards.locations_kb(),
                link_preview_options=LinkPreviewOptions(
                    url=photo, prefer_large_media=True, show_above_text=True
                ),
            )
        return await message.answer(
            texts.LOCATIONS, reply_markup=keyboards.locations_kb()
        )
    if target == "svc":
        services = await db.user_services(user["id"])
        if not services:
            return await message.answer(
                texts.SERVICES_EMPTY, reply_markup=keyboards.back_menu()
            )
        return await message.answer(
            texts.SERVICES_LIST.format(count=len(services)),
            reply_markup=keyboards.services_kb(services),
        )
    if target == "wal":
        min_charge = int(await db.get_setting("min_charge", "50000"))
        return await message.answer(
            texts.WALLET.format(
                balance=f"{user['balance']:,}", min_charge=f"{min_charge:,}"
            ),
            reply_markup=keyboards.wallet_amounts(),
        )
    # بقیه صفحه ها: منوی اصلی (امن ترین حالت)
    await show_menu(message, user)


async def _shop(message: Message, db: Database, user: dict) -> None:
    cats = await db.shop_categories()
    if not cats:
        return await message.answer(
            "فعلا پلنی برای فروش فعال نیست.", reply_markup=keyboards.back_menu()
        )
    await message.answer(
        texts.SHOP.format(balance=f"{user['balance']:,}"),
        reply_markup=keyboards.plan_categories_kb(cats),
    )


@router.message(Command("buy"))
async def cmd_buy(message: Message, db: Database, state: FSMContext, user: dict) -> None:
    await state.clear()
    cats = await db.shop_categories()
    if not cats:
        return await message.answer(
            "فعلا پلنی برای فروش فعال نیست. کمی صبر کن یا به پشتیبانی خبر بده.",
            reply_markup=keyboards.back_menu(),
        )
    await message.answer(
        texts.SHOP.format(balance=f"{user['balance']:,}"),
        reply_markup=keyboards.plan_categories_kb(cats),
    )


@router.message(Command("account"))
async def cmd_account(
    message: Message, db: Database, state: FSMContext, user: dict
) -> None:
    await state.clear()
    services = await db.user_services(user["id"])
    if not services:
        return await message.answer(
            texts.SERVICES_EMPTY, reply_markup=keyboards.back_menu()
        )
    await message.answer(
        texts.SERVICES_LIST.format(count=len(services)),
        reply_markup=keyboards.services_kb(services),
    )


@router.message(Command("wallet"))
async def cmd_wallet(
    message: Message, db: Database, state: FSMContext, user: dict
) -> None:
    await state.clear()
    min_charge = int(await db.get_setting("min_charge", "50000"))
    await message.answer(
        texts.WALLET.format(
            balance=f"{user['balance']:,}", min_charge=f"{min_charge:,}"
        ),
        reply_markup=keyboards.wallet_amounts(),
    )


@router.message(Command("test"))
async def cmd_test(message: Message, state: FSMContext, user: dict) -> None:
    await state.clear()
    if not config.trial_enabled:
        return await message.answer(
            "تست رایگان فعلا غیرفعاله.", reply_markup=keyboards.back_menu()
        )
    if user["free_trial_used"]:
        return await message.answer(
            texts.TRIAL_USED, reply_markup=keyboards.back_menu()
        )
    # همان گیت عضویت کانال که روی دکمه تست رایگان هست
    if join.required():
        missing = await join.missing(message.bot, message.from_user.id)
        if missing:
            return await message.answer(
                texts.JOIN_REQUIRED, reply_markup=keyboards.join_kb(missing, "trial")
            )
    await message.answer(
        texts.TRIAL_OFFER.format(size=config.trial_mb, days=config.trial_days),
        reply_markup=keyboards.trial_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.GUIDE_INTRO, reply_markup=keyboards.guide_kb())


@router.message(Command("support"))
async def cmd_support(
    message: Message, db: Database, state: FSMContext, user: dict
) -> None:
    await state.clear()
    tickets = await db.user_tickets(user["id"], limit=1)
    unread = await db.unread_replies(user["id"])
    note = texts.SUPPORT_UNREAD.format(n=unread) if unread else texts.SUPPORT_NO_UNREAD
    await message.answer(
        texts.SUPPORT.format(unread=note),
        reply_markup=keyboards.support_kb(bool(tickets)),
    )
