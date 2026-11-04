"""Direction C, "Causeway": material and structure. A Windows 11 shell (Mica
backdrop with a basalt-grain fallback, one content slab, settings cards), and
the Causeway mark doing real work: its lit tops are the shield level, large,
on Today. Data is drawn in the stone's own shapes: hexagon cells for the
30-day calendar and column-topped bars for the week."""
import math
from common import *

NAME = "C · Causeway"
SLUG = "c-causeway"
SUMMARY = ("Material and structure: a Windows 11 shell (Mica backdrop with a basalt-grain fallback, one content slab, settings cards) "
           "and the Causeway mark doing real work. Its lit tops are the shield level, large on Today; History uses hexagon cells and column-topped bars.")

def _grain(rgb, a):
    return ("url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'>"
            "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/>"
            f"<feColorMatrix values='0 0 0 0 {rgb}  0 0 0 0 {rgb}  0 0 0 0 {rgb}  {a} 0 0 0 0'/></filter>"
            "<rect width='100%25' height='100%25' filter='url(%23n)'/></svg>\")")


GRAIN = _grain(1, 0.10)
GRAIN_LIGHT = _grain(0, 0.08)

CSS = CAPTION_CSS + LEGEND_CSS + MONO_CSS + SWITCH_CSS + """
body{background:var(--backdrop)}
.win{height:860px;display:grid;grid-template-columns:248px 1fr;grid-template-rows:40px 1fr;background:var(--backdrop) %s}
[data-theme=light] .win{background:var(--backdrop) %s}
.tb{grid-column:1/3;display:flex;align-items:center;gap:10px;padding-left:16px;font-size:12px;color:var(--text-muted)}
.side{padding:6px 10px 16px 12px;display:flex;flex-direction:column}
.nav{display:flex;flex-direction:column;gap:2px}
.nav a{display:flex;align-items:center;gap:14px;height:40px;padding:0 12px;border-radius:6px;color:var(--text);position:relative;font-weight:400}
.nav a .ico{color:var(--text-muted)}
.nav a.on{background:var(--track);font-weight:600}
.nav a.on .ico{color:var(--text)}
.nav a.on::before{content:"";position:absolute;left:0;top:12px;bottom:12px;width:3px;border-radius:2px;background:var(--primary)}
.side.quiet .nav a{color:var(--text-faint)} .side.quiet .nav a .ico{color:var(--text-faint)}
.side.quiet .nav a.on{background:none;font-weight:400} .side.quiet .nav a.on::before{background:var(--border-strong)}
.status{margin:20px 12px 0;padding-top:16px;border-top:1px solid var(--border)}
.status .k{font-size:12px;line-height:16px;color:var(--text-muted)}
.status .v{font-size:26px;line-height:32px;font-weight:600;letter-spacing:-.02em}
.status .s{font-size:13px;color:var(--text-muted)}
.status .s b{color:var(--text);font-weight:600}
.trial{margin-top:auto;padding:14px 12px 4px;font-size:13px;color:var(--text-muted)}
.trial .btn{margin-top:10px;width:100%%}
.slab{background:var(--bg);border-top-left-radius:10px;border-top:1px solid var(--border);border-left:1px solid var(--border);
  padding:28px 40px 24px;min-height:0;overflow:hidden;display:flex;flex-direction:column}
[data-theme=light] .slab{background:var(--surface)}
h1{font-size:28px;line-height:34px;font-weight:600;letter-spacing:-.02em}
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px}
[data-theme=light] .card{background:var(--surface-2)}
.lbl{display:block;font-size:13px;line-height:18px;color:var(--text-muted);font-weight:500;margin-bottom:8px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:36px;padding:0 16px;border-radius:6px;font-weight:600}
.btn.primary{background:var(--primary);color:var(--primary-ink)}
.btn.primary.big{height:48px;font-size:15px;padding:0 32px}
.btn.secondary{background:var(--surface-2);border:1px solid var(--border-strong)}
.combo{display:flex;align-items:center;justify-content:space-between;height:40px;padding:0 12px;border-radius:6px;background:var(--surface-2);border:1px solid var(--border-strong);border-bottom-color:var(--text-faint);font-weight:500}
.combo .ico{width:16px;height:16px;color:var(--text-faint)}
.field{height:40px;border-radius:6px;background:var(--field);border:1px solid var(--border-strong);border-bottom:2px solid var(--text-faint);padding:0 12px;display:flex;align-items:center;color:var(--text-faint)}
""" % (GRAIN, GRAIN_LIGHT)


