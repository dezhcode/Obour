"""مار و پله دو تا چهار نفره؛ فقط سمت سرور.

مثل بقیهٔ بازی ها: هیچ I/O ندارد، وضعیت یک dict ساده است که به JSON ذخیره می شود،
هر اتفاق یک رویداد شماره دار می سازد و ربات و نوبت های بی جواب فقط داخل tick جلو می روند.

قواعد:
- همه از خانهٔ ۱ شروع می کنند؛ در نوبتت تاس می ریزی و همان قدر جلو می روی
- پای نردبان بالا می روی و سر مار پایین می افتی
- برای بردن باید دقیقاً به ۱۰۰ برسی؛ اگر تاس بیشتر از لازم باشد این نوبت حرکتی نیست
- تاس ۶ یک نوبت اضافه می دهد (حداکثر دو بار پشت هم؛ ششِ سوم نوبت را تمام می کند)
- اولین کسی که به ۱۰۰ برسد برنده است و بازی همان لحظه تمام می شود

تاس سمت سرور ریخته می شود؛ مینی اپ فقط رویداد roll را نمایش می دهد (پریدن خانه به خانه، بعد
سرخوردن روی مار یا بالا رفتن از نردبان). صندلی ها "0" تا "3" (زرد، آبی، قرمز، سبز) به ترتیب نوبت.
"""
from __future__ import annotations

import random

SEATS = ("0", "1", "2", "3")
SNAKES = {17: 7, 54: 34, 62: 19, 64: 60, 87: 24, 93: 73, 95: 75, 99: 78}
LADDERS = {4: 14, 9: 31, 20: 38, 28: 84, 40: 59, 51: 67, 63: 81, 71: 91}
GOAL = 100
INTRO = 1.6
BOT_THINK = 0.9
DICE_T = 0.75        # چرخیدن تاس در مینی اپ
STEP_T = 0.17        # پریدن هر خانه
SLIDE_T = 0.95       # مار یا نردبان
PAUSE = 0.35
MAX_BONUS = 2
MAX_EVENTS = 40
TURN_S = 15

_rng = random.SystemRandom()


def seats_of(players: int) -> tuple:
    return SEATS[:max(2, min(4, int(players)))]


def jump_of(cell: int) -> int | None:
    return SNAKES.get(cell) or LADDERS.get(cell)


# ---------- وضعیت ----------
def new_state(seats: list[dict], now: float, turn_s: int, stake: bool, players: int = 2, first: int | None = None) -> dict:
    """seats: [{color: "0".."3", uid, name, av, pic, bot}]"""
    order = list(seats_of(players))
    ps = {}
    for s in seats:
        ps[s["color"]] = {"uid": s.get("uid"), "name": s["name"], "av": s.get("av", 1), "pic": s.get("pic", ""),
                          "bot": bool(s.get("bot")), "out": False, "misses": 0, "pos": 1}
    st = {
        "game": "snakes", "order": order, "n": len(order), "players": ps,
        "turn": first if first in range(len(order)) else _rng.randrange(len(order)),
        "phase": "play", "next_at": now + INTRO, "deadline": now + INTRO + TURN_S,
        "turn_s": min(max(int(turn_s), TURN_S), 60), "stake": stake, "bonus": 0, "last": None,
        "events": [], "seq": 0, "turn_id": 0, "winner": None, "over": False, "started": now,
        "stats": {s: {"rolls": 0, "sixes": 0, "ladders": 0, "snakes": 0} for s in order},
    }
    _event(st, t="start", turn=order[st["turn"]])
    _wait(st, now, INTRO)
    return st


def _event(st: dict, **e) -> None:
    st["seq"] += 1
    e["seq"] = st["seq"]
    st["events"].append(e)
    if len(st["events"]) > MAX_EVENTS:
        st["events"] = st["events"][-MAX_EVENTS:]


def _auto(st: dict, i: int) -> bool:
    p = st["players"][st["order"][i]]
    return p["bot"] or p["out"]


def _wait(st: dict, now: float, delay: float) -> None:
    if _auto(st, st["turn"]):
        delay += BOT_THINK
    st["turn_id"] = st["seq"]
    st["next_at"] = now + delay
    st["deadline"] = now + delay + st["turn_s"]


def current(st: dict) -> str | None:
    return st["order"][st["turn"]] if st["phase"] == "play" and not st["over"] else None


def _check_turn(st: dict, i: int, now: float) -> str | None:
    if st["over"]:
        return "over"
    if st["turn"] != i:
        return "not_your_turn"
    if now < st["next_at"] - 0.25:
        return "not_ready"
    return None


