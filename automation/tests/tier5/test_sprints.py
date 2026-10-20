# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: sprints."""

from __future__ import annotations
import re
import time
from pathlib import Path
import psutil
import pytest
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from core import state_verifier as verify
from ._helpers import DESKTOP



# ======================================= today's counters mean "today"

class TestTodayCounters:
    """
    "Distractions blocked" sat under a TODAY heading but summed every app's
    lifetime BlockCount, so it never reset and counted yesterday's blocks.
    """

    def test_blocks_today_is_not_a_lifetime_sum(self):
        source = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(
            encoding="utf-8")
        stats = source.split("public void RefreshStats()")[1].split("\n    }")[0]

        assert "Sum(a => a.BlockCount)" not in stats, \
            "a lifetime total must not be displayed as today's figure"
        assert "BlocksTodayCurrent" in stats

    def test_the_day_rolls_over(self):
        """RecordBlock must zero the tally when the date changes."""
        source = (Path(DESKTOP_DIR) / "Models" / "AppSettings.cs").read_text(
            encoding="utf-8")
        record = source.split("public void RecordBlock")[1].split("\n    }")[0]
        assert "BlocksToday = 0" in record, "the counter never resets at midnight"

    def test_a_sprint_records_its_own_block_count(self):
        source = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(
            encoding="utf-8")
        assert "_current.BlocksEnforced = _blocksThisSprint" in source, (
            "a session must record its own blocks, not the process-wide total "
            "since launch"
        )


# ============ a sprint can't be escaped by closing Basalt (F3, #43)

