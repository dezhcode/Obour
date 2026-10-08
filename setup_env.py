"""ثبت خودکار توکن ها، سکرت وبهوک و آیدی ادمین در .env مرکزی.

  python setup_env.py              حالت پرسش و پاسخ (پیشنهادی)
  python setup_env.py --apply      همان + ری استارت و ثبت وبهوک هر دو ربات
  python setup_env.py --rotate     ساخت دوباره سکرت ها (وبهوک ها باید دوباره ثبت شوند)
  python setup_env.py --dry-run    فقط نشان بده چه چیزی عوض می شود
  python setup_env.py --panel      اطلاعات پنل PasarGuard را دوباره بپرس
  python setup_env.py --from setup.env   بدون تایپ: مقادیر از فایل (نمونه: setup.env.example)
راه اندازی کامل (کد، کتابخانه، پلن، وبهوک) با یک دستور: bash setup_all.sh

بدون پرسش (مثلا در اسکریپت دیگر):
  python setup_env.py --yes --bot-token ... --gc-token ... --admin-ids 111,222
توکن داده شده با فلگ در history شل می ماند؛ حالت پرسش و پاسخ امن تر است.

این اسکریپت:
  - اگر .env نباشد از روی .env.example می سازد
  - BOT_TOKEN و GAME_CLUB_BOT_TOKEN را می پرسد، شکلشان را چک می کند و با getMe
    تایید می کند؛ یوزرنیم ربات Game Club را خودش در GAME_CLUB_BOT_USERNAME می نویسد
  - ADMIN_IDS را می پرسد (آیدی عددی، با کاما)
  - WEBHOOK_SECRET، WEBHOOK_PATH، ADMIN_KEY و GAME_CLUB_WEBHOOK_SECRET را اگر خالی
    یا نامعتبر باشند می سازد؛ مقدار درست موجود را دست نمی زند (مگر با --rotate)
  - بقیه فایل (توضیح ها و ترتیب خط ها) را همان طور نگه می دارد
  - قبل از تغییر نسخه پشتیبان .env.bak می سازد و دسترسی هر دو را 600 می کند
  - هیچ توکن یا سکرتی را کامل چاپ نمی کند
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
EXAMPLE_PATH = BASE_DIR / ".env.example"

TOKEN_RE = re.compile(r"^\d{5,15}:[A-Za-z0-9_-]{30,}$")
# secret_token تلگرام: ۱ تا ۲۵۶ حرف از A-Z a-z 0-9 _ -
SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{24,256}$")
LINE_RE = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$")

OK, NEW, KEEP, BAD = "[ ثبت شد ]", "[ ساخته شد ]", "[ بدون تغییر ]", "[ خطا ]"


# ---------- خواندن و نوشتن .env بدون به هم ریختن فایل ----------
def _split_value(raw: str) -> tuple[str, str]:
    """مقدار و توضیح انتهای خط را جدا می کند (همان قاعده python-dotenv)."""
    raw = raw.rstrip("\n")
    s = raw.strip()
    if s[:1] in ("'", '"'):
        q = s[0]
        end = s.find(q, 1)
        if end > 0:
            return s[1:end], s[end + 1:]
    m = re.search(r"\s+#", raw)
    if m:
        return raw[: m.start()].strip(), raw[m.start():]
    return s, ""


def quote(value: str) -> str:
    """مقدار امن برای python-dotenv: ساده بدون کوتیشن، بقیه داخل کوتیشن."""
    if re.fullmatch(r"[A-Za-z0-9_\-.:/@,+=%~]*", value):
        return value
    if "'" not in value and "\n" not in value:
        return f"'{value}'"  # داخل ' ' همه چیز عینا خوانده می شود
    if '"' not in value and "\\" not in value and "\n" not in value:
        return f'"{value}"'
    raise ValueError("مقدار هم ' و هم \" (یا \\) دارد؛ آن را دستی در .env بنویس")


class EnvFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
        self.added: list[str] = []

    def get(self, key: str) -> str:
        value = ""
        for line in self.lines:  # مثل python-dotenv: آخرین تکرار برنده است
            m = LINE_RE.match(line)
            if m and m.group(2) == key:
                value = _split_value(m.group(4))[0]
        return value

    def set(self, key: str, value: str) -> None:
        found = False
        for i, line in enumerate(self.lines):
            m = LINE_RE.match(line)
            if m and m.group(2) == key:
                _, comment = _split_value(m.group(4))
                nl = "\n" if line.endswith("\n") else ""
                self.lines[i] = f"{m.group(1)}{key}={quote(value)}{comment}{nl}"
                found = True
        if not found:
            if self.lines and not self.lines[-1].endswith("\n"):
                self.lines[-1] += "\n"
            if not self.added:
                self.lines.append("\n# ---------- افزوده شده با setup_env.py ----------\n")
            self.lines.append(f"{key}={quote(value)}\n")
            self.added.append(key)

    def text(self) -> str:
        return "".join(self.lines)

    def save(self) -> None:
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(self.text())
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)


# ---------- کمکی ها ----------
def mask(value: str) -> str:
    if not value:
        return "-"
    if ":" in value and value.split(":", 1)[0].isdigit():  # توکن ربات: آیدی ربات + ۴ حرف آخر
        bot_id, rest = value.split(":", 1)
        return f"{bot_id}:…{rest[-4:]}"
    if len(value) < 24:  # پسورد و مانند آن: هیچ حرفی نشان داده نمی شود
        return f"•••• ({len(value)} حرف)"
    return f"{value[:3]}…{value[-3:]} ({len(value)} حرف)"


def parse_admin_ids(raw: str) -> list[int]:
    """'111, 222 333' -> [111, 222, 333]؛ اعداد فارسی هم پذیرفته می شوند."""
    raw = raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩،", "01234567890123456789,"))
    out: list[int] = []
    for part in re.split(r"[,\s]+", raw.strip()):
        if not part:
            continue
        if not part.isdigit() or not (1 <= int(part) < 10**15):
            raise ValueError(f"«{part}» آیدی عددی تلگرام نیست")
        if int(part) not in out:
            out.append(int(part))
    return out


def new_secret(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def is_placeholder_path(value: str) -> bool:
    return not value or "CHANGE_ME" in value.upper() or not value.startswith("/") or len(value) < 12


async def _get_me(token: str, proxy: str, api_base: str) -> tuple[str, str]:
    """('ok', username) یا ('bad', علت) یا ('net', علت). شبکه مثل خود ربات (TG_PROXY / TG_API_BASE)."""
    try:
        from aiogram import Bot
        from aiogram.client.session.aiohttp import AiohttpSession
        from aiogram.client.telegram import TelegramAPIServer
        from aiogram.exceptions import TelegramNotFound, TelegramUnauthorizedError
    except Exception:  # noqa: BLE001
        return "net", "aiogram نصب نیست (اول venv را فعال کن)"
    kwargs: dict = {}
    if proxy:
        kwargs["proxy"] = proxy
    if api_base:
        kwargs["api"] = TelegramAPIServer.from_base(api_base.rstrip("/"))
    try:
        session = AiohttpSession(**kwargs)
    except Exception as e:  # noqa: BLE001  (مثلا پروکسی socks بدون aiohttp-socks)
        return "net", f"ساخت اتصال: {e}"
    bot = Bot(token=token, session=session)
    try:
        me = await asyncio.wait_for(bot.get_me(), timeout=15)
        return "ok", me.username or ""
    except (TelegramUnauthorizedError, TelegramNotFound):
        return "bad", "تلگرام این توکن را نمی شناسد (باطل شده یا اشتباه کپی شده)"
    except Exception as e:  # noqa: BLE001
        return "net", f"{type(e).__name__}: {e}"[:160]
    finally:
        await bot.session.close()


def check_token(token: str, env: EnvFile) -> tuple[str, str]:
    return asyncio.run(_get_me(token, env.get("TG_PROXY"), env.get("TG_API_BASE")))


# ---------- پرسش ----------
class Asker:
    def __init__(self, interactive: bool) -> None:
        self.interactive = interactive

    def secret(self, label: str, current: str) -> str:
        if not self.interactive:
            return ""
        hint = f" [فعلی {mask(current)}، Enter = نگه دار]" if current else ""
        try:
            return getpass.getpass(f"{label}{hint}: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("\nلغو شد؛ چیزی نوشته نشد.")

    def text(self, label: str, current: str) -> str:
        if not self.interactive:
            return ""
        hint = f" [فعلی {current}، Enter = نگه دار]" if current else ""
        try:
            return input(f"{label}{hint}: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("\nلغو شد؛ چیزی نوشته نشد.")

    def yes(self, label: str, default: bool = False) -> bool:
        if not self.interactive:
            return default
        try:
            ans = input(f"{label} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise SystemExit("\nلغو شد؛ چیزی نوشته نشد.")
        return default if not ans else ans in ("y", "yes", "بله", "آره", "ب")


def resolve_token(name: str, title: str, given: str | None, env: EnvFile, ask: Asker,
                  verify: bool, required: bool, forbid: str = "") -> tuple[str, str]:
    """توکن نهایی و یوزرنیم ربات (اگر getMe جواب داد)."""
    current = env.get(name)
    for attempt in range(3):
        value = (given if given is not None else ask.secret(f"توکن {title}", current)) or current
        given = None  # بعد از خطا، از کاربر بپرس
        if not value:
            if required and ask.interactive and attempt < 2:
                print(f"  {title} خالی است. توکن را از @BotFather بردار.")
                continue
            return "", ""
        if not TOKEN_RE.match(value):
            print(f"  {BAD} شکل توکن درست نیست (باید مثل 123456789:AA... باشد)")
        elif forbid and value == forbid:
            print(f"  {BAD} ربات Game Club باید یک ربات جدا از ربات عبور باشد (توکن یکسان است)")
        else:
            if not verify:
                return value, ""
            status, info = check_token(value, env)
            if status == "ok":
                print(f"  تایید شد: @{info}")
                return value, info
            if status == "net" and ask.interactive and not env.get("TG_PROXY") and not env.get("TG_API_BASE"):
                print(f"  تلگرام از این هاست در دسترس نیست ({info})")
                proxy = ask.text("پروکسی تلگرام برای TG_PROXY (مثل socks5://host:port؛ Enter = بدون پروکسی)", "")
                if proxy:
                    env.set("TG_PROXY", proxy)
                    print("  TG_PROXY ثبت شد")
                    status, info = check_token(value, env)
                    if status == "ok":
                        print(f"  تایید شد: @{info}")
                        return value, info
            if status == "net":
                print(f"  هشدار: تلگرام در دسترس نیست، توکن بدون تایید ثبت می شود ({info})")
                return value, ""
            print(f"  {BAD} {info}")
        if not ask.interactive:
            raise SystemExit(f"{name} نامعتبر است؛ چیزی نوشته نشد.")
    raise SystemExit(f"{name} سه بار نامعتبر بود؛ چیزی نوشته نشد.")


def resolve_admins(given: str | None, env: EnvFile, ask: Asker, bot_ids: set[int]) -> str:
    current = env.get("ADMIN_IDS")
    for _ in range(3):
        raw = given if given is not None else ask.text("آیدی عددی ادمین (چند تا با کاما؛ از @userinfobot)", current)
        given = None
        raw = raw or current
        try:
            ids = parse_admin_ids(raw)
        except ValueError as e:
            print(f"  {BAD} {e}")
        else:
            if not ids:
                print("  هشدار: ADMIN_IDS خالی است؛ هیچ کس به پنل ادمین و دستورهای ادمین دسترسی ندارد")
                return ""
            if bot_ids & set(ids):
                print(f"  {BAD} این آیدی مال خود ربات است، نه حساب تلگرام تو")
            else:
                return ",".join(str(i) for i in ids)
        if not ask.interactive:
            raise SystemExit("ADMIN_IDS نامعتبر است؛ چیزی نوشته نشد.")
    raise SystemExit("ADMIN_IDS سه بار نامعتبر بود؛ چیزی نوشته نشد.")


# ---------- خواندن از فایل ----------
# کلیدهایی که از فایل --from عینا به .env می روند (بعد از چک ساده)
PLAIN_KEYS = ("WEBHOOK_BASE_URL", "TG_PROXY", "TG_API_BASE", "PANEL_BASE_URL", "PANEL_USERNAME",
              "PANEL_PASSWORD", "PANEL_API_KEY", "PANEL_GROUP_ID", "GAME_CLUB_BOT_USERNAME")


def load_from(a: argparse.Namespace) -> dict[str, str]:
    """فایل setup.env را می خواند؛ خالی ها نادیده گرفته می شوند (یعنی مقدار فعلی بماند)."""
    path = Path(a.from_file)
    if not path.exists():
        raise SystemExit(f"فایل {path} پیدا نشد")
    f = EnvFile(path)
    keys = ("BOT_TOKEN", "GAME_CLUB_BOT_TOKEN", "ADMIN_IDS") + PLAIN_KEYS
    vals = {k: f.get(k).strip() for k in keys if f.get(k).strip()}
    for k in ("WEBHOOK_BASE_URL", "PANEL_BASE_URL"):
        if k in vals:
            vals[k] = vals[k].rstrip("/")
            if not vals[k].startswith(("https://", "http://")):
                raise SystemExit(f"{k} در {path} باید با https:// شروع شود؛ چیزی نوشته نشد")
    for k, v in vals.items():
        try:
            quote(v)
        except ValueError as e:
            raise SystemExit(f"{k}: {e}") from None
    if "GAME_CLUB_BOT_USERNAME" in vals:
        vals["GAME_CLUB_BOT_USERNAME"] = vals["GAME_CLUB_BOT_USERNAME"].lstrip("@")
    a.bot_token = a.bot_token or vals.get("BOT_TOKEN")
    a.gc_token = a.gc_token or vals.get("GAME_CLUB_BOT_TOKEN")
    a.admin_ids = a.admin_ids or vals.get("ADMIN_IDS")
    return vals


# ---------- اجرا ----------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ثبت توکن، سکرت وبهوک و آیدی ادمین در .env")
    p.add_argument("--bot-token", help="توکن ربات عبور (BOT_TOKEN)")
    p.add_argument("--gc-token", help="توکن ربات Game Club (GAME_CLUB_BOT_TOKEN)")
    p.add_argument("--admin-ids", help="آیدی عددی ادمین ها، با کاما")
    p.add_argument("--env", default=str(ENV_PATH), help="مسیر فایل .env (پیش فرض: کنار همین اسکریپت)")
    p.add_argument("--panel", action="store_true", help="اطلاعات پنل PasarGuard را دوباره بپرس")
    p.add_argument("--from", dest="from_file", metavar="FILE",
                   help="مقادیر را از یک فایل بخوان (برای وقتی ترمینال تایپ نمی پذیرد)؛ بعد از ثبت پاک می شود")
    p.add_argument("--rotate", action="store_true", help="همه سکرت ها و مسیر وبهوک را از نو بساز")
    p.add_argument("--no-check", action="store_true", help="توکن را با getMe تایید نکن")
    p.add_argument("--yes", "-y", action="store_true", help="بدون پرسش؛ فقط از فلگ ها و مقادیر موجود")
    p.add_argument("--dry-run", action="store_true", help="فقط تغییرات را نشان بده، چیزی ننویس")
    p.add_argument("--no-hints", action="store_true", help=argparse.SUPPRESS)  # از setup_all.sh
    p.add_argument("--apply", action="store_true", help="بعد از نوشتن: ری استارت و ثبت وبهوک هر دو ربات")
    a = p.parse_args(argv)

    env_path = Path(a.env).resolve()
    src = load_from(a) if a.from_file else None
    interactive = not a.yes and not src and sys.stdin.isatty()
    ask = Asker(interactive)

    created = False
    if not env_path.exists():
        if not EXAMPLE_PATH.exists():
            raise SystemExit(f"{env_path} و .env.example هیچ کدام پیدا نشد")
        created = True
    env = EnvFile(env_path if not created else EXAMPLE_PATH)
    env.path = env_path
    before = env.text()

    print(f"\nفایل تنظیمات: {env_path}" + ("  (از .env.example ساخته می شود)" if created else ""))
    if interactive:
        print("توکن و پسورد هنگام تایپ یا paste نمایش داده نمی شوند؛ paste کن (کلیک راست یا Ctrl+Shift+V) و Enter بزن.")
        print("Enter خالی یعنی مقدار فعلی بماند. اگر ترمینال چیزی نمی پذیرد: setup.env.example را ببین.\n")

    verify = not a.no_check
    rows: list[tuple[str, str, str]] = []

    def put(key: str, value: str, generated: bool = False) -> None:
        if key in ("ADMIN_IDS", "GAME_CLUB_BOT_USERNAME", "WEBHOOK_BASE_URL", "PANEL_BASE_URL", "PANEL_USERNAME",
                   "PANEL_GROUP_ID", "TG_API_BASE"):
            shown = value or "-"
        elif key == "WEBHOOK_PATH":
            shown = "/tg/…" + value[-3:]
        else:
            shown = mask(value)
        if value == env.get(key):
            rows.append((KEEP, key, shown))
            return
        env.set(key, value)
        rows.append((NEW if generated else OK, key, shown))

    if src:  # شبکه و آدرس ها پیش از تایید توکن، تا getMe از همان پروکسی برود
        print(f"مقادیر از فایل {a.from_file} خوانده شد: {', '.join(sorted(src)) or 'هیچ'}\n")
        for key in PLAIN_KEYS:
            if src.get(key):
                put(key, src[key])

    # ۱. ربات عبور
    print("— ربات عبور")
    token, _ = resolve_token("BOT_TOKEN", "ربات عبور", a.bot_token, env, ask, verify, required=True)
    put("BOT_TOKEN", token)

    # ۲. ربات Game Club
    print("— ربات Game Club (یک ربات جدا در BotFather؛ خالی = Game Club خاموش)")
    gc_token, gc_user = resolve_token("GAME_CLUB_BOT_TOKEN", "ربات Game Club", a.gc_token, env, ask,
                                      verify, required=False, forbid=token)
    put("GAME_CLUB_BOT_TOKEN", gc_token)
    if gc_user:
        put("GAME_CLUB_BOT_USERNAME", gc_user)
    elif gc_token and not env.get("GAME_CLUB_BOT_USERNAME"):
        user = ask.text("یوزرنیم ربات Game Club (بدون @)", "").lstrip("@")
        if user and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", user):
            print(f"  {BAD} یوزرنیم معتبر نیست؛ بعدا در .env بنویس")
        elif user:
            put("GAME_CLUB_BOT_USERNAME", user)

    # ۳. ادمین
    print("— ادمین")
    bot_ids = {int(t.split(":", 1)[0]) for t in (token, gc_token) if t}
    put("ADMIN_IDS", resolve_admins(a.admin_ids, env, ask, bot_ids))

    # ۴. آدرس اپ و پنل: فقط اگر خالی باشند (یا --panel)
    base = env.get("WEBHOOK_BASE_URL")
    if not base.startswith("https://"):
        print("— آدرس اپ")
        url = ask.text("آدرس اپ روی هاست (مثل https://dezhcode.pyho.ir/obour)", base).rstrip("/")
        if url.startswith("https://"):
            put("WEBHOOK_BASE_URL", url)
    has_auth = env.get("PANEL_API_KEY") or (env.get("PANEL_USERNAME") and env.get("PANEL_PASSWORD"))
    if ask.interactive and (a.panel or not has_auth):
        print("— پنل PasarGuard (Enter = مقدار فعلی)")
        url = ask.text("آدرس پنل (بدون /dashboard)", env.get("PANEL_BASE_URL")).rstrip("/")
        if url:
            put("PANEL_BASE_URL", url)
        user = ask.text("یوزرنیم پنل", env.get("PANEL_USERNAME"))
        if user:
            put("PANEL_USERNAME", user)
        password = ask.secret("پسورد پنل", env.get("PANEL_PASSWORD"))
        if password:
            try:
                put("PANEL_PASSWORD", password)
            except ValueError as e:
                print(f"  {BAD} {e}")

    # ۵. سکرت ها: فقط اگر خالی، نامعتبر یا --rotate
    taken: set[str] = set()
    for key in ("WEBHOOK_SECRET", "ADMIN_KEY", "GAME_CLUB_WEBHOOK_SECRET"):
        cur = env.get(key)
        if a.rotate or not SECRET_RE.match(cur) or cur in taken:
            if cur and not a.rotate:
                why = "تکراری" if cur in taken else "کوتاه یا با حرف غیرمجاز"
                print(f"  {key} {why} بود؛ از نو ساخته شد")
            cur = new_secret()
            put(key, cur, generated=True)
        else:
            put(key, cur)
        taken.add(cur)
    wpath = env.get("WEBHOOK_PATH")
    if a.rotate or is_placeholder_path(wpath):
        put("WEBHOOK_PATH", "/tg/" + new_secret(16), generated=True)
    else:
        put("WEBHOOK_PATH", wpath)

    changed = env.text() != before or created
    print()
    for tag, key, shown in rows:
        print(f"{tag:<15} {key:<26} {shown}")
    if env.added:
        print(f"\nکلیدهای تازه انتهای فایل اضافه شدند: {', '.join(env.added)}")
    if env.get("GAME_CLUB_BOT_TOKEN") and not env.get("GAME_CLUB_BOT_USERNAME"):
        print("\nهشدار: GAME_CLUB_BOT_USERNAME خالی است؛ کارت Game Club در مینی اپ عبور نشان داده نمی شود.")
    if not env.get("WEBHOOK_BASE_URL").startswith("https://"):
        print("\nهشدار: WEBHOOK_BASE_URL با https:// شروع نمی شود؛ وبهوک و مینی اپ کار نمی کنند.")

    if a.dry_run:
        print("\n(--dry-run) چیزی نوشته نشد.")
        return 0
    if not changed:
        print("\nهمه چیز از قبل درست بود؛ فایل دست نخورد.")
    else:
        if not created:
            bak = env_path.with_name(env_path.name + ".bak")
            shutil.copy2(env_path, bak)
            os.chmod(bak, 0o600)
        env.save()
        print(f"\nذخیره شد: {env_path} (دسترسی 600)" + ("" if created else f"؛ نسخه قبلی: {env_path.name}.bak"))
    if src:  # توکن و پسورد نباید در فایل دوم روی هاست بمانند
        Path(a.from_file).unlink(missing_ok=True)
        print(f"فایل {a.from_file} پاک شد (مقادیرش حالا در .env است).")

    rotated = any(tag == NEW and k in ("WEBHOOK_SECRET", "WEBHOOK_PATH", "GAME_CLUB_WEBHOOK_SECRET")
                  for tag, k, _ in rows)
    if a.no_hints:
        return 0
    do_apply = a.apply or (changed and ask.interactive and ask.yes("الان ری استارت کنم و وبهوک هر دو ربات را ثبت کنم؟", True))
    if do_apply:
        return apply(env_path, gc_enabled=bool(gc_token))

    print("\nقدم بعد:")
    print("  ۱. ری استارت:            ./restart.sh")
    print("  ۲. وبهوک ربات عبور:      python manage_webhook.py set")
    if gc_token:
        print("  ۳. وبهوک Game Club:      python manage_webhook.py gc-set")
    if rotated and not created:
        print("  (سکرت یا مسیر وبهوک عوض شد؛ تا قدم ۲ و ۳ را نزنی ربات ها آپدیت نمی گیرند)")
    print("  یا همه با هم:            python setup_env.py --apply")
    return 0


def apply(env_path: Path, gc_enabled: bool) -> int:
    """ری استارت Passenger و ثبت وبهوک ها، هر کدام در پروسه تازه تا .env جدید خوانده شود."""
    if env_path != ENV_PATH:
        print("\n--apply فقط برای .env کنار پروژه کار می کند.")
        return 1
    (BASE_DIR / "tmp").mkdir(exist_ok=True)
    (BASE_DIR / "tmp" / "restart.txt").touch()
    print("\nری استارت: tmp/restart.txt")
    code = 0
    for action in ["set"] + (["gc-set"] if gc_enabled else []):
        print(f"\n$ python manage_webhook.py {action}")
        r = subprocess.run([sys.executable, str(BASE_DIR / "manage_webhook.py"), action], cwd=BASE_DIR, check=False)
        code = code or r.returncode
    if code:
        print("\nثبت وبهوک کامل نشد. شبکه تلگرام (TG_PROXY / TG_API_BASE) را چک کن و دوباره بزن:"
              "  python setup_env.py --apply")
    return code


if __name__ == "__main__":
    sys.exit(main())
