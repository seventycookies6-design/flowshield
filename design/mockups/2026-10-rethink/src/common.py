"""Shared pieces for the 2026-10 rethink mockups: tokens, sample data, icons,
glyphs and small chart builders. Everything here returns plain strings of
HTML/SVG so each mockup file stays self-contained (no network, no framework).
"""
import math
from datetime import date, timedelta

# Path from design/mockups/2026-10-rethink/<direction>/ back to the repo's Inter.
FONT_URL = "../../../../Website/fonts/InterVariable.woff2"

# ---------------------------------------------------------------- tokens
# Copied from design/tokens.json. New tokens proposed by this rethink are
# marked NEW; README.md lists them with measured contrast.
TOKENS = {
    "dark": {
        "bg": "#141517", "bg-soft": "#191A1C", "surface": "#1F2022", "surface-2": "#27292B",
        "text": "#EDEDEB", "text-muted": "#AEB0B3", "text-faint": "#909398",
        "primary": "#3AA892", "primary-hover": "#4FBEA7", "primary-ink": "#0B1F1B",
        "border": "rgba(237,237,235,.12)", "border-strong": "rgba(237,237,235,.22)",
        "track": "rgba(237,237,235,.08)", "primary-soft": "rgba(58,168,146,.20)",
        "ok": "#5EC987", "warn": "#E0B35A", "danger": "#EF7A88",
        "focus-ring": "rgba(58,168,146,.5)",
        # NEW
        "backdrop": "#1E1F22",
        "heat-1": "#223F39", "heat-2": "#265A4F", "heat-3": "#2B7466", "heat-4": "#4FBEA7",
        "heat-ink-0": "#AEB0B3", "heat-ink-1": "#EDEDEB", "heat-ink-2": "#EDEDEB", "heat-ink-3": "#EDEDEB", "heat-ink-4": "#0B1F1B",
        "tick": "#909398", "tick-dim": "#3A3C3F",
    },
    "light": {
        "bg": "#ECEBE7", "bg-soft": "#E2E1DC", "surface": "#F7F6F3", "surface-2": "#FCFBF9",
        "text": "#1C1D1F", "text-muted": "#54565A", "text-faint": "#606266",
        "primary": "#0C6B5C", "primary-hover": "#095548", "primary-ink": "#F7F6F3",
        "border": "rgba(28,29,31,.12)", "border-strong": "rgba(28,29,31,.22)",
        "track": "rgba(28,29,31,.08)", "primary-soft": "rgba(12,107,92,.12)",
        "ok": "#276A3E", "warn": "#7A5413", "danger": "#A3334A",
        "focus-ring": "rgba(12,107,92,.45)",
        # NEW
        "backdrop": "#E3E2DD",
        "heat-1": "#D3E3DD", "heat-2": "#9CC5BA", "heat-3": "#2C7D6E", "heat-4": "#0C5C4F",
        "heat-ink-0": "#54565A", "heat-ink-1": "#1C1D1F", "heat-ink-2": "#1C1D1F", "heat-ink-3": "#F7F6F3", "heat-ink-4": "#F7F6F3",
        "tick": "#606266", "tick-dim": "#C9C8C3",
    },
}


def css_vars(theme):
    return ":root{" + "".join(f"--{k}:{v};" for k, v in TOKENS[theme].items()) + "}"


BASE_CSS = """
@font-face{font-family:"Inter";src:url("%s") format("woff2");font-weight:100 900;font-display:block}
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1280px;height:860px;overflow:hidden}
body{font-family:"Inter","Segoe UI Variable","Segoe UI",system-ui,sans-serif;font-size:14px;line-height:21px;
  color:var(--text);background:var(--bg);-webkit-font-smoothing:antialiased;font-optical-sizing:auto}
button{font:inherit;color:inherit;background:none;border:0;cursor:pointer}
input{font:inherit;color:inherit}
.num{font-variant-numeric:tabular-nums}
.mono{font-family:"Cascadia Mono",Consolas,monospace}
.muted{color:var(--text-muted)} .faint{color:var(--text-faint)}
svg{display:block}
.ico{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round;flex:none}
html[data-theme=dark]{--field:var(--bg-soft)} html[data-theme=light]{--field:var(--surface-2)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
/* the keyboard focus ring, shown on one control per screen to prove it is designed */
.focus{outline:2px solid var(--focus-ring);outline-offset:2px}
""" % FONT_URL


