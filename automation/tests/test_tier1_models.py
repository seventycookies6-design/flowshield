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
from datetime import datetime, timedelta
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

    def test_skip_today_from_the_card_stores_a_plain_date_too(self):
        """
        Today's Skip today passes the start's local date, which carries
        Kind=Local (TimeZoneInfo.ConvertTimeFromUtc(..., Local), as
        DateTime.Today does). Stored as it came, the file would hold
        "2026-09-28T00:00:00-04:00": an instant, not a date.
        """
        out = probe({"cmd": "schedule-skip", "schedule": schedule(), "roundtrip": True,
                     "kind": "local", "skip": ["2026-09-28"], "query": ["2026-09-28"]})
        assert out["stored"] == ["2026-09-28T00:00:00"], "a Local date must lose its offset in the file"
        assert out["is_skipped"] == [True]

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
                   for name in ("ScheduleText.cs", "SprintSchedule.cs", "ScheduleMatcher.cs", "StudyTemplate.cs",
                                "SchedulePlanner.cs")]
        sources += [DESKTOP / "ViewModels" / "ScheduleViewModel.cs", DESKTOP / "Services" / "ScheduleService.cs"]
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


class TestSchedulePlanner:
    """F6: what the scheduler does on each tick. Pure, so the gaps can be tested."""

    Z = EASTERN

    def decide(self, schedules, last, now, shown=(), zone=None, short=False):
        return probe({"cmd": "schedule-decide", "schedules": schedules, "zone": zone or self.Z,
                      "last": last, "now": now, "shown": list(shown), "short": short})

    def test_heads_up_five_minutes_before(self):
        out = self.decide([schedule()], "2026-09-28T20:54:50Z", "2026-09-28T20:55:05Z")
        assert out["actions"] == [{"kind": "HeadsUp", "id": "s1", "start": "2026-09-28T21:00:00Z"}]

    def test_heads_up_only_once(self):
        out = self.decide([schedule()], "2026-09-28T20:55:05Z", "2026-09-28T20:55:20Z",
                          shown=["s1@2026-09-28T21:00:00Z"])
        assert out["actions"] == []

    def test_no_heads_up_when_ask_first_is_off(self):
        out = self.decide([schedule(AskFirst=False)], "2026-09-28T20:54:50Z", "2026-09-28T20:55:05Z")
        assert out["actions"] == []

    def test_start_at_the_time(self):
        out = self.decide([schedule()], "2026-09-28T20:59:50Z", "2026-09-28T21:00:05Z")
        assert [a["kind"] for a in out["actions"]] == ["Start"]

    def test_a_skipped_day_does_nothing(self):
        s = schedule(SkippedDatesLocal=["2026-09-28T00:00:00"])
        out = self.decide([s], "2026-09-28T20:54:50Z", "2026-09-28T21:00:05Z")
        assert out["actions"] == []

    def test_a_skipped_day_has_no_heads_up_either(self):
        s = schedule(SkippedDatesLocal=["2026-09-28T00:00:00"])
        out = self.decide([s], "2026-09-28T20:54:50Z", "2026-09-28T20:55:05Z")
        assert out["actions"] == []

    def test_a_disabled_schedule_does_nothing(self):
        out = self.decide([schedule(Enabled=False)], "2026-09-28T20:59:50Z", "2026-09-28T21:00:05Z")
        assert out["actions"] == []

    def test_waking_twenty_minutes_late_offers_never_starts(self):
        out = self.decide([schedule()], "2026-09-28T20:30:00Z", "2026-09-28T21:20:00Z")
        assert [a["kind"] for a in out["actions"]] == ["OfferMissed"]

    def test_waking_an_hour_late_does_nothing(self):
        out = self.decide([schedule()], "2026-09-28T20:30:00Z", "2026-09-28T22:00:00Z")
        assert out["actions"] == []

    def test_a_long_gap_offers_at_most_one_start(self):
        """Review focus 2: asleep over several scheduled starts is one offer, not a burst."""
        daily = schedule(days=[0, 1, 2, 3, 4, 5, 6], minute=21 * 60)  # 21:00 every day
        out = self.decide([daily], "2026-09-25T12:00:00Z", "2026-09-29T01:10:00Z")  # 21:10 EDT on the 28th
        assert [a["kind"] for a in out["actions"]] == ["OfferMissed"]
        assert out["actions"][0]["start"] == "2026-09-29T01:00:00Z"

    def test_one_offer_per_tick_across_schedules_the_latest_start(self):
        """Review focus 2 again, with two schedules missed in one gap."""
        early = schedule(Id="a", minute=17 * 60)          # 21:00Z
        later = schedule(Id="b", minute=17 * 60 + 10)     # 21:10Z
        out = self.decide([later, early], "2026-09-28T20:30:00Z", "2026-09-28T21:25:00Z")
        assert out["actions"] == [{"kind": "OfferMissed", "id": "b", "start": "2026-09-28T21:10:00Z"}]

    def test_two_schedules_at_the_same_minute_come_out_in_a_stable_order(self):
        """Review focus 3: the service starts the first and skips the second."""
        a = schedule(Id="a", TemplateId="t1")
        b = schedule(Id="b", TemplateId="t2")
        out = self.decide([b, a], "2026-09-28T20:59:50Z", "2026-09-28T21:00:05Z")
        assert [x["id"] for x in out["actions"]] == ["a", "b"]

    @pytest.mark.parametrize("new_zone", ["Pacific Standard Time", "GMT Standard Time"])
    def test_a_zone_change_between_ticks_replays_nothing(self, new_zone):
        """
        Every interval is in UTC, so a start already passed is never inside a
        later one, whatever the zone now says. The next tick counts from the
        last one, with no reset: westward (17:00 PDT is 00:00Z) or eastward
        (17:00 BST was 16:00Z), the 17:00 EDT start that just ran is not seen again.
        """
        ran = self.decide([schedule()], "2026-09-28T20:59:50Z", "2026-09-28T21:00:05Z")
        assert [a["kind"] for a in ran["actions"]] == ["Start"]
        after = self.decide([schedule()], "2026-09-28T21:00:05Z", "2026-09-28T21:00:20Z", zone=new_zone)
        assert after["actions"] == []

    def test_a_clock_set_forward_past_a_start_is_a_gap_like_sleep(self):
        """
        Review focus 2: a clock change is a gap, like sleep. Set forward from
        16:50 to 17:10 EDT, the next tick still counts from 16:50, so 17:00 is
        one missed offer, never a start. Windows also says "the clock changed"
        on resume and on its own time sync; the service no longer restarts its
        count then, which is what erased the sleep gap and lost starts.
        """
        before, tick = "2026-09-28T20:50:00Z", "2026-09-28T21:10:15Z"
        out = self.decide([schedule()], before, tick)
        assert out["actions"] == [{"kind": "OfferMissed", "id": "s1", "start": "2026-09-28T21:00:00Z"}]

    def test_a_start_seen_seconds_after_an_hour_asleep_is_offered_never_started(self):
        """
        Final review of PR C (R20): the PC slept from 16:00 and woke at
        17:00:30 with a 17:00 schedule. The start is 30 seconds old, which
        would count as on time on an ordinary tick, but nobody was here for
        the heads-up and the spec says never start after waking. A gap since
        the last tick makes every start inside it a miss.
        """
        out = self.decide([schedule()], "2026-09-28T20:00:00Z", "2026-09-28T21:00:30Z")
        assert out["actions"] == [{"kind": "OfferMissed", "id": "s1", "start": "2026-09-28T21:00:00Z"}]

    def test_an_ordinary_tick_starts_a_start_seconds_old(self):
        """The rule above must not touch a normal tick: 10 s since the last one, start 5 s old."""
        out = self.decide([schedule()], "2026-09-28T20:59:55Z", "2026-09-28T21:00:05Z")
        assert [a["kind"] for a in out["actions"]] == ["Start"]

    @pytest.mark.parametrize("last,kinds", [
        ("2026-09-28T20:59:30Z", ["Start"]),        # 59 s since the last tick: late, still a tick
        ("2026-09-28T20:59:28Z", ["OfferMissed"]),  # 61 s: a gap, so the start is only offered
    ])
    def test_a_tick_held_back_under_a_minute_still_starts(self, last, kinds):
        """
        #316: on the VM a busy UI thread held the 15 s tick back, and a
        scheduled start came 57 s late. Past OnTime (1 minute) the planner
        reads the stall as a gap and offers the start as missed instead. The
        rule stays; the timer's priority keeps real ticks inside it.
        """
        out = self.decide([schedule()], last, "2026-09-28T21:00:29Z")
        assert [a["kind"] for a in out["actions"]] == kinds

    def test_short_mode_a_gap_offers_a_start_seconds_old(self):
        """The same rule at --short-schedules' scale: 12 s since the last 1 s tick is a gap."""
        out = self.decide([schedule()], "2026-09-28T20:59:50Z", "2026-09-28T21:00:02Z", short=True)
        assert [a["kind"] for a in out["actions"]] == ["OfferMissed"]

    def test_short_schedules_shrink_every_window_and_the_tick(self):
        """
        Roomy enough for the UI suite to act (R20 polish): the heads-up card
        is up for 15 seconds, a missed start is offered for 30, and a tick
        that lands two seconds late on a busy UI thread still starts.
        """
        out = probe({"cmd": "schedule-windows", "short": True})
        assert out == {"lead": 15, "late": 30, "on_time": 3, "tick": 1}
        assert probe({"cmd": "schedule-windows", "short": False}) == \
            {"lead": 300, "late": 1800, "on_time": 60, "tick": 15}

    @pytest.mark.parametrize("short", [False, True])
    def test_every_rule_can_happen_in_both_modes(self, short):
        """
        With 15-second ticks and a 1-minute on-time window, --short-schedules'
        late window could never offer (anything within a minute started) and
        a lead shorter than a tick could be stepped over.
        """
        w = probe({"cmd": "schedule-windows", "short": short})
        assert w["tick"] < w["lead"], "some tick always lands inside the heads-up lead"
        assert w["tick"] < w["on_time"], "some tick always sees a start on time"
        assert w["on_time"] < w["late"], "a start seen late can be offered"

    @pytest.mark.parametrize("last,now,kinds", [
        ("2026-09-28T20:59:44Z", "2026-09-28T20:59:45Z", ["HeadsUp"]),      # 15 s ahead
        ("2026-09-28T20:59:43Z", "2026-09-28T20:59:44Z", []),               # 16 s ahead: not yet
        ("2026-09-28T20:59:59Z", "2026-09-28T21:00:01Z", ["Start"]),
        ("2026-09-28T20:59:59Z", "2026-09-28T21:00:05Z", ["OfferMissed"]),  # a 6 s gap: 5 s late
        ("2026-09-28T20:59:59Z", "2026-09-28T21:00:31Z", []),               # past the 30 s window
    ])
    def test_short_schedules_run_every_rule_in_seconds(self, last, now, kinds):
        out = self.decide([schedule()], last, now, shown=[], short=True)
        assert [a["kind"] for a in out["actions"]] == kinds

    # R21: a start missed while FlowShield was closed. The service saves the
    # time of its last check and counts from it on the next launch.

    def seed(self, last, now="2026-09-28T21:00:00Z"):
        return probe({"cmd": "schedule-seed", "last": last, "now": now})["seed"]

    def test_a_launch_counts_from_the_last_check_it_saved(self):
        assert self.seed("2026-09-28T20:50:00Z") == "2026-09-28T20:50:00Z"

    def test_a_first_launch_counts_from_now(self):
        assert self.seed(None) == "2026-09-28T21:00:00Z"

    def test_a_check_weeks_ago_is_clamped_to_the_look_back_limit(self):
        """StartsBetweenUtc clamps too; the seed says so in one place rather than walking a month."""
        assert self.seed("2026-08-01T12:00:00Z") == "2026-09-20T21:00:00Z"

    def test_a_check_in_the_future_counts_from_now(self):
        """A clock set back between launches: nothing between the two is passed time."""
        assert self.seed("2026-09-28T21:05:00Z") == "2026-09-28T21:00:00Z"

    def test_a_start_missed_while_closed_is_offered_on_launch(self):
        """The seed feeds Decide: closed at 16:50, launched at 17:10 EDT, the 17:00 start is one offer."""
        seed = self.seed("2026-09-28T20:50:00Z", now="2026-09-28T21:10:15Z")
        out = self.decide([schedule()], seed, "2026-09-28T21:10:15Z")
        assert out["actions"] == [{"kind": "OfferMissed", "id": "s1", "start": "2026-09-28T21:00:00Z"}]

    def test_a_start_handled_before_exit_is_not_offered_again(self):
        """The stamp is taken at the start of the tick that handled it, so the start is at or before it."""
        out = self.decide([schedule()], self.seed("2026-09-28T21:00:05Z", now="2026-09-28T21:10:00Z"),
                          "2026-09-28T21:10:00Z")
        assert out["actions"] == []

    # R23: a card does not go stale.

    @pytest.mark.parametrize("now,short,expired", [
        ("2026-09-28T21:29:59Z", False, False),
        ("2026-09-28T21:30:01Z", False, True),
        ("2026-09-28T21:00:29Z", True, False),
        ("2026-09-28T21:00:31Z", True, True),
    ])
    def test_a_card_expires_once_the_late_window_has_passed_its_start(self, now, short, expired):
        out = probe({"cmd": "schedule-card-expired", "start": "2026-09-28T21:00:00Z", "now": now, "short": short})
        assert out["expired"] is expired


