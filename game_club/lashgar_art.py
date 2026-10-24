"""عکس برگهٔ آخر لشگر کاغذی برای پیام پایان جنگ در گروه (Pillow).

همان برگهٔ مینی اپ: کاغذ، خط وسط، نقاشی مدادی هر دو نفر (نیمهٔ بالا از دید بازیکن اول برعکس)، نیروها
با خط مدادی، رد همهٔ شلیک ها و ضربدر قرمز روی نیروهای خورده. پاک کن فقط نقاشی همان نیمه را پاک می کند.
"""
from __future__ import annotations

import io
import json
import math

from PIL import Image, ImageDraw

from . import lashgar

S = 0.72                  # پیکسل به ازای هر واحد برگه
PAD = 24
PAPER = (252, 251, 247)
INK = (58, 58, 58)
RED = (200, 50, 60)
# رنگ ها و ضخامت های مداد؛ همان PENCILS و WIDTHS مینی اپ (lashgar.js)
PENCILS = [(61, 61, 61), (200, 50, 60), (224, 123, 36), (232, 180, 34), (62, 142, 58), (31, 95, 200), (138, 90, 43),
           (142, 91, 214)]
WIDTHS = [4, 7, 12, 20]
FLAGS = {"0": (47, 123, 246), "1": (239, 65, 54)}


def _xy(color: str, top: str, x: float, y: float) -> tuple[float, float]:
    """نقطهٔ (x, y) نیمهٔ color ← پیکسل تصویر. نیمهٔ top بالای خط و برعکس است (مثل دید بازیکن پایین)."""
    w, h = lashgar.W * S, lashgar.H * S
    if color == top:
        return PAD + w - x * S, PAD + h - y * S
    return PAD + x * S, PAD + h + y * S


def _ink_layer(strokes: list[dict]) -> Image.Image:
    """نقاشی یک نیمه در مختصات خود آن نیمه (پاک کن شفاف می کند، فقط همین لایه را)."""
    im = Image.new("RGBA", (int(lashgar.W * S), int(lashgar.H * S)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for s in strokes:
        p = s.get("p") or []
        pts = [(p[i] * S, p[i + 1] * S) for i in range(0, len(p) - 1, 2)]
        if not pts:
            continue
        wd = max(1, round(WIDTHS[min(len(WIDTHS) - 1, int(s.get("w") or 0))] * S * (2.2 if s.get("e") else 1)))
        col = (0, 0, 0, 0) if s.get("e") else (*PENCILS[min(len(PENCILS) - 1, int(s.get("c") or 0))], 225)
        if len(pts) > 1:
            d.line(pts, fill=col, width=wd, joint="curve")
        r = wd / 2
        for x, y in (pts[0], pts[-1]):
            d.ellipse((x - r, y - r, x + r, y + r), fill=col)
    return im


def _unit(d: ImageDraw.ImageDraw, u: dict, place, flag_rgb) -> None:  # noqa: ANN001
    """نیرو با همان شکل های SHAPES (فقط خط دور، مثل مداد)؛ place: (x, y) شکل ← پیکسل."""
    a = math.radians(u.get("r") or 0)
    ca, sa = math.cos(a), math.sin(a)

    def P(x: float, y: float) -> tuple[float, float]:
        X, Y = x * lashgar.UNIT_S, y * lashgar.UNIT_S
        return place(u["x"] + X * ca - Y * sa, u["y"] + X * sa + Y * ca)
    lw = max(2, round(1.3 * lashgar.UNIT_S * S))
    for p in lashgar.SHAPES[u["k"]]:
        if p[0] == "c":
            pts = [P(p[1] + (p[3] - 0.5) * math.cos(t / 12 * math.tau), p[2] + (p[3] - 0.5) * math.sin(t / 12 * math.tau)) for t in range(13)]
            d.line(pts, fill=INK, width=lw, joint="curve")
        elif p[0] == "s":
            d.line([P(p[1], p[2]), P(p[3], p[4])], fill=INK, width=lw)
        elif p[0] == "p":
            pts = [P(x, y) for x, y in p[1]]
            if u["k"] == "flag":
                d.polygon(pts, fill=flag_rgb)
            d.line(pts + pts[:1], fill=INK, width=lw, joint="curve")
        else:
            pts = [P(p[1] + (p[3] - 0.6) * math.cos(t / 16 * math.tau), p[2] + (p[4] - 0.6) * math.sin(t / 16 * math.tau)) for t in range(17)]
            d.line(pts, fill=INK, width=lw, joint="curve")


def render(state: dict, strokes: list[dict]) -> bytes:
    """state: وضعیت پایان جنگ؛ strokes: ردیف های ink (color، data) به ترتیب کشیدن ← PNG."""
    order = state["order"]
    top = order[1] if len(order) > 1 else "1"
    w, h = int(lashgar.W * S), int(lashgar.H * S)
    img = Image.new("RGB", (w + PAD * 2, h * 2 + PAD * 2), (154, 106, 64))
    d = ImageDraw.Draw(img)
    d.rectangle((PAD, PAD, PAD + w, PAD + 2 * h), fill=PAPER)
    by: dict[str, list] = {c: [] for c in order}
    for r in strokes:
        try:
            by.setdefault(r["color"], []).append(json.loads(r["data"]))
        except (TypeError, ValueError):
            continue
    for c, lst in by.items():
        layer = _ink_layer(lst)
        if c == top:
            layer = layer.rotate(180)
            img.paste(layer, (PAD, PAD), layer)
        else:
            img.paste(layer, (PAD, PAD + h), layer)
    d = ImageDraw.Draw(img)
    # خط وسط، کمی دست کشیده
    mid = [(PAD + i * w / 24, PAD + h + (2.2 if i % 2 else -2.2)) for i in range(25)]
    d.line(mid, fill=INK, width=3, joint="curve")
    players = state["players"]
    for c in order:
        place = (lambda cc: lambda x, y: _xy(cc, top, x, y))(c)
        for u in players[c].get("units") or []:
            _unit(d, u, place, FLAGS.get(c, (47, 123, 246)))
    rm = lashgar.MARK_R * S
    for sh in state.get("shots") or []:
        foe = next((c for c in order if c != sh.get("by")), None)
        if foe is None or sh.get("off"):
            continue
        x, y = _xy(foe, top, sh["x"], sh["y"])
        d.ellipse((x - rm, y - rm, x + rm, y + rm), fill=RED if sh.get("hit") else (226, 150, 155))
    for c in order:
        for u in players[c].get("units") or []:
            if not u.get("dead"):
                continue
            x, y = _xy(c, top, u["x"], u["y"])
            k = lashgar.REACH[u["k"]] * S * 0.55
            d.line([(x - k, y - k * 0.75), (x + k, y + k * 0.75)], fill=RED, width=4)
            d.line([(x - k, y + k * 0.75), (x + k, y - k * 0.75)], fill=RED, width=4)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
