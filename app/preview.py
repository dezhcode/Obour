"""خدمات پیش نمایش: شماره مجازی و ویزا کارت مجازی.

فروش این دو هنوز باز نشده؛ مینی اپ از همین جا کشورها، نوع کارت ها و
قیمت های تقریبی را نشان می دهد و کاربر می تواند «خبرم کن» بزند. قیمت ها به
تتر (USDT) اند و با نرخ تتر عبور به تومان هم نشان داده می شوند؛ چون هنوز
خریدی انجام نمی شود «تقریبی» علامت خورده اند. دستیار هوشمند هم برای جواب
دادن درباره این خدمات همین داده را می خواند (knowledge).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db import Database

KINDS = ("number", "visa")
TITLES = {"number": "شماره مجازی", "visa": "ویزا کارت"}

NUMBERS: dict = {
    "title": "شماره مجازی",
    "sub": "شماره خارجی برای کد تایید تلگرام، واتساپ، گوگل و سایت‌ها",
    "services": [
        {"key": "telegram", "title": "تلگرام", "icon": "send"},
        {"key": "whatsapp", "title": "واتساپ", "icon": "chat"},
        {"key": "google", "title": "گوگل و جیمیل", "icon": "globe"},
        {"key": "instagram", "title": "اینستاگرام", "icon": "camera"},
        {"key": "openai", "title": "ChatGPT", "icon": "spark"},
        {"key": "other", "title": "سایر سایت‌ها", "icon": "grid"},
    ],
    # once: یک بار مصرف (یک کد)، rent: اجاره 30 روزه؛ هر دو به تتر
    "countries": [
        {"code": "US", "flag": "🇺🇸", "title": "آمریکا", "once": 0.9, "rent": 7.5},
        {"code": "GB", "flag": "🇬🇧", "title": "انگلیس", "once": 0.8, "rent": 6.5},
        {"code": "CA", "flag": "🇨🇦", "title": "کانادا", "once": 0.8, "rent": 6.5},
        {"code": "DE", "flag": "🇩🇪", "title": "آلمان", "once": 1.1, "rent": 8.0},
        {"code": "NL", "flag": "🇳🇱", "title": "هلند", "once": 1.0, "rent": 7.5},
        {"code": "FR", "flag": "🇫🇷", "title": "فرانسه", "once": 1.0, "rent": 7.5},
        {"code": "TR", "flag": "🇹🇷", "title": "ترکیه", "once": 0.6, "rent": 5.0},
        {"code": "ID", "flag": "🇮🇩", "title": "اندونزی", "once": 0.4, "rent": 3.5},
    ],
    "kinds": [
        {"key": "once", "title": "یک‌بار مصرف", "sub": "برای گرفتن یک کد تایید؛ اگر کد نیاید مبلغ کامل برمی‌گردد"},
        {"key": "rent", "title": "اجاره 30 روزه", "sub": "شماره یک ماه مال توست و هر چند بار بخواهی کد می‌گیری"},
    ],
    "steps": [
        "کشور و سرویسی که کد تایید برایش لازم است را انتخاب کن",
        "مبلغ از کیف پول عبور کم و شماره همان لحظه نشان داده می‌شود",
        "کد تایید در مینی اپ و ربات برایت می‌آید",
    ],
}

VISA: dict = {
    "title": "ویزا کارت مجازی",
    "sub": "پرداخت آنلاین بین‌المللی؛ اشتراک‌ها، اپ‌استور و خریدهای خارجی",
    # issue: هزینه صدور، topup_pct: کارمزد هر شارژ (درصد)، min_topup: کمترین شارژ؛ همه به تتر
    "cards": [
        {"key": "lite", "title": "کارت یک‌بار مصرف", "sub": "برای یک خرید یا یک اشتراک؛ بعد از استفاده بسته می‌شود",
         "issue": 3, "topup_pct": 4, "min_topup": 5, "valid": "3 ماه", "tone": "net"},
        {"key": "plus", "title": "کارت شارژی", "sub": "هر وقت خواستی شارژش کن؛ مناسب اشتراک‌های ماهانه",
         "issue": 8, "topup_pct": 3, "min_topup": 10, "valid": "1 سال", "tone": "ai", "best": True},
        {"key": "pro", "title": "کارت حرفه‌ای", "sub": "سقف بالاتر و کارمزد کمتر برای خریدهای بیشتر",
         "issue": 15, "topup_pct": 2, "min_topup": 25, "valid": "2 سال", "tone": "cash"},
    ],
    "works": ["ChatGPT و OpenAI", "Google Play", "App Store", "Spotify", "Netflix", "Amazon",
              "Canva", "Midjourney", "سرورهای ابری", "دامنه و هاست"],
    "features": [
        {"icon": "shield", "title": "فقط برای خودت", "sub": "شماره کارت و CVV فقط در حساب خودت نمایش داده می‌شود"},
        {"icon": "wallet", "title": "شارژ با تتر یا کیف پول", "sub": "تومان کیف پول به تتر تبدیل و روی کارت می‌نشیند"},
        {"icon": "lock", "title": "قفل موقت", "sub": "هر وقت خواستی کارت را قفل یا باز کن"},
        {"icon": "list", "title": "گزارش تراکنش‌ها", "sub": "هر پرداخت کارت در مینی اپ ثبت می‌شود"},
    ],
    "steps": [
        "نوع کارت را انتخاب کن و هزینه صدور از کیف پول کم می‌شود",
        "کارت چند دقیقه بعد با شماره، تاریخ و CVV آماده است",
        "با تتر شارژش کن و در هر سایت خارجی پرداخت کن",
    ],
}


async def waitlist(db: "Database", user_id: int) -> dict[str, dict]:
    out = {}
    for kind in KINDS:
        row = await db.fetchone("SELECT COUNT(*) AS n FROM soon_waitlist WHERE kind = ?", (kind,))
        mine = await db.fetchone("SELECT 1 FROM soon_waitlist WHERE kind = ? AND user_id = ?", (kind, user_id))
        out[kind] = {"count": int(row["n"] if row else 0), "joined": bool(mine)}
    return out


async def join(db: "Database", user_id: int, kind: str, on: bool = True) -> bool:
    from app.utils import now_str

    if kind not in KINDS:
        return False
    if on:
        await db.execute("INSERT OR IGNORE INTO soon_waitlist(user_id, kind, created_at) VALUES (?,?,?)",
                         (user_id, kind, now_str()))
    else:
        await db.execute("DELETE FROM soon_waitlist WHERE user_id = ? AND kind = ?", (user_id, kind))
    return True


async def counts(db: "Database") -> dict[str, int]:
    rows = await db.fetchall("SELECT kind, COUNT(*) AS n FROM soon_waitlist GROUP BY kind")
    return {r["kind"]: int(r["n"]) for r in rows}


async def announce(bot, db: "Database", kind: str) -> int:  # noqa: ANN001
    """«فعال شد» به همه منتظران یک خدمت، هر کس به زبان خودش؛ بعد فهرست خالی می شود."""
    from app import i18n, keyboards, texts

    rows = await db.fetchall(
        """SELECT u.telegram_id, u.lang FROM soon_waitlist w JOIN users u ON u.id = w.user_id
           WHERE w.kind = ?""", (kind,))
    sent = 0
    for row in rows:
        try:
            with i18n.using(i18n.lang_of(dict(row))):
                text = texts.SOON_LIVE.format(title=i18n.t(TITLES[kind]))
                kb = keyboards.soon_live_kb(kind)
                await bot.send_message(int(row["telegram_id"]), text, reply_markup=kb)
            sent += 1
        except Exception:  # noqa: BLE001
            pass
    await db.execute("DELETE FROM soon_waitlist WHERE kind = ?", (kind,))
    return sent


async def public(db: "Database", user_id: int) -> dict:
    from app import pricing

    try:
        rate = int(pricing.rate_for(await pricing.load(db), "USDT") or 0)
    except Exception:  # noqa: BLE001
        rate = 0
    return {"usdt_rate": rate, "number": NUMBERS, "visa": VISA, "waitlist": await waitlist(db, user_id)}


def knowledge() -> str:
    """خلاصه متنی برای دستیار هوشمند."""
    c = ", ".join(f"{x['title']} (یک‌بار {x['once']} / اجاره {x['rent']} تتر)" for x in NUMBERS["countries"])
    v = "; ".join(f"{x['title']}: صدور {x['issue']} تتر، کارمزد شارژ {x['topup_pct']}٪، اعتبار {x['valid']}"
                  for x in VISA["cards"])
    return ("شماره مجازی (پیش‌نمایش، فروش هنوز باز نشده؛ قیمت‌ها تقریبی): " + c + ". "
            "ویزا کارت مجازی (پیش‌نمایش، صدور هنوز باز نشده؛ قیمت‌ها تقریبی): " + v + ". "
            "کاربر با «خبرم کن» در مینی اپ در فهرست انتظار ثبت می‌شود.")
