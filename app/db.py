"""لایه دیتابیس (SQLite با WAL).

نکات مالی مهم:
- همه تغییرات موجودی اتمیک هستند (UPDATE ... WHERE balance >= ?).
- تراکنش ها idem_key یکتا دارند تا دابل کلیک / آپدیت تکراری تلگرام
  باعث دوبار کسر یا دوبار شارژ نشود (idempotency از فاز ۱).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta

import aiosqlite

from .utils import TZ, now, now_str, slugify_service_name, track_code

log = logging.getLogger("obour.db")


def _ts(value: str | None) -> str:
    """یکسان سازی قالب زمان برای مقایسه رشته ای.

    در نسخه های قبلی بعضی زمان ها با فاصله ("2026-01-01 10:00:00") و
    بعضی ISO ("2026-01-01T10:00:00+03:30") ذخیره شده اند. مقایسه خام این
    دو غلط جواب می دهد، چون کاراکتر T از فاصله بزرگ تر است.
    """
    if not value:
        return ""
    return value.replace(" ", "T")[:19]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_id INTEGER NOT NULL UNIQUE,
  username TEXT,
  first_name TEXT,
  balance INTEGER NOT NULL DEFAULT 0,
  referred_by INTEGER,
  free_trial_used INTEGER NOT NULL DEFAULT 0,
  rules_accepted_at TEXT,
  is_blocked INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  emoji TEXT NOT NULL DEFAULT '📦',
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  data_gb INTEGER NOT NULL,
  duration_days INTEGER NOT NULL,
  price INTEGER NOT NULL,
  panel_template_id INTEGER,
  category_id INTEGER REFERENCES categories(id),
  is_active INTEGER NOT NULL DEFAULT 1,
  badge TEXT
);

CREATE TABLE IF NOT EXISTS services (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  plan_id INTEGER REFERENCES plans(id),
  panel_username TEXT NOT NULL UNIQUE,
  sub_url TEXT NOT NULL,
  label TEXT,
  data_gb INTEGER,
  duration_days INTEGER,
  created_at TEXT NOT NULL,
  expire_at TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  warn_data_at TEXT,        -- زمان ارسال هشدار حجم (یک بار)
  warn_expire_at TEXT,      -- زمان ارسال هشدار انقضا (یک بار)
  winback_at TEXT           -- زمان ارسال پیام برگشت پس از انقضا (یک بار)
);

CREATE TABLE IF NOT EXISTS pending_amounts (
  amount INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  base_amount INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  type TEXT NOT NULL,
  amount INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  receipt_file_id TEXT,
  reject_reason TEXT,
  idem_key TEXT UNIQUE,
  code TEXT,              -- کد پیگیری کوتاه (OB-XXXX)
  created_at TEXT NOT NULL,
  decided_at TEXT,
  decided_by INTEGER,
  paid_at TEXT,           -- زمانی که کاربر گفت واریز کردم
  reminded_at TEXT,       -- زمان ارسال یادآوری (یک بار)
  cancelled_at TEXT       -- اگر کاربر لغو کرد، یادآوری نمی رود
);

CREATE TABLE IF NOT EXISTS discounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  kind TEXT NOT NULL DEFAULT 'percent',   -- percent | fixed
  amount INTEGER NOT NULL,                -- درصد یا مبلغ ثابت
  max_uses INTEGER,                       -- NULL = نامحدود
  used_count INTEGER NOT NULL DEFAULT 0,
  per_user_limit INTEGER NOT NULL DEFAULT 1,
  expires_at TEXT,                        -- NULL = بدون انقضا
  min_amount INTEGER NOT NULL DEFAULT 0,  -- حداقل مبلغ خرید
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discount_uses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  discount_id INTEGER NOT NULL REFERENCES discounts(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  order_amount INTEGER NOT NULL,
  saved INTEGER NOT NULL,
  used_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- نگاشت پیام پشتیبانی ادمین به کاربر.
-- قبلا در حافظه بود؛ روی هاست سی پنل پروسه مرتب ری استارت می شود
-- پس باید در دیتابیس بماند تا پاسخ ادمین گم نشود.
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  direction TEXT NOT NULL,        -- in (از کاربر) | out (پاسخ ادمین)
  body TEXT,                      -- متن پیام
  file_id TEXT,                   -- اگر عکس بود
  admin_id INTEGER,               -- برای پاسخ ها
  is_read INTEGER NOT NULL DEFAULT 0,
  user_msg_id INTEGER,            -- آیدی پیام کاربر، برای ریپلای پاسخ روی آن
  code TEXT,                      -- کد پیگیری، فقط روی ردیف ریشه تیکت
  status TEXT,                    -- open | answered | closed (فقط روی ریشه)
  closed_at TEXT,
  -- شناسه رشته گفتگو. پیام ریشه thread_id = id خودش، و همه پیام های
  -- بعدی (چه کاربر چه پشتیبانی) همان را می گیرند. بدون این، هر پیام
  -- تازه کاربر یک تیکت جدا می شد و فهرست تیکت ها پر از موارد تکراری.
  thread_id INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS support_links (
  admin_id INTEGER NOT NULL,
  message_id INTEGER NOT NULL,
  user_tg_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (admin_id, message_id)
);

-- قفل عملیات مالی. جلوی خرید/تمدید همزمان یک کاربر را می گیرد.
-- در دیتابیس است نه حافظه، چون پسنجر ممکن است چند پروسه بالا بیاورد.
CREATE TABLE IF NOT EXISTS op_locks (
  key TEXT PRIMARY KEY,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- شمارنده نام سرویس هر کاربر. از COUNT(*) استفاده نمی کنیم چون با
-- حذف سرویس یا دو خرید همزمان، نام تکراری می سازد.
CREATE TABLE IF NOT EXISTS service_seq (
  user_id INTEGER PRIMARY KEY,
  last INTEGER NOT NULL DEFAULT 0
);

-- ذخیره وضعیت FSM در دیتابیس (بجای MemoryStorage)
CREATE TABLE IF NOT EXISTS fsm_state (
  key TEXT PRIMARY KEY,
  state TEXT,
  data TEXT NOT NULL DEFAULT '{}',
  updated_at TEXT NOT NULL
);

-- پاداش معرفی. هر ردیف یعنی یک پاداش واریز شده به کیف پول معرف.
-- کلید یکتا روی (txn_id, kind) جلوی واریز دوباره برای یک خرید را
-- می گیرد، حتی اگر هندلر به هر دلیلی دو بار اجرا شود.
CREATE TABLE IF NOT EXISTS referral_earnings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  referrer_id INTEGER NOT NULL REFERENCES users(id),
  invitee_id INTEGER NOT NULL REFERENCES users(id),
  txn_id INTEGER,
  order_amount INTEGER NOT NULL DEFAULT 0,
  reward INTEGER NOT NULL DEFAULT 0,
  kind TEXT NOT NULL DEFAULT 'purchase',
  created_at TEXT NOT NULL,
  UNIQUE(txn_id, kind)
);

-- عکس روزانه مصرف هر سرویس. کرون روزی یک بار عدد تجمعی پنل را
-- می نویسد و اختلاف دو روز = مصرف آن روز. با PRIMARY KEY مرکب،
-- اجرای چندباره کرون در یک روز فقط مقدار را به روز می کند.
CREATE TABLE IF NOT EXISTS usage_daily (
  service_id INTEGER NOT NULL REFERENCES services(id),
  day TEXT NOT NULL,               -- YYYY-MM-DD به وقت تهران
  used_bytes INTEGER NOT NULL,     -- مصرف تجمعی سرویس تا آن لحظه
  data_limit INTEGER,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (service_id, day)
);

-- توجه: ایندکس ستون code این جا ساخته نمی شود. روی دیتابیس های قدیمی
-- این ستون هنوز وجود ندارد و چون SCHEMA قبل از مهاجرت ها اجرا می شود،
-- ساختن ایندکس این جا کل بالا آمدن ربات را با «no such column: code»
-- متوقف می کرد. ساختش به انتهای _migrate منتقل شد.
-- کار ارسال همگانی. چرا در دیتابیس و نه فقط یک تسک در حافظه؟
-- زیر Passenger پروسه بعد از پاسخ دادن به درخواست وبهوک خوابانده
-- می شود و هر تسک پس زمینه ای نصفه می ماند. با ثبت در دیتابیس، ارسال
-- را می شود تکه تکه ادامه داد: هم در همان درخواست تا جایی که وقت هست،
-- هم در هر اجرای کران.
CREATE TABLE IF NOT EXISTS broadcast_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  src_chat_id INTEGER NOT NULL,
  src_message_id INTEGER NOT NULL,
  show_source INTEGER NOT NULL DEFAULT 0,
  pin INTEGER NOT NULL DEFAULT 0,
  markup_json TEXT,
  report_chat_id INTEGER,
  report_message_id INTEGER,
  status TEXT NOT NULL DEFAULT 'active',   -- active | done | failed
  cursor_user_id INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  sent INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0,
  blocked INTEGER NOT NULL DEFAULT 0,
  pinned INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_bc_status ON broadcast_jobs(status, id);

-- نظرسنجی با دکمه های خود ربات (نه نظرسنجی بومی تلگرام).
-- چرا؟ نظرسنجی بومی در پیام همگانی برای هر کاربر یک نسخه جدا می سازد،
-- پس هیچ مجموع مشترکی وجود ندارد. با دکمه های خودمان، رای ها در یک
-- جا جمع می شوند و می شود تفکیک کرد چه کسی چه رایی داده.
CREATE TABLE IF NOT EXISTS polls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  question TEXT NOT NULL,
  layout TEXT NOT NULL DEFAULT 'vertical',   -- vertical | horizontal
  style TEXT,                                 -- رنگ دکمه ها
  show_results INTEGER NOT NULL DEFAULT 1,    -- کاربر بعد از رای نتیجه را ببیند؟
  is_open INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS poll_options (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  poll_id INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
  label TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS poll_votes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  poll_id INTEGER NOT NULL,
  option_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(poll_id, user_id)   -- هر کاربر یک رای؛ تغییر رای جایگزین می شود
);

CREATE INDEX IF NOT EXISTS idx_poll_opt ON poll_options(poll_id, position);
CREATE INDEX IF NOT EXISTS idx_poll_votes ON poll_votes(poll_id, option_id);

-- سفارش های خدمات هوش مصنوعی (واسط warzoneshop).
-- چرا جدول جدا و نه استفاده از services؟ چون ماهیتش فرق دارد: اینجا
-- حجم و انقضا نداریم، بلکه یک یا چند «لینک تحویل» داریم که صادر شده و
-- برگشت ناپذیرند.
--
-- وضعیت ها:
--   pending   پول کسر شده، هنوز به سرویس دهنده نرفته
--   delivered موفق، لینک ها تحویل داده شده
--   failed    قطعا انجام نشد، پول برگشت خورده
--   unknown   پاسخ نگرفتیم؛ ممکن است انجام شده باشد. هرگز خودکار
--             دوباره تلاش یا برگشت نمی خورد - ادمین باید بررسی کند.
CREATE TABLE IF NOT EXISTS ai_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  service_id TEXT NOT NULL,
  title TEXT,
  quantity INTEGER NOT NULL DEFAULT 1,
  usd_cost REAL,
  price INTEGER NOT NULL,              -- مبلغ تومانی کسر شده
  status TEXT NOT NULL DEFAULT 'pending',
  code TEXT,                           -- کد پیگیری AI-xxxxx
  provider_order_id TEXT,
  products TEXT,                       -- لینک های تحویل، JSON
  error TEXT,
  txn_id INTEGER,
  created_at TEXT NOT NULL,
  delivered_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_ai_user ON ai_orders(user_id, id);
CREATE INDEX IF NOT EXISTS idx_ai_status ON ai_orders(status, id);

-- کاربرهایی که خواستند وقتی موجودی برگشت خبردار شوند. خالی شدن
-- موجودی سرویس دهنده یا موجودی خودمان، دیگر باعث خاموش شدن کل بخش
-- نمی شود (که کاربر را گیج می کرد)؛ به جایش این فهرست است.
CREATE TABLE IF NOT EXISTS ai_waitlist (
  user_id INTEGER PRIMARY KEY REFERENCES users(id),
  created_at TEXT NOT NULL
);

-- کانال هایی که ربات در آن ها ادمین است.
-- Bot API هیچ متدی برای «کانال های من» ندارد، پس خودمان ثبت می کنیم:
-- هر بار وضعیت عضویت ربات در یک چت عوض شود، تلگرام رویداد
-- my_chat_member می فرستد و ما همان جا ذخیره می کنیم.
CREATE TABLE IF NOT EXISTS bot_channels (
  chat_id INTEGER PRIMARY KEY,
  title TEXT,
  username TEXT,
  type TEXT,
  can_post INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ref_earn ON referral_earnings(referrer_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ref_invitee ON referral_earnings(invitee_id);
CREATE INDEX IF NOT EXISTS idx_txn_user ON transactions(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_svc_user ON services(user_id);
CREATE INDEX IF NOT EXISTS idx_txn_status ON transactions(status);
CREATE INDEX IF NOT EXISTS idx_svc_expire ON services(expire_at);
CREATE INDEX IF NOT EXISTS idx_users_ref ON users(referred_by);
"""

