"""اندپوینت های مینی اپ Game Club (همه زیر /gc/api/...).

هر درخواست initData تلگرام را در هدر X-Init-Data دارد و wsgi.py آن را
با توکن ربات Game Club می سنجد؛ اینجا کاربر تاییدشده می رسد.
خروجی همیشه dict است؛ خطا با GCError و یک کد کوتاه برمی گردد و متن
فارسی را مینی اپ می سازد.
"""
from __future__ import annotations

import json
import re

from . import admin, bridge, gate, groups, names, service, social
from .bot import gcrt
from .config import gc
from .db import pic_url
from .service import GCError

_IDEM = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _idem(body: dict) -> str:
    v = str(body.get("idem") or "")
    if not _IDEM.match(v):
        raise GCError("bad_idem")
    return v


def _obour():
    from app.runtime import runtime

    return runtime


def _name_state(p: dict) -> dict:
    """یوزرنیم و اینکه کی می شود دوباره عوضش کرد (بار اول آزاد است)."""
    at = int(p.get("uname_at") or 0)
    return {"name": p["name"], "name_next": at + names.RENAME_DAYS * 86400 if at else 0,
            "name_hint": not p.get("uname_seen") and not at}


def invite_link(code: str, game: str = "ludo") -> str:
    return f"https://t.me/{gc.username}?start={game}_{code}" if gc.username else ""


