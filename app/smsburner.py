"""اتصال به SMSBurner (smsburner.com) برای فروش شماره مجازی.

قرارداد (از https://smsburner.com/openapi.json و https://smsburner.com/fa/api):

    پایه: https://smsburner.com/api/v1          هدر  Authorization: Bearer <seed>
    GET  /catalog           ردیف های (سرویس × کشور) با قیمت دلاری و موجودی  ← rows
    GET  /services          همه سرویس ها (id، name، slug، category)           ← services
    GET  /countries         همه کشورها (code، name)                            ← countries
    POST /quote             {"service_id", "country"}  ← قیمت نهایی
    GET  /account           حساب و موجودی ما
    POST /numbers           خرید  {"service_id", "country"}  ← شماره صادر می شود
    GET  /numbers/{id}      پیگیری: phone_number، sms_code، status
    POST /numbers/{id}/cancel  لغو و برگشت پول (فقط تا وقتی پیامک نیامده)

seed (۱۶ حرف، مثل AbC3-dEf4-gHj5-kLm6) تنها اعتبار حساب است و موجودی ما
را خرج می کند؛ هیچ وقت در لاگ نوشته نمی شود.

دو روش اتصال با همان seed (خودکار تشخیص داده می شود و در دیتابیس می ماند):

    bearer   /api/v1 با هدر Authorization: Bearer <seed> (حساب هایی که از POST /api/v1/account ساخته شده اند)
    session  مستند اصلی سایت: POST /auth-api.php {action: login, seed} ← کوکی ← api.php?action=...
             (حساب های ساخته شده از خود سایت: user، buy، orders، cancel). ورود فقط ۵ بار در ۱۵ دقیقه
             مجاز است، پس کوکی ذخیره می شود و فقط وقتی منقضی شد دوباره وارد می شویم.
             پیگیری شماره از فهرست «orders» (۵۰ سفارش اخیر) است؛ شماره ی تلفن ممکن است چند ثانیه بعد
             از خرید در آن پیدا شود، و quote ندارد (قیمت از جدول قیمت ها و پاسخ خرید می آید).

نکته مهم: خرید کلید یکتا (Idempotency-Key) ندارد. پس خریدی که شاید به
سرویس دهنده رسیده باشد (قطع وسط پاسخ، ۵xx) **هیچ وقت دوباره فرستاده
نمی شود** و CanbosoUnknown بالا می رود؛ ادمین آن را دستی می بندد.

شکل دقیق پاسخ خرید و پیگیری در مستند نیامده؛ برای همین نام های رایج
هر فیلد پذیرفته می شود و پاسخ خام از پنل ادمین («خروجی خام») دیده
می شود. خطاها همان خطاهای canboso اند تا بقیه ربات یک رفتار ببیند.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import httpx

from app.canboso import CanbosoError, CanbosoNoFunds, CanbosoUnknown, norm_currency

log = logging.getLogger("obour.smsburner")

BASE_URL = "https://smsburner.com/api/v1"
NAME = "smsburner"
TIMEOUT = 15.0              # کاتالوگ، قیمت، پیگیری: کوتاه، تا هندلر وبهوک (۵۰ ثانیه) نترکد
BUY_TIMEOUT = 25.0          # خود خرید کمی بیشتر صبر می کند
MIN_INTERVAL = 1.1          # فاصله حداقل بین دو درخواست؛ سایت بعد از چند درخواست پشت سر هم ۴۲۹ «Wait 1 s» می دهد
CATALOG_TTL = 60.0
BALANCE_TTL = 30.0
MAX_WAIT = 15.0
# پنجره تحویل هر شماره نزد سرویس دهنده (دقیقه)
VALID_MINUTES = 20

# وضعیت اتصال هر seed (مشترک بین نمونه های کلاینت): {tag: {"mode": "", "cookies": {...}}}.
# tag هش seed است، نه خود seed.
_STATE: dict[str, dict] = {}
_LOGINS: list[float] = []     # زمان ورودهای اخیر (سقف سایت: ۵ بار در ۱۵ دقیقه)
_AUTH_LOCK = asyncio.Lock()   # تشخیص روش اتصال و ورود یکی یکی انجام شوند
LOGIN_BUDGET = 3              # حداکثر ورود در ۱۵ دقیقه که خودمان مجاز می دانیم

_last_call = 0.0
_rate_lock = asyncio.Lock()
_cache: dict[str, tuple[float, Any]] = {}


# نوع اپراتور: virtual (VoIP، ارزان، ممکنه بعضی سرویس ها رد کنن)، physical (سیم کارت واقعی)،
# premium (سریع ترین، حدود ۱۰ ثانیه، بیشترین موفقیت)
OP_TYPES = ("virtual", "physical", "premium")


def seed_tag(seed: str) -> str:
    return hashlib.sha256((seed or "").encode()).hexdigest()[:12]


def _login_required(data: Any) -> bool:
    return isinstance(data, dict) and (str(data.get("error") or "").lower() == "login required"
                                       or data.get("logged_in") is False)


class SmsBadSeed(CanbosoError):
    """seed نامعتبر است (۴۰۱ یا ۴۰۳). تا ادمین درستش نکند هیچ خریدی ممکن نیست."""


class SmsOrderNotFound(CanbosoError):
    """سفارش در ۵۰ سفارش اخیر حساب نیست (روش نشست فقط همین فهرست را دارد)."""


class SmsOutOfStock(CanbosoError):
    """برای این سرویس و کشور شماره ای نیست (قطعا خرید انجام نشد)."""


class SmsAlreadyReceived(CanbosoError):
    """پیامک رسیده؛ دیگر نمی شود لغو کرد."""


async def _pace() -> None:
    global _last_call
    async with _rate_lock:
        gap = time.monotonic() - _last_call
        if gap < MIN_INTERVAL:
            await asyncio.sleep(MIN_INTERVAL - gap)
        _last_call = time.monotonic()


def _first(d: Any, *keys: str) -> Any:
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if v not in (None, "") and not isinstance(v, (dict, list)):
            return v
    return None


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "").lstrip("$").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _message(r: httpx.Response) -> str:
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return r.text[:200]
    if isinstance(data, dict):
        err = data.get("message") or data.get("error") or data.get("detail")
        if isinstance(err, dict):
            err = err.get("message") or err.get("code")
        return str(err or data)[:200]
    return str(data)[:200]


def _error_code(r: httpx.Response) -> str:
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        return ""
    return str(data.get("error") or "").lower() if isinstance(data, dict) else ""


def _no_funds(code: str, msg: str) -> bool:
    low = f"{code} {msg}".lower()
    return any(w in low for w in ("insufficient", "balance", "funds", "top up", "top-up"))


def _out_of_stock(code: str, msg: str) -> bool:
    low = f"{code} {msg}".lower()
    return any(w in low for w in ("stock", "not available", "unavailable", "no numbers", "no_numbers", "sold"))


def _unwrap(data: Any) -> dict:
    """بدنه اصلی پاسخ: بعضی پاسخ ها شماره را زیر number/order/data می گذارند."""
    if not isinstance(data, dict):
        return {}
    for k in ("number", "order", "data", "result"):
        if isinstance(data.get(k), dict):
            return data[k]
    return data


def norm_phone(v: Any) -> str:
    s = str(v or "").strip()
    if s and s.lstrip("+").replace(" ", "").replace("-", "").isdigit() and not s.startswith("+"):
        return "+" + s
    return s


def norm_status(status: Any, sms_code: Any) -> str:
    """active | completed | cancelled | refunded | expired."""
    if sms_code not in (None, ""):
        return "completed"
    s = str(status or "").strip().lower()
    if s in ("completed", "complete", "success", "received", "done", "finished"):
        return "completed"
    if s in ("cancelled", "canceled"):
        return "cancelled"
    if s in ("refunded", "refund"):
        return "refunded"
    if s in ("expired", "timeout", "timed_out"):
        return "expired"
    return "active"


def parse_number(data: Any) -> dict:
    """پاسخ خرید یا پیگیری به شکل ثابت: id، phone، sms_code، sms_text، status، price."""
    src = _unwrap(data)
    pid = _first(src, "number_id", "order_id", "id") or _first(data, "number_id", "order_id", "id")
    # فقط فیلدهای مستند: «code» یا «message» عمومی ممکن است کد کشور یا پیام وضعیت باشند و
    # اگر به جای کد پیامک برداشته شوند، سفارش با کد جعلی «تحویل شده» می شود
    code = _first(src, "sms_code", "otp_code") or _first(data, "sms_code")
    text = _first(src, "sms_text", "sms_body")
    exp_in = _num(_first(src, "expires_in", "ttl", "seconds_left"))
    return {
        "id": str(pid) if pid not in (None, "") else "",
        "phone": norm_phone(_first(src, "phone_number", "phone", "number", "msisdn")),
        "sms_code": str(code) if code not in (None, "") else "",
        "sms_text": str(text) if text not in (None, "") else "",
        "status": norm_status(_first(src, "status", "state"), code),
        "price": _num(_first(src, "price", "price_usd", "cost", "charged")),
        "expires_at": str(_first(src, "expires_at", "expiry", "expires") or ""),
        "expires_in": exp_in,
        "raw": data,
    }


def normalize_rows(data: Any) -> list[dict]:
    """GET /catalog ← ردیف های (سرویس × کشور) با قیمت دلاری."""
    raw = data.get("rows") if isinstance(data, dict) else data
    out: list[dict] = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        sid = _first(r, "service_id", "id")
        cc = str(_first(r, "country_code", "country", "code") or "").strip().lower()
        price = _num(_first(r, "price", "price_usd", "cost"))
        if sid in (None, "") or not cc or price is None:
            continue
        stock = _num(_first(r, "stock", "available", "count"))
        out.append({
            "service_id": str(sid),
            "service": str(_first(r, "service", "service_name", "name") or sid),
            "slug": str(_first(r, "service_slug", "slug") or ""),
            "category": str(_first(r, "category") or "tech"),
            "cc": cc,
            "country": str(_first(r, "country_name", "country_title")
                           or (_first(r, "country") if _first(r, "country_code") else None) or cc.upper()),
            "price": price,
            "stock": None if stock is None else max(0, int(stock)),
        })
    return out


class SmsBurner:
    name = NAME
    # خرید کلید یکتا ندارد: خرید مبهم دوباره فرستاده نمی شود
    idempotent = False

    def __init__(self, seed: str, base_url: str | None = None, proxy: str = "", persist=None) -> None:  # noqa: ANN001
        self._seed = (seed or "").strip()
        self._tag = seed_tag(self._seed)
        self._state = _STATE.setdefault(self._tag, {"mode": "", "cookies": {}})
        self._persist_cb = persist
        base = (base_url or BASE_URL).rstrip("/")
        # ریشه سایت (برای مسیر قدیمی api.php که فهرست اپراتورها را دارد)
        self._origin = base.split("/api/")[0] if "/api/" in base else base
        kw: dict[str, Any] = {"proxy": proxy} if proxy.startswith(("http", "socks")) else {}
        self._http = httpx.AsyncClient(
            base_url=base, timeout=TIMEOUT,
            headers={"Authorization": f"Bearer {self._seed}", "Accept": "application/json"}, **kw,
        )
        host = self._origin.split("://", 1)[-1].split("/", 1)[0]
        for name, value in (self._state.get("cookies") or {}).items():
            self._http.cookies.set(name, value, domain=host)

    @property
    def configured(self) -> bool:
        return bool(self._seed)

    async def close(self) -> None:
        await self._http.aclose()

    # ---------- درخواست پایه ----------
    async def _get(self, path: str) -> Any:
        for attempt in range(2):
            await _pace()
            try:
                r = await self._http.get(path)
            except Exception as exc:  # noqa: BLE001
                raise CanbosoError(f"ارتباط برقرار نشد: {type(exc).__name__}") from exc
            if r.status_code == 429:
                wait = _retry_after(r, 5.0)
                if attempt == 0 and wait <= MAX_WAIT:
                    await asyncio.sleep(wait)
                    continue
                raise CanbosoError(f"سقف درخواست؛ {int(wait)} ثانیه دیگر")
            if r.status_code in (401, 403):
                raise SmsBadSeed("seed نامعتبر است")
            if r.status_code >= 400:
                raise CanbosoError(f"HTTP {r.status_code}: {_message(r)}")
            try:
                data = r.json()
            except Exception as exc:  # noqa: BLE001
                raise CanbosoError("پاسخ قابل خواندن نبود") from exc
            if isinstance(data, dict) and data.get("ok") is False:
                raise CanbosoError(_message(r))
            return data
        raise CanbosoError("سرویس دهنده شلوغ است")

    async def _cached(self, key: str, ttl: float, force: bool, path: str) -> Any:
        hit = _cache.get(key)
        if not force and hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        data = await self._get(path)
        _cache[key] = (time.monotonic(), data)
        return data

    # ---------- کاتالوگ ----------
    async def catalog(self, force: bool = False, max_age: float | None = None) -> list[dict]:
        """ردیف های (سرویس × کشور) با قیمت دلاری (فقط ۵۰۰ ردیف برتر). بدون seed هم کار می کند."""
        return normalize_rows(await self._cached("catalog", max_age if max_age is not None else CATALOG_TTL,
                                                 force, "/catalog"))

    async def country_services(self, cc: str) -> list[dict]:
        """همه ی سرویس های یک کشور با قیمت دلاری و موجودی (api.php، بدون seed).

        کاتالوگ /api/v1/catalog فقط ۵۰۰ ردیف دارد و فیلتر کشور یا سرویس را نمی پذیرد، پس برای
        فهرست کامل کشورهای هر سرویس، به ازای هر کشور یک بار از همین مسیر می خوانیم."""
        cc = (cc or "").lower()
        data = await self._get(f"{self._origin}/api.php?action=services&country={cc}")
        raw = data.get("services") if isinstance(data, dict) else data
        out: list[dict] = []
        for x in raw or []:
            if not isinstance(x, dict) or x.get("id") in (None, ""):
                continue
            price = _num(x.get("price"))
            if price is None:
                continue
            stock = _num(x.get("stock"))
            out.append({"service_id": str(x["id"]), "service": str(x.get("name") or x["id"]),
                        "slug": str(x.get("slug") or ""), "category": str(x.get("category") or "tech"),
                        "cc": cc, "price": price, "stock": None if stock is None else max(0, int(stock))})
        return out

    async def services(self, force: bool = False) -> list[dict]:
        data = await self._cached("services", 600.0, force, "/services")
        raw = data.get("services") if isinstance(data, dict) else data
        return [{"id": str(s["id"]), "name": str(s.get("name") or s["id"]), "slug": str(s.get("slug") or ""),
                 "category": str(s.get("category") or "tech")}
                for s in raw or [] if isinstance(s, dict) and s.get("id") not in (None, "")]

    async def countries(self, force: bool = False) -> list[dict]:
        data = await self._cached("countries", 600.0, force, "/countries")
        raw = data.get("countries") if isinstance(data, dict) else data
        return [{"code": str(c["code"]).lower(), "name": str(c.get("name") or c["code"])}
                for c in raw or [] if isinstance(c, dict) and c.get("code")]

    async def operators(self, cc: str, force: bool = False) -> list[dict]:
        """اپراتورهای یک کشور: [{id, name, type (virtual|physical|premium), mult}].

        فقط مسیر قدیمی api.php این فهرست را دارد (در /api/v1 نیست) و بدون seed هم
        جواب می دهد. هر اپراتور یک ضریب قیمت روی قیمت پایه سرویس دارد.
        """
        cc = (cc or "").lower()
        hit = _cache.get(f"ops:{cc}")
        if not force and hit and time.monotonic() - hit[0] < 600.0:
            return hit[1]
        data = await self._get(f"{self._origin}/api.php?action=operators&country={cc}")
        raw = data.get("operators") if isinstance(data, dict) else data
        out: list[dict] = []
        for o in raw or []:
            if not isinstance(o, dict) or o.get("id") in (None, ""):
                continue
            mult = _num(o.get("price_multiplier"))
            kind = str(o.get("type") or "").lower()
            if mult is None or mult <= 0:
                continue
            out.append({"id": str(o["id"]), "name": str(o.get("name") or o["id"]),
                        "type": kind if kind in OP_TYPES else "virtual", "mult": mult})
        _cache[f"ops:{cc}"] = (time.monotonic(), out)
        return out

    async def _b_quote(self, service_id: str, cc: str, operator_id: str | None = None) -> float | None:
        """(bearer) قیمت دلاری تازه برای یک سرویس و کشور (و اپراتور)؛ None اگر پاسخ قابل فهم نبود."""
        await _pace()
        body: dict[str, Any] = {"service_id": _id(service_id), "country": cc.upper()}
        if operator_id:
            body["operator_id"] = _id(operator_id)
        for attempt in range(2):
            try:
                r = await self._http.post("/quote", json=body)
            except Exception as exc:  # noqa: BLE001
                raise CanbosoError(f"ارتباط برقرار نشد: {type(exc).__name__}") from exc
            wait = _retry_after(r, 2.0)
            if r.status_code == 429 and attempt == 0 and wait <= 4.0:
                await asyncio.sleep(wait)       # فقط قیمت است؛ یک بار دوباره
                await _pace()
                continue
            break
        if r.status_code in (401, 403):
            raise SmsBadSeed("seed نامعتبر است")
        if r.status_code == 409 or (r.status_code == 404):
            raise SmsOutOfStock(_message(r))
        if r.status_code >= 400:
            return None     # از جمله ۴۲۹: قیمت تایید نشد؛ قیمت کاتالوگ می ماند و ادمین از هزینه ی واقعی باخبر می شود
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            return None
        src = _unwrap(data)
        return _num(_first(src, "price", "price_usd", "final_price", "total", "cost", "amount")) \
            or _num(_first(data, "price", "price_usd", "final_price", "total"))

    async def balance(self, force: bool = True) -> dict | None:
        """موجودی ما نزد سرویس دهنده؛ None اگر خوانده نشد."""
        if not self.configured:
            return None
        hit = _cache.get("balance")
        if not force and hit and time.monotonic() - hit[0] < BALANCE_TTL:
            return hit[1]
        out: dict | None = None
        try:
            out = await self._balance_raw()
            _cache.pop("balance_err", None)
        except CanbosoError as exc:
            log.info("موجودی سرویس دهنده خوانده نشد: %s", exc)
            _cache["balance_err"] = (time.monotonic(), exc)
        _cache["balance"] = (time.monotonic(), out)
        return out

    async def _balance_raw(self) -> dict | None:
        if await self._mode() == "session":
            return await self._s_balance()
        data = await self._get("/account")
        src = _unwrap(data)
        for k in ("account", "user", "wallet"):
            if isinstance(src.get(k), dict):
                src = src[k]
                break
        amount = _num(_first(src, "balance", "balance_usd", "amount", "credit")) if src else None
        if amount is None:
            amount = _num(_first(data, "balance", "balance_usd", "credit"))
        if amount is None:
            return None
        return {"balance": amount, "currency": norm_currency(_first(src, "currency") or "USD"), "text": ""}

    def mode_label(self) -> str:
        """برای پنل ادمین: روش اتصال تشخیص داده شده."""
        return {"bearer": "Bearer (/api/v1)", "session": "نشست کوکی (api.php)"}.get(self._state.get("mode") or "", "هنوز تشخیص داده نشده")

    @staticmethod
    def balance_error() -> Exception | None:
        """خطای آخرین خواندن موجودی؛ None اگر خوانده شد."""
        hit = _cache.get("balance_err")
        return hit[1] if hit else None

    async def debug(self) -> dict:
        """پاسخ خام چند مسیر برای پنل ادمین (بدون کش، کوتاه شده)."""
        out: dict[str, Any] = {}
        # اپراتورها فقط در api.php هستند (برای نوع شماره: مجازی / فیزیکی / پریمیوم)
        ops_url = f"{self._origin}/api.php?action=operators&country=us"
        for path in ("/account", "/countries", "/catalog", ops_url):
            await _pace()
            started = time.monotonic()
            try:
                r = await self._http.get(path)
                try:
                    body: Any = r.json()
                except Exception:  # noqa: BLE001
                    body = r.text[:1500]
                if isinstance(body, dict):
                    # فهرست های بلند را کوتاه کن تا پیام ادمین نترکد
                    body = {k: (v[:3] if isinstance(v, list) else v) for k, v in body.items()}
                elif isinstance(body, list):
                    body = body[:4]
                key = "/operators?country=us" if path == ops_url else path
                out[key] = {"status": r.status_code, "ms": int((time.monotonic() - started) * 1000), "body": body}
            except Exception as exc:  # noqa: BLE001
                out["/operators?country=us" if path == ops_url else path] = {
                    "status": 0, "error": f"{type(exc).__name__}: {exc}"}
        # روش نشست کوکی (مستند اصلی سایت): ورود با seed و خواندن user. کوکی هرگز چاپ نمی شود.
        sess: dict[str, Any] = {"mode_in_use": self._state.get("mode") or "هنوز تشخیص داده نشده"}
        try:
            await self._login()
            sess["login"] = "ok"
            sess["user"] = await self._api("user", relogin=False)
        except SmsBadSeed:
            sess["login"] = "Invalid seed (seed را سایت نمی شناسد)"
        except CanbosoError as exc:
            sess["login"] = f"خطا: {exc}"
        out["session"] = {"status": 200 if sess.get("login") == "ok" else 0, "body": sess}
        return out

    # ---------- خرید و پیگیری ----------
    async def _b_buy(self, service_id: str, cc: str, operator_id: str | None = None) -> dict:
        """(bearer) خرید یک شماره (با نوع/اپراتور دلخواه، وگرنه پیش فرض سایت). خروجی parse_number.

        - SmsOutOfStock: شماره ای نیست (قطعا خرید نشد)
        - CanbosoNoFunds: موجودی *ما* کم است (قطعا خرید نشد)
        - CanbosoError: قطعا خرید نشد (پول کاربر برمی گردد)
        - CanbosoUnknown: شاید خریده شده؛ دوباره فرستاده نمی شود
        فقط وقتی اتصال اصلا برقرار نشده (چیزی نرفته) یا ۴۲۹ آمده تکرار می شود.
        """
        body: dict[str, Any] = {"service_id": _id(service_id), "country": cc.upper()}
        if operator_id:
            body["operator_id"] = _id(operator_id)
        r: httpx.Response | None = None
        for attempt in range(3):
            await _pace()
            try:
                r = await self._http.post("/numbers", json=body, timeout=BUY_TIMEOUT)
            except httpx.ConnectError as exc:
                if attempt < 2:
                    await asyncio.sleep(2.0)
                    continue
                raise CanbosoError(f"ارتباط برقرار نشد: {type(exc).__name__}") from exc
            except Exception as exc:  # noqa: BLE001  (تایم اوت یا قطع وسط پاسخ: شاید خریده شده)
                raise CanbosoUnknown(f"پاسخ نرسید: {type(exc).__name__}") from exc
            if r.status_code == 429 and attempt < 2:
                wait = _retry_after(r, 3.0 * (attempt + 1))
                if wait <= MAX_WAIT:
                    await asyncio.sleep(wait)
                    continue
            break

        assert r is not None
        code, msg, err = r.status_code, _message(r), _error_code(r)
        if code == 429:
            raise CanbosoError("سرویس دهنده شلوغ است، چند دقیقه دیگر امتحان کن")
        if code >= 500:
            raise CanbosoUnknown(f"HTTP {code}: {msg}")
        if code in (401, 403):
            raise SmsBadSeed("seed نامعتبر است")
        if code == 402 or (code >= 400 and _no_funds(err, msg)):
            raise CanbosoNoFunds(msg)
        if code == 409 or (code >= 400 and _out_of_stock(err, msg)):
            raise SmsOutOfStock(msg)
        if code == 404:
            raise CanbosoError("سرویس یا کشور پیدا نشد")
        if code >= 400:
            raise CanbosoError(f"درخواست رد شد: {msg}")
        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            raise CanbosoUnknown("پاسخ قابل خواندن نبود") from exc
        if not isinstance(data, dict):
            raise CanbosoUnknown("پاسخ ناشناخته")
        if data.get("ok") is False:
            low = f"{data.get('error')} {data.get('message')}"
            if _no_funds("", low):
                raise CanbosoNoFunds(low[:200])
            if _out_of_stock("", low):
                raise SmsOutOfStock(low[:200])
            raise CanbosoError(str(data.get("message") or data.get("error") or "خرید انجام نشد")[:200])
        info = parse_number(data)
        # پاسخ 2xx بدون شناسه: خرید انجام شده ولی پیگیری ندارد → دست ادمین
        if not info["id"]:
            raise CanbosoUnknown("خرید انجام شد ولی شناسه شماره در پاسخ نبود")
        forget_balance()
        return info

    async def _b_poll(self, number_id: str) -> dict:
        """(bearer) وضعیت یک شماره (و کد پیامک اگر آمده). خروجی parse_number."""
        data = await self._get(f"/numbers/{number_id}")
        info = parse_number(data)
        info["id"] = info["id"] or str(number_id)
        return info

    async def _b_cancel(self, number_id: str) -> bool:
        """(bearer) لغو و برگشت پول. True یعنی لغو شد؛ SmsAlreadyReceived اگر پیامک آمده."""
        await _pace()
        try:
            r = await self._http.post(f"/numbers/{number_id}/cancel")
        except Exception as exc:  # noqa: BLE001
            raise CanbosoUnknown(f"پاسخ نرسید: {type(exc).__name__}") from exc
        if r.status_code in (401, 403):
            raise SmsBadSeed("seed نامعتبر است")
        if r.status_code == 409:
            raise SmsAlreadyReceived(_message(r))
        if r.status_code >= 500:
            raise CanbosoUnknown(f"HTTP {r.status_code}: {_message(r)}")
        if r.status_code >= 400:
            raise CanbosoError(f"لغو نشد: {_message(r)}")
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = {}
        if isinstance(data, dict) and data.get("ok") is False:
            raise CanbosoError(_message(r))
        forget_balance()
        return True


    # ═══════════ تشخیص روش اتصال و توزیع ═══════════

    async def _persist(self) -> None:
        if self._persist_cb:
            try:
                await self._persist_cb(self._state)
            except Exception:  # noqa: BLE001
                log.warning("ذخیره وضعیت اتصال SMSBurner نشد", exc_info=True)

    async def _mode(self) -> str:
        """bearer یا session. بار اول: اول Bearer، اگر ۴۰۱ داد ورود با seed (حساب های ساخته شده از سایت)."""
        m = self._state.get("mode")
        if m:
            return m
        if not self.configured:
            raise CanbosoError("seed تنظیم نشده")
        async with _AUTH_LOCK:
            m = self._state.get("mode")         # در همین فاصله کس دیگری تشخیص داده بود
            if m:
                return m
            try:
                await self._get("/account")
                m = "bearer"
            except SmsBadSeed:
                await self._login(locked=True)  # اگر seed واقعا نامعتبر باشد، همین جا SmsBadSeed بالا می رود
                m = "session"
            self._state["mode"] = m
            await self._persist()
            log.info("روش اتصال SMSBurner: %s", m)
            return m

    async def quote(self, service_id: str, cc: str, operator_id: str | None = None) -> float | None:
        """قیمت دلاری تازه (فقط bearer)؛ در روش نشست quote نداریم و None برمی گردد."""
        if not self.configured:
            raise CanbosoError("seed تنظیم نشده")
        if await self._mode() == "session":
            return None
        return await self._b_quote(service_id, cc, operator_id)

    async def buy(self, service_id: str, cc: str, operator_id: str | None = None) -> dict:
        if not self.configured:
            raise CanbosoError("seed تنظیم نشده")
        if await self._mode() == "session":
            return await self._s_buy(service_id, cc, operator_id)
        return await self._b_buy(service_id, cc, operator_id)

    async def poll(self, number_id: str) -> dict:
        if await self._mode() == "session":
            return await self._s_poll(number_id)
        return await self._b_poll(number_id)

    async def cancel(self, number_id: str) -> bool:
        if not self.configured:
            raise CanbosoError("seed تنظیم نشده")
        if await self._mode() == "session":
            return await self._s_cancel(number_id)
        return await self._b_cancel(number_id)

    # ═══════════ روش نشست کوکی (api.php) ═══════════

    async def _login(self, locked: bool = False) -> None:
        """POST /auth-api.php {action: login, seed}؛ کوکی در کلاینت و در وضعیت ذخیره می شود.

        چند درخواست همزمان که نشست منقضی شده را دیدند، فقط یک ورود انجام می دهند و بقیه همان کوکی تازه را
        برمی دارند (سقف سایت ۵ ورود در ۱۵ دقیقه است)."""
        if locked:
            return await self._login_locked()
        async with _AUTH_LOCK:
            return await self._login_locked()

    async def _login_locked(self) -> None:
        host = self._origin.split("://", 1)[-1].split("/", 1)[0]
        mine = {c.name: c.value for c in self._http.cookies.jar}
        if self._state.get("cookies") and mine != self._state["cookies"]:
            for name, value in self._state["cookies"].items():      # کس دیگری در همین فاصله وارد شد؛ کوکی تازه اش را بردار
                self._http.cookies.set(name, value, domain=host)
            return
        t = time.monotonic()
        _LOGINS[:] = [x for x in _LOGINS if t - x < 900]
        if len(_LOGINS) >= LOGIN_BUDGET:
            raise CanbosoError("ورود به SMSBurner موقتا محدود شده؛ چند دقیقه دیگر دوباره امتحان کن")
        _LOGINS.append(t)
        await _pace()
        try:
            r = await self._http.post(f"{self._origin}/auth-api.php", data={"action": "login", "seed": self._seed})
        except Exception as exc:  # noqa: BLE001
            raise CanbosoError(f"ارتباط برقرار نشد: {type(exc).__name__}") from exc
        if r.status_code == 429:
            raise CanbosoError("ورود به SMSBurner موقتا محدود شده؛ چند دقیقه دیگر دوباره امتحان کن")
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            data = {}
        if isinstance(data, dict) and data.get("success"):
            self._state["cookies"] = {c.name: c.value for c in self._http.cookies.jar}
            await self._persist()
            return
        err = str(data.get("error") or "") if isinstance(data, dict) else ""
        if r.status_code in (401, 403) or "seed" in err.lower() or not err:
            raise SmsBadSeed("seed نامعتبر است")
        raise CanbosoError(f"ورود ناموفق: {err[:120]}")

    async def _api(self, action: str, post: dict | None = None, relogin: bool = True) -> Any:
        """یک درخواست api.php با نشست؛ اگر «Login required» بود یک بار دوباره وارد می شود."""
        url = f"{self._origin}/api.php"
        for attempt in range(2):
            await _pace()
            try:
                if post is None:
                    r = await self._http.get(url, params={"action": action})
                else:
                    r = await self._http.post(url, params={"action": action}, json=post)
            except Exception as exc:  # noqa: BLE001
                raise CanbosoError(f"ارتباط برقرار نشد: {type(exc).__name__}") from exc
            if r.status_code == 429:
                wait = _retry_after(r, 5.0)
                if attempt == 0 and wait <= MAX_WAIT:
                    await asyncio.sleep(wait)
                    continue
                raise CanbosoError(f"سقف درخواست؛ {int(wait)} ثانیه دیگر")
            break
        if r.status_code >= 500:
            raise CanbosoError(f"HTTP {r.status_code}")
        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            raise CanbosoError("پاسخ قابل خواندن نبود") from exc
        if _login_required(data) and relogin:
            await self._login()
            return await self._api(action, post, relogin=False)
        return data

    async def _s_balance(self) -> dict | None:
        data = await self._api("user")
        amount = _num(data.get("balance")) if isinstance(data, dict) and data.get("logged_in") else None
        return None if amount is None else {"balance": amount, "currency": "USDT", "text": ""}

    async def _s_orders(self, force: bool = False) -> list[dict]:
        """۵۰ سفارش اخیر (با کدهای پیامک). چند سفارش منتظر کد یک درخواست را شریک می شوند (کش ۳ ثانیه)."""
        hit = _cache.get("orders")
        if not force and hit and time.monotonic() - hit[0] < 3.0:
            return hit[1]
        data = await self._api("orders")
        if not isinstance(data, list):
            raise CanbosoError(str((data or {}).get("error") if isinstance(data, dict) else data)[:150] or "پاسخ ناشناخته")
        _cache["orders"] = (time.monotonic(), data)
        return data

    @staticmethod
    def _s_info(o: dict) -> dict:
        code = o.get("sms_code")
        return {"id": str(o.get("id") or ""), "phone": norm_phone(o.get("phone_number")),
                "sms_code": str(code) if code not in (None, "") else "", "sms_text": "",
                "status": norm_status(o.get("status"), code), "price": _num(o.get("price")),
                "expires_at": "", "expires_in": None, "raw": o}

    async def _s_poll(self, number_id: str, force: bool = False) -> dict:
        for o in await self._s_orders(force=force):
            if isinstance(o, dict) and str(o.get("id")) == str(number_id):
                return self._s_info(o)
        raise SmsOrderNotFound("سفارش در ۵۰ سفارش اخیر SMSBurner پیدا نشد")

    async def _s_buy(self, service_id: str, cc: str, operator_id: str | None = None) -> dict:
        """خرید با api.php?action=buy. همان قواعد bearer: خرید مبهم هرگز دوباره فرستاده نمی شود."""
        body: dict[str, Any] = {"country": cc.lower(), "service_id": _id(service_id)}
        if operator_id:
            body["operator_id"] = _id(operator_id)
        relogged = False
        r: httpx.Response | None = None
        for attempt in range(4):
            await _pace()
            try:
                r = await self._http.post(f"{self._origin}/api.php", params={"action": "buy"}, json=body,
                                          timeout=BUY_TIMEOUT)
            except httpx.ConnectError as exc:
                if attempt < 3:
                    await asyncio.sleep(2.0)
                    continue
                raise CanbosoError(f"ارتباط برقرار نشد: {type(exc).__name__}") from exc
            except Exception as exc:  # noqa: BLE001  (تایم اوت یا قطع وسط پاسخ: شاید خریده شده)
                raise CanbosoUnknown(f"پاسخ نرسید: {type(exc).__name__}") from exc
            if r.status_code == 429 and attempt < 3:
                wait = _retry_after(r, 3.0 * (attempt + 1))
                if wait <= MAX_WAIT:
                    await asyncio.sleep(wait)
                    continue
            try:
                data = r.json()
            except Exception:  # noqa: BLE001
                data = None
            if _login_required(data) and not relogged:
                relogged = True             # خرید انجام نشده (وارد نبودیم)؛ وارد شو و دوباره بفرست
                await self._login()
                continue
            break
        assert r is not None
        code = r.status_code
        if code == 429:
            raise CanbosoError("سرویس دهنده شلوغ است، چند دقیقه دیگر امتحان کن")
        if code >= 500:
            raise CanbosoUnknown(f"HTTP {code}")
        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            raise CanbosoUnknown("پاسخ قابل خواندن نبود") from exc
        if not isinstance(data, dict):
            raise CanbosoUnknown("پاسخ ناشناخته")
        err = str(data.get("error") or "")
        if _login_required(data):
            raise SmsBadSeed("seed نامعتبر است")
        if err:
            if _no_funds("", err):
                raise CanbosoNoFunds(err[:200])
            if _out_of_stock("", err):
                raise SmsOutOfStock(err[:200])
            raise CanbosoError(err[:200])
        oid = data.get("order_id")
        if not data.get("success") or oid in (None, ""):
            raise CanbosoUnknown("خرید انجام شد ولی شناسه سفارش در پاسخ نبود" if data.get("success")
                                 else "پاسخ خرید نامشخص بود")
        forget_balance()
        info = {"id": str(oid), "phone": "", "sms_code": "", "sms_text": "", "status": "active",
                "price": _num(data.get("price")), "expires_at": "", "expires_in": None, "raw": data}
        try:
            # شماره ی تلفن در پاسخ خرید نیست؛ معمولا همین لحظه در فهرست سفارش ها هست
            got = await self._s_poll(str(oid), force=True)
            info.update({k: got[k] for k in ("phone", "sms_code", "status") if got.get(k)})
        except CanbosoError:
            pass                            # پایشگر چند ثانیه بعد شماره را می گیرد
        return info

    async def _s_cancel(self, number_id: str) -> bool:
        """لغو با api.php?action=cancel (POST). SmsAlreadyReceived اگر پیامک رسیده باشد."""
        body = {"order_id": _id(number_id), "id": _id(number_id)}
        relogged = False
        while True:
            await _pace()
            try:
                r = await self._http.post(f"{self._origin}/api.php", params={"action": "cancel"}, json=body)
            except Exception as exc:  # noqa: BLE001
                raise CanbosoUnknown(f"پاسخ نرسید: {type(exc).__name__}") from exc
            if r.status_code == 405:
                raise CanbosoError("لغو از مسیر API ممکن نیست")
            if r.status_code >= 500:
                raise CanbosoUnknown(f"HTTP {r.status_code}")
            try:
                data = r.json()
            except Exception:  # noqa: BLE001
                data = {}
            if _login_required(data) and not relogged:
                relogged = True
                await self._login()
                continue
            break
        err = str(data.get("error") or "") if isinstance(data, dict) else ""
        if err:
            low = err.lower()
            if any(w in low for w in ("sms", "received", "completed", "already")):
                raise SmsAlreadyReceived(err[:150])
            raise CanbosoError(f"لغو نشد: {err[:150]}")
        forget_balance()
        _cache.pop("orders", None)
        return True


def _id(service_id: str) -> Any:
    s = str(service_id)
    return int(s) if s.isdigit() else s


def _retry_after(r: httpx.Response, default: float) -> float:
    """مهلت ۴۲۹: هدر Retry-After، وگرنه retry_after داخل بدنه ی JSON سایت، وگرنه پیش فرض."""
    raw = r.headers.get("Retry-After")
    if raw and raw.replace(".", "", 1).isdigit():
        return float(raw)
    try:
        body = r.json()
        wait = _num(body.get("retry_after")) if isinstance(body, dict) else None
    except Exception:  # noqa: BLE001
        wait = None
    return max(0.5, wait) + 0.2 if wait else default


def forget_balance() -> None:
    _cache.pop("balance", None)
