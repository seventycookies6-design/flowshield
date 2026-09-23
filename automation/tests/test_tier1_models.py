"""
Tier 1 -- the real C# model code (1.0.10).

The tests here run DesktopApp/Models through `core.model_probe`, so the
answer comes from .NET rather than from a Python copy of the rule; only the
house-voice check reads the source instead. Kept apart from
test_tier1_unit.py so the two files can change independently.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from config import SERVER_DIR
from core import model_probe
from core.model_probe import ProbeError, probe

DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"


# ============================ the model probe: real C# from tier 1 (1.0.10)

class TestModelProbe:
    """
    Tier 1 mirrors C# rules in Python and pins the C# by source, because there
    is no dotnet test project. That can't prove the C# computes the answer,
    and for time zones .NET decides it, not Python. ModelProbe compiles
    DesktopApp/Models as it is and answers JSON, so these run the real code.
    """

    def test_the_probe_answers(self):
        assert probe({"cmd": "ping"}) == {"ok": True}

    def test_the_probe_runs_the_real_soft_overlay_policy(self):
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0},
            {"op": "show", "app": "Discord", "at": 2},
            {"op": "left"},
            {"op": "show", "app": "Discord", "at": 60},
        ]})
        assert out["results"] == [True, False, True, True]

    def test_an_unknown_command_is_an_error_not_a_silent_pass(self):
        with pytest.raises(ProbeError):
            probe({"cmd": "no-such-command"})

    # The harness itself: every way a probe can go wrong is a ProbeError that
    # names the command, and a broken Models folder is compiled once, not once
    # per test (up to 300 s each).

    def test_a_build_failure_is_remembered_not_rebuilt(self, monkeypatch):
        calls = []

        def failing_build(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 1, stdout="error CS0000: no", stderr="")

        monkeypatch.setattr(model_probe, "_build_outcome", None)
        monkeypatch.setattr(model_probe.shutil, "which", lambda name: "dotnet")
        monkeypatch.setattr(model_probe.subprocess, "run", failing_build)
        for _ in range(2):
            with pytest.raises(ProbeError, match="did not build"):
                model_probe.build()
        assert len(calls) == 1, "the second call must re-raise the first failure, not rebuild"

    def test_a_hung_probe_is_a_probe_error_that_names_the_command(self, monkeypatch):
        def hang(command, **kwargs):
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout", 0), output="half an answer")

        monkeypatch.setattr(model_probe, "_build_outcome", Path("ModelProbe.exe"))
        monkeypatch.setattr(model_probe.subprocess, "run", hang)
        with pytest.raises(ProbeError) as err:
            probe({"cmd": "ping"})
        assert "ping" in str(err.value) and "half an answer" in str(err.value)

    def test_an_answer_that_is_not_json_is_a_probe_error_not_a_decode_error(self, monkeypatch):
        def chatty(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, stdout="a stray WriteLine\n{}", stderr="")

        monkeypatch.setattr(model_probe, "_build_outcome", Path("ModelProbe.exe"))
        monkeypatch.setattr(model_probe.subprocess, "run", chatty)
        with pytest.raises(ProbeError) as err:
            probe({"cmd": "ping"})
        assert "ping" in str(err.value) and "stray WriteLine" in str(err.value)


# ============================================ F6: study templates (1.0.10)

class TestStudyTemplates:
    """F6: the three built-ins from the launch checklist, and a template can't hold nonsense."""

    def _builtins(self) -> dict:
        return {t["BuiltInKey"]: t for t in probe({"cmd": "template-builtins"})["templates"]}

    def test_three_built_ins_ship_with_the_checklist_values(self):
        b = self._builtins()
        assert set(b) == {"homework", "exam", "light"}
        hw, ex, li = b["homework"], b["exam"], b["light"]
        assert (hw["Name"], hw["SprintMinutes"], hw["Shield"], hw["CycleSprints"], hw["BreakMinutes"]) \
            == ("Homework evening", 45, 2, 3, 10)
        assert (ex["Name"], ex["SprintMinutes"], ex["Shield"], ex["CycleSprints"]) \
            == ("Exam prep", 90, 3, 0)
        assert (li["Name"], li["SprintMinutes"], li["Shield"], li["CycleSprints"], li["BreakMinutes"]) \
            == ("Light study", 25, 1, 0, 5)

    def test_built_ins_use_whichever_profile_is_active(self):
        assert all(t["ProfileId"] == "" for t in self._builtins().values())

    def test_each_call_hands_out_fresh_ids(self):
        first = {t["Id"] for t in self._builtins().values()}
        second = {t["Id"] for t in self._builtins().values()}
        assert len(first) == 3 and not first & second
        assert all(len(i) == 32 for i in first | second), "a built-in never arrives without an id"

    def test_the_length_bounds_are_todays_custom_length_bounds(self):
        """
        The comment on StudyTemplate's bounds says they match Today's custom
        sprint length; the numbers are declared twice, so pin them equal.
        (TodayViewModel.cs is the teammate's file this week, so no sharing yet.)
        """
        def const(path, name):
            match = re.search(rf"public const int {name} = (\d+);", path.read_text(encoding="utf-8"))
            assert match, f"{name} not found in {path.name}"
            return int(match.group(1))

        template, today = DESKTOP / "Models" / "StudyTemplate.cs", DESKTOP / "ViewModels" / "TodayViewModel.cs"
        assert const(template, "MinSprintMinutes") == const(today, "CustomMinMinutes")
        assert const(template, "MaxSprintMinutes") == const(today, "CustomMaxMinutes")

    @pytest.mark.parametrize("field,given,expected", [
        ("SprintMinutes", 2, 5),
        ("SprintMinutes", 500, 240),
        ("CycleSprints", 1, 0),
        ("CycleSprints", 7, 0),
        ("CycleSprints", 3, 3),
        ("BreakMinutes", 0, 1),
        ("BreakMinutes", 99, 60),
        ("Shield", 9, 2),
        ("Name", "   ", "Untitled template"),
        ("Name", "x" * 60, "x" * 40),
        ("Name", "  Mock exam  ", "Mock exam"),
        ("ProfileId", None, ""),
        ("BuiltInKey", None, ""),
    ])
    def test_normalize_clamps_every_field(self, field, given, expected):
        template = {"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2,
                    "CycleSprints": 0, "BreakMinutes": 5, "ProfileId": "", "BuiltInKey": ""}
        template[field] = given
        out = probe({"cmd": "template-normalize", "template": template})
        assert out["template"][field] == expected
        assert out["changed"] is (given != expected)

    @pytest.mark.parametrize("template", [{"Id": "", "Name": "A"}, {"Name": "A"}],
                             ids=["blank id", "no Id key"])
    def test_normalize_gives_a_missing_id_a_new_one_and_says_so(self, template):
        """Reported as a change, so the loader saves it: an id that isn't saved changes every launch."""
        out = probe({"cmd": "template-normalize", "template": template})
        assert len(out["template"]["Id"]) == 32 and out["changed"] is True

    def test_truncation_never_splits_an_emoji(self):
        """Cutting at 40 UTF-16 units would leave half a surrogate pair, saved as U+FFFD."""
        out = probe({"cmd": "template-normalize", "template": {"Id": "t1", "Name": "x" * 39 + "\U0001F600"}})
        assert out["template"]["Name"] == "x" * 39

    def test_is_built_in_is_safe_to_read_before_normalize(self):
        """A hand-edited "BuiltInKey": null must not crash whoever reads IsBuiltIn first."""
        out = probe({"cmd": "template-normalize", "template": {"Id": "t1", "Name": "A", "BuiltInKey": None}})
        assert out["is_built_in_before"] is False


