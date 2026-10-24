"""لشگر کاغذی (جنگ کاغذی دهه ۶۰): فقط در گروه، دو نفره، بدون ربات؛ فقط سمت سرور.

مثل بقیهٔ بازی ها هیچ I/O ندارد؛ وضعیت یک dict ساده است که JSON ذخیره می شود و هر اتفاق یک رویداد
شماره دار دارد. خط های مدادی (نقاشی) حجیم اند و جدا در جدول ink می مانند (service.py)؛ اینجا فقط
اسم لشگر، جای نیروها و شلیک هاست.

مرحله ها (phase):
  draw    هر کس اسم لشگرش را می گذارد، نیروهایش را روی نیمهٔ خودش می چیند و هر چه خواست می کشد.
          وقت ندارد؛ وقتی هر دو «آماده» زدند جنگ شروع می شود. تا آن موقع کسی نیمهٔ دیگری را نمی بیند.
          اگر یکی آماده بود و دیگری AUTO_AFTER ثانیه دست به برگه نزد، بقیهٔ نیروهایش خودکار چیده می شود
          و جنگ شروع می شود؛ اگر هیچ کس IDLE_END ثانیه کاری نکرد، بازی بی برنده تمام می شود.
  battle  نوبتی؛ هر شلیک TURN_S ثانیه. نقطه روی نیمهٔ خودت؛ برگه از خط وسط تا می شود و رد نقطه قرینه
          روی نیمهٔ حریف می افتد (با کمی خطا از کجی تا و لرزش دست). هر نیرویی که رد به آن بخورد خط
          می خورد. وقت تمام شد = نوبت می سوزد؛ MISS_MAX بار پشت هم = باخت.
  over    برنده کسی است که پرچم حریف را بزند یا همهٔ نیروهای دیگرش را خط بزند (یا حریف برود).

مختصات: هر نیمه W×H است؛ x از چپ صاحب همان نیمه، y فاصله از خط وسط (صفر کنار خط).
نیرو: {k: نوع، x، y، r: چرخش به درجه، dead}؛ شکل هر نوع همان شکل مینی اپ است (SHAPES با مقیاس UNIT_S).
"""
from __future__ import annotations

import math
import random
import re

SEATS = ("0", "1")
W, H = 1000, 700
KINDS = ("sol", "tank", "gun", "heli", "flag")
KIND_FA = {"sol": "سرباز", "tank": "تانک", "gun": "توپ", "heli": "هلیکوپتر", "flag": "پرچم"}
ARMIES = {11: {"sol": 6, "tank": 2, "gun": 1, "heli": 1, "flag": 1},
          18: {"sol": 10, "tank": 3, "gun": 2, "heli": 2, "flag": 1}}
UNIT_S = 2.8          # هر واحد شکل نیرو چند واحد برگه است
MARK_R = 12.0         # شعاع رد شلیک
EDGE = 0.6            # نیرو تا چه اندازه از شعاعش می تواند به لبهٔ برگه نزدیک شود
SPREAD = 0.62         # دو نیرو تا چه اندازه از جمع شعاعشان می توانند به هم نزدیک شوند (روی هم نمی افتند)
TURN_S = 60           # وقت هر شلیک
MISS_MAX = 3          # سوختن پشت سر هم نوبت = باخت
INTRO = 3.0           # کنار رفتن دفترها و سکه، پیش از اولین نوبت
SHOT_PAUSE = 3.2      # پخش تا شدن، فشار و باز شدن برگه پیش از نوبت بعد
TIMEOUT_PAUSE = 1.0
NUDGE_AFTER = 300.0   # service: یادآوری به کسی که حریفش آماده است و پنج دقیقه دست به برگه نزده
AUTO_AFTER = 600.0    # بعد از ده دقیقه: بقیهٔ نیروهایش خودکار چیده می شود و جنگ شروع می شود
IDLE_END = 1800.0     # هیچ کس آماده نیست و نیم ساعت کسی کاری نکرده: بازی بی برنده تمام می شود
TOUCH_EVERY = 30.0    # نقاشی (جدول ink) هر چند ثانیه یک بار «آخرین کار» بازیکن را تازه می کند
FOLD_MAX = 8.0        # کجی تا (درجه) که کلاینت از کشیدن انگشت اندازه می گیرد، حداکثر
FOLD_K = 0.5          # چه سهمی از کجی کشیدن واقعا خط تا را می چرخاند
JITTER = 5.0          # لرزش دست (انحراف معیار، واحد برگه)
NAME_MIN, NAME_MAX = 2, 20
MAX_EVENTS = 40