def roll(st: dict, i: int, now: float, auto: bool = False, v: int | None = None) -> str | None:
    """تاس نوبت دار i. v فقط برای آزمون ها."""
    err = _check_turn(st, i, now)
    if err:
        return err
    s = st["order"][i]
    p = st["players"][s]
    d = int(v) if v in range(1, 7) else _rng.randint(1, 6)
    frm = p["pos"]
    mid = frm + d if frm + d <= GOAL else frm
    to = jump_of(mid) or mid
    via = "ladder" if mid in LADDERS else "snake" if mid in SNAKES else None
    p["pos"] = to
    sx = st["stats"][s]
    sx["rolls"] += 1
    if d == 6:
        sx["sixes"] += 1
    if via:
        sx["ladders" if via == "ladder" else "snakes"] += 1
    bonus = d == 6 and to != GOAL and st["bonus"] < MAX_BONUS
    st["last"] = {"c": s, "v": d}
    _event(st, t="roll", c=s, v=d, frm=frm, mid=mid, to=to, via=via, stay=mid == frm, bonus=bonus, auto=auto)
    if to == GOAL:
        _finish(st, s)
        return None
    anim = DICE_T + (mid - frm) * STEP_T + (SLIDE_T if via else 0) + PAUSE
    if bonus:
        st["bonus"] += 1
        _wait(st, now, anim)
    else:
        st["bonus"] = 0
        _next(st, now, anim)
    return None


def _next(st: dict, now: float, delay: float) -> None:
    st["turn"] = (st["turn"] + 1) % st["n"]     # کسی که رفته هم نوبت دارد؛ ربات جایش تاس می ریزد
    _event(st, t="turn", c=st["order"][st["turn"]])
    _wait(st, now, delay)


def _finish(st: dict, w: str | None, why: str = "") -> None:
    st["over"], st["winner"], st["phase"] = True, w, "over"
    _event(st, t="win" if w is not None else "end", c=w, why=why)


def leave(st: dict, s: str, now: float, why: str = "left") -> None:
    """خروج یا جریمهٔ غیبت. دو نفره: حریف برنده. سه و چهار نفره: ربات جای او تاس می ریزد؛
    اگر هیچ آدمی سر میز نماند بازی بی برنده تمام می شود."""
    p = st["players"].get(s)
    if not p or p["out"] or st["over"]:
        return
    p["out"] = True
    _event(st, t="leave", c=s, why=why)
    if st["n"] == 2:
        _finish(st, next(k for k in st["order"] if k != s), "left")
        return
    if not any(not q["bot"] and not q["out"] for q in st["players"].values()):
        _finish(st, None, "empty")
        return
    if st["order"][st["turn"]] == s:
        st["next_at"] = min(st["next_at"], now + BOT_THINK)


# کارهای زمان دار (ربات) را از زمانِ موعدشان حساب می کنیم نه از لحظهٔ poll؛ وگرنه هر ربات منتظر
# poll بعدی می ماند. اگر کسی مدت زیادی نپرسیده، از همین لحظه.
CATCHUP = 2.0


def _due(st: dict, now: float) -> float:
    return st["next_at"] if 0 <= now - st["next_at"] <= CATCHUP else now


def tick(st: dict, now: float) -> bool:
    changed = False
    for _ in range(8):
        if st["over"]:
            break
        i = st["turn"]
        s = st["order"][i]
        p = st["players"][s]
        if _auto(st, i):
            if now < st["next_at"]:
                break
            roll(st, i, _due(st, now), auto=True)
            changed = True
            continue
        if now < st["deadline"]:
            break
        p["misses"] += 1
        _event(st, t="timeout", c=s, n=p["misses"])
        changed = True
        if st["stake"] and p["misses"] >= 3:
            leave(st, s, now, "timeout")
            continue
        # وقت تمام شد: تاس به جای او ریخته می شود
        roll(st, i, max(now, st["next_at"]), auto=True)
    return changed


def human_acted(st: dict, s: str) -> None:
    st["players"][s]["misses"] = 0


def winners(st: dict) -> set[str]:
    return {st["winner"]} if st.get("winner") else set()


def ranking(st: dict) -> list[str]:
    """برنده اول، بقیه به ترتیب جلوترین خانه."""
    return sorted(st["order"], key=lambda s: (s != st.get("winner"), -st["players"][s]["pos"]))


# ---------- نمای هر بازیکن ----------
def view(st: dict, me: str | None, since: int, now: float) -> dict:
    cur = current(st)
    auto = cur is not None and _auto(st, st["order"].index(cur))
    return {
        "order": list(st["order"]), "n": st["n"],
        "players": {s: {"name": p["name"], "av": p["av"], "pic": p.get("pic", ""), "bot": p["bot"], "out": p["out"],
                        "me": s == me, "pos": p["pos"]} for s, p in st["players"].items()},
        "me": me,
        "phase": st["phase"],
        "turn": cur,
        "can_roll": cur is not None and cur == me,
        "bonus": st["bonus"],
        "last": st.get("last"),
        "snakes": SNAKES, "ladders": LADDERS,
        "ready_ms": max(0, int((st["next_at"] - now) * 1000)) if cur is not None else 0,
        "deadline_ms": 0 if (cur is None or auto) else max(0, int((st["deadline"] - now) * 1000)),
        "turn_ms": st["turn_s"] * 1000,
        "events": [e for e in st["events"] if e["seq"] > since],
        "seq": st["seq"],
        "over": st["over"],
        "winner": st["winner"],
        "ranking": ranking(st) if st["over"] else None,
        "stats": st["stats"].get(me) if me else None,
        "started": st["started"],
    }
