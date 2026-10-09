"""آزمون های Game Club: قواعد منچ و پول بازی امتیازی.

    python -m pytest game_club/test_game_club.py -q
یا بدون pytest:
    python game_club/test_game_club.py
"""
from __future__ import annotations

import asyncio
import math
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game_club import hokm, ludo  # noqa: E402


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


def test_buy_obour_plan_with_points():
    """خرید پلن عبور با امتیاز از راه سرویس خرید خود عبور (پنل ساختگی)."""
    import types

    tmp = tempfile.mkdtemp()
    from app.db import Database
    from game_club import bridge
    from game_club.db import GCDatabase

    class Panel:
        base_url = "https://panel.example"

        def __init__(self, fail=False):
            self.fail, self.made = fail, []

        async def username_taken(self, name):
            return False

        async def create_service(self, username, **kw):
            if self.fail:
                from app.panel import PanelSafeError
                raise PanelSafeError("down")
            self.made.append(username)
            return types.SimpleNamespace(subscription_url="/sub/" + username)

        async def remove(self, name):
            pass

        async def get_user(self, name):
            return None

    async def run():
        odb = Database(os.path.join(tmp, "o.db"))
        await odb.connect()
        gdb = GCDatabase(os.path.join(tmp, "gc.db"))
        await gdb.connect()
        u = await odb.get_or_create_user(77, None, "x")
        await odb.execute("INSERT INTO plans(title, data_gb, duration_days, price, is_active) VALUES('p', 10, 30, 95000, 1)")
        plan = (await odb.active_plans())[0]
        await gdb.player(77, "x")
        await gdb.credit(77, 2000)
        pts = bridge.points_for(95000)
        panel = Panel()
        r = await bridge.buy(gdb, odb, panel, None, 77, plan["id"], "buy-test-0001")
        assert r["ok"] and len(panel.made) == 1
        assert (await gdb.get_player(77))["points"] == 2000 - pts
        assert (await odb.get_user(u["id"]))["balance"] == pts * 100 - 95000
        r = await bridge.buy(gdb, odb, panel, None, 77, plan["id"], "buy-test-0001")   # تکرار
        assert r.get("repeat") and len(panel.made) == 1 and (await gdb.get_player(77))["points"] == 2000 - pts
        r = await bridge.buy(gdb, odb, Panel(fail=True), None, 77, plan["id"], "buy-test-0002")
        assert not r["ok"] and r["credited"] == pts * 100              # پول در کیف عبور ماند
        assert (await odb.get_user(u["id"]))["balance"] == 2 * pts * 100 - 95000
        await gdb.close()
        await odb.close()

    asyncio.run(run())


def test_notify_and_admin_close():
    """بازیکنی که بیرون رفته حداکثر دو بار خبر نوبت و یک بار نتیجه می گیرد؛ بستن میز پول را برمی گرداند."""
    import time as _t

    tmp = tempfile.mkdtemp()
    from game_club import service
    from game_club.db import GCDatabase

    sent = []

    async def notifier(tg, text, page):
        sent.append((tg, text[:12], page))

    async def run():
        service.notifier = notifier
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        for tg in (1, 2):
            await db.player(tg, f"p{tg}")
            await db.credit(tg, 500)
        cfg = {"mode": "stake", "entry": 100, "players": 2, "pawns": 2}
        await service.queue_join(db, 1, cfg)
        mid = (await service.queue_join(db, 2, cfg))["match"]
        # فقط بازیکن ۱ صفحه را می پرسد؛ بازیکن ۲ بیرون است. زمان را با ددلاین جلو می بریم.
        for _ in range(40):
            m = await db.get_match(mid)
            if m["status"] != "playing":
                break
            st = m["state"]
            st["deadline"] = st["next_at"] = _t.time() - 1
            await db.save_match(mid, m["version"], m["status"], st)
            await service.match_view(db, 1, mid)
        m = await db.get_match(mid)
        assert m["status"] == "over"
        turn_pings = [x for x in sent if x[0] == 2 and "نوبت" in x[1]]
        assert 1 <= len(turn_pings) <= 2, sent
        # نتیجه برای غایب: هر دو بازیکن غایب اند و هر کدام زودتر سه نوبت جا بیندازد می بازد،
        # پس بازیکن ۲ یا خبر باخت (index) می گیرد یا خبر برد (wallet)
        assert any(x[0] == 2 and x[2] in ("index.html", "wallet.html") and "منچ" in x[1] for x in sent), sent
        # بستن میز دعوت توسط ادمین = بازگشت ورودی
        before = (await db.get_player(1))["points"]
        inv = await service.invite_create(db, 1, cfg)
        assert (await db.get_player(1))["points"] == before - 100
        r = await service.admin_close(db, inv["match"])
        assert r["refunded"] == 100 and (await db.get_player(1))["points"] == before
        assert (await db.get_match(inv["match"]))["status"] == "cancelled"
        st = await db.stats(0)
        assert st["players"] == 2 and st["games"] == 1
        service.notifier = None
        await db.close()

    asyncio.run(run())


