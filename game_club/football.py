"""فوتبال دو نفره (مهره ای، نوبتی)؛ فقط سمت سرور.

مثل منچ و حکم: هیچ I/O ندارد، وضعیت یک dict ساده است که به JSON ذخیره می شود،
هر اتفاق یک رویداد شماره دار می سازد و ربات و نوبت های بی جواب فقط داخل tick
جلو می روند.

قواعد:
- هر بازیکن شش مهره دارد (یک دروازه بان، پنج بازیکن)؛ صندلی ۰ از دروازه پایین
  دفاع می کند و به بالا حمله می کند، صندلی ۱ برعکس
- اول بازی هر کس تیم و چیدمان حمله و دفاعش را انتخاب می کند (SETUP_S ثانیه)
- در نوبتت یکی از مهره هایت را با جهت و قدرت دلخواه شوت می کنی. فیزیک برخورد
  مهره ها، توپ و دیواره ها همین جا حساب می شود و مسیر حرکت (فریم ها) برای
  نمایش به مینی اپ می رود
- گل: توپ کامل از خط دروازه بگذرد. بعد از گل همه سر جایشان برمی گردند و تیمی
  که گل خورده شروع می کند
- اولین کسی که به تعداد گل هدف (۳ یا ۵) برسد برنده است؛ خروج یعنی باخت

مختصات دنیا: زمین W در H، مبدا گوشه بالا چپ؛ مهره های صندلی ۰ شماره ۰ تا ۵،
صندلی ۱ شماره ۶ تا ۱۱ و توپ شماره ۱۲.
فقط + - * / و sqrt در فیزیک به کار رفته تا نسخه جاوااسکریپت (demo-football.js)
همان نتیجه را بدهد.
"""
from __future__ import annotations

import math
import random

SEATS = ("0", "1")
W, H = 600.0, 1040.0
MID = H / 2
GOAL_W, GOAL_D = 220.0, 60.0
GX0, GX1 = (W - GOAL_W) / 2, (W + GOAL_W) / 2
DISC_R, BALL_R = 36.0, 18.0
DISC_M, BALL_M = 1.0, 0.55      # مهره سنگین؛ توپ سبک تر ولی نه پَر
BALL = 12
N = 13
VMAX = 2200.0            # سرعت مهره با بیشترین قدرت (واحد بر ثانیه)
MIN_POWER = 0.06
DT = 1 / 120
FRAME_EVERY = 4          # ۳۰ فریم در ثانیه برای نمایش
MAX_SIM = 9.0
AFTER_GOAL = 0.5         # توپ بعد از گل کمی در تور می چرخد
# مهره ها وزن دارند: اصطکاک ثابت زیاد، پس کم سُر می خورند و قاطع می ایستند؛ توپ بیشتر می غلتد
DRAG = (0.9, 1.3)        # (مهره، توپ) کاهش سرعت متناسب با سرعت
FRIC = (360.0, 280.0)    # کاهش سرعت ثابت («جاذبه»: هر دو روی چمن می نشینند و زود آرام می شوند)
BALL_VMAX = 1200.0       # توپ هر چقدر هم محکم زده شود از این تندتر نمی رود
BALL_SLIDE, SLIDE_V = 0.9, 700.0  # توپ تند اول روی چمن «سُر» می خورد (اصطکاک بیشتر) و بعد نرم می غلتد
MU_PAIR = 0.12           # اصطکاک لحظه برخورد: بخشی از سرعت کناری دو جسم گرفته می شود
MU_WALL = (0.15, 0.08)   # اصطکاک کناری دیواره (مهره، توپ)
MAX_PASS = 3             # پاس پشت سرهم که نوبت اضافه می دهد
HOLD_GAP = DISC_R + BALL_R + 1.0  # فاصله مرکز توپ چسبیده تا مرکز مهره
E_PAIR, E_BALL_DISC, E_DISC_WALL, E_BALL_WALL = 0.82, 0.68, 0.5, 0.65
STOP = 4.0

