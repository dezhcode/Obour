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
import time

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

    async def notifier(tg, text, page, key=""):
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
        # حداکثر دو یادآوری نوبت در هر بازی (اگر بازیکن ۱ با تاس ۶ پشت سر هم زودتر جریمه شود،
        # ممکن است نوبت بازیکن ۲ اصلا نرسیده باشد؛ پس صفر هم درست است)
        turn_pings = [x for x in sent if x[0] == 2 and "نوبت" in x[1]]
        assert len(turn_pings) <= 2, sent
        # نتیجه برای غایب: هر دو بازیکن غایب اند و هر کدام زودتر سه نوبت جا بیندازد می بازد،
        # پس بازیکن ۲ یا خبر باخت (index) می گیرد یا خبر برد (wallet)
        assert any(x[0] == 2 and x[2] in ("index.html", "shop.html") and "منچ" in x[1] for x in sent), sent
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
        assert p["tg_name"] == "علی bرضایی/b" and pic_url(p) == user["photo_url"]   # نویسه های HTML حذف می شوند
        assert p["name"] != p["tg_name"] and p["name"].isascii()                   # همه جا یوزرنیم بازی دیده می شود
        assert len(p["pic"]) >= 8 and await db.player_by_pic(p["pic"])
        p2 = await db.player(78, "سارا", None, "")                                # عکس پنهان: آدرس /gc/pic
        assert pic_url(p2) == "pic/" + p2["pic"]
        assert pic_url(await db.player(78, "سارا", None, None)) == "pic/" + p2["pic"]   # پیام ربات عکس را پاک نمی کند
        try:
            r = await service.invite_create(db, 77, {"mode": "free", "entry": 0, "players": 2, "pawns": 2})
            lobby = (await service.match_view(db, 77, r["match"]))["lobby"]["seats"]
            assert [x["pic"] for x in lobby] == [user["photo_url"]] and lobby[0]["name"] == p["name"]
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
            assert [m["me"] for m in v["chat"]] == [False, True] and v["chat"][0]["name"] == (await db.get_player(1))["name"]
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


def test_bots_catch_up_on_late_poll():
    """سه ربات پشت سر هم: اگر poll کمی دیر برسد همه در همان poll بازی می کنند (از موعد خودشان)،
    نه هر کدام یک poll؛ و اگر خیلی دیر باشد از همان لحظه حساب می شود تا مهلت آدم نسوزد."""
    seats = [{"color": s, "uid": 1 if s == "0" else None, "name": s, "bot": s != "0"} for s in hokm.SEATS]
    st = hokm.new_state(seats, 0.0, 20, False, 7, hakem=0)
    assert hokm.choose_trump(st, 0, 0, 10.0) is None
    hokm.tick(st, 20.0)                                   # پخش تمام شد؛ نوبت حاکم (آدم)
    assert st["phase"] == "play" and st["turn"] == 0
    assert hokm.play(st, 0, hokm.legal(st, 0)[0], 20.0) is None
    hokm.tick(st, 20.0 + 3 * hokm.BOT_THINK + 0.2)
    assert len(st["trick"]) == 4 or st["phase"] == "collect"
    st2 = hokm.new_state(seats, 0.0, 20, False, 7, hakem=0)
    hokm.choose_trump(st2, 0, 0, 10.0); hokm.tick(st2, 20.0)
    hokm.play(st2, 0, hokm.legal(st2, 0)[0], 20.0)
    hokm.tick(st2, 500.0)                                 # خیلی دیر: از لحظهٔ poll
    assert st2["next_at"] >= 500.0


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


def _fb_ready(seed_first=0, passes=0, target=3):
    from game_club import football as F
    st = F.new_state([{"color": "0", "name": "a", "uid": 1}, {"color": "1", "name": "b", "uid": 2}], 0.0, 20, False, target,
                     first=seed_first, passes=passes)
    F.setup(st, "0", "eagles", "132", "132", 1.0)
    F.setup(st, "1", "lions", "132", "132", 1.0)
    return F, st


def _fb_lineup(F, st):
    """مهره ها دور از هم و ساکن: صندلی ۰ پایین، صندلی ۱ بالا؛ مهرهٔ ۱ شوت زننده، مهرهٔ ۲ گیرنده، توپ بین شان."""
    pos = [[521.0, 1824.0], [500.0, 1500.0], [500.0, 700.0]] + [[150.0 + 180 * q, 1750.0] for q in range(3)]
    pos += [[521.0, 96.0]] + [[x, 330.0] for x in (100.0, 250.0, 700.0, 850.0, 960.0)]
    pos.append([500.0, 1250.0])
    st["pos"] = pos
    st["next_at"] = 0
    st["new_ko"] = False
    return pos


def test_football_physics_and_rules():
    from game_club import football as F
    seats = [{"color": "0", "name": "a", "uid": 1}, {"color": "1", "name": "b", "bot": True}]
    st = F.new_state(seats, 0.0, 20, False, 3, first=0)
    assert st["phase"] == "setup" and len(st["pos"]) == 13 and st["target"] == 3 and st["passes"] == 0
    # چیدمان شروع: دروازه بان ها جلوی دروازه و توپ وسط زمین
    assert st["pos"][0][1] > 1700 and st["pos"][6][1] < 220 and abs(st["pos"][12][0] - 521) <= 4
    assert F.setup(st, "0", "nope", "132", "132", 1.0) == "bad_setup"
    assert F.setup(st, "0", "eagles", "141", "123", 1.0) is None
    assert st["phase"] == "play" and st["turn"] == 0 and st["new_ko"]
    assert F.shot(st, 0, 4, 0, -1, 0.5, 1.0) == "not_ready"            # هنوز نمایش «مقابل» است
    assert F.shot(st, 1, 4, 0, -1, 0.5, 99.0) == "not_your_turn"
    assert F.shot(st, 0, 9, 0, -1, 0.5, 99.0) == "bad_shot"
    assert F.shot(st, 0, 4, 0, 0, 0.5, 99.0) == "bad_shot"
    # گل از ضربهٔ شروع خطاست: امتیاز نمی گیرد، حریف شروع می کند
    pos = _fb_lineup(F, st)
    st["new_ko"] = True
    pos[12] = [400.0, 400.0]
    pos[4] = [400.0, 520.0]
    assert F.shot(st, 0, 4, 0, -1, 0.55, 99.0) is None
    assert st["score"] == [0, 0] and st["turn"] == 1 and st["new_ko"] and st["kick"] == 1
    ev = [e for e in st["events"] if e["t"] in ("shot", "goal", "reset")][-3:]
    assert [e["t"] for e in ev] == ["shot", "goal", "reset"] and ev[1]["foul"] and ev[0]["frames"]
    assert len(ev[0]["frames"][0]) == 2 * len(ev[0]["ids"])
    # گل عادی بعد از اولین شوت: امتیاز می گیرد و تیم گل خورده شروع می کند
    st["turn"], st["next_at"], st["new_ko"] = 0, 0, False
    pos = _fb_lineup(F, st)
    pos[12] = [400.0, 400.0]
    pos[4] = [400.0, 520.0]
    assert F.shot(st, 0, 4, 0, -1, 0.55, 199.0) is None
    assert st["score"] == [1, 0] and st["turn"] == 1 and st["kick"] == 1 and st["new_ko"] and st["stats"]["0"]["goals"] == 1
    # بدون پاس: توپ از دست می رود و نوبت حریف می شود
    st["turn"], st["next_at"], st["new_ko"], st["score"] = 0, 0, False, [0, 0]
    pos = _fb_lineup(F, st)
    pos[12] = [900.0, 1000.0]
    assert F.shot(st, 0, 3, 0, -1, 0.3, 399.0) is None and st["turn"] == 1 and st["chain"] == 0
    assert [e["t"] for e in st["events"]][-1] == "lose"
    # فقط فریم های آخرین شوت نگه داشته می شود
    assert sum(1 for e in st["events"] if e.get("frames")) <= 1
    # مهلت نوبت مثل پلاتو: ۳۰، بعد ۲۰، ۱۷، ۱۴، ۱۱، ۸ ثانیه؛ غایب ها حداکثر ۱۰
    assert [F.turn_time(20, c) for c in (0, 1, 2, 3, 4, 5, 9)] == [30.0, 20.0, 17.0, 14.0, 11.0, 8.0, 8.0]
    assert F.turn_time(20, 0, 2) == 10.0
    # غیبت در بازی امتیازی: سه نوبت = باخت
    st = F.new_state([{"color": "0", "name": "a", "uid": 1}, {"color": "1", "name": "b", "uid": 2}], 0.0, 20, True, 3, first=0)
    now = F.SETUP_S + 1
    F.tick(st, now)
    assert st["phase"] == "play" and st["players"]["0"]["team"] and st["players"]["1"]["team"]
    for _ in range(12):
        now += 40
        F.tick(st, now)
        if st["over"]:
            break
    assert st["over"] and st["winner"] in (0, 1)


def test_football_pass_rules():
    import math
    F, st = _fb_ready()
    pos = _fb_lineup(F, st)
    # شوت مهرهٔ ۱ به توپ، توپ به مهرهٔ ۲ می رسد: پاس کامل، دوباره نوبت خودم، گیرنده پشت توپ رو به دروازه
    assert F.shot(st, 0, 1, 0, -1, 0.42, 100.0) is None
    assert st["turn"] == 0 and st["chain"] == 1, (st["turn"], st["chain"])
    e = [x for x in st["events"] if x["t"] == "pass"][-1]
    assert e["d"] == 2 and e["n"] == 1 and e["left"] is None
    bx, by = st["pos"][F.BALL]
    rx, ry = st["pos"][2]
    assert 95 < math.hypot(bx - rx, by - ry) < 130 and ry > by - 5          # گیرنده زیر توپ (دروازهٔ حریف بالاست)
    assert st["stats"]["0"]["passes"] == 1 and F.view(st, "0", 0, 0.0)["chain"] == 1
    assert F.turn_time(20, 1) == 20.0 and st["deadline"] - st["next_at"] == 20.0
    # سقف پاس: با سه پاس، پاس چهارم حساب نمی شود و نوبت حریف می شود
    F, st = _fb_ready(passes=3)
    for n in range(1, 4):
        _fb_lineup(F, st)
        st["chain"] = n - 1
        assert F.shot(st, 0, 1, 0, -1, 0.42, 100.0 * n) is None and st["chain"] == n and st["turn"] == 0, n
    _fb_lineup(F, st)
    assert F.shot(st, 0, 1, 0, -1, 0.42, 500.0) is None
    assert st["turn"] == 1 and st["chain"] == 0 and st["stats"]["0"]["passes"] == 3
    # توپ به یار نرسد: پاس نیست و نوبت حریف است
    F, st = _fb_ready()
    pos = _fb_lineup(F, st)
    assert F.shot(st, 0, 1, 1, -0.2, 0.42, 100.0) is None
    assert st["chain"] == 0 and st["turn"] == 1
    # مهرهٔ خودم که مهرهٔ دیگرم را هل بدهد پاس نیست (باید توپ به یار برسد)
    F, st = _fb_ready()
    pos = _fb_lineup(F, st)
    pos[12] = [900.0, 1000.0]
    pos[2] = [500.0, 1330.0]
    assert F.shot(st, 0, 1, 0, -1, 0.3, 100.0) is None and st["chain"] == 0 and st["turn"] == 1


