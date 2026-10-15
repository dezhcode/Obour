"""بیلیارد ۸ توپ دو نفره یا چهار نفره (یاری)؛ فقط سمت سرور.

مثل فوتبال و حکم: هیچ I/O ندارد، وضعیت یک dict ساده است که به JSON ذخیره می شود،
هر اتفاق یک رویداد شماره دار می سازد و ربات و نوبت های بی جواب فقط داخل tick جلو
می روند. فیزیک هر ضربه همین جا حساب می شود و مسیر توپ ها (فریم های ۳۰ در ثانیه)،
برخوردها (برای صدا) و افتادن توپ ها برای نمایش به مینی اپ می رود؛ مینی اپ فقط
جهت، قدرت، پیچ (انگلیش) و جای توپ سفید را می فرستد.

قواعد (۸ توپ):
- صندلی ها به ترتیب نوبت؛ در چهار نفره ۰ و ۲ یک تیم و ۱ و ۳ تیم دیگرند (مثل حکم:
  اولین مهمان میز دعوت یار سازنده می شود) و نوبت یکی در میان بین دو تیم می چرخد
- بریک: توپ سفید پشت خط سر؛ اگر ۸ در بریک بیفتد یا کمتر از ۴ توپ به ریل بخورد
  (و هیچ توپی نیفتد) دوباره چیده می شود و همان بازیکن دوباره بریک می زند
- میز باز تا اولین توپی که بعد از بریک قانونی بیفتد؛ گروه آن (تک رنگ ۱ تا ۷ یا
  راه راه ۹ تا ۱۵) مال تیم زننده می شود
- خطا = حریف «توپ در دست» دارد: اول به توپ اشتباه (یا ۸ پیش از وقتش) خوردن، به
  هیچ توپی نخوردن، افتادن توپ سفید، یا اینکه بعد از برخورد هیچ توپی به ریل نخورد
- توپ خودت بیفتد و خطا نکنی = نوبت دوباره مال توست
- ۸ را بعد از پاک کردن گروهت و بدون خطا بیندازی برده ای؛ زودتر یا با خطا = باخت

فیزیک: بازنویسی مستقل با عددهای بازی پلاتو (ابعاد میز، کوشن ها، دهانه جیب ها،
میراسازی جهت دار، مواد برخورد، ضربه و پیچ). مختصات: میز ۸۳۴ در ۱۵۱۶، مبدا گوشه
بالا چپ، توپ شعاع ۲۰؛ بریک از پایین میز به سمت راک بالا.
"""
from __future__ import annotations

import math
import random

# ---------- ثابت های میز (واحد میز) ----------
W, H = 834.0, 1516.0
R = 20.0
D = 2 * R
HEAD = 1099.0                         # خط سر؛ در بریک مرکز توپ سفید پایین تر از HEAD + R
MIN_X, MAX_X, MIN_Y, MAX_Y = 97.0, 737.0, 97.0, 1419.0
BREAK_MIN_Y = HEAD + R
CUE_START = (W / 2 - 5, HEAD + R)
FOOT = (W - 418.0, H / 2)             # نقطهٔ برگرداندن توپ بیرون پریده

# میراسازی جهت دار (محور غالب ۰٫۹۴، محور دیگر ۰٫۴۱)
DAMP, ANG_DAMP = 0.625, 0.625
D_AXIS, D_CROSS, D_CLAMP, D_DIV = 0.94, 0.41, 1650.0, 3500.0
# مواد برخورد: (اصطکاک، ضریب بازگشت)
MAT_BALL, MAT_RAIL, MAT_MOUTH = (0.0, 0.99), (0.1, 0.95), (0.8, 0.2)
MASS, INV_I = 1.0, 1.0 / (1.0 * R * R)
# گام زمانی: (گام ثابت، تکرار حل کننده)
STEP_SHOT, STEP_BREAK = (0.01111, 10), (0.0093, 2)
DC = 1 / 120
# ضربه و پیچ
IMPULSE, SPIN_ANG, SPIN_MAX = 2375.0, 250.0, math.radians(30)
MIN_POWER, BREAK_MIN = 0.02, 0.35
BREAK_BONUS, BREAK_RAND, BREAK_JIT = 1.25, 0.15, math.radians(0.3)
SPIN_K, SPIN_DAMP, SPIN_DAMP_HIT, SPIN_GAIN = 0.003, 0.99, 0.97, 10.0
# جیب ها
POCKET_MAX_V, POCKET_FORCE, SENSOR = 550.0, 3.8, 0.49
SINK_TIME, SINK_PULL, SINK_DRAG = 0.55, 60.0, 5.0
SLEEP_V, SLEEP_T = 10.0, 0.2
MAX_SIM = 25.0
FPS = 30

# جیب: (x، y، شعاع، مرکز سوراخ x، y)؛ ترتیب: ۴ گوشه، ۲ وسط
POCKETS = (
    (49.0, 47.0, 70.0, 63.0, 63.0), (W - 49, 47.0, 70.0, W - 63, 63.0),
    (49.0, H - 47, 70.0, 63.0, H - 63), (W - 49, H - 47, 70.0, W - 63, H - 63),
    (21.0, H / 2, 60.0, 50.0, H / 2), (W - 21, H / 2, 60.0, W - 50, H / 2),
)

