"""پل بین Passenger (همزمان) و اندپوینت های async مینی اپ.

از همان runtime ربات استفاده می شود - یعنی همان event loop، همان اتصال
SQLite و همان session پنل. هیچ اتصال دوم و هیچ پروسه دومی ساخته نمی شود.
"""
from __future__ import annotations

import hmac
import json
import logging
import mimetypes
import os
import time
import traceback
from urllib.parse import parse_qs, unquote

from app.config import config
from app.webapp import WEBAPP_PATH
from app.webapp import api as webapi
from app.webapp.auth import AuthError, verify

log = logging.getLogger("obour.webapp")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# دامنه هایی که اجازه دارند مینی اپ را داخل iframe بگذارند. نسخه وب
# تلگرام مینی اپ را در iframe باز می کند، پس X-Frame-Options: DENY
# مینی اپ را روی دسکتاپ کاملا می شکند.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://telegram.org; "
    "style-src 'self' 'unsafe-inline'; "
    # img-src: عکس پروفایل کاربر روی CDN تلگرام است و دامنه اش ثابت
    # نیست (t.me، cdn*.telesco.pe و ...). محدود به https می ماند تا
    # محتوای ناامن بار نشود.
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    # connect-src: TON Connect با bridge کیف پول ها (دامنه های متعدد و
    # متغیر، مثل bridge.tonapi.io) و فهرست کیف پول ها در config.ton.org
    # حرف می زند. فقط https؛ اسکریپتش از خود سرور ما بار می شود.
    "connect-src 'self' https:; "
    "frame-ancestors https://web.telegram.org https://*.telegram.org; "
    "base-uri 'none'; form-action 'none'"
)

# سقف نرخ ساده در حافظه: هر کاربر تلگرام در هر پنجره.
# مینی اپ آدرس عمومی دارد و بدون این، یک اسکریپت می تواند با یک
# initData معتبر هزاران بار پنل را صدا بزند.
_RATE: dict[int, list[float]] = {}
_RATE_WINDOW = 60.0
_RATE_MAX = 60


# سقف جدا برای نوشتن. خواندن زیاد بی خطر است، ولی خرید پول جابه جا
# می کند و باید سخت تر باشد.
_WRITE_RATE: dict[int, list[float]] = {}
_WRITE_WINDOW = 60.0
_WRITE_MAX = 6


def _write_rate_ok(tg_id: int) -> bool:
    now = time.monotonic()
    hits = [t for t in _WRITE_RATE.get(tg_id, []) if now - t < _WRITE_WINDOW]
    if len(hits) >= _WRITE_MAX:
        _WRITE_RATE[tg_id] = hits
        return False
    hits.append(now)
    _WRITE_RATE[tg_id] = hits
    return True


def _body(environ: dict, limit: int = 8192) -> dict:
    """بدنه JSON درخواست. سقف اندازه دارد تا یک بدنه بزرگ حافظه نخورد.

    پیش فرض ۸ کیلوبایت؛ فقط مسیر رسید سقف بزرگ تر می گیرد (عکس base64).
    """
    try:
        size = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        size = 0
    if size <= 0 or size > limit:
        return {}
    raw = environ["wsgi.input"].read(size)
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def _rate_ok(tg_id: int) -> bool:
    now = time.monotonic()
    hits = [t for t in _RATE.get(tg_id, []) if now - t < _RATE_WINDOW]
    if len(hits) >= _RATE_MAX:
        _RATE[tg_id] = hits
        return False
    hits.append(now)
    _RATE[tg_id] = hits
    if len(_RATE) > 500:  # جلوگیری از رشد بی انتها روی پروسه طولانی عمر
        for key in [k for k, v in _RATE.items() if not v or now - v[-1] > 600][:200]:
            _RATE.pop(key, None)
    return True