def test_football_phys_matches_plato_numbers():
    """ثابت های بستهٔ پلاتو و ویژگی های فیزیکی: زمان توقف ثابت، برگشت از دیوار، فاصلهٔ آهن ربا."""
    import math
    from game_club import football_phys as P
    assert (P.W, P.H, P.GOAL_W, P.BALL_R, P.REG_R, P.KEEP_R) == (1042.0, 1920.0, 354.0, 32.0, 55.0, 64.0)
    park = [[120.0, 100.0 + 150 * q] for q in range(11)]
    # بدون برخورد: مسافت متناسب با قدرت و توقف در زمان ثابت (میرایی رو به افزایش)
    d = []
    for power in (50, 150, 250):
        pos = [[521.0, 1800.0]] + park + [[900.0, 100.0]]
        r = P.run_shot(pos, 0, 0.0, -power * P.IMPULSE_MULT, 0, False)
        d.append((1800.0 - r["pos"][0][1], r["steps"]))
    assert abs(d[2][0] / d[0][0] - 5.0) < 0.05 and abs(d[0][1] - d[2][1]) <= 6
    # ضریب برگشت: توپ ۰٫۹۵ از دیوار برمی گردد
    pos = [[120.0, 150.0 * q + 100] for q in range(12)] + [[500.0, 960.0]]
    s = P.Sim(pos, 0)
    s.wake(12)
    s.vx[12] = 1000.0
    prev, ratio = None, 0
    for _ in range(120):
        s.step()
        if prev is not None and prev * s.vx[12] < 0:
            ratio = -s.vx[12] / prev
            break
        prev = s.vx[12]
    assert 0.92 < ratio < 0.97, ratio
    # آهن ربا: توپ به گیرندهٔ پاس با فاصلهٔ ۵۵ + ۱٫۵×۳۲ = ۱۰۳ می چسبد
    pos = [[100.0, 1800.0], [300.0, 1300.0], [300.0, 700.0], [800.0, 1800.0], [800.0, 1500.0], [800.0, 1200.0]]
    pos += [[1000.0 - 10 * q, 100.0 + 140 * q] for q in range(6)] + [[300.0, 1100.0]]
    r = P.run_shot(pos, 1, 0.0, -110 * P.IMPULSE_MULT, 0, True)
    assert r["shooter"] == 1 and r["receiver"] == 2
    bx, by = r["pos"][12]
    assert abs(math.hypot(bx - r["pos"][2][0], by - r["pos"][2][1]) - 103.0) < 1.5
    # کنترل: گیرنده بدون مانع پشت توپ می نشیند، فاصله ۱۲۷ و رو به دروازهٔ بالا
    park2 = [[100.0, 1800.0], [100.0, 1500.0], [800.0, 1000.0], [800.0, 1800.0], [800.0, 1500.0], [100.0, 1200.0]]
    cpos = [p[:] for p in park2]
    cpos[2] = [500.0, 800.0]
    cpos += [[1000.0 - 10 * q, 100.0 + 140 * q] for q in range(6)] + [[500.0, 903.0]]
    c = P.run_control(cpos, 2, 0)
    cx, cy = c["pos"][2]
    assert c["moved"] and abs(math.hypot(cx - 500.0, cy - 903.0) - 127.0) < 2.0 and cy > 903.0
    # حسگر دروازه: توپ کامل داخل خط
    pos = [[521.0, 700.0]] + [[100.0 + 80 * q, 1700.0] for q in range(5)] + [[950.0 - 80 * (q % 3), 300.0 + 120 * q] for q in range(6)] + [[521.0, 520.0]]
    r = P.run_shot(pos, 0, 0.0, -90 * P.IMPULSE_MULT, 0, True)
    assert r["goal"] == 0 and r["pos"][12][1] < 70
    # قطعی بودن: دو بار اجرا یک نتیجه می دهد
    r2 = P.run_shot(pos, 0, 0.0, -90 * P.IMPULSE_MULT, 0, True)
    assert r2["frames"] == r["frames"]


def test_football_bots_play_a_game():
    import time
    from game_club import football as F
    st = F.new_state([{"color": "0", "name": "a", "bot": True}, {"color": "1", "name": "b", "bot": True}], 0.0, 20, False, 2)
    now, t0 = 0.0, time.time()
    while not st["over"] and now < 6000 and time.time() - t0 < 150:
        now += 0.5
        F.tick(st, now)
        for x, y in st["pos"]:
            assert -80 <= x <= F.W + 80 and -80 <= y <= F.H + 80
    assert st["over"] and max(st["score"]) == 2 and F.winners(st) == {F.SEATS[st["winner"]]}
    assert sum(1 for e in st["events"] if e.get("frames")) <= 1


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
            cfg = {"game": "football", "mode": "stake", "entry": 100, "target": 2, "passes": 3}
            inv = await service.invite_create(db, 1, cfg)
            await service.invite_join(db, 2, inv["code"])
            m = await db.get_match(inv["match"])
            assert m["status"] == "playing"
            for tg in (1, 2):
                await service.act(db, tg, inv["match"], "setup", data={"team": "eagles", "fa": "132", "fd": "132"})
            m = await db.get_match(inv["match"])
            kits = {s: p["kit"] for s, p in m["state"]["players"].items()}
            assert sorted(kits.values()) == ["away", "home"]                  # تیم یکسان: یکی لباس مهمان
            from game_club import football as F
            assert m["state"]["passes"] == 3 and m["state"]["target"] == 2
            rows = {r["color"]: r["tg_id"] for r in await db.match_players(inv["match"])}
            for _ in range(300):
                m = await db.get_match(inv["match"])
                if m["status"] != "playing":
                    break
                st = m["state"]
                clock[0] = max(clock[0], st["next_at"]) + 0.1
                seat = st["turn"]
                k, dx, dy, p = F.bot_shot(st, seat)
                await service.act(db, rows[str(seat)], inv["match"], "shot", data={"i": k, "dx": dx, "dy": dy, "p": p})
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
            if tg == 13:
                from aiogram.exceptions import TelegramForbiddenError
                from aiogram.methods import CopyMessage
                raise TelegramForbiddenError(method=CopyMessage(chat_id=tg, from_chat_id=chat, message_id=msg), message="blocked")
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
            # پیام همگانی (پیش نویس از ربات): همه به جز مسدود؛ ۱۳ ربات را بسته. پنل فقط آمار را می بیند
            bid = await db.bc_draft(99, 99, 7, "|بازی|brand", "all")
            assert await db.bc_launch(bid, admin._target("all", 99)) == 4
            admin.kick()
            await admin._running
            b = await db.bc_get(bid)
            assert b["status"] == "done" and b["sent"] == 3 and b["blocked"] == 1, dict(b)
            assert sorted(t for t, _ in bot.sent) == [10, 12, 99] and all(x == "copy:99:7" for _, x in bot.sent)
            st = (await h("admin/broadcasts"))["summary"]
            assert st["sent"] == 3 and st["blocked"] == 1 and st["count"] == 1
            log_actions = [x["action"] for x in (await h("admin/log"))["rows"]]
            assert "ban" in log_actions and "points" in log_actions
        finally:
            obour_cfg.admin_ids[:] = old_ids
            gcrt.db, gcrt.bot = old_db, old_bot
            await admin.sync_settings(db, force=True)
            await db.close()
    asyncio.run(run())


def test_style_shop():
    """میز و ورق حکم: A رایگان، بقیه با امتیاز؛ خرید یک بار، همان idem بی اثر، استفاده فقط از خریده شده."""
    tmp = tempfile.mkdtemp()
    from game_club import service
    from game_club.db import GCDatabase

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        await db.player(5, "a")
        await db.credit(5, 600)
        v = await service.style_view(db, 5)
        assert v["table"] == "a" and v["cards"] == "a"
        assert {i["id"] for i in v["items"] if i["owned"]} == {"table:a", "cards:a", "cards:m"}
        v = await service.style_use(db, 5, "cards:m")                        # مدرن رایگان است
        assert v["cards"] == "m"
        try:
            await service.style_use(db, 5, "table:b")
            raise AssertionError("used unowned")
        except service.GCError as e:
            assert e.code == "not_owned"
        v = await service.style_buy(db, 5, "table:b", "idem-style-1")
        assert v["table"] == "b" and v["points"] == 100
        v = await service.style_buy(db, 5, "table:b", "idem-style-1")        # تکرار همان درخواست
        assert v["points"] == 100
        try:
            await service.style_buy(db, 5, "cards:c", "idem-style-2")         # ۳۰۰ لازم است، ۱۰۰ دارد
            raise AssertionError("bought without points")
        except service.GCError as e:
            assert e.code == "insufficient"
        await service.style_use(db, 5, "table:a")
        v = await service.style_use(db, 5, "table:b")
        assert v["table"] == "b" and (await db.get_player(5))["points"] == 100
        assert (await db.ledger_of(5))[0]["kind"] in ("style", "charge")
        assert any(r["kind"] == "style" and r["amount"] == -500 for r in await db.ledger_of(5))
        await db.close()
    asyncio.run(run())



