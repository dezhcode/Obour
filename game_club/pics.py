"""عکس پروفایل تلگرام بازیکن ها برای مینی اپ.

اگر initData تلگرام photo_url داشته باشد، مینی اپ همان را نشان می دهد. اگر
نداشته باشد (مثلا کاربر از دکمه ربات وارد شده)، عکس از Bot API
(getUserProfilePhotos) گرفته و روی دیسک نگه داشته می شود و از /gc/pic/<key>
سرو می شود. آدرس فایل Bot API توکن ربات را دارد، پس هیچ وقت به مرورگر نمی رود.
key یک رشته تصادفی برای هر بازیکن است تا آیدی تلگرام کسی در آدرس نیاید.
"""
from __future__ import annotations

import logging
import os
import re
import time

from .config import gc

log = logging.getLogger("gameclub.pics")

KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,24}$")
TTL_OK = 24 * 3600        # عکس پیدا شده یک روز نگه داشته می شود
TTL_NONE = 6 * 3600       # «عکس ندارد» شش ساعت
TTL_ERR = 10 * 60         # خطای شبکه ده دقیقه (تا به تلگرام فشار نیاید)
MAX_BYTES = 512 * 1024


def pic_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(gc.db_path)), "gc_pics")


def _paths(key: str) -> tuple[str, str]:
    d = pic_dir()
    return os.path.join(d, key + ".jpg"), os.path.join(d, key + ".none")


def _fresh(path: str, ttl: int) -> bool:
    try:
        return time.time() - os.path.getmtime(path) < ttl
    except OSError:
        return False


def cached(key: str) -> tuple[str, bytes | None]:
    """("hit", عکس) یا ("none", None) یا ("miss", None)."""
    jpg, none = _paths(key)
    if _fresh(jpg, TTL_OK):
        with open(jpg, "rb") as fh:
            return "hit", fh.read()
    if os.path.exists(none):
        try:
            with open(none) as fh:
                ttl = TTL_ERR if fh.read().strip() == "err" else TTL_NONE
        except OSError:
            ttl = TTL_NONE
        if _fresh(none, ttl):
            return "none", None
    return "miss", None


def _write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


async def fetch(key: str) -> bytes | None:
    """عکس را از Bot API می گیرد و نگه می دارد. فقط برای کلید بازیکن های واقعی."""
    from .bot import gcrt

    g = await gcrt.ensure()
    p = await g.db.player_by_pic(key)
    if not p or not g.bot:
        return None  # کلید ناشناس: چیزی روی دیسک نوشته نمی شود
    jpg, none = _paths(key)
    try:
        photos = await g.bot.get_user_profile_photos(p["tg_id"], limit=1)
        if not photos.total_count or not photos.photos:
            _write(none, b"none")
            return None
        sizes = sorted(photos.photos[0], key=lambda s: s.width)
        pick = next((s for s in sizes if s.width >= 160), sizes[-1])
        if pick.file_size and pick.file_size > MAX_BYTES:
            pick = sizes[0]
        f = await g.bot.get_file(pick.file_id)
        buf = await g.bot.download_file(f.file_path)
        data = buf.read() if buf else b""
        if not data or len(data) > MAX_BYTES:
            _write(none, b"none")
            return None
        _write(jpg, data)
        if os.path.exists(none):
            os.remove(none)
        return data
    except Exception as exc:  # noqa: BLE001
        log.warning("عکس پروفایل %s گرفته نشد: %s", key, exc)
        _write(none, b"err")
        return None
