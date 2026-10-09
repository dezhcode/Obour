"""دیتابیس جدای Game Club (SQLite با WAL).

قواعد مالی همان قواعد عبور است:
- هر تغییر امتیاز اتمیک است (UPDATE ... WHERE points >= ?)
- هر ردیف دفتر (ledger) یک idem یکتا دارد تا درخواست تکراری دو بار ثبت نشود
- وضعیت میز با شماره نسخه ذخیره می شود؛ اگر دو پروسه همزمان بنویسند،
  دومی رد می شود و دوباره از نو می خواند (Passenger چند پروسه دارد)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
  tg_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  username TEXT,
  av INTEGER NOT NULL DEFAULT 0,
  points INTEGER NOT NULL DEFAULT 0,
  games INTEGER NOT NULL DEFAULT 0,
  wins INTEGER NOT NULL DEFAULT 0,
  show_spend INTEGER NOT NULL DEFAULT 0,
  tutorial INTEGER NOT NULL DEFAULT 0,
  sound INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  seen_at INTEGER NOT NULL
);

-- هر تغییر امتیاز یک ردیف. amount مثبت = ورود، منفی = خروج
-- kind: charge, entry, refund, prize, shop, transfer, gift
CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  amount INTEGER NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  ref TEXT NOT NULL DEFAULT '',
  idem TEXT UNIQUE,
  status TEXT NOT NULL DEFAULT 'done',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ledger_user ON ledger(tg_id, id);
CREATE INDEX IF NOT EXISTS ledger_kind ON ledger(kind, created_at);

CREATE TABLE IF NOT EXISTS matches (
  id TEXT PRIMARY KEY,
  game TEXT NOT NULL DEFAULT 'ludo',
  status TEXT NOT NULL,            -- lobby, playing, over, cancelled
  cfg TEXT NOT NULL,
  state TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 0,
  host INTEGER,
  invite TEXT UNIQUE,
  settled INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS match_players (
  match_id TEXT NOT NULL,
  tg_id INTEGER NOT NULL,
  color TEXT NOT NULL,
  paid INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (match_id, tg_id)
);
CREATE INDEX IF NOT EXISTS mp_user ON match_players(tg_id, active);

-- صف بازی با ناشناس. held = امتیاز ورودی که هنگام ورود به صف قفل شده
CREATE TABLE IF NOT EXISTS queue (
  tg_id INTEGER PRIMARY KEY,
  cfg_key TEXT NOT NULL,
  cfg TEXT NOT NULL,
  held INTEGER NOT NULL DEFAULT 0,
  claimed TEXT,
  created_at REAL NOT NULL
);

-- نتیجه هر بازیکن انسانی در هر بازی تمام شده (رده بندی از اینجا)
CREATE TABLE IF NOT EXISTS results (
  match_id TEXT NOT NULL,
  tg_id INTEGER NOT NULL,
  won INTEGER NOT NULL,
  prize INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (match_id, tg_id)
);
CREATE INDEX IF NOT EXISTS results_time ON results(created_at);

CREATE TABLE IF NOT EXISTS notify (
  tg_id INTEGER NOT NULL,
  game TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tg_id, game)
);

-- آخرین باری که هر بازیکن صفحه میز را پرسیده (برای اعلان به کسی که بیرون رفته)
CREATE TABLE IF NOT EXISTS presence (
  match_id TEXT NOT NULL,
  tg_id INTEGER NOT NULL,
  seen REAL NOT NULL,
  PRIMARY KEY (match_id, tg_id)
);

-- هر اعلان یک بار (کلید یکتا)
-- گفتگوی سر میز (مثل پلاتو). متن پیش از ذخیره پاک سازی می شود
CREATE TABLE IF NOT EXISTS chat (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id TEXT NOT NULL,
  tg_id INTEGER NOT NULL,
  color TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_match ON chat(match_id, id);

CREATE TABLE IF NOT EXISTS pings (
  key TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS locks (
  key TEXT PRIMARY KEY,
  expires_at REAL NOT NULL
);

-- ظاهرهای خریده شده (میز و ورق حکم): item مثل table:b یا cards:c
CREATE TABLE IF NOT EXISTS owned (
  tg_id INTEGER NOT NULL,
  item TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (tg_id, item)
);

-- پنل مدیریت: هر کار ادمین یک ردیف (چه کسی، چه کاری، روی چه کسی/میزی)
CREATE TABLE IF NOT EXISTS admin_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  admin INTEGER NOT NULL,
  action TEXT NOT NULL,
  target TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS admin_log_at ON admin_log(id);

-- تنظیماتی که از پنل عوض می شوند و بر .env مقدم اند
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

-- پیام همگانی: متن از پنل یا کپی یک پیام از ربات؛ پیشرفت با cursor روی tg_id
CREATE TABLE IF NOT EXISTS broadcasts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  admin INTEGER NOT NULL,
  text TEXT NOT NULL DEFAULT '',
  src_chat INTEGER,
  src_msg INTEGER,
  button TEXT NOT NULL DEFAULT '',
  target TEXT NOT NULL DEFAULT 'all',
  status TEXT NOT NULL DEFAULT 'active',
  cursor INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  sent INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0,
  blocked INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  finished_at INTEGER
);
"""


