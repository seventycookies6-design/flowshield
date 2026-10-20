# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 1: goals journal."""

from __future__ import annotations
from datetime import date, timedelta
from datetime import date
from pathlib import Path
import pytest
from config import SERVER_DIR
from ._helpers import DAY, GOAL_MINUTES, GOAL_SPRINTS, Goal, defuse, escape_csv, escape_markdown, suggested_name



class TestDailyGoalProgress:
    """F15: progress counts the right thing for each kind of goal."""

    def test_no_goal_means_no_progress_and_no_bar(self):
        g = Goal(sessions=[(DAY, 50, True)])
        assert not g.is_set()
        assert g.progress_on(DAY) == (0, 0)

    def test_a_zero_target_is_not_a_goal(self):
        g = Goal(kind=GOAL_MINUTES, target=0)
        assert not g.is_set(), "a kind without a target must not switch the feature on"

    def test_minutes_count_time_actually_focused(self):
        g = Goal(GOAL_MINUTES, 90, [(DAY, 25, True), (DAY, 20, False)])
        assert g.progress_on(DAY) == (45, 90)

    def test_minutes_include_a_sprint_ended_early(self):
        g = Goal(GOAL_MINUTES, 30, [(DAY, 30, False)])
        assert g.met_on(DAY), "those minutes happened, even though the sprint was abandoned"

    def test_sprints_count_completed_ones_only(self):
        g = Goal(GOAL_SPRINTS, 2, [(DAY, 25, True), (DAY, 25, False)])
        assert g.progress_on(DAY) == (1, 2)
        assert not g.met_on(DAY)

    def test_overshooting_still_counts_as_met(self):
        g = Goal(GOAL_SPRINTS, 2, [(DAY, 25, True)] * 5)
        assert g.met_on(DAY)

    def test_yesterdays_sessions_do_not_count_towards_today(self):
        g = Goal(GOAL_SPRINTS, 1, [(DAY - timedelta(days=1), 25, True)])
        assert not g.met_on(DAY)


class TestDailyGoalSkips:
    """F15: a planned day off, at most once in any seven days."""

    def test_one_skip_is_allowed(self):
        g = Goal(GOAL_SPRINTS, 2)
        assert g.can_skip(DAY)

    def test_a_second_skip_in_the_same_week_is_refused(self):
        g = Goal(GOAL_SPRINTS, 2, skips=[DAY - timedelta(days=2)])
        assert not g.can_skip(DAY), "the allowance is one in seven days"

    def test_the_window_is_rolling_not_a_calendar_week(self):
        g = Goal(GOAL_SPRINTS, 2, skips=[DAY - timedelta(days=6)])
        assert not g.can_skip(DAY), "six days ago is still inside the seven-day window"
        g2 = Goal(GOAL_SPRINTS, 2, skips=[DAY - timedelta(days=7)])
        assert g2.can_skip(DAY), "seven days ago has left the window"

    def test_a_day_cannot_be_skipped_twice(self):
        g = Goal(GOAL_SPRINTS, 2, skips=[DAY])
        assert not g.can_skip(DAY)

    def test_skipping_needs_a_goal(self):
        g = Goal()
        assert not g.can_skip(DAY), "a day off is meaningless without a goal to miss"


