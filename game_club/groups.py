"""بازی در گروه های تلگرام: ربات یک «کارت میز» در گروه می فرستد؛ دکمه ها داخل خود پیام اند
(پیام غنی Bot API 10.3 با بلوک دکمه)، نه کیبورد شیشه ای زیر پیام.

- /hokm، /ludo، /football، /billiard (یا /play برای انتخاب بازی) کارت «تنظیم میز» می فرستد: سازنده حالت بازی
  (طول بازی، تعداد بازیکن، مدل) را انتخاب می کند و «باز کردن میز» را می زند؛ سازنده خودش می نشیند.
- با هر نشستن یا بلند شدن، کارت عوض می شود: چه کسانی نشسته اند (با منشن) و چند جای خالی مانده.
- وقتی میز پر شد یا سازنده «شروع» را زد، دکمه های میز می روند و کارت «بازی شروع شد» می شود با اسم
  بازی، بازیکن ها و دکمهٔ «دیدن بازی» تا اعضای گروه بازی را زنده ببینند. به هر بازیکن در پیوی ربات
  و در خود گروه (پیام فقط-برای-او) خبر می رود.
- آخر بازی کارت نتیجه را نشان می دهد با دکمهٔ «میز تازه». میزی که ۱۵ دقیقه شروع نشود بسته می شود.
- همین کارت با @ربات hokm در هر چتی (حالت اینلاین) یا از مینی اپ («فرستادن به گروه») هم فرستاده می شود.
میزهای گروه همیشه آزاد اند (بدون امتیاز) تا با یک لمس اتفاقی از کسی امتیاز کم نشود.
"""
from __future__ import annotations

import logging
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    EphemeralMessageParameters,
    InlineQueryResultArticle,
    InputRichBlockButtons,
    InputRichBlockParagraph,
    InputRichMessage,
    InputRichMessageContent,
    Message,
    RichMessageButton,
)

from . import service
from . import style as st
from .config import gc
from .db import GCDatabase
from .service import GCError

log = logging.getLogger(__name__)
router = Router(name="gameclub-groups")
GROUP = F.chat.type.in_({"group", "supergroup"})

# opts: (کلید، عنوان، [(مقدار، برچسب)]) — همان حالت هایی که میز خصوصی مینی اپ دارد
GAMES = {
    "hokm": {"name": "حکم", "icon": "🃏", "base": {"game": "hokm", "mode": "free", "entry": 0},
             "opts": [("target", "طول بازی", [(3, "3 دست · سریع"), (7, "7 دست · کامل")])], "def": {"target": 7}},
    "ludo": {"name": "منچ", "icon": "🎲", "base": {"mode": "free", "entry": 0},
             "opts": [("players", "تعداد بازیکن", [(2, "2 نفره"), (4, "4 نفره")]),
                      ("pawns", "مدل بازی", [(2, "سریع · 2 مهره"), (4, "کلاسیک · 4 مهره")])],
             "def": {"players": 4, "pawns": 2}},
    "football": {"name": "فوتبال", "icon": "⚽", "base": {"game": "football", "mode": "free", "entry": 0},
                 "opts": [("target", "تا چند گل", [(2, "2 گل · خیلی سریع"), (3, "3 گل · سریع"), (5, "5 گل · کامل")]),
                          ("passes", "پاس‌ها", [(0, "بدون محدودیت"), (3, "3 پاس"), (6, "6 پاس")])], "def": {"target": 3, "passes": 0}},
    "billiard": {"name": "بیلیارد", "icon": "🎱", "base": {"game": "billiard", "mode": "free", "entry": 0},
                 "opts": [("players", "تعداد بازیکن", [(2, "2 نفره · رو در رو"), (4, "4 نفره · یاری")])], "def": {"players": 2}},
}
OPEN_TTL = 15 * 60       # میز یا کارت تنظیمی که این مدت شروع نشود بسته می شود
fd = str   # عددهای پیام های ربات لاتین اند


def cfg_of(game: str, picks: dict) -> dict:
    """تنظیم بازی از انتخاب های سازنده؛ فقط مقدارهای مجاز، بقیه پیش فرض."""
    g = GAMES[game]
    out = dict(g["base"])
    for key, _, opts in g["opts"]:
        v = picks.get(key)
        out[key] = v if v in [o[0] for o in opts] else g["def"][key]
    return out