class TestScheduleService:
    """
    F6: the timer around the planner. It runs on WPF's dispatcher, which the
    probe doesn't host, so these read its source, with comments stripped so a
    call left only in a comment can't satisfy them.
    """

    def code(self) -> str:
        source = (DESKTOP / "Services" / "ScheduleService.cs").read_text(encoding="utf-8")
        return "\n".join(line.split("//")[0] for line in source.splitlines())

    @staticmethod
    def body(code: str, signature: str) -> str:
        """One member, from its signature to the closing brace at member depth."""
        start = code.index(signature)
        return code[start:code.index("\n    }", start)]

    def test_it_follows_a_clock_or_time_zone_change(self):
        """.NET caches the local zone: without this the schedules keep the old zone's clock until a restart."""
        code = self.code()
        assert "SystemEvents.TimeChanged += OnTimeChanged;" in code
        assert "SystemEvents.TimeChanged -= OnTimeChanged;" in code, "Stop() lets go of the event"
        assert "TimeZoneInfo.ClearCachedData();" in self.body(code, "private void ClockChanged()")

    def test_a_clock_change_never_erases_the_gap(self):
        """
        Windows says the clock changed on resume from sleep and whenever its
        time sync steps the clock (seconds, several times a week). Restarting
        the count there erased the sleep gap, so the missed offer never came,
        and lost any start between the last tick and the step. Only Start()
        and a tick may move the count.
        """
        code = self.code()
        assert "_lastTickUtc" not in self.body(code, "private void ClockChanged()")
        rest = code
        for member in ("public void Start()", "public void Tick(DateTime nowUtc)"):
            rest = rest.replace(self.body(code, member), "")
        assert not re.search(r"_lastTickUtc\s*=(?!=)", rest), "the count moves only in Start() and Tick()"

    def test_the_tick_rate_follows_short_schedules(self):
        """A 15-second tick can't see --short-schedules' 5-second lead or 10-second window."""
        code = self.code()
        assert re.search(r"public static TimeSpan Interval\s*=>\s*SchedulePlanner\.TickInterval;", code)
        start = self.body(code, "public void Start()")
        assert "_timer.Interval = Interval;" in start, "read when the timer starts, after the flags are set"
        assert start.index("_timer.Interval = Interval;") < start.index("_timer.Start();")

    def test_every_tick_reads_the_zone_afresh(self):
        assert re.search(r"SchedulePlanner\.Decide\([^;]*TimeZoneInfo\.Local", self.code())

    def test_a_clock_set_back_counts_from_the_new_time(self):
        """Nothing between the new time and the last tick is read as passed time at once."""
        assert "if (nowUtc < _lastTickUtc) _lastTickUtc = nowUtc;" in self.code()

    def test_the_last_check_is_stamped_before_anything_is_raised(self):
        """
        R21: a start missed while FlowShield was closed is offered on launch.
        Every tick stamps its time on the settings first, so any save that
        follows (a scheduled start saves; exit saves) keeps it, and Start()
        counts from the stamp, clamped, instead of from now.
        """
        code = self.code()
        tick = self.body(code, "public void Tick(DateTime nowUtc)")
        assert "_settings.ScheduleLastCheckUtc = nowUtc;" in tick
        assert tick.index("_settings.ScheduleLastCheckUtc = nowUtc;") < tick.index("Action?.Invoke(this, action);")
        start = self.body(code, "public void Start()")
        assert "_lastTickUtc = SchedulePlanner.SeedLastTick(_settings.ScheduleLastCheckUtc, " in start

    def test_one_failing_handler_cannot_eat_a_tick(self):
        """
        _lastTickUtc has already moved on, so an action a throwing handler
        dropped would never be raised again, and the exception would reach
        the dispatcher's error dialog from a background tick.
        """
        tick = self.body(self.code(), "public void Tick(DateTime nowUtc)")
        guarded = tick[tick.index("try"):]
        assert "Action?.Invoke(this, action);" in guarded.split("catch", 1)[0]
        assert re.search(r"catch \(Exception ex\)\s*\{\s*Log\.Warn\(", guarded)
        warning = guarded.split("Log.Warn(", 1)[1].split(";", 1)[0]
        assert "action.Kind" in warning and "action.Schedule.Id" in warning, "name the schedule and the kind"

    def test_every_tick_is_announced_before_it_decides(self):
        """R23: the card's expiry is checked on each tick, whether or not anything is due."""
        tick = self.body(self.code(), "public void Tick(DateTime nowUtc)")
        assert "Ticked?.Invoke(this, nowUtc);" in tick
        assert tick.index("Ticked?.Invoke(this, nowUtc);") < tick.index("SchedulePlanner.Decide(")


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

    def test_a_restored_built_in_takes_a_number_when_its_name_is_taken(self):
        """
        Delete Exam prep, save your own "Exam prep", then Restore: the user's
        keeps its name and the built-in comes back as "Exam prep 2", so the
        names Today's chips and the page's ids are built from stay unique.
        """
        first = probe({"cmd": "settings-ensure-templates", "settings": settings_json()})
        kept = [t for t in first["raw_templates"] if t["BuiltInKey"] != "exam"]
        mine = {"Id": "t1", "Name": "Exam prep", "SprintMinutes": 60, "Shield": 2}
        out = probe({"cmd": "settings-restore-builtins",
                     "settings": settings_json(Templates=kept + [mine], TemplatesSeeded=True)})
        assert out["added"] == 1
        assert out["templates"] == ["Homework evening", "Light study", "Exam prep", "Exam prep 2"]

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