def test_telegram_profile():
    """نام کامل و عکس پروفایل از initData تلگرام؛ عکس به صندلی ها، صفحه بازی و رده بندی می رسد."""
    import json as _json
    import time as _t
    from urllib.parse import urlencode

    tmp = tempfile.mkdtemp()
    os.environ["GAME_CLUB_DB_PATH"] = os.path.join(tmp, "gc.db")
    from game_club import auth, service
    from game_club.config import gc as gconf
    from game_club.db import GCDatabase, pic_url

    gconf.token = "123:test"
    user = {"id": 77, "first_name": "علی", "last_name": "<b>رضایی</b>", "username": "ali",
            "photo_url": "https://t.me/i/userpic/320/abc.jpg"}
    fields = {"auth_date": str(int(_t.time())), "user": _json.dumps(user, ensure_ascii=False)}
    u = auth.verify(urlencode({**fields, "hash": auth.sign(fields)}))
    assert u.full_name == "علی <b>رضایی</b>" and u.photo_url.startswith("https://t.me/")
    bad = dict(fields, user=_json.dumps({**user, "photo_url": "javascript:alert(1)"}))
    assert auth.verify(urlencode({**bad, "hash": auth.sign(bad)})).photo_url == ""

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        p = await db.player(77, u.full_name, u.username, u.photo_url)
        assert p["name"] == "علی bرضایی/b" and pic_url(p) == user["photo_url"]   # نویسه های HTML حذف می شوند
        assert len(p["pic"]) >= 8 and await db.player_by_pic(p["pic"])
        p2 = await db.player(78, "سارا", None, "")                                # عکس پنهان: آدرس /gc/pic
        assert pic_url(p2) == "pic/" + p2["pic"]
        assert pic_url(await db.player(78, "سارا", None, None)) == "pic/" + p2["pic"]   # پیام ربات عکس را پاک نمی کند
        try:
            r = await service.invite_create(db, 77, {"mode": "free", "entry": 0, "players": 2, "pawns": 2})
            lobby = (await service.match_view(db, 77, r["match"]))["lobby"]["seats"]
            assert [x["pic"] for x in lobby] == [user["photo_url"]]
            await service.invite_join(db, 78, r["code"])                       # میز دو نفره پر شد و شروع می شود
            game = (await service.match_view(db, 78, r["match"]))["game"]
            assert {x["pic"] for x in game["players"].values()} == {user["photo_url"], "pic/" + p2["pic"]}
        finally:
            await db.close()

    asyncio.run(run())


def test_table_chat():
    """گفتگوی سر میز: فقط بازیکن های میز، پاک سازی متن، محدودیت سرعت، تحویل با match_view."""
    tmp = tempfile.mkdtemp()
    os.environ["GAME_CLUB_DB_PATH"] = os.path.join(tmp, "gc.db")
    from game_club import service
    from game_club.db import GCDatabase

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        try:
            for tg, n in ((1, "علی"), (2, "سارا"), (3, "غریبه")):
                await db.player(tg, n)
            r = await service.invite_create(db, 1, {"mode": "free", "entry": 0, "players": 2, "pawns": 2})
            await service.invite_join(db, 2, r["code"])
            mid = r["match"]
            await service.chat_send(db, 1, mid, "  سلام\u202e   <b>خوش‌بازی</b>\n ")
            for bad, code in (("   ", "empty"), ("دوباره", "chat_slow")):
                try:
                    await service.chat_send(db, 1, mid, bad)
                    raise AssertionError(code)
                except service.GCError as e:
                    assert e.code == code
            try:
                await service.chat_send(db, 3, mid, "سلام")                  # کسی که سر میز نیست
                raise AssertionError("outsider")
            except service.GCError as e:
                assert e.code == "not_found"
            await service.chat_send(db, 2, mid, "x" * 500)
            v = await service.match_view(db, 2, mid, 0, 0)
            assert [m["text"] for m in v["chat"]] == ["سلام <b>خوش‌بازی</b>", "x" * 140]   # متن خام؛ مینی اپ با textContent نشان می دهد
            assert [m["me"] for m in v["chat"]] == [False, True] and v["chat"][0]["name"] == "علی"
            assert (await service.match_view(db, 2, mid, 0, v["chat"][-1]["id"]))["chat"] == []
            assert "chat" not in await service.match_view(db, 2, mid, 0)
            # پایان بازی: گفتگوی میز پاک می شود و دیگر پیامی پذیرفته نمی شود
            await service.leave_any(db, 1, mid)
            assert (await db.get_match(mid))["status"] == "over"
            assert await db.chat_since(mid, 0) == []
            try:
                await service.chat_send(db, 2, mid, "خداحافظ")
                raise AssertionError("chat after over")
            except service.GCError as e:
                assert e.code == "not_found"
        finally:
            await db.close()

    asyncio.run(run())



