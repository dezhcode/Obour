"""ساخت صداهای فوتبال (بدون فایل بیرونی، فقط numpy و ffmpeg).

    python game_club/tools/football_sounds.py

صداها با «سنتز مُدال» ساخته می شوند: هر جسم چند فرکانس طبیعی دارد که با ضربه با هم به
صدا درمی آیند و هر کدام با سرعت خودش خاموش می شود؛ همراه یک ضربه کوتاه نویزی. فیلترها
در حوزه فرکانس (FFT) اعمال می شوند تا ساخت سریع باشد. خروجی کنار صداهای ورق در
game_club/webapp/static/sfx/:

- fb_kick        ضربه انگشت به مهره (تق نرم)
- fb_clack1..3   برخورد دو مهره فلزی-پلاستیکی (تق شفاف با کمی زنگ)
- fb_ball1..2    خوردن مهره به توپ چرمی (پوک بم)
- fb_wall        خوردن به دیواره کنار زمین (گرومپ با کمی لرزش)
- fb_post        خوردن توپ به تیرک فلزی (دینگ)
- fb_whistle     سوت داور با لرزش ساچمه (یک کوتاه و یک بلند)
- fb_goal        هورای تماشاگرها بعد از گل
- fb_crowd       همهمه تماشاگرها، حلقه ۸ ثانیه ای برای پس زمینه
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from card_sounds import OUT, SR, save  # noqa: E402

RNG = np.random.default_rng(2027)


def t_axis(d: float) -> np.ndarray:
    return np.arange(int(d * SR)) / SR


def shape(x: np.ndarray, gain) -> np.ndarray:
    """فیلتر در حوزه فرکانس: gain(f) ضریب هر فرکانس."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(X * gain(f), len(x))


