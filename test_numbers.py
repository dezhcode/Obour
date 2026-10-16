"""تست آفلاین شماره مجازی (SMSBurner) با سرور شبیه سازی شده.

هیچ درخواستی به smsburner.com نمی رود و هیچ پولی خرج نمی شود؛ فقط منطق
خرید، قیمت و (مهم تر از همه) جابجایی پول بررسی می شود:
کسر، برگشت، لغو، خرید مبهم، و اینکه دو بررسی همزمان هیچ وقت دوبار
پول برنگردانند یا دوبار کد تحویل ندهند.

    python test_numbers.py
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, ".")

import httpx

from app import smsburner
from app.db import Database
from app.services import numbers_shop as ns

smsburner.MIN_INTERVAL = 0

RATE = 100_000          # تومان به ازای هر تتر
USD = 0.35              # قیمت دلاری شماره در کاتالوگ شبیه سازی شده


class FakeServer:
    """SMSBurner شبیه سازی شده. mode رفتار خرید را عوض می کند."""

    def __init__(self) -> None:
        self.mode = "ok"
        self.status = "active"
        self.sms = None
        self.cancel_status = 200
        self.calls: list[tuple[str, str]] = []
        self.balance = 10.0

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path.replace("/api/v1", ""), request.method
        self.calls.append((method, path))
        if path == "/catalog":
            return httpx.Response(200, json={"ok": True, "rows": [
                {"service_id": 2, "service": "Telegram", "service_slug": "telegram", "category": "social",
                 "country_code": "us", "country": "United States", "price": USD, "stock": 999},
                {"service_id": 2, "service": "Telegram", "service_slug": "telegram", "category": "social",
                 "country_code": "in", "country": "India", "price": 0.16, "stock": 999},
                {"service_id": 2, "service": "Telegram", "service_slug": "telegram", "category": "social",
                 "country_code": "de", "country": "Germany", "price": 1.0, "stock": 0},
            ]})
        if path == "/account":
            return httpx.Response(200, json={"ok": True, "balance": self.balance})
        if path == "/quote":
            return httpx.Response(200, json={"ok": True, "price": USD})
        if path == "/numbers" and method == "POST":
            if self.mode == "ok":
                return httpx.Response(201, json={"ok": True, "number_id": 101, "phone_number": "15551234567",
                                                 "price": USD, "status": "active"})
            if self.mode == "stock":
                return httpx.Response(409, json={"ok": False, "error": "out_of_stock", "message": "No numbers"})
            if self.mode == "funds":
                return httpx.Response(402, json={"error": "insufficient_balance", "need_usd": 0.5, "have_usd": 0.1})
            if self.mode == "timeout":
                raise httpx.ReadTimeout("slow", request=request)
            if self.mode == "5xx":
                return httpx.Response(502, text="bad gateway")
            if self.mode == "noid":
                return httpx.Response(201, json={"ok": True, "phone_number": "15550000000"})
            if self.mode == "401":
                return httpx.Response(401, json={"ok": False, "error": "unauthorized"})
        if path == "/numbers/101" and method == "GET":
            return httpx.Response(200, json={"ok": True, "phone_number": "15551234567",
                                             "sms_code": self.sms, "status": self.status})
        if path == "/numbers/101/cancel" and method == "POST":
            if self.cancel_status == 409:
                return httpx.Response(409, json={"ok": False, "error": "sms_received"})
            return httpx.Response(200, json={"ok": True, "refunded": True})
        return httpx.Response(404, json={"ok": False, "error": "not_found"})


def install(server: FakeServer) -> None:
    def make(_db):  # noqa: ANN001
        sb = smsburner.SmsBurner("AbC3-dEf4-gHj5-kLm6")
        sb._http = httpx.AsyncClient(
            base_url=smsburner.BASE_URL, transport=httpx.MockTransport(server.handler),
            headers={"Authorization": "Bearer x"})
        return sb

    async def fake_client(db):  # noqa: ANN001
        return make(db)

    ns.client = fake_client      # type: ignore[assignment]
    smsburner._cache.clear()


async def new_user(db: Database, tg: int, balance: int) -> dict:
    u = await db.get_or_create_user(tg, f"u{tg}", f"User{tg}")
    if balance:
        await db.atomic_credit(u["id"], balance)
    return await db.get_user(u["id"])


async def bal(db: Database, u: dict) -> int:
    return int((await db.get_user(u["id"]))["balance"])


async def main() -> None:
    tmp = tempfile.mkdtemp()
    db = Database(os.path.join(tmp, "n.db"))
    await db.connect()
    try:
        await run(db)
    finally:
        await db.close()
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nهمه تست های شماره مجازی گذشت ✅")


async def run(db: Database) -> None:
    await db.set_setting("ai_usdt_rate", str(RATE))
    await db.set_setting(ns.KEY_SETTING, "AbC3-dEf4-gHj5-kLm6")
    srv = FakeServer()
    install(srv)
    price = ns.price_toman(USD, RATE, await ns.load_cfg(db))
    assert price == 49_000, price                        # 35000 × 1.4 = 49000
    assert ns.price_toman(0.1, RATE, await ns.load_cfg(db)) == 15_000   # کف سود ۵۰۰۰: 10000 + 5000
    print("OK pricing", price)

    # ۱) خرید موفق ← منتظر کد ← کد می رسد ← فقط یک بار تحویل
    u = await new_user(db, 1, 100_000)
    r = await ns.buy(db, None, u, "2", "us")
    assert r["status"] == ns.ACTIVE, r
    o = r["order"]
    assert o["phone"] == "+15551234567" and o["provider_id"] == "101" and o["expires_at"]
    assert await bal(db, u) == 100_000 - price
    r1 = await ns.check(db, o)
    assert r1["event"] is None and r1["status"] == ns.ACTIVE
    srv.sms = "847291"
    a, b = await asyncio.gather(ns.check(db, o), ns.check(db, o))
    assert sorted([bool(a["event"]), bool(b["event"])]) == [False, True], (a["event"], b["event"])
    done = await db.get_number_order(o["id"])
    assert done["status"] == ns.COMPLETED and done["sms_code"] == "847291"
    assert await bal(db, u) == 100_000 - price          # کد آمد: پولی برنمی گردد
    print("OK buy → code (single delivery under race)")

    # ۲) لغو: پول یک بار برمی گردد
    srv.sms, srv.status = None, "active"
    u2 = await new_user(db, 2, 100_000)
    o2 = (await ns.buy(db, None, u2, "2", "us"))["order"]
    assert await bal(db, u2) == 100_000 - price
    c1, c2 = await asyncio.gather(ns.cancel(db, o2), ns.cancel(db, o2))
    assert await bal(db, u2) == 100_000, await bal(db, u2)       # فقط یک برگشت
    assert (await db.get_number_order(o2["id"]))["status"] == ns.REFUNDED
    assert sorted([bool(c1.get("event")), bool(c2.get("event"))]) == [False, True]
    print("OK cancel refunds exactly once")

    # ۳) لغو وقتی پیامک همین حالا رسیده: کد تحویل می شود، پولی برنمی گردد
    u3 = await new_user(db, 3, 100_000)
    o3 = (await ns.buy(db, None, u3, "2", "us"))["order"]
    srv.cancel_status, srv.sms = 409, "111222"
    r3 = await ns.cancel(db, o3)
    assert r3["status"] == ns.COMPLETED and r3["order"]["sms_code"] == "111222"
    assert await bal(db, u3) == 100_000 - price
    srv.cancel_status, srv.sms = 200, None
    print("OK cancel after SMS delivers the code instead")

    # ۴) سرویس دهنده خودش منقضی/لغو کرد: پول کاربر یک بار برمی گردد
    u4 = await new_user(db, 4, 100_000)
    o4 = (await ns.buy(db, None, u4, "2", "us"))["order"]
    srv.status = "expired"
    e1, e2 = await asyncio.gather(ns.check(db, o4), ns.check(db, o4))
    assert await bal(db, u4) == 100_000
    assert sorted([bool(e1["event"]), bool(e2["event"])]) == [False, True]
    srv.status = "active"
    print("OK provider expiry refunds exactly once")

    # ۵) موجود نیست (۴۰۹): پول برمی گردد
    srv.mode = "stock"
    u5 = await new_user(db, 5, 100_000)
    r5 = await ns.buy(db, None, u5, "2", "us")
    assert r5["status"] == ns.UNAVAILABLE and await bal(db, u5) == 100_000
    assert (await db.get_number_order(r5["order"]["id"]))["status"] == ns.FAILED
    # کشور بی موجودی در کاتالوگ: حتی تماس خرید هم نمی رود
    n_before = len([c for c in srv.calls if c == ("POST", "/numbers")])
    r5b = await ns.buy(db, None, u5, "2", "de")
    assert r5b["status"] == ns.UNAVAILABLE and "order" not in r5b
    assert len([c for c in srv.calls if c == ("POST", "/numbers")]) == n_before
    print("OK out of stock refunds / blocks")

    # ۶) موجودی خود ما نزد سرویس دهنده تمام شده (۴۰۲): پول کاربر برمی گردد
    srv.mode = "funds"
    u6 = await new_user(db, 6, 100_000)
    r6 = await ns.buy(db, None, u6, "2", "us")
    assert r6["status"] == ns.NO_FUNDS and await bal(db, u6) == 100_000
    print("OK provider out of funds refunds user")

    # ۷) پاسخ مبهم (timeout / 5xx / بدون شناسه): پول برنمی گردد، دست ادمین
    for mode in ("timeout", "5xx", "noid"):
        srv.mode = mode
        u7 = await new_user(db, 70 + len(mode), 100_000)
        r7 = await ns.buy(db, None, u7, "2", "us")
        assert r7["status"] == ns.UNKNOWN, (mode, r7["status"])
        assert await bal(db, u7) == 100_000 - price, mode
        # ادمین «برگشت پول» می زند؛ دوبار زدن دوبار پول نمی دهد
        s1 = await ns.settle_manual(db, r7["order"], refund=True)
        s2 = await ns.settle_manual(db, r7["order"], refund=True)
        assert s1["status"] == ns.FAILED and await bal(db, u7) == 100_000, mode
        assert s2["status"] == ns.FAILED
        assert await bal(db, u7) == 100_000
    print("OK ambiguous purchase → manual settle, no double refund")

    # ۸) موجودی کیف پول کم: هیچ سفارشی ساخته نمی شود
    srv.mode = "ok"
    u8 = await new_user(db, 8, 1_000)
    r8 = await ns.buy(db, None, u8, "2", "us")
    assert r8["status"] == ns.INSUFFICIENT and await bal(db, u8) == 1_000
    assert not await db.user_number_orders(u8["id"])
    print("OK insufficient wallet")

    # ۹) seed نامعتبر: خرید انجام نمی شود، پول برمی گردد
    srv.mode = "401"
    u9 = await new_user(db, 9, 100_000)
    r9 = await ns.buy(db, None, u9, "2", "us")
    assert r9["status"] == ns.PROVIDER_ERROR and await bal(db, u9) == 100_000
    srv.mode = "ok"
    print("OK invalid seed refunds")

    # ۱۰) قفل: خرید همزمان یک کاربر
    u10 = await new_user(db, 10, 300_000)
    ra, rb = await asyncio.gather(ns.buy(db, None, u10, "2", "us"), ns.buy(db, None, u10, "2", "us"))
    assert sorted([ra["status"], rb["status"]]) == sorted([ns.ACTIVE, ns.LOCKED]), (ra["status"], rb["status"])
    assert await bal(db, u10) == 300_000 - price
    print("OK concurrent buys are locked")

    # ۱۱) کاتالوگ: بی موجودی و بیشتر از موجودی ما نمایش داده نمی شود
    cat = await ns.catalog(db, force=True)
    assert {r["cc"] for r in cat["rows"]} == {"us", "in"}
    assert ns.countries_of(cat, "2")[0]["cc"] == "in"                # ارزان ترین اول
    srv.balance = 0.2                                                # فقط هند (0.16) می رسد
    cat = await ns.catalog(db, force=True)
    assert {r["cc"] for r in cat["rows"]} == {"in"}
    srv.balance = 10.0
    print("OK catalog filters")

    # ۱۲) نمایش و کیبوردها: callback_data زیر ۶۴ بایت و بدون خطا
    from app import i18n, keyboards
    from app.handlers.numbers import order_view

    cat = await ns.catalog(db, force=True)
    kbs = [keyboards.num_hub_kb(ns.services_of(cat)), keyboards.num_countries_kb(cat["rows"], "2", 0, 1),
           keyboards.num_confirm_kb(True, "2", "us"), keyboards.num_active_kb(99999),
           keyboards.num_done_kb("2"), keyboards.num_orders_kb(await db.user_number_orders(u["id"])),
           keyboards.num_cancel_ask_kb(5), keyboards.admin_num_kb(True), keyboards.admin_num_kb(False),
           keyboards.num_cats_kb([{"key": "social", "title": "شبکه", "emoji": "💬", "count": 3}]),
           keyboards.num_services_kb(ns.services_of(cat), "social", 0, 2)]
    for order in await db.user_number_orders(u["id"]) + await db.user_number_orders(u2["id"]) \
            + await db.user_number_orders(u4["id"]) + await db.user_number_orders(u10["id"]):
        text, kb = order_view(order)
        kbs.append(kb)
        assert text, order["status"]
    first = (await db.user_number_orders(u["id"]))[0]
    for lang in ("fa", "en", "ru", "zh"):
        with i18n.using(lang):
            assert order_view(first)[0]
    for kb in kbs:
        for row in kb.inline_keyboard:
            for b in row:
                assert len((b.callback_data or "").encode()) <= 64, b.callback_data
    print("OK views & keyboards")

    # ۱۳) آمار
    st = await db.number_stats()
    assert st["completed"] >= 2 and st["revenue"] >= 2 * price, st
    print("OK stats", {k: st[k] for k in ("total", "completed", "active", "unknown", "refunded")})

    await handler_flow(db, srv)


class FakeCall:
    """CallbackQuery ساختگی: دکمه ای که کاربر می زند و صفحه ای که ربات نشان می دهد."""

    def __init__(self, data: str) -> None:
        from unittest.mock import AsyncMock, MagicMock

        self.data = data
        self.message = MagicMock()
        self.message.chat.id, self.message.message_id = 777, 5
        self.message.edit_text = AsyncMock(return_value=self.message)
        self.message.answer = AsyncMock(return_value=self.message)
        self.answer = AsyncMock()
        self.bot = AsyncMock()

    @property
    def page(self) -> str:
        return self.message.edit_text.call_args.args[0]

    @property
    def buttons(self) -> list[str]:
        kb = self.message.edit_text.call_args.kwargs.get("reply_markup")
        return [b.callback_data for row in kb.inline_keyboard for b in row] if kb else []


async def handler_flow(db: Database, srv: FakeServer) -> None:
    """مسیر کامل کاربر در ربات: منو ← سرویس ← کشور ← تایید ← خرید ← کد."""
    from app.handlers import numbers as h

    h.ensure_watcher = lambda *a, **k: None      # type: ignore[assignment]
    srv.mode, srv.sms, srv.status = "ok", None, "active"
    # سفارش های باز مانده از تست های بالا (همه به یک شماره ۱۰۱ می رسند) این بخش را قاطی نکنند
    await db.execute("UPDATE number_orders SET status = 'refunded' WHERE status = 'active'")
    u = await new_user(db, 500, 200_000)

    async def tap(data: str, fn) -> FakeCall:  # noqa: ANN001
        c = FakeCall(data)
        await fn(c, db, await db.get_user(u["id"]))
        return c

    c = await tap("num", h.cb_hub)
    assert "شماره مجازی" in c.page and "num:s:2:0" in c.buttons and "num:cats" in c.buttons, c.buttons
    c = await tap("num:cats", h.cb_cats)
    assert "num:c:social:0" in c.buttons, c.buttons
    c = await tap("num:c:social:0", h.cb_cat)
    assert "Telegram" in str(c.message.edit_text.call_args) and "num:s:2:0" in c.buttons
    c = await tap("num:s:2:0", h.cb_service)
    assert c.buttons.index("num:b:2:in") < c.buttons.index("num:b:2:us"), c.buttons       # ارزان تر اول
    c = await tap("num:b:2:us", h.cb_confirm)
    assert "49,000" in c.page and "num:go:2:us" in c.buttons
    c = await tap("num:go:2:us", h.cb_buy)
    assert "+15551234567" in c.page and any(b.startswith("num:chk:") for b in c.buttons), c.page
    order = (await db.user_number_orders(u["id"]))[0]
    assert order["chat_id"] == 777 and order["message_id"] == 5      # برای خبر دادن بعدی ذخیره شد
    assert await bal(db, u) == 200_000 - 49_000

    c = await tap(f"num:chk:{order['id']}", h.cb_check)                # هنوز کدی نیامده
    c.answer.assert_awaited()
    assert "+15551234567" in c.page
    c = await tap(f"num:x:{order['id']}", h.cb_cancel_ask)
    assert f"num:xy:{order['id']}" in c.buttons
    srv.sms = "654321"
    c = await tap(f"num:chk:{order['id']}", h.cb_check)                # کد رسید
    assert "654321" in c.page, c.page
    c = await tap("num:mine", h.cb_mine)
    assert "654321" in c.page and "+15551234567" in c.page

    # شماره دیگر: لغو از طریق دکمه
    srv.sms, srv.status = None, "active"
    await tap("num:go:2:us", h.cb_buy)
    o2 = (await db.user_number_orders(u["id"]))[0]
    before = await bal(db, u)
    c = await tap(f"num:xy:{o2['id']}", h.cb_cancel)
    assert await bal(db, u) == before + 49_000 and "برگشت" in c.page

    # سفارش کس دیگر دیده نمی شود
    other = await new_user(db, 501, 0)
    c = FakeCall(f"num:o:{o2['id']}")
    await h.cb_order(c, db, other)
    c.message.edit_text.assert_not_awaited()
    assert c.answer.await_args.kwargs.get("show_alert") is True

    # کد رسیده در پس زمینه: پایشگر خبر می دهد
    srv.sms, srv.status = None, "active"
    await tap("num:go:2:us", h.cb_buy)
    srv.sms = "999000"
    from unittest.mock import AsyncMock

    bot = AsyncMock()
    assert await h.sweep(db, bot) == 1
    sent = bot.send_message.await_args
    assert sent.args[0] == int(u["telegram_id"]) and "999000" in sent.args[1], sent
    assert await h.sweep(db, bot) == 0                                   # دیگر سفارش بازی نیست
    print("OK bot handler flow (hub → service → country → confirm → buy → code → cancel → watcher)")


asyncio.run(main())
