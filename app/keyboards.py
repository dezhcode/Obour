"""کیبوردهای inline ربات."""
from __future__ import annotations

import re

from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import config
from app.i18n import t as _t

# ---------- رنگ دکمه ها (Bot API 9.4) ----------
# تلگرام از فوریه ۲۰۲۶ فیلد style را به InlineKeyboardButton اضافه کرد.
# سه مقدار مجاز: primary (آبی)، success (سبز)، danger (قرمز).
PRIMARY = "primary"
SUCCESS = "success"
DANGER = "danger"

# اگر نسخه aiogram قدیمی باشد و style را نشناسد، بی سروصدا نادیده گرفته
# می شود تا ربات نخوابد. برای دیدن رنگ ها aiogram باید ۳.۲۵ یا بالاتر باشد.
_FIELDS = getattr(InlineKeyboardButton, "model_fields", {})
_STYLE_SUPPORTED = "style" in _FIELDS
_ICON_SUPPORTED = "icon_custom_emoji_id" in _FIELDS

# ---------- ایموجی سفارشی روی دکمه (Bot API 9.4) ----------
# شرط استفاده: صاحب ربات باید Telegram Premium داشته باشد.
# آیدی ایموجی ها در .env تنظیم می شود؛ اگر خالی باشد چیزی نمایش داده نمی شود.
ICONS = {
    "buy": config.icon_buy,
    "wallet": config.icon_wallet,
    "gift": config.icon_gift,
    "ok": config.icon_ok,
}


def _add(
    kb: InlineKeyboardBuilder,
    text: str,
    style: str | None = None,
    icon: str | None = None,
    icon_id: str | None = None,
    alt: str = "",
    **kwargs,
) -> None:
    """افزودن دکمه با رنگ و ایموجی سفارشی اختیاری.

    هر دو قابلیت به Bot API 9.4 نیاز دارند و اگر پشتیبانی نشوند
    بی سروصدا کنار گذاشته می شوند تا ربات همیشه کار کند.

    نکته مهم درباره ایموجی پریمیوم روی دکمه:
    تلگرام آیکن (icon_custom_emoji_id) را کنار متن دکمه نشان می دهد و
    متن دکمه هم نمی تواند خالی باشد. پس برای دکمه ای که متنش فقط یک
    ایموجی است (مثل ➕ و ➖ در ساخت دلخواه)، اگر آیکن بگذاریم و ایموجی
    متنی هم بماند، کاربر دو ایموجی کنار هم می بیند. راه حل:
      - اگر alt داده شده باشد (مثلا «بیشتر»)، متن دکمه همان می شود و
        ایموجی پریمیوم به عنوان آیکن کنارش می نشیند.
      - اگر alt نداشته باشیم، آیکن گذاشته نمی شود و همان ایموجی متنی
        می ماند؛ یک ایموجی بهتر از دو ایموجی است.
    """
    # متن دکمه به زبان کاربر؛ ایموجی ابتدای متن جدا ترجمه نمی شود
    text = _tr(text)
    alt = _tr(alt) if alt else alt

    if style and _STYLE_SUPPORTED:
        kwargs["style"] = style

    if _ICON_SUPPORTED:
        # اولویت: icon_id صریح > icon از env > تشخیص خودکار از متن
        chosen = icon_id or (ICONS.get(icon) if icon else None)
        if not chosen:
            chosen, _ = _auto_icon(text)
        if chosen:
            # ایموجی متنی باید برداشته شود وگرنه با آیکن تکرار می شود
            label = _EMOJI_LEAD.sub("", text).strip()
            if not label:
                label = alt.strip()
            if label:
                kwargs["icon_custom_emoji_id"] = chosen
                text = label
            # اگر هیچ متنی نماند، آیکن را بی خیال می شویم (دکمه فقط ایموجی)

    kb.button(text=text, **kwargs)


_EMOJI_LEAD = re.compile(
    r"^[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u27BF\u2B00-\u2BFF"
    r"\uFE0F\u200D\U0001F3FB-\U0001F3FF]+\s*"
)


def _tr(text: str) -> str:
    """ترجمه متن دکمه. کلید ترجمه متن بدون ایموجی ابتدایی است، پس یک
    عبارت (مثلا «کیف پول») با هر ایموجی ای که ادمین بگذارد ترجمه می شود."""
    from app import i18n

    if not text or i18n.get_lang() == i18n.DEFAULT:
        return text
    m = _EMOJI_LEAD.match(text)
    lead = m.group(0) if m else ""
    return lead + i18n.t(text[len(lead):])


def _strip_lead_emoji(text: str) -> str:
    """حذف ایموجی ابتدای متن دکمه.

    اگر بعد از حذف چیزی نماند (دکمه فقط ایموجی بوده مثل ➕)، متن اصلی
    نگه داشته می شود تا دکمه بی نام نشود.
    """
    stripped = _EMOJI_LEAD.sub("", text).strip()
    return stripped or text


def _auto_icon(text: str) -> tuple[str | None, str]:
    """(آیدی ایموجی سفارشی، متن بدون ایموجی).

    اگر ایموجی ابتدای متن دکمه در پنل ادمین سفارشی شده باشد، آیدی اش
    برمی گردد و ایموجی از متن حذف می شود؛ چون تلگرام خودش آیکن را
    کنار متن می گذارد و نگه داشتن ایموجی متنی باعث تکرار می شود.
    """
    from app import emoji as emo

    if not emo._cache or not text:
        return None, text
    parts = text.split(" ", 1)
    head = parts[0].replace("\ufe0f", "")
    if not head:
        return None, text
    for key, (fallback, _t, _c) in emo.CATALOG.items():
        if fallback.replace("\ufe0f", "") == head:
            eid = emo.custom_id(key)
            if eid:
                rest = parts[1].strip() if len(parts) > 1 else ""
                return eid, (rest or text)
            return None, text
    return None, text


def _btn(
    kb: InlineKeyboardBuilder,
    emoji_key: str,
    label: str = "",
    style: str | None = None,
    alt: str = "",
    **kwargs,
) -> None:
    """دکمه با ایموجی از کاتالوگ قابل تنظیم در پنل ادمین.

    متن دکمه ایموجی پیش فرض را نشان می دهد و اگر ادمین ایموجی سفارشی
    تنظیم کرده باشد، روی دکمه هم به صورت icon نمایش داده می شود.

    alt برای دکمه های بی متن است: متنی که وقتی ایموجی پریمیوم فعال شد
    جای ایموجی متنی را می گیرد (چون متن دکمه نمی تواند خالی باشد).
    """
    from app import emoji as emo

    fallback = emo.default(emoji_key)
    text = f"{fallback} {label}".strip() if label else fallback
    _add(kb, text, style=style, icon_id=emo.custom_id(emoji_key), alt=alt, **kwargs)


def _spacer(kb: InlineKeyboardBuilder, text: str) -> None:
    """دکمه نمایشی و غیرقابل کلیک (برای نوار وضعیت و سرتیتر).

    اگر نسخه aiogram از دکمه غیرفعال پشتیبانی نکند، به یک دکمه بی اثر
    با callback خنثی تبدیل می شود.
    """
    try:
        from aiogram.types import CallbackGame  # noqa: F401  (فقط برای تشخیص نسخه)
    except Exception:  # noqa: BLE001
        pass
    # ایموجی سفارشی روی دکمه نمایشی هم اعمال می شود (مثل نوار «۵ گیگ»)
    extra: dict = {}
    if _ICON_SUPPORTED:
        eid, _rest = _auto_icon(text)
        if eid:
            label = _EMOJI_LEAD.sub("", text).strip()
            if label:
                extra["icon_custom_emoji_id"] = eid
                text = label

    if "disabled" in _FIELDS:
        try:
            from aiogram.types import DisabledButton

            kb.button(text=text, disabled=DisabledButton(), **extra)
            return
        except Exception:  # noqa: BLE001
            pass
    kb.button(text=text, callback_data="noop", **extra)


def main_menu(trial_available: bool = False) -> InlineKeyboardMarkup:
    """منوی اصلی.

    دکمه هایی که بخششان از پنل خاموش شده باشد اصلا ساخته نمی شوند -
    نه اینکه ساخته شوند و بعد پیام «غیرفعال است» بدهند. کاربر نباید
    چیزی ببیند که نمی تواند بخرد.
    """
    from app import features

    kb = InlineKeyboardBuilder()
    rows: list[int] = []

    if trial_available and features.is_on("shop_trial"):
        _btn(kb, "gift", "تست رایگان", style=SUCCESS, callback_data="trial")
        rows.append(1)

    _btn(kb, "shop", "فروشگاه", style=PRIMARY, callback_data="buy")
    _btn(kb, "user", "سرویس های من", callback_data="svc")
    rows.append(2)

    pair: list[str] = []
    if features.is_on("shop_wallet"):
        _btn(kb, "wallet", "کیف پول", style=SUCCESS, callback_data="wal")
        pair.append("wal")
    if features.is_on("shop_referral"):
        _btn(kb, "invite", "هم سفرها", callback_data="ref")
        pair.append("ref")
    if pair:
        rows.append(len(pair))

    _btn(kb, "guide", "راهنما", callback_data="guide")
    _btn(kb, "support", "پشتیبانی", callback_data="sup")
    rows.append(2)

    # ---------- مینی اپ ----------
    # مکمل است، نه جایگزین: همه دکمه های بالا سر جایشان می مانند.
    # اگر آدرس https نباشد (یا مینی اپ خاموش باشد) دکمه اصلا ساخته
    # نمی شود؛ تلگرام مینی اپ روی http را باز نمی کند و کاربر نباید
    # دکمه ای ببیند که کار نمی کند.
    try:
        from aiogram.types import WebAppInfo

        from app import webapp as _webapp

        _wa_url = _webapp.url()
        if _wa_url:
            # از _btn رد می شود نه _add: این طور ایموجی اش از کاتالوگ
            # می آید، در پنل ادمین قابل تغییر است، و اگر ایموجی پریمیوم
            # برایش ست کنی روی دکمه به صورت icon نمایش داده می شود -
            # دقیقا مثل بقیه دکمه های منو.
            _btn(kb, "webapp", "مینی اپ عبور", web_app=WebAppInfo(url=_wa_url))
            rows.append(1)
    except Exception:  # noqa: BLE001
        pass  # نبود مینی اپ نباید منوی اصلی را بشکند

    _add(kb, "🌐 زبان", callback_data="lang")
    rows.append(1)

    kb.adjust(*rows)
    return kb.as_markup()


