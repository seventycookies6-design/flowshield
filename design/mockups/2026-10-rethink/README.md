# Basalt design rethink, October 2026 (issue #368)

Three design directions for the desktop app, sketched as HTML before any XAML is
touched. Open **[index.html](index.html)** for the contact sheet.

| Folder | Direction | In one line |
| --- | --- | --- |
| [`a-dial/`](a-dial/) | **A · Dial** | The instrument: a 60-minute timer face with precise ticks replaces the empty ring, and every setting sits in one control column beside it. |
| [`b-ledger/`](b-ledger/) | **B · Ledger** | Quiet editorial typography: no cards, no sidebar, very large numerals. The next sprint is a sentence you edit. |
| [`c-causeway/`](c-causeway/) | **C · Causeway** | Material and structure: a Windows 11 shell (Mica, one content slab, settings cards) with the Causeway mark as the live shield-level readout. |

Each folder has the same six screens: Today at rest, Today during a Firm sprint
(24:13 left, "Finish the essay conclusion"), Blocked apps, Settings → License
(trial, 5 days left), History, and Today at rest in the light theme. Every
`.png` is a 1280×860 headless Chromium render of the `.html` beside it.

**Recommendation: A · Dial**, with two borrowings named at the end.

---

## What every direction fixes

These are the problems from the launch-readiness review. All three directions
fix them, each in its own way:

| Problem today | Fixed by |
| --- | --- |
| Today at rest is dominated by an empty grey ring | A: the ring becomes a scale that shows the length you set. B: no ring at all, just the number. C: the ring is replaced by the Causeway mark showing the shield you picked. |
| Template names look like plain text | All three: templates are bordered, selectable controls that show what they set (length, shield, cycle). The one that matches the current settings is shown selected, with fill and outline, not colour alone. |
| Settings → License states the trial three times and has two Buy buttons | All three: the trial is stated once, with one Buy button on the page. The sidebar or top-bar trial note is hidden on this one page, because the page is where that note leads. "License" is spelled one way, American. |
| Blocked Apps reads like an admin form | All three: the profile is one control (a dropdown or tabs). Rename, Duplicate and Delete move behind a "⋯" menu or a single link. The app count appears once. A zero counter reads "Not needed yet" in neutral grey, never rose. The picker is labelled "Add an app". |
| History heatmap has no weekday labels or legend | All three: weekday labels, a minutes legend, a date in every cell, today outlined, and minutes in each cell's tooltip / accessible name. |
| Nothing in the app says Basalt | A: an instrument face and the mark in the sidebar. B: typographic voice and the mark in the top bar. C: the mark is the shield readout, and the backdrop is stone. |

Sample data is the same everywhere: momentum 186, an 8-day streak, 2.9 hours
(174 min) this week across 5 finished sprints plus one ended early, the
blocklist Discord / Steam / Epic Games Launcher, and the three built-in
templates with their real settings from `Models/StudyTemplate.cs` (Homework
evening 45 min Firm ×3 with 10-min breaks, Exam prep 90 min Sealed, Light study
25 min Soft). The price is $4.99 one-time. Milestone titles are the real ones
from `Models/Milestones.cs`.

### Honesty check

Nothing shown is a feature the app lacks. The features shown are: templates;
length, shield, blocklist, cycle and intention; momentum, streak and the 30-day
trend; today's sprints, minutes and distractions; week stats, the heatmap, the
sprint list with intention and journal, Export your journal, and milestones;
profiles, the per-app on/off switch, Remove, the picker (Running now / Installed
/ Suggested), manual process or path entry, and notice-only websites; the trial,
Buy, license activation, and the privacy sentence about what leaves the PC
(wording from `SettingsView.xaml`). Devices are listed only once a license is
active, which matches the app (`IsPro`).

Three readouts are **new presentations of data the app already has**, not new
features. Each needs a small view-model property:

- B's "Started 16:15 / Ends 17:00" under the sprint bar.
- Showing which template matches the current settings.
- The 7-segment trial meter in A.

No celebration, no exclamation marks, no emoji. An early end is stated
neutrally ("Ended early after 9 minutes").

---

## A · Dial