def test_shop_off_by_default():
    """فروشگاه پیش فرض خاموش است: فهرست، خرید و انتقال همه shop_off می دهند."""
    import types

    from game_club import api
    from game_club.config import gc as gconf
    from game_club.service import GCError

    assert gconf.shop_enabled is False
    user = types.SimpleNamespace(id=1, first_name="x", username=None)
    for name, method in (("shop", "GET"), ("shop/buy", "POST"), ("shop/transfer", "POST")):
        try:
            asyncio.run(api.handle(name, method, user, {}, {"plan_id": 1, "points": 100, "idem": "x" * 16}))
            raise AssertionError(name + " worked while the shop is off")
        except GCError as e:
            assert e.code == "shop_off", e.code


# ---------- حکم ----------
def _card(s, r):
    """خال (۰ پیک، ۱ دل، ۲ خشت، ۳ گشنیز) و ارزش (۲ تا ۱۴)."""
    return s * 13 + (r - 2)


def test_hokm_rules():
    """برنده دور، اجبار به خال شروع، کوت و چرخش حاکم."""
    S, H, D, C = 0, 1, 2, 3
    # بدون حکم در دور: بزرگ ترین دل برنده است؛ برگ خال دیگر حتی آس هم نمی برد
    assert hokm.trick_winner([[0, _card(H, 10)], [1, _card(H, 13)], [2, _card(C, 14)], [3, _card(H, 3)]], S) == 1
    # یک پیک کوچک (حکم) همه را می برد؛ دو حکم: بزرگ تر
    assert hokm.trick_winner([[0, _card(H, 14)], [1, _card(S, 2)], [2, _card(H, 13)], [3, _card(D, 14)]], S) == 1
    assert hokm.trick_winner([[0, _card(H, 14)], [1, _card(S, 2)], [2, _card(S, 9)], [3, _card(H, 3)]], S) == 2

    seats = [{"color": s, "uid": i + 1, "name": s, "bot": False} for i, s in enumerate(hokm.SEATS)]
    st = hokm.new_state(seats, 0.0, 20, False, 7, hakem=0)
    assert st["phase"] == "trump" and all(len(st["hands"][s]) == 5 for s in hokm.SEATS)
    assert hokm.play(st, 0, st["hands"]["0"][0], 2.0) == "not_play_phase"
    assert hokm.choose_trump(st, 1, S, 2.0) == "not_your_turn"
    assert hokm.choose_trump(st, 0, S, 2.0) is None
    assert all(len(st["hands"][s]) == 13 for s in hokm.SEATS)
    assert sum(len(st["hands"][s]) for s in hokm.SEATS) == 52 and len({c for s in hokm.SEATS for c in st["hands"][s]}) == 52
    # اجبار خال: دست ها را خودمان می چینیم
    st["hands"]["0"] = [_card(H, 9)]
    st["hands"]["1"] = [_card(H, 4), _card(S, 14)]
    assert hokm.play(st, 1, _card(H, 4), 2.0) == "not_your_turn"
    assert hokm.play(st, 0, _card(H, 9), 2.0) is None
    assert hokm.legal(st, 1) == [_card(H, 4)]
    assert hokm.play(st, 1, _card(S, 14), 2.0) == "illegal_card"

    # کوت: تیم حاکم (۰ و ۲) هفت به صفر می برد = ۲ امتیاز و حاکم می ماند
    st = hokm.new_state(seats, 0.0, 20, False, 7, hakem=0)
    st.update(phase="collect", trick=[[0, 0]], turn=0, tricks=[7, 0], next_at=0)
    hokm._after_collect(st, 1.0)
    assert st["score"] == [2, 0] and st["hakem"] == 0 and st["events"][-1]["kot"]
    # تیم حاکم کوت می شود = ۳ امتیاز برای حریف و حکم به نفر بعدی می رسد
    st = hokm.new_state(seats, 0.0, 20, False, 7, hakem=0)
    st.update(phase="collect", trick=[[1, 0]], turn=1, tricks=[0, 7], next_at=0)
    hokm._after_collect(st, 1.0)
    assert st["score"] == [0, 3] and st["hakem"] == 1
    # برد عادی ۷ به ۴ = ۱ امتیاز؛ رسیدن به هدف = پایان بازی
    st = hokm.new_state(seats, 0.0, 20, False, 3, hakem=2)
    st.update(phase="collect", trick=[[0, 0]], turn=0, tricks=[7, 4], score=[2, 1], next_at=0)
    hokm._after_collect(st, 1.0)
    assert st["over"] and st["winner"] == 0 and st["score"] == [3, 1]
    assert hokm.winners(st) == {"0", "2"}


