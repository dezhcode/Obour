"""اسم‌فامیل (فقط در گروه): همه هم‌زمان برای یک حرف ستون‌ها را پر می‌کنند؛ داور هوش مصنوعی عبور است.

دور به دور (phase):
  letter  حرف دور. دور اول: تا همه برگشان را باز کنند (حداکثر GATHER ثانیه) و هوش مصنوعی حرف همهٔ
          دورها را بدهد (وگرنه تصادفی)؛ بعد REVEAL ثانیه نمایش حرف. حرف فقط همان REVEAL ثانیهٔ آخر
          دیده می‌شود تا کسی زودتر از بقیه فکر نکند
  write   نوشتن تا پایان وقت؛ کسی که برگش کامل است می‌تواند «استپ» بزند، یا برگش را زودتر تحویل دهد
  stop    بعد از استپ بقیه STOP_GRACE ثانیه وقت دارند؛ اگر از وقت نوشتن کمتر از این مانده باشد، همان باقی مانده
  judge   داوری: service جواب‌ها را به داور (esmfamil_ai) می‌دهد؛ اگر تا JUDGE_MAX حکم نیامد، داوری ساده
  show    برگ دور با امتیازها؛ صاحب جواب ردشده می‌تواند اعتراض کند و بقیه رأی می‌دهند؛ «دور بعد» یا پایان وقت
  over    پایان؛ بیشترین جمع برنده است (مساوی = چند برنده)
امتیاز هر خانه: جواب درست تکی ۱۰، درست تکراری ۵، ردشده یا خالی ۰.
این فایل فقط قواعد است و به شبکه دست نمی‌زند: برای داور ورودی می‌سازد و حکمش را اعمال می‌کند.
"""
from __future__ import annotations

import random
import re

SEATS = tuple(str(i) for i in range(10))
MAX_PLAYERS = 10
MIN_PLAYERS = 2
COLS = (("name", "اسم"), ("family", "فامیل"), ("city", "شهر"), ("country", "کشور"),
        ("food", "غذا"), ("animal", "حیوان"), ("fruit", "میوه"), ("thing", "اشیا"), ("color", "رنگ"))
COL_FA = dict(COLS)
# حرف‌های بازی؛ ث، ذ، ض، ظ، ژ، غ و ء کنار گذاشته شده‌اند (برای بیشتر ستون‌ها جوابی ندارند)
LETTERS = tuple("ابپتجچحخدرزسشصطعفقکگلمنوهی")
ROUNDS = (1, 3, 5)
SECS = (180, 300, 480)    # وقت هر دور: ۳، ۵ یا ۸ دقیقه
GATHER = 20.0
REVEAL = 3.5
STOP_GRACE = 20.0
JUDGE_MAX = 40.0
SHOW = 25.0
APPEAL_EXTRA = 15.0
LATE = 1.5          # برگی که تا این مدت بعد از پایان وقت برسد (تأخیر شبکه) هنوز پذیرفته می‌شود
MAX_LEN = 32
MAX_EVENTS = 30
UNIQUE, SHARED = 10, 5

_MAP = str.maketrans({"ي": "ی", "ى": "ی", "ئ": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه",
                      "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ؤ": "و"})
_DROP = re.compile(r"[ً-ٰٟـ‌‍‎‏\s\-_.,،؛:!?؟\"'«»()]")
_CTRL = re.compile(r"[\u0000-\u001f\u007f‪-‮⁦-⁩]")


def clean(s, n: int = MAX_LEN) -> str:  # noqa: ANN001
    """یک خط، بدون نویسهٔ کنترلی و جهت‌دهی، حداکثر n نویسه."""
    return " ".join(_CTRL.sub(" ", str(s or "")).split())[:n]


def norm(s) -> str:  # noqa: ANN001
    """شکل مقایسه: عربی به فارسی، آ = ا، بدون اعراب، فاصله و نیم‌فاصله ("باقالی پلو" = "باقالی‌پلو")."""
    return _DROP.sub("", clean(s, 64).translate(_MAP)).lower()


def starts(s, letter: str) -> bool:  # noqa: ANN001
    k = norm(s)
    return bool(k) and k[0] == norm(letter)[:1]


def active(st: dict) -> list[str]:
    return [c for c in st["order"] if not st["players"][c]["out"]]