_rng = random.SystemRandom()

# شکل هر نیرو برای خوردن شلیک (همان طرح مینی اپ؛ واحد شکل، مرکز نیرو صفر): c دایره، s پاره خط ضخیم،
# p چندضلعی، e بیضی. ضخامت ها کمی بیشتر از خط مداد است تا شلیکی که به لبهٔ خط بخورد هم حساب شود
SHAPES = {
    "sol": (("c", 0, -9, 3.7), ("s", 0, -6, 0, 4, 1.7), ("s", -5, -2, 4, -3, 1.5), ("s", 0, 4, -4, 11, 1.5),
            ("s", 0, 4, 4, 11, 1.5), ("s", 3, -3, 8, -9, 1.4)),
    "tank": (("p", ((-21, 3), (21, 3), (18, 11.6), (-18, 11.6))),
             ("p", ((-16.6, 3), (-13.4, -3.6), (12.4, -3.6), (16.6, 3))),
             ("p", ((-7.6, -3), (-6.6, -9.4), (1, -10.7), (7.6, -9.4), (8.6, -3))),
             ("s", 6, -7, 23, -13, 1.6)),
    "gun": (("c", -6, 6, 5.7), ("c", 6, 6, 5.7), ("s", -7.5, 2.5, 16, -9, 2.7)),
    "heli": (("e", 0, 0, 12.7, 7.7), ("s", 11, -1, 29, -1, 2.3), ("s", 29, -7, 29, 5, 1.3), ("s", -17, -11, 17, -11, 1.4),
             ("s", 0, -11, 0, -7, 1.1), ("s", -8, 10, 8, 10, 1.3), ("s", -5, 7, -5, 10, 1.1), ("s", 5, 7, 5, 10, 1.1)),
    "flag": (("s", 0, 12, 0, -16, 1.3), ("p", ((0, -16.7), (17.7, -16.7), (17.7, -3.3), (0, -3.3)))),
}


def _reach(prims) -> float:  # noqa: ANN001
    out = 0.0
    for p in prims:
        if p[0] == "c":
            out = max(out, math.hypot(p[1], p[2]) + p[3])
        elif p[0] == "s":
            out = max(out, math.hypot(p[1], p[2]) + p[5], math.hypot(p[3], p[4]) + p[5])
        elif p[0] == "p":
            out = max(out, *(math.hypot(x, y) for x, y in p[1]))
        else:
            out = max(out, math.hypot(p[1], p[2]) + max(p[3], p[4]))
    return out


# دورترین نقطهٔ هر نیرو از مرکزش (واحد برگه): مرز برگه، روی هم نیفتادن، و فیلتر سریع پیش از آزمون دقیق
REACH = {k: _reach(v) * UNIT_S for k, v in SHAPES.items()}

# اسم های آماده برای کسی که اسمی نگذاشت (مینی اپ هم همین ها را پیشنهاد می دهد)
ARMY_A = ("لشگر", "گردان", "تیپ", "یگان", "گروهان")
ARMY_B = ("شیرها", "عقاب‌ها", "نیمکت آخر", "زنگ تفریح", "مداد سیاه‌ها", "پاک‌کن دورنگ", "کلاس پنجم", "تخته‌سیاه",
          "گچ‌های رنگی", "دفتر مشق", "جامدادی‌ها", "پلنگ‌ها", "ستاره‌ها", "ساندویچ کالباس")
_CTRL = re.compile(r"[\u0000-\u001f\u007f‎‏‪-‮⁦-⁩]")
_NAME_OK = re.compile(r"^[^\W_]+(?:[ ‌][^\W_]+)*$")
_LINKY = ("http", "www.", "t.me", ".com", ".ir", "@")
BAD_WORDS = {"کس", "کیر", "کون", "کونی", "جنده", "کسکش", "گوه", "حرومزاده", "fuck", "shit", "bitch", "porn", "sex",
             "dick", "kir", "kos", "kon", "koon", "jende"}


