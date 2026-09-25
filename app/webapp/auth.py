"""احراز هویت مینی اپ با initData تلگرام.

هیچ توکن و کوکی و سشنی نداریم. هر درخواست API رشته initData را با خودش
می آورد و ما همان جا امضایش را می سنجیم. این تنها راه درست است:
آیدی تلگرام را اگر از بدنه درخواست بخوانیم، هر کسی می تواند با curl
آیدی یک نفر دیگر را بفرستد و کیف پولش را ببیند.

روش (مستند رسمی تلگرام):
  secret = HMAC_SHA256(key="WebAppData", msg=BOT_TOKEN)
  check  = "\\n".join(sorted("key=value"))   # بدون hash و signature
  valid  = HMAC_SHA256(key=secret, msg=check).hexdigest() == hash

به علاوه auth_date را هم می سنجیم تا یک initData لو رفته تا ابد کار
نکند. پیش فرض ۶ ساعت؛ تلگرام خودش هنگام باز شدن دوباره مینی اپ یک
initData تازه می دهد، پس این سختگیری برای کاربر هزینه ای ندارد.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, unquote

from app.config import config

# حداکثر عمر مجاز initData (ثانیه). صفر یعنی بدون محدودیت - توصیه نمی شود.
MAX_AGE = int(os.getenv("WEBAPP_MAX_AGE", "21600") or 21600)


class AuthError(Exception):
    """initData نامعتبر یا منقضی."""


@dataclass(slots=True)
class WebAppUser:
    id: int
    first_name: str
    username: str
    language_code: str
    is_premium: bool
    start_param: str


def _parse_qsl(init_data: str) -> dict:
    """تجزیه استاندارد. توجه: parse_qsl علامت + را به فاصله تبدیل می کند."""
    return dict(parse_qsl(init_data, keep_blank_values=True))


def _parse_raw(init_data: str) -> dict:
    """تجزیه بدون قاعده فرم: + همان + می ماند.

    initData با encodeURIComponent ساخته می شود و آنجا + به %2B تبدیل
    می شود، پس در حالت عادی دو تجزیه یکی هستند. ولی بعضی کلاینت ها و
    واسط ها رشته را دوباره دست می زنند و یک + خام باقی می ماند؛ آن وقت
    parse_qsl آن را فاصله می کند و امضا می شکند. هر دو حالت امتحان
    می شود تا یک کاراکتر، کل ورود کاربر را خراب نکند.
    """
    out: dict[str, str] = {}
    for part in init_data.split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        out[unquote(key)] = unquote(value)
    return out


def _sign(fields: dict) -> str:
    """امضای مورد انتظار برای این مجموعه فیلد."""
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", config.bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, check.encode("utf-8"), hashlib.sha256).hexdigest()


def _candidates(init_data: str):
    """همه شکل های محتمل data-check-string.

    دو محور:
      * تجزیه: parse_qsl استاندارد یا خام (بدون + به فاصله)
      * فیلد signature: حذف شود یا بماند

    محور دوم اهمیت دارد. تلگرام از ۲۰۲۴ فیلد signature را هم می فرستد
    (برای اعتبارسنجی شخص ثالث با Ed25519). متن مستند می گوید در
    data-check-string نیاید، ولی پیاده سازی های واقعی - از جمله خود
    aiogram - فقط hash را برمی دارند و signature را نگه می دارند. اگر
    اشتباه انتخاب کنیم، امضا برای همه کاربران می شکند و از بیرون شبیه
    «توکن غلط» دیده می شود. پس هر دو امتحان می شود و اولی که خواند
    برنده است.

    خروجی: (نام حالت، فیلدها، امضای داده شده)
    """
    for pname, parser in (("qsl", _parse_qsl), ("raw", _parse_raw)):
        base = parser(init_data)
        given = base.get("hash", "")
        for sname in ("no-signature", "with-signature"):
            fields = {k: v for k, v in base.items() if k != "hash"}
            if sname == "no-signature":
                fields.pop("signature", None)
            yield f"{pname}/{sname}", fields, given


def verify(init_data: str) -> WebAppUser:
    """initData را می سنجد و کاربر تلگرام را برمی گرداند."""
    if not init_data:
        raise AuthError("initData خالی است")
    if not config.bot_token:
        raise AuthError("BOT_TOKEN تنظیم نشده")

    matched = None
    saw_hash = False
    for _name, fields, given in _candidates(init_data):
        if not given:
            continue
        saw_hash = True
        if hmac.compare_digest(_sign(fields), given):
            matched = fields
            break

    if not saw_hash:
        raise AuthError("امضا در initData نیست")
    if matched is None:
        raise AuthError("امضای initData معتبر نیست")
    fields = matched

    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError:
        auth_date = 0
    if auth_date <= 0:
        raise AuthError("auth_date نامعتبر است")
    if MAX_AGE and (time.time() - auth_date) > MAX_AGE:
        raise AuthError("نشست منقضی شده؛ مینی اپ را دوباره باز کن")

    try:
        raw_user = json.loads(fields.get("user") or "{}")
    except ValueError:
        raw_user = {}
    uid = raw_user.get("id")
    if not isinstance(uid, int) or uid <= 0:
        raise AuthError("کاربر در initData نیست")

    return WebAppUser(
        id=uid,
        first_name=(raw_user.get("first_name") or "")[:64],
        username=(raw_user.get("username") or "")[:64],
        language_code=(raw_user.get("language_code") or "")[:8],
        is_premium=bool(raw_user.get("is_premium")),
        start_param=(fields.get("start_param") or "")[:64],
    )


def describe(init_data: str) -> dict:
    """گزارش عیب یابی. هیچ داده حساسی برنمی گرداند.

    نه توکن، نه خود initData، نه امضای کامل. فقط اثر انگشت و طول ها -
    به اندازه ای که بشود فهمید کدام حلقه پاره است.
    """
    token = config.bot_token or ""
    bot_id = token.split(":", 1)[0] if ":" in token else ""
    out: dict = {
        "token_set": bool(token),
        "token_len": len(token),
        "token_has_space": token != token.strip(),
        "bot_id_from_token": bot_id,
        "token_fingerprint": hashlib.sha256(token.encode()).hexdigest()[:12],
        "init_data_len": len(init_data or ""),
        "max_age": MAX_AGE,
        "now": int(time.time()),
    }
    if not init_data:
        out["problem"] = "initData به سرور نرسید (هدر X-Init-Data خالی بود)"
        return out

    raw_fields = _parse_raw(init_data)
    out["fields_received"] = sorted(raw_fields)
    out["has_signature_field"] = "signature" in raw_fields

    attempts = []
    for name, fields, given in _candidates(init_data):
        expected = _sign(fields) if given else ""
        attempts.append({
            "parser": name,
            "fields": sorted(fields),
            "has_hash": bool(given),
            "given_hash_head": given[:8],
            "expected_hash_head": expected[:8],
            "match": bool(given) and hmac.compare_digest(expected, given),
            "auth_date": fields.get("auth_date", ""),
            "age_seconds": (
                int(time.time()) - int(fields["auth_date"])
                if fields.get("auth_date", "").isdigit() else None
            ),
        })
    out["attempts"] = attempts

    # آیدی کاربر و آیدی ربات از خود initData، برای مقایسه با توکن
    try:
        user = json.loads(_parse_raw(init_data).get("user") or "{}")
        out["user_id"] = user.get("id")
    except ValueError:
        out["user_id"] = None

    winner = next((a for a in attempts if a["match"]), None)
    if winner:
        out["matched_variant"] = winner["parser"]
        out["problem"] = (
            f"امضا با حالت {winner['parser']} درست است؛ اگر باز خطا "
            "می گیری، مشکل از عمر نشست است"
        )
    elif not any(a["has_hash"] for a in attempts):
        out["problem"] = "فیلد hash در initData نبود - رشته ناقص به سرور رسیده"
    else:
        out["problem"] = (
            "هیچ حالتی نخواند. اگر token_matches_bot درست است، یعنی "
            "رشته ای که امضا می شود با آنچه تلگرام امضا کرده فرق دارد - "
            "fields_received را ببین."
        )
    return out
