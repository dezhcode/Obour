"""تست آفلاین خدمات تلگرام (MarketApp: پرمیوم و استارز) با سرور شبیه سازی شده.

پاسخ ها همان پاسخ های واقعی تست روی هاست اند (MARKETAPP_FA.md)، از جمله دو تراکنش
خرید واقعی (پرمیوم ۳ ماه و ۵۰ استارز). هیچ درخواستی به marketapp.org نمی رود.
بررسی می شود: قیمت تومانی، بررسی گیرنده و کش، خرید نمایشی (بی کسر پول)، و این که
inspect_tx تراکنش دستکاری شده (مقصد، مبلغ، کامنت) را رد می کند.

    python test_telegram_shop.py
"""
import asyncio
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, ".")

import httpx

from app.db import Database
from app.services import marketapp as mk

RATE = 100_000          # تومان به ازای هر تتر
TOKEN = "808141-0000000000000000000000000000test-1792222408"

# از گزارش واقعی ۲۰۲۶-۱۰-۱۷
PREMIUM_PRICES = {"months3": {"ton": 9.0678, "gram": 9.0678, "usd": 12.229800000000001},
                  "months6": {"ton": 12.097199999999999, "gram": 12.097199999999999, "usd": 16.3098},
                  "months12": {"ton": 21.9402, "gram": 21.9402, "usd": 29.569799999999997}}
PREMIUM3_TX = ("9067800000",
               "te6ccgEBBAEApwABiD8rktKNU5SUERQRoQDa3uHo2Ws6WMnCvKGuSZrlSBSHOXj11eIhaCGcVEJ/9pW44ncL//yM1UwYro8PIB86"
               "AolNA8sMAQFOgAgRtHZRbYDLSyfCByJNN1VTi/GV14GNOz4VV3VlUyStagQjxUUAAgFOAAAAAFRlbGVncmFtIFByZW1pdW0gZm9y"
               "IDMgbW9udGhzIAoKUmVmAwAUI01iSGZwU25FSA==")
STARS50_TX = ("567732000",
              "te6ccgEBAwEAlwABiD8rktKzL50TfLy26RIF1zWXZZBsP7XL4/oZa3mvIcEQyPPwdeiyBMSZDsRN8qRXV+15apEClb8nW9pA/2WQ"
              "sMFwlWEKAQFMgBCkiH8LM/zUu0afyGCTWJwX1mDjdlf2rMa9UoQlD4UHSEJaFYACAEoAAAAANTAgVGVsZWdyYW0gU3RhcnMgCgpS"
              "ZWYjYUpCYnA1YjN5")
FRAGMENT_PREMIUM = "EQBAjaOyi2wGWlk-EDkSabqqnF-MrrwMadnwqrurKpkla9nE"
FRAGMENT_STARS = "EQCFJEP4WZ_mpdo0_kMEmsTgvrMHG7K_tWY16pQhKHwoOoy2"


class FakeServer:
    def __init__(self) -> None:
        self.mode = "ok"          # ok | down | bad_dest | overcharge
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        import json

        path = request.url.path
        self.calls.append(path)
        if request.headers.get("Authorization") != TOKEN:
            return httpx.Response(401, json={"detail": "Invalid or expired token.", "code": "AUTH_04"})
        if self.mode == "down":
            return httpx.Response(502, text="<html>bad gateway</html>")
        body = json.loads(request.content or b"{}")
        if path == "/v1/fragment/premium/price/":
            return httpx.Response(200, json=PREMIUM_PRICES)
        if path == "/v1/fragment/stars/price/":
            q = int(body["quantity"])
            if q == 50:
                return httpx.Response(200, json={"ton": 0.567732, "gram": 0.567732, "usd": 0.765})
            return httpx.Response(200, json={"ton": 0.0113526 * q, "gram": 0.0113526 * q, "usd": 0.0153 * q})
        if path.endswith("/recipient/"):
            if body["username"].lower() in ("sara_m", "ibeni79"):
                return httpx.Response(200, json={"photo": '<img src="https://cdn4.telesco.pe/file/x.jpg" width="40">',
                                                 "name": "Sara"})
            return httpx.Response(400, json={"detail": "User not found."})
        if path.endswith("/buy/"):
            if path.startswith("/v1/fragment/premium/"):
                if body["months"] not in (3, 6, 12):
                    return httpx.Response(400, json={"detail": "invalid months"})
                amount, payload = PREMIUM3_TX       # همیشه سفارش ۳ ماه؛ برای تست کامنت نخواندن
            else:
                if not 50 <= body["quantity"] <= 1_000_000:
                    return httpx.Response(400, json={"detail": "50 - 1,000,000"})
                amount, payload = STARS50_TX
            to = mk.MARKETAPP_CONTRACT
            if self.mode == "bad_dest":
                to = FRAGMENT_PREMIUM
            if self.mode == "overcharge":
                amount = str(int(int(amount) * 1.2))
            return httpx.Response(200, json={"transaction": {"validUntil": int(time.time()) + 120, "messages": [
                {"address": to, "amount": amount, "payload": payload, "stateInit": None}]}})
        return httpx.Response(404, json={"detail": "not found"})


