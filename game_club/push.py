"""نوتیفیکیشن گوشی برای برنامهٔ اندروید AsoTas (Firebase Cloud Messaging، HTTP v1).

کلید سرویس فایربیس (فایل JSON) از GAME_CLUB_FCM_KEY خوانده می شود؛ بی آن هیچ کاری نمی کند
و بازی و ربات مثل قبل کار می کنند. هر گوشی با POST /gc/api/push/token توکنش را می فرستد.
- نوبت و اعلان های بازی: به گوشی های همان بازیکن (کنار پیام ربات تلگرام)
- پاپ آپ پنل مدیریت با گزینهٔ «نوتیفیکیشن گوشی»: به تاپیک all (همهٔ گوشی ها)
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time

import aiohttp

from .config import gc

log = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_key: dict | None = None
_access: tuple[float, str] = (0.0, "")


def enabled() -> bool:
    return bool(_load())


def _load() -> dict | None:
    global _key
    if _key is None:
        try:
            with open(gc.fcm_key, encoding="utf-8") as fh:
                k = json.load(fh)
            _key = k if k.get("private_key") and k.get("client_email") and k.get("project_id") else {}
        except (OSError, ValueError, TypeError):
            _key = {}
        if not _key and gc.fcm_key:
            log.warning("کلید فایربیس AsoTas (GAME_CLUB_FCM_KEY) خوانده نشد")
    return _key or None


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


async def _token(session: aiohttp.ClientSession) -> str:
    """توکن دسترسی گوگل (یک ساعته) با JWT امضا شدهٔ کلید سرویس"""
    global _access
    if _access[1] and _access[0] > time.time() + 60:
        return _access[1]
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    k = _load()
    now = int(time.time())
    uri = k.get("token_uri") or "https://oauth2.googleapis.com/token"
    head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps({"iss": k["client_email"], "scope": SCOPE, "aud": uri, "iat": now, "exp": now + 3600}).encode())
    key = serialization.load_pem_private_key(k["private_key"].encode(), password=None)
    sig = _b64(key.sign(f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256()))
    async with session.post(uri, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                       "assertion": f"{head}.{body}.{sig}"}) as r:
        j = await r.json(content_type=None)
    tok = str(j.get("access_token") or "")
    if not tok:
        raise RuntimeError(f"fcm token: {j.get('error')}")
    _access = (now + int(j.get("expires_in") or 3600), tok)
    return tok


def _media(img: str) -> str:
    """عکس پاپ آپ: نشانی کامل https برای نمایش در نوتیفیکیشن"""
    if not img:
        return ""
    if img.startswith("https://"):
        return img
    return f"{gc.base_url}/{img}" if gc.base_url else ""


async def send(*, token: str = "", topic: str = "", title: str, body: str, img: str = "",
               channel: str = "turn", data: dict | None = None) -> str:
    """یک نوتیفیکیشن؛ خروجی ok، gone (توکن دیگر معتبر نیست) یا failed"""
    k = _load()
    if not k or not (token or topic):
        return "failed"
    note = {"title": title[:80], "body": body[:400]}
    pic = _media(img)
    if pic:
        note["image"] = pic
    msg = {"notification": note, "data": {kk: str(v) for kk, v in (data or {}).items()},
           "android": {"priority": "high", "notification": {"channel_id": channel, "sound": "default"}}}
    msg["token" if token else "topic"] = token or topic
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            tok = await _token(s)
            url = f"https://fcm.googleapis.com/v1/projects/{k['project_id']}/messages:send"
            async with s.post(url, json={"message": msg}, headers={"Authorization": f"Bearer {tok}"}) as r:
                if r.status == 200:
                    return "ok"
                text = await r.text()
                if r.status == 404 or "UNREGISTERED" in text:
                    return "gone"
                log.info("نوتیفیکیشن AsoTas نرفت (%s): %s", r.status, text[:200])
    except Exception as e:  # noqa: BLE001
        log.info("نوتیفیکیشن AsoTas نرفت: %s", e)
    return "failed"


async def to_player(db, tg: int, text: str, page: str = "") -> None:  # noqa: ANN001
    """اعلان بازی (نوبت، میز منتظر و ...) به همهٔ گوشی های یک بازیکن"""
    if not enabled():
        return
    for t in await db.push_tokens_of(tg):
        r = await send(token=t, title="AsoTas", body=text, channel="turn", data={"page": page})
        if r == "gone":
            await db.push_drop(t)


def to_all(title: str, text: str, img: str = "") -> None:
    """پاپ آپ پنل مدیریت برای همهٔ گوشی ها (در پس زمینه)"""
    if not enabled():
        return
    asyncio.get_running_loop().create_task(
        send(topic="all", title=title or "AsoTas", body=text or title, img=img, channel="news", data={"page": "popup"}))