def new_state(seats: list[dict], now: float, rounds: int = 3, secs: int = 300) -> dict:
    """seats: [{color, uid, name, av, pic}] فقط آدم (این بازی ربات ندارد)."""
    players = {s["color"]: {"uid": s.get("uid"), "name": s["name"], "av": s.get("av", 1), "pic": s.get("pic", ""),
                            "bot": False, "out": False} for s in seats}
    order = [c for c in SEATS if c in players]
    return {
        "game": "esmfamil", "order": order, "players": players, "cols": [k for k, _ in COLS],
        "rounds_n": max(1, min(int(rounds), max(ROUNDS))), "secs": max(30, min(int(secs), max(SECS))),
        "round": 0, "phase": "letter", "letters": [], "lines": [],
        "sheets": {}, "done": [], "stopper": None, "ready": [], "appeals": {}, "here": [],
        "deadline": now + GATHER, "phase_at": now, "lease": None,
        "rounds": [], "totals": {c: 0 for c in order},
        "seq": 0, "events": [], "over": False, "winner": None, "winners": [], "started": now, "stake": False,
    }


def _event(st: dict, **e) -> None:
    st["seq"] += 1
    e["seq"] = st["seq"]
    st["events"].append(e)
    if len(st["events"]) > MAX_EVENTS:
        st["events"] = st["events"][-MAX_EVENTS:]


def letter_of(st: dict) -> str | None:
    return st["letters"][st["round"]] if len(st["letters"]) > st["round"] else None


# ---------- حرف‌ها ----------
def set_letters(st: dict, letters, lines, now: float) -> bool:  # noqa: ANN001
    """حرف همهٔ دورها (از داور یا تصادفی). حرف تکراری یا بیرون از LETTERS کنار می‌رود و جایش تصادفی می‌آید."""
    if st["over"] or st["phase"] != "letter" or st["letters"]:
        return False
    out, said = [], []
    for i, x in enumerate(letters or []):
        l = norm(x)[:1]
        if l in LETTERS and l not in out:
            out.append(l)
            said.append(clean((lines or [""] * (i + 1))[i] if i < len(lines or []) else "", 90))
        if len(out) == st["rounds_n"]:
            break
    rest = [l for l in LETTERS if l not in out]
    random.shuffle(rest)
    while len(out) < st["rounds_n"]:
        out.append(rest.pop())
        said.append("")
    st["letters"], st["lines"] = out, said
    st["deadline"] = now + REVEAL if _all_here(st) else max(st["deadline"], now + REVEAL)
    return True


def _all_here(st: dict) -> bool:
    return all(c in st["here"] for c in active(st))


def arrive(st: dict, c: str, now: float) -> bool:
    """بازیکن صفحهٔ برگ را باز کرد؛ وقتی همه آمدند و حرف آماده است، دور اول زودتر شروع می‌شود."""
    if st["over"] or c not in st["players"] or c in st["here"]:
        return False
    st["here"].append(c)
    _go_early(st, now)
    return True


def _go_early(st: dict, now: float) -> None:
    if st["phase"] == "letter" and st["letters"] and _all_here(st):
        st["deadline"] = min(st["deadline"], now + REVEAL)


def letter_shown(st: dict, now: float) -> bool:
    return st["phase"] != "letter" or (bool(st["letters"]) and now >= st["deadline"] - REVEAL - 0.05)


# ---------- نوشتن ----------
def _start_write(st: dict, now: float) -> None:
    st["phase"], st["phase_at"], st["deadline"] = "write", now, now + st["secs"]
    st["sheets"] = {c: {} for c in active(st)}
    st["done"], st["stopper"] = [], None
    _event(st, t="write", r=st["round"])


def _to_judge(st: dict, now: float) -> None:
    st["phase"], st["phase_at"], st["deadline"], st["lease"] = "judge", now, now + JUDGE_MAX, None
    _event(st, t="judge", r=st["round"])


def _writing(st: dict, c: str, now: float) -> str | None:
    if st["over"] or c not in st["players"] or st["players"][c]["out"]:
        return "not_playing"
    if st["phase"] not in ("write", "stop") or now > st["deadline"] + LATE:
        return "closed"
    if c in st["done"]:
        return "submitted"
    return None


def answer(st: dict, c: str, sheet, now: float) -> str | None:  # noqa: ANN001
    """ذخیرهٔ برگ (همه یا بخشی از ستون‌ها)؛ مقدار خالی یعنی پاک کردن آن خانه."""
    err = _writing(st, c, now)
    if err:
        return err
    if not isinstance(sheet, dict):
        return "bad_sheet"
    mine = st["sheets"].setdefault(c, {})
    for k in st["cols"]:
        if k in sheet:
            v = clean(sheet[k])
            if v:
                mine[k] = v
            else:
                mine.pop(k, None)
    return None


