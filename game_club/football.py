"""فوتبال میزی دو نفره (Table Soccer پلاتو، حالت تاکتیکی)؛ فقط سمت سرور.

مثل منچ و حکم: هیچ I/O ندارد، وضعیت یک dict ساده است که به JSON ذخیره می شود،
هر اتفاق یک رویداد شماره دار می سازد و ربات و نوبت های بی جواب فقط داخل tick جلو می روند.
فیزیک (football_phys.py) پورت دقیق موتور بازی پلاتو است؛ قوانین هم از کد همان بازی آمده اند:

- هر بازیکن شش مهره دارد (اولی دروازه بان)؛ صندلی ۰ از دروازهٔ پایین دفاع می کند و به بالا حمله
  می کند، صندلی ۱ برعکس. اول بازی هر کس تیم و چیدمان حمله و دفاعش را می گذارد
- در نوبتت یک مهره را به سمت دلخواه شوت می کنی (کشیدن تا ۲۵۰ واحد)؛ فقط یک شوت در هر نوبت
- پاس: اگر مهره ای از خودت توپ را بزند (شوت زننده) و بعد توپ به مهرهٔ دیگری از خودت بخورد (گیرنده)
  و پایان حرکت توپ تا ۲۳۶ واحد از گیرنده دور نباشد، پاس کامل است: توپ مثل آهن ربا به گیرنده می چسبد،
  گیرنده خودش پشت توپ و رو به دروازه می نشیند و دوباره نوبت توست (زمان نوبت هر پاس ۳ ثانیه کمتر
  تا حداقل ۸ ثانیه). بدون پاس، توپ را از دست می دهی و نوبت حریف است
- گل: توپ کامل از خط دروازه بگذرد. گل از ضربهٔ شروع بازی خطاست و حساب نمی شود. بعد از گل همه
  سر جایشان برمی گردند و تیمی که گل خورده شروع می کند
- اولین کسی که به تعداد گل هدف (۲، ۳ یا ۵) برسد برنده است؛ خروج یعنی باخت

اندازه ها (واحد زمین) و فیزیک در football_phys.py؛ ورودی شوت: جهت (dx، dy) و قدرت ۰..۱
(= طول کشیدن ÷ ۲۵۰). مهره های صندلی ۰ شماره ۰ تا ۵، صندلی ۱ شماره ۶ تا ۱۱ و توپ ۱۲.
"""
from __future__ import annotations

import math
import random

from . import football_phys as P
from .football_phys import BALL, BALL_R, CONTROL_RADIUS, GOAL_H, H, IMPULSE_MAX, IMPULSE_MULT, N, W, radius_of

SEATS = ("0", "1")
GOALS_TO_WIN = (2, 3, 5)
PASS_LIMITS = (0, 3, 6)           # ۰ = بی نهایت
MIN_POWER = 0.02
SETUP_S = 20.0           # انتخاب تیم و چیدمان
INTRO = 3.4              # نمایش «مقابل» قبل از شروع
SHOT_PAUSE = 0.35
GOAL_PAUSE = 3.0         # جشن گل و برگشت مهره ها
BOT_THINK = 1.1
TURN_S = 20              # پیش فرض زمان نوبت (ثانیه)؛ شوت اول نوبت ۱٫۵ برابر
MAX_EVENTS = 40
RANDOM_DISPLACEMENT = 8.0

TEAMS = ("eagles", "lions", "cheetahs", "mountain", "storm", "sea")
FORMS = ("132", "123", "141", "1212")
_FORM_NAME = {"132": "1-3-2", "123": "1-2-3", "141": "1-4-1", "1212": "1-2-1-2"}
# چیدمان ها از bundle بازی پلاتو (کسر عرض و ارتفاع؛ ارتفاع از دروازهٔ خودی؛ اولی دروازه بان)
_K = None
_FORM = {
    "1-3-2": ((.5, _K), (.22, .22), (.5, .2), (.78, .22), (.4, .38), (.6, .38)),
    "d:1-3-2": ((.5, _K), (.26, .12), (.5, .17), (.74, .12), (.36, .24), (.64, .24)),
    "1-2-3": ((.5, _K), (.4, .2), (.6, .2), (.22, .33), (.78, .33), (.5, .35)),
    "d:1-2-3": ((.5, _K), (.4, .11), (.6, .11), (.22, .25), (.78, .25), (.5, .26)),
    "1-4-1": ((.5, _K), (.17, .25), (.39, .21), (.61, .21), (.83, .25), (.5, .35)),
    "d:1-4-1": ((.5, _K), (.25, .14), (.42, .12), (.58, .12), (.75, .14), (.5, .35)),
    "1-2-1-2": ((.5, _K), (.35, .18), (.65, .18), (.5, .3), (.35, .38), (.65, .38)),
    "d:1-2-1-2": ((.5, _K), (.35, .12), (.65, .12), (.5, .21), (.35, .3), (.65, .3)),
}