def check(cond: bool, what: str) -> None:
    if not cond:
        raise AssertionError(what)


async def run(db: Database) -> None:
    srv = FakeServer()
    mk.TRANSPORT = httpx.MockTransport(srv.handler)
    u = await db.get_or_create_user(555, "u555", "User555")
    await db.atomic_credit(u["id"], 250_000)
    u = await db.get_user(u["id"])

    # بدون توکن: راه اندازی نشده و هیچ درخواستی نمی رود
    r = await mk.buy(db, u, mk.PREMIUM, "sara_m", 3)
    check(r == {"ok": False, "error": mk.NOT_CONFIGURED, "message": mk.MESSAGES[mk.NOT_CONFIGURED]}, f"no token: {r}")
    check(not srv.calls, "no token → no API call")
    await db.set_setting(mk.KEY_SETTING, TOKEN)
    check(not await mk.ready(db), "no usdt rate → not ready")
    await db.set_setting("ai_usdt_rate", str(RATE))
    check(await mk.ready(db), "token + rate → ready")
    check(await mk.mode(db) == mk.DEMO, "live not available → demo")
    await db.set_setting(mk.MODE_SETTING, mk.LIVE)
    check(await mk.mode(db) == mk.DEMO, "live setting ignored while LIVE_AVAILABLE is off")
    print("OK settings: token, rate, demo mode")

    # قیمت تومانی: دلار × نرخ تتر + ٪۱۵ (کف ۱۰٬۰۰۰)، رند رو به بالا به هزار
    cat = await mk.catalog(db)
    p3 = next(p for p in cat["premium"] if p["months"] == 3)
    check(p3["price"] == 1_407_000, f"premium 3: {p3}")
    check(cat["best"] == 12, f"best value: {cat['best']}")
    pack50 = next(p for p in cat["packs"] if p["qty"] == 50)
    check(pack50["price"] == 88_000, f"50 stars pack: {pack50}")     # 0.765×100000=76500 → +15% = 87975 → 88000
    n = len(srv.calls)
    await mk.catalog(db)
    check(len(srv.calls) == n, "catalog cached")
    await db.set_setting("tgs_profit_percent", "20")
    check(next(p for p in (await mk.catalog(db))["premium"] if p["months"] == 3)["price"] == 1_468_000,
          "profit change applies without refetch")
    await db.set_setting("tgs_profit_percent", "15")
    print("OK prices: toman from USD, 15% / min profit / round, cache")

    # گیرنده
    r = await mk.recipient(db, mk.PREMIUM, "@Sara_M")
    check(r["ok"] and r["username"] == "Sara_M" and r["name"] == "Sara"
          and r["photo"] == "https://cdn4.telesco.pe/file/x.jpg", f"recipient: {r}")
    n = len(srv.calls)
    await mk.recipient(db, mk.PREMIUM, "https://t.me/sara_m")
    check(len(srv.calls) == n, "recipient cached (case-insensitive)")
    r = await mk.recipient(db, mk.STARS, "nobody_here")
    check(not r["ok"] and r["error"] == mk.NOT_FOUND, f"not found: {r}")
    n = len(srv.calls)
    r = await mk.recipient(db, mk.STARS, "a b")
    check(not r["ok"] and r["error"] == mk.BAD_USERNAME and len(srv.calls) == n, "bad username, no call")
    print("OK recipient: found + photo, cache, not found, bad username")

    # خرید نمایشی پرمیوم ۳ ماه: تراکنش واقعی بررسی می شود و پولی کم نمی شود
    r = await mk.buy(db, u, mk.PREMIUM, "@sara_m", 3)
    check(r["ok"] and r["demo"], f"demo premium: {r}")
    c = r["check"]
    check(c["ok"] and not c["problems"], f"check ok: {c}")
    check(c["fragment"] == FRAGMENT_PREMIUM and c["ref"] == "MbHfpSnEH" and abs(c["fee_pct"] - 1.96) < 0.01, f"decoded: {c}")
    check(c["comment"].startswith("Telegram Premium for 3 months"), c["comment"])
    o = r["order"]
    check(o["mode"] == "demo" and o["status"] == "demo" and o["price"] == 1_407_000 and o["code"].startswith("TG-"),
          f"order: {o}")
    check((await db.get_user(u["id"]))["balance"] == 250_000, "demo never charges")
    check(await db.acquire_lock(f"tgbuy:{u['id']}", 5), "lock released")
    await db.release_lock(f"tgbuy:{u['id']}")
    r = await mk.buy(db, u, mk.STARS, "sara_m", 50)
    check(r["ok"] and r["check"]["ok"] and r["check"]["fragment"] == FRAGMENT_STARS and r["check"]["ref"] == "aJBbp5b3y",
          f"demo stars: {r.get('check')}")
    print("OK demo buy: real premium/stars tx inspected, order saved, balance untouched")

    # تراکنش مشکوک رد می شود
    r = await mk.buy(db, u, mk.PREMIUM, "sara_m", 6)        # سرور سفارش ۳ ماه می دهد
    check(r["ok"] and not r["check"]["ok"] and "کامنت با محصول نمی خواند" in r["check"]["problems"], f"comment: {r['check']}")
    srv.mode = "bad_dest"
    r = await mk.buy(db, u, mk.PREMIUM, "sara_m", 3)
    check(not r["check"]["ok"] and "مقصد قرارداد MarketApp نیست" in r["check"]["problems"], f"dest: {r['check']}")
    srv.mode = "overcharge"
    r = await mk.buy(db, u, mk.PREMIUM, "sara_m", 3)
    check(not r["check"]["ok"] and any(p.startswith("مبلغ") for p in r["check"]["problems"]), f"amount: {r['check']}")
    srv.mode = "ok"
    print("OK inspect_tx rejects wrong comment, destination and overcharge")

    # ورودی نامعتبر، قفل، سرویس دهنده خوابیده
    n = len(srv.calls)
    check((await mk.buy(db, u, mk.PREMIUM, "sara_m", 5))["error"] == mk.BAD_AMOUNT, "5 months")
    check((await mk.buy(db, u, mk.STARS, "sara_m", 10))["error"] == mk.BAD_AMOUNT, "10 stars")
    check((await mk.buy(db, u, mk.STARS, "a", 50))["error"] == mk.BAD_USERNAME, "bad username")
    check(len(srv.calls) == n, "invalid input → no API call")
    r = await mk.buy(db, u, mk.PREMIUM, "nobody_here", 3)
    check(r["error"] == mk.NOT_FOUND, f"recipient not found blocks buy: {r}")
    await db.acquire_lock(f"tgbuy:{u['id']}", 30)
    check((await mk.buy(db, u, mk.PREMIUM, "sara_m", 3))["error"] == mk.LOCKED, "locked")
    await db.release_lock(f"tgbuy:{u['id']}")
    srv.mode = "down"
    mk._catalog.update(at=0.0, data=None)
    try:
        await mk.catalog(db)
        check(False, "catalog should fail when provider is down")
    except mk.MarketAppError as exc:
        check(exc.code == "down" and exc.status == 502, f"down: {exc.code} {exc.status}")
    check((await mk.buy(db, u, mk.PREMIUM, "sara_m", 3))["error"] == mk.PROVIDER, "provider down → provider error")
    srv.mode = "ok"
    print("OK bad amount/username, lock, provider down")

    orders = await db.user_tg_orders(u["id"])
    check(len(orders) == 5 and all(x["mode"] == "demo" for x in orders), f"orders: {len(orders)}")
    check(await db.user_tg_recipients(u["id"]) == ["sara_m"], "recent recipients deduplicated")
    st = await db.tg_stats()
    check(st["total"] == 5 and st["demo"] == 5 and st["revenue"] == 0, f"stats: {st}")
    check((await db.get_user(u["id"]))["balance"] == 250_000, "balance never changed")
    print("OK orders, recent recipients, stats")