**Rationale.** The product is a timer that holds a line, so the timer should be
an instrument, not a placeholder. A 60-minute face with minute ticks works like
a good kitchen timer or a camera dial. The teal arc is the length you set (at
rest) or the time left (during a sprint), and a knob marks its leading edge.
The empty ring becomes the most informative object on the screen. Everything
you decide sits in one labelled control column, read top to bottom in the order
you decide: template, length, shield, blocklist and cycle, intention, Start.
Teal appears only on state and selection: the arc, the selected segment, the
selected template, the active nav tick, and the one primary button.

**Hierarchy, screen by screen**

- **Today at rest.** Two halves.
  - Left, the dial showing what you have set, with Momentum beneath it in one panel: the number and streak, the trend chart with labelled axes, and today's three counts on one line.
  - Right, the controls. Each choice is visible as a labelled segmented control instead of hiding behind "Change", because the shield level is the product's core idea and deserves to be seen before you start.
  - One primary action: Start sprint.
  - The page subtitle ("Start a sprint and let the shield hold the line") is dropped. It said nothing the screen doesn't.
- **Today, Firm sprint.** Only the dial, larger, plus the intention above it and "Shield II · Firm · Sprint 2 of 3" below it. The sidebar dims and loses the trial note: the app never talks about buying during a sprint. "End sprint…" is a quiet secondary button. Elapsed ticks go dim and remaining ticks stay bright, so time left reads by shape and brightness, not only colour.
- **Blocked apps.**
  - The list carries its own header: profile dropdown, "⋯" profile menu, and the app count, stated once.
  - Each row has the app, its category and process, a neutral "Stopped 9 times" or "Not needed yet", the on/off switch, and Remove (×, with an accessible name).
  - Websites are a separate notice-only panel with an empty state.
  - The picker is a side panel titled "Add an app", with results labelled by source and the manual path entry demoted to a link.
- **Settings → License.**
  - One trial panel: "5 days left", a 7-segment meter, and the end date. Price and the single Buy button sit beside it.
  - "Already bought Basalt?" holds the key and email fields with a secondary Activate button.
  - The privacy sentence sits below as a note.
  - The sidebar trial note is hidden on this page.
- **History.**
  - The four stat cards become one week panel. The headline number (2.9 h) comes first, then three supporting facts as a definition list, then the Mon–Sun bar chart with a labelled minutes axis and today in bold.
  - Below are the 30-day calendar, every sprint, and milestones.
  - In the sprint list the outcome appears only when it isn't "completed", so the early end stands out without colour.

## B · Ledger

**Rationale.** The opposite move: take everything away until only type is
left. There are no cards and no sidebar, and hierarchy comes entirely from size
and weight. A 208 px "45:00" at rest and a 288 px "24:13" during a sprint sit
against 14–24 px text and hairline rules. The configuration is a sentence: "45
minutes behind a Firm shield, blocking Default (3 apps), for 3 sprints with
10-minute breaks." Each bold, underlined phrase is a button that opens its
choices. It is the most progressive-disclosure design of the three: a person
who uses a template never sees a control they don't need, but the full plan is
always readable. History opens with a sentence instead of four boxes.

**Hierarchy, screen by screen**

- **Today at rest.**
  - The number first, then the sentence, then the shield's promise in one line, the intention, and Start.
  - Templates are a ruled list on the right with their specs. The selected one has a teal rule and a check.
  - Momentum is a typographic block (186, then the streak), with the trend and today's line below.
  - Navigation moves to a top bar. The trial note and a Buy link sit at its far right, as text, never a second teal button.
- **Today, Firm sprint.**
  - The screen is the number. A three-bar level meter with "Shield II · Firm · Sprint 2 of 3" sits above it.
  - Below it, a thin timeline runs from "Started 16:15" to "Ends 17:00", with the elapsed part in teal and a marker at now. It is drawn as a timeline so it can't be misread as "54% done".
  - Then the intention at 30 px, and "End sprint…".
- **Blocked apps.**
  - A ledger table: App and process, Category, Times stopped, Blocking (the switch), and a Remove link.
  - The profile is an inline dropdown phrase in the header, with one "Rename, duplicate or delete" link.
  - One sentence under the table says what happens to these apps at each shield level.
  - Below the table, "Add an app" (search and results) and "Websites · notice only" sit side by side.