# ---------- هندسه ----------
def _seg_d(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _in_poly(px: float, py: float, pts) -> bool:  # noqa: ANN001
    inside = False
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % len(pts)]
        if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def touches(u: dict, mx: float, my: float, r: float = MARK_R) -> bool:
    """رد شلیک (دایرهٔ شعاع r در (mx, my) روی نیمهٔ صاحب نیرو) به شکل نیروی u می خورد؟

    چرخش مثل rotate(r) در SVG مینی اپ است (y رو به پایین، یعنی ساعتگرد روی صفحه)."""
    dx, dy = mx - u["x"], my - u["y"]
    if math.hypot(dx, dy) > REACH[u["k"]] + r:
        return False
    a = -math.radians(u.get("r") or 0)
    lx = (dx * math.cos(a) - dy * math.sin(a)) / UNIT_S
    ly = (dx * math.sin(a) + dy * math.cos(a)) / UNIT_S
    rr = r / UNIT_S
    for p in SHAPES[u["k"]]:
        if p[0] == "c" and math.hypot(lx - p[1], ly - p[2]) <= p[3] + rr:
            return True
        if p[0] == "s" and _seg_d(lx, ly, p[1], p[2], p[3], p[4]) <= p[5] + rr:
            return True
        if p[0] == "p":
            pts = p[1]
            if _in_poly(lx, ly, pts) or any(_seg_d(lx, ly, *pts[i], *pts[(i + 1) % len(pts)]) <= rr for i in range(len(pts))):
                return True
        if p[0] == "e" and ((lx - p[1]) / (p[3] + rr)) ** 2 + ((ly - p[2]) / (p[4] + rr)) ** 2 <= 1:
            return True
    return False


def landing(x: float, y: float, a: float, rng: random.Random | None = None) -> tuple[float, float]:
    """جای رد نقطهٔ (x, y) نیمهٔ تیرانداز روی نیمهٔ حریف (مختصات خود حریف) بعد از تا شدن برگه.

    قاب تیرانداز: خط وسط محور x و نیمهٔ او پایین (y مثبت). خط تا از وسط خط وسط می گذرد و به اندازهٔ
    a×FOLD_K درجه کج است؛ قرینه نسبت به خط کج یعنی قرینهٔ ساده که ۲θ دور وسط خط چرخیده. بعد لرزش دست.
    حریف روبه رو نشسته: x او برعکس x تیرانداز است و y او فاصله از خط به سمت خودش."""
    r = rng or _rng
    th = math.radians(max(-FOLD_MAX, min(FOLD_MAX, a)) * FOLD_K)
    ux, uy = x - W / 2, -y
    c2, s2 = math.cos(2 * th), math.sin(2 * th)
    px, py = W / 2 + ux * c2 - uy * s2, ux * s2 + uy * c2
    lim = JITTER * 2.5
    px += max(-lim, min(lim, r.gauss(0, JITTER)))
    py += max(-lim, min(lim, r.gauss(0, JITTER)))
    return W - px, -py


# ---------- اسم لشگر ----------
def clean_name(raw) -> str:  # noqa: ANN001
    """یک خط، بدون نویسهٔ کنترلی و جهت دهی؛ فاصله ها یکی."""
    return " ".join(_CTRL.sub(" ", str(raw or "")).split())[:NAME_MAX + 10].strip("‌ ")


def name_problem(s: str) -> str | None:
    if len(s) < NAME_MIN:
        return "army_short"
    if len(s) > NAME_MAX:
        return "army_long"
    low = s.lower()
    if any(b in low for b in _LINKY) or not _NAME_OK.match(s):
        return "army_chars"
    if set(re.split(r"[ ‌]+", low)) & BAD_WORDS:
        return "army_bad"
    return None


def random_army(taken: str = "", rng: random.Random | None = None) -> str:
    r = rng or _rng
    for _ in range(30):
        n = f"{r.choice(ARMY_A)} {r.choice(ARMY_B)}"
        if n != taken:
            return n
    return "لشگر بی‌نام"


# ---------- وضعیت ----------
def new_state(seats: list[dict], now: float, army: int = 11) -> dict:
    """seats: [{color: "0" یا "1"، uid، name، av، pic}] فقط آدم (این بازی ربات ندارد)."""
    size = army if army in ARMIES else 11
    ps = {}
    for s in seats:
        ps[s["color"]] = {"uid": s.get("uid"), "name": s["name"], "av": s.get("av", 1), "pic": s.get("pic", ""),
                          "bot": False, "out": False, "army": "", "units": [], "ready": False, "ready_at": 0.0,
                          "last": now, "misses": 0, "shots": 0, "hits": 0}
    st = {"game": "lashgar", "order": [c for c in SEATS if c in ps], "players": ps, "size": size,
          "phase": "draw", "turn": 0, "shots": [], "next_at": now, "deadline": 0.0, "turn_s": TURN_S, "turn_id": 0,
          "seq": 0, "events": [], "over": False, "winner": None, "why": "", "started": now, "battle_at": 0.0,
          "stake": False}
    _event(st, t="draw")
    return st


