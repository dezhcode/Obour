"""خروجی خام canboso را در یک فایل JSON ذخیره می کند.

مستقل از ربات است و فقط به پایتون ۳ نیاز دارد (هیچ کتابخانه اضافه ای
لازم ندارد)؛ روی سرور یا کامپیوتر خودت اجرا کن:

    python canboso_dump.py

کلید به این ترتیب پیدا می شود:
  ۱. آرگومان اول:          python canboso_dump.py tgb_xxx
  ۲. متغیر محیطی CANBOSO_API_KEY
  ۳. خط CANBOSO_API_KEY=... در فایل .env کنار همین فایل

خروجی: canboso_dump.json کنار همین فایل. فقط می خواند (products و
balance)؛ هیچ خریدی انجام نمی دهد. کلید در فایل خروجی با *** جایگزین
می شود، پس فایل را می شود با خیال راحت فرستاد.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://canboso.com/api/v2/telegram-buyer"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "canboso_dump.json")


def find_key() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    if os.environ.get("CANBOSO_API_KEY"):
        return os.environ["CANBOSO_API_KEY"].strip()
    env = os.path.join(HERE, ".env")
    if os.path.isfile(env):
        with open(env, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("CANBOSO_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def get(path: str, key: str) -> dict:
    url = f"{BASE}{path}?{urllib.parse.urlencode({'key': key})}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "obour-dump/1.0"})
    started = time.monotonic()
    out: dict = {"request": f"GET {BASE}{path}?key=***"}
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status, headers, raw = r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as exc:
        status, headers, raw = exc.code, dict(exc.headers or {}), exc.read()
    except Exception as exc:  # noqa: BLE001
        out.update({"status": 0, "error": f"{type(exc).__name__}: {exc}"})
        return out
    out["status"] = status
    out["ms"] = int((time.monotonic() - started) * 1000)
    out["headers"] = {k: v for k, v in headers.items()
                      if k.lower() in ("content-type", "retry-after", "x-ratelimit-limit", "x-ratelimit-remaining", "date")}
    text = raw.decode("utf-8", errors="replace")
    try:
        out["body"] = json.loads(text)
    except ValueError:
        out["body_text"] = text[:5000]
    return out


def summary(products: dict, balance: dict) -> list[dict]:
    """خلاصه هر محصول، برای خواندن سریع (پاسخ کامل هم در فایل هست)."""
    body = products.get("body") if isinstance(products.get("body"), dict) else {}
    rows = []
    for p in body.get("products") or []:
        if not isinstance(p, dict):
            continue
        price = p.get("price") or {}
        rows.append({
            "productId": p.get("productId"),
            "name": p.get("name"),
            "productType": p.get("productType"),
            "price": price.get("amount"),
            "currency": price.get("currency"),
            "available": (p.get("availability") or {}).get("available"),
            "purchaseRequirements": p.get("purchaseRequirements"),
        })
    return rows


def main() -> None:
    key = find_key()
    if not key:
        print("کلید پیدا نشد. اجرا کن: python canboso_dump.py tgb_xxx")
        sys.exit(1)
    print("در حال خواندن محصولات…")
    products = get("/products", key)
    time.sleep(1)  # فاصله کوتاه؛ سقف درخواست را رعایت می کنیم
    print("در حال خواندن موجودی…")
    balance = get("/balance", key)
    doc = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "products": products,
        "balance": balance,
        "summary": summary(products, balance),
    }
    text = json.dumps(doc, ensure_ascii=False, indent=2).replace(key, "***")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    n = len(doc["summary"])
    print(f"/products -> HTTP {products.get('status')} · {n} محصول")
    print(f"/balance  -> HTTP {balance.get('status')}")
    print(f"ذخیره شد: {OUT}")


if __name__ == "__main__":
    main()