def test_profile_stats():
    """پروفایل: کارنامهٔ هر بازی و آخرین بازی ها از جدول نتیجه ها (فقط بازی های تمام شده)."""
    import json as _json
    tmp = tempfile.mkdtemp()
    from game_club.db import GCDatabase

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        try:
            await db.player(5, "a")
            now = 1_700_000_000
            for i, (game, won, prize, mode) in enumerate([("hokm", 1, 200, "stake"), ("hokm", 0, 0, "free"), ("football", 1, 0, "free")]):
                await db.execute("INSERT INTO matches(id, game, status, cfg, state, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                                 (f"m{i}", game, "over", _json.dumps({"mode": mode, "entry": 100 if mode == "stake" else 0}), "{}", now + i, now + i))
                await db.add_result(f"m{i}", 5, bool(won), prize)
            g = {r["game"]: r for r in await db.game_stats(5)}
            assert g["hokm"]["games"] == 2 and g["hokm"]["wins"] == 1 and g["hokm"]["prize"] == 200
            assert g["football"]["games"] == 1 and g["football"]["wins"] == 1
            rec = await db.recent_games(5)
            assert [r["game"] for r in rec] == ["football", "hokm", "hokm"]           # تازه ترین اول
            assert _json.loads(rec[2]["cfg"])["entry"] == 100
            p = await db.get_player(5)
            assert p["games"] == 3 and p["wins"] == 2
        finally:
            await db.close()

    asyncio.run(run())

def test_usernames():
    """یوزرنیم: اسم تصادفی یکتا برای کاربر تازه، تبدیل کاربرهای قدیمی، قاعده ها، یکتایی و فاصلهٔ ۳۰ روزه."""
    import aiosqlite
    tmp = tempfile.mkdtemp()
    from game_club import names
    from game_club.db import GCDatabase

    path = os.path.join(tmp, "gc.db")

    async def old_db():
        # دیتابیس نسخهٔ قبل: اسم تلگرام در name، دو نفر هم اسم
        async with aiosqlite.connect(path) as c:
            await c.execute("CREATE TABLE players (tg_id INTEGER PRIMARY KEY, name TEXT NOT NULL DEFAULT '', username TEXT,"
                            " av INTEGER NOT NULL DEFAULT 0, points INTEGER NOT NULL DEFAULT 0, games INTEGER NOT NULL DEFAULT 0,"
                            " wins INTEGER NOT NULL DEFAULT 0, show_spend INTEGER NOT NULL DEFAULT 0, tutorial INTEGER NOT NULL DEFAULT 0,"
                            " sound INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, seen_at INTEGER NOT NULL)")
            for tg in (1, 2):
                await c.execute("INSERT INTO players(tg_id, name, created_at, seen_at) VALUES(?, 'علی', 1, 1)", (tg,))
            await c.commit()

    async def run():
        await old_db()
        db = GCDatabase(path)
        await db.connect()
        try:
            a, b = await db.get_player(1), await db.get_player(2)
            assert a["tg_name"] == "علی" and b["tg_name"] == "علی"
            assert a["name"] != b["name"] and names.problem(a["name"]) is None and names.problem(b["name"]) is None
            # کاربر تازه: اسم تلگرام فقط در tg_name؛ name یوزرنیم تصادفی معتبر
            c = await db.player(3, "سارا", "sara_tg")
            assert c["tg_name"] == "سارا" and names.problem(c["name"]) is None and c["name"] != "سارا"
            c2 = await db.player(3, "سارا جان", "sara_tg")
            assert c2["name"] == c["name"] and c2["tg_name"] == "سارا جان"      # ورود دوباره یوزرنیم را عوض نمی کند
            # قاعده ها
            for bad, code in (("ab", "name_short"), ("9lives", "name_start"), ("ali-x", "name_chars"), ("#abc", "name_start"), ("ab#c", "name_chars"),
                              ("admin", "name_reserved"), ("a" * 17, "name_long")):
                assert await db.set_name(3, bad) == code, bad
            assert await db.set_name(3, "@Sara_99") == ""                       # @ و حرف بزرگ نرمال می شود
            assert (await db.get_player(3))["name"] == "sara_99"
            # یکتا
            assert await db.set_name(1, "SARA_99") == "name_taken"
            # دومین تغییر تا ۳۰ روز ممکن نیست؛ بعدش آزاد
            assert (await db.set_name(3, "sara_new")).startswith("name_wait:")
            later = int(time.time()) + names.RENAME_DAYS * 86400 + 5
            assert await db.set_name(3, "sara_new", now=later) == ""
            assert await db.name_taken("sara_new") and not await db.name_taken("sara_99")
        finally:
            await db.close()

    asyncio.run(run())


def test_game_board():
    """رده بندی هر بازی جدا: فقط برد همان بازی، ترتیب برد و جایزه، و جایگاه من."""
    import json as _json
    tmp = tempfile.mkdtemp()
    from game_club import service
    from game_club.db import GCDatabase

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        try:
            for tg in (1, 2, 3):
                await db.player(tg, f"p{tg}")
            now = int(time.time())
            rows = [("hokm", 1, 1, 0), ("hokm", 1, 1, 200), ("hokm", 2, 1, 0), ("hokm", 3, 0, 0), ("ludo", 3, 1, 0), ("ludo", 3, 1, 0)]
            for i, (game, tg, won, prize) in enumerate(rows):
                await db.execute("INSERT INTO matches(id, game, status, cfg, state, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                                 (f"m{i}", game, "over", _json.dumps({"mode": "free"}), "{}", now, now))
                await db.add_result(f"m{i}", tg, bool(won), prize)
            b = await service.game_leaderboard(db, 2, "hokm", "week")
            assert [r["wins"] for r in b["rows"]] == [2, 1] and b["rows"][1]["me"], b
            assert b["mine"]["rank"] == 2 and b["mine"]["wins"] == 1
            assert (await service.game_leaderboard(db, 3, "hokm", "all"))["mine"]["rank"] == 0   # بدون برد در حکم
            lb = await service.game_leaderboard(db, 3, "ludo", "month")
            assert len(lb["rows"]) == 1 and lb["mine"]["rank"] == 1 and lb["mine"]["games"] == 2
            try:
                await service.game_leaderboard(db, 1, "chess", "week")
                raise AssertionError("bad game")
            except service.GCError as e:
                assert e.code == "bad_game"
        finally:
            await db.close()

    asyncio.run(run())


def test_profile_bio_cover():
    """درباره من: نویسه های خطرناک حذف و ۸۰ نویسه نگه داشته می شود؛ کاور پیش فرض Game Club است."""
    tmp = tempfile.mkdtemp()
    from game_club import service
    from game_club.db import GCDatabase

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        try:
            p = await db.player(9, "x")
            assert p["cover"] == "gc" and p["bio"] == "" and "gc" in service.COVERS
            await db.set_profile(9, bio="<b>سلام</b>\nخوبی؟ " + "ا" * 200)
            bio = (await db.get_player(9))["bio"]
            assert "<" not in bio and "\n" not in bio and len(bio) == 80 and bio.startswith("bسلام/b خوبی؟")
            await db.set_profile(9, cover="gc")
            assert (await db.get_player(9))["cover"] == "gc"
        finally:
            await db.close()

    asyncio.run(run())


def test_friends_and_dm():
    """دوستی با یوزرنیم: درخواست، قبول، پیام خصوصی و نخوانده ها، دعوت به بازی، بلاک و حذف."""
    tmp = tempfile.mkdtemp()
    from game_club import service, social
    from game_club.db import GCDatabase

    sent = []

    async def notifier(tg, text, page, key=""):
        sent.append((tg, page))

    async def run():
        service.notifier = notifier
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        try:
            a, b, c = (await db.player(1, "a")), (await db.player(2, "b")), (await db.player(3, "c"))
            await db.set_name(2, "bob_two")
            f = await social.find(db, 1, "@BOB_two")
            assert f["relation"] == "none" and f["user"]["name"] == "bob_two" and "tg_id" not in f["user"]
            uid_b, uid_a = f["user"]["uid"], a["pic"]
            assert (await social.request(db, 1, uid_b))["relation"] == "outgoing"
            assert (await social.badge(db, 2))["requests"] == 1 and any(x == (2, "friends.html") for x in sent)
            v = await social.friends_view(db, 2)
            assert [x["uid"] for x in v["incoming"]] == [uid_a] and not v["friends"]
            # پیام قبل از دوستی ممنوع
            try:
                await social.send(db, 1, uid_b, "سلام")
                raise AssertionError("dm before friends")
            except service.GCError as e:
                assert e.code == "not_friends"
            assert (await social.accept(db, 2, uid_a))["relation"] == "friend"
            assert (await social.friends_view(db, 1))["friends"][0]["name"] == "bob_two"
            await social.send(db, 1, uid_b, "  سلام\u202e  رفیق  ")
            assert (await social.badge(db, 2))["unread"] == 1
            ch = await social.chat(db, 2, uid_a)
            assert [m["text"] for m in ch["messages"]] == ["سلام رفیق"] and not ch["messages"][0]["me"]
            assert (await social.badge(db, 2))["unread"] == 0                 # با دیدن چت خوانده شد
            try:
                await social.send(db, 1, uid_b, "دوباره")                     # خیلی سریع
                raise AssertionError("slow")
            except service.GCError as e:
                assert e.code == "chat_slow"
            # دعوت به بازی: میز آزاد ساخته می شود و کارتش در چت می آید
            await db.execute("UPDATE dms SET created_at = created_at - 5")
            inv = await social.invite(db, 2, uid_a, "hokm")
            m = await db.get_match(inv["match"])
            assert m["status"] == "lobby" and m["cfg"]["mode"] == "free"
            last = (await social.chat(db, 1, uid_b))["messages"][-1]
            assert last["kind"] == "invite" and last["meta"]["code"] == inv["code"]
            assert any(p.startswith("hokm-lobby.html?join=") for _, p in sent)
            # بلاک: دوستی پاک می شود، پیام و پیدا کردن ممنوع
            await social.block(db, 2, uid_a, True)
            assert (await social.friends_view(db, 1))["friends"] == []
            try:
                await social.find(db, 1, "bob_two")
                raise AssertionError("blocked find")
            except service.GCError as e:
                assert e.code == "not_found"
            try:
                await social.request(db, 1, uid_b)
                raise AssertionError("blocked request")
            except service.GCError as e:
                assert e.code == "cant_add"
            await social.block(db, 2, uid_a, False)
            await social.request(db, 1, uid_b)
            assert (await social.drop(db, 1, uid_b))["relation"] == "none"       # پس گرفتن درخواست
            assert (await social.friends_view(db, 2))["incoming"] == []
            try:
                await social.request(db, 1, a["pic"])                             # خودم
                raise AssertionError("self")
            except service.GCError as e:
                assert e.code == "not_found"
        finally:
            service.notifier = None
            await db.close()

    asyncio.run(run())


class _FakeGroupBot:
    """ربات ساختگی برای آزمون کارت های گروه (پیام غنی)."""
    def __init__(self):
        from types import SimpleNamespace as NS
        self.NS, self.sent, self.dms, self.edits, self.prepared, self.n = NS, [], [], [], [], 100

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.dms.append((chat_id, text))
        return self.NS(message_id=1)

    async def send_rich_message(self, chat_id, rich_message, **kw):
        self.n += 1
        self.sent.append((chat_id, rich_message, kw.get("ephemeral_message_parameters")))
        return self.NS(message_id=self.n)

    async def edit_message_text(self, text=None, chat_id=None, message_id=None, inline_message_id=None, rich_message=None, **kw):
        assert rich_message is not None and text is None and kw.get("reply_markup") is None
        self.edits.append((inline_message_id or (chat_id, message_id), rich_message))

    async def save_prepared_inline_message(self, user_id, result, **kw):
        self.prepared.append((user_id, result, kw))
        return self.NS(id="prep1", expiration_date=0)


class _CQ:
    def __init__(self, uid, data, imid=None, chat=None):
        from types import SimpleNamespace as NS
        self.from_user = NS(id=uid, first_name=f"u{uid}", last_name=None, username=None)
        self.data, self.inline_message_id, self.answers = data, imid, []
        self.message = NS(chat=chat, message_id=0) if chat else None

    async def answer(self, text=None, show_alert=False, **kw):
        self.answers.append(text)


def test_group_tables():
    """میز گروه: کارت تنظیم (فقط سازنده)، باز کردن، نشستن با منشن، شروع بدون دکمهٔ نشستن و با «دیدن بازی»،
    تماشای بازی برای عضو گروه، پیام پیوی و ephemeral، نتیجه، بستن کارت و میز کهنه. هیچ کیبورد شیشه ای نیست."""
    from types import SimpleNamespace as NS
    tmp = tempfile.mkdtemp()
    from game_club import groups, service
    from game_club.db import GCDatabase
    P, B = groups.plain, groups.buttons

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        bot = _FakeGroupBot()
        groups.install(bot, db)
        old_user, groups.gc.username = groups.gc.username, "gcbot"
        try:
            chat = NS(id=-1001, title="گروه دوستان")
            users = [NS(id=i, first_name=f"u{i}", last_name=None, username=None) for i in (11, 12, 13, 14)]
            assert await groups.create(db, bot, chat, users[0], "hokm") is None
            cid, card, _ = bot.sent[-1]
            assert cid == -1001 and "حالت بازی" in P(card) and "✓ 7 دست" in P(card)
            token = next(b.callback_data for b in B(card) if b.callback_data.startswith("gs:open:"))[8:]
            assert {b.callback_data for b in B(card)} >= {f"gs:target=3:{token}", f"gs:cancel:{token}"}
            assert '"id":11' in card.model_dump_json()           # منشن سازنده
            # میز دوم حکم هم زمان تنظیم نمی شود؛ غیر سازنده نمی تواند تنظیم کند
            assert "داره چیده می‌شه" in await groups.create(db, bot, chat, users[1], "hokm")
            cq = _CQ(12, f"gs:target=3:{token}", chat=chat)
            await groups.on_setup(cq, gdb=db)
            assert "فقط سازنده" in cq.answers[-1] and (await db.draft(token))["cfg"] == {"target": 7}
            await groups.on_setup(_CQ(11, f"gs:target=3:{token}", chat=chat), gdb=db)
            assert (await db.draft(token))["cfg"] == {"target": 3} and "✓ 3 دست" in P(bot.edits[-1][1])
            # باز کردن: همان پیام کارت میز می شود
            await groups.on_setup(_CQ(11, f"gs:open:{token}", chat=chat), gdb=db)
            row = await db.open_group_table(-1001, "hokm")
            m = await db.get_match(row["match_id"])
            assert m["cfg"]["target"] == 3 and row["message_id"] == 101 and (await db.draft(token))["status"] == "open"
            where, rm = bot.edits[-1]
            assert where == (-1001, 101) and "3 صندلی مونده" in P(rm) and "تا 3 دست" in P(rm)
            assert [b.style for b in B(rm)[:2]] == ["success", "danger"] and B(rm)[0].callback_data == f"gt:join:{m['id']}"
            assert "بازه" in await groups.create(db, bot, chat, users[1], "hokm")
            # نشستن با دکمهٔ داخل پیام
            for u in (12, 13):
                await groups.on_button(_CQ(u, f"gt:join:{m['id']}", chat=chat), gdb=db, bot=bot)
            last = bot.edits[-1][1]
            assert '"id":13' in last.model_dump_json() and "1 صندلی مونده" in P(last) and "(3 از 4)" in P(last)
            cq = _CQ(13, f"gt:join:{m['id']}", chat=chat)
            await groups.on_button(cq, gdb=db, bot=bot)
            assert "نشستی" in cq.answers[-1]
            # نفر چهارم: میز پر و بازی شروع؛ دکمه های میز می روند و فقط «دیدن بازی» می ماند
            await groups.on_button(_CQ(14, f"gt:join:{m['id']}", chat=chat), gdb=db, bot=bot)
            m = await db.get_match(m["id"])
            assert m["status"] == "playing"
            rm = bot.edits[-1][1]
            assert "شروع شد" in P(rm) and "حکم" in P(rm) and '"id":14' in rm.model_dump_json()
            assert [(b.text, b.url) for b in B(rm)] == [("دیدن بازی", f"https://t.me/gcbot?startapp=w_hokm_{m['id']}")]
            assert (await db.group_table(m["id"]))["status"] == "playing"
            assert {d[0] for d in bot.dms} == {11, 12, 13, 14}
            eph = [s for s in bot.sent if s[2] is not None]
            assert len(eph) == 4 and {e[2].receiver_user_id for e in eph} == {11, 12, 13, 14}
            # تکرار به روزرسانی دوباره خبر شروع نمی فرستد
            n = len(bot.sent)
            await groups.refresh(db, m["id"])
            assert len(bot.sent) == n
            # تماشا: عضو گروه که سر میز نیست، بازی را می بیند ولی برگ کسی را نه
            await db.player(99, "watcher")
            v = await service.match_view(db, 99, m["id"])
            assert v["watch"] and v["me"] == v["game"]["order"][0] and v["game"]["hand"] == [] and "chat" not in v
            assert all(not p["me"] for p in v["game"]["players"].values())
            v2 = await service.match_view(db, 11, m["id"])     # بازیکن با همان لینک بازی خودش را می بیند
            assert not v2.get("watch") and v2["game"]["hand"]
            # میز خصوصی (نه گروهی) را غریبه نمی بیند
            await db.player(98, "x")
            priv = await service.invite_create(db, 98, {"game": "hokm", "mode": "free", "entry": 0, "target": 3})
            try:
                await service.match_view(db, 99, priv["match"])
                raise AssertionError("میز خصوصی دیده شد")
            except service.GCError as e:
                assert e.code == "not_found"
            # پایان: کارت نتیجه با دکمهٔ میز تازه
            for u in users:
                await service.leave_any(db, u.id, m["id"])
            m = await db.get_match(m["id"])
            if m["status"] == "over":
                # پایان: فقط اطلاعات میز، بدون دکمه
                assert "تموم شد" in P(bot.edits[-1][1]) and "مدت بازی" in P(bot.edits[-1][1]) and not B(bot.edits[-1][1])
            # کارت تنظیمی که کسی بازش نکرد بعد از ۱۵ دقیقه بسته می شود
            assert await groups.create(db, bot, chat, NS(id=21, first_name="x", last_name=None, username=None), "ludo") is None
            tok = next(b.callback_data for b in B(bot.sent[-1][1]) if b.callback_data.startswith("gs:open:"))[8:]
            await db.execute("UPDATE group_drafts SET created_at = created_at - 3600 WHERE token = ?", (tok,))
            await groups.expire(db)
            assert (await db.draft(tok))["status"] == "closed" and "بسته شد" in P(bot.edits[-1][1])
            cq = _CQ(21, f"gs:open:{tok}", chat=chat)
            await groups.on_setup(cq, gdb=db)
            assert "از کار افتاده" in cq.answers[-1]
            # میز فوتبالی که باز شد ولی کسی نیامد هم بسته می شود
            assert await groups.create(db, bot, chat, NS(id=22, first_name="y", last_name=None, username=None), "football") is None
            tok = next(b.callback_data for b in B(bot.sent[-1][1]) if b.callback_data.startswith("gs:open:"))[8:]
            await groups.on_setup(_CQ(22, f"gs:open:{tok}", chat=chat), gdb=db)
            row = await db.open_group_table(-1001, "football")
            await db.execute("UPDATE group_tables SET created_at = created_at - 3600 WHERE match_id = ?", (row["match_id"],))
            await groups.expire(db)
            assert (await db.get_match(row["match_id"]))["status"] == "cancelled" and "بسته شد" in P(bot.edits[-1][1])
            # لغو کارت تنظیم با سازنده
            assert await groups.create(db, bot, chat, NS(id=23, first_name="z", last_name=None, username=None), "ludo") is None
            tok = next(b.callback_data for b in B(bot.sent[-1][1]) if b.callback_data.startswith("gs:open:"))[8:]
            await groups.on_setup(_CQ(23, f"gs:cancel:{tok}", chat=chat), gdb=db)
            assert (await db.draft(tok))["status"] == "closed" and "جمع کرد" in P(bot.edits[-1][1])
        finally:
            groups.gc.username = old_user
            service.table_hook = None
            await db.close()

    asyncio.run(run())


def test_inline_tables():
    """حالت اینلاین و «فرستادن به گروه»: کارت تنظیم با توکن، تنظیم و باز کردن فقط با سازنده، نشستن، ویرایش با inline_message_id."""
    from types import SimpleNamespace as NS
    tmp = tempfile.mkdtemp()
    from game_club import groups, service
    from game_club.db import GCDatabase
    P, B = groups.plain, groups.buttons

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        bot = _FakeGroupBot()
        groups.install(bot, db)
        try:
            # @ربات منچ → فقط کارت منچ؛ بدون متن هر سه بازی
            got = []
            iq = NS(from_user=NS(id=31, first_name="host", last_name=None, username=None), query="منچ")

            async def answer(results, **kw):
                got.append((results, kw))
            iq.answer = answer
            await groups.on_inline(iq, gdb=db)
            res, kw = got[-1]
            assert len(res) == 1 and kw["is_personal"] and res[0].reply_markup is None
            rm = res[0].input_message_content.rich_message
            token = res[0].id
            assert "حالت بازی" in P(rm) and f"gs:open:{token}" in [b.callback_data for b in B(rm)]
            iq.query = ""
            await groups.on_inline(iq, gdb=db)
            assert len(got[-1][0]) == 5          # حکم، منچ، فوتبال، بیلیارد، دیوار
            # فقط سازنده تنظیم می کند؛ شناسهٔ پیام اینلاین از همین لمس ثبت می شود
            cq = _CQ(32, f"gs:open:{token}", imid="IM1")
            await groups.on_setup(cq, gdb=db)
            assert "فقط سازنده" in cq.answers[-1] and (await db.draft(token))["status"] == "setup"
            await groups.on_setup(_CQ(31, f"gs:players=2:{token}", imid="IM1"), gdb=db)
            d = await db.draft(token)
            assert d["inline_message_id"] == "IM1" and d["cfg"]["players"] == 2
            assert bot.edits[-1][0] == "IM1" and "✓ 2 نفره" in P(bot.edits[-1][1])
            # مقدار غیرمجاز نادیده گرفته می شود
            await groups.on_setup(_CQ(31, f"gs:players=9:{token}", imid="IM1"), gdb=db)
            assert (await db.draft(token))["cfg"]["players"] == 2
            await groups.on_setup(_CQ(31, f"gs:open:{token}", imid="IM1"), gdb=db)
            mid = (await db.draft(token))["match_id"]
            assert mid and (await db.group_table(mid))["inline_message_id"] == "IM1"
            m = await db.get_match(mid)
            assert m["cfg"]["players"] == 2 and [s["tg"] for s in m["state"]["seats"]] == [31]
            assert bot.edits[-1][0] == "IM1" and B(bot.edits[-1][1])[0].callback_data == f"gt:join:{mid}"
            # لمس دوباره «باز کردن» میز دوم نمی سازد
            cq = _CQ(31, f"gs:open:{token}", imid="IM1")
            await groups.on_setup(cq, gdb=db)
            assert "از کار افتاده" in cq.answers[-1]
            # نفر دوم می نشیند: میز ۲ نفره پر و بازی شروع می شود؛ پیوی می رود، ephemeral نه (چت معلوم نیست)
            await groups.on_button(_CQ(32, f"gt:join:{mid}", imid="IM1"), gdb=db, bot=bot)
            assert (await db.get_match(mid))["status"] == "playing" and "شروع شد" in P(bot.edits[-1][1])
            assert {d[0] for d in bot.dms} == {31, 32} and not bot.sent
            # پایان: «میز تازه» در همان پیام اینلاین کارت تنظیم تازه می سازد با کسی که زد
            for u in (31, 32):
                await service.leave_any(db, u, mid)
            if (await db.get_match(mid))["status"] == "over":
                assert not B(bot.edits[-1][1]) and "تموم شد" in P(bot.edits[-1][1])
                # «میز تازه» (کارت بسته شده) در همان پیام اینلاین کارت تنظیم تازه می سازد
                await groups.on_button(_CQ(33, "gt:new:ludo", imid="IM1"), gdb=db, bot=bot)
                d = await db.one("SELECT * FROM group_drafts WHERE host = 33")
                assert d["inline_message_id"] == "IM1" and d["status"] == "setup" and "حالت بازی" in P(bot.edits[-1][1])
            # فرستادن از مینی اپ: پیام آماده با کارت تنظیم همین بازی
            pid = await groups.prepare_share(db, 33, "football")
            uid, art, kw = bot.prepared[-1]
            assert pid == "prep1" and uid == 33 and kw["allow_group_chats"] and not kw["allow_channel_chats"]
            assert (await db.draft(art.id))["game"] == "football" and art.input_message_content.rich_message.blocks
            try:
                await groups.prepare_share(db, 33, "chess")
                raise AssertionError("بازی ناشناخته")
            except service.GCError as e:
                assert e.code == "bad_game"
        finally:
            service.table_hook = None
            await db.close()

    asyncio.run(run())


def test_emoji_and_style():
    """ایموجی پریمیوم Game Club و قالب متنی عبور: متن، پیام غنی، دکمه ها، پیام همگانی با چند دکمه."""
    tmp = tempfile.mkdtemp()
    from aiogram.types import MessageEntity
    from game_club import admin, emoji as emo, groups, service, style as st
    from game_club.db import GCDatabase

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        from unittest import mock
        url = mock.patch.object(type(admin.gc), "webapp_url", new_callable=mock.PropertyMock, return_value="https://x.test/gc/")
        try:
            # بدون تنظیم: همه چیز همان ایموجی معمولی
            emo.load_rows({})
            assert emo.html_of("hokm") == "🃏" and emo.apply("سلام 🃏") == "سلام 🃏"
            assert emo.button("🃏 بازی حکم") == {"text": "🃏 بازی حکم"} and emo.button("حکم", "hokm") == {"text": "🃏 حکم"}
            # تنظیم با پیام ادمین: آفست ها UTF-16 اند (🃏 دو واحد، ⚽ یکی)
            ents = [MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id="111"),
                    MessageEntity(type="custom_emoji", offset=2, length=1, custom_emoji_id="222"),
                    MessageEntity(type="custom_emoji", offset=3, length=2, custom_emoji_id="333")]   # 🦄 در کاتالوگ نیست
            pairs = emo.from_message("🃏⚽🦄", ents)
            assert pairs == [("hokm", "111"), ("football", "222")]
            for k, eid in pairs:
                await emo.set_emoji(db, k, eid)
            await emo.set_emoji(db, "play", "444")
            emo.load_rows(await db.settings_all())      # همان چیزی که پروسه های دیگر می خوانند
            assert emo.custom_id("hokm") == "111" and emo.custom_id("football") == "222"
            # متن HTML: ⚽ با و بی FE0F؛ اعمال دوباره تگ تودرتو نمی سازد
            out = emo.apply("<b>حکم</b> 🃏 و ⚽️ و 🎲")
            assert out.count("<tg-emoji") == 2 and 'emoji-id="111">🃏<' in out and 'emoji-id="222">⚽️<' in out and "🎲" in out
            assert emo.apply(out) == out
            # دکمهٔ شیشه ای: ایموجی از متن برداشته می شود و آیکن پریمیوم کنارش می نشیند
            assert emo.button("🃏 بازی حکم") == {"text": "بازی حکم", "icon_custom_emoji_id": "111"}
            assert emo.button("حکم", "hokm") == {"text": "حکم", "icon_custom_emoji_id": "111"}
            assert emo.button("🃏") == {"text": "🃏"}                        # دکمهٔ بی متن آیکن نمی گیرد
            # قالب متنی: هر خط با RLM، سرتیتر ╮── و │، خط آخر ╯─، اسم کاربر امن
            parts = st.frame("hokm", "میز حکم", "تنظیم میز", [["سلام ", st.iso("<x>"), "!"]], foot=("coin", "امتیاز", [st.num(1250), " امتیاز"]))
            h = st.to_html(parts)
            lines = h.split("\n")
            assert all(x.startswith(st.RLM) for x in lines if x) and lines[0].startswith(st.RLM + "╮── <tg-emoji")
            assert lines[1] == st.RLM + "│   تنظیم میز" and lines[-1].startswith(st.RLM + "╯─ ") and "1,250" in lines[-1]
            assert "&lt;x&gt;" in h and lines[2] == "" and lines[-2] == st.RLM + "💰 امتیاز"
            rich = st.to_rich(parts)
            assert any(getattr(x, "custom_emoji_id", "") == "111" for x in rich) and isinstance(rich[0], str)
            # کارت گروه: پاراگراف و دکمهٔ داخل پیام با ایموجی پریمیوم
            tok = await db.new_draft(7, "hokm", {"target": 7})
            await db.player(7, "u7")
            card = await groups.setup_card(db, await db.draft(tok))
            dump = card.model_dump_json()
            assert '"custom_emoji_id":"111"' in dump and "╮── " in groups.plain(card) and "╯─ " in groups.plain(card)
            open_btn = next(b for b in groups.buttons(card) if b.callback_data == f"gs:open:{tok}")
            # دکمه های کارت گروه ایموجی ندارند، حتی وقتی پریمیوم تنظیم شده
            assert open_btn.text == "باز کردن میز" and all(isinstance(b.text, str) for b in groups.buttons(card))
            # پیام همگانی: تا ۳ دکمه، شکل قدیمی هم، صفحهٔ ناشناخته کنار گذاشته می شود
            btns = admin.parse_buttons("|ورود به Game Club|brand\nhokm-lobby.html|🃏 بازی حکم|\nbad.html|x|hokm\nludo-lobby.html|منچ|nope\nfriends.html|دوستان")
            assert btns == [("", "ورود به Game Club", "brand"), ("hokm-lobby.html", "🃏 بازی حکم", ""), ("ludo-lobby.html", "منچ", "")]
            assert admin.parse_buttons("hokm-lobby.html|بازی") == [("hokm-lobby.html", "بازی", "")]
            url.start()
            kb = admin._kb("|ورود|play\nhokm-lobby.html|🃏 بازی حکم|")
            rows = [r[0] for r in kb.inline_keyboard]
            assert [(b.text, b.icon_custom_emoji_id, b.web_app.url) for b in rows] == [
                ("ورود", "444", "https://x.test/gc/"), ("بازی حکم", "111", "https://x.test/gc/hokm-lobby.html")]
            assert admin._kb("") is None
            # متن ادمین: tg-emoji خودش هم مجاز است
            assert admin._clean_text('<tg-emoji emoji-id="9">🔥</tg-emoji> <script>') == '<tg-emoji emoji-id="9">🔥</tg-emoji> &lt;script&gt;'
            # کپی از عبور (همان پروسه): ایموجی هم شکل
            from app import emoji as ob
            ob._cache["fire"] = "555"
            try:
                assert ("fire", "555") in emo.from_obour()
            finally:
                ob._cache.pop("fire", None)
            # برگرداندن
            await emo.reset(db, "hokm")
            assert emo.custom_id("hokm") is None and "emoji:hokm" not in await db.settings_all()
        finally:
            emo.load_rows({})
            mock.patch.stopall()
            service.table_hook = None
            await db.close()

    asyncio.run(run())


def test_broadcast_from_bot():
    """پیام همگانی فقط از ربات: پیش نویس، دکمه ها با ایموجی پریمیوم، گیرنده ها، ارسال یک باره؛ پنل فقط آمار."""
    tmp = tempfile.mkdtemp()
    from game_club import admin, bot as gbot
    from game_club.db import GCDatabase

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        try:
            for i in (1, 2, 3):
                await db.player(i, f"p{i}")
            bid = await db.bc_draft(1, 1, 50, "|ورود به Game Club|brand", "all")
            # پیش نویس نه فرستاده می شود نه در آمار پنل است
            assert not await db.bc_active() and not await db.bc_list()
            text, kb = await gbot._bc_panel(db, bid, 1)
            assert "پیش‌نویس" in text and "3 نفر" in text.replace("\u2068", "").replace("\u2069", "")
            datas = [b.callback_data for r in kb.inline_keyboard for b in r]
            assert f"bc:t:{bid}:active7" in datas and f"bc:send:{bid}" in datas and f"bc:b:{bid}" in datas
            # دکمه ها از متن ادمین: ایموجی پریمیوم اول خط آیکن می شود؛ خط بد کنار می رود؛ حداکثر ۳
            lines, bad = gbot.parse_button_lines('<tg-emoji emoji-id="777">🃏</tg-emoji> بازی حکم | حکم\nخانه رو ببین | خانه\nبد | جایی\na | منچ\nb | فوتبال')
            assert lines == ["hokm-lobby.html|بازی حکم|777", "|خانه رو ببین|", "ludo-lobby.html|a|"] and bad == ["بد | جایی"]
            assert await db.bc_set_draft(bid, button="\n".join(lines), target="game:hokm")
            assert admin.parse_buttons((await db.bc_get(bid))["button"])[0] == ("hokm-lobby.html", "بازی حکم", "777")
            from game_club import emoji as emo
            assert emo.button("بازی حکم", "777") == {"text": "بازی حکم", "icon_custom_emoji_id": "777"}
            # ارسال: فقط یک بار
            assert await db.bc_launch(bid, admin._target("all", 1)) == 3
            assert await db.bc_launch(bid, "all") == 0 and not await db.bc_set_draft(bid, target="me")
            assert [b["id"] for b in await db.bc_active()] == [bid]
            # پنل: فقط آمار (مسیر فرستادن نیست)
            from unittest import mock

            async def noop(_db):
                return None
            mock.patch.object(admin, "is_admin", return_value=True).start()
            mock.patch.object(admin, "resume_if_needed", noop).start()
            r = await admin.handle("admin/broadcasts", "GET", 1, {}, {}, db)
            assert r["summary"]["count"] == 1 and r["list"][0]["target"] == "همه" and r["list"][0]["buttons"][0] == "بازی حکم"
            try:
                await admin.handle("admin/broadcast", "POST", 1, {}, {"text": "x"}, db)
                raise AssertionError("ارسال از پنل نباید باشد")
            except admin.GCError as e:
                assert e.code == "not_found"
            # لغو پیش نویس
            b2 = await db.bc_draft(1, 1, 51, "", "all")
            assert await db.bc_drop_draft(b2) and not await db.bc_drop_draft(b2) and len(await db.bc_list()) == 1
        finally:
            from unittest import mock
            mock.patch.stopall()
            await db.close()

    asyncio.run(run())


def test_emoji_admin_and_tone():
    """مدیریت ایموجی در ربات مثل عبور (دسته -> ایموجی -> فرستادن پریمیوم) و عددهای لاتین در پیام ها."""
    import re
    from types import SimpleNamespace as NS
    tmp = tempfile.mkdtemp()
    from aiogram.dispatcher.event.bases import SkipHandler
    from aiogram.types import MessageEntity
    from app.config import config as obour_cfg
    from game_club import bot as gbot, emoji as emo, groups, service
    from game_club.db import GCDatabase
    persian = re.compile("[\u06f0-\u06f9\u0660-\u0669]")

    class CQ:
        def __init__(self, data):
            self.from_user, self.data, self.answers, self.views = NS(id=5), data, [], []
            self.message = NS(edit_text=self._edit)

        async def _edit(self, text, reply_markup=None):
            self.views.append((text, reply_markup))

        async def answer(self, text=None, show_alert=False):
            self.answers.append(text)

    class Msg:
        def __init__(self, text, entities=None):
            self.from_user, self.text, self.entities, self.out = NS(id=5), text, entities, []

        async def answer(self, text, reply_markup=None, **kw):
            self.out.append((text, reply_markup))

    def datas(kb):
        return [b.callback_data for r in kb.inline_keyboard for b in r]

    def flat(t):   # عددها داخل نشانه های جداکننده جهت (FSI/PDI) هستند
        return t.replace("\u2068", "").replace("\u2069", "")

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        old_ids = list(obour_cfg.admin_ids)
        obour_cfg.admin_ids[:] = [5]
        try:
            emo.load_rows({})
            cq = CQ("ge:h")
            await gbot.on_emoji_button(cq, gdb=db)
            text, kb = cq.views[-1]
            assert f"0 از {len(emo.CATALOG)}" in flat(text) and not persian.search(text) and "ge:c:0:0" in datas(kb) and "ge:o" in datas(kb)
            cq = CQ("ge:c:1:1")                 # دستهٔ «میز و دکمه ها» صفحهٔ دوم (8 تا در هر صفحه)
            await gbot.on_emoji_button(cq, gdb=db)
            text, kb = cq.views[-1]
            assert "صفحه 2 از 2" in flat(text) and datas(kb)[:3] == ["ge:e:new", "ge:e:cancel", "ge:e:selected"] and "ge:c:1:0" in datas(kb)
            # انتخاب یک ایموجی: منتظر ایموجی پریمیوم؛ ایموجی معمولی رد می شود
            await gbot.on_emoji_button(CQ("ge:e:hokm"), gdb=db)
            m = Msg("🃏")
            await gbot.on_emoji_input(m, gdb=db)
            assert "پریمیوم نیست" in m.out[-1][0] and not emo.custom_id("hokm")
            m = Msg("🦄", [MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id="9001")])
            await gbot.on_emoji_input(m, gdb=db)
            assert emo.custom_id("hokm") == "9001" and "عوض شد" in m.out[-1][0] and "ge:e:hokm" in datas(m.out[-1][1])
            # دکمهٔ همان ایموجی حالا آیکن پریمیوم و ✨ دارد
            btn = next(b for r in m.out[-1][1].inline_keyboard for b in r if b.callback_data == "ge:e:hokm")
            assert btn.icon_custom_emoji_id == "9001" and btn.text.endswith("✨")
            # بعد از ثبت، پیام های بعدی ادمین دیگر ایموجی حساب نمی شوند
            try:
                await gbot.on_emoji_input(Msg("سلام"), gdb=db)
                raise AssertionError("باید رد می شد")
            except SkipHandler:
                pass
            # چندتا با هم
            await gbot.on_emoji_button(CQ("ge:b"), gdb=db)
            m = Msg("🎲⚽", [MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id="9002"),
                            MessageEntity(type="custom_emoji", offset=2, length=1, custom_emoji_id="9003")])
            await gbot.on_emoji_input(m, gdb=db)
            assert emo.custom_id("ludo") == "9002" and emo.custom_id("football") == "9003" and "2 ایموجی" in m.out[-1][0]
            # برگرداندن
            cq = CQ("ge:r:hokm")
            await gbot.on_emoji_button(cq, gdb=db)
            assert not emo.custom_id("hokm") and "ge:e:hokm" in datas(cq.views[-1][1])
            # /start و /help: راهنمای بازی در گروه با @آیدی ربات (نه /hokm) و دکمهٔ انتخاب گروه
            old_user, gbot.gc.username = gbot.gc.username, "gcbot"
            try:
                m = Msg("/help")
                await gbot.on_help(m)
                m2 = Msg("/start")
                m2.from_user = NS(id=5, first_name="x", last_name=None, username=None)
                await gbot.on_start(m2, command=NS(args=None), gdb=db)
            finally:
                gbot.gc.username = old_user
            for text, kb in (m.out[-1], m2.out[-1]):
                assert "@gcbot" in text and "/hokm" not in text and not persian.search(text)
                assert kb.inline_keyboard[0][0].switch_inline_query_chosen_chat.allow_group_chats
            # پیام های ربات: عددها لاتین
            await db.player(1, "a")
            await db.player(2, "b")
            r = await service.invite_create(db, 1, groups.cfg_of("hokm", {"target": 3}))
            await service.invite_join(db, 2, (await db.get_match(r["match"]))["invite"])
            await db.add_group_table(r["match"], -1, "g", "hokm", 1)
            card = await groups.render(db, await db.get_match(r["match"]), await db.group_table(r["match"]))
            body = groups.plain(card)
            assert "(2 از 4)" in body and "تا 3 دست" in body and not persian.search(body)
            tok = await db.new_draft(1, "ludo", {})
            setup = groups.plain(await groups.setup_card(db, await db.draft(tok)))
            assert "4 نفره" in setup and not persian.search(setup)
        finally:
            obour_cfg.admin_ids[:] = old_ids
            emo.load_rows({})
            service.table_hook = None
            await db.close()

    asyncio.run(run())


