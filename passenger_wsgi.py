"""نقطه ورود Passenger روی هاست سی پنل.

در تنظیمات Setup Python App سی پنل:
  Application startup file : passenger_wsgi.py
  Application entry point  : application

مسیرهایی که این اپ پاسخ می دهد (نسبت به آدرس اپ، یعنی /obour):
  POST  <WEBHOOK_PATH>            دریافت آپدیت از تلگرام
  GET   /health                   بررسی سلامت (بدون کلید، پاسخ کوتاه)
  GET   /import?a=..&u=..         صفحه اتصال سریع (بدون کلید، عمومی)
  GET   /app                      مینی اپ (احراز هویت با initData تلگرام)
  GET   /app/static/<n>           فایل های ثابت مینی اپ
  GET   /app/api/<n>              داده مینی اپ (فقط خواندنی، فاز یک)
  GET   /cron?key=..              اجرای کارهای دوره ای (هشدارها، پاکسازی)
  GET   /img/<name>               تصویرهای داخل ربات (app/assets)
  GET   /status?key=SECRET        وضعیت کامل
  GET   /setwebhook?key=SECRET    ثبت وبهوک روی تلگرام + فهرست دستورها
  GET   /setcommands?key=SECRET   ثبت فقط فهرست دستورها
  GET   /delwebhook?key=SECRET    حذف وبهوک
"""
from __future__ import annotations

import hmac
import json
import os
import sys
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

_BOOT_ERROR: str | None = None

try:
    from aiogram.types import Update

    from app.config import config
    from app.runtime import runtime, setup_logging

    setup_logging()
except Exception:  # noqa: BLE001
    _BOOT_ERROR = traceback.format_exc()