def page(title, theme, css, body):
    return f"""<!doctype html>
<html lang="en-US" data-theme="{theme}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1280">
<title>{title}</title>
<style>
{css_vars(theme)}
{BASE_CSS}
{css}
</style>
</head>
<body>
{body}
</body>
</html>
"""

# ---------------------------------------------------------------- icons (Lucide outlines)
ICONS = {
    "today": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "history": '<path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    "blocked": '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
    "schedule": '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/>',
    "settings": '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "chev-r": '<path d="m9 18 6-6-6-6"/>',
    "chev-d": '<path d="m6 9 6 6 6-6"/>',
    "chev-u": '<path d="m18 15-6-6-6 6"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "key": '<path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z"/><circle cx="16.5" cy="7.5" r=".5"/>',
    "lock": '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    "more": '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
    "monitor": '<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>',
    "milestone": '<circle cx="12" cy="8" r="6"/><path d="M15.477 12.89 17 22l-5-3-5 3 1.523-9.11"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
}


def ic(name, size=20, cls="ico", sw=None):
    style = f' style="stroke-width:{sw}"' if sw else ""
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'aria-hidden="true"{style}>{ICONS[name]}</svg>')


def caption_buttons(color="currentColor"):
    """Windows 11 caption buttons: minimise, maximise, close (46x32 each)."""
    s = f'stroke="{color}" stroke-width="1" fill="none"'
    return (
        '<div class="capbtns" aria-hidden="true">'
        f'<span><svg width="10" height="10" viewBox="0 0 10 10"><path d="M0 5.5h10" {s}/></svg></span>'
        f'<span><svg width="10" height="10" viewBox="0 0 10 10"><rect x=".5" y=".5" width="9" height="9" {s}/></svg></span>'
        f'<span><svg width="10" height="10" viewBox="0 0 10 10"><path d="M0 0l10 10M10 0L0 10" {s}/></svg></span>'
        '</div>')


CAPTION_CSS = """
.capbtns{margin-left:auto;display:flex;height:100%}
.capbtns span{width:46px;height:100%;display:grid;place-items:center;color:var(--text)}
"""

# ---------------------------------------------------------------- brand mark
# Polygons copied from design/brand/basalt-mark-on-dark.svg (do not redraw).
_MARK = [
    ("L", "46.25,25.5 53.75,32 53.75,68 46.25,61.5"),
    ("F", "53.75,32 68.75,32 68.75,68 53.75,68"),
    ("R", "68.75,32 76.25,25.5 76.25,61.5 68.75,68"),
    ("T3", "76.25,25.5 68.75,32 53.75,32 46.25,25.5 53.75,19 68.75,19"),   # back column top
    ("L", "23.75,41 31.25,47.5 31.25,74.5 23.75,68"),
    ("F", "31.25,47.5 46.25,47.5 46.25,74.5 31.25,74.5"),
    ("R", "46.25,47.5 53.75,41 53.75,68 46.25,74.5"),
    ("T2", "53.75,41 46.25,47.5 31.25,47.5 23.75,41 31.25,34.5 46.25,34.5"),  # middle column top
    ("L", "46.25,56.5 53.75,63 53.75,81 46.25,74.5"),
    ("F", "53.75,63 68.75,63 68.75,81 53.75,81"),
    ("R", "68.75,63 76.25,56.5 76.25,74.5 68.75,81"),
    ("T1", "76.25,56.5 68.75,63 53.75,63 46.25,56.5 53.75,50 68.75,50"),   # front column top
]
_FACES = {
    "dark": {"T": "#E6E6E3", "L": "#A3A6AA", "F": "#74777C", "R": "#4B4E53", "lit": "#3AA892", "ground": "#141517"},
    "light": {"T": "#8B8E93", "L": "#55585D", "F": "#36383C", "R": "#1F2023", "lit": "#0C6B5C", "ground": "#ECEBE7"},
}


