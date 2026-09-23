"""
Tier 1 -- the real C# model code (1.0.10).

The tests here run DesktopApp/Models through `core.model_probe`, so the
answer comes from .NET rather than from a Python copy of the rule; only the
house-voice check reads the source instead. Kept apart from
test_tier1_unit.py so the two files can change independently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from config import SERVER_DIR
from core.model_probe import ProbeError, probe


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

    def test_normalize_gives_a_missing_id_a_new_one(self):
        out = probe({"cmd": "template-normalize", "template": {"Id": "", "Name": "A"}})
        assert len(out["template"]["Id"]) == 32 and out["changed"] is True


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
    ])
    def test_days(self, days, expected):
        assert probe({"cmd": "text-days", "days": days})["text"] == expected

    @pytest.mark.parametrize("start,now,expected", [
        ("2026-09-28T17:00:00", "2026-09-28T09:00:00", "Next: tonight 17:00 · Homework evening"),
        ("2026-09-28T09:00:00", "2026-09-28T07:00:00", "Next: today 09:00 · Homework evening"),
        ("2026-09-29T17:00:00", "2026-09-28T20:00:00", "Next: tomorrow 17:00 · Homework evening"),
        ("2026-10-01T17:00:00", "2026-09-28T20:00:00", "Next: Thu 17:00 · Homework evening"),
    ])
    def test_next_up(self, start, now, expected):
        out = probe({"cmd": "text-next-up", "name": "Homework evening", "start": start, "now": now})
        assert out["text"] == expected

    def test_the_copy_keeps_to_the_house_voice(self):
        """DESIGN_SYSTEM.md §9: no exclamation marks; ASCII only in C# literals (escape the rest)."""
        for name in ("ScheduleText.cs", "SprintSchedule.cs", "ScheduleMatcher.cs", "StudyTemplate.cs"):
            source = (Path(SERVER_DIR).parent / "DesktopApp" / "Models" / name).read_text(encoding="utf-8")
            for text in re.findall(r'"([^"]*)"', source):
                assert "!" not in text, f"exclamation mark in {name}: {text!r}"
                assert text.isascii(), f"non-ascii in {name}: {text!r}"


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
        source = (Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "MainViewModel.cs").read_text(encoding="utf-8")
        assert source.index("Settings.EnsureProfiles()") < source.index("Settings.EnsureTemplates()")