DEFAULT_SETTINGS = {
    "card_number": "",
    "card_holder": "",
    "bank_name": "",
    "min_charge": "50000",
    "base_gb_rate": "3500",
    "custom_builder_enabled": "0",
    "rules_enabled": "1",
    "rules_text": (
        "♨️ <b>قوانین استفاده از خدمات عبور</b>\n\n"
        "۱. به اطلاعیه هایی که در کانال گذاشته می شود توجه کن.\n\n"
        "۲. اگر قطعی پیش اومد و اطلاعیه ای در کانال نبود، به پشتیبانی پیام بده.\n\n"
        "۳. لینک سرویست رو با پیامک برای کسی نفرست. اگر لازم شد، از ایمیل "
        "یا خود تلگرام استفاده کن.\n\n"
        "۴. سرویس برای استفاده شخصیه. اشتراک گذاری گسترده باعث کندی و "
        "مسدود شدن سرویست می شه."
    ),
}


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._conn is not None:
            return
        # اگر پوشه دیتابیس وجود ندارد، ساخته شود (روی هاست تازه)
        parent = os.path.dirname(os.path.abspath(self.path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        # isolation_level=None یعنی هر دستور خودش commit می شود.
        # لازم است تا BEGIN IMMEDIATE دستی (در next_service_number) خطای
        # «transaction within a transaction» ندهد و تراکنش نیمه باز نماند.
        self._conn = await aiosqlite.connect(self.path, timeout=15, isolation_level=None)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        # اگر پسنجر چند پروسه بالا بیاورد، بجای خطای database is locked صبر می کند
        await self._conn.execute("PRAGMA busy_timeout=10000")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(SCHEMA)
        await self._migrate()
        await self._ensure_code_indexes()
        for key, value in DEFAULT_SETTINGS.items():
            await self._conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value)
            )
        await self._seed_categories()
        await self._seed_service_seq()
        await self._conn.commit()
        log.info("database ready: %s", self.path)

    async def _ensure_code_indexes(self) -> None:
        """ایندکس های ستون code، بعد از اینکه مهاجرت ستون را اضافه کرد.

        این کار عمدا از SCHEMA بیرون کشیده شده: روی یک دیتابیس قدیمی،
        جدول transactions هنوز ستون code ندارد و SCHEMA قبل از مهاجرت ها
        اجرا می شود، پس ساختن ایندکس آن جا خطای «no such column» می داد.
        """
        assert self._conn
        for sql in (
            "CREATE INDEX IF NOT EXISTS idx_txn_code ON transactions(code)",
            "CREATE INDEX IF NOT EXISTS idx_ticket_code ON tickets(code)",
        ):
            try:
                await self._conn.execute(sql)
            except Exception:  # noqa: BLE001
                # نبود ایندکس فقط کمی کندی در جستجوی کد پیگیری است،
                # پس هیچ وقت نباید جلوی بالا آمدن ربات را بگیرد.
                log.warning("ساخت ایندکس ناموفق: %s", sql, exc_info=True)

    async def _seed_service_seq(self) -> None:
        """پر کردن شمارنده نام سرویس برای دیتابیس های قبلی.

        روی نسخه قدیمی نام سرویس از COUNT(*) ساخته می شد. اینجا برای هر
        کاربر بزرگ ترین شماره ای که واقعا استفاده شده پیدا و ثبت می شود
        تا نام جدید با نام های موجود تصادم نکند.
        """
        assert self._conn
        cur = await self._conn.execute("SELECT COUNT(*) FROM service_seq")
        if (await cur.fetchone())[0] > 0:
            return
        cur = await self._conn.execute(
            "SELECT user_id, panel_username FROM services"
        )
        highest: dict[int, int] = {}
        for row in await cur.fetchall():
            uid, name = row[0], (row[1] or "")
            suffix = name.rsplit("_", 1)[-1]
            n = int(suffix) if suffix.isdigit() else 0
            highest[uid] = max(highest.get(uid, 0), n)
        for uid, last in highest.items():
            await self._conn.execute(
                "INSERT OR IGNORE INTO service_seq(user_id, last) VALUES(?, ?)",
                (uid, last),
            )
        if highest:
            log.info("شمارنده نام سرویس برای %s کاربر مقدار گرفت", len(highest))

    async def _migrate(self) -> None:
        """افزودن ستون های جدید به دیتابیس هایی که از قبل ساخته شده اند.

        CREATE TABLE IF NOT EXISTS ستون تازه را اضافه نمی کند، پس روی
        دیتابیس زنده باید صریح ALTER بزنیم. این کار امن و تکرارپذیر است.
        """
        assert self._conn
        migrations = [
            ("services", "label", "ALTER TABLE services ADD COLUMN label TEXT"),
            (
                "users",
                "rules_accepted_at",
                "ALTER TABLE users ADD COLUMN rules_accepted_at TEXT",
            ),
            ("services", "warn_data_at", "ALTER TABLE services ADD COLUMN warn_data_at TEXT"),
            (
                "services",
                "warn_expire_at",
                "ALTER TABLE services ADD COLUMN warn_expire_at TEXT",
            ),
            ("services", "winback_at", "ALTER TABLE services ADD COLUMN winback_at TEXT"),
            (
                "tickets",
                "user_msg_id",
                "ALTER TABLE tickets ADD COLUMN user_msg_id INTEGER",
            ),
            (
                "plans",
                "category_id",
                "ALTER TABLE plans ADD COLUMN category_id INTEGER REFERENCES categories(id)",
            ),
            ("transactions", "paid_at", "ALTER TABLE transactions ADD COLUMN paid_at TEXT"),
            (
                "transactions",
                "reminded_at",
                "ALTER TABLE transactions ADD COLUMN reminded_at TEXT",
            ),
            (
                "transactions",
                "cancelled_at",
                "ALTER TABLE transactions ADD COLUMN cancelled_at TEXT",
            ),
            ("transactions", "code", "ALTER TABLE transactions ADD COLUMN code TEXT"),
            ("tickets", "code", "ALTER TABLE tickets ADD COLUMN code TEXT"),
            ("tickets", "status", "ALTER TABLE tickets ADD COLUMN status TEXT"),
            ("tickets", "closed_at", "ALTER TABLE tickets ADD COLUMN closed_at TEXT"),
            ("tickets", "thread_id", "ALTER TABLE tickets ADD COLUMN thread_id INTEGER"),
        ]
        for table, column, sql in migrations:
            cur = await self._conn.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in await cur.fetchall()}
            if column not in existing:
                await self._conn.execute(sql)
                log.info("مهاجرت انجام شد: %s.%s اضافه شد", table, column)
                # کاربران موجود قبل از افزودن قوانین، تایید شده فرض می شوند
                # تا دفعه بعد با صفحه قوانین غافلگیر نشوند.
                # ردیف های قدیمی هم کد پیگیری بگیرند، وگرنه کاربر برای
                # خرید دیروزش کدی ندارد و /track جواب نمی دهد.
                if (table, column) == ("transactions", "code"):
                    await self._conn.execute(
                        "UPDATE transactions SET code = 'OB-' || "
                        "printf('%04X', id) WHERE code IS NULL"
                    )
                if (table, column) == ("tickets", "code"):
                    await self._conn.execute(
                        "UPDATE tickets SET code = 'TK-' || printf('%04X', id) "
                        "WHERE code IS NULL AND direction = 'in'"
                    )
                if (table, column) == ("tickets", "thread_id"):
                    # گذشته را با همان منطق قدیمی (خطی) رشته بندی می کنیم:
                    # هر پیام به آخرین تیکت «in» قبل از خودش تعلق دارد.
                    await self._conn.execute(
                        """UPDATE tickets SET thread_id = CASE
                             WHEN direction = 'in' THEN id
                             ELSE COALESCE((SELECT MAX(p.id) FROM tickets p
                                            WHERE p.user_id = tickets.user_id
                                              AND p.direction = 'in'
                                              AND p.id < tickets.id), id)
                           END
                           WHERE thread_id IS NULL"""
                    )
                    log.info("رشته گفتگوی تیکت های قدیمی ساخته شد")
                if (table, column) == ("tickets", "status"):
                    # تیکت های قدیمی که پاسخ گرفته اند باز نمانند
                    await self._conn.execute(
                        """UPDATE tickets SET status = CASE
                               WHEN EXISTS (SELECT 1 FROM tickets t2
                                            WHERE t2.user_id = tickets.user_id
                                              AND t2.direction = 'out'
                                              AND t2.id > tickets.id)
                               THEN 'answered' ELSE 'open' END
                           WHERE status IS NULL AND direction = 'in'"""
                    )
                if (table, column) == ("users", "rules_accepted_at"):
                    await self._conn.execute(
                        "UPDATE users SET rules_accepted_at = ? "
                        "WHERE rules_accepted_at IS NULL",
                        (now_str(),),
                    )
                    log.info("کاربران موجود به عنوان تاییدکرده علامت خوردند")
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()

    async def execute(self, sql: str, params: tuple = ()) -> int:
        """execute + commit؛ مقدار برگشتی rowcount."""
        async with self._lock:
            assert self._conn
            cur = await self._conn.execute(sql, params)
            await self._conn.commit()
            return cur.rowcount

    async def insert(self, sql: str, params: tuple = ()) -> int:
        """درج یک ردیف و برگرداندن آیدی آن.

        قبلا بعضی جاها بعد از insert با ORDER BY id DESC LIMIT 1 آیدی
        خوانده می شد که در همزمانی آیدی ردیف کس دیگری را برمی گرداند.
        """
        async with self._lock:
            assert self._conn
            cur = await self._conn.execute(sql, params)
            await self._conn.commit()
            return int(cur.lastrowid or 0)

    async def fetchone(self, sql: str, params: tuple = ()):  # noqa: ANN201
        async with self._lock:
            assert self._conn
            cur = await self._conn.execute(sql, params)
            return await cur.fetchone()

    async def fetchall(self, sql: str, params: tuple = ()) -> list:  # noqa: ANN201
        async with self._lock:
            assert self._conn
            cur = await self._conn.execute(sql, params)
            return await cur.fetchall()

    # ---------- کاربران ----------
    async def get_or_create_user(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        referred_by: int | None = None,
    ) -> dict:
        await self.execute(
            """INSERT OR IGNORE INTO users(telegram_id, username, first_name, referred_by, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (telegram_id, username, first_name, referred_by, now_str()),
        )
        row = await self.fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        changed = row is not None and (
            (row["username"] or None) != (username or None)
            or (row["first_name"] or None) != (first_name or None)
        )
        if changed:
            await self.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?",
                (username, first_name, telegram_id),
            )
            row = await self.fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return dict(row)

    async def get_user_by_tg(self, telegram_id: int) -> dict | None:
        row = await self.fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return dict(row) if row else None

    async def get_user(self, user_id: int) -> dict | None:
        row = await self.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        return dict(row) if row else None

    # ---------- قفل عملیات (ضد دابل کلیک و خرید همزمان) ----------
    async def acquire_lock(self, key: str, ttl_seconds: int = 180) -> bool:
        """گرفتن قفل. False یعنی همین حالا یک عملیات دیگر در جریان است.

        چرا در دیتابیس؟ چون روی هاست سی پنل ممکن است چند پروسه بالا باشد
        و قفل در حافظه هر پروسه بی اثر می شود. TTL دارد تا اگر پروسه وسط
        کار کشته شد، کاربر برای همیشه قفل نماند.
        """
        await self.execute("DELETE FROM op_locks WHERE expires_at < ?", (now_str(),))
        expires = (datetime.now(TZ) + timedelta(seconds=ttl_seconds)).isoformat(
            timespec="seconds"
        )
        try:
            async with self._lock:
                assert self._conn
                await self._conn.execute(
                    "INSERT INTO op_locks(key, expires_at, created_at) VALUES(?, ?, ?)",
                    (key, expires, now_str()),
                )
                await self._conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def release_lock(self, key: str) -> None:
        await self.execute("DELETE FROM op_locks WHERE key = ?", (key,))

    # ---------- عملیات اتمیک مالی ----------
    async def atomic_debit(self, user_id: int, amount: int) -> bool:
        """کسر اتمیک؛ False یعنی موجودی کافی نبود.

        مبلغ منفی یا صفر رد می شود تا یک باگ بالادستی نتواند با کسر
        منفی، موجودی کاربر را زیاد کند.
        """
        if amount <= 0:
            return False
        rc = await self.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ? AND balance >= ?",
            (amount, user_id, amount),
        )
        return rc == 1

    async def atomic_credit(self, user_id: int, amount: int) -> bool:
        if amount <= 0:
            return False
        rc = await self.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id)
        )
        return rc == 1

    # ---------- تراکنش ها ----------
    async def insert_transaction(
        self,
        user_id: int,
        type_: str,
        amount: int,
        status: str = "pending",
        receipt_file_id: str | None = None,
        idem_key: str | None = None,
    ) -> int | None:
        """idem_key تکراری -> None (یعنی قبلا پردازش شده)."""
        try:
            txn_id = await self.insert(
                """INSERT INTO transactions(user_id, type, amount, status, receipt_file_id, idem_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, type_, amount, status, receipt_file_id, idem_key, now_str()),
            )
        except aiosqlite.IntegrityError:
            return None
        # کد پیگیری بعد از درج ساخته می شود چون از روی آیدی ردیف است؛
        # این طور یکتایی بدون قفل و بدون حلقه تلاش مجدد تضمین می شود.
        await self.execute(
            "UPDATE transactions SET code = ? WHERE id = ?",
            (track_code("OB", txn_id), txn_id),
        )
        return txn_id

    async def transaction_by_code(self, code: str) -> dict | None:
        row = await self.fetchone(
            "SELECT * FROM transactions WHERE code = ?", (code,)
        )
        return dict(row) if row else None

    async def charge_queue_position(self, txn_id: int) -> int:
        """چند درخواست شارژ زودتر از این یکی در صف بررسی است.

        فقط آن هایی شمرده می شوند که رسید فرستاده اند، چون همان ها
        واقعا روی میز ادمین هستند.
        """
        row = await self.fetchone(
            """SELECT COUNT(*) AS n FROM transactions
               WHERE type = 'charge' AND status = 'pending'
                 AND receipt_file_id IS NOT NULL AND id < ?""",
            (txn_id,),
        )
        return (row["n"] if row else 0) + 1

    async def fail_transaction(self, txn_id: int, reason: str) -> None:
        """علامت زدن تراکنش ناموفق.

        قبلا ردیف با DELETE پاک می شد. حذف کردن سابقه مالی درست نیست:
        هم ردپای حسابداری از بین می رود و هم دیگر نمی توان فهمید چند بار
        و با چه خطایی خرید شکست خورده.
        """
        await self.execute(
            """UPDATE transactions
               SET status = 'failed', decided_at = ?, reject_reason = ?
               WHERE id = ? AND status = 'pending'""",
            (now_str(), reason[:200], txn_id),
        )

    async def approve_purchase(self, txn_id: int) -> bool:
        """قطعی کردن خرید. اتمیک از حالت pending."""
        rc = await self.execute(
            """UPDATE transactions SET status = 'approved', decided_at = ?
               WHERE id = ? AND status = 'pending'""",
            (now_str(), txn_id),
        )
        return rc == 1

    async def get_transaction(self, txn_id: int) -> dict | None:
        row = await self.fetchone("SELECT * FROM transactions WHERE id = ?", (txn_id,))
        return dict(row) if row else None

    async def decide_transaction(
        self, txn_id: int, status: str, admin_id: int, reason: str | None = None
    ) -> dict | None:
        """تغییر وضعیت اتمیک از pending (ضد تایید دوباره)."""
        rc = await self.execute(
            """UPDATE transactions
               SET status = ?, decided_at = ?, decided_by = ?, reject_reason = ?
               WHERE id = ? AND status = 'pending'""",
            (status, now_str(), admin_id, reason, txn_id),
        )
        if rc != 1:
            return None
        txn = await self.get_transaction(txn_id)
        # آزادسازی مبلغ رزرو شده تا دوباره قابل استفاده باشد
        if txn and txn["type"] == "charge":
            await self.release_amount(txn["amount"])
        return txn

    async def set_receipt(self, txn_id: int, file_id: str) -> None:
        await self.execute(
            "UPDATE transactions SET receipt_file_id = ? WHERE id = ?", (file_id, txn_id)
        )

    async def pending_charges(self, limit: int = 20) -> list[dict]:
        rows = await self.fetchall(
            """SELECT t.*, u.first_name, u.username, u.telegram_id, u.balance
               FROM transactions t JOIN users u ON u.id = t.user_id
               WHERE t.type = 'charge' AND t.status = 'pending' AND t.receipt_file_id IS NOT NULL
               ORDER BY t.id DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in rows]

    async def user_transactions(
        self,
        user_id: int,
        limit: int = 10,
        offset: int = 0,
        kind: str | None = None,
    ) -> list[dict]:
        """سوابق مالی کاربر. kind: charge | purchase | referral | None (همه)."""
        sql = "SELECT * FROM transactions WHERE user_id = ?"
        params: list = [user_id]
        if kind:
            sql += " AND type = ?"
            params.append(kind)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = await self.fetchall(sql, tuple(params))
        return [dict(r) for r in rows]

    async def count_transactions(self, user_id: int, kind: str | None = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM transactions WHERE user_id = ?"
        params: list = [user_id]
        if kind:
            sql += " AND type = ?"
            params.append(kind)
        row = await self.fetchone(sql, tuple(params))
        return row["n"] if row else 0

    # ---------- پلن ها ----------
    async def active_plans(self, category_id: int | None = None) -> list[dict]:
        """پلن های فعال. با category_id فقط یک دسته برمی گردد."""
        if category_id is not None:
            rows = await self.fetchall(
                """SELECT * FROM plans WHERE is_active = 1 AND category_id = ?
                   ORDER BY data_gb""",
                (category_id,),
            )
        else:
            rows = await self.fetchall(
                """SELECT p.* FROM plans p
                   LEFT JOIN categories c ON c.id = p.category_id
                   WHERE p.is_active = 1
                   ORDER BY COALESCE(c.sort_order, 999), p.data_gb"""
            )
        return [dict(r) for r in rows]

    async def shop_categories(self) -> list[dict]:
        """دسته های فعالی که حداقل یک پلن فعال دارند (برای فروشگاه)."""
        rows = await self.fetchall(
            """SELECT c.*, COUNT(p.id) AS n
               FROM categories c
               JOIN plans p ON p.category_id = c.id AND p.is_active = 1
               WHERE c.is_active = 1
               GROUP BY c.id
               HAVING n > 0
               ORDER BY c.sort_order, c.id"""
        )
        return [dict(r) for r in rows]

    async def all_plans(self) -> list[dict]:
        rows = await self.fetchall("SELECT * FROM plans ORDER BY data_gb")
        return [dict(r) for r in rows]

    async def get_plan(self, plan_id: int) -> dict | None:
        row = await self.fetchone("SELECT * FROM plans WHERE id = ?", (plan_id,))
        return dict(row) if row else None

    async def update_plan(self, plan_id: int, **fields) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        await self.execute(f"UPDATE plans SET {sets} WHERE id = ?", (*fields.values(), plan_id))

    # ---------- سرویس ها ----------
    async def next_service_number(self, user_id: int) -> int:
        """شماره بعدی سرویس کاربر - اتمیک و بدون تکرار.

        نسخه قبلی COUNT(*) بود. اگر کاربر دو خرید همزمان می کرد یا سرویسی
        حذف می شد، دو سرویس نام یکسان می گرفتند: یا پنل درخواست دوم را رد
        می کرد، یا بدتر، پول کسر می شد و insert روی قید UNIQUE می افتاد.
        """
        async with self._lock:
            assert self._conn
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                await self._conn.execute(
                    "INSERT OR IGNORE INTO service_seq(user_id, last) VALUES(?, 0)",
                    (user_id,),
                )
                await self._conn.execute(
                    "UPDATE service_seq SET last = last + 1 WHERE user_id = ?",
                    (user_id,),
                )
                cur = await self._conn.execute(
                    "SELECT last FROM service_seq WHERE user_id = ?", (user_id,)
                )
                row = await cur.fetchone()
                await self._conn.commit()
            except Exception:
                await self._conn.rollback()
                raise
        return int(row[0]) if row else 1

    async def free_panel_username(
        self,
        user_tg_id: int,
        user_id: int,
        desired: str = "",
        taken=None,  # noqa: ANN001
        exclude: set[str] | None = None,
    ) -> str:
        """ساخت نام یکتا برای سرویس روی پنل.

        اگر کاربر اسمی انتخاب کرده باشد، همان (بعد از تبدیل به لاتین)
        مبنا قرار می گیرد و فقط در صورت تکراری بودن عدد می گیرد. اگر
        اسمی نداده باشد یا اسمش قابل تبدیل نباشد (مثلا فقط ایموجی)،
        به الگوی قدیمی obour_<آیدی>_<شماره> برمی گردیم.

        `exclude` نام هایی است که پنل هنگام ساخت واقعا ردشان کرده (۴۰۹).
        این ها حتی اگر بررسی GET بگوید آزادند، دوباره پیشنهاد نمی شوند.

        اگر `taken` داده شود (معمولا panel.username_taken)، نام روی پنل
        هم بررسی می شود. این لازم است چون پنل ممکن است سرویس هایی داشته
        باشد که در دیتابیس ربات نیستند - مثلا وقتی دیتابیس از نو ساخته
        شده ولی پنل سر جایش مانده. بدون این بررسی، ساخت با ۴۰۹ شکست
        می خورد.
        """

        blocked = {n.lower() for n in (exclude or ())}

        async def _free(name: str) -> bool:
            # نامی که پنل قبلا با ۴۰۹ ردش کرده دوباره امتحان نمی شود.
            # بدون این، وقتی GET پنل بگوید «نیست» ولی POST بگوید
            # «تکراری» (مثلا چون یکتایی پنل به بزرگی و کوچکی حروف حساس
            # نیست، یا کاربر حذف شده هنوز در ایندکس مانده)، حلقه تلاش
            # مجدد همان نام را بی نهایت بار امتحان می کند و خرید شکست
            # می خورد - دقیقا باگی که در لاگ دیده شد.
            if name.lower() in blocked:
                return False
            row = await self.fetchone(
                "SELECT 1 FROM services WHERE panel_username = ? COLLATE NOCASE",
                (name,),
            )
            if row is not None:
                return False
            if taken is not None and await taken(name):
                log.warning("نام %s روی پنل وجود دارد، نام بعدی", name)
                return False
            return True

        slug = slugify_service_name(desired) if desired else ""
        if len(slug) >= 3:
            for attempt in range(1, 30):
                name = slug if attempt == 1 else f"{slug}_{attempt}"
                if await _free(name):
                    return name
            log.warning("نام دلخواه %s آزاد نبود، به نام خودکار برمی گردیم", slug)

        for _ in range(50):
            number = await self.next_service_number(user_id)
            name = f"obour_{user_tg_id}_{number}"
            if await _free(name):
                return name
        raise RuntimeError("نام آزاد برای سرویس پیدا نشد")

    async def insert_service(
        self,
        user_id: int,
        plan_id: int | None,
        panel_username: str,
        sub_url: str,
        data_gb: int,
        duration_days: int,
        expire_at: str,
    ) -> int:
        return await self.insert(
            """INSERT INTO services(user_id, plan_id, panel_username, sub_url, data_gb, duration_days, created_at, expire_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, plan_id, panel_username, sub_url, data_gb, duration_days, now_str(), expire_at),
        )

    async def user_services(self, user_id: int) -> list[dict]:
        """سرویس های کاربر. حذف شده ها (is_active=0) نمایش داده نمی شوند."""
        rows = await self.fetchall(
            "SELECT * FROM services WHERE user_id = ? AND is_active = 1 ORDER BY id",
            (user_id,),
        )
        return [dict(r) for r in rows]

    async def delete_service(self, service_id: int, user_id: int) -> bool:
        """حذف نرم سرویس (فقط از دید کاربر).

        ردیف پاک نمی شود چون به تراکنش خرید گره خورده و پاک کردنش
        گزارش مالی را خراب می کند. فقط is_active صفر می شود تا از لیست
        کاربر برود. شرط user_id هم هست تا کسی سرویس دیگری را حذف نکند.
        """
        rc = await self.execute(
            "UPDATE services SET is_active = 0 WHERE id = ? AND user_id = ? AND is_active = 1",
            (service_id, user_id),
        )
        return rc == 1

    async def get_service(self, service_id: int) -> dict | None:
        row = await self.fetchone("SELECT * FROM services WHERE id = ?", (service_id,))
        return dict(row) if row else None

    async def reset_service_warnings(self, service_id: int) -> None:
        """صفر کردن نشانه های هشدار بعد از تمدید.

        بدون این کار، سرویس تمدید شده دیگر هیچ وقت هشدار حجم یا انقضا
        نمی گیرد چون قبلا یک بار گرفته است.
        """
        await self.execute(
            """UPDATE services
               SET warn_data_at = NULL, warn_expire_at = NULL, winback_at = NULL
               WHERE id = ?""",
            (service_id,),
        )

    async def update_service_sub(self, service_id: int, sub_url: str) -> None:
        """ثبت لینک ساب تازه بعد از ابطال لینک قبلی."""
        await self.execute(
            "UPDATE services SET sub_url = ? WHERE id = ?", (sub_url, service_id)
        )

    async def update_service_expire(self, service_id: int, expire_at: str) -> None:
        await self.execute(
            "UPDATE services SET expire_at = ?, is_active = 1 WHERE id = ?",
            (expire_at, service_id),
        )

    # ---------- تنظیمات ----------
    # ---------- هشدارها و برگشت مشتری ----------
    async def services_for_expiry_warning(self, days: int = 3) -> list[dict]:
        """سرویس های فعالی که تا N روز دیگر منقضی می شوند و هشدار نگرفته اند."""
        now = datetime.now(TZ)
        soon = (now + timedelta(days=days)).isoformat(timespec="seconds")
        rows = await self.fetchall(
            """SELECT s.*, u.telegram_id, u.first_name
               FROM services s JOIN users u ON u.id = s.user_id
               WHERE s.is_active = 1
                 AND s.warn_expire_at IS NULL
                 AND s.expire_at > ? AND s.expire_at <= ?
                 AND u.is_blocked = 0""",
            (now.isoformat(timespec="seconds"), soon),
        )
        return [dict(r) for r in rows]

    async def active_services_for_check(self) -> list[dict]:
        """سرویس های فعالی که هنوز هشدار حجم نگرفته اند (برای بررسی مصرف)."""
        rows = await self.fetchall(
            """SELECT s.*, u.telegram_id, u.first_name
               FROM services s JOIN users u ON u.id = s.user_id
               WHERE s.is_active = 1
                 AND s.warn_data_at IS NULL
                 AND s.data_gb > 0
                 AND s.expire_at > ?
                 AND u.is_blocked = 0""",
            (now_str(),),
        )
        return [dict(r) for r in rows]

    async def services_for_winback(self, days_after: int = 2) -> list[dict]:
        """سرویس های منقضی شده که کاربرش سرویس فعال دیگری ندارد.

        فقط کسانی که واقعا رفته اند پیام می گیرند، نه کسی که سرویس
        دیگری دارد یا همین حالا تمدید کرده.
        """
        now = datetime.now(TZ)
        cutoff = (now - timedelta(days=days_after)).isoformat(timespec="seconds")
        rows = await self.fetchall(
            """SELECT s.*, u.telegram_id, u.first_name
               FROM services s JOIN users u ON u.id = s.user_id
               WHERE s.winback_at IS NULL
                 AND s.expire_at <= ?
                 AND u.is_blocked = 0
                 AND NOT EXISTS (
                       SELECT 1 FROM services s2
                       WHERE s2.user_id = s.user_id AND s2.expire_at > ?
                 )
               GROUP BY s.user_id""",
            (cutoff, now.isoformat(timespec="seconds")),
        )
        return [dict(r) for r in rows]

    async def mark_warned(self, service_id: int, field: str) -> None:
        if field not in ("warn_data_at", "warn_expire_at", "winback_at"):
            return
        await self.execute(
            f"UPDATE services SET {field} = ? WHERE id = ?", (now_str(), service_id)
        )

    # ---------- تیکت پشتیبانی ----------
    async def open_thread(self, user_id: int) -> dict | None:
        """تیکت بازِ کاربر (اگر باشد).

        «باز» یعنی وضعیتش open یا answered است - یعنی هنوز بسته نشده.
        تا وقتی چنین تیکتی هست، پیام های تازه کاربر به همان می چسبند.
        """
        # مهم: فقط ردیف های *ریشه* حساب می شوند. پیام های بعدی کاربر
        # داخل یک رشته، status ندارند و اگر این شرط نباشد، COALESCE
        # آن ها را «باز» می بیند و رشته بعدی به خودِ آن پیام می چسبد -
        # یعنی زنجیره می شکند و باز هم تیکت های جدا ساخته می شود.
        row = await self.fetchone(
            """SELECT * FROM tickets
               WHERE user_id = ? AND direction = 'in'
                 AND COALESCE(thread_id, id) = id
                 AND COALESCE(status, 'open') IN ('open', 'answered')
               ORDER BY id DESC LIMIT 1""",
            (user_id,),
        )
        return dict(row) if row else None

    async def add_ticket(
        self,
        user_id: int,
        direction: str,
        body: str | None = None,
        file_id: str | None = None,
        admin_id: int | None = None,
        user_msg_id: int | None = None,
        thread_id: int | None = None,
        force_new: bool = False,
    ) -> tuple[int, int, bool]:
        """ثبت یک پیام تیکت.

        خروجی: (شناسه پیام، شناسه رشته گفتگو، آیا تیکت تازه باز شد؟)

        رفتار تازه: پیام کاربر اگر تیکت بازی داشته باشد به **همان**
        می چسبد، نه اینکه تیکت جدید بسازد. فقط وقتی تیکتی باز نباشد
        (یا force_new داده شود) رشته تازه ساخته می شود. قبلا هر پیام
        یک تیکت جدا می شد و فهرست تیکت ها بی معنی می شد.
        """
        is_new = False
        if direction == "in" and thread_id is None and not force_new:
            current = await self.open_thread(user_id)
            if current:
                thread_id = int(current["id"])

        ticket_id = await self.insert(
            """INSERT INTO tickets
               (user_id, direction, body, file_id, admin_id, user_msg_id,
                status, thread_id, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                direction,
                body,
                file_id,
                admin_id,
                user_msg_id,
                # وضعیت فقط روی ریشه رشته نگهداری می شود
                "open" if (direction == "in" and thread_id is None) else None,
                thread_id,
                now_str(),
            ),
        )

        if thread_id is None:
            # این پیام خودش ریشه است
            thread_id = ticket_id
            await self.execute(
                "UPDATE tickets SET thread_id = ?, code = ? WHERE id = ?",
                (ticket_id, track_code("TK", ticket_id), ticket_id),
            )
            is_new = direction == "in"
        elif direction == "in":
            # کاربر دوباره پیام داد: تیکت از «پاسخ داده شده» به «باز»
            # برمی گردد تا در فهرست ادمین دیده شود
            await self.execute(
                "UPDATE tickets SET status = 'open' WHERE id = ? AND status = 'answered'",
                (thread_id,),
            )
        return ticket_id, thread_id, is_new

    # ---------- وضعیت و پیگیری تیکت ----------
    async def ticket_threads(self, user_id: int, limit: int = 10) -> list[dict]:
        """فهرست تیکت های کاربر (فقط پیام های خودش) با تعداد پاسخ ها.

        پاسخ هایی به یک تیکت نسبت داده می شوند که بعد از آن و قبل از
        تیکت بعدی ثبت شده اند؛ مدل گفتگو در این ربات خطی است.
        """
        rows = await self.fetchall(
            """SELECT t.*,
                      (SELECT COUNT(*) FROM tickets r
                        WHERE COALESCE(r.thread_id, r.id) = t.id
                          AND r.direction = 'out') AS replies,
                      (SELECT MAX(r.created_at) FROM tickets r
                        WHERE COALESCE(r.thread_id, r.id) = t.id) AS last_at
               FROM tickets t
               WHERE t.user_id = ? AND t.direction = 'in'
                 AND COALESCE(t.thread_id, t.id) = t.id
               ORDER BY t.id DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(r) for r in rows]

    async def ticket_code(self, ticket_id: int) -> str | None:
        row = await self.fetchone("SELECT code FROM tickets WHERE id = ?", (ticket_id,))
        return row["code"] if row else None

    async def ticket_by_code(self, code: str) -> dict | None:
        """تیکت با کد پیگیری، به همراه آیدی تلگرام صاحبش.

        آیدی تلگرام لازم است تا ادمین بتواند مستقیم روی صفحه پیگیری
        ریپلای کند و جواب به همان کاربر برسد.
        """
        row = await self.fetchone(
            """SELECT t.*, u.telegram_id AS user_tg_id
               FROM tickets t JOIN users u ON u.id = t.user_id
               WHERE t.code = ? AND t.direction = 'in'""",
            (code,),
        )
        return dict(row) if row else None

    async def ticket_messages(self, ticket_id: int, user_id: int) -> list[dict]:
        """همه پیام های یک رشته گفتگو، به ترتیب زمان.

        حالا مستقیم از thread_id خوانده می شود، نه از حدس «هر چه بین
        این تیکت و تیکت بعدی است» - که با چسبیدن پیام ها به یک رشته
        دیگر درست کار نمی کرد.
        """
        rows = await self.fetchall(
            """SELECT * FROM tickets
               WHERE user_id = ? AND COALESCE(thread_id, id) = ?
               ORDER BY id""",
            (user_id, ticket_id),
        )
        return [dict(r) for r in rows]

    async def set_ticket_status(self, ticket_id: int, status: str) -> None:
        await self.execute(
            "UPDATE tickets SET status = ?, closed_at = ? WHERE id = ?",
            (status, now_str() if status == "closed" else None, ticket_id),
        )

    async def close_ticket(self, ticket_id: int, user_id: int) -> bool:
        """بستن تیکت توسط کاربر. مالکیت هم بررسی می شود."""
        n = await self.execute(
            """UPDATE tickets SET status = 'closed', closed_at = ?
               WHERE id = ? AND user_id = ? AND direction = 'in'
                 AND COALESCE(status, 'open') != 'closed'""",
            (now_str(), ticket_id, user_id),
        )
        return n > 0

    # ---------- پیگیری مصرف ----------
    async def record_usage(
        self, service_id: int, day: str, used_bytes: int, data_limit: int | None
    ) -> None:
        """ثبت عکس روزانه مصرف. اجرای دوباره در همان روز فقط به روزرسانی است."""
        await self.execute(
            """INSERT INTO usage_daily(service_id, day, used_bytes, data_limit, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(service_id, day) DO UPDATE SET
                   used_bytes = excluded.used_bytes,
                   data_limit = excluded.data_limit,
                   updated_at = excluded.updated_at""",
            (service_id, day, int(used_bytes), data_limit, now_str()),
        )

    async def usage_history(self, service_id: int, days: int = 8) -> list[dict]:
        """آخرین عکس های مصرف، از قدیم به جدید."""
        rows = await self.fetchall(
            """SELECT day, used_bytes, data_limit FROM usage_daily
               WHERE service_id = ? ORDER BY day DESC LIMIT ?""",
            (service_id, days),
        )
        return [dict(r) for r in reversed(rows)]

    async def last_user_msg_id(self, user_id: int) -> int | None:
        """آیدی آخرین پیام کاربر در پشتیبانی، برای ریپلای پاسخ روی آن."""
        row = await self.fetchone(
            """SELECT user_msg_id FROM tickets
               WHERE user_id = ? AND direction = 'in' AND user_msg_id IS NOT NULL
               ORDER BY id DESC LIMIT 1""",
            (user_id,),
        )
        return row["user_msg_id"] if row else None

    async def recent_ticket_history(
        self, user_id: int, limit: int = 6, before_id: int | None = None
    ) -> list[dict]:
        """چند پیام آخر رد و بدل شده با این کاربر، به ترتیب زمان.

        برای سربرگ ادمین است: وقتی تیکت تازه ای می رسد، ادمین باید
        بدون رفتن به جای دیگر بداند قبلا درباره چه چیزی حرف زده اند.
        before_id یعنی خود پیام فعلی در تاریخچه تکرار نشود.
        """
        if before_id:
            rows = await self.fetchall(
                """SELECT direction, body, file_id, created_at FROM tickets
                   WHERE user_id = ? AND id < ? ORDER BY id DESC LIMIT ?""",
                (user_id, before_id, limit),
            )
        else:
            rows = await self.fetchall(
                """SELECT direction, body, file_id, created_at FROM tickets
                   WHERE user_id = ? ORDER BY id DESC LIMIT ?""",
                (user_id, limit),
            )
        return [dict(r) for r in reversed(rows)]

    async def user_tickets(self, user_id: int, limit: int = 20) -> list[dict]:
        rows = await self.fetchall(
            """SELECT * FROM tickets WHERE user_id = ?
               ORDER BY id DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(r) for r in reversed(rows)]

    async def unread_replies(self, user_id: int) -> int:
        row = await self.fetchone(
            """SELECT COUNT(*) AS n FROM tickets
               WHERE user_id = ? AND direction = 'out' AND is_read = 0""",
            (user_id,),
        )
        return row["n"] or 0

    async def mark_tickets_read(self, user_id: int) -> None:
        await self.execute(
            "UPDATE tickets SET is_read = 1 WHERE user_id = ? AND direction = 'out'",
            (user_id,),
        )

    # ---------- لیست کاربران (ادمین) ----------
    async def users_page(
        self, page: int = 0, per_page: int = 8, sort: str = "recent"
    ) -> tuple[list[dict], int]:
        """صفحه ای از کاربران با آمار خلاصه. خروجی: (لیست، تعداد کل)."""
        orders = {
            "recent": "u.created_at DESC",
            "balance": "u.balance DESC",
            "spent": "spent DESC",
            "services": "svc DESC",
        }
        order = orders.get(sort, orders["recent"])
        rows = await self.fetchall(
            f"""SELECT u.*,
                   (SELECT COUNT(*) FROM services s WHERE s.user_id = u.id) AS svc,
                   (SELECT COALESCE(SUM(-amount), 0) FROM transactions t
                     WHERE t.user_id = u.id AND t.type = 'purchase'
                       AND t.status = 'approved') AS spent
                FROM users u
                ORDER BY {order}
                LIMIT ? OFFSET ?""",
            (per_page, page * per_page),
        )
        total = await self.fetchone("SELECT COUNT(*) AS n FROM users")
        return [dict(r) for r in rows], (total["n"] or 0)

    async def user_summary(self, user_id: int) -> dict:
        """آمار کامل یک کاربر برای پنل ادمین."""
        row = await self.fetchone(
            """SELECT
                 (SELECT COUNT(*) FROM services WHERE user_id = ?) AS services,
                 (SELECT COUNT(*) FROM users WHERE referred_by =
                    (SELECT telegram_id FROM users WHERE id = ?)) AS referrals,
                 (SELECT COALESCE(SUM(-amount), 0) FROM transactions
                   WHERE user_id = ? AND type = 'purchase' AND status = 'approved') AS spent,
                 (SELECT COALESCE(SUM(amount), 0) FROM transactions
                   WHERE user_id = ? AND type = 'charge' AND status = 'approved') AS charged,
                 (SELECT COUNT(*) FROM transactions
                   WHERE user_id = ? AND status = 'pending') AS pending""",
            (user_id, user_id, user_id, user_id, user_id),
        )
        return dict(row) if row else {}

    # ---------- کد تخفیف ----------
    async def create_discount(
        self,
        code: str,
        kind: str,
        amount: int,
        max_uses: int | None = None,
        expires_at: str | None = None,
        min_amount: int = 0,
        per_user_limit: int = 1,
    ) -> int | None:
        """ساخت کد تخفیف. None یعنی کد تکراری است."""
        try:
            return await self.insert(
                """INSERT INTO discounts
                   (code, kind, amount, max_uses, expires_at, min_amount,
                    per_user_limit, is_active, created_at)
                   VALUES(?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (
                    code.strip().upper(),
                    kind,
                    amount,
                    max_uses,
                    expires_at,
                    min_amount,
                    per_user_limit,
                    now_str(),
                ),
            )
        except aiosqlite.IntegrityError:
            return None

    async def get_discount(self, did: int) -> dict | None:
        row = await self.fetchone("SELECT * FROM discounts WHERE id = ?", (did,))
        return dict(row) if row else None

    async def discount_by_code(self, code: str) -> dict | None:
        row = await self.fetchone(
            "SELECT * FROM discounts WHERE code = ?", (code.strip().upper(),)
        )
        return dict(row) if row else None

    async def discounts(self) -> list[dict]:
        return [dict(r) for r in await self.fetchall(
            "SELECT * FROM discounts ORDER BY is_active DESC, id DESC"
        )]

    async def update_discount(self, did: int, **fields) -> None:
        allowed = {
            "code", "kind", "amount", "max_uses", "expires_at",
            "min_amount", "per_user_limit", "is_active",
        }
        sets, vals = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                vals.append(v)
        if not sets:
            return
        vals.append(did)
        await self.execute(f"UPDATE discounts SET {', '.join(sets)} WHERE id = ?", tuple(vals))

    async def delete_discount(self, did: int) -> None:
        await self.execute("DELETE FROM discount_uses WHERE discount_id = ?", (did,))
        await self.execute("DELETE FROM discounts WHERE id = ?", (did,))

    async def validate_discount(
        self, code: str, user_id: int, order_amount: int
    ) -> tuple[dict | None, str]:
        """اعتبارسنجی کد. خروجی: (کد یا None، پیام خطا).

        همه شرط ها اینجا بررسی می شوند تا منطق در یک جا بماند.
        """
        d = await self.discount_by_code(code)
        if not d:
            return None, "not_found"
        if not d["is_active"]:
            return None, "inactive"
        if d["expires_at"] and _ts(d["expires_at"]) < _ts(now_str()):
            return None, "expired"
        if d["max_uses"] is not None and d["used_count"] >= d["max_uses"]:
            return None, "exhausted"
        if order_amount < (d["min_amount"] or 0):
            return None, "min_amount"
        row = await self.fetchone(
            "SELECT COUNT(*) AS n FROM discount_uses WHERE discount_id = ? AND user_id = ?",
            (d["id"], user_id),
        )
        if (row["n"] or 0) >= (d["per_user_limit"] or 1):
            return None, "user_limit"
        return d, ""

    @staticmethod
    def discount_value(d: dict, order_amount: int) -> int:
        """مبلغ تخفیف. هرگز از خود سفارش بیشتر نمی شود."""
        if d["kind"] == "percent":
            value = order_amount * d["amount"] // 100
        else:
            value = d["amount"]
        return max(0, min(value, order_amount))

    async def redeem_discount(
        self, did: int, user_id: int, order_amount: int, saved: int
    ) -> bool:
        """ثبت مصرف کد به صورت اتمیک.

        شرط used_count در همان UPDATE بررسی می شود تا دو خرید هم زمان
        نتوانند از سقف عبور کنند.
        """
        async with self._lock:
            assert self._conn
            await self._conn.execute("BEGIN IMMEDIATE")
            try:
                cur = await self._conn.execute(
                    """SELECT per_user_limit,
                              (SELECT COUNT(*) FROM discount_uses
                                WHERE discount_id = ? AND user_id = ?) AS mine
                       FROM discounts
                       WHERE id = ? AND is_active = 1
                         AND (max_uses IS NULL OR used_count < max_uses)""",
                    (did, user_id, did),
                )
                row = await cur.fetchone()
                if row is None or (row[1] or 0) >= (row[0] or 1):
                    await self._conn.rollback()
                    return False
                await self._conn.execute(
                    "UPDATE discounts SET used_count = used_count + 1 WHERE id = ?",
                    (did,),
                )
                await self._conn.execute(
                    """INSERT INTO discount_uses(discount_id, user_id, order_amount, saved, used_at)
                       VALUES(?, ?, ?, ?, ?)""",
                    (did, user_id, order_amount, saved, now_str()),
                )
                await self._conn.commit()
                return True
            except Exception:
                await self._conn.rollback()
                raise

    async def discount_stats(self, did: int) -> dict:
        row = await self.fetchone(
            """SELECT COUNT(*) AS uses, COUNT(DISTINCT user_id) AS users,
                      COALESCE(SUM(saved), 0) AS saved,
                      COALESCE(SUM(order_amount), 0) AS revenue
               FROM discount_uses WHERE discount_id = ?""",
            (did,),
        )
        return dict(row) if row else {"uses": 0, "users": 0, "saved": 0, "revenue": 0}

    # ---------- دسته بندی پلن ها ----------
    async def _seed_categories(self) -> None:
        """ساخت دسته های پیش فرض و اتصال پلن های بدون دسته.

        فقط یک بار اجرا می شود. اگر دسته ای وجود داشته باشد کاری نمی کند.
        پلن های قدیمی بر اساس مدتشان به دسته مناسب وصل می شوند.
        """
        assert self._conn
        cur = await self._conn.execute("SELECT COUNT(*) FROM categories")
        if (await cur.fetchone())[0] == 0:
            defaults = [
                ("روزانه", "☀️", 1),
                ("هفتگی", "📆", 2),
                ("ماهانه", "🗓", 3),
            ]
            for title, emoji, order in defaults:
                await self._conn.execute(
                    """INSERT INTO categories(title, emoji, sort_order, is_active, created_at)
                       VALUES(?, ?, ?, 1, ?)""",
                    (title, emoji, order, now_str()),
                )
            log.info("دسته های پیش فرض ساخته شدند")

        # اتصال پلن های بدون دسته بر اساس مدت
        rows = await self._conn.execute("SELECT id, title FROM categories ORDER BY sort_order")
        cats = {r[1]: r[0] for r in await rows.fetchall()}
        mapping = [
            ("روزانه", 0, 3),
            ("هفتگی", 4, 14),
            ("ماهانه", 15, 99999),
        ]
        for title, lo, hi in mapping:
            cid = cats.get(title)
            if not cid:
                continue
            await self._conn.execute(
                """UPDATE plans SET category_id = ?
                   WHERE category_id IS NULL AND duration_days BETWEEN ? AND ?""",
                (cid, lo, hi),
            )

    async def categories(self, only_active: bool = False) -> list[dict]:
        sql = "SELECT * FROM categories"
        if only_active:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY sort_order, id"
        return [dict(r) for r in await self.fetchall(sql)]

    async def get_category(self, cid: int) -> dict | None:
        row = await self.fetchone("SELECT * FROM categories WHERE id = ?", (cid,))
        return dict(row) if row else None

    async def create_category(self, title: str, emoji: str = "📦") -> int:
        row = await self.fetchone("SELECT COALESCE(MAX(sort_order), 0) AS m FROM categories")
        return await self.insert(
            """INSERT INTO categories(title, emoji, sort_order, is_active, created_at)
               VALUES(?, ?, ?, 1, ?)""",
            (title, emoji, (row["m"] or 0) + 1, now_str()),
        )

    async def update_category(self, cid: int, **fields) -> None:
        allowed = {"title", "emoji", "sort_order", "is_active"}
        sets, vals = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                vals.append(v)
        if not sets:
            return
        vals.append(cid)
        await self.execute(f"UPDATE categories SET {', '.join(sets)} WHERE id = ?", tuple(vals))

    async def delete_category(self, cid: int) -> bool:
        """حذف دسته. پلن هایش بدون دسته می شوند (نه حذف)."""
        await self.execute("UPDATE plans SET category_id = NULL WHERE category_id = ?", (cid,))
        rows = await self.execute("DELETE FROM categories WHERE id = ?", (cid,))
        return bool(rows)

    async def move_category(self, cid: int, direction: int) -> bool:
        """جابه جایی دسته در ترتیب نمایش. direction: -1 بالا، +1 پایین."""
        cats = await self.categories()
        idx = next((i for i, c in enumerate(cats) if c["id"] == cid), None)
        if idx is None:
            return False
        new_idx = idx + direction
        if not 0 <= new_idx < len(cats):
            return False
        a, b = cats[idx], cats[new_idx]
        await self.update_category(a["id"], sort_order=b["sort_order"])
        await self.update_category(b["id"], sort_order=a["sort_order"])
        return True

    async def category_plan_count(self, cid: int) -> int:
        row = await self.fetchone(
            "SELECT COUNT(*) AS n FROM plans WHERE category_id = ?", (cid,)
        )
        return row["n"] or 0

    # ---------- قوانین ----------
    async def accept_rules(self, user_id: int) -> bool:
        """ثبت تایید قوانین. اگر قبلا تایید کرده باشد False برمی گردد."""
        rows = await self.execute(
            """UPDATE users SET rules_accepted_at = ?
               WHERE id = ? AND rules_accepted_at IS NULL""",
            (now_str(), user_id),
        )
        return bool(rows)

    async def reset_all_rules(self) -> int:
        """لغو تایید همه کاربران (وقتی قوانین مهم تغییر کرد)."""
        return await self.execute("UPDATE users SET rules_accepted_at = NULL")

    # ---------- یادآوری فیش ----------
    async def mark_paid(self, txn_id: int, user_id: int) -> bool:
        """ثبت اینکه کاربر گفت واریز کردم. مبنای شمارش ۱۰ دقیقه یادآوری."""
        rows = await self.execute(
            """UPDATE transactions SET paid_at = ?
               WHERE id = ? AND user_id = ? AND status = 'pending'
                 AND paid_at IS NULL AND cancelled_at IS NULL""",
            (now_str(), txn_id, user_id),
        )
        return bool(rows)

    async def cancel_charge(self, txn_id: int, user_id: int) -> dict | None:
        """لغو شارژ توسط کاربر. یادآوری دیگر فرستاده نمی شود."""
        rows = await self.execute(
            """UPDATE transactions SET cancelled_at = ?, status = 'cancelled'
               WHERE id = ? AND user_id = ? AND status = 'pending'""",
            (now_str(), txn_id, user_id),
        )
        if not rows:
            return None
        txn = await self.get_transaction(txn_id)
        if txn:
            await self.release_amount(txn["amount"])
        return txn

    async def pending_reminders(self, minutes: int = 10) -> list[dict]:
        """تراکنش هایی که باید یادآوری بگیرند.

        شرط ها: کاربر گفته واریز کردم، بیش از N دقیقه گذشته، هنوز رسید
        نفرستاده، لغو نکرده، و قبلا یادآوری نگرفته.
        """
        # قالب زمان باید دقیقا مثل now_str() باشد (ISO با آفست).
        # نسخه قبلی strftime بود و مقایسه رشته ای همیشه غلط جواب می داد،
        # پس یادآوری فیش در عمل هرگز ارسال نمی شد.
        cutoff = (datetime.now(TZ) - timedelta(minutes=minutes)).isoformat(
            timespec="seconds"
        )
        rows = await self.fetchall(
            """SELECT t.*, u.telegram_id
               FROM transactions t JOIN users u ON u.id = t.user_id
               WHERE t.type = 'charge' AND t.status = 'pending'
                 AND t.paid_at IS NOT NULL AND t.paid_at < ?
                 AND t.receipt_file_id IS NULL
                 AND t.cancelled_at IS NULL
                 AND t.reminded_at IS NULL""",
            (cutoff,),
        )
        return [dict(r) for r in rows]

    async def mark_reminded(self, txn_id: int) -> None:
        await self.execute(
            "UPDATE transactions SET reminded_at = ? WHERE id = ?", (now_str(), txn_id)
        )

    # ---------- مبلغ یکتا برای تشخیص رسید ----------
    async def reserve_amount(
        self, user_id: int, base_amount: int, ttl_minutes: int = 2, tries: int = 60
    ) -> int | None:
        """رزرو یک مبلغ یکتا نزدیک به base_amount.

        سه رقم آخر تصادفی می شود تا از روی رسید بفهمیم مال کیست.
        اگر مبلغ قبلا رزرو شده باشد، مقدار دیگری امتحان می شود.
        None یعنی نتوانستیم مبلغ آزاد پیدا کنیم.
        """
        import random

        await self.purge_expired_amounts()
        now = datetime.now(TZ)
        created = now.isoformat(timespec="seconds")
        expires = (now + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds")

        for _ in range(tries):
            suffix = random.randint(1, 999)
            amount = base_amount + suffix
            try:
                await self.execute(
                    """INSERT INTO pending_amounts(amount, user_id, base_amount, created_at, expires_at)
                       VALUES(?, ?, ?, ?, ?)""",
                    (amount, user_id, base_amount, created, expires),
                )
                return amount
            except aiosqlite.IntegrityError:
                continue  # تکراری بود، دوباره امتحان کن
        return None

    async def extend_amount(self, amount: int, user_id: int, ttl_minutes: int) -> bool:
        """مهلت مبلغ رزرو شده را از همین حالا دوباره شروع می کند.

        ربات مبلغ را در مرحله تایید رزرو می کند؛ با مهلت کوتاه، شمارش باید
        از لحظه نمایش شماره کارت باشد نه از مرحله تایید.
        """
        expires = (datetime.now(TZ) + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds")
        rows = await self.execute(
            "UPDATE pending_amounts SET expires_at = ? WHERE amount = ? AND user_id = ?",
            (expires, amount, user_id),
        )
        return bool(rows)

    async def release_amount(self, amount: int) -> None:
        await self.execute("DELETE FROM pending_amounts WHERE amount = ?", (amount,))

    async def purge_expired_locks(self) -> int:
        return await self.execute("DELETE FROM op_locks WHERE expires_at < ?", (now_str(),))

    async def purge_expired_amounts(self) -> int:
        return await self.execute(
            "DELETE FROM pending_amounts WHERE expires_at < ?", (now_str(),)
        )

    async def find_by_amount(self, amount: int) -> dict | None:
        """پیدا کردن صاحب یک مبلغ رزرو شده (برای ادمین)."""
        return await self.fetchone(
            "SELECT * FROM pending_amounts WHERE amount = ?", (amount,)
        )

    # ---------- تست رایگان و هم سفرها ----------
    async def mark_trial_used(self, user_id: int) -> bool:
        """علامت گذاری تست رایگان. False یعنی قبلا استفاده شده (اتمیک)."""
        rows = await self.execute(
            "UPDATE users SET free_trial_used = 1 WHERE id = ? AND free_trial_used = 0",
            (user_id,),
        )
        return bool(rows)

    async def referral_count(self, telegram_id: int) -> int:
        """تعداد هم سفرها.

        توجه: ستون referred_by آیدی تلگرام معرف را نگه می دارد (نه آیدی
        داخلی). نسخه قبلی آیدی داخلی را پاس می داد و همیشه صفر برمی گشت.
        """
        row = await self.fetchone(
            "SELECT COUNT(*) AS c FROM users WHERE referred_by = ?", (telegram_id,)
        )
        return row["c"] if row else 0

    # ---------- ارسال همگانی ----------
    async def create_broadcast(
        self,
        src_chat_id: int,
        src_message_id: int,
        show_source: bool,
        pin: bool,
        markup_json: str | None,
        report_chat_id: int,
        report_message_id: int,
    ) -> int:
        """ثبت یک کار ارسال همگانی تازه و برگرداندن آیدی آن."""
        row = await self.fetchone(
            "SELECT COUNT(*) AS n FROM users WHERE is_blocked = 0"
        )
        return await self.insert(
            """INSERT INTO broadcast_jobs(
                   src_chat_id, src_message_id, show_source, pin, markup_json,
                   report_chat_id, report_message_id, total, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                src_chat_id,
                src_message_id,
                1 if show_source else 0,
                1 if pin else 0,
                markup_json,
                report_chat_id,
                report_message_id,
                row["n"] if row else 0,
                now_str(),
            ),
        )

    async def active_broadcast(self) -> dict | None:
        row = await self.fetchone(
            "SELECT * FROM broadcast_jobs WHERE status = 'active' ORDER BY id LIMIT 1"
        )
        return dict(row) if row else None

    async def broadcast_targets(self, after_user_id: int, limit: int) -> list[dict]:
        """دسته بعدی گیرنده ها. مکان نما روی users.id است تا اضافه شدن
        کاربر تازه وسط ارسال، ترتیب را به هم نریزد."""
        rows = await self.fetchall(
            """SELECT id, telegram_id FROM users
               WHERE is_blocked = 0 AND id > ?
               ORDER BY id LIMIT ?""",
            (after_user_id, limit),
        )
        return [dict(r) for r in rows]

    async def update_broadcast(
        self,
        job_id: int,
        cursor_user_id: int,
        sent: int,
        failed: int,
        blocked: int,
        pinned: int,
    ) -> None:
        await self.execute(
            """UPDATE broadcast_jobs
               SET cursor_user_id = ?, sent = ?, failed = ?, blocked = ?,
                   pinned = ?, updated_at = ?
               WHERE id = ?""",
            (cursor_user_id, sent, failed, blocked, pinned, now_str(), job_id),
        )

    async def finish_broadcast(self, job_id: int, status: str = "done") -> None:
        await self.execute(
            "UPDATE broadcast_jobs SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_str(), job_id),
        )

    # ---------- نظرسنجی ----------
    async def create_poll(
        self,
        question: str,
        options: list[str],
        layout: str = "vertical",
        style: str | None = None,
        show_results: bool = True,
    ) -> int:
        poll_id = await self.insert(
            """INSERT INTO polls(question, layout, style, show_results, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (question, layout, style, 1 if show_results else 0, now_str()),
        )
        for i, label in enumerate(options):
            await self.insert(
                "INSERT INTO poll_options(poll_id, label, position) VALUES (?, ?, ?)",
                (poll_id, label, i),
            )
        return poll_id

    async def get_poll(self, poll_id: int) -> dict | None:
        row = await self.fetchone("SELECT * FROM polls WHERE id = ?", (poll_id,))
        return dict(row) if row else None

    async def poll_options(self, poll_id: int) -> list[dict]:
        rows = await self.fetchall(
            "SELECT * FROM poll_options WHERE poll_id = ? ORDER BY position, id",
            (poll_id,),
        )
        return [dict(r) for r in rows]

    async def poll_results(self, poll_id: int) -> list[dict]:
        """گزینه ها به همراه تعداد رای. صفر هم برمی گردد (LEFT JOIN)."""
        rows = await self.fetchall(
            """SELECT o.id, o.label, o.position,
                      COUNT(v.id) AS votes
               FROM poll_options o
               LEFT JOIN poll_votes v ON v.option_id = o.id
               WHERE o.poll_id = ?
               GROUP BY o.id ORDER BY o.position, o.id""",
            (poll_id,),
        )
        return [dict(r) for r in rows]

    async def poll_vote(self, poll_id: int, option_id: int, user_id: int) -> bool:
        """ثبت یا تغییر رای. False یعنی همین گزینه از قبل انتخاب شده بود."""
        row = await self.fetchone(
            "SELECT option_id FROM poll_votes WHERE poll_id = ? AND user_id = ?",
            (poll_id, user_id),
        )
        if row and int(row["option_id"]) == option_id:
            return False
        if row:
            await self.execute(
                "UPDATE poll_votes SET option_id = ?, created_at = ? "
                "WHERE poll_id = ? AND user_id = ?",
                (option_id, now_str(), poll_id, user_id),
            )
        else:
            await self.insert(
                """INSERT INTO poll_votes(poll_id, option_id, user_id, created_at)
                   VALUES (?, ?, ?, ?)""",
                (poll_id, option_id, user_id, now_str()),
            )
        return True

    async def user_poll_vote(self, poll_id: int, user_id: int) -> int | None:
        row = await self.fetchone(
            "SELECT option_id FROM poll_votes WHERE poll_id = ? AND user_id = ?",
            (poll_id, user_id),
        )
        return int(row["option_id"]) if row else None

    async def list_polls(self, limit: int = 10) -> list[dict]:
        rows = await self.fetchall(
            """SELECT p.*, (SELECT COUNT(*) FROM poll_votes v WHERE v.poll_id = p.id)
                      AS votes
               FROM polls p ORDER BY p.id DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in rows]

    async def set_poll_open(self, poll_id: int, is_open: bool) -> None:
        await self.execute(
            "UPDATE polls SET is_open = ? WHERE id = ?", (1 if is_open else 0, poll_id)
        )

    async def poll_breakdown(self, poll_id: int) -> list[dict]:
        """رای ها به تفکیک «کاربر دارای سرویس» و «بدون سرویس».

        این تفکیک مهم است: نظر کسی که پول داده با نظر کسی که فقط ثبت نام
        کرده وزن یکسانی ندارد.
        """
        rows = await self.fetchall(
            """SELECT o.label,
                      SUM(CASE WHEN s.n > 0 THEN 1 ELSE 0 END) AS buyers,
                      SUM(CASE WHEN s.n > 0 THEN 0 ELSE 1 END) AS others
               FROM poll_votes v
               JOIN poll_options o ON o.id = v.option_id
               LEFT JOIN (SELECT user_id, COUNT(*) AS n FROM services GROUP BY user_id) s
                      ON s.user_id = v.user_id
               WHERE v.poll_id = ?
               GROUP BY o.id ORDER BY o.position, o.id""",
            (poll_id,),
        )
        return [dict(r) for r in rows]

    # ---------- سفارش های هوش مصنوعی ----------
    async def create_ai_order(
        self,
        user_id: int,
        service_id: str,
        title: str,
        quantity: int,
        usd_cost: float | None,
        price: int,
        txn_id: int | None = None,
    ) -> dict:
        """ثبت سفارش در حالت pending، *قبل* از تماس با سرویس دهنده.

        ترتیب عمدی است: اول ردیف ساخته می شود، بعد سفارش واقعی. اگر
        وسط کار پروسه بمیرد، ردیف pending می ماند و ادمین می بیند -
        برخلاف حالتی که اول سفارش بدهیم و بعد ثبت کنیم، که می تواند
        سفارش پرداخت شده بدون هیچ ردی باقی بگذارد.
        """
        oid = await self.insert(
            """INSERT INTO ai_orders
               (user_id, service_id, title, quantity, usd_cost, price, txn_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, service_id, title, quantity, usd_cost, price, txn_id, now_str()),
        )
        code = track_code("AI", oid)
        await self.execute("UPDATE ai_orders SET code = ? WHERE id = ?", (code, oid))
        row = await self.fetchone("SELECT * FROM ai_orders WHERE id = ?", (oid,))
        return dict(row)

    async def finish_ai_order(
        self,
        order_id: int,
        status: str,
        provider_order_id: str | None = None,
        products: str | None = None,
        error: str | None = None,
    ) -> None:
        await self.execute(
            """UPDATE ai_orders
               SET status = ?, provider_order_id = ?, products = ?, error = ?,
                   delivered_at = ?
               WHERE id = ?""",
            (
                status,
                provider_order_id,
                products,
                (error or "")[:300] or None,
                now_str() if status == "delivered" else None,
                order_id,
            ),
        )

    async def get_ai_order(self, order_id: int) -> dict | None:
        row = await self.fetchone("SELECT * FROM ai_orders WHERE id = ?", (order_id,))
        return dict(row) if row else None

    async def user_ai_orders(self, user_id: int, limit: int = 10) -> list[dict]:
        rows = await self.fetchall(
            """SELECT * FROM ai_orders WHERE user_id = ?
               ORDER BY id DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(r) for r in rows]

    async def ai_orders_by_status(self, status: str, limit: int = 20) -> list[dict]:
        rows = await self.fetchall(
            """SELECT a.*, u.telegram_id, u.first_name FROM ai_orders a
               JOIN users u ON u.id = a.user_id
               WHERE a.status = ? ORDER BY a.id DESC LIMIT ?""",
            (status, limit),
        )
        return [dict(r) for r in rows]

    async def ai_order_by_code(self, code: str) -> dict | None:
        row = await self.fetchone(
            """SELECT a.*, u.telegram_id AS user_tg_id FROM ai_orders a
               JOIN users u ON u.id = a.user_id WHERE a.code = ?""",
            (code,),
        )
        return dict(row) if row else None

    async def ai_stats(self) -> dict:
        row = await self.fetchone(
            """SELECT
                 COUNT(*) AS total,
                 SUM(CASE WHEN status='delivered' THEN 1 ELSE 0 END) AS delivered,
                 SUM(CASE WHEN status='unknown' THEN 1 ELSE 0 END) AS unknown,
                 SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
                 SUM(CASE WHEN status='delivered' THEN price ELSE 0 END) AS revenue
               FROM ai_orders"""
        )
        return dict(row) if row else {}

    # ---------- فهرست انتظار هوش مصنوعی ----------
    async def ai_waitlist_add(self, user_id: int) -> bool:
        try:
            await self.insert(
                "INSERT INTO ai_waitlist(user_id, created_at) VALUES (?, ?)",
                (user_id, now_str()),
            )
            return True
        except Exception:  # noqa: BLE001
            return False  # از قبل ثبت شده

    async def ai_waitlist_all(self) -> list[dict]:
        rows = await self.fetchall(
            """SELECT w.user_id, u.telegram_id FROM ai_waitlist w
               JOIN users u ON u.id = w.user_id"""
        )
        return [dict(r) for r in rows]

    async def ai_waitlist_clear(self) -> None:
        await self.execute("DELETE FROM ai_waitlist")

    # ---------- کانال ها ----------
    async def save_channel(
        self, chat_id: int, title: str, username: str, ctype: str, can_post: bool
    ) -> None:
        await self.execute(
            """INSERT INTO bot_channels(chat_id, title, username, type, can_post, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET
                 title = excluded.title, username = excluded.username,
                 type = excluded.type, can_post = excluded.can_post,
                 updated_at = excluded.updated_at""",
            (chat_id, title, username, ctype, 1 if can_post else 0, now_str()),
        )

    async def forget_channel(self, chat_id: int) -> None:
        await self.execute("DELETE FROM bot_channels WHERE chat_id = ?", (chat_id,))

    async def bot_channels(self) -> list[dict]:
        rows = await self.fetchall(
            "SELECT * FROM bot_channels WHERE can_post = 1 ORDER BY title"
        )
        return [dict(r) for r in rows]

    # ---------- ریست کامل کاربر ----------
    async def purge_user(self, user_id: int, keep_services: bool = False) -> dict:
        """پاک کردن ردپای کاربر تا دفعه بعد مثل کاربر تازه باشد.

        keep_services=True یعنی ردیف سرویس ها در ربات می ماند (برای وقتی
        که فقط می خواهی کیف پول و تست رایگان ریست شود). پیش فرض پاک
        کردن همه چیز است.

        توجه: این کار سرویس ها را از *پنل* پاک نمی کند - آن کار جدا و
        عمدی است، چون برگشت پذیر نیست.
        """
        stats = {}
        # هر جدولی که کلید خارجی به users دارد باید *قبل* از خود کاربر
        # پاک شود، وگرنه SQLite با FOREIGN KEY constraint failed رد
        # می کند و هیچ چیز حذف نمی شود. سه جدول جا افتاده بود:
        # pending_amounts، discount_uses، و سمت invitee در
        # referral_earnings (کاربر می تواند دعوت شده هم باشد، نه فقط
        # دعوت کننده).
        tables = [
            ("pending_amounts", "user_id"),
            ("ai_orders", "user_id"),
            ("ai_waitlist", "user_id"),
            ("transactions", "user_id"),
            ("discount_uses", "user_id"),
            ("tickets", "user_id"),
            ("referral_earnings", "referrer_id"),
            ("referral_earnings", "invitee_id"),
            ("poll_votes", "user_id"),
        ]
        if not keep_services:
            tables.insert(0, ("services", "user_id"))
        for table, col in tables:
            try:
                n = await self.execute(
                    f"DELETE FROM {table} WHERE {col} = ?", (user_id,)
                )
                stats[table] = stats.get(table, 0) + n
            except Exception:  # noqa: BLE001
                log.warning("پاک کردن %s برای کاربر %s نشد", table, user_id)
                stats.setdefault(table, 0)
        # ارجاع معرف دیگران به این کاربر هم پاک می شود
        try:
            await self.execute(
                "UPDATE users SET referred_by = NULL WHERE referred_by = ?", (user_id,)
            )
        except Exception:  # noqa: BLE001
            pass
        stats["users"] = await self.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return stats

    # ---------- پاداش هم سفرها ----------
    async def record_referral_earning(
        self,
        referrer_id: int,
        invitee_id: int,
        txn_id: int | None,
        order_amount: int,
        reward: int,
        kind: str = "purchase",
    ) -> bool:
        """ثبت پاداش. False یعنی برای همین خرید قبلا ثبت شده بود.

        اول ثبت می شود، بعد پول واریز می شود. اگر ترتیب برعکس بود و
        پروسه وسط کار می افتاد، ممکن بود پول دو بار واریز شود.
        """
        try:
            await self.insert(
                """INSERT INTO referral_earnings(
                       referrer_id, invitee_id, txn_id, order_amount, reward, kind, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (referrer_id, invitee_id, txn_id, order_amount, reward, kind, now_str()),
            )
            return True
        except aiosqlite.IntegrityError:
            return False

    async def invitee_rewarded_before(self, invitee_id: int) -> bool:
        """آیا برای این کاربر قبلا پاداشی به معرفش رسیده؟ (برای پاداش اولین خرید)"""
        row = await self.fetchone(
            "SELECT 1 AS x FROM referral_earnings WHERE invitee_id = ? LIMIT 1",
            (invitee_id,),
        )
        return row is not None

    async def referral_stats(self, telegram_id: int, user_id: int) -> dict:
        """آمار صفحه هم سفرها: تعداد دعوت، تعداد خریدار، درآمد کل و ماه جاری."""
        joined = await self.referral_count(telegram_id)
        row = await self.fetchone(
            """SELECT COUNT(*) AS n,
                      COALESCE(SUM(reward), 0) AS total,
                      COUNT(DISTINCT invitee_id) AS buyers
               FROM referral_earnings WHERE referrer_id = ?""",
            (user_id,),
        )
        month = await self.fetchone(
            """SELECT COALESCE(SUM(reward), 0) AS s FROM referral_earnings
               WHERE referrer_id = ? AND created_at >= ?""",
            (user_id, (now() - timedelta(days=30)).isoformat(timespec="seconds")),
        )
        return {
            "joined": joined,
            "rewards": row["n"] if row else 0,
            "total": row["total"] if row else 0,
            "buyers": row["buyers"] if row else 0,
            "month": month["s"] if month else 0,
        }

    async def referral_log(self, user_id: int, limit: int = 10) -> list[dict]:
        """آخرین پاداش ها همراه نام کاربر دعوت شده."""
        rows = await self.fetchall(
            """SELECT e.reward, e.order_amount, e.kind, e.created_at,
                      u.first_name, u.username
               FROM referral_earnings e
               JOIN users u ON u.id = e.invitee_id
               WHERE e.referrer_id = ?
               ORDER BY e.id DESC LIMIT ?""",
            (user_id, limit),
        )
        return [dict(r) for r in rows]

    async def referral_top(self, limit: int = 10) -> list[dict]:
        """جدول برترین معرف ها (برای ادمین یا نمایش عمومی)."""
        rows = await self.fetchall(
            """SELECT u.telegram_id, u.first_name, u.username,
                      COALESCE(SUM(e.reward), 0) AS total,
                      COUNT(DISTINCT e.invitee_id) AS buyers
               FROM referral_earnings e
               JOIN users u ON u.id = e.referrer_id
               GROUP BY e.referrer_id
               ORDER BY total DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in rows]

    async def get_setting(self, key: str, default: str = "") -> str:
        row = await self.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        await self.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # ---------- آمار ادمین ----------
    async def dashboard_stats(self) -> dict:
        total_users = await self.fetchone("SELECT COUNT(*) AS c FROM users")
        active_services = await self.fetchone(
            "SELECT COUNT(*) AS c FROM services WHERE is_active = 1 AND expire_at > ?",
            (now_str(),),
        )
        today = datetime.now(TZ).date().isoformat()
        today_sales = await self.fetchone(
            "SELECT COALESCE(SUM(-amount), 0) AS s FROM transactions "
            "WHERE type = 'purchase' AND status = 'approved' AND substr(created_at, 1, 10) = ?",
            (today,),
        )
        pending = await self.fetchone(
            "SELECT COUNT(*) AS c FROM transactions "
            "WHERE type = 'charge' AND status = 'pending' AND receipt_file_id IS NOT NULL"
        )
        return {
            "total_users": total_users["c"],
            "active_services": active_services["c"],
            "today_sales": today_sales["s"],
            "pending_count": pending["c"],
        }
    # ---------- نگاشت پیام های پشتیبانی (پایدار در دیتابیس) ----------
    async def save_support_link(self, admin_id: int, message_id: int, user_tg_id: int) -> None:
        await self.execute(
            "INSERT INTO support_links(admin_id, message_id, user_tg_id, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(admin_id, message_id) DO UPDATE SET user_tg_id = excluded.user_tg_id",
            (admin_id, message_id, user_tg_id, now_str()),
        )

    async def get_support_link(self, admin_id: int, message_id: int) -> int | None:
        row = await self.fetchone(
            "SELECT user_tg_id FROM support_links WHERE admin_id = ? AND message_id = ?",
            (admin_id, message_id),
        )
        return row["user_tg_id"] if row else None

    async def purge_old_support_links(self, days: int = 30) -> int:
        cutoff = (datetime.now(TZ) - timedelta(days=days)).isoformat(timespec="seconds")
        return await self.execute("DELETE FROM support_links WHERE created_at < ?", (cutoff,))

    # ---------- نام دلخواه سرویس ----------
    async def set_service_label(self, service_id: int, user_id: int, label: str | None) -> bool:
        """ثبت نام دلخواه. user_id در شرط هست تا کسی سرویس دیگری را تغییر ندهد."""
        rows = await self.execute(
            "UPDATE services SET label = ? WHERE id = ? AND user_id = ?",
            (label, service_id, user_id),
        )
        return rows > 0
