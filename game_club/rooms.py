"""اتاق بازی داخل برنامه: میزبان بازی و تنظیمش را انتخاب می کند، اتاق با کد ۶ حرفی ساخته می شود و
دوستان با دعوت (چت + نوتیفیکیشن)، لینک یا کد می آیند. هر مهمان «آماده‌ام» می زند و میزبان شروع می کند.

روی همان میز دعوت service.invite_create سوار است (status=lobby)؛ این جا فقط چیزهای اتاق:
تنظیم از همان گزینه های کارت گروه (groups.GAMES)، سقف نفر اسم‌فامیل، آماده بودن، بیرون کردن،
دعوت چند دوست با هم و یادآوری. اسم‌فامیل و لشگر کاغذی که قبلا فقط در گروه تلگرام ساخته می شدند
این جا هم ساخته می شوند.
"""
from __future__ import annotations

import json
import time

from . import groups, service, social
from .config import gc
from .db import GCDatabase, pic_url
from .service import GCError, mutate

INVITE_MAX = 20          # در هر دعوت چند دوست
REMIND_S = 60            # یادآوری به هر نفر حداکثر هر یک دقیقه
CODE_LEN = 6


def link(code: str) -> str:
    """لینک اتاق: صفحه ای روی سرور که برنامه را باز می کند، وگرنه تلگرام یا مایکت (wsgi: /r/<کد>)"""
    return f"{gc.base_url}/r/{code}" if gc.base_url and code else ""


def opts() -> list[dict]:
    """بازی ها و گزینه های هر کدام برای صفحهٔ ساخت اتاق (همان گزینه های کارت گروه)"""
    out = []
    for k, g in groups.GAMES.items():
        out.append({"id": k, "name": g["name"], "def": g["def"],
                    "opts": [{"key": key, "title": title, "vals": [[v, lab] for v, lab in vals]} for key, title, vals in g["opts"]],
                    "cap": [2, 10] if k == "esmfamil" else None})
    return out


async def create(db: GCDatabase, tg: int, game: str, picks: dict, cap: int | None = None) -> dict:
    if game not in groups.GAMES:
        raise GCError("bad_game")
    cfg = groups.cfg_of(game, picks if isinstance(picks, dict) else {})
    if game != "esmfamil":
        cap = None
    elif cap is not None:
        try:
            cap = max(2, min(10, int(cap)))
        except (TypeError, ValueError):
            raise GCError("bad_cfg") from None
    r = await service.invite_create(db, tg, cfg, cap=cap, room=True)
    return {**r, "game": game, "link": link(r["code"])}


async def _room(db: GCDatabase, code: str) -> dict:
    m = await db.match_by_invite(str(code or "").strip().upper()[:12])
    if not m:
        raise GCError("bad_invite")
    return m


async def peek(db: GCDatabase, code: str) -> dict:
    """پیش نمایش اتاق قبل از نشستن (صفحهٔ ورود با کد)"""
    m = await _room(db, code)
    host = await db.get_player(m["host"]) or {}
    seats = m["state"].get("seats", [])
    game = service.game_of(m["cfg"])
    return {"game": game, "code": m["invite"], "status": m["status"], "host": host.get("name", ""),
            "summary": groups.summary(game, m["cfg"]).rsplit(" · ", 1)[0] if game == "esmfamil" else groups.summary(game, m["cfg"]),
            "cap": service._cap(m),
            "seats": [{"name": s["name"], "av": s["av"], "pic": s.get("pic", "")} for s in seats]}


async def join(db: GCDatabase, tg: int, code: str) -> dict:
    m = await _room(db, code)
    r = await service.invite_join(db, tg, m["invite"])
    return {**r, "game": service.game_of(m["cfg"])}


async def _lobby(db: GCDatabase, match_id: str) -> dict:
    m = await db.get_match(str(match_id or ""))
    if not m or m["status"] != "lobby":
        raise GCError("not_found")
    return m


