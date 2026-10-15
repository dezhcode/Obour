"""بازی در گروه های تلگرام: ربات یک «کارت میز» در گروه می فرستد و هر کس دکمهٔ «بنشین» را بزند سر میز می نشیند.

- /hokm، /ludo، /football (یا /play برای انتخاب بازی) در گروه میز آزاد می سازد؛ سازنده خودش می نشیند.
- با هر نشستن یا بلند شدن، متن کارت عوض می شود: چه کسانی نشسته اند (با منشن) و چند جای خالی مانده.
- وقتی میز پر شد یا سازنده «شروع» را زد، کارت «بازی شروع شد» می شود با دکمهٔ ورود به مینی اپ،
  به هر بازیکن در پیوی ربات پیام می رود و در خود گروه هم یک پیام فقط-برای-او (ephemeral).
- آخر بازی کارت نتیجه را نشان می دهد با دکمهٔ «میز تازه». میزی که ۱۵ دقیقه شروع نشود بسته می شود.
میزهای گروه همیشه آزاد اند (بدون امتیاز) تا با یک لمس اتفاقی از کسی امتیاز کم نشود.
"""
from __future__ import annotations

import logging
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, EphemeralMessageParameters, InlineKeyboardButton, InlineKeyboardMarkup, Message

from . import service
from .config import gc
from .db import GCDatabase
from .service import GCError

log = logging.getLogger(__name__)
router = Router(name="gameclub-groups")
GROUP = F.chat.type.in_({"group", "supergroup"})

GAMES = {
    "hokm": {"name": "حکم", "icon": "🃏", "cfg": {"game": "hokm", "mode": "free", "entry": 0, "target": 7}, "len": "تا ۷ دست"},
    "ludo": {"name": "منچ", "icon": "🎲", "cfg": {"mode": "free", "entry": 0, "players": 4, "pawns": 2}, "len": "۴ نفره · ۲ مهره"},
    "football": {"name": "فوتبال", "icon": "⚽", "cfg": {"game": "football", "mode": "free", "entry": 0, "target": 3}, "len": "تا ۳ گل"},
}
OPEN_TTL = 15 * 60       # میزی که این مدت شروع نشود بسته می شود
FD = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
fd = lambda n: str(n).translate(FD)  # noqa: E731


def mention(tg: int, name: str) -> str:
    # یوزرنیم ها فقط a-z، عدد و _ هستند؛ امن برای HTML
    return f'<a href="tg://user?id={int(tg)}">{name}</a>'


def app_link(game: str, code: str) -> str:
    """لینک مستقیم مینی اپ اصلی ربات (Main Mini App) که مستقیم سر همین میز باز می شود."""
    return f"https://t.me/{gc.username}?startapp={game}_{code}" if gc.username else ""


def _btn(text: str, style: str | None = None, **kw) -> InlineKeyboardButton:
    # رنگ دکمه (Bot API فوریه ۲۰۲۶)؛ تلگرام های قدیمی همان دکمهٔ ساده را نشان می دهند
    return InlineKeyboardButton(text=text, style=style, **kw)


# ---------- ساختن کارت ----------
async def _seats(db: GCDatabase, m: dict) -> list[dict]:
    """صندلی های پرشده به ترتیب نشستن: {tg, name} یا ربات {name, bot}."""
    if m["status"] == "lobby":
        return [{"tg": s["tg"], "name": s.get("name") or "بازیکن"} for s in m["state"].get("seats", [])]
    rows = {r["color"]: r for r in await db.match_players_named(m["id"])}
    out = []
    for c, p in (m["state"].get("players") or {}).items():
        r = rows.get(c)
        out.append({"tg": r["tg_id"], "name": r.get("name") or p.get("name")} if r and not p.get("bot") else {"name": p.get("name"), "bot": True, "color": c})
        out[-1]["color"] = c
    return out