def chrome(active, body, theme="dark", quiet=False, trial=True, status=True):
    nav = [("today", "Today"), ("history", "History"), ("blocked", "Blocked apps"),
           ("schedule", "Schedule"), ("settings", "Settings")]
    links = "".join(f'<a class="{"on" if k == active else ""}">{ic(k)}<span>{t}</span></a>' for k, t in nav)
    st = ('<div class="status"><div class="k">Momentum</div><div class="v num">186</div>'
          '<div class="s">Streak <b class="num">8 days</b></div></div>') if status else ""
    tr = ('<div class="trial">Free trial · 5 days left<button class="btn secondary">Buy Basalt · $4.99</button></div>') if trial else ""
    return f"""
<div class="win">
  <div class="tb">{mark(16, theme, ground="var(--backdrop)")}<span>Basalt</span>{caption_buttons()}</div>
  <aside class="side{' quiet' if quiet else ''}"><nav class="nav" aria-label="Main">{links}</nav>{st}{tr}</aside>
  <main class="slab">{body}</main>
</div>"""


SEG_CSS = """
.seg{display:flex;gap:6px}
.seg>span{flex:1;display:flex;align-items:center;justify-content:center;gap:10px;height:56px;border-radius:8px;
  background:var(--surface-2);border:1px solid var(--border-strong);color:var(--text-muted);font-weight:500}
.seg>span.on{background:var(--primary-soft);border:1.5px solid var(--primary);color:var(--text);font-weight:600}
.seg .rn{font-size:12px;color:var(--text-faint)}
"""


