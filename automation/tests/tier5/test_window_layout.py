# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: window layout."""

from __future__ import annotations
import re
from pathlib import Path
import pytest
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR



class TestSmallScreenLayout:
    """
    The window's minimum size was 900x620, which didn't fit on small laptops
    or split-screen layouts. The adaptive layout must collapse the nav rail to
    icons and move the stats rail below the timer at narrow widths.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_main_window_min_size_allows_small_screens(self):
        xaml = self.read("MainWindow.xaml")
        assert 'MinHeight="540"' in xaml, "MinHeight must be 540 to fit small screens"
        assert 'MinWidth="800"' in xaml, "MinWidth must be 800 to fit small screens"
        assert 'MinHeight="620"' not in xaml, "old MinHeight 620 must be replaced"
        assert 'MinWidth="900"' not in xaml, "old MinWidth 900 must be replaced"

    def test_today_view_has_adaptive_layout_elements(self):
        xaml = self.read("Views", "TodayView.xaml")
        assert 'x:Name="StatsRail"' in xaml, "stats rail must be named for adaptive layout"
        assert 'x:Name="StatsColumn"' in xaml, "stats column must be named for adaptive layout"
        assert 'x:Name="StatsRow"' in xaml, "stats row must be named for adaptive layout"
        assert 'x:Name="TimerCard"' in xaml, "timer card must be named for adaptive layout"

    def test_today_view_code_behind_handles_size_changes(self):
        cs = self.read("Views", "TodayView.xaml.cs")
        assert "OnSizeChanged" in cs, "TodayView must handle SizeChanged for adaptive layout"
        assert "StatsColumn" in cs and "StatsRail" in cs, \
            "TodayView must adjust stats column and rail position on size change"
        assert "Grid.SetRow" in cs or "SetRow" in cs, \
            "TodayView must move the stats rail between rows for narrow/wide layout"


    @pytest.mark.parametrize("view", ["MainWindow", "Views/TodayView"])
    def test_resizing_never_overwrites_a_visibility_binding(self, view):
        """
        The first draft set NavBuyButton.Visibility from OnSizeChanged. A local
        value replaces the element's {Binding IsNotPro} binding, so after one
        resize a paying customer saw "Buy Basalt" again. Code-behind may
        only toggle Visibility on elements whose Visibility isn't data-bound.
        """
        import re

        xaml = self.read(*f"{view}.xaml".split("/")).replace("\ufeff", "")
        cs = self.read(*f"{view}.xaml.cs".split("/"))

        toggled = set(re.findall(r"\b(\w+)\.Visibility\s*=", cs))
        if view == "MainWindow":
            assert toggled, "MainWindow.xaml.cs no longer toggles visibility; update this test"

        for name in toggled:
            start = xaml.find(f'x:Name="{name}"')
            assert start >= 0, f"{view}.xaml.cs toggles {name}, which isn't in the XAML"
            element = xaml[xaml.rfind("<", 0, start):xaml.find(">", start)]
            assert "Visibility=\"{Binding" not in element, \
                f"{name} has a Visibility binding that {view}.xaml.cs overwrites"

    def test_the_buy_button_keeps_its_paid_user_binding(self):
        xaml = self.read("MainWindow.xaml").replace("\ufeff", "")
        start = xaml.find('AutomationId="GetProNavButton"')
        element = xaml[xaml.rfind("<", 0, start):xaml.find(">", start)]
        assert "{Binding IsNotPro" in element


class TestBlockedAppsRowSwitchNotClipped:
    """
    PR #182 review (§4): the per-app enable/disable switch in the Blocked
    Apps list (Steam/Discord/Minecraft Launcher rows) was clipped by the
    card's right edge. The row's Grid has one flexible column (app name,
    MinWidth 120) and four Auto columns -- icon, "blocked N x" stat, Remove
    button, switch -- inside a ListBox with
    ScrollViewer.HorizontalScrollBarVisibility="Disabled", which clips
    overflow instead of scrolling it. This PR's own spacing bumps (icon
    margin 13->12, "blocked N" margin 14->16, Remove button padding
    14,0->16,0, switch margin 14,0,0,0->16,0,0,0) pushed the row's required
    width past the card's available width (roughly 480px once the 1180px
    window's 240px nav rail, 32px page margins, 300px picker column, 16px
    gap, 24px Card padding and 16px RowCard padding are all subtracted), so
    the switch -- the last Auto column -- lost its right edge.

    The review fix pulled the Remove button's own padding and the switch's
    own margin back down to 12 (still on the §4 4/8/12/16/24/32/48/64
    scale), reclaiming 12px. This test sums the four literal spacing values
    straight from the live XAML rather than reimplementing WPF's
    text-measurement and layout engine -- those four numbers are the whole
    cause the review named, and BUDGET is the same arithmetic used to find
    and fix it.
    """

    VIEW = Path(DESKTOP_DIR) / "Views" / "BlockedAppsView.xaml"

    # 76 (pre-fix: 12+16+32+16) overflowed the card; 64 (post-fix:
    # 12+16+24+12) fits with margin to spare. Drawn at 70 so a future bump
    # of any one value by a single further 4px §4 step trips it again.
    BUDGET = 70

    ICON_MARGIN = re.compile(
        r'Grid\.Column="0" Width="34" Height="34".*?Margin="0,0,(\d+),0">', re.DOTALL
    )
    STAT_MARGIN = re.compile(
        r'Grid\.Column="2" VerticalAlignment="Center" Margin="0,0,(\d+),0"\s*\n\s*'
        r'Style="\{StaticResource Caption\}">\s*\n\s*<Run Text="blocked"'
    )
    BUTTON_PADDING = re.compile(
        r'Style="\{StaticResource BtnDanger\}" Content="Remove"\s*\n\s*Padding="(\d+),0"'
    )
    SWITCH_MARGIN = re.compile(
        r'Style="\{StaticResource Switch\}"\s*\n\s*VerticalAlignment="Center" Margin="(\d+),0,0,0"'
    )

    # Verbatim pre-fix fragment (this PR's own shipped numbers, before the
    # review caught the clip): proves the checker below actually rejects
    # the failing set rather than passing by construction.
    PRE_FIX_FIXTURE = (
        '<Border Grid.Column="0" Width="34" Height="34" CornerRadius="{StaticResource RadiusControl}"\n'
        '        Background="{StaticResource PrimarySoft}" BorderBrush="{StaticResource Primary}" BorderThickness="1"\n'
        '        Margin="0,0,12,0">\n'
        '<TextBlock Grid.Column="2" VerticalAlignment="Center" Margin="0,0,16,0"\n'
        '           Style="{StaticResource Caption}">\n'
        '    <Run Text="blocked"/>\n'
        '<Button Grid.Column="3" Style="{StaticResource BtnDanger}" Content="Remove"\n'
        '        Padding="16,0" VerticalAlignment="Center"\n'
        '<CheckBox Grid.Column="4" Style="{StaticResource Switch}"\n'
        '          VerticalAlignment="Center" Margin="16,0,0,0"\n'
    )

    def _total(self, text: str) -> int:
        icon = self.ICON_MARGIN.search(text)
        stat = self.STAT_MARGIN.search(text)
        button = self.BUTTON_PADDING.search(text)
        switch = self.SWITCH_MARGIN.search(text)
        assert icon and stat and button and switch, (
            "one of the Blocked Apps row's spacing patterns wasn't found -- "
            "has the row's XAML structure changed? update this test's regexes to match."
        )
        return (
            int(icon.group(1))
            + int(stat.group(1))
            + int(button.group(1)) * 2
            + int(switch.group(1))
        )

    def test_fixture_of_known_pre_fix_values_is_rejected(self):
        """Proves the checker catches the bug: the pre-fix numbers
        (12+16+32+16=76) must exceed BUDGET."""
        total = self._total(self.PRE_FIX_FIXTURE)
        assert total > self.BUDGET, (
            f"expected the pre-fix fixture ({total}) to exceed BUDGET ({self.BUDGET})"
        )

    def test_blocked_apps_row_spacing_fits_the_card(self):
        text = self.VIEW.read_text(encoding="utf-8")
        total = self._total(text)
        assert total <= self.BUDGET, (
            f"Blocked Apps row spacing (icon margin + stat margin + 2x Remove "
            f"button padding + switch margin = {total}) exceeds the "
            f"{self.BUDGET}px budget that keeps the switch from being "
            "clipped by the card's right edge (PR #182 review) -- pull one "
            "of these back to the next lower §4 scale step."
        )


# ======================================== #189: the app adapts to its window

class TestAppAdaptsToItsWindow:
    """
    #189. Miles saw clipped nav icons, and two pages (Sleep Blocking,
    Settings) that sat in a narrow centred column instead of using the window.
    A render-kit sweep of main at six sizes, 1920x1040 down to the 800x540
    minimum, found the rest: fixed side columns on Today and Blocked Apps,
    breakpoints read from the window instead of the view, a picker that cut
    app names short at every size, and Blocked Apps clipping its Remove
    buttons below about 780px. DESIGN_SYSTEM.md §4 now records the rules;
    these tests hold them.
    """

    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"
    VIEWS = Path(DESKTOP_DIR) / "Views"

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8-sig")

    def _style(self, key: str, path: Path | None = None) -> str:
        xaml = self._read(path or self.THEME)
        start = xaml.index(f'x:Key="{key}"')
        return xaml[start:xaml.index("</Style>", start)]

    def test_nav_rows_leave_room_for_their_icons(self):
        """BtnBase fixes Height=40; NavButton added Padding 16,12, leaving a
        16px box for a 20px icon, which clipped it at the top and bottom."""
        nav = self._style("NavButton")
        height = float(re.search(r'Property="Height" Value="([\d.]+)"', nav).group(1))
        padding = re.search(r'Property="Padding" Value="([\d.,]+)"', nav).group(1).split(",")
        vertical = float(padding[1]) if len(padding) >= 2 else float(padding[0])
        icons = Path(DESKTOP_DIR) / "Styles" / "Icons.xaml"
        icon = float(re.search(r'Property="Height" Value="([\d.]+)"', self._style("Icon", icons)).group(1))
        assert height - 2 * vertical >= icon, (
            f"a nav row {height}px tall with {vertical}px vertical padding has "
            f"{height - 2 * vertical}px for a {icon}px icon")



    def test_breakpoints_read_the_space_the_view_has(self):
        """Keyed on the window, a view couldn't respond to its own width."""
        window_xaml = self._read(Path(DESKTOP_DIR) / "MainWindow.xaml")
        assert '<Grid x:Name="RootGrid" SizeChanged="OnSizeChanged">' in window_xaml
        assert 'SizeChanged="OnSizeChanged"\n' not in window_xaml.split("<Grid", 1)[0], (
            "the rail breakpoint belongs on the root grid, not the window")
        for code in ("TodayView.xaml.cs", "BlockedAppsView.xaml.cs"):
            source = (self.VIEWS / code).read_text(encoding="utf-8")
            assert "e.NewSize.Width" in source, f"{code} should read its own new width"
            assert "Window.GetWindow" not in source, f"{code} still reads the window's width"

    def test_blocked_apps_stacks_and_scrolls_when_narrow(self):
        """Side by side below ~780px, the list clipped its Remove buttons; split
        into fixed halves, a short window showed no rows at all."""
        blocked = self._read(self.VIEWS / "BlockedAppsView.xaml")
        assert '<ScrollViewer x:Name="PageScroll"' in blocked
        source = (self.VIEWS / "BlockedAppsView.xaml.cs").read_text(encoding="utf-8")
        assert "StackPickerBelow" in source
        assert "ScrollBarVisibility.Auto" in source and "ScrollBarVisibility.Disabled" in source

    def test_the_adaptive_panel_counts_columns_by_width(self):
        """The panel's column count: as many as keep each at MinColumnWidth,
        between one and MaxColumns, and one for an unusable width."""
        source = (Path(DESKTOP_DIR) / "Infrastructure" / "AdaptiveColumns.cs").read_text(encoding="utf-8")
        assert "Math.Floor((width + spacing) / (minColumnWidth + spacing))" in source
        assert "Math.Clamp(fit, 1, Math.Max(1, maxColumns))" in source
        assert "double.IsInfinity(width)" in source, "an infinite width must fall back to one column"

    def test_today_stat_values_share_their_labels_line_height(self):
        """The numbers used the default style while their labels used Body, so
        they sat higher than the labels beside them."""
        today = self._read(self.VIEWS / "TodayView.xaml")
        for binding in ("SessionsToday", "FocusMinutesToday", "BlocksToday"):
            tag = re.search(r'<TextBlock Text="\{Binding ' + binding + r'\}"[^>]*>', today, re.S).group(0)
            assert 'Style="{StaticResource Body}"' in tag, f"{binding} should use the Body style"


