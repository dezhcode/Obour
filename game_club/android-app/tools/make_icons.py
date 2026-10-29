"""آیکون و صفحهٔ شروع برنامهٔ اندروید AsoTas از روی شخصیت برند («تاسی» داش‌مشتی).

    python3 game_club/android-app/tools/make_icons.py

ورودی ها (game_club/android-app/art):
  mascot-icon.png  آیکون کامل با زمینهٔ آبی و بنفش (نیم تنه)؛ برای آیکون معمولی و گرد و آیکون ۵۱۲ مایکت
  mascot-full.png  همان شخصیت با تمام قد و زمینهٔ شفاف؛ لایهٔ جلوی آیکون adaptive و صفحهٔ شروع
خروجی: mipmap ها، splash ها و store/icon-512.png. فقط Pillow لازم است؛ خروجی ها در مخزن هستند.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "..", "art")
RES = os.path.join(HERE, "..", "android", "app", "src", "main", "res")
STORE = os.path.join(HERE, "..", "store")
# همان رنگ های زمینهٔ آیکون (گوشهٔ بالا چپ آبی، پایین راست بنفش) و نور طلایی پشت شخصیت
TL, TR, BL, BR = (18, 104, 240), (98, 97, 250), (42, 105, 247), (124, 78, 251)
GLOW = (255, 214, 120)
DENS = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
SS = 4


def background(w: int, h: int, glow_at=(.5, .42), glow_r=.34) -> Image.Image:
    """زمینهٔ آبی به بنفش (درون یابی چهار گوشه) با هالهٔ طلایی نرم."""
    # ۲×۲ پیکسل گوشه ها، اول ۶۴×۶۴ (دوخطی) و بعد اندازهٔ نهایی: گرادیان نرم بدون نوار
    g = Image.new("RGB", (2, 2))
    for (x, y), c in zip(((0, 0), (1, 0), (0, 1), (1, 1)), (TL, TR, BL, BR)):
        g.putpixel((x, y), c)
    g = g.resize((64, 64), Image.BILINEAR).resize((w, h), Image.BICUBIC).convert("RGBA")
    m = Image.new("L", (w, h), 0)
    r = min(w, h) * glow_r
    cx, cy = w * glow_at[0], h * glow_at[1]
    ImageDraw.Draw(m).ellipse((cx - r, cy - r, cx + r, cy + r), fill=105)
    m = m.filter(ImageFilter.GaussianBlur(r * .5))
    g.paste(Image.new("RGBA", (w, h), GLOW + (255,)), (0, 0), m)
    return g


def masked(img: Image.Image, shape: str) -> Image.Image:
    n = img.width
    m = Image.new("L", (n * SS, n * SS), 0)
    if shape == "circle":
        ImageDraw.Draw(m).ellipse((0, 0, n * SS - 1, n * SS - 1), fill=255)
    else:
        ImageDraw.Draw(m).rounded_rectangle((0, 0, n * SS - 1, n * SS - 1), n * SS * .22, fill=255)
    out = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    out.paste(img.convert("RGBA"), (0, 0), m.resize((n, n), Image.LANCZOS))
    return out


def fit(img: Image.Image, box: int) -> Image.Image:
    k = box / max(img.size)
    return img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)


def foreground(full: Image.Image, n: int) -> Image.Image:
    """لایهٔ جلوی آیکون adaptive (۱۰۸ واحد) با همان ترکیب آیکون اصلی: کلاه از ۱۶٪ بالا، دست ها تا ۸۰٪.
    گوشی ها معمولا ۸۰ واحد وسط را نشان می دهند (کلاه تا دست ها کامل)؛ جلیقه تا لبهٔ پایین ادامه دارد تا جای برش
    دیده نشود؛ با سخت ترین برش (دایرهٔ ۷۲ واحدی) هم صورت و کلاه کامل است."""
    layer = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    h = n * .97                                   # قد کامل شخصیت به این اندازه؛ دست ها حدود ۶۶٪ قد
    w = round(h * full.width / full.height)
    body = full.resize((w, round(h)), Image.LANCZOS)
    top = round(n * .16)
    body = body.crop((0, 0, w, min(body.height, n - top)))
    layer.alpha_composite(body, ((n - w) // 2, top))
    return layer


def save(img: Image.Image, *parts: str) -> None:
    path = os.path.join(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, optimize=True)


def main() -> None:
    icon = Image.open(os.path.join(ART, "mascot-icon.png")).convert("RGB")
    full = Image.open(os.path.join(ART, "mascot-full.png")).convert("RGBA")
    for dens, k in DENS.items():
        legacy, fg = round(48 * k), round(108 * k)
        small = icon.resize((legacy, legacy), Image.LANCZOS)
        save(masked(small, "square"), RES, f"mipmap-{dens}", "ic_launcher.png")
        save(masked(small, "circle"), RES, f"mipmap-{dens}", "ic_launcher_round.png")
        save(foreground(full, fg), RES, f"mipmap-{dens}", "ic_launcher_foreground.png")
        save(background(fg, fg).convert("RGB"), RES, f"mipmap-{dens}", "ic_launcher_background.png")
        # صفحهٔ شروع اندروید ۱۱ و پایین تر: شخصیت تمام قد روی همان زمینه
        for orient, (w, h) in (("port", (320, 480)), ("land", (480, 320))):
            W, H = round(w * k), round(h * k)
            sp = background(W, H, glow_at=(.5, .47), glow_r=.30)
            c = fit(full, round(min(W, H) * (.62 if orient == "port" else .72)))
            sp.alpha_composite(c, ((W - c.width) // 2, (H - c.height) // 2))
            save(sp.convert("RGB"), RES, f"drawable-{orient}-{dens}", "splash.png")
    sp = background(480, 320, glow_at=(.5, .47), glow_r=.30)
    c = fit(full, 230)
    sp.alpha_composite(c, ((480 - c.width) // 2, (320 - c.height) // 2))
    save(sp.convert("RGB"), RES, "drawable", "splash.png")
    save(icon.resize((512, 512), Image.LANCZOS), STORE, "icon-512.png")
    print("آیکون ها و splash ساخته شدند")


if __name__ == "__main__":
    main()