def _event(st: dict, **e) -> None:
    st["seq"] += 1
    e["seq"] = st["seq"]
    st["events"].append(e)
    if len(st["events"]) > MAX_EVENTS:
        st["events"] = st["events"][-MAX_EVENTS:]


def _foe(st: dict, c: str) -> str:
    return next(x for x in st["order"] if x != c)


def current(st: dict) -> str | None:
    return st["order"][st["turn"]] if st["phase"] == "battle" and not st["over"] else None


def _drawing(st: dict, c: str) -> str | None:
    if st["over"]:
        return "over"
    p = st["players"].get(c)
    if not p or p["out"]:
        return "not_playing"
    if st["phase"] != "draw":
        return "not_draw"
    if p["ready"]:
        return "is_ready"
    return None


def set_army(st: dict, c: str, raw, now: float) -> str | None:  # noqa: ANN001
    err = _drawing(st, c)
    if err:
        return err
    n = clean_name(raw)
    bad = name_problem(n)
    if bad:
        return bad
    if n == st["players"][_foe(st, c)]["army"]:
        return "army_taken"
    p = st["players"][c]
    if p["army"] != n:
        p["army"] = n
        _event(st, t="army", c=c)
    p["last"] = now
    return None


def check_units(units, size: int) -> tuple[list | None, str | None]:  # noqa: ANN001
    """فهرست نیروهای یک نفر از کلاینت: (نیروهای پاک شده، کد خطا). کمتر از کل ارتش هم قبول است."""
    army = ARMIES.get(size) or ARMIES[11]
    if not isinstance(units, list) or len(units) > sum(army.values()):
        return None, "bad_units"
    left = dict(army)
    out = []
    for u in units:
        if not isinstance(u, dict) or u.get("k") not in left:
            return None, "bad_units"
        try:
            x, y, r = float(u.get("x")), float(u.get("y")), float(u.get("r") or 0)
        except (TypeError, ValueError):
            return None, "bad_units"
        if not all(math.isfinite(v) for v in (x, y, r)):
            return None, "bad_units"
        k = u["k"]
        if left[k] <= 0:
            return None, "too_many"
        left[k] -= 1
        m = REACH[k] * EDGE
        if not (m <= x <= W - m and m <= y <= H - m):
            return None, "unit_out"
        out.append({"k": k, "x": round(x, 1), "y": round(y, 1), "r": int(round(r)) % 360})
    for i in range(len(out)):
        for j in range(i):
            a, b = out[i], out[j]
            if math.hypot(a["x"] - b["x"], a["y"] - b["y"]) < (REACH[a["k"]] + REACH[b["k"]]) * SPREAD:
                return None, "unit_overlap"
    return out, None


def set_units(st: dict, c: str, units, now: float) -> str | None:  # noqa: ANN001
    err = _drawing(st, c)
    if err:
        return err
    out, err = check_units(units, st["size"])
    if err:
        return err
    p = st["players"][c]
    p["units"], p["last"] = out, now
    return None


def touch(st: dict, c: str, now: float) -> bool:
    """بازیکن دارد نقاشی می کند (خط تازه در جدول ink): آخرین کارش هر TOUCH_EVERY ثانیه یک بار تازه می شود."""
    p = st["players"].get(c)
    if not p or st["phase"] != "draw" or now - p["last"] < TOUCH_EVERY:
        return False
    p["last"] = now
    return True


def _full(st: dict, c: str) -> bool:
    return len(st["players"][c]["units"]) == sum(ARMIES[st["size"]].values())


def ready(st: dict, c: str, now: float) -> str | None:
    """«آماده‌ام»: اسم لشگر و همهٔ نیروها لازم است؛ وقتی هر دو آماده شدند جنگ شروع می شود."""
    err = _drawing(st, c)
    if err:
        return None if err == "is_ready" else err
    p = st["players"][c]
    if not p["army"]:
        return "need_army"
    if not _full(st, c):
        return "need_units"
    p["ready"], p["ready_at"], p["last"] = True, now, now
    _event(st, t="ready", c=c)
    if all(st["players"][x]["ready"] for x in st["order"]):
        _battle(st, now)
    return None


