"""ابزار مشترک نمایش پیام.

مشکلی که این ماژول حل می کند:
هر جا با edit_text کار می کردیم، سه حالت خطا می داد و پیام تازه ساخته
می شد یا هندلر می افتاد:

۱. پیام فعلی عکس است (مثلا صفحه QR) و متن ندارد -> edit_text شکست می خورد
۲. محتوای جدید دقیقا مثل قبلی است -> message is not modified
۳. پیام خیلی قدیمی است و تلگرام اجازه ویرایش نمی دهد

با edit_or_send هر سه حالت پوشش داده می شود و کاربر همیشه یک پیام
زنده می بیند، نه یک دنباله از پیام های تکراری.
"""
from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message


async def edit_or_send(
    message: Message,
    text: str,
    reply_markup=None,  # noqa: ANN001
    **kwargs,
) -> Message:
    """پیام را در جای خودش ویرایش می کند. اگر نشد، جایگزینش می کند.

    ایموجی سفارشی اینجا اعمال نمی شود؛ این کار روی لایه session انجام
    می شود (EmojiOutgoingMiddleware). قبلا در هر دو جا اعمال می شد و
    نتیجه تگ tg-emoji تودرتو بود که تلگرام آن را رد می کند.
    """
    # همیشه اول ویرایش را امتحان می کنیم، حتی وقتی message.text خالی است.
    # پیام های Rich Message (جدول) اصلا فیلد text ندارند، پس شرط قبلی
    # (message.text is not None) باعث می شد هر رفت و برگشت از یک صفحه
    # جدولی، پیام را پاک کند و پیام تازه بفرستد - یعنی چت می پرید و
    # تاریخچه شلوغ می شد. اگر پیام واقعا قابل ویرایش نباشد (عکس، QR)،
    # تلگرام خطا می دهد و همان مسیر قبلی (حذف و ارسال) اجرا می شود.
    try:
        return await message.edit_text(text, reply_markup=reply_markup, **kwargs)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return message  # چیزی عوض نشده، همان پیام سر جایش می ماند
        # هر خطای دیگر ویرایش (پیام عکس دار، قدیمی، حذف شده و ...): پیام تازه

    # ویرایش ممکن نشد (عکس، QR و مانند آن).
    # قدیمی را برمی داریم تا چت شلوغ نشود، بعد پیام تازه می فرستیم.
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    return await message.answer(text, reply_markup=reply_markup, **kwargs)


async def edit_or_send_rich(message: Message, rich, reply_markup=None) -> Message:  # noqa: ANN001
    """نسخه جدولی edit_or_send: ویرایش یا ارسال با Rich Message (جدول واقعی).

    نیاز به Bot API 10.1+‌ و aiogram 3.30+ دارد. اگر ارسال شکست بخورد
    (کلاینت قدیمی، سرور Bot API خودمیزبان قدیمی و...)، استثنا بالا
    می‌رود - صدا زننده باید بگیرد و به نسخه متنی برگردد. این تابع
    خودش هیچ fallback ای انجام نمی‌دهد چون تصمیم گیری درباره نسخه
    متنی جایگزین به محتوای خود صفحه بستگی دارد.
    """
    bot = message.bot
    # مثل edit_or_send: بدون شرط روی message.text. پیام جدولی فیلد text
    # ندارد، پس شرط قبلی باعث می شد جابجایی بین دو صفحه جدولی (مثلا
    # صفحه بعد سوابق) هر بار پیام را پاک کند و از نو بفرستد.
    try:
        return await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message.message_id,
            rich_message=rich,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return message
        # هر خطای دیگر ویرایش: پیام تازه می‌فرستیم (زیر همین تابع ادامه دارد)

    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    return await bot.send_rich_message(
        chat_id=message.chat.id, rich_message=rich, reply_markup=reply_markup
    )


async def working(message: Message, text: str) -> Message:
    """نمایش پیام «در حال انجام» همراه با نشانگر تایپینگ.

    نشانگر تایپینگ به کاربر می گوید ربات زنده است و دارد کار می کند،
    نه اینکه هنگ کرده. تلگرام آن را حدود ۵ ثانیه یا تا پیام بعدی نشان می دهد.

    خود پیام برگردانده می شود تا مراحل بعدی (تحویل سرویس یا نمایش خطا)
    روی همان پیام بنشینند. اگر ورودی پیام خود کاربر باشد، ویرایش ممکن
    نیست و پیام تازه ای ساخته و برگردانده می شود.
    """
    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
    except Exception:  # noqa: BLE001
        pass  # نشانگر تزئینی است، نباید جریان کار را بشکند
    try:
        edited = await message.edit_text(text)
        return edited if isinstance(edited, Message) else message
    except TelegramBadRequest:
        return await message.answer(text)


