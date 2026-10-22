"""اتصال به وب سرویس فروش عمده ssondigitalworks (Developer / Reseller API) برای خدمات هوش مصنوعی.

قرارداد (از مستند فروشنده):

    یک آدرس:  https://ssondigitalworks.online/api/reseller
    GET  ?action=products   فهرست محصولات
    GET  ?action=balance    موجودی کیف پول ما
    POST ?action=order      خرید، بدنه:
         {"product_id": "...", "quantity": 1, "external_order_id": "..."}
    هدر Authorization: Bearer <کلید>

- این API فقط قیمت عمده (هزینه ما) را از موجودی ما کم می کند؛ قیمت فروش
  به کاربر را خود ربات حساب می کند (app/pricing.py و سود هر محصول).
- external_order_id برای هر سفارش یکتاست و «تکرار با همان شناسه همان
  سفارش قبلی را برمی گرداند و دوباره پول کم نمی کند». پس مثل
  Idempotency-Key است: وقتی جواب نرسید، با همان شناسه دوباره می پرسیم و
  خرید تکراری نمی شود؛ سفارش مبهم هم بعدا با همان شناسه حل می شود.

این کلاس همان رابط Canboso را دارد (catalog، balance، purchase، debug،
close) و خروجی را به همان شکل برمی گرداند تا بقیه ربات (فروشگاه، مینی اپ،
پنل ادمین) بدون تغییر کار کند.

شکل دقیق فیلدهای پاسخ در مستند نیامده؛ برای همین نام های رایج هر فیلد
پذیرفته می شود و پاسخ خام از پنل ادمین («خروجی خام API») قابل دیدن است.
کلید هیچ وقت در لاگ نوشته نمی شود.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import httpx

from app.canboso import CanbosoError, CanbosoNoFunds, CanbosoUnknown, norm_currency

log = logging.getLogger("obour.sson")

BASE_URL = "https://ssondigitalworks.online/api/reseller"
NAME = "sson"
TITLE = "ssondigitalworks"
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


# شناسه ایموجی پریمیوم تلگرام که فروشنده در متن ها می گذارد، مثل
# «{pe:5415932912484779414} Gemini»؛ معمولا ایموجی معمولی بعدش هم آمده.
_PE_RE = re.compile(r"\{pe:\d+\}")


def clean_text(v: Any) -> str:
    """حذف {pe:...} و فاصله اضافه سر و ته هر خط."""
    text = _PE_RE.sub("", str(v or "")).replace("\r\n", "\n")
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def _unwrap(data: Any) -> Any:
    """بعضی API ها همه چیز را زیر data یا result می گذارند."""
    if isinstance(data, dict):
        for k in ("data", "result"):
            if isinstance(data.get(k), (dict, list)):
                return data[k]
    return data


# ═══════════════════ تبدیل به شکل canboso ═══════════════════


def normalize_product(p: dict, default_currency: str) -> dict | None:
    """یک محصول این API به همان شکلی که ai_shop از canboso انتظار دارد."""
    pid = _first(p, "product_id", "id", "productId", "code", "sku")
    if pid in (None, ""):
        return None
    price_raw = _first(p, "wholesale_price", "reseller_price", "price", "cost", "price_usd", "amount", "unit_price")
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
    # product_type فروشنده: link (لینک فعال سازی)، text (حساب یا کد متنی) یا null
    ptype = str(_first(p, "product_type", "type", "delivery_type") or "").lower()
    return {
        "productId": str(pid),
        "name": clean_text(_first(p, "name", "title", "product_name")) or f"#{pid}",
        "description": clean_text(_first(p, "description", "desc", "details", "note")),
        "productType": "account",
        "deliveryKind": "link" if ptype == "link" else "",
        "emoji": clean_text(_first(p, "category", "brand", "service")).lower().replace(" ", "_"),
        "image": str(image or ""),
        "price": {"amount": price, "currency": norm_currency(currency)},
        "availability": {"available": stock},
        "purchaseRequirements": {},
    }


_USER_KEYS = ("username", "user", "email", "login", "account")
_PASS_KEYS = ("password", "pass", "pwd")
_CONTENT_KEYS = ("content", "data", "code", "key", "license", "link", "url", "redeem_link", "activation_link",
                 "text", "value", "details", "delivery", "delivered", "item", "stock", "result")


def _is_meta(key: str) -> bool:
    """کلیدهایی که اطلاعات سفارش اند، نه محتوای تحویلی (شناسه، وضعیت، قیمت، زمان...)."""
    k = str(key).lower()
    return (k in _META_KEYS or k.endswith(("_id", "_at", "_date", "_time", "_price", "_amount", "_status", "_name"))
            or k.startswith(("is_", "has_")))


_META_KEYS = {
    "id", "ok", "success", "error", "errors", "message", "msg", "status", "state", "order_id", "orderid",
    "external_order_id", "product_id", "productid", "numeric_id", "slug", "name", "title", "product_name",
    "product", "quantity", "qty", "price", "unit_price", "total", "amount", "cost", "charged", "wholesale_price",
    "wholesale_total", "currency", "balance", "reseller", "user", "user_id", "customer", "created", "updated",
    "date", "time", "timestamp", "type", "product_type", "category", "description", "duplicate", "existing",
    "fulfillment", "fulfillment_status", "payment", "pricing", "meta", "note", "warranty", "count",
    # در سطح سفارش «code» معمولا کد سفارش است، نه کد فعال سازی
    "code", "order_code", "reference", "ref", "key",
}
# داخل یک قلم تحویلی، code و key همان کد فعال سازی اند
_ITEM_CONTENT = ("code", "key")


def _account_of(item: Any) -> dict:
    """یک قلم تحویلی به شکل حساب canboso (user، password، otherInfo ...)."""
    if isinstance(item, dict):
        user = _first(item, *_USER_KEYS)
        pw = _first(item, *_PASS_KEYS)
        rest = {k: v for k, v in item.items()
                if k not in _USER_KEYS + _PASS_KEYS and v not in (None, "", [], {})
                and (k in _ITEM_CONTENT or not _is_meta(k))}
        content = _first(rest, *_CONTENT_KEYS)
        if isinstance(content, (dict, list)):
            content = None
        if content is not None and not user and not pw:
            # فقط محتوا (لینک، کد یا متن حساب): همان قالب رشته ای
            inner = _account_of(str(content))
            extra = [f"{k}: {v}" for k, v in rest.items()
                     if k not in _CONTENT_KEYS and not isinstance(v, (dict, list))]
            if extra:
                inner["otherInfo"] = "\n".join(x for x in [inner.get("otherInfo", ""), *extra] if x)
            return inner
        other = [str(content)] if content is not None else []
        other += [f"{k}: {v}" for k, v in rest.items()
                  if k not in _CONTENT_KEYS and not isinstance(v, (dict, list))]
        return {"user": str(user or ""), "password": str(pw or ""), "otherInfo": "\n".join(other)}
    text = str(item or "").strip()
    if text.startswith(("http://", "https://")) and " " not in text:
        return {"user": text}
    # قالب رایج فروشنده: Email|Password|2FA (یا بیشتر)
    parts = [x.strip() for x in text.split("|")]
    if "\n" not in text and len(parts) >= 2 and parts[0] and parts[1] and " " not in parts[0]:
        return {"user": parts[0], "password": parts[1], "otherInfo": " | ".join(x for x in parts[2:] if x)}
    return {"otherInfo": text}


# جاهایی که محتوای تحویلی ممکن است باشد (به ترتیب)
_DELIVERY_KEYS = ("delivered", "delivery", "delivered_items", "deliverables", "items", "accounts", "credentials",
                  "codes", "keys", "licenses", "links", "link", "redeem_link", "activation_link", "url",
                  "content", "product_data", "data", "details", "result", "stock", "item", "text", "value")


def _delivered_of(d: dict) -> Any:
    for k in _DELIVERY_KEYS:
        v = d.get(k)
        if v in (None, "", [], {}) or isinstance(v, bool):
            continue
        if isinstance(v, dict):
            # مثل {"delivery": {"link": ...}}؛ دیکشنری بی محتوای شناخته شده رد می شود
            inner = _delivered_of(v)
            if inner is not None:
                return inner
            if any(x in v for x in _USER_KEYS + _PASS_KEYS):
                return v
            continue
        if isinstance(v, (int, float)):
            continue
        return v
    return None


def _scan(d: Any, depth: int = 0) -> list:
    """آخرین راه: هر متن غیر اطلاعات سفارش (شناسه، وضعیت، قیمت...) در پاسخ.

    شکل پاسخ سفارش در مستند فروشنده نیامده؛ اگر لینک یا کد زیر کلیدی آمد که
    نمی شناسیم، این طوری گم نمی شود.
    """
    out: list = []
    if depth > 3 or not isinstance(d, dict):
        return out
    for k, v in d.items():
        if _is_meta(k) or v in (None, "", [], {}) or isinstance(v, (bool, int, float)):
            continue
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str) and x.strip():
                    out.append(x)
                elif isinstance(x, dict):
                    out.append(x)
        elif isinstance(v, dict):
            out += _scan(v, depth + 1)
    return out


FAILED_STATES = ("failed", "cancelled", "canceled", "rejected", "refunded", "error")


def normalize_order(data: dict, product_id: str) -> dict:
    """پاسخ خرید به شکل canboso: order، payment و delivery.accounts."""
    src = _unwrap(data)
    src = src if isinstance(src, dict) else {}
    o = src.get("order") if isinstance(src.get("order"), dict) else src
    delivered = _delivered_of(o)
    if delivered is None and o is not src:
        delivered = _delivered_of(src)

    def accounts_from(items: Any) -> list[dict]:
        if isinstance(items, (str, dict)):
            items = [items]
        flat: list = []
        for x in items or []:
            lines = [ln.strip() for ln in x.splitlines() if ln.strip()] if isinstance(x, str) else []
            # چند لینک یا چند حساب «Email|Password» در یک متن: هر خط یک قلم
            if len(lines) > 1 and all(ln.startswith(("http://", "https://")) or "|" in ln for ln in lines):
                flat += lines
            else:
                flat.append(x)
        return [a for a in (_account_of(x) for x in flat) if any(a.values())]

    accounts = accounts_from(delivered)
    if not accounts:
        accounts = accounts_from(_scan(o) or (_scan(src) if o is not src else []))
    code = (_first(o, "order_id", "orderId", "id", "order_code", "code")
            or _first(src, "order_id", "orderId", "id"))
    amount = (_num(_first(o, "total", "amount", "cost", "price", "charged", "wholesale_total"))
              or _num(_first(src, "total", "amount", "cost", "charged")))
    return {
        "success": True,
        "order": {"orderCode": str(code or ""), "productId": str(product_id),
                  "externalOrderId": str(_first(o, "external_order_id") or ""),
                  "status": str(_first(o, "status", "state") or ("completed" if accounts else "processing"))},
        "payment": {"amount": amount} if amount is not None else {},
        "delivery": {"accounts": accounts},
        "raw": data,
    }


# ═══════════════════ کلاینت ═══════════════════


class Sson:
    name = NAME
    title = TITLE
    # external_order_id یکتا: تکرار همان سفارش دوباره خرید نمی کند
    idempotent = True

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._key = (api_key or "").strip()
        self.base_url = (base_url or BASE_URL).rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=TIMEOUT,
            headers={"Authorization": f"Bearer {self._key}", "Accept": "application/json"},
        )

    @property
    def configured(self) -> bool:
        return bool(self._key)

    async def close(self) -> None:
        await self._http.aclose()

    async def _get(self, action: str) -> Any:
        if not self.configured:
            raise CanbosoError("کلید API تنظیم نشده")
        for attempt in range(2):
            await _pace()
            try:
                r = await self._http.get(self.base_url, params={"action": action})
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
            if isinstance(data, dict) and (data.get("success") is False or data.get("ok") is False):
                raise CanbosoError(_message(r))
            return data
        raise CanbosoError("سرویس دهنده شلوغ است")

    # ---------- محصولات ----------
    async def catalog(self, force: bool = False) -> dict:
        global _products_cache
        if not force and _products_cache and time.monotonic() - _products_cache[0] < PRODUCTS_TTL:
            return _products_cache[1]
        data = await self._get("products")
        raw: Any = data
        if isinstance(data, dict):
            raw = data.get("products")
            if raw is None:
                raw = _unwrap(data)
            if isinstance(raw, dict):
                raw = raw.get("products") or raw.get("items") or raw.get("data") or []
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
        """موجودی ما نزد سرویس دهنده؛ اگر خوانده نشد None (بی سقف)."""
        global _balance_cache
        if not force and _balance_cache and time.monotonic() - _balance_cache[0] < BALANCE_TTL:
            return _balance_cache[1]
        out: dict | None = None
        try:
            data = await self._get("balance")
            src = _unwrap(data)
            # پاسخ واقعی: {"ok": true, "reseller": {"user_id": ..., "balance": 0.0}}
            for k in ("reseller", "wallet", "account", "user"):
                if isinstance(src, dict) and isinstance(src.get(k), dict):
                    src = src[k]
                    break
            amount = _num(_first(src, "balance", "amount", "credit", "wallet", "available")) if isinstance(src, dict) else None
            if amount is None and isinstance(data, dict):
                src = data
                amount = _num(_first(data, "balance", "amount", "credit", "wallet"))
            if amount is not None:
                out = {"balance": amount, "currency": norm_currency(src.get("currency") or "USD"), "text": ""}
        except CanbosoError as exc:
            log.info("موجودی سرویس دهنده خوانده نشد: %s", exc)
        _balance_cache = (time.monotonic(), out)
        return out

    async def debug(self) -> dict:
        """پاسخ خام products و balance برای پنل ادمین (بدون کش)."""
        out: dict[str, Any] = {}
        for action in ("products", "balance"):
            await _pace()
            started = time.monotonic()
            try:
                r = await self._http.get(self.base_url, params={"action": action})
                try:
                    body: Any = r.json()
                except Exception:  # noqa: BLE001
                    body = r.text[:2000]
                out[action] = {"status": r.status_code, "ms": int((time.monotonic() - started) * 1000), "body": body}
            except Exception as exc:  # noqa: BLE001
                out[action] = {"status": 0, "error": f"{type(exc).__name__}: {exc}"}
        return out

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
        """خرید. خروجی به شکل canboso (order، payment، delivery).

        idempotency_key همان external_order_id است.
        - CanbosoError: قطعا انجام نشد (پول کاربر برمی گردد)
        - CanbosoNoFunds: موجودی ما کم است (انجام نشد)
        - CanbosoUnknown: معلوم نیست؛ بعدا با همان شناسه دوباره پرسیده می شود
        چون شناسه یکتاست، جواب نرسیده با همان شناسه دوباره فرستاده می شود و
        اگر اولی انجام شده بود همان سفارش برمی گردد.
        """
        if not self.configured:
            raise CanbosoError("کلید API تنظیم نشده")
        if not idempotency_key:
            raise CanbosoError("شناسه سفارش خالی است")
        body: dict[str, Any] = {"product_id": str(product_id), "quantity": int(quantity),
                                "external_order_id": idempotency_key}
        if customer_email:
            body["email"] = customer_email

        maybe_sent = False      # آیا ممکن است درخواستی به مسیر خرید رسیده باشد؟
        r: httpx.Response | None = None
        for attempt in range(3):
            await _pace()
            try:
                r = await self._http.post(self.base_url, params={"action": "order"}, json=body,
                                          headers={"Content-Type": "application/json"})
            except httpx.ConnectError as exc:
                # اتصال برقرار نشد؛ این بار چیزی نرفت
                if attempt < 2:
                    await asyncio.sleep(2.0)
                    continue
                if maybe_sent:
                    raise CanbosoUnknown(f"پاسخ نرسید: {type(exc).__name__}") from exc
                raise CanbosoError(f"ارتباط برقرار نشد: {type(exc).__name__}") from exc
            except Exception as exc:  # noqa: BLE001  (تایم اوت یا قطع وسط پاسخ: شاید انجام شده)
                maybe_sent = True
                if attempt < 2:
                    await asyncio.sleep(2.0)
                    continue
                raise CanbosoUnknown(f"پاسخ نرسید: {type(exc).__name__}") from exc

            code = r.status_code
            if code == 429:
                raw = r.headers.get("Retry-After")
                wait = float(raw) if raw and raw.replace(".", "", 1).isdigit() else 3.0 * (attempt + 1)
                if attempt < 2 and wait <= MAX_WAIT:
                    await asyncio.sleep(wait)
                    continue
                if maybe_sent:
                    raise CanbosoUnknown("HTTP 429 بعد از تلاش مبهم")
                raise CanbosoError("سرویس دهنده شلوغ است، چند دقیقه دیگر امتحان کن")
            if code >= 500:
                maybe_sent = True
                if attempt < 2:
                    await asyncio.sleep(2.0)
                    continue
                raise CanbosoUnknown(f"HTTP {code}: {_message(r)}")
            break

        assert r is not None
        code = r.status_code
        if code == 409:
            # همان شناسه هنوز در حال انجام است یا قبلا ثبت شده؛ بعدا دوباره می پرسیم
            raise CanbosoUnknown(f"HTTP 409: {_message(r)}")
        if code >= 400:
            msg = _message(r)
            if maybe_sent:
                raise CanbosoUnknown(f"HTTP {code} بعد از تلاش مبهم: {msg}")
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
        if data.get("success") is False or data.get("ok") is False or (
                data.get("error") and _delivered_of(data) is None and not isinstance(data.get("order"), dict)):
            msg = _message(r)
            if _no_funds(msg):
                raise CanbosoNoFunds(msg[:200])
            raise CanbosoError(msg[:200] or "سفارش انجام نشد")
        forget_balance()
        out = normalize_order(data, str(product_id))
        if out["order"]["status"].lower() in FAILED_STATES and not out["delivery"]["accounts"]:
            raise CanbosoError(f"سفارش {out['order']['status']} شد")
        return out


def forget_balance() -> None:
    global _balance_cache
    _balance_cache = None
