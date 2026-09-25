"""تست دود آزمایشی لایه دیتابیس - بعد از تست حذف می شود."""
import asyncio
import os
import sys

sys.path.insert(0, ".")

for suffix in ("", "-wal", "-shm"):
    try:
        os.remove("test_smoke.db" + suffix)
    except FileNotFoundError:
        pass

from app.db import Database


async def main() -> None:
    db = Database("test_smoke.db")
    await db.connect()

    # ۱) کاربر
    u = await db.get_or_create_user(111, "ali", "Ali", referred_by=None)
    assert u["balance"] == 0, "balance اولیه باید صفر باشد"
    u2 = await db.get_or_create_user(222, "reza", "Reza")
    print("OK users")

    # ۲) کسر اتمیک: با موجودی صفر باید شکست بخورد
    assert await db.atomic_debit(u["id"], 1000) is False, "کسر از موجودی صفر نباید موفق شود"
    await db.atomic_credit(u["id"], 100_000)
    assert await db.atomic_debit(u["id"], 30_000) is True
    fresh = await db.get_user(u["id"])
    assert fresh["balance"] == 70_000, f"balance غلط: {fresh['balance']}"
    # کسر بیشتر از موجودی
    assert await db.atomic_debit(u["id"], 999_999) is False
    assert (await db.get_user(u["id"]))["balance"] == 70_000, "موجودی نباید تغییر کند"
    print("OK atomic debit/credit")

    # ۳) idempotency
    t1 = await db.insert_transaction(u["id"], "purchase", -30_000, idem_key="buy:1:1:100")
    t2 = await db.insert_transaction(u["id"], "purchase", -30_000, idem_key="buy:1:1:100")
    assert t1 is not None and t2 is None, "idem_key تکراری باید None برگرداند"
    print("OK idempotency")

    # ۴) decide اتمیک (ضد تایید دوباره)
    d1 = await db.decide_transaction(t1, "approved", 999)
    d2 = await db.decide_transaction(t1, "rejected", 999)
    assert d1 is not None and d1["status"] == "approved"
    assert d2 is None, "تغییر وضعیت دوباره باید رد شود"
    print("OK decide transaction")

    # ۵) تنظیمات
    await db.set_setting("card_number", "6037-9911-2222-3333")
    assert await db.get_setting("card_number") == "6037-9911-2222-3333"
    assert await db.get_setting("min_charge", "0") == "50000"
    print("OK settings")

    # ۶) پلن و سرویس
    await db.execute(
        "INSERT INTO plans(title, data_gb, duration_days, price, is_active) VALUES ('محبوب', 20, 30, 79000, 1)"
    )
    plan = (await db.active_plans())[0]
    sid = await db.insert_service(u["id"], plan["id"], "obour_111_1", "https://x/sub", 20, 30, "2026-10-08T12:00:00")
    svc = await db.get_service(sid)
    assert svc["panel_username"] == "obour_111_1"
    print("OK plans/services")

    # ۶.۱) نام سرویس یکتا حتی بعد از حذف سرویس (باگ COUNT(*) نسخه قبل)
    n2 = await db.free_panel_username(111, u["id"])
    await db.execute("DELETE FROM services WHERE panel_username = ?", (n2,))
    n3 = await db.free_panel_username(111, u["id"])
    assert n2 != n3, "نام سرویس نباید بعد از حذف تکرار شود"
    print("OK unique service names:", n2, n3)

    # ۶.۲) قفل عملیات مالی
    assert await db.acquire_lock("pay:1") is True
    assert await db.acquire_lock("pay:1") is False, "قفل دوم نباید گرفته شود"
    await db.release_lock("pay:1")
    assert await db.acquire_lock("pay:1") is True
    print("OK op locks")

    # ۶.۳) تراکنش ناموفق پاک نمی شود
    tf = await db.insert_transaction(u["id"], "purchase", -1000, idem_key="fail:1")
    await db.fail_transaction(tf, "panel rejected")
    row = await db.get_transaction(tf)
    assert row and row["status"] == "failed" and row["reject_reason"]
    assert await db.approve_purchase(tf) is False, "تراکنش failed نباید approved شود"
    print("OK failed transactions kept")

    # ۶.۴) هم سفرها با آیدی تلگرام شمرده می شود
    assert await db.referral_count(111) == 0
    await db.get_or_create_user(333, "sara", "Sara", referred_by=111)
    assert await db.referral_count(111) == 1, "شمارش رفرال با آیدی تلگرام"
    print("OK referrals")

    # ۶.۵) سقف هر کاربر روی کد تخفیف
    did = await db.create_discount("TEST10", "percent", 10, max_uses=5, per_user_limit=1)
    assert await db.redeem_discount(did, u["id"], 100_000, 10_000) is True
    assert await db.redeem_discount(did, u["id"], 100_000, 10_000) is False
    print("OK discount per-user limit")

    # ۷) داشبورد
    stats = await db.dashboard_stats()
    assert stats["total_users"] == 3
    print("OK dashboard:", stats)

    await db.close()
    print("\nALL DB TESTS PASSED")


asyncio.run(main())
