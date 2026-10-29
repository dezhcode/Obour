"""دوستان AsoTas: درخواست دوستی، قبول و رد، حذف، بلاک، پیام خصوصی و دعوت به بازی.

هر کاربر بیرون فقط با شناسهٔ عمومی uid (همان کلید تصادفی عکس، pic) دیده می شود؛ آیدی تلگرام
هیچ وقت به مینی اپ نمی رسد. پیام خصوصی فقط بین دو دوست است و بلاک دو طرفه همه چیز را می بندد.
"""
from __future__ import annotations

import json
import time

from . import names, service
from .db import GCDatabase, pic_url
from .service import GCError

ONLINE_S = 150          # اگر در این چند ثانیهٔ آخر مینی اپ باز بوده، آنلاین است
MAX_FRIENDS = 300
MAX_PENDING = 60        # درخواست بی جواب فرستاده شده
REQ_PER_HOUR = 25
DM_MAX = 300
GAME_NAME = {"hokm": "حکم", "ludo": "منچ", "football": "فوتبال", "billiard": "بیلیارد", "divar": "دیوار",
             "esmfamil": "اسم‌فامیل", "lashgar": "لشگر کاغذی", "snakes": "مار و پله"}
# میز دعوتی که از صفحهٔ دوستان یا چت ساخته می شود (آزاد؛ سازنده بعدا می تواند خودش میز بسازد).
# اسم‌فامیل اینجا نیست: فقط در گروه بازی می شود
INVITE_CFG = {
    "hokm": {"game": "hokm", "mode": "free", "entry": 0, "target": 7},
    "ludo": {"mode": "free", "entry": 0, "players": 2, "pawns": 2},
    "football": {"game": "football", "mode": "free", "entry": 0, "target": 3},
    "billiard": {"game": "billiard", "mode": "free", "entry": 0, "players": 2},
    "divar": {"game": "divar", "mode": "free", "entry": 0, "players": 2, "variant": "classic"},
    "snakes": {"game": "snakes", "mode": "free", "entry": 0, "players": 2},
}


def public(p: dict) -> dict:
    return {"uid": p["pic"], "name": p["name"], "av": int(p.get("av") or 1), "pic": pic_url(p), "bio": p.get("bio") or ""}


async def _other(db: GCDatabase, me: int, uid: str) -> dict:
    p = await db.player_by_pic(str(uid or "")[:40])
    if not p or p["tg_id"] == me:
        raise GCError("not_found")
    return p


async def relation(db: GCDatabase, me: int, other: int) -> str:
    if me == other:
        return "self"
    if await db.blocked(me, other):
        return "blocked"
    row = await db.friend_row(me, other)
    if not row:
        return "none"
    if row["status"] == "accepted":
        return "friend"
    return "outgoing" if row["requester"] == me else "incoming"


async def _status(db: GCDatabase, p: dict, now: float) -> dict:
    online = now - int(p.get("seen_at") or 0) < ONLINE_S
    mid = await db.active_match_of(p["tg_id"]) if online else None
    game = await db.match_game(mid) if mid else None
    return {"online": online, "playing": game if game in GAME_NAME else None, "seen": int(p.get("seen_at") or 0)}


async def friends_view(db: GCDatabase, me: int) -> dict:
    now = time.time()
    unread = await db.unread_by(me)
    friends, incoming, outgoing = [], [], []
    for r in await db.friend_rows(me):
        item = public(r)
        if r["status"] == "accepted":
            item.update(await _status(db, r, now))
            item["unread"] = unread.get(r["tg_id"], 0)
            friends.append(item)
        elif r["requester"] == me:
            outgoing.append(item)
        else:
            item["at"] = int(r["updated_at"])
            incoming.append(item)
    friends.sort(key=lambda f: (not f["online"], -f["unread"], f["name"]))
    return {"friends": friends, "incoming": incoming, "outgoing": outgoing,
            "blocked": [public(p) for p in await db.blocked_list(me)]}


async def badge(db: GCDatabase, me: int) -> dict:
    requests = sum(1 for r in await db.friend_rows(me) if r["status"] == "pending" and r["requester"] != me)
    return {"requests": requests, "unread": sum((await db.unread_by(me)).values())}


async def find(db: GCDatabase, me: int, raw: str) -> dict:
    name = names.normalize(raw)
    if names.problem(name):
        raise GCError("not_found")
    p = await db.player_by_name(name)
    if not p or p.get("banned"):
        raise GCError("not_found")
    rel = await relation(db, me, p["tg_id"])
    # کسی که مرا بلاک کرده پیدا نمی شود
    if rel != "self" and await db.blocked(p["tg_id"], me):
        raise GCError("not_found")
    return {"user": {**public(p), "games": int(p.get("games") or 0), "wins": int(p.get("wins") or 0)}, "relation": rel}


async def profile(db: GCDatabase, me: int, uid: str) -> dict:
    p = await _other(db, me, uid)
    if await db.blocked(p["tg_id"], me):
        raise GCError("not_found")
    out = {**public(p), "games": int(p.get("games") or 0), "wins": int(p.get("wins") or 0),
           "joined": int(p.get("created_at") or 0), "cover": p.get("cover") or "gc"}
    out.update(await _status(db, p, time.time()))
    return {"user": out, "relation": await relation(db, me, p["tg_id"])}


