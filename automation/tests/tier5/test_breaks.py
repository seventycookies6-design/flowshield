# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: breaks."""

from __future__ import annotations
import re
from pathlib import Path
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR



# ============================== a break leaves the shield, and everything
# ============================== else, alone (F5)

class TestABreakStandsTheShieldDown:
    """
    F5's promise is that during a break blocked apps are allowed. The way that
    is kept is that nothing starts the blocker again: the sprint's end stops
    enforcing, and the break path never calls BeginEnforcing.

    Written as source tests because the alternative — a second "break mode" in
    AppBlockerService — is exactly what this must not become. A mode could be
    entered by mistake; no call at all cannot be.
    """

    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    BLOCKER = Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs"

    def vm(self) -> str:
        return self.TODAY_VM.read_text(encoding="utf-8")

    def break_region(self) -> str:
        source = self.vm()
        assert "breaks and cycles (F5)" in source, "the F5 code should be in one place"
        return source.split("breaks and cycles (F5)")[1].split("--------------- stats")[0]

    def test_ending_a_sprint_stops_enforcing_before_any_break_can_start(self):
        source = self.vm()
        end = source.split("private void EndSprint(bool completed, bool interrupted = false)")[1].split("\n    /// <summary>")[0]
        assert "_main.Blocker.StopEnforcing();" in end

    def test_nothing_in_the_break_path_starts_the_blocker(self):
        region = self.break_region()
        assert "BeginEnforcing" not in region, \
            "a break that enforces is not a break; the shield stays down for all of it"

    def test_the_blocker_gained_no_break_mode(self):
        blocker = self.BLOCKER.read_text(encoding="utf-8")
        for name in ("CycleState", "RunningBreak", "IsOnBreak", "BreakMode"):
            assert name not in blocker, \
                f"F5 uses the existing BeginEnforcing/StopEnforcing; {name} in the blocker is a second way to be wrong"

    def test_the_break_never_touches_momentum_the_streak_or_the_goal(self):
        region = self.break_region()
        for forbidden in ("MomentumScore", "ApplyMomentum", "CurrentStreak", "DailyGoal"):
            assert forbidden not in region, \
                f"a break must not reach {forbidden}; five minutes off is not progress and not a penalty"

    def test_only_a_completed_sprint_earns_a_break(self):
        source = self.vm()
        offer = source.split("private void OfferBreakIfEarned(bool completed)")[1].split("\n    }")[0]
        assert "CycleState.OffersBreak(completed)" in offer, \
            "ending early must not be rewarded with a break; the rule stays in the model"

    def test_a_break_starts_no_sprint_of_its_own_without_a_cycle(self):
        region = self.break_region()
        assert "StartsNextSprint" in region, \
            "only a cycle continues by itself; a single sprint's break ends quietly"


