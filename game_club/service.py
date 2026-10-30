"""میزها، صف ناشناس، دعوت، سکه، جام و تسویه.

سکه فقط پول داخل بازی است (players.points): هدیهٔ شروع، جایزهٔ روزانه، برد رتبه ای و خرید درون برنامه ای
می آورد و فقط آیتم می خرد. بازی ورودی ندارد.
بازی رتبه ای (mode=ranked): فقط صف آنلاین با بازیکن واقعی (نه دعوت، نه ربات)؛ برنده جام (+GAME_CLUB_RANK_WIN)
و چند سکه از طرف بازی (سقف روزانه دارد) می گیرد و بازنده جام از دست می دهد. در موتورها همان پرچم قدیمی
stake است: سه نوبت غیبت پشت سر هم یعنی باخت.
میزهای امتیازی قدیمی (mode=stake) که پیش از سکه شروع شده اند با همان قاعدهٔ قبلی تمام می شوند، ولی جایزه و
برگشت ورودی شان به legacy_points می رود تا refund.py به کیف عبور برگرداند.
همه این ها idem دارند تا درخواست تکراری دو بار پول جابه جا نکند.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import secrets
import time

from . import billiard, divar, esmfamil, esmfamil_ai, football, hokm, lashgar, ludo, names, snakes
from .config import gc
from .db import GCDatabase, pic_url

log = logging.getLogger("gameclub.service")

_ALPH = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


# هر بازی: موتور قواعد، نام فارسی و صفحه میز
GAMES = {"ludo": (ludo, "منچ", "ludo.html"), "hokm": (hokm, "حکم", "hokm.html"),
         "football": (football, "فوتبال", "football.html"), "billiard": (billiard, "بیلیارد", "billiard.html"),
         "divar": (divar, "دیوار", "divar.html"), "esmfamil": (esmfamil, "اسم‌فامیل", "esmfamil.html"),
         "lashgar": (lashgar, "لشگر کاغذی", "lashgar.html"), "snakes": (snakes, "مار و پله", "snakes.html")}
# بازی هایی که فقط در گروه ساخته می شوند (میز از کارت گروه؛ مینی اپ فقط می نشیند و بازی می کند)
GROUP_ONLY = {"esmfamil", "lashgar"}


def game_of(cfg: dict) -> str:
    g = cfg.get("game")
    return g if g in GAMES else "ludo"


def _eng(cfg: dict):
    return GAMES[game_of(cfg)][0]


def _gname(cfg: dict) -> str:
    return GAMES[game_of(cfg)][1]


def _gpage(cfg: dict) -> str:
    return GAMES[game_of(cfg)][2]


def _seat_order(cfg: dict) -> tuple:
    """ترتیب صندلی ها؛ در حکم اولین مهمان میز دعوت یار سازنده می شود."""
    g = game_of(cfg)
    if g == "hokm":
        return hokm.LOBBY_ORDER
    if g == "football":
        return football.SEATS
    if g == "billiard":
        # چهار نفره: مثل حکم اولین مهمان یار سازنده می شود
        return billiard.LOBBY_ORDER4 if cfg.get("players") == 4 else billiard.SEATS2
    if g == "divar":
        return divar.LOBBY_ORDER4 if cfg.get("players") == 4 else divar.SEATS2
    if g == "esmfamil":
        return esmfamil.SEATS
    if g == "lashgar":
        return lashgar.SEATS
    if g == "snakes":
        return snakes.seats_of(cfg.get("players") or 2)
    return ludo.SEATS[cfg["players"]]


def _current(st: dict) -> str | None:
    if st.get("game") == "football":
        return football.current(st)
    if st.get("game") == "billiard":
        return billiard.current(st)
    if st.get("game") == "divar":
        return divar.current(st)
    if st.get("game") == "esmfamil":
        return None
    if st.get("game") == "lashgar":
        return lashgar.current(st)
    if st.get("game") == "snakes":
        return snakes.current(st)
    if st.get("game") == "hokm":
        return hokm.SEATS[st["hakem"] if st["phase"] == "trump" else st["turn"]] if st["phase"] in ("trump", "play") else None
    return ludo.current(st)


def _winners(st: dict) -> set:
    if st.get("game") == "hokm":
        return hokm.winners(st)
    if st.get("game") == "football":
        return football.winners(st)
    if st.get("game") == "billiard":
        return billiard.winners(st)
    if st.get("game") == "divar":
        return divar.winners(st)
    if st.get("game") == "esmfamil":
        return esmfamil.winners(st)
    if st.get("game") == "lashgar":
        return lashgar.winners(st)
    if st.get("game") == "snakes":
        return snakes.winners(st)
    return {st["winner"]} if st.get("winner") else set()


# هر تغییر میز (نشستن، بلند شدن، شروع، پایان، بستن) به groups.py خبر داده می شود تا کارت گروه به روز شود
table_hook = None


async def _hook(db: GCDatabase, match_id: str) -> None:
    if table_hook is None:
        return
    try:
        await table_hook(db, match_id)
    except Exception:  # noqa: BLE001
        log.debug("کارت میز گروه به روز نشد", exc_info=True)


# تابع ارسال پیام ربات (tg, text, page, key=نوع اعلان)؛ bot.py هنگام راه اندازی می گذارد
notifier = None
AWAY = 12.0  # کسی که این مدت صفحه میز را نپرسیده، بیرون از مینی اپ حساب می شود


async def _notify(db: GCDatabase, tg: int | None, key: str, text: str, page: str = "ludo.html") -> None:
    """هر اعلان یک بار، در ربات تلگرام و نوتیفیکیشن گوشی (برنامهٔ اندروید)؛ خطای ارسال بازی را نمی شکند."""
    from . import push

    if (notifier is None and not push.enabled()) or not tg or not await db.ping_once(key):
        return
    if notifier is not None and tg > 0:
        try:
            await notifier(tg, text, page, key=key.split(":", 1)[0])
        except Exception:  # noqa: BLE001
            log.debug("اعلان AsoTas نرفت", exc_info=True)
    try:
        await push.to_player(db, tg, text, page)
    except Exception:  # noqa: BLE001
        log.debug("نوتیفیکیشن گوشی AsoTas نرفت", exc_info=True)


async def _away(db: GCDatabase, match_id: str, tg: int, now: float) -> bool:
    return now - await db.seen(match_id, tg) > AWAY


class GCError(Exception):
    def __init__(self, code: str, **extra) -> None:
        super().__init__(code)
        self.code = code
        self.extra = extra


def _code(n: int) -> str:
    return "".join(secrets.choice(_ALPH) for _ in range(n))


# ---------- تنظیم میز ----------
def _mode(raw: dict) -> str:
    """free یا ranked. «stake» صفحه های قدیمی (کش) همان رتبه ای است؛ ورودی دیگر نیست."""
    if raw.get("mode") not in ("ranked", "stake"):
        return "free"
    if not gc.ranked_enabled:
        raise GCError("ranked_off")
    return "ranked"


def _ints_of(raw: dict, **defaults: int) -> dict:
    try:
        return {k: int(raw.get(k) or d) for k, d in defaults.items()}
    except (TypeError, ValueError):
        raise GCError("bad_cfg") from None


def norm_cfg(raw: dict) -> dict:
    """تنظیمات میز. entry همیشه ۰ است (فقط برای سازگاری با صفحه های قدیمی و کلید صف می ماند)."""
    game = raw.get("game")
    if game in GROUP_ONLY and raw.get("mode") in ("ranked", "stake"):
        raise GCError("bad_cfg")
    if game == "esmfamil":
        # همیشه آزاد: داوری با هوش مصنوعی است
        v = _ints_of(raw, rounds=3, secs=300)
        if v["rounds"] not in esmfamil.ROUNDS or v["secs"] not in esmfamil.SECS:
            raise GCError("bad_cfg")
        return {"game": "esmfamil", "mode": "free", "entry": 0, "players": esmfamil.MAX_PLAYERS, **v}
    if game == "lashgar":
        # دو نفره و همیشه آزاد (میز گروه)؛ فقط اندازهٔ ارتش انتخاب می شود
        v = _ints_of(raw, army=11)
        if v["army"] not in lashgar.ARMIES:
            raise GCError("bad_cfg")
        return {"game": "lashgar", "mode": "free", "entry": 0, "players": 2, **v}
    mode = _mode(raw)
    if game == "hokm":
        v = _ints_of(raw, target=7)
        if v["target"] not in (3, 7):
            raise GCError("bad_cfg")
        return {"game": "hokm", "mode": mode, "entry": 0, "players": 4, **v}
    if game == "football":
        v = _ints_of(raw, target=3, passes=0)
        if v["target"] not in football.GOALS_TO_WIN or v["passes"] not in football.PASS_LIMITS:
            raise GCError("bad_cfg")
        return {"game": "football", "mode": mode, "entry": 0, "players": 2, "target": v["target"], "passes": v["passes"]}
    if game == "billiard":
        v = _ints_of(raw, players=2)
        if v["players"] not in (2, 4):
            raise GCError("bad_cfg")
        return {"game": "billiard", "mode": mode, "entry": 0, **v}
    if game == "divar":
        v = _ints_of(raw, players=2)
        variant = "star" if raw.get("variant") == "star" else "classic"
        if v["players"] not in (2, 4) or (variant == "star" and v["players"] != 4):
            raise GCError("bad_cfg")
        return {"game": "divar", "mode": mode, "entry": 0, **v, "variant": variant}
    if game == "snakes":
        v = _ints_of(raw, players=2)
        if v["players"] not in (2, 3, 4):
            raise GCError("bad_cfg")
        return {"game": "snakes", "mode": mode, "entry": 0, **v}
    v = _ints_of(raw, players=2, pawns=2)
    if v["players"] not in (2, 4) or v["pawns"] not in (2, 4):
        raise GCError("bad_cfg")
    return {"game": "ludo", "mode": mode, "entry": 0, **v}


def cfg_key(cfg: dict) -> str:
    if game_of(cfg) == "football":
        return f"football:{cfg['mode']}:{cfg['entry']}:{cfg['target']}:{cfg.get('passes', 0)}"
    if game_of(cfg) == "hokm":
        return f"hokm:{cfg['mode']}:{cfg['entry']}:{cfg['target']}"
    if game_of(cfg) == "billiard":
        return f"billiard:{cfg['mode']}:{cfg['entry']}:{cfg['players']}"
    if game_of(cfg) == "divar":
        return f"divar:{cfg['mode']}:{cfg['entry']}:{cfg['players']}:{cfg.get('variant', 'classic')}"
    if game_of(cfg) == "snakes":
        return f"snakes:{cfg['mode']}:{cfg['entry']}:{cfg['players']}"
    if game_of(cfg) == "esmfamil":
        return f"esmfamil:free:0:{cfg['rounds']}:{cfg['secs']}"
    if game_of(cfg) == "lashgar":
        return f"lashgar:free:0:{cfg['army']}"
    return f"{cfg['mode']}:{cfg['entry']}:{cfg['players']}:{cfg['pawns']}"


# ---------- سکه ----------
async def spend(db: GCDatabase, tg: int, amount: int, kind: str, note: str, ref: str, idem: str) -> bool:
    """کسر سکه با ردیف دفتر. همان idem دوباره = همان نتیجه قبلی."""
    lid = await db.add_ledger(tg, kind, -amount, note, ref, idem, status="pending")
    if lid is None:
        row = await db.ledger_by_idem(idem)
        return bool(row and row["status"] == "done")
    if await db.debit(tg, amount):
        await db.set_ledger_status(lid, "done")
        return True
    await db.set_ledger_status(lid, "failed")
    return False


async def earn(db: GCDatabase, tg: int, amount: int, kind: str, note: str, ref: str, idem: str) -> bool:
    if amount <= 0:
        return False
    lid = await db.add_ledger(tg, kind, amount, note, ref, idem, status="pending")
    if lid is None:
        return False  # قبلا داده شده
    await db.player(tg)
    if await db.credit(tg, amount):
        await db.set_ledger_status(lid, "done")
        return True
    await db.set_ledger_status(lid, "failed")
    return False


async def earn_legacy(db: GCDatabase, tg: int, amount: int, kind: str, note: str, ref: str, idem: str) -> bool:
    """امتیاز قدیمی (جایزه و برگشت ورودی میزهای امتیازی پیش از سکه)؛ refund.py به کیف عبور برمی گرداند."""
    if amount <= 0:
        return False
    lid = await db.add_ledger(tg, kind, amount, note, ref, idem, status="pending")
    if lid is None:
        return False
    await db.player(tg)
    if await db.credit_legacy(tg, amount):
        await db.set_ledger_status(lid, "done")
        return True
    await db.set_ledger_status(lid, "failed")
    return False


def _iran_day(now: float | None = None) -> int:
    """شمارهٔ روز به وقت ایران (UTC+3:30)؛ جایزهٔ روزانه و سقف سکهٔ برد رتبه ای با همین عوض می شوند."""
    return int(((now or time.time()) + 12600) // 86400)


async def welcome_gift(db: GCDatabase, tg: int) -> None:
    """هدیهٔ شروع، یک بار برای هر حساب."""
    if gc.start_coins and not await db.ledger_by_idem(f"gift:start:{tg}"):
        await earn(db, tg, gc.start_coins, "gift", "هدیهٔ شروع از طرف تاسی 🎁", "start", f"gift:start:{tg}")


def daily_view(p: dict, now: float | None = None) -> dict:
    """جایزهٔ ورود روزانه: روز چندم پشت سر هم، امروز گرفته یا نه، سکهٔ هر روز."""
    today, last, streak = _iran_day(now), int(p.get("daily_day") or 0), int(p.get("daily_streak") or 0)
    plan = list(gc.daily_coins)
    if last == today:
        return {"claimed": True, "day": streak, "next": (streak % len(plan)) + 1, "plan": plan}
    nxt = (streak % len(plan)) + 1 if last == today - 1 else 1
    return {"claimed": False, "day": nxt - 1, "next": nxt, "plan": plan}


async def daily_claim(db: GCDatabase, tg: int, now: float | None = None) -> dict:
    p = await db.get_player(tg) or {}
    v = daily_view(p, now)
    if v["claimed"]:
        raise GCError("daily_done")
    today, streak = _iran_day(now), v["next"]
    if not await db.claim_daily(tg, int(p.get("daily_day") or 0), today, streak):
        raise GCError("daily_done")
    amount = v["plan"][streak - 1]
    await earn(db, tg, amount, "daily", f"جایزهٔ روز {streak}", "daily", f"daily:{tg}:{today}")
    p = await db.get_player(tg) or {}
    return {"coins": amount, "points": int(p.get("points") or 0), "daily": daily_view(p, now)}


LEAGUES = ((1000, "قهرمان"), (600, "الماسی"), (300, "طلایی"), (100, "نقره‌ای"), (0, "برنزی"))


def league(cups: int) -> str:
    return next(name for floor, name in LEAGUES if cups >= floor)


# ---------- ساخت و تغییر میز ----------
async def _seat_info(db: GCDatabase, tg: int) -> dict:
    p = await db.get_player(tg) or {}
    return {"name": (p.get("name") or "بازیکن")[:24], "av": int(p.get("av") or 1), "pic": pic_url(p)}


async def _start_game(db: GCDatabase, match_id: str, cfg: dict, humans: list[dict], *, create: bool) -> None:
    """humans: [{tg, paid, color?}] → میز در حال بازی."""
    colors = list(_seat_order(cfg))
    seats, used = [], set()
    for h in humans:
        c = h.get("color") if h.get("color") in colors and h.get("color") not in used else \
            next(x for x in colors if x not in used)
        used.add(c)
        info = await _seat_info(db, h["tg"])
        seats.append({"color": c, "uid": h["tg"], "name": info["name"], "av": info["av"], "pic": info["pic"],
                      "bot": False, "paid": h["paid"]})
    # ربات ها هم یوزرنیمی از همان نوع بازیکن ها دارند تا سر میز یکدست باشند
    bot_names = {s["name"] for s in seats}
    for c in colors if game_of(cfg) not in GROUP_ONLY else ():   # اسم‌فامیل و لشگر کاغذی ربات ندارند
        if c not in used:
            if cfg["mode"] != "free":     # رتبه ای (و امتیازی قدیمی) فقط با بازیکن واقعی
                raise GCError("need_players")
            bn = next(n for n in names.random_candidates() if n not in bot_names)
            bot_names.add(bn)
            seats.append({"color": c, "uid": None, "name": bn, "av": random.randint(1, 23), "bot": True})
    if game_of(cfg) == "hokm":
        state = hokm.new_state(seats, time.time(), gc.turn_seconds, cfg["mode"] != "free", cfg["target"])
    elif game_of(cfg) == "football":
        state = football.new_state(seats, time.time(), gc.turn_seconds, cfg["mode"] != "free", cfg["target"],
                                   passes=cfg.get("passes", 0))
    elif game_of(cfg) == "billiard":
        state = billiard.new_state(seats, time.time(), gc.turn_seconds, cfg["mode"] != "free", cfg["players"])
    elif game_of(cfg) == "divar":
        state = divar.new_state(seats, time.time(), gc.turn_seconds, cfg["mode"] != "free", cfg["players"],
                                cfg.get("variant", "classic"))
    elif game_of(cfg) == "snakes":
        state = snakes.new_state(seats, time.time(), gc.turn_seconds, cfg["mode"] != "free", cfg["players"])
    elif game_of(cfg) == "esmfamil":
        state = esmfamil.new_state(seats, time.time(), cfg["rounds"], cfg["secs"])
    elif game_of(cfg) == "lashgar":
        state = lashgar.new_state(seats, time.time(), cfg.get("army", 11))
    else:
        first = random.choice([s["color"] for s in seats if not s["bot"]])
        state = ludo.new_state(seats, cfg["pawns"], time.time(), gc.turn_seconds, cfg["mode"] != "free", first)
    state["pot"] = sum(s.get("paid", 0) for s in seats)
    if create:
        await db.create_match(match_id, "playing", cfg, state, humans[0]["tg"])
        for s in seats:
            if not s["bot"]:
                await db.add_match_player(match_id, s["uid"], s["color"], s.get("paid", 0))
    else:
        m = await db.get_match(match_id)
        if not m or m["status"] != "lobby" or not await db.save_match(match_id, m["version"], "playing", state):
            raise GCError("busy")
    log.info("میز %s شروع شد: %s", match_id, cfg_key(cfg))


async def mutate(db: GCDatabase, match_id: str, fn):
    """خواندن، تغییر، نوشتن با شماره نسخه. اگر پروسه دیگری زودتر نوشت، از نو."""
    for _ in range(8):
        m = await db.get_match(match_id)
        if not m:
            raise GCError("not_found")
        changed, result = fn(m)
        if not changed:
            await _jobs(db, m)
            return m, result
        if await db.save_match(match_id, m["version"], m["status"], m["state"]):
            m["version"] += 1
            if m["status"] == "over":
                await settle(db, m)
            await _jobs(db, m)
            return m, result
        await asyncio.sleep(0.03)
    raise GCError("busy")


# ---------- اسم‌فامیل: داور هوش مصنوعی در پس زمینه ----------
# انتخاب حرف و داوری چند ثانیه طول می کشد؛ درخواست بازیکن منتظرش نمی ماند. یک پروسه با «اجاره» (lease)
# داخل خود میز کار را برمی دارد تا دو پروسه دو بار از هوش مصنوعی نپرسند. اگر کار نیمه ماند، موتور
# بعد از GATHER یا JUDGE_MAX خودش حرف تصادفی یا داوری ساده می گذارد.
_tasks: set = set()


def _spawn_task(coro) -> None:  # noqa: ANN001
    t = asyncio.get_running_loop().create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


spawn = _spawn_task   # آزمون ها جایش تابعی می گذارند که coroutine را نگه دارد و خودش await کند


def _esm_job(st: dict) -> str | None:
    if st.get("game") != "esmfamil" or st["over"]:
        return None
    if st["phase"] == "letter" and not st["letters"]:
        job = "letters"
    elif st["phase"] == "judge":
        job = f"judge:{st['round']}"
    else:
        return None
    return None if st.get("lease") == job else job


async def _jobs(db: GCDatabase, m: dict | None) -> None:
    if not m or m["status"] != "playing" or not _esm_job(m["state"]):
        return
    job = _esm_job(m["state"])

    def claim(mm: dict):
        if mm["status"] != "playing" or _esm_job(mm["state"]) != job:
            return False, None
        mm["state"]["lease"] = job
        return True, json.loads(json.dumps(mm["state"]))

    _, snap = await mutate(db, m["id"], claim)
    if snap:
        spawn(_esm_run(db, m["id"], job, snap))


async def _esm_run(db: GCDatabase, match_id: str, job: str, st: dict) -> None:
    try:
        if job == "letters":
            letters, lines, _by = await esmfamil_ai.pick_letters(st["rounds_n"])

            def put(mm: dict):
                ok = mm["status"] == "playing" and esmfamil.set_letters(mm["state"], letters, lines, time.time())
                return ok, None
            await mutate(db, match_id, put)
            return
        rnd = st["round"]
        verdicts, by = await esmfamil_ai.judge(esmfamil.letter_of(st) or "", esmfamil.judge_input(st))

        def apply(mm: dict):
            ok = mm["status"] == "playing" and esmfamil.apply_judgement(mm["state"], verdicts, by, time.time(), rnd)
            if mm["state"]["over"]:
                mm["status"] = "over"
            return ok, None
        await mutate(db, match_id, apply)
    except Exception:  # noqa: BLE001  (موتور بعد از مهلت خودش جایگزین می گذارد)
        log.warning("کار پس زمینهٔ اسم‌فامیل %s برای میز %s نشد", job, match_id, exc_info=True)


# ---------- فروشگاه ظاهر: میز و ورق حکم ----------
# (نوع، طرح، نام، قیمت به سکه)؛ طرح A رایگان و پیش فرض است. هر سکه GAME_CLUB_POINT_TOMAN تومان
STYLE_ITEMS = {
    "table:a": ("table", "a", "میز کلاسیک", 0),
    "table:b": ("table", "b", "میز کافه شب", 80),
    "table:c": ("table", "c", "میز AsoTas", 80),
    "cards:m": ("cards", "m", "ورق مدرن", 0),       # درشت خوان (طرح قبلی بازی)، رایگان
    "cards:a": ("cards", "a", "ورق کلاسیک", 0),
    "cards:b": ("cards", "b", "ورق کافه شب", 50),
    "cards:c": ("cards", "c", "ورق AsoTas", 50),
    "cards:d": ("cards", "d", "ورق رنگ تمام", 50),
}


# کاورهای پروفایل؛ طرح های بعدی همین جا (و کلاس cover-<id> در gc.css) اضافه می شوند
COVERS = {"gc": "AsoTas"}


def style_of(player: dict) -> dict:
    return {"table": player.get("table_skin") or "a", "cards": player.get("card_skin") or "a"}


async def style_view(db: GCDatabase, tg: int) -> dict:
    p = await db.get_player(tg) or {}
    owned, cur = await db.owned_of(tg), style_of(p)
    items = [{"id": k, "kind": kind, "look": look, "name": name, "price": price,
              "owned": price == 0 or k in owned, "on": cur[kind] == look}
             for k, (kind, look, name, price) in STYLE_ITEMS.items()]
    return {"items": items, **cur, "points": p.get("points", 0)}


async def style_buy(db: GCDatabase, tg: int, item: str, idem: str) -> dict:
    """خرید یک میز یا ورق با سکه؛ بعد از خرید همان هم انتخاب می شود. همان idem دوباره = بی اثر."""
    if item not in STYLE_ITEMS:
        raise GCError("not_found")
    kind, look, name, price = STYLE_ITEMS[item]
    if price and item not in await db.owned_of(tg):
        if not await spend(db, tg, price, "style", f"خرید {name}", item, idem):
            raise GCError("insufficient")
        await db.add_owned(tg, item)
    await db.set_skin(tg, kind, look)
    return await style_view(db, tg)


async def style_use(db: GCDatabase, tg: int, item: str) -> dict:
    if item not in STYLE_ITEMS:
        raise GCError("not_found")
    kind, look, _, price = STYLE_ITEMS[item]
    if price and item not in await db.owned_of(tg):
        raise GCError("not_owned")
    await db.set_skin(tg, kind, look)
    return await style_view(db, tg)


async def settle(db: GCDatabase, m: dict) -> None:
    """یک بار و فقط یک بار: جام و سکهٔ رتبه ای (یا جایزهٔ میز امتیازی قدیمی)، نتیجه ها، آزاد کردن بازیکن ها."""
    if not await db.mark_settled(m["id"]):
        return
    st, cfg = m["state"], m["cfg"]
    rows = await db.match_players(m["id"])
    winners = _winners(st)
    name, game = _gname(cfg), game_of(cfg)
    legacy = cfg["mode"] == "stake"
    shares = _legacy_shares(st, rows) if legacy else {}
    good = _good_winners(st, rows) if cfg["mode"] == "ranked" and winners else set()
    got: dict[int, tuple[int, int]] = {}      # tg -> (سکه یا جایزه، تغییر جام)
    for r in rows:
        won = r["color"] in winners
        prize = cups = 0
        if legacy:
            prize = shares.get(r["tg_id"], 0)
            if not winners and r["paid"]:
                await earn_legacy(db, r["tg_id"], r["paid"], "refund", f"بازگشت ورودی {name}", m["id"],
                                  f"endrefund:{m['id']}:{r['tg_id']}")
            elif prize:
                # منچ یک برنده دارد (idem قبلی همان می ماند)؛ در حکم هر عضو تیم برنده سهم خودش را می گیرد
                idem = f"prize:{m['id']}" if game == "ludo" else f"prize:{m['id']}:{r['tg_id']}"
                await earn_legacy(db, r["tg_id"], prize, "prize", f"جایزهٔ {name}", m["id"], idem)
        elif winners and cfg["mode"] == "ranked":
            ok = r["tg_id"] in good
            cups = await db.rank_add(r["tg_id"], game, gc.rank_win if ok else -gc.rank_lose, ok)
            if ok:
                prize = await _rank_coins(db, r["tg_id"], m["id"], name)
        got[r["tg_id"]] = (prize, cups)
        await db.add_result(m["id"], r["tg_id"], won, prize, cups)
        kots = st.get("kots") if game == "hokm" else None
        if kots and kots[int(r["color"]) % 2]:
            await db.add_kots(r["tg_id"], kots[int(r["color"]) % 2])
    await db.deactivate(m["id"])
    now = time.time()
    for r in rows:
        if not await _away(db, m["id"], r["tg_id"], now):
            continue
        won = r["color"] in winners
        prize, cups = got.get(r["tg_id"], (0, 0))
        if game == "esmfamil":   # برگ کامل همه را ربات در خود گروه فرستاده است
            text = "اسم‌فامیل رو بردی داش! 🎉 برگت از همه پرتر بود برو برگ همه رو تو گروه ببین 😎" if won else \
                "اسم‌فامیل تموم شد و این دفعه نشد 😅 برگ همه با امتیازا تو گروهه دست بعد مال توئه!" if winners else \
                "اسم‌فامیل تموم شد برو نتیجه رو تو گروه ببین"
        elif game == "lashgar":   # برگهٔ آخر جنگ را ربات در خود گروه فرستاده است
            text = "لشگرت جنگو برد فرمانده! 🎉 برگهٔ آخر جنگو تو گروه ببین 😎" if won else \
                "این جنگو باختی 😅 برگهٔ آخر تو گروهه جنگ بعد مال توئه!" if winners else \
                "جنگ کاغذی تموم شد برو نتیجه رو تو گروه ببین"
        elif won and cfg["mode"] == "ranked":
            text = f"{name} رتبه‌ای رو بردی داش! 🏆 {cups:+} جام" + (f" و {prize} سکه جایزه ریخت تو کیفت" if prize else "") + " دمت گرم!"
        elif won:
            text = f"{name} رو بردی! 🎉 حریفا هنوز تو شوکن"
        else:
            text = f"بازی {name} تموم شد و این دفعه نشد فدای سرت دست بعد مال توئه 😉" if winners else f"بازی {name} تموم شد"
        await _notify(db, r["tg_id"], f"over:{m['id']}:{r['tg_id']}", text, _gpage(cfg).replace(".html", "-lobby.html"))
    await _hook(db, m["id"])


def _good_winners(st: dict, rows: list[dict]) -> set:
    """برنده هایی که جایزه می گیرند: در بازی های تیمی و چندنفره کسی که وسط بازی رفته (out) چیزی نمی گیرد."""
    winners = _winners(st)
    return {r["tg_id"] for r in rows if r["color"] in winners
            and not (st.get("game") in ("hokm", "billiard", "divar", "snakes") and st["players"].get(r["color"], {}).get("out"))}


async def _rank_coins(db: GCDatabase, tg: int, match_id: str, name: str) -> int:
    """سکهٔ برد رتبه ای با سقف روزانه (به وقت ایران)."""
    day0 = _iran_day() * 86400 - 12600
    room = gc.rank_coins_day - await db.earned_since(tg, "reward", day0)
    n = max(0, min(gc.rank_coins, room))
    if n and await earn(db, tg, n, "reward", f"برد رتبه‌ای {name}", match_id, f"reward:{match_id}:{tg}"):
        return n
    return 0


def _legacy_shares(st: dict, rows: list[dict]) -> dict:
    """جایزهٔ میزهای امتیازی قدیمی (پیش از سکه): همهٔ ورودی ها بین برنده هایی که نرفته اند."""
    if not st.get("stake"):
        return {}
    pot = sum(r["paid"] for r in rows)
    good = _good_winners(st, rows)
    return {tg: pot // len(good) for tg in good} if good and pot else {}


def _color_of(rows: list[dict], tg: int) -> str | None:
    return next((r["color"] for r in rows if r["tg_id"] == tg), None)


# ---------- صف ناشناس ----------
async def queue_join(db: GCDatabase, tg: int, raw_cfg: dict) -> dict:
    cfg = norm_cfg(raw_cfg)
    active = await db.active_match_of(tg)
    if active:
        return {"state": "matched", "match": active}
    if raw_cfg.get("solo") and cfg["mode"] == "free":
        # تمرین با ربات: بدون صف، همین حالا با ربات ها
        if await db.queue_row(tg):
            await queue_leave(db, tg)
        mid = _code(10)
        await _start_game(db, mid, cfg, [{"tg": tg, "paid": 0}], create=True)
        return {"state": "matched", "match": mid}
    old = await db.queue_row(tg)
    if old:
        if old["cfg_key"] == cfg_key(cfg) and not old["claimed"]:
            return await queue_status(db, tg)
        await queue_leave(db, tg)
    await db.queue_put(tg, cfg_key(cfg), cfg, 0)
    await try_match(db, cfg)
    return await queue_status(db, tg)


async def try_match(db: GCDatabase, cfg: dict) -> None:
    key = cfg_key(cfg)
    if not await db.lock("mm:" + key):
        return
    try:
        n = cfg["players"]
        rows = await db.queue_waiting(key)
        while len(rows) >= n:
            group, rows = rows[:n], rows[n:]
            await _from_queue(db, cfg, group)
        if rows and cfg["mode"] == "free" and gc.bot_fill_seconds and \
                time.time() - rows[0]["created_at"] >= gc.bot_fill_seconds:
            await _from_queue(db, cfg, rows)
    finally:
        await db.unlock("mm:" + key)


async def _from_queue(db: GCDatabase, cfg: dict, group: list[dict]) -> None:
    # اول میز ساخته می شود و بعد صف به آن اشاره می کند، تا کسی شماره میزی
    # را نگیرد که هنوز وجود ندارد. قفل mm:<key> نمی گذارد دو پروسه یک نفر
    # را همزمان بردارند.
    mid = _code(10)
    await _start_game(db, mid, cfg, [{"tg": r["tg_id"], "paid": r["held"]} for r in group], create=True)
    await db.queue_claim([r["tg_id"] for r in group], mid)


async def queue_status(db: GCDatabase, tg: int) -> dict:
    row = await db.queue_row(tg)
    if row and not row["claimed"]:
        await try_match(db, json.loads(row["cfg"]))
        row = await db.queue_row(tg)
    if not row:
        active = await db.active_match_of(tg)
        return {"state": "matched", "match": active} if active else {"state": "none"}
    if row["claimed"]:
        await db.queue_del(tg)
        return {"state": "matched", "match": row["claimed"]}
    waiting = await db.queue_waiting(row["cfg_key"])
    cfg = json.loads(row["cfg"])
    return {"state": "waiting", "waited": int(time.time() - row["created_at"]), "cfg": cfg,
            "found": len(waiting), "need": cfg["players"],
            "bots_in": max(0, gc.bot_fill_seconds - int(time.time() - row["created_at"]))
            if cfg["mode"] == "free" and gc.bot_fill_seconds else None,
            "can_bots": cfg["mode"] == "free"}


async def queue_bots(db: GCDatabase, tg: int) -> dict:
    """صف آزاد: بازیکن نمی خواهد منتظر بماند؛ هر که الان در صف است با ربات ها سر یک میز."""
    row = await db.queue_row(tg)
    if not row or row["claimed"]:
        return await queue_status(db, tg)
    cfg = json.loads(row["cfg"])
    if cfg["mode"] != "free":
        raise GCError("need_players")
    key = cfg_key(cfg)
    if not await db.lock("mm:" + key):
        raise GCError("busy")
    try:
        rows = await db.queue_waiting(key)
        mine = [r for r in rows if r["tg_id"] == tg]
        if mine:
            others = [r for r in rows if r["tg_id"] != tg][:cfg["players"] - 1]
            await _from_queue(db, cfg, mine + others)
    finally:
        await db.unlock("mm:" + key)
    return await queue_status(db, tg)


async def queue_leave(db: GCDatabase, tg: int) -> dict:
    row = await db.queue_row(tg)
    if not row:
        return {"state": "none"}
    if row["claimed"]:
        await db.queue_del(tg)
        return {"state": "matched", "match": row["claimed"]}
    await db.queue_del(tg)
    if row["held"]:   # صف امتیازی قدیمی
        await earn_legacy(db, tg, row["held"], "refund", f"انصراف از صف {_gname(json.loads(row['cfg']))}", "queue",
                          f"qrefund:{tg}:{row['created_at']}")
    return {"state": "none"}


# ---------- میز دعوت ----------
async def invite_create(db: GCDatabase, tg: int, raw_cfg: dict) -> dict:
    cfg = norm_cfg(raw_cfg)
    if cfg["mode"] != "free":     # رتبه ای فقط با صف آنلاین (میز رفیقا جام نمی دهد)
        raise GCError("ranked_online")
    if await db.active_match_of(tg):
        raise GCError("in_match")
    if await db.queue_row(tg):
        await queue_leave(db, tg)
    mid, code = _code(10), _code(6)
    colors = _seat_order(cfg)
    paid, ref = 0, f"{mid}:{tg}:{int(time.time() * 1000)}"
    info = await _seat_info(db, tg)
    state = {"lobby": True, "seats": [{"color": colors[0], "tg": tg, "paid": paid, "ref": ref, **info}]}
    await db.create_match(mid, "lobby", cfg, state, tg, invite=code)
    await db.add_match_player(mid, tg, colors[0], paid)
    return {"match": mid, "code": code}


async def invite_join(db: GCDatabase, tg: int, code: str) -> dict:
    m = await db.match_by_invite(code.strip().upper()[:12])
    if not m:
        raise GCError("bad_invite")
    rows = await db.match_players(m["id"])
    if any(r["tg_id"] == tg for r in rows):
        return {"match": m["id"]}
    if m["status"] != "lobby":
        raise GCError("started")
    other = await db.active_match_of(tg)
    if other:
        raise GCError("in_match", match=other)
    cfg = m["cfg"]
    if cfg["mode"] != "free":     # میز امتیازی قدیمی که هنوز باز مانده: کسی تازه نمی نشیند
        raise GCError("started")
    paid, ref = 0, f"{m['id']}:{tg}:{int(time.time() * 1000)}"
    info = await _seat_info(db, tg)

    def sit(mm: dict):
        seats = mm["state"].get("seats", [])
        if mm["status"] != "lobby":
            return False, "started"
        if any(s["tg"] == tg for s in seats):
            return False, None
        free = [c for c in _seat_order(cfg) if c not in {s["color"] for s in seats}]
        if not free:
            return False, "full"
        seats.append({"color": free[0], "tg": tg, "paid": paid, "ref": ref, **info})
        return True, free[0]

    try:
        mm, color = await mutate(db, m["id"], sit)
    except GCError:
        color = "busy"
    if color in ("full", "started", "busy"):
        raise GCError(color)
    if color:
        await db.add_match_player(m["id"], tg, color, paid)
        host = m["host"]
        if host and host != tg and await _away(db, m["id"], host, time.time()):
            await _notify(db, host, f"join:{m['id']}:{tg}", f"{info['name']} نشست سر میز {_gname(cfg)}! زود بیا که منتظرن 😄",
                          _gpage(cfg).replace(".html", "-lobby.html"))
        if len(mm["state"]["seats"]) == cfg["players"]:
            await _lobby_go(db, mm)
        await _hook(db, m["id"])
    return {"match": m["id"]}


async def _lobby_go(db: GCDatabase, m: dict) -> None:
    humans = [{"tg": s["tg"], "paid": s["paid"], "color": s["color"]} for s in m["state"]["seats"]]
    try:
        await _start_game(db, m["id"], m["cfg"], humans, create=False)
    except GCError as e:
        if e.code != "busy":
            raise
    await _jobs(db, await db.get_match(m["id"]))   # اسم‌فامیل: حرف ها از همین حالا آماده شوند


async def lobby_start(db: GCDatabase, tg: int, match_id: str) -> None:
    m = await db.get_match(match_id)
    if not m or m["status"] != "lobby":
        raise GCError("not_found")
    if m["host"] != tg:
        raise GCError("not_host")
    if m["cfg"]["mode"] != "free" and len(m["state"]["seats"]) < m["cfg"]["players"]:
        raise GCError("need_players")
    if game_of(m["cfg"]) in GROUP_ONLY and len(m["state"]["seats"]) < \
            (esmfamil.MIN_PLAYERS if game_of(m["cfg"]) == "esmfamil" else m["cfg"]["players"]):
        raise GCError("need_players")
    await _lobby_go(db, m)
    await _hook(db, match_id)


async def lobby_leave(db: GCDatabase, tg: int, m: dict) -> None:
    if m["host"] == tg:
        def cancel(mm: dict):
            if mm["status"] != "lobby":
                return False, False
            mm["status"] = "cancelled"
            return True, True
        _, ok = await mutate(db, m["id"], cancel)
        if ok:
            for s in m["state"]["seats"]:
                if s["paid"]:
                    await earn_legacy(db, s["tg"], s["paid"], "refund", f"لغو میز {_gname(m['cfg'])}", m["id"], "refund:" + s["ref"])
            await db.deactivate(m["id"])
            await _hook(db, m["id"])
        return

    def stand(mm: dict):
        seats = mm["state"]["seats"]
        if mm["status"] != "lobby" or not any(s["tg"] == tg for s in seats):
            return False, None
        seat = next(s for s in seats if s["tg"] == tg)
        mm["state"]["seats"] = [s for s in seats if s["tg"] != tg]
        return True, seat
    _, seat = await mutate(db, m["id"], stand)
    if seat:
        await db.execute("DELETE FROM match_players WHERE match_id = ? AND tg_id = ?", (m["id"], tg))
        if seat["paid"]:
            await earn_legacy(db, tg, seat["paid"], "refund", f"خروج از میز {_gname(m['cfg'])}", m["id"], "refund:" + seat["ref"])
        await _hook(db, m["id"])


# ---------- بازی ----------
async def _membership(db: GCDatabase, tg: int, match_id: str) -> tuple[list[dict], str]:
    rows = await db.match_players(match_id)
    color = _color_of(rows, tg)
    if color is None:
        raise GCError("not_found")
    return rows, color


def _ticker(now: float, here: str | None = None):
    def fn(m: dict):
        if m["status"] != "playing":
            return False, None
        changed = _eng(m["cfg"]).tick(m["state"], now)
        if here is not None and m["state"].get("game") == "esmfamil":
            changed = esmfamil.arrive(m["state"], here, now) or changed
        if m["state"]["over"]:
            m["status"] = "over"
        return changed, None
    return fn


# ---------- لشگر کاغذی: خط های مداد (جدول ink، جدا از وضعیت میز تا هر poll سنگین نشود) ----------
INK_OPS = 24                 # حداکثر کار نقاشی در هر درخواست
INK_PTS = 400                # حداکثر نقطهٔ هر خط (کلاینت خط بلند را تکه تکه می فرستد)
INK_MAX_STROKES = 900        # خط های زندهٔ هر نفر
INK_MAX_POINTS = 60000       # جمع نقطه های زندهٔ هر نفر
INK_COLORS, INK_WIDTHS = 8, 4
INK_PAGE = 300


def _stroke(raw) -> tuple[str, int] | None:  # noqa: ANN001
    """یک خط مداد: {c: رنگ، w: ضخامت، e: پاک کن، p: [x0, y0, x1, y1, ...]} ← (JSON فشرده، تعداد نقطه)."""
    if not isinstance(raw, dict):
        return None
    pts = raw.get("p")
    if not isinstance(pts, list) or len(pts) < 2 or len(pts) % 2 or len(pts) > INK_PTS * 2:
        return None
    try:
        c, w, e = int(raw.get("c") or 0), int(raw.get("w") or 0), 1 if raw.get("e") else 0
        lim = ((-30, lashgar.W + 30), (-30, lashgar.H + 30))
        out = [max(lim[i % 2][0], min(lim[i % 2][1], int(round(float(v))))) for i, v in enumerate(pts)]
    except (TypeError, ValueError, OverflowError):
        return None
    if not (0 <= c < INK_COLORS and 0 <= w < INK_WIDTHS):
        return None
    return json.dumps({"c": c, "w": w, "e": e, "p": out}, separators=(",", ":")), len(out) // 2


async def ink_post(db: GCDatabase, tg: int, match_id: str, ops) -> dict:  # noqa: ANN001
    """کارهای نقاشی یک نفر به ترتیب: s خط تازه، u برداشتن آخرین خط، c پاک کردن همه؛ فقط پیش از «آماده».
    همه اول سنجیده می شوند تا درخواستی که رد شد نیمه کاره ثبت نشود (کلاینت دوباره می فرستد)."""
    _, color = await _membership(db, tg, match_id)
    m = await db.get_match(match_id)
    if not m or m["status"] != "playing" or game_of(m["cfg"]) != "lashgar":
        raise GCError("not_found")
    st = m["state"]
    if st["phase"] != "draw" or st["players"][color]["out"]:
        raise GCError("not_draw")
    if st["players"][color]["ready"]:
        raise GCError("is_ready")
    if not isinstance(ops, list) or not ops or len(ops) > INK_OPS:
        raise GCError("bad_ink")
    todo = []
    for op in ops:
        kind = op.get("op") if isinstance(op, dict) else None
        if kind == "s":
            got = _stroke(op.get("s"))
            if not got:
                raise GCError("bad_ink")
            todo.append(("s", got))
        elif kind in ("u", "c"):
            todo.append((kind, None))
        else:
            raise GCError("bad_ink")
    n, pts = await db.ink_load(match_id, color)
    add = [g for k, g in todo if k == "s"]
    if not any(k == "c" for k, _ in todo) and (n + len(add) > INK_MAX_STROKES or pts + sum(g[1] for g in add) > INK_MAX_POINTS):
        raise GCError("ink_full")
    ids = []
    for kind, got in todo:
        if kind == "s":
            ids.append(await db.add_ink(match_id, color, "s", got[0], got[1]))
        elif kind == "u":
            ids.append(await db.ink_undo(match_id, color))
        else:
            ids.append(await db.ink_clear(match_id, color))
    now = time.time()
    if now - st["players"][color]["last"] >= lashgar.TOUCH_EVERY:
        await mutate(db, match_id, lambda mm: (mm["status"] == "playing" and lashgar.touch(mm["state"], color, now), None))
    return {"ok": True, "ids": ids, "v": await db.ink_last(match_id, color)}


async def ink_get(db: GCDatabase, tg: int, match_id: str, since: int, snap: bool) -> dict:
    """خط های نقاشی که این بیننده می تواند ببیند: تا شروع جنگ فقط مال خودش (تماشاگر هیچ)، بعد مال هر دو.
    snap: بار اول (یا بعد از شروع جنگ) فقط خط های زنده، صفحه به صفحه؛ بعد کارهای تازه (s، x، c) از since."""
    rows = await db.match_players(match_id)
    color = _color_of(rows, tg)
    m = await db.get_match(match_id)
    if not m or game_of(m["cfg"]) != "lashgar" or m["status"] == "lobby":
        raise GCError("not_found")
    if color is None and not await db.group_table(match_id):
        raise GCError("not_found")
    draw = m["state"]["phase"] == "draw" and color is not None   # تماشاگر همیشه خط های هر دو نفر را می گیرد
    got = await db.ink_since(match_id, max(0, int(since)), color if draw else None, INK_PAGE, snap)
    ops = []
    for r in got:
        o = {"id": r["id"], "c": r["color"], "op": r["op"]}
        if r["op"] == "s":
            o["s"] = json.loads(r["data"])
        elif r["op"] == "x":
            o["ref"] = r["ref"]
        ops.append(o)
    more = len(got) == INK_PAGE
    v = got[-1]["id"] if got else max(0, int(since))
    if snap and not more:            # فهرست خط های زنده تمام شد؛ از این به بعد کارهای تازه از آخرین شماره
        v = max(v, await db.ink_last(match_id, color if draw else None))
    return {"ops": ops, "v": v, "more": more}


# ---------- گفتگوی سر میز ----------
CHAT_MAX = 140
_CHAT_BAD = re.compile(r"[\u0000-\u001f\u007f\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def clean_chat(text: str) -> str:
    """فاصله های اضافه و نویسه های کنترلی و جهت دهی حذف؛ حداکثر ۱۴۰ نویسه."""
    text = _CHAT_BAD.sub(" ", str(text or ""))
    return " ".join(text.split())[:CHAT_MAX]


async def chat_send(db: GCDatabase, tg: int, match_id: str, text: str) -> dict:
    _, color = await _membership(db, tg, match_id)
    m = await db.get_match(match_id)
    if not m or m["status"] not in ("lobby", "playing"):
        raise GCError("not_found")   # بعد از پایان یا بستن میز گفتگو بسته است
    text = clean_chat(text)
    if not text:
        raise GCError("empty")
    # جلوی سیل پیام: یک پیام در ۱٫۵ ثانیه و حداکثر ۱۲ پیام در دقیقه
    if await db.chat_recent(match_id, tg, 1.5) or await db.chat_recent(match_id, tg, 60) >= 12:
        raise GCError("chat_slow")
    cid = await db.add_chat(match_id, tg, color, text)
    return {"ok": True, "id": cid}


async def chat_view(db: GCDatabase, tg: int, match_id: str, since_id: int) -> list[dict]:
    rows = await db.chat_since(match_id, max(0, since_id))
    return [{"id": r["id"], "color": r["color"], "text": r["text"], "at": int(r["created_at"]),
             "name": (r.get("name") or "بازیکن")[:24], "av": int(r.get("av") or 1), "pic": pic_url(r),
             "me": r["tg_id"] == tg, "pid": r.get("pic") if r["tg_id"] != tg else ""} for r in rows]


async def _put_pids(db: GCDatabase, match_id: str, game: dict, viewer: int | None) -> None:
    """کلید عمومی هر بازیکن واقعی (pid) کنار نامش در نمای بازی؛ با لمس آواتار کارت پروفایلش باز می شود.
    آیدی تلگرام بیرون نمی رود و برای خود بیننده و ربات ها pid نیست."""
    players = game.get("players") if isinstance(game, dict) else None
    if not isinstance(players, dict):
        return
    for color, (tg_id, pid) in (await db.match_pids(match_id)).items():
        p = players.get(color)
        if isinstance(p, dict) and not p.get("bot") and tg_id != viewer:
            p["pid"] = pid


async def match_view(db: GCDatabase, tg: int, match_id: str, since: int = 0, chat_since: int | None = None,
                     fresh: dict | None = None) -> dict:
    """fresh: میزی که همین الان (در همین درخواست) خوانده و نوشته شده؛ دوباره خوانده نمی شود."""
    rows = await db.match_players(match_id)
    color = _color_of(rows, tg)
    if color is None:   # تماشاگر: فقط میزهای گروه، فقط وقتی بازی شروع شده؛ بدون برگ کسی و بدون چت
        return await _watch_view(db, match_id, since)
    await db.touch(match_id, tg)
    now = time.time()
    m = fresh if fresh is not None else (await mutate(db, match_id, _ticker(now, color)))[0]
    if m["status"] == "playing":
        await _ping_turn(db, m, tg, now)
    cfg = m["cfg"]
    out = {"id": m["id"], "status": m["status"], "cfg": cfg, "v": m["version"], "me": color}
    if chat_since is not None:
        out["chat"] = await chat_view(db, tg, match_id, chat_since)
    if m["status"] in ("lobby", "cancelled"):
        out["lobby"] = {"seats": [{"color": s["color"], "name": s["name"], "av": s["av"], "pic": s.get("pic", ""),
                                   "me": s["tg"] == tg}
                                  for s in m["state"].get("seats", [])],
                        "code": m["invite"], "host": m["host"] == tg}
        return out
    st = m["state"]
    out["game"] = _eng(cfg).view(st, color, since, now)
    if game_of(cfg) == "lashgar":
        out["game"]["ink_v"] = await db.ink_last(match_id, color if st["phase"] == "draw" else None)
    await _put_pids(db, match_id, out["game"], tg)
    if m["status"] == "over":
        won = color in _winners(st)
        res = await db.result_row(match_id, tg) or {}
        out["result"] = {"won": won, "coins": int(res.get("prize") or 0), "cups": int(res.get("cups") or 0)}
        if cfg["mode"] == "ranked":
            out["result"]["rank"] = r = await db.rank_of(tg, game_of(cfg))
            r["league"] = league(r["cups"])
    return out


async def _watch_view(db: GCDatabase, match_id: str, since: int) -> dict:
    if not match_id or not await db.group_table(match_id):
        raise GCError("not_found")
    now = time.time()
    m = await db.get_match(match_id)
    if not m or m["status"] == "lobby":
        raise GCError("not_found")
    if m["status"] == "playing":
        m, _ = await mutate(db, match_id, _ticker(now))
    st, cfg = m["state"], m["cfg"]
    out = {"id": m["id"], "status": m["status"], "cfg": cfg, "v": m["version"], "watch": True,
           "me": (st.get("order") or [None])[0]}   # صفحه از دید بازیکن اول کشیده می شود
    if m["status"] != "cancelled":
        out["game"] = _eng(cfg).view(st, None, since, now)
        if game_of(cfg) == "lashgar":
            out["game"]["ink_v"] = await db.ink_last(match_id, None)   # تماشاگر نقاشی هر دو را از همان چیدن می بیند
        await _put_pids(db, match_id, out["game"], None)
        out["pot"] = st.get("pot", 0)
    return out


async def my_tables(db: GCDatabase, tg: int) -> list[dict]:
    """میزهای باز کاربر برای صفحهٔ خانه: صف، میز دعوت در انتظار، بازی در جریان."""
    out = []
    q = await db.queue_row(tg)
    if q and not q["claimed"]:
        cfg = json.loads(q["cfg"])
        out.append({"kind": "queue", "game": game_of(cfg), "cfg": cfg,
                    "found": len(await db.queue_waiting(q["cfg_key"])), "need": cfg["players"]})
    for mid in await db.active_matches_of(tg):
        m = await db.get_match(mid)
        if not m:
            continue
        cfg, st = m["cfg"], m["state"]
        rows = await db.match_players(mid)
        me = _color_of(rows, tg)
        t = {"kind": m["status"], "id": mid, "game": game_of(cfg), "cfg": cfg}
        if m["status"] == "lobby":
            seats = st.get("seats", [])
            t.update(found=len(seats), need=cfg["players"], host=m["host"] == tg,
                     players=[{"name": x["name"], "av": x["av"], "pic": x.get("pic", ""), "me": x["tg"] == tg}
                              for x in seats])
        else:
            if st.get("over"):
                continue
            t["players"] = [{"name": st["players"][c]["name"], "av": st["players"][c]["av"],
                             "pic": st["players"][c].get("pic", ""), "bot": st["players"][c]["bot"], "me": c == me}
                            for c in st["order"]]
            t["my_turn"] = _current(st) == me
            if t["game"] == "football" and me is not None:
                mine = int(me)
                t["score"] = [st["score"][mine], st["score"][1 - mine]]
                t["target"] = st["target"]
            if t["game"] == "billiard" and me is not None:
                mine = billiard.team(st["order"].index(me))
                sc = billiard.score(st)
                t["score"] = [sc[mine], sc[1 - mine]]
                t["target"] = 7
            if t["game"] == "divar" and me is not None:
                t["left"] = divar.dist(st, me)
            if t["game"] == "snakes" and me is not None:
                t["pos"] = st["players"][me]["pos"]
            if t["game"] == "lashgar" and me is not None:
                t["phase"] = st["phase"]
                if st["phase"] == "battle":
                    t["alive"] = [lashgar.alive(st["players"][me]), lashgar.alive(st["players"][lashgar._foe(st, me)])]
            if t["game"] == "hokm" and me is not None:
                mine = int(me) % 2
                t["score"] = [st["score"][mine], st["score"][1 - mine]]
                t["target"] = st["target"]
        out.append(t)
    return out


async def _ping_turn(db: GCDatabase, m: dict, asker: int, now: float) -> None:
    """نوبت کسی رسیده که بیرون از مینی اپ است: در ربات خبرش کن (حداکثر دو بار در هر بازی)."""
    st = m["state"]
    if st.get("game") == "lashgar" and st["phase"] == "draw":
        idle = lashgar.nudge_due(st, now)
        uid = st["players"][idle]["uid"] if idle else None
        if uid and uid != asker and await _away(db, m["id"], uid, now):
            await _notify(db, uid, f"lnudge:{m['id']}:{uid}",
                          "حریفت ارتششو چیده و آماده‌ست! 🪖 زود بیا اسم لشگر و نیروهاتو بچین اگه تا 5 دقیقهٔ دیگه "
                          "دست به برگه نزنی بقیهٔ نیروهات خودکار چیده می‌شه و جنگ شروع می‌شه", _gpage(m["cfg"]))
        return
    cur = _current(st)
    if st["over"] or cur is None:
        return
    p = st["players"][cur]
    uid = p.get("uid")
    if p["bot"] or not uid or uid == asker or not await _away(db, m["id"], uid, now):
        return
    if await db.ping_count(f"turn:{m['id']}:{uid}:") >= 2:
        return
    hk, fb, bl = st.get("game") == "hokm", st.get("game") == "football", st.get("game") == "billiard"
    dv, lg, sn = st.get("game") == "divar", st.get("game") == "lashgar", st.get("game") == "snakes"
    team_game = hk or ((bl or dv) and st.get("n") == 4) or (sn and st.get("n", 2) > 2)
    extra = " 3 بار نوبت سوختن پشت هم یعنی باخت" if lg else \
        (" تو بازی رتبه‌ای 3 بار غیبت یعنی بیرون رفتن از بازی" if team_game else " تو بازی رتبه‌ای 3 بار غیبت یعنی باخت") \
        if st.get("stake") else ""
    what = ("حکم رو انتخاب کن" if st["phase"] == "trump" else "برگتو بنداز") if hk \
        else "شوتتو بزن وگرنه توپ می‌ره دست حریف" if fb \
        else "ضربه‌تو بزن وگرنه حریف توپو دستش می‌گیره 🎱" if bl \
        else "یه قدم برو یا یه دیوار بذار وگرنه یه قدم به جات برمی‌داریم 🧱" if dv \
        else "نقطه رو بذار و برگه رو تا کن وگرنه نوبتت می‌سوزه 💥" if lg \
        else "تاسو بریز وگرنه خودمون جات می‌ریزیم 🎲" if sn else "وگرنه ربات جات تاس می‌ریزه 🎲"
    await _notify(db, uid, f"turn:{m['id']}:{uid}:{st.get('turn_id', 0)}",
                  f"نوبت توئه داش تو {_gname(m['cfg'])}! {st.get('turn_s', gc.turn_seconds)} ثانیه وقت داری {what}{extra}",
                  _gpage(m["cfg"]))


async def admin_close(db: GCDatabase, match_id: str) -> dict:
    """بستن میز گیرکرده توسط ادمین: میز لغو و ورودی میزهای امتیازی قدیمی به legacy_points برمی گردد."""
    m = await db.get_match(match_id)
    if not m or m["status"] not in ("lobby", "playing"):
        raise GCError("not_open")

    def cancel(mm: dict):
        if mm["status"] not in ("lobby", "playing"):
            return False, False
        mm["status"] = "cancelled"
        return True, True

    _, ok = await mutate(db, match_id, cancel)
    if not ok:
        raise GCError("not_open")
    refunded = 0
    if m["status"] == "lobby":
        for seat in m["state"].get("seats", []):
            if seat.get("paid") and await earn_legacy(db, seat["tg"], seat["paid"], "refund", "بستن میز توسط پشتیبانی",
                                                      match_id, "refund:" + seat["ref"]):
                refunded += seat["paid"]
    else:
        for r in await db.match_players(match_id):
            if r["paid"] and await earn_legacy(db, r["tg_id"], r["paid"], "refund", "بستن میز توسط پشتیبانی",
                                               match_id, f"cancel:{match_id}:{r['tg_id']}"):
                refunded += r["paid"]
    await db.mark_settled(match_id)
    await db.deactivate(match_id)
    log.warning("میز %s توسط ادمین بسته شد؛ %s امتیاز برگشت", match_id, refunded)
    await _hook(db, match_id)
    return {"refunded": refunded}


async def act(db: GCDatabase, tg: int, match_id: str, action: str, k: int | None = None, since: int = 0,
              data: dict | None = None) -> dict:
    _, color = await _membership(db, tg, match_id)
    now = time.time()

    def fn(m: dict):
        if m["status"] != "playing":
            return False, "over"
        st = m["state"]
        eng = _eng(m["cfg"])
        changed = eng.tick(st, now)
        noop = False
        kk = int(k) if str(k if k is not None else "").lstrip("-").isdigit() else -1
        if action == "leave":
            eng.leave(st, color, now, "left")
            err = None
        elif eng is ludo and action == "roll":
            err = ludo.roll(st, color, now)
        elif eng is ludo and action == "move":
            err = ludo.move(st, color, kk, now)
        elif eng is hokm and action == "trump":
            err = hokm.choose_trump(st, int(color), kk, now)
        elif eng is hokm and action == "play":
            err = hokm.play(st, int(color), kk, now)
        elif eng is football and action == "setup":
            d = data or {}
            err = football.setup(st, color, str(d.get("team") or ""), str(d.get("fa") or ""), str(d.get("fd") or ""), now)
        elif eng is football and action == "shot":
            d = data or {}
            err = football.shot(st, int(color), d.get("i"), d.get("dx"), d.get("dy"), d.get("p"), now)
        elif eng is divar and action == "move":
            d = data or {}
            err = divar.move(st, st["order"].index(color), d.get("r"), d.get("c"), now)
        elif eng is divar and action == "wall":
            d = data or {}
            err = divar.wall(st, st["order"].index(color), d.get("o"), d.get("r"), d.get("c"), now)
        elif eng is snakes and action == "roll":
            err = snakes.roll(st, st["order"].index(color), now)
        elif eng is billiard and action == "shot":
            d = data or {}
            err = billiard.shot(st, st["order"].index(color), d.get("a"), d.get("p"), d.get("sx"), d.get("sy"),
                                d.get("cx"), d.get("cy"), now)
        elif eng is esmfamil and action == "answer":
            err = esmfamil.answer(st, color, (data or {}).get("sheet"), now)
        elif eng is esmfamil and action in ("stop", "submit", "ready"):
            if action != "ready":
                esmfamil.answer(st, color, (data or {}).get("sheet") or {}, now)   # آخرین نوشته ها هم برسد
            err = getattr(esmfamil, action)(st, color, now)
        elif eng is esmfamil and action == "appeal":
            err = esmfamil.appeal(st, color, str((data or {}).get("col") or ""), now)
        elif eng is esmfamil and action == "vote":
            d = data or {}
            err = esmfamil.vote(st, color, str(d.get("key") or ""), bool(d.get("yes")), now)
        elif eng is billiard and action == "aim":
            d = data or {}
            err = billiard.aim(st, st["order"].index(color), d.get("a"), d.get("p"), d.get("cx"), d.get("cy"), now)
            if err == "same":                    # خیلی زود پس از قبلی: چیزی نوشته نمی شود
                err, noop = None, True
        elif eng is lashgar and action == "army":
            err = lashgar.set_army(st, color, (data or {}).get("name"), now)
        elif eng is lashgar and action == "units":
            err = lashgar.set_units(st, color, (data or {}).get("units"), now)
        elif eng is lashgar and action in ("ready", "unready"):
            err = getattr(lashgar, action)(st, color, now)
        elif eng is lashgar and action == "shoot":
            d = data or {}
            err = lashgar.shoot(st, color, d.get("x"), d.get("y"), d.get("a"), now)
        else:
            err = "bad_action"
        if err is None and action not in ("leave", "aim"):   # نشانه گیری بدون ضربه، غیبت را پاک نمی کند
            eng.human_acted(st, color)
        if st["over"]:
            m["status"] = "over"
        return changed or (err is None and not noop), err

    m, err = await mutate(db, match_id, fn)
    if action == "leave":
        await db.deactivate(match_id, tg)
    if err and err not in ("over",):
        raise GCError(err)
    if action in ("aim", "answer", "units"):     # پاسخ سبک: کلاینت نمای کامل را با poll می گیرد
        return {"ok": True}
    # میز همین الان خوانده و (با tick) نوشته شد؛ نما از همان ساخته می شود، نه یک بار دیگر از پایگاه
    return await match_view(db, tg, match_id, since, fresh=m)


async def leave_any(db: GCDatabase, tg: int, match_id: str) -> dict:
    m = await db.get_match(match_id)
    if not m:
        raise GCError("not_found")
    if m["status"] == "lobby":
        await lobby_leave(db, tg, m)
        return {"left": True}
    if m["status"] == "playing":
        return await act(db, tg, match_id, "leave")
    await db.deactivate(match_id, tg)
    return {"left": True}


# ---------- رده بندی ----------
PERIODS = {"week": 7 * 86400, "month": 30 * 86400, "all": None}


async def leaderboard(db: GCDatabase, tg: int, kind: str, period: str) -> dict:
    span = PERIODS.get(period, PERIODS["week"])
    since = int(time.time() - span) if span else 0
    rows = await (db.top_players(since) if kind == "top" else db.top_spenders(since))
    me = await db.get_player(tg) or {}
    mine = await db.my_value(tg, since, kind)
    return {
        "kind": kind, "period": period,
        "rows": [{"name": r["name"] or "بازیکن", "av": r["av"], "pic": pic_url(r), "value": int(r["value"] or 0),
                  "wins": int(r.get("wins") or 0), "me": r["tg_id"] == tg,
                  "pid": r.get("pic") if r["tg_id"] != tg else ""} for r in rows],
        "mine": {"value": int(mine.get("value") or 0), "wins": int(mine.get("wins") or 0),
                 "games": int(mine.get("games") or 0), "visible": kind == "top" or bool(me.get("show_spend"))},
    }


async def game_leaderboard(db: GCDatabase, tg: int, game: str, period: str) -> dict:
    """رده بندی هر بازی جدا (صفحهٔ همان بازی): cup = بیشترین جام رتبه ای، وگرنه بیشترین برد در این بازه."""
    if game not in GAMES:
        raise GCError("bad_game")
    if period == "cup":
        return {
            "game": game, "period": period,
            "rows": [{"name": r["name"] or "بازیکن", "av": r["av"], "pic": pic_url(r), "cups": int(r["cups"]),
                      "league": league(int(r["cups"])), "wins": int(r["wins"]), "games": int(r["games"]),
                      "me": r["tg_id"] == tg, "pid": r.get("pic") if r["tg_id"] != tg else ""} for r in await db.cup_board(game)],
            "mine": {**(mine := await db.cup_rank(tg, game)), "league": league(mine["cups"])},
        }
    span = PERIODS.get(period, PERIODS["week"])
    since = int(time.time() - span) if span else 0
    rows = await db.game_board(game, since)
    return {
        "game": game, "period": period,
        "rows": [{"name": r["name"] or "بازیکن", "av": r["av"], "pic": pic_url(r), "wins": int(r["wins"] or 0),
                  "games": int(r["games"] or 0), "value": int(r["value"] or 0), "me": r["tg_id"] == tg,
                  "pid": r.get("pic") if r["tg_id"] != tg else ""} for r in rows],
        "mine": await db.game_rank(tg, game, since),
    }
