"""خدمات تلگرام از MarketApp (پرمیوم، استارز و ...). مرجع: MARKETAPP_FA.md

فعلا فقط تنظیمات و تست زنده API از پنل ادمین؛ فروش به کاربر هنوز پیاده نشده.

تست کامل حدود یک دقیقه طول می کشد، پس در پس زمینه اجرا می شود (مثل
به روزرسانی قیمت شماره ها) و فایل گزارش بعدا در چت ادمین می آید. httpx این
تست همگام است و در یک thread جدا اجرا می شود تا حلقه ربات گیر نکند.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING

from app.config import config
from app.utils import esc

if TYPE_CHECKING:
    from aiogram import Bot

    from app.db import Database

log = logging.getLogger("obour.marketapp")

KEY_SETTING = "marketapp_token"
USER_SETTING = "marketapp_test_user"
CHANNEL_SETTING = "marketapp_test_channel"

USERNAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{3,31}")
CHECK_BUDGET = 150          # ثانیه؛ بعدش درخواست های باقی مانده رد می شوند

_check: asyncio.Task | None = None


async def token(db: "Database") -> str:
    return config.marketapp_token or (await db.get_setting(KEY_SETTING, "") or "").strip()


def valid_token(raw: str) -> bool:
    return 16 <= len(raw) <= 300 and not re.search(r"\s", raw)


def clean_username(raw: str) -> str | None:
    """«@name» یا «t.me/name» یا «name» ← name؛ نامعتبر ← None."""
    s = raw.strip().removeprefix("https://").removeprefix("http://").removeprefix("t.me/").lstrip("@")
    return s if USERNAME_RE.fullmatch(s) else None


def check_running() -> bool:
    return _check is not None and not _check.done()


def report(tok: str, user: str, channel: str | None) -> tuple[str, list[dict]]:
    """همگام: کل گزارش متنی (توکن پاک شده) و نتیجه درخواست ها."""
    from app.services import marketapp_check

    lines: list[str] = []
    results = marketapp_check.run(tok, user, channel, None, raw=True, out=lines.append, budget=CHECK_BUDGET)
    return "\n".join(lines).replace(tok, "***"), results


def _caption(results: list[dict], user: str, channel: str | None) -> str:
    ok = sum(1 for r in results if r["ok"])
    out = [f"🧪 <b>تست کامل MarketApp</b> · @{esc(user)}" + (f" · @{esc(channel)}" if channel else ""),
           f"✅ {ok} از {len(results)} درخواست موفق"]
    bad = [r for r in results if not r["ok"]]
    if bad and not ok:
        out.append(f"❌ هیچ درخواستی موفق نشد: {esc(str(bad[0].get('text') or bad[0].get('data') or '')[:150])}")
        if all(r["status"] == 0 for r in bad):
            out.append("هاست به api.marketapp.org وصل نمی‌شود؛ MARKETAPP_PROXY را در .env بگذار.")
    elif bad:
        out.append("خطاها (بعضی عمدی اند، برای دیدن قالب خطا):")
        for r in bad[:8]:
            out.append(f"• {r['status']} {esc(r['name'])}")
        if len(bad) > 8:
            out.append(f"• … و {len(bad) - 8} مورد دیگر")
    out.append("جزئیات و پاسخ خام همه درخواست ها در فایل. چیزی امضا یا پرداخت نشد.")
    return "\n".join(out)[:1024]


async def _check_and_send(bot: "Bot", tok: str, chat_id: int, user: str, channel: str | None) -> None:
    from aiogram.types import BufferedInputFile

    try:
        text, results = await asyncio.to_thread(report, tok, user, channel)
    except Exception as exc:  # noqa: BLE001
        log.exception("marketapp check failed")
        await bot.send_message(chat_id, f"❌ تست MarketApp اجرا نشد: <code>{esc(str(exc)[:300])}</code>")
        return
    name = f"marketapp_check_{datetime.now():%Y%m%d_%H%M%S}.txt"
    await bot.send_document(chat_id, BufferedInputFile(text.encode("utf-8"), filename=name),
                            caption=_caption(results, user, channel))


async def start_check(bot: "Bot", db: "Database", chat_id: int, user: str, channel: str | None) -> bool:
    """تست کامل را در پس زمینه شروع می کند. اگر یکی در حال اجراست یا توکن نیست False."""
    global _check
    tok = await token(db)
    if not tok or check_running():
        return False
    _check = asyncio.get_running_loop().create_task(_check_and_send(bot, tok, chat_id, user, channel))
    return True
