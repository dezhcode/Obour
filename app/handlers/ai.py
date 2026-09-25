"""خرید خدمات هوش مصنوعی (اشتراک جمنای پرو و مانند آن).

ترتیب عملیات عمدی و حیاتی است، چون تحویل **برگشت ناپذیر** است:

    ۱. قفل بگیر (جلوی دوبار کلیک و اجرای همزمان)
    ۲. قیمت تازه را از سرویس دهنده بگیر (قیمت پلکانی است)
    ۳. پول را اتمیک از کیف پول کم کن
    ۴. سفارش را در حالت pending ثبت کن  ← قبل از تماس با سرویس دهنده
    ۵. سفارش واقعی را بده
    ۶. موفق → تحویل و ثبت delivered
       خطای قطعی → برگشت پول و ثبت failed
       مبهم (تایم اوت) → ثبت unknown، پول برنمی گردد، ادمین خبردار می شود

قدم ۴ قبل از ۵ است تا اگر پروسه وسط کار بمیرد، ردی باقی بماند. اگر
برعکس بود، ممکن بود سفارشی پرداخت شود بدون اینکه هیچ جا ثبت شده باشد.
"""
from __future__ import annotations

import json
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app import features, keyboards, pricing, texts
from app.db import Database
from app.ui import edit_or_send
from app.warzone import Warzone, WarzoneError, WarzoneNoFunds, WarzoneUnknown

log = logging.getLogger("obour.ai")
router = Router(name="ai")

# فعلا فقط همین یک محصول عرضه می شود
GEMINI_SERVICE_ID = "S_01"


async def _client(db: Database) -> Warzone:
    key = await db.get_setting("ai_api_key", "")
    return Warzone(key)


async def _notify_admins(bot, text: str) -> None:  # noqa: ANN001
    from app.config import config

    for admin_id in config.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:  # noqa: BLE001
            log.debug("خبر دادن به ادمین %s نشد", admin_id, exc_info=True)


@router.callback_query(F.data == "ai:buy")
async def cb_ai_product(call: CallbackQuery, db: Database, user: dict) -> None:
    """کارت محصول با قیمت تومانی."""
    if not features.is_on("shop_ai"):
        return await call.answer(texts.SECTION_OFF, show_alert=True)

    cfg = await pricing.load(db)
    if not pricing.is_configured(cfg):
        return await call.answer(texts.AI_NOT_CONFIGURED, show_alert=True)

    wz = await _client(db)
    try:
        if not wz.configured:
            return await call.answer(texts.AI_NOT_CONFIGURED, show_alert=True)
        product = await wz.product(GEMINI_SERVICE_ID)
        if not product:
            return await call.answer(texts.AI_UNAVAILABLE, show_alert=True)

        stock = int(product.get("stock") or 0)
        orderable = product.get("orderable", True)
        usd = product.get("price")
        if not orderable or stock <= 0 or usd in (None, ""):
            await edit_or_send(
                call.message, texts.AI_TEMP_UNAVAILABLE, keyboards.ai_notify_kb()
            )
            return await call.answer()

        # قیمت مستقیم از همین محصول - نه یک درخواست دیگر
        cost = float(usd)
    except WarzoneError as exc:
        log.warning("خواندن محصول هوش مصنوعی نشد: %s", exc)
        return await call.answer(texts.AI_PROVIDER_DOWN, show_alert=True)
    finally:
        await wz.close()

    b = pricing.compute(cost, cfg)
    await edit_or_send(
        call.message,
        texts.AI_PRODUCT.format(
            name=product.get("name") or "اشتراک هوش مصنوعی",
            price=f"{b.final:,}",
            balance=f"{user['balance']:,}",
            stock=stock,
        ),
        keyboards.ai_product_kb(b.final <= int(user["balance"])),
    )
    await call.answer()


