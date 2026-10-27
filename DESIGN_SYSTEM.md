# Basalt design system

One visual language for the desktop app and the website, so that a customer
moving from the site to the installer to the app sees the same product. It
builds on what already exists: the stone and teal palette from the site
redesign (#27), which the app adopted in #32.

**Part A is binding.** Every app and site change follows it. **Part B describes
the current implementation.** It is a starting point, not a ceiling (#366).

The features these rules will be applied to are listed in
**`LAUNCH_FEATURE_CHECKLIST.md`**.

---

## Part A — Binding

### The idea: a calm instrument

**Basalt should feel like a precise, quiet tool you trust, not a wellness
app and not a game.**

Basalt sits in a space no product in the category occupies (Part B §1): **the seriousness of a utility
with the calm and clarity of a well-made instrument.** Think of a good watch
face or a camera's controls. Everything has a purpose, the important number is
large, and nothing flashes for attention.

### Six principles

1. **One thing matters at a time.** During a sprint, the time left and the shield are the screen. Everything else recedes.
2. **Calm is the default; colour means something.** Surfaces are neutral stone. Teal marks the active or primary thing. Amber and rose appear only for warnings and problems.
3. **Strength is shown, not shouted.** Shield levels escalate through shape and fill, not alarm colours or exclamation marks.
4. **Honest over impressive.** Real screenshots, real numbers, plain words. Never a mock-up of a feature that doesn't exist, never generated people or UI.
5. **Kind, never guilty.** Ending early, a broken streak or a lost day are stated neutrally, with a way forward.
6. **Accessible by construction.** Every colour pair passes WCAG AA, every control works from the keyboard, and motion respects the reduce-motion setting.

### Information hierarchy

- Each screen has one job. The same fact is not stated twice on one screen.
- Each view has one Primary action.
- Controls appear where and when they are needed (progressive disclosure).
- Every empty state points to the next action.
- Numbers show units and context: charts have legends; calendars have weekday labels.

### Hard rules

- **Tokens:** colours come only from `design/tokens.json` through `tools/build_tokens.py`; no hex literals in views; every colour reference in XAML is a `DynamicResource`, because the light/dark swap depends on it.
- **Contrast:** every token pair used for text passes measured WCAG AA (4.5:1); measure any new pair before shipping, so readable text is proved rather than guessed (§2 keeps the reference table).
- **Meaningful colour:** `ok`/`warn`/`danger` mean status, never decoration; teal means state, selection or progress, so colour carries a consistent meaning.
- **Accessibility:** controls are keyboard reachable, have a visible 2 px focus ring and accessible names; colour is never the only signal, text survives 200% scaling, and reduced motion is honoured everywhere (app: `SystemParameters.ClientAreaAnimation`; site: `prefers-reduced-motion`), so everyone can use the product.
- **Calm:** nothing bounces, spins or shakes; no confetti, fireworks, sounds or alarm visuals; state failure neutrally, because the product helps without celebrating or blaming.
- **Surfaces:** no decorative gradients or glows; glass/acrylic/Mica is allowed only for the window frame and navigation rail as a Windows 11 system backdrop, with AA text contrast measured over the worst case and a solid token surface on Windows 10 or when transparency effects are off; cards, controls and text never sit on translucent surfaces, so content stays legible.
- **Texture:** restrained material texture is allowed in the app and on the site, never under text, cards or controls, with contrast unaffected and off with reduced transparency where applicable; no photographs of rock or marble veining behind copy, so material never competes with content.
- **Title bar:** a custom or extended title bar keeps Snap Layouts, the system menu, keyboard access, accessible names and correct drag regions, so changing the frame preserves Windows behaviour.
- **Imagery:** real product only, with sample data and never a real blocklist or license; no stock photos, AI-generated people, fake device frames or mock-ups of unshipped screens, so marketing stays honest and private data stays private.
- **Voice:** plain, specific words; no exclamation marks or emoji in product copy; use the binding word list below, so the product is clear and kind.
- **Brand:** copy the Causeway mark from `design/brand/`, never redraw it, so the same mark reaches every surface.
- **Licences:** fonts and icons stay licensed and embedded or self-hosted (Inter OFL, Lucide ISC), with notices shipped and no runtime web-font services, so they work offline and their terms are met.
- **Automation:** keep existing `AutomationId`s and put ids on controls, not layout panels, because UI Automation does not surface panel ids (#134).
- **Blocker:** follow `CLAUDE.md`'s deliberately timid blocker rule: protect critical processes; no admin rights, drivers, services or hosts-file edits, so focus never puts the machine at risk.

### Binding words and honesty

Basalt talks like a calm, competent friend who respects your time.

| Use | Not |
| --- | --- |
| sprint | session, pomodoro, focus block |
| shield, shield level | mode, strictness, difficulty |
| Soft, Firm, Sealed | Level 1/2/3 on their own |
| momentum | score, points, XP |
| blocklist | blacklist, block set |
| buy Basalt, license | upgrade, Pro, subscription |
| free trial | free version, free plan |
| ended early | failed, gave up, quit |

Issue #365 is an owner decision and may revise the shield vocabulary after the
Basalt rename. Until then, this word list stays binding. Customer-facing text
spells it **license**, the American way (decided in #370); code identifiers,
`AutomationId`s and API fields keep their existing names.

- Never describe an unshipped feature (the tier 5 claims test enforces this for pricing).
- Name a competitor or quote its price only after re-checking the source; see the checklist's F24.
- Prices always include "plus tax where it applies" near the number on the site.
- Video has no sound, a poster and a text description, so it remains calm and accessible.

### Changing the design

Part B describes what shipped and is not binding. A design PR may change the
design and Part B together in the same PR. No separate "doc first" PR is needed.
Include before/after screenshots in both themes and contrast measurements for
any new colour pair. Accessibility must not regress. Better solutions are
welcome; Part B is a starting point, not a ceiling.

---

## Part B — Current implementation (descriptive, not binding)

These are implementation notes, values and adoption records, not rules for
future designs. The original section numbers are kept for existing references.
Engineering facts are labelled: a design can change, but WPF's behaviour still
needs accounting for. Part A's customer protections apply throughout.

### 1. Research background

The competitor research (14 September 2026, summarised in the checklist) found
the category splits into:

| Style | Seen in | What it communicates |
| --- | --- | --- |
| Bright green, cartoon illustrations, collectables | Forest | Fun, playful. Some users find it childish for serious work. |
| Gradients, stock photography, generic "wellness" look | Opal, Freedom | Friendly, lifestyle. Hard to tell apart. |
| Dark, dense, settings-heavy utility | Cold Turkey, FocusMe | Powerful, serious. Often described as intimidating. |
| System-native, muted | Windows Focus Sessions | Built-in, safe. Forgettable. |

---

### 2. Colour

#### Tokens

Both themes share the same token names in the app and on the site. **System is
the app's default (§12); the site follows the visitor's system setting.**

The neutrals are stone (#336): light is honed marble, a near-neutral white
with a trace of warmth; dark is basalt, a charcoal with a faint blue cast,
never pure black, so light text doesn't bloom. Values marked **change** fixed
contrast failures measured on 14 September 2026 (see "Contrast" below).

| Token | Dark | Light | Use |
| --- | --- | --- | --- |
| `bg` | `#141517` | `#ECEBE7` | Window and page background |
| `bg-soft` | `#191A1C` | `#E2E1DC` | Navigation rail, alternating bands |
| `surface` | `#1F2022` | `#F7F6F3` | Cards, panels, dialogs |
| `surface-2` | `#27292B` | `#FCFBF9` | Controls, inputs, hover fills on surfaces |
| `text` | `#EDEDEB` | `#1C1D1F` | Headings, primary text, large numbers |
| `text-muted` | `#AEB0B3` | `#54565A` | Body copy, labels |
| `text-faint` | `#909398` | `#606266` | Captions, hints, placeholders |
| `primary` | `#3AA892` | `#0C6B5C` | Primary buttons, active states, the timer ring, focus |
| `primary-hover` | `#4FBEA7` | `#095548` | Hover and pressed primary |
| `primary-ink` | `#0B1F1B` | `#F7F6F3` | Text and icons on `primary` |
| `primary-soft` | `#3AA892` at 20% | `#0C6B5C` at 12% | Selected chips, soft highlights |
| `ok` | `#5EC987` | **change** `#2F7D4A` → `#276A3E` | Completed, success |
| `warn` | `#E0B35A` | **change** `#9A6B1F` → `#7A5413` | Trial ending, "are you sure" |
| `danger` | `#EF7A88` | **change** `#B33A4A` → `#A3334A` | Errors, destructive actions |
| `border` | `text` at 12% | `text` at 12% | Card and control outlines |
| `border-strong` | `text` at 22% | `text` at 22% | Hovered or focused outlines, toasts |
| `focus-ring` | `primary` at 50% | `primary` at 45% | Keyboard focus outline, 2 px |
| `scrim` | `bg` at 95% | `bg` at 92% | Behind the lock screen and dialogs |
| `shadow` *(doc amendment, A3, #147)* | `#000000` | `#000000` | Opaque black for the `DropShadowEffect.Color` behind cards; the effect's own `Opacity` does the fading, so this stays a fixed black in both themes rather than a themed pair. App-only — the site expresses card elevation as `shadow-soft`/`shadow-lift` rgba strings in CSS, which encode the same black directly. |

#### Colour use in the current design

- **Legacy names removed.** `Violet`, `VioletBright`, `Cyan`, `Glass*`, `Accent` and `WindowBg` are gone from `Theme.xaml`, and `--violet`, `--violet-bright`, `--cyan`, `--grad` and `--glass*` are gone from `styles.css`. Colour references use the token names above. (The site keeps a short alias block — `--bg`, `--ink`, `--edge` and friends — for the legal and success pages; those are token names under a shorter spelling, not dead colours.)
- **Token references.** Every colour in XAML and CSS comes from a token. The lock screen's former literal hex backdrop was removed in #180 (A3).
- **Teal is structural, not decorative.** Teal may appear in as many places as a screen needs, provided it always means one of three things:
  - **state**: something is on, active or running (an engaged shield, an enabled toggle, the tier badge's trial dot);
  - **selection**: the current navigation item, the chosen chip, the focused control;
  - **progress**: the timer ring, progress bars, chart series.

  The primary action is teal because it is the thing that changes state. Nothing is teal just to look branded: no teal headings, dividers, borders, illustrations or background washes. If everything is teal, nothing is. What earns the colour is that it always means the same thing, not that it is rare. (Replaces the earlier "teal is scarce" rule, #147.)
- **Status colours are for status only.** Amber and rose never decorate. `ok` green is for "done", not for "go".
- **Depth:** surface steps and soft shadows replaced the purple glows in #32. Part A sets the conditions for system backdrops and material texture.

#### Contrast reference

Measured against WCAG 2.1 on 14 September 2026 (normal text needs 4.5:1), and
again on 5 October 2026 for the stone neutrals (#336):

| Pair | Dark | Light | Result |
| --- | --- | --- | --- |
| `text` on `bg` | 15.6 | 14.1 | Pass |
| `text-muted` on `bg` | 8.4 | 6.2 | Pass |
| `text-muted` on `surface` | 7.5 | 6.8 | Pass |
| `text-faint` on `surface` | 5.3 | 5.7 | Pass (failed both at 4.07 / 3.27 before 14 September) |
| `primary` on `bg` | 6.3 | 5.4 | Pass |
| `primary-ink` on `primary` | 5.9 | 5.9 | Pass |
| `warn` on `bg` | 9.4 | 5.7 | Pass (light failed at 3.68 before 14 September) |
| `ok` on `bg` | 8.9 | 5.5 | Pass (light failed at 3.98 before 14 September) |
| `danger` on `bg` | 6.8 | 5.6 | Pass (light was borderline at 4.56) |

Any new token or pairing gets measured the same way before it ships.

---

### 3. Typography

#### One family, everywhere

The site formerly used **Syne** for headings and **Source Sans 3** for text,
and the app used **Segoe UI Variable**. Both now use a single family,
**[Inter](https://rsms.me/inter/)** (decided in #147; shipped in #171 and #172).

There is no separate display face. Hierarchy comes from size, weight and
tracking: headings are heavier and tighter, body text is regular and open.
This is how Linear and Raycast work, and it matches the "instrument" idea in
section 1: one precise voice, not two competing ones.

| Role | Font | Where |
| --- | --- | --- |
| Headings | **Inter** 600–700, negative tracking (see scale) | Site hero and section headings; the app's page titles and the lock screen headline. |
| Text and UI | **Inter** 400/500/600 | Everything else, in both. |
| Numbers | **Inter** with tabular figures (`font-variant-numeric: tabular-nums`; `Typography.NumeralAlignment="Tabular"` in WPF) | The timer, stats, prices, momentum, so digits don't jiggle as they change. |
| Licence keys | Cascadia Mono, then Consolas | Keys and anything the user must copy exactly. |

- **Fallback** in both: `Segoe UI Variable`, `Segoe UI`, then `system-ui`.
- **In the app:** Inter is embedded as a resource in `DesktopApp`, with the SIL Open Font License (`OFL.txt`) alongside the font files. Only the weights the scale uses are embedded. Part A keeps licensing and offline delivery binding.
- **On the site:** Inter is served with `font-display: swap` and a fallback tuned so text doesn't shift when the web font loads. The Syne and Source Sans 3 links were removed in #172.
- **Tracking** follows the roles in the scale below. **Engineering fact:** WPF has no letter-spacing property on `TextBlock`, so heading tracking is approximated with weight or the static Inter Display cut for `display` and `timer` sizes. The app and site match visually rather than numerically.

#### Scale

A shared scale. Sizes are in px for the app; the site uses the matching `rem`
values in `styles.css` (`--text-*`).

All roles are Inter.

| Token | Size / line height | Weight | Tracking | Use |
| --- | --- | --- | --- | --- |
| `display-xl` | 56 / 60 (site hero) | 700 | −3% | Site hero only |
| `display` | 30 / 36 | 600 | −2% | Page titles, lock screen, section headings |
| `title` | 18 / 24 | 600 | −1% | Card titles, dialog titles |
| `body` | 14 / 21 (app), 17 / 27 (site) | 400 | 0 | Paragraphs, list items |
| `label` | 13 / 18 | 500 | 0 | Buttons, field labels |
| `caption` | 12 / 17 | 400 | 0 | Hints, timestamps |
| `eyebrow` | 11 / 14, uppercase | 600 | +6% | Section labels such as "MOMENTUM" |
| `timer` | 64 / 64, tabular | 600 | −2% | The sprint countdown |
| `stat` | 36 / 40, tabular | 600 | −1% | Momentum, minutes, prices |

- **Sentence case** everywhere except eyebrows.
- **Current weight range:** no more than three weights on one screen (400, 500 and 600, with 700 reserved for the site hero). This is an implementation choice. With one family, weight does the work a second face used to do.
- **Tighter as it gets bigger:** negative tracking only at `title` size and above; small text stays at 0 so it remains legible.

---

### 4. Space, shape and depth

- **Spacing scale (4-based):** 4, 8, 12, 16, 24, 32, 48, 64 for padding and gaps. Card padding is 24, space between cards 16, page margins 32 in the app.
- **Corner radius:** 6 for small chips and tags, 10 for buttons, inputs and toggles, 14 for cards and dialogs, and fully round for pills and the tier badge. The app previously used 8, 10, 11, 12, 13 and 14 interchangeably; normalised to this set (A2, issue #147).
- **Where these values live:** corner radii are three resources — `RadiusChip`/`RadiusControl`/`RadiusCard` — in `DesktopApp/Styles/Theme.xaml`, and values in `Website/styles.css`. The eight spacing numbers are literals per element. Neither is in `design/tokens.json`, which is colour only (§14); a future issue may unify them the way colour is unified.
- **Engineering fact — round shapes:** fully round elements set `inf:Pill.IsRound="True"`, because WPF draws an oversized radius such as 9999 as an ellipse rather than clamping it like CSS.
- **Stone (currently on the site, #336).** The product is named after basalt, so the site shows the material in two restrained ways:
  - **Grain** on the page ground (`body`, and the `bg-soft` bands) through `--texture-grain`: an inline SVG noise, under 1 KB, dark specks in light mode and pale ones in dark, each at most about 8% opaque. It never goes on a surface: cards, buttons and text boxes stay solid, so every contrast figure in §2 still holds.
  - **Basalt columns**: one faint row of columns seen side-on, standing on the hero's bottom edge inside its padding (`.hero::after`). It is drawn in `text` at 13% through a mask, so it follows the theme, and it is never placed behind text or a control.
  - Depth comes from surface steps and shadows. Part A allows restrained material texture in the app too, with the same protections for content and contrast.
- **Borders:** 1 px `border` on cards and controls; `border-strong` on hover and focus.
- **Shadows**, currently two levels:
  - `soft` for cards on the site and for toasts;
  - `lift` for dialogs and the lock screen card.
  - The dark design favours a surface step over a shadow.
- **Layout:**
  - **App:** a 240 px navigation rail and a content area aligned with its page title. The content grows with the window up to 1280 px (`PageMaxWidth` in `Theme.xaml`); past that, the title and page stay together in a 1280 px column centred beside the rail, so an ultrawide screen doesn't spread a page's cards apart (#406). The mouse wheel over the margins either side still scrolls the page.
  - **The app adapts to its window.** Each breakpoint reads the width the element actually has, not the window's, so a view responds to its own space:
    - **Rail:** below a 1000 px window client width it compacts to 72 px of icons, with the names as tooltips (`MainWindow.CompactRailBelow`).
    - **Card grids** (`inf:AdaptiveColumns`: History, Schedule) lay cards out in rows, left to right in reading order, as many columns as fit at the panel's minimum width, up to its maximum. Cards in a row share the row's height, so neighbours' edges line up (#406; this was a masonry layout that left them uneven). The column count is balanced over the rows, so five cards that would fit four abreast sit three and two. `FillLastRow` lets a short last row share the full width, for rows of unlike cards. Gaps are in the panel's `Spacing`, rather than the cards' margins.
    - **Settings** is one column of full-width cards, like Windows' own Settings: its groups hold one to three cards each, and no row of them could line up at every width.
    - **Two-pane pages** give the side pane a proportional width with a minimum and maximum: Today's stats (`0.4*`, 300–420 px) and Blocked Apps' picker (`0.65*`, 260–460 px). Below a view width of 700 px (Today) or 780 px (Blocked Apps), the side pane stacks under the main one and the page scrolls.
    - **Fully round shapes** use `inf:Pill.IsRound`; see the engineering fact above.
    - Settings is six labelled groups with a section rail; below 900px the rail becomes a chip row. The rail marks the current group like the main rail does: a `surface-2` fill and a `primary` bar (an underline in the chip row).
    - **Today's timer ring** is drawn at 222 px and scaled as a whole to about a third of the page's height, up to 320 px, so a tall window isn't left half empty.
  - **Engineering fact — fixed-height controls:** vertical padding consumes the space available for content. `BtnBase` fixes the height at 40, and navigation rows are 44 with no vertical padding, leaving room for their 20 px icons.
  - **Site:** a 1120 px maximum width (`--maxw`).
  - **Minimum app size:** 800 × 540 (Roadmap 1.13).

---

### 5. Icons

- **Navigation glyphs:** Lucide replaced the Unicode glyphs (`◷`, `⊘`, `☾`, `⚙`) in #151. Those rendered differently across Windows versions and did not match each other. Every rail icon covers the same square 18 of the 24 grid, so `Stretch=Uniform` draws them at one size; the Settings gear is an eight-tooth gear drawn for that square (#406), since the earlier one covered 15 × 19 and drew tall. A tier 5 test measures each rail icon's bounds.
- **Outline icons:** the design uses [Lucide](https://lucide.dev), at 1.75 px stroke on a 24 px grid, as XAML `Path` geometry and inline SVG on the site. Its ISC notice ships with the icons; Part A keeps that requirement binding.
- **Sizes:** 16 px inline with text, 20 px in navigation and buttons, 24 px for feature headings.
- **Icons inherit** the text colour of their context; only an active item's icon is `primary`.
- **The Causeway mark** (three basalt columns; source SVGs and spec in `design/brand/`) is the only filled brand icon. Keep it identical everywhere: the site favicon and header, the app's navigation, title bar and taskbar icon (Roadmap 1.6), the tray icon and the installer. Copy it from `design/brand/`, never redraw it; `tools/build_icons.py` builds the app's `.ico` files from those SVGs. The tile (`basalt-icon.svg`) is the same in both themes; the bare mark beside the wordmark swaps between its on-light and on-dark copies. Lit column tops (teal) mean a sprint is running: `FlowShield.Running.ico` is the Firm tile, the tray's fallback when its minute countdown can't be drawn. The shield-level glyphs in §6 stay shields.

---

### 6. Shield levels: the signature visual

The three shields are Basalt's most distinctive idea, so they get a
consistent visual language, used identically on the Today page, the site,
notifications, the tray and the summary card.

| Level | Glyph | Fill | Name and promise |
| --- | --- | --- | --- |
| I · Soft | Shield outline with **one** bar | Outline in `text-muted` | "Soft — notes distractions and nudges you" |
| II · Firm | Shield outline with **two** bars | Outline and bars in `primary` | "Firm — closes blocked apps" |
| III · Sealed | Solid `primary` shield with **three** bars and a small lock notch | Solid `primary`, glyph in `primary-ink` | "Sealed — closes apps and locks the list until the sprint ends" |

- **Strength escalates through fill and bars, never through colour changes** such as green to amber to red. That would read as danger and clash with principle 3.
- **Selected state:** the chip gets `primary-soft` fill and a `primary` outline; others stay `surface-2`.
- **During a sprint** the active shield's glyph sits beside the timer and in the tray icon.
- **Shared glyphs:** a XAML `DrawingImage` resource and an SVG symbol on the site, built once per platform.

---

### 7. Components

Each component is defined once. In the app it's a style in `Theme.xaml`; on the
site it's a class in `styles.css`. Names match across the two.

#### Buttons

| Variant | App style | Site class | Look | Use |
| --- | --- | --- | --- | --- |
| Primary | `BtnPrimary` | `.btn-primary` | `primary` fill, `primary-ink` label | One per view: Start sprint, Buy Basalt, Activate |
| Secondary | `BtnGhost` | `.btn-ghost` | `surface-2` fill, `border`, `text` label | Alternatives: Skip break, Copy key |
| Quiet | `BtnQuiet` | `.btn-quiet` | No fill, `text-muted` label, fill on hover | Low-emphasis: Deactivate, Open log |
| Destructive | `BtnDanger` | `.btn-danger` | `surface-2` fill, `danger` label and border | Delete everything, End sprint anyway |

- **Height** 40 (app) or 44 (site), radius 10, horizontal padding 20, `label` type.
- **States:** hover uses `primary-hover` or `border-strong`; pressed darkens by one step; disabled is 45% opacity with no hover; focus shows a 2 px `focus-ring` offset by 2 px.
- **Button text is a verb:** "Start sprint", not "OK".

#### Cards

- **Look:** `surface` fill, 1 px `border`, radius 14, padding 24.
- **Heading:** an optional `eyebrow`, then a `title`.
- **Stat cards:** one `stat` number, one `caption` label, and optionally a delta in `ok` or `text-muted` (never `danger` for a momentum drop; see Voice).

#### Form controls

- **Text inputs:** 40 high, `surface-2` fill, `border`, radius 10; `border-strong` on hover; `focus-ring` on focus. An empty field shows its `AutomationProperties.HelpText` as a `text-faint` placeholder (4.74:1 dark, 5.91:1 light on `surface-2`).
- **Date pickers** (`Styles/Pickers.xaml`) look like a text input with a calendar icon; the calendar drops down on a card surface, its selected day drawn like a selected segment.
- **Labels and hints:** field labels sit above as eyebrows (upper case), hints below in `caption`, both starting at the field's left edge.
- **Toggles:** a 46 × 26 track. Off is `surface-2` with a `text-faint` knob; on is `primary` with a `primary-ink` knob. The label sits to the left, with an optional one-line caption.
- **Segmented choices** (sprint length, shield level, daily goal, export format, theme): chips in a row, radius 10, `surface-2`; the selected chip gets `primary-soft` fill and a `primary` outline. Every pick-one choice in the app uses them; there are no stock radio buttons.
- **Option cards** (`OptionCard`, first-run's shield levels): the segmented look as a full-width row, for a choice that needs a title and a line or two of explanation.
- **Quiet buttons** pad 12 either side; one that starts a line takes a -12 margin, so its label lines up with the text above it.

#### Timer ring (Today)

- **Ring:** 12 px stroke on a `track` circle, with the progress arc in `primary` and a round cap. Diameter: 222px, matching the app-today sketches' proportions at the app's default 1280-wide layout; scales down gracefully to the 800×540 minimum via the existing `today-small` layout path.
- **Centre:** the `timer` number, a `caption` state line ("Shield II engaged"), and the shield glyph.
- **Progress:** the ring shows the time left, so it starts full and drains as the sprint or break runs. The arc glides linearly between the once-a-second ticks; the digits in the centre never ease. When reduced motion is on, the arc steps once a second instead, and no pulse or glow is ever added.

#### Sprint summary card (checklist F12)

- A `surface` card with **three stats in a row**: minutes, distractions caught, momentum change.
- Below it the intention ("You planned: …"), then the one-line journal input.
- A completed sprint shows a small `ok` check; an early end shows a neutral `text-muted` dot, never red.

#### Lock screen (trial ended)

- **Backdrop:** the `scrim` token over the page content, with the navigation rail left visible.
- **Card:** centred, max width 520, `lift` shadow.
- **Content:** a `display` headline, one paragraph, one Primary button (Buy), a divider, then the licence key field with a Secondary Activate button.

#### Intervention moments (Soft overlay, Firm warning, blocked page)

These are where Basalt steps between the user and a distraction (checklist
F7, and F10's blocked page). They share one pattern:

- A compact `surface` panel with the shield glyph, one sentence ("Discord is on your blocklist until 5:45 PM"), and the time left.
- The Soft notice (1.0.10) picks its sentence from four calm wordings by try number, then shows the sprint's intention when one was set ("You planned: finish chapter 3") and a `caption` try count ("3rd try this sprint"). Three actions: **Close ‹app›** first and Primary (the user's choice: it asks the app to close and never kills it); **Back to work** second, a Ghost button that has focus and is the default and the keyboard action (Enter and Esc), so a keystroke meant for the blocked app can never close it; **Allow 5 minutes** last, Quiet and on its own line, disabled until a wait that grows with each try runs out, with the countdown in its label as text ("Allow 5 minutes · 0:08"). A caption under the buttons carries the promise: "Nothing is closed unless you choose to."
- Firm shows a short countdown before closing.
- **No red, no alarm icons, no shaking animations.** It should feel like a polite colleague tapping your shoulder.

#### Toasts and native notifications

- **In-app toast:** `surface` with `border-strong`, radius 12, bottom-centre, 4 seconds, one line.
- **Native Windows notifications:** title in sentence case, one line of body, the app icon, and at most two actions.

#### Tier badge

A pill at the bottom of the navigation rail: `surface-2` with an `eyebrow`
label and a small status dot.

- **Trial:** `primary` dot.
- **Purchased:** `ok` dot.
- **Trial ended:** `warn` dot.

#### Charts (momentum trend, weekly view, heatmap)

- **Line charts:** a single series in `primary`, 2 px, with no area fill. Gridlines are `border` and horizontal only. Axis labels use `caption` in `text-faint`.
- **Heatmap:** five steps from `surface-2` to `primary`, with a visible legend. Never rely on colour alone; hovering or focusing a cell shows the value.
- **Current chart choices:** no 3D or pie charts; no more than two series. These are implementation choices, not limits on future charts. Part A keeps legends and signals beyond colour binding.

---

### 8. Motion

- **Durations:** 120 ms for hovers and presses, 200 ms for panels and selection changes, 300 ms for page transitions. Ease-out for entering, ease-in for leaving.
- **Movement in this design:** fades and short slides of 8 px or less. The numeric limit is descriptive; Part A keeps bouncing, spinning and shaking out.
- **Milestones** (checklist F14) may fade in and settle. Part A keeps celebratory effects out.
- **Reduced motion implementation:** `prefers-reduced-motion` on the site; in the app, Windows' "Animation effects" (`SystemParameters.ClientAreaAnimation`). With reduced motion on, transitions become instant and the site's hero video (checklist F27) shows its poster frame instead. Honouring the setting remains binding in Part A.

---

### 9. Voice and copy

The binding voice rules and word list are in Part A. These examples show the
current tone:

- **Plain and direct:**
  - "Discord closed — it's on your blocklist."
  - Not "Oops! Looks like you got distracted 😅".
- **Neutral about failure:**
  - "Ended early. Momentum −6 — it recovers with your next sprint."
  - Not "You broke your streak!".
- **Specific:** "Sealed until 5:45 PM", not "Locked for now".
- **No exclamation marks and no emoji** in product copy.

The UI currently spells "License key" in Settings; the app and email mostly
use "licence". The copy pass in §15 remains open.

---

### 10. Imagery and marketing assets

- **Real product only:** screenshots and screen recordings of the shipped app, with sample data and never a real blocklist or licence. No stock photos, AI-generated people, or mock-ups of unshipped screens.
- **Framing:** screenshots sit in a `surface` frame with a 14 radius and a `soft` shadow, never a fake laptop or phone frame.
- **Video:** muted, looping, under about 2 MB on desktop and 1 MB on mobile, with a poster frame, `playsinline`, and a text description for screen readers.
- **Illustration:** where a diagram helps, such as the "student day" timeline, use flat shapes in the token colours and the shield glyphs, not characters.
- **Social and store images:** the same screenshots and type, on `bg`.

---

### 11. Website specifics

- **Adoption:** the site was the source of the palette. Contrast fixes, legacy `--violet`/`--cyan`/`--grad` removal, the icon set and shield glyphs, `.btn-quiet`/`.btn-danger`, Inter and tabular price figures are recorded in §15.
- **Theme toggle:** light/dark toggle, defaulting to the visitor's system setting.
- **Performance:** the hero renders text and the primary button before any image or video loads. Fonts use `swap`.

### 12. Desktop app specifics

- **Theme:**
  - Settings → Appearance offers System, Dark and Light; **System is the default**, and follows Windows' own app theme (`AppsUseLightTheme` under HKCU, read-only), changing with it without a restart. Done in F21 (#237).
  - **Engineering fact — Tokens merge:** the light theme is the same tokens in a second `ResourceDictionary`, rather than per-view overrides. `App.xaml` merges `Styles/Tokens.xaml` as its own entry and `ThemeService` swaps that entry for `Styles/Tokens.Light.xaml`. Nothing else may merge a Tokens file: a later merge shadows the swapped one. Every colour reference in XAML is a `DynamicResource` so it re-resolves; Part A keeps this binding.
  - **Engineering fact — Freezables and drawing:** two things cannot follow a swapped dictionary and are handled in code instead: a `DynamicResource` inside a Freezable (the shield glyphs' `DrawingImage` brushes), which is why `ShieldGlyphs.xaml` is reloaded on a change; and anything drawn rather than bound (the tray countdown icon, the DWM title bar), which re-reads its tokens on `ThemeService.Changed`.
- **Window:**
  - The current app uses the standard Windows title bar.
  - Part A allows a custom or extended title bar when it preserves Windows behaviour and accessibility.
- **Tray icon:**
  - The app's Causeway tile (`FlowShield.ico`, built from `design/brand/basalt-icon.svg`).
  - During a sprint it counts down the minutes left, drawn in `primary` on `primary-ink` so it follows the app theme; the running tile (`FlowShield.Running.ico`, the Firm variant) is its fallback.

---

### 13. Accessibility checklist

This records adoption, not exceptions to Part A. An unticked item still needs
verification; it does not make the accessibility requirement optional.

- [x] All token pairs meet WCAG AA, with the fixes in section 2 applied. Done in F21 (#237): a tier 1 test computes WCAG contrast for every pair in section 2's table, in **both** themes, from `design/tokens.json`, and fails below 4.5:1. Measured: dark 16.56 / 8.41 / 5.35 / 6.46 / 5.87 / 9.67 / 9.14 / 7.01; light 13.83 / 5.49 / 5.81 / 5.05 / 5.78 / 5.32 / 5.14 / 5.28.
- [x] Every interactive element is reachable and usable from the keyboard, with a visible 2 px focus ring. Done in F21 (#237): the shared `FocusVisual` style in `Theme.xaml` draws a 2 px `focus-ring` outline, set by every operable style (`BtnBase`, `Field`, `Switch`, `Segment`, `SegmentShield`, `PlainItem`/`HeatCellItem`, `PickerItem`) and by the implicit `RadioButton`/`CheckBox` styles. Escape closes the dialogs and panels that have a cancel action; each overlay is a `Cycle` tab scope and takes focus when it opens.
- [x] Every control has an accessible name; existing `AutomationId`s are kept. Done in F21 (#237), with a tier 5 test over the XAML.
- [ ] Colour is never the only signal: shield levels use bars and labels, and status uses icons and text.
- [ ] Text scales with Windows text-size settings and browser zoom to 200% without clipping.
- [ ] Reduced motion is honoured in the app and on the site.
- [ ] Video has a poster, no sound, and a text description.

---

### 14. Tokens pipeline

The colour pipeline shipped in #41. Type, spacing and radii remain separate
values in `DesktopApp/Styles/Theme.xaml` and `Website/styles.css` (§4); adding
them to the JSON was the original plan, not a prerequisite for a design PR.

1. `design/tokens.json` holds the colour tokens for both themes.
2. `tools/build_tokens.py` generates `DesktopApp/Styles/Tokens.xaml` (dark), `DesktopApp/Styles/Tokens.Light.xaml` and the colour blocks between the `tokens:` markers in `Website/styles.css`. `App.xaml` merges the Tokens dictionary; see the engineering facts in §12.
3. A tier 5 test runs the generator's `--check` mode and fails if committed files are stale. This catches drift and gives the doc steward concrete evidence.
4. `DESIGN_SYSTEM.md` is in the doc steward's editable list in `tools/doc_steward/config.json`, so these notes can stay in step with the implementation.

### 15. Adoption checklist

The original adoption split in `LAUNCH_FEATURE_CHECKLIST.md` → "Who builds
what" gave the token generator to Keenan first and the rest to Miles, as
separate small visual pull requests. This checklist records that work. Future
design PRs follow Part A, including keeping `AutomationId`s and supplying
before/after screenshots in both themes.

- [x] Tokens: `design/tokens.json`, the generator and the parity test (section 14). Done in #41: colours only so far; type, spacing and radii can be added to the JSON as their tasks land.
- [x] Contrast fixes applied in the app and on the site (section 2). Done in #180 (A3, app tokens) and #178 (B3, site inherits the regenerated CSS block): `Tokens.xaml`/`Tokens.Light.xaml` carry `InkFaintColor` `#948F86`/`#625E57` (the proposed passing values), and B4 (#184) confirmed the site's own block was already current off the same generator run.
- [x] Legacy colour aliases removed from `Theme.xaml` and `styles.css`. Done in #130.
- [x] No hard-coded colours left in app views. Verified: `grep -rE "#[0-9A-Fa-f]{6}" DesktopApp --include=*.xaml` matches only `Styles/Tokens.xaml` and `Styles/Tokens.Light.xaml` (the generated token files); every view and `Theme.xaml` itself is clean. Done in #180 (A3).
- [x] Inter embedded in the app and served on the site, replacing Syne, Source Sans 3 and Segoe UI, with tabular figures for numbers (section 3). Done in #171 (A1: `DesktopApp/Assets/Fonts/Inter-{Regular,Medium,SemiBold}.ttf` + `InterDisplay-SemiBold.ttf`, `OFL.txt`, `Typography.NumeralAlignment="Tabular"` on Today/Sleep Blocking numbers) and #172 (B1: `Website/fonts/InterVariable.woff2` + `OFL.txt`, no `fonts.googleapis.com` links remain, `font-variant-numeric: tabular-nums` used 5× in `styles.css`).
- [x] Spacing and radii normalised to the scales (section 4). Done in #182 (A2): `RadiusChip`/`RadiusControl`/`RadiusCard` resources referenced 15× in `Theme.xaml`; `--radius-chip: 6px` added and used in `styles.css` (#178, B3). #191 (merged) extended the same scale to the new adaptive layout.
- [x] Icon set adopted, and the Unicode glyphs in navigation replaced (section 5). Done in #151: Lucide outlines in `Styles/Icons.xaml`, navigation and the two list views. Shield glyphs followed separately (section 6).
- [x] Shield glyphs built and used on Today, the site, notifications and the tray (section 6). Done in #176 (A4: `DesktopApp/Styles/ShieldGlyphs.xaml`, shared by the shield chips and the beside-timer glyph) and #178 (B3: inline SVG `<symbol>` set in `Website/index.html` reusing the same crest geometry, used by the shields section).
- [x] Destructive and quiet button variants added (section 7). Done in #180 (A3: `BtnQuiet`/`BtnDanger` styles in `Theme.xaml`) and #178 (B3: `.btn-quiet`/`.btn-danger` classes in `styles.css`).
- [ ] Copy pass against the word list and tone rules, including one consistent spelling of licence/license (section 9). Partial: B4/B6 (#184, #188) fixed tone on the site, but the two spellings are still mixed rather than one chosen consistently — `DesktopApp/Views/SettingsView.xaml` shows the user-facing label `Text="LICENSE KEY"` and `AutomationProperties.Name="License key"` (American), while other app and email copy uses "licence" (British); the site mixes both across `index.html`/`legal.html`/`success.html`/`checkout.js`. Left unticked.
- [x] Reduced-motion support in the app and on the site (section 8). Done in #176 (A4: `DesktopApp/Infrastructure/Motion.cs` reads `SystemParameters.ClientAreaAnimation` and zeroes every duration when it's off) and pre-existing site support (`prefers-reduced-motion` in `Website/index.html`/`styles.css`).
- [x] Light theme in the app (section 12, checklist F21). Done in #237: `App.xaml` merges `Styles/Tokens.xaml` as its own entry and `DesktopApp/Services/ThemeService.cs` swaps it for the generated `Tokens.Light.xaml`; Settings → Appearance offers System (the default, following Windows) / Dark / Light, and every colour reference in the app's XAML is a `DynamicResource`.
