"""قواعد منچ؛ فقط سمت سرور.

این ماژول هیچ I/O ندارد: وضعیت یک dict ساده است که در دیتابیس به JSON
ذخیره می شود. هر کاری که روی میز اتفاق می افتد یک رویداد شماره دار
می سازد؛ مینی اپ همان رویدادها را به ترتیب پخش می کند (تاس، پرش مهره،
زدن) و بعد خودش را با وضعیت نهایی یکی می کند.

زمان بندی: ربات ها و نوبت های بی جواب فقط داخل tick جلو می روند و tick
با هر درخواست مینی اپ صدا زده می شود. یعنی هیچ کار پس زمینه ای لازم
نیست (روی Passenger نمی شود ترد دائمی داشت).
"""
from __future__ import annotations

import random
import secrets
from typing import Callable

TRACK = [(1,6),(2,6),(3,6),(4,6),(5,6),(6,5),(6,4),(6,3),(6,2),(6,1),(6,0),(7,0),(8,0),(8,1),(8,2),(8,3),(8,4),(8,5),
         (9,6),(10,6),(11,6),(12,6),(13,6),(14,6),(14,7),(14,8),(13,8),(12,8),(11,8),(10,8),(9,8),(8,9),(8,10),(8,11),
         (8,12),(8,13),(8,14),(7,14),(6,14),(6,13),(6,12),(6,11),(6,10),(6,9),(5,8),(4,8),(3,8),(2,8),(1,8),(0,8),(0,7),(0,6)]
ORDER = ("blue", "red", "green", "yellow")
START = {"blue": 0, "red": 13, "green": 26, "yellow": 39}
SAFE = frozenset((0, 8, 13, 21, 26, 34, 39, 47))
FIN = 56            # ۰ خانه شروع، ۵۰ آخرین خانه مسیر مشترک، ۵۱ تا ۵۵ راهرو، ۵۶ مرکز
YARD = -1
SEATS = {2: ("yellow", "red"), 4: ORDER}
MAX_EVENTS = 40

Rng = Callable[[], int]


def server_die() -> int:
    """تاس سمت سرور؛ از منبع امن سیستم عامل."""
    return secrets.randbelow(6) + 1


def track_index(color: str, p: int) -> int:
    return (START[color] + p) % 52 if 0 <= p <= 50 else -1


# ---------- ساخت ----------
def new_state(seats: list[dict], n_pawns: int, now: float, turn_s: int, stake: bool, first: str | None = None) -> dict:
    """seats: [{color, uid, name, av, bot}]"""
    order = [c for c in ORDER if any(s["color"] == c for s in seats)]
    players = {s["color"]: {"uid": s.get("uid"), "name": s["name"], "av": s.get("av", 1), "bot": bool(s.get("bot")),
                            "out": False, "misses": 0} for s in seats}
    turn = order.index(first) if first in order else random.randrange(len(order))
    st = {
        "order": order, "players": players, "pawns": {c: [YARD] * n_pawns for c in order},
        "turn": turn, "phase": "roll", "dice": None, "movable": [], "sixes": 0,
        "next_at": now + 1.5, "deadline": now + 1.5 + turn_s, "turn_s": turn_s, "stake": stake,
        "last": {}, "events": [], "seq": 0, "winner": None, "over": False, "started": now,
        "stats": {c: {"caps": 0, "sixes": 0} for c in order},
    }
    return st


def current(st: dict) -> str:
    return st["order"][st["turn"]]


def _event(st: dict, **e) -> None:
    st["seq"] += 1
    e["seq"] = st["seq"]
    st["events"].append(e)
    if len(st["events"]) > MAX_EVENTS:
        st["events"] = st["events"][-MAX_EVENTS:]


def legal(st: dict, c: str, d: int) -> list[int]:
    return [k for k, p in enumerate(st["pawns"][c]) if (p == YARD and d == 6) or (0 <= p and p + d <= FIN)]


def active_colors(st: dict) -> list[str]:
    return [c for c in st["order"] if not st["players"][c]["out"]]