def test_hokm_bot_games_finish():
    for _ in range(40):
        seats = [{"color": s, "uid": None, "name": s, "bot": True} for s in hokm.SEATS]
        st = hokm.new_state(seats, 0.0, 20, False, random.choice((3, 7)))
        t = 0.0
        while not st["over"]:
            t += 2.0
            hokm.tick(st, t)
            assert t < 20000
        assert max(st["score"]) >= st["target"]


def test_hokm_service_flow():
    """تمرین با ربات تا آخر، و میز دعوت امتیازی: اولین مهمان یار سازنده است و جایزه بین دو برنده تقسیم می شود."""
    tmp = tempfile.mkdtemp()
    os.environ["GAME_CLUB_DB_PATH"] = os.path.join(tmp, "gc.db")
    from game_club import service
    from game_club.db import GCDatabase

    clock = [1000.0]
    real = service.time.time
    service.time.time = lambda: clock[0]

    async def play_out(db, tgs, mid):
        for _ in range(3000):
            clock[0] += 0.7
            done = True
            for tg in tgs:
                v = await service.match_view(db, tg, mid, 0)
                if v["status"] != "playing":
                    continue
                done = False
                g = v["game"]
                if g["turn"] != v["me"]:
                    continue
                if g["phase"] == "trump":
                    await service.act(db, tg, mid, "trump", 1)
                elif g["legal"]:
                    await service.act(db, tg, mid, "play", g["legal"][-1])
            if done:
                return
        raise AssertionError("game did not finish")

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        try:
            for tg in (1, 2, 3, 4):
                await db.player(tg, f"p{tg}")
                await db.credit(tg, 1000)
            r = await service.queue_join(db, 1, {"game": "hokm", "mode": "free", "target": 3, "solo": True})
            assert r["state"] == "matched"
            m = await db.get_match(r["match"])
            assert m["cfg"]["game"] == "hokm" and await db.match_game(r["match"]) == "hokm"
            v = await service.match_view(db, 1, r["match"], 0)
            assert v["me"] == "0" and len(v["game"]["hand"]) == 5 and sum(p["bot"] for p in v["game"]["players"].values()) == 3
            await play_out(db, [1], r["match"])
            assert (await db.get_match(r["match"]))["status"] == "over"

            cfg = {"game": "hokm", "mode": "stake", "entry": 100, "target": 3}
            inv = await service.invite_create(db, 1, cfg)
            for tg in (2, 3, 4):
                await service.invite_join(db, tg, inv["code"])
            rows = {r["tg_id"]: r["color"] for r in await db.match_players(inv["match"])}
            assert rows == {1: "0", 2: "2", 3: "1", 4: "3"}, rows          # ۲ یار سازنده است
            assert [(await db.get_player(tg))["points"] for tg in (1, 2, 3, 4)] == [900] * 4
            await play_out(db, [1, 2, 3, 4], inv["match"])
            m = await db.get_match(inv["match"])
            win = m["state"]["winner"]
            pts = {tg: (await db.get_player(tg))["points"] for tg in (1, 2, 3, 4)}
            winners = {tg for tg, c in rows.items() if int(c) % 2 == win}
            assert all(pts[tg] == 1100 for tg in winners) and all(pts[tg] == 900 for tg in pts if tg not in winners), pts
            assert sum(pts.values()) == 4000
            await service.settle(db, m)                                      # تسویه دوباره چیزی جابه جا نمی کند
            assert {tg: (await db.get_player(tg))["points"] for tg in (1, 2, 3, 4)} == pts
        finally:
            await db.close()
            service.time.time = real

    asyncio.run(run())