def need_of(game: str, cfg: dict) -> int:
    return int(cfg.get("players") or 0) if game in ("ludo", "billiard") else 4 if game == "hokm" else 2


def summary(game: str, cfg: dict) -> str:
    n = fd(need_of(game, cfg))
    if game == "hokm":
        return f"آزاد · {n} نفره · تا {fd(cfg.get('target', 7))} دست"
    if game == "ludo":
        return f"آزاد · {n} نفره · {'کلاسیک' if cfg.get('pawns') == 4 else 'سریع'} ({fd(cfg.get('pawns', 2))} مهره)"
    if game == "billiard":
        return f"آزاد · {n} نفره · {'یاری (دو تیم دونفره)' if cfg.get('players') == 4 else 'رو در رو'} · ۸ توپ"
    return f"آزاد · {n} نفره · تا {fd(cfg.get('target', 3))} گل"


def app_link(game: str, code: str) -> str:
    """لینک مستقیم مینی اپ اصلی ربات (Main Mini App) که مستقیم سر همین میز باز می شود."""
    return f"https://t.me/{gc.username}?startapp={game}_{code}" if gc.username and code else ""


def watch_link(game: str, match_id: str) -> str:
    """«دیدن بازی»: صفحهٔ بازی در حالت تماشا (بازیکن خودِ میز با همین لینک بازی خودش را باز می کند)."""
    return f"https://t.me/{gc.username}?startapp=w_{game}_{match_id}" if gc.username else ""


# ---------- اجزای پیام غنی (قالب متنی عبور در یک پاراگراف + ردیف دکمه های داخل پیام) ----------
OPT_ICON = {"target": "time", "players": "users", "pawns": "ludo", "passes": "users"}


def who(tg: int, name: str) -> list:
    return [st.FSI, st.M(tg, name), st.PDI]


def _para(parts: list) -> InputRichBlockParagraph:
    return InputRichBlockParagraph(text=st.to_rich(parts))


def _bt(key: str | None, label: str, style: str | None = None, **kw) -> RichMessageButton:
    """دکمهٔ داخل کارت گروه: فقط متن، بدون ایموجی (key فقط برای خوانایی کد می ماند)."""
    return st.rich_button(None, label, style, **kw)


def _row(*btns: RichMessageButton) -> InputRichBlockButtons:
    return InputRichBlockButtons(buttons=list(btns), align="center")


def _rm(blocks: list) -> InputRichMessage:
    return InputRichMessage(blocks=blocks, is_rtl=True)


def card(parts: list, *rows: InputRichBlockButtons) -> InputRichMessage:
    return _rm([_para(parts), *rows])


def plain(rm: InputRichMessage) -> str:
    """متن ساده پیام غنی (برای آزمون ها و لاگ)."""
    def walk(x) -> str:  # noqa: ANN001
        if isinstance(x, str):
            return x
        if isinstance(x, list):
            return "".join(walk(y) for y in x)
        if isinstance(x, dict):
            return " ".join(walk(v) for k, v in x.items() if k in ("text", "blocks", "items", "buttons", "alternative_text"))
        return ""
    return walk(rm.model_dump(exclude_none=True).get("blocks", []))


def buttons(rm: InputRichMessage) -> list[RichMessageButton]:
    out = []
    for b in rm.blocks or []:
        if isinstance(b, InputRichBlockButtons):
            out += b.buttons
    return out


# ---------- کارت ها ----------
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


def _player_line(s: dict) -> list:
    return ["• ", st.E("robot"), " ", st.iso(s["name"])] if s.get("bot") else ["• ", *who(s["tg"], s["name"])]


