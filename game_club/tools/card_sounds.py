"""ساخت صداهای ورق حکم (بدون فایل بیرونی، فقط numpy و ffmpeg).

    python game_club/tools/card_sounds.py

خروجی در game_club/webapp/static/sfx/ ساخته می شود (mp3 تک کاناله). صداها از
نویز فیلترشده ساخته می شوند تا شبیه کاغذ واقعی باشند:
- place1..3  نشستن ورق روی ماهوت (ضربه کوتاه کاغذ + بم نرم میز)
- place_soft1..3 / place_hard1..3  پرتاب آرام / محکم (با سطح صدای واقعی)
- slide_soft / slide_hard  سُر خوردن کوتاه و آرام / بلند و تند
- throw      هوای پرتاب ورق تا روی میز
- flick      یک ورق پخش شده (برای پخش دست)
- shuffle    بُر زدن (ریفل) با پل آخر
- collect    جمع شدن ورق های یک دور
- slide1..2  سُر خوردن ورق روی ماهوت
- square     تق زدن دسته روی میز برای مرتب کردن
- flip       برگرداندن ورق
همه از مدل فیزیکی ساده ساخته می شوند: مُدهای میرای خود ورق، هوای زیر ورق، ضربهٔ نرم میز،
اصطکاک دانه دانهٔ ماهوت و زمان بندی واقعی ریفل (حدود ۵۰ برگ).
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


def modal(n: int, rng: np.random.Generator, freqs, decays, amps) -> np.ndarray:
    """ارتعاش خود ورق (مقوای نازک): چند مُد میرا که ماهوت زود خفه شان می کند."""
    t = np.arange(n) / SR
    x = np.zeros(n)
    for f, d, a in zip(freqs, decays, amps):
        f *= rng.uniform(.93, 1.07)
        x += a * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t / d)
    return x


def place(rng: np.random.Generator, gain: float = 1.0, dur: float = 0.24, power: float = 0.6) -> np.ndarray:
    """نشستن ورق روی ماهوت. power از ۰ (آرام گذاشتن) تا ۱ (محکم کوبیدن):
    آرام = پف هوای نرم و بم، تق کاغذی خفه، بدون ترق؛ محکم = ترق تیز کاغذ، پف و ضربهٔ میز
    قوی تر و کوتاه تر، مُدهای خود ورق بیشتر شنیده می شود."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    nz = rng.standard_normal(n)
    pw = float(np.clip(power, 0, 1))
    puff = biquad(biquad(nz, "lp", (380 + 520 * pw) * rng.uniform(.85, 1.2)), "hp", 90) * env(n, 0.002 - 0.0012 * pw, (0.016 - 0.007 * pw) * rng.uniform(.8, 1.2))
    slap = biquad(nz, "bp", (1050 + 1100 * pw) * rng.uniform(.85, 1.2), 0.7) * env(n, 0.0004, (0.009 - 0.005 * pw) * rng.uniform(.8, 1.2))
    crisp = biquad(rng.standard_normal(n), "hp", 3800) * env(n, 0.0002, 0.0012 + 0.001 * pw)
    card = modal(n, rng, (520, 1180, 1960, 2880, 4100), (.006, .005, .004, .003, .0025), (.5, .7, .55, .35, .2))
    thump = np.sin(2 * np.pi * (120 - 30 * pw) * rng.uniform(.9, 1.15) * t) * env(n, 0.002, 0.012 + 0.01 * pw)
    x = (1.3 - 0.2 * pw) * puff + (0.6 + 0.7 * pw) * slap + (0.05 + 0.5 * pw ** 1.5) * crisp + (0.15 + 0.35 * pw) * card + (0.3 + 0.45 * pw) * thump
    return biquad(room(x, 0.12), "lp", 3800 + 3200 * pw) * gain


def slide(rng: np.random.Generator, dur: float = 0.22, rate: float = 900) -> np.ndarray:
    """سُر خوردن ورق روی ماهوت: اصطکاک دانه دانه (چسبیدن و رها شدن ریز) که آرام می شود.
    سُر خوردن تند (پرتاب محکم) دانه های بیشتر و صدای روشن تر دارد."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    grains = np.zeros(n)
    pos = 0.0
    while pos < dur * 0.92:
        k = int(pos * SR)
        if k < n:
            grains[k] += rng.uniform(.4, 1.0) * (1 - pos / dur)
        pos += rng.exponential(1 / rate) * (1 + 2.5 * pos / dur)
    tex = biquad(grains + 0.25 * rng.standard_normal(n), "bp", 2400 * rng.uniform(.9, 1.1), 0.8)
    body = biquad(rng.standard_normal(n), "bp", 900, 0.9) * 0.35
    shape = np.clip(t / 0.012, 0, 1) * (1 - t / dur) ** 1.4
    return biquad(room((tex + body) * shape, 0.08), "lp", 5000)


def throw(rng: np.random.Generator, dur: float = 0.18) -> np.ndarray:
    """هوای ورق در پرواز: خِش نرم که با نزدیک شدن کمی زیرتر می شود."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    sweep = 700 + 1400 * (t / dur) ** 1.2
    flutter = 1 + 0.5 * np.sin(2 * np.pi * rng.uniform(22, 30) * t)
    shape = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2
    return biquad(biquad(rng.standard_normal(n), "bp", sweep, 1.1), "lp", 4000) * shape * flutter * 0.6