# ============================== the window opens inside the work area (#296)

class TestTheWindowFitsTheWorkArea296:
    """
    The main window asked for 1180 × 760 with CenterScreen and never checked
    the monitor, so on a 768 px-tall screen its title bar sat above the top
    and its bottom under the taskbar (VM bench, 1.0.9 RC). Start-up and every
    return from the tray now run FitToWorkArea, which goes through the pure
    WindowFit rule tier 1 mirrors.
    """

    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"

    def member(self, code: str, signature: str) -> str:
        parts = code.split(signature, 1)
        assert len(parts) == 2, f"{signature} not found in MainWindow.xaml.cs"
        return parts[1].split("\n    }")[0]

    def test_start_up_and_tray_restore_fit_the_window(self):
        code = self.WINDOW.read_text(encoding="utf-8")
        assert "FitToWorkArea();" in self.member(code, "protected override void OnSourceInitialized(EventArgs e)")
        restore = self.member(code, "private void RestoreFromTray()")
        assert "FitToWorkArea();" in restore
        assert restore.index("WindowState = WindowState.Normal;") < restore.index("FitToWorkArea();"), \
            "fit after restoring: a maximised or minimised window is skipped"

    def test_it_uses_the_monitors_work_area_not_the_whole_screen(self):
        fit = self.member(self.WINDOW.read_text(encoding="utf-8"), "private void FitToWorkArea()")
        assert "MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)" in fit
        assert "info.rcWork" in fit and "info.rcMonitor" not in fit
        assert "TransformFromDevice" in fit, "the work area is in device pixels; the window in DIPs"
        assert "WindowFit.Fit(current, workArea, MinWidth, MinHeight)" in fit


