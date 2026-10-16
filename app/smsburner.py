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

نکته مهم: خرید کلید یکتا (Idempotency-Key) ندارد. پس خریدی که شاید به
سرویس دهنده رسیده باشد (قطع وسط پاسخ، ۵xx) **هیچ وقت دوباره فرستاده
نمی شود** و CanbosoUnknown بالا می رود؛ ادمین آن را دستی می بندد.

شکل دقیق پاسخ خرید و پیگیری در مستند نیامده؛ برای همین نام های رایج
هر فیلد پذیرفته می شود و پاسخ خام از پنل ادمین («خروجی خام») دیده
می شود. خطاها همان خطاهای canboso اند تا بقیه ربات یک رفتار ببیند.
"""
from __future__ import annotations

import asyncio
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
MIN_INTERVAL = 0.4          # فاصله حداقل بین دو درخواست این پروسه
CATALOG_TTL = 60.0
BALANCE_TTL = 30.0
MAX_WAIT = 15.0
# پنجره تحویل هر شماره نزد سرویس دهنده (دقیقه)
VALID_MINUTES = 20

_last_call = 0.0
_rate_lock = asyncio.Lock()
_cache: dict[str, tuple[float, Any]] = {}


# نوع اپراتور: virtual (VoIP، ارزان، ممکنه بعضی سرویس ها رد کنن)، physical (سیم کارت واقعی)،
# premium (سریع ترین، حدود ۱۰ ثانیه، بیشترین موفقیت)
OP_TYPES = ("virtual", "physical", "premium")


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
            "country": str(_first(r, "country_name", "country_title") or cc.upper()),
            "price": price,
            "stock": None if stock is None else max(0, int(stock)),
        })
    return out


class SmsBurner:
    name = NAME
    # خرید کلید یکتا ندارد: خرید مبهم دوباره فرستاده نمی شود
    idempotent = False

    def __init__(self, seed: str, base_url: str | None = None, proxy: str = "") -> None:
        self._seed = (seed or "").strip()
        base = (base_url or BASE_URL).rstrip("/")
        # ریشه سایت (برای مسیر قدیمی api.php که فهرست اپراتورها را دارد)
        self._origin = base.split("/api/")[0] if "/api/" in base else base
        kw: dict[str, Any] = {"proxy": proxy} if proxy.startswith(("http", "socks")) else {}
        self._http = httpx.AsyncClient(
            base_url=base, timeout=TIMEOUT,
            headers={"Authorization": f"Bearer {self._seed}", "Accept": "application/json"}, **kw,
        )

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
                raise CanbosoError("seed نامعتبر است")
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
    async def catalog(self, force: bool = False) -> list[dict]:
        """ردیف های (سرویس × کشور) با قیمت دلاری. بدون seed هم کار می کند."""
        return normalize_rows(await self._cached("catalog", CATALOG_TTL, force, "/catalog"))

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

    async def quote(self, service_id: str, cc: str, operator_id: str | None = None) -> float | None:
        """قیمت دلاری تازه برای یک سرویس و کشور (و اپراتور)؛ None اگر پاسخ قابل فهم نبود."""
        if not self.configured:
            raise CanbosoError("seed تنظیم نشده")
        await _pace()
        body: dict[str, Any] = {"service_id": _id(service_id), "country": cc.upper()}
        if operator_id:
            body["operator_id"] = _id(operator_id)
        try:
            r = await self._http.post("/quote", json=body)
        except Exception as exc:  # noqa: BLE001
            raise CanbosoError(f"ارتباط برقرار نشد: {type(exc).__name__}") from exc
        if r.status_code in (401, 403):
            raise CanbosoError("seed نامعتبر است")
        if r.status_code == 409 or (r.status_code == 404):
            raise SmsOutOfStock(_message(r))
        if r.status_code >= 400:
            return None
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
            data = await self._get("/account")
            src = _unwrap(data)
            for k in ("account", "user", "wallet"):
                if isinstance(src.get(k), dict):
                    src = src[k]
                    break
            amount = _num(_first(src, "balance", "balance_usd", "amount", "credit")) \
                if src else None
            if amount is None:
                amount = _num(_first(data, "balance", "balance_usd", "credit"))
            if amount is not None:
                out = {"balance": amount, "currency": norm_currency(_first(src, "currency") or "USD"), "text": ""}
        except CanbosoError as exc:
            log.info("موجودی سرویس دهنده خوانده نشد: %s", exc)
        _cache["balance"] = (time.monotonic(), out)
        return out

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
        return out

    # ---------- خرید و پیگیری ----------
    async def buy(self, service_id: str, cc: str, operator_id: str | None = None) -> dict:
        """خرید یک شماره (با نوع/اپراتور دلخواه، وگرنه پیش فرض سایت). خروجی parse_number.

        - SmsOutOfStock: شماره ای نیست (قطعا خرید نشد)
        - CanbosoNoFunds: موجودی *ما* کم است (قطعا خرید نشد)
        - CanbosoError: قطعا خرید نشد (پول کاربر برمی گردد)
        - CanbosoUnknown: شاید خریده شده؛ دوباره فرستاده نمی شود
        فقط وقتی اتصال اصلا برقرار نشده (چیزی نرفته) یا ۴۲۹ آمده تکرار می شود.
        """
        if not self.configured:
            raise CanbosoError("seed تنظیم نشده")
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
            raise CanbosoError("seed نامعتبر است")
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

    async def poll(self, number_id: str) -> dict:
        """وضعیت یک شماره (و کد پیامک اگر آمده). خروجی parse_number."""
        data = await self._get(f"/numbers/{number_id}")
        info = parse_number(data)
        info["id"] = info["id"] or str(number_id)
        return info

    async def cancel(self, number_id: str) -> bool:
        """لغو و برگشت پول. True یعنی لغو شد؛ SmsAlreadyReceived اگر پیامک آمده."""
        if not self.configured:
            raise CanbosoError("seed تنظیم نشده")
        await _pace()
        try:
            r = await self._http.post(f"/numbers/{number_id}/cancel")
        except Exception as exc:  # noqa: BLE001
            raise CanbosoUnknown(f"پاسخ نرسید: {type(exc).__name__}") from exc
        if r.status_code in (401, 403):
            raise CanbosoError("seed نامعتبر است")
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


def _id(service_id: str) -> Any:
    s = str(service_id)
    return int(s) if s.isdigit() else s


def _retry_after(r: httpx.Response, default: float) -> float:
    raw = r.headers.get("Retry-After")
    return float(raw) if raw and raw.replace(".", "", 1).isdigit() else default


def forget_balance() -> None:
    _cache.pop("balance", None)