def test_billiard_physics():
    from game_club import billiard as Bl
    rng = random.Random(7)
    pos = Bl.rack(rng)
    assert len(pos) == 16 and all(p is not None for p in pos)
    for i in range(16):
        assert Bl._free(pos, i, *pos[i])                                   # بدون هم پوشانی
    # بریک: توپ ها پخش می شوند و هیچ توپی از میز بیرون نمی رود
    res = Bl.simulate(pos, -math.pi / 2, 1.3, (0, 0), True)
    assert res["frames"] and res["first"] > 0 and len(res["rails"]) >= 4
    for p in res["pos"]:
        assert p is None or (0 <= p[0] <= Bl.W and 0 <= p[1] <= Bl.H)
    # ضربهٔ صاف به گوشه: توپ ۱ کنار جیب بالا چپ می افتد، سفید روی میز می ماند
    pos = [None] * 16
    pos[0], pos[1] = [300.0, 300.0], [200.0, 200.0]
    res = Bl.simulate(pos, math.atan2(-100, -100), 0.35, (0, 0), False)
    assert [p[0] for p in res["pots"]] == [1] and res["pots"][0][3] == 0 and res["pos"][0] is not None
    assert res["first"] == 1


def _bl_state(n=2):
    from game_club import billiard as Bl
    seats = [{"color": c, "uid": i + 1, "name": c, "bot": False} for i, c in enumerate(Bl.seats_of(n))]
    st = Bl.new_state(seats, 0.0, 20, False, n, first=0)
    return Bl, st


