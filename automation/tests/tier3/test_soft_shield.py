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

    Since #432 every button ignores input for about 1.5 s when the notice
    opens (DESIGN_SYSTEM.md Part A, Interruptions), so a test that means to
    press one waits for the lock to end first (_wait_until_unlocked). The
    buttons stay enabled throughout; what changes is that they become
    keyboard-focusable, which UI Automation reports.
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

    @pytest.fixture
    def long_lock_app(self, logger):
        """
        A fresh Basalt whose notice keeps its buttons locked for six seconds
        (--long-notice-lock) instead of 1.5, so a test can click inside the
        lock and see nothing happen: 1.5 s is shorter than a UIA round trip
        or two (#242). Only the clock changes; the gate is the same.
        """
        from config import APP_EXE
        from desktop.app_controller import DesktopController

        if not Path(APP_EXE).exists():
            pytest.skip(f"{APP_EXE} not built")
        ctrl = DesktopController(logger)
        ctrl.launch_app(clean_state=True, extra_args=["--long-notice-lock"])
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
    def _wait_until_focusable(control, timeout):
        """
        A button on the notice takes input once it can take keyboard focus:
        the lock, and Allow's own wait, keep it enabled but unfocusable (#432).
        Raced against a deadline rather than slept on (#146).
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if control.is_keyboard_focusable():
                    return True
            except Exception:
                pass
            time.sleep(0.1)
        return False

    def _wait_until_unlocked(self, overlay, timeout=10):
        """The lock is over once Back to work can take focus."""
        back = overlay.child_window(auto_id="SoftOverlayBackToWorkButton").wrapper_object()
        assert self._wait_until_focusable(back, timeout), "the notice's buttons never unlocked"

    @staticmethod
    def _log_mark(app) -> int:
        """
        How many lines the app log holds now. The log outlives a --reset
        launch, so an earlier test's "back to work from charmap" is still in
        it: a test that asserts something did *not* happen reads only the
        lines written after its own mark.
        """
        path = app.app_log_path()
        if path is None:
            return 0
        try:
            return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            return 0

    @staticmethod
    def _logged_since(app, mark: int, needle: str) -> bool:
        path = app.app_log_path()
        if path is None:
            return False
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return False
        return any(needle.lower() in line.lower() for line in lines[mark:])

    def _wait_logged_since(self, app, mark: int, needle: str, timeout=10) -> bool:
        """Raced against a deadline rather than slept on (#146)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._logged_since(app, mark, needle):
                return True
            time.sleep(0.25)
        return False

    @staticmethod
    def _shows(overlay, auto_id, timeout=1.0) -> bool:
        """A collapsed element leaves the UIA tree, so a hidden one doesn't exist."""
        try:
            return overlay.child_window(auto_id=auto_id).exists(timeout=timeout)
        except Exception:
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

            self._wait_until_unlocked(overlay)
            overlay.child_window(auto_id="SoftOverlayBackToWorkButton").click_input()
            time.sleep(1.5)
            assert self._overlay(timeout=2) is None, "Back to work must take it down"
            assert process.poll() is None, "Back to work must not close the blocked app"
        finally:
            if process.poll() is None:
                process.kill()

    def test_enter_does_nothing_and_no_button_is_default_or_focused(self, fresh_app):
        """
        #432 (Part A, Interruptions): the notice lands up to one blocker sweep
        after the blocked app came to the front, while the user may still be
        typing in it. No button is the default and none has focus when it
        opens, and Enter does nothing, during the lock and after it: the
        notice stays up, nothing is answered, the app keeps running.
        """
        process = self._decoy()
        try:
            mark = self._log_mark(fresh_app)
            self._arm_and_start(fresh_app, process)

            overlay = self._overlay()
            assert overlay is not None, (
                "a blocked app was the foreground window at Soft and nothing said so"
            )
            buttons = [overlay.child_window(auto_id=aid).wrapper_object() for aid in
                       ("SoftOverlayBackToWorkButton", "SoftOverlayCloseButton",
                        "SoftOverlayAllowButton")]
            for button in buttons:
                assert not button.has_keyboard_focus(), (
                    f"{button.window_text()!r} has focus at open; focus starts on the band")

            overlay.type_keys("{ENTER}", set_foreground=True)
            self._wait_until_unlocked(overlay)
            for button in buttons:
                assert not button.has_keyboard_focus(), (
                    f"{button.window_text()!r} took focus by itself after the lock")
            overlay.type_keys("{ENTER}", set_foreground=True)
            time.sleep(1.5)

            assert self._overlay(timeout=2) is not None, "Enter must not answer the notice"
            assert not self._logged_since(fresh_app, mark, f"back to work from {self.TARGET}"), (
                "Enter must not be Back to work: no button is the default")
            assert not self._logged_since(fresh_app, mark, f"soft notice: close {self.TARGET} chosen"), (
                "Enter must never ask the blocked app to close"
            )
            assert process.poll() is None, "Enter must never close the blocked app"
        finally:
            if process.poll() is None:
                process.kill()

    def test_every_button_ignores_input_during_the_lock(self, long_lock_app):
        """
        #432: for the lock (six seconds here, 1.5 s for a customer; see
        long_lock_app) every button ignores clicks, Space and Enter. They
        stay enabled, so their labels keep full contrast, but can't take
        focus, and the wait is shown. After it, a deliberate Tab then Space
        works: Tab from the band lands on Back to work.
        """
        app = long_lock_app
        process = self._decoy()
        try:
            mark = self._log_mark(app)
            self._arm_and_start(app, process)

            overlay = self._overlay()
            assert overlay is not None, (
                "a blocked app was the foreground window at Soft and nothing said so"
            )
            close = overlay.child_window(auto_id="SoftOverlayCloseButton").wrapper_object()
            back = overlay.child_window(auto_id="SoftOverlayBackToWorkButton").wrapper_object()

            # A click, Space and Enter inside the lock, first, while the lock
            # has the most time left: nothing happens.
            close.click_input()
            overlay.type_keys("{SPACE}{ENTER}", set_foreground=True)
            assert not back.is_keyboard_focusable(), (
                "the lock ended before the test could act inside it; the click proved nothing")
            for button in (close, back):
                assert button.is_enabled(), "a locked button stays enabled, at full contrast"
                assert not button.is_keyboard_focusable(), "a locked button can't take focus"
            wait = overlay.child_window(auto_id="SoftOverlayWait").window_text()
            assert wait.startswith("Buttons unlock"), wait
            time.sleep(1.0)
            assert self._overlay(timeout=2) is not None, "a click inside the lock must be ignored"
            assert not self._logged_since(app, mark, f"soft notice: close {self.TARGET} chosen"), (
                "Close was answered inside the lock")
            assert not self._logged_since(app, mark, f"back to work from {self.TARGET}")
            assert process.poll() is None, "nothing may close the app inside the lock"

            self._wait_until_unlocked(overlay)
            wait = overlay.child_window(auto_id="SoftOverlayWait").window_text()
            assert "Tab then Space" in wait, wait

            # Deliberate: Tab from the band to Back to work, then Space.
            overlay.type_keys("{TAB}", set_foreground=True)
            deadline = time.time() + 5
            while time.time() < deadline and not back.has_keyboard_focus():
                time.sleep(0.1)
            assert back.has_keyboard_focus(), "Tab from the band must land on Back to work"
            overlay.type_keys("{SPACE}", set_foreground=False)

            assert self._wait_logged_since(app, mark, f"back to work from {self.TARGET}"), (
                "Tab then Space after the lock is Back to work")
            assert process.poll() is None, "Back to work leaves the app running"
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
            allow = overlay.child_window(auto_id="SoftOverlayAllowButton").wrapper_object()
            assert self._wait_until_focusable(allow, timeout=8), "Allow never became pressable"
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

    def test_allow_ignores_input_until_its_own_wait_runs_out(self, real_wait_app):
        """
        1.0.10: Allow 5 minutes waits (5, 10, 20, then 30 s) before it can be
        pressed, beyond the 1.5 s lock every button has (#432). It stays
        enabled, its countdown in its label, but can't take focus and ignores
        a click. The try count is hidden on the first try and shows on the
        second (#432).

        Run with the real waits: the three-second --short-timers wait is
        shorter than the suite can observe (see real_wait_app). The click is
        made on the second try, whose ten-second wait leaves room for UIA.
        """
        app = real_wait_app
        process = self._decoy()
        try:
            mark = self._log_mark(app)
            self._arm_and_start(app, process)

            allow = self._first_sight_of("SoftOverlayAllowButton")
            assert allow is not None, (
                "a blocked app was the foreground window at Soft and nothing said so"
            )
            overlay = self._overlay(timeout=2)
            assert overlay is not None
            close = overlay.child_window(auto_id="SoftOverlayCloseButton")
            assert self.TARGET.lower() in close.window_text().lower(), close.window_text()
            assert not self._shows(overlay, "SoftOverlayTryLine"), (
                "the try count is hidden on the first try")

            # First try: once the lock is over, Close and Back to work take
            # focus, while Allow still waits, enabled and unfocusable.
            self._wait_until_unlocked(overlay)
            assert allow.is_enabled(), "Allow stays enabled while it waits"
            assert not allow.is_keyboard_focusable(), "Allow must wait before it can be pressed"
            assert "Allow 5 minutes in 0:0" in allow.window_text() or \
                allow.window_text() == "Allow 5 minutes", allow.window_text()

            overlay.child_window(auto_id="SoftOverlayBackToWorkButton").click_input()
            assert self._wait_logged_since(app, mark, f"back to work from {self.TARGET}"), (
                "Back to work was never answered")

            # Second try, after Back to work's few quiet seconds.
            time.sleep(6.0)
            self._bring_forward(process)
            overlay = self._overlay()
            assert overlay is not None, "the decoy came back and no second notice appeared"
            try_line = overlay.child_window(auto_id="SoftOverlayTryLine").window_text()
            assert "2nd try this sprint" in try_line, try_line

            self._wait_until_unlocked(overlay)
            allow = overlay.child_window(auto_id="SoftOverlayAllowButton").wrapper_object()
            assert not allow.is_keyboard_focusable(), "the second try's Allow waits ten seconds"
            allow.click_input()
            time.sleep(1.0)
            assert self._overlay(timeout=2) is not None, "a click on a waiting Allow must be ignored"
            assert not self._logged_since(app, mark, f"{self.TARGET} allowed for"), (
                "Allow was answered before its wait ran out")

            assert self._wait_until_focusable(allow, timeout=15), "Allow's wait never ran out"
            allow.click_input()
            assert self._wait_logged_since(app, mark, f"{self.TARGET} allowed for"), (
                "Allow works once its wait is over")
            assert process.poll() is None
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
            self._wait_until_unlocked(overlay)
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
            self._wait_until_unlocked(overlay)
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
        assert fresh_app.exists("SummaryMinutesValue", timeout=10), "the summary card never appeared"
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
