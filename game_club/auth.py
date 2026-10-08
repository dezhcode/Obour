"""تایید initData مینی اپ Game Club.

همان الگوریتم مینی اپ عبور (app/webapp/auth.py) است، فقط با توکن ربات
Game Club امضا می شود؛ initData ای که برای ربات عبور صادر شده اینجا قبول
نمی شود و برعکس.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from app.webapp.auth import MAX_AGE, AuthError, WebAppUser, _candidates

from .config import gc

__all__ = ["AuthError", "GCUser", "WebAppUser", "photo_ok", "sign", "verify"]

# عکس پروفایل تلگرام (photo_url در initData) فقط از دامنه های خود تلگرام پذیرفته می شود
_PHOTO_HOSTS = ("t.me", "telegram.org", "telesco.pe", "telegram-cdn.org")


def photo_ok(url: str) -> str:
    """آدرس عکس اگر امن و از تلگرام باشد، وگرنه رشته خالی."""
    url = (url or "").strip()
    if not url or len(url) > 400 or any(ch in url for ch in " \"'<>`\\"):
        return ""
    try:
        u = urlparse(url)
    except ValueError:
        return ""
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not any(host == h or host.endswith("." + h) for h in _PHOTO_HOSTS):
        return ""
    return url


@dataclass(slots=True)
class GCUser(WebAppUser):
    last_name: str = ""
    photo_url: str = ""

    @property
    def full_name(self) -> str:
        return " ".join(x for x in (self.first_name, self.last_name) if x).strip()


def sign(fields: dict, token: str | None = None) -> str:
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", (token or gc.token).encode(), hashlib.sha256).digest()
    return hmac.new(secret, check.encode("utf-8"), hashlib.sha256).hexdigest()


def verify(init_data: str) -> GCUser:
    if not init_data:
        raise AuthError("initData خالی است")
    if not gc.token:
        raise AuthError("GAME_CLUB_BOT_TOKEN تنظیم نشده")
    matched = None
    for _name, fields, given in _candidates(init_data):
        if given and hmac.compare_digest(sign(fields), given):
            matched = fields
            break
    if matched is None:
        raise AuthError("امضای initData معتبر نیست")
    try:
        auth_date = int(matched.get("auth_date", "0"))
    except ValueError:
        auth_date = 0
    if auth_date <= 0 or (MAX_AGE and time.time() - auth_date > MAX_AGE):
        raise AuthError("نشست منقضی شده؛ مینی اپ را دوباره باز کن")
    try:
        raw = json.loads(matched.get("user") or "{}")
    except ValueError:
        raw = {}
    uid = raw.get("id")
    if not isinstance(uid, int) or uid <= 0:
        raise AuthError("کاربر در initData نیست")
    return GCUser(
        id=uid,
        first_name=(raw.get("first_name") or "")[:64],
        username=(raw.get("username") or "")[:64],
        language_code=(raw.get("language_code") or "")[:8],
        is_premium=bool(raw.get("is_premium")),
        start_param=(matched.get("start_param") or "")[:64],
        last_name=(raw.get("last_name") or "")[:64],
        photo_url=photo_ok(raw.get("photo_url") or ""),
    )