class TestATemplatesBreakRidesWithTheSprint:
    """
    F6: a sprint started from a template takes its breaks at the template's
    length, and a restart mid-cycle must not lose that. It is saved with the
    running sprint; a sprint saved by 1.0.9 has none and uses Settings.
    """

    SPRINT = {"StartedUtc": "2026-09-28T21:00:00Z", "PlannedMinutes": 45, "Shield": 2,
              "LastSeenUtc": "2026-09-28T21:00:00Z"}

    def test_the_templates_break_length_is_saved_with_the_running_sprint(self):
        sprint = dict(self.SPRINT, TemplateBreakMinutes=10)
        out = probe({"cmd": "settings-ensure-templates", "settings": settings_json(ActiveSprint=sprint)})
        assert out["saved"]["ActiveSprint"]["TemplateBreakMinutes"] == 10

    def test_a_sprint_saved_before_templates_uses_the_break_settings(self):
        out = probe({"cmd": "settings-ensure-templates", "settings": settings_json(ActiveSprint=self.SPRINT)})
        assert out["saved"]["ActiveSprint"]["TemplateBreakMinutes"] is None

    # A restart during a break inside a template cycle must keep the
    # template's breaks too (PR C polish, item 8), so the break carries it.

    BREAK = {"StartedUtc": "2026-09-28T21:45:00Z", "EndsUtc": "2026-09-28T21:55:00Z", "Minutes": 10,
             "SprintsPlanned": 3, "SprintsDone": 1}

    def test_the_templates_break_length_is_saved_with_the_running_break(self):
        saved = dict(self.BREAK, TemplateBreakMinutes=10)
        out = probe({"cmd": "settings-ensure-templates", "settings": settings_json(ActiveBreak=saved)})
        assert out["saved"]["ActiveBreak"]["TemplateBreakMinutes"] == 10

    def test_a_break_saved_before_templates_uses_the_break_settings(self):
        out = probe({"cmd": "settings-ensure-templates", "settings": settings_json(ActiveBreak=self.BREAK)})
        assert out["saved"]["ActiveBreak"]["TemplateBreakMinutes"] is None


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

    @pytest.mark.parametrize("try_number", [1, 4])
    def test_short_timers_make_every_wait_three_seconds(self, try_number):
        """
        Three, not one: long enough for the UI suite to see Allow disabled
        before the wait runs out (a UIA lookup costs most of a second), short
        enough that no test waits on it.
        """
        assert probe({"cmd": "soft-wait", "try": try_number, "short": True})["seconds"] == 3

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
        """
        A quick bounce out of the app and back inside the quiet window says
        nothing, as after Back to work; a later return is a fresh sighting.
        """
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0}, {"op": "close", "app": "Discord", "at": 0},
            {"op": "left"},
            {"op": "show", "app": "Discord", "at": 1}, {"op": "left"},
            {"op": "show", "app": "Discord", "at": 30},
        ]})
        assert out["results"][3] is False and out["results"][5] is True

    def test_close_keeps_the_notice_down_while_the_app_stays_in_front(self):
        """
        After Close the app may well stay in front: its own "save changes?"
        prompt is up, or it ignores the ask. Quietening it like Back to work
        put the full-screen notice back over that prompt five seconds later as
        a "2nd try". The sighting is answered, not cleared: nothing shows again
        until the app has left the foreground and come back.
        """
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0}, {"op": "close", "app": "Discord", "at": 0},
            {"op": "show", "app": "Discord", "at": 10},
            {"op": "left"},
            {"op": "show", "app": "Discord", "at": 11},
        ]})
        assert out["results"][2] is False, "the same sighting, long after the quiet window"
        assert out["results"][3] is False, "Close already took the notice down"
        assert out["results"][4] is True, "left and came back: a fresh sighting"

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
        # DESIGN_SYSTEM.md section 7: one sentence, and none of them ends in a
        # full stop, so a full stop in the middle is a second sentence.
        assert all(". " not in s and not s.endswith(".") for s in sentences), sentences

    @pytest.mark.parametrize("seconds,label", [(8, "Allow 5 minutes · 0:08"),
                                               (30, "Allow 5 minutes · 0:30"),
                                               (0, "Allow 5 minutes")])
    def test_the_allow_button_counts_down_in_text(self, seconds, label):
        assert probe({"cmd": "soft-copy", "try": 1, "allow_left": seconds})["allow_label"] == label

    def test_an_empty_intention_shows_nothing(self):
        assert probe({"cmd": "soft-copy", "try": 1, "intention": "  "})["intention"] == ""
        assert probe({"cmd": "soft-copy", "try": 1, "intention": "finish chapter 3"})["intention"] \
            == "You planned: finish chapter 3"

    def test_the_note_under_the_buttons_is_softs_promise(self):
        """One wording, read by the notice and the Settings caption alike."""
        assert probe({"cmd": "soft-copy", "try": 1})["close_note"] == "Nothing is closed unless you choose to."


