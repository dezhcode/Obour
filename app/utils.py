"""ابزارهای مشترک: زمان تهران، فرمت پول، نوار مصرف."""
from __future__ import annotations

import logging
import os
import secrets

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from app.i18n import t as _t

TZ = ZoneInfo("Asia/Tehran")
GIB = 1024 ** 3


def now() -> datetime:
    return datetime.now(TZ)


def esc(value) -> str:  # noqa: ANN001
    """امن سازی متن کاربر برای parse_mode=HTML.

    نام کاربر، یوزرنیم، نام سرویس و هر متنی که از بیرون می آید باید از
    این تابع رد شود. اگر رد نشود و کاربر در نامش < یا & داشته باشد،
    تلگرام کل پیام را رد می کند (can't parse entities) و پیام هرگز
    نمی رسد - مثلا تیکت پشتیبانی به دست ادمین نمی رسد.
    """
    import html

    if value is None:
        return ""
    return html.escape(str(value), quote=False)


def now_str() -> str:
    return now().isoformat(timespec="seconds")


def after_days(days: int) -> datetime:
    return now() + timedelta(days=days)


def fmt_money(amount: int) -> str:
    return f"{amount:,}"


def remaining_days(expire_str: str | None) -> int:
    """روزهای کامل باقی مانده (رو به پایین). منقضی = صفر.

    برای تمدید استفاده می شود: فقط روزهای کامل منتقل می شوند تا عددی که
    به پنل می دهیم و عددی که در دیتابیس می نویسیم دقیقا یکی باشد.
    """
    if not expire_str:
        return 0
    seconds = _seconds_left(expire_str)
    if seconds <= 0:
        return 0
    return int(seconds // 86400)


def renew_days(expire_str: str | None, plan_days: int, keep_remaining: bool) -> int:
    """تعداد کل روزهای سرویس بعد از تمدید.

    keep_remaining=True یعنی روزهای باقی مانده سوخت نمی شوند و روی مدت
    پلن اضافه می شوند (رفتار منصفانه برای کسی که زود تمدید می کند).
    """
    if not keep_remaining:
        return plan_days
    return plan_days + remaining_days(expire_str)


def fmt_dt(value: str | datetime | None) -> str:
    if not value:
        return "-"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ)
    return value.strftime("%Y-%m-%d  %H:%M")


def days_left(expire_str: str) -> int:
    """روز باقی مانده، رو به بالا.

    قبلا از .days استفاده می شد که برای سرویس یک روزه همان لحظه صفر
    برمی گرداند و سرویس تست بلافاصله منقضی نشان داده می شد. حالا تا وقتی
    حتی یک ثانیه مانده باشد، حداقل ۱ برمی گردد.
    """
    import math

    seconds = _seconds_left(expire_str)
    if seconds <= 0:
        return 0
    return max(1, math.ceil(seconds / 86400))


def _seconds_left(expire_str: str) -> float:
    expire = datetime.fromisoformat(expire_str)
    if expire.tzinfo is None:
        expire = expire.replace(tzinfo=TZ)
    return (expire - now()).total_seconds()


def is_expired(expire_str: str) -> bool:
    """آیا واقعا منقضی شده؟ مقایسه دقیق زمانی، نه بر حسب روز."""
    return _seconds_left(expire_str) <= 0


def time_left_text(expire_str: str) -> str:
    """زمان باقی مانده به زبان آدمیزاد.

    زیر یک روز به ساعت و زیر یک ساعت به دقیقه نمایش داده می شود تا
    سرویس تست یک روزه درست دیده شود.
    """
    seconds = _seconds_left(expire_str)
    if seconds <= 0:
        return _t("تمام شده")
    import math

    if seconds < 3600:
        return f"{max(1, math.ceil(seconds / 60))} {_t('دقیقه')}"
    if seconds < 86400:
        return f"{math.ceil(seconds / 3600)} {_t('ساعت')}"
    return f"{math.ceil(seconds / 86400)} {_t('روز')}"


def usage_bar(used: int, total: int | None, width: int = 16) -> str:
    """نوار مصرف مثل ████░░░░░░░░░░░░

    فقط خود نوار برمی گردد؛ درصد جداگانه با usage_percent گرفته می شود
    تا در قالب صفحه سرویس بتوان آن را جای دیگری گذاشت.
    """
    if not total:
        return "░" * width  # نامحدود: نوار خالی
    ratio = min(1.0, used / total) if total > 0 else 0.0
    filled = round(ratio * width)
    return "█" * filled + "░" * (width - filled)


def usage_percent(used: int, total: int | None) -> int:
    if not total or total <= 0:
        return 0
    return min(100, round(used / total * 100))


def fmt_gb(data_bytes: int | None) -> str:
    if data_bytes is None:
        return _t("نامحدود")
    gb = data_bytes / GIB
    return f"{gb:g} {_t('گیگ')}"


