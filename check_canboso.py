"""خروجی واقعی canboso و برداشت ربات از آن، کنار هم.

  python check_canboso.py            جدول محصولات و موجودی
  python check_canboso.py --json     همه چیز به صورت JSON (پاسخ خام + برداشت ربات)

کلید از CANBOSO_API_KEY در .env خوانده می شود و هیچ جا چاپ نمی شود.
فقط می خواند: هیچ خریدی انجام نمی دهد.
"""
from __future__ import annotations

import asyncio
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def _st(v) -> str:  # noqa: ANN001
    return "∞" if v is None else str(v)


async def main() -> None:
    from app.config import config
    from app.db import Database
    from app.services import ai_shop

    db = Database(config.db_path)
    await db.connect()
    try:
        key = await ai_shop.api_key(db)
        if not key:
            print("CANBOSO_API_KEY در .env نیست.")
            return
        cb = await ai_shop.client(db)
        try:
            raw = await cb.debug()
        finally:
            await cb.close()
        try:
            view = await ai_shop.catalog(db, force=True, admin=True)
            for x in view["items"]:
                x.pop("raw", None)
        except Exception as exc:  # noqa: BLE001
            view = {"error": str(exc), "items": [], "balance": None}

        if "--json" in sys.argv:
            out = json.dumps({"responses": raw, "bot_view": view}, ensure_ascii=False, indent=2, default=str)
            print(out.replace(key, "***"))
            return

        for path, r in raw.items():
            print(f"GET {path} -> HTTP {r.get('status')} · {r.get('ms', '-')}ms {r.get('error', '')}")
        bal = view.get("balance")
        print(f"\nکیف پول شما نزد canboso: {(bal or {}).get('text') or (bal or {}).get('balance', 'خوانده نشد')}")
        if view.get("error"):
            print("خطا:", view["error"])
        print(f"\n{'':2}{'id':<28}{'name':<34}{'type':<16}{'cost':>12}  {'toman':>12}  API  wallet  shown")
        for x in view["items"]:
            mark = "on " if x["visible"] else "off"
            price = f"{x['price']:,}" if x["priced"] else "no rate"
            shown = _st(x["stock"]) if x["available"] else "out"
            print(f"{mark} {x['id'][:27]:<28}{x['name'][:33]:<34}{x['type'][:15]:<16}"
                  f"{x['cost']:>9g} {x['currency']:<3}{price:>12}  {_st(x['api_stock']):>3}  {_st(x['wallet_stock']):>6}  {shown:>5}"
                  + (f"  months={x['months']}" if x["months"] else "") + ("  email" if x["needs_email"] else ""))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