# ============================= turned back, recorded and shown (1.0.10, 4.3)

def focus_session(started_utc: str, turned_back: int | None = None) -> dict:
    """A finished 25-minute Soft sprint as the settings file holds it."""
    ended = datetime.fromisoformat(started_utc.replace("Z", "+00:00")) + timedelta(minutes=25)
    session = {"StartedUtc": started_utc, "EndedUtc": ended.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "PlannedMinutes": 25, "Shield": 1, "Completed": True, "BlocksEnforced": 0}
    if turned_back is not None:
        session["TurnedBack"] = turned_back
    return session


class TestTurnedBack:
    """
    Spec 4.3: Close and Back to work on the Soft notice each count as one
    turned back. The count is saved with the sprint and History adds up the
    week's; which app it was is never recorded.
    """

    # Thursday 24 September 2026, local. Its week is Monday 21 to Sunday 27.
    # The sprints meant to fall in it start at noon or 15:00 UTC on the
    # Tuesday or Wednesday, which stay inside that week in every time zone,
    # so the answer doesn't depend on this PC's zone.
    NOW = "2026-09-24T12:00:00"

    def test_the_week_adds_up_every_sprints_turned_back(self):
        week = probe({"cmd": "history-week", "now": self.NOW, "sessions": [
            focus_session("2026-09-22T12:00:00Z", turned_back=2),
            focus_session("2026-09-23T12:00:00Z", turned_back=3),
        ]})
        assert week["TurnedBack"] == 5

    def test_a_sprint_outside_the_week_is_not_counted(self):
        week = probe({"cmd": "history-week", "now": self.NOW, "sessions": [
            focus_session("2026-09-22T12:00:00Z", turned_back=2),
            focus_session("2026-09-10T12:00:00Z", turned_back=7),    # two weeks before
        ]})
        assert week["TurnedBack"] == 2
        assert week["SprintsCompleted"] == 1

    def test_a_sprint_saved_before_1_0_10_counts_zero(self):
        """A 1.0.9 settings file has no TurnedBack on its sprints; they load as 0."""
        week = probe({"cmd": "history-week", "now": self.NOW, "sessions": [
            focus_session("2026-09-22T12:00:00Z", turned_back=2),
            focus_session("2026-09-23T15:00:00Z"),
        ]})
        assert week["SprintsCompleted"] == 2, "the old sprint is in the week"
        assert week["TurnedBack"] == 2

    @pytest.mark.parametrize("n,text", [(0, ""), (1, "Turned back 1 time"), (4, "Turned back 4 times"),
                                        (11, "Turned back 11 times")])
    def test_the_wording(self, n, text):
        """Empty at zero, so the card and History hide the line rather than say 'Turned back 0 times'."""
        assert probe({"cmd": "turned-back-text", "n": n})["text"] == text


