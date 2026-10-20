# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 3: blocking."""

from __future__ import annotations
import os
import subprocess
import time
from pathlib import Path
import pytest
from core.installed_apps import STEAM_INSTALLED
from config import TEST_BLOCK_APP
from core import state_verifier as verify

pytestmark = pytest.mark.ui



# ============================================================= blocked apps

class TestBlockedApps:
    def test_adding_an_app_shows_it_in_the_list(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)
        names = fresh_app.blocked_app_names()
        assert any(TEST_BLOCK_APP.lower() in n.lower() for n in names), names

    def test_adding_an_app_persists_it_to_disk(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)
        result = verify.verify_blocked_app_persisted(TEST_BLOCK_APP)
        assert result.ok, result.detail

    def test_a_duplicate_is_refused(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.6)
        before = len(fresh_app.blocked_app_names())

        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)
        after = len(fresh_app.blocked_app_names())

        assert after == before, "the same process was added twice"

    def test_there_is_no_blocked_app_limit(self, fresh_app):
        """The old free tier stopped at three; the trial and a purchase have no cap."""
        fresh_app.navigate_to_tab("Blocked Apps")
        expected = {f"limit-probe-{index}" for index in range(5)}
        for index in range(5):
            assert fresh_app.add_blocked_app(f"limit-probe-{index}"), f"Add disabled for app {index}"
            time.sleep(0.5)

        saved = {app["ProcessName"] for app in verify.read_settings()["BlockedApps"]}
        assert saved == expected, f"blocked apps were not all persisted: {saved}"
        names = fresh_app.blocked_app_names()
        assert len(names) == 5, f"only {len(names)} of 5 apps were added: {names}"

    def test_removing_an_app_takes_it_off_the_list_and_disk(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)
        assert verify.verify_blocked_app_persisted(TEST_BLOCK_APP).ok

        fresh_app.remove_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)

        names = fresh_app.blocked_app_names()
        assert not any(TEST_BLOCK_APP.lower() in n.lower() for n in names), names
        assert not verify.verify_blocked_app_persisted(TEST_BLOCK_APP).ok

    def test_a_protected_system_process_cannot_be_blocked(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app("explorer")
        time.sleep(0.8)

        names = " ".join(fresh_app.blocked_app_names()).lower()
        assert "explorer" not in names, "explorer.exe must never be blockable"


# ==================================================== blocklist profiles (F9)

class TestBlocklistProfiles:
    """
    A profile is a named blocklist, and a sprint enforces the active one only —
    the checklist's Done-when for F9: switch profile, start a sprint, check that
    only that profile's app is blocked.
    """

    OTHER_TARGET = "flowshield-test-target-two"

    def test_the_default_profile_holds_todays_list(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)

        settings = verify.read_settings()
        profiles = settings["Profiles"]
        assert len(profiles) == 1 and profiles[0]["Name"] == "Default", profiles
        names = [a["ProcessName"] for a in profiles[0]["Apps"]]
        assert TEST_BLOCK_APP in names, names
        assert settings["ActiveProfileId"] == profiles[0]["Id"]

    def test_a_new_profile_starts_from_the_list_on_screen(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)

        fresh_app.new_profile("School")
        time.sleep(0.8)

        names = fresh_app.blocked_app_names()
        assert any(TEST_BLOCK_APP.lower() in n.lower() for n in names), names

        settings = verify.read_settings()
        assert [p["Name"] for p in settings["Profiles"]] == ["Default", "School"]

    def test_the_list_edits_the_selected_profile_only(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)
        fresh_app.new_profile("School")
        time.sleep(0.8)

        # Swap School's target for a different one.
        fresh_app.remove_blocked_app(TEST_BLOCK_APP)
        fresh_app.add_blocked_app(self.OTHER_TARGET)
        time.sleep(0.8)

        settings = verify.read_settings()
        by_name = {p["Name"]: [a["ProcessName"] for a in p["Apps"]] for p in settings["Profiles"]}
        assert by_name["Default"] == [TEST_BLOCK_APP], by_name
        assert by_name["School"] == [self.OTHER_TARGET], by_name

    def test_the_last_profile_cannot_be_deleted(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        time.sleep(0.5)
        # DeleteProfileButton is bound straight to DeleteProfileCommand with no
        # separate IsEnabled — WPF disables the control itself when CanExecute
        # is false, so UI Automation cannot invoke it (unlike a merely-covered
        # control, #134's Invoke-through-an-overlay case). The refusal already
        # lives in the view model (CLAUDE.md: "a gate must refuse in the view
        # model, not only by covering the screen"); disabled is the proof.
        assert not fresh_app.is_control_enabled("DeleteProfileButton"), \
            "Delete must refuse when it is the only profile"

        settings = verify.read_settings()
        assert len(settings["Profiles"]) == 1, "the only profile must survive Delete"

    def test_today_names_the_profile_the_next_sprint_will_use(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.new_profile("School")
        time.sleep(0.8)

        fresh_app.navigate_to_tab("Today")
        assert "School" in fresh_app.today_profile_caption()

    def _decoy(self, tmp_path, name: str) -> subprocess.Popen:
        """A harmless stand-in process under a given name, as TestPreSprintWarning does."""
        import shutil

        exe = tmp_path / f"{name}.exe"
        shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "PING.EXE", exe)
        return subprocess.Popen(
            [str(exe), "-n", "300", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_a_firm_sprint_blocks_only_the_active_profiles_app(self, fresh_app, tmp_path):
        """
        The Done-when. Default blocks one target, School blocks another; with
        School active, a Firm sprint closes School's target and leaves
        Default's running.
        """
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.6)
        fresh_app.new_profile("School")
        time.sleep(0.6)
        fresh_app.remove_blocked_app(TEST_BLOCK_APP)
        fresh_app.add_blocked_app(self.OTHER_TARGET)
        time.sleep(0.6)

        # Two harmless stand-ins, one per profile.
        default_target = self._decoy(tmp_path, TEST_BLOCK_APP)
        school_target = self._decoy(tmp_path, self.OTHER_TARGET)
        try:
            fresh_app.navigate_to_tab("Today")
            assert "School" in fresh_app.today_profile_caption()
            fresh_app.select_shield("Firm")
            fresh_app.start_sprint()

            # Wait for the outcome, not for a duration (#146): School's target
            # going away is the signal.
            deadline = time.time() + 30
            while time.time() < deadline and school_target.poll() is None:
                time.sleep(0.5)

            assert school_target.poll() is not None, \
                "the active profile's app was left running"
            assert default_target.poll() is None, \
                "an app on another profile was closed; only the active profile is enforced"
        finally:
            for process in (default_target, school_target):
                if process.poll() is None:
                    process.kill()
            fresh_app.stop_sprint()

    def test_sealed_locks_the_profile_switcher(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.new_profile("School")
        time.sleep(0.6)

        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Sealed")
        fresh_app.start_sprint()
        fresh_app.wait_out_grace_period()

        before = verify.read_settings()["ActiveProfileId"]
        fresh_app.navigate_to_tab("Blocked Apps")
        # The switcher's whole row is IsEnabled="{Binding CanSwitchProfile}",
        # so a genuinely disabled WPF control cannot be Invoked through UI
        # Automation either (unlike #134's merely-covered-but-enabled case) —
        # the disabled state itself is the proof the lock holds in the view
        # model, not just on screen.
        assert not fresh_app.is_control_enabled("Profile_Default"), \
            "Sealed must disable the profile switcher"
        time.sleep(0.8)

        assert verify.read_settings()["ActiveProfileId"] == before, \
            "Sealed must keep the active profile until the sprint ends"
        # stop_sprint() clicks StopSprintButton, which lives on Today — the
        # test is still on Blocked Apps from the assertion above.
        fresh_app.navigate_to_tab("Today")
        fresh_app.stop_sprint()


# ============================================================== sprint flow

class TestPreSprintWarning:
    """
    F7 / roadmap 1.8: a blocked app already open is named before the sprint
    starts, with the choice to close it first or go ahead.
    """

    TARGET = "flowshield-test-target"

    def _decoy(self, tmp_path):
        import shutil
        exe = tmp_path / f"{self.TARGET}.exe"
        shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "PING.EXE", exe)
        return subprocess.Popen(
            [str(exe), "-n", "300", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def _arm(self, app):
        app.navigate_to_tab("Blocked Apps")
        assert app.add_blocked_app(self.TARGET)
        time.sleep(0.6)
        app.navigate_to_tab("Today")
        app.choose("Shield_Firm")
        time.sleep(0.4)

    def test_an_open_blocked_app_is_named_before_the_sprint_starts(self, fresh_app, tmp_path):
        process = self._decoy(tmp_path)
        try:
            self._arm(fresh_app)
            fresh_app.start_sprint(confirm_open_apps=False)
            time.sleep(1.0)

            assert fresh_app.exists("RunningAppsTitle", timeout=5), (
                "a blocked app was already open and nothing said so"
            )
            # The app title-cases display names, so compare without case.
            listed = fresh_app.text_of("RunningAppsList")
            assert self.TARGET.lower() in listed.lower(), listed

            # Nothing has started yet — the panel is a question, not a countdown.
            assert not fresh_app.exists("StopSprintButton", timeout=1)
            assert process.poll() is None, "nothing may be closed before the answer"
        finally:
            if process.poll() is None:
                process.kill()

    def test_start_anyway_starts_the_sprint(self, fresh_app, tmp_path):
        process = self._decoy(tmp_path)
        try:
            self._arm(fresh_app)
            fresh_app.start_sprint(confirm_open_apps=False)
            assert fresh_app.exists("RunningAppsTitle", timeout=5)

            fresh_app.click("StartAnywayButton")
            time.sleep(1.5)

            assert not fresh_app.exists("RunningAppsTitle", timeout=1)
            assert fresh_app.exists("StopSprintButton", timeout=5), "the sprint should be running"
        finally:
            if process.poll() is None:
                process.kill()

    def test_the_panel_does_not_come_back_after_it_is_answered(self, fresh_app, tmp_path):
        """
        Both answers call back into the start path. Without the latch that is a
        loop the customer cannot get out of.
        """
        process = self._decoy(tmp_path)
        try:
            self._arm(fresh_app)
            fresh_app.start_sprint(confirm_open_apps=False)
            assert fresh_app.exists("RunningAppsTitle", timeout=5)
            fresh_app.click("CloseThemNowButton")
            time.sleep(2.0)
            assert not fresh_app.exists("RunningAppsTitle", timeout=2), (
                "answering the panel must not put it straight back up"
            )
            assert fresh_app.exists("StopSprintButton", timeout=5)
        finally:
            if process.poll() is None:
                process.kill()


class TestFirmWarnsBeforeClosing:
    """
    F7 / roadmap 1.8: Firm asks a blocked app to close, gives it a few seconds
    to save, and only then forces it.

    The suite runs with --short-timers, so the grace period is 2 s rather than
    10. The point being tested is that a warning happens at all and that the
    app outlives it briefly — not the exact duration, which is tier 1's job.
    """

    TARGET = "flowshield-test-target"

    def _decoy(self, tmp_path):
        import shutil
        exe = tmp_path / f"{self.TARGET}.exe"
        shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "PING.EXE", exe)
        return subprocess.Popen(
            [str(exe), "-n", "300", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_the_app_is_warned_and_survives_the_grace_period(self, fresh_app, tmp_path):
        process = self._decoy(tmp_path)
        try:
            fresh_app.navigate_to_tab("Blocked Apps")
            assert fresh_app.add_blocked_app(self.TARGET)
            time.sleep(0.6)

            fresh_app.navigate_to_tab("Today")
            fresh_app.choose("Shield_Firm")
            time.sleep(0.4)
            fresh_app.start_sprint()

            # The warning names the app and says how long there is to save.
            warned = ""
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    text = fresh_app.text_of("ToastText", timeout=1)
                except Exception:
                    text = ""
                if "closing in" in text:
                    warned = text
                    break
                time.sleep(0.5)

            assert warned, "a blocked app must be warned before it is closed"
            assert self.TARGET.lower() in warned.lower(), warned
            assert "Save your work." in warned, warned

            # And it is still there while that warning is on screen — which is
            # the entire difference from the old behaviour.
            assert process.poll() is None, (
                "the app was killed before its grace period; the warning would "
                "have been a lie"
            )

            deadline = time.time() + 25
            while time.time() < deadline and process.poll() is None:
                time.sleep(1)
            assert process.poll() is not None, "the grace period must end in a close"
        finally:
            if process.poll() is None:
                process.kill()

    def test_hard_kill_gives_no_warning(self, fresh_app, tmp_path):
        """
        The setting exists so there is no window to slip through. If this ever
        starts warning, the feature people turned on has quietly gone away.
        """
        process = self._decoy(tmp_path)
        try:
            fresh_app.navigate_to_tab("Blocked Apps")
            assert fresh_app.add_blocked_app(self.TARGET)
            time.sleep(0.4)

            fresh_app.navigate_to_tab("Settings")
            assert fresh_app.set_toggle("HardKillModeToggle", True) is True
            time.sleep(0.4)

            fresh_app.navigate_to_tab("Today")
            fresh_app.choose("Shield_Firm")
            time.sleep(0.4)
            fresh_app.start_sprint()

            deadline = time.time() + 20
            seen = []
            while time.time() < deadline and process.poll() is None:
                try:
                    seen.append(fresh_app.text_of("ToastText", timeout=1))
                except Exception:
                    pass
                time.sleep(0.5)

            assert process.poll() is not None, "hard kill must still close the app"
            assert not any("closing in" in t for t in seen), (
                f"hard kill must not warn first; saw {seen}"
            )
        finally:
            if process.poll() is None:
                process.kill()


class TestDistractionsAreCountedPerApp:
    """
    One app closing is one distraction, however many processes it runs.

    Steam runs seven; closing it once was reported as seven distractions, which
    made the number grow with an app's implementation rather than with anything
    the customer did (#138). Every process is still closed — what changed is the
    counting.

    This is the first tier 3 test that puts a real process in front of the
    blocker. `flowshield-test-target` was only ever a name on the blocklist
    before, so nothing exercised enforcement end to end.
    """

    TARGET = "flowshield-test-target"

    def _decoys(self, tmp_path, count=3):
        """
        Several processes of ONE blocked app.

        They share an executable name on purpose: that is what makes them one
        app with several processes, which is the case this test exists for.
        Copies of ping, which sits quietly for as long as it is asked to and
        has no window to steal focus.
        """
        import shutil
        exe = tmp_path / f"{self.TARGET}.exe"
        shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "PING.EXE", exe)
        return [
            subprocess.Popen(
                [str(exe), "-n", "300", "127.0.0.1"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for _ in range(count)
        ]

    def test_closing_one_app_counts_one_distraction(self, fresh_app, tmp_path):
        processes = self._decoys(tmp_path)
        try:
            fresh_app.navigate_to_tab("Blocked Apps")
            assert fresh_app.add_blocked_app(self.TARGET)
            time.sleep(0.6)

            fresh_app.navigate_to_tab("Today")
            assert fresh_app.text_of("BlocksTodayValue") == "0"

            fresh_app.choose("Shield_Firm")
            time.sleep(0.4)
            fresh_app.start_sprint()

            # The blocker sweeps every two seconds; give it several.
            deadline = time.time() + 25
            while time.time() < deadline:
                if all(p.poll() is not None for p in processes):
                    break
                time.sleep(1)

            alive = [p.pid for p in processes if p.poll() is None]
            assert not alive, (
                f"every process of a blocked app must be closed; {len(alive)} "
                f"survived. Deduplicating the count must never skip a kill."
            )

            time.sleep(2.5)
            counted = fresh_app.text_of("BlocksTodayValue")
            assert counted == "1", (
                f"{len(processes)} processes of one blocked app were closed; the "
                f"customer should see one distraction, not {counted}"
            )
        finally:
            for p in processes:
                if p.poll() is None:
                    p.kill()


# ============================================================ app picker (F8)

class TestAppPicker:
    def _saved(self, process: str) -> dict:
        apps = verify.read_settings()["BlockedApps"]
        return next(a for a in apps if a["ProcessName"].lower() == process)

    @pytest.mark.skipif(not STEAM_INSTALLED, reason="the picker lists Steam only where it is installed")
    def test_blocking_steam_from_suggestions_saves_all_its_processes(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.set_text("AppSearchInput", "steam")
        time.sleep(0.6)
        fresh_app.click("PickApp_steam")
        time.sleep(1.0)

        steam = self._saved("steam")
        assert steam["Name"] == "Steam"
        assert [p.lower() for p in steam["ExtraProcessNames"]] == ["steamwebhelper"]
        assert any("Steam" in n for n in fresh_app.blocked_app_names())
        assert fresh_app.text_of("PickApp_steam") == "Steam is blocked"
        assert fresh_app.is_control_enabled("PickApp_steam") is False, "Steam could be added twice"

    def test_typing_a_known_process_gets_the_whole_app(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app("steamwebhelper")
        time.sleep(1.0)
        helper = self._saved("steamwebhelper")
        assert helper["Name"] == "Steam" and [p.lower() for p in helper["ExtraProcessNames"]] == ["steam"]

    def test_searching_for_a_protected_process_explains_why_it_is_missing(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.set_text("AppSearchInput", "explorer")
        time.sleep(0.6)
        assert "never closes windows system processes" in fresh_app.text_of("AppSearchNotice").lower()
        assert not fresh_app.exists("PickApp_explorer", timeout=1)

    def test_browsers_carry_the_warning(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.set_text("AppSearchInput", "edge")
        deadline = time.time() + 10
        items = []
        while time.time() < deadline:
            try:
                items = fresh_app.element("AppPickerList", timeout=1).children()
            except Exception:
                items = []
            if items:
                break
            time.sleep(0.2)
        assert items, "the Edge suggestion should appear in the app picker"
        texts = " ".join(t for item in items for t in item.texts())
        assert "closes the whole browser" in texts.lower(), texts
