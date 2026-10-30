"""راهنمای مینی اپ (game_club/webapp/help.html) → JSON برای صفحهٔ راهنمای برنامهٔ نیتیو.

usage: python -I native-app/tools/gen_help.py   (از ریشهٔ مخزن)
خروجی: native-app/android/app/src/main/res/raw/help.json
[{id, title, lead: [خط], steps: [{icon, title, lines: [خط]}]}]
"""
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "game_club", "webapp", "help.html")
OUT = os.path.join(ROOT, "native-app", "android", "app", "src", "main", "res", "raw", "help.json")


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def lines(s: str) -> list[str]:
    return [x for x in (clean(p) for p in re.split(r"<br\s*/?>", s)) if x]


def main():
    t = open(SRC, encoding="utf-8").read()
    main_ = t[t.index("<main"):t.index("</main>")]
    out = []
    for sec in re.findall(r"<section[\s\S]*?</section>", main_):
        h = re.search(r'<h2[^>]*id="([^"]+)"[^>]*>([\s\S]*?)</h2>', sec)
        if not h:
            continue
        steps = []
        for li in re.findall(r"<li>([\s\S]*?)</li>", sec):
            ic = re.search(r'data-ic="([^"]+)"', li)
            b = re.search(r"<b>([\s\S]*?)</b>", li)
            p = re.search(r"<p>([\s\S]*?)</p>", li)
            if b or p:
                steps.append({"icon": ic.group(1) if ic else "info", "title": clean(b.group(1)) if b else "",
                              "lines": lines(p.group(1)) if p else []})
        # پاراگراف هایی که بیرون فهرست مرحله ها هستند
        body = re.sub(r"<(ol|ul)[\s\S]*?</\1>", "", sec)
        lead = [x for p in re.findall(r"<p[^>]*>([\s\S]*?)</p>", body) for x in lines(p)]
        out.append({"id": h.group(1), "title": clean(h.group(2)), "lead": lead, "steps": steps})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for s in out:
        print(s["id"], "-", len(s["lead"]), "lead,", len(s["steps"]), "steps")


if __name__ == "__main__":
    main()