def test_hakem_ace_draw_and_intro():
    # اولین آس حاکم را تعیین می کند و پیش از پخش، رویداد hakem با همه برگ ها می آید
    for _ in range(200):
        i, draw = hokm.draw_hakem()
        assert draw and hokm.rank(draw[-1][1]) == 12 and all(hokm.rank(c) != 12 for _, c in draw[:-1])
        assert draw[-1][0] == hokm.SEATS[i]
        assert all(draw[k + 1][0] == hokm.SEATS[(int(draw[k][0]) + 1) % 4] for k in range(len(draw) - 1))
    seats = [{"color": s, "name": s, "bot": s != "0"} for s in hokm.SEATS]
    st = hokm.new_state(seats, 1000.0, 20, False, 7)
    kinds = [e["t"] for e in st["events"]]
    assert kinds[:2] == ["hakem", "deal"], kinds
    intro = st["events"][0]
    assert intro["c"] == hokm.SEATS[st["hakem"]] and hokm.rank(intro["draw"][-1][1]) == 12
    # ربات حاکم تا تمام شدن انیمیشن آس کشی و پخش و کمی فکر، حکم نمی کند
    wait = hokm.START_GRACE + hokm.draw_time(len(intro["draw"])) + hokm.DEAL_ANIM
    if st["hakem"] != 0:
        assert st["next_at"] >= 1000.0 + wait + hokm.TRUMP_THINK - 1e-6
        assert not hokm.tick(st, 1000.0 + wait) and st["phase"] == "trump"
    # دست بعد: hakem بدون draw و با حاکم قبلی
    st2 = hokm.new_state(seats, 0.0, 20, False, 7, hakem=1)
    st2["prev_hakem"], st2["hand_no"] = 1, 1
    hokm._start_hand(st2, 50.0)
    e = [x for x in st2["events"] if x["t"] == "hakem"][-1]
    assert e["draw"] is None and e["prev"] == "1" and e["hand"] == 1


def test_queue_waits_for_full_table_and_bots_on_request():
    tmp = tempfile.mkdtemp()
    from game_club import service
    from game_club.db import GCDatabase

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        real = service.time.time
        clock = [10_000.0]
        service.time.time = lambda: clock[0]
        try:
            for tg in (1, 2, 3):
                await db.player(tg, f"p{tg}")
            cfg = {"game": "hokm", "mode": "free", "target": 3}
            assert (await service.queue_join(db, 1, cfg))["state"] == "waiting"
            assert (await service.queue_join(db, 2, cfg))["state"] == "waiting"
            clock[0] += 600                       # ده دقیقه بعد هم ربات خودکار نمی نشیند
            st = await service.queue_status(db, 1)
            assert st["state"] == "waiting" and st["bots_in"] is None and st["can_bots"] and st["found"] == 2
            # میزهای باز در خانه: صف
            tables = await service.my_tables(db, 2)
            assert tables and tables[0]["kind"] == "queue" and tables[0]["game"] == "hokm"
            # بازیکن ۱ نمی خواهد منتظر بماند: هر دو با دو ربات سر یک میز
            r = await service.queue_bots(db, 1)
            assert r["state"] == "matched"
            r2 = await service.queue_status(db, 2)
            assert r2 == {"state": "matched", "match": r["match"]}
            m = await db.get_match(r["match"])
            assert sum(1 for p in m["state"]["players"].values() if not p["bot"]) == 2
            tables = await service.my_tables(db, 1)
            assert [t["kind"] for t in tables] == ["playing"] and tables[0]["id"] == r["match"]
            assert tables[0]["score"] == [0, 0] and len(tables[0]["players"]) == 4
            # میز دعوت: در انتظار بقیه در خانه دیده می شود
            inv = await service.invite_create(db, 3, cfg)
            t3 = await service.my_tables(db, 3)
            assert t3[0]["kind"] == "lobby" and t3[0]["id"] == inv["match"] and t3[0]["found"] == 1 and t3[0]["need"] == 4
            # بازی امتیازی با ربات پر نمی شود
            await db.credit(3, 500)
            m3 = await db.get_match(inv["match"])
            await service.lobby_leave(db, 3, m3)
            await service.queue_join(db, 3, {"game": "hokm", "mode": "stake", "entry": 100, "target": 3})
            try:
                await service.queue_bots(db, 3)
                raise AssertionError("stake queue must not take bots")
            except service.GCError as e:
                assert e.code == "need_players"
        finally:
            service.time.time = real
            await db.close()

    asyncio.run(run())