# =========================================== the taskbar Jump List (1.0.10, 5)

class TestStartSprintArg:
    """
    Spec 5: the Jump List runs FlowShield.exe --start-sprint (the tray's quick
    start) or --start-sprint=<templateId>. StartSprintArg reads that from a
    command line, and writes the one each template's entry carries.
    """

    @pytest.mark.parametrize("args,found,template_id", [
        (["--tray"], False, None),
        ([], False, None),
        (["--start-sprint"], True, None),
        (["--START-SPRINT=abc"], True, "abc"),
        (["--start-sprint="], True, None),
        (["--start-sprint=  "], True, None),
        (["--reset", "--start-sprint=abc"], True, "abc"),
        (["--start-sprinter"], False, None),
    ])
    def test_it_reads_the_argument(self, args, found, template_id):
        assert probe({"cmd": "start-arg", "args": args}) == {"found": found, "id": template_id}

    def test_a_templates_entry_carries_an_argument_that_reads_back_as_its_id(self):
        template_id = "0f8fad5bd9cb469fa16570867728950e"   # StudyTemplate.NewId's shape
        arg = probe({"cmd": "start-arg-for", "id": template_id})["arg"]
        assert arg == f"--start-sprint={template_id}"
        assert probe({"cmd": "start-arg", "args": [arg]}) == {"found": True, "id": template_id}

    @pytest.mark.parametrize("template_id", ["", "abc --reset", 'a"b', "a\tb"])
    def test_an_id_that_would_not_survive_a_command_line_gets_no_entry(self, template_id):
        """
        The id goes into a command line. One with a space or a quote would
        split into extra arguments (--reset among them), so it gets no entry
        rather than a broken one. Every id FlowShield makes is 32 hex digits.
        """
        assert probe({"cmd": "start-arg-for", "id": template_id})["arg"] is None