def lang_kb(current: str | None = None) -> InlineKeyboardMarkup:
    """انتخاب زبان. نام هر زبان به خط خودش است و ترجمه نمی شود؛ زبان
    پیشنهادی (حدس از تلگرام یا انتخاب فعلی) تیک دارد."""
    from app import i18n

    kb = InlineKeyboardBuilder()
    for code in i18n.LANGS:
        mark = " ✓" if code == current else ""
        kb.button(text=f"{i18n.FLAGS[code]} {i18n.NAMES[code]}{mark}", callback_data=f"lang:{code}")
    kb.adjust(2, 2)
    return kb.as_markup()


def shop_hub_kb() -> InlineKeyboardMarkup:
    """صفحه اول فروشگاه: انتخاب بین کانفیگ و خدمات هوش مصنوعی.

    این لایه عمدا اضافه شد تا منوی اصلی با اضافه شدن محصول های تازه
    (استارز، پرمیوم و...) شلوغ نشود؛ همه شان زیر همین شاخه می آیند.
    """
    from app import features

    kb = InlineKeyboardBuilder()
    rows: list[int] = []

    # دو شاخه اصلی کنار هم؛ لوکیشن ها اینجا نیست چون داخل صفحه کانفیگ
    # هست و تکرارش فقط شلوغی است.
    main = 0
    if features.is_on("shop_vpn"):
        _btn(kb, "shop", "کانفیگ و اینترنت آزاد", style=PRIMARY, callback_data="buy:vpn")
        main += 1
    if features.is_on("shop_ai"):
        _btn(kb, "ai", "خدمات هوش مصنوعی", style=SUCCESS, callback_data="buy:ai")
        main += 1
    if main:
        rows.append(main)

    if features.is_on("shop_wallet"):
        _btn(kb, "wallet", "شارژ کیف پول", callback_data="wal")
        rows.append(1)
    _btn(kb, "back", "منوی اصلی", callback_data="menu")
    rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()


def ai_shop_kb() -> InlineKeyboardMarkup:
    """صفحه خدمات هوش مصنوعی."""
    kb = InlineKeyboardBuilder()
    _btn(kb, "ai", "اشتراک جمنای پرو", style=PRIMARY, callback_data="ai:buy")
    _btn(kb, "history", "سفارش های من", callback_data="ai:mine")
    _btn(kb, "back", "فروشگاه", callback_data="buy")
    kb.adjust(1, 2)
    return kb.as_markup()


def ai_track_kb(order_id: int, has_provider_code: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if has_provider_code:
        _btn(kb, "sync", "وضعیت لحظه ای", style=PRIMARY, callback_data=f"ai:status:{order_id}")
    _btn(kb, "back", "منوی اصلی", callback_data="menu")
    kb.adjust(1, 1) if has_provider_code else kb.adjust(1)
    return kb.as_markup()


def ai_notify_kb() -> InlineKeyboardMarkup:
    """وقتی محصول موقتا موجود نیست - نه دکمه غیرفعال، یک دکمه فعال."""
    kb = InlineKeyboardBuilder()
    _btn(kb, "bell", "وقتی موجود شد خبرم کن", style=PRIMARY, callback_data="ai:notify")
    _btn(kb, "back", "برگشت", callback_data="buy:ai")
    kb.adjust(1, 1)
    return kb.as_markup()


def ai_product_kb(affordable: bool) -> InlineKeyboardMarkup:
    """کارت محصول. اگر موجودی کم باشد، دکمه خرید جایش را به شارژ می دهد."""
    kb = InlineKeyboardBuilder()
    if affordable:
        _btn(kb, "ok", "تایید و خرید", style=SUCCESS, callback_data="ai:ok")
    else:
        _btn(kb, "wallet", "شارژ کیف پول", style=SUCCESS, callback_data="wal")
    _btn(kb, "back", "برگشت", callback_data="buy:ai")
    kb.adjust(1, 1)
    return kb.as_markup()


def ai_delivered_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _btn(kb, "history", "سفارش های من", callback_data="ai:mine")
    _btn(kb, "support", "پشتیبانی", callback_data="sup")
    _add(kb, "🏠 منوی اصلی", callback_data="menu")
    kb.adjust(2, 1)
    return kb.as_markup()


def back_to_shop_kb() -> InlineKeyboardMarkup:
    """برگشت از یک شاخه فروشگاه.

    وقتی هر دو شاخه فعال باشند، «فروشگاه» معنا دارد؛ وگرنه آن صفحه
    اصلا نمایش داده نمی شود و دکمه باید مستقیم به منو برود.
    """
    from app import features

    kb = InlineKeyboardBuilder()
    if features.is_on("shop_vpn") and features.is_on("shop_ai"):
        _btn(kb, "back", "فروشگاه", callback_data="buy")
        _add(kb, "🏠 منوی اصلی", callback_data="menu")
        kb.adjust(2)
    else:
        _add(kb, "🏠 منوی اصلی", callback_data="menu")
        kb.adjust(1)
    return kb.as_markup()


def back_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "🔙 منوی اصلی", callback_data="menu")
    return kb.as_markup()


def _fmt_days(days: int) -> str:
    """نمایش خوانا برای مدت."""
    if days == 1:
        return _t("۱ روز")
    if days == 7:
        return _t("۱ هفته")
    if days == 14:
        return _t("۲ هفته")
    if days % 30 == 0:
        months = days // 30
        return _t("۱ ماه") if months == 1 else f"{months} {_t('ماه')}"
    return f"{days} {_t('روز')}"


def plan_categories_kb(cats: list[dict]) -> InlineKeyboardMarkup:
    """صفحه اول فروشگاه: دکمه هر دسته + ساخت دلخواه زیرش."""
    kb = InlineKeyboardBuilder()
    for c in cats:
        _add(
            kb,
            f"{c['emoji']} {c['title']}",
            style=PRIMARY,
            callback_data=f"buy:c:{c['id']}",
        )
    from app import features

    rows: list[int] = [min(len(cats), 3) or 1]
    if features.is_on("shop_custom"):
        _btn(kb, "custom", "بساز به سلیقه خودت", style=SUCCESS, callback_data="cst")
        rows.append(1)
    side: list[str] = []
    if features.is_on("shop_locations"):
        _btn(kb, "globe_loc", "سرورها و لوکیشن ها", callback_data="loc")
        side.append("loc")
    if features.is_on("shop_wallet"):
        _btn(kb, "wallet", "شارژ کیف پول", callback_data="wal")
        side.append("wal")
    if side:
        rows.append(len(side))
    # اگر فقط یک شاخه فعال باشد، صفحه اول فروشگاه رد می شود و همین
    # صفحه اولین صفحه است - پس دکمه برگشت باید به منوی اصلی برود،
    # نه به «فروشگاه» که دوباره همین جا برمی گردد (حلقه بی پایان، و
    # از دید کاربر یعنی «دکمه برگشت کار نمی کند»).
    both = features.is_on("shop_vpn") and features.is_on("shop_ai")
    _btn(
        kb,
        "back",
        "فروشگاه" if both else "منوی اصلی",
        callback_data="buy" if both else "menu",
    )
    rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()


def locations_kb() -> InlineKeyboardMarkup:
    """صفحه سرورها و لوکیشن ها: راه برگشت به فروشگاه."""
    kb = InlineKeyboardBuilder()
    _btn(kb, "shop", "دیدن پلن ها", style=PRIMARY, callback_data="buy:vpn")
    _btn(kb, "back", "منوی اصلی", callback_data="menu")
    kb.adjust(1, 1)
    return kb.as_markup()


def plans_kb(plans: list[dict], category: str | None = None) -> InlineKeyboardMarkup:
    """لیست پلن های یک دسته."""
    kb = InlineKeyboardBuilder()
    for p in plans:
        badge = "🔥 " if p.get("badge") else ""
        _add(
            kb,
            f"{badge}{p['title']} · {p['data_gb']} {_t('گیگ')} · {p['price']:,} {_t('تومان')}",
            style=PRIMARY if p.get("badge") else None,  # پلن محبوب آبی
            callback_data=f"buy:p:{p['id']}",
        )
    _add(kb, "🔙 دسته ها", callback_data="buy:vpn")
    kb.adjust(1)
    return kb.as_markup()


def plan_confirm(
    plan_id: int,
    prev_id: int | None = None,
    next_id: int | None = None,
    discount_code: str | None = None,
) -> InlineKeyboardMarkup:
    """صفحه تایید خرید یک پلن.

    چیدمان:
      ردیف ۱ : تایید و خرید | انصراف
      ردیف ۲ : پلن بعدی | پلن قبلی
      ردیف ۳ : منوی اصلی
    """
    kb = InlineKeyboardBuilder()
    _btn(kb, "ok", "تایید و خرید", style=SUCCESS, callback_data=f"buy:ok:{plan_id}")
    _add(kb, "❌ انصراف", style=DANGER, callback_data="buy:vpn")

    # کد تخفیف: یک ردیف کامل تا با دکمه های ناوبری قاطی نشود
    if discount_code:
        _add(kb, f"🎟 {discount_code} ✕", callback_data=f"buy:dscx:{plan_id}")
    else:
        _add(kb, "🎟 کد تخفیف دارم", callback_data=f"buy:dsc:{plan_id}")

    nav = 0
    if next_id:
        _add(kb, "پلن بعدی ⬅️", callback_data=f"buy:p:{next_id}")
        nav += 1
    if prev_id:
        _add(kb, "➡️ پلن قبلی", callback_data=f"buy:p:{prev_id}")
        nav += 1

    _add(kb, "🔙 منوی اصلی", callback_data="menu")

    # ردیف ها: [تایید|انصراف] [کد تخفیف] [ناوبری] [منو]
    if nav:
        kb.adjust(2, 1, nav, 1)
    else:
        kb.adjust(2, 1, 1)
    return kb.as_markup()