async def toast(call, text: str, alert: bool = False) -> None:
    """پاسخ سریع روی دکمه بدون ویرایش پیام.

    برای تاییدهای کوچک که ارزش عوض کردن کل صفحه را ندارند.
    """
    try:
        await call.answer(text, show_alert=alert)
    except Exception:  # noqa: BLE001
        pass


async def deliver(
    message: Message,
    caption: str,
    sub_url: str,
    reply_markup=None,  # noqa: ANN001
    filename: str = "obour_sub.png",
    effect: str = "",
) -> None:
    """تحویل سرویس در یک پیام واحد: QR + متن + دکمه ها.

    چرا یک پیام؟ دو پیام جدا (عکس و متن) چت را شلوغ می کند و کاربر باید
    بین آن ها بالا و پایین برود. با caption روی عکس، همه چیز یکجاست.

    سه مرحله جدا با خطای جدا: ساخت QR، ارسال عکس، ارسال متن. اگر هر
    کدام شکست بخورد مرحله بعد اجرا می شود و دلیلش در لاگ می نشیند. در
    نسخه قبلی یک except همه را یکجا می گرفت و مثلا خطای افکت، QR را هم
    با خودش می برد بدون اینکه معلوم شود کدام بخش خراب بوده.

    هر ارسال در صورت نیاز دو بار تلاش می شود: با افکت، و اگر نشد بدون
    افکت. افکت تزئینی است و نباید تحویل سرویس را از بین ببرد.
    """
    import logging

    from aiogram.types import BufferedInputFile, LinkPreviewOptions

    from . import effects
    from .utils import qr_png

    log = logging.getLogger("obour.ui")
    no_preview = LinkPreviewOptions(is_disabled=True)
    # افکت فقط روی پیام تازه سوار می شود، و اینجا واقعا پیام تازه
    # می فرستیم (answer_photo)، پس جای درستی برای افکت است.
    fx = effects.kwargs(effect, message.chat.id) if effect else {}
    attempts = (fx, {}) if fx else ({},)

    # ---------- ۱) ساخت تصویر QR ----------
    photo = None
    if sub_url:
        try:
            photo = BufferedInputFile(qr_png(sub_url), filename=filename)
        except Exception:  # noqa: BLE001
            # معمولا یعنی Pillow یا qrcode نصب نیست، یا مسیر قاب خراب است
            log.error(
                "ساخت تصویر QR ناموفق بود - سرویس بدون QR تحویل می شود. "
                "اگر روی هاست تازه نصب کرده ای، pip install -r requirements.txt را اجرا کن",
                exc_info=True,
            )

    # ---------- ۲) ارسال عکس ----------
    if photo is not None:
        for attempt_fx in attempts:
            try:
                await message.answer_photo(
                    photo=photo, caption=caption, reply_markup=reply_markup, **attempt_fx
                )
                try:
                    await message.delete()  # پیام «در حال ساخت» را برمی داریم
                except TelegramBadRequest:
                    pass
                return
            except Exception as exc:  # noqa: BLE001
                if attempt_fx:
                    effects.disable(effect, str(exc))
                    continue
                log.error("ارسال عکس QR ناموفق بود", exc_info=True)

    # ---------- ۳) حالت پشتیبان: فقط متن ----------
    # اینجا هم پیام تازه می فرستیم تا افکت از دست نرود؛ ویرایش پیام
    # اجازه افکت نمی دهد.
    for attempt_fx in attempts:
        try:
            await message.answer(
                caption,
                reply_markup=reply_markup,
                link_preview_options=no_preview,
                **attempt_fx,
            )
            try:
                await message.delete()
            except TelegramBadRequest:
                pass
            return
        except Exception as exc:  # noqa: BLE001
            if attempt_fx:
                effects.disable(effect, str(exc))
                continue
            log.error("ارسال پیام تحویل ناموفق بود", exc_info=True)

    # آخرین تلاش: حتما باید لینک به دست کاربر برسد
    await edit_or_send(
        message, caption, reply_markup=reply_markup, link_preview_options=no_preview
    )


async def consume(message: Message, prompt_id: int | None = None) -> None:
    """پاک کردن پیام ورودی کاربر (و در صورت نیاز پیام سوال).

    وقتی کاربر مقداری تایپ می کند (مثلا مبلغ شارژ)، نگه داشتن آن پیام
    چت را شلوغ می کند و مقدار حساس (مثل مبلغ) بی دلیل باقی می ماند.
    خطاها نادیده گرفته می شوند چون تلگرام فقط تا ۴۸ ساعت اجازه حذف می دهد.
    """
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    if prompt_id:
        try:
            await message.bot.delete_message(message.chat.id, prompt_id)
        except Exception:  # noqa: BLE001
            pass
