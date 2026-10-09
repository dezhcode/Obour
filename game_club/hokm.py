"""قواعد حکم چهارنفره؛ فقط سمت سرور.

مثل منچ (ludo.py): هیچ I/O ندارد، وضعیت یک dict ساده است که به JSON ذخیره
می شود، هر اتفاق یک رویداد شماره دار می سازد و ربات ها و نوبت های بی جواب
فقط داخل tick جلو می روند (با هر درخواست مینی اپ).

قواعد (حکم ایرانی، دو تیم دونفره):
- صندلی ها ۰ تا ۳ به ترتیب نوبت (خلاف عقربه ساعت)؛ ۰ و ۲ یک تیم، ۱ و ۳ تیم دیگر
- حاکم دست اول به رسم قدیم تعیین می شود: برگ ها رو باز یکی یکی دور میز پخش
  می شوند و اولین کسی که آس بگیرد حاکم است (رویداد hakem با draw)
- اول دست به هر نفر ۵ برگ داده می شود؛ حاکم از روی برگ هایش حکم (خال برتر) را
  انتخاب می کند و بعد ۸ برگ دیگر به هر نفر می رسد
- حاکم دور اول را شروع می کند. هر کس باید از خال شروع شده بیاید؛ اگر نداشت
  هر برگی (حکم یا دور ریختن). بزرگ ترین حکم، وگرنه بزرگ ترین برگ خال شروع،
  دور را می برد و برنده دور بعد را شروع می کند
- تیمی که زودتر ۷ دور ببرد دست را برده: ۱ امتیاز. اگر تیم دیگر هیچ دوری نبرده
  باشد «کوت» است: ۲ امتیاز، و اگر کوت شده تیم حاکم باشد ۳ امتیاز
- اگر تیم حاکم دست را ببازد، حکم به نفر بعدی می رسد
- اولین تیمی که به امتیاز هدف (۳ یا ۷ دست) برسد بازی را برده

برگ ها عدد ۰ تا ۵۱ اند: خال = c // 13 (۰ پیک، ۱ دل، ۲ خشت، ۳ گشنیز) و
ارزش = c % 13 (۰ یعنی ۲ ... ۱۲ یعنی آس).
"""
from __future__ import annotations

import random

SEATS = ("0", "1", "2", "3")
# ترتیب نشستن سر میز دعوت: اولین مهمان یار سازنده می شود (صندلی ۲)
LOBBY_ORDER = ("0", "2", "1", "3")
SUITS = 4
HAND_TRICKS = 7
MAX_EVENTS = 60
# زمان ها با انیمیشن مینی اپ هماهنگ اند تا هر کس ببیند حاکم کیست و حکم چه شد
START_GRACE = 2.5    # تا بازیکن ها از شمارش معکوس لابی به میز برسند
HAKEM_ANIM = 2.2     # اعلام حاکم در دست های بعد
DEAL_ANIM = 1.8      # پخش پنج برگ اول
TRUMP_THINK = 2.4    # ربات حاکم کمی فکر می کند تا بقیه «در حال انتخاب حکم» را ببینند
DEAL2_ANIM = 4.0     # نمایش حکم انتخاب شده و پخش هشت برگ بعدی
BOT_THINK = 0.9
COLLECT = 1.5        # برگ های یک دور این مدت روی میز می مانند
HANDOVER = 3.6       # نمایش نتیجه دست

_rng = random.SystemRandom()


def suit(c: int) -> int:
    return c // 13


def rank(c: int) -> int:
    return c % 13


def team(i: int) -> int:
    return i % 2


def nxt(i: int) -> int:
    return (i + 1) % 4


def draw_time(n: int) -> float:
    """مدت انیمیشن «آس کشی» برای n برگ (همان گام های hokm.js)."""
    step = .17 if n > 14 else .23 if n > 8 else .30
    return .7 + n * step + 2.8


def draw_hakem() -> tuple[int, list[list]]:
    """برگ ها رو باز، از یک نفر تصادفی دور میز؛ اولین آس حاکم را تعیین می کند."""
    deck = list(range(52))
    _rng.shuffle(deck)
    i, draw = _rng.randrange(4), []
    for c in deck:
        draw.append([SEATS[i], c])
        if rank(c) == 12:
            return i, draw
        i = nxt(i)
    return i, draw  # دست نیافتنی: چهار آس در دسته هست