def unready(st: dict, c: str, now: float) -> str | None:
    """تا وقتی حریف آماده نشده، می شود از «آماده» برگشت و باز چید و کشید."""
    if st["over"] or st["phase"] != "draw" or c not in st["players"]:
        return "not_draw"
    p = st["players"][c]
    if p["ready"]:
        p["ready"], p["last"] = False, now
        _event(st, t="unready", c=c)
    return None


def _autofill(st: dict, c: str, rng: random.Random | None = None) -> None:
    """اسم و نیروهایی که کم است برای کسی که خیلی منتظرش ماندیم (بزرگ ها اول، جای خالی تصادفی)."""
    r = rng or _rng
    p = st["players"][c]
    if not p["army"]:
        p["army"] = random_army(st["players"][_foe(st, c)]["army"], r)
    have = {k: 0 for k in KINDS}
    for u in p["units"]:
        have[u["k"]] += 1
    need = [k for k, n in ARMIES[st["size"]].items() for _ in range(max(0, n - have[k]))]
    for k in sorted(need, key=lambda x: -REACH[x]):
        m = REACH[k] * EDGE
        u = None
        for _ in range(500):
            u = {"k": k, "x": round(r.uniform(m, W - m), 1), "y": round(r.uniform(m, H - m), 1), "r": 0}
            if all(math.hypot(u["x"] - v["x"], u["y"] - v["y"]) >= (REACH[k] + REACH[v["k"]]) * SPREAD for v in p["units"]):
                break
        p["units"].append(u)


def _battle(st: dict, now: float) -> None:
    st["phase"], st["battle_at"] = "battle", now
    for c in st["order"]:
        for u in st["players"][c]["units"]:
            u["dead"] = False
    st["turn"] = _rng.randrange(len(st["order"]))
    _event(st, t="battle", first=st["order"][st["turn"]])
    _wait(st, now, INTRO)


def _wait(st: dict, now: float, pause: float) -> None:
    st["turn_id"] = st["seq"]
    st["next_at"] = now + pause
    st["deadline"] = st["next_at"] + st["turn_s"]


def _next(st: dict, now: float, pause: float = SHOT_PAUSE) -> None:
    st["turn"] = 1 - st["turn"]
    _event(st, t="turn", c=st["order"][st["turn"]])
    _wait(st, now, pause)


def _check_turn(st: dict, c: str, now: float) -> str | None:
    if st["over"]:
        return "over"
    if st["phase"] != "battle":
        return "not_battle"
    if current(st) != c:
        return "not_your_turn"
    if now < st["next_at"] - 0.3:
        return "not_ready"
    return None


def shoot(st: dict, c: str, x, y, a, now: float, rng: random.Random | None = None) -> str | None:  # noqa: ANN001
    """شلیک: (x, y) نقطه روی نیمهٔ خود تیرانداز، a کجی کشیدن انگشت هنگام تا کردن (درجه)."""
    err = _check_turn(st, c, now)
    if err:
        return err
    try:
        x, y, a = float(x), float(y), float(a or 0)
    except (TypeError, ValueError):
        return "bad_shot"
    if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= W and 0 <= y <= H):
        return "bad_shot"
    a = max(-FOLD_MAX, min(FOLD_MAX, a)) if math.isfinite(a) else 0.0
    tx, ty = landing(x, y, a, rng)
    foe = _foe(st, c)
    fp, me = st["players"][foe], st["players"][c]
    on = 0 <= tx <= W and 0 <= ty <= H
    hit = [i for i, u in enumerate(fp["units"]) if not u.get("dead") and touches(u, tx, ty)] if on else []
    for i in hit:
        fp["units"][i]["dead"] = True
    me["shots"] += 1
    me["hits"] += len(hit)
    me["misses"] = 0
    shot = {"n": len(st["shots"]) + 1, "by": c, "x": round(tx, 1), "y": round(ty, 1), "hit": hit, "a": round(a, 1),
            "off": not on, "ax": round(x, 1), "ay": round(y, 1)}
    st["shots"].append(shot)
    _event(st, t="shot", **shot)
    if any(fp["units"][i]["k"] == "flag" for i in hit):
        _finish(st, c, "flag")
    elif all(u.get("dead") for u in fp["units"] if u["k"] != "flag"):
        _finish(st, c, "army")
    else:
        _next(st, now)
    return None


