"""نظرسنجی با دکمه های خود ربات.

چرا نظرسنجی بومی تلگرام استفاده نشد؟
`sendPoll` در پیام همگانی برای *هر کاربر یک نظرسنجی جدا* می سازد. یعنی
هر نفر فقط رای خودش را می بیند و هیچ مجموع مشترکی وجود ندارد. با
دکمه های خودمان، رای ها در یک جدول جمع می شوند، می شود تفکیک کرد چه
کسی رای داده، و می شود نتیجه را به تفکیک «کاربر خریدار» و «بدون خرید»
دید - که برای تصمیم گیری خیلی ارزشمندتر از یک عدد کلی است.

(برای کانال، نظرسنجی بومی تلگرام مناسب تر است چون یک پست واحد است و
همه یک مجموع می بینند؛ آن مسیر جداست.)
"""
from __future__ import annotations

import logging

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db import Database
from app.keyboards import _add  # noqa: PLC2701

log = logging.getLogger("obour.polls")

BAR_LEN = 10


def poll_kb(
    poll: dict, options: list[dict], voted_option: int | None = None
) -> InlineKeyboardMarkup:
    """دکمه های گزینه ها.

    چیدمان افقی یعنی دو گزینه در هر ردیف. برای متن های کوتاه («بله»،
    «خیر») افقی تمیزتر است؛ برای گزینه های بلند، عمودی خواناتر.

    ایموجی پریمیوم: اگر متن گزینه با یکی از ایموجی های کاتالوگ شروع
    شود، _add خودش آن را به ایموجی سفارشی تبدیل می کند - همان مسیری
    که بقیه دکمه های ربات دارند.
    """
    kb = InlineKeyboardBuilder()
    for opt in options:
        mark = "✅ " if voted_option == opt["id"] else ""
        _add(
            kb,
            f"{mark}{opt['label']}"[:64],
            style=poll.get("style") or None,
            callback_data=f"pv:{poll['id']}:{opt['id']}",
        )
    per_row = 2 if poll.get("layout") == "horizontal" else 1
    kb.adjust(per_row)
    return kb.as_markup()


def render(poll: dict, results: list[dict], total: int, show_results: bool) -> str:
    """متن نظرسنجی. اگر نتیجه نمایش داده نشود، فقط سوال می ماند."""
    lines = [
        "╮── 📊 نظرسنجی",
        f"│   \u2068{poll['question']}\u2069",
        "",
    ]
    if not show_results:
        lines.append("یکی از گزینه ها رو انتخاب کن.")
        lines.append("╯─ نتیجه بعد از رای دادن نشون داده می شه.")
        return "\n".join(lines)

    for r in results:
        votes = int(r["votes"] or 0)
        pct = round(votes * 100 / total) if total else 0
        filled = round(pct * BAR_LEN / 100)
        bar = "█" * filled + "░" * (BAR_LEN - filled)
        lines.append(f"├ \u2068{r['label']}\u2069")
        lines.append(f"│  \u2068{bar}\u2069 \u2068{pct}\u2069٪ · \u2068{votes}\u2069 رای")
    lines.append("")
    lines.append(f"╯─ مجموع \u2068{total}\u2069 رای · می تونی رایت رو عوض کنی.")
    return "\n".join(lines)


async def view(db: Database, poll_id: int, user_id: int | None = None) -> tuple:
    """(متن، کیبورد) نظرسنجی برای نمایش به یک کاربر.

    اگر کاربر هنوز رای نداده و نظرسنجی روی «نمایش نتیجه بعد از رای»
    تنظیم شده باشد، اعداد پنهان می مانند - تا رای دیگران روی نظر او
    اثر نگذارد.
    """
    poll = await db.get_poll(poll_id)
    if not poll:
        return None, None
    options = await db.poll_options(poll_id)
    results = await db.poll_results(poll_id)
    total = sum(int(r["votes"] or 0) for r in results)

    voted = await db.user_poll_vote(poll_id, user_id) if user_id else None
    show = bool(poll["show_results"]) or voted is not None
    text = render(poll, results, total, show_results=show)
    return text, poll_kb(poll, options, voted)


def admin_report(poll: dict, results: list[dict], breakdown: list[dict]) -> str:
    """گزارش کامل برای ادمین، با تفکیک خریدار و غیرخریدار."""
    total = sum(int(r["votes"] or 0) for r in results)
    lines = [
        "╮── 📊 گزارش نظرسنجی",
        f"│   \u2068{poll['question']}\u2069",
        "",
        f"وضعیت: {'باز' if poll['is_open'] else 'بسته'} · مجموع \u2068{total}\u2069 رای",
        "",
    ]
    bd = {b["label"]: b for b in breakdown}
    for r in results:
        votes = int(r["votes"] or 0)
        pct = round(votes * 100 / total) if total else 0
        b = bd.get(r["label"], {})
        buyers = int(b.get("buyers") or 0)
        others = int(b.get("others") or 0)
        lines.append(f"├ \u2068{r['label']}\u2069 — \u2068{votes}\u2069 رای (\u2068{pct}\u2069٪)")
        lines.append(f"│  خریدار: \u2068{buyers}\u2069 · بدون خرید: \u2068{others}\u2069")
    lines.append("")
    lines.append("╯─ «خریدار» یعنی حداقل یک سرویس دارد.")
    return "\n".join(lines)