SETUP_S = 20.0           # انتخاب تیم و چیدمان
INTRO = 3.4              # نمایش «مقابل» قبل از شروع
SHOT_PAUSE = 0.35
GOAL_PAUSE = 3.6         # جشن گل و برگشت مهره ها
BOT_THINK = 1.1
TURN_S = 15
MAX_EVENTS = 40

TEAMS = ("eagles", "lions", "cheetahs", "mountain", "storm", "sea")
FORMS = ("132", "123", "141", "1212")
# (x، فاصله از خط دروازه خودی)؛ اولی دروازه بان
ATK = {
    "132": ((300, 42), (110, 230), (300, 210), (490, 230), (220, 400), (380, 400)),
    "123": ((300, 42), (200, 220), (400, 220), (110, 410), (300, 430), (490, 410)),
    "141": ((300, 42), (90, 280), (230, 250), (370, 250), (510, 280), (300, 430)),
    "1212": ((300, 42), (200, 200), (400, 200), (300, 320), (210, 430), (390, 430)),
}
DEF = {
    "132": ((300, 42), (120, 190), (300, 160), (480, 190), (210, 300), (390, 300)),
    "123": ((300, 42), (210, 160), (390, 160), (110, 300), (300, 320), (490, 300)),
    "141": ((300, 42), (90, 180), (230, 160), (370, 160), (510, 180), (300, 320)),
    "1212": ((300, 42), (210, 150), (390, 150), (300, 240), (200, 340), (400, 340)),
}

# دیواره ها: پاره خط ها؛ دو سرشان مثل تیرک گرد رفتار می کنند
SEGS = (
    ((0.0, 0.0), (GX0, 0.0)), ((GX1, 0.0), (W, 0.0)),
    ((GX0, 0.0), (GX0, -GOAL_D)), ((GX0, -GOAL_D), (GX1, -GOAL_D)), ((GX1, -GOAL_D), (GX1, 0.0)),
    ((0.0, H), (GX0, H)), ((GX1, H), (W, H)),
    ((GX0, H), (GX0, H + GOAL_D)), ((GX0, H + GOAL_D), (GX1, H + GOAL_D)), ((GX1, H + GOAL_D), (GX1, H)),
    ((0.0, 0.0), (0.0, H)), ((W, 0.0), (W, H)),
)

_rng = random.SystemRandom()


def other(i: int) -> int:
    return 1 - i


