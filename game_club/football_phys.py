"""فیزیک فوتبال میزی (Table Soccer): پورت دقیق فیزیک بازی پلاتو.

پلاتو از موتور p2.js (حل کنندهٔ گاوس-سایدل با معادلات SPOOK) استفاده می کند و تنظیم ها
(جرم، میرایی، ضریب برگشت، اصطکاک، گام زمانی ۰٫۰۱۵) در بستهٔ کلاینت بازی آمده اند؛ این فایل
همان مراحل World.internalStep را اجرا می کند:
  میرایی ← ترتیب SAP و جفت های برخورد ← بیدار کردن ← جزیره ها و حل کننده (۱۰ تکرار)
  ← انتگرال ← خواب ← postStep
و قوانین پاس (آهن ربا، شوت زننده و گیرنده) و گل را همان جا، لحظه به لحظه، اعمال می کند.
این پورت با خود موتور p2 داخل بستهٔ پلاتو سنجیده شده (test_football_phys_matches_plato).

فقط + - * / و sqrt در شوت به کار رفته (توان میرایی هم با log/exp ساخته شده از همین ها) تا
نسخهٔ جاوااسکریپت (static/football-physics.js) همان نتیجه را بدهد؛ سرور همیشه مرجع است.

مختصات: زمین W×H، مبدا بالا چپ. مهره های صندلی ۰ شماره ۰..۵ (پایین)، صندلی ۱ شماره ۶..۱۱ (بالا)
و توپ شماره ۱۲. صندلی ۰ به بالا حمله می کند (دروازهٔ بالا = اندیس ۰). اولین مهرهٔ هر تیم دروازه بان است.
"""
from __future__ import annotations

import math

MAXF = 1.7976931348623157e308

# ---------- زمین (Xu.LARGE در پلاتو) ----------
W, H = 1042.0, 1920.0
GOAL_W = 354.0
BALL_R = 32.0
GOAL_H = BALL_R * 3            # عمق دروازه = ۳ شعاع توپ
POST_R = 5.0
BOX_W = (W - GOAL_W) * 0.5     # دیوارهٔ دو طرف دروازه
BALL = 12
N = 13

# ---------- مهره ها و توپ (H و tA در پلاتو) ----------
REG_R, KEEP_R = 55.0, 64.0
REG_M, KEEP_M = 0.76, 1.0
REG_D, KEEP_D = 0.41, 0.46
TOK_DVAR, TOK_ANG = 1.005, 0.4
BALL_M, BALL_D, BALL_DVAR, BALL_CTL_D, BALL_ANG = 0.11, 0.36, 1.003, 0.75, 0.5
CONTROL_RADIUS = 236.0         # فاصلهٔ توپ تا گیرندهٔ پاس برای کامل شدن پاس
SLEEP_TOK, SLEEP_BALL, SLEEP_T = 10.0, 30.0, 0.02
IMPULSE_MULT, IMPULSE_MAX = 4.6, 250.0
MAGNET_PASS, MAGNET_CTRL = 1.5, 2.25

DT = 0.015
FRAME_EVERY = 2
MAX_STEPS = 3000
ITER = 10
TOL = 1e-7
FRIC_G = 10.0                  # frictionGravity: نیروی لغزش = اصطکاک × ۱۰ × جرم کاسته

# مواد: (ضریب برگشت، اصطکاک، سختی، آرامش)
CM = {
    ("ball", "goal"): (0.0, 30.0, 1e4, 8.0),
    ("ball", "wall"): (0.95, 400.0, MAXF, 4.0),
    ("ball", "player"): (0.8, 500.0, MAXF, 4.0),
    ("player", "goal"): (0.0, 40.0, 1e4, 8.0),
    ("player", "wall"): (0.7, 500.0, MAXF, 4.0),
    ("player", "player"): (0.77, 200.0, MAXF, 4.0),
}
FRIC_K, FRIC_RELAX = 1e6, 4.0   # سختی و آرامش اصطکاک (پیش فرض p2)
CON_K, CON_RELAX = 1e6, 4.0     # معادلهٔ قید فاصله (آهن ربا)

AUTO_V_MAX, AUTO_V_MIN = 600.0, 500.0
CONTROL_ANGLE_DIF = 3 * 0.0174533
CONTROL_MAX_STEPS = 900


def rd2(v: float) -> float:
    return math.floor(v * 100.0 + 0.5) / 100.0


# ---------- توان میرایی: base ** DT فقط با + - * / و sqrt ----------
def _ln(x: float) -> float:
    y = x
    for _ in range(6):
        y = math.sqrt(y)
    z = (y - 1.0) / (y + 1.0)
    z2 = z * z
    s = z * (1.0 + z2 * (1.0 / 3 + z2 * (1.0 / 5 + z2 * (1.0 / 7 + z2 * (1.0 / 9 + z2 * (1.0 / 11 + z2 * (1.0 / 13)))))))
    return 128.0 * s


