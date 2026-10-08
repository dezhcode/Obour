"""tokens.json را به tokens.css تبدیل می کند (یک منبع برای همه مقادیر).

    python game_club/design/build_tokens.py            # فونت ها با آدرس فایل
    python game_club/design/build_tokens.py --inline   # فونت ها داخل CSS (برای آرتیفکت)
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATIC = HERE.parent / "webapp" / "static"


def build(inline: bool = False) -> str:
    t = json.loads((HERE / "tokens.json").read_text(encoding="utf-8"))
    out = [f"/* {t['name']} — generated from tokens.json */"]
    for f in t["type"]["fonts"]:
        path = STATIC / f["file"]
        src = (f"data:font/woff2;base64,{base64.b64encode(path.read_bytes()).decode()}"
               if inline else f["file"])
        out.append(f"@font-face{{font-family:\"{f['family']}\";src:url(\"{src}\") format(\"woff2\");"
                   f"font-weight:{f['weight']};font-style:normal;font-display:swap}}")
    first = t["color"]["themes"][0]["id"]
    vars_ = []
    for tok in t["color"]["tokens"]:
        v = tok["value"] if isinstance(tok["value"], str) else tok["value"][first]
        vars_.append(f"--{tok['name']}:{v}")
    for fam in ("shadow", "spacing", "radius", "zIndex"):
        for tok in t.get(fam, {}).get("tokens", []):
            vars_.append(f"--{tok['name']}:{tok['value']}")
    for k, v in t["type"]["families"].items():
        vars_.append(f"--font-{k}:{v}")
    out.append(":root{" + ";".join(vars_) + "}")
    for g in t["type"]["groups"]:
        fam = t["type"]["families"][g["family"]]
        for s in g["styles"]:
            out.append(f".{s['name']}{{font-family:{fam};font-size:{s['fontSize']};"
                       f"line-height:{s['lineHeight']};font-weight:{s['fontWeight']}}}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    inline = "--inline" in sys.argv
    dest = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else STATIC / "tokens.css"
    dest.write_text(build(inline), encoding="utf-8")
    print(dest, dest.stat().st_size)