def wallet_amounts(presets: tuple[int, ...] = (50_000, 100_000, 200_000), crypto: bool = False,
                   stars: bool = False) -> InlineKeyboardMarkup:
    """کیف پول کاربر فارسی: مبلغ های کارت به کارت، و بقیه روش ها زیرش."""
    kb = InlineKeyboardBuilder()
    for amount in presets:
        kb.button(text=f"{amount:,}", callback_data=f"wal:c:{amount}")
    _add(kb, "✍️ مبلغ دلخواه", style=PRIMARY, callback_data="wal:custom")
    _btn(kb, "history", "سوابق من", callback_data="hist")
    rows = [3, 2]
    other = []
    if crypto:
        _add(kb, "💎 پرداخت با TON / USDT", callback_data="cw")
        other.append(1)
    if stars:
        _add(kb, "⭐ پرداخت با Stars", callback_data="sw")
        other.append(1)
    if len(other) == 2:
        other = [2]
    _add(kb, "🔙 منوی اصلی", callback_data="menu")
    kb.adjust(*rows, *other, 1)
    return kb.as_markup()


def wallet_methods(crypto: bool, stars: bool) -> InlineKeyboardMarkup:
    """کیف پول کاربر غیر فارسی: کارت به کارت ندارد، فقط کریپتو و Stars."""
    kb = InlineKeyboardBuilder()
    rows = []
    if crypto:
        _add(kb, "💎 پرداخت با TON / USDT", style=PRIMARY, callback_data="cw")
        rows.append(1)
    if stars:
        _add(kb, "⭐ پرداخت با Stars", style=PRIMARY, callback_data="sw")
        rows.append(1)
    _btn(kb, "history", "سوابق من", callback_data="hist")
    _add(kb, "🔙 منوی اصلی", callback_data="menu")
    kb.adjust(*rows, 2)
    return kb.as_markup()


def stars_amounts(rate: int, presets: tuple[int, ...] = (50_000, 100_000, 200_000)) -> InlineKeyboardMarkup:
    import math

    kb = InlineKeyboardBuilder()
    for amount in presets:
        kb.button(text=f"{amount:,} · ⭐{max(1, math.ceil(amount / rate)):,}", callback_data=f"sw:a:{amount}")
    _add(kb, "✍️ مبلغ دلخواه", style=PRIMARY, callback_data="sw:custom")
    _add(kb, "🔙 برگشت", callback_data="wal")
    kb.adjust(1, 1, 1, 1, 1)
    return kb.as_markup()


def crypto_amounts(presets: tuple[int, ...] = (50_000, 100_000, 200_000)) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for amount in presets:
        kb.button(text=f"{amount:,}", callback_data=f"cw:a:{amount}")
    _add(kb, "✍️ مبلغ دلخواه", style=PRIMARY, callback_data="cw:custom")
    _add(kb, "🔙 برگشت", callback_data="wal")
    kb.adjust(3, 1, 1)
    return kb.as_markup()


def crypto_assets(amount: int, quotes: dict) -> InlineKeyboardMarkup:
    """یک دکمه برای هر ارزی که نرخ دارد، با مبلغش روی خود دکمه."""
    kb = InlineKeyboardBuilder()
    icons = {"TON": "💎", "USDT": "💵"}
    for asset, q in quotes.items():
        _add(kb, f"{icons.get(asset, '•')} {q['amount']} {asset}", style=PRIMARY,
             callback_data=f"cw:p:{amount}:{asset}")
    _add(kb, "🔙 برگشت", callback_data="cw")
    kb.adjust(*([1] * (len(quotes) + 1)))
    return kb.as_markup()


def crypto_invoice_kb(inv: dict, link: str, address: str, amount: str, webapp_url: str = "") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    rows = []
    _add(kb, "💎 پرداخت با Tonkeeper", style=SUCCESS, url=link)
    rows.append(1)
    if webapp_url:
        from aiogram.types import WebAppInfo

        _add(kb, "📱 پرداخت با TON Connect", web_app=WebAppInfo(url=webapp_url))
        rows.append(1)
    _add(kb, "کپی آدرس", copy_text=CopyTextButton(text=address))
    _add(kb, "کپی مبلغ", copy_text=CopyTextButton(text=amount))
    _add(kb, "کپی کامنت", copy_text=CopyTextButton(text=inv["code"]))
    rows.append(3)
    _add(kb, "🔄 بررسی پرداخت", callback_data=f"cw:chk:{inv['id']}")
    _add(kb, "❌ انصراف", style=DANGER, callback_data=f"cw:x:{inv['id']}")
    rows.append(2)
    kb.adjust(*rows)
    return kb.as_markup()


def amount_confirm_kb(amount: int) -> InlineKeyboardMarkup:
    """تایید مبلغ اختصاصی پیش از نمایش کارت.

    این مرحله باعث می شود کاربر واقعا متن را بخواند و بعدا نگوید
    نمی دانستم باید دقیق واریز کنم.
    """
    kb = InlineKeyboardBuilder()
    _add(kb, "✅ خوندم، ادامه", style=SUCCESS, icon="ok", callback_data=f"wal:go:{amount}")
    _add(kb, "🔙 مبلغ دیگه", callback_data="wal")
    kb.adjust(1, 1)
    return kb.as_markup()


def card_kb_v2(card_number: str, amount: int, txn_id: int) -> InlineKeyboardMarkup:
    """اطلاعات کارت + دکمه «واریز کردم» و لغو.

    با زدن «واریز کردم» زمان ثبت می شود و اگر تا ۱۰ دقیقه رسید نیاید،
    cron یک یادآوری می فرستد. لغو، یادآوری را متوقف و مبلغ را آزاد می کند.
    """
    kb = InlineKeyboardBuilder()
    _add(kb, "کپی شماره کارت", copy_text=CopyTextButton(text=card_number))
    _add(kb, "کپی مبلغ (ریال)", copy_text=CopyTextButton(text=str(amount * 10)))
    _add(kb, "✅ واریز کردم", style=SUCCESS, callback_data=f"wal:paid:{txn_id}")
    _add(kb, "❌ انصراف", style=DANGER, callback_data=f"wal:cancel:{txn_id}")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def awaiting_receipt_kb(txn_id: int) -> InlineKeyboardMarkup:
    """بعد از «واریز کردم»: فقط انصراف باقی می ماند."""
    kb = InlineKeyboardBuilder()
    _add(kb, "❌ انصراف", style=DANGER, callback_data=f"wal:cancel:{txn_id}")
    return kb.as_markup()


def card_kb(card_number: str, amount: int) -> InlineKeyboardMarkup:
    """دکمه های کپی کارت و مبلغ.

    مبلغ به ریال کپی می شود چون اپ های بانکی ریالی هستند. متن پیام
    تومان را هم نشان می دهد. ایموجی روی دکمه ها نیست، چون دکمه کپی
    خودش آیکن دارد.
    """
    kb = InlineKeyboardBuilder()
    _add(kb, "کپی شماره کارت", copy_text=CopyTextButton(text=card_number))
    _add(kb, "کپی مبلغ (ریال)", copy_text=CopyTextButton(text=str(amount * 10)))
    _add(kb, "🔙 منوی اصلی", callback_data="menu")
    kb.adjust(2, 1)
    return kb.as_markup()


def services_kb(services: list[dict]) -> InlineKeyboardMarkup:
    """لیست سرویس ها با نشانگر وضعیت روی هر دکمه.

    ایموجی وضعیت ابتدای متن دکمه می نشیند، پس اگر ادمین برای 🟢 یا 🟠
    یا 🔴 ایموجی پریمیوم تنظیم کرده باشد، _add خودش تشخیص می دهد و به
    شکل آیکن دکمه نمایش می دهد.
    """
    from app import texts
    from app.utils import service_status

    kb = InlineKeyboardBuilder()
    for s in services:
        name = (s.get("label") or "").strip() or f"سرویس {s['id']}"
        dot = texts.SVC_DOT[
            service_status(s.get("expire_at"), duration_days=s.get("duration_days"))
        ]
        _add(kb, f"{dot} {name} · {s['data_gb']} {_t('گیگ')}", callback_data=f"svc:v:{s['id']}")
    _add(kb, "🛒 خرید سرویس جدید", style=PRIMARY, callback_data="buy")
    _add(kb, "🔙 منوی اصلی", callback_data="menu")
    kb.adjust(1)
    return kb.as_markup()


def service_detail_kb(
    service_id: int, sub_url: str, deletable: bool = False
) -> InlineKeyboardMarkup:
    """چیدمان جزئیات سرویس: پرکاربردترین کارها بالا و جفت جفت کنار هم.

    قبلا هر دکمه یک ردیف جدا بود (تا هشت ردیف)، که روی موبایل خیلی
    طولانی می شد. اینجا بر اساس کاربرد گروه بندی شده: باز کردن/کپی
    لینک با هم، اتصال سریع و تمدید (پرکاربردترین اقدام ها) با هم،
    مصرف و دستگاه ها (نظارتی) با هم، QR و تغییر نام (فرعی) با هم؛
    آپدیت لینک و حذف چون حساس ترند تنها می مانند.
    """
    kb = InlineKeyboardBuilder()
    rows: list[int] = []

    if sub_url and sub_url.startswith(("http://", "https://")):
        _add(kb, "🌐 باز کردن لینک", style=PRIMARY, url=sub_url)
        _add(kb, "کپی لینک", copy_text=CopyTextButton(text=sub_url))
        rows.append(2)
    elif sub_url:
        _add(kb, "کپی لینک", copy_text=CopyTextButton(text=sub_url))
        rows.append(1)

    _add(kb, "⚡️ اتصال سریع", style=PRIMARY, callback_data=f"cn:{service_id}")
    _add(kb, "♻️ تمدید", style=SUCCESS, callback_data=f"svc:rnw:{service_id}")
    rows.append(2)

    _add(kb, "📈 مصرف", callback_data=f"svc:use:{service_id}")
    _add(kb, "📱 دستگاه ها", callback_data=f"svc:dev:{service_id}")
    rows.append(2)

    _add(kb, "📷 QR", callback_data=f"svc:qr:{service_id}")
    _add(kb, "✏️ تغییر نام", callback_data=f"svc:nm:{service_id}")
    rows.append(2)

    _btn(kb, "relink", "آپدیت و لینک جدید", callback_data=f"svc:relink:{service_id}")
    rows.append(1)
    if deletable:
        _btn(kb, "trash", "حذف سرویس", style=DANGER, callback_data=f"svc:del:{service_id}")
        rows.append(1)
    _add(kb, "🔙 سرویس های من", callback_data="svc")
    rows.append(1)

    kb.adjust(*rows)
    return kb.as_markup()


def renew_confirm_kb(service_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "✅ تایید تمدید", style=SUCCESS, callback_data=f"svc:rnwok:{service_id}")
    _add(kb, "❌ انصراف", style=DANGER, callback_data=f"svc:v:{service_id}")
    kb.adjust(2)
    return kb.as_markup()