async def setup_card(db: GCDatabase, d: dict) -> InputRichMessage:
    """کارت تنظیم میز: فقط سازنده حالت را عوض می کند و میز را باز می کند."""
    game, tok = d["game"], d["token"]
    g, cfg = GAMES[game], cfg_of(game, d["cfg"])
    host = await db.get_player(d["host"]) or {}
    head = st.frame(game, f"میز {g['name']}", "تنظیم میز", [
        ["سازنده: ", *who(d["host"], host.get("name") or "بازیکن")],
        "حالت بازی رو انتخاب کن و «باز کردن میز» رو بزن تا بقیه بپرن سر میز 😎",
    ], foot=("gear", "حالت فعلی", summary(game, cfg)))
    blocks = [_para(head)]
    for key, label, opts in g["opts"]:
        blocks.append(_para([st.E(OPT_ICON.get(key, "gear")), " ", st.B(label)]))
        blocks.append(_row(*[_bt(None, ("✓ " if cfg[key] == v else "") + lab, "primary" if cfg[key] == v else None,
                                 callback_data=f"gs:{key}={v}:{tok}") for v, lab in opts]))
    blocks.append(_row(_bt("play", "باز کردن میز", "success", callback_data=f"gs:open:{tok}"),
                       _bt("cancel", "لغو", "danger", callback_data=f"gs:cancel:{tok}")))
    return _rm(blocks)


def closed_card(game: str, text: str = "میز جمع شد.") -> InputRichMessage:
    g = GAMES[game]
    return card(st.frame(game, f"میز {g['name']}", "بسته شد", [text], foot=(None, None, "هر وقت دلتون خواست، یه میز تازه بچینید.")),
                _row(_bt("new", f"میز تازهٔ {g['name']}", "success", callback_data=f"gt:new:{game}")))


async def render(db: GCDatabase, m: dict, row: dict) -> InputRichMessage:
    g, game = GAMES[row["game"]], row["game"]
    cfg, mid = m["cfg"], m["id"]
    need = need_of(game, cfg)
    seats = await _seats(db, m)
    if m["status"] == "lobby":
        host = next((s for s in seats if s.get("tg") == row["host"]), None)
        free = need - len(seats)
        lines = [["سازنده: ", *(who(host["tg"], host["name"]) if host else ["—"])], "",
                 [st.E("users"), " ", st.B(f"سر میز ({fd(len(seats))} از {fd(need)})")]]
        lines += [[f"{fd(i + 1)}. ", *who(s["tg"], s["name"])] for i, s in enumerate(seats)]
        lines += [[f"{fd(i + 1)}. ", st.E("seat"), " خالی؛ منتظر یه قهرمان"] for i in range(len(seats), need)]
        foot = ("seat", "جای خالی", f"{fd(free)} صندلی مونده؛ «بشین» رو بزن تا جا نموندی!") if free else ("party", "میز پر شد", "الان بازی شروع می‌شه؛ کمربندا رو ببندید 😄")
        rows = [_row(_bt("seat", "بشین", "success", callback_data=f"gt:join:{mid}"),
                     _bt("leave", "بلند شو", "danger", callback_data=f"gt:leave:{mid}"))]
        if free:
            rows.append(_row(_bt("robot", "شروع؛ جای خالی با ربات", "primary", callback_data=f"gt:start:{mid}")))
        return card(st.frame(game, f"میز {g['name']}", summary(game, cfg), lines, foot), *rows)
    players = [[st.E("users"), " ", st.B("بازیکن‌ها")], *[_player_line(s) for s in seats]]
    if m["status"] == "playing":
        link = watch_link(game, mid)
        return card(st.frame(game, f"بازی {g['name']}", f"شروع شد · {summary(game, cfg)}", players,
                             foot=("watch", "تماشا", "بقیه هم زنده می‌بینن؛ فقط تقلب نرسونید 😄")),
                    *([_row(_bt("watch", "دیدن بازی", "primary", url=link))] if link else []))
    if m["status"] == "cancelled":
        return closed_card(game)
    state = m["state"]
    win_colors = service._winners(state)
    winners = [s for s in seats if s.get("color") in win_colors]
    res: list = [st.E("trophy"), " برنده: "]
    for i, s in enumerate(winners):
        res += ([" و "] if i else []) + (who(s["tg"], s["name"]) if not s.get("bot") else [st.iso(s["name"])])
    lines = [res if winners else "بازی بی‌برنده تموم شد؛ صلح جهانی برقرار شد 🕊"]
    sc = state.get("score")
    if isinstance(sc, list) and len(sc) == 2:
        lines.append([st.E("score"), f" نتیجه: {fd(sc[0])} – {fd(sc[1])}"])
    # پایان بازی: فقط خروجی اطلاعات میز (بدون دکمه)؛ برنده ها در فهرست بازیکن ها نشان دارند
    players = [[st.E("users"), " ", st.B("بازیکن‌ها")],
               *[_player_line(s) + ([" ", st.E("trophy")] if s.get("color") in win_colors else []) for s in seats]]
    start = state.get("started") or m.get("created_at") or time.time()
    mins = max(1, round(((m.get("updated_at") or time.time()) - start) / 60))
    return card(st.frame(game, f"بازی {g['name']}", f"تموم شد · {summary(game, cfg)}", lines + [""] + players,
                         foot=("time", "مدت بازی", f"{fd(mins)} دقیقه")))


