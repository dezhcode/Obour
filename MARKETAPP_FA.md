# MarketApp API (مرجع برای خدمات تلگرام)

یادداشت مرجع برای فروش **تلگرام پرمیوم، استارز** و بقیه خدمات Fragment از طریق
[marketapp.org](https://marketapp.org) با پرداخت از کیف پول TON خودمان. در ربات و مینی اپ پیاده شده و
**فعلا خرید نمایشی است** (بخش «پیاده‌سازی در عبور» پایین).

> **منبع‌ها (هیچ‌کدام رسمی نیستند):**
> - کد کامل کتابخانه `marketapp-api` نسخه 1.0.1 روی PyPI (نویسنده S1qwy). مخزن GitHub آن
>   (`s1qwy/marketapp-api`) دیگر عمومی نیست.
> - تاریخچه `S1qwy/fragment-api-py` روی GitHub: نسخه ۱۲ «No-KYC mode» را با همین API ساخته بود و
>   نسخه ۱۳ آن را حذف کرد.
> - پلاگین `marketapp` در `kloveren/morgan-gift-plugins` روی GitHub (بخش گیفت‌ها، با `api.marketapp.ws/v1`).
>
> مستندات رسمی را ندیده‌ایم. بخش Fragment و اجاره با توکن واقعی از روی هاست تست شد (بخش «نتیجه تست
> واقعی» پایین)؛ هنوز هیچ تراکنشی امضا و ارسال نشده. قبل از پروداکشن با یک خرید کوچک (مثلا ۵۰ استارز
> برای خودمان) مسیر پرداخت را هم بسنج.

## نتیجه تست واقعی (۲۰۲۶-۱۰-۱۷، از هاست، پلن رایگان)

- هاست ایران مستقیم به `api.marketapp.org` وصل شد (۴۰ تا ۵۰۰ میلی ثانیه)؛ پروکسی لازم نبود.
- **قیمت‌ها** (TON، در آن لحظه؛ `ton` و `gram` همیشه برابر بودند):

  | محصول | TON | دلار | سهم MarketApp |
  |---|---|---|---|
  | پرمیوم ۳ / ۶ / ۱۲ ماه | 9.0678 / 12.0972 / 21.9402 | 12.23 / 16.31 / 29.57 | ٪۲ |
  | ۵۰ استارز (هر استار ۰٫۰۱۱۳۵ TON) | 0.567732 | 0.765 | ٪۲ |
  | گیواوی ۵۰۰ استارز (۱ برنده) / پرمیوم ۳ ماه (۱ برنده) | 5.70515 / 11.398 | 7.69 / 15.36 | ٪۲٫۵ |
  | شارژ حساب تلگرام ۱ | 1.01 | - | ٪۱ |

- مبلغ تراکنش خرید **دقیقا** برابر قیمت `price/` بود؛ `validUntil` فقط **۱۲۰ ثانیه** بعد است.
- **خطاها** همه `{"detail": "..."}` اند: یوزرنیم ناموجود `400 "User not found."`، ماه نامعتبر
  `400 "invalid months"`، استارز خارج از بازه `400 "50 - 1,000,000"`، توکن اشتباه
  `401 {"detail": "Invalid or expired token. ...", "code": "AUTH_04"}`.
- **پلن رایگان:** همه خدمات Fragment، کالکشن‌ها و اجاره کار کرد. `gifts/onsale`، `gifts/history` و
  `nfts/collections/{c}` جواب `402 "Paid API plan required"` دادند (پس خرید گیفت تست نشد).
- `currency` می‌تواند `GRAM` یا `TON` (یکی‌اند) یا `USDT` باشد.

## تست زنده

از ربات (پیشنهادی): /admin ← تنظیمات ← 💎 خدمات تلگرام ← 🔑 توکن، بعد 🧪 تست کامل API. حدود یک دقیقه
بعد فایل گزارش `.txt` با خلاصه در کپشن در همان چت می‌آید. گیرنده پیش‌فرض یوزرنیم خود ادمین است
(👤 گیرنده تست)؛ برای تست گیواوی 📢 کانال تست را بگذار. اگر هاست به `api.marketapp.org` وصل نشد،
`MARKETAPP_PROXY` را در `.env` بگذار.

از ترمینال هاست:

```bash
python check_marketapp.py --user YOUR_USERNAME [--channel CHANNEL] [--ads LINK] [--json]
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
- **خطا:** `400` با `{"detail": "..."}` برای ورودی یا گیرنده نامعتبر، `401` (`code: AUTH_04`) برای توکن،
  `402` برای endpointهای پلن پولی. بدنه خطا معمولا JSON است ولی در 502/504 ممکن است HTML باشد.
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
  `validUntil` (ثانیه یونیکس، **۱۲۰ ثانیه** بعد از ساخت) باید فرستاده شود.

### شکل payload (از تست واقعی)

**پرداخت با TON** (`currency` = `GRAM` یا `TON`): یک پیام به قرارداد MarketApp
`EQCpwa0v6lvGA01uKGfsW1CK1Nd59aO_xVFGGHPy7JTghHTB`، با `amount` = کل قیمت:

```
op 0x3f2b92d2 (32 بیت) + امضای MarketApp (512 بیت)
└ ref: آدرس پرداخت Fragment + مبلغی که به Fragment می‌رسد (coins) + 1 بیت
  └ ref: کامنت Fragment، مثل "Telegram Premium for 3 months \n\nRef#MbHfpSnEH"
```

قرارداد سهم Fragment را با کامنت به آدرس Fragment می‌فرستد و بقیه (٪۱ تا ٪۲٫۵) را برای خودش نگه می‌دارد.
آدرس‌های Fragment که دیده شد: پرمیوم `EQBAjaOy...la9nE`، استارز `EQCFJEP4...oOoy2`، شارژ حساب `EQBeab7D...l91M`.
سفارش امضای MarketApp را دارد، پس هر کیف پولی می‌تواند آن را بپردازد و تغییرش ممکن نیست.

**پرداخت با USDT**: انتقال جتون استاندارد (`op 0x0f8a7ea5`) از **کیف پول جتون حسابی که توکن مال آن است**
به همان قرارداد MarketApp، با ۰٫۱۵ TON برای کارمزد. مبلغ USDT دقیقا قیمت دلاری است (۵۰ استارز = 0.765
USDT) و `response_destination` آدرس کیف پول آن حساب است. پس پرداخت USDT را فقط همان کیف پولی می‌تواند
امضا کند که با آن در marketapp.org وارد شده‌ای؛ مزیتش این است که قیمت دلاری ثابت است و نوسان TON ندارد.
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

محدودیت‌ها (تست شده): پرمیوم فقط ۳، ۶ یا ۱۲ ماه؛ استارز ۵۰ تا ۱٬۰۰۰٬۰۰۰. گیواوی استارز ۱۳ بسته
ثابت دارد (۵۰۰ تا ۱٬۰۰۰٬۰۰۰ استار). شارژ حساب تلگرام حداقل ۱.

- جواب گیرنده `{"photo": "<img src=\"https://cdn4.telesco.pe/...\">", "name": "..."}` است (`photo` تگ HTML است).
- گیرنده باید **@username** داشته باشد. یوزرنیم ناموجود: `400 {"detail": "User not found."}`.
- رفتار برای گیرنده‌ای که از قبل پرمیوم دارد هنوز دیده نشده.

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

## پیاده‌سازی در عبور (حالت نمایشی)

**کاربر:** مینی اپ ← فروشگاه ← کارت «تلگرام پرمیوم و استارز» (کنار هوش مصنوعی)، یا ربات ← فروشگاه ←
«💎 پرمیوم و استارز تلگرام» (لینک عمیق `start=tg`). مسیر: گیرنده (خودم، گیرنده‌های اخیر یا یوزرنیم) ←
پرمیوم ۳/۶/۱۲ ماه یا استارز (۶ بسته یا تعداد دلخواه ۵۰ تا ۱٬۰۰۰٬۰۰۰) ← تایید ← نتیجه.

**حالت نمایشی یعنی:** قیمت زنده، بررسی گیرنده (اسم و عکس)، قیمت دقیق لحظه تایید و ساخت سفارش واقعی
MarketApp همه انجام می‌شوند و `inspect_tx` روی تراکنش برگشتی اجرا می‌شود؛ فقط امضا و ارسال انجام نمی‌شود،
**هیچ پولی از کیف پول کاربر کم نمی‌شود** و سفارش با `mode='demo'` در جدول `tg_orders` می‌ماند. ربات و
مینی اپ در هر صفحه‌ای که به خرید می‌رسد (ویترین، صفحه بخش، تایید، نتیجه) این را به کاربر می‌گویند.

**راه‌اندازی (ادمین):** تنظیمات ← 💎 خدمات تلگرام ← 🔑 توکن (یا `MARKETAPP_TOKEN` در `.env`)؛ نرخ تتر باید
تنظیم باشد (همان نرخ مشترک). سود: درصد سود (پیش‌فرض ٪۱۵)، حداقل سود (۱۰٬۰۰۰ تومان) و رند (۱٬۰۰۰).
«🧮 پیش‌نمایش قیمت» قیمت زنده دلاری و قیمت کاربر را نشان می‌دهد. بخش را از «بخش‌های ربات»
(`shop_telegram`) هم می‌شود خاموش کرد. بدون توکن یا نرخ تتر، کارت و دکمه پنهان می‌مانند.

**قیمت:** قیمت دلاری MarketApp × نرخ تتر + سود (درصد، با کف سود)، رو به بالا رند. قیمت‌ها ۳ دقیقه کش
می‌شوند؛ صفحه تایید و خود سفارش همیشه قیمت تازه می‌گیرند.

**فایل‌ها:**

- `app/services/marketapp.py`: کلاینت API، قیمت، گیرنده (۱۰ دقیقه کش)، `inspect_tx`، `buy()`، حالت فروش
- `app/handlers/telegram_shop.py`: گفتگوی ربات · `app/handlers/admin.py` (`adm:tgs:*`): پنل ادمین
- `app/webapp/api.py` (`tg`، `tg/recipient`، `tg/quote`، `tg/buy`) و `app/webapp/static/index.html` (`TG`)
- `test_telegram_shop.py`: تست آفلاین با پاسخ‌ها و تراکنش‌های واقعی گزارش هاست (سرویس، گفتگوی ربات با
  Dispatcher واقعی aiogram، اندپوینت‌های مینی اپ)

**برای فروش واقعی (قدم بعد):** امضا و ارسال تراکنش با کیف پول خرید (seed در `.env`، کیف پول V5R1 یا V4R2،
Ed25519) اضافه شود، بعد `LIVE_AVAILABLE` روشن و `tgs_mode=live` شود. مسیر واقعی همان `buy()` است با این
تفاوت‌ها: کسر اتمیک از کیف پول کاربر پیش از ساخت سفارش، `inspect_tx` باید `ok` باشد وگرنه برگشت پول و
لغو، امضا و ارسال، تایید روی زنجیره؛ نتیجه مبهم ← `unknown` و تصمیم ادمین (endpoint کلید یکتا ندارد).

## برای ربات عبور

- `app/ton.py` فقط می‌خواند و BOC می‌سازد؛ هش سلول و امضا ندارد. برای امضا یا `tonutils` روی هاست نصب
  شود، یا امضای کیف پول V5R1 (Ed25519) به `app/ton.py` اضافه شود.
- کیف پول خرید باید **جدا** از `TON_RECEIVE_ADDRESS` باشد و موجودی کم داشته باشد، با هشدار کم شدن
  موجودی برای ادمین.
- قبل از امضا (تنها سد جلوی خالی شدن کیف پول، چون سرور هر چه API بدهد را امضا می‌کند): دقیقا یک پیام؛
  مقصد = قرارداد MarketApp بالا؛ `op 0x3f2b92d2`؛ کامنت داخلش همان محصول باشد ("Telegram Premium for 3
  months" / "50 Telegram Stars")؛ `amount` ≤ قیمتی که همان لحظه گرفتیم. `check_marketapp.py` همین‌ها را
  از payload بیرون می‌کشد.
- ترتیب سفارش مثل `app/services/numbers_shop.py`: قفل کاربر ← بررسی گیرنده ← قیمت تازه ← موجودی کیف
  پول خرید ← کسر اتمیک ← سفارش `pending` ← گرفتن تراکنش ← امضا و ارسال ← تایید. قطعا نشد → برگشت پول؛
  مبهم → `unknown` و تصمیم ادمین.
- قیمت تومانی = قیمت سکه از API × نرخ TON (`app/services/market.py`) + سود ادمین. چون قیمت TON نوسان
  دارد، سود کمی بیشتر در نظر بگیر.