# ================================= F6: schedules and when they start (1.0.10)

EASTERN = "Eastern Standard Time"   # Windows id; UTC-5 in winter, UTC-4 in summer
MON_THU = [1, 2, 3, 4]              # DayOfWeek: Sunday = 0 ... Saturday = 6


def schedule(days=MON_THU, minute=17 * 60, **extra) -> dict:
    return {"Id": "s1", "TemplateId": "t1", "Days": days, "StartMinuteOfDay": minute,
            "AskFirst": True, "Enabled": True, "SkippedDatesLocal": [], **extra}


class TestScheduleMatcher:
    """
    F6: when a schedule starts, computed by .NET's own time-zone rules.
    The dates are real: in 2026 US clocks go forward on Sunday 8 March and
    back on Sunday 1 November, and 28 September is a Monday.
    """

    def test_a_weeknight_schedule_starts_at_its_local_time(self):
        out = probe({"cmd": "schedule-start-on", "schedule": schedule(),
                     "date": "2026-09-28", "zone": EASTERN})
        assert out["utc"] == "2026-09-28T21:00:00Z"      # 17:00 EDT

    def test_a_day_that_is_not_chosen_has_no_start(self):
        out = probe({"cmd": "schedule-start-on", "schedule": schedule(),
                     "date": "2026-09-26", "zone": EASTERN})  # Saturday
        assert out["utc"] is None

    def test_the_day_is_the_local_one_even_when_utc_is_already_tomorrow(self):
        """Spec 3.2: a day-of-week change across midnight. 21:30 EDT Monday is 01:30 UTC Tuesday."""
        s = schedule(days=[1], minute=21 * 60 + 30)      # Mondays only
        out = probe({"cmd": "schedule-next", "schedule": s,
                     "after": "2026-09-28T12:00:00Z", "zone": EASTERN})
        assert out["utc"] == "2026-09-29T01:30:00Z"

    def test_spring_forward_starts_at_the_first_minute_that_exists(self):
        s = schedule(days=[0], minute=2 * 60 + 30)       # Sunday 02:30 never happens on 8 March
        out = probe({"cmd": "schedule-start-on", "schedule": s, "date": "2026-03-08", "zone": EASTERN})
        assert out["utc"] == "2026-03-08T07:00:00Z"      # 03:00 EDT

    def test_fall_back_starts_once_at_the_first_of_the_two(self):
        s = schedule(days=[0], minute=60 + 30)           # Sunday 01:30 happens twice on 1 November
        out = probe({"cmd": "schedule-start-on", "schedule": s, "date": "2026-11-01", "zone": EASTERN})
        assert out["utc"] == "2026-11-01T05:30:00Z"      # the EDT 01:30
        between = probe({"cmd": "schedule-between", "schedule": s, "zone": EASTERN,
                         "from": "2026-10-31T12:00:00Z", "to": "2026-11-02T12:00:00Z"})
        assert between["utc"] == ["2026-11-01T05:30:00Z"], "one start, not two"

    def test_next_start_skips_the_weekend(self):
        out = probe({"cmd": "schedule-next", "schedule": schedule(),
                     "after": "2026-09-25T12:00:00Z", "zone": EASTERN})  # Friday
        assert out["utc"] == "2026-09-28T21:00:00Z"

    def test_next_start_is_strictly_after_now(self):
        out = probe({"cmd": "schedule-next", "schedule": schedule(),
                     "after": "2026-09-28T21:00:00Z", "zone": EASTERN})
        assert out["utc"] == "2026-09-29T21:00:00Z"

    def test_starts_in_a_window_cover_every_chosen_day_once(self):
        out = probe({"cmd": "schedule-between", "schedule": schedule(), "zone": EASTERN,
                     "from": "2026-09-27T00:00:00Z", "to": "2026-10-01T00:00:00Z"})
        assert out["utc"] == ["2026-09-28T21:00:00Z", "2026-09-29T21:00:00Z",
                              "2026-09-30T21:00:00Z"]

    def test_no_days_means_never(self):
        out = probe({"cmd": "schedule-next", "schedule": schedule(days=[]),
                     "after": "2026-09-25T12:00:00Z", "zone": EASTERN})
        assert out["utc"] is None

    def test_an_unset_last_check_looks_back_a_week_at_most(self):
        """
        DateTime.MinValue is what an unset last check looks like. Nothing more
        than a week late is ever acted on, so the window is clamped to eight
        days rather than throwing, or walking every day since year one.
        """
        out = probe({"cmd": "schedule-between", "schedule": schedule(), "zone": EASTERN,
                     "from": "0001-01-01T00:00:00Z", "to": "2026-10-01T00:00:00Z"})
        assert out["utc"] == ["2026-09-23T21:00:00Z", "2026-09-24T21:00:00Z",
                              "2026-09-28T21:00:00Z", "2026-09-29T21:00:00Z",
                              "2026-09-30T21:00:00Z"]