# ---------- فیزیک ----------
def simulate(pos: list, vel: dict) -> dict:
    """pos: سیزده [x, y]؛ vel: {شماره: (vx, vy)}. نتیجه: پایان، فریم ها، گل."""
    x = [float(p[0]) for p in pos]
    y = [float(p[1]) for p in pos]
    vx, vy = [0.0] * N, [0.0] * N
    r = [DISC_R] * 12 + [BALL_R]
    m = [DISC_M] * 12 + [BALL_M]
    kind = [0] * 12 + [1]
    moving = set()
    for i, (a, b) in vel.items():
        vx[i], vy[i] = float(a), float(b)
        moving.add(i)
    moved = set(moving)
    frames = [[x[:], y[:]]]
    goal, after, t, step = None, 0.0, 0.0, 0
    hits = []   # [زمان، نوع، شدت] برای صدا: b توپ، d مهره، w دیواره، p تیرک دروازه
    touch = []  # مهره هایی که توپ (تندتر از خودشان) به آن ها خورده، به ترتیب: برای تشخیص پاس
    while moving and t < MAX_SIM:
        step += 1
        t += DT
        for i in moving:
            x[i] += vx[i] * DT
            y[i] += vy[i] * DT
        # برخورد دو به دو (هر جفت یک بار)
        # ترتیب ثابت (مرتب) تا نسخه جاوااسکریپت دقیقا همین نتیجه را بدهد
        for i in sorted(moving):
            for j in range(N):
                if j == i or (j in moving and j < i):
                    continue
                rr = r[i] + r[j]
                dx, dy = x[j] - x[i], y[j] - y[i]
                if dx > rr or dx < -rr or dy > rr or dy < -rr:
                    continue
                d2 = dx * dx + dy * dy
                if d2 >= rr * rr or d2 == 0.0:
                    continue
                d = math.sqrt(d2)
                nx, ny = dx / d, dy / d
                rel = (vx[j] - vx[i]) * nx + (vy[j] - vy[i]) * ny
                inv = 1 / m[i] + 1 / m[j]
                if rel < 0:
                    if rel < -120 and len(hits) < 24:
                        hits.append([round(t, 2), "b" if BALL in (i, j) else "d", round(min(1.0, -rel / 2000), 2)])
                    if BALL in (i, j):
                        o = j if i == BALL else i
                        if vx[BALL] * vx[BALL] + vy[BALL] * vy[BALL] > vx[o] * vx[o] + vy[o] * vy[o] and o not in touch:
                            touch.append(o)
                    imp = -(1 + (E_BALL_DISC if BALL in (i, j) else E_PAIR)) * rel / inv
                    vx[i] -= imp / m[i] * nx
                    vy[i] -= imp / m[i] * ny
                    vx[j] += imp / m[j] * nx
                    vy[j] += imp / m[j] * ny
                    tx, ty = -ny, nx
                    vt = (vx[j] - vx[i]) * tx + (vy[j] - vy[i]) * ty
                    jt = -MU_PAIR * vt / inv
                    vx[i] -= jt / m[i] * tx
                    vy[i] -= jt / m[i] * ty
                    vx[j] += jt / m[j] * tx
                    vy[j] += jt / m[j] * ty
                over = rr - d
                ki, kj = (1 / m[i]) / inv, (1 / m[j]) / inv
                x[i] -= nx * over * ki
                y[i] -= ny * over * ki
                x[j] += nx * over * kj
                y[j] += ny * over * kj
                moving.add(j)
                moved.add(j)
        if BALL in moving:
            sp2 = vx[BALL] * vx[BALL] + vy[BALL] * vy[BALL]
            if sp2 > BALL_VMAX * BALL_VMAX:
                f = BALL_VMAX / math.sqrt(sp2)
                vx[BALL] *= f
                vy[BALL] *= f
        # دیواره ها و تیرک ها
        for i in moving:
            e = E_BALL_WALL if kind[i] else E_DISC_WALL
            for (ax, ay), (bx, by) in SEGS:
                ex, ey = bx - ax, by - ay
                ll = ex * ex + ey * ey
                u = ((x[i] - ax) * ex + (y[i] - ay) * ey) / ll
                u = 0.0 if u < 0 else 1.0 if u > 1 else u
                qx, qy = ax + ex * u, ay + ey * u
                dx, dy = x[i] - qx, y[i] - qy
                if dx > r[i] or dx < -r[i] or dy > r[i] or dy < -r[i]:
                    continue
                d2 = dx * dx + dy * dy
                if d2 >= r[i] * r[i] or d2 == 0.0:
                    continue
                d = math.sqrt(d2)
                nx, ny = dx / d, dy / d
                vn = vx[i] * nx + vy[i] * ny
                if vn < 0:
                    if vn < -150 and len(hits) < 24:
                        post = (u == 0.0 or u == 1.0) and (abs(qx - GX0) < 1 or abs(qx - GX1) < 1) and \
                            (abs(qy) < 1 or abs(qy - H) < 1)
                        hits.append([round(t, 2), "p" if post else "w", round(min(1.0, -vn / 2000), 2)])
                    vx[i] -= (1 + e) * vn * nx
                    vy[i] -= (1 + e) * vn * ny
                    vt = vx[i] * -ny + vy[i] * nx
                    vx[i] -= MU_WALL[kind[i]] * vt * -ny
                    vy[i] -= MU_WALL[kind[i]] * vt * nx
                x[i] += nx * (r[i] - d)
                y[i] += ny * (r[i] - d)
        # اصطکاک
        for i in sorted(moving):
            sp = math.sqrt(vx[i] * vx[i] + vy[i] * vy[i])
            k = kind[i]
            dg = DRAG[k] + (BALL_SLIDE if k == 1 and sp > SLIDE_V else 0.0)
            ns = sp - (dg * sp + FRIC[k]) * DT
            if ns <= STOP:
                vx[i] = vy[i] = 0.0
                moving.discard(i)
            else:
                f = ns / sp
                vx[i] *= f
                vy[i] *= f
        if goal is None:
            if y[BALL] < -BALL_R:
                goal = 0          # صندلی ۰ به بالا حمله می کند
            elif y[BALL] > H + BALL_R:
                goal = 1
        else:
            after += DT
            if after >= AFTER_GOAL:
                break
        if step % FRAME_EVERY == 0:
            frames.append([x[:], y[:]])
    frames.append([x[:], y[:]])
    ids = sorted(moved)
    out_frames = [[v for i in ids for v in (round(f[0][i]), round(f[1][i]))] for f in frames]
    return {"pos": [[round(x[i], 1), round(y[i], 1)] for i in range(N)], "ids": ids, "frames": out_frames,
            "dur": round(len(frames) / (1 / (DT * FRAME_EVERY)), 2), "goal": goal, "hits": hits, "touch": touch}