def fmt_data(data_bytes: int | None) -> str:
    """حجم به شکل «۱۰ GB» برای صفحه سرویس."""
    if data_bytes is None:
        return _t("نامحدود")
    gb = data_bytes / GIB
    if gb and gb < 1:
        return f"{round(gb * 1024):g} MB"
    return f"{gb:g} GB"


def service_status(
    expire_at: str | None,
    used: int = 0,
    total: int | None = None,
    duration_days: int | None = None,
) -> str:
    """کلید وضعیت سرویس: active / warn / finished / expired.

    آستانه هشدار **نسبی** است، نه یک عدد ثابت. نسخه قبلی هر سرویسی را
    که کمتر از ۲۴ ساعت اعتبار داشت «رو به اتمام» می دانست؛ نتیجه این
    بود که سرویس یک روزه و تست رایگان از همان ثانیه اول نارنجی نشان
    داده می شدند، در حالی که تازه ساخته شده بودند.

    حالا هشدار وقتی است که یک چهارم پایانی عمر سرویس شروع شده باشد، و
    حداکثر یک روز مانده به پایان. یعنی:
      سرویس ۳۰ روزه -> ۲۴ ساعت آخر
      سرویس ۷ روزه  -> ۲۴ ساعت آخر (یک چهارم آن ۴۲ ساعت است)
      سرویس ۱ روزه  -> ۶ ساعت آخر
    """
    if total and total > 0 and used >= total:
        return "finished"
    if is_expired(expire_at):
        return "expired"
    if total and total > 0 and used / total >= 0.9:
        return "warn"

    seconds = _seconds_left(expire_at) if expire_at else 0
    if seconds <= 0:
        return "active"
    threshold = 86400.0
    if duration_days:
        threshold = min(threshold, duration_days * 86400 * 0.25)
    if seconds <= threshold:
        return "warn"
    return "active"


# ---------- ساخت نام فنی سرویس از اسم دلخواه کاربر ----------
# نگاشت حرف به حرف فارسی به لاتین. کامل نیست و قرار هم نیست باشد؛
# فقط باید نامی بسازد که پنل قبولش کند و برای کاربر آشنا باشد.
_FA_LATIN = {
    "ا": "a", "آ": "a", "أ": "a", "إ": "a", "ب": "b", "پ": "p", "ت": "t",
    "ث": "s", "ج": "j", "چ": "ch", "ح": "h", "خ": "kh", "د": "d", "ذ": "z",
    "ر": "r", "ز": "z", "ژ": "zh", "س": "s", "ش": "sh", "ص": "s", "ض": "z",
    "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "gh", "ک": "k",
    "ك": "k", "گ": "g", "ل": "l", "م": "m", "ن": "n", "و": "v", "ه": "h",
    "ة": "h", "ی": "y", "ي": "y", "ئ": "y", "ء": "", "َ": "", "ِ": "",
    "ُ": "", "ّ": "", "ْ": "",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
}



# حروف و ارقامی که در فارسی و انگلیسی با هم اشتباه نمی شوند
# (بدون 0/O و 1/I/L) تا کاربر کد را درست بخواند و تایپ کند.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def track_code(prefix: str, row_id: int) -> str:
    """کد پیگیری کوتاه و یکتا.

    بخش اول از روی آیدی ردیف ساخته می شود، پس یکتایی تضمین است؛
    دو حرف تصادفی آخر فقط برای این است که کد قابل حدس زدن نباشد و
    کسی با شمردن نتواند حجم فروش را تخمین بزند.
    """
    n = max(1, int(row_id))
    core = ""
    base = len(_CODE_ALPHABET)
    while n:
        n, rem = divmod(n, base)
        core = _CODE_ALPHABET[rem] + core
    salt = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(2))
    return f"{prefix}-{core.rjust(3, _CODE_ALPHABET[0])}{salt}"


def normalize_code(raw: str) -> str:
    """کد ورودی کاربر را تمیز می کند (فاصله، حروف کوچک، ارقام فارسی)."""
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    out = (raw or "").translate(table).strip().upper()
    out = out.replace(" ", "").replace("_", "-").replace("—", "-")
    if out and "-" not in out and len(out) > 2:
        out = out[:2] + "-" + out[2:]
    return out

def slugify_service_name(raw: str) -> str:
    """تبدیل اسم دلخواه کاربر به نامی که پنل می پذیرد.

    پنل فقط حروف و رقم لاتین و زیرخط را قبول می کند، پس اسم فارسی
    حرف به حرف به لاتین برگردانده می شود. اگر چیز قابل استفاده ای
    نماند، رشته خالی برمی گردد و صدازننده باید نام خودکار بسازد.
    """
    out: list[str] = []
    for ch in (raw or "").strip().lower():
        if ch.isascii() and (ch.isalnum() or ch == "_"):
            out.append(ch)
        elif ch in _FA_LATIN:
            out.append(_FA_LATIN[ch])
        elif ch.isspace() or ch in "-.،,":
            out.append("_")
        # بقیه (ایموجی، علائم) کنار گذاشته می شوند
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    if slug and slug[0].isdigit():
        slug = "s" + slug  # بعضی پنل ها نام با رقم را قبول نمی کنند
    return slug[:24]


