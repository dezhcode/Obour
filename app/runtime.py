"""هسته مشترک اجرا: ساخت bot / dispatcher / db / panel.

این ماژول هم برای اجرای polling استفاده می شود (main.py) و هم برای
اجرا زیر Passenger روی هاست سی پنل (passenger_wsgi.py).

منطق کار زیر Passenger:
Passenger یک اپ WSGI همزمان (sync) اجرا می کند، ولی aiogram async است.
پس یک event loop دائمی در یک ترد جدا بالا می آوریم و درخواست های وبهوک
را با run_coroutine_threadsafe به آن می سپاریم. تمام کارهای async ربات
روی همان یک loop انجام می شود، پس اتصال SQLite و session تلگرام سالم می مانند.
"""
from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import threading
from typing import Any, Coroutine

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import ErrorEvent

from .config import config
from .db import Database
from .fsm_storage import SQLiteStorage
from .middlewares import ThrottleMiddleware, UserMiddleware
from .panel import Panel

log = logging.getLogger("obour")

_LOG_READY = False


def setup_logging() -> None:
    """لاگ همزمان در فایل و stderr. روی سی پنل stderr به error log دامنه می رود."""
    global _LOG_READY
    if _LOG_READY:
        return
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.log_level, logging.INFO))

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)

    try:
        os.makedirs(os.path.dirname(config.log_path), exist_ok=True)
        fileh = logging.handlers.RotatingFileHandler(
            config.log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        fileh.setFormatter(fmt)
        root.addHandler(fileh)
    except OSError:
        pass  # اگر نشد فایل بسازد، فقط stderr

    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    _LOG_READY = True


def make_session() -> AiohttpSession:
    """ساخت session تلگرام با پشتیبانی از پروکسی و آدرس واسط."""
    kwargs: dict[str, Any] = {}
    if config.tg_proxy:
        kwargs["proxy"] = config.tg_proxy
    if config.tg_api_base:
        kwargs["api"] = TelegramAPIServer.from_base(config.tg_api_base)
    return AiohttpSession(**kwargs)


def build() -> tuple[Dispatcher, Bot, Database, Panel | None]:
    """ساخت همه اجزای ربات. هیچ I/O ای اینجا انجام نمی شود."""
    db = Database(config.db_path)
    has_auth = bool(config.panel_api_key or (config.panel_username and config.panel_password))
    panel = Panel(config) if (config.panel_base_url and has_auth) else None

    bot = Bot(
        token=config.bot_token,
        session=make_session(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # اعمال ایموجی سفارشی روی همه پیام های خروجی (بدون نیاز به تغییر هندلرها)
    from app.emoji_mw import EmojiOutgoingMiddleware

    bot.session.middleware(EmojiOutgoingMiddleware())
    dp = Dispatcher(storage=SQLiteStorage(db))

    dp["db"] = db
    dp["panel"] = panel

    throttle = ThrottleMiddleware(delay=0.4)
    user_mw = UserMiddleware()
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(throttle)
        observer.middleware(user_mw)

    # وارد کردن روترها اینجا انجام می شود تا از import حلقه ای جلوگیری شود
    from .handlers import (
        admin,
        ai,
        buy,
        commands,
        extras,
        services,
        start,
        track,
        wallet,
    )

    # روتر دستورها اول از همه: دستور اسلشی باید حتی وسط یک جریان FSM هم
    # کار کند، پس نباید هندلرهای state دار زودتر آن را بگیرند.
    dp.include_routers(
        wallet.pay_router,
        commands.router,
        admin.router,
        ai.router,
        buy.router,
        extras.router,
        wallet.router,
        services.router,
        track.router,
        start.router,
    )

    @dp.errors()
    async def _on_error(event: ErrorEvent) -> bool:
        """گرفتن خطاهای هندلرها در یک نقطه.

        بعضی خطاهای تلگرام بی ضرر هستند و نباید لاگ را شلوغ کنند:
        وقتی کاربر یک دکمه را دو بار می زند، محتوای پیام عوض نمی شود و
        تلگرام message is not modified برمی گرداند.

        «query is too old» هم همین طور است: کالبک تلگرام حدود ۱۵ ثانیه
        اعتبار دارد و اگر هندلر پشت یک درخواست کند پنل مانده باشد، تا
        وقت answer() دیگر منقضی شده. کار اصلی هندلر انجام شده و فقط آن
        تیک بی صدا از دست رفته، پس نباید به عنوان خطای هندل نشده لاگ
        شود یا پیام «مشکلی پیش اومد» بدهد.
        """
        exc = event.exception

        if isinstance(exc, TelegramBadRequest) and "message is not modified" in str(exc):
            return True
        if isinstance(exc, TelegramBadRequest) and "query is too old" in str(exc):
            log.debug("کالبک منقضی شده بود، نادیده گرفته شد")
            return True
        if isinstance(exc, TelegramRetryAfter):
            log.warning("محدودیت نرخ تلگرام: %s ثانیه", exc.retry_after)
            return True

        log.exception("خطای هندل نشده در پردازش آپدیت", exc_info=exc)

        # به کاربر بگو مشکلی پیش آمده تا در سکوت منتظر نماند
        callback = getattr(event.update, "callback_query", None)
        if callback is not None:
            try:
                await callback.answer("یه مشکلی پیش اومد. دوباره امتحان کن.", show_alert=True)
            except Exception:  # noqa: BLE001
                pass
        return True

    return dp, bot, db, panel


class Runtime:
    """نگهدارنده یک event loop دائمی برای اجرا زیر WSGI."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.bot: Bot | None = None
        self.dp: Dispatcher | None = None
        self.db: Database | None = None
        self.panel: Panel | None = None

    # ---------- راه اندازی ----------
    def ensure_started(self) -> None:
        if self._loop is not None and self._loop.is_running():
            return
        with self._lock:
            if self._loop is not None and self._loop.is_running():
                return
            setup_logging()
            if not config.bot_token:
                raise RuntimeError("BOT_TOKEN در فایل .env تنظیم نشده است")

            # اگر loop قبلی مرده ولی منابعش باز مانده، آزادشان کن
            if self._loop is not None:
                old_loop, old_db = self._loop, self.db
                self._loop = None
                try:
                    if old_db is not None and old_loop.is_closed() is False:
                        asyncio.run_coroutine_threadsafe(old_db.close(), old_loop).result(timeout=5)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    old_loop.call_soon_threadsafe(old_loop.stop)
                except Exception:  # noqa: BLE001
                    pass
                log.info("loop قبلی مرده بود، منابعش آزاد شد")

            loop = asyncio.new_event_loop()
            ready = threading.Event()

            def _runner() -> None:
                asyncio.set_event_loop(loop)
                loop.call_soon(ready.set)
                loop.run_forever()

            thread = threading.Thread(target=_runner, name="obour-loop", daemon=True)
            thread.start()
            ready.wait(timeout=10)

            self._loop = loop
            self._thread = thread

            self.dp, self.bot, self.db, self.panel = build()
            async def _boot() -> None:
                await self.db.connect()
                from app import effects
                from app import emoji as emo

                await emo.load(self.db)
                await effects.load(self.db)
                from app import features

                await features.load(self.db)
                # نام کاربری ربات را یک بار می گیریم و نگه می داریم؛
                # ساخت لینک عمیق برای دکمه های کانال به آن نیاز دارد و
                # نباید هر بار get_me صدا زده شود.
                try:
                    me = await self.bot.get_me()
                    if me.username:
                        await self.db.set_setting("bot_username", me.username)
                except Exception:  # noqa: BLE001
                    log.debug("خواندن نام کاربری ربات نشد", exc_info=True)

                # وبهوکی که قبل از اضافه شدن Stars ثبت شده، pre_checkout_query
                # را نمی گیرد و پرداخت ستاره بی صدا شکست می خورد. همین جا
                # درستش می کنیم تا لازم نباشد کسی /setwebhook را دوباره بزند.
                try:
                    info = await self.bot.get_webhook_info()
                    got = set(info.allowed_updates or [])
                    if info.url and got and not set(config.allowed_updates) <= got:
                        await self.bot.set_webhook(
                            url=info.url,
                            secret_token=config.webhook_secret or None,
                            allowed_updates=list(config.allowed_updates),
                        )
                        log.info("allowed_updates وبهوک به روز شد (pre_checkout_query برای Stars)")
                except Exception:  # noqa: BLE001
                    log.warning("بررسی allowed_updates وبهوک نشد", exc_info=True)

            fut = asyncio.run_coroutine_threadsafe(_boot(), loop)
            fut.result(timeout=30)
            log.info("obour runtime ready (pid=%s)", os.getpid())

    # ---------- اجرای کوروتین از دنیای همزمان ----------
    def run(self, coro: Coroutine, timeout: float = 50.0) -> Any:
        self.ensure_started()
        assert self._loop is not None
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    def run_background(self, coro: Coroutine) -> None:
        self.ensure_started()
        assert self._loop is not None
        asyncio.run_coroutine_threadsafe(coro, self._loop)


runtime = Runtime()