def test_football_physics_and_rules():
    from game_club import football as F
    seats = [{"color": "0", "name": "a", "uid": 1}, {"color": "1", "name": "b", "bot": True}]
    st = F.new_state(seats, 0.0, 20, False, 3, first=0)
    assert st["phase"] == "setup" and len(st["pos"]) == 13
    assert F.setup(st, "0", "nope", "132", "132", 1.0) == "bad_setup"
    assert F.setup(st, "0", "eagles", "141", "123", 1.0) is None
    assert st["phase"] == "play" and st["turn"] == 0
    assert F.shot(st, 0, 4, 0, -1, 1, 1.0) == "not_ready"            # هنوز نمایش «مقابل» است
    assert F.shot(st, 1, 4, 0, -1, 1, 99.0) == "not_your_turn"
    assert F.shot(st, 0, 9, 0, -1, 1, 99.0) == "bad_shot"
    # شوت مستقیم به دروازه بالا = گل صندلی ۰، بعد شروع با حریف
    st["pos"][F.BALL] = [300.0, 120.0]
    st["pos"][4] = [300.0, 200.0]
    for k in range(6, 12):
        st["pos"][k] = [40.0 + (k - 6) * 80, 980.0]
    assert F.shot(st, 0, 4, 0, -1, 0.6, 99.0) is None
    kinds = [e["t"] for e in st["events"][-3:]]
    assert kinds == ["shot", "goal", "reset"] and st["score"] == [1, 0] and st["turn"] == 1
    shot_e = st["events"][-3]
    assert shot_e["frames"] and len(shot_e["frames"][0]) == 2 * len(shot_e["ids"])
    # همه چیز داخل زمین یا تور می ماند و ربات بازی را تمام می کند
    for _ in range(3):
        st = F.new_state([{"color": "0", "name": "a", "bot": True}, {"color": "1", "name": "b", "bot": True}], 0.0, 20, False, 3)
        now = 0.0
        while not st["over"] and now < 3000:
            now += 0.5
            F.tick(st, now)
            for x, y in st["pos"]:
                assert -1 <= x <= F.W + 1 and -F.GOAL_D - 1 <= y <= F.H + F.GOAL_D + 1
        assert st["over"] and max(st["score"]) == 3 and F.winners(st) == {F.SEATS[st["winner"]]}
    # فقط فریم های آخرین شوت نگه داشته می شود
    assert sum(1 for e in st["events"] if e.get("frames")) <= 1
    # غیبت در بازی امتیازی: سه نوبت = باخت
    st = F.new_state([{"color": "0", "name": "a", "uid": 1}, {"color": "1", "name": "b", "uid": 2}], 0.0, 20, True, 3, first=0)
    now = F.SETUP_S + 1
    F.tick(st, now)
    assert st["phase"] == "play" and st["players"]["0"]["team"] and st["players"]["1"]["team"]
    for _ in range(12):
        now += 30
        F.tick(st, now)
        if st["over"]:
            break
    assert st["over"] and st["winner"] in (0, 1)


def test_football_pass_gives_extra_turn():
    from game_club import football as F
    st = F.new_state([{"color": "0", "name": "a", "uid": 1}, {"color": "1", "name": "b", "uid": 2}], 0.0, 20, False, 3, first=0)
    F.setup(st, "0", "eagles", "132", "132", 1.0)
    F.setup(st, "1", "lions", "132", "132", 1.0)
    park = [[40.0 + k * 50, 520.0] for k in range(12)]

    def lineup():
        st["pos"] = [p[:] for p in park] + [[300.0, 820.0]]
        st["pos"][0] = [300.0, 900.0]          # شوت زننده پشت توپ
        st["pos"][1] = [300.0, 640.0]          # یار جلوتر در مسیر توپ
        for k in range(6, 12):
            st["pos"][k] = [60.0 + (k - 6) * 96, 120.0]
        st["next_at"] = 0
    for n in range(1, F.MAX_PASS + 1):
        lineup()
        assert F.shot(st, 0, 0, 0, -1, .5, 100.0 * n) is None
        assert st["turn"] == 0 and st["streak"] == n, (n, st["turn"], st["streak"])
        e = [x for x in st["events"] if x["t"] == "pass"][-1]
        assert e["d"] == 1 and e["n"] == n
        # توپ به گیرنده چسبیده: درست جلوی آن رو به دروازه حریف، و رویداد شوت جای قبلی را نگه داشته
        dx, dy = st["pos"][1]
        assert e["ball"] == st["pos"][F.BALL] == [dx, round(dy - F.DISC_R - F.BALL_R - 1, 1)]
        sh = [x for x in st["events"] if x["t"] == "shot"][-1]
        assert sh["pos"][F.BALL] != e["ball"]
        assert st["hold"] == 1 and F.view(st, "0", 0, 0.0)["hold"] == 1
    # مهره ای که توپ را دارد به هر طرف شوت بزند، اول زیر توپ می آید: توپ در جهت شوت جلویش است
    st["next_at"] = 0
    dx, dy = st["pos"][1]
    assert F.shot(st, 0, 1, 1, 0, .4, 950.0) is None
    sh = [x for x in st["events"] if x["t"] == "shot"][-1]
    assert sh["hold"] == [round(dx + F.HOLD_GAP, 1), dy] and st["hold"] is None
    assert F.BALL in sh["ids"] and sh["pos"][F.BALL][0] > dx + F.HOLD_GAP
    st["turn"], st["streak"] = 0, F.MAX_PASS     # پاس ها به سقف رسیده
    lineup()                                   # پاس چهارم: نوبت دیگر اضافه نمی شود
    F.shot(st, 0, 0, 0, -1, .5, 900.0)
    assert st["turn"] == 1 and st["streak"] == 0 and st["stats"]["0"]["passes"] == F.MAX_PASS
    # برخورد مهره خودم (نه توپ) به یار پاس نیست
    res = F.simulate([[300.0, 900.0], [300.0, 760.0]] + [[40.0 + k * 50, 300.0] for k in range(10)] + [[500.0, 600.0]], {0: (0, -1500)})
    assert F.pass_of(0, 0, res) is None
    # جلوی گیرنده دیواره است: توپ کج تر می چسبد؛ صندلی ۱ رو به پایین
    pos = [[40.0 + k * 50, 520.0] for k in range(12)] + [[300.0, 500.0]]
    pos[1] = [300.0, 30.0]
    b = F.catch_pos(pos, 0, 1)
    assert b and b[1] >= F.BALL_R and abs(math.hypot(b[0] - 300.0, b[1] - 30.0) - (F.DISC_R + F.BALL_R + 1)) < .2
    pos[7] = [300.0, 300.0]
    assert F.catch_pos(pos, 1, 7) == [300.0, 355.0]


