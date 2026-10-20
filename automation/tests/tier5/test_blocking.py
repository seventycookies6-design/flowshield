# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: blocking."""

from __future__ import annotations
import re
import shutil
import subprocess
import time
from pathlib import Path
import psutil
import pytest
from core.installed_apps import STEAM_INSTALLED
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from core import state_verifier as verify
from ._helpers import DESKTOP



# ============================== blocklist is not enumerated across threads

class TestBlocklistThreadSafety:
    """
    The watcher ran on a timer thread and enumerated the same List<BlockedApp>
    the UI thread adds to and removes from. An enumeration racing a mutation
    throws "Collection was modified" from inside a timer callback.
    """

    def test_the_watcher_uses_a_private_snapshot(self):
        source = (Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs").read_text(
            encoding="utf-8")
        tick = source.split("private void Tick()")[1].split("\n    }")[0]

        assert "settings.BlockedApps" not in tick, (
            "Tick must not enumerate AppSettings.BlockedApps directly — the UI "
            "thread mutates that list"
        )
        assert "_targets" in tick, "Tick should read the snapshot rebuilt by UpdateSettings"

    def test_updating_settings_rebuilds_the_snapshot(self):
        source = (Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs").read_text(
            encoding="utf-8")
        update = source.split("public void UpdateSettings")[1].split("\n    }")[0]
        assert "_targets" in update and "ToList()" in update, \
            "UpdateSettings must refresh the snapshot, or the blocklist goes stale"

    @pytest.mark.ui
    def test_rapid_blocklist_edits_do_not_destabilise_the_app(self, fresh_app):
        """Churn the list while the watcher is running and confirm it survives."""
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()          # watcher now enumerating every 2s
        time.sleep(1.0)

        fresh_app.navigate_to_tab("Blocked Apps")
        for index in range(3):
            fresh_app.add_blocked_app(f"churn-{index}")
            time.sleep(0.4)
        for index in range(3):
            fresh_app.remove_blocked_app(f"churn-{index}")
            time.sleep(0.4)

        assert fresh_app.current_page_title() == "Blocked Apps", "the app fell over"
        assert fresh_app.blocked_app_names() == [], fresh_app.blocked_app_names()

        fresh_app.navigate_to_tab("Today")
        fresh_app.stop_sprint()
        assert "early" in fresh_app.session_state().lower()


# ================================= the blocked-app list updates on screen

class TestBlockedAppNotifies:
    """BlockCount changes while the list is visible; without INotifyPropertyChanged
    the "blocked N ×" label renders once and then never changes."""

    def test_blocked_app_raises_property_changed(self):
        source = (Path(DESKTOP_DIR) / "Models" / "AppSettings.cs").read_text(
            encoding="utf-8")
        assert "class BlockedApp : INotifyPropertyChanged" in source
        block = source.split("class BlockedApp")[1].split("public class")[0]
        assert "public int BlockCount" in block and "Raise()" in block, \
            "BlockCount must notify, or the count on screen goes stale"


# ============================ sleep blocking actually blocks

class TestSleepBlockingEnforces:
    """
    Inside the sleep window the watcher previously dropped to the Soft shield
    unless hard-kill mode was on, so a scheduled block only wrote a log line.
    Nobody is at the keyboard at 2am to be nudged.

    #197 widened this: the Firm floor used to be applied only when no sprint
    was running, so a Soft sprint through the night switched the nightly block
    off. The assertion now holds the floor itself rather than the one line that
    used to express it -- TestTheSleepWindowNeverDropsBelowFirm has the detail.
    """

    def test_sleep_window_closes_apps(self):
        source = (Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs").read_text(
            encoding="utf-8")
        tick = source.split("private void Tick()")[1].split("\n    }")[0]
        assert re.search(r"if \(sleepActive[^)]*\) shield = ShieldLevel\.Firm;", tick), \
            "a scheduled sleep block must close apps, not merely nudge"


# ============ blocking Steam left steamwebhelper running (F8, #58)