def test_billiard_rules():
    Bl, st = _bl_state()
    rk = lambda: [p[:] if p else None for p in st["balls"]]   # noqa: E731
    assert st["breaking"] and st["bih"] and Bl.current(st) == "0"
    # بریک: توپ سفید جلوی خط سر قابل گذاشتن نیست
    assert Bl.shot(st, 0, -1.57, 1, 0, 0, 400, 900, 10.0) == "bad_place"
    assert Bl.shot(st, 1, -1.57, 1, 0, 0, None, None, 10.0) == "not_your_turn"
    # بریک قانونی بدون افتادن توپ: میز باز، نوبت حریف
    res = {"pos": rk(), "pots": [], "first": 3, "rails": [0, 1, 2, 3, 4], "dur": 1.0}
    Bl._resolve(st, 0, res, [], 10.0)
    assert not st["breaking"] and st["solids"] == -1 and st["turn"] == 1 and not st["bih"]
    # میز باز: افتادن تک رنگ = گروه تک رنگ مال تیم زننده و نوبت ادامه دارد
    b = rk(); b[2] = None
    Bl._resolve(st, 1, {"pos": b, "pots": [[2, .5, 1, 0]], "first": 2, "rails": [], "dur": 1.0}, Bl.targets(st, 1), 20.0)
    assert st["solids"] == 1 and st["turn"] == 1 and Bl.solids_of(st, 1) and not Bl.solids_of(st, 0)
    # برخورد اول با توپ حریف = خطا، حریف توپ در دست
    Bl._resolve(st, 1, {"pos": rk(), "pots": [], "first": 9, "rails": [9], "dur": 1.0}, Bl.targets(st, 1), 30.0)
    assert st["turn"] == 0 and st["bih"] and st["msg"] == "wrong_first"
    # توپ در دست: روی توپ دیگر نمی شود گذاشت
    p9 = st["balls"][9]
    assert Bl.shot(st, 0, 0, .5, 0, 0, p9[0], p9[1], 40.0) == "bad_place"
    # افتادن سفید = خطا
    b = rk(); b[0] = None
    Bl._resolve(st, 0, {"pos": b, "pots": [[0, .5, 1, 2]], "first": 9, "rails": [], "dur": 1.0}, Bl.targets(st, 0), 50.0)
    assert st["turn"] == 1 and st["bih"] and st["msg"] == "scratch" and st["balls"][0] is not None
    # ۸ پیش از پاک شدن گروه = باخت تیم زننده
    _, st2 = _bl_state()
    st2["breaking"], st2["solids"] = False, 0
    b = [p[:] for p in st2["balls"]]; b[8] = None
    Bl._resolve(st2, 0, {"pos": b, "pots": [[8, .5, 1, 1]], "first": 1, "rails": [], "dur": 1.0}, Bl.targets(st2, 0), 60.0)
    assert st2["over"] and st2["winner"] == 1 and Bl.winners(st2) == {"1"}
    # گروه پاک، ۸ بعد از برخورد اول با خود ۸ = برد
    _, st3 = _bl_state()
    st3["breaking"], st3["solids"] = False, 0
    for k in range(1, 8):
        st3["balls"][k] = None
    assert Bl.targets(st3, 0) == [8]
    b = [p[:] if p else None for p in st3["balls"]]; b[8] = None
    Bl._resolve(st3, 0, {"pos": b, "pots": [[8, .5, 1, 1]], "first": 8, "rails": [], "dur": 1.0}, [8], 70.0)
    assert st3["over"] and st3["winner"] == 0 and st3["msg"] == "won"
    # وقت تمام شد = حریف توپ در دست
    _, st4 = _bl_state()
    Bl.tick(st4, st4["deadline"] + 1)
    assert st4["turn"] == 1 and st4["bih"] and st4["players"]["0"]["misses"] == 1


