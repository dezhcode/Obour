"""خدمات تلگرام از MarketApp: پرمیوم و استارز تلگرام. مرجع: MARKETAPP_FA.md

همه چیز از همان API واقعی که با توکن روی هاست تست شد:

    قیمت ها      POST /v1/fragment/premium/price/ و /v1/fragment/stars/price/
    گیرنده       POST /v1/fragment/{premium|stars}/recipient/   ← {"name", "photo"}
    خرید         POST /v1/fragment/{premium|stars}/buy/          ← تراکنش آماده (امضا نشده)

endpoint خرید پولی برنمی دارد؛ فقط تراکنش TON آماده می دهد که کیف پول ما باید امضا
و ارسال کند. پیش از امضا همیشه inspect_tx همان بررسی های MARKETAPP_FA.md را اجرا
می کند (یک پیام، مقصد قرارداد MarketApp، op سفارش، کامنت همان محصول، مبلغ ≤ قیمت).

حالت فروش (MODE_SETTING):
    demo  همه مسیر واقعی است (قیمت زنده، بررسی گیرنده، ساخت و بررسی تراکنش خرید)
          جز امضا و ارسال؛ هیچ پولی از کیف پول کاربر کم نمی شود و به کاربر گفته می شود.
    live  فروش واقعی. تا امضای کیف پول خرید (Ed25519 و کیف پول V5R1/V4R2) اضافه نشده،
          LIVE_AVAILABLE خاموش است و حالت همیشه demo می ماند.

قیمت تومانی = قیمت دلاری MarketApp × نرخ تتر عبور + سود (درصد، با کف سود)، رو به بالا
رند. قیمت دلاری همان مبلغ USDT است که MarketApp در پرداخت تتری می گیرد.

پایین فایل: تست کامل API برای پنل ادمین (فایل گزارش در چت ادمین).
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from app import pricing
from app.config import config
from app.utils import esc

if TYPE_CHECKING:
    from aiogram import Bot

    from app.db import Database

log = logging.getLogger("obour.marketapp")

KEY_SETTING = "marketapp_token"
USER_SETTING = "marketapp_test_user"
CHANNEL_SETTING = "marketapp_test_channel"
MODE_SETTING = "tgs_mode"

DEMO, LIVE = "demo", "live"
# امضا و ارسال تراکنش با کیف پول خرید هنوز پیاده نشده؛ تا آن وقت فروش فقط نمایشی است
LIVE_AVAILABLE = False

PREMIUM, STARS = "premium", "stars"
KINDS = (PREMIUM, STARS)
PREMIUM_MONTHS = (3, 6, 12)
STARS_MIN, STARS_MAX = 50, 1_000_000
STAR_PACKS = (50, 100, 250, 500, 1000, 2500)

# از تست واقعی (MARKETAPP_FA.md): هر سفارش TON یک پیام به این قرارداد است
MARKETAPP_CONTRACT = "EQCpwa0v6lvGA01uKGfsW1CK1Nd59aO_xVFGGHPy7JTghHTB"
OP_MARKETAPP_ORDER = 0x3F2B92D2
OP_JETTON_TRANSFER = 0x0F8A7EA5
TX_TOLERANCE = 0.01          # مبلغ تراکنش حداکثر ٪۱ بیشتر از قیمتی که همان لحظه گرفتیم
NANO = 1_000_000_000

USERNAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,31}")
CHECK_BUDGET = 150          # ثانیه؛ بعدش درخواست های باقی مانده تست ادمین رد می شوند
CATALOG_TTL = 180           # ثانیه
RECIPIENT_TTL = 600

# تنظیمات قیمت (ادمین از پنل عوض می کند). نرخ تتر همان نرخ مشترک عبور است.
FIELDS: dict[str, tuple[str, str, str]] = {
    "tgs_profit_percent": ("درصد سود", "15", "سود روی قیمت دلاری MarketApp؛ مثلا 15"),
    "tgs_min_profit": ("حداقل سود (تومان)", "10000", "کف سود هر سفارش"),
    "tgs_round_to": ("رند کردن به (تومان)", "1000", "قیمت نهایی رو به بالا رند می شود"),
}

# نتیجه ها (کد خطا ← پیام فارسی برای کاربر)
NOT_CONFIGURED = "not_configured"
BAD_USERNAME = "bad_username"
NOT_FOUND = "not_found"
BAD_AMOUNT = "bad_amount"
LOCKED = "locked"
PROVIDER = "provider"
CHECK_FAILED = "check_failed"
MESSAGES = {
    NOT_CONFIGURED: "این بخش هنوز راه‌اندازی نشده.",
    BAD_USERNAME: "یوزرنیم درست نیست؛ مثل @name (۵ تا ۳۲ حرف انگلیسی، عدد یا _).",
    NOT_FOUND: "این یوزرنیم توی تلگرام پیدا نشد. املاش رو چک کن؛ اگه گیرنده یوزرنیم نداره، اول باید یکی بسازه.",
    BAD_AMOUNT: "تعداد استارز باید بین ۵۰ تا ۱٬۰۰۰٬۰۰۰ باشه.",
    LOCKED: "یه سفارش دیگه‌ات در حال انجامه؛ چند ثانیه صبر کن.",
    PROVIDER: "سرویس‌دهنده الان جواب نمی‌ده؛ کمی بعد دوباره امتحان کن.",
    CHECK_FAILED: "سفارش ساخته شد ولی بررسی امنیتی‌اش رد شد؛ خرید انجام نمی‌شه.",
}

_check: asyncio.Task | None = None
_catalog: dict[str, Any] = {"at": 0.0, "data": None}
_recipients: dict[tuple[str, str], tuple[float, dict]] = {}
# برای تست: یک httpx.MockTransport به جای شبکه
TRANSPORT: httpx.AsyncBaseTransport | None = None


# ═══════════════════ تنظیمات ═══════════════════


async def token(db: "Database") -> str:
    return config.marketapp_token or (await db.get_setting(KEY_SETTING, "") or "").strip()


def valid_token(raw: str) -> bool:
    return 16 <= len(raw) <= 300 and not re.search(r"\s", raw)


def clean_username(raw: str) -> str | None:
    """«@name» یا «t.me/name» یا «name» ← name؛ نامعتبر ← None."""
    s = (raw or "").strip().removeprefix("https://").removeprefix("http://").removeprefix("t.me/").lstrip("@")
    return s if USERNAME_RE.fullmatch(s) else None


async def load_cfg(db: "Database") -> dict[str, float]:
    out: dict[str, float] = {}
    for key, (_title, default, _desc) in FIELDS.items():
        raw = await db.get_setting(key, default)
        try:
            out[key] = float(str(raw).replace(",", "") or default)
        except (TypeError, ValueError):
            out[key] = float(default)
    return out


async def usdt_rate(db: "Database") -> float:
    return pricing.rate_for(await pricing.load(db), "USDT")


async def ready(db: "Database") -> bool:
    """فروش (حتی نمایشی) وقتی ممکن است که توکن و نرخ تتر تنظیم باشند."""
    return bool(await token(db)) and await usdt_rate(db) > 0


async def mode(db: "Database") -> str:
    if LIVE_AVAILABLE and await db.get_setting(MODE_SETTING, DEMO) == LIVE:
        return LIVE
    return DEMO


def price_toman(usd: float, rate: float, cfg: dict[str, float]) -> int:
    """قیمت کاربر: قیمت دلاری × نرخ تتر + سود (درصد، با کف سود)، رند رو به بالا."""
    base = usd * rate
    total = max(base * (1 + cfg.get("tgs_profit_percent", 0) / 100), base + cfg.get("tgs_min_profit", 0))
    step = int(cfg.get("tgs_round_to") or 1) or 1
    return int(math.ceil(total / step) * step)


# ═══════════════════ کلاینت API ═══════════════════


class MarketAppError(Exception):
    """code: not_found | bad_input | auth | plan | busy | down."""

    def __init__(self, message: str, status: int = 0, code: str = "down") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class Client:
    def __init__(self, tok: str) -> None:
        proxy = config.marketapp_proxy
        kw: dict[str, Any] = {"proxy": proxy} if proxy.startswith(("http", "socks")) else {}
        if TRANSPORT is not None:
            kw = {"transport": TRANSPORT}
        self.http = httpx.AsyncClient(
            base_url=config.marketapp_base_url or "https://api.marketapp.org",
            timeout=20,
            headers={"Authorization": tok, "Accept": "application/json",
                     "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) obour/1.0"},
            **kw,
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def _post(self, path: str, body: dict | None = None) -> Any:
        try:
            resp = await self.http.post(path, json=body)
        except httpx.HTTPError as exc:
            raise MarketAppError(f"{type(exc).__name__}: {exc}", 0, "down") from exc
        try:
            data = resp.json()
        except ValueError:
            data = None
        if resp.status_code >= 400:
            detail = str((data or {}).get("detail") if isinstance(data, dict) else resp.text[:200])
            code = {401: "auth", 402: "plan", 429: "busy"}.get(resp.status_code)
            if resp.status_code == 400:
                code = "not_found" if "not found" in detail.lower() else "bad_input"
            raise MarketAppError(detail, resp.status_code, code or "down")
        if not isinstance(data, dict):
            raise MarketAppError("جواب نامعتبر", resp.status_code, "down")
        return data

    async def premium_prices(self) -> dict[int, dict]:
        data = await self._post("/v1/fragment/premium/price/")
        return {m: data.get(f"months{m}") or {} for m in PREMIUM_MONTHS}

    async def stars_price(self, qty: int) -> dict:
        return await self._post("/v1/fragment/stars/price/", {"quantity": int(qty)})

    async def recipient(self, kind: str, username: str) -> dict:
        return await self._post(f"/v1/fragment/{kind}/recipient/", {"username": username})

    async def buy_tx(self, kind: str, username: str, amount: int, currency: str = "TON") -> dict:
        if kind == PREMIUM:
            body = {"username": username, "months": int(amount), "currency": currency}
        else:
            body = {"username": username, "quantity": int(amount), "currency": currency}
        data = await self._post(f"/v1/fragment/{kind}/buy/", body)
        tx = data.get("transaction")
        if not isinstance(tx, dict) or not tx.get("messages"):
            raise MarketAppError("تراکنش در جواب نبود", 200, "down")
        return tx


async def client(db: "Database") -> Client:
    return Client(await token(db))


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _photo(raw: Any) -> str:
    """جواب گیرنده عکس را به شکل تگ <img src="..."> می دهد؛ فقط لینک https بیرون کشیده می شود."""
    s = str(raw or "")
    m = re.search(r'src=["\'](https://[^"\']+)["\']', s)
    return m.group(1) if m else (s if s.startswith("https://") else "")


# ═══════════════════ قیمت ها ═══════════════════


async def _raw_prices(db: "Database", force: bool = False) -> dict:
    """قیمت دلاری و TON پرمیوم و هر استار؛ CATALOG_TTL ثانیه کش می شود."""
    if not force and _catalog["data"] and time.monotonic() - _catalog["at"] < CATALOG_TTL:
        return _catalog["data"]
    cli = await client(db)
    try:
        prem = await cli.premium_prices()
        st = await cli.stars_price(1000)
    finally:
        await cli.close()
    data = {
        "premium": {m: {"usd": _num(p.get("usd")), "ton": _num(p.get("ton") or p.get("gram"))} for m, p in prem.items()},
        "star_usd": _num(st.get("usd")) / 1000,
        "star_ton": _num(st.get("ton") or st.get("gram")) / 1000,
    }
    if not all(v["usd"] > 0 for v in data["premium"].values()) or data["star_usd"] <= 0:
        raise MarketAppError("قیمت دلاری در جواب نبود", 200, "down")
    _catalog.update(at=time.monotonic(), data=data)
    return data


async def catalog(db: "Database", force: bool = False) -> dict:
    """ویترین: پلن های پرمیوم و بسته های استارز با قیمت تومانی (MarketAppError اگر API جواب ندهد)."""
    raw = await _raw_prices(db, force)
    rate, cfg = await usdt_rate(db), await load_cfg(db)
    premium = []
    for m in PREMIUM_MONTHS:
        p = raw["premium"][m]
        price = price_toman(p["usd"], rate, cfg)
        premium.append({"months": m, "usd": p["usd"], "ton": p["ton"], "price": price, "per_month": price // m})
    packs = [{"qty": q, "price": price_toman(raw["star_usd"] * q, rate, cfg)} for q in STAR_PACKS]
    per_star = price_toman(raw["star_usd"] * 1000, rate, cfg) / 1000
    best = min(premium, key=lambda x: x["per_month"])["months"]
    return {"premium": premium, "best": best, "packs": packs, "per_star": per_star,
            "min": STARS_MIN, "max": STARS_MAX, "rate": rate}


def valid_amount(kind: str, amount: Any) -> int | None:
    try:
        n = int(amount)
    except (TypeError, ValueError):
        return None
    if kind == PREMIUM:
        return n if n in PREMIUM_MONTHS else None
    if kind == STARS:
        return n if STARS_MIN <= n <= STARS_MAX else None
    return None


async def quote(db: "Database", kind: str, amount: int) -> dict:
    """قیمت دقیق همین لحظه (بدون کش): {usd, ton, price}."""
    cli = await client(db)
    try:
        if kind == PREMIUM:
            p = (await cli.premium_prices())[amount]
        else:
            p = await cli.stars_price(amount)
    finally:
        await cli.close()
    usd, ton = _num(p.get("usd")), _num(p.get("ton") or p.get("gram"))
    if usd <= 0:
        raise MarketAppError("قیمت دلاری در جواب نبود", 200, "down")
    return {"usd": usd, "ton": ton, "price": price_toman(usd, await usdt_rate(db), await load_cfg(db))}


# ═══════════════════ گیرنده ═══════════════════


async def recipient(db: "Database", kind: str, raw_username: str) -> dict:
    """بررسی گیرنده با API: {ok, username, name, photo} یا {ok: False, error, message}."""
    username = clean_username(raw_username)
    if not username:
        return {"ok": False, "error": BAD_USERNAME, "message": MESSAGES[BAD_USERNAME]}
    kind = kind if kind in KINDS else PREMIUM
    key = (kind, username.lower())
    hit = _recipients.get(key)
    if hit and time.monotonic() - hit[0] < RECIPIENT_TTL:
        return {**hit[1], "username": username} if hit[1]["ok"] else hit[1]
    cli = await client(db)
    try:
        data = await cli.recipient(kind, username)
        out = {"ok": True, "username": username, "name": str(data.get("name") or username)[:64],
               "photo": _photo(data.get("photo"))}
    except MarketAppError as exc:
        if exc.code == "not_found":
            out = {"ok": False, "error": NOT_FOUND, "message": MESSAGES[NOT_FOUND]}
        elif exc.code == "bad_input":
            # مثلا گیرنده ای که از قبل پرمیوم دارد؛ متن خود MarketApp
            return {"ok": False, "error": "rejected", "message": str(exc)[:200]}
        else:
            log.warning("بررسی گیرنده MarketApp نشد: %s", exc)
            return {"ok": False, "error": PROVIDER, "message": MESSAGES[PROVIDER]}
    finally:
        await cli.close()
    _recipients[key] = (time.monotonic() if out["ok"] else time.monotonic() - RECIPIENT_TTL + 60, out)
    return out


# ═══════════════════ بررسی تراکنش پیش از امضا ═══════════════════


def _cell_comments(cell: Any) -> list[str]:
    from app.ton import read_comment

    out = [t] if (t := read_comment(cell)) is not None else []
    for r in cell.refs:
        out += _cell_comments(r)
    return out


def _expected_ok(kind: str, amount: int, comment: str) -> bool:
    if kind == PREMIUM:
        m = re.search(r"Telegram Premium for (\d+) month", comment)
        return bool(m) and int(m.group(1)) == amount
    m = re.match(r"\s*([\d,\s]+?)\s*Telegram Stars", comment)
    return bool(m) and int(re.sub(r"\D", "", m.group(1)) or 0) == amount


def inspect_tx(tx: dict, kind: str, amount: int, quote_ton: float) -> dict:
    """بررسی های MARKETAPP_FA.md روی تراکنش خرید، پیش از هر امضا.

    {ok, problems, to, ton, fragment, forward_ton, fee_pct, comment, ref, valid_in}
    """
    from app.ton import Cell, TonError, same_address

    out: dict[str, Any] = {"ok": False, "problems": [], "to": "", "ton": 0.0, "fragment": "", "forward_ton": 0.0,
                           "fee_pct": 0.0, "comment": "", "ref": "", "valid_in": 0}
    msgs = tx.get("messages") or []
    out["valid_in"] = int(_num(tx.get("validUntil")) - time.time())
    if out["valid_in"] <= 0:
        out["problems"].append("validUntil گذشته")
    if len(msgs) != 1:
        out["problems"].append(f"{len(msgs)} پیام به جای یکی")
    if not msgs:
        return out
    m = msgs[0]
    out["to"] = str(m.get("address") or "")
    nano = int(_num(m.get("amount")))
    out["ton"] = nano / NANO
    if not same_address(out["to"], MARKETAPP_CONTRACT):
        out["problems"].append("مقصد قرارداد MarketApp نیست")
    if quote_ton > 0 and out["ton"] > quote_ton * (1 + TX_TOLERANCE) + 1e-9:
        out["problems"].append(f"مبلغ {out['ton']:g} بیشتر از قیمت {quote_ton:g}")
    try:
        cell = Cell.from_boc(str(m.get("payload") or "").strip().replace("-", "+").replace("_", "/"))
        if len(cell.bits) < 32 or int(cell.bits[:32], 2) != OP_MARKETAPP_ORDER or not cell.refs:
            out["problems"].append("op سفارش MarketApp نیست")
        else:
            s = cell.refs[0].slice()
            dst, fwd = s.address(), s.coins()
            out["fragment"] = dst.friendly(bounceable=True) if dst else ""
            out["forward_ton"] = fwd / NANO
            out["fee_pct"] = round((nano - fwd) / nano * 100, 2) if nano else 0.0
        comments = _cell_comments(cell)
        out["comment"] = comments[0] if comments else ""
        ref = re.search(r"Ref#(\w+)", out["comment"])
        out["ref"] = ref.group(1) if ref else ""
        if not _expected_ok(kind, amount, out["comment"]):
            out["problems"].append("کامنت با محصول نمی خواند")
    except (TonError, IndexError, ValueError) as exc:
        out["problems"].append(f"payload خوانده نشد: {exc}")
    out["ok"] = not out["problems"]
    return out


# ═══════════════════ خرید ═══════════════════


def order_title(o: dict) -> str:
    return f"پرمیوم {o['amount']} ماهه" if o["kind"] == PREMIUM else f"{int(o['amount']):,} استارز"


def order_out(o: dict) -> dict:
    return {"id": o["id"], "code": o["code"], "kind": o["kind"], "amount": o["amount"], "title": order_title(o),
            "recipient": o["recipient"], "recipient_name": o.get("recipient_name") or "", "price": o["price"],
            "mode": o["mode"], "status": o["status"], "created_at": o["created_at"]}


def _fail(code: str, message: str | None = None) -> dict:
    return {"ok": False, "error": code, "message": message or MESSAGES.get(code, MESSAGES[PROVIDER])}


async def buy(db: "Database", user: dict, kind: str, raw_username: str, amount: Any) -> dict:
    """سفارش پرمیوم یا استارز از ربات و مینی اپ.

    حالت نمایشی: گیرنده، قیمت دقیق همین لحظه و خود تراکنش خرید از MarketApp واقعی
    است و inspect_tx رویش اجرا می شود؛ فقط امضا و ارسال انجام نمی شود و هیچ پولی از
    کیف پول کاربر کم نمی شود. سفارش با mode=demo ثبت می شود.
    """
    if kind not in KINDS:
        return _fail(BAD_AMOUNT)
    n = valid_amount(kind, amount)
    if n is None:
        return _fail(BAD_AMOUNT)
    username = clean_username(raw_username)
    if not username:
        return _fail(BAD_USERNAME)
    if not await ready(db):
        return _fail(NOT_CONFIGURED)
    lock = f"tgbuy:{user['id']}"
    if not await db.acquire_lock(lock, ttl_seconds=60):
        return _fail(LOCKED)
    try:
        rcp = await recipient(db, kind, username)
        if not rcp["ok"]:
            return _fail(rcp["error"], rcp["message"])
        try:
            q = await quote(db, kind, n)
        except MarketAppError as exc:
            log.warning("قیمت MarketApp خوانده نشد: %s", exc)
            return _fail(PROVIDER)
        current = await mode(db)
        if current == LIVE:     # تا LIVE_AVAILABLE روشن نشده، اینجا نمی رسیم
            return _fail(PROVIDER, "فروش واقعی هنوز فعال نیست.")
        cli = await client(db)
        try:
            tx = await cli.buy_tx(kind, rcp["username"], n)
        except MarketAppError as exc:
            log.warning("سفارش MarketApp ساخته نشد: %s", exc)
            if exc.code in ("not_found", "bad_input"):
                return _fail("rejected", str(exc)[:200])
            return _fail(PROVIDER)
        finally:
            await cli.close()
        check = inspect_tx(tx, kind, n, q["ton"])
        msg = tx["messages"][0]
        order = await db.create_tg_order(
            user["id"], kind, n, rcp["username"], rcp["name"], q["usd"], q["ton"], q["price"], DEMO, DEMO,
            ref=check["ref"], tx_to=check["to"], tx_amount=str(msg.get("amount") or ""), fragment=check["fragment"],
            error="; ".join(check["problems"]) or None,
        )
        if not check["ok"]:
            log.warning("بررسی تراکنش MarketApp رد شد (%s): %s", order["code"], check["problems"])
        return {"ok": True, "demo": True, "order": order, "check": check, "recipient": rcp,
                "balance": int(user["balance"])}
    finally:
        await db.release_lock(lock)


# ═══════════════════ تست کامل API برای پنل ادمین ═══════════════════


def check_running() -> bool:
    return _check is not None and not _check.done()


def report(tok: str, user: str, channel: str | None) -> tuple[str, list[dict]]:
    """همگام: کل گزارش متنی (توکن پاک شده) و نتیجه درخواست ها."""
    from app.services import marketapp_check

    lines: list[str] = []
    results = marketapp_check.run(tok, user, channel, None, raw=True, out=lines.append, budget=CHECK_BUDGET)
    return "\n".join(lines).replace(tok, "***"), results


def _caption(results: list[dict], user: str, channel: str | None) -> str:
    ok = sum(1 for r in results if r["ok"])
    out = [f"🧪 <b>تست کامل MarketApp</b> · @{esc(user)}" + (f" · @{esc(channel)}" if channel else ""),
           f"✅ {ok} از {len(results)} درخواست موفق"]
    bad = [r for r in results if not r["ok"]]
    if bad and not ok:
        out.append(f"❌ هیچ درخواستی موفق نشد: {esc(str(bad[0].get('text') or bad[0].get('data') or '')[:150])}")
        if all(r["status"] == 0 for r in bad):
            out.append("هاست به api.marketapp.org وصل نمی‌شود؛ MARKETAPP_PROXY را در .env بگذار.")
    elif bad:
        out.append("خطاها (بعضی عمدی اند، برای دیدن قالب خطا):")
        for r in bad[:8]:
            out.append(f"• {r['status']} {esc(r['name'])}")
        if len(bad) > 8:
            out.append(f"• … و {len(bad) - 8} مورد دیگر")
    out.append("جزئیات و پاسخ خام همه درخواست ها در فایل. چیزی امضا یا پرداخت نشد.")
    return "\n".join(out)[:1024]


async def _check_and_send(bot: "Bot", tok: str, chat_id: int, user: str, channel: str | None) -> None:
    from aiogram.types import BufferedInputFile

    try:
        text, results = await asyncio.to_thread(report, tok, user, channel)
    except Exception as exc:  # noqa: BLE001
        log.exception("marketapp check failed")
        await bot.send_message(chat_id, f"❌ تست MarketApp اجرا نشد: <code>{esc(str(exc)[:300])}</code>")
        return
    name = f"marketapp_check_{datetime.now():%Y%m%d_%H%M%S}.txt"
    await bot.send_document(chat_id, BufferedInputFile(text.encode("utf-8"), filename=name),
                            caption=_caption(results, user, channel))


async def start_check(bot: "Bot", db: "Database", chat_id: int, user: str, channel: str | None) -> bool:
    """تست کامل را در پس زمینه شروع می کند. اگر یکی در حال اجراست یا توکن نیست False."""
    global _check
    tok = await token(db)
    if not tok or check_running():
        return False
    _check = asyncio.get_running_loop().create_task(_check_and_send(bot, tok, chat_id, user, channel))
    return True