def qr_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "🔙 بازگشت", callback_data="svc")
    return kb.as_markup()


# ---------- ادمین ----------
def admin_dash_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "💳 شارژهای در انتظار", callback_data="adm:chg")
    _add(kb, "👤 مدیریت کاربر", callback_data="adm:usr")
    _add(kb, "📂 پلن ها و دسته ها", callback_data="adm:cats")
    _add(kb, "🎟 کد تخفیف", callback_data="adm:dsc")
    _add(kb, "👥 لیست کاربران", callback_data="adm:ulist:0:recent")
    _add(kb, "📢 پیام همگانی", callback_data="adm:bc")
    _btn(kb, "chart", "نظرسنجی ها", callback_data="adm:polls")
    _btn(kb, "megaphone", "پست در کانال", callback_data="adm:ch")
    _add(kb, "🎛 تنظیمات", callback_data="adm:set")
    _add(kb, "🔄 بروزرسانی", callback_data="adm")
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()


POLL_LAYOUTS = {"vertical": "عمودی (هر گزینه یک ردیف)", "horizontal": "افقی (دوتایی)"}


def admin_polls_kb(polls: list[dict]) -> InlineKeyboardMarkup:
    """فهرست نظرسنجی ها در پنل ادمین."""
    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    for p in polls[:10]:
        mark = "🟢" if p.get("is_open") else "⚪️"
        _add(
            kb,
            f"{mark} {p['question'][:28]} · {p.get('votes', 0)}",
            callback_data=f"adm:pollv:{p['id']}",
        )
        rows.append(1)
    _add(kb, "➕ نظرسنجی تازه", style=SUCCESS, callback_data="adm:pollnew")
    _add(kb, "🔙 پنل", callback_data="adm")
    rows.append(2)
    kb.adjust(*rows)
    return kb.as_markup()


def admin_poll_kb(poll_id: int, is_open: bool) -> InlineKeyboardMarkup:
    """مدیریت یک نظرسنجی."""
    kb = InlineKeyboardBuilder()
    _add(kb, "📢 فرستادن به همه", style=PRIMARY, callback_data=f"adm:pollbc:{poll_id}")
    _btn(kb, "megaphone", "پست در کانال", callback_data=f"adm:pollch:{poll_id}")
    _add(
        kb,
        ("🔒 بستن رای گیری" if is_open else "🔓 باز کردن دوباره"),
        style=None if is_open else SUCCESS,
        callback_data=f"adm:polltog:{poll_id}",
    )
    _add(kb, "🎨 چیدمان و رنگ", callback_data=f"adm:pollfmt:{poll_id}")
    _add(kb, "🔄 بروزرسانی", callback_data=f"adm:pollv:{poll_id}")
    _add(kb, "🔙 نظرسنجی ها", callback_data="adm:polls")
    kb.adjust(2, 2, 2)
    return kb.as_markup()


def admin_poll_format_kb(poll_id: int) -> InlineKeyboardMarkup:
    """چیدمان (افقی/عمودی) و رنگ دکمه های نظرسنجی."""
    kb = InlineKeyboardBuilder()
    for key, title in POLL_LAYOUTS.items():
        _add(kb, title, callback_data=f"adm:polllay:{poll_id}:{key}")
    for key, title in BROADCAST_STYLES.items():
        style = None if key == "none" else key
        _add(kb, title, style=style, callback_data=f"adm:pollcol:{poll_id}:{key}")
    _add(kb, "🔙 برگشت", callback_data=f"adm:pollv:{poll_id}")
    kb.adjust(1, 1, 2, 2, 1)
    return kb.as_markup()


