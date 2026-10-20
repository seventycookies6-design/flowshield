# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 1: blocking."""

from __future__ import annotations
import json
import re
from pathlib import Path
import pytest
from config import SERVER_DIR
from ._helpers import JUNK_NAME_WORDS, JUNK_PROCESS_WORDS, SoftOverlayPolicy, normalize_process_name, parse_time, picker_filter, picker_is_not_an_app, picker_merge, within_sleep_window



class TestSleepWindow:
    def test_same_day_window_includes_its_middle(self):
        assert within_sleep_window(13 * 60, 9 * 60, 17 * 60) is True

    def test_same_day_window_excludes_outside(self):
        assert within_sleep_window(8 * 60, 9 * 60, 17 * 60) is False
        assert within_sleep_window(18 * 60, 9 * 60, 17 * 60) is False

    def test_window_crossing_midnight_includes_late_evening(self):
        assert within_sleep_window(23 * 60, 22 * 60, 6 * 60) is True

    def test_window_crossing_midnight_includes_early_morning(self):
        assert within_sleep_window(2 * 60, 22 * 60, 6 * 60) is True

    def test_window_crossing_midnight_excludes_daytime(self):
        assert within_sleep_window(12 * 60, 22 * 60, 6 * 60) is False

    def test_boundaries_are_half_open(self):
        # Start is inclusive, end exclusive — so a window can't double-count.
        assert within_sleep_window(22 * 60, 22 * 60, 6 * 60) is True
        assert within_sleep_window(6 * 60, 22 * 60, 6 * 60) is False


class TestTimeParsing:
    @pytest.mark.parametrize("text,expected", [
        ("22:00", (22, 0)),
        ("06:45", (6, 45)),
        ("9:05", (9, 5)),
        ("2200", (22, 0)),
        ("10pm", (22, 0)),
        ("12am", (0, 0)),
    ])
    def test_accepted_formats(self, text, expected):
        assert parse_time(text) == expected

    @pytest.mark.parametrize("text", ["", "   ", "banana", "25:00", "12:99", "::"])
    def test_rejected_formats(self, text):
        assert parse_time(text) is None


class TestProcessNameNormalisation:
    @pytest.mark.parametrize("raw,expected", [
        ("slack", "slack"),
        ("Slack.exe", "Slack"),
        (r"C:\Users\me\AppData\Local\slack\slack.exe", "slack"),
        ('  "steam.EXE"  ', "steam"),
        ("C:/Program Files/App/thing.exe", "thing"),
    ])
    def test_normalisation(self, raw, expected):
        assert normalize_process_name(raw) == expected

    def test_protected_processes_list_covers_the_shell_and_the_app_itself(self):
        source = (Path(SERVER_DIR).parent / "DesktopApp" / "Services"
                  / "AppBlockerService.cs").read_text(encoding="utf-8")

        # Take the initialiser body only — splitting on the identifier alone
        # lands inside the doc comment above it.
        marker = "HashSet<string> CriticalProcesses"
        start = source.index(marker)
        block = source[source.index("{", start):source.index("};", start)].lower()

        for critical in ("explorer", "csrss", "winlogon", "lsass",
                         "flowshield", "powershell", "services", "lsass"):
            assert f'"{critical}"' in block, f"{critical} must never be terminable"


