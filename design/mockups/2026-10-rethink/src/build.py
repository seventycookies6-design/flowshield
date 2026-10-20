"""Builds the 2026-10 rethink mockups.

    python design/mockups/2026-10-rethink/src/build.py [a-dial b-ledger ...]

Writes one self-contained HTML file per screen into each direction's folder,
renders each to a 1280x860 PNG with Playwright (Chromium), checks the PNG size
and that Inter loaded, and writes the index.html contact sheet.
"""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
sys.path.insert(0, str(HERE))

import dir_a  # noqa: E402
import dir_b  # noqa: E402
import dir_c  # noqa: E402

DIRECTIONS = [dir_a, dir_b, dir_c]


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def build(only=None):
    files = []
    for d in DIRECTIONS:
        if only and d.SLUG not in only:
            continue
        folder = OUT / d.SLUG
        folder.mkdir(exist_ok=True)
        for slug, _label, fn in d.SCREENS:
            p = folder / f"{slug}.html"
            p.write_text(fn(), encoding="utf-8")
            files.append(p)
    return files


def render(files):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)  # never a visible window
        page = browser.new_page(viewport={"width": 1280, "height": 860}, device_scale_factor=1)
        for f in files:
            page.goto(f.as_uri())
            page.evaluate("document.fonts.ready")
            if not page.evaluate("document.fonts.check('600 16px Inter')"):
                raise SystemExit(f"Inter did not load for {f}")
            # flag anything that overflows its box horizontally (clipped text)
            over = page.evaluate("""() => [...document.querySelectorAll('body *')]
                .filter(e => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflow !== 'visible')
                .filter(e => !e.classList.contains('sr'))
                .map(e => e.className || e.tagName).slice(0, 5)""")
            # and anything that runs past the bottom of the window (clipped vertically)
            low = page.evaluate("""() => [...document.querySelectorAll('body *')]
                .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.bottom > 861; })
                .map(e => e.className || e.tagName).slice(0, 5)""")
            over = over + low
            png = f.with_suffix(".png")
            page.screenshot(path=str(png), full_page=False)
            w, h = png_size(png)
            assert (w, h) == (1280, 860), f"{png} is {w}x{h}"
            print(f"ok  {png.relative_to(OUT)}  {w}x{h}" + (f"  overflow: {over}" if over else ""))
        browser.close()


def contact_sheet():
    sections = []
    for d in DIRECTIONS:
        cards = "".join(
            f'<figure><a href="{d.SLUG}/{slug}.png"><img src="{d.SLUG}/{slug}.png" alt="{d.NAME}: {label}" loading="lazy"></a>'
            f'<figcaption><b>{label}</b> <a href="{d.SLUG}/{slug}.html">HTML</a></figcaption></figure>'
            for slug, label, _ in d.SCREENS)
        sections.append(f'<section><h2>{d.NAME}</h2><p>{d.SUMMARY}</p><div class="grid">{cards}</div></section>')
    html = f"""<!doctype html>
<html lang="en-US"><head><meta charset="utf-8"><title>Basalt design rethink, October 2026: contact sheet</title>
<style>
@font-face{{font-family:Inter;src:url("../../../Website/fonts/InterVariable.woff2") format("woff2");font-weight:100 900}}
body{{margin:0;padding:40px 48px 64px;background:#141517;color:#EDEDEB;font:14px/21px Inter,"Segoe UI",sans-serif}}
h1{{font-size:28px;line-height:34px;font-weight:600;letter-spacing:-.02em;margin:0 0 6px}}
.lede{{color:#AEB0B3;max-width:820px;margin:0 0 32px}}
section{{margin-top:40px;border-top:1px solid rgba(237,237,235,.12);padding-top:24px}}
h2{{font-size:20px;line-height:28px;font-weight:600;margin:0 0 4px}}
section>p{{color:#AEB0B3;max-width:900px;margin:0 0 18px}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px 20px}}
figure{{margin:0}}
img{{width:100%;display:block;border-radius:8px;border:1px solid rgba(237,237,235,.12)}}
figcaption{{margin-top:8px;display:flex;justify-content:space-between;color:#AEB0B3}}
figcaption b{{color:#EDEDEB;font-weight:600}}
a{{color:#AEB0B3}}
</style></head><body>
<h1>Basalt design rethink, October 2026</h1>
<p class="lede">Three directions for issue #368, each shown on the same five screens with the same sample data, plus Today at rest in the light theme. Every image is a 1280&times;860 render of the HTML file beside it. Rationale, hierarchy changes, new tokens and the recommendation are in <a href="README.md">README.md</a>.</p>
{''.join(sections)}
</body></html>
"""
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print("ok  index.html")


if __name__ == "__main__":
    only = set(sys.argv[1:]) or None
    files = build(only)
    render(files)
    contact_sheet()