async def handle(name: str, method: str, user, q: dict, body: dict) -> dict:  # noqa: ANN001
    # فروشگاه در دوره آزمایشی خاموش است (GAME_CLUB_SHOP): نه فهرست، نه خرید، نه انتقال
    if name.startswith("shop") and not gc.shop_enabled:
        raise GCError("shop_off")
    g = await gcrt.ensure()
    gdb = g.db
    tg = user.id
    # نام و عکس هر بار از initData تلگرام به روز می شود
    full = getattr(user, "full_name", "") or user.first_name
    player = await gdb.player(tg, full or user.username or "بازیکن", user.username or None,
                              getattr(user, "photo_url", None))
    ob = _obour()
    await admin.sync_settings(gdb)          # تنظیمات پنل مدیریت (هر ۱۰ ثانیه)
    await admin.resume_if_needed(gdb)       # پیام همگانی نیمه کاره (هر دقیقه)

    # ---------- پنل مدیریت ----------
    if name == "admin" or name.startswith("admin/"):
        return await admin.handle(name, method, tg, q, body, gdb)
    # کاربر مسدود فقط صفحه خانه را می بیند (با پیام مسدودی)
    if player.get("banned") and name != "me":
        raise GCError("banned")
    # تعمیرات: میز تازه ساخته نمی شود؛ بازی های در جریان ادامه دارند
    if gc.maintenance and method == "POST" and not admin.is_admin(tg) and \
            re.match(r"^(ludo|hokm|football|billiard|divar|esmfamil|lashgar)/(queue|queue/bots|invite|join)$", name):
        raise GCError("maintenance")
    # عضویت اجباری (پنل مدیریت): ساختن یا نشستن سر میز فقط برای عضوهای کانال ها و گروه های لازم
    if method == "POST" and re.match(r"^(ludo|hokm|football|billiard|divar|esmfamil|lashgar)/(queue|queue/bots|invite|join)$", name):
        await gate.require(gdb, g.bot, tg)
    # ---------- باز شدن مینی اپ: کانال های لازم و پیام پاپ آپ ----------
    if name == "boot" and method == "GET":
        return {"gate": await gate.missing(gdb, g.bot, tg), "popup": await gate.popup_view(gdb)}
    if name == "gate/check" and method == "POST":      # «عضو شدم»: بدون حافظه دوباره از تلگرام
        return {"gate": await gate.missing(gdb, g.bot, tg, fresh=True)}

    # ---------- خود من ----------
    if name == "me" and method == "GET":
        ou = await bridge.obour_account(ob.db, tg)
        active = await gdb.active_match_of(tg)
        q_row = await gdb.queue_row(tg)
        return {
            "player": {**{k: player[k] for k in ("name", "av", "points", "games", "wins", "show_spend", "tutorial",
                                                 "sound")}, "pic": pic_url(player),
                       "joined": int(player.get("created_at") or 0), "bio": player.get("bio") or "",
                       "kots": int(player.get("kots") or 0),
                       "cover": player.get("cover") if player.get("cover") in service.COVERS else "gc", **_name_state(player)},
            "covers": [{"id": k, "name": v} for k, v in service.COVERS.items()],
            "history": await gdb.history(tg),
            "notify": await gdb.notify_of(tg),
            "obour": {"linked": bool(ou), "balance": int(ou["balance"]) if ou else 0},
            "active_match": active,
            "active_game": await gdb.match_game(active) if active else None,
            "queue": bool(q_row and not q_row["claimed"]),
            "tables": await service.my_tables(gdb, tg),
            "social": await social.badge(gdb, tg),
            "is_admin": admin.is_admin(tg), "banned": bool(player.get("banned")), "style": service.style_of(player),
            "notice": gc.notice, "maintenance": gc.maintenance,
            "settings": {"stake": gc.stake_enabled, "shop": gc.shop_enabled, "entries": list(gc.entries), "packs": list(gc.charge_packs),
                         "rate": gc.point_toman, "turn_s": gc.turn_seconds, "rake": gc.rake_percent,
                         "bot": gc.username, "obour_bot": await ob.db.get_setting("bot_username", "")},
        }
    # ---------- دوستان و پیام خصوصی ----------
    if name == "friends" and method == "GET":
        return await social.friends_view(gdb, tg)
    if name == "friends/find" and method == "GET":
        return await social.find(gdb, tg, str(q.get("n") or ""))
    if name == "friends/user" and method == "GET":
        return await social.profile(gdb, tg, str(q.get("u") or ""))
    if name in ("friends/request", "friends/accept", "friends/drop", "friends/block") and method == "POST":
        uid = str(body.get("uid") or "")
        if name == "friends/request":
            return await social.request(gdb, tg, uid)
        if name == "friends/accept":
            return await social.accept(gdb, tg, uid)
        if name == "friends/drop":
            return await social.drop(gdb, tg, uid)
        return await social.block(gdb, tg, uid, bool(body.get("on", True)))
    if name == "dm" and method == "GET":
        return await social.chat(gdb, tg, str(q.get("u") or ""), int(q.get("since") or 0))
    if name == "dm" and method == "POST":
        return await social.send(gdb, tg, str(body.get("uid") or ""), str(body.get("text") or ""))
    if name == "dm/invite" and method == "POST":
        return await social.invite(gdb, tg, str(body.get("uid") or ""), str(body.get("game") or ""))
    if name == "group/share" and method == "POST":   # کارت میز برای Telegram.WebApp.shareMessage
        return {"id": await groups.prepare_share(gdb, tg, str(body.get("game") or ""))}
    # ---------- یوزرنیم ----------
    if name == "name/check" and method == "GET":
        n = names.normalize(str(q.get("n") or ""))
        bad = names.problem(n)
        if not bad and n != player["name"] and await gdb.name_taken(n, tg):
            bad = "name_taken"
        out = {"name": n, "ok": not bad, "error": bad}
        if bad == "name_taken":
            out["suggest"] = [c for c in names.suggestion_candidates(n) if not await gdb.name_taken(c, tg)][:3]
        return out
    if name == "name" and method == "POST":
        err = await gdb.set_name(tg, str(body.get("name") or ""))
        if err:
            raise GCError(err)
        return _name_state(await gdb.get_player(tg) or player)
    if name == "name/seen" and method == "POST":
        await gdb.execute("UPDATE players SET uname_seen = 1 WHERE tg_id = ?", (tg,))
        return {"ok": True}
    # ---------- پروفایل: کارنامهٔ هر بازی و آخرین بازی ها ----------
    if name == "profile" and method == "GET":
        recent = []
        for r in await gdb.recent_games(tg):
            try:
                cfg = json.loads(r["cfg"] or "{}")
            except ValueError:
                cfg = {}
            recent.append({"game": r["game"], "won": bool(r["won"]), "prize": int(r["prize"] or 0), "at": int(r["at"]),
                           "mode": cfg.get("mode", "free"), "entry": int(cfg.get("entry") or 0)})
        return {"games": [{"game": g["game"], "games": int(g["games"]), "wins": int(g["wins"]), "prize": int(g["prize"])}
                          for g in await gdb.game_stats(tg)],
                "recent": recent}
    # ---------- فروشگاه ظاهر (میز و ورق حکم) ----------
    if name == "style" and method == "GET":
        return await service.style_view(gdb, tg)
    if name == "style/buy" and method == "POST":
        return await service.style_buy(gdb, tg, str(body.get("id") or ""), _idem(body))
    if name == "style/use" and method == "POST":
        return await service.style_use(gdb, tg, str(body.get("id") or ""))
    if name == "settings" and method == "POST":
        for f in ("show_spend", "tutorial", "sound"):
            if f in body:
                await gdb.set_flag(tg, f, 1 if body[f] else 0)
        if "cover" in body and str(body["cover"]) not in service.COVERS:
            raise GCError("bad_cover")
        await gdb.set_profile(tg, cover=str(body["cover"]) if "cover" in body else None,
                              bio=str(body.get("bio") or "") if "bio" in body else None)
        p = await gdb.get_player(tg) or {}
        return {"ok": True, "bio": p.get("bio") or "", "cover": p.get("cover") or "gc"}
    if name == "notify" and method == "POST":
        game = str(body.get("game") or "")
        if game not in ("esm", "hokm", "football"):
            raise GCError("bad_game")
        return {"on": await gdb.toggle_notify(tg, game)}

    # ---------- کیف امتیاز و عبور ----------
    if name == "wallet/charge" and method == "POST":
        return await bridge.charge(gdb, ob.db, tg, int(body.get("points") or 0), _idem(body))
    if name == "shop" and method == "GET":
        ou = await bridge.obour_account(ob.db, tg)
        return {"plans": await bridge.plans(ob.db), "rate": gc.point_toman,
                "obour": {"linked": bool(ou), "balance": int(ou["balance"]) if ou else 0}}
    if name == "shop/buy" and method == "POST":
        return await bridge.buy(gdb, ob.db, ob.panel, ob.bot, tg, int(body.get("plan_id") or 0), _idem(body))
    if name == "shop/transfer" and method == "POST":
        return await bridge.transfer(gdb, ob.db, tg, int(body.get("points") or 0), _idem(body))

    # ---------- رده بندی ----------
    if name == "leaderboard" and method == "GET" and q.get("game"):
        return await service.game_leaderboard(gdb, tg, str(q.get("game")), q.get("period") or "week")
    if name == "leaderboard" and method == "GET":
        kind = "spend" if q.get("kind") == "spend" else "top"
        return await service.leaderboard(gdb, tg, kind, q.get("period") or "week")

    # ---------- میزها: منچ، حکم، فوتبال، بیلیارد، دیوار، اسم‌فامیل و لشگر کاغذی (ludo/...، hokm/...، ...) با یک سرویس ----------
    game, _, op = name.partition("/")
    if game in service.GROUP_ONLY and op in ("queue", "queue/bots", "invite"):
        raise GCError("group_only")       # میز اسم‌فامیل و لشگر کاغذی فقط از کارت گروه ساخته می شود
    if game == "lashgar" and op == "ink":   # نقاشی (خط های مداد) جدا از نمای میز
        if method == "POST":
            return await service.ink_post(gdb, tg, str(body.get("match") or ""), body.get("ops"))
        return await service.ink_get(gdb, tg, str(q.get("match") or ""), int(q.get("since") or 0) if str(q.get("since") or "0").isdigit() else 0,
                                     q.get("snap") == "1")
    if game in service.GAMES and op:
        def cfg_in() -> dict:
            c = body.get("cfg") or {}
            return {**c, "game": game} if isinstance(c, dict) else {"game": game}

        if op == "queue":
            if method == "POST":
                return await service.queue_join(gdb, tg, cfg_in())
            return await service.queue_status(gdb, tg)
        if op == "queue/bots" and method == "POST":
            return await service.queue_bots(gdb, tg)
        if op == "queue/leave" and method == "POST":
            return await service.queue_leave(gdb, tg)
        if op == "invite" and method == "POST":
            out = await service.invite_create(gdb, tg, cfg_in())
            out["link"] = invite_link(out["code"], game)
            return out
        if op == "join" and method == "POST":
            return await service.invite_join(gdb, tg, str(body.get("code") or ""))
        if op == "start" and method == "POST":
            await service.lobby_start(gdb, tg, str(body.get("match") or ""))
            return {"ok": True}
        if op == "match" and method == "GET":
            mid = q.get("id") or await gdb.active_match_of(tg, game) or ""
            if not mid:
                raise GCError("not_found")
            chat = q.get("chat")
            out = await service.match_view(gdb, tg, mid, int(q.get("since") or 0),
                                           int(chat) if str(chat or "").isdigit() else None)
            if out.get("lobby"):
                out["lobby"]["link"] = invite_link(out["lobby"]["code"] or "", service.game_of(out["cfg"]))
            return out
        acts = {"ludo": ("roll", "move"), "hokm": ("trump", "play"), "football": ("setup", "shot"),
                "billiard": ("shot", "aim"), "divar": ("move", "wall"),
                "esmfamil": ("answer", "stop", "submit", "appeal", "vote", "ready"),
                "lashgar": ("army", "units", "ready", "unready", "shoot")}[game]
        if op in acts and method == "POST":
            return await service.act(gdb, tg, str(body.get("match") or ""), op, body.get("k"),
                                     int(body.get("since") or 0), body)
        if op == "chat" and method == "POST":
            return await service.chat_send(gdb, tg, str(body.get("match") or ""), str(body.get("text") or ""))
        if op == "leave" and method == "POST":
            return await service.leave_any(gdb, tg, str(body.get("match") or ""))

    raise GCError("not_found")
