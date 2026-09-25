"""کارهای دوره ای که روی هاست سی پنل باید با Cron اجرا شوند.

روی سرور اختصاصی این کارها داخل خود پروسه ربات انجام می شوند، ولی زیر
Passenger پروسه بعد از بیکاری خوابانده می شود، پس حلقه داخلی قابل اتکا نیست.

  python cron_tasks.py          پاکسازی + هشدار انقضا
  python cron_tasks.py --quiet  بدون چاپ خروجی (مناسب کران)

یا از راه وب (وقتی کران سی پنل کار نمی کند):
  https://DOMAIN/cron?key=ADMIN_KEY

پیشنهاد زمان بندی: هر ۱۵ دقیقه.
"""
from __future__ import annotations

import asyncio
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

from app import i18n
from app.config import config
from app.db import Database
from app.utils import esc

QUIET = "--quiet" in sys.argv


def say(msg: str) -> None:
    if not QUIET:
        print(msg)


async def send_receipt_reminders(db: Database) -> int:
    """یادآوری فیش برای کسانی که گفتند واریز کردم ولی رسید نفرستادند.

    شرط ها در pending_reminders بررسی می شود: بیش از ۱۰ دقیقه گذشته،
    رسید نیامده، لغو نکرده، و قبلا یادآوری نگرفته (فقط یک بار).
    """
    pending = await db.pending_reminders(minutes=10)
    if not pending:
        return 0

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from app import texts

    bot = Bot(
        config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    sent = 0
    try:
        for txn in pending:
            try:
                with i18n.using(i18n.lang_of(txn)):
                    await bot.send_message(
                        int(txn["telegram_id"]),
                        texts.RECEIPT_REMINDER.format(amount=f"{txn['amount']:,}"),
                    )
                sent += 1
            except Exception as exc:  # noqa: BLE001
                say(f"  یادآوری برای {txn['telegram_id']} نرفت: {exc}")
            finally:
                # چه رفت چه نرفت، دوباره تلاش نمی کنیم تا کاربر اسپم نشود
                await db.mark_reminded(txn["id"])
            await asyncio.sleep(0.05)  # رعایت محدودیت نرخ تلگرام
    finally:
        await bot.session.close()
    return sent


async def _open_bot():  # noqa: ANN202
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    bot = Bot(
        config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        from app.emoji_mw import EmojiOutgoingMiddleware

        bot.session.middleware(EmojiOutgoingMiddleware())
    except Exception:  # noqa: BLE001
        pass
    return bot


async def send_expiry_warnings(db: Database, days: int = 3) -> int:
    """هشدار نزدیک شدن انقضا. هر سرویس فقط یک بار."""
    items = await db.services_for_expiry_warning(days)
    if not items:
        return 0

    from app import keyboards, texts
    from app.utils import days_left

    bot = await _open_bot()
    sent = 0
    try:
        for s in items:
            left = max(1, days_left(s["expire_at"]))
            try:
                with i18n.using(i18n.lang_of(s)):
                    await bot.send_message(
                        int(s["telegram_id"]),
                        texts.warn_expire(
                            name=esc(s.get("first_name") or i18n.t("دوست من")),
                            service=esc(s.get("label") or f"{i18n.t('سرویس')} {s['id']}"),
                            days=left,
                        ),
                        reply_markup=keyboards.warn_kb(s["id"]),
                    )
                sent += 1
            except Exception as exc:  # noqa: BLE001
                say(f"  هشدار انقضا برای {s['telegram_id']} نرفت: {exc}")
            finally:
                await db.mark_warned(s["id"], "warn_expire_at")
            await asyncio.sleep(0.05)
    finally:
        await bot.session.close()
    return sent


async def send_data_warnings(db: Database, threshold: int = 80) -> int:
    """هشدار حجم رو به اتمام.

    مصرف واقعی از پنل خوانده می شود. اگر پنل در دسترس نباشد، این مرحله
    بی سروصدا رد می شود تا بقیه کارهای کرون انجام شود.
    """
    items = await db.active_services_for_check()
    if not items:
        return 0

    has_auth = bool(
        config.panel_api_key or (config.panel_username and config.panel_password)
    )
    if not (config.panel_base_url and has_auth):
        return 0

    from app import keyboards, texts
    from app.panel import Panel
    from app.utils import GIB, fmt_gb

    try:
        panel = Panel(config)
    except Exception:  # noqa: BLE001
        return 0

    bot = await _open_bot()
    sent = 0
    try:
        for s in items:
            try:
                u = await panel.get_user(s["panel_username"])
            except Exception:  # noqa: BLE001
                continue
            if not u or not getattr(u, "data_limit", None):
                continue
            used = getattr(u, "used_traffic", 0) or 0
            limit = u.data_limit or 0
            if limit <= 0:
                continue
            percent = int(used * 100 / limit)
            if percent < threshold:
                continue

            remaining = max(0, limit - used)
            try:
                with i18n.using(i18n.lang_of(s)):
                    await bot.send_message(
                        int(s["telegram_id"]),
                        texts.warn_data(
                            name=esc(s.get("first_name") or i18n.t("دوست من")),
                            service=esc(s.get("label") or f"{i18n.t('سرویس')} {s['id']}"),
                            percent=percent,
                            remaining=fmt_gb(remaining / GIB),
                        ),
                        reply_markup=keyboards.warn_kb(s["id"]),
                    )
                sent += 1
            except Exception as exc:  # noqa: BLE001
                say(f"  هشدار حجم برای {s['telegram_id']} نرفت: {exc}")
            finally:
                await db.mark_warned(s["id"], "warn_data_at")
            await asyncio.sleep(0.05)
    finally:
        await bot.session.close()
        await panel.close()
    return sent


async def snapshot_usage(db: Database) -> int:
    """ثبت عکس روزانه مصرف همه سرویس های فعال.

    عدد تجمعی پنل ذخیره می شود و اختلاف دو روز، مصرف آن روز را می دهد.
    اگر پنل در دسترس نباشد، بی سروصدا رد می شود.
    """
    items = await db.active_services_for_check()
    if not items:
        return 0

    has_auth = bool(
        config.panel_api_key or (config.panel_username and config.panel_password)
    )
    if not (config.panel_base_url and has_auth):
        return 0

    from datetime import datetime

    from app.panel import Panel
    from app.utils import TZ

    try:
        panel = Panel(config)
    except Exception:  # noqa: BLE001
        return 0

    day = datetime.now(TZ).strftime("%Y-%m-%d")
    saved = 0
    try:
        for s in items:
            try:
                u = await panel.get_user(s["panel_username"])
            except Exception:  # noqa: BLE001
                continue
            if not u:
                continue
            await db.record_usage(
                s["id"],
                day,
                getattr(u, "used_traffic", 0) or 0,
                getattr(u, "data_limit", None),
            )
            saved += 1
            await asyncio.sleep(0.02)  # فشار نیاوردن به پنل
    finally:
        await panel.close()
    return saved


async def send_winback(db: Database, days_after: int = 2) -> int:
    """پیام برگشت برای کسانی که سرویسشان تمام شده و برنگشته اند.

    یک کد تخفیف عمومی برگشت ساخته می شود (اگر نباشد) و در پیام می آید.
    """
    items = await db.services_for_winback(days_after)
    if not items:
        return 0

    from app import keyboards, texts

    code = "COMEBACK"
    if not await db.discount_by_code(code):
        # ۳۰ روز اعتبار و یک بار برای هر کاربر. قبلا بدون انقضا ساخته
        # می شد و یک کد تخفیف همیشگی روی همه خریدها باقی می ماند.
        from datetime import datetime, timedelta as _td

        from app.utils import TZ as _TZ

        expires = (datetime.now(_TZ) + _td(days=30)).isoformat(timespec="seconds")
        await db.create_discount(
            code, "percent", 10, per_user_limit=1, expires_at=expires
        )

    custom = await db.get_setting("winback_text", "")
    bot = await _open_bot()
    sent = 0
    try:
        for s in items:
            try:
                # متن دلخواه ادمین فقط برای فارسی زبان هاست؛ بقیه قالب
                # ترجمه شده را می گیرند.
                lang = i18n.lang_of(s)
                with i18n.using(lang):
                    await bot.send_message(
                        int(s["telegram_id"]),
                        texts.winback(
                            custom if lang == i18n.DEFAULT else "",
                            name=esc(s.get("first_name") or i18n.t("دوست من")), code=code
                        ),
                        reply_markup=keyboards.winback_kb(),
                    )
                sent += 1
            except Exception as exc:  # noqa: BLE001
                say(f"  پیام برگشت برای {s['telegram_id']} نرفت: {exc}")
            finally:
                await db.mark_warned(s["id"], "winback_at")
            await asyncio.sleep(0.05)
    finally:
        await bot.session.close()
    return sent


async def continue_broadcast(db: Database, budget: float = 40.0) -> str:
    """ادامه دادن ارسال همگانی ثبت شده.

    ارسال همگانی زیر Passenger در یک درخواست جا نمی شود، پس در جدول
    broadcast_jobs ثبت می شود و هر اجرای کران یک تکه اش را پیش می برد.
    اگر کاری در جریان نباشد، هزینه اش فقط یک کوئری است.
    """
    job = await db.active_broadcast()
    if not job:
        return "کاری در صف نیست"

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from app import broadcast

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        result = await broadcast.run_chunk(bot, db, budget=budget)
    finally:
        await bot.session.close()
    if not result:
        return "کاری در صف نیست"
    state = "تمام شد" if result.get("done") else "ادامه دارد"
    return f"{state} - {result['sent']} موفق، {result['blocked']} بلاک، {result['failed']} ناموفق"


async def main() -> None:
    db = Database(config.db_path)
    await db.connect()
    try:
        r = await send_receipt_reminders(db)
        say(f"یادآوری فیش: {r}")

        e = await send_expiry_warnings(db, config.warn_expire_days)
        say(f"هشدار انقضا: {e}")

        d = await send_data_warnings(db, config.warn_data_percent)
        say(f"هشدار حجم: {d}")

        w = await send_winback(db, config.winback_after_days)
        say(f"پیام برگشت: {w}")

        u = await snapshot_usage(db)
        say(f"عکس مصرف ثبت شد: {u}")

        n = await db.purge_expired_amounts()
        say(f"مبالغ رزرو منقضی پاک شد: {n}")

        # قفل های جامانده از پروسه هایی که وسط کار کشته شده اند
        lk = await db.purge_expired_locks()
        say(f"قفل های منقضی پاک شد: {lk}")

        m = await db.purge_old_support_links(days=30)
        say(f"نگاشت های قدیمی پشتیبانی پاک شد: {m}")

        # وضعیت های FSM رهاشده قدیمی تر از ۲ روز.
        # cutoff در پایتون ساخته می شود چون updated_at با آفست تهران ذخیره
        # شده و مقایسه با datetime('now') در SQLite اشتباه جواب می دهد.
        from datetime import timedelta

        from app.utils import now

        cutoff = (now() - timedelta(days=2)).isoformat(timespec="seconds")
        k = await db.execute("DELETE FROM fsm_state WHERE updated_at < ?", (cutoff,))
        say(f"وضعیت های رهاشده پاک شد: {k}")

        # ادامه ارسال همگانی نیمه کاره. عمدا قبل از مهر زمان است تا
        # اگر طول کشید، باز هم مهر ثبت شود.
        b = await continue_broadcast(db)
        say(f"ارسال همگانی: {b}")

        # مهر زمان آخرین اجرا. پنل ادمین و check_setup از همین می فهمند
        # کران زنده است یا نه - بدون این، خاموش بودن کران تا وقتی یک
        # کاربر شکایت نکند معلوم نمی شود.
        from app.utils import now_str

        await db.set_setting("last_cron_at", now_str())
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
