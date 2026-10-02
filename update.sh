#!/usr/bin/env bash
# به روزرسانی ربات روی هاست با یک دستور:
#
#   bash update.sh            آخرین نسخه شاخه main
#   bash update.sh <branch>   آخرین نسخه یک شاخه دیگر
#
# کارها به ترتیب:
#   ۱. اگر پوشه هنوز گیت نیست، به مخزن وصلش می کند (فقط بار اول)
#   ۲. آخرین نسخه را از گیت هاب می گیرد و فایل ها را با آن یکی می کند
#   ۳. اگر requirements.txt عوض شده بود، کتابخانه ها را نصب می کند
#   ۴. اپ را ری استارت می کند (tmp/restart.txt) و یک بار بیدارش می کند
#
# فایل های شخصی دست نمی خورند: .env، دیتابیس ها (*.db)، data/، logs/ و
# tmp/ در .gitignore هستند و گیت به آن ها کاری ندارد. ولی هر تغییری که
# مستقیم روی هاست در فایل های کد داده باشی، با نسخه گیت هاب جایگزین می شود.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
BRANCH="${1:-main}"
REPO_URL="${OBOUR_REPO:-https://github.com/dezhcode/Obour.git}"
VENV="${OBOUR_VENV:-/home/wmkmbrcs/virtualenv/obour/3.11}"
APP_URL="${OBOUR_URL:-https://dezhcode.pyho.ir/obour}"

cd "$APP_DIR"
if [ -f "$VENV/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
fi

say() { printf '\n== %s\n' "$*"; }

# ۱. بار اول: پوشه فعلی را به مخزن وصل کن
if [ ! -d .git ]; then
  say "اولین اجرا: وصل کردن پوشه به $REPO_URL"
  git init -q
  git remote add origin "$REPO_URL"
fi

# ۲. گرفتن آخرین نسخه
say "گرفتن آخرین نسخه شاخه $BRANCH"
OLD="$(git rev-parse -q --verify HEAD 2>/dev/null || echo none)"
OLD_REQ="$(git show HEAD:requirements.txt 2>/dev/null | sha1sum || true)"
git fetch --depth 50 origin "$BRANCH"
# reset --hard فایل های کد را با نسخه گیت هاب یکی می کند (حتی بار اول که
# فایل ها هنوز در گیت ثبت نیستند)؛ بعد شاخه محلی روی همان نسخه ساخته می شود.
git reset -q --hard "origin/$BRANCH"
git checkout -q -B "$BRANCH"
NEW="$(git rev-parse HEAD)"
NEW_REQ="$(sha1sum < requirements.txt)"

if [ "$OLD" = "$NEW" ]; then
  echo "کد از قبل به روز بود ($(git log -1 --format='%h %s'))"
else
  echo "به روز شد: ${OLD:0:7} -> ${NEW:0:7}"
  if [ "$OLD" != none ]; then
    git log --format='  - %h %s' "$OLD..$NEW" 2>/dev/null | head -20 || true
  fi
fi

# ۳. کتابخانه ها، فقط وقتی لازم است
if [ "$OLD" = none ] || [ "$OLD_REQ" != "$NEW_REQ" ]; then
  say "نصب کتابخانه ها (requirements.txt عوض شده)"
  pip install -q -r requirements.txt
fi

# ۴. ری استارت پسنجر و بیدار کردن اپ
say "ری استارت"
mkdir -p tmp
touch tmp/restart.txt
if command -v curl >/dev/null 2>&1; then
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 30 "$APP_URL/health" || true)"
  echo "health: HTTP $code"
fi
echo "تمام."