async def ready(db: GCDatabase, tg: int, match_id: str, on: bool) -> dict:
    await _lobby(db, match_id)

    def fn(mm: dict):
        seat = next((s for s in mm["state"].get("seats", []) if s["tg"] == tg), None)
        if mm["status"] != "lobby" or not seat:
            return False, False
        if bool(seat.get("ready")) == on:
            return False, True
        seat["ready"] = on
        return True, True
    _, ok = await mutate(db, match_id, fn)
    if not ok:
        raise GCError("not_found")
    await service._hook(db, match_id)
    return {"ready": on}


async def kick(db: GCDatabase, host: int, match_id: str, color: str) -> dict:
    m = await _lobby(db, match_id)
    if m["host"] != host:
        raise GCError("not_host")
    seat = next((s for s in m["state"].get("seats", []) if s["color"] == color), None)
    if not seat or seat["tg"] == host:
        raise GCError("not_found")
    await service.lobby_leave(db, seat["tg"], m)
    return {"ok": True}


def _ready_count(m: dict) -> int:
    return sum(1 for s in m["state"].get("seats", []) if s["tg"] == m["host"] or s.get("ready"))


async def start(db: GCDatabase, tg: int, match_id: str) -> dict:
    m = await _lobby(db, match_id)
    if m["host"] != tg:
        raise GCError("not_host")
    if _ready_count(m) < service.min_players(m["cfg"]):
        raise GCError("need_ready")
    await service.lobby_start(db, tg, match_id)
    return {"ok": True}


async def invite(db: GCDatabase, me: int, match_id: str, uids: list) -> dict:
    """دعوت چند دوست به اتاق: کارت دعوت در چت هر کدام، اعلان ربات و نوتیفیکیشن گوشی"""
    m = await _lobby(db, match_id)
    if not any(s["tg"] == me for s in m["state"].get("seats", [])):
        raise GCError("not_found")
    if not isinstance(uids, list) or not uids:
        raise GCError("bad_input")
    game = service.game_of(m["cfg"])
    mine = await db.get_player(me) or {}
    seated = {s["tg"] for s in m["state"].get("seats", [])}
    now, sent, add = time.time(), [], []
    for uid in [str(u)[:40] for u in uids[:INVITE_MAX]]:
        try:
            p = await social._other(db, me, uid)
            await social._can_message(db, me, p["tg_id"])
        except GCError:
            continue
        if p["tg_id"] in seated:
            continue
        old = next((i for i in m["state"].get("invited", []) if i["tg"] == p["tg_id"]), None)
        if old and now - old.get("at", 0) < REMIND_S:
            continue
        meta = json.dumps({"game": game, "code": m["invite"], "match": m["id"], "room": True})
        await db.add_dm(me, p["tg_id"], f"دعوت به اتاق {social.GAME_NAME[game]}", "invite", meta)
        await service._notify(db, p["tg_id"], f"rinv:{m['id']}:{p['tg_id']}:{int(now // REMIND_S)}",
                              f"<b>{mine.get('name', '')}</b> دعوتت کرد به اتاق {social.GAME_NAME[game]} 🎲 بزن بیا تو اتاق",
                              f"room.html?join={m['invite']}")
        add.append({"tg": p["tg_id"], "uid": p["pic"], "name": p["name"][:24], "av": int(p.get("av") or 1),
                    "pic": pic_url(p), "at": now})
        sent.append(uid)

    if add:
        def fn(mm: dict):
            if mm["status"] != "lobby":
                return False, None
            have = {s["tg"] for s in mm["state"].get("seats", [])}
            keep = [i for i in mm["state"].get("invited", []) if i["tg"] not in {a["tg"] for a in add}]
            mm["state"]["invited"] = (keep + [a for a in add if a["tg"] not in have])[-30:]
            return True, None
        await mutate(db, match_id, fn)
        await service._hook(db, match_id)
    return {"sent": sent}
