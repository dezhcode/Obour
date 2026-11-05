"""تست مدل هوش مصنوعی دستیار: انتخاب مدل، فرستادن عکس و برگشت به پیش فرض.

    python test_ai_model.py

بدون شبکه؛ جای وب سرویس یک transport آزمایشی است.
"""
import asyncio
import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("AI_API_KEY", "test-key")

DB_FILE = "test_ai_model.db"
for suffix in ("", "-wal", "-shm"):
    try:
        os.remove(DB_FILE + suffix)
    except FileNotFoundError:
        pass

from app.config import config
from app.db import Database
from app.services import admin_ops, assistant


async def main() -> None:
    db = Database(DB_FILE)
    await db.connect()
    sent: list[dict] = []

    async def fake(payload: dict, timeout: float) -> str:
        sent.append(dict(payload))
        return "OK"

    assistant.set_transport(fake)
    try:
        # ۱) بدون تنظیم: مدلی فرستاده نمی شود (پیش فرض وب سرویس)
        assert await assistant.ask("hi", db=db) == "OK"
        assert "model" not in sent[-1], sent[-1]
        print("OK default model")

        # ۲) انتخاب ادمین در دیتابیس
        ok, val = await admin_ops.save_setting(db, "ai_model", "haiku", 1)
        assert ok and val == "haiku"
        await assistant.ask("hi", db=db)
        assert sent[-1]["model"] == "haiku", sent[-1]
        print("OK admin model")

        # ۳) عکس همراه مدل می رود
        await assistant.ask("what is this", image=b"\xff\xd8\xff-fake", db=db)
        assert sent[-1]["model"] == "haiku" and sent[-1]["image_base64"], sent[-1]
        print("OK image + model")

        # ۴) AI_MODEL در .env وقتی ادمین چیزی نگذاشته
        await admin_ops.save_setting(db, "ai_model", "-", 1)
        assert await db.get_setting("ai_model", "x") == ""
        config.ai_model = "luna"
        await assistant.ask("hi", db=db)
        assert sent[-1]["model"] == "luna", sent[-1]
        await assistant.ask("hi")                      # بدون db هم از env
        assert sent[-1]["model"] == "luna", sent[-1]
        print("OK env model")

        # ۵) اعتبارسنجی نام مدل
        assert admin_ops.clean_setting("ai_model", "gpt-5.4-mini") == (True, "gpt-5.4-mini")
        assert admin_ops.clean_setting("ai_model", "") == (True, "")
        assert admin_ops.clean_setting("ai_model", "bad model!")[0] is False
        print("OK model validation")

        # ۶) مدل ناشناخته: یک بار با پیش فرض وب سرویس امتحان می شود
        calls: list[dict] = []

        async def picky(payload: dict, timeout: float) -> str:
            calls.append(dict(payload))
            if "model" in payload:
                raise assistant.AIError("unknown model; GET /api/models lists the available ones", "bad_request")
            return "fine"

        assistant.set_transport(picky)
        assert await assistant.ask("hi", db=db) == "fine"
        assert len(calls) == 2 and "model" in calls[0] and "model" not in calls[1], calls
        print("OK unknown model fallback")
    finally:
        assistant.set_transport(None)
        await db.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(DB_FILE + suffix)
            except FileNotFoundError:
                pass
    print("ALL OK")


if __name__ == "__main__":
    asyncio.run(main())