# کوشن ها (شش چندضلعی با فک مورب کنار هر جیب) و دیوارهٔ داخلی جیب ها؛ (pos، path)
_RAILS = (
    ((0, 116), ((0, 0), (60, 0), (76, 15), (76, 598), (65, 602), (0, 602))),
    ((0, 798), ((0, 0), (65, 0), (76, 4), (76, 587), (60, 602), (0, 602))),
    ((773, 116), ((0, 0), (60, 0), (60, 602), (-5, 602), (-16, 598), (-16, 15))),
    ((777, 798), ((0, 0), (56, 0), (56, 602), (-4, 602), (-20, 587), (-20, 4))),
    ((116, 0), ((0, 0), (599, 0), (599, 61), (585, 77), (14, 77), (0, 61))),
    ((130, 1438), ((0, 0), (571, 0), (585, 16), (585, 77), (-14, 77), (-14, 16))),
)
_MOUTHS = (
    ((0, 0), ((0, 0), (115, 0), (115, 58), (101, 43), (93, 35), (88, 32), (82, 28), (72, 25), (57, 24), (47, 28),
              (38, 33), (28, 45), (25, 51), (24, 56), (24, 71), (27, 80), (35, 91), (58, 114), (58, 116), (0, 116))),
    ((833, 0), ((0, 0), (0, 116), (-58, 116), (-58, 114), (-35, 91), (-27, 80), (-24, 71), (-24, 56), (-25, 51),
                (-28, 45), (-38, 33), (-47, 28), (-57, 24), (-72, 25), (-82, 28), (-88, 32), (-93, 35), (-101, 43),
                (-115, 58), (-115, 0))),
    ((0, 1515), ((0, 0), (0, -116), (58, -116), (58, -114), (35, -91), (27, -80), (24, -71), (24, -56), (25, -51),
                 (28, -45), (38, -33), (47, -28), (57, -24), (72, -25), (82, -28), (88, -32), (93, -35), (101, -43),
                 (115, -58), (115, 0))),
    ((833, 1515), ((0, 0), (-115, 0), (-115, -58), (-101, -43), (-93, -35), (-88, -32), (-82, -28), (-72, -25),
                   (-57, -24), (-47, -28), (-38, -33), (-28, -45), (-25, -51), (-24, -56), (-24, -71), (-27, -80),
                   (-35, -91), (-58, -114), (-58, -116), (0, -116))),
    ((-20, 710), ((-20, 0), (58, 0), (58, 8), (48, 8), (38, 10), (32, 13), (25, 18), (20, 25), (15, 36), (13, 44),
                  (13, 51), (16, 62), (20, 70), (27, 78), (34, 83), (47, 87), (58, 87), (58, 95), (-20, 95))),
    ((853, 710), ((20, 0), (20, 95), (-58, 95), (-58, 87), (-47, 87), (-34, 83), (-27, 78), (-20, 70), (-16, 62),
                  (-13, 51), (-13, 44), (-15, 36), (-20, 25), (-25, 18), (-32, 13), (-38, 10), (-48, 8), (-58, 8),
                  (-58, 0))),
)


def _edges(polys, kind: int) -> list:
    """لبه های هر چندضلعی با نرمال رو به بیرون؛ (ax، ay، bx، by، nx، ny، نوع)."""
    out = []
    for (px, py), path in polys:
        ox, oy = px - path[0][0], py - path[0][1]
        v = [(ox + x, oy + y) for x, y in path]
        area = sum(v[j][0] * v[i][1] - v[i][0] * v[j][1] for i, j in zip(range(len(v)), [len(v) - 1] + list(range(len(v) - 1))))
        if area < 0:
            v.reverse()
        for i in range(len(v)):
            (ax, ay), (bx, by) = v[i], v[(i + 1) % len(v)]
            ln = math.hypot(bx - ax, by - ay)
            if ln > 1e-9:
                out.append((float(ax), float(ay), float(bx), float(by), (by - ay) / ln, -(bx - ax) / ln, kind))
    return out