class TestAppSuggestions:
    """The picker's built-in suggestions (F8)."""

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"

    @classmethod
    def data(cls) -> dict:
        import json

        return json.loads((cls.DESKTOP / "Data" / "app_suggestions.json").read_text(encoding="utf-8"))

    @classmethod
    def critical(cls) -> set[str]:
        import re

        source = (cls.DESKTOP / "Services" / "AppBlockerService.cs").read_text(encoding="utf-8")
        block = source.split("CriticalProcesses = new(")[1].split("};")[0]
        return {name.lower() for name in re.findall(r'"([^"]+)"', block)}

    def apps(self):
        return [(g, a) for g in self.data()["groups"] for a in g["apps"]]

    def test_the_groups_the_checklist_asks_for(self):
        names = [g["name"] for g in self.data()["groups"]]
        assert names[:2] == ["Chat", "Games & launchers"]
        assert "Browsers" in names

    def test_every_app_has_a_name_and_processes(self):
        for _, app in self.apps():
            assert app["name"].strip(), app
            assert app["processes"], f"{app['name']} has no processes"
            assert isinstance(app["verified"], bool), app["name"]
            for process in app["processes"]:
                assert process == process.strip() and process, app["name"]
                assert not process.lower().endswith(".exe"), f"{process}: no .exe suffix"
                assert "\\" not in process and "/" not in process

    def test_nothing_protected_is_ever_suggested(self):
        critical = self.critical()
        assert "explorer" in critical and "flowshield" in critical   # the parse worked
        for _, app in self.apps():
            for process in app["processes"]:
                assert process.lower() not in critical, f"{app['name']} suggests protected {process}"

    def test_no_process_belongs_to_two_apps(self):
        seen = {}
        for _, app in self.apps():
            for process in app["processes"]:
                assert process.lower() not in seen, f"{process} is in {seen.get(process.lower())} and {app['name']}"
                seen[process.lower()] = app["name"]

    def test_app_names_are_unique(self):
        names = [a["name"].lower() for _, a in self.apps()]
        assert len(names) == len(set(names))

    def test_steam_covers_its_helper(self):
        steam = next(a for _, a in self.apps() if a["name"] == "Steam")
        assert {p.lower() for p in steam["processes"]} == {"steam", "steamwebhelper"}

    def test_xbox_uses_the_names_seen_on_a_clean_install(self):
        # Checked on Miles's VM in #53: the Xbox app runs as XboxPcApp with an XboxPcTray helper.
        # XboxPcAppAdminServer is left out: it runs elevated, and the timid blocker can't close it.
        # #348, on Windows 11 (DESKTOP-QI8SG30): the Start menu's XBOX entry is
        # XboxPcAppCE in the package manifest, so the Store scan finds the app by
        # that name; listing it here folds that row into this suggestion.
        xbox = next(a for _, a in self.apps() if a["name"] == "Xbox app")
        assert xbox["processes"] == ["XboxPcApp", "XboxPcAppCE", "XboxPcTray"] and xbox["verified"] is True

    def test_browsers_warn_that_the_whole_browser_closes(self):
        browsers = next(g for g in self.data()["groups"] if g["name"] == "Browsers")
        assert "whole browser" in browsers["note"].lower()
        assert {"chrome", "msedge", "firefox"} <= {p for a in browsers["apps"] for p in a["processes"]}

    def test_the_file_is_built_into_the_app(self):
        project = (self.DESKTOP / "FlowShield.csproj").read_text(encoding="utf-8")
        assert 'EmbeddedResource Include="Data\\app_suggestions.json"' in project
        picker = (self.DESKTOP / "Models" / "AppPicker.cs").read_text(encoding="utf-8")
        assert '"FlowShield.app_suggestions.json"' in picker