# ================================================ the Today declutter (#147)

class TestTodayDeclutter147:
    """
    The competitor gap analysis (2026-10-05) found Today stacked the timer,
    six length chips, three shields, a cycle row, an intention box and the
    momentum essay in one column, with Start sprint lost among them. Idle,
    Today is now the timer, the templates and Start; the pickers fold behind
    one summary line, and the momentum rule lives on History.
    """

    TODAY = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"
    HISTORY = Path(DESKTOP_DIR) / "Views" / "HistoryView.xaml"
    VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    PICKERS = ('AutomationId="SprintLength_15"', 'AutomationId="SprintLength_Custom"',
               'AutomationId="CustomMinutesInput"', 'AutomationId="Shield_Soft"',
               'AutomationId="Shield_Firm"', 'AutomationId="Shield_Sealed"',
               'AutomationId="ShieldDescriptionText"', 'AutomationId="Cycle_Off"',
               'AutomationId="Cycle_4"', 'AutomationId="CycleDescriptionText"',
               "StringFormat=TodayProfile_{0}")
    # Warnings about the shield in use, the blocklist's name, the intention
    # and Start itself: never folded.
    ALWAYS_SHOWN = ("SealedRestartHint", "SoftHardKillHint", "TodayProfileCaption",
                    "IntentionInput", "StartSprintButton")

    def _fold(self):
        xaml = self.TODAY.read_text(encoding="utf-8")
        opener = '<StackPanel Visibility="{Binding SprintOptionsVisible, Converter={StaticResource BoolVis}}">'
        assert xaml.count(opener) == 1, "one fold, bound to SprintOptionsVisible"
        start = xaml.index(opener)
        # The fold's own closing tag: count nested StackPanels, skipping self-closing ones.
        depth = 0
        for tag in re.finditer(r"<(/?)StackPanel\b[^>]*?(/?)>", xaml[start:]):
            if tag.group(2):
                continue
            depth += -1 if tag.group(1) else 1
            if depth == 0:
                return xaml, xaml[start:start + tag.end()]
        raise AssertionError("the fold never closes")


    def test_warnings_start_and_intention_remain_reachable_when_options_are_collapsed(self):
        xaml, fold = self._fold()
        for auto_id in self.ALWAYS_SHOWN:
            assert f'AutomationId="{auto_id}"' in xaml, auto_id
            assert f'AutomationId="{auto_id}"' not in fold, f"{auto_id} must not be folded away"


    def test_the_fold_starts_closed_and_never_hides_why_start_is_off(self):
        code = " ".join(self.VM.read_text(encoding="utf-8").split())
        assert "private bool _sprintOptionsOpen;" in code, "closed until Change"
        assert "SprintOptionsRowVisible && (_sprintOptionsOpen || CustomMinutesErrorVisible)" in code, \
            "an invalid custom length keeps the pickers, and its error, on screen"
        assert "public bool SprintOptionsRowVisible => !IsRunning && !IsOnBreak;" in code

    def test_the_summary_reads_what_start_reads(self):
        code = " ".join(self.VM.read_text(encoding="utf-8").split())
        assert ("SprintOptionsCopy.Summary( IsCustomSelected && !IsCustomMinutesValid ? 0 : SelectedMinutes, "
                "SelectedShield, CycleSprints)") in code
        for declaration in ("public ShieldLevel SelectedShield", "public int CycleSprints",
                            "public int SelectedMinutes"):
            body = code.split(declaration, 1)[1].split(" public ", 1)[0]
            assert "Raise(nameof(SprintOptionsSummary));" in body, f"{declaration} must refresh the line"


    def test_the_link_scrolls_the_rule_into_view(self):
        """
        VM bench on #330: at 1024x768 the opened rule sat below the week's
        figures and the heatmap, so the link looked dead. The request waits
        until History is showing, then scrolls after layout.
        """
        vm = " ".join((Path(DESKTOP_DIR) / "ViewModels" / "HistoryViewModel.cs").read_text(encoding="utf-8").split())
        view = " ".join((Path(DESKTOP_DIR) / "Views" / "HistoryView.xaml.cs").read_text(encoding="utf-8").split())
        show = vm.split("public void ShowExplainer()", 1)[1].split("}", 1)[0]
        assert "ExplainerVisible = true;" in show and "ExplainerScrollPending = true;" in show
        assert 'x:Name="MomentumCard"' in self.HISTORY.read_text(encoding="utf-8")
        assert "IsVisibleChanged += (_, _) => ScrollToExplainerIfAsked();" in view, "acts once History shows"
        scroll = view.split("private void ScrollToExplainerIfAsked()", 1)[1]
        assert "!IsVisible) return;" in scroll, "a collapsed page cannot scroll"
        assert "MomentumCard.BringIntoView()" in scroll and "DispatcherPriority.Loaded" in scroll

    def test_the_driver_opens_the_fold_only_for_todays_pickers(self):
        from desktop.app_controller import is_sprint_option
        for auto_id in ("SprintLength_25", "Shield_Firm", "Cycle_2", "CustomMinutesInput",
                        "ShieldDescriptionText", "TodayProfile_School"):
            assert is_sprint_option(auto_id), auto_id
        for auto_id in ("TemplateShield_Soft", "TemplateCycle_2", "FirstRunShield_Sealed",
                        "StartSprintButton", "SprintOptionsToggle", "IntentionInput"):
            assert not is_sprint_option(auto_id), auto_id


