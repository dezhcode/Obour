"""بازی در گروه های تلگرام: ربات یک «کارت میز» در گروه می فرستد؛ دکمه ها داخل خود پیام اند
(پیام غنی Bot API 10.3 با بلوک دکمه)، نه کیبورد شیشه ای زیر پیام.

- /hokm، /ludo، /football، /billiard، /divar، /esmfamil، /lashgar (یا /play برای انتخاب بازی) کارت «تنظیم میز» می فرستد: سازنده حالت بازی
  (طول بازی، تعداد بازیکن، مدل) را انتخاب می کند و «باز کردن میز» را می زند؛ سازنده خودش می نشیند.
- با هر نشستن یا بلند شدن، کارت عوض می شود: چه کسانی نشسته اند (با منشن) و چند جای خالی مانده.
- وقتی میز پر شد یا سازنده «شروع» را زد، دکمه های میز می روند و کارت «بازی شروع شد» می شود با اسم
  بازی، بازیکن ها و دکمهٔ «دیدن بازی» تا اعضای گروه بازی را زنده ببینند. به هر بازیکن در پیوی ربات
  و در خود گروه (پیام فقط-برای-او) خبر می رود.
- آخر بازی کارت نتیجه را نشان می دهد با دکمهٔ «میز تازه». میزی که ۱۵ دقیقه شروع نشود بسته می شود.
- همین کارت با @ربات hokm در هر چتی (حالت اینلاین) یا از مینی اپ («فرستادن به گروه») هم فرستاده می شود.
میزهای گروه همیشه آزاد اند (بدون امتیاز) تا با یک لمس اتفاقی از کسی امتیاز کم نشود.
اسم‌فامیل فقط همین جا ساخته می شود (۲ تا ۱۰ نفر، بدون ربات)؛ آخر بازی برگ همه با امتیازها در گروه می آید.
لشگر کاغذی (جنگ کاغذی) هم فقط گروهی است (دو نفره، بدون ربات)؛ آخر جنگ عکس برگهٔ آخر در گروه می آید.
"""
from __future__ import annotations

import logging
import time

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    EphemeralMessageParameters,
    InlineQueryResultArticle,
    InlineQueryResultsButton,
    InputRichBlockButtons,
    InputRichBlockDetails,
    InputRichBlockParagraph,
    InputRichBlockTable,
    InputRichMessage,
    InputRichMessageContent,
    Message,
    RichBlockTableCell,
    RichMessageButton,
    RichTextStrikethrough,
)

from . import esmfamil, lashgar, service
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
    # دیوار: یک انتخاب برای تعداد و نوع (۲ نفره، ۴ نفرهٔ کلاسیک، ۴ نفرهٔ ستاره)؛ cfg_of به players و variant تبدیلش می کند
    "divar": {"name": "دیوار", "icon": "🧱", "base": {"game": "divar", "mode": "free", "entry": 0},
              "opts": [("kind", "حالت بازی", [(2, "2 نفره · 9×9"), (4, "4 نفره · کلاسیک"), (5, "4 نفره · ستارهٔ وسط")])],
              "def": {"kind": 2}},
    # اسم‌فامیل: فقط گروهی، ۲ تا ۱۰ نفر، بدون ربات؛ حرف و داوری با هوش مصنوعی عبور
    "esmfamil": {"name": "اسم‌فامیل", "icon": "📝", "base": {"game": "esmfamil", "mode": "free", "entry": 0},
                 "opts": [("rounds", "تعداد دور", [(1, "1 دور · برق‌آسا"), (3, "3 دور"), (5, "5 دور · کامل")]),
                          ("secs", "وقت هر دور", [(180, "3 دقیقه · تند"), (300, "5 دقیقه"), (480, "8 دقیقه · با حوصله")])],
                 "def": {"rounds": 3, "secs": 300}},
    # لشگر کاغذی (جنگ کاغذی): فقط گروهی، دو نفره، بدون ربات؛ نقاشی وقت ندارد و هر شلیک 1 دقیقه
    "lashgar": {"name": "لشگر کاغذی", "icon": "🪖", "base": {"game": "lashgar", "mode": "free", "entry": 0},
                "opts": [("army", "ارتش هر نفر", [(11, "کوچک · 11 نیرو"), (18, "بزرگ · 18 نیرو")])],
                "def": {"army": 11}},
}
GROUP_ONLY = service.GROUP_ONLY
OPEN_TTL = 15 * 60       # میز یا کارت تنظیمی که این مدت شروع نشود بسته می شود
fd = str   # عددهای پیام های ربات لاتین اند


