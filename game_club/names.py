"""یوزرنیم بازیکن ها: اسمی که همه جای Game Club نشان داده می شود (به جای اسم تلگرام).

قواعد:
- ۳ تا ۱۶ نویسه؛ اولی حرف انگلیسی، بقیه حرف انگلیسی کوچک، عدد یا _
- یکتا (همه کوچک ذخیره می شوند پس بزرگی و کوچکی حرف فرقی نمی کند)
- چند کلمهٔ رزرو و چند کلمهٔ زشت پذیرفته نمی شود
هر کاربر تازه یک اسم تصادفی خوش آهنگ می گیرد (مثل lucky_falcon) و بعد می تواند عوضش کند.
"""
from __future__ import annotations

import random
import re

MIN_LEN, MAX_LEN = 3, 16
RENAME_DAYS = 30
PATTERN = re.compile(rf"^[a-z][a-z0-9_]{{{MIN_LEN - 1},{MAX_LEN - 1}}}$")

RESERVED = {
    "admin", "admins", "administrator", "root", "support", "help", "system", "moderator", "mod",
    "obour", "gameclub", "game_club", "gc", "bot", "official", "owner", "staff", "telegram", "null", "undefined",
}
# کلمه هایی که هیچ جای یوزرنیم نباید باشند
BLOCKED = ("fuck", "shit", "bitch", "pussy", "porn", "nigg", "whore", "jende")
# کلمه های کوتاه فقط وقتی خودشان یک تکه اند (kosar و kirk قبول است، kos_x نه)
BLOCKED_WORDS = {"sex", "dick", "kir", "kos", "koon", "kon", "kun", "kooni"}

ADJ = (
    "lucky", "brave", "swift", "calm", "bold", "happy", "clever", "quiet", "wild", "sunny", "smart", "royal",
    "silver", "golden", "rapid", "jolly", "mighty", "noble", "witty", "cool", "proud", "keen", "fierce", "gentle",
    "magic", "cosmic", "shiny", "sneaky", "frosty", "stormy", "misty", "rusty", "dusty", "funky", "lazy", "eager",
)
NOUN = (
    "falcon", "tiger", "lion", "panda", "fox", "wolf", "eagle", "otter", "koala", "hawk", "raven", "shark",
    "comet", "rocket", "pirate", "ninja", "wizard", "knight", "joker", "ace", "king", "queen", "jack", "dice",
    "pawn", "rook", "star", "moon", "storm", "river", "maple", "cactus", "mango", "pepper", "cookie", "puma",
)


def normalize(raw: str) -> str:
    return (raw or "").strip().lstrip("@").lower()


def problem(name: str) -> str | None:
    """کد مشکل یوزرنیم، یا None اگر قابل قبول است (یکتا بودن را دیتابیس می سنجد)."""
    if len(name) < MIN_LEN:
        return "name_short"
    if len(name) > MAX_LEN:
        return "name_long"
    if not name[0].isascii() or not name[0].isalpha():
        return "name_start"
    if not PATTERN.match(name):
        return "name_chars"
    parts = set(re.split(r"[_0-9]+", name))
    if name in RESERVED or any(b in name for b in BLOCKED) or parts & BLOCKED_WORDS:
        return "name_reserved"
    return None


def random_name(rng: random.Random | None = None) -> str:
    r = rng or random
    for _ in range(20):
        n = f"{r.choice(ADJ)}_{r.choice(NOUN)}"
        if len(n) <= MAX_LEN:
            return n
    return "player_" + "".join(r.choice("abcdefghjkmnpqrstuvwxyz") for _ in range(6))


def random_candidates(rng: random.Random | None = None):
    """اسم های تصادفی پشت سر هم: اول دو کلمه ای، بعد با یک حرف و عدد اضافه تا حتما یکی آزاد باشد."""
    r = rng or random
    for _ in range(12):
        yield random_name(r)
    while True:
        base = random_name(r)[: MAX_LEN - 4]
        yield f"{base}_{r.randint(10, 999)}"


def suggestion_candidates(name: str) -> list[str]:
    """چند اسم قابل قبول نزدیک به اسمی که گرفته شده (آزاد بودنشان را دیتابیس می سنجد)."""
    base = re.sub(r"[^a-z0-9_]", "", name.lower())[: MAX_LEN - 5] or "player"
    if not base[0].isalpha():
        base = "p" + base
    out: list[str] = []
    for cand in (f"{base}_gc", f"the_{base}", f"{base}_play", f"{base}_x", f"{base}_{random.randint(10, 99)}"):
        cand = cand[:MAX_LEN]
        if problem(cand) is None and cand not in out:
            out.append(cand)
    return out
