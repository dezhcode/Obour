"""PNG های make_previews.js -> webp های static/previews (اندازهٔ مناسب کاشی و بنر).

    python3 game_club/tools/make_previews.py /tmp/pv game_club/webapp/static/previews
"""
import os
import sys

from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
os.makedirs(dst, exist_ok=True)


def out(im: Image.Image, name: str, q: int = 86) -> None:
    im.save(os.path.join(dst, name + ".webp"), "WEBP", quality=q, method=6)


def fit(im: Image.Image, w: int) -> Image.Image:
    return im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)


# میز بیلیارد خوابیده (برای کاشی و بنر افقی)
table = Image.open(os.path.join(src, "bl-table.png")).convert("RGBA")
out(fit(table.rotate(90, expand=True), 1200), "bl-table", 84)
for k in (0, 1, 2, 3, 8, 9, 10, 11, 13):
    out(Image.open(os.path.join(src, f"bl-ball-{k}.png")).convert("RGBA").resize((96, 96), Image.LANCZOS), f"bl-ball-{k}", 90)
out(fit(Image.open(os.path.join(src, "bl-cue.png")).convert("RGBA"), 720), "bl-cue", 90)

# فوتبال: زمین ایستاده، مهره های دو تیم و توپ
out(fit(Image.open(os.path.join(src, "fb-pitch.png")).convert("RGB"), 720), "fb-pitch", 82)
for n in ("fb-disc-eagles", "fb-disc-lions"):
    out(Image.open(os.path.join(src, n + ".png")).convert("RGBA").resize((160, 160), Image.LANCZOS), n, 90)
out(Image.open(os.path.join(src, "fb-ball.png")).convert("RGBA").resize((72, 72), Image.LANCZOS), "fb-ball", 90)
print("ok", sorted(os.listdir(dst)))
