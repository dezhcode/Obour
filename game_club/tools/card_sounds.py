"""ساخت صداهای ورق حکم (بدون فایل بیرونی، فقط numpy و ffmpeg).

    python game_club/tools/card_sounds.py

خروجی در game_club/webapp/static/sfx/ ساخته می شود (mp3 تک کاناله). صداها از
نویز فیلترشده ساخته می شوند تا شبیه کاغذ واقعی باشند:
- place1..3  نشستن ورق روی ماهوت (ضربه کوتاه کاغذ + بم نرم میز)
- throw      هوای پرتاب ورق تا روی میز
- flick      یک ورق پخش شده (برای پخش دست)
- shuffle    بُر زدن (ریفل) با پل آخر
- collect    جمع شدن ورق های یک دور
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import wave

import numpy as np

SR = 44100
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webapp", "static", "sfx")


def biquad(x: np.ndarray, kind: str, f, q: float = 0.707) -> np.ndarray:
    """فیلتر RBJ؛ f می تواند ثابت یا آرایه (فرکانس متغیر در زمان) باشد."""
    n = len(x)
    fa = np.broadcast_to(np.asarray(f, dtype=float), (n,))
    y = np.zeros(n)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(n):
        if i % 32 == 0:
            w = 2 * np.pi * min(fa[i], SR * 0.45) / SR
            cw, sw = np.cos(w), np.sin(w)
            al = sw / (2 * q)
            if kind == "bp":
                b0, b1, b2 = al, 0.0, -al
            elif kind == "hp":
                b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
            else:
                b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
            a0, a1, a2 = 1 + al, -2 * cw, 1 - al
            b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0
        v = b0 * x[i] + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, x[i], y1, v
        y[i] = v
    return y


def env(n: int, attack: float, tau: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-np.maximum(t - attack, 0) / tau)


def room(x: np.ndarray, amount: float = 0.16) -> np.ndarray:
    """اتاق کوچک: چند پژواک کوتاه و نرم شده."""
    y = x.copy()
    for d, g in ((0.011, 0.5), (0.019, 0.35), (0.029, 0.25), (0.043, 0.15)):
        k = int(d * SR)
        e = np.zeros_like(x)
        e[k:] = x[:-k]
        y += amount * g * biquad(e, "lp", 3500)
    return y


def place(rng: np.random.Generator, gain: float = 1.0, dur: float = 0.26) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    snap = biquad(nz, "hp", 2200) * env(n, 0.0006, 0.0035 * rng.uniform(.8, 1.2))
    paper = biquad(nz, "bp", 1300 * rng.uniform(.85, 1.2), 0.8) * env(n, 0.0012, 0.016 * rng.uniform(.8, 1.25))
    air = biquad(rng.standard_normal(n), "bp", 3600 * rng.uniform(.9, 1.1), 1.3) * env(n, 0.0008, 0.007)
    thump = np.sin(2 * np.pi * 150 * rng.uniform(.9, 1.15) * t) * env(n, 0.002, 0.02)
    x = 0.35 * snap + 1.6 * paper + 0.3 * air + 0.55 * thump
    return biquad(room(x), "lp", 5200) * gain


def throw(rng: np.random.Generator, dur: float = 0.2) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    sweep = 1100 + 1700 * (t / dur) ** 0.8
    rustle = 1 + 0.35 * biquad(rng.standard_normal(n), "lp", 60) * 8
    shape = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.6
    return biquad(biquad(rng.standard_normal(n), "bp", sweep, 0.9), "lp", 4500) * shape * rustle * 0.9


def flick(rng: np.random.Generator, gain: float = 1.0) -> np.ndarray:
    n = int(0.09 * SR)
    nz = rng.standard_normal(n)
    a = biquad(nz, "hp", 2600) * env(n, 0.0004, 0.004)
    b = biquad(nz, "bp", 1900 * rng.uniform(.85, 1.2), 1.0) * env(n, 0.001, 0.011)
    return biquad(0.3 * a + 1.3 * b, "lp", 6000) * gain


def shuffle(rng: np.random.Generator) -> np.ndarray:
    n = int(1.15 * SR)
    x = np.zeros(n)
    pos, gap = 0.04, 0.032
    while pos < 0.82:
        f = flick(rng, rng.uniform(.35, .75))
        k = int(pos * SR)
        x[k:k + len(f)] += f[: n - k]
        pos += gap * rng.uniform(.8, 1.2)
        gap = max(0.011, gap * 0.95)
    t = np.arange(n) / SR
    rustle = biquad(rng.standard_normal(n), "bp", 2200, 0.7) * np.clip((t - 0.02) / 0.1, 0, 1) * np.clip((0.85 - t) / 0.1, 0, 1) * 0.18
    x += rustle
    br = throw(rng, 0.22) * 0.7
    k = int(0.84 * SR)
    x[k:k + len(br)] += br[: n - k]
    p = place(rng, 0.7, 0.2)
    k = int(1.0 * SR)
    x[k:k + len(p)] += p[: n - k]
    return biquad(room(x, 0.1), "lp", 5500)


def collect(rng: np.random.Generator) -> np.ndarray:
    n = int(0.34 * SR)
    t = np.arange(n) / SR
    sweep = 900 + 1300 * (t / 0.34)
    shape = np.sin(np.pi * np.clip(t / 0.3, 0, 1)) ** 1.3
    x = biquad(biquad(rng.standard_normal(n), "bp", sweep, 0.9), "lp", 4000) * shape * 0.7
    p = place(rng, 0.55, 0.2)
    k = int(0.22 * SR)
    x[k:k + len(p)] += p[: n - k]
    return x


def save(name: str, x: np.ndarray) -> None:
    x = x / (np.max(np.abs(x)) + 1e-9) * 0.7
    fade = min(len(x), int(0.01 * SR))
    x[-fade:] *= np.linspace(1, 0, fade)
    pcm = (x * 32767).astype("<i2")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
        tmp = fh.name
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    out = os.path.join(OUT, name + ".mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-ac", "1", "-b:a", "64k", out], check=True)
    os.remove(tmp)
    print(name, os.path.getsize(out), "bytes")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(1405)
    for k in (1, 2, 3):
        save(f"place{k}", place(rng))
    save("throw", throw(rng))
    save("flick", flick(rng))
    save("shuffle", shuffle(rng))
    save("collect", collect(rng))


if __name__ == "__main__":
    main()