def cfg_of(game: str, picks: dict) -> dict:
    """تنظیم بازی از انتخاب های سازنده؛ فقط مقدارهای مجاز، بقیه پیش فرض."""
    g = GAMES[game]
    out = dict(g["base"])
    for key, _, opts in g["opts"]:
        v = picks.get(key)
        out[key] = v if v in [o[0] for o in opts] else g["def"][key]
    if game == "divar":
        out["players"] = 2 if out["kind"] == 2 else 4
        out["variant"] = "star" if out["kind"] == 5 else "classic"
    if game == "esmfamil":
        out["players"] = esmfamil.MAX_PLAYERS
    if game == "lashgar":
        out["players"] = 2
    return out


def need_of(game: str, cfg: dict) -> int:
    if game == "esmfamil":
        return esmfamil.MAX_PLAYERS
    if game == "lashgar":
        return 2
    return int(cfg.get("players") or 0) if game in ("ludo", "billiard", "divar") else 4 if game == "hokm" else 2


def summary(game: str, cfg: dict) -> str:
    n = fd(need_of(game, cfg))
    if game == "hokm":
        return f"آزاد · {n} نفره · تا {fd(cfg.get('target', 7))} دست"
    if game == "ludo":
        return f"آزاد · {n} نفره · {'کلاسیک' if cfg.get('pawns') == 4 else 'سریع'} ({fd(cfg.get('pawns', 2))} مهره)"
    if game == "divar":
        kind = "ستارهٔ وسط · 11×11" if cfg.get("variant") == "star" else "9×9"
        return f"آزاد · {n} نفره · {kind} · هر نفر {fd(10 if n == '2' else 7 if cfg.get('variant') == 'star' else 5)} دیوار"
    if game == "billiard":
        return f"آزاد · {n} نفره · {'یاری (دو تیم دونفره)' if cfg.get('players') == 4 else 'رو در رو'} · ۸ توپ"
    if game == "lashgar":
        army = cfg.get("army", 11)
        return f"تن‌به‌تن · ارتش {'بزرگ' if army == 18 else 'کوچک'} ({fd(army)} نیرو) · هر شلیک 1 دقیقه"
    if game == "esmfamil":
        return f"{fd(cfg.get('rounds', 3))} دور · هر دور {fd(round(cfg.get('secs', 300) / 60))} دقیقه · {fd(esmfamil.MIN_PLAYERS)} تا {n} نفر"
    return f"آزاد · {n} نفره · تا {fd(cfg.get('target', 3))} گل"


def app_link(game: str, code: str) -> str:
    """لینک مستقیم مینی اپ اصلی ربات (Main Mini App) که مستقیم سر همین میز باز می شود."""
    return f"https://t.me/{gc.username}?startapp={game}_{code}" if gc.username and code else ""


def watch_link(game: str, match_id: str) -> str:
    """«دیدن بازی»: صفحهٔ بازی در حالت تماشا (بازیکن خودِ میز با همین لینک بازی خودش را باز می کند)."""
    return f"https://t.me/{gc.username}?startapp=w_{game}_{match_id}" if gc.username else ""


# ---------- اجزای پیام غنی (قالب متنی عبور در یک پاراگراف + ردیف دکمه های داخل پیام) ----------
OPT_ICON = {"target": "time", "players": "users", "pawns": "ludo", "passes": "users", "kind": "divar", "rounds": "esmfamil",
            "secs": "time", "army": "lashgar"}


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
    if m["status"] == "lobby" and game == "lashgar":
        return _lg_lobby(game, cfg, mid, seats, row)
    if m["status"] == "lobby" and game in GROUP_ONLY:
        return _esm_lobby(game, cfg, mid, seats, row)
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
        if game == "esmfamil":
            players += ["", [st.E("judge"), " حرف هر دور و تصحیح برگ‌ها با هوش مصنوعی عبوره."]]
        if game == "lashgar":
            players += ["", "اول اسم لشگر، بعد نقاشی؛ عجله‌ای نیست! هر وقت هر دو آماده شدن، جنگ شروع می‌شه و هر شلیک 1 دقیقه وقت داره."]
        return card(st.frame(game, f"بازی {g['name']}", f"شروع شد · {summary(game, cfg)}", players,
                             foot=("watch", "تماشا", "بقیه هم زنده می‌بینن؛ فقط لو ندید کجا رو بزنن 😄" if game == "lashgar"
                                   else "بقیه هم زنده می‌بینن؛ فقط تقلب نرسونید 😄")),
                    *([_row(_bt("watch", "دیدن جنگ" if game == "lashgar" else "دیدن بازی", "primary", url=link))] if link else []))
    if m["status"] == "cancelled":
        return closed_card(game)
    state = m["state"]
    if game == "esmfamil":
        # کارت گروه خلاصه است و برگ کامل جدا می آید؛ کارت اینلاین (بدون چت) خودش برگ کامل می شود
        return esm_result(m, seats, full=not row.get("chat_id"))
    if game == "lashgar":
        return lg_result(m, seats)
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


