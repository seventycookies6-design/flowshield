# FlowShield design system

One visual language for the desktop app and the website, so that a customer
moving from the site to the installer to the app sees the same product. It
builds on what already exists: the stone and teal palette from the site
redesign (#27), which the app adopted in #32. It sets rules where the two still
differ.

The features these rules will be applied to are listed in
**`LAUNCH_FEATURE_CHECKLIST.md`**.

---

## 1. The idea: a calm instrument

**FlowShield should feel like a precise, quiet tool you trust, not a wellness
app and not a game.**

The competitor research (14 September 2026, summarised in the checklist) found
the category splits into:

| Style | Seen in | What it communicates |
| --- | --- | --- |
| Bright green, cartoon illustrations, collectables | Forest | Fun, playful. Some users find it childish for serious work. |
| Gradients, stock photography, generic "wellness" look | Opal, Freedom | Friendly, lifestyle. Hard to tell apart. |
| Dark, dense, settings-heavy utility | Cold Turkey, FocusMe | Powerful, serious. Often described as intimidating. |
| System-native, muted | Windows Focus Sessions | Built-in, safe. Forgettable. |

FlowShield sits in a space none of them occupy: **the seriousness of a utility
with the calm and clarity of a well-made instrument.** Think of a good watch
face or a camera's controls. Everything has a purpose, the important number is
large, and nothing flashes for attention.

### Principles

1. **One thing matters at a time.** During a sprint, the time left and the shield are the screen. Everything else recedes.
2. **Calm is the default; colour means something.** Surfaces are neutral stone. Teal marks the active or primary thing. Amber and rose appear only for warnings and problems.
3. **Strength is shown, not shouted.** Shield levels escalate through shape and fill, not alarm colours or exclamation marks.
4. **Honest over impressive.** Real screenshots, real numbers, plain words. Never a mock-up of a feature that doesn't exist, never generated people or UI.
5. **Kind, never guilty.** Ending early, a broken streak or a lost day are stated neutrally, with a way forward.
6. **Accessible by construction.** Every colour pair passes WCAG AA, every control works from the keyboard, and motion respects the reduce-motion setting.

---

## 2. Colour

### Tokens

Both themes share the same token names in the app and on the site. **Dark is the
app's default; the site follows the visitor's system setting.**

Values marked **change** differ from what ships today. They fix contrast
failures measured on 14 September 2026 (see "Contrast" below).

| Token | Dark | Light | Use |
| --- | --- | --- | --- |
| `bg` | `#121110` | `#E6E4DF` | Window and page background |
| `bg-soft` | `#181716` | `#DDDBD5` | Navigation rail, alternating bands |
| `surface` | `#1C1B19` | `#F4F3EF` | Cards, panels, dialogs |
| `surface-2` | `#242220` | `#FAF9F6` | Controls, inputs, hover fills on surfaces |
| `text` | `#F2F0EB` | `#1A1917` | Headings, primary text, large numbers |
| `text-muted` | `#B0ADA5` | `#5C5954` | Body copy, labels |
| `text-faint` | **change** `#7E7B73` → `#948F86` | **change** `#8A867E` → `#625E57` | Captions, hints, placeholders |
| `primary` | `#3AA892` | `#0C6B5C` | Primary buttons, active states, the timer ring, focus |
| `primary-hover` | `#4FBEA7` | `#095548` | Hover and pressed primary |
| `primary-ink` | `#0B1F1B` | `#F4F3EF` | Text and icons on `primary` |
| `primary-soft` | `#3AA892` at 20% | `#0C6B5C` at 12% | Selected chips, soft highlights |
| `ok` | `#5EC987` | **change** `#2F7D4A` → `#276A3E` | Completed, success |
| `warn` | `#E0B35A` | **change** `#9A6B1F` → `#7A5413` | Trial ending, "are you sure" |
| `danger` | `#EF7A88` | **change** `#B33A4A` → `#A3334A` | Errors, destructive actions |
| `border` | `text` at 12% | `text` at 12% | Card and control outlines |
| `border-strong` | `text` at 22% | `text` at 22% | Hovered or focused outlines, toasts |
| `focus-ring` | `primary` at 50% | `primary` at 45% | Keyboard focus outline, 2 px |
| `scrim` | `bg` at 95% | `bg` at 92% | Behind the lock screen and dialogs |

### Rules

- **No legacy names.** `Violet`, `VioletBright`, `Cyan`, `Glass*`, `Accent` and `WindowBg` are gone from `Theme.xaml`, and `--violet`, `--violet-bright`, `--cyan`, `--grad` and `--glass*` are gone from `styles.css`. Colours are referenced by the token names above and nothing else, so no new code reaches for a colour that no longer means anything. (The site keeps a short alias block — `--bg`, `--ink`, `--edge` and friends — for the legal and success pages; those are token names under a shorter spelling, not dead colours.)
- **No hard-coded colours in views.** Every colour in XAML and CSS comes from a token. (Today, for example, the lock screen's backdrop is a literal hex value in `MainWindow.xaml`.)
- **Teal is structural, not decorative.** Teal may appear in as many places as a screen needs, provided it always means one of three things:
  - **state**: something is on, active or running (an engaged shield, an enabled toggle, the tier badge's trial dot);
  - **selection**: the current navigation item, the chosen chip, the focused control;
  - **progress**: the timer ring, progress bars, chart series.

  The primary action is teal because it is the thing that changes state. Nothing is teal just to look branded: no teal headings, dividers, borders, illustrations or background washes. If everything is teal, nothing is. What earns the colour is that it always means the same thing, not that it is rare. (Replaces the earlier "teal is scarce" rule, #147.)
- **Status colours are for status only.** Amber and rose never decorate. `ok` green is for "done", not for "go".
- **No gradients, glows or glass.** The purple glows removed in #32 stay gone. Depth comes from surface steps and soft shadows.

### Contrast

Measured against WCAG 2.1 on 14 September 2026 (normal text needs 4.5:1):

| Pair | Dark | Light | Result |
| --- | --- | --- | --- |
| `text` on `bg` | 16.6 | 13.8 | Pass |
| `text-muted` on `bg` | 8.4 | 5.5 | Pass |
| `text-faint` on `surface` (current) | 4.07 | 3.27 | **Fails both** |
| `text-faint` on `surface` (proposed) | 5.35 | 5.81 | Pass |
| `primary` on `bg` | 6.5 | 5.1 | Pass |
| `primary-ink` on `primary` | 5.9 | 5.8 | Pass |
| `warn` on `bg` (light current → proposed) | — | 3.68 → 5.32 | **Fails**, fixed |
| `ok` on `bg` (light current → proposed) | — | 3.98 → 5.14 | **Fails**, fixed |
| `danger` on `bg` (light current → proposed) | — | 4.56 → 5.28 | Borderline, fixed |

Any new token or pairing gets measured the same way before it ships.

---

## 3. Typography

### One family, everywhere

Today the site uses **Syne** for headings and **Source Sans 3** for text, and
the app uses **Segoe UI Variable**. That's the most visible difference between
the two. Both are replaced by a single family, **[Inter](https://rsms.me/inter/)**,
in the app and on the site (decided in #147).

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
- **In the app:** embed Inter as a resource in `DesktopApp`. It is SIL Open Font License, which permits bundling; keep the licence text (`OFL.txt`) alongside the font files. Don't depend on a web font service at runtime. Embed only the weights the scale uses.
- **On the site:** serve Inter with `font-display: swap` and a fallback tuned so text doesn't shift when the web font loads. Remove the Syne and Source Sans 3 links once Inter is in.
- **Tracking** is set per role in the scale below, never ad hoc. In WPF there is no letter-spacing property on `TextBlock`, so heading tracking is approximated there, with weight, or with the static Inter Display cut for `display` and `timer` sizes if that reads closer. Match the site visually rather than numerically.

### Scale

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
- **No more than three weights on one screen** (400, 500 and 600, with 700 reserved for the site hero). With one family, weight does the work a second face used to do, so it gets one more step, used consistently.
- **Tighter as it gets bigger:** negative tracking only at `title` size and above; small text stays at 0 so it remains legible.

---

## 4. Space, shape and depth

- **Spacing scale (4-based):** 4, 8, 12, 16, 24, 32, 48, 64. Padding and gaps use these values only. Card padding is 24, space between cards 16, page margins 32 in the app.
- **Corner radius:** 6 for small chips and tags, 10 for buttons, inputs and toggles, 14 for cards and dialogs, and fully round for pills and the tier badge. Today's app uses 8, 10, 11, 12, 13 and 14 interchangeably; normalise to this set.
- **Borders:** 1 px `border` on cards and controls; `border-strong` on hover and focus.
- **Shadows**, two levels only:
  - `soft` for cards on the site and for toasts;
  - `lift` for dialogs and the lock screen card.
  - In dark mode, prefer a surface step over a shadow.
- **Layout:**
  - **App:** a 240 px navigation rail and a content area with a 720 px readable maximum for settings-like pages. Today and History may use the full width.
  - **Site:** a 1120 px maximum width (`--maxw`).
  - **Minimum app size:** 800 × 540 (Roadmap 1.13).

---

## 5. Icons

- **Replace the Unicode glyphs** now used for navigation (`◷`, `⊘`, `☾`, `⚙`). They render differently across Windows versions and don't match each other.
- **Use one outline icon set** at 1.75 px stroke on a 24 px grid, the same on the site and in the app. [Lucide](https://lucide.dev) fits the style and is ISC-licensed, which permits this use; confirm the licence and keep its notice when adopting it. Convert the icons used to XAML `Path` geometry, and to inline SVG on the site.
- **Sizes:** 16 px inline with text, 20 px in navigation and buttons, 24 px for feature headings.
- **Icons inherit** the text colour of their context; only an active item's icon is `primary`.
- **The FlowShield shield mark** is the only filled brand icon. Keep it identical everywhere: the site favicon, the app's title bar and taskbar icon (Roadmap 1.6), the tray icon and the installer.

---

## 6. Shield levels: the signature visual

The three shields are FlowShield's most distinctive idea, so they get a
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
- **Build the glyph once** per platform: a XAML `DrawingImage` resource and an SVG symbol on the site.

---

## 7. Components

Each component is defined once. In the app it's a style in `Theme.xaml`; on the
site it's a class in `styles.css`. Names match across the two.

### Buttons

| Variant | App style | Site class | Look | Use |
| --- | --- | --- | --- | --- |
| Primary | `BtnPrimary` | `.btn-primary` | `primary` fill, `primary-ink` label | One per view: Start sprint, Buy FlowShield, Activate |
| Secondary | `BtnGhost` | `.btn-ghost` | `surface-2` fill, `border`, `text` label | Alternatives: Skip break, Copy key |
| Quiet | `BtnQuiet` | `.btn-quiet` | No fill, `text-muted` label, fill on hover | Low-emphasis: Deactivate, Open log |
| Destructive | `BtnDanger` (*new*) | `.btn-danger` (*new*) | `surface-2` fill, `danger` label and border | Delete everything, End sprint anyway |

- **Height** 40 (app) or 44 (site), radius 10, horizontal padding 20, `label` type.
- **States:** hover uses `primary-hover` or `border-strong`; pressed darkens by one step; disabled is 45% opacity with no hover; focus shows a 2 px `focus-ring` offset by 2 px.
- **Button text is a verb:** "Start sprint", not "OK".

### Cards

- **Look:** `surface` fill, 1 px `border`, radius 14, padding 24.
- **Heading:** an optional `eyebrow`, then a `title`.
- **Stat cards:** one `stat` number, one `caption` label, and optionally a delta in `ok` or `text-muted` (never `danger` for a momentum drop; see Voice).

### Form controls

- **Text inputs:** 40 high, `surface-2` fill, `border`, radius 10; `border-strong` on hover; `focus-ring` on focus.
- **Labels and hints:** labels sit above in `label` type; hints below in `caption`.
- **Toggles:** a 46 × 26 track. Off is `surface-2` with a `text-faint` knob; on is `primary` with a `primary-ink` knob. The label sits to the left, with an optional one-line caption.
- **Segmented choices** (sprint length, shield level): chips in a row, radius 10, `surface-2`; the selected chip gets `primary-soft` fill and a `primary` outline.

### Timer ring (Today)

- **Ring:** 12 px stroke on a `track` circle, with the progress arc in `primary` and a round cap.
- **Centre:** the `timer` number, a `caption` state line ("Shield II engaged"), and the shield glyph.
- **Progress:** updates once a second with no easing. When reduced motion is on, the arc still updates, but no pulse or glow is ever added.

### Sprint summary card (checklist F12)

- A `surface` card with **three stats in a row**: minutes, distractions caught, momentum change.
- Below it the intention ("You planned: …"), then the one-line journal input.
- A completed sprint shows a small `ok` check; an early end shows a neutral `text-muted` dot, never red.

### Lock screen (trial ended)

- **Backdrop:** the `scrim` token over the page content, with the navigation rail left visible.
- **Card:** centred, max width 520, `lift` shadow.
- **Content:** a `display` headline, one paragraph, one Primary button (Buy), a divider, then the licence key field with a Secondary Activate button.

### Intervention moments (Soft overlay, Firm warning, blocked page)

These are where FlowShield steps between the user and a distraction (checklist
F7, and F10's blocked page). They share one pattern:

- A compact `surface` panel with the shield glyph, one sentence ("Discord is on your blocklist until 5:45 PM"), and the time left.
- Soft adds one Secondary action ("Continue anyway"); Firm shows a short countdown before closing.
- **No red, no alarm icons, no shaking animations.** It should feel like a polite colleague tapping your shoulder.

### Toasts and native notifications

- **In-app toast:** `surface` with `border-strong`, radius 12, bottom-centre, 4 seconds, one line.
- **Native Windows notifications:** title in sentence case, one line of body, the app icon, and at most two actions.

### Tier badge

A pill at the bottom of the navigation rail: `surface-2` with an `eyebrow`
label and a small status dot.
- **Trial:** `primary` dot.
- **Purchased:** `ok` dot.
- **Trial ended:** `warn` dot.

### Charts (momentum trend, weekly view, heatmap)

- **Line charts:** a single series in `primary`, 2 px, with no area fill. Gridlines are `border` and horizontal only. Axis labels use `caption` in `text-faint`.
- **Heatmap:** five steps from `surface-2` to `primary`, with a visible legend. Never rely on colour alone; hovering or focusing a cell shows the value.
- **No 3D, no pie charts,** no more than two series.

---

## 8. Motion

- **Durations:** 120 ms for hovers and presses, 200 ms for panels and selection changes, 300 ms for page transitions. Ease-out for entering, ease-in for leaving.
- **Movement:** fades and short slides of 8 px or less only. Nothing bounces, spins or shakes.
- **No celebratory effects:** no confetti, fireworks or sound, including for milestones (checklist F14). A milestone may fade in and settle.
- **Reduced motion:** honour the setting everywhere. `prefers-reduced-motion` on the site; in the app, Windows' "Animation effects" (`SystemParameters.ClientAreaAnimation`). With it on, transitions become instant and the site's hero video (checklist F27) shows its poster frame instead.

---

## 9. Voice and copy

FlowShield talks like a calm, competent friend who respects your time.

### Tone

- **Plain and direct:**
  - "Discord closed — it's on your blocklist."
  - Not "Oops! Looks like you got distracted 😅".
- **Neutral about failure:**
  - "Ended early. Momentum −6 — it recovers with your next sprint."
  - Not "You broke your streak!".
- **Specific:** "Sealed until 5:45 PM", not "Locked for now".
- **No exclamation marks and no emoji** in product copy.

### Words to use consistently

| Use | Not |
| --- | --- |
| sprint | session, pomodoro, focus block |
| shield, shield level | mode, strictness, difficulty |
| Soft, Firm, Sealed | Level 1/2/3 on their own |
| momentum | score, points, XP |
| blocklist | blacklist, block set |
| buy FlowShield, licence | upgrade, Pro, subscription |
| free trial | free version, free plan |
| ended early | failed, gave up, quit |

(The UI currently spells "License key"; pick one spelling, British "licence" or
American "license", and use it everywhere in both products. The app and email
mostly use "licence".)

### Honesty rules for copy

- Never describe an unshipped feature (the tier 5 claims test enforces this for pricing).
- Name a competitor or quote its price only after re-checking the source; see the checklist's F24.
- Prices always include "plus tax where it applies" near the number on the site.

---

## 10. Imagery and marketing assets

- **Real product only:** screenshots and screen recordings of the shipped app, with sample data and never a real blocklist or licence. No stock photos, AI-generated people, or mock-ups of unshipped screens.
- **Framing:** screenshots sit in a `surface` frame with a 14 radius and a `soft` shadow, never a fake laptop or phone frame.
- **Video:** muted, looping, under about 2 MB on desktop and 1 MB on mobile, with a poster frame, `playsinline`, and a text description for screen readers.
- **Illustration:** where a diagram helps, such as the "student day" timeline, use flat shapes in the token colours and the shield glyphs, not characters.
- **Social and store images:** the same screenshots and type, on `bg`.

---

## 11. Website specifics

- **The site already follows most of this** (it's the source of the palette). Remaining work:
  - apply the contrast fixes;
  - remove the legacy `--violet`, `--cyan` and `--grad` aliases;
  - adopt the icon set and shield glyphs;
  - add the `.btn-quiet` and `.btn-danger` variants;
  - replace Syne and Source Sans 3 with Inter (section 3);
  - use tabular figures for prices.
- **Theme toggle:** keep the light/dark toggle; default to the visitor's system setting.
- **Performance:** the hero must render text and the primary button before any image or video loads. Fonts use `swap`.

## 12. Desktop app specifics

- **Theme:**
  - Dark is the default until checklist F21 adds the light theme with a system-follow option.
  - Build the light theme from the same tokens, as a second `ResourceDictionary`, not by overriding individual views.
- **Window:**
  - Keep the standard Windows title bar for now.
  - A custom title bar is out of scope; it's easy to get wrong with snapping and accessibility.
- **Tray icon:**
  - A monochrome shield that follows the taskbar theme.
  - It becomes filled `primary` with a progress notch during a sprint.

---

## 13. Accessibility checklist

- [ ] All token pairs meet WCAG AA, with the fixes in section 2 applied.
- [ ] Every interactive element is reachable and usable from the keyboard, with a visible 2 px focus ring.
- [ ] Every control has an accessible name; existing `AutomationId`s are kept.
- [ ] Colour is never the only signal: shield levels use bars and labels, and status uses icons and text.
- [ ] Text scales with Windows text-size settings and browser zoom to 200% without clipping.
- [ ] Reduced motion is honoured in the app and on the site.
- [ ] Video has a poster, no sound, and a text description.

---

## 14. Making it the single source of truth

Colours and sizes are duplicated today between `DesktopApp/Styles/Theme.xaml`
and `Website/styles.css`, and they already drift. Recommended implementation, as
its own issue:

1. Create `design/tokens.json` with every token in section 2 (both themes), the type scale, spacing and radii.
2. Add `tools/build_tokens.py` to generate `DesktopApp/Styles/Tokens.xaml` (dark), `DesktopApp/Styles/Tokens.Light.xaml` and the marked colour blocks in `Website/styles.css` from it. `Theme.xaml` merges `Tokens.xaml`, and `styles.css` carries the generated values between its `tokens:` markers.
3. Add a tier 5 test that runs the generator's `--check` mode and fails if the committed files are stale. That makes drift impossible and gives the doc steward something concrete to check.
4. Add `DESIGN_SYSTEM.md` to the doc steward's editable list, so this document stays in step with the tokens.

## 15. Adoption checklist

Who owns each task is in `LAUNCH_FEATURE_CHECKLIST.md` → "Who builds what": the token generator is Keenan's and lands first; the rest are Miles's. Work through these as separate small pull requests. Each is visual-only, keeps
`AutomationId`s, and includes before and after screenshots in the PR.

- [x] Tokens: `design/tokens.json`, the generator and the parity test (section 14). Done in #41: colours only so far; type, spacing and radii can be added to the JSON as their tasks land.
- [ ] Contrast fixes applied in the app and on the site (section 2).
- [x] Legacy colour aliases removed from `Theme.xaml` and `styles.css`. Done in #130.
- [ ] No hard-coded colours left in app views.
- [ ] Inter embedded in the app and served on the site, replacing Syne, Source Sans 3 and Segoe UI, with tabular figures for numbers (section 3).
- [ ] Spacing and radii normalised to the scales (section 4).
- [x] Icon set adopted, and the Unicode glyphs in navigation replaced (section 5). Done in #151: Lucide outlines in `Styles/Icons.xaml`, navigation and the two list views. Shield glyphs are section 6 and still to come.
- [ ] Shield glyphs built and used on Today, the site, notifications and the tray (section 6).
- [ ] Destructive and quiet button variants added (section 7).
- [ ] Copy pass against the word list and tone rules, including one consistent spelling of licence/license (section 9).
- [ ] Reduced-motion support in the app and on the site (section 8).
- [ ] Light theme in the app (section 12, checklist F21).