_rng = random.SystemRandom()


def other(i: int) -> int:
    return 1 - i


def turn_time(base: float, chain: int, misses: int = 0) -> float:
    """مهلت نوبت (getTurnTime پلاتو): شوت اول ۱٫۵ برابر، هر پاس ۳ ثانیه کمتر تا ۸ ثانیه؛ غایب ها حداکثر ۱۰."""
    base = float(base)
    t = base * 1.5 if chain <= 0 else max(min(8.0, base), base - 3.0 * (chain - 1))
    return min(t, 10.0) if misses >= 2 else t


def formation(seat: int, form: str, attack: bool) -> list:
    name = _FORM_NAME.get(form, "1-3-2")
    pts = _FORM[name if attack else "d:" + name]
    out = []
    for fx, fy in pts:
        y = GOAL_H if fy is None else fy * H
        out.append([fx * W, H - y if seat == 0 else y])
    return out


def _disp() -> float:
    return _rng.random() * RANDOM_DISPLACEMENT - RANDOM_DISPLACEMENT * 0.5


def kickoff_pos(st: dict, random_disp: bool = True) -> list:
    """چیدمان شروع: تیم شروع کننده چیدمان حمله و حریف چیدمان دفاعش را می گذارد؛ توپ وسط زمین."""
    k = st["kick"]
    pos = []
    for i, s in enumerate(SEATS):
        p = st["players"][s]
        pos += formation(i, p["fa"] if i == k else p["fd"], i == k)
    pos.append([W / 2, H / 2])
    if random_disp:
        pos = [[P.rd2(x + _disp()), P.rd2(y + _disp())] for x, y in pos]
    return pos


# ---------- ساخت ----------
def new_state(seats: list[dict], now: float, turn_s: int, stake: bool, target: int, first: int | None = None,
              passes: int = 0) -> dict:
    """seats: [{color: "0" | "1", uid, name, av, pic, bot}]"""
    taken = set()
    players = {}
    for s in seats:
        bot = bool(s.get("bot"))
        team = None
        if bot:
            team = _rng.choice([t for t in TEAMS if t not in taken])
            taken.add(team)
        players[s["color"]] = {"uid": s.get("uid"), "name": s["name"], "av": s.get("av", 1), "pic": s.get("pic", ""),
                               "bot": bot, "out": False, "misses": 0, "team": team, "kit": "home",
                               "fa": _rng.choice(FORMS) if bot else "132", "fd": _rng.choice(FORMS) if bot else "132",
                               "ready": bot}
    st = {
        "game": "football", "order": list(SEATS), "players": players, "target": target if target in GOALS_TO_WIN else 3,
        "passes": passes if passes in PASS_LIMITS else 0, "score": [0, 0],
        "phase": "setup", "turn": 0, "kick": first if first in (0, 1) else _rng.randrange(2),
        "pos": [], "next_at": now + SETUP_S, "deadline": now + SETUP_S, "turn_s": min(max(int(turn_s), 8), 60),
        "stake": stake, "events": [], "seq": 0, "turn_id": 0, "winner": None, "over": False, "started": now,
        "stats": {s: {"shots": 0, "goals": 0, "passes": 0} for s in SEATS}, "chain": 0, "new_ko": True,
    }
    st["pos"] = kickoff_pos(st)
    _event(st, t="setup")
    if all(p["ready"] for p in players.values()):
        _start(st, now)
    return st


def _event(st: dict, **e) -> None:
    st["seq"] += 1
    e["seq"] = st["seq"]
    st["events"].append(e)
    if len(st["events"]) > MAX_EVENTS:
        st["events"] = st["events"][-MAX_EVENTS:]


def _auto(st: dict, i: int) -> bool:
    p = st["players"][SEATS[i]]
    return p["bot"] or p["out"]