def mark(height, theme="dark", lit=0, ground=None, label="Basalt"):
    """Bare Causeway mark. lit = shield level: 1 Soft, 2 Firm, 3 Sealed tops lit."""
    f = _FACES[theme]
    g = ground or f["ground"]
    w = height * 56 / 66
    lit_tops = {1: {"T1"}, 2: {"T1", "T2"}, 3: {"T1", "T2", "T3"}}.get(lit, set())
    polys = []
    for face, pts in _MARK:
        if face.startswith("T"):
            fill = f["lit"] if face in lit_tops else f["T"]
        else:
            fill = f[face]
        polys.append(f'<polygon points="{pts}" fill="{fill}"/>')
    sw = 1 if height >= 60 else 1.6
    return (f'<svg width="{w:.1f}" height="{height}" viewBox="22 17 56 66" role="img" aria-label="{label}">'
            f'<g stroke="{g}" stroke-width="{sw}" stroke-linejoin="round">{"".join(polys)}</g></svg>')


# ---------------------------------------------------------------- shield glyphs (DESIGN_SYSTEM.md §6)
_SHIELD = "M12,3 L19.5,6 L19.5,11.5 C19.5,16.2 16.3,19.8 12,21 C7.7,19.8 4.5,16.2 4.5,11.5 L4.5,6 Z"


def shield_glyph(level, size=20):
    if level == 1:
        return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true">'
                f'<path d="{_SHIELD}" fill="none" stroke="var(--text-muted)" stroke-width="1.75" stroke-linejoin="round"/>'
                f'<path d="M8.5,11.5 L15.5,11.5" stroke="var(--text-muted)" stroke-width="1.75" stroke-linecap="round"/></svg>')
    if level == 2:
        return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true">'
                f'<path d="{_SHIELD}" fill="none" stroke="var(--primary)" stroke-width="1.75" stroke-linejoin="round"/>'
                f'<path d="M8.5,10.2 L15.5,10.2 M8.5,13.4 L15.5,13.4" stroke="var(--primary)" stroke-width="1.75" stroke-linecap="round"/></svg>')
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true">'
            f'<path d="{_SHIELD}" fill="var(--primary)"/>'
            f'<path d="M8.5,9.4 L15.5,9.4 M8.5,12 L15.5,12 M8.5,14.6 L15.5,14.6" stroke="var(--primary-ink)" stroke-width="1.75" stroke-linecap="round"/></svg>')


# ---------------------------------------------------------------- sample data (consistent everywhere)
TODAY = date(2026, 10, 16)  # a Friday
START30 = TODAY - timedelta(days=29)  # Thu 17 Sep
MINUTES30 = [0, 25, 0, 0, 45, 0, 25, 45, 0, 0, 50, 45, 70, 0,      # 17 Sep - 30 Sep
             25, 0, 90, 0, 45, 90, 45, 0, 25, 50, 25,                # 1 Oct - 11 Oct
             45, 25, 34, 25, 45]                                     # 12 Oct - 16 Oct (174 min = 2.9 h)
assert len(MINUTES30) == 30 and sum(MINUTES30[-5:]) == 174


def momentum_series():
    """A plausible 30-day momentum line ending at its peak of 186."""
    m, out = 10.0, []
    for i, mins in enumerate(MINUTES30):
        d = START30 + timedelta(days=i)
        if d == date(2026, 10, 14):        # the sprint ended early: decays, doesn't reset
            m = m * 0.85 - 2
        m += mins / 4.0
        m *= 0.985
        out.append(m)
    k = 186 / out[-1]
    return [round(v * k) for v in out]


MOMENTUM = momentum_series()

TEMPLATES = [  # from DesktopApp/Models/StudyTemplate.cs
    {"name": "Homework evening", "min": 45, "shield": 2, "cycle": 3, "brk": 10},
    {"name": "Exam prep", "min": 90, "shield": 3, "cycle": 0, "brk": 5},
    {"name": "Light study", "min": 25, "shield": 1, "cycle": 0, "brk": 5},
]
SHIELD_NAME = {1: "Soft", 2: "Firm", 3: "Sealed"}
SHIELD_ROMAN = {1: "I", 2: "II", 3: "III"}
SHIELD_PROMISE = {  # README.md wording
    1: "A full-screen notice on its own screen; the blocked app keeps running unless you close it.",
    2: "Blocked apps are warned to save their work, then closed.",
    3: "Warned, then closed, and the blocklist locks until the sprint ends.",
}


