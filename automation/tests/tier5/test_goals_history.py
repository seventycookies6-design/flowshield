# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: goals history."""

from __future__ import annotations
import re
from pathlib import Path
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from ._helpers import DESKTOP



# ==================================================== daily goal guards (F15)

class TestDailyGoalRegressions:
    """
    F15 added a daily goal, and with it a streak that has to settle itself.

    Two things could quietly break: the streak for the people who never set a
    goal, and the bar appearing for them at all.
    """

    MODEL = DESKTOP_DIR / "Models" / "DailyGoal.cs"
    TODAY_VM = DESKTOP_DIR / "ViewModels" / "TodayViewModel.cs"
    TODAY_XAML = DESKTOP_DIR / "Views" / "TodayView.xaml"

    def test_the_streak_settles_somewhere_that_runs_without_a_sprint(self):
        """
        The bug this guards: the streak was only ever recalculated inside
        ApplyMomentum, which runs when a sprint completes. A missed day was
        therefore invisible until the next completed sprint — so a week off
        still showed the old streak. With a goal, that becomes wrong rather
        than merely stale, because a day can now fail by falling short.
        """
        vm = self.TODAY_VM.read_text(encoding="utf-8")
        refresh = vm.split("public void RefreshStats()", 1)
        assert len(refresh) == 2, "RefreshStats must still exist"
        assert "DailyGoal.Settle" in refresh[1][:900], \
            "RefreshStats must settle the streak: it is the path that runs on launch " \
            "and when the day rolls over, with no sprint to trigger it"

    def test_the_goal_bar_is_bound_to_visibility_not_just_emptied(self):
        """
        A goal-less user must not see an empty bar. Hiding it by blanking the
        text would leave the track and the padding behind.
        """
        xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        # Anchored on the progress text, which UI Automation can actually
        # resolve. The panel's own id was removed in #134: an id on a layout
        # panel is never surfaced, so it could not fail.
        panel = xaml.split('AutomationProperties.AutomationId="DailyGoalProgressText"', 1)
        assert len(panel) == 2, "the daily goal panel must be present"
        before = panel[0][-800:]
        assert "GoalVisible" in before and "BoolVis" in before, \
            "the panel itself must collapse when no goal is set"

    def test_a_skipped_day_cannot_be_turned_into_a_counted_one(self):
        """
        Judge checks the skip first. Reversing that order would let a stray
        two-minute sprint on a planned day off consume the weekly allowance
        and count the day, which is the opposite of what the user asked for.
        """
        model = self.MODEL.read_text(encoding="utf-8")
        judge = model.split("public static DayVerdict Judge", 1)
        assert len(judge) == 2, "Judge must exist"
        body = judge[1][:400]
        skip_at = body.find("IsSkipped")
        met_at = body.find("MetOn")
        assert skip_at != -1 and met_at != -1
        assert skip_at < met_at, "a skip must be judged before the goal is measured"

    def test_the_weekly_allowance_is_not_a_calendar_week(self):
        """
        A fixed week boundary allows two days off back to back — Sunday and
        Monday — from an allowance that reads as one per week.
        """
        model = self.MODEL.read_text(encoding="utf-8")
        used = model.split("public static int SkipsUsedInWindow", 1)
        assert len(used) == 2
        assert "AddDays(-(SkipWindowDays - 1))" in used[1][:400], \
            "the window must be measured back from the day, not from a week boundary"

    def test_settling_is_idempotent_in_source(self):
        """
        Settle runs on launch, on rollover and after every sprint. If it did not
        record where it got to, each call would re-walk the same days and count
        them again.
        """
        model = self.MODEL.read_text(encoding="utf-8")
        assert "StreakSettledDayLocal = date" in model, \
            "Settle must record the day it settled through"

    def test_today_is_never_judged_as_missed(self):
        """
        Today is still in progress. Breaking the streak at 9am because the goal
        is not met yet would be absurd.
        """
        model = self.MODEL.read_text(encoding="utf-8")
        settle = model.split("public static bool Settle", 1)
        assert len(settle) == 2
        assert "if (day == date)" in settle[1][:1600], \
            "the loop must treat today specially: it can add to the streak, never break it"