def pass_of(i: int, disc: int, res: dict) -> int | None:
    """پاس: توپ بعد از شوت به یکی دیگر از مهره های خودی خورده باشد (نه خود شوت زننده)."""
    return next((d for d in res["touch"] if i * 6 <= d < i * 6 + 6 and d != disc), None)


# جهت های امتحانی برای جای توپ بعد از پاس، نسبت به رو به جلو (صاف، بعد کم کم کج تر)
_C30, _S30 = 0.8660254037844386, 0.5
CATCH_DIRS = ((0.0, -1.0), (_S30, -_C30), (-_S30, -_C30), (_C30, -_S30), (-_C30, -_S30), (1.0, 0.0), (-1.0, 0.0),
              (_C30, _S30), (-_C30, _S30), (0.0, 1.0))


def catch_pos(pos: list, i: int, d: int) -> list | None:
    """پاس مثل آهنربا: توپ به مهره d می چسبد، درست جلوی آن رو به دروازه حریف (برای صاحبش صاف بالای مهره).
    اگر جلویش جا نبود (دیواره یا مهره دیگر)، کمی کج تر؛ اگر هیچ جا نبود None."""
    cx, cy = pos[d]
    sg = 1.0 if i == 0 else -1.0     # صندلی ۰ رو به بالا حمله می کند، صندلی ۱ رو به پایین
    for fx, fy in CATCH_DIRS:
        bx, by = cx + fx * sg * HOLD_GAP, cy + fy * sg * HOLD_GAP
        if _free(pos, d, bx, by):
            return [round(bx, 1), round(by, 1)]
    return None


def _free(pos: list, d: int, bx: float, by: float) -> bool:
    """جای توپ کنار مهره d آزاد است: داخل زمین و روی هیچ مهره دیگری نیست."""
    if bx < BALL_R or bx > W - BALL_R or by < BALL_R or by > H - BALL_R:
        return False
    lim = (DISC_R + BALL_R + 0.5) * (DISC_R + BALL_R + 0.5)
    for j in range(12):
        if j != d:
            dx, dy = pos[j][0] - bx, pos[j][1] - by
            if dx * dx + dy * dy < lim:
                return False
    return True


def hold_pos(pos: list, d: int, dx: float, dy: float) -> list:
    """مهره ای که توپ را گرفته شوت می زند: اول زیر توپ می آید، یعنی توپ درست جلویش در جهت
    شوت قرار می گیرد (اگر آنجا جا باشد) و بعد شوت حساب می شود. pos تازه برمی گردد."""
    ln = math.sqrt(dx * dx + dy * dy)
    bx, by = pos[d][0] + dx / ln * HOLD_GAP, pos[d][1] + dy / ln * HOLD_GAP
    if not _free(pos, d, bx, by):
        return pos
    out = [p[:] for p in pos]
    out[BALL] = [bx, by]
    return out


def formation(seat: int, form: str, attack: bool) -> list:
    pts = (ATK if attack else DEF).get(form) or ATK["132"]
    if seat == 0:
        return [[float(px), H - d] for px, d in pts]
    return [[W - px, float(d)] for px, d in pts]


def kickoff_pos(st: dict) -> list:
    k = st["kick"]
    pos = []
    for i, s in enumerate(SEATS):
        p = st["players"][s]
        pos += formation(i, p["fa"] if i == k else p["fd"], i == k)
    return pos + [[W / 2, MID]]