# ---------- اسم‌فامیل: کارت میز و برگ نهایی ----------
def _esm_lobby(game: str, cfg: dict, mid: str, seats: list[dict], row: dict) -> InputRichMessage:
    host = next((s for s in seats if s.get("tg") == row["host"]), None)
    free = esmfamil.MAX_PLAYERS - len(seats)
    lines = [["سازنده: ", *(who(host["tg"], host["name"]) if host else ["—"])], "",
             [st.E("judge"), " حرف هر دور رو هوش مصنوعی عبور انتخاب می‌کنه و برگ‌ها رو هم خودش تصحیح می‌کنه."],
             "جواب درستی که فقط خودت نوشتی 10، تکراری 5، غلط یا خالی 0.", "",
             [st.E("users"), " ", st.B(f"سر میز ({fd(len(seats))} نفر)")]]
    lines += [[f"{fd(i + 1)}. ", *who(s["tg"], s["name"])] for i, s in enumerate(seats)]
    if len(seats) < esmfamil.MIN_PLAYERS:
        foot = ("seat", "منتظر حریف", "حداقل یه نفر دیگه باید «بشین» رو بزنه؛ تنهایی که مزه نداره 😉")
    else:
        foot = ("play", "آماده", f"تا {fd(free)} نفر دیگه هم جا هست؛ هر وقت سازنده خواست «بزن بریم» رو می‌زنه 🚀")
    rows = [_row(_bt("seat", "بشین", "success", callback_data=f"gt:join:{mid}"),
                 _bt("leave", "بلند شو", "danger", callback_data=f"gt:leave:{mid}"))]
    if len(seats) >= esmfamil.MIN_PLAYERS:
        rows.append(_row(_bt("play", "بزن بریم!", "primary", callback_data=f"gt:start:{mid}")))
    return card(st.frame(game, "میز اسم‌فامیل", summary(game, cfg), lines, foot), *rows)


def _esm_rank(state: dict) -> list[str]:
    tot = state.get("totals") or {}
    return sorted(state.get("order") or [], key=lambda c: (-tot.get(c, 0), (state.get("order") or []).index(c)))


def _esm_who(c: str, by: dict, state: dict) -> list:
    s = by.get(c)
    name = (s or {}).get("name") or state["players"][c]["name"]
    return who(s["tg"], name) if s and s.get("tg") else [st.iso(name)]


def esm_head(m: dict, seats: list[dict], more: bool = False) -> list:
    """قاب بالای برگ نهایی: برنده و رده‌بندی."""
    state = m["state"]
    by = {s.get("color"): s for s in seats}
    tot = state.get("totals") or {}
    wins = state.get("winners") or []
    if wins:
        res: list = [st.E("trophy"), " ", st.B("برنده: ")]
        for i, c in enumerate(wins):
            res += ([" و "] if i else []) + _esm_who(c, by, state)
        res += [f" با {fd(tot.get(wins[0], 0))} امتیاز"]
    else:
        res = ["کسی امتیاز نگرفت؛ برگ‌ها سفید موند 🕊"]
    lines: list = [res, "", [st.E("score"), " ", st.B("رده‌بندی")]]
    for i, c in enumerate(_esm_rank(state)):
        out = " (وسط بازی رفت)" if state["players"][c].get("out") else ""
        lines.append([f"{fd(i + 1)}. ", *_esm_who(c, by, state), f" — {fd(tot.get(c, 0))}{out}",
                      *([" ", st.E("trophy")] if c in wins else [])])
    by_ai = any(r.get("by") == "ai" for r in state.get("rounds") or [])
    if more:
        lines += ["", "برگ همه با امتیاز هر خونه رو پایین‌تر گذاشتیم؛ ببینید کی چی نوشته 👇"]
    rounds = len(state.get("rounds") or [])
    return st.frame("esmfamil", "اسم‌فامیل", f"تموم شد · {fd(rounds)} دور", lines,
                    foot=("judge", "داور", "هوش مصنوعی عبور" if by_ai else "داوری خودکار"))


