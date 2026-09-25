"""عضویت اجباری در کانال (فعلا فقط برای تست رایگان).

قالب هر مورد در JOIN_CHANNELS:
  @Obour_Net                                  کانال عمومی
  -1001234567890=https://t.me/+AbCdEf         کانال خصوصی با لینک دعوت

نکته مهم: ربات باید در کانال ادمین باشد، وگرنه تلگرام اجازه
get_chat_member نمی دهد. در آن حالت عمدا «عضو هست» فرض می کنیم تا یک
اشتباه در تنظیمات، جلوی تست رایگان همه کاربران را نگیرد. دلیلش در لاگ
ثبت می شود.
"""
from __future__ import annotations

import logging

from app.config import config

log = logging.getLogger("obour.join")

_OK_STATUS = {"creator", "administrator", "member"}


def parse(entry: str) -> tuple[str, str, str]:
    """(شناسه چت، آدرس پیوستن، عنوان نمایشی)"""
    entry = entry.strip()
    if "=" in entry:
        chat, _, url = entry.partition("=")
        chat, url = chat.strip(), url.strip()
        title = chat if chat.startswith("@") else "کانال عبور"
        return chat, url, title
    handle = entry.lstrip("@")
    return f"@{handle}", f"https://t.me/{handle}", f"@{handle}"


def channels() -> list[tuple[str, str, str]]:
    return [parse(x) for x in config.join_channels if x.strip()]


def required() -> bool:
    """آیا عضویت اجباری برای تست رایگان روشن است؟"""
    return bool(config.join_for_trial and config.join_channels)


async def missing(bot, telegram_id: int) -> list[tuple[str, str, str]]:  # noqa: ANN001
    """کانال هایی که کاربر هنوز عضوشان نیست."""
    out: list[tuple[str, str, str]] = []
    for chat, url, title in channels():
        try:
            member = await bot.get_chat_member(chat, telegram_id)
        except Exception:  # noqa: BLE001
            # ربات ادمین نیست یا آیدی کانال غلط است -> سد راه کاربر نشو
            log.warning("بررسی عضویت %s ممکن نشد", chat, exc_info=True)
            continue
        status = getattr(member, "status", "")
        status = getattr(status, "value", status)
        ok = status in _OK_STATUS or (
            status == "restricted" and getattr(member, "is_member", False)
        )
        if not ok:
            out.append((chat, url, title))
    return out
