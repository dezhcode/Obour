"""ربات تلگرام Game Club.

روی همان event loop عبور ساخته می شود (app.runtime) ولی Bot، Dispatcher
و دیتابیس خودش را دارد. کار اصلی ربات باز کردن مینی اپ است:
  /start            خوش آمد + دکمه ورود
  /start ludo_CODE  لینک دعوت دوست: دکمه مستقیم به همان میز (حکم: hokm_CODE، فوتبال: football_CODE)
  /start obour      آمده از کارت Game Club در مینی اپ عبور
  /points           موجودی امتیاز
  /help             قوانین کوتاه
در گروه ها (groups.py): /hokm، /ludo، /football یا /play کارت تنظیم میز می فرستد؛ دکمه ها داخل خود پیام اند (پیام غنی).
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
    CallbackQuery,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from . import emoji as emo
from . import style as st
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

                @dp.update.outer_middleware()
                async def _sync(handler, event, data):  # noqa: ANN001, ANN202
                    # تنظیمات پنل و ایموجی های پریمیوم (هر ۱۰ ثانیه از دیتابیس)
                    from . import admin as _adm

                    try:
                        await _adm.sync_settings(db)
                    except Exception:  # noqa: BLE001
                        log.debug("همگام سازی تنظیمات نشد", exc_info=True)
                    return await handler(event, data)

                from . import groups

                dp.include_router(groups.router)     # اول گروه ها؛ بعد دستورهای پیوی
                dp.include_router(router)
                groups.install(self.bot, db)
                asyncio.get_running_loop().create_task(_heal_webhook(self.bot))
                self.dp = dp
                from . import service

                bot = self.bot

                async def notify(tg: int, text: str, page: str, key: str = "") -> None:
                    icon, sub, btn = NOTICE.get(key, ("bell", "اعلان", "باز کردن Game Club"))
                    body = st.to_html(st.frame(icon, "Game Club", sub, [st.Raw(text)]))
                    await bot.send_message(tg, body, reply_markup=open_kb(page, btn, "brand"))

                service.notifier = notify
            self.db = db
            log.info("Game Club آماده شد (db=%s)", gc.db_path)
        return self


gcrt = GCRuntime()


# نوع اعلان -> (ایموجی، زیرعنوان، متن دکمه)
NOTICE = {
    "turn": ("turn", "نوبت توئه", "برگرد سر بازی"),
    "join": ("seat", "یکی سر میزت نشست", "برو سر میز"),
    "over": ("trophy", "نتیجهٔ بازی", "باز کردن Game Club"),
    "freq": ("friend", "درخواست دوستی", "دیدن درخواست"),
    "facc": ("friend", "دوستی تازه", "دیدن دوستان"),
    "dm": ("chat", "پیام تازه", "خواندن پیام"),
    "dminv": ("link", "دعوت به بازی", "نشستن سر میز"),
}


def open_kb(page: str = "", text: str = "ورود به Game Club", icon: str | None = "brand") -> InlineKeyboardMarkup | None:
    """دکمهٔ باز کردن مینی اپ؛ ایموجی پریمیوم (اگر تنظیم شده) آیکن کنار متن دکمه است."""
    if not gc.webapp_url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        st.kb_button(text, icon, web_app=WebAppInfo(url=gc.webapp_url + page))]])


def _name(message: Message) -> str:
    u = message.from_user
    if not u:
        return "بازیکن"
    return " ".join(x for x in (u.first_name, u.last_name) if x).strip() or u.username or "بازیکن"


def _h(icon: str, title, sub=None, lines=(), foot=None) -> str:  # noqa: ANN001
    return st.to_html(st.frame(icon, title, sub, lines, foot))


GAME_FA = {"ludo": "منچ", "hokm": "حکم", "football": "فوتبال"}


@router.message(CommandStart())
async def on_start(message: Message, command: CommandObject, gdb: GCDatabase) -> None:
    u = message.from_user
    if not u:
        return
    me = await gdb.player(u.id, _name(message), u.username)
    if me.get("banned"):
        await message.answer(_h("ban", "Game Club", "حساب مسدود", [
            "حساب تو در Game Club مسدود شده."], foot=(None, None, "اگه فکر می‌کنی اشتباه شده، به پشتیبانی عبور پیام بده.")))
        return
    arg = (command.args or "").strip()
    game = arg.split("_", 1)[0]
    if game in GAME_FA and "_" in arg:
        name = GAME_FA[game]
        code = "".join(ch for ch in arg.split("_", 1)[1].upper() if ch.isalnum())[:12]
        m = await gdb.match_by_invite(code)
        if not m or m["status"] != "lobby":
            await message.answer(_h(game, f"میز {name}", "دیگه باز نیست", [
                "این میز بسته شده یا بازی‌اش شروع شده."], foot=(None, None, "خودت یه میز تازه بساز 👇")),
                reply_markup=open_kb(f"{game}-lobby.html", f"میز تازهٔ {name}", "new"))
            return
        stake = m["cfg"]["mode"] == "stake"
        who = {"hokm": "یار خودش توی حکم", "football": "یه بازی فوتبال", "ludo": "یه دست منچ"}[game]
        await message.answer(_h(game, f"میز {name}", "دعوت دوستت", [
            f"دوستت تو رو به {who} دعوت کرده."],
            foot=("coin", "نوع میز", ["با امتیاز · ورودی ", st.num(m["cfg"]["entry"])] if stake else "آزاد · بدون امتیاز")),
            reply_markup=open_kb(f"{game}-lobby.html?join={code}", "نشستن سر میز", "seat"))
        return
    lines = [["سلام ", st.iso(me.get("name") or "بازیکن"), "، بازی با منه."], "",
             [st.E("hokm"), " حکم  ", st.E("ludo"), " منچ  ", st.E("football"), " فوتبال"],
             "با دوستات یا با ناشناس؛ توی گروه هم با /hokm میز بساز."]
    if arg == "obour":
        lines += ["", "حساب عبورت با همین تلگرام وصله؛ شارژ از کیف پول عبور فوریه."]
    await message.answer(_h("hello", "Game Club", "منوی اصلی", lines, foot=("coin", "امتیاز", [st.num(me["points"]), " امتیاز"])),
                         reply_markup=open_kb())


@router.message(Command("points"))
async def on_points(message: Message, gdb: GCDatabase) -> None:
    u = message.from_user
    if not u:
        return
    p = await gdb.player(u.id, _name(message), u.username)
    await message.answer(_h("coin", "کیف امتیاز", "Game Club", [
        [st.E("trophy"), " برد: ", st.num(p["wins"]), " از ", st.num(p["games"]), " بازی"]],
        foot=("coin", "موجودی", [st.num(p["points"]), " امتیاز"])),
        reply_markup=open_kb("shop.html", "کیف امتیاز", "coin"))


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(_h("help", "قوانین کوتاه", "Game Club", [
        "• بازی آزاد: بدون امتیاز، برای سرگرمی",
        "• بازی با امتیاز: همه ورودی یکسان می‌دن، برنده همه رو می‌بره",
        "• تاس و ورق روی سرور پخش می‌شه؛ هر نوبت ۲۰ ثانیه وقت داری",
        "• توی گروه: /hokm، /ludo یا /football",
    ], foot=(None, None, "امتیاز فقط توی خدمات عبور خرج می‌شه و نقد نمی‌شه.")),
        reply_markup=open_kb("help.html", "راهنمای کامل", "help"))


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
    n = st.num
    await message.answer(_h("chart", "آمار Game Club", "امروز و کل", [
        ["بازیکن: ", n(allt["players"]), " · امتیاز در گردش: ", n(allt["points"])],
        ["الان: ", n(allt["playing"]), " میز در بازی، ", n(allt["lobby"]), " میز دعوت، ", n(allt["queue"]), " نفر در صف"], "",
        [st.B("۲۴ ساعت گذشته")],
        ["بازی تمام شده: ", n(day["games"])],
        ["شارژ: ", n(day["charge"]), " امتیاز (", n(day["charge"] * gc.point_toman), " تومان)"],
        ["ورودی: ", n(day["entry"]), " · جایزه: ", n(day["prize"])],
    ], foot=("coin", "خرج در عبور", [n(day["shop"]), " امتیاز"])))


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
    await message.answer(_h("ok" if ok else "warn", "تغییر امتیاز", st.iso(tg), [
        "انجام شد." if ok else "انجام نشد (موجودی کافی نیست؟)"], foot=("coin", "موجودی فعلی", [st.num(p["points"]), " امتیاز"])))
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
    await message.answer(_h("ok", "میز بسته شد", st.iso(mid), [], foot=("coin", "ورودی برگشتی", [st.num(r["refunded"]), " امتیاز"])))


@router.message(Command("admin"))
async def on_admin(message: Message) -> None:
    """پنل مدیریت Game Club (فقط ادمین های عبور)."""
    if not _is_admin(message):
        await on_text(message)
        return
    kb = open_kb("admin.html", "پنل مدیریت Game Club", "gear")
    await message.answer(_h("gear", "پنل مدیریت", "Game Club", [
        "کاربران، میزها، تراکنش‌ها، پیام همگانی، ایموجی‌ها و تنظیمات."],
        foot=("brand", "ایموجی پریمیوم", "/gcemoji")) if kb else "آدرس https مینی اپ تنظیم نشده.", reply_markup=kb)


# ---------- پیام همگانی (فقط از ربات؛ مینی اپ فقط آمار را نشان می دهد) ----------
# ۱) پیام را (متن، عکس، ویدیو... با ایموجی پریمیوم) در ربات بفرست و رویش ریپلای کن: /gcbc
# ۲) در کارت کنترل: گیرنده ها، دکمه ها (تا ۳ تا، با ایموجی پریمیوم)، نسخهٔ آزمایشی و ارسال با تایید
# پیش نویس در دیتابیس است (status=draft)؛ پس اگر پروسه عوض شد چیزی گم نمی شود.
PAGE_ALIAS = {"خانه": "", "home": "", "حکم": "hokm-lobby.html", "منچ": "ludo-lobby.html", "فوتبال": "football-lobby.html",
              "بازی‌ها": "games.html", "بازی ها": "games.html", "بازیها": "games.html", "دوستان": "friends.html",
              "پروفایل": "profile.html", "فروشگاه": "shop.html", "کیف": "shop.html"}
PAGE_FA = {"": "خانه", "hokm-lobby.html": "حکم", "ludo-lobby.html": "منچ", "football-lobby.html": "فوتبال",
           "games.html": "بازی‌ها", "friends.html": "دوستان", "profile.html": "پروفایل", "shop.html": "فروشگاه"}
_BC_WAIT = "bcwait:"   # setting: ادمین دارد دکمه های کدام پیش نویس را می فرستد


def _ib(text: str, data: str, key: str | None = None) -> InlineKeyboardButton:
    return st.kb_button(text, key, callback_data=data)


async def _bc_panel(gdb: GCDatabase, bid: int, admin_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    from . import admin

    b = await gdb.bc_get(bid)
    if not b or b["status"] != "draft":
        return _h("megaphone", "پیام همگانی", f"شماره {bid}", ["این پیش‌نویس دیگه فعال نیست."]), None
    n = await gdb.bc_count(admin._target(b["target"], admin_id))
    btns = admin.parse_buttons(b["button"])
    lines = ["پیامی که روش ریپلای کردی همون‌طور برای همه می‌ره؛ با عکس، متن و ایموجی‌های پریمیومش.", "",
             [st.E("link"), " ", st.B("دکمه‌ها")]]
    lines += [["• ", st.Raw(emo.html_of(k) + " ") if k in emo.CATALOG else "", label, " ← ", PAGE_FA.get(page, "خانه")]
              for page, label, k in btns] or ["بدون دکمه"]
    text = _h("megaphone", "پیام همگانی", f"پیش‌نویس {bid}", lines,
              foot=("users", "گیرنده‌ها", [admin.target_label(b["target"]), " · ", st.num(n), " نفر"]))
    tk = [_ib(("✅ " if b["target"] == k else "") + t, f"bc:t:{bid}:{k}") for k, t in admin.TARGET_KEYS]
    rows = [tk[:3], tk[3:6], tk[6:],
            [_ib("✏️ دکمه‌ها", f"bc:b:{bid}"), _ib("🧪 نسخهٔ آزمایشی", f"bc:test:{bid}")],
            [_ib(f"ارسال برای {n:,} نفر", f"bc:send:{bid}", "megaphone")],
            [_ib("لغو پیش‌نویس", f"bc:del:{bid}", "cancel")]]
    return text, InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r])


@router.message(Command("gcbc"))
async def on_broadcast(message: Message, gdb: GCDatabase) -> None:
    """پیام همگانی با هر نوع محتوا: روی یک پیام (عکس، ویدیو، متن...) ریپلای کن و بنویس /gcbc"""
    if not _is_admin(message):
        return
    src = message.reply_to_message
    if not src:
        await message.answer(_h("megaphone", "پیام همگانی", "از همین ربات", [
            "۱. پیامت رو همین‌جا بفرست؛ متن، عکس، ویدیو، با ایموجی پریمیوم",
            "۲. روی همون پیام ریپلای کن و بنویس /gcbc",
            "۳. گیرنده‌ها و دکمه‌ها رو انتخاب کن، آزمایشی ببین و بفرست"],
            foot=("chart", "آمار", "پیشرفت و آمار ارسال‌ها توی پنل مدیریت")))
        return
    days = (message.text or "").split()[1:2]
    target = {"7": "active7", "30": "active30"}.get(days[0] if days else "", "all")
    bid = await gdb.bc_draft(message.from_user.id, src.chat.id, src.message_id, "|ورود به Game Club|brand", target)
    text, kb = await _bc_panel(gdb, bid, message.from_user.id)
    await message.answer(text, reply_markup=kb, reply_to_message_id=src.message_id)


@router.callback_query(F.data.startswith("bc:"))
async def on_bc_button(cq: CallbackQuery, gdb: GCDatabase, bot: Bot) -> None:
    from app.config import config as obour_cfg

    from . import admin

    if cq.from_user.id not in obour_cfg.admin_ids:
        await cq.answer()
        return
    parts = (cq.data or "").split(":", 3)
    act, bid = parts[1], int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    me = cq.from_user.id
    b = await gdb.bc_get(bid)
    if not b or b["status"] != "draft":
        await cq.answer("این پیش‌نویس دیگه فعال نیست.", show_alert=True)
        return

    async def redraw() -> None:
        text, kb = await _bc_panel(gdb, bid, me)
        try:
            await cq.message.edit_text(text, reply_markup=kb)
        except Exception:  # noqa: BLE001  (not modified)
            pass

    if act == "t" and len(parts) == 4 and parts[3] in dict(admin.TARGET_KEYS):
        await gdb.bc_set_draft(bid, target=parts[3])
        await cq.answer(admin.target_label(parts[3]))
        await redraw()
    elif act == "b":
        await gdb.setting_put(_BC_WAIT + str(me), str(bid))
        await cq.answer()
        await cq.message.answer(_h("link", "دکمه‌های پیام", f"پیش‌نویس {bid}", [
            "هر خط یه دکمه (حداکثر ۳ تا): متن دکمه | صفحه", "",
            "🃏 بازی حکم | حکم", "🎮 ورود به Game Club | خانه", "",
            "صفحه‌ها: " + "، ".join(PAGE_FA.values()),
            "ایموجی اول هر خط اگه پریمیوم باشه، آیکن پریمیوم دکمه می‌شه."],
            foot=(None, None, "بدون دکمه: فقط بفرست -")))
    elif act == "test":
        r = await admin._send(bot, me, "", b["button"], (b["src_chat"], b["src_msg"]))
        await cq.answer("نسخهٔ آزمایشی برات رسید." if r == "ok" else "نرسید؛ پیام اصلی پاک نشده؟", show_alert=r != "ok")
    elif act == "send":
        n = await gdb.bc_count(admin._target(b["target"], me))
        await cq.answer()
        await cq.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [_ib(f"بله، برای {n:,} نفر بفرست", f"bc:go:{bid}", "ok")], [_ib("برگشت", f"bc:back:{bid}")]]))
    elif act == "back":
        await cq.answer()
        await redraw()
    elif act == "go":
        target = admin._target(b["target"], me)
        total = await gdb.bc_launch(bid, target)
        if not total:
            await cq.answer("گیرنده‌ای نداره یا قبلا فرستاده شده.", show_alert=True)
            return
        await gdb.log_admin(me, "broadcast", str(bid), f"{target} · copy")
        admin.kick()
        await cq.answer("ارسال شروع شد")
        await cq.message.edit_text(_h("megaphone", "پیام همگانی", f"شماره {bid}", ["ارسال شروع شد؛ حدود ۲۰ پیام در ثانیه."],
                                      foot=("users", "گیرنده‌ها", [st.num(total), " نفر"])),
                                   reply_markup=open_kb("admin.html#bc", "دیدن آمار", "chart"))
    elif act == "del":
        await gdb.bc_drop_draft(bid)
        await cq.answer("لغو شد")
        await cq.message.edit_text(_h("megaphone", "پیام همگانی", f"پیش‌نویس {bid}", ["لغو شد."]))
    else:
        await cq.answer()


def parse_button_lines(html_text: str) -> tuple[list[str], list[str]]:
    """متن ادمین (HTML با tg-emoji) -> خط های «صفحه|متن|آیدی ایموجی» و خط های نامعتبر."""
    import html as _html
    import re

    ok, bad = [], []
    for raw in html_text.splitlines():
        if not raw.strip():
            continue
        m = re.match(r'\s*<tg-emoji emoji-id="(\d+)">[^<]*</tg-emoji>\s*', raw)
        icon = m.group(1) if m else ""
        line = _html.unescape(re.sub(r"<[^>]+>", "", raw[m.end():] if m else raw))
        label, sep, page = line.rpartition("|")
        page = " ".join(page.replace("\u200c", " ").split())
        label = " ".join(label.replace("|", " ").split())[:40]
        if not sep or not label or page not in PAGE_ALIAS:
            bad.append(_html.unescape(re.sub(r"<[^>]+>", "", raw)).strip())
            continue
        ok.append(f"{PAGE_ALIAS[page]}|{label}|{icon}")
    return ok[:3], bad


@router.message(F.chat.type == "private", F.text)
async def on_bc_buttons(message: Message, gdb: GCDatabase) -> None:
    """ادمینی که «دکمه ها» را زده: پیام بعدی اش دکمه های پیش نویس است."""
    from aiogram.dispatcher.event.bases import SkipHandler

    if not _is_admin(message) or (message.text or "").startswith("/"):
        raise SkipHandler
    key = _BC_WAIT + str(message.from_user.id)
    bid = (await gdb.settings_all()).get(key)
    if not bid or not str(bid).isdigit():
        raise SkipHandler
    if (message.text or "").strip() in ("-", "—", "بدون دکمه"):
        lines, bad = [], []
    else:
        lines, bad = parse_button_lines(message.html_text)
        if not lines:
            await message.answer("هیچ خط درستی پیدا نشد. شکلش این‌طوریه: <code>🃏 بازی حکم | حکم</code>\n"
                                 "صفحه‌ها: " + "، ".join(PAGE_FA.values()))
            return
    await gdb.setting_put(key, None)
    if not await gdb.bc_set_draft(int(bid), button="\n".join(lines)):
        await message.answer("این پیش‌نویس دیگه فعال نیست.")
        return
    text, kb = await _bc_panel(gdb, int(bid), message.from_user.id)
    if bad:
        text = "این خط‌ها کنار گذاشته شد: " + "، ".join(emo.esc(x) for x in bad) + "\n\n" + text
    await message.answer(text, reply_markup=kb)


# ---------- ایموجی های پریمیوم ----------
# ادمین یک پیام با ایموجی های پریمیوم می فرستد: هر کدام که ایموجی جایگزینش در کاتالوگ است
# برای همان کلید ثبت می شود. /gcemoji <کلید> فقط همان کلید را با اولین ایموجی پریمیوم پیام بعد.
_emoji_wait: dict[int, tuple[str, float]] = {}


def _emoji_page() -> str:
    rows = [[st.E(x["key"]) if x["id"] else x["emoji"], " ", x["title"], " · ", st.iso(x["key"]),
             " ✓" if x["id"] else ""] for x in emo.listing()]
    done = sum(1 for x in emo.listing() if x["id"])
    return _h("brand", "ایموجی‌های پریمیوم", "Game Club", [
        "یه پیام با ایموجی‌های پریمیوم بفرست؛ هر کدوم که شکل معمولیش توی فهرست زیر باشه، جاش می‌شینه.",
        "یه کلید خاص: /gcemoji hokm و بعد ایموجی رو بفرست",
        "کپی از عبور: /gcemoji obour",
        "برگرداندن: /gcemoji reset hokm", "", *rows],
        foot=("selected", "تنظیم شده", [st.num(done), " از ", st.num(len(emo.CATALOG))]))


@router.message(Command("gcemoji"))
async def on_emoji(message: Message, command: CommandObject, gdb: GCDatabase) -> None:
    if not _is_admin(message):
        await on_text(message)
        return
    import time as _t

    await emo.load(gdb)
    args = (command.args or "").split()
    if args[:1] == ["obour"]:
        pairs = emo.from_obour()
        for k, eid in pairs:
            await emo.set_emoji(gdb, k, eid)
        await gdb.log_admin(message.from_user.id, "setting", "emoji", f"obour {len(pairs)}")
        await message.answer(f"{len(pairs)} ایموجی از عبور کپی شد.\n\n" + _emoji_page())
        return
    if args[:1] == ["reset"] and len(args) == 2 and args[1] in emo.CATALOG:
        await emo.reset(gdb, args[1])
        await message.answer(_emoji_page())
        return
    if len(args) == 1 and args[0] in emo.CATALOG:
        _emoji_wait[message.from_user.id] = (args[0], _t.time() + 300)
        await message.answer(f"حالا ایموجی پریمیوم «{emo.CATALOG[args[0]][1]}» ({emo.default(args[0])}) رو بفرست.")
        return
    await message.answer(_emoji_page())


@router.message(F.chat.type == "private", F.entities)
async def on_custom_emoji(message: Message, gdb: GCDatabase) -> None:
    """پیام ادمین با ایموجی پریمیوم: ثبت برای کلیدها؛ بقیه پیام ها مثل همیشه."""
    if not _is_admin(message) or not any(e.type == "custom_emoji" for e in message.entities or []):
        await on_text(message)
        return
    import time as _t

    want = _emoji_wait.pop(message.from_user.id, None)
    if want and want[1] > _t.time():
        eid = emo.first_custom(message.entities)
        pairs = [(want[0], eid)] if eid else []
    else:
        pairs = emo.from_message(message.text or "", message.entities)
    for k, eid in pairs:
        await emo.set_emoji(gdb, k, eid)
    if pairs:
        await gdb.log_admin(message.from_user.id, "setting", "emoji", " ".join(k for k, _ in pairs))
    await message.answer((f"{len(pairs)} ایموجی ثبت شد: {' '.join(emo.html_of(k) for k, _ in pairs)}\n\n" if pairs else
                          "ایموجی پریمیومی که شکل معمولیش توی فهرست باشه پیدا نشد. برای یه کلید خاص: /gcemoji hokm\n\n")
                         + _emoji_page())


@router.message(F.chat.type == "private", F.text)
async def on_text(message: Message) -> None:
    await message.answer(_h("brand", "Game Club", "بازی", ["برای بازی، Game Club رو باز کن."],
                            foot=(None, None, "یا توی گروهت بنویس /hokm")), reply_markup=open_kb())


COMMANDS = [BotCommand(command="start", description="ورود به Game Club"),
            BotCommand(command="points", description="موجودی امتیاز"),
            BotCommand(command="help", description="قوانین")]
GROUP_COMMANDS = [BotCommand(command="hokm", description="میز حکم در همین گروه"),
                  BotCommand(command="ludo", description="میز منچ در همین گروه"),
                  BotCommand(command="football", description="میز فوتبال در همین گروه"),
                  BotCommand(command="play", description="انتخاب بازی")]
UPDATES = ["message", "callback_query", "inline_query", "chosen_inline_result"]


async def _heal_webhook(bot: Bot) -> None:
    """بعد از به روزرسانی: اگر وبهوک هنوز دکمه ها (callback_query) را نمی گیرد، دوباره ثبتش کن."""
    try:
        info = await bot.get_webhook_info()
        if info.url and set(UPDATES) - set(info.allowed_updates or ["message"]):
            await setup(bot, drop=False)
            log.info("وبهوک Game Club برای دکمه های گروه به روز شد")
    except Exception:  # noqa: BLE001
        log.debug("بررسی وبهوک نشد", exc_info=True)


async def setup(bot: Bot, drop: bool = True) -> str:
    """وبهوک، فهرست دستورها و دکمه منو. از مسیر /gc/setwebhook صدا زده می شود."""
    if not gc.webhook_secret:
        raise RuntimeError("GAME_CLUB_WEBHOOK_SECRET در .env تنظیم نشده")
    await bot.set_webhook(url=gc.webhook_url, secret_token=gc.webhook_secret,
                          drop_pending_updates=drop, allowed_updates=UPDATES)
    await bot.set_my_commands(COMMANDS, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())
    note = "menu: off (https لازم است)"
    if gc.webapp_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="بازی", web_app=WebAppInfo(url=gc.webapp_url)))
        note = f"menu: {gc.webapp_url}"
    me = await bot.get_me()
    return f"game club webhook set: {gc.webhook_url}\nbot: @{me.username}\n{note}"