def test_football_service_flow():
    from game_club import service
    from game_club.db import GCDatabase
    tmp = tempfile.mkdtemp()

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        real = service.time.time
        clock = [50_000.0]
        service.time.time = lambda: clock[0]
        try:
            for tg in (1, 2):
                await db.player(tg, f"p{tg}")
                await db.credit(tg, 1000)
            # تمرین با ربات
            r = await service.queue_join(db, 1, {"game": "football", "mode": "free", "target": 3, "solo": True})
            mid = r["match"]
            v = await service.match_view(db, 1, mid)
            assert v["game"]["phase"] == "setup" and v["cfg"]["players"] == 2
            v = await service.act(db, 1, mid, "setup", data={"team": "sea", "fa": "123", "fd": "141"})
            assert v["game"]["phase"] == "play"
            assert (await service.my_tables(db, 1))[0]["score"] == [0, 0]
            await service.leave_any(db, 1, mid)
            assert (await db.get_match(mid))["status"] == "over"
            # بازی امتیازی با دعوت: برنده کل ورودی ها را می برد
            cfg = {"game": "football", "mode": "stake", "entry": 100, "target": 3}
            inv = await service.invite_create(db, 1, cfg)
            await service.invite_join(db, 2, inv["code"])
            m = await db.get_match(inv["match"])
            assert m["status"] == "playing"
            for tg in (1, 2):
                await service.act(db, tg, inv["match"], "setup", data={"team": "eagles", "fa": "132", "fd": "132"})
            m = await db.get_match(inv["match"])
            kits = {s: p["kit"] for s, p in m["state"]["players"].items()}
            assert sorted(kits.values()) == ["away", "home"]                  # تیم یکسان: یکی لباس مهمان
            for _ in range(400):
                m = await db.get_match(inv["match"])
                if m["status"] != "playing":
                    break
                st = m["state"]
                clock[0] = max(clock[0], st["next_at"]) + 0.1
                seat = st["turn"]
                tg = [1, 2][seat] if (await db.match_players(inv["match"]))[0]["color"] == "0" else [2, 1][seat]
                rows = {r["color"]: r["tg_id"] for r in await db.match_players(inv["match"])}
                tg = rows[str(seat)]
                bx, by = st["pos"][12]
                x, y = st["pos"][seat * 6 + 4]
                await service.act(db, tg, inv["match"], "shot", data={"i": 4, "dx": bx - x, "dy": by - y, "p": 0.9})
            m = await db.get_match(inv["match"])
            assert m["status"] == "over", m["state"]["score"]
            pts = sorted([(await db.get_player(1))["points"], (await db.get_player(2))["points"]])
            assert pts == [900, 1100], pts
        finally:
            service.time.time = real
            await db.close()

    asyncio.run(run())