class TestSprintScheduleSkips:
    """F6: Skip today, and a schedule can't hold nonsense."""

    def test_skip_today_is_remembered_for_that_date_only(self):
        out = probe({"cmd": "schedule-skip", "schedule": schedule(),
                     "skip": ["2026-09-28"], "query": ["2026-09-28", "2026-09-29"]})
        assert out["is_skipped"] == [True, False]

    def test_old_skips_are_pruned_after_fourteen_days(self):
        out = probe({"cmd": "schedule-skip", "schedule": schedule(),
                     "skip": ["2026-09-01", "2026-09-28"], "query": []})
        assert out["skipped"] == ["2026-09-28"]

    def test_the_skip_memory_keeps_fourteen_days_and_drops_fifteen(self):
        out = probe({"cmd": "schedule-skip", "schedule": schedule(),
                     "skip": ["2026-09-13", "2026-09-14", "2026-09-28"], "query": []})
        assert out["skipped"] == ["2026-09-14", "2026-09-28"]

    def test_a_skip_survives_the_file_whatever_the_time_zone_does(self):
        """
        A skip is a date, not an instant. Stored with an offset it would be
        converted at load, so after a westward zone change it would read as
        the day before. Round-trip through JSON as the settings file does.
        """
        out = probe({"cmd": "schedule-skip", "schedule": schedule(), "roundtrip": True,
                     "skip": ["2026-09-28"], "query": ["2026-09-28"]})
        assert out["is_skipped"] == [True]
        assert out["stored"] == ["2026-09-28T00:00:00"], "no offset, no Z: a plain local date"

    def test_normalize_gives_a_schedule_without_an_id_key_one_and_says_so(self):
        s = schedule()
        del s["Id"]
        out = probe({"cmd": "schedule-normalize", "schedule": s})
        assert len(out["schedule"]["Id"]) == 32 and out["changed"] is True

    @pytest.mark.parametrize("minute,expected", [(-5, 0), (24 * 60, 24 * 60 - 1), (600, 600)])
    def test_normalize_keeps_the_start_inside_the_day(self, minute, expected):
        out = probe({"cmd": "schedule-normalize", "schedule": schedule(minute=minute)})
        assert out["schedule"]["StartMinuteOfDay"] == expected
        assert out["changed"] is (minute != expected)

    def test_normalize_sorts_and_dedupes_days(self):
        out = probe({"cmd": "schedule-normalize", "schedule": schedule(days=[4, 1, 1, 9])})
        assert out["schedule"]["Days"] == [1, 4]
        assert out["changed"] is True

    @pytest.mark.parametrize("field,filled", [("TemplateId", ""), ("Days", []), ("SkippedDatesLocal", [])])
    def test_normalize_fills_in_a_null_from_a_hand_edited_file(self, field, filled):
        """The loader saves only when Normalize says something changed, so a null counts as a change."""
        out = probe({"cmd": "schedule-normalize", "schedule": schedule(**{field: None})})
        assert out["schedule"][field] == filled
        assert out["changed"] is True