# ---------- انتخاب حرکت (ربات و نوبت بی جواب) ----------
def _danger(st: dict, c: str, ti: int) -> bool:
    for o in active_colors(st):
        if o == c:
            continue
        for q in st["pawns"][o]:
            oi = track_index(o, q)
            if oi >= 0 and 1 <= (ti - oi) % 52 <= 6:
                return True
    return False


def best_move(st: dict, c: str, d: int, moves: list[int]) -> int:
    best, best_s = moves[0], -1e9
    for k in moves:
        p = st["pawns"][c][k]
        np = 0 if p == YARD else p + d
        ti, cur = track_index(c, np), track_index(c, p)
        s = np / 8 + random.random() * 3
        if p == YARD:
            s += 50
        if np == FIN:
            s += 80
        if p <= 50 < np:
            s += 35
        if ti >= 0:
            if ti in SAFE:
                s += 15
            else:
                if any(track_index(o, q) == ti for o in active_colors(st) if o != c for q in st["pawns"][o]):
                    s += 100
                if _danger(st, c, ti):
                    s -= 40
        if cur >= 0 and cur not in SAFE and _danger(st, c, cur):
            s += 25
        if s > best_s:
            best, best_s = k, s
    return best


# ---------- نوبت ----------
def _next_turn(st: dict) -> None:
    n = len(st["order"])
    for _ in range(n):
        st["turn"] = (st["turn"] + 1) % n
        if not st["players"][current(st)]["out"]:
            return


def _begin_turn(st: dict, now: float, wait: float) -> None:
    st["phase"], st["dice"], st["movable"] = "roll", None, []
    st["next_at"] = now + wait
    st["deadline"] = now + wait + st["turn_s"]


def _finish(st: dict, winner: str | None) -> None:
    st["over"], st["winner"], st["phase"], st["movable"] = True, winner, "over", []
    _event(st, t="win" if winner else "end", c=winner)


def roll(st: dict, c: str, now: float, value: int | None = None, auto: bool = False) -> str | None:
    """None یعنی انجام شد؛ وگرنه کد خطا."""
    if st["over"]:
        return "over"
    if current(st) != c:
        return "not_your_turn"
    if st["phase"] != "roll":
        return "not_roll_phase"
    d = value or server_die()
    st["dice"] = d
    st["last"][c] = d
    if d == 6:
        st["stats"][c]["sixes"] += 1
    _event(st, t="roll", c=c, v=d, auto=auto)
    moves = legal(st, c, d)
    if not moves:
        _event(st, t="nomove", c=c, v=d)
        st["sixes"] = 0
        _next_turn(st)
        _begin_turn(st, now, 1.6)
        return None
    st["phase"], st["movable"] = "move", moves
    st["next_at"] = now + 0.9
    st["deadline"] = now + 0.9 + st["turn_s"]
    # یک حرکت ممکن (یا همه در لانه، که همه یکی اند): بدون معطلی انجام می شود
    pawns = st["pawns"][c]
    if len(moves) == 1 or all(pawns[k] == YARD for k in moves):
        return move(st, c, moves[0], now + 0.9, auto=True, forced=True)
    return None


