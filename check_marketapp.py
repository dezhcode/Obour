"""تست زنده MarketApp API (پرمیوم، استارز، گیفت و اجاره) با داده واقعی.

  python check_marketapp.py --user USERNAME                همه تست ها
  python check_marketapp.py --user USERNAME --channel CH   + گیواوی برای کانال CH
  python check_marketapp.py --user USERNAME --ads LINK     + شارژ حساب تبلیغات (لینک fragment.com/ads/pay?account=...)
  python check_marketapp.py --user USERNAME --json         پاسخ خام همه درخواست ها به صورت JSON

توکن از MARKETAPP_TOKEN (محیط یا .env) خوانده می شود و هیچ جا چاپ نمی شود. مرجع: MARKETAPP_FA.md

هیچ تراکنشی امضا یا ارسال نمی شود و هیچ پولی جابجا نمی شود: endpointهای خرید فقط تراکنش آماده
برمی گردانند و این اسکریپت فقط آن را باز می کند (مقصد، مبلغ، کامنت) و با قیمت اعلام شده مقایسه می کند.
endpointهایی که روی NFT خودمان کار می کنند (فروش، اجاره دادن، کد ورود) تست نمی شوند.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
import uuid

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import httpx

from app.ton import Cell, TonError, read_comment

BASE = os.environ.get("MARKETAPP_BASE", "https://api.marketapp.org").rstrip("/")
NANO = 1_000_000_000

results: list[dict] = []


def _token() -> str:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:  # noqa: BLE001
        pass
    tok = (os.environ.get("MARKETAPP_TOKEN") or "").strip()
    if not tok and sys.stdin.isatty():
        tok = getpass.getpass("MarketApp token: ").strip()
    if not tok:
        sys.exit("MARKETAPP_TOKEN در .env یا محیط نیست.")
    return tok


class Api:
    def __init__(self, token: str) -> None:
        self.http = httpx.Client(
            base_url=BASE,
            timeout=30,
            headers={
                "Authorization": token,
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) obour-check/1.0",
            },
        )

    def call(self, name: str, method: str, path: str, *, body: dict | None = None,
             params: dict | None = None) -> dict:
        t0 = time.monotonic()
        r: dict = {"name": name, "method": method, "path": path, "body": body, "params": params}
        try:
            resp = self.http.request(method, path, json=body, params=params)
            r["status"] = resp.status_code
            try:
                r["data"] = resp.json()
            except ValueError:
                r["data"] = None
                r["text"] = resp.text[:300]
        except httpx.HTTPError as exc:
            r["status"] = 0
            r["text"] = f"{type(exc).__name__}: {exc}"
        r["ms"] = int((time.monotonic() - t0) * 1000)
        r["ok"] = 200 <= r["status"] < 300
        results.append(r)
        time.sleep(0.3)
        return r


# ═══════════════════ نمایش ═══════════════════


def _short(v, n: int = 160) -> str:  # noqa: ANN001
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + "…"


def show(r: dict, note: str = "") -> None:
    mark = "OK " if r["ok"] else "ERR"
    print(f"\n[{mark}] {r['name']}\n      {r['method']} {r['path']} -> HTTP {r['status']} · {r['ms']}ms")
    if r.get("body") is not None:
        print(f"      body: {_short(r['body'])}")
    if r.get("params"):
        print(f"      params: {_short({k: v for k, v in r['params'].items() if v is not None})}")
    if not r["ok"]:
        print(f"      error: {_short(r.get('data') if r.get('data') is not None else r.get('text', ''), 400)}")
    elif note:
        print(f"      {note}")


def _b64(s: str) -> str:
    return s.strip().replace("-", "+").replace("_", "/")


def _payload_text(b64: str | None) -> str:
    if not b64:
        return "-"
    try:
        cell = Cell.from_boc(_b64(b64))
    except TonError as exc:
        return f"(BOC خوانده نشد: {exc})"
    text = read_comment(cell)
    if text is not None:
        return f"comment={text!r}"
    bits = cell.bits
    op = f"0x{int(bits[:32], 2):08x}" if len(bits) >= 32 else "-"
    return f"op={op} bits={len(bits)} refs={len(cell.refs)}"


def show_tx(r: dict, quote: float | None = None) -> None:
    """تراکنش برگشتی را باز می کند؛ امضا یا ارسال نمی شود."""
    show(r)
    if not r["ok"] or not isinstance(r.get("data"), dict):
        return
    tx = r["data"].get("transaction") or r["data"]
    msgs = tx.get("messages") or []
    total = 0
    for i, m in enumerate(msgs):
        amt = int(m.get("amount") or 0)
        total += amt
        print(f"      msg{i}: to={m.get('address')} amount={amt / NANO:.9f} "
              f"{_payload_text(m.get('payload'))} stateInit={'yes' if m.get('stateInit') else 'no'}")
    left = int(tx.get("validUntil") or 0) - int(time.time())
    line = f"      total={total / NANO:.9f} · validUntil in {left}s · messages={len(msgs)}"
    if quote:
        line += f" · quote={quote:g} · diff={(total / NANO - quote) / quote * 100:+.2f}%"
    print(line)
    extra = {k: v for k, v in r["data"].items() if k != "transaction"}
    if extra:
        print(f"      extra fields: {_short(extra)}")


def _price(p: dict | None) -> float | None:
    if not isinstance(p, dict):
        return None
    for k in ("gram", "ton"):
        if p.get(k):
            return float(p[k])
    return None


def _ton_amount(v) -> float:  # noqa: ANN001
    """قیمت بازار ممکن است nano (رشته عدد صحیح بزرگ) یا TON باشد."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return f / NANO if f >= 1_000_000 and float(f).is_integer() else f


