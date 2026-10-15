"""ایموجی های پریمیوم Game Club (مثل app/emoji.py عبور).

هر ایموجی یک کلید دارد با یک ایموجی معمولی پیش فرض. ادمین برای هر کلید یک ایموجی
پریمیوم تنظیم می کند (در ربات Game Club با /gcemoji یا کپی از عبور) و بدون تغییر کد
همه جا عوض می شود:
  متن HTML      -> <tg-emoji emoji-id="123">🃏</tg-emoji>
  پیام غنی       -> RichTextCustomEmoji (در متن و روی دکمه های داخل پیام)
  دکمهٔ شیشه ای  -> icon_custom_emoji_id (پیوی ربات و پیام همگانی)
اگر چیزی تنظیم نشده باشد (یا صاحب ربات پریمیوم نداشته باشد) همان ایموجی معمولی دیده می شود.
آیدی ها در جدول settings با کلید emoji:<key> هستند و هر ۱۰ ثانیه با تنظیمات پنل خوانده می شوند.
"""
from __future__ import annotations

import html
import re

PREFIX = "emoji:"

# کلید -> (ایموجی پیش فرض، عنوان برای پنل)؛ هر ایموجی پیش فرض فقط یک بار
CATALOG: dict[str, tuple[str, str]] = {
    "brand": ("🎮", "نماد Game Club"),
    "hello": ("👋", "سلام و خوش آمد"),
    "hokm": ("🃏", "حکم"),
    "ludo": ("🎲", "منچ"),
    "football": ("⚽", "فوتبال"),
    "billiard": ("🎱", "بیلیارد"),
    "seat": ("🪑", "صندلی خالی و بشین"),
    "leave": ("🚪", "بلند شو"),
    "robot": ("🤖", "ربات و شروع با ربات"),
    "watch": ("👀", "دیدن بازی"),
    "trophy": ("🏆", "برنده"),
    "crown": ("👑", "سازندهٔ میز"),
    "users": ("👥", "بازیکن ها"),
    "gear": ("⚙️", "تنظیم میز"),
    "play": ("▶️", "باز کردن میز و شروع"),
    "new": ("➕", "میز تازه"),
    "cancel": ("✖️", "لغو"),
    "selected": ("✅", "گزینهٔ انتخاب شده"),
    "time": ("⏱", "طول بازی"),
    "score": ("🎯", "نتیجه"),
    "coin": ("💰", "امتیاز و کیف"),
    "star": ("⭐", "سطح و رتبه"),
    "fire": ("🔥", "محبوب"),
    "turn": ("⏰", "نوبت تو"),
    "bell": ("🔔", "اعلان"),
    "chat": ("💬", "پیام دوستان"),
    "friend": ("🤝", "دوستی"),
    "gift": ("🎁", "هدیه"),
    "party": ("🎉", "تبریک"),
    "group": ("🏟", "بازی در گروه"),
    "link": ("🔗", "دعوت"),
    "help": ("📖", "راهنما"),
    "shop": ("🛍", "فروشگاه"),
    "home": ("🏠", "خانه"),
    "megaphone": ("📢", "پیام همگانی"),
    "chart": ("📊", "آمار"),
    "ban": ("🚫", "مسدود"),
    "warn": ("⚠️", "هشدار"),
    "ok": ("✔️", "انجام شد"),
}

# دسته ها برای صفحهٔ مدیریت ایموجی در ربات (مثل عبور: دسته -> فهرست -> ایموجی)
CATEGORIES: dict[str, list[str]] = {
    "بازی‌ها": ["brand", "hokm", "ludo", "football", "billiard", "group", "trophy", "score", "time"],
    "میز و دکمه‌ها": ["seat", "leave", "robot", "watch", "crown", "users", "gear", "play", "new", "cancel", "selected"],
    "امتیاز و اعلان": ["coin", "star", "fire", "turn", "bell", "chat", "friend", "gift", "party", "link"],
    "عمومی": ["hello", "help", "shop", "home", "megaphone", "chart", "ban", "warn", "ok"],
}

_cache: dict[str, str] = {}


def _base(e: str) -> str:
    return e.replace("️", "")


def load_rows(rows: dict) -> None:
    """از خروجی settings_all (همان که تنظیمات پنل را می خواند)."""
    _cache.clear()
    for k, v in rows.items():
        if k.startswith(PREFIX) and v and k[len(PREFIX):] in CATALOG:
            _cache[k[len(PREFIX):]] = str(v)


async def load(db) -> None:  # noqa: ANN001
    load_rows(await db.settings_all())


async def set_emoji(db, key: str, eid: str) -> None:  # noqa: ANN001
    await db.setting_put(PREFIX + key, eid)
    _cache[key] = eid