@router.callback_query(F.data == "ai:ok")
async def cb_ai_buy(call: CallbackQuery, db: Database, user: dict) -> None:
    """خرید واقعی."""
    if not features.is_on("shop_ai"):
        return await call.answer(texts.SECTION_OFF, show_alert=True)

    lock = f"ai:{user['id']}"
    if not await db.acquire_lock(lock, ttl_seconds=120):
        return await call.answer(texts.AI_IN_PROGRESS, show_alert=True)

    wz = await _client(db)
    order_row: dict | None = None
    try:
        await call.answer()
        await edit_or_send(call.message, texts.AI_WORKING, None)

        # قیمت تازه - بین دیدن کارت و زدن دکمه ممکن است عوض شده باشد.
        # force=True یعنی کش را دور بزن؛ اینجا تنها جایی است که قیمت
        # واقعا باید لحظه ای باشد، چون پول کاربر بر اساسش کم می شود.
        product = await wz.product(GEMINI_SERVICE_ID, force=True)
        if (
            not product
            or not product.get("orderable", True)
            or int(product.get("stock") or 0) <= 0
            or product.get("price") in (None, "")
        ):
            await edit_or_send(
                call.message, texts.AI_TEMP_UNAVAILABLE, keyboards.ai_notify_kb()
            )
            return
        cost = float(product["price"])

        b = await pricing.price_for(db, cost)

        # بررسی موجودی *خودمان* قبل از کسر پول کاربر. بدون این، کاربر
        # پولش کم می شود و بلافاصله برمی گردد - که تجربه بدی است حتی
        # اگر از نظر مالی درست باشد.
        our_balance = await wz.balance()
        if our_balance is not None and our_balance < cost:
            log.error("موجودی نزد سرویس دهنده کافی نیست (%s < %s)", our_balance, cost)
            await _notify_admins(
                call.bot,
                texts.AI_ADMIN_NO_FUNDS.format(
                    error=f"موجودی {our_balance}$ است و این سفارش {cost}$ لازم دارد"
                ),
            )
            await edit_or_send(
                call.message, texts.AI_TEMP_UNAVAILABLE, keyboards.ai_notify_kb()
            )
            return

        # کسر اتمیک - اگر موجودی کافی نباشد هیچ اتفاقی نمی افتد
        if not await db.atomic_debit(user["id"], b.final):
            await edit_or_send(
                call.message,
                texts.INSUFFICIENT,
                keyboards.insufficient_kb(),
            )
            return

        txn_id = await db.insert_transaction(
            user["id"], "ai_purchase", -b.final, status="approved"
        )
        order_row = await db.create_ai_order(
            user_id=user["id"],
            service_id=GEMINI_SERVICE_ID,
            title=product.get("name") or "اشتراک هوش مصنوعی",
            quantity=1,
            usd_cost=cost,
            price=b.final,
            txn_id=txn_id,
        )

        # ---------- نقطه بی بازگشت ----------
        try:
            result = await wz.order(GEMINI_SERVICE_ID, 1)
        except WarzoneUnknown as exc:
            # پول برنمی گردد: ممکن است سفارش انجام شده باشد. برگرداندن
            # خودکار یعنی احتمال تحویل رایگان محصول.
            await db.finish_ai_order(order_row["id"], "unknown", error=str(exc))
            log.error("سفارش هوش مصنوعی مبهم ماند: %s", order_row["code"])
            await _notify_admins(
                call.bot,
                texts.AI_ADMIN_UNKNOWN.format(
                    code=order_row["code"],
                    user=user["telegram_id"],
                    price=f"{b.final:,}",
                    error=str(exc)[:120],
                ),
            )
            await edit_or_send(
                call.message, texts.AI_PENDING_REVIEW.format(code=order_row["code"]),
                keyboards.back_to_shop_kb(),
            )
            return
        except WarzoneNoFunds as exc:
            # موجودی *ما* نزد سرویس دهنده تمام شده. پول کاربر برمی گردد.
            # قبلا اینجا کل بخش خاموش می شد - که کاربر را گیج می کرد
            # (دکمه ناپدید می شد بدون هیچ توضیحی). حالا بخش دست نخورده
            # می ماند و فقط پیام "فعلا موجود نیست" نشان داده می شود؛
            # ادمین هم خبردار می شود تا شارژ کند.
            await db.atomic_credit(user["id"], b.final)
            await db.insert_transaction(
                user["id"], "refund", b.final, status="approved"
            )
            await db.finish_ai_order(
                order_row["id"], "failed", error="موجودی سرویس دهنده تمام شد"
            )
            log.error("موجودی نزد سرویس دهنده تمام شد: %s", exc)
            await _notify_admins(call.bot, texts.AI_ADMIN_NO_FUNDS.format(
                error=str(exc)[:150]
            ))
            await edit_or_send(
                call.message,
                texts.AI_TEMP_UNAVAILABLE,
                keyboards.ai_notify_kb(),
            )
            return
        except WarzoneError as exc:
            # قطعا انجام نشد - پول برمی گردد
            await db.atomic_credit(user["id"], b.final)
            await db.insert_transaction(
                user["id"], "refund", b.final, status="approved"
            )
            await db.finish_ai_order(order_row["id"], "failed", error=str(exc))
            log.warning("سفارش هوش مصنوعی ناموفق: %s", exc)
            await edit_or_send(
                call.message,
                texts.AI_FAILED_REFUNDED.format(price=f"{b.final:,}"),
                keyboards.back_to_shop_kb(),
            )
            return

        products = result.get("products") or []
        await db.finish_ai_order(
            order_row["id"],
            "delivered",
            provider_order_id=str(result.get("order_id") or ""),
            products=json.dumps(products, ensure_ascii=False),
        )
        await edit_or_send(
            call.message,
            texts.AI_DELIVERED.format(
                name=order_row["title"],
                code=order_row["code"],
                provider_code=result.get("order_id") or "-",
                links="\n\n".join(f"<code>{p}</code>" for p in products),
            ),
            keyboards.ai_delivered_kb(),
        )
        log.info("سفارش هوش مصنوعی %s تحویل شد", order_row["code"])

    except Exception:  # noqa: BLE001
        log.exception("خرید هوش مصنوعی شکست خورد")
        if order_row:
            await db.finish_ai_order(order_row["id"], "unknown", error="خطای داخلی")
        await edit_or_send(
            call.message, texts.AI_PROVIDER_DOWN, keyboards.back_to_shop_kb()
        )
    finally:
        await wz.close()
        await db.release_lock(lock)


