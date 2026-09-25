"""مینی اپ عبور.

فاز یک: فقط خواندنی. هیچ اندپوینتی در این فاز چیزی را تغییر نمی دهد -
نه خرید، نه شارژ، نه تمدید. همه عملیات مالی همان طور که بود داخل خود
ربات انجام می شود و مینی اپ فقط «ویترین» همان داده هاست.

چرا این طور؟ منطق خرید الان داخل handlers/buy.py قفل است. تا وقتی آن
منطق به یک سرویس لایر مشترک منتقل نشده، نوشتن یک مسیر خرید دوم یعنی
دو پیاده سازی موازی برای پول - و اولین باگ مالی از همان جا می آید.

ساختار:
  auth.py   احراز هویت با initData تلگرام (HMAC)
  api.py    توابع async که داده را از db و panel می خوانند
  wsgi.py   پل بین دنیای همزمان Passenger و این توابع
  static/   خود مینی اپ (یک فایل HTML بدون هیچ CDN خارجی)
"""
from __future__ import annotations

import os

from app.config import config

# زیرمسیر مینی اپ نسبت به ریشه اپ. آدرس نهایی که در BotFather ثبت
# می شود: WEBHOOK_BASE_URL + WEBAPP_PATH  مثلا:
#   https://dezhcode.pyho.ir/obour/app
WEBAPP_PATH = "/" + (os.getenv("WEBAPP_PATH", "").strip().strip("/") or "app")


def is_enabled() -> bool:
    """مینی اپ فقط وقتی روشن است که آدرس عمومی و https داشته باشیم.

    تلگرام مینی اپ روی http را اصلا باز نمی کند، پس بهتر است دکمه اش
    ساخته نشود تا کاربر روی چیزی بزند که باز نمی شود.
    """
    if os.getenv("WEBAPP_ENABLED", "true").strip().lower() in ("0", "false", "off", "no"):
        return False
    return config.webhook_base_url.startswith("https://")


def url() -> str:
    """آدرس کامل مینی اپ. خالی یعنی خاموش."""
    if not is_enabled():
        return ""
    return f"{config.webhook_base_url}{WEBAPP_PATH}"