class TestScheduleText:
    """F6: how a schedule reads on the Schedule page."""

    @pytest.mark.parametrize("days,expected", [
        ([1, 2, 3, 4, 5], "Weekdays"),
        ([0, 1, 2, 3, 4, 5, 6], "Every day"),
        ([6, 0], "Weekends"),
        ([1, 2, 3, 4], "Mon–Thu"),
        ([1, 3, 5], "Mon, Wed, Fri"),
        ([0], "Sun"),
        ([], "No days"),
        ([9], "No days"),    # not a DayOfWeek; a hand-edited file, before Normalize drops it
    ])
    def test_days(self, days, expected):
        assert probe({"cmd": "text-days", "days": days})["text"] == expected

    @pytest.mark.parametrize("start,now,expected", [
        ("2026-09-28T17:00:00", "2026-09-28T09:00:00", "Next: tonight 17:00 · Homework evening"),
        ("2026-09-28T09:00:00", "2026-09-28T07:00:00", "Next: today 09:00 · Homework evening"),
        ("2026-09-29T17:00:00", "2026-09-28T20:00:00", "Next: tomorrow 17:00 · Homework evening"),
        ("2026-10-01T17:00:00", "2026-09-28T20:00:00", "Next: Thu 17:00 · Homework evening"),
        # A Monday-only schedule seen on Monday after it ran: "Mon 17:00" would read as today.
        ("2026-10-05T17:00:00", "2026-09-28T18:00:00", "Next: next Mon 17:00 · Homework evening"),
        ("2026-10-08T17:00:00", "2026-09-28T18:00:00", "Next: next Thu 17:00 · Homework evening"),
        # A start already behind now (a clock set back) reads like today, not like a weekday.
        ("2026-09-27T17:00:00", "2026-09-28T09:00:00", "Next: tonight 17:00 · Homework evening"),
    ])
    def test_next_up(self, start, now, expected):
        out = probe({"cmd": "text-next-up", "name": "Homework evening", "start": start, "now": now})
        assert out["text"] == expected

    def test_the_copy_keeps_to_the_house_voice(self):
        """DESIGN_SYSTEM.md §9: no exclamation marks; ASCII only in C# literals (escape the rest)."""
        sources = [DESKTOP / "Models" / name
                   for name in ("ScheduleText.cs", "SprintSchedule.cs", "ScheduleMatcher.cs", "StudyTemplate.cs")]
        sources.append(DESKTOP / "ViewModels" / "ScheduleViewModel.cs")
        for path in sources:
            source = path.read_text(encoding="utf-8")
            for text in re.findall(r'"([^"]*)"', source):
                assert "!" not in text, f"exclamation mark in {path.name}: {text!r}"
                assert text.isascii(), f"non-ascii in {path.name}: {text!r}"

        # The page's own strings. Its range labels use an en dash on purpose
        # (the view model builds them), so only the exclamation rule applies.
        xaml = (DESKTOP / "Views" / "ScheduleView.xaml").read_text(encoding="utf-8")
        for text in re.findall(r'\b(?:Text|Content)="([^"]*)"', xaml):
            assert "!" not in text, f"exclamation mark in ScheduleView.xaml: {text!r}"