def move(st: dict, c: str, k: int, now: float, auto: bool = False, forced: bool = False) -> str | None:
    if st["over"]:
        return "over"
    if current(st) != c:
        return "not_your_turn"
    if st["phase"] != "move":
        return "not_move_phase"
    if k not in st["movable"]:
        return "illegal_move"
    d = st["dice"]
    pawns = st["pawns"][c]
    frm = pawns[k]
    to = 0 if frm == YARD else frm + d
    pawns[k] = to
    caps: list[list] = []
    ti = track_index(c, to)
    if ti >= 0 and ti not in SAFE:
        for o in active_colors(st):
            if o == c:
                continue
            for j, q in enumerate(st["pawns"][o]):
                if track_index(o, q) == ti:
                    st["pawns"][o][j] = YARD
                    caps.append([o, j])
    fin = to == FIN
    st["stats"][c]["caps"] += len(caps)
    _event(st, t="move", c=c, k=k, frm=frm, to=to, cap=caps, fin=fin, auto=auto and not forced)
    steps = 1 if frm == YARD else d
    anim = 0.35 + steps * 0.17 + (0.7 if caps else 0) + (0.4 if fin else 0)
    if all(p == FIN for p in pawns):
        _finish(st, c)
        return None
    extra = d == 6 or bool(caps) or fin
    st["sixes"] = st["sixes"] + 1 if d == 6 else 0
    if st["sixes"] >= 3:
        _event(st, t="six3", c=c)
        st["sixes"] = 0
        _next_turn(st)
    elif not extra:
        st["sixes"] = 0
        _next_turn(st)
    _begin_turn(st, now, anim + 0.4)
    return None


def leave(st: dict, c: str, now: float, why: str = "left") -> None:
    """خروج یا جریمه سه نوبت غیبت: مهره ها از صفحه برداشته می شوند."""
    p = st["players"].get(c)
    if not p or p["out"] or st["over"]:
        return
    was_turn = current(st) == c
    p["out"] = True
    st["pawns"][c] = []
    _event(st, t="leave", c=c, why=why)
    alive = active_colors(st)
    humans = [x for x in alive if not st["players"][x]["bot"]]
    if not humans:
        _finish(st, alive[0] if len(alive) == 1 and st["stake"] else None)
        return
    if len(alive) == 1:
        _finish(st, alive[0])
        return
    if was_turn:
        st["sixes"] = 0
        _next_turn(st)
        _begin_turn(st, now, 0.8)


def tick(st: dict, now: float, die: Rng = server_die) -> bool:
    """ربات ها و نوبت های تمام شده را جلو می برد. True یعنی چیزی عوض شد."""
    changed = False
    for _ in range(8):
        if st["over"]:
            break
        c = current(st)
        p = st["players"][c]
        if p["bot"]:
            if now < st["next_at"]:
                break
            if st["phase"] == "roll":
                roll(st, c, now, die())
            else:
                move(st, c, best_move(st, c, st["dice"], st["movable"]), now)
            changed = True
            continue
        if now < st["deadline"]:
            break
        # وقت بازیکن تمام شد: تاس و بهترین حرکت خودکار
        p["misses"] += 1
        _event(st, t="timeout", c=c, n=p["misses"])
        if st["stake"] and p["misses"] >= 3:
            leave(st, c, now, "timeout")
        elif st["phase"] == "roll":
            roll(st, c, now, die(), auto=True)
        else:
            move(st, c, best_move(st, c, st["dice"], st["movable"]), now, auto=True)
        changed = True
    return changed


def human_acted(st: dict, c: str) -> None:
    st["players"][c]["misses"] = 0


# ---------- نمای هر بازیکن ----------
def view(st: dict, me: str | None, since: int, now: float) -> dict:
    cur = current(st)
    cp = st["players"][cur]
    return {
        "order": st["order"],
        "players": {c: {"name": p["name"], "av": p["av"], "bot": p["bot"], "out": p["out"], "me": c == me}
                    for c, p in st["players"].items()},
        "pawns": st["pawns"],
        "turn": None if st["over"] else cur,
        "phase": st["phase"],
        "dice": st["dice"],
        "movable": st["movable"] if (cur == me and st["phase"] == "move") else [],
        "deadline_ms": 0 if (st["over"] or cp["bot"]) else max(0, int((st["deadline"] - now) * 1000)),
        "turn_ms": st["turn_s"] * 1000,
        "last": st["last"],
        "done": {c: sum(1 for p in st["pawns"][c] if p == FIN) for c in st["order"]},
        "events": [e for e in st["events"] if e["seq"] > since],
        "seq": st["seq"],
        "over": st["over"],
        "winner": st["winner"],
        "stats": st["stats"].get(me) if me else None,
        "started": st["started"],
    }
