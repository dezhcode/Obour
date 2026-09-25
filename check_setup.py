"""بررسی سلامت نصب قبل از دپلوی.

  python check_setup.py

همه چیزهایی که می توانند خراب باشند را یکجا چک می کند و دقیق می گوید
کدام قسمت مشکل دارد.
"""
from __future__ import annotations

import asyncio
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

OK = "[ OK ]"
BAD = "[ خطا ]"
WARN = "[ هشدار ]"

problems = 0


def report(ok: bool, title: str, detail: str = "", warn_only: bool = False) -> None:
    global problems
    tag = OK if ok else (WARN if warn_only else BAD)
    if not ok and not warn_only:
        problems += 1
    line = f"{tag} {title}"
    if detail:
        line += f"  ->  {detail}"
    print(line)


async def main() -> None:
    print(f"\nپایتون: {sys.version.split()[0]}\n")

    # ---------- کتابخانه ها ----------
    for mod in ("aiogram", "aiosqlite", "dotenv", "pasarguard", "qrcode"):
        try:
            __import__(mod)
            report(True, f"کتابخانه {mod}")
        except ImportError as exc:
            report(False, f"کتابخانه {mod}", str(exc))

    from app.config import config

    print()
    # ---------- تنظیمات ----------
    report(bool(config.bot_token), "BOT_TOKEN", "در .env پر نشده" if not config.bot_token else "")
    report(bool(config.admin_ids), "ADMIN_IDS", f"{config.admin_ids}" if config.admin_ids else "خالی است")
    report(bool(config.panel_base_url), "PANEL_BASE_URL", config.panel_base_url or "خالی است")
    has_auth = bool(config.panel_api_key or (config.panel_username and config.panel_password))
    report(has_auth, "احراز هویت پنل", "نه API key نه یوزر/پسورد" if not has_auth else "")

    if config.webhook_mode:
        report(bool(config.webhook_base_url), "WEBHOOK_BASE_URL", config.webhook_base_url or "خالی")
        report(
            len(config.webhook_secret) >= 16,
            "WEBHOOK_SECRET",
            "الزامی است. بدون آن هیچ آپدیتی پذیرفته نمی شود (حداقل ۱۶ کاراکتر)",
        )
        report(
            len(config.admin_key) >= 16,
            "ADMIN_KEY",
            "برای /status و /setwebhook لازم است و باید با WEBHOOK_SECRET فرق کند",
        )
        report(
            config.admin_key != config.webhook_secret or not config.admin_key,
            "ADMIN_KEY جدا از WEBHOOK_SECRET",
            "این دو باید دو رشته متفاوت باشند",
        )
        report(config.webhook_base_url.startswith("https://"), "وبهوک روی HTTPS")
        print(f"        آدرس نهایی وبهوک: {config.webhook_url}")
    else:
        report(True, "حالت اجرا", "polling", warn_only=True)

    print()
    # ---------- دیتابیس ----------
    from app.db import Database

    try:
        db = Database(config.db_path)
        await db.connect()
        plans = await db.all_plans()
        report(True, "دیتابیس", config.db_path)
        report(bool(plans), "پلن ها", f"{len(plans)} پلن" if plans else "خالی - seed_plans.py را اجرا کن", warn_only=not plans)
        card = await db.get_setting("card_number")
        report(bool(card), "شماره کارت", "در پنل ادمین ربات ثبت کن" if not card else card, warn_only=True)
        await db.close()
    except Exception as exc:  # noqa: BLE001
        report(False, "دیتابیس", str(exc))

    # ---------- تلگرام ----------
    if config.bot_token:
        from aiogram import Bot

        from app.runtime import make_session

        bot = Bot(token=config.bot_token, session=make_session())
        try:
            me = await bot.get_me()
            report(True, "اتصال به تلگرام", f"@{me.username}")
            info = await bot.get_webhook_info()
            print(f"        وبهوک فعلی: {info.url or '-'}")
            if info.last_error_message:
                report(False, "آخرین خطای وبهوک", info.last_error_message, warn_only=True)
        except Exception as exc:  # noqa: BLE001
            report(
                False,
                "اتصال به تلگرام",
                f"{exc}  (اگر هاست ایران است، TG_PROXY را در .env تنظیم کن)",
            )
        finally:
            await bot.session.close()

    # ---------- کتابخانه های QR ----------
    # فقط import کردن کافی نیست؛ یک QR واقعی ساخته می شود تا اگر
    # چیزی در زنجیره خراب باشد همین جا معلوم شود، نه وسط اولین خرید.
    try:
        from app.utils import qr_png

        data = qr_png("https://example.com/sub/test")
        report(len(data) > 1000, "ساخت تصویر QR", f"{len(data)//1024} کیلوبایت")
    except ImportError as exc:
        report(
            False,
            "ساخت تصویر QR",
            f"{exc} — روی هاست اجرا کن: pip install -r requirements.txt",
        )
    except Exception as exc:  # noqa: BLE001
        report(False, "ساخت تصویر QR", str(exc))

    # ---------- قاب QR ----------
    # فقط وجود فایل کافی نیست؛ اگر مختصات بیرون از تصویر باشد، QR
    # نصفه پیست می شود و کسی متوجه نمی شود تا اولین خرید.
    if config.qr_frame_path:
        if not os.path.exists(config.qr_frame_path):
            report(
                False,
                "قاب QR",
                f"فایل پیدا نشد: {config.qr_frame_path} (QR ساده فرستاده می شود)",
                warn_only=True,
            )
        else:
            try:
                from PIL import Image

                with Image.open(config.qr_frame_path) as frame:
                    w, h = frame.size
                fits = (
                    config.qr_box_x >= 0
                    and config.qr_box_y >= 0
                    and config.qr_box_x + config.qr_box_size <= w
                    and config.qr_box_y + config.qr_box_size <= h
                )
                report(
                    fits,
                    "قاب QR",
                    f"تصویر {w}x{h} · QR در ({config.qr_box_x},{config.qr_box_y}) "
                    f"به اندازه {config.qr_box_size}"
                    + ("" if fits else " — بیرون از تصویر می افتد"),
                )
            except ImportError:
                report(False, "کتابخانه Pillow", "نصب نیست، QR بدون قاب می رود", warn_only=True)
            except Exception as exc:  # noqa: BLE001
                report(False, "قاب QR", str(exc), warn_only=True)

    # ---------- افکت پیام ----------
    effects_on = [
        name
        for name, value in (
            ("تست رایگان", config.effect_trial),
            ("شارژ", config.effect_charge),
            ("خرید", config.effect_purchase),
        )
        if value
    ]
    if effects_on:
        import aiogram

        from app import effects as fx

        supported = fx._supported()
        report(
            supported,
            "افکت پیام",
            f"aiogram {aiogram.__version__} · فعال برای: " + "، ".join(effects_on)
            if supported
            else f"aiogram {aiogram.__version__} پارامتر message_effect_id را ندارد "
            f"— حداقل ۳.۷ لازم است: pip install -U 'aiogram>=3.25,<4'",
            warn_only=True,
        )

    # ---------- پنل ----------
    if config.panel_base_url and has_auth:
        from app.panel import Panel

        panel = Panel(config)
        try:
            healthy = await panel.health()
            report(healthy, "اتصال به پنل PasarGuard")
            # ابطال لینک ساب: بدانیم از چه راهی انجام می شود
            report(True, "ابطال لینک ساب", panel.revoke_capability(), warn_only=True)
            # دستگاه های متصل (HWID): فقط روی پنل های نسخه ۵ به بعد هست
            report(True, "دستگاه های متصل", panel.hwid_capability(), warn_only=True)

        except Exception as exc:  # noqa: BLE001
            report(False, "اتصال به پنل PasarGuard", str(exc))
        finally:
            await panel.close()

    # ---------- کران ----------
    # بدون کران، هشدار حجم و انقضا و یادآوری فیش هیچ وقت نمی رود.
    try:
        import asyncio as _aio

        from app.db import Database as _DB

        async def _last_cron():
            db = _DB(config.db_path)
            await db.connect()
            try:
                return await db.get_setting("last_cron_at")
            finally:
                await db.close()

        _last = _aio.run(_last_cron())
        if not _last:
            report(
                False,
                "کران (کارهای دوره ای)",
                "تا حالا اجرا نشده - هشدار حجم/انقضا فرستاده نمی شود",
                warn_only=True,
            )
        else:
            from datetime import datetime as _dt
            from datetime import timedelta as _td

            from app.utils import TZ as _TZ

            _stale = (_dt.now(_TZ) - _dt.fromisoformat(_last)) > _td(hours=2)
            report(
                not _stale,
                "کران (کارهای دوره ای)",
                f"آخرین اجرا: {_last}",
                warn_only=True,
            )
    except Exception as _exc:  # noqa: BLE001
        report(False, "کران (کارهای دوره ای)", str(_exc), warn_only=True)

    print()
    if problems:
        print(f"{problems} مشکل پیدا شد. قبل از دپلوی برطرفشان کن.\n")
        sys.exit(1)
    print("همه چیز آماده است.\n")


if __name__ == "__main__":
    asyncio.run(main())
