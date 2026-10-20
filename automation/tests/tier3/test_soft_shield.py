# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 3: soft shield."""

from __future__ import annotations
import os
import subprocess
import time
from pathlib import Path
import pytest
from core import state_verifier as verify

pytestmark = pytest.mark.ui



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
        A fresh Basalt with the real Soft waits, not --short-timers.

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

        A background SetForegroundWindow request can be refused by Windows'
        foreground lock (#250). Briefly share the foreground and target input
        queues for the handoff, then detach even if the request fails. Check
        the owning PID rather than treating a successful API call as focus.
        """
        import pywintypes
        import win32api
        import win32con
        import win32gui
        import win32process

        windows = self._decoy_windows(process)
        assert windows, "the decoy has no window to bring forward"
        hwnd = windows[0].handle
        caller = win32api.GetCurrentThreadId()
        # AttachThreadInput requires a message queue on the calling thread.
        win32gui.PeekMessage(0, 0, 0, win32con.PM_NOREMOVE)
        deadline = time.monotonic() + 5
        last_error = ""
        while time.monotonic() < deadline:
            if self._foreground_pid() == process.pid:
                return
            foreground = win32gui.GetForegroundWindow()
            foreground_thread = (win32process.GetWindowThreadProcessId(foreground)[0]
                                 if foreground else 0)
            target_thread = win32process.GetWindowThreadProcessId(hwnd)[0]
            attached = []
            try:
                for thread in dict.fromkeys((foreground_thread, target_thread)):
                    if thread and thread != caller:
                        win32process.AttachThreadInput(caller, thread, True)
                        attached.append(thread)
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
            except pywintypes.error as exc:
                last_error = str(exc)
            finally:
                for thread in reversed(attached):
                    win32process.AttachThreadInput(caller, thread, False)
            if self._foreground_pid() == process.pid:
                return
            time.sleep(0.05)
        pytest.fail(
            f"the decoy (pid {process.pid}) never became the foreground window; "
            f"foreground pid is {self._foreground_pid()}; {last_error}"
        )

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
        # answer inside Basalt's own window, which is what actually holds
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
