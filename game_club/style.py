"""قالب متنی پیام های AsoTas، همان سبک عبور:

    ╮── 👋 AsoTas
    │   خوش اومدی

    سلام، بازی با منه.

    💰 امتیاز
    ╯─ ⁨1,250⁩ امتیاز

یک بار ساخته می شود و دو خروجی دارد: HTML برای پیام معمولی (پیوی، اعلان، همگانی) و یک
پاراگراف پیام غنی برای کارت های گروه (یک بلوک تا خط ها همان طور که نوشته شده بمانند).
هر خط با نشانهٔ راست به چپ (RLM) شروع می شود تا یوزرنیم لاتین یا عدد جهت خط را عوض نکند.
"""
from __future__ import annotations

import html

from . import emoji as emo

RLM, FSI, PDI = "\u200f", "\u2068", "\u2069"
# همهٔ عددهای پیام های ربات لاتین اند (۱۲ -> 12)، هر جا که نوشته شده باشند
LATIN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def en(s: str) -> str:
    return str(s).translate(LATIN)


class E:
    """ایموجی کاتالوگ (پریمیوم اگر تنظیم شده)."""
    def __init__(self, key: str) -> None:
        self.key = key


class B:
    """متن پررنگ."""
    def __init__(self, *parts) -> None:  # noqa: ANN002
        self.parts = list(parts)


class M:
    """منشن کاربر با شناسهٔ تلگرام."""
    def __init__(self, tg: int, name: str) -> None:
        self.tg, self.name = int(tg), name or "بازیکن"


class Raw:
    """HTML آماده (فقط در خروجی HTML؛ در پیام غنی برچسب ها حذف می شوند)."""
    def __init__(self, text: str) -> None:
        self.text = text


def iso(s) -> str:  # noqa: ANN001
    """عدد یا اسم لاتین وسط متن فارسی: جدا از جهت خط."""
    return f"{FSI}{s}{PDI}"


def num(n: int) -> str:
    return iso(f"{int(n):,}")


def _line(x) -> list:  # noqa: ANN001
    return list(x) if isinstance(x, (list, tuple)) else [x]


def frame(icon: str, title, sub=None, lines=(), foot=None) -> list:  # noqa: ANN001
    """icon: کلید ایموجی؛ title و sub: متن یا قطعه ها؛ lines: خط های بدنه ("" = خط خالی)؛
    foot: (کلید ایموجی، برچسب، مقدار) یا (None، None، مقدار) برای خط آخر «╯─»."""
    rows: list[list] = [["╮── ", E(icon), " ", *_line(title)]]
    if sub is not None:
        rows.append(["│   ", *_line(sub)])
    body = [[] if x == "" else _line(x) for x in lines]
    if body:
        rows.append([])
        rows += body
    if foot:
        k, label, value = foot
        if label is not None:
            rows.append([])
            rows.append([E(k), " ", *_line(label)] if k else _line(label))
        rows.append(["╯─ ", *_line(value)])
    out: list = []
    for i, r in enumerate(rows):
        if i:
            out.append("\n")
        if r:
            out.append(RLM)
            out += r
    return out


def to_html(parts: list) -> str:
    out = []
    for p in parts:
        if isinstance(p, str):
            out.append(html.escape(en(p), quote=False))
        elif isinstance(p, E):
            out.append(emo.html_of(p.key))
        elif isinstance(p, B):
            out.append(f"<b>{to_html(p.parts)}</b>")
        elif isinstance(p, M):
            out.append(f'<a href="tg://user?id={p.tg}">{html.escape(p.name, quote=False)}</a>')
        elif isinstance(p, Raw):
            out.append(en(p.text))
    return "".join(out)


def to_rich(parts: list) -> list:
    """قطعه های پیام غنی (رشته های پشت سر هم یکی می شوند)."""
    from aiogram.types import RichTextBold, RichTextTextMention, User

    out: list = []

    def put(x) -> None:  # noqa: ANN001
        if isinstance(x, str) and out and isinstance(out[-1], str):
            out[-1] += x
        elif x != "":
            out.append(x)

    for p in parts:
        if isinstance(p, str):
            put(en(p))
        elif isinstance(p, E):
            put(emo.rich_of(p.key))
        elif isinstance(p, B):
            inner = to_rich(p.parts)
            put(RichTextBold(text=inner[0] if len(inner) == 1 else inner))
        elif isinstance(p, M):
            put(RichTextTextMention(text=p.name, user=User(id=p.tg, is_bot=False, first_name=p.name)))
        elif isinstance(p, Raw):
            import re

            put(en(html.unescape(re.sub(r"<[^>]+>", "", p.text))))
    return out


def plain(parts: list) -> str:
    """متن ساده (برای آزمون و لاگ)."""
    out = []
    for p in parts:
        if isinstance(p, str):
            out.append(en(p))
        elif isinstance(p, E):
            out.append(emo.default(p.key))
        elif isinstance(p, B):
            out.append(plain(p.parts))
        elif isinstance(p, M):
            out.append(p.name)
        elif isinstance(p, Raw):
            out.append(p.text)
    return "".join(out)


def kb_button(label: str, key: str | None = None, **kw):  # noqa: ANN201
    """دکمهٔ شیشه ای (پیوی) با آیکن پریمیوم اگر تنظیم شده."""
    from aiogram.types import InlineKeyboardButton

    return InlineKeyboardButton(**emo.button(en(label), key), **kw)


def rich_button(key: str | None, label: str, style: str | None = None, **kw):  # noqa: ANN201
    """دکمهٔ داخل پیام غنی (گروه و اینلاین)، با ایموجی پریمیوم در متنش."""
    from aiogram.types import RichMessageButton

    text = to_rich([E(key), " ", label]) if key else [en(label)]
    return RichMessageButton(text=text[0] if len(text) == 1 else text, style=style, **kw)
