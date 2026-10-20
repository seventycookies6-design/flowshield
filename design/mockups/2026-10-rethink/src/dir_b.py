"""Direction B, "Ledger": quiet editorial typography. No cards and no sidebar;
a top bar, one reading column, hairline rules and very large tabular numerals.
The next sprint is a sentence you edit, and History opens with a sentence
instead of four stat boxes."""
from common import *

NAME = "B · Ledger"
SLUG = "b-ledger"
SUMMARY = ("Quiet editorial typography: no cards and no sidebar. A top bar, one reading column, hairline rules "
           "and very large tabular numerals. The next sprint is a sentence you edit; History opens with a sentence, not four stat boxes.")

CSS = CAPTION_CSS + LEGEND_CSS + MONO_CSS + SWITCH_CSS + """
.win{display:flex;flex-direction:column;height:860px}
.tb{height:32px;flex:none;display:flex;align-items:center;gap:8px;padding-left:12px;font-size:12px;color:var(--text-muted)}
.top{height:56px;flex:none;display:flex;align-items:stretch;gap:40px;padding:0 48px;border-bottom:1px solid var(--border)}
.brand{display:flex;align-items:center;gap:9px;font-weight:600;font-size:15px;letter-spacing:-.01em}
.top nav{display:flex;gap:28px}
.top nav a{display:flex;align-items:center;color:var(--text-muted);font-weight:500;position:relative}
.top nav a.on{color:var(--text)}
.top nav a.on::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:var(--primary)}
.top.quiet nav a{color:var(--text-faint)}
.top.quiet nav a.on{color:var(--text-muted)}
.top.quiet nav a.on::after{background:var(--border-strong)}
.trial{margin-left:auto;display:flex;align-items:center;gap:14px;font-size:13px;color:var(--text-muted)}
.trial a{color:var(--text);font-weight:600;text-decoration:underline;text-underline-offset:3px;text-decoration-color:var(--border-strong)}
.page{flex:1;min-height:0;padding:40px 64px 28px}
h1{font-size:30px;line-height:36px;font-weight:600;letter-spacing:-.02em}
.eyebrow{font-size:13px;line-height:18px;color:var(--text-muted);font-weight:500}
.rule{border-top:1px solid var(--border)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:40px;padding:0 16px;border-radius:8px;font-weight:600}
.btn.primary{background:var(--primary);color:var(--primary-ink);height:48px;padding:0 28px;font-size:15px}
.btn.secondary{border:1px solid var(--border-strong);background:transparent}
.link{color:var(--text);font-weight:500;text-decoration:underline;text-underline-offset:4px;text-decoration-color:var(--border-strong)}
.uline{border:0;border-bottom:1.5px solid var(--border-strong);height:44px;display:flex;align-items:center;font-size:16px;color:var(--text-faint);background:transparent}
.meter{display:inline-flex;gap:3px;align-items:flex-end}
.meter i{display:block;width:5px;border-radius:1px;background:var(--border-strong)}
.meter i.on{background:var(--primary)}
"""


def meter(level, h=14):
    bars = "".join(f'<i class="{"on" if i < level else ""}" style="height:{h*(0.55+0.225*i):.0f}px"></i>' for i in range(3))
    return f'<span class="meter" aria-hidden="true">{bars}</span>'


def chrome(active, body, theme="dark", quiet=False, trial=True):
    nav = [("today", "Today"), ("history", "History"), ("blocked", "Blocked apps"),
           ("schedule", "Schedule"), ("settings", "Settings")]
    links = "".join(f'<a class="{"on" if k == active else ""}">{t}</a>' for k, t in nav)
    tr = '<div class="trial"><span>Free trial · 5 days left</span><a>Buy Basalt</a></div>' if trial else ""
    return f"""
<div class="win">
  <div class="tb">{mark(14, theme)}<span>Basalt</span>{caption_buttons()}</div>
  <header class="top{' quiet' if quiet else ''}">
    <div class="brand">{mark(20, theme)}<span>Basalt</span></div>
    <nav aria-label="Main">{links}</nav>
    {tr}
  </header>
  <main class="page">{body}</main>
</div>"""