RAIL, MOUTH = 0, 1
EDGES = _edges(_RAILS, RAIL) + _edges(_MOUTHS, MOUTH)
MOUTH_EDGES = [e for e in EDGES if e[6] == MOUTH]
# شبکهٔ ۴۰ تایی: هر خانه فقط لبه هایی که توپ داخلش ممکن است به آن ها بخورد (وسط میز خالی است)
CELL = 40.0
_GW, _GH = int(W // CELL) + 3, int(H // CELL) + 3


def _grid(edges) -> dict:
    g: dict = {}
    for e in edges:
        x0, x1 = min(e[0], e[2]) - R - 2, max(e[0], e[2]) + R + 2
        y0, y1 = min(e[1], e[3]) - R - 2, max(e[1], e[3]) + R + 2
        for cx in range(int(math.floor(x0 / CELL)), int(math.floor(x1 / CELL)) + 1):
            for cy in range(int(math.floor(y0 / CELL)), int(math.floor(y1 / CELL)) + 1):
                g.setdefault((cx, cy), []).append(e)
    return g


GRID_ALL = _grid(EDGES)
GRID_MOUTH = _grid(MOUTH_EDGES)


# ---------- شبیه سازی یک ضربه ----------
class _Ball:
    __slots__ = ("n", "x", "y", "vx", "vy", "w", "sx", "sy", "sd", "first", "first_done", "rail", "sink", "sink_t",
                 "potted", "sleep_t", "asleep", "cap_t")

    def __init__(self, n: int, x: float, y: float) -> None:
        self.n, self.x, self.y = n, x, y
        self.vx = self.vy = self.w = self.sx = self.sy = 0.0
        self.sd = SPIN_DAMP
        self.first, self.first_done, self.rail = -1, False, False
        self.sink, self.sink_t, self.cap_t = None, 0.0, 0.0
        self.potted, self.sleep_t, self.asleep = False, 0.0, False


def _damping(b: _Ball, dt: float) -> None:
    ax, ay = abs(b.vx), abs(b.vy)
    o = ax * D_AXIS + ay * D_CROSS if ax > ay else ay * D_AXIS + ax * D_CROSS
    if o > D_CLAMP:
        o = D_CLAMP
    a = (1 - DAMP) * (1 + o / D_DIV)
    s = (1 - ANG_DAMP) * (1 + o / D_DIV)
    fa = a ** dt
    b.vx *= fa
    b.vy *= fa
    b.w *= s ** dt


def _spin_step(b: _Ball, dt: float) -> None:
    if b.sx == 0.0 and b.sy == 0.0:
        return
    v = math.sqrt(b.vx * b.vx + b.vy * b.vy)
    k = (D * SPIN_K) / max(1.0, min(10.0, v / 100))
    ax, ay = b.sx * k, b.sy * k
    if ax * ax + ay * ay > 1:
        b.vx += ax
        b.vy += ay
    sc = b.sd ** (dt / DC)
    b.sx *= sc
    b.sy *= sc


def _ball_in(b: _Ball, p: tuple) -> bool:
    d = math.hypot(p[0] - b.x, p[1] - b.y)
    cap = p[2] - R
    if d < cap * 0.25:          # درست وسط سوراخ: در هر سرعتی می افتد
        return True
    return math.hypot(b.vx, b.vy) <= POCKET_MAX_V and d < cap


def _contacts(balls: list) -> list:
    out = []
    live = [b for b in balls if not b.potted]
    for i, a in enumerate(live):
        grid = GRID_MOUTH if a.sink is not None else GRID_ALL
        if a.sink is None:
            for b in live[i + 1:]:
                if b.sink is not None:
                    continue
                dx, dy = b.x - a.x, b.y - a.y
                if dx > D or dx < -D or dy > D or dy < -D:
                    continue
                d2 = dx * dx + dy * dy
                if d2 >= D * D:
                    continue
                d = math.sqrt(d2)
                if d > 1e-9:
                    nx, ny = dx / d, dy / d
                else:
                    nx, ny, d = 1.0, 0.0, 0.0
                out.append([a, b, nx, ny, D - d, MAT_BALL[1], MAT_BALL[0], 2, 0.0, 0.0, 0.0, 0.0])
        es = grid.get((int(math.floor(a.x / CELL)), int(math.floor(a.y / CELL))))
        if not es:
            continue
        for ax_, ay_, bx_, by_, enx, eny, kind in es:
            ex, ey = bx_ - ax_, by_ - ay_
            l2 = ex * ex + ey * ey
            t = ((a.x - ax_) * ex + (a.y - ay_) * ey) / l2 if l2 > 0 else 0.0
            t = 0.0 if t < 0 else 1.0 if t > 1 else t
            qx, qy = ax_ + ex * t, ay_ + ey * t
            dx, dy = qx - a.x, qy - a.y
            d2 = dx * dx + dy * dy
            if d2 >= R * R:
                continue
            d = math.sqrt(d2)
            if d > 1e-9:
                nx, ny = dx / d, dy / d
            else:
                nx, ny, d = -enx, -eny, 0.0
            fr, e = MAT_RAIL if kind == RAIL else MAT_MOUTH
            out.append([a, None, nx, ny, R - d, e, fr, kind, 0.0, 0.0, 0.0, 0.0])
    return out


def _solve(cs: list, iters: int) -> None:
    """ضربهٔ ترتیبی با انباشت (مثل planck/Box2D) + اصلاح هم پوشانی.
    هر تماس: [a، b، nx، ny، فرورفتگی، بازگشت، اصطکاک، نوع، vn0، هدف، pn، pt]"""
    for c in cs:
        a, b, nx, ny = c[0], c[1], c[2], c[3]
        vn0 = ((b.vx if b else 0.0) - a.vx) * nx + ((b.vy if b else 0.0) - a.vy) * ny
        c[8] = vn0
        c[9] = -c[5] * vn0 if vn0 < -1e-4 else 0.0
        c[10] = c[11] = 0.0
    for _ in range(iters):
        for c in cs:
            a, b, nx, ny = c[0], c[1], c[2], c[3]
            tx, ty = -ny, nx
            bvx, bvy = (b.vx, b.vy) if b else (0.0, 0.0)
            vn = (bvx - a.vx) * nx + (bvy - a.vy) * ny
            kn = 1.0 + (1.0 if b else 0.0)
            pn = c[10] + (c[9] - vn) / kn
            if pn < 0:
                pn = 0.0
            dp = pn - c[10]
            c[10] = pn
            a.vx -= nx * dp
            a.vy -= ny * dp
            if b:
                b.vx += nx * dp
                b.vy += ny * dp
            mu = c[6]
            if mu > 0:
                sa = (nx * ty - ny * tx) * R
                bvx, bvy = (b.vx, b.vy) if b else (0.0, 0.0)
                vt = (bvx - a.vx) * tx + (bvy - a.vy) * ty + (b.w * -sa if b else 0.0) - a.w * sa
                kt = kn + INV_I * sa * sa * (2 if b else 1)
                pt = c[11] - vt / kt
                mx = mu * c[10]
                pt = mx if pt > mx else -mx if pt < -mx else pt
                dt_ = pt - c[11]
                c[11] = pt
                a.vx -= tx * dt_
                a.vy -= ty * dt_
                a.w -= INV_I * dt_ * sa
                if b:
                    b.vx += tx * dt_
                    b.vy += ty * dt_
                    b.w += INV_I * dt_ * sa
    for c in cs:
        pen = c[4] - 0.02
        if pen <= 0:
            continue
        a, b, nx, ny = c[0], c[1], c[2], c[3]
        corr = pen * 0.9 / (2.0 if b else 1.0)
        a.x -= nx * corr
        a.y -= ny * corr
        if b:
            b.x += nx * corr
            b.y += ny * corr


def _on_ball_hit(b: _Ball, other: int) -> None:
    if b.first == -1:
        b.first = other
    if not b.first_done and b.sd == SPIN_DAMP:
        b.first_done = True
        b.sd = SPIN_DAMP_HIT
        b.vx += b.sx * SPIN_K * SPIN_GAIN
        b.vy += b.sy * SPIN_K * SPIN_GAIN


def _sink_step(b: _Ball, h: float) -> bool:
    p = b.sink
    b.sink_t += h
    b.vx += (p[3] - b.x) * SINK_PULL * h
    b.vy += (p[4] - b.y) * SINK_PULL * h
    k = math.exp(-SINK_DRAG * h)
    b.vx *= k
    b.vy *= k
    dx, dy = p[3] - b.x, p[4] - b.y
    settled = dx * dx + dy * dy < 9 and b.vx * b.vx + b.vy * b.vy < 625
    return b.sink_t >= SINK_TIME or (settled and b.sink_t > 0.18)


def simulate(pos: list, angle: float, power: float, spin: tuple, breaking: bool) -> dict:
    """pos: ۱۶ عضو [x، y] یا None (توپ افتاده) برای توپ ۰ (سفید) تا ۱۵.
    خروجی: جای نهایی، فریم ها، توپ های افتاده، برخورد اول و ریل ها، صداها."""
    balls = [_Ball(n, float(p[0]), float(p[1])) for n, p in enumerate(pos) if p is not None]
    by_n = {b.n: b for b in balls}
    cue = by_n[0]
    nx, ny = math.cos(angle), math.sin(angle)
    imp = power * IMPULSE
    if spin[1]:
        cue.sx, cue.sy = nx * spin[1] * power * SPIN_ANG, ny * spin[1] * power * SPIN_ANG
    cue.vx, cue.vy = nx * imp, ny * imp
    if spin[0]:
        s = angle + spin[0] * SPIN_MAX
        px, py = math.cos(s) * R, math.sin(s) * R
        cue.w = (px * ny * imp - py * nx * imp) * INV_I
    step, iters = STEP_BREAK if breaking else STEP_SHOT
    t, next_f = 0.0, 0.0
    frames, pots, hits = [], [], []
    moved = {0}

    def frame() -> None:
        frames.append([v for b in balls for v in ((round(b.x), round(b.y)) if not b.potted else (-1, -1))])

    def moving() -> bool:
        for b in balls:
            if b.potted:
                continue
            if b.sink is not None:
                return True
            sp2 = b.vx * b.vx + b.vy * b.vy
            if sp2 >= SLEEP_V * SLEEP_V or (not b.asleep and sp2 > 0):
                return True
        return False

    frame()
    next_f = 1 / FPS
    while t < MAX_SIM and moving():
        vmax = max((math.hypot(b.vx, b.vy) for b in balls if not b.potted), default=0.0)
        n = max(1, min(16, int(math.ceil(vmax * step / (R * 0.25)))))
        h = step / n
        for _ in range(n):
            t += h
            # ۱) جیب ها: حس گر، گرفتن توپ، کشش لبهٔ جیب
            for b in balls:
                if b.potted or b.sink is not None:
                    continue
                for pi, p in enumerate(POCKETS):
                    dx, dy = p[0] - b.x, p[1] - b.y
                    if dx * dx + dy * dy >= (p[2] + R * SENSOR) ** 2:
                        continue
                    if _ball_in(b, p):
                        b.sink, b.sink_t, b.cap_t, b.rail = p + (pi,), 0.0, t, False
                        break
                    b.vx += dx * POCKET_FORCE * h
                    b.vy += dy * POCKET_FORCE * h
            # ۲) میراسازی
            for b in balls:
                if not b.potted and b.sink is None and not b.asleep:
                    _damping(b, h)
            # ۳) برخوردها
            cs = _contacts(balls)
            if cs:
                _solve(cs, iters)
                for c in cs:
                    if not (c[10] > 0 and c[8] < -1):
                        continue
                    a, b = c[0], c[1]
                    if b is not None:
                        _on_ball_hit(a, b.n)
                        _on_ball_hit(b, a.n)
                        a.asleep = b.asleep = False
                        moved.add(a.n)
                        moved.add(b.n)
                        if c[8] < -60 and len(hits) < 48:
                            hits.append([round(t, 2), "b", round(min(1.0, -c[8] / 1500), 2), round(a.x)])
                    else:
                        a.rail = True
                        if c[8] < -60 and len(hits) < 48:
                            hits.append([round(t, 2), "r" if c[7] == RAIL else "p", round(min(1.0, -c[8] / 1000), 2), round(a.x)])
            # ۴) حرکت
            for b in balls:
                if not b.potted:
                    b.x += b.vx * h
                    b.y += b.vy * h
            # ۵) پیچ (انگلیش)
            for b in balls:
                if not b.potted and b.sink is None and not b.asleep:
                    _spin_step(b, h)
            # ۶) افتادن در سوراخ
            for b in balls:
                if b.sink is not None and _sink_step(b, h):
                    pots.append([b.n, round(b.cap_t, 2), round(t, 2), b.sink[5]])
                    b.sink, b.potted = None, True
                    b.vx = b.vy = b.w = b.sx = b.sy = 0.0
                    moved.add(b.n)
            # ۷) خواب
            for b in balls:
                if b.potted or b.sink is not None:
                    continue
                sp2 = b.vx * b.vx + b.vy * b.vy
                if sp2 < SLEEP_V * SLEEP_V:
                    b.sleep_t += h
                    if b.sleep_t >= SLEEP_T:
                        b.asleep, b.vx, b.vy, b.w = True, 0.0, 0.0, 0.0
                else:
                    b.sleep_t, b.asleep = 0.0, False
                    moved.add(b.n)
        if t >= next_f:
            frame()
            next_f += 1 / FPS
    frame()
    ids = [b.n for b in balls]
    keep = [i for i, n in enumerate(ids) if n in moved]
    out_frames = [[f[2 * i + k] for i in keep for k in (0, 1)] for f in frames]
    final = [None] * 16
    for b in balls:
        if not b.potted:
            final[b.n] = [round(b.x, 2), round(b.y, 2)]
    return {"pos": final, "ids": [ids[i] for i in keep], "frames": out_frames, "dur": round(len(frames) / FPS, 2),
            "pots": pots, "first": cue.first, "rails": sorted(b.n for b in balls if b.rail), "hits": hits}


# ---------- چیدمان ----------
def rack(rng: random.Random) -> list:
    """۱۵ توپ مثلثی (رأس بالا)، ۸ وسط ردیف سوم، دو گوشهٔ عقب یکی تک رنگ و یکی راه راه."""
    order = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15]
    rng.shuffle(order)
    pair = []
    for v in list(order):
        if len(pair) < 2 and (not pair or (v < 8) != (pair[0] < 8)):
            pair.append(v)
            order.remove(v)
    order.insert(4, 8)
    order.insert(10, pair[0])
    order.insert(14, pair[1])
    sp = D + 2
    for _ in range(500):
        ang = math.radians(29 + rng.random() * 2)
        f, d = math.sin(ang) * sp, math.cos(ang) * sp
        p, m = -math.sin(ang + math.pi / 3) * sp, -math.cos(ang + math.pi / 3) * sp
        ax, ay = 415 + rng.random() * 4, 414 + rng.random() * 8
        pos = [None] * 16
        k = 0
        for e, n in enumerate((1, 2, 3, 4, 5)):
            s = ax - f * (n - 1) + (rng.random() * 0.06 - 0.03) * math.sin(ang)
            ll = ay - d * e + (rng.random() * 0.06 - 0.03) * math.cos(ang)
            for _j in range(n):
                pos[order[k]] = [round(s, 2), round(ll, 2)]
                k += 1
                s -= p
                ll += m
        pos[0] = list(CUE_START)
        if all(_free(pos, i, *pos[i]) for i in range(1, 16)):
            return pos
    return pos


