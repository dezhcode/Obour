"""ترجمه های ربات و مینی اپ.

هر زبان یک ماژول دارد (en.py، ru.py، zh.py) با دو دیکشنری:
  TEXTS    نام ثابت texts.py → متن ترجمه شده (همان جای گذاری های {..})
  PHRASES  عبارت فارسی کوتاه (دکمه ها، پاپ آپ ها) → ترجمه

فارسی زبان پایه است و ماژول ندارد: هر چه در ترجمه نباشد فارسی می ماند.
"""
from __future__ import annotations

import importlib
from functools import lru_cache


@lru_cache(maxsize=None)
def catalog(lang: str) -> dict:
    try:
        mod = importlib.import_module(f"app.locales.{lang}")
    except ModuleNotFoundError:
        return {}
    return {"TEXTS": getattr(mod, "TEXTS", {}), "PHRASES": getattr(mod, "PHRASES", {})}
