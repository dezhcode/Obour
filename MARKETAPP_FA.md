# MarketApp API (مرجع برای خدمات تلگرام)

یادداشت مرجع برای فروش **تلگرام پرمیوم، استارز** و بقیه خدمات Fragment از طریق
[marketapp.org](https://marketapp.org) با پرداخت از کیف پول TON خودمان. هنوز در ربات پیاده نشده.

> **منبع‌ها (هیچ‌کدام رسمی نیستند):**
> - کد کامل کتابخانه `marketapp-api` نسخه 1.0.1 روی PyPI (نویسنده S1qwy). مخزن GitHub آن
>   (`s1qwy/marketapp-api`) دیگر عمومی نیست.
> - تاریخچه `S1qwy/fragment-api-py` روی GitHub: نسخه ۱۲ «No-KYC mode» را با همین API ساخته بود و
>   نسخه ۱۳ آن را حذف کرد.
> - پلاگین `marketapp` در `kloveren/morgan-gift-plugins` روی GitHub (بخش گیفت‌ها، با `api.marketapp.ws/v1`).
>
> مستندات رسمی را ندیده‌ایم و API هنوز با توکن واقعی تست نشده. قبل از پروداکشن با یک خرید کوچک
> (مثلا ۵۰ استارز برای خودمان) همه چیز را بسنج.

## تست زنده

```bash
MARKETAPP_TOKEN=... python check_marketapp.py --user YOUR_USERNAME [--channel CHANNEL] [--ads LINK] [--json]
```

یا از مرورگر (کل گزارش به صورت یک فایل `.txt` دانلود می‌شود):

```
https://dezhcode.pyho.ir/obour/marketapp-check?key=ADMIN_KEY&user=USERNAME&channel=CHANNEL
```

توکن از `MARKETAPP_TOKEN` در `.env` هاست؛ اگر نبود از پارامتر `mt=` (در access log هاست می‌ماند، پس فقط
برای توکن موقت). بدون `user` یوزرنیم اولین ادمین (`ADMIN_IDS`) استفاده می‌شود.

همه endpointهای Fragment، بازار و اجاره را با داده واقعی صدا می‌زند. تراکنش‌های خرید را فقط باز می‌کند
(مقصد، مبلغ، کامنت، اختلاف با قیمت اعلام شده) و **هیچ چیزی امضا یا ارسال نمی‌کند**. توکن چاپ نمی‌شود.

## اصول

- **آدرس پایه:** `https://api.marketapp.org` (قدیمی: `https://api.marketapp.ws`). همه مسیرها با `/v1/`
  شروع و با `/` تمام می‌شوند.
- **هدرها:** `Authorization: <token>` (خود توکن، **بدون** `Bearer`) + `Content-Type: application/json`.
- **توکن:** از `https://marketapp.org/api-token`. فقط در `.env`.
  کتابخانه `fragment-api-py` نسخه ۱۲ یک توکن پیش‌فرض در کدش دارد که مال کس دیگری است؛ استفاده نکن.
- **خطا:** وضعیت `422` یعنی بدنه نامعتبر (اعتبارسنجی)، هر وضعیت ≥ 400 دیگر خطای API است. بدنه خطا
  معمولا JSON است ولی در 502/504 ممکن است HTML باشد.
- **KYC:** لازم نیست (برخلاف خود Fragment که کوکی و KYC می‌خواهد).

## مهم‌ترین نکته: endpoint خرید پولی برنمی‌دارد

هر endpoint «خرید/پرداخت» فقط یک تراکنش TON آماده برمی‌گرداند (قالب TON Connect):

```json
{
  "transaction": {
    "validUntil": 1760000000,
    "messages": [
      {"address": "EQ...", "amount": "1234567890", "payload": "te6cc...", "stateInit": null}
    ]
  }
}
```

- `amount` به **nanoton** و از نوع رشته است. `payload` و `stateInit` سلول BOC به base64 هستند (ممکن است
  url-safe باشند).
- خرید فقط وقتی انجام می‌شود که کیف پول ما این پیام‌ها را امضا و به شبکه بفرستد. تا قبل از
  `validUntil` (ثانیه یونیکس) باید فرستاده شود.
- endpoint کلید یکتا (idempotency) ندارد. اگر نتیجه ارسال مبهم بود، **دوباره نفرست**؛ ممکن است دو بار
  خرید شود.

## خدمات Fragment (برای فروش)

همه `POST`. جواب قیمت‌ها: `{"ton": float, "gram": float, "usd": float|null}` به واحد سکه (نه nano).
کتابخانه موجودی سکه اصلی شبکه را «GRAM» می‌نامد و `currency` پیش‌فرض را `"GRAM"` می‌فرستد.

| کار | مسیر | بدنه | جواب |
|---|---|---|---|
| قیمت پرمیوم | `/v1/fragment/premium/price/` | ندارد | `{"months3": P, "months6": P, "months12": P}` |
| بررسی گیرنده پرمیوم | `/v1/fragment/premium/recipient/` | `{"username"}` | `{"name", "photo"}` |
| خرید پرمیوم | `/v1/fragment/premium/buy/` | `{"username", "months": 3\|6\|12, "currency": "GRAM"}` | تراکنش |
| قیمت استارز | `/v1/fragment/stars/price/` | `{"quantity"}` | `P` |
| بررسی گیرنده استارز | `/v1/fragment/stars/recipient/` | `{"username"}` | `{"name", "photo"}` |
| خرید استارز | `/v1/fragment/stars/buy/` | `{"username", "quantity", "currency": "GRAM"}` | تراکنش |
| قیمت گیواوی استارز | `/v1/fragment/stars-giveaway/price/` | ندارد | `{"items": [{ton, gram, usd, stars, boosts}]}` |
| گیرنده گیواوی استارز (کانال) | `/v1/fragment/stars-giveaway/recipient/` | `{"username"}` | `{"name", "photo"}` |
| خرید گیواوی استارز | `/v1/fragment/stars-giveaway/buy/` | `{"username", "quantity": برنده‌ها, "stars"}` | تراکنش |
| قیمت گیواوی پرمیوم | `/v1/fragment/premium-giveaway/price/` | `{"quantity"}` | `{"months3", "months6", "months12", "boosts"}` |
| گیرنده گیواوی پرمیوم | `/v1/fragment/premium-giveaway/recipient/` | `{"username"}` | `{"name", "photo"}` |
| خرید گیواوی پرمیوم | `/v1/fragment/premium-giveaway/buy/` | `{"username", "months", "quantity", "currency": "GRAM"}` | تراکنش |
| گیرنده شارژ حساب تلگرام | `/v1/fragment/telegram-topup/recipient/` | `{"username"}` | `{"name", "photo"}` |
| شارژ حساب تلگرام | `/v1/fragment/telegram-topup/pay/` | `{"username", "amount"}` | تراکنش |
| شارژ حساب تبلیغات (Ads) | `/v1/fragment/ads-topup/pay/` | `{"fragment_link": "https://fragment.com/ads/pay?account=...", "amount"}` | تراکنش |

محدودیت‌ها (از `fragment-api-py` نسخه ۱۲): پرمیوم فقط ۳، ۶ یا ۱۲ ماه؛ استارز حداقل ۵۰؛ شارژ حساب
تلگرام حداقل ۱.

- `photo` در جواب گیرنده ممکن است یک تگ `<img src="...">` باشد، نه لینک خالی.
- گیرنده باید **@username** داشته باشد.
- اگر گیرنده از قبل پرمیوم داشته باشد، endpoint گیرنده خطایی می‌دهد که در متنش `already` یا
  `subscribed` هست. یوزرنیم ناموجود هم خطای 404 یا متن `not found` می‌دهد.

## بازار گیفت، یوزرنیم و شماره (اختیاری)

| کار | مسیر |
|---|---|
| کالکشن‌ها / کالکشن‌های گیفت | `GET /v1/collections/` ، `GET /v1/collections/gifts/` |
| ویژگی‌های یک کالکشن | `GET /v1/collections/{collection}/attributes/` |
| گیفت‌های در فروش | `GET /v1/gifts/onsale/` (فیلتر کالکشن، مدل، سمبل، بک‌دراپ، قیمت؛ صفحه‌بندی با `cursor`) |
| تاریخچه فروش گیفت | `GET /v1/gifts/history/` |
| اطلاعات یک NFT / NFTهای یک مالک / یک کالکشن | `GET /v1/nfts/{address}/` ، `GET /v1/nfts/owner/{owner}/` ، `GET /v1/nfts/collections/{collection}/` |
| خرید NFT | `POST /v1/nfts/buy/` با `{"data": [{"nft_address", "price", "currency"}]}` ← تراکنش |
| فروش، تغییر قیمت، لغو فروش | `POST /v1/nfts/sale/` ، `/v1/nfts/change_price/` ، `/v1/nfts/cancel_sale/` ← تراکنش |
| فروش یا مزایده روی Fragment | `POST /v1/nfts/fragment/sale/` ، `/v1/nfts/fragment/auction/` ← تراکنش |
| اجاره: لیست گیفت، یوزرنیم و شماره قابل اجاره | `GET /v1/rent/gifts/` ، `/v1/rent/usernames/` ، `/v1/rent/numbers/` |
| اجاره کردن / تمدید | `POST /v1/rent/{nft}/pay/` ، `/v1/rent/{nft}/extend/` با `{"duration", "price_per_day"}` ← تراکنش |
| اجاره‌های من | `GET /v1/rent/my-rented/` |
| کد ورود شماره اجاره‌ای | `POST /v1/rent/{nft}/login-code/` ، `/v1/rent/{nft}/toggle-login-code/` |
| وصل کردن NFT اجاره‌ای به Fragment | `POST /v1/rent/{nft}/tonconnect/` با `{"tonconnect_url"}` |
| اجاره دادن / تنظیمات / لغو | `POST /v1/rent/{gifts\|usernames\|numbers}/rent-out/` ، `.../update-settings/` ، `/v1/rent/cancel/` |

در جواب‌های بازار، قیمت‌ها (`floor`، `price`، `min_bid` و ...) رشته nanoton هستند.

## امضا و ارسال تراکنش

کتابخانه و پلاگین تقریبا یک کار می‌کنند:

1. کیف پول از seed (کتابخانه: V4R2 یا V5R1؛ پلاگین: V5R1) و یک ارائه‌دهنده (Toncenter یا TonAPI).
2. (کتابخانه) موجودی ≥ جمع `amount` پیام‌ها + ۰٫۰۱ سکه برای کارمزد؛ وگرنه نفرست.
3. `seqno` فعلی را بخوان و همه پیام‌ها را در **یک** تراکنش بفرست: `payload` به عنوان body و
   `stateInit` به عنوان init. پلاگین `bounce=true` و `send_mode = PAY_GAS_SEPARATELY + IGNORE_ERRORS`
   (یعنی ۳) می‌گذارد.
4. (کتابخانه) تایید: هر ۳ ثانیه تا ۴۰ بار (حدود ۲ دقیقه)، تا `seqno` بالا برود و موجودی کم شود. بالا رفتن
   `seqno` یعنی تراکنش اجرا شد، نه لزوما این که Fragment سفارش را تحویل داد.

## برای ربات عبور

- `app/ton.py` فقط می‌خواند و BOC می‌سازد؛ هش سلول و امضا ندارد. برای امضا یا `tonutils` روی هاست نصب
  شود، یا امضای کیف پول V5R1 (Ed25519) به `app/ton.py` اضافه شود.
- کیف پول خرید باید **جدا** از `TON_RECEIVE_ADDRESS` باشد و موجودی کم داشته باشد، با هشدار کم شدن
  موجودی برای ادمین.
- قبل از امضا: جمع `amount` پیام‌ها نباید از قیمتی که همان لحظه گرفتیم (با کمی تلرانس) بیشتر باشد.
  سرور هر چه API بدهد را امضا می‌کند و این تنها سد جلوی خالی شدن کیف پول است.
- ترتیب سفارش مثل `app/services/numbers_shop.py`: قفل کاربر ← بررسی گیرنده ← قیمت تازه ← موجودی کیف
  پول خرید ← کسر اتمیک ← سفارش `pending` ← گرفتن تراکنش ← امضا و ارسال ← تایید. قطعا نشد → برگشت پول؛
  مبهم → `unknown` و تصمیم ادمین.
- قیمت تومانی = قیمت سکه از API × نرخ TON (`app/services/market.py`) + سود ادمین. چون قیمت TON نوسان
  دارد، سود کمی بیشتر در نظر بگیر.
