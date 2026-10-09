"""تنظیمات Game Club از همان .env مرکزی عبور (app.config آن را بار می کند)."""
from __future__ import annotations

import os

from app.config import _abs_path, _bool, _int_env, config as obour


def _ints(name: str, default: str) -> tuple[int, ...]:
    raw = os.getenv(name, "") or default
    out = []
    for x in raw.replace(" ", "").split(","):
        if x.isdigit() and int(x) > 0:
            out.append(int(x))
    return tuple(out) or tuple(int(x) for x in default.split(","))


class GCConfig:
    token: str = os.getenv("GAME_CLUB_BOT_TOKEN", "").strip()
    username: str = os.getenv("GAME_CLUB_BOT_USERNAME", "").strip().lstrip("@")
    db_path: str = _abs_path(os.getenv("GAME_CLUB_DB_PATH", "").strip() or "data/game_club.db")
    # زیرمسیر Game Club روی همان دامنه عبور، مثلا https://site/obour/gc/
    path: str = "/" + (os.getenv("GAME_CLUB_PATH", "").strip().strip("/") or "gc")
    # رشته تصادفی جدا از WEBHOOK_SECRET عبور؛ بدونش وبهوک Game Club بسته است
    webhook_secret: str = os.getenv("GAME_CLUB_WEBHOOK_SECRET", "").strip()
    # هر امتیاز چند تومان از کیف پول عبور
    point_toman: int = max(1, _int_env("GAME_CLUB_POINT_TOMAN", "100"))
    # کلید خاموش کردن بازی امتیازی (فقط بازی آزاد می ماند)
    stake_enabled: bool = _bool("GAME_CLUB_STAKE", "true")
    # فروشگاه (خرید خدمات عبور و انتقال امتیاز). در دوره آزمایشی خاموش است:
    # نه دیده می شود و نه از API چیزی خریده می شود.
    shop_enabled: bool = _bool("GAME_CLUB_SHOP", "false")
    entries: tuple[int, ...] = _ints("GAME_CLUB_ENTRIES", "50,100,250,500")
    charge_packs: tuple[int, ...] = _ints("GAME_CLUB_PACKS", "250,500,1000,2500")
    # سهم عبور از جایزه به درصد؛ پیش فرض صفر (برنده همه را می برد)
    rake_percent: int = min(30, max(0, _int_env("GAME_CLUB_RAKE", "0")))
    turn_seconds: int = min(60, max(8, _int_env("GAME_CLUB_TURN_SECONDS", "20")))
    # چند ثانیه صبر در صف بازی آزاد قبل از پر کردن جای خالی با ربات
    # ۰ = صف ناشناس هیچ وقت خودکار با ربات پر نمی شود؛ میز وقتی کامل شد شروع می شود
    # (بازیکن صف آزاد می تواند خودش «شروع با ربات» را بزند). کلید قدیمی
    # GAME_CLUB_BOT_FILL_SECONDS عمدا خوانده نمی شود تا مقدار ۱۵ مانده در .env اثری نداشته باشد.
    bot_fill_seconds: int = max(0, _int_env("GAME_CLUB_QUEUE_AUTOBOT_SECONDS", "0"))

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    @property
    def base_url(self) -> str:
        return f"{obour.webhook_base_url}{self.path}" if obour.webhook_base_url else ""

    @property
    def webapp_url(self) -> str:
        return f"{self.base_url}/" if self.base_url.startswith("https://") else ""

    @property
    def hook_path(self) -> str:
        return f"{self.path}/hook"

    @property
    def webhook_url(self) -> str:
        return f"{self.base_url}/hook" if self.base_url else ""


gc = GCConfig()
