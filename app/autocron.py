"""کران خودکار: اجرای کارهای دوره ای بدون نیاز به کران هاست.

مشکل چیست؟
روی خیلی از هاست های سی پنل، کران یا اصلا اجرا نمی شود یا با مسیر
اشتباه پایتون بی سروصدا شکست می خورد. نتیجه اش این است که هشدار حجم،
هشدار انقضا، یادآوری فیش و ادامه ارسال همگانی هیچ وقت انجام نمی شوند -
و بدتر، کسی هم متوجه نمی شود.

راه حل: خود ربات کارها را انجام می دهد.
هر بار که یک آپدیت از تلگرام می رسد (یعنی هر بار کسی با ربات کار
می کند)، بعد از اینکه **پاسخ کاربر داده شد**، نگاه می کنیم آیا از
آخرین اجرا به اندازه کافی گذشته یا نه. اگر گذشته باشد، یک دور از
کارها را با سقف زمانی کوتاه اجرا می کنیم.

چرا این جواب می دهد؟
یک ربات فروش همیشه ترافیک دارد؛ حتی چند کلیک در ساعت کافی است. اگر
ساعت ها هیچ کس کار نکند، هشدارها هم چند ساعت دیر می شوند - که برای
هشدار انقضای سه روزه اصلا مهم نیست.

این جایگزین کران است، نه رقیبش: اگر کران هاست یا پینگ بیرونی هم کار
کند، هر کدام زودتر رسید کار را انجام می دهد و بقیه رد می شوند (قفل
دیتابیس جلوی اجرای همزمان را می گیرد).
"""
from __future__ import annotations

import logging
import time

from app.config import config
from app.db import Database
from app.utils import now, now_str

log = logging.getLogger("obour.autocron")

# آخرین باری که در همین پروسه بررسی کردیم. جلوی کوئری زدن به ازای هر
# تک آپدیت را می گیرد - بدون این، در یک ربات شلوغ هر کلیک یک کوئری
# اضافه می ساخت.
_last_check = 0.0
_CHECK_GAP = 60.0  # ثانیه

# لحظه ای که این پروسه بالا آمد. زیر Passenger پروسه بعد از بیکاری
# کشته می شود و اولین کاربرِ بعدی هزینه راه اندازی دوباره را می دهد؛
# اگر همان لحظه یک دور کران هم اجرا کنیم، آن کاربر دو برابر معطل
# می شود. پس تا چند ثانیه اول عمر پروسه، کران خودکار اجرا نمی شود.
_started_at = time.monotonic()
_WARMUP = 45.0  # ثانیه


def _due_minutes() -> int:
    return max(5, config.autocron_minutes)


async def is_due(db: Database) -> bool:
    """آیا وقت اجرای دور بعدی رسیده؟"""
    last = await db.get_setting("last_cron_at", "")
    if not last:
        return True
    try:
        from datetime import datetime

        gap = (now() - datetime.fromisoformat(last)).total_seconds()
    except (ValueError, TypeError):
        return True
    return gap >= _due_minutes() * 60


async def maybe_run(bot, db: Database) -> None:  # noqa: ANN001
    """اگر وقتش رسیده، یک دور کارهای دوره ای را اجرا می کند.

    هر خطایی اینجا فقط لاگ می شود: این کار در حاشیه رسیدگی به آپدیت
    کاربر انجام می شود و هیچ وقت نباید تجربه او را خراب کند.
    """
    global _last_check

    if not config.autocron_enabled:
        return

    # پروسه تازه بالا آمده: بگذار اول کاربر جواب بگیرد
    if (time.monotonic() - _started_at) < _WARMUP:
        return

    # بررسی سبک در حافظه، قبل از هر کوئری
    if (time.monotonic() - _last_check) < _CHECK_GAP:
        return
    _last_check = time.monotonic()

    try:
        if not await is_due(db):
            return
        # قفل کوتاه تر از فاصله اجرا، تا اگر پروسه ای وسط کار مرد،
        # دور بعدی معطل نماند
        if not await db.acquire_lock("autocron", ttl_seconds=300):
            return
        try:
            await _run_round(bot, db)
        finally:
            await db.release_lock("autocron")
    except Exception:  # noqa: BLE001
        log.exception("اجرای خودکار کارهای دوره ای شکست خورد")


async def _run_round(bot, db: Database) -> None:  # noqa: ANN001
    """یک دور کامل، با سقف زمانی.

    ترتیب عمدی است: کارهایی که مستقیم به کاربر پیام می دهند اول
    می آیند، چون اگر بودجه زمانی تمام شد، بهتر است پاکسازی عقب بیفتد
    نه هشدار انقضای کسی.
    """
    import cron_tasks as tasks

    deadline = time.monotonic() + config.autocron_budget
    done: list[str] = []

    async def step(name: str, factory) -> None:  # noqa: ANN001
        """اجرای یک کار، اگر هنوز وقت مانده باشد.

        factory یک تابع بدون آرگومان است که کوروتین را *همان لحظه*
        می سازد. قبلا خود کوروتین پاس داده می شد و وقتی بودجه تمام شده
        بود، ساخته ولی هیچ وقت await نمی شد - که هم RuntimeWarning
        می داد و هم یعنی آن کار بی سروصدا رد می شد.
        """
        if time.monotonic() >= deadline:
            log.info("بودجه زمانی تمام شد، «%s» به دور بعد موکول شد", name)
            return
        try:
            result = await factory()
            if result:
                done.append(f"{name}={result}")
        except Exception:  # noqa: BLE001
            log.warning("کار دوره ای «%s» شکست خورد", name, exc_info=True)

    await step("یادآوری فیش", lambda: tasks.send_receipt_reminders(db))
    await step("هشدار انقضا", lambda: tasks.send_expiry_warnings(db, config.warn_expire_days))
    await step("هشدار حجم", lambda: tasks.send_data_warnings(db, config.warn_data_percent))
    await step("پیام برگشت", lambda: tasks.send_winback(db, config.winback_after_days))

    # ارسال همگانی نیمه کاره: با بات همین پروسه، نه یک نشست تازه
    if time.monotonic() < deadline:
        try:
            from app import broadcast

            remaining = max(5.0, deadline - time.monotonic())
            result = await broadcast.run_chunk(bot, db, budget=remaining)
            if result:
                done.append("ارسال همگانی")
        except Exception:  # noqa: BLE001
            log.warning("ادامه ارسال همگانی شکست خورد", exc_info=True)

    # پرداخت های کریپتو که دیر رسیده اند (بعد از بسته شدن مینی اپ یا ربات)
    from app.services import crypto

    await step("پرداخت کریپتو", lambda: crypto.scan(db, bot, force=True))
    await step("عکس مصرف", lambda: tasks.snapshot_usage(db))
    await step("پاکسازی مبالغ", lambda: db.purge_expired_amounts())
    await step("پاکسازی قفل ها", lambda: db.purge_expired_locks())

    # مهر زمان همیشه ثبت می شود، حتی اگر بودجه وسط کار تمام شده باشد؛
    # وگرنه دور بعدی بلافاصله دوباره شروع می شود و ربات کند می ماند.
    await db.set_setting("last_cron_at", now_str())
    log.info("کارهای دوره ای خودکار اجرا شد: %s", ", ".join(done) or "بدون تغییر")