def _free(pos: list, me: int, x: float, y: float) -> bool:
    for i, p in enumerate(pos):
        if i != me and p is not None and (p[0] - x) ** 2 + (p[1] - y) ** 2 < D * D - 1e-6:
            return False
    return True


def spot(pos: list, n: int) -> list:
    """جای خالی نزدیک نقطهٔ پا برای توپی که از میز بیرون پریده."""
    fx, fy = FOOT
    for k in range(400):
        ring, idx = k // 8, k % 8
        a = idx * math.pi / 4
        x = min(MAX_X, max(MIN_X, fx + math.cos(a) * 4 * ring))
        y = min(MAX_Y, max(MIN_Y, fy + math.sin(a) * 4 * ring / 1.2))
        if _free(pos, n, x, y):
            return [x, y]
    return [fx, fy]


def cue_spot(pos: list, breaking: bool) -> list:
    """جای پیش فرض توپ سفید (بعد از افتادنش یا برای بریک)."""
    x, y = CUE_START if breaking else (W / 2 - 5, MIN_Y + (MAX_Y - MIN_Y) * 0.78)
    if _free(pos, 0, x, y):
        return [x, y]
    for k in range(1, 60):
        for dx in (k * 6, -k * 6):
            if MIN_X <= x + dx <= MAX_X and _free(pos, 0, x + dx, y):
                return [x + dx, y]
    return [x, y]