def _wait(st: dict, now: float, delay: float) -> None:
    """نوبت تازه: بعد از پایان انیمیشن (delay) شروع می شود و مهلتش از آن لحظه حساب می شود."""
    i = st["turn"]
    if _auto(st, i):
        delay += BOT_THINK
    st["turn_id"] = st["seq"]
    st["next_at"] = now + delay
    st["deadline"] = now + delay + turn_time(st["turn_s"], st["chain"], st["players"][SEATS[i]]["misses"])


def current(st: dict) -> str | None:
    return SEATS[st["turn"]] if st["phase"] == "play" and not st["over"] else None


# ---------- انتخاب تیم و چیدمان ----------
def setup(st: dict, s: str, team: str, fa: str, fd: str, now: float) -> str | None:
    if st["over"]:
        return "over"
    if st["phase"] != "setup":
        return "not_setup"
    p = st["players"].get(s)
    if not p:
        return "not_found"
    if team not in TEAMS or fa not in FORMS or fd not in FORMS:
        return "bad_setup"
    p.update(team=team, fa=fa, fd=fd, ready=True)
    _event(st, t="ready", c=s)
    if all(q["ready"] for q in st["players"].values()):
        _start(st, now)
    return None


def _start(st: dict, now: float) -> None:
    taken = [p["team"] for p in st["players"].values() if p["team"]]
    for s in SEATS:
        p = st["players"][s]
        if not p["team"]:
            p["team"] = next((t for t in TEAMS if t not in taken), TEAMS[0])
            taken.append(p["team"])
        p["ready"] = True
    a, b = st["players"]["0"], st["players"]["1"]
    a["kit"], b["kit"] = "home", "away" if a["team"] == b["team"] else "home"
    st["phase"], st["turn"], st["chain"], st["new_ko"] = "play", st["kick"], 0, True
    st["pos"] = kickoff_pos(st)
    _event(st, t="start", teams={s: {"team": p["team"], "kit": p["kit"]} for s, p in st["players"].items()},
           pos=st["pos"], kick=SEATS[st["kick"]])
    _wait(st, now, INTRO)


# ---------- شوت ----------
def impulse(dx: float, dy: float, power: float) -> tuple[float, float] | None:
    """ضربه = جهت × (قدرت × ۲۵۰) × ۴٫۶ (IMPULSE در پلاتو)."""
    ln = math.sqrt(dx * dx + dy * dy)
    if ln < 1e-9:
        return None
    f = min(1.0, max(MIN_POWER, power)) * IMPULSE_MAX * IMPULSE_MULT / ln
    return dx * f, dy * f


def _pass_done(res: dict) -> bool:
    """پاس کامل: شوت زننده و گیرندهٔ متفاوت (هر دو از تیم نوبت دار) و توپ تا ۲۳۶ واحد از گیرنده."""
    s, r = res["shooter"], res["receiver"]
    if s is None or r is None or s == r or res["goal"] is not None:
        return False
    bx, by = res["pos"][BALL]
    return math.hypot(res["pos"][r][0] - bx, res["pos"][r][1] - by) <= CONTROL_RADIUS