def _finish(st: dict, w: str | None, why: str) -> None:
    st["over"], st["winner"], st["why"], st["phase"] = True, w, why, "over"
    _event(st, t="win" if w is not None else "end", c=w, why=why)


def leave(st: dict, c: str, now: float, why: str = "left") -> None:
    """خروج یا جریمهٔ غیبت: حریف برنده است."""
    p = st["players"].get(c)
    if not p or p["out"] or st["over"]:
        return
    p["out"] = True
    _event(st, t="leave", c=c, why=why)
    _finish(st, _foe(st, c), why)


def tick(st: dict, now: float) -> bool:
    if st["over"]:
        return False
    if st["phase"] == "draw":
        return _draw_tick(st, now)
    changed = False
    for _ in range(4):
        if st["over"] or now < st["deadline"]:
            break
        c = current(st)
        p = st["players"][c]
        p["misses"] += 1
        _event(st, t="timeout", c=c, n=p["misses"])
        changed = True
        if p["misses"] >= MISS_MAX:
            leave(st, c, now, "timeout")
            break
        _next(st, now, TIMEOUT_PAUSE)
    return changed


def _draw_tick(st: dict, now: float) -> bool:
    ps = [st["players"][c] for c in st["order"]]
    done = [p for p in ps if p["ready"]]
    if len(done) == 1:
        idle = next(c for c in st["order"] if not st["players"][c]["ready"])
        q = st["players"][idle]
        if now - max(q["last"], done[0]["ready_at"]) >= AUTO_AFTER:
            _autofill(st, idle)
            q["ready"], q["ready_at"] = True, now
            _event(st, t="auto", c=idle)
            _battle(st, now)
            return True
        return False
    if not done and all(now - p["last"] >= IDLE_END for p in ps):
        _finish(st, None, "idle")
        return True
    return False


def nudge_due(st: dict, now: float) -> str | None:
    """کسی که حریفش آماده است و NUDGE_AFTER ثانیه دست به برگه نزده (service یک بار خبرش می کند)."""
    if st["over"] or st["phase"] != "draw":
        return None
    ps = st["players"]
    done = [c for c in st["order"] if ps[c]["ready"]]
    if len(done) != 1:
        return None
    idle = next(c for c in st["order"] if not ps[c]["ready"])
    return idle if now - max(ps[idle]["last"], ps[done[0]]["ready_at"]) >= NUDGE_AFTER else None


def human_acted(st: dict, c: str) -> None:
    st["players"][c]["misses"] = 0


def winners(st: dict) -> set[str]:
    return {st["winner"]} if st.get("winner") else set()


def alive(p: dict) -> int:
    return sum(1 for u in p["units"] if not u.get("dead"))


# ---------- نمای هر بازیکن ----------
def view(st: dict, me: str | None, since: int, now: float) -> dict:
    """هر کس تا شروع جنگ فقط نیمهٔ خودش را دارد (از حریف فقط اسم لشگر، آمادگی و تعداد نیروی چیده)."""
    reveal = st["phase"] != "draw"
    cur = current(st)
    players = {}
    for c, p in st["players"].items():
        mine = c == me
        players[c] = {"name": p["name"], "av": p["av"], "pic": p.get("pic", ""), "bot": False, "out": p["out"], "me": mine,
                      "army": p["army"], "ready": p["ready"], "placed": len(p["units"]), "alive": alive(p),
                      "shots": p["shots"], "hits": p["hits"], "misses": p["misses"],
                      # تماشاگر (me=None) از همان چیدن هر دو نیمه را می بیند؛ بازیکن ها تا شروع جنگ فقط نیمهٔ خود را
                      "units": [dict(u) for u in p["units"]] if (mine or reveal or me is None) else None}
    return {
        "order": list(st["order"]), "players": players, "me": me if me in st["players"] else None,
        "size": st["size"], "army": dict(ARMIES[st["size"]]), "w": W, "h": H, "unit_s": UNIT_S, "mark_r": MARK_R,
        "phase": st["phase"], "turn": cur,
        "ready_ms": max(0, int((st["next_at"] - now) * 1000)) if cur else 0,
        "deadline_ms": max(0, int((st["deadline"] - now) * 1000)) if cur else 0,
        "turn_ms": st["turn_s"] * 1000,
        "shots": list(st["shots"]) if reveal else [],
        "events": [e for e in st["events"] if e["seq"] > since],
        "seq": st["seq"], "over": st["over"], "winner": st["winner"], "why": st["why"],
        "started": st["started"], "battle_at": st["battle_at"],
    }
