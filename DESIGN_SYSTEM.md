# Basalt design system

One visual language for the desktop app and the website, so that a customer
moving from the site to the installer to the app sees the same product. It
builds on what already exists: the stone and teal palette from the site
redesign (#27), which the app adopted in #32.

**Part A is binding.** Every app and site change follows it. **Part B describes
the current implementation.** It is a starting point, not a ceiling (#366).

**A redesign is in progress (2026-11).** Part A below already describes it:
depth from Windows 11's own materials, Segoe UI Variable in the app, real
controls, and the notice's input guard. Part B describes what has shipped;
each implementation PR updates its own Part B section. The foundations (depth
tokens, Segoe UI Variable, Segoe Fluent Icons, the control styles and Mica)
shipped in #430, and Today with its setup panel in #431; the other screens are re-laid out in the PRs after it. The target screens and
the depth values are in [`design/redesign-2026-11/`](design/redesign-2026-11/README.md).

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
large, and nothing flashes for attention. Like a well-made instrument, it has
real depth: surfaces that sit at different heights under one light, so you can
see what you can touch and what matters now. Depth is never decoration.

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
- Controls appear where and when they are needed (progressive disclosure). A main screen shows a summary; the full set of settings is one click away (on Today, the setup panel).
- Anything that acts looks like a control of its kind, so people can see what is clickable and what will happen. Buttons for actions, with one Primary per view. A disclosure with a chevron for showing more in place. Selectors, segmented controls or dropdowns for choices, and toggles for on and off. Plain links only for going to another place or to help.
- Every section of a page reads as part of it, with a heading and real rows or controls. Nothing a customer needs is set as fine print under a divider.
- Every empty state points to the next action.
- Numbers show units and context: charts have legends; calendars have weekday labels.

### Hard rules

- **Tokens:** colours come only from `design/tokens.json` through `tools/build_tokens.py`; no hex literals in views; every colour reference in XAML is a `DynamicResource`, because the light/dark swap depends on it.
- **Contrast:** every token pair used for text passes measured WCAG AA (4.5:1); measure any new pair before shipping, so readable text is proved rather than guessed (§2 keeps the reference table).
- **Meaningful colour:** `ok`/`warn`/`danger` mean status, never decoration; teal means state, selection or progress, so colour carries a consistent meaning.
- **Accessibility:** controls are keyboard reachable, have a visible 2 px focus ring and accessible names; colour is never the only signal, text survives 200% scaling, and reduced motion is honoured everywhere (app: `SystemParameters.ClientAreaAnimation`; site: `prefers-reduced-motion`), so everyone can use the product.
- **Calm:** nothing bounces, spins, shakes or pulses; no confetti, fireworks, sounds or alarm visuals; state failure neutrally, because the product helps without celebrating or blaming.
- **Depth:** one depth system, built from Windows 11's own materials, so the app looks like flagship Windows software without decoration:
  - **Base:** Mica is the window's base, title bar included. It is opaque, so text on it is unaffected.
  - **Surfaces** sit above the base at two elevations: resting (sidebar, side cards, lists) and raised (the thing you act on now, such as Today's Now card). Higher is a step lighter, has a fine highlight on its top edge, and casts a larger shadow. There is one light, from above: highlights on top edges only, and shadows fall straight down and are never coloured. Buttons are raised; text fields and selector tracks are recessed.
  - **Acrylic** is only for temporary surfaces: the setup panel, dropdowns, flyouts and menus, with a tint heavy enough that every text pair passes AA over the brightest thing behind it, and never behind a paragraph. The notice band is tinted to about 90%, because a game is behind it.
  - **Gradients and glow appear only on live things:** the timer ring's progress arc, the Primary button, a toggle that is on, and a soft teal glow that is present only while a sprint runs ("Basalt is holding") and gone when it ends. It never pulses. No decorative gradients, glows, blobs or coloured shadows anywhere.
  - **Fallback:** with transparency effects off, on Windows 10, in battery saver or when the window is inactive, Mica and acrylic become solid token surfaces and nothing else changes. High contrast uses system colours only, with solid borders and no gradients, shadows, glow or translucency.
  - **Site:** the same language in CSS: an opaque base, surfaces at the same two elevations, the same buttons, and translucency only on the navigation bar.
- **Interruptions:** the full-screen notice can't be dismissed by accident. No button is the default and none has focus when it appears, so Enter and stray typing do nothing. Every button ignores input for about 1.5 seconds, with the wait shown, then a click or a deliberate Tab then Space works. This keeps someone who is typing from dismissing it, and keeps it usable from the keyboard.
- **Texture:** restrained material texture is allowed in the app and on the site, never under text, cards or controls, with contrast unaffected and off with reduced transparency where applicable; no photographs of rock or marble veining behind copy, so material never competes with content.
- **Title bar:** a custom or extended title bar keeps Snap Layouts, the system menu, keyboard access, accessible names and correct drag regions, so changing the frame preserves Windows behaviour.
- **Imagery:** real product only, with sample data and never a real blocklist or license; no stock photos, AI-generated people, fake device frames or mock-ups of unshipped screens, so marketing stays honest and private data stays private.
- **Voice:** plain, specific words; no exclamation marks or emoji in product copy; use the binding word list below, so the product is clear and kind.
- **Brand:** copy the Causeway mark from `design/brand/`, never redraw it, so the same mark reaches every surface. One exception: a lit, dimensional rendering of the same geometry may appear at the big moments (first run, the end of a sprint, the end of the trial). It is made once, kept in `design/brand/`, and copied like the flat mark. Everywhere else the flat mark is used.
- **Type and icons:**
  - **App:** Segoe UI Variable, the Windows 11 system face, so the window's own title bar, menus and dialogs and the app's content are one typeface. Display for the countdown and titles, Text for everything else, falling back to Segoe UI on Windows 10. Icons are Segoe Fluent Icons (Segoe MDL2 Assets on Windows 10), plus Basalt's own shield glyphs. Both are part of Windows, so nothing is bundled.
  - **Site:** Segoe UI Variable first, so a visitor on Windows sees the app's face, then Inter (self-hosted, OFL) everywhere else. Site icons stay Lucide (ISC).
  - Fonts and icons stay licensed and embedded, self-hosted or supplied by the system, with notices shipped and no runtime web-font services, so they work offline and their terms are met.
- **Automation:** keep existing `AutomationId`s and put ids on controls, not layout panels, because UI Automation does not surface panel ids (#134).
- **Blocker:** follow `CLAUDE.md`'s deliberately timid blocker rule: protect critical processes; no admin rights, drivers, services or hosts-file edits, so focus never puts the machine at risk.
- **Apple platforms:** the Mac app (and later the iPhone app) follows Apple's Human Interface Guidelines first, so it feels like a Mac app rather than a Windows port (Miles, #425). Apple's guidance decides structure, navigation, controls, type and materials: the system font (SF Pro) through text styles instead of Inter, semantic system colours for backgrounds and text, SF Symbols for interface icons, and Liquid Glass where the system applies it (toolbars, sidebars, sheets, menus, popovers, the menu bar extra), never on content. These replace the type, icon and depth rules above on Apple platforms only. Basalt's own rules still apply there: colour meaning and the token pipeline (teal is the accent; amber and rose are status), calm, the shield language, the word list, accessibility and the blocker rule. Accessibility identifiers take the place of `AutomationId`s.

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

**Depth tokens (#430).** The redesign's depth system
([`design/redesign-2026-11/README.md`](design/redesign-2026-11/README.md))
entered `design/tokens.json` in #430. They are app-only for now: the site
adopts them in its own PR (they are in `css_skip`), and the Mac app, which
uses Apple's materials, doesn't get them (`apple_skip`). `white` is a base
for the translucent highlights and is not emitted on its own.

| Token (WPF key) | Dark | Light | Use |
| --- | --- | --- | --- |
| `mica` (`Mica`) | `#18191B` | `#EDEDEB` | E0, the window base, as drawn in the mockups (Windows supplies the real material) |
| `mica-fallback` (`MicaFallback`) | `#1B1C1E` | `#EFEFED` | E0 when Mica is off (§4 "Mica and its fallback") |
| `elev-1` (`Elev1`) | `#1F2123` | `#F6F6F4` | E1, resting surfaces: cards, the rail, lists |
| `elev-2` (`Elev2`) | `#27292C` | `#FDFDFC` | E2, raised: the thing you act on now, the selected rail item |
| `elev-3` (`Elev3`) | `#2C2E32` | `#FBFAF8` | E3, flyouts, dropdowns, calendars; solid E3 is acrylic's fallback |
| `acrylic` (`Acrylic`) | `elev-3` at 74% | `elev-3` at 78% | The acrylic tint, for when acrylic is built |
| `highlight-1/2/3` | white at 5.5 / 8.5 / 12% | white at 85 / 100 / 100% | The 1 px top highlight of E1 / E2 / E3 |
| `hairline` (`Hairline`) | black at 34% | `text` at 10% | The 1 px outline of every surface |
| `divider` (`Divider`) | white at 7% | `text` at 9% | Rules between rows |
| `control` / `control-hover` / `control-pressed` | white at 7 / 11 / 4% | white at 72 / 95%, `text` at 4% | Raised control fill and its states |
| `control-highlight` / `control-edge` / `control-shadow` | white 20%, white 12%, black 30% | white, `text` 17%, `text` 24% | A raised control's lit top edge, outline and 1 px shadow |
| `well` / `well-edge` / `well-line` | black 26%, white 10%, white 56% | white 78%, `text` 12%, `text` 56% | Recessed fields: fill, outline, the Windows bottom line |
| `segment-track` (`SegmentTrack`) | black at 26% | `text` at 6% | A segmented selector's recessed track, and an unpicked loose segment |
| `thumb` (`Thumb`) | `#3A3D41` | `#FFFFFF` | The picked segment (raised) |
| `primary-grad-top` / `-bottom` | `#4FBBA4` → `#37A08B` | `#0F7A69` → `#0A5F52` | The Primary button's gradient, and a switch that is on |
| `primary-highlight` / `primary-edge` / `primary-shadow` | white 34%, black 10%, black 34% | white 22%, black 12%, `text` 26% | The Primary button's lit edge, outline and shadow line |
| `ring-grad-start` / `-end` | `#5CC7B0` → `#2F947F` | `#14917C` → `#0A5A4E` | The ring's progress arc (`RingGradient`, Today since #431) |
| `glow` (`Glow`) | `primary` at 20% | `primary` at 13% | The teal glow while a sprint runs (`GlowGradient`, Today since #431) |

The generator also writes multi-colour resources from `app_brushes` into both
Tokens dictionaries, so they swap with the theme: `Elev1Surface`,
`Elev2Surface` and `Elev3Surface` (each elevation with its highlight
composited onto its top rows, since WPF has no inset shadow),
`PrimaryGradient`, `RingGradient`, `GlowGradient`, and the shadows `ShadowE1`,
`ShadowE2`, `ShadowE3` and `ShadowPrimary`: black, falling straight down
(`Direction="270"`), with per-theme opacity.

#### Colour use in the current design

- **Legacy names removed.** `Violet`, `VioletBright`, `Cyan`, `Glass*`, `Accent` and `WindowBg` are gone from `Theme.xaml`, and `--violet`, `--violet-bright`, `--cyan`, `--grad` and `--glass*` are gone from `styles.css`. Colour references use the token names above. (The site keeps a short alias block — `--bg`, `--ink`, `--edge` and friends — for the legal and success pages; those are token names under a shorter spelling, not dead colours.)
- **Token references.** Every colour in XAML and CSS comes from a token. The lock screen's former literal hex backdrop was removed in #180 (A3).
- **Teal is structural, not decorative.** Teal may appear in as many places as a screen needs, provided it always means one of three things:
  - **state**: something is on, active or running (an engaged shield, an enabled toggle, the tier badge's trial dot);
  - **selection**: the current navigation item, the chosen chip, the focused control;
  - **progress**: the timer ring, progress bars, chart series.

  The primary action is teal because it is the thing that changes state. Nothing is teal just to look branded: no teal headings, dividers, borders, illustrations or background washes. If everything is teal, nothing is. What earns the colour is that it always means the same thing, not that it is rare. (Replaces the earlier "teal is scarce" rule, #147.)
- **Status colours are for status only.** Amber and rose never decorate. `ok` green is for "done", not for "go".
- **Depth:** since #430 the app has the redesign's depth system: Mica (or its solid fallback) as the base, E1 cards and rail, E2 for the selected rail item, E3 flyouts, raised controls and recessed fields (§4, §7). Gradients appear in their four places only: the Primary button, a switch that is on, and since #431 the ring's arc and the glow behind it while a sprint runs.

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

The depth tokens' text pairs, measured on 11 November 2026 (#430). A
translucent layer is composited onto what it sits on first, so "`text` on
`control` on `elev-1`" is a button label on a card.

| Pair | Dark | Light | Result |
| --- | --- | --- | --- |
| `text` on `mica` / `mica-fallback` | 15.0 / 14.6 | 14.4 / 14.7 | Pass |
| `text-muted` on `mica` / `mica-fallback` | 8.1 / 7.9 | 6.3 / 6.4 | Pass |
| `text-faint` on `mica` / `mica-fallback` | 5.7 / 5.5 | 5.2 / 5.3 | Pass |
| `text` on `elev-1` / `elev-2` / `elev-3` | 13.8 / 12.4 / 11.6 | 15.6 / 16.6 / 16.2 | Pass |
| `text-muted` on `elev-1` / `elev-2` / `elev-3` | 7.4 / 6.7 / 6.3 | 6.8 / 7.2 / 7.1 | Pass |
| `text-faint` on `elev-1` / `elev-2` | 5.2 / 4.7 | 5.7 / 6.0 | Pass |
| `text-faint` on `elev-3` | 4.41 | 5.9 | **Fails in dark: not for text.** Nothing on an E3 flyout uses `text-faint`; a tier 5 test keeps it that way |
| `primary` on `mica` / `elev-1` / `elev-2` | 6.0 / 5.5 / 5.0 | 5.5 / 5.9 / 6.3 | Pass |
| `primary-ink` on `primary-grad-top` / `-bottom` | 7.3 / 5.4 | 4.85 / 7.0 | Pass |
| `text` on `control` on `elev-1` / `elev-2` | 11.2 / 10.0 | 16.4 / 16.7 | Pass |
| `text` on `control-hover` on `elev-2` | 8.7 | 16.9 | Pass |
| `danger` on `control` on `elev-1` | 4.86 | 6.5 | Pass |
| `text` on `well` on `elev-2` | 14.2 | 16.9 | Pass |
| `text-faint` (placeholder) on `well` on `elev-2` / `elev-1` | 5.4 / 5.8 | 6.1 / 6.0 | Pass |
| `text-muted` on `segment-track` on `elev-2` | 7.7 | 6.5 | Pass |
| `text` on `thumb` | 9.3 | 16.9 | Pass |

A tier 5 test (`TestDepthTokens430`) computes every passing row above from
`design/tokens.json`. Any new token or pairing gets measured the same way
before it ships.

The setup panel's acrylic (#431), measured on 12 November 2026: the page's
snapshot is drawn at 35% over solid `elev-3`, then the `acrylic` tint over
that, so whatever is behind the panel contributes about a tenth. The worst
case is the brightest (dark) or darkest (light) thing that could sit behind it:

| Pair, over acrylic with … behind | Dark | Light | Result |
| --- | --- | --- | --- |
| `text` / `text-muted`, the Primary button behind | 9.9 / 5.3 | 14.4 / 6.3 | Pass |
| `text` / `text-muted`, pure white (dark) or black (light) behind | 8.7 / 4.7 | 13.7 / 6.0 | Pass |
| `warn` (the custom length's error), the same | 5.2 | 5.5 | Pass |

`TestAcrylicContrast431` (tier 5) computes these from `design/tokens.json` too.

---

### 3. Typography

#### The faces

The site formerly used **Syne** and **Source Sans 3**, then both app and site
used **[Inter](https://rsms.me/inter/)** (#147; #171, #172). The redesign
(#430) moved the app to **Segoe UI Variable**, the Windows 11 system face, so
the window's own title bar and the app's content are one typeface. The site
keeps Inter until its own redesign PR (Part A: Segoe UI Variable first, then
Inter).

| Role | App (#430) | Site | Where |
| --- | --- | --- | --- |
| Display | **Segoe UI Variable Display** 600 (`FontStackDisplay`) | Inter 600–700 | The countdown, the big numbers (`Timer`, `Stat`) and page titles (`H1`) |
| Text and UI | **Segoe UI Variable Text** 400/600 (`FontStack`) | Inter 400/500/600 | Everything else, including card titles (`H2`) |
| Numbers | Tabular figures (`Typography.NumeralAlignment="Tabular"`) | `font-variant-numeric: tabular-nums` | The timer, stats, prices, momentum, so digits don't jiggle |
| Licence keys | Cascadia Mono, then Consolas | the same | Keys and anything the user must copy exactly |

- **Fallback:** each app stack falls back to **Segoe UI**, which is what Windows 10 has.
- **Engineering fact, measured on Windows 11 build 26300:** WPF resolves `Segoe UI Variable Text` and `Segoe UI Variable Display` to `SEGUIVAR.TTF`, but the bare `Segoe UI Variable` to `SEGOEUI.TTF`, plain Segoe UI. So every stack names its optical cut. The theme probe checks the resolved file (tier 5), and a tier 5 test rejects the bare family name in the app's XAML.
- **Nothing is bundled** in the app since #430: the Inter files and their OFL notice were removed from `DesktopApp`. The site still self-hosts Inter with its notice.
- **Tracking:** WPF has no letter-spacing property on `TextBlock`. The Display cut is drawn for large sizes, which does what negative tracking did for Inter.

#### Scale

A shared scale. Sizes are in px for the app; the site uses the matching `rem`
values in `styles.css` (`--text-*`).

In the app, `display`, `timer` and `stat` are Segoe UI Variable Display and
the rest are Segoe UI Variable Text (#430); on the site every role is Inter.
Buttons and fields moved to 14 px with #430 (the mockups' size), with Primary
at weight 600 and the other buttons at 400.

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
- **Corner radius:** in the app, 6 for small chips and tags, 8 for buttons, inputs and toggles, 12 for cards, dialogs and flyouts, and fully round for pills and the tier badge (the redesign's "surfaces 12, controls 8", #430; A2's set in #147 was 6 / 10 / 14, which the site still uses until its redesign PR).
- **Where these values live:** corner radii are three resources — `RadiusChip`/`RadiusControl`/`RadiusCard` — in `DesktopApp/Styles/Theme.xaml`, and values in `Website/styles.css`. The eight spacing numbers are literals per element. Neither is in `design/tokens.json`, which is colour only (§14); a future issue may unify them the way colour is unified.
- **Engineering fact — round shapes:** fully round elements set `inf:Pill.IsRound="True"`, because WPF draws an oversized radius such as 9999 as an ellipse rather than clamping it like CSS.
- **Stone (currently on the site, #336).** The product is named after basalt, so the site shows the material in two restrained ways:
  - **Grain** on the page ground (`body`, and the `bg-soft` bands) through `--texture-grain`: an inline SVG noise, under 1 KB, dark specks in light mode and pale ones in dark, each at most about 8% opaque. It never goes on a surface: cards, buttons and text boxes stay solid, so every contrast figure in §2 still holds.
  - **Basalt columns**: one faint row of columns seen side-on, standing on the hero's bottom edge inside its padding (`.hero::after`). It is drawn in `text` at 13% through a mask, so it follows the theme, and it is never placed behind text or a control.
  - Depth comes from surface steps and shadows. Part A allows restrained material texture in the app too, with the same protections for content and contrast.
- **Depth in the app (#430):** the redesign's depth table, built from the tokens in §2:
  - **E0, the base:** the main window is Mica, or the solid `mica-fallback` (see "Mica and its fallback" below).
  - **E1 (`Card`, the rail):** `Elev1Surface`, a 1 px `hairline`, `ShadowE1` (blur 6, 2 down).
  - **E2 (`CardRaised`, the selected rail item):** `Elev2Surface`, `hairline`, `ShadowE2` (blur 28, 10 down). Today's Now card uses it (#431).
  - **E3 (`Flyout`, the dropdown, the date picker's calendar and the setup panel):** `Elev3Surface`, `hairline`, `ShadowE3` (blur 56, 24 down). Solid E3 is acrylic's fallback.
  - **Acrylic (the setup panel, #431):** WPF has no backdrop blur, so `Views/SetupPanel.xaml.cs` takes one snapshot of the page under the panel (a `VisualBrush` of the title and page into a `RenderTargetBitmap`, reaching 1.5 blur radii past the panel), blurs it once with a 28 px `BlurEffect` into a second, frozen bitmap, and shows that under the `acrylic` tint (`elev-3` at 74%, light 78%), over the solid E3 base. Nothing blurs live: the snapshot is re-taken, debounced, when the panel opens, on a resize, a theme change, or when what Today shows beneath it changes. It is drawn only while the window's backdrop is Mica (`WindowBackdrop.Changed`), so with transparency effects off, on battery saver, on Windows 10, in software rendering or while the window is inactive the panel is solid E3, which is also what every text pair on it is measured against. **Not yet seen on a real Windows 11 PC:** on the test VM the policy reports Mica, so the acrylic is drawn there (over a window Windows paints solid).
  - **Engineering fact — highlights:** WPF has no inset box-shadow, so each surface's 1 px top highlight is the first rows of its background brush (an absolute-mapped gradient the generator composites), drawn just inside the hairline. Each shadow is one `DropShadowEffect`, where the CSS uses two layers.
- **Mica and its fallback (#430):** `Services/WindowBackdrop.cs` asks DWM for Mica (`DWMWA_SYSTEMBACKDROP_TYPE` = `DWMSBT_MAINWINDOW` from build 22621, `DWMWA_MICA_EFFECT` on 21H2), extends the frame into the client area and clears WPF's composition background. `Models/BackdropPolicy.cs` then decides what the window's base shows: Mica (a clear background) only with transparency effects on, Windows 11, battery saver off, WPF rendering on the GPU, DWM's acceptance and the window active; otherwise the solid `MicaFallback`; and the system window colour in high contrast. It is re-decided on activation, `WM_SETTINGCHANGE`, `WM_POWERBROADCAST`, `WM_DWMCOMPOSITIONCHANGED` and rendering-tier changes. The standard title bar stays, so Snap Layouts and the system menu are Windows' own. High contrast so far changes only the base; the rest of the app's high-contrast pass (system colours on every control) is still to do. **Not yet seen on real hardware:** the test VM has no 3D, so Windows draws its own solid fallback there even though DWM accepts the request.
- **Borders:** 1 px `hairline` on surfaces since #430; controls use `control-edge` (raised) or `well-edge` (recessed). `border` and `border-strong` remain for chips, rows and hover.
- **Shadows on the site**, currently two levels:
  - `soft` for cards on the site and for toasts;
  - `lift` for dialogs and the lock screen card.
  - The dark design favours a surface step over a shadow. (The app's shadows are the E1–E3 ones above.)
- **Layout:**
  - **App:** a 240 px navigation rail and a content area aligned with its page title. The content grows with the window up to 1280 px (`PageMaxWidth` in `Theme.xaml`); past that, the title and page stay together in a 1280 px column centred beside the rail, so an ultrawide screen doesn't spread a page's cards apart (#406). The mouse wheel over the margins either side still scrolls the page.
  - **The app adapts to its window.** Each breakpoint reads the width the element actually has, not the window's, so a view responds to its own space:
    - **Rail:** below a 1000 px window client width it compacts to 72 px of icons, with the names as tooltips (`MainWindow.CompactRailBelow`).
    - **Card grids** (`inf:AdaptiveColumns`: History, Schedule) lay cards out in rows, left to right in reading order, as many columns as fit at the panel's minimum width, up to its maximum. Cards in a row share the row's height, so neighbours' edges line up (#406; this was a masonry layout that left them uneven). The column count is balanced over the rows, so five cards that would fit four abreast sit three and two. `FillLastRow` lets a short last row share the full width, for rows of unlike cards. Gaps are in the panel's `Spacing`, rather than the cards' margins.
    - **Settings** is one column of full-width cards, like Windows' own Settings: its groups hold one to three cards each, and no row of them could line up at every width.
    - **Two-pane pages** give the side pane a proportional width with a minimum and maximum: Today's side cards (`0.46*`, 300–400 px, #431) and Blocked Apps' picker (`0.65*`, 260–460 px). Below a view width of 900 px, Today's Up next and Momentum leave the Now card's side and sit in a row under it, and below 600 px one above the other (the small-window mockup); below 780 px Blocked Apps' picker stacks under its list and the page scrolls.
    - **Today on a short page** (view height under 600 px, #431): the cards keep their order and tighten their spacing (10 between cards, smaller padding, a 36 px Set up, field and Start, 52 px template cards, a sparkline without its range and peak), and the window's page title takes less room below a 640 px client height, so the 1092 × 614 small window shows Now, Up next, Momentum and Templates without scrolling.
    - **Fully round shapes** use `inf:Pill.IsRound`; see the engineering fact above.
    - Settings is six labelled groups with a section rail; below 900px the rail becomes a chip row. The rail marks the current group like the main rail does: a `surface-2` fill and a `primary` bar (an underline in the chip row).
    - **Today's timer ring** is drawn at 222 px and scaled as a whole to about a third of the page's height, between 160 and 228 px since #431 (`TimerRingSize`), so it sits in the Now card at the mockups' size and shrinks on a short window.
  - **Engineering fact — fixed-height controls:** vertical padding consumes the space available for content. `BtnBase` fixes the height at 40, and navigation rows are 44 with no vertical padding, leaving room for their 20 px icons. Since #430 the button templates apply only a button's horizontal padding (`HorizontalPaddingConverter`), because a view's `Padding="48,12"` clipped the 14 px label inside the 40 px height.
  - **Site:** a 1120 px maximum width (`--maxw`).
  - **Minimum app size:** 800 × 540 (Roadmap 1.13).

---

### 5. Icons

- **App icons (#430):** Segoe Fluent Icons, with Segoe MDL2 Assets as the Windows 10 fallback (`IconFont` in `Styles/Icons.xaml`). Each icon is one code point (`IconToday` Clock, `IconHistory` AreaChart, `IconBlocked` Blocked, `IconSleep` QuietHours, `IconSettings`, `IconRefresh`, `IconCalendar`, the chevrons, `IconClose`, `IconMore`, and since #431 `IconSetup` Equalizer, `IconPlay` and `IconUp`), shown in a `TextBlock` with the `Icon` (20) or `IconSmall` (16) style, centred in a square box. Every code point used exists in both fonts. Both fonts are part of Windows, so nothing is bundled and no notice ships.
- **History:** Unicode glyphs (`◷`, `⊘`, `☾`, `⚙`) rendered differently across Windows versions; Lucide outlines replaced them in #151 and were the app's icons until #430. A tier 5 test still bans those symbol glyphs in views.
- **Site icons:** [Lucide](https://lucide.dev), at 1.75 px stroke on a 24 px grid, as inline SVG. Its ISC notice ships with the site (`icons-LICENSE.txt`).
- **Sizes:** 16 px inline with text, 20 px in navigation and buttons, 24 px for feature headings.
- **Icons inherit** the text colour of their context; only an active item's icon is `primary`.
- **The lit mark** (#431): `design/brand/basalt-mark-lit.svg`, the one dimensional rendering of the Causeway geometry that Part A allows at the big moments, copied into `BrandMarkLit` in `Styles/BrandMark.xaml`. Today shows it at the end of a sprint. See `design/brand/README.md`.
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
- **Selected state:** since #430 the picked chip is raised (`thumb`, a lit top edge) with the teal marker under it and its label at 600; the others are recessed (§7, segmented choices).
- **During a sprint** the active shield's glyph sits in the sprint's Details (#431) and in the tray icon. Before a sprint, Today's shield level is one `SegmentGroup`, each option with its glyph and name.
- **Shared glyphs:** a XAML `DrawingImage` resource and an SVG symbol on the site, built once per platform.

---

### 7. Components

Each component is defined once. In the app it's a style in `Theme.xaml`; on the
site it's a class in `styles.css`. Names match across the two.

#### Buttons

| Variant | App style | Site class | Look | Use |
| --- | --- | --- | --- | --- |
| Primary | `BtnPrimary` | `.btn-primary` | App (#430): `PrimaryGradient` fill, lit top edge (`primary-highlight`), `primary-edge` outline, a `primary-shadow` line and `ShadowPrimary` below, `primary-ink` label at 600. Site: `primary` fill | One per view: Start sprint, Buy Basalt, Activate |
| Secondary | `BtnGhost` (= `BtnBase`) | `.btn-ghost` | App (#430): raised: `control` fill, `control-highlight` top edge, `control-edge` outline, a 1 px `control-shadow` line under it, `text` label at 400. Site: `surface-2` fill, `border` | Alternatives: Copy key, Rename |
| Quiet | `BtnQuiet` | `.btn-quiet` | No fill, `text-muted` label, `control` fill on hover | Low-emphasis: Deactivate, Open log |
| Destructive | `BtnDanger` | `.btn-danger` | The raised control with a `danger` label and outline | Remove, End sprint anyway |
| Icon | `BtnIcon` | — | The raised control, 36 square, a glyph inside and an `AutomationProperties.Name` | Close on the setup panel (#431) |
| Link | `BtnLink` | — | `primary` label at 13 px with a drawn chevron, no fill, `control` on hover (#431) | Going to another place or to help only: "Edit schedules", "How momentum works" |

- **App (#430):** height 40, radius 8, horizontal padding 20, 14 px. Only the horizontal padding is applied inside the fixed height (§4).
- **Site:** height 44, radius 10, `label` type.
- **States (app):** hover lifts the fill (`control-hover`; on Primary a thin `primary-highlight` wash); pressed drops it (`control-pressed`; on Primary `primary-edge`) and hides the lit edge; disabled is 45% opacity; keyboard focus shows a 2 px `focus-ring` offset by 2 px.
- **Button text is a verb:** "Start sprint", not "OK".

#### Cards

- **Look (app, #430):** `Card` is the E1 surface (`Elev1Surface`, `hairline`, `ShadowE1`), radius 12, padding 24. `CardRaised` is E2 and `Flyout` E3 (§4). `CardTinted` keeps its #347 structure: the shadow on the opaque E1 layer, the `primary-soft` tint inside it. `RowCard` (a row on a card) uses the raised `control` fill and `control-edge`.
- **Look (site):** `surface` fill, 1 px `border`, radius 14, padding 24.
- **Heading:** an optional `eyebrow`, then a `title`.
- **Stat cards:** one `stat` number, one `caption` label, and optionally a delta in `ok` or `text-muted` (never `danger` for a momentum drop; see Voice).

#### Form controls

- **Text inputs (`Field`, #430):** recessed: the `well` fill, a `well-edge` outline and the Windows bottom line (`well-line`), which turns `primary` and 2 px thick on keyboard focus, with the 2 px focus ring as well; radius 8. An empty field shows its `AutomationProperties.HelpText` as a `text-faint` placeholder (5.41:1 dark, 6.11:1 light on the well over E2).
- **Date pickers** (`Styles/Pickers.xaml`) are recessed like a text input, with a calendar glyph; the calendar drops down as an E3 flyout, its selected day drawn like a selected segment.
- **Dropdown (`Dropdown`, `DropdownItem`, #430):** a `ComboBox` drawn as the recessed well with a chevron, opening an E3 flyout; the picked item has the teal marker. The setup panel's blocklist is the first screen to use it (#431).
- **Disclosure (`Disclosure`, #430):** a raised `ToggleButton` whose chevron turns to point up while open, for showing more in place (a running sprint's Details, #431). UI Automation reports it as a toggle.
- **Labels and hints:** field labels sit above, hints below in `caption`, both starting at the field's left edge. Since #431 Today and the setup panel label fields in sentence case (`FieldLabel`, 13 px, `text-muted`: "Shield level", "Your plan (optional)"); the other screens still use upper-case eyebrows until their own PRs. On the setup panel (E3) hints use `text-muted`, never `text-faint`.
- **Toggles (`Switch`, #430):** a 40 × 20 recessed track with a `well-line` outline and a 12 px `text-muted` knob at the left when off; when on, the `PrimaryGradient` track with a 14 px `primary-ink` knob at the right. The label sits to the left, with an optional one-line caption. `SwitchStated` adds the state written beside the track ("On" / "Off"), for Plans' schedules.
- **Segmented choices** (sprint length, shield level, daily goal, export format, theme), since #430: an option you could pick is recessed (the `segment-track` tone with a `well-edge` outline); the picked one is raised (the `thumb` fill, a lit top edge, `control-edge`), set at 600, with the same teal marker as the rail under its label, so selection never rests on tone alone. Radius 8. Today's shield level and the setup panel's length and sprints in a row use the grouped `SegmentGroup` and `SegmentItem` (one recessed track, one raised thumb) since #431; the other screens' choices still sit loose in rows until their own PRs. Every pick-one choice in the app uses them; there are no stock radio buttons.
- **Option cards** (`OptionCard`, first-run's shield levels): the segmented look as a full-width row, for a choice that needs a title and a line or two of explanation, with the teal marker at its left edge.
- **Quiet buttons** pad 12 either side; one that starts a line takes a -12 margin, so its label lines up with the text above it.

#### Today (#431)

Today is a raised **Now** card (E2) beside two resting cards (E1), **Up next** and **Momentum**, with **Templates** below. There is no page subtitle, no upper-case label and no middle dot between facts.

- **Now's status line**, beside "Now", says what is blocked right now (`RingCaption`): "Nothing is blocked.", "Sleep blocking is on." inside the nightly window, "Basalt is holding. 3 apps blocked at Firm." while a sprint runs (with a teal state dot), "Sprint complete. Nothing is blocked." after one.
- **Ready:** the ring with the length and "ends 10:49 PM / if you start now"; a one-line summary ("One 45-minute sprint, Default blocklist, 3 apps") with **Set up**; the shield level (`SegmentGroup`) and its explanation; "Your plan (optional)" and the view's Primary, **Start sprint**. Set up opens the setup panel.
- **Setup panel:** a right-side E3 flyout (acrylic over Mica, §4) with length (15 / 25 / 45 / 60 / 90 / Custom, segmented; Custom shows a number field), sprints in a row (1 to 4) and the blocklist (dropdown), Close and Done. The ring and the summary beneath follow each choice. Esc, Close, Done and a click outside close it, except while a custom length Start would refuse is showing its reason; Tab cycles inside it, and focus returns to Set up.
- **Running:** the ring's arc in `RingGradient` with a soft `GlowGradient` behind it (only while a sprint runs, never during a break, never pulsing); "until 10:19 PM" under the countdown, which the title bar repeats; the plan at full contrast; a **Details** disclosure (shield, blocklist, start time, what has been blocked so far) and the end button. No Primary, and Buy leaves the rail until the sprint ends.
- **End of a sprint:** the lit mark (§5) in the countdown's place; the result ("15 minutes focused") with its line of facts ("Firm, 10:04 PM to 10:19 PM. No blocked app was opened."); "You planned: …. What moved?", the note and the Primary **Save note** (or Not now). After a finished sprint, a **Take a break** card offers Start break and Start next sprint; there is no Skip break, and a running break has End break. Momentum then comes first in the side column, with today's change ("Up 6 today, from 186") and "Day 9 of your streak".
- **Up next:** the next schedule start or the sleep window, whichever comes first ("10:30 PM / Sleep blocking until 6:30 AM"), or "Nothing scheduled", with a link to the Schedule page.
- **Momentum:** the number, today's facts without zero counters ("No sprint yet today", "2 sprints today, 50 minutes focused") and the streak, with the 30-day line.
- **Templates:** one card per template; clicking the card fills it in (a preset, not a lock), and its **Start** starts it through every gate Start has.

#### Timer ring (Today)

- **Ring:** a 12 px `track` circle and the progress arc, a `Path` with an `ArcSegment` stroked in `RingGradient` with round caps (#431; WPF has no conic brush, so the gradient is diagonal). Drawn at 222 px and scaled as a whole between 160 and 228 px (§4).
- **Centre:** the `timer` number in the Display cut, then "ends …" and "if you start now" before a sprint, or "until …" during a sprint or break, and "Sprint 2 of 3" in a cycle. The status line that sat here moved to the top of the Now card in #431.
- **Progress:** the ring shows the time left, so it starts full and drains as the sprint or break runs. The arc glides linearly between the once-a-second ticks; the digits in the centre never ease. When reduced motion is on, the arc steps once a second instead. A break's arc is `text-muted`.

#### Sprint summary (checklist F12)

- Since #431 the end of a sprint takes the countdown's place in the Now card (see "Today" above): the minutes as a headline, one line of facts, and what the shield stopped (#349) beneath; the momentum change and the streak are in the Momentum card.
- The plan is said once, in the note's prompt ("You planned: …. What moved?"), then the one-line note.
- Ending early adds one neutral line under the headline ("Ended early. It'll recover."), never red.

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
- **The rail's Buy button** is Secondary since #431, so it never competes with Start sprint, and it is hidden while a sprint runs (`MainViewModel.BuyVisible`).
- **Window:**
  - The app uses the standard Windows title bar, which Mica covers too (#430). While a sprint runs it reads "Basalt — 11:26", the same text as the ring. Part A allows a custom or extended title bar when it preserves Windows behaviour and accessibility.
  - The window's base is Mica or its solid fallback (§4, "Mica and its fallback").
- **Tray icon:**
  - The app's Causeway tile (`FlowShield.ico`, built from `design/brand/basalt-icon.svg`).
  - During a sprint it counts down the minutes left, drawn in `primary` on `primary-ink` so it follows the app theme; the running tile (`FlowShield.Running.ico`, the Firm variant) is its fallback.

### 12a. Mac app specifics

The Mac beta (#426) applies Part A's Apple-platforms rule like this:

- **Structure:** one main window with a `NavigationSplitView` sidebar (Today, History, Blocked Apps, Schedule). Settings isn't a page: it is the standard Settings window (⌘,) with panes. Toolbar actions also appear in the menus. A Sprint menu carries Start, End and the shield levels.
- **Menu bar extra:** the Mac counterpart of the Windows tray. It shows the minutes left during a sprint and offers start, end, open and quit. Closing the main window keeps Basalt running there.
- **Colour:** `tools/build_tokens.py` writes `AppleApps/Basalt/Tokens.xcassets`, one colour set per app token, named like the WPF keys (`Primary`, `Ink`, `Amber`…), with light and dark appearances, plus `AccentColor` = `primary`. Window and content backgrounds use the system's semantic colours; Basalt's tokens carry meaning (accent, status, shields, charts).
- **Type:** SF Pro through SwiftUI text styles, with monospaced digits for the timer and stats.
- **Shields:** SF Symbols escalate by shape, not colour: `shield` (Soft), `shield.lefthalf.filled` (Firm), `lock.shield.fill` (Sealed).
- **Materials:** no custom glass on cards, lists or the timer. The Soft notice and the Firm warning are ordinary windows with solid surfaces, because they carry text the person must read.

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
2. `tools/build_tokens.py` generates `DesktopApp/Styles/Tokens.xaml` (dark), `DesktopApp/Styles/Tokens.Light.xaml` and the colour blocks between the `tokens:` markers in `Website/styles.css`. `App.xaml` merges the Tokens dictionary; see the engineering facts in §12. It also writes the Mac app's colour sets in `AppleApps/Basalt/Tokens.xcassets` (§12a), leaving out the tokens in `apple_skip`. Since #430 it also writes `app_brushes` into both Tokens dictionaries: the elevation surfaces, the gradients and the shadows (§2), so they swap with the theme like the colours.
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
- [x] Inter embedded in the app and served on the site, replacing Syne, Source Sans 3 and Segoe UI, with tabular figures for numbers (section 3). Done in #171 (A1: `DesktopApp/Assets/Fonts/Inter-{Regular,Medium,SemiBold}.ttf` + `InterDisplay-SemiBold.ttf`, `OFL.txt`, `Typography.NumeralAlignment="Tabular"` on Today/Sleep Blocking numbers) and #172 (B1: `Website/fonts/InterVariable.woff2` + `OFL.txt`, no `fonts.googleapis.com` links remain, `font-variant-numeric: tabular-nums` used 5× in `styles.css`). The app part was superseded by #430 (Segoe UI Variable); the site still serves Inter.
- [x] Spacing and radii normalised to the scales (section 4). Done in #182 (A2): `RadiusChip`/`RadiusControl`/`RadiusCard` resources referenced 15× in `Theme.xaml`; `--radius-chip: 6px` added and used in `styles.css` (#178, B3). #191 (merged) extended the same scale to the new adaptive layout.
- [x] Icon set adopted, and the Unicode glyphs in navigation replaced (section 5). Done in #151: Lucide outlines in `Styles/Icons.xaml`, navigation and the two list views. Shield glyphs followed separately (section 6).
- [x] Shield glyphs built and used on Today, the site, notifications and the tray (section 6). Done in #176 (A4: `DesktopApp/Styles/ShieldGlyphs.xaml`, shared by the shield chips and the beside-timer glyph) and #178 (B3: inline SVG `<symbol>` set in `Website/index.html` reusing the same crest geometry, used by the shields section).
- [x] Destructive and quiet button variants added (section 7). Done in #180 (A3: `BtnQuiet`/`BtnDanger` styles in `Theme.xaml`) and #178 (B3: `.btn-quiet`/`.btn-danger` classes in `styles.css`).
- [ ] Copy pass against the word list and tone rules, including one consistent spelling of licence/license (section 9). Partial: B4/B6 (#184, #188) fixed tone on the site, but the two spellings are still mixed rather than one chosen consistently — `DesktopApp/Views/SettingsView.xaml` shows the user-facing label `Text="LICENSE KEY"` and `AutomationProperties.Name="License key"` (American), while other app and email copy uses "licence" (British); the site mixes both across `index.html`/`legal.html`/`success.html`/`checkout.js`. Left unticked.
- [x] Today redesigned (#431): the Now card in its three states, Up next, Momentum and template cards, the setup panel with acrylic over Mica, the ring's gradient arc and the glow, the lit mark, and Buy made Secondary and hidden during a sprint ("Today" in section 7).
- [x] Redesign foundations in the app (#430): the depth tokens and generated surfaces, gradients and shadows (sections 2, 14); Segoe UI Variable with named optical cuts, replacing the embedded Inter (section 3); Segoe Fluent Icons, replacing Lucide in the app (section 5); radii 6 / 8 / 12 and Mica with its fallback (section 4); raised buttons, recessed fields, the segmented selector, the stated switch, the disclosure and the dropdown (section 7). The screens' new layouts follow in their own PRs.
- [x] Reduced-motion support in the app and on the site (section 8). Done in #176 (A4: `DesktopApp/Infrastructure/Motion.cs` reads `SystemParameters.ClientAreaAnimation` and zeroes every duration when it's off) and pre-existing site support (`prefers-reduced-motion` in `Website/index.html`/`styles.css`).
- [x] Light theme in the app (section 12, checklist F21). Done in #237: `App.xaml` merges `Styles/Tokens.xaml` as its own entry and `DesktopApp/Services/ThemeService.cs` swaps it for the generated `Tokens.Light.xaml`; Settings → Appearance offers System (the default, following Windows) / Dark / Light, and every colour reference in the app's XAML is a `DynamicResource`.