def _cell(cell: dict, col: str):  # noqa: ANN202
    a = cell.get("a") or ""
    if not a:
        return "—"
    if not cell.get("ok"):
        return [RichTextStrikethrough(text=a), " 0"]
    return f"{a} {fd(cell.get('s', 0))}"


def esm_round_blocks(state: dict, i: int, by: dict) -> list:
    """جدول یک دور: ستون‌ها بازیکن‌ها، ردیف‌ها دسته‌ها، و دو ردیف آخر امتیاز این دور و جمع تا این دور."""
    rec = state["rounds"][i]
    cols = [c for c in state["order"] if c in rec["cells"]]
    names = [(by.get(c) or {}).get("name") or state["players"][c]["name"] for c in cols]

    def C(text, head: bool = False, align: str = "center") -> RichBlockTableCell:  # noqa: ANN001
        return RichBlockTableCell(align=align, valign="middle", text=text, is_header=head or None)

    cells = [[C("", True), *[C(st.en(n), True) for n in names]]]
    for k in state["cols"]:
        cells.append([C(esmfamil.COL_FA[k], True, "right"), *[C(_cell(rec["cells"][c][k], k)) for c in cols]])
    upto = {c: sum(r["scores"].get(c, 0) for r in state["rounds"][:i + 1]) for c in cols}
    cells.append([C("این دور", True, "right"), *[C(fd(rec["scores"].get(c, 0))) for c in cols]])
    cells.append([C("جمع", True, "right"), *[C(fd(upto[c])) for c in cols]])
    blocks: list = [InputRichBlockTable(cells=cells, is_bordered=True, is_striped=True, is_compact=True)]
    why = []
    for c in cols:
        for k in state["cols"]:
            cell = rec["cells"][c][k]
            if cell.get("a") and not cell.get("ok") and cell.get("why"):
                why.append(["• ", st.iso((by.get(c) or {}).get("name") or state["players"][c]["name"]), f" · {esmfamil.COL_FA[k]}: «",
                            cell["a"], "» ", cell["why"]])
            elif cell.get("appealed"):
                why.append(["• ", st.iso((by.get(c) or {}).get("name") or state["players"][c]["name"]), f" · {esmfamil.COL_FA[k]}: «",
                            cell["a"], "» با رأی بچه‌ها قبول شد 🙌"])
    if why:
        blocks.append(_para([st.E("judge"), " ", st.B("نظر داور"), "\n", *sum(([*w, "\n"] for w in why[:24]), [])[:-1]]))
    return blocks


def esm_result(m: dict, seats: list[dict], full: bool = True) -> InputRichMessage:
    state = m["state"]
    by = {s.get("color"): s for s in seats}
    blocks: list = [_para(esm_head(m, seats, more=not full))]
    if full:
        n = len(state.get("rounds") or [])
        for i in range(n):
            rec = state["rounds"][i]
            blocks.append(InputRichBlockDetails(
                summary=st.to_rich([st.B(f"دور {fd(i + 1)}"), f" · حرف «{rec['letter']}»"]),
                blocks=esm_round_blocks(state, i, by), is_open=i == n - 1))
    blocks.append(_row(_bt("new", "یه دست دیگه بزنیم؟", "success", callback_data="gt:new:esmfamil")))
    return _rm(blocks)