# ---------- وضعیت بازی ----------
SEATS2, SEATS4 = ("0", "1"), ("0", "1", "2", "3")
LOBBY_ORDER4 = ("0", "2", "1", "3")    # اولین مهمان میز دعوت یار سازنده می شود
SHOT_PAUSE = 0.6
INTRO = 2.6
BOT_THINK = 1.4
MAX_EVENTS = 40
TURN_S = 30

_rng = random.SystemRandom()


def seats_of(players: int) -> tuple:
    return SEATS4 if players == 4 else SEATS2


def team(i: int) -> int:
    return i % 2


def new_state(seats: list[dict], now: float, turn_s: int, stake: bool, players: int = 2, first: int | None = None) -> dict:
    """seats: [{color: "0".."3", uid, name, av, pic, bot}]"""
    order = seats_of(players)
    ps = {}
    for s in seats:
        ps[s["color"]] = {"uid": s.get("uid"), "name": s["name"], "av": s.get("av", 1), "pic": s.get("pic", ""),
                          "bot": bool(s.get("bot")), "out": False, "misses": 0}
    st = {
        "game": "billiard", "order": list(order), "n": len(order), "players": ps,
        "balls": rack(_rng), "solids": -1, "turn": first if first in range(len(order)) else _rng.randrange(len(order)),
        "bih": True, "breaking": True, "msg": "break", "phase": "play",
        "next_at": now + INTRO, "deadline": now + INTRO + TURN_S, "turn_s": min(max(int(turn_s), TURN_S), 60),
        "stake": stake, "events": [], "seq": 0, "turn_id": 0, "winner": None, "over": False, "started": now,
        "stats": {s: {"shots": 0, "pots": 0, "fouls": 0} for s in order}, "breaks": 0,
    }
    _event(st, t="start", balls=st["balls"], turn=order[st["turn"]])
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