# ---------------------------------------------------------------- Today at rest
def today_rest(theme="dark"):
    tpl = ""
    for i, t in enumerate(TEMPLATES):
        on = i == 0
        tpl += (f'<li class="{"on" if on else ""}"><button aria-pressed="{str(on).lower()}"><span class="tn">{t["name"]}</span>'
                f'<span class="ts num">{template_spec(t)}</span></button>{ic("check", 18) if on else ""}</li>')
    body = f"""
<div class="cols">
  <section class="lead" aria-label="Next sprint">
    <div class="eyebrow">Friday 16 October · next sprint</div>
    <div class="giant num">45:00</div>
    <p class="sentence">
      <button class="tok">45 minutes</button> behind a <button class="tok">{meter(2, 13)} Firm shield</button>,
      <span class="nw">blocking <button class="tok">Default</button> <span class="faint">(3 apps)</span>,</span>
      <span class="nw">for <button class="tok">3 sprints</button> with 10-minute breaks.</span>
    </p>
    <p class="promise">Firm: {SHIELD_PROMISE[2][0].lower() + SHIELD_PROMISE[2][1:]}</p>
    <div class="uline">Intention, optional. Shown on the timer and again when the sprint ends.</div>
    <div class="go"><button class="btn primary">Start sprint</button></div>
  </section>
  <aside class="side">
    <div class="eyebrow">Templates</div>
    <ul class="tpl">{tpl}</ul>
    <div class="eyebrow" style="margin-top:36px">Momentum</div>
    <div class="mom"><span class="mn num">186</span><span class="muted">points · <b>8-day streak</b></span></div>
    {trend_chart(340, 96, grid=(0, 100, 200))}
    <p class="todayline muted num">Today: 1 sprint, 45 minutes, 2 distractions stopped.</p>
  </aside>
</div>"""
    css = CSS + """
.cols{display:grid;grid-template-columns:1fr 340px;gap:72px;height:100%;padding-top:12px}
.giant{font-size:208px;line-height:196px;font-weight:600;letter-spacing:-.045em;margin:20px 0 26px -10px}
.nw{white-space:nowrap}
.sentence{font-size:24px;line-height:40px;color:var(--text-muted);max-width:680px}
.tok{font-size:24px;line-height:30px;color:var(--text);font-weight:600;border-bottom:2px solid var(--border-strong);padding:0 2px;border-radius:4px 4px 0 0}
.tok .meter{margin-right:4px;vertical-align:-1px}
.promise{margin-top:12px;color:var(--text-muted);font-size:14px}
.uline{margin-top:32px;max-width:640px}
.go{margin-top:28px}
.side{padding-top:2px}
.tpl{list-style:none;margin-top:10px;border-top:1px solid var(--border)}
.tpl li{display:flex;align-items:center;border-bottom:1px solid var(--border);position:relative;padding-left:14px}
.tpl li button{flex:1;display:flex;flex-direction:column;align-items:flex-start;padding:12px 0;text-align:left}
.tpl li.on::before{content:"";position:absolute;left:0;top:12px;bottom:12px;width:2px;background:var(--primary)}
.tpl li .ico{color:var(--primary);margin-right:4px}
.tn{font-size:15px;line-height:22px;font-weight:600}
.ts{font-size:13px;line-height:19px;color:var(--text-muted)}
.mom{display:flex;align-items:baseline;gap:12px;margin:6px 0 10px}
.mn{font-size:48px;line-height:52px;font-weight:600;letter-spacing:-.03em}
.mom b{color:var(--text);font-weight:600}
.todayline{margin-top:14px;font-size:13px}
"""
    return page("Basalt · Ledger · Today at rest", theme, css, chrome("today", body, theme))