def template_spec(t):
    cyc = f" · {t['cycle']} sprints" if t["cycle"] else ""
    return f"{t['min']} min · {SHIELD_NAME[t['shield']]}{cyc}"


BLOCKED = [
    {"name": "Discord", "cat": "Chat", "proc": "discord.exe", "stopped": 14},
    {"name": "Steam", "cat": "Games & launchers", "proc": "steam.exe", "stopped": 9},
    {"name": "Epic Games Launcher", "cat": "Games & launchers", "proc": "epicgameslauncher.exe", "stopped": 0},
]
PICKER = [
    {"name": "Spotify", "src": "Running now", "added": False},
    {"name": "Minecraft Launcher", "src": "Installed", "added": False},
    {"name": "Roblox", "src": "Suggested · Games & launchers", "added": False},
    {"name": "WhatsApp", "src": "Suggested · Chat", "added": False},
    {"name": "Steam", "src": "Installed", "added": True},
]
SPRINTS = [  # newest first
    {"when": "Fri 16 Oct · 15:20", "len": "45 min", "shield": 2, "out": "Completed",
     "intent": "Draft the middle section of the essay", "journal": "Middle section drafted. Conclusion next."},
    {"when": "Thu 15 Oct · 17:05", "len": "25 min", "shield": 1, "out": "Completed",
     "intent": "Chemistry flashcards", "journal": "Got through the chapter 4 cards."},
    {"when": "Wed 14 Oct · 20:40", "len": "25 min", "shield": 1, "out": "Completed",
     "intent": "Read the history chapter", "journal": "Twelve pages, notes on the treaty."},
    {"when": "Wed 14 Oct · 19:50", "len": "45 min", "shield": 2, "out": "Ended early", "done": 9,
     "intent": "", "journal": ""},
    {"when": "Tue 13 Oct · 18:30", "len": "25 min", "shield": 1, "out": "Completed",
     "intent": "Spanish vocabulary", "journal": "Verb list done, forty words."},
    {"when": "Mon 12 Oct · 19:10", "len": "45 min", "shield": 2, "out": "Completed",
     "intent": "Maths problem set 3", "journal": "Questions 1 to 8. Question 9 tomorrow."},
]
MILESTONES = [  # titles from DesktopApp/Models/Milestones.cs
    {"title": "Seven days in a row", "when": "15 Oct", "text": "Seven days in a row with a finished focus day."},
    {"title": "Ten hours focused", "when": "10 Oct", "text": "Ten hours of sprints that really ran."},
    {"title": "Momentum at 100", "when": "6 Oct", "text": "Finished sprints have built your momentum to 100."},
    {"title": "First Sealed sprint", "when": "3 Oct", "text": "You finished a sprint on Sealed, the strictest shield."},
]
WEEK = [("Mon", 45), ("Tue", 25), ("Wed", 34), ("Thu", 25), ("Fri", 45), ("Sat", None), ("Sun", None)]


def heat_level(mins):
    if mins <= 0:
        return 0
    if mins <= 25:
        return 1
    if mins <= 45:
        return 2
    if mins <= 60:
        return 3
    return 4


HEAT_LEGEND = [(0, "0"), (1, "1–25"), (2, "26–45"), (3, "46–60"), (4, "60+")]


def heat_fill(level):
    return "var(--track)" if level == 0 else f"var(--heat-{level})"


