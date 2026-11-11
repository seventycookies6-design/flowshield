# Redesign, November 2026: the target

This folder is the target for the app and site redesign. `DESIGN_SYSTEM.md`
Part A holds the binding rules it follows. Part B describes what has shipped,
and each implementation PR updates its own section. Once every screen has
shipped, this folder becomes history.

## Where it came from

The design came from a blind outside review of the current app and site, run
in rounds by a separate design agent (Claude Fable 5.2). The agent saw only
screenshots, the live site and a one-paragraph product description, not this
repo. Rounds one to three drifted into a new identity and were rejected. Round
four is a redesign of the current Basalt: same sidebar, teal, logo, ring and
voice, with depth, real controls and less clutter. Both owners chose round four.

## The screens

`mockups/` holds the target screens as PNGs, at the size of the capture each
one replaces. They were rendered on Linux, so Selawik (Microsoft's open,
metric-compatible stand-in) takes Segoe UI Variable's place. On Windows the
real face is finer.

| File | Screen |
| --- | --- |
| `app-today-ready-dark.png`, `-light.png`, `-small-dark.png` | Today, ready to start |
| `app-today-ready-fallback-dark.png` | The same with transparency effects off |
| `app-sprint-running-dark.png` | Today with a sprint running |
| `app-setup-panel-dark.png`, `-light.png`, `-fallback-dark.png` | The setup panel (the full sprint settings) |
| `app-plans-dark.png` | Plans: blocklists, schedules and templates |
| `app-sprint-complete-dark.png` | End of a sprint |
| `app-notice-dark.png`, `app-notice-second-try-dark.png` | The full-screen notice (Soft) |
| `site-home-desktop-light.png`, `site-home-phone-dark.png` | Site, first screen |
| `site-strengths-desktop-light.png` | Site, the Soft / Firm / Sealed section |

`reference-css/` is the mockups' own CSS. It's the most exact record of the
depth values, colours and spacing, and is useful when porting to XAML and
`Website/styles.css`. It isn't production code. New colours still enter
through `design/tokens.json` and `tools/build_tokens.py`.

**Not drawn yet:** History, Settings, first run, the end of the trial, the
notice in light, and high contrast. Apply the same system to them.

## The depth system

| Level | What sits there | Dark | Light | Top highlight | Shadow (straight down) |
| --- | --- | --- | --- | --- | --- |
| E0 Mica | The window and title bar; the space between surfaces | `#18191B`, wallpaper tint | `#EDEDEB`, tinted | none | none |
| E1 resting | Sidebar, Up next, Momentum, Templates, the Plans sections | `#1F2123` | `#F6F6F4` | 1 px, white 5.5% (light 85%) | 0 1 2 + 0 2 6 |
| E2 raised | Now (the thing you act on); the selected sidebar item | `#27292C` | `#FDFDFC` | 1 px, white 8.5% (light 100%) | 0 2 4 + 0 12 28 |
| E3 acrylic | Setup panel, dropdowns, flyouts, menus | `#2C2E32` at 74%, 28 px blur | `#FBFAF8` at 78% | 1 px, white 12% | 0 8 16 + 0 28 64 |

- **Hairline:** every surface has a 1 px outer hairline (black 34% in dark, 10% in light).
- **Controls:** buttons are raised, with a lit top edge and a 1 px shadow. Text fields and selector tracks are recessed, with the Windows bottom line.
- **Gradients, in four places only:** the ring's arc, the Primary button, a toggle that is on, and the teal glow while a sprint runs.
- **Fallback solids:** Mica becomes `#1B1C1E` in dark and `#EFEFED` in light, and acrylic becomes solid E3.
- **Corner radius:** surfaces 12, controls 8.

## Typeface and icons

- **App type:** Segoe UI Variable. Display is for the countdown and titles, Text for everything else, with Segoe UI as the fallback on Windows 10.
- **Site type:** Segoe UI Variable first, then self-hosted Inter.
- **App icons:** Segoe Fluent Icons, plus Basalt's shield glyphs.
- **Site icons:** Lucide stays.

**WPF engineering fact, measured on Windows 11 build 26300 (2026-11-11):**

| WPF family name | Resolves to |
| --- | --- |
| `Segoe UI Variable Display`, `Segoe UI Variable Text`, `Segoe UI Variable Small` | `SEGUIVAR.TTF` |
| `Segoe UI Variable` (bare) | `SEGOEUI.TTF`, plain Segoe UI |

So always name the cut, for example
`FontFamily="Segoe UI Variable Text, Segoe UI"`.

## Controls (who gets what)

