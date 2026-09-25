"""خرید سرویس — منطق مشترک ربات و مینی اپ.

ترتیب امن (همان ترتیبی که در ربات آزموده شده و عمدا تغییر نکرده):
  ۱. قفل گرفتن، تا دو خرید همزمان یک کاربر روی هم نیفتد
  ۲. ساخت کاربر روی پنل موفق شود
  ۳. بعد پول با کسر اتمیک کم شود
  ۴. اگر کسر شکست خورد، کاربر پنل حذف و خطای موجودی برگردد

چرا این ترتیب و نه برعکس؟ اگر اول پول کم شود و بعد ساخت پنل شکست
بخورد، کاربر پول داده و سرویس ندارد - و برگرداندنش دستی است. در
ترتیب فعلی بدترین حالت این است که یک کاربر روی پنل ساخته شود و
بلافاصله حذف شود؛ هیچ پولی جابه جا نشده.

این فایل عمدا هیچ متن فارسی قابل نمایش تولید نمی کند: خروجی یک کد
خطاست و لایه بالا تصمیم می گیرد چه چیزی به کاربر نشان دهد. همان خطا
در ربات یک پیام با کیبورد است و در مینی اپ یک JSON.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.panel import (
    PanelAmbiguous,
    PanelNameTaken,
    PanelSafeError,
    gb_bytes,
    sub_url_of,
)
from app.utils import after_days

if TYPE_CHECKING:
    from app.db import Database
    from app.panel import Panel

log = logging.getLogger("obour.purchase")


# کدهای خطا. لایه نمایش این ها را به متن ترجمه می کند.
PLAN_UNAVAILABLE = "plan_unavailable"   # پلن حذف یا غیرفعال شده
PANEL_BUSY = "panel_busy"               # پنل در دسترس نیست
LOCKED = "locked"                       # خرید دیگری از همین کاربر در جریان است
DUPLICATE = "duplicate"                 # همین درخواست قبلا ثبت شده (idem)
NAME_FAILED = "name_failed"             # نام یکتا روی پنل ساخته نشد
PANEL_ERROR = "panel_error"             # ساخت روی پنل شکست خورد
INSUFFICIENT = "insufficient"           # موجودی کافی نبود


@dataclass(slots=True)
class Discount:
    """کد تخفیفی که لایه بالا از قبل اعتبارسنجی کرده."""

    id: int
    code: str
    saved: int


@dataclass(slots=True)
class PurchaseResult:
    """نتیجه خرید. ok یعنی سرویس ساخته و تحویل شدنی است."""

    ok: bool
    error: str = ""
    service_id: int | None = None
    sub_url: str = ""
    panel_username: str = ""
    label: str = ""
    price: int = 0
    txn_id: int | None = None
    balance_after: int = 0
    plan: dict = field(default_factory=dict)
    discount_used: bool = False


async def _create_with_retry(
    db: "Database",
    panel: "Panel",
    user: dict,
    label: str,
    panel_username: str,
    **kwargs,  # noqa: ANN003
) -> tuple:
    """ساخت سرویس، با گرفتن نام تازه اگر نام گرفته شده بود.

    خروجی: (پاسخ پنل، نامی که واقعا ساخته شد). نام برگشتی حتما باید
    استفاده شود؛ اگر تلاش دوم با نام دیگری موفق شده باشد و ما نام اول
    را ذخیره کنیم، سرویس در دیتابیس با نام اشتباه ثبت می شود و تمدید و
    حذف بعدی سراغ کاربر دیگری می رود.

    بین بررسی آزاد بودن نام و ساخت واقعی یک فاصله زمانی هست؛ در آن
    فاصله ممکن است کس دیگری همان نام را بگیرد. تا سه بار نام بعدی
    امتحان می شود. اگر باز هم نشد، خطای امن بالا می رود و پول کسر
    نمی شود.
    """
    last: Exception | None = None
    tried: set[str] = set()
    for attempt in range(3):
        try:
            resp = await panel.create_service(username=panel_username, **kwargs)
            return resp, panel_username
        except PanelNameTaken as exc:
            last = exc
            tried.add(panel_username)
            log.warning(
                "نام %s روی پنل گرفته شده بود (تلاش %s)", panel_username, attempt + 1
            )
            # از تلاش دوم به بعد، نام دلخواه کاربر را رها می کنیم و به
            # الگوی خودکار obour_<آیدی>_<شماره> می رویم. اگر پنل یک نام
            # را رد کند ولی در GET آزاد نشانش بدهد (یکتایی غیرحساس به
            # حروف، کاربر حذف شده جامانده در ایندکس و...)، چسبیدن به
            # همان ریشه یعنی هر سه تلاش هدر می رود.
            desired = label if attempt == 0 else ""
            panel_username = await db.free_panel_username(
                user["telegram_id"],
                user["id"],
                desired,
                taken=panel.username_taken,
                exclude=tried,
            )
    raise last or PanelSafeError("نام آزاد روی پنل پیدا نشد")


async def purchase(
    db: "Database",
    panel: "Panel | None",
    user: dict,
    plan: dict | None,
    *,
    label: str = "",
    idem: str,
    discount: Discount | None = None,
) -> PurchaseResult:
    """خرید یک پلن. قفل، اعتبارسنجی و کل ترتیب امن اینجاست.

    idem کلید یکتایی این درخواست است. در ربات از آیدی کال بک ساخته
    می شود و در مینی اپ باید از یک شناسه یکتای همان درخواست بیاید.
    اگر تلگرام یا شبکه همان درخواست را دوباره بفرستد، خرید دوم ثبت
    نمی شود ولی خرید بعدیِ خود کاربر آزاد است.

    discount را لایه بالا از قبل اعتبارسنجی کرده و فقط مبلغ تخفیف را
    می دهد. دلیلش این است که اعتبارسنجی کد در ربات به وضعیت گفتگو گره
    خورده و در مینی اپ نمی خورد؛ ولی کسر و ثبت مصرفش باید در همین
    ترتیب امن بنشیند.
    """
    if not plan or not plan.get("is_active"):
        return PurchaseResult(False, PLAN_UNAVAILABLE)
    if panel is None:
        return PurchaseResult(False, PANEL_BUSY)

    # قفل: هر کاربر در هر لحظه فقط یک عملیات مالی.
    # دابل کلیک و خرید همزمان از دو دستگاه، هر دو اینجا متوقف می شوند.
    lock = f"pay:{user['id']}"
    if not await db.acquire_lock(lock):
        return PurchaseResult(False, LOCKED)
    try:
        return await _run(db, panel, user, plan, label, idem, discount)
    finally:
        await db.release_lock(lock)


async def _run(
    db: "Database",
    panel: "Panel",
    user: dict,
    plan: dict,
    label: str,
    idem: str,
    discount: Discount | None,
) -> PurchaseResult:
    """بدنه خرید، با فرض اینکه قفل گرفته شده."""
    saved = discount.saved if discount else 0
    # قیمت نهایی همان چیزی است که کاربر روی صفحه دیده
    price = max(0, plan["price"] - saved)

    txn_id = await db.insert_transaction(user["id"], "purchase", -price, idem_key=idem)
    if txn_id is None:
        return PurchaseResult(False, DUPLICATE)

    # ۱) نام یکتا و ساخت روی پنل
    try:
        panel_username = await db.free_panel_username(
            user["telegram_id"], user["id"], label, taken=panel.username_taken
        )
    except Exception:  # noqa: BLE001
        await db.fail_transaction(txn_id, "نام سرویس ساخته نشد")
        log.exception("free_panel_username failed for %s", user["telegram_id"])
        return PurchaseResult(False, NAME_FAILED, txn_id=txn_id)

    try:
        resp, panel_username = await _create_with_retry(
            db,
            panel,
            user,
            label,
            panel_username,
            data_bytes=gb_bytes(plan["data_gb"]),
            days=plan["duration_days"],
            note=f"obour tg:{user['telegram_id']} plan:{plan['id']}",
        )
    except PanelSafeError as exc:
        # مطمئنیم چیزی ساخته نشد -> لغو امن تراکنش
        await db.fail_transaction(txn_id, f"panel rejected: {exc}")
        log.error("panel create rejected for %s", user["telegram_id"], exc_info=True)
        return PurchaseResult(False, PANEL_ERROR, txn_id=txn_id)
    except PanelAmbiguous as exc:
        # شاید ساخته شده باشد. اول تایید بگیر، بعد تصمیم بگیر.
        log.error("panel create AMBIGUOUS for %s", panel_username, exc_info=True)
        try:
            created = await panel.get_user(panel_username)
        except Exception:  # noqa: BLE001
            created = None
        if created is None:
            await db.fail_transaction(txn_id, f"panel ambiguous, not created: {exc}")
            return PurchaseResult(False, PANEL_ERROR, txn_id=txn_id)
        resp = created  # واقعا ساخته شده بود -> ادامه عادی خرید

    # ۲) کسر اتمیک موجودی
    if price > 0 and not await db.atomic_debit(user["id"], price):
        await panel.remove(panel_username)
        await db.fail_transaction(txn_id, "موجودی کافی نبود")
        return PurchaseResult(False, INSUFFICIENT, txn_id=txn_id, price=price)

    if not await db.approve_purchase(txn_id):
        log.error("تراکنش %s در حالت pending نبود", txn_id)

    # ثبت مصرف کد تخفیف پس از قطعی شدن خرید
    discount_used = False
    if discount and saved:
        if await db.redeem_discount(discount.id, user["id"], plan["price"], saved):
            discount_used = True
        else:
            log.warning(
                "کد %s ثبت نشد (ظرفیت پر شد) txn=%s", discount.code, txn_id
            )
            discount_used = True  # کد مصرف شده تلقی می شود تا دوباره اعمال نشود

    # ۳) ثبت سرویس
    expire = after_days(plan["duration_days"])
    sub_url = sub_url_of(resp, panel.base_url)
    service_id = await db.insert_service(
        user_id=user["id"],
        plan_id=plan["id"],
        panel_username=panel_username,
        sub_url=sub_url,
        data_gb=plan["data_gb"],
        duration_days=plan["duration_days"],
        expire_at=expire.isoformat(timespec="seconds"),
    )
    if label:
        await db.set_service_label(service_id, user["id"], label)

    fresh = await db.get_user(user["id"])
    return PurchaseResult(
        ok=True,
        service_id=service_id,
        sub_url=sub_url,
        panel_username=panel_username,
        label=label,
        price=price,
        txn_id=txn_id,
        balance_after=int(fresh["balance"]) if fresh else 0,
        plan=plan,
        discount_used=discount_used,
    )