# ---------- به روز کردن کارت (از دکمه ها یا هر تغییری در سرویس) ----------
_bot: Bot | None = None
_db: GCDatabase | None = None


def install(bot: Bot, db: GCDatabase) -> None:
    global _bot, _db
    _bot, _db = bot, db
    service.table_hook = refresh


def _where(row: dict) -> dict | None:
    if row.get("inline_message_id"):
        return {"inline_message_id": row["inline_message_id"]}
    if row.get("message_id"):
        return {"chat_id": row["chat_id"], "message_id": row["message_id"]}
    return None


async def _edit(where: dict | None, rm: InputRichMessage) -> None:
    if not where or not _bot:
        return
    try:
        await _bot.edit_message_text(rich_message=rm, parse_mode=None, link_preview_options=None,
                                     disable_web_page_preview=None, **where)
    except Exception as e:  # noqa: BLE001  (مثلا «message is not modified» یا پیام پاک شده)
        if "not modified" not in str(e):
            log.debug("کارت میز گروه به روز نشد", exc_info=True)


async def _send(chat_id: int, rm: InputRichMessage, **kw):  # noqa: ANN202
    return await _bot.send_rich_message(chat_id=chat_id, rich_message=rm, **kw)


async def refresh(db: GCDatabase, match_id: str) -> None:
    row = await db.group_table(match_id)
    if not row or not _bot:
        return
    m = await db.get_match(match_id)
    if not m:
        return
    status = {"lobby": "open", "playing": "playing", "over": "over", "cancelled": "closed"}.get(m["status"], "closed")
    await _edit(_where(row), await render(db, m, row))
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
            text = st.to_html(st.frame(row["game"], f"بازی {g['name']}", "شروع شد", [
                ["بازی توی «", st.iso(title), "» شروع شد؛ همه منتظر توان، دیر نکن! 🏃"]], foot=("play", "ورود", "دکمهٔ زیر رو بزن")))
            await _bot.send_message(tg, text, reply_markup=open_kb(f"{row['game']}.html", "ورود به بازی", "play"))
        except Exception:  # noqa: BLE001
            pass
        # ۲) پیام فقط-برای-او داخل همان گروه (Ephemeral Messages)؛ کارت اینلاین چت را نمی شناسد
        if not row["chat_id"]:
            continue
        try:
            rm = card(st.frame(row["game"], f"بازی {g['name']}", "شروع شد", [[*who(tg, s["name"]), "، میز پر شد و بازی شروع شد! بدو بیا 🏃"]],
                               foot=("play", "ورود", "این پیام رو فقط تو می‌بینی؛ هیس 🤫")),
                      *([_row(_bt("play", "ورود به بازی", "primary", url=link))] if link else []))
            await _send(row["chat_id"], rm, ephemeral_message_parameters=EphemeralMessageParameters(receiver_user_id=tg))
        except Exception:  # noqa: BLE001
            log.debug("پیام ephemeral نرفت", exc_info=True)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def expire(db: GCDatabase) -> None:
    """کارت تنظیم یا میزی که مدتی شروع نشده بسته می شود (سازنده بلند می شود = میز لغو)."""
    before = int(time.time()) - OPEN_TTL
    for d in await db.stale_drafts(before):
        if await db.claim_draft(d["token"], "closed"):
            await _edit(_where(d), closed_card(d["game"], "کسی نیومد میز رو باز کنه؛ میز خوابش برد 😴"))
    for row in await db.stale_group_tables(before):
        m = await db.get_match(row["match_id"])
        if m and m["status"] == "lobby":
            try:
                await service.lobby_leave(db, row["host"], m)
            except GCError:
                pass
        await refresh(db, row["match_id"])