# ---------------------------------------------------------------- Today during a Firm sprint
def today_sprint(theme="dark"):
    left = 24 + 13 / 60
    pct = left / 45 * 100
    body = f"""
<section class="run" aria-label="Sprint running">
  <div class="state">{meter(2, 16)}<span><b>Shield II · Firm</b></span><span class="faint">·</span><span class="num">Sprint 2 of 3</span></div>
  <div class="giant num">24:13</div>
  <p class="left num">left of 45 minutes</p>
  <div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="45" aria-valuenow="20.8" aria-label="Minutes done"><span style="width:{100-pct:.1f}%"></span><b style="left:{100-pct:.1f}%"></b></div>
  <div class="scale num"><span>Started 16:15</span><span>Ends 17:00</span></div>
  <div class="intent"><div class="eyebrow">Intention</div><p>Finish the essay conclusion</p></div>
  <button class="btn secondary end">End sprint…</button>
</section>"""
    css = CSS + """
.page{padding-top:56px}
.state{display:flex;align-items:center;gap:12px;font-size:16px}
.state b{font-weight:600}
.giant{font-size:288px;line-height:264px;font-weight:600;letter-spacing:-.05em;margin:20px 0 4px -16px}
.left{font-size:18px;color:var(--text-muted);margin-bottom:28px}
.bar b{position:absolute;top:-5px;width:2px;height:14px;background:var(--text);margin-left:-1px;border-radius:1px}
.bar{height:4px;background:var(--track);border-radius:2px;max-width:1152px;position:relative}
.bar span{position:absolute;left:0;top:0;bottom:0;background:var(--primary);border-radius:2px}
.scale{display:flex;justify-content:space-between;margin-top:10px;color:var(--text-muted);font-size:14px}
.intent{margin-top:40px}
.intent p{font-size:30px;line-height:38px;font-weight:600;letter-spacing:-.015em;margin-top:6px}
.end{margin-top:32px;color:var(--text-muted)}
"""
    return page("Basalt · Ledger · Today, Firm sprint", theme, css, chrome("today", body, theme, quiet=True, trial=False))


# ---------------------------------------------------------------- Blocked apps
def blocked_apps(theme="dark"):
    rows = ""
    for a in BLOCKED:
        st = f'<td class="num">{a["stopped"]}</td>' if a["stopped"] else '<td class="faint">Not yet</td>'
        rows += (f'<tr><td><b>{a["name"]}</b><span class="mono faint">{a["proc"]}</span></td><td class="muted">{a["cat"]}</td>'
                 f'{st}<td>{switch(True, "Block " + a["name"])}</td><td class="r"><a class="link sm">Remove</a></td></tr>')
    picks = ""
    for p in PICKER[:4]:
        picks += f'<li><b>{p["name"]}</b><span class="faint">{p["src"]}</span><a class="link sm">Block</a></li>'
    body = f"""
<div class="hd">
  <h1>Blocked apps</h1>
  <p class="profile">Profile <button class="tok">Default {ic("chev-d", 14)}</button> <a class="link sm">Rename, duplicate or delete</a></p>
</div>
<table class="ledger">
  <thead><tr><th>App</th><th>Category</th><th>Times stopped</th><th>Blocking</th><th class="r"><span class="sr">Remove</span></th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<p class="count muted num">3 apps on Default. The shield closes them during a Firm or Sealed sprint and shows its notice on Soft.</p>
<div class="two">
  <section>
    <div class="eyebrow">Add an app</div>
    <div class="uline focus">{ic("search", 18)}<span>Discord, Steam, Minecraft…</span></div>
    <ul class="picks">{picks}</ul>
    <a class="link sm more">Add by process name or .exe path</a>
  </section>
  <section>
    <div class="eyebrow">Websites · notice only</div>
    <p class="web">Basalt shows its notice when the tab in front names one of these. It reads the tab title only, so it can miss a page or catch a search, and it never closes your browser.</p>
    <p class="faint web">No websites yet.</p>
    <button class="btn secondary">{ic("plus", 16)}Add a website</button>
  </section>
</div>"""
    css = CSS + """
.hd{display:flex;align-items:baseline;gap:28px}
.profile{color:var(--text-muted);font-size:15px}
.tok{font-size:15px;color:var(--text);font-weight:600;border-bottom:2px solid var(--border-strong);padding:0 2px;margin:0 10px 0 6px;display:inline-flex;align-items:center;gap:4px}
.tok .ico{color:var(--text-faint)}
.link.sm{font-size:13px;color:var(--text-muted)}
.ledger{width:100%;border-collapse:collapse;margin-top:24px}
.ledger th{text-align:left;font-size:13px;font-weight:500;color:var(--text-muted);padding:0 0 10px;border-bottom:1px solid var(--border-strong)}
.ledger td{padding:12px 0;border-bottom:1px solid var(--border);vertical-align:middle}
.ledger td b{display:block;font-weight:600;font-size:15px}
.ledger td .mono{font-size:12px}
.ledger th:nth-child(1){width:38%} .ledger th:nth-child(2){width:24%} .ledger th:nth-child(3){width:14%} .ledger th:nth-child(4){width:12%}
.r{text-align:right}
.count{margin-top:12px;font-size:13px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:72px;margin-top:36px}
.uline{gap:10px;margin-top:6px}
.picks{list-style:none}
.picks li{display:grid;grid-template-columns:1fr auto auto;gap:16px;align-items:baseline;padding:10px 0;border-bottom:1px solid var(--border)}
.picks li b{font-weight:600}
.picks li span{font-size:13px}
.more{display:inline-block;margin-top:12px}
.web{margin-top:8px;color:var(--text-muted);max-width:460px}
.two .btn{margin-top:16px}
"""
    return page("Basalt · Ledger · Blocked apps", theme, css, chrome("blocked", body, theme))