def _nxt(st: dict, i: int) -> int:
    return (i + 1) % st["n"]


def solids_of(st: dict, i: int) -> bool | None:
    """صندلی i تک رنگ می زند؟ (None یعنی میز هنوز باز است)"""
    return None if st["solids"] < 0 else st["solids"] == team(i)


def _group_left(st: dict, solids: bool) -> int:
    base = 1 if solids else 9
    return sum(1 for k in range(base, base + 7) if st["balls"][k] is not None)


def targets(st: dict, i: int) -> list[int]:
    """توپ هایی که صندلی i مجاز است اول به آن ها بزند."""
    b = st["balls"]
    sol = solids_of(st, i)
    if sol is None:
        return [k for k in range(1, 16) if k != 8 and b[k] is not None]
    base = 1 if sol else 9
    out = [k for k in range(base, base + 7) if b[k] is not None]
    return out if out else ([8] if b[8] is not None else [])


def _valid_place(st: dict, x: float, y: float) -> bool:
    if not (MIN_X <= x <= MAX_X and MIN_Y <= y <= MAX_Y):
        return False
    if st["breaking"] and y < BREAK_MIN_Y:
        return False
    return _free(st["balls"], 0, x, y)


def shot(st: dict, i: int, angle, power, sx=0.0, sy=0.0, cx=None, cy=None, now: float = 0.0, auto: bool = False) -> str | None:
    if st["over"]:
        return "over"
    if st["phase"] != "play":
        return "not_play_phase"
    if st["turn"] != i:
        return "not_your_turn"
    if not auto and now < st["next_at"] - 0.3:
        return "not_ready"
    try:
        angle, power, sx, sy = float(angle), float(power), float(sx or 0), float(sy or 0)
    except (TypeError, ValueError):
        return "bad_shot"
    if not all(map(math.isfinite, (angle, power, sx, sy))):
        return "bad_shot"
    if cx is not None or cy is not None:
        if not st["bih"]:
            return "bad_place"
        try:
            cx, cy = float(cx), float(cy)
        except (TypeError, ValueError):
            return "bad_place"
        if not (math.isfinite(cx) and math.isfinite(cy)) or not _valid_place(st, cx, cy):
            return "bad_place"
        st["balls"][0] = [round(cx, 2), round(cy, 2)]
    power = min(1.0, max(MIN_POWER, power))
    sl = math.hypot(sx, sy)
    if sl > 1:
        sx, sy = sx / sl, sy / sl
    s = st["order"][i]
    breaking = st["breaking"]
    if breaking and power > BREAK_MIN:
        power *= BREAK_BONUS + _rng.random() * BREAK_RAND
        angle += _rng.random() * BREAK_JIT * 2 - BREAK_JIT
    pos0 = [p[:] if p else None for p in st["balls"]]
    need = targets(st, i)                  # هدف های مجاز پیش از ضربه (قاعدهٔ برخورد اول)
    res = simulate(pos0, angle, power, (sx, sy), breaking)
    for e in st["events"]:
        if e.get("t") == "shot":
            e.pop("frames", None)
    st["stats"][s]["shots"] += 1
    _event(st, t="shot", c=s, a=round(angle, 4), p=round(power, 3), cue=pos0[0], ids=res["ids"], frames=res["frames"],
           dur=res["dur"], pots=res["pots"], hits=res["hits"], auto=auto)
    st["balls"] = res["pos"]
    _resolve(st, i, res, need, now)
    return None


def _resolve(st: dict, i: int, res: dict, need: list, now: float) -> None:
    """پایان ضربه: خطا، تخصیص گروه، ادامهٔ نوبت، برد و باخت (قواعد ۸ توپ)."""
    s = st["order"][i]
    b = st["balls"]
    potted = [p[0] for p in res["pots"]]
    balls_in = [n for n in potted if n != 0]
    cue_in = 0 in potted
    eight_in = 8 in potted
    first = res["first"]
    rails = [n for n in res["rails"]]
    tm = team(i)
    st["stats"][s]["pots"] += len([n for n in balls_in if n != 8])
    pause = res["dur"] + SHOT_PAUSE
    foul = None
    if st["breaking"]:
        if eight_in or (len(rails) < 4 and not balls_in):
            st["breaks"] += 1
            st["balls"] = rack(_rng)
            st["bih"], st["msg"] = True, "break_8" if eight_in else "break_illegal"
            _event(st, t="rack", c=s, balls=st["balls"], why=st["msg"])
            _wait(st, now, pause + 1.0)
            return
        st["breaking"] = False
        if cue_in:
            foul = "scratch"
        else:
            kept = _assign(st, i, balls_in)
            st["msg"] = "open" if st["solids"] < 0 else ("solids" if solids_of(st, i) else "stripes")
            _respot(st)
            _after(st, i, kept, None, pause, now)
            return
    else:
        sol = solids_of(st, i)
        if sol is not None and need == [8]:
            if first != 8:
                foul = "hit_8_first"
        elif first == -1:
            foul = "no_hit"
        elif first == 8 or (sol is not None and (first < 8) != sol):
            foul = "wrong_first"
        if cue_in:
            foul = "scratch"
        if foul is None and not rails and not balls_in:
            foul = "no_rail"
        if foul is None and any(p is not None and not (0 <= p[0] <= W and 0 <= p[1] <= H) for p in b[1:]):
            foul = "jump"
    if eight_in:
        sol = solids_of(st, i)
        cleared = sol is not None and _group_left(st, sol) == 0
        if cleared and foul is None:
            st["msg"] = "won"
            _finish(st, tm, "pot8")
        else:
            st["msg"] = "lost8"
            _finish(st, 1 - tm, "foul8" if cleared else "early8")
        return
    _respot(st)
    if foul is not None:
        st["stats"][s]["fouls"] += 1
        st["msg"] = foul
        _after(st, i, False, foul, pause, now)
        return
    kept = _assign(st, i, balls_in)
    sol = solids_of(st, i)
    good = [n for n in balls_in if sol is None or (n < 8) == sol]
    keep = kept or bool(good)
    if not balls_in:
        st["msg"] = ""
    elif not good:
        st["msg"] = "wrong_pot"
    elif sol is not None and targets(st, i) == [8]:
        st["msg"] = "on_8"
    else:
        st["msg"] = "potted"
    _after(st, i, keep, None, pause, now)


