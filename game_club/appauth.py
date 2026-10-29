"""حساب و نشست برنامهٔ اندروید AsoTas (بیرون از تلگرام initData نیست).

برنامه بار اول یک حساب مهمان می گیرد (یوزرنیم تصادفی، مثل مینی اپ؛ بعدا عوض می شود) و یک توکن
نشست که در هدر X-GC-Token می فرستد. توکن ها و کدها فقط به صورت هش در دیتابیس می مانند.

سه جور حساب:
  مهمان    tg_id منفی، بی ایمیل؛ اگر برنامه پاک شود از دست می رود
  ایمیلی   tg_id منفی با یک ایمیل در app_emails؛ با کد ایمیل از هر گوشی برمی گردد
  تلگرامی  همان tg_id تلگرام؛ همان حساب مینی اپ (پروفایل، رفقا، بازی ها)
هر جا که به کاربر پیام تلگرامی می رود یا عضویتش در تلگرام پرسیده می شود (اعلان، پیام همگانی، عضویت
اجباری، عکس پروفایل، کیف عبور) tg_id منفی رد می شود.

ورود با تلگرام: برنامه لینک t.me/<ربات>?start=login_<کد> را باز می کند، ربات از کاربر تأیید می گیرد
(با اسم گوشی، تا کسی نتواند لینک خودش را برای دیگری بفرستد و حسابش را بگیرد) و برنامه با رمز جدای poll
که فقط خودش دارد نتیجه را می پرسد. ورود با ایمیل: کد ۶ رقمی (۱۰ دقیقه، ۵ بار حدس).
ایمیل تازه روی حساب مهمان همین گوشی می نشیند (پیشرفتش می ماند)؛ ایمیلی که حساب دارد به همان حساب می برد.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import time

log = logging.getLogger("game_club.appauth")

SESSION_DAYS = 365       # نشستی که این مدت باز نشده بسته می شود (حساب می ماند)
TOUCH_EVERY = 3600
GUEST_NAME = "مهمان"
LOGIN_TTL = 600          # لینک ورود تلگرام و کد ایمیل
CODE_TRIES = 5
RESEND_AFTER = 60
SENDS_PER_HOUR = 5
_TOKEN = re.compile(r"^gcs_[A-Za-z0-9_-]{32,64}$")
_LOGIN = re.compile(r"^[A-Za-z0-9_-]{16,48}$")
_EMAIL = re.compile(r"^[a-z0-9._%+\-]{1,64}@[a-z0-9\-]+(\.[a-z0-9\-]+)*\.[a-z]{2,24}$")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class LoginError(Exception):
    def __init__(self, code: str, **extra) -> None:
        super().__init__(code)
        self.code, self.extra = code, extra


def is_guest(tg_id: int) -> bool:
    """حساب بدون تلگرام (مهمان یا ایمیلی)."""
    return int(tg_id) < 0


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def clean_device(text: str) -> str:
    return re.sub(r"[^\w .\-+()/]", "", text or "", flags=re.UNICODE).strip()[:40]


def norm_email(raw: str) -> str | None:
    e = (raw or "").strip().lower()
    return e if len(e) <= 254 and _EMAIL.match(e) else None


async def _new_account(db) -> dict:  # noqa: ANN001
    """بازیکن تازهٔ بدون تلگرام با یوزرنیم تصادفی."""
    for _ in range(8):
        # زیر ۲^۵۲ تا در جاوااسکریپت دقیق بماند
        gid = -1 - secrets.randbelow(2 ** 52 - 1)
        if not await db.one("SELECT 1 FROM players WHERE tg_id = ?", (gid,)):
            return await db.player(gid, GUEST_NAME, None)
    raise RuntimeError("guest id")


async def _session(db, tg_id: int, device: str, now: int) -> str:  # noqa: ANN001
    token = "gcs_" + secrets.token_urlsafe(32)
    await db.execute("INSERT INTO app_sessions(token_hash, tg_id, device, created_at, seen_at) VALUES(?,?,?,?,?)",
                     (_hash(token), tg_id, clean_device(device), now, now))
    return token


async def new_guest(db, device: str = "", *, now: float | None = None) -> dict:  # noqa: ANN001
    """حساب مهمان تازه با یوزرنیم تصادفی و توکن نشست: {'token', 'player'}."""
    now = int(now or time.time())
    player = await _new_account(db)
    return {"token": await _session(db, player["tg_id"], device, now), "player": player}


async def _session_row(db, token: str, now: int) -> dict | None:  # noqa: ANN001
    if not _TOKEN.match(token or ""):
        return None
    h = _hash(token)
    row = await db.one("SELECT tg_id, seen_at FROM app_sessions WHERE token_hash = ?", (h,))
    if not row or now - row["seen_at"] > SESSION_DAYS * 86400:
        if row:
            await db.execute("DELETE FROM app_sessions WHERE token_hash = ?", (h,))
        return None
    if now - row["seen_at"] > TOUCH_EVERY:
        await db.execute("UPDATE app_sessions SET seen_at = ? WHERE token_hash = ?", (now, h))
    return row


async def session_player(db, token: str, *, now: float | None = None) -> dict | None:  # noqa: ANN001
    """بازیکن صاحب توکن نشست؛ None اگر توکن نامعتبر یا منقضی است."""
    row = await _session_row(db, token, int(now or time.time()))
    return await db.get_player(row["tg_id"]) if row else None


async def logout(db, token: str) -> None:  # noqa: ANN001
    if _TOKEN.match(token or ""):
        await db.execute("DELETE FROM app_sessions WHERE token_hash = ?", (_hash(token),))


async def account(db, tg_id: int) -> dict:  # noqa: ANN001
    """نوع حساب برای صفحهٔ پروفایل: telegram، email (با آدرس) یا guest."""
    if tg_id > 0:
        return {"kind": "telegram"}
    row = await db.one("SELECT email FROM app_emails WHERE tg_id = ?", (tg_id,))
    return {"kind": "email", "email": row["email"]} if row else {"kind": "guest"}


async def _switch(db, tg_id: int, current: str, device: str, now: int) -> dict:  # noqa: ANN001
    """نشست تازه برای tg_id؛ نشست قبلی همین گوشی بسته می شود."""
    token = await _session(db, tg_id, device, now)
    await logout(db, current)
    return {"token": token, "account": await account(db, tg_id)}


# ---------- ورود با تلگرام (لینک ربات) ----------
async def tg_start(db, device: str = "", *, now: float | None = None) -> dict:  # noqa: ANN001
    """کد لینک ربات (start=login_<code>) و رمز poll که فقط برنامه نگه می دارد."""
    now = int(now or time.time())
    await db.execute("DELETE FROM app_tg_logins WHERE created_at < ?", (now - 86400,))
    code, poll = secrets.token_urlsafe(18), secrets.token_urlsafe(24)
    await db.execute("INSERT INTO app_tg_logins(code_hash, poll_hash, device, state, created_at) VALUES(?,?,?,?,?)",
                     (_hash(code), _hash(poll), clean_device(device), "wait", now))
    return {"code": code, "poll": poll, "ttl": LOGIN_TTL}


async def tg_pending(db, code: str, *, now: float | None = None) -> dict | None:  # noqa: ANN001
    """درخواست ورودی که هنوز منتظر تأیید در ربات است (برای پیام تأیید ربات)."""
    if not _LOGIN.match(code or ""):
        return None
    now = int(now or time.time())
    return await db.one("SELECT device, created_at FROM app_tg_logins WHERE code_hash = ? AND state = 'wait' AND created_at >= ?",
                        (_hash(code), now - LOGIN_TTL))


async def tg_decide(db, code: str, tg_id: int, ok: bool, *, now: float | None = None) -> bool:  # noqa: ANN001
    """«آره خودمم» یا «نه» در ربات؛ False اگر لینک منقضی یا قبلا جواب داده شده."""
    if not _LOGIN.match(code or "") or tg_id <= 0:
        return False
    now = int(now or time.time())
    n = await db.execute("UPDATE app_tg_logins SET state = ?, tg_id = ? WHERE code_hash = ? AND state = 'wait' AND created_at >= ?",
                         ("ok" if ok else "no", tg_id if ok else None, _hash(code), now - LOGIN_TTL))
    return n > 0


async def tg_check(db, poll: str, current: str = "", *, now: float | None = None) -> dict:  # noqa: ANN001
    """نتیجهٔ ورود برای برنامه: wait، no، expired یا ok (با توکن نشست تازه، فقط یک بار)."""
    if not _LOGIN.match(poll or ""):
        return {"state": "expired"}
    now = int(now or time.time())
    row = await db.one("SELECT * FROM app_tg_logins WHERE poll_hash = ?", (_hash(poll),))
    if not row or row["state"] == "used" or (row["state"] == "wait" and now - row["created_at"] > LOGIN_TTL):
        return {"state": "expired"}
    if row["state"] != "ok":
        return {"state": row["state"]}
    # دو پرسش هم زمان: فقط یکی نشست می گیرد
    if not await db.execute("UPDATE app_tg_logins SET state = 'used' WHERE poll_hash = ? AND state = 'ok'", (_hash(poll),)):
        return {"state": "expired"}
    return {"state": "ok", **await _switch(db, row["tg_id"], current, row["device"], now)}


# ---------- ورود با ایمیل (کد ۶ رقمی) ----------
def _code_hash(email: str, code: str) -> str:
    return _hash(f"{email}:{code}")


async def email_start(db, raw: str, *, send=None, now: float | None = None) -> dict:  # noqa: ANN001
    """کد تازه به ایمیل؛ LoginError: bad_email، email_off، email_wait، email_limit، send_fail."""
    from . import mailer

    email = norm_email(raw)
    if not email:
        raise LoginError("bad_email")
    if send is None:
        if not mailer.enabled():
            raise LoginError("email_off")
        send = mailer.send_code
    now = int(now or time.time())
    row = await db.one("SELECT * FROM app_codes WHERE email = ?", (email,))
    if row and now - row["sent_at"] < RESEND_AFTER:
        raise LoginError("email_wait", wait=RESEND_AFTER - (now - row["sent_at"]))
    fresh = not row or now - row["window_at"] >= 3600
    if not fresh and row["sends"] >= SENDS_PER_HOUR:
        raise LoginError("email_limit", wait=3600 - (now - row["window_at"]))
    code = f"{secrets.randbelow(10 ** 6):06d}"
    await db.execute(
        "INSERT INTO app_codes(email, code_hash, tries, sent_at, expires_at, sends, window_at) VALUES(?,?,0,?,?,?,?) "
        "ON CONFLICT(email) DO UPDATE SET code_hash = excluded.code_hash, tries = 0, sent_at = excluded.sent_at, "
        "expires_at = excluded.expires_at, sends = excluded.sends, window_at = excluded.window_at",
        (email, _code_hash(email, code), now, now + LOGIN_TTL, 1 if fresh else row["sends"] + 1, now if fresh else row["window_at"]))
    try:
        await send(email, code, LOGIN_TTL // 60)
    except Exception:  # noqa: BLE001
        log.exception("ایمیل کد ورود AsoTas نرفت")
        # کد نرسیده: دوباره فرستادن زودتر آزاد است
        await db.execute("UPDATE app_codes SET sent_at = 0 WHERE email = ?", (email,))
        raise LoginError("send_fail") from None
    return {"ok": True, "email": email, "ttl": LOGIN_TTL, "resend": RESEND_AFTER}


async def email_verify(db, raw: str, code: str, current: str = "", device: str = "", *,  # noqa: ANN001
                       now: float | None = None) -> dict:
    """کد درست: نشست حساب این ایمیل. ایمیل تازه روی حساب مهمان همین گوشی می نشیند، وگرنه حساب تازه.
    LoginError: bad_email، code_expired، code_tries، code_bad (left)."""
    email = norm_email(raw)
    if not email:
        raise LoginError("bad_email")
    now = int(now or time.time())
    code = re.sub(r"\D", "", (code or "").translate(_DIGITS))
    row = await db.one("SELECT * FROM app_codes WHERE email = ?", (email,))
    if not row or now > row["expires_at"]:
        raise LoginError("code_expired")
    if row["tries"] >= CODE_TRIES:
        raise LoginError("code_tries")
    if not hmac.compare_digest(row["code_hash"], _code_hash(email, code)):
        await db.execute("UPDATE app_codes SET tries = tries + 1 WHERE email = ?", (email,))
        left = CODE_TRIES - row["tries"] - 1
        raise LoginError("code_bad", left=left) if left > 0 else LoginError("code_tries")
    await db.execute("DELETE FROM app_codes WHERE email = ?", (email,))

    cur = await _session_row(db, current, now)
    owner = await db.one("SELECT tg_id FROM app_emails WHERE email = ?", (email,))
    if owner:
        tg = owner["tg_id"]
        if cur and cur["tg_id"] == tg:
            return {"token": current, "account": await account(db, tg)}
    else:
        pure_guest = cur and cur["tg_id"] < 0 and not await db.one("SELECT 1 FROM app_emails WHERE tg_id = ?", (cur["tg_id"],))
        tg = cur["tg_id"] if pure_guest else (await _new_account(db))["tg_id"]
        await db.execute("INSERT INTO app_emails(email, tg_id, created_at) VALUES(?,?,?)", (email, tg, now))
        if pure_guest:
            return {"token": current, "account": await account(db, tg)}
    return await _switch(db, tg, current, device, now)