- **Settings → License.**
  - Settings gets a vertical sub-navigation.
  - The License page reads as prose: "You're on the free trial, with 5 days left." That is the only statement of the trial. Then the end date and price, and one Buy button.
  - Below a rule, "Have a license key?" with underlined fields.
- **History.**
  - The lede sentence carries all four of this week's facts.
  - Below it sit the calendar heatmap, a ledger of every sprint (When / Length / Shield / Outcome / Intention and journal), and milestones as marginalia.

## C · Causeway

**Rationale.** Lean into the material the product is named after, and into
Windows 11 itself:

- **The shell.** A Mica backdrop (on Windows 10, a flat `backdrop` colour with a faint basalt grain), a title bar merged into it, the nav and an ambient status column on the backdrop, and the content on one raised slab. This is the WinUI layout.
- **The mark at work.** The Causeway mark stops being decoration. Its lit tops are the shield level (1 Soft, 2 Firm, 3 Sealed), exactly as the brand README defines for the tray. On Today it is drawn large, so choosing a shield visibly lights the columns.
- **Data in the stone's shapes.** Week bars have a column's hexagon top, and the 30-day calendar is a honeycomb, because basalt seen from above is hexagonal.

Settings uses the Windows 11 settings-card pattern.

**Hierarchy, screen by screen**

- **Today at rest.**
  - Templates come first, as tiles with a small mark showing each one's shield.
  - Then one hero card: the large mark (Firm, two columns lit), "45:00", the shield's name and promise, and the three-way shield control.
  - Below are length, blocklist and cycle as three labelled combo boxes, then the intention and Start sprint on one row.
  - Momentum and streak move to the sidebar as ambient status, so Today does one job: set up and start.
- **Today, Firm sprint.** The mark and the time are a single lockup: the screen is literally the shield level and the time left. Under the time, 45 one-minute segments drain right to left, with the sprint count and the shield's promise. The sidebar dims and loses status and trial.
- **Blocked apps.**
  - Profiles are tabs with their app counts, "New profile", and a "⋯" menu for the rest.
  - Apps are tiles (icon, switch, name, category, process, a neutral counter, and remove).
  - Websites are a settings-card row.
  - "Add an app" is a docked side sheet.
- **Settings → License.**
  - A header card with the Basalt tile, then "Free trial · 5 days left · everything unlocked until Wednesday 21 October", the price and the one Buy button.
  - "Activate a license key" is an expander, shown open.
  - "Your devices" is a disabled row until a license is active.
  - "What leaves this PC" is a row with the privacy policy link.
- **History.** A week card (four stats in a 2×2 grid, column-topped bars), then the honeycomb calendar, the sprint list (each row led by a small mark showing its shield) and milestones.

---

## New tokens and measured contrast

Measured with the WCAG 2.x formula against the token values in
`design/tokens.json`. Alpha tokens are flattened over the background they sit on.
Text pairs must reach 4.5:1; meaningful graphics 3:1.

| Token | Dark | Light | Used by | Pairs (dark / light) |
| --- | --- | --- | --- | --- |
| `backdrop` | `#1E1F22` | `#E3E2DD` | C: the Mica fallback, behind the nav | text 14.06 / 13.00 · text-muted 7.58 / 5.67 · text-faint 5.35 / 4.71 · primary (nav tick) 5.65 / 4.95 |
| `heat-1` | `#223F39` | `#D3E3DD` | heatmap 1–25 min | label `heat-ink-1` 9.75 / 12.69 |
| `heat-2` | `#265A4F` | `#9CC5BA` | heatmap 26–45 min | label `heat-ink-2` 6.74 / 8.92 |
| `heat-3` | `#2B7466` | `#2C7D6E` | heatmap 46–60 min | label `heat-ink-3` 4.72 / 4.56 |
| `heat-4` | `#4FBEA7` (= dark `primary-hover`) | `#0C5C4F` | heatmap over 60 min | label `heat-ink-4` 7.55 / 7.31; against `surface` 7.19 / 7.31 |
| `heat-ink-0…4` | `text-muted`, `text`, `text`, `text`, `primary-ink` | `text-muted`, `text`, `text`, `primary-ink`, `primary-ink` | the date numbers in heatmap cells | 0 min cell (on `track` over `surface`): 6.04 / 5.82 |
| `tick` | `#909398` (= `text-faint`) | `#606266` (= `text-faint`) | A: dial ticks inside the set length | graphic on `surface` 5.29 / 5.65 |
| `tick-dim` | `#3A3C3F` | `#C9C8C3` | A: ticks outside the set length, elapsed ticks | 1.47 / 1.55. Deliberately inactive: the same information is carried by the arc and the number |
| `field` (role, not a colour) | `bg-soft` | `surface-2` | text field and segmented-control wells | — |

