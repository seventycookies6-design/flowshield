# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 1: sprints."""

from __future__ import annotations
import re
from datetime import date, timedelta
from datetime import date
from pathlib import Path
import pytest
from config import SERVER_DIR
from ._helpers import apply_momentum, custom_minutes_valid, distraction_summary, end_flow, journal_prompt_title, momentum_after_ending, phrase_matches, recorded_end, resume_decision, summary_title, watched_so_far



class TestMomentum:
    def test_completing_a_standard_sprint_adds_ten(self):
        assert apply_momentum(0, True, 25) == 10.0

    def test_longer_sprints_are_worth_more_but_are_capped(self):
        assert apply_momentum(0, True, 50) == 20.0
        assert apply_momentum(0, True, 600) == 30.0, "weight should cap at 3x"

    def test_short_sprints_have_a_floor(self):
        assert apply_momentum(0, True, 1) == 5.0, "weight should floor at 0.5x"

    def test_abandoning_decays_rather_than_resets(self):
        after = apply_momentum(100, False, 25)
        assert 0 < after < 100, f"expected decay, got {after}"
        assert after == 83.0

    def test_momentum_never_goes_negative(self):
        assert apply_momentum(1, False, 25) == 0.0
        assert apply_momentum(0, False, 25) == 0.0

    def test_decay_is_recoverable_in_a_few_sprints(self):
        score = apply_momentum(50, False, 25)
        for _ in range(2):
            score = apply_momentum(score, True, 25)
        assert score > 50, "two good sprints should more than undo one lapse"


