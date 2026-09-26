"""تنظیمات ربات از فایل env - هیچ توکنی هاردکد نمی شود."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ریشه پروژه (پوشه ای که main.py و passenger_wsgi.py در آن هستند)
BASE_DIR = Path(__file__).resolve().parent.parent

# فایل env همیشه از ریشه پروژه خوانده می شود، نه از پوشه جاری.
# روی هاست سی پنل پوشه جاری همیشه ریشه اپ نیست، پس این خط حیاتی است.
load_dotenv(BASE_DIR / ".env")


def _abs_path(value: str) -> str:
    """مسیر نسبی را به مسیر مطلق کنار پروژه تبدیل می کند."""
    p = Path(value).expanduser()
    return str(p if p.is_absolute() else (BASE_DIR / p))


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _str_list(name: str) -> list[str]:
    """فهرست رشته ای جدا شده با کاما (کانال های عضویت اجباری)."""
    raw = os.getenv(name, "")
    return [x.strip() for x in raw.split(",") if x.strip()]


def _int_env(name: str, default: str) -> int:
    """عدد از env با تحمل مقدار خالی یا غلط (ربات نباید بالا نیامدن بدهد)."""
    raw = (os.getenv(name, "") or "").strip()
    try:
        return int(raw) if raw else int(default)
    except ValueError:
        return int(default)


def _int_list(name: str) -> list[int]:
    raw = os.getenv(name, "")
    return [int(x) for x in raw.replace(" ", "").split(",") if x]


def _panel_url(name: str) -> str:
    """آدرس پایه پنل. اگر کاربر آدرس داشبورد را وارد کند، اصلاح می شود."""
    url = os.getenv(name, "").strip().rstrip("/")
    for suffix in ("/dashboard", "/admin", "/api"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url.rstrip("/")


@dataclass(slots=True)
class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    admin_ids: list[int] = field(default_factory=lambda: _int_list("ADMIN_IDS"))

    db_path: str = _abs_path(os.getenv("DB_PATH", "").strip() or "data/obour.db")

    panel_base_url: str = _panel_url("PANEL_BASE_URL")
    panel_api_key: str = os.getenv("PANEL_API_KEY", "")
    # روش دوم احراز هویت: یوزر/پسورد ادمین پنل (SDK رسمی با Bearer token کار می کند)
    panel_username: str = os.getenv("PANEL_USERNAME", "")
    panel_password: str = os.getenv("PANEL_PASSWORD", "")
    panel_verify_ssl: bool = _bool("PANEL_VERIFY_SSL", "true")
    # PANEL_GROUP_ID می تواند یک عدد باشد، یا all / خالی برای استفاده از همه گروه ها
    panel_group_id: int | None = (
        int(os.getenv("PANEL_GROUP_ID", "").strip())
        if os.getenv("PANEL_GROUP_ID", "").strip().isdigit()
        else None
    )
    panel_group_all: bool = not os.getenv("PANEL_GROUP_ID", "").strip().isdigit()

    # ===== هشدارها (اجرا با cron_tasks.py) =====
    warn_data_percent: int = int(os.getenv("WARN_DATA_PERCENT", "80"))
    warn_expire_days: int = int(os.getenv("WARN_EXPIRE_DAYS", "3"))
    winback_after_days: int = int(os.getenv("WINBACK_AFTER_DAYS", "2"))

    # ===== شارژ کیف پول =====
    # چند دقیقه مبلغ یکتای شارژ برای کاربر نگه داشته می شود. مهلت پرداخت
    # ربات و تایمر مینی اپ هر دو از همین عدد است. رسیدی که بعد از مهلت
    # برسد هنوز پذیرفته می شود؛ فقط مبلغ برای دیگران آزاد شده است.
    charge_ttl_minutes: int = max(1, _int_env("CHARGE_TTL_MINUTES", "2"))

    # ===== QR روی قاب برند =====
    # قاب پیش فرض assets/qr_frame.png است (۱۰۸۶ در ۱۴۴۸).
    # مختصات زیر برای همان تصویر اندازه گیری شده: باکس سفید از
    # x=194 تا 891 و y=301 تا 1111 است و QR در وسطش می نشیند.
    # اگر قاب را عوض کردی، این سه عدد را هم متناسبش کن.
    qr_frame_path: str = _abs_path(os.getenv("QR_FRAME_PATH", "assets/qr_frame.png"))
    qr_box_x: int = int(os.getenv("QR_BOX_X", "213"))
    qr_box_y: int = int(os.getenv("QR_BOX_Y", "376"))
    qr_box_size: int = int(os.getenv("QR_BOX_SIZE", "660"))
    qr_fg: str = os.getenv("QR_FG", "#0a1e3f")
    qr_bg: str = os.getenv("QR_BG", "#ffffff")

    # ===== افکت پیام (Bot API 7.2) =====
    # فقط در چت خصوصی و فقط روی پیام های تازه (نه ویرایش) کار می کند.
    # برای گرفتن آیدی یک افکت، همان پیام را با افکت دلخواه برای ربات
    # بفرست و مقدار effect_id را از آپدیت بردار.
    effect_trial: str = os.getenv("EFFECT_TRIAL", "5420104476780411731")
    effect_charge: str = os.getenv("EFFECT_CHARGE", "5343933807311467091")
    effect_purchase: str = os.getenv("EFFECT_PURCHASE", "5276520408655338097")

    # ===== ایموجی سفارشی روی دکمه ها (Bot API 9.4) =====
    # نیازمند Telegram Premium برای صاحب ربات.
    # آیدی ایموجی را از پیام حاوی آن ایموجی (فیلد custom_emoji_id) بردار.
    icon_buy: str = os.getenv("ICON_BUY", "")
    icon_wallet: str = os.getenv("ICON_WALLET", "")
    icon_gift: str = os.getenv("ICON_GIFT", "")
    icon_ok: str = os.getenv("ICON_OK", "")

    # ===== تست رایگان (بخش ۵.۵ سند) =====
    trial_enabled: bool = _bool("TRIAL_ENABLED", "true")
    trial_mb: int = int(os.getenv("TRIAL_MB", "200"))
    trial_days: int = int(os.getenv("TRIAL_DAYS", "1"))

    # ===== قیمت گذاری ساخت دلخواه (بخش ۵.۲ سند) =====
    # قیمت = حجم × نرخ هر گیگ × ضریب مدت
    custom_rate_per_gb: int = int(os.getenv("CUSTOM_RATE_PER_GB", "3500"))

    # ===== سیاست تمدید =====
    # true  : روزهای باقی مانده سرویس سوخت نمی شود و به مدت جدید اضافه می شود
    # false : تمدید از لحظه پرداخت حساب می شود (رفتار نسخه قبلی)
    renew_keep_remaining: bool = _bool("RENEW_KEEP_REMAINING", "true")

    # ===== کران خودکار (بدون نیاز به کران هاست) =====
    # ربات خودش کارهای دوره ای را در حاشیه رسیدگی به آپدیت های تلگرام
    # انجام می دهد. روی هاست هایی که کران سی پنل کار نمی کند، این تنها
    # راهی است که هشدارها و یادآوری ها واقعا فرستاده شوند.
    autocron_enabled: bool = _bool("AUTOCRON", "true")
    autocron_minutes: int = _int_env("AUTOCRON_MINUTES", "15")  # فاصله بین دورها
    autocron_budget: float = float(os.getenv("AUTOCRON_BUDGET", "15") or 15)

    # ===== خودپینگ (بیدار نگه داشتن پروسه) =====
    # ربات هر چند دقیقه یک درخواست به /health خودش می زند تا Passenger
    # پروسه را نکشد. نیاز به WEBHOOK_BASE_URL دارد.
    keepalive_enabled: bool = _bool("KEEPALIVE", "true")
    keepalive_minutes: int = _int_env("KEEPALIVE_MINUTES", "15")

    # ===== مهلت پاسخ پنل =====
    # پیش فرض قبلی ۲۰ ثانیه بود. وقتی پنل پشت کلادفلر کند می شود و ۵۲۲
    # می دهد، کاربر تمام آن مدت پشت یک صفحه در حال بارگذاری می ماند.
    # ۸ ثانیه برای یک پنل سالم کاملا کافی است و در حالت خرابی، خیلی
    # زودتر به مسیر جایگزین می رسیم.
    panel_timeout: float = float(os.getenv("PANEL_TIMEOUT", "8") or 8)

    # ===== پاداش هم سفرها (معرفی) =====
    # پاداش وقتی داده می شود که کاربر دعوت شده واقعا خرید کند (نه صرف
    # استارت زدن)، تا کسی با ساختن اکانت الکی کیف پول پر نکند.
    ref_enabled: bool = _bool("REF_ENABLED", "true")
    ref_percent: int = _int_env("REF_PERCENT", "10")          # درصد از هر خرید
    ref_first_bonus: int = _int_env("REF_FIRST_BONUS", "0")   # پاداش اضافه اولین خرید
    ref_min_order: int = _int_env("REF_MIN_ORDER", "0")       # حداقل مبلغ خرید
    ref_max_reward: int = _int_env("REF_MAX_REWARD", "0")     # سقف هر پاداش، ۰ = بی سقف

    # ===== عضویت اجباری در کانال =====
    # هر مورد یا @username است یا به شکل  -1001234567890=https://t.me/+abc
    join_channels: list[str] = field(default_factory=lambda: _str_list("JOIN_CHANNELS"))

    # کانالی که ربات در آن پست می گذارد (آیدی عددی، مثل -1001234567890).
    # ربات باید ادمین کانال باشد. از پنل ادمین هم قابل تغییر است.
    channel_id: str = os.getenv("CHANNEL_ID", "")
    join_for_trial: bool = _bool("JOIN_FOR_TRIAL", "true")

    # ===== پرداخت کریپتو (TON و USDT روی شبکه TON) =====
    # بدون آدرس کیف پول، این بخش کلا خاموش است. کلید خصوصی هیچ وقت لازم
    # نیست: ربات فقط تراکنش های ورودی این آدرس را می خواند.
    ton_network: str = (os.getenv("TON_NETWORK", "").strip().lower() or "mainnet")
    ton_receive_address: str = os.getenv("TON_RECEIVE_ADDRESS", "").strip()
    # کلید Toncenter از @tonapibot (برای testnet کلید جدا می دهد)
    toncenter_api_key: str = os.getenv("TONCENTER_API_KEY", "").strip()
    # خالی = آدرس پیش فرض Toncenter برای همان شبکه
    toncenter_url: str = os.getenv("TONCENTER_URL", "").strip().rstrip("/")
    # مستر جتون USDT. روی mainnet خالی بماند (آدرس رسمی تتر استفاده می شود).
    # روی testnet تتر رسمی نیست؛ یک جتون تستی با ۶ رقم اعشار بساز و آدرسش را بگذار.
    ton_usdt_master: str = os.getenv("TON_USDT_MASTER", "").strip()
    ton_usdt_decimals: int = _int_env("TON_USDT_DECIMALS", "6")
    # مهلت پرداخت هر فاکتور (دقیقه)؛ پول دیرتر هم تا ۴۸ ساعت شناخته می شود
    crypto_invoice_minutes: int = _int_env("CRYPTO_INVOICE_MINUTES", "20")
    # اگر هاست به toncenter.com دسترسی ندارد: http://host:port یا socks5://...
    ton_proxy: str = os.getenv("TON_PROXY", "").strip()

    # نوع آپدیت هایی که وبهوک می گیرد. pre_checkout_query برای پرداخت
    # Telegram Stars لازم است؛ بدون آن پرداخت ستاره بعد از ۱۰ ثانیه رد می شود.
    allowed_updates: tuple = ("message", "callback_query", "my_chat_member", "pre_checkout_query")

    webhook_mode: bool = _bool("WEBHOOK_MODE")
    webhook_base_url: str = os.getenv("WEBHOOK_BASE_URL", "").rstrip("/")
    webhook_path: str = "/" + (os.getenv("WEBHOOK_PATH", "").strip().strip("/") or "webhook/obour")
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "")
    # کلید مدیریتی برای /status و /setwebhook و /delwebhook.
    # جدا از WEBHOOK_SECRET است چون در URL می آید و در access log هاست
    # ذخیره می شود؛ نباید همان رشته ای باشد که تلگرام با آن احراز می شود.
    admin_key: str = os.getenv("ADMIN_KEY", "")
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8080"))

    # ===== شبکه تلگرام =====
    # اگر سرور به api.telegram.org دسترسی مستقیم ندارد (هاست ایران)
    # یک پروکسی بگذار: socks5://user:pass@host:port  یا  http://host:port
    tg_proxy: str = os.getenv("TG_PROXY", "").strip()
    # یا یک آدرس واسط بجای api.telegram.org (Local Bot API / reverse proxy)
    tg_api_base: str = os.getenv("TG_API_BASE", "").strip().rstrip("/")

    # ===== لاگ =====
    log_path: str = _abs_path(os.getenv("LOG_PATH", "").strip() or "logs/obour.log")
    log_level: str = (os.getenv("LOG_LEVEL", "").strip() or "INFO").upper()

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_base_url}{self.webhook_path}"

    @property
    def import_base(self) -> str:
        """آدرس صفحه واسط «اتصال سریع».

        تلگرام در دکمه url فقط http و https و tg را می پذیرد، پس لینک
        اسکیم برنامه ها (hiddify:// و ...) را نمی شود مستقیم روی دکمه
        گذاشت. این صفحه روی همان دامنه ربات باز می شود و کاربر را به
        برنامه می فرستد. اگر WEBHOOK_BASE_URL خالی باشد، ربات به جای
        دکمه، لینک را برای کپی می دهد.
        """
        return f"{self.webhook_base_url}/import" if self.webhook_base_url else ""

    @property
    def app_base_uri(self) -> str:
        """زیرمسیری که اپ روی آن سوار است، مثلا /obour.

        از WEBHOOK_BASE_URL استخراج می شود و برای نرمال کردن مسیر درخواست
        زیر Passenger لازم است (بعضی نسخه ها SCRIPT_NAME را ست نمی کنند)."""
        from urllib.parse import urlparse

        override = os.getenv("APP_BASE_URI", "").strip()
        raw = override if override else urlparse(self.webhook_base_url).path
        raw = raw.strip("/")
        return f"/{raw}" if raw else ""

    @property
    def base_dir(self) -> Path:
        return BASE_DIR


config = Config()