# ═══════════════════ تست ها ═══════════════════


def test_fragment(api: Api, user: str, channel: str | None, ads: str | None) -> None:
    print("\n══════════ Fragment: قیمت ها ══════════")
    r = api.call("قیمت پرمیوم", "POST", "/v1/fragment/premium/price/")
    prem = r.get("data") if r["ok"] and isinstance(r.get("data"), dict) else {}
    show(r, "  ".join(f"{k}={_short(v)}" for k, v in prem.items()))

    stars_q: dict[int, float | None] = {}
    for q in (50, 1000):
        r = api.call(f"قیمت {q} استارز", "POST", "/v1/fragment/stars/price/", body={"quantity": q})
        stars_q[q] = _price(r.get("data")) if r["ok"] else None
        show(r, f"{_short(r.get('data'))}" + (f" · per star={stars_q[q] / q:.6f}" if stars_q[q] else ""))

    r = api.call("قیمت گیواوی استارز", "POST", "/v1/fragment/stars-giveaway/price/")
    ga_items = (r.get("data") or {}).get("items") if r["ok"] and isinstance(r.get("data"), dict) else None
    show(r, f"{len(ga_items or [])} packages, first: {_short((ga_items or [None])[0])}")

    r = api.call("قیمت گیواوی پرمیوم (۱ برنده)", "POST", "/v1/fragment/premium-giveaway/price/",
                 body={"quantity": 1})
    pga = r.get("data") if r["ok"] and isinstance(r.get("data"), dict) else {}
    show(r, _short(pga, 300))

    print(f"\n══════════ Fragment: گیرنده (@{user}) ══════════")
    for name, path in (("premium", "/v1/fragment/premium/recipient/"),
                       ("stars", "/v1/fragment/stars/recipient/"),
                       ("telegram-topup", "/v1/fragment/telegram-topup/recipient/")):
        r = api.call(f"گیرنده {name}", "POST", path, body={"username": user})
        show(r, _short(r.get("data"), 200))
    bogus = "zz" + uuid.uuid4().hex[:14]
    r = api.call("گیرنده ناموجود (قالب خطا)", "POST", "/v1/fragment/premium/recipient/", body={"username": bogus})
    show(r, _short(r.get("data"), 200))

    print("\n══════════ Fragment: خرید (فقط ساخت تراکنش؛ امضا نمی شود) ══════════")
    r = api.call("خرید پرمیوم ۳ ماه", "POST", "/v1/fragment/premium/buy/",
                 body={"username": user, "months": 3, "currency": "GRAM"})
    show_tx(r, _price(prem.get("months3")))
    for cur in ("GRAM", "TON", "USDT"):
        r = api.call(f"خرید ۵۰ استارز currency={cur}", "POST", "/v1/fragment/stars/buy/",
                     body={"username": user, "quantity": 50, "currency": cur})
        show_tx(r, stars_q.get(50) if cur != "USDT" else None)
    r = api.call("شارژ حساب تلگرام ۱", "POST", "/v1/fragment/telegram-topup/pay/",
                 body={"username": user, "amount": 1})
    show_tx(r, 1.0)

    print("\n══════════ Fragment: قالب خطاها ══════════")
    r = api.call("پرمیوم ۵ ماه (نامعتبر)", "POST", "/v1/fragment/premium/buy/",
                 body={"username": user, "months": 5, "currency": "GRAM"})
    show(r, _short(r.get("data"), 300))
    r = api.call("۱۰ استارز (کمتر از حداقل)", "POST", "/v1/fragment/stars/buy/",
                 body={"username": user, "quantity": 10, "currency": "GRAM"})
    show(r, _short(r.get("data"), 300))
    bad = httpx.Client(base_url=BASE, timeout=30, headers={"Authorization": "invalid-token"})
    t0 = time.monotonic()
    try:
        resp = bad.post("/v1/fragment/premium/price/")
        rr = {"name": "توکن نامعتبر (قالب خطا)", "method": "POST", "path": "/v1/fragment/premium/price/",
              "status": resp.status_code, "ok": resp.is_success, "body": None, "params": None,
              "data": None, "text": resp.text[:300]}
    except httpx.HTTPError as exc:
        rr = {"name": "توکن نامعتبر (قالب خطا)", "method": "POST", "path": "/v1/fragment/premium/price/",
              "status": 0, "ok": False, "body": None, "params": None, "text": str(exc)}
    rr["ms"] = int((time.monotonic() - t0) * 1000)
    results.append(rr)
    show(rr, rr.get("text", ""))

    if channel:
        print(f"\n══════════ Fragment: گیواوی (@{channel}) ══════════")
        for name, path in (("stars-giveaway", "/v1/fragment/stars-giveaway/recipient/"),
                           ("premium-giveaway", "/v1/fragment/premium-giveaway/recipient/")):
            r = api.call(f"گیرنده {name}", "POST", path, body={"username": channel})
            show(r, _short(r.get("data"), 200))
        if ga_items:
            pkg = ga_items[0]
            r = api.call(f"خرید گیواوی {pkg.get('stars')} استارز، ۱ برنده", "POST",
                         "/v1/fragment/stars-giveaway/buy/",
                         body={"username": channel, "quantity": 1, "stars": pkg.get("stars")})
            show_tx(r, _price(pkg))
        r = api.call("خرید گیواوی پرمیوم ۳ ماه، ۱ برنده", "POST", "/v1/fragment/premium-giveaway/buy/",
                     body={"username": channel, "months": 3, "quantity": 1, "currency": "GRAM"})
        show_tx(r, _price(pga.get("months3")))

    if ads:
        print("\n══════════ Fragment: شارژ حساب تبلیغات ══════════")
        r = api.call("شارژ Ads ۱", "POST", "/v1/fragment/ads-topup/pay/",
                     body={"fragment_link": ads, "amount": 1})
        show_tx(r, 1.0)


