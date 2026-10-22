"""
Tier 1 -- the sleep schedule (roadmap 3.7).

The time rules run through `core.model_probe`, so .NET answers them: the next
night, a window that crosses midnight, the chosen nights, the ten-minute
warning and the two daylight-saving days. The view model and the pages are
not compiled by the probe (no dotnet test project), so what they promise is
pinned by reading the source, like the rest of tier 1.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from config import SERVER_DIR
from core.model_probe import probe

DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
EASTERN = "Eastern Standard Time"  # UTC-5 in winter, UTC-4 in summer

# DayOfWeek as .NET numbers it.
SUN, MON, TUE, WED, THU, FRI, SAT = range(7)
EVERY_NIGHT_MONDAY_FIRST = [MON, TUE, WED, THU, FRI, SAT, SUN]
WEEKNIGHTS = [SUN, MON, TUE, WED, THU]  # the nights before a school or work day


def enabled(start="23:00:00", end="06:30:00", days=None, **more):
    settings = {"IsSleepBlockEnabled": True, "SleepBlockStartTime": start,
                "SleepBlockEndTime": end, **more}
    if days is not None:
        settings["SleepBlockDays"] = days
    return settings


def window(settings, now, **more):
    return probe({"cmd": "sleep-window", "settings": settings, "zone": EASTERN, "now": now, **more})


def next_text(settings, now):
    return probe({"cmd": "sleep-next-text", "settings": settings, "zone": EASTERN, "now": now})["text"]


def read(relative: str) -> str:
    return (DESKTOP / relative).read_text(encoding="utf-8")


# 2026-09-28 is a Monday; Eastern is on daylight time, UTC-4.
MON_8PM = "2026-09-29T00:00:00Z"


class TestNextOccurrence:
    def test_the_next_window_crosses_midnight(self):
        out = window(enabled(), MON_8PM)
        assert out["next"]["start"] == "2026-09-29T03:00:00Z"
        assert out["next"]["end"] == "2026-09-29T10:30:00Z"
        assert out["next"]["startLocal"] == "2026-09-28T23:00"
        assert out["next"]["endLocal"] == "2026-09-29T06:30"
        assert out["contains"] is False

    def test_inside_the_window_after_midnight_and_the_next_is_tomorrows(self):
        out = window(enabled(), "2026-09-29T06:00:00Z")  # Tuesday 02:00
        assert out["contains"] is True
        assert out["current"]["start"] == "2026-09-29T03:00:00Z"
        assert out["next"]["start"] == "2026-09-30T03:00:00Z"

    def test_boundaries_are_half_open(self):
        assert window(enabled(), "2026-09-29T03:00:00Z")["contains"] is True
        assert window(enabled(), "2026-09-29T10:29:59Z")["contains"] is True
        assert window(enabled(), "2026-09-29T10:30:00Z")["contains"] is False

    def test_a_same_day_window_needs_no_midnight(self):
        out = window(enabled("13:00:00", "17:00:00"), "2026-09-28T12:00:00Z")  # 08:00
        assert out["next"]["startLocal"] == "2026-09-28T13:00"
        assert out["next"]["endLocal"] == "2026-09-28T17:00"

    def test_equal_start_and_end_never_opens(self):
        out = window(enabled("22:00:00", "22:00:00"), MON_8PM)
        assert out["canOpen"] is False and out["next"] is None and out["contains"] is False

    def test_the_ten_minute_warning_is_ten_minutes_before_the_start(self):
        out = window(enabled(), MON_8PM)
        assert out["warning"] == "2026-09-29T02:50:00Z"


class TestChosenNights:
    def test_weeknights_skip_friday_and_saturday_starts(self):
        s = enabled(days=WEEKNIGHTS)
        # Thursday 21:00: tonight's window is still the next one.
        thursday = window(s, "2026-10-02T01:00:00Z")
        assert thursday["next"]["startLocal"] == "2026-10-01T23:00"
        # Friday noon: Friday and Saturday are skipped, so it is Sunday night.
        friday = window(s, "2026-10-02T16:00:00Z")
        assert friday["next"]["startLocal"] == "2026-10-04T23:00"

    def test_a_chosen_night_runs_into_the_morning_of_one_that_is_not(self):
        s = enabled(days=WEEKNIGHTS)
        assert window(s, "2026-10-02T07:00:00Z")["contains"] is True    # Friday 03:00, Thursday's window
        assert window(s, "2026-10-03T07:00:00Z")["contains"] is False   # Saturday 03:00, Friday's is not chosen
        assert window(s, "2026-10-05T06:00:00Z")["contains"] is True    # Monday 02:00, Sunday's window

    def test_one_chosen_night_is_a_week_apart(self):
        out = window(enabled(days=[FRI]), MON_8PM)
        assert out["next"]["startLocal"] == "2026-10-02T23:00"
        after = window(enabled(days=[FRI]), "2026-10-03T07:00:00Z")  # inside Friday's window
        assert after["next"]["startLocal"] == "2026-10-09T23:00"

    def test_the_nights_come_back_monday_first(self):
        assert window(enabled(days=[SUN, THU, MON]), MON_8PM)["nights"] == [MON, THU, SUN]

    def test_duplicates_and_unknown_days_are_ignored(self):
        assert window(enabled(days=[MON, MON, 9]), MON_8PM)["nights"] == [MON]

    def test_the_warning_is_for_a_chosen_night_only(self):
        steps = probe({"cmd": "sleep-warning", "settings": enabled(days=WEEKNIGHTS), "zone": EASTERN, "steps": [
            {"now": "2026-10-03T02:50:00Z", "apps": ["Steam"]},   # Friday 22:50: not a chosen night
            {"now": "2026-10-02T02:50:00Z", "apps": ["Steam"]},   # Thursday 22:50
        ]})["steps"]
        assert steps[0]["notice"] is None
        assert steps[1]["notice"]["message"] == "Steam closes at 23:00."


class TestOldSettings:
    def test_a_file_with_no_nights_means_every_night(self):
        out = window({"IsSleepBlockEnabled": True}, MON_8PM)
        assert out["savedDays"] is None
        assert out["nights"] == EVERY_NIGHT_MONDAY_FIRST
        assert out["canOpen"] is True

    def test_no_nights_stays_unset_through_a_clone(self):
        assert window({"IsSleepBlockEnabled": True}, MON_8PM, clone=True)["savedDays"] is None

    def test_chosen_nights_survive_the_json_round_trip(self):
        out = window(enabled(days=WEEKNIGHTS), MON_8PM, clone=True)
        assert out["savedDays"] == WEEKNIGHTS

    def test_an_explicitly_empty_choice_is_not_every_night(self):
        out = window(enabled(days=[]), MON_8PM, clone=True)
        assert out["savedDays"] == []
        assert out["nights"] == []
        assert out["canOpen"] is False and out["next"] is None and out["contains"] is False


class TestDaylightSaving:
    def test_spring_forward_shortens_the_night(self):
        # Saturday 2026-03-07 23:00 EST to Sunday 06:30 EDT: clocks skip 02:00 -> 03:00.
        out = window(enabled(days=[SAT]), "2026-03-07T12:00:00Z")
        assert out["next"]["start"] == "2026-03-08T04:00:00Z"
        assert out["next"]["end"] == "2026-03-08T10:30:00Z"   # six and a half real hours

    def test_a_start_inside_the_skipped_hour_moves_to_the_first_real_minute(self):
        out = window(enabled("02:30:00", "05:00:00", days=[SUN]), "2026-03-08T00:00:00Z")
        assert out["next"]["start"] == "2026-03-08T07:00:00Z"
        assert out["next"]["startLocal"] == "2026-03-08T03:00"
        assert out["next"]["end"] == "2026-03-08T09:00:00Z"

    def test_fall_back_lengthens_the_night(self):
        out = window(enabled(days=[SAT]), "2026-10-31T12:00:00Z")
        assert out["next"]["start"] == "2026-11-01T03:00:00Z"
        assert out["next"]["end"] == "2026-11-01T11:30:00Z"   # eight and a half real hours

    def test_a_start_in_the_repeated_hour_means_the_first_one(self):
        out = window(enabled("01:30:00", "05:00:00", days=[SUN]), "2026-11-01T00:00:00Z")
        assert out["next"]["start"] == "2026-11-01T05:30:00Z"      # 01:30 EDT, not 01:30 EST
        assert out["next"]["end"] == "2026-11-01T10:00:00Z"
        # 01:45 the second time round is inside the window, not a new opening.
        assert window(enabled("01:30:00", "05:00:00", days=[SUN]), "2026-11-01T06:45:00Z")["contains"] is True

    def test_the_warning_does_not_repeat_when_clocks_go_back(self):
        s = enabled("01:30:00", "05:00:00", days=[SUN])
        steps = probe({"cmd": "sleep-warning", "settings": s, "zone": EASTERN, "steps": [
            {"now": "2026-11-01T05:20:00Z", "apps": ["Steam"]},
            {"now": "2026-11-01T05:21:00Z", "apps": ["Steam"]},
            {"now": "2026-11-01T05:19:00Z", "apps": ["Steam"]},   # the clock stepped back
            {"now": "2026-11-01T05:22:00Z", "apps": ["Steam"]},
        ]})["steps"]
        assert [s_["notice"] is not None for s_ in steps] == [True, False, False, False]


class TestNextOnThePage:
    def test_tonight(self):
        assert next_text(enabled(), MON_8PM) == "Tonight 23:00 → 06:30"

    def test_tomorrow(self):
        assert next_text(enabled(days=[TUE]), MON_8PM) == "Tomorrow 23:00 → 06:30"

    def test_a_day_name_within_the_week(self):
        assert next_text(enabled(days=[FRI]), MON_8PM) == "Friday 23:00 → 06:30"

    def test_a_week_away_says_next(self):
        # Tuesday 23:30, inside Tuesday's window, with only Tuesday chosen.
        assert next_text(enabled(days=[TUE]), "2026-09-30T03:30:00Z") == "Next Tuesday 23:00 → 06:30"

    def test_a_daytime_start_is_today_not_tonight(self):
        assert next_text(enabled("14:00:00", "16:00:00"), "2026-09-28T12:00:00Z") == "Today 14:00 → 16:00"

    def test_nothing_when_no_night_is_chosen(self):
        assert next_text(enabled(days=[]), MON_8PM) is None


class TestTheWarning:
    def steps(self, settings, *steps, **more):
        out = probe({"cmd": "sleep-warning", "settings": settings, "zone": EASTERN,
                     "steps": [{"now": n, "apps": a} for n, a in steps], **more})
        return out["steps"]

    def test_it_names_the_apps_that_will_close(self):
        out = self.steps(enabled(), ("2026-09-29T02:50:00Z", ["Steam", "Discord"]))[0]
        assert out["notice"] == {"kind": "SleepWindowWarning", "title": "Wind down",
                                 "message": "Steam and Discord close at 23:00.",
                                 "action": "OpenSchedule"}

    def test_it_waits_for_ten_minutes_before_and_goes_out_once(self):
        out = self.steps(enabled(),
                         ("2026-09-29T02:49:45Z", ["Steam"]),
                         ("2026-09-29T02:50:00Z", ["Steam"]),
                         ("2026-09-29T02:50:15Z", ["Steam"]),
                         ("2026-09-29T02:59:45Z", ["Steam"]))
        assert [s["notice"] is not None for s in out] == [False, True, False, False]

    def test_apps_are_only_listed_when_a_notice_goes_out(self):
        out = self.steps(enabled(), ("2026-09-29T02:49:00Z", ["Steam"]), ("2026-09-29T02:50:00Z", ["Steam"]))
        assert [s["appsAsked"] for s in out] == [False, True]

    def test_turning_the_notification_off_suppresses_it(self):
        off = enabled(NotificationKinds={"SleepWindowWarning": False})
        out = self.steps(off, ("2026-09-29T02:50:00Z", ["Steam"]))[0]
        assert out["notice"] is None and out["appsAsked"] is False

    def test_the_master_switch_suppresses_it(self):
        out = self.steps(enabled(NotificationsEnabled=False), ("2026-09-29T02:50:00Z", ["Steam"]))[0]
        assert out["notice"] is None

    def test_other_notification_types_do_not_switch_it_off(self):
        s = enabled(NotificationKinds={"ScheduledSprint": False, "AppClosing": False})
        assert self.steps(s, ("2026-09-29T02:50:00Z", ["Steam"]))[0]["notice"] is not None

    def test_a_window_that_is_off_or_locked_sends_nothing(self):
        assert self.steps(enabled(IsSleepBlockEnabled=False), ("2026-09-29T02:50:00Z", ["Steam"]))[0]["notice"] is None
        assert self.steps(enabled(), ("2026-09-29T02:50:00Z", ["Steam"]), locked=True)[0]["notice"] is None

    def test_a_window_that_has_opened_is_never_warned_about_late(self):
        out = self.steps(enabled(), ("2026-09-29T03:05:00Z", ["Steam"]))[0]
        assert out["notice"] is None

    def test_opening_the_app_inside_the_ten_minutes_still_warns(self):
        out = self.steps(enabled(), ("2026-09-29T02:57:00Z", ["Steam"]))[0]
        assert out["notice"]["message"] == "Steam closes at 23:00."

    def test_a_running_sprint_does_not_hold_it_back(self):
        # Only money and updates wait for a sprint to end (F19/F20).
        assert self.steps(enabled(), ("2026-09-29T02:50:00Z", ["Steam"]), sprint=True)[0]["notice"] is not None

    def test_each_night_is_warned_about_once(self):
        out = self.steps(enabled(),
                         ("2026-09-29T02:50:00Z", ["Steam"]),
                         ("2026-09-30T02:50:00Z", ["Steam"]))
        assert [s["notice"] is not None for s in out] == [True, True]

    def test_with_nothing_running_it_promises_nothing_about_apps(self):
        out = self.steps(enabled(), ("2026-09-29T02:50:00Z", []))[0]
        assert out["notice"]["message"] == "Your sleep shield goes up at 23:00."

    @pytest.mark.parametrize("apps,message", [
        (["Steam"], "Steam closes at 23:00."),
        (["Steam", "Discord"], "Steam and Discord close at 23:00."),
        (["Steam", "Discord", "Slack"], "Steam, Discord and Slack close at 23:00."),
        (["Steam", "Discord", "Slack", "Zoom", "Teams"], "Steam, Discord, Slack and 2 more close at 23:00."),
    ])
    def test_the_wording_for_one_to_many(self, apps, message):
        out = probe({"cmd": "sleep-warning-copy", "apps": apps, "start": "23:00"})
        assert out == {"title": "Wind down", "message": message}


class TestWhatTheAppDoesWithIt:
    """Read from the source: the view model and pages are not compiled by the probe."""

    def test_enforcement_and_the_page_read_the_same_window(self):
        blocker = read("Services/AppBlockerService.cs")
        within = blocker.split("public static bool IsWithinSleepWindow", 1)[1].split("\n    }\n", 1)[0]
        assert "SleepWindow.From(settings).Contains(" in within
        page = read("ViewModels/SleepBlockingViewModel.cs")
        assert "SleepWindow.From(settings)" in page and "window.Next(now)" in page

    def test_the_warning_rides_the_schedulers_tick_not_a_timer_of_its_own(self):
        main = read("ViewModels/MainViewModel.cs")
        assert "Scheduler.Ticked += (_, now) => SleepBlocking.OnSchedulerTick(now);" in main
        assert "DispatcherTimer" not in read("ViewModels/SleepBlockingViewModel.cs")

    def test_the_warning_goes_through_the_one_notification_chokepoint(self):
        vm = read("ViewModels/SleepBlockingViewModel.cs")
        assert "_main.Notify(notice.Kind" in vm
        assert "NotificationKind.SleepWindowWarning" in read("Models/SleepWindow.cs")

    def test_closing_is_still_the_graceful_close_at_firm(self):
        blocker = read("Services/AppBlockerService.cs")
        assert "if (sleepActive && shield < ShieldLevel.Firm) shield = ShieldLevel.Firm;" in blocker
        assert "HardKillModeEnabled" in blocker

    def test_an_empty_choice_is_refused_by_the_view_model(self):
        vm = read("ViewModels/SleepBlockingViewModel.cs")
        save = vm.split("private void Save()", 1)[1].split("public void RefreshStatus", 1)[0]
        assert "nights.Count == 0" in save
        assert save.index("nights.Count == 0") < save.index("SleepBlockDays = nights")
        enable = vm.split("public bool IsEnabled", 1)[1].split("// ---- the window's times", 1)[0]
        assert "SleepBlockDays is { Count: 0 }" in enable
        assert enable.index("SleepBlockDays is { Count: 0 }") < enable.index("IsSleepBlockEnabled = value")

    def test_the_trial_lock_is_checked_first_in_the_view_model(self):
        vm = read("ViewModels/SleepBlockingViewModel.cs")
        save = vm.split("private void Save()", 1)[1]
        assert save.lstrip().startswith("{\n        if (_main.IsLocked)")
        enable = vm.split("public bool IsEnabled", 1)[1]
        assert enable.index("value && _main.IsLocked") < enable.index("IsSleepBlockEnabled = value")
        view = read("Views/SleepBlockingView.xaml")
        assert view.count('IsEnabled="{Binding HasAccess}"') >= 3   # toggle, pickers, nights, save

    def test_the_sealed_lock_is_no_stricter_and_no_looser_than_before(self):
        # Sealed never gated the sleep window; only the trial does. Keep it so.
        assert "Sealed" not in read("ViewModels/SleepBlockingViewModel.cs")

    def test_enabling_offers_start_with_windows_through_the_settings_switch(self):
        vm = read("ViewModels/SleepBlockingViewModel.cs")
        assert "StartupOfferPending = value && !_main.Settings.StartWithWindows;" in vm
        assert "_main.SettingsPage.StartWithWindows = true;" in vm
        assert "ShowStartupPanel = enabled && !_main.IsLocked && !startsAtSignIn;" in vm
        assert "StartupEntry.Set(value)" in read("ViewModels/SettingsViewModel.cs")

    def test_the_page_says_so_plainly_and_without_blame(self):
        vm = read("ViewModels/SleepBlockingViewModel.cs")
        assert "Basalt isn't set to start when you sign in" in vm
        assert "The sleep window only works while Basalt is running." in vm
        assert "should" not in vm.split("StartupText = ", 1)[1].split(";", 1)[0]

    def test_the_new_controls_are_named_for_screen_readers(self):
        view = read("Views/SleepBlockingView.xaml")
        for auto_id in ("SleepStartHour", "SleepStartMinute", "SleepEndHour", "SleepEndMinute",
                        "SleepNextText", "SleepStartWithWindowsButton", "SleepStartupNotNowButton"):
            assert f'AutomationProperties.AutomationId="{auto_id}"' in view, auto_id
        for combo in re.findall(r"<ComboBox\b.*?/>", view, flags=re.S):
            assert "AutomationProperties.Name=" in combo and "AutomationProperties.AutomationId=" in combo
        vm = read("ViewModels/SleepBlockingViewModel.cs")
        assert 'AutomationId = $"SleepNight_{label}"' in vm and 'night",' in vm

    def test_the_existing_ids_are_kept_and_only_the_two_text_boxes_retired(self):
        view = read("Views/SleepBlockingView.xaml")
        for auto_id in ("SleepBlockToggle", "SaveSleepWindowButton", "SleepStatusText", "SleepWindowText",
                        "SleepGetProButton"):
            assert f'AutomationProperties.AutomationId="{auto_id}"' in view, auto_id
        assert "SleepStartInput" not in view and "SleepEndInput" not in view

    def test_the_picker_style_uses_tokens_only(self):
        theme = read("Styles/Theme.xaml")
        style = theme.split('x:Key="TimePickerItem"', 1)[1].split("Toggle switch, built from a CheckBox", 1)[0]
        assert not re.search(r'="#[0-9A-Fa-f]{3,8}"', style), "a literal colour in the picker style"
        assert 'x:Key="TimePicker"' in theme and "FocusVisualStyle" in style

    def test_settings_gets_exactly_one_new_toggle_for_it(self):
        xaml = read("Views/SettingsView.xaml")
        assert xaml.count('AutomationId="NotifySleepWindowToggle"') == 1
        assert 'IsChecked="{Binding NotifySleepWindowWarning}"' in xaml
        vm = read("ViewModels/SettingsViewModel.cs")
        assert "Raise(nameof(NotifySleepWindowWarning));" in vm
        assert "IsOn(NotificationKind.SleepWindowWarning)" in vm

    def test_the_export_carries_the_nights_and_nothing_new_leaves_the_machine(self):
        assert "nights = " in read("Services/DataPrivacyService.cs")
        for name in ("SleepWindow.cs", "SleepBlockingViewModel.cs"):
            path = "Models" if name == "SleepWindow.cs" else "ViewModels"
            source = read(f"{path}/{name}")
            assert "HttpClient" not in source and "WebRequest" not in source