async def run_bot(db: Database) -> None:
    """گفتگوی ربات با Dispatcher واقعی aiogram؛ پیام های خروجی ضبط می شوند و به تلگرام نمی روند."""
    from datetime import datetime

    from aiogram import Bot, Dispatcher
    from aiogram.client.session.base import BaseSession
    from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
    from aiogram.types import CallbackQuery, Chat, Message, Update, User

    from app import keyboards
    from app.handlers import telegram_shop

    class Capture(BaseSession):
        def __init__(self) -> None:
            super().__init__()
            self.out: list = []

        async def make_request(self, bot, method, timeout=None):  # noqa: ANN001, ANN201
            self.out.append(method)
            if isinstance(method, (SendMessage, EditMessageText)):
                return Message(message_id=len(self.out) + 100, date=datetime.now(), text=method.text,
                               chat=Chat(id=555, type="private"), reply_markup=method.reply_markup)
            return True

        async def stream_content(self, *a, **k):  # noqa: ANN002, ANN003, ANN201
            raise NotImplementedError

        async def close(self) -> None:
            pass

    sess = Capture()
    bot = Bot("42:TEST", session=sess)
    dp = Dispatcher()
    dp.include_router(telegram_shop.router)
    me = User(id=555, is_bot=False, first_name="U", username="sara_m")
    chat = Chat(id=555, type="private")
    seq = iter(range(1, 10_000))

    async def user():  # noqa: ANN202
        return await db.get_user((await db.get_or_create_user(555, "sara_m", "User555"))["id"])

    async def tap(data: str) -> list:
        n = len(sess.out)
        msg = Message(message_id=10, date=datetime.now(), chat=chat, text="…",
                      from_user=User(id=42, is_bot=True, first_name="bot"))
        upd = Update(update_id=next(seq), callback_query=CallbackQuery(
            id=str(next(seq)), from_user=me, chat_instance="c", message=msg, data=data))
        upd = Update.model_validate(upd.model_dump(), context={"bot": bot})
        await dp.feed_update(bot, upd, db=db, user=await user())
        return sess.out[n:]

    async def say(text: str) -> list:
        n = len(sess.out)
        upd = Update(update_id=next(seq), message=Message(message_id=next(seq), date=datetime.now(), chat=chat,
                                                          from_user=me, text=text))
        upd = Update.model_validate(upd.model_dump(), context={"bot": bot})
        await dp.feed_update(bot, upd, db=db, user=await user())
        return sess.out[n:]

    def texts_of(out: list) -> str:
        return "\n".join(m.text for m in out if isinstance(m, (SendMessage, EditMessageText)))

    def buttons(out: list) -> list[tuple[str, str]]:
        rows = []
        for m in out:
            mk_ = getattr(m, "reply_markup", None)
            for row in (mk_.inline_keyboard if mk_ else []):
                rows += [(b.text, b.callback_data) for b in row]
        return rows

    before = (await user())["balance"]
    out = await tap("tg")
    check("نمایشی" in texts_of(out) and ("⭐ تلگرام پرمیوم", "tg:k:premium") in buttons(out), "hub")
    out = await tap("tg:k:premium")
    check(("👤 برای خودم · @sara_m", "tg:r:premium:sara_m") in buttons(out), f"recipient kb: {buttons(out)}")
    out = await say("@nobody_here")
    check("پیدا نشد" in texts_of(out), f"not found: {texts_of(out)}")
    out = await say("@sara_m")
    check("1,407,000" in texts_of(out) and ("3 ماه · 1,407,000", "tg:p:3") in buttons(out), f"plans: {buttons(out)}")
    out = await tap("tg:p:3")
    check("نمایشی" in texts_of(out) and any(cb == "tg:ok" and "نمایشی" in t for t, cb in buttons(out)), "confirm")
    out = await tap("tg:ok")
    txt = texts_of(out)
    check("سفارش نمایشی ثبت شد" in txt and "TG-" in txt and "هیچ پولی" in txt, f"done: {txt}")
    out = await tap("tg:k:stars")
    out = await tap("tg:r:stars:sara_m")
    check(("⭐ 50 · 88,000", "tg:s:50") in buttons(out), f"packs: {buttons(out)}")
    out = await tap("tg:sc")
    out = await say("۷۵۰")                       # عدد فارسی
    check("750 استارز" in texts_of(out), f"custom qty confirm: {texts_of(out)}")
    out = await say("۱۰")                        # حالت تمام شد؛ پیام بی اثر
    check(not out, "no state after confirm")
    out = await tap("tg:ok")
    check("750 استارز" in texts_of(out) and "سفارش نمایشی ثبت شد" in texts_of(out), "stars done")
    out = await tap("tg:mine")
    check(texts_of(out).count("🧪 نمایشی") >= 2, f"my orders: {texts_of(out)}")
    out = await tap("tg:k:premium")
    out = await say("سلام، یه سوال داشتم")      # از منو رفته و حالا چیز دیگری می نویسد
    check(not out, "unrelated text falls through to other handlers")
    out = await say("@sara_m")
    check(not out, "stale recipient state cleared")
    check((await user())["balance"] == before, "bot demo never charges")
    check(any(cb == "tg" for _, cb in buttons([type("M", (), {"reply_markup": keyboards.shop_hub_kb([], telegram=True)})()])),
          "shop hub has Telegram button")
    await bot.session.close()
    print("OK bot flow: hub, recipient (bad/good), premium confirm, demo order, custom stars, my orders")