class TestTodayPolishFromThe1011VmRun:
    """
    #347 and #290: three findings from the 1.0.11 VM run, and Today's stats
    going stale overnight. Each test fails against 1.0.10's code.
    """

    VIEWS = Path(DESKTOP_DIR) / "Views"
    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"
    MAIN_VM = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    OVERLAY = Path(DESKTOP_DIR) / "Views" / "SoftOverlayWindow.xaml.cs"

    def _xaml_files(self):
        return sorted(self.VIEWS.glob("*.xaml")) + [Path(DESKTOP_DIR) / "MainWindow.xaml"]

    def test_no_shadowed_card_has_a_translucent_background(self):
        """
        The Card style's DropShadowEffect is drawn from the alpha of all the
        element's content, so a Card painted with the translucent PrimarySoft
        cast a blurred shadow from every line of text and both buttons of the
        heads-up card. A tinted card is CardTinted, which keeps the shadow on
        an opaque layer.
        """
        offenders = []
        for path in self._xaml_files():
            text = path.read_text(encoding="utf-8")
            for tag in re.findall(r"<Border\b[^>]*>", text, flags=re.S):
                if 'Style="{StaticResource Card}"' in tag and "PrimarySoft" in tag:
                    offenders.append(f"{path.name}: {' '.join(tag.split())[:120]}")
        assert not offenders, offenders

    def test_the_tinted_card_shadows_an_opaque_surface(self):
        theme = self.THEME.read_text(encoding="utf-8")
        style = theme.split('<Style x:Key="CardTinted"', 1)[1].split("</Style>", 1)[0]
        outer = style.split("<Border.Effect>", 1)[0]
        outer_tag = outer[outer.rindex("<Border "):]
        assert 'Background="{DynamicResource Surface}"' in outer_tag, \
            "the shadow must sit on the opaque surface, not on the tint"
        inner = style.split("</Border.Effect>", 1)[1]
        assert 'Background="{DynamicResource PrimarySoft}"' in inner
        heads_up = (self.VIEWS / "TodayView.xaml").read_text(encoding="utf-8")
        card = heads_up.split("HeadsUpVisible", 1)[0].rsplit("<", 1)[1]
        assert card.startswith('ContentControl Style="{StaticResource CardTinted}"'), card[:80]

    def test_the_website_notice_counts_its_minutes_down(self):
        """It showed the minutes left when it opened and never again (328-notice-youtube.png)."""
        handler = self.MAIN_VM.read_text(encoding="utf-8").split("private void OnSoftForeground", 1)[1]
        handler = handler.split("\n    }", 1)[0]
        assert "SoftOverlayCopy.TimeLeft(Today.Remaining)" not in handler, \
            "a string worked out once can't count down"
        assert "() => Today.Remaining" in handler
        overlay = self.OVERLAY.read_text(encoding="utf-8")
        configure = overlay.split("public void Configure(", 1)[1].split("\n    }", 1)[0]
        assert "Func<TimeSpan> remaining" in configure
        ticks = re.search(r"_timeLeftTimer\.Tick \+= .*SoftOverlayCopy\.TimeLeft\(remaining\(\)\)", configure)
        assert ticks, "a timer must re-read the time left while the notice is up"
        closed = overlay.split("protected override void OnClosed", 1)[1].split("\n    }", 1)[0]
        assert "_timeLeftTimer?.Stop();" in closed

    def test_the_blocked_apps_counter_is_not_zero_padded(self):
        xaml = (self.VIEWS / "BlockedAppsView.xaml").read_text(encoding="utf-8")
        assert "Apps.Count, StringFormat={}{0:00}" not in xaml, '"01 apps"'
        assert 'Text="apps on the shield"' not in xaml, "the label must agree with the count"
        assert "Converter={StaticResource AppsOnShieldLabel}" in xaml

    def test_todays_stats_move_to_the_new_day_while_left_open(self):
        """#290: idle on Today across midnight, nothing re-ran RefreshStats."""
        main = self.MAIN_VM.read_text(encoding="utf-8")
        assert re.search(r"Scheduler\.Ticked \+= \(_, now\) => Today\.RefreshStatsOnNewDay\(now\);", main)
        today = self.TODAY_VM.read_text(encoding="utf-8")
        on_new_day = today.split("public void RefreshStatsOnNewDay(DateTime nowUtc)", 1)[1].split("\n    }", 1)[0]
        assert "nowUtc.ToLocalTime().Date == _statsDay" in on_new_day, "the day is the local one"
        assert "RefreshStats();" in on_new_day
        refresh = today.split("public void RefreshStats()", 1)[1].split("\n    }", 1)[0]
        assert "_statsDay = today;" in refresh