def esm_html(m: dict, seats: list[dict]) -> list[str]:
    """جایگزین متنی برگ نهایی (اگر پیام غنی نرفت): هر دور یک نقل‌قول بازشدنی؛ چند پیام اگر بلند شد."""
    state = m["state"]
    by = {s.get("color"): s for s in seats}
    head = st.to_html(esm_head(m, seats))
    parts = []
    for i, rec in enumerate(state.get("rounds") or []):
        rows = []
        for c in [c for c in state["order"] if c in rec["cells"]]:
            name = (by.get(c) or {}).get("name") or state["players"][c]["name"]
            cells = []
            for k in state["cols"]:
                cell = rec["cells"][c][k]
                a = _esc(cell.get("a") or "—")
                cells.append(f"{esmfamil.COL_FA[k]}: " + (f"<s>{a}</s> 0" if cell.get("a") and not cell.get("ok")
                                                         else f"{a} {cell.get('s', 0)}" if cell.get("a") else a))
            rows.append(f"<b>{_esc(name)}</b> ({rec['scores'].get(c, 0)})\n" + " · ".join(cells))
        parts.append(f"<b>دور {i + 1} · حرف «{rec['letter']}»</b>\n<blockquote expandable>" + "\n\n".join(rows) + "</blockquote>")
    out, cur = [], head
    for p in parts:
        if len(cur) + len(p) + 2 > 3900:
            out.append(cur)
            cur = p
        else:
            cur += "\n\n" + p
    out.append(cur)
    return out


async def _esm_results(db: GCDatabase, m: dict, row: dict) -> None:
    """پایان اسم‌فامیل: برگ همه با امتیاز هر خانه و برنده، به صورت پیام تازه در خود گروه."""
    if not row.get("chat_id") or not m["state"].get("rounds"):
        return
    seats = await _seats(db, m)
    try:
        await _send(row["chat_id"], esm_result(m, seats))
        return
    except Exception:  # noqa: BLE001
        log.info("برگ نهایی اسم‌فامیل به شکل پیام غنی نرفت؛ متن ساده", exc_info=True)
    try:
        for text in esm_html(m, seats):
            await _bot.send_message(row["chat_id"], text)
    except Exception:  # noqa: BLE001
        log.warning("برگ نهایی اسم‌فامیل نرفت", exc_info=True)


# ---------- لشگر کاغذی: کارت میز و نتیجهٔ جنگ ----------
def _lg_lobby(game: str, cfg: dict, mid: str, seats: list[dict], row: dict) -> InputRichMessage:
    host = next((s for s in seats if s.get("tg") == row["host"]), None)
    lines = [["سازنده: ", *(who(host["tg"], host["name"]) if host else ["—"])], "",
             [st.E("lashgar"), " همون جنگ کاغذی زنگ تفریح: اسم لشگر، چیدن نیروها و نقاشی با مداد؛ نقاشی وقت نداره."],
             [st.E("boom"), " هر شلیک 1 دقیقه: یه نقطه، تا کردن برگه و فشار از پشت؛ هر نیرویی که رد بهش بخوره خط می‌خوره."], "",
             [st.E("users"), " ", st.B(f"سر میز ({fd(len(seats))} از 2)")]]
    lines += [[f"{fd(i + 1)}. ", *who(s["tg"], s["name"])] for i, s in enumerate(seats)]
    lines += [[f"{fd(i + 1)}. ", st.E("seat"), " خالی؛ منتظر یه فرمانده"] for i in range(len(seats), 2)]
    foot = ("seat", "منتظر حریف", "یه نفر دیگه «بشین» رو بزنه، جنگ شروع می‌شه 🪖") if len(seats) < 2 else \
        ("party", "میز پر شد", "الان جنگ شروع می‌شه!")
    return card(st.frame(game, "میز لشگر کاغذی", summary(game, cfg), lines, foot),
                _row(_bt("seat", "بشین", "success", callback_data=f"gt:join:{mid}"),
                     _bt("leave", "بلند شو", "danger", callback_data=f"gt:leave:{mid}")))


def lg_stats(state: dict) -> dict:
    """هر فرمانده: شلیک، شلیکی که به چیزی خورد، دقت (درصد) و نیروی سالم از کل."""
    out = {}
    for c in state.get("order") or []:
        mine = [x for x in state.get("shots") or [] if x.get("by") == c]
        good = sum(1 for x in mine if x.get("hit"))
        p = state["players"][c]
        out[c] = {"shots": len(mine), "good": good, "acc": round(good * 100 / len(mine)) if mine else 0,
                  "alive": lashgar.alive(p), "total": len(p.get("units") or [])}
    return out


def _lg_army(state: dict, c: str) -> str:
    return state["players"][c].get("army") or "بی‌نام"


