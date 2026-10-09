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

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