class TestPickerSearch:
    ENTRIES = [
        {"name": "Discord", "processes": ["Discord"], "source": "Suggested"},
        {"name": "Steam", "processes": ["steam", "steamwebhelper"], "source": "Suggested"},
        {"name": "Microsoft Edge", "processes": ["msedge"], "source": "Suggested"},
        {"name": "Obsidian", "processes": ["Obsidian"], "source": "Installed"},
        {"name": "Adobe Reader", "processes": ["AcroRd32"], "source": "Running"},
    ]

    @pytest.mark.parametrize("query,expected", [
        ("", ["Discord", "Steam", "Microsoft Edge", "Obsidian", "Adobe Reader"]),
        ("steam", ["Steam"]),
        ("webhelper", ["Steam"]),                  # finds an app by any of its processes
        ("msedge.exe", ["Microsoft Edge"]),
        ("o", ["Obsidian", "Discord", "Microsoft Edge", "Adobe Reader"]),
        ("zzz", []),
    ])
    def test_matches_and_order(self, query, expected):
        assert picker_filter(self.ENTRIES, query) == expected

    def test_the_mirror_matches_the_app(self):
        source = (Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppPicker.cs").read_text(encoding="utf-8")
        filt = source.split("public static List<PickerEntry> Filter(")[1]
        assert "e.Name.StartsWith(q, StringComparison.OrdinalIgnoreCase) ? 0 : 1" in filt
        assert ".ThenBy(e => e.Source)" in filt
        assert "e.Processes.Any(p => p.Contains(q, StringComparison.OrdinalIgnoreCase))" in filt


# ====================================================== per-app on/off switch

class TestPerAppSwitch:
    """Roadmap 2.4: each blocked-app row has an on/off switch wired to ToggleApp."""

    XAML = Path(SERVER_DIR).parent / "DesktopApp" / "Views" / "BlockedAppsView.xaml"
    VM = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "BlockedAppsViewModel.cs"

    def test_the_switch_automation_id_is_in_the_xaml(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        assert "AppEnabledSwitch" in xaml, \
            "each blocked-app row must expose an AppEnabledSwitch AutomationId"

    def test_toggle_app_exists_in_the_viewmodel(self):
        vm = self.VM.read_text(encoding="utf-8")
        assert "ToggleApp" in vm, "BlockedAppsViewModel must expose ToggleApp"
        assert "ToggleAppCommand" in vm, "ToggleApp must be reachable as a command"


# ===================== what is already open, before a sprint (F7 / 1.8)

class TestPreSprintRunningApps:
    """
    Roadmap 1.8: before a sprint starts, if blocked apps are running, list them
    and offer Close them now or Start anyway.

    The point is the chance to save, so the wording has to be honest about what
    each shield will actually do — promising a close at Soft, which closes
    nothing, would be worse than saying nothing.
    """

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    VM = DESKTOP / "ViewModels" / "TodayViewModel.cs"
    SERVICE = DESKTOP / "Services" / "AppBlockerService.cs"
    XAML = DESKTOP / "Views" / "TodayView.xaml"

    def test_the_list_names_each_app_once(self):
        """
        Steam runs seven processes. "Steam, Steam, Steam, Steam" is not a list,
        and it is the same reason #138 counts apps rather than processes.
        """
        source = self.SERVICE.read_text(encoding="utf-8")
        body = source.split("public IReadOnlyList<string> RunningBlockedApps", 1)[1]
        body = body.split("\n    }", 1)[0]
        assert "seen.Add(app.DisplayName)" in body

    def test_looking_is_not_enforcing(self):
        """It runs before the sprint does; it must not close anything."""
        source = self.SERVICE.read_text(encoding="utf-8")
        body = source.split("public IReadOnlyList<string> RunningBlockedApps", 1)[1]
        body = body.split("\n    }", 1)[0]
        for forbidden in ("Kill(", "CloseMainWindow(", "BeginEnforcing"):
            assert forbidden not in body, f"the pre-sprint look must not {forbidden}"

    def test_soft_does_not_promise_a_close_it_will_not_do(self):
        source = self.VM.read_text(encoding="utf-8")
        explanation = source.split("RunningAppsExplanation =>", 1)[1].split(";", 1)[0]
        assert "ShieldLevel.Soft" in explanation
        assert "they stay open" in explanation
        assert "asked to close" in explanation, "Firm and above say what happens"

    def test_the_panel_offers_both_answers(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        for automation_id in ("RunningAppsTitle", "RunningAppsList",
                              "CloseThemNowButton", "StartAnywayButton"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml

    def test_the_panel_puts_no_id_where_nothing_can_find_it(self):
        """
        A Border is not surfaced to UI Automation. An id on one can never be
        resolved, which cost a whole VM run: the panel opened, exists() said it
        had not, and the driver never answered it.
        """
        xaml = self.XAML.read_text(encoding="utf-8")
        panel = xaml.split("What is already open, before the shield goes up", 1)[1]
        panel = panel.split("</Border>", 1)[0]
        for tag in ("<Border", "<StackPanel", "<ItemsControl"):
            for element in panel.split(tag)[1:]:
                head = element.split(">", 1)[0]
                assert "AutomationProperties.AutomationId" not in head, (
                    f"an AutomationId is on a {tag[1:]}, where nothing can find it"
                )

    def test_answering_does_not_ask_again(self):
        """
        Both answers call back into StartSprint. Without the latch that is a
        loop: panel, answer, panel, answer.
        """
        source = self.VM.read_text(encoding="utf-8")
        assert "if (!_runningAppsAnswered)" in source
        assert "_runningAppsAnswered = false;" in source, (
            "the latch has to reset, or the next sprint is never checked"
        )


class TestSoftOverlayPolicy:
    """
    Roadmap 1.7: at Soft, a blocked app coming to the front gets a full-screen
    notice — once, not on every sweep of the blocker, and not at all for five
    minutes after "Allow 5 minutes".
    """

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    MODEL = DESKTOP / "Models" / "SoftOverlayPolicy.cs"
    BACK_TO_WORK_QUIET_SECONDS = 5

    def test_a_blocked_app_coming_to_the_front_is_shown_once(self):
        """
        The blocker sweeps every two seconds. Showing the notice on every sweep
        while Discord is still in front would be a flashing box, not a nudge.
        """
        policy = SoftOverlayPolicy()
        assert policy.should_show("Discord", 0)
        for tick in range(1, 20):
            assert not policy.should_show("Discord", tick * 2), (
                "the notice must appear once per sighting, not once per sweep"
            )

    def test_going_away_and_coming_back_is_a_new_sighting(self):
        policy = SoftOverlayPolicy()
        assert policy.should_show("Discord", 0)
        assert policy.left_the_foreground() is True, "a notice was up and must come down"
        assert policy.should_show("Discord", 60)

    def test_nothing_to_take_down_when_no_notice_was_up(self):
        policy = SoftOverlayPolicy()
        assert policy.left_the_foreground() is False

    def test_another_blocked_app_gets_its_own_notice(self):
        policy = SoftOverlayPolicy()
        assert policy.should_show("Discord", 0)
        assert policy.should_show("Steam", 2)
        assert not policy.should_show("Steam", 4)

    def test_allow_five_minutes_is_five_minutes_for_that_app_only(self):
        policy = SoftOverlayPolicy()
        assert policy.should_show("Discord", 0)
        policy.allow_five_minutes("Discord", 0)

        # Returning inside the window says nothing.
        assert not policy.should_show("Discord", 1)
        assert policy.left_the_foreground() is False
        assert not policy.should_show("Discord", 299)

        # Another blocked app is not covered by Discord's allowance.
        assert policy.should_show("Steam", 10)

        policy.left_the_foreground()
        assert policy.should_show("Discord", 301), (
            "five minutes is five minutes, not the rest of the sprint"
        )

    def test_back_to_work_goes_quiet_just_long_enough_to_get_out_of_the_way(self):
        """
        Bringing Basalt forward takes a moment. Without the quiet window the
        notice reappears in the gap, over the window it just asked for.
        """
        policy = SoftOverlayPolicy()
        assert policy.should_show("Discord", 0)
        policy.back_to_work("Discord", 0)
        assert not policy.should_show("Discord", 1)
        policy.left_the_foreground()
        assert policy.should_show("Discord", 30), (
            "going back to the distraction later must nudge again"
        )

    def test_a_quiet_window_expiring_does_not_interrupt_what_you_are_doing(self):
        """
        The notice appears when you go to the blocked app, not while you are in
        it. Someone who asked for five minutes and is still in Discord at minute
        six gets nothing until they leave and come back — a panel appearing over
        a window they are typing in would be the worst moment for it.
        """
        policy = SoftOverlayPolicy()
        policy.should_show("Discord", 0)
        policy.allow_five_minutes("Discord", 0)
        for tick in range(1, 400, 2):
            assert not policy.should_show("Discord", tick)

    def test_app_names_are_matched_without_case(self):
        policy = SoftOverlayPolicy()
        policy.allow_five_minutes("Discord", 0)
        assert not policy.should_show("discord", 10)

    def test_an_allowance_does_not_outlive_its_sprint(self):
        policy = SoftOverlayPolicy()
        policy.allow_five_minutes("Discord", 0)
        policy.reset()
        assert policy.should_show("Discord", 10), (
            "a new sprint starts with no allowances carried over"
        )

    def test_the_mirror_counts_tries_and_turned_back_like_the_probe(self):
        """
        1.0.10: the same sequence the probe runs against the real C#
        (test_tier1_models.py), so the mirror cannot drift from it unnoticed.
        Close and Back to work count as turned back; Allow does not.
        """
        policy = SoftOverlayPolicy()
        assert policy.should_show("Discord", 0)
        policy.close_it("Discord", 1)
        policy.left_the_foreground()
        assert policy.should_show("Steam", 30)
        policy.back_to_work("Steam", 31)
        policy.left_the_foreground()
        assert policy.should_show("Discord", 60)
        policy.allow_five_minutes("Discord", 61)
        assert policy.tries == 3
        assert policy.turned_back == 2
        policy.reset()
        assert (policy.tries, policy.turned_back) == (0, 0), "a new sprint counts again"

    def test_close_answers_the_sighting_rather_than_clearing_it(self):
        """
        After Close the app may stay in front with its own "save changes?"
        prompt up. Cleared like Back to work, the sighting came back as a
        "2nd try" over that prompt once the quiet window ran out.
        """
        policy = SoftOverlayPolicy()
        assert policy.should_show("Discord", 0)
        policy.close_it("Discord", 0)
        assert not policy.should_show("Discord", 10), "still the same sighting: the app never left"
        assert policy.left_the_foreground() is False, "Close already took the notice down"
        assert policy.should_show("Discord", 11), "left and came back: a fresh sighting"

    # ---- the mirror above proves the rules are right; these prove the C# has
    # them. Without this half, `if (false && !isNewSighting)` in ShouldShow
    # left every Python test passing while the notice flashed on every sweep.

    def _model(self) -> str:
        return " ".join(self.MODEL.read_text(encoding="utf-8").split())

    def _body(self, signature: str) -> str:
        source = self.MODEL.read_text(encoding="utf-8")
        assert signature in source, f"{signature} is gone from SoftOverlayPolicy.cs"
        return " ".join(source.split(signature, 1)[1].split("\n    }", 1)[0].split())

    def test_the_windows_in_the_model_match_this_mirror(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "TimeSpan.FromMinutes(5)" in source, "Allow 5 minutes has to be five minutes"
        assert f"TimeSpan.FromSeconds({self.BACK_TO_WORK_QUIET_SECONDS})" in source

    def test_the_model_returns_early_for_a_sighting_it_has_already_answered(self):
        body = self._body("public bool ShouldShow(string displayName, DateTime nowUtc)")
        assert ("var isNewSighting = !string.Equals(_sighting, displayName, "
                "StringComparison.OrdinalIgnoreCase);") in body, (
            "the same-sighting test has to compare the remembered app with this one, "
            "without case"
        )
        assert "if (!isNewSighting) return false;" in body, (
            "once per sighting is this line; short-circuiting it (false && ...) "
            "makes the notice appear on every two-second sweep"
        )
        assert "if (IsQuiet(displayName, nowUtc)) return false;" in body, (
            "an allowance has to be checked where the notice is decided"
        )
        for dead in ("false &&", "true ||", "&& false", "|| true"):
            assert dead not in body, f"{dead} disables a rule while leaving it in the source"

    def test_the_sighting_is_remembered_even_when_nothing_is_drawn(self):
        """
        Otherwise a suppressed app is a new sighting every sweep, and the moment
        its five minutes are up the notice lands on a window mid-sentence.
        """
        body = self._body("public bool ShouldShow(string displayName, DateTime nowUtc)")
        assert body.index("_sighting = displayName;") < body.index("if (!isNewSighting)")

    def test_each_answer_maps_to_its_own_window(self):
        source = self._model()
        assert ("public void AllowFiveMinutes(string displayName, DateTime nowUtc) => "
                "Quieten(displayName, nowUtc, AllowWindow);") in source
        back = self._body("public void BackToWork(string displayName, DateTime nowUtc)")
        assert "TurnedBack++;" in back, "Back to work counts as turned back (1.0.10)"
        assert "Quieten(displayName, nowUtc, BackToWorkQuiet);" in back
        assert "AllowWindow = TimeSpan.FromMinutes(5)" in source
        assert (f"BackToWorkQuiet = TimeSpan.FromSeconds"
                f"({self.BACK_TO_WORK_QUIET_SECONDS})") in source

    def test_close_keeps_the_sighting_in_the_model(self):
        """Close answers the sighting; only leaving the foreground clears it."""
        close = self._body("public void CloseIt(string displayName, DateTime nowUtc)")
        assert "TurnedBack++;" in close, "Close counts as turned back (1.0.10)"
        assert "_quietUntil[displayName] = nowUtc + BackToWorkQuiet;" in close
        assert "_showing = false;" in close
        assert "_sighting = null;" not in close and "Quieten(" not in close, (
            "clearing the sighting re-shows the notice over the app's own save prompt"
        )

    def test_a_quiet_window_is_recorded_per_app_and_read_back(self):
        quieten = self._body(
            "private void Quieten(string displayName, DateTime nowUtc, TimeSpan window)")
        assert "_quietUntil[displayName] = nowUtc + window;" in quieten, (
            "the window has to be stored against the app, or it silences everything"
        )
        assert "_sighting = null;" in quieten, (
            "clearing the sighting is what makes coming back later a new one"
        )
        assert "_showing = false;" in quieten

        is_quiet = self._model()
        assert ("_quietUntil.TryGetValue(displayName, out var until) && nowUtc < until"
                in is_quiet), "a window that is never compared against the clock never ends"

    def test_the_notice_is_taken_down_only_when_one_was_up(self):
        body = self._body("public bool LeftTheForeground()")
        assert "var wasShowing = _showing;" in body
        assert "_showing = false;" in body
        assert "return wasShowing;" in body, (
            "returning true unconditionally would ask MainWindow to close a "
            "notice that was never opened"
        )

    def test_reset_forgets_every_allowance(self):
        body = self._body("public void Reset()")
        assert "_quietUntil.Clear();" in body
        assert "_sighting = null;" in body
        assert "_showing = false;" in body

    def test_the_policy_decides_nothing_about_closing_anything(self):
        """Soft notes distractions. A policy that could close one is the wrong shape."""
        source = self.MODEL.read_text(encoding="utf-8")
        for forbidden in ("Kill(", "CloseMainWindow(", "Process"):
            assert forbidden not in source, f"the Soft notice policy must not mention {forbidden}"

    def test_the_sentence_names_the_app_and_when_the_blocklist_holds_until(self):
        """DESIGN_SYSTEM.md §7's own example: "Discord is on your blocklist until 5:45 PM"."""
        source = self.MODEL.read_text(encoding="utf-8")
        sentence = source.split("public static string Sentence", 1)[1]
        sentence = sentence.split("=>", 1)[1].split(";", 1)[0]
        assert "{displayName} is on your blocklist until" in sentence

    def test_the_time_left_is_specific(self):
        source = self.MODEL.read_text(encoding="utf-8")
        body = source.split("public static string TimeLeft", 1)[1].split("\n    }", 1)[0]
        assert "1 minute left in this sprint" in body
        assert "minutes left in this sprint" in body

    def test_the_copy_keeps_to_the_house_voice(self):
        """DESIGN_SYSTEM.md §9: no exclamation marks, no emoji, no scolding."""
        source = self.MODEL.read_text(encoding="utf-8")
        quoted = re.findall(r'"([^"]*)"', source)
        for text in quoted:
            assert "!" not in text, f"exclamation mark in product copy: {text!r}"
            assert text.isascii(), f"non-ascii (emoji?) in product copy: {text!r}"


# ================================================ blocklist profiles (F9)

class TestBlocklistProfileRules:
    """
    The three rules a blocklist profile lives by (F9, roadmap 3.8): the one
    list that existed before becomes the Default profile, there is always at
    least one profile, and an active id naming nothing still resolves to a
    list the shield can enforce.

    Unit-by-source, like the settings-model tests above: it reads the C# rather
    than running it.
    """

    SETTINGS = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"
    PROFILE = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "BlocklistProfile.cs"
    MAIN_VM = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "MainViewModel.cs"

    def source(self) -> str:
        return self.SETTINGS.read_text(encoding="utf-8")

    def method(self, signature: str) -> str:
        return self.source().split(signature)[1].split("\n    }")[0]

    # ------------------------------------------------------------- migration

    def test_the_old_single_blocklist_becomes_the_default_profile(self):
        ensure = self.method("public bool EnsureProfiles()")
        assert "Profiles.Count == 0" in ensure
        assert "DefaultProfileName" in ensure
        assert "_legacyBlockedApps" in ensure, \
            "the list from a settings file written before profiles must carry over"
        assert "changed = true" in ensure

    def test_the_legacy_list_is_what_the_old_property_name_still_writes_into(self):
        source = self.source()
        blocked = source.split("public List<BlockedApp> BlockedApps")[1].split("\n    }")[0]
        assert "set => _legacyBlockedApps = value;" in blocked
        assert "get => ActiveProfile.Apps;" in blocked

    def test_migration_runs_once_at_startup_before_anything_reads_the_list(self):
        main = self.MAIN_VM.read_text(encoding="utf-8")
        ctor = main.split("public MainViewModel(")[1].split("\n    public SettingsService")[0]
        assert "Settings.EnsureProfiles()" in ctor
        assert ctor.index("Settings.EnsureProfiles()") < ctor.index("new AppBlockerService("), \
            "profiles must exist before the blocker takes its first snapshot"

    # -------------------------------------------- never delete the last one

    def test_the_last_profile_cannot_be_deleted(self):
        remove = self.method("public bool RemoveProfile(string? id)")
        assert "if (Profiles.Count <= 1) return false;" in remove, \
            "there is always at least one blocklist"

    def test_deleting_the_active_profile_moves_the_active_id(self):
        remove = self.method("public bool RemoveProfile(string? id)")
        assert "ActiveProfileId = Profiles[0].Id" in remove

    def test_the_view_model_hides_delete_on_the_only_profile(self):
        vm = (Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels"
              / "BlockedAppsViewModel.cs").read_text(encoding="utf-8")
        assert "public bool CanDeleteProfile => CanEditProfiles && Profiles.Count > 1;" in vm

    # ----------------------------------------------- resolving the active id

    def test_a_missing_active_id_falls_back_rather_than_throwing(self):
        active = self.source().split("public BlocklistProfile ActiveProfile")[1].split("\n    }")[0]
        assert "FindProfile(ActiveProfileId)" in active
        assert "if (Profiles.Count > 0) return Profiles[0];" in active, \
            "an id naming a deleted profile must still resolve to a list"
        assert "Profiles.Add(seeded)" in active, \
            "with no profiles at all, one is seeded rather than returning null"

    def test_an_empty_id_never_matches_a_profile(self):
        find = self.source().split(
            "public BlocklistProfile? FindProfile(string? id) =>")[1].split(";")[0]
        assert "string.IsNullOrEmpty(id)" in find
        assert "? null" in find

    def test_ensureprofiles_settles_a_dangling_active_id(self):
        ensure = self.method("public bool EnsureProfiles()")
        assert "if (FindProfile(ActiveProfileId) is null)" in ensure
        assert "ActiveProfileId = Profiles[0].Id;" in ensure

    # ------------------------------------------------------ keeping it simple

    def test_a_profile_is_a_name_and_a_list_and_nothing_more(self):
        profile = self.PROFILE.read_text(encoding="utf-8")
        for rule in ("Schedule", "TimeWindow", "DaysOfWeek", "ShieldLevel"):
            assert rule not in profile, \
                f"a profile carries no {rule}: per-profile rules are the complexity F9 refuses"

    def test_the_suggested_profiles_are_offered_not_created(self):
        source = self.source()
        assert '"School", "Gaming break", "Everything"' in source
        ensure = self.method("public bool EnsureProfiles()")
        assert "SuggestedProfileNames" not in ensure, \
            "the suggestions are names to pick from, not profiles the app makes"


class TestPickerListsOnlyInstalledApps:
    """The picker shows an app only when it is on this PC, so every row can
    carry the app's own icon from its installed exe (nothing is bundled)."""

    SUGGESTIONS = [
        {"name": "Discord", "processes": ["Discord"]},
        {"name": "Slack", "processes": ["slack"]},
        {"name": "Steam", "processes": ["steam", "steamwebhelper"]},
    ]

    def test_uninstalled_suggestions_are_left_out(self):
        found = [{"name": "Discord", "processes": ["Discord"]},
                 {"name": "Steam Helper", "processes": ["steamwebhelper"]},
                 {"name": "Obsidian", "processes": ["Obsidian"]}]
        assert picker_merge(self.SUGGESTIONS, found) == ["Discord", "Steam", "Obsidian"]

    def test_nothing_found_means_nothing_suggested(self):
        assert picker_merge(self.SUGGESTIONS, []) == []

    def test_the_mirror_matches_the_app(self):
        source = (Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppPicker.cs").read_text(encoding="utf-8")
        merge = source.split("public static List<PickerEntry> Merge(")[1].split("public static")[0]
        assert "covered.Add(covering)" in merge
        assert "!covered.Contains(r)" in merge

    def test_the_picker_does_not_open_on_the_whole_catalogue(self):
        root = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels"
        blocked = (root / "BlockedAppsViewModel.cs").read_text(encoding="utf-8")
        first_run = (root / "FirstRunViewModel.cs").read_text(encoding="utf-8")
        assert "_allEntries = AppPicker.Suggestions(" not in blocked
        assert "LoadApps(AppPicker.Suggestions(" not in first_run

    def test_icons_only_come_from_the_installed_exe(self):
        catalog = (Path(SERVER_DIR).parent / "DesktopApp" / "Services" / "AppCatalog.cs").read_text(encoding="utf-8")
        assert "ExtractAssociatedIcon(exePath)" in catalog
        assets = Path(SERVER_DIR).parent / "DesktopApp" / "Assets" / "Icons"
        assert not [p for p in assets.iterdir() if p.suffix.lower() in (".png", ".ico", ".svg")], \
            "no third-party app logos are shipped"


class TestPickerSkipsThingsThatArentApps:
    """Real Start Menu and uninstall entries from a developer's PC (22 Sep 2026)."""

    @pytest.mark.parametrize("name,process", [
        ("Check for FxSound updates", "updater"),
        ("Discord", "Update"),                       # Squirrel's shortcut target, not Discord
        ("Uninstall Cisco Packet Tracer", "unins000"),
        ("Visual Studio Installer", "setup"),
        ("Roblox Studio", "RobloxStudioInstaller"),
        ("Python 3.12 Module Docs (64-bit)", "python"),
        ("Microsoft Visual C++ v14 Redistributable (x64) - 14.51.36247", "VC_redist.x64"),
        ("Microsoft Windows Desktop Runtime - 8.0.26 (x64)", "windowsdesktop-runtime-8.0.26-win-x64"),
        ("Microsoft .NET SDK 10.0.401 (x64)", "dotnet-sdk-10.0.401-win-x64"),
        ("Microsoft ASP.NET Core 8.0.25 - Shared Framework (x64)", "AspNetCoreSharedFrameworkBundle-x64"),
        ("Parsec Virtual Display Driver", "uninstall"),
        ("Dell SupportAssist OS Recovery Plugin for Dell Update", "DellUpdateSupportAssistPlugin"),
        ("Windows 11 Installation Assistant", "Windows10UpgraderApp"),
        ("Logi Download Assistant", "logi_download_assistant"),
        ("Microsoft OneDrive", "OneDriveSetup"),
        ("Python 3.12.10 (64-bit)", "python-3.12.10-amd64"),   # the installer the uninstall entry names
    ])
    def test_junk_is_left_out(self, name, process):
        assert picker_is_not_an_app(name, process)

    @pytest.mark.parametrize("name,process", [
        ("Discord", "Discord"), ("Steam", "steam"), ("Roblox Player", "RobloxPlayerBeta"),
        ("Google Chrome", "chrome"), ("Notion", "Notion"), ("Cursor", "Cursor"),
        ("Modrinth App", "Modrinth App"), ("VMware Workstation Pro", "vmware"),
        ("Canva", "Canva"), ("FxSound", "FxSound"), ("Parsec", "parsecd"),
        ("Python 3.12 (64-bit)", "python"), ("OneDrive", "OneDrive"),
    ])
    def test_real_apps_stay(self, name, process):
        assert not picker_is_not_an_app(name, process)

    def test_the_mirror_matches_the_app(self):
        root = Path(SERVER_DIR).parent / "DesktopApp"
        picker = (root / "Models" / "AppPicker.cs").read_text(encoding="utf-8")
        for word in JUNK_NAME_WORDS + JUNK_PROCESS_WORDS:
            assert f'"{word}"' in picker, word
        catalog = (root / "Services" / "AppCatalog.cs").read_text(encoding="utf-8")
        assert "AppPicker.IsNotAnApp(name, process)" in catalog


# ================================== Store and Xbox apps (#348)

class TestStoreAppsAreBlockedTimidly:
    """
    #348. A classic Store app's window belongs to ApplicationFrameHost, which
    frames every Store app at once; the app's own process has no main window.
    The blocker finds the app behind the frame, asks the frame to close, and
    never touches the frame host itself.
    """

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    BLOCKER = DESKTOP / "Services" / "AppBlockerService.cs"
    WINDOWS = DESKTOP / "Services" / "PackagedWindows.cs"
    CATALOG = DESKTOP / "Services" / "AppCatalog.cs"
    MODEL = DESKTOP / "Models" / "PackagedApp.cs"

    def critical(self) -> set[str]:
        import re
        source = self.BLOCKER.read_text(encoding="utf-8")
        start = source.index("HashSet<string> CriticalProcesses")
        block = source[source.index("{", start):source.index("};", start)]
        return {name.lower() for name in re.findall(r'"([^"]+)"', block)}

    def shared_hosts(self) -> set[str]:
        import re
        source = self.MODEL.read_text(encoding="utf-8")
        start = source.index("HashSet<string> SharedHosts")
        block = source[source.index("{", start):source.index("};", start)]
        return {name.lower() for name in re.findall(r'"([^"]+)"', block)}

    def test_the_frame_host_is_never_closed(self):
        assert "applicationframehost" in self.critical()
        assert "applicationframehost" in self.shared_hosts()

    def test_no_suggestion_is_a_shared_host(self):
        import json
        data = json.loads((self.DESKTOP / "Data" / "app_suggestions.json").read_text(encoding="utf-8"))
        hosts = self.shared_hosts()
        assert {"gamelaunchhelper", "wwahost"} <= hosts
        for group in data["groups"]:
            for app in group["apps"]:
                for process in app["processes"]:
                    assert process.lower() not in hosts, f"{app['name']} suggests shared host {process}"

    def test_the_frame_lookup_only_reads_and_asks(self):
        source = self.WINDOWS.read_text(encoding="utf-8")
        for forbidden in ("Kill(", "TerminateProcess", "OpenProcess", "SendMessage(", "Process."):
            assert forbidden not in source, f"PackagedWindows must not use {forbidden}"
        assert "WM_CLOSE = 0x0010" in source and "PostMessage(frame, WM_CLOSE" in source

    def test_graceful_close_falls_back_to_the_frame(self):
        source = self.BLOCKER.read_text(encoding="utf-8")
        ask = "process.CloseMainWindow() || PackagedWindows.CloseFramesOf(process.Id)"
        sweep = source.split("private void Tick", 1)[1].split("if (!graceful)", 1)[1]
        assert sweep.index(ask) < sweep.index("KillAll(processes, shield);", sweep.index(ask))
        soft = source.split("public int AskToClose(", 1)[1].split("\n    }", 1)[0]
        assert ask in soft

    def test_the_soft_notice_names_the_app_inside_a_frame(self):
        source = self.BLOCKER.read_text(encoding="utf-8")
        body = source.split("private void ReportForeground(", 1)[1].split("\n    }", 1)[0]
        resolve = body.index("PackagedWindows.AppProcessBehind(window)")
        assert resolve < body.index("Process.GetProcessById((int)pid)")
        # Basalt's own windows are still checked after the swap.
        assert resolve < body.index("pid == (uint)Environment.ProcessId")

    def test_the_picker_reads_store_apps_per_user_and_skips_windows(self):
        source = self.CATALOG.read_text(encoding="utf-8")
        assert 'Safely("Store apps", () => found.AddRange(StoreApps()))' in source
        body = source.split("private static IEnumerable<PickerEntry> StoreApps()", 1)[1].split("\n    }\n", 1)[0]
        assert "Registry.CurrentUser" in body and "Registry.LocalMachine" not in body
        assert "IsUnderWindows(folder)" in body
        assert "AppPicker.IsNotAnApp(" in body

    def test_running_store_apps_are_found_through_their_frames(self):
        source = self.CATALOG.read_text(encoding="utf-8")
        running = source.split("private static IEnumerable<PickerEntry> Running()", 1)[1].split(
            "private static IEnumerable<PickerEntry> StoreApps()", 1)[0]
        assert "PackagedWindows.Frames()" in running
        assert "IsUnderWindows(path)" in running.split("PackagedWindows.Frames()", 1)[1]