def admin_channel_kb(has_channel: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if has_channel:
        _add(kb, "✍️ پست تازه", style=PRIMARY, callback_data="adm:chnew")
    _add(kb, "🔄 بروزرسانی", callback_data="adm:ch")
    _add(kb, "🔙 پنل", callback_data="adm")
    kb.adjust(1, 2) if has_channel else kb.adjust(2)
    return kb.as_markup()


def admin_channels_kb(channels: list[dict], active: str) -> InlineKeyboardMarkup:
    """انتخاب کانال فعال از بین کانال هایی که ربات ادمینشان است."""
    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    for c in channels[:10]:
        is_active = str(c["chat_id"]) == str(active)
        _add(
            kb,
            f"{'✅ ' if is_active else ''}{c['title'] or c['chat_id']}"[:40],
            style=PRIMARY if is_active else None,
            callback_data=f"adm:chpick:{c['chat_id']}",
        )
        rows.append(1)
    if active:
        _add(kb, "✍️ پست تازه", style=SUCCESS, callback_data="adm:chnew")
        rows.append(1)
    _add(kb, "🔄 بروزرسانی", callback_data="adm:ch")
    _add(kb, "🔙 پنل", callback_data="adm")
    rows.append(2)
    kb.adjust(*rows)
    return kb.as_markup()


def admin_user_reset_kb(telegram_id: int) -> InlineKeyboardMarkup:
    """تایید دو مرحله ای پاک کردن کاربر - چون برگشت پذیر نیست."""
    kb = InlineKeyboardBuilder()
    _add(
        kb,
        "🗑 فقط ریست ربات",
        style=DANGER,
        callback_data=f"adm:ureset:{telegram_id}:soft",
    )
    _btn(
        kb,
        "purge",
        "ریست + حذف از پنل",
        style=DANGER,
        callback_data=f"adm:ureset:{telegram_id}:hard",
    )
    _add(kb, "🔙 انصراف", callback_data=f"adm:u:{telegram_id}")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def admin_pending_kb(items: list[dict]) -> InlineKeyboardMarkup:
    """فهرست شارژهای در انتظار، هر کدام یک دکمه شیشه ای.

    با زدن هر دکمه، خود رسید (عکس) دوباره با دکمه های تایید/رد فرستاده
    می شود - تا ادمین لازم نباشد لای پیام های قدیمی ربات دنبال فیش بگردد.
    """
    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    for t in items[:10]:
        name = (t.get("first_name") or "-").strip()[:14]
        _add(
            kb,
            f"💳 {name} · {t['amount']:,}",
            style=PRIMARY,
            callback_data=f"adm:chgv:{t['id']}",
        )
        rows.append(1)
    _add(kb, "🔄 بروزرسانی", callback_data="adm:chg")
    _add(kb, "🔙 پنل", callback_data="adm")
    rows.append(2)
    kb.adjust(*rows)
    return kb.as_markup()


def admin_charge_kb(txn_id: int, from_panel: bool = False) -> InlineKeyboardMarkup:
    """دکمه های تصمیم روی یک رسید.

    from_panel یعنی این رسید از فهرست پنل باز شده (نه پیام خودکار لحظه
    واریز)، پس یک راه برگشت به همان فهرست هم لازم دارد.
    """
    kb = InlineKeyboardBuilder()
    _add(kb, "✅ تأیید", style=SUCCESS, callback_data=f"chg:ok:{txn_id}")
    _add(kb, "❌ رد", style=DANGER, callback_data=f"chg:no:{txn_id}")
    _add(kb, "🔁 رسید تکراری", callback_data=f"chg:dup:{txn_id}")
    rows = [2, 1]
    if from_panel:
        _add(kb, "🔙 فهرست در انتظار", callback_data="adm:chg")
        rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()


def admin_reject_reasons_kb(txn_id: int) -> InlineKeyboardMarkup:
    """دلایل آماده رد رسید + گزینه دلیل دلخواه.

    دکمه برگشت به همان سه دکمه تایید/رد/تکراری برمی گردد (chg:back)،
    نه به لیست شارژهای در انتظار - چون پیام رسید یک عکس است و آن
    لیست با edit_text روی عکس خطا می دهد.
    """
    kb = InlineKeyboardBuilder()
    _add(kb, "مبلغ نمی خونه", callback_data=f"chg:no:{txn_id}:amount")
    _add(kb, "رسید ناخوانا", callback_data=f"chg:no:{txn_id}:unreadable")
    _add(kb, "رسید نامعتبر", callback_data=f"chg:no:{txn_id}:invalid")
    _add(kb, "✍️ دلیل دستی", style=PRIMARY, callback_data=f"chg:no:{txn_id}:custom")
    _add(kb, "🔙 انصراف", callback_data=f"chg:back:{txn_id}")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def admin_user_kb(telegram_id: int, blocked: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "💰 شارژ دستی", callback_data=f"adm:uadd:{telegram_id}")
    _add(kb, "➖ کسر دستی", callback_data=f"adm:usub:{telegram_id}")
    if blocked:
        _add(kb, "✅ رفع مسدودی", callback_data=f"adm:ub:{telegram_id}")
    else:
        _add(kb, "🚫 مسدود", callback_data=f"adm:ub:{telegram_id}")
    _add(kb, "🌐 سرویس های کاربر", style=PRIMARY, callback_data=f"adm:usvc:{telegram_id}")
    _add(kb, "🗑 پاک کردن کاربر", style=DANGER, callback_data=f"adm:uresetask:{telegram_id}")
    _add(kb, "👥 لیست کاربران", callback_data="adm:ulist:0:recent")
    _add(kb, "🔎 جستجوی جدید", callback_data="adm:usr")
    kb.adjust(2, 1, 1, 1, 2)
    return kb.as_markup()


def admin_user_services_kb(telegram_id: int, services: list[dict]) -> InlineKeyboardMarkup:
    """فهرست سرویس های یک کاربر در پنل ادمین."""
    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    for sv in services[:10]:
        label = (sv.get("label") or "").strip() or f"سرویس {sv['id']}"
        _add(kb, f"🌐 {label}", callback_data=f"adm:svcv:{sv['id']}")
        rows.append(1)
    _add(kb, "🔙 کاربر", callback_data=f"adm:u:{telegram_id}")
    rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()


def admin_service_kb(service_id: int, telegram_id: int, sub_url: str) -> InlineKeyboardMarkup:
    """جزئیات یک سرویس از دید ادمین: کپی لینک ساب + برگشت."""
    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    if sub_url:
        _add(kb, "کپی لینک ساب", copy_text=CopyTextButton(text=sub_url))
        rows.append(1)
        if sub_url.startswith(("http://", "https://")):
            _add(kb, "🌐 باز کردن لینک", url=sub_url)
            rows.append(1)
    _add(kb, "🔄 بروزرسانی", callback_data=f"adm:svcv:{service_id}")
    _add(kb, "🔙 سرویس ها", callback_data=f"adm:usvc:{telegram_id}")
    rows.append(2)
    kb.adjust(*rows)
    return kb.as_markup()


def admin_broadcast_ask_kb() -> InlineKeyboardMarkup:
    """کیبورد صفحه «منتظر پیام منبع». فقط انصراف - چون هر پیامی که
    ادمین در این حالت بفرستد به عنوان محتوای همگانی گرفته می شود، نباید
    منوی کامل ادمین این وسط باشد که کلیک اشتباه به state گیر بیفتد."""
    kb = InlineKeyboardBuilder()
    _add(kb, "❌ انصراف", style=DANGER, callback_data="adm:bccancel")
    kb.adjust(1)
    return kb.as_markup()


def admin_broadcast_builder_kb(has_button: bool, has_forward_src: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(
        kb,
        "🔘 تغییر دکمه" if has_button else "🔘 افزودن دکمه",
        callback_data="adm:bcbtn",
    )
    if has_button:
        _add(kb, "✏️ عنوان دکمه", callback_data="adm:bclabel")
        _add(kb, "🎨 رنگ دکمه", callback_data="adm:bcbtn:style")
        _add(kb, "🚫 حذف دکمه", style=DANGER, callback_data="adm:bcbtnrm")
    _add(kb, "📌 پین/آن پین", callback_data="adm:bcpin")
    if has_forward_src:
        _add(kb, "📤 حالت نمایش منبع", callback_data="adm:bcsrc")
    _add(kb, "✅ ارسال به همه", style=SUCCESS, callback_data="adm:bcsend")
    _add(kb, "❌ انصراف", style=DANGER, callback_data="adm")
    # با دکمه: [تغییر دکمه] / [عنوان، رنگ] / [حذف] / [پین]
    rows = [1, 2, 1, 1] if has_button else [1, 1]
    if has_forward_src:
        rows.append(1)
    rows += [1, 1]
    kb.adjust(*rows)
    return kb.as_markup()


# صفحه های داخلی ربات که می شود دکمه شان را زیر پیام همگانی گذاشت.
# کلید: (callback_data, عنوان پیش فرض دکمه)
BROADCAST_DESTS: dict[str, tuple[str, str]] = {
    "shop": ("buy", "🛒 خرید سرویس"),
    "loc": ("loc", "🌍 سرورها و لوکیشن ها"),
    "ref": ("ref", "🤝 دعوت دوستان و پاداش"),
    "trial": ("trial", "🎁 تست رایگان"),
    "svc": ("svc", "🌐 سرویس های من"),
    "wal": ("wal", "💰 شارژ کیف پول"),
    "cst": ("cst", "🎛 ساخت سرویس دلخواه"),
    "guide": ("guide", "📚 راهنمای اتصال"),
    "sup": ("sup", "💬 پشتیبانی"),
    "menu": ("menu", "🏠 منوی اصلی"),
}

# رنگ های ممکن برای دکمه شیشه ای
BROADCAST_STYLES: dict[str, str] = {
    "none": "بدون رنگ",
    PRIMARY: "آبی",
    SUCCESS: "سبز",
    DANGER: "قرمز",
}


def admin_broadcast_btn_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _btn(kb, "page", "صفحه های ربات", style=PRIMARY, callback_data="adm:bcbtn:page")
    _add(kb, "🔗 دکمه لینک", callback_data="adm:bcbtn:url")
    _add(kb, "🛒 دکمه خرید پلن", callback_data="adm:bcbtn:plan")
    _add(kb, "🔙 انصراف", callback_data="adm:bcback")
    kb.adjust(1, 2, 1)
    return kb.as_markup()


def admin_broadcast_page_pick_kb() -> InlineKeyboardMarkup:
    """انتخاب اینکه دکمه پیام همگانی کاربر را به کدام صفحه ربات ببرد."""
    kb = InlineKeyboardBuilder()
    for key, (_cb, title) in BROADCAST_DESTS.items():
        _add(kb, title, callback_data=f"adm:bcpage:{key}")
    _add(kb, "🔙 انصراف", callback_data="adm:bcback")
    kb.adjust(2, 2, 2, 2, 2, 2, 1)
    return kb.as_markup()


def admin_broadcast_style_kb() -> InlineKeyboardMarkup:
    """انتخاب رنگ دکمه."""
    kb = InlineKeyboardBuilder()
    for key, title in BROADCAST_STYLES.items():
        style = None if key == "none" else key
        _add(kb, title, style=style, callback_data=f"adm:bcstyle:{key}")
    _add(kb, "🔙 برگشت", callback_data="adm:bcback")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def single_url_button(
    label: str, url: str, style: str | None = None
) -> InlineKeyboardMarkup:
    """یک دکمه لینک تکی زیر پیام همگانی، با رنگ دلخواه."""
    kb = InlineKeyboardBuilder()
    _add(kb, label[:64], style=style, url=url)
    kb.adjust(1)
    return kb.as_markup()


def single_callback_button(
    label: str, callback_data: str, style: str | None = None
) -> InlineKeyboardMarkup:
    """یک دکمه کال بک تکی زیر پیام همگانی، با رنگ دلخواه."""
    kb = InlineKeyboardBuilder()
    _add(kb, label[:64], style=style, callback_data=callback_data)
    kb.adjust(1)
    return kb.as_markup()


def admin_broadcast_plan_pick_kb(plans: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in plans:
        _add(kb, f"{p['title']} · {p['price']:,} تومان", callback_data=f"adm:bcplan:{p['id']}")
    _add(kb, "🔙 انصراف", callback_data="adm:bcback")
    kb.adjust(1)
    return kb.as_markup()


def admin_setting_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "💳 شماره کارت", callback_data="adm:set:card_number")
    _add(kb, "👤 صاحب کارت", callback_data="adm:set:card_holder")
    _add(kb, "🏦 بانک", callback_data="adm:set:bank_name")
    _add(kb, "🔢 حداقل شارژ", callback_data="adm:set:min_charge")
    _add(kb, "⭐ نرخ ستاره", callback_data="adm:set:stars_rate")
    _add(kb, "💵 نرخ تتر", callback_data="adm:set:crypto_usdt_rate")
    _add(kb, "💎 نرخ TON", callback_data="adm:set:crypto_ton_rate")
    _add(kb, "➗ کارمزد کریپتو", callback_data="adm:set:crypto_fee_percent")
    _add(kb, "🌐 گروه های پنل", callback_data="adm:groups")
    _add(kb, "🎨 ایموجی ها", callback_data="adm:emo")
    _add(kb, "♨️ قوانین", callback_data="adm:rules")
    _btn(kb, "winback", "پیام برگشت", callback_data="adm:wb")
    _btn(kb, "toggle", "بخش های ربات", callback_data="adm:feat")
    _btn(kb, "ai", "خدمات هوش مصنوعی", callback_data="adm:ai")
    _add(kb, "🎬 افکت پیام", callback_data="adm:fx")
    _add(kb, "🔙 داشبورد", callback_data="adm")
    kb.adjust(2, 2, 2, 2, 2, 2, 2, 1)
    return kb.as_markup()


def admin_effects_kb(sources: dict) -> InlineKeyboardMarkup:  # noqa: ANN001
    """لیست سه جایگاه افکت با وضعیت فعلی هر کدام."""
    kb = InlineKeyboardBuilder()
    labels = {
        "trial": "🎁 تست رایگان",
        "charge": "💰 شارژ کیف پول",
        "purchase": "🎉 خرید و تمدید سرویس",
    }
    for kind, label in labels.items():
        tag = "✨" if sources.get(kind) else ""
        _add(kb, f"{tag} {label}".strip(), callback_data=f"adm:fx:{kind}")
    _add(kb, "🔙 تنظیمات", callback_data="adm:set")
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()


def admin_effect_edit_kb(kind: str, has_override: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "🎬 ارسال پیام با افکت جدید", callback_data=f"adm:fxset:{kind}")
    if has_override:
        _add(kb, "↩️ برگشت به مقدار env", style=DANGER, callback_data=f"adm:fxclear:{kind}")
    _add(kb, "🔙 لیست افکت ها", callback_data="adm:fx")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def admin_effect_capture_kb(kind: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "❌ انصراف", callback_data=f"adm:fx:{kind}")
    kb.adjust(1)
    return kb.as_markup()


def insufficient_kb() -> InlineKeyboardMarkup:
    """موجودی کم: میان بر شارژ (بخش ۵.۲ سند)."""
    kb = InlineKeyboardBuilder()
    _add(kb, "💰 شارژ کیف پول", callback_data="wal")
    _add(kb, "🔙 فروشگاه", callback_data="buy")
    kb.adjust(1, 1)
    return kb.as_markup()


# ---------- تست رایگان ----------
def trial_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "🎁 فعالش کن", callback_data="trial:ok")
    _add(kb, "🔙 منوی اصلی", callback_data="menu")
    kb.adjust(1, 1)
    return kb.as_markup()


def trial_after_kb() -> InlineKeyboardMarkup:
    """بعد از تست: هدایت به فروشگاه (بخش ۱۳ سند)."""
    kb = InlineKeyboardBuilder()
    _add(kb, "🛒 دیدن پلن ها", callback_data="buy:vpn")
    _add(kb, "📚 راهنمای اتصال", callback_data="guide")
    kb.adjust(1, 1)
    return kb.as_markup()


# ---------- ساخت دلخواه ----------
CUSTOM_GB_STEPS = [5, 10, 15, 20, 30, 50, 75, 100]
CUSTOM_DAY_STEPS = [1, 3, 7, 14, 30, 60, 90, 180]


def custom_builder_kb(gb: int, days: int) -> InlineKeyboardMarkup:
    """اسلایدر حجم و مدت با قیمت زنده (بخش ۵.۲ سند)."""
    kb = InlineKeyboardBuilder()
    gi = CUSTOM_GB_STEPS.index(gb) if gb in CUSTOM_GB_STEPS else 1
    di = CUSTOM_DAY_STEPS.index(days) if days in CUSTOM_DAY_STEPS else 0

    from app import emoji as emo

    _btn(kb, "minus", alt="کمتر", callback_data=f"cst:gb:{max(gi - 1, 0)}:{di}")
    _spacer(kb, f"{emo.default('data')} {gb} {_t('گیگ')}")
    _btn(
        kb,
        "plus",
        alt="بیشتر",
        callback_data=f"cst:gb:{min(gi + 1, len(CUSTOM_GB_STEPS) - 1)}:{di}",
    )

    _btn(kb, "minus", alt="کمتر", callback_data=f"cst:dy:{gi}:{max(di - 1, 0)}")
    _spacer(kb, f"{emo.default('calendar')} {_fmt_days(days)}")
    _btn(
        kb,
        "plus",
        alt="بیشتر",
        callback_data=f"cst:dy:{gi}:{min(di + 1, len(CUSTOM_DAY_STEPS) - 1)}",
    )

    _btn(kb, "ok", "تایید و خرید", style=SUCCESS, callback_data=f"cst:ok:{gi}:{di}")
    _btn(kb, "back", "فروشگاه", callback_data="buy")
    kb.adjust(3, 3, 1, 1)
    return kb.as_markup()


def devices_kb(service_id: int, has_devices: bool) -> InlineKeyboardMarkup:
    """صفحه دستگاه های متصل."""
    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    if has_devices:
        _btn(kb, "door", "خروج همه دستگاه ها", style=DANGER, callback_data=f"svc:devout:{service_id}")
        rows.append(1)
    _btn(kb, "secure", "خروج و لینک تازه", style=DANGER, callback_data=f"svc:devnew:{service_id}")
    rows.append(1)
    _add(kb, "🔄 بروزرسانی", callback_data=f"svc:dev:{service_id}")
    _add(kb, "🔙 سرویس", callback_data=f"svc:v:{service_id}")
    rows.append(2)
    kb.adjust(*rows)
    return kb.as_markup()


def devices_kick_kb(service_id: int) -> InlineKeyboardMarkup:
    """تایید خروج همه دستگاه ها."""
    kb = InlineKeyboardBuilder()
    _btn(kb, "door", "بله، همه رو خارج کن", style=DANGER, callback_data=f"svc:devoutok:{service_id}")
    _add(kb, "🔐 خروج و لینک تازه", callback_data=f"svc:devnew:{service_id}")
    _add(kb, "🔙 انصراف", callback_data=f"svc:dev:{service_id}")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def devices_reset_kb(service_id: int) -> InlineKeyboardMarkup:
    """تایید خروج همه دستگاه ها همراه با لینک تازه."""
    kb = InlineKeyboardBuilder()
    _add(kb, "🔐 بله، امنش کن", style=DANGER, callback_data=f"svc:devnewok:{service_id}")
    _add(kb, "🔙 انصراف", callback_data=f"svc:dev:{service_id}")
    kb.adjust(1, 1)
    return kb.as_markup()


def service_relink_kb(service_id: int) -> InlineKeyboardMarkup:
    """تایید ابطال لینک ساب."""
    kb = InlineKeyboardBuilder()
    _btn(kb, "relink", "بله، لینک جدید بده", style=DANGER, callback_data=f"svc:relinkok:{service_id}")
    _add(kb, "🔙 انصراف", callback_data=f"svc:v:{service_id}")
    kb.adjust(1, 1)
    return kb.as_markup()


def service_delete_kb(service_id: int) -> InlineKeyboardMarkup:
    """تایید حذف سرویس."""
    kb = InlineKeyboardBuilder()
    _btn(kb, "trash", "بله، حذف کن", style=DANGER, callback_data=f"svc:delok:{service_id}")
    _add(kb, "🔙 انصراف", callback_data=f"svc:v:{service_id}")
    kb.adjust(1, 1)
    return kb.as_markup()


def service_name_kb(cancel_data: str, skip_data: str = "nm:skip") -> InlineKeyboardMarkup:
    """کیبورد مرحله انتخاب اسم سرویس (قبل از پرداخت)."""
    kb = InlineKeyboardBuilder()
    _add(kb, "⏭ بدون اسم، خودت انتخاب کن", callback_data=skip_data)
    _add(kb, "🔙 برگشت", callback_data=cancel_data)
    kb.adjust(1, 1)
    return kb.as_markup()


def custom_confirm_kb(gi: int, di: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "✅ تایید و خرید", callback_data=f"cst:go:{gi}:{di}")
    _add(kb, "🔙 برگشت", callback_data=f"cst:gb:{gi}:{di}")
    kb.adjust(1, 1)
    return kb.as_markup()


# ---------- راهنما ----------
def guide_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "📱 اندروید", callback_data="gd:android")
    _add(kb, "🍎 آیفون", callback_data="gd:ios")
    _add(kb, "💻 ویندوز", callback_data="gd:windows")
    _add(kb, "🖥 مک", callback_data="gd:mac")
    _add(kb, "❓ سوالات پرتکرار", callback_data="faq")
    _add(kb, "🔙 منوی اصلی", callback_data="menu")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def guide_back_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "🔙 راهنما", callback_data="guide")
    _add(kb, "🏠 منوی اصلی", callback_data="menu")
    kb.adjust(2)
    return kb.as_markup()


