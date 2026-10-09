#!/usr/bin/env bash
# ساخت و تنظیم کلید دستیار هوش مصنوعی (AI_API_KEY) با یک دستور:
#
#   bash ai_key.sh
#
# کارها به ترتیب:
#   ۱. پوشه وب سرویس هوش مصنوعی (مخزن Web-Service) را روی همین هاست پیدا می کند
#   ۲. یک کلید تصادفی تازه می سازد
#   ۳. کلید را به API_KEY وب سرویس اضافه می کند (کلید قبلی عبور جایش عوض می شود،
#      کلیدهای دیگر دست نمی خورند) و در AI_API_KEY فایل .env عبور می گذارد
#   ۴. وب سرویس و ربات عبور را ری استارت می کند
#   ۵. کلید را روی وب سرویس امتحان می کند و check_ai.py را اجرا می کند
#
# کلید هیچ جا کامل چاپ نمی شود؛ فقط در دو فایل .env می ماند.
#
# گزینه ها:
#   --service DIR   پوشه وب سرویس (اگر خودکار پیدا نشد). یا متغیر AI_SERVICE_DIR
#   --url URL       آدرس وب سرویس برای تست (پیش فرض AI_BASE_URL در .env یا https://dezhcode.pyho.ir)
#   --keep-old      کلید قبلی عبور را هم روی وب سرویس معتبر نگه دار
#   --no-restart    ری استارت نکن
#   --no-test       تست نکن
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${OBOUR_VENV:-/home/wmkmbrcs/virtualenv/obour/3.11}"
APP_URL="${OBOUR_URL:-https://dezhcode.pyho.ir/obour}"
SERVICE_DIR="${AI_SERVICE_DIR:-}"
URL=""
KEEP_OLD=0
RESTART=1
TEST=1

while [ $# -gt 0 ]; do
  case "$1" in
    --service) SERVICE_DIR="${2:-}"; shift 2 ;;
    --url) URL="${2:-}"; shift 2 ;;
    --keep-old) KEEP_OLD=1; shift ;;
    --no-restart) RESTART=0; shift ;;
    --no-test) TEST=0; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "گزینه ناشناخته: $1 (راهنما: bash ai_key.sh --help)" >&2; exit 2 ;;
  esac
done

say() { printf '\n== %s\n' "$*"; }
die() { printf '\nخطا: %s\n' "$*" >&2; exit 1; }

PY="python3"
if [ -x "$VENV/bin/python" ]; then PY="$VENV/bin/python"; fi
command -v "$PY" >/dev/null 2>&1 || die "python3 پیدا نشد"

# ---------- ۱. پیدا کردن وب سرویس ----------
say "پیدا کردن وب سرویس هوش مصنوعی"
is_service() { [ -f "$1/app.py" ] && [ -f "$1/copilot_client.py" ] && grep -q "_api_keys" "$1/app.py" 2>/dev/null; }
if [ -z "$SERVICE_DIR" ]; then
  while IFS= read -r f; do
    d="$(dirname "$f")"
    [ "$d" = "$APP_DIR" ] && continue
    if is_service "$d"; then SERVICE_DIR="$d"; break; fi
  done < <(find "$HOME" -maxdepth 3 -name copilot_client.py -not -path "*/virtualenv/*" -not -path "*/.git/*" 2>/dev/null | sort)
fi
[ -n "$SERVICE_DIR" ] || die "پوشه وب سرویس پیدا نشد. مسیرش را بده: bash ai_key.sh --service ~/پوشه_وب_سرویس"
SERVICE_DIR="$(cd "$SERVICE_DIR" && pwd)"
is_service "$SERVICE_DIR" || die "$SERVICE_DIR وب سرویس هوش مصنوعی (Web-Service) نیست"
echo "وب سرویس: $SERVICE_DIR"
echo "ربات عبور: $APP_DIR"

if [ -z "$URL" ]; then
  URL="$(grep -E '^AI_BASE_URL=' "$APP_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"'"'"' \r' || true)"
  URL="${URL:-https://dezhcode.pyho.ir}"
fi
URL="${URL%/}"

# ---------- ۲ و ۳. ساخت کلید و نوشتن در دو .env ----------
say "ساخت کلید تازه و نوشتن در فایل های .env"
# کلید فقط از راه متغیر محیطی به پایتون می رسد (در خط فرمان دیده نمی شود)
NEW_KEY="$("$PY" -c 'import secrets; print("obour_" + secrets.token_urlsafe(32))')"
export NEW_KEY KEEP_OLD
"$PY" - "$SERVICE_DIR/.env" "$APP_DIR/.env" <<'PYEOF'
import os
import sys
import tempfile