def lg_result(m: dict, seats: list[dict]) -> InputRichMessage:
    """کارت آخر جنگ: برنده (اسم لشگر و منشن)، چرا تمام شد، جدول شلیک ها و دکمهٔ جنگ تازه."""
    state = m["state"]
    by = {s.get("color"): s for s in seats}

    def man(c: str) -> list:
        s = by.get(c)
        name = (s or {}).get("name") or state["players"][c]["name"]
        return who(s["tg"], name) if s and s.get("tg") else [st.iso(name)]
    w, why = state.get("winner"), state.get("why")
    lines: list = []
    if w:
        foe = next(c for c in state["order"] if c != w)
        lines.append([st.E("trophy"), " ", st.B("برنده: "), "لشگر «", st.iso(_lg_army(state, w)), "» (", *man(w), ")"])
        lines.append({"flag": ["شلیک آخر خورد به پرچم «", st.iso(_lg_army(state, foe)), "»؛ جنگ همون‌جا تموم شد! 🚩"],
                      "army": ["همهٔ نیروهای «", st.iso(_lg_army(state, foe)), "» خط خوردن! 💥"],
                      "left": [*man(foe), " وسط جنگ رفت."],
                      "timeout": [*man(foe), " سه بار پشت هم نوبتشو سوزوند."]}.get(why, ""))
    else:
        lines.append("جنگ بی‌برنده تموم شد؛ صلح برقرار شد 🕊")
    S = lg_stats(state)

    def C(text, head: bool = False, align: str = "center") -> RichBlockTableCell:  # noqa: ANN001
        return RichBlockTableCell(align=align, valign="middle", text=text, is_header=head or None)
    order = sorted(state["order"], key=lambda c: c != w)
    cells = [[C("لشگر", True, "right"), C("شلیک", True), C("خورد", True), C("دقت", True), C("سالم", True)]]
    for c in order:
        x = S[c]
        cells.append([C(_lg_army(state, c), True, "right"), C(fd(x["shots"])), C(fd(x["good"])),
                      C(f"{fd(x['acc'])}%"), C(f"{fd(x['alive'])} از {fd(x['total'])}")])
    start = state.get("battle_at") or state.get("started") or m.get("created_at") or time.time()
    mins = max(1, round(((m.get("updated_at") or time.time()) - start) / 60))
    head = st.frame("lashgar", "لشگر کاغذی", f"تموم شد · {fd(len(state.get('shots') or []))} شلیک", lines,
                    foot=("time", "مدت جنگ", f"{fd(mins)} دقیقه"))
    return _rm([_para(head), InputRichBlockTable(cells=cells, is_bordered=True, is_striped=True, is_compact=True),
                _row(_bt("new", "یه جنگ دیگه بزنیم؟", "success", callback_data="gt:new:lashgar"))])


async def _lg_results(db: GCDatabase, m: dict, row: dict) -> None:
    """پایان جنگ در گروه: عکس برگهٔ آخر (نقاشی، نیروها و رد همهٔ شلیک ها) به شکل پیام تازه."""
    if not row.get("chat_id") or not m["state"].get("shots"):
        return
    try:
        from . import lashgar_art
        png = lashgar_art.render(m["state"], await db.ink_strokes(m["id"]))
        state, w = m["state"], m["state"].get("winner")
        cap = f"برگهٔ آخر جنگ؛ لشگر «{_esc(_lg_army(state, w))}» برد! 🏆" if w else "برگهٔ آخر جنگ کاغذی"
        await _bot.send_photo(row["chat_id"], BufferedInputFile(png, "lashgar.png"), caption=cap)
    except Exception:  # noqa: BLE001
        log.warning("عکس برگهٔ آخر لشگر کاغذی نرفت", exc_info=True)


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
    if status != row["status"] and await db.set_group_status(match_id, row["status"], status):
        if status == "playing":
            await _announce_start(db, m, row)
        elif status == "over" and row["game"] == "esmfamil":
            await _esm_results(db, m, row)
        elif status == "over" and row["game"] == "lashgar":
            await _lg_results(db, m, row)