# ---------- ساخت ----------
def new_state(seats: list[dict], now: float, turn_s: int, stake: bool, target: int, hakem: int | None = None) -> dict:
    """seats: [{color: "0".."3", uid, name, av, pic, bot}]"""
    draw = None
    if hakem not in range(4):
        hakem, draw = draw_hakem()
    players = {s["color"]: {"uid": s.get("uid"), "name": s["name"], "av": s.get("av", 1), "pic": s.get("pic", ""),
                            "bot": bool(s.get("bot")), "out": False, "misses": 0} for s in seats}
    st = {
        "game": "hokm", "order": list(SEATS), "players": players, "target": target, "score": [0, 0],
        "hand_no": 0, "hakem": hakem, "prev_hakem": None, "trump": None,
        "phase": "trump", "hands": {s: [] for s in SEATS}, "rest": {s: [] for s in SEATS},
        "tricks": [0, 0], "trick": [], "led": None, "turn": 0, "played": [], "last_trick": None,
        "next_at": now, "deadline": now, "turn_s": turn_s, "stake": stake,
        "events": [], "seq": 0, "turn_id": 0, "winner": None, "over": False, "started": now,
        "stats": {s: {"tricks": 0, "hakem": 0} for s in SEATS},
    }
    _start_hand(st, now, START_GRACE + (draw_time(len(draw)) if draw else HAKEM_ANIM), draw)
    return st


def _event(st: dict, **e) -> None:
    st["seq"] += 1
    e["seq"] = st["seq"]
    st["events"].append(e)
    if len(st["events"]) > MAX_EVENTS:
        st["events"] = st["events"][-MAX_EVENTS:]


def _sort(cards: list[int], trump: int | None = None) -> list[int]:
    # حکم اول، بعد بقیه خال ها؛ داخل هر خال از بزرگ به کوچک
    return sorted(cards, key=lambda c: (0 if trump is not None and suit(c) == trump else 1, suit(c), -rank(c)))


def _start_hand(st: dict, now: float, lead: float = HAKEM_ANIM, draw: list | None = None) -> None:
    deck = list(range(52))
    _rng.shuffle(deck)
    for k, s in enumerate(SEATS):
        part = deck[k * 13:(k + 1) * 13]
        st["hands"][s] = _sort(part[:5])
        st["rest"][s] = part[5:]
    st.update(trump=None, phase="trump", tricks=[0, 0], trick=[], led=None, played=[], last_trick=None,
              turn=st["hakem"])
    st["stats"][SEATS[st["hakem"]]]["hakem"] += 1
    prev = st.get("prev_hakem")
    _event(st, t="hakem", c=SEATS[st["hakem"]], hand=st["hand_no"], draw=draw,
           prev=SEATS[prev] if prev is not None else None)
    _event(st, t="deal", hakem=SEATS[st["hakem"]], hand=st["hand_no"])
    _wait(st, now, lead + DEAL_ANIM + (TRUMP_THINK if _auto(st, st["hakem"]) else 0))


def _wait(st: dict, now: float, delay: float) -> None:
    st["turn_id"] = st["seq"]
    st["next_at"] = now + delay
    st["deadline"] = now + delay + st["turn_s"]


def current(st: dict) -> str:
    return SEATS[st["turn"]]


def _auto(st: dict, i: int) -> bool:
    p = st["players"][SEATS[i]]
    return p["bot"] or p["out"]


# ---------- قواعد ----------
def legal(st: dict, i: int) -> list[int]:
    hand = st["hands"][SEATS[i]]
    if st["phase"] != "play" or st["turn"] != i:
        return []
    if st["led"] is not None:
        follow = [c for c in hand if suit(c) == st["led"]]
        if follow:
            return follow
    return list(hand)


def trick_winner(trick: list[list[int]], trump: int) -> int:
    """trick: [[صندلی, برگ], ...] به ترتیب بازی؛ صندلی برنده را برمی گرداند."""
    best_i, best = trick[0]
    for i, c in trick[1:]:
        if suit(c) == suit(best):
            if rank(c) > rank(best):
                best_i, best = i, c
        elif suit(c) == trump:
            best_i, best = i, c
    return best_i


def choose_trump(st: dict, i: int, s: int, now: float, auto: bool = False) -> str | None:
    if st["over"]:
        return "over"
    if st["phase"] != "trump":
        return "not_trump_phase"
    if st["hakem"] != i:
        return "not_your_turn"
    if s not in range(SUITS):
        return "bad_suit"
    st["trump"] = s
    for k in SEATS:
        st["hands"][k] = _sort(st["hands"][k] + st["rest"][k], s)
        st["rest"][k] = []
    st["phase"], st["turn"] = "play", st["hakem"]
    _event(st, t="trump", c=SEATS[i], suit=s, auto=auto)
    _wait(st, now, DEAL2_ANIM)
    return None