def faq_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "🐢 سرعت کمه", callback_data="faq:slow")
    _add(kb, "🔌 وصل نمی شه", callback_data="faq:notwork")
    _add(kb, "📊 حجم چطور حساب می شه", callback_data="faq:volume")
    _add(kb, "📱 چند دستگاه", callback_data="faq:devices")
    _add(kb, "🔙 راهنما", callback_data="guide")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def faq_back_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "🔙 سوالات", callback_data="faq")
    _add(kb, "🆘 پشتیبانی", callback_data="sup")
    kb.adjust(2)
    return kb.as_markup()


# ---------- هم سفرها ----------
def referral_kb(link: str, has_log: bool = False) -> InlineKeyboardMarkup:
    """دکمه دعوت هم سفر.

    switch_inline_query لیست چت های کاربر را همان جا باز می کند و متن
    دعوت را آماده می فرستد. روان تر از باز شدن مرورگر یا کپی دستی لینک است.
    """
    kb = InlineKeyboardBuilder()
    invite = f"با این لینک به عبور بپیوند و اینترنت آزاد بگیر\n{link}"
    _add(
        kb,
        "📤 دعوت از دوستان",
        style=PRIMARY,
        switch_inline_query=invite,
    )
    # کپی لینک و گزارش پاداش کنار هم: هر دو «کار بعدی» کاربر در این
    # صفحه اند، پس یک ردیف مشترک منطقی تر از دو ردیف جداست.
    _add(kb, "کپی لینک", copy_text=CopyTextButton(text=link))
    rows = [1]
    if has_log:
        _add(kb, "📜 گزارش پاداش", callback_data="ref:log")
        rows.append(2)
    else:
        rows.append(1)
    _add(kb, "🔙 منوی اصلی", callback_data="menu")
    rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()


def referral_log_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "🔙 هم سفرها", callback_data="ref")
    _add(kb, "🏠 منوی اصلی", callback_data="menu")
    kb.adjust(2)
    return kb.as_markup()


# ---------- اتصال سریع ----------
def connect_platform_kb(service_id: int) -> InlineKeyboardMarkup:
    """انتخاب دستگاه برای اتصال سریع."""
    from app.apps import PLATFORMS

    kb = InlineKeyboardBuilder()
    for key, (emoji, title, _apps) in PLATFORMS.items():
        _add(kb, f"{emoji} {title}", callback_data=f"cn:{service_id}:{key}")
    _add(kb, "📚 راهنمای کامل", callback_data="guide")
    _add(kb, "🔙 برگشت", callback_data=f"svc:v:{service_id}")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def connect_apps_kb(service_id: int, platform: str, sub_url: str, name: str = "Obour"):
    """دکمه هر برنامه + حالت پشتیبان کپی لینک.

    خروجی: (کیبورد، آیا دکمه یک کلیکی ساخته شد)

    اگر WEBHOOK_BASE_URL تنظیم نشده باشد صفحه واسط وجود ندارد، پس
    به جای دکمه، لینک اسکیم به صورت کپی شدنی داده می شود. تلگرام اجازه
    نمی دهد اسکیم دلخواه مستقیم روی دکمه url بنشیند.
    """
    from app.apps import import_link, platform_apps, scheme_url

    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    one_click = False
    for key, title in platform_apps(platform):
        url = import_link(key, sub_url, name)
        if url:
            _add(kb, f"⚡️ {title}", style=PRIMARY, url=url)
            one_click = True
        else:
            deep = scheme_url(key, sub_url, name)
            if not deep:
                continue
            _add(kb, title, copy_text=CopyTextButton(text=deep))
        rows.append(1)

    if sub_url:
        _add(kb, "کپی لینک سرویس", copy_text=CopyTextButton(text=sub_url))
        rows.append(1)
    _add(kb, "🔙 دستگاه دیگر", callback_data=f"cn:{service_id}")
    _add(kb, "🏠 منوی اصلی", callback_data="menu")
    rows.append(2)
    kb.adjust(*rows)
    return kb.as_markup(), one_click


# ---------- عضویت اجباری ----------
def join_kb(channels: list[tuple[str, str, str]], target: str = "trial") -> InlineKeyboardMarkup:
    """دکمه پیوستن به هر کانال + بررسی عضویت."""
    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    for _chat, url, title in channels:
        _add(kb, f"📣 {_t('عضویت در')} {title}", url=url)
        rows.append(1)
    _add(kb, "✅ عضو شدم", style=SUCCESS, callback_data=f"join:ck:{target}")
    _add(kb, "🔙 منوی اصلی", callback_data="menu")
    rows.append(1)
    rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()


def back_admin_kb() -> InlineKeyboardMarkup:
    """برگشت ساده به داشبورد ادمین."""
    kb = InlineKeyboardBuilder()
    _add(kb, "🔙 داشبورد", callback_data="adm")
    return kb.as_markup()


# ---------- مدیریت دسته و پلن (ادمین) ----------
def admin_cats_kb(cats: list[dict]) -> InlineKeyboardMarkup:
    """لیست دسته ها با تعداد پلن."""
    kb = InlineKeyboardBuilder()
    for c in cats:
        mark = "" if c["is_active"] else " (خاموش)"
        _add(
            kb,
            f"{c['emoji']} {c['title']} · {c['n']} پلن{mark}",
            callback_data=f"adm:cat:{c['id']}",
        )
    _add(kb, "➕ دسته جدید", style=SUCCESS, callback_data="adm:cat:new")
    _add(kb, "🔙 داشبورد", callback_data="adm")
    kb.adjust(1)
    return kb.as_markup()