# ---------------------------------------------------------------- Settings, License
def settings_license(theme="dark"):
    sub = ["License & devices", "Focus", "App", "Notifications", "Your data", "About"]
    s = "".join(f'<a class="{"on" if i == 0 else ""}">{x}</a>' for i, x in enumerate(sub))
    body = f"""
<div class="wrap">
  <nav class="subnav" aria-label="Settings sections"><h1>Settings</h1>{s}</nav>
  <section class="content">
    <div class="eyebrow">License</div>
    <p class="statement">You're on the free trial, with <span class="num">5</span> days left.</p>
    <p class="body">Everything is unlocked until Wednesday 21 October. Buy Basalt once for <b class="num">$4.99</b> to keep it. There is no subscription.</p>
    <button class="btn primary">Buy Basalt</button>
    <div class="rule" style="margin:40px 0 28px"></div>
    <h2>Have a license key?</h2>
    <p class="muted">It's in the email from your purchase. Your devices are listed here once it's active.</p>
    <div class="fields">
      <label><span class="eyebrow">License key</span><div class="uline mono">FS-XXXX-XXXX-XXXX-XXXX</div></label>
      <label><span class="eyebrow">Email used at checkout, optional</span><div class="uline">you@example.com</div></label>
    </div>
    <button class="btn secondary">Activate license</button>
    <p class="small faint">Activating sends your license key, the checkout email, a salted device identifier and this PC's name to the license server. Nothing else leaves this PC. <a class="link">Privacy policy</a></p>
  </section>
</div>"""
    css = CSS + """
.wrap{display:grid;grid-template-columns:220px 1fr;gap:64px;height:100%}
.subnav{display:flex;flex-direction:column}
.subnav h1{margin-bottom:22px}
.subnav a{padding:8px 0 8px 14px;color:var(--text-muted);font-weight:500;position:relative}
.subnav a.on{color:var(--text)}
.subnav a.on::before{content:"";position:absolute;left:0;top:9px;bottom:9px;width:2px;background:var(--primary)}
.content{max-width:640px;padding-top:6px}
.statement{font-size:34px;line-height:42px;font-weight:600;letter-spacing:-.02em;margin:8px 0 12px}
.body{font-size:16px;line-height:26px;color:var(--text-muted);margin-bottom:24px;max-width:560px}
.body b{color:var(--text);font-weight:600}
h2{font-size:20px;line-height:28px;font-weight:600;letter-spacing:-.01em}
.fields{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin:22px 0 24px}
.fields .uline{font-size:15px}
.small{font-size:13px;line-height:19px;margin-top:24px}
.small .link{color:var(--text-muted)}
"""
    return page("Basalt · Ledger · Settings, License", theme, css, chrome("settings", body, theme, trial=False))