def band(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return shape(x, lambda f: 1 / (1 + (lo / np.maximum(f, 1)) ** 4) / (1 + (f / hi) ** 4))


def lp(x: np.ndarray, hi: float) -> np.ndarray:
    return shape(x, lambda f: 1 / (1 + (f / hi) ** 4))


def modes(d: float, specs, drop: float = 0.0) -> np.ndarray:
    """specs: (فرکانس، زمان خاموشی، دامنه). drop: افت نسبی فرکانس در ابتدای ضربه."""
    t = t_axis(d)
    out = np.zeros_like(t)
    for f, tau, a in specs:
        f = f * (1 + RNG.uniform(-.02, .02))
        fi = f * (1 + drop * np.exp(-t / 0.01))
        out += a * np.exp(-t / tau) * np.sin(2 * np.pi * np.cumsum(fi) / SR + RNG.uniform(0, 6.28))
    return out


def burst(d: float, ms: float) -> np.ndarray:
    t = t_axis(d)
    return RNG.standard_normal(len(t)) * np.exp(-t / (ms / 1000))


def room(x: np.ndarray, amount: float = .12, size: float = 1.0) -> np.ndarray:
    y = x.copy()
    for dl, g in ((.009, .5), (.017, .35), (.027, .25), (.041, .16), (.063, .1)):
        k = int(dl * size * SR)
        if k < len(x):
            y[k:] += lp(x, 4000)[:-k] * g * amount * 2
    return y


def kick() -> np.ndarray:
    d = .14
    tap = band(burst(d, 3), 700, 2600) * .8
    body = modes(d, ((310, .018, .6), (720, .01, .25)))
    return room(tap + body, .08)


def clack(v: int) -> np.ndarray:
    d = .2
    base = (1420, 2310, 3480, 4900)
    sh = 1 + (v - 2) * .06
    ring = modes(d, ((base[0] * sh, .03, 1), (base[1] * sh, .02, .6), (base[2] * sh, .012, .3), (base[3] * sh, .007, .15), (640 * sh, .02, .5)))
    click = band(burst(d, 1.2), 1200, 4500) * 1.1
    return room(lp(ring * .6 + click, 5000), .1)


def ball(v: int) -> np.ndarray:
    d = .22
    f0 = 210 if v == 1 else 240
    body = modes(d, ((f0, .045, 1), (f0 * 2.3, .025, .4), (f0 * 5.1, .01, .2)), drop=.25)
    slap = lp(burst(d, 4), 1600) * .6
    return room(body + slap, .1)


def wall() -> np.ndarray:
    d = .32
    thud = modes(d, ((105, .07, 1), (178, .05, .6), (310, .03, .4), (520, .018, .25)), drop=.15)
    knock = lp(burst(d, 10), 900) * .9
    t = t_axis(d)
    rattle = np.zeros_like(t)
    for k, g in enumerate((.35, .2, .12)):
        s = int((.016 + k * .019) * SR)
        r = band(burst(.05, 4), 1500, 3200) * g
        rattle[s:s + len(r)] += r[: len(rattle) - s]
    return room(thud + knock + rattle, .16)


def post() -> np.ndarray:
    d = 1.1
    ping = modes(d, ((1320, .32, 1), (2215, .2, .45), (3505, .13, .4), (4870, .08, .2), (660, .25, .3)))
    click = band(burst(d, 1.5), 2500, 9000) * .8
    return room(ping * .7 + click, .2, 1.4)


def whistle() -> np.ndarray:
    def blow(d: float) -> np.ndarray:
        t = t_axis(d)
        # ساچمه داخل سوت: لرزش نامنظم ۳۵ تا ۴۵ هرتز در فرکانس و دامنه
        rate = 40 + np.cumsum(RNG.standard_normal(len(t))) * .002
        ph = 2 * np.pi * np.cumsum(rate) / SR
        trill = np.sin(ph) + .3 * np.sin(2 * ph + 1)
        f = 3150 + 110 * trill
        car = 2 * np.pi * np.cumsum(f) / SR
        tone = np.sin(car) + .18 * np.sin(2 * car) + .05 * np.sin(3 * car)
        am = 1 + .3 * trill
        air = band(RNG.standard_normal(len(t)), 2700, 3700) * .35
        env = np.clip(t / .025, 0, 1) * np.clip((d - t) / .06, 0, 1)
        return (tone * am * .8 + air) * env
    gap = np.zeros(int(.1 * SR))
    return room(np.concatenate([blow(.17), gap, blow(.72)]), .25, 2.5)


def voices(d: float, n: int, loud: float, rng: np.random.Generator) -> np.ndarray:
    """جمعیت: n صدای انسانی (موج اره ای با گام لرزان از فیلتر واکه ها) با هجاهای تصادفی."""
    t = t_axis(d)
    out = np.zeros_like(t)
    vowels = ((730, 1090, 2440), (570, 840, 2410), (300, 870, 2240), (660, 1720, 2410), (520, 1190, 2390))
    for _ in range(n):
        f0 = rng.uniform(110, 290) * (1 + loud * .25)
        glide = 1 + .06 * np.sin(2 * np.pi * rng.uniform(.2, .7) * t + rng.uniform(0, 6)) + loud * .12 * np.clip(t / .5, 0, 1)
        ph = np.cumsum(f0 * glide) / SR
        saw = 2 * (ph % 1) - 1
        fa, fb, fc = vowels[rng.integers(len(vowels))]
        v = shape(saw, lambda f: np.exp(-.5 * ((f - fa) / 90) ** 2) + .6 * np.exp(-.5 * ((f - fb) / 120) ** 2) + .25 * np.exp(-.5 * ((f - fc) / 200) ** 2))
        syl = rng.uniform(2.5, 5.5)
        gate = np.clip(np.sin(2 * np.pi * syl * t + rng.uniform(0, 6)) * 1.6 + loud * 2.2, 0, 1)
        out += v * gate * rng.uniform(.4, 1)
    return out / np.sqrt(n)


def goal() -> np.ndarray:
    d = 2.8
    t = t_axis(d)
    rng = np.random.default_rng(7)
    roar = voices(d, 48, 1.0, rng) * 1.2
    bed = band(rng.standard_normal(len(t)), 250, 3000) * .55
    swell = np.clip(t / .35, 0, 1) ** 1.4 * np.where(t > 1.9, np.exp(-(t - 1.9) / .5), 1.0)
    return room((roar + bed) * swell, .3, 2.2)


def crowd() -> np.ndarray:
    d, x = 8.0, .8
    t = t_axis(d + x)
    rng = np.random.default_rng(11)
    babble = voices(d + x, 40, 0.0, rng) * .9
    bed = lp(band(rng.standard_normal(len(t)), 150, 2500), 1800) * .6
    y = room(babble + bed, .3, 2.2)
    # حلقه بی درز: انتها روی ابتدا محو می شود
    k = int(x * SR)
    fade = np.linspace(0, 1, k)
    y[:k] = y[:k] * fade + y[-k:] * (1 - fade)
    return y[: int(d * SR)]


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    save("fb_kick", kick())
    for v in (1, 2, 3):
        save(f"fb_clack{v}", clack(v))
    for v in (1, 2):
        save(f"fb_ball{v}", ball(v))
    save("fb_wall", wall())
    save("fb_post", post())
    save("fb_whistle", whistle())
    save("fb_goal", goal())
    save("fb_crowd", crowd())
    old = os.path.join(OUT, "fb_clack.mp3")
    if os.path.exists(old):
        os.remove(old)


if __name__ == "__main__":
    main()