class TestDailyGoalStreak:
    """F15: the streak counts days that met the goal, and settles without a sprint."""

    def test_meeting_the_goal_counts_the_day(self):
        g = Goal(GOAL_SPRINTS, 1, [(DAY, 25, True)], settled=DAY - timedelta(days=1), streak=3)
        g.settle(DAY)
        assert g.streak == 4

    def test_falling_short_does_not_count_today_but_does_not_break_it_either(self):
        g = Goal(GOAL_SPRINTS, 3, [(DAY, 25, True)], settled=DAY - timedelta(days=1), streak=3)
        g.settle(DAY)
        assert g.streak == 3, "today is not over; a short day so far must not break the streak"

    def test_a_missed_yesterday_breaks_the_streak_with_no_sprint_to_notice(self):
        g = Goal(GOAL_SPRINTS, 1, [], settled=DAY - timedelta(days=3), streak=9)
        g.settle(DAY)
        assert g.streak == 0, "the whole point of settling: nothing ran on those days"

    def test_a_skipped_day_holds_the_streak_without_adding_to_it(self):
        g = Goal(GOAL_SPRINTS, 1, [], skips=[DAY - timedelta(days=1)],
                 settled=DAY - timedelta(days=2), streak=5)
        g.settle(DAY)
        assert g.streak == 5, "a day off keeps the streak; it is not a day of focus"

    def test_a_skip_wins_over_a_stray_sprint_on_the_same_day(self):
        g = Goal(GOAL_SPRINTS, 1, [(DAY, 25, True)], skips=[DAY])
        assert g.judge(DAY) == "skipped", \
            "otherwise a two-minute sprint on a rest day spends the skip for nothing"

    def test_settling_twice_changes_nothing(self):
        g = Goal(GOAL_SPRINTS, 1, [(DAY, 25, True)], settled=DAY - timedelta(days=1), streak=2)
        g.settle(DAY)
        first = g.streak
        g.settle(DAY)
        assert g.streak == first, "settle runs on launch, at midnight and after every sprint"

    def test_a_clock_moved_backwards_does_not_walk_backwards(self):
        g = Goal(GOAL_SPRINTS, 1, [], settled=DAY, streak=4)
        g.settle(DAY - timedelta(days=3))
        assert g.streak == 4, "a corrected clock must not silently destroy a streak"

    def test_without_a_goal_the_old_rule_still_applies(self):
        g = Goal(sessions=[(DAY, 5, True)], settled=DAY - timedelta(days=1), streak=2)
        g.settle(DAY)
        assert g.streak == 3, "no goal set: any completed sprint counts the day, as before"

    def test_without_a_goal_a_missed_day_still_breaks_it(self):
        g = Goal(sessions=[], settled=DAY - timedelta(days=2), streak=6)
        g.settle(DAY)
        assert g.streak == 0

    def test_a_day_already_settled_can_still_be_counted_when_the_goal_lands(self):
        """
        #194: RefreshStats settles today at launch, before the day's first
        sprint. Meeting the goal afterwards has to count that day.
        """
        g = Goal(GOAL_SPRINTS, 1, [], settled=DAY, streak=5)
        g.settle(DAY)                              # launch: nothing yet
        assert g.streak == 5
        g.sessions.append((DAY, 25, True))         # the day's sprint completes
        g.settle(DAY)
        assert g.streak == 6, "a settled day must still be able to join the streak"

    def test_a_day_is_counted_once_however_many_sprints_it_takes(self):
        g = Goal(GOAL_SPRINTS, 1, [(DAY, 25, True)], settled=DAY, streak=5)
        for _ in range(4):
            g.settle(DAY)
            g.sessions.append((DAY, 25, True))
        assert g.streak == 6, "the streak counts days, not sprints"

    def test_note_progress_reports_the_one_moment_the_goal_lands(self):
        g = Goal(GOAL_SPRINTS, 2, [(DAY, 25, True)], settled=DAY, streak=0)
        assert g.note_progress(DAY) is False, "one of two sprints is not a met goal"
        g.sessions.append((DAY, 25, True))
        assert g.note_progress(DAY) is True, "the toast fires on the sprint that meets it"
        g.sessions.append((DAY, 25, True))
        assert g.note_progress(DAY) is False, "and not again on every later sprint"
        assert g.streak == 1

    def test_a_first_run_takes_the_existing_streak_as_given(self):
        g = Goal(GOAL_SPRINTS, 1, [], streak=11, settled=None)
        g.settle(DAY)
        assert g.streak == 11, "an upgrade must not recompute history that is not in Sessions"
        assert g.settled == DAY


