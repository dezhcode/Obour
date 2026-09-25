"""استوریج FSM روی SQLite.

چرا لازم است؟
روی هاست سی پنل، پسنجر پروسه اپ را بعد از چند دقیقه بیکاری می خواباند و
با درخواست بعدی دوباره بالا می آورد. با MemoryStorage هر بار که این اتفاق
بیفتد وضعیت کاربر (مثلا وسط وارد کردن مبلغ شارژ) پاک می شود و کاربر گیر
می کند. با این استوریج، وضعیت در همان دیتابیس ربات ذخیره می شود و
ری استارت شدن پروسه هیچ اثری ندارد.
"""
from __future__ import annotations

import json
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from .db import Database
from .utils import now_str


def _key(key: StorageKey) -> str:
    """ساخت کلید یکتا. با getattr نوشته شده تا با نسخه های مختلف aiogram
    که فیلدهای جدید اضافه کرده اند (thread_id, business_connection_id) بسازد."""
    parts = [
        str(key.bot_id),
        str(key.chat_id),
        str(key.user_id),
        str(getattr(key, "thread_id", None) or 0),
        str(getattr(key, "business_connection_id", None) or "-"),
        str(getattr(key, "destiny", "default")),
    ]
    return ":".join(parts)


class SQLiteStorage(BaseStorage):
    def __init__(self, db: Database) -> None:
        self.db = db

    async def _row(self, key: StorageKey):  # noqa: ANN202
        return await self.db.fetchone(
            "SELECT state, data FROM fsm_state WHERE key = ?", (_key(key),)
        )

    async def set_state(self, key: StorageKey, state: State | str | None = None) -> None:
        value = state.state if isinstance(state, State) else state
        await self.db.execute(
            "INSERT INTO fsm_state(key, state, data, updated_at) VALUES (?, ?, '{}', ?) "
            "ON CONFLICT(key) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at",
            (_key(key), value, now_str()),
        )

    async def get_state(self, key: StorageKey) -> str | None:
        row = await self._row(key)
        return row["state"] if row else None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        await self.db.execute(
            "INSERT INTO fsm_state(key, state, data, updated_at) VALUES (?, NULL, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (_key(key), json.dumps(data, ensure_ascii=False), now_str()),
        )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        row = await self._row(key)
        if not row or not row["data"]:
            return {}
        try:
            return json.loads(row["data"])
        except (ValueError, TypeError):
            return {}

    async def update_data(self, key: StorageKey, data: dict[str, Any]) -> dict[str, Any]:
        current = await self.get_data(key)
        current.update(data)
        await self.set_data(key, current)
        return current

    async def close(self) -> None:
        return None
