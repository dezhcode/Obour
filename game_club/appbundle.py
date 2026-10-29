"""بستهٔ صفحه ها و بازی ها برای برنامهٔ اندروید (Capacitor) و آپدیت خودکارش.

همان فایل های webapp/ است با سه تغییر:
  - اسکریپت SDK تلگرام برداشته می شود (بیرون از تلگرام لازم نیست و بدون اینترنت صفحه را نگه می دارد)؛
  - به جایش app-config.js (آدرس سرور و نسخهٔ همین بسته) و static/app.js (مهمان، نشست، آپدیت) می آید؛
  - پنل مدیریت و sw.js داخل برنامه نمی روند.

یک منبع برای دو کار:
  - ساختن www برنامه پیش از build اندروید:  python -m game_club.appbundle --out game_club/android-app/www
  - آپدیت خودکار: سرور همین بسته را زیپ می کند (GET /gc/app/manifest و /gc/app/bundle/<v>.zip)؛ برنامه
    نسخه را می پرسد، بستهٔ تازه را دانلود و نگه می دارد و دفعهٔ بعد که باز شد از آن استفاده می کند.

MIN_NATIVE: اگر صفحه ها به چیزی از خود برنامه (پلاگین تازه) نیاز پیدا کردند که نسخهٔ نصب شده ندارد، این
عدد را برابر versionCode همان build اندروید کن؛ برنامهٔ قدیمی تر بسته را نمی گیرد و کاربر را به آپدیت از
مایکت می فرستد.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import threading
import zipfile
from dataclasses import dataclass

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp")
MIN_NATIVE = 1
SKIP = {"admin.html", "sw.js"}
_TG_SDK = re.compile(r'<script src="https://telegram\.org/js/telegram-web-app\.js[^"]*"></script>')
_HEAD_APP = '<script src="app-config.js"></script>\n<script src="static/app.js"></script>'


@dataclass(frozen=True)
class Bundle:
    version: str
    files: dict           # مسیر -> بایت ها (همه، با app-config.js)
    zip: bytes
    sha256: str


def _walk() -> list[tuple[str, str]]:
    out = []
    for root, dirs, files in os.walk(WEB_DIR):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for f in sorted(files):
            if f.startswith("."):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, WEB_DIR).replace(os.sep, "/")
            if rel not in SKIP:
                out.append((rel, full))
    return out


def _transform(rel: str, data: bytes) -> bytes:
    if not rel.endswith(".html"):
        return data
    html = data.decode("utf-8")
    html, n = _TG_SDK.subn(_HEAD_APP, html, count=1)
    if not n:   # صفحه ای که SDK تلگرام ندارد: پیش از اولین اسکریپت
        html = html.replace("<script", _HEAD_APP + "\n<script", 1)
    return html.encode("utf-8")


def build(base: str) -> Bundle:
    """بستهٔ کامل. base آدرس سرور Game Club با / آخر، مثلا https://dezhcode.pyho.ir/obour/gc/"""
    files = {}
    for rel, full in _walk():
        with open(full, "rb") as fh:
            files[rel] = _transform(rel, fh.read())
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode() + b"\0" + hashlib.sha256(files[rel]).digest())
    h.update(base.encode())
    version = h.hexdigest()[:16]
    cfg = {"base": base, "bundle": version, "min_native": MIN_NATIVE}
    files["app-config.js"] = ("window.GC_APP = " + json.dumps(cfg) + ";\n").encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in sorted(files):
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, files[rel])
    raw = buf.getvalue()
    return Bundle(version, files, raw, hashlib.sha256(raw).hexdigest())


_lock = threading.Lock()
_cache: dict = {}


def _stamp() -> tuple:
    return tuple((rel, os.path.getmtime(full), os.path.getsize(full)) for rel, full in _walk())


def current() -> Bundle:
    """بستهٔ فعلی سرور (تا وقتی فایلی عوض نشده از حافظه)."""
    from .config import gc

    base = gc.webapp_url
    key = (base, _stamp())
    with _lock:
        if _cache.get("key") != key:
            _cache["key"], _cache["bundle"] = key, build(base)
        return _cache["bundle"]


def manifest() -> dict:
    from .config import gc

    # بدون آدرس سرور (WEBHOOK_BASE_URL) بسته به سرور وصل نمی شود؛ چیزی برای آپدیت اعلام نمی شود
    if not gc.webapp_url:
        return {"version": None, "min_native": MIN_NATIVE}
    b = current()
    return {"version": b.version, "url": f"app/bundle/{b.version}.zip", "sha256": b.sha256,
            "size": len(b.zip), "min_native": MIN_NATIVE}


def main() -> None:
    ap = argparse.ArgumentParser(description="ساختن www برنامهٔ اندروید Game Club")
    ap.add_argument("--out", required=True, help="پوشهٔ خروجی (مثلا game_club/android-app/www)")
    ap.add_argument("--base", default=os.getenv("GC_APP_BASE", "https://dezhcode.pyho.ir/obour/gc/"),
                    help="آدرس سرور Game Club با / آخر")
    a = ap.parse_args()
    base = a.base if a.base.endswith("/") else a.base + "/"
    b = build(base)
    if os.path.isdir(a.out):
        import shutil

        shutil.rmtree(a.out)
    for rel, data in b.files.items():
        path = os.path.join(a.out, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
    print(f"www آماده شد: {a.out} · نسخهٔ {b.version} · {len(b.files)} فایل · {len(b.zip) // 1024} KB زیپ")


if __name__ == "__main__":
    main()