# ---------------------------------------------------------------- Today at rest
def today_rest(theme="dark"):
    tiles = ""
    for i, t in enumerate(TEMPLATES):
        on = i == 0
        cyc = f"{t['cycle']} sprints · {t['brk']} min breaks" if t["cycle"] else "One sprint"
        tiles += (f'<button class="tile{" on" if on else ""}" aria-pressed="{str(on).lower()}">{mark(34, theme, lit=t["shield"], ground="var(--tile-ground)", label=SHIELD_NAME[t["shield"]] + " shield")}'
                  f'<span><b>{t["name"]}</b><span class="num">{t["min"]} min · {SHIELD_NAME[t["shield"]]}</span><span class="num">{cyc}</span></span></button>')
    seg = "".join(f'<span class="{"on" if l == 2 else ""}">{mark(30, theme, lit=l, ground="var(--seg-ground-" + ("on" if l == 2 else "off") + ")", label="")}'
                  f'<span>{SHIELD_NAME[l]}</span><span class="rn">{SHIELD_ROMAN[l]}</span></span>' for l in (1, 2, 3))
    body = f"""
<h1>Today</h1>
<span class="lbl" style="margin-top:20px">Start from a template</span>
<div class="tiles">{tiles}</div>
<section class="card hero" aria-label="Next sprint">
  <div class="art">{mark(176, theme, lit=2, ground="var(--hero-ground)", label="Causeway mark showing the Firm shield: two columns lit")}</div>
  <div class="ctl">
    <div class="time num">45:00</div>
    <div class="sname"><b>Shield II · Firm</b><span class="muted">{SHIELD_PROMISE[2]}</span></div>
    <div class="seg" role="radiogroup" aria-label="Shield">{seg}</div>
  </div>
</section>
<div class="row3">
  <div><span class="lbl">Sprint length</span><div class="combo"><span class="num">45 minutes</span>{ic("chev-d")}</div></div>
  <div><span class="lbl">Blocklist</span><div class="combo"><span>Default <span class="faint">· 3 apps</span></span>{ic("chev-d")}</div></div>
  <div><span class="lbl">Cycle</span><div class="combo"><span class="num">3 sprints <span class="faint">· 10 min breaks</span></span>{ic("chev-d")}</div></div>
</div>
<div class="go">
  <div class="int"><span class="lbl">Intention <span class="faint">(optional)</span></span><div class="field focus">Shown on the timer and again when the sprint ends</div></div>
  <button class="btn primary big">Start sprint</button>
</div>"""
    css = CSS + SEG_CSS + """
:root{--tile-ground:var(--surface-2);--hero-ground:var(--surface);--seg-ground-off:var(--surface-2);--seg-ground-on:#243B38}
[data-theme=light]{--tile-ground:var(--surface-2);--hero-ground:var(--surface-2);--seg-ground-on:#DFEAE6}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.tile{display:flex;align-items:center;gap:14px;text-align:left;padding:12px 16px;border-radius:8px;background:var(--surface-2);border:1px solid var(--border-strong)}
.tile.on{background:var(--primary-soft);border:1.5px solid var(--primary)}
.tile.on{--tile-ground:#1C3230}
[data-theme=light] .tile.on{--tile-ground:#DBE5E1}
.tile>span{display:flex;flex-direction:column}
.tile b{font-weight:600;font-size:14px;line-height:20px}
.tile span span{font-size:12px;line-height:17px;color:var(--text-muted)}
.hero{display:flex;align-items:center;gap:44px;margin-top:20px;padding:24px 32px 24px 40px}
.art{width:180px;display:flex;justify-content:center}
.ctl{flex:1}
.time{font-size:88px;line-height:88px;font-weight:600;letter-spacing:-.035em}
.sname{display:flex;flex-direction:column;margin:10px 0 18px}
.sname b{font-size:16px;line-height:22px;font-weight:600}
.sname span{font-size:13px}
.row3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:20px}
.go{display:flex;align-items:flex-end;gap:16px;margin-top:20px}
.int{flex:1}
"""
    return page("Basalt · Causeway · Today at rest", theme, css, chrome("today", body, theme))


# ---------------------------------------------------------------- Today during a Firm sprint
def today_sprint(theme="dark"):
    left = 24 + 13 / 60
    segs = ""
    for m in range(45):
        if m + 1 <= int(left):
            cls = "on"
        elif m < left:
            cls = "part"
        else:
            cls = ""
        segs += f'<i class="{cls}"></i>'
    body = f"""
<section class="run" aria-label="Sprint running">
  <div class="intent"><span class="lbl">Intention</span><p>Finish the essay conclusion</p></div>
  <div class="lock">
    {mark(232, theme, lit=2, ground="var(--bg)", label="Firm shield: two columns lit")}
    <div class="rd">
      <div class="time num">24:13</div>
      <div class="cap num">left of 45 minutes · sprint 2 of 3</div>
      <div class="segs" role="progressbar" aria-label="Minutes left" aria-valuemin="0" aria-valuemax="45" aria-valuenow="24">{segs}</div>
      <div class="sh"><b>Shield II · Firm</b><span class="muted">{SHIELD_PROMISE[2]}</span></div>
    </div>
  </div>
  <button class="btn secondary end">End sprint…</button>
</section>"""
    css = CSS + """
.run{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:0;padding-bottom:30px}
.intent{text-align:center}
.intent .lbl{margin-bottom:2px}
.intent p{font-size:20px;line-height:28px;font-weight:600}
.lock{display:flex;align-items:center;gap:56px;margin:44px 0 40px}
.rd{width:470px}
.time{font-size:132px;line-height:124px;font-weight:600;letter-spacing:-.04em;margin-left:-6px}
.cap{color:var(--text-muted);font-size:15px;margin-top:8px}
.segs{display:flex;gap:3px;margin:22px 0 22px;height:18px}
.segs i{flex:1;border-radius:2px;background:var(--track)}
.segs i.on{background:var(--primary)}
.segs i.part{background:linear-gradient(90deg,var(--primary) 22%,var(--track) 22%)}
.sh{display:flex;flex-direction:column}
.sh b{font-weight:600;font-size:16px;line-height:22px}
.sh span{font-size:13px}
.end{color:var(--text-muted)}
"""
    return page("Basalt · Causeway · Today, Firm sprint", theme, css,
                chrome("today", body, theme, quiet=True, trial=False, status=False))


