"""نمایش دستگاه های ثبت شده یک سرویس (HWID).

پنل برای هر دستگاه، نوع سیستم عامل و نسخه و مدل را نگه می دارد، ولی
هیچ کدام تضمین شده نیستند: بعضی اپ ها هدر دستگاه نمی فرستند و فقط یک
شناسه خام ثبت می شود. پس همه فیلدها اختیاری فرض می شوند و اگر چیزی
نبود، عنوان قابل فهمی از روی همان شناسه ساخته می شود.

نام دقیق کلیدها بین نسخه های پنل فرق می کند، بنابراین چند نام محتمل
برای هر مقدار امتحان می شود.
"""
from __future__ import annotations

from app.utils import fmt_dt
from app.i18n import t as _t

_OS_ICONS = (
    ("android", "📱", "اندروید"),
    ("ios", "🍎", "آیفون"),
    ("iphone", "🍎", "آیفون"),
    ("ipad", "🍎", "آیپد"),
    ("mac", "🖥", "مک"),
    ("darwin", "🖥", "مک"),
    ("windows", "💻", "ویندوز"),
    ("win", "💻", "ویندوز"),
    ("linux", "🐧", "لینوکس"),
)


def _first(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return str(value).strip()
    return ""


def icon_and_os(row: dict) -> tuple[str, str]:
    """(ایموجی، نام سیستم عامل). نام خالی یعنی پنل چیزی نفرستاده."""
    raw = _first(row, "device_os", "os", "platform", "device_type").lower()
    for needle, icon, title in _OS_ICONS:
        if needle in raw:
            return icon, t(title)
    return "📟", raw


def title(row: dict) -> str:
    """عنوان خوانا برای یک دستگاه."""
    _icon, os_name = icon_and_os(row)
    raw_os = _first(row, "device_os", "os", "platform", "device_type").lower()
    model = _first(row, "device_model", "model", "device_name", "name")
    version = _first(row, "os_version", "version")

    # اگر مدل همان اسم سیستم عامل باشد (مثلا model="linux")، تکرارش
    # نکن؛ وگرنه «linux · لینوکس» می شود.
    if model.lower() in (raw_os, os_name.lower()):
        model = ""

    parts = [p for p in (model, os_name) if p]
    label = " · ".join(dict.fromkeys(parts))
    if version:
        label = f"{label} \u2068{version}\u2069" if label else version
    if label:
        return label

    # هیچ اطلاعاتی نبود: با چند رقم آخر شناسه، دستگاه ها قابل تفکیک می مانند
    hwid = _first(row, "hwid", "id", "device_id")
    return f"{_t('دستگاه ناشناس')} ({hwid[-4:]})" if hwid else _t("دستگاه ناشناس")


def columns(row: dict) -> tuple[str, str, str]:
    """(دستگاه، سیستم عامل، آخرین اتصال) - برای نمایش جدولی."""
    icon, os_name = icon_and_os(row)
    model = _first(row, "device_model", "model", "device_name", "name")
    version = _first(row, "os_version", "version")
    raw_os = _first(row, "device_os", "os", "platform", "device_type").lower()
    if model.lower() in (raw_os, os_name.lower()):
        model = ""

    if model:
        device_col = f"{icon} {model}".strip()
    elif os_name:
        device_col = f"{icon} {os_name}".strip()
    else:
        device_col = f"{icon} {title(row)}".strip()
    os_col = f"{os_name} {version}".strip() if (os_name or version) else _t("نامشخص")
    return device_col, os_col, last_seen(row)


def last_seen(row: dict) -> str:
    when = _first(
        row, "last_used_at", "last_seen_at", "used_at", "updated_at", "created_at"
    )
    return fmt_dt(when) if when else _t("نامشخص")


def limit_of(panel_user) -> int:  # noqa: ANN001
    """سقف دستگاه کاربر. صفر یعنی بی سقف یا تنظیم نشده."""
    for key in ("hwid_limit", "device_limit", "hwid_count_limit"):
        value = getattr(panel_user, key, None)
        if isinstance(value, int) and value > 0:
            return value
    return 0
