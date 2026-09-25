"""اتصال به فروشگاه واسط (api.warzoneshop.in) برای خدمات هوش مصنوعی.

قرارداد API:
    POST /api/v1/order   {"service_id": "S_01", "quantity": 1}
      → {"success": true, "order_id": "ORD-...", "total_cost": 0.60,
         "new_balance": 41.55, "products": ["https://serviceactivation.google.com/..."]}
    GET  /api/v1/products   فهرست سرویس ها با قیمت و موجودی
    GET  /api/v1/balance    موجودی حساب ما نزد آن ها
    GET  /api/v1/orders     تاریخچه سفارش ها

احراز هویت با هدر X-API-Key. آن کلید می تواند موجودی را خرج کند، پس
مثل رمز با آن رفتار می شود: فقط در تنظیمات دیتابیس/env می ماند و هیچ
وقت در لاگ یا پیام نوشته نمی شود.

نکته حیاتی: تحویل **برگشت ناپذیر** است. وقتی لینک فعال سازی صادر شد،
دیگر نمی شود پسش گرفت. برای همین این ماژول هیچ وقت خودش سفارش را
دوباره تلاش نمی کند - تصمیم گیری درباره تکرار با لایه بالاتر است که
وضعیت سفارش را در دیتابیس دارد.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

log = logging.getLogger("obour.warzone")

BASE_URL = "https://api.warzoneshop.in/api/v1"
TIMEOUT = 25.0  # سفارش گاهی کند است؛ کوتاه تر یعنی ابهام بیشتر

# سرویس دهنده سقف ۳ درخواست در ثانیه به ازای هر IP دارد. چون همه
# درخواست های ربات از یک IP می روند، این سقف مشترک است - پس فاصله
# می گذاریم به جای اینکه منتظر ۴۲۹ بمانیم.
MIN_INTERVAL = 0.50      # ثانیه؛ عمدا بالاتر از 1/3 تا حاشیه داشته باشیم
PRODUCTS_TTL = 60.0      # کش فهرست محصولات

_last_call = 0.0
_rate_lock = asyncio.Lock()
_products_cache: tuple[float, list[dict]] | None = None


async def _pace() -> None:
    """فاصله انداختن بین درخواست ها تا به سقف نرخ نخوریم."""
    global _last_call
    async with _rate_lock:
        gap = time.monotonic() - _last_call
        if gap < MIN_INTERVAL:
            await asyncio.sleep(MIN_INTERVAL - gap)
        _last_call = time.monotonic()


class WarzoneError(Exception):
    """خطای عمومی سرویس دهنده."""


class WarzoneNoFunds(WarzoneError):
    """موجودی *ما* نزد سرویس دهنده کافی نیست.

    این با «موجودی کاربر کم است» فرق دارد: اینجا مشکل از حساب ماست و
    تا شارژ نشود، هیچ سفارشی از هیچ کاربری موفق نمی شود. پس علاوه بر
    برگرداندن پول کاربر، باید فروش متوقف و ادمین خبردار شود - وگرنه
    هر کاربر بعدی هم همین شکست را تجربه می کند.
    """


class WarzoneUnknown(WarzoneError):
    """نمی دانیم سفارش انجام شد یا نه (تایم اوت/قطع ارتباط).

    این حالت هرگز نباید با تلاش دوباره پاسخ داده شود: ممکن است سفارش
    اول موفق بوده و تکرارش یعنی دوبار پول دادن. باید دستی بررسی شود.
    """


def _retry_after(response, default: float) -> float:  # noqa: ANN001
    """مدت انتظار از هدر Retry-After، وگرنه مقدار پیش فرض."""
    raw = response.headers.get("Retry-After") if response is not None else None
    try:
        return max(float(raw), 0.5) if raw else default
    except (TypeError, ValueError):
        return default


class Warzone:
    def __init__(self, api_key: str) -> None:
        self._key = (api_key or "").strip()
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=TIMEOUT,
            headers={"Content-Type": "application/json"},
        )

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._key}

    async def close(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str, **params: Any) -> dict:
        if not self.configured:
            raise WarzoneError("کلید API تنظیم نشده")
        for attempt in range(3):
            await _pace()
            try:
                r = await self._http.get(path, headers=self._headers(), params=params)
            except Exception as exc:  # noqa: BLE001
                raise WarzoneError(f"ارتباط برقرار نشد: {exc}") from exc
            if r.status_code in (429, 503) and attempt < 2:
                # خواندن است، پس تلاش دوباره کاملا بی خطر است
                await asyncio.sleep(_retry_after(r, 1.5 * (attempt + 1)))
                continue
            if r.status_code == 401:
                raise WarzoneError("کلید API نامعتبر است")
            if r.status_code >= 400:
                raise WarzoneError(f"HTTP {r.status_code}: {r.text[:120]}")
            return r.json()
        raise WarzoneError("سرویس دهنده شلوغ است")

    async def products(self, force: bool = False) -> list[dict]:
        """فهرست سرویس ها.

        هر مورد: service_id, name, price, stock, orderable, pricing.
        توجه: وقتی سرویس ناموجود است price ممکن است null باشد - پس
        هیچ جا نباید بدون بررسی روی آن حساب باز کرد.
        """
        global _products_cache

        if not force and _products_cache:
            ts, cached = _products_cache
            if (time.monotonic() - ts) < PRODUCTS_TTL:
                return cached

        data = await self._get("/products")
        items = data.get("services") or data.get("products") or data.get("data") or []
        items = [i for i in items if isinstance(i, dict)]
        _products_cache = (time.monotonic(), items)
        return items

    async def product(self, service_id: str, force: bool = False) -> dict | None:
        for p in await self.products(force=force):
            if str(p.get("service_id")) == str(service_id):
                return p
        return None

    async def balance(self) -> float | None:
        # اندپوینت درست /me است، نه /balance
        try:
            data = await self._get("/me")
        except WarzoneError as exc:
            log.warning("خواندن موجودی نشد: %s", exc)
            return None
        for key in ("wallet_balance", "balance", "new_balance", "amount"):
            if key in data:
                try:
                    return float(data[key])
                except (TypeError, ValueError):
                    pass
        return None

    async def quote(self, service_id: str, quantity: int) -> float | None:
        """هزینه دلاری واقعی این تعداد.

        چرا نمی شود قیمت × تعداد حساب کرد؟ چون قیمت گذاری پلکانی است
        (pricing: "tiered")؛ سفارش دو تایی در نمونه رسمی ۱٫۲۰ می شود
        نه ۱٫۰۰. تنها مرجع درست، خود سرویس دهنده است.
        """
        # سرویس دهنده اندپوینت quote ندارد؛ قیمت از فهرست محصولات
        # خوانده می شود. برای تعداد ۱ دقیق است. برای تعداد بیشتر، اگر
        # پله های قیمت در خود محصول آمده باشد از آن استفاده می کنیم،
        # وگرنه ضرب می کنیم و هزینه واقعی در پاسخ سفارش (total_cost)
        # ثبت می شود.
        p = await self.product(service_id)
        if p and quantity > 1:
            tiers = p.get("tiers") or p.get("pricing_tiers")
            if isinstance(tiers, list):
                for t in sorted(tiers, key=lambda x: int(x.get("min_qty") or 0), reverse=True):
                    if quantity >= int(t.get("min_qty") or 0) and t.get("price"):
                        return float(t["price"]) * quantity
        if not p or p.get("price") in (None, ""):
            return None
        return float(p["price"]) * quantity

    async def order(self, service_id: str, quantity: int = 1) -> dict:
        """ثبت سفارش. خروجی شامل products (لینک های تحویل) است.

        سه نوع نتیجه:
        - موفق: dict با products
        - WarzoneError: قطعا انجام نشد (پول کاربر باید برگردد)
        - WarzoneUnknown: معلوم نیست (پول نباید خودکار برگردد؛ ادمین
          باید با order_id یا تاریخچه بررسی کند)
        """
        if not self.configured:
            raise WarzoneError("کلید API تنظیم نشده")
        payload = {"service_id": service_id, "quantity": int(quantity)}
        r = None

        # مستندات سرویس دهنده صریح است: «۴۲۹ و ۵۰۳ هیچ کدام به مسیر
        # خرید نرسیده اند» - یعنی تلاش دوباره روی این دو *امن* است و
        # خطر خرید تکراری ندارد. بقیه حالت ها هرگز تکرار نمی شوند.
        for attempt in range(3):
            await _pace()
            try:
                r = await self._http.post(
                    "/order", json=payload, headers=self._headers()
                )
            except (
                httpx.TimeoutException,
                httpx.ReadError,
                httpx.RemoteProtocolError,
            ) as exc:
                # درخواست رفته ولی جواب نگرفتیم: ممکن است سفارش ثبت شده
                # باشد. اینجا تکرار ممنوع است.
                raise WarzoneUnknown(f"پاسخ نرسید: {exc}") from exc
            except Exception as exc:  # noqa: BLE001
                raise WarzoneError(f"ارتباط برقرار نشد: {exc}") from exc

            if r.status_code in (429, 503) and attempt < 2:
                wait = _retry_after(r, 2.0 * (attempt + 1))
                log.info(
                    "سفارش با %s برگشت (تلاش %s) - %s ثانیه صبر",
                    r.status_code, attempt + 1, wait,
                )
                await asyncio.sleep(wait)
                continue
            break

        if r is None:
            raise WarzoneError("درخواستی فرستاده نشد")
        if r.status_code == 401:
            raise WarzoneError("کلید API نامعتبر است")
        if r.status_code in (429, 503):
            # بعد از سه تلاش هنوز شلوغ است - ولی *قطعا* خریدی نشده
            raise WarzoneError("سرویس دهنده شلوغ است، چند لحظه دیگر امتحان کن")
        if r.status_code in (400, 402, 409):
            # طبق مستندات: ۴۰۰ هرگز موجودی را کم نمی کند و موجودی انبار
            # را مصرف نمی کند - پس قطعا انجام نشده
            body = r.text[:200]
            if "insufficient" in body.lower() and "wallet" in body.lower():
                raise WarzoneNoFunds(body)
            raise WarzoneError(f"سفارش رد شد: {body[:120]}")
        if r.status_code >= 500:
            # سرور خطا داد - ممکن است بعد از ثبت سفارش باشد
            raise WarzoneUnknown(f"HTTP {r.status_code}")
        if r.status_code >= 400:
            raise WarzoneError(f"HTTP {r.status_code}: {r.text[:120]}")

        data = r.json()
        if not data.get("success"):
            raise WarzoneError(str(data.get("error") or data)[:150])
        if not data.get("products"):
            # موفق اعلام شده ولی چیزی تحویل نداده: مبهم است
            raise WarzoneUnknown("سفارش موفق بود ولی محصولی برنگشت")
        return data

    async def history(self, page: int = 1, limit: int = 20) -> dict:
        """تاریخچه سفارش ها - برای بررسی سفارش های مبهم."""
        return await self._get("/orders", page=page, limit=min(max(limit, 1), 200))

    async def find_order(self, provider_order_id: str, max_pages: int = 5) -> dict | None:
        """جستجوی یک سفارش مشخص در تاریخچه، برای وضعیت زنده.

        سرویس دهنده اندپوینت «یک سفارش» جدا ندارد، فقط فهرست صفحه بندی
        شده؛ پس صفحه به صفحه دنبالش می گردیم. سفارش های تازه اول فهرست
        هستند، پس معمولا همان صفحه اول کافی است.
        """
        for page in range(1, max_pages + 1):
            try:
                data = await self.history(page=page, limit=50)
            except WarzoneError:
                return None
            items = data.get("orders") or data.get("data") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                oid = str(item.get("order_id") or item.get("id") or "")
                if oid == str(provider_order_id):
                    return item
            total_pages = data.get("total_pages")
            if total_pages and page >= int(total_pages):
                break
        return None