# ---------------------------------------------------------------- Blocked apps
def blocked_apps(theme="dark"):
    tiles = ""
    for a in BLOCKED:
        st = (f'<span class="num">Stopped {a["stopped"]} times</span>' if a["stopped"]
              else '<span class="faint">Not needed yet</span>')
        tiles += f"""
<li class="card app">
  <div class="top">{monogram(a["name"], 40, 8, 17)}{switch(True, "Block " + a["name"])}</div>
  <b>{a["name"]}</b>
  <span class="muted">{a["cat"]}</span>
  <span class="mono faint">{a["proc"]}</span>
  <div class="bot">{st}<button class="x" aria-label="Remove {a["name"]}">{ic("x", 16)}</button></div>
</li>"""
    picks = ""
    for p in PICKER:
        act = (f'<span class="added">{ic("check", 16)}Added</span>' if p["added"]
               else '<button class="btn secondary sm">Block</button>')
        picks += f'<li>{monogram(p["name"], 32, 6, 14)}<div><b>{p["name"]}</b><span class="faint">{p["src"]}</span></div>{act}</li>'
    body = f"""
<div class="hd"><h1>Blocked apps</h1></div>
<div class="pv" role="tablist" aria-label="Blocklist profile">
  <span class="on">Default <span class="faint num">3</span></span><span>Exam week <span class="faint num">5</span></span>
  <button class="btn quiet">{ic("plus", 16)}New profile</button>
  <button class="btn quiet more" aria-label="Rename, duplicate or delete Default">{ic("more", 18)}</button>
</div>
<div class="cols">
  <section>
    <p class="muted sub">The shield stops these during a sprint on the Default profile.</p>
    <ul class="grid">{tiles}</ul>
    <div class="card web">
      {ic("globe")}
      <div><b>Websites · notice only</b><p class="muted">A notice when the tab in front names one of these. Basalt reads the tab title only and never closes your browser.</p></div>
      <button class="btn secondary">Add website</button>
    </div>
  </section>
  <aside class="card picker">
    <h2>Add an app</h2>
    <div class="field focus">{ic("search", 18)}<span>Discord, Steam, Minecraft…</span></div>
    <ul>{picks}</ul>
    <a class="manual">Add by process name or .exe path</a>
  </aside>
</div>"""
    css = CSS + """
.pv{display:flex;align-items:center;gap:4px;margin-top:16px;border-bottom:1px solid var(--border)}
.pv>span{padding:10px 14px 12px;color:var(--text-muted);font-weight:500;position:relative}
.pv>span.on{color:var(--text);font-weight:600}
.pv>span.on::after{content:"";position:absolute;left:14px;right:14px;bottom:-1px;height:3px;border-radius:2px;background:var(--primary)}
.btn.quiet{color:var(--text-muted);font-weight:500;height:32px;padding:0 10px}
.pv .more{margin-left:auto}
.cols{display:grid;grid-template-columns:1fr 340px;gap:24px;margin-top:18px;align-items:start}
.sub{margin-bottom:12px}
.grid{list-style:none;display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.app{padding:16px;display:flex;flex-direction:column}
.app .top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px}
.app b{font-weight:600;font-size:15px;line-height:21px}
.app span{font-size:13px;line-height:19px}
.app .mono{font-size:12px;overflow-wrap:anywhere;margin-bottom:12px}
.app .bot{margin-top:auto!important;display:flex;justify-content:space-between;align-items:center;margin-top:12px;padding-top:10px;border-top:1px solid var(--border)}
.app .x{width:28px;height:28px;display:grid;place-items:center;border-radius:6px;color:var(--text-muted)}
.web{display:flex;gap:14px;align-items:center;padding:16px 18px;margin-top:12px}
.web .ico{color:var(--text-muted)}
.web>div{flex:1}
.web b{font-weight:600}
.web p{font-size:13px;line-height:19px}
.picker{padding:18px 18px 16px}
.picker h2{font-size:17px;line-height:24px;font-weight:600;margin-bottom:12px}
.picker .field{gap:10px}
.picker ul{list-style:none;margin-top:6px}
.picker li{display:flex;align-items:center;gap:12px;padding:9px 0;border-bottom:1px solid var(--border)}
.picker li>div{flex:1;display:flex;flex-direction:column}
.picker li b{font-weight:600}
.picker li span{font-size:12px;line-height:17px}
.btn.sm{height:30px;font-size:13px;padding:0 12px}
.added{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--text-muted)}
.manual{display:block;margin-top:12px;font-size:13px;color:var(--text-muted);text-decoration:underline;text-underline-offset:3px;text-decoration-color:var(--border-strong)}
"""
    return page("Basalt · Causeway · Blocked apps", theme, css, chrome("blocked", body, theme))