# قاب یک بار از دیسک خوانده و در حافظه نگه داشته می شود. خواندن دوباره
# یک تصویر یک و نیم مگابایتی در هر خرید، روی هاست اشتراکی هدر دادن وقت است.
_FRAME_CACHE: dict[str, object] = {}


def _frame_image(path: str):  # noqa: ANN201
    from PIL import Image

    cached = _FRAME_CACHE.get(path)
    if cached is None:
        cached = Image.open(path).convert("RGB")
        _FRAME_CACHE[path] = cached
    return cached


def qr_png(data: str, caption: str = "") -> bytes:
    """تولید عکس QR از لینک ساب.

    اگر فایل قاب اختصاصی برند در مسیر config.qr_frame_path موجود باشد،
    QR روی همان قاب می نشیند. در غیر این صورت QR ساده تولید می شود.
    مختصات محل نشستن QR روی قاب با QR_BOX_* در فایل env تنظیم می شود.
    """
    import io

    import qrcode

    from .config import config

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=config.qr_fg, back_color=config.qr_bg).convert("RGB")

    frame_path = config.qr_frame_path
    if frame_path and os.path.exists(frame_path):
        try:
            from PIL import Image

            frame = _frame_image(frame_path).copy()
            size = config.qr_box_size
            # NEAREST نه LANCZOS: نرم کردن لبه ماژول های QR باعث می شود
            # دوربین بعضی گوشی ها سخت تر بخواند. QR باید لبه تیز بماند.
            qr_resized = img.resize((size, size), Image.NEAREST)
            frame.paste(qr_resized, (config.qr_box_x, config.qr_box_y))

            # کاهش به پالت ۲۵۶ رنگ: حجم خروجی را حدود نصف می کند و
            # ارسال را سریع تر. dither خاموش است تا لبه ماژول های QR
            # نقطه نقطه نشود؛ خود QR فقط دو رنگ دارد و دست نخورده
            # می ماند (تست شده: ناحیه QR بعد از کاهش هم دقیقا دو رنگ است).
            try:
                frame = frame.quantize(colors=256, dither=Image.Dither.NONE)
            except Exception:  # noqa: BLE001
                pass  # نسخه قدیمی Pillow: بدون کاهش هم درست کار می کند

            buf = io.BytesIO()
            # optimize=True روی تصویر بزرگ چند ثانیه CPU می گیرد و روی
            # هاست اشتراکی هر خرید را کند می کند.
            frame.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:  # noqa: BLE001
            logging.getLogger("obour.utils").warning(
                "ساخت QR روی قاب ناموفق بود، QR ساده استفاده شد", exc_info=True
            )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()



# ---------- قیمت گذاری ساخت دلخواه (بخش ۵.۲ سند) ----------
# قیمت بر پایه حجم است، چون هزینه واقعی فروشنده فقط به حجم بستگی دارد نه مدت.
# مدت طولانی تر فقط یک کارمزد کوچک نگهداری دارد (نه ضریب چند برابری).
# مدت های کوتاه ضریب کمتر از ۱ ندارند: هزینه واقعی حجم است نه مدت،
# پس قیمت یک روزه نباید خیلی کمتر از ماهانه با همان حجم باشد.
DURATION_FEE = {1: 0.80, 3: 0.85, 7: 0.90, 14: 0.95, 30: 1.00, 60: 1.10, 90: 1.15, 180: 1.25}

# حداقل قیمت هر سرویس. زیر این مقدار سود ریالی ارزش وقت پشتیبانی را ندارد.
MIN_PRICE = 15_000


def duration_multiplier(days: int) -> float:
    """کارمزد مدت. سقف ۱.۲۵ و کف ۰.۸ تا قیمت منطقی بماند."""
    if days in DURATION_FEE:
        return DURATION_FEE[days]
    # درون یابی خطی برای مدت های غیر استاندارد
    if days <= 1:
        return 0.80
    if days >= 180:
        return 1.25
    known = sorted(DURATION_FEE)
    for lo, hi in zip(known, known[1:]):
        if lo <= days <= hi:
            ratio = (days - lo) / (hi - lo)
            return DURATION_FEE[lo] + ratio * (DURATION_FEE[hi] - DURATION_FEE[lo])
    return 1.25


def custom_price(gb: int, days: int, rate_per_gb: int) -> int:
    """قیمت سرویس دلخواه، گرد شده به ۱۰۰۰ تومان بالا.

    هرچه حجم بیشتر، نرخ هر گیگ کمتر (تخفیف پلکانی مطابق سند).
    """
    discount = 1.0
    if gb >= 100:
        discount = 0.80
    elif gb >= 50:
        discount = 0.85
    elif gb >= 30:
        discount = 0.90
    elif gb >= 20:
        discount = 0.95

    raw = gb * rate_per_gb * discount * duration_multiplier(days)
    price = int(round(raw / 1000) * 1000)
    return max(price, MIN_PRICE)


def price_per_gb(price: int, gb: int) -> int:
    return int(price / gb) if gb else 0