class TestEveryProcessOfAnAppIsBlocked:
    """
    A blocklist entry held one process name, so blocking Steam closed steam.exe
    and left steamwebhelper (the store and chat windows) running.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_the_blocker_matches_every_process_of_an_entry(self):
        blocker = self.read("Services", "AppBlockerService.cs")
        assert "foreach (var processName in app.AllProcessNames) targets[processName] = app;" in blocker

    def test_old_single_process_entries_are_upgraded_on_load(self):
        vm = self.read("ViewModels", "BlockedAppsViewModel.cs")
        ctor = vm.split("public BlockedAppsViewModel(MainViewModel main)")[1].split("\n    }")[0]
        # Since F9 the top-up runs over every profile's list, not just the one
        # that happens to be active — a profile you switch to must not leak
        # through steamwebhelper either.
        assert "foreach (var profile in main.Settings.Profiles)" in ctor
        assert "UpgradeToFullSuggestions(profile.Apps)" in ctor
        assert ctor.index("UpgradeToFullSuggestions") < ctor.index("Apps = new ObservableCollection")

    def test_older_settings_files_still_load(self):
        model = self.read("Models", "AppSettings.cs")
        assert "public List<string> ExtraProcessNames { get; set; } = new();" in model

    @pytest.mark.ui
    @pytest.mark.skipif(not STEAM_INSTALLED, reason="the picker lists Steam only where it is installed")
    def test_a_firm_sprint_closes_steams_helper_too(self, fresh_app, tmp_path):
        import shutil
        import subprocess

        import psutil

        # A harmless stand-in: Windows' own ping, renamed to Steam's helper.
        helper = tmp_path / "steamwebhelper.exe"
        shutil.copy(Path(r"C:\Windows\System32\PING.EXE"), helper)
        proc = subprocess.Popen([str(helper), "-n", "600", "127.0.0.1"],
                                stdout=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            fresh_app.navigate_to_tab("Blocked Apps")
            fresh_app.set_text("AppSearchInput", "steam")
            time.sleep(0.6)
            fresh_app.click("PickApp_steam")
            time.sleep(0.8)

            fresh_app.navigate_to_tab("Today")
            fresh_app.select_shield("Firm")
            time.sleep(0.4)
            fresh_app.start_sprint()

            deadline = time.time() + 15
            while time.time() < deadline and psutil.pid_exists(proc.pid) and proc.poll() is None:
                time.sleep(0.5)
            assert proc.poll() is not None, "steamwebhelper kept running during a Firm sprint on Steam"
        finally:
            if proc.poll() is None:
                proc.kill()


class TestPerAppSwitchGuard:
    """
    The per-app on/off switch is a second way to edit the blocklist, so it must
    be disabled while a Sealed sprint holds the list shut — the same guard the
    Add box and Remove button already obey.
    """

    XAML = Path(DESKTOP_DIR) / "Views" / "BlockedAppsView.xaml"
    VM = Path(DESKTOP_DIR) / "ViewModels" / "BlockedAppsViewModel.cs"

    def test_the_switch_binds_is_enabled_to_a_guard_property(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        assert 'IsEnabled="{Binding DataContext.CanEditApps' in xaml, (
            "the switch must bind IsEnabled to a guard property on the viewmodel"
        )

    def test_the_guard_depends_on_the_sealed_state(self):
        vm = self.VM.read_text(encoding="utf-8")
        assert "CanEditApps => !IsSealed" in vm, (
            "CanEditApps must be false while a Sealed sprint is running"
        )
        assert "Raise(nameof(CanEditApps))" in vm, (
            "CanEditApps must notify when sprint state changes"
        )


class TestEnforcementBookkeepingIsForgottenWhenTheWindowCloses:
    """
    #196. _present and _closingAt were only cleared by BeginEnforcing and
    StopEnforcing, which a sprint calls. The sleep window has no such moment:
    Tick returns at the "nothing to enforce" guard, which sits above the
    per-tick cleanup, so a close deadline written at 05:59 survived to 22:00 the
    next night. The first sweep of the new window then found now >= deadline and
    went straight to KillAll -- no warning, no ten seconds to save -- and
    _present kept the sighting from counting as a distraction.
    """

    SERVICE = DESKTOP / "Services" / "AppBlockerService.cs"

    def _idle_guard(self, source: str) -> str:
        match = re.search(r"if \(!enforcing && !sleepActive\)(.*?)\n        \}", source, re.S)
        if match is None:
            # The shipped one-liner form.
            match = re.search(r"if \(!enforcing && !sleepActive\)([^\n]*)", source)
        assert match, "Tick's nothing-to-enforce guard was not found; update this regex"
        return match.group(1)

    def test_the_guard_clears_what_the_last_window_saw(self):
        guard = self._idle_guard(self.SERVICE.read_text(encoding="utf-8"))
        assert "_present.Clear()" in guard and "_closingAt.Clear()" in guard, (
            "a deadline left over from the last window kills the app on sight when "
            "the next one opens"
        )

    def test_the_pre_fix_guard_is_rejected(self):
        guard = self._idle_guard(
            "        var sleepActive = IsWithinSleepWindow(settings);\n"
            "        if (!enforcing && !sleepActive) return;\n"
        )
        assert "_closingAt.Clear()" not in guard

    def test_the_grace_period_is_still_what_it_promises(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        assert "process.CloseMainWindow()" in source, "warn first"
        assert "now < deadline) continue" in source, "then wait out the grace period"
        grace = (DESKTOP / "Models" / "GracefulClose.cs").read_text(encoding="utf-8")
        assert "TimeSpan.FromSeconds(10)" in grace


class TestEmptyProfileForgetsEnforcementBookkeeping:
    """
    #269. During a sprint, switching to a profile with no enabled apps made
    Tick return before it forgot the old warning deadline and presence.
    Switching back after the grace period then killed a blocked app on its
    first sweep without a fresh warning.
    """

    SERVICE = DESKTOP / "Services" / "AppBlockerService.cs"

    def _empty_targets_branch(self, source: str) -> str:
        tick = source.split("private void Tick()", 1)
        assert len(tick) == 2, "AppBlockerService.Tick was not found; update this extraction"
        head = re.search(r"if\s*\(\s*targets\.Count\s*==\s*0\s*\)\s*", tick[1])
        assert head, "Tick's empty-targets return was not found; update this extraction"
        rest = tick[1][head.end():]
        if not rest.startswith("{"):
            return rest.split(";", 1)[0] + ";"          # the old one-line early return
        # Brace-match the block: it holds a nested lock (_gate) { ... }.
        depth = 0
        for i, ch in enumerate(rest):
            depth += ch == "{"
            depth -= ch == "}"
            if depth == 0:
                return rest[1:i]
        raise AssertionError("unbalanced braces after the empty-targets check")

    def test_empty_targets_clear_both_collections_under_the_lock(self):
        branch = self._empty_targets_branch(self.SERVICE.read_text(encoding="utf-8"))
        lock = re.search(r"lock\s*\(\s*_gate\s*\)\s*\{(?P<body>[^{}]*)\}", branch, re.S)
        assert lock, (
            "when the active profile has no enabled apps, Tick must clear its pending"
            " enforcement state under _gate before returning"
        )
        locked = lock.group("body")
        assert re.search(r"_present\s*\.\s*Clear\s*\(\s*\)", locked), (
            "an empty profile must forget which blocked apps were present"
        )
        assert re.search(r"_closingAt\s*\.\s*Clear\s*\(\s*\)", locked), (
            "an empty profile must forget old close deadlines so returning to it"
            " cannot kill an app without a fresh warning"
        )
        assert re.search(r"return\s*;", branch[lock.end():]), (
            "Tick must return after clearing pending enforcement state for an empty profile"
        )


class TestTheSleepWindowNeverDropsBelowFirm:
    """
    #197. The sleep window forced Firm only when no sprint was running
    ("sleepActive && !enforcing"), so starting a Soft sprint at 23:00 switched
    the nightly shield off for its whole length: blocked apps were noted and
    left running, which is strictly less enforcement than having no sprint at
    all. The floor belongs to the window, not to the sprint.
    """

    SERVICE = DESKTOP / "Services" / "AppBlockerService.cs"

    FLOOR = re.compile(r"if \(sleepActive[^)]*\) shield = ShieldLevel\.Firm;")

    def test_the_floor_does_not_depend_on_whether_a_sprint_is_running(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        match = self.FLOOR.search(source)
        assert match, "the sleep window's Firm floor was not found; update this regex"
        assert "!enforcing" not in match.group(0), (
            "a Soft sprint must not be able to lower the nightly shield below Firm"
        )
        assert "shield < ShieldLevel.Firm" in match.group(0), (
            "raise a weaker shield to Firm and leave Firm and Sealed alone"
        )

    def test_the_pre_fix_line_is_rejected(self):
        match = self.FLOOR.search(
            "        if (sleepActive && !enforcing) shield = ShieldLevel.Firm;\n"
        )
        assert match and "!enforcing" in match.group(0)

    def test_soft_outside_the_window_still_only_nudges(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        assert "var terminate = shield >= ShieldLevel.Firm || hardKill;" in source, (
            "Soft must still be notice-only when nothing else raises the floor"
        )


# ================================== blocklist profiles must not break anything

class TestBlocklistProfilesKeepTheirPromises:
    """
    F9 turned the one blocklist into a list of named ones. Four things had to
    survive that: a settings file written before profiles existed, Sealed's
    lock (now over the switcher as well as the list), enforcement reading one
    profile and not the union of all of them, and every `AutomationId` the
    suite already drives.
    """

    APP_SETTINGS = (DESKTOP_DIR / "Models" / "AppSettings.cs").read_text(encoding="utf-8")
    BLOCKER = (DESKTOP_DIR / "Services" / "AppBlockerService.cs").read_text(encoding="utf-8")
    BLOCKED_VM = (DESKTOP_DIR / "ViewModels" / "BlockedAppsViewModel.cs").read_text(encoding="utf-8")
    TODAY_VM = (DESKTOP_DIR / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
    BLOCKED_XAML = (DESKTOP_DIR / "Views" / "BlockedAppsView.xaml").read_text(encoding="utf-8")
    TODAY_XAML = (DESKTOP_DIR / "Views" / "TodayView.xaml").read_text(encoding="utf-8")

    # ------------------------------------------ an old settings file still loads

    def test_the_old_settings_shape_still_has_a_home(self):
        """
        `BlockedApps` is the only blocklist a pre-F9 settings file has. It must
        still be a serialized property (not [JsonIgnore], not renamed), or every
        existing customer opens Basalt to an empty blocklist.
        """
        blocked = self.APP_SETTINGS.split("public List<BlockedApp> BlockedApps")[1].split("\n    }")[0]
        assert "set => _legacyBlockedApps = value;" in blocked
        declaration = self.APP_SETTINGS.split("public List<BlockedApp> BlockedApps")[0]
        assert not declaration.rstrip().endswith("[JsonIgnore]"), \
            "BlockedApps must stay serializable, or an old settings file has nowhere to land"

    def test_the_old_name_still_answers_with_the_list_in_use(self):
        """
        Everything written before F9 — the first run, the privacy export, the
        UI tests reading settings["BlockedApps"] — asks for BlockedApps and must
        get the profile actually being enforced.
        """
        blocked = self.APP_SETTINGS.split("public List<BlockedApp> BlockedApps")[1].split("\n    }")[0]
        assert "get => ActiveProfile.Apps;" in blocked

    def test_a_settings_file_with_no_profiles_is_migrated_not_emptied(self):
        ensure = self.APP_SETTINGS.split("public bool EnsureProfiles()")[1].split("\n    }")[0]
        assert "_legacyBlockedApps ?? new List<BlockedApp>()" in ensure, \
            "the pre-F9 list becomes the Default profile; it is never dropped"

    # ------------------------------------------------ Sealed locks the switcher

    def test_sealed_refuses_a_profile_switch_in_the_view_model(self):
        """
        Not by disabling the chips alone: UI Automation can still invoke a
        disabled or covered control (#134), so the refusal has to be in the
        view model, the same as the list's own Sealed guard.
        """
        switch = self.BLOCKED_VM.split("private void SelectProfile(BlocklistProfile? profile)")[1].split(
            "\n    }")[0]
        assert "if (IsSealed)" in switch
        assert "SetActiveProfile" in switch
        assert switch.index("if (IsSealed)") < switch.index("SetActiveProfile"), \
            "the Sealed check must come before the switch, not after it"

    def test_the_switcher_is_also_disabled_while_sealed(self):
        assert "public bool CanSwitchProfile => !IsSealed && !_main.IsLocked;" in self.BLOCKED_VM
        assert 'IsEnabled="{Binding CanSwitchProfile}"' in self.BLOCKED_XAML
        assert 'IsEnabled="{Binding CanSwitchProfile}"' in self.TODAY_XAML

    def test_renaming_duplicating_and_deleting_are_sealed_too(self):
        """A Sealed sprint's blocklist cannot be renamed out from under it either."""
        guard = self.BLOCKED_VM.split("private bool GuardProfileEdit()")[1].split("\n    }")[0]
        assert "if (IsSealed)" in guard
        for command in ("RenameProfileCommand", "DuplicateProfileCommand", "DeleteProfileCommand"):
            line = self.BLOCKED_VM.split(f"{command} = new RelayCommand(")[1].split(";")[0]
            assert "CanEditProfiles" in line or "CanDeleteProfile" in line, \
                f"{command} must be refused while Sealed"
        assert "public bool CanEditProfiles => !IsSealed" in self.BLOCKED_VM
        assert "public bool CanDeleteProfile => CanEditProfiles" in self.BLOCKED_VM

    def test_a_resumed_sprint_comes_back_on_the_profile_it_started_with(self):
        """Otherwise a restart is a way round Sealed's lock (F3 + F9)."""
        assert "ActiveProfileId = S.ActiveProfile.Id," in self.TODAY_VM, \
            "the running sprint record must name the profile it is enforcing"
        resume = self.TODAY_VM.split("case SprintResume.Resume:")[1].split("break;")[0]
        assert "SetActiveProfile(saved.ActiveProfileId)" in resume

    # -------------------------------------- enforcement uses one profile only

    def test_the_blocker_enforces_the_active_profile_and_nothing_else(self):
        assert "_targets = settings.ActiveProfile.Apps.ToList();" in self.BLOCKER
        # The pre-sprint look reads one profile: the active one before Start
        # (F7), or a scheduled template's own list for its heads-up (F6),
        # which is the one that becomes active when the template starts.
        assert "RunningBlockedApps(settings.ActiveProfile);" in self.BLOCKER
        assert "foreach (var app in profile.Apps)" in self.BLOCKER
        assert "settings.Profiles" not in self.BLOCKER, \
            "the shield must never walk every profile — only the active one is enforced"

    def test_adds_and_removes_land_on_the_selected_profile_only(self):
        assert "ActiveApps.Add(app);" in self.BLOCKED_VM
        assert "ActiveApps.RemoveAll(a =>" in self.BLOCKED_VM
        assert "_main.Settings.BlockedApps.Add(" not in self.BLOCKED_VM

    def test_today_says_which_blocklist_the_next_sprint_uses(self):
        assert 'AutomationProperties.AutomationId="TodayProfileCaption"' in self.TODAY_XAML
        assert '$"Blocking: {ActiveProfile.Name}"' in self.BLOCKED_VM

    # ------------------------------------------------ the existing ids survive

    @pytest.mark.parametrize("auto_id", [
        "NewAppNameInput", "AddAppButton", "BlockedAppsList", "BlockedAppsStatusText",
        "BlockedAppsEmptyText", "AppSearchInput", "AppSearchNotice", "AppPickerList",
        "RefreshProcessesButton",
    ])
    def test_every_blocked_apps_id_the_suite_drives_is_still_there(self, auto_id):
        assert f'AutomationProperties.AutomationId="{auto_id}"' in self.BLOCKED_XAML

    def test_the_per_row_ids_keep_their_shape(self):
        assert "StringFormat=RemoveApp_{0}" in self.BLOCKED_XAML
        assert "StringFormat=AppEnabledSwitch_{0}" in self.BLOCKED_XAML

    @pytest.mark.parametrize("auto_id", [
        "ProfileNameInput", "RenameProfileButton", "NewProfileButton",
        "DuplicateProfileButton", "DeleteProfileButton",
        "ConfirmDeleteProfileButton", "CancelDeleteProfileButton",
    ])
    def test_the_new_profile_controls_are_all_addressable(self, auto_id):
        assert f'AutomationProperties.AutomationId="{auto_id}"' in self.BLOCKED_XAML

    def test_the_new_ids_sit_on_controls_not_layout_panels(self):
        """#134: an id on a Border or a StackPanel is never surfaced."""
        for marker, control in (
            ('AutomationId="ProfileNameInput"', "TextBox"),
            ('AutomationId="NewProfileButton"', "Button"),
            ('AutomationId="DeleteProfileButton"', "Button"),
        ):
            before = self.BLOCKED_XAML.split(marker)[0]
            opening = before.rstrip().rsplit("<", 1)[-1].split()[0]
            assert opening == control, f"{marker} sits on <{opening}>, not <{control}>"


class TestQuickStartBringsOpenAppQuestionForward:
    """
    Issue #270: when a blocked app is already open, StartSprint shows F7's
    open-apps question and returns. Starting from the tray or global hotkey
    must bring that question into view instead of silently leaving it hidden.
    """

    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"

    def source(self) -> str:
        return self.WINDOW.read_text(encoding="utf-8")

    def method(self, source: str, name: str) -> str:
        match = re.search(
            rf"\bprivate\s+(?:void|IntPtr)\s+{re.escape(name)}\s*\([^)]*\)\s*\{{",
            source,
        )
        assert match, f"MainWindow must define {name}() for issue #270 quick start handling"
        depth = 1
        for index in range(match.end(), len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[match.end():index]
        assert False, f"could not find the end of MainWindow.{name}()"

    def test_the_tray_start_item_uses_quickstart(self):
        source = self.source()
        tray = self.method(source, "BuildTrayMenu")
        assert re.search(r"QuickStart\s*\(\s*\)", tray), \
            "the tray start item must use QuickStart() so F7's open-apps question is shown"

    def test_the_global_hotkey_uses_quickstart(self):
        source = self.source()
        hotkey = self.method(source, "WndProc")
        assert re.search(r"QuickStart\s*\(\s*\)", hotkey), \
            "the global hotkey must use QuickStart() so F7's open-apps question is shown"

    def test_quickstart_restores_and_selects_today_for_the_open_apps_question(self):
        source = self.source()
        quick_start = self.method(source, "QuickStart")
        assert re.search(r"StartCommand\s*\.\s*Execute\s*\(\s*null\s*\)", quick_start), \
            "QuickStart() must still execute Today.StartCommand"
        assert re.search(r"if\s*\([^)]*Today\.RunningAppsPanelVisible", quick_start), \
            "QuickStart() must detect when StartSprint shows F7's open-apps question"
        assert re.search(r"\.CurrentPage\s*=\s*AppPage\.Today", quick_start), \
            "QuickStart() must select Today when the open-apps question appears"
        assert re.search(r"\b(?:RestoreFromTray|BringToFront)\s*\(\s*\)", quick_start), \
            "QuickStart() must restore or bring the window forward for the open-apps question"


# ============================== #289 — a sweep that outlives its sprint

class TestBlockerSweepStopsWhenEnforcementEnds:
    """
    Tick copies IsEnforcing before it lists processes. A sprint ending
    (StopEnforcing) mid-sweep left that sweep closing apps during the break.
    Every close and kill must ask again, under the gate.
    """

    SOURCE = Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs"

    def _tick(self) -> str:
        source = self.SOURCE.read_text(encoding="utf-8")
        return source.split("private void Tick()", 1)[1].split("private ", 1)[0]

    def test_the_recheck_reads_enforcement_under_the_gate(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        helper = source.split("private bool StillEnforcing()", 1)[1].split("private void Tick()", 1)[0]
        assert "lock (_gate)" in helper and "IsEnforcing" in helper
        assert "IsWithinSleepWindow" in helper, "the sleep window enforces without a sprint"

    def test_every_close_and_kill_is_preceded_by_the_recheck(self):
        tick = self._tick()
        for needle in ("KillAll(processes, shield);", "process.CloseMainWindow()"):
            for match in re.finditer(re.escape(needle), tick):
                before = tick[:match.start()]
                assert "StillEnforcing()" in before[-600:], (
                    f"{needle} must be preceded by a StillEnforcing() check (#289)")

    def test_the_sweep_rechecks_before_reporting_each_app(self):
        tick = self._tick()
        loop = tick.split("foreach (var (key, entry) in running)", 1)[1]
        assert "StillEnforcing()" in loop.split("bool firstSighting;", 1)[0]
class TestSealedToastNamesTheApp:
    """#324: removing or switching off a listed app mid-sprint names it in the refusal."""

    SOURCE = Path(DESKTOP_DIR) / "ViewModels" / "BlockedAppsViewModel.cs"

    def _source(self):
        return self.SOURCE.read_text(encoding="utf-8")

    def _method(self, signature):
        return self._source().split(signature, 1)[1].split("\n    }", 1)[0]

    def test_the_named_and_general_sentences(self):
        helper = self._method("public static string SealedToast(")
        assert '$"{appName} and other blocklisted apps are sealed until this sprint ends."' in helper
        assert '"The blocklist is sealed until this sprint ends."' in helper
        assert "string.IsNullOrWhiteSpace(appName)" in helper, "no name falls back to the general sentence"

    @pytest.mark.parametrize("signature", [
        "private void RemoveApp(BlockedApp? app)",
        "public void ToggleApp(BlockedApp? app)",
    ])
    def test_listed_app_actions_pass_its_name(self, signature):
        assert "_main.Toast(SealedToast(app.DisplayName));" in self._method(signature)

    def test_every_sealed_refusal_goes_through_the_helper(self):
        source = self._source()
        assert source.count("sealed until this sprint ends") == 2, "only the helper's two sentences"
        assert source.count("_main.Toast(SealedToast(") == 6


@pytest.mark.ui
class TestBlockedAppsListKeepsItsViewport:
    """#377: profiles and websites consumed the default card's entire height.

    All five apps were saved, but the zero-height list exposed one stale UIA
    row and customers could not reach any of the apps they had added.
    """

    @pytest.mark.parametrize("compact", [False, True], ids=["default", "compact"])
    def test_the_fifth_app_can_be_seen_and_removed(self, fresh_app, compact):
        if compact:
            import ctypes

            scale = ctypes.windll.user32.GetDpiForWindow(fresh_app.window.handle) / 96
            fresh_app.window.wrapper_object().iface_transform.Resize(800 * scale, 540 * scale)
        fresh_app.navigate_to_tab("Blocked Apps")
        expected = {f"limit-probe-{index}" for index in range(5)}
        for process in sorted(expected):
            assert fresh_app.add_blocked_app(process), f"Add disabled for {process}"

        def saved_apps():
            return {app["ProcessName"] for app in verify.read_settings()["BlockedApps"]}

        assert saved_apps() == expected, "every distinct blocked app must be persisted"
        bounds = fresh_app.element("BlockedAppsList").rectangle()
        assert bounds.height() > 0 and bounds.width() > 0, "the blocked-app list has no viewport"
        assert len(fresh_app.blocked_app_names()) == 5

        scroll_id = "BlockedAppsPageScroll" if compact else "BlockedAppsScroll"
        scroll = fresh_app.element(scroll_id).iface_scroll
        last_id = "RemoveApp_limit-probe-4"

        def reveal_last_app():
            # In the stacked layout the picker follows the apps, so the last
            # app is reached before the bottom of the whole page.
            for percent in range(0, 101, 5):
                scroll.SetScrollPercent(-1, percent)
                button = fresh_app.element(last_id)
                if fresh_app._is_on_screen(button):
                    return button
                time.sleep(0.1)
            pytest.fail("the fifth row is still clipped after scrolling")

        button = reveal_last_app()

        # Wheel input over a row must scroll back to the add controls, too.
        # An inner ListBox ScrollViewer can swallow it even when it cannot scroll.
        from pywinauto import mouse

        centre = button.rectangle().mid_point()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not fresh_app._is_on_screen(fresh_app.element("AddAppButton")):
            mouse.scroll(coords=(centre.x, centre.y), wheel_dist=1)
        assert fresh_app._is_on_screen(fresh_app.element("AddAppButton")), "wheel input is trapped in the app list"

        button = reveal_last_app()
        # A real click proves reachability; Invoke can act on a clipped control.
        button.click_input()

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and saved_apps() != expected - {"limit-probe-4"}:
            time.sleep(0.1)
        assert saved_apps() == expected - {"limit-probe-4"}