class TestJumpListText:
    """
    Spec 5: a template's entry reads "Start <template>". Entries are shell
    menu text, where one & marks a keyboard mnemonic and is not drawn, so
    "Maths & Physics" would show as "Maths Physics" with the P underlined.
    JumpListText escapes it the shell's way (&&); the tooltip stays as typed.
    """

    @pytest.mark.parametrize("name,title", [
        ("Light study", "Start Light study"),
        ("Maths & Physics", "Start Maths && Physics"),
        ("R&D && more", "Start R&&D &&&& more"),
    ])
    def test_a_templates_title_escapes_the_shells_mnemonic(self, name, title):
        assert probe({"cmd": "jump-title", "name": name})["title"] == title


# ====================== the shield and the nightly sleep window (#304, 1.0.10)

class TestTheFiveMinutesLeftNotification:
    """
    #304: "Nearly there — the shield comes down when the time is up" was said
    inside the nightly sleep window too, where only the sprint's shield comes
    down and the sleep shield keeps closing blocked apps. BreakCopy.EndingSoon
    says which shield comes down, in the voice of the break offer.
    """

    def ending_soon(self, in_window: bool, ends: str = "06:00") -> str:
        return probe({"cmd": "ending-soon-copy", "in_sleep_window": in_window, "ends": ends})["text"]

    def test_outside_the_window_it_reads_as_it_always_did(self):
        assert self.ending_soon(False) == "Nearly there — the shield comes down when the time is up."

    def test_inside_the_window_it_says_the_sleep_shield_stays_up(self):
        assert self.ending_soon(True, "06:30") == (
            "Nearly there — the sprint's shield comes down when the time is up, "
            "but your nightly sleep shield stays up until 06:30.")

    def test_inside_the_window_it_never_says_the_shield_comes_down_unqualified(self):
        text = self.ending_soon(True)
        assert not re.search(r"\bthe shield (comes|is|stays) down", text), text


