"""ساخت صداهای فوتبال (بدون فایل بیرونی، فقط numpy و ffmpeg).

    python game_club/tools/football_sounds.py

خروجی کنار صداهای ورق در game_club/webapp/static/sfx/:
- fb_kick    ضربهٔ انگشت به مهره (تق پلاستیکی کوتاه)
- fb_clack   برخورد مهره با مهره یا توپ
- fb_wall    خوردن به دیوارهٔ زمین (بم و چوبی)
- fb_whistle سوت داور (با لرزش ساچمه)
- fb_goal    هورای تماشاگرها بعد از گل
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from card_sounds import OUT, SR, biquad, env, room, save  # noqa: E402


def kick(rng: np.random.Generator) -> np.ndarray:
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * (210 - 60 * t / 0.16) * t) * env(n, 0.002, 0.035)
    snap = biquad(rng.standard_normal(n), "bp", 2600, 1.4) * env(n, 0.0005, 0.006) * 0.9
    return room(body * 0.9 + snap, 0.1)


def clack(rng: np.random.Generator) -> np.ndarray:
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    tick = biquad(rng.standard_normal(n), "bp", 3300, 2.2) * env(n, 0.0004, 0.008)
    ring = (np.sin(2 * np.pi * 1450 * t) * 0.5 + np.sin(2 * np.pi * 2380 * t) * 0.3) * env(n, 0.0005, 0.018)
    return room(tick + ring * 0.6, 0.08)


def wall(rng: np.random.Generator) -> np.ndarray:
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    thud = biquad(rng.standard_normal(n), "lp", 520, 0.9) * env(n, 0.001, 0.04)
    tone = np.sin(2 * np.pi * 118 * t) * env(n, 0.002, 0.06)
    return room(thud * 1.4 + tone * 0.8, 0.14)


def whistle(rng: np.random.Generator) -> np.ndarray:
    def blow(d: float) -> np.ndarray:
        n = int(d * SR)
        t = np.arange(n) / SR
        trill = 1 + 0.035 * np.sign(np.sin(2 * np.pi * 27 * t + rng.random()))
        f = 2650 * trill
        ph = 2 * np.pi * np.cumsum(f) / SR
        x = np.sin(ph) + 0.25 * np.sin(2 * ph)
        air = biquad(rng.standard_normal(n), "bp", 2650, 3.0) * 0.25
        e = np.clip(t / 0.02, 0, 1) * np.clip((d - t) / 0.05, 0, 1)
        return (x * 0.8 + air) * e
    gap = np.zeros(int(0.09 * SR))
    return room(np.concatenate([blow(0.16), gap, blow(0.62)]), 0.2)


def goal(rng: np.random.Generator) -> np.ndarray:
    d = 2.6
    n = int(d * SR)
    t = np.arange(n) / SR
    crowd = np.zeros(n)
    for f, q in ((520, 0.8), (900, 1.1), (1500, 1.3), (2300, 1.6)):
        band = biquad(rng.standard_normal(n), "bp", f, q)
        lfo = 0.75 + 0.25 * np.sin(2 * np.pi * (2 + rng.random() * 3) * t + rng.random() * 6)
        crowd += band * lfo
    shape = np.clip(t / 0.35, 0, 1) ** 1.5 * np.where(t > 1.7, np.exp(-(t - 1.7) / 0.45), 1.0)
    # چند «هوو»ی بلند در میان جمعیت
    yell = np.zeros(n)
    for k in range(6):
        s = int((0.2 + rng.random() * 1.2) * SR)
        m = int(0.5 * SR)
        tt = np.arange(m) / SR
        f0 = 260 + rng.random() * 180
        v = np.sin(2 * np.pi * f0 * tt * (1 + 0.15 * tt)) * np.sin(np.pi * tt / 0.5) * 0.18
        yell[s:s + m] += v[: max(0, min(m, n - s))]
    return room(crowd * shape + biquad(yell, "lp", 1800) * shape, 0.22)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(2026)
    save("fb_kick", kick(rng))
    save("fb_clack", clack(rng))
    save("fb_wall", wall(rng))
    save("fb_whistle", whistle(rng))
    save("fb_goal", goal(rng))


if __name__ == "__main__":
    main()