def _admin_check(environ: dict, raw_init: str) -> tuple[bool, bool, int | None]:
    """(ادمین با آیدی، ادمین با کلید، آیدی ادعا شده).

    آیدی از initData بدون اعتبارسنجی امضا خوانده می شود - چون ممکن است
    دقیقا همان امضا خراب باشد و بخواهیم عیب یابی کنیم. پس هر چیزی که
    پشت این چک قرار می گیرد باید بی خطر باشد: گزارش عیب یابی هیچ داده
    حساسی ندارد و نصب فونت هم فقط یک فایل عمومی را دانلود می کند.
    """
    claimed = None
    try:
        from app.webapp.auth import _parse_raw  # noqa: PLC0415

        claimed = (json.loads(_parse_raw(raw_init).get("user") or "{}")).get("id")
    except Exception:  # noqa: BLE001
        claimed = None
    by_id = bool(claimed) and claimed in config.admin_ids

    key = (config.admin_key or "").strip()
    qs = environ.get("QUERY_STRING", "")
    cands = [environ.get("HTTP_X_ADMIN_KEY", ""), _query(environ).get("key", "")]
    for part in qs.split("&"):
        nm, _, val = part.partition("=")
        if nm == "key":
            cands.append(unquote(val))
    expanded = []
    for c in cands:
        c = (c or "").strip()
        if c:
            expanded += [c, c[:1].lower() + c[1:], c[:1].upper() + c[1:]]
    want = key.encode("utf-8")
    by_key = bool(key) and any(
        hmac.compare_digest(c.encode("utf-8"), want) for c in expanded
    )
    return by_id, by_key, claimed


def is_webapp_path(path: str) -> bool:
    return path == WEBAPP_PATH or path.startswith(WEBAPP_PATH + "/")


def _sub_path(path: str) -> str:
    """مسیر داخل مینی اپ: /app/api/wallet -> /api/wallet

    تکرار زیرمسیر هم پاک می شود. نسخه قبلی یک ریدایرکت نسبی می فرستاد
    و چون passenger_wsgi._path اسلش پایانی را حذف می کند، آن ریدایرکت
    همیشه شلیک می شد و هر بار یک /app دیگر ته آدرس می چسباند:
    /obour/app -> /obour/app/app/ -> not found. آن ریدایرکت حذف شد،
    ولی مرورگرها ۳۰۱ را کش می کنند؛ پس آدرس تکراری هم اینجا درست
    می شود تا کسی مجبور به پاک کردن کش نباشد.
    """
    rest = path[len(WEBAPP_PATH):]
    while rest.startswith(WEBAPP_PATH + "/") or rest == WEBAPP_PATH:
        rest = rest[len(WEBAPP_PATH):]
    return "/" + rest.strip("/")


def _mount(environ: dict) -> str:
    """آدرس عمومی خود مینی اپ، همیشه با اسلش پایانی.

    مسیرهای نسبی داخل صفحه (فونت و static/) بدون این، یک پله بالاتر
    resolve می شوند. به جای ریدایرکت، همین مقدار داخل HTML تزریق
    می شود تا صفحه از هر آدرسی درست کار کند.
    """
    script = (environ.get("SCRIPT_NAME", "") or "").rstrip("/")
    base = config.app_base_uri if not script else script
    return (base.rstrip("/") + WEBAPP_PATH + "/") or "/"


def _json(start_response, payload: dict, status: str = "200 OK"):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(status, [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"),
    ])
    return [body]


def _query(environ: dict) -> dict:
    return {k: v[0] for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}


def _init_data(environ: dict) -> str:
    """initData از هدر خوانده می شود، نه از query string.

    هدر در access log هاست ثبت نمی شود؛ query string می شود. initData
    شامل امضای معتبر است و نشتش یعنی کسی می تواند تا ۶ ساعت به جای
    کاربر درخواست بزند.
    """
    return environ.get("HTTP_X_INIT_DATA", "") or _query(environ).get("_auth", "")


