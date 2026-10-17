"""تست زنده MarketApp API (پرمیوم، استارز، گیفت و اجاره) با داده واقعی. مرجع: MARKETAPP_FA.md

سه راه اجرا، هر سه همین run():
  ربات:  تنظیمات ← 💎 خدمات تلگرام ← 🧪 تست کامل API   (فایل گزارش در همان چت؛ app/services/marketapp.py)
  وب:    GET /marketapp-check?key=ADMIN_KEY[&user=..&channel=..&ads=..]   (passenger_wsgi.py)
  ترمینال: python check_marketapp.py --user USERNAME [--channel CH] [--ads LINK] [--json]

هیچ تراکنشی امضا یا ارسال نمی شود و هیچ پولی جابجا نمی شود: endpointهای خرید فقط تراکنش آماده
برمی گردانند و این جا فقط باز می شود (مقصد، مبلغ، کامنت) و با قیمت اعلام شده مقایسه می شود.
endpointهایی که روی NFT خودمان کار می کنند (فروش، اجاره دادن، کد ورود) تست نمی شوند.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Callable

import httpx

from app.config import config
from app.ton import Cell, TonError, read_comment

BASE = config.marketapp_base_url or "https://api.marketapp.org"
NANO = 1_000_000_000


def _short(v, n: int = 160) -> str:  # noqa: ANN001
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + "…"


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


def _items(r: dict) -> list:
    d = r.get("data")
    return (d.get("items") or []) if r["ok"] and isinstance(d, dict) else []


class Check:
    def __init__(self, token: str, out: Callable[[str], None] = print, budget: float | None = None) -> None:
        proxy = config.marketapp_proxy
        self.http = httpx.Client(
            base_url=BASE,
            timeout=20,
            **({"proxy": proxy} if proxy.startswith(("http", "socks")) else {}),
            headers={
                "Authorization": token,
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) obour-check/1.0",
            },
        )
        self.out = out
        self.results: list[dict] = []
        self.deadline = time.monotonic() + budget if budget else None

    def close(self) -> None:
        self.http.close()

    def call(self, name: str, method: str, path: str, *, body: dict | None = None,
             params: dict | None = None, headers: dict | None = None) -> dict:
        r: dict = {"name": name, "method": method, "path": path, "body": body, "params": params}
        if self.deadline and time.monotonic() > self.deadline:
            r.update(status=0, ok=False, ms=0, text="skipped: time budget")
            self.results.append(r)
            return r
        t0 = time.monotonic()
        try:
            resp = self.http.request(method, path, json=body, params=params, headers=headers)
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
        self.results.append(r)
        time.sleep(0.3)
        return r

    # ═══════════════════ نمایش ═══════════════════

    def section(self, title: str) -> None:
        self.out(f"\n══════════ {title} ══════════")

    def show(self, r: dict, note: str = "") -> None:
        mark = "OK " if r["ok"] else "ERR"
        self.out(f"\n[{mark}] {r['name']}\n      {r['method']} {r['path']} -> HTTP {r['status']} · {r['ms']}ms")
        if r.get("body") is not None:
            self.out(f"      body: {_short(r['body'])}")
        if r.get("params"):
            self.out(f"      params: {_short({k: v for k, v in r['params'].items() if v is not None})}")
        if not r["ok"]:
            err = r.get("data") if r.get("data") is not None else r.get("text", "")
            self.out(f"      error: {_short(err, 400)}")
        elif note:
            self.out(f"      {note}")

    def show_tx(self, r: dict, quote: float | None = None) -> None:
        """تراکنش برگشتی را باز می کند؛ امضا یا ارسال نمی شود."""
        self.show(r)
        if not r["ok"] or not isinstance(r.get("data"), dict):
            return
        tx = r["data"].get("transaction") or r["data"]
        msgs = tx.get("messages") or []
        total = 0
        for i, m in enumerate(msgs):
            amt = int(m.get("amount") or 0)
            total += amt
            self.out(f"      msg{i}: to={m.get('address')} amount={amt / NANO:.9f} "
                     f"{_payload_text(m.get('payload'))} stateInit={'yes' if m.get('stateInit') else 'no'}")
        left = int(tx.get("validUntil") or 0) - int(time.time())
        line = f"      total={total / NANO:.9f} · validUntil in {left}s · messages={len(msgs)}"
        if quote:
            line += f" · quote={quote:g} · diff={(total / NANO - quote) / quote * 100:+.2f}%"
        self.out(line)
        extra = {k: v for k, v in r["data"].items() if k != "transaction"}
        if extra:
            self.out(f"      extra fields: {_short(extra)}")

    # ═══════════════════ تست ها ═══════════════════

    def fragment(self, user: str, channel: str | None, ads: str | None) -> None:
        self.section("Fragment: قیمت ها")
        r = self.call("قیمت پرمیوم", "POST", "/v1/fragment/premium/price/")
        prem = r.get("data") if r["ok"] and isinstance(r.get("data"), dict) else {}
        self.show(r, "  ".join(f"{k}={_short(v)}" for k, v in prem.items()))

        stars_q: dict[int, float | None] = {}
        for q in (50, 1000):
            r = self.call(f"قیمت {q} استارز", "POST", "/v1/fragment/stars/price/", body={"quantity": q})
            stars_q[q] = _price(r.get("data")) if r["ok"] else None
            self.show(r, _short(r.get("data")) + (f" · per star={stars_q[q] / q:.6f}" if stars_q[q] else ""))

        r = self.call("قیمت گیواوی استارز", "POST", "/v1/fragment/stars-giveaway/price/")
        ga_items = _items(r)
        self.show(r, f"{len(ga_items)} packages, first: {_short(ga_items[0] if ga_items else None)}")

        r = self.call("قیمت گیواوی پرمیوم (۱ برنده)", "POST", "/v1/fragment/premium-giveaway/price/",
                      body={"quantity": 1})
        pga = r.get("data") if r["ok"] and isinstance(r.get("data"), dict) else {}
        self.show(r, _short(pga, 300))

        self.section(f"Fragment: گیرنده (@{user})")
        for name, path in (("premium", "/v1/fragment/premium/recipient/"),
                           ("stars", "/v1/fragment/stars/recipient/"),
                           ("telegram-topup", "/v1/fragment/telegram-topup/recipient/")):
            r = self.call(f"گیرنده {name}", "POST", path, body={"username": user})
            self.show(r, _short(r.get("data"), 200))
        bogus = "zz" + uuid.uuid4().hex[:14]
        r = self.call("گیرنده ناموجود (قالب خطا)", "POST", "/v1/fragment/premium/recipient/",
                      body={"username": bogus})
        self.show(r, _short(r.get("data"), 200))

        self.section("Fragment: خرید (فقط ساخت تراکنش؛ امضا نمی شود)")
        r = self.call("خرید پرمیوم ۳ ماه", "POST", "/v1/fragment/premium/buy/",
                      body={"username": user, "months": 3, "currency": "GRAM"})
        self.show_tx(r, _price(prem.get("months3")))
        for cur in ("GRAM", "TON", "USDT"):
            r = self.call(f"خرید ۵۰ استارز currency={cur}", "POST", "/v1/fragment/stars/buy/",
                          body={"username": user, "quantity": 50, "currency": cur})
            self.show_tx(r, stars_q.get(50) if cur != "USDT" else None)
        r = self.call("شارژ حساب تلگرام ۱", "POST", "/v1/fragment/telegram-topup/pay/",
                      body={"username": user, "amount": 1})
        self.show_tx(r, 1.0)

        self.section("Fragment: قالب خطاها")
        r = self.call("پرمیوم ۵ ماه (نامعتبر)", "POST", "/v1/fragment/premium/buy/",
                      body={"username": user, "months": 5, "currency": "GRAM"})
        self.show(r)
        r = self.call("۱۰ استارز (کمتر از حداقل)", "POST", "/v1/fragment/stars/buy/",
                      body={"username": user, "quantity": 10, "currency": "GRAM"})
        self.show(r)
        r = self.call("توکن نامعتبر (قالب خطا)", "POST", "/v1/fragment/premium/price/",
                      headers={"Authorization": "invalid-token"})
        self.show(r)

        if channel:
            self.section(f"Fragment: گیواوی (@{channel})")
            for name, path in (("stars-giveaway", "/v1/fragment/stars-giveaway/recipient/"),
                               ("premium-giveaway", "/v1/fragment/premium-giveaway/recipient/")):
                r = self.call(f"گیرنده {name}", "POST", path, body={"username": channel})
                self.show(r, _short(r.get("data"), 200))
            if ga_items:
                pkg = ga_items[0]
                r = self.call(f"خرید گیواوی {pkg.get('stars')} استارز، ۱ برنده", "POST",
                              "/v1/fragment/stars-giveaway/buy/",
                              body={"username": channel, "quantity": 1, "stars": pkg.get("stars")})
                self.show_tx(r, _price(pkg))
            r = self.call("خرید گیواوی پرمیوم ۳ ماه، ۱ برنده", "POST", "/v1/fragment/premium-giveaway/buy/",
                          body={"username": channel, "months": 3, "quantity": 1, "currency": "GRAM"})
            self.show_tx(r, _price(pga.get("months3")))

        if ads:
            self.section("Fragment: شارژ حساب تبلیغات")
            r = self.call("شارژ Ads ۱", "POST", "/v1/fragment/ads-topup/pay/",
                          body={"fragment_link": ads, "amount": 1})
            self.show_tx(r, 1.0)

    def market(self) -> None:
        self.section("بازار: کالکشن ها و گیفت ها")
        r = self.call("همه کالکشن ها", "GET", "/v1/collections/")
        self.show(r, f"{len(r['data'])} collections" if r["ok"] and isinstance(r.get("data"), list) else "")

        r = self.call("کالکشن های گیفت", "GET", "/v1/collections/gifts/")
        cols = r["data"] if r["ok"] and isinstance(r.get("data"), list) else []
        self.show(r, f"{len(cols)} gift collections, first: {_short(cols[0] if cols else None, 300)}")
        cols = sorted(cols, key=lambda c: -int(((c.get("extra_data") or {}).get("on_sale_all")) or 0))
        col = cols[0].get("address") if cols else None
        if not col:
            return
        self.out(f"      → کالکشن انتخابی: {cols[0].get('name')} ({col})")

        r = self.call("ویژگی های کالکشن", "GET", f"/v1/collections/{col}/attributes/")
        attrs = (r.get("data") or {}).get("attributes") if r["ok"] and isinstance(r.get("data"), dict) else []
        self.show(r, "  ".join(f"{a.get('trait_type')}={len(a.get('values') or [])}" for a in attrs or []))

        r = self.call("گیفت های در فروش (ارزان ترین)", "GET", "/v1/gifts/onsale/",
                      params={"collection_address": col, "sort_by": "min_bid_asc"})
        items = _items(r)
        self.show(r, f"{len(items)} items, cursor={_short((r.get('data') or {}).get('cursor'))}, "
                     f"first: {_short(items[0] if items else None, 400)}")

        r = self.call("تاریخچه فروش گیفت", "GET", "/v1/gifts/history/",
                      params={"limit": 5, "order_by": "new_to_old"})
        hist = _items(r)
        self.show(r, f"{len(hist)} events, first: {_short(hist[0] if hist else None, 400)}")

        r = self.call("NFTهای کالکشن (onsale)", "GET", f"/v1/nfts/collections/{col}/",
                      params={"filter_by": "onsale", "limit": 5})
        self.show(r, f"{len(_items(r))} items")

        if not items:
            return
        it = items[0]
        nft = it.get("address")
        r = self.call("اطلاعات یک NFT", "GET", f"/v1/nfts/{nft}/")
        self.show(r, _short(r.get("data"), 500))
        owner = it.get("real_owner") or it.get("owner")
        if owner:
            r = self.call("NFTهای یک مالک", "GET", f"/v1/nfts/owner/{owner}/", params={"limit": 5})
            self.show(r, f"{len(_items(r))} items")

        price = _ton_amount(it.get("min_bid"))
        cur = it.get("currency") or "TON"
        r = self.call(f"خرید NFT ارزان ترین ({price:g} {cur})", "POST", "/v1/nfts/buy/",
                      body={"data": [{"nft_address": nft, "price": price, "currency": cur}]})
        self.show_tx(r, price)

    def rent(self) -> None:
        self.section("بازار: اجاره")
        for cat in ("gifts", "usernames", "numbers"):
            r = self.call(f"قابل اجاره: {cat}", "GET", f"/v1/rent/{cat}/", params={"sort_by": "recently_touch"})
            items = _items(r)
            self.show(r, f"{len(items)} items, first: {_short(items[0] if items else None, 300)}")
            r = self.call(f"تاریخچه اجاره: {cat}", "GET", f"/v1/rent/{cat}/history/",
                          params={"limit": 5, "order_by": "new_to_old"})
            self.show(r, f"{len(_items(r))} events")
        r = self.call("اجاره های من", "GET", "/v1/rent/my-rented/")
        self.show(r, _short(r.get("data"), 200))

    def summary(self) -> None:
        ok = sum(1 for r in self.results if r["ok"])
        self.section(f"خلاصه: {ok}/{len(self.results)} درخواست موفق")
        for r in self.results:
            self.out(f"  {'OK ' if r['ok'] else 'ERR'} {r['status']:>3} {r['method']:<4} {r['path']:<48} {r['name']}")


def run(token: str, user: str, channel: str | None = None, ads: str | None = None, *,
        raw: bool = False, out: Callable[[str], None] = print, budget: float | None = None) -> list[dict]:
    """همه تست ها پشت سر هم؛ اگر یک بخش خطا داد، متن خطا در گزارش می آید و بقیه ادامه می دهند."""
    chk = Check(token, out, budget)
    out(f"MarketApp check · {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC · {BASE} · "
        f"proxy={'yes' if config.marketapp_proxy else '-'} · "
        f"user=@{user} channel={channel or '-'} ads={'yes' if ads else '-'} · "
        f"python {sys.version.split()[0]} · httpx {httpx.__version__}")
    try:
        for step in (lambda: chk.fragment(user, channel, ads), chk.market, chk.rent):
            try:
                step()
            except Exception:  # noqa: BLE001
                out("\n[CRASH]\n" + traceback.format_exc())
        chk.summary()
        if raw:
            out("\n══════════ پاسخ خام (JSON) ══════════")
            out(json.dumps(chk.results, ensure_ascii=False, indent=2, default=str))
    finally:
        chk.close()
    return chk.results