def _respond(start_response, status: str, body: str, ctype: str = "text/plain; charset=utf-8"):
    data = body.encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", ctype),
            ("Content-Length", str(len(data))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [data]


def _path(environ: dict) -> str:
    """مسیر داخل اپ.

    بسته به نسخه پسنجر و نحوه سوار شدن اپ روی زیرمسیر، ممکن است
    PATH_INFO شامل /obour باشد یا نباشد. هر دو حالت پوشش داده می شود.
    """
    path = environ.get("PATH_INFO", "") or "/"
    for prefix in (environ.get("SCRIPT_NAME", "") or "", config.app_base_uri):
        prefix = prefix.rstrip("/")
        if prefix and path.startswith(prefix):
            path = path[len(prefix) :] or "/"
    return "/" + path.strip("/")


def _is_webhook(path: str) -> bool:
    target = config.webhook_path
    return path == target or path.endswith(target)


def _query(environ: dict) -> dict:
    from urllib.parse import parse_qs

    return {k: v[0] for k, v in parse_qs(environ.get("QUERY_STRING", "")).items()}


def _query_raw(environ: dict, name: str) -> str:
    """یک پارامتر query، بدون تبدیل + به فاصله.

    parse_qs قاعده فرم های وب را اجرا می کند: + یعنی فاصله. برای متن
    فرم درست است، ولی کلید ADMIN_KEY معمولا base64 است و + دارد. نتیجه
    این بود که کلید با همان طول ولی بایت های متفاوت می رسید و بی صدا رد
    می شد - مسیرهای /setwebhook و /status برای هر کلیدی که + داشت کار
    نمی کردند، بدون هیچ پیام خطای معناداری.

    unquote درصدها را باز می کند ولی به + دست نمی زند.
    """
    from urllib.parse import unquote

    for part in (environ.get("QUERY_STRING", "") or "").split("&"):
        key, _, value = part.partition("=")
        if unquote(key) == name:
            return unquote(value)
    return ""


def _authorized(environ: dict) -> bool:
    """احراز هویت مسیرهای مدیریتی.

    کلید از ADMIN_KEY خوانده می شود، نه WEBHOOK_SECRET. این کلید در URL
    می آید و URL در access log هاست ذخیره می شود؛ پس نباید همان رشته ای
    باشد که تلگرام با آن هویت وبهوک را تایید می کند.
    مقایسه با compare_digest انجام می شود تا از حدس زدن بایت به بایت
    (timing) در امان باشد. کلید را می توان در هدر X-Admin-Key هم فرستاد
    که در لاگ ثبت نمی شود.

    کلید از سه جا پذیرفته می شود: هدر، query خام (+ دست نخورده)، و
    query استاندارد. دومی رفع باگ + است؛ سومی برای کسی است که + را
    خودش %2B کرده یا کلیدش اصلا + ندارد.
    """
    key = (config.admin_key or "").strip()
    if not key:
        return False
    want = key.encode("utf-8")
    candidates = (
        environ.get("HTTP_X_ADMIN_KEY") or "",
        _query_raw(environ, "key"),
        _query(environ).get("key") or "",
    )
    # بایت مقایسه می شود: compare_digest روی رشته غیر ASCII خطا می دهد
    return any(
        hmac.compare_digest(c.strip().encode("utf-8"), want)
        for c in candidates
        if c
    )


def application(environ, start_response):  # noqa: ANN001, ANN201
    if _BOOT_ERROR:
        # متن خطا ممکن است مسیر فایل ها و تنظیمات را لو بدهد، پس فقط در
        # لاگ می نشیند و به بیرون پیام کوتاه می رود.
        sys.stderr.write(_BOOT_ERROR)
        return _respond(start_response, "500 Internal Server Error", "boot error")

    path = _path(environ)
    method = environ.get("REQUEST_METHOD", "GET").upper()

    # ---------- مینی اپ ----------
    # قبل از بقیه مسیرها می آید چون زیرمسیر خودش را دارد و نباید با
    # وبهوک یا /import قاطی شود. اگر ماژول مینی اپ خراب باشد، بقیه
    # ربات نباید بخوابد - پس داخل try است.
    try:
        from app.webapp.wsgi import handle as webapp_handle
        from app.webapp.wsgi import is_webapp_path

        if is_webapp_path(path):
            environ["_obour_path"] = path
            return webapp_handle(environ, start_response, runtime)
    except Exception:  # noqa: BLE001
        sys.stderr.write(traceback.format_exc())
        return _respond(start_response, "500 Internal Server Error", "webapp error")

    # ---------- وبهوک تلگرام ----------
    if method == "POST" and _is_webhook(path):
        secret = environ.get("HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN", "")
        if not config.webhook_secret or not hmac.compare_digest(
            secret, config.webhook_secret
        ):
            # وبهوک بدون WEBHOOK_SECRET باز است و هر کسی می تواند آپدیت
            # جعلی بفرستد، پس نبودنش هم رد می شود.
            return _respond(start_response, "403 Forbidden", "forbidden")

        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        raw = environ["wsgi.input"].read(length) if length else b""

        try:
            runtime.ensure_started()
            payload = json.loads(raw.decode("utf-8"))
            update = Update.model_validate(payload, context={"bot": runtime.bot})
            runtime.run(runtime.dp.feed_update(runtime.bot, update), timeout=50)
        except Exception:  # noqa: BLE001
            # همیشه ۲۰۰ برمی گردانیم تا تلگرام همان آپدیت را بی نهایت بار
            # دوباره نفرستد. خطا در لاگ ثبت می شود.
            import logging

            logging.getLogger("obour.wsgi").exception("update handling failed")

        # کران خودکار: بعد از اینکه پاسخ کاربر داده شد، اگر وقتش رسیده
        # باشد یک دور کارهای دوره ای اجرا می شود. چون اینجا (و نه قبل
        # از feed_update) صدا زده می شود، کاربر هیچ تاخیری حس نمی کند.
        # خودش داخل خودش قفل و سقف زمانی دارد.
        try:
            from app import autocron, keepalive

            keepalive.start()
            runtime.run(
                autocron.maybe_run(runtime.bot, runtime.db),
                timeout=config.autocron_budget + 20,
            )
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger("obour.wsgi").warning(
                "کران خودکار اجرا نشد", exc_info=True
            )
        return _respond(start_response, "200 OK", "ok")

    # ---------- اتصال سریع (بدون کلید، عمومی) ----------
    # دکمه های «اتصال سریع» ربات به اینجا می آیند و کاربر را به برنامه
    # کلاینت می فرستند. تلگرام اسکیم دلخواه را روی دکمه قبول نمی کند،
    # پس این صفحه واسط لازم است. فقط لینک ساب خود پنل پذیرفته می شود
    # تا این مسیر به یک ریدایرکت باز تبدیل نشود.
    if path == "/import" and method == "GET":
        try:
            from app import apps

            q = _query(environ)
            key = (q.get("a") or "").strip()
            sub_url = apps.unpack((q.get("u") or "").strip())
            name = (q.get("n") or "Obour").strip()[:40]
            if key not in apps.APPS or not apps.is_allowed_sub(sub_url):
                return _respond(start_response, "400 Bad Request", "bad request")
            return _respond(
                start_response,
                "200 OK",
                apps.render_page(key, sub_url, name),
                "text/html; charset=utf-8",
            )
        except Exception:  # noqa: BLE001
            sys.stderr.write(traceback.format_exc())
            return _respond(start_response, "500 Internal Server Error", "import failed")

    # ---------- سلامت ----------
    # ---------- تصویرهای داخل ربات ----------
    # ربات تصویرهای خودش را سرو می کند تا نیازی به آپلود جایی نباشد.
    # آدرس عمومی همین مسیر، هم برای بلوک عکس Rich Message کار می کند و
    # هم برای پیش نمایش لینک (که file_id را قبول نمی کند).
    if path.startswith("/img/") and method == "GET":
        import mimetypes
        import os

        name = os.path.basename(path[5:])  # جلوگیری از ../
        fpath = os.path.join(os.path.dirname(__file__), "app", "assets", name)
        if not os.path.isfile(fpath):
            return _respond(start_response, "404 Not Found", "not found")
        ctype = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
        with open(fpath, "rb") as fh:
            body = fh.read()
        start_response(
            "200 OK",
            [
                ("Content-Type", ctype),
                ("Content-Length", str(len(body))),
                # تلگرام تصویر را کش می کند؛ یک روز کافی است
                ("Cache-Control", "public, max-age=86400"),
            ],
        )
        return [body]

    if path in ("/health", "/") and method == "GET":
        # این مسیر دو کار می کند:
        # ۱. پاسخ سلامت برای سرویس های پینگ
        # ۲. گرم نگه داشتن ربات. Passenger پروسه بیکار را می کشد و
        #    کاربر بعدی هزینه راه اندازی دوباره را می دهد (همان تاخیری
        #    که بعد از مدتی بی کاری حس می شود). با صدا زدن
        #    ensure_started اینجا، پینگ دوره ای هم پروسه را زنده نگه
        #    می دارد و هم ربات را آماده.
        warm = "cold"
        try:
            runtime.ensure_started()
            warm = "warm"
            # خودپینگ بعدی را زمان بندی کن (اگر نخش زنده نیست)
            from app import keepalive

            keepalive.start()
            # این درخواست را فرصتی برای کارهای دوره ای هم حساب می کنیم.
            # یعنی خودپینگ عملا نقش کران را بازی می کند: هر ربع ساعت
            # یک بار اینجا می رسیم و اگر کاری عقب مانده باشد انجام
            # می شود - از جمله ادامه ارسال همگانی.
            from app import autocron

            runtime.run(
                autocron.maybe_run(runtime.bot, runtime.db),
                timeout=config.autocron_budget + 20,
            )
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger("obour.wsgi").warning("گرم کردن ناموفق", exc_info=True)
        return _respond(start_response, "200 OK", f"obour: ok ({warm})")

    if path == "/status":
        if not _authorized(environ):
            return _respond(start_response, "403 Forbidden", "forbidden")
        try:
            runtime.ensure_started()
            info = runtime.run(runtime.bot.get_webhook_info(), timeout=30)
            me = runtime.run(runtime.bot.get_me(), timeout=30)
            panel_ok = None
            if runtime.panel:
                panel_ok = runtime.run(runtime.panel.health(), timeout=30)
            body = {
                "pid": os.getpid(),
                "python": sys.version.split()[0],
                "bot": f"@{me.username}",
                "db_path": config.db_path,
                "expected_webhook": config.webhook_url,
                "current_webhook": info.url,
                "pending_updates": info.pending_update_count,
                "last_error": info.last_error_message,
                "panel_healthy": panel_ok,
            }
            return _respond(
                start_response,
                "200 OK",
                json.dumps(body, ensure_ascii=False, indent=2),
                "application/json; charset=utf-8",
            )
        except Exception:  # noqa: BLE001
            sys.stderr.write(traceback.format_exc())
            return _respond(start_response, "500 Internal Server Error", "status failed")

    # ---------- اجرای کارهای دوره ای از راه وب ----------
    # اگر کران سی پنل کار نکند (که زیاد پیش می آید: مسیر پایتون اشتباه،
    # venv فعال نشده، یا کران اصلا اجرا نمی شود)، می شود همین مسیر را با
    # یک سرویس پینگ رایگان مثل cron-job.org هر ۱۵ دقیقه صدا زد.
    if path == "/cron":
        if not _authorized(environ):
            return _respond(start_response, "403 Forbidden", "forbidden")
        try:
            import asyncio

            import cron_tasks

            # --quiet را روشن می کنیم تا خروجی در لاگ وب سرور نریزد
            cron_tasks.QUIET = True
            asyncio.run(cron_tasks.main())
            return _respond(start_response, "200 OK", "cron: ok")
        except Exception:  # noqa: BLE001
            sys.stderr.write(traceback.format_exc())
            return _respond(start_response, "500 Internal Server Error", "cron failed")

    if path == "/setwebhook":
        if not _authorized(environ):
            return _respond(start_response, "403 Forbidden", "forbidden")
        try:
            runtime.ensure_started()
            runtime.run(
                runtime.bot.set_webhook(
                    url=config.webhook_url,
                    secret_token=config.webhook_secret or None,
                    drop_pending_updates=True,
                    allowed_updates=list(config.allowed_updates),
                ),
                timeout=30,
            )
            # فهرست دستورها هم همان جا ثبت می شود تا یک قدم کمتر باشد
            from app.commands import setup_commands

            runtime.run(setup_commands(runtime.bot), timeout=30)

            # دکمه منوی چت (کنار فیلد تایپ) به مینی اپ وصل می شود.
            # این کار را اینجا می کنیم تا لازم نباشد دستی در BotFather
            # آدرس را ثبت کنی و بعد یادت برود عوضش کنی.
            wa_note = "webapp: off"
            try:
                from aiogram.types import MenuButtonWebApp, WebAppInfo

                from app import webapp as _webapp

                wa_url = _webapp.url()
                if wa_url:
                    runtime.run(
                        runtime.bot.set_chat_menu_button(
                            menu_button=MenuButtonWebApp(
                                text="عبور", web_app=WebAppInfo(url=wa_url)
                            )
                        ),
                        timeout=30,
                    )
                    wa_note = f"webapp: {wa_url}"
            except Exception:  # noqa: BLE001
                wa_note = "webapp: failed (see log)"
                sys.stderr.write(traceback.format_exc())

            return _respond(
                start_response,
                "200 OK",
                f"webhook set: {config.webhook_url}\n{wa_note}",
            )
        except Exception:  # noqa: BLE001
            return _respond(start_response, "500 Internal Server Error", traceback.format_exc())

    if path == "/setcommands":
        if not _authorized(environ):
            return _respond(start_response, "403 Forbidden", "forbidden")
        try:
            runtime.ensure_started()
            from app.commands import PUBLIC_COMMANDS, setup_commands

            runtime.run(setup_commands(runtime.bot), timeout=30)
            return _respond(
                start_response, "200 OK", f"commands set: {len(PUBLIC_COMMANDS)}"
            )
        except Exception:  # noqa: BLE001
            return _respond(start_response, "500 Internal Server Error", traceback.format_exc())

    if path == "/delwebhook":
        if not _authorized(environ):
            return _respond(start_response, "403 Forbidden", "forbidden")
        try:
            runtime.ensure_started()
            runtime.run(runtime.bot.delete_webhook(drop_pending_updates=False), timeout=30)
            return _respond(start_response, "200 OK", "webhook deleted")
        except Exception:  # noqa: BLE001
            return _respond(start_response, "500 Internal Server Error", traceback.format_exc())

    return _respond(start_response, "404 Not Found", "not found")
