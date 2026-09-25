"""اتصال سریع: ساخت لینک مستقیم ایمپورت برای برنامه های کلاینت.

چرا این فایل لازم است؟
کاربر تازه کار باید لینک ساب را کپی کند، برنامه را باز کند، دنبال
دکمه «افزودن اشتراک» بگردد و لینک را بچسباند. بیشترین تیکت پشتیبانی
همین جا ساخته می شود. هر کلاینت یک اسکیم ایمپورت دارد (مثل
hiddify://install-sub?url=...) که با یک کلیک همه این کارها را می کند.

محدودیت تلگرام:
دکمه inline با فیلد url فقط http و https و tg را قبول می کند؛ اسکیم
دلخواه رد می شود (BUTTON_URL_INVALID). پس دکمه به یک صفحه واسط روی
دامنه خود ربات وصل می شود (مسیر /import در passenger_wsgi.py) و آن
صفحه کاربر را به برنامه می فرستد.

اگر WEBHOOK_BASE_URL خالی باشد (اجرای محلی با polling)، لینک اسکیم
به صورت متن برای کپی به کاربر داده می شود.
"""
from __future__ import annotations

import base64
from urllib.parse import quote, urlencode, urlparse

from app.config import config

# کلید، نام نمایشی، قالب لینک اسکیم
# {url} = آدرس ساب به صورت urlencode شده
# {raw} = آدرس ساب خام
# {b64} = آدرس ساب به صورت base64 (شادوراکت)
# {name} = نام نمایشی سرویس (urlencode شده)
APPS: dict[str, tuple[str, str]] = {
    "hiddify": ("Hiddify", "hiddify://install-sub?url={url}&name={name}"),
    "v2rayng": ("v2rayNG", "v2rayng://install-sub?url={url}&name={name}"),
    "clash": ("Clash Meta", "clash://install-config?url={url}&name={name}"),
    "streisand": ("Streisand", "streisand://import/{raw}"),
    "shadowrocket": ("Shadowrocket", "sub://{b64}"),
    "v2box": ("V2Box", "v2box://install-sub?url={url}&name={name}"),
    "karing": ("Karing", "karing://install-config?url={url}&name={name}"),
    "nekobox": ("NekoBox", "sn://subscription?url={url}&name={name}"),
}

# ترتیب پیشنهادی برای هر سیستم عامل. مورد اول = پیشنهاد ما.
PLATFORMS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "android": ("📱", "اندروید", ("hiddify", "v2rayng", "nekobox", "clash")),
    "ios": ("🍎", "آیفون", ("streisand", "shadowrocket", "v2box", "hiddify")),
    "windows": ("💻", "ویندوز", ("hiddify", "karing", "clash")),
    "mac": ("🖥", "مک", ("hiddify", "streisand", "clash")),
}

# فروشگاه یا صفحه دانلود هر برنامه، برای کاربری که هنوز نصبش نکرده
STORES: dict[str, str] = {
    "hiddify": "https://github.com/hiddify/hiddify-app/releases/latest",
    "v2rayng": "https://github.com/2dust/v2rayNG/releases/latest",
    "clash": "https://github.com/MetaCubeX/ClashMetaForAndroid/releases/latest",
    "streisand": "https://apps.apple.com/app/streisand/id6450534064",
    "shadowrocket": "https://apps.apple.com/app/shadowrocket/id932747118",
    "v2box": "https://apps.apple.com/app/v2box-v2ray-client/id6446814690",
    "karing": "https://github.com/KaringX/karing/releases/latest",
    "nekobox": "https://github.com/MatsuriDayo/NekoBoxForAndroid/releases/latest",
}


def app_title(key: str) -> str:
    item = APPS.get(key)
    return item[0] if item else key


def platform_apps(platform: str) -> list[tuple[str, str]]:
    """فهرست (کلید، نام) برنامه های پیشنهادی یک سیستم عامل."""
    _, _, keys = PLATFORMS.get(platform, ("", "", ()))
    return [(k, app_title(k)) for k in keys if k in APPS]