def shot(st: dict, i: int, k: int, dx: float, dy: float, power: float, now: float, auto: bool = False) -> str | None:
    if st["over"]:
        return "over"
    if st["phase"] != "play":
        return "not_play_phase"
    if st["turn"] != i:
        return "not_your_turn"
    if not auto and now < st["next_at"] - 0.3:
        return "not_ready"
    try:
        k, dx, dy, power = int(k), float(dx), float(dy), float(power)
    except (TypeError, ValueError):
        return "bad_shot"
    if k not in range(6) or not all(map(math.isfinite, (dx, dy, power))):
        return "bad_shot"
    imp = impulse(dx, dy, power)
    if imp is None:
        return "bad_shot"
    token = i * 6 + k
    lim = st["passes"]
    pass_ok = lim == 0 or st["chain"] < lim
    res = P.run_shot(st["pos"], token, imp[0], imp[1], i, pass_ok)
    for e in st["events"]:
        if e.get("t") in ("shot", "pass"):
            e.pop("frames", None)
    pos = _round_pos(res["pos"])
    st["stats"][SEATS[i]]["shots"] += 1
    kick_shot = st["new_ko"]
    g = res["goal"]
    _event(st, t="shot", c=SEATS[i], k=k, ids=res["ids"], frames=res["frames"], dur=res["dur"], pos=pos,
           hits=_hits(res["hits"]), goal=SEATS[g] if g is not None else None, auto=auto, kick=kick_shot)
    base = res["dur"] + SHOT_PAUSE
    if g is not None:
        return _goal(st, i, g, pos, kick_shot, base, now)
    st["new_ko"] = False
    passed = _pass_done(res)
    pos = _fix_ball(pos)
    moved = _remove_from_goal(pos, res["receiver"] if passed else None)
    if moved:
        _event(st, t="settle", ids=sorted(moved), pos=[pos[q] for q in sorted(moved)])
        base += 0.4
    st["pos"] = pos
    if passed:
        st["chain"] += 1
        st["stats"][SEATS[i]]["passes"] += 1
        ctl = P.run_control(pos, res["receiver"], i)
        pos = _round_pos(ctl["pos"]) if ctl["moved"] else pos
        st["pos"] = pos
        left = (st["passes"] - st["chain"]) if st["passes"] else None
        _event(st, t="pass", c=SEATS[i], d=res["receiver"], n=st["chain"], left=left, ids=ctl["ids"],
               frames=ctl["frames"], dur=ctl["dur"], pos=pos)
        _wait(st, now, base + ctl["dur"] + 0.5)
        return None
    st["chain"] = 0
    st["turn"] = other(i)
    _event(st, t="lose", c=SEATS[i], to=SEATS[st["turn"]])
    _wait(st, now, base)
    return None


def _round_pos(pos: list) -> list:
    return [[P.rd2(p[0]), P.rd2(p[1])] for p in pos]


def _hits(hits: list) -> list:
    """[زمان، نوع، شدت ۰..۱] برای صدا: b توپ، d مهره، w دیواره، p تیرک دروازه."""
    return [[h[0], h[1], round(min(1.0, h[2] / 2000.0) * 100.0) / 100.0] for h in hits[:24]]


def _goal(st: dict, i: int, g: int, pos: list, kick_shot: bool, base: float, now: float) -> str | None:
    s = st["stats"]
    foul = kick_shot            # گل از ضربهٔ شروع بازی خطاست
    if not foul:
        st["score"][g] += 1
        s[SEATS[g]]["goals"] += 1 if g == i else 0
    _event(st, t="goal", c=SEATS[g], by=SEATS[i], own=g != i, score=list(st["score"]), foul=foul)
    if not foul and st["score"][g] >= st["target"]:
        st["pos"] = pos
        _finish(st, g)
        return None
    st["chain"] = 0
    st["kick"] = other(i) if g == i else i
    st["turn"] = st["kick"]
    st["new_ko"] = True
    st["pos"] = kickoff_pos(st)
    _event(st, t="reset", pos=st["pos"], kick=SEATS[st["kick"]], foul=foul)
    _wait(st, now, base + GOAL_PAUSE)
    return None


def _fix_ball(pos: list) -> list:
    """توپ بیرون از زمین مانده (نباید پیش بیاید): وسط زمین بگذار."""
    bx, by = pos[BALL]
    if 0.0 < bx < W and 0.0 < by < H:
        return pos
    out = [p[:] for p in pos]
    out[BALL] = [W / 2, H / 2]
    return out


def _free_spot(pos: list, d: int, x: float, y: float) -> bool:
    r = radius_of(d)
    if x - r < 0 or x + r > W or y - r < 0 or y + r > H:
        return False
    if (x - r < P.BOX_W or x + r > W - P.BOX_W) and (y - r < GOAL_H or y + r > H - GOAL_H):
        return False
    for q in range(N):
        if q == d:
            continue
        rq = radius_of(q)
        if abs(pos[q][0] - x) < r + rq and abs(pos[q][1] - y) < r + rq:      # هم پوشانی کادر دور دایره (AABB)
            return False
    return True