# ---------- ساخت ----------
def new_state(seats: list[dict], now: float, turn_s: int, stake: bool, target: int, first: int | None = None) -> dict:
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
        "game": "football", "order": list(SEATS), "players": players, "target": target, "score": [0, 0],
        "phase": "setup", "turn": 0, "kick": first if first in (0, 1) else _rng.randrange(2),
        "pos": [], "next_at": now + SETUP_S, "deadline": now + SETUP_S, "turn_s": min(int(turn_s), TURN_S),
        "stake": stake, "events": [], "seq": 0, "turn_id": 0, "winner": None, "over": False, "started": now,
        "stats": {s: {"shots": 0, "goals": 0, "passes": 0} for s in SEATS}, "streak": 0,
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
    if _auto(st, st["turn"]):
        delay += BOT_THINK
    st["turn_id"] = st["seq"]
    st["next_at"] = now + delay
    st["deadline"] = now + delay + st["turn_s"]


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
    st["phase"], st["turn"] = "play", st["kick"]
    st["pos"] = kickoff_pos(st)
    _event(st, t="start", teams={s: {"team": p["team"], "kit": p["kit"]} for s, p in st["players"].items()},
           pos=st["pos"], kick=SEATS[st["kick"]])
    _wait(st, now, INTRO)


# ---------- شوت ----------
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
    ln = math.sqrt(dx * dx + dy * dy)
    if ln < 1e-6:
        return "bad_shot"
    power = min(1.0, max(MIN_POWER, power))
    v = VMAX * power / ln
    disc = i * 6 + k
    pos0 = hold_pos(st["pos"], disc, dx, dy) if st.get("hold") == disc else st["pos"]
    held = [round(pos0[BALL][0], 1), round(pos0[BALL][1], 1)] if pos0 is not st["pos"] else None
    st["hold"] = None
    res = simulate(pos0, {disc: (dx * v, dy * v)})
    for e in st["events"]:
        if e.get("t") == "shot":
            e.pop("frames", None)
    st["pos"] = res["pos"]
    st["stats"][SEATS[i]]["shots"] += 1
    g = res["goal"]
    pas = pass_of(i, disc, res) if g is None else None
    _event(st, t="shot", c=SEATS[i], k=k, ids=res["ids"], frames=res["frames"], dur=res["dur"], pos=res["pos"], hits=res["hits"],
           goal=SEATS[g] if g is not None else None, auto=auto, hold=held)
    if g is None:
        if pas is not None and st.get("streak", 0) < MAX_PASS:
            # پاس به یار: نوبت دوباره مال همین بازیکن است
            st["streak"] = st.get("streak", 0) + 1
            st["stats"][SEATS[i]]["passes"] = st["stats"][SEATS[i]].get("passes", 0) + 1
            ball = catch_pos(st["pos"], i, pas)
            if ball is not None:
                st["pos"] = [p[:] for p in st["pos"]]    # pos رویداد شوت (همان فهرست) دست نخورد
                st["pos"][BALL] = ball
                st["hold"] = pas                         # این مهره توپ را دارد تا شوت بعدی
            _event(st, t="pass", c=SEATS[i], d=pas, n=st["streak"], left=MAX_PASS - st["streak"], ball=st["pos"][BALL])
        else:
            st["streak"] = 0
            st["turn"] = other(i)
        _wait(st, now, res["dur"] + SHOT_PAUSE)
        return None
    st["streak"] = 0
    st["score"][g] += 1
    st["stats"][SEATS[g]]["goals"] += 1 if g == i else 0
    _event(st, t="goal", c=SEATS[g], by=SEATS[i], own=g != i, score=list(st["score"]))
    if st["score"][g] >= st["target"]:
        _finish(st, g)
        return None
    st["kick"] = other(g)
    st["turn"] = st["kick"]
    st["pos"] = kickoff_pos(st)
    _event(st, t="reset", pos=st["pos"], kick=SEATS[st["kick"]])
    _wait(st, now, res["dur"] + GOAL_PAUSE)
    return None


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
    return (W / 2, -GOAL_D / 2) if i == 0 else (W / 2, H + GOAL_D / 2)