# ---------------------------------------------------------------- charts
def trend_chart(w, h, values=None, pad_l=30, pad_b=22, label_peak=True, grid=(0, 100, 200), stroke=2):
    """Momentum line with labelled axes. y = points, x = the last 30 days."""
    values = values or MOMENTUM
    ymax = grid[-1]
    pw, ph = w - pad_l - 6, h - pad_b - 8
    def X(i): return pad_l + pw * i / (len(values) - 1)
    def Y(v): return 8 + ph * (1 - v / ymax)
    parts = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
             f'aria-label="Momentum over the last 30 days, rising to a peak of {values[-1]} today">']
    for g in grid:
        y = Y(g)
        parts.append(f'<line x1="{pad_l}" x2="{w-6}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--border)" stroke-width="1"/>')
        parts.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="var(--text-faint)" class="num">{g}</text>')
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(values))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="var(--primary)" stroke-width="{stroke}" stroke-linejoin="round" stroke-linecap="round"/>')
    lx, ly = X(len(values) - 1), Y(values[-1])
    parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="var(--primary)"/>')
    for i, lab in ((0, "17 Sep"), (14, "1 Oct"), (29, "16 Oct")):
        anchor = "start" if i == 0 else ("end" if i == 29 else "middle")
        parts.append(f'<text x="{X(i):.1f}" y="{h-4}" text-anchor="{anchor}" font-size="11" fill="var(--text-faint)">{lab}</text>')
    parts.append("</svg>")
    return "".join(parts)


def week_bars(w, h, bar_w=28, grid=(0, 30, 60), today_idx=4, value_labels=True, cap=False):
    """Minutes per day this week, Monday to Sunday, with a labelled y axis."""
    pad_l, pad_b, pad_t = 34, 24, 18
    pw, ph = w - pad_l - 4, h - pad_b - pad_t
    ymax = grid[-1]
    def Y(v): return pad_t + ph * (1 - v / ymax)
    parts = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
             f'aria-label="Minutes focused each day this week: Monday 45, Tuesday 25, Wednesday 34, Thursday 25, Friday 45">']
    for g in grid:
        y = Y(g)
        parts.append(f'<line x1="{pad_l}" x2="{w-4}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--border)"/>')
        parts.append(f'<text x="{pad_l-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="var(--text-faint)" class="num">{g}</text>')
    parts.append(f'<text x="{pad_l-8}" y="{pad_t-8}" text-anchor="end" font-size="11" fill="var(--text-faint)">min</text>')
    step = pw / 7
    for i, (d, v) in enumerate(WEEK):
        cx = pad_l + step * i + step / 2
        colour = "var(--text)" if i == today_idx else "var(--text-faint)"
        weight = "600" if i == today_idx else "400"
        parts.append(f'<text x="{cx:.1f}" y="{h-5}" text-anchor="middle" font-size="12" fill="{colour}" font-weight="{weight}">{d}</text>')
        if v is None:
            parts.append(f'<line x1="{cx-bar_w/2+4:.1f}" x2="{cx+bar_w/2-4:.1f}" y1="{Y(0)-1:.1f}" y2="{Y(0)-1:.1f}" stroke="var(--border-strong)" stroke-width="2" stroke-linecap="round"/>')
            continue
        y = Y(v)
        x = cx - bar_w / 2
        if cap:
            # a basalt column seen from the front: a flat bar under a lighter, squashed hexagon top
            top_h = 7
            parts.append(f'<rect x="{x:.1f}" y="{y+top_h/2:.1f}" width="{bar_w}" height="{Y(0)-y-top_h/2:.1f}" fill="var(--heat-3)"/>')
            parts.append(f'<polygon points="{x:.1f},{y+top_h/2:.1f} {x+bar_w*.25:.1f},{y:.1f} {x+bar_w*.75:.1f},{y:.1f} {x+bar_w:.1f},{y+top_h/2:.1f} {x+bar_w*.75:.1f},{y+top_h:.1f} {x+bar_w*.25:.1f},{y+top_h:.1f}" fill="var(--heat-4)"/>')
        else:
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{Y(0)-y:.1f}" rx="3" fill="var(--primary)"/>')
        if value_labels:
            parts.append(f'<text x="{cx:.1f}" y="{y-6:.1f}" text-anchor="middle" font-size="11" fill="var(--text-muted)" class="num">{v}</text>')
    parts.append("</svg>")
    return "".join(parts)


