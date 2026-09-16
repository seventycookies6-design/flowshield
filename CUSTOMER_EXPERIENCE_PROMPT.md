# FlowShield — customer experience overhaul prompt

Paste everything below the line into a Claude Code session opened in the
FlowShield repo. It was written by walking the product the way a customer
meets it (site → checkout → install → first run → daily use → paying → updates
→ leaving) and checking every promise against the code.

## Progress

Who builds each item is in `LAUNCH_FEATURE_CHECKLIST.md` → "Who builds what"
(tracking issues #37 and #38). Kept up to date as items land. Tracked on GitHub in issues #1–#6 (one per
phase), with an issue per item as work starts.

| Item | Status | Where |
| --- | --- | --- |
| 1.1 Align the site with the app | **Done** — site copy corrected, claims test in tier 5, follow-ups finished; live site republished 13 September 2026 | #8, #9, #10, #12 |
| 1.2 Start with Windows starts in the tray | **Done** — `--tray` starts hidden in the tray, and only installed copies refresh the Run value | #13, #14 |
| 1.3 One instance only | **Done**: a second launch brings the running copy forward (argument handover ready for 1.4) | #49 |
| 1.4 Register `flowshield://` | **Done**: installed copies open activation links, and activate after one confirming click | #51 |
| 1.5 Uninstall cleans up | **Done**: uninstall removes the Run value and `flowshield://`; data stays, deletion steps in `SELLING.md` | #54 |
| 2.1 First run | **Done** as launch checklist F18 | #68 |
| 2.5 Notifications that respect you, 2.7 A tray that does something | **Done** as launch checklist F19: switchable tray notifications, a countdown tray icon, tooltip and taskbar progress. Starting a sprint from the tray comes with F4 | #95 |
| 2.2 An app picker | **Done** as launch checklist F8 | #58 |
| 2.3 Custom sprint lengths | **Done**: a Custom… option accepts 5–240 minutes, is validated with an error message, persists across restarts, and is gated behind the trial lock | |
| 1.9 Sealed means sealed, with an honest escape hatch | **Done** as launch checklist F2 | #47 |
| 1.10 Sprints survive restarts | **Done** as launch checklist F3 | #43 |
| 6.6 Changelog and support pages | **Done**: `changelog.html` and `support.html` added, linked from every page footer; footer links covered by tier 5 | #6 |
| Everything else | Not started | #1–#6 |

The audit table below is the state on 13 September 2026, before any fixes. For
1.1, only the *site's claims* changed: the promises in A2–A6 are no longer
advertised, and A31's momentum-and-streak wording now matches the app, but website blocking,
custom lengths, analytics, export, the Soft overlay and a stricter Sealed mode
are still unbuilt (items 2.3, 2.6, 3.5, 3.6, 1.7, 1.9).