async def _announce_start(db: GCDatabase, m: dict, row: dict) -> None:
    g = GAMES[row["game"]]
    link = app_link(row["game"], m.get("invite") or "")
    title = row.get("chat_title") or "گروه"
    for s in await _seats(db, m):
        if s.get("bot"):
            continue
        tg = s["tg"]
        # اسم‌فامیل میز «پر» ندارد: سازنده شروع می کند و هر کس باید زود برگش را باز کند
        esm, lg = row["game"] == "esmfamil", row["game"] == "lashgar"
        go = "برگمو باز کن" if esm else "برو سر برگه" if lg else "ورود به بازی"
        # ۱) پیوی ربات (اگر کاربر قبلا ربات را استارت کرده باشد)
        try:
            from .bot import open_kb
            line = (["اسم‌فامیل توی «", st.iso(title), "» شروع شد! برگتو باز کن؛ حرف که رو بشه، ساعت راه می‌افته ✍️"] if esm else
                    ["جنگ کاغذی توی «", st.iso(title), "» شروع شد! اسم لشگرت رو بذار و ارتشت رو بکش؛ عجله‌ای نیست 🪖"] if lg else
                    ["بازی توی «", st.iso(title), "» شروع شد؛ همه منتظر توان، دیر نکن! 🏃"])
            text = st.to_html(st.frame(row["game"], f"بازی {g['name']}", "شروع شد", [line], foot=("play", "ورود", "دکمهٔ زیر رو بزن")))
            await _bot.send_message(tg, text, reply_markup=open_kb(f"{row['game']}.html", go, "play"))
        except Exception:  # noqa: BLE001
            pass
        # ۲) پیام فقط-برای-او داخل همان گروه (Ephemeral Messages)؛ کارت اینلاین چت را نمی شناسد
        if not row["chat_id"]:
            continue
        try:
            rm = card(st.frame(row["game"], f"بازی {g['name']}", "شروع شد",
                               [[*who(tg, s["name"]), "، اسم‌فامیل شروع شد! بدو برگتو باز کن ✍️" if esm else
                                 "، جنگ کاغذی شروع شد! برو اسم لشگرت رو بذار 🪖" if lg else "، میز پر شد و بازی شروع شد! بدو بیا 🏃"]],
                               foot=("play", "ورود", "این پیام رو فقط تو می‌بینی؛ هیس 🤫")),
                      *([_row(_bt("play", go, "primary", url=link))] if link else []))
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


@router.message(GROUP, Command("hokm", "ludo", "football", "billiard", "divar", "esmfamil", "lashgar"))
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
                 foot=("group", "بازی‌ها", "حکم، منچ، فوتبال، بیلیارد، دیوار، اسم‌فامیل و لشگر کاغذی؛ همه مجانی، فقط سر کل‌کل 😄")),
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
                "busy": "یه لحظه صبر کن، دوباره بزن.", "not_found": "این میز دیگه نیست 👻",
                "need_players": "حداقل 2 نفر باید بشینن؛ تنهایی که مزه نداره 😄"}.get(e.code, "نشد؛ یه بار دیگه بزن.")
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
                  "billiard": ("billiard", "بیلیارد", "pool", "8ball", "snooker"),
                  "divar": ("divar", "دیوار", "quoridor", "wall", "kooridor"),
                  "esmfamil": ("esmfamil", "اسم‌فامیل", "اسم فامیل", "اسم", "esm", "namefamily"),
                  "lashgar": ("lashgar", "لشگر", "لشکر", "جنگ", "جنگ کاغذی", "jang", "paperwar", "war")}


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
    in_group = getattr(iq, "chat_type", None) in ("group", "supergroup")
    allowed = [k for k in GAMES if in_group or k not in GROUP_ONLY]   # اسم‌فامیل و لشگر کاغذی فقط در گروه
    games = [k for k in allowed if not q or any(a.startswith(q) or q.startswith(a) for a in INLINE_ALIASES[k])]
    hint = None
    only = next((k for k in GAMES if k in GROUP_ONLY and q and any(a.startswith(q) or q.startswith(a) for a in INLINE_ALIASES[k])), None)
    if not in_group and only:
        hint = InlineQueryResultsButton(text=f"{GAMES[only]['name']} فقط توی گروه بازی می‌شه؛ راهنما", start_parameter=only)
    await iq.answer([await _article(gdb, u.id, g) for g in games or allowed], cache_time=0, is_personal=True, button=hint)


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
                                                       allow_user_chats=game not in GROUP_ONLY, allow_group_chats=True,
                                                       allow_bot_chats=False, allow_channel_chats=False)
    return prepared.id