# ---------- ساختن و باز کردن میز ----------
def _name(u) -> str:  # noqa: ANN001
    return " ".join(x for x in (u.first_name, u.last_name) if x).strip() or u.username or "بازیکن"


async def _ephemeral(message: Message, text: str) -> None:
    """جواب فقط برای کسی که دستور را فرستاده؛ اگر نشد، جواب عادی."""
    try:
        await message.answer(text, ephemeral_message_parameters=EphemeralMessageParameters(receiver_user_id=message.from_user.id))
    except Exception:  # noqa: BLE001
        await message.reply(text)


async def create(db: GCDatabase, bot: Bot, chat, user, game: str) -> str | None:  # noqa: ANN001
    """کارت تنظیم میز تازه در گروه؛ None یعنی فرستاده شد، وگرنه متن خطا برای همان کاربر."""
    await expire(db)
    me = await db.player(user.id, _name(user), user.username)
    if me.get("banned"):
        return "حسابت توی Game Club مسدوده 🚫"
    name = GAMES[game]["name"]
    if await db.open_group_table(chat.id, game):
        return f"یه میز {name} همین الان تو این گروه بازه؛ برو همون‌جا «بشین» رو بزن 😉"
    if await db.setup_draft_in(chat.id, game, int(time.time()) - OPEN_TTL):
        return f"یه میز {name} داره چیده می‌شه؛ صبر کن سازنده‌ش بازش کنه."
    token = await db.new_draft(user.id, game, dict(GAMES[game]["def"]), chat.id, getattr(chat, "title", "") or "")
    sent = await _send(chat.id, await setup_card(db, await db.draft(token)))
    await db.set_draft(token, message_id=sent.message_id)
    return None


async def open_table(db: GCDatabase, d: dict) -> str | None:
    """«باز کردن میز»: میز واقعی با تنظیم انتخاب شده؛ همان پیام کارت میز می شود."""
    name = GAMES[d["game"]]["name"]
    if d["chat_id"] and await db.open_group_table(d["chat_id"], d["game"]):
        return f"یه میز {name} همین الان تو این گروه بازه."
    if not await db.claim_draft(d["token"], "open"):
        return "این کارت دیگه از کار افتاده."
    try:
        r = await service.invite_create(db, d["host"], cfg_of(d["game"], d["cfg"]))
    except GCError as e:
        await db.unclaim_draft(d["token"])
        return {"in_match": "تو الان سر یه میز دیگه‌ای؛ اول اونو تموم کن، بعد بیا 😅"}.get(e.code, "میز ساخته نشد؛ یه بار دیگه امتحان کن.")
    mid = r["match"]
    await db.add_group_table(mid, d["chat_id"], d["chat_title"], d["game"], d["host"])
    if d["message_id"]:
        await db.set_group_message(mid, d["message_id"])
    if d["inline_message_id"]:
        await db.set_group_inline(mid, d["inline_message_id"])
    await db.set_draft(d["token"], match_id=mid)
    await refresh(db, mid)
    return None


@router.message(GROUP, Command("hokm", "ludo", "football", "billiard"))
async def on_game(message: Message, gdb: GCDatabase, bot: Bot) -> None:
    game = (message.text or "").split()[0].lstrip("/").split("@")[0].lower()
    if not message.from_user or game not in GAMES:
        return
    err = await create(gdb, bot, message.chat, message.from_user, game)
    if err:
        await _ephemeral(message, err)


@router.message(GROUP, Command("play", "start"))
async def on_play(message: Message) -> None:
    await _send(message.chat.id, card(
        st.frame("brand", "Game Club", "بازی در گروه", ["چی بازی کنیم؟ هر کی زودتر بزنه، میز رو می‌چینه و خودش اول می‌شینه."],
                 foot=("group", "بازی‌ها", "حکم، منچ، فوتبال و بیلیارد؛ همه مجانی، فقط سر کل‌کل 😄")),
        _row(*[_bt(k, g["name"], "primary" if k == "hokm" else None, callback_data=f"gt:new:{k}") for k, g in GAMES.items()])))


async def _draft_err(cq: CallbackQuery, text: str) -> None:
    await cq.answer(text, show_alert=True)