def _exp(t: float) -> float:
    u = t / 64.0
    e = 1.0 + u * (1.0 + u * (1.0 / 2 + u * (1.0 / 6 + u * (1.0 / 24 + u * (1.0 / 120 + u * (1.0 / 720 + u * (1.0 / 5040)))))))
    for _ in range(6):
        e = e * e
    return e


def dpow(base: float) -> float:
    """base ** DT (برای base در [0، ۱])."""
    if base <= 0.0:
        return 0.0
    if base >= 1.0:
        return 1.0
    return _exp(DT * _ln(base))


# ---------- هندسهٔ ثابت: ترتیب «بدن ها» مثل World.bodies در پلاتو ----------
# اسلات ۰ توپ، ۱..۴ صفحه ها (دیوارها)، ۵..۸ جعبهٔ کنار دروازه، ۹..۱۰ حسگر دروازه، ۱۱..۱۴ تیرک،
# ۱۵..۲۶ مهره ها. p2 جفت ها را با SAP روی محور x مرتب می کند (فهرست محوری)، همان ترتیب بسته بندی معادله ها.
PLANES = (((0.0, 0.0), (0.0, 1.0), "goal"), ((W, 0.0), (-1.0, 0.0), "wall"),
          ((0.0, H), (0.0, -1.0), "goal"), ((0.0, 0.0), (1.0, 0.0), "wall"))
BOX_HW, BOX_HH = BOX_W * 0.5, GOAL_H * 0.5
BOXES = ((BOX_HW, BOX_HH), (W - BOX_HW, BOX_HH), (BOX_HW, H - BOX_HH), (W - BOX_HW, H - BOX_HH))
_GH = GOAL_H - BALL_R * 2
GOAL_HW, GOAL_HH = GOAL_W * 0.5, _GH * 0.5
GOALS = ((W * 0.5, GOAL_HH), (W * 0.5, H - GOAL_HH))          # حسگر دروازه: مرکز
_PX0 = W * 0.5 - GOAL_W * 0.5 - POST_R
_PX1 = W * 0.5 + GOAL_W * 0.5 + POST_R
POSTS = ((_PX0, GOAL_H), (_PX1, GOAL_H), (_PX0, H - GOAL_H), (_PX1, H - GOAL_H))
# کران پایین x جعبهٔ AABB هر اسلات ثابت (برای مرتب سازی SAP)؛ صفحه: نیم صفحهٔ «توپر»
_BIG = 1e7
STATIC_LOWER = {1: -_BIG, 2: W, 3: -_BIG, 4: -_BIG}
for _i, (_bx, _by) in enumerate(BOXES):
    STATIC_LOWER[5 + _i] = _bx - BOX_HW
for _i, (_gx, _gy) in enumerate(GOALS):
    STATIC_LOWER[9 + _i] = _gx - GOAL_HW
for _i, (_px, _py) in enumerate(POSTS):
    STATIC_LOWER[11 + _i] = _px - POST_R


_LOWER0 = [STATIC_LOWER.get(_s, 0.0) for _s in range(27)]


def _build_pairs():
    """جفت های (i، j) که اجازهٔ برخورد دارند و حداقل یکی پویاست (بدون حسگرها)."""
    grp, msk = {}, {}
    for s in range(27):
        if s == 0:
            grp[s], msk[s] = 8, 1 | 2 | 4 | 16
        elif s <= 8:
            grp[s], msk[s] = 1, 4 | 8
        elif s <= 10:
            grp[s], msk[s] = 2, 8
        elif s <= 14:
            grp[s], msk[s] = 16, 4 | 8
        else:
            grp[s], msk[s] = 4, 1 | 4 | 8 | 16
    pairs = []
    for i in range(1, 27):
        for j in range(i):
            if not (i == 0 or i >= 15 or j == 0 or j >= 15):
                continue
            if not ((grp[i] & msk[j]) and (grp[j] & msk[i])):
                continue
            if 9 <= i <= 10 or 9 <= j <= 10:
                continue          # حسگر دروازه جدا بررسی می شود
            pairs.append((i, j))
    return pairs


PAIRS = _build_pairs()


def slot_dyn(s: int) -> int:
    if s == 0:
        return BALL
    return s - 15 if s >= 15 else -1


def dyn_slot(d: int) -> int:
    return 0 if d == BALL else d + 15


PAIRDATA = [(i, j, slot_dyn(i), slot_dyn(j)) for i, j in PAIRS]
PAIR_BY_DYN: list = [[] for _ in range(N)]
for _n, (_i, _j, _di, _dj) in enumerate(PAIRDATA):
    if _di >= 0:
        PAIR_BY_DYN[_di].append(_n)
    if _dj >= 0:
        PAIR_BY_DYN[_dj].append(_n)


def radius_of(k: int) -> float:
    if k == BALL:
        return BALL_R
    return KEEP_R if k % 6 == 0 else REG_R