def _remove_from_goal(pos: list, exempt: int | None) -> set:
    """مهره های غیر دروازه بان که ته دروازه مانده اند به بیرون خط دروازه می روند (removePlayersFromGoal)."""
    moved = set()
    for d in range(12):
        if d % 6 == 0 or d == exempt:
            continue
        y = pos[d][1]
        if d < 6:
            line, limit, e = H - GOAL_H, H - GOAL_H * 0.8, -1.0
            inside = y > limit
        else:
            line, limit, e = GOAL_H, GOAL_H * 0.8, 1.0
            inside = y < limit
        if not inside:
            continue
        r = radius_of(d)
        s = r * 0.1
        a = math.floor((W - r * 2) / s)
        px, py = pos[d][0], line + r * 1.1 * e
        u = 1.0 if px > W else -1.0
        h_cnt, l_cnt, c = 0, 0, 1000
        while not _free_spot(pos, d, px, py) and c > 0:
            if h_cnt < 6:
                h_cnt += 1
                py += s * e
            else:
                h_cnt = 0
                l_cnt += 1
                if l_cnt >= a:
                    l_cnt = 0
                else:
                    c -= 1
                    if (1000 - c) % a != 0:
                        py -= s * e * 6
                    px += s * u
                    if px < r:
                        px = W - r - 1
                    elif px > W - r:
                        px = r + 1
        pos[d] = [P.rd2(px), P.rd2(py)]
        moved.add(d)
    return moved


def _finish(st: dict, w: int | None) -> None:
    st["over"], st["winner"], st["phase"] = True, w, "over"
    _event(st, t="win" if w is not None else "end", c=SEATS[w] if w is not None else None, score=list(st["score"]))


def leave(st: dict, s: str, now: float, why: str = "left") -> None:
    """خروج یا جریمه غیبت در بازی امتیازی: حریف برنده است."""
    p = st["players"].get(s)
    if not p or p["out"] or st["over"]:
        return
    p["out"] = True
    _event(st, t="leave", c=s, why=why)
    _finish(st, other(int(s)))


# ---------- ربات ----------
def _goal_of(i: int) -> tuple[float, float]:
    """مرکز دروازه ای که صندلی i به آن حمله می کند."""
    return (W / 2, 0.0) if i == 0 else (W / 2, H)


def _rate_of(k: int) -> float:
    """چند واحد زمین به ازای هر واحد قدرت (کشیدن) مهره بدون برخورد می رود."""
    return 4.54 if k % 6 == 0 else 6.8


def _rate(st: dict, i: int, res: dict) -> float:
    g = res["goal"]
    if g is not None:
        if st["new_ko"]:
            return -400.0
        return 100000.0 if g == i else -100000.0
    pos = res["pos"]
    bx, by = pos[BALL]
    passed = _pass_done(res)
    gx, gy = _goal_of(i)
    ox, oy = _goal_of(other(i))
    near = -math.hypot(bx - gx, by - gy)
    danger = min(math.hypot(bx - ox, by - oy), 900.0)
    v = near * 0.7 + danger * 0.5
    if passed:
        v += 420.0 + (300.0 if math.hypot(bx - gx, by - gy) < 700 else 0.0)
    mine = min(math.hypot(pos[q][0] - bx, pos[q][1] - by) for q in range(i * 6, i * 6 + 6))
    theirs = min(math.hypot(pos[q][0] - bx, pos[q][1] - by) for q in range((1 - i) * 6, (1 - i) * 6 + 6))
    v += (min(theirs, 500.0) - min(mine, 500.0)) * 0.25
    return v


def _cands(st: dict, i: int) -> list:
    """شوت های امتحانی: پشت توپ به سمت دروازه، ضربهٔ مستقیم به توپ، پاس به یار."""
    pos = st["pos"]
    bx, by = pos[BALL]
    gx, gy = _goal_of(i)
    ux, uy = gx - bx, gy - by
    ul = math.hypot(ux, uy) or 1.0
    ux, uy = ux / ul, uy / ul
    out = []
    for k in range(6):
        d = i * 6 + k
        tx, ty = pos[d]
        rk = radius_of(d)
        gxp, gyp = bx - ux * (rk + BALL_R - 3.0), by - uy * (rk + BALL_R - 3.0)
        ax, ay = gxp - tx, gyp - ty
        dist = math.hypot(ax, ay) or 1.0
        align = (ax / dist) * ux + (ay / dist) * uy
        out.append((align * 600.0 - dist * 0.2, k, ax / dist, ay / dist, min(1.0, (dist + 90.0) / _rate_of(k) / IMPULSE_MAX)))
        cx, cy = bx - tx, by - ty
        cd = math.hypot(cx, cy) or 1.0
        out.append((align * 200.0 - cd * 0.2, k, cx / cd, cy / cd, min(1.0, (cd + 150.0) / _rate_of(k) / IMPULSE_MAX)))
        for j in range(6):
            if j == k:
                continue
            mx, my = pos[i * 6 + j]
            pxv, pyv = mx - bx, my - by
            pl = math.hypot(pxv, pyv) or 1.0
            if pl < 160:
                continue
            gx2, gy2 = bx - pxv / pl * (rk + BALL_R - 3.0), by - pyv / pl * (rk + BALL_R - 3.0)
            ax, ay = gx2 - tx, gy2 - ty
            dist = math.hypot(ax, ay) or 1.0
            line = (ax / dist) * (pxv / pl) + (ay / dist) * (pyv / pl)
            if line < 0.3:
                continue
            out.append((line * 350.0 + 120.0 - dist * 0.2, k, ax / dist, ay / dist,
                        min(1.0, (dist + pl * 0.5) / _rate_of(k) / IMPULSE_MAX)))
    out.sort(reverse=True)
    return out