@router.callback_query(F.data.startswith("gs:"))
async def on_setup(cq: CallbackQuery, gdb: GCDatabase) -> None:
    """دکمه های کارت تنظیم: gs:<کلید=مقدار|open|cancel>:<توکن>"""
    act, _, token = (cq.data or "")[3:].partition(":")
    d = await gdb.draft(token)
    if not d or d["status"] != "setup":
        return await _draft_err(cq, "این کارت دیگه از کار افتاده.")
    if cq.from_user.id != d["host"]:
        return await _draft_err(cq, "فقط سازنده تنظیمش می‌کنه 😉 صبر کن میز باز شه، بعد «بشین» رو بزن.")
    # کارت اینلاین یا فرستاده از مینی اپ: شناسهٔ پیام از همین لمس معلوم می شود
    if cq.inline_message_id and not d["inline_message_id"]:
        await gdb.set_draft(token, inline_message_id=cq.inline_message_id)
        d["inline_message_id"] = cq.inline_message_id
    if act == "cancel":
        if await gdb.claim_draft(token, "closed"):
            await _edit(_where(d), closed_card(d["game"], "سازنده پشیمون شد و میز رو جمع کرد 🤷"))
        await cq.answer("جمعش کردیم")
        return
    if act == "open":
        err = await open_table(gdb, d)
        await cq.answer(err or "میز باز شد و نشستی! حالا بقیه بپرن سر میز 🎉", show_alert=bool(err))
        return
    key, _, val = act.partition("=")
    opts = {k: [o[0] for o in o_] for k, _, o_ in GAMES[d["game"]]["opts"]}
    if key not in opts or not val.isdigit() or int(val) not in opts[key]:
        await cq.answer()
        return
    d["cfg"] = {**cfg_of(d["game"], d["cfg"]), key: int(val)}
    await gdb.set_draft(token, cfg={k: d["cfg"][k] for k in opts})
    await cq.answer()
    await _edit(_where(d), await setup_card(gdb, d))


async def _act(cq: CallbackQuery, gdb: GCDatabase, act: str, match_id: str) -> None:
    """بشین، بلند شو و شروع روی میزی که باز شده (گروهی یا اینلاین)."""
    u = cq.from_user
    row = await gdb.group_table(match_id)
    m = await gdb.get_match(match_id) if row else None
    if not row or not m:
        await cq.answer("این میز دیگه نیست 👻", show_alert=True)
        return
    await gdb.player(u.id, _name(u), u.username)
    try:
        if act == "join":
            if m["status"] == "lobby" and any(s["tg"] == u.id for s in m["state"].get("seats", [])):
                await cq.answer("تو که همین الان نشستی! 😄")
                return
            p = await gdb.get_player(u.id) or {}
            if p.get("banned"):
                raise GCError("banned")
            await service.invite_join(gdb, u.id, m["invite"])
            await cq.answer("نشستی! حالا فقط منتظر بقیه‌ایم 😎")
        elif act == "leave":
            if not any(s["tg"] == u.id for s in m["state"].get("seats", [])) or m["status"] != "lobby":
                await cq.answer("تو که سر این میز نیستی 🤔")
                return
            await service.lobby_leave(gdb, u.id, m)
            await cq.answer("میز جمع شد." if u.id == row["host"] else "بلند شدی؛ جات خالی 🥲")
        elif act == "start":
            await service.lobby_start(gdb, u.id, m["id"])
            await cq.answer("بزن بریم! 🚀")
        else:
            await cq.answer()
            return
    except GCError as e:
        text = {"in_match": "تو الان سر یه میز دیگه‌ای 😅", "full": "میز پره؛ دفعهٔ بعد زودتر بجنب!", "started": "دیر رسیدی؛ بازی شروع شده 😅",
                "not_host": "فقط سازندهٔ میز می‌تونه شروع کنه.", "banned": "حسابت مسدوده 🚫",
                "busy": "یه لحظه صبر کن، دوباره بزن.", "not_found": "این میز دیگه نیست 👻"}.get(e.code, "نشد؛ یه بار دیگه بزن.")
        await cq.answer(text, show_alert=True)
    await refresh(gdb, m["id"])