def _rate(st: dict, i: int, res: dict, disc: int = -1) -> float:
    if res["goal"] is not None:
        return 1000.0 if res["goal"] == i else -2000.0
    pas = pass_of(i, disc, res) if st.get("streak", 0) < MAX_PASS else None
    bonus = 160.0 if pas is not None else 0.0
    bx, by = (catch_pos(res["pos"], i, pas) if pas is not None else None) or res["pos"][BALL]
    gx, gy = _goal_of(i)
    near = -math.sqrt((bx - gx) ** 2 + (by - gy) ** 2)       # توپ نزدیک دروازه حریف بهتر
    ox, oy = _goal_of(other(i))
    danger = math.sqrt((bx - ox) ** 2 + (by - oy) ** 2)       # و دور از دروازه خودی
    return near * 0.6 + min(danger, 500) * 0.4 + bonus


def bot_shot(st: dict, i: int) -> tuple[int, float, float, float]:
    pos = st["pos"]
    bx, by = pos[BALL]
    gx, gy = _goal_of(i)
    gl = math.sqrt((gx - bx) ** 2 + (gy - by) ** 2) or 1.0
    ux, uy = (gx - bx) / gl, (gy - by) / gl
    cands = []
    for k in range(6):
        dx0, dy0 = pos[i * 6 + k]
        # جای برخورد: پشت توپ، در امتداد خط توپ تا دروازه
        cx, cy = bx - ux * (DISC_R + BALL_R) * 0.9, by - uy * (DISC_R + BALL_R) * 0.9
        ax, ay = cx - dx0, cy - dy0
        dist = math.sqrt(ax * ax + ay * ay) or 1.0
        ax, ay = ax / dist, ay / dist
        align = ax * ux + ay * uy
        if align < 0.15:   # پشت توپ نیست: مستقیم به توپ بزن تا دور شود
            ax, ay = bx - dx0, by - dy0
            dist = math.sqrt(ax * ax + ay * ay) or 1.0
            ax, ay = ax / dist, ay / dist
        power = min(1.0, max(0.5, 0.42 + dist / 1250))
        if st.get("hold") == i * 6 + k:
            # توپ دست این مهره است: مستقیم رو به دروازه، محکم
            ax, ay = gx - dx0, gy - dy0
            dist = math.sqrt(ax * ax + ay * ay) or 1.0
            ax, ay, align, power = ax / dist, ay / dist, 1.5, 0.9
        cands.append((align * 2 - dist / 900, k, ax, ay, power))
    cands.sort(reverse=True)
    best, best_v = None, -1e9
    for _, k, ax, ay, power in cands[:4]:
        a = (_rng.random() - 0.5) * 0.09
        ca, sa = math.cos(a), math.sin(a)
        dx, dy = ax * ca - ay * sa, ax * sa + ay * ca
        p0 = hold_pos(pos, i * 6 + k, dx, dy) if st.get("hold") == i * 6 + k else pos
        res = simulate(p0, {i * 6 + k: (dx * VMAX * power, dy * VMAX * power)})
        v = _rate(st, i, res, i * 6 + k) + _rng.random() * 30
        if v > best_v:
            best, best_v = (k, dx, dy, power), v
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
        st["streak"] = 0
        st["hold"] = None
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
        "setup_ms": max(0, int((st["next_at"] - now) * 1000)) if ph == "setup" else 0,
        "ready_ms": max(0, int((st["next_at"] - now) * 1000)) if cur is not None else 0,
        "deadline_ms": 0 if (cur is None or auto) else max(0, int((st["deadline"] - now) * 1000)),
        "turn_ms": st["turn_s"] * 1000,
        "events": [e for e in st["events"] if e["seq"] > since],
        "seq": st["seq"],
        "over": st["over"],
        "winner": SEATS[st["winner"]] if st["winner"] is not None else None,
        "stats": st["stats"].get(me) if me else None,
        "streak": st.get("streak", 0), "hold": st.get("hold"),
        "started": st["started"],
    }
