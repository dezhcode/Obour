# راهنمای دپلوی Obour روی هاست سی پنل

آدرس هدف: `https://dezhcode.pyho.ir/obour`

---

## قبل از شروع: دو نکته که باید بدانی

**۱. دسترسی سرور به تلگرام.**
ربات باید بتواند به `api.telegram.org` وصل شود تا پیام بفرستد. اگر هاست
داخل ایران باشد این آدرس معمولا فیلتر است. وبهوک یک طرفه کار نمی کند:
تلگرام آپدیت را به سرور تو می فرستد (این جهت مشکلی ندارد) ولی جواب دادن
ربات نیاز به اتصال خروجی دارد.

در قدم ۷ با `check_setup.py` این را دقیق تست می کنیم. اگر شکست خورد،
در بخش «اتصال تلگرام» پایین همین فایل راه حل ها آمده.

**۲. جای پوشه اپ.**
پوشه کدها **نباید** داخل `public_html` باشد، وگرنه فایل `.env` با
توکن و پسورد پنل از طریق مرورگر قابل دانلود می شود. در این راهنما پوشه
اپ را `obour_app` می گذاریم که کنار `public_html` است نه داخلش.

---

## قدم ۱: ساخت اپ پایتون در سی پنل

وارد سی پنل شو و برو به **Setup Python App** (زیر بخش Software).
روی **CREATE APPLICATION** بزن و این مقادیر را بگذار:

| فیلد | مقدار |
|---|---|
| Python version | بالاترین نسخه موجود، حداقل `3.10` |
| Application root | `obour_app` |
| Application URL | دامنه `dezhcode.pyho.ir` و در کادر مسیر بنویس `obour` |
| Application startup file | `passenger_wsgi.py` |
| Application entry point | `application` |

**CREATE** را بزن.

بعد از ساخت، بالای همان صفحه یک دستور نمایش داده می شود شبیه این:

```
source /home/USERNAME/virtualenv/obour_app/3.11/bin/activate && cd /home/USERNAME/obour_app
```

این خط را کپی کن و یک جا نگه دار. هر جا در ادامه گفتم «وارد محیط شو»
منظورم اجرای همین دستور است. `USERNAME` و شماره نسخه پایتون مال خودت است.

---

## قدم ۲: آپلود فایل ها

فایل `Obour_cPanel.zip` را در **File Manager** داخل پوشه
`/home/USERNAME/obour_app` آپلود کن و روی آن **Extract** بزن.

بعد از استخراج، ساختار باید این شکلی باشد:

```
obour_app/
├── passenger_wsgi.py      <- نقطه ورود پسنجر
├── main.py
├── requirements.txt
├── .env.example
├── check_setup.py
├── manage_webhook.py
├── cron_tasks.py
├── seed_plans.py
├── restart.sh
├── app/
├── data/                  <- دیتابیس اینجا ساخته می شود
├── logs/                  <- لاگ ها
└── tmp/                   <- سیگنال ری استارت پسنجر
```

اگر فایل `passenger_wsgi.py` از قبل توسط سی پنل ساخته شده بود، با نسخه
داخل زیپ **جایگزینش کن** (Overwrite).

---

## قدم ۳: نصب کتابخانه ها

### راه اول: با ترمینال (توصیه می شود)

از **Terminal** سی پنل یا SSH وارد شو، بعد:

```bash
source /home/USERNAME/virtualenv/obour_app/3.11/bin/activate && cd /home/USERNAME/obour_app
pip install --upgrade pip
pip install -r requirements.txt
```

### راه دوم: بدون ترمینال

اگر ترمینال نداری، در همان صفحه **Setup Python App** روی اپ بزن،
پایین صفحه بخش **Configuration files** را پیدا کن، مقدار
`requirements.txt` را وارد کن، **Add** بزن و بعد دکمه **Run Pip Install**
را بزن.

نصب چند دقیقه طول می کشد. اگر `Pillow` خطا داد، در فایل
`requirements.txt` خط `qrcode[pil]>=7.4` را به `qrcode>=7.4` تغییر بده
(کیو آر کد به جای عکس، متنی نمایش داده می شود).

---

## قدم ۴: ساخت فایل تنظیمات

```bash
cp .env.example .env
chmod 600 .env
```

حالا دو رشته تصادفی بساز:

```bash
python -c "import secrets; print('WEBHOOK_SECRET =', secrets.token_urlsafe(32))"
python -c "import secrets; print('WEBHOOK_PATH   = /tg/' + secrets.token_urlsafe(16))"
```