class Sim:
    """یک جهان p2: ۱۳ جسم پویا + هندسهٔ ثابت. step همان internalStep است."""

    def __init__(self, pos: list, team: int, pass_ok: bool = False) -> None:
        n = N
        self.x = [float(p[0]) for p in pos]
        self.y = [float(p[1]) for p in pos]
        self.vx = [0.0] * n
        self.vy = [0.0] * n
        self.w = [0.0] * n
        self.r = [radius_of(k) for k in range(n)]
        self.m = [BALL_M if k == BALL else (KEEP_M if k % 6 == 0 else REG_M) for k in range(n)]
        self.im = [1.0 / m for m in self.m]
        self.ii = [0.0 if k == BALL else 1.0 / (self.r[k] * self.r[k] / 2) for k in range(n)]
        self.base_d = [BALL_D if k == BALL else (KEEP_D if k % 6 == 0 else REG_D) for k in range(n)]
        self.damp = self.base_d[:]
        self.angf = [dpow(1.0 - (BALL_ANG if k == BALL else TOK_ANG)) for k in range(n)]
        self.angf_base = self.angf[:]
        self.slim2 = [(SLEEP_BALL if k == BALL else SLEEP_TOK) ** 2 for k in range(n)]
        self.st = [2] * n            # ۰ بیدار، ۱ خواب آلود، ۲ خواب
        self.idle = [0.0] * n
        self.mmx = [1.0] * n
        self.mmy = [1.0] * n
        self.time = 0.0
        self.last_pairs: set = set()      # جفت های برخورد گام قبل (firstImpact)
        self.prev_ov: set = set()         # هم پوشانی های توپ گام قبل (beginContact)
        self.axis = list(range(27))       # فهرست محوری SAP (ماندگار بین گام ها)
        self.hits: list = []
        # قوانین پاس
        self.team = team
        self.pass_ok = pass_ok
        self.shooter = None
        self.receiver = None
        self.goal = None
        self.magnet = None               # اندیس مهره ای که توپ به آن چسبیده
        self.magnet_dist = 0.0
        self.ctl = False                 # حالت کنترل (حرکت گیرندهٔ پاس پشت توپ)

    # ---------- کمک ----------
    def wake(self, k: int) -> None:
        self.st[k] = 0
        self.idle[k] = 0.0

    def sleep(self, k: int) -> None:
        self.st[k] = 2
        self.vx[k] = self.vy[k] = self.w[k] = 0.0

    def set_impulse(self, k: int, ix: float, iy: float) -> None:
        self.vx[k] += ix * self.im[k] * self.mmx[k]
        self.vy[k] += iy * self.im[k] * self.mmy[k]

    # ---------- آهن ربای توپ (magnetizeBall / demagnetizeBall) ----------
    def magnetize(self, k: int, control: bool = False, secure: bool = True) -> None:
        self.demagnetize(False)
        d = self.r[k]
        d += BALL_R * (MAGNET_CTRL if (control and secure) else MAGNET_PASS)
        self.magnet, self.magnet_dist = k, d
        self.wake(k)
        self.wake(BALL)
        if control:
            self.mmx[BALL] = self.mmy[BALL] = 0.0
            for p in range(12):
                self.angf[p] = 0.0
                if p != k:
                    self.damp[p] = 0.9999999
        else:
            self.damp[BALL] = BALL_CTL_D

    def demagnetize(self, full: bool) -> None:
        if self.magnet is not None:
            if full:
                self.mmx[BALL] = self.mmy[BALL] = 1.0
                for p in range(12):
                    self.angf[p] = self.angf_base[p]
                    if p != self.magnet:
                        self.damp[p] = self.base_d[p]
            else:
                self.damp[BALL] = BALL_D
            self.magnet = None
        else:
            self.mmx[BALL] = self.mmy[BALL] = 1.0

    # ---------- ترتیب SAP ----------
    def _sort_axis(self) -> list:
        x, r = self.x, self.r
        lower = _LOWER0[:]
        lower[0] = x[BALL] - r[BALL]
        for k in range(12):
            lower[15 + k] = x[k] - r[k]
        ax = self.axis
        for q in range(1, 27):          # مرتب سازی درجی پایدار، مثل SAPBroadphase.sortList
            e = ax[q]
            t = lower[e]
            i = q - 1
            while i >= 0 and lower[ax[i]] > t:
                ax[i + 1] = ax[i]
                i -= 1
            ax[i + 1] = e
        pos = [0] * 27
        for idx, sl in enumerate(ax):
            pos[sl] = idx
        return pos

    # ---------- یک گام ----------
    def step(self) -> None:
        x, y, vx, vy, w, st = self.x, self.y, self.vx, self.vy, self.w, self.st
        h = DT
        # ۱) میرایی (applyDamping)
        for k in range(N):
            if vx[k] != 0.0 or vy[k] != 0.0 or w[k] != 0.0:
                f = dpow(1.0 - self.damp[k])
                vx[k] *= f
                vy[k] *= f
                w[k] *= self.angf[k]
        # ۲) ترتیب SAP، حسگر دروازه و شروع برخورد توپ با مهره ها (beginContact)
        axpos = self._sort_axis()
        self._ball_events(axpos)
        # ۳) تماس ها
        contacts = []
        cur_pairs: set = set()
        wake_after: list = []
        awake = [d for d in range(N) if st[d] != 2]
        if len(awake) == 1:
            idxs = PAIR_BY_DYN[awake[0]]
        else:
            seen: set = set()
            for d in awake:
                seen.update(PAIR_BY_DYN[d])
            idxs = sorted(seen)
        for n in idxs:
            i, j, di, dj = PAIRDATA[n]
            c = self._contact(i, j, di, dj, axpos)
            if c is None:
                continue
            if di >= 0 and dj >= 0:
                for a, b in ((di, dj), (dj, di)):
                    if st[a] == 2 and st[b] == 0:
                        if vx[b] * vx[b] + vy[b] * vy[b] + w[b] * w[b] >= self.slim2[b] * 2:
                            wake_after.append(a)
            cur_pairs.add((i, j))
            pa, pb = axpos[i], axpos[j]
            contacts.append(((pa, pb) if pa < pb else (pb, pa), c, (i, j) not in self.last_pairs))
        for a in wake_after:
            self.wake(a)
        self.last_pairs = cur_pairs
        contacts.sort(key=lambda t: t[0])
        # ۴) معادله ها، جزیره ها و حل
        eqs = self._build_equations(contacts)
        if eqs:
            self._solve_islands(eqs)
        # ۵) انتگرال
        for k in range(N):
            if vx[k] != 0.0 or vy[k] != 0.0:
                x[k] += vx[k] * h
                y[k] += vy[k] * h
        # ۶) خواب (sleepTick)
        for k in range(N):
            if vx[k] * vx[k] + vy[k] * vy[k] + w[k] * w[k] >= self.slim2[k]:
                self.idle[k] = 0.0
                st[k] = 0
            else:
                self.idle[k] += h
                if st[k] != 1:
                    st[k] = 1
            if self.idle[k] > SLEEP_T:
                self.sleep(k)
        self.time += h
        # ۷) postStep: منطق بازی (آهن ربا)، میرایی توپ، میرایی مهره ها
        if self.receiver is not None and not self.ctl and (self.magnet is None or self.magnet != self.receiver):
            vx[BALL] = vy[BALL] = 0.0
            self.magnetize(self.receiver)
        if st[BALL] == 1:
            self.damp[BALL] = BALL_CTL_D if self.magnet is not None else BALL_D
        elif st[BALL] == 0 and self.damp[BALL] < 1.0:
            d = self.damp[BALL] * BALL_DVAR
            self.damp[BALL] = d if d < 1.0 else 1.0
        for k in range(12):
            if st[k] == 1:
                self.damp[k] = self.base_d[k]
            elif st[k] == 0 and self.damp[k] < 1.0:
                d = self.damp[k] * TOK_DVAR
                self.damp[k] = d if d < 1.0 else 1.0

    # ---------- beginContact توپ (به ترتیب جفت های SAP) ----------
    def _ball_events(self, axpos: list) -> None:
        x, y = self.x, self.y
        bx, by, R = x[BALL], y[BALL], BALL_R
        cur: set = set()
        news: list = []
        for g in (0, 1):
            gx, gy = GOALS[g]
            lx, ly = bx - gx, by - gy
            qx = -GOAL_HW if lx < -GOAL_HW else (GOAL_HW if lx > GOAL_HW else lx)
            qy = -GOAL_HH if ly < -GOAL_HH else (GOAL_HH if ly > GOAL_HH else ly)
            dx, dy = qx - lx, qy - ly
            if dx * dx + dy * dy <= R * R:
                cur.add(g)
                if g not in self.prev_ov:
                    news.append((min(axpos[0], axpos[9 + g]), max(axpos[0], axpos[9 + g]), 0, g))
        for k in range(12):
            rr = self.r[k] + R
            dx, dy = x[k] - bx, y[k] - by
            if dx > rr or dx < -rr or dy > rr or dy < -rr:
                continue
            if dx * dx + dy * dy <= rr * rr:
                cur.add(10 + k)
                if (10 + k) not in self.prev_ov:
                    news.append((min(axpos[0], axpos[15 + k]), max(axpos[0], axpos[15 + k]), 1, k))
        self.prev_ov = cur
        news.sort()
        for _, _, kind, q in news:
            if kind == 0:
                if self.goal is None:
                    self.goal = q
                    self.receiver = None
            else:
                self._touch(q)

    def _touch(self, o: int) -> None:
        """توپ به مهرهٔ o خورد: شوت زنندهٔ پاس و گیرنده را مشخص می کند."""
        if not self.pass_ok or (o // 6) != self.team:
            return
        if self.shooter is None:
            self.shooter = o
        elif o != self.shooter and o != self.receiver:
            self.receiver = o

    # ---------- یافتن تماس برای یک جفت ----------
    def _contact(self, i: int, j: int, di: int, dj: int, axpos: list):
        """(A، B، nx، ny، cAx، cAy، cBx، cBy، Gq، ماده A، ماده B، نوع صدا)؛ نرمال از A به B."""
        x, y, r = self.x, self.y, self.r
        if di >= 0 and dj >= 0:             # دایره/دایره: A = دیرتر در فهرست محوری، B = زودتر
            a, b = (di, dj) if axpos[i] > axpos[j] else (dj, di)
            ax, ay, bx, by = x[a], y[a], x[b], y[b]
            ra, rb = r[a], r[b]
            dx, dy = bx - ax, by - ay
            rr = ra + rb
            if dx > rr or dx < -rr or dy > rr or dy < -rr:
                return None
            d2 = dx * dx + dy * dy
            if d2 > rr * rr:
                return None
            d = math.sqrt(d2)
            nx, ny = (1.0, 0.0) if d == 0.0 else (dx / d, dy / d)
            kind = "b" if BALL in (di, dj) else "d"
            return (a, b, nx, ny, nx * ra, ny * ra, -nx * rb, -ny * rb, d - ra - rb,
                    "ball" if a == BALL else "player", "ball" if b == BALL else "player", kind)
        d_ = di if di >= 0 else dj
        s_ = j if di >= 0 else i
        cx, cy, R = x[d_], y[d_], r[d_]
        mat_d = "ball" if d_ == BALL else "player"
        if 1 <= s_ <= 4:                    # صفحه: A = صفحه، B = دایره
            (px, py), (nx, ny), mt = PLANES[s_ - 1]
            dd = nx * (cx - px) + ny * (cy - py)
            if dd > R:
                return None
            return (13, d_, nx, ny, (cx - px) - nx * dd, (cy - py) - ny * dd, -nx * R, -ny * R, dd - R, mt, mat_d, "w")
        if 5 <= s_ <= 8:                    # جعبه: A = دایره، B = جعبه (نرمال از دایره به جعبه)
            bx0, by0 = BOXES[s_ - 5]
            lx, ly = cx - bx0, cy - by0
            qx = -BOX_HW if lx < -BOX_HW else (BOX_HW if lx > BOX_HW else lx)
            qy = -BOX_HH if ly < -BOX_HH else (BOX_HH if ly > BOX_HH else ly)
            dx, dy = qx - lx, qy - ly
            d2 = dx * dx + dy * dy
            if d2 > R * R:
                return None
            if d2 == 0.0:                   # مرکز داخل جعبه: از نزدیک ترین وجه بیرون
                gx, gy = BOX_HW - abs(lx), BOX_HH - abs(ly)
                if gx < gy:
                    qx, qy = (BOX_HW if lx >= 0 else -BOX_HW), ly
                else:
                    qx, qy = lx, (BOX_HH if ly >= 0 else -BOX_HH)
                dx, dy = qx - lx, qy - ly
                d2 = dx * dx + dy * dy
            d = math.sqrt(d2)
            nx, ny = (0.0, 1.0) if d == 0.0 else (dx / d, dy / d)
            return (d_, 13, nx, ny, nx * R, ny * R, qx, qy, d - R, mat_d, "wall", "w")
        # تیرک (دایرهٔ ثابت): A = دیرتر در فهرست محوری
        px, py = POSTS[s_ - 11]
        post_first = axpos[s_] > axpos[dyn_slot(d_)]      # تیرک دیرتر ← A
        if post_first:
            ax, ay, bx, by, ra, rb, A, B = px, py, cx, cy, POST_R, R, 13, d_
        else:
            ax, ay, bx, by, ra, rb, A, B = cx, cy, px, py, R, POST_R, d_, 13
        dx, dy = bx - ax, by - ay
        rr = ra + rb
        if dx > rr or dx < -rr or dy > rr or dy < -rr:
            return None
        d2 = dx * dx + dy * dy
        if d2 > rr * rr:
            return None
        d = math.sqrt(d2)
        nx, ny = (1.0, 0.0) if d == 0.0 else (dx / d, dy / d)
        return (A, B, nx, ny, nx * ra, ny * ra, -nx * rb, -ny * rb, d - ra - rb, mat_d, "wall", "p")

    # ---------- معادله ها: همهٔ تماس ها، بعد اصطکاک ها، بعد قید آهن ربا ----------
    # هر معادله: [A، B، g0..g5، نوع (۰ تماس، ۱ اصطکاک، ۲ قید)، gq، a، b، eps، invC، λ، minDt، maxDt،
    #            iMA، iIA، iMB، iIB، ضریب برگشت، firstImpact، ایندکس، B]
    def _build_equations(self, contacts: list):
        x, y = self.x, self.y
        st, im, ii, mmx, mmy, m = self.st, self.im, self.ii, self.mmx, self.mmy, self.m
        eqs: list = []
        fr: list = []

        def mk(A, B, g, kind, gq, a, b, eps, mn, mx, rest, first):
            sA = A == 13 or st[A] == 2
            sB = B == 13 or st[B] == 2
            iMA = 0.0 if sA else im[A]
            iIA = 0.0 if sA else ii[A]
            iMB = 0.0 if sB else im[B]
            iIB = 0.0 if sB else ii[B]
            mAx = mmx[A] if A != 13 else 1.0
            mAy = mmy[A] if A != 13 else 1.0
            mBx = mmx[B] if B != 13 else 1.0
            mBy = mmy[B] if B != 13 else 1.0
            gimgt = (g[0] * g[0] * iMA * mAx + g[1] * g[1] * iMA * mAy + g[2] * g[2] * iIA
                     + g[3] * g[3] * iMB * mBx + g[4] * g[4] * iMB * mBy + g[5] * g[5] * iIB)
            return [A, B, g[0], g[1], g[2], g[3], g[4], g[5], kind, gq, a, b, eps, 1.0 / (gimgt + eps), 0.0, mn, mx,
                    iMA, iIA, iMB, iIB, rest, first, 0, 0.0]

        for (_, c, first) in contacts:
            A, B, nx, ny, cax, cay, cbx, cby, gq, matA, matB, kind = c
            rest, mu, k, relax = CM[(matA, matB)] if (matA, matB) in CM else CM[(matB, matA)]
            a_s = 4.0 / (DT * (1.0 + 4.0 * relax))
            b_s = 4.0 * relax / (1.0 + 4.0 * relax)
            eps = 4.0 / (DT * DT * k * (1.0 + 4.0 * relax))
            g = (-nx, -ny, -(cax * ny - cay * nx), nx, ny, cbx * ny - cby * nx)
            if first and (-self._gw(g, A, B)) > 120.0 and len(self.hits) < 40:
                self.hits.append([math.floor(self.time * 100.0 + 0.5) / 100.0, kind, -self._gw(g, A, B)])
            eqs.append(mk(A, B, g, 0, gq, a_s, b_s, eps, 0.0, MAXF * DT, rest, first))
            tx, ty = ny, -nx
            if A == 13:
                red = m[B]
            elif B == 13:
                red = m[A]
            else:
                red = m[A] * m[B] / (m[A] + m[B])
            slip = mu * FRIC_G * red
            a_f = 4.0 / (DT * (1.0 + 4.0 * FRIC_RELAX))
            b_f = 4.0 * FRIC_RELAX / (1.0 + 4.0 * FRIC_RELAX)
            eps_f = 4.0 / (DT * DT * FRIC_K * (1.0 + 4.0 * FRIC_RELAX))
            gf = (-tx, -ty, -(cax * ty - cay * tx), tx, ty, cbx * ty - cby * tx)
            fr.append(mk(A, B, gf, 1, 0.0, a_f, b_f, eps_f, -slip * DT, slip * DT, 0.0, False))
        eqs.extend(fr)
        if self.magnet is not None:
            k = self.magnet
            dx, dy = x[BALL] - x[k], y[BALL] - y[k]
            ln = math.sqrt(dx * dx + dy * dy)
            if ln > 0.0:
                ux, uy = dx / ln, dy / ln
                a_c = 4.0 / (DT * (1.0 + 4.0 * CON_RELAX))
                b_c = 4.0 * CON_RELAX / (1.0 + 4.0 * CON_RELAX)
                eps_c = 4.0 / (DT * DT * CON_K * (1.0 + 4.0 * CON_RELAX))
                eqs.append(mk(k, BALL, (-ux, -uy, 0.0, ux, uy, 0.0), 2, ln - self.magnet_dist, a_c, b_c, eps_c,
                              -MAXF * DT, MAXF * DT, 0.0, False))
        for n, e in enumerate(eqs):
            e[23] = n
        return eqs

    def _gw(self, g, A, B) -> float:
        vx, vy, w = self.vx, self.vy, self.w
        vAx, vAy, wA = (vx[A], vy[A], w[A]) if A != 13 else (0.0, 0.0, 0.0)
        vBx, vBy, wB = (vx[B], vy[B], w[B]) if B != 13 else (0.0, 0.0, 0.0)
        return g[0] * vAx + g[1] * vAy + g[2] * wA + g[3] * vBx + g[4] * vBy + g[5] * wB

    # ---------- جزیره ها (islandSplit) و حل گروه به گروه ----------
    def _solve_islands(self, eqs: list) -> None:
        # union-find روی اسلات بدن ها، با اندازه؛ جزیرهٔ هر بدن پویا = ریشه، بدن ثابت = -۱
        idp = list(range(28))
        sz = [1] * 28

        def find(i):
            while i != idp[i]:
                idp[i] = idp[idp[i]]
                i = idp[i]
            return i
        for e in eqs:
            A, B = e[0], e[1]
            if A != 13 and B != 13:
                a, b = find(dyn_slot(A)), find(dyn_slot(B))
                if a != b:
                    if sz[a] < sz[b]:
                        idp[a] = b
                        sz[b] += sz[a]
                    else:
                        idp[b] = a
                        sz[a] += sz[b]
        island = {13: -1}
        for k in range(N):
            island[k] = find(dyn_slot(k))

        def key(e):
            ia = island[e[0]]
            return ia if ia > 0 else island[e[1]]
        eqs.sort(key=lambda e: (key(e), e[23]))
        n = len(eqs)
        s = 0
        while s < n:
            kk = key(eqs[s])
            t = s + 1
            while t < n and key(eqs[t]) == kk:
                t += 1
            self._solve(eqs[s:t])
            s = t

    # ---------- حل کنندهٔ گاوس-سایدل (GSSolver) برای یک گروه ----------
    def _solve(self, eqs: list) -> None:
        vlx = [0.0] * 14
        vly = [0.0] * 14
        wl = [0.0] * 14
        mmx, mmy = self.mmx, self.mmy
        vx, vy, w = self.vx, self.vy, self.w
        neq = len(eqs)
        tol2 = (TOL * neq) * (TOL * neq)
        for e in eqs:                 # B و invC از سرعت های همین لحظه (computeB)
            A, B = e[0], e[1]
            vAx, vAy, wA = (vx[A], vy[A], w[A]) if A != 13 else (0.0, 0.0, 0.0)
            vBx, vBy, wB = (vx[B], vy[B], w[B]) if B != 13 else (0.0, 0.0, 0.0)
            gw = e[2] * vAx + e[3] * vAy + e[4] * wA + e[5] * vBx + e[6] * vBy + e[7] * wB
            kind = e[8]
            if kind == 0:
                if e[22] and e[21] != 0.0:
                    e[24] = -(1.0 / e[11] * (1.0 + e[21]) * gw) * e[11]
                else:
                    e[24] = -e[9] * e[10] - gw * e[11]
            elif kind == 1:
                e[24] = -gw * e[11]
            else:
                e[24] = -e[9] * e[10] - gw * e[11]
            e[14] = 0.0
        for _ in range(ITER):
            tot = 0.0
            for e in eqs:
                A, B = e[0], e[1]
                lam = e[14]
                dl = e[13] * (e[24] - (e[2] * vlx[A] + e[3] * vly[A] + e[4] * wl[A] + e[5] * vlx[B] + e[6] * vly[B] + e[7] * wl[B]) - e[12] * lam)
                s = lam + dl
                if s < e[15]:
                    dl = e[15] - lam
                elif s > e[16]:
                    dl = e[16] - lam
                e[14] = lam + dl
                if A != 13:
                    vlx[A] += e[2] * e[17] * dl * mmx[A]
                    vly[A] += e[3] * e[17] * dl * mmy[A]
                    wl[A] += e[18] * e[4] * dl
                if B != 13:
                    vlx[B] += e[5] * e[19] * dl * mmx[B]
                    vly[B] += e[6] * e[19] * dl * mmy[B]
                    wl[B] += e[20] * e[7] * dl
                tot += abs(dl)
            if tot * tot < tol2:
                break
        for k in range(N):
            vx[k] += vlx[k]
            vy[k] += vly[k]
            w[k] += wl[k]

    def all_asleep(self) -> bool:
        return self.st.count(2) == N


def _pack(sim: Sim, frames: list, x0: list, ids_force: set) -> tuple:
    moved = set(ids_force)
    for q in range(N):
        if abs(sim.x[q] - x0[0][q]) > 1e-9 or abs(sim.y[q] - x0[1][q]) > 1e-9:
            moved.add(q)
    ids = sorted(moved)
    out = []
    for f in frames:
        row = []
        for q in ids:
            row.append(rd2(f[0][q]))
            row.append(rd2(f[1][q]))
        out.append(row)
    return ids, out


def run_shot(pos: list, k: int, ix: float, iy: float, team: int, pass_ok: bool) -> dict:
    """یک شوت: ضربهٔ (ix، iy) به مهرهٔ k؛ تا خوابیدن همه یا سقف گام ها اجرا می شود."""
    sim = Sim(pos, team, pass_ok)
    sim.set_impulse(k, ix, iy)        # مثل پلاتو: همه «خواب» اند و مهرهٔ شوت زننده با ضربه بیدار می شود (sleepTick)
    x0 = [sim.x[:], sim.y[:]]
    frames = [[sim.x[:], sim.y[:]]]
    steps = 0
    while True:
        sim.step()
        steps += 1
        if steps % FRAME_EVERY == 0:
            frames.append([sim.x[:], sim.y[:]])
        if sim.all_asleep() or steps >= MAX_STEPS:
            break
    sim.demagnetize(False)
    frames.append([sim.x[:], sim.y[:]])
    ids, out = _pack(sim, frames, x0, {k})
    return {"pos": [[sim.x[q], sim.y[q]] for q in range(N)], "ids": ids, "frames": out, "steps": steps,
            "dur": rd2(steps * DT), "goal": sim.goal, "shooter": sim.shooter,
            "receiver": sim.receiver, "hits": sim.hits, "sim": sim}


# ---------- کنترل بعد از پاس: گیرنده می رود پشت توپ، رو به دروازه (startControl / animateControl) ----------
def secure_dist(pos: list, k: int) -> bool:
    t = radius_of(k) + BALL_R * MAGNET_CTRL
    return t < pos[k][0] < W - t and GOAL_H + t < pos[k][1] < H - GOAL_H - t


def _pointing_to_goal(pos: list, k: int, team: int) -> bool:
    px, py = pos[k]
    bx, by = pos[BALL]
    dx, dy = bx - px, by - py
    ln = math.hypot(dx, dy)
    if ln == 0.0:
        return False
    ex, ey = px + dx / ln * H, py + dy / ln * H
    gx, gy = GOALS[team]
    x1, x2 = gx - GOAL_HW + POST_R, gx + GOAL_HW - POST_R
    rx, ry = ex - px, ey - py
    sx, sy = x2 - x1, 0.0
    den = rx * sy - ry * sx
    if den == 0.0:
        return False
    t = ((x1 - px) * sy - (gy - py) * sx) / den
    u = ((x1 - px) * ry - (gy - py) * rx) / den
    return t > 0.0 and t <= 1.0 and 0.0 <= u <= 1.0


def control_destination(pos: list, k: int, team: int):
    """جای مقصد گیرنده (یا فهرست نقطه ها وقتی باید دور توپ بچرخد)؛ None یعنی همین جا بماند."""
    if _pointing_to_goal(pos, k, team):
        return None
    px, py = pos[k]
    bx, by = pos[BALL]
    gx, gy = GOALS[team]
    r = radius_of(k) + BALL_R * MAGNET_CTRL
    n = math.atan2(gy - by, gx - bx) + math.pi
    if n < 0:
        n += 2 * math.pi
    ax, ay = bx + math.cos(n) * r, by + math.sin(n) * r
    s = math.atan2(py - by, px - bx)
    if s < 0:
        s += 2 * math.pi
    s = abs(n - s)
    s = abs(s - math.pi)
    rad = radius_of(k)
    wall = False
    if (bx - r - rad <= 0 and ax <= bx) or (bx + r + rad >= W and ax >= bx):
        wall = (py <= by) if team == 0 else (py >= by)      # صندلی ۰ = تیم ۱ در پلاتو
    if s < math.pi / 6 or wall:
        sg = (-1.0 if team == 0 else 1.0) if ax < W * 0.5 else (1.0 if team == 0 else -1.0)
        dist = math.hypot(px - bx, py - by)
        pts = [(ax, ay)]
        for q in range(1, 5):
            ang = n + sg * math.pi / 5 * q
            pts.insert(0, (bx + math.cos(ang) * dist, by + math.sin(ang) * dist))
        return pts
    return (ax, ay)


def run_control(pos: list, k: int, team: int) -> dict:
    """گیرندهٔ پاس با سرعت ۶۰۰→۵۰۰ دور توپ می چرخد تا پشت توپ و رو به دروازه قرار گیرد."""
    dest = control_destination(pos, k, team)
    if dest is None:             # همین حالا رو به دروازه است؛ جابه جایی لازم نیست
        return {"pos": [[float(p[0]), float(p[1])] for p in pos], "ids": [], "frames": [], "steps": 0, "dur": 0.0, "moved": False}
    sim = Sim(pos, team, False)
    sim.ctl = True
    sim.magnetize(k, True, secure_dist(pos, k))
    for q in range(12):               # startControl: همهٔ مهره ها (حتی گیرنده) دوباره می خوابند؛ توپ بیدار می ماند
        sim.sleep(q)
        sim.idle[q] = 0.0
    x0 = [sim.x[:], sim.y[:]]
    frames = [[sim.x[:], sim.y[:]]]
    cv = AUTO_V_MAX
    steps = 0
    done = False
    while steps < CONTROL_MAX_STEPS:
        if not done:
            e = dest if isinstance(dest, tuple) else dest[0]
            bx, by = sim.x[BALL], sim.y[BALL]
            ia = math.atan2(sim.y[k] - by, sim.x[k] - bx)
            ta = math.atan2(e[1] - by, e[0] - bx)
            if abs(ia - ta) > CONTROL_ANGLE_DIF:
                dx, dy = e[0] - sim.x[k], e[1] - sim.y[k]
                ln = math.hypot(dx, dy)
                if ln > 0.0:
                    sim.vx[k], sim.vy[k] = dx / ln * cv, dy / ln * cv
                    sim.wake(k)
            elif not isinstance(dest, tuple) and len(dest) > 1:
                dest = dest[1:]
            else:
                sim.vx[k] = sim.vy[k] = 0.0
                sim.damp[k] = 1.0          # setMagnetizedPlayerHampered(true)
                done = True
            cv = max(AUTO_V_MIN, cv - 1.0)
        sim.step()
        steps += 1
        if steps % FRAME_EVERY == 0:
            frames.append([sim.x[:], sim.y[:]])
        if done and sim.all_asleep():
            break
    sim.demagnetize(True)
    frames.append([sim.x[:], sim.y[:]])
    ids, out = _pack(sim, frames, x0, set())
    return {"pos": [[sim.x[q], sim.y[q]] for q in range(N)], "ids": ids, "frames": out, "steps": steps,
            "dur": rd2(steps * DT), "moved": bool(ids)}