Existing pairs these mockups lean on, for the record:

- `text` on the selected segment (`primary-soft` over the field): 10.90 / 13.68.
- `primary-ink` on `primary` (the Start button): 5.87 / 5.94.
- `primary` as a graphic on `surface` (dial arc, bars): 5.59 / 5.94.

Heat fills form a lightness ramp, so they stay ordered for colour-blind
readers. Adjacent steps are close, as in any sequential scale: 1.15–2.44 dark,
1.05–2.60 light. That is why every cell also carries its date and its minutes
in the tooltip and accessible name, and the legend gives the bands in numbers.

One new **use** of an existing token: in the light theme the Causeway mark's
lit tops use light `primary` `#0C6B5C`. The brand README defines lit tops only
on dark. This needs Miles's sign-off as owner of the mark.

## Accessibility notes (all directions)

- **Focus.** Each set shows the 2 px `focus-ring` outline on one control (the app search field, and in C the intention field) to show it is designed for. It reuses the existing `FocusVisual`.
- **Colour is never the only signal.**
  - Selected segments and tiles also get an outline and a heavier weight.
  - Shield levels carry a name and numeral, plus bars, a glyph or lit columns.
  - Elapsed versus remaining time is also brightness and shape.
  - An early end is a sentence.
  - Zero counters are words.