خروجی را نگه دار. حالا فایل را باز کن:

```bash
nano .env
```

(یا از File Manager روی `.env` راست کلیک و **Edit**. اگر فایل را نمی بینی،
از تنظیمات File Manager گزینه **Show Hidden Files** را روشن کن.)

این مقادیر را پر کن:

```env
BOT_TOKEN=توکنی که BotFather داده
ADMIN_IDS=آیدی عددی خودت از @userinfobot

WEBHOOK_MODE=true
WEBHOOK_BASE_URL=https://dezhcode.pyho.ir/obour
WEBHOOK_PATH=/tg/همان رشته تصادفی دوم
WEBHOOK_SECRET=همان رشته تصادفی اول

PANEL_BASE_URL=https://zerofee.ok-exor.ir
PANEL_USERNAME=salatinvpn
PANEL_PASSWORD=پسورد پنلت
PANEL_GROUP_ID=all
```

با `Ctrl+O` ذخیره و `Ctrl+X` خروج.

> `WEBHOOK_BASE_URL` باید دقیقا شامل `/obour` باشد، چون اپ روی زیرمسیر
> سوار شده. آدرس نهایی وبهوک می شود:
> `https://dezhcode.pyho.ir/obour/tg/<رشته تصادفی>`

---

## قدم ۵: درج پلن ها در دیتابیس

```bash
python seed_plans.py
```

باید شش پلن ثبت شود. دیتابیس در `data/obour.db` ساخته می شود.

---

## قدم ۶: بستن دسترسی وب به فایل های حساس

پوشه اپ بیرون `public_html` است پس در حالت عادی امن است. برای اطمینان
بیشتر:

```bash
chmod 600 .env
chmod 700 data logs
```

---

## قدم ۷: تست کامل قبل از اتصال

```bash
python check_setup.py
```

این اسکریپت همه چیز را چک می کند: کتابخانه ها، تنظیمات، دیتابیس،
اتصال به تلگرام و اتصال به پنل. هر خطی که `[ خطا ]` داشت باید قبل از
ادامه درست شود.

خروجی سالم آخرش می نویسد: `همه چیز آماده است.`

---

## قدم ۸: ری استارت اپ

از صفحه **Setup Python App** دکمه **RESTART** را بزن، یا در ترمینال:

```bash
./restart.sh
```

---

## قدم ۹: تست اینکه اپ زنده است

در مرورگر باز کن:

```
https://dezhcode.pyho.ir/obour/health
```

باید بنویسد `obour: ok`.

اگر خطای ۵۰۰ یا صفحه پسنجر دیدی، برو به بخش «رفع مشکل» پایین.

---

## قدم ۱۰: ثبت وبهوک

```bash
python manage_webhook.py set
```

یا اگر ترمینال نداری، در مرورگر باز کن (به جای `SECRET` مقدار
`WEBHOOK_SECRET` را بگذار):

```
https://dezhcode.pyho.ir/obour/setwebhook?key=SECRET
```

برای دیدن وضعیت:

```bash
python manage_webhook.py info
```

یا در مرورگر: `https://dezhcode.pyho.ir/obour/status?key=SECRET`

در خروجی `pending_updates` باید صفر باشد و `last_error` خالی.

---

## قدم ۱۱: تست ربات

در تلگرام برو سراغ `@ObourNet_bot` و `/start` بزن. منو باید بیاید.

بعد این ها را چک کن:

1. پنل ادمین باز می شود
2. شماره کارت را ثبت کن
3. موجودی خودت را دستی شارژ کن
4. یک پلن ارزان بخر و لینک ساب را در v2rayNG تست کن
5. یک پیام متنی بفرست، باید به پشتیبانی برود و ریپلای ادمین به کاربر برسد

---

## قدم ۱۲: کران جاب ها

روی هاست سی پنل، پسنجر بعد از چند دقیقه بیکاری پروسه را می خواباند.
پس کارهای دوره ای باید با Cron انجام شوند.

برو به **Cron Jobs** در سی پنل و دو تا اضافه کن:

**الف) پاکسازی دوره ای — هر ۱۵ دقیقه** (`*/15 * * * *`):

```
/home/USERNAME/virtualenv/obour_app/3.11/bin/python /home/USERNAME/obour_app/cron_tasks.py --quiet >/dev/null 2>&1
```

**ب) گرم نگه داشتن اپ — هر ۵ دقیقه** (`*/5 * * * *`):