def admin_cat_kb(cid: int, active: bool, first: bool, last: bool) -> InlineKeyboardMarkup:
    """مدیریت یک دسته."""
    kb = InlineKeyboardBuilder()
    _add(kb, "📋 پلن های این دسته", style=PRIMARY, callback_data=f"adm:cat:plans:{cid}")
    _add(kb, "✏️ نام", callback_data=f"adm:cat:f:title:{cid}")
    _add(kb, "😀 ایموجی", callback_data=f"adm:cat:f:emoji:{cid}")
    if not first:
        _add(kb, "⬆️ بالاتر", callback_data=f"adm:cat:mv:-1:{cid}")
    if not last:
        _add(kb, "⬇️ پایین تر", callback_data=f"adm:cat:mv:1:{cid}")
    _add(
        kb,
        "🔕 غیرفعال" if active else "🔔 فعال",
        style=DANGER if active else SUCCESS,
        callback_data=f"adm:cat:tg:{cid}",
    )
    _add(kb, "🗑 حذف دسته", style=DANGER, callback_data=f"adm:cat:del:{cid}")
    _add(kb, "🔙 دسته ها", callback_data="adm:cats")
    kb.adjust(1, 2, 2, 1, 1, 1)
    return kb.as_markup()


def admin_cat_del_kb(cid: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "✅ بله، حذف کن", style=DANGER, callback_data=f"adm:cat:del:yes:{cid}")
    _add(kb, "❌ انصراف", callback_data=f"adm:cat:{cid}")
    kb.adjust(1, 1)
    return kb.as_markup()


def admin_cat_plans_kb(cid: int, plans: list[dict]) -> InlineKeyboardMarkup:
    """پلن های یک دسته."""
    kb = InlineKeyboardBuilder()
    for p in plans:
        mark = "" if p["is_active"] else " (خاموش)"
        fire = "🔥 " if p.get("badge") else ""
        _add(
            kb,
            f"{fire}{p['title']} · {p['data_gb']}گ · {p['price']:,}{mark}",
            callback_data=f"adm:pln:{p['id']}",
        )
    _add(kb, "➕ پلن جدید", style=SUCCESS, callback_data=f"adm:pln:new:{cid}")
    _add(kb, "🔙 دسته", callback_data=f"adm:cat:{cid}")
    kb.adjust(1)
    return kb.as_markup()


def admin_plan_kb(pid: int, active: bool, badge: bool) -> InlineKeyboardMarkup:
    """مدیریت یک پلن."""
    kb = InlineKeyboardBuilder()
    _add(kb, "✏️ نام", callback_data=f"adm:pln:f:title:{pid}")
    _add(kb, "📦 حجم", callback_data=f"adm:pln:f:data_gb:{pid}")
    _add(kb, "📅 مدت", callback_data=f"adm:pln:f:duration_days:{pid}")
    _add(kb, "💰 قیمت", callback_data=f"adm:pln:f:price:{pid}")
    _add(kb, "📂 تغییر دسته", callback_data=f"adm:pln:cat:{pid}")
    _add(
        kb,
        "🔥 حذف برچسب" if badge else "🔥 پرفروش ترین",
        callback_data=f"adm:pln:badge:{pid}",
    )
    _add(
        kb,
        "🔕 غیرفعال" if active else "🔔 فعال",
        style=DANGER if active else SUCCESS,
        callback_data=f"adm:pln:tg:{pid}",
    )
    _add(kb, "🔙 برگشت", callback_data=f"adm:pln:back:{pid}")
    kb.adjust(2, 2, 1, 1, 1, 1)
    return kb.as_markup()


def admin_plan_move_kb(pid: int, cats: list[dict]) -> InlineKeyboardMarkup:
    """انتخاب دسته جدید برای پلن."""
    kb = InlineKeyboardBuilder()
    for c in cats:
        _add(kb, f"{c['emoji']} {c['title']}", callback_data=f"adm:pln:cat:set:{pid}:{c['id']}")
    _add(kb, "🔙 برگشت", callback_data=f"adm:pln:{pid}")
    kb.adjust(1)
    return kb.as_markup()


# ---------- لیست کاربران (ادمین) ----------
USER_SORTS = (
    ("recent", "🆕 جدیدترین"),
    ("balance", "💰 موجودی"),
    ("spent", "🛒 خرید"),
    ("services", "🌐 سرویس"),
)


def admin_users_kb(
    users: list[dict], page: int, total: int, per_page: int, sort: str
) -> InlineKeyboardMarkup:
    """لیست کاربران با صفحه بندی و مرتب سازی."""
    kb = InlineKeyboardBuilder()
    for u in users:
        name = (u.get("first_name") or "بی نام")[:14]
        flag = "🚫" if u["is_blocked"] else ""
        kb.button(
            text=f"{flag}{name} · {u['balance']:,}ت · {u['svc']}🌐",
            callback_data=f"adm:u:{u['telegram_id']}",
        )
    rows = [1] * len(users)

    nav = 0
    if page > 0:
        _add(kb, "⬅️ قبلی", callback_data=f"adm:ulist:{page - 1}:{sort}")
        nav += 1
    if (page + 1) * per_page < total:
        _add(kb, "بعدی ➡️", callback_data=f"adm:ulist:{page + 1}:{sort}")
        nav += 1
    if nav:
        rows.append(nav)

    for key, label in USER_SORTS:
        if key != sort:
            _add(kb, label, callback_data=f"adm:ulist:0:{key}")
    rows.append(len(USER_SORTS) - 1)

    _add(kb, "🔎 جستجو", style=PRIMARY, callback_data="adm:usr")
    _add(kb, "🔙 داشبورد", callback_data="adm")
    rows += [2]
    kb.adjust(*rows)
    return kb.as_markup()


# ---------- هشدارها ----------
def warn_kb(service_id: int) -> InlineKeyboardMarkup:
    """دکمه های پیام هشدار: مستقیم به تمدید همان سرویس."""
    kb = InlineKeyboardBuilder()
    _btn(kb, "renew", "تمدید همین سرویس", style=SUCCESS, callback_data=f"svc:rnw:{service_id}")
    _btn(kb, "user", "سرویس های من", callback_data="svc")
    kb.adjust(1, 1)
    return kb.as_markup()


def winback_kb() -> InlineKeyboardMarkup:
    """دکمه های پیام برگشت مشتری."""
    kb = InlineKeyboardBuilder()
    _btn(kb, "shop", "دیدن پلن ها", style=PRIMARY, callback_data="buy:vpn")
    _btn(kb, "chat", "سوالی دارم", callback_data="sup")
    kb.adjust(1, 1)
    return kb.as_markup()


# ---------- پشتیبانی و تیکت ----------
def support_kb(has_tickets: bool) -> InlineKeyboardMarkup:
    """چیدمان پشتیبانی: عمل اصلی تنها و برجسته، بقیه دوتا-دوتا کنار هم.

    ارسال تیکت مهم ترین کار این صفحه است، پس تنها و با رنگ اصلی می آید.
    اگر تیکت داشته باشد، تیکت های من (سبز، چون وضعیت و پیگیری نشان می دهد)
    و تاریخچه کنار هم می آیند. سوالات پرتکرار و پیگیری با کد هم یک ردیف
    دیگر. برگشت همیشه تنها و ته صفحه.
    """
    kb = InlineKeyboardBuilder()
    rows: list[int] = []

    _btn(kb, "chat", "ارسال تیکت", style=PRIMARY, callback_data="sup:new")
    rows.append(1)

    if has_tickets:
        _btn(kb, "ticket", "تیکت های من", style=SUCCESS, callback_data="sup:tk")
        _add(kb, "📋 تاریخچه گفتگو", callback_data="sup:list")
        rows.append(2)

    _add(kb, "❓ سوالات پرتکرار", callback_data="faq")
    _add(kb, "🔎 پیگیری با کد", callback_data="track")
    rows.append(2)

    _btn(kb, "back", "منوی اصلی", callback_data="menu")
    rows.append(1)

    kb.adjust(*rows)
    return kb.as_markup()


def tickets_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _btn(kb, "chat", "تیکت جدید", style=PRIMARY, callback_data="sup:new")
    _add(kb, "🔙 پشتیبانی", callback_data="sup")
    kb.adjust(1, 1)
    return kb.as_markup()


def ticket_list_kb(tickets: list[dict]) -> InlineKeyboardMarkup:
    """فهرست تیکت ها با کد روی دکمه."""
    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    for t in tickets[:8]:
        mark = {"open": "🟡", "answered": "🟢", "closed": "⚪️"}.get(
            t.get("status") or "open", "🟡"
        )
        _add(kb, f"{mark} {t.get('code') or t['id']}", callback_data=f"tk:v:{t['id']}")
        rows.append(1)
    _btn(kb, "chat", "تیکت جدید", style=PRIMARY, callback_data="sup:new")
    _add(kb, "🔙 پشتیبانی", callback_data="sup")
    rows.append(2)
    kb.adjust(*rows)
    return kb.as_markup()


