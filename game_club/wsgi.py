"""مسیرهای AsoTas زیر Passenger (همه با پیشوند GAME_CLUB_PATH، پیش فرض /gc).

  GET   /gc                 ریدایرکت به /gc/ (آدرس های نسبی صفحه ها درست شوند)
  GET   /gc/                صفحه خانه؛ /gc/<page>.html بقیه صفحه ها
  GET   /gc/static/<file>   css، js، فونت ها
  *     /gc/api/<name>      API مینی اپ (initData در هدر X-Init-Data، یا توکن برنامهٔ اندروید در X-GC-Token)
  POST  /gc/app/guest       برنامهٔ اندروید: حساب مهمان تازه و توکن نشست (appauth.py)
  POST  /gc/app/logout      برنامهٔ اندروید: بستن توکن
  GET   /gc/app/manifest    برنامهٔ اندروید: نسخهٔ تازهٔ صفحه ها و بازی ها (appbundle.py)
  GET   /gc/app/bundle/<v>.zip  همان بسته برای آپدیت خودکار
  POST  /gc/hook            وبهوک ربات AsoTas (هدر secret token)
  GET   /gc/setwebhook?key= ثبت وبهوک، دستورها و دکمه منو (ADMIN_KEY عبور)
  GET   /gc/pic/<key>       عکس پروفایل تلگرام بازیکن (از Bot API، نگه داشته روی دیسک)
"""
from __future__ import annotations

import hashlib
import gzip
import hmac
import json
import logging
import mimetypes
import os
import re
import time
import traceback

from .config import gc

log = logging.getLogger("gameclub.wsgi")

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")
PAGES = {"index.html", "wallet.html", "profile.html", "games.html", "friends.html", "chat.html", "leaderboard.html", "shop.html", "help.html", "ludo-lobby.html", "ludo.html", "hokm-lobby.html", "hokm.html", "football-lobby.html", "football.html", "billiard-lobby.html", "billiard.html", "divar-lobby.html", "divar.html", "esmfamil-lobby.html", "esmfamil.html", "lashgar-lobby.html", "lashgar.html", "snakes-lobby.html", "snakes.html", "admin.html"}

# مثل مینی اپ عبور: فقط اسکریپت SDK تلگرام از بیرون، بقیه از خود سرور
_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://telegram.org; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; "
    "connect-src 'self'; frame-ancestors https://web.telegram.org https://*.telegram.org; "
    "base-uri 'none'; form-action 'none'"
)

_RATE: dict[int, list[float]] = {}

# برنامهٔ اندروید صفحه ها را از داخل خودش (Capacitor) باز می کند و به این سرور درخواست می زند
APP_ORIGINS = {"https://localhost", "http://localhost", "capacitor://localhost", "ionic://localhost"} | {
    o.strip() for o in os.getenv("GAME_CLUB_APP_ORIGINS", "").split(",") if o.strip()}
_CORS_PATHS = ("/api/", "/app/", "/pic/", "/media/")


def _rate_ok(uid: int, limit: int = 300, window: float = 60) -> bool:
    now = time.monotonic()
    hits = [t for t in _RATE.get(uid, []) if now - t < window]
    ok = len(hits) < limit
    if ok:
        hits.append(now)
    _RATE[uid] = hits
    if len(_RATE) > 5000:
        _RATE.clear()
    return ok


def is_gc_path(path: str) -> bool:
    return path == gc.path or path.startswith(gc.path + "/")


def _send(start_response, status: str, body: bytes, ctype: str, extra: list | None = None):
    headers = [("Content-Type", ctype), ("Content-Length", str(len(body))),
               ("X-Content-Type-Options", "nosniff")] + (extra or [])
    start_response(status, headers)
    return [body]


def _json(start_response, status: str, data: dict, environ: dict | None = None):
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    extra = [("Cache-Control", "no-store")]
    # پاسخ بزرگ (مثلا مسیر یک شوت فوتبال) فشرده می رود تا روی اینترنت موبایل زودتر برسد
    if environ is not None and len(body) > 1400 and "gzip" in (environ.get("HTTP_ACCEPT_ENCODING") or ""):
        body = gzip.compress(body, compresslevel=5)
        extra += [("Content-Encoding", "gzip"), ("Vary", "Accept-Encoding")]
    return _send(start_response, status, body, "application/json; charset=utf-8", extra)


