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
import secrets
import time

from . import ludo
from .config import gc
from .db import GCDatabase

log = logging.getLogger("gameclub.service")

BOT_NAMES = ("سارا", "امیر", "نگار", "رضا", "مهسا", "علی", "پریا", "کیان", "هستی", "سینا", "آرش", "یاسمن")
_ALPH = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


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
    return {"name": (p.get("name") or "بازیکن")[:24], "av": int(p.get("av") or 1)}


async def _start_game(db: GCDatabase, match_id: str, cfg: dict, humans: list[dict], *, create: bool) -> None:
    """humans: [{tg, paid, color?}] → میز در حال بازی."""
    colors = list(ludo.SEATS[cfg["players"]])
    seats, used = [], set()
    for h in humans:
        c = h.get("color") if h.get("color") in colors and h.get("color") not in used else \
            next(x for x in colors if x not in used)
        used.add(c)
        info = await _seat_info(db, h["tg"])
        seats.append({"color": c, "uid": h["tg"], "name": info["name"], "av": info["av"], "bot": False, "paid": h["paid"]})
    names = random.sample(BOT_NAMES, len(BOT_NAMES))
    for c in colors:
        if c not in used:
            if cfg["mode"] == "stake":
                raise GCError("need_players")
            seats.append({"color": c, "uid": None, "name": "ربات " + names.pop(), "av": random.randint(1, 23), "bot": True})
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


async def settle(db: GCDatabase, m: dict) -> None:
    """یک بار و فقط یک بار: جایزه، نتیجه ها، آزاد کردن بازیکن ها."""
    if not await db.mark_settled(m["id"]):
        return
    st, cfg = m["state"], m["cfg"]
    rows = await db.match_players(m["id"])
    winner = st.get("winner")
    pot = sum(r["paid"] for r in rows)
    prize = pot - pot * gc.rake_percent // 100
    for r in rows:
        won = r["color"] == winner
        if cfg["mode"] == "stake":
            if winner is None and r["paid"]:
                await earn(db, r["tg_id"], r["paid"], "refund", "بازگشت ورودی منچ", m["id"], f"endrefund:{m['id']}:{r['tg_id']}")
            elif won and prize:
                await earn(db, r["tg_id"], prize, "prize", "جایزهٔ منچ", m["id"], f"prize:{m['id']}")
        await db.add_result(m["id"], r["tg_id"], won, prize if (won and cfg["mode"] == "stake") else 0)
    await db.deactivate(m["id"])


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
        if not await spend(db, tg, cfg["entry"], "entry", "ورودی منچ", ref, f"entry:{ref}"):
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
        if rows and cfg["mode"] == "free" and time.time() - rows[0]["created_at"] >= gc.bot_fill_seconds:
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
            "bots_in": max(0, gc.bot_fill_seconds - int(time.time() - row["created_at"])) if cfg["mode"] == "free" else None}


async def queue_leave(db: GCDatabase, tg: int) -> dict:
    row = await db.queue_row(tg)
    if not row:
        return {"state": "none"}
    if row["claimed"]:
        await db.queue_del(tg)
        return {"state": "matched", "match": row["claimed"]}
    await db.queue_del(tg)
    if row["held"]:
        await earn(db, tg, row["held"], "refund", "انصراف از صف منچ", "queue", f"qrefund:{tg}:{row['created_at']}")
    return {"state": "none"}


# ---------- میز دعوت ----------
async def invite_create(db: GCDatabase, tg: int, raw_cfg: dict) -> dict:
    cfg = norm_cfg(raw_cfg)
    if await db.active_match_of(tg):
        raise GCError("in_match")
    if await db.queue_row(tg):
        await queue_leave(db, tg)
    mid, code = _code(10), _code(6)
    colors = ludo.SEATS[cfg["players"]]
    paid, ref = 0, f"{mid}:{tg}:{int(time.time() * 1000)}"
    if cfg["mode"] == "stake":
        if not await spend(db, tg, cfg["entry"], "entry", "ورودی منچ", mid, "entry:" + ref):
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
        if not await spend(db, tg, cfg["entry"], "entry", "ورودی منچ", m["id"], "entry:" + ref):
            raise GCError("insufficient")
        paid = cfg["entry"]
    info = await _seat_info(db, tg)

    def sit(mm: dict):
        seats = mm["state"].get("seats", [])
        if mm["status"] != "lobby":
            return False, "started"
        if any(s["tg"] == tg for s in seats):
            return False, None
        free = [c for c in ludo.SEATS[cfg["players"]] if c not in {s["color"] for s in seats}]
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
            await earn(db, tg, paid, "refund", "بازگشت ورودی منچ", m["id"], "refund:" + ref)
        raise GCError(color)
    if color:
        await db.add_match_player(m["id"], tg, color, paid)
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
                    await earn(db, s["tg"], s["paid"], "refund", "لغو میز منچ", m["id"], "refund:" + s["ref"])
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
            await earn(db, tg, seat["paid"], "refund", "خروج از میز منچ", m["id"], "refund:" + seat["ref"])


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
        changed = ludo.tick(m["state"], now)
        if m["state"]["over"]:
            m["status"] = "over"
        return changed, None
    return fn


async def match_view(db: GCDatabase, tg: int, match_id: str, since: int = 0) -> dict:
    rows, color = await _membership(db, tg, match_id)
    now = time.time()
    m, _ = await mutate(db, match_id, _ticker(now))
    cfg = m["cfg"]
    out = {"id": m["id"], "status": m["status"], "cfg": cfg, "v": m["version"], "me": color}
    if m["status"] in ("lobby", "cancelled"):
        out["lobby"] = {"seats": [{"color": s["color"], "name": s["name"], "av": s["av"], "me": s["tg"] == tg}
                                  for s in m["state"].get("seats", [])],
                        "code": m["invite"], "host": m["host"] == tg}
        return out
    st = m["state"]
    out["game"] = ludo.view(st, color, since, now)
    out["pot"] = st.get("pot", 0)
    if m["status"] == "over":
        prize = (st.get("pot", 0) - st.get("pot", 0) * gc.rake_percent // 100) if cfg["mode"] == "stake" else 0
        out["result"] = {"won": st.get("winner") == color, "prize": prize if st.get("winner") == color else 0,
                         "lost": next((r["paid"] for r in rows if r["tg_id"] == tg), 0) if st.get("winner") != color else 0}
    return out


async def act(db: GCDatabase, tg: int, match_id: str, action: str, k: int | None = None, since: int = 0) -> dict:
    _, color = await _membership(db, tg, match_id)
    now = time.time()

    def fn(m: dict):
        if m["status"] != "playing":
            return False, "over"
        st = m["state"]
        changed = ludo.tick(st, now)
        if action == "roll":
            err = ludo.roll(st, color, now)
        elif action == "move":
            err = ludo.move(st, color, int(k if k is not None else -1), now)
        elif action == "leave":
            ludo.leave(st, color, now, "left")
            err = None
        else:
            err = "bad_action"
        if err is None and action != "leave":
            ludo.human_acted(st, color)
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
        "rows": [{"name": r["name"] or "بازیکن", "av": r["av"], "value": int(r["value"] or 0),
                  "wins": int(r.get("wins") or 0), "me": r["tg_id"] == tg} for r in rows],
        "mine": {"value": int(mine.get("value") or 0), "wins": int(mine.get("wins") or 0),
                 "games": int(mine.get("games") or 0), "visible": kind == "top" or bool(me.get("show_spend"))},
    }