| Screen | Control |
| --- | --- |
| **Today, ready** | Set up (button, opens the setup panel). Soft / Firm / Sealed (segmented selector). Your plan (text field). **Start sprint** (Primary). Start on each template (button). "Schedules in Plans", "Edit in Plans" (links). "How momentum works" (help link). |
| **Sprint running** | Details (disclosure with a chevron). End sprint early (button). No Primary. Buy is hidden while a sprint runs. |
| **End of sprint** | What moved? (text field). **Save note** (Primary). Start break, Start next sprint (buttons). |
| **Setup panel** | Close (icon button). Length 15 / 25 / 45 / 60 / 90 / Custom (segmented; Custom shows a number field). Sprints in a row 1 to 4 (segmented). Blocklist (dropdown). Done (button). |
| **Plans** | New blocklist, Add an app, Add schedule, New template (buttons). Edit on every row (button). Schedule on/off (toggle, with "On"/"Off" written beside it). Start on each template (button). ⋯ menu (Restore built-in templates). No Primary. |
| **Notice** | **Back to work** (Primary, but not the default). Close the app (button). Allow 5 minutes (button, with its own longer delay). |

## The notice's input guard (binding in Part A)

- **No default and no initial focus.** No `IsDefault` or `IsCancel`, and focus starts on the band, not on a button.
- **Enter does nothing:** a `PreviewKeyDown` handler swallows it.
- **The 1.5-second lock.** Buttons stay enabled, so their labels keep full contrast, but they aren't focusable and ignore clicks until a 1.5 s timer fires. A bar and a short countdown show the wait.
- **After the lock:** a click works, and so does a deliberate Tab then Space.
- **Try count:** shown from the second try.
- **No plan typed:** the headline falls back to "‹App› is on your blocklist until ‹time›".

This changes behaviour, so it needs a test in the matching tier.

## How each piece is built in WPF on .NET 10

| Piece | How | Risk |
| --- | --- | --- |
| Mica | `DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE = 38, DWMSBT_MAINWINDOW = 2)`, with the window background transparent where Mica should show. The app already calls `DwmSetWindowAttribute` for the dark title bar. | The call returns S_OK on the test VM, but **not visually verified**: the VM's virtual GPU has no 3D, so Windows turns transparency off and shows the solid fallback. Check on a real Windows 11 PC. |
| Acrylic panel | WPF has no backdrop-blur brush. When the panel opens, take one `RenderTargetBitmap` of the page beneath it, show it under a `BlurEffect` (radius about 28) with the 74% tint, and re-take it on resize or theme change. | The costliest piece. The solid fallback reads fine if it's cut. |
| Acrylic dropdowns and menus | A `Popup` is its own window, so `DWMSBT_TRANSIENTWINDOW = 3` on its handle may give real acrylic. | The call returns S_OK, but it's unverified for the same reason as Mica. Solid E3 is the fallback. |
| Ring | A `Path` with an `ArcSegment`. The stroke is a two-stop diagonal `LinearGradientBrush` with round caps (WPF has no conic brush). | Free |
| Glow | An ellipse with a `RadialGradientBrush` behind the ring, present only while a sprint runs. | Free |
| Notice | A borderless topmost window per screen: a 56% black scrim and the band at a 92% tint, with no blur. | Free |
| Type | See the engineering fact above. | Solved |

## Decisions and known deviations

- **Wording:** the binding word list (`DESIGN_SYSTEM.md`) still says *shield* and *shield level*, but the mockups say *strength*. Until the owner decision in #365, implementation keeps the word list's terms and the mockups' layout.
- **Skip break is removed.** Starting the next sprint is the skip, so `app-sprint-complete-dark.png`'s "Skip break" button doesn't ship.
- **No middle-dot separators.** Where a mockup uses "·" between facts, use commas or separate lines.
- **Site captures** in the mockups are renders. The real site uses captures of the real build, taken after the app screens ship, because Part A requires real product imagery.
- **Sample data:** template contents, the 6:00 PM schedule and the app icons in the mockups are sample data.

## Suggested order

1. **Foundations:**
   - depth colours added to `design/tokens.json`, then run the token build script
   - Segoe UI Variable and Segoe Fluent Icons
   - control styles: raised button, recessed field, segmented selector, toggle, chevron disclosure
   - Mica with its fallback
2. **Today,** in its three states, and the setup panel.
3. **The notice,** with its input-guard test.
4. **Plans,** which merges Blocked Apps and Schedule and keeps every existing `AutomationId`.
5. **History, Settings, first run and trial ended,** applying the system.
6. **Site:** the same depth in CSS, the first screen, the Soft / Firm / Sealed cards, then real captures from the new build.
