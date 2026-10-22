"""دیوار (کوریدور) دو و چهار نفره؛ فقط سمت سرور.

مثل بقیهٔ بازی ها: هیچ I/O ندارد، وضعیت یک dict ساده است که به JSON ذخیره می شود،
هر اتفاق یک رویداد شماره دار می سازد و ربات و نوبت های بی جواب فقط داخل tick جلو می روند.

قواعد (کوریدور رسمی):
- هر مهره از وسط ضلع خودش شروع می کند و باید به ضلع روبه رو برسد (حالت «ستاره»: به خانهٔ وسط)
- در نوبتت یا مهره را یک خانه (بالا، پایین، چپ، راست) می بری یا یک دیوار دو خانه ای می گذاری
- اگر مهرهٔ دیگری کنارت باشد و بینتان دیوار نباشد از رویش می پری؛ اگر پشتش دیوار، لبه یا مهرهٔ
  دیگری باشد به چپ یا راست همان مهره (کج) می روی. پریدن از روی دو مهره ممنوع است
- دیوارها روی هم نمی افتند و ضربدری از هم رد نمی شوند؛ هیچ دیواری نباید راه هیچ بازیکنی را
  کامل ببندد (مهره ها مانع حساب نمی شوند)
- اولین کسی که برسد برنده است و بازی همان لحظه تمام می شود

حالت ها: ۲ نفره ۹×۹ با ۱۰ دیوار؛ ۴ نفرهٔ کلاسیک ۹×۹ با ۵ دیوار؛ ۴ نفرهٔ ستاره ۱۱×۱۱ با ۷ دیوار.

مختصات: [سطر، ستون] از گوشهٔ بالا چپ. صندلی ها با ضلع شروعشان نام گذاری شده اند:
"0" پایین، "1" چپ، "2" بالا، "3" راست (ترتیب نوبت ساعتگرد). مینی اپ صفحه را می چرخاند تا
هر کس خودش را پایین ببیند.
دیوار [o, r, c]: o="h" دیوار افقی بین سطر r و r+1 روی ستون های c و c+1؛ o="v" دیوار عمودی
بین ستون c و c+1 روی سطرهای r و r+1.
"""
from __future__ import annotations

import random
from collections import deque

SEATS2, SEATS4 = ("0", "2"), ("0", "1", "2", "3")
LOBBY_ORDER4 = ("0", "2", "1", "3")    # میز دعوت: اولین مهمان روبه روی سازنده می نشیند
WALLS = {(2, "classic"): 10, (4, "classic"): 5, (4, "star"): 7}
INTRO = 1.6
STEP_PAUSE = 0.35
BOT_THINK = 1.1
MAX_EVENTS = 40
TURN_S = 25
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))

_rng = random.SystemRandom()


def seats_of(players: int) -> tuple:
    return SEATS4 if players == 4 else SEATS2


def size_of(variant: str) -> int:
    return 11 if variant == "star" else 9


def start_of(s: str, n: int) -> list:
    m = (n - 1) // 2
    return {"0": [n - 1, m], "1": [m, 0], "2": [0, m], "3": [m, n - 1]}[s]


def at_goal(st: dict, s: str, r: int, c: int) -> bool:
    n = st["size"]
    if st["star"]:
        m = (n - 1) // 2
        return r == m and c == m
    return {"0": r == 0, "1": c == n - 1, "2": r == n - 1, "3": c == 0}[s]


# ---------- دیوارها و راه ----------
def wall_set(st: dict) -> set:
    return {(w[0], w[1], w[2]) for w in st["walls"]}


def blocked(W: set, r: int, c: int, dr: int, dc: int) -> bool:
    """دیواری بین خانهٔ (r,c) و خانهٔ کناری در جهت (dr,dc) هست؟"""
    if dr == 1:
        return ("h", r, c) in W or ("h", r, c - 1) in W
    if dr == -1:
        return ("h", r - 1, c) in W or ("h", r - 1, c - 1) in W
    if dc == 1:
        return ("v", r, c) in W or ("v", r - 1, c) in W
    return ("v", r, c - 1) in W or ("v", r - 1, c - 1) in W


