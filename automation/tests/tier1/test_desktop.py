# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 1: desktop."""

from __future__ import annotations
import json
import re
from pathlib import Path
import pytest
from config import SERVER_DIR
from ._helpers import fit_window



# ======================================= tray and keyboard start a sprint (F4)

class TestSpaceShortcutSource:
    """
    Space on Today must start or end a sprint like the buttons do, but never
    while a text box (the intention field, the sealed phrase, the custom
    length) has focus — otherwise typing a space anywhere also toggled the
    sprint underneath the user.
    """

    TODAY_VM = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "TodayViewModel.cs"
    MAIN_XAML = Path(SERVER_DIR).parent / "DesktopApp" / "MainWindow.xaml"

    def source(self) -> str:
        return self.TODAY_VM.read_text(encoding="utf-8")

    def test_space_is_ignored_with_focus_in_a_text_box(self):
        source = self.source()
        guard = source.split("private bool CanUseSpaceShortcut()")[1].split("\n\n")[0]
        assert "Keyboard.FocusedElement is not TextBox" in guard, \
            "the Space shortcut must refuse while a text box has focus"

    def test_space_only_fires_on_today(self):
        source = self.source()
        guard = source.split("private bool CanUseSpaceShortcut()")[1].split("\n\n")[0]
        assert "AppPage.Today" in guard

    def test_space_reuses_the_same_toggle_as_the_buttons(self):
        source = self.source()
        assert "ToggleOrEndCommand = new RelayCommand(TogglePrimary, CanUseSpaceShortcut)" in source
        # TogglePrimary is exactly what StartSprintButton/StopSprintButton drive
        # (RequestEnd while running, StartSprint otherwise) — not a shortcut
        # around either.
        toggle = source.split("public void TogglePrimary()")[1].split("\n    }")[0]
        assert "RequestEnd()" in toggle and "StartSprint()" in toggle

    def test_the_window_binds_space_and_shift_shields_not_a_global_hook(self):
        xaml = self.MAIN_XAML.read_text(encoding="utf-8")
        assert '<KeyBinding Key="Space" Command="{Binding Today.ToggleOrEndCommand}"/>' in xaml
        for n in (1, 2, 3):
            assert f'Modifiers="Shift" Key="D{n}"' in xaml
        # Ctrl+1..5 is reserved for page navigation (issue #37, one slot per
        # nav-rail tab since F16 added History); Shift must never collide with it.
        for n in (1, 2, 3, 4, 5):
            assert f'Modifiers="Ctrl" Key="D{n}"' in xaml
        assert "RegisterWindowsHookEx" not in xaml
        assert "SetWindowsHookEx" not in (Path(SERVER_DIR).parent / "DesktopApp" / "MainWindow.xaml.cs").read_text(
            encoding="utf-8"), "keyboard shortcuts must be WPF KeyBindings, not a global hook"