def test_billiard_teams_and_bot_games():
    from game_club import billiard as Bl
    random.seed(5)
    assert Bl.team(0) == Bl.team(2) != Bl.team(1) == Bl.team(3)
    for n in (2, 4, 4):
        st = Bl.new_state([{"color": c, "name": c, "bot": True} for c in Bl.seats_of(n)], 0.0, 20, False, n)
        t = 0.0
        while not st["over"] and t < 30000:
            t += 1.0
            Bl.tick(st, t)
            for p in st["balls"]:
                assert p is None or (0 <= p[0] <= Bl.W and 0 <= p[1] <= Bl.H)
        assert st["over"] and st["winner"] in (0, 1)
        assert Bl.winners(st) == {s for k, s in enumerate(st["order"]) if k % 2 == st["winner"]}
    # چهار نفره: خروج یک نفر بازی را تمام نمی کند (ربات جایش بازی می کند)
    st = Bl.new_state([{"color": c, "uid": i + 1, "name": c, "bot": False} for i, c in enumerate(Bl.SEATS4)], 0.0, 20, False, 4)
    Bl.leave(st, "2", 1.0)
    assert not st["over"] and st["players"]["2"]["out"]
    _, st2 = _bl_state(2)
    Bl.leave(st2, "0", 1.0)
    assert st2["over"] and Bl.winners(st2) == {"1"}