def _all_done(st: dict, now: float) -> None:
    if all(x in st["done"] for x in active(st)):
        _to_judge(st, now)


def submit(st: dict, c: str, now: float) -> str | None:
    """تحویل زودتر برگ؛ وقتی همه تحویل دادند داوری بی‌معطلی شروع می‌شود."""
    err = _writing(st, c, now)
    if err:
        return None if err == "submitted" else err
    st["done"].append(c)
    _event(st, t="done", c=c)
    _all_done(st, now)
    return None


def stop(st: dict, c: str, now: float) -> str | None:
    """«استپ!»: فقط با برگ کامل؛ بقیه STOP_GRACE ثانیه وقت دارند (نه بیشتر از وقتی که از نوشتن مانده)."""
    err = _writing(st, c, now)
    if err:
        return err
    if st["phase"] != "write":
        return "closed"
    sheet = st["sheets"].get(c, {})
    if any(not sheet.get(k) for k in st["cols"]):
        return "sheet_not_full"
    st["stopper"] = c
    st["done"].append(c)
    st["phase"], st["phase_at"] = "stop", now
    st["deadline"] = min(st["deadline"], now + STOP_GRACE)
    _event(st, t="stop", c=c)
    _all_done(st, now)
    return None


# ---------- داوری ----------
def judge_input(st: dict) -> dict:
    """{ستون: [جواب‌های متفاوت هر ستون که با حرف دور شروع می‌شوند]}: همین‌ها به داور می‌روند."""
    L = letter_of(st) or ""
    out = {}
    for k in st["cols"]:
        seen: dict = {}
        for c in active(st):
            a = st["sheets"].get(c, {}).get(k, "")
            if a and starts(a, L):
                seen.setdefault(norm(a), a)
        out[k] = list(seen.values())
    return out


def simple_verdicts(st: dict) -> dict:
    """داوری بی‌هوش مصنوعی: هر جوابی که با حرف شروع شود و دست کم دو حرف باشد قبول است."""
    return {k: {norm(a): {"ok": len(norm(a)) >= 2, "why": "" if len(norm(a)) >= 2 else "خیلی کوتاهه", "same": norm(a)}
                for a in answers} for k, answers in judge_input(st).items()}


def _score(rec: dict, cols: list[str]) -> None:
    """امتیاز خانه‌ها: درست تکی ۱۰، درست تکراری (همان key) ۵، بقیه ۰."""
    cells = rec["cells"]
    rec["scores"] = {c: 0 for c in cells}
    for k in cols:
        groups: dict = {}
        for c, row in cells.items():
            if row[k]["ok"]:
                groups.setdefault(row[k]["key"], []).append(c)
        for c, row in cells.items():
            cell = row[k]
            cell["s"] = (UNIQUE if len(groups[cell["key"]]) == 1 else SHARED) if cell["ok"] else 0
            rec["scores"][c] += cell["s"]


def _totals(st: dict) -> None:
    st["totals"] = {c: sum(r["scores"].get(c, 0) for r in st["rounds"]) for c in st["order"]}


def apply_judgement(st: dict, verdicts: dict | None, by: str, now: float, rnd: int) -> bool:
    """حکم داور برای دور rnd (اگر هنوز همان دور در داوری باشد). verdicts: {ستون: {norm(جواب): {ok, why, same}}}."""
    if st["over"] or st["phase"] != "judge" or st["round"] != rnd:
        return False
    verdicts = verdicts or {}
    simple = simple_verdicts(st)
    L = letter_of(st) or ""
    cells = {}
    for c in active(st):
        row = {}
        for k in st["cols"]:
            a = st["sheets"].get(c, {}).get(k, "")
            if not a:
                row[k] = {"a": "", "ok": False, "s": 0, "why": "", "key": ""}
            elif not starts(a, L):
                row[k] = {"a": a, "ok": False, "s": 0, "why": f"با «{L}» شروع نمی‌شه", "key": "", "fix": True}
            else:
                v = verdicts.get(k, {}).get(norm(a)) or simple[k][norm(a)]
                ok = bool(v.get("ok"))
                same = norm(v.get("same") or "") if ok else ""
                row[k] = {"a": a, "ok": ok, "s": 0, "why": "" if ok else clean(v.get("why") or "", 60),
                          "key": same if same and starts(same, L) else norm(a) if ok else ""}
        cells[c] = row
    rec = {"letter": L, "line": st["lines"][rnd] if rnd < len(st["lines"]) else "", "by": by,
           "cells": cells, "stopper": st["stopper"]}
    _score(rec, st["cols"])
    st["rounds"].append(rec)
    _totals(st)
    st["phase"], st["phase_at"], st["deadline"] = "show", now, now + SHOW
    st["ready"], st["appeals"], st["lease"] = [], {}, None
    _event(st, t="scored", r=rnd, by=by)
    return True


