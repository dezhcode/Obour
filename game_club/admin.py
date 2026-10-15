"""پنل مدیریت Game Club (صفحه admin.html، همه زیر /gc/api/admin...).

ادمین ها همان ADMIN_IDS عبور هستند؛ ورود با initData تلگرام از مینی اپ Game Club.
برای غیر ادمین هر مسیر admin «پیدا نشد» برمی گرداند تا وجود پنل معلوم نشود.

بخش ها: داشبورد، کاربران (جستجو، جزئیات، تغییر امتیاز، مسدود کردن، پیام مستقیم)،
میزها (در جریان و تمام شده، بستن و برگرداندن ورودی)، تراکنش ها، پیام همگانی،
تنظیمات زنده (بر .env مقدم) و گزارش کارهای ادمین.

پیام همگانی در پس زمینه روی loop عبور فرستاده می شود (حدود ۲۰ پیام در ثانیه) و
پیشرفتش در دیتابیس است؛ اگر پروسه بسته شد، با اولین درخواست بعدی از همان جا ادامه می یابد.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time

from . import emoji as emo
from . import style as st
from .config import GCConfig, gc
from .db import GCDatabase, pic_url
from .service import GCError

log = logging.getLogger(__name__)

GAMES = ("ludo", "hokm", "football", "billiard")
PAGES = {"": "خانه", "ludo-lobby.html": "منچ", "hokm-lobby.html": "حکم", "football-lobby.html": "فوتبال",
         "billiard-lobby.html": "بیلیارد",
         "shop.html": "فروشگاه و کیف", "profile.html": "پروفایل", "games.html": "بازی ها", "friends.html": "دوستان"}
KINDS = ("charge", "entry", "refund", "prize", "admin", "transfer", "shop", "gift", "style")
# تنظیمات قابل تغییر از پنل: (نوع، کمینه، بیشینه)
SETTINGS = {
    "maintenance": ("bool", 0, 1),
    "stake_enabled": ("bool", 0, 1),
    "turn_seconds": ("int", 8, 60),
    "bot_fill_seconds": ("int", 0, 120),
    "rake_percent": ("int", 0, 30),
    "notice": ("text", 0, 300),
}
_BC_TAG = re.compile(r"</?(b|strong|i|em|u|s|a|code|pre|tg-spoiler|blockquote|tg-emoji)(\s[^>]*)?>", re.I)
BC_BUTTONS = 3   # حداکثر دکمه زیر پیام همگانی


def is_admin(tg: int) -> bool:
    from app.config import config as obour_cfg

    return tg in obour_cfg.admin_ids


# ---------- تنظیمات زنده ----------
_synced = 0.0


def _parse(key: str, raw: str):  # noqa: ANN202
    kind, lo, hi = SETTINGS[key]
    if kind == "bool":
        return raw in ("1", "true", "on")
    if kind == "int":
        return min(hi, max(lo, int(raw)))
    return raw[:hi]


async def sync_settings(db: GCDatabase, force: bool = False) -> None:
    """مقدارهای جدول settings روی gc می نشیند (هر پروسه حداکثر هر ۱۰ ثانیه یک بار می خواند)."""
    global _synced
    if not force and time.time() - _synced < 10:
        return
    _synced = time.time()
    rows = await db.settings_all()
    emo.load_rows(rows)                      # ایموجی های پریمیوم (emoji:<key>)
    for key in SETTINGS:
        default = getattr(GCConfig, key)
        try:
            setattr(gc, key, _parse(key, rows[key]) if key in rows else default)
        except (TypeError, ValueError):
            setattr(gc, key, default)


def _settings_view(rows: dict) -> list[dict]:
    return [{"key": k, "kind": SETTINGS[k][0], "min": SETTINGS[k][1], "max": SETTINGS[k][2],
             "value": getattr(gc, k), "env": getattr(GCConfig, k), "custom": k in rows} for k in SETTINGS]


# ---------- پیام ----------
def parse_buttons(raw: str) -> list[tuple[str, str, str]]:
    """دکمه های زیر پیام: هر خط «صفحه|متن|کلید ایموجی» (شکل قدیمی «صفحه|متن» هم درست است)."""
    out = []
    for line in str(raw or "").splitlines():
        if not line.strip():
            continue
        page, label, key = (line.split("|") + ["", "", ""])[:3]
        if page not in PAGES:
            continue
        label = " ".join(label.split())[:40] or "ورود به Game Club"
        key = key.strip()
        out.append((page, label, key if key in emo.CATALOG or (key.isdigit() and len(key) < 25) else ""))
    return out[:BC_BUTTONS]


def _kb(button: str):  # noqa: ANN202
    """هر دکمه یک ردیف؛ ایموجی پریمیوم (کلید یا ایموجی اول متن) آیکن کنار متن دکمه می شود."""
    from aiogram.types import InlineKeyboardMarkup, WebAppInfo

    btns = parse_buttons(button)
    if not btns or not gc.webapp_url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[st.kb_button(label, key or None, web_app=WebAppInfo(url=gc.webapp_url + page))]
                                                 for page, label, key in btns])


async def _send(bot, tg: int, text: str = "", button: str = "", src: tuple | None = None) -> str:  # noqa: ANN001
    """یک پیام؛ خروجی: ok، blocked (کاربر ربات را بسته) یا failed."""
    from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

    for _ in range(3):
        try:
            if src:
                await bot.copy_message(tg, src[0], src[1], reply_markup=_kb(button))
            else:
                await bot.send_message(tg, emo.apply(text), reply_markup=_kb(button), disable_web_page_preview=True)
            return "ok"
        except TelegramRetryAfter as e:
            await asyncio.sleep(min(30, e.retry_after) + 0.5)
        except TelegramForbiddenError:
            return "blocked"
        except Exception as e:  # noqa: BLE001
            log.info("پیام Game Club به %s نرسید: %s", tg, e)
            return "failed"
    return "failed"


def _clean_text(text: str) -> str:
    """متن پیام ادمین: فقط برچسب های ساده HTML تلگرام می ماند؛ بقیه < > & امن می شوند."""
    text = str(text or "").strip()[:3500]
    keep: list[str] = []

    def stash(m: re.Match) -> str:
        keep.append(m.group(0))
        return f"\x00{len(keep) - 1}\x00"

    text = html.escape(_BC_TAG.sub(stash, text), quote=False)
    return re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], text)


BATCH, GAP = 25, 0.05
_running: asyncio.Task | None = None
_checked = 0.0


async def run_broadcasts(budget: float = 3600.0) -> None:
    """همه پیام های همگانی فعال را جلو می برد. قفل دیتابیس جلوی فرستادن دوباره از دو پروسه را می گیرد."""
    from .bot import gcrt

    g = await gcrt.ensure()
    db, bot = g.db, g.bot
    if bot is None:
        return
    end = time.time() + budget
    for job in await db.bc_active():
        key = f"gcbc:{job['id']}"
        if not await db.try_lock(key, ttl=60):
            continue
        try:
            while time.time() < end:
                cur = await db.bc_get(job["id"])
                if not cur or cur["status"] != "active":
                    break
                ids = await db.bc_targets(cur["target"], cur["cursor"], BATCH)
                if not ids:
                    await db.bc_finish(cur["id"], "done")
                    log.warning("پیام همگانی Game Club %s تمام شد", cur["id"])
                    break
                src = (cur["src_chat"], cur["src_msg"]) if cur["src_msg"] else None
                n = {"ok": 0, "failed": 0, "blocked": 0}
                for tg in ids:
                    n[await _send(bot, tg, cur["text"], cur["button"], src)] += 1
                    await asyncio.sleep(GAP)
                await db.bc_progress(cur["id"], ids[-1], n["ok"], n["failed"], n["blocked"])
                await db.extend_lock(key, 60)
        finally:
            await db.unlock(key)


def kick() -> None:
    """فرستادن در پس زمینه (روی همین loop)؛ اگر در این پروسه در حال اجراست کاری نمی کند."""
    global _running
    if _running is not None and not _running.done():
        return
    _running = asyncio.get_running_loop().create_task(run_broadcasts())


async def resume_if_needed(db: GCDatabase) -> None:
    """هر درخواستی (حداکثر دقیقه ای یک بار) پیام همگانی نیمه کاره را از سر می گیرد."""
    global _checked
    if time.time() - _checked < 60:
        return
    _checked = time.time()
    if await db.bc_active():
        kick()


# ---------- خلاصه ها ----------
def _player_row(p: dict) -> dict:
    return {"id": p["tg_id"], "name": p["name"], "tg_name": p.get("tg_name") or "", "username": p.get("username") or "", "av": p["av"], "pic": pic_url(p),
            "points": p["points"], "games": p["games"], "wins": p["wins"], "banned": bool(p.get("banned")),
            "created": p["created_at"], "seen": p["seen_at"]}


def _score(game: str, st: dict) -> str:
    sc = st.get("score")
    if game in ("football", "hokm") and isinstance(sc, list) and len(sc) == 2:
        return f"{sc[0]} - {sc[1]}"
    if game == "billiard" and isinstance(st.get("balls"), list) and st.get("solids", -1) >= 0:
        from .billiard import score
        a, b = score(st)
        return f"{a} - {b}"
    if game == "ludo" and isinstance(st.get("pawns"), dict):
        fa = {"blue": "آبی", "red": "قرمز", "green": "سبز", "yellow": "زرد"}
        return " · ".join(f"{fa.get(c, c)} {sum(1 for x in ps if x == 56)}" for c, ps in st["pawns"].items())
    return ""


def _table(m: dict, rows: list[dict]) -> dict:
    st, cfg = m["state"] or {}, m["cfg"] or {}
    if m["status"] == "lobby":
        names = [s.get("name", "") for s in st.get("seats", [])]
    else:
        names = [(r.get("name") or str(r["tg_id"])) for r in rows]
        bots = [p.get("name", "") for p in (st.get("players") or {}).values() if isinstance(p, dict) and p.get("bot")]
        names += [b + " (ربات)" for b in bots]
    return {"id": m["id"], "game": m["game"] or cfg.get("game", "ludo"), "status": m["status"], "mode": cfg.get("mode"),
            "entry": cfg.get("entry", 0), "players": names, "need": cfg.get("players", 0), "invite": bool(m.get("invite")),
            "score": _score(m["game"] or "", st), "created": m["created_at"], "updated": m["updated_at"],
            "pot": st.get("pot", 0), "over": bool(st.get("over")), "winner": st.get("winner")}


def _page(q: dict) -> int:
    try:
        return max(0, min(200, int(q.get("page") or 0)))
    except ValueError:
        return 0


def _int(v, name: str = "bad_input") -> int:  # noqa: ANN001
    try:
        return int(v)
    except (TypeError, ValueError):
        raise GCError(name) from None


# ---------- API ----------
async def handle(name: str, method: str, admin: int, q: dict, body: dict, db: GCDatabase) -> dict:  # noqa: C901
    if not is_admin(admin):
        raise GCError("not_found")
    from . import service
    from .bot import gcrt

    now = int(time.time())
    path = name[len("admin"):].strip("/")

    if method == "GET":
        if path == "":
            await resume_if_needed(db)
            return {"stats": await db.admin_stats(now), "daily": await db.admin_daily(now),
                    "rate": gc.point_toman, "maintenance": gc.maintenance,
                    "bc": [dict(b) for b in await db.bc_active()]}
        if path == "users":
            rows = await db.admin_players(q.get("q", ""), q.get("sort", "recent"), q.get("f", "all"), _page(q) * 30, 30)
            return {"users": [_player_row(r) for r in rows], "more": len(rows) == 30}
        if path == "user":
            tg = _int(q.get("id"))
            p = await db.get_player(tg)
            if not p:
                raise GCError("not_found")
            return {"user": {**_player_row(p), "ban_note": p.get("ban_note", ""), "admin": is_admin(tg)},
                    "ledger": await db.ledger_of(tg), "results": [
                        {**r, "cfg": json.loads(r["cfg"]) if r.get("cfg") else {}} for r in await db.results_of(tg)],
                    "tables": await service.my_tables(db, tg)}
        if path == "tables":
            live = q.get("s", "live") != "over"
            ms = await db.matches_by_status(("playing", "lobby") if live else ("over", "cancelled"), _page(q) * 30, 30)
            return {"tables": [_table(m, await db.match_players_named(m["id"])) for m in ms], "more": len(ms) == 30}
        if path == "table":
            m = await db.get_match(str(q.get("id") or ""))
            if not m:
                raise GCError("not_found")
            rows = await db.match_players_named(m["id"])
            return {"table": _table(m, rows), "rows": rows, "cfg": m["cfg"]}
        if path == "ledger":
            k = q.get("k", "")
            rows = await db.ledger_recent(k if k in KINDS else "", _page(q) * 40, 40)
            return {"rows": rows, "more": len(rows) == 40}
        if path == "broadcasts":
            await resume_if_needed(db)
            # فقط آمار؛ فرستادن از ربات است (/gcbc)
            rows = [bc_view(b) for b in await db.bc_list(30)]
            done = [b for b in rows if b["status"] != "active"]
            sent, blocked = sum(b["sent"] for b in rows), sum(b["blocked"] for b in rows)
            return {"list": rows, "summary": {"count": len(rows), "active": len(rows) - len(done), "sent": sent, "blocked": blocked,
                                              "failed": sum(b["failed"] for b in rows), "total": sum(b["total"] for b in rows)}}
        if path == "emoji":
            return {"emojis": emo.listing(), "obour": len(emo.from_obour())}
        if path == "settings":
            return {"settings": _settings_view(await db.settings_all())}
        if path == "log":
            return {"rows": await db.admin_log(_page(q) * 40, 40)}
        raise GCError("not_found")

    # ---------- نوشتن ----------
    if path == "points":
        tg, amount = _int(body.get("id")), _int(body.get("amount"))
        if not amount or abs(amount) > 10_000_000:
            raise GCError("bad_amount")
        if not await db.get_player(tg):
            raise GCError("not_found")
        idem = "admin:" + str(body.get("idem") or "")[:64]
        if len(idem) < 14:
            raise GCError("bad_idem")
        note = "پشتیبانی" + (": " + str(body.get("note")).strip()[:80] if str(body.get("note") or "").strip() else "")
        ok = (await service.earn(db, tg, amount, "admin", note, f"admin:{admin}", idem) if amount > 0
              else await service.spend(db, tg, -amount, "admin", note, f"admin:{admin}", idem))
        if not ok:
            raise GCError("insufficient" if amount < 0 else "done_before")
        await db.log_admin(admin, "points", str(tg), f"{amount:+d} {note}")
        return {"ok": True, "points": (await db.get_player(tg))["points"]}
    if path == "ban":
        tg, banned = _int(body.get("id")), bool(body.get("banned"))
        if banned and is_admin(tg):
            raise GCError("bad_input")
        note = str(body.get("note") or "").strip()[:200]
        if not await db.set_ban(tg, banned, note):
            raise GCError("not_found")
        if banned:
            await service.queue_leave(db, tg)
        await db.log_admin(admin, "ban" if banned else "unban", str(tg), note)
        return {"ok": True}
    if path == "message":
        tg = _int(body.get("id"))
        text = _clean_text(body.get("text", ""))
        g = await gcrt.ensure()
        if not text or g.bot is None:
            raise GCError("bad_input")
        r = await _send(g.bot, tg, text, str(body.get("button") or ""))
        if r != "ok":
            raise GCError("send_" + r)
        await db.log_admin(admin, "message", str(tg), text[:120])
        return {"ok": True}
    if path == "close":
        mid = str(body.get("id") or "")
        r = await service.admin_close(db, mid)
        await db.log_admin(admin, "close", mid, f"refund {r['refunded']}")
        return {"ok": True, **r}
    if path == "broadcast/cancel":
        bid = _int(body.get("id"))
        if not await db.bc_finish(bid, "cancelled"):
            raise GCError("not_found")
        await db.log_admin(admin, "broadcast_cancel", str(bid))
        return {"ok": True}
    if path in ("emoji", "emoji/reset", "emoji/obour"):
        # ایموجی پریمیوم: آیدی دستی، برگرداندن به معمولی، یا کپی همه از عبور
        if path == "emoji/obour":
            pairs = emo.from_obour()
        else:
            key = str(body.get("key") or "")
            if key not in emo.CATALOG:
                raise GCError("bad_input")
            eid = "" if path == "emoji/reset" else re.sub(r"\D", "", str(body.get("id") or ""))[:24]
            if path == "emoji" and len(eid) < 5:
                raise GCError("bad_input")
            pairs = [(key, eid)]
        for k, eid in pairs:
            await (emo.set_emoji(db, k, eid) if eid else emo.reset(db, k))
        await db.log_admin(admin, "setting", "emoji", " ".join(k for k, _ in pairs)[:120] or "obour 0")
        return {"ok": True, "n": len(pairs), "emojis": emo.listing()}
    if path == "setting":
        key = str(body.get("key") or "")
        if key not in SETTINGS:
            raise GCError("bad_input")
        val = body.get("value")
        if val is None:
            await db.setting_put(key, None)
        else:
            kind = SETTINGS[key][0]
            raw = ("1" if val in (True, 1, "1", "true", "on") else "0") if kind == "bool" else str(val)
            try:
                _parse(key, raw)
            except (TypeError, ValueError):
                raise GCError("bad_input") from None
            if kind == "text":   # اطلاعیه صفحه خانه به صورت متن ساده نمایش داده می شود
                raw = " ".join(raw.split())[:SETTINGS[key][2]]
            await db.setting_put(key, raw)
        await sync_settings(db, force=True)
        await db.log_admin(admin, "setting", key, "reset" if val is None else str(getattr(gc, key))[:120])
        return {"ok": True, "settings": _settings_view(await db.settings_all())}
    raise GCError("not_found")


TARGET_KEYS = [("all", "همه"), ("active7", "فعال ۷ روز"), ("active30", "فعال ۳۰ روز"), ("game:hokm", "بازیکنان حکم"),
               ("game:ludo", "بازیکنان منچ"), ("game:football", "بازیکنان فوتبال"),
               ("game:billiard", "بازیکنان بیلیارد"), ("me", "فقط خودم")]


def target_label(t: str) -> str:
    """برچسب گیرنده ها، هم برای کلید فرم و هم برای مقدار ذخیره شده."""
    t = str(t or "all")
    if t.startswith("seen:"):
        days = round((time.time() - int(t[5:] or 0)) / 86400)
        return f"فعال {days} روز اخیر" if days > 0 else "فعال ها"
    if t.startswith("id:"):
        return "فقط خودم"
    return dict(TARGET_KEYS).get(t, "همه")


def bc_view(b: dict) -> dict:
    return {"id": b["id"], "status": b["status"], "total": b["total"], "sent": b["sent"], "failed": b["failed"],
            "blocked": b["blocked"], "created_at": b["created_at"], "finished_at": b.get("finished_at"),
            "copy": bool(b["src_msg"]), "text": re.sub(r"<[^>]+>", "", b["text"] or "")[:200], "target": target_label(b["target"]),
            "buttons": [label for _, label, _ in parse_buttons(b["button"])]}


def _target(t: str, admin: int) -> str:
    """مخاطبان پیام همگانی از فرم پنل: all، active7، active30، game:<name>، me"""
    t = str(t or "all")
    if t in ("active7", "active30"):
        return f"seen:{int(time.time()) - (7 if t == 'active7' else 30) * 86400}"
    if t.startswith("game:") and t[5:] in GAMES:
        return t
    if t == "me":
        return f"id:{admin}"
    return "all"
