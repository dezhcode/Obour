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

CREATE TABLE IF NOT EXISTS locks (
  key TEXT PRIMARY KEY,
  expires_at REAL NOT NULL
);
"""


_UNSAFE = re.compile(r"[<>&\"'`\\]|[\u0000-\u001f\u200e\u200f\u202a-\u202e]")


def _clean(text: str) -> str:
    return _UNSAFE.sub("", text or "").strip()[:40]


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

    async def unlock(self, key: str) -> None:
        await self.execute("DELETE FROM locks WHERE key = ?", (key,))

    # ---------- بازیکن ----------
    async def player(self, tg_id: int, name: str = "", username: str | None = None) -> dict:
        # نام از پروفایل تلگرام می آید و در صفحه بقیه بازیکن ها نشان داده می شود؛
        # نویسه هایی که در HTML معنی دارند همین جا حذف می شوند (جلوگیری از XSS)
        name = _clean(name)
        username = _clean(username or "") or None
        now = int(time.time())
        await self.execute(
            "INSERT OR IGNORE INTO players(tg_id, name, username, av, created_at, seen_at) VALUES(?,?,?,?,?,?)",
            (tg_id, name[:40], username, tg_id % 23 + 1, now, now),
        )
        if name:
            await self.execute("UPDATE players SET name=?, username=?, seen_at=? WHERE tg_id=?",
                               (name[:40], username, now, tg_id))
        return await self.one("SELECT * FROM players WHERE tg_id = ?", (tg_id,))  # type: ignore[return-value]

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
            "INSERT INTO matches(id, status, cfg, state, version, host, invite, created_at, updated_at) "
            "VALUES(?,?,?,?,0,?,?,?,?)",
            (match_id, status, json.dumps(cfg), json.dumps(state, ensure_ascii=False), host, invite, now, now))

    async def save_match(self, match_id: str, version: int, status: str, state: dict) -> bool:
        """فقط اگر کسی در این فاصله ننوشته باشد ذخیره می شود."""
        return await self.execute(
            "UPDATE matches SET state = ?, status = ?, version = version + 1, updated_at = ? "
            "WHERE id = ? AND version = ?",
            (json.dumps(state, ensure_ascii=False), status, int(time.time()), match_id, version)) == 1

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
            "SELECT r.tg_id, p.name, p.av, SUM(r.won) AS wins, SUM(r.prize) AS value "
            "FROM results r JOIN players p ON p.tg_id = r.tg_id WHERE r.created_at >= ? "
            "GROUP BY r.tg_id HAVING wins > 0 ORDER BY value DESC, wins DESC LIMIT ?", (since, limit))

    async def top_spenders(self, since: int, limit: int = 10) -> list[dict]:
        return await self.all(
            "SELECT l.tg_id, p.name, p.av, -SUM(l.amount) AS value FROM ledger l "
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

    # ---------- خبرم کن ----------
    async def toggle_notify(self, tg_id: int, game: str) -> bool:
        if await self.execute("DELETE FROM notify WHERE tg_id = ? AND game = ?", (tg_id, game)):
            return False
        await self.execute("INSERT INTO notify(tg_id, game, created_at) VALUES(?,?,?)", (tg_id, game, int(time.time())))
        return True

    async def notify_of(self, tg_id: int) -> list[str]:
        return [r["game"] for r in await self.all("SELECT game FROM notify WHERE tg_id = ?", (tg_id,))]