async def request(db: GCDatabase, me: int, uid: str) -> dict:
    p = await _other(db, me, uid)
    other = p["tg_id"]
    if await db.blocked(me, other):
        raise GCError("you_blocked")
    if await db.blocked(other, me):
        raise GCError("cant_add")
    row = await db.friend_row(me, other)
    if row and row["status"] == "accepted":
        return {"relation": "friend"}
    if row and row["requester"] == other:         # او هم درخواست داده بود: همین الان دوست می شوید
        return await accept(db, me, uid)
    if row:
        return {"relation": "outgoing"}
    if await db.count_friends(me, "accepted") >= MAX_FRIENDS:
        raise GCError("too_many_friends")
    if await db.recent_requests(me, int(time.time()) - 3600) >= REQ_PER_HOUR or \
            sum(1 for r in await db.friend_rows(me) if r["status"] == "pending" and r["requester"] == me) >= MAX_PENDING:
        raise GCError("slow_requests")
    await db.set_friend(me, other, "pending", me)
    mine = await db.get_player(me) or {}
    await service._notify(db, other, f"freq:{me}:{other}:{int(time.time() // 86400)}",
                          f"<b>{mine.get('name', '')}</b> می‌خواد رفیقت بشه قبول می‌کنی؟ 🤝", "friends.html")
    return {"relation": "outgoing"}


async def accept(db: GCDatabase, me: int, uid: str) -> dict:
    p = await _other(db, me, uid)
    row = await db.friend_row(me, p["tg_id"])
    if not row or row["status"] != "pending" or row["requester"] == me:
        raise GCError("no_request")
    await db.set_friend(me, p["tg_id"], "accepted", row["requester"])
    mine = await db.get_player(me) or {}
    await service._notify(db, p["tg_id"], f"facc:{me}:{p['tg_id']}",
                          f"<b>{mine.get('name', '')}</b> درخواستتو قبول کرد و حالا دیگه رفیقید! 🎉", "friends.html")
    return {"relation": "friend"}


async def drop(db: GCDatabase, me: int, uid: str) -> dict:
    """رد درخواست، پس گرفتن درخواست یا حذف از دوستان."""
    p = await _other(db, me, uid)
    await db.del_friend(me, p["tg_id"])
    return {"relation": "none"}


async def block(db: GCDatabase, me: int, uid: str, on: bool) -> dict:
    p = await _other(db, me, uid)
    await db.set_block(me, p["tg_id"], on)
    if on:
        await db.del_friend(me, p["tg_id"])
    return {"relation": "blocked" if on else "none"}


def _msg(r: dict, me: int) -> dict:
    out = {"id": r["id"], "me": r["sender"] == me, "kind": r["kind"], "text": r["text"], "at": int(r["created_at"])}
    if r["kind"] == "invite":
        try:
            out["meta"] = json.loads(r["meta"] or "{}")
        except ValueError:
            out["meta"] = {}
    return out


async def chat(db: GCDatabase, me: int, uid: str, since: int = 0) -> dict:
    p = await _other(db, me, uid)
    rel = await relation(db, me, p["tg_id"])
    if await db.blocked(p["tg_id"], me):
        raise GCError("not_found")
    rows = await db.dms(me, p["tg_id"], max(0, since))
    mine = [r for r in rows if r["sender"] != me]
    if mine:
        await db.mark_read(me, p["tg_id"], mine[-1]["id"])
    user = {**public(p), **(await _status(db, p, time.time()))}
    return {"user": user, "relation": rel, "messages": [_msg(r, me) for r in rows]}


async def _can_message(db: GCDatabase, me: int, other: int) -> None:
    if await db.blocked(me, other):
        raise GCError("you_blocked")
    if await db.blocked(other, me) or await relation(db, me, other) != "friend":
        raise GCError("not_friends")


async def _ping_dm(db: GCDatabase, me: int, p: dict, text: str, page: str) -> None:
    """پیام تازه برای کسی که الان در مینی اپ نیست؛ حداکثر هر ۱۰ دقیقه یک بار از هر نفر."""
    if time.time() - int(p.get("seen_at") or 0) < ONLINE_S:
        return
    await service._notify(db, p["tg_id"], f"dm:{p['tg_id']}:{me}:{int(time.time() // 600)}", text, page)


async def send(db: GCDatabase, me: int, uid: str, text: str) -> dict:
    p = await _other(db, me, uid)
    await _can_message(db, me, p["tg_id"])
    text = service._CHAT_BAD.sub(" ", str(text or ""))
    text = " ".join(text.split())[:DM_MAX]
    if not text:
        raise GCError("empty")
    now = time.time()
    if await db.dm_sent_since(me, now - 0.7) or await db.dm_sent_since(me, now - 60) >= 30:
        raise GCError("chat_slow")
    mid = await db.add_dm(me, p["tg_id"], text)
    mine = await db.get_player(me) or {}
    await _ping_dm(db, me, p, f"<b>{mine.get('name', '')}</b> یه پیام برات فرستاده 💬", f"chat.html?u={mine.get('pic', '')}")
    return {"id": mid}


async def invite(db: GCDatabase, me: int, uid: str, game: str) -> dict:
    """یک میز دعوت آزاد می سازد و کارت دعوت را در چت دوست می گذارد."""
    if game not in INVITE_CFG:
        raise GCError("bad_game")
    p = await _other(db, me, uid)
    await _can_message(db, me, p["tg_id"])
    if await db.dm_sent_since(me, time.time() - 2):
        raise GCError("chat_slow")
    r = await service.invite_create(db, me, dict(INVITE_CFG[game]))
    meta = json.dumps({"game": game, "code": r["code"], "match": r["match"]})
    await db.add_dm(me, p["tg_id"], f"دعوت به {GAME_NAME[game]}", "invite", meta)
    mine = await db.get_player(me) or {}
    await service._notify(db, p["tg_id"], f"dminv:{r['match']}",
                          f"<b>{mine.get('name', '')}</b> دعوتت کرده به {GAME_NAME[game]} بزن بشین کنارش داره دست‌گرمی می‌کنه 😄",
                          f"{game}-lobby.html?join={r['code']}")
    return {"match": r["match"], "code": r["code"], "game": game}