def heat_calendar(cell=30, gap=6, show_dates=True, radius=6):
    """30 days as a Monday-first calendar: weekday labels on top, one row per week."""
    first_monday = START30 - timedelta(days=START30.weekday())
    weeks = ((TODAY - first_monday).days // 7) + 1
    lab_h = 22
    w = 7 * cell + 6 * gap
    h = lab_h + weeks * cell + (weeks - 1) * gap
    parts = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
             f'aria-label="Focus minutes per day for the last 30 days, 17 September to 16 October">']
    for i, d in enumerate("MTWTFSS"):
        full = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i]
        parts.append(f'<text x="{i*(cell+gap)+cell/2:.1f}" y="13" text-anchor="middle" font-size="11" fill="var(--text-faint)">{full}</text>')
    for k in range(weeks * 7):
        d = first_monday + timedelta(days=k)
        r, c = divmod(k, 7)
        x, y = c * (cell + gap), lab_h + r * (cell + gap)
        if d < START30 or d > TODAY:
            continue
        mins = MINUTES30[(d - START30).days]
        lvl = heat_level(mins)
        stroke = ' stroke="var(--text)" stroke-width="1.5"' if d == TODAY else ""
        parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="{radius}" fill="{heat_fill(lvl)}"{stroke}>'
                     f'<title>{d:%a %d %b}: {mins} min</title></rect>')
        if show_dates:
            col = f"var(--heat-ink-{lvl})"
            parts.append(f'<text x="{x+cell/2:.1f}" y="{y+cell/2+4:.1f}" text-anchor="middle" font-size="11" fill="{col}" class="num">{d.day}</text>')
    parts.append("</svg>")
    return "".join(parts)


def heat_legend(sw=14, radius=3, hexes=False):
    items = []
    for lvl, lab in HEAT_LEGEND:
        if hexes:
            sh = (f'<svg width="{sw}" height="{sw}" viewBox="0 0 16 16" aria-hidden="true">'
                  f'<polygon points="4,1.5 12,1.5 15.5,8 12,14.5 4,14.5 .5,8" fill="{heat_fill(lvl)}"/></svg>')
        else:
            sh = f'<span style="display:inline-block;width:{sw}px;height:{sw}px;border-radius:{radius}px;background:{heat_fill(lvl)}"></span>'
        items.append(f'<span class="lg">{sh}<span>{lab}</span></span>')
    return ('<div class="legend" aria-label="Legend: minutes focused per day"><span class="lg faint">Minutes</span>'
            + "".join(items) + '</div>')


LEGEND_CSS = """
.legend{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--text-muted);flex-wrap:wrap}
.legend .lg{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
"""


def monogram(name, size=32, radius=8, fs=14):
    return (f'<span class="mono-tile" style="width:{size}px;height:{size}px;border-radius:{radius}px;font-size:{fs}px" '
            f'aria-hidden="true">{name[0]}</span>')


MONO_CSS = """
.mono-tile{display:inline-grid;place-items:center;flex:none;background:var(--surface-2);border:1px solid var(--border);
  color:var(--text-muted);font-weight:600;font-family:"Inter",sans-serif}
"""


def switch(on=True, label=""):
    return (f'<span class="sw {"on" if on else ""}" role="switch" aria-checked="{str(on).lower()}" aria-label="{label}">'
            '<span></span></span>')


SWITCH_CSS = """
.sw{width:40px;height:22px;border-radius:11px;border:1.5px solid var(--border-strong);position:relative;flex:none;display:inline-block}
.sw span{position:absolute;top:3px;left:3px;width:13px;height:13px;border-radius:50%;background:var(--text-muted)}
.sw.on{background:var(--primary);border-color:var(--primary)}
.sw.on span{left:21px;background:var(--primary-ink)}
"""


def sprint_title(s):
    """The bold line of a sprint row: its intention, or for an early end a neutral statement."""
    if s["out"] != "Completed":
        return f"Ended early after {s['done']} minutes"
    return s["intent"] or "No intention"


def sprint_meta(s):
    """When, length and shield; the outcome is only mentioned when it isn't 'completed'."""
    return f"{s['when']} · {s['len']} · {SHIELD_NAME[s['shield']]}"