def _serve_static(start_response, name: str):
    """فایل ثابت. یک پله زیرپوشه پشتیبانی می شود (مثل fonts/…).

    basename تنها کافی نبود: فایل های فونت در زیرپوشه fonts نشسته اند
    و با basename، مسیر fonts/peyda-400.woff2 به دنبال فایلی در ریشه
    می گشت و ۴۰۴ می داد. هر جزء مسیر جدا پاکسازی می شود تا .. از هیچ
    طرف رد نشود.
    """
    parts = [q for q in name.replace("\\", "/").split("/") if q not in ("", ".", "..")]
    if not parts or len(parts) > 2:
        return _json(start_response, {"error": "not found"}, "404 Not Found")
    safe = parts[-1]
    fpath = os.path.join(STATIC_DIR, *parts)
    # مرز را دوباره می سنجیم؛ به رشته ها اعتماد نمی کنیم.
    if os.path.commonpath([
        os.path.abspath(fpath), os.path.abspath(STATIC_DIR)
    ]) != os.path.abspath(STATIC_DIR):
        return _json(start_response, {"error": "not found"}, "404 Not Found")
    if not os.path.isfile(fpath):
        return _json(start_response, {"error": "not found"}, "404 Not Found")
    ctype = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
    # mimetypes روی بعضی سیستم ها woff2 را نمی شناسد و مرورگر فونت را
    # با نوع اشتباه رد می کند.
    if safe.endswith(".woff2"):
        ctype = "font/woff2"
    with open(fpath, "rb") as fh:
        body = fh.read()
    start_response("200 OK", [
        ("Content-Type", ctype),
        ("Content-Length", str(len(body))),
        ("Cache-Control", "public, max-age=604800"),
    ])
    return [body]