class TestRingCaptions:
    """
    #304: every line the view model can put under the timer ring comes from
    RingCaption or BreakCopy.Caption, so tier 5's layout probe can measure
    each one. This pins the list itself from .NET.
    """

    def captions(self) -> list[dict]:
        """Line breaks folded to spaces: a long caption may set its own (tier 5 checks the layout)."""
        captions = probe({"cmd": "ring-captions"})["captions"]
        return [dict(c, text=" ".join(c["text"].split())) for c in captions]

    def test_every_break_caption_is_listed_in_both_sleep_states(self):
        texts = {c["text"] for c in self.captions()}
        for expected in ("Break — the shield is down", "Break resumed — the shield is down",
                         "Break — sleep shield still up", "Break resumed — sleep shield still up"):
            assert expected in texts, f"{expected!r} is not measured"

    def test_the_resumed_break_in_the_window_is_parallel_again(self):
        """#301 cut it to 'Resumed — sleep shield up' to fit one line; it wraps now."""
        texts = {c["text"] for c in self.captions()}
        assert "Resumed — sleep shield up" not in texts

    def test_every_shield_is_listed_starting_and_resuming_with_the_glyph(self):
        running = {c["text"] for c in self.captions() if c["running"]}
        assert running == {"Shield I engaged", "Shield II engaged", "Shield III engaged",
                           "Sprint resumed — shield I", "Sprint resumed — shield II",
                           "Sprint resumed — shield III"}

    def test_the_idle_and_ending_lines_are_listed(self):
        idle = {c["text"] for c in self.captions() if not c["running"]}
        for expected in ("Ready when you are", "Sprint cancelled", "Break over", "Sprint complete",
                         "Sprint interrupted", "Sprint ended early",
                         "Sprint finished while FlowShield was closed"):
            assert expected in idle, f"{expected!r} is not measured"