def _inb(n: int, r: int, c: int) -> bool:
    return 0 <= r < n and 0 <= c < n


def path(st: dict, s: str, W: set | None = None, frm: list | None = None) -> list:
    """کوتاه ترین راه مهرهٔ s تا مقصد (بی توجه به مهره ها)؛ [] یعنی راهی نیست."""
    W = wall_set(st) if W is None else W
    n = st["size"]
    r0, c0 = frm or st["players"][s]["pos"]
    prev = {(r0, c0): None}
    q = deque([(r0, c0)])
    while q:
        r, c = q.popleft()
        if at_goal(st, s, r, c):
            out = []
            k = (r, c)
            while k is not None:
                out.append(list(k))
                k = prev[k]
            return out[::-1]
        for dr, dc in DIRS:
            nr, nc = r + dr, c + dc
            if _inb(n, nr, nc) and (nr, nc) not in prev and not blocked(W, r, c, dr, dc):
                prev[(nr, nc)] = (r, c)
                q.append((nr, nc))
    return []


def dist(st: dict, s: str, W: set | None = None, frm: list | None = None) -> int:
    p = path(st, s, W, frm)
    return len(p) - 1 if p else 10 ** 6


def wall_error(st: dict, o: str, r: int, c: int) -> str | None:
    n = st["size"]
    if o not in ("h", "v") or not (0 <= r <= n - 2 and 0 <= c <= n - 2):
        return "bad_wall"
    W = wall_set(st)
    if (o, r, c) in W or ("v" if o == "h" else "h", r, c) in W:
        return "wall_taken"
    near = (("h", r, c - 1), ("h", r, c + 1)) if o == "h" else (("v", r - 1, c), ("v", r + 1, c))
    if any(x in W for x in near):
        return "wall_taken"
    W.add((o, r, c))
    if any(not path(st, s, W) for s in st["order"]):
        return "wall_blocks"
    return None


def moves(st: dict, s: str) -> list:
    """خانه هایی که مهرهٔ s می تواند برود (با پرش و حرکت کج)."""
    n, W = st["size"], wall_set(st)
    r, c = st["players"][s]["pos"]
    occ = {tuple(p["pos"]) for k, p in st["players"].items() if k != s}
    out = []
    for dr, dc in DIRS:
        nr, nc = r + dr, c + dc
        if not _inb(n, nr, nc) or blocked(W, r, c, dr, dc):
            continue
        if (nr, nc) not in occ:
            out.append([nr, nc])
            continue
        jr, jc = nr + dr, nc + dc
        if _inb(n, jr, jc) and not blocked(W, nr, nc, dr, dc) and (jr, jc) not in occ:
            out.append([jr, jc])
            continue
        for pr, pc in (((0, 1), (0, -1)) if dr else ((1, 0), (-1, 0))):
            sr, sc = nr + pr, nc + pc
            if _inb(n, sr, sc) and not blocked(W, nr, nc, pr, pc) and (sr, sc) not in occ and [sr, sc] not in out:
                out.append([sr, sc])
    return out


