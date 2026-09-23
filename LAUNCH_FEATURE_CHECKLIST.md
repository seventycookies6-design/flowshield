# FlowShield — launch feature checklist

What to build before FlowShield is launched to real customers, and what should
wait until after. Every item notes which competitors the idea comes from, why it
fits FlowShield, how to build it within the rules in `CLAUDE.md`, and how to
know it's done.

The visual side (colours, type, components, motion, copy) lives in
**`DESIGN_SYSTEM.md`**. Every user-facing item here should follow it.

---

## How to use this document

- **It is a plan, not a record.** Nothing below is built unless its box is
  ticked. Never describe an unticked item on the site, in the app or in an email.
- **One item, one issue, one pull request.** Claim the issue before starting,
  as `CLAUDE.md` describes. Tick the box in the same pull request that ships the
  item, and link it.
- **The existing roadmap still applies.** `CUSTOMER_EXPERIENCE_PROMPT.md` lists
  fixes for problems a customer runs into today. Where an item here overlaps a
  roadmap item, it says **Roadmap x.y**. Build it once, to both descriptions, and
  tick both.
- **Pricing has changed since the roadmap was written.** FlowShield is now a
  7-day free trial with everything unlocked, then a one-time $4.99 purchase
  (#29). Ignore "Pro only" labels in the roadmap; nothing is gated by tier any
  more.

### Where the competitor facts come from

Competitor details come from a Perplexity Deep Research report the owner ran on
14 September 2026. That report cites public pricing pages, store listings and
reviews. **None of it has been independently checked here, and prices and
features change often.** Before quoting a competitor on the site (a name, a
price, a feature), re-check the source and note the date. Internal planning
can rely on the report as it stands.

### Priority labels

| Label | Meaning |
| --- | --- |
| **Launch** | Must be done before launch; FlowShield feels unfinished or untrustworthy without it. |
| **Launch+** | Strongly wanted for launch. Ship without it only if it would delay launch by weeks. |
| **Later** | After launch, once real customers show it's needed. |
| **Owner decision** | Needs Keenan's call before anyone builds it; the options are laid out. |

### Effort labels

**S** is about a day, **M** a few days to a week, and **L** more than a week, including tests.

### Rules every item must respect

These come from `CLAUDE.md` and the roadmap, and they shape several decisions below.

- **The blocker stays deliberately timid.** No admin rights, drivers, services,
  hosts-file or DNS edits, and nothing on
  `AppBlockerService.CriticalProcesses` is ever closed. This is why FlowShield
  will not copy Cold Turkey's uninstall locks or hosts-based website blocking.
- **Local first.** No accounts, no cloud sync, no telemetry. Sessions, journal
  and blocklists stay on the PC, encrypted with DPAPI.
- **Never claim a feature the shipped build doesn't have.** The tier 5 claims
  test (`TestWebsiteClaimsMatchTheApp`) enforces this for the pricing section.
- **Every behaviour change gets a test** in the matching tier. Keep existing
  `AutomationId`s.

---

## Who builds what

The work is split evenly between the two people, and matched to the tools each
of them develops with. Every checklist item, design-system task and remaining
roadmap item below has exactly one owner. Tracking issues: #37 (Keenan) and
#38 (Miles).

### How the split was decided

| | Keenan: Claude Code | Miles: Codex and Cursor |
| --- | --- | --- |
| Where it runs | Locally on Keenan's Windows PC, with a terminal, the full build, the UI test suite that drives the real app, and the owner's signed-in dashboards (Stripe, Render, GitHub releases) | Codex runs well-specified tasks in cloud sandboxes, several at once, and opens pull requests; Cursor is an editor where Miles iterates interactively and sees the result immediately |
| Strongest at | Long, multi-file changes that cross the app, licence server and tests; state machines and Windows integration (processes, tray, registry, native messaging, persistence); keeping changes consistent with `CLAUDE.md`; releases, deploys and anything needing the owner's accounts | Well-scoped, clearly specified changes done in parallel (Codex); fast visual iteration on XAML and CSS with a human judging the result, website work, copy and polish (Cursor) |
| Weaker at | Pixel-level visual tuning (it judges layouts from screenshots, one round at a time); one session works on one thing at a time | Cloud sandboxes aren't a Windows desktop, so Codex can't run the WPF app or its UI tests (Miles verifies app changes on Windows before opening a pull request); no access to the owner's Stripe, Render or release accounts |
| So owns | Sprint engine and strictness, scheduling, blocking coverage, data and history, licence server and purchase flow, notifications and tray, installer and release pipeline, the design-token generator | Visual design-system adoption, the shield visuals and overlay, the summary card and motivation screens, light theme and accessibility, settings layout, the website, FAQ and marketing copy |

**Balance:** effort is counted as S = 1, M = 3, L = 6. Keenan's launch work totals 50 points, and Miles's 49. Website blocking (F10, L) and allow-only focus (F11) sit with Keenan but come after launch, so they're outside that count.

**Merging doesn't change:** Keenan's Claude Code session still reviews and merges everyone's pull requests, as `CLAUDE.md` describes.

### Keenan (Claude Code)

| Item | What | Effort |
| --- | --- | --- |
| F2 | Escape hatch that gets harder by shield level (Roadmap 1.9) | M |
| F3 | Sprints survive restarts and crashes (Roadmap 1.10) | M |
| F4 | Start a sprint from the tray or keyboard (Roadmap 3.9) (done, #214) | S |
| F5 | Breaks and study cycles (Roadmap 3.4) (done, #230) | M |
| F6 | Study templates and scheduled sprints (done, #293, #306) | M |
| F8 | App picker with student and gamer suggestions (Roadmap 2.2) (done, #58) | M |
| F9 | Blocklist profiles (Roadmap 3.8) (done, #233) | M |
| F16 | History and weekly view (Roadmap 3.1, 3.6) (done, #217) | M |
| F18 | Three-step first run (Roadmap 2.1) (done, #68) | M |
| F19 | Native notifications and tray (Roadmap 2.5, 2.7) (done, #95) | S |
| F23 | Privacy promise: in-app "Your data" and the claims test (Roadmap 4.5); Miles writes the website section (done, #211) | S |
| F25 | Code signing in the release script (after the certificate is bought) | M |
| Design §14 | `design/tokens.json`, the XAML and CSS generator, and the parity test | M |
| Roadmap 1.3 | One instance only (done, #49) | S |
| Roadmap 1.4 | Register `flowshield://` (done, #51) | S |
| Roadmap 1.5 | Uninstall cleans up (done, #54) | S |
| Roadmap 4.1 | Updates that just happen | M |
| Roadmap 5.1 | Buy from inside the app with no key to copy (server) | M |
| Roadmap 5.2 | Honest waiting while the licence server wakes (done, #225) | S |
| Roadmap 5.4 | Lost your key? (server) (done, #208) | S |
| Roadmap 5.5 | Close the email-only unlock (server and email) | M |
| Roadmap 5.7 | See and manage your devices (done, #229) | M |
| After launch | F10 website blocking extension (owner decision first), F11 allow-only focus | L, M |

### Miles (Codex and Cursor)

| Item | What | Effort |
| --- | --- | --- |
| F1 | Shield levels as clear commitment modes | S |
| F7 | Soft overlay and graceful Firm close (Roadmap 1.7, 1.8) (done, #146, #224, #298) | M |
| F12 | Sprint summary card | S |
| F13 | Set an intention before a sprint (Roadmap 3.3) | S |
| F14 | Momentum explained, trend chart and milestones (Roadmap 3.2) | M |
| F15 | Daily focus goal | S |
| F17 | Read back and export the journal (Roadmap 3.5) | S |
| F20 | A trial that never nags (done, #213) | S |
| F21 | Light theme, keyboard use and accessibility (Roadmap 4.6) (done, #237) | M |
| F22 | Clear, calm Settings (Roadmap 4.2) (done, #253) | S |
| F24 | One-time price as the headline, on the site | S |
| F26 | Honest limits and the FAQ (Roadmap 6.2) | S |
| F27 | Real screenshots and a screen recording (Roadmap 6.1) | S |
| Design §2 | Contrast fixes in the app and site (done, #180, #178) | S |
| Design §2 | Remove legacy colour aliases and hard-coded colours (done, #130, #180) | S |
| Design §3 | Embed Inter (one family, app and site); tabular numbers (done, #171, #172) | S |
| Design §4 | Normalise spacing and corner radii (done, #182) | S |
| Design §5 | Outline icon set replacing the Unicode glyphs (done, #151) | M |
| Design §6 | Shield glyphs everywhere (done, #176, #178) | M |
| Design §7 | Quiet and destructive button variants (done, #180, #178) | S |
| Design §8–9 | Reduced motion (done, #176), and the copy pass — not done: the app and site still mix "licence" and "license" | S |
| Roadmap 1.2 | Start with Windows in the tray (#13, pull request #14, done) | M |
| Roadmap 1.6 | A real app icon | S |
| Roadmap 1.13 | Fit small screens | S |
| Roadmap 1.14 | Friendly errors | S |
| Roadmap 1.15 | No developer text on customer surfaces | S |
| Roadmap 2.3 | Custom sprint lengths | S |
| Roadmap 2.4 | Per-app on/off switch | S |
| Roadmap 3.7 | A sleep schedule people trust | M |
| Roadmap 4.3 | Help that works | S |
| Roadmap 5.3 | A thank-you page that can't lose the key | S |
| Roadmap 6.3 | Guide the download | S |
| Roadmap 6.4 | Phone visitors | S |
| Roadmap 6.6 | Changelog and support pages | S |
| Roadmap 6.7 | Website accessibility | S |

### Where the two meet

A few items depend on each other. Agree the interface on the issue before either side builds it.

- **F2 and F3 → F12:** the summary card shows "ended early" and "interrupted" sprints, which F2 and F3 define. Keenan records the fields on `FocusSession` first.
- **F16 → F14:** milestones are listed on the History page. Keenan builds the page; Miles adds milestones and the momentum chart to it.
- **Design §14 → Miles's design tasks and F21:** the token generator should land first, so contrast fixes, alias removal and the light theme edit `design/tokens.json` rather than the XAML and CSS by hand. Keenan does it first.
- **F6 → Roadmap 3.7:** Keenan's scheduler reworks the sleep-blocking schedule. Miles's schedule UI builds on it.
- **F23:** Keenan builds the in-app data page and the claims test; Miles writes the website section, following the test.
- **F8 → F18:** the first run reuses the app picker's suggestions; both are Keenan's.

### Roadmap items not assigned

| Roadmap item | Why |
| --- | --- |
| 1.1 Align the site | Done (#8–#12) |
| 1.11 Keep Free history, 1.12 Show Pro limits | Obsolete: there is no free tier since #29 |
| 3.5 Export, 3.6 Momentum analytics | Covered by F17 and F16 |
| 3.8 Profiles, 3.9 Keyboard | Covered by F9 and F4 |
| 4.4 Crash reporting | Owner decision still to make |
| 5.6 Billing trouble, 5.8 Plans and trial, 5.9 Subscription emails | Obsolete or decided: one-time purchase (#29). Purchase emails wait for an email provider on Render |
| 6.5 Say it near the price | Replaced by F24 |

---

## What competitors do well, and where FlowShield stands

A summary of the research, to explain the choices below.

| Selling point | Who does it best | FlowShield today | Plan |
| --- | --- | --- | --- |
| Blocks are hard to escape | Cold Turkey (Frozen Turkey), SelfControl, Freedom (Locked Mode), Opal (Hard Mode) | Sealed locks the blocklist, but **End sprint** is one click at every level | F2, F3 |
| Starting a session is instant | RescueTime ("Focus Now" button), Windows Focus Sessions | One click on Today; no tray or keyboard start | F4 |
| Structured study routines | FocusMe (plans), AppBlock and Otto (Pomodoro cycles), Windows Focus Sessions (breaks) | Fixed sprint lengths, no breaks or schedules | F5, F6 |
| Blocks desktop apps and games | Cold Turkey, FocusMe, Freedom | **Core strength**: Discord, Steam and launchers by process | F8, F9 |
| Blocks websites | Cold Turkey, Freedom, FocusMe, LeechBlock NG, BlockSite | **Not at all** | F10 |
| Progress that motivates | Forest (trees), RescueTime and Windows (streaks, goals) | Momentum score and day streak; no history, goals or summaries | F12–F17 |
| Quick, guided first run | RescueTime (after simplifying), FocusMe (setup wizard) | None; the app opens on an empty Today page | F18 |
| One-time price | Cold Turkey ($39), Forest (~$3.99 on iOS); most others are $30–$60 a year | **$4.99 once**, 3 PCs | F24 |
| Privacy, no account | SelfControl, LeechBlock NG, SiteBlocker, DigitalZen | **Core strength**: local, encrypted, no account | F23 |
| Trustworthy installer | Established, signed products | Unsigned; SmartScreen warns | F25 |

**FlowShield's unique position:** it's the only product in the report that combines Windows desktop-app blocking, three escalating shield levels, momentum that doesn't reset, local-only privacy, and a price below the cost of one month of most subscriptions. Everything below should strengthen that position, not blur it.

---

## 1. Sprints and commitment

### F1 — Shield levels as clear commitment modes · **Launch** · S

- [x] Done — shipped in #97

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor

**Borrowed from:** Cold Turkey and SelfControl, which sell strictness directly ("the toughest blocker"); Opal's named modes (Hard Mode, Allow-Only).

**Why it fits:** the three shields are FlowShield's most distinctive feature, but today they're labelled only "I · Soft", "II · Firm" and "III · Sealed", with one line of description. Competitors show that people choose strictness when it's framed as a commitment they're making, not a technical setting.

**How to build it**
- On Today, give each shield button a one-line promise:
  - Soft: "Notes distractions and nudges you."
  - Firm: "Closes blocked apps."
  - Sealed: "Closes apps and locks the list until the sprint ends."
- Add a "Best for" hint under the selected shield: Soft for classes or light work, Firm for homework, Sealed for exams and deep work. Use the same scenarios as the website's shield section.
- Use the same three-bar shield icon and colour for each level in the app, the site and notifications (see `DESIGN_SYSTEM.md` → "Shield levels").
- Copy must stay true to `AppBlockerService`: Soft only records and notifies unless hard kill is on.

**Done when:** tier 3 checks each shield's description text; tier 5 checks that the descriptions match the site's shield section.

---

### F2 — An honest escape hatch that gets harder as the shield gets stronger · **Launch** · M · Roadmap 1.9

- [x] Done (#47): grace period set to 2 minutes by the owner

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** RescueTime (a session can be cancelled in its first five minutes without counting; after that, ending it counts); Freedom's Locked Mode; Cold Turkey's Frozen Turkey; SelfControl's non-cancellable timer.

**Why it fits:** reviewers of every blocker say the same thing: if quitting is effortless, the blocker is pointless. But a lock with no way out (Cold Turkey, SelfControl) generates the other big complaint, being locked out of something needed. FlowShield's escalating shields are the natural place for a fair middle ground.

**How to build it**
- **Grace window, every level:** in the first 2 minutes (owner decision), **Cancel** ends the sprint with no momentum change and nothing recorded. This covers a wrong length or a wrong shield.
- **Soft:** after the grace window, **End sprint** ends it immediately. It's recorded as abandoned and momentum decays as it does today.
- **Firm:** **End sprint** opens a confirmation that shows the time left and the momentum you'll lose, with a 5-second countdown before **End anyway** is enabled.
- **Sealed:** no **End sprint** button. **I need to stop** opens a 30-second countdown; after it, you type a short phrase ("end my sprint"), and the sprint is recorded as abandoned with a larger momentum penalty.
  - This keeps an escape route for real emergencies without making quitting casual.
  - Roadmap 1.9 describes the same idea; build to both.
- **No uninstall locks, services or drivers.** Quitting FlowShield from Task Manager still ends enforcement; the timid-blocker rules forbid preventing that. Instead, F3 means a restarted FlowShield resumes the sprint.
- Tray and keyboard exits (F4) go through the same flow, never around it.

**Done when:**
- Tier 1 covers penalty and grace-window rules.
- Tier 3 covers each level's end flow, including that the Sealed flow can't be completed before the countdown ends.
- Tier 5 regression: ending a Sealed sprint needs more than one click.

---

### F3 — Sprints survive restarts and crashes · **Launch** · M · Roadmap 1.10

- [x] Done (#43)

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** Cold Turkey and SelfControl, whose blocks continue through a restart. That is a large part of their reputation for strictness.

**Why it fits:** today a sprint lives only in memory. Closing FlowShield from Task Manager, a crash or a reboot silently ends it, so Sealed can be escaped without going through F2.

**How to build it**
- Persist the running sprint (start time, planned length, shield, and a last-seen heartbeat) in settings the moment it starts, and clear it when it ends.
- On launch, including a `--tray` start at sign-in, resume a sprint that still has time left, with its shield and lock state intact. Show "Sprint resumed — 18 minutes left".
- If the time ran out while FlowShield was closed, record it as completed only if the app was running for at least half of it. Otherwise record it as interrupted, neither completed nor abandoned. Keep the rule simple and write it down in the code.
- Pairs with Start with Windows (Roadmap 1.2 / #14): a Sealed sprint only survives a reboot if FlowShield starts at sign-in, so say so when Sealed is chosen and start-with-Windows is off.

**Done when:**
- Tier 1 covers the resume and expiry rules.
- Tier 3 kills the process during a sprint, relaunches, and checks the sprint and lock are back.

---

### F4 — Start a sprint from anywhere in one action · **Launch+** · S · Roadmap 2.7, 3.9

- [x] Done (#214)

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** RescueTime's one-click "Focus Now", added after users complained about a four-step start; Windows Focus Sessions' start in the Clock app.

**Why it fits:** FlowShield usually sits in the tray. Opening the window just to press Start is the kind of friction RescueTime had to remove.

**How to build it**
- **Tray menu:**
  - **Start sprint (last settings)** and **Start…** (opens Today).
  - During a sprint: time left, **Open**, and **End sprint**, which goes through the F2 flow.
- **Keyboard:** `Space` on Today starts or ends a sprint, and `Ctrl+1/2/3` picks a shield.
- **Optional global hotkey** (off by default) to start the last sprint, registered with `RegisterHotKey`, which needs no admin rights.
- The tray icon changes during a sprint: a filled shield plus a small ring showing progress, drawn per the design system.

**Done when:** tier 3 starts a sprint from the tray menu and via `Space`, and checks the end flow is the F2 one.

---

### F5 — Breaks and study cycles · **Launch+** · M · Roadmap 3.4

- [x] Done (#230): a completed sprint offers a break — 5 minutes, or 15 after every fourth completed sprint in a row, both adjustable in Settings — with **Start break**, **Skip break** and **Start next sprint** on the card; a sprint ended early or interrupted offers none. An optional cycle chooser on Today runs 2, 3 or 4 sprints as sprint → break → sprint by itself, with "Sprint 2 of 3" under the timer. During a break the blocker does not enforce, the ring counts down in `text-muted` instead of `primary`, and the tray tooltip and window title read "Break · 4:59". Breaks never touch momentum, the streak or the daily goal, and nothing about the trial or the lock screen appears during one. A break survives a restart alongside the running sprint, or ends quietly if its time ran out while FlowShield was closed. The rules live in `DesktopApp/Models/CycleState.cs`; `--short-timers` gives a 3-second break and `--short-sprints` a 5-second sprint for the UI suite.

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** Pomodoro blockers (AppBlock, Otto, Time To Focus), which block during work and release during breaks; FocusMe's break rules; Windows Focus Sessions' break length.

**Why it fits:** students already think in Pomodoro terms, and the sprint lengths (15–90 minutes) map straight onto them. Without breaks, a homework evening means restarting sprints by hand.

**How to build it**
- After a completed sprint, offer a break: 5 minutes by default, 15 after every fourth sprint, both adjustable. Buttons: **Start break**, **Skip break**, **Start next sprint**.
- **Cycles:** optionally run a set number of sprints with breaks between them automatically, for example "3 × 45 min".
- **During breaks the shield is down.** Blocked apps are allowed and the timer shows the break counting down.
- Breaks don't affect momentum. A cycle abandoned mid-sprint follows the F2 rules for that sprint only.
- Show a native notification when a break ends (Roadmap 2.5).

**Done when:**
- Tier 1 covers the cycle state machine.
- Tier 3 runs a short cycle (using a test-only minute override, like `--expire-trial`) and checks blocking is off during the break.

---

### F6 — Study templates and scheduled sprints · **Launch+** · M

- [x] Done (#293, #306): three built-in templates — Homework evening (3 × 45 min, Firm, 10-minute breaks), Exam prep (90 min, Sealed) and Light study (25 min, Soft, 5-minute breaks) — plus the user's own, each a named sprint length, shield, cycle, break length and blocklist profile. A chip row above Start on Today fills in length, shield, cycle and profile (a preset, not a lock) and hides while a sprint or break runs. Sleep Blocking became the **Schedule** page, with the nightly window unchanged at the bottom, where a template is attached to days and a start time. Five minutes before, a notification and a card on Today say what starts at what time and which open blocked apps it will close, with **Start now** and **Skip today**; clicking the notification opens Today; with Ask first off it starts and says so. An Ask-first start nobody was asked about (its heads-up fell while a sprint or break was running) is offered on the card as due now, never taken. A scheduled start applies the template to Today the way a chip does and goes through the same gates as Start (terms, first run, trial, one sprint at a time); it asks F7's open-apps question unless the heads-up named those apps where the user could see them (the window up, or the notification that names them sent). A start missed while the PC was asleep or FlowShield was closed is offered for 30 minutes, never started; a card goes once its start is handled or 30 minutes have passed. Skipping costs no momentum. A template's break length stays with its sprint and its breaks across a restart, and a chip carries it to a hand start. The rules live in `DesktopApp/Models/ScheduleMatcher.cs` and `SchedulePlanner.cs`; `--short-schedules` gives a 15-second heads-up and a 30-second late window for the UI suite.

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** FocusMe (plans that run on a schedule); Freedom (recurring sessions); Cold Turkey (scheduled blocks); LeechBlock NG (block sets tied to time windows).

**Why it fits:** "Every weeknight 5–7 PM is homework" is the core student scenario on the website. Today it needs someone to remember to press Start every evening. FlowShield already has a scheduler for sleep blocking, so this reuses proven code.

**How to build it**
- **Templates:** a template is a named set of sprint length, shield, break pattern, cycle count and profile (F9). Ship three:
  - Homework evening: 3 × 45 min, Firm, 10-minute breaks.
  - Exam prep: 90 min, Sealed.
  - Light study: 25 min, Soft, 5-minute breaks.
  People can edit and add their own.
- **Schedules:** attach a template to days and a start time, for example weeknights at 17:00. At that time FlowShield starts the template, or shows "Homework evening starts in 5 minutes — Start now / Skip today" if the user prefers being asked first.
- Build it on the sleep-blocking scheduler (`AppBlockerService.IsWithinSleepWindow`) and make it consistent with Sleep Blocking. Consider moving both into a single **Schedule** page.
- A skipped scheduled sprint costs no momentum; only abandoning a started sprint does.

**Done when:** tier 1 covers schedule matching (days, times crossing midnight, DST); tier 3 creates a schedule a minute ahead and checks it starts.

---

### F7 — Soft shows a real overlay; Firm closes gracefully · **Launch** · M · Roadmap 1.7, 1.8

- [x] Done (#146, #224, #298) — 1.8's close path shipped in #146: a warning naming the
      app, a grace period, `CloseMainWindow` before any kill, and a panel before
      the sprint saying what is already open. Hard kill still closes instantly,
      by design. 1.7's Soft notice shipped in #224: a topmost full-screen window
      on the blocked app's own monitor, naming the app and the time left, with
      *Back to work* and *Allow 5 minutes*. It never closes anything on its
      own, shows once per sighting, never over a FlowShield panel, and never
      at Firm or Sealed. A Settings switch turns it off.
      1.0.10 (#298): the notice gained *Close ‹app›*, first and primary (it
      asks the app to close and never kills it); *Back to work* is the default
      and keyboard action (Enter, Esc), so a keystroke meant for the blocked
      app can never close it; *Allow 5 minutes* waits 5, 10, 20, then 30 s
      with a text countdown; the sprint's intention and a try count show.
      Close and Back to work each count as one *turned back* (#307), saved
      with the sprint as a count only (never which app) and shown on its
      summary card and in History's week.

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor

**Borrowed from:** Opal and Forest's blocked screens, and LeechBlock NG's blocked page: a clear "this is blocked" moment, not a silent kill.

**Why it fits:** today Soft only shows a toast inside FlowShield's window, which usually isn't visible, and Firm kills a process with no warning. That risks unsaved work and gives no feeling of being protected. Roadmap 1.7 and 1.8 already specify the fix.

**How to build it**
- Build to Roadmap 1.7 and 1.8.
- The overlay and warning follow `DESIGN_SYSTEM.md` → "Intervention moments": calm, never scolding, and show the time left.

---

## 2. What gets blocked

### F8 — An app picker built for students and gamers · **Launch** · M · Roadmap 2.2

- [x] Done (#58): browsers included with the whole-browser warning; existing single-process entries are upgraded to the full app. Process names marked `"verified": false` in `DesktopApp/Data/app_suggestions.json` still need checking on a clean install.

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** Cold Turkey's granular blocking (apps, games, Microsoft Store apps); PC Screen Time Manager, which scans common install folders to suggest distracting apps; BlockSite's categories, in spirit.

**Why it fits:** adding an app today means typing a process name or picking from a raw process list. Students don't know that Minecraft's launcher is `MinecraftLauncher.exe`. Easy, correct blocking of Discord, Steam, Epic and game launchers is FlowShield's strongest differentiator, so this must feel effortless.

**How to build it**
- One searchable list combining:
  - Installed apps, from the Start Menu shortcuts and the per-user and machine uninstall registry keys (read-only, no admin).
  - Apps running now.
  - A built-in suggestions list, grouped as **Chat** (Discord, Slack, WhatsApp, Telegram), **Games & launchers** (Steam, Epic Games, Battle.net, Riot Client, Minecraft Launcher, Xbox app), **Video** (Netflix and similar desktop apps), and **Browsers** (clearly labelled "closes the whole browser").
- Each suggestion maps a friendly name and icon to all its process names. For example, Steam covers `steam` and `steamwebhelper`.
- Show the app's real icon, pulled from its executable.
- Never offer anything on `CriticalProcesses`, and explain why if someone searches for one.

**Done when:**
- Tier 1 covers the suggestion mappings and critical-process filtering.
- Tier 3 adds an app from suggestions and checks every mapped process name is saved.

---

### F9 — Blocklist profiles · **Launch+** · M · Roadmap 3.8

- [x] Done (#233)

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** LeechBlock NG's block sets (up to 30, each with its own rules); FocusMe's plans; Opal's rule types.

**Why it fits:** a student's "homework" list (Discord, games) differs from their "exam" list (also the browser). One global list forces them to edit it before every sprint, and Sealed then locks the wrong list.

**How to build it**
- Profiles are named blocklists, such as **School**, **Gaming break** and **Everything**. There's always one default, and Today shows which profile a sprint will use.
- Templates (F6) and schedules pick a profile.
- Keep it simple: one list per profile, no nested rules. Advanced time rules like LeechBlock's are what reviewers call too complex; avoid them.
- Sealed locks the active profile (and the profile switcher) until the sprint ends.

**Done when:** tier 3 switches profile, starts a sprint, and checks only that profile's apps are blocked.

---

### F10 — Website blocking · **Owner decision** (Launch+ or Later) · L · Roadmap 2.6

- [ ] Decision recorded
- [ ] Done

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** almost every competitor. LeechBlock NG and BlockSite are browser-only; Cold Turkey, Freedom and FocusMe block both apps and sites.

**Why it fits:** it's the biggest gap in the research. YouTube and social media in a browser are distractions FlowShield can't touch today, except by closing the whole browser. It matters for students, who do homework in the same browser they get distracted in.

**Why not the obvious way:** the report suggests hosts-file or DNS blocking. That needs admin rights and edits system files, both forbidden by the timid-blocker rules. Don't do it.

**How to build it, the rule-compliant way: a companion browser extension**
- A Chrome/Edge extension, plus Firefox later, that blocks a site list only while a FlowShield sprint is running.
- It learns sprint state from FlowShield through **native messaging**. The host is registered per-user under `HKCU`, which needs no admin rights. When FlowShield isn't running, the extension blocks nothing.
- Site lists live in FlowShield's profiles (F9), so there's one place to edit what's blocked. The extension stores nothing permanently.
- Blocked pages show a calm FlowShield page with the time left, following the design system.
- Shield levels apply: Soft shows an interstitial with **Continue anyway**, Firm and Sealed block. Sealed also warns in FlowShield if the extension is disabled mid-sprint.
- Be honest about limits on the site and in the app: it only covers browsers with the extension installed.

**Interim option:** detect when a browser window's title contains a blocked site name and treat it as a Soft-level distraction, a notice only. Never close a browser for this, because it would close every tab.

**Owner decision:**
- (a) Build the extension for launch, adding several weeks.
- (b) Launch as desktop apps only, stating that clearly, and build the extension first after launch.

The recommendation is (b) plus the honest message (F26), unless early users say browser distraction is the main problem.

**Done when:** tier 2 covers the native messaging host's protocol; the extension's own test suite covers matching; the extension's store listing and privacy disclosure are ready.

---

### F11 — Allow-only focus for exams · **Later** · M

- [ ] Done

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** Opal's Allow-Only rule, which blocks everything except chosen apps.

**Why it fits:** for exam prep, listing what's *allowed* (a PDF reader, notes app and calculator) is easier than listing every distraction.

**How to build it**
- A profile type where everything with a visible window is blocked except the allowed list and all critical processes.
- Only at Firm or Sealed, and only for windowed user apps, never background processes.
- **High risk of closing something important:** require a preview ("these 7 open apps will close") before the sprint starts.
- **Wait until after launch:** it's powerful but easy to get wrong.

---

## 3. Motivation and progress

### F12 — A sprint summary worth reading · **Launch** · S

- [x] Done — shipped in #100

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor

**Borrowed from:** RescueTime's session summaries; Forest's end-of-session screen with your tree and coins.

**Why it fits:** today a finished sprint shows "Sprint complete" and the journal prompt. The moment of accomplishment is the best time to reinforce the habit, and FlowShield already tracks everything needed.

**How to build it**
- When a sprint ends, show a card with:
  - minutes focused;
  - distractions caught, split into apps closed and nudges;
  - the momentum change (for example "+12 → 58");
  - the streak ("Day 4").
  The "What moved?" line goes under it.
- If the user set an intention (F13), show it back: "You planned: finish chapter 3. What moved?"
- **For an abandoned sprint:** use the same card with neutral wording, "Ended early — momentum −6. It'll recover." Never guilt-trip; see the design system's voice rules.
- Numbers only animate if reduced motion is off.

**Done when:** tier 3 finishes a short sprint and checks the card shows the values stored in settings.

---

### F13 — Set an intention before a sprint · **Launch+** · S · Roadmap 3.3

- [x] Done — shipped in #104

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor

**Borrowed from:** Serene, which asks for one goal for the day and structures sessions around it.

**Why it fits:** "What moved?" after a sprint works better when there was a "what are you working on?" before it. It turns the journal into a simple plan-then-reflect loop without becoming a task manager.

**How to build it:** an optional one-line field on Today ("What are you working on?"). It's saved with the session, shown on the timer during the sprint and on the summary card (F12). Leaving it empty is always fine.

---

### F14 — Momentum you can understand, with quiet milestones · **Launch+** · M · Roadmap 3.2

- [ ] Done — the explainer and the 30-day trend chart shipped in #132;
      the quiet milestones wait on F16's History list (#133)

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor

**Borrowed from:** Forest's collection and achievements; streaks and daily goals in Windows Focus Sessions and RescueTime. All are adapted to stay calm, with no trees, coins or confetti.

**Why it fits:** momentum that decays instead of resetting is a real difference from fragile streaks. People only value it if they can see how it works. Forest shows light rewards keep students coming back, but its playful style doesn't fit FlowShield.

**How to build it**
- **Explain the rule:** a small "How momentum works" explainer next to the score. It covers the formula in plain words: finished sprints add, longer ones add more, and quitting takes a slice off but never resets.
- **Trend chart:** a 30-day momentum chart on Today or History, drawn per `DESIGN_SYSTEM.md` → "Charts".
- **Milestones:** quiet milestones such as first sealed sprint, 10 hours focused, a 7-day streak, and momentum 100.
  - Each shows once as a small card, with the shield icon and one sentence, and is kept in a list on History.
  - No sounds, no confetti, no badges for things that aren't real effort.
- Momentum and milestones stay local.

---

### F15 — A daily focus goal · **Launch+** · S

- [x] Done — shipped in #113

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor

**Borrowed from:** Windows Focus Sessions' daily goal; RescueTime's goals.

**Why it fits:** "2 sprints today" or "90 minutes today" is concrete for a student, and the day streak becomes meaningful once it means "hit your goal".

**How to build it**
- An optional goal, set in minutes or in sprints, with a thin progress bar on Today.
- A day counts toward the streak only if the goal is met; with no goal set, the current rule applies.
- The goal can be skipped for a day, such as a planned day off, without breaking the streak, up to once a week.

---

### F16 — History and a weekly view · **Launch+** · M · Roadmap 3.1, 3.6

- [x] Done (#217): this week Monday–Sunday in local time (hours focused,
      sprints completed, distractions caught, most-blocked app), a 30-day
      heatmap of focus minutes in five steps with a legend, and every sprint
      newest first with its length, shield, outcome, intention and journal line
      — which is F17's read-back. The rules are pure in `Models/HistoryStats.cs`
      and nothing new is stored. The most-blocked app is the per-entry count on
      the blocklist, and the card says so: a sprint records how many
      distractions it caught, never which app. The journal export stays on
      Settings, reached from here with a Secondary button. An empty MILESTONES
      card holds the place for F14 (#133). The tier 3 test was written but not
      run; UI runs are scheduled separately.

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** RescueTime and Opal's weekly summaries and time saved, keeping the insight and dropping the cloud analytics and wellbeing scores.

**Why it fits:** sessions are already stored but can't be seen. The research shows people value basic analytics (time focused, distractions avoided) but don't need Opal-style scoring.

**How to build it**
- A **History** page. At the top, this week: focused hours, sprints completed, distractions caught, and the most-blocked app.
- Below that, a calendar heatmap of focus minutes, then a list of sessions with their intention, journal line and shield.
- All computed locally from `AppSettings.Sessions`. No new data leaves the PC.
- Roadmap 3.1 and 3.6 cover the detail; build to them.

---

### F17 — Read back and export the journal · **Launch+** · S · Roadmap 3.5

- [x] Done — the export shipped in #116; the read-back it promised shipped with
      History in #217, where every sprint's intention and journal line is listed
      newest first. The export card stays on Settings, with a Secondary button
      to it from History.

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor; the read-back by Keenan with F16

**Borrowed from:** Serene's daily goal record and RescueTime's summaries. Mainly this fixes a gap: the journal can be written but never read.

**How to build it:** journal entries appear in History (F16). Export them to CSV or Markdown with a date range, as Roadmap 3.5 describes.

---

## 4. First run and everyday use

### F18 — A three-step first run · **Launch** · M · Roadmap 2.1

- [x] Done (#68): a panel over the main window; only suggestions found on this PC are preticked (never browsers); Sealed is offered with its note, Firm selected. "Settings → Help" is the **Show the welcome again** button under Settings → Advanced. Shield wording updates with F1.

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** FocusMe's setup wizard, and RescueTime's lesson in the other direction: keep setup short, and never repeat a tour before every session.

**Why it fits:** a new user lands on an empty Today page with no blocklist, so their first sprint blocks nothing. This is the moment most free trials are won or lost, and FlowShield only has 7 days.

**How to build it**
1. **What distracts you?** The F8 suggestions, with the most common ones preselected for the user to confirm.
2. **How strict?** The three shields explained in one sentence each (F1), with Firm as the default.
3. **Your first sprint:** pick 25 or 45 minutes, and optionally start with Windows. Then **Start my first sprint**.

- Skippable at every step, and re-openable from Settings → Help.
- Mention the trial once, calmly, at the end: "Everything is unlocked for 7 days."
- Never shown again after it's finished or skipped.

**Done when:** tier 3 completes the first run on a clean install and checks the blocklist, shield and start-with-Windows choice were saved.

---

### F19 — Native notifications and a helpful tray · **Launch** · S · Roadmap 2.5, 2.7

- [x] Done (#95): tray notifications for sprint started, 5 minutes left, complete, interrupted and trial ending, each switchable in Settings; break-over and scheduled-sprint kinds are defined and wire up with F5 and F6. The tray icon counts down the minutes left, the tooltip names the shield and time, the taskbar button shows progress, and the window title carries the countdown (Windows 11 hides new tray icons in the overflow until the user drags one out).

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** RescueTime's tray countdown and progress; Windows Focus Sessions' system integration.

**How to build it**
- Use native Windows toast notifications for sprint started, 5 minutes left, sprint complete, break over, a scheduled sprint about to start, and trial ending.
- Each can be switched off in Settings.
- The tray icon shows sprint state (F4).
- Notifications follow the design system's voice rules.

---

### F20 — A trial that never nags · **Launch** · S

- [x] Done (#212): the trial is exactly three surfaces now — the sidebar
      badge (whose dot now follows DESIGN_SYSTEM.md §7: primary while
      trialling, warn once ended, ok once bought), the day-6 notice, and the
      lock screen, which also waits out the sprint's summary card so a trial
      ending mid-sprint never interrupts either.

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor; this
pass built with Claude Code, since most of the plumbing (F19's notification
policy and the settings fields) already lived on Keenan's side.

**Borrowed from:** avoiding the anti-pattern reviewers criticise in BlockSite (constant upsells) and Freedom (a tightly limited free tier).

**Why it fits:** FlowShield's trial is already full-featured, which is the good pattern. What's left is to keep the reminders respectful.

**How to build it**
- The only trial messages:
  - the sidebar badge;
  - one notification on day 6 ("1 day left");
  - the lock screen after day 7.
- Never a pop-up during a sprint.
- The Buy button stays where it is today and never blocks anything during the trial.

**Done when:** a tier 5 test asserts no trial message is raised while a sprint is running.

---

### F21 — Light theme, keyboard use and accessibility · **Launch+** · M · Roadmap 4.6

- [x] Done (#237)

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor

**Borrowed from:** Windows Focus Sessions, which follows the system theme and has solid keyboard support.

**How to build it:** follow Windows light or dark with an override, using the light palette already defined for the website (see `DESIGN_SYSTEM.md`). Full keyboard navigation with visible focus, screen-reader names on every control, and contrast that passes WCAG AA. The design system lists the current tokens that fail.

---

### F22 — Clear, calm Settings · **Launch+** · S · Roadmap 4.2

- [x] Done (#253)

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor

Build to Roadmap 4.2. As scheduling, profiles and notifications arrive (F5–F9, F19), group them so Settings doesn't become FocusMe-style "tab overload", which reviewers call overwhelming.

---

## 5. Trust, privacy and pricing

### F23 — A privacy promise, stated plainly and provable · **Launch** · S

- [x] Done (#211)

**Assigned:** Keenan (seventycookies6-design), built with Claude Code

**Borrowed from:** SelfControl and LeechBlock NG (no accounts, no data collected), and newer entrants (SiteBlocker, DigitalZen) that lead with privacy against Freedom, Opal and RescueTime's accounts and cloud analytics.

**Why it fits:** it's already true of FlowShield and rare in the category, but the site only mentions it in passing.

**How to build it**
- **Website:** a dedicated section. "No account. No cloud. No tracking." Explain what stays on the PC (sessions, journal, blocklists, encrypted with Windows DPAPI) and the only thing that ever leaves it (the licence check). Link to the privacy policy.
- **App:** Settings → **Your data** shows exactly what's stored and where, with **Export** and **Delete everything** (Roadmap 4.5).
- Everything written must match the code. A tier 5 test should keep the claims tied to code markers, like the existing pricing claims registry.

---

### F24 — Make the one-time price the headline it deserves · **Launch** · S

- [x] Done — shipped in #124

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor

**Borrowed from:** Cold Turkey's "Pay once, own forever"; the subscription fatigue the report found in reviews of Freedom, BlockSite and Opal.

**Why it fits:** $4.99 once is far below every paid competitor in the report, which charge $30–$60 a year or $39–$99 for lifetime licences. This is the most persuasive fact FlowShield has.

**How to build it**
- **Site pricing:**
  - "Pay once. Keep it. No subscription."
  - "Up to 3 PCs."
  - "Try everything free for 7 days — no card."
- **A general comparison line**, such as "Most blockers charge $30–$60 every year." Only name a competitor or quote an exact price after re-checking the source and adding the check date in a code comment. Prices change, and naming competitors carries legal and accuracy risk. An unnamed range is safer.
- **Keep the promise consistent** everywhere: app lock screen, success page, legal page and licence email already say it; keep them in step.

---

### F25 — Installer trust: code signing and a security note · **Launch** · M · owner action

- [ ] Certificate bought (owner)
- [ ] Signing added to `tools/build_release.ps1`
- [ ] Security note on the site

**Assigned:** Keenan (seventycookies6-design), built with Claude Code (certificate purchase is an owner action)

**Borrowed from:** established products that ship signed installers. Windows SmartScreen's "unknown publisher" warning is the biggest install drop-off noted in `SELLING.md`.

**How to build it**
- The owner buys a code-signing certificate (see `SELLING.md`).
- Sign the app and installer in `tools/build_release.ps1` with `--signParams`.
- Add a short security note to the site and FAQ: signed, runs as a normal user, no admin rights, no drivers, no system changes. All of that is true today and enforced by the timid-blocker rules.

---

### F26 — Say honestly what FlowShield doesn't do yet · **Launch** · S · Roadmap 6.2

- [x] Done — shipped in #124

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor

**Borrowed from:** reviewers' frustration when a product's limits surface after purchase, and SelfControl's plain "what it does" framing.

**How to build it:** a FAQ entry and a short line near pricing. "FlowShield blocks desktop apps on Windows 10 and 11. It doesn't block websites inside your browser yet, and there's no Mac or phone app." Update it the day F10 ships. Treat the limit as focus, not apology: it's built for the apps that actually eat a gamer's or student's evening.

---

### F27 — Show the real product · **Launch** · S · Roadmap 6.1

- [x] Done — shipped in #139

**Assigned:** Miles (milessmart6-pixel), built with Codex and Cursor

**Borrowed from:** every established competitor's site leads with screenshots or a demo of its real app. The Higgsfield proposal (#33) was declined for cost; real captures do the job for free.

**How to build it**
- Real screenshots of Today, the shield picker, the summary card (F12) and History (F16), captured with sample data and never a real blocklist (see `.gitignore`).
- A short, silent, looping screen recording of starting a sprint and a blocked app being closed.
- Follow the site performance and reduced-motion rules in `DESIGN_SYSTEM.md`.

---

## 6. Considered and deliberately not doing

Recorded so nobody re-proposes these without new reasons.

| Idea | Seen in | Why not |
| --- | --- | --- |
| Uninstall protection, lockouts that survive Task Manager, service or driver enforcement | Cold Turkey (Frozen Turkey) | Needs admin rights, services or drivers, which the timid-blocker rules forbid. It's also the source of "I locked myself out" complaints. F2 and F3 give strictness without it. |
| Hosts-file or DNS website blocking | Suggested by the research | Needs admin rights and system file edits. Use the extension route (F10). |
| Accounts and cloud sync across devices | Freedom, Opal, FocusMe, RescueTime | Breaks the local-first promise and needs ongoing infrastructure. Revisit only if a phone app is ever built. |
| Heavy gamification: trees, coins, collectables | Forest | Clashes with the calm identity and reads as "childish" to some users, per reviews. F14 keeps the motivation without the look. |
| AI coach or wellbeing score | FocusMe, Opal | Needs data analysis the product doesn't have, and it's easy to overclaim. Simple, true stats (F16) are the better fit. |
| Subscriptions, tiers or a limited free plan | Freedom, BlockSite, Opal, FocusMe | Decided in #29: one-time purchase after a full trial. |
| Category or keyword parental-control blocking | BlockSite | Different audience (parents), different trust model. FlowShield is self-control for yourself. |
| Full-time time tracking of every app | RescueTime | Privacy-heavy, and not what FlowShield is for. It records only sprints. |
| Marketing video generated by AI | Higgsfield proposal (#33) | Declined for cost; real captures (F27) instead. |
| Mac or mobile apps | Opal, Forest, Freedom | Out of scope for launch. Windows-first is the positioning. |

---

## 7. Launch definition

FlowShield is ready for launch when:

- [x] Every **Launch** item above is ticked except F25: F1, F2, F3, F7, F8, F12, F18, F19, F20, F23, F24, F26 and F27 are all done (22 September 2026). F25 (code signing) is the only one left, waiting on the certificate purchase.
- [ ] The owner has recorded a decision on F10 (website blocking).
- [ ] Roadmap Phase 1 (`CUSTOMER_EXPERIENCE_PROMPT.md`) is complete.
- [ ] The app and site follow `DESIGN_SYSTEM.md`, including the accessibility fixes listed there.
- [ ] The owner launch gates in `SELLING.md` are done: Stripe account activation, completed legal pages and a support email.
- [ ] The full test suite passes, including UI tests, on a clean Windows machine that isn't the development PC.
- [ ] Stripe is switched to live mode, deliberately and last, following `SELLING.md` → "Going live on Stripe".

**Launch+** items should mostly be done too; list any that aren't in the launch notes, so the site never implies they exist.

## Suggested order

Dependencies first, then the moments customers notice most:

1. **Blocking basics:** F8 app picker and F1 shield copy (small, and everything builds on them).
2. **Strictness:** F3 sprints survive restarts, then F2 escape hatch (together they make the shields honest), plus F7 overlay and graceful close.
3. **First impressions:** F18 first run, F12 summary card, F19 notifications, F20 quiet trial.
4. **Routines:** F9 profiles, then F5 breaks, then F6 templates and schedules.
5. **Progress:** F13 intention, F16 history, F17 journal read-back, F14 momentum explained, F15 daily goal.
6. **Launch surface:** F23 privacy, F24 pricing, F26 limits, F27 real product, F25 signing (start the certificate purchase early; it can take days).
7. **After the F10 decision:** the browser extension.