@router.callback_query(F.data == "ai:notify")
async def cb_ai_notify_me(call: CallbackQuery, db: Database, user: dict) -> None:
    """ثبت نام در فهرست انتظار موجود شدن."""
    added = await db.ai_waitlist_add(user["id"])
    await call.answer(
        "باشه، به محض موجود شدن خبرت می کنیم ✅" if added
        else "قبلا ثبت نامت رو داشتیم، صبر کن 🔔",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("ai:status:"))
async def cb_ai_status_live(call: CallbackQuery, db: Database, user: dict) -> None:
    """وضعیت لحظه ای یک سفارش، مستقیم از تاریخچه سرویس دهنده.

    سرویس دهنده اندپوینت «یک سفارش» جدا ندارد؛ در تاریخچه اش دنبال
    provider_order_id می گردیم. خروجی خام نمایش داده می شود چون شکل
    دقیق فیلدهای وضعیت مستند نشده است.
    """
    from app.config import config

    order_id = int(call.data.split(":")[2])
    order = await db.get_ai_order(order_id)
    if not order:
        return await call.answer("این سفارش پیدا نشد.", show_alert=True)
    is_admin = user["telegram_id"] in config.admin_ids
    if not is_admin and order["user_id"] != user["id"]:
        return await call.answer("این سفارش مال تو نیست.", show_alert=True)
    if not order.get("provider_order_id"):
        return await call.answer(texts.AI_STATUS_LIVE_UNKNOWN, show_alert=True)

    await call.answer("در حال بررسی...")
    wz = await _client(db)
    try:
        found = await wz.find_order(order["provider_order_id"])
    except WarzoneError:
        found = None
    finally:
        await wz.close()

    if not found:
        return await call.message.answer(texts.AI_STATUS_LIVE_FAILED)

    raw = "\n".join(f"• <code>{k}</code>: {v}" for k, v in found.items() if k != "products")
    await call.message.answer(texts.AI_STATUS_LIVE.format(raw=raw or "—"))


@router.callback_query(F.data == "ai:mine")
async def cb_ai_orders(call: CallbackQuery, db: Database, user: dict) -> None:
    """سفارش های هوش مصنوعی کاربر، با لینک های تحویل."""
    orders = await db.user_ai_orders(user["id"])
    if not orders:
        await edit_or_send(
            call.message, texts.AI_ORDERS_EMPTY, keyboards.back_to_shop_kb()
        )
        return await call.answer()

    blocks = []
    for o in orders:
        links = ""
        if o.get("products"):
            try:
                items = json.loads(o["products"])
                links = "\n".join(f"<code>{p}</code>" for p in items)
            except Exception:  # noqa: BLE001
                links = ""
        provider = f" · {o['provider_order_id']}" if o.get("provider_order_id") else ""
        blocks.append(
            texts.AI_ORDER_ROW.format(
                status=texts.AI_STATUS.get(o["status"], o["status"]),
                title=o["title"],
                code=o["code"] + provider,
                price=f"{o['price']:,}",
                links=("\n" + links) if links else "",
            )
        )
    await edit_or_send(
        call.message,
        texts.AI_ORDERS.format(count=len(orders), rows="\n\n".join(blocks)),
        keyboards.back_to_shop_kb(),
    )
    await call.answer()