_UNSAFE = re.compile(r"[<>&\"'`\\]|[\u0000-\u001f\u200e\u200f\u202a-\u202e]")


def _clean(text: str) -> str:
    return _UNSAFE.sub("", text or "").strip()[:40]


def pic_url(p: dict | None) -> str:
    """آدرس عکس پروفایل برای مینی اپ: photo_url تلگرام، وگرنه عکسی که ربات می گیرد."""
    if not p:
        return ""
    if p.get("photo"):
        return p["photo"]
    return f"pic/{p['pic']}" if p.get("pic") else ""


class GCDatabase:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._conn is not None:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self.path, timeout=15)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=8000")
        await self._conn.executescript(SCHEMA)
        # ستون های تازه روی دیتابیس قدیمی: عکس پروفایل تلگرام و کلید آدرس عکس
        cur = await self._conn.execute("PRAGMA table_info(players)")
        have = {r[1] for r in await cur.fetchall()}
        for col in ("photo", "pic", "ban_note", "table_skin", "card_skin"):
            if col not in have:
                await self._conn.execute(f"ALTER TABLE players ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
        if "banned" not in have:   # مسدود شده توسط ادمین
            await self._conn.execute("ALTER TABLE players ADD COLUMN banned INTEGER NOT NULL DEFAULT 0")
        await self._conn.execute("CREATE INDEX IF NOT EXISTS players_pic ON players(pic)")
        # گفتگوی میزهایی که تمام یا بسته شده اند (مثلا از پیش از این نسخه) پاک می شود
        await self._conn.execute(
            "DELETE FROM chat WHERE match_id NOT IN (SELECT id FROM matches WHERE status IN ('lobby','playing'))")
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ---------- پایه ----------
    async def execute(self, sql: str, params: tuple = ()) -> int:
        async with self._lock:
            assert self._conn
            cur = await self._conn.execute(sql, params)
            await self._conn.commit()
            return cur.rowcount

    async def insert(self, sql: str, params: tuple = ()) -> int:
        async with self._lock:
            assert self._conn
            cur = await self._conn.execute(sql, params)
            await self._conn.commit()
            return cur.lastrowid

    async def one(self, sql: str, params: tuple = ()) -> dict | None:
        async with self._lock:
            assert self._conn
            cur = await self._conn.execute(sql, params)
            row = await cur.fetchone()
            return dict(row) if row else None

    async def all(self, sql: str, params: tuple = ()) -> list[dict]:
        async with self._lock:
            assert self._conn
            cur = await self._conn.execute(sql, params)
            return [dict(r) for r in await cur.fetchall()]

    # ---------- قفل بین پروسه ها ----------
    async def try_lock(self, key: str, ttl: float = 10.0) -> bool:
        now = time.time()
        await self.execute("DELETE FROM locks WHERE expires_at < ?", (now,))
        try:
            await self.execute("INSERT INTO locks(key, expires_at) VALUES(?, ?)", (key, now + ttl))
            return True
        except aiosqlite.IntegrityError:
            return False

    async def lock(self, key: str, ttl: float = 10.0, wait: float = 4.0) -> bool:
        end = time.monotonic() + wait
        while True:
            if await self.try_lock(key, ttl):
                return True
            if time.monotonic() > end:
                return False
            await asyncio.sleep(0.05)

    async def extend_lock(self, key: str, ttl: float) -> None:
        await self.execute("UPDATE locks SET expires_at = ? WHERE key = ?", (time.time() + ttl, key))

    async def unlock(self, key: str) -> None:
        await self.execute("DELETE FROM locks WHERE key = ?", (key,))

    # ---------- بازیکن ----------
    async def player(self, tg_id: int, name: str = "", username: str | None = None,
                     photo: str | None = None) -> dict:
        """ساخت یا به روز کردن بازیکن با نام و عکس پروفایل تلگرام.

        نام در صفحه بقیه بازیکن ها نشان داده می شود؛ نویسه هایی که در HTML معنی
        دارند همین جا حذف می شوند (جلوگیری از XSS). photo=None یعنی عکس دست نخورد
        (مثلا پیام ربات که photo_url ندارد)؛ رشته خالی یعنی کاربر عکسش را پنهان کرده.
        pic کلید تصادفی آدرس /gc/pic/<pic> است تا آیدی تلگرام کسی در آدرس عکس نیاید.
        """
        name = _clean(name)
        username = _clean(username or "") or None
        now = int(time.time())
        await self.execute(
            "INSERT OR IGNORE INTO players(tg_id, name, username, av, pic, created_at, seen_at) VALUES(?,?,?,?,?,?,?)",
            (tg_id, name[:40], username, tg_id % 23 + 1, secrets.token_urlsafe(9), now, now),
        )
        if name:
            await self.execute("UPDATE players SET name=?, username=?, seen_at=? WHERE tg_id=?",
                               (name[:40], username, now, tg_id))
        if photo is not None:
            await self.execute("UPDATE players SET photo=? WHERE tg_id=?", (photo[:400], tg_id))
        await self.execute("UPDATE players SET pic=? WHERE tg_id=? AND pic=''", (secrets.token_urlsafe(9), tg_id))
        return await self.one("SELECT * FROM players WHERE tg_id = ?", (tg_id,))  # type: ignore[return-value]

    # ---------- گفتگو ----------
    async def add_chat(self, match_id: str, tg_id: int, color: str, text: str) -> int:
        async with self._lock:
            assert self._conn
            cur = await self._conn.execute(
                "INSERT INTO chat(match_id, tg_id, color, text, created_at) VALUES(?,?,?,?,?)",
                (match_id, tg_id, color, text, time.time()))
            await self._conn.commit()
            return int(cur.lastrowid or 0)

    async def chat_since(self, match_id: str, since_id: int, limit: int = 40) -> list[dict]:
        rows = await self.all(
            "SELECT c.id, c.tg_id, c.color, c.text, c.created_at, p.name, p.av, p.photo, p.pic FROM chat c "
            "LEFT JOIN players p ON p.tg_id = c.tg_id WHERE c.match_id = ? AND c.id > ? ORDER BY c.id DESC LIMIT ?",
            (match_id, since_id, limit))
        return rows[::-1]

    async def chat_recent(self, match_id: str, tg_id: int, seconds: float) -> int:
        row = await self.one("SELECT COUNT(*) AS n FROM chat WHERE match_id = ? AND tg_id = ? AND created_at > ?",
                             (match_id, tg_id, time.time() - seconds))
        return int(row["n"]) if row else 0

    async def player_by_pic(self, pic: str) -> dict | None:
        return await self.one("SELECT * FROM players WHERE pic = ? AND pic != ''", (pic,))

    async def get_player(self, tg_id: int) -> dict | None:
        return await self.one("SELECT * FROM players WHERE tg_id = ?", (tg_id,))

    async def set_flag(self, tg_id: int, field: str, value: int) -> None:
        if field not in ("show_spend", "tutorial", "sound"):
            raise ValueError(field)
        await self.execute(f"UPDATE players SET {field} = ? WHERE tg_id = ?", (value, tg_id))

    # ---------- امتیاز ----------
    async def debit(self, tg_id: int, amount: int) -> bool:
        if amount <= 0:
            return False
        return await self.execute(
            "UPDATE players SET points = points - ? WHERE tg_id = ? AND points >= ?",
            (amount, tg_id, amount)) == 1

    async def credit(self, tg_id: int, amount: int) -> bool:
        if amount <= 0:
            return False
        return await self.execute("UPDATE players SET points = points + ? WHERE tg_id = ?", (amount, tg_id)) == 1

    async def add_ledger(self, tg_id: int, kind: str, amount: int, note: str = "", ref: str = "",
                         idem: str | None = None, status: str = "done") -> int | None:
        """None یعنی همین idem قبلا ثبت شده."""
        try:
            return await self.insert(
                "INSERT INTO ledger(tg_id, kind, amount, note, ref, idem, status, created_at) VALUES(?,?,?,?,?,?,?,?)",
                (tg_id, kind, amount, note[:120], ref, idem, status, int(time.time())))
        except aiosqlite.IntegrityError:
            return None

    async def ledger_by_idem(self, idem: str) -> dict | None:
        return await self.one("SELECT * FROM ledger WHERE idem = ?", (idem,))

    async def set_ledger_status(self, ledger_id: int, status: str, amount: int | None = None) -> None:
        if amount is None:
            await self.execute("UPDATE ledger SET status = ? WHERE id = ?", (status, ledger_id))
        else:
            await self.execute("UPDATE ledger SET status = ?, amount = ? WHERE id = ?", (status, amount, ledger_id))

    async def history(self, tg_id: int, limit: int = 30) -> list[dict]:
        return await self.all(
            "SELECT kind, amount, note, status, created_at FROM ledger WHERE tg_id = ? AND status != 'failed' "
            "ORDER BY id DESC LIMIT ?", (tg_id, limit))

    # ---------- میز ----------
    async def get_match(self, match_id: str) -> dict | None:
        row = await self.one("SELECT * FROM matches WHERE id = ?", (match_id,))
        if row:
            row["cfg"] = json.loads(row["cfg"])
            row["state"] = json.loads(row["state"])
        return row

    async def create_match(self, match_id: str, status: str, cfg: dict, state: dict, host: int | None,
                           invite: str | None = None) -> None:
        now = int(time.time())
        await self.execute(
            "INSERT INTO matches(id, game, status, cfg, state, version, host, invite, created_at, updated_at) "
            "VALUES(?,?,?,?,?,0,?,?,?,?)",
            (match_id, cfg.get("game") or "ludo", status, json.dumps(cfg), json.dumps(state, ensure_ascii=False),
             host, invite, now, now))

    async def match_game(self, match_id: str | None) -> str:
        row = await self.one("SELECT game FROM matches WHERE id = ?", (match_id,)) if match_id else None
        return (row or {}).get("game") or "ludo"

    async def save_match(self, match_id: str, version: int, status: str, state: dict) -> bool:
        """فقط اگر کسی در این فاصله ننوشته باشد ذخیره می شود.

        وقتی میز تمام یا بسته شد، گفتگوی آن میز هم پاک می شود (نگه داشته نمی شود)."""
        ok = await self.execute(
            "UPDATE matches SET state = ?, status = ?, version = version + 1, updated_at = ? "
            "WHERE id = ? AND version = ?",
            (json.dumps(state, ensure_ascii=False), status, int(time.time()), match_id, version)) == 1
        if ok and status in ("over", "cancelled"):
            await self.execute("DELETE FROM chat WHERE match_id = ?", (match_id,))
        return ok

    async def match_by_invite(self, code: str) -> dict | None:
        row = await self.one("SELECT id FROM matches WHERE invite = ?", (code,))
        return await self.get_match(row["id"]) if row else None

    async def add_match_player(self, match_id: str, tg_id: int, color: str, paid: int) -> bool:
        try:
            await self.execute("INSERT INTO match_players(match_id, tg_id, color, paid) VALUES(?,?,?,?)",
                               (match_id, tg_id, color, paid))
            return True
        except aiosqlite.IntegrityError:
            return False

    async def match_players(self, match_id: str) -> list[dict]:
        return await self.all("SELECT * FROM match_players WHERE match_id = ?", (match_id,))

    async def active_match_of(self, tg_id: int) -> str | None:
        row = await self.one(
            "SELECT mp.match_id FROM match_players mp JOIN matches m ON m.id = mp.match_id "
            "WHERE mp.tg_id = ? AND mp.active = 1 AND m.status IN ('lobby','playing') "
            "ORDER BY m.created_at DESC LIMIT 1", (tg_id,))
        return row["match_id"] if row else None

    async def active_matches_of(self, tg_id: int) -> list[str]:
        rows = await self.all(
            "SELECT mp.match_id FROM match_players mp JOIN matches m ON m.id = mp.match_id "
            "WHERE mp.tg_id = ? AND mp.active = 1 AND m.status IN ('lobby','playing') "
            "ORDER BY m.created_at DESC LIMIT 5", (tg_id,))
        return [r["match_id"] for r in rows]

    async def deactivate(self, match_id: str, tg_id: int | None = None) -> None:
        if tg_id is None:
            await self.execute("UPDATE match_players SET active = 0 WHERE match_id = ?", (match_id,))
        else:
            await self.execute("UPDATE match_players SET active = 0 WHERE match_id = ? AND tg_id = ?",
                               (match_id, tg_id))

    async def mark_settled(self, match_id: str) -> bool:
        return await self.execute("UPDATE matches SET settled = 1 WHERE id = ? AND settled = 0", (match_id,)) == 1

    async def add_result(self, match_id: str, tg_id: int, won: bool, prize: int) -> None:
        try:
            await self.execute("INSERT INTO results(match_id, tg_id, won, prize, created_at) VALUES(?,?,?,?,?)",
                               (match_id, tg_id, int(won), prize, int(time.time())))
        except aiosqlite.IntegrityError:
            return
        await self.execute("UPDATE players SET games = games + 1, wins = wins + ? WHERE tg_id = ?",
                           (int(won), tg_id))

    # ---------- صف ----------
    async def queue_row(self, tg_id: int) -> dict | None:
        return await self.one("SELECT * FROM queue WHERE tg_id = ?", (tg_id,))

    async def queue_put(self, tg_id: int, cfg_key: str, cfg: dict, held: int) -> None:
        await self.execute(
            "INSERT OR REPLACE INTO queue(tg_id, cfg_key, cfg, held, claimed, created_at) VALUES(?,?,?,?,NULL,?)",
            (tg_id, cfg_key, json.dumps(cfg), held, time.time()))

    async def queue_waiting(self, cfg_key: str) -> list[dict]:
        return await self.all(
            "SELECT * FROM queue WHERE cfg_key = ? AND claimed IS NULL ORDER BY created_at", (cfg_key,))

    async def queue_claim(self, tg_ids: list[int], match_id: str) -> None:
        q = ",".join("?" * len(tg_ids))
        await self.execute(f"UPDATE queue SET claimed = ? WHERE tg_id IN ({q}) AND claimed IS NULL",
                           (match_id, *tg_ids))

    async def queue_del(self, tg_id: int) -> None:
        await self.execute("DELETE FROM queue WHERE tg_id = ?", (tg_id,))

    # ---------- رده بندی ----------
    async def top_players(self, since: int, limit: int = 10) -> list[dict]:
        return await self.all(
            "SELECT r.tg_id, p.name, p.av, p.photo, p.pic, SUM(r.won) AS wins, SUM(r.prize) AS value "
            "FROM results r JOIN players p ON p.tg_id = r.tg_id WHERE r.created_at >= ? "
            "GROUP BY r.tg_id HAVING wins > 0 ORDER BY value DESC, wins DESC LIMIT ?", (since, limit))

    async def top_spenders(self, since: int, limit: int = 10) -> list[dict]:
        return await self.all(
            "SELECT l.tg_id, p.name, p.av, p.photo, p.pic, -SUM(l.amount) AS value FROM ledger l "
            "JOIN players p ON p.tg_id = l.tg_id "
            "WHERE l.kind IN ('entry','refund','shop','transfer') AND l.status = 'done' AND l.created_at >= ? "
            "AND p.show_spend = 1 GROUP BY l.tg_id HAVING value > 0 ORDER BY value DESC LIMIT ?", (since, limit))

    async def my_value(self, tg_id: int, since: int, kind: str) -> dict:
        if kind == "top":
            row = await self.one("SELECT COALESCE(SUM(won),0) AS wins, COUNT(*) AS games, COALESCE(SUM(prize),0) AS value "
                                 "FROM results WHERE tg_id = ? AND created_at >= ?", (tg_id, since))
        else:
            row = await self.one("SELECT COALESCE(-SUM(amount),0) AS value FROM ledger WHERE tg_id = ? AND "
                                 "kind IN ('entry','refund','shop','transfer') AND status='done' AND created_at >= ?",
                                 (tg_id, since))
        return row or {"value": 0}

    # ---------- حضور و اعلان ----------
    async def touch(self, match_id: str, tg_id: int) -> None:
        """ثبت حضور؛ برای کم کردن نوشتن، حداکثر هر ۳ ثانیه یک بار (حافظه پروسه جلوی پرسش های اضافه را می گیرد)."""
        now = time.time()
        memo = self.__dict__.setdefault("_touched", {})
        if now - memo.get((match_id, tg_id), 0) < 3:
            return
        memo[(match_id, tg_id)] = now
        if len(memo) > 5000:
            memo.clear()
        await self.execute(
            "INSERT INTO presence(match_id, tg_id, seen) VALUES(?,?,?) "
            "ON CONFLICT(match_id, tg_id) DO UPDATE SET seen = excluded.seen WHERE seen < excluded.seen - 3",
            (match_id, tg_id, now))

    async def seen(self, match_id: str, tg_id: int) -> float:
        row = await self.one("SELECT seen FROM presence WHERE match_id = ? AND tg_id = ?", (match_id, tg_id))
        return float(row["seen"]) if row else 0.0

    async def ping_once(self, key: str) -> bool:
        try:
            await self.execute("INSERT INTO pings(key, created_at) VALUES(?, ?)", (key, int(time.time())))
            return True
        except aiosqlite.IntegrityError:
            return False

    async def ping_count(self, prefix: str) -> int:
        row = await self.one("SELECT COUNT(*) AS n FROM pings WHERE key LIKE ?", (prefix + "%",))
        return int(row["n"]) if row else 0

    # ---------- آمار ادمین ----------
    async def stats(self, since: int) -> dict:
        q = lambda sql, *a: self.one(sql, a)  # noqa: E731
        return {
            "players": (await q("SELECT COUNT(*) AS n FROM players"))["n"],
            "points": (await q("SELECT COALESCE(SUM(points),0) AS n FROM players"))["n"],
            "playing": (await q("SELECT COUNT(*) AS n FROM matches WHERE status = 'playing'"))["n"],
            "lobby": (await q("SELECT COUNT(*) AS n FROM matches WHERE status = 'lobby'"))["n"],
            "queue": (await q("SELECT COUNT(*) AS n FROM queue WHERE claimed IS NULL"))["n"],
            "games": (await q("SELECT COUNT(DISTINCT match_id) AS n FROM results WHERE created_at >= ?", since))["n"],
            "charge": (await q("SELECT COALESCE(SUM(amount),0) AS n FROM ledger WHERE kind='charge' AND status='done' AND created_at >= ?", since))["n"],
            "entry": (await q("SELECT COALESCE(-SUM(amount),0) AS n FROM ledger WHERE kind='entry' AND status='done' AND created_at >= ?", since))["n"],
            "prize": (await q("SELECT COALESCE(SUM(amount),0) AS n FROM ledger WHERE kind='prize' AND status='done' AND created_at >= ?", since))["n"],
            "shop": (await q("SELECT COALESCE(-SUM(amount),0) AS n FROM ledger WHERE kind IN ('shop','transfer') AND status='done' AND created_at >= ?", since))["n"],
        }

    # ---------- ظاهر (میز و ورق) ----------
    async def owned_of(self, tg_id: int) -> set[str]:
        return {r["item"] for r in await self.all("SELECT item FROM owned WHERE tg_id = ?", (tg_id,))}

    async def add_owned(self, tg_id: int, item: str) -> None:
        await self.execute("INSERT OR IGNORE INTO owned(tg_id, item, created_at) VALUES(?,?,?)", (tg_id, item, int(time.time())))

    async def set_skin(self, tg_id: int, kind: str, look: str) -> None:
        col = {"table": "table_skin", "cards": "card_skin"}[kind]
        await self.execute(f"UPDATE players SET {col} = ? WHERE tg_id = ?", (look, tg_id))

    # ---------- پنل مدیریت ----------
    async def admin_stats(self, now: int) -> dict:
        """آمار صفحه اول پنل: امروز، ۷ روز و کل."""
        q = lambda sql, *a: self.one(sql, a)  # noqa: E731
        day, week = now - 86400, now - 7 * 86400
        out = {"all": await self.stats(0), "day": await self.stats(day), "week": await self.stats(week)}
        out["new_day"] = (await q("SELECT COUNT(*) AS n FROM players WHERE created_at >= ?", day))["n"]
        out["new_week"] = (await q("SELECT COUNT(*) AS n FROM players WHERE created_at >= ?", week))["n"]
        out["active_day"] = (await q("SELECT COUNT(*) AS n FROM players WHERE seen_at >= ?", day))["n"]
        out["active_week"] = (await q("SELECT COUNT(*) AS n FROM players WHERE seen_at >= ?", week))["n"]
        out["banned"] = (await q("SELECT COUNT(*) AS n FROM players WHERE banned = 1"))["n"]
        out["online"] = (await q("SELECT COUNT(DISTINCT tg_id) AS n FROM presence WHERE seen >= ?", now - 60))["n"]
        out["by_game"] = {r["game"]: r["n"] for r in await self.all(
            "SELECT m.game AS game, COUNT(DISTINCT r.match_id) AS n FROM results r JOIN matches m ON m.id = r.match_id "
            "WHERE r.created_at >= ? GROUP BY m.game", (week,))}
        out["live_by_game"] = {r["game"]: r["n"] for r in await self.all(
            "SELECT game, COUNT(*) AS n FROM matches WHERE status = 'playing' GROUP BY game")}
        return out

    async def admin_daily(self, now: int, days: int = 14) -> list[dict]:
        """نمودار روزانه: بازی تمام شده، بازیکن تازه و شارژ هر روز (روز به وقت تهران تقریبی: UTC+3:30)."""
        tz = 12600
        start = (now + tz) // 86400 * 86400 - tz - (days - 1) * 86400
        bucket = lambda col: f"CAST(({col} - {start}) / 86400 AS INTEGER)"  # noqa: E731
        games = {r["d"]: r["n"] for r in await self.all(
            f"SELECT {bucket('created_at')} AS d, COUNT(DISTINCT match_id) AS n FROM results WHERE created_at >= ? GROUP BY d", (start,))}
        new = {r["d"]: r["n"] for r in await self.all(
            f"SELECT {bucket('created_at')} AS d, COUNT(*) AS n FROM players WHERE created_at >= ? GROUP BY d", (start,))}
        charge = {r["d"]: r["n"] for r in await self.all(
            f"SELECT {bucket('created_at')} AS d, SUM(amount) AS n FROM ledger WHERE kind = 'charge' AND status = 'done' "
            "AND created_at >= ? GROUP BY d", (start,))}
        return [{"t": start + i * 86400, "games": games.get(i, 0), "new": new.get(i, 0), "charge": charge.get(i, 0) or 0}
                for i in range(days)]

    async def admin_players(self, q: str = "", sort: str = "recent", filt: str = "all",
                            offset: int = 0, limit: int = 30) -> list[dict]:
        where, args = [], []
        q = (q or "").strip().lstrip("@")
        if q:
            if q.isdigit():
                where.append("(tg_id = ? OR name LIKE ?)")
                args += [int(q), f"%{q}%"]
            else:
                where.append("(name LIKE ? OR username LIKE ?)")
                args += [f"%{q}%", f"%{q}%"]
        if filt == "banned":
            where.append("banned = 1")
        elif filt == "active":
            where.append("seen_at >= ?")
            args.append(int(time.time()) - 7 * 86400)
        elif filt == "rich":
            where.append("points > 0")
        order = {"recent": "seen_at DESC", "new": "created_at DESC", "points": "points DESC",
                 "games": "games DESC", "wins": "wins DESC"}.get(sort, "seen_at DESC")
        sql = ("SELECT tg_id, name, username, av, pic, points, games, wins, banned, created_at, seen_at FROM players"
               + (" WHERE " + " AND ".join(where) if where else "") + f" ORDER BY {order}, tg_id LIMIT ? OFFSET ?")
        return await self.all(sql, (*args, limit, offset))

    async def set_ban(self, tg_id: int, banned: bool, note: str = "") -> bool:
        return bool(await self.execute("UPDATE players SET banned = ?, ban_note = ? WHERE tg_id = ?",
                                       (1 if banned else 0, note[:200] if banned else "", tg_id)))

    async def ledger_of(self, tg_id: int, limit: int = 40) -> list[dict]:
        return await self.all("SELECT id, kind, amount, note, status, created_at FROM ledger WHERE tg_id = ? "
                              "ORDER BY id DESC LIMIT ?", (tg_id, limit))

    async def ledger_recent(self, kind: str = "", offset: int = 0, limit: int = 40) -> list[dict]:
        where, args = "", []
        if kind:
            where, args = "WHERE l.kind = ?", [kind]
        return await self.all(
            "SELECT l.id, l.tg_id, l.kind, l.amount, l.note, l.status, l.created_at, p.name FROM ledger l "
            f"LEFT JOIN players p ON p.tg_id = l.tg_id {where} ORDER BY l.id DESC LIMIT ? OFFSET ?", (*args, limit, offset))

    async def results_of(self, tg_id: int, limit: int = 15) -> list[dict]:
        return await self.all(
            "SELECT r.match_id, r.won, r.prize, r.created_at, m.game, m.cfg FROM results r "
            "LEFT JOIN matches m ON m.id = r.match_id WHERE r.tg_id = ? ORDER BY r.created_at DESC LIMIT ?", (tg_id, limit))

    async def matches_by_status(self, statuses: tuple[str, ...], offset: int = 0, limit: int = 30) -> list[dict]:
        marks = ",".join("?" * len(statuses))
        rows = await self.all(f"SELECT id FROM matches WHERE status IN ({marks}) ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                              (*statuses, limit, offset))
        out = []
        for r in rows:
            m = await self.get_match(r["id"])
            if m:
                out.append(m)
        return out

    async def match_players_named(self, match_id: str) -> list[dict]:
        return await self.all(
            "SELECT mp.tg_id, mp.color, mp.paid, mp.active, p.name, p.username FROM match_players mp "
            "LEFT JOIN players p ON p.tg_id = mp.tg_id WHERE mp.match_id = ?", (match_id,))

    async def log_admin(self, admin: int, action: str, target: str = "", detail: str = "") -> None:
        await self.insert("INSERT INTO admin_log(admin, action, target, detail, created_at) VALUES(?,?,?,?,?)",
                          (admin, action, str(target)[:80], str(detail)[:400], int(time.time())))

    async def admin_log(self, offset: int = 0, limit: int = 40) -> list[dict]:
        return await self.all("SELECT * FROM admin_log ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))

    async def settings_all(self) -> dict:
        return {r["key"]: r["value"] for r in await self.all("SELECT key, value FROM settings")}

    async def setting_put(self, key: str, value: str | None) -> None:
        if value is None:
            await self.execute("DELETE FROM settings WHERE key = ?", (key,))
        else:
            await self.execute("INSERT INTO settings(key, value, updated_at) VALUES(?,?,?) ON CONFLICT(key) "
                               "DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                               (key, value, int(time.time())))

    # پیام همگانی
    @staticmethod
    def _bc_where(target: str) -> tuple[str, list]:
        """شرط مخاطبان: all، seen:<ts> (فعال از آن زمان)، game:<name> (کسانی که آن بازی را کرده اند)، id:<tg>"""
        kind, _, arg = (target or "all").partition(":")
        if kind == "seen" and arg.isdigit():
            return "banned = 0 AND seen_at >= ?", [int(arg)]
        if kind == "game" and arg:
            return ("banned = 0 AND tg_id IN (SELECT mp.tg_id FROM match_players mp JOIN matches m ON m.id = mp.match_id "
                    "WHERE m.game = ?)", [arg])
        if kind == "id" and arg.isdigit():
            return "tg_id = ?", [int(arg)]
        return "banned = 0", []

    async def bc_count(self, target: str) -> int:
        w, a = self._bc_where(target)
        row = await self.one(f"SELECT COUNT(*) AS n FROM players WHERE {w}", tuple(a))
        return int(row["n"]) if row else 0

    async def bc_targets(self, target: str, after: int, limit: int) -> list[int]:
        w, a = self._bc_where(target)
        rows = await self.all(f"SELECT tg_id FROM players WHERE {w} AND tg_id > ? ORDER BY tg_id LIMIT ?", (*a, after, limit))
        return [r["tg_id"] for r in rows]

    async def bc_create(self, admin: int, target: str, text: str = "", button: str = "",
                        src_chat: int | None = None, src_msg: int | None = None) -> int:
        total = await self.bc_count(target)
        return await self.insert(
            "INSERT INTO broadcasts(admin, text, src_chat, src_msg, button, target, total, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (admin, text, src_chat, src_msg, button, target, total, int(time.time())))

    async def bc_get(self, bid: int) -> dict | None:
        return await self.one("SELECT * FROM broadcasts WHERE id = ?", (bid,))

    async def bc_list(self, limit: int = 15) -> list[dict]:
        return await self.all("SELECT * FROM broadcasts ORDER BY id DESC LIMIT ?", (limit,))

    async def bc_active(self) -> list[dict]:
        return await self.all("SELECT * FROM broadcasts WHERE status = 'active' ORDER BY id")

    async def bc_progress(self, bid: int, cursor: int, sent: int, failed: int, blocked: int) -> None:
        await self.execute("UPDATE broadcasts SET cursor = ?, sent = sent + ?, failed = failed + ?, blocked = blocked + ? "
                           "WHERE id = ?", (cursor, sent, failed, blocked, bid))

    async def bc_finish(self, bid: int, status: str) -> bool:
        return bool(await self.execute("UPDATE broadcasts SET status = ?, finished_at = ? WHERE id = ? AND status = 'active'",
                                       (status, int(time.time()), bid)))

    # ---------- خبرم کن ----------
    async def toggle_notify(self, tg_id: int, game: str) -> bool:
        if await self.execute("DELETE FROM notify WHERE tg_id = ? AND game = ?", (tg_id, game)):
            return False
        await self.execute("INSERT INTO notify(tg_id, game, created_at) VALUES(?,?,?)", (tg_id, game, int(time.time())))
        return True

    async def notify_of(self, tg_id: int) -> list[str]:
        return [r["game"] for r in await self.all("SELECT game FROM notify WHERE tg_id = ?", (tg_id,))]