# ---------------------------------------------------------------- Settings, License
def settings_license(theme="dark"):
    tabs = ["License & devices", "Focus", "App", "Notifications", "Your data", "About"]
    t = "".join(f'<span class="{"on" if i == 0 else ""}">{x}</span>' for i, x in enumerate(tabs))
    tile = """<svg width="56" height="56" viewBox="0 0 100 100" aria-hidden="true"><rect width="100" height="100" rx="19" fill="#17181B"/>
<g stroke="#17181B" stroke-width="1" stroke-linejoin="round">""" + "".join(
        f'<polygon points="{p}" fill="{ {"L": "#A3A6AA", "F": "#74777C", "R": "#4B4E53"}.get(f, "#E6E6E3") }"/>' for f, p in
        __import__("common")._MARK) + "</g></svg>"
    body = f"""
<h1>Settings</h1>
<div class="pv" role="tablist" aria-label="Settings sections">{t}</div>
<div class="stack">
  <section class="card lic">
    {tile}
    <div class="who"><b>Basalt</b><span class="muted">Free trial · <span class="num">5</span> days left · everything unlocked until Wednesday 21 October</span></div>
    <div class="buy"><span class="num"><b>$4.99</b> one-time</span><button class="btn primary">Buy Basalt</button></div>
  </section>
  <section class="card exp">
    <div class="eh">{ic("key")}<div><b>Activate a license key</b><span class="muted">Use the key from your purchase email.</span></div>{ic("chev-u", 18)}</div>
    <div class="eb">
      <label><span class="lbl">License key</span><div class="field mono">FS-XXXX-XXXX-XXXX-XXXX</div></label>
      <label><span class="lbl">Email used at checkout <span class="faint">(optional)</span></span><div class="field">you@example.com</div></label>
      <button class="btn secondary">Activate</button>
    </div>
  </section>
  <section class="card row dis">{ic("monitor")}<div><b>Your devices</b><span class="muted">Listed here once a license is active.</span></div></section>
  <section class="card row">{ic("lock")}<div><b>What leaves this PC</b><span class="muted">Only the license check: your key, the checkout email, a salted device identifier and this PC's name.</span></div><a class="lnk">Privacy policy</a></section>
</div>"""
    css = CSS + """
.pv{display:flex;gap:4px;margin-top:16px;border-bottom:1px solid var(--border)}
.pv>span{padding:10px 14px 12px;color:var(--text-muted);font-weight:500;position:relative}
.pv>span:first-child{padding-left:0}
.pv>span.on{color:var(--text);font-weight:600}
.pv>span.on::after{content:"";position:absolute;left:0;right:14px;bottom:-1px;height:3px;border-radius:2px;background:var(--primary)}
.stack{display:flex;flex-direction:column;gap:6px;margin-top:22px;max-width:860px}
.lic{display:flex;align-items:center;gap:18px;padding:20px 22px;margin-bottom:10px}
.who{flex:1;display:flex;flex-direction:column}
.who b{font-size:20px;line-height:28px;font-weight:600}
.buy{display:flex;align-items:center;gap:16px;color:var(--text-muted)}
.buy b{color:var(--text);font-size:18px;font-weight:600}
.exp .eh,.row{display:flex;align-items:center;gap:16px;padding:16px 20px}
.exp .eh>div,.row>div{flex:1;display:flex;flex-direction:column}
.exp b,.row b{font-weight:600}
.exp span,.row span{font-size:13px;line-height:19px}
.exp .ico,.row .ico{color:var(--text-muted)}
.eb{display:grid;grid-template-columns:1fr 1fr auto;gap:16px;align-items:end;padding:16px 20px 20px 56px;border-top:1px solid var(--border)}
.dis b{color:var(--text-muted)}
.lnk{font-size:13px;color:var(--text);text-decoration:underline;text-underline-offset:3px;text-decoration-color:var(--border-strong)}
"""
    return page("Basalt · Causeway · Settings, License", theme, css, chrome("settings", body, theme, trial=False))