# ---------- اعتراض و رأی ----------
def appeal(st: dict, c: str, col: str, now: float) -> str | None:
    """صاحب جواب ردشده (نه جواب خالی یا با حرف دیگر) اعتراض می‌کند؛ بقیهٔ بازیکن‌ها رأی می‌دهند."""
    if st["over"] or st["phase"] != "show" or not st["rounds"]:
        return "closed"
    cell = st["rounds"][-1]["cells"].get(c, {}).get(col)
    if not cell or cell["ok"] or not cell["a"] or cell.get("fix"):
        return "no_appeal"
    key = f"{c}:{col}"
    if key in st["appeals"]:
        return "appealed"
    if not [x for x in active(st) if x != c]:
        return "no_appeal"
    st["appeals"][key] = {"c": c, "col": col, "yes": [], "no": [], "res": None}
    st["deadline"] = max(st["deadline"], now + APPEAL_EXTRA)
    if c in st["ready"]:
        st["ready"].remove(c)
    _event(st, t="appeal", c=c, col=col)
    return None


def _resolve(st: dict, key: str) -> None:
    ap = st["appeals"][key]
    if ap["res"] is not None:
        return
    ap["res"] = len(ap["yes"]) > len(ap["no"])
    if ap["res"]:
        rec = st["rounds"][-1]
        cell = rec["cells"][ap["c"]][ap["col"]]
        cell.update(ok=True, key=norm(cell["a"]), why="", appealed=True)
        _score(rec, st["cols"])
        _totals(st)
    _event(st, t="appealed", key=key, ok=ap["res"])


def vote(st: dict, c: str, key: str, yes: bool, now: float) -> str | None:
    if st["over"] or st["phase"] != "show":
        return "closed"
    ap = st["appeals"].get(key)
    if not ap or ap["res"] is not None:
        return "no_appeal"
    if c == ap["c"] or c not in active(st):
        return "no_vote"
    for side in ("yes", "no"):
        if c in ap[side]:
            ap[side].remove(c)
    ap["yes" if yes else "no"].append(c)
    if all(x in ap["yes"] or x in ap["no"] for x in active(st) if x != ap["c"]):
        _resolve(st, key)
    return None


def _open_appeals(st: dict) -> bool:
    return any(ap["res"] is None for ap in st["appeals"].values())


def ready(st: dict, c: str, now: float) -> str | None:
    """«دور بعد»؛ وقتی همه آماده‌اند و رأی‌گیری بازی نمانده، زودتر می‌رویم."""
    if st["over"] or st["phase"] != "show" or c not in active(st):
        return "closed"
    if c not in st["ready"]:
        st["ready"].append(c)
    if all(x in st["ready"] for x in active(st)) and not _open_appeals(st):
        _next_round(st, now)
    return None


def _next_round(st: dict, now: float) -> None:
    for key in list(st["appeals"]):
        _resolve(st, key)
    if st["round"] + 1 >= st["rounds_n"]:
        _finish(st)
        return
    st["round"] += 1
    st["phase"], st["phase_at"], st["deadline"] = "letter", now, now + REVEAL
    st["appeals"], st["ready"], st["sheets"], st["done"], st["stopper"] = {}, [], {}, [], None
    _event(st, t="letter", r=st["round"])


def _finish(st: dict) -> None:
    st["phase"], st["over"] = "over", True
    act = active(st)
    best = max((st["totals"].get(c, 0) for c in act), default=0)
    st["winners"] = [c for c in act if st["totals"].get(c, 0) == best] if best > 0 else []
    st["winner"] = st["winners"][0] if st["winners"] else None
    _event(st, t="win", c=st["winners"])


