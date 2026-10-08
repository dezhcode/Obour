#!/usr/bin/env bash
# راه اندازی کامل عبور و Game Club روی هاست با یک بار اجرا:
#
#   bash setup_all.sh                 شاخه فعلی (بار اول: main)
#   bash setup_all.sh <branch>        یک شاخه دیگر
#   bash setup_all.sh -y              بدون پرسش (فقط مقادیر موجود .env)
#   bash setup_all.sh --no-update     بدون گرفتن کد تازه از گیت هاب
#   bash setup_all.sh --panel         اطلاعات پنل را دوباره بپرس
#
# کارها به ترتیب:
#   ۱. فعال کردن venv و رفتن به پوشه اپ
#   ۲. گرفتن آخرین نسخه کد (update.sh) و نصب کتابخانه های جاافتاده
#   ۳. ساخت پوشه های data، logs و tmp با دسترسی درست
#   ۴. setup_env.py: توکن دو ربات، آیدی ادمین، آدرس و پنل، سکرت های وبهوک
#   ۵. درج پلن ها، فقط اگر دیتابیس هیچ پلنی ندارد (قیمت های تو دست نمی خورند)
#   ۶. ری استارت پسنجر و بیدار کردن اپ
#   ۷. ثبت وبهوک، دستورها و دکمه منوی ربات عبور و ربات Game Club
#   ۸. check_setup.py: گزارش نهایی سلامت
#
# هر بار اجرا امن است: مقادیر درست .env، دیتابیس ها و پلن ها دست نمی خورند.
# مسیرها را می شود با OBOUR_DIR، OBOUR_VENV و OBOUR_URL عوض کرد.

main() {
  set -uo pipefail

  local APP_DIR="${OBOUR_DIR:-/home/wmkmbrcs/obour}"
  local VENV="${OBOUR_VENV:-/home/wmkmbrcs/virtualenv/obour/3.11}"
  local BRANCH="" YES="" UPDATE=1 PANEL="" REEXEC=""
  local arg
  for arg in "$@"; do
    case "$arg" in
      -y|--yes) YES="--yes" ;;
      --no-update) UPDATE=0 ;;
      --panel) PANEL="--panel" ;;
      --reexec) REEXEC=1 ;;
      -h|--help) sed -n '2,21p' "$0"; return 0 ;;
      -*) echo "گزینه ناشناخته: $arg"; return 2 ;;
      *) BRANCH="$arg" ;;
    esac
  done

  step() { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
  warn() { printf '\033[1;33m!! %s\033[0m\n' "$*"; }
  fail() { printf '\033[1;31mXX %s\033[0m\n' "$*"; exit 1; }

  # ۱. venv و پوشه
  step "۱. محیط پایتون و پوشه اپ"
  [ -f "$VENV/bin/activate" ] || fail "venv پیدا نشد: $VENV"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  cd "$APP_DIR" || fail "پوشه اپ پیدا نشد: $APP_DIR"
  echo "پایتون: $(python --version 2>&1)  |  پوشه: $APP_DIR"

  # ۲. کد تازه
  if [ "$UPDATE" = 1 ] && [ -z "$REEXEC" ]; then
    if [ -z "$BRANCH" ]; then
      BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
      { [ -z "$BRANCH" ] || [ "$BRANCH" = HEAD ]; } && BRANCH=main
    fi
    step "۲. گرفتن آخرین نسخه شاخه $BRANCH"
    local before after
    before="$(sha1sum setup_all.sh 2>/dev/null || true)"
    bash update.sh "$BRANCH" || fail "به روزرسانی کد انجام نشد (اتصال به گیت هاب را چک کن)"
    after="$(sha1sum setup_all.sh 2>/dev/null || true)"
    if [ "$before" != "$after" ] && [ -f setup_all.sh ]; then
      echo "نسخه تازه همین اسکریپت آمد؛ از نو اجرا می شود."
      exec bash setup_all.sh --reexec --no-update $YES $PANEL
    fi
  else
    step "۲. گرفتن کد تازه: رد شد"
  fi
  if ! python -c "import aiogram, aiosqlite, dotenv" >/dev/null 2>&1; then
    echo "نصب کتابخانه ها از requirements.txt"
    pip install -q -r requirements.txt || fail "نصب کتابخانه ها انجام نشد"
  fi

  # ۳. پوشه ها
  step "۳. پوشه های data، logs و tmp"
  mkdir -p data logs tmp
  chmod 700 data logs

  # ۴. تنظیمات
  step "۴. تنظیمات .env"
  python setup_env.py --no-hints $YES $PANEL || fail "تنظیمات کامل نشد؛ چیزی ثبت نشد"
  chmod 600 .env

  # ۵. پلن ها
  step "۵. پلن ها"
  local plans
  plans="$(python - <<'PY' 2>/dev/null
import asyncio
from app.config import config
from app.db import Database

async def count():
    db = Database(config.db_path)
    await db.connect()
    try:
        print(len(await db.all_plans()))
    finally:
        await db.close()

asyncio.run(count())
PY
)"
  if [ "${plans:-0}" = 0 ]; then
    python seed_plans.py || warn "درج پلن ها انجام نشد"
  else
    echo "$plans پلن در دیتابیس هست؛ دست نخورد."
  fi

  # ۶. ری استارت
  step "۶. ری استارت"
  touch tmp/restart.txt
  local url code
  url="$(python -c "from app.config import config; print(config.webhook_base_url)" 2>/dev/null)"
  url="${OBOUR_URL:-$url}"
  if [ -n "$url" ] && command -v curl >/dev/null 2>&1; then
    code="$(curl -s -o /dev/null -w '%{http_code}' -m 60 "$url/health" || true)"
    echo "health: HTTP $code"
    [ "$code" = 200 ] || warn "اپ جواب درست نداد؛ لاگ را ببین: tail -50 logs/obour.log"
  fi

  # ۷. وبهوک ها
  step "۷. وبهوک ربات عبور"
  local hooks_ok=1
  python manage_webhook.py set || { hooks_ok=0; warn "وبهوک ربات عبور ثبت نشد"; }
  if python -c "from game_club.config import gc; raise SystemExit(0 if gc.token else 1)" 2>/dev/null; then
    step "۷. وبهوک ربات Game Club"
    python manage_webhook.py gc-set || { hooks_ok=0; warn "وبهوک Game Club ثبت نشد"; }
  else
    warn "GAME_CLUB_BOT_TOKEN خالی است؛ Game Club خاموش می ماند"
  fi

  # ۸. گزارش
  step "۸. بررسی نهایی"
  python check_setup.py || true

  echo
  if [ "$hooks_ok" = 1 ]; then
    echo "تمام. در تلگرام به هر دو ربات /start بده."
  else
    warn "وبهوک ثبت نشد. اگر هاست به تلگرام دسترسی ندارد TG_PROXY را در .env بگذار و دوباره بزن: bash setup_all.sh --no-update"
    return 1
  fi
}

# کل اسکریپت داخل main است تا اگر update.sh همین فایل را عوض کرد، اجرای فعلی خراب نشود.
main "$@"
