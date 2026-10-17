"""تست زنده MarketApp API از ترمینال. همان تست «تنظیمات ← 💎 خدمات تلگرام ← 🧪 تست کامل API» ربات.

  python check_marketapp.py --user USERNAME                همه تست ها
  python check_marketapp.py --user USERNAME --channel CH   + گیواوی برای کانال CH
  python check_marketapp.py --user USERNAME --ads LINK     + شارژ حساب تبلیغات (لینک fragment.com/ads/pay?account=...)
  python check_marketapp.py --user USERNAME --json         + پاسخ خام همه درخواست ها به صورت JSON

توکن از MARKETAPP_TOKEN در .env (یا توکن پنل ادمین) خوانده می شود و هیچ جا چاپ نمی شود.
هیچ تراکنشی امضا یا ارسال نمی شود. منطق تست: app/services/marketapp_check.py
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys


async def _token() -> str:
    from app.config import config
    from app.db import Database
    from app.services import marketapp

    if config.marketapp_token:
        return config.marketapp_token
    db = Database(config.db_path)
    await db.connect()
    try:
        return await marketapp.token(db)
    finally:
        await db.close()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="MarketApp live check (never signs or sends a transaction)")
    ap.add_argument("--user", required=True, help="یوزرنیم گیرنده تست، بدون @")
    ap.add_argument("--channel", help="کانال برای تست گیواوی، بدون @")
    ap.add_argument("--ads", help="لینک fragment.com/ads/pay?account=... برای تست شارژ تبلیغات")
    ap.add_argument("--json", action="store_true", help="پاسخ خام همه درخواست ها")
    args = ap.parse_args()

    from app.services import marketapp_check

    token = asyncio.run(_token())
    if not token and sys.stdin.isatty():
        token = getpass.getpass("MarketApp token: ").strip()
    if not token:
        sys.exit("MARKETAPP_TOKEN در .env نیست و در پنل ادمین هم توکنی ثبت نشده.")

    marketapp_check.run(token, args.user.lstrip("@"), (args.channel or "").lstrip("@") or None, args.ads,
                        raw=args.json, out=lambda s: print(s.replace(token, "***")))


if __name__ == "__main__":
    main()
