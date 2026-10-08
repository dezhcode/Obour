"""اتصال به وب سرویس فروش عمده aitoolifystudio (Reseller API v1) برای خدمات هوش مصنوعی.

قرارداد:

    GET  {BASE}/products     فهرست محصولات   ← data.products
    POST {BASE}/order        خرید            بدنه {"product_id": عدد، "quantity": 1}
                                             ← result.delivered[0] محتوای محصول
    هدر Authorization: Bearer <کلید>

این کلاس همان رابط Canboso را دارد (catalog، balance، purchase، debug،
close) و خروجی را به همان شکل برمی گرداند تا بقیه ربات (فروشگاه، مینی اپ،
پنل ادمین) بدون تغییر کار کند.

تفاوت مهم با canboso: این API کلید یکتای خرید (Idempotency-Key) ندارد. پس
درخواستی که شاید به سرویس دهنده رسیده باشد **هیچ وقت دوباره فرستاده
نمی شود** (وگرنه ممکن است دوبار خرید شود)؛ سفارش مبهم می ماند تا ادمین
در پنل سرویس دهنده ببیند و دستی «برگشت پول» یا «تحویل شد» بزند.

شکل دقیق فیلدهای محصول در مستند نیامده؛ برای همین نام های رایج هر فیلد
پذیرفته می شود و پاسخ خام از پنل ادمین («خروجی خام») قابل دیدن است.
کلید هیچ وقت در لاگ نوشته نمی شود.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.canboso import CanbosoError, CanbosoNoFunds, CanbosoUnknown, norm_currency

log = logging.getLogger("obour.aitoolify")

BASE_URL = "https://bot.aitoolifystudio.io/api/reseller/v1"
NAME = "aitoolify"
TIMEOUT = 45.0
MIN_INTERVAL = 0.5
PRODUCTS_TTL = 60.0
BALANCE_TTL = 30.0
MAX_WAIT = 15.0

_last_call = 0.0
_rate_lock = asyncio.Lock()
_products_cache: tuple[float, dict] | None = None
_balance_cache: tuple[float, dict | None] | None = None


async def _pace() -> None:
    global _last_call
    async with _rate_lock:
        gap = time.monotonic() - _last_call
        if gap < MIN_INTERVAL:
            await asyncio.sleep(MIN_INTERVAL - gap)
        _last_call = time.monotonic()


def _first(d: dict, *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
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
        err = data.get("error")
        if isinstance(err, dict):
            err = err.get("message") or err.get("code")
        return str(err or data.get("message") or data.get("detail") or data)[:200]
    return str(data)[:200]


def _no_funds(msg: str) -> bool:
    low = msg.lower()
    return any(w in low for w in ("balance", "funds", "credit", "top up", "top-up"))


# ═══════════════════ تبدیل به شکل canboso ═══════════════════


def normalize_product(p: dict, default_currency: str) -> dict | None:
    """یک محصول این API به همان شکلی که ai_shop از canboso انتظار دارد."""
    pid = _first(p, "id", "product_id", "productId")
    if pid in (None, ""):
        return None
    price_raw = _first(p, "price", "reseller_price", "price_usd", "cost", "amount", "unit_price")
    currency = _first(p, "currency", "price_currency") or default_currency
    if isinstance(price_raw, dict):
        currency = price_raw.get("currency") or currency
        price_raw = _first(price_raw, "amount", "value", "usd")
    price = _num(price_raw)

    stock: int | None = None
    raw_stock = _first(p, "stock", "available", "quantity", "qty", "in_stock", "inStock", "count")
    if isinstance(raw_stock, bool):
        stock = None if raw_stock else 0
    elif _num(raw_stock) is not None:
        stock = max(0, int(_num(raw_stock) or 0))
    status = str(_first(p, "status", "state") or "").lower()
    if status in ("out_of_stock", "unavailable", "disabled", "inactive", "sold_out") or p.get("active") is False:
        stock = 0

    image = _first(p, "image", "image_url", "imageUrl", "icon", "logo", "thumbnail")
    return {
        "productId": str(pid),
        "name": str(_first(p, "name", "title", "product_name") or f"#{pid}"),
        "description": str(_first(p, "description", "desc", "details", "note") or ""),
        "productType": "account",
        "emoji": str(_first(p, "category", "brand", "service") or "").lower().replace(" ", "_"),
        "image": str(image or ""),
        "price": {"amount": price, "currency": norm_currency(currency)},
        "availability": {"available": stock},
        "purchaseRequirements": {},
    }


def _account_of(item: Any) -> dict:
    """یک قلم delivered به شکل حساب canboso (user، password، otherInfo ...)."""
    if isinstance(item, dict):
        user = _first(item, "username", "user", "email", "login", "account")
        pw = _first(item, "password", "pass", "pwd")
        rest = {k: v for k, v in item.items()
                if k not in ("username", "user", "email", "login", "account", "password", "pass", "pwd")
                and v not in (None, "", [], {})}
        content = _first(rest, "content", "data", "code", "key", "link", "url", "text", "value")
        other = [str(content)] if content is not None else []
        other += [f"{k}: {v}" for k, v in rest.items()
                  if k not in ("content", "data", "code", "key", "link", "url", "text", "value")
                  and not isinstance(v, (dict, list))]
        return {"user": str(user or ""), "password": str(pw or ""), "otherInfo": "\n".join(other)}
    text = str(item or "").strip()
    if text.startswith(("http://", "https://")) and " " not in text:
        return {"user": text}
    return {"otherInfo": text}


def normalize_order(data: dict, product_id: str) -> dict:
    """پاسخ خرید به شکل canboso: order، payment و delivery.accounts."""
    delivered = data.get("delivered")
    if delivered is None and isinstance(data.get("order"), dict):
        delivered = data["order"].get("delivered")
    if isinstance(delivered, (str, dict)):
        delivered = [delivered]
    accounts = [a for a in (_account_of(x) for x in (delivered or [])) if any(a.values())]
    o = data.get("order") if isinstance(data.get("order"), dict) else data
    code = _first(o, "order_id", "orderId", "id", "order_code", "code") or _first(data, "order_id", "id")
    amount = _num(_first(o, "total", "amount", "cost", "price", "charged")) or _num(_first(data, "total", "amount", "cost", "charged"))
    return {
        "success": True,
        "order": {"orderCode": str(code or ""), "productId": str(product_id),
                  "status": str(_first(o, "status") or ("completed" if accounts else "processing"))},
        "payment": {"amount": amount} if amount is not None else {},
        "delivery": {"accounts": accounts},
        "raw": data,
    }


# ═══════════════════ کلاینت ═══════════════════


class Aitoolify:
    name = NAME
    # کلید یکتای خرید ندارد: سفارش مبهم دوباره فرستاده نمی شود
    idempotent = False

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._key = (api_key or "").strip()
        self._http = httpx.AsyncClient(
            base_url=(base_url or BASE_URL).rstrip("/"), timeout=TIMEOUT,
            headers={"Authorization": f"Bearer {self._key}", "Accept": "application/json"},
        )

    @property
    def configured(self) -> bool:
        return bool(self._key)

    async def close(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str) -> Any:
        if not self.configured:
            raise CanbosoError("کلید API تنظیم نشده")
        for attempt in range(2):
            await _pace()
            try:
                r = await self._http.get(path)
            except Exception as exc:  # noqa: BLE001
                raise CanbosoError(f"ارتباط برقرار نشد: {type(exc).__name__}") from exc
            if r.status_code == 429:
                raw = r.headers.get("Retry-After")
                wait = float(raw) if raw and raw.replace(".", "", 1).isdigit() else 5.0
                if attempt == 0 and wait <= MAX_WAIT:
                    await asyncio.sleep(wait)
                    continue
                raise CanbosoError(f"سقف درخواست؛ {int(wait)} ثانیه دیگر")
            if r.status_code in (401, 403):
                raise CanbosoError("کلید API نامعتبر است")
            if r.status_code >= 400:
                raise CanbosoError(f"HTTP {r.status_code}: {_message(r)}")
            try:
                data = r.json()
            except Exception as exc:  # noqa: BLE001
                raise CanbosoError("پاسخ قابل خواندن نبود") from exc
            if isinstance(data, dict) and data.get("success") is False:
                raise CanbosoError(_message(r))
            return data
        raise CanbosoError("سرویس دهنده شلوغ است")

    # ---------- محصولات ----------
    async def catalog(self, force: bool = False) -> dict:
        global _products_cache
        if not force and _products_cache and time.monotonic() - _products_cache[0] < PRODUCTS_TTL:
            return _products_cache[1]
        data = await self._get("/products")
        raw = data.get("products") if isinstance(data, dict) else data
        if isinstance(raw, dict):
            raw = raw.get("items") or raw.get("data") or []
        cur = norm_currency((data.get("currency") if isinstance(data, dict) else None) or "USD")
        products = [n for n in (normalize_product(p, cur) for p in (raw or []) if isinstance(p, dict)) if n]
        out = {"currency": cur, "products": products}
        _products_cache = (time.monotonic(), out)
        return out

    async def product(self, product_id: str, force: bool = False) -> dict | None:
        for p in (await self.catalog(force=force))["products"]:
            if str(p.get("productId")) == str(product_id):
                return p
        return None

    async def balance(self, force: bool = True) -> dict | None:
        """موجودی ما نزد سرویس دهنده اگر API آن را بدهد؛ وگرنه None (بی سقف)."""
        global _balance_cache
        if not force and _balance_cache and time.monotonic() - _balance_cache[0] < BALANCE_TTL:
            return _balance_cache[1]
        out: dict | None = None
        try:
            data = await self._get("/balance")
            src = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
            amount = _num(_first(src, "balance", "amount", "credit", "wallet")) if isinstance(src, dict) else None
            if amount is not None:
                out = {"balance": amount, "currency": norm_currency(src.get("currency") or "USD"), "text": ""}
        except CanbosoError as exc:
            log.info("موجودی سرویس دهنده خوانده نشد: %s", exc)
        _balance_cache = (time.monotonic(), out)
        return out

    async def debug(self) -> dict:
        """پاسخ خام /products و /balance برای پنل ادمین (بدون کش)."""
        out: dict[str, Any] = {}
        for path in ("/products", "/balance"):
            await _pace()
            started = time.monotonic()
            try:
                r = await self._http.get(path)
                try:
                    body: Any = r.json()
                except Exception:  # noqa: BLE001
                    body = r.text[:2000]
                out[path] = {"status": r.status_code, "ms": int((time.monotonic() - started) * 1000), "body": body}
            except Exception as exc:  # noqa: BLE001
                out[path] = {"status": 0, "error": f"{type(exc).__name__}: {exc}"}
        return out

    # ---------- خرید ----------
    async def purchase(
        self,
        product_id: str,
        *,
        idempotency_key: str = "",
        quantity: int = 1,
        customer_email: str | None = None,
        slot_months: int | None = None,
    ) -> dict:
        """خرید. خروجی به شکل canboso (order، payment، delivery).

        - CanbosoError: قطعا انجام نشد (پول کاربر برمی گردد)
        - CanbosoNoFunds: موجودی ما کم است (انجام نشد)
        - CanbosoUnknown: شاید انجام شده؛ دوباره فرستاده نمی شود
        فقط وقتی اتصال اصلا برقرار نشده (چیزی نرفته) یا ۴۲۹ آمده، تکرار می شود.
        """
        if not self.configured:
            raise CanbosoError("کلید API تنظیم نشده")
        pid: Any = int(product_id) if str(product_id).isdigit() else str(product_id)
        body: dict[str, Any] = {"product_id": pid, "quantity": int(quantity)}
        if customer_email:
            body["email"] = customer_email
        r: httpx.Response | None = None
        for attempt in range(3):
            await _pace()
            try:
                r = await self._http.post("/order", json=body, headers={"Content-Type": "application/json"})
            except httpx.ConnectError as exc:
                if attempt < 2:
                    await asyncio.sleep(2.0)
                    continue
                raise CanbosoError(f"ارتباط برقرار نشد: {type(exc).__name__}") from exc
            except Exception as exc:  # noqa: BLE001  (تایم اوت یا قطع وسط پاسخ: شاید انجام شده)
                raise CanbosoUnknown(f"پاسخ نرسید: {type(exc).__name__}") from exc
            if r.status_code == 429 and attempt < 2:
                raw = r.headers.get("Retry-After")
                wait = float(raw) if raw and raw.replace(".", "", 1).isdigit() else 3.0 * (attempt + 1)
                if wait <= MAX_WAIT:
                    await asyncio.sleep(wait)
                    continue
            break

        assert r is not None
        code = r.status_code
        if code == 429:
            raise CanbosoError("سرویس دهنده شلوغ است، چند دقیقه دیگر امتحان کن")
        if code >= 500:
            raise CanbosoUnknown(f"HTTP {code}: {_message(r)}")
        if code >= 400:
            msg = _message(r)
            if code == 402 or _no_funds(msg):
                raise CanbosoNoFunds(msg)
            if code in (401, 403):
                raise CanbosoError("کلید API نامعتبر است")
            if code == 404:
                raise CanbosoError("محصول پیدا نشد")
            raise CanbosoError(f"درخواست رد شد: {msg}")
        try:
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            raise CanbosoUnknown("پاسخ قابل خواندن نبود") from exc
        if not isinstance(data, dict):
            raise CanbosoUnknown("پاسخ ناشناخته")
        if data.get("success") is False or (data.get("error") and not data.get("delivered")):
            msg = str(data.get("error") or data.get("message") or "")
            if _no_funds(msg):
                raise CanbosoNoFunds(msg[:200])
            raise CanbosoError(msg[:200] or "سفارش انجام نشد")
        forget_balance()
        return normalize_order(data, str(product_id))


def forget_balance() -> None:
    global _balance_cache
    _balance_cache = None
