"""آیکون و صفحهٔ شروع برنامهٔ اندروید Game Club، از روی همان تاس سفید دکمهٔ «بازی ها» در منوی مینی اپ.

    python3 game_club/android-app/tools/make_icons.py

خروجی: mipmap ها (آیکون معمولی، گرد و لایه های adaptive)، splash ها و store/icon-512.png برای مایکت.
فقط Pillow لازم دارد؛ خروجی ها در مخزن هستند و build اندروید به این اسکریپت نیازی ندارد.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "android", "app", "src", "main", "res")
STORE = os.path.join(HERE, "..", "store")
SKY, VIOLET = (43, 110, 242), (124, 102, 242)
PIPS = [(76, 141, 255), (255, 90, 106), (47, 197, 132), (255, 197, 49)]   # رنگ مهره های چهار بازیکن
INK = (28, 34, 53)
DENS = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
SS = 4   # نمونه برداری بیشتر برای لبه های نرم


def gradient(n: int) -> Image.Image:
    """زمینهٔ آبی به بنفش (مورب) با نور ملایم بالا."""
    g = Image.new("RGB", (n, n))
    px = g.load()
    for y in range(n):
        for x in range(n):
            t = (x + y) / (2 * (n - 1))
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(SKY, VIOLET))
    glow = Image.new("L", (n, n), 0)
    ImageDraw.Draw(glow).ellipse((-n * .2, -n * .45, n * 1.2, n * .55), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(n / 8))
    return Image.composite(Image.new("RGB", (n, n), (255, 255, 255)), g, glow)


def die(n: int, frac: float) -> Image.Image:
    """تاس سفید کج (۹ درجه) با سایه، پنج خال: چهار گوشه به رنگ بازیکن ها و وسط سرمه ای. شفاف، n×n."""
    big = n * SS
    s = big * frac
    layer = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    x0, y0 = (big - s) / 2, (big - s) / 2
    r = s * .26
    # سایهٔ زیر تاس
    sh = Image.new("L", (big, big), 0)
    ImageDraw.Draw(sh).rounded_rectangle((x0, y0 + s * .09, x0 + s, y0 + s * 1.09), r, fill=120)
    sh = sh.filter(ImageFilter.GaussianBlur(s * .07))
    layer.paste(Image.new("RGBA", (big, big), (16, 20, 60, 255)), (0, 0), sh)
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((x0, y0, x0 + s, y0 + s), r, fill=(205, 211, 224, 255))            # لبهٔ پایین (عمق)
    d.rounded_rectangle((x0, y0, x0 + s, y0 + s * .93), r, fill=(255, 255, 255, 255))
    pr, pad = s * .095, s * .25
    spots = [(pad, pad, PIPS[0]), (s - pad, pad, PIPS[1]), (s / 2, s * .465, INK), (pad, s * .93 - pad, PIPS[2]), (s - pad, s * .93 - pad, PIPS[3])]
    for cx, cy, col in spots:
        d.ellipse((x0 + cx - pr, y0 + cy - pr, x0 + cx + pr, y0 + cy + pr), fill=col + (255,))
    layer = layer.rotate(9, resample=Image.BICUBIC, center=(big / 2, big / 2))
    return layer.resize((n, n), Image.LANCZOS)


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


def full_icon(n: int, frac: float = .6) -> Image.Image:
    bg = gradient(n).convert("RGBA")
    bg.alpha_composite(die(n, frac))
    return bg


def save(img: Image.Image, *parts: str) -> None:
    path = os.path.join(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, optimize=True)


def main() -> None:
    for dens, k in DENS.items():
        legacy, fg = round(48 * k), round(108 * k)
        base = full_icon(legacy)
        save(masked(base, "square"), RES, f"mipmap-{dens}", "ic_launcher.png")
        save(masked(base, "circle"), RES, f"mipmap-{dens}", "ic_launcher_round.png")
        # adaptive: لایهٔ جلو فقط تاس (در محدودهٔ امن ۶۶ از ۱۰۸)، لایهٔ پشت زمینهٔ رنگی
        save(die(fg, .44), RES, f"mipmap-{dens}", "ic_launcher_foreground.png")
        save(gradient(fg), RES, f"mipmap-{dens}", "ic_launcher_background.png")
        # صفحهٔ شروع اندروید ۱۱ و پایین تر (عمودی و افقی)
        for orient, (w, h) in (("port", (320, 480)), ("land", (480, 320))):
            W, H = round(w * k), round(h * k)
            sp = gradient(max(W, H)).crop((0, 0, W, H)).convert("RGBA")
            m = round(min(W, H) * .42)
            sp.alpha_composite(die(m, .72), ((W - m) // 2, (H - m) // 2))
            save(sp.convert("RGB"), RES, f"drawable-{orient}-{dens}", "splash.png")
    sp = gradient(480).crop((0, 80, 480, 400)).convert("RGBA")
    sp.alpha_composite(die(140, .72), (170, 90))
    save(sp.convert("RGB"), RES, "drawable", "splash.png")
    save(full_icon(512).convert("RGB"), STORE, "icon-512.png")
    print("آیکون ها و splash ساخته شدند")


if __name__ == "__main__":
    main()