# ================== F6: templates and schedules in the settings file (1.0.10)

def settings_json(**fields) -> dict:
    """A settings file as 1.0.9 wrote it: two profiles, no Templates, Schedules or TemplatesSeeded."""
    base = {"Profiles": [{"Id": "p1", "Name": "School", "Apps": []},
                         {"Id": "p2", "Name": "Everything", "Apps": []}],
            "ActiveProfileId": "p1"}
    base.update(fields)
    return base


class TestTemplatesInSettings:
    """F6: templates and schedules live in the encrypted settings file."""

    def test_a_1_0_9_settings_file_gets_the_built_ins_once(self):
        out = probe({"cmd": "settings-ensure-templates", "settings": settings_json()})
        assert out["changed_first"] is True and out["changed_second"] is False
        assert out["templates"] == ["Homework evening", "Exam prep", "Light study"]
        assert out["seeded"] is True

    def test_deleting_every_template_does_not_bring_them_back(self):
        out = probe({"cmd": "settings-ensure-templates",
                     "settings": settings_json(Templates=[], TemplatesSeeded=True)})
        assert out["templates"] == [] and out["changed_first"] is False

    def test_the_seeded_mark_is_saved_with_the_file(self):
        """The next launch reads what this one saved: seed, save, delete them all, load again."""
        first = probe({"cmd": "settings-ensure-templates", "settings": settings_json()})
        saved = first["saved"]
        saved["Templates"] = []
        out = probe({"cmd": "settings-ensure-templates", "settings": saved})
        assert out["templates"] == [] and out["changed_first"] is False

    def test_a_schedule_whose_template_is_gone_is_removed_on_load(self):
        s = {"Id": "s1", "TemplateId": "missing", "Days": [1], "StartMinuteOfDay": 1020}
        out = probe({"cmd": "settings-ensure-templates",
                     "settings": settings_json(Templates=[], TemplatesSeeded=True, Schedules=[s])})
        assert out["schedules"] == [] and out["changed_first"] is True

    def test_load_repairs_a_template_and_a_schedule_out_of_range(self):
        t = {"Id": "t1", "Name": "Mine", "SprintMinutes": 500, "Shield": 2}
        s = {"Id": "s1", "TemplateId": "t1", "Days": [4, 1, 1], "StartMinuteOfDay": 1020}
        out = probe({"cmd": "settings-ensure-templates",
                     "settings": settings_json(Templates=[t], TemplatesSeeded=True, Schedules=[s])})
        assert out["changed_first"] is True and out["changed_second"] is False
        assert out["raw_templates"][0]["SprintMinutes"] == 240
        assert out["raw_schedules"][0]["Days"] == [1, 4]

    @pytest.mark.parametrize("field", ["Templates", "Schedules"])
    def test_a_null_list_from_a_hand_edited_file_counts_as_a_change(self, field):
        out = probe({"cmd": "settings-ensure-templates",
                     "settings": settings_json(TemplatesSeeded=True, **{field: None})})
        assert out["changed_first"] is True and out["changed_second"] is False

    def test_a_null_entry_in_either_list_is_dropped_not_fatal(self):
        """[null] in a hand-edited file used to throw inside the MainViewModel constructor."""
        t = {"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2}
        s = {"Id": "s1", "TemplateId": "t1", "Days": [1], "StartMinuteOfDay": 1020}
        out = probe({"cmd": "settings-ensure-templates",
                     "settings": settings_json(Templates=[None, t], TemplatesSeeded=True,
                                               Schedules=[None, s])})
        assert out["changed_first"] is True and out["changed_second"] is False
        assert out["templates"] == ["Mine"] and out["schedules"] == ["s1"]

    def test_records_without_an_id_key_get_ids_that_are_saved(self):
        """An id the loader doesn't save would be a new one every launch (and PR C keys on it)."""
        t1 = {"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2}
        t2 = {"Name": "Other", "SprintMinutes": 30, "Shield": 2}
        s = {"TemplateId": "t1", "Days": [1], "StartMinuteOfDay": 1020}
        out = probe({"cmd": "settings-ensure-templates",
                     "settings": settings_json(Templates=[t1, t2], TemplatesSeeded=True, Schedules=[s])})
        assert out["changed_first"] is True and out["changed_second"] is False
        assert len(out["raw_templates"][1]["Id"]) == 32
        assert len(out["raw_schedules"][0]["Id"]) == 32

    def test_seeding_does_not_duplicate_a_built_in_that_is_already_there(self):
        """A file with a built-in but no TemplatesSeeded mark (hand-edited, or half migrated)."""
        homework = {"Id": "h1", "Name": "Homework evening", "SprintMinutes": 45, "Shield": 2,
                    "CycleSprints": 3, "BreakMinutes": 10, "BuiltInKey": "homework"}
        out = probe({"cmd": "settings-ensure-templates",
                     "settings": settings_json(Templates=[homework], TemplatesSeeded=False)})
        assert out["templates"] == ["Homework evening", "Exam prep", "Light study"]
        assert out["seeded"] is True and out["changed_second"] is False

    def test_two_templates_with_one_name_are_told_apart_on_load(self):
        """The page and its AutomationIds go by name, so no two templates may share one."""
        a = {"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2}
        b = {"Id": "t2", "Name": "mine", "SprintMinutes": 45, "Shield": 2}
        out = probe({"cmd": "settings-ensure-templates",
                     "settings": settings_json(Templates=[a, b], TemplatesSeeded=True)})
        assert out["templates"] == ["Mine", "mine 2"], "the earlier one keeps its name"
        assert out["changed_first"] is True and out["changed_second"] is False

    @pytest.mark.parametrize("wanted,except_id,expected", [
        ("Mine", None, "Mine 3"),                  # "Mine" and "Mine 2" are both taken
        ("MINE", None, "MINE 3"),                  # case-insensitive, like profiles
        ("Mine 2", None, "Mine 2 2"),
        ("Fresh", None, "Fresh"),
        ("Mine", "t1", "Mine"),                    # renaming a template to its own name
        ("x" * 40, None, "x" * 38 + " 2"),         # the number fits inside the 40-character cap
    ], ids=["taken", "case", "the numbered one is taken", "free", "own name", "at the cap"])
    def test_unique_template_name(self, wanted, except_id, expected):
        templates = [{"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2},
                     {"Id": "t2", "Name": "Mine 2", "SprintMinutes": 30, "Shield": 2},
                     {"Id": "t3", "Name": "x" * 40, "SprintMinutes": 30, "Shield": 2}]
        out = probe({"cmd": "settings-unique-template-name", "wanted": wanted, "except_id": except_id,
                     "settings": settings_json(Templates=templates, TemplatesSeeded=True)})
        assert out["name"] == expected

    def test_deleting_a_template_deletes_its_schedules(self):
        t = {"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2}
        keep = {"Id": "s2", "TemplateId": "t2", "Days": [2], "StartMinuteOfDay": 600}
        gone = {"Id": "s1", "TemplateId": "t1", "Days": [1], "StartMinuteOfDay": 1020}
        t2 = {"Id": "t2", "Name": "Other", "SprintMinutes": 30, "Shield": 2}
        out = probe({"cmd": "settings-delete-template", "id": "t1",
                     "settings": settings_json(Templates=[t, t2], TemplatesSeeded=True,
                                               Schedules=[gone, keep])})
        assert out["used_by"] == ["s1"], "the confirmation names the schedules that go with it"
        assert out["removed"] == 1
        assert out["templates"] == ["Other"] and out["schedules"] == ["s2"]

    def test_deleting_an_unknown_template_changes_nothing(self):
        t = {"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2}
        s = {"Id": "s1", "TemplateId": "t1", "Days": [1], "StartMinuteOfDay": 1020}
        out = probe({"cmd": "settings-delete-template", "id": "nope",
                     "settings": settings_json(Templates=[t], TemplatesSeeded=True, Schedules=[s])})
        assert out["removed"] == 0
        assert out["templates"] == ["Mine"] and out["schedules"] == ["s1"]

    def test_restore_adds_only_the_missing_built_ins(self):
        first = probe({"cmd": "settings-ensure-templates", "settings": settings_json()})
        kept = [t for t in first["raw_templates"] if t["BuiltInKey"] != "exam"]
        out = probe({"cmd": "settings-restore-builtins",
                     "settings": settings_json(Templates=kept, TemplatesSeeded=True)})
        assert out["added"] == 1
        assert sorted(out["templates"]) == ["Exam prep", "Homework evening", "Light study"]

    def test_restore_leaves_the_users_own_templates_alone(self):
        mine = {"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2}
        out = probe({"cmd": "settings-restore-builtins",
                     "settings": settings_json(Templates=[mine], TemplatesSeeded=True)})
        assert out["added"] == 3
        assert out["templates"] == ["Mine", "Homework evening", "Exam prep", "Light study"]

    @pytest.mark.parametrize("profile_id,expected", [("p2", "Everything"), ("", "School"),
                                                     ("deleted", "School")])
    def test_a_template_uses_its_profile_or_the_active_one(self, profile_id, expected):
        t = {"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2, "ProfileId": profile_id}
        out = probe({"cmd": "settings-profile-for", "template_id": "t1",
                     "settings": settings_json(Templates=[t], TemplatesSeeded=True)})
        assert out["profile"] == expected

    def test_startup_ensures_templates_after_profiles(self):
        """Anchored on the if-statements, so a call left only in a comment can't satisfy it."""
        source = (DESKTOP / "ViewModels" / "MainViewModel.cs").read_text(encoding="utf-8")
        profiles, templates = "if (Settings.EnsureProfiles())", "if (Settings.EnsureTemplates())"
        assert profiles in source and templates in source
        assert source.index(profiles) < source.index(templates)


# ============================ Soft friction: tries, the wait, wording (1.0.10)

class TestSoftFriction:
    """
    1.0.10: the one sec study (PNAS 2023) found the 'don't open it' choice did
    the most and a wait helped; fixed friction fades within weeks. So: Close
    first, a wait before Allow that grows with each try, varied wording.
    """

    def test_tries_count_every_notice_this_sprint_across_apps(self):
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0}, {"op": "left"},
            {"op": "show", "app": "Steam", "at": 10}, {"op": "left"},
            {"op": "show", "app": "Discord", "at": 20},
            {"op": "tries"},
        ]})
        assert out["results"][-1] == 3

    @pytest.mark.parametrize("try_number,seconds", [(1, 5), (2, 10), (3, 20), (4, 30), (9, 30)])
    def test_the_wait_before_allow_grows(self, try_number, seconds):
        assert probe({"cmd": "soft-wait", "try": try_number})["seconds"] == seconds

    def test_short_timers_make_every_wait_one_second(self):
        assert probe({"cmd": "soft-wait", "try": 4, "short": True})["seconds"] == 1

    def test_close_and_back_to_work_count_as_turned_back_and_allow_does_not(self):
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0}, {"op": "close", "app": "Discord", "at": 1},
            {"op": "left"},
            {"op": "show", "app": "Steam", "at": 30}, {"op": "back", "app": "Steam", "at": 31},
            {"op": "left"},
            {"op": "show", "app": "Discord", "at": 60}, {"op": "allow", "app": "Discord", "at": 61},
            {"op": "turned"},
        ]})
        assert out["results"][-1] == 2

    def test_close_goes_quiet_like_back_to_work(self):
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0}, {"op": "close", "app": "Discord", "at": 0},
            {"op": "show", "app": "Discord", "at": 1}, {"op": "left"},
            {"op": "show", "app": "Discord", "at": 30},
        ]})
        assert out["results"][2] is False and out["results"][4] is True

    def test_a_new_sprint_starts_counting_again(self):
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0}, {"op": "back", "app": "Discord", "at": 0},
            {"op": "reset"}, {"op": "tries"}, {"op": "turned"},
        ]})
        assert out["results"][-2:] == [0, 0]

    @pytest.mark.parametrize("n,line", [(1, "1st try this sprint"), (2, "2nd try this sprint"),
                                        (3, "3rd try this sprint"), (4, "4th try this sprint"),
                                        (11, "11th try this sprint"), (12, "12th try this sprint"),
                                        (13, "13th try this sprint"), (21, "21st try this sprint"),
                                        (22, "22nd try this sprint")])
    def test_the_try_line(self, n, line):
        assert probe({"cmd": "soft-copy", "try": n})["try_line"] == line

    def test_the_first_sentence_is_the_design_systems_own_example(self):
        out = probe({"cmd": "soft-copy", "try": 1, "app": "Discord", "ends": "2026-09-28T17:45:00"})
        assert out["sentence"].startswith("Discord is on your blocklist until")

    def test_the_wording_varies_across_four_tries_and_then_repeats(self):
        sentences = [probe({"cmd": "soft-copy", "try": n, "app": "Discord",
                            "ends": "2026-09-28T17:45:00"})["sentence"] for n in range(1, 6)]
        assert len(set(sentences[:4])) == 4 and sentences[4] == sentences[0]
        assert all("Discord" in s or "this time" in s for s in sentences)

    @pytest.mark.parametrize("seconds,label", [(8, "Allow 5 minutes · 0:08"),
                                               (30, "Allow 5 minutes · 0:30"),
                                               (0, "Allow 5 minutes")])
    def test_the_allow_button_counts_down_in_text(self, seconds, label):
        assert probe({"cmd": "soft-copy", "try": 1, "allow_left": seconds})["allow_label"] == label

    def test_an_empty_intention_shows_nothing(self):
        assert probe({"cmd": "soft-copy", "try": 1, "intention": "  "})["intention"] == ""
        assert probe({"cmd": "soft-copy", "try": 1, "intention": "finish chapter 3"})["intention"] \
            == "You planned: finish chapter 3"