def test_market(api: Api) -> None:
    print("\n══════════ بازار: کالکشن ها و گیفت ها ══════════")
    r = api.call("همه کالکشن ها", "GET", "/v1/collections/")
    show(r, f"{len(r['data'])} collections" if r["ok"] and isinstance(r.get("data"), list) else "")

    r = api.call("کالکشن های گیفت", "GET", "/v1/collections/gifts/")
    cols = r["data"] if r["ok"] and isinstance(r.get("data"), list) else []
    show(r, f"{len(cols)} gift collections, first: {_short(cols[0] if cols else None, 300)}")
    cols = sorted(cols, key=lambda c: -int(((c.get("extra_data") or {}).get("on_sale_all")) or 0))
    col = cols[0]["address"] if cols else None
    if not col:
        return
    print(f"      → کالکشن انتخابی: {cols[0].get('name')} ({col})")

    r = api.call("ویژگی های کالکشن", "GET", f"/v1/collections/{col}/attributes/")
    attrs = (r.get("data") or {}).get("attributes") if r["ok"] and isinstance(r.get("data"), dict) else []
    show(r, "  ".join(f"{a.get('trait_type')}={len(a.get('values') or [])}" for a in attrs or []))

    r = api.call("گیفت های در فروش (ارزان ترین)", "GET", "/v1/gifts/onsale/",
                 params={"collection_address": col, "sort_by": "min_bid_asc"})
    items = (r.get("data") or {}).get("items") if r["ok"] and isinstance(r.get("data"), dict) else []
    show(r, f"{len(items or [])} items, cursor={_short((r.get('data') or {}).get('cursor'))}, "
            f"first: {_short((items or [None])[0], 400)}")

    r = api.call("تاریخچه فروش گیفت", "GET", "/v1/gifts/history/", params={"limit": 5, "order_by": "new_to_old"})
    hist = (r.get("data") or {}).get("items") if r["ok"] and isinstance(r.get("data"), dict) else []
    show(r, f"{len(hist or [])} events, first: {_short((hist or [None])[0], 400)}")

    r = api.call("NFTهای کالکشن (onsale)", "GET", f"/v1/nfts/collections/{col}/",
                 params={"filter_by": "onsale", "limit": 5})
    show(r, f"{len((r.get('data') or {}).get('items') or []) if r['ok'] else 0} items")

    if not items:
        return
    it = items[0]
    nft = it.get("address")
    r = api.call("اطلاعات یک NFT", "GET", f"/v1/nfts/{nft}/")
    show(r, _short(r.get("data"), 500))
    owner = it.get("real_owner") or it.get("owner")
    if owner:
        r = api.call("NFTهای یک مالک", "GET", f"/v1/nfts/owner/{owner}/", params={"limit": 5})
        show(r, f"{len((r.get('data') or {}).get('items') or []) if r['ok'] else 0} items")

    price = _ton_amount(it.get("min_bid"))
    cur = it.get("currency") or "TON"
    r = api.call(f"خرید NFT ارزان ترین ({price:g} {cur})", "POST", "/v1/nfts/buy/",
                 body={"data": [{"nft_address": nft, "price": price, "currency": cur}]})
    show_tx(r, price)


