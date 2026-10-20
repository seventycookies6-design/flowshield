"""Direction A, "Dial": the instrument. A 60-minute timer face with precise
ticks replaces the empty ring; everything you set lives in one control column
beside it, read top to bottom in the order you decide."""
import math
from common import *

NAME = "A · Dial"
SLUG = "a-dial"

CSS = CAPTION_CSS + LEGEND_CSS + MONO_CSS + SWITCH_CSS + """
.win{display:flex;flex-direction:column;height:860px}
.tb{height:32px;flex:none;display:flex;align-items:center;gap:8px;padding-left:12px;font-size:12px;color:var(--text-muted);background:var(--bg)}
.body{flex:1;display:flex;min-height:0}
.side{width:224px;flex:none;border-right:1px solid var(--border);padding:18px 12px 18px;display:flex;flex-direction:column}
.brand{display:flex;align-items:center;gap:10px;padding:2px 12px 22px;font-weight:600;font-size:16px;letter-spacing:-.01em}
.nav{display:flex;flex-direction:column;gap:2px}
.nav a{display:flex;align-items:center;gap:12px;height:40px;padding:0 12px;border-radius:8px;color:var(--text-muted);font-weight:500;position:relative;text-decoration:none}
.nav a.on{color:var(--text);background:var(--surface)}
.nav a.on::before{content:"";position:absolute;left:0;top:11px;bottom:11px;width:3px;border-radius:2px;background:var(--primary)}
.side.quiet .nav a{color:var(--text-faint)}
.side.quiet .nav a.on{color:var(--text-muted);background:none}
.side.quiet .nav a.on::before{background:var(--border-strong)}
.foot{margin-top:auto;padding:14px 12px 4px;border-top:1px solid var(--border);font-size:13px;line-height:19px}
.foot .t{color:var(--text-muted)}
.foot a{color:var(--text);font-weight:600;text-decoration:underline;text-underline-offset:3px;text-decoration-color:var(--border-strong)}
.main{flex:1;min-width:0;padding:26px 40px 24px;display:flex;flex-direction:column}
.head{display:flex;align-items:baseline;gap:16px;margin-bottom:22px}
.head h1{font-size:26px;line-height:32px;font-weight:600;letter-spacing:-.02em}
.head .aside{margin-left:auto;color:var(--text-muted)}
.lbl{display:block;font-size:13px;line-height:18px;font-weight:500;color:var(--text-muted);margin-bottom:8px}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:12px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:40px;padding:0 16px;border-radius:8px;font-weight:600;font-size:14px}
.btn.primary{background:var(--primary);color:var(--primary-ink);height:48px;font-size:15px}
.btn.secondary{background:var(--surface-2);border:1px solid var(--border-strong)}
.btn.quiet{color:var(--text-muted);padding:0 10px}
.select{display:flex;align-items:center;justify-content:space-between;height:40px;padding:0 12px;border-radius:8px;
  background:var(--surface-2);border:1px solid var(--border-strong);font-weight:500}
.select .ico{color:var(--text-faint);width:16px;height:16px}
.field{height:40px;border-radius:8px;background:var(--field);border:1px solid var(--border-strong);padding:0 12px;display:flex;align-items:center;color:var(--text-faint)}
/* segmented control: one bar, selected = fill + outline + weight (never colour alone) */
.seg{display:flex;background:var(--field);border:1px solid var(--border-strong);border-radius:10px;padding:3px;gap:3px}
.seg>span{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;height:34px;border-radius:7px;color:var(--text-muted);font-weight:500}
.seg>span.on{background:var(--primary-soft);box-shadow:inset 0 0 0 1.5px var(--primary);color:var(--text);font-weight:600}
.seg.tall>span{height:42px}
.seg .rn{font-size:12px;color:var(--text-faint);font-weight:500}
"""


def chrome(active, body, theme="dark", quiet=False, foot=True):
    nav = [("today", "Today"), ("history", "History"), ("blocked", "Blocked apps"),
           ("schedule", "Schedule"), ("settings", "Settings")]
    links = "".join(
        f'<a class="{"on" if k == active else ""}" {"aria-current=page" if k == active else ""}>{ic(k)}<span>{t}</span></a>'
        for k, t in nav)
    footer = ('<div class="foot"><div class="t">Free trial · 5 days left</div>'
              '<a>Buy Basalt · $4.99</a></div>') if foot else ""
    return f"""
<div class="win">
  <div class="tb">{mark(14, theme)}<span>Basalt</span>{caption_buttons()}</div>
  <div class="body">
    <aside class="side{' quiet' if quiet else ''}">
      <div class="brand">{mark(22, theme)}<span>Basalt</span></div>
      <nav class="nav" aria-label="Main">{links}</nav>
      {footer}
    </aside>
    <main class="main">{body}</main>
  </div>
</div>"""