def test_admin_panel():
    """پنل مدیریت: فقط ادمین، آمار، جستجو، تغییر امتیاز، مسدود کردن، تنظیمات زنده و پیام همگانی."""
    tmp = tempfile.mkdtemp()
    from app.config import config as obour_cfg
    from game_club import admin, service
    from game_club.bot import gcrt
    from game_club.config import gc
    from game_club.db import GCDatabase

    class FakeBot:
        def __init__(self):
            self.sent = []

        async def send_message(self, tg, text, **kw):
            if tg == 13:
                from aiogram.exceptions import TelegramForbiddenError
                from aiogram.methods import SendMessage
                raise TelegramForbiddenError(method=SendMessage(chat_id=tg, text=text), message="blocked")
            self.sent.append((tg, text))

        async def copy_message(self, tg, chat, msg, **kw):
            self.sent.append((tg, f"copy:{chat}:{msg}"))

    async def run():
        old_ids, old_db, old_bot = list(obour_cfg.admin_ids), gcrt.db, gcrt.bot
        obour_cfg.admin_ids[:] = [99]
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        bot = FakeBot()
        gcrt.db, gcrt.bot = db, bot
        try:
            for tg in (10, 11, 12, 13, 99):
                await db.player(tg, f"user{tg}", f"u{tg}")
            await db.credit(10, 300)
            h = lambda name, method="GET", q=None, body=None, who=99: admin.handle(  # noqa: E731
                name, method, who, q or {}, body or {}, db)
            try:
                await h("admin", who=10)
                raise AssertionError("non-admin got in")
            except service.GCError as e:
                assert e.code == "not_found"
            d = await h("admin")
            assert d["stats"]["all"]["players"] == 5 and len(d["daily"]) == 14
            assert [u["id"] for u in (await h("admin/users", q={"q": "u11"}))["users"]] == [11]
            assert (await h("admin/users", q={"q": "10"}))["users"][0]["id"] == 10
            # امتیاز: افزودن، کسر، تکرار همان درخواست بی اثر
            r = await h("admin/points", "POST", body={"id": 10, "amount": 500, "note": "جبران", "idem": "abcdef123456"})
            assert r["points"] == 800
            try:
                await h("admin/points", "POST", body={"id": 10, "amount": 500, "idem": "abcdef123456"})
                raise AssertionError("idem ignored")
            except service.GCError as e:
                assert e.code == "done_before"
            assert (await h("admin/points", "POST", body={"id": 10, "amount": -100, "idem": "zz12345678"}))["points"] == 700
            u = await h("admin/user", q={"id": "10"})
            assert u["user"]["points"] == 700 and u["ledger"][0]["kind"] == "admin"
            # مسدود: از صف بیرون می رود؛ ادمین مسدود نمی شود
            await service.queue_join(db, 11, {"mode": "free", "players": 2, "pawns": 2})
            await h("admin/ban", "POST", body={"id": 11, "banned": True, "note": "تقلب"})
            assert (await db.get_player(11))["banned"] == 1 and not await db.queue_row(11)
            assert [x["id"] for x in (await h("admin/users", q={"f": "banned"}))["users"]] == [11]
            try:
                await h("admin/ban", "POST", body={"id": 99, "banned": True})
                raise AssertionError("banned an admin")
            except service.GCError:
                pass
            # تنظیمات زنده: بر .env مقدم و قابل برگشت
            await h("admin/setting", "POST", body={"key": "maintenance", "value": True})
            await h("admin/setting", "POST", body={"key": "turn_seconds", "value": 200})
            assert gc.maintenance is True and gc.turn_seconds == 60
            await h("admin/setting", "POST", body={"key": "maintenance", "value": None})
            await h("admin/setting", "POST", body={"key": "turn_seconds", "value": None})
            assert gc.maintenance is False and gc.turn_seconds == type(gc).turn_seconds
            # پیام: HTML ساده می ماند، بقیه امن می شود
            assert admin._clean_text("<b>سلام</b> <script>x</script> 2<3") == "<b>سلام</b> &lt;script&gt;x&lt;/script&gt; 2&lt;3"
            # پیام همگانی: نسخه آزمایشی به خود ادمین، بعد همه (به جز مسدود)؛ ۱۳ ربات را بسته
            r = await h("admin/broadcast", "POST", body={"text": "<b>جام</b> هفته", "target": "all", "button": "|بازی"})
            assert r["total"] == 4 and bot.sent[0][0] == 99
            await admin._running
            b = await db.bc_get(r["id"])
            assert b["status"] == "done" and b["sent"] == 3 and b["blocked"] == 1, dict(b)
            assert sorted(t for t, _ in bot.sent[1:]) == [10, 12, 99]
            assert (await h("admin/bc_count", q={"target": "game:ludo"}))["n"] == 0
            log_actions = [x["action"] for x in (await h("admin/log"))["rows"]]
            assert "broadcast" in log_actions and "ban" in log_actions and "points" in log_actions
        finally:
            obour_cfg.admin_ids[:] = old_ids
            gcrt.db, gcrt.bot = old_db, old_bot
            await admin.sync_settings(db, force=True)
            await db.close()
    asyncio.run(run())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
