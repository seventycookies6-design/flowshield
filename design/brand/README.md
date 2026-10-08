# Basalt logo: "Causeway"

The approved logo for the Basalt rename. This folder is the source of truth;
an implementing agent should not redraw it, only apply it where listed below.
The design canvas it came from (private, owner: Miles) is
https://claude.ai/artifact/JJus1N6LhATsvDs9htCP5J. It also holds three
rejected directions (single column, stacked drums, hex "b").

## The idea

Three hexagonal basalt columns packed edge to edge in plan, standing at three
heights, seen from above and in front. It echoes the column row on the
site's hero (`.hero::after`, DESIGN_SYSTEM.md §4 "Stone") and says what the
product does: orderly structure standing between you and distraction.

It follows the existing rules: flat fills only (no gradients, glows or glass),
teal only for *state*, one mark identical everywhere.

## Files

| File | Use |
| --- | --- |
| `basalt-icon.svg` | App icon / taskbar / favicon / installer: idle. 100x100 tile, radius 19, ground `#17181B`. |
| `basalt-icon-soft.svg` | Sprint running on Soft: front column's top is teal. |
| `basalt-icon-firm.svg` | Sprint running on Firm: front and middle tops are teal. |
| `basalt-icon-sealed.svg` | Sprint running on Sealed: all three tops are teal. |
| `basalt-mark-on-light.svg` | Bare mark (no tile) beside the wordmark on light backgrounds (`bg` `#ECEBE7`). Joints are `#ECEBE7`. |
| `basalt-mark-on-dark.svg` | Bare mark on dark backgrounds (`bg` `#141517`). Joints are `#141517`. |
| `basalt-mark-mono.svg` | One colour via `currentColor`; set `--basalt-ground` to the surface colour (joints). Tray, print, engraving. |

## Geometry (all coordinates in the 100x100 tile)

- Regular hexagon prisms, flat-topped, circumradius `r = 7.5`, so one column is `2r = 15` wide in plan. The plan view is squashed to 50% vertically, so a top face is 15 wide by about 6.5 tall.
- Visible side height: front column `1.2r` (18), middle `1.8r` (27), back `2.4r` (36): steps of `0.6r`.
- Light comes from the upper left: left faces are lightest, right faces darkest.
- Mark spans x 23.75 to 76.25, y 19 to 81 (viewBox `22 17 56 66` for the bare mark).
- Joints: 1 unit stroke in the ground colour, `stroke-linejoin: round`.
- Clear space: `r` on every side. Minimum: 16 px as a tile, 20 px bare.
- The geometry is exact in the SVGs; copy the polygons, do not trace.

## Colour

Faces are fixed greys (they are not theme tokens: the mark is identical in both themes, only the bare mark swaps between its light and dark versions).

| Face | On tile / on dark | On light |
| --- | --- | --- |
| Top (idle) | `#E6E6E3` | `#8B8E93` |
| Left | `#A3A6AA` | `#55585D` |
| Front | `#74777C` | `#36383C` |
| Right | `#4B4E53` | `#1F2023` |
| Lit top (sprint) | `#3AA892` (the dark-theme `primary` token) | not used |
| Tile ground | `#17181B` | |

Lit tops use the teal for *state* (a sprint is running), which is exactly the
meaning DESIGN_SYSTEM.md §2 allows. Shield level is shown by how many tops are
lit (1 Soft, 2 Firm, 3 Sealed), consistent with §6: escalation by fill and
count, never by a colour change.

## Wordmark

"Basalt" set in Inter 600, tracking -2%, sentence case, beside the bare mark
(mark height about 1.35 x cap height of the wordmark, gap about 0.4 x mark
width). No separate display face (DESIGN_SYSTEM.md §3).

## Where to apply it (for the implementing agent)

1. **Website** (`Website/index.html`): replace the header `.brand` inline
   shield SVG with the bare mark (light/dark via `prefers-color-scheme` or two
   `<symbol>`s, as the shield glyphs already do) and replace the `<link rel="icon">`
   data URI with `basalt-icon.svg` content. Also check `legal.html`,
   `support.html`, `success.html` and `changelog.html` headers.
2. **App icon files** (`DesktopApp/Assets/`): the current `FlowShield.svg`,
   `FlowShield.ico`, `FlowShield.Running.svg` and `FlowShield.Running.ico` are the old
   shield. Replace with the Causeway tiles. Regenerate the `.ico` files
   (`tools/build_icons.py`) at 16, 20, 24, 32, 40, 48, 64, 256. `Running` = the
   Firm variant unless the tray is extended to three levels (optional: soft/firm/sealed
   tray icons, the countdown icon in `MainWindow.xaml.cs` `CountdownIcon` is unaffected).
   Keep the file names and `.csproj` references unless you also update
   `MainWindow.xaml.cs` `LoadIcon` and the `.csproj` `ApplicationIcon`/`Resource` lines
   (the rename deliberately kept old names where installs depend on them).
3. **App title bar / nav**: wherever the shield mark is shown as a brand
   (not the shield *level* glyphs), use the bare mark or small tile.
4. **Installer** and any social / OG image: use `basalt-icon.svg`.
5. **DESIGN_SYSTEM.md** §5: replace "The FlowShield shield mark is the only
   filled brand icon" with the Causeway mark (it remains the only filled
   brand icon, identical everywhere). Leave §6 shield-level glyphs as they are.
6. Check the mark at 16 px and 24 px on light and dark taskbars; the three
   columns blur into a stepped silhouette with lighter tops at 16 px, which is
   expected and still reads.

## Not in scope

The shield-level glyphs (§6) stay shields. Do not add gradients, glows,
photographic rock or marble to the mark.