class TestStreakCountsADayItAlreadySettled:
    """
    #194. DailyGoal.Settle could only add today to the streak inside its walk
    loop, which runs while StreakSettledDayLocal < today -- and then writes
    StreakSettledDayLocal = today whether or not the day counted. RefreshStats
    settles today from the TodayViewModel constructor, i.e. at launch, before
    the day's first sprint exists, so every later call that day fell into the
    "date <= settled" branch whose only move was Max(CurrentStreak, 1). A user
    meeting their goal daily stayed on the streak they arrived with; a new user
    stuck at "1 day" forever.

    The fix routes all three paths through CountDayIfNewlyCounted, which uses
    the GoalMetDayLocal marker that already existed to make it once-per-day.
    """

    MODEL = DESKTOP / "Models" / "DailyGoal.cs"

    # The shipped same-day branch, verbatim: proves the checker below rejects it
    # rather than passing by construction.
    PRE_FIX_FIXTURE = (
        "        if (date <= settled)\n"
        "        {\n"
        "            if (date == settled && Judge(s, date) == DayVerdict.Counted)\n"
        "                s.CurrentStreak = Math.Max(s.CurrentStreak, 1);\n"
        "            return s.CurrentStreak != streakBefore;\n"
        "        }\n"
    )

    def _same_day_branch(self, source: str) -> str:
        match = re.search(r"if \(date <= settled\)\s*\{(.*?)\n        \}", source, re.S)
        assert match, "Settle's clock-moved-backwards branch was not found; update this regex"
        return match.group(1)

    def test_the_fixture_of_the_shipped_branch_is_rejected(self):
        branch = self._same_day_branch(self.PRE_FIX_FIXTURE)
        assert "CountDayIfNewlyCounted" not in branch
        assert "Math.Max(s.CurrentStreak, 1)" in branch, (
            "the pre-fix branch clamps to 1 instead of counting the day"
        )

    def test_a_day_already_settled_goes_through_the_once_per_day_marker(self):
        source = self.MODEL.read_text(encoding="utf-8")
        branch = self._same_day_branch(source)
        assert "CountDayIfNewlyCounted" in branch, (
            "meeting the goal on a day Settle has already visited must still count it"
        )
        assert "Math.Max(s.CurrentStreak, 1)" not in source, (
            "clamping to 1 is what pinned every existing streak in place"
        )

    def test_the_marker_is_the_one_that_already_existed(self):
        source = self.MODEL.read_text(encoding="utf-8")
        counter = source.split("private static bool CountDayIfNewlyCounted(", 1)
        assert len(counter) == 2, "DailyGoal must expose the once-per-day counter"
        body = counter[1].split("\n    }", 1)[0]
        assert "s.GoalMetDayLocal?.Date == date" in body, (
            "GoalMetDayLocal is the field that makes this once a day, not once a sprint"
        )
        assert "s.CurrentStreak++" in body

    def test_every_path_that_can_count_today_uses_it(self):
        source = self.MODEL.read_text(encoding="utf-8")
        # First run, the already-settled branch, and the walk loop's today.
        assert source.count("CountDayIfNewlyCounted(s,") >= 3, (
            "first run, a re-settled today and the walk loop must all count today "
            "the same way, or one of them goes back to being unable to"
        )

    def test_note_progress_reads_the_marker_rather_than_setting_it_again(self):
        source = self.MODEL.read_text(encoding="utf-8")
        note = source.split("public static bool NoteProgress(", 1)[1].split("\n    }", 1)[0]
        assert "metBefore" in note and "Settle(s, date)" in note, (
            "NoteProgress must read GoalMetDayLocal either side of Settle"
        )
        assert "s.GoalMetDayLocal = date" not in note, (
            "two places setting the marker is how the toast and the streak drift apart"
        )


