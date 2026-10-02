"""روش پرداخت هر تراکنش، برای سوابق کاربر (مینی اپ و ربات).

جدول transactions ستون روش ندارد؛ روش از پیوندهای موجود معلوم می شود:
فاکتور کریپتو و فاکتور Stars هرکدام txn_id دارند، خرید هوش مصنوعی هم.
پس برای ردیف های قدیمی هم بدون مهاجرت درست جواب می دهد. ردیف باید از
db.user_transactions آمده باشد (با ستون های cx_* / st_* / ai_*).
"""
from __future__ import annotations

METHODS = {
    "card": "کارت به کارت",
    "ton": "TON · کیف پول کریپتو",
    "usdt": "USDT · کیف پول کریپتو",
    "stars": "Telegram Stars",
    "wallet": "موجودی کیف پول عبور",
    "referral": "پاداش هم‌سفر",
    "refund": "برگشت به کیف پول",
    "admin": "تغییر توسط پشتیبانی",
}


def _units(units, asset: str) -> str:  # noqa: ANN001
    from app.services import crypto

    try:
        return f"{crypto.fmt_units(int(units), asset)} {asset}"
    except (TypeError, ValueError):
        return ""


def _short(addr: str) -> str:
    return addr if len(addr) <= 16 else f"{addr[:6]}…{addr[-6:]}"


def info(t: dict) -> dict:
    """{"method": کلید، "label": متن، "details": [[عنوان، مقدار]...]، "tx_url": لینک زنجیره}."""
    typ = t.get("type") or ""
    details: list[list[str]] = []
    url = ""
    if typ == "charge":
        asset = (t.get("cx_asset") or "").upper()
        if asset:
            method = "usdt" if asset == "USDT" else "ton"
            paid = t.get("cx_paid") or t.get("cx_units")
            if paid:
                details.append(["مبلغ پرداختی", _units(paid, asset)])
            if t.get("cx_payer"):
                details.append(["کیف پول پرداخت‌کننده", _short(str(t["cx_payer"]))])
            if t.get("cx_hash"):
                from app.services import crypto

                url = crypto._explorer(str(t["cx_hash"]))
                details.append(["تراکنش شبکه", _short(str(t["cx_hash"]))])
        elif t.get("st_stars"):
            method = "stars"
            details.append(["تعداد ستاره", f"{int(t['st_stars']):,} ⭐"])
        else:
            method = "card"
    elif typ in ("purchase", "ai_purchase"):
        method = "wallet"
        if t.get("ai_title"):
            details.append(["محصول", str(t["ai_title"])])
            if t.get("ai_code"):
                details.append(["سفارش", str(t["ai_code"])])
    elif typ == "referral":
        method = "referral"
    elif typ == "refund":
        method = "refund"
    elif typ == "admin_adjust":
        method = "admin"
    else:
        method = ""
    return {"method": method, "label": METHODS.get(method, ""), "details": details, "tx_url": url}