def scheme_url(key: str, sub_url: str, name: str = "Obour") -> str:
    """لینک اسکیم ایمپورت برای یک برنامه. رشته خالی یعنی پشتیبانی نمی شود."""
    item = APPS.get(key)
    if not item or not sub_url:
        return ""
    template = item[1]
    b64 = base64.b64encode(sub_url.encode("utf-8")).decode("ascii")
    return template.format(
        url=quote(sub_url, safe=""),
        raw=sub_url,
        b64=b64,
        name=quote(name or "Obour", safe=""),
    )


def pack(sub_url: str) -> str:
    """بسته بندی امن آدرس ساب برای گذاشتن در query string."""
    return base64.urlsafe_b64encode(sub_url.encode("utf-8")).decode("ascii").rstrip("=")


def unpack(token: str) -> str:
    """باز کردن آدرس ساب. اگر خراب بود رشته خالی برمی گردد."""
    if not token:
        return ""
    pad = "=" * (-len(token) % 4)
    try:
        return base64.urlsafe_b64decode(token + pad).decode("utf-8")
    except Exception:  # noqa: BLE001
        return ""


def is_allowed_sub(sub_url: str) -> bool:
    """فقط لینک های http(s) و ترجیحا روی دامنه پنل پذیرفته می شوند.

    بدون این بررسی، مسیر /import یک ریدایرکت باز می شد و هر کسی
    می توانست با دامنه شما کاربر را به هر جایی بفرستد.
    """
    if not sub_url.startswith(("http://", "https://")):
        return False
    panel_host = urlparse(config.panel_base_url).hostname or ""
    if not panel_host:
        return True
    host = urlparse(sub_url).hostname or ""
    return host == panel_host or host.endswith("." + panel_host)


def import_link(key: str, sub_url: str, name: str = "Obour") -> str:
    """آدرس https صفحه واسط، مناسب دکمه تلگرام.

    اگر آدرس عمومی اپ تنظیم نشده باشد، رشته خالی برمی گردد و لایه
    کیبورد به جای دکمه، لینک کپی شدنی نشان می دهد.
    """
    base = config.import_base
    if not base or key not in APPS or not sub_url:
        return ""
    query = urlencode({"a": key, "u": pack(sub_url), "n": name or "Obour"})
    return f"{base}?{query}"


# ---------- صفحه ای که روی مرورگر کاربر باز می شود ----------
_PAGE = """<!doctype html>
<html lang="fa" dir="rtl"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>عبور - افزودن سرویس</title>
<style>
 body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
 background:#0a1e3f;color:#e8f0ff;font-family:system-ui,-apple-system,"Segoe UI",Tahoma,sans-serif}}
 .card{{text-align:center;padding:32px 24px;max-width:360px}}
 h1{{font-size:20px;margin:0 0 8px}} p{{opacity:.75;font-size:14px;line-height:2;margin:0 0 24px}}
 a.btn{{display:block;padding:14px 20px;border-radius:14px;background:#2f6fed;color:#fff;
 text-decoration:none;font-size:16px;margin-bottom:12px}}
 a.alt{{background:transparent;border:1px solid #2f6fed;color:#9dc0ff}}
</style></head><body><div class="card">
<h1>در حال باز کردن {app}</h1>
<p>اگر خودکار باز نشد، دکمه زیر را بزن.<br>اگر برنامه نصب نیست، اول نصبش کن.</p>
<a class="btn" href="{deep}">باز کردن {app}</a>
<a class="btn alt" href="{store}">دانلود {app}</a>
</div>
<script>setTimeout(function(){{location.href={deep_js};}},250);</script>
</body></html>"""


def render_page(key: str, sub_url: str, name: str = "Obour") -> str:
    """HTML صفحه واسط. در passenger_wsgi.py استفاده می شود."""
    import html
    import json

    deep = scheme_url(key, sub_url, name)
    title = html.escape(app_title(key))
    return _PAGE.format(
        app=title,
        deep=html.escape(deep, quote=True),
        deep_js=json.dumps(deep),
        store=html.escape(STORES.get(key, "https://t.me/"), quote=True),
    )
