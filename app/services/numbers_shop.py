"""فروش شماره مجازی (SMSBurner) — مستقل از رابط.

سرویس دهنده: app/smsburner.py. هر خرید یک شماره یک بار مصرف است که تا ۲۰
دقیقه کد پیامک می گیرد؛ اگر کد نیاید پول کامل برمی گردد.

ترتیب خرید عمدی است (مثل ai_shop):

    ۱. قفل کاربر
    ۲. قیمت و موجودی تازه (بدون کش) از سرویس دهنده
    ۳. موجودی *ما* نزد سرویس دهنده بررسی می شود
    ۴. کسر اتمیک از کیف پول کاربر
    ۵. سفارش pending ثبت می شود ← قبل از تماس با سرویس دهنده
    ۶. خرید
    ۷. موفق → active (منتظر کد)
       قطعا انجام نشد → پول برمی گردد
       مبهم → unknown؛ پول برنمی گردد و ادمین دستی تصمیم می گیرد، چون
       خرید کلید یکتا ندارد و دوباره فرستادنش ممکن است دوبار خرید کند.

هر تغییر وضعیتی که پول جابجا می کند (برگشت، تحویل) با یک UPDATE شرطی
اتمیک انجام می شود؛ پس بررسی همزمان (کاربر، پایشگر، کران) هیچ وقت دوبار
پول برنمی گرداند و دوبار کد تحویل نمی دهد.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from app import i18n, pricing
from app.canboso import CanbosoError, CanbosoNoFunds, CanbosoUnknown
from app.config import config
from app.smsburner import (
    VALID_MINUTES,
    SmsAlreadyReceived,
    SmsBurner,
    SmsOutOfStock,
)
from app.utils import esc, now, now_str

if TYPE_CHECKING:
    from app.db import Database

log = logging.getLogger("obour.numbers")

KEY_SETTING = "smsburner_seed"

# وضعیت سفارش
PENDING = "pending"
ACTIVE = "active"
COMPLETED = "completed"
FAILED = "failed"
REFUNDED = "refunded"
UNKNOWN = "unknown"

# نتیجه خرید/عملیات (فراتر از وضعیت سفارش)
LOCKED = "locked"
NOT_CONFIGURED = "not_configured"
UNAVAILABLE = "unavailable"
INSUFFICIENT = "insufficient"
NO_FUNDS = "no_funds"
CANT_CANCEL = "cant_cancel"
PROVIDER_ERROR = "provider_error"
BAD_STATE = "bad_state"

# اگر سرویس دهنده بعد از پایان پنجره هنوز active گفت، کمی صبر می کنیم و بعد
# خودمان لغو می کنیم
GRACE = timedelta(minutes=3)

# تنظیمات قیمت (ادمین از پنل عوض می کند). نرخ تتر همان نرخ مشترک عبور است.
FIELDS: dict[str, tuple[str, str, str]] = {
    "num_profit_percent": ("درصد سود شماره", "40", "سود روی قیمت دلاری سرویس دهنده؛ مثلا 40"),
    "num_min_profit": ("حداقل سود (تومان)", "5000",
                       "کف سود هر شماره؛ شماره ها ارزانند و درصد تنها کارمزد را هم پوشش نمی دهد"),
    "num_round_to": ("رند کردن به (تومان)", "1000", "قیمت نهایی رو به بالا رند می شود"),
}


# ═══════════════════ تنظیمات و کلاینت ═══════════════════


async def seed(db: "Database") -> str:
    """seed از .env (SMSBURNER_SEED)، وگرنه همان که ادمین در پنل گذاشته."""
    return config.smsburner_seed or (await db.get_setting(KEY_SETTING, "") or "").strip()


async def client(db: "Database") -> SmsBurner:
    return SmsBurner(await seed(db), config.smsburner_base_url or None, config.smsburner_proxy)


async def load_cfg(db: "Database") -> dict[str, float]:
    out: dict[str, float] = {}
    for key, (_title, default, _desc) in FIELDS.items():
        raw = await db.get_setting(key, default)
        try:
            out[key] = float(str(raw).replace(",", "") or default)
        except (TypeError, ValueError):
            out[key] = float(default)
    return out


async def usdt_rate(db: "Database") -> float:
    return pricing.rate_for(await pricing.load(db), "USDT")


async def ready(db: "Database") -> bool:
    """فروش شماره وقتی ممکن است که seed و نرخ تتر تنظیم باشند."""
    return bool(await seed(db)) and await usdt_rate(db) > 0


def price_toman(cost_usd: float, rate: float, cfg: dict[str, float]) -> int:
    """قیمت کاربر: هزینه دلاری × نرخ تتر + سود (درصد، با کف سود)، رند رو به بالا."""
    base = cost_usd * rate
    total = max(base * (1 + cfg.get("num_profit_percent", 0) / 100), base + cfg.get("num_min_profit", 0))
    step = int(cfg.get("num_round_to") or 1) or 1
    return int(math.ceil(total / step) * step)


# ═══════════════════ نام کشور و دسته ═══════════════════

FA_COUNTRY = {
    "al": "آلبانی", "ar": "آرژانتین", "at": "اتریش", "bh": "بحرین", "bd": "بنگلادش", "be": "بلژیک",
    "bo": "بولیوی", "ba": "بوسنی", "br": "برزیل", "bg": "بلغارستان", "kh": "کامبوج", "cm": "کامرون",
    "ca": "کانادا", "cl": "شیلی", "cn": "چین", "co": "کلمبیا", "cd": "کنگو", "cr": "کاستاریکا",
    "hr": "کرواسی", "cz": "چک", "dk": "دانمارک", "do": "دومینیکن", "ec": "اکوادور", "eg": "مصر",
    "sv": "السالوادور", "ee": "استونی", "et": "اتیوپی", "fi": "فنلاند", "fr": "فرانسه", "ge": "گرجستان",
    "de": "آلمان", "gh": "غنا", "gr": "یونان", "gt": "گواتمالا", "ht": "هائیتی", "hn": "هندوراس",
    "hk": "هنگ کنگ", "hu": "مجارستان", "in": "هند", "id": "اندونزی", "iq": "عراق", "ie": "ایرلند",
    "il": "اسرائیل", "it": "ایتالیا", "ci": "ساحل عاج", "jm": "جامائیکا", "jp": "ژاپن", "jo": "اردن",
    "kz": "قزاقستان", "ke": "کنیا", "kw": "کویت", "kg": "قرقیزستان", "la": "لائوس", "lv": "لتونی",
    "lb": "لبنان", "lt": "لیتوانی", "lu": "لوکزامبورگ", "mo": "ماکائو", "mg": "ماداگاسکار", "my": "مالزی",
    "ml": "مالی", "mx": "مکزیک", "md": "مولداوی", "mn": "مغولستان", "me": "مونته نگرو", "ma": "مراکش",
    "mz": "موزامبیک", "mm": "میانمار", "np": "نپال", "nl": "هلند", "ni": "نیکاراگوئه", "ng": "نیجریه",
    "mk": "مقدونیه شمالی", "no": "نروژ", "om": "عمان", "pk": "پاکستان", "pa": "پاناما", "py": "پاراگوئه",
    "pe": "پرو", "ph": "فیلیپین", "pl": "لهستان", "pt": "پرتغال", "pr": "پورتوریکو", "qa": "قطر",
    "ro": "رومانی", "ru": "روسیه", "sa": "عربستان", "sn": "سنگال", "rs": "صربستان", "sg": "سنگاپور",
    "sk": "اسلواکی", "si": "اسلوونی", "za": "آفریقای جنوبی", "kr": "کره جنوبی", "es": "اسپانیا",
    "lk": "سریلانکا", "se": "سوئد", "ch": "سوئیس", "tw": "تایوان", "tz": "تانزانیا", "th": "تایلند",
    "tt": "ترینیداد", "tn": "تونس", "tr": "ترکیه", "ae": "امارات", "ug": "اوگاندا", "ua": "اوکراین",
    "gb": "انگلیس", "us": "آمریکا", "uy": "اروگوئه", "uz": "ازبکستان", "ve": "ونزوئلا", "vn": "ویتنام",
    "ye": "یمن", "zm": "زامبیا", "zw": "زیمبابوه",
}


def flag(cc: str) -> str:
    cc = (cc or "").upper()
    if len(cc) != 2 or not cc.isalpha():
        return "🏳️"
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in cc)


def country_title(cc: str, api_name: str = "") -> str:
    """نام کشور به زبان کاربر: فارسی از جدول خودمان، بقیه زبان ها نام انگلیسی سرویس دهنده."""
    if i18n.get_lang() == i18n.DEFAULT:
        return FA_COUNTRY.get((cc or "").lower()) or api_name or (cc or "").upper()
    return api_name or (cc or "").upper()


# دسته های سرویس دهنده ← (عنوان فارسی، ایموجی). ناشناخته = «سایر».
CATEGORIES: dict[str, tuple[str, str]] = {
    "social": ("شبکه اجتماعی و پیام رسان", "💬"),
    "tech": ("ابزار و فناوری", "🧰"),
    "email": ("ایمیل", "📧"),
    "finance": ("مالی و کریپتو", "💳"),
    "ecommerce": ("خرید آنلاین", "🛍"),
    "streaming": ("موزیک و فیلم", "🎬"),
    "gaming": ("بازی", "🎮"),
    "dating": ("دوست یابی", "💞"),
    "ride": ("تاکسی و غذا", "🚕"),
}
OTHER_CAT = ("سایر", "📦")

# سرویس های پرطرفدار که اول نشان داده می شوند (به ترتیب)
POPULAR = ("telegram", "whatsapp", "google", "instagram", "openai", "claude", "facebook", "twitter",
           "tiktok", "discord", "binance", "microsoft", "apple", "paypal", "snapchat", "amazon")


def cat_title(key: str) -> tuple[str, str]:
    return CATEGORIES.get(key, OTHER_CAT)


# ═══════════════════ کاتالوگ با قیمت تومانی ═══════════════════


async def catalog(db: "Database", force: bool = False) -> dict:
    """ردیف های (سرویس × کشور) قابل فروش با قیمت تومانی.

    {"rate", "rows": [{service_id, service, slug, category, cc, country, usd, price, stock}]}
    این فقط برای نمایش است؛ موقع خرید قیمت و موجودی دوباره و بدون کش خوانده
    می شود. کشور بی نرخ، بی موجودی یا بیشتر از موجودی ما نزد سرویس دهنده
    نمایش داده نمی شود.
    """
    rate = await usdt_rate(db)
    cfg = await load_cfg(db)
    sb = await client(db)
    try:
        rows = await sb.catalog(force=force)
        bal = await sb.balance(force=force) if sb.configured else None
    finally:
        await sb.close()
    wallet = bal["balance"] if bal and bal.get("currency") in ("", "USDT") else None
    out = []
    for r in rows:
        if r["price"] <= 0 or r["stock"] == 0:
            continue
        if wallet is not None and wallet < r["price"]:
            continue
        out.append({
            "service_id": r["service_id"], "service": r["service"], "slug": r["slug"],
            "category": r["category"], "cc": r["cc"], "country": r["country"],
            "usd": r["price"], "price": price_toman(r["price"], rate, cfg) if rate > 0 else 0,
            "stock": r["stock"],
        })
    return {"rate": rate, "rows": out}


def pages(total: int, per_page: int) -> int:
    return max(1, -(-total // per_page))


def services_of(cat: dict) -> list[dict]:
    """سرویس ها با کمترین قیمت و تعداد کشور؛ پرطرفدارها اول."""
    by: dict[str, dict] = {}
    for r in cat["rows"]:
        s = by.setdefault(r["service_id"], {"id": r["service_id"], "name": r["service"], "slug": r["slug"],
                                            "category": r["category"], "from": r["price"], "n": 0})
        s["from"] = min(s["from"], r["price"])      # کمترین قیمت تومانی
        s["n"] += 1
    items = list(by.values())
    rank = {slug: i for i, slug in enumerate(POPULAR)}
    items.sort(key=lambda s: (rank.get(s["slug"], 999), s["name"].lower()))
    return items


def countries_of(cat: dict, service_id: str) -> list[dict]:
    """کشورهای یک سرویس، ارزان ترین اول."""
    rows = [r for r in cat["rows"] if r["service_id"] == str(service_id)]
    rows.sort(key=lambda r: (r["price"], r["country"]))
    return rows


def row_of(cat: dict, service_id: str, cc: str) -> dict | None:
    return next((r for r in cat["rows"] if r["service_id"] == str(service_id) and r["cc"] == cc), None)


# ═══════════════════ جستجوی سرویس ═══════════════════

_ARABIC = str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "أ": "ا", "إ": "ا", "ؤ": "و"})

# نام فارسی رایج ← slug سرویس در SMSBurner
FA_ALIASES = {
    "تلگرام": "telegram", "تلگرم": "telegram", "واتساپ": "whatsapp", "واتس اپ": "whatsapp", "واتسآپ": "whatsapp",
    "گوگل": "google", "جیمیل": "google", "اینستاگرام": "instagram", "اینستا": "instagram",
    "فیسبوک": "facebook", "فیس بوک": "facebook", "توییتر": "twitter", "تویتر": "twitter", "ایکس": "twitter",
    "تیک تاک": "tiktok", "تیکتاک": "tiktok", "دیسکورد": "discord", "اسنپ چت": "snapchat", "لینکدین": "linkedin",
    "پیپال": "paypal", "بایننس": "binance", "بایبیت": "bybit", "کوین بیس": "coinbase", "مایکروسافت": "microsoft",
    "اپل": "apple", "آیکلود": "icloud", "آمازون": "amazon", "علی اکسپرس": "aliexpress", "نتفلیکس": "netflix",
    "اسپاتیفای": "spotify", "استیم": "steam", "ایمو": "imo", "لاین": "line", "سیگنال": "signal",
    "چت جی پی تی": "openai", "چت جیپیتی": "openai", "اوپن ای آی": "openai", "کلود": "claude",
    "اوبر": "uber", "تیندر": "tinder", "ردیت": "reddit", "پینترست": "pinterest", "اسلک": "slack",
    "گیت هاب": "github", "گیتهاب": "github", "یاهو": "yahoo", "ایرانسل": "any-other", "سایر": "any-other",
    "ترد": "threads", "توییچ": "twitch", "یوتیوب": "youtube", "ایبی": "ebay", "ای بی": "ebay",
}


def norm_query(q: str) -> str:
    """کوچک، بدون فاصله و نیم فاصله، یکدست کردن ی و ک عربی."""
    q = str(q or "").translate(_ARABIC).lower()
    for ch in (" ", "‌", "‏", "‎", "-", "_", ".", "/"):
        q = q.replace(ch, "")
    return q.strip()


def search_services(cat: dict, query: str, limit: int = 10) -> list[dict]:
    """سرویس هایی که اسم (انگلیسی یا فارسی رایج) شان به متن کاربر می خورد؛ دقیق ترین ها اول."""
    q = norm_query(query)
    if len(q) < 2:
        return []
    slugs = set()
    for alias, slug in FA_ALIASES.items():
        a = norm_query(alias)
        # «تلگرام» دقیق، «تلگ» ابتدای اسم، یا «شماره تلگرام» که اسم داخلش است
        if a == q or (len(q) >= 3 and (a.startswith(q) or (len(a) >= 3 and a in q))):
            slugs.add(slug)
    scored = []
    for s in services_of(cat):
        name, slug = norm_query(s["name"]), norm_query(s["slug"])
        if s["slug"] in slugs:
            score = 0
        elif name == q or slug == q:
            score = 0
        elif name.startswith(q) or slug.startswith(q):
            score = 1
        elif q in name or q in slug:
            score = 2
        else:
            continue
        scored.append((score, s["name"].lower(), s))
    scored.sort(key=lambda t: t[:2])
    return [s for _, _, s in scored[:limit]]


# ═══════════════════ نوع شماره (اپراتور) ═══════════════════

# نوع ← (عنوان فارسی، ایموجی)
OP_LABELS = {"virtual": ("مجازی", "📞"), "physical": ("فیزیکی", "📱"), "premium": ("پریمیوم", "⭐")}


def op_title(op: dict | None) -> str:
    """«فیزیکی · T-Mobile» به زبان جاری؛ خالی اگر اپراتور انتخاب نشده."""
    if not op or not (op.get("id") or op.get("operator_id")):
        return ""
    kind = op.get("type") or op.get("operator_type") or "virtual"
    name = op.get("name") or op.get("operator_name") or ""
    return f"{i18n.t(OP_LABELS.get(kind, OP_LABELS['virtual'])[0])} · {name}".strip(" ·")


def country_label(order: dict) -> str:
    """نام کشور (به زبان جاری) به همراه نوع شماره اگر انتخاب شده: «آمریکا · فیزیکی · T-Mobile»."""
    label = country_title(order.get("country") or "", order.get("country_name") or "")
    op = op_title(order_op(order))
    return f"{label} · {op}" if op else label


def order_op(order: dict) -> dict | None:
    if not order.get("operator_id"):
        return None
    return {"id": order["operator_id"], "name": order.get("operator_name") or "", "type": order.get("operator_type") or "virtual"}


async def operators_of(db: "Database", cat: dict, service_id: str, cc: str) -> list[dict]:
    """گزینه های نوع شماره برای یک سرویس و کشور با قیمت تومانی، ارزان ترین اول.

    خالی یعنی انتخابی نیست (یک اپراتور یا فهرست خوانده نشد)؛ آن وقت خرید با اپراتور
    پیش فرض سایت انجام می شود، همان رفتار قبل از این قابلیت."""
    row = row_of(cat, service_id, cc)
    if row is None:
        return []
    sb = await client(db)
    try:
        ops = await sb.operators(cc)
    except CanbosoError as exc:
        log.info("اپراتورهای %s خوانده نشد: %s", cc, exc)
        return []
    finally:
        await sb.close()
    if len(ops) < 2:
        return []
    rate, cfg = cat["rate"], await load_cfg(db)
    out = [{**o, "usd": round(row["usd"] * o["mult"], 4), "price": price_toman(row["usd"] * o["mult"], rate, cfg)} for o in ops]
    out.sort(key=lambda o: (o["price"], o["name"]))
    return out


# ═══════════════════ خرید ═══════════════════


async def buy(db: "Database", bot, user: dict, service_id: str, cc: str,  # noqa: ANN001
              operator_id: str | None = None) -> dict:
    """{"status": ..., "order": ردیف سفارش}. status یکی از ثابت های بالا یا وضعیت سفارش.

    operator_id: نوع/اپراتور انتخابی کاربر (از operators_of)؛ خالی = پیش فرض سایت."""
    cc = (cc or "").lower()
    operator_id = str(operator_id).strip() if operator_id and str(operator_id) not in ("0", "None") else None
    lock = f"num:{user['id']}"
    if not await db.acquire_lock(lock, ttl_seconds=120):
        return {"status": LOCKED}
    sb = await client(db)
    try:
        if not sb.configured:
            return {"status": NOT_CONFIGURED}
        rate = await usdt_rate(db)
        if rate <= 0:
            return {"status": NOT_CONFIGURED}
        cfg = await load_cfg(db)

        # قیمت و موجودی تازه
        try:
            rows = await sb.catalog(force=True)
        except CanbosoError as exc:
            log.warning("کاتالوگ شماره مجازی خوانده نشد: %s", exc)
            return {"status": PROVIDER_ERROR, "error": str(exc)}
        row = next((r for r in rows if r["service_id"] == str(service_id) and r["cc"] == cc), None)
        if row is None or row["stock"] == 0 or row["price"] <= 0:
            return {"status": UNAVAILABLE}
        usd = row["price"]
        op = None
        if operator_id:
            # قیمت اپراتور = قیمت پایه × ضریب همان اپراتور (قیمت نهایی را quote تایید می کند)
            try:
                op = next((o for o in await sb.operators(cc) if o["id"] == operator_id), None)
            except CanbosoError as exc:
                return {"status": PROVIDER_ERROR, "error": str(exc)}
            if op is None:
                return {"status": UNAVAILABLE}
            usd = row["price"] * op["mult"]
        try:
            quoted = await sb.quote(service_id, cc, operator_id)
        except SmsOutOfStock:
            return {"status": UNAVAILABLE}
        except CanbosoError as exc:
            return {"status": PROVIDER_ERROR, "error": str(exc)}
        if quoted and quoted > 0:
            if quoted <= usd * 3:
                usd = max(usd, quoted)      # هیچ وقت زیر قیمت تمام شده نمی فروشیم
            else:
                # عدد باورنکردنی (مثلا واحد دیگر): به کاتالوگ اعتماد می کنیم و ادمین از هشدار هزینه واقعی خبردار می شود
                log.warning("قیمت quote (%s) با کاتالوگ (%s) جور نیست؛ نادیده گرفته شد", quoted, usd)
        price = price_toman(usd, rate, cfg)

        # موجودی خودمان قبل از کسر پول کاربر
        bal = await sb.balance()
        if bal is not None and bal.get("currency") in ("", "USDT") and bal["balance"] < usd:
            await alert_admins(bot, "🚨 <b>موجودی SMSBurner کافی نیست</b>\n\n"
                                    f"موجودی {bal['balance']:g} دلار است و یک شماره {usd:g} دلار لازم دارد. "
                                    "حساب را شارژ کن: تنظیمات ← 📱 شماره مجازی.")
            return {"status": UNAVAILABLE}

        if not await db.atomic_debit(user["id"], price):
            return {"status": INSUFFICIENT, "price": price}
        txn_id = await db.insert_transaction(user["id"], "number_purchase", -price, status="approved")
        order = await db.create_number_order(
            user["id"], str(service_id), row["service"], cc, row["country"], usd, price, txn_id,
            operator={"id": op["id"], "name": op["name"], "type": op["type"]} if op else None)
        return await _send(db, bot, sb, user, order)
    finally:
        await sb.close()
        await db.release_lock(lock)


async def _send(db: "Database", bot, sb: SmsBurner, user: dict, order: dict) -> dict:  # noqa: ANN001
    try:
        info = await sb.buy(order["service_id"], order["country"], order.get("operator_id") or None)
    except CanbosoUnknown as exc:
        await db.update_number_order(order["id"], only_from=(PENDING,), status=UNKNOWN, error=str(exc)[:300])
        log.error("سفارش شماره مبهم ماند: %s (%s)", order["code"], exc)
        await alert_admins(bot, (
            "⚠️ <b>خرید شماره مجازی مبهم ماند</b>\n\n"
            f"کد: <code>{order['code']}</code>\nکاربر: <code>{user['telegram_id']}</code>\n"
            f"مبلغ کسر شده: {order['price']:,} تومان\nعلت: {esc(str(exc)[:120])}\n\n"
            "<b>پول برنگشته</b> چون ممکنه شماره خریده شده باشد. اول موجودی و سفارش های حساب "
            "SMSBurner را ببین، بعد: تنظیمات ← 📱 شماره مجازی ← 🔎 سفارش های مبهم."))
        return {"status": UNKNOWN, "order": await db.get_number_order(order["id"])}
    except CanbosoNoFunds as exc:
        await _refund(db, order, FAILED, "موجودی سرویس دهنده تمام شد")
        await alert_admins(bot, "🚨 <b>موجودی SMSBurner تمام شد</b>\n\nیک خرید انجام نشد و پول کاربر برگشت.\n"
                                f"<code>{esc(str(exc)[:150])}</code>\nحساب را شارژ کن.")
        return {"status": NO_FUNDS, "order": await db.get_number_order(order["id"])}
    except SmsOutOfStock:
        await _refund(db, order, FAILED, "شماره موجود نبود")
        return {"status": UNAVAILABLE, "order": await db.get_number_order(order["id"])}
    except CanbosoError as exc:
        await _refund(db, order, FAILED, str(exc))
        log.warning("سفارش شماره %s انجام نشد: %s", order["code"], exc)
        return {"status": PROVIDER_ERROR, "order": await db.get_number_order(order["id"]), "error": str(exc)}

    expires = (now() + timedelta(minutes=VALID_MINUTES)).isoformat(timespec="seconds")
    if info.get("expires_in"):
        expires = (now() + timedelta(seconds=float(info["expires_in"]))).isoformat(timespec="seconds")
    cost = info.get("price") or order["usd_cost"]
    await db.update_number_order(order["id"], only_from=(PENDING,), status=ACTIVE, provider_id=info["id"],
                                 phone=info["phone"], expires_at=expires, usd_cost=cost, checked_at=now_str())
    if info.get("price") and order["usd_cost"] and info["price"] > float(order["usd_cost"]) * 1.001:
        await alert_admins(bot, f"⚠️ هزینه واقعی سفارش <code>{order['code']}</code> بیشتر از برآورد بود: "
                                f"{info['price']:g} دلار به جای {float(order['usd_cost']):g}")
    log.info("شماره مجازی %s صادر شد", order["code"])
    fresh = await db.get_number_order(order["id"])
    if info.get("sms_code") or info["status"] == "completed":
        # پیامک همان لحظه رسیده بود
        await _deliver(db, fresh, info)
        fresh = await db.get_number_order(order["id"])
    return {"status": fresh["status"], "order": fresh}


# ═══════════════════ پیگیری، لغو، استرداد ═══════════════════


def is_expired(order: dict, with_grace: bool = False) -> bool:
    try:
        end = datetime.fromisoformat(order["expires_at"])
    except (TypeError, ValueError):
        return False
    return now() > end + (GRACE if with_grace else timedelta(0))


async def _deliver(db: "Database", order: dict, info: dict) -> bool:
    """کد رسیده را ثبت می کند؛ True فقط برای اولین بار (برای اطلاع به کاربر)."""
    return await db.update_number_order(
        order["id"], only_from=(ACTIVE, PENDING), status=COMPLETED, sms_code=info.get("sms_code") or "",
        sms_text=(info.get("sms_text") or "")[:500], completed_at=now_str(), checked_at=now_str())


async def _refund(db: "Database", order: dict, status: str, reason: str) -> bool:
    """برگشت پول کاربر؛ فقط یک بار (شرط اتمیک روی وضعیت)."""
    if not await db.update_number_order(order["id"], only_from=(PENDING, ACTIVE, UNKNOWN),
                                        status=status, error=reason[:300]):
        return False
    await db.atomic_credit(order["user_id"], int(order["price"]))
    await db.insert_transaction(order["user_id"], "refund", int(order["price"]), status="approved")
    return True


async def check(db: "Database", order: dict, sb: SmsBurner | None = None) -> dict:
    """یک بار از سرویس دهنده می پرسد.

    {"status": وضعیت سفارش بعد از بررسی, "order": سفارش تازه, "event": None | "completed" | "refunded"}
    event فقط وقتی پر است که همین فراخوانی تغییر را انجام داد (برای اطلاع به کاربر).
    """
    if order["status"] != ACTIVE or not order.get("provider_id"):
        return {"status": order["status"], "order": order, "event": None}
    own = sb is None
    sb = sb or await client(db)
    event = None
    try:
        try:
            info = await sb.poll(order["provider_id"])
        except CanbosoError as exc:
            log.info("پیگیری شماره %s نشد: %s", order["code"], exc)
            return {"status": PROVIDER_ERROR, "order": order, "event": None, "error": str(exc)}
        await db.update_number_order(order["id"], checked_at=now_str())
        if info["status"] == "completed":
            if await _deliver(db, order, info):
                event = "completed"
        elif info["status"] in ("cancelled", "refunded", "expired"):
            # سرویس دهنده خودش پول را به حساب ما برگردانده؛ پول کاربر هم برمی گردد
            if await _refund(db, order, REFUNDED, f"سرویس دهنده: {info['status']}"):
                event = "refunded"
        elif is_expired(order, with_grace=True):
            # پنجره تمام شده ولی هنوز active؛ خودمان لغو می کنیم
            try:
                await sb.cancel(order["provider_id"])
                if await _refund(db, order, REFUNDED, "مهلت ۲۰ دقیقه تمام شد، کدی نیامد"):
                    event = "refunded"
            except SmsAlreadyReceived:
                pass        # دور بعد کد را می گیریم
            except CanbosoError as exc:
                log.info("لغو شماره منقضی %s نشد: %s", order["code"], exc)
    finally:
        if own:
            await sb.close()
    fresh = await db.get_number_order(order["id"])
    return {"status": fresh["status"], "order": fresh, "event": event}


async def cancel(db: "Database", order: dict) -> dict:
    """لغو توسط کاربر و برگشت پول (فقط اگر کدی نیامده)."""
    if order["status"] != ACTIVE or not order.get("provider_id"):
        return {"status": BAD_STATE, "order": order}
    sb = await client(db)
    try:
        try:
            await sb.cancel(order["provider_id"])
        except SmsAlreadyReceived:
            # کد همین حالا رسیده؛ به جای لغو، تحویلش بده
            r = await check(db, order, sb)
            return {"status": r["status"], "order": r["order"], "event": r["event"]}
        except CanbosoUnknown as exc:
            return {"status": PROVIDER_ERROR, "order": order, "error": str(exc)}
        except CanbosoError as exc:
            return {"status": CANT_CANCEL, "order": order, "error": str(exc)}
        refunded = await _refund(db, order, REFUNDED, "لغو توسط کاربر")
        return {"status": REFUNDED, "order": await db.get_number_order(order["id"]),
                "event": "refunded" if refunded else None}
    finally:
        await sb.close()


async def reroll(db: "Database", bot, user: dict, order: dict) -> dict:  # noqa: ANN001
    """«شماره ی دیگه»: شماره ی منتظر کد لغو می شود (پولش برمی گردد) و از همان سرویس، کشور و نوع
    یک شماره ی تازه گرفته می شود.

    اگر لغو نشد (کد رسیده یا سایت اجازه نداد) هیچ خرید تازه ای انجام نمی شود. قیمت خرید تازه
    دوباره از سایت خوانده می شود و ممکن است کمی فرق کند. بین دو درخواست ۲۰ ثانیه فاصله لازم
    است تا کسی با لغو و خرید پشت سر هم به سرویس دهنده فشار نیاورد.

    خروجی مثل buy؛ اگر لغو نشد، وضعیت لغو (CANT_CANCEL، PROVIDER_ERROR، COMPLETED، BAD_STATE...).
    """
    if order["status"] != ACTIVE:
        return {"status": BAD_STATE, "order": order}
    if not await db.acquire_lock(f"numre:{user['id']}", ttl_seconds=20):
        return {"status": LOCKED, "order": order}
    c = await cancel(db, order)
    if c["status"] != REFUNDED:
        return {"status": c["status"], "order": c.get("order") or order, "error": c.get("error"),
                "event": c.get("event")}
    fresh = await db.get_user(user["id"]) or user
    r = await buy(db, bot, fresh, order["service_id"], order["country"], order.get("operator_id") or None)
    r["old"] = c["order"]
    return r


async def settle_manual(db: "Database", order: dict, refund: bool) -> dict:
    """سفارش مبهم (خرید معلوم نشد) با تصمیم ادمین بسته می شود.

    refund=True: در حساب SMSBurner شماره ای نبود؛ پول کاربر برمی گردد.
    refund=False: خریده شده و ادمین کد را از سایت برداشته و خودش به کاربر داده است.
    """
    if order["status"] not in (UNKNOWN, PENDING):
        return {"status": order["status"], "order": order}
    if refund:
        await _refund(db, order, FAILED, "بررسی دستی ادمین: خرید انجام نشده بود")
    else:
        await db.update_number_order(order["id"], only_from=(UNKNOWN, PENDING), status=COMPLETED,
                                     completed_at=now_str(), sms_text="تحویل دستی توسط پشتیبانی")
    return {"status": (FAILED if refund else COMPLETED), "order": await db.get_number_order(order["id"])}


async def active_orders(db: "Database", limit: int = 50) -> list[dict]:
    return await db.number_orders_by_status((ACTIVE,), limit)


async def alert_admins(bot, body: str) -> None:  # noqa: ANN001
    if bot is None:
        return
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(admin_id, body)
        except Exception:  # noqa: BLE001
            log.debug("خبر دادن به ادمین %s نشد", admin_id, exc_info=True)