class TestSprintSurvivesRestart:
    """
    A running sprint lived only in memory, so killing Basalt from Task
    Manager, a crash or a reboot ended it silently, even a Sealed one.
    """

    @staticmethod
    def today() -> str:
        return (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")

    def test_the_sprint_is_saved_before_enforcement_starts(self):
        start = self.today().split("private void StartSprint()")[1].split("\n    }")[0]
        assert "S.ActiveSprint = new RunningSprint" in start
        assert start.index("_main.SaveSettings()") < start.index("BeginRunning("), \
            "a crash between starting and saving would lose the sprint"

    def test_ending_a_sprint_clears_it(self):
        end = self.today().split("private void EndSprint(bool completed, bool interrupted = false)")[1].split("\n    }")[0]
        assert "S.ActiveSprint = null" in end

    def test_startup_resumes_after_the_defaults_are_applied(self):
        main = (Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs").read_text(encoding="utf-8")
        ctor = main.split("public MainViewModel(")[1].split("\n    }")[0]
        assert "Today.ResumeInterruptedSprint()" in ctor
        assert ctor.index("Today.SelectedShield = Settings.DefaultShield") < ctor.index("ResumeInterruptedSprint"), \
            "applying the default shield after resuming would replace a Sealed sprint's shield"

    def test_a_resumed_sprint_keeps_its_shield(self):
        resume = self.today().split("public void ResumeInterruptedSprint")[1].split("\n    }")[0]
        assert "Shield = saved.Shield" in resume and "BeginRunning(" in resume

    @pytest.mark.ui
    def test_killing_flowshield_mid_sprint_does_not_end_a_sealed_sprint(self, logger):
        from desktop.app_controller import DesktopController

        first = DesktopController(logger)
        try:
            first.launch_app(clean_state=True)
            first.connect_window()
            time.sleep(1.0)
            first.navigate_to_tab("Blocked Apps")
            first.add_blocked_app(TEST_BLOCK_APP)
            first.navigate_to_tab("Today")
            first.select_shield("Sealed")
            time.sleep(0.5)
            first.start_sprint()
            time.sleep(2.0)
            saved = verify.read_settings()
            assert saved.get("ActiveSprint"), "the running sprint was not saved"
        finally:
            first.close_app()          # a hard kill, like ending it from Task Manager

        second = DesktopController(logger)
        try:
            second.launch_app(clean_state=False)
            second.connect_window()
            time.sleep(1.5)
            second.navigate_to_tab("Today")
            assert "resumed" in second.session_state().lower(), second.session_state()
            assert second.exists("StopSprintButton", timeout=3), "the sprint is not running after relaunch"

            second.navigate_to_tab("Blocked Apps")
            time.sleep(0.6)
            assert second.is_control_enabled("NewAppNameInput") is False, \
                "a resumed Sealed sprint must keep the blocklist locked"
            assert second.is_control_enabled("AddAppButton") is False
        finally:
            second.close_app()


# ============ a sprint couldn't be escaped by one click (F2, #47)

class TestNoOneClickEscape:
    """
    End sprint was one click at every shield level, and the tray's Quit exited
    instantly mid-sprint, so neither Firm nor Sealed actually held.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_the_end_button_goes_through_the_policy(self):
        today = self.read("ViewModels", "TodayViewModel.cs")
        assert "StopCommand = new RelayCommand(() => RequestEnd()" in today
        assert "EndSprint(completed: false), () => IsRunning" not in today
        request = today.split("public bool RequestEnd()")[1].split("\n    }")[0]
        assert "EndSprintPolicy.FlowFor(" in request

    def test_end_anyway_rechecks_the_wait(self):
        today = self.read("ViewModels", "TodayViewModel.cs")
        end_anyway = today.split("private void EndAnyway()")[1].split("\n    }")[0]
        assert "!EndAnywayEnabled) return" in end_anyway, \
            "End anyway must refuse before the countdown and phrase are done, whatever invoked it"

    def test_tray_quit_and_window_close_use_the_end_flow(self):
        window = self.read("MainWindow.xaml.cs")
        assert 'menu.Items.Add("Quit", null, (_, _) => Quit());' in window
        quit_ = window.split("private void Quit()")[1].split("\n    }")[0]
        assert "RequestEnd()" in quit_
        closing = window.split("protected override void OnClosing")[1].split("\n    }")[0]
        assert "NeedsEndFlowToQuit" in closing

    def test_short_timers_only_shorten_waits(self):
        policy = self.read("Models", "EndSprintPolicy.cs")
        flow = policy.split("public static EndFlow FlowFor")[1].split(";")[0]
        assert "UseShortTimers" not in flow, "the test flag must not change which flow applies"

    @pytest.mark.ui
    def test_closing_the_window_mid_firm_sprint_goes_through_the_flow(self, fresh_app):
        import psutil

        fresh_app.navigate_to_tab("Settings")
        fresh_app.set_toggle("MinimizeToTrayToggle", False)   # close really exits
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Firm")
        time.sleep(0.4)
        fresh_app.start_sprint()
        fresh_app.wait_out_grace_period()

        fresh_app.window.close()                      # WM_CLOSE, like clicking X
        time.sleep(1.5)
        assert psutil.pid_exists(fresh_app.pid), "closing the window escaped a Firm sprint"
        assert fresh_app.exists("KeepGoingButton", timeout=3), "no end flow was shown"

        deadline = time.time() + 10
        while time.time() < deadline and not fresh_app.is_control_enabled("EndAnywayButton"):
            time.sleep(0.4)
        fresh_app.click("EndAnywayButton")

        deadline = time.time() + 10
        while time.time() < deadline and psutil.pid_exists(fresh_app.pid):
            time.sleep(0.4)
        assert not psutil.pid_exists(fresh_app.pid), "Basalt didn't quit after the sprint ended"


# ============ custom sprint lengths must be wired up (roadmap 2.3)

class TestCustomSprintLengthsWired:
    """The Custom option must exist in the view and be bound to the viewmodel."""

    def test_the_view_has_a_custom_sprint_option(self):
        view = (Path(DESKTOP_DIR) / "Views" / "TodayView.xaml").read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="SprintLength_Custom"' in view
        assert "Custom…" in view

    def test_the_custom_input_is_bound(self):
        view = (Path(DESKTOP_DIR) / "Views" / "TodayView.xaml").read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="CustomMinutesInput"' in view
        assert "{Binding CustomMinutes" in view

    def test_the_existing_presets_are_still_present(self):
        view = (Path(DESKTOP_DIR) / "Views" / "TodayView.xaml").read_text(encoding="utf-8")
        for length in (15, 25, 45, 60, 90):
            assert f'SprintLength_{length}' in view, f"preset {length} min was removed"

    def test_presets_do_not_bind_to_the_live_length(self):
        """
        Presets bind to PresetMinutes, which is 0 while Custom is selected.
        Bound to SelectedMinutes, typing "15" on the way to "150" lit the
        15-minute preset and WPF's radio group unchecked Custom mid-keystroke.
        """
        view = (Path(DESKTOP_DIR) / "Views" / "TodayView.xaml").read_text(encoding="utf-8")
        assert "{Binding SelectedMinutes, Converter={StaticResource IntEq}" not in view
        assert view.count("{Binding PresetMinutes, Converter={StaticResource IntEq}") == 5


class TestCustomSprintLengthBehaviour:
    """
    Merge review of the first draft found: typing a value never saved it
    (only clicking the radio did), an out-of-range value silently kept the
    previous length, and Start stayed enabled. These drive the real window.
    """

    @pytest.mark.ui
    def test_typing_a_custom_length_sets_saves_and_validates(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.click("SprintLength_Custom")
        assert fresh_app.exists("CustomMinutesInput", timeout=3)

        fresh_app.set_text("CustomMinutesInput", "150")
        time.sleep(0.5)
        assert fresh_app.sprint_timer() == "150:00", "the typed length didn't become the sprint length"
        assert verify.read_settings().get("LastCustomSprintMinutes") == 150, \
            "the typed length was not saved"
        assert fresh_app.is_control_enabled("StartSprintButton")

        fresh_app.set_text("CustomMinutesInput", "300")
        time.sleep(0.5)
        assert fresh_app.exists("CustomMinutesError", timeout=3), "no message for an out-of-range value"
        assert fresh_app.sprint_timer() == "150:00", "an invalid value changed the sprint length"
        assert not fresh_app.is_control_enabled("StartSprintButton"), \
            "Start must be disabled while the custom value is invalid"
        assert verify.read_settings().get("LastCustomSprintMinutes") == 150

        fresh_app.set_text("CustomMinutesInput", "abc")
        time.sleep(0.5)
        assert fresh_app.exists("CustomMinutesError", timeout=3)
        assert not fresh_app.is_control_enabled("StartSprintButton")

        # A preset click leaves custom mode and takes over cleanly.
        fresh_app.click("SprintLength_25")
        time.sleep(0.5)
        assert fresh_app.sprint_timer() == "25:00"
        assert not fresh_app.exists("CustomMinutesInput", timeout=1)
        assert fresh_app.is_control_enabled("StartSprintButton")


# ============ the per-app switch must not unlock a Sealed blocklist (roadmap 2.4)

# ============================ sprint summary card (F12)

class TestSprintSummaryCard:
    """The post-sprint card must appear and disappear with the journal prompt."""


    def test_the_abandoned_wording_stays_neutral(self):
        viewmodel = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert "It'll recover." in viewmodel
        assert "No distractions caught" in viewmodel


# ============================ sprint intention (F13)

class TestSummaryCardSeesTheSettledStreak:
    """
    F12's card shows the streak; F15 is what advances it. They were built
    separately, and the card was filled in before DailyGoal.Settle ran — so on
    the day a streak started, the line was collapsed and the person who had
    just earned "Day 1" saw a card with no streak on it.
    """

    VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"

    def test_stats_are_refreshed_before_the_card_is_built(self):
        source = self.VM.read_text(encoding="utf-8")
        end_sprint = source.split("_main.Blocker.StopEnforcing();", 1)[1]
        end_sprint = end_sprint.split("private void UpdateSummaryCard", 1)[0]

        refresh = end_sprint.find("RefreshStats();")
        card = end_sprint.find("UpdateSummaryCard(")
        assert refresh != -1, "EndSprint no longer refreshes stats"
        assert card != -1, "EndSprint no longer builds the summary card"
        assert refresh < card, (
            "the summary card is built before RefreshStats, so it reads a "
            "CurrentStreak that DailyGoal.Settle has not updated yet"
        )

    def test_the_streak_line_is_still_conditional(self):
        """
        Hiding the line at zero is right — "Day 0" is not a thing. The bug was
        the value being stale, not the condition.
        """
        source = self.VM.read_text(encoding="utf-8")
        assert "SummaryStreakVisible = S.CurrentStreak > 0;" in source

    def test_the_move_left_cancel_alone_and_refreshed_once(self):
        """
        The first version of this fix deleted the identical RefreshStats line
        in CancelSprint instead of EndSprint's later one, so a cancel stopped
        refreshing and a finished sprint refreshed twice.
        """
        source = self.VM.read_text(encoding="utf-8")
        cancel = source.split("private void CancelSprint()", 1)[1].split("\n    }", 1)[0]
        end = source.split("private void EndSprint(", 1)[1].split("private void UpdateSummaryCard", 1)[0]
        assert "RefreshStats();" in cancel, "CancelSprint no longer refreshes stats"
        assert end.count("RefreshStats();") == 1, "EndSprint should refresh stats exactly once"


class TestSprintIntentionGuard:
    """F13: the intention input, the ring line and the card line stay wired."""

    XAML = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"
    VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"

    def test_the_input_is_optional_and_locked_while_the_sprint_runs(self):
        view = self.XAML.read_text(encoding="utf-8")
        section = view[view.find("intention (F13)"):view.find("sprint summary")]
        assert 'AutomationProperties.AutomationId="IntentionInput"' in section
        assert 'IsEnabled="{Binding IsRunning, Converter={StaticResource InvBool}}"' in section

    def test_the_ring_and_the_card_each_show_the_intention(self):
        view = self.XAML.read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="SprintIntentionText"' in view
        card = view[view.find("sprint summary"):]
        card = card[:card.find("journal prompt")]
        assert 'AutomationProperties.AutomationId="SummaryIntentionText"' in card
        assert "SummaryIntentionVisible" in card

    def test_a_long_intention_cannot_break_the_timer_ring(self):
        # A long line wrapped to five lines inside the ring and pushed the
        # buttons down: the caption style wraps, so trimming never applied.
        view = self.XAML.read_text(encoding="utf-8")
        section = view[view.find("intention (F13)"):view.find("sprint summary")]
        assert 'MaxLength="80"' in section, "the input must cap what can be typed"

        viewmodel = self.VM.read_text(encoding="utf-8")
        assert "public const int MaxIntentionLength = 80;" in viewmodel
        assert "capped[..MaxIntentionLength]" in viewmodel, \
            "the cap must hold for pasted and programmatically set text too"

        ring = view[:view.find("SPRINT LENGTH")]
        line = ring[ring.find('AutomationId="SprintIntentionText"') - 600:]
        assert 'TextWrapping="NoWrap"' in line and 'TextTrimming="CharacterEllipsis"' in line, \
            "the line under the timer must stay on one line"

    def test_the_journal_prompt_title_is_bound_not_static(self):
        view = self.XAML.read_text(encoding="utf-8")
        journal = view[view.find("journal prompt"):]
        assert "JournalPromptTitle" in journal
        assert 'Text="What moved?"' not in journal, \
            "the prompt title must come from the viewmodel so it can repeat the intention"

    def test_cancelling_a_sprint_clears_the_intention_input(self):
        viewmodel = self.VM.read_text(encoding="utf-8")
        cancel = viewmodel[viewmodel.find("private void CancelSprint"):]
        cancel = cancel[:cancel.find("// ---------------------------------------------------------------- timer")]
        assert 'IntentionText = ""' in cancel, \
            "cancelling must clear the input so a stale intention is not captured by the next sprint"


class TestDistractionCountIsPerApp:
    """
    #138: "Distractions blocked" counts apps, not processes.

    The bug was invisible until a real multi-process app was put in front of
    the blocker — Steam runs seven, and closing it once read as seven
    distractions. The behaviour is covered end to end in tier 3; these guard
    the two halves that are easy to undo by accident.
    """

    SERVICE = Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs"

    def test_every_process_is_still_closed(self):
        """
        The dedupe covers *reporting*, never enforcement. An app whose helper
        survives because the count said "already seen" would be a far worse bug
        than the one being fixed.

        F7 moved the sweep from per-process to per-app, so this no longer reads
        as an ordering: enforcement now acts on the whole group at once, and
        what matters is that no kill sits behind the first-sighting check.
        """
        source = self.SERVICE.read_text(encoding="utf-8")
        body = source.split("private void Tick", 1)[1]
        for call in ("KillAll(processes, shield);",):
            for fragment in body.split(call)[:-1]:
                tail = fragment.rsplit("\n", 3)[-3:]
                assert not any("if (firstSighting)" in line for line in tail), (
                    "a kill must never be guarded by the first-sighting check, "
                    "or a second process of an already-counted app would survive"
                )
        assert "KillAll(processes, shield);" in body

    def test_reporting_is_what_the_first_sighting_check_guards(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        body = source.split("private void Tick", 1)[1]
        assert "if (firstSighting) Report(" in body, (
            "the first-sighting check exists to deduplicate reporting"
        )

    def test_an_app_that_goes_away_can_count_again(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        assert "_present.IntersectWith(running.Keys)" in source, (
            "entries with nothing running must be forgotten, or reopening a "
            "blocked app would never count as a fresh distraction"
        )

    def test_the_counter_is_reset_when_enforcement_starts_and_stops(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        for method in ("BeginEnforcing", "StopEnforcing"):
            body = source.split(f"public void {method}(", 1)[1]
            body = body.split("    }", 1)[0]
            assert "_present.Clear();" in body, f"{method} must clear the seen set"


class TestResumingDoesNotCreditTimeFlowShieldWasClosed:
    """
    #198. F3 records a sprint whose time ran out while Basalt was closed as
    finished only if Basalt was watching for at least half of it -- but
    Decide measured that as LastSeenUtc minus StartedUtc, and
    ResumeInterruptedSprint refreshes LastSeenUtc. Reopening the app for one
    second near the end of a 60-minute sprint therefore counted all 60 minutes
    as watched: the sprint was recorded Completed, took +24 momentum and a
    streak day, having enforced nothing. RunningSprint now carries the watched
    total itself, added to on each heartbeat and deliberately not across the gap
    a resume spans.
    """

    SETTINGS = DESKTOP / "Models" / "AppSettings.cs"
    VM = DESKTOP / "ViewModels" / "TodayViewModel.cs"

    def _decide(self, source: str) -> str:
        return source.split("public SprintResume Decide(", 1)[1].split("\n    }", 1)[0]

    def test_the_decision_reads_an_accumulated_total(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        decide = self._decide(source)
        # Since #203 the preference lives in WatchedSoFar, which every
        # judgement of watched time reads; Decide must go through it.
        so_far = source.split("public double WatchedSoFar", 1)[1].split(";", 1)[0]
        assert "WatchedSoFar" in decide and "WatchedMinutes ??" in so_far, (
            "Decide must prefer the accumulated watched time over the two-timestamp "
            "estimate a resume invalidates"
        )
        assert "CompletedIfWatchedFraction" in decide, "the half-watched bar itself is unchanged"

    def test_the_pre_fix_decision_is_rejected(self):
        decide = self._decide(
            "    public SprintResume Decide(DateTime nowUtc)\n"
            "    {\n"
            "        if (PlannedMinutes <= 0) return SprintResume.Discard;\n"
            "        if (nowUtc < EndsUtc) return SprintResume.Resume;\n"
            "        var watched = (Min(LastSeenUtc, EndsUtc) - StartedUtc).TotalMinutes;\n"
            "        return watched >= PlannedMinutes * CompletedIfWatchedFraction\n"
            "            ? SprintResume.RecordCompleted\n"
            "            : SprintResume.RecordInterrupted;\n"
            "    }\n"
        )
        assert "WatchedMinutes" not in decide

    def test_old_settings_files_still_load(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        assert "public double? WatchedMinutes { get; set; }" in source, (
            "nullable, so a settings file written before this field falls back to "
            "the old estimate instead of being judged as never watched"
        )

    def test_only_the_heartbeat_adds_to_it(self):
        vm = self.VM.read_text(encoding="utf-8")
        assert "NoteStillWatching(now, WatchedStretchCap)" in vm, (
            "the heartbeat is the one place that records another watched stretch"
        )
        resume = vm.split("case SprintResume.Resume:", 1)[1].split("break;", 1)[0]
        assert "saved.LastSeenUtc = now;" in resume
        assert "NoteStillWatching" not in resume, (
            "resuming must not credit the sprint with the time Basalt was closed "
            "-- that is the whole bug"
        )

    def test_a_suspended_machine_cannot_inflate_it(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        body = source.split("public void NoteStillWatching(", 1)[1].split("\n    }", 1)[0]
        assert "Min(stretch, cap)" in body, (
            "a DispatcherTimer does not tick while the machine sleeps, so an "
            "uncapped gap would credit time nothing was enforced for"
        )
        vm = self.VM.read_text(encoding="utf-8")
        assert "WatchedStretchCap = HeartbeatInterval * 2" in vm


class TestTimeUpAfterSleepUsesWatchedTime:
    """A lid-closed gap must not turn an expired sprint into full credit."""

    VM = DESKTOP / "ViewModels" / "TodayViewModel.cs"
    SETTINGS = DESKTOP / "Models" / "AppSettings.cs"

    def _block(self, source: str, marker: str) -> str:
        start = source.find(marker)
        assert start >= 0, f"could not find C# block starting at {marker!r}"
        opening = source.find("{", start)
        assert opening >= 0, f"could not find the opening brace for {marker!r}"
        depth = 0
        for index in range(opening, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[opening + 1:index]
        assert False, f"could not find the closing brace for {marker!r}"

    def test_time_up_notes_the_final_stretch_and_uses_the_active_sprint_decision(self):
        source = self.VM.read_text(encoding="utf-8")
        tick = self._block(source, "private void OnTick()")
        time_up = self._block(tick, "if (remaining <= TimeSpan.Zero)")
        note = time_up.find("NoteStillWatching(")
        decide = time_up.find(".Decide(now)")
        end = time_up.find("EndSprint(")
        assert note >= 0 and decide >= 0 and end >= 0 and note < decide < end, (
            "when time is up, OnTick must first cap and record the final watched "
            "stretch, then consult ActiveSprint.Decide(now), before ending the "
            "sprint; a sleeping PC or clock jump must not count the gap"
        )
        assert "WatchedStretchCap" in time_up[note:decide], (
            "the final stretch after the lid-closed gap must use the same watched-time cap"
        )
        assert "RecordInterrupted" in time_up and "interrupted: true" in time_up, (
            "a time-up decision below the watched fraction must end as interrupted"
        )
        assert "EndSprint(completed: true)" in time_up, (
            "a time-up decision at or above the watched fraction must still complete normally"
        )

    def test_interrupted_end_records_interruption_without_credit_or_break(self):
        source = self.VM.read_text(encoding="utf-8")
        signature = "private void EndSprint("
        assert signature in source, "EndSprint was not found"
        end = self._block(source, signature)
        header = source[source.find(signature):source.find("{", source.find(signature))]
        assert "interrupted" in header, (
            "EndSprint must accept an interrupted flag so time-up under-watching "
            "can be recorded separately from a user ending early"
        )
        assert "_current.Interrupted = interrupted" in end, (
            "the session saved after the lid-closed case must carry Interrupted = true"
        )
        assert "ApplyMomentum" in end and re.search(
            r"if\s*\(\s*!interrupted\s*\)[^{;]*ApplyMomentum\s*\(", end
        ), "an under-watched sprint must skip momentum gain and ended-early decay"
        assert re.search(r"if\s*\(\s*!interrupted\s*\)[^{;]*OfferBreakIfEarned\s*\(", end), (
            "an interrupted sprint after sleep must not offer or start a break"
        )

    def test_running_sprint_decide_uses_watched_so_far_helper(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        decide = self._block(source, "public SprintResume Decide(")
        assert "WatchedSoFar" in decide and "WatchedMinutes ??" not in decide, (
            "RunningSprint.Decide must use the shared clamped WatchedSoFar helper"
        )

    def test_resume_seeds_legacy_watched_minutes_before_advancing_last_seen(self):
        source = self.VM.read_text(encoding="utf-8")
        resume = self._block(source, "public void ResumeInterruptedSprint(")
        branch = resume.split("case SprintResume.Resume:", 1)[1].split(
            "case SprintResume.RecordCompleted:", 1
        )[0]
        advance = branch.find("saved.LastSeenUtc = now")
        seed_region = branch[:advance] if advance >= 0 else ""
        assert advance >= 0 and "WatchedMinutes" in seed_region and "WatchedSoFar" in seed_region, (
            "the Resume branch must seed missing WatchedMinutes from WatchedSoFar "
            "before LastSeenUtc advances, preserving 1.0.8 legacy time"
        )

    def _helper_ends_an_interruption_at_watched_time(self):
        """Since #300 both ends are worked out by RunningSprint.RecordedEnd."""
        helper = self._block(self.SETTINGS.read_text(encoding="utf-8"),
                             "public static DateTime RecordedEnd(")
        assert re.search(
            r"if\s*\(\s*interrupted\s*\)\s*return\s+startedUtc\s*\+\s*"
            r"TimeSpan\.FromMinutes\s*\(\s*watchedMinutes\s*\)",
            helper,
        ), "an interrupted sprint must end at its start plus the minutes watched"

    def test_startup_interruption_ends_at_watched_time(self):
        source = self.VM.read_text(encoding="utf-8")
        resume = self._block(source, "public void ResumeInterruptedSprint(")
        branch = resume.split("case SprintResume.RecordCompleted:", 1)[1]
        assert re.search(
            r"EndedUtc\s*=\s*RunningSprint\.RecordedEnd\(\s*saved\.StartedUtc\s*,\s*saved\.EndsUtc\s*,\s*"
            r"saved\.WatchedSoFar\s*,\s*now\s*,\s*completed\s*,\s*interrupted:\s*!completed\s*\)",
            branch,
        ), (
            "startup recovery must use EndsUtc only for completed sprints and "
            "StartedUtc + WatchedSoFar for interrupted sprints"
        )
        self._helper_ends_an_interruption_at_watched_time()

    def test_interrupted_end_uses_clamped_time_and_notifies_cycle_clear(self):
        source = self.VM.read_text(encoding="utf-8")
        end = self._block(source, "private void EndSprint(")
        assert re.search(
            r"_current\.EndedUtc\s*=\s*RunningSprint\.RecordedEnd\(\s*_current\.StartedUtc\s*,\s*"
            r"_endsAtUtc\s*,\s*S\.ActiveSprint\?\.WatchedSoFar\s*\?\?\s*0\s*,[^;]*,\s*interrupted\s*\)",
            end,
        ), "EndSprint must timestamp an interruption from clamped ActiveSprint.WatchedSoFar"
        self._helper_ends_an_interruption_at_watched_time()
        cleared = end.find("_cycle = interrupted ? CycleState.Nothing")
        text_raise = end.find("Raise(nameof(CycleProgressText))", cleared)
        visible_raise = end.find("Raise(nameof(CycleProgressVisible))", cleared)
        assert cleared >= 0 and text_raise > cleared and visible_raise > cleared, (
            "clearing the cycle on an interrupted EndSprint must notify both cycle "
            "progress bindings because OfferBreakIfEarned is skipped"
        )


class TestShortSprintsCannotBuyCredit:
    """
    PR #230 review: --short-sprints makes any sprint run five seconds, and it is
    an ordinary command-line flag — nothing stops a customer passing it. As
    first written, EndSprint still recorded the sprint at its *planned* length
    and ran ApplyMomentum on it, so `FlowShield.exe --short-sprints` with a
    90-minute sprint selected bought 30 points of momentum, a streak day and a
    day's goal every five seconds.

    The rule it now follows is --expire-trial's: a test flag may take something
    away, never hand it out. A shortened sprint records nothing and moves no
    score, exactly like a sprint cancelled inside the grace period.

    Proven to fail first: deleting the `if (CycleState.SprintCountsAsProgress)`
    guard in EndSprint (going back to an unconditional Sessions.Add +
    ApplyMomentum) fails the second and third assertions below.
    """

    MODEL = Path(DESKTOP_DIR) / "Models" / "CycleState.cs"
    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    APP = Path(DESKTOP_DIR) / "App.xaml.cs"

    def vm(self) -> str:
        return self.TODAY_VM.read_text(encoding="utf-8")

    def test_the_flag_has_a_named_invariant_of_its_own(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "public static bool SprintCountsAsProgress => !UseShortSprints;" in source, \
            "the rule must be one readable line, not a condition spread through the view model"

    def test_a_shortened_sprint_is_never_recorded(self):
        end = self.vm().split("private void EndSprint(bool completed, bool interrupted = false)")[1].split(
            "\n    /// <summary>")[0]
        guard = end.split("if (CycleState.SprintCountsAsProgress)")
        assert len(guard) == 2, "EndSprint must gate the record on the flag's invariant"
        body = guard[1].split("\n        }")[0]
        assert "S.Sessions.Add(_current);" in body, \
            "the session record must sit inside the guard, not outside it"
        assert "ApplyMomentum(completed, _current);" in body, \
            "momentum must sit inside the guard too"

        # Nothing may add a session or score outside that guard.
        outside = guard[0] + guard[1].split("\n        }", 1)[1]
        for forbidden in ("S.Sessions.Add(", "ApplyMomentum("):
            assert forbidden not in outside, \
                f"{forbidden} outside the guard lets --short-sprints buy credit again"

    def test_the_resume_path_cannot_be_used_to_get_round_it(self):
        """The other place a sprint is recorded and scored (F3's resume)."""
        resume = self.vm().split("public void ResumeInterruptedSprint(")[1].split(
            "\n    private void OnTick()")[0]
        assert "if (CycleState.SprintCountsAsProgress)" in resume
        recorded = resume.split("if (CycleState.SprintCountsAsProgress)")[1].split(
            "\n                }")[0]
        assert "S.Sessions.Add(session);" in recorded
        assert "ApplyMomentum(completed: true, session);" in recorded

    def test_the_daily_goal_and_streak_are_reached_only_through_that_record(self):
        """
        DailyGoal counts S.Sessions, and the streak only moves inside
        ApplyMomentum — so gating those two is gating all three kinds of credit.
        Nothing else in the view model may touch the goal or the streak.
        """
        vm = self.vm()
        apply_momentum = vm.split("private void ApplyMomentum(")[1].split("\n    private ")[0]
        assert "DailyGoal.NoteProgress" in apply_momentum
        assert "S.MomentumScore" in apply_momentum

        # RefreshStats settles the streak for the day, which must stay a
        # read-only settle — it may not count a sprint that was never recorded.
        elsewhere = vm.replace(apply_momentum, "")
        assert "DailyGoal.NoteProgress" not in elsewhere, \
            "goal credit must have exactly one route, and it is the gated one"

    def test_the_flag_is_documented_as_test_only_where_it_is_read(self):
        app = self.APP.read_text(encoding="utf-8")
        block = app.split('"--short-sprints"')[1].split("\n        }")[0]
        assert "Models.CycleState.UseShortSprints = true;" in block
        assert "IsPro" not in block and "TrialStartedUtc" not in block, \
            "a launch flag must never grant a licence or a trial"


class TestACompletedSprintDoesNotCountTheSleep300:
    """
    #300. A DispatcherTimer does not tick while the PC sleeps, so the first
    tick after waking reaches OnTick's time-up branch with the nap behind it.
    Since #203 a sprint Basalt watched at least half of still finishes
    there, which is right -- but EndSprint stamped its end with DateTime.UtcNow,
    the moment of waking, and FocusSession.ActualMinutes is EndedUtc minus
    StartedUtc. Eight hours asleep became eight hours focused: on the summary
    card, the minutes goal and today's tile, History, the heatmap and the
    journal export. F3's startup path already ended a completed sprint at its
    planned end; both now go through RunningSprint.RecordedEnd.

    The cap is not tied to finishing. An End click already queued at wake
    can be handled before the sprint clock's first tick (Background priority
    until #319, Normal since), so an End click handled after waking but
    before that first tick ends the sprint early with now hours past its
    planned end; it is still recorded as ended early, momentum and all, but
    its minutes are capped the same way.
    """

    SETTINGS = DESKTOP / "Models" / "AppSettings.cs"
    VM = DESKTOP / "ViewModels" / "TodayViewModel.cs"

    # EndSprint's assignment as 1.0.9 shipped it, verbatim: proves the checker
    # below rejects it rather than passing by construction.
    PRE_FIX_END_SPRINT = (
        "        _current.EndedUtc = interrupted\n"
        "            ? _current.StartedUtc + TimeSpan.FromMinutes(S.ActiveSprint?.WatchedSoFar ?? 0)\n"
        "            : DateTime.UtcNow;\n"
    )

    @staticmethod
    def _code(source: str) -> str:
        """The source without its // comments, which describe the old behaviour."""
        return re.sub(r"(^|\s)//[^\n]*", r"\1", source)

    @staticmethod
    def _block(source: str, marker: str) -> str:
        start = source.find(marker)
        assert start >= 0, f"{marker!r} was not found; update this test"
        opening = source.find("{", start)
        depth = 0
        for index in range(opening, len(source)):
            depth += source[index] == "{"
            depth -= source[index] == "}"
            if depth == 0:
                return source[opening + 1:index]
        raise AssertionError(f"unbalanced braces after {marker!r}")

    def _problems(self, end_sprint: str) -> list[str]:
        """What is wrong with the end EndSprint records; empty when nothing is."""
        match = re.search(r"_current\.EndedUtc\s*=(.*?);", end_sprint, re.S)
        assert match, "EndSprint's EndedUtc assignment was not found; update this test"
        value = " ".join(match.group(1).split())
        call = re.search(r"RunningSprint\.RecordedEnd\(([^)]*)\)", value)
        outside = value.replace(call.group(0), "") if call else value

        problems = []
        if "DateTime.UtcNow" in outside:
            problems.append("the end is the bare DateTime.UtcNow, which after a sleep is the wake time")
        if call is None:
            problems.append("the end must come from RunningSprint.RecordedEnd")
        else:
            args = [arg.strip() for arg in call.group(1).split(",")]
            if args[1:2] != ["_endsAtUtc"]:
                problems.append(f"the planned end passed must be _endsAtUtc, not {args[1:2]}")
            if args[3:5] != ["DateTime.UtcNow", "completed"]:
                problems.append(f"now and completed must be passed as such, not {args[3:5]}")
        return problems

    def test_the_helper_caps_any_uninterrupted_end_at_the_planned_end(self):
        source = self._code(self.SETTINGS.read_text(encoding="utf-8"))
        assert re.search(
            r"public static DateTime RecordedEnd\(\s*DateTime startedUtc,\s*DateTime plannedEndUtc,\s*"
            r"double watchedMinutes,\s*DateTime nowUtc,\s*bool completed,\s*bool interrupted\)",
            source,
        ), "the call sites below are checked against this parameter order"
        helper = self._block(source, "public static DateTime RecordedEnd(")
        assert re.search(
            r"return\s+nowUtc\s*>\s*plannedEndUtc\s*\?\s*plannedEndUtc\s*:\s*nowUtc\s*;",
            helper,
        ), "any end but an interruption is now, and never after the planned end"

    def test_end_sprint_records_its_end_through_the_helper(self):
        end = self._block(self._code(self.VM.read_text(encoding="utf-8")), "private void EndSprint(")
        assert self._problems(end) == []

    def test_the_shipped_assignment_is_rejected(self):
        problems = self._problems(self.PRE_FIX_END_SPRINT)
        assert any("bare DateTime.UtcNow" in problem for problem in problems), problems


# ============ #284 — the lock screen waits for a resumed sprint or break

class TestLockScreenWaitsForResumedFocus:
    """
    A sprint or break saved while the trial was active and resumed after it
    expired was covered by the lock screen at once, while the blocker kept
    enforcing underneath. The cover now waits for focus and its summary prompt;
    IsLocked itself stays true so every refusal still holds.
    """

    DESKTOP = Path(DESKTOP_DIR)

    def _main(self) -> str:
        return (self.DESKTOP / "ViewModels" / "MainViewModel.cs").read_text(encoding="utf-8")

    def test_the_overlay_binds_to_the_new_property_not_the_refusal(self):
        xaml = (self.DESKTOP / "MainWindow.xaml").read_text(encoding="utf-8")
        panel = xaml.split('AutomationProperties.AutomationId="TrialEndedPanel"', 1)[0]
        assert 'Visibility="{Binding ShowLockScreen,' in panel.rsplit("<Border", 1)[1]

    def test_the_cover_waits_for_focus_and_the_summary(self):
        main = self._main()
        line = next(l for l in main.splitlines() if "public bool ShowLockScreen" in l)
        for part in ("IsLocked", "!IsFocusInProgress", "!Today.JournalPromptVisible"):
            assert part in line, f"ShowLockScreen must include {part}"

    def test_islocked_still_refuses_while_focus_is_under_way(self):
        main = self._main()
        assert "public bool IsLocked => !HasAccess;" in main, \
            "start and edit refusals read IsLocked; only the cover may wait"

    def test_the_cover_is_re_evaluated_when_focus_or_the_prompt_ends(self):
        main = self._main()
        changed = main.split("public void OnSprintStateChanged()", 1)[1].split("\n    }", 1)[0]
        assert "Raise(nameof(ShowLockScreen))" in changed
        assert "Raise(nameof(ShowLockScreen))" in main.split("public void OnTierChanged()", 1)[1].split("\n    }", 1)[0]
        today = (self.DESKTOP / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        setter = today.split("public bool JournalPromptVisible", 1)[1].split("private string _journalText", 1)[0]
        assert "_main.RefreshLockScreen()" in setter


class TestMilestoneCardClearsOnTheNextSprint:
    """#359 review: the F14 milestone card is cleared when the next sprint
    starts, with the summary card, instead of staying up while it runs (the
    setup column it sits in stays visible during a sprint)."""

    def test_begin_running_hides_the_milestone_card(self):
        today = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        begin = today.split("private void BeginRunning(")[1].split("\n    }\n")[0]
        assert "JournalPromptVisible = false;" in begin
        assert "MilestoneNoticeVisible = false;" in begin
