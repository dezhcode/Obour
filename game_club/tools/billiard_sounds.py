"""ساخت صداهای بیلیارد (بدون فایل بیرونی، فقط numpy؛ برای mp3 ffmpeg یا lameenc).

    python game_club/tools/billiard_sounds.py

مثل صداهای فوتبال با «سنتز مُدال»: هر جسم چند فرکانس طبیعی دارد که با ضربه با هم به
صدا درمی آیند و هر کدام با سرعت خودش خاموش می شود، به همراه ضربهٔ کوتاه نویزی تماس.
توپ بیلیارد رزین فنولیک سخت است: صدای برخوردش بسیار کوتاه، روشن و «تقِ» شفاف است؛
کوشن لاستیک روی چوب است: گرومپ نرم و بم؛ جیب: افتادن روی چرم و غلتیدن در توری.
خروجی در game_club/webapp/static/sfx/:

- bl_click1..3   برخورد محکم دو توپ (سه رنگ کمی متفاوت تا تکراری نباشد)
- bl_soft1..2    برخورد آرام دو توپ (تیک کوچک)
- bl_rail1..2    خوردن توپ به کوشن
- bl_pocket1..2  افتادن توپ در جیب و غلتیدنش در توری
- bl_cue1..2     ضربهٔ نوک چرمی چوب به توپ سفید (آرام / محکم)
- bl_rack        چیدن توپ ها در مثلث
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave

import numpy as np

SR = 44100
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webapp", "static", "sfx")
RNG = np.random.default_rng(1908)


def t_axis(d: float) -> np.ndarray:
    return np.arange(int(d * SR)) / SR


def shape(x: np.ndarray, gain) -> np.ndarray:
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(X * gain(f), len(x))


def band(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return shape(x, lambda f: 1 / (1 + (lo / np.maximum(f, 1)) ** 4) / (1 + (f / hi) ** 4))


def lp(x: np.ndarray, hi: float) -> np.ndarray:
    return shape(x, lambda f: 1 / (1 + (f / hi) ** 4))


def hp(x: np.ndarray, lo: float) -> np.ndarray:
    return shape(x, lambda f: 1 / (1 + (lo / np.maximum(f, 1)) ** 4))


def modes(d: float, specs, drop: float = 0.0, jitter: float = .02) -> np.ndarray:
    """specs: (فرکانس، زمان خاموشی، دامنه). drop: افت فرکانس در لحظهٔ ضربه."""
    t = t_axis(d)
    out = np.zeros_like(t)
    for f, tau, a in specs:
        f = f * (1 + RNG.uniform(-jitter, jitter))
        fi = f * (1 + drop * np.exp(-t / 0.006))
        out += a * np.exp(-t / tau) * np.sin(2 * np.pi * np.cumsum(fi) / SR + RNG.uniform(0, 6.28))
    return out


def burst(d: float, ms: float, attack_ms: float = 0.0) -> np.ndarray:
    t = t_axis(d)
    env = np.exp(-t / (ms / 1000))
    if attack_ms:
        env *= 1 - np.exp(-t / (attack_ms / 1000))
    return RNG.standard_normal(len(t)) * env


def room(x: np.ndarray, amount: float = .1, size: float = 1.0) -> np.ndarray:
    """انعکاس های کوتاه سالن کوچک (کف و دیوار نزدیک)."""
    y = x.copy()
    for dl, g in ((.007, .45), (.013, .32), (.021, .22), (.034, .14), (.052, .09), (.081, .05)):
        k = int(dl * size * SR)
        if k < len(x):
            y[k:] += lp(x, 3500)[:-k] * g * amount * 2.2
    return y


def place(dst: np.ndarray, src: np.ndarray, at: float, gain: float = 1.0) -> None:
    s = int(at * SR)
    if s >= len(dst):
        return
    n = min(len(src), len(dst) - s)
    dst[s:s + n] += src[:n] * gain


# ---------- اجزا ----------
def click(v: int, hard: float = 1.0) -> np.ndarray:
    """برخورد دو توپ رزینی: لحظهٔ تماس ~۰٫۲ میلی ثانیه ⇒ ضربهٔ پهن باند، بعد زنگ کوتاه کره ها."""
    d = .16
    sh = 1 + (v - 2) * .045
    ring = modes(d, ((3150 * sh, .010, 1.0), (4780 * sh, .007, .75), (6420 * sh, .005, .5), (8350 * sh, .0035, .3),
                     (1880 * sh, .006, .35)), drop=.04)
    tick = band(burst(d, .35, .03), 1500, 11000) * 1.6
    body = modes(d, ((920 * sh, .007, .35),))
    x = tick * (.6 + .4 * hard) + ring * (.35 + .4 * hard) + body * .5
    if hard < .6:   # آرام: روشنایی کمتر
        x = lp(x, 3000 + 6000 * hard)
    return room(x, .07)


def rail(v: int) -> np.ndarray:
    """کوشن لاستیکی روی ریل چوبی: گرومپ بم و نرم با کمی صدای چوب."""
    d = .34
    sh = 1 + (v - 1) * .07
    thud = modes(d, ((118 * sh, .055, 1.0), (186 * sh, .04, .55), (296 * sh, .028, .35), (455 * sh, .016, .2)), drop=.18)
    rub = lp(burst(d, 7, .4), 700) * .7
    wood = modes(d, ((780 * sh, .012, .28), (1240 * sh, .007, .14)))
    slap = band(burst(d, .8, .05), 900, 3500) * .35
    return room(thud + rub + wood + slap, .14, 1.2)


def drop_in(v: int) -> np.ndarray:
    """افتادن در جیب: ضربه به لبهٔ چرمی، افت، چند برخورد کوچک با توپ های داخل و غلتیدن در توری."""
    d = 1.15
    out = np.zeros(int(d * SR))
    # ضربهٔ اول به لبهٔ جیب و چرم ته جیب
    place(out, modes(.35, ((140, .06, 1), (230, .04, .6), (380, .025, .3)), drop=.2) + lp(burst(.35, 6, .3), 900) * .8, 0.0, 1.0)
    place(out, click(1 + v, .45) * .55, .012)
    # برخوردهای کوچک با توپ های داخل جیب (فاصله ها و شدت ها کم می شوند)
    t, g = .16 + .03 * v, .55
    for k in range(5 + v):
        place(out, click(1 + (k % 3), .35 + .3 * g) * g, t)
        t += .07 + .05 * k * RNG.uniform(.6, 1.1)
        g *= .62
    # غلتیدن روی توری و چرم: همهمهٔ بم که خاموش می شود
    tt = t_axis(d)
    roll = lp(RNG.standard_normal(len(tt)), 260) * np.exp(-((tt - .45) / .32) ** 2) * .9
    roll *= 1 + .5 * np.sin(2 * np.pi * 11 * tt)
    out += roll
    return room(out, .1)


def cue(v: int) -> np.ndarray:
    """نوک چرمی چوب به توپ: «تاک» کوتاه و نسبتا گرم؛ محکم ⇒ تیزتر."""
    d = .2
    hard = .45 if v == 1 else 1.0
    tip = band(burst(d, 1.1 + (1 - hard), .1), 600, 2600 + 3500 * hard) * 1.2
    ball = modes(d, ((3100, .008, .45 * hard), (4700, .005, .3 * hard)))
    wood = modes(d, ((330, .02, .55), (610, .012, .35), (1450, .006, .25 * hard)))
    return room(tip + ball + wood, .08)


def rack() -> np.ndarray:
    """چیدن توپ ها در مثلث: چند ده تق کوچک پشت سر هم و صدای غلتیدن روی ماهوت."""
    d = 1.3
    out = np.zeros(int(d * SR))
    t = .0
    for k in range(26):
        place(out, click(1 + k % 3, RNG.uniform(.25, .7)) * RNG.uniform(.25, .7), t)
        t += RNG.uniform(.02, .06)
    tt = t_axis(d)
    out += lp(RNG.standard_normal(len(tt)), 400) * np.exp(-((tt - .45) / .4) ** 2) * .25
    return room(out, .1)


# ---------- ذخیره ----------
def save(name: str, x: np.ndarray, peak: float = 0.75) -> None:
    x = x / (np.max(np.abs(x)) + 1e-9) * peak
    fade = min(len(x), int(0.008 * SR))
    x[-fade:] *= np.linspace(1, 0, fade)
    pcm = (x * 32767).astype("<i2")
    out = os.path.join(OUT, name + ".mp3")
    if shutil.which("ffmpeg"):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
            tmp = fh.name
        with wave.open(tmp, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-ac", "1", "-b:a", "64k", out], check=True)
        os.remove(tmp)
    else:
        import lameenc   # pip install lameenc
        enc = lameenc.Encoder()
        enc.set_bit_rate(64)
        enc.set_in_sample_rate(SR)
        enc.set_channels(1)
        enc.set_quality(2)
        with open(out, "wb") as fh:
            fh.write(enc.encode(pcm.tobytes()) + enc.flush())
    print(name, os.path.getsize(out), "bytes")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for v in (1, 2, 3):
        save(f"bl_click{v}", click(v, 1.0))
    for v in (1, 2):
        save(f"bl_soft{v}", click(v, .35), .45)
    for v in (1, 2):
        save(f"bl_rail{v}", rail(v))
    for v in (1, 2):
        save(f"bl_pocket{v}", drop_in(v))
    save("bl_cue1", cue(1), .55)
    save("bl_cue2", cue(2))
    save("bl_rack", rack(), .6)


if __name__ == "__main__":
    main()