# ---------- وضعیت ----------
def new_state(seats: list[dict], now: float, turn_s: int, stake: bool, players: int = 2, variant: str = "classic",
              first: int | None = None) -> dict:
    """seats: [{color: "0".."3", uid, name, av, pic, bot}]"""
    order = seats_of(players)
    variant = variant if players == 4 and variant == "star" else "classic"
    n = size_of(variant)
    walls = WALLS[(len(order), variant)]
    ps = {}
    for s in seats:
        ps[s["color"]] = {"uid": s.get("uid"), "name": s["name"], "av": s.get("av", 1), "pic": s.get("pic", ""),
                          "bot": bool(s.get("bot")), "out": False, "misses": 0, "walls": walls, "pos": start_of(s["color"], n)}
    st = {
        "game": "divar", "order": list(order), "n": len(order), "size": n, "star": variant == "star", "variant": variant,
        "players": ps, "walls": [], "turn": first if first in range(len(order)) else _rng.randrange(len(order)),
        "phase": "play", "next_at": now + INTRO, "deadline": now + INTRO + TURN_S,
        "turn_s": min(max(int(turn_s), TURN_S), 60), "stake": stake, "events": [], "seq": 0, "turn_id": 0,
        "winner": None, "over": False, "started": now,
        "stats": {s: {"moves": 0, "walls": 0} for s in order},
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


def _next(st: dict, now: float) -> None:
    st["turn"] = (st["turn"] + 1) % st["n"]
    _event(st, t="turn", c=st["order"][st["turn"]])
    _wait(st, now, STEP_PAUSE)


def _check_turn(st: dict, i: int, now: float) -> str | None:
    if st["over"]:
        return "over"
    if st["turn"] != i:
        return "not_your_turn"
    if now < st["next_at"] - 0.25:
        return "not_ready"
    return None


def move(st: dict, i: int, r, c, now: float) -> str | None:
    err = _check_turn(st, i, now)
    if err:
        return err
    try:
        to = [int(r), int(c)]
    except (TypeError, ValueError):
        return "illegal_move"
    s = st["order"][i]
    if to not in moves(st, s):
        return "illegal_move"
    p = st["players"][s]
    frm = p["pos"]
    p["pos"] = to
    st["stats"][s]["moves"] += 1
    jump = abs(to[0] - frm[0]) + abs(to[1] - frm[1]) > 1
    _event(st, t="move", c=s, frm=frm, to=to, jump=jump)
    if at_goal(st, s, *to):
        _finish(st, s)
        return None
    _next(st, now)
    return None


def wall(st: dict, i: int, o, r, c, now: float) -> str | None:
    err = _check_turn(st, i, now)
    if err:
        return err
    s = st["order"][i]
    p = st["players"][s]
    if p["walls"] <= 0:
        return "no_walls"
    try:
        r, c = int(r), int(c)
    except (TypeError, ValueError):
        return "bad_wall"
    o = str(o)
    err = wall_error(st, o, r, c)
    if err:
        return err
    st["walls"].append([o, r, c, s])
    p["walls"] -= 1
    st["stats"][s]["walls"] += 1
    _event(st, t="wall", c=s, w=[o, r, c])
    _next(st, now)
    return None


def _finish(st: dict, w: str | None, why: str = "") -> None:
    st["over"], st["winner"], st["phase"] = True, w, "over"
    _event(st, t="win" if w is not None else "end", c=w, why=why)


def leave(st: dict, s: str, now: float, why: str = "left") -> None:
    """خروج یا جریمهٔ غیبت. دو نفره: حریف برنده. چهار نفره: ربات جای او بازی می کند؛
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


# ---------- ربات ----------
def _step(st: dict, s: str) -> list | None:
    """بهترین خانه از میان حرکت های مجاز: نزدیک ترین به مقصد (کمی تصادفی بین هم ارزها)."""
    W = wall_set(st)
    best, bd = None, None
    for m in moves(st, s):
        d = dist(st, s, W, m) + _rng.random() * 0.4
        if bd is None or d < bd:
            best, bd = m, d
    return best


def _wall_cands(st: dict, path_cells: list, upto: int = 4) -> list:
    out = []
    for k in range(min(upto, len(path_cells) - 1)):
        (r1, c1), (r2, c2) = path_cells[k], path_cells[k + 1]
        if r1 != r2:
            r = min(r1, r2)
            out += [("h", r, c1), ("h", r, c1 - 1)]
        else:
            c = min(c1, c2)
            out += [("v", r1, c), ("v", r1 - 1, c)]
    return out


def bot_turn(st: dict, i: int) -> tuple:
    """("move", r, c) یا ("wall", o, r, c). دیوار وقتی که حریفی جلوتر یا خیلی نزدیک مقصد است و
    دیوار راه او را بیشتر از راه خودمان طولانی می کند."""
    s = st["order"][i]
    p = st["players"][s]
    W = wall_set(st)
    mine = dist(st, s, W)
    lead, lp = None, None
    for k in st["order"]:
        if k == s:
            continue
        pk = path(st, k, W)
        if pk and (lp is None or len(pk) < len(lp)):
            lead, lp = k, pk
    if p["walls"] > 0 and lp and (len(lp) - 1 < mine or len(lp) - 1 <= 2) and _rng.random() < 0.8:
        best, bs = None, 0.0
        theirs = len(lp) - 1
        for o, r, c in _wall_cands(st, lp):
            if wall_error(st, o, r, c):
                continue
            W2 = W | {(o, r, c)}
            gain = dist(st, lead, W2) - theirs
            cost = dist(st, s, W2) - mine
            sc = gain - 0.7 * cost + _rng.random() * 0.3
            if sc > bs:
                best, bs = (o, r, c), sc
        if best and (bs >= 1.5 or theirs <= 2):
            return ("wall",) + best
    m = _step(st, s)
    return ("move", m[0], m[1]) if m else ("pass",)


# کارهای زمان دار (ربات، جمع کردن دور، دست بعد) را از زمانِ موعدشان حساب می کنیم نه از لحظهٔ poll؛
# وگرنه هر ربات منتظر poll بعدی می ماند و با سه ربات نوبت آدم چند ثانیه دیرتر می رسد.
# اگر کسی مدت زیادی نپرسیده، از همین لحظه (تا مهلت نفر بعد بی دلیل نسوزد).
CATCHUP = 2.0


def _due(st: dict, now: float) -> float:
    return st["next_at"] if 0 <= now - st["next_at"] <= CATCHUP else now


def tick(st: dict, now: float) -> bool:
    changed = False
    for _ in range(4):
        if st["over"]:
            break
        i = st["turn"]
        s = st["order"][i]
        p = st["players"][s]
        if _auto(st, i):
            if now < st["next_at"]:
                break
            act, t = bot_turn(st, i), _due(st, now)
            if act[0] == "wall":
                wall(st, i, act[1], act[2], act[3], t)
            elif act[0] == "move":
                move(st, i, act[1], act[2], t)
            else:
                _next(st, t)
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
        # وقت تمام شد: یک قدم در کوتاه ترین راه به جای او
        m = _step(st, s)
        if m:
            move(st, i, m[0], m[1], max(now, st["next_at"]))
        else:
            _next(st, now)
    return changed


def human_acted(st: dict, s: str) -> None:
    st["players"][s]["misses"] = 0


def winners(st: dict) -> set[str]:
    return {st["winner"]} if st.get("winner") else set()


# ---------- نمای هر بازیکن ----------
def view(st: dict, me: str | None, since: int, now: float) -> dict:
    cur = current(st)
    auto = cur is not None and _auto(st, st["order"].index(cur))
    W = wall_set(st)
    return {
        "order": list(st["order"]),
        "n": st["n"], "size": st["size"], "star": st["star"], "variant": st["variant"],
        "players": {s: {"name": p["name"], "av": p["av"], "pic": p.get("pic", ""), "bot": p["bot"], "out": p["out"],
                        "me": s == me, "walls": p["walls"], "pos": p["pos"], "left": dist(st, s, W)}
                    for s, p in st["players"].items()},
        "me": me,
        "phase": st["phase"],
        "turn": cur,
        "walls": st["walls"],
        "moves": moves(st, me) if cur is not None and cur == me else [],
        "ready_ms": max(0, int((st["next_at"] - now) * 1000)) if cur is not None else 0,
        "deadline_ms": 0 if (cur is None or auto) else max(0, int((st["deadline"] - now) * 1000)),
        "turn_ms": st["turn_s"] * 1000,
        "events": [e for e in st["events"] if e["seq"] > since],
        "seq": st["seq"],
        "over": st["over"],
        "winner": st["winner"],
        "stats": st["stats"].get(me) if me else None,
        "started": st["started"],
    }
