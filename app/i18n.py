"""چندزبانه: فارسی (پایه)، انگلیسی، روسی و چینی.

زبان هر کاربر در ستون users.lang است. تا وقتی کاربر خودش انتخاب نکرده
(NULL)، زبان از language_code تلگرامش حدس زده می شود و در اولین /start
صفحه انتخاب زبان با همان حدس به عنوان پیشنهاد نشان داده می شود.

زبان جاری در یک ContextVar نگه داشته می شود، نه در آرگومان توابع. هر
آپدیت تلگرام و هر درخواست مینی اپ در تسک خودش اجرا می شود، پس کافی است
middleware (یا API) یک بار set_lang بزند؛ بعد از آن:

- texts.X خودش ترجمه زبان جاری را برمی گرداند (texts.py آخرش ماژولش را
  به یک ماژول زبان آگاه تبدیل می کند)، پس صدها جای texts.X.format(...)
  دست نخورده می مانند.
- _add در keyboards.py متن هر دکمه را با t() ترجمه می کند.
- متن های پراکنده داخل هندلرها (پاپ آپ ها و پیام های کوتاه) با t()
  پیچیده شده اند.

پیام به کاربر دیگر (تایید شارژ توسط ادمین، هشدار کران، پاداش معرفی) باید
به زبان گیرنده باشد، نه فرستنده: قالب بندی آن داخل `with using(lang):`
انجام می شود.

پنل ادمین عمدا فارسی می ماند.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

LANGS = ("fa", "en", "ru", "zh")
DEFAULT = "fa"
# برای language_code هایی که هیچ کدام از چهار زبان نیستند
FALLBACK = "en"

# نام هر زبان به زبان خودش، برای دکمه های انتخاب
NAMES = {"fa": "فارسی", "en": "English", "ru": "Русский", "zh": "中文"}
FLAGS = {"fa": "🇮🇷", "en": "🇬🇧", "ru": "🇷🇺", "zh": "🇨🇳"}

_current: ContextVar[str] = ContextVar("obour_lang", default=DEFAULT)


def normalize(code: str | None) -> str | None:
    """کد زبان ذخیره شده یا ارسالی را به یکی از LANGS می برد، یا None."""
    code = (code or "").strip().lower()
    return code if code in LANGS else None


def detect(language_code: str | None) -> str:
    """حدس زبان از language_code تلگرام (مثل fa، en-US، zh-hans، ru)."""
    code = (language_code or "").strip().lower().replace("_", "-")
    base = code.split("-", 1)[0]
    if base in ("fa", "ps", "tg"):          # فارسی، پشتو و تاجیکی: فارسی نزدیک ترین است
        return "fa"
    if base in ("ru", "uk", "be", "kk", "ky", "uz"):  # کشورهایی که روسی رایج است
        return "ru"
    if base == "zh":
        return "zh"
    if base == "en":
        return "en"
    return FALLBACK if base else DEFAULT


def lang_of(user: dict | None, language_code: str | None = None) -> str:
    """زبان یک کاربر: انتخاب خودش، وگرنه حدس از تلگرام."""
    chosen = normalize((user or {}).get("lang"))
    if chosen:
        return chosen
    return detect(language_code) if language_code else DEFAULT


def get_lang() -> str:
    return _current.get()


def set_lang(lang: str | None) -> None:
    _current.set(normalize(lang) or DEFAULT)


def is_rtl(lang: str | None = None) -> bool:
    return (lang or get_lang()) == "fa"


@contextmanager
def using(lang: str | None) -> Iterator[None]:
    """برای قالب بندی پیامی که به کاربر دیگری فرستاده می شود."""
    token = _current.set(normalize(lang) or DEFAULT)
    try:
        yield
    finally:
        _current.reset(token)


def _catalog(lang: str) -> dict:
    from app.locales import catalog

    return catalog(lang)


def t(text: str, **kw) -> str:
    """ترجمه یک عبارت کوتاه که متن فارسی اش کلید است.

    عبارتی که ترجمه نشده باشد همان فارسی برمی گردد تا چیزی نشکند.
    """
    lang = get_lang()
    out = text
    if lang != DEFAULT and text:
        out = _catalog(lang).get("PHRASES", {}).get(text, text)
    return out.format(**kw) if kw else out


def text(name: str, fa_value):  # noqa: ANN001, ANN201
    """ثابت texts.py به زبان جاری؛ اگر ترجمه نداشت، همان فارسی."""
    lang = get_lang()
    if lang == DEFAULT:
        return fa_value
    return _catalog(lang).get("TEXTS", {}).get(name, fa_value)
