"""اتصال به canboso.com (Buyer API 2.1.0) برای خدمات هوش مصنوعی.

قرارداد (از مستند Swagger سرویس دهنده):

    GET  /api/v2/telegram-buyer/products?key=...   فهرست محصولات
    GET  /api/v2/telegram-buyer/balance?key=...    موجودی کیف پول ما
    POST /api/v2/telegram-buyer/purchase           خرید
         هدر Idempotency-Key (اجباری، یکتا برای هر خرید)
         بدنه {"key", "product_id", "quantity",
               "customer_email"?, "slot_months"?}

- کلید در پارامتر key می آید (نه هدر). با آن موجودی ما خرج می شود؛
  پس هیچ وقت در لاگ نوشته نمی شود.
- قیمت ها به ارز کیف پول است (walletCurrency: VND یا USD).
- انواع محصول: account (نام کاربری/رمز همان لحظه تحویل می شود)، slot
  (ایمیل مشتری لازم است و ممکن است فروشنده بعدا انجامش دهد)،
  upgrade_account. محصول ویژه slot_chatgpt_business ایمیل و تعداد ماه
  (slot_months از allowedMonths) می خواهد.
- Idempotency-Key: «تکرار همان درخواست با همان کلید، پاسخ اصلی را
  برمی گرداند». پس برخلاف سرویس دهنده قبلی، وقتی جواب نرسید می شود با
  همان کلید دوباره پرسید و خرید تکراری نمی شود. سفارش مبهم هم بعدا با
  همان کلید حل می شود.
- سقف ها در پنجره ۶۰ ثانیه: محصولات ۳۰، موجودی ۳۰، خرید ۶۰ درخواست به
  ازای هر کلید. ۴۲۹ با Retry-After می آید و تخلف تکراری مسدودی پلکانی
  (۱ دقیقه تا ۶ ساعت) دارد؛ هرگز پشت سر هم تکرار نمی کنیم.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

log = logging.getLogger("obour.canboso")

BASE_URL = "https://canboso.com/api/v2/telegram-buyer"
TIMEOUT = 30.0
MIN_INTERVAL = 0.5        # فاصله بین درخواست ها؛ خیلی زیر سقف ها
PRODUCTS_TTL = 60.0       # سقف ۳۰ در دقیقه برای محصولات: کش لازم است
MAX_WAIT = 15.0           # بیشتر از این برای Retry-After صبر نمی کنیم

_last_call = 0.0
_rate_lock = asyncio.Lock()
_products_cache: tuple[float, dict] | None = None


async def _pace() -> None:
    global _last_call
    async with _rate_lock:
        gap = time.monotonic() - _last_call
        if gap < MIN_INTERVAL:
            await asyncio.sleep(MIN_INTERVAL - gap)
        _last_call = time.monotonic()


class CanbosoError(Exception):
    """قطعا انجام نشد (پول کاربر باید برگردد)."""


class CanbosoNoFunds(CanbosoError):
    """موجودی *ما* نزد سرویس دهنده کافی نیست."""


class CanbosoUnknown(CanbosoError):
    """نمی دانیم خرید انجام شد یا نه. پول خودکار برنمی گردد؛ با همان
    Idempotency-Key بعدا دوباره پرسیده می شود."""


def _retry_after(r: httpx.Response | None, default: float) -> float:
    raw = r.headers.get("Retry-After") if r is not None else None
    try:
        return max(float(raw), 0.5) if raw else default
    except (TypeError, ValueError):
        return default


def _message(r: httpx.Response) -> str:
    try:
        data = r.json()
        return str(data.get("message") or data.get("code") or data)[:200]
    except Exception:  # noqa: BLE001
        return r.text[:200]


class Canboso:
    def __init__(self, api_key: str) -> None:
        self._key = (api_key or "").strip()
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT)

    @property
    def configured(self) -> bool:
        return bool(self._key)

    async def close(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str) -> dict:
        if not self.configured:
            raise CanbosoError("کلید API تنظیم نشده")
        for attempt in range(2):
            await _pace()
            try:
                r = await self._http.get(path, params={"key": self._key})
            except Exception as exc:  # noqa: BLE001
                raise CanbosoError(f"ارتباط برقرار نشد: {type(exc).__name__}") from exc
            if r.status_code == 429:
                wait = _retry_after(r, 5.0)
                if attempt == 0 and wait <= MAX_WAIT:
                    await asyncio.sleep(wait)
                    continue
                raise CanbosoError(f"سقف درخواست؛ {int(wait)} ثانیه دیگر")
            if r.status_code == 401:
                raise CanbosoError("کلید API نامعتبر است")
            if r.status_code >= 400:
                raise CanbosoError(f"HTTP {r.status_code}: {_message(r)}")
            data = r.json()
            if not data.get("success", True):
                raise CanbosoError(str(data.get("message") or data)[:200])
            return data
        raise CanbosoError("سرویس دهنده شلوغ است")

    # ---------- محصولات ----------
    async def catalog(self, force: bool = False) -> dict:
        """{"currency": "VND"|"USD", "products": [...]} با کش ۶۰ ثانیه."""
        global _products_cache
        if not force and _products_cache and time.monotonic() - _products_cache[0] < PRODUCTS_TTL:
            return _products_cache[1]
        data = await self._get("/products")
        out = {
            "currency": str(data.get("walletCurrency") or "").upper(),
            "products": [p for p in (data.get("products") or []) if isinstance(p, dict) and p.get("productId")],
        }
        _products_cache = (time.monotonic(), out)
        return out

    async def product(self, product_id: str, force: bool = False) -> dict | None:
        for p in (await self.catalog(force=force))["products"]:
            if str(p.get("productId")) == str(product_id):
                return p
        return None

    async def balance(self) -> dict | None:
        """{"balance": عدد به ارز کیف پول، "currency": ...} یا None."""
        try:
            data = await self._get("/balance")
        except CanbosoError as exc:
            log.warning("خواندن موجودی canboso نشد: %s", exc)
            return None
        try:
            return {"balance": float(data.get("balance") or 0),
                    "currency": str(data.get("walletCurrency") or "").upper(),
                    "text": data.get("balanceText") or ""}
        except (TypeError, ValueError):
            return None

    # ---------- خرید ----------
    async def purchase(
        self,
        product_id: str,
        *,
        idempotency_key: str,
        quantity: int = 1,
        customer_email: str | None = None,
        slot_months: int | None = None,
    ) -> dict:
        """خرید. خروجی: پاسخ کامل موفق (order، payment، delivery).

        - CanbosoError: قطعا انجام نشد
        - CanbosoNoFunds: موجودی ما کم است (انجام نشد)
        - CanbosoUnknown: معلوم نیست؛ با همان idempotency_key بعدا دوباره صدا بزن

        چون Idempotency-Key داریم، جواب نرسیده را با همان کلید دوباره
        می پرسیم: اگر اولی انجام شده بود همان پاسخ برمی گردد و خرید
        تکراری نمی شود.
        """
        if not self.configured:
            raise CanbosoError("کلید API تنظیم نشده")
        body: dict[str, Any] = {"key": self._key, "product_id": str(product_id), "quantity": int(quantity)}
        if customer_email:
            body["customer_email"] = customer_email
        if slot_months:
            body["slot_months"] = int(slot_months)
        headers = {"Idempotency-Key": idempotency_key}

        maybe_sent = False      # آیا ممکن است درخواستی به مسیر خرید رسیده باشد؟
        r: httpx.Response | None = None
        for attempt in range(3):
            await _pace()
            try:
                r = await self._http.post("/purchase", json=body, headers=headers)
            except httpx.ConnectError as exc:
                # اتصال برقرار نشد؛ این بار چیزی نرفت
                if attempt < 2:
                    await asyncio.sleep(2.0)
                    continue
                if maybe_sent:
                    raise CanbosoUnknown(f"پاسخ نرسید: {type(exc).__name__}") from exc
                raise CanbosoError(f"ارتباط برقرار نشد: {type(exc).__name__}") from exc
            except Exception as exc:  # noqa: BLE001  (تایم اوت، قطع وسط پاسخ)
                maybe_sent = True
                if attempt < 2:
                    await asyncio.sleep(2.0)
                    continue
                raise CanbosoUnknown(f"پاسخ نرسید: {type(exc).__name__}") from exc

            code = r.status_code
            if code in (429, 503):
                # ۴۲۹: سقف نرخ؛ ۵۰۳: «محافظ خرید موقتا در دسترس نیست».
                # هیچ کدام خرید را انجام نداده اند.
                wait = _retry_after(r, 3.0 * (attempt + 1))
                if attempt < 2 and wait <= MAX_WAIT:
                    await asyncio.sleep(wait)
                    continue
                if maybe_sent:
                    raise CanbosoUnknown(f"HTTP {code} بعد از تلاش مبهم")
                raise CanbosoError("سرویس دهنده شلوغ است، چند دقیقه دیگر امتحان کن")
            if code == 409:
                msg = _message(r)
                if "progress" in msg.lower():
                    # همین خرید (همین کلید) هنوز در حال انجام است
                    maybe_sent = True
                    if attempt < 2:
                        await asyncio.sleep(3.0)
                        continue
                    raise CanbosoUnknown(f"هنوز در حال انجام: {msg}")
                if maybe_sent:
                    raise CanbosoUnknown(f"HTTP 409 بعد از تلاش مبهم: {msg}")
                raise CanbosoError(f"موجودی محصول کافی نیست: {msg}")
            if code >= 500:
                maybe_sent = True
                if attempt < 2:
                    await asyncio.sleep(2.0)
                    continue
                raise CanbosoUnknown(f"HTTP {code}")
            break

        assert r is not None
        code = r.status_code
        if code == 400:
            msg = _message(r)
            low = msg.lower()
            if "balance" in low and ("not enough" in low or "insufficient" in low):
                raise CanbosoNoFunds(msg)
            raise CanbosoError(f"درخواست رد شد: {msg}")
        if code == 401:
            raise CanbosoError("کلید API نامعتبر است")
        if code == 404:
            raise CanbosoError("محصول پیدا نشد")
        if code >= 400:
            raise CanbosoError(f"HTTP {code}: {_message(r)}")
        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            raise CanbosoUnknown("پاسخ قابل خواندن نبود") from exc
        if not data.get("success"):
            raise CanbosoError(str(data.get("message") or data)[:200])
        if not isinstance(data.get("order"), dict):
            raise CanbosoUnknown("پاسخ موفق بدون اطلاعات سفارش")
        return data


def accounts_of(result: dict) -> list[dict]:
    """حساب های تحویل شده از پاسخ خرید (ممکن است خالی باشد)."""
    delivery = result.get("delivery") or {}
    return [a for a in (delivery.get("accounts") or []) if isinstance(a, dict)]


def is_waiting(result: dict) -> bool:
    """سفارش پذیرفته شده ولی فروشنده بعدا انجامش می دهد (مثل slot)."""
    order = result.get("order") or {}
    status = str(order.get("status") or "").lower()
    fulfil = str(order.get("fulfillmentStatus") or "").lower()
    return bool((status and status != "completed") or fulfil.startswith("waiting") or (
        not accounts_of(result) and order.get("autoCompleted") is False
    ))