def bot_shot(st: dict, i: int) -> tuple[int, float, float, float]:
    cands = _cands(st, i)[:7]
    lim = st["passes"]
    pass_ok = lim == 0 or st["chain"] < lim
    best, best_v = None, -1e18
    for _, k, ax, ay, power in cands:
        a = (_rng.random() - 0.5) * 0.05
        ca, sa = math.cos(a), math.sin(a)
        dx, dy = ax * ca - ay * sa, ax * sa + ay * ca
        pw = min(1.0, max(0.12, power * (0.95 + _rng.random() * 0.1)))
        imp = impulse(dx, dy, pw)
        res = P.run_shot(st["pos"], i * 6 + k, imp[0], imp[1], i, pass_ok)
        v = _rate(st, i, res) + _rng.random() * 25
        if v > best_v:
            best, best_v = (k, dx, dy, pw), v
    return best


def tick(st: dict, now: float) -> bool:
    changed = False
    for _ in range(4):
        if st["over"]:
            break
        if st["phase"] == "setup":
            if now < st["next_at"]:
                break
            _start(st, now)
            changed = True
            continue
        i = st["turn"]
        s = SEATS[i]
        p = st["players"][s]
        if _auto(st, i):
            if now < st["next_at"]:
                break
            k, dx, dy, power = bot_shot(st, i)
            shot(st, i, k, dx, dy, power, now, auto=True)
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
        st["turn"] = other(i)
        st["chain"] = 0
        _event(st, t="lose", c=s, to=SEATS[st["turn"]], miss=True)
        _wait(st, now, SHOT_PAUSE)
    return changed


def human_acted(st: dict, s: str) -> None:
    st["players"][s]["misses"] = 0


def winners(st: dict) -> set[str]:
    return {SEATS[st["winner"]]} if st.get("winner") is not None else set()


# ---------- نمای هر بازیکن ----------
def view(st: dict, me: str | None, since: int, now: float) -> dict:
    ph = st["phase"]
    cur = current(st)
    auto = cur is not None and _auto(st, int(cur))
    return {
        "order": list(SEATS),
        "players": {s: {"name": p["name"], "av": p["av"], "pic": p.get("pic", ""), "bot": p["bot"], "out": p["out"],
                        "me": s == me, "team": p["team"], "kit": p["kit"], "ready": p["ready"],
                        **({"fa": p["fa"], "fd": p["fd"]} if s == me else {})}
                    for s, p in st["players"].items()},
        "me": me,
        "phase": ph,
        "turn": cur,
        "kick": SEATS[st["kick"]],
        "pos": st["pos"],
        "score": st["score"],
        "target": st["target"],
        "passes": st["passes"],
        "chain": st["chain"],
        "kickoff": st["new_ko"],
        "setup_ms": max(0, int((st["next_at"] - now) * 1000)) if ph == "setup" else 0,
        "ready_ms": max(0, int((st["next_at"] - now) * 1000)) if cur is not None else 0,
        "deadline_ms": 0 if (cur is None or auto) else max(0, int((st["deadline"] - now) * 1000)),
        "turn_ms": int(turn_time(st["turn_s"], st["chain"], st["players"][SEATS[st["turn"]]]["misses"]) * 1000),
        "events": [e for e in st["events"] if e["seq"] > since],
        "seq": st["seq"],
        "over": st["over"],
        "winner": SEATS[st["winner"]] if st["winner"] is not None else None,
        "stats": st["stats"].get(me) if me else None,
        "started": st["started"],
    }
