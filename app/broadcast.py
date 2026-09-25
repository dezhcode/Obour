"""ارسال همگانی تکه تکه و قابل ادامه.

چرا این طور؟
ارسال همگانی قبلا یک `asyncio.create_task` بود که از داخل درخواست
وبهوک شروع می شد. زیر Passenger این کار نمی کند: به محض اینکه پاسخ
درخواست برگردد، پروسه خوابانده (و گاهی کشته) می شود و تسک نصفه
می ماند. نتیجه اش همان چیزی بود که دیدی - پیام «در حال ارسال...» روی
صفحه می ماند و به کاربرها چیزی نمی رسید.

حالا کار در جدول `broadcast_jobs` ثبت می شود و هر بار که فرصتی هست
(همان درخواست ادمین، یا هر اجرای کران) یک تکه از آن پیش می رود. اگر
پروسه وسط کار بمیرد، دفعه بعد از همان جایی که بود ادامه پیدا می کند -
هیچ کاربری دو بار پیام نمی گیرد، چون مکان نما روی `users.id` است.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from app import texts
from app.db import Database

log = logging.getLogger("obour.broadcast")

BATCH = 25  # تعداد گیرنده در هر دور، بین دو بار ذخیره پیشرفت
GAP = 0.05  # فاصله بین پیام ها: حدود ۲۰ پیام در ثانیه


def markup_to_json(markup) -> str | None:  # noqa: ANN001
    """کیبورد را برای ذخیره در دیتابیس به JSON تبدیل می کند."""
    if markup is None:
        return None
    try:
        return markup.model_dump_json()
    except Exception:  # noqa: BLE001
        log.warning("تبدیل دکمه همگانی به JSON نشد", exc_info=True)
        return None


def markup_from_json(raw: str | None):  # noqa: ANN201
    if not raw:
        return None
    try:
        from aiogram.types import InlineKeyboardMarkup

        return InlineKeyboardMarkup.model_validate(json.loads(raw))
    except Exception:  # noqa: BLE001
        log.warning("بازسازی دکمه همگانی از JSON نشد", exc_info=True)
        return None


async def _send_one(bot, job: dict, target: int, markup) -> str:  # noqa: ANN001
    """ارسال به یک نفر. خروجی: sent | blocked | failed"""
    from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

    for attempt in range(3):
        try:
            if job["show_source"]:
                # forwardMessage دکمه نمی پذیرد؛ اگر دکمه تنظیم شده باشد
                # جدا زیرش فرستاده می شود.
                sent_msg = await bot.forward_message(
                    chat_id=target,
                    from_chat_id=job["src_chat_id"],
                    message_id=job["src_message_id"],
                )
                if markup is not None:
                    await bot.send_message(
                        target, "👆", reply_markup=markup, disable_notification=True
                    )
            else:
                sent_msg = await bot.copy_message(
                    chat_id=target,
                    from_chat_id=job["src_chat_id"],
                    message_id=job["src_message_id"],
                    reply_markup=markup,
                )
            if job["pin"]:
                try:
                    await bot.pin_chat_message(
                        chat_id=target,
                        message_id=sent_msg.message_id,
                        disable_notification=True,
                    )
                    return "pinned"
                except Exception:  # noqa: BLE001
                    pass  # کاربر اجازه پین نداده - ارسال که موفق بوده
            return "sent"
        except TelegramRetryAfter as exc:
            # اگر نادیده بگیریم، بقیه پیام ها هم رد می شوند
            await asyncio.sleep(exc.retry_after + 1)
        except TelegramForbiddenError:
            return "blocked"  # ربات را بلاک کرده یا اکانت پاک شده
        except Exception:  # noqa: BLE001
            if attempt == 2:
                log.warning("ارسال همگانی به %s نشد", target, exc_info=True)
                return "failed"
            await asyncio.sleep(1)
    return "failed"


async def run_chunk(bot, db: Database, budget: float = 20.0) -> dict | None:  # noqa: ANN001
    """یک تکه از ارسال فعال را پیش می برد.

    budget سقف زمانی به ثانیه است. وقتی تمام شد، همان جا متوقف می شویم
    و پیشرفت ذخیره می ماند تا دفعه بعد ادامه پیدا کند.

    خروجی: وضعیت کار، یا None اگر ارسال فعالی نباشد.
    """
    job = await db.active_broadcast()
    if not job:
        return None

    # قفل کوتاه: جلوی این را می گیرد که کران و درخواست ادمین همزمان
    # یک کار را پیش ببرند و پیام تکراری بفرستند. کوتاه است تا اگر
    # پروسه ای وسط کار مرد، خیلی زود آزاد شود.
    if not await db.acquire_lock(f"bc:{job['id']}", ttl_seconds=int(budget) + 30):
        log.info("تکه دیگری از ارسال %s در جریان است", job["id"])
        return job

    markup = markup_from_json(job.get("markup_json"))
    sent, failed, blocked, pinned = (
        job["sent"], job["failed"], job["blocked"], job["pinned"],
    )
    cursor = job["cursor_user_id"]
    deadline = time.monotonic() + budget
    done = False

    try:
        while time.monotonic() < deadline:
            targets = await db.broadcast_targets(cursor, BATCH)
            if not targets:
                done = True
                break

            for row in targets:
                result = await _send_one(bot, job, int(row["telegram_id"]), markup)
                if result == "pinned":
                    sent += 1
                    pinned += 1
                elif result == "sent":
                    sent += 1
                elif result == "blocked":
                    blocked += 1
                else:
                    failed += 1
                cursor = int(row["id"])
                await asyncio.sleep(GAP)
                if time.monotonic() >= deadline:
                    break

            await db.update_broadcast(job["id"], cursor, sent, failed, blocked, pinned)
            await _report(bot, job, sent + failed + blocked, job["total"], final=False)

        await db.update_broadcast(job["id"], cursor, sent, failed, blocked, pinned)
        if done:
            await db.finish_broadcast(job["id"], "done")
            await _report(
                bot, job, sent + failed + blocked, job["total"], final=True,
                sent=sent, blocked=blocked, failed=failed, pinned=pinned,
            )
            log.info(
                "ارسال همگانی %s تمام شد: %s موفق، %s بلاک، %s ناموفق",
                job["id"], sent, blocked, failed,
            )
    finally:
        await db.release_lock(f"bc:{job['id']}")

    return {**job, "sent": sent, "failed": failed, "blocked": blocked, "done": done}


async def _report(  # noqa: PLR0913
    bot,  # noqa: ANN001
    job: dict,
    progress: int,
    total: int,
    final: bool,
    sent: int = 0,
    blocked: int = 0,
    failed: int = 0,
    pinned: int = 0,
) -> None:
    """به روزرسانی پیام گزارش در چت ادمین. شکستش مهم نیست."""
    if not job.get("report_chat_id"):
        return
    if final:
        pin_line = f"📌 پین شده روی \u2068{pinned}\u2069 چت\n" if job["pin"] else ""
        text = texts.ADMIN_BROADCAST_DONE.format(
            sent=sent, blocked=blocked, failed=failed, pin_line=pin_line
        )
    else:
        text = texts.ADMIN_BROADCAST_PROGRESS.format(done=progress, total=total)
    try:
        await bot.edit_message_text(
            chat_id=job["report_chat_id"],
            message_id=job["report_message_id"],
            text=text,
        )
    except Exception:  # noqa: BLE001
        pass
