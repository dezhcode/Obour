"""مسیرهای Game Club زیر Passenger (همه با پیشوند GAME_CLUB_PATH، پیش فرض /gc).

  GET   /gc                 ریدایرکت به /gc/ (آدرس های نسبی صفحه ها درست شوند)
  GET   /gc/                صفحه خانه؛ /gc/<page>.html بقیه صفحه ها
  GET   /gc/static/<file>   css، js، فونت ها
  *     /gc/api/<name>      API مینی اپ (initData در هدر X-Init-Data)
  POST  /gc/hook            وبهوک ربات Game Club (هدر secret token)
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
PAGES = {"index.html", "wallet.html", "profile.html", "leaderboard.html", "shop.html", "help.html", "ludo-lobby.html", "ludo.html", "hokm-lobby.html", "hokm.html", "football-lobby.html", "football.html", "admin.html"}

# مثل مینی اپ عبور: فقط اسکریپت SDK تلگرام از بیرون، بقیه از خود سرور
_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://telegram.org; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; "
    "connect-src 'self'; frame-ancestors https://web.telegram.org https://*.telegram.org; "
    "base-uri 'none'; form-action 'none'"
)

_RATE: dict[int, list[float]] = {}


def _rate_ok(uid: int, limit: int = 300) -> bool:
    now = time.monotonic()
    hits = [t for t in _RATE.get(uid, []) if now - t < 60]
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


def _file(start_response, rel: str):
    rel = rel.lstrip("/")
    full = os.path.realpath(os.path.join(WEB_DIR, rel))
    if not full.startswith(os.path.realpath(WEB_DIR) + os.sep) or not os.path.isfile(full):
        return _send(start_response, "404 Not Found", b"not found", "text/plain")
    with open(full, "rb") as fh:
        data = fh.read()
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    if full.endswith(".woff2"):
        ctype = "font/woff2"
    if ctype.startswith("text/") or ctype in ("application/javascript",):
        ctype += "; charset=utf-8"
    page = full.endswith(".html")
    extra = [("Cache-Control", "no-cache" if page else "public, max-age=3600")]
    if page:
        data = _versioned(data)
        extra.append(("Content-Security-Policy", _CSP))
    return _send(start_response, "200 OK", data, ctype, extra)


def handle(environ: dict, start_response, path: str, runtime, authorized):  # noqa: ANN001
    method = environ.get("REQUEST_METHOD", "GET").upper()
    sub = path[len(gc.path):] or ""

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
            log.exception("آپدیت Game Club پردازش نشد")
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

    # ---------- API ----------
    if sub.startswith("/api/"):
        from app.webapp.auth import AuthError

        from .api import handle as api_handle
        from .auth import verify
        from .service import GCError

        init = environ.get("HTTP_X_INIT_DATA", "")
        try:
            user = verify(init)
        except AuthError as exc:
            return _json(start_response, "401 Unauthorized", {"error": "auth", "detail": str(exc)})
        if not _rate_ok(user.id):
            return _json(start_response, "429 Too Many Requests", {"error": "rate"})
        name = sub[5:].strip("/")
        # متن پیام همگانی پنل مدیریت بلندتر است
        body = _body(environ, 32768 if name.startswith("admin") else 8192) if method == "POST" else {}
        try:
            data = runtime.run(api_handle(name, method, user, _query(environ), body), timeout=45)
            return _json(start_response, "200 OK", data, environ)
        except GCError as e:
            return _json(start_response, "400 Bad Request", {"error": e.code, **e.extra})
        except Exception:  # noqa: BLE001
            log.exception("API Game Club خطا داد: %s", name)
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

    # ---------- صفحه ها و فایل های ثابت ----------
    if method != "GET":
        return _send(start_response, "405 Method Not Allowed", b"method", "text/plain")
    if sub in ("/", "/index.html"):
        return _file(start_response, "index.html")
    if sub.lstrip("/") in PAGES:
        return _file(start_response, sub.lstrip("/"))
    if sub.startswith("/static/"):
        return _file(start_response, sub)
    return _send(start_response, "404 Not Found", b"not found", "text/plain")
