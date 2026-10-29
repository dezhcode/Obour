"""ربات تلگرام AsoTas.

روی همان event loop عبور ساخته می شود (app.runtime) ولی Bot، Dispatcher
و دیتابیس خودش را دارد. کار اصلی ربات باز کردن مینی اپ است:
  /start            خوش آمد + دکمه ورود
  /start ludo_CODE  لینک دعوت دوست: دکمه مستقیم به همان میز (حکم: hokm_CODE، فوتبال: football_CODE، بیلیارد: billiard_CODE، دیوار: divar_CODE، اسم‌فامیل: esmfamil_CODE، لشگر کاغذی: lashgar_CODE، مار و پله: snakes_CODE)
  /esmfamil         در پیوی: اسم‌فامیل فقط در گروه یا کانال است؛ توضیح و دکمهٔ انتخاب گروه/کانال
  /lashgar          در پیوی: لشگر کاغذی (جنگ کاغذی) هم فقط در گروه یا کانال است
  /start obour      آمده از کارت AsoTas در مینی اپ عبور
  /points           موجودی امتیاز
  /help             قوانین کوتاه
در گروه ها (groups.py): @آیدی ربات (حالت اینلاین) یا /hokm، /ludo، /football، /billiard، /divar، /esmfamil، /lashgar، /snakes، /play کارت تنظیم میز می فرستد.
/start و /help راه اینلاین را یاد می دهند و دکمهٔ «بازی توی گروه» دارند.
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
    SwitchInlineQueryChosenChat,
    WebAppInfo,
)

from . import emoji as emo
from . import style as st
from .config import gc
from .db import GCDatabase

log = logging.getLogger("gameclub.bot")
router = Router(name="gameclub")


class GCRuntime:
    """اجزای AsoTas روی loop عبور. یک بار ساخته می شود."""

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

                # عضویت اجباری (پنل مدیریت): در پیوی تا عضو کانال ها/گروه های لازم نشده، فقط پیام «عضو شو»
                from . import gate as _gate

                @dp.message.outer_middleware()
                async def _gate_msg(handler, event, data):  # noqa: ANN001, ANN202
                    u = event.from_user
                    if event.chat.type == "private" and u and not u.is_bot:
                        try:
                            need = await _gate.missing(db, self.bot, u.id)
                        except Exception:  # noqa: BLE001
                            need = []
                        if need:
                            await event.answer(gate_text(need), reply_markup=gate_kb(need))
                            return None
                    return await handler(event, data)

                @dp.callback_query.outer_middleware()
                async def _gate_cb(handler, event, data):  # noqa: ANN001, ANN202
                    msg = event.message
                    if msg and msg.chat.type == "private" and not (event.data or "").startswith("gate:"):
                        try:
                            need = await _gate.missing(db, self.bot, event.from_user.id)
                        except Exception:  # noqa: BLE001
                            need = []
                        if need:
                            await event.answer("اول عضو " + "، ".join(c["title"] for c in need) + " شو 🙏", show_alert=True)
                            return None
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
                    if tg < 0:      # مهمان برنامهٔ اندروید پیوی تلگرام ندارد
                        return
                    icon, sub, btn = NOTICE.get(key, ("bell", "اعلان", "باز کردن AsoTas"))
                    body = st.to_html(st.frame(icon, "AsoTas", sub, [st.Raw(text)]))
                    await bot.send_message(tg, body, reply_markup=open_kb(page, btn, "brand"))

                service.notifier = notify
            self.db = db
            log.info("AsoTas آماده شد (db=%s)", gc.db_path)
        return self


gcrt = GCRuntime()


# نوع اعلان -> (ایموجی، زیرعنوان، متن دکمه)
NOTICE = {
    "turn": ("turn", "نوبت توئه!", "برگرد سر بازی"),
    "join": ("seat", "یکی سر میزت نشست", "برو سر میز"),
    "over": ("trophy", "نتیجهٔ بازی", "باز کردن AsoTas"),
    "freq": ("friend", "درخواست دوستی", "ببین کیه"),
    "facc": ("friend", "رفیق تازه", "دیدن رفیقا"),
    "dm": ("chat", "پیام تازه", "بخونش"),
    "dminv": ("link", "دعوت به بازی", "بشین سر میز"),
}


def gate_text(need: list[dict]) -> str:
    names = "، ".join(f"«{c['title']}»" for c in need)
    return st.to_html(st.frame("megaphone", "AsoTas", "عضویت لازمه", [
        f"برای بازی توی AsoTas اول باید عضو {names} بشی.", "",
        "عضو که شدی، دکمهٔ «عضو شدم» رو بزن تا بریم سراغ بازی 🎮"]))


def gate_kb(need: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=("📢 " if c.get("kind") == "channel" else "👥 ") + c["title"], url=c["url"])]
            for c in need if c.get("url")]
    rows.append([InlineKeyboardButton(text="✅ عضو شدم", callback_data="gate:ok")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "gate:ok")
async def on_gate_ok(cb: CallbackQuery, gdb: GCDatabase) -> None:
    from . import gate

    need = await gate.missing(gdb, cb.bot, cb.from_user.id, fresh=True)
    if need:
        await cb.answer("هنوز عضو " + "، ".join(c["title"] for c in need) + " نشدی 🤔", show_alert=True)
        try:
            await cb.message.edit_text(gate_text(need), reply_markup=gate_kb(need))
        except Exception:  # noqa: BLE001
            pass
        return
    await cb.answer("عضویتت تأیید شد ✅")
    try:
        await cb.message.edit_text(st.to_html(st.frame("ok", "AsoTas", "خوش اومدی!", [
            "عضویتت تأیید شد ✅ حالا می‌تونی بازی کنی."])), reply_markup=open_kb("", "بزن بریم بازی"))
    except Exception:  # noqa: BLE001
        pass


def open_kb(page: str = "", text: str = "ورود به AsoTas", icon: str | None = "brand") -> InlineKeyboardMarkup | None:
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


GAME_FA = {"ludo": "منچ", "hokm": "حکم", "football": "فوتبال", "billiard": "بیلیارد", "divar": "دیوار", "esmfamil": "اسم‌فامیل",
           "lashgar": "لشگر کاغذی", "snakes": "مار و پله"}


# ---------- راهنمای بازی در گروه با حالت اینلاین (@آیدی ربات) ----------
def bot_at() -> str:
    return f"@{gc.username}" if gc.username else "@آیدی_ربات"


def group_steps() -> list:
    return [[st.E("group"), " ", st.B("بازی توی گروه")],
            ["1. توی گروهت بنویس ", st.iso(bot_at()), " و یه فاصله بذار"],
            "2. از لیستی که بالای کیبورد باز می‌شه، بازی رو انتخاب کن: حکم، منچ، فوتبال، بیلیارد، دیوار، اسم‌فامیل، لشگر کاغذی یا مار و پله",
            "3. حالت بازی رو بچین و «باز کردن میز» رو بزن",
            "4. رفیقات «بشین» رو می‌زنن؛ میز که پر شد، بازی شروع می‌شه 🎉"]


def with_group_button(kb: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup:
    """دکمهٔ «بازی توی گروه»: تلگرام فهرست چت ها را باز می کند و @آیدی ربات را خودش می نویسد."""
    btn = st.kb_button("بازی توی گروه", "group", switch_inline_query_chosen_chat=SwitchInlineQueryChosenChat(
        query="", allow_group_chats=True, allow_user_chats=True, allow_channel_chats=True))
    return InlineKeyboardMarkup(inline_keyboard=[[btn], *(kb.inline_keyboard if kb else [])])


@router.message(CommandStart())
async def on_start(message: Message, command: CommandObject, gdb: GCDatabase) -> None:
    u = message.from_user
    if not u:
        return
    me = await gdb.player(u.id, _name(message), u.username)
    if me.get("banned"):
        await message.answer(_h("ban", "AsoTas", "حساب مسدود", [
            "حسابت توی AsoTas مسدود شده 🚫"],
            foot=(None, None, "اگه فکر می‌کنی اشتباه شده، به پشتیبانی عبور پیام بده؛ آدمای خوبی‌ان 😄")))
        return
    arg = (command.args or "").strip()
    if arg == "esmfamil":   # از دکمهٔ راهنمای حالت اینلاین در پیوی
        await message.answer(_h("esmfamil", "اسم‌فامیل", "بازی گروهی", esmfamil_intro(),
                                foot=(None, None, "دکمهٔ زیر رو بزن و گروهت رو انتخاب کن 👇")), reply_markup=esmfamil_kb())
        return
    if arg == "lashgar":
        await message.answer(_h("lashgar", "لشگر کاغذی", "بازی گروهی", lashgar_intro(),
                                foot=(None, None, "دکمهٔ زیر رو بزن و گروهت رو انتخاب کن 👇")), reply_markup=lashgar_kb())
        return
    game = arg.split("_", 1)[0]
    if game in GAME_FA and "_" in arg:
        name = GAME_FA[game]
        code = "".join(ch for ch in arg.split("_", 1)[1].upper() if ch.isalnum())[:12]
        m = await gdb.match_by_invite(code)
        if not m or m["status"] != "lobby":
            await message.answer(_h(game, f"میز {name}", "دیر رسیدی 😅", [
                "این میز یا جمع شده یا بازیش شروع شده."], foot=(None, None, "عیب نداره؛ خودت یه میز تازه بچین 👇")),
                reply_markup=open_kb(f"{game}-lobby.html", f"میز تازهٔ {name}", "new"))
            return
        stake = m["cfg"]["mode"] == "stake"
        who = {"hokm": "یه دست حکم (یار خودش!)", "football": "یه بازی فوتبال", "ludo": "یه دست منچ",
               "billiard": "یه دست بیلیارد" + (" (یار خودش!)" if m["cfg"].get("players") == 4 else ""),
               "divar": "یه دست دیوار" + (" چهار نفره" if m["cfg"].get("players") == 4 else ""),
               "esmfamil": "یه دست اسم‌فامیل با داور هوش مصنوعی", "lashgar": "یه جنگ کاغذی (لشگر کاغذی!)",
               "snakes": "یه دست مار و پله" + (f" {m['cfg'].get('players')} نفره" if m["cfg"].get("players") else "")}[game]
        await message.answer(_h(game, f"میز {name}", "دعوتت کردن!", [
            f"رفیقت تو رو به {who} دعوت کرده؛ منتظره بشینی کنارش 😎"],
            foot=("coin", "نوع میز", ["با امتیاز · ورودی ", st.num(m["cfg"]["entry"])] if stake else "آزاد · مجانی")),
            reply_markup=open_kb(f"{game}-lobby.html?join={code}", "بشین سر میز", "seat"))
        return
    lines = [["سلام ", st.iso(me.get("name") or "بازیکن"), "، خوش اومدی! اینجا کسی حوصله‌ش سر نمی‌ره 😎"], "",
             [st.E("hokm"), " حکم  ", st.E("ludo"), " منچ  ", st.E("football"), " فوتبال  ", st.E("billiard"), " بیلیارد  ", st.E("divar"), " دیوار  ", st.E("snakes"), " مار و پله"],
             "با رفیقات یا با ناشناس؛ هر جا حوصله‌ت سر رفت 😄",
             [st.E("esmfamil"), " اسم‌فامیل هم داریم، توی گروه یا کانال؛ داورش هوش مصنوعی عبوره!"],
             [st.E("lashgar"), " لشگر کاغذی هم هست؛ همون جنگ کاغذی دهه شصت، توی گروه یا کانال 🪖"], "", *group_steps()]
    if arg == "obour":
        lines += ["", "حساب عبورت به همین تلگرام وصله؛ شارژ از کیف عبور یه ثانیه‌ست ⚡"]
    await message.answer(_h("hello", "AsoTas", "منوی اصلی", lines, foot=("coin", "امتیاز", [st.num(me["points"]), " امتیاز"])),
                         reply_markup=with_group_button(open_kb()))


def esmfamil_intro() -> list:
    return [[st.E("esmfamil"), " ", st.B("اسم‌فامیل توی گروه یا کانال بازی می‌شه")],
            "همه با هم یه حرف می‌گیرن و اسم، فامیل، شهر، کشور، غذا، حیوان، میوه، اشیا و رنگ رو پر می‌کنن؛ هر دور 3، 5 یا 8 دقیقه.",
            [st.E("judge"), " حرف هر دور رو هوش مصنوعی عبور انتخاب می‌کنه و برگ‌ها رو هم خودش تصحیح می‌کنه."],
            "جواب درستی که فقط تو نوشتی 10، تکراری 5؛ آخر بازی برگ همه با امتیازا توی گروه میاد و برنده اعلام می‌شه 🏆", "",
            ["توی گروهت بنویس ", st.iso("/esmfamil"), " یا توی گروه و کانالت ", st.iso(bot_at() + " esmfamil")]]


def esmfamil_kb() -> InlineKeyboardMarkup:
    """فقط گروه ها و کانال ها در فهرست انتخاب تلگرام می آیند؛ کارت تنظیم میز همان جا ساخته می شود."""
    btn = st.kb_button("یه گروه یا کانال انتخاب کن، بزن بریم", "group", switch_inline_query_chosen_chat=SwitchInlineQueryChosenChat(
        query="esmfamil", allow_group_chats=True, allow_user_chats=False, allow_bot_chats=False, allow_channel_chats=True))
    kb = open_kb("esmfamil-lobby.html", "چطوری بازی کنم؟", "help")
    return InlineKeyboardMarkup(inline_keyboard=[[btn], *(kb.inline_keyboard if kb else [])])


def lashgar_intro() -> list:
    return [[st.E("lashgar"), " ", st.B("لشگر کاغذی توی گروه یا کانال بازی می‌شه")],
            "همون جنگ کاغذی زنگ تفریح: یه برگه، خط وسط، این‌ور ارتش تو و اون‌ور ارتش حریف. اول اسم لشگرت رو می‌ذاری، "
            "بعد سرباز و تانک و توپ و هلیکوپتر و پرچمت رو می‌چینی و با مداد هر چی دلت خواست می‌کشی؛ نقاشی وقت نداره.",
            [st.E("boom"), " هر شلیک 1 دقیقه وقت داره: یه نقطه روی نیمهٔ خودت، برگه رو تا می‌کنی و از پشت فشار می‌دی؛ "
             "ردش قرینه روی نیمهٔ حریف می‌افته و هر نیرویی که بخوره، خط می‌خوره."],
            "هر کی زودتر پرچم حریف رو بزنه یا همهٔ نیروهاشو خط بزنه، برنده‌ست 🏆", "",
            ["توی گروهت بنویس ", st.iso("/lashgar"), " یا توی گروه و کانالت ", st.iso(bot_at() + " lashgar")]]


def lashgar_kb() -> InlineKeyboardMarkup:
    btn = st.kb_button("یه گروه یا کانال انتخاب کن، بزن بریم", "group", switch_inline_query_chosen_chat=SwitchInlineQueryChosenChat(
        query="lashgar", allow_group_chats=True, allow_user_chats=False, allow_bot_chats=False, allow_channel_chats=True))
    kb = open_kb("lashgar-lobby.html", "چطوری بازی کنم؟", "help")
    return InlineKeyboardMarkup(inline_keyboard=[[btn], *(kb.inline_keyboard if kb else [])])


@router.message(Command("lashgar"))
async def on_lashgar(message: Message) -> None:
    """در پیوی: این بازی گروهی است (در گروه همین دستور را groups.py جواب می دهد)."""
    await message.answer(_h("lashgar", "لشگر کاغذی", "بازی گروهی", lashgar_intro(),
                            foot=(None, None, "دکمهٔ زیر رو بزن و گروهت رو انتخاب کن 👇")), reply_markup=lashgar_kb())


@router.message(Command("esmfamil"))
async def on_esmfamil(message: Message) -> None:
    """در پیوی: این بازی گروهی است (در گروه همین دستور را groups.py جواب می دهد)."""
    await message.answer(_h("esmfamil", "اسم‌فامیل", "بازی گروهی", esmfamil_intro(),
                            foot=(None, None, "دکمهٔ زیر رو بزن و گروهت رو انتخاب کن 👇")), reply_markup=esmfamil_kb())


@router.message(Command("points"))
async def on_points(message: Message, gdb: GCDatabase) -> None:
    u = message.from_user
    if not u:
        return
    p = await gdb.player(u.id, _name(message), u.username)
    rate = round(p["wins"] * 100 / p["games"]) if p["games"] else 0
    vibe = ("هنوز بازی نکردی؛ زمین منتظرته!" if not p["games"] else "داری می‌ترکونی 🔥" if rate >= 60
            else "بد نیست؛ یه کم دیگه تمرین 😉" if rate >= 35 else "شانس با تو قهره؛ ولی آشتی می‌کنه 😄")
    await message.answer(_h("coin", "کیف امتیاز", "AsoTas", [
        [st.E("trophy"), " برد: ", st.num(p["wins"]), " از ", st.num(p["games"]), " بازی"], vibe],
        foot=("coin", "موجودی", [st.num(p["points"]), " امتیاز"])),
        reply_markup=open_kb("shop.html", "کیف امتیاز", "coin"))


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(_h("help", "راهنما", "بازی توی گروه", [
        *group_steps(), "",
        "لازم نیست ربات عضو گروه باشه؛ فقط آیدیش رو بنویس 😉",
        "دکمهٔ «بازی توی گروه» هم گروهت رو باز می‌کنه و آیدی رو خودش می‌نویسه.",
    ], foot=(None, None, "قوانین هر بازی توی «راهنمای کامل» هست")),
        reply_markup=with_group_button(open_kb("help.html", "راهنمای کامل", "help")))


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
    await message.answer(_h("chart", "آمار AsoTas", "امروز و کل", [
        ["بازیکن: ", n(allt["players"]), " · امتیاز در گردش: ", n(allt["points"])],
        ["الان: ", n(allt["playing"]), " میز در بازی، ", n(allt["lobby"]), " میز دعوت، ", n(allt["queue"]), " نفر تو صف"], "",
        [st.B("24 ساعت گذشته")],
        ["بازی تموم‌شده: ", n(day["games"])],
        ["شارژ: ", n(day["charge"]), " امتیاز (", n(day["charge"] * gc.point_toman), " تومان)"],
        ["ورودی: ", n(day["entry"]), " · جایزه: ", n(day["prize"])],
    ], foot=("coin", "خرج تو عبور", [n(day["shop"]), " امتیاز"])))


@router.message(Command("gcpoints"))
async def on_points_admin(message: Message, command: CommandObject, gdb: GCDatabase) -> None:
    if not _is_admin(message):
        return
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].lstrip("-").isdigit() or int(parts[1]) == 0:
        await message.answer("شکل درستش اینه: <code>/gcpoints 123456789 500</code> (منفی برای کم کردن)")
        return
    tg, amount = int(parts[0]), int(parts[1])
    if not await gdb.get_player(tg):
        await message.answer("این بنده خدا هنوز AsoTas رو باز نکرده.")
        return
    from . import service

    idem = f"admin:{message.chat.id}:{message.message_id}"
    ok = (await service.earn(gdb, tg, amount, "admin", "تنظیم دستی پشتیبانی", "admin", idem) if amount > 0
          else await service.spend(gdb, tg, -amount, "admin", "تنظیم دستی پشتیبانی", "admin", idem))
    p = await gdb.get_player(tg)
    await message.answer(_h("ok" if ok else "warn", "تغییر امتیاز", st.iso(tg), [
        "انجام شد ✅" if ok else "نشد؛ موجودیش کافی نیست؟"], foot=("coin", "موجودی الان", [st.num(p["points"]), " امتیاز"])))
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
        await message.answer("میز بازی با این شناسه پیدا نشد 🤔")
        return
    await message.answer(_h("ok", "میز بسته شد", st.iso(mid), [], foot=("coin", "ورودی برگشتی", [st.num(r["refunded"]), " امتیاز"])))


@router.message(Command("admin"))
async def on_admin(message: Message) -> None:
    """پنل مدیریت AsoTas (فقط ادمین های عبور)."""
    if not _is_admin(message):
        await on_text(message)
        return
    rows = []
    if gc.webapp_url:
        rows.append([st.kb_button("پنل مدیریت (مینی اپ)", "gear", web_app=WebAppInfo(url=gc.webapp_url + "admin.html"))])
    rows.append([_ib("ایموجی‌های پریمیوم", "ge:h", "brand"), _ib("پیام همگانی", "bc:help", "megaphone")])
    await message.answer(_h("gear", "پنل مدیریت", "AsoTas", [
        "کاربرا، میزها، تراکنش‌ها، آمار پیام همگانی و تنظیمات توی مینی اپ.",
        "ایموجی‌ها و پیام همگانی همین‌جا توی ربات."], foot=(None, None, "از کجا شروع کنیم؟ 👇")),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


def _ib(text: str, data: str, key: str | None = None, style: str | None = None) -> InlineKeyboardButton:
    return st.kb_button(text, key, callback_data=data, **({"style": style} if style else {}))


# ---------- ایموجی های پریمیوم (دقیقا مثل عبور: دسته -> فهرست -> ایموجی -> فرستادن ایموجی پریمیوم) ----------
_EMO_WAIT = "emowait:"   # setting: ادمین منتظر فرستادن ایموجی پریمیوم برای این کلید است ("*" = چندتا با هم)
EMOJI_PAGE = 8
_CATS = list(emo.CATEGORIES)


def _done(keys) -> int:  # noqa: ANN001
    return sum(1 for k in keys if emo.custom_id(k))


def _emo_home() -> tuple[str, InlineKeyboardMarkup]:
    text = _h("brand", "ایموجی‌های پریمیوم", [st.num(_done(emo.CATALOG)), " از ", st.num(len(emo.CATALOG)), " پریمیوم شده"], [
        "ایموجی هر بخش ربات رو می‌تونی با یه ایموجی پریمیوم عوض کنی؛ از کارت‌های گروه تا دکمه‌ها و پیام همگانی ✨",
        "", "صاحب ربات باید Telegram Premium داشته باشه، وگرنه همون ایموجی معمولی دیده می‌شه."],
        foot=(None, None, "یه دسته رو انتخاب کن 👇"))
    rows = [[_ib(f"{c} ({_done(ks)}/{len(ks)})", f"ge:c:{i}:0")] for i, (c, ks) in enumerate(emo.CATEGORIES.items())]
    rows.append([_ib("📥 چندتا با هم", "ge:b"), _ib("🔁 کپی از عبور", "ge:o")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def _emo_list(ci: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    ci = max(0, min(ci, len(_CATS) - 1))
    cat = _CATS[ci]
    keys = emo.CATEGORIES[cat]
    pages = max(1, (len(keys) + EMOJI_PAGE - 1) // EMOJI_PAGE)
    page = max(0, min(page, pages - 1))
    text = _h("brand", cat, [st.num(_done(keys)), " از ", st.num(len(keys)), " پریمیوم شده · صفحه ", st.num(page + 1), " از ", st.num(pages)],
              ["روی هر کدوم بزنی، عوضش می‌کنی."], foot=(None, None, "✨ یعنی پریمیومش تنظیم شده."))
    rows = [[st.kb_button(f"{emo.default(k)} {emo.CATALOG[k][1]}{' ✨' if emo.custom_id(k) else ''}", k, callback_data=f"ge:e:{k}")]
            for k in keys[page * EMOJI_PAGE:(page + 1) * EMOJI_PAGE]]
    nav = ([_ib("⬅️ قبلی", f"ge:c:{ci}:{page - 1}")] if page > 0 else []) + \
          ([_ib("بعدی ➡️", f"ge:c:{ci}:{page + 1}")] if page < pages - 1 else [])
    if nav:
        rows.append(nav)
    rows.append([_ib("🔙 دسته‌ها", "ge:h")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def _cat_of(key: str) -> tuple[int, int]:
    for i, ks in enumerate(emo.CATEGORIES.values()):
        if key in ks:
            return i, ks.index(key) // EMOJI_PAGE
    return 0, 0


def _emo_edit(key: str) -> tuple[str, InlineKeyboardMarkup]:
    ci, page = _cat_of(key)
    text = _h(key, emo.CATALOG[key][1], ["ایموجی فعلی ", st.E(key)], [
        "حالا یه ایموجی پریمیوم بفرست تا جاش بشینه.", "",
        st.Raw("<blockquote>فقط ایموجی پریمیوم (متحرک) قبوله؛ ایموجی معمولی که فرقی نمی‌کنه 😄 "
               "اگه پریمیوم نداری، از یه کانال ایموجی فوروارد کن.</blockquote>")])
    rows = ([[_ib("↩️ برگرد به معمولی", f"ge:r:{key}", style="danger")]] if emo.custom_id(key) else []) + \
        [[_ib("🔙 برگشت", f"ge:c:{ci}:{page}")]]
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def _emo_wait(gdb: GCDatabase, admin_id: int, key: str | None) -> None:
    await gdb.setting_put(_EMO_WAIT + str(admin_id), key)


@router.message(Command("gcemoji"))
async def on_emoji(message: Message, gdb: GCDatabase) -> None:
    if not _is_admin(message):
        await on_text(message)
        return
    await emo.load(gdb)
    await _emo_wait(gdb, message.from_user.id, None)
    text, kb = _emo_home()
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("ge:"))
async def on_emoji_button(cq: CallbackQuery, gdb: GCDatabase) -> None:
    from app.config import config as obour_cfg

    if cq.from_user.id not in obour_cfg.admin_ids:
        await cq.answer()
        return
    parts = (cq.data or "").split(":")
    act, me = parts[1], cq.from_user.id
    await emo.load(gdb)

    async def show(view: tuple[str, InlineKeyboardMarkup]) -> None:
        try:
            await cq.message.edit_text(view[0], reply_markup=view[1])
        except Exception:  # noqa: BLE001  (not modified)
            pass

    if act == "h":
        await _emo_wait(gdb, me, None)
        await cq.answer()
        await show(_emo_home())
    elif act == "c" and len(parts) == 4 and parts[2].isdigit() and parts[3].lstrip("-").isdigit():
        await _emo_wait(gdb, me, None)
        await cq.answer()
        await show(_emo_list(int(parts[2]), int(parts[3])))
    elif act == "e" and len(parts) == 3 and parts[2] in emo.CATALOG:
        await _emo_wait(gdb, me, parts[2])
        await cq.answer()
        await show(_emo_edit(parts[2]))
    elif act == "r" and len(parts) == 3 and parts[2] in emo.CATALOG:
        await emo.reset(gdb, parts[2])
        await _emo_wait(gdb, me, None)
        await gdb.log_admin(me, "setting", "emoji", f"reset {parts[2]}")
        await cq.answer("برگشت به معمولی ↩️")
        await show(_emo_list(*_cat_of(parts[2])))
    elif act == "o":
        pairs = emo.from_obour()
        for k, eid in pairs:
            await emo.set_emoji(gdb, k, eid)
        await gdb.log_admin(me, "setting", "emoji", f"obour {len(pairs)}")
        await cq.answer(f"{len(pairs)} ایموجی از عبور کپی شد" if pairs else "توی عبور ایموجی هم‌شکلی تنظیم نشده", show_alert=not pairs)
        await show(_emo_home())
    elif act == "b":
        await _emo_wait(gdb, me, "*")
        await cq.answer()
        await show((_h("brand", "چندتا با هم", "ایموجی‌های پریمیوم", [
            "یه پیام پر از ایموجی پریمیوم بفرست؛ هر کدوم که شکل معمولیش توی فهرست ربات باشه، خودش جاش می‌شینه 🪄"],
            foot=(None, None, "مثلا پریمیوم‌های 🃏🎲⚽🏆 رو پشت هم بفرست")),
            InlineKeyboardMarkup(inline_keyboard=[[_ib("🔙 دسته‌ها", "ge:h")]])))
    else:
        await cq.answer()


@router.message(F.chat.type == "private", F.text)
async def on_emoji_input(message: Message, gdb: GCDatabase) -> None:
    """ادمینی که یک ایموجی (یا «چندتا با هم») را انتخاب کرده: پیام بعدی اش ایموجی پریمیوم است."""
    from aiogram.dispatcher.event.bases import SkipHandler

    if not _is_admin(message) or (message.text or "").startswith("/"):
        raise SkipHandler
    key = (await gdb.settings_all()).get(_EMO_WAIT + str(message.from_user.id))
    if not key:
        raise SkipHandler
    me = message.from_user.id
    if key == "*":
        pairs = emo.from_message(message.text or "", message.entities)
        if not pairs:
            await message.answer("هیچ ایموجی پریمیومی که شکل معمولیش توی فهرست باشه پیدا نکردم 🤔 یه بار دیگه بفرست.")
            return
        for k, eid in pairs:
            await emo.set_emoji(gdb, k, eid)
        await _emo_wait(gdb, me, None)
        await gdb.log_admin(me, "setting", "emoji", " ".join(k for k, _ in pairs)[:120])
        text, kb = _emo_home()
        await message.answer(f"✅ {len(pairs)} ایموجی عوض شد: {' '.join(emo.html_of(k) for k, _ in pairs)}\n\n" + text, reply_markup=kb)
        return
    if key not in emo.CATALOG:
        await _emo_wait(gdb, me, None)
        raise SkipHandler
    eid = emo.first_custom(message.entities)
    if not eid:
        await message.answer("این ایموجی پریمیوم نیست 🙂\n\nیه ایموجی متحرک (پریمیوم) بفرست. اگه پریمیوم نداری، "
                             "می‌تونی از کانال‌های ایموجی یکی رو فوروارد کنی.")
        return
    await emo.set_emoji(gdb, key, eid)
    await _emo_wait(gdb, me, None)
    await gdb.log_admin(me, "setting", "emoji", key)
    text, kb = _emo_list(*_cat_of(key))
    await message.answer(f"✅ ایموجی <b>{emo.CATALOG[key][1]}</b> عوض شد.\n\nنمونه: {emo.html_of(key)}\n\n" + text, reply_markup=kb)


# ---------- پیام همگانی (فقط از ربات؛ مینی اپ فقط آمار را نشان می دهد) ----------
# ۱) پیام را (متن، عکس، ویدیو... با ایموجی پریمیوم) در ربات بفرست و رویش ریپلای کن: /gcbc
# ۲) در کارت کنترل: گیرنده ها، دکمه ها (تا ۳ تا، با ایموجی پریمیوم)، نسخهٔ آزمایشی و ارسال با تایید
# پیش نویس در دیتابیس است (status=draft)؛ پس اگر پروسه عوض شد چیزی گم نمی شود.
PAGE_ALIAS = {"خانه": "", "home": "", "حکم": "hokm-lobby.html", "منچ": "ludo-lobby.html", "فوتبال": "football-lobby.html",
              "بیلیارد": "billiard-lobby.html", "دیوار": "divar-lobby.html", "اسم‌فامیل": "esmfamil-lobby.html",
              "اسم فامیل": "esmfamil-lobby.html", "لشگر کاغذی": "lashgar-lobby.html", "لشکر کاغذی": "lashgar-lobby.html",
              "جنگ کاغذی": "lashgar-lobby.html", "مار و پله": "snakes-lobby.html", "مار": "snakes-lobby.html",
              "بازی‌ها": "games.html", "بازی ها": "games.html", "بازیها": "games.html", "دوستان": "friends.html",
              "پروفایل": "profile.html", "فروشگاه": "shop.html", "کیف": "shop.html"}
PAGE_FA = {"": "خانه", "hokm-lobby.html": "حکم", "ludo-lobby.html": "منچ", "football-lobby.html": "فوتبال", "billiard-lobby.html": "بیلیارد", "divar-lobby.html": "دیوار",
           "esmfamil-lobby.html": "اسم‌فامیل", "lashgar-lobby.html": "لشگر کاغذی", "snakes-lobby.html": "مار و پله", "games.html": "بازی‌ها", "friends.html": "دوستان", "profile.html": "پروفایل", "shop.html": "فروشگاه"}
_BC_WAIT = "bcwait:"   # setting: ادمین دارد دکمه های کدام پیش نویس را می فرستد


async def _bc_panel(gdb: GCDatabase, bid: int, admin_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    from . import admin

    b = await gdb.bc_get(bid)
    if not b or b["status"] != "draft":
        return _h("megaphone", "پیام همگانی", f"شماره {bid}", ["این پیش‌نویس دیگه از کار افتاده."]), None
    n = await gdb.bc_count(admin._target(b["target"], admin_id))
    btns = admin.parse_buttons(b["button"])
    lines = ["پیامی که روش ریپلای کردی عینا برای همه می‌ره؛ با عکس، متن و ایموجی‌های پریمیومش 📬", "",
             [st.E("link"), " ", st.B("دکمه‌ها")]]
    lines += [["• ", st.Raw(emo.html_of(k) + " ") if k in emo.CATALOG else "", label, " ← ", PAGE_FA.get(page, "خانه")]
              for page, label, k in btns] or ["بدون دکمه؛ ساده و بی‌آلایش 😄"]
    text = _h("megaphone", "پیام همگانی", f"پیش‌نویس {bid}", lines,
              foot=("users", "گیرنده‌ها", [admin.target_label(b["target"]), " · ", st.num(n), " نفر"]))
    tk = [_ib(("✅ " if b["target"] == k else "") + t, f"bc:t:{bid}:{k}") for k, t in admin.TARGET_KEYS]
    rows = [tk[:3], tk[3:6], tk[6:],
            [_ib("✏️ دکمه‌ها", f"bc:b:{bid}"), _ib("🧪 نسخهٔ آزمایشی", f"bc:test:{bid}")],
            [_ib(f"ارسال برای {n:,} نفر", f"bc:send:{bid}", "megaphone", "success")],
            [_ib("بیخیال پیش‌نویس", f"bc:del:{bid}", "cancel")]]
    return text, InlineKeyboardMarkup(inline_keyboard=[r for r in rows if r])


def _bc_help() -> str:
    return _h("megaphone", "پیام همگانی", "از همین ربات", [
        "1. پیامت رو همین‌جا بفرست؛ متن، عکس یا ویدیو، با ایموجی پریمیوم",
        "2. روی همون پیام ریپلای کن و بنویس /gcbc",
        "3. گیرنده‌ها و دکمه‌ها رو بچین، یه نسخهٔ آزمایشی ببین و بفرست 🚀"],
        foot=("chart", "آمار", "پیشرفت و آمار ارسال‌ها توی پنل مدیریت (مینی اپ)"))


@router.message(Command("gcbc"))
async def on_broadcast(message: Message, gdb: GCDatabase) -> None:
    """پیام همگانی با هر نوع محتوا: روی یک پیام (عکس، ویدیو، متن...) ریپلای کن و بنویس /gcbc"""
    if not _is_admin(message):
        return
    src = message.reply_to_message
    if not src:
        await message.answer(_bc_help())
        return
    days = (message.text or "").split()[1:2]
    target = {"7": "active7", "30": "active30"}.get(days[0] if days else "", "all")
    bid = await gdb.bc_draft(message.from_user.id, src.chat.id, src.message_id, "|ورود به AsoTas|brand", target)
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
    if parts[1:2] == ["help"]:
        await cq.answer()
        await cq.message.answer(_bc_help())
        return
    act, bid = parts[1], int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    me = cq.from_user.id
    b = await gdb.bc_get(bid)
    if not b or b["status"] != "draft":
        await cq.answer("این پیش‌نویس دیگه از کار افتاده.", show_alert=True)
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
            "هر خط یه دکمه (حداکثر 3 تا): متن دکمه | صفحه", "",
            "🃏 بازی حکم | حکم", "🎮 ورود به AsoTas | خانه", "",
            "صفحه‌ها: " + "، ".join(PAGE_FA.values()),
            "ایموجی اول هر خط اگه پریمیوم باشه، آیکن پریمیوم دکمه می‌شه."],
            foot=(None, None, "بدون دکمه؟ فقط یه - بفرست")))
    elif act == "test":
        r = await admin._send(bot, me, "", b["button"], (b["src_chat"], b["src_msg"]))
        await cq.answer("نسخهٔ آزمایشی برات رسید؛ یه نگاه بنداز 👀" if r == "ok" else "نرسید؛ پیام اصلی رو پاک نکردی؟", show_alert=r != "ok")
    elif act == "send":
        n = await gdb.bc_count(admin._target(b["target"], me))
        await cq.answer()
        await cq.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [_ib(f"آره، برای {n:,} نفر بفرست", f"bc:go:{bid}", "ok", "success")], [_ib("صبر کن، برگرد", f"bc:back:{bid}")]]))
    elif act == "back":
        await cq.answer()
        await redraw()
    elif act == "go":
        target = admin._target(b["target"], me)
        total = await gdb.bc_launch(bid, target)
        if not total:
            await cq.answer("یا گیرنده نداره یا قبلا رفته 🤔", show_alert=True)
            return
        await gdb.log_admin(me, "broadcast", str(bid), f"{target} · copy")
        admin.kick()
        await cq.answer("رفت که بره! 🚀")
        await cq.message.edit_text(_h("megaphone", "پیام همگانی", f"شماره {bid}", ["ارسال شروع شد؛ حدود 20 پیام در ثانیه می‌ره."],
                                      foot=("users", "گیرنده‌ها", [st.num(total), " نفر"])),
                                   reply_markup=open_kb("admin.html#bc", "دیدن آمار", "chart"))
    elif act == "del":
        await gdb.bc_drop_draft(bid)
        await cq.answer("بیخیالش شدیم")
        await cq.message.edit_text(_h("megaphone", "پیام همگانی", f"پیش‌نویس {bid}", ["بیخیالش شدیم؛ چیزی برای کسی نرفت."]))
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
            await message.answer("هیچ خط درستی پیدا نکردم 🤔 شکلش این‌طوریه: <code>🃏 بازی حکم | حکم</code>\n"
                                 "صفحه‌ها: " + "، ".join(PAGE_FA.values()))
            return
    await gdb.setting_put(key, None)
    if not await gdb.bc_set_draft(int(bid), button="\n".join(lines)):
        await message.answer("این پیش‌نویس دیگه از کار افتاده.")
        return
    text, kb = await _bc_panel(gdb, int(bid), message.from_user.id)
    if bad:
        text = "این خط‌ها کنار گذاشته شد: " + "، ".join(emo.esc(x) for x in bad) + "\n\n" + text
    await message.answer(text, reply_markup=kb)


@router.message(F.chat.type == "private", F.text)
async def on_text(message: Message) -> None:
    await message.answer(_h("brand", "AsoTas", "بزن بریم", ["برای بازی، AsoTas رو باز کن 👇"],
                            foot=(None, None, ["یا توی گروهت بنویس ", st.iso(bot_at()), " و یه بازی انتخاب کن"])),
                         reply_markup=with_group_button(open_kb()))


COMMANDS = [BotCommand(command="start", description="ورود به AsoTas"),
            BotCommand(command="points", description="موجودی امتیاز"),
            BotCommand(command="esmfamil", description="اسم‌فامیل (توی گروه یا کانال)"),
            BotCommand(command="lashgar", description="لشگر کاغذی؛ جنگ کاغذی (توی گروه یا کانال)"),
            BotCommand(command="help", description="قوانین")]
GROUP_COMMANDS = [BotCommand(command="hokm", description="میز حکم در همین گروه"),
                  BotCommand(command="ludo", description="میز منچ در همین گروه"),
                  BotCommand(command="football", description="میز فوتبال در همین گروه"),
                  BotCommand(command="billiard", description="میز بیلیارد در همین گروه"),
                  BotCommand(command="divar", description="میز دیوار در همین گروه"),
                  BotCommand(command="snakes", description="میز مار و پله در همین گروه"),
                  BotCommand(command="esmfamil", description="اسم‌فامیل با داور هوش مصنوعی"),
                  BotCommand(command="lashgar", description="لشگر کاغذی؛ جنگ کاغذی دهه شصت"),
                  BotCommand(command="play", description="انتخاب بازی")]
UPDATES = ["message", "callback_query", "inline_query", "chosen_inline_result"]


async def _heal_webhook(bot: Bot) -> None:
    """بعد از به روزرسانی: اگر وبهوک هنوز دکمه ها (callback_query) را نمی گیرد، دوباره ثبتش کن."""
    try:
        info = await bot.get_webhook_info()
        if info.url and set(UPDATES) - set(info.allowed_updates or ["message"]):
            await setup(bot, drop=False)
            log.info("وبهوک AsoTas برای دکمه های گروه به روز شد")
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