**Business model change (14 September 2026, #29):** the owner replaced the
free tier and the $4.99/month Pro subscription with a **7-day free trial
(everything unlocked), then a one-time $4.99 purchase**. Read "Pro" below as
"the bought app", and treat items built around subscriptions — billing
trouble and cancellation (5.6), subscription emails (5.9), the trial and plans
decision (5.8, now decided) — as superseded or needing a rewrite for a
one-time purchase before anyone builds them.

**Launch checklist (14 September 2026, #34):** `LAUNCH_FEATURE_CHECKLIST.md`
turns competitor research into features for launch, and cross-references the
items below by number (e.g. "Roadmap 1.9"), so build overlapping items once,
to both descriptions. `DESIGN_SYSTEM.md` sets the visual style for all of it.

**Correction (13 September 2026):** an earlier version of item 1.2 said
Velopack installs updates in versioned folders. It doesn't; installed copies
run from a stable `current` folder. Item 1.2 below is corrected.

---

You're working on **FlowShield**, a Windows focus timer and app blocker with a
7-day free trial, sold as a one-time $4.99 purchase. Read `README.md`, `SELLING.md`,
`HANDOFF_PROMPT.md` and `FINAL_REPORT.md` first. They're accurate.

Your job is to turn FlowShield into the product a customer would actually want
to pay for and keep. The audit below lists what a customer runs into today;
the phases after it say what to build. Work through the phases **in order**,
one item at a time, and report briefly after each phase. Where an item is
marked **Owner decision** or **Owner action**, prepare everything you can,
then stop and ask. Don't guess on pricing, spending, legal text or anything
that needs the owner's accounts.

## Ground rules

Carried over from the handoff, and still binding:

- **Stripe stays in test mode.** Never use or ask for `sk_live_` keys.
- **Never type secrets into any field or print them in chat.** Get dashboards
  ready and let the owner paste.
- **Never commit** `.stripe_keys.json`, `*.db`, `node_modules/`, `bin/`, `obj/`,
  `dist/`, `logs/`, `reports/` or `screenshots/`.
- **Don't archive or delete the old "Focus Unlock Pro" product** in Stripe.
- **Don't edit text files with PowerShell** `Get-Content`/`Set-Content`. Use the
  file edit tools; `python tools/fix_mojibake.py <file>` repairs damage.
- **Don't create accounts or sign in for the owner.**
- **Pushing does not deploy the server.** After any `Server/` change, ask the
  owner to click *Manual Deploy* on Render, then run
  `python automation/verify_deployed.py`.
- End commit messages with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

New for this work:

1. **The blocker stays deliberately timid.** Never terminate anything on
   `AppBlockerService.CriticalProcesses`, never require admin rights, never
   install drivers, services or browser extensions, never edit the hosts file.
   Letting one distraction through is cheaper than closing something that
   matters. "Harder to escape" features add *friction and honesty*, not
   hostility — there is always a safe way out, and it is recorded.
2. **Never claim what the product doesn't do.** Every sentence on the site, in
   the app and in emails must be true of the shipped build. If a promise can't
   be built, remove the promise. Existing code already follows this rule (see
   the comments in `Website/checkout.js`); keep it.
3. **Every behaviour change gets a test** in the matching tier
   (`automation/tests/test_tier1_unit.py` … `test_tier7_devices.py`). Regression
   fixes go in tier 5 and must fail against the code before the fix. Keep every
   existing `AutomationProperties.AutomationId`; add new ones for new controls.
4. **Test runs already protect the owner's settings** through
   `automation/core/settings_guard.py`. Any new script that launches the app
   must wrap its entry point in `preserve_user_settings()`.
5. **Local first.** Sessions, journal and blocklists stay on the machine,
   DPAPI-encrypted. Anything that leaves the machine (crash reports,
   diagnostics) is opt-in, previewable, and off by default — the site promises
   "0 telemetry sent".
6. **After each phase:** `dotnet build -c Release` with 0 warnings, the full
   suite (`python -m pytest automation/tests -q`; warn the owner first because
   the UI tiers take over the screen), `python automation/smoke_ui.py` for fresh
   screenshots, and update `README.md`, `SELLING.md` and `FINAL_REPORT.md`
   (`python automation/make_report.py`). Commit per item, push per phase.
   Cutting a release (`pwsh tools/build_release.ps1 -Version 1.x.0 -Publish`)
   and publishing the site (`pwsh tools/publish_site.ps1`) need the owner's OK
   each time.

## What a customer runs into today

Verified against the code on 13 September 2026. File references are where to
start, not the whole fix.

| # | Where | What the customer experiences | Evidence |
| --- | --- | --- | --- |
| A1 | Download | "Windows protected your PC", *Unknown publisher*, and the Run button hidden behind *More info*. | Unsigned build; confirmed on a real install. |
| A2 | Site | The hero mock shows `Browser — youtube.com closed ×2`. FlowShield can't block websites, only whole processes. | `Website/index.html` mock; `AppBlockerService` matches process names only. |
| A3 | Site | Pro promises *custom sprint lengths*, *momentum analytics*, *unlimited history* and *journal export (CSV / Markdown)*. Custom lengths, analytics and export don't exist; Pro history is stored but no screen shows it. | `TodayViewModel.SprintLengths` is five fixed presets; no history view, chart or export code anywhere. |
| A4 | Site | *Soft: "A full-screen reminder slides over the distraction."* There is no overlay. Soft logs a line and shows a toast inside FlowShield's own window, which is usually hidden. | `AppBlockerService.Tick` (`nudged blocked process`); `MainViewModel.OnBlocked` → `Toast`. |
| A5 | Site / app | *Sealed: "even you can't unlock it early".* "End sprint" works at every level, tray *Quit* works, and quitting drops the shield. | `TodayViewModel.StopCommand` only checks `IsRunning`; `MainWindow` tray *Quit*. |
| A6 | Site / app | *Hard kill mode: "no three-second grace window".* Firm already kills instantly with no grace period, so Hard kill changes nothing except under Soft. | `AppBlockerService.Tick`: `terminate = shield >= Firm \|\| HardKillModeEnabled`. |
| A7 | App | Blocked apps are killed instantly with no warning. Unsaved work is lost, and because the toast is in a hidden window, it looks like the app crashed. | `process.Kill(entireProcessTree: false)`. |
| A8 | App | The journal is written after every sprint and can never be read again. There's no screen that shows it. | `FocusSession.Journal` is saved; no view binds it. |
| A9 | App | Free history is **deleted** after 7 days, so someone who upgrades later finds their past gone. | `TodayViewModel.EndSprint`: `S.Sessions.RemoveAll(...)`. |
| A10 | App | "Start with Windows" opens the full window at every sign-in. It writes `--tray`, which nothing reads. | `SettingsViewModel.ApplyStartWithWindows`; no `--tray` handling in `App.OnStartup`. |
| A11 | App | Launching twice runs two blockers and two tray icons. | No single-instance guard. |
| A12 | Thank-you page | "Activate in FlowShield" does nothing. `flowshield://` is never registered. | `Website/success.html`; no protocol registration. |
| A13 | Thank-you page | "Save this key — it is shown here only once." There's no email delivery configured, so closing the tab loses the key. | `checkout.js`; `/health` reports `email: disabled`. |
| A14 | Checkout | The licence server sleeps on Render's free plan. The first "Get Pro" click can sit on "Opening secure checkout…" for ~50 s with no explanation, and `fetch` has no timeout. | `SELLING.md`; `checkout.js startCheckout`. |
| A15 | Checkout | The success page checks for the key only 10 times, 1.2 s apart, then shows "Still confirming your payment" — easy to hit while Stripe or a waking server is slow. | `fetchLicense(sessionId, 10, …)`. |
| A16 | Site | Customers can see developer messages: "Run `node tools/setup_stripe_store.js`", "Start it with `cd Server && npm start`", "see STRIPE_SETUP.md". | `checkout.js friendlyError`, `initSuccessPage`. |
| A17 | Legal | A visible "These are drafts" banner, and `[operator name]`, `[registered address]`, `[support email]` placeholders. No support email anywhere. | `Website/legal.html`; `config.js supportEmail: ""`. |
| A18 | App | Anyone who knows a customer's email can unlock Pro with it. | `SELLING.md` → Known weaknesses; `/validate` accepts email alone. |
| A19 | App | Adding an app means knowing its process name. "Running now" lists raw names (`msedgewebview2`, `ApplicationFrameHost`) with no icons or friendly names, and nothing for apps that aren't running. Steam, Discord and others use several processes. | `BlockedAppsView.xaml`; `LoadRunningProcesses`. |
| A20 | App | Pro limits are invisible until clicked. 45/60/90 min and *Sealed* look available, then snap back with a 4-second toast. | `TodayView.xaml`; `SelectedMinutes` / `SelectedShield` setters. |
| A21 | App | No notification when a sprint ends while the window is hidden, so the "What moved?" prompt waits unseen. | `EndSprint` sets `JournalPromptVisible` only. |
| A22 | App | A running sprint is lost if the app restarts, crashes, updates or the PC reboots. | `_current` lives only in memory. |
| A23 | App | Sleep blocking silently closes apps at bedtime. No heads-up, no weekday schedule, times typed into free-text boxes, and it only works if FlowShield happens to be running. | `SleepBlockingView.xaml`; `SleepBlockingViewModel`. |
| A24 | App | Updates only happen if the customer finds *Settings → Check for updates* and then clicks *Restart to update*. | `SettingsViewModel.CheckForUpdatesAsync`; no automatic check. |
| A25 | App | Settings shows developer controls: a *License server* URL field (typing in it breaks licensing) and "Settings are DPAPI-encrypted at C:\…". | `SettingsView.xaml` Advanced card. |
| A26 | App | No app icon. The exe, Start Menu shortcut, taskbar and *Installed apps* show the generic Windows icon; the tray uses `SystemIcons.Shield`. | `FlowShield.csproj` `<ApplicationIcon></ApplicationIcon>`; `MainWindow.SetUpTray`. |
| A27 | App | The minimum window size is 900×620, taller than a 1366×768 laptop at 125% scaling can show (1093×614 in total, less the taskbar). | `MainWindow.xaml` `MinHeight="620"`. |
| A28 | App | Unexpected errors show a raw exception message and a log path. | `App.OnDispatcherUnhandledException`. |
| A29 | Uninstall | The Start-with-Windows registry entry is left behind, pointing at a deleted exe. | No Velopack uninstall hook in `Program.Main`. |
| A30 | Site | No real screenshots or video, no FAQ, no mention of cancelling on the homepage, no link-preview tags, and phone visitors get a Windows `.exe` link. | Checked on the live site at 375 px. |
| A31 | App / site | The site says "No gamified streak confetti", but the app's Momentum card leads with "Streak: N days". | `TodayView.xaml` `StreakText`. |

## Phase 1 — Make every promise true, and fix what's broken

The goal: nothing a customer reads or clicks is false or dead.

1. **Align the site with the app** (A2, A3, A6, A31). Build list: items 2.3,
   3.1, 3.5, 3.6 and 2.6 below deliver custom lengths, history, analytics,
   export and site blocking. Until each ships, remove or reword its claim in
   `Website/index.html`. Replace the static mock with one that matches the real
   Today screen. Decide the momentum-vs-streak story and make site and app say
   the same thing. *Accept:* a tier-5 test reads the Pro and Free feature lists
   in `index.html` and fails if a listed feature has no matching implementation
   marker (a documented list in the test, updated as features land).
2. **Start with Windows starts in the tray** (A10). Handle `--tray` in
   `App.OnStartup`: create the view model and tray icon, don't show the window.
   While the setting is enabled, an **installed** copy re-writes the Run value on
   launch, so a missing or stale entry is repaired. Velopack runs installed
   copies from the stable `%LOCALAPPDATA%\FlowShield\current\FlowShield.exe`, so
   updates don't move the executable — the refresh is a repair, not an update
   requirement. A **dev build must never refresh the Run value on launch**: it
   shares `%APPDATA%\FlowShield\settings.json` with any installed copy, so doing
   so would point sign-in at `bin\Release\...`. (The explicit Settings toggle may
   still register whichever build is running.) *Accept:* launching with `--tray`
   leaves no visible window and the tray icon is present; launching a dev build
   leaves an existing Run value untouched.
3. **One instance only** (A11). A named mutex per user. A second launch hands
   its arguments (including `flowshield://` URLs) to the first over a named
   pipe, brings it to the front, and exits. *Accept:* two launches → one
   process.
4. **Register `flowshield://`** (A12). Register under
   `HKCU\Software\Classes\flowshield` in Velopack's install and update hooks
   (`VelopackApp.Build().WithAfterInstallFastCallback(...)`,
   `WithAfterUpdateFastCallback`) and remove it in the uninstall hook. Handle
   `flowshield://activate?key=FS-…` by opening *Account* with the key filled in
   and activating after one confirmation click. *Accept:* the success page's
   button activates Pro in an installed copy.
5. **Uninstall cleans up** (A29). The uninstall hook removes the Run value and
   the protocol key. User data in `%APPDATA%\FlowShield` stays (the site and
   `SELLING.md` already say so); document how to delete it.
6. **A real app icon** (A26). Design a multi-resolution `.ico` from the shield
   mark already used in `MainWindow.xaml` and on the site (16–256 px). Set
   `ApplicationIcon`, the window icon, the tray icon, and pass it to `vpk pack`
   in `tools/build_release.ps1`. Add a distinct tray variant for "sprint
   running".
7. **Soft shield shows a real overlay** (A4). When a blocked app's window
   appears, show a topmost, full-screen, click-through-proof overlay on that
   window's monitor. It names the app, shows the time left in the sprint, and
   offers **Back to work** (minimises the distraction) and **Allow 5 minutes**
   (recorded on the session, and capped at once per app per sprint). It never
   covers FlowShield's own windows, UAC or the lock screen. *Accept:* a UI test
   launches the test target at Soft and finds the overlay by AutomationId.
8. **Firm closes gracefully; Hard kill means instant** (A6, A7). Firm: show a
   notification "Discord is blocked — closing in 10 s. Save your work.", then
   `CloseMainWindow()`, then `Kill()` only if it's still running after the grace
   period. Hard kill (Pro): no warning, no grace. Before any sprint starts, if
   blocked apps are running, list them and offer **Close them now** or **Start
   anyway**. Update the legal page's "closed without warning" wording to match.
9. **Sealed means sealed, with an honest escape hatch** (A5). During a Sealed
   sprint: *End sprint* becomes **Emergency exit**, which asks for a typed
   sentence and a 60-second wait, then ends the sprint and records it as
   *seal broken* on the session and in the journal. Tray *Quit* and window close
   are disabled with an explanation. If FlowShield is killed or the PC restarts,
   it resumes the sealed sprint on next launch (see 1.10) and records the
   interruption. No watchdog processes, no protection from Task Manager — rule 1.
10. **Sprints survive restarts** (A22). Persist the running sprint (start,
    planned end, shield, blocks, allowances) on start and on each block event.
    On launch, resume it if its end time is still in the future; otherwise
    close it as completed or interrupted, honestly. *Accept:* a UI test starts a
    sprint, kills the app, relaunches, and finds the timer still counting down.
11. **Keep Free history; limit the view, not the data** (A9). Stop deleting
    sessions. Free shows the last 7 days; older entries appear locked with
    "Upgrade to see your full history". Upgrading reveals everything. Add a
    migration test.
12. **Show Pro limits before the click** (A20). Lock icons and a small PRO badge
    on 45/60/90 min, custom length and *Sealed*. Clicking a locked option opens a
    short in-app upsell card (what Pro adds, price, **Upgrade** and **Not now**)
    instead of a disappearing toast.
13. **Fit small screens** (A27). Minimum 800×540; below ~1000 px wide the stats
    rail moves under the timer and the nav rail collapses to icons. *Accept:*
    smoke screenshots at 1093×570 and 1920×1080 with nothing clipped.
14. **Friendly errors** (A28). Replace the raw exception dialog with "Something
    went wrong." plus **Copy details** and **Get help** (see 4.3). Keep full
    detail in the log. The dialog must not claim the sprint is still guarded or
    that data is safe — after an arbitrary exception that can't be verified, and
    tier 5 now enforces it.
15. **No developer text on customer surfaces** (A16, A25). Site: every error is
    written for a buyer ("Checkout is taking longer than usual — try again in a
    minute. You haven't been charged.") with developer detail only in the
    console. App: remove the *License server* field and the DPAPI path from
    Settings; keep the `--server=` command-line override for tests and add a
    hidden `--dev` flag that shows them.

## Phase 2 — A first run and a blocklist that feel safe

1. **First-run welcome** (skippable, three short steps, re-openable from
   Settings):
   1. What FlowShield does and what it will never touch, in two sentences.
   2. **Pick your distractions** using the new picker (2.2), pre-ticking
      nothing.
   3. Choose a default sprint and shield, turn on notifications and
      Start with Windows (both explained, both opt-in), then **Start your first
      sprint**.
2. **An app picker people can use** (A19). One searchable list combining:
   installed apps from Start Menu shortcuts (all-users and per-user), apps with
   a visible window right now, and a short suggestions list (Discord, Steam,
   Epic Games, Battle.net, Spotify, Slack, Teams, WhatsApp, Telegram, Netflix,
   popular games). Show each app's icon and friendly name
   (`FileVersionInfo.FileDescription`, falling back to the shortcut name).
   Background and system processes are hidden by default, behind a "Show
   everything" toggle. Keep manual entry. Known multi-process apps map to a
   group (Steam → `steam`, `steamwebhelper`; Discord → `discord`, `update`
   only when launched from Discord's folder). *Accept:* adding "Steam" blocks
   every Steam process and never a critical one.
3. **Custom sprint lengths** (Pro, promised on the site). A "Custom…" option
   accepting 5–240 minutes, remembered as a fourth preset.
4. **Per-app on/off switch.** `BlockedAppsViewModel.ToggleApp` exists with no
   UI; add a switch on each row. Disabled while Sealed.
5. **Windows notifications** (A21). Native toast notifications (e.g.
   `CommunityToolkit.WinUI.Notifications`, registered with the app's AUMID via
   the install hook) for:
   - sprint finished, with a **Log what moved** input right in the notification;
   - an app closed or nudged, with the time left;
   - sleep window starting in 10 minutes (Phase 3.7);
   - an update ready (Phase 4.1).
   Each type can be turned off in Settings.
6. **Site blocking without admin rights** (A2). **Owner decision:** which tier
   gets it (suggest Pro). Detect distracting sites in Chrome, Edge, Firefox and
   Brave by the foreground window's title, and where available by reading the
   address bar through UI Automation. Treat a matching tab like a blocked app:
   Soft shows the overlay, Firm and Sealed switch the browser to a local "This
   site is blocked until 14:32" page (a file in the install folder) instead of
   closing the browser. Never close a whole browser for one tab. Start with a
   curated list (YouTube, Reddit, X, Instagram, TikTok, Facebook, Twitch,
   Netflix, news sites) plus custom domains. Only then restore the youtube.com
   line on the site mock.
7. **A better tray.** Always show the icon while a sprint or sleep window is
   active. The tooltip shows time left. The menu offers **Start 25-min sprint**
   (the default), **End sprint** or **Emergency exit**, **Open FlowShield** and
   **Quit** (disabled while Sealed).

## Phase 3 — Sprints worth coming back to

1. **History** (A8). A new *History* page: a calendar heatmap of focus minutes,
   a list of sessions (date, length, shield, completed, interrupted or seal
   broken, blocks, allowances, journal line), a search box over journal
   entries, and editing of a journal line after the fact. Free: last 7 days
   (1.11). Pro: everything.
2. **Momentum you can understand.** A small chart of momentum over the last 30
   days (Pro: all time), and one sentence explaining how it rises and decays.
   Resolve the streak wording (A31).
3. **Set an intention.** An optional "What are you working on?" field before
   starting. The end-of-sprint prompt shows it back ("You planned: finish the
   report. What moved?").
4. **Breaks and cycles.** An optional break after each sprint (default 5
   minutes; a longer one after four), with **Skip break** and **Start next
   sprint**. The shield is down during breaks unless the owner of the machine
   chooses otherwise. Sound cues on start, end and break end, each switchable
   off.
5. **Export** (Pro, promised). CSV and Markdown export of sessions and journal,
   with a date range. Tests check the files' contents.
6. **Momentum analytics** (Pro, promised). Weekly and monthly focus totals,
   best time of day, most-blocked apps, completion rate by shield level.
   Computed locally.
7. **A sleep schedule people trust** (A23).
   - Proper time pickers, and a day-of-week selector (e.g. weeknights only).
   - A notification 10 minutes before the window opens: "Wind down — Steam and
     Discord close at 23:00."
   - Show the next occurrence ("Tonight 23:00 → 06:30").
   - Enabling it offers to turn on Start with Windows, and the page warns
     plainly if FlowShield isn't set to run at sign-in.
   - Graceful close as in 1.8.
   - **Owner decision:** whether Pro gets a one-time "15 more minutes" per
     night.
8. **Profiles** (Pro). Named setups (for example *Work*, *Study*, *Evening*),
   each with its own blocklist, sprint length and shield, picked from the Today
   screen and the tray.
9. **Keyboard and quick access.** `Space` starts or ends a sprint on Today;
   `Ctrl+1…5` switch pages; an optional global hotkey (default
   `Ctrl+Alt+F`, off by default) opens FlowShield. An optional small,
   always-on-top timer that can be dragged anywhere.

## Phase 4 — Updates, settings, help and data

1. **Updates that just happen** (A24). Check on launch and every 24 hours,
   download quietly, and apply when FlowShield next quits or restarts with no
   sprint running. Show a "What's new in 1.x" card once after updating, read
   from the release notes. Keep the manual button. Never restart mid-sprint.
2. **Settings, reorganised.** Sections: *General* (start with Windows, tray,
   theme, sounds, hotkey), *Notifications*, *Blocking* (grace period, hard kill,
   default shield), *Account* (plan, devices, billing, deactivate), *Data &
   privacy*, *About* (version, updates, licences, links).
3. **Help that works.** A *Get help* entry that opens the FAQ, shows the support
   email, and builds a diagnostics bundle (recent log, version, Windows version,
   settings **with the licence key and email redacted**) the customer can
   preview, copy or save. Nothing is sent automatically.
4. **Crash reporting, opt-in.** **Owner decision:** whether to offer it at all,
   given the "0 telemetry" promise. If yes: off by default, asked once after the
   first crash, every report previewable, sent only on consent, and the site's
   claim reworded to "No telemetry unless you choose to send a crash report".
5. **Your data.** *Export everything* (a JSON bundle of blocklists, sessions,
   journal and preferences), *Import*, and *Delete all FlowShield data* with a
   typed confirmation. Tests cover a round trip.
6. **Light theme and accessibility.** Follow the Windows light/dark setting,
   with an override. Full keyboard navigation with visible focus; every control
   named for screen readers; text contrast checked against WCAG AA; honour
   Windows text scaling and reduce-motion.

## Phase 5 — Buying, activating and keeping Pro

Server changes in this phase need the owner's *Manual Deploy* on Render.

1. **Upgrade from inside the app, with no key to copy.** *Get Pro* in the app
   asks the server for a one-time claim token tied to this device, opens
   checkout with it, and polls. When payment completes, the app activates
   itself and shows "Pro unlocked", even if the browser tab is closed. The
   site's checkout keeps working for people who buy on the web.
2. **Honest waiting** (A14, A15). Fire a `/health` warm-up request when the
   pricing section scrolls into view and when the app opens its upgrade card.
   Give `fetch` a timeout. After 3 seconds show "Waking up secure checkout —
   this can take up to a minute" with a live elapsed counter. On the success
   page, poll for up to 2 minutes with the same message. **Owner action:**
   Render's paid plan removes the cold start entirely (`SELLING.md`).
3. **A thank-you page that can't lose the key** (A13). Show the key, **Copy**,
   **Email me this key** (uses `/resend-license`), **Activate in FlowShield**
   (1.4), and **Download FlowShield** for people who bought first. Remove "shown
   here only once". **Owner action:** configure `RESEND_API_KEY` or `SMTP_URL`
   plus `EMAIL_FROM` on Render so the key email actually sends.
4. **Lost your key?** In the app's *Account* section and on the site: enter the
   checkout email and the key is re-sent to that address. Rate-limited on the
   server.
5. **Close the email-only unlock** (A18). Activating by email sends a 6-digit
   code (or a magic link) to that address; the code activates. Existing Pro
   installs stay activated. Tests in tier 4 prove an email alone no longer
   unlocks Pro.
6. **Billing trouble without surprises.** When Stripe reports `past_due`, keep
   Pro for a grace period (**Owner decision:** suggest 7 days) and show a banner
   with **Update payment method** (billing portal). When a subscription is set
   to cancel, show "Pro until 12 October" rather than switching off early, and
   at the end explain what changed. The server already reports status; the app
   needs the states and copy.
7. **See and manage your devices.** *Account* lists each activated device by
   name with last-seen date and **Remove**, using `/devices`. Hitting the
   3-device limit shows that list right there, instead of an error.
8. **Plans and trial.** **Owner decision:** a 7-day Pro trial with no card, an
   annual price, or both. Build whichever the owner picks, with trial days left
   shown in the app and an honest end-of-trial notice. Don't invent prices.
9. **Emails a subscriber expects.** **Owner action:** email provider first.
   Then templates for: licence key, payment failed, subscription cancelled,
   trial ending. Plain, short, no dark patterns, each with the support email.

## Phase 6 — A site that earns the download

1. **Show the real product** (A30). Use `python automation/smoke_ui.py`
   screenshots (never a Blocked Apps capture, which lists real processes; see
   `.gitignore`), plus a short silent loop of starting a sprint and an app being
   closed. Add `og:` and Twitter meta tags with a proper preview image.
2. **An FAQ** covering:
   - What gets blocked, and what never will.
   - Will I lose unsaved work? (The grace period from 1.8.)
   - Why Windows shows a warning when installing, and exactly what to click —
     with the screenshot — until the build is signed.
   - How cancelling and refunds work.
   - What's stored and where. How the 3-device limit works.
   - Offline use, and system requirements (Windows 10/11 x64).
   - How to uninstall, and how to delete my data.
3. **Guide the download.** Clicking *Download* shows a short "What happens next"
   panel: the SmartScreen step (until signed), running the installer, and the
   first-run welcome.
4. **Phone visitors.** Detect mobile and replace the `.exe` button with **Get
   the download link** (a copy-link button, or an email via the licence server
   once email delivery exists). Add a working mobile menu for the nav links.
5. **Say it near the price.** "Cancel anytime from the app or your receipt
   email", the refund summary, and what happens to your data if you stop
   paying, right under the Pro plan.
6. **Changelog and support pages**, linked from the footer and from the app's
   *What's new* card.
7. **Accessibility.** Keyboard focus styles, alt text, colour contrast, and
   `prefers-reduced-motion`.

## Owner-only items

Prepare what you can, then ask. Don't do these yourself.

| Item | Why it matters | What you can prepare |
| --- | --- | --- |
| **Code-signing certificate** | Removes the SmartScreen wall (A1), the single biggest drop-off. | The `--signParams` wiring in `tools/build_release.ps1`, behind a parameter. |
| **Domain** | Credible site, a support address, deliverable email. | Pages custom-domain steps; `EMAIL_FROM` change list. |
| **Render paid plan** | No cold start (A14). | Nothing to code; confirm via `/health` uptime. |
| **Email provider credentials** | Key delivery, recovery, billing emails. | Templates and tests with the capture provider. |
| **Legal details and review** | Removes the draft banner and placeholders (A17). | A checklist of each placeholder and where it appears. |
| **Pricing: trial, annual, grace period** | 5.6, 5.8. | Options with trade-offs, no numbers invented. |
| **Site blocking tier** | 2.6. | The feature behind a tier flag. |
| **Crash reporting** | 4.4 vs the "0 telemetry" promise. | The opt-in design and copy. |
| **Going live on Stripe** | Real revenue. Last. | `SELLING.md` → Going live on Stripe. |
| **winget or Microsoft Store listing** | Easier, trusted installs. | A winget manifest draft once signed. |

## How to report

After each phase, send a short status:

- Items done, each with one line on what changed and the test that covers it.
- Build result and full test counts (passed / skipped / failed), with the reason
  for every skip.
- Before-and-after smoke screenshots for anything visible.
- Anything that changed a customer-facing claim, and the new wording.
- Open questions for the owner, especially **Owner decision** items reached in
  that phase.

Then wait for the owner before starting the next phase.
