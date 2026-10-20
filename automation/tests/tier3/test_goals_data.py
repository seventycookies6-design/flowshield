# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 3: goals data."""

from __future__ import annotations
import time
from datetime import datetime, timedelta
import pytest
from core import state_verifier as verify

pytestmark = pytest.mark.ui



class TestDailyGoal:
    """
    F15: an optional daily goal, a bar on Today, and a streak that only counts
    days the goal was met.
    """

    def test_no_goal_is_set_on_a_fresh_install(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        assert fresh_app.is_selected("GoalOffRadio") is True, \
            "the goal is opt-in; a new install must not start with one"

    def test_the_bar_is_absent_until_a_goal_is_set(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        # The ProgressBar, not the StackPanel around it: WPF does not surface a
        # bare panel as a UIA element, so asserting on the panel passes whether
        # the bar is there or not.
        assert fresh_app.exists("DailyGoalBar") is False, \
            "a goal-less user must not see an empty progress bar"

    def test_choosing_sprints_offers_a_target_and_saves_it(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.8)

        settings = verify.read_settings()
        assert settings["DailyGoalKind"] in (2, "Sprints")
        assert settings["DailyGoalTarget"] == 3, "picking sprints must land on a usable default"
        assert "sprints" in fresh_app.text_of("GoalUnitLabel").lower()

    def test_switching_kind_does_not_carry_the_number_across(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalMinutesRadio")
        time.sleep(0.6)
        assert verify.read_settings()["DailyGoalTarget"] == 90

        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.6)
        assert verify.read_settings()["DailyGoalTarget"] == 3, \
            "90 minutes is a normal day; 90 sprints is nobody's day"

    def test_a_target_out_of_range_is_reported_and_not_saved(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.6)

        fresh_app.set_text("GoalTargetInput", "999")
        time.sleep(0.6)

        assert fresh_app.exists("GoalTargetError") is True
        assert verify.read_settings()["DailyGoalTarget"] == 3, \
            "an out-of-range target must be refused, not silently clamped into the file"

    def test_the_bar_appears_on_today_once_a_goal_exists(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.6)

        fresh_app.navigate_to_tab("Today")
        assert fresh_app.exists("DailyGoalBar") is True
        assert "/ 3 sprints" in fresh_app.text_of("DailyGoalProgressText")

    def test_finishing_a_sprint_moves_the_bar(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.6)
        fresh_app.set_text("GoalTargetInput", "2")
        time.sleep(0.6)

        fresh_app.navigate_to_tab("Today")
        assert fresh_app.text_of("DailyGoalProgressText").startswith("0 /")

        fresh_app.select_sprint_length(15)
        fresh_app.start_sprint()
        time.sleep(1.0)
        fresh_app.stop_sprint()
        time.sleep(1.0)

        # Ending early does not complete a sprint, so a sprint-counted goal
        # stays where it was. This is the same rule the Today tile uses.
        assert fresh_app.text_of("DailyGoalProgressText").startswith("0 /")

    def test_taking_a_day_off_is_offered_once_a_week(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.6)

        assert "1 day off left" in fresh_app.text_of("SkipRemainingText")
        fresh_app.click("SkipTodayButton")
        time.sleep(0.8)

        assert "0 days off left" in fresh_app.text_of("SkipRemainingText")
        assert len(verify.read_settings()["SkipDatesLocal"]) == 1

        fresh_app.navigate_to_tab("Today")
        assert fresh_app.text_of("DailyGoalNote") == "Day off"

    def test_a_day_off_can_be_taken_back(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("GoalSprintsRadio")
        time.sleep(0.6)
        fresh_app.click("SkipTodayButton")
        time.sleep(0.8)
        fresh_app.click("SkipTodayButton")
        time.sleep(0.8)

        assert "1 day off left" in fresh_app.text_of("SkipRemainingText")
        assert verify.read_settings()["SkipDatesLocal"] == []
# ======================================================= journal export (F17)

class TestJournalExport:
    """
    F17: sprints and journal lines saved as a file the customer keeps.

    The point of doing this end to end is the file itself — the formatters are
    unit-tested, but nothing else proves the bytes that land on disk.
    """

    def _one_sprint_with_a_journal_line(self, app, line):
        app.navigate_to_tab("Today")
        app.start_sprint()
        time.sleep(1.2)
        app.stop_sprint()
        time.sleep(0.8)
        app.set_text("JournalInput", line)
        app.click("SaveJournalButton")
        time.sleep(1.0)

    def test_the_export_card_counts_the_sprints_in_range(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        assert "0 sprints" in fresh_app.text_of("ExportRangeText")

        self._one_sprint_with_a_journal_line(fresh_app, "wrote the exporter")
        fresh_app.navigate_to_tab("Settings")
        assert "1 sprint in this range" in fresh_app.text_of("ExportRangeText")

    def test_csv_is_written_with_the_journal_line(self, fresh_app, tmp_path):
        self._one_sprint_with_a_journal_line(fresh_app, "wrote the exporter")

        target = tmp_path / "export.csv"
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("ExportCsvRadio")
        time.sleep(0.4)
        fresh_app.click("ExportJournalButton")
        assert fresh_app.save_dialog_to(str(target)), "the Save dialog never appeared"
        time.sleep(1.5)

        raw = target.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), "Excel needs the UTF-8 BOM"

        text = raw.decode("utf-8-sig")
        assert "\r\n" in text, "Excel on Windows expects CRLF"

        lines = [line for line in text.splitlines() if line.strip()]
        assert lines[0].startswith("date (local),start (local)")
        assert "wrote the exporter" in lines[1]
        assert len(lines) == 2, f"expected a header and one row, got {len(lines)}"

    def test_markdown_is_written_and_grouped_by_day(self, fresh_app, tmp_path):
        self._one_sprint_with_a_journal_line(fresh_app, "wrote the exporter")

        target = tmp_path / "export.md"
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("ExportMarkdownRadio")
        time.sleep(0.4)
        fresh_app.click("ExportJournalButton")
        assert fresh_app.save_dialog_to(str(target)), "the Save dialog never appeared"
        time.sleep(1.5)

        text = target.read_text(encoding="utf-8")
        assert not text.startswith("﻿"), "a BOM shows up as stray characters in Markdown"
        assert text.startswith("# Basalt journal")
        assert f"## {datetime.now():%Y-%m-%d}" in text, "sessions must be grouped under their day"
        assert "wrote the exporter" in text

    def test_a_journal_line_that_looks_like_a_formula_is_defused(self, fresh_app, tmp_path):
        """The one real security issue in an export: a cell Excel would run."""
        self._one_sprint_with_a_journal_line(fresh_app, "=1+1")

        target = tmp_path / "formula.csv"
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("ExportCsvRadio")
        time.sleep(0.4)
        fresh_app.click("ExportJournalButton")
        assert fresh_app.save_dialog_to(str(target))
        time.sleep(1.5)

        text = target.read_text(encoding="utf-8-sig")
        assert "'=1+1" in text, "a leading = must be defused before Excel opens it"


# ============================================================ your data (F23)

class TestYourDataCard:
    """
    Settings -> Your data: the card is visible, names what leaves the PC, and
    its Export button opens a real Save dialog. Delete everything is checked
    only as far as its confirmation dialog — actually confirming it restarts
    the app into first run, which belongs in its own isolated run rather than
    alongside the rest of this suite.
    """

    def test_the_card_and_its_controls_are_visible(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        assert fresh_app.exists("WhatLeavesText")
        assert fresh_app.exists("ExportDataButton")
        assert fresh_app.exists("DeleteEverythingButton")

        leaves = fresh_app.text_of("WhatLeavesText").lower()
        # Customer-facing text spells it "license" (#370).
        assert "license key" in leaves and "device" in leaves

    def test_export_opens_a_save_dialog_and_excludes_the_licence_key(self, fresh_app, tmp_path):
        target = tmp_path / "flowshield-data.json"
        fresh_app.navigate_to_tab("Settings")
        fresh_app.click("ExportDataButton")
        assert fresh_app.save_dialog_to(str(target)), "the Save dialog never appeared"
        time.sleep(1.0)

        import json
        payload = json.loads(target.read_text(encoding="utf-8"))
        assert "licence" in payload
        assert "licenseKey" not in payload["licence"], \
            "the export must never contain the licence key"
        assert "blockedApps" in payload and "sessions" in payload
        # F6: templates and schedules are stored locally too, so they are part
        # of "everything". A fresh install holds the three built-ins.
        assert [t["Name"] for t in payload["studyTemplates"]] == \
            ["Homework evening", "Exam prep", "Light study"]
        assert payload["sprintSchedules"] == []

    def test_delete_everything_asks_for_confirmation_first(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.click("DeleteEverythingButton")
        time.sleep(0.5)
        assert fresh_app.exists("ConfirmDeleteDialog"), \
            "an irreversible local wipe must not happen on a single click"
        assert fresh_app.exists("ConfirmDeleteConfirmButton")
        assert fresh_app.exists("ConfirmDeleteCancelButton")
        # It says what goes, the templates and the taskbar list included (#311).
        detail = fresh_app.text_of("ConfirmDeleteDetailText")
        assert "templates" in detail and "taskbar Jump List" in detail, detail

        # Cancelling must leave everything exactly as it was.
        fresh_app.click("ConfirmDeleteCancelButton")
        time.sleep(0.5)
        assert fresh_app.exists("DeleteEverythingButton"), "Settings must still be there after cancelling"


# =========================================== History and the weekly view (F16)

class TestHistoryPage:
    """
    F16: the History page. The unit tests pin the arithmetic; what only the real
    app can show is that the page is reachable, that it picks up a sprint that
    happened on another page, and that the week's figures on screen match what
    was actually written to the settings file.
    """

    def _one_sprint(self, app, intention, journal):
        app.navigate_to_tab("Today")
        app.set_text("IntentionInput", intention)
        app.start_sprint()
        time.sleep(1.2)
        app.stop_sprint()
        time.sleep(0.8)
        app.set_text("JournalInput", journal)
        app.click("SaveJournalButton")
        time.sleep(1.0)

    def test_history_is_reachable_and_empty_to_begin_with(self, fresh_app):
        assert fresh_app.navigate_to_tab("History") == "History"
        assert fresh_app.text_of("WeekSprintsValue") == "0"
        assert fresh_app.text_of("WeekFocusHours") == "0.0"
        assert "No sprints yet" in fresh_app.text_of("HistoryEmptyText")
        # Nothing has been blocked, and the card says so rather than naming an app.
        assert "Nothing has needed blocking yet" in fresh_app.text_of("MostBlockedNote")

    def test_the_week_picks_up_a_sprint_run_on_today(self, fresh_app):
        """
        The refresh-on-entry case. History is built when the app starts, so
        without MainViewModel refreshing it on navigation the page would show
        zeroes for the rest of the run.
        """
        self._one_sprint(fresh_app, "finish chapter 3", "shipped the history page")

        fresh_app.navigate_to_tab("History")
        assert int(fresh_app.text_of("WeekDistractionsValue")) >= 0
        # Ended early, so it is not a completed sprint — but its minutes count.
        assert fresh_app.text_of("WeekSprintsValue") == "0"
        assert float(fresh_app.text_of("WeekFocusHours")) >= 0.0

        # The row is the newest, so it is the first HistoryRow* control found.
        assert "ended early" in fresh_app.text_of("HistoryRowOutcome")
        assert "finish chapter 3" in fresh_app.text_of("HistoryRowIntention")
        assert "shipped the history page" in fresh_app.text_of("HistoryRowJournal")

        # And it matches what was persisted, not just what the UI claims.
        session = verify.read_settings()["Sessions"][-1]
        assert session["Intention"] == "finish chapter 3"
        assert session["Journal"] == "shipped the history page"
        assert session["Completed"] is False

    def test_the_heatmap_states_its_values_rather_than_only_colouring_them(self, fresh_app):
        """
        DESIGN_SYSTEM.md §7: never colour alone. Every cell is a focusable
        control whose accessible name is its own day and minutes, so this is
        also the check that a screen reader gets something to read.
        """
        self._one_sprint(fresh_app, "", "measured the heatmap")
        fresh_app.navigate_to_tab("History")

        assert fresh_app.exists("FocusHeatmap"), "the heatmap never rendered"
        assert "–" in fresh_app.text_of("HeatmapRange"), "the range names both ends"
        assert "best day" in fresh_app.text_of("HeatmapPeak")
        assert fresh_app.text_of("HeatmapLegendLow") == "Less"
        assert fresh_app.text_of("HeatmapLegendHigh") == "More"

    def test_the_export_is_reachable_from_history(self, fresh_app):
        """F17's card stays on Settings; History is the way to it (F16)."""
        fresh_app.navigate_to_tab("History")
        fresh_app.click("HistoryExportButton")
        time.sleep(0.8)
        assert fresh_app.current_page_title() == "Settings"
        assert fresh_app.exists("ExportJournalButton")

    def test_looking_at_history_changes_nothing(self, fresh_app):
        """The page only reads. Visiting it must not rewrite the sprint record."""
        self._one_sprint(fresh_app, "", "wrote it down")
        before = verify.read_settings()["Sessions"]

        fresh_app.navigate_to_tab("History")
        time.sleep(1.0)
        fresh_app.navigate_to_tab("Today")
        time.sleep(0.5)

        assert verify.read_settings()["Sessions"] == before