def _assign(st: dict, i: int, balls_in: list[int]) -> bool:
    """میز باز: اولین توپ افتاده (جز ۸) گروه تیم زننده را تعیین می کند."""
    if st["solids"] >= 0:
        return False
    first = next((n for n in balls_in if n != 8), None)
    if first is None:
        return False
    st["solids"] = team(i) if first < 8 else 1 - team(i)
    _event(st, t="groups", solids=st["solids"], c=st["order"][i])
    return True


def _respot(st: dict) -> None:
    b = st["balls"]
    for n in range(1, 16):
        p = b[n]
        if p is not None and not (0 <= p[0] <= W and 0 <= p[1] <= H):
            b[n] = None
            b[n] = spot(b, n)
            _event(st, t="spot", k=n, at=b[n])


def _after(st: dict, i: int, keep: bool, foul: str | None, pause: float, now: float) -> None:
    b = st["balls"]
    if b[0] is None or not (0 <= b[0][0] <= W and 0 <= b[0][1] <= H):
        b[0] = None
        b[0] = cue_spot(b, False)
    nxt = i if keep and foul is None else _nxt(st, i)
    st["turn"] = nxt
    st["bih"] = foul is not None
    _event(st, t="turn", c=st["order"][nxt], bih=st["bih"], foul=foul, msg=st["msg"], balls=b, solids=st["solids"])
    _wait(st, now, pause)


def _finish(st: dict, w: int | None, why: str = "") -> None:
    st["over"], st["winner"], st["phase"] = True, w, "over"
    _event(st, t="win" if w is not None else "end", team=w, why=why, balls=st["balls"])


def leave(st: dict, s: str, now: float, why: str = "left") -> None:
    """خروج یا جریمهٔ غیبت. دو نفره: حریف برنده. چهار نفره: مثل حکم ربات جای او بازی
    می کند؛ اگر کسی از یک تیم نماند آن تیم باخته است."""
    p = st["players"].get(s)
    if not p or p["out"] or st["over"]:
        return
    p["out"] = True
    _event(st, t="leave", c=s, why=why)
    i = st["order"].index(s)
    if st["n"] == 2:
        _finish(st, 1 - team(i), "left")
        return
    if not any(not q["bot"] and not q["out"] for q in st["players"].values()):
        _finish(st, None, "empty")
        return
    if st["turn"] == i:
        st["next_at"] = min(st["next_at"], now + BOT_THINK)


# ---------- ربات ----------
def _seg_clear(pos: list, ax: float, ay: float, bx: float, by: float, skip: set, gap: float = D) -> bool:
    ex, ey = bx - ax, by - ay
    l2 = ex * ex + ey * ey or 1.0
    for n, p in enumerate(pos):
        if p is None or n in skip:
            continue
        t = ((p[0] - ax) * ex + (p[1] - ay) * ey) / l2
        if t <= 0 or t >= 1:
            continue
        qx, qy = ax + ex * t, ay + ey * t
        if (p[0] - qx) ** 2 + (p[1] - qy) ** 2 < gap * gap:
            return False
    return True


def _plans(st: dict, i: int, cue: list) -> list:
    """ضربه های ممکن با «توپ شبح»: هدف مجاز → جیب، مسیر باز، زاویهٔ برش کم."""
    pos = st["balls"]
    out = []
    for k in targets(st, i):
        bx, by = pos[k]
        for p in POCKETS:
            tx, ty = p[3], p[4]
            ux, uy = tx - bx, ty - by
            dl = math.hypot(ux, uy) or 1.0
            ux, uy = ux / dl, uy / dl
            gx, gy = bx - ux * D, by - uy * D
            cxv, cyv = gx - cue[0], gy - cue[1]
            cl = math.hypot(cxv, cyv)
            if cl < 1:
                continue
            cut = (cxv * ux + cyv * uy) / cl
            if cut < 0.25:
                continue
            if not _seg_clear(pos, cue[0], cue[1], gx, gy, {0, k}) or not _seg_clear(pos, bx, by, tx, ty, {0, k}):
                continue
            score = cut * 3 - dl / 900 - cl / 1400
            power = min(0.85, max(0.14, 0.08 + (cl + dl * 1.3) / (2600 * max(0.45, cut))))
            out.append((score, math.atan2(cyv, cxv), power, k))
    out.sort(reverse=True)
    return out


