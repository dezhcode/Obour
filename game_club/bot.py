"""ربات تلگرام Game Club.

روی همان event loop عبور ساخته می شود (app.runtime) ولی Bot، Dispatcher
و دیتابیس خودش را دارد. کار اصلی ربات باز کردن مینی اپ است:
  /start            خوش آمد + دکمه ورود
  /start ludo_CODE  لینک دعوت دوست: دکمه مستقیم به همان میز
  /start obour      آمده از کارت Game Club در مینی اپ عبور
  /points           موجودی امتیاز
  /help             قوانین کوتاه
ادمین ها (ADMIN_IDS عبور):
  /gcstats                  آمار امروز و همه
  /gcpoints <tg_id> <مقدار>  افزودن یا کسر امتیاز (منفی = کسر)
  /gcclose <match_id>       بستن میز گیرکرده و برگرداندن ورودی ها
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
                from . import service

                bot = self.bot

                async def notify(tg: int, text: str, page: str) -> None:
                    await bot.send_message(tg, text, reply_markup=open_kb(page, "باز کردن Game Club"))

                service.notifier = notify
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
    if not u:
        return "بازیکن"
    return " ".join(x for x in (u.first_name, u.last_name) if x).strip() or u.username or "بازیکن"


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


# ---------- ادمین ----------
def _is_admin(message: Message) -> bool:
    from app.config import config as obour_cfg

    return bool(message.from_user and message.from_user.id in obour_cfg.admin_ids)


@router.message(Command("gcstats"))
async def on_stats(message: Message, gdb: GCDatabase) -> None:
    if not _is_admin(message):
        return
    import time as _t

    day = await gdb.stats(int(_t.time()) - 86400)
    allt = await gdb.stats(0)
    f = lambda v: f"{int(v):,}"  # noqa: E731
    await message.answer(
        "<b>Game Club</b>\n"
        f"بازیکن: {f(allt['players'])} · امتیاز در گردش: {f(allt['points'])}\n"
        f"الان: {f(allt['playing'])} میز در بازی، {f(allt['lobby'])} میز دعوت، {f(allt['queue'])} نفر در صف\n\n"
        "<b>۲۴ ساعت گذشته</b>\n"
        f"بازی تمام شده: {f(day['games'])}\n"
        f"شارژ: {f(day['charge'])} امتیاز ({f(day['charge'] * gc.point_toman)} تومان)\n"
        f"ورودی: {f(day['entry'])} · جایزه: {f(day['prize'])}\n"
        f"خرج در عبور: {f(day['shop'])}")


@router.message(Command("gcpoints"))
async def on_points_admin(message: Message, command: CommandObject, gdb: GCDatabase) -> None:
    if not _is_admin(message):
        return
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].lstrip("-").isdigit() or int(parts[1]) == 0:
        await message.answer("شکل درست: <code>/gcpoints 123456789 500</code> (منفی برای کسر)")
        return
    tg, amount = int(parts[0]), int(parts[1])
    if not await gdb.get_player(tg):
        await message.answer("این کاربر هنوز Game Club را باز نکرده.")
        return
    from . import service

    idem = f"admin:{message.chat.id}:{message.message_id}"
    ok = (await service.earn(gdb, tg, amount, "admin", "تنظیم دستی پشتیبانی", "admin", idem) if amount > 0
          else await service.spend(gdb, tg, -amount, "admin", "تنظیم دستی پشتیبانی", "admin", idem))
    p = await gdb.get_player(tg)
    await message.answer(("انجام شد" if ok else "انجام نشد (موجودی کافی نیست؟)") + f". موجودی فعلی: {p['points']:,}")
    log.warning("ادمین %s امتیاز %s را %+d کرد (ok=%s)", message.from_user.id, tg, amount, ok)


@router.message(Command("gcclose"))
async def on_close(message: Message, command: CommandObject, gdb: GCDatabase) -> None:
    if not _is_admin(message):
        return
    mid = (command.args or "").strip()
    from . import service

    try:
        r = await service.admin_close(gdb, mid)
    except service.GCError:
        await message.answer("میز باز با این شناسه پیدا نشد.")
        return
    await message.answer(f"میز {mid} بسته شد؛ {r['refunded']:,} امتیاز ورودی به بازیکن ها برگشت.")


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
