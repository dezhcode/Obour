"""خودپینگ: ربات هر چند دقیقه یک درخواست به خودش می زند.

چرا لازم است؟
Passenger پروسه بیکار را می کشد. نتیجه اش دو چیز است:
۱. کاربر بعدی باید منتظر راه اندازی دوباره بماند
۲. هیچ کار دوره ای ای انجام نمی شود (چون هیچ کدی در حال اجرا نیست)

این ماژول یک نخ (thread) پس زمینه راه می اندازد که هر N دقیقه یک
درخواست ساده به `/health` خود ربات می زند. آن درخواست:
- تایمر بیکاری Passenger را صفر می کند، پس پروسه زنده می ماند
- کران خودکار را هم بیدار می کند (چون /health آن را صدا می زند)

یعنی عملا یک کران داخلی، بدون هیچ سرویس بیرونی.

محدودیت صادقانه: اگر پروسه به هر دلیلی کشته شود (ریستارت هاست، اتمام
حافظه، دیپلوی)، دیگر کسی نیست که پینگ بزند. اولین کاربر بعدی پروسه را
زنده می کند و همان لحظه این نخ هم دوباره راه می افتد. برای پوشش کامل،
یک پینگ بیرونی رایگان (UptimeRobot و مانند آن) مطمئن تر است - این
ماژول جایگزین آن نیست، ولی در نبودش کار را راه می اندازد.
"""
from __future__ import annotations

import logging
import threading
import time
import urllib.request

from app.config import config

log = logging.getLogger("obour.keepalive")

_thread: threading.Thread | None = None
_lock = threading.Lock()


def _ping_once(url: str) -> None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "obour-keepalive/1"},
        method="GET",
    )
    # تایم اوت کوتاه: این فقط یک بیدارباش است، نه کاری که جوابش مهم باشد
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read(64)


def _loop(url: str, interval: int) -> None:
    # اولین پینگ با کمی تاخیر، تا مزاحم راه اندازی خود پروسه نشود
    time.sleep(30)
    while True:
        try:
            _ping_once(url)
            log.debug("خودپینگ انجام شد")
        except Exception as exc:  # noqa: BLE001
            # شکست پینگ عادی است (ریستارت، شبکه). فقط لاگ سبک.
            log.debug("خودپینگ نشد: %s", exc)
        time.sleep(interval)


def start() -> None:
    """راه اندازی نخ خودپینگ. چند بار صدا زدن اشکالی ندارد."""
    global _thread

    if not config.keepalive_enabled:
        return
    base = config.webhook_base_url
    if not base:
        # بدون آدرس عمومی نمی شود به خود درخواست زد
        return

    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        url = f"{base.rstrip('/')}/health"
        interval = max(5, config.keepalive_minutes) * 60
        _thread = threading.Thread(
            target=_loop,
            args=(url, interval),
            name="obour-keepalive",
            daemon=True,  # مانع بسته شدن پروسه نشود
        )
        _thread.start()
        log.info("خودپینگ هر %s دقیقه روی %s", config.keepalive_minutes, url)


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