class TestSprintResume:
    """F3: what happens to a sprint that was running when Basalt closed."""

    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"

    @pytest.mark.parametrize("planned,started,last_seen,ends,watched,expected", [
        (60, 0, 23, 60, None, 23),  # old settings use the capped legacy estimate
        (60, 0, 23, 60, -4, 0),
        (60, 0, 75, 60, 75, 60),
    ])
    def test_watched_so_far_uses_legacy_value_and_clamps(
            self, planned, started, last_seen, ends, watched, expected):
        assert watched_so_far(planned, started, last_seen, ends, watched) == expected

    def test_app_settings_defines_clamped_watched_so_far(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "public double WatchedSoFar" in source, \
            "RunningSprint must expose the shared WatchedSoFar estimate"
        prop = source.split("WatchedSoFar", 1)[1].split("}", 1)[0]
        assert "PlannedMinutes" in prop and (
            "Math.Clamp" in prop or ("Math.Max" in prop and "Math.Min" in prop)
        ), "RunningSprint.WatchedSoFar must clamp watched minutes to 0..PlannedMinutes"

    def test_the_threshold_matches_the_app(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "CompletedIfWatchedFraction = 0.5" in source

    @pytest.mark.parametrize("started,planned,last_seen,expected", [
        (10, 25, 0.2, "Resume"),              # crashed mid-sprint, relaunched quickly
        (10, 25, 9.5, "Resume"),              # closed almost immediately, still time left
        (24.9, 25, 24, "Resume"),             # seconds left
        (30, 25, 6, "RecordCompleted"),       # ran 24 of 25 minutes, then closed
        (60, 25, 47.5, "RecordCompleted"),    # watched exactly half
        (60, 25, 50, "RecordInterrupted"),    # watched 10 of 25 minutes
        (120, 90, 119, "RecordInterrupted"),  # closed a minute in, reopened much later
        (5, 0, 0, "Discard"),                 # unreadable record
    ])
    def test_decision(self, started, planned, last_seen, expected):
        assert resume_decision(started, planned, last_seen) == expected

    @pytest.mark.parametrize("started,planned,last_seen,watched,expected", [
        # #198: the 60-minute sprint Basalt watched 2 minutes of, reopened
        # near the end so LastSeenUtc sits a minute before the finish line.
        (65, 60, 6, 2, "RecordInterrupted"),
        # The same timestamps with the app genuinely up the whole time.
        (65, 60, 6, 59, "RecordCompleted"),
        (65, 60, 6, 30, "RecordCompleted"),        # exactly half
        (65, 60, 6, 29.9, "RecordInterrupted"),
    ])
    def test_the_decision_uses_watched_time_not_two_timestamps(
            self, started, planned, last_seen, watched, expected):
        assert resume_decision(started, planned, last_seen, watched) == expected
        assert resume_decision(started, planned, last_seen) == "RecordCompleted", \
            "the old estimate cannot tell these apart; that is the bug"

    @pytest.mark.parametrize("watched,expected", [
        (2, "RecordInterrupted"),
        (29.9, "RecordInterrupted"),
        (30, "RecordCompleted"),
        (59.5, "RecordCompleted"),  # the last heartbeat was 30 seconds before time was up
    ])
    def test_time_up_uses_the_watched_fraction(self, watched, expected):
        assert resume_decision(60, 60, 0.5, watched) == expected

    def test_a_settings_file_without_the_field_falls_back_to_the_old_estimate(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "public double? WatchedMinutes" in source, \
            "WatchedMinutes must be nullable so pre-existing settings files still load"
        decide = source.split("public SprintResume Decide(")[1].split("}", 1)[0]
        assert "WatchedSoFar" in decide, "Decide must read watched time through WatchedSoFar"
        # The preference itself lives in the shared helper since #203.
        so_far = source.split("public double WatchedSoFar", 1)[1].split(";", 1)[0]
        assert "WatchedMinutes ??" in so_far, \
            "WatchedSoFar must prefer WatchedMinutes and fall back when it is null"


class TestASprintIsRecordedAsEndingWhenItDid:
    """
    #300: a sprint finished by the first tick after the PC woke was stamped
    with the wake time, so the whole nap counted as focused minutes. So was
    one ended by a click handled after waking but before that tick: input
    already queued can come before the clock's first tick (Background
    priority until #319), and the end was now.
    Any end but an interruption is now capped at the planned end.
    """

    SOURCE = TestSprintResume.SOURCE

    def helper(self) -> str:
        """
        The C# the mirror stands for. Every case reads it first, so the mirror
        cannot go on passing after the helper is changed or deleted.
        """
        source = self.SOURCE.read_text(encoding="utf-8")
        parts = source.split("public static DateTime RecordedEnd(", 1)
        assert len(parts) == 2, "RunningSprint.RecordedEnd is what these cases describe"
        return parts[1].split("\n    }", 1)[0]

    def test_the_helper_makes_the_same_comparison(self):
        helper = self.helper()
        # The cap reads nothing but the two times: not whether the sprint
        # completed, so an End click after waking is capped too.
        assert re.search(
            r"return\s+nowUtc\s*>\s*plannedEndUtc\s*\?\s*plannedEndUtc\s*:\s*nowUtc", helper
        ), helper
        assert re.search(
            r"if\s*\(\s*interrupted\s*\)\s*return\s+startedUtc\s*\+\s*"
            r"TimeSpan\.FromMinutes\(\s*watchedMinutes\s*\)", helper
        ), helper

    # A 60-minute sprint started at minute 100, so it was due to end at 160.
    @pytest.mark.parametrize("now,completed,interrupted,expected", [
        (160 + 8 * 60, True, False, 160),   # finished by the first tick after an 8-hour sleep
        (160 + 1 / 60, True, False, 160),   # finished by a tick one second late
        (130, False, False, 130),           # ended early: when it was ended
        (160 + 8 * 60, False, False, 160),  # ended early by a click after waking, before that tick
        (160 + 8 * 60, False, True, 110),   # interrupted: the start plus the 10 minutes watched
    ])
    def test_the_recorded_end(self, now, completed, interrupted, expected):
        self.helper()
        assert recorded_end(100, 160, 10, now, completed, interrupted) == expected


class TestEndSprintPolicy:
    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "EndSprintPolicy.cs"

    def test_the_owner_decisions_are_in_the_app(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "TimeSpan.FromMinutes(2)" in source, "grace period is 2 minutes"
        assert "TimeSpan.FromSeconds(5)" in source, "Firm confirmation waits 5 s"
        assert "TimeSpan.FromSeconds(30)" in source, "Sealed countdown is 30 s"
        assert 'SealedPhrase = "end my sprint"' in source
        assert "score * 0.7 - 5" in source and "score * 0.85 - 2" in source

    @pytest.mark.parametrize("shield,elapsed,flow", [
        ("Soft", 5, "Cancel"), ("Firm", 119, "Cancel"), ("Sealed", 0, "Cancel"),
        ("Soft", 120, "Immediate"), ("Firm", 121, "Confirm"), ("Sealed", 3600, "Sealed"),
    ])
    def test_flow(self, shield, elapsed, flow):
        assert end_flow(shield, elapsed) == flow

    @pytest.mark.parametrize("score,shield,after", [
        (100, "Soft", 83.0), (100, "Firm", 83.0), (100, "Sealed", 65.0),
        (5, "Sealed", 0.0), (0, "Firm", 0.0),
    ])
    def test_sealed_costs_more(self, score, shield, after):
        assert momentum_after_ending(score, shield) == after

    @pytest.mark.parametrize("typed,ok", [
        ("end my sprint", True), ("  End  My Sprint ", True), ("END MY SPRINT", True),
        ("end my sprint.", False), ("end sprint", False), ("", False),
    ])
    def test_phrase(self, typed, ok):
        assert phrase_matches(typed) is ok


class TestSprintSummaryCard:
    """The card (F12) reads per-sprint numbers the session must now remember."""
    MODEL = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"
    VIEWMODEL = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "TodayViewModel.cs"

    def test_the_session_remembers_the_split_and_start_momentum(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "public int AppsClosed { get; set; }" in source
        assert "public int NudgesSent { get; set; }" in source
        assert "public double MomentumAtStart { get; set; }" in source

    def test_blocks_are_counted_as_closed_or_nudged(self):
        source = self.VIEWMODEL.read_text(encoding="utf-8")
        assert "public void RecordBlock(bool terminated, string name)" in source
        assert "_closedThisSprint++" in source and "_nudgesThisSprint++" in source
        assert "MomentumAtStart = S.MomentumScore" in source

    def test_the_card_is_fresh_for_every_sprint(self):
        source = self.VIEWMODEL.read_text(encoding="utf-8")
        assert "_closedThisSprint = 0" in source
        assert "_nudgesThisSprint = 0" in source
        assert "UpdateSummaryCard(completed, _current)" in source

    def test_a_saved_sprint_remembers_its_start_momentum(self):
        model = self.MODEL.read_text(encoding="utf-8")
        viewmodel = self.VIEWMODEL.read_text(encoding="utf-8")
        assert model.count("public double MomentumAtStart { get; set; }") == 2, \
            "both FocusSession and RunningSprint must remember the start momentum"
        assert "MomentumAtStart = saved.MomentumAtStart" in viewmodel, \
            "a resumed sprint must keep the momentum it started with"

    @pytest.mark.parametrize("start,end", [(0, 5), (40, 45)])
    def test_completed_title(self, start, end):
        assert summary_title(True, start, end) == "Sprint complete"

    @pytest.mark.parametrize("start,end,title", [
        (10, 0, "Ended early — momentum −10. It'll recover."),
        (2.4, 0, "Ended early — momentum −2. It'll recover."),
        (0.5, 0, "Ended early. It'll recover."),   # a small loss must not print "−0"
        (0, 0, "Ended early. It'll recover."),
    ])
    def test_abandoned_title(self, start, end, title):
        assert summary_title(False, start, end) == title

    @pytest.mark.parametrize("closed,nudged,total,expected", [
        (0, 0, 0, "No distractions caught"),
        (2, 1, 3, "2 closed · 1 nudge"),
        (0, 3, 3, "0 closed · 3 nudges"),
        (1, 0, 1, "1 closed · 0 nudges"),
        (0, 0, 4, "4 distractions caught"),
        (0, 0, 1, "1 distraction caught"),
    ])
    def test_distraction_wording(self, closed, nudged, total, expected):
        assert distraction_summary(closed, nudged, total) == expected


class TestSprintIntention:
    """F13: the optional one-line intention travels with the sprint it started."""
    MODEL = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"
    VIEWMODEL = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "TodayViewModel.cs"

    def test_the_session_and_the_saved_sprint_both_remember_it(self):
        model = self.MODEL.read_text(encoding="utf-8")
        assert model.count('public string Intention { get; set; } = "";') == 2, \
            "both FocusSession and RunningSprint must carry the intention"

    def test_the_intention_is_captured_when_the_sprint_starts(self):
        viewmodel = self.VIEWMODEL.read_text(encoding="utf-8")
        assert "Intention = intention" in viewmodel
        assert "Intention = saved.Intention" in viewmodel, \
            "a resumed sprint must keep the intention it started with"

    def test_a_sprint_recorded_while_closed_keeps_its_intention_and_momentum(self):
        viewmodel = self.VIEWMODEL.read_text(encoding="utf-8")
        assert viewmodel.count("Intention = saved.Intention") == 2, \
            "the resume path and the recorded-while-closed path must both carry the intention"
        assert viewmodel.count("MomentumAtStart = saved.MomentumAtStart") == 2, \
            "both saved-sprint paths must restore the start momentum"

    def test_the_prompt_repeats_the_intention(self):
        assert journal_prompt_title(None) == "What moved?"
        assert journal_prompt_title("   ") == "What moved?"
        assert journal_prompt_title("finish chapter 3") == \
            "You planned: finish chapter 3. What moved?"


class TestCustomSprintLengths:
    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"

    def test_settings_round_trips_last_custom_sprint_minutes(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "public int LastCustomSprintMinutes { get; set; } = 30;" in source

    @pytest.mark.parametrize("minutes", [5, 30, 120, 240])
    def test_validation_accepts_values_in_range(self, minutes):
        assert custom_minutes_valid(minutes) is True

    @pytest.mark.parametrize("minutes", [0, 1, 4, 241, 300, -5])
    def test_validation_rejects_values_outside_range(self, minutes):
        assert custom_minutes_valid(minutes) is False

    def test_the_viewmodel_exposes_the_bounds(self):
        vm = (Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels"
              / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert "CustomMinMinutes = 5" in vm
        assert "CustomMaxMinutes = 240" in vm

    @staticmethod
    def viewmodel_member(name: str) -> str:
        vm = (Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels"
              / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert name in vm, f"TodayViewModel no longer has {name}"
        return vm.split(name, 1)[1].split("\n    }", 1)[0]

    def test_selecting_custom_without_access_opens_the_upgrade_page(self):
        # The radio's two-way IsChecked binding writes the property before any
        # command fires, so the gate has to be in the setter itself. The first
        # draft put it in a command and the locked user got the feature anyway.
        setter = self.viewmodel_member("public bool IsCustomSelected")
        assert "_main.IsLocked" in setter
        assert "_main.OpenUpgradePage()" in setter

    def test_a_valid_custom_value_is_persisted_when_typed(self):
        # The first draft only saved when the Custom radio was clicked, never
        # when the number was typed — so the value was lost on restart.
        apply = self.viewmodel_member("private void ApplyCustomMinutes()")
        assert "S.LastCustomSprintMinutes = _customMinutes" in apply
        assert "_main.SaveSettings()" in apply
        text_setter = self.viewmodel_member("public string CustomMinutesText")
        assert "ApplyCustomMinutes()" in text_setter

    def test_start_is_refused_while_the_custom_value_is_invalid(self):
        vm = (Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels"
              / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert "StartCommand = new RelayCommand(StartSprint, CanStart)" in vm
        can_start = vm.split("private bool CanStart()")[1].split("\n", 1)[0]
        assert "IsCustomMinutesValid" in can_start

    def test_the_input_is_bound_as_text_so_garbage_is_rejected(self):
        # An int-typed binding swallows "abc" as a silent binding error and
        # leaves the previous length in place with no message.
        view = (Path(SERVER_DIR).parent / "DesktopApp" / "Views"
                / "TodayView.xaml").read_text(encoding="utf-8-sig")
        assert "{Binding CustomMinutesText, UpdateSourceTrigger=PropertyChanged}" in view
        assert 'AutomationProperties.AutomationId="CustomMinutesError"' in view


# ================================= momentum trend and explainer (F14 / 3.2)

class TestMomentumTrend:
    """
    Python mirror of Models/MomentumTrend.cs. Momentum is event-driven, so the
    trend is a replay of the sessions rather than a second record of the score.
    """

    DAYS = 30
    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    MODEL = DESKTOP / "Models" / "MomentumTrend.cs"

    @staticmethod
    def _after(score, completed, minutes, sealed_=False, interrupted=False):
        # An interrupted sprint leaves the score alone, exactly as
        # TodayViewModel.ApplyMomentum does — it is never called for one.
        if interrupted:
            return score
        if completed:
            weight = min(max(minutes / 25.0, 0.5), 3.0)
            return round(score + 10 * weight, 1)
        return round(max(0.0, score * 0.7 - 5) if sealed_ else max(0.0, score * 0.85 - 2), 1)

    @staticmethod
    def _unpack(session):
        """Sessions are (day, completed, minutes, sealed) with optional interrupted."""
        day, completed, minutes, sealed_ = session[:4]
        return day, completed, minutes, sealed_, (len(session) > 4 and session[4])

    def _points(self, sessions, today, days=None):
        days = days or self.DAYS
        start = today - timedelta(days=days - 1)
        by_day, score = {}, 0.0
        for session in sorted(sessions):
            day, completed, minutes, sealed_, interrupted = self._unpack(session)
            score = self._after(score, completed, minutes, sealed_, interrupted)
            by_day[day] = score
        running = 0.0
        for session in sorted(sessions):
            day, completed, minutes, sealed_, interrupted = self._unpack(session)
            if day < start:
                running = self._after(running, completed, minutes, sealed_, interrupted)
        out = []
        for i in range(days):
            day = start + timedelta(days=i)
            if day in by_day:
                running = by_day[day]
            out.append((day, running))
        return out

    def test_a_quiet_day_carries_the_score_forward(self):
        today = date(2026, 9, 18)
        points = self._points([(date(2026, 9, 16), True, 25, False)], today)
        assert len(points) == self.DAYS
        assert points[-1][1] == 10.0
        assert points[-2][1] == 10.0, "a day with no sprints must not drop the line to zero"

    def test_days_before_the_window_still_count(self):
        """The first point is the score as it stood then, not zero."""
        today = date(2026, 9, 18)
        old = date(2026, 1, 1)
        points = self._points([(old, True, 25, False)], today)
        assert points[0][1] == 10.0

    def test_ending_early_shows_as_a_dip_not_a_reset(self):
        today = date(2026, 9, 18)
        points = self._points([
            (date(2026, 9, 10), True, 50, False),
            (date(2026, 9, 11), False, 25, True),
        ], today)
        after_finish = round(0 + 10 * 2.0, 1)
        assert after_finish == 20.0
        assert points[-1][1] == round(max(0.0, 20.0 * 0.7 - 5), 1) == 9.0
        assert points[-1][1] > 0, "momentum decays, it does not reset"

    def test_sprints_that_were_all_ended_early_leave_nothing_to_draw(self):
        """
        Momentum only moves when a sprint is *finished*. Someone who started
        three and ended them all early has sessions and a score of zero, and a
        line pinned to the bottom gridline reads as broken rather than as
        "nothing yet" — so the chart stays hidden.
        """
        today = date(2026, 9, 18)
        points = self._points([
            (date(2026, 9, 16), False, 25, False),
            (date(2026, 9, 17), False, 25, False),
            (date(2026, 9, 18), False, 25, True),
        ], today)
        assert all(score == 0.0 for _, score in points)
        assert not any(score > 0 for _, score in points),             "nothing above zero means nothing worth drawing"

    def test_the_series_is_always_the_full_window(self):
        points = self._points([], date(2026, 9, 18))
        assert len(points) == self.DAYS
        assert {score for _, score in points} == {0.0}

    def test_the_explanation_matches_the_numbers_in_the_code(self):
        """
        The explainer states the rule in points and percentages. If the rule
        changes and the words don't, the app is lying to the customer in the
        one place that claims to be authoritative.
        """
        source = self.MODEL.read_text(encoding="utf-8")
        policy = (self.DESKTOP / "Models" / "EndSprintPolicy.cs").read_text(
            encoding="utf-8")
        today_vm = (self.DESKTOP / "ViewModels" / "TodayViewModel.cs").read_text(
            encoding="utf-8")

        assert "Math.Clamp(session.PlannedMinutes / 25.0, 0.5, 3.0)" in today_vm
        assert "S.MomentumScore + 10 * weight" in today_vm
        assert "score * 0.7 - 5" in policy and "score * 0.85 - 2" in policy

        explanation = source.split("Explanation =", 1)[1]
        assert "10 points for a 25-minute one" in explanation
        assert "5 points at the least, 30 at the most" in explanation, \
            "0.5 and 3.0 times 10 points"
        assert "15% and 2 points at Soft or Firm" in explanation
        assert "30% and 5 at Sealed" in explanation
        assert "never goes below zero" in explanation
        assert "does not decay overnight" in explanation

    def test_an_interrupted_sprint_does_not_move_the_line(self):
        """
        #195: momentum is only ever changed by a finished sprint or a deliberate
        early end, so the replay must leave an interrupted one alone — otherwise
        the chart drifts below the score printed beside it.
        """
        today = date(2026, 9, 18)
        points = self._points([
            (date(2026, 9, 16), True, 25, False, False),
            (date(2026, 9, 17), False, 25, False, True),   # interrupted
        ], today)
        assert points[-1][1] == 10.0, "an interrupted sprint enforces nothing and costs nothing"

    def test_the_trend_replays_rather_than_recording(self):
        """
        A stored daily sample would start the day the feature shipped and could
        disagree with MomentumScore. The model must derive from Sessions.
        """
        source = self.MODEL.read_text(encoding="utf-8")
        assert "settings.Sessions.OrderBy" in source
        settings = (self.DESKTOP / "Models" / "AppSettings.cs").read_text(
            encoding="utf-8")
        assert "MomentumHistory" not in settings, \
            "the trend must not add a second copy of the score to settings"


class TestMomentumTrendView:
    """The chart is on Today, its explainer on History, and both follow the chart rules."""

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    XAML = DESKTOP / "Views" / "TodayView.xaml"

    def _momentum_card(self):
        """Just the part F14 added, so this says nothing about older screens."""
        xaml = self.XAML.read_text(encoding="utf-8")
        return xaml.split("F14: the 30-day trend", 1)[1].split("</Border>", 1)[0]

    def test_today_has_the_chart_and_history_has_the_explainer(self):
        """The Today declutter (#147) moved the rule to History; Today links to it."""
        today = self.XAML.read_text(encoding="utf-8")
        history = (self.DESKTOP / "Views" / "HistoryView.xaml").read_text(encoding="utf-8")
        for automation_id in ("MomentumTrendRange", "MomentumTrendPeak", "MomentumRulesLink"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in today
        for automation_id in ("MomentumExplainerButton", "MomentumExplainerText"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in history
            assert f'AutomationProperties.AutomationId="{automation_id}"' not in today

    def test_no_automation_id_sits_on_a_layout_panel(self):
        """
        A Grid or StackPanel is not surfaced to UI Automation, so an id on one
        can never be found — and exists() on it answers the same whether the
        content is there or not, which is how a passing test can mean nothing.
        """
        block = self._momentum_card()
        for tag in ("<Grid", "<StackPanel"):
            for element in block.split(tag)[1:]:
                head = element.split(">", 1)[0]
                assert "AutomationProperties.AutomationId" not in head,                     f"an AutomationId is on a {tag[1:]}, where nothing can find it"

    def test_the_chart_is_described_where_a_screen_reader_can_hear_it(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        vm = (self.DESKTOP / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert 'AutomationProperties.Name="{Binding TrendDescription}"' in xaml
        assert "public string TrendDescription" in vm

    def test_the_chart_follows_the_design_system(self):
        """
        DESIGN_SYSTEM.md "Charts": one series in primary at 2 px, no area fill,
        horizontal gridlines in border.
        """
        xaml = self.XAML.read_text(encoding="utf-8")
        chart = xaml.split('<Grid Height="64"', 1)[1].split("</Grid>", 1)[0]

        # DynamicResource since F21: a colour reference has to re-resolve when
        # the light theme swaps the tokens dictionary under it.
        assert 'Stroke="{DynamicResource Primary}"' in chart
        assert 'StrokeThickness="2"' in chart
        assert "Fill=" not in chart, "a line chart has no area fill"
        assert chart.count("<Polyline") == 1, "no more than one series"
        assert 'Stroke="{DynamicResource Edge}"' in chart, "gridlines use the border token"

        for line in chart.split("<Line")[1:]:
            head = line.split("/>", 1)[0]
            y1 = head.split('Y1="', 1)[1].split('"', 1)[0]
            y2 = head.split('Y2="', 1)[1].split('"', 1)[0]
            assert y1 == y2, "gridlines are horizontal only"

    def test_the_chart_hides_itself_when_there_is_nothing_to_draw(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        assert "{Binding TrendVisible, Converter={StaticResource BoolVis}}" in xaml
        vm = (self.DESKTOP / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert "TrendVisible = points.Any(p => p.Score > 0);" in vm,             "the chart hides until there is momentum, not merely until there is a sprint"


# ===================================== History and the weekly view (F16 / 3.1, 3.6)

class TestHistoryStats:
    """
    Python mirror of Models/HistoryStats.cs.

    History is a projection of AppSettings.Sessions, not a second record, so
    every rule it applies — where a week starts, which day a sprint counts on,
    how a heatmap cell picks its step — is pinned here against the source.
    """

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    MODEL = DESKTOP / "Models" / "HistoryStats.cs"

    HEATMAP_DAYS = 30
    STEPS = 5

    # --------------------------------------------------------- the rules again

    @staticmethod
    def _week_start(day):
        """Monday of that week. The C# uses DayOfWeek, where Sunday is 0."""
        back = 6 if day.weekday() == 6 else day.weekday()
        return day - timedelta(days=back)

    @classmethod
    def _week_end(cls, day):
        return cls._week_start(day) + timedelta(days=6)

    @classmethod
    def _for_week(cls, sessions, now):
        """sessions are (local day, actual minutes, completed, blocks)."""
        start, end = cls._week_start(now), cls._week_end(now)
        inside = [s for s in sessions if start <= s[0] <= end]
        return {
            "start": start,
            "end": end,
            "minutes": round(sum(s[1] for s in inside), 1),
            "completed": sum(1 for s in inside if s[2]),
            "blocks": sum(s[3] for s in inside),
        }

    @classmethod
    def _step(cls, minutes, peak):
        import math
        if minutes <= 0:
            return 0
        if peak <= 0:
            return 1
        share = math.ceil(minutes / peak * (cls.STEPS - 1))
        return min(max(share, 1), cls.STEPS - 1)

    @classmethod
    def _heatmap(cls, sessions, today, days=None):
        days = days or cls.HEATMAP_DAYS
        start = today - timedelta(days=days - 1)
        by_day = {}
        for day, minutes, _completed, _blocks in sessions:
            if start <= day <= today:
                by_day[day] = by_day.get(day, 0) + minutes
        by_day = {day: round(m) for day, m in by_day.items()}
        peak = max(by_day.values()) if by_day else 0
        return [
            (start + timedelta(days=i),
             by_day.get(start + timedelta(days=i), 0),
             cls._step(by_day.get(start + timedelta(days=i), 0), peak))
            for i in range(days)
        ]

    # ------------------------------------------------------- week boundaries

    def test_the_week_runs_monday_to_sunday(self):
        # 21 September 2026 is a Monday.
        monday = date(2026, 9, 21)
        assert monday.weekday() == 0
        assert self._week_start(monday) == monday
        assert self._week_end(monday) == date(2026, 9, 27)

    def test_every_day_of_one_week_agrees_on_its_monday(self):
        monday = date(2026, 9, 21)
        for offset in range(7):
            day = monday + timedelta(days=offset)
            assert self._week_start(day) == monday, f"{day} fell outside its own week"
            assert self._week_end(day) == monday + timedelta(days=6)

    def test_sunday_belongs_to_the_week_that_just_ended(self):
        """
        The one boundary that is easy to get wrong: .NET numbers Sunday 0, so a
        naive DayOfWeek - 1 would send Sunday back to the *next* Monday and
        silently move a Sunday evening's sprints into next week's total.
        """
        sunday = date(2026, 9, 27)
        assert sunday.weekday() == 6
        assert self._week_start(sunday) == date(2026, 9, 21)
        assert self._week_end(sunday) == sunday

        source = self.MODEL.read_text(encoding="utf-8")
        assert "DayOfWeek.Sunday ? 6" in source, \
            "Sunday needs the full six days back, not DayOfWeek - 1"

    def test_monday_starts_a_new_week_rather_than_extending_the_old_one(self):
        assert self._week_start(date(2026, 9, 28)) == date(2026, 9, 28)
        assert self._week_start(date(2026, 9, 27)) == date(2026, 9, 21)

    def test_the_week_is_monday_first_whatever_the_regional_format_says(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "CurrentCulture" not in source and "FirstDayOfWeek" not in source, \
            "a culture-dependent week would move last week's hours when the format changes"

    # ------------------------------------------------------- the week's figures

    def test_the_week_counts_only_its_own_sprints(self):
        now = date(2026, 9, 23)          # Wednesday
        week = self._for_week([
            (date(2026, 9, 20), 60.0, True, 4),     # the Sunday before: last week
            (date(2026, 9, 21), 25.0, True, 1),
            (date(2026, 9, 23), 12.0, False, 2),
            (date(2026, 9, 28), 45.0, True, 9),     # next Monday
        ], now)
        assert week["minutes"] == 37.0
        assert week["completed"] == 1
        assert week["blocks"] == 3

    def test_minutes_count_whatever_the_outcome_but_completed_does_not(self):
        """
        A sprint ended after 12 of its 25 minutes really was 12 minutes of
        focus, and Today's card already sums every sprint's minutes for one day
        — the week must agree with it. "Sprints completed" is the finished ones.
        """
        now = date(2026, 9, 23)
        week = self._for_week([
            (date(2026, 9, 21), 25.0, True, 0),
            (date(2026, 9, 22), 12.0, False, 0),
        ], now)
        assert week["minutes"] == 37.0
        assert week["completed"] == 1

    def test_an_empty_week_is_zero_rather_than_missing(self):
        week = self._for_week([], date(2026, 9, 23))
        assert (week["minutes"], week["completed"], week["blocks"]) == (0, 0, 0)
        assert week["start"] == date(2026, 9, 21)

    def test_a_sprint_counts_on_the_local_day_it_started(self):
        """A sprint begun at 11:30pm belongs to that evening, not to tomorrow."""
        source = self.MODEL.read_text(encoding="utf-8")
        body = source.split("DayOf(FocusSession session) =>", 1)[1].split(";", 1)[0]
        assert "StartedUtc.ToLocalTime().Date" in body
        assert "EndedUtc" not in body, "the day a sprint ended is not the day it counts on"

    # ------------------------------------------------------ heatmap bucketing

    def test_no_focus_at_all_is_its_own_step(self):
        """One minute must look different from none; step 0 means nothing."""
        assert self._step(0, 120) == 0
        assert self._step(1, 120) == 1

    def test_the_busiest_day_takes_the_darkest_step(self):
        assert self._step(120, 120) == self.STEPS - 1 == 4

    def test_the_four_used_steps_split_the_range_evenly(self):
        peak = 100
        assert self._step(1, peak) == 1
        assert self._step(25, peak) == 1
        assert self._step(26, peak) == 2
        assert self._step(50, peak) == 2
        assert self._step(51, peak) == 3
        assert self._step(75, peak) == 3
        assert self._step(76, peak) == 4
        assert self._step(100, peak) == 4

    def test_the_scale_follows_the_window_not_a_fixed_minute_count(self):
        """
        25-minute sprints and three-hour days must both read; scaling against a
        fixed target would flatten one of them into a single block.
        """
        assert self._step(25, 25) == 4, "a light week still shows its best day dark"
        assert self._step(25, 200) == 1, "a heavy week puts the same 25 minutes low"

    def test_a_day_that_is_the_only_one_with_any_focus_is_still_readable(self):
        assert self._step(5, 5) == 4

    def test_a_peak_of_zero_never_divides_by_it(self):
        assert self._step(0, 0) == 0
        assert self._step(3, 0) == 1

    def test_the_grid_is_always_the_full_window(self):
        cells = self._heatmap([], date(2026, 9, 23))
        assert len(cells) == self.HEATMAP_DAYS
        assert {step for _day, _m, step in cells} == {0}
        assert cells[0][0] == date(2026, 9, 23) - timedelta(days=29)
        assert cells[-1][0] == date(2026, 9, 23)

    def test_days_outside_the_window_are_left_out_of_the_scale(self):
        """An old marathon day must not flatten the last 30 days against it."""
        today = date(2026, 9, 23)
        cells = self._heatmap([
            (date(2026, 1, 1), 600.0, True, 0),
            (date(2026, 9, 22), 30.0, True, 0),
        ], today)
        by_day = {day: (minutes, step) for day, minutes, step in cells}
        assert by_day[date(2026, 9, 22)] == (30, 4), \
            "the busiest day inside the window is the top of the scale"

    def test_several_sprints_on_one_day_add_up_in_one_cell(self):
        today = date(2026, 9, 23)
        cells = self._heatmap([
            (today, 25.0, True, 0),
            (today, 25.0, True, 0),
        ], today)
        assert cells[-1][1] == 50

    def test_the_heatmap_has_five_steps_and_thirty_days(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert f"HeatmapDays = {self.HEATMAP_DAYS}" in source
        assert f"Steps = {self.STEPS}" in source, \
            'DESIGN_SYSTEM.md §7: "five steps from surface-2 to primary"'

    # ------------------------------------------------- the most-blocked app

    @staticmethod
    def _most_blocked(apps):
        """apps are (display name, block count)."""
        ranked = sorted(
            (a for a in apps if a[1] > 0),
            key=lambda a: (-a[1], a[0].lower()))
        return ranked[0][0] if ranked else ""

    def test_the_app_blocked_most_often_wins(self):
        assert self._most_blocked([("Discord", 3), ("Steam", 9), ("Slack", 1)]) == "Steam"

    def test_a_tie_breaks_on_the_name_so_the_card_stays_still(self):
        """
        Two apps on the same count must not swap places between one draw and the
        next, which is what list order would do.
        """
        assert self._most_blocked([("Steam", 4), ("Discord", 4)]) == "Discord"
        assert self._most_blocked([("Discord", 4), ("Steam", 4)]) == "Discord"

    def test_a_tie_ignores_case(self):
        assert self._most_blocked([("brave", 2), ("Ableton", 2)]) == "Ableton"

    def test_apps_that_have_never_been_blocked_are_not_named(self):
        assert self._most_blocked([("Discord", 0), ("Steam", 0)]) == ""
        assert self._most_blocked([]) == ""

    def test_the_tie_break_is_the_one_in_the_source(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "OrderByDescending(a => a.BlockCount)" in source
        assert "ThenBy(a => a.DisplayName, StringComparer.OrdinalIgnoreCase)" in source

    # ------------------------------------------------------------ the shape

    def test_the_aggregation_is_pure(self):
        """
        No clock, no file system and no view: the page's rules have to be
        testable on their own, and the same numbers have to come out twice.
        """
        source = self.MODEL.read_text(encoding="utf-8")
        for forbidden in ("DateTime.Now", "DateTime.UtcNow", "File.", "SettingsService",
                          "HttpClient", "using System.Windows"):
            assert forbidden not in source, \
                f"HistoryStats must stay pure; it mentions {forbidden}"

    def test_history_adds_nothing_to_what_is_stored(self):
        """
        Same reasoning as the momentum trend: a stored weekly roll-up would
        start the day this shipped and could disagree with the sessions it
        claims to summarise.
        """
        settings = (self.DESKTOP / "Models" / "AppSettings.cs").read_text(encoding="utf-8")
        for forbidden in ("WeeklyStats", "HistoryCache", "FocusMinutesByDay"):
            assert forbidden not in settings


# ============================== graceful close at Firm (F7 / roadmap 1.8)

class TestGracefulClose:
    """
    Python mirror of Models/GracefulClose.cs.

    Firm used to call Kill() the instant it saw a blocked app. It now asks the
    app to close itself, waits, and only forces it if it is still there — which
    is the difference between losing an essay and being told to save it.
    """

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    MODEL = DESKTOP / "Models" / "GracefulClose.cs"

    GRACE_SECONDS = 10
    SHORT_GRACE_SECONDS = 2

    @staticmethod
    def _is_graceful(shield, hard_kill):
        return not hard_kill and shield >= 2      # 2 = Firm, 3 = Sealed

    def test_soft_never_warns_about_closing_because_it_never_closes(self):
        assert not self._is_graceful(1, False)

    def test_firm_and_sealed_warn_first(self):
        assert self._is_graceful(2, False)
        assert self._is_graceful(3, False)

    def test_hard_kill_stays_instant_at_every_shield(self):
        """
        Someone who turned hard kill on asked for no way round it, and ten
        seconds to alt-tab and save is a way round it.
        """
        for shield in (1, 2, 3):
            assert not self._is_graceful(shield, True)

    def test_the_warning_says_the_app_the_delay_and_what_to_do(self):
        source = self.MODEL.read_text(encoding="utf-8")
        warning = source.split("public static string Warning", 1)[1]
        warning = warning.split("return ", 1)[1].split(";", 1)[0]
        assert "is blocked" in warning
        assert "closing in {seconds} s" in warning
        assert "Save your work." in warning

    def test_the_grace_period_is_ten_seconds_and_two_under_short_timers(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert f"TimeSpan.FromSeconds({self.SHORT_GRACE_SECONDS})" in source
        assert f"TimeSpan.FromSeconds({self.GRACE_SECONDS})" in source
        assert "UseShortTimers" in source, "the UI suite cannot wait ten seconds a time"

    def test_the_short_timer_flag_is_wired_to_the_command_line(self):
        app = (self.DESKTOP / "App.xaml.cs").read_text(encoding="utf-8")
        assert "Models.GracefulClose.UseShortTimers = true;" in app

    def test_closing_is_asked_for_before_it_is_forced(self):
        """
        CloseMainWindow is the same request the window's own close button
        sends; Kill is not. The order is the whole feature.
        """
        service = (self.DESKTOP / "Services" / "AppBlockerService.cs").read_text(
            encoding="utf-8")
        sweep = service.split("private void Tick", 1)[1]
        asked = sweep.index("CloseMainWindow()")
        forced = sweep.index("_closingAt.Remove(key)")
        assert asked < forced, "the app must be asked to close before the deadline kills it"

    def test_a_blocked_app_that_goes_away_forgets_its_deadline(self):
        service = (self.DESKTOP / "Services" / "AppBlockerService.cs").read_text(
            encoding="utf-8")
        assert "_closingAt.Remove(gone)" in service, (
            "a half-finished close must not outlive the app it was closing"
        )
