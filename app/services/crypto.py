"""شارژ کیف پول با TON و USDT (روی شبکه TON)؛ برای کاربرهای خارج از کشور.

جریان:
  ۱. کاربر مبلغ تومانی و ارز را انتخاب می کند؛ فاکتور با یک کد یکتا
     (مثل OB-7K2M9Q) و مبلغ به TON/USDT ساخته می شود و نرخ همان لحظه
     روی فاکتور قفل می شود.
  ۲. کاربر پرداخت می کند: در مینی اپ با TON Connect (کیف پول خودش امضا
     می کند)، یا در ربات با لینک Tonkeeper یا دستی. کد فاکتور در کامنت
     تراکنش است.
  ۳. پایشگر تراکنش های ورودی کیف پول ما را از Toncenter می خواند، از روی
     کامنت فاکتور را پیدا می کند و اگر مبلغ کافی بود، کیف پول تومانی کاربر
     را شارژ می کند. ادمین لازم نیست.

امنیت:
  - به چیزی که مینی اپ بعد از sendTransaction می گوید اعتماد نمی شود؛
    فقط تراکنش واقعی روی زنجیره شارژ می کند.
  - USDT از تراکنش های کیف پول جتونِ *خودمان* خوانده می شود، که آدرسش
    از خود مستر تتر پرسیده شده. قرارداد جتون internal_transfer را فقط از
    کیف پول جتون همان مستر می پذیرد؛ پس جتون تقلبی با اسم USDT تراکنش
    موفقی روی این آدرس نمی سازد.
  - هر tx_hash فقط یک بار مصرف می شود (UNIQUE در دیتابیس).
  - کم پرداخت خودکار شارژ نمی شود؛ به ادمین گزارش می شود.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote as url_quote

from app import i18n, texts
from app.config import config
from app.utils import esc
from app.services import charge as charge_svc
from app.ton import (  # noqa: F401  (TonError از همین ماژول هم در دسترس است)
    Address, Cell, TonError, address_from_boc, address_slice_boc, comment_cell,
    jetton_transfer_body, read_comment, read_internal_transfer,
)

if TYPE_CHECKING:
    from app.db import Database

log = logging.getLogger("obour.crypto")

TON, USDT = "TON", "USDT"
ASSETS = (TON, USDT)
USDT_MAINNET = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
# TON همراه انتقال جتون برای کارمزد شبکه؛ اضافه اش به کیف پول کاربر برمی گردد
JETTON_ATTACH = 80_000_000
# مبلغ فاکتور به این دقت گرد (رو به بالا) می شود: ۰٫۰۱ از هر ارز
_ROUND_DECIMALS = 2

# کد خطاها (API و ربات هر کدام متن خودشان را دارند)
OFF = "off"
NO_RATE = "no_rate"
BAD_ASSET = "bad_asset"
TOO_SMALL = charge_svc.TOO_SMALL
TOO_LARGE = charge_svc.TOO_LARGE
NEED_WALLET = "need_wallet"
NETWORK = "network"

_CODE_RE = re.compile(r"OB-[A-Z0-9]{6}")
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


# ═══════════════════ تنظیمات ═══════════════════


def testnet() -> bool:
    return config.ton_network == "testnet"


def network_id() -> str:
    """شناسه شبکه در TON Connect: -239 اصلی، -3 تست."""
    return "-3" if testnet() else "-239"


def receive_address() -> Address | None:
    try:
        return Address.parse(config.ton_receive_address) if config.ton_receive_address else None
    except TonError:
        log.error("TON_RECEIVE_ADDRESS نامعتبر است: %r", config.ton_receive_address)
        return None


def usdt_master() -> Address | None:
    raw = config.ton_usdt_master or ("" if testnet() else USDT_MAINNET)
    try:
        return Address.parse(raw) if raw else None
    except TonError:
        log.error("TON_USDT_MASTER نامعتبر است: %r", raw)
        return None


def decimals(asset: str) -> int:
    return 9 if asset == TON else config.ton_usdt_decimals


def fmt_units(units: int, asset: str) -> str:
    """۱۲۳۴۰۰۰۰ میکرو تتر -> «12.34»؛ صفرهای اضافه حذف می شوند."""
    d = decimals(asset)
    whole, frac = divmod(int(units), 10 ** d)
    s = f"{whole}.{frac:0{d}d}".rstrip("0").rstrip(".")
    return s


def pay_address(bounceable: bool = False) -> str:
    addr = receive_address()
    return addr.friendly(bounceable=bounceable, testnet=testnet()) if addr else ""


# ═══════════════════ Toncenter ═══════════════════


def _api_base() -> str:
    if config.toncenter_url:
        return config.toncenter_url
    return "https://testnet.toncenter.com" if testnet() else "https://toncenter.com"


_session = None


def _http():  # noqa: ANN202
    """یک session برای همه درخواست ها، روی همان loop ربات."""
    global _session
    import aiohttp

    if _session is None or _session.closed:
        proxy = (config.ton_proxy or "").strip()
        connector = None
        if proxy.startswith("socks"):
            from aiohttp_socks import ProxyConnector

            connector = ProxyConnector.from_url(proxy)
        _session = aiohttp.ClientSession(
            connector=connector, timeout=aiohttp.ClientTimeout(total=12),
            headers={"User-Agent": "ObourBot"},
        )
    return _session


def _proxy_kw() -> dict:
    proxy = (config.ton_proxy or "").strip()
    return {"proxy": proxy} if proxy.startswith("http") else {}


class TonApiError(RuntimeError):
    pass


async def _call(method: str, path: str, *, params: dict | None = None, body: dict | None = None) -> dict:
    headers = {"X-API-Key": config.toncenter_api_key} if config.toncenter_api_key else {}
    url = _api_base() + path
    for attempt in range(3):
        try:
            async with _http().request(method, url, params=params, json=body, headers=headers, **_proxy_kw()) as r:
                if r.status == 429:           # سقف درخواست؛ کمی صبر و دوباره
                    await asyncio.sleep(1.2 * (attempt + 1))
                    continue
                data = await r.json(content_type=None)
                if r.status >= 400:
                    raise TonApiError(f"{r.status}: {str(data)[:200]}")
                return data
        except (asyncio.TimeoutError, OSError) as exc:
            if attempt == 2:
                raise TonApiError(f"{type(exc).__name__}") from exc
            await asyncio.sleep(0.8)
        except Exception as exc:  # noqa: BLE001  (aiohttp.ClientError و json خراب)
            if isinstance(exc, TonApiError):
                raise
            if attempt == 2:
                raise TonApiError(f"{type(exc).__name__}: {exc}") from exc
            await asyncio.sleep(0.8)
    raise TonApiError("429")


async def account_transactions(account: Address, limit: int = 60) -> list[dict]:
    data = await _call("GET", "/api/v3/transactions", params={
        "account": account.raw, "limit": str(limit), "offset": "0", "sort": "desc",
    })
    return list(data.get("transactions") or [])


_JW_CACHE: dict[tuple[str, str], Address] = {}


async def jetton_wallet(owner: Address, master: Address) -> Address:
    """آدرس کیف پول جتون owner، پرسیده شده از خود مستر (get_wallet_address).

    اول API نسخه ۳ و اگر نشد نسخه ۲ Toncenter امتحان می شود؛ شکل جواب
    این دو فرق دارد.
    """
    key = (owner.raw, master.raw)
    if key in _JW_CACHE:
        return _JW_CACHE[key]
    boc = address_slice_boc(owner)
    found: Address | None = None
    errors = []
    try:
        data = await _call("POST", "/api/v3/runGetMethod", body={
            "address": master.raw, "method": "get_wallet_address",
            "stack": [{"type": "slice", "value": boc}],
        })
        if int(data.get("exit_code", 0)) == 0 and data.get("stack"):
            item = data["stack"][0]
            found = address_from_boc(item.get("value") or "")
    except TonApiError as exc:
        errors.append(f"v3 {exc}")
    if found is None:
        try:
            data = await _call("POST", "/api/v2/runGetMethod", body={
                "address": master.friendly(bounceable=True, testnet=testnet()),
                "method": "get_wallet_address", "stack": [["tvm.Slice", boc]],
            })
            res = data.get("result") or {}
            if int(res.get("exit_code", 0)) == 0 and res.get("stack"):
                item = res["stack"][0]
                cell = item[1] if isinstance(item, list) and len(item) > 1 else {}
                found = address_from_boc((cell or {}).get("bytes") or "")
        except TonApiError as exc:
            errors.append(f"v2 {exc}")
    if found is None:
        raise TonApiError("کیف پول جتون پیدا نشد: " + "; ".join(errors))
    _JW_CACHE[key] = found
    return found


# ═══════════════════ نرخ ═══════════════════

_TON_USD: tuple[float, float] = (0.0, 0.0)   # (قیمت، زمان)


async def _ton_usd() -> float:
    """قیمت دلاری TON از tonapi.io، ده دقیقه کش. خطا -> ۰ (یعنی نامعلوم)."""
    global _TON_USD
    price, at = _TON_USD
    if price and time.monotonic() - at < 600:
        return price
    try:
        async with _http().get("https://tonapi.io/v2/rates", params={"tokens": "ton", "currencies": "usd"}, **_proxy_kw()) as r:
            data = await r.json(content_type=None)
        price = float(data["rates"]["TON"]["prices"]["USD"])
        _TON_USD = (price, time.monotonic())
        return price
    except Exception:  # noqa: BLE001
        log.warning("قیمت TON از tonapi خوانده نشد", exc_info=True)
        return _TON_USD[0]


async def rates(db: "Database") -> dict[str, int]:
    """تومان برای هر ۱ واحد از هر ارز. ۰ یعنی این ارز فعلا قابل پرداخت نیست.

    نرخ تتر را ادمین تعیین می کند (بازار ایران API قابل اعتماد ندارد).
    نرخ TON اگر دستی تعیین نشده باشد از قیمت دلاری TON × نرخ تتر ساخته
    می شود.
    """
    def _int(v: str) -> int:
        try:
            return max(0, int(float((v or "0").replace(",", ""))))
        except ValueError:
            return 0

    usdt = _int(await db.get_setting("crypto_usdt_rate", "0"))
    ton = _int(await db.get_setting("crypto_ton_rate", "0"))
    if not ton and usdt:
        ton = int(round(await _ton_usd() * usdt))
    return {TON: ton, USDT: usdt if usdt_master() else 0}


async def fee_percent(db: "Database") -> float:
    try:
        return max(0.0, min(50.0, float(await db.get_setting("crypto_fee_percent", "0") or 0)))
    except ValueError:
        return 0.0


def enabled() -> bool:
    return receive_address() is not None


async def configured(db: "Database") -> bool:
    """آدرس هست و دست کم یک نرخ تعیین شده (بدون خواندن قیمت از اینترنت)."""
    for key in ("crypto_usdt_rate", "crypto_ton_rate"):
        try:
            if float((await db.get_setting(key, "0") or "0").replace(",", "")) > 0:
                return True
        except ValueError:
            pass
    return False


def to_units(toman: int, rate: int, asset: str, fee: float = 0.0) -> int:
    """تومان -> کوچک ترین واحد ارز، گرد شده رو به بالا به ۰٫۰۱."""
    d = decimals(asset)
    step = 10 ** max(0, d - _ROUND_DECIMALS)
    raw = toman * (1 + fee / 100) / rate * (10 ** d)
    return int(math.ceil(raw / step - 1e-9) * step)


async def quote(db: "Database", toman: int) -> dict:
    """مبلغ هر ارز برای یک مبلغ تومانی، برای نمایش پیش از انتخاب."""
    r = await rates(db)
    fee = await fee_percent(db)
    out = {}
    for a in ASSETS:
        if r.get(a):
            units = to_units(toman, r[a], a, fee)
            out[a] = {"units": units, "amount": fmt_units(units, a), "rate": r[a]}
    return out


# ═══════════════════ فاکتور ═══════════════════


def _new_code() -> str:
    return "OB-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


async def create_invoice(db: "Database", user: dict, toman: int, asset: str, source: str) -> dict:
    """{ok, invoice} یا {ok: False, error}."""
    if not enabled():
        return {"ok": False, "error": OFF}
    asset = (asset or "").upper()
    if asset not in ASSETS:
        return {"ok": False, "error": BAD_ASSET}
    min_c = await charge_svc.min_charge(db)
    if toman < min_c:
        return {"ok": False, "error": TOO_SMALL, "min": min_c}
    if toman > charge_svc.MAX_CHARGE:
        return {"ok": False, "error": TOO_LARGE}
    r = await rates(db)
    if not r.get(asset):
        return {"ok": False, "error": NO_RATE}
    units = to_units(toman, r[asset], asset, await fee_percent(db))
    for _ in range(5):
        code = _new_code()
        if not await db.crypto_invoice_by_code(code):
            break
    inv_id = await db.create_crypto_invoice(
        user_id=user["id"], code=code, asset=asset, units=units, toman=toman,
        rate=r[asset], source=source, minutes=config.crypto_invoice_minutes,
    )
    return {"ok": True, "invoice": await db.get_crypto_invoice(inv_id)}


def tonkeeper_link(inv: dict) -> str:
    """لینک https که Tonkeeper (و کیف پول هایی که ton:// را می فهمند) باز می کند.

    تلگرام روی دکمه فقط http/https/tg را می پذیرد، پس ton:// نمی شود.
    """
    addr = pay_address()
    q = f"amount={inv['units']}&text={url_quote(inv['code'])}"
    if inv["asset"] == USDT:
        master = usdt_master()
        q = f"jetton={master.friendly(bounceable=True, testnet=testnet())}&" + q if master else q
    return f"https://app.tonkeeper.com/transfer/{addr}?{q}"


async def ton_connect_messages(inv: dict, payer: str | None) -> list[dict]:
    """پیام های sendTransaction برای TON Connect.

    TON: یک انتقال ساده به آدرس ما با کامنت.
    USDT: پیام به کیف پول جتونِ خودِ کاربر با بدنه transfer (TEP-74)؛
    مقصد نهایی آدرس ما و کامنت در forward_payload است.
    """
    recv = receive_address()
    if recv is None:
        raise TonApiError("off")
    if inv["asset"] == TON:
        return [{
            "address": recv.friendly(bounceable=False, testnet=testnet()),
            "amount": str(int(inv["units"])),
            "payload": comment_cell(inv["code"]).to_boc(),
        }]
    master = usdt_master()
    if master is None:
        raise TonApiError("usdt off")
    owner = Address.parse(payer or "")
    jw = await jetton_wallet(owner, master)
    body = jetton_transfer_body(
        amount=int(inv["units"]), destination=recv, response=owner,
        comment=inv["code"], forward_ton=1,
    )
    return [{
        "address": jw.friendly(bounceable=True, testnet=testnet()),
        "amount": str(JETTON_ATTACH),
        "payload": body.to_boc(),
    }]


def public(inv: dict) -> dict:
    """شکل فاکتور برای مینی اپ."""
    from app.utils import now_str

    status = inv["status"]
    if status == "pending" and inv["expires_at"] <= now_str():
        status = "expired"
    return {
        "id": inv["id"], "code": inv["code"], "asset": inv["asset"],
        "units": str(inv["units"]), "amount": fmt_units(inv["units"], inv["asset"]),
        "toman": inv["toman"], "status": status, "expires_at": inv["expires_at"],
        "ttl_minutes": config.crypto_invoice_minutes,
        "address": pay_address(), "network": network_id(), "testnet": testnet(),
        "link": tonkeeper_link(inv),
        "paid_amount": fmt_units(inv["paid_units"], inv["asset"]) if inv.get("paid_units") else None,
    }


# ═══════════════════ خواندن پرداخت ها ═══════════════════


@dataclass
class Payment:
    asset: str
    tx_hash: str
    units: int
    payer: str
    comment: str | None

    @property
    def code(self) -> str | None:
        m = _CODE_RE.search((self.comment or "").upper())
        return m.group(0) if m else None


def _body_cell(msg: dict) -> Cell | None:
    body = ((msg.get("message_content") or {}).get("body")) or ""
    if not body:
        return None
    try:
        return Cell.from_boc(body)
    except (TonError, IndexError, ValueError):
        return None


def parse_ton_payment(tx: dict) -> Payment | None:
    """یک تراکنش کیف پول ما -> پرداخت TON، یا None."""
    m = tx.get("in_msg") or {}
    src = m.get("source")
    if not src or m.get("bounced"):
        return None                     # پیام خارجی یا برگشتی
    desc = tx.get("description") or {}
    # پیام bounceable به کیف پولی که aborted شده، پول را برمی گرداند
    if desc.get("aborted") and m.get("bounce"):
        return None
    value = int(m.get("value") or 0)
    if value <= 0:
        return None
    comment = read_comment(_body_cell(m))
    if comment is None:
        decoded = (m.get("message_content") or {}).get("decoded") or {}
        comment = decoded.get("comment") if decoded.get("type") == "text_comment" else None
    return Payment(TON, str(tx.get("hash") or ""), value, str(src), comment)


def parse_jetton_payment(tx: dict) -> Payment | None:
    """یک تراکنش کیف پول جتون ما -> پرداخت USDT، یا None.

    فقط تراکنش موفق حساب است: قرارداد جتون internal_transfer ناشناس را
    رد می کند (aborted)، پس موفق بودن یعنی واقعا تتر رسیده.
    """
    desc = tx.get("description") or {}
    if desc.get("aborted"):
        return None
    compute = desc.get("compute_ph") or {}
    if compute and not compute.get("success", False):
        return None
    m = tx.get("in_msg") or {}
    if not m.get("source") or m.get("bounced"):
        return None
    cell = _body_cell(m)
    if cell is None:
        return None
    j = read_internal_transfer(cell)
    if j is None or j.amount <= 0:
        return None
    payer = j.sender.raw if j.sender else str(m.get("source"))
    return Payment(USDT, str(tx.get("hash") or ""), j.amount, payer, j.comment)


_our_jw: Address | None = None


async def our_jetton_wallet(db: "Database") -> Address | None:
    """کیف پول تتر خودمان؛ یک بار پرسیده و در تنظیمات ذخیره می شود."""
    global _our_jw
    recv, master = receive_address(), usdt_master()
    if recv is None or master is None:
        return None
    if _our_jw is not None:
        return _our_jw
    key = f"crypto_jw:{recv.raw}:{master.raw}"
    saved = await db.get_setting(key, "")
    if saved:
        try:
            _our_jw = Address.parse(saved)
            return _our_jw
        except TonError:
            pass
    _our_jw = await jetton_wallet(recv, master)
    await db.set_setting(key, _our_jw.raw)
    return _our_jw


async def fetch_payments(db: "Database", assets: set[str]) -> list[Payment]:
    out: list[Payment] = []
    recv = receive_address()
    if recv is None:
        return out
    if TON in assets:
        for tx in await account_transactions(recv):
            p = parse_ton_payment(tx)
            if p:
                out.append(p)
    if USDT in assets:
        jw = await our_jetton_wallet(db)
        if jw is not None:
            for tx in await account_transactions(jw):
                p = parse_jetton_payment(tx)
                if p:
                    out.append(p)
    return out


# ═══════════════════ تطبیق و شارژ ═══════════════════

_scan_lock: asyncio.Lock | None = None
_last_scan = 0.0
_MIN_GAP = 4.0


async def scan(db: "Database", bot=None, *, force: bool = False) -> int:  # noqa: ANN001
    """یک دور: پرداخت های تازه را پیدا و فاکتورها را تسویه می کند.

    خروجی: تعداد فاکتورهایی که در این دور بسته شدند. چند صدا زدن پشت سر
    هم (مینی اپ هر چند ثانیه وضعیت را می پرسد) به یک درخواست به Toncenter
    در هر چند ثانیه تبدیل می شود.
    """
    global _scan_lock, _last_scan
    if not enabled():
        return 0
    if _scan_lock is None:
        _scan_lock = asyncio.Lock()
    if _scan_lock.locked():
        return 0
    async with _scan_lock:
        if not force and time.monotonic() - _last_scan < _MIN_GAP:
            return 0
        _last_scan = time.monotonic()
        invoices = await db.watch_crypto_invoices()
        if not invoices:
            return 0
        by_code = {inv["code"]: inv for inv in invoices}
        try:
            payments = await fetch_payments(db, {inv["asset"] for inv in invoices})
        except TonApiError as exc:
            log.warning("خواندن تراکنش ها از Toncenter نشد: %s", exc)
            return 0
        closed = 0
        for p in payments:
            inv = by_code.get(p.code or "")
            if inv is None or inv["asset"] != p.asset or not p.tx_hash:
                continue
            if await settle(db, bot, inv, p):
                closed += 1
                by_code.pop(inv["code"], None)
        return closed


async def settle(db: "Database", bot, inv: dict, p: Payment) -> bool:  # noqa: ANN001
    if await db.crypto_tx_seen(p.tx_hash):
        return False
    status = "paid" if p.units >= int(inv["units"]) else "underpaid"
    if not await db.settle_crypto_invoice(
        inv["id"], status=status, tx_hash=p.tx_hash, payer=p.payer, paid_units=p.units,
    ):
        return False
    user = await db.get_user(inv["user_id"])
    if status == "paid":
        txn_id = await db.insert_transaction(
            user_id=inv["user_id"], type_="charge", amount=int(inv["toman"]),
            status="approved", idem_key=f"crypto:{inv['id']}",
        )
        if txn_id is None:
            log.error("تراکنش شارژ کریپتو تکراری بود invoice=%s", inv["id"])
            return False
        if not await db.atomic_credit(inv["user_id"], int(inv["toman"])):
            log.error("شارژ کریپتو به موجودی اضافه نشد invoice=%s", inv["id"])
        await db.set_crypto_txn(inv["id"], txn_id)
        log.info("شارژ کریپتو %s: %s %s -> %s تومان کاربر %s",
                 inv["code"], fmt_units(p.units, p.asset), p.asset, inv["toman"], inv["user_id"])
        user = await db.get_user(inv["user_id"])
    else:
        log.warning("کم پرداخت %s: %s از %s", inv["code"], p.units, inv["units"])
    if bot is not None and user:
        await _announce(bot, inv, p, user, status)
    return True


async def _announce(bot, inv: dict, p: Payment, user: dict, status: str) -> None:  # noqa: ANN001
    paid = fmt_units(p.units, p.asset)
    lang = i18n.lang_of(user)
    with i18n.using(lang):
        if status == "paid":
            body = texts.CRYPTO_PAID.format(
                amount=f"{inv['toman']:,}", crypto=paid, asset=p.asset,
                balance=f"{user['balance']:,}", code=inv["code"],
            )
        else:
            body = texts.CRYPTO_UNDERPAID.format(
                paid=paid, need=fmt_units(inv["units"], inv["asset"]), asset=p.asset, code=inv["code"],
            )
    try:
        await bot.send_message(int(user["telegram_id"]), body)
    except Exception:  # noqa: BLE001
        log.warning("خبر شارژ کریپتو به کاربر %s نرسید", user.get("telegram_id"), exc_info=True)

    with i18n.using("fa"):
        admin = texts.ADMIN_CRYPTO_IN.format(
            state="✅ شارژ شد" if status == "paid" else "⚠️ کم پرداخت؛ شارژ نشد",
            name=esc(user.get("first_name") or "-"), telegram_id=user["telegram_id"],
            crypto=paid, need=fmt_units(inv["units"], inv["asset"]), asset=p.asset,
            amount=f"{inv['toman']:,}", code=inv["code"],
            tx=_explorer(p.tx_hash),
        )
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(admin_id, admin, disable_web_page_preview=True)
        except Exception:  # noqa: BLE001
            log.warning("گزارش شارژ کریپتو به ادمین %s نرسید", admin_id)


def _explorer(tx_hash: str) -> str:
    import base64

    try:
        hx = base64.b64decode(tx_hash + "=" * (-len(tx_hash) % 4)).hex()
    except Exception:  # noqa: BLE001
        hx = tx_hash
    host = "testnet.tonviewer.com" if testnet() else "tonviewer.com"
    return f"https://{host}/transaction/{hx}"


# ═══════════════════ پایشگر ═══════════════════

_watcher: asyncio.Task | None = None


def ensure_watcher(db: "Database", bot) -> None:  # noqa: ANN001
    """تا وقتی فاکتور در مهلت هست، هر چند ثانیه یک بار بررسی می کند.

    روی همان event loop ربات اجرا می شود. وقتی فاکتور باز نماند، خودش
    تمام می شود؛ پرداخت های دیرتر را کران خودکار و «بررسی پرداخت» پیدا
    می کنند.
    """
    global _watcher
    if not enabled():
        return
    if _watcher is not None and not _watcher.done():
        return
    try:
        _watcher = asyncio.get_running_loop().create_task(_watch(db, bot))
    except RuntimeError:
        pass


async def _watch(db: "Database", bot) -> None:  # noqa: ANN001
    from app.utils import now_str

    idle = errors = 0
    while True:
        try:
            await scan(db, bot, force=True)
            active = [i for i in await db.watch_crypto_invoices()
                      if i["status"] == "pending" and i["expires_at"] > now_str()]
            errors = 0
        except Exception:  # noqa: BLE001
            log.warning("پایش پرداخت کریپتو خطا داد", exc_info=True)
            errors += 1
            active = [] if errors >= 20 else [None]
        idle = 0 if active else idle + 1
        if idle >= 2:
            return
        await asyncio.sleep(8)
