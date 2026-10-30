"""آیکن های مینی اپ (P در game_club/webapp/static/gc.js) → Kotlin برای برنامهٔ نیتیو.

usage: python -I native-app/tools/gen_icons.py   (از ریشهٔ مخزن)
خروجی: native-app/android/app/src/main/java/dezhcode/asotas/ui/IconPaths.kt
هر آیکن یک یا چند تکه است: داده مسیر SVG (دایره و مستطیل گرد هم به مسیر تبدیل می شوند) و چرخش اختیاری.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "game_club", "webapp", "static", "gc.js")
OUT = os.path.join(ROOT, "native-app", "android", "app", "src", "main", "java", "dezhcode", "asotas", "ui", "IconPaths.kt")


def num(v):
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


def circle(a):
    cx, cy, r = float(a["cx"]), float(a["cy"]), float(a["r"])
    return f"M{num(cx - r)} {num(cy)}a{num(r)} {num(r)} 0 1 0 {num(2 * r)} 0a{num(r)} {num(r)} 0 1 0 {num(-2 * r)} 0z"


def rect(a):
    x, y, w, h = (float(a[k]) for k in ("x", "y", "width", "height"))
    r = min(float(a.get("rx", 0)), w / 2, h / 2)
    if not r:
        return f"M{num(x)} {num(y)}h{num(w)}v{num(h)}h{num(-w)}z"
    return (f"M{num(x + r)} {num(y)}h{num(w - 2 * r)}a{num(r)} {num(r)} 0 0 1 {num(r)} {num(r)}"
            f"v{num(h - 2 * r)}a{num(r)} {num(r)} 0 0 1 {num(-r)} {num(r)}h{num(-(w - 2 * r))}"
            f"a{num(r)} {num(r)} 0 0 1 {num(-r)} {num(-r)}v{num(-(h - 2 * r))}a{num(r)} {num(r)} 0 0 1 {num(r)} {num(-r)}z")


def parts(svg):
    out = []
    for tag, attrs in re.findall(r"<(path|circle|rect)\s([^>]*?)/?>", svg):
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
        d = a["d"] if tag == "path" else circle(a) if tag == "circle" else rect(a)
        rot = re.match(r"rotate\(([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)", a.get("transform", ""))
        out.append((d, rot.groups() if rot else None))
    return out


def main():
    js = open(SRC, encoding="utf-8").read()
    body = js[js.index("const P = {"):]
    body = body[:body.index("\n};")]
    icons = re.findall(r"^\s+(\w+): '(.*)',?$", body, re.M)
    lines = [
        "package dezhcode.asotas.ui",
        "",
        "// ساخته شده با native-app/tools/gen_icons.py از آیکن های مینی اپ (P در game_club/webapp/static/gc.js)؛ دستی عوض نکن",
        "",
        "internal class IconPart(val d: String, val rotate: Float = 0f, val px: Float = 0f, val py: Float = 0f)",
        "",
        "internal val ICON_PATHS: Map<String, List<IconPart>> = mapOf(",
    ]
    for name, svg in icons:
        ps = []
        for d, rot in parts(svg):
            if rot:
                ps.append(f'IconPart("{d}", {num(rot[0])}f, {num(rot[1])}f, {num(rot[2])}f)')
            else:
                ps.append(f'IconPart("{d}")')
        lines.append(f'    "{name}" to listOf({", ".join(ps)}),')
    lines.append(")")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{len(icons)} icons -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