def play(st: dict, i: int, c: int, now: float, auto: bool = False) -> str | None:
    if st["over"]:
        return "over"
    if st["phase"] != "play":
        return "not_play_phase"
    if st["turn"] != i:
        return "not_your_turn"
    if c not in legal(st, i):
        return "illegal_card"
    st["hands"][SEATS[i]].remove(c)
    if not st["trick"]:
        st["led"] = suit(c)
    st["trick"].append([i, c])
    st["played"].append(c)
    _event(st, t="play", c=SEATS[i], card=c, auto=auto)
    if len(st["trick"]) < 4:
        st["turn"] = nxt(i)
        _wait(st, now, BOT_THINK if _auto(st, st["turn"]) else 0.35)
        return None
    w = trick_winner(st["trick"], st["trump"])
    st["tricks"][team(w)] += 1
    st["stats"][SEATS[w]]["tricks"] += 1
    st["phase"], st["turn"] = "collect", w
    _event(st, t="trick", c=SEATS[w], tricks=list(st["tricks"]))
    st["next_at"] = st["deadline"] = now + COLLECT
    return None


def _after_collect(st: dict, now: float) -> None:
    st["last_trick"] = {"cards": st["trick"], "winner": SEATS[st["turn"]]}
    st["trick"], st["led"] = [], None
    w = next((t for t in (0, 1) if st["tricks"][t] >= HAND_TRICKS), None)
    if w is None:
        st["phase"] = "play"
        _wait(st, now, BOT_THINK if _auto(st, st["turn"]) else 0.2)
        return
    lose = 1 - w
    hakem_team = team(st["hakem"])
    kot = st["tricks"][lose] == 0
    pts = (3 if lose == hakem_team else 2) if kot else 1
    st["score"][w] += pts
    _event(st, t="hand", team=w, pts=pts, kot=kot, tricks=list(st["tricks"]), score=list(st["score"]),
           hakem=str(st["hakem"]))
    if st["score"][w] >= st["target"]:
        _finish(st, w)
        return
    st["prev_hakem"] = st["hakem"]
    if w != hakem_team:
        st["hakem"] = nxt(st["hakem"])
    st["hand_no"] += 1
    st["phase"] = "handover"
    st["next_at"] = st["deadline"] = now + HANDOVER


def _finish(st: dict, winner: int | None) -> None:
    st["over"], st["winner"], st["phase"] = True, winner, "over"
    _event(st, t="win" if winner is not None else "end", team=winner)


def leave(st: dict, s: str, now: float, why: str = "left") -> None:
    """خروج یا جریمه غیبت: از این به بعد ربات جای او بازی می کند."""
    p = st["players"].get(s)
    if not p or p["out"] or st["over"]:
        return
    p["out"] = True
    _event(st, t="leave", c=s, why=why)
    if not any(not q["bot"] and not q["out"] for q in st["players"].values()):
        _finish(st, None)
        return
    if st["turn"] == int(s) and st["phase"] in ("trump", "play"):
        st["next_at"] = min(st["next_at"], now + BOT_THINK)


# ---------- ربات (و نوبت بی جواب) ----------
def bot_trump(st: dict, i: int) -> int:
    hand = st["hands"][SEATS[i]]
    def score(s: int) -> float:
        cs = [rank(c) for c in hand if suit(c) == s]
        return len(cs) * 10 + sum(r - 7 for r in cs if r >= 9) * 3 + _rng.random()
    return max(range(SUITS), key=score)


def _boss(st: dict, c: int, mine: list[int]) -> bool:
    """بزرگ ترین برگ باقی مانده از این خال است؟ (همه بزرگ ترها بازی شده یا دست خودم)"""
    gone = set(st["played"]) | set(mine)
    return all(x in gone for x in range(c + 1, (suit(c) + 1) * 13))