class TestDailyGoalSource:
    """The C# the mirror above stands in for."""

    MODEL = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "DailyGoal.cs"
    SETTINGS = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"
    TODAY_VM = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "TodayViewModel.cs"
    TODAY_XAML = Path(SERVER_DIR).parent / "DesktopApp" / "Views" / "TodayView.xaml"
    SETTINGS_XAML = Path(SERVER_DIR).parent / "DesktopApp" / "Views" / "SettingsView.xaml"

    def test_the_settings_carry_the_goal_and_its_bookkeeping(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        for field in ("DailyGoalKind", "DailyGoalTarget", "StreakSettledDayLocal",
                      "GoalMetDayLocal", "SkipDatesLocal"):
            assert field in source, f"AppSettings must persist {field}"

    def test_the_allowance_is_one_day_off_per_rolling_week(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "SkipsPerWeek = 1" in source
        assert "SkipWindowDays = 7" in source

    def test_the_streak_is_settled_rather_than_nudged(self):
        vm = self.TODAY_VM.read_text(encoding="utf-8")
        assert "DailyGoal.Settle" in vm, "RefreshStats must settle the streak"
        assert "DailyGoal.NoteProgress" in vm, "a finished sprint must settle the day"
        assert "gap switch" not in vm, "the old gap-based streak must be gone"

    def test_the_bar_is_hidden_when_no_goal_is_set(self):
        xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        # The panel carries no id of its own (#134): one on a layout panel is
        # not surfaced to UI Automation. Its children are the handles.
        assert 'AutomationProperties.AutomationId="DailyGoalPanel"' not in xaml
        assert 'AutomationProperties.AutomationId="DailyGoalProgressText"' in xaml
        assert "GoalVisible" in xaml, "the panel must bind its visibility to GoalVisible"

    def test_the_settings_page_offers_both_kinds_and_a_day_off(self):
        xaml = self.SETTINGS_XAML.read_text(encoding="utf-8")
        for automation_id in ("GoalOffRadio", "GoalMinutesRadio", "GoalSprintsRadio",
                              "GoalTargetInput", "SkipTodayButton"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml


class TestJournalExportFormulaInjection:
    """
    F17: a journal line is free text, and a spreadsheet runs a cell that starts
    with =, +, -, @, tab or carriage return. That is the one way an export can
    hurt the person who opens it.
    """

    @pytest.mark.parametrize("payload", [
        "=cmd|'/c calc'!A1",
        "+1+1",
        "-2+3",
        "@SUM(A1:A9)",
        "\tsneaky",
        "\rsneaky",
    ])
    def test_a_formula_is_defused(self, payload):
        assert defuse(payload).startswith("'"), payload

    def test_ordinary_text_is_left_alone(self):
        for safe in ("finished chapter 3", "10am standup", "a - b", "x = y"):
            assert defuse(safe) == safe, safe

    def test_defusing_happens_before_quoting(self):
        # Otherwise the apostrophe lands outside the quotes and does nothing.
        assert escape_csv('=HYPERLINK("http://x","click")').startswith('"\'=')

    def test_an_empty_cell_stays_empty(self):
        assert defuse("") == ""
        assert escape_csv("") == ""


class TestJournalExportCsv:
    """F17: the CSV has to survive journal lines that contain anything."""

    def test_a_comma_is_quoted(self):
        assert escape_csv("read, then wrote") == '"read, then wrote"'

    def test_a_quote_is_doubled(self):
        assert escape_csv('he said "no"') == '"he said ""no"""'

    def test_a_newline_is_quoted_not_stripped(self):
        assert escape_csv("line one\nline two") == '"line one\nline two"'

    def test_plain_text_is_not_quoted(self):
        assert escape_csv("shipped the parser") == "shipped the parser"


class TestJournalExportMarkdown:
    """F17: a journal line must not become document structure."""

    @pytest.mark.parametrize("payload", ["# done", "- fixed it", "* starred",
                                         "> quoted", "| table", "`code"])
    def test_structure_characters_are_escaped(self, payload):
        assert escape_markdown(payload).startswith("\\"), payload

    def test_a_newline_inside_a_journal_line_is_flattened(self):
        assert "\n" not in escape_markdown("first\nsecond")

    def test_ordinary_text_is_untouched(self):
        assert escape_markdown("wrote the export") == "wrote the export"


class TestJournalExportFileName:
    """F17: the file says what it is and what it covers."""

    def test_the_name_carries_both_dates(self):
        assert suggested_name(date(2026, 9, 1), date(2026, 9, 18), "csv") == \
            "Basalt journal 2026-09-01 to 2026-09-18.csv"

    def test_markdown_gets_the_md_extension(self):
        assert suggested_name(date(2026, 9, 1), date(2026, 9, 18), "md").endswith(".md")

    def test_a_backwards_range_is_put_in_order(self):
        assert suggested_name(date(2026, 9, 18), date(2026, 9, 1), "csv") == \
            "Basalt journal 2026-09-01 to 2026-09-18.csv"


class TestJournalExportSource:
    """The C# behind the mirrors above."""

    MODEL = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "JournalExport.cs"
    SERVICE = Path(SERVER_DIR).parent / "DesktopApp" / "Services" / "JournalExportService.cs"
    SETTINGS_XAML = Path(SERVER_DIR).parent / "DesktopApp" / "Views" / "SettingsView.xaml"

    def test_the_csv_names_the_outcome_not_just_completed(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert '"ended early"' in source and '"interrupted"' in source, \
            "completed=false alone hides giving up versus losing the sprint to a crash"

    def test_the_csv_is_written_with_a_bom_and_markdown_without(self):
        service = self.SERVICE.read_text(encoding="utf-8")
        assert "encoderShouldEmitUTF8Identifier: true" in service, \
            "Excel needs the BOM or it mangles accents and emoji"
        assert "encoderShouldEmitUTF8Identifier: false" in service, \
            "a BOM shows up as stray characters in Markdown renderers"

    def test_the_csv_uses_crlf(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert '"\\r\\n"' in source, "Excel on Windows expects CRLF"

    def test_dates_are_local_and_say_so(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "date (local)" in source and "start (local)" in source
        assert "ToLocalTime()" in source, \
            "the customer picked the dates off a local calendar"

    def test_the_export_only_writes_where_the_user_chose(self):
        service = self.SERVICE.read_text(encoding="utf-8")
        assert "File.WriteAllText(path" in service
        assert "GetTempPath" not in service and "Upload" not in service, \
            "nothing may leave the machine; the privacy policy says so"

    def test_settings_offers_a_range_a_format_and_a_button(self):
        xaml = self.SETTINGS_XAML.read_text(encoding="utf-8")
        for automation_id in ("ExportFromDate", "ExportToDate", "ExportCsvRadio",
                              "ExportMarkdownRadio", "ExportJournalButton"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml
