"""دستیار هوش مصنوعی در مینی اپ: گفتگو، ارجاع، پیشنهاد پلن، دستیار فروشگاه.

تاریخچه گفتگو در خود مینی اپ نگه داشته می شود و هر بار فرستاده می شود
(وب سرویس حافظه ندارد). این تاریخچه فقط روی جواب های همین کاربر اثر
دارد و زمینه حساب همیشه از دیتابیس خوانده می شود، نه از کلاینت.
"""
from __future__ import annotations

import base64
import binascii
import logging
from typing import TYPE_CHECKING

from app.services import assistant
from app.services.assistant import AIError
from app.webapp.api import ApiError, _require_user
from app.webapp.auth import WebAppUser

if TYPE_CHECKING:
    from app.db import Database
    from app.panel import Panel

log = logging.getLogger("obour.webapp.assist")

TIMEOUT = 75  # مینی اپ مثل وبهوک محدودیت ۵۰ ثانیه ندارد


def _need(feature: str) -> None:
    if not assistant.ready(feature):
        raise ApiError("دستیار هوشمند فعلا در دسترس نیست", 503, "ai_off")


async def _limit(db: "Database", user: dict) -> None:
    if not await assistant.allowed(db, user["id"]):
        raise ApiError("امروز به سقف سوال از دستیار رسیدی", 429, "ai_limit")


def _clean_history(messages) -> list[dict]:  # noqa: ANN001
    out = []
    for m in (messages if isinstance(messages, list) else [])[-20:]:
        if not isinstance(m, dict):
            continue
        role = "user" if m.get("role") == "user" else "assistant"
        text = str(m.get("text") or "").strip()[:1200]
        if text:
            out.append({"role": role, "text": text})
    return out


def _image(raw: str) -> bytes | None:
    raw = str(raw or "")
    if not raw:
        return None
    raw = raw.split(",", 1)[1] if raw.startswith("data:") else raw
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ApiError("عکس خوانده نشد", 400, "bad_image") from exc
    if len(data) > assistant.MAX_IMAGE:
        raise ApiError("عکس خیلی بزرگه", 413, "too_big")
    return data


def _err(exc: AIError) -> ApiError:
    log.info("دستیار مینی اپ: %s", exc)
    return ApiError("دستیار الان جواب نداد، کمی بعد دوباره امتحان کن", 502, "ai_" + exc.code)


async def chat(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, messages, text: str,  # noqa: ANN001
               image: str = "", mode: str = "chat") -> dict:
    user = await _require_user(db, wuser)
    _need("ai_support")
    text = (text or "").strip()[:1500]
    img = _image(image)
    if not text and not img:
        raise ApiError("پیام خالیه", 400, "empty")
    await _limit(db, user)
    try:
        answer = await assistant.support_reply(
            db, user, _clean_history(messages), text, image=img,
            mode="fix" if mode == "fix" else "chat", timeout=TIMEOUT,
        )
    except AIError as exc:
        raise _err(exc) from exc
    return {"text": answer[:3000]}


async def escalate(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, messages, bot=None) -> dict:  # noqa: ANN001
    from app.services import support

    user = await _require_user(db, wuser)
    hist = _clean_history(messages)
    if not hist:
        raise ApiError("گفتگویی برای ارسال نیست", 400, "empty")
    summary = await assistant.escalate_summary(db, user, hist)
    last = next((h["text"] for h in reversed(hist) if h["role"] == "user"), "")
    body = f"🤖 ارجاع از دستیار هوشمند\n\n📝 خلاصه:\n{summary}\n\n💬 آخرین پیام کاربر:\n{last}"
    r = await support.send(bot, db, user, body, via="ai")
    return {"ok": True, "code": r.get("code"), "thread_id": r.get("thread_id")}


async def recommend(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, force: bool = False) -> dict:
    user = await _require_user(db, wuser)
    _need("ai_recommend")
    if force:
        await _limit(db, user)
    try:
        rec = await assistant.recommend(db, user, force=force, timeout=TIMEOUT)
    except AIError as exc:
        raise _err(exc) from exc
    plan = await db.get_plan(rec["plan_id"]) if rec.get("plan_id") else None
    return {
        "text": rec["text"],
        "plan": {k: plan[k] for k in ("id", "title", "price", "data_gb", "duration_days")}
        if plan and plan.get("is_active") else None,
    }


async def shop(db: "Database", panel: "Panel | None", wuser: WebAppUser, *, q: str) -> dict:
    from app.services import ai_shop

    user = await _require_user(db, wuser)
    _need("ai_shop_help")
    q = (q or "").strip()[:500]
    if len(q) < 2:
        raise ApiError("بنویس دنبال چی هستی", 400, "empty")
    await _limit(db, user)
    try:
        cat = await ai_shop.catalog(db)
    except Exception as exc:  # noqa: BLE001
        raise ApiError("فروشگاه الان در دسترس نیست", 503, "provider") from exc
    try:
        r = await assistant.shop_pick(db, user, q, cat["items"], timeout=TIMEOUT)
    except AIError as exc:
        raise _err(exc) from exc
    return {"text": r["text"], "ids": r["ids"]}