def flick(rng: np.random.Generator, gain: float = 1.0) -> np.ndarray:
    """یک ورق که از دسته جدا و پخش می شود: تق نوک انگشت و فِش کوتاه."""
    n = int(0.11 * SR)
    nz = rng.standard_normal(n)
    a = biquad(nz, "hp", 2800) * env(n, 0.0003, 0.003)
    b = biquad(nz, "bp", 2100 * rng.uniform(.85, 1.2), 1.0) * env(n, 0.0008, 0.01)
    card = modal(n, rng, (900, 1700, 2600), (.004, .003, .0025), (.4, .5, .3))
    sw = biquad(rng.standard_normal(n), "bp", 1300, 1.2) * env(n, 0.01, 0.03) * 0.35
    return biquad(0.35 * a + 1.1 * b + 0.25 * card + sw, "lp", 6500) * gain


def flap(rng: np.random.Generator) -> np.ndarray:
    """یک برگ در ریفل: گوشهٔ ورق که از زیر شست رها می شود و به برگ زیری می خورد."""
    n = int(0.03 * SR)
    nz = rng.standard_normal(n)
    return (biquad(nz, "bp", rng.uniform(2300, 3600), 1.4) * env(n, 0.0002, rng.uniform(.0015, .003))
            + 0.4 * modal(n, rng, (1400, 2500), (.002, .0015), (.5, .4))) * rng.uniform(.45, 1)


def square(rng: np.random.Generator, hits: int = 2) -> np.ndarray:
    """مرتب کردن دسته: دو بار تق زدن لبهٔ دسته روی میز."""
    n = int((0.09 * hits + 0.12) * SR)
    x = np.zeros(n)
    for h in range(hits):
        m = int(0.09 * SR)
        t = np.arange(m) / SR
        k = int(h * 0.075 * SR)
        hit = (np.sin(2 * np.pi * 190 * rng.uniform(.9, 1.1) * t) * env(m, 0.001, 0.014)
               + 0.6 * biquad(rng.standard_normal(m), "bp", 1250, 0.9) * env(m, 0.0004, 0.006)
               + 0.25 * modal(m, rng, (620, 1450), (.008, .005), (.6, .4)))
        x[k:k + m] += hit * (1 if h == hits - 1 else .7)
    return biquad(room(x, 0.12), "lp", 5000)


def shuffle(rng: np.random.Generator) -> np.ndarray:
    """بُر زدن ریفل: حدود ۵۰ برگ که اول آرام و بعد تند لای هم می روند، پل (آبشار برگ ها)
    و در آخر دو تق برای مرتب کردن دسته."""
    n = int(1.55 * SR)
    x = np.zeros(n)
    pos, gap = 0.05, 0.026
    count = 0
    while pos < 0.78 and count < 52:
        f = flap(rng)
        k = int(pos * SR)
        x[k:k + len(f)] += f[: n - k]
        pos += gap * rng.uniform(.7, 1.3)
        gap = max(0.0085, gap * 0.955) if count < 36 else gap * 1.06
        count += 1
    t = np.arange(n) / SR
    # پل: برگ ها با هم می ریزند (فِش بلند با تق های ریز)
    br0 = 0.86
    br = biquad(rng.standard_normal(n), "bp", 1900, 0.7) * np.clip((t - br0) / 0.04, 0, 1) * np.clip((br0 + 0.28 - t) / 0.12, 0, 1) * 0.3
    x += br
    p = br0
    while p < br0 + 0.26:
        f = flap(rng) * 0.45
        k = int(p * SR)
        x[k:k + len(f)] += f[: n - k]
        p += rng.uniform(.004, .009)
    sq = square(rng)
    k = int(1.22 * SR)
    x[k:k + len(sq)] += sq[: n - k] * 0.9
    return biquad(room(x, 0.1), "lp", 6000)


def collect(rng: np.random.Generator) -> np.ndarray:
    """جمع کردن برگ های روی میز: سُر خوردن و یک تق."""
    s1 = slide(rng, 0.26)
    sq = square(rng, 1)
    n = len(s1) + int(0.08 * SR)
    x = np.zeros(n)
    x[:len(s1)] += s1 * 0.8
    k = int(0.2 * SR)
    x[k:k + len(sq)] += sq[: n - k]
    return x


def flip(rng: np.random.Generator) -> np.ndarray:
    """برگرداندن ورق: فِش سریع هوا و تق کوتاه کاغذ."""
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    sw = biquad(rng.standard_normal(n), "bp", 1500 + 2500 * t / 0.16, 1.0) * np.sin(np.pi * np.clip(t / 0.09, 0, 1)) ** 2
    tick = np.zeros(n)
    k = int(0.085 * SR)
    f = flick(rng, 0.8)
    tick[k:k + len(f)] += f[: n - k]
    return 0.55 * sw + tick


def save(name: str, x: np.ndarray, peak: float = 0.7) -> None:
    """peak سطح نهایی است؛ نسخه های آرام عمدا آرام تر ذخیره می شوند تا شدت واقعی بماند."""
    x = x / (np.max(np.abs(x)) + 1e-9) * peak
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
        save(f"place_soft{k}", place(rng, power=0.1 + 0.05 * k), peak=0.38)
        save(f"place_hard{k}", place(rng, power=0.85 + 0.05 * k), peak=0.92)
    for k in (1, 2):
        save(f"slide{k}", slide(rng, 0.2 + 0.05 * k))
    save("slide_soft", slide(rng, 0.17, 650), peak=0.32)
    save("slide_hard", slide(rng, 0.36, 1400), peak=0.6)
    save("throw", throw(rng))
    save("flick", flick(rng))
    save("shuffle", shuffle(rng))
    save("collect", collect(rng))
    save("square", square(rng))
    save("flip", flip(rng))


if __name__ == "__main__":
    main()