# ---------------------------------------------------------------- the dial
def dial(size, set_min=45, remaining=None, label=""):
    k = size / 400
    c = size / 2
    R = c - 2
    r_arc = R - 9 * k
    r_tick = R - 22 * k
    end = remaining if remaining is not None else set_min

    def pt(m, r):
        a = math.radians(m / 60 * 360)
        return c + r * math.sin(a), c - r * math.cos(a)

    s = [f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" role="img" aria-label="{label}">']
    s.append(f'<circle cx="{c}" cy="{c}" r="{R}" fill="var(--surface)" stroke="var(--border)" stroke-width="1"/>')
    s.append(f'<circle cx="{c}" cy="{c}" r="{r_arc}" fill="none" stroke="var(--track)" stroke-width="{4*k:.1f}"/>')
    for m in range(60):
        major = m % 5 == 0
        ln = (16 if major else 8) * k
        x1, y1 = pt(m, r_tick)
        x2, y2 = pt(m, r_tick - ln)
        if remaining is None:
            col = "var(--tick)" if m < set_min else "var(--tick-dim)"
        else:
            col = "var(--text)" if m < remaining else ("var(--tick-dim)" if m < set_min else "var(--track)")
        sw = (2 if major else 1.2) * k
        s.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{col}" stroke-width="{sw:.2f}" stroke-linecap="round"/>')
    for m in (0, 15, 30, 45):
        x, y = pt(m, r_tick - 34 * k)
        s.append(f'<text x="{x:.1f}" y="{y + 4.5*k:.1f}" text-anchor="middle" font-size="{13*k:.1f}" fill="var(--text-faint)" class="num">{m}</text>')
    # the set / remaining arc, with a knob at its leading edge
    x0, y0 = pt(0, r_arc)
    x1, y1 = pt(end, r_arc)
    large = 1 if end > 30 else 0
    s.append(f'<path d="M{x0:.2f},{y0:.2f} A{r_arc:.2f},{r_arc:.2f} 0 {large} 1 {x1:.2f},{y1:.2f}" fill="none" '
             f'stroke="var(--primary)" stroke-width="{4*k:.1f}" stroke-linecap="round"/>')
    s.append(f'<circle cx="{x1:.2f}" cy="{y1:.2f}" r="{7*k:.1f}" fill="var(--primary)" stroke="var(--surface)" stroke-width="{3*k:.1f}"/>')
    s.append("</svg>")
    return "".join(s)


def dial_block(size, time_text, cap, set_min=45, remaining=None, time_px=80, label=""):
    return f"""
<div class="dialwrap" style="width:{size}px;height:{size}px">
  {dial(size, set_min, remaining, label)}
  <div class="readout">
    <div class="time num" style="font-size:{time_px}px;line-height:{time_px}px">{time_text}</div>
    <div class="cap">{cap}</div>
  </div>
</div>"""


DIAL_CSS = """
.dialwrap{position:relative;flex:none}
.dialwrap .readout{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.dialwrap .time{font-weight:600;letter-spacing:-.03em}
.dialwrap .cap{margin-top:10px;color:var(--text-muted);font-size:14px}
"""


# ---------------------------------------------------------------- Today at rest
def today_rest(theme="dark"):
    tiles = ""
    for i, t in enumerate(TEMPLATES):
        on = i == 0
        tiles += (f'<button class="tile{" on" if on else ""}" aria-pressed="{str(on).lower()}">'
                  f'<span class="tn">{t["name"]}</span><span class="ts num">{t["min"]} min · {SHIELD_NAME[t["shield"]]}</span>'
                  f'<span class="ts num">{(str(t["cycle"]) + " sprints") if t["cycle"] else "One sprint"}</span></button>')
    lengths = "".join(f'<span class="{"on" if m == 45 else ""} num">{m}</span>' for m in (15, 25, 45, 60, 90)) + '<span>Custom</span>'
    shields = "".join(
        f'<span class="{"on" if l == 2 else ""}">{shield_glyph(l, 18)}<span>{SHIELD_NAME[l]}</span><span class="rn">{SHIELD_ROMAN[l]}</span></span>'
        for l in (1, 2, 3))
    body = f"""
<div class="head"><h1>Today</h1><span class="aside">Friday 16 October</span></div>
<div class="grid">
  <section class="left">
    {dial_block(392, "45:00", "Ready when you are", label="Timer face set to 45 minutes of 60")}
    <div class="panel mom">
      <div class="m1">
        <span class="lbl">Momentum</span>
        <div class="big num">186</div>
        <div class="muted">Streak <b class="num" style="color:var(--text);font-weight:600">8 days</b></div>
      </div>
      <div class="m2">
        <span class="lbl">Momentum, last 30 days</span>
        {trend_chart(270, 104)}
      </div>
      <div class="m3"><span class="muted">Today</span><span class="num">1 sprint</span><span class="num">45 min focused</span><span class="num">2 distractions stopped</span></div>
    </div>
  </section>
  <section class="right" aria-label="Next sprint">
    <div><span class="lbl">Template</span><div class="tiles">{tiles}</div></div>
    <div><span class="lbl">Sprint length, minutes</span><div class="seg">{lengths}</div></div>
    <div><span class="lbl">Shield</span><div class="seg tall">{shields}</div>
      <p class="promise">{SHIELD_PROMISE[2]}</p></div>
    <div class="two">
      <div><span class="lbl">Blocklist</span><div class="select"><span>Default <span class="faint">· 3 apps</span></span>{ic("chev-d")}</div></div>
      <div><span class="lbl">Cycle</span><div class="select"><span class="num">3 sprints <span class="faint">· 10 min breaks</span></span>{ic("chev-d")}</div></div>
    </div>
    <div><span class="lbl">Intention <span class="faint">(optional)</span></span><div class="field">Shown on the timer and again when the sprint ends</div></div>
    <button class="btn primary">Start sprint</button>
  </section>
</div>"""
    css = CSS + DIAL_CSS + """
.grid{flex:1;display:grid;grid-template-columns:1fr 480px;gap:36px;min-height:0}
.left{display:flex;flex-direction:column;align-items:center;gap:22px}
.mom{width:100%;display:grid;grid-template-columns:120px 1fr;grid-template-rows:auto auto;column-gap:20px;padding:16px 20px 0}
.mom .big{font-size:40px;line-height:44px;font-weight:600;letter-spacing:-.02em;margin-bottom:2px}
.mom .m3{grid-column:1/3;display:flex;gap:18px;border-top:1px solid var(--border);margin-top:12px;padding:10px 0 12px;font-size:13px}
.right{display:flex;flex-direction:column;gap:20px;padding-bottom:0}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
.tile{display:flex;flex-direction:column;align-items:flex-start;gap:2px;text-align:left;padding:10px 10px;border-radius:10px;
  background:var(--surface-2);border:1px solid var(--border-strong)}
.tile .tn{font-weight:600;font-size:14px;line-height:20px}
.tile .ts{font-size:12px;line-height:17px;color:var(--text-muted)}
.tile.on{background:var(--primary-soft);border-color:var(--primary);box-shadow:inset 0 0 0 .5px var(--primary)}
.promise{margin-top:8px;font-size:13px;line-height:18px;color:var(--text-muted)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.right .btn.primary{margin-top:2px}
"""
    return page("Basalt · Dial · Today at rest", theme, css, chrome("today", body, theme))


# ---------------------------------------------------------------- Today during a Firm sprint
def today_sprint(theme="dark"):
    body = f"""
<div class="sprint">
  <div class="intent"><span class="lbl">Intention</span><p>Finish the essay conclusion</p></div>
  {dial_block(500, "24:13", "left of 45 minutes", remaining=24 + 13/60, time_px=108,
              label="24 minutes 13 seconds left of 45")}
  <div class="state">{shield_glyph(2, 22)}<span><b>Shield II · Firm</b></span><span class="dot">·</span><span class="num">Sprint 2 of 3</span></div>
  <button class="btn secondary end">End sprint…</button>
</div>"""
    css = CSS + DIAL_CSS + """
.main{padding-top:24px}
.sprint{flex:1;display:flex;flex-direction:column;align-items:center}
.intent{text-align:center;margin-bottom:22px}
.intent .lbl{margin-bottom:4px}
.intent p{font-size:20px;line-height:28px;font-weight:600;letter-spacing:-.01em}
.state{display:flex;align-items:center;gap:10px;margin-top:24px;font-size:15px}
.state b{font-weight:600}
.state .dot{color:var(--text-faint)}
.end{margin-top:22px;color:var(--text-muted)}
"""
    return page("Basalt · Dial · Today, Firm sprint", theme, css, chrome("today", body, theme, quiet=True, foot=False))


# ---------------------------------------------------------------- Blocked apps
def blocked_apps(theme="dark"):
    rows = ""
    for a in BLOCKED:
        stopped = (f'<span class="num">Stopped {a["stopped"]} times</span>' if a["stopped"]
                   else '<span class="faint">Not needed yet</span>')
        rows += f"""
<li class="row">
  {monogram(a["name"], 36, 9, 15)}
  <div class="nm"><b>{a["name"]}</b><span class="muted">{a["cat"]} · <span class="mono">{a["proc"]}</span></span></div>
  <div class="st muted">{stopped}</div>
  {switch(True, "Block " + a["name"])}
  <button class="iconbtn" aria-label="Remove {a["name"]}">{ic("x", 18)}</button>
</li>"""
    picks = ""
    for p in PICKER:
        act = (f'<span class="added">{ic("check", 16)}Added</span>' if p["added"]
               else '<button class="btn secondary sm">Block</button>')
        picks += f"""
<li class="pick">{monogram(p["name"], 32, 8, 14)}<div class="nm"><b>{p["name"]}</b><span class="faint">{p["src"]}</span></div>{act}</li>"""
    body = f"""
<div class="head"><h1>Blocked apps</h1></div>
<div class="grid">
  <section>
    <p class="sub">What the shield stops during a sprint.</p>
    <div class="panel"><div class="listhead">
      <div class="prof"><span class="muted">Profile</span>
        <div class="select" style="width:170px"><span>Default</span>{ic("chev-d")}</div>
        <button class="iconbtn bordered" aria-label="Profile options: rename, duplicate, new, delete">{ic("more", 18)}</button></div>
      <span class="num cnt">3 apps</span></div><ul class="list">{rows}</ul></div>
    <div class="panel web">
      <div class="wt">{ic("globe")}<div><b>Websites</b> <span class="faint">· notice only</span>
        <p class="muted">Basalt shows its notice when the tab in front names one of these. It reads the tab title only and never closes your browser.</p></div>
        <button class="btn secondary">{ic("plus", 16)}Add website</button></div>
      <p class="empty faint">No websites yet.</p>
    </div>
  </section>
  <aside class="panel picker" aria-label="Add an app">
    <h2>Add an app</h2>
    <div class="field search focus">{ic("search", 18)}<span>Discord, Steam, Minecraft…</span></div>
    <ul class="picks">{picks}</ul>
    <a class="manual">Add by process name or .exe path</a>
  </aside>
</div>"""
    css = CSS + """
.head{margin-bottom:6px}
.prof{display:flex;align-items:center;gap:10px}
.iconbtn{width:36px;height:36px;display:grid;place-items:center;border-radius:8px;color:var(--text-muted)}
.iconbtn.bordered{border:1px solid var(--border-strong);background:var(--surface-2);height:40px;width:40px}
.sub{color:var(--text-muted);margin-bottom:16px}
.sub b{color:var(--text);font-weight:600}
.grid{display:grid;grid-template-columns:1fr 360px;gap:28px;align-items:start}
.picker{margin-top:37px}
.listhead{display:flex;justify-content:space-between;align-items:center;padding:12px 16px 12px 20px;border-bottom:1px solid var(--border)}
.listhead .cnt{font-size:13px;color:var(--text-muted);font-weight:500}
.list{list-style:none}
.row{display:flex;align-items:center;gap:14px;padding:12px 12px 12px 20px;border-bottom:1px solid var(--border)}
.row:last-child{border-bottom:0}
.row .nm{flex:1;display:flex;flex-direction:column;min-width:0}
.row .nm b{font-weight:600}
.row .nm span{font-size:13px;line-height:18px}
.row .st{font-size:13px;width:130px;text-align:right}
.web{margin-top:16px;padding:16px 20px}
.web .wt{display:flex;gap:14px;align-items:flex-start}
.web .wt>div{flex:1}
.web .wt .ico{margin-top:1px;color:var(--text-muted)}
.web p{font-size:13px;line-height:19px;margin-top:4px;max-width:420px}
.web .empty{margin:12px 0 0 34px;font-size:13px}
.picker{padding:20px}
.picker h2{font-size:17px;line-height:24px;font-weight:600;margin-bottom:12px}
.search{gap:10px}
.picks{list-style:none;margin-top:8px}
.pick{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border)}
.pick .nm{flex:1;display:flex;flex-direction:column}
.pick .nm b{font-weight:600}
.pick .nm span{font-size:12px;line-height:17px}
.btn.sm{height:32px;padding:0 14px;font-size:13px}
.added{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--text-muted);padding-right:6px}
.manual{display:block;margin-top:14px;font-size:13px;color:var(--text-muted);text-decoration:underline;text-underline-offset:3px;text-decoration-color:var(--border-strong)}
"""
    return page("Basalt · Dial · Blocked apps", theme, css, chrome("blocked", body, theme))


# ---------------------------------------------------------------- Settings, License
def settings_license(theme="dark"):
    tabs = ["License & devices", "Focus", "App", "Notifications", "Your data", "About"]
    t = "".join(f'<a class="{"on" if i == 0 else ""}">{x}</a>' for i, x in enumerate(tabs))
    meter = "".join(f'<span class="{"used" if i < 2 else ""}"></span>' for i in range(7))
    body = f"""
<div class="head"><h1>Settings</h1></div>
<nav class="tabs" aria-label="Settings sections">{t}</nav>
<div class="col">
  <section class="panel trial">
    <div class="tl">
      <span class="lbl">Free trial</span>
      <div class="big num">5 days left</div>
      <div class="meter" role="img" aria-label="Day 3 of a 7-day trial">{meter}</div>
      <p class="muted">Everything is unlocked until Wednesday 21 October.</p>
    </div>
    <div class="tr">
      <div class="price num">$4.99</div>
      <p class="muted">One-time purchase.<br>No subscription.</p>
      <button class="btn primary">Buy Basalt</button>
    </div>
  </section>
  <section class="panel act">
    <h2>Already bought Basalt?</h2>
    <p class="muted">Enter the license key from your purchase email.</p>
    <div class="fields">
      <label><span class="lbl">License key</span><div class="field mono">FS-XXXX-XXXX-XXXX-XXXX</div></label>
      <label><span class="lbl">Email used at checkout <span class="faint">(optional)</span></span><div class="field">you@example.com</div></label>
    </div>
    <div class="actrow"><button class="btn secondary">Activate license</button><span class="faint">Your devices are listed here once a license is active.</span></div>
  </section>
  <p class="note">{ic("info", 16)}<span>Activating sends your license key, the checkout email, a salted device identifier and this PC's name to the license server. Nothing else leaves this PC. <a>Privacy policy</a></span></p>
</div>"""
    css = CSS + """
.head{margin-bottom:12px}
.tabs{display:flex;gap:26px;border-bottom:1px solid var(--border);margin-bottom:24px}
.tabs a{padding:0 0 12px;color:var(--text-muted);font-weight:500;position:relative}
.tabs a.on{color:var(--text)}
.tabs a.on::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:var(--primary);border-radius:1px}
.col{max-width:720px;display:flex;flex-direction:column;gap:16px}
.trial{display:flex;padding:22px 24px;gap:24px}
.tl{flex:1}
.big{font-size:36px;line-height:42px;font-weight:600;letter-spacing:-.02em}
.meter{display:flex;gap:4px;margin:14px 0 12px;width:280px}
.meter span{flex:1;height:8px;border-radius:2px;background:var(--primary)}
.meter span.used{background:var(--track);box-shadow:inset 0 0 0 1px var(--border-strong)}
.tr{width:220px;border-left:1px solid var(--border);padding-left:24px;display:flex;flex-direction:column;justify-content:center}
.price{font-size:32px;line-height:38px;font-weight:600;letter-spacing:-.02em}
.tr p{font-size:13px;line-height:19px;margin:4px 0 14px}
.act{padding:22px 24px}
.act h2{font-size:17px;line-height:24px;font-weight:600}
.act>p{margin-top:2px}
.fields{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:18px 0 18px}
.actrow{display:flex;align-items:center;gap:16px;font-size:13px}
.note{display:flex;gap:10px;font-size:13px;line-height:19px;color:var(--text-muted);max-width:640px;padding:0 4px}
.note .ico{margin-top:2px;color:var(--text-faint)}
.note a{color:var(--text);text-decoration:underline;text-underline-offset:3px;text-decoration-color:var(--border-strong)}
"""
    # This page is the trial's home, so the sidebar footer would say it twice: hidden here.
    return page("Basalt · Dial · Settings, License", theme, css, chrome("settings", body, theme, foot=False))


# ---------------------------------------------------------------- History
def history(theme="dark"):
    sprints = ""
    for s in SPRINTS[:4]:
        jr = f'<p class="jr">{s["journal"]}</p>' if s["journal"] else ""
        it = f'<span class="it{"" if s["out"] == "Completed" else " early"}">{sprint_title(s)}</span>'
        sprints += f"""
<li><div class="meta">{shield_glyph(s["shield"], 16)}<span class="num">{sprint_meta(s)}</span></div>{it}{jr}</li>"""
    ms = "".join(f'<li>{ic("milestone", 18)}<div><b>{m["title"]}</b><span class="faint num">{m["when"]}</span></div></li>' for m in MILESTONES)
    body = f"""
<div class="head"><h1>History</h1><span class="aside">This week · 12–18 October</span></div>
<section class="panel week">
  <div class="wl">
    <span class="lbl">Focused this week</span>
    <div class="big num">2.9<span> h</span></div>
    <dl>
      <div><dt>Sprints finished</dt><dd class="num">5</dd></div>
      <div><dt>Distractions stopped</dt><dd class="num">8</dd></div>
      <div><dt>Stopped most often</dt><dd>Discord</dd></div>
    </dl>
  </div>
  <div class="wr"><span class="lbl">Minutes focused per day</span>{week_bars(430, 150)}</div>
</section>
<div class="row2">
  <section class="panel heat">
    <div class="hh"><span class="lbl">Focus, last 30 days</span></div>
    {heat_calendar(cell=30, gap=6)}
    {heat_legend()}
  </section>
  <section class="panel sp">
    <div class="hh"><span class="lbl">Every sprint · newest first</span><a class="exp">{ic("download", 16)}Export your journal</a></div>
    <ul>{sprints}</ul>
  </section>
  <section class="panel mil"><span class="lbl">Milestones</span><ul>{ms}</ul></section>
</div>"""
    css = CSS + LEGEND_CSS + """
.head{margin-bottom:18px}
.week{display:flex;gap:28px;padding:18px 22px 14px}
.wl{width:300px}
.big{font-size:44px;line-height:48px;font-weight:600;letter-spacing:-.02em}
.big span{font-size:20px;color:var(--text-muted);font-weight:500;letter-spacing:0}
dl{margin-top:14px;display:flex;flex-direction:column;gap:6px}
dl div{display:flex;justify-content:space-between;font-size:13px;border-top:1px solid var(--border);padding-top:6px}
dt{color:var(--text-muted)} dd{font-weight:600}
.wr{flex:1;border-left:1px solid var(--border);padding-left:28px}
.row2{display:grid;grid-template-columns:auto 1fr 230px;gap:16px;margin-top:16px;align-items:start}
.heat{padding:16px 20px 16px}
.heat .legend{margin-top:14px}
.hh{display:flex;align-items:center;justify-content:space-between}
.sp{padding:16px 20px 6px}
.sp ul{list-style:none}
.sp li{padding:10px 0;border-top:1px solid var(--border)}
.sp .w{font-size:13px;color:var(--text-muted)}
.sp .meta{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--text-muted)}
.sp .meta b{font-weight:500;color:var(--text-muted)}
.sp .it{display:block;font-weight:600;margin-top:4px}
.sp .it.early{font-weight:500;color:var(--text-muted)}
.sp .jr{font-size:13px;line-height:19px;color:var(--text-muted)}
.exp{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--text-muted);margin-bottom:8px}
.mil{padding:16px 18px 10px}
.mil ul{list-style:none}
.mil li{display:flex;gap:10px;padding:9px 0;border-top:1px solid var(--border);color:var(--text-muted)}
.mil li .ico{margin-top:1px}
.mil li div{display:flex;flex-direction:column}
.mil li b{color:var(--text);font-weight:600;font-size:13px;line-height:18px}
.mil li span{font-size:12px;line-height:17px}
"""
    return page("Basalt · Dial · History", theme, css, chrome("history", body, theme))


SCREENS = [
    ("today-rest", "Today at rest", lambda: today_rest("dark")),
    ("today-sprint", "Today, Firm sprint", lambda: today_sprint("dark")),
    ("blocked-apps", "Blocked apps", lambda: blocked_apps("dark")),
    ("settings-license", "Settings → License", lambda: settings_license("dark")),
    ("history", "History", lambda: history("dark")),
    ("today-rest-light", "Today at rest, light", lambda: today_rest("light")),
]
SUMMARY = "A 60-minute timer face with precise ticks replaces the empty ring; every setting sits in one control column beside it."
