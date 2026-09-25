"""پاداش هم سفرها.

قاعده: پاداش وقتی داده می شود که کاربر دعوت شده «خرید موفق» انجام دهد
(خرید پلن، ساخت دلخواه یا تمدید). صرف استارت زدن پاداشی ندارد، وگرنه
با چند اکانت الکی می شد کیف پول پر کرد.

مبلغ پاداش = درصدی از مبلغی که واقعا از کیف پول کاربر کم شده، به علاوه
پاداش ثابت اولین خرید (اگر در env تنظیم شده باشد).

این تابع هیچ وقت نباید جریان خرید را بشکند؛ هر خطایی فقط لاگ می شود.
"""
from __future__ import annotations

import logging

from app import effects, texts
from app.config import config
from app.db import Database
from app.utils import esc

log = logging.getLogger("obour.referral")


async def reward_purchase(
    bot,  # noqa: ANN001
    db: Database,
    user: dict,
    amount: int,
    txn_id: int | None,
    reason: str = "خرید",
) -> int:
    """پاداش خرید کاربر را به معرفش می دهد. خروجی: مبلغ واریز شده."""
    try:
        return await _reward(bot, db, user, amount, txn_id, reason)
    except Exception:  # noqa: BLE001
        log.exception("ثبت پاداش معرفی ناموفق بود (txn=%s)", txn_id)
        return 0


async def _reward(
    bot,  # noqa: ANN001
    db: Database,
    user: dict,
    amount: int,
    txn_id: int | None,
    reason: str,
) -> int:
    if not config.ref_enabled or amount <= 0:
        return 0
    if amount < config.ref_min_order:
        return 0

    ref_tg = user.get("referred_by")
    if not ref_tg:
        return 0

    referrer = await db.get_user_by_tg(int(ref_tg))
    if not referrer or referrer["id"] == user["id"] or referrer["is_blocked"]:
        return 0

    reward = amount * max(0, config.ref_percent) // 100
    if config.ref_max_reward > 0:
        reward = min(reward, config.ref_max_reward)

    first = not await db.invitee_rewarded_before(user["id"])
    if first:
        reward += max(0, config.ref_first_bonus)
    if reward <= 0:
        return 0

    # اول ثبت، بعد واریز. اگر این خرید قبلا پاداش گرفته، ثبت رد می شود.
    kind = "first" if first else "purchase"
    if not await db.record_referral_earning(
        referrer_id=referrer["id"],
        invitee_id=user["id"],
        txn_id=txn_id,
        order_amount=amount,
        reward=reward,
        kind=kind,
    ):
        log.info("پاداش تکراری برای تراکنش %s نادیده گرفته شد", txn_id)
        return 0

    if not await db.atomic_credit(referrer["id"], reward):
        log.error("واریز پاداش به کاربر %s انجام نشد", referrer["id"])
        return 0

    # ردیف مالی برای حسابداری (مثل شارژ دستی)
    await db.insert_transaction(
        referrer["id"],
        "referral",
        reward,
        status="approved",
        idem_key=f"ref:{txn_id}:{kind}" if txn_id else None,
    )

    await _notify(bot, db, referrer, user, reward, first, reason)
    return reward


async def _notify(
    bot,  # noqa: ANN001
    db: Database,
    referrer: dict,
    invitee: dict,
    reward: int,
    first: bool,
    reason: str,
) -> None:
    """خبر دادن به معرف. اگر ربات را بلاک کرده باشد، فقط لاگ می شود."""
    fresh = await db.get_user(referrer["id"]) or referrer
    body = texts.REFERRAL_REWARD.format(
        name=esc((invitee.get("first_name") or "یک هم سفر").strip()),
        reward=f"{reward:,}",
        balance=f"{fresh['balance']:,}",
        reason=reason,
        note=texts.REFERRAL_FIRST_NOTE if first else "",
    )
    fx = effects.kwargs(effects.CHARGE, int(referrer["telegram_id"]))
    for attempt_fx in ((fx, {}) if fx else ({},)):
        try:
            await bot.send_message(int(referrer["telegram_id"]), body, **attempt_fx)
            return
        except Exception as exc:  # noqa: BLE001
            if attempt_fx:
                effects.disable(effects.CHARGE, str(exc))
                continue
            log.warning("خبر پاداش به %s نرسید", referrer["telegram_id"], exc_info=True)
