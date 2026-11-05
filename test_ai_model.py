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

        # ۷) آمار ادمین: مدل و کد خطا هر درخواست ثبت می شود و ai_stats جمع می زند
        async def broke(payload: dict, timeout: float) -> str:
            raise assistant.AIError("bad key", "auth")

        await db.execute("DELETE FROM ai_log")
        u = await db.get_or_create_user(111, "ali", "Ali")
        await admin_ops.save_setting(db, "ai_model", "mini", 1)
        assistant.set_transport(fake)
        await assistant.ask("a", kind="support", db=db, user_id=u["id"])
        await assistant.ask("b", kind="fix", db=db, user_id=u["id"], image=b"\xff\xd8x")
        assistant.set_transport(broke)
        try:
            await assistant.ask("c", kind="support", db=db, user_id=u["id"])
            raise SystemExit("expected AIError")
        except assistant.AIError:
            pass
        st = await db.ai_stats(1)
        assert st["total"]["n"] == 3 and st["total"]["bad"] == 1 and st["total"]["users"] == 1, st
        assert st["kinds"]["support"]["n"] == 2 and st["kinds"]["fix"]["n"] == 1, st
        assert st["models"]["mini"]["n"] == 3, st
        assert st["errors"] == {"auth": 1}, st
        assert (await db.ai_stats(30))["total"]["n"] == 3
        from app.handlers import assist as hassist
        html = hassist.stats_html(st, 1, "mini")
        assert "3" in html and "mini" in html and "کلید اشتباه" in html, html
        empty = {"total": {"n": 0, "bad": 0, "ms": 0, "users": 0}, "kinds": {}, "models": {}, "errors": {}, "daily": []}
        assert "درخواستی ثبت نشده" in hassist.stats_html(empty, 7, "")
        print("OK stats")
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