async def reset(db, key: str) -> None:  # noqa: ANN001
    await db.setting_put(PREFIX + key, None)
    _cache.pop(key, None)


def default(key: str) -> str:
    return CATALOG.get(key, ("", ""))[0]


def custom_id(key: str) -> str | None:
    return _cache.get(key) or None


def key_of(e: str) -> str | None:
    """کلید کاتالوگ برای یک ایموجی معمولی (بدون حساسیت به FE0F)."""
    b = _base(e)
    return next((k for k, (d, _) in CATALOG.items() if _base(d) == b), None)


def html_of(key: str) -> str:
    d, eid = default(key), custom_id(key)
    return f'<tg-emoji emoji-id="{eid}">{d}</tg-emoji>' if eid else d


def rich_of(key: str):  # noqa: ANN201
    """برای پیام غنی: RichTextCustomEmoji یا همان ایموجی معمولی."""
    d, eid = default(key), custom_id(key)
    if not eid:
        return d
    from aiogram.types import RichTextCustomEmoji

    return RichTextCustomEmoji(custom_emoji_id=eid, alternative_text=d)


# ---------- جایگزینی خودکار در متن HTML (پیام همگانی، پیام ادمین) ----------
_TAG = re.compile(r"<tg-emoji\b[^>]*>.*?</tg-emoji>", re.S)


def apply(text: str) -> str:
    """هر ایموجی کاتالوگ که پریمیومش تنظیم شده، در متن HTML پریمیوم می شود (تگ های موجود دست نمی خورند)."""
    if not _cache or not text:
        return text
    mapping = {_base(default(k)): eid for k, eid in _cache.items()}
    pat = re.compile("|".join(re.escape(e) + "️?" for e in sorted(mapping, key=len, reverse=True)))

    def sub(m: re.Match) -> str:
        whole = m.group(0)
        return f'<tg-emoji emoji-id="{mapping[_base(whole)]}">{whole}</tg-emoji>'

    out, last = [], 0
    for m in _TAG.finditer(text):
        out.append(pat.sub(sub, text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(pat.sub(sub, text[last:]))
    return "".join(out)


_LEAD = re.compile(r"^([\U0001F000-\U0001FAFF←-⇿⌀-➿⬀-⯿■-◿][️‍\U0001F3FB-\U0001F3FF]*)\s*")


def button(label: str, key: str | None = None) -> dict:
    """متن و آیکن دکمهٔ شیشه ای: اگر کلید (یا ایموجی اول متن) پریمیوم دارد، ایموجی از متن
    برداشته می شود و آیکن کنار متن می نشیند؛ وگرنه همان «ایموجی + متن»."""
    label = (label or "").strip()
    m = _LEAD.match(label)
    rest = label[m.end():].strip() if m else label
    k = key or (key_of(m.group(1)) if m else None)
    # کلید می تواند خود آیدی ایموجی پریمیوم هم باشد (دکمه ای که ادمین در ربات با ایموجی پریمیوم نوشته)
    eid = (k if k.isdigit() else custom_id(k)) if k else None
    if eid and rest:
        return {"text": rest, "icon_custom_emoji_id": eid}
    if k and not m and default(k):
        return {"text": f"{default(k)} {label}".strip()}
    return {"text": label}


# ---------- تنظیم از روی پیام ادمین ----------
def from_message(text: str, entities) -> list[tuple[str, str]]:  # noqa: ANN001
    """(کلید، آیدی) برای هر ایموجی پریمیوم پیام که ایموجی جایگزینش در کاتالوگ است."""
    out: list[tuple[str, str]] = []
    for e in entities or []:
        if e.type != "custom_emoji" or not e.custom_emoji_id:
            continue
        k = key_of(e.extract_from(text or ""))
        if k and all(k != x for x, _ in out):
            out.append((k, e.custom_emoji_id))
    return out


def first_custom(entities) -> str | None:  # noqa: ANN001
    return next((e.custom_emoji_id for e in entities or [] if e.type == "custom_emoji" and e.custom_emoji_id), None)


def from_obour() -> list[tuple[str, str]]:
    """ایموجی های پریمیومی که در عبور برای همین ایموجی ها تنظیم شده (همان پروسه)."""
    try:
        from app import emoji as ob
    except Exception:  # noqa: BLE001
        return []
    by_base = {_base(d): ob.custom_id(k) for k, (d, _t, _c) in ob.CATALOG.items() if ob.custom_id(k)}
    return [(k, by_base[_base(d)]) for k, (d, _) in CATALOG.items() if by_base.get(_base(d))]


def listing() -> list[dict]:
    return [{"key": k, "emoji": d, "title": t, "id": _cache.get(k, "")} for k, (d, t) in CATALOG.items()]


def esc(s: str) -> str:
    return html.escape(str(s or ""), quote=False)
