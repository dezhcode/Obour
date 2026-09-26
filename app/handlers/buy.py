"""خرید سرویس - با ترتیب امن ساخت/کسر و قفل ضد خرید همزمان.

ترتیب امن (بخش ۵.۲ سند):
۱. قفل گرفتن (تا دو خرید همزمان یک کاربر روی هم نیفتد)
۲. ساخت کاربر روی پنل موفق شود
۳. بعد پول با کسر اتمیک کم شود
۴. اگر کسر شکست خورد -> کاربر پنل حذف و پیام موجودی کم

تغییرات مهم نسبت به نسخه قبل:
- قفل عملیات در دیتابیس، به جای idem_key وابسته به message_id که باعث
  می شد خرید دوباره همان پلن در همان صفحه برای همیشه قفل شود
- تراکنش ناموفق با وضعیت failed می ماند، پاک نمی شود (ردپای حسابداری)
- کد تخفیف به همان پلنی که برایش وارد شده گره خورده و همان قیمتی که
  کاربر می بیند کسر می شود
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

from app import referral, effects, features, keyboards, pricing, richtable, texts, ui
from app.config import config
from app.db import Database
from app.panel import Panel
from app.services import purchase as purchase_svc
from app.states import Buy
from app.ui import edit_or_send
from app.utils import esc
from app.i18n import t as _t

log = logging.getLogger("obour.buy")
router = Router(name="buy")


@router.callback_query(F.data == "buy")
async def cb_shop_hub(
    call: CallbackQuery, db: Database, state: FSMContext, user: dict
) -> None:
    """صفحه اول فروشگاه: انتخاب بین کانفیگ و خدمات هوش مصنوعی.

    اگر فقط یک شاخه فعال باشد، مستقیم به همان می رویم - یک صفحه واسط
    با تک دکمه فقط یک کلیک اضافه است و هیچ کمکی نمی کند.
    """
    await _clear_discount(state)
    vpn, ai = features.is_on("shop_vpn"), features.is_on("shop_ai")

    if vpn and not ai:
        return await cb_buy(call, db, state, user)
    if ai and not vpn:
        return await cb_ai_shop(call, db, user)
    if not vpn and not ai:
        await edit_or_send(call.message, texts.SHOP_CLOSED, keyboards.back_menu())
        return await call.answer()

    await edit_or_send(
        call.message,
        texts.SHOP_HUB.format(balance=f"{user['balance']:,}"),
        keyboards.shop_hub_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "buy:ai")
async def cb_ai_shop(call: CallbackQuery, db: Database, user: dict) -> None:
    """بخش خدمات هوش مصنوعی: کاتالوگ canboso با قیمت تومانی."""
    if not features.is_on("shop_ai"):
        return await call.answer(texts.SECTION_OFF, show_alert=True)
    from app.services import ai_shop

    cfg = await pricing.load(db)
    if not await ai_shop.api_key(db) or not (pricing.is_configured(cfg, "USD") or pricing.is_configured(cfg, "VND")):
        # هنوز تنظیم نشده: به جای خطای مبهم، همان صفحه «به زودی»
        await edit_or_send(
            call.message,
            texts.AI_SHOP_SOON.format(balance=f"{user['balance']:,}"),
            keyboards.back_to_shop_kb(),
        )
        return await call.answer()
    from app.handlers.ai import show_catalog

    await show_catalog(call.message, db, user)
    await call.answer()


@router.callback_query(F.data == "buy:vpn")
async def cb_buy(call: CallbackQuery, db: Database, state: FSMContext, user: dict) -> None:
    """فهرست دسته های کانفیگ (روزانه / هفتگی / ماهانه)."""
    if not features.is_on("shop_vpn"):
        return await call.answer(texts.SECTION_OFF, show_alert=True)
    await _clear_discount(state)
    cats = await db.shop_categories()
    if not cats:
        await edit_or_send(
            call.message,
            _t("فعلا پلنی برای فروش فعال نیست. کمی صبر کن یا به پشتیبانی خبر بده."),
            keyboards.back_menu(),
        )
        return await call.answer()
    await edit_or_send(
        call.message,
        texts.SHOP.format(balance=f"{user['balance']:,}"),
        keyboards.plan_categories_kb(cats),
    )
    await call.answer()


@router.callback_query(F.data == "loc")
async def cb_locations(call: CallbackQuery, db: Database) -> None:
    """صفحه اطلاعاتی سرورها و لوکیشن ها.

    خرید جداگانه لوکیشن نداریم - همه کانفیگ ها در یک لینک اشتراک
    می آیند - پس این صفحه فقط توضیح می دهد کاربر چه چیزی می خرد.

    اگر عکس تنظیم شده باشد، صفحه به صورت Rich Message با بلوک عکس
    ساخته می شود. نکته مهم: Rich Message یک پیام *متنی* است، پس
    رفت و برگشت با ویرایش انجام می شود و پیام پاک نمی شود - برخلاف
    sendPhoto که اجباری پیام تازه می سازد.
    """
    if not features.is_on("shop_locations"):
        return await call.answer(texts.SECTION_OFF, show_alert=True)
    markup = keyboards.locations_kb()
    # تصویر پیش فرض همراه خود ربات می آید و از مسیر /img سرو می شود؛
    # پس بدون هیچ تنظیمی کار می کند. اگر ادمین با /locimg چیز دیگری
    # گذاشته باشد، آن اولویت دارد.
    # ترتیب انتخاب عکس مهم است: آدرس اینترنتی بر file_id اولویت دارد.
    # چرا؟ چون مسیر «پیش نمایش لینک» (که فقط با آدرس کار می کند) پیام را
    # متنی نگه می دارد و HTML را پردازش می کند - یعنی ایموجی پریمیوم
    # و فاصله های متن سالم می مانند. مسیر Rich Message (برای file_id)
    # هیچ کدام را ندارد: ایموجی ها ساده نشان داده می شوند.
    custom = await db.get_setting("locations_photo", "")
    bundled = (
        f"{config.webhook_base_url.rstrip('/')}/img/locations.jpg"
        if config.webhook_base_url
        else ""
    )
    if custom.startswith(("http://", "https://")):
        photo = custom
    elif bundled:
        photo = bundled          # عکس همراه ربات، به شکل آدرس
    else:
        photo = custom           # فقط file_id مانده؛ آخرین چاره

    # ---------- راه اول: پیش نمایش لینک بالای متن ----------
    # چرا این اول است و نه Rich Message؟
    # در Rich Message هر پاراگراف یک بلوک جداست و *تلگرام* تصمیم
    # می گیرد بینشان چقدر فاصله باشد؛ خط های خالی متن اصلی از بین
    # می روند و همه چیز فشرده می شود. با پیش نمایش لینک، متن دقیقا
    # همان متن قبلی است - با همان اینترها و فاصله ها.
    # پیام هم متنی می ماند، پس رفت و برگشت با ویرایش انجام می شود و
    # پیام پاک نمی شود. تنها شرطش این است که عکس آدرس اینترنتی باشد
    # (که تصویر پیش فرض خود ربات هست).
    if photo.startswith(("http://", "https://")):
        try:
            await edit_or_send(
                call.message,
                f'<a href="{photo}">\u2060</a>' + texts.LOCATIONS,
                markup,
                link_preview_options=LinkPreviewOptions(
                    url=photo, prefer_large_media=True, show_above_text=True
                ),
            )
            return await call.answer()
        except Exception as exc:  # noqa: BLE001
            log.warning("پیش نمایش لینک برای لوکیشن ها نشد: %s", exc)

    # ---------- راه دوم: Rich Message ----------
    # فقط وقتی لازم می شود که عکس file_id باشد (پیش نمایش لینک file_id
    # را قبول نمی کند). اینجا متن یکجا در یک بلوک می رود تا حداقل
    # خط ها حفظ شوند.
    if photo:
        try:
            rich = richtable.photo_page(photo, texts.LOCATIONS)
            await ui.edit_or_send_rich(call.message, rich, markup)
            return await call.answer()
        except Exception as exc:  # noqa: BLE001
            log.warning("صفحه لوکیشن ها با Rich Message نشد: %s", exc, exc_info=True)
            await db.set_setting("locations_photo_error", str(exc)[:300])

    await edit_or_send(call.message, texts.LOCATIONS, markup)
    await call.answer()


@router.callback_query(F.data.startswith("buy:c:"))
async def cb_buy_category(call: CallbackQuery, db: Database, user: dict) -> None:
    """لیست پلن های یک دسته."""
    category_id = int(call.data.split(":")[2])
    plans = await db.active_plans(category_id)
    cat = await db.get_category(category_id)
    if not plans:
        await edit_or_send(call.message, texts.CATEGORY_EMPTY, keyboards.back_menu())
        return await call.answer()
    await edit_or_send(
        call.message,
        texts.SHOP_CATEGORY_GENERIC.format(
            emoji=cat["emoji"] if cat else "📦",
            title=esc(cat["title"]) if cat else _t("پلن ها"),
            balance=f"{user['balance']:,}",
        ),
        keyboards.plans_kb(plans),
    )
    await call.answer()


# ==================== صفحه پلن ====================
async def _clear_discount(state: FSMContext) -> None:
    await state.update_data(discount_code=None, discount_plan=None)


async def _active_discount(
    db: Database, state: FSMContext, user: dict, plan: dict
) -> tuple[dict | None, int]:
    """کد تخفیف فعال برای همین پلن. خروجی: (کد، مبلغ تخفیف).

    دو شرط با هم بررسی می شود:
    ۱. کد برای همین پلن وارد شده باشد، نه پلن دیگری که کاربر بعدا دیده
    ۲. کد همین لحظه هم معتبر باشد (ممکن است ظرفیتش پر شده باشد)
    """
    data = await state.get_data()
    code = data.get("discount_code")
    if not code or data.get("discount_plan") != plan["id"]:
        return None, 0
    d, _err = await db.validate_discount(code, user["id"], plan["price"])
    if not d:
        await _clear_discount(state)
        return None, 0
    return d, db.discount_value(d, plan["price"])


def _plan_body(plan: dict, user: dict) -> str:
    # خط لوکیشن ها به همه پلن ها اضافه می شود چون همه پلن ها همان
    # ۲۳ کانفیگ را دارند؛ اگر روزی پلن محدود به لوکیشن اضافه شد،
    # این خط باید بر اساس خود پلن ساخته شود.
    return texts.PLAN_DETAIL.format(
        badge=texts.PLAN_BADGE_BEST if plan.get("badge") else texts.PLAN_BADGE_PLAIN,
        title=esc(plan["title"]),
        data=plan["data_gb"],
        days=plan["duration_days"],
        price=f"{plan['price']:,}",
        balance=f"{user['balance']:,}",
    ) + texts.PLAN_LOCATIONS_LINE


def _discount_body(plan: dict, code: str, saved: int) -> str:
    return texts.DISCOUNT_OK.format(
        code=esc(code),
        original=f"{plan['price']:,}",
        saved=f"{saved:,}",
        final=f"{plan['price'] - saved:,}",
    )


async def _render_plan(
    message: Message, db: Database, state: FSMContext, user: dict, plan: dict
) -> None:
    """رندر صفحه پلن، همراه تخفیف اگر فعال باشد."""
    body = _plan_body(plan, user)
    d, saved = await _active_discount(db, state, user, plan)
    if d:
        body += "\n\n" + _discount_body(plan, d["code"], saved)
    else:
        # پیشنهاد ارتقا فقط وقتی تخفیفی روی صفحه نیست، تا شلوغ نشود
        nxt = await _better_plan(db, plan)
        if nxt:
            body += "\n\n" + texts.UPSELL.format(
                extra=f"{nxt['price'] - plan['price']:,}", bigger=nxt["data_gb"]
            )

    prev_id, next_id = await _neighbours(db, plan)
    await edit_or_send(
        message,
        body,
        keyboards.plan_confirm(
            plan["id"], prev_id, next_id, discount_code=d["code"] if d else None
        ),
    )


async def show_plan_from_start(
    message: Message, db: Database, user: dict, plan: dict
) -> None:
    """نمایش یک پلن از روی لینک عمیق (دکمه زیر پست کانال).

    از _render_plan استفاده نمی کنیم چون آن به FSMContext نیاز دارد و
    اینجا از مسیر /start می آییم؛ کارت پلن به تنهایی کافی است.
    """
    if not plan.get("is_active"):
        return await message.answer(texts.PLAN_UNAVAILABLE, reply_markup=keyboards.back_menu())
    await message.answer(
        _plan_body(plan, user),
        reply_markup=keyboards.plan_confirm(plan["id"]),
    )


@router.callback_query(F.data.startswith("buy:p:"))
async def cb_plan_detail(
    call: CallbackQuery, db: Database, state: FSMContext, user: dict
) -> None:
    plan_id = int(call.data.split(":")[2])
    plan = await db.get_plan(plan_id)
    if not plan or not plan["is_active"]:
        await edit_or_send(call.message, texts.PLAN_UNAVAILABLE, keyboards.back_menu())
        return await call.answer()
    await _render_plan(call.message, db, state, user, plan)
    await call.answer()


async def _neighbours(db: Database, plan: dict) -> tuple[int | None, int | None]:
    """پلن قبلی و بعدی، داخل همان دسته.

    قبلا بین همه دسته ها حرکت می کرد و کاربر با زدن «پلن بعدی» ناگهان
    از دسته روزانه سر از ماهانه در می آورد.
    """
    plans = await db.active_plans(plan["category_id"]) if plan["category_id"] else []
    if not plans:
        plans = await db.active_plans()
    plans = sorted(plans, key=lambda p: (p["data_gb"], p["id"]))
    ids = [p["id"] for p in plans]
    if plan["id"] not in ids or len(ids) < 2:
        return None, None
    i = ids.index(plan["id"])
    prev_id = ids[i - 1] if i > 0 else None
    next_id = ids[i + 1] if i < len(ids) - 1 else None
    return prev_id, next_id


async def _better_plan(db: Database, plan: dict) -> dict | None:
    """پلن بعدی که حجمش بیشتر ولی هر گیگش ارزان تر باشد."""
    if not plan.get("data_gb"):
        return None
    cur_per_gb = plan["price"] / plan["data_gb"]
    best = None
    for p in await db.active_plans():
        if p["id"] == plan["id"] or not p.get("data_gb"):
            continue
        if p["data_gb"] <= plan["data_gb"] or p["price"] <= plan["price"]:
            continue
        if p["price"] / p["data_gb"] >= cur_per_gb:
            continue
        if best is None or p["data_gb"] < best["data_gb"]:
            best = p
    return best


# ==================== خرید ====================
@router.callback_query(F.data.startswith("buy:ok:"))
async def cb_buy_confirm(
    call: CallbackQuery, db: Database, state: FSMContext
) -> None:
    """مرحله اسم سرویس - قبل از پرداخت.

    اسمی که کاربر اینجا می دهد دو کار می کند: هم عنوان سرویس در ربات
    می شود، هم مبنای نام فنی سرویس روی پنل (به جای obour_<آیدی>_<شماره>).
    """
    plan_id = int(call.data.split(":")[2])
    plan = await db.get_plan(plan_id)
    if not plan or not plan["is_active"]:
        await edit_or_send(call.message, texts.PLAN_UNAVAILABLE, keyboards.back_menu())
        return await call.answer()

    await state.set_state(Buy.waiting_service_name)
    await state.update_data(buy_plan=plan_id)
    await edit_or_send(
        call.message,
        texts.SERVICE_NAME_BEFORE_BUY,
        keyboards.service_name_kb(f"buy:p:{plan_id}"),
    )
    await call.answer()


@router.callback_query(Buy.waiting_service_name, F.data == "nm:skip")
async def cb_buy_skip_name(
    call: CallbackQuery, db: Database, panel: Panel | None, state: FSMContext, user: dict
) -> None:
    await _start_purchase(call.message, db, panel, state, user, "", f"buy:{call.id}", call)


@router.message(Buy.waiting_service_name, F.text)
async def msg_buy_service_name(
    message: Message, db: Database, panel: Panel | None, state: FSMContext, user: dict
) -> None:
    raw = (message.text or "").strip()
    if len(raw) > 30:
        return await message.answer(texts.SERVICE_NAME_TOO_LONG)
    # آیدی پیام کلید یکتای این تلاش است: اگر تلگرام همان آپدیت را دوباره
    # بفرستد، آیدی یکی است و خرید دوم ثبت نمی شود.
    idem = f"buy:m{message.chat.id}:{message.message_id}"
    await _start_purchase(message, db, panel, state, user, raw, idem)


async def _start_purchase(
    message: Message,
    db: Database,
    panel: Panel | None,
    state: FSMContext,
    user: dict,
    label: str,
    idem: str,
    call: CallbackQuery | None = None,
) -> None:
    """آماده سازی ورودی ها، صدا زدن سرویس خرید، و نمایش نتیجه.

    خود خرید اینجا نیست: در app/services/purchase.py است تا مینی اپ هم
    از همان یک پیاده سازی استفاده کند. چیزی که اینجا می ماند فقط کار
    رابط است - خواندن وضعیت گفتگو، پیام «در حال آماده سازی»، و ترجمه
    کد خطا به متن و کیبورد.
    """
    data = await state.get_data()
    plan = await db.get_plan(data["buy_plan"]) if data.get("buy_plan") else None
    await state.set_state(None)

    # تخفیف در ربات به وضعیت گفتگو گره خورده، پس اعتبارسنجی اش همین جا
    # می ماند و فقط مبلغ نهایی به سرویس داده می شود.
    discount = None
    if plan:
        d, saved = await _active_discount(db, state, user, plan)
        if d and saved:
            discount = purchase_svc.Discount(id=d["id"], code=d["code"], saved=saved)

    # پیام «در حال ساخت» قبل از تماس با پنل نشان داده می شود چون ساخت
    # روی پنل تا چند ثانیه طول می کشد و کاربر نباید صفحه بی جواب ببیند.
    working: Message | None = None
    if plan and plan["is_active"] and panel is not None:
        working = await ui.working(
            message, texts.building(name=esc(user.get("first_name") or ""))
        )

    result = await purchase_svc.purchase(
        db, panel, user, plan, label=label, idem=idem, discount=discount
    )

    if result.ok:
        if result.discount_used:
            await _clear_discount(state)
        await ui.deliver(
            working,
            caption=texts.buy_success(
                sub_url=result.sub_url,
                balance=f"{result.balance_after:,}",
                name=esc(result.label) or f"{_t('سرویس')} {result.service_id}",
            ),
            sub_url=result.sub_url,
            reply_markup=keyboards.service_detail_kb(result.service_id, result.sub_url),
            effect=effects.PURCHASE,
        )
        # پاداش معرف. هر خطایی داخل خودش لاگ می شود و خرید را نمی شکند.
        await referral.reward_purchase(
            message.bot,
            db,
            user,
            result.price,
            result.txn_id,
            "سرویس {title} رو خرید",
            title=esc(plan["title"]),
        )
        if call:
            await call.answer()
        return

    await _show_error(message, working, call, result)


# کد خطای سرویس -> چیزی که کاربر در ربات می بیند.
# سرویس عمدا متن نمی سازد؛ همان خطا در مینی اپ شکل دیگری دارد.
_ALERTS = {
    purchase_svc.LOCKED: "یه پرداخت همین حالا در جریانه. چند لحظه صبر کن.",
    purchase_svc.DUPLICATE: "این خرید در حال پردازشه.",
}


async def _show_error(
    message: Message,
    working: Message | None,
    call: CallbackQuery | None,
    result: "purchase_svc.PurchaseResult",
) -> None:
    """ترجمه کد خطا به پیام. هیچ تصمیم مالی اینجا گرفته نمی شود."""
    err = result.error

    # این دو خطا قبل از پیام «در حال ساخت» رخ می دهند و به صورت هشدار
    # روی همان صفحه نشان داده می شوند، نه یک پیام تازه.
    if err in _ALERTS:
        if call:
            return await call.answer(_ALERTS[err], show_alert=True)
        return await message.answer(_ALERTS[err])

    if err == purchase_svc.PLAN_UNAVAILABLE:
        return await message.answer(
            texts.PLAN_UNAVAILABLE, reply_markup=keyboards.back_menu()
        )
    if err == purchase_svc.PANEL_BUSY:
        return await message.answer(texts.PANEL_BUSY_ALERT)

    target = working or message
    if err == purchase_svc.INSUFFICIENT:
        return await _fail(target, texts.INSUFFICIENT, keyboards.insufficient_kb())

    # NAME_FAILED و PANEL_ERROR هر دو از دید کاربر یک چیزند: سرویس ساخته
    # نشد و پولی کم نشده. تفکیکشان فقط در لاگ معنی دارد.
    if err in (purchase_svc.NAME_FAILED, purchase_svc.PANEL_ERROR):
        return await _fail(target, texts.PANEL_ERROR)

    # کد خطای ناشناخته: یعنی سرویس کد تازه ای اضافه کرده و اینجا
    # به روز نشده. پیام عمومی می دهیم ولی در لاگ سروصدا می کنیم.
    log.error("کد خطای ترجمه نشده از سرویس خرید: %s", err)
    return await _fail(target, texts.PANEL_ERROR)


async def _fail(message: Message, body: str, markup=None) -> None:  # noqa: ANN001
    """نمایش خطا روی همان پیامی که «در حال آماده سازی» را نشان می داد."""
    try:
        await message.edit_text(body, reply_markup=markup or keyboards.back_menu())
    except Exception:  # noqa: BLE001
        await message.answer(body, reply_markup=markup or keyboards.back_menu())


# ==================== کد تخفیف (کاربر) ====================
@router.callback_query(F.data.startswith("buy:dsc:"))
async def cb_discount_ask(call: CallbackQuery, state: FSMContext) -> None:
    plan_id = int(call.data.split(":")[2])
    await state.set_state(Buy.waiting_discount)
    await state.update_data(discount_plan=plan_id)
    await edit_or_send(
        call.message, texts.DISCOUNT_ASK, keyboards.discount_cancel_kb(plan_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("buy:dscx:"))
async def cb_discount_remove(
    call: CallbackQuery, db: Database, state: FSMContext, user: dict
) -> None:
    """حذف کد تخفیف اعمال شده و بازگشت به صفحه پلن."""
    plan_id = int(call.data.split(":")[2])
    await _clear_discount(state)
    plan = await db.get_plan(plan_id)
    if not plan:
        return await call.answer()
    await _render_plan(call.message, db, state, user, plan)
    await call.answer(_t("کد حذف شد"))


@router.message(Buy.waiting_discount, F.text)
async def msg_discount_code(
    message: Message, db: Database, state: FSMContext, user: dict
) -> None:
    data = await state.get_data()
    plan_id = data.get("discount_plan")
    plan = await db.get_plan(plan_id) if plan_id else None
    if not plan:
        await state.clear()
        return await message.answer(_t("یه اشتباهی پیش اومد. دوباره از فروشگاه شروع کن."))

    code = (message.text or "").strip()
    if not code or len(code) > 40:
        return await message.answer(texts.DISCOUNT_ERR["not_found"])

    d, err = await db.validate_discount(code, user["id"], plan["price"])
    if not d:
        msg = texts.DISCOUNT_ERR.get(err, _t("این کد معتبر نیست."))
        if err == "min_amount":
            other = await db.discount_by_code(code)
            msg = msg.format(min_amount=f"{other['min_amount']:,}" if other else "-")
        return await message.answer(msg)

    await state.set_state(None)
    await state.update_data(discount_code=d["code"], discount_plan=plan["id"])
    saved = db.discount_value(d, plan["price"])
    await message.answer(
        _plan_body(plan, user) + "\n\n" + _discount_body(plan, d["code"], saved),
        reply_markup=keyboards.plan_confirm(plan["id"], discount_code=d["code"]),
    )