def _body(environ: dict, limit: int = 8192) -> dict:
    try:
        size = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        size = 0
    if size <= 0 or size > limit:
        return {}
    try:
        data = json.loads(environ["wsgi.input"].read(size).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return data if isinstance(data, dict) else {}


def _query(environ: dict) -> dict:
    from urllib.parse import parse_qs

    return {k: v[0] for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}


# تلگرام css و js را یک ساعت کش می کند. هر صفحه (که کش نمی شود) آدرس این فایل ها را
# با ?v=<هش محتوا> می دهد تا بعد از هر به روزرسانی فایل تازه گرفته شود و صفحه جدید
# با css و js قدیمی کشیده نشود.
_ASSET_RE = re.compile(rb'((?:href|src)="static/[\w./-]+\.(?:css|js))"')
_ver_cache: dict[str, tuple[float, str]] = {}


def _asset_ver(rel: str) -> str:
    full = os.path.join(WEB_DIR, rel)
    try:
        mtime = os.path.getmtime(full)
    except OSError:
        return ""
    hit = _ver_cache.get(rel)
    if hit and hit[0] == mtime:
        return hit[1]
    with open(full, "rb") as fh:
        ver = hashlib.sha1(fh.read()).hexdigest()[:10]
    _ver_cache[rel] = (mtime, ver)
    return ver


def _versioned(html: bytes) -> bytes:
    def sub(m: re.Match) -> bytes:
        attr = m.group(1)
        ver = _asset_ver(attr.split(b'"', 1)[1].decode())
        return attr + (b"?v=" + ver.encode() if ver else b"") + b'"'

    return _ASSET_RE.sub(sub, html)


# فایل های ثابت در حافظهٔ پروسه: بایت ها، نسخهٔ فشرده و ETag (تا تغییر mtime)
_static_cache: dict[str, tuple] = {}
_GZIP_TYPES = ("text/", "application/javascript", "application/json", "image/svg+xml")


def _gz(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=6, mtime=0)


def _file(start_response, rel: str, environ: dict | None = None):
    """صفحه ها و فایل های ثابت.

    - فایل نسخه دار (?v=<هش همان فایل>، همهٔ css و js صفحه ها): یک سال و immutable؛ گوشی دیگر نمی پرسد.
    - بقیهٔ فایل ها (عکس، صدا، فونت): یک روز، صفحه ها و css/js بی نسخه: کوتاه؛ همه با ETag تا پرسش
      دوباره فقط ۳۰۴ (بی بدنه) بگیرد.
    - متن ها (html، css، js، svg) فشرده (gzip) می روند؛ نسخهٔ فشرده هم در حافظه می ماند."""
    environ = environ or {}
    rel = rel.lstrip("/")
    full = os.path.realpath(os.path.join(WEB_DIR, rel))
    if not full.startswith(os.path.realpath(WEB_DIR) + os.sep) or not os.path.isfile(full):
        return _send(start_response, "404 Not Found", b"not found", "text/plain")
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    if full.endswith(".woff2"):
        ctype = "font/woff2"
    if ctype.startswith("text/") or ctype in ("application/javascript",):
        ctype += "; charset=utf-8"
    page = full.endswith(".html")
    mtime = os.path.getmtime(full)
    hit = _static_cache.get(full)
    if page or not hit or hit[0] != mtime:
        with open(full, "rb") as fh:
            data = fh.read()
        if page:
            data = _versioned(data)          # نشانی css و js با هش تازه؛ پس صفحه هر بار ساخته می شود
        zipped = _gz(data) if len(data) > 1024 and ctype.startswith(_GZIP_TYPES) else None
        hit = (mtime, data, zipped, '"' + hashlib.sha1(data).hexdigest()[:16] + '"')
        if not page:
            _static_cache[full] = hit
    _, data, zipped, etag = hit
    q = environ.get("QUERY_STRING") or ""
    if page or rel == "sw.js":
        cache = "no-cache"
    elif q.startswith("v=") and q[2:12] == _asset_ver(rel):
        cache = "public, max-age=31536000, immutable"
    elif rel.endswith((".js", ".css")):
        cache = "public, max-age=300"
    else:
        cache = "public, max-age=86400"
    extra = [("Cache-Control", cache), ("ETag", etag)]
    if zipped is not None:
        extra.append(("Vary", "Accept-Encoding"))
    if page:
        extra.append(("Content-Security-Policy", _CSP))
    if environ.get("HTTP_IF_NONE_MATCH") == etag:
        start_response("304 Not Modified", extra)
        return [b""]
    if zipped is not None and "gzip" in (environ.get("HTTP_ACCEPT_ENCODING") or ""):
        extra.append(("Content-Encoding", "gzip"))
        return _send(start_response, "200 OK", zipped, ctype, extra)
    return _send(start_response, "200 OK", data, ctype, extra)


def _cors(environ: dict, start_response):  # noqa: ANN001
    """start_response ای که برای درخواست های برنامهٔ اندروید هدر CORS هم می گذارد."""
    origin = environ.get("HTTP_ORIGIN", "")
    if origin not in APP_ORIGINS:
        return start_response

    def sr(status, headers, exc_info=None):  # noqa: ANN001
        headers = [h for h in headers if h[0].lower() != "vary"] + [
            ("Access-Control-Allow-Origin", origin), ("Vary", "Origin")]
        return start_response(status, headers, exc_info) if exc_info else start_response(status, headers)
    return sr


def _app_user(runtime, token: str):  # noqa: ANN001
    """بازیکن صاحب توکن برنامه، به شکل کاربر مینی اپ؛ AuthError اگر توکن بسته یا منقضی است."""
    from app.webapp.auth import AuthError

    from . import appauth
    from .auth import GCUser
    from .bot import gcrt

    async def go():  # noqa: ANN202
        g = await gcrt.ensure()
        return await appauth.session_player(g.db, token)

    p = runtime.run(go(), timeout=15)
    if not p:
        raise AuthError("نشست برنامه منقضی شده")
    # photo_url=None یعنی عکس پروفایل دست نخورد (برنامه initData ندارد)
    return GCUser(id=p["tg_id"], first_name=(p.get("tg_name") or "")[:64], username=(p.get("username") or "")[:64],
                  language_code="fa", is_premium=False, start_param="", last_name="", photo_url=None)


def _client_key(environ: dict, kind: str) -> int:
    """کلید محدودیت درخواست برای آی پی (منفی تا با آیدی کاربرها قاطی نشود)."""
    ip = (environ.get("HTTP_X_FORWARDED_FOR") or environ.get("REMOTE_ADDR") or "").split(",")[0].strip()
    return -1 - int(hashlib.sha1(f"{kind}:{ip}".encode()).hexdigest()[:12], 16)


def _app_routes(environ: dict, start_response, sub: str, method: str, runtime):  # noqa: ANN001
    from . import appauth, appbundle
    from .bot import gcrt

    if sub == "/app/guest" and method == "POST":
        # اینترنت موبایل ایران پشت NAT مشترک است؛ سقف برای هر آی پی باید بلند باشد
        if not _rate_ok(_client_key(environ, "guest"), 30, 3600):
            return _json(start_response, "429 Too Many Requests", {"error": "rate"})
        device = str(_body(environ, 1024).get("device") or "")

        async def make():  # noqa: ANN202
            return await appauth.new_guest((await gcrt.ensure()).db, device)
        r = runtime.run(make(), timeout=15)
        return _json(start_response, "200 OK", {"token": r["token"]})
    if sub == "/app/logout" and method == "POST":
        tok = environ.get("HTTP_X_GC_TOKEN", "")

        async def out():  # noqa: ANN202
            await appauth.logout((await gcrt.ensure()).db, tok)
        runtime.run(out(), timeout=15)
        return _json(start_response, "200 OK", {"ok": True})
    if sub == "/app/manifest" and method == "GET":
        return _json(start_response, "200 OK", appbundle.manifest())
    if sub.startswith("/app/bundle/") and method == "GET":
        b = appbundle.current()
        if sub != f"/app/bundle/{b.version}.zip":
            return _send(start_response, "404 Not Found", b"not found", "text/plain")
        return _send(start_response, "200 OK", b.zip, "application/zip",
                     [("Cache-Control", "public, max-age=31536000, immutable")])
    return _send(start_response, "404 Not Found", b"not found", "text/plain")


def handle(environ: dict, start_response, path: str, runtime, authorized):  # noqa: ANN001
    method = environ.get("REQUEST_METHOD", "GET").upper()
    sub = path[len(gc.path):] or ""
    if sub.startswith(_CORS_PATHS):
        if method == "OPTIONS":
            origin = environ.get("HTTP_ORIGIN", "")
            ok = origin in APP_ORIGINS
            start_response("204 No Content", ([("Access-Control-Allow-Origin", origin), ("Vary", "Origin"),
                                                ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
                                                ("Access-Control-Allow-Headers", "X-GC-Token, Content-Type"),
                                                ("Access-Control-Max-Age", "86400")] if ok else []) + [("Content-Length", "0")])
            return [b""]
        start_response = _cors(environ, start_response)

    # _path() پسنجر اسلش آخر را برمی دارد؛ /gc و /gc/ فقط از PATH_INFO خام جدا می شوند
    if sub == "" and (environ.get("PATH_INFO") or "").endswith("/"):
        sub = "/"
    if sub == "":
        start_response("301 Moved Permanently", [("Location", gc.path.strip("/").split("/")[-1] + "/"),
                                                 ("Content-Length", "0")])
        return [b""]

    # ---------- وبهوک ربات ----------
    if sub == "/hook" and method == "POST":
        secret = environ.get("HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN", "")
        if not gc.webhook_secret or not hmac.compare_digest(secret, gc.webhook_secret):
            return _send(start_response, "403 Forbidden", b"forbidden", "text/plain")
        try:
            from aiogram.types import Update

            from .bot import gcrt

            raw = _body(environ, limit=1_000_000)
            g = runtime.run(gcrt.ensure(), timeout=30)
            if g.bot and g.dp and raw:
                update = Update.model_validate(raw, context={"bot": g.bot})
                runtime.run(g.dp.feed_update(g.bot, update), timeout=50)
        except Exception:  # noqa: BLE001
            log.exception("آپدیت AsoTas پردازش نشد")
        return _send(start_response, "200 OK", b"ok", "text/plain")

    if sub == "/setwebhook":
        if not authorized(environ):
            return _send(start_response, "403 Forbidden", b"forbidden", "text/plain")
        try:
            from .bot import gcrt, setup

            g = runtime.run(gcrt.ensure(), timeout=30)
            if not g.bot:
                return _send(start_response, "400 Bad Request", b"GAME_CLUB_BOT_TOKEN is empty", "text/plain")
            note = runtime.run(setup(g.bot), timeout=60)
            return _send(start_response, "200 OK", note.encode("utf-8"), "text/plain; charset=utf-8")
        except Exception:  # noqa: BLE001
            return _send(start_response, "500 Internal Server Error", traceback.format_exc().encode(), "text/plain")

    # ---------- برنامهٔ اندروید: مهمان، نشست، آپدیت خودکار ----------
    if sub.startswith("/app/"):
        return _app_routes(environ, start_response, sub, method, runtime)

    # ---------- API ----------
    if sub.startswith("/api/"):
        from app.webapp.auth import AuthError

        from .api import handle as api_handle
        from .auth import verify
        from .service import GCError

        init = environ.get("HTTP_X_INIT_DATA", "")
        token = environ.get("HTTP_X_GC_TOKEN", "")
        try:
            user = _app_user(runtime, token) if token and not init else verify(init)
        except AuthError as exc:
            return _json(start_response, "401 Unauthorized", {"error": "auth", "detail": str(exc)})
        if not _rate_ok(user.id):
            return _json(start_response, "429 Too Many Requests", {"error": "rate"})
        name = sub[5:].strip("/")
        # متن پیام همگانی پنل مدیریت بلندتر است
        body = _body(environ, 2_200_000 if name == "admin/popup" else 32768 if name.startswith("admin") else 8192) \
            if method == "POST" else {}
        try:
            data = runtime.run(api_handle(name, method, user, _query(environ), body), timeout=45)
            return _json(start_response, "200 OK", data, environ)
        except GCError as e:
            return _json(start_response, "400 Bad Request", {"error": e.code, **e.extra})
        except Exception:  # noqa: BLE001
            log.exception("API AsoTas خطا داد: %s", name)
            return _json(start_response, "500 Internal Server Error", {"error": "server"})

    # ---------- عکس پروفایل ----------
    if sub.startswith("/pic/") and method == "GET":
        from . import pics

        key = sub[5:]
        if not pics.KEY_RE.match(key):
            return _send(start_response, "404 Not Found", b"not found", "text/plain")
        state, data = pics.cached(key)
        if state == "miss":
            try:
                data = runtime.run(pics.fetch(key), timeout=20)
            except Exception:  # noqa: BLE001
                log.exception("عکس پروفایل گرفته نشد")
                data = None
        if not data:
            return _send(start_response, "404 Not Found", b"no photo", "text/plain",
                         [("Cache-Control", "public, max-age=3600")])
        return _send(start_response, "200 OK", data, "image/jpeg", [("Cache-Control", "public, max-age=86400")])

    # ---------- عکس پیام پاپ آپ (از پنل مدیریت) ----------
    if sub.startswith("/media/") and method == "GET":
        from . import gate

        got = gate.read_media(sub[7:])
        if not got:
            return _send(start_response, "404 Not Found", b"not found", "text/plain")
        return _send(start_response, "200 OK", got[0], got[1], [("Cache-Control", "public, max-age=604800, immutable")])

    # ---------- صفحه ها و فایل های ثابت ----------
    if method != "GET":
        return _send(start_response, "405 Method Not Allowed", b"method", "text/plain")
    if sub in ("/", "/index.html"):
        return _file(start_response, "index.html", environ)
    if sub.lstrip("/") in PAGES:
        return _file(start_response, sub.lstrip("/"), environ)
    if sub == "/sw.js":                  # service worker: باید از ریشهٔ مینی اپ داده شود تا همه صفحه ها را بگیرد
        return _file(start_response, "sw.js", environ)
    if sub.startswith("/static/"):
        return _file(start_response, sub, environ)
    return _send(start_response, "404 Not Found", b"not found", "text/plain")