def ticket_view_kb(ticket_id: int, closed: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    if not closed:
        _add(kb, "🔔 پیگیری می کنم", style=PRIMARY, callback_data=f"tk:bump:{ticket_id}")
        _add(kb, "✅ مشکلم حل شد", style=SUCCESS, callback_data=f"tk:close:{ticket_id}")
        rows.append(2)
    _add(kb, "🔙 تیکت های من", callback_data="sup:tk")
    _add(kb, "🏠 منوی اصلی", callback_data="menu")
    rows.append(2)
    kb.adjust(*rows)
    return kb.as_markup()


def track_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _btn(kb, "history", "سوابق من", callback_data="hist")
    _add(kb, "❌ انصراف", style=DANGER, callback_data="menu")
    kb.adjust(2)
    return kb.as_markup()


def track_result_kb(kind: str = "txn", ticket_id: int | None = None) -> InlineKeyboardMarkup:
    """دکمه های زیر نتیجه پیگیری."""
    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    if kind == "ticket" and ticket_id:
        _add(kb, "🎫 دیدن گفتگو", style=PRIMARY, callback_data=f"tk:v:{ticket_id}")
        rows.append(1)
    _add(kb, "🔎 کد دیگه", callback_data="track")
    _btn(kb, "history", "سوابق من", callback_data="hist")
    rows.append(2)
    _add(kb, "🏠 منوی اصلی", callback_data="menu")
    rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()


def history_kb(
    items: list[dict], kind: str, page: int, has_next: bool
) -> InlineKeyboardMarkup:
    """سوابق: هر مورد یک دکمه، به علاوه فیلتر و صفحه بندی."""
    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    for t in items:
        label = f"{t.get('code') or t['id']} · {abs(int(t['amount'])):,}"
        _add(kb, label, callback_data=f"hist:v:{t['id']}")
        rows.append(1)

    # فیلتر فعال با ایموجی و رنگ آبی مشخص می شود تا کاربر بداند الان
    # چه چیزی می بیند. قبلا فقط یک 🔹 کوچک بود که در ردیف چهارتایی
    # تقریبا دیده نمی شد.
    filters = (("all", "همه"), ("charge", "شارژ"), ("purchase", "خرید"), ("referral", "پاداش"))
    for key, title in filters:
        active = key == kind
        _add(
            kb,
            f"✅ {title}" if active else title,
            style=PRIMARY if active else None,
            callback_data=f"hist:f:{key}",
        )
    rows.append(4)

    nav = 0
    if page > 0:
        _btn(kb, "left", "جدیدتر", callback_data=f"hist:p:{kind}:{page - 1}")
        nav += 1
    if has_next:
        _btn(kb, "right", "قدیمی تر", callback_data=f"hist:p:{kind}:{page + 1}")
        nav += 1
    if nav:
        rows.append(nav)
    _add(kb, "🏠 منوی اصلی", callback_data="menu")
    rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()


def usage_kb(service_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "♻️ تمدید", style=SUCCESS, callback_data=f"svc:rnw:{service_id}")
    _add(kb, "🔙 سرویس", callback_data=f"svc:v:{service_id}")
    kb.adjust(2)
    return kb.as_markup()


def ticket_cancel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "❌ انصراف", style=DANGER, callback_data="sup")
    return kb.as_markup()


def discount_cancel_kb(plan_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "🔙 بدون تخفیف ادامه بده", callback_data=f"buy:p:{plan_id}")
    return kb.as_markup()


# ---------- کد تخفیف ----------
def admin_discounts_kb(items: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in items:
        mark = "" if d["is_active"] else " (خاموش)"
        val = f"{d['amount']}٪" if d["kind"] == "percent" else f"{d['amount']:,}ت"
        used = f"{d['used_count']}"
        if d["max_uses"]:
            used += f"/{d['max_uses']}"
        _add(kb, f"{d['code']} · {val} · {used}{mark}", callback_data=f"adm:dsc:{d['id']}")
    _add(kb, "➕ کد جدید", style=SUCCESS, callback_data="adm:dsc:new")
    _add(kb, "🔙 داشبورد", callback_data="adm")
    kb.adjust(1)
    return kb.as_markup()


def admin_discount_kb(did: int, active: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(
        kb,
        "🔕 غیرفعال" if active else "🔔 فعال",
        style=DANGER if active else SUCCESS,
        callback_data=f"adm:dsc:tg:{did}",
    )
    _add(kb, "🗑 حذف", style=DANGER, callback_data=f"adm:dsc:del:{did}")
    _add(kb, "🔙 کدها", callback_data="adm:dsc")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def admin_discount_del_kb(did: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "✅ بله، حذف کن", style=DANGER, callback_data=f"adm:dsc:del:yes:{did}")
    _add(kb, "❌ انصراف", callback_data=f"adm:dsc:{did}")
    kb.adjust(1, 1)
    return kb.as_markup()


def rules_kb() -> InlineKeyboardMarkup:
    """تایید قوانین برای کاربر جدید."""
    kb = InlineKeyboardBuilder()
    _btn(kb, "ok", "خوندم و قبول دارم", style=SUCCESS, callback_data="rules:ok")
    return kb.as_markup()


def admin_ai_kb(has_key: bool) -> InlineKeyboardMarkup:
    """تنظیمات خدمات هوش مصنوعی."""
    kb = InlineKeyboardBuilder()
    _add(kb, "🔑 کلید API", style=PRIMARY, callback_data="adm:ai:key")
    _add(kb, "💱 نرخ دلار", callback_data="adm:ai:f:ai_usd_rate")
    _add(kb, "➕ سود ثابت (تومان)", style=PRIMARY, callback_data="adm:ai:f:ai_markup_toman")
    _add(kb, "📈 درصد سود", callback_data="adm:ai:f:ai_profit_percent")
    _add(kb, "💳 درصد کارمزد", callback_data="adm:ai:f:ai_fee_percent")
    _add(kb, "🛡 حاشیه نوسان", callback_data="adm:ai:f:ai_buffer_percent")
    _add(kb, "⬇️ حداقل سود", callback_data="adm:ai:f:ai_min_profit")
    _add(kb, "🔢 رند کردن", callback_data="adm:ai:f:ai_round_to")
    if has_key:
        _add(kb, "🧮 پیش نمایش قیمت", style=SUCCESS, callback_data="adm:ai:preview")
        _add(kb, "💼 موجودی من", callback_data="adm:ai:balance")
        _btn(kb, "bell", "موجود شد، خبردار کن", style=SUCCESS, callback_data="adm:ai:restock")
    _add(kb, "🔎 سفارش های مبهم", callback_data="adm:ai:unknown")
    _add(kb, "🔙 تنظیمات", callback_data="adm:set")
    kb.adjust(1, 1, 1, 2, 2, 2, 2, 1, 2) if has_key else kb.adjust(1, 1, 1, 2, 2, 2, 1, 1)
    return kb.as_markup()


def admin_features_kb(items: list[tuple[str, str, bool]]) -> InlineKeyboardMarkup:
    """روشن/خاموش کردن بخش های ربات.

    رنگ سبز = روشن، قرمز = خاموش؛ با یک کلیک عوض می شود.
    """
    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    for key, title, on in items:
        _add(
            kb,
            f"{'🟢' if on else '🔴'} {title}",
            style=SUCCESS if on else DANGER,
            callback_data=f"adm:feat:{key}",
        )
        rows.append(1)
    _add(kb, "🔙 تنظیمات", callback_data="adm:set")
    rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()


def admin_winback_kb(has_custom: bool) -> InlineKeyboardMarkup:
    """مدیریت پیام برگشت - همان الگوی قوانین."""
    kb = InlineKeyboardBuilder()
    _add(kb, "✏️ ویرایش متن", style=PRIMARY, callback_data="adm:wb:edit")
    _add(kb, "👁 پیش نمایش", callback_data="adm:wb:preview")
    if has_custom:
        _add(kb, "↩️ برگشت به پیش فرض", style=DANGER, callback_data="adm:wb:reset")
    _add(kb, "🔙 تنظیمات", callback_data="adm:set")
    kb.adjust(2, 1, 1) if has_custom else kb.adjust(2, 1)
    return kb.as_markup()


def admin_rules_kb(enabled: bool) -> InlineKeyboardMarkup:
    """مدیریت قوانین در پنل ادمین."""
    kb = InlineKeyboardBuilder()
    _add(kb, "✏️ ویرایش متن", callback_data="adm:rules:edit")
    _add(
        kb,
        "🔕 غیرفعال کردن" if enabled else "🔔 فعال کردن",
        style=DANGER if enabled else SUCCESS,
        callback_data="adm:rules:toggle",
    )
    _add(kb, "♻️ تاییدها را پاک کن", style=DANGER, callback_data="adm:rules:reset")
    _add(kb, "👁 پیش نمایش", callback_data="adm:rules:preview")
    _add(kb, "🔙 تنظیمات", callback_data="adm:set")
    kb.adjust(1, 1, 1, 1, 1)
    return kb.as_markup()


def admin_rules_reset_confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    _add(kb, "✅ بله، پاک کن", style=DANGER, callback_data="adm:rules:reset:yes")
    _add(kb, "❌ انصراف", callback_data="adm:rules")
    kb.adjust(1, 1)
    return kb.as_markup()


# ---------- مدیریت ایموجی (پنل ادمین) ----------
def emoji_categories_kb() -> InlineKeyboardMarkup:
    """دسته های ایموجی."""
    from app import emoji as emo

    kb = InlineKeyboardBuilder()
    for cat, items in emo.titles_by_category().items():
        done = sum(1 for key, _e, _t in items if emo.custom_id(key))
        kb.button(text=f"{cat} ({done}/{len(items)})", callback_data=f"adm:emo:c:{cat}")
    _add(kb, "🔙 تنظیمات", callback_data="adm:set")
    kb.adjust(2)
    return kb.as_markup()


EMOJI_PAGE = 8


def emoji_list_kb(category: str, page: int = 0) -> InlineKeyboardMarkup:
    """ایموجی های یک دسته با صفحه بندی.

    بعضی دسته ها بیش از ده مورد دارند و فهرست بلند روی موبایل غیرقابل
    استفاده می شود، پس هر صفحه هشت مورد نشان می دهد.
    """
    from app import emoji as emo

    items = emo.titles_by_category().get(category, [])
    pages = max(1, (len(items) + EMOJI_PAGE - 1) // EMOJI_PAGE)
    page = max(0, min(page, pages - 1))
    chunk = items[page * EMOJI_PAGE : (page + 1) * EMOJI_PAGE]

    kb = InlineKeyboardBuilder()
    rows: list[int] = []
    for key, fallback, title in chunk:
        mark = "✨" if emo.custom_id(key) else ""
        _add(
            kb,
            f"{fallback} {title} {mark}".strip(),
            icon_id=emo.custom_id(key),
            callback_data=f"adm:emo:e:{key}",
        )
        rows.append(1)

    nav = 0
    if page > 0:
        _add(kb, "⬅️ قبلی", callback_data=f"adm:emo:pg:{page - 1}:{category}")
        nav += 1
    if page < pages - 1:
        _add(kb, "بعدی ➡️", callback_data=f"adm:emo:pg:{page + 1}:{category}")
        nav += 1
    if nav:
        rows.append(nav)

    _add(kb, "🔙 دسته ها", callback_data="adm:emo")
    rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()


def emoji_edit_kb(key: str, has_custom: bool) -> InlineKeyboardMarkup:
    """صفحه ویرایش یک ایموجی."""
    kb = InlineKeyboardBuilder()
    if has_custom:
        _add(kb, "↩️ بازگشت به پیش فرض", style=DANGER, callback_data=f"adm:emo:r:{key}")
    _add(kb, "🔙 برگشت", callback_data="adm:emo")
    kb.adjust(1)
    return kb.as_markup()


def is_admin(telegram_id: int) -> bool:
    return telegram_id in config.admin_ids

