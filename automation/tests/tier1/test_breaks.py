# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 1: breaks."""

from __future__ import annotations
import re
from pathlib import Path
import pytest
from config import SERVER_DIR
from ._helpers import BREAK_COPY_CASES, BREAK_COPY_MODEL, Cycle, Today, break_caption, break_minutes, break_panel_text, cycle_source, decide_break



class TestBreakLength:
    """F5: five minutes, and fifteen after every fourth completed sprint in a row."""

    def test_the_source_picks_the_long_break_on_every_fourth(self):
        """The mirror below is only worth anything if it matches this line."""
        source = cycle_source()
        assert "public const int LongBreakEvery = 4;" in source
        picker = source.split("public static int BreakMinutes(")[1].split(";")[0]
        assert "completedInARow > 0 && completedInARow % LongBreakEvery == 0" in picker, picker
        assert "? longMinutes : shortMinutes" in picker, picker
        assert "public const int DefaultShortBreakMinutes = 5;" in source
        assert "public const int DefaultLongBreakMinutes = 15;" in source

    def test_the_usual_break_is_the_short_one(self):
        assert break_minutes(1, 5, 15) == 5
        assert break_minutes(3, 5, 15) == 5

    def test_the_fourth_sprint_in_a_row_earns_the_long_break(self):
        assert break_minutes(4, 5, 15) == 15

    def test_and_every_fourth_after_that(self):
        assert break_minutes(8, 5, 15) == 15
        assert break_minutes(12, 5, 15) == 15
        assert break_minutes(9, 5, 15) == 5

    def test_a_run_of_none_earns_nothing_long(self):
        assert break_minutes(0, 5, 15) == 5, "zero % 4 is zero; that must not read as a fourth sprint"

    def test_both_lengths_come_from_settings(self):
        assert break_minutes(1, 3, 30) == 3
        assert break_minutes(4, 3, 30) == 30


class TestBreakIsOfferedOnlyForAFinishedSprint:
    """F5: ending early is F2's business; a break for it would pay for stopping."""

    def test_the_source_offers_a_break_for_a_completed_sprint_and_nothing_else(self):
        source = cycle_source()
        assert "public static bool OffersBreak(bool completed) => completed;" in source, \
            "the rule must be exactly 'completed', not a condition that can drift"
        # And the view model asks the model rather than deciding for itself.
        vm = (Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "TodayViewModel.cs").read_text(
            encoding="utf-8")
        assert "CycleState.OffersBreak(completed)" in vm

    def test_a_completed_sprint_offers_one(self):
        t = Today()
        t.end_sprint(completed=True)
        assert t.offer_visible

    def test_a_sprint_ended_early_offers_nothing(self):
        t = Today()
        t.end_sprint(completed=False)
        assert not t.offer_visible
        assert not t.on_break

    def test_ending_early_clears_the_run_towards_a_long_break(self):
        t = Today()
        for _ in range(3):
            t.start_sprint()
            t.end_sprint(completed=True)
            t.skip_break()
        t.start_sprint()
        t.end_sprint(completed=False)
        assert t.in_a_row == 0, "three finished then one abandoned is not four in a row"


class TestBreaksChangeNothingElse:
    """F5: momentum, the streak and the daily goal never hear about a break."""

    def test_starting_and_ending_a_break_moves_nothing(self):
        t = Today()
        t.start_sprint()
        t.end_sprint(completed=True)
        before = (t.momentum, t.goal_days)
        t.start_break()
        t.break_ran_out()
        assert (t.momentum, t.goal_days) == before

    def test_skipping_a_break_costs_nothing(self):
        t = Today()
        t.start_sprint()
        t.end_sprint(completed=True)
        before = (t.momentum, t.goal_days)
        t.skip_break()
        assert (t.momentum, t.goal_days) == before

    def test_nothing_is_enforced_while_a_break_runs(self):
        t = Today()
        t.start_sprint()
        assert t.enforcing
        t.end_sprint(completed=True)
        t.start_break()
        assert not t.enforcing, "the shield is down for the whole break"