async def run_api(db: Database) -> None:
    """اندپوینت های مینی اپ: ویترین، گیرنده، قیمت، سفارش (nonce و قوانین)."""
    from app.webapp import api as webapi
    from app.webapp.auth import WebAppUser

    wu = WebAppUser(id=777, first_name="W", username="Sara_M", language_code="fa", is_premium=False, start_param="")
    u = await db.get_or_create_user(777, "Sara_M", "W")
    before = (await db.get_user(u["id"]))["balance"]
    d = await webapi.tg_info(db, None, wu)
    check(d["ready"] and d["demo"] and d["me"] == "Sara_M" and len(d["premium"]) == 3 and len(d["packs"]) == 6,
          f"tg_info: {d}")
    check(d["best"] == 12 and d["per_star"] > 0 and not d["down"], "tg_info prices")
    r = await webapi.tg_recipient(db, None, wu, kind="stars", username="@sara_m")
    check(r["ok"] and r["name"] == "Sara", f"tg_recipient: {r}")
    q = await webapi.tg_quote(db, None, wu, kind="premium", amount="3")
    check(q["price"] == 1_407_000, f"tg_quote: {q}")
    for kind, n in (("premium", "5"), ("stars", "10"), ("gift", "3")):
        try:
            await webapi.tg_quote(db, None, wu, kind=kind, amount=n)
            check(False, f"quote {kind} {n} should fail")
        except webapi.ApiError as exc:
            check(exc.status == 400, f"quote error status {exc.status}")
    try:
        await webapi.tg_buy(db, None, wu, kind="premium", amount="3", username="sara_m", nonce="n-00000001")
        check(False, "rules not accepted should block")
    except webapi.ApiError as exc:
        check(exc.code == "rules", f"rules gate: {exc.code}")
    await db.set_setting("rules_enabled", "0")
    x = await webapi.tg_buy(db, None, wu, kind="premium", amount="3", username="sara_m", nonce="n-00000002")
    check(x["demo"] and x["order"]["mode"] == "demo" and x["order"]["title"] == "پرمیوم 3 ماهه", f"tg_buy: {x}")
    try:
        await webapi.tg_buy(db, None, wu, kind="premium", amount="3", username="sara_m", nonce="n-00000002")
        check(False, "same nonce twice should be rejected")
    except webapi.ApiError as exc:
        check(exc.status == 409 and exc.code == "duplicate", f"nonce: {exc.status} {exc.code}")
    try:
        await webapi.tg_buy(db, None, wu, kind="premium", amount="3", username="nobody_here", nonce="n-00000003")
        check(False, "unknown recipient should fail")
    except webapi.ApiError as exc:
        check(exc.status == 400 and exc.code == mk.NOT_FOUND, f"recipient error: {exc.status} {exc.code}")
    d = await webapi.tg_info(db, None, wu)
    check(len(d["orders"]) == 1 and d["recents"] == ["sara_m"], f"orders/recents: {d['orders']} {d['recents']}")
    check((await db.get_user(u["id"]))["balance"] == before, "api demo never charges")
    from app import features
    await features.set_on(db, "shop_telegram", False)
    try:
        await webapi.tg_quote(db, None, wu, kind="premium", amount="3")
        check(False, "feature off should block")
    except webapi.ApiError as exc:
        check(exc.status == 403, f"feature off: {exc.status}")
    check(not (await webapi.tg_info(db, None, wu))["ready"], "feature off → not ready")
    await features.set_on(db, "shop_telegram", True)
    print("OK mini app API: info, recipient, quote errors, rules gate, nonce, feature toggle")


async def main() -> None:
    os.environ.pop("MARKETAPP_TOKEN", None)
    tmp = tempfile.mkdtemp()
    db = Database(os.path.join(tmp, "t.db"))
    await db.connect()
    try:
        await run(db)
        await run_bot(db)
        await run_api(db)
    finally:
        await db.close()
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nهمه تست های خدمات تلگرام گذشت ✅")


asyncio.run(main())
