"""خرید سکه از مایکت (پرداخت درون برنامه ای، فقط داخل برنامهٔ اندروید).

جریان (static/app.js و پلاگین بومی MyketBilling در android-app):
  ۱. برنامه برای بسته ای سفارش می سازد (POST iap/order)؛ شناسهٔ سفارش developerPayload خرید مایکت می شود
     و نشان می دهد سکهٔ این خرید مال کدام حساب است؛
  ۲. مایکت پرداخت را می گیرد و دادهٔ خرید (JSON) و امضای آن را به برنامه می دهد؛
  ۳. برنامه همان را می فرستد (POST iap/verify). سرور امضا را با کلید عمومی مایکت می سنجد، اگر توکن دسترسی
     هست خرید را از API خود مایکت هم می پرسد و فقط بعد سکه می دهد؛ هر توکن خرید فقط یک بار؛
  ۴. بعد از جواب سرور برنامه خرید را consume می کند تا همان بسته دوباره خریدنی شود. اگر وسط کار قطع شد
     (اینترنت، بسته شدن برنامه)، خرید consume نشده می ماند و دفعهٔ بعد برنامه دوباره همین را می فرستد.

امضا: RSA با SHA1 (PKCS#1 v1.5)، همان که کتابخانهٔ مایکت در گوشی هم می سنجد. بدون کتابخانهٔ بیرونی.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time

from .config import gc
from .db import GCDatabase
from .service import GCError

log = logging.getLogger("gameclub.iap")

MYKET_API = "https://developer.myket.ir"
_SHA1_INFO = bytes.fromhex("3021300906052b0e03021a05000414")   # DigestInfo برای SHA1


class Later(Exception):
    """مایکت الان جواب نداد (شبکه یا خطای خودش)؛ خرید سر جایش می ماند و بعدا دوباره سنجیده می شود."""


def sku_of(coins: int) -> str:
    return f"coins_{coins}"


def packs() -> list[dict]:
    return [{"sku": sku_of(n), "coins": n, "toman": n * gc.point_toman} for n in gc.coin_packs]


def coins_of(sku: str) -> int:
    return next((n for n in gc.coin_packs if sku_of(n) == sku), 0)


def enabled() -> bool:
    return gc.iap_enabled and bool(gc.myket_key)


def view(in_app: bool) -> dict:
    """تنظیمات خرید برای me. کلید عمومی (برای سنجش امضا در خود گوشی) فقط داخل برنامه؛ وقتی خرید از پنل
    خاموش است هم می آید تا خریدهای نیمه کارهٔ قبلی باز هم تأیید و consume شوند."""
    return {"on": enabled() and in_app, "key": gc.myket_key if in_app else "", "packs": packs()}


# ---------- امضای RSA ----------
def _der(buf: bytes, i: int) -> tuple[int, bytes, int]:
    tag, ln = buf[i], buf[i + 1]
    i += 2
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(buf[i:i + n], "big")
        i += n
    return tag, buf[i:i + ln], i + ln


def _rsa_key(b64: str) -> tuple[int, int]:
    """کلید عمومی مایکت (base64 از DER؛ SubjectPublicKeyInfo یا RSAPublicKey) ← (n, e)."""
    der = base64.b64decode("".join(b64.split()))
    tag, seq, _ = _der(der, 0)
    if tag != 0x30:
        raise ValueError("key")
    first, body, j = _der(seq, 0)
    if first == 0x30:                       # SubjectPublicKeyInfo: الگوریتم، بعد BIT STRING
        tag, bits, _ = _der(seq, j)
        if tag != 0x03:
            raise ValueError("key")
        tag, seq, _ = _der(bits[1:], 0)
        first, body, j = _der(seq, 0)
    if first != 0x02:
        raise ValueError("key")
    tag, e, _ = _der(seq, j)
    return int.from_bytes(body, "big"), int.from_bytes(e, "big")


def verify_signature(key_b64: str, data: str, sig_b64: str) -> bool:
    try:
        n, e = _rsa_key(key_b64)
        sig = base64.b64decode(sig_b64 or "", validate=False)
    except (ValueError, IndexError, TypeError):
        return False
    k = (n.bit_length() + 7) // 8
    pad = k - 3 - len(_SHA1_INFO) - 20
    if pad < 8 or len(sig) != k:
        return False
    s = int.from_bytes(sig, "big")
    if s >= n:
        return False
    em = pow(s, e, n).to_bytes(k, "big")
    want = b"\x00\x01" + b"\xff" * pad + b"\x00" + _SHA1_INFO + hashlib.sha1(data.encode()).digest()
    return hmac.compare_digest(em, want)


# ---------- API مایکت (فقط سرور به سرور) ----------
async def store_check(sku: str, token: str) -> dict | None:
    """وضعیت خرید از مایکت؛ None یعنی مایکت چنین خریدی نمی شناسد. Later یعنی الان معلوم نیست."""
    import httpx

    pkg, head = gc.app_package, {"X-Access-Token": gc.myket_token, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(base_url=MYKET_API, timeout=12) as http:
            r = await http.post(f"/api/partners/applications/{pkg}/purchases/products/{sku}/verify",
                                json={"tokenId": token}, headers=head)
            # مسیر تازه نبود: همان پرسش با مسیر قدیمی مایکت
            if r.status_code in (404, 405) and "messageCode" not in r.text:
                r = await http.get(f"/api/applications/{pkg}/purchases/products/{sku}/tokens/{token}", headers=head)
    except httpx.HTTPError as e:
        raise Later(str(e)) from e
    if r.status_code in (400, 404):
        log.warning("مایکت خرید را نشناخت: %s %s", r.status_code, r.text[:200])
        return None
    if r.status_code != 200:
        # ۴۰۱/۴۰۳ یعنی توکن دسترسی مشکل دارد؛ پول کاربر را رد نمی کنیم، بعدا دوباره
        log.error("پرسش خرید از مایکت نشد: %s %s", r.status_code, r.text[:200])
        raise Later(str(r.status_code))
    try:
        return r.json()
    except ValueError as e:
        raise Later("json") from e


# ---------- سفارش و تأیید ----------
async def order(db: GCDatabase, tg: int, sku: str) -> dict:
    if not enabled():
        raise GCError("iap_off")
    coins = coins_of(sku)
    if not coins:
        raise GCError("iap_sku")
    oid = "o" + secrets.token_urlsafe(15)
    await db.execute("INSERT INTO iap_orders(id, tg_id, sku, created_at) VALUES(?,?,?,?)", (oid, tg, sku, int(time.time())))
    return {"order": oid, "sku": sku, "coins": coins}


async def verify(db: GCDatabase, tg: int, data: str, signature: str) -> dict:
    """دادهٔ خرید مایکت ← سکه برای صاحب سفارش (یک بار). again یعنی قبلا داده شده بود (برنامه فقط consume می کند)."""
    if not gc.myket_key:
        raise GCError("iap_off")
    try:
        p = json.loads(data or "")
    except ValueError:
        raise GCError("iap_bad") from None
    if not isinstance(p, dict):
        raise GCError("iap_bad")
    sku = str(p.get("productId") or "")
    token = str(p.get("purchaseToken") or p.get("token") or "")
    payload = str(p.get("developerPayload") or "")
    coins = coins_of(sku)
    if not coins or not token or len(token) > 400 or p.get("packageName", gc.app_package) != gc.app_package \
            or str(p.get("purchaseState") or 0) != "0":
        raise GCError("iap_bad")
    if not verify_signature(gc.myket_key, data, signature):
        log.warning("امضای خرید مایکت درست نبود: کاربر %s، %s", tg, sku)
        raise GCError("iap_bad")
    done = await db.one("SELECT tg_id FROM iap_purchases WHERE token = ?", (token,))
    if done:
        return await _result(db, tg, int(done["tg_id"]), coins, again=True)
    if gc.myket_token:
        try:
            st = await store_check(sku, token)
        except Later:
            raise GCError("iap_later") from None
        if not st or str(st.get("purchaseState", 1)) != "0" or \
                (st.get("developerPayload") and str(st["developerPayload"]) != payload):
            log.warning("مایکت خرید را تأیید نکرد: کاربر %s، %s، %s", tg, sku, str(st)[:200])
            raise GCError("iap_bad")
    # سکه مال کسی است که سفارش را ساخته (اگر برنامه وسط کار حساب عوض کرده باشد هم)
    o = await db.one("SELECT tg_id, sku FROM iap_orders WHERE id = ?", (payload,)) if payload else None
    if o and o["sku"] != sku:
        raise GCError("iap_bad")
    owner = int(o["tg_id"]) if o else tg
    idem = "iap:" + hashlib.sha256(token.encode()).hexdigest()[:40]
    try:
        new = await db.iap_credit(token, payload, owner, sku, coins, str(p.get("orderId") or ""),
                                  f"خرید {coins} سکه از مایکت", idem)
    except LookupError:
        raise GCError("iap_bad") from None
    if new:
        log.info("خرید سکه از مایکت: کاربر %s، %s سکه (%s)", owner, coins, sku)
    return await _result(db, tg, owner, coins, again=not new)


async def _result(db: GCDatabase, tg: int, owner: int, coins: int, again: bool) -> dict:
    me = await db.get_player(tg) or {}
    return {"ok": True, "coins": coins, "again": again, "mine": owner == tg, "points": int(me.get("points") or 0)}