class TestCycles:
    """F5: "3 × 45" runs sprint → break → sprint by itself."""

    def test_the_source_transitions_match_the_mirror(self):
        source = cycle_source()
        assert "public bool InCycle => SprintsPlanned > 1;" in source
        assert "public bool CycleFinished => InCycle && SprintsDone >= SprintsPlanned;" in source
        assert "public bool StartsNextSprint => InCycle && SprintsDone < SprintsPlanned;" in source
        assert "SprintsDone = SprintsDone + 1" in source, "a finished sprint counts towards the cycle"
        assert "public CycleState OnSprintAbandoned() => Nothing;" in source, \
            "an abandoned sprint must end the cycle outright, not shrink it"
        label = source.split("public string CycleLabel =>")[1].split(";")[0]
        assert '$"Sprint {SprintNumber} of {SprintsPlanned}"' in label, label

    def test_a_cycle_shows_which_sprint_is_running(self):
        t = Today(chooser=3)
        t.start_sprint()
        assert t.cycle.label == "Sprint 1 of 3"
        t.end_sprint(completed=True)
        assert t.cycle.label == "Sprint 2 of 3"

    def test_a_single_sprint_has_no_label(self):
        t = Today()
        t.start_sprint()
        assert t.cycle.label == ""

    def test_the_break_starts_itself_between_sprints(self):
        t = Today(chooser=3)
        t.start_sprint()
        t.end_sprint(completed=True)
        assert t.on_break, "a cycle should not need a click between its sprints"
        assert not t.enforcing

    def test_the_next_sprint_starts_when_the_break_runs_out(self):
        t = Today(chooser=3)
        t.start_sprint()
        t.end_sprint(completed=True)
        t.break_ran_out()
        assert t.sprints_run == 2
        assert t.enforcing

    def test_skipping_a_break_moves_straight_to_the_next_sprint(self):
        t = Today(chooser=2)
        t.start_sprint()
        t.end_sprint(completed=True)
        t.skip_break()
        assert t.sprints_run == 2, "skipping is free, and free does not mean the cycle stops"

    def test_the_cycle_stops_after_its_last_sprint(self):
        t = Today(chooser=2)
        t.start_sprint()
        t.end_sprint(completed=True)
        t.break_ran_out()
        t.end_sprint(completed=True)
        t.break_ran_out()
        assert t.sprints_run == 2, "a 2-sprint cycle must not run a third"
        assert t.cycle.label == ""

    def test_the_chooser_does_not_restart_the_count_mid_cycle(self):
        t = Today(chooser=3)
        t.start_sprint()
        t.end_sprint(completed=True)
        t.break_ran_out()
        assert t.cycle.done == 1 and t.cycle.planned == 3

    def test_a_cycle_abandoned_mid_sprint_stops_there(self):
        t = Today(chooser=3)
        t.start_sprint()
        t.end_sprint(completed=True)
        t.break_ran_out()
        t.end_sprint(completed=False)          # the second sprint is given up
        assert not t.cycle.in_cycle, "the rest of the cycle must not run on"
        assert not t.on_break and not t.offer_visible
        assert t.sprints_run == 2

    def test_abandoning_costs_that_sprint_and_no_more(self):
        """F2 decides the price once. The cycle does not add a second one."""
        t = Today(chooser=3)
        t.start_sprint()
        t.end_sprint(completed=False)
        assert t.momentum == -5, "one ended-early sprint, one decay"

    def test_the_fourth_sprint_of_a_cycle_earns_the_long_break(self):
        t = Today(chooser=4)
        t.start_sprint()
        for _ in range(3):
            t.end_sprint(completed=True)
            assert t.break_minutes_running == 5, "the first three breaks are the short one"
            t.break_ran_out()          # which starts the next sprint itself
        t.end_sprint(completed=True)
        assert t.in_a_row == 4
        assert break_minutes(t.in_a_row, t.short_break, t.long_break) == 15
        assert t.sprints_run == 4


class TestBreakSurvivesARestart:
    """F5: a saved break is picked up, or ended without a word."""

    def test_the_source_ends_an_expired_break_quietly(self):
        source = cycle_source()
        decide = source.split("public BreakResume Decide(DateTime nowUtc) =>")[1].split(";")[0]
        assert "EndsUtc <= nowUtc ? BreakResume.EndQuietly : BreakResume.Resume" in decide, decide

        # And the view model takes that branch silently: no notification, and no
        # sprint started behind the customer's back.
        vm = (Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "TodayViewModel.cs").read_text(
            encoding="utf-8")
        resume = vm.split("public void ResumeInterruptedBreak(")[1].split("\n    }")[0]
        quietly = resume.split("BreakResume.EndQuietly")[1]
        assert "Notify" not in quietly, "a break that ran out hours ago must not announce itself"
        assert "StartSprint" not in quietly, "nor start a sprint nobody is there for"

    def test_a_break_with_time_left_resumes(self):
        assert decide_break(100, 40) == "resume"

    def test_a_break_that_ran_out_while_closed_ends_quietly(self):
        assert decide_break(100, 100) == "end quietly"
        assert decide_break(100, 900) == "end quietly"

    def test_a_resumed_break_keeps_its_cycle(self):
        saved = Cycle(planned=3, done=1, phase="break")
        t = Today(chooser=0)
        t.cycle = saved
        t.on_break = True
        assert t.cycle.label == "Sprint 2 of 3"
        t.break_ran_out()
        assert t.sprints_run == 1, "the cycle carries on where it left off"