async def render(db: GCDatabase, m: dict, row: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    g = GAMES[row["game"]]
    cfg, mid = m["cfg"], m["id"]
    need = int(cfg.get("players") or (4 if row["game"] == "hokm" else 2))
    seats = await _seats(db, m)
    host = next((s for s in seats if s.get("tg") == row["host"]), None)
    head = f"{g['icon']} <b>میز {g['name']}</b> · آزاد · {g['len']}"
    if m["status"] == "lobby":
        lines = [f"{fd(i + 1)}. {mention(s['tg'], s['name'])}" for i, s in enumerate(seats)]
        lines += [f"{fd(i + 1)}. ⬜ جای خالی" for i in range(len(seats), need)]
        free = need - len(seats)
        text = (f"{head}\nسازنده: {mention(row['host'], host['name']) if host else '—'}\n\n"
                f"<b>سر میز ({fd(len(seats))} از {fd(need)}):</b>\n" + "\n".join(lines) + "\n\n"
                + (f"{fd(free)} جای خالی مانده؛ «بنشین» را بزن." if free else "میز پر شد!"))
        kb = [[_btn("بنشین", "success", callback_data=f"gt:join:{mid}"), _btn("بلند شو", "danger", callback_data=f"gt:leave:{mid}")]]
        if len(seats) < need:
            kb.append([_btn("شروع؛ جای خالی را ربات پر کند", "primary", callback_data=f"gt:start:{mid}")])
        return text, InlineKeyboardMarkup(inline_keyboard=kb)
    humans = [mention(s["tg"], s["name"]) for s in seats if not s.get("bot")]
    bots = [s["name"] for s in seats if s.get("bot")]
    who = "، ".join(humans) + (f" و ربات‌ها: {'، '.join(bots)}" if bots else "")
    if m["status"] == "playing":
        text = f"{g['icon']} <b>بازی {g['name']} شروع شد!</b>\n\nبازیکن‌ها: {who}\n\nهر کس سر میز است «ورود به بازی» را بزند."
        link = app_link(row["game"], m.get("invite") or "")
        kb = [[_btn("ورود به بازی", "primary", url=link)]] if link else []
        return text, InlineKeyboardMarkup(inline_keyboard=kb) if kb else None
    again = InlineKeyboardMarkup(inline_keyboard=[[_btn(f"میز تازهٔ {g['name']}", "success", callback_data=f"gt:new:{row['game']}")]])
    if m["status"] == "cancelled":
        return f"{g['icon']} <b>میز {g['name']} بسته شد.</b>\nهر وقت خواستید میز تازه بسازید.", again
    st = m["state"]
    win_colors = service._winners(st)
    winners = [mention(s["tg"], s["name"]) if not s.get("bot") else s["name"] for s in seats if s.get("color") in win_colors]
    sc = st.get("score")
    score = f"\nنتیجه: {fd(sc[0])} – {fd(sc[1])}" if isinstance(sc, list) and len(sc) == 2 else ""
    res = f"🏆 برنده: {' و '.join(winners)}" if winners else "بازی بدون برنده تمام شد."
    return f"{g['icon']} <b>بازی {g['name']} تمام شد</b>\n\n{res}{score}\n\nبازیکن‌ها: {who}", again


# ---------- به روز کردن کارت (از دکمه ها یا هر تغییری در سرویس) ----------
_bot: Bot | None = None
_db: GCDatabase | None = None


def install(bot: Bot, db: GCDatabase) -> None:
    global _bot, _db
    _bot, _db = bot, db
    service.table_hook = refresh


async def refresh(db: GCDatabase, match_id: str) -> None:
    row = await db.group_table(match_id)
    if not row or not _bot:
        return
    m = await db.get_match(match_id)
    if not m:
        return
    status = {"lobby": "open", "playing": "playing", "over": "over", "cancelled": "closed"}.get(m["status"], "closed")
    text, kb = await render(db, m, row)
    if row["message_id"]:
        try:
            await _bot.edit_message_text(text, chat_id=row["chat_id"], message_id=row["message_id"], reply_markup=kb,
                                         disable_web_page_preview=True)
        except Exception as e:  # noqa: BLE001  (مثلا «message is not modified» یا پیام پاک شده)
            if "not modified" not in str(e):
                log.debug("کارت میز گروه به روز نشد", exc_info=True)
    # فقط بار اول که میز شروع می شود (یک پروسه برنده می شود) به بازیکن ها خبر می دهیم
    if status != row["status"] and await db.set_group_status(match_id, row["status"], status) and status == "playing":
        await _announce_start(db, m, row)


async def _announce_start(db: GCDatabase, m: dict, row: dict) -> None:
    g = GAMES[row["game"]]
    link = app_link(row["game"], m.get("invite") or "")
    title = row.get("chat_title") or "گروه"
    for s in await _seats(db, m):
        if s.get("bot"):
            continue
        tg = s["tg"]
        # ۱) پیوی ربات (اگر کاربر قبلا ربات را استارت کرده باشد)
        try:
            from .bot import open_kb
            await _bot.send_message(tg, f"{g['icon']} بازی <b>{g['name']}</b> در گروه «{_esc(title)}» شروع شد! بزن تا وارد شوی:",
                                    reply_markup=open_kb(f"{row['game']}.html", "ورود به بازی"))
        except Exception:  # noqa: BLE001
            pass
        # ۲) پیام فقط-برای-او داخل همان گروه (Ephemeral Messages)
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[_btn("ورود به بازی", "primary", url=link)]]) if link else None
            await _bot.send_message(row["chat_id"], f"{mention(tg, s['name'])}، بازی {g['name']} شروع شد! «ورود به بازی» را بزن.",
                                    reply_markup=kb, ephemeral_message_parameters=EphemeralMessageParameters(receiver_user_id=tg))
        except Exception:  # noqa: BLE001
            log.debug("پیام ephemeral نرفت", exc_info=True)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def expire(db: GCDatabase) -> None:
    """میزهای گروهی که مدتی شروع نشده اند بسته می شوند (سازنده بلند می شود = میز لغو)."""
    for row in await db.stale_group_tables(int(time.time()) - OPEN_TTL):
        m = await db.get_match(row["match_id"])
        if m and m["status"] == "lobby":
            try:
                await service.lobby_leave(db, row["host"], m)
            except GCError:
                pass
        await refresh(db, row["match_id"])


