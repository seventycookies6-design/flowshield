"""
Tier 3 — end-to-end through the real UI.

These drive the shipped binary with UI Automation and check that what the UI
claims matches what was actually persisted to the DPAPI-encrypted settings file.
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core.installed_apps import STEAM_INSTALLED

from config import TEST_BLOCK_APP
from core import state_verifier as verify

pytestmark = pytest.mark.ui


# ================================================================ app shell

class TestAppShell:
    def test_window_opens_on_the_today_page(self, app):
        assert app.current_page_title() == "Today"

    @pytest.mark.parametrize("tab", ["History", "Blocked Apps", "Schedule",
                                     "Settings", "Today"])
    def test_every_tab_is_reachable(self, app, tab):
        assert app.navigate_to_tab(tab) == tab

    def test_a_clean_install_starts_the_seven_day_trial(self, app):
        app.navigate_to_tab("Settings")
        assert "free trial — 7 days left" in app.get_license_status_text().lower()
        assert app.tier_badge().upper() == "TRIAL · 7 DAYS LEFT"
        # The panel is a Border, which UI Automation can't see; its button can be.
        assert not app.exists("LockBuyButton", timeout=1.5), "a new install is locked"

        settings = verify.read_settings()
        assert settings.get("TrialStartedUtc"), "the trial start was not saved"

    def test_the_app_writes_an_encrypted_settings_file(self, app):
        # Touch a setting so the file definitely exists.
        app.navigate_to_tab("Blocked Apps")
        app.add_blocked_app("settings-file-probe")
        time.sleep(0.8)

        result = verify.settings_is_encrypted()
        assert result.ok, result.detail

    def test_settings_cannot_be_read_without_dpapi(self, app):
        """The on-disk bytes must not contain the plaintext payload."""
        from config import SETTINGS_PATH

        # Write a distinctive value ourselves rather than relying on a previous
        # test having run — each test gets its own wiped instance.
        marker = "plaintext-leak-canary"
        app.navigate_to_tab("Blocked Apps")
        app.add_blocked_app(marker)
        time.sleep(0.9)

        raw = SETTINGS_PATH.read_text(encoding="utf-8", errors="replace")
        assert marker not in raw, "a blocked app name appeared in plaintext on disk"

        # And it really is recoverable through DPAPI — so the test proves
        # encryption, not merely that the write failed.
        settings = verify.read_settings()
        names = [a["ProcessName"] for a in settings["BlockedApps"]]
        assert marker in names, names


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
        for index in range(5):
            fresh_app.add_blocked_app(f"limit-probe-{index}")
            time.sleep(0.5)

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


class TestSoftShowsTheNotice:
    """
    F7 / roadmap 1.7: at Soft, a blocked app coming to the front gets a
    topmost full-screen notice naming it and the time left — and the app is
    still running afterwards, unless the user chose Close (1.0.10), which asks
    it to close the way its own close button would and never kills it.

    The decoy is Character Map (charmap.exe, in System32 on every client
    Windows), run as itself and blocked as "charmap". The notice's whole
    trigger is the decoy *owning* the foreground window, and the renamed ping
    the other blocker tests use cannot, even launched with its own console: on
    Windows 11 a new console is hosted by Windows Terminal, so the foreground
    window belongs to windowsterminal — a critical process the blocker
    ignores — and the notice never appears (#250). Notepad is wrong too: it
    can hand off to the Store app and exit. Character Map is a plain Win32
    dialog: it owns its window, can be brought to the front, and answers
    WM_CLOSE (what Process.CloseMainWindow sends) by exiting normally, so
    Close's ask can be seen to land. It is not copied under a test name like
    the other decoys: its dialog template lives in en-US\\charmap.exe.mui,
    which a copy outside System32 cannot find, so a renamed copy exits at once
    with no window. A Character Map the user had open would be caught along
    with the decoy; the suite already owns the screen while it runs.

    The notice is its own top-level window, so it is found through Desktop
    rather than through the controller, which only searches the main window.
    """

    TARGET = "charmap"
    OVERLAY = "SoftOverlayWindow"

    @pytest.fixture
    def real_wait_app(self, logger):
        """
        A fresh FlowShield with the real Soft waits, not --short-timers.

        Under --short-timers Allow's wait is three seconds, still under the
        floor the suite can see into: a UIA lookup plus an IsEnabled read can
        cost a second or more, so a test asserting "still disabled" against a
        short wait would be asserting on its own speed (#242; OBSERVABLE_SECONDS
        in tier 5). The real first-try wait is five seconds, which is long
        enough to observe, and it is the wait a customer gets.
        """
        from config import APP_EXE
        from desktop.app_controller import DesktopController

        if not Path(APP_EXE).exists():
            pytest.skip(f"{APP_EXE} not built")
        ctrl = DesktopController(logger)
        ctrl.launch_app(clean_state=True, short_timers=False)
        ctrl.connect_window()
        time.sleep(1.0)
        ctrl.focus(force=True)
        yield ctrl
        ctrl.close_app()

    @staticmethod
    def _foreground_pid() -> int:
        """Which process owns the foreground window — the blocker's own question."""
        import ctypes
        user32 = ctypes.windll.user32
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
        return pid.value

    @staticmethod
    def _decoy_windows(process):
        """The decoy's visible top-level windows (the win32 backend takes a pid)."""
        from pywinauto import Desktop
        try:
            return [w for w in Desktop(backend="win32").windows(process=process.pid)
                    if w.is_visible()]
        except Exception:
            return []

    def _decoy(self):
        exe = Path(os.environ["WINDIR"]) / "System32" / f"{self.TARGET}.exe"
        if not exe.exists():
            pytest.skip(f"{exe} is not on this Windows; the notice needs a GUI decoy")
        process = subprocess.Popen([str(exe)])
        # Wait for its window, not for a duration (#146).
        deadline = time.time() + 10
        while time.time() < deadline and process.poll() is None \
                and not self._decoy_windows(process):
            time.sleep(0.2)
        assert process.poll() is None, "the decoy exited before it showed a window"
        assert self._decoy_windows(process), "the decoy never showed a window"
        return process

    def _bring_forward(self, process):
        """
        Put the decoy in the OS foreground, and prove it got there.

        Checked through GetForegroundWindow rather than assumed, so a decoy
        that cannot take focus reads as a bench problem and not as the product
        failing to notice it (#250).
        """
        windows = self._decoy_windows(process)
        assert windows, "the decoy has no window to bring forward"
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                windows[0].set_focus()
            except Exception:
                pass
            if self._foreground_pid() == process.pid:
                return
            time.sleep(0.2)
        pytest.fail("the decoy never became the foreground window, so nothing can trigger the notice")

    def _overlay(self, timeout=15):
        """The notice's window, or None. Raced, not slept on (#146)."""
        from pywinauto import Desktop

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                window = Desktop(backend="uia").window(auto_id=self.OVERLAY)
                if window.exists(timeout=0.5):
                    return window
            except Exception:
                pass
            time.sleep(0.4)
        return None

    def _first_sight_of(self, auto_id, timeout=15):
        """
        A control on the notice, sampled the moment the notice is up: one UIA
        resolution per attempt (wrapper_object polls inside pywinauto and
        returns on the first hit), because the wait it is used to observe is
        finite and every round trip spends some of it.
        """
        from pywinauto import Desktop

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                return Desktop(backend="uia").window(auto_id=self.OVERLAY) \
                    .child_window(auto_id=auto_id).wrapper_object()
            except Exception:
                pass
            time.sleep(0.02)
        return None

    @staticmethod
    def _wait_until_enabled(control, timeout):
        """Raced against a deadline rather than slept on (#146)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if control.is_enabled():
                    return True
            except Exception:
                pass
            time.sleep(0.1)
        return False

    def _arm_and_start(self, app, process):
        app.navigate_to_tab("Blocked Apps")
        assert app.add_blocked_app(self.TARGET)
        time.sleep(0.6)
        app.navigate_to_tab("Today")
        app.choose("Shield_Soft")
        time.sleep(0.4)
        app.start_sprint(confirm_open_apps=True)

        # The notice's whole trigger is the decoy being the foreground window
        # (class docstring), but arming just spent several clicks and an F7
        # answer inside FlowShield's own window, which is what actually holds
        # focus now. Hand it back.
        self._bring_forward(process)

    def test_a_blocked_app_in_front_gets_a_notice_that_closes_nothing(self, fresh_app):
        process = self._decoy()
        try:
            self._arm_and_start(fresh_app, process)

            overlay = self._overlay()
            assert overlay is not None, (
                "a blocked app was the foreground window at Soft and nothing said so"
            )

            named = overlay.child_window(auto_id="SoftOverlayText").window_text()
            assert self.TARGET.lower() in named.lower(), named
            assert "on your blocklist until" in named, named
            assert overlay.child_window(auto_id="SoftOverlayTimeLeft").exists()

            # Soft's promise: the distraction is noted, not closed.
            assert process.poll() is None, "Soft must never close the blocked app"

            overlay.child_window(auto_id="SoftOverlayBackToWorkButton").click_input()
            time.sleep(1.5)
            assert self._overlay(timeout=2) is None, "Back to work must take it down"
            assert process.poll() is None, "Back to work must not close the blocked app"
        finally:
            if process.poll() is None:
                process.kill()

    def test_enter_is_back_to_work_and_never_closes_the_app(self, fresh_app):
        """
        The notice lands up to one blocker sweep after the blocked app came to
        the front, while the user may still be typing in it. A keystroke meant
        for that app -- Enter to send a chat line, say -- must never become
        "the user chose to close it". Enter on the fresh notice is Back to
        work: nothing was asked to close, the app is still running, and the
        notice is down.
        """
        process = self._decoy()
        try:
            self._arm_and_start(fresh_app, process)

            overlay = self._overlay()
            assert overlay is not None, (
                "a blocked app was the foreground window at Soft and nothing said so"
            )
            overlay.type_keys("{ENTER}", set_foreground=True)

            # Wait for what happens (#146): Back to work is logged by name.
            went_back = f"back to work from {self.TARGET}"
            deadline = time.time() + 10
            while time.time() < deadline and not fresh_app.app_log_contains(went_back):
                time.sleep(0.25)
            assert fresh_app.app_log_contains(went_back), "Enter on the notice must be Back to work"
            assert not fresh_app.app_log_contains(f"(pid {process.pid}) to close, as the user chose"), (
                "Enter must never ask the blocked app to close"
            )
            assert process.poll() is None, "Enter must never close the blocked app"
            assert self._overlay(timeout=2) is None, "Back to work takes the notice down"
        finally:
            if process.poll() is None:
                process.kill()

    def test_allow_five_minutes_keeps_it_quiet(self, fresh_app):
        process = self._decoy()
        try:
            self._arm_and_start(fresh_app, process)

            overlay = self._overlay()
            assert overlay is not None
            # 1.0.10: Allow waits before it can be pressed (three seconds under
            # --short-timers), so a click before then would do nothing.
            allow = overlay.child_window(auto_id="SoftOverlayAllowButton")
            assert self._wait_until_enabled(allow, timeout=8), "Allow never became pressable"
            allow.click_input()
            time.sleep(1.0)

            # Back to the decoy: inside the five minutes, nothing appears.
            self._bring_forward(process)
            time.sleep(6.0)                     # three sweeps of the blocker
            assert self._overlay(timeout=2) is None, (
                "Allow 5 minutes has to mean five minutes"
            )
            assert process.poll() is None
        finally:
            if process.poll() is None:
                process.kill()

    def test_allow_is_disabled_until_the_wait_runs_out(self, real_wait_app):
        """
        1.0.10: Allow 5 minutes waits (5, 10, 20, then 30 s) before it can be
        pressed; Close works at once; the try count shows. Run with the real
        five-second first-try wait: the three-second --short-timers wait is
        shorter than the suite can observe (see real_wait_app).
        """
        process = self._decoy()
        try:
            self._arm_and_start(real_wait_app, process)

            allow = self._first_sight_of("SoftOverlayAllowButton")
            assert allow is not None, (
                "a blocked app was the foreground window at Soft and nothing said so"
            )
            assert not allow.is_enabled(), "Allow must wait before it can be pressed"

            # While Allow still waits, Close already works and the try count shows.
            overlay = self._overlay(timeout=2)
            assert overlay is not None
            close = overlay.child_window(auto_id="SoftOverlayCloseButton")
            assert close.is_enabled(), "Close works at once, with no wait"
            assert self.TARGET.lower() in close.window_text().lower(), close.window_text()
            try_line = overlay.child_window(auto_id="SoftOverlayTryLine").window_text()
            assert "1st try this sprint" in try_line, try_line

            assert self._wait_until_enabled(allow, timeout=10), "Allow's wait never ran out"
        finally:
            if process.poll() is None:
                process.kill()

    def test_close_asks_the_app_to_close_and_never_kills_it(self, fresh_app):
        """
        1.0.10: Close is the user's choice. The blocker asks the app to close
        (CloseMainWindow, so its own save prompt can appear) and never kills
        it, and the notice goes down. Character Map answers the ask by exiting
        on its own, so the exit code tells an ask from a kill: 0 for its own
        close, 4294967295 (TerminateProcess with -1) for Process.Kill.
        """
        process = self._decoy()
        try:
            self._arm_and_start(fresh_app, process)

            overlay = self._overlay()
            assert overlay is not None, (
                "a blocked app was the foreground window at Soft and nothing said so"
            )
            overlay.child_window(auto_id="SoftOverlayCloseButton").click_input()

            asked = f"(pid {process.pid}) to close, as the user chose"
            deadline = time.time() + 10
            while time.time() < deadline and not fresh_app.app_log_contains(asked):
                time.sleep(0.25)
            assert fresh_app.app_log_contains(asked), "Close must ask the blocked app to close"
            assert fresh_app.app_log_contains(f"soft notice: close {self.TARGET} chosen")

            # The app answers the ask by closing itself. Wait for that rather
            # than checking the instant the ask is logged — a wrongful kill
            # would come from a later sweep — then tell the two apart.
            deadline = time.time() + 10
            while time.time() < deadline and process.poll() is None:
                time.sleep(0.25)
            assert process.poll() is not None, "the decoy did not close when asked"
            assert process.returncode == 0, (
                f"the decoy exited with {process.returncode}: killed, not asked"
            )
            assert not fresh_app.app_log_contains(f"(pid {process.pid}) at shield"), (
                "Soft must never kill the app, even when the user chose Close"
            )
            assert self._overlay(timeout=2) is None, "Close must take the notice down"
        finally:
            if process.poll() is None:
                process.kill()

    def test_back_to_work_is_counted_on_the_card_and_in_the_saved_sprint(self, fresh_app):
        """
        1.0.10 (spec 4.3): Back to work counts as turned back, and the count
        is saved with the sprint and shown on its summary card.

        The sprint is ended early once its grace period is over, rather than
        shortened with --short-sprints: a shortened sprint is never saved
        (CycleState.SprintCountsAsProgress), so there would be no saved sprint
        to read the count from. Ending early records it and shows the same card.
        """
        process = self._decoy()
        try:
            self._arm_and_start(fresh_app, process)

            overlay = self._overlay()
            assert overlay is not None, (
                "a blocked app was the foreground window at Soft and nothing said so"
            )
            overlay.child_window(auto_id="SoftOverlayBackToWorkButton").click_input()

            # Wait for what happens (#146): Back to work is logged by name.
            went_back = f"back to work from {self.TARGET}"
            deadline = time.time() + 10
            while time.time() < deadline and not fresh_app.app_log_contains(went_back):
                time.sleep(0.25)
            assert fresh_app.app_log_contains(went_back), "Back to work was never answered"
        finally:
            # Gone before the sprint is ended, so no second notice can come up
            # over the end button (a full-screen window takes the click).
            if process.poll() is None:
                process.kill()

        fresh_app.focus(force=True)
        fresh_app.stop_sprint()                    # Soft past its grace ends at once
        assert fresh_app.exists("SummaryTitle", timeout=10), "the summary card never appeared"
        assert fresh_app.text_of("SummaryTurnedBackText") == "Turned back 1 time"

        session = verify.read_settings()["Sessions"][-1]
        assert session["Shield"] in (1, "Soft")
        assert session["TurnedBack"] == 1

    def test_firm_closes_the_app_instead_of_covering_it(self, fresh_app):
        """The notice is Soft's. Firm has seconds to save in, and a panel over
        the window being saved would be the worst possible moment for one."""
        process = self._decoy()
        try:
            fresh_app.navigate_to_tab("Blocked Apps")
            assert fresh_app.add_blocked_app(self.TARGET)
            time.sleep(0.6)
            fresh_app.navigate_to_tab("Today")
            fresh_app.choose("Shield_Firm")
            time.sleep(0.4)
            fresh_app.start_sprint(confirm_open_apps=True)

            deadline = time.time() + 25
            while time.time() < deadline and process.poll() is None:
                assert self._overlay(timeout=0.5) is None, (
                    "Firm must not show the Soft notice"
                )
                time.sleep(0.5)
            assert process.poll() is not None, "Firm still closes the app"
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


class TestSprints:
    def test_starting_a_sprint_runs_the_timer_down(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(2.5)

        timer = fresh_app.sprint_timer()
        assert timer != "25:00", f"timer did not advance (still {timer})"
        assert "engaged" in fresh_app.session_state().lower()
        fresh_app.stop_sprint()

    def test_ending_a_sprint_early_is_recorded_as_such(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(1.5)
        fresh_app.stop_sprint()
        time.sleep(0.8)
        assert "early" in fresh_app.session_state().lower()

    def test_abandoning_a_sprint_does_not_zero_momentum(self, fresh_app):
        """Momentum decays on an abandoned sprint; it must not reset to zero."""
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(1.2)
        fresh_app.stop_sprint()
        time.sleep(1.0)

        settings = verify.read_settings()
        assert settings["MomentumScore"] >= 0
        assert len(settings["Sessions"]) == 1
        assert settings["Sessions"][0]["Completed"] is False

    def test_the_journal_prompt_appears_after_a_sprint(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(1.2)
        fresh_app.stop_sprint()
        time.sleep(0.8)
        assert fresh_app.exists("JournalInput", timeout=4)

    def test_a_journal_entry_is_saved_with_the_session(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(1.2)
        fresh_app.stop_sprint()
        time.sleep(0.8)

        fresh_app.set_text("JournalInput", "shipped the licence server")
        fresh_app.click("SaveJournalButton")
        time.sleep(1.0)

        settings = verify.read_settings()
        assert settings["Sessions"][-1]["Journal"] == "shipped the licence server"

    def test_ending_early_shows_the_neutral_summary_card(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(1.5)
        fresh_app.stop_sprint()
        time.sleep(1.0)

        title = fresh_app.text_of("SummaryTitle")
        assert "ended early" in title.lower()
        assert "it'll recover" in title.lower()
        assert "−0" not in title, "no momentum was lost, so the card must not say 'momentum −0'"
        assert fresh_app.text_of("SummaryDistractionsValue") == "No distractions caught"
        # 1.0.10: nothing was turned back, so there is no "Turned back 0 times".
        assert not fresh_app.exists("SummaryTurnedBackText", timeout=1)

        settings = verify.read_settings()
        assert fresh_app.text_of("SummaryMomentumText").endswith(f"→ {int(settings['MomentumScore'])}")

    def test_finishing_a_sprint_shows_the_summary_card(self, fresh_app):
        """The shortest sprint is five minutes; the card must show what settings stores."""
        fresh_app.navigate_to_tab("Today")
        fresh_app.click("SprintLength_Custom")
        fresh_app.set_text("CustomMinutesInput", "5")
        time.sleep(0.5)
        fresh_app.start_sprint()

        assert fresh_app.exists("SummaryTitle", timeout=340), \
            "the 5-minute sprint finished but the summary card never appeared"

        settings = verify.read_settings()
        session = settings["Sessions"][-1]
        assert session["Completed"] is True

        assert fresh_app.text_of("SummaryTitle") == "Sprint complete"
        started = datetime.fromisoformat(session["StartedUtc"].replace("Z", "+00:00"))
        ended = datetime.fromisoformat(session["EndedUtc"].replace("Z", "+00:00"))
        # #300: it ends at its planned end, not whenever the tick that noticed
        # ran -- after a sleep, that tick is hours late.
        assert (ended - started).total_seconds() == session["PlannedMinutes"] * 60, \
            f"a {session['PlannedMinutes']}-minute sprint was recorded as {ended - started}"
        actual_minutes = round((ended - started).total_seconds() / 60)
        assert fresh_app.text_of("SummaryMinutesValue") == \
            f"{actual_minutes} minutes focused"

        if session["BlocksEnforced"] == 0:
            expected = "No distractions caught"
        else:
            nudges = session["NudgesSent"]
            expected = (f"{session['AppsClosed']} closed · "
                        f"{'1 nudge' if nudges == 1 else f'{nudges} nudges'}")
        assert fresh_app.text_of("SummaryDistractionsValue") == expected

        momentum = fresh_app.text_of("SummaryMomentumText")
        assert momentum.endswith(f"→ {int(settings['MomentumScore'])}")
        assert momentum.startswith("+"), "a finished sprint gained momentum"
        assert fresh_app.text_of("SummaryStreakText") == "Day 1"


# ================================================== sprint intention (F13)

class TestSprintIntention:
    """F13: the optional intention is saved with the sprint and shown back."""

    def test_an_intention_is_saved_shown_on_the_timer_and_repeated(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.set_text("IntentionInput", "finish chapter 3")
        time.sleep(0.4)
        fresh_app.start_sprint()
        time.sleep(1.2)

        assert fresh_app.text_of("SprintIntentionText") == "finish chapter 3"

        fresh_app.stop_sprint()
        time.sleep(1.0)

        settings = verify.read_settings()
        assert settings["Sessions"][-1]["Intention"] == "finish chapter 3"
        assert fresh_app.text_of("SummaryIntentionText") == "You planned: finish chapter 3"
        assert fresh_app.text_of("JournalPromptTitle") == \
            "You planned: finish chapter 3. What moved?"
        assert fresh_app.text_of("IntentionInput") == ""

    def test_an_empty_intention_leaves_everything_default(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()
        time.sleep(1.2)
        fresh_app.stop_sprint()
        time.sleep(0.8)

        settings = verify.read_settings()
        assert settings["Sessions"][-1]["Intention"] == ""
        assert not fresh_app.exists("SummaryIntentionText", timeout=1)
        assert fresh_app.text_of("JournalPromptTitle") == "What moved?"

    def test_a_long_intention_is_capped_and_stays_on_one_line(self, fresh_app):
        long_one = ("finish the entire chapter three problem set and then review every single "
                    "lecture slide from week nine before the exam tomorrow morning")
        fresh_app.navigate_to_tab("Today")
        fresh_app.set_text("IntentionInput", long_one)
        time.sleep(0.4)

        typed = fresh_app.text_of("IntentionInput")
        assert len(typed) == 80, f"the input accepted {len(typed)} characters"
        assert typed == long_one[:80]

        fresh_app.start_sprint()
        time.sleep(1.2)

        # The ring's line must not grow taller than a single caption line.
        line = fresh_app.element("SprintIntentionText").rectangle()
        assert line.height() < 24, f"the intention wrapped inside the ring ({line.height()}px tall)"

        fresh_app.cancel_sprint()
        time.sleep(0.8)

    def test_cancelling_a_sprint_clears_the_intention_input(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.set_text("IntentionInput", "write the report")
        time.sleep(0.4)
        fresh_app.start_sprint()
        time.sleep(1.2)
        fresh_app.cancel_sprint()
        time.sleep(0.8)

        assert fresh_app.text_of("IntentionInput") == ""
        settings = verify.read_settings()
        assert settings["Sessions"] == []


# ==================================================== the trial unlocks all

class TestTrialUnlocksEverything:
    """During the 7-day trial every feature is available, as after a purchase."""

    def test_sleep_blocking_turns_on(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        assert fresh_app.set_toggle("SleepBlockToggle", True) is True
        fresh_app.set_sleep_window("23:15", "06:45")
        time.sleep(0.8)
        saved = verify.verify_sleep_window(enabled=True, start="23:15", end="06:45")
        assert saved.ok, saved.detail

    def test_shield_three_and_long_sprints_stick(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Sealed")
        time.sleep(0.8)
        assert "locks" in fresh_app.text_of("ShieldDescriptionText").lower()

    def test_hard_kill_mode_turns_on(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        assert fresh_app.set_toggle("HardKillModeToggle", True) is True
        time.sleep(0.8)
        assert verify.read_settings()["HardKillModeEnabled"] is True


# ==================================================== shield wording (F1)

class TestShieldWording:
    """F1: Today and first run show each shield's promise and scenario."""

    EXPECTED = {
        "Soft": ("Notes distractions and nudges you.", "Best for classes or light work."),
        "Firm": ("Closes blocked apps.", "Best for homework."),
        "Sealed": ("Closes apps and locks the list until the sprint ends.",
                   "Best for exams and deep work."),
    }

    def test_today_shows_the_promise_and_scenario_for_each_shield(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        for level, (promise, best_for) in self.EXPECTED.items():
            fresh_app.select_shield(level)
            # Wait for what happens, not for a duration (CLAUDE.md's testing
            # gotchas, #146): a flat sleep(0.5) here was long enough on a quiet
            # machine but not under the full suite's load, where the binding
            # update can lag behind the click and the text still reads the
            # previous shield's promise for a moment.
            deadline = time.time() + 5
            while time.time() < deadline and fresh_app.text_of("ShieldDescriptionText") != promise:
                time.sleep(0.2)
            assert fresh_app.text_of("ShieldDescriptionText") == promise, level
            assert fresh_app.text_of("ShieldBestForText") == best_for, level

    def test_first_run_uses_the_same_wording(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.click("ShowFirstRunButton")
        assert fresh_app.exists("FirstRunSkipButton", timeout=3)

        # In the full suite the Settings button is often scrolled out of view and
        # invoked directly, so the welcome can still be opening when Next is
        # pressed. Wait for step 1, then confirm the step actually moved.
        deadline = time.time() + 5
        while time.time() < deadline and fresh_app.text_of("FirstRunStepText") != "Step 1 of 3":
            time.sleep(0.25)
        assert fresh_app.text_of("FirstRunStepText") == "Step 1 of 3"

        for _ in range(2):
            fresh_app.click("FirstRunNextButton")
            deadline = time.time() + 3
            while time.time() < deadline and fresh_app.text_of("FirstRunStepText") != "Step 2 of 3":
                time.sleep(0.25)
            if fresh_app.text_of("FirstRunStepText") == "Step 2 of 3":
                break
        assert fresh_app.text_of("FirstRunStepText") == "Step 2 of 3"
        try:
            for level, (promise, best_for) in self.EXPECTED.items():
                assert fresh_app.text_of(f"FirstRun{level}Promise") == promise, level
                assert fresh_app.text_of(f"FirstRun{level}BestFor") == best_for, level
        finally:
            fresh_app.click("FirstRunSkipButton")
            time.sleep(0.5)
            assert not fresh_app.exists("FirstRunSkipButton", timeout=1)


# ================================================== after the trial ends

class TestTrialEnded:
    """With the trial over and nothing bought, the app is locked."""

    def test_the_lock_screen_offers_the_purchase(self, expired_app):
        assert expired_app.exists("LockBuyButton", timeout=5), "no lock screen after the trial"
        assert "$4.99" in expired_app.text_of("TrialEndedText")
        assert expired_app.tier_badge().upper() == "TRIAL ENDED"

    def test_a_sprint_cannot_start(self, expired_app):
        expired_app.navigate_to_tab("Today")
        try:
            expired_app.start_sprint()
        except Exception:                      # noqa: BLE001 — covered by the lock screen
            pass
        time.sleep(1.5)
        assert "engaged" not in expired_app.session_state().lower(), "a locked app started a sprint"
        assert verify.read_settings()["Sessions"] == []

    def test_sleep_blocking_and_hard_kill_are_disabled(self, expired_app):
        expired_app.navigate_to_tab("Schedule")
        assert expired_app.is_control_enabled("SleepBlockToggle") is False
        expired_app.navigate_to_tab("Settings")
        assert expired_app.is_control_enabled("HardKillModeToggle") is False
        assert "trial ended" in expired_app.get_license_status_text().lower()

    def test_the_buy_button_opens_the_store(self, expired_app):
        expired_app.click("LockBuyButton")
        time.sleep(1.5)
        assert expired_app.app_log_contains("opening upgrade page")


# ========================= a trial that expires mid-sprint (F20, #9) ========

class TestTrialExpiringDuringASprint:
    """
    A trial that runs out while a sprint is in progress must not interrupt
    it, and must not interrupt the summary card the sprint ends on either.
    The lock is only allowed to appear once that card has been read and
    dismissed with "Save entry" — never before.
    """

    def test_the_lock_waits_for_the_sprint_and_its_summary(self, trial_expiring_soon_app):
        app = trial_expiring_soon_app
        app.navigate_to_tab("Today")

        # The shortest sprint FlowShield offers (5 minutes) comfortably
        # outlasts the trial set by --expire-trial-in (see the fixture).
        # Custom length is Pro-gated, so this only works while the trial is
        # still live — which is why the fixture's runway has to cover the
        # driver's own setup cost (#243).
        app.click("SprintLength_Custom")
        app.set_text("CustomMinutesInput", "5")
        time.sleep(0.5)
        app.start_sprint()

        # Wait for the trial to actually cross its boundary rather than
        # guessing at it: the fixture recorded when it runs out, on this same
        # clock, so the assertion below is about the product rather than about
        # a sleep being long enough. This is the moment a naive "check access
        # every minute" fails.
        while time.monotonic() < app.trial_ends_at + 5:
            time.sleep(1)

        assert app.exists("StopSprintButton", timeout=1), \
            "the sprint must still be running well after the trial has technically ended"
        assert not app.exists("LockBuyButton", timeout=1.5), \
            "the trial ending must never interrupt a running sprint"

        # Wait for the sprint to finish on its own and the summary card to appear.
        assert app.exists("SummaryTitle", timeout=340), \
            "the 5-minute sprint never finished"
        assert app.text_of("SummaryTitle") == "Sprint complete"

        # The summary/journal card is up: the lock must still be held off so
        # "what moved?" is never interrupted by "buy FlowShield".
        time.sleep(2)
        assert not app.exists("LockBuyButton", timeout=1.5), \
            "the lock must wait until the summary card is dismissed"
        assert app.tier_badge().upper() != "TRIAL ENDED", \
            "the tier badge must not flip to ended while the summary is still on screen"

        # Dismiss the card the normal way, exactly as F12 describes.
        app.set_text("JournalInput", "watched the trial run out mid-sprint")
        app.click("SaveJournalButton")

        # Only now is the lock allowed to appear.
        assert app.exists("LockBuyButton", timeout=5), \
            "the lock must appear once the summary card has been dismissed"
        assert app.tier_badge().upper() == "TRIAL ENDED"


# ============================================ full purchase path (Stripe)

@pytest.mark.stripe
@pytest.mark.e2e
class TestPurchaseToActivation:
    """
    The complete money path: checkout → licence → activation → persisted Pro.

    Skipped without Stripe credentials.
    """

    def test_full_flow(self, fresh_app, server, needs_stripe, logger):
        import requests

        from browser.stripe_checkout import StripeCheckoutAutomator
        from config import (TEST_CARD, TEST_CVC, TEST_EMAIL, TEST_EXPIRY,
                            TEST_NAME, TEST_ZIP)

        created = requests.post(f"{server}/create-checkout",
                                json={"email": TEST_EMAIL}, timeout=45).json()
        assert created["url"].startswith("https://checkout.stripe.com/")

        automator = StripeCheckoutAutomator(logger=logger, headless=True,
                                            shot_dir=logger.shot_dir)
        result = automator.complete_checkout(
            checkout_url=created["url"], email=TEST_EMAIL, card_number=TEST_CARD,
            expiry=TEST_EXPIRY, cvc=TEST_CVC, postal_code=TEST_ZIP,
            cardholder=TEST_NAME)
        assert result.ok, result.message
        assert result.session_id

        deadline = time.time() + 60
        payload = {}
        while time.time() < deadline:
            response = requests.get(f"{server}/get-license",
                                    params={"session_id": result.session_id}, timeout=20)
            payload = response.json()
            if response.status_code == 200 and payload.get("isPro"):
                break
            time.sleep(2)
        assert payload.get("isPro") is True, payload
        assert payload["licenseKey"] == created["licenseKey"]

        fresh_app.navigate_to_tab("Settings")
        fresh_app.enter_license_key(payload["licenseKey"])
        fresh_app.click_activate_pro()
        status = fresh_app.wait_for_license_status("Licence active", timeout=45)
        assert "licence active" in status.lower()

        ui = verify.verify_ui_pro_status(fresh_app, expected_pro=True)
        assert ui.ok, ui.detail

        disk = verify.verify_dpapi_settings(expected_pro=True)
        assert disk.ok, disk.detail
        assert disk.data["LicenseKey"] == payload["licenseKey"]


@pytest.mark.stripe
@pytest.mark.e2e
class TestPurchaseUnlocksAnExpiredTrial:
    """Buying FlowShield after the trial has ended must lift the lock."""

    def test_a_licence_unlocks_the_locked_app(self, expired_app, server,
                                              needs_stripe, logger):
        import requests

        from browser.stripe_checkout import StripeCheckoutAutomator
        from config import (TEST_CARD, TEST_CVC, TEST_EMAIL, TEST_EXPIRY,
                            TEST_NAME, TEST_ZIP)

        created = requests.post(f"{server}/create-checkout", json={}, timeout=45).json()
        automator = StripeCheckoutAutomator(logger=logger, headless=True,
                                            shot_dir=logger.shot_dir)
        paid = automator.complete_checkout(
            checkout_url=created["url"], email=TEST_EMAIL, card_number=TEST_CARD,
            expiry=TEST_EXPIRY, cvc=TEST_CVC, postal_code=TEST_ZIP,
            cardholder=TEST_NAME)
        assert paid.ok, paid.message

        deadline = time.time() + 60
        while time.time() < deadline:
            body = requests.get(f"{server}/get-license",
                                params={"session_id": paid.session_id}, timeout=20).json()
            if body.get("isPro"):
                break
            time.sleep(2)

        # Activate from the lock screen itself — the Settings page is behind it.
        expired_app.set_text("LockLicenseKeyInput", created["licenseKey"])
        expired_app.click("LockActivateButton")

        deadline = time.time() + 45
        while time.time() < deadline and expired_app.exists("LockBuyButton", timeout=1):
            time.sleep(1)
        assert not expired_app.exists("LockBuyButton", timeout=1), "the lock stayed up after buying"

        expired_app.navigate_to_tab("Settings")
        assert "licence active" in expired_app.get_license_status_text().lower()
        assert expired_app.tier_badge().upper() == "PURCHASED"



# ====================================== ending a sprint by shield level (F2)

class TestEndingASprint:
    """
    The app is launched with --short-timers: a 3 s grace period, 2 s for Firm's
    confirmation and 3 s for Sealed's countdown. Every step still has to happen.
    """

    def _start(self, app, shield):
        app.navigate_to_tab("Today")
        app.select_shield(shield)
        time.sleep(0.4)
        app.start_sprint()
        time.sleep(0.6)

    def test_cancelling_in_the_grace_period_leaves_no_record(self, fresh_app):
        self._start(fresh_app, "Sealed")
        assert "cancel" in fresh_app.end_button_label().lower()
        fresh_app.cancel_sprint()
        time.sleep(1.0)

        assert "cancelled" in fresh_app.session_state().lower()
        settings = verify.read_settings()
        assert settings["Sessions"] == [], "a cancelled sprint was recorded"
        assert settings.get("ActiveSprint") is None
        assert settings["MomentumScore"] == 0

    def test_soft_ends_straight_away(self, fresh_app):
        self._start(fresh_app, "Soft")
        fresh_app.wait_out_grace_period()
        assert fresh_app.end_button_label() == "End sprint"
        fresh_app.click("StopSprintButton")
        time.sleep(1.0)
        assert "early" in fresh_app.session_state().lower()
        assert not fresh_app.exists("KeepGoingButton", timeout=1)

    def test_firm_needs_a_confirmation_that_waits(self, fresh_app):
        """
        #242 reported "End anyway is enabled immediately". It is not: the app
        log showed EndAnywayEnabled flipping 2.507 s after the panel opened,
        against a 2 s FirmConfirmDelay. What could not happen was *reading* it
        inside a 2 s window — element lookup plus IsEnabled is a UIA round trip
        costing a second or more on this page. So the delay is 6 s under
        --short-timers (EndSprintPolicy, same reasoning as #222's grace period)
        and the assertion times how long the button stays disabled instead of
        assuming one read lands inside the window.
        """
        self._start(fresh_app, "Firm")
        fresh_app.wait_out_grace_period()

        opened = time.monotonic()
        fresh_app.click("StopSprintButton")
        assert fresh_app.exists("KeepGoingButton", timeout=3), "Firm ended without a confirmation"

        # Only assert "disabled right now" while the window provably still has
        # time left on it; otherwise the read itself is the thing being timed.
        if time.monotonic() - opened < 3.0:
            assert fresh_app.is_control_enabled("EndAnywayButton") is False, \
                "End anyway was ready immediately"

        # Measured from before the click, which only ever inflates the number —
        # so a button that was enabled from the start cannot fake a long wait.
        fresh_app.wait_until_control_enabled("EndAnywayButton", timeout=20)
        waited = time.monotonic() - opened
        assert waited >= 4.0, \
            f"End anyway unlocked after {waited:.1f}s of a 6s confirm countdown"

        fresh_app.click("EndAnywayButton")
        time.sleep(1.0)
        assert "early" in fresh_app.session_state().lower()

    def test_sealed_needs_the_countdown_and_the_phrase(self, fresh_app):
        self._start(fresh_app, "Sealed")
        fresh_app.wait_out_grace_period()
        assert "need to stop" in fresh_app.end_button_label().lower()

        opened = time.monotonic()
        fresh_app.click("StopSprintButton")
        assert fresh_app.exists("EndPhraseInput", timeout=3), "Sealed didn't ask for the phrase"

        # Same measurement as the Firm test above (#242): the countdown is 8 s
        # under --short-timers, and the right phrase must not beat it.
        fresh_app.set_text("EndPhraseInput", "end my sprint")
        if time.monotonic() - opened < 5.0:
            assert fresh_app.is_control_enabled("EndAnywayButton") is False, \
                "the phrase ended a Sealed sprint before its countdown"

        fresh_app.wait_until_control_enabled("EndAnywayButton", timeout=25)
        waited = time.monotonic() - opened
        assert waited >= 5.0, \
            f"End anyway unlocked after {waited:.1f}s of an 8s sealed countdown"

        # The countdown being over must not let the wrong phrase through. No
        # timing in this half: the gate is the words, not the clock.
        fresh_app.set_text("EndPhraseInput", "end sprint")
        time.sleep(0.5)
        assert fresh_app.is_control_enabled("EndAnywayButton") is False, "the wrong phrase was accepted"

        fresh_app.set_text("EndPhraseInput", "end my sprint")
        time.sleep(0.6)
        assert fresh_app.is_control_enabled("EndAnywayButton") is True
        fresh_app.click("EndAnywayButton")
        time.sleep(1.0)

        session = verify.read_settings()["Sessions"][-1]
        assert session["Completed"] is False and session["Shield"] in (3, "Sealed")

    def test_keep_going_backs_out_at_no_cost(self, fresh_app):
        self._start(fresh_app, "Firm")
        fresh_app.wait_out_grace_period()
        fresh_app.click("StopSprintButton")
        assert fresh_app.exists("KeepGoingButton", timeout=3)
        fresh_app.click("KeepGoingButton")
        time.sleep(0.8)

        assert fresh_app.exists("StopSprintButton", timeout=2), "the sprint stopped after Keep going"
        settings = verify.read_settings()
        assert settings["Sessions"] == [] and settings.get("ActiveSprint")


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


# ===================================================== terms acceptance (legal)

def current_terms_version() -> str:
    """LegalTerms.Version as the app has it, so a terms bump needs no test edit."""
    source = (Path(__file__).resolve().parents[2] / "DesktopApp" / "Models" / "LegalTerms.cs")
    return source.read_text(encoding="utf-8").split('public const string Version = "')[1].split('"')[0]


class TestTermsGate:
    """A clean install must agree to the terms before FlowShield can do anything."""

    def _launch(self, logger, clean=True):
        from desktop.app_controller import DesktopController

        app = DesktopController(logger)
        app.launch_app(clean_state=clean, show_first_run=True)
        app.connect_window()
        time.sleep(1.5)
        return app

    def test_a_clean_install_must_agree_before_anything_else(self, logger):
        app = self._launch(logger)
        try:
            assert app.exists("AcceptTermsButton", timeout=4), "no terms gate on a clean install"
            assert "closes programs" in app.text_of("TermsDataLossText").lower()
            assert "unsaved work" in app.text_of("TermsDataLossText").lower()
            assert app.text_of("TermsVersionText").startswith("Version ")

            # The page behind the gate must not act. The overlay stops a mouse,
            # so this invokes the covered button directly — the harder case.
            try:
                app.element("StartSprintButton").invoke()
            except Exception:
                pass
            time.sleep(1.0)
            assert not app.exists("StopSprintButton", timeout=1), \
                "a sprint started while the terms were still on screen"
            assert verify.read_settings().get("ActiveSprint") is None

            assert not app.exists("FirstRunSkipButton", timeout=1), \
                "the welcome must wait behind the terms"
            assert verify.read_settings().get("TermsAcceptedVersion", "") == ""

            app.click("AcceptTermsButton")

            deadline = time.time() + 8
            settings = verify.read_settings()
            while time.time() < deadline and not settings.get("TermsAcceptedVersion"):
                time.sleep(0.5)
                settings = verify.read_settings()
            assert settings["TermsAcceptedVersion"] == current_terms_version(), settings["TermsAcceptedVersion"]
            assert settings["TermsAcceptedUtc"], "the time of acceptance must be recorded"
            assert not app.exists("AcceptTermsButton", timeout=1)
            assert app.exists("FirstRunSkipButton", timeout=4), \
                "the welcome should follow once the terms are accepted"
        finally:
            app.close_app()

    def test_it_is_not_asked_again_after_accepting(self, logger):
        app = self._launch(logger)
        try:
            app.accept_terms_if_shown()
        finally:
            app.close_app()

        again = self._launch(logger, clean=False)
        try:
            assert not again.exists("AcceptTermsButton", timeout=2), "the gate came back"
        finally:
            again.close_app()

    def test_settings_shows_when_the_terms_were_accepted(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        text = fresh_app.text_of("TermsAcceptedText")
        assert "accepted" in text.lower() and current_terms_version() in text, text


# ========================================================= notifications (F19)

class TestNotificationSettings:
    TOGGLES = [
        ("NotifySprintStartedToggle", "SprintStarted"),
        ("NotifyFiveMinutesLeftToggle", "FiveMinutesLeft"),
        ("NotifySprintCompleteToggle", "SprintComplete"),
        ("NotifySprintInterruptedToggle", "SprintInterrupted"),
        ("NotifyBreakOverToggle", "BreakOver"),
        ("NotifyScheduledSprintToggle", "ScheduledSprint"),
        ("NotifyAppClosingToggle", "AppClosing"),
        ("NotifyTrialEndingToggle", "TrialEnding"),
    ]

    def test_every_notification_is_on_for_a_new_install(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        assert fresh_app.toggle_state("NotificationsToggle") is True
        for toggle, _ in self.TOGGLES:
            assert fresh_app.toggle_state(toggle) is True, toggle

    def test_switching_one_off_is_saved(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.set_toggle("NotifyFiveMinutesLeftToggle", False)
        time.sleep(0.8)

        kinds = verify.read_settings()["NotificationKinds"]
        assert kinds["FiveMinutesLeft"] is False
        assert verify.read_settings()["NotificationsEnabled"] is True

    def test_the_master_switch_disables_the_rest(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.set_toggle("NotificationsToggle", False)
        time.sleep(0.8)
        assert verify.read_settings()["NotificationsEnabled"] is False
        assert fresh_app.is_control_enabled("NotifySprintStartedToggle") is False

    def test_a_running_sprint_puts_the_countdown_in_the_title(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.click("SprintLength_15")
        fresh_app.start_sprint()
        time.sleep(1.5)
        title = fresh_app.window.window_text()
        assert title.startswith("FlowShield —"), title
        assert ":" in title, title


# ============================================================ first run (F18)

class TestFirstRun:
    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def _launch(self, logger, clean=True):
        from desktop.app_controller import DesktopController

        app = DesktopController(logger)
        app.launch_app(clean_state=clean, show_first_run=True)
        app.connect_window()
        time.sleep(1.5)
        # The terms gate comes before the welcome on a clean install; its own
        # behaviour is covered by TestTermsGate.
        app.accept_terms_if_shown()
        return app

    def _run_value(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
                return winreg.QueryValueEx(k, "FlowShield")[0]
        except FileNotFoundError:
            return None

    def _set_run_value(self, value):
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
            if value is None:
                try:
                    winreg.DeleteValue(k, "FlowShield")
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(k, "FlowShield", 0, winreg.REG_SZ, value)

    @pytest.mark.skipif(not STEAM_INSTALLED, reason="the picker lists Steam only where it is installed")
    def test_completing_it_saves_every_choice_and_starts_the_sprint(self, logger):
        saved_run = self._run_value()          # the toggle writes the real Run value
        app = self._launch(logger)
        try:
            assert app.exists("FirstRunSkipButton", timeout=3), "a clean install didn't get the welcome"
            assert app.text_of("FirstRunStepText") == "Step 1 of 3"

            app.set_text("FirstRunSearchInput", "steam")
            time.sleep(0.8)
            # Steam may already be ticked for this PC, so drive it to checked rather than blind-clicking.
            assert app.set_toggle("FirstRunPickApp_steam", True) is True, "Steam wouldn't stay ticked"
            app.click("FirstRunNextButton")
            time.sleep(0.4)

            assert app.text_of("FirstRunStepText") == "Step 2 of 3"
            app.click("FirstRunShield_Sealed")
            app.click("FirstRunNextButton")
            time.sleep(0.4)

            app.click("FirstRunLength_45")
            assert app.set_toggle("FirstRunStartWithWindows", True) is True, "Start-with-Windows wouldn't stay ticked"
            assert "unlocked for 7 days" in app.text_of("FirstRunTrialText").lower()
            app.click("FirstRunStartButton")
            time.sleep(1.5)

            assert not app.exists("FirstRunSkipButton", timeout=1), "the welcome stayed open"

            # #244: the wizard's Start goes through the same
            # TodayViewModel.StartSprint as the Start button, so it meets F7's
            # "these blocked apps are open" question too — and it always does
            # here, because step 1 pre-ticks every suggested app found on this
            # PC, not only the one the test typed. The app log showed
            # "first run finished: 5 apps ... sprint started" followed by
            # "pre-sprint: 3 blocked app(s) already open": the sprint was
            # waiting on an unanswered panel, not failing to start.
            app.answer_open_apps_question()
            assert app.exists("StopSprintButton", timeout=3), "the first sprint didn't start"

            s = verify.read_settings()
            steam = next(
                (a for a in s["BlockedApps"] if a["ProcessName"].lower() == "steam"),
                None,
            )
            assert steam is not None, "Steam was not saved to the blocklist"
            assert [p.lower() for p in steam["ExtraProcessNames"]] == ["steamwebhelper"]
            assert s["DefaultShield"] in (3, "Sealed")
            assert s["DefaultSprintMinutes"] == 45
            assert s["StartWithWindows"] is True, "StartWithWindows setting was not saved"
            assert self._run_value(), "start-with-Windows Run registry value was not written"
            assert s["FirstRunCompleted"] is True
            active = s["ActiveSprint"]
            assert active["PlannedMinutes"] == 45 and active["Shield"] in (3, "Sealed")
        finally:
            app.close_app()
            self._set_run_value(saved_run)

    def test_skipping_means_it_never_comes_back(self, logger):
        app = self._launch(logger)
        try:
            app.click("FirstRunSkipButton")
            time.sleep(0.8)
            assert not app.exists("FirstRunSkipButton", timeout=1)
            assert verify.read_settings()["FirstRunCompleted"] is True
        finally:
            app.close_app()

        again = self._launch(logger, clean=False)
        try:
            assert not again.exists("FirstRunSkipButton", timeout=2), "the welcome came back after skipping"
            assert again.current_page_title() == "Today"
        finally:
            again.close_app()

    def test_settings_can_open_it_again(self, fresh_app):
        assert not fresh_app.exists("FirstRunSkipButton", timeout=1)
        fresh_app.navigate_to_tab("Settings")
        fresh_app.click("ShowFirstRunButton")
        assert fresh_app.exists("FirstRunSkipButton", timeout=3)
        assert fresh_app.text_of("FirstRunStepText") == "Step 1 of 3"
        fresh_app.click("FirstRunSkipButton")
        time.sleep(0.5)
        assert not fresh_app.exists("FirstRunSkipButton", timeout=1)

    def test_a_locked_trial_never_gets_it(self, logger):
        from desktop.app_controller import DesktopController

        app = DesktopController(logger)
        app.launch_app(clean_state=True, show_first_run=True, extra_args=["--expire-trial"])
        app.connect_window()
        try:
            time.sleep(1.5)
            assert app.exists("LockBuyButton", timeout=3)
            assert not app.exists("FirstRunSkipButton", timeout=1), "the welcome covered the lock screen"
        finally:
            app.close_app()


# ======================================================= one instance (1.3)

def launch_again(*extra: str) -> int:
    """Start a second FlowShield without closing the first; returns its exit code."""
    import subprocess
    from pathlib import Path

    from config import APP_EXE

    proc = subprocess.run([str(APP_EXE), *extra], cwd=str(Path(APP_EXE).parent), timeout=30)
    return proc.returncode


def flowshield_pids() -> list[int]:
    import psutil

    return [p.pid for p in psutil.process_iter(["name"])
            if (p.info["name"] or "").lower() == "flowshield.exe"]


class TestOneInstance:
    def test_opening_it_again_brings_back_the_running_copy(self, fresh_app):
        import win32gui

        hwnd = fresh_app.window.handle             # UIA can't find a hidden window later
        fresh_app.window.close()                   # minimise-to-tray is on by default
        time.sleep(1.0)
        assert not win32gui.IsWindowVisible(hwnd), "closing didn't hide to the tray"

        launch_again()
        time.sleep(1.5)

        assert flowshield_pids() == [fresh_app.pid], "a second FlowShield kept running"
        assert win32gui.IsWindowVisible(hwnd), "the running copy wasn't brought back"


# =================================================== flowshield:// links (1.4)

# Shaped like a real key; never activated, so it doesn't need to exist.
LINK_KEY = "FS-ABCD-EFGH-JKMN-PQR5"
LINK = f"flowshield://activate?key={LINK_KEY}"


class TestActivationLinks:
    def _launch_with(self, logger, *extra):
        from desktop.app_controller import DesktopController

        app = DesktopController(logger)
        app.launch_app(clean_state=True, extra_args=list(extra))
        app.connect_window()
        time.sleep(1.2)
        return app

    def test_a_link_fills_in_the_key_and_waits_for_a_click(self, logger):
        app = self._launch_with(logger, LINK)
        try:
            assert app.exists("ConfirmActivationButton", timeout=3), "no confirmation was shown"
            assert app.text_of("ActivationLinkKey") == LINK_KEY
            assert app.current_page_title() == "Settings"
            time.sleep(1.0)
            settings = verify.read_settings()
            assert not settings.get("IsPro") and not settings.get("LicenseKey"), \
                "the link activated without the user's click"

            app.click("DismissActivationButton")
            time.sleep(0.6)
            assert not app.exists("ConfirmActivationButton", timeout=1)
            assert not verify.read_settings().get("IsPro")
        finally:
            app.close_app()

    def test_activate_checks_the_key_with_the_server(self, logger, server):
        app = self._launch_with(logger, LINK)
        try:
            app.click("ConfirmActivationButton")
            status = app.wait_for_license_status("not activated", timeout=30)
            assert "not activated" in status.lower(), status   # a made-up key is refused
            assert not app.exists("ConfirmActivationButton", timeout=1)
        finally:
            app.close_app()

    def test_a_link_reaches_a_copy_that_is_already_running(self, fresh_app):
        launch_again(LINK)
        time.sleep(1.5)
        assert flowshield_pids() == [fresh_app.pid]
        assert fresh_app.exists("ConfirmActivationButton", timeout=3), "the running copy ignored the link"
        assert fresh_app.text_of("ActivationLinkKey") == LINK_KEY

    @pytest.mark.parametrize("link", [
        "flowshield://settings?hardkill=on",
        "flowshield://activate?key=not-a-key",
        "flowshield://activate",
    ])
    def test_other_links_do_nothing(self, logger, link):
        app = self._launch_with(logger, link)
        try:
            assert not app.exists("ConfirmActivationButton", timeout=2)
            assert app.current_page_title() == "Today"
        finally:
            app.close_app()


# =========================================================== daily goal (F15)

# ============================================ momentum explained (F14 / 3.2)
class TestMomentumTrendAndExplainer:
    """F14: the score is on screen with the rule behind it and 30 days of shape."""

    def test_the_explainer_opens_and_closes(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        assert not fresh_app.exists("MomentumExplainerText", timeout=1),             "the card leads with the number, not with the essay"

        fresh_app.click("MomentumExplainerButton")
        time.sleep(0.5)
        assert fresh_app.exists("MomentumExplainerText", timeout=3)

        fresh_app.click("MomentumExplainerButton")
        time.sleep(0.5)
        assert not fresh_app.exists("MomentumExplainerText", timeout=1)

    def test_the_chart_stays_hidden_until_there_is_momentum(self, fresh_app):
        """
        Not "until there is a sprint". Ending one early leaves the score at
        zero, and a line on the bottom gridline reads as broken.

        Asserted on the captions, not on the Grid that holds the line: a layout
        panel is not surfaced to UI Automation, so exists() on one answers the
        same either way.

        The *visible* case cannot be reached from here — momentum only moves on
        a finished sprint, and the shortest is 15 real minutes, which no tier 3
        test can wait for. It is covered at tier 1 instead, on the same rules.
        """
        fresh_app.navigate_to_tab("Today")
        assert not fresh_app.exists("MomentumTrendRange", timeout=1),             "a clean install has nothing to plot"

        fresh_app.start_sprint()
        time.sleep(1.2)
        fresh_app.stop_sprint()
        time.sleep(1.0)

        assert not fresh_app.exists("MomentumTrendRange", timeout=2),             "a sprint ended early leaves momentum at zero, so there is still nothing to draw"


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
        assert text.startswith("# FlowShield journal")
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


# ============================== tray and keyboard start a sprint (F4)
#
# Written for F4 but not run in this session: UI tests take over the screen,
# only one can run at a time on this machine, and the orchestrator schedules
# them. See the PR description.

class TestSpaceStartsAndEndsASprint:
    """
    Space on Today (F4) must behave exactly like clicking StartSprintButton
    and StopSprintButton — including going through the F2 end flow, not
    ending a Firm sprint immediately.
    """

    def test_space_starts_a_sprint_and_opens_the_firm_end_flow(self, fresh_app):
        """
        #245: this never actually pressed Space. pywinauto drops a bare " "
        from type_keys unless with_spaces=True, so the old `type_keys(" ")`
        sent nothing at all — a DIAG build logging every PreviewKeyDown saw no
        key arrive. It is sent as {SPACE} now.

        With a real Space arriving, the second half of the old test was wrong
        too: it clicked Shield_Firm first, and the DIAG log then showed
        `key Space focus=RadioButton id='Shield_Firm'`. WPF's ButtonBase owns
        Space for whichever control has keyboard focus — that is what makes
        every button on the page keyboard-operable (F21) — so the key never
        reaches Window.InputBindings. That is correct behaviour, not the
        shortcut failing, and the guard in CanUseSpaceShortcut is about text
        boxes, not about out-shouting a focused button.

        So nothing is clicked before the key: a fresh app opens on Today with
        Firm as the default shield, which is the state a customer is in when
        they press Space, and the only state in which the shortcut is the
        thing that owns the key.
        """
        assert fresh_app.current_page_title() == "Today", \
            "a fresh app should already be on Today; clicking a tab would take the key focus"

        fresh_app.focus(force=True)
        fresh_app.window.type_keys("{SPACE}")
        assert fresh_app.exists("StopSprintButton", timeout=5), \
            "Space did not start the sprint"
        # A blocked app already open would have asked instead of starting.
        fresh_app.answer_open_apps_question()

        # Firm is the default shield, so this is the Firm end flow below.
        assert verify.read_settings()["ActiveSprint"]["Shield"] in (2, "Firm")

        fresh_app.wait_out_grace_period()

        # Space again must open the same F2 flow the button opens — a
        # confirmation that waits — never end the sprint outright.
        opened = time.monotonic()
        fresh_app.window.type_keys("{SPACE}")
        assert fresh_app.exists("KeepGoingButton", timeout=3), \
            "Space skipped Firm's confirmation and ended the sprint directly"

        # Timed, not read once — see test_firm_needs_a_confirmation_that_waits.
        fresh_app.wait_until_control_enabled("EndAnywayButton", timeout=20)
        waited = time.monotonic() - opened
        assert waited >= 4.0, \
            f"End anyway unlocked after {waited:.1f}s — Space must not skip Firm's countdown"

        # Clean up through the real flow rather than leaving a sprint running.
        fresh_app.click("KeepGoingButton")
        time.sleep(0.5)
        fresh_app.stop_sprint()

    def test_space_typed_into_the_intention_field_stays_a_space(self, fresh_app):
        """
        The guard in TodayViewModel.CanUseSpaceShortcut: typing into the
        intention box must not also start a sprint underneath the user.
        """
        fresh_app.navigate_to_tab("Today")
        fresh_app.set_text("IntentionInput", "write")

        # set_text ends on {END}, so the caret sits after "write" with the box
        # holding keyboard focus (the DIAG run confirmed
        # focus=TextBox id='IntentionInput' at the moment the key arrives).
        # Type " notes" as real keystrokes: a bare " " is dropped by pywinauto
        # unless with_spaces=True, so the space is sent as {SPACE}, and the word
        # after it proves the space landed *inside* the value — text_of()
        # strips the ends, so a trailing space can never be observed and the
        # old assertion could not pass whatever the app did.
        intention_box = fresh_app.element("IntentionInput")
        intention_box.type_keys("{SPACE}notes")
        time.sleep(0.3)

        assert not fresh_app.exists("StopSprintButton", timeout=1), \
            "a space typed into the intention field also started a sprint"
        assert fresh_app.text_of("IntentionInput") == "write notes", \
            "the space must still land in the text box"

    def test_an_empty_range_still_saves_a_file_with_headings(self, fresh_app, tmp_path):
        target = tmp_path / "empty.csv"
        fresh_app.navigate_to_tab("Settings")
        fresh_app.click("ExportJournalButton")
        assert fresh_app.save_dialog_to(str(target))
        time.sleep(1.5)

        text = target.read_text(encoding="utf-8-sig")
        lines = [line for line in text.splitlines() if line.strip()]
        assert len(lines) == 1, "an empty range writes the header and nothing else"
        assert "headings only" in fresh_app.text_of("ExportStatusText")


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
        assert "licence key" in leaves and "device" in leaves

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


# ==================================================== breaks and cycles (F5)
#
# Written for F5 but NOT run in this session: UI tests take over the screen,
# only one can run at a time on this machine, and the orchestrator schedules
# them. See the PR description.

class TestBreaksAndCycles:
    """
    A two-sprint cycle, end to end, with five-second sprints and three-second
    breaks (--short-sprints and --short-timers).

    The point of the test is the one thing only a real run can show: that a
    blocked app launched *during* the break is left alone, and closed again as
    soon as the next sprint starts. Everything else about the state machine is
    tier 1's job.
    """

    TARGET = "flowshield-test-target"

    @staticmethod
    def _start(logger, **launch):
        from config import APP_EXE
        from desktop.app_controller import DesktopController

        if not Path(APP_EXE).exists():
            pytest.skip(f"{APP_EXE} not built")

        ctrl = DesktopController(logger)
        ctrl.launch_app(clean_state=True, **launch)
        ctrl.connect_window()
        time.sleep(1.0)
        ctrl.focus(force=True)
        return ctrl

    @pytest.fixture
    def cycle_app(self, logger):
        """Five-second sprints and three-second breaks: a whole cycle in seconds."""
        ctrl = self._start(logger, extra_args=["--short-sprints"])
        yield ctrl
        ctrl.close_app()

    @pytest.fixture
    def long_break_app(self, logger):
        """
        Five-second sprints, but a real five-minute break.

        use_defaults drops the launcher's own --short-timers, which is what
        makes the break long enough to watch a blocked app live through it.
        """
        ctrl = self._start(logger, use_defaults=True, extra_args=["--short-sprints"])
        yield ctrl
        ctrl.close_app()

    def _decoy(self, tmp_path, suffix=""):
        """A quiet blocked app: a copy of ping, as the tests above do."""
        import shutil
        exe = tmp_path / f"{self.TARGET}{suffix}.exe"
        if not exe.exists():
            shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "PING.EXE", exe)
        return subprocess.Popen(
            [str(exe), "-n", "300", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_a_completed_sprint_offers_a_break(self, cycle_app):
        cycle_app.navigate_to_tab("Today")
        cycle_app.select_sprint_length(15)
        cycle_app.start_sprint()

        # Five seconds later the sprint finishes on its own.
        assert cycle_app.exists("BreakPanelTitle", timeout=20), \
            "a completed sprint must offer a break"
        assert cycle_app.text_of("BreakPanelTitle") == "Take a break"
        assert "5 minutes" in cycle_app.text_of("BreakPanelText")
        for control in ("StartBreakButton", "SkipBreakButton", "StartNextSprintButton"):
            assert cycle_app.exists(control, timeout=3), f"{control} is missing from the card"

    def test_a_sprint_ended_early_offers_no_break(self, fresh_app):
        """A normal 15-minute sprint, ended by hand after its grace period."""
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_sprint_length(15)
        fresh_app.start_sprint()
        fresh_app.stop_sprint()
        time.sleep(1.0)

        assert fresh_app.exists("SummaryTitle", timeout=5), "the summary card should be up"
        assert not fresh_app.exists("StartBreakButton", timeout=2), \
            "ending early must not be rewarded with a break"

    def test_nothing_is_blocked_during_the_break(self, long_break_app, tmp_path):
        app = long_break_app
        app.navigate_to_tab("Blocked Apps")
        assert app.add_blocked_app(self.TARGET)
        time.sleep(0.6)

        app.navigate_to_tab("Today")
        app.select_shield("Firm")
        app.select_sprint_length(15)
        app.start_sprint()

        # Five seconds later the sprint finishes and the break is offered.
        assert app.exists("StartBreakButton", timeout=20)
        app.click("StartBreakButton")
        time.sleep(1.0)
        assert app.text_of("BreakPanelTitle") == "On a break"

        # The shield is down: a blocked app may be opened and must survive. The
        # blocker sweeps every two seconds, so twelve is several chances to fail.
        process = self._decoy(tmp_path)
        try:
            deadline = time.time() + 12
            while time.time() < deadline:
                assert process.poll() is None, \
                    "a blocked app was closed during a break; the shield must be down"
                time.sleep(1)

            # And the shield comes straight back up with the next sprint. The
            # decoy is still running, so StartSprint's F7 gate (Blocked Apps
            # already open) fires just like it does from the Start button —
            # answer it the same way start_sprint() does, or the sprint never
            # actually starts and nothing is ever enforced.
            app.click("StartNextSprintButton")
            answered = app.answer_open_apps_question()
            assert answered, "the open-apps question should be answered"
            deadline = time.time() + 10
            warning = ""
            while time.time() < deadline:
                try:
                    warning = app.text_of("ToastText", timeout=0.4)
                except Exception:
                    warning = ""
                if "closing in" in warning.lower():
                    break
                time.sleep(0.2)
            assert "closing in" in warning.lower(), "the shield should warn before closing the app"
        finally:
            if process.poll() is None:
                process.kill()

    def test_a_two_sprint_cycle_runs_itself(self, cycle_app):
        """Five-second sprints and three-second breaks: about fifteen seconds."""
        cycle_app.navigate_to_tab("Today")
        cycle_app.select_sprint_length(15)
        cycle_app.choose("Cycle_2")
        time.sleep(0.4)
        cycle_app.start_sprint()

        assert cycle_app.text_of("CycleProgressText", timeout=5) == "Sprint 1 of 2"

        # Sprint 1 finishes, a three-second break runs itself, and sprint 2
        # starts with no click at all.
        deadline = time.time() + 30
        seen_second = False
        while time.time() < deadline:
            try:
                if cycle_app.text_of("CycleProgressText", timeout=1) == "Sprint 2 of 2":
                    seen_second = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        assert seen_second, "the cycle did not start its second sprint by itself"

        # The cycle stops at two. Nothing is checked in Sessions here on
        # purpose: --short-sprints records nothing at all, which is exactly what
        # stops that flag from buying momentum, a streak day or a goal (tier 5's
        # TestShortSprintsCannotBuyCredit). What a real run proves is that the
        # cycle ends rather than rolling into a third sprint.
        deadline = time.time() + 30
        while time.time() < deadline and cycle_app.exists("StopSprintButton", timeout=1):
            time.sleep(1)

        time.sleep(8)
        assert not cycle_app.exists("StopSprintButton", timeout=2), \
            "the cycle must stop after its last sprint, not roll on"
        # text_of() raises rather than returning a falsy value when the control
        # is gone, so the "label gone" case has to be checked with exists()
        # first rather than relying on `or` to short-circuit past a raise.
        if cycle_app.exists("CycleProgressText", timeout=1):
            assert cycle_app.text_of("CycleProgressText", timeout=1) == "", \
                "the cycle label must go once the cycle is over"

        # And nothing was credited for those five-second sprints.
        settings = verify.read_settings()
        assert settings.get("Sessions", []) == [], \
            "--short-sprints must record nothing"
        assert settings.get("MomentumScore", 0) == 0, \
            "--short-sprints must not move momentum"
        assert settings.get("CurrentStreak", 0) == 0

    def test_a_break_never_moves_momentum_or_the_goal(self, cycle_app):
        cycle_app.navigate_to_tab("Today")
        cycle_app.select_sprint_length(15)
        cycle_app.start_sprint()
        assert cycle_app.exists("StartBreakButton", timeout=20)

        momentum_before = cycle_app.text_of("MomentumValue")
        minutes_before = cycle_app.text_of("FocusMinutesValue")

        cycle_app.click("SkipBreakButton")
        time.sleep(1.0)

        assert cycle_app.text_of("MomentumValue") == momentum_before, \
            "skipping a break must not change momentum"
        assert cycle_app.text_of("FocusMinutesValue") == minutes_before, \
            "a break is not focus time"
# ==================================== the light theme, on screen (F21, #236)

class TestLightTheme:
    """
    F21: Settings -> Appearance switches the app between dark, light and
    whatever Windows is set to, without a restart.

    Written, not run: tier 3 takes over the screen, so the orchestrator
    schedules it. Everything a source test can prove about F21 is already in
    tier 5; what only a running window can show is that the pixels changed --
    that the swapped Tokens dictionary actually reaches what is drawn.

    The measurement is the window's own mean brightness rather than one pixel:
    the page is mostly background in both themes, so dark sits far below the
    midpoint and light far above it, wherever the cards happen to land at that
    window size.
    """

    #: 0-255. The dark theme's bg is #121110 and its surfaces barely lighter;
    #: the light theme's bg is #E6E4DF. Nothing legitimate lands between these.
    DARK_CEILING = 110
    LIGHT_FLOOR = 170

    @staticmethod
    def _mean_brightness(app) -> float:
        image = app.window.capture_as_image().convert("L")
        # A quarter-size sample is plenty and keeps the test quick.
        thumbnail = image.resize((image.width // 4 or 1, image.height // 4 or 1))
        pixels = list(thumbnail.getdata())
        return sum(pixels) / len(pixels)

    def test_switching_to_light_redraws_the_window(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")

        fresh_app.choose("ThemeDarkRadio")
        time.sleep(1.0)  # wait for the dark theme redraw
        dark = self._mean_brightness(fresh_app)
        assert dark < self.DARK_CEILING, (
            f"the app should start dark; measured {dark:.0f}/255")

        fresh_app.choose("ThemeLightRadio")
        time.sleep(1.0)  # the swap is synchronous; this is one render pass

        light = self._mean_brightness(fresh_app)
        assert light > self.LIGHT_FLOOR, (
            f"the light theme never reached the screen; measured {light:.0f}/255 "
            f"(was {dark:.0f})")
        assert light - dark > 60, "the two themes must be plainly different"

        # And the choice is what was saved, not just what was drawn.
        assert verify.read_settings().get("Theme") == 2, "Light is AppTheme.Light (2)"

    def test_switching_back_to_dark_restores_it(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.choose("ThemeLightRadio")
        time.sleep(1.0)
        assert self._mean_brightness(fresh_app) > self.LIGHT_FLOOR

        fresh_app.choose("ThemeDarkRadio")
        time.sleep(1.0)
        assert self._mean_brightness(fresh_app) < self.DARK_CEILING, \
            "Dark must undo the swap, not leave a half-lit window"
        assert verify.read_settings().get("Theme") == 1, "Dark is AppTheme.Dark (1)"

    def test_system_is_the_default_and_survives_a_restart(self, fresh_app):
        """
        System is 0, so a settings file written before F21 still means "follow
        Windows" rather than "dark for ever".
        """
        fresh_app.navigate_to_tab("Settings")
        assert fresh_app.is_selected("ThemeSystemRadio"), \
            "a clean install must start on System"

        fresh_app.choose("ThemeLightRadio")
        time.sleep(1.0)
        assert verify.read_settings().get("Theme") == 2

        # Relaunch against the same settings file, as a customer would.
        fresh_app.close_app()
        fresh_app.launch_app(clean_state=False, extra_args=["--skip-first-run"])
        fresh_app.connect_window()
        time.sleep(1.0)
        fresh_app.focus(force=True)

        fresh_app.navigate_to_tab("Settings")
        assert fresh_app.is_selected("ThemeLightRadio"), \
            "the choice must come back after a restart"
        assert self._mean_brightness(fresh_app) > self.LIGHT_FLOOR

    def test_the_keyboard_can_reach_and_use_the_appearance_control(self):
        """
        DESIGN_SYSTEM.md §13. Tab must land on the Appearance options and Space
        must choose one -- the control is not mouse-only.

        Left for the orchestrator's run: it needs real key input to the focused
        window, which is exactly what tier 3 owns.
        """
        pytest.skip("keyboard walk: run as part of the scheduled tier 3 pass")


# ============================================ settings rail (F22, Task 2)

@pytest.mark.ui
class TestSettingsRail:
    """F22: the section rail jumps to a group and tracks scroll position.

    Not run here — Smart App Control blocks launching the built app on this
    machine. Written per the brief for Miles/Keenan to run once SAC is off.
    """

    def test_about_link_scrolls_updates_into_view(self, app):
        app.navigate_to_tab("Settings")
        app.click("SettingsNav_About")
        assert app.is_on_screen("CheckForUpdatesButton")
        assert app.is_selected("SettingsNav_About")

    def test_focus_link_scrolls_break_minutes_into_view(self, app):
        app.navigate_to_tab("Settings")
        app.click("SettingsNav_Focus")
        assert app.is_on_screen("ShortBreakMinutesInput")
        assert app.is_selected("SettingsNav_Focus")


# =================================================== the Schedule page (F6)

class TestSchedulePage:
    """F6: templates and schedules, with the sleep window below them, unchanged."""

    def test_the_built_in_templates_are_listed(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        for name in ("Homework evening", "Exam prep", "Light study"):
            assert fresh_app.exists(f"TemplateRow_{name}", timeout=3), name

    def test_the_sleep_window_is_still_on_the_page(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        assert fresh_app.exists("SleepBlockToggle", timeout=3)
        assert fresh_app.exists("SaveSleepWindowButton", timeout=3)

    def test_adding_a_schedule_saves_it(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        assert fresh_app.text_of("ScheduleNextUpText") == "No schedules yet"
        fresh_app.add_schedule("Homework evening", ["Mon", "Tue", "Wed", "Thu"], "17:00")
        schedules = verify.wait_for_settings(lambda st: len(st["Schedules"]) == 1,
                                             what="the new schedule")["Schedules"]
        s = schedules[0]
        assert s["Days"] == [1, 2, 3, 4] and s["StartMinuteOfDay"] == 17 * 60 and s["AskFirst"] is True
        template = next(t for t in verify.read_settings()["Templates"] if t["Id"] == s["TemplateId"])
        assert template["Name"] == "Homework evening"
        assert "Mon–Thu" in fresh_app.text_of(f"ScheduleRow_{s['Id']}")
        next_up = fresh_app.text_of("ScheduleNextUpText")
        assert next_up.startswith("Next: ") and next_up.endswith("17:00 · Homework evening"), next_up

    def test_save_is_refused_without_a_day(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("AddScheduleButton")
        fresh_app.choose("ScheduleTemplate_Light study")
        assert not fresh_app.is_control_enabled("SaveScheduleButton")

    def test_a_new_schedule_starts_from_the_first_template(self, fresh_app):
        """The picker shows which template Save would use; nothing is chosen invisibly."""
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("AddScheduleButton")
        assert fresh_app.is_selected("ScheduleTemplate_Homework evening")
        assert not fresh_app.is_selected("ScheduleTemplate_Exam prep")

    def test_editing_a_schedule_opens_it_as_saved_and_keeps_its_id(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.add_schedule("Exam prep", ["Sat"], "09:00", ask_first=False)
        original = verify.wait_for_settings(lambda st: len(st["Schedules"]) == 1,
                                            what="the new schedule")["Schedules"][0]

        fresh_app.click(f"EditSchedule_{original['Id']}")
        assert fresh_app.is_selected("ScheduleTemplate_Exam prep")
        assert fresh_app.toggle_state("ScheduleDay_Sat") is True
        assert fresh_app.toggle_state("ScheduleDay_Mon") is False
        assert fresh_app.text_of("ScheduleTimeInput") == "09:00"
        assert fresh_app.toggle_state("ScheduleAskFirstToggle") is False

        fresh_app.set_text("ScheduleTimeInput", "10:30")
        fresh_app.click("SaveScheduleButton")
        fresh_app.wait_until_gone("SaveScheduleButton")
        schedules = verify.wait_for_settings(
            lambda st: st["Schedules"] and st["Schedules"][0]["StartMinuteOfDay"] == 10 * 60 + 30,
            what="the edited start time")["Schedules"]
        assert len(schedules) == 1, "editing must not add a second schedule"
        assert schedules[0]["Id"] == original["Id"]

    def test_a_schedule_can_be_switched_off(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.add_schedule("Light study", ["Sun"], "19:00")
        schedule_id = verify.wait_for_settings(lambda st: len(st["Schedules"]) == 1,
                                               what="the new schedule")["Schedules"][0]["Id"]

        assert fresh_app.set_toggle(f"ScheduleEnabled_{schedule_id}", False) is False
        verify.wait_for_settings(lambda st: st["Schedules"][0]["Enabled"] is False,
                                 what="the schedule switched off")
        assert fresh_app.text_of("ScheduleNextUpText") == "All your schedules are off"

    def test_a_sealed_sprint_refuses_a_schedule_change_through_automation(self, fresh_app):
        """
        CLAUDE.md, "Covered controls": prove the lock by what happens, not by
        the grey. The row's switch is driven through UI Automation's Toggle
        pattern and its Delete through Invoke, the way a test or an assistive
        tool would reach them; the file must not change and the switch must
        still read as saved. WPF refuses either pattern on a disabled control
        with an exception, which is one acceptable way to refuse.
        """
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.add_schedule("Light study", ["Sun"], "19:00")
        before = verify.wait_for_settings(lambda st: len(st["Schedules"]) == 1,
                                          what="the new schedule")["Schedules"]
        schedule_id = before[0]["Id"]
        assert before[0]["Enabled"] is True

        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Sealed")
        fresh_app.start_sprint()
        fresh_app.wait_out_grace_period()
        try:
            fresh_app.navigate_to_tab("Schedule")
            refusals = []
            switch = fresh_app.element(f"ScheduleEnabled_{schedule_id}")
            try:
                switch.iface_toggle.Toggle()
            except Exception as exc:                      # noqa: BLE001
                refusals.append(f"toggle: {type(exc).__name__}")
            delete = fresh_app.element(f"DeleteSchedule_{schedule_id}")
            try:
                delete.iface_invoke.Invoke()
            except Exception as exc:                      # noqa: BLE001
                refusals.append(f"delete: {type(exc).__name__}")

            assert fresh_app.toggle_state(f"ScheduleEnabled_{schedule_id}") is True, \
                "the switch must still show the saved state"
            assert fresh_app.exists(f"ScheduleRow_{schedule_id}", timeout=2), \
                "the row must still be there"
            # A refusal has no outcome to wait for; give a wrongly accepted
            # change the same moment the profile-switcher test does.
            time.sleep(0.8)
            assert verify.read_settings()["Schedules"] == before, \
                f"Sealed must keep the schedules exactly as saved (refusals: {refusals})"
            assert "Sealed" in fresh_app.text_of("ScheduleStatusText")
        finally:
            fresh_app.navigate_to_tab("Today")
            fresh_app.stop_sprint()

    def test_deleting_a_template_deletes_its_schedules_after_a_confirmation(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.add_schedule("Exam prep", ["Sat"], "09:00")
        fresh_app.click("DeleteTemplate_Exam prep")
        assert "1 schedule" in (fresh_app.accept_dialog() or ""), \
            "the confirmation names what goes with it"
        settings = verify.wait_for_settings(lambda st: st["Schedules"] == [],
                                            what="the schedule going with its template")
        assert all(t["Name"] != "Exam prep" for t in settings["Templates"])

    def test_restore_brings_back_a_deleted_built_in(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("DeleteTemplate_Light study")
        assert fresh_app.accept_dialog() is not None, "deleting a template asks first"
        assert not fresh_app.exists("TemplateRow_Light study", timeout=1.5)
        fresh_app.click("RestoreTemplatesButton")
        assert fresh_app.exists("TemplateRow_Light study", timeout=3)

    def test_a_new_template_is_saved_with_its_settings(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("NewTemplateButton")
        fresh_app.set_text("TemplateNameInput", "Reading")
        fresh_app.set_text("TemplateMinutesInput", "30")
        fresh_app.choose("TemplateShield_Soft")
        fresh_app.choose("TemplateCycle_2")
        fresh_app.set_text("TemplateBreakInput", "7")
        fresh_app.click("SaveTemplateButton")

        assert fresh_app.exists("TemplateRow_Reading", timeout=3)
        settings = verify.wait_for_settings(lambda st: any(t["Name"] == "Reading" for t in st["Templates"]),
                                            what="the Reading template")
        saved = next(t for t in settings["Templates"] if t["Name"] == "Reading")
        assert (saved["SprintMinutes"], saved["CycleSprints"], saved["BreakMinutes"]) == (30, 2, 7)
        assert saved["Shield"] in (1, "Soft")
        assert saved["ProfileId"] == "", "no profile chosen means whichever is active"
        assert saved["BuiltInKey"] == ""

    def test_a_second_template_with_the_same_name_gets_a_number(self, fresh_app):
        """Rows and their buttons are addressed by name, so two "Reading"s would be one."""
        fresh_app.navigate_to_tab("Schedule")
        for _ in range(2):
            fresh_app.click("NewTemplateButton")
            fresh_app.set_text("TemplateNameInput", "Reading")
            fresh_app.click("SaveTemplateButton")
            fresh_app.wait_until_gone("SaveTemplateButton")

        assert fresh_app.exists("TemplateRow_Reading", timeout=3)
        assert fresh_app.exists("TemplateRow_Reading 2", timeout=3)
        settings = verify.wait_for_settings(
            lambda st: sum(t["Name"].startswith("Reading") for t in st["Templates"]) == 2,
            what="both Reading templates")
        assert [t["Name"] for t in settings["Templates"]][-2:] == ["Reading", "Reading 2"]

    def test_a_template_length_out_of_range_is_refused(self, fresh_app):
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("NewTemplateButton")
        # The labels say the same limits Save checks, built from one set of constants.
        assert fresh_app.text_of("TemplateMinutesLabel") == "Sprint minutes (5–240)"
        assert fresh_app.text_of("TemplateBreakLabel") == "Break minutes (1–60)"
        fresh_app.set_text("TemplateNameInput", "Marathon")
        fresh_app.set_text("TemplateMinutesInput", "300")
        fresh_app.click("SaveTemplateButton")

        status = fresh_app.text_of("TemplateStatusText")
        assert "5" in status and "240" in status, status
        assert all(t["Name"] != "Marathon" for t in verify.read_settings()["Templates"])

    def test_a_template_can_use_a_blocklist_profile(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.new_profile("School")
        settings = verify.wait_for_settings(lambda st: any(p["Name"] == "School" for p in st["Profiles"]),
                                            what="the School profile")
        school = next(p for p in settings["Profiles"] if p["Name"] == "School")

        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("NewTemplateButton")
        assert fresh_app.is_selected("TemplateProfileActive"), \
            "a new template follows whichever profile is active"
        fresh_app.set_text("TemplateNameInput", "Maths")
        fresh_app.choose("TemplateProfile_School")
        fresh_app.click("SaveTemplateButton")

        settings = verify.wait_for_settings(lambda st: any(t["Name"] == "Maths" for t in st["Templates"]),
                                            what="the Maths template")
        saved = next(t for t in settings["Templates"] if t["Name"] == "Maths")
        assert saved["ProfileId"] == school["Id"]

    def test_a_sealed_sprint_makes_the_page_read_only(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Sealed")
        fresh_app.start_sprint()
        fresh_app.wait_out_grace_period()
        try:
            fresh_app.navigate_to_tab("Schedule")
            for auto_id in ("AddScheduleButton", "NewTemplateButton", "RestoreTemplatesButton",
                            "EditTemplate_Exam prep", "DeleteTemplate_Exam prep"):
                # is_control_enabled says False for a control it can't find,
                # so prove it is there first.
                assert fresh_app.exists(auto_id, timeout=3), auto_id
                assert not fresh_app.is_control_enabled(auto_id), \
                    f"{auto_id} must be locked during a Sealed sprint"
            assert "Sealed" in fresh_app.text_of("ScheduleStatusText")
        finally:
            fresh_app.navigate_to_tab("Today")
            fresh_app.stop_sprint()

    def test_the_mouse_wheel_scrolls_the_page_over_the_sleep_window(self, fresh_app):
        """
        The embedded sleep view keeps its own ScrollViewer. Inside this page it
        has nothing to scroll, but WPF still marks every wheel turn over it as
        handled, so the page would stop moving under the pointer.
        """
        import pywinauto.mouse as mouse

        fresh_app.navigate_to_tab("Schedule")
        # To the foot of the page through the Scroll pattern, which doesn't
        # depend on what is under the pointer; the sleep window is last.
        fresh_app.element("SchedulePageScroll").iface_scroll.SetScrollPercent(-1, 100)
        time.sleep(0.6)
        window = fresh_app.window.rectangle()
        before = fresh_app.element("SaveSleepWindowButton").rectangle()
        assert window.top < before.top < window.bottom, "the sleep window's Save is on screen"

        # One turn up with the pointer on the sleep window's own button.
        mouse.scroll(coords=((before.left + before.right) // 2, (before.top + before.bottom) // 2),
                     wheel_dist=1)
        time.sleep(0.6)
        after = fresh_app.element("SaveSleepWindowButton").rectangle()
        assert after.top > before.top, "a wheel turn over the sleep window must scroll the page"


# ============================ scheduled sprints and Today's chips (F6, PR C)

class TestScheduledSprints:
    """F6 done-when: a schedule a minute ahead starts, after a heads-up that can skip it."""

    # Saving a schedule through the editor is several seconds of clicks, so
    # the start has to be further off than that or it passes before Save.
    SETUP_SECONDS = 30

    # --short-schedules: the heads-up lead, the late window and how late a
    # tick may be and still start (SchedulePlanner; pinned in tier 1).
    LEAD_SECONDS = 15
    ON_TIME_SECONDS = 3

    TARGET = "flowshield-test-target"

    def _schedule_in(self, app, seconds: int = 70, template="Light study", ask=True,
                     setup_seconds: int | None = None) -> datetime:
        """
        A schedule for the whole minute `seconds` from now. The editor takes
        HH:MM, so the start rounds down to the minute; one that would land
        inside `setup_seconds` (SETUP_SECONDS by default) moves on a minute.
        Returns the start, which is still more than a lead and a tick away.
        """
        now = datetime.now()
        at = (now + timedelta(seconds=seconds)).replace(second=0, microsecond=0)
        if (at - now).total_seconds() < (setup_seconds or self.SETUP_SECONDS):
            at += timedelta(minutes=1)
        app.navigate_to_tab("Schedule")
        app.add_schedule(template, [at.strftime("%a")], at.strftime("%H:%M"), ask_first=ask)
        verify.wait_for_settings(lambda st: len(st.get("Schedules") or []) == 1, what="the schedule")
        assert datetime.now() < at - timedelta(seconds=self.LEAD_SECONDS + 1), \
            "the editor took so long the heads-up was missed"
        return at

    def _wait_past_the_start(self, at: datetime) -> None:
        """Until the start and its on-time window are behind us, plus a tick or two, so a start would show."""
        while datetime.now() < at + timedelta(seconds=self.ON_TIME_SECONDS + 5):
            time.sleep(0.5)

    def _decoy(self, tmp_path):
        """A blocked app that is open: a renamed ping, as TestPreSprintWarning uses."""
        import shutil
        exe = tmp_path / f"{self.TARGET}.exe"
        shutil.copy2(Path(os.environ["WINDIR"]) / "System32" / "PING.EXE", exe)
        return subprocess.Popen(
            [str(exe), "-n", "300", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    @staticmethod
    def _wait_for_sprint(app, timeout: float = 40) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if "Shield" in app.session_state():
                return True
            time.sleep(0.5)
        return False

    START_NOTICES = ("SprintStarted", "ScheduledSprint")

    @staticmethod
    def _log_lines(app) -> list[str]:
        path = app.app_log_path()
        return path.read_text(encoding="utf-8", errors="replace").splitlines() if path else []

    def _start_notices_since(self, app, seen: int, expected: str, timeout: float = 5) -> list[str]:
        """
        The start notifications the app logged ("notification: <kind>") after
        its first `seen` log lines, once `expected` is among them or the
        timeout passes. Call it once the sprint shows as running: a start's
        notices go out in the same dispatcher turn, so all of them are logged.
        """
        deadline = time.time() + timeout
        while True:
            kinds = [line.rsplit("notification: ", 1)[1].strip()
                     for line in self._log_lines(app)[seen:] if "notification: " in line]
            kinds = [kind for kind in kinds if kind in self.START_NOTICES]
            if expected in kinds or time.time() >= deadline:
                return kinds
            time.sleep(0.25)

    def test_heads_up_then_it_starts(self, schedule_app):
        self._schedule_in(schedule_app)
        schedule_app.navigate_to_tab("Today")
        schedule_app.wait_until_control_enabled("HeadsUpStartNowButton", timeout=100)
        # Read straight away: under --short-schedules the card is up for fifteen seconds.
        title = schedule_app.text_of("HeadsUpCard")
        text = schedule_app.text_of("HeadsUpText")
        assert title.startswith("Light study starts at "), title
        assert text == "25 minutes at Soft.", text

        assert self._wait_for_sprint(schedule_app), "the sprint started by itself"
        sprint = verify.read_settings()["ActiveSprint"]
        assert sprint["Shield"] == 1   # Soft, from the template
        assert sprint["TemplateBreakMinutes"] == 5, "the template's own break rides with the sprint"
        assert not schedule_app.exists("HeadsUpStartNowButton", timeout=0.5), "the card has done its job"

    def test_skip_today_stops_it(self, schedule_app):
        at = self._schedule_in(schedule_app)
        schedule_app.navigate_to_tab("Today")
        schedule_app.wait_until_control_enabled("HeadsUpSkipButton", timeout=100)
        schedule_app.click("HeadsUpSkipButton")
        # A click that lands after the start would read as Skip not working.
        assert datetime.now() < at, f"Skip was clicked after the start; too slow for the {self.LEAD_SECONDS}-second lead"
        settings = verify.wait_for_settings(
            lambda st: bool(st["Schedules"][0]["SkippedDatesLocal"]), what="the skip")
        assert settings["Schedules"][0]["SkippedDatesLocal"] == [at.strftime("%Y-%m-%dT00:00:00")], \
            "the start's own date, with no offset"

        # Past the start and its on-time window: nothing started.
        self._wait_past_the_start(at)
        assert verify.read_settings().get("ActiveSprint") is None
        assert "Shield" not in schedule_app.session_state()

    def test_the_heads_up_names_the_app_it_will_close_and_stands_in_for_the_question(
            self, schedule_app, tmp_path):
        process = self._decoy(tmp_path)
        try:
            schedule_app.navigate_to_tab("Blocked Apps")
            assert schedule_app.add_blocked_app(self.TARGET)
            self._schedule_in(schedule_app, template="Homework evening")
            schedule_app.navigate_to_tab("Today")
            schedule_app.wait_until_control_enabled("HeadsUpStartNowButton", timeout=100)
            text = schedule_app.text_of("HeadsUpText")
            assert text.lower().startswith("45 minutes at firm."), text
            assert f"{self.TARGET} will be closed." in text.lower(), text

            assert self._wait_for_sprint(schedule_app), "the heads-up named it, so nothing is asked"
            assert not schedule_app.exists("RunningAppsTitle", timeout=0.5)
            assert verify.read_settings()["ActiveSprint"]["TemplateBreakMinutes"] == 10
        finally:
            if process.poll() is None:
                process.kill()

    def test_without_a_heads_up_an_open_app_is_asked_about_first(self, schedule_app, tmp_path):
        """
        Ask first off: nothing named the app, so the start waits on F7's
        question, as quick start does (#270). Answering it starts the template.
        """
        process = self._decoy(tmp_path)
        try:
            schedule_app.navigate_to_tab("Blocked Apps")
            assert schedule_app.add_blocked_app(self.TARGET)
            self._schedule_in(schedule_app, template="Homework evening", ask=False)
            schedule_app.navigate_to_tab("Schedule")   # away from Today: the question brings it back

            assert schedule_app.exists("RunningAppsTitle", timeout=100), "the question never came"
            assert schedule_app.current_page_title() == "Today"
            assert not schedule_app.exists("StopSprintButton", timeout=1)
            assert process.poll() is None, "nothing may be closed before the answer"
            assert verify.read_settings().get("ActiveSprint") is None

            seen = len(self._log_lines(schedule_app))
            schedule_app.click("StartAnywayButton")
            assert schedule_app.exists("StopSprintButton", timeout=5), "the answer starts the template"
            sprint = verify.wait_for_settings(lambda st: st.get("ActiveSprint") is not None,
                                              what="the sprint")["ActiveSprint"]
            assert sprint["PlannedMinutes"] == 45 and sprint["TemplateBreakMinutes"] == 10
            assert self._start_notices_since(schedule_app, seen, "ScheduledSprint") == ["ScheduledSprint"], \
                "the answered start is still the schedule's, named once"
        finally:
            if process.poll() is None:
                process.kill()

    def test_a_start_without_asking_sends_one_notification(self, schedule_app):
        """
        Review of PR C: "Sprint started" is on by default, so a start with Ask
        first off sent it and "Light study started" back to back. The named
        one (spec 3.3) stands in for it: one start, one notification.
        """
        self._schedule_in(schedule_app, ask=False)
        schedule_app.navigate_to_tab("Today")
        seen = len(self._log_lines(schedule_app))
        assert self._wait_for_sprint(schedule_app, timeout=100), "the sprint started by itself"
        assert self._start_notices_since(schedule_app, seen, "ScheduledSprint") == ["ScheduledSprint"]

    def _wait_for_log_line(self, app, needle: str, since: int, deadline: datetime, what: str) -> None:
        """
        Poll the app log for `needle` after its first `since` lines until
        `deadline`; a miss fails as `what`, not as a timeout. The log is one
        file a day, so an earlier run's line would otherwise match at once.
        """
        while not any(needle in line for line in self._log_lines(app)[since:]):
            assert datetime.now() < deadline, what
            time.sleep(0.2)

    def test_a_start_whose_heads_up_fell_in_a_hand_sprint_is_offered_not_started(self, schedule_app):
        """
        Final review of PR C: Ask first promises a question before a start.
        A sprint running when the heads-up is due swallows it (the scheduler
        refuses while busy, and remembers the heads-up as shown), so at the
        time nobody had been asked. The start is then offered on the card,
        never taken. A 25-minute hand sprint ending between T-15 and T is
        enough; here one is stopped by hand inside that window.
        """
        since = len(self._log_lines(schedule_app))     # this launch's lines only
        # Room for the editor and a hand Start before the heads-up is due.
        at = self._schedule_in(schedule_app, setup_seconds=self.SETUP_SECONDS + self.LEAD_SECONDS)
        schedule_app.navigate_to_tab("Today")
        schedule_app.select_shield("Soft")             # a fresh state starts at Firm, whose Stop asks first
        schedule_app.start_sprint()
        assert datetime.now() < at - timedelta(seconds=self.LEAD_SECONDS + 1), \
            "Start landed too late for the heads-up to fall inside the sprint"

        # The heads-up tick lands while the sprint runs: refused, and remembered
        # as shown. The sprint is then stopped inside the lead: one lookup and
        # an invoke, not click()'s resolve-scroll-settle, so the stop lands
        # seconds before the start instead of racing it (#241). Soft ends on
        # one press, in or out of the grace period.
        stop = schedule_app.element("StopSprintButton")
        self._wait_for_log_line(schedule_app, "schedule HeadsUp for Light study skipped: busy or gated",
                                since=since, deadline=at, what="the heads-up was not swallowed by the sprint")
        try:
            stop.invoke()
        except Exception:                                  # noqa: BLE001
            stop.click_input()
        stopped_at = datetime.now()
        seen = len(self._log_lines(schedule_app))
        assert stopped_at < at, f"the sprint ended after the start; too slow for the {self.LEAD_SECONDS}-second lead"
        ended_by = time.time() + 5
        while "Shield" in schedule_app.session_state():
            assert time.time() < ended_by, "the Stop press did not end the sprint"
            time.sleep(0.2)

        schedule_app.wait_until_control_enabled("HeadsUpStartNowButton", timeout=20)
        assert schedule_app.text_of("HeadsUpCard") == "Light study is due now"
        assert schedule_app.text_of("HeadsUpText") == "25 minutes at Soft."
        assert not any("schedule card shown: HeadsUp for Light study" in line
                       for line in self._log_lines(schedule_app)[since:]), \
            "no heads-up card was ever up: this offer is the first question"

        # Past the start and its on-time window: offered, not started.
        self._wait_past_the_start(at)
        assert verify.read_settings().get("ActiveSprint") is None
        assert "Shield" not in schedule_app.session_state()
        assert schedule_app.exists("HeadsUpStartNowButton", timeout=0.5), "the offer stays up"
        assert self._start_notices_since(schedule_app, seen, "ScheduledSprint") == ["ScheduledSprint"], \
            "the offer is announced once, and no start is"

        # The offer is live: Start now starts the template, with its own break.
        schedule_app.click("HeadsUpStartNowButton")
        assert self._wait_for_sprint(schedule_app, timeout=10), "Start now starts the template"
        sprint = verify.wait_for_settings(lambda st: st.get("ActiveSprint") is not None,
                                          what="the sprint")["ActiveSprint"]
        assert sprint["PlannedMinutes"] == 25 and sprint["TemplateBreakMinutes"] == 5
        assert not schedule_app.exists("HeadsUpStartNowButton", timeout=0.5), "the card has done its job"

    def test_a_template_chip_fills_in_today(self, fresh_app):
        fresh_app.select_shield("Soft")
        fresh_app.click("TemplateChip_Homework evening")
        assert fresh_app.is_selected("Shield_Firm")
        assert fresh_app.is_selected("SprintLength_45")
        assert fresh_app.is_selected("Cycle_3")
        settings = verify.wait_for_settings(lambda st: st["CycleSprints"] == 3, what="the template's cycle")
        assert settings["CycleSprints"] == 3

    def test_a_chip_carries_the_templates_break_to_a_hand_start(self, fresh_app):
        """
        PR C polish, item 9: the chip's preset includes the template's break
        length, and a hand change of length afterwards keeps it, so the
        sprint started by Start takes the template's breaks (Light study: 5).
        """
        fresh_app.click("TemplateChip_Light study")
        assert fresh_app.is_selected("SprintLength_25")
        fresh_app.click("SprintLength_15")
        fresh_app.start_sprint()
        sprint = verify.wait_for_settings(lambda st: st.get("ActiveSprint") is not None,
                                          what="the sprint")["ActiveSprint"]
        assert sprint["PlannedMinutes"] == 15, "the hand change of length stands"
        assert sprint["TemplateBreakMinutes"] == 5, "the chip's break rides with the sprint"

    def test_a_template_between_the_preset_lengths_uses_custom(self, fresh_app):
        """Also shows a new template reaching Today's chips (TemplatesChanged)."""
        fresh_app.navigate_to_tab("Schedule")
        fresh_app.click("NewTemplateButton")
        fresh_app.set_text("TemplateNameInput", "Reading")
        fresh_app.set_text("TemplateMinutesInput", "30")
        fresh_app.click("SaveTemplateButton")
        fresh_app.wait_until_gone("SaveTemplateButton")

        fresh_app.navigate_to_tab("Today")
        fresh_app.click("TemplateChip_Reading")
        assert fresh_app.is_selected("SprintLength_Custom")
        assert fresh_app.text_of("CustomMinutesInput") == "30"
        assert fresh_app.text_of("SprintTimerText") == "30:00"

    def test_the_chips_hide_while_a_sprint_runs(self, fresh_app):
        assert fresh_app.exists("TemplateChip_Light study", timeout=3)
        fresh_app.start_sprint()
        try:
            fresh_app.wait_until_gone("TemplateChip_Light study")
        finally:
            fresh_app.cancel_sprint()
        assert fresh_app.exists("TemplateChip_Light study", timeout=3), "back once the sprint is over"


# ===================================================== the taskbar Jump List (1.0.10)

class TestJumpList:
    """
    Spec 5: right-clicking FlowShield on the taskbar offers Start sprint and
    Start <template>, which run FlowShield.exe --start-sprint and
    --start-sprint=<templateId>. An entry does nothing but run its command
    line, so these run the command lines rather than the shell's menu. A cold
    launch handles the argument after startup; a launch while FlowShield runs
    hands it over the single-instance pipe.
    """

    MISSING = "That template isn't here any more. Pick one on Today."
    RUNNING = "A sprint is already running."

    @staticmethod
    def _template_id(name: str) -> str:
        return next(t["Id"] for t in verify.read_settings()["Templates"] if t["Name"] == name)

    @staticmethod
    def _running_sprint(app) -> dict:
        # A blocked app already open on this PC is asked about first (F7).
        app.answer_open_apps_question(timeout=5)
        assert app.exists("StopSprintButton", timeout=10), "no sprint started"
        return verify.wait_for_settings(lambda st: st.get("ActiveSprint") is not None,
                                        what="the sprint")["ActiveSprint"]

    @staticmethod
    def _log_lines(app) -> list[str]:
        path = app.app_log_path()
        return path.read_text(encoding="utf-8", errors="replace").splitlines() if path else []

    def _jump_list_lines(self, app, seen: int, timeout: float = 5) -> list[str]:
        """
        What the app logged about the Jump List after its first `seen` log
        lines, once there is anything or the timeout passes. The list is
        built right after the window is shown, in the same startup turn.
        """
        deadline = time.time() + timeout
        while True:
            lines = [line for line in self._log_lines(app)[seen:] if "jump list" in line]
            if lines or time.time() >= deadline:
                return lines
            time.sleep(0.25)

    @staticmethod
    def _toast(app, expected: str, timeout: float = 6) -> str:
        deadline, toast = time.time() + timeout, ""
        while toast != expected and time.time() < deadline:
            toast = app.toast_text(timeout=1)
        return toast

    def test_a_template_starts_from_a_cold_launch_and_a_deleted_one_starts_nothing(self, fresh_app):
        light = self._template_id("Light study")
        entries = len(verify.read_settings()["Templates"]) + 1   # Start sprint, then one per template
        fresh_app.close_app()
        seen = len(self._log_lines(fresh_app))
        fresh_app.launch_app(clean_state=False, extra_args=[f"--start-sprint={light}"])
        fresh_app.connect_window()

        # The list itself: built at startup, and every entry accepted by the
        # shell on this machine. Rebuild swallows a failure into a Warn, so
        # the log is the one place that says the list is really there (review).
        lines = self._jump_list_lines(fresh_app, seen)
        assert any(line.endswith(f"jump list: {entries} entries") for line in lines), lines
        assert not any("could not build the jump list" in line for line in lines), lines

        sprint = self._running_sprint(fresh_app)
        assert sprint["Shield"] == 1, "Soft, from Light study"
        assert sprint["PlannedMinutes"] == 25 and sprint["TemplateBreakMinutes"] == 5

        # A pinned list can outlive a template (review focus 5); the fallback
        # is Today, wherever the window was.
        fresh_app.navigate_to_tab("History")
        launch_again("--start-sprint=missing")
        assert flowshield_pids() == [fresh_app.pid], "the second launch kept running"
        toast = self._toast(fresh_app, self.MISSING)
        assert toast == self.MISSING, toast
        assert fresh_app.current_page_title() == "Today", "a dangling entry falls back to Today"
        assert verify.read_settings()["ActiveSprint"]["StartedUtc"] == sprint["StartedUtc"], \
            "the running sprint was replaced"

        # A template while a sprint runs: said, not silent (review).
        launch_again(f"--start-sprint={light}")
        assert flowshield_pids() == [fresh_app.pid], "the third launch kept running"
        toast = self._toast(fresh_app, self.RUNNING)
        assert toast == self.RUNNING, toast
        assert verify.read_settings()["ActiveSprint"]["StartedUtc"] == sprint["StartedUtc"], \
            "the running sprint was replaced"

    def test_start_sprint_reaches_a_running_copy_as_the_trays_quick_start(self, fresh_app):
        """No template: Today's last settings, exactly as the tray's Start sprint takes them."""
        fresh_app.select_shield("Soft")
        fresh_app.select_sprint_length(15)

        launch_again("--start-sprint")
        assert flowshield_pids() == [fresh_app.pid], "the second launch kept running"
        sprint = self._running_sprint(fresh_app)
        assert sprint["Shield"] == 1 and sprint["PlannedMinutes"] == 15
        assert sprint.get("TemplateBreakMinutes") is None, "no template was involved"