class TestNothingSellsOrLocksDuringABreak:
    """
    F20: the trial lock and anything about money wait for a sprint to end. A
    break is part of the same sitting — locking the app or offering to sell
    during the three minutes between two sprints breaks that promise just as
    surely, and until F5 the guard only knew about a running sprint.
    """

    MAIN_VM = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"

    def source(self) -> str:
        return self.MAIN_VM.read_text(encoding="utf-8")

    def test_focus_in_progress_includes_the_break(self):
        source = self.source()
        assert re.search(r"IsFocusInProgress\s*=>\s*Today\.IsRunning\s*\|\|\s*Today\.IsOnBreak", source), \
            "the guard must know a break is under way"

    def test_the_access_check_waits_for_the_break_too(self):
        source = self.source()
        refresh = source.split("public void RefreshAccess()")[1].split("\n    /// <summary>")[0]
        assert "IsFocusInProgress" in refresh, \
            "the lock screen must not appear between two sprints of a cycle"

    def test_a_notification_that_interrupts_focus_waits_for_the_break_too(self):
        source = self.source()
        notify = source.split("public bool Notify(")[1].split("\n    /// <summary>")[0]
        assert "NotificationPolicy.ShouldShow(kind, Settings, IsFocusInProgress)" in notify

    def test_the_break_over_notice_is_switchable_like_the_others(self):
        settings_vm = (Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs").read_text(encoding="utf-8")
        assert "NotificationKind.BreakOver" in settings_vm
        settings_xaml = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="NotifyBreakOverToggle"' in settings_xaml


class TestTheRingSaysWhichClockIsRunning:
    """
    DESIGN_SYSTEM §2: teal means state, selection or progress — through a
    sprint. A break drawn in the same teal arc would read as "the shield is up"
    at a glance, which is the one thing it is not (§7 timer ring).
    """

    XAML = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"

    def test_the_two_arcs_have_different_colours_and_never_show_together(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        assert 'Visibility="{Binding SprintRingVisible' in xaml
        assert 'Visibility="{Binding BreakRingVisible' in xaml
        # DynamicResource since F21: a colour reference has to re-resolve when
        # the light theme swaps the tokens dictionary under it.
        assert 'Stroke="{DynamicResource InkDim}" StrokeThickness="12"' in xaml, \
            "the break arc is text-muted, not primary"

    def test_the_view_model_keeps_them_exclusive(self):
        vm = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert re.search(r"SprintRingVisible\s*=>\s*!IsOnBreak", vm)
        assert re.search(r"BreakRingVisible\s*=>\s*IsOnBreak", vm)


class TestTheTrayFollowsTheBreak:
    """
    PR #230 review: during a break the tray still read "Start sprint (last
    settings)", which is the idle label. The break is not idle — the next thing
    is the next sprint, and that is what the row does.
    """

    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"

    def test_the_menu_names_the_next_sprint_during_a_break(self):
        build = self.WINDOW.read_text(encoding="utf-8").split(
            "private void BuildTrayMenu(")[1].split("\n    /// <summary>")[0]
        assert 'onBreak ? "Start next sprint" : "Start sprint (last settings)"' in build, \
            "the tray must say what it is about to do"
        assert "Vm?.Today.IsOnBreak == true" in build

    def test_it_is_still_the_same_start_command(self):
        """
        The label changed, not the action: starting a sprint cuts the break
        short through the same start flow as the Today button and Space use.
        """
        build = self.WINDOW.read_text(encoding="utf-8").split(
            "private void BuildTrayMenu(")[1].split("\n    /// <summary>")[0]
        assert "QuickStart()" in build
        assert "StartBreak" not in build, "the tray never reaches into the break itself"




class TestCycleTextFollowsTheSprintLength:
    """Choosing a sprint length after the cycle count left the cycle line
    saying the old length ("4 sprints of 90 minutes" with 25 min selected):
    SelectedMinutes never raised CycleDescription."""

    VM = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "TodayViewModel.cs"

    def test_changing_the_length_refreshes_the_cycle_line(self):
        source = self.VM.read_text(encoding="utf-8")
        start = source.index("public int SelectedMinutes")
        setter = source[start:source.index("\n    }\n", start)]
        assert "Raise(nameof(CycleDescription))" in setter

    def test_restoring_a_running_sprint_refreshes_it_too(self):
        source = self.VM.read_text(encoding="utf-8")
        restore = source.index("Raise(nameof(SelectedMinutes));\n                Raise(nameof(PresetMinutes));")
        assert "Raise(nameof(CycleDescription))" in source[restore:restore + 400]


class TestBreakCommandsRefreshCanExecute:
    """Break state changes must make WPF recheck the break commands."""

    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"

    def test_break_state_changes_refresh_the_commands(self):
        source = self.TODAY_VM.read_text(encoding="utf-8")
        methods = (
            ("private void BeginBreakClock(bool resumed)", 1,
             "Starting a break leaves its skip and continue buttons unavailable."),
            ("private void EndBreak(bool notify)", 2,
             "Ending a break leaves its skip and continue buttons in the wrong state."),
            ("private void OfferBreakIfEarned(bool completed)", 1,
             "Finishing a sprint leaves the new break buttons unavailable."),
        )
        for signature, expected_calls, customer_message in methods:
            body = source.split(signature, 1)[1].split("\n    }", 1)[0]
            assert body.count("CommandManager.InvalidateRequerySuggested();") == expected_calls, customer_message