# ---------- دستورها و دکمه ها ----------
def _name(u) -> str:  # noqa: ANN001
    return " ".join(x for x in (u.first_name, u.last_name) if x).strip() or u.username or "بازیکن"


async def _ephemeral(message: Message, text: str) -> None:
    """جواب فقط برای کسی که دستور را فرستاده؛ اگر نشد، جواب عادی."""
    try:
        await message.answer(text, ephemeral_message_parameters=EphemeralMessageParameters(receiver_user_id=message.from_user.id))
    except Exception:  # noqa: BLE001
        await message.reply(text)


async def create(db: GCDatabase, bot: Bot, chat, user, game: str) -> str | None:  # noqa: ANN001
    """میز تازه در گروه؛ None یعنی ساخته شد، وگرنه متن خطا برای همان کاربر."""
    await expire(db)
    me = await db.player(user.id, _name(user), user.username)
    if me.get("banned"):
        return "حساب تو در Game Club مسدود شده است."
    if await db.open_group_table(chat.id, game):
        return f"یک میز {GAMES[game]['name']} همین الان در این گروه باز است؛ روی همان «بنشین» را بزن."
    try:
        r = await service.invite_create(db, user.id, dict(GAMES[game]["cfg"]))
    except GCError as e:
        return {"in_match": "تو الان سر یک میز دیگر هستی؛ اول آن را تمام کن."}.get(e.code, "میز ساخته نشد؛ دوباره امتحان کن.")
    await db.add_group_table(r["match"], chat.id, getattr(chat, "title", "") or "", game, user.id)
    m = await db.get_match(r["match"])
    row = await db.group_table(r["match"])
    text, kb = await render(db, m, row)
    sent = await bot.send_message(chat.id, text, reply_markup=kb, disable_web_page_preview=True)
    await db.set_group_message(r["match"], sent.message_id)
    return None


@router.message(GROUP, Command("hokm", "ludo", "football"))
async def on_game(message: Message, gdb: GCDatabase, bot: Bot) -> None:
    game = (message.text or "").split()[0].lstrip("/").split("@")[0].lower()
    if not message.from_user or game not in GAMES:
        return
    err = await create(gdb, bot, message.chat, message.from_user, game)
    if err:
        await _ephemeral(message, err)


@router.message(GROUP, Command("play", "start"))
async def on_play(message: Message) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[[_btn(f"{g['icon']} {g['name']}", "primary" if k == "hokm" else None, callback_data=f"gt:new:{k}")]
                                               for k, g in GAMES.items()])
    await message.answer("<b>Game Club</b>\nچه بازی‌ای بازی کنیم؟ هر کس بزند میز را می‌سازد و خودش اول می‌نشیند.", reply_markup=kb)


@router.callback_query(F.data.startswith("gt:"))
async def on_button(cq: CallbackQuery, gdb: GCDatabase, bot: Bot) -> None:
    parts = (cq.data or "").split(":", 2)
    act, arg = (parts + ["", ""])[1:3]
    u = cq.from_user
    msg = cq.message
    if act == "new":
        if arg not in GAMES or not msg:
            await cq.answer()
            return
        err = await create(gdb, bot, msg.chat, u, arg)
        await cq.answer(err or f"میز {GAMES[arg]['name']} ساخته شد و نشستی!", show_alert=bool(err))
        return
    await expire(gdb)
    row = await gdb.group_table(arg)
    m = await gdb.get_match(arg) if row else None
    if not row or not m:
        await cq.answer("این میز دیگر نیست.", show_alert=True)
        return
    await gdb.player(u.id, _name(u), u.username)
    try:
        if act == "join":
            p = await gdb.get_player(u.id) or {}
            if p.get("banned"):
                raise GCError("banned")
            await service.invite_join(gdb, u.id, m["invite"])
            await cq.answer("نشستی سر میز! وقتی پر شد بازی شروع می‌شود.")
        elif act == "leave":
            if not any(s["tg"] == u.id for s in m["state"].get("seats", [])) or m["status"] != "lobby":
                await cq.answer("تو سر این میز نیستی.")
                return
            await service.lobby_leave(gdb, u.id, m)
            await cq.answer("میز بسته شد." if u.id == row["host"] else "از میز بلند شدی.")
        elif act == "start":
            await service.lobby_start(gdb, u.id, m["id"])
            await cq.answer("بازی شروع شد!")
        else:
            await cq.answer()
            return
    except GCError as e:
        text = {"in_match": "تو الان سر یک میز دیگر هستی.", "full": "میز پر است.", "started": "این بازی شروع شده.",
                "not_host": "فقط سازندهٔ میز می‌تواند شروع کند.", "banned": "حساب تو مسدود است.",
                "busy": "یک لحظه بعد دوباره بزن.", "not_found": "این میز دیگر نیست."}.get(e.code, "نشد؛ دوباره امتحان کن.")
        await cq.answer(text, show_alert=True)
    await refresh(gdb, m["id"])