# ---------------------------------------------------------------- History
def hex_calendar(R=17):
    """30 days as flat-topped hexagons: rows are weekdays, columns are weeks (offset like basalt from above)."""
    from datetime import timedelta
    first_monday = START30 - timedelta(days=START30.weekday())
    weeks = ((TODAY - first_monday).days // 7) + 1
    hw = math.sqrt(3) * R          # pointy-topped hex width
    lab_w = 38
    w = lab_w + weeks * hw + hw / 2 + 4
    h = 7 * R * 1.5 + R * 0.5 + 6
    s = [f'<svg width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}" role="img" '
         f'aria-label="Focus minutes per day for the last 30 days, 17 September to 16 October">']
    for r, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        cy = R + r * R * 1.5 + 2
        s.append(f'<text x="0" y="{cy+4:.1f}" font-size="11" fill="var(--text-faint)">{d}</text>')
    for k in range(weeks * 7):
        day = first_monday + timedelta(days=k)
        c, r = divmod(k, 7)
        if day < START30 or day > TODAY:
            continue
        cx = lab_w + hw / 2 + c * hw + (hw / 2 if r % 2 else 0)
        cy = R + r * R * 1.5 + 2
        pts = " ".join(f"{cx + (R-1.2)*math.cos(math.radians(60*i-30)):.1f},{cy + (R-1.2)*math.sin(math.radians(60*i-30)):.1f}" for i in range(6))
        mins = MINUTES30[(day - START30).days]
        lvl = heat_level(mins)
        stroke = ' stroke="var(--text)" stroke-width="1.5"' if day == TODAY else ""
        s.append(f'<polygon points="{pts}" fill="{heat_fill(lvl)}"{stroke}><title>{day:%a %d %b}: {mins} min</title></polygon>')
        col = f"var(--heat-ink-{lvl})"
        s.append(f'<text x="{cx:.1f}" y="{cy+4:.1f}" text-anchor="middle" font-size="11" fill="{col}" class="num">{day.day}</text>')
    s.append("</svg>")
    return "".join(s)


def history(theme="dark"):
    rows = ""
    for s in SPRINTS[:4]:
        rows += (f'<li>{mark(26, theme, lit=s["shield"], ground="var(--surface)", label=SHIELD_NAME[s["shield"]])}'
                 f'<div><span class="m num">{sprint_meta(s)}</span>'
                 f'<b class="{"" if s["out"] == "Completed" else "early"}">{sprint_title(s)}</b>'
                 + (f'<span class="muted">{s["journal"]}</span>' if s["journal"] else "") + '</div></li>')
    ms = "".join(f'<li>{ic("milestone", 18)}<div><b>{m["title"]}</b><span class="faint num">{m["when"]}</span></div></li>' for m in MILESTONES)
    body = f"""
<div class="hd"><h1>History</h1><span class="muted">This week · 12–18 October</span></div>
<section class="card wk">
  <div class="st">
    <div><span class="lbl">Focused</span><b class="num">2.9 h</b></div>
    <div><span class="lbl">Sprints finished</span><b class="num">5</b></div>
    <div><span class="lbl">Distractions stopped</span><b class="num">8</b></div>
    <div><span class="lbl">Stopped most often</span><b class="t">Discord</b></div>
  </div>
  <div class="ch"><span class="lbl">Minutes focused per day</span>{week_bars(470, 132, bar_w=30, cap=True)}</div>
</section>
<div class="r2">
  <section class="card hx"><span class="lbl">Focus, last 30 days</span>{hex_calendar()}{heat_legend(14, hexes=True)}</section>
  <section class="card sp"><div class="sh"><span class="lbl">Every sprint · newest first</span><a>{ic("download", 16)}Export your journal</a></div><ul>{rows}</ul></section>
  <section class="card ml"><span class="lbl">Milestones</span><ul>{ms}</ul></section>
</div>"""
    css = CSS + """
.hd{display:flex;align-items:baseline;gap:16px}
.wk{display:flex;gap:28px;padding:18px 22px;margin-top:18px}
.st{display:grid;grid-template-columns:1fr 1fr;gap:16px 28px;width:330px;align-content:center}
.st b{font-size:28px;line-height:32px;font-weight:600;letter-spacing:-.02em}
.st .lbl{margin-bottom:2px}
.st b.t{font-size:22px}
.ch{flex:1;border-left:1px solid var(--border);padding-left:28px}
.r2{display:grid;grid-template-columns:auto 1fr 220px;gap:12px;margin-top:12px;align-items:start}
.hx{padding:16px 18px}
.hx svg{margin:4px 0 12px}
.hx .legend{gap:8px}
.sp{padding:16px 18px 6px}
.sh{display:flex;justify-content:space-between}
.sh a{display:inline-flex;gap:6px;align-items:center;font-size:13px;color:var(--text-muted);height:18px}
.sp ul,.ml ul{list-style:none}
.sp li{display:flex;gap:12px;padding:10px 0;border-top:1px solid var(--border)}
.sp li>div{display:flex;flex-direction:column}
.sp .m{font-size:12px;line-height:17px;color:var(--text-muted)}
.sp b{font-weight:600}
.sp b.early{font-weight:500;color:var(--text-muted)}
.sp li span.muted{font-size:13px;line-height:19px}
.ml{padding:16px 16px 8px}
.ml li{display:flex;gap:10px;padding:9px 0;border-top:1px solid var(--border);color:var(--text-muted)}
.ml li>div{display:flex;flex-direction:column}
.ml b{color:var(--text);font-weight:600;font-size:13px;line-height:18px}
.ml span{font-size:12px;line-height:17px}
"""
    return page("Basalt · Causeway · History", theme, css, chrome("history", body, theme))


SCREENS = [
    ("today-rest", "Today at rest", lambda: today_rest("dark")),
    ("today-sprint", "Today, Firm sprint", lambda: today_sprint("dark")),
    ("blocked-apps", "Blocked apps", lambda: blocked_apps("dark")),
    ("settings-license", "Settings → License", lambda: settings_license("dark")),
    ("history", "History", lambda: history("dark")),
    ("today-rest-light", "Today at rest, light", lambda: today_rest("light")),
]
