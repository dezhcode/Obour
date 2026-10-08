"""آزمون های Game Club: قواعد منچ و پول بازی امتیازی.

    python -m pytest game_club/test_game_club.py -q
یا بدون pytest:
    python game_club/test_game_club.py
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_club import ludo  # noqa: E402


def _seats(n, bots=True):
    return [{"color": c, "uid": None if bots else i + 1, "name": c, "bot": bots} for i, c in enumerate(ludo.SEATS[n])]


def test_bot_games_finish():
    random.seed(1)
    for _ in range(60):
        n = random.choice([2, 4])
        st = ludo.new_state(_seats(n), random.choice([2, 4]), 0.0, 20, False)
        t = 0.0
        while not st["over"] and t < 20000:
            t += 0.5
            ludo.tick(st, t)
            for c in st["order"]:
                assert all(-1 <= p <= 56 for p in st["pawns"][c])
        assert st["over"] and st["winner"] in st["order"]


def test_turn_rules():
    st = ludo.new_state(_seats(2, bots=False), 2, 0.0, 20, False, first="yellow")
    assert ludo.roll(st, "red", 1) == "not_your_turn"
    assert ludo.roll(st, "yellow", 1, value=3) is None          # بدون ۶ از لانه بیرون نمی آید
    assert ludo.current(st) == "red"
    assert ludo.roll(st, "red", 2, value=6) is None             # همه در لانه: حرکت خودکار
    assert st["pawns"]["red"][0] == 0 and ludo.current(st) == "red"   # ۶ = نوبت اضافه


def test_capture_and_safe():
    st = ludo.new_state(_seats(2, bots=False), 2, 0.0, 20, False, first="yellow")
    st["pawns"]["yellow"] = [10, -1]
    st["pawns"]["red"] = [38, -1]                               # زرد با ۲ به خانه ۵۱ مسیر می رسد؛ قرمز همان جاست
    assert ludo.track_index("red", 38) == ludo.track_index("yellow", 12) == 51
    ludo.roll(st, "yellow", 1, value=2)
    assert st["pawns"]["red"][0] == -1                          # زده شد
    assert ludo.current(st) == "yellow"                         # زدن = نوبت اضافه
    # خانه ستاره امن است: قرمز روی ستاره ۸ (خانه ۲۱ قرمز = ۸)، زرد با رسیدن به آن نمی زند
    st2 = ludo.new_state(_seats(2, bots=False), 2, 0.0, 20, False, first="yellow")
    st2["pawns"]["yellow"] = [19, -1]
    st2["pawns"]["red"] = [ (8 - 13) % 52, -1]
    ludo.roll(st2, "yellow", 1, value=2)
    assert ludo.track_index("yellow", 21) == 8 and st2["pawns"]["red"][0] == (8 - 13) % 52


def test_stake_idle_forfeit():
    st = ludo.new_state(_seats(2, bots=False), 2, 0.0, 20, True, first="yellow")
    t = 0.0
    while not st["over"] and t < 1000:
        t += 1
        ludo.tick(st, t)
    assert st["over"] and any(e["t"] == "leave" and e["why"] == "timeout" for e in st["events"])


def test_stake_money_flow():
    """ورودی، جایزه و بازگشت پول با دو بازیکن واقعی؛ جمع امتیازها ثابت می ماند."""
    tmp = tempfile.mkdtemp()
    os.environ["GAME_CLUB_DB_PATH"] = os.path.join(tmp, "gc.db")

    from game_club import service
    from game_club.db import GCDatabase

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        for tg in (1, 2):
            await db.player(tg, f"p{tg}")
            await db.credit(tg, 500)
        cfg = {"mode": "stake", "entry": 100, "players": 2, "pawns": 2}
        assert (await service.queue_join(db, 1, cfg))["state"] == "waiting"
        assert (await db.get_player(1))["points"] == 400
        r = await service.queue_join(db, 2, cfg)
        assert r["state"] == "matched"
        mid = r["match"]
        # بازیکن ۱ بیرون می رود، ۲ می برد
        await service.leave_any(db, 1, mid)
        p1, p2 = (await db.get_player(1))["points"], (await db.get_player(2))["points"]
        assert (p1, p2) == (400, 600), (p1, p2)
        # تسویه دوباره پولی جابه جا نمی کند
        m = await db.get_match(mid)
        await service.settle(db, m)
        assert (await db.get_player(2))["points"] == 600
        # میز دعوت: نشستن، بلند شدن، دوباره نشستن = دوباره ورودی
        inv = await service.invite_create(db, 1, cfg)
        assert (await db.get_player(1))["points"] == 300
        m = await db.get_match(inv["match"])
        await service.lobby_leave(db, 1, m)                    # میزبان می بندد = بازگشت
        assert (await db.get_player(1))["points"] == 400
        # صف: انصراف = بازگشت
        await service.queue_join(db, 2, cfg)
        assert (await db.get_player(2))["points"] == 500
        await service.queue_leave(db, 2)
        assert (await db.get_player(2))["points"] == 600
        assert (await db.get_player(1))["points"] + (await db.get_player(2))["points"] == 1000
        await db.close()

    asyncio.run(run())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
