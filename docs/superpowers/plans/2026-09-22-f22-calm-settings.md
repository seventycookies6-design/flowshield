# F22 — Clear, Calm Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Orchestration:** Opus orchestrates and reviews; each task goes to a fresh **Sonnet** implementer (`model: "sonnet"`) and a fresh Sonnet spec/quality reviewer. Opus runs the final whole-branch review. Tasks are strictly sequential (all touch `SettingsView.xaml`), so never run two implementers at once.

**Goal:** Turn Settings from ~11 unordered cards in a masonry grid into six labelled groups with a section rail, so it reads calm instead of "tab overload" (F22 / Roadmap 4.2, issue #38 item 1).

**Architecture:** One `ScrollViewer` stays; inside it, six `SettingsGroup` blocks (header + its own `inf:AdaptiveColumns`) replace the single flat `AdaptiveColumns`. A left rail of six radio-style links calls `BringIntoView` on a group; a scroll listener highlights the group in view. Nothing is hidden or moved to another page, so every existing `AutomationId` stays realized and reachable — no UI-test rewrites.

**Tech Stack:** .NET 8 WPF (C#/XAML), pytest source-level tests (tier 1/5) + pywinauto UI tests (tier 3).

**Spec:** `LAUNCH_FEATURE_CHECKLIST.md` → "F22 — Clear, calm Settings"; `DESIGN_SYSTEM.md` §4 (layout), §5 (icons), §13 (accessibility); issue #38.

## Global Constraints

- Keep every existing `AutomationProperties.AutomationId` in `SettingsView.xaml` exactly as-is (CLAUDE.md: "Keep existing `AutomationId`s").
- Colours only via `DynamicResource` tokens; new colours go in `design/tokens.json` + `python tools/build_tokens.py`, never hand-edited `Tokens.xaml`.
- Settings-like pages flow cards with `inf:AdaptiveColumns` (MinColumnWidth 400, MaxColumns 3, gaps in `Spacing`, not card margins).
- Inter, the §3 type scale, existing `Eyebrow`/`H2`/`Body`/`Caption` styles only. Lucide icons via the existing icon mechanism used by the main nav (#151).
- Must work in light and dark themes and at 800×540 (1.13 Fit small screens).
- Keyboard: every rail link reachable by Tab, activates with Enter/Space, has an accessible name.
- Don't edit text files with PowerShell `Get-Content`/`Set-Content`.
- Commits end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` (implementers) — branch `feat/f22-calm-settings` from `origin/main`, one PR closing a new F22 issue. Never merge; the owner's session merges.
- **This laptop has Smart App Control on: the built app cannot launch here.** Implementers run `dotnet build -c Release` and the fast tests only. UI (tier 3) tests are written but run by Miles after SAC is off, or on Keenan's machine — say so in the PR.

## Groups (the design, decided)

| # | Group header | `AutomationId` | Cards, in order (existing cards moved, not rewritten) |
|---|---|---|---|
| 1 | Licence & devices | `SettingsGroup_Licence` | Licence card (includes devices) |
| 2 | Focus | `SettingsGroup_Focus` | Daily goal; Breaks; **new** "Shields" card holding `SoftOverlayToggle` and `HardKillModeToggle` rows lifted out of Preferences |
| 3 | App | `SettingsGroup_App` | Preferences (now: Start with Windows, Minimise to tray, Global hotkey); Appearance |
| 4 | Notifications | `SettingsGroup_Notifications` | Notifications card |
| 5 | Your data | `SettingsGroup_Data` | Export your journal; Your data |
| 6 | About | `SettingsGroup_About` | Updates; Advanced |

Rail link ids: `SettingsNav_Licence`, `SettingsNav_Focus`, `SettingsNav_App`, `SettingsNav_Notifications`, `SettingsNav_Data`, `SettingsNav_About`.

## Review Focus

1. Window at 800×540 — rail must not squeeze cards below 400px: below 900px window width the rail collapses to a horizontal wrapping chip row above the groups.
2. Light theme — the active rail link must be distinguishable without colour alone (weight + left bar), §13 "colour-only signal".
3. Keyboard-only user — Tab reaches the rail, Enter jumps, focus lands on the group header (not lost at top).
4. Clicking the last group (About) when it's shorter than the viewport — highlight must still switch to About (bottom-of-scroll rule).
5. Sealed/active sprint states that disable controls (e.g. `DeleteEverythingBlockedText`, profile lock) still show correctly after cards move groups.

---

### Task 1: Group the cards into six sections

**Files:**
- Modify: `DesktopApp/Views/SettingsView.xaml` (whole file restructure; cards moved verbatim)
- Modify: `DesktopApp/Styles/` — add `SettingsGroupHeader` style to the file where `Eyebrow`/`H2` are defined (find with `grep -rn 'x:Key="Eyebrow"' DesktopApp/Styles`)
- Test: `automation/tests/test_tier1_unit.py` (new class at end)

**Interfaces:**
- Produces: six `StackPanel`s with `x:Name="Group_Licence"` … `Group_About` and `AutomationProperties.AutomationId="SettingsGroup_*"` (names per table). Task 2 calls `BringIntoView` on these names.

- [ ] **Step 1: Write the failing test** — append to `test_tier1_unit.py`:

```python
class TestSettingsIsGrouped:
    """F22: Settings is six labelled groups in a fixed order, and moving
    cards into them lost no control."""

    XAML = Path(SERVER_DIR).parent / "DesktopApp" / "Views" / "SettingsView.xaml"
    GROUPS = ["Licence", "Focus", "App", "Notifications", "Data", "About"]
    # every id the suite relies on; must survive the move
    KEPT_IDS = ["LicenseKeyInput", "ActivateProButton", "DevicesList",
                "StartWithWindowsToggle", "MinimizeToTrayToggle", "SoftOverlayToggle",
                "HardKillModeToggle", "GlobalHotkeyToggle", "ThemeSystemRadio",
                "GoalOffRadio", "ShortBreakMinutesInput", "ExportJournalButton",
                "NotificationsToggle", "NotifyTrialEndingToggle", "ExportDataButton",
                "DeleteEverythingButton", "VersionText", "CheckForUpdatesButton",
                "OpenLogButton", "ShowFirstRunButton"]

    def test_groups_exist_in_order(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        positions = [xaml.find(f'AutomationProperties.AutomationId="SettingsGroup_{g}"')
                     for g in self.GROUPS]
        assert all(p >= 0 for p in positions), positions
        assert positions == sorted(positions), "groups out of order"

    def test_every_existing_id_survives(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        for aid in self.KEPT_IDS:
            assert xaml.count(f'AutomationProperties.AutomationId="{aid}"') == 1, aid

    def test_shield_toggles_live_in_focus(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        focus = xaml.index('SettingsGroup_Focus"')
        app = xaml.index('SettingsGroup_App"')
        for aid in ("SoftOverlayToggle", "HardKillModeToggle"):
            assert focus < xaml.index(f'"{aid}"') < app, f"{aid} belongs in Focus"
```

- [ ] **Step 2: Run to verify it fails**
Run: `python -m pytest automation/tests/test_tier1_unit.py::TestSettingsIsGrouped -q`
Expected: FAIL (`positions` contains -1).

- [ ] **Step 3: Implement.** Add the style:

```xml
<Style x:Key="SettingsGroupHeader" TargetType="TextBlock" BasedOn="{StaticResource H2}">
    <Setter Property="Margin" Value="0,32,0,12"/>
    <Setter Property="Focusable" Value="True"/>
</Style>
```

Restructure `SettingsView.xaml` so the `ScrollViewer` (give it `x:Name="SettingsScroll"`) holds `<StackPanel x:Name="GroupsPanel" Margin="0,0,8,0">`, containing per group:

```xml
<StackPanel x:Name="Group_Focus"
            AutomationProperties.AutomationId="SettingsGroup_Focus"
            AutomationProperties.Name="Focus">
    <TextBlock x:Name="Header_Focus" Text="Focus" Style="{StaticResource SettingsGroupHeader}"/>
    <inf:AdaptiveColumns MinColumnWidth="400" MaxColumns="3" Spacing="16">
        <!-- Daily goal card (moved verbatim) -->
        <!-- Breaks card (moved verbatim) -->
        <!-- Shields card: new Card border with Eyebrow "SHIELDS" and the
             SoftOverlayToggle and HardKillModeToggle rows cut from Preferences,
             each with its existing hint text, separated by the same 1px Edge divider -->
    </inf:AdaptiveColumns>
</StackPanel>
```

The first group's header uses `Margin="0,0,0,12"` (override locally). Delete the Preferences rows you moved (and the divider above each) so each id appears once. Keep all comments that explain existing controls (#134 etc.) with their control.

- [ ] **Step 4: Verify** — `python -m pytest automation/tests/test_tier1_unit.py::TestSettingsIsGrouped -q` PASS; `cd DesktopApp && dotnet build -c Release` 0 errors; full fast suite `python -m pytest automation/tests -m "not ui and not stripe" -q` — no new failures (baseline ~1053 passed). If an older source test asserts a card's position/neighbours, update only its locating logic, not what it asserts.

- [ ] **Step 5: Commit** `git commit -am "F22: group Settings into six labelled sections"`

---

### Task 2: Section rail that jumps and follows scroll

**Files:**
- Modify: `DesktopApp/Views/SettingsView.xaml` (wrap in a 2-column `Grid`: rail `Width="180"` + scroll)
- Modify: `DesktopApp/Views/SettingsView.xaml.cs`
- Test: `automation/tests/test_tier1_unit.py` (extend `TestSettingsIsGrouped`), `automation/tests/test_tier3_e2e.py` (new UI test)

**Interfaces:**
- Consumes: `Group_*`, `Header_*`, `SettingsScroll`, `GroupsPanel` from Task 1.
- Produces: `SettingsNav_*` RadioButtons (GroupName `SettingsNav`), style `SettingsNavLink`; code-behind `JumpTo(string group)`.

- [ ] **Step 1: Failing tests.** Tier 1 (add methods to `TestSettingsIsGrouped`):

```python
    def test_rail_has_a_link_per_group(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        for g in self.GROUPS:
            assert f'AutomationProperties.AutomationId="SettingsNav_{g}"' in xaml
            assert f'Tag="{g}"' in xaml

    def test_rail_jump_focuses_the_header(self):
        cs = (self.XAML.parent / "SettingsView.xaml.cs").read_text(encoding="utf-8")
        assert "BringIntoView" in cs and ".Focus()" in cs
        assert "ScrollChanged" in cs, "rail must follow scrolling"
```

Tier 3 (in `test_tier3_e2e.py`, follow the fixture/marker pattern of the neighbouring Settings tests — `grep -n "navigate_to_tab(\"Settings\")" automation/tests/test_tier3_e2e.py`):

```python
@pytest.mark.ui
class TestSettingsRail:
    def test_about_link_scrolls_updates_into_view(self, app):
        app.navigate_to_tab("Settings")
        app.click("SettingsNav_About")
        assert app.is_on_screen("CheckForUpdatesButton")
        assert app.is_selected("SettingsNav_About")
```

If `is_on_screen`/`is_selected` don't exist on the controller (`automation/desktop/app_controller.py`), add them: `is_on_screen` = element's `rectangle()` intersects the main window's rectangle and `is_offscreen` is False; `is_selected` = `SelectionItemPattern.IsSelected` via `element.is_selected()`.

- [ ] **Step 2: Run tier 1** — FAIL. (Tier 3 can't run on SAC machines; mark in PR.)

- [ ] **Step 3: Implement.** Rail XAML (column 0):

```xml
<StackPanel x:Name="Rail" Grid.Column="0" Margin="0,0,16,0"
            AutomationProperties.Name="Settings sections">
    <RadioButton Style="{StaticResource SettingsNavLink}" GroupName="SettingsNav" Tag="Licence"
                 Content="Licence &amp; devices" IsChecked="True"
                 AutomationProperties.AutomationId="SettingsNav_Licence" Click="OnNavClick"/>
    <!-- same for Focus, App, Notifications, Data ("Your data"), About -->
</StackPanel>
```

`SettingsNavLink` style (same Styles file): template = `Border` with 3px left bar (`BorderThickness="3,0,0,0"`, `BorderBrush` transparent → `{DynamicResource Accent}` when checked), padding `12,8`; text `InkDim` → `Ink` + `SemiBold` when checked; hover background `{DynamicResource Surface2}` (use whichever hover token the main nav style uses — copy its trigger). Focus visual = existing app focus style.

Code-behind:

```csharp
private static readonly string[] Groups = { "Licence", "Focus", "App", "Notifications", "Data", "About" };
private bool _jumping;

private void OnNavClick(object sender, RoutedEventArgs e)
{
    if (sender is FrameworkElement { Tag: string g }) JumpTo(g);
}

public void JumpTo(string group)
{
    if (FindName("Group_" + group) is not FrameworkElement target) return;
    _jumping = true;
    var y = target.TransformToAncestor(GroupsPanel).Transform(new Point(0, 0)).Y;
    SettingsScroll.ScrollToVerticalOffset(y);
    (FindName("Header_" + group) as UIElement)?.Focus();
    Dispatcher.BeginInvoke(() => _jumping = false, DispatcherPriority.Background);
}

private void OnScrollChanged(object sender, ScrollChangedEventArgs e)
{
    if (_jumping) return;
    string current = Groups[0];
    if (SettingsScroll.VerticalOffset >= SettingsScroll.ScrollableHeight - 1)
        current = Groups[^1];            // bottom reached: last group wins (Review Focus 4)
    else
        foreach (var g in Groups)
        {
            var el = (FrameworkElement)FindName("Group_" + g);
            var top = el.TransformToAncestor(GroupsPanel).Transform(new Point(0, 0)).Y;
            if (top <= SettingsScroll.VerticalOffset + 24) current = g;
        }
    if (FindName("SettingsNav_" + current) is RadioButton rb) rb.IsChecked = true;
}
```

Wire `ScrollChanged="OnScrollChanged"` on `SettingsScroll`; set `x:Name="SettingsNav_Licence"` etc. on the RadioButtons so `FindName` works. Note `JumpTo` uses `ScrollToVerticalOffset` (not `BringIntoView`) for exact top alignment — keep a `BringIntoView` call only as a fallback if `TransformToAncestor` throws `InvalidOperationException` (not yet in tree), so the tier 1 assertion on `BringIntoView` stays meaningful.

- [ ] **Step 4: Verify** tier 1 PASS, build 0 errors/0 warnings, fast suite green.
- [ ] **Step 5: Commit** `"F22: section rail for Settings that jumps and follows scroll"`

---

### Task 3: Narrow windows — rail becomes a chip row

**Files:**
- Modify: `DesktopApp/Views/SettingsView.xaml`, `SettingsView.xaml.cs`
- Test: `automation/tests/test_tier1_unit.py`

**Interfaces:** Consumes `Rail` and the `SettingsNav_*` buttons; produces `const double RailBreakpoint = 900;`.

- [ ] **Step 1: Failing test**

```python
    def test_rail_collapses_on_narrow_windows(self):
        cs = (self.XAML.parent / "SettingsView.xaml.cs").read_text(encoding="utf-8")
        assert "RailBreakpoint = 900" in cs
        assert "SizeChanged" in cs
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Make `Rail` a `WrapPanel` (Orientation Vertical by default). On `SizeChanged` of the UserControl: if `ActualWidth < RailBreakpoint`, move `Rail` to `Grid.Row=0, Grid.Column=0, Grid.ColumnSpan=2`, `Orientation=Horizontal`, `Margin="0,0,0,12"`, set rail column width to 0 and scroll to Row 1; otherwise restore. In horizontal mode the `SettingsNavLink` left bar becomes a bottom bar — implement via a `DataTrigger` on the parent `WrapPanel.Orientation` switching `BorderThickness` to `0,0,0,2`.
- [ ] **Step 4: Verify** tier 1 PASS, build clean, fast suite green.
- [ ] **Step 5: Commit** `"F22: Settings rail collapses to a chip row on narrow windows"`

---

### Task 4: Docs, copy, and tracker truth

**Files:**
- Modify: `LAUNCH_FEATURE_CHECKLIST.md` (F22 `- [x] Done (#<PR>)`, both "Who builds what" rows), `DESIGN_SYSTEM.md` §4 (one bullet: "Settings is six labelled groups with a section rail; below 900px the rail becomes a chip row"), `Website/changelog.html` Unreleased section (one line: "Settings is grouped into six sections you can jump between."), `HANDOFF_PROMPT.md` if it lists F22 as open.
- Test: existing doc/changelog tier 5 tests.

- [ ] **Step 1:** Make the edits above; do not claim anything not built (CLAUDE.md rule).
- [ ] **Step 2:** `python -m pytest automation/tests -m "not ui and not stripe" -q` — green.
- [ ] **Step 3: Commit** `"F22: record calm Settings in the checklist, design system and changelog"`
- [ ] **Step 4 (orchestrator):** push branch, open PR "F22: clear, calm Settings" closing the F22 issue, template filled; Checks section states UI tests not run locally because Smart App Control blocks the dev build; request before/after captures at 1920×1040 and 800×540 from whoever runs the UI suite. Do not merge.

---

### Task 5: Site — the "5–7 PM" example box matches the other boxes

Miles's request (22 Sep review): on the landing page, the hero's worked example ("Turn your 5–7 PM into a protected homework block…") is a square-cornered box with only a 3px left bar, so it looks unfinished next to the SmartScreen note directly above it. Give it the same shape as `.smartscreen-note`. Independent of Tasks 1–4.

**Files:**
- Modify: `Website/styles.css:609-617` (the `.hero .example` rule)
- Test: `automation/tests/test_tier5_regressions.py` (new class at end; reuse the `_rule(selector)` helper pattern from the class around line 3337)

- [ ] **Step 1: Failing test**

```python
class TestHeroExampleMatchesTheOtherBoxes:
    """The 5–7 PM example shares the SmartScreen note's border and corners."""

    CSS = Path(SERVER_DIR).parent / "Website" / "styles.css"

    def _rule(self, selector):
        css = self.CSS.read_text(encoding="utf-8")
        start = css.index(selector + " {")
        return css[start:css.index("}", start)]

    def test_rounded_like_the_smartscreen_note(self):
        rule = self._rule(".hero .example")
        assert "border-radius: var(--radius-sm)" in rule
        assert "border: 1px solid var(--color-border)" in rule
        assert "border-left: 3px" not in rule
```

- [ ] **Step 2: Run** `python -m pytest automation/tests/test_tier5_regressions.py::TestHeroExampleMatchesTheOtherBoxes -q` — FAIL.
- [ ] **Step 3: Implement** — replace the `border-left` line in `.hero .example` with:

```css
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
```

Keep the padding, background and colour. Check the existing test at line ~3337 (`"solid var(--color-primary)" not in …`) still passes.
- [ ] **Step 4: Verify** the new test and the full fast suite pass; open `http://localhost:5500/` (`cd Website && python -m http.server 5500`) and screenshot the hero in dark and light themes and at 390px width, and attach them to the PR.
- [ ] **Step 5: Commit** `"Site: round the hero's 5–7 PM example like the other boxes"`