- **200% text scale.** Every layout is a column grid. At 200% the A and C two-column screens (Today, Blocked apps, History) fall back to one column, using the adaptive breakpoint the app already has (#191). Dials, marks and giant numerals sit in a `Viewbox` with `StretchDirection="DownOnly"`, as the timer already does, so they shrink rather than clip. B's sentence wraps naturally, because its tokens are inline.
- **Reduced motion.** Nothing here needs animation. The dial arc, B's timeline and C's segments step once a second. With motion allowed, a 150 ms ease on the arc end is the most that is proposed, and `Motion.cs` zeroes it.

---

## What is hard or risky to build in WPF, and how

**Shared**

- **Letter-spacing.** WPF `TextBlock` has no tracking property. The mockups use −2% to −5% tracking on large numerals. The big sizes should use the embedded `InterDisplay-SemiBold.ttf`, whose spacing is already tighter, and accept slightly looser headings than the HTML. Don't fake tracking with per-glyph `Glyphs` elements: that breaks accessibility and selection.
- **Moving controls into menus.** Rename, Duplicate, New profile and Delete become `ContextMenu` items behind "⋯". The tier tests find these buttons by `AutomationId`. Keep the ids on the `MenuItem`s, and update the test driver to open the menu first. Plan this as part of the Blocked apps PR.
- **The selected template.** It needs a derived view-model property, true when the template's length, shield, cycle and profile equal the current settings. It is not a new feature, but it is new logic and gets a test.

**A · Dial.** Medium risk overall; the dial is the only real work.

- **Drawing the dial.** A custom `FrameworkElement` with `OnRender`: 60 tick lines, four numerals and an `ArcSegment`. It invalidates once a second; there is no per-frame work. `UseLayoutRounding` keeps 1 px ticks crisp.
- **Sprints over 60 minutes.** A 60-minute face can't show a 90 or 240-minute sprint. The face should step its scale with the sprint: 60, 120 or 240 minutes, renumbered (0/30/60/90 for 120). The tick density stays the same, and the number in the centre stays authoritative.
- **Screen readers.** The dial needs an `AutomationPeer` (`ProgressBar` pattern, the value in minutes).
- **The rest.** Segmented controls are the existing `Segment` radio style. The trial meter is an `ItemsControl` of seven `Border`s. Lowest risk of the three.

**B · Ledger**

- **The sentence composer** is the hard part: a `WrapPanel` mixing `TextBlock` runs with token `Button`s, each opening a `Popup` that holds the segmented choices.
  - Keyboard: Tab between tokens, Enter or Space to open, Escape to close.
  - Each token needs an `AutomationProperties.Name` that states the setting ("Shield, Firm").
  - At 200% the wrap must stay readable.
  - Allow time for focus, Narrator and popup placement testing.
- **The top navigation** replaces the sidebar, which changes `MainWindow` structure and every nav test path.
- **Giant numerals** at 208–288 px need the `Viewbox` guard: "1:29:59" is much wider than "24:13".
- Medium-to-high risk; most of it is interaction, not drawing.

**C · Causeway.** Highest risk, mostly in the window chrome.

- **Mica.** In WPF on .NET 8 it means:
  - a transparent window background;
  - `DwmSetWindowAttribute` with `DWMWA_SYSTEMBACKDROP_TYPE` (Windows 11 22H2 and later) and `DWMWA_USE_IMMERSIVE_DARK_MODE`;
  - `WindowChrome` with the client area extended into the title bar.
- **The merged title bar** forces custom caption buttons. Keeping Windows 11 Snap Layouts on the maximise button means handling `WM_NCHITTEST` and returning `HTMAXBUTTON`. This is the "easy to get wrong" area the old design doc warned about. Mica also needs a solid fallback for Windows 10, high contrast and a disabled backdrop: the `backdrop` token plus a 180 px grain `ImageBrush` (tiled, absolute viewport, at most 10% opacity).
- **The mark.** The large mark is 12 `Polygon`s copied from the brand SVG, with the lit-top fills bound to the shield level. That part is easy. At 176–232 px the brand's 1-unit joints render at about 3 px, which is correct to the spec but heavy. Ask Miles whether display sizes may use thinner joints.
- **The honeycomb calendar** is a `Canvas` with computed polygon positions. It reads less directly than a square grid: weeks zigzag. That costs legibility for identity.
- **Settings cards and the expander** map directly to existing styles.

---

## Recommendation: A · Dial

Reasons:

1. **It answers the brief's first principle most directly.** "During a sprint the time left and the shield level are the screen." A's sprint screen is exactly that: one instrument, bright ticks for what is left, the shield named under it. At rest, the same instrument turns the review's worst problem, the empty ring, into the clearest readout on the page.
2. **It fixes hierarchy without hiding the product's core idea.** The shield level is visible and explained before you start, and the reading order is the decision order. B hides more, which is elegant for a template user but makes Firm versus Sealed easy to miss. C spends its biggest element on brand.
3. **It is the cheapest to build well.** One custom control (the dial) plus restyles of controls that already exist. No window-chrome work, no composer popups. It can land in the small PRs #368 asks for: Today, then Blocked apps, then License, then History.
4. **It reads as Basalt without leaning on illustration.** The precision of the face, the ticks and the tabular numerals is the "well-made instrument" identity. The mark stays where the brand puts it.

Two borrowings worth taking into A:

- **From B, History's lede sentence** ("You focused for 2.9 hours across 5 finished sprints…") in place of A's definition list. It states the week once, in words, and is the best single idea in B.
- **From C, the Causeway lit tops as the shield glyph** beside the dial during a sprint, matching the tray icon. Only if Keenan and Miles agree to relax the brand note that shield-level glyphs "stay shields". Otherwise keep §6's shields, as rendered.

If the deciding goal is identity over cost, choose C, but schedule the
window-chrome work as its own PR, with a Windows 10 and high-contrast pass on
the VM bench.

---

## Files

- `index.html`: contact sheet of all 18 renders, linked to their HTML.
- `a-dial/`, `b-ledger/`, `c-causeway/`: one self-contained `.html` per screen (inline CSS, no network, no scripts) and its `.png`. Fonts load from `../../../../Website/fonts/InterVariable.woff2`.
- `src/`: the generator that writes the HTML and renders the PNGs (Python plus Playwright Chromium, headless), with shared tokens, sample data, icons, the brand mark polygons and the chart builders in `common.py`. Rebuild with `python design/mockups/2026-10-rethink/src/build.py` (or pass `a-dial`, `b-ledger` or `c-causeway` for one direction). The build checks every PNG is 1280×860, that Inter loaded, and that nothing overflows its box or the window.
