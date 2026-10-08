"""ربات تلگرام Game Club.

روی همان event loop عبور ساخته می شود (app.runtime) ولی Bot، Dispatcher
و دیتابیس خودش را دارد. کار اصلی ربات باز کردن مینی اپ است:
  /start            خوش آمد + دکمه ورود
  /start ludo_CODE  لینک دعوت دوست: دکمه مستقیم به همان میز
  /start obour      آمده از کارت Game Club در مینی اپ عبور
  /points           موجودی امتیاز
  /help             قوانین کوتاه
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from .config import gc
from .db import GCDatabase

log = logging.getLogger("gameclub.bot")
router = Router(name="gameclub")


class GCRuntime:
    """اجزای Game Club روی loop عبور. یک بار ساخته می شود."""

    def __init__(self) -> None:
        self.db: GCDatabase | None = None
        self.bot: Bot | None = None
        self.dp: Dispatcher | None = None
        self._init_lock = asyncio.Lock()

    async def ensure(self) -> "GCRuntime":
        if self.db is not None:
            return self
        async with self._init_lock:
            if self.db is not None:
                return self
            db = GCDatabase(gc.db_path)
            await db.connect()
            if gc.token:
                from app.runtime import make_session

                self.bot = Bot(token=gc.token, session=make_session(),
                               default=DefaultBotProperties(parse_mode=ParseMode.HTML))
                dp = Dispatcher()
                dp["gdb"] = db
                dp.include_router(router)
                self.dp = dp
            self.db = db
            log.info("Game Club آماده شد (db=%s)", gc.db_path)
        return self


gcrt = GCRuntime()


def open_kb(page: str = "", text: str = "ورود به Game Club") -> InlineKeyboardMarkup | None:
    if not gc.webapp_url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=text, web_app=WebAppInfo(url=gc.webapp_url + page))]])


def _name(message: Message) -> str:
    u = message.from_user
    return (u.first_name or u.username or "بازیکن") if u else "بازیکن"


@router.message(CommandStart())
async def on_start(message: Message, command: CommandObject, gdb: GCDatabase) -> None:
    u = message.from_user
    if not u:
        return
    await gdb.player(u.id, _name(message), u.username)
    arg = (command.args or "").strip()
    if arg.startswith("ludo_"):
        code = "".join(ch for ch in arg[5:].upper() if ch.isalnum())[:12]
        m = await gdb.match_by_invite(code)
        if not m or m["status"] != "lobby":
            await message.answer("این میز منچ دیگر باز نیست. خودت یک میز تازه بساز 👇",
                                 reply_markup=open_kb("ludo-lobby.html", "میز تازهٔ منچ"))
            return
        mode = "با امتیاز (ورودی " + f"{m['cfg']['entry']:,}" + ")" if m["cfg"]["mode"] == "stake" else "آزاد"
        await message.answer(f"دوستت تو را به یک دست <b>منچ {mode}</b> دعوت کرده.\nبزن تا کنارش بنشینی:",
                             reply_markup=open_kb(f"ludo-lobby.html?join={code}", "نشستن سر میز"))
        return
    hello = ("به <b>Game Club</b> خوش آمدی!\n\n"
             "منچ بازی کن، با دوستت یا با ناشناس. در بازی با امتیاز برنده همهٔ ورودی‌ها را می‌برد "
             "و امتیازت را می‌توانی در عبور خرج کنی: کانفیگ، تمدید و اشتراک هوش مصنوعی.")
    if arg == "obour":
        hello += "\n\nحساب عبورت با همین تلگرام وصل است؛ شارژ از کیف پول عبور فوری است."
    await message.answer(hello, reply_markup=open_kb())


@router.message(Command("points"))
async def on_points(message: Message, gdb: GCDatabase) -> None:
    u = message.from_user
    if not u:
        return
    p = await gdb.player(u.id, _name(message), u.username)
    await message.answer(f"موجودی امتیازت: <b>{p['points']:,}</b>\nبرد: {p['wins']:,} از {p['games']:,} بازی",
                         reply_markup=open_kb("wallet.html", "کیف امتیاز"))


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(
        "<b>قوانین کوتاه</b>\n"
        "• بازی آزاد: بدون امتیاز، برای سرگرمی\n"
        "• بازی با امتیاز: همه ورودی یکسان می‌دهند، برنده همه را می‌برد\n"
        "• تاس روی سرور ریخته می‌شود؛ هر نوبت ۲۰ ثانیه وقت داری\n"
        "• امتیاز فقط در خدمات عبور خرج می‌شود و به پول نقد برنمی‌گردد",
        reply_markup=open_kb("help.html", "راهنمای کامل"))


@router.message(F.text)
async def on_text(message: Message) -> None:
    await message.answer("برای بازی، Game Club را باز کن 👇", reply_markup=open_kb())


COMMANDS = [BotCommand(command="start", description="ورود به Game Club"),
            BotCommand(command="points", description="موجودی امتیاز"),
            BotCommand(command="help", description="قوانین")]


async def setup(bot: Bot) -> str:
    """وبهوک، فهرست دستورها و دکمه منو. از مسیر /gc/setwebhook صدا زده می شود."""
    if not gc.webhook_secret:
        raise RuntimeError("GAME_CLUB_WEBHOOK_SECRET در .env تنظیم نشده")
    await bot.set_webhook(url=gc.webhook_url, secret_token=gc.webhook_secret,
                          drop_pending_updates=True, allowed_updates=["message"])
    await bot.set_my_commands(COMMANDS)
    note = "menu: off (https لازم است)"
    if gc.webapp_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="بازی", web_app=WebAppInfo(url=gc.webapp_url)))
        note = f"menu: {gc.webapp_url}"
    me = await bot.get_me()
    return f"game club webhook set: {gc.webhook_url}\nbot: @{me.username}\n{note}"