```
curl -s https://dezhcode.pyho.ir/obour/health >/dev/null 2>&1
```

مورد ب باعث می شود پسنجر پروسه را نخواباند و اولین پیام کاربر با تاخیر
چند ثانیه ای مواجه نشود.

مسیر پایتون را از خروجی دستور `which python` داخل محیط مجازی بگیر.

---

# رفع مشکل

## خطای ۵۰۰ روی /health

لاگ خطا را ببین:

```bash
tail -50 ~/logs/dezhcode.pyho.ir.error.log
tail -50 /home/USERNAME/obour_app/logs/obour.log
```

خود اپ هم متن کامل خطا را در پاسخ برمی گرداند اگر ایراد در مرحله
import باشد. علت های رایج:

- کتابخانه ها نصب نشده اند -> قدم ۳ را تکرار کن
- نسخه پایتون زیر ۳.۱۰ است -> اپ را با نسخه بالاتر بساز
- `passenger_wsgi.py` نسخه سی پنل است نه نسخه ما -> جایگزینش کن

## اپ اصلا بالا نمی آید / صفحه پیش فرض می آید

مطمئن شو مسیر Application URL دقیقا `obour` است و در
`public_html/obour` فایل دیگری (مثل `index.html`) نیست که جلوی
پسنجر را بگیرد.

## اتصال تلگرام برقرار نمی شود

اگر `check_setup.py` روی «اتصال به تلگرام» خطا داد، یعنی سرور به
`api.telegram.org` دسترسی ندارد. سه راه:

**۱. پروکسی.** در `.env`:
```env
TG_PROXY=socks5://user:pass@ip:port
```
یا `http://ip:port`. برای socks باید `aiohttp-socks` نصب باشد
(در `requirements.txt` هست).

**۲. آدرس واسط.** اگر یک ریورس پروکسی روی سرور خارج داری:
```env
TG_API_BASE=https://tg-proxy.yourdomain.com
```

**۳. تغییر هاست.** مطمئن ترین راه: هاست خارج از ایران.

بعد از هر تغییر `.env` باید اپ را ری استارت کنی (`./restart.sh`).

## تلگرام آپدیت می فرستد ولی ربات جواب نمی دهد

```bash
python manage_webhook.py info
```

- `last_error` بگوید `SSL error` -> گواهی دامنه معتبر نیست، از سی پنل
  AutoSSL را برای `dezhcode.pyho.ir` اجرا کن.
- `last_error` بگوید `404` یا `Wrong response` -> `WEBHOOK_PATH` در
  `.env` با آدرس ثبت شده فرق دارد. `manage_webhook.py set` را دوباره بزن.
- `pending_updates` عدد بزرگی باشد و بالا برود -> اپ بالا نمی آید،
  لاگ ها را ببین.

## خطای database is locked

یعنی پسنجر چند پروسه همزمان بالا آورده. کد با WAL و busy_timeout این
را تحمل می کند، ولی اگر مکرر شد، در صفحه Setup Python App اپ را ری استارت
کن. اگر ادامه داشت با پشتیبانی هاست تماس بگیر تا
`passenger_max_pool_size` را برای این اپ روی ۱ بگذارند.

## بعد از تغییر کد، تغییرات اعمال نمی شود

```bash
./restart.sh
```

پسنجر کد را کش می کند و فقط با تغییر `tmp/restart.txt` از نو می خواند.

---

# دستورهای پرکاربرد

همه اینها بعد از «وارد محیط شو» اجرا می شوند:

```bash
# ورود به محیط
source /home/USERNAME/virtualenv/obour_app/3.11/bin/activate && cd /home/USERNAME/obour_app

python check_setup.py              # تست کامل نصب
python manage_webhook.py info      # وضعیت وبهوک
python manage_webhook.py set       # ثبت مجدد وبهوک
python manage_webhook.py delete    # حذف وبهوک
python seed_plans.py               # به روزرسانی پلن ها
python cron_tasks.py               # اجرای دستی پاکسازی
./restart.sh                       # ری استارت اپ
tail -f logs/obour.log             # دیدن زنده لاگ
```

---

# پشتیبان گیری

فایل مهم فقط یکی است: `data/obour.db` (کاربران، موجودی ها، سرویس ها).

```bash
cp data/obour.db ~/backup_obour_$(date +%F).db
```

یک کران روزانه هم می توانی بگذاری:

```
0 4 * * * cp /home/USERNAME/obour_app/data/obour.db /home/USERNAME/backups/obour_$(date +\%F).db
```
