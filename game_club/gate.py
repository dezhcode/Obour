"""عضویت اجباری در کانال/گروه و پیام پاپ آپ مینی اپ؛ هر دو از پنل مدیریت (جدول settings، JSON).

gate:  {"on": bool, "chats": [{"id": "-100…" یا "@name", "title": "...", "url": "https://t.me/..."}]}
       وقتی روشن است، برای کار با ربات (پیوی) و ساختن یا نشستن سر میز باید عضو همهٔ این ها بود؛ مینی اپ هم
       صفحهٔ «عضو شو» با دکمهٔ «عضو شدم» نشان می دهد. ادمین ها مستثنا هستند. عضویت از getChatMember است؛ پس
       ربات باید در کانال ادمین (و در گروه عضو) باشد. اگر تلگرام جواب نداد (ربات را برداشته اند و ...)، کسی قفل نمی شود.
popup: {"on": bool, "v": نسخه، "title", "text", "img": "media/<فایل>" یا https، "btn", "url", "mode": "once" | "always"}
       با باز شدن مینی اپ نشان داده می شود؛ «once» یعنی هر نفر هر نسخه را یک بار می بیند (هر ذخیره = نسخهٔ تازه).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time

from .config import gc
from .db import GCDatabase
from .service import GCError

log = logging.getLogger("gameclub.gate")

MAX_CHATS = 8
OK_TTL = 600            # عضویت تأیید شده ده دقیقه به خاطر می ماند
MEDIA_RE = re.compile(r"^(popup|bc)-[a-f0-9]{12}\.(jpg|png|webp|gif)$")
IMG_MAX = 1_500_000
_TYPES = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"RIFF": "webp", b"GIF8": "gif"}

_cfg: dict[str, tuple[float, dict]] = {}
_ok: dict[tuple[int, str], float] = {}


async def load(db: GCDatabase, key: str) -> dict:
    """تنظیم JSON از جدول settings (هر ۱۰ ثانیه یک بار از دیتابیس)."""
    hit = _cfg.get(key)
    if hit and time.time() - hit[0] < 10:
        return hit[1]
    try:
        val = json.loads((await db.settings_all()).get(key) or "{}")
    except (TypeError, ValueError):
        val = {}
    val = val if isinstance(val, dict) else {}
    _cfg[key] = (time.time(), val)
    return val


async def save(db: GCDatabase, key: str, val: dict) -> dict:
    await db.setting_put(key, json.dumps(val, ensure_ascii=False))
    _cfg[key] = (time.time(), val)
    return val


# ---------- عضویت ----------
async def is_member(bot, chat_id: str, tg: int, fresh: bool = False) -> bool:  # noqa: ANN001
    k = (tg, str(chat_id))
    if not fresh and time.time() - _ok.get(k, 0) < OK_TTL:
        return True
    try:
        m = await bot.get_chat_member(_chat_ref(chat_id), tg)
    except Exception as e:  # noqa: BLE001
        log.warning("عضویت %s در %s بررسی نشد (ربات ادمین است؟): %s", tg, chat_id, e)
        return True
    ok = m.status in ("creator", "administrator", "member") or (m.status == "restricted" and bool(getattr(m, "is_member", False)))
    if ok:
        _ok[k] = time.time()
    else:
        _ok.pop(k, None)
    return ok


async def missing(db: GCDatabase, bot, tg: int, fresh: bool = False) -> list[dict]:  # noqa: ANN001
    """کانال ها و گروه هایی که این کاربر هنوز عضوشان نیست (خالی = آزاد)."""
    from . import admin

    cfg = await load(db, "gate")
    # مهمان برنامهٔ اندروید حساب تلگرامی ندارد که عضویتش پرسیده شود
    if not cfg.get("on") or not cfg.get("chats") or bot is None or tg < 0 or admin.is_admin(tg):
        return []
    out = []
    for c in cfg["chats"]:
        if not await is_member(bot, c["id"], tg, fresh):
            out.append({"title": c.get("title") or "کانال", "url": c.get("url") or "", "kind": c.get("kind", "channel")})
    return out


async def require(db: GCDatabase, bot, tg: int) -> None:  # noqa: ANN001
    need = await missing(db, bot, tg)
    if need:
        raise GCError("must_join", chats=need)


def _chat_ref(raw: str):  # noqa: ANN202
    raw = str(raw).strip()
    return int(raw) if re.fullmatch(r"-?\d+", raw) else raw


def parse_chat(raw: str) -> str:
    """@name، t.me/name یا آیدی عددی ← چیزی که getChat می فهمد. لینک دعوت خصوصی (t.me/+…) آیدی ندارد."""
    s = str(raw or "").strip()
    if re.fullmatch(r"-?\d{5,20}", s):
        return s
    m = re.fullmatch(r"(?:https?://)?(?:t\.me|telegram\.me)/(?!\+|joinchat/)([A-Za-z][A-Za-z0-9_]{3,31})/?", s)
    if m:
        return "@" + m.group(1)
    if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,31}", s):
        return "@" + s.lstrip("@")
    raise GCError("need_id")


def clean_url(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if s.startswith("@"):
        s = "https://t.me/" + s[1:]
    if not re.fullmatch(r"https://[^\s<>\"']{4,300}", s):
        raise GCError("bad_url")
    return s


async def add_chat(db: GCDatabase, bot, raw: str, url: str, title: str) -> dict:  # noqa: ANN001
    """کانال/گروه تازه: ربات باید آن را ببیند (و در کانال ادمین باشد)؛ لینک اگر داده نشد ساخته می شود."""
    if bot is None:
        raise GCError("no_bot")
    cfg = dict(await load(db, "gate"))
    chats = list(cfg.get("chats") or [])
    if len(chats) >= MAX_CHATS:
        raise GCError("too_many")
    ref = parse_chat(raw)
    try:
        chat = await bot.get_chat(_chat_ref(ref))
    except Exception:  # noqa: BLE001
        raise GCError("chat_not_found") from None
    try:
        me = await bot.get_me()
        bm = await bot.get_chat_member(chat.id, me.id)
        is_admin = bm.status in ("administrator", "creator")
    except Exception:  # noqa: BLE001
        is_admin = False
    if not is_admin:
        raise GCError("bot_not_admin")
    if any(str(c["id"]) == str(chat.id) for c in chats):
        raise GCError("already")
    link = clean_url(url)
    if not link and chat.username:
        link = f"https://t.me/{chat.username}"
    if not link:
        try:
            link = await bot.export_chat_invite_link(chat.id)
        except Exception:  # noqa: BLE001
            raise GCError("need_url") from None
    kind = "channel" if chat.type == "channel" else "group"
    chats.append({"id": str(chat.id), "title": " ".join(str(title or chat.title or "").split())[:60] or "کانال", "url": link, "kind": kind})
    cfg["chats"] = chats
    return await save(db, "gate", cfg)


# ---------- پاپ آپ ----------
def media_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(gc.db_path)), "gc_media")


def save_image(data_url: str) -> str:
    """عکس پاپ آپ (data:image/...;base64) روی دیسک ← "media/popup-<hash>.<پسوند>"."""
    m = re.fullmatch(r"data:image/[a-z+.-]+;base64,([A-Za-z0-9+/=\s]+)", str(data_url or ""))
    if not m:
        raise GCError("bad_image")
    try:
        raw = base64.b64decode(m.group(1), validate=False)
    except ValueError:
        raise GCError("bad_image") from None
    return store_media(raw, "popup")


def store_media(raw: bytes, prefix: str) -> str:
    """عکس (jpg، png، webp، gif تا IMG_MAX) روی دیسک ← "media/<prefix>-<hash>.<پسوند>"؛ prefix: popup یا bc"""
    if not raw or len(raw) > IMG_MAX:
        raise GCError("bad_image")
    ext = next((e for sig, e in _TYPES.items() if raw.startswith(sig)), None)
    if not ext or (ext == "webp" and raw[8:12] != b"WEBP"):
        raise GCError("bad_image")
    name = f"{prefix}-{hashlib.sha1(raw).hexdigest()[:12]}.{ext}"
    os.makedirs(media_dir(), exist_ok=True)
    path = os.path.join(media_dir(), name)
    if not os.path.exists(path):
        with open(path + ".tmp", "wb") as fh:
            fh.write(raw)
        os.replace(path + ".tmp", path)
    return "media/" + name


def read_media(name: str) -> tuple[bytes, str] | None:
    if not MEDIA_RE.match(name):
        return None
    try:
        with open(os.path.join(media_dir(), name), "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    ext = name.rsplit(".", 1)[1]
    return data, {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}[ext]


async def set_popup(db: GCDatabase, body: dict) -> dict:
    old = await load(db, "popup")
    text = str(body.get("text") or "").strip()[:1200]
    title = " ".join(str(body.get("title") or "").split())[:80]
    btn = " ".join(str(body.get("btn") or "").split())[:40]
    url = clean_url(body.get("url"))
    img = old.get("img", "")
    if body.get("img") == "":
        img = ""
    elif str(body.get("img") or "").startswith("data:"):
        img = save_image(body["img"])
    elif str(body.get("img") or "").startswith("https://"):
        img = clean_url(body["img"])
    on = bool(body.get("on"))
    if on and not (text or title or img):
        raise GCError("empty_popup")
    if btn and not url:
        raise GCError("need_url")
    val = {"on": on, "v": int(old.get("v") or 0) + 1, "title": title, "text": text, "img": img, "btn": btn if url else "",
           "url": url, "mode": "always" if body.get("mode") == "always" else "once"}
    return await save(db, "popup", val)


async def popup_view(db: GCDatabase) -> dict | None:
    p = await load(db, "popup")
    if not p.get("on"):
        return None
    return {k: p.get(k) for k in ("v", "title", "text", "img", "btn", "url", "mode")}