def test_static_cache_headers():
    """فایل های ثابت: نسخه دار یک ساله و immutable، بقیه با ETag (پرسش دوباره = ۳۰۴)، متن ها فشرده؛ sw.js و صفحه ها no-cache."""
    import gzip as gz
    from game_club import wsgi as W

    def get(rel, **env):
        got = {}
        body = b"".join(W._file(lambda st, h: got.update(status=st, h=dict(h)), rel, env))
        return got["status"], got["h"], body
    ver = W._asset_ver("static/gc.js")
    st, h, body = get("static/gc.js", QUERY_STRING="v=" + ver, HTTP_ACCEPT_ENCODING="gzip, br")
    assert st == "200 OK" and "immutable" in h["Cache-Control"] and h["Content-Encoding"] == "gzip"
    raw = gz.decompress(body)
    assert raw == open(os.path.join(W.WEB_DIR, "static", "gc.js"), "rb").read() and len(body) < len(raw) / 2
    assert "immutable" not in get("static/gc.js", QUERY_STRING="v=old")[1]["Cache-Control"]
    st, h, body = get("static/gc.js", HTTP_IF_NONE_MATCH=h["ETag"])
    assert st == "304 Not Modified" and body == b""
    assert get("static/gc.js")[1].get("Content-Encoding") is None          # بدون gzip در درخواست
    st, h, _ = get("sw.js")
    assert st == "200 OK" and h["Cache-Control"] == "no-cache"
    st, h, body = get("index.html", HTTP_ACCEPT_ENCODING="gzip")
    assert h["Cache-Control"] == "no-cache" and "Content-Security-Policy" in h
    assert b'static/gc.js?v=' + ver.encode() in gz.decompress(body)
    assert get("../wsgi.py")[0].startswith("404")


def test_billiard_break_known_in_advance():
    """دو عدد تصادفی بریک از پیش در نمای بازی است (bj)، تا گوشی بریک را همان لحظه عیناً مثل سرور نشان بدهد."""
    import math
    Bl, st = _bl_state()
    bj = st["bj"]
    v = Bl.view(st, "0", 0, 0.0)
    assert v["breaking"] and v["bj"] == bj and all(0 <= x < 1 for x in bj)
    pos0 = [p[:] if p else None for p in st["balls"]]
    a, p = -math.pi / 2 + 0.01, 0.9
    assert Bl.shot(st, 0, a, p, 0, 0, None, None, 10.0) is None
    e = next(x for x in st["events"] if x["t"] == "shot")
    pw, ang = p * (Bl.BREAK_BONUS + bj[0] * Bl.BREAK_RAND), a + (bj[1] * Bl.BREAK_JIT * 2 - Bl.BREAK_JIT)
    assert e["p"] == round(pw, 3) and e["a"] == round(ang, 4)
    # همان ورودی ها، همان فریم ها (همان چیزی که گوشی پیش از رسیدن جواب پخش کرده)
    assert Bl.simulate(pos0, ang, pw, (0.0, 0.0), True)["frames"] == e["frames"]
    assert st["bj"] != bj                       # بریک بعدی (اگر میز دوباره چیده شد) عدد تازه دارد
    if not st["breaking"]:
        assert Bl.view(st, "0", 0, 20.0)["bj"] is None


def test_billiard_live_aim():
    from game_club import billiard as Bl
    random.seed(9)
    st = Bl.new_state([{"color": c, "uid": i + 1, "name": c, "bot": False} for i, c in enumerate(Bl.SEATS2)], 0.0, 30, False, 2, 0)
    t = st["next_at"]
    assert Bl.aim(st, 1, 0.5, 0.2, now=t) == "not_your_turn"
    assert Bl.aim(st, 0, 0.5, 0.2, now=t) is None
    lv = Bl.view(st, "1", 0, t)["live"]
    assert lv["c"] == "0" and abs(lv["a"] - 0.5) < 1e-6 and lv["p"] == 0.2 and lv["cue"] is None
    assert Bl.aim(st, 0, 0.9, 0.2, now=t + 0.1) == "same"          # پشت سر هم: چیزی نوشته نمی شود
    # توپ در دست: جای مجاز فرستاده می شود، جای غیرمجاز نه
    assert Bl.aim(st, 0, 0.9, 0.0, Bl.W / 2, Bl.BREAK_MIN_Y + 40, now=t + 1) is None
    assert Bl.view(st, "1", 0, t)["live"]["cue"] == [round(Bl.W / 2, 1), round(Bl.BREAK_MIN_Y + 40, 1)]
    assert Bl.aim(st, 0, 0.9, 0.0, Bl.W / 2, 300, now=t + 2) is None
    assert Bl.view(st, "1", 0, t)["live"]["cue"] is None
    assert Bl.shot(st, 0, -1.5, 0.8, now=t + 3) is None
    assert Bl.view(st, "1", 0, t + 3)["live"] is None                # بعد از ضربه نشانه گیری پاک است
    # ربات: اول نزدیک هدف بدون قدرت، کمی پیش از ضربه دقیق با قدرت، بعد همان ضربه
    st = Bl.new_state([{"color": "0", "uid": 1, "name": "a"}, {"color": "1", "name": "b", "bot": True}], 0.0, 30, False, 2, 1)
    t0 = st["next_at"] - Bl.BOT_THINK + 0.1
    Bl.tick(st, t0)
    lv = Bl.view(st, "0", 0, t0)["live"]
    assert lv and lv["c"] == "1" and lv["p"] == 0
    plan = st["plan"]["v"]
    Bl.tick(st, st["next_at"] - 0.5)
    lv = Bl.view(st, "0", 0, st["next_at"] - 0.5)["live"]
    assert abs(lv["a"] - round(plan[0], 4)) < 1e-6 and lv["p"] > 0
    Bl.tick(st, st["next_at"] + 0.01)
    sh = [e for e in st["events"] if e["t"] == "shot"][-1]
    # اگر ربات توپ بیندازد نوبت با خودش می ماند و برای ضربهٔ بعد دوباره برنامه می ریزد
    assert sh["c"] == "1" and sh["auto"] and ("plan" not in st or st["order"][st["turn"]] == "1")