service_env, obour_env = sys.argv[1], sys.argv[2]
new = os.environ["NEW_KEY"]
keep_old = os.environ.get("KEEP_OLD") == "1"


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()
    except FileNotFoundError:
        return []


def value(lines, name):
    for ln in lines:
        s = ln.strip()
        if s.startswith("export "):
            s = s[7:].lstrip()
        if s.startswith(name + "="):
            return s.split("=", 1)[1].strip().strip("\"'")
    return None


def put(path, name, val):
    """name=val را جایگزین اولین خط همان نام می کند، تکراری ها را برمی دارد و بقیه خط ها را دست نمی زند."""
    lines, out, done = read(path), [], False
    for ln in lines:
        s = ln.strip()
        if s.startswith("export "):
            s = s[7:].lstrip()
        if s.startswith(name + "="):
            if not done:
                out.append(f"{name}={val}")
                done = True
            continue
        out.append(ln)
    if not done:
        out.append(f"{name}={val}")
    d = os.path.dirname(os.path.abspath(path))
    mode = os.stat(path).st_mode & 0o777 if os.path.exists(path) else 0o600
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".env.tmp.")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


old = value(read(obour_env), "AI_API_KEY") or ""
keys = [k.strip() for k in (value(read(service_env), "API_KEY") or "").split(",") if k.strip()]
if old and old in keys and not keep_old:
    keys = [new if k == old else k for k in keys]      # کلید قبلی عبور با کلید تازه عوض می شود
    print("کلید قبلی عبور روی وب سرویس با کلید تازه جایگزین شد")
else:
    keys.append(new)
keys = [k for k in keys if k != "change-me-to-a-long-random-string"]
if new not in keys:
    keys.append(new)
put(service_env, "API_KEY", ",".join(dict.fromkeys(keys)))
put(obour_env, "AI_API_KEY", new)
print(f"وب سرویس: {len(keys)} کلید معتبر")
print(f"عبور: AI_API_KEY = {new[:9]}…  ({len(new)} کاراکتر)")
PYEOF

# ---------- ۴. ری استارت ----------
if [ "$RESTART" = 1 ]; then
  say "ری استارت وب سرویس و ربات"
  mkdir -p "$SERVICE_DIR/tmp" "$APP_DIR/tmp"
  touch "$SERVICE_DIR/tmp/restart.txt" "$APP_DIR/tmp/restart.txt"
  echo "علامت ری استارت برای هر دو اپ گذاشته شد (tmp/restart.txt)"
  # بیدار کردن ربات تا با .env تازه بالا بیاید
  curl -s -m 25 -o /dev/null "$APP_URL/health" 2>/dev/null || true
fi

# ---------- ۵. تست ----------
if [ "$TEST" = 1 ]; then
  say "تست کلید روی $URL"
  # درخواست خالی: اگر کلید پذیرفته شود جواب 400 (پیام لازم است) می آید، اگر نه 401؛ هزینه هوش مصنوعی ندارد
  code=000
  for i in 1 2 3 4 5 6; do
    code="$(curl -s -m 20 -o /dev/null -w '%{http_code}' -X POST "$URL/api/chat" \
      -H @<(printf 'Authorization: Bearer %s\nContent-Type: application/json\n' "$NEW_KEY") \
      --data '{}' 2>/dev/null || echo 000)"
    case "$code" in 400|200) break ;; esac
    sleep 4
  done
  case "$code" in
    400|200) echo "OK: وب سرویس کلید تازه را پذیرفت" ;;
    401) echo "FAIL: وب سرویس کلید را نپذیرفت (401)."
         echo "  اگر در cPanel ← Setup Python App ← اپ وب سرویس متغیر API_KEY تعریف شده، آن بر .env مقدم است:"
         echo "  آن متغیر را پاک کن (یا کلید را آنجا هم بگذار) و اپ را Restart کن، بعد دوباره: bash ai_key.sh --no-restart" ;;
    503) echo "FAIL: وب سرویس هنوز کلیدی ندارد (503). چند ثانیه بعد دوباره تست کن: bash ai_key.sh --keep-old" ;;
    *) echo "FAIL: وب سرویس جواب نداد (کد $code). آدرس را بررسی کن: --url https://..." ;;
  esac
  if [ -f "$APP_DIR/check_ai.py" ]; then
    say "تست کامل از طرف عبور (check_ai.py)"
    (cd "$APP_DIR" && "$PY" check_ai.py) || echo "check_ai.py خطا داد؛ خروجی بالا را ببین"
  fi
  echo
  echo "یادآوری: اگر AI_API_KEY در cPanel ← Setup Python App ← اپ عبور هم تعریف شده، آن بر .env مقدم است؛ پاکش کن."
fi

unset NEW_KEY
say "تمام شد"