class TestTheGoalSeesTheSprintThatJustFinished:
    """
    #199. EndSprint called ApplyMomentum -- and through it
    DailyGoal.NoteProgress, which counts S.Sessions -- before adding the
    finished sprint to S.Sessions. So the goal was always judged one sprint
    behind: with a two-sprint goal the bar on Today read "2 / 2" (RefreshStats
    runs after the add) while the "Daily goal met" toast waited for a third
    sprint that may never come. ResumeInterruptedSprint had the same order.
    """

    VM = DESKTOP / "ViewModels" / "TodayViewModel.cs"

    def _order(self, body: str) -> tuple[int, int]:
        add = body.find("Sessions.Add(")
        momentum = body.find("ApplyMomentum(")
        assert add >= 0 and momentum >= 0, (
            "expected both the Sessions.Add and the ApplyMomentum call; update this test"
        )
        return add, momentum

    def test_end_sprint_records_before_it_judges(self):
        source = self.VM.read_text(encoding="utf-8")
        body = source.split("private void EndSprint(bool completed, bool interrupted = false)", 1)[1].split("\n    }", 1)[0]
        add, momentum = self._order(body)
        assert add < momentum, (
            "S.Sessions.Add must come before ApplyMomentum, or the daily goal and "
            "the streak are judged without the sprint that just finished"
        )

    def test_a_sprint_that_finished_while_closed_is_recorded_before_it_is_judged(self):
        source = self.VM.read_text(encoding="utf-8")
        body = source.split("case SprintResume.RecordCompleted:", 1)[1].split("break;", 1)[0]
        add, momentum = self._order(body)
        assert add < momentum, (
            "the RecordCompleted branch must add the session before ApplyMomentum too"
        )

    def test_the_pre_fix_order_is_rejected(self):
        add, momentum = self._order(
            "        ApplyMomentum(completed, _current);\n"
            "        S.Sessions.Add(_current);\n"
        )
        assert add > momentum, "the shipped order judged the goal before recording the sprint"


class TestTheTrendLeavesAnInterruptedSprintAlone:
    """
    #195. MomentumTrend.After branched on Completed alone, so a sprint recorded
    as Interrupted -- Basalt was not running for most of it, nothing was
    enforced -- was charged the ended-early decay on replay. ApplyMomentum is
    never called for one, so the drawn line sank below the MomentumText printed
    beside it, and TrendDescription (the only thing a screen reader gets)
    described a shape that contradicted the number it quoted.
    """

    MODEL = DESKTOP / "Models" / "MomentumTrend.cs"
    VM = DESKTOP / "ViewModels" / "TodayViewModel.cs"

    def _after(self, source: str) -> str:
        body = source.split("private static double After(double score, FocusSession session)", 1)
        assert len(body) == 2, "MomentumTrend.After was not found; update this test"
        return body[1].split(";", 1)[0]

    def test_the_replay_carries_the_score_through_an_interrupted_sprint(self):
        after = self._after(self.MODEL.read_text(encoding="utf-8"))
        assert "session.Interrupted" in after, (
            "the replay must skip an interrupted sprint; Completed alone cannot "
            "tell 'gave up' from 'the app was not running'"
        )

    def test_the_pre_fix_body_is_rejected(self):
        after = self._after(
            "    private static double After(double score, FocusSession session) =>\n"
            "        session.Completed\n"
            "            ? Math.Round(score + 10 * Math.Clamp(session.PlannedMinutes / 25.0, 0.5, 3.0), 1)\n"
            "            : EndSprintPolicy.MomentumAfterEndingEarly(score, session.Shield);\n"
        )
        assert "session.Interrupted" not in after

    def test_the_live_score_still_never_moves_for_an_interrupted_sprint(self):
        """The rule the replay is being matched against."""
        vm = self.VM.read_text(encoding="utf-8")
        resume = vm.split("case SprintResume.RecordCompleted:", 1)[1].split("break;", 1)[0]
        assert "if (completed) ApplyMomentum" in resume, (
            "momentum is applied only when the sprint counts as finished"
        )


# ================================= History is wired up and stays read-only (F16)