def test_billiard_service_flow():
    from game_club import service
    from game_club.db import GCDatabase
    tmp = tempfile.mkdtemp()

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        real = service.time.time
        clock = [80_000.0]
        service.time.time = lambda: clock[0]
        try:
            for tg in (1, 2, 3, 4):
                await db.player(tg, f"p{tg}")
                await db.credit(tg, 1000)
            # تمرین با ربات: دو نفره
            r = await service.queue_join(db, 1, {"game": "billiard", "mode": "free", "players": 2, "solo": True})
            mid = r["match"]
            v = await service.match_view(db, 1, mid)
            g = v["game"]
            assert g["n"] == 2 and g["breaking"] and len(g["balls"]) == 16 and v["cfg"]["players"] == 2
            # تا نوبت من شود (ربات ممکن است اول بزند)
            for _ in range(20):
                m = await db.get_match(mid)
                st = m["state"]
                clock[0] = max(clock[0], st["next_at"]) + 0.2
                if st["order"][st["turn"]] == v["me"] and not st["over"]:
                    break
                await service.match_view(db, 1, mid)
            assert await service.act(db, 1, mid, "aim", data={"a": -1.2, "p": 0.3}) == {"ok": True}
            lv = (await service.match_view(db, 1, mid))["game"]["live"]
            assert lv["c"] == v["me"] and abs(lv["a"] + 1.2) < 1e-6 and lv["p"] == 0.3
            v = await service.act(db, 1, mid, "shot", data={"a": -1.5, "p": 0.8, "sx": 0, "sy": 0})
            # فقط آخرین ضربه فریم دارد (فریم ضربه های قبلی برای کوچک ماندن وضعیت پاک می شود)
            shots = [e for e in v["game"]["events"] if e["t"] == "shot"]
            assert shots and shots[-1].get("frames") and all(len(h) == 4 for h in shots[-1]["hits"])
            assert (await service.my_tables(db, 1))[0]["game"] == "billiard"
            await service.leave_any(db, 1, mid)
            assert (await db.get_match(mid))["status"] == "over"
            # چهار نفره یاری با امتیاز: اولین مهمان یار سازنده (صندلی ۲) و جایزه بین تیم برنده
            cfg = {"game": "billiard", "mode": "stake", "entry": 100, "players": 4}
            inv = await service.invite_create(db, 1, cfg)
            for tg in (2, 3, 4):
                await service.invite_join(db, tg, inv["code"])
            m = await db.get_match(inv["match"])
            assert m["status"] == "playing"
            rows = {r["tg_id"]: r["color"] for r in await db.match_players(inv["match"])}
            assert rows == {1: "0", 2: "2", 3: "1", 4: "3"}
            assert [(await db.get_player(tg))["points"] for tg in (1, 2, 3, 4)] == [900] * 4

            def win0(mm):
                from game_club import billiard
                billiard._finish(mm["state"], 0, "pot8")
                mm["status"] = "over"
                return True, None
            await service.mutate(db, inv["match"], win0)
            pts = {tg: (await db.get_player(tg))["points"] for tg in (1, 2, 3, 4)}
            assert pts == {1: 1100, 2: 1100, 3: 900, 4: 900}, pts
        finally:
            service.time.time = real
            await db.close()

    asyncio.run(run())



def _dv(players=2, variant="classic", bots=False, first=0):
    from game_club import divar as Dv
    seats = [{"color": c, "uid": None if bots else i + 1, "name": c, "bot": bots} for i, c in enumerate(Dv.seats_of(players))]
    return Dv, Dv.new_state(seats, 0.0, 20, False, players, variant, first)


def test_divar_rules():
    Dv, st = _dv()
    assert st["size"] == 9 and st["order"] == ["0", "2"] and st["players"]["0"]["walls"] == 10
    assert st["players"]["0"]["pos"] == [8, 4] and st["players"]["2"]["pos"] == [0, 4]
    t = st["next_at"]
    # حرکت عادی و حرکت غیرمجاز
    assert Dv.move(st, 0, 6, 4, t) == "illegal_move"
    assert Dv.move(st, 1, 1, 4, t) == "not_your_turn"
    assert Dv.move(st, 0, 7, 4, t) is None and st["players"]["0"]["pos"] == [7, 4]
    # پرش از روی مهره و حرکت کج وقتی پشتش دیوار است
    st["players"]["0"]["pos"], st["players"]["2"]["pos"] = [4, 4], [3, 4]
    st["turn"] = 0
    assert sorted(Dv.moves(st, "0")) == sorted([[5, 4], [2, 4], [4, 5], [4, 3]])
    st["walls"].append(["h", 2, 4, "2"])
    assert sorted(Dv.moves(st, "0")) == sorted([[5, 4], [3, 5], [3, 3], [4, 5], [4, 3]])
    # دیوار روی دیوار، ضربدری، کنار هم با هم پوشانی، بیرون صفحه
    assert Dv.wall_error(st, "h", 2, 4) == "wall_taken"
    assert Dv.wall_error(st, "h", 2, 5) == "wall_taken"
    assert Dv.wall_error(st, "v", 2, 4) == "wall_taken"
    assert Dv.wall_error(st, "h", 2, 6) is None
    assert Dv.wall_error(st, "h", 8, 0) == "bad_wall"
    Dv2, s2 = _dv()
    # جعبهٔ بسته: [7..8,3..4] فقط از ستون 5 راه دارد؛ بستنش ممنوع است
    s2["walls"] = [["h", 6, 3, "2"], ["v", 7, 2, "2"]]
    assert Dv2.wall_error(s2, "v", 7, 4) == "wall_blocks"
    # دیوار: کم شدن موجودی، تمام شدن دیوار
    Dv3, s3 = _dv()
    t = s3["next_at"]
    assert Dv3.wall(s3, 0, "h", 3, 3, t) is None and s3["players"]["0"]["walls"] == 9 and s3["turn"] == 1
    s3["players"]["2"]["walls"] = 0
    assert Dv3.wall(s3, 1, "h", 5, 5, s3["next_at"]) == "no_walls"
    # برنده: رسیدن به ضلع روبه رو
    Dv4, s4 = _dv()
    s4["players"]["0"]["pos"] = [1, 0]
    assert Dv4.move(s4, 0, 0, 0, s4["next_at"]) is None and s4["over"] and Dv4.winners(s4) == {"0"}
    # ستاره: مقصد خانهٔ وسط، ۱۱×۱۱ و ۷ دیوار
    Dv5, s5 = _dv(4, "star")
    assert s5["size"] == 11 and all(p["walls"] == 7 for p in s5["players"].values())
    assert s5["players"]["1"]["pos"] == [5, 0] and Dv5.at_goal(s5, "3", 5, 5) and not Dv5.at_goal(s5, "3", 5, 0)
    Dv6, s6 = _dv(4)
    assert all(p["walls"] == 5 for p in s6["players"].values()) and Dv6.at_goal(s6, "1", 3, 8)


def test_divar_bot_games_and_leave():
    from game_club import divar as Dv
    random.seed(7)
    for players, variant in ((2, "classic"), (4, "classic"), (4, "star")):
        for _ in range(4):
            _, st = _dv(players, variant, bots=True)
            t, k = 0.0, 0
            while not st["over"] and k < 3000:
                t = max(t + 0.01, st["next_at"])
                Dv.tick(st, t)
                k += 1
                assert all(Dv.path(st, s) for s in st["order"])
            assert st["over"] and st["winner"] in st["order"]
            w = st["players"][st["winner"]]["pos"]
            assert Dv.at_goal(st, st["winner"], *w)
    # وقت تمام شد: یک قدم به جای بازیکن در کوتاه ترین راه
    _, st = _dv()
    Dv.tick(st, st["deadline"] + 0.1)
    assert st["players"]["0"]["pos"] == [7, 4] and st["players"]["0"]["misses"] == 1
    # دو نفره: خروج یعنی برد حریف؛ چهار نفره: ربات جای او بازی می کند
    _, st = _dv()
    Dv.leave(st, "0", 1.0)
    assert st["over"] and Dv.winners(st) == {"2"}
    _, st = _dv(4)
    Dv.leave(st, "1", 1.0)
    assert not st["over"] and st["players"]["1"]["out"]


def test_divar_service_flow():
    from game_club import groups, service
    from game_club.db import GCDatabase
    tmp = tempfile.mkdtemp()

    async def run():
        db = GCDatabase(os.path.join(tmp, "gc.db"))
        await db.connect()
        real = service.time.time
        clock = [90_000.0]
        service.time.time = lambda: clock[0]
        try:
            for tg in (1, 2, 3, 4):
                await db.player(tg, f"p{tg}")
                await db.credit(tg, 1000)
            # تنظیم نامعتبر: ستاره فقط چهار نفره
            try:
                service.norm_cfg({"game": "divar", "players": 2, "variant": "star"})
                raise AssertionError("bad cfg passed")
            except service.GCError as e:
                assert e.code == "bad_cfg"
            # تمرین با ربات
            r = await service.queue_join(db, 1, {"game": "divar", "mode": "free", "players": 2, "solo": True})
            mid = r["match"]
            # صفحهٔ هر بازی بی شناسه فقط میز همان بازی را می گیرد
            assert await db.active_match_of(1, "divar") == mid and await db.active_match_of(1, "billiard") is None
            v = await service.match_view(db, 1, mid)
            g = v["game"]
            assert g["size"] == 9 and g["n"] == 2 and v["me"] in g["order"]
            for _ in range(20):
                m = await db.get_match(mid)
                st = m["state"]
                clock[0] = max(clock[0], st["next_at"]) + 0.2
                if st["order"][st["turn"]] == v["me"] and not st["over"]:
                    break
                await service.match_view(db, 1, mid)
            v = await service.match_view(db, 1, mid)
            mv = v["game"]["moves"]
            assert mv
            v = await service.act(db, 1, mid, "move", data={"r": mv[0][0], "c": mv[0][1]})
            assert v["game"]["players"][v["me"]]["pos"] == mv[0]
            try:
                await service.act(db, 1, mid, "wall", data={"o": "h", "r": 3, "c": 3})
                raise AssertionError("acted out of turn")
            except service.GCError as e:
                assert e.code in ("not_your_turn", "not_ready")
            assert (await service.my_tables(db, 1))[0]["game"] == "divar"
            await service.leave_any(db, 1, mid)
            assert (await db.get_match(mid))["status"] == "over"
            # چهار نفرهٔ ستاره با امتیاز: یک برنده همهٔ جایزه را می برد
            cfg = {"game": "divar", "mode": "stake", "entry": 100, "players": 4, "variant": "star"}
            inv = await service.invite_create(db, 1, cfg)
            for tg in (2, 3, 4):
                await service.invite_join(db, tg, inv["code"])
            m = await db.get_match(inv["match"])
            assert m["status"] == "playing" and m["state"]["size"] == 11
            rows = {r["tg_id"]: r["color"] for r in await db.match_players(inv["match"])}
            assert rows == {1: "0", 2: "2", 3: "1", 4: "3"}

            def win(mm):
                from game_club import divar
                divar._finish(mm["state"], "1")
                mm["status"] = "over"
                return True, None
            await service.mutate(db, inv["match"], win)
            pts = {tg: (await db.get_player(tg))["points"] for tg in (1, 2, 3, 4)}
            prize = 400 - 400 * service.gc.rake_percent // 100
            assert pts == {1: 900, 2: 900, 3: 900 + prize, 4: 900}, pts
            # گروه: انتخاب «۴ نفره · ستاره» به players و variant تبدیل می شود
            c = groups.cfg_of("divar", {"kind": 5})
            assert c["players"] == 4 and c["variant"] == "star" and service.norm_cfg(c)["variant"] == "star"
            assert groups.cfg_of("divar", {})["players"] == 2 and groups.need_of("divar", groups.cfg_of("divar", {"kind": 4})) == 4
        finally:
            service.time.time = real
            await db.close()

    asyncio.run(run())

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
