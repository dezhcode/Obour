"""میزها، صف ناشناس، دعوت، امتیاز و تسویه.

قاعده پول در بازی امتیازی:
- ورودی هنگام ورود به صف یا نشستن سر میز دعوت کم می شود (ledger: entry)
- اگر بازی شروع نشد (انصراف، لغو میز) همان ورودی برمی گردد (refund)
- پایان بازی: کل ورودی ها منهای سهم عبور (GAME_CLUB_RAKE) به برنده (prize)
- بازی امتیازی هیچ وقت با ربات پر نمی شود؛ ربات فقط در بازی آزاد می نشیند
همه این ها idem دارند تا درخواست تکراری دو بار پول جابه جا نکند.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import secrets
import time

from . import football, hokm, ludo
from .config import gc
from .db import GCDatabase, pic_url

log = logging.getLogger("gameclub.service")

BOT_NAMES = ("سارا", "امیر", "نگار", "رضا", "مهسا", "علی", "پریا", "کیان", "هستی", "سینا", "آرش", "یاسمن")
_ALPH = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


# هر بازی: موتور قواعد، نام فارسی و صفحه میز
GAMES = {"ludo": (ludo, "منچ", "ludo.html"), "hokm": (hokm, "حکم", "hokm.html"),
         "football": (football, "فوتبال", "football.html")}


def game_of(cfg: dict) -> str:
    g = cfg.get("game")
    return g if g in GAMES else "ludo"


def _eng(cfg: dict):
    return GAMES[game_of(cfg)][0]


def _gname(cfg: dict) -> str:
    return GAMES[game_of(cfg)][1]


def _gpage(cfg: dict) -> str:
    return GAMES[game_of(cfg)][2]


def _seat_order(cfg: dict) -> tuple:
    """ترتیب صندلی ها؛ در حکم اولین مهمان میز دعوت یار سازنده می شود."""
    g = game_of(cfg)
    if g == "hokm":
        return hokm.LOBBY_ORDER
    if g == "football":
        return football.SEATS
    return ludo.SEATS[cfg["players"]]


def _current(st: dict) -> str | None:
    if st.get("game") == "football":
        return football.current(st)
    if st.get("game") == "hokm":
        return hokm.SEATS[st["hakem"] if st["phase"] == "trump" else st["turn"]] if st["phase"] in ("trump", "play") else None
    return ludo.current(st)


def _winners(st: dict) -> set:
    if st.get("game") == "hokm":
        return hokm.winners(st)
    if st.get("game") == "football":
        return football.winners(st)
    return {st["winner"]} if st.get("winner") else set()


# تابع ارسال پیام ربات (tg, text, page)؛ bot.py هنگام راه اندازی می گذارد
notifier = None
AWAY = 12.0  # کسی که این مدت صفحه میز را نپرسیده، بیرون از مینی اپ حساب می شود


async def _notify(db: GCDatabase, tg: int | None, key: str, text: str, page: str = "ludo.html") -> None:
    """هر اعلان یک بار؛ خطای ارسال (مثلا ربات استارت نشده) بازی را نمی شکند."""
    if notifier is None or not tg or not await db.ping_once(key):
        return
    try:
        await notifier(tg, text, page)
    except Exception:  # noqa: BLE001
        log.debug("اعلان Game Club نرفت", exc_info=True)


async def _away(db: GCDatabase, match_id: str, tg: int, now: float) -> bool:
    return now - await db.seen(match_id, tg) > AWAY


class GCError(Exception):
    def __init__(self, code: str, **extra) -> None:
        super().__init__(code)
        self.code = code
        self.extra = extra


def _code(n: int) -> str:
    return "".join(secrets.choice(_ALPH) for _ in range(n))


# ---------- تنظیم میز ----------
def norm_cfg(raw: dict) -> dict:
    mode = "stake" if raw.get("mode") == "stake" else "free"
    if mode == "stake" and not gc.stake_enabled:
        raise GCError("stake_off")
    if raw.get("game") == "hokm":
        try:
            target = int(raw.get("target") or 7)
            entry = int(raw.get("entry") or 0)
        except (TypeError, ValueError):
            raise GCError("bad_cfg") from None
        if target not in (3, 7):
            raise GCError("bad_cfg")
        if mode == "stake":
            if entry not in gc.entries:
                raise GCError("bad_entry")
        else:
            entry = 0
        return {"game": "hokm", "mode": mode, "entry": entry, "players": 4, "target": target}
    if raw.get("game") == "football":
        try:
            target = int(raw.get("target") or 3)
            entry = int(raw.get("entry") or 0)
        except (TypeError, ValueError):
            raise GCError("bad_cfg") from None
        if target not in (3, 5):
            raise GCError("bad_cfg")
        if mode == "stake":
            if entry not in gc.entries:
                raise GCError("bad_entry")
        else:
            entry = 0
        return {"game": "football", "mode": mode, "entry": entry, "players": 2, "target": target}
    try:
        players = int(raw.get("players") or 2)
        pawns = int(raw.get("pawns") or 2)
        entry = int(raw.get("entry") or 0)
    except (TypeError, ValueError):
        raise GCError("bad_cfg") from None
    if players not in (2, 4) or pawns not in (2, 4):
        raise GCError("bad_cfg")
    if mode == "stake":
        if entry not in gc.entries:
            raise GCError("bad_entry")
    else:
        entry = 0
    return {"game": "ludo", "mode": mode, "entry": entry, "players": players, "pawns": pawns}


def cfg_key(cfg: dict) -> str:
    if game_of(cfg) in ("hokm", "football"):
        return f"{game_of(cfg)}:{cfg['mode']}:{cfg['entry']}:{cfg['target']}"
    return f"{cfg['mode']}:{cfg['entry']}:{cfg['players']}:{cfg['pawns']}"


# ---------- امتیاز ----------
async def spend(db: GCDatabase, tg: int, amount: int, kind: str, note: str, ref: str, idem: str) -> bool:
    """کسر امتیاز با ردیف دفتر. همان idem دوباره = همان نتیجه قبلی."""
    lid = await db.add_ledger(tg, kind, -amount, note, ref, idem, status="pending")
    if lid is None:
        row = await db.ledger_by_idem(idem)
        return bool(row and row["status"] == "done")
    if await db.debit(tg, amount):
        await db.set_ledger_status(lid, "done")
        return True
    await db.set_ledger_status(lid, "failed")
    return False


async def earn(db: GCDatabase, tg: int, amount: int, kind: str, note: str, ref: str, idem: str) -> bool:
    if amount <= 0:
        return False
    lid = await db.add_ledger(tg, kind, amount, note, ref, idem, status="pending")
    if lid is None:
        return False  # قبلا داده شده
    await db.player(tg)
    if await db.credit(tg, amount):
        await db.set_ledger_status(lid, "done")
        return True
    await db.set_ledger_status(lid, "failed")
    return False


# ---------- ساخت و تغییر میز ----------
async def _seat_info(db: GCDatabase, tg: int) -> dict:
    p = await db.get_player(tg) or {}
    return {"name": (p.get("name") or "بازیکن")[:24], "av": int(p.get("av") or 1), "pic": pic_url(p)}


async def _start_game(db: GCDatabase, match_id: str, cfg: dict, humans: list[dict], *, create: bool) -> None:
    """humans: [{tg, paid, color?}] → میز در حال بازی."""
    colors = list(_seat_order(cfg))
    seats, used = [], set()
    for h in humans:
        c = h.get("color") if h.get("color") in colors and h.get("color") not in used else \
            next(x for x in colors if x not in used)
        used.add(c)
        info = await _seat_info(db, h["tg"])
        seats.append({"color": c, "uid": h["tg"], "name": info["name"], "av": info["av"], "pic": info["pic"],
                      "bot": False, "paid": h["paid"]})
    names = random.sample(BOT_NAMES, len(BOT_NAMES))
    for c in colors:
        if c not in used:
            if cfg["mode"] == "stake":
                raise GCError("need_players")
            seats.append({"color": c, "uid": None, "name": names.pop(), "av": random.randint(1, 23), "bot": True})
    if game_of(cfg) == "hokm":
        state = hokm.new_state(seats, time.time(), gc.turn_seconds, cfg["mode"] == "stake", cfg["target"])
    elif game_of(cfg) == "football":
        state = football.new_state(seats, time.time(), gc.turn_seconds, cfg["mode"] == "stake", cfg["target"])
    else:
        first = random.choice([s["color"] for s in seats if not s["bot"]])
        state = ludo.new_state(seats, cfg["pawns"], time.time(), gc.turn_seconds, cfg["mode"] == "stake", first)
    state["pot"] = sum(s.get("paid", 0) for s in seats)
    if create:
        await db.create_match(match_id, "playing", cfg, state, humans[0]["tg"])
        for s in seats:
            if not s["bot"]:
                await db.add_match_player(match_id, s["uid"], s["color"], s.get("paid", 0))
    else:
        m = await db.get_match(match_id)
        if not m or m["status"] != "lobby" or not await db.save_match(match_id, m["version"], "playing", state):
            raise GCError("busy")
    log.info("میز %s شروع شد: %s", match_id, cfg_key(cfg))


async def mutate(db: GCDatabase, match_id: str, fn):
    """خواندن، تغییر، نوشتن با شماره نسخه. اگر پروسه دیگری زودتر نوشت، از نو."""
    for _ in range(8):
        m = await db.get_match(match_id)
        if not m:
            raise GCError("not_found")
        changed, result = fn(m)
        if not changed:
            return m, result
        if await db.save_match(match_id, m["version"], m["status"], m["state"]):
            m["version"] += 1
            if m["status"] == "over":
                await settle(db, m)
            return m, result
        await asyncio.sleep(0.03)
    raise GCError("busy")


# ---------- فروشگاه ظاهر: میز و ورق حکم ----------
# (نوع، طرح، نام، قیمت به امتیاز)؛ طرح A رایگان و پیش فرض است
STYLE_ITEMS = {
    "table:a": ("table", "a", "میز کلاسیک", 0),
    "table:b": ("table", "b", "میز کافه شب", 500),
    "table:c": ("table", "c", "میز Game Club", 500),
    "cards:m": ("cards", "m", "ورق مدرن", 0),       # درشت خوان (طرح قبلی بازی)، رایگان
    "cards:a": ("cards", "a", "ورق کلاسیک", 0),
    "cards:b": ("cards", "b", "ورق کافه شب", 300),
    "cards:c": ("cards", "c", "ورق Game Club", 300),
}


def style_of(player: dict) -> dict:
    return {"table": player.get("table_skin") or "a", "cards": player.get("card_skin") or "a"}


async def style_view(db: GCDatabase, tg: int) -> dict:
    p = await db.get_player(tg) or {}
    owned, cur = await db.owned_of(tg), style_of(p)
    items = [{"id": k, "kind": kind, "look": look, "name": name, "price": price,
              "owned": price == 0 or k in owned, "on": cur[kind] == look}
             for k, (kind, look, name, price) in STYLE_ITEMS.items()]
    return {"items": items, **cur, "points": p.get("points", 0)}


async def style_buy(db: GCDatabase, tg: int, item: str, idem: str) -> dict:
    """خرید یک میز یا ورق با امتیاز؛ بعد از خرید همان هم انتخاب می شود. همان idem دوباره = بی اثر."""
    if item not in STYLE_ITEMS:
        raise GCError("not_found")
    kind, look, name, price = STYLE_ITEMS[item]
    if price and item not in await db.owned_of(tg):
        if not await spend(db, tg, price, "style", f"خرید {name}", item, idem):
            raise GCError("insufficient")
        await db.add_owned(tg, item)
    await db.set_skin(tg, kind, look)
    return await style_view(db, tg)


async def style_use(db: GCDatabase, tg: int, item: str) -> dict:
    if item not in STYLE_ITEMS:
        raise GCError("not_found")
    kind, look, _, price = STYLE_ITEMS[item]
    if price and item not in await db.owned_of(tg):
        raise GCError("not_owned")
    await db.set_skin(tg, kind, look)
    return await style_view(db, tg)


async def settle(db: GCDatabase, m: dict) -> None:
    """یک بار و فقط یک بار: جایزه، نتیجه ها، آزاد کردن بازیکن ها."""
    if not await db.mark_settled(m["id"]):
        return
    st, cfg = m["state"], m["cfg"]
    rows = await db.match_players(m["id"])
    winners = _winners(st)
    name = _gname(cfg)
    shares = prize_shares(st, rows)
    for r in rows:
        won = r["color"] in winners
        share = shares.get(r["tg_id"], 0)
        if cfg["mode"] == "stake":
            if not winners and r["paid"]:
                await earn(db, r["tg_id"], r["paid"], "refund", f"بازگشت ورودی {name}", m["id"], f"endrefund:{m['id']}:{r['tg_id']}")
            elif share:
                # منچ یک برنده دارد (idem قبلی همان می ماند)؛ در حکم هر عضو تیم برنده سهم خودش را می گیرد
                idem = f"prize:{m['id']}" if game_of(cfg) == "ludo" else f"prize:{m['id']}:{r['tg_id']}"
                await earn(db, r["tg_id"], share, "prize", f"جایزهٔ {name}", m["id"], idem)
        await db.add_result(m["id"], r["tg_id"], won, share if cfg["mode"] == "stake" else 0)
    await db.deactivate(m["id"])
    now = time.time()
    for r in rows:
        if not await _away(db, m["id"], r["tg_id"], now):
            continue
        won = r["color"] in winners
        share = shares.get(r["tg_id"], 0)
        if won:
            text = f"{name} را بردی! {share:,} امتیاز جایزه به کیفت اضافه شد." if cfg["mode"] == "stake" and share else f"{name} را بردی!"
        else:
            text = f"بازی {name} تمام شد و این بار باختی." if winners else f"بازی {name} تمام شد."
        await _notify(db, r["tg_id"], f"over:{m['id']}:{r['tg_id']}", text, "wallet.html" if won and share else "index.html")


def prize_shares(st: dict, rows: list[dict]) -> dict:
    """جایزه هر نفر (فقط بازی امتیازی). منچ: همه به برنده. حکم: بین اعضای تیم برنده
    که بازی را ترک نکرده اند تقسیم می شود."""
    if not st.get("stake"):
        return {}
    winners = _winners(st)
    pot = sum(r["paid"] for r in rows)
    prize = pot - pot * gc.rake_percent // 100
    got = [r for r in rows if r["color"] in winners
           and not (st.get("game") == "hokm" and st["players"].get(r["color"], {}).get("out"))]
    if not got or not prize:
        return {}
    return {r["tg_id"]: prize // len(got) for r in got}


def _color_of(rows: list[dict], tg: int) -> str | None:
    return next((r["color"] for r in rows if r["tg_id"] == tg), None)


# ---------- صف ناشناس ----------
async def queue_join(db: GCDatabase, tg: int, raw_cfg: dict) -> dict:
    cfg = norm_cfg(raw_cfg)
    active = await db.active_match_of(tg)
    if active:
        return {"state": "matched", "match": active}
    if raw_cfg.get("solo") and cfg["mode"] == "free":
        # تمرین با ربات: بدون صف، همین حالا با ربات ها
        if await db.queue_row(tg):
            await queue_leave(db, tg)
        mid = _code(10)
        await _start_game(db, mid, cfg, [{"tg": tg, "paid": 0}], create=True)
        return {"state": "matched", "match": mid}
    old = await db.queue_row(tg)
    if old:
        if old["cfg_key"] == cfg_key(cfg) and not old["claimed"]:
            return await queue_status(db, tg)
        await queue_leave(db, tg)
    held = 0
    if cfg["mode"] == "stake":
        ref = f"q{tg}-{int(time.time() * 1000)}"
        if not await spend(db, tg, cfg["entry"], "entry", f"ورودی {_gname(cfg)}", ref, f"entry:{ref}"):
            raise GCError("insufficient")
        held = cfg["entry"]
    await db.queue_put(tg, cfg_key(cfg), cfg, held)
    await try_match(db, cfg)
    return await queue_status(db, tg)


async def try_match(db: GCDatabase, cfg: dict) -> None:
    key = cfg_key(cfg)
    if not await db.lock("mm:" + key):
        return
    try:
        n = cfg["players"]
        rows = await db.queue_waiting(key)
        while len(rows) >= n:
            group, rows = rows[:n], rows[n:]
            await _from_queue(db, cfg, group)
        if rows and cfg["mode"] == "free" and gc.bot_fill_seconds and \
                time.time() - rows[0]["created_at"] >= gc.bot_fill_seconds:
            await _from_queue(db, cfg, rows)
    finally:
        await db.unlock("mm:" + key)


async def _from_queue(db: GCDatabase, cfg: dict, group: list[dict]) -> None:
    # اول میز ساخته می شود و بعد صف به آن اشاره می کند، تا کسی شماره میزی
    # را نگیرد که هنوز وجود ندارد. قفل mm:<key> نمی گذارد دو پروسه یک نفر
    # را همزمان بردارند.
    mid = _code(10)
    await _start_game(db, mid, cfg, [{"tg": r["tg_id"], "paid": r["held"]} for r in group], create=True)
    await db.queue_claim([r["tg_id"] for r in group], mid)


async def queue_status(db: GCDatabase, tg: int) -> dict:
    row = await db.queue_row(tg)
    if row and not row["claimed"]:
        await try_match(db, json.loads(row["cfg"]))
        row = await db.queue_row(tg)
    if not row:
        active = await db.active_match_of(tg)
        return {"state": "matched", "match": active} if active else {"state": "none"}
    if row["claimed"]:
        await db.queue_del(tg)
        return {"state": "matched", "match": row["claimed"]}
    waiting = await db.queue_waiting(row["cfg_key"])
    cfg = json.loads(row["cfg"])
    return {"state": "waiting", "waited": int(time.time() - row["created_at"]), "cfg": cfg,
            "found": len(waiting), "need": cfg["players"],
            "bots_in": max(0, gc.bot_fill_seconds - int(time.time() - row["created_at"]))
            if cfg["mode"] == "free" and gc.bot_fill_seconds else None,
            "can_bots": cfg["mode"] == "free"}


async def queue_bots(db: GCDatabase, tg: int) -> dict:
    """صف آزاد: بازیکن نمی خواهد منتظر بماند؛ هر که الان در صف است با ربات ها سر یک میز."""
    row = await db.queue_row(tg)
    if not row or row["claimed"]:
        return await queue_status(db, tg)
    cfg = json.loads(row["cfg"])
    if cfg["mode"] != "free":
        raise GCError("need_players")
    key = cfg_key(cfg)
    if not await db.lock("mm:" + key):
        raise GCError("busy")
    try:
        rows = await db.queue_waiting(key)
        mine = [r for r in rows if r["tg_id"] == tg]
        if mine:
            others = [r for r in rows if r["tg_id"] != tg][:cfg["players"] - 1]
            await _from_queue(db, cfg, mine + others)
    finally:
        await db.unlock("mm:" + key)
    return await queue_status(db, tg)


async def queue_leave(db: GCDatabase, tg: int) -> dict:
    row = await db.queue_row(tg)
    if not row:
        return {"state": "none"}
    if row["claimed"]:
        await db.queue_del(tg)
        return {"state": "matched", "match": row["claimed"]}
    await db.queue_del(tg)
    if row["held"]:
        await earn(db, tg, row["held"], "refund", f"انصراف از صف {_gname(json.loads(row['cfg']))}", "queue",
                   f"qrefund:{tg}:{row['created_at']}")
    return {"state": "none"}


# ---------- میز دعوت ----------
async def invite_create(db: GCDatabase, tg: int, raw_cfg: dict) -> dict:
    cfg = norm_cfg(raw_cfg)
    if await db.active_match_of(tg):
        raise GCError("in_match")
    if await db.queue_row(tg):
        await queue_leave(db, tg)
    mid, code = _code(10), _code(6)
    colors = _seat_order(cfg)
    paid, ref = 0, f"{mid}:{tg}:{int(time.time() * 1000)}"
    if cfg["mode"] == "stake":
        if not await spend(db, tg, cfg["entry"], "entry", f"ورودی {_gname(cfg)}", mid, "entry:" + ref):
            raise GCError("insufficient")
        paid = cfg["entry"]
    info = await _seat_info(db, tg)
    state = {"lobby": True, "seats": [{"color": colors[0], "tg": tg, "paid": paid, "ref": ref, **info}]}
    await db.create_match(mid, "lobby", cfg, state, tg, invite=code)
    await db.add_match_player(mid, tg, colors[0], paid)
    return {"match": mid, "code": code}


async def invite_join(db: GCDatabase, tg: int, code: str) -> dict:
    m = await db.match_by_invite(code.strip().upper()[:12])
    if not m:
        raise GCError("bad_invite")
    rows = await db.match_players(m["id"])
    if any(r["tg_id"] == tg for r in rows):
        return {"match": m["id"]}
    if m["status"] != "lobby":
        raise GCError("started")
    other = await db.active_match_of(tg)
    if other:
        raise GCError("in_match", match=other)
    cfg = m["cfg"]
    # هر نشستن یک ref تازه دارد؛ کسی که بلند شد و دوباره نشست، دوباره ورودی می دهد
    paid, ref = 0, f"{m['id']}:{tg}:{int(time.time() * 1000)}"
    if cfg["mode"] == "stake":
        if not await spend(db, tg, cfg["entry"], "entry", f"ورودی {_gname(cfg)}", m["id"], "entry:" + ref):
            raise GCError("insufficient")
        paid = cfg["entry"]
    info = await _seat_info(db, tg)

    def sit(mm: dict):
        seats = mm["state"].get("seats", [])
        if mm["status"] != "lobby":
            return False, "started"
        if any(s["tg"] == tg for s in seats):
            return False, None
        free = [c for c in _seat_order(cfg) if c not in {s["color"] for s in seats}]
        if not free:
            return False, "full"
        seats.append({"color": free[0], "tg": tg, "paid": paid, "ref": ref, **info})
        return True, free[0]

    try:
        mm, color = await mutate(db, m["id"], sit)
    except GCError:
        color = "busy"
    if color in ("full", "started", "busy"):
        if paid:
            await earn(db, tg, paid, "refund", f"بازگشت ورودی {_gname(cfg)}", m["id"], "refund:" + ref)
        raise GCError(color)
    if color:
        await db.add_match_player(m["id"], tg, color, paid)
        host = m["host"]
        if host and host != tg and await _away(db, m["id"], host, time.time()):
            await _notify(db, host, f"join:{m['id']}:{tg}", f"{info['name']} سر میز {_gname(cfg)} تو نشست!",
                          _gpage(cfg).replace(".html", "-lobby.html"))
        if len(mm["state"]["seats"]) == cfg["players"]:
            await _lobby_go(db, mm)
    return {"match": m["id"]}


async def _lobby_go(db: GCDatabase, m: dict) -> None:
    humans = [{"tg": s["tg"], "paid": s["paid"], "color": s["color"]} for s in m["state"]["seats"]]
    try:
        await _start_game(db, m["id"], m["cfg"], humans, create=False)
    except GCError as e:
        if e.code != "busy":
            raise


async def lobby_start(db: GCDatabase, tg: int, match_id: str) -> None:
    m = await db.get_match(match_id)
    if not m or m["status"] != "lobby":
        raise GCError("not_found")
    if m["host"] != tg:
        raise GCError("not_host")
    if m["cfg"]["mode"] == "stake" and len(m["state"]["seats"]) < m["cfg"]["players"]:
        raise GCError("need_players")
    await _lobby_go(db, m)


async def lobby_leave(db: GCDatabase, tg: int, m: dict) -> None:
    if m["host"] == tg:
        def cancel(mm: dict):
            if mm["status"] != "lobby":
                return False, False
            mm["status"] = "cancelled"
            return True, True
        _, ok = await mutate(db, m["id"], cancel)
        if ok:
            for s in m["state"]["seats"]:
                if s["paid"]:
                    await earn(db, s["tg"], s["paid"], "refund", f"لغو میز {_gname(m['cfg'])}", m["id"], "refund:" + s["ref"])
            await db.deactivate(m["id"])
        return

    def stand(mm: dict):
        seats = mm["state"]["seats"]
        if mm["status"] != "lobby" or not any(s["tg"] == tg for s in seats):
            return False, None
        seat = next(s for s in seats if s["tg"] == tg)
        mm["state"]["seats"] = [s for s in seats if s["tg"] != tg]
        return True, seat
    _, seat = await mutate(db, m["id"], stand)
    if seat:
        await db.execute("DELETE FROM match_players WHERE match_id = ? AND tg_id = ?", (m["id"], tg))
        if seat["paid"]:
            await earn(db, tg, seat["paid"], "refund", f"خروج از میز {_gname(m['cfg'])}", m["id"], "refund:" + seat["ref"])


# ---------- بازی ----------
async def _membership(db: GCDatabase, tg: int, match_id: str) -> tuple[list[dict], str]:
    rows = await db.match_players(match_id)
    color = _color_of(rows, tg)
    if color is None:
        raise GCError("not_found")
    return rows, color


def _ticker(now: float):
    def fn(m: dict):
        if m["status"] != "playing":
            return False, None
        changed = _eng(m["cfg"]).tick(m["state"], now)
        if m["state"]["over"]:
            m["status"] = "over"
        return changed, None
    return fn


# ---------- گفتگوی سر میز ----------
CHAT_MAX = 140
_CHAT_BAD = re.compile(r"[\u0000-\u001f\u007f\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def clean_chat(text: str) -> str:
    """فاصله های اضافه و نویسه های کنترلی و جهت دهی حذف؛ حداکثر ۱۴۰ نویسه."""
    text = _CHAT_BAD.sub(" ", str(text or ""))
    return " ".join(text.split())[:CHAT_MAX]


async def chat_send(db: GCDatabase, tg: int, match_id: str, text: str) -> dict:
    _, color = await _membership(db, tg, match_id)
    m = await db.get_match(match_id)
    if not m or m["status"] not in ("lobby", "playing"):
        raise GCError("not_found")   # بعد از پایان یا بستن میز گفتگو بسته است
    text = clean_chat(text)
    if not text:
        raise GCError("empty")
    # جلوی سیل پیام: یک پیام در ۱٫۵ ثانیه و حداکثر ۱۲ پیام در دقیقه
    if await db.chat_recent(match_id, tg, 1.5) or await db.chat_recent(match_id, tg, 60) >= 12:
        raise GCError("chat_slow")
    cid = await db.add_chat(match_id, tg, color, text)
    return {"ok": True, "id": cid}


async def chat_view(db: GCDatabase, tg: int, match_id: str, since_id: int) -> list[dict]:
    rows = await db.chat_since(match_id, max(0, since_id))
    return [{"id": r["id"], "color": r["color"], "text": r["text"], "at": int(r["created_at"]),
             "name": (r.get("name") or "بازیکن")[:24], "av": int(r.get("av") or 1), "pic": pic_url(r),
             "me": r["tg_id"] == tg} for r in rows]


async def match_view(db: GCDatabase, tg: int, match_id: str, since: int = 0, chat_since: int | None = None) -> dict:
    rows, color = await _membership(db, tg, match_id)
    await db.touch(match_id, tg)
    now = time.time()
    m, _ = await mutate(db, match_id, _ticker(now))
    if m["status"] == "playing":
        await _ping_turn(db, m, tg, now)
    cfg = m["cfg"]
    out = {"id": m["id"], "status": m["status"], "cfg": cfg, "v": m["version"], "me": color}
    if chat_since is not None:
        out["chat"] = await chat_view(db, tg, match_id, chat_since)
    if m["status"] in ("lobby", "cancelled"):
        out["lobby"] = {"seats": [{"color": s["color"], "name": s["name"], "av": s["av"], "pic": s.get("pic", ""),
                                   "me": s["tg"] == tg}
                                  for s in m["state"].get("seats", [])],
                        "code": m["invite"], "host": m["host"] == tg}
        return out
    st = m["state"]
    out["game"] = _eng(cfg).view(st, color, since, now)
    out["pot"] = st.get("pot", 0)
    if m["status"] == "over":
        won = color in _winners(st)
        out["result"] = {"won": won, "prize": prize_shares(st, rows).get(tg, 0),
                         "lost": next((r["paid"] for r in rows if r["tg_id"] == tg), 0) if not won else 0}
    return out


async def my_tables(db: GCDatabase, tg: int) -> list[dict]:
    """میزهای باز کاربر برای صفحهٔ خانه: صف، میز دعوت در انتظار، بازی در جریان."""
    out = []
    q = await db.queue_row(tg)
    if q and not q["claimed"]:
        cfg = json.loads(q["cfg"])
        out.append({"kind": "queue", "game": game_of(cfg), "cfg": cfg,
                    "found": len(await db.queue_waiting(q["cfg_key"])), "need": cfg["players"]})
    for mid in await db.active_matches_of(tg):
        m = await db.get_match(mid)
        if not m:
            continue
        cfg, st = m["cfg"], m["state"]
        rows = await db.match_players(mid)
        me = _color_of(rows, tg)
        t = {"kind": m["status"], "id": mid, "game": game_of(cfg), "cfg": cfg}
        if m["status"] == "lobby":
            seats = st.get("seats", [])
            t.update(found=len(seats), need=cfg["players"], host=m["host"] == tg,
                     players=[{"name": x["name"], "av": x["av"], "pic": x.get("pic", ""), "me": x["tg"] == tg}
                              for x in seats])
        else:
            if st.get("over"):
                continue
            t["players"] = [{"name": st["players"][c]["name"], "av": st["players"][c]["av"],
                             "pic": st["players"][c].get("pic", ""), "bot": st["players"][c]["bot"], "me": c == me}
                            for c in st["order"]]
            t["my_turn"] = _current(st) == me
            if t["game"] == "football" and me is not None:
                mine = int(me)
                t["score"] = [st["score"][mine], st["score"][1 - mine]]
                t["target"] = st["target"]
            if t["game"] == "hokm" and me is not None:
                mine = int(me) % 2
                t["score"] = [st["score"][mine], st["score"][1 - mine]]
                t["target"] = st["target"]
        out.append(t)
    return out


async def _ping_turn(db: GCDatabase, m: dict, asker: int, now: float) -> None:
    """نوبت کسی رسیده که بیرون از مینی اپ است: در ربات خبرش کن (حداکثر دو بار در هر بازی)."""
    st = m["state"]
    cur = _current(st)
    if st["over"] or cur is None:
        return
    p = st["players"][cur]
    uid = p.get("uid")
    if p["bot"] or not uid or uid == asker or not await _away(db, m["id"], uid, now):
        return
    if await db.ping_count(f"turn:{m['id']}:{uid}:") >= 2:
        return
    hk, fb = st.get("game") == "hokm", st.get("game") == "football"
    extra = (" در بازی امتیازی سه نوبت غیبت یعنی بیرون رفتن از بازی." if hk else " در بازی امتیازی سه نوبت غیبت یعنی باخت.") \
        if st.get("stake") else ""
    what = ("حکم را انتخاب کن" if st["phase"] == "trump" else "برگت را بازی کن") if hk \
        else "شوتت را بزن، وگرنه نوبت به حریف می‌رسد" if fb else "حرکت خودکار انجام می‌شود"
    await _notify(db, uid, f"turn:{m['id']}:{uid}:{st.get('turn_id', 0)}",
                  f"نوبت توست در {_gname(m['cfg'])}! {st.get('turn_s', gc.turn_seconds)} ثانیه وقت داری؛ {what}.{extra}",
                  _gpage(m["cfg"]))


async def admin_close(db: GCDatabase, match_id: str) -> dict:
    """بستن میز گیرکرده توسط ادمین: میز لغو و همه ورودی ها برمی گردد."""
    m = await db.get_match(match_id)
    if not m or m["status"] not in ("lobby", "playing"):
        raise GCError("not_open")

    def cancel(mm: dict):
        if mm["status"] not in ("lobby", "playing"):
            return False, False
        mm["status"] = "cancelled"
        return True, True

    _, ok = await mutate(db, match_id, cancel)
    if not ok:
        raise GCError("not_open")
    refunded = 0
    if m["status"] == "lobby":
        for seat in m["state"].get("seats", []):
            if seat.get("paid") and await earn(db, seat["tg"], seat["paid"], "refund", "بستن میز توسط پشتیبانی",
                                                match_id, "refund:" + seat["ref"]):
                refunded += seat["paid"]
    else:
        for r in await db.match_players(match_id):
            if r["paid"] and await earn(db, r["tg_id"], r["paid"], "refund", "بستن میز توسط پشتیبانی",
                                        match_id, f"cancel:{match_id}:{r['tg_id']}"):
                refunded += r["paid"]
    await db.mark_settled(match_id)
    await db.deactivate(match_id)
    log.warning("میز %s توسط ادمین بسته شد؛ %s امتیاز برگشت", match_id, refunded)
    return {"refunded": refunded}


async def act(db: GCDatabase, tg: int, match_id: str, action: str, k: int | None = None, since: int = 0,
              data: dict | None = None) -> dict:
    _, color = await _membership(db, tg, match_id)
    now = time.time()

    def fn(m: dict):
        if m["status"] != "playing":
            return False, "over"
        st = m["state"]
        eng = _eng(m["cfg"])
        changed = eng.tick(st, now)
        kk = int(k) if str(k if k is not None else "").lstrip("-").isdigit() else -1
        if action == "leave":
            eng.leave(st, color, now, "left")
            err = None
        elif eng is ludo and action == "roll":
            err = ludo.roll(st, color, now)
        elif eng is ludo and action == "move":
            err = ludo.move(st, color, kk, now)
        elif eng is hokm and action == "trump":
            err = hokm.choose_trump(st, int(color), kk, now)
        elif eng is hokm and action == "play":
            err = hokm.play(st, int(color), kk, now)
        elif eng is football and action == "setup":
            d = data or {}
            err = football.setup(st, color, str(d.get("team") or ""), str(d.get("fa") or ""), str(d.get("fd") or ""), now)
        elif eng is football and action == "shot":
            d = data or {}
            err = football.shot(st, int(color), d.get("i"), d.get("dx"), d.get("dy"), d.get("p"), now)
        else:
            err = "bad_action"
        if err is None and action != "leave":
            eng.human_acted(st, color)
        if st["over"]:
            m["status"] = "over"
        return changed or err is None, err

    m, err = await mutate(db, match_id, fn)
    if action == "leave":
        await db.deactivate(match_id, tg)
    if err and err not in ("over",):
        raise GCError(err)
    return await match_view(db, tg, match_id, since)


async def leave_any(db: GCDatabase, tg: int, match_id: str) -> dict:
    m = await db.get_match(match_id)
    if not m:
        raise GCError("not_found")
    if m["status"] == "lobby":
        await lobby_leave(db, tg, m)
        return {"left": True}
    if m["status"] == "playing":
        return await act(db, tg, match_id, "leave")
    await db.deactivate(match_id, tg)
    return {"left": True}


# ---------- رده بندی ----------
PERIODS = {"week": 7 * 86400, "month": 30 * 86400, "all": None}


async def leaderboard(db: GCDatabase, tg: int, kind: str, period: str) -> dict:
    span = PERIODS.get(period, PERIODS["week"])
    since = int(time.time() - span) if span else 0
    rows = await (db.top_players(since) if kind == "top" else db.top_spenders(since))
    me = await db.get_player(tg) or {}
    mine = await db.my_value(tg, since, kind)
    return {
        "kind": kind, "period": period,
        "rows": [{"name": r["name"] or "بازیکن", "av": r["av"], "pic": pic_url(r), "value": int(r["value"] or 0),
                  "wins": int(r.get("wins") or 0), "me": r["tg_id"] == tg} for r in rows],
        "mine": {"value": int(mine.get("value") or 0), "wins": int(mine.get("wins") or 0),
                 "games": int(mine.get("games") or 0), "visible": kind == "top" or bool(me.get("show_spend"))},
    }
