"""نرخ بازار آزاد از tgju.org: دلار، تتر و تون کوین به تومان.

tgju یک فایل JSON عمومی دارد که صفحه های خودش با آن به روز می شوند:

    https://call{1..5}.tgju.org/ajax.json
    {"current": {"price_dollar_rl": {"p": "1,064,500", "h": ..., "l": ..., "t": "14:25:11", "ts": ...}, ...}}

قیمت ها ریالی اند (p)؛ این جا به تومان تبدیل می شوند. کلید دلار ثابت است
(price_dollar_rl). کلید تتر و تون در طول زمان عوض شده، پس به جای یک نام
ثابت، بین کلیدهای موجود دنبالشان می گردیم (tether / toncoin / open-network)
و اگر قیمت دلاری بود، در نرخ تتر ضرب می شود. ادمین می تواند کلید دقیق را
با تنظیم های tgju_key_usd / tgju_key_usdt / tgju_key_ton هم تعیین کند.

خروجی پنج دقیقه کش می شود و آخرین قیمت سالم در دیتابیس هم می ماند تا اگر
tgju موقتا در دسترس نبود (یا پروسه زیر Passenger از نو بالا آمد) نرخ ها
صفر نشوند. قیمتی که بیش از MAX_AGE قدیمی باشد دیگر استفاده نمی شود.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.db import Database

log = logging.getLogger("obour.market")

URLS = tuple(f"https://call{i}.tgju.org/ajax.json" for i in (1, 2, 3, 4, 5))
CACHE_TTL = 300            # ثانیه
MAX_AGE = 6 * 3600         # بعد از این، آخرین قیمت ذخیره شده کهنه حساب می شود
SETTING_AUTO = "market_auto"
SETTING_LAST = "market_last"

USD_KEYS = ("price_dollar_rl", "price_dollar")
USDT_PAT = re.compile(r"tether|usdt", re.I)
TON_PAT = re.compile(r"toncoin|open[-_]?network|(^|[-_])ton([-_]|$)", re.I)

_cache: dict[str, Any] = {"at": 0.0, "data": None}


# ═══════════════════ خواندن و پارس ═══════════════════


def _num(v: Any) -> float:
    """«1,064,500» یا «۱٬۰۶۴٬۵۰۰» یا عدد -> float. نامعتبر -> 0."""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").strip()
    s = s.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    s = re.sub(r"[^\d.]", "", s.replace("٫", "."))
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def _is_rial(key: str) -> bool:
    return key.endswith(("_rl", "-irr", "_irr", "-rl", "-ir"))


def current(doc: dict) -> dict[str, dict]:
    """بخش current فایل ajax.json؛ هر قالب دیگری خالی برمی گردد."""
    cur = doc.get("current") if isinstance(doc, dict) else None
    return cur if isinstance(cur, dict) else {}


def _price(item: Any) -> float:
    if isinstance(item, dict):
        return _num(item.get("p", item.get("price")))
    return _num(item)


def _pick(cur: dict, pat: re.Pattern, prefer_rial: bool = True) -> tuple[str, float] | None:
    """بهترین کلید منطبق: اول ریالی، بعد کوتاه ترین نام (کمتر احتمال جفت ارز عجیب)."""
    found = [(k, _price(v)) for k, v in cur.items() if pat.search(k) and _price(v) > 0]
    if not found:
        return None
    found.sort(key=lambda kv: (not _is_rial(kv[0]) if prefer_rial else 0, len(kv[0])))
    return found[0]


def parse(doc: dict, keys: dict[str, str] | None = None) -> dict:
    """قیمت های تومانی از ajax.json. کلیدی که پیدا نشود صفر می ماند.

    خروجی: {"usd", "usdt", "ton" (تومان)، "keys": {...}، "time": ساعت tgju}.
    """
    keys = keys or {}
    cur = current(doc)
    out: dict[str, Any] = {"usd": 0, "usdt": 0, "ton": 0, "keys": {}, "time": ""}

    def toman(key: str, raw: float) -> float:
        return raw / 10 if _is_rial(key) else raw

    # دلار
    for k in ([keys["usd"]] if keys.get("usd") else []) + list(USD_KEYS):
        if k in cur and _price(cur[k]) > 0:
            out["usd"] = int(round(toman(k, _price(cur[k]))))
            out["keys"]["usd"] = k
            item = cur[k]
            if isinstance(item, dict):
                out["time"] = str(item.get("t") or item.get("ts") or "")
            break
    if not 5_000 <= out["usd"] <= 20_000_000:
        out["usd"] = 0                              # عدد بی معنی پایه تتر و تون نشود

    # تتر: هر کلیدی که به تتر می خورد بررسی می شود و واحدش از روی عدد
    # حدس زده می شود (ریال، تومان یا دلار). قیمت بازار ایران (ریالی یا
    # تومانی) بر قیمت دلاری × نرخ دلار ترجیح دارد؛ نزدیک ترین به نرخ دلار
    # برنده است. قیمت دلاری تتر حدود ۱ است و فقط وقتی کلید ایرانی نیست
    # استفاده می شود.
    k_t = keys.get("usdt")
    cands = [(k_t, _price(cur[k_t]))] if k_t and k_t in cur else \
        [(k, _price(v)) for k, v in cur.items() if USDT_PAT.search(k) and _price(v) > 0]
    best: tuple[int, float, int, str] | None = None     # (اولویت، فاصله، تومان، کلید)
    for k, raw in cands:
        options: list[tuple[int, float]] = []          # (اولویت، تومان)
        if _is_rial(k):
            options.append((0, raw / 10))
        elif raw >= 1000:
            options += [(0, raw / 10), (0, raw)]        # ریال یا تومان؛ نزدیک تر به دلار
        elif raw < 100 and out["usd"]:
            options.append((1, raw * out["usd"]))       # دلاری × نرخ دلار
        for prio, tm in options:
            dist = abs(tm / out["usd"] - 1) if out["usd"] else (0 if _is_rial(k) else 1)
            cand = (prio, dist, int(round(tm)), k)
            if best is None or cand[:2] < best[:2]:
                best = cand
    if best and (not out["usd"] or best[1] <= 0.4):
        out["usdt"], out["keys"]["usdt"] = best[2], best[3]

    # تون: ریالی مستقیم؛ دلاری × نرخ تتر (یا دلار اگر تتر نبود)
    k_n = keys.get("ton")
    hit = (k_n, _price(cur[k_n])) if k_n and k_n in cur else _pick(cur, TON_PAT)
    if hit:
        if _is_rial(hit[0]):
            out["ton"] = int(round(hit[1] / 10))
        elif hit[1] < 10_000:
            base = out["usdt"] or out["usd"]
            out["ton"] = int(round(hit[1] * base)) if base else 0
        if out["ton"]:
            out["keys"]["ton"] = hit[0]
    return sane(out)


def sane(q: dict) -> dict:
    """عددهای بی معنی (خطای پارس یا تغییر واحد سایت) کنار گذاشته می شوند."""
    if not 5_000 <= q.get("usd", 0) <= 20_000_000:
        q["usd"] = 0
    if not 5_000 <= q.get("usdt", 0) <= 20_000_000:
        q["usdt"] = 0
    if q["usd"] and q["usdt"] and not 0.7 <= q["usdt"] / q["usd"] <= 1.4:
        log.warning("نرخ تتر (%s) با دلار (%s) نمی خواند؛ کنار گذاشته شد", q["usdt"], q["usd"])
        q["usdt"] = 0
    if not 100 <= q.get("ton", 0) <= 200_000_000:
        q["ton"] = 0
    return q


async def _download() -> dict:
    """ajax.json از اولین سرور tgju که جواب درست بدهد."""
    import aiohttp

    from app.services.crypto import _proxy_kw

    last_err: Exception | None = None
    deadline = time.monotonic() + 15        # جمعا، تا صفحه ها معطل نمانند
    timeout = aiohttp.ClientTimeout(total=6)
    headers = {"User-Agent": "Mozilla/5.0 (ObourBot rates)", "Accept": "application/json",
               "Referer": "https://www.tgju.org/"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as s:
        for url in URLS:
            if time.monotonic() > deadline:
                break
            try:
                async with s.get(url, **_proxy_kw()) as r:
                    if r.status != 200:
                        raise RuntimeError(f"HTTP {r.status}")
                    doc = json.loads(await r.text())
                if current(doc):
                    return doc
                raise RuntimeError("current خالی است")
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                log.info("tgju %s: %s", url, exc)
    raise RuntimeError(f"tgju در دسترس نیست: {last_err}")


# ═══════════════════ کش و دیتابیس ═══════════════════


async def _keys(db: "Database") -> dict[str, str]:
    return {k: (await db.get_setting(f"tgju_key_{k}", "") or "").strip() for k in ("usd", "usdt", "ton")}


async def auto_on(db: "Database") -> bool:
    return (await db.get_setting(SETTING_AUTO, "1") or "1") != "0"


async def set_auto(db: "Database", on: bool) -> None:
    await db.set_setting(SETTING_AUTO, "1" if on else "0")


async def _stored(db: "Database") -> dict | None:
    try:
        q = json.loads(await db.get_setting(SETTING_LAST, "") or "null")
    except ValueError:
        return None
    return q if isinstance(q, dict) else None


async def quote(db: "Database", force: bool = False) -> dict:
    """{"usd", "usdt", "ton", "at" (یونیکس)، "time", "keys", "ok", "stale", "error"}.

    اول کش حافظه، بعد tgju، و اگر tgju جواب نداد آخرین قیمت ذخیره شده.
    """
    now = time.time()
    if not force and _cache["data"] and now - _cache["at"] < CACHE_TTL:
        return _cache["data"]
    try:
        q = parse(await _download(), await _keys(db))
        if not (q["usd"] or q["usdt"] or q["ton"]):
            raise RuntimeError("هیچ نرخی در پاسخ tgju پیدا نشد")
        q.update(at=int(now), ok=True, stale=False, error="")
        await db.set_setting(SETTING_LAST, json.dumps(q))
    except Exception as exc:  # noqa: BLE001
        log.warning("نرخ tgju خوانده نشد: %s", exc)
        old = await _stored(db) or {"usd": 0, "usdt": 0, "ton": 0, "keys": {}, "time": "", "at": 0}
        fresh = now - int(old.get("at") or 0) < MAX_AGE
        q = {**old, "ok": False, "stale": not fresh, "error": str(exc)[:200]}
        if not fresh:
            q.update(usd=0, usdt=0, ton=0)
    _cache.update(at=now, data=q)
    return q


async def last(db: "Database") -> dict:
    """آخرین قیمت بدون تماس با اینترنت (کش حافظه یا دیتابیس)؛ برای صفحه تنظیمات."""
    if _cache["data"]:
        return _cache["data"]
    old = await _stored(db)
    return {**old, "ok": True, "stale": time.time() - int(old.get("at") or 0) >= MAX_AGE} if old else {}


async def has_rate(db: "Database", asset: str) -> bool:
    """نرخ خودکار این ارز الان معلوم است؟ (بدون اینترنت)."""
    if not await auto_on(db):
        return False
    q = await last(db)
    return bool(q.get(asset)) and not q.get("stale")


async def fresh(db: "Database", max_age: int = 60) -> dict:
    """قیمت بازار تازه تر از max_age ثانیه؛ پیش از ساخت فاکتور و نمایش نرخ.

    اگر نرخ خودکار خاموش باشد کاری نمی کند. خطای tgju هم مانع نمی شود:
    همان آخرین قیمت سالم (تا MAX_AGE) برمی گردد.
    """
    if not await auto_on(db):
        return {}
    q = _cache["data"]
    if q and q.get("ok") and time.time() - float(_cache["at"]) < max_age:
        return q
    return await quote(db, force=True)


async def auto_rate(db: "Database", asset: str) -> int:
    """نرخ خودکار یک ارز (usd | usdt | ton) به تومان؛ ۰ یعنی خودکار خاموش یا نامعلوم."""
    if not await auto_on(db):
        return 0
    try:
        return int((await quote(db)).get(asset) or 0)
    except Exception:  # noqa: BLE001
        log.warning("نرخ خودکار %s خوانده نشد", asset, exc_info=True)
        return 0


def public(q: dict) -> dict:
    """خروجی عمومی برای /rates و پنل ادمین."""
    return {
        "source": "tgju.org",
        "usd": int(q.get("usd") or 0), "usdt": int(q.get("usdt") or 0), "ton": int(q.get("ton") or 0),
        "unit": "toman", "updated_at": int(q.get("at") or 0), "tgju_time": q.get("time") or "",
        "ok": bool(q.get("ok")), "stale": bool(q.get("stale")), "keys": q.get("keys") or {},
    }
