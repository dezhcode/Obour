"""فونت های مینی اپ (woff2 در game_club/webapp/static/fonts) → ttf برای res/font اندروید.

usage (از native-app): python3 tools/fonts.py      نیاز: pip install fonttools brotli
اندروید woff2 نمی خواند؛ این تبدیل در workflow «AsoTas Native» پیش از ساخت APK اجرا می شود.
"""
import os

from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "..", "game_club", "webapp", "static", "fonts")
OUT = os.path.join(HERE, "android", "app", "src", "main", "res", "font")
FONTS = {
    "Rokh-Regular": "rokh_400", "Rokh-Medium": "rokh_500", "Rokh-Bold": "rokh_700",
    "Rokh-ExtraBold": "rokh_800", "Rokh-Black": "rokh_900",
    "Peyda-400": "peyda_400", "Peyda-600": "peyda_600", "Peyda-700": "peyda_700", "Peyda-800": "peyda_800",
}

os.makedirs(OUT, exist_ok=True)
for src, dst in FONTS.items():
    f = TTFont(os.path.join(SRC, src + ".woff2"))
    f.flavor = None
    f.save(os.path.join(OUT, dst + ".ttf"))
    print(f"{src}.woff2 -> res/font/{dst}.ttf")
