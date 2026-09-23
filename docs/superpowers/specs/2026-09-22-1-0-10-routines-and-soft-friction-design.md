# 1.0.10: routines and a smarter Soft shield — design

**Date:** 22 September 2026 · **Owner:** Keenan (seventycookies6-design), built with Claude Code
**Status:** approved in conversation; this is the written spec for review.
**Release target:** 1.0.10, this weekend (after Miles publishes 1.0.9).

## 1. Goal

Ship the two things competitor research says matter most and that FlowShield
can do inside its rules:

1. **Routines** — study templates and scheduled sprints (launch checklist
   **F6**), so "weeknights 17:00 is homework" happens without remembering to
   press Start. It also unblocks Miles's Roadmap 3.7 (sleep schedule).
2. **A Soft shield that works like the research says friction works** — a
   clear way to turn back, a wait before allowing that grows with each try,
   the sprint's intention shown back, and a count of times the user turned
   back.

Plus one small convenience: a taskbar **Jump List** to start a sprint.

### Success criteria

- A user can pick a built-in template on Today and start it in one click.
- A user can schedule "Homework evening, Mon–Thu 17:00", get a heads-up five
  minutes before, and have it start at 17:00 unless they skip it.
- A missed schedule (PC asleep, FlowShield closed) is offered, never forced.
- The Soft notice's **Allow 5 minutes** is gated by a wait of 5 s, 10 s, 20 s,
  then 30 s for the 1st, 2nd, 3rd and later tries in a sprint.
- The summary card and History show how many times the user turned back.
- Every behaviour has a test in the matching tier; the fast suite and the
  touched UI tests pass; every visible change has a screenshot.
- Nothing new leaves the PC. No admin rights, services, drivers or hosts edits.

### Out of scope for 1.0.10 (candidates for 1.0.11)

Opt-in website-title notice (a Soft-level website nudge), a per-sprint log of
which apps were blocked, Store/Xbox (UWP) app blocking, the real browser
extension (F10, needs go-live store accounts), allow-only mode (F11),
auto-updates (Roadmap 4.1, which touches the quit path Miles is fixing in
#204). See the appendix for the evidence behind each.

## 2. Constraints

From `CLAUDE.md` and the launch checklist: the blocker stays timid (never
closes a critical process, no admin, no services, drivers or hosts edits);
local-first (no accounts, cloud or telemetry; settings stay DPAPI-encrypted);
never claim a feature the shipped build lacks; every behaviour change gets a
test; keep existing `AutomationId`s; follow `DESIGN_SYSTEM.md` (calm voice,
light and dark themes, keyboard use, reduced motion).

**Coordination with 1.0.9.** Miles cuts 1.0.9 from `main`, and is still fixing
#203 (a sprint that expires while the PC sleeps) and #204 (quitting during a
Soft sprint). Those touch `TodayViewModel` (`OnTick`, `EndSprint`,
`ResumeInterruptedSprint`), `MainWindow`'s quit and close paths,
`App.OnExit` and `RunningSprint`. Therefore:

- **Nothing from this spec merges to `main` until the `v1.0.9` GitHub release
  exists** — otherwise unfinished 1.0.10 work would ship inside 1.0.9.
- Work that avoids those files is built now, on branches, and rebased onto
  1.0.9 before merging. Work that touches `StartSprint`, `EndSprint` or the
  summary card is built on top of 1.0.9.

## 3. Templates and schedules (F6)

### 3.1 Data

Both live in `AppSettings` (the existing encrypted settings file).

**`StudyTemplate`** — `Id` (Guid string, assigned by `Normalize()` when a
record has none, and reported as a change so it is saved), `Name` (unique:
a second "Mine" becomes "Mine 2", as profiles do, both when saving from the
editor and when loading a file), `SprintMinutes` (5–240), `Shield`,
`CycleSprints` (one of `CycleState.CycleChoices`: 0 for a single sprint, or 2,
3, 4), `BreakMinutes` (1–60), `ProfileId` (a `BlocklistProfile.Id`; empty, or
naming a deleted profile, means the active profile), `BuiltInKey`
("homework", "exam", "light", or empty for the user's own, so **Restore
built-ins** knows which is missing). `AppSettings` also records
`TemplatesSeeded`, so deleting every template is respected.

Three built-ins, seeded once, on the first load without the `TemplatesSeeded`
mark (never again because the list is empty, and never a second copy of one
that is already there):

| Name | Sprints | Shield | Break |
|---|---|---|---|
| Homework evening | 3 × 45 min | Firm | 10 min |
| Exam prep | 1 × 90 min | Sealed | — |
| Light study | 1 × 25 min | Soft | 5 min |

