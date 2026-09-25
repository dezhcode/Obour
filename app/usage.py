"""تحلیل مصرف روزانه و پیش بینی اتمام حجم.

کرون هر روز عدد تجمعی مصرف را از پنل می خواند و در usage_daily
می نویسد. مصرف یک روز = اختلاف دو عکس پشت سر هم.

چند نکته که در محاسبه رعایت شده:
- اگر سرویس ریست یا تمدید شود، عدد تجمعی پنل کم می شود و اختلاف منفی
  در می آید؛ این روزها صفر حساب می شوند نه عدد منفی.
- اگر بین دو عکس چند روز فاصله افتاده باشد (کرون اجرا نشده)، مصرف روی
  همان بازه پخش می شود تا میانگین بیخود بالا نرود.
- پیش بینی با میانگین سه روز آخر ساخته می شود، چون رفتار اخیر کاربر
  مهم تر از هفته پیش است.
"""
from __future__ import annotations

from datetime import date, datetime

from app.utils import GIB, days_left, fmt_data
from app.i18n import t as _t

_WEEKDAYS = ("دوشنبه", "سه شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه")
_BLOCKS = "▁▂▃▄▅▆▇█"


def _as_date(day: str) -> date | None:
    try:
        return datetime.strptime(day, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def daily_deltas(rows: list[dict]) -> list[tuple[date, int]]:
    """تبدیل عکس های تجمعی به مصرف روزانه."""
    out: list[tuple[date, int]] = []
    prev_day: date | None = None
    prev_used: int | None = None
    for row in rows:
        day = _as_date(row["day"])
        used = int(row["used_bytes"] or 0)
        if day is None:
            continue
        if prev_day is not None and prev_used is not None:
            gap = max(1, (day - prev_day).days)
            diff = max(0, used - prev_used)  # ریست یا تمدید = صفر
            share = diff // gap
            out.append((day, share))
        prev_day, prev_used = day, used
    return out


def label(day: date) -> str:
    today = date.today()
    delta = (today - day).days
    if delta == 0:
        return _t("امروز")
    if delta == 1:
        return _t("دیروز")
    return t(_WEEKDAYS[day.weekday()])


def chart(deltas: list[tuple[date, int]], width: int = 7) -> str:
    """نمودار ستونی متنی از مصرف روزهای اخیر."""
    items = deltas[-width:]
    if not items:
        return ""
    peak = max(v for _, v in items) or 1
    lines = []
    for day, value in items:
        level = min(len(_BLOCKS) - 1, int(value * (len(_BLOCKS) - 1) / peak))
        bar = _BLOCKS[level] * 3 if value else "·"
        lines.append(f"├ \u2068{label(day):<7}\u2069 {bar}  \u2068{fmt_data(value)}\u2069")
    return "\n".join(lines)


def forecast(rows: list[dict], service: dict) -> dict:
    """خلاصه عددی مصرف + پیش بینی.

    خروجی: has_data، average، total، days_to_empty (None = نامعلوم)،
    days_to_expire، verdict (کلید متن نتیجه).
    """
    deltas = daily_deltas(rows)
    latest = rows[-1] if rows else None
    limit = int(latest["data_limit"] or 0) if latest else 0
    used = int(latest["used_bytes"] or 0) if latest else 0
    time_left = days_left(service["expire_at"])

    result = {
        "has_data": bool(deltas),
        "chart": chart(deltas),
        "average": 0,
        "total": sum(v for _, v in deltas),
        "used": used,
        "limit": limit,
        "days_to_empty": None,
        "days_to_expire": max(0, time_left),
        "verdict": "no_data",
    }
    if not deltas:
        return result

    recent = [v for _, v in deltas[-3:]]
    average = sum(recent) // len(recent)
    result["average"] = average

    if limit <= 0:
        result["verdict"] = "unlimited"
        return result
    if average <= 0:
        result["verdict"] = "idle"
        return result

    remaining = max(0, limit - used)
    days = remaining / average
    result["days_to_empty"] = int(days)
    if remaining <= 0:
        result["verdict"] = "empty"
    elif days < result["days_to_expire"]:
        result["verdict"] = "data_first"
    else:
        result["verdict"] = "time_first"
    return result


def gb(value: int) -> str:
    return f"{value / GIB:.1f}"