# ---------------------------------------------------------------- History
def history(theme="dark"):
    rows = ""
    for s in SPRINTS:
        jr = s["journal"] or '<span class="faint">No journal entry</span>'
        it = s["intent"] or '<span class="faint">No intention</span>'
        out = s["out"]
        ln = s["len"] if s["out"] == "Completed" else f'{s["done"]} of {s["len"]}'
        rows += (f'<tr><td class="num">{s["when"]}</td><td class="num">{ln}</td>'
                 f'<td><span class="sh">{meter(s["shield"], 12)}{SHIELD_NAME[s["shield"]]}</span></td><td>{out}</td>'
                 f'<td><b>{it}</b><span>{jr}</span></td></tr>')
    ms = "".join(f'<li><b>{m["title"]}</b><span class="faint num">{m["when"]}</span></li>' for m in MILESTONES)
    body = f"""
<div class="hd"><h1>History</h1><span class="eyebrow">This week · 12–18 October</span></div>
<p class="lede">You focused for <b class="num">2.9 hours</b> across <b class="num">5 finished sprints</b>.
The shield stepped in <b class="num">8 times</b>, most often for <b>Discord</b>.</p>
<div class="mid">
  <section>
    <div class="eyebrow">Focus, last 30 days</div>
    <div class="cal">{heat_calendar(cell=32, gap=5, radius=4)}</div>
    {heat_legend(12, 2)}
  </section>
  <section class="spr">
    <div class="sh2"><span class="eyebrow">Every sprint, newest first</span><a class="link sm">Export your journal</a></div>
    <table class="ledger">
      <thead><tr><th>When</th><th>Length</th><th>Shield</th><th>Outcome</th><th>Intention and journal</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>
  <aside class="ms"><div class="eyebrow">Milestones</div><ul>{ms}</ul></aside>
</div>"""
    css = CSS + """
.hd{display:flex;align-items:baseline;gap:20px}
.lede{font-size:24px;line-height:36px;color:var(--text-muted);max-width:900px;margin:16px 0 34px;letter-spacing:-.005em}
.lede b{color:var(--text);font-weight:600}
.mid{display:grid;grid-template-columns:auto 1fr 150px;gap:36px;align-items:start}
.cal{margin:12px 0 14px}
.legend{flex-wrap:nowrap;gap:8px}
.sh2{display:flex;justify-content:space-between;align-items:baseline}
.link.sm{font-size:13px;color:var(--text-muted)}
.ledger{width:100%;border-collapse:collapse;margin-top:10px}
.ledger th{text-align:left;font-size:12px;font-weight:500;color:var(--text-muted);padding:0 10px 8px 0;border-bottom:1px solid var(--border-strong)}
.ledger td{padding:10px 10px 10px 0;border-bottom:1px solid var(--border);vertical-align:top;font-size:13px;line-height:19px}
.ledger td:nth-child(1){white-space:nowrap;color:var(--text-muted)}
.ledger td:nth-child(2){white-space:nowrap}
.ledger td b{display:block;font-weight:600;font-size:14px}
.ledger td span{color:var(--text-muted)}
.sh{display:inline-flex;align-items:center;gap:6px;color:var(--text)!important}
.ms ul{list-style:none;margin-top:10px;border-top:1px solid var(--border)}
.ms li{padding:9px 0;border-bottom:1px solid var(--border);display:flex;flex-direction:column}
.ms li b{font-weight:600;font-size:13px;line-height:18px}
.ms li span{font-size:12px}
"""
    return page("Basalt · Ledger · History", theme, css, chrome("history", body, theme))


SCREENS = [
    ("today-rest", "Today at rest", lambda: today_rest("dark")),
    ("today-sprint", "Today, Firm sprint", lambda: today_sprint("dark")),
    ("blocked-apps", "Blocked apps", lambda: blocked_apps("dark")),
    ("settings-license", "Settings → License", lambda: settings_license("dark")),
    ("history", "History", lambda: history("dark")),
    ("today-rest-light", "Today at rest, light", lambda: today_rest("light")),
]