class TestGlobalHotkeySource:
    """The optional Ctrl+Alt+F hotkey (F4): off by default, per-user, no admin rights."""

    SETTINGS = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"
    WINDOW = Path(SERVER_DIR).parent / "DesktopApp" / "MainWindow.xaml.cs"
    SETTINGS_VM = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "SettingsViewModel.cs"
    SETTINGS_XAML = Path(SERVER_DIR).parent / "DesktopApp" / "Views" / "SettingsView.xaml"

    def test_the_setting_defaults_to_off(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        field = source.split("public bool GlobalHotkeyEnabled")[1].split("\n")[0]
        assert "= true" not in field, "the global hotkey must be off until the user turns it on"

    def test_registration_uses_registerhotkey_not_admin_rights(self):
        window = self.WINDOW.read_text(encoding="utf-8")
        assert 'DllImport("user32.dll"' in window
        assert "RegisterHotKey(" in window
        assert "UnregisterHotKey(" in window
        assert "runas" not in window.lower()

    def test_a_taken_combination_turns_the_setting_back_off(self):
        window = self.WINDOW.read_text(encoding="utf-8")
        setup = window.split("private void SetUpGlobalHotkey()")[1].split("\n    private ")[0]
        assert "if (RegisterHotKey(" in setup
        failure = setup.split("else")[1]
        assert "GlobalHotkeyEnabled = false" in failure
        assert "vm.Toast(" in failure, "a taken hotkey must tell the user, not fail silently"

    def test_the_hotkey_is_unregistered_on_close(self):
        window = self.WINDOW.read_text(encoding="utf-8")
        closing = window.split("protected override void OnClosing")[1]
        assert "UnregisterHotKey(" in closing

    def test_the_setting_persists_through_the_normal_settings_pipeline(self):
        vm = self.SETTINGS_VM.read_text(encoding="utf-8")
        assert "public bool GlobalHotkeyEnabled" in vm
        assert "_main.SaveSettings();" in vm.split("public bool GlobalHotkeyEnabled")[1].split("}\n    }")[0]

        xaml = self.SETTINGS_XAML.read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="GlobalHotkeyToggle"' in xaml
        assert "{Binding GlobalHotkeyEnabled}" in xaml


class TestTrayMenuSource:
    """
    The tray menu (F4): start with last settings, start via the window, and —
    while running — the time left plus an End sprint that goes through the F2
    flow rather than ending the sprint directly.
    """

    WINDOW = Path(SERVER_DIR).parent / "DesktopApp" / "MainWindow.xaml.cs"

    def source(self) -> str:
        return self.WINDOW.read_text(encoding="utf-8")

    def test_the_menu_is_rebuilt_before_it_opens(self):
        source = self.source()
        assert "menu.Opening += (_, _) => BuildTrayMenu(menu);" in source

    def test_idle_offers_last_settings_and_start(self):
        source = self.source()
        build = source.split("private void BuildTrayMenu(")[1].split("\n    private ")[0]
        assert '"Start sprint (last settings)"' in build
        # Since #270 the item goes through QuickStart(), which executes
        # StartCommand and brings F7's open-apps question forward if it appears.
        assert "QuickStart()" in build
        assert '"Start…"' in build

    def test_running_shows_time_left_and_end_sprint(self):
        source = self.source()
        build = source.split("private void BuildTrayMenu(")[1].split("\n    private ")[0]
        assert "RemainingText" in build
        assert "Enabled = false" in build, "the time-left row must not be clickable"
        assert '"End sprint"' in build
        assert "EndSprintFromTray()" in build

    def test_end_sprint_from_tray_goes_through_the_f2_flow(self):
        source = self.source()
        end = source.split("private void EndSprintFromTray()")[1].split("\n    }")[0]
        assert "BringToFront()" in end
        assert "vm.Today.StopCommand.Execute(null)" in end, \
            "the tray must trigger the same StopCommand as the Today button, not end the sprint directly"
        assert "EndSprint(" not in end


# ============================ every token pair meets WCAG AA (F21, DESIGN_SYSTEM.md §2)

class TestTokenContrast:
    """
    DESIGN_SYSTEM.md §2 "Contrast" lists the pairs that matter and the ratio
    each one measured at; §13 asks that all of them meet WCAG AA. Normal text
    needs 4.5:1.

    The light theme is no longer decoration: F21 lets a customer run the app in
    it, so both themes are measured here, from design/tokens.json, in the same
    arithmetic WCAG 2.1 defines. Changing a colour in the JSON without checking
    what it lands on now fails this test rather than shipping.
    """

    ROOT = Path(SERVER_DIR).parent
    MINIMUM = 4.5

    #: (foreground token, background token) — exactly §2's "Contrast" table.
    PAIRS = (
        ("text", "bg"),
        ("text-muted", "bg"),
        ("text-faint", "surface"),
        ("primary", "bg"),
        ("primary-ink", "primary"),
        ("warn", "bg"),
        ("ok", "bg"),
        ("danger", "bg"),
    )

    def tokens(self) -> dict:
        return json.loads((self.ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))

    @staticmethod
    def _resolve(theme: dict, name: str) -> tuple[str, float]:
        """A token as (hex, alpha). A {"ref": …} token follows what it points at."""
        value = theme[name]
        if isinstance(value, str):
            return value, 1.0
        base, alpha = TestTokenContrast._resolve(theme, value["ref"])
        return base, alpha * float(value.get("alpha", 1.0))

    @staticmethod
    def _channels(hex_colour: str) -> tuple[int, int, int]:
        digits = hex_colour.lstrip("#")
        assert len(digits) == 6, f"expected #RRGGBB, got {hex_colour!r}"
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

    @staticmethod
    def _relative_luminance(rgb: tuple[int, int, int]) -> float:
        """WCAG 2.1 relative luminance."""
        def linear(channel: int) -> float:
            value = channel / 255
            return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        red, green, blue = (linear(c) for c in rgb)
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    @classmethod
    def ratio(cls, foreground: str, background: str) -> float:
        light = cls._relative_luminance(cls._channels(foreground))
        dark = cls._relative_luminance(cls._channels(background))
        brighter, dimmer = max(light, dark), min(light, dark)
        return (brighter + 0.05) / (dimmer + 0.05)

    def test_the_maths_matches_the_published_examples(self):
        """A sanity check on the formula itself: black on white is 21:1."""
        assert self.ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
        assert self.ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0, abs=0.01)
        assert self.ratio("#767676", "#FFFFFF") == pytest.approx(4.54, abs=0.01)

    @pytest.mark.parametrize("theme_name", ("dark", "light"))
    def test_every_documented_pair_passes_AA(self, theme_name):
        theme = self.tokens()["themes"][theme_name]
        failures = []
        for foreground, background in self.PAIRS:
            fg, fg_alpha = self._resolve(theme, foreground)
            bg, bg_alpha = self._resolve(theme, background)
            # Every pair in §2 is between two opaque tokens; a translucent one
            # would need the colour underneath it to mean anything.
            assert fg_alpha == 1.0 and bg_alpha == 1.0,                 f"{foreground} on {background} is not an opaque pair any more"
            measured = self.ratio(fg, bg)
            if measured < self.MINIMUM:
                failures.append(f"{theme_name}: {foreground} on {background} is "
                                f"{measured:.2f}:1, below {self.MINIMUM}:1")
        assert not failures, "; ".join(failures)

    def test_the_light_theme_carries_the_corrected_values(self):
        """
        The corrected light values are what make warn, ok, danger and
        text-faint pass above (text-faint is the stone grey from #336).
        Regressing any of them to the pre-#180 value would put the light
        theme back under AA.
        """
        theme = self.tokens()["themes"]["light"]
        assert theme["text-faint"] == "#606266"
        assert theme["ok"] == "#276A3E"
        assert theme["warn"] == "#7A5413"
        assert theme["danger"] == "#A3334A"


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

    def test_cards_sit_in_the_bound_groups(self):
        """Binding Groups table: App = Preferences, Appearance.
        About = Updates, then Advanced."""
        xaml = self.XAML.read_text(encoding="utf-8")
        app = xaml.index('SettingsGroup_App"')
        notifications = xaml.index('SettingsGroup_Notifications"')
        about = xaml.index('SettingsGroup_About"')

        assert app < xaml.index('"ThemeSystemRadio"') < notifications, \
            "Appearance (ThemeSystemRadio) belongs in App"

        for aid in ("OpenLogButton", "ShowFirstRunButton"):
            assert xaml.index(f'"{aid}"') > about, \
                f"Advanced ({aid}) belongs in About, after Updates"

    def test_rail_has_a_link_per_group(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        for g in self.GROUPS:
            assert f'AutomationProperties.AutomationId="SettingsNav_{g}"' in xaml
            assert f'Tag="{g}"' in xaml

    def test_rail_jump_focuses_the_header(self):
        cs = (self.XAML.parent / "SettingsView.xaml.cs").read_text(encoding="utf-8")
        assert "BringIntoView" in cs and ".Focus()" in cs
        assert "ScrollChanged" in cs, "rail must follow scrolling"

    def test_rail_links_activate_with_enter(self):
        """WPF RadioButtons don't reliably fire Click on Enter, only Space --
        the code-behind must handle Key.Enter itself so every rail link
        activates with either key (constraints.md keyboard requirement)."""
        cs = (self.XAML.parent / "SettingsView.xaml.cs").read_text(encoding="utf-8")
        assert "Key.Enter" in cs

    def test_rail_collapses_on_narrow_windows(self):
        cs = (self.XAML.parent / "SettingsView.xaml.cs").read_text(encoding="utf-8")
        assert "RailBreakpoint = 900" in cs
        assert "SizeChanged" in cs

    def test_settings_scroll_and_rail_get_rowspan(self):
        """CRITICAL: at wide widths, Rail and SettingsScroll both sit in the
        Auto row (row 0) with no RowSpan, so SettingsScroll gets unlimited
        height and Settings can't scroll at 900px or wider. The code-behind
        must call Grid.SetRowSpan for both, in both layouts."""
        cs = (self.XAML.parent / "SettingsView.xaml.cs").read_text(encoding="utf-8")
        assert "Grid.SetRowSpan(SettingsScroll" in cs
        assert "Grid.SetRowSpan(Rail" in cs


class TestTimerRingDrains:
    """The sprint and break rings count down, so they drain from full rather
    than fill, and glide between the once-a-second ticks unless Windows'
    animation effects are off (DESIGN_SYSTEM.md §7)."""

    ROOT = Path(SERVER_DIR).parent / "DesktopApp" / "Views"

    def xaml(self):
        return (self.ROOT / "TodayView.xaml").read_text(encoding="utf-8")

    def code(self):
        return (self.ROOT / "TodayView.xaml.cs").read_text(encoding="utf-8")

    def test_both_rings_draw_the_time_left(self):
        xaml = self.xaml()
        assert xaml.count("Path=RingRemaining, ElementName=Root, Converter={StaticResource ProgressDash}") == 2
        assert "Binding Progress, Converter={StaticResource ProgressDash}" not in xaml

    def test_the_ring_value_is_the_fraction_left(self):
        assert "1 - progress" in self.code()

    def test_it_glides_only_when_animation_effects_are_on(self):
        code = self.code()
        assert "Motion.AnimationsEnabled" in code
        assert "new DoubleAnimation" in code and "TimeSpan.FromSeconds(1)" in code

    def test_an_empty_ring_paints_no_dot(self):
        xaml = self.xaml()
        assert xaml.count("Path=RingRemaining, ElementName=Root, Converter={StaticResource PositiveVis}") == 2


class TestWindowFitsTheWorkArea:
    """
    #296: on a 768 px-tall screen the 1180 × 760 window opened with its title
    bar above the screen and its bottom under the taskbar. Start-up and
    restoring from the tray now fit it inside the work area of its monitor.
    """

    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Infrastructure" / "WindowFit.cs"
    XAML = Path(SERVER_DIR).parent / "DesktopApp" / "MainWindow.xaml"
    MIN = (800, 540)

    def requested(self):
        xaml = self.XAML.read_text(encoding="utf-8-sig")
        size = re.search(r'Height="(\d+)" Width="(\d+)"', xaml)
        minimum = re.search(r'MinHeight="(\d+)" MinWidth="(\d+)"', xaml)
        assert size and minimum, "MainWindow.xaml no longer sets its size this way; update this test"
        assert (int(minimum.group(2)), int(minimum.group(1))) == self.MIN
        return int(size.group(2)), int(size.group(1))

    def centred(self, screen_w, screen_h):
        """Where CenterScreen puts the window: against the whole screen, as the VM saw."""
        w, h = self.requested()
        return ((screen_w - w) / 2, (screen_h - h) / 2, w, h)

    @pytest.mark.parametrize("screen,work", [
        ((1366, 768), (0, 0, 1366, 728)),   # the most common laptop screen, 40 px taskbar
        ((1024, 768), (0, 0, 1024, 728)),   # the VM bench (#296)
        ((1280, 720), (0, 0, 1280, 672)),
        ((1920, 1080), (0, 0, 1920, 1040)),
    ])
    def test_the_whole_window_lands_inside_the_work_area(self, screen, work):
        left, top, w, h = fit_window(self.centred(*screen), work, *self.MIN)
        wl, wt, ww, wh = work
        assert left >= wl and top >= wt, "the title bar must be on-screen"
        assert left + w <= wl + ww and top + h <= wt + wh, "nothing may run off the side or under the taskbar"

    def test_a_screen_that_has_room_is_left_alone(self):
        window = self.centred(1920, 1080)
        assert fit_window(window, (0, 0, 1920, 1040), *self.MIN) == window

    def test_1024_by_768_fills_the_work_area_exactly(self):
        # The VM saw [-78, -20, 966, 740]; now it starts at the corner.
        assert fit_window(self.centred(1024, 768), (0, 0, 1024, 728), *self.MIN) == (0, 0, 1024, 728)

    def test_never_below_the_minimum_and_the_title_bar_wins(self):
        # A 800 × 600 screen with a 48 px taskbar: shrinks to its 552 px.
        assert fit_window((-50, -30, 1180, 760), (0, 0, 800, 552), *self.MIN) == (0, 0, 800, 552)
        # Smaller than the minimum: the top-left corner stays on-screen.
        assert fit_window((0, 0, 1180, 760), (0, 0, 640, 432), *self.MIN) == (0, 0, 800, 540)

    def test_a_second_monitor_keeps_its_offset(self):
        # Work area of a monitor to the right of the primary one.
        assert fit_window((1500, 100, 1180, 760), (1366, 0, 1366, 728), *self.MIN) == (1500, 0, 1180, 728)

    def test_the_mirror_matches_the_app(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "Math.Max(minWidth, Math.Min(window.Width, workArea.Width))" in source
        assert "Math.Max(minHeight, Math.Min(window.Height, workArea.Height))" in source
        assert "Math.Max(workArea.Left, Math.Min(window.Left, workArea.Right - width))" in source
        assert "Math.Max(workArea.Top, Math.Min(window.Top, workArea.Bottom - height))" in source
