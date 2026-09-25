"""جدول واقعی برای صفحات آماری، با Rich Message (Bot API 10.1، تیر ۱۴۰۵).

قبل از این، سوابق و دستگاه‌های متصل با کاراکترهای جعبه‌ای (├ │ ╮ ╯)
شبیه‌سازی می‌شدند - که روی صفحه‌های عریض یا فونت‌های مختلف به‌هم می‌ریخت.
از تیر ۱۴۰۵، تلگرام جدول واقعی را در پیام پشتیبانی می‌کند
(InputRichBlockTable) و دیگر لازم نیست جدول را با متن شبیه‌سازی کرد.

نیازمندی‌ها:
- aiogram باید ۳.۳۰ یا بالاتر باشد.
- سرور Bot API (رسمی یا self-hosted) باید Bot API 10.1+ را پشتیبانی کند.

اگر هرکدام نبود، ساخت جدول با ImportError/AttributeError یا خطای تلگرام
مواجه می‌شود. این ماژول عمدا هیچ‌جا خطا را نمی‌گیرد - صدا زننده
(app/ui.py و هندلرها) باید با try/except به نسخه متنی قدیمی برگردد،
چون این قابلیت خیلی تازه است و ممکن است همه جا هنوز در دسترس نباشد.
"""
from __future__ import annotations


def table(
    headers: list[str],
    rows: list[list[str]],
    *,
    caption: str | None = None,
    align: list[str] | None = None,
) -> "InputRichMessage":  # noqa: F821
    """جدول ساده: یک ردیف عنوان + ردیف‌های داده، راست‌چین پیش‌فرض.

    align اگر داده شود باید هم‌طول headers باشد؛ هر مقدار یکی از
    'right' | 'left' | 'center' است. پیش‌فرض همه‌چیز راست‌چین می‌ماند،
    چون محتوای فارسی است.
    """
    from aiogram.types import InputRichBlockTable, InputRichMessage, RichBlockTableCell

    aligns = align or ["right"] * len(headers)

    def _row(values: list[str], header: bool) -> list[RichBlockTableCell]:
        return [
            RichBlockTableCell(
                text=str(v),
                align=aligns[i] if i < len(aligns) else "right",
                valign="middle",
                is_header=True if header else None,
            )
            for i, v in enumerate(values)
        ]

    grid = [_row(headers, header=True)] + [_row(r, header=False) for r in rows]
    block = InputRichBlockTable(cells=grid, is_bordered=True, is_striped=True)
    blocks: list = [block]

    from aiogram.types import InputRichBlockParagraph, RichTextBold

    if caption:
        # عنوان به‌عنوان یک پاراگراف پررنگ بالای جدول - caption خود
        # InputRichBlockTable هم هست، ولی زیر جدول می‌آید که برای یک
        # سربرگ طبیعی نیست.
        blocks.insert(
            0, InputRichBlockParagraph(text=RichTextBold(text=caption))
        )

    return InputRichMessage(blocks=blocks, is_rtl=True)


def photo_page(
    photo: str,
    body: str,
    *,
    caption: str | None = None,
) -> "InputRichMessage":  # noqa: F821
    """صفحه ای با یک عکس بالا و متن زیرش، به صورت Rich Message.

    چرا این طوری و نه sendPhoto معمولی؟
    تلگرام اجازه نمی دهد یک پیام متنی به پیام عکس دار ویرایش شود؛ یعنی
    با روش معمول، رفتن به صفحه لوکیشن ها و برگشتن، هر بار پیام را پاک
    می کرد و پیام تازه می فرستاد. ولی Rich Message یک پیام *متنی* است
    که می تواند بلوک عکس داشته باشد - و editMessageText با پارامتر
    rich_message آن را همان جا ویرایش می کند. پس رفت و برگشت بین
    صفحه ها بدون پاک شدن انجام می شود.

    photo می تواند file_id (ترجیحا) یا آدرس عمومی عکس باشد.
    body متن صفحه است؛ هر پاراگراف (جدا شده با خط خالی) یک بلوک می شود.
    """
    from aiogram.types import (
        InputMediaPhoto,
        InputRichBlockParagraph,
        InputRichBlockPhoto,
        InputRichMessage,
    )

    # فیلد photo یک رشته نمی گیرد، بلکه یک InputMediaPhoto می خواهد.
    # (لاگ واقعی: "Input should be a valid dictionary or instance of
    # InputMediaPhoto"). خود InputMediaPhoto هم در فیلد media، file_id
    # یا آدرس اینترنتی را به صورت رشته قبول می کند.
    photo_block = InputRichBlockPhoto(
        photo=InputMediaPhoto(media=photo, caption=caption or None)
    )

    # متن یکجا در *یک* بلوک می رود، نه یک بلوک به ازای هر پاراگراف.
    # وقتی هر پاراگراف بلوک جدا باشد، فاصله بینشان را تلگرام تعیین
    # می کند و خط های خالی متن اصلی از بین می روند - نتیجه اش متنی
    # فشرده و بدون نفس است. با یک بلوک، خط ها همان طور که نوشته شده اند
    # می مانند.
    blocks: list = [photo_block, InputRichBlockParagraph(text=body)]

    return InputRichMessage(blocks=blocks, is_rtl=True)
