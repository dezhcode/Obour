"""تبدیل قیمت دلاری سرویس دهنده به قیمت تومانی برای کاربر.

چرا یک ماژول جدا؟ چون این حساس ترین بخش فروش خدمات واسط است: یک
اشتباه در فرمول یعنی فروش زیر قیمت تمام شده، و چون تحویل برگشت ناپذیر
است، ضرر قابل جبران نیست.

فرمول:
    پایه      = قیمت دلاری × نرخ دلار
    + سود     = پایه × درصد سود
    + کارمزد  = پایه × درصد کارمزد انتقال
    + حاشیه   = پایه × درصد حاشیه نوسان ارز
    → اگر سود ریالی از حداقل کمتر شد، حداقل اعمال می شود
    → رند رو به بالا به نزدیک ترین واحد

سود ثابت (ai_markup_toman):
اگر ادمین آن را بیشتر از صفر بگذارد، قیمت ساده می شود:
    قیمت کاربر = قیمت API به تومان + همین مبلغ ثابت (بعد رند رو به بالا)
و درصد سود، کارمزد، حاشیه نوسان و حداقل سود نادیده گرفته می شوند. یعنی
قیمت همیشه دقیقا همین مقدار (مثلا ۱۰۰، ۱۵۰ یا ۲۰۰ هزار تومان) از قیمت
محصول در API بالاتر است. صفر = برگشت به حالت درصدی.

چرا حاشیه نوسان جدا از سود؟
اگر همه را در یک عدد جمع کنی، وقتی دلار می پرد نمی فهمی سود واقعی ات
چقدر آب رفته. جدا بودنشان یعنی می شود گفت «۲۰٪ سود می خواهم و ۸٪ هم
سپر نوسان» و بعد دقیقا دید کدام یک دارد مصرف می شود.

نرخ دلار عمدا دستی است. سرویس های نرخ ارز برای ایران غیرقابل اتکا
هستند و یک عدد غلط یعنی فروش محصول به قیمت مفت؛ به جایش اگر نرخ کهنه
شود، داشبورد هشدار می دهد.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.db import Database

# کلید تنظیمات -> (عنوان فارسی، پیش فرض، توضیح)
FIELDS: dict[str, tuple[str, str, str]] = {
    "ai_usd_rate": ("نرخ دلار (تومان)", "0", "قیمت هر دلار به تومان"),
    "ai_markup_toman": ("سود ثابت (تومان)", "0",
                        "قیمت کاربر = قیمت API + همین مبلغ، مثلا 100000. صفر یعنی حالت درصدی"),
    "ai_profit_percent": ("درصد سود", "20", "سود خالص شما"),
    "ai_fee_percent": ("درصد کارمزد", "3", "کارمزد انتقال پول و درگاه"),
    "ai_buffer_percent": ("حاشیه نوسان ارز", "8", "سپر در برابر جهش نرخ"),
    "ai_min_profit": ("حداقل سود (تومان)", "20000", "کف سود روی هر فروش"),
    "ai_round_to": ("رند کردن به (تومان)", "1000", "قیمت نهایی رو به بالا رند می شود"),
}


@dataclass
class Breakdown:
    """ریز محاسبه یک قیمت - برای پیش نمایش در پنل ادمین."""

    usd: float
    rate: int
    base: int
    profit: int
    fee: int
    buffer: int
    final: int
    fixed: int = 0   # سود ثابت تومانی؛ صفر یعنی حالت درصدی

    @property
    def net_profit(self) -> int:
        """سود خالص: کارمزد و حاشیه هزینه اند، نه سود."""
        return self.final - self.base - self.fee


async def load(db: Database) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, (_title, default, _desc) in FIELDS.items():
        raw = await db.get_setting(key, default)
        try:
            out[key] = float(str(raw).replace(",", "") or default)
        except (TypeError, ValueError):
            out[key] = float(default)
    return out


def compute(usd: float, cfg: dict[str, float]) -> Breakdown:
    """قیمت نهایی تومانی از قیمت دلاری."""
    rate = int(cfg.get("ai_usd_rate") or 0)
    base = usd * rate
    step = int(cfg.get("ai_round_to") or 1) or 1

    # حالت سود ثابت: قیمت API + مبلغ ثابت، بدون درصدها
    fixed = int(cfg.get("ai_markup_toman") or 0)
    if fixed > 0:
        final = int(math.ceil((base + fixed) / step) * step)
        return Breakdown(usd=usd, rate=rate, base=int(base), profit=final - int(base),
                         fee=0, buffer=0, final=final, fixed=fixed)
    profit = base * (cfg.get("ai_profit_percent", 0) / 100)
    fee = base * (cfg.get("ai_fee_percent", 0) / 100)
    buffer_ = base * (cfg.get("ai_buffer_percent", 0) / 100)

    total = base + profit + fee + buffer_

    # کف سود: روی محصول ارزان، درصدها عدد کوچکی می شوند که حتی کارمزد
    # را هم پوشش نمی دهد
    min_profit = cfg.get("ai_min_profit", 0)
    if (total - base - fee) < min_profit:
        total = base + fee + min_profit

    final = int(math.ceil(total / step) * step)

    return Breakdown(
        usd=usd,
        rate=rate,
        base=int(base),
        profit=int(profit),
        fee=int(fee),
        buffer=int(buffer_),
        final=final,
    )


async def price_for(db: Database, usd: float) -> Breakdown:
    return compute(usd, await load(db))


def is_configured(cfg: dict[str, float]) -> bool:
    """بدون نرخ دلار هیچ قیمتی معنا ندارد."""
    return bool(cfg.get("ai_usd_rate"))


def explain(b: Breakdown) -> str:
    """ریز محاسبه، برای صفحه تنظیمات ادمین."""
    if b.fixed:
        return (
            "╮── 🧮 ریز قیمت (سود ثابت)\n"
            f"│   \u2068{b.usd:g}\u2069 دلار\n\n"
            f"├ قیمت API (× \u2068{b.rate:,}\u2069): \u2068{b.base:,}\u2069\n"
            f"├ سود ثابت: \u2068{b.fixed:,}\u2069\n\n"
            f"💰 قیمت کاربر: <b>\u2068{b.final:,}\u2069</b> تومان\n"
            f"╯─ سود شما: \u2068{b.net_profit:,}\u2069 تومان"
        )
    return (
        "╮── 🧮 ریز قیمت\n"
        f"│   \u2068{b.usd:g}\u2069 دلار\n\n"
        f"├ پایه (× \u2068{b.rate:,}\u2069): \u2068{b.base:,}\u2069\n"
        f"├ سود: \u2068{b.profit:,}\u2069\n"
        f"├ کارمزد: \u2068{b.fee:,}\u2069\n"
        f"├ حاشیه نوسان: \u2068{b.buffer:,}\u2069\n\n"
        f"💰 قیمت کاربر: <b>\u2068{b.final:,}\u2069</b> تومان\n"
        f"╯─ سود خالص شما: \u2068{b.net_profit:,}\u2069 تومان"
    )
