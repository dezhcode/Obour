#!/usr/bin/env bash
# راه اندازی کامل عبور و Game Club روی هاست با یک بار اجرا:
#
#   bash setup_all.sh                 شاخه فعلی (بار اول: main)
#   bash setup_all.sh <branch>        یک شاخه دیگر
#   bash setup_all.sh -y              بدون پرسش (فقط مقادیر موجود .env)
#   bash setup_all.sh --no-update     بدون گرفتن کد تازه از گیت هاب
#   bash setup_all.sh --panel         اطلاعات پنل را دوباره بپرس
#   bash setup_all.sh --once          برای Cron Jobs: فقط یک بار، یا هر بار که setup.env تازه باشد
#
# بدون تایپ در ترمینال: مقادیر را در فایل setup.env کنار اپ بنویس (نمونه:
# setup.env.example، با File Manager سی پنل). اسکریپت آن را می خواند، در .env ثبت
# می کند و پاکش می کند. گزارش هر اجرا در logs/setup_all.log می ماند.
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
  local BRANCH="" YES="" UPDATE=1 PANEL="" REEXEC="" ONCE=""
  local arg
  for arg in "$@"; do
    case "$arg" in
      -y|--yes) YES="--yes" ;;
      --no-update) UPDATE=0 ;;
      --panel) PANEL="--panel" ;;
      --reexec) REEXEC=1 ;;
      --once) ONCE="--once" ;;
      -h|--help) sed -n '2,27p' "$0"; return 0 ;;
      -*) echo "گزینه ناشناخته: $arg"; return 2 ;;
      *) BRANCH="$arg" ;;
    esac
  done

  step() { printf '\n\033[1;32m== %s\033[0m\n' "$*"; }
  warn() { printf '\033[1;33m!! %s\033[0m\n' "$*"; }
  fail() { printf '\033[1;31mXX %s\033[0m\n' "$*"; exit 1; }

  cd "$APP_DIR" || fail "پوشه اپ پیدا نشد: $APP_DIR"
  mkdir -p logs tmp

  # کران هر دقیقه اجرا می کند: کار فقط وقتی هست که هنوز اجرا نشده یا setup.env تازه آمده
  if [ -n "$ONCE" ] && [ -z "$REEXEC" ] && [ -f tmp/setup_all.done ] && [ ! -f setup.env ]; then
    return 0
  fi
  # setup.env خراب: تا وقتی عوضش نکرده ای، کران دوباره امتحانش نمی کند
  if [ -n "$ONCE" ] && [ -f setup.env ] && [ -f tmp/setup_all.failed ] \
     && [ "$(sha1sum < setup.env)" = "$(cat tmp/setup_all.failed)" ]; then
    return 0
  fi
  # جلوگیری از دو اجرای هم زمان (قفل کهنه تر از ۳۰ دقیقه رها می شود)
  if [ -z "$REEXEC" ]; then
    find tmp -maxdepth 1 -name setup_all.lock -mmin +30 -exec rm -rf {} + 2>/dev/null
    mkdir tmp/setup_all.lock 2>/dev/null || { echo "یک اجرای دیگر در جریان است."; return 0; }
  fi
  # shellcheck disable=SC2064  # مسیر همین حالا باز می شود؛ بعد از main متغیر محلی نیست
  trap "rm -rf '$APP_DIR/tmp/setup_all.lock'" EXIT
  [ -z "$REEXEC" ] && exec > >(tee -a logs/setup_all.log) 2>&1
  echo; echo "######## $(date '+%Y-%m-%d %H:%M:%S') setup_all.sh $*"

  # بدون ترمینال تعاملی (کران، Execute script) پرسشی در کار نیست
  [ -t 0 ] || YES="--yes"
  local FROM=""
  if [ -f setup.env ]; then
    FROM="--from setup.env"
    YES="--yes"
  fi

  # ۱. venv
  step "۱. محیط پایتون و پوشه اپ"
  [ -f "$VENV/bin/activate" ] || fail "venv پیدا نشد: $VENV"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
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
      exec bash setup_all.sh --reexec --no-update $YES $PANEL $ONCE
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
  [ -n "$FROM" ] && echo "مقادیر از setup.env خوانده می شود."
  if ! python setup_env.py --no-hints $YES $PANEL $FROM; then
    [ -f setup.env ] && sha1sum < setup.env > tmp/setup_all.failed
    fail "تنظیمات کامل نشد؛ چیزی ثبت نشد. خطای بالا را درست کن (setup.env سر جایش ماند)"
  fi
  rm -f tmp/setup_all.failed
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

  touch tmp/setup_all.done
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
