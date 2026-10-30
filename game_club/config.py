"""تنظیمات AsoTas از همان .env مرکزی عبور (app.config آن را بار می کند)."""
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
    # کلید سرویس فایربیس (فایل JSON) برای نوتیفیکیشن گوشی برنامهٔ اندروید (push.py)؛ خالی = خاموش
    fcm_key: str = _abs_path(os.getenv("GAME_CLUB_FCM_KEY", "").strip()) if os.getenv("GAME_CLUB_FCM_KEY", "").strip() else ""
    # زیرمسیر AsoTas روی همان دامنه عبور، مثلا https://site/obour/gc/
    path: str = "/" + (os.getenv("GAME_CLUB_PATH", "").strip().strip("/") or "gc")
    # رشته تصادفی جدا از WEBHOOK_SECRET عبور؛ بدونش وبهوک AsoTas بسته است
    webhook_secret: str = os.getenv("GAME_CLUB_WEBHOOK_SECRET", "").strip()
    # هر سکه چند تومان: قیمت بسته های سکه، و نرخ برگشت امتیازهای قدیمی به کیف عبور (refund.py)
    point_toman: int = max(1, _int_env("GAME_CLUB_POINT_TOMAN", "500"))
    # سکه فقط پول داخل بازی است: با بازی و جایزه یا خرید درون برنامه ای جمع می شود و فقط آیتم می خرد
    # (نه ورودی بازی، نه خدمات عبور، نه انتقال). بازی رتبه ای ورودی ندارد: برد جام و چند سکه از طرف بازی.
    ranked_enabled: bool = _bool("GAME_CLUB_RANKED", "true")
    rank_win: int = max(1, _int_env("GAME_CLUB_RANK_WIN", "20"))
    rank_lose: int = max(0, _int_env("GAME_CLUB_RANK_LOSE", "10"))
    rank_coins: int = max(0, _int_env("GAME_CLUB_RANK_COINS", "2"))
    rank_coins_day: int = max(0, _int_env("GAME_CLUB_RANK_COINS_DAY", "10"))
    # هدیهٔ شروع هر حساب و جایزهٔ ورود روزانه (روزهای پشت هم؛ بعد از روز آخر از نو)
    start_coins: int = max(0, _int_env("GAME_CLUB_START_COINS", "10"))
    daily_coins: tuple[int, ...] = _ints("GAME_CLUB_DAILY", "1,1,2,2,3,3,5")
    # خرید سکه از مایکت (فقط برنامهٔ اندروید، iap.py). کلید عمومی RSA و توکن دسترسی هر دو از پنل توسعه دهندهٔ
    # مایکت (بخش محصولات درون برنامه ای). بدون کلید عمومی خرید بسته است؛ توکن یعنی هر خرید از API خود مایکت هم
    # پرسیده می شود (پیشنهادی). شناسهٔ محصول هر بسته در پنل مایکت: coins_<تعداد> (مثلا coins_120)
    iap_enabled: bool = _bool("GAME_CLUB_IAP", "true")
    myket_key: str = os.getenv("GAME_CLUB_MYKET_PUBLIC_KEY", "").strip()
    myket_token: str = os.getenv("GAME_CLUB_MYKET_ACCESS_TOKEN", "").strip()
    app_package: str = os.getenv("GAME_CLUB_APP_PACKAGE", "").strip() or "dezhcode.AsoTas.app"
    coin_packs: tuple[int, ...] = _ints("GAME_CLUB_COIN_PACKS", "50,120,250,600")
    turn_seconds: int = min(60, max(8, _int_env("GAME_CLUB_TURN_SECONDS", "20")))
    # چند ثانیه صبر در صف بازی آزاد قبل از پر کردن جای خالی با ربات
    # ۰ = صف ناشناس هیچ وقت خودکار با ربات پر نمی شود؛ میز وقتی کامل شد شروع می شود
    # (بازیکن صف آزاد می تواند خودش «شروع با ربات» را بزند). کلید قدیمی
    # GAME_CLUB_BOT_FILL_SECONDS عمدا خوانده نمی شود تا مقدار ۱۵ مانده در .env اثری نداشته باشد.
    bot_fill_seconds: int = max(0, _int_env("GAME_CLUB_QUEUE_AUTOBOT_SECONDS", "0"))
    # کد ورود ایمیلی برنامهٔ اندروید (mailer.py)؛ بدون HOST ورود با ایمیل خاموش است.
    # پورت ۴۶۵ یعنی SSL، بقیه STARTTLS (اگر سرور داشته باشد)
    smtp_host: str = os.getenv("GAME_CLUB_SMTP_HOST", "").strip()
    smtp_port: int = _int_env("GAME_CLUB_SMTP_PORT", "465")
    smtp_user: str = os.getenv("GAME_CLUB_SMTP_USER", "").strip()
    smtp_password: str = os.getenv("GAME_CLUB_SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("GAME_CLUB_SMTP_FROM", "").strip()
    # این دو فقط از پنل مدیریت عوض می شوند (جدول settings):
    # تعمیرات = بازی تازه شروع نمی شود (میزهای در جریان ادامه دارند)؛ اطلاعیه = نوار بالای صفحه خانه
    maintenance: bool = False
    notice: str = ""

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