def bot_card(st: dict, i: int) -> int:
    hand = st["hands"][SEATS[i]]
    ok = legal(st, i)
    trump = st["trump"]
    low = lambda cs: min(cs, key=rank)  # noqa: E731
    high = lambda cs: max(cs, key=rank)  # noqa: E731
    if not st["trick"]:
        plain = [c for c in ok if suit(c) != trump]
        boss = [c for c in plain if _boss(st, c, hand)]
        if boss:
            return high(boss)
        if plain:
            by = {}
            for c in plain:
                by.setdefault(suit(c), []).append(c)
            longest = max(by.values(), key=lambda cs: (len(cs), -min(rank(x) for x in cs)))
            return low(longest)
        return low(ok)
    w = trick_winner(st["trick"], trump)
    wc = next(c for j, c in st["trick"] if j == w)
    partner = team(w) == team(i)
    last = len(st["trick"]) == 3

    def beats(c: int) -> bool:
        return trick_winner(st["trick"] + [[i, c]], trump) == i

    following = suit(ok[0]) == st["led"]
    if following:
        win = [c for c in ok if beats(c)]
        boss_win = [c for c in win if _boss(st, c, hand)]
        if partner:
            # یار جلوست: فقط اگر برگش ضعیف است و برگ قطعی داریم رویش می رویم
            if last or _boss(st, wc, hand) or rank(wc) >= 10 or not boss_win:
                return low(ok)
            return high(boss_win)
        if win:
            return low(win) if last or not boss_win else high(boss_win)
        return low(ok)
    plain = [c for c in ok if suit(c) != trump]
    if partner:
        return low(plain) if plain else low(ok)
    win = [c for c in ok if suit(c) == trump and beats(c)]
    if win:
        return low(win)
    return low(plain) if plain else low(ok)


# ---------- زمان ----------
def tick(st: dict, now: float) -> bool:
    """ربات ها، نوبت های تمام شده و مکث های بین دور و دست را جلو می برد."""
    changed = False
    for _ in range(12):
        if st["over"]:
            break
        ph = st["phase"]
        if ph == "collect":
            if now < st["next_at"]:
                break
            _after_collect(st, now)
            changed = True
            continue
        if ph == "handover":
            if now < st["next_at"]:
                break
            _start_hand(st, now)
            changed = True
            continue
        i = st["hakem"] if ph == "trump" else st["turn"]
        s = SEATS[i]
        p = st["players"][s]
        if _auto(st, i):
            if now < st["next_at"]:
                break
        else:
            if now < st["deadline"]:
                break
            p["misses"] += 1
            _event(st, t="timeout", c=s, n=p["misses"])
            if st["stake"] and p["misses"] >= 3:
                leave(st, s, now, "timeout")
                changed = True
                continue
        auto = not p["bot"]
        if ph == "trump":
            choose_trump(st, i, bot_trump(st, i), now, auto=auto)
        else:
            play(st, i, bot_card(st, i), now, auto=auto)
        changed = True
    return changed


def human_acted(st: dict, s: str) -> None:
    st["players"][s]["misses"] = 0


def winners(st: dict) -> set[str]:
    """صندلی های تیم برنده (برای تسویه)."""
    if st.get("winner") is None:
        return set()
    return {s for k, s in enumerate(SEATS) if team(k) == st["winner"]}


# ---------- نمای هر بازیکن ----------
def view(st: dict, me: str | None, since: int, now: float) -> dict:
    mi = int(me) if me in SEATS else None
    ph = st["phase"]
    act = st["hakem"] if ph == "trump" else st["turn"]
    ap = st["players"][SEATS[act]]
    waiting = ph in ("trump", "play") and not st["over"]
    return {
        "order": list(SEATS),
        "players": {s: {"name": p["name"], "av": p["av"], "pic": p.get("pic", ""), "bot": p["bot"], "out": p["out"],
                        "me": s == me, "team": int(s) % 2, "count": len(st["hands"][s])}
                    for s, p in st["players"].items()},
        "me": me,
        "hand": list(st["hands"][me]) if me in SEATS else [],
        "phase": ph,
        "turn": SEATS[act] if waiting else None,
        "hakem": SEATS[st["hakem"]],
        "trump": st["trump"],
        "trick": st["trick"],
        "led": st["led"],
        "last_trick": st["last_trick"],
        "tricks": st["tricks"],
        "score": st["score"],
        "target": st["target"],
        "hand_no": st["hand_no"],
        "legal": legal(st, mi) if mi is not None and waiting and ph == "play" else [],
        "deadline_ms": 0 if (not waiting or _auto(st, act)) else max(0, int((st["deadline"] - now) * 1000)),
        "turn_ms": st["turn_s"] * 1000,
        "events": [e for e in st["events"] if e["seq"] > since],
        "seq": st["seq"],
        "over": st["over"],
        "winner": st["winner"],
        "stats": st["stats"].get(me) if me else None,
        "started": st["started"],
    }
