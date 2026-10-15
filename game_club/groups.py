"""بازی در گروه های تلگرام: ربات یک «کارت میز» در گروه می فرستد؛ دکمه ها داخل خود پیام اند
(پیام غنی Bot API 10.3 با بلوک دکمه)، نه کیبورد شیشه ای زیر پیام.

- /hokm، /ludo، /football (یا /play برای انتخاب بازی) کارت «تنظیم میز» می فرستد: سازنده حالت بازی
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
    InputRichBlockFooter,
    InputRichBlockList,
    InputRichBlockListItem,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichMessage,
    InputRichMessageContent,
    Message,
    RichMessageButton,
    RichTextBold,
    RichTextTextMention,
    User,
)

from . import service
from .config import gc
from .db import GCDatabase
from .service import GCError

log = logging.getLogger(__name__)
router = Router(name="gameclub-groups")
GROUP = F.chat.type.in_({"group", "supergroup"})

# opts: (کلید، عنوان، [(مقدار، برچسب)]) — همان حالت هایی که میز خصوصی مینی اپ دارد
GAMES = {
    "hokm": {"name": "حکم", "icon": "🃏", "base": {"game": "hokm", "mode": "free", "entry": 0},
             "opts": [("target", "طول بازی", [(3, "۳ دست · سریع"), (7, "۷ دست · کامل")])], "def": {"target": 7}},
    "ludo": {"name": "منچ", "icon": "🎲", "base": {"mode": "free", "entry": 0},
             "opts": [("players", "تعداد بازیکن", [(2, "۲ نفره"), (4, "۴ نفره")]),
                      ("pawns", "مدل بازی", [(2, "سریع · ۲ مهره"), (4, "کلاسیک · ۴ مهره")])],
             "def": {"players": 4, "pawns": 2}},
    "football": {"name": "فوتبال", "icon": "⚽", "base": {"game": "football", "mode": "free", "entry": 0},
                 "opts": [("target", "تا چند گل", [(3, "۳ گل · سریع"), (5, "۵ گل · کامل")])], "def": {"target": 3}},
}
OPEN_TTL = 15 * 60       # میز یا کارت تنظیمی که این مدت شروع نشود بسته می شود
FD = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
fd = lambda n: str(n).translate(FD)  # noqa: E731


def cfg_of(game: str, picks: dict) -> dict:
    """تنظیم بازی از انتخاب های سازنده؛ فقط مقدارهای مجاز، بقیه پیش فرض."""
    g = GAMES[game]
    out = dict(g["base"])
    for key, _, opts in g["opts"]:
        v = picks.get(key)
        out[key] = v if v in [o[0] for o in opts] else g["def"][key]
    return out


def need_of(game: str, cfg: dict) -> int:
    return int(cfg.get("players") or 0) if game == "ludo" else 4 if game == "hokm" else 2


def summary(game: str, cfg: dict) -> str:
    n = fd(need_of(game, cfg))
    if game == "hokm":
        return f"آزاد · {n} نفره · تا {fd(cfg.get('target', 7))} دست"
    if game == "ludo":
        return f"آزاد · {n} نفره · {'کلاسیک' if cfg.get('pawns') == 4 else 'سریع'} ({fd(cfg.get('pawns', 2))} مهره)"
    return f"آزاد · {n} نفره · تا {fd(cfg.get('target', 3))} گل"


def app_link(game: str, code: str) -> str:
    """لینک مستقیم مینی اپ اصلی ربات (Main Mini App) که مستقیم سر همین میز باز می شود."""
    return f"https://t.me/{gc.username}?startapp={game}_{code}" if gc.username and code else ""


def watch_link(game: str, match_id: str) -> str:
    """«دیدن بازی»: صفحهٔ بازی در حالت تماشا (بازیکن خودِ میز با همین لینک بازی خودش را باز می کند)."""
    return f"https://t.me/{gc.username}?startapp=w_{game}_{match_id}" if gc.username else ""


# ---------- اجزای پیام غنی ----------
def mention(tg: int, name: str) -> RichTextTextMention:
    return RichTextTextMention(text=name or "بازیکن", user=User(id=int(tg), is_bot=False, first_name=name or "بازیکن"))


def _p(*parts) -> InputRichBlockParagraph:  # noqa: ANN002
    return InputRichBlockParagraph(text=list(parts))


def _h(text: str, size: int = 2) -> InputRichBlockSectionHeading:
    return InputRichBlockSectionHeading(text=text, size=size)


def _b(text: str, style: str | None = None, **kw) -> RichMessageButton:
    return RichMessageButton(text=text, style=style, **kw)


def _row(*buttons: RichMessageButton) -> InputRichBlockButtons:
    return InputRichBlockButtons(buttons=list(buttons), align="center")


def _list(items: list) -> InputRichBlockList:
    return InputRichBlockList(items=[InputRichBlockListItem(blocks=[_p(*(x if isinstance(x, list) else [x]))]) for x in items])


def _rm(blocks: list) -> InputRichMessage:
    return InputRichMessage(blocks=blocks, is_rtl=True)


def plain(rm: InputRichMessage) -> str:
    """متن ساده پیام غنی (برای آزمون ها و لاگ)."""
    def walk(x) -> str:  # noqa: ANN001
        if isinstance(x, str):
            return x
        if isinstance(x, list):
            return "".join(walk(y) for y in x)
        if isinstance(x, dict):
            return " ".join(walk(v) for k, v in x.items() if k in ("text", "blocks", "items", "buttons"))
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


async def setup_card(db: GCDatabase, d: dict) -> InputRichMessage:
    """کارت تنظیم میز: فقط سازنده حالت را عوض می کند و میز را باز می کند."""
    g, cfg, tok = GAMES[d["game"]], cfg_of(d["game"], d["cfg"]), d["token"]
    host = await db.get_player(d["host"]) or {}
    blocks = [_h(f"{g['icon']} میز {g['name']}"),
              _p("سازنده: ", mention(d["host"], host.get("name") or "بازیکن")),
              _p("حالت بازی را انتخاب کن و «باز کردن میز» را بزن تا بقیه بنشینند.")]
    for key, label, opts in g["opts"]:
        blocks.append(_p(RichTextBold(text=label)))
        blocks.append(_row(*[_b(("✓ " if cfg[key] == v else "") + lab, "primary" if cfg[key] == v else None,
                                callback_data=f"gs:{key}={v}:{tok}") for v, lab in opts]))
    blocks.append(_row(_b("باز کردن میز", "success", callback_data=f"gs:open:{tok}"),
                       _b("لغو", "danger", callback_data=f"gs:cancel:{tok}")))
    blocks.append(InputRichBlockFooter(text=f"{summary(d['game'], cfg)} · فقط سازنده تنظیم می‌کند"))
    return _rm(blocks)


def closed_card(game: str, text: str = "هر وقت خواستید میز تازه بسازید.") -> InputRichMessage:
    g = GAMES[game]
    return _rm([_h(f"{g['icon']} میز {g['name']} بسته شد"), _p(text),
                _row(_b(f"میز تازهٔ {g['name']}", "success", callback_data=f"gt:new:{game}"))])


async def render(db: GCDatabase, m: dict, row: dict) -> InputRichMessage:
    g, game = GAMES[row["game"]], row["game"]
    cfg, mid = m["cfg"], m["id"]
    need = need_of(game, cfg)
    seats = await _seats(db, m)
    if m["status"] == "lobby":
        host = next((s for s in seats if s.get("tg") == row["host"]), None)
        free = need - len(seats)
        items = [mention(s["tg"], s["name"]) for s in seats] + ["⬜ جای خالی"] * free
        kb = [_row(_b("بنشین", "success", callback_data=f"gt:join:{mid}"), _b("بلند شو", "danger", callback_data=f"gt:leave:{mid}"))]
        if free:
            kb.append(_row(_b("شروع؛ جای خالی را ربات پر کند", "primary", callback_data=f"gt:start:{mid}")))
        return _rm([_h(f"{g['icon']} میز {g['name']}"), _p(summary(game, cfg)),
                    _p("سازنده: ", mention(row["host"], host["name"]) if host else "—"),
                    _p(RichTextBold(text=f"سر میز ({fd(len(seats))} از {fd(need)}):")), _list(items),
                    _p(f"{fd(free)} جای خالی مانده؛ «بنشین» را بزن." if free else "میز پر شد!"), *kb])
    players = [mention(s["tg"], s["name"]) if not s.get("bot") else f"🤖 {s['name']}" for s in seats]
    if m["status"] == "playing":
        link = watch_link(game, mid)
        return _rm([_h(f"{g['icon']} بازی {g['name']} شروع شد"), _p(summary(game, cfg)),
                    _p(RichTextBold(text="بازیکن‌ها:")), _list(players),
                    *([_row(_b("👀 دیدن بازی", "primary", url=link))] if link else []),
                    InputRichBlockFooter(text="اعضای گروه بازی را زنده می‌بینند؛ بازیکن‌ها با همین دکمه وارد بازی می‌شوند.")])
    again = _row(_b(f"میز تازهٔ {g['name']}", "success", callback_data=f"gt:new:{game}"))
    if m["status"] == "cancelled":
        return closed_card(game)
    st = m["state"]
    win_colors = service._winners(st)
    winners = [mention(s["tg"], s["name"]) if not s.get("bot") else s["name"] for s in seats if s.get("color") in win_colors]
    sc = st.get("score")
    res = ["🏆 برنده: "] + [x for i, w in enumerate(winners) for x in ([" و "] if i else []) + [w]] if winners else ["بازی بدون برنده تمام شد."]
    blocks = [_h(f"{g['icon']} بازی {g['name']} تمام شد"), _p(*res)]
    if isinstance(sc, list) and len(sc) == 2:
        blocks.append(_p(f"نتیجه: {fd(sc[0])} – {fd(sc[1])}"))
    return _rm(blocks + [_p(RichTextBold(text="بازیکن‌ها:")), _list(players), again])


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
            await _bot.send_message(tg, f"{g['icon']} بازی <b>{g['name']}</b> در «{_esc(title)}» شروع شد! بزن تا وارد شوی:",
                                    reply_markup=open_kb(f"{row['game']}.html", "ورود به بازی"))
        except Exception:  # noqa: BLE001
            pass
        # ۲) پیام فقط-برای-او داخل همان گروه (Ephemeral Messages)؛ کارت اینلاین چت را نمی شناسد
        if not row["chat_id"]:
            continue
        try:
            rm = _rm([_p(mention(tg, s["name"]), f"، بازی {g['name']} شروع شد!"),
                      *([_row(_b("ورود به بازی", "primary", url=link))] if link else [])])
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
            await _edit(_where(d), closed_card(d["game"], "کسی میز را باز نکرد؛ هر وقت خواستید دوباره بسازید."))
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
        return "حساب تو در Game Club مسدود شده است."
    name = GAMES[game]["name"]
    if await db.open_group_table(chat.id, game):
        return f"یک میز {name} همین الان در این گروه باز است؛ روی همان «بنشین» را بزن."
    if await db.setup_draft_in(chat.id, game, int(time.time()) - OPEN_TTL):
        return f"یک میز {name} همین الان در حال تنظیم است؛ صبر کن سازنده‌اش بازش کند."
    token = await db.new_draft(user.id, game, dict(GAMES[game]["def"]), chat.id, getattr(chat, "title", "") or "")
    sent = await _send(chat.id, await setup_card(db, await db.draft(token)))
    await db.set_draft(token, message_id=sent.message_id)
    return None


async def open_table(db: GCDatabase, d: dict) -> str | None:
    """«باز کردن میز»: میز واقعی با تنظیم انتخاب شده؛ همان پیام کارت میز می شود."""
    name = GAMES[d["game"]]["name"]
    if d["chat_id"] and await db.open_group_table(d["chat_id"], d["game"]):
        return f"یک میز {name} همین الان در این گروه باز است."
    if not await db.claim_draft(d["token"], "open"):
        return "این کارت دیگر فعال نیست."
    try:
        r = await service.invite_create(db, d["host"], cfg_of(d["game"], d["cfg"]))
    except GCError as e:
        await db.unclaim_draft(d["token"])
        return {"in_match": "تو الان سر یک میز دیگر هستی؛ اول آن را تمام کن."}.get(e.code, "میز ساخته نشد؛ دوباره امتحان کن.")
    mid = r["match"]
    await db.add_group_table(mid, d["chat_id"], d["chat_title"], d["game"], d["host"])
    if d["message_id"]:
        await db.set_group_message(mid, d["message_id"])
    if d["inline_message_id"]:
        await db.set_group_inline(mid, d["inline_message_id"])
    await db.set_draft(d["token"], match_id=mid)
    await refresh(db, mid)
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
    await _send(message.chat.id, _rm([_h("Game Club"), _p("چه بازی‌ای بازی کنیم؟ هر کس بزند میز را تنظیم می‌کند و خودش اول می‌نشیند."),
                                      _row(*[_b(f"{g['icon']} {g['name']}", "primary" if k == "hokm" else None, callback_data=f"gt:new:{k}")
                                             for k, g in GAMES.items()])]))


async def _draft_err(cq: CallbackQuery, text: str) -> None:
    await cq.answer(text, show_alert=True)


@router.callback_query(F.data.startswith("gs:"))
async def on_setup(cq: CallbackQuery, gdb: GCDatabase) -> None:
    """دکمه های کارت تنظیم: gs:<کلید=مقدار|open|cancel>:<توکن>"""
    act, _, token = (cq.data or "")[3:].partition(":")
    d = await gdb.draft(token)
    if not d or d["status"] != "setup":
        return await _draft_err(cq, "این کارت دیگر فعال نیست.")
    if cq.from_user.id != d["host"]:
        return await _draft_err(cq, "فقط سازندهٔ میز تنظیمش می‌کند؛ وقتی باز شد «بنشین» را بزن.")
    # کارت اینلاین یا فرستاده از مینی اپ: شناسهٔ پیام از همین لمس معلوم می شود
    if cq.inline_message_id and not d["inline_message_id"]:
        await gdb.set_draft(token, inline_message_id=cq.inline_message_id)
        d["inline_message_id"] = cq.inline_message_id
    if act == "cancel":
        if await gdb.claim_draft(token, "closed"):
            await _edit(_where(d), closed_card(d["game"], "سازنده میز را لغو کرد."))
        await cq.answer("لغو شد")
        return
    if act == "open":
        err = await open_table(gdb, d)
        await cq.answer(err or "میز باز شد و نشستی! حالا بقیه «بنشین» را بزنند.", show_alert=bool(err))
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
    """بنشین، بلند شو و شروع روی میزی که باز شده (گروهی یا اینلاین)."""
    u = cq.from_user
    row = await gdb.group_table(match_id)
    m = await gdb.get_match(match_id) if row else None
    if not row or not m:
        await cq.answer("این میز دیگر نیست.", show_alert=True)
        return
    await gdb.player(u.id, _name(u), u.username)
    try:
        if act == "join":
            if m["status"] == "lobby" and any(s["tg"] == u.id for s in m["state"].get("seats", [])):
                await cq.answer("سر همین میز نشسته‌ای.")
                return
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
                return await _draft_err(cq, "حساب تو در Game Club مسدود شده است.")
            token = await gdb.new_draft(u.id, arg, dict(GAMES[arg]["def"]))
            await gdb.set_draft(token, inline_message_id=cq.inline_message_id)
            await cq.answer("حالت بازی را انتخاب کن و میز را باز کن.")
            await _edit({"inline_message_id": cq.inline_message_id}, await setup_card(gdb, await gdb.draft(token)))
            return
        if not cq.message:
            await cq.answer()
            return
        err = await create(gdb, bot, cq.message.chat, u, arg)
        await cq.answer(err or "حالت بازی را انتخاب کن و میز را باز کن.", show_alert=bool(err))
        return
    await expire(gdb)
    await _act(cq, gdb, act, arg)


@router.callback_query(F.data.startswith("gi:"))
async def on_old_inline(cq: CallbackQuery) -> None:
    """کارت های اینلاین نسخهٔ قبل."""
    await cq.answer("این کارت قدیمی است؛ یک میز تازه بساز.", show_alert=True)


# ---------- حالت اینلاین (@ربات hokm در هر چتی) و «فرستادن به گروه» از مینی اپ ----------
INLINE_ALIASES = {"hokm": ("hokm", "حکم", "hk"), "ludo": ("ludo", "منچ", "mench"), "football": ("football", "فوتبال", "fb", "soccer")}


async def _article(db: GCDatabase, host: int, game: str) -> InlineQueryResultArticle:
    """کارت تنظیم میز به شکل نتیجهٔ اینلاین؛ سازنده همان کسی است که فرستاده."""
    g = GAMES[game]
    token = await db.new_draft(host, game, dict(g["def"]))
    return InlineQueryResultArticle(
        id=token, title=f"{g['icon']} میز {g['name']} بساز",
        description=f"{summary(game, cfg_of(game, g['def']))} · حالت را خودت انتخاب می‌کنی",
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
