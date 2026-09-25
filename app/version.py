"""نسخه ربات و بررسی سلامت نصب.

چرا این فایل لازم شد؟
چند بار پیش آمد که باگی «برطرف شده» دوباره در لاگ دیده شد، یا تغییری
که اعمال شده بود روی سرور نبود - چون فقط بخشی از فایل ها جایگزین شده
بود. هیچ راهی هم نبود که بفهمیم روی سرور واقعا چه نسخه ای بالاست.

حالا `/version` دقیقا می گوید چه نسخه ای اجرا می شود و کدام قابلیت ها
واقعا در کد حاضرند. اگر چیزی ❌ بود، یعنی آن فایل جایگزین نشده.
"""
from __future__ import annotations

# قرارداد شماره گذاری (از نسخه ۵.۵.۰ به بعد): MAJOR.MINOR.PATCH
#   PATCH  رفع باگ یا تغییر جزئی بدون قابلیت تازه      5.5.0 -> 5.5.1
#   MINOR  قابلیت تازه که چیزی را نمی شکند             5.5.1 -> 5.6.0
#   MAJOR  تغییر بزرگ یا چیزی که سازگاری را می شکند    5.6.0 -> 6.0.0
#
# شماره های قدیمی (۵۴ و ۵۵) همان ۵.۴ و ۵.۵ هستند؛ عمدا از ۵.۰.۰ شروع
# نشد تا ترتیب نسخه ها به هم نریزد و لاگ های قدیمی قابل ردیابی بمانند.
VERSION = "6.1.1"
BUILD_DATE = "1405-06-29"


def version_tuple() -> tuple[int, int, int]:
    """نسخه به شکل عددی، برای مقایسه.

    مقایسه رشته ای اشتباه می دهد: "5.10.0" < "5.9.0" است اگر رشته ای
    بسنجی. هر جا لازم شد نسخه ها مقایسه شوند از این استفاده شود.
    """
    parts = (VERSION.split("-")[0].split(".") + ["0", "0"])[:3]
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)  # type: ignore[return-value]