def _bot_place(st: dict, i: int) -> list:
    """توپ در دست: توپ سفید را پشت بهترین هدف (روی امتداد هدف تا جیب) می گذارد."""
    pos = st["balls"]
    if st["breaking"]:
        x = W / 2 - 5 + (_rng.random() - 0.5) * 160
        return [x, BREAK_MIN_Y + 10] if _valid_place(st, x, BREAK_MIN_Y + 10) else list(CUE_START)
    best, bv = None, -1e9
    for k in targets(st, i):
        bx, by = pos[k]
        for p in POCKETS:
            ux, uy = p[3] - bx, p[4] - by
            dl = math.hypot(ux, uy) or 1.0
            ux, uy = ux / dl, uy / dl
            for back in (110, 160, 230):
                x, y = bx - ux * (D + back), by - uy * (D + back)
                if not _valid_place(st, x, y) or not _seg_clear(pos, bx, by, p[3], p[4], {0, k}):
                    continue
                v = -dl / 900 - back / 600 + _rng.random() * 0.1
                if v > bv:
                    best, bv = [x, y], v
    if best is None:
        best = cue_spot(pos, False)
    return best


def bot_shot(st: dict, i: int) -> tuple:
    """(زاویه، قدرت، پیچ x، پیچ y، x سفید، y سفید)"""
    place = _bot_place(st, i) if st["bih"] else None
    cue = place or st["balls"][0]
    if st["breaking"]:
        apex = min((p for n, p in enumerate(st["balls"]) if n and p), key=lambda p: p[1])
        a = math.atan2(apex[1] - cue[1], apex[0] - cue[0]) + (_rng.random() - 0.5) * 0.02
        return a, 0.92 + _rng.random() * 0.08, 0.0, 0.0, *(place or (None, None))
    if place:
        old = st["balls"][0]
        st["balls"][0] = place
    plans = _plans(st, i, cue)
    if place:
        st["balls"][0] = old
    if plans:
        _, a, power, _k = plans[min(len(plans) - 1, int(_rng.random() ** 3 * 2))]
        a += (_rng.random() - 0.5) * 0.022           # دست ربات هم کمی می لرزد
        return a, min(1.0, power * (0.95 + _rng.random() * 0.15)), 0.0, (_rng.random() - 0.5) * 0.4, *(place or (None, None))
    # راه باز به جیب نیست: محکم به نزدیک ترین توپ مجاز تا خطا نشود
    tg = targets(st, i) or [n for n in range(1, 16) if st["balls"][n]]
    k = min(tg, key=lambda n: math.hypot(st["balls"][n][0] - cue[0], st["balls"][n][1] - cue[1]))
    bx, by = st["balls"][k]
    a = math.atan2(by - cue[1], bx - cue[0]) + (_rng.random() - 0.5) * 0.05
    return a, 0.45 + _rng.random() * 0.25, 0.0, 0.0, *(place or (None, None))


def tick(st: dict, now: float) -> bool:
    changed = False
    for _ in range(3):
        if st["over"]:
            break
        i = st["turn"]
        s = st["order"][i]
        p = st["players"][s]
        if _auto(st, i):
            if now < st["next_at"]:
                break
            a, pw, sx, sy, cx, cy = bot_shot(st, i)
            shot(st, i, a, pw, sx, sy, cx, cy, now, auto=True)
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
        # وقت تمام شد: خطا، نفر بعد توپ در دست دارد
        st["msg"] = "timeout"
        if st["breaking"]:
            st["turn"] = _nxt(st, i)
            st["bih"] = True
            _event(st, t="turn", c=st["order"][st["turn"]], bih=True, foul="timeout", msg="timeout", balls=st["balls"],
                   solids=st["solids"])
            _wait(st, now, 0.4)
        else:
            _after(st, i, False, "timeout", 0.4, now)
    return changed


def human_acted(st: dict, s: str) -> None:
    st["players"][s]["misses"] = 0


def winners(st: dict) -> set[str]:
    w = st.get("winner")
    if w is None:
        return set()
    return {s for k, s in enumerate(st["order"]) if team(k) == w}


def score(st: dict) -> list[int]:
    """تعداد توپ های افتادهٔ گروه هر تیم [تیم ۰، تیم ۱] (پیش از تعیین گروه ۰)."""
    if st["solids"] < 0:
        return [0, 0]
    out = [0, 0]
    for tm in (0, 1):
        sol = st["solids"] == tm
        out[tm] = 7 - _group_left(st, sol)
    return out


# ---------- نمای هر بازیکن ----------
def view(st: dict, me: str | None, since: int, now: float) -> dict:
    cur = current(st)
    mi = st["order"].index(me) if me in st["order"] else None
    auto = cur is not None and _auto(st, st["order"].index(cur))
    return {
        "order": list(st["order"]),
        "n": st["n"],
        "players": {s: {"name": p["name"], "av": p["av"], "pic": p.get("pic", ""), "bot": p["bot"], "out": p["out"],
                        "me": s == me, "team": team(st["order"].index(s)),
                        "group": None if st["solids"] < 0 else ("solids" if st["solids"] == team(st["order"].index(s)) else "stripes")}
                    for s, p in st["players"].items()},
        "me": me,
        "phase": st["phase"],
        "turn": cur,
        "balls": st["balls"],
        "solids": st["solids"],
        "bih": st["bih"],
        "breaking": st["breaking"],
        "msg": st["msg"],
        "targets": targets(st, st["turn"]) if cur is not None else [],
        "mine": targets(st, mi) if mi is not None and not st["over"] else [],
        "score": score(st),
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