All three can be edited or deleted. **Restore built-ins** re-adds any built-in
that is missing, without touching the user's own templates.

A template's `BreakMinutes` applies to the breaks of the cycle it started
only. The global break settings (`ShortBreakMinutes`, `LongBreakMinutes`) are
unchanged and still apply to sprints started by hand.

**`SprintSchedule`** — `Id` (assigned by `Normalize()` like a template's),
`TemplateId`, `Days` (a set of `DayOfWeek`), `StartMinuteOfDay` (minutes
after local midnight, 0–1439), `AskFirst` (default true), `Enabled` (default
true), `SkippedDatesLocal` (dates the user chose **Skip today**, stored as
plain dates with no time-zone offset; pruned to the last 14 days whenever a
skip is added).

A schedule has a start time only. The template's length decides when the
sprint ends, which avoids the midnight-spanning bugs LeechBlock users report.
Deleting a template deletes its schedules, after a confirmation that says how
many go with it.

### 3.2 Matching

`ScheduleMatcher` is pure (no timers, no UI) and answers in UTC, so no
comparison depends on what the wall clock is doing:

- `NextStartUtc(schedule, afterUtc, zone)` — the first start strictly after
  `afterUtc`, for the schedule's days, or null when no day is chosen.
- `StartsBetweenUtc(schedule, fromUtcExclusive, toUtcInclusive, zone)` — every
  start in the window `(from, to]`, oldest first. The window is clamped to
  the last 8 days: nothing more than a week late is ever acted on, so an
  unset last check (`DateTime.MinValue`) is safe.

Daylight saving:

- **Spring forward** (the start time does not exist that day): start at the
  first valid minute after the gap.
- **Fall back** (the start time happens twice): start once, at the first
  occurrence.

These rules are written in a code comment and covered by tier 1 tests,
including a day-of-week change across midnight and a skipped date.

### 3.3 The scheduler

`ScheduleService` owns a 15-second `DispatcherTimer`. `MainViewModel` creates
and starts it (a two-line change) and nothing else in `MainViewModel` changes.
On each tick, for each enabled schedule:

| Situation | Behaviour |
|---|---|
| Start is 5 minutes away (and `AskFirst`) | Raise the heads-up: a `ScheduledSprint` notification (the kind already exists in `Notifications.cs`) and a card on Today — "Homework evening starts at 17:00" with **Start now** and **Skip today**. The card names blocked apps that are open ("Discord will be closed") so it doubles as the pre-sprint warning. |
| Start time reached, not skipped | Apply the template and start through the same gates as the Start button: terms accepted, first run finished, trial not ended. Open blocked apps get the normal Firm/Sealed warn-then-close. The pre-sprint running-apps panel is not shown; the heads-up replaced it. |
| `AskFirst` is off | No heads-up; the notification "Homework evening started" appears at the start. |
| A sprint or break is already running | Skip quietly and log one line. Nothing stacks or queues. |
| FlowShield was closed or the PC asleep at the start time, and it is now up to 30 minutes late | Ask: "You missed Homework evening · Start now / Not today". Never start automatically after waking or launching. |
| More than 30 minutes late | Do nothing; log one line. |
| **Skip today** | Record the date on the schedule. No effect on momentum, streak or daily goal. |
| Trial ended (locked) | Never start and never show a heads-up. |
| Terms not accepted or first run showing | Never start; no heads-up. |

"Late" is measured against the wall clock of the missed start. The service
remembers the last tick it saw; on the first tick after a gap longer than a
minute it treats any start inside the gap as missed.

Templates started from a schedule set `RunningSprint.ActiveProfileId` from the
template (the field and its "F6's templates will set it" comment already
exist). Sealed schedules are allowed; the heads-up says the list will lock.

**Test hook:** `--short-schedules` makes the heads-up lead 5 seconds instead
of 5 minutes and the late window 10 seconds instead of 30 minutes, like the
existing `--short-timers` and `--short-sprints`. The UI suite's default
launch flags do not include it; the schedule tests add it.

### 3.4 The Schedule page

The **Sleep Blocking** tab becomes **Schedule**. The nav label and page title
change; the keyboard shortcut, the `AppPage` value's position and every
existing `AutomationId` stay.

Top to bottom:

1. **Next up** — one line: "Next: tonight 17:00 · Homework evening", or "No
   schedules yet".
2. **Your schedules** — one row each: template name, days, time and "asks
   first" when it does (changed through **Edit**, not a switch on the row),
   an on/off switch, **Edit**, **Delete**. **Add schedule** opens an inline
   editor: template picker, Mon–Sun day chips, a time field, **Ask first**.
   Save is disabled until a template and at least one day are chosen.
3. **Templates** — one row each with **Edit** (name, sprint length, shield,
   sprints in the cycle, break length, blocklist profile) and **Delete**;
   **New template** and **Restore built-ins** below the list.
4. **Sleep window** — the existing section, unchanged. Miles's Roadmap 3.7
   reworks this part later.

During a Sealed sprint the schedules and templates are read-only, like the
blocklist: every change is refused in the view model, not only greyed out.
The embedded sleep window is unchanged (it keeps its own trial lock only).

### 3.5 Templates on Today

A chip row above **Start**: one chip per template, in list order. Choosing a
chip fills in sprint length, shield, cycle count and profile; each can still
be changed before starting (a preset, not a lock). The chips are hidden while
a sprint or break runs. `Ctrl+1/2/3` still pick shields; chips get no new
shortcuts.

## 4. Soft friction

Research basis: the one sec field study (PNAS, 2023; 280 users) found the
"don't open it" option did the most, a wait helped, and a reminder alone did
not; a 2026 study found fixed friction fades within about a month. Details in
the appendix.

### 4.1 The notice

The Soft notice (`SoftOverlayWindow`) keeps its placement, its once per
sighting rule and "never over a FlowShield panel". Its content becomes:

- **Sentence** — one of four calm wordings, chosen by the try number so it
  varies without being random (for example "Discord is on your blocklist until
  5:45 PM", "You set this time aside until 5:45 PM"). All follow
  `DESIGN_SYSTEM.md` §7 and §9: no telling off, no exclamation marks.
- **Intention**, when set: "You planned: finish chapter 3".
- **Try count**: "3rd try this sprint".
- **Close Discord** — first in the row and primary in colour; works at once
  by mouse, or by Tab and then Enter or Space. It asks the app to close with
  `CloseMainWindow` only; it never kills, so the app's own "save your work?"
  prompt still appears. Never offered for a critical process (they can't be
  on a blocklist anyway). It is never the keyboard's default and never takes
  the initial focus: the notice lands up to one blocker sweep after the app
  came to the front, while the user may still be typing in it, so a keystroke
  meant for the blocked app can never close it.
- **Back to work** — secondary; the default and keyboard action. It has
  focus when the notice opens, and `Enter`, `Space` and `Esc` all mean Back
  to work. Leaves the app running and brings FlowShield forward.
- After Close the notice stays down while the app is still in front (its own
  "save changes?" prompt, or an app that ignores the ask); it can show again
  only once the app has left the foreground and come back.
- **Allow 5 minutes** — last; disabled until the wait runs out, with the
  countdown in its label ("Allow 5 minutes · 0:08"). The countdown is text, so
  it respects reduced motion.

### 4.2 Rules

In `SoftOverlayPolicy` (pure, tier 1):

- The try number is how many times the notice has been shown this sprint,
  across all apps. `Reset()` at sprint start and end already clears state; it
  also clears the count.
- Wait for try *n*: 5 s, 10 s, 20 s, then 30 s for every later try.
  `--short-timers` makes every wait 3 s (long enough for the UI suite to see
  Allow disabled before the wait runs out).
- **Close** and **Back to work** each count as one *turned back*; **Allow**
  does not.
- The "Allow 5 minutes" quiet window and the "Back to work" quiet seconds are
  unchanged.

### 4.3 Turned back, recorded

`FocusSession` gains `TurnedBack` (int, default 0), saved when the sprint
ends. It is a count only; which app is never recorded (the existing design
choice in `HistoryStats`).

- **Summary card:** "Turned back 4 times", only when above zero and only for
  Soft sprints.
- **History, this week:** "Turned back 11 times" beside distractions caught.
- **Your data:** listed with the other per-sprint fields; the data claims test
  is updated.
- It stays on the PC, so the privacy policy does not change.

### 4.4 Soft's promise, in words

Soft still never closes anything on its own. The copy changes from "the
blocked app keeps running" to "nothing is closed unless you choose to", in
the app's shield description, `README.md`, the site's shield section and the
claims registry that tier 5 checks. Firm and Sealed are unchanged.

## 5. Jump List

Right-clicking FlowShield on the taskbar shows **Start sprint** (last
settings) and **Start ‹template›** for each template. Each runs
`FlowShield.exe --start-sprint` or `--start-sprint=<templateId>`. When
FlowShield is already running, the argument is passed through the existing
single-instance pipe; otherwise it is handled after startup. Either way it
goes through the same gates as a tray start. The list is rebuilt when
templates change. A template id that no longer exists falls back to Today with
a calm toast.

## 6. Delivery

One GitHub issue per pull request, claimed before work starts. Every task is
built test-first. Each pull request adds its line to the changelog's
**Unreleased** section (the first one to merge after 1.0.9 recreates the
heading) and ticks what it ships in `LAUNCH_FEATURE_CHECKLIST.md`.

| PR | Contents | Built | Tests |
|---|---|---|---|
| A | Tier 1 model probe; `StudyTemplate`, `SprintSchedule`, `ScheduleMatcher`, seeding and saving; the Schedule page (§3.1, §3.2, §3.4) | Now | tier 1, tier 3, tier 5 |
| B | Soft friction: policy, notice, copy, claims (§4.1, §4.2, §4.4) | Now | tier 1, tier 3, tier 5 |
| C | Scheduler, heads-up card, start hook, Today chips, notification switch, `--short-schedules` (§3.3, §3.5) | After 1.0.9 | tier 1, tier 3, tier 5 |
| D | Turned back recorded and shown (§4.3) | After 1.0.9 and B | tier 1, tier 3, tier 5 |
| E | Jump List (§5) | After 1.0.9 and A | tier 1, tier 3, tier 5 |

The models and the page are one PR because a page PR stacked on an unmerged
models PR is the stacked-PR problem `CLAUDE.md` warns about. PR A (the page)
and PR C (the scheduler) merge the same night, and no release is cut from
`main` between them: the page's copy describes starts that only C performs,
and a build with A but not C would claim a feature it lacks (ruling R7). Tier 1 gains a
small probe (`automation/csharp/ModelProbe`) that compiles
`DesktopApp/Models` as it is, so the date, time-zone and Soft rules are tested
in .NET rather than only in Python mirrors.

Checks on every pull request: the fast suite (`-m "not ui and not stripe"`),
the touched UI tests on this PC one run at a time, a screenshot of each visible
change, and a spec-compliance and a code-quality review. After the last merge,
one full UI suite run on the final `main`.

Not part of this work: cutting the 1.0.10 release, deploying the licence
server, and anything on Miles's branches.

## 7. Risks

| Risk | Mitigation |
|---|---|
| A scheduled start surprises someone mid-game | Heads-up 5 minutes before by default; never starts after waking; **Skip today** is one click. |
| Scheduler and #203's sleep fix disagree about time | The scheduler compares wall-clock starts only and is built on top of 1.0.9, using whatever resume handling #203 adds. |
| **Close** at Soft loses unsaved work | `CloseMainWindow` only, never a kill, so the app's own save prompt appears. |
| Soft copy change breaks the claims test or the site | Same pull request updates the registry, the site section and `README.md`. |
| Merging before 1.0.9 ships unfinished work | Hard rule: no merge until the `v1.0.9` release exists. |

## Appendix: research summary (22 September 2026)

Five parallel research passes: dedicated blockers, focus and habit apps, user
voice, technical feasibility, and this codebase. Vendor-written comparison
blogs were treated as biased. Reddit and Microsoft Store reviews could not be
fetched.

**Convergent findings**

1. Scheduled and recurring sessions are the most requested missing feature
   (Microsoft Q&A, Steam forums, Freedom and Cold Turkey release notes; Cold
   Turkey 4.6 and 4.9 and Freedom 7.15 extended scheduling in 2025–26).
2. Friction beats walls when it offers a real way out: one sec (PNAS 2023,
   <https://www.pnas.org/doi/10.1073/pnas.2213114120>), CHI 2024
   (<https://dl.acm.org/doi/10.1145/3613904.3642370>), a 2025 Danish study of
   teenagers; habituation fades fixed friction (2026,
   <https://pmc.ncbi.nlm.nih.gov/articles/PMC13123756/>). Competitors
   converging on it: LeechBlock delays, Plucky, Intentional, FocusMe's stop
   delay and breathing break screen (Sep 2026).
3. Website blocking is the largest gap (8+ independent sources), but the only
   rule-compliant precise route is an extension with native messaging, which
   needs store accounts and the $5 Chrome Web Store fee — go-live batch
   (#166). A window-title Soft notice is a rule-compliant interim (1.0.11
   candidate).
4. "It silently stopped blocking" is the top complaint about Freedom and Cold
   Turkey; a visible enforcement log would build trust (1.0.11 candidate).
5. Store and Xbox apps run under `ApplicationFrameHost`; they can be
   identified by AUMID without admin (1.0.11 candidate).
6. One-time pricing is praised on its own; anger is aimed at subscriptions and
   paywalled basics. FlowShield's $4.99 is below every paid competitor found.

**Considered and not proposed:** body doubling, leaderboards and sync (need
accounts); trees, pets and focus audio (fade, clash with the calm tone); AI
coaches (cloud, no organic praise found); a daily game allowance (turns a
sprint blocker into an always-on monitor — owner decision, later).

**Already in FlowShield:** a weekly skip day for the streak (F15), a global
hotkey (F4), the graded escape hatch (F2).