def leave(st: dict, c: str, now: float, why: str = "left") -> None:
    if st["over"] or c not in st["players"] or st["players"][c]["out"]:
        return
    st["players"][c]["out"] = True
    for lst in (st["done"], st["ready"]):
        if c in lst:
            lst.remove(c)
    _event(st, t="leave", c=c, why=why)
    if not active(st):
        _finish(st)
    elif st["phase"] == "letter":
        _go_early(st, now)
    elif st["phase"] in ("write", "stop"):
        _all_done(st, now)
    elif st["phase"] == "show":
        for key, ap in list(st["appeals"].items()):
            if ap["c"] == c:
                ap["res"] = False
            elif ap["res"] is None and all(x in ap["yes"] or x in ap["no"] for x in active(st) if x != ap["c"]):
                _resolve(st, key)
        if all(x in st["ready"] for x in active(st)) and not _open_appeals(st):
            _next_round(st, now)


def tick(st: dict, now: float) -> bool:
    """پایان وقت هر مرحله. داوری‌ای که تا JUDGE_MAX نرسیده با داوری ساده بسته می‌شود."""
    if st["over"]:
        return False
    changed = False
    for _ in range(4):
        ph = st["phase"]
        if now < st["deadline"]:
            break
        if ph == "letter":
            if not st["letters"]:
                set_letters(st, [], [], now)
            else:
                _start_write(st, now)
        elif ph in ("write", "stop"):
            if now < st["deadline"] + LATE:
                break
            _to_judge(st, now)
        elif ph == "judge":
            apply_judgement(st, simple_verdicts(st), "simple", now, st["round"])
        elif ph == "show":
            _next_round(st, now)
        else:
            break
        changed = True
    return changed


def current(st: dict) -> str | None:
    return None    # نوبتی نیست؛ همه هم‌زمان می‌نویسند


def human_acted(st: dict, c: str) -> None:
    """غیبت در این بازی شمرده نمی‌شود (برگ خالی خودش صفر می‌گیرد)."""


def winners(st: dict) -> set[str]:
    return set(st.get("winners") or [])


def view(st: dict, me: str | None, since: int, now: float) -> dict:
    """هر بازیکن فقط برگ خودش را تا پایان داوری می‌بیند؛ بقیه فقط تعداد خانه‌های پرشده. بعد از داوری، برگ همه.
    تماشاگر (me=None، از کارت گروه) همان موقع نوشتن هم برگ همه را زنده می‌بیند (sheets)."""
    ph, rnd = st["phase"], st["round"]
    writing = ph in ("write", "stop", "judge")
    me_in = me in st["players"] if me else False
    letter = letter_of(st) if letter_shown(st, now) else None
    appeals = {}
    for key, ap in st["appeals"].items():
        appeals[key] = {"c": ap["c"], "col": ap["col"], "yes": len(ap["yes"]), "no": len(ap["no"]), "res": ap["res"],
                        "mine": "yes" if me in ap["yes"] else "no" if me in ap["no"] else None}
    return {
        "order": list(st["order"]),
        "players": {c: {"name": p["name"], "av": p["av"], "pic": p.get("pic", ""), "out": p["out"], "me": c == me,
                        "total": st["totals"].get(c, 0), "done": c in st["done"], "ready": c in st["ready"],
                        "filled": len(st["sheets"].get(c, {})) if writing else None}
                    for c, p in st["players"].items()},
        "me": me if me_in else None,
        "cols": [{"k": k, "fa": COL_FA[k]} for k in st["cols"]],
        "rounds_n": st["rounds_n"], "round": rnd, "secs": st["secs"],
        "phase": ph,
        "letter": letter,
        "line": st["lines"][rnd] if letter and rnd < len(st["lines"]) else "",
        "deadline_ms": max(0, int((st["deadline"] - now) * 1000)) if ph in ("letter", "write", "stop", "show") else 0,
        "waiting": [c for c in active(st) if c not in st["here"]] if ph == "letter" and rnd == 0 else [],
        "sheet": dict(st["sheets"].get(me, {})) if me_in and writing else None,
        "sheets": {c: dict(st["sheets"].get(c, {})) for c in st["players"]} if me is None and writing else None,
        "submitted": me in st["done"],
        "stopper": st["stopper"],
        "results": st["rounds"],
        "appeals": appeals,
        "totals": st["totals"],
        "events": [e for e in st["events"] if e["seq"] > since],
        "seq": st["seq"],
        "over": st["over"], "winner": st["winner"], "winners": st["winners"],
        "started": st["started"],
    }