@router.callback_query(F.data.startswith("gt:"))
async def on_button(cq: CallbackQuery, gdb: GCDatabase, bot: Bot) -> None:
    act, _, arg = (cq.data or "")[3:].partition(":")
    u = cq.from_user
    if act == "new":
        if arg not in GAMES:
            await cq.answer()
            return
        if cq.inline_message_id:   # کارت اینلاین: کارت تنظیم تازه در همان پیام، با کسی که دکمه را زد
            me = await gdb.player(u.id, _name(u), u.username)
            if me.get("banned"):
                return await _draft_err(cq, "حسابت توی Game Club مسدوده 🚫")
            token = await gdb.new_draft(u.id, arg, dict(GAMES[arg]["def"]))
            await gdb.set_draft(token, inline_message_id=cq.inline_message_id)
            await cq.answer("حالت بازی رو انتخاب کن و میز رو باز کن 😉")
            await _edit({"inline_message_id": cq.inline_message_id}, await setup_card(gdb, await gdb.draft(token)))
            return
        if not cq.message:
            await cq.answer()
            return
        err = await create(gdb, bot, cq.message.chat, u, arg)
        await cq.answer(err or "حالت بازی رو انتخاب کن و میز رو باز کن 😉", show_alert=bool(err))
        return
    await expire(gdb)
    await _act(cq, gdb, act, arg)


@router.callback_query(F.data.startswith("gi:"))
async def on_old_inline(cq: CallbackQuery) -> None:
    """کارت های اینلاین نسخهٔ قبل."""
    await cq.answer("این کارت قدیمیه؛ یه میز تازه بساز.", show_alert=True)


# ---------- حالت اینلاین (@ربات hokm در هر چتی) و «فرستادن به گروه» از مینی اپ ----------
INLINE_ALIASES = {"hokm": ("hokm", "حکم", "hk"), "ludo": ("ludo", "منچ", "mench"), "football": ("football", "فوتبال", "fb", "soccer"),
                  "billiard": ("billiard", "بیلیارد", "pool", "8ball", "snooker")}


async def _article(db: GCDatabase, host: int, game: str) -> InlineQueryResultArticle:
    """کارت تنظیم میز به شکل نتیجهٔ اینلاین؛ سازنده همان کسی است که فرستاده."""
    g = GAMES[game]
    token = await db.new_draft(host, game, dict(g["def"]))
    return InlineQueryResultArticle(
        id=token, title=f"{g['icon']} میز {g['name']} بساز",
        description=f"{summary(game, cfg_of(game, g['def']))} · حالتش با خودت",
        input_message_content=InputRichMessageContent(rich_message=await setup_card(db, await db.draft(token))))


@router.inline_query()
async def on_inline(iq, gdb: GCDatabase) -> None:  # noqa: ANN001
    u = iq.from_user
    me = await gdb.player(u.id, _name(u), u.username)
    if me.get("banned"):
        await iq.answer([], cache_time=5, is_personal=True)
        return
    q = (iq.query or "").strip().lower()
    games = [k for k, al in INLINE_ALIASES.items() if not q or any(a.startswith(q) or q.startswith(a) for a in al)] or list(GAMES)
    await iq.answer([await _article(gdb, u.id, g) for g in games], cache_time=0, is_personal=True)


@router.chosen_inline_result()
async def on_chosen(cr, gdb: GCDatabase) -> None:  # noqa: ANN001
    """اگر inline feedback در BotFather روشن باشد، شناسهٔ پیام از همان لحظه معلوم است (برای بستن کارت کهنه)."""
    if cr.inline_message_id and await gdb.draft(cr.result_id):
        await gdb.set_draft(cr.result_id, inline_message_id=cr.inline_message_id)


async def prepare_share(db: GCDatabase, tg: int, game: str) -> str:
    """کارت تنظیم میز آماده برای Telegram.WebApp.shareMessage (کاربر خودش گروه یا چت را انتخاب می کند)."""
    if game not in GAMES:
        raise GCError("bad_game")
    if not _bot:
        raise GCError("no_bot")
    prepared = await _bot.save_prepared_inline_message(user_id=tg, result=await _article(db, tg, game),
                                                       allow_user_chats=True, allow_group_chats=True,
                                                       allow_bot_chats=False, allow_channel_chats=False)
    return prepared.id
