"""ورود برنامهٔ اندروید Game Club (بیرون از تلگرام initData نیست).

فعلا فقط حالت مهمان: برنامه بار اول یک حساب مهمان می گیرد (یوزرنیم تصادفی، مثل مینی اپ؛ بعدا عوض
می شود) و یک توکن نشست که در هدر X-GC-Token می فرستد. توکن فقط به صورت هش در دیتابیس می ماند.
حساب مهمان tg_id منفی دارد تا با آیدی های تلگرام قاطی نشود؛ هر جا که به کاربر پیام تلگرامی
می رود یا عضویتش در تلگرام پرسیده می شود (اعلان، پیام همگانی، عضویت اجباری، عکس پروفایل،
کیف عبور) از مهمان رد می شود. سیستم ورود (تلگرام و ایمیل) بعدا همین نشست ها را به حساب وصل می کند.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import time

SESSION_DAYS = 365       # نشست مهمانی که این مدت باز نشده بسته می شود (حساب می ماند)
TOUCH_EVERY = 3600
GUEST_NAME = "مهمان"
_TOKEN = re.compile(r"^gcs_[A-Za-z0-9_-]{32,64}$")


def is_guest(tg_id: int) -> bool:
    return int(tg_id) < 0


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def clean_device(text: str) -> str:
    return re.sub(r"[^\w .\-+()/]", "", text or "", flags=re.UNICODE).strip()[:40]


async def new_guest(db, device: str = "", *, now: float | None = None) -> dict:  # noqa: ANN001
    """حساب مهمان تازه با یوزرنیم تصادفی و توکن نشست: {'token', 'player'}."""
    now = int(now or time.time())
    for _ in range(8):
        # زیر ۲^۵۲ تا در جاوااسکریپت دقیق بماند
        gid = -1 - secrets.randbelow(2 ** 52 - 1)
        if not await db.one("SELECT 1 FROM players WHERE tg_id = ?", (gid,)):
            break
    else:
        raise RuntimeError("guest id")
    player = await db.player(gid, GUEST_NAME, None)
    token = "gcs_" + secrets.token_urlsafe(32)
    await db.execute("INSERT INTO app_sessions(token_hash, tg_id, device, created_at, seen_at) VALUES(?,?,?,?,?)",
                     (_hash(token), gid, clean_device(device), now, now))
    return {"token": token, "player": player}


async def session_player(db, token: str, *, now: float | None = None) -> dict | None:  # noqa: ANN001
    """بازیکن صاحب توکن نشست؛ None اگر توکن نامعتبر یا منقضی است."""
    if not _TOKEN.match(token or ""):
        return None
    now = int(now or time.time())
    h = _hash(token)
    row = await db.one("SELECT tg_id, seen_at FROM app_sessions WHERE token_hash = ?", (h,))
    if not row or now - row["seen_at"] > SESSION_DAYS * 86400:
        if row:
            await db.execute("DELETE FROM app_sessions WHERE token_hash = ?", (h,))
        return None
    if now - row["seen_at"] > TOUCH_EVERY:
        await db.execute("UPDATE app_sessions SET seen_at = ? WHERE token_hash = ?", (now, h))
    return await db.get_player(row["tg_id"])


async def logout(db, token: str) -> None:  # noqa: ANN001
    if _TOKEN.match(token or ""):
        await db.execute("DELETE FROM app_sessions WHERE token_hash = ?", (_hash(token),))