def test_rent(api: Api) -> None:
    print("\n══════════ بازار: اجاره ══════════")
    for cat in ("gifts", "usernames", "numbers"):
        r = api.call(f"قابل اجاره: {cat}", "GET", f"/v1/rent/{cat}/", params={"sort_by": "recently_touch"})
        items = (r.get("data") or {}).get("items") if r["ok"] and isinstance(r.get("data"), dict) else []
        show(r, f"{len(items or [])} items, first: {_short((items or [None])[0], 300)}")
        r = api.call(f"تاریخچه اجاره: {cat}", "GET", f"/v1/rent/{cat}/history/",
                     params={"limit": 5, "order_by": "new_to_old"})
        hist = (r.get("data") or {}).get("items") if r["ok"] and isinstance(r.get("data"), dict) else []
        show(r, f"{len(hist or [])} events")
    r = api.call("اجاره های من", "GET", "/v1/rent/my-rented/")
    show(r, _short(r.get("data"), 200))


def main() -> None:
    ap = argparse.ArgumentParser(description="MarketApp live check (never signs or sends a transaction)")
    ap.add_argument("--user", required=True, help="یوزرنیم گیرنده تست، بدون @")
    ap.add_argument("--channel", help="کانال برای تست گیواوی، بدون @")
    ap.add_argument("--ads", help="لینک fragment.com/ads/pay?account=... برای تست شارژ تبلیغات")
    ap.add_argument("--json", action="store_true", help="پاسخ خام همه درخواست ها")
    args = ap.parse_args()

    token = _token()
    api = Api(token)
    print(f"MarketApp: {BASE}")
    try:
        test_fragment(api, args.user.lstrip("@"), (args.channel or "").lstrip("@") or None, args.ads)
        test_market(api)
        test_rent(api)
    finally:
        api.http.close()

    ok = sum(1 for r in results if r["ok"])
    print(f"\n══════════ خلاصه: {ok}/{len(results)} درخواست موفق ══════════")
    for r in results:
        print(f"  {'OK ' if r['ok'] else 'ERR'} {r['status']:>3} {r['method']:<4} {r['path']:<48} {r['name']}")
    if args.json:
        out = json.dumps(results, ensure_ascii=False, indent=2, default=str)
        print("\n" + out.replace(token, "***"))


if __name__ == "__main__":
    main()