class TestHistoryPage:
    """
    F16 adds a fifth page, and three things about it are easy to break without
    noticing by eye.

    The nav entry: a page with a view model and no way to reach it is invisible
    (the tab is one Button among five, and #191's compact rail hides its label
    at narrow widths, so the rail's code must know about the new label).

    The AutomationIds: an id on a Border, Grid or ItemsControl is never
    surfaced to UI Automation, so a test asking for it passes whether the
    content was drawn or not (#134) — which is how the whole page could quietly
    stop rendering with every tier 3 test still green.

    And what it reads: the page is a projection of the sprints already on disk.
    If it ever starts writing settings, or reads the licence, the device list or
    anything that leaves the machine, the local-first promise and the privacy
    policy both stop being true.
    """

    DESKTOP = Path(DESKTOP_DIR)
    XAML = DESKTOP / "Views" / "HistoryView.xaml"
    VM = DESKTOP / "ViewModels" / "HistoryViewModel.cs"
    MAIN_XAML = DESKTOP / "MainWindow.xaml"
    MAIN_VM = DESKTOP / "ViewModels" / "MainViewModel.cs"
    MAIN_CODE = DESKTOP / "MainWindow.xaml.cs"
    MODEL = DESKTOP / "Models" / "HistoryStats.cs"

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8-sig")

    # ------------------------------------------------------------ the nav entry

    def test_the_nav_rail_has_a_history_tab(self):
        xaml = self._read(self.MAIN_XAML)
        assert 'AutomationProperties.AutomationId="Tab_History"' in xaml
        assert 'CommandParameter="History"' in xaml
        assert 'AutomationProperties.Name="History"' in xaml, \
            "the compact rail shows the name as a tooltip, so it has to exist"
        assert "{StaticResource IconHistory}" in xaml, \
            "the tab needs a Lucide geometry, like the other four"

    def test_the_tab_follows_the_same_pattern_as_the_other_four(self):
        xaml = self._read(self.MAIN_XAML)
        tabs = xaml.split('<StackPanel x:Name="NavTabs"', 1)[1].split("<Grid/>", 1)[0]
        ids = re.findall(r'AutomationProperties.AutomationId="(Tab_\w+)"', tabs)
        assert ids == ["Tab_Today", "Tab_History", "Tab_BlockedApps",
                       "Tab_SleepBlocking", "Tab_Settings"], \
            f"the rail's tabs are {ids}"
        for tab in tabs.split("<Button")[1:]:
            assert 'Style="{StaticResource NavButton}"' in tab, \
                "every tab uses NavButton, which is the 44px row (#191)"
            assert 'Tag="{Binding Is' in tab, "the active state binds through Tag"

    def test_the_compact_rail_hides_the_history_label_too(self):
        """
        Every other label is collapsed by name below 1000px. A label left out
        of that list stays visible in a 72px rail and overflows it.
        """
        code = self.MAIN_CODE.read_text(encoding="utf-8")
        labels = set(re.findall(r'(Nav\w+Label)\.Visibility = narrow', code))
        xaml = self._read(self.MAIN_XAML)
        declared = set(re.findall(r'<TextBlock x:Name="(Nav\w+Label)"', xaml))
        assert declared == labels, \
            f"these labels are never collapsed in the compact rail: {sorted(declared - labels)}"

    def test_navigation_reaches_the_page_and_refreshes_it(self):
        vm = self.MAIN_VM.read_text(encoding="utf-8")
        assert "AppPage.History" in vm
        assert "public bool IsHistoryPage" in vm
        assert "Raise(nameof(IsHistoryPage));" in vm, \
            "without this the page never becomes visible"
        assert "case AppPage.History: History.Refresh(); break;" in vm, \
            "sprints happen on another page, so History must refresh on entry"

        window = self._read(self.MAIN_XAML)
        assert "<views:HistoryView DataContext=\"{Binding History}\"" in window
        assert "DataContext.IsHistoryPage" in window

    # --------------------------------------------------- ids on real controls

    def test_every_automation_id_sits_on_a_control(self):
        xaml = self._read(self.XAML)
        for tag in ("<Grid", "<StackPanel", "<Border", "<ItemsControl",
                    "<UniformGrid", "<ScrollViewer", "<inf:AdaptiveColumns"):
            for element in xaml.split(tag)[1:]:
                head = element.split(">", 1)[0]
                assert "AutomationProperties.AutomationId" not in head, \
                    f"an AutomationId is on a {tag[1:]}, where nothing can find it"

    def test_the_week_stat_values_are_not_hidden_behind_a_name_override(self):
        """
        A TextBlock has no ValuePattern, so UI Automation surfaces its content
        through the element's Name — which is exactly what
        AutomationProperties.Name overrides. Setting an explicit Name on
        these three (as History briefly did) makes automation, and a screen
        reader, read the eyebrow label instead of the number: "Sprints
        completed this week" instead of "12". Regression for #222.
        """
        xaml = self._read(self.XAML)
        for automation_id in ("WeekFocusHours", "WeekSprintsValue", "WeekDistractionsValue"):
            block = xaml.split(f'AutomationProperties.AutomationId="{automation_id}"', 1)[1][:400]
            assert "AutomationProperties.Name" not in block.split("/>", 1)[0], \
                f"{automation_id} has a Name override hiding its bound value from automation"

    def test_the_page_offers_the_handles_a_test_needs(self):
        xaml = self._read(self.XAML)
        for automation_id in (
            "WeekFocusHours", "WeekRangeText", "WeekSprintsValue",
            "WeekDistractionsValue", "MostBlockedApp", "MostBlockedNote",
            "FocusHeatmap", "HeatmapLegend", "HeatmapRange", "HeatmapPeak",
            "MilestonesEmptyText", "HistoryExportButton",
            "HistoryRowHeading", "HistoryRowOutcome", "HistoryRowJournal",
            "HistoryEmptyText",
        ):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml, \
                f"{automation_id} is missing from History"

    def test_the_heatmap_cells_are_focusable_controls_that_say_their_value(self):
        """
        DESIGN_SYSTEM.md §7: a heatmap never relies on colour alone, and
        hovering or focusing a cell shows the value. A Border does neither — it
        takes no focus and UI Automation does not surface it.
        """
        theme = self._read(self.DESKTOP / "Styles" / "Theme.xaml")
        style = theme[theme.index('x:Key="HeatCellItem"'):]
        style = style[:style.index("</Style>")]
        assert 'TargetType="ListBoxItem"' in style, "a cell has to be a real control"
        assert 'Property="AutomationProperties.Name" Value="{Binding Name}"' in style
        assert 'Property="ToolTip" Value="{Binding Name}"' in style
        assert 'Property="IsKeyboardFocused" Value="True"' in style, \
            "a focused cell has to show that it is focused"

        vm = self.VM.read_text(encoding="utf-8")
        assert "focus minutes" in vm, "a cell's name states its own value"

    def test_the_heatmap_has_an_accessible_legend(self):
        xaml = self._read(self.XAML)
        legend = re.search(
            r'<ListBox\b(?=[^>]*ItemsSource="\{Binding LegendSteps\}")'
            r'(?=[^>]*AutomationProperties\.Name="([^"]+)")[^>]*>', xaml, re.S)
        assert legend, "the heatmap legend needs an accessible description"
        description = legend.group(1).lower()
        assert "no focus" in description and "busiest day" in description, (
            "the legend must explain what its low and high levels mean")
        assert re.search(r'ItemsSource="\{Binding [^}]+\}"', legend.group(0)), (
            "the legend must describe each available heatmap level")

        converter = (self.DESKTOP / "Infrastructure" / "Converters.cs").read_text(encoding="utf-8")
        body = converter.split("class HeatStepToBrushConverter", 1)[1]
        assert '"Surface2Color"' in body and '"PrimaryColor"' in body, \
            "the ramp is mixed from the generated tokens, not hand-picked colours"
        hard_coded = re.findall(r'#[0-9A-Fa-f]{6}', body)
        assert not hard_coded, f"a colour is hard-coded in the converter: {hard_coded}"

    # ------------------------------------------------- what the page reads

    def test_history_reads_the_sprints_and_never_writes(self):
        """
        Read-only by construction. A page that saved settings could lose a
        running sprint's record just by being looked at, and the weekly figures
        would stop being a projection of what is stored.
        """
        vm = self.VM.read_text(encoding="utf-8")
        for forbidden in ("SaveSettings", "SettingsService.Save", "S.Sessions.Add",
                          "S.Sessions.Remove", "S.Sessions.Clear", "HttpClient",
                          "File.", "Process.Start"):
            assert forbidden not in vm, f"History must only read; it calls {forbidden}"

    def test_the_figures_come_from_sessions_alone(self):
        """
        Everything counted on this page is derived from AppSettings.Sessions
        through HistoryStats. The one exception is named out loud: the
        most-blocked app is the per-entry count Basalt already keeps on the
        blocklist, because a sprint records how many distractions it caught and
        never which app they were — and the card says so rather than implying
        the count is this week's.
        """
        model = self.MODEL.read_text(encoding="utf-8")
        week = model.split("public static Week ForWeek", 1)[1].split("\n    }", 1)[0]
        heatmap = model.split("public static IReadOnlyList<Cell> Heatmap", 1)[1] \
                       .split("\n    }", 1)[0]
        for name, block in (("ForWeek", week), ("Heatmap", heatmap)):
            assert "sessions" in block, f"{name} should read the sessions it is handed"
            for forbidden in ("BlockedApps", "MomentumScore", "CurrentStreak",
                              "LicenseKey", "DeviceCount", "BlocksToday"):
                assert forbidden not in block, \
                    f"{name} reads {forbidden}; the week's figures come from Sessions"

        vm = self.VM.read_text(encoding="utf-8")
        touched = set(re.findall(r'\bS\.(\w+)', vm))
        # Profiles joined the list with F9: the most-blocked count is summed
        # across every profile, so the card's answer does not change when the
        # active blocklist does. EarnedMilestones (F14) is listed, not derived:
        # the History list shows each milestone once, with the day it was earned.
        assert touched <= {"Sessions", "BlockedApps", "Profiles", "EarnedMilestones"}, \
            f"History reads more of the settings than it should: {sorted(touched)}"
        assert "MostBlockedNoteText" in vm, \
            "the most-blocked card must state that its count is not this week's"

    def test_the_page_stays_local(self):
        """Nothing new leaves the PC, which is why F16 needs no privacy change."""
        for path in (self.VM, self.MODEL):
            text = path.read_text(encoding="utf-8")
            for forbidden in ("http://", "https://", "Upload", "PostAsync", "WebClient"):
                assert forbidden not in text, f"{path.name} mentions {forbidden}"

        # The view's only URLs are the two XAML namespace declarations.
        urls = re.findall(r'https?://\S+', self._read(self.XAML))
        assert all("schemas.microsoft.com" in url for url in urls), \
            f"History links out to {urls}"

    # --------------------------------------------------------- design and voice

    def test_the_page_uses_the_type_roles_and_the_radius_resources(self):
        xaml = self._read(self.XAML)
        for style in ("Eyebrow", "Stat", "Caption", "Body"):
            assert f'Style="{{StaticResource {style}}}"' in xaml, f"§3's {style} role is unused"
        assert 'Style="{StaticResource Card}"' in xaml
        assert not re.search(r'CornerRadius="\d', xaml), \
            "§4: radii come from the named resources, never a literal"

        # The heatmap's own squares are shaped in Theme.xaml, so check there too.
        theme = self._read(self.DESKTOP / "Styles" / "Theme.xaml")
        for key in ("HeatCellItem", "HeatLegendItem"):
            style = theme[theme.index(f'x:Key="{key}"'):]
            style = style[:style.index("</Style>")]
            assert 'CornerRadius="{StaticResource RadiusChip}"' in style, \
                f"{key} should use §4's chip radius"
        assert 'Typography.NumeralAlignment="Tabular"' in xaml, "§3: stats use tabular figures"
        assert "<inf:AdaptiveColumns" in xaml, \
            "the week's cards flow into columns rather than a fixed row (#191)"

    def test_the_outcome_wording_is_the_one_the_export_already_uses(self):
        """
        §9: "ended early", never "failed" or "gave up" — and one spelling, so
        the page and the exported file cannot drift apart.
        """
        vm = self.VM.read_text(encoding="utf-8")
        assert "JournalExport.Outcome(session)" in vm
        assert "JournalExport.ShieldName(session.Shield)" in vm

        # Only the strings the customer reads: no comments (which quote §9's
        # banned words in order to forbid them) and no code around them.
        lines = [line for line in vm.splitlines()
                 if not line.lstrip().startswith(("//", "///", "*"))]
        copy = " ".join(re.findall(r'"([^"\n]{4,})"', "\n".join(lines))).lower()
        # An interpolated {session.PlannedMinutes} is code, not words on screen.
        copy = re.sub(r"\{[^}]*\}", " ", copy)
        for forbidden in ("failed", "gave up", "broke your streak", "session",
                          "pomodoro", "blacklist", "!"):
            assert forbidden not in copy, f"§9 forbids {forbidden!r} in product copy"
        assert "sprint" in copy, "§9: sprints, not sessions"

    def test_a_poor_week_is_never_drawn_in_red(self):
        """§7 and §9: never `danger` for a momentum or focus drop."""
        xaml = self._read(self.XAML)
        for token in ("Rose", "Red", "Danger"):
            assert f"StaticResource {token}" not in xaml, \
                f"History colours something with {token}"

    def test_the_shield_glyph_is_the_shared_resource(self):
        xaml = self._read(self.XAML)
        assert "{StaticResource ShieldGlyph}" in xaml, \
            "§6: one glyph resource, not a per-page copy"

    def test_the_milestones_are_listed_here_with_their_ids(self):
        """F14's quiet milestones are listed on History, each with its name,
        sentence and date, and the empty line says what to expect."""
        xaml = self._read(self.XAML)
        assert "MILESTONES" in xaml
        assert "{Binding MilestoneRows}" in xaml
        assert 'AutomationProperties.AutomationId="MilestoneTitle"' in xaml
        assert 'AutomationProperties.AutomationId="MilestonesEmptyText"' in xaml

    def test_journal_export_controls_keep_ids_and_remain_reachable(self):
        """
        F17's export card is still on Settings, with every AutomationId it
        shipped; History is a second way to it.
        """
        settings = self._read(self.DESKTOP / "Views" / "SettingsView.xaml")
        for automation_id in ("ExportFromDate", "ExportToDate", "ExportCsvRadio",
                              "ExportMarkdownRadio", "ExportJournalButton"):
            control = re.search(
                r'<(?:Button|DatePicker|RadioButton)\b(?=[^>]*AutomationProperties\.AutomationId="'
                + re.escape(automation_id) + r'")[^>]*>', settings, re.S)
            assert control, f"{automation_id} must remain on a real export control"
            assert 'IsTabStop="False"' not in control.group(0), (
                f"{automation_id} must remain keyboard reachable")
        for automation_id in ("ExportRangeText", "ExportStatusText"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in settings, \
                f"{automation_id} disappeared from the export status"

        xaml = self._read(self.XAML)
        button = re.search(
            r'<Button\b(?=[^>]*AutomationProperties\.AutomationId="HistoryExportButton")[^>]*>',
            xaml, re.S)
        assert button and 'IsTabStop="False"' not in button.group(0), (
            "History export must be a keyboard-reachable button")

        vm = self.VM.read_text(encoding="utf-8")
        assert "AppPage.Settings" in vm, "the button has to go somewhere"

    def test_the_sprint_list_reads_the_journal_back(self):
        """F17 promised the journal could be read again; F16 is where it is."""
        xaml = self._read(self.XAML)
        assert 'AutomationProperties.AutomationId="HistoryRowJournal"' in xaml
        assert 'AutomationProperties.AutomationId="HistoryRowIntention"' in xaml
        vm = self.VM.read_text(encoding="utf-8")
        assert "OrderByDescending(s => s.StartedUtc)" in vm, "newest first"