def handle(environ, start_response, runtime):  # noqa: ANN001, ANN201
    """رسیدگی به همه مسیرهای زیر WEBAPP_PATH."""
    path = _sub_path(environ.get("_obour_path", "/"))
    method = environ.get("REQUEST_METHOD", "GET").upper()

    # فهرست سفید نوشتن. هر مسیر دیگری خواندنی می ماند، تا اگر روزی
    # اندپوینتی اضافه شد بی سروصدا قابل نوشتن نشود.
    WRITE_PATHS = ("/api/purchase", "/api/topup/start", "/api/topup/receipt",
                   "/api/rules/accept", "/api/ticket/send", "/api/lang",
                   "/api/crypto/start", "/api/crypto/pay", "/api/crypto/cancel")
    if method == "POST":
        if path not in WRITE_PATHS:
            return _json(
                start_response, {"error": "این مسیر خواندنی است"},
                "405 Method Not Allowed",
            )
    elif method not in ("GET", "HEAD"):
        return _json(start_response, {"error": "روش پشتیبانی نمی شود"},
                     "405 Method Not Allowed")

    # ---------- خود صفحه ----------
    if path in ("/", "/index.html"):
        fpath = os.path.join(STATIC_DIR, "index.html")
        if not os.path.isfile(fpath):
            return _json(start_response, {"error": "میني اپ نصب نشده"}, "404 Not Found")
        with open(fpath, "rb") as fh:
            body = fh.read()
        # __BASE__ جای آدرس واقعی مینی اپ را می گیرد. بدون این، فونت و
        # فایل های static یک پله بالاتر (روی /obour/static/...) خوانده
        # می شدند و ۴۰۴ می گرفتند.
        body = body.replace(b"__BASE__", _mount(environ).encode("utf-8"))
        start_response("200 OK", [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
            # صفحه کش نمی شود تا نسخه تازه بلافاصله به دست کاربر برسد؛
            # سنگینی اش در استاتیک هاست که کش طولانی دارند.
            ("Cache-Control", "no-cache"),
            ("Content-Security-Policy", _CSP),
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
        ])
        return [body]

    # CSS فونت اختصاصی. پویا ساخته می شود تا اگر ادمین فونت را با
    # /wafont برداشت، صفحه بی سروصدا به فونت بعدی برگردد و نه اینکه
    # به یک فایل ۴۰۴ لینک بماند.
    if path == "/static/custom-font.css":
        font = os.path.join(STATIC_DIR, "custom-font.woff2")
        css = ""
        if os.path.isfile(font):
            css = (
                "@font-face{font-family:'ObourCustom';"
                f"src:url('custom-font.woff2') format('woff2');"
                "font-weight:100 900;font-display:swap}"
                ":root{--font-custom:'ObourCustom'}"
            )
        body = css.encode("utf-8")
        start_response("200 OK", [
            ("Content-Type", "text/css; charset=utf-8"),
            ("Content-Length", str(len(body))),
            # کش کوتاه: ادمین فونت را عوض می کند و باید زود ببیند
            ("Cache-Control", "public, max-age=300"),
        ])
        return [body]

    if path.startswith("/static/"):
        return _serve_static(start_response, path[len("/static/"):])

    # manifest برای TON Connect. کیف پول ها (Tonkeeper و ...) آن را بدون
    # احراز هویت می خوانند تا نام و آیکن اپ را به کاربر نشان دهند.
    if path == "/tonconnect-manifest.json":
        from app import webapp as _webapp

        base = _webapp.url()
        body = json.dumps({
            "url": base,
            "name": "Obour",
            "iconUrl": f"{base}/static/ton-icon.png",
        }).encode("utf-8")
        start_response("200 OK", [
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(body))),
            ("Access-Control-Allow-Origin", "*"),
            ("Cache-Control", "public, max-age=3600"),
        ])
        return [body]

    if not path.startswith("/api/"):
        return _json(start_response, {"error": "not found"}, "404 Not Found")

    # ---------- عیب یابی ----------
    # قبل از احراز هویت می آید، چون دقیقا کارش توضیح دادن شکست همان
    # احراز هویت است. با ADMIN_KEY قفل شده تا هر کسی وضعیت توکن را
    # نبیند. کلید را می شود در هدر X-Admin-Key هم فرستاد.
    if path == "/api/diag":
        raw_init = _init_data(environ)
        by_admin_id, by_key, claimed_uid = _admin_check(environ, raw_init)

        if not (by_admin_id or by_key):
            return _json(start_response, {
                "error": "دسترسی رد شد",
                "your_telegram_id": claimed_uid,
                "admin_ids_configured": len(config.admin_ids),
                "you_are_admin": by_admin_id,
                "admin_key_set": bool((config.admin_key or "").strip()),
                "hint": (
                    "آیدی تلگرامت را به ADMIN_IDS در .env اضافه کن و Restart بزن؛ "
                    "بعد دیگر کلید لازم نیست."
                ),
            }, "403 Forbidden")
        from app.webapp.auth import describe

        report = describe(_init_data(environ))

        # هویت واقعی توکن را از خود تلگرام می پرسیم. این تنها جواب
        # قطعی است: اگر آیدی ربات با آیدی داخل توکن یکی باشد ولی امضا
        # نخواند، یعنی مینی اپ از ربات دیگری باز شده.
        try:
            runtime.ensure_started()
            me = runtime.run(runtime.bot.get_me(), timeout=20)
            report["bot_from_telegram"] = {"id": me.id, "username": me.username}
            report["token_matches_bot"] = (
                str(me.id) == report.get("bot_id_from_token")
            )
        except Exception as exc:  # noqa: BLE001
            report["bot_from_telegram"] = f"getMe نشد: {type(exc).__name__}"

        # دکمه منوی چت: آدرسی که واقعا روی ربات ثبت شده
        try:
            btn = runtime.run(runtime.bot.get_chat_menu_button(), timeout=20)
            wa = getattr(btn, "web_app", None)
            report["menu_button_url"] = getattr(wa, "url", None) or type(btn).__name__
        except Exception as exc:  # noqa: BLE001
            report["menu_button_url"] = f"خوانده نشد: {type(exc).__name__}"

        if report.get("token_matches_bot") and not any(
            a["match"] for a in report.get("attempts", [])
        ):
            report["problem"] = (
                "توکن مال همین ربات است ولی امضا نخواند - یعنی این صفحه "
                "از ربات دیگری باز شده. menu_button_url و آدرس مینی اپی "
                "که روی آن زدی را مقایسه کن؛ احتمالا یک ربات تستی هم به "
                "همین آدرس وصل است."
            )

        return _json(start_response, report)

    # ---------- احراز هویت ----------
    try:
        wuser = verify(_init_data(environ))
    except AuthError as exc:
        return _json(
            start_response,
            {"error": str(exc), "code": "auth"},
            "401 Unauthorized",
        )

    if not _rate_ok(wuser.id):
        return _json(
            start_response,
            {"error": "درخواست ها زیاد شد، چند لحظه صبر کن", "code": "rate"},
            "429 Too Many Requests",
        )

    name = path[len("/api/"):].strip("/")
    query = _query(environ)

    try:
        runtime.ensure_started()
        db, panel = runtime.db, runtime.panel

        # ---------- QR ----------
        if name == "qr":
            sid = int(query.get("id") or 0)
            sub = runtime.run(webapi.qr_payload(db, panel, wuser, sid), timeout=20)
            svg = webapi.qr_svg(sub)
            start_response("200 OK", [
                ("Content-Type", "image/svg+xml; charset=utf-8"),
                ("Content-Length", str(len(svg))),
                ("Cache-Control", "private, max-age=300"),
            ])
            return [svg]

        # ---------- جزئیات سرویس ----------
        if name == "service":
            sid = int(query.get("id") or 0)
            data = runtime.run(
                webapi.service_detail(db, panel, wuser, sid), timeout=30
            )
            return _json(start_response, data)

        # ---------- گفتگوی تیکت ----------
        if name == "ticket":
            tid = int(query.get("id") or 0)
            data = runtime.run(
                webapi.ticket_thread(db, panel, wuser, tid), timeout=20
            )
            return _json(start_response, data)

        # ---------- خرید ----------
        if name == "purchase":
            # خرید فقط با POST. با GET، یک لینک ساده یا prefetch مرورگر
            # می توانست پول کم کند - و مرورگرها GET را آزادانه و گاهی
            # خودکار می زنند.
            if method != "POST":
                return _json(start_response, {
                    "error": "خرید فقط با POST", "code": "bad_method",
                }, "405 Method Not Allowed")

            if not _write_rate_ok(wuser.id):
                return _json(start_response, {
                    "error": "درخواست های زیادی فرستادی، کمی صبر کن",
                    "code": "rate",
                }, "429 Too Many Requests")

            body = _body(environ)
            try:
                plan_id = int(body.get("plan_id") or 0)
            except (TypeError, ValueError):
                plan_id = 0
            nonce = str(body.get("nonce") or "")[:64]
            if plan_id <= 0 or len(nonce) < 8:
                return _json(start_response, {
                    "error": "درخواست ناقص", "code": "bad_request",
                }, "400 Bad Request")

            # تایم اوت بلندتر: ساخت روی پنل تا چند ثانیه طول می کشد و
            # قطع کردنش وسط کار یعنی سرویسی ساخته شود که ثبت نشده.
            data = runtime.run(
                webapi.purchase(
                    db, panel, wuser,
                    plan_id=plan_id, nonce=nonce, bot=runtime.bot,
                ),
                timeout=90,
            )
            return _json(start_response, data)

        # ---------- نوشتن های دیگر: شارژ، قوانین، تیکت ----------
        if name in ("topup/start", "topup/receipt", "rules/accept", "ticket/send", "lang"):
            if method != "POST":
                return _json(start_response, {"error": "فقط POST", "code": "bad_method"}, "405 Method Not Allowed")
            if not _write_rate_ok(wuser.id):
                return _json(start_response, {"error": "درخواست های زیادی فرستادی، کمی صبر کن", "code": "rate"}, "429 Too Many Requests")
            if name == "topup/start":
                body = _body(environ)
                try:
                    amount = int(body.get("amount") or 0)
                except (TypeError, ValueError):
                    amount = 0
                if amount <= 0:
                    return _json(start_response, {"error": "مبلغ نامعتبر", "code": "bad_request"}, "400 Bad Request")
                return _json(start_response, runtime.run(webapi.topup_start(db, panel, wuser, amount=amount), timeout=30))
            if name == "topup/receipt":
                import base64, binascii  # noqa: E401
                body = _body(environ, limit=5 * 1024 * 1024)
                try:
                    txn_id = int(body.get("txn_id") or 0)
                    raw = str(body.get("image") or "")
                    raw = raw.split(",", 1)[1] if raw.startswith("data:") else raw
                    image = base64.b64decode(raw, validate=True)
                except (TypeError, ValueError, binascii.Error):
                    txn_id, image = 0, b""
                if txn_id <= 0 or not image:
                    return _json(start_response, {"error": "عکس رسید نرسید", "code": "bad_request"}, "400 Bad Request")
                return _json(start_response, runtime.run(
                    webapi.topup_receipt(db, panel, wuser, txn_id=txn_id, image=image, bot=runtime.bot), timeout=60))
            if name == "lang":
                body = _body(environ, limit=256)
                return _json(start_response, runtime.run(
                    webapi.set_lang(db, panel, wuser, lang=str(body.get("lang") or "")), timeout=20))
            if name == "rules/accept":
                return _json(start_response, runtime.run(webapi.rules_accept(db, panel, wuser), timeout=20))
            if name == "ticket/send":
                body = _body(environ, limit=16384)
                return _json(start_response, runtime.run(
                    webapi.ticket_send(db, panel, wuser, body=str(body.get("body") or ""), bot=runtime.bot), timeout=30))

        # ---------- کریپتو (TON Connect) ----------
        if name in ("crypto/start", "crypto/pay", "crypto/cancel"):
            if method != "POST":
                return _json(start_response, {"error": "فقط POST", "code": "bad_method"}, "405 Method Not Allowed")
            if not _write_rate_ok(wuser.id):
                return _json(start_response, {"error": "درخواست های زیادی فرستادی، کمی صبر کن", "code": "rate"}, "429 Too Many Requests")
            body = _body(environ, limit=1024)
            try:
                invoice_id = int(body.get("id") or 0)
                toman = int(body.get("toman") or 0)
            except (TypeError, ValueError):
                invoice_id = toman = 0
            if name == "crypto/start":
                if toman <= 0:
                    return _json(start_response, {"error": "مبلغ نامعتبر", "code": "bad_request"}, "400 Bad Request")
                return _json(start_response, runtime.run(webapi.crypto_start(
                    db, panel, wuser, toman=toman, asset=str(body.get("asset") or "")), timeout=30))
            if invoice_id <= 0:
                return _json(start_response, {"error": "درخواست ناقص", "code": "bad_request"}, "400 Bad Request")
            if name == "crypto/pay":
                return _json(start_response, runtime.run(webapi.crypto_pay(
                    db, panel, wuser, invoice_id=invoice_id, wallet=str(body.get("wallet") or "")[:100],
                    bot=runtime.bot), timeout=40))
            return _json(start_response, runtime.run(webapi.crypto_cancel(
                db, panel, wuser, invoice_id=invoice_id), timeout=20))
        if name == "crypto/status":
            return _json(start_response, runtime.run(webapi.crypto_status(
                db, panel, wuser, invoice_id=int(query.get("id") or 0), bot=runtime.bot), timeout=40))

        # ---------- بقیه ----------
        handler = webapi.ROUTES.get(name)
        if handler is None:
            return _json(start_response, {"error": "not found"}, "404 Not Found")

        kwargs = {}
        if name == "wallet":
            kwargs["offset"] = int(query.get("offset") or 0)
            kind = (query.get("kind") or "").strip()
            kwargs["kind"] = kind if kind in ("charge", "purchase", "referral") else None

        data = runtime.run(handler(db, panel, wuser, **kwargs), timeout=30)
        return _json(start_response, data)

    except webapi.ApiError as exc:
        return _json(
            start_response,
            {"error": exc.message, "code": exc.code},
            f"{exc.status} Error",
        )
    except (ValueError, TypeError):
        return _json(start_response, {"error": "درخواست نامعتبر"}, "400 Bad Request")
    except Exception:  # noqa: BLE001
        # متن خطا فقط در لاگ می نشیند؛ بیرون یک پیام کوتاه می رود.
        log.error("webapp %s failed\n%s", name, traceback.format_exc())
        return _json(
            start_response,
            {"error": "مشکلی پیش آمد، دوباره امتحان کن", "code": "server"},
            "500 Internal Server Error",
        )
