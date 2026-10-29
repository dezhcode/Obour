"""ایمیل کد ورود برنامهٔ اندروید AsoTas با SMTP همان هاست (تنظیمات GAME_CLUB_SMTP_* در .env).

    GAME_CLUB_SMTP_HOST      مثلا mail.dezhcode.pyho.ir (بدون آن ورود با ایمیل خاموش است)
    GAME_CLUB_SMTP_PORT      ۴۶۵ برای SSL (پیش فرض) یا ۵۸۷ برای STARTTLS
    GAME_CLUB_SMTP_USER      نام کاربری صندوق، معمولا خود آدرس
    GAME_CLUB_SMTP_PASSWORD
    GAME_CLUB_SMTP_FROM      فرستنده؛ پیش فرض همان USER
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from .config import gc

TIMEOUT = 20


def enabled() -> bool:
    return bool(gc.smtp_host and (gc.smtp_from or gc.smtp_user))


def code_mail(code: str, minutes: int) -> tuple[str, str, str]:
    """(موضوع، متن ساده، html) ایمیل کد ورود با لحن تاسی."""
    subject = f"کد ورود AsoTas · {code}"
    text = (f"سلام رفیق 👋\n\nکد ورودت به AsoTas اینه\n\n{code}\n\n"
            f"تا {minutes} دقیقه کار می‌کنه\nاگه خودت نخواستی بی‌خیالش شو و به هیچ‌کس نده\n\nتاسی 🎲")
    html = f"""<!doctype html><html lang="fa" dir="rtl"><body style="margin:0;padding:24px 12px;background:#F2F0F8">
<div style="max-width:420px;margin:0 auto;background:#fff;border-radius:20px;padding:28px 24px;text-align:center;
font-family:Vazirmatn,Tahoma,'Segoe UI',sans-serif;color:#1B2340;direction:rtl">
<div style="font-size:15px;font-weight:700;color:#5B5F7A">AsoTas</div>
<p style="font-size:16px;line-height:28px;margin:16px 0 8px">سلام رفیق 👋<br>کد ورودت به AsoTas اینه</p>
<div dir="ltr" style="font-size:36px;font-weight:800;letter-spacing:8px;background:#FFF4D6;color:#1B2340;
border-radius:14px;padding:14px 0;margin:8px 0 16px">{code}</div>
<p style="font-size:13px;line-height:24px;color:#5B5F7A;margin:0">تا {minutes} دقیقه کار می‌کنه<br>
اگه خودت نخواستی بی‌خیالش شو و به هیچ‌کس نده</p>
<p style="font-size:13px;color:#5B5F7A;margin:20px 0 0">تاسی 🎲</p></div></body></html>"""
    return subject, text, html


def _send_sync(to: str, subject: str, text: str, html: str) -> None:
    sender = gc.smtp_from or gc.smtp_user
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("AsoTas", sender))
    msg["To"] = to
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1] if "@" in sender else None)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    ctx = ssl.create_default_context()
    if gc.smtp_port == 465:
        with smtplib.SMTP_SSL(gc.smtp_host, gc.smtp_port, context=ctx, timeout=TIMEOUT) as s:
            if gc.smtp_user:
                s.login(gc.smtp_user, gc.smtp_password)
            s.send_message(msg)
        return
    with smtplib.SMTP(gc.smtp_host, gc.smtp_port, timeout=TIMEOUT) as s:
        s.ehlo()
        if s.has_extn("starttls"):
            s.starttls(context=ctx)
            s.ehlo()
        if gc.smtp_user:
            s.login(gc.smtp_user, gc.smtp_password)
        s.send_message(msg)


async def send_code(to: str, code: str, minutes: int) -> None:
    """فرستادن کد؛ خطای SMTP همان طور بالا می رود (appauth آن را send_fail می کند)."""
    subject, text, html = code_mail(code, minutes)
    await asyncio.to_thread(_send_sync, to, subject, text, html)