class TestBreaksAndCyclesSource:
    """The C# the mirrors above stand in for."""

    ROOT = Path(SERVER_DIR).parent / "DesktopApp"
    MODEL = ROOT / "Models" / "CycleState.cs"
    SETTINGS = ROOT / "Models" / "AppSettings.cs"
    TODAY_VM = ROOT / "ViewModels" / "TodayViewModel.cs"
    TODAY_XAML = ROOT / "Views" / "TodayView.xaml"
    SETTINGS_XAML = ROOT / "Views" / "SettingsView.xaml"
    NOTIFICATIONS = ROOT / "Models" / "Notifications.cs"

    def test_the_rules_live_in_a_model_of_their_own(self):
        assert self.MODEL.exists(), "tier 1 pins these rules by reading them"
        source = self.MODEL.read_text(encoding="utf-8")
        assert "LongBreakEvery = 4" in source
        assert "DefaultShortBreakMinutes = 5" in source
        assert "DefaultLongBreakMinutes = 15" in source
        assert "OffersBreak(bool completed) => completed" in source

    def test_the_model_never_reads_momentum_a_streak_or_a_goal(self):
        source = self.MODEL.read_text(encoding="utf-8")
        for forbidden in ("MomentumScore", "CurrentStreak", "DailyGoal"):
            assert forbidden not in source, f"a break must not be able to touch {forbidden}"

    def test_the_settings_persist_the_break_and_its_lengths(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        for field in ("ActiveBreak", "ShortBreakMinutes", "LongBreakMinutes",
                      "CompletedSprintsInARow", "CycleSprints"):
            assert field in source, f"AppSettings must persist {field}"

    def test_a_break_is_only_ever_offered_through_the_model(self):
        vm = self.TODAY_VM.read_text(encoding="utf-8")
        assert "CycleState.OffersBreak(completed)" in vm, \
            "the offer rule belongs to the model, not to a condition in the view model"
        assert "CycleState.BreakMinutes(" in vm

    def test_the_test_only_override_shortens_only_the_break(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "UseShortTimers" in source, "tier 3 cannot wait five minutes for a break"
        app = (self.ROOT / "App.xaml.cs").read_text(encoding="utf-8")
        assert "Models.CycleState.UseShortTimers = true;" in app

    def test_today_names_the_break_and_the_cycle(self):
        xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        for automation_id in ("StartBreakButton", "SkipBreakButton", "StartNextSprintButton",
                              "BreakPanelTitle", "CycleProgressText",
                              "Cycle_Off", "Cycle_2", "Cycle_3", "Cycle_4"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml

    def test_settings_can_change_both_break_lengths_and_the_notice(self):
        xaml = self.SETTINGS_XAML.read_text(encoding="utf-8")
        for automation_id in ("ShortBreakMinutesInput", "LongBreakMinutesInput",
                              "NotifyBreakOverToggle"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml

    def test_the_tray_says_break_rather_than_naming_a_shield(self):
        source = self.NOTIFICATIONS.read_text(encoding="utf-8")
        assert 'Break · ' in source, "the tooltip and title read \"Break · 4:59\" during a break"
        window = (self.ROOT / "MainWindow.xaml.cs").read_text(encoding="utf-8")
        assert "NotificationPolicy.BreakLabel(remaining)" in window

    def test_the_break_copy_has_no_exclamation_marks(self):
        """DESIGN_SYSTEM §9: no exclamation marks anywhere the customer reads."""
        vm = self.TODAY_VM.read_text(encoding="utf-8")
        region = vm.split("breaks and cycles (F5)")[1].split("--------------- stats")[0]
        assert '!"' not in region and "! " not in region, region

    def test_the_break_record_carries_the_cycle_it_belongs_to(self):
        source = self.MODEL.read_text(encoding="utf-8")
        run = source.split("public class RunningBreak")[1]
        for field in ("StartedUtc", "EndsUtc", "SprintsPlanned", "SprintsDone"):
            assert field in run, f"a resumed break needs {field}"
        assert "BreakResume.EndQuietly" in run


class TestBreakCopyInTheSleepWindow:
    """
    #272 and #301: during a break inside the nightly sleep window the
    sprint's shield is down, but the sleep shield still closes blocked apps.
    The offer, the running break's line and the caption under the ring each
    say which shield is up; outside the window they read as they always did.
    """

    def source(self) -> str:
        """The C# the mirrors stand for. Every case reads it first."""
        assert BREAK_COPY_MODEL.exists(), "Models/BreakCopy.cs is what these cases describe"
        return BREAK_COPY_MODEL.read_text(encoding="utf-8")

    @pytest.mark.parametrize("on_break,is_long", [(True, True), (True, False),
                                                  (False, True), (False, False)])
    def test_inside_the_window_every_line_says_the_sleep_shield_is_up(self, on_break, is_long):
        self.source()
        text = break_panel_text(True, on_break, is_long, 5, "06:00")
        assert "sleep shield" in text and "06:00" in text, text
        assert "still closed" in text, "and that blocked apps are still closed under it"
        assert "allowed" not in text, text
        assert not re.search(r"\bthe shield (is|stays) down|with the shield down", text), (
            "inside the window 'the shield is down' is only true of the sprint's shield"
        )

    def test_outside_the_window_the_lines_are_unchanged(self):
        self.source()
        assert break_panel_text(False, True, False, 5, "06:00") == \
            "The shield is down. Blocked apps are allowed until the break ends."
        assert break_panel_text(False, False, False, 5, "06:00") == \
            "5 minutes with the shield down. It changes nothing about your momentum."
        assert break_panel_text(False, False, True, 15, "06:00") == \
            "4 sprints in a row, so this break is 15 minutes. The shield stays down while it runs."

    @pytest.mark.parametrize("in_window", [True, False])
    def test_the_offer_names_its_length_either_way(self, in_window):
        self.source()
        assert "5 minutes" in break_panel_text(in_window, False, False, 5, "06:00")
        long_offer = break_panel_text(in_window, False, True, 15, "06:00")
        assert long_offer.startswith("4 sprints in a row, so this break is 15 minutes."), long_offer

    @pytest.mark.parametrize("in_window,resumed,expected", [
        (False, False, "Break — the shield is down"),
        (False, True, "Break resumed —\nthe shield is down"),
        (True, False, "Break — sleep shield still up"),
        (True, True, "Break resumed —\nsleep shield still up"),
    ])
    def test_the_caption(self, in_window, resumed, expected):
        self.source()
        assert break_caption(in_window, resumed) == expected

    @pytest.mark.parametrize("resumed", [True, False])
    def test_inside_the_window_the_caption_says_the_sleep_shield_is_up(self, resumed):
        self.source()
        caption = break_caption(True, resumed)
        assert "sleep shield" in caption and caption.endswith(" up"), caption
        assert "down" not in caption, "inside the window only the sprint's shield is down"

    @pytest.mark.parametrize("in_window,on_break,is_long", BREAK_COPY_CASES)
    def test_the_source_has_each_line_word_for_word(self, in_window, on_break, is_long):
        """
        The mirror rendered with the C# placeholders is the C# literal, so the
        two cannot drift apart without this failing.
        """
        rendered = break_panel_text(in_window, on_break, is_long, "{minutes}", "{sleepEndsText}",
                                    long_every="{CycleState.LongBreakEvery}")
        literal = ('$"' if "{" in rendered else '"') + rendered + '"'
        assert literal in self.source(), f"BreakCopy.PanelText has no {literal}"

    @pytest.mark.parametrize("in_window", [True, False])
    @pytest.mark.parametrize("resumed", [True, False])
    def test_the_source_has_each_caption(self, in_window, resumed):
        literal = break_caption(in_window, resumed).replace("\n", "\\n")
        assert f'"{literal}"' in self.source()

    def test_the_copy_has_no_exclamation_marks(self):
        """DESIGN_SYSTEM §9: no exclamation marks anywhere the customer reads."""
        source = self.source()
        assert '!"' not in source and "! " not in source, source