def self_check() -> list[tuple[str, bool, str]]:
    """بررسی اینکه قابلیت های کلیدی واقعا در کد نصب شده حاضرند.

    خروجی: [(نام قابلیت، حاضر؟، جزئیات)]

    عمدا به جای «شماره نسخه در فایل» خودِ رفتار کد بررسی می شود - چون
    شماره نسخه را می شود جایگزین کرد بدون اینکه بقیه فایل ها بروند.
    """
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    # --- نسخه ۴۰: چیدمان و سوابق ---
    try:
        from app.handlers.track import PAGE_SIZE

        add("سوابق ۱۰ ردیفی", PAGE_SIZE >= 10, f"PAGE_SIZE={PAGE_SIZE}")
    except Exception as exc:  # noqa: BLE001
        add("سوابق ۱۰ ردیفی", False, str(exc))

    try:
        from app.emoji import CATALOG

        add("ایموجی جدا برای سوابق", "history" in CATALOG, f"{len(CATALOG)} کلید")
    except Exception as exc:  # noqa: BLE001
        add("ایموجی جدا برای سوابق", False, str(exc))

    # --- نسخه ۴۰: تیکت و پیام برگشت ---
    try:
        from app.db import Database

        add("تاریخچه تیکت برای ادمین", hasattr(Database, "recent_ticket_history"))
        add("ریست کامل کاربر", hasattr(Database, "purge_user"))
        add("نظرسنجی", hasattr(Database, "create_poll"))
        add("فهرست کانال ها", hasattr(Database, "bot_channels"))
        add("تیکت رشته ای", hasattr(Database, "open_thread"))
    except Exception as exc:  # noqa: BLE001
        add("متدهای دیتابیس", False, str(exc))

    try:
        from app import texts

        add("پیام برگشت قابل ویرایش", hasattr(texts, "ADMIN_WINBACK_HOME"))
        add("متن برگشت تازه", "دلمون برات تنگ شده" in texts.WINBACK)
    except Exception as exc:  # noqa: BLE001
        add("متن ها", False, str(exc))

    try:
        from app import features

        add("بخش های قابل خاموش کردن", len(features.FEATURES) >= 7)
    except Exception as exc:  # noqa: BLE001
        add("بخش های قابل خاموش کردن", False, str(exc))

    try:
        from app import pricing, warzone  # noqa: F401
        from app.db import Database as _D

        add("خدمات هوش مصنوعی", hasattr(_D, "create_ai_order"))
    except Exception as exc:  # noqa: BLE001
        add("خدمات هوش مصنوعی", False, str(exc))

    # --- نسخه ۴۲ تا ۴۴ ---
    try:
        import os

        assets = os.path.join(os.path.dirname(__file__), "assets", "locations.jpg")
        add("تصویر لوکیشن ها", os.path.isfile(assets))
    except Exception as exc:  # noqa: BLE001
        add("تصویر لوکیشن ها", False, str(exc))

    try:
        from app import richtable

        src = richtable.photo_page.__doc__ or ""
        import inspect

        code = inspect.getsource(richtable.photo_page)
        add("عکس Rich اصلاح شده", "InputMediaPhoto" in code)
    except Exception as exc:  # noqa: BLE001
        add("عکس Rich اصلاح شده", False, str(exc))

    try:
        import inspect

        from app.db import Database

        code = inspect.getsource(Database.purge_user)
        add("ریست کاربر بدون خطای FK", "pending_amounts" in code)
    except Exception as exc:  # noqa: BLE001
        add("ریست کاربر بدون خطای FK", False, str(exc))

    try:
        import inspect

        from app.handlers import admin

        code = inspect.getsource(admin)
        add("لینک عمیق دکمه های کانال", "_deep_link_markup" in code)
        add("دکمه نظرسنجی در ارسال همگانی", "_outgoing_markup" in code)
    except Exception as exc:  # noqa: BLE001
        add("قابلیت های کانال", False, str(exc))

    # --- نسخه ۵.۵.۰: سرویس لایر خرید ---
    try:
        import inspect

        from app.handlers import buy
        from app.services import purchase as _p

        add("سرویس لایر خرید", hasattr(_p, "purchase"))
        add(
            "خرید در ربات از سرویس رد می شود",
            "purchase_svc.purchase" in inspect.getsource(buy),
        )
        add(
            "سرویس مستقل از رابط",
            "aiogram" not in inspect.getsource(_p),
        )
    except Exception as exc:  # noqa: BLE001
        add("سرویس لایر خرید", False, str(exc))

    # --- نسخه ۶.۱.۰: همه چیز داخل مینی اپ ---
    try:
        import os
        import re

        page = os.path.join(os.path.dirname(__file__), "webapp", "static", "index.html")
        body = open(page, encoding="utf-8").read() if os.path.isfile(page) else ""
        from app.services import charge as _ch, support as _sp  # noqa: F401

        add("شارژ کیف پول در مینی اپ", "SubPages.topup" in body and hasattr(_ch, "attach_receipt"))
        add("رسید دوباره به ادمین نمی رود", hasattr(_ch, "ALREADY_SENT"))
        add("تیکت و پاسخ در مینی اپ", "SubPages.compose" in body and hasattr(_sp, "send"))
        add("قوانین و راهنما در مینی اپ", "SubPages.rules" in body and "SubPages.guide" in body)
        add("اسلایدر کارت ها", "const SliderFx" in body and "scroll-snap-type" in body)
        add("تور ایمنی SVG", "svg:not([width])" in body)
        add("کارت پلن: حجم هم وزن قیمت، دکمه خرید توپر", "stat-vol" in body and "btn-buy" in body)
        refs = re.findall(r"App\.openBot\('?(\w*)'?\)", body)
        add("ارجاع به ربات فقط ثبت نام و AI", len(refs) <= 2, ", ".join(r or "start" for r in refs))
    except Exception as exc:  # noqa: BLE001
        add("همه چیز داخل مینی اپ", False, str(exc))

    # --- نسخه ۶.۰.۰: طراحی کارت عبور ---
    try:
        import os

        static = os.path.join(os.path.dirname(__file__), "webapp", "static")
        page = os.path.join(static, "index.html")
        body = open(page, encoding="utf-8").read() if os.path.isfile(page) else ""
        add("طراحی کارت عبور", "function Pass(" in body and "function Slider(" in body)
        add("فقط تم روشن", "data-theme" not in body and "setHeaderColor('#EDF1F8')" in body)
        add("ناوبری چهار تب", "TABS: [['home'" in body and "'account'" in body)
        add("سیستم رنگ معنادار", all(t in body for t in ("--net-t", "--cash-t", "--ai-t", "--help-t")))
        add("نمودار یکنوا", "function monotonePath(" in body)
        add("گفتگوی تیکت", "function Thread(" in body and "noNav = true" in body)
        add("کپی با راه جایگزین", "copyFallback" in body)
        add("اشتراک بومی تلگرام", "t.me/share/url" in body)
        weights = ["400", "600", "700", "800"]
        have = [w for w in weights if os.path.isfile(os.path.join(static, "fonts", f"peyda-{w}.woff2"))]
        add("فونت پیدا", len(have) == len(weights), f"{len(have)} از {len(weights)} وزن")
        banner = os.path.isfile(os.path.join(static, "ai-banner.jpg"))
        add("بنر هوش مصنوعی", True, "تنظیم شده" if banner else "با /wabanner تنظیم کن")
    except Exception as exc:  # noqa: BLE001
        add("طراحی کارت عبور", False, str(exc))

    # --- نسخه ۵.۱۱.۰: تمام صفحه ---
    try:
        import os

        page = os.path.join(os.path.dirname(__file__), "webapp", "static", "index.html")
        body = open(page, encoding="utf-8").read() if os.path.isfile(page) else ""
        add("تمام صفحه روی موبایل", "requestFullscreen()" in body and "const Viewport" in body)
        add("فاصله امن دستگاه و دکمه های تلگرام", "--tg-csa-t" in body and "--tg-sa-t" in body)
        add("بدون دکمه برگشت تکراری", "tg-back .back" in body)
        add("افکت کمتر روی اندروید ضعیف", "perf-low" in body)
    except Exception as exc:  # noqa: BLE001
        add("تمام صفحه", False, str(exc))

    # --- نسخه ۵.۱۰.۱: نگهبان کلاس های CSS ---
    # در ۵.۱۰.۰ دو کلاس پایه (.stack و .between) موقع بازنویسی گم شدند
    # و هیچ چیز خبر نداد: فقط کارت ها بی صدا به هم چسبیدند. این چک هر
    # کلاسی را که در markup استفاده شده ولی در CSS تعریف نشده پیدا می کند.
    try:
        import os
        import re

        page = os.path.join(os.path.dirname(__file__), "webapp", "static", "index.html")
        body = open(page, encoding="utf-8").read() if os.path.isfile(page) else ""
        css = "\n".join(re.findall(r"<style>(.*?)</style>", body, re.S))
        css = re.sub(r"url\([^)]*\)", "", css)
        defined = set(re.findall(r"\.([a-zA-Z][\w-]*)", css))
        used: set[str] = set()
        for attr in re.findall(r'class="([^"]*)"', body):
            for c in re.sub(r"\$\{[^}]*\}", " ", attr).split():
                if re.fullmatch(r"[a-zA-Z][\w-]*", c):
                    used.add(c)
        # کلاس هایی که فقط قلاب جاوااسکریپت اند و ظاهری ندارند
        hooks = {"bubble-text", "logo"}
        missing = sorted(used - defined - hooks)
        add(
            "همه کلاس های CSS تعریف شده اند",
            not missing,
            ("گم شده: " + ", ".join(missing[:6])) if missing else f"{len(used)} کلاس",
        )
    except Exception as exc:  # noqa: BLE001
        add("نگهبان کلاس های CSS", False, str(exc))

    # --- نسخه ۵.۹.۱: رفع باگ + در ADMIN_KEY ---
    try:
        import os

        root = os.path.dirname(os.path.dirname(__file__))
        wsgi_src = open(os.path.join(root, "passenger_wsgi.py"), encoding="utf-8").read()
        add("ADMIN_KEY با + در مسیرهای مدیریتی", "_query_raw" in wsgi_src)
        api_src = open(os.path.join(os.path.dirname(__file__), "webapp", "api.py"), encoding="utf-8").read()
        add("لینک اتصال سریع encode شده", "apps.import_link(" in api_src)
    except Exception as exc:  # noqa: BLE001
        add("رفع باگ ۵.۹.۱", False, str(exc))

    # --- نسخه ۵.۶.۰: خرید از مینی اپ ---
    try:
        import inspect

        from app.webapp import api as _wapi
        from app.webapp import wsgi as _wwsgi

        code = inspect.getsource(_wwsgi)
        add("خرید از مینی اپ", hasattr(_wapi, "purchase"))
        add("خرید فقط با POST", 'name == "purchase"' in code and "bad_method" in code)
        add("سقف نرخ جدا برای نوشتن", "_write_rate_ok" in code)
    except Exception as exc:  # noqa: BLE001
        add("خرید از مینی اپ", False, str(exc))

    # --- نسخه ۵.۵.۰: مینی اپ ---
    try:
        from app.webapp.auth import _candidates, verify  # noqa: F401

        variants = len(list(_candidates("auth_date=1&hash=x&signature=y")))
        add("مینی اپ نصب است", True)
        add("امضای initData با هر دو قرارداد", variants >= 4, f"{variants} حالت")
    except Exception as exc:  # noqa: BLE001
        add("مینی اپ نصب است", False, str(exc))

    try:
        import os

        page = os.path.join(os.path.dirname(__file__), "webapp", "static", "index.html")
        body = ""
        if os.path.isfile(page):
            with open(page, encoding="utf-8") as fh:
                body = fh.read()
        add("صفحه مینی اپ", bool(body), f"{len(body)//1024} کیلوبایت")
        add("لوگوی عبور جاسازی شده", "data:image/webp;base64," in body)
        add("اعداد لاتین", "toLocaleString('en-US')" in body)
    except Exception as exc:  # noqa: BLE001
        add("صفحه مینی اپ", False, str(exc))

    try:
        from app.emoji import CATALOG as _CAT
        from app.webapp.api import qr_svg

        add("ایموجی دکمه مینی اپ", "webapp" in _CAT)
        add("QR ساده در مینی اپ", callable(qr_svg))
    except Exception as exc:  # noqa: BLE001
        add("ایموجی و QR مینی اپ", False, str(exc))

    return checks


def report() -> str:
    """گزارش خوانا برای دستور /version."""
    checks = self_check()
    ok_count = sum(1 for _, ok, _ in checks if ok)
    lines = [
        "╮── 🏷 نسخه ربات",
        f"│   نسخه \u2068{VERSION}\u2069 · ساخت \u2068{BUILD_DATE}\u2069",
        "",
        f"بررسی نصب: \u2068{ok_count}\u2069 از \u2068{len(checks)}\u2069 مورد سالم",
        "",
    ]
    for name, ok, detail in checks:
        mark = "✅" if ok else "❌"
        line = f"├ {mark} \u2068{name}\u2069"
        if detail and not ok:
            line += f"\n│  \u2068{detail[:60]}\u2069"
        lines.append(line)
    lines.append("")
    if ok_count == len(checks):
        lines.append("╯─ همه چیز سر جاشه.")
    else:
        lines.append(
            "╯─ موارد ❌ یعنی اون فایل ها جایگزین نشدن. "
            "کل پوشه app رو یکجا جایگزین کن."
        )
    return "\n".join(lines)
