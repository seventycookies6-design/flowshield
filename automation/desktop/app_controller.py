"""
UI-Automation driver for the FlowShield desktop app.

Everything addresses controls by AutomationId rather than by on-screen text, so
copy changes don't break the suite. Text is only asserted on, never used to
locate.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import psutil
from pywinauto import Application, Desktop
from pywinauto.controls.uiawrapper import UIAWrapper
from pywinauto.findwindows import ElementNotFoundError
from pywinauto.timings import TimeoutError as PwaTimeoutError
from pywinauto.uia_defines import IUIA
from pywinauto.uia_element_info import UIAElementInfo

from config import (
    APP_EXE,
    APP_PROCESS_NAME,
    APP_WINDOW_TITLE,
    DESKTOP_DIR,
    SERVER_URL,
    SETTINGS_PATH,
    UI_ACTION_TIMEOUT,
    WEBSITE_URL,
    WINDOW_CONNECT_TIMEOUT,
)

TAB_IDS = {
    "today": "Tab_Today",
    "blocked apps": "Tab_BlockedApps",
    "blockedapps": "Tab_BlockedApps",
    "sleep blocking": "Tab_SleepBlocking",
    "sleepblocking": "Tab_SleepBlocking",
    "settings": "Tab_Settings",
}


class DesktopControllerError(RuntimeError):
    pass


# pywinauto's IUIA() is a Borg, but its __init__ re-derives the control-type
# lookup tables on every instantiation — ~1.6s a call, which dwarfs the ~15ms
# FindFirst it is used for. Resolve it once and reuse.
_IUIA = None
_UIA_DLL = None
_CONDITION_CACHE: dict[str, object] = {}


def _uia():
    global _IUIA, _UIA_DLL
    if _IUIA is None:
        instance = IUIA()
        _IUIA = instance.iuia
        _UIA_DLL = instance.UIA_dll
    return _IUIA, _UIA_DLL


def _automation_id_condition(auto_id: str):
    """Property conditions are immutable and reusable; build each one once."""
    if auto_id not in _CONDITION_CACHE:
        iuia, uia = _uia()
        _CONDITION_CACHE[auto_id] = iuia.CreatePropertyCondition(
            uia.UIA_AutomationIdPropertyId, auto_id
        )
    return _CONDITION_CACHE[auto_id]


class DesktopController:
    """Drives one FlowShield window."""

    def __init__(self, logger=None):
        self.log = logger
        self.app: Application | None = None
        self.window = None
        self.pid: int | None = None

    # ------------------------------------------------------------- logging

    def _say(self, message: str) -> None:
        if self.log:
            self.log.info(message)
        else:
            print(f"    {message}")

    # --------------------------------------------------------------- build

    def build_app(self, configuration: str = "Release") -> bool:
        """dotnet build. Returns True on success; raises with output on failure."""
        self._say(f"building {DESKTOP_DIR.name} ({configuration})")
        result = subprocess.run(
            ["dotnet", "build", "-c", configuration, "--nologo", "-v", "minimal"],
            cwd=str(DESKTOP_DIR),
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise DesktopControllerError(
                f"dotnet build failed ({result.returncode}):\n{result.stdout}\n{result.stderr}"
            )
        self._say("build succeeded")
        return True

    # -------------------------------------------------------------- launch

    @staticmethod
    def kill_stray_instances() -> int:
        """Terminate any FlowShield left over from a previous run."""
        killed = 0
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                if (proc.info["name"] or "").lower() == f"{APP_PROCESS_NAME.lower()}.exe":
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if killed:
            time.sleep(1.2)
        return killed

    def launch_app(self, clean_state: bool = True, extra_args: list[str] | None = None) -> int:
        if not Path(APP_EXE).exists():
            raise DesktopControllerError(f"{APP_EXE} not found — build the app first.")

        self.kill_stray_instances()

        args = [str(APP_EXE)]
        if clean_state:
            args.append("--reset")
            # Belt and braces: --reset clears settings at startup, but delete the
            # file too so a crash before that point can't leak state between runs.
            try:
                if SETTINGS_PATH.exists():
                    SETTINGS_PATH.unlink()
            except OSError as exc:
                self._say(f"could not delete settings file: {exc}")

        args.append(f"--server={SERVER_URL}")
        args.append(f"--website={WEBSITE_URL}")
        if extra_args:
            args.extend(extra_args)

        self._say(f"launching {Path(APP_EXE).name} {' '.join(args[1:])}")
        process = subprocess.Popen(args, cwd=str(Path(APP_EXE).parent))
        self.pid = process.pid
        return self.pid

    def connect_window(self, timeout: float = WINDOW_CONNECT_TIMEOUT):
        """Attach to the main window; retries while the app starts up."""
        deadline = time.time() + timeout
        last_error: Exception | None = None

        while time.time() < deadline:
            try:
                if self.pid:
                    self.app = Application(backend="uia").connect(process=self.pid, timeout=2)
                else:
                    self.app = Application(backend="uia").connect(
                        title=APP_WINDOW_TITLE, timeout=2
                    )
                window = self.app.window(title=APP_WINDOW_TITLE, top_level_only=True)
                window.wait("exists visible ready", timeout=5)
                self.window = window
                self._say(f"connected to window (hwnd {window.handle}, pid {self.pid})")
                return window
            except (ElementNotFoundError, PwaTimeoutError, RuntimeError, Exception) as exc:
                last_error = exc
                time.sleep(0.6)

        raise DesktopControllerError(
            f"could not connect to a '{APP_WINDOW_TITLE}' window within {timeout}s "
            f"(last error: {last_error})"
        )

    @property
    def hwnd(self) -> int | None:
        try:
            return self.window.handle if self.window else None
        except Exception:
            return None

    def focus(self, force: bool = False) -> None:
        """
        Bring the window forward. set_focus() costs seconds (it restores, raises
        and waits), so it is skipped when the window is already in front.
        """
        try:
            import ctypes

            if not force and self.hwnd:
                if ctypes.windll.user32.GetForegroundWindow() == self.hwnd:
                    return
            self.window.set_focus()
            time.sleep(0.2)
        except Exception as exc:
            self._say(f"set_focus failed (continuing): {exc}")

    # ------------------------------------------------------- element access

    def element(self, auto_id: str, control_type: str | None = None, timeout: float | None = None):
        """
        Resolve a control by AutomationId.

        This goes through the native UIA FindFirst rather than pywinauto's
        child_window(). child_window walks the descendant tree in Python and
        builds a wrapper per node, which costs ~20s per lookup on this window
        (the Blocked Apps page alone lists a few hundred processes). FindFirst
        does the same search inside the UIA provider and returns in single-digit
        milliseconds. `control_type` is kept for call-site readability but is
        not needed to disambiguate — AutomationIds here are unique.
        """
        timeout = timeout if timeout is not None else UI_ACTION_TIMEOUT
        if self.window is None:
            raise DesktopControllerError("not connected to a window")

        _, uia = _uia()
        condition = _automation_id_condition(auto_id)

        deadline = time.time() + timeout
        while True:
            try:
                found = self.window.element_info.element.FindFirst(
                    uia.TreeScope_Descendants, condition
                )
                if found:
                    return UIAWrapper(UIAElementInfo(found))
            except Exception as exc:                # COM hiccup during a re-render
                if time.time() >= deadline:
                    raise DesktopControllerError(
                        f"UIA lookup for '{auto_id}' failed: {exc}"
                    ) from exc

            if time.time() >= deadline:
                raise DesktopControllerError(
                    f"no element with AutomationId '{auto_id}' appeared within {timeout}s"
                )
            time.sleep(0.15)

    def exists(self, auto_id: str, timeout: float = 1.5) -> bool:
        try:
            self.element(auto_id, timeout=timeout)
            return True
        except Exception:
            return False

    @staticmethod
    def _wait_ready(control, timeout: float = UI_ACTION_TIMEOUT) -> None:
        """Block until a wrapper reports visible and enabled."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if control.is_visible() and control.is_enabled():
                    return
            except Exception:
                pass
            time.sleep(0.15)
        raise DesktopControllerError("control did not become visible and enabled")

    def _is_on_screen(self, control, margin: int = 2) -> bool:
        """
        True only when the control's whole rectangle sits inside the window.

        Containment must be total, not centre-based. A control clipped at the
        bottom edge of a ScrollViewer still reports a centre inside the window,
        but a synthesised click there lands on the clipped sliver and the
        command never fires — silently.
        """
        try:
            rect = control.rectangle()
            window = self.window.rectangle()
            return (rect.left >= window.left + margin
                    and rect.right <= window.right - margin
                    and rect.top >= window.top + margin
                    and rect.bottom <= window.bottom - margin)
        except Exception:
            return False

    def _scroll_into_view(self, control, auto_id: str | None = None, attempts: int = 6):
        """
        Bring a control fully into view the way a user would.

        Tries the ScrollItem pattern first (ListBox items implement it), then
        falls back to the mouse wheel over the window, re-resolving the control
        each time because scrolling moves its rectangle.
        """
        try:
            control.iface_scroll_item.ScrollIntoView()
            time.sleep(0.3)
            if auto_id:
                control = self.element(auto_id, timeout=3)
        except Exception:
            pass  # Not every element implements ScrollItem.

        if self._is_on_screen(control) or auto_id is None:
            return control

        window_rect = self.window.rectangle()
        centre = ((window_rect.left + window_rect.right) // 2,
                  (window_rect.top + window_rect.bottom) // 2)

        for _ in range(attempts):
            rect = control.rectangle()
            direction = "down" if rect.bottom > window_rect.bottom else "up"
            try:
                self.window.scroll(direction, "line", 3)
            except Exception:
                try:
                    import pywinauto.mouse as mouse
                    mouse.scroll(coords=centre, wheel_dist=-3 if direction == "down" else 3)
                except Exception:
                    break
            time.sleep(0.25)

            control = self.element(auto_id, timeout=3)
            if self._is_on_screen(control):
                break

        return control

    def click(self, auto_id: str, control_type: str | None = None) -> None:
        """
        Click a control, scrolling it into view first.

        WPF reports a control inside a scrolled-away part of a ScrollViewer as
        visible and enabled, and its rectangle still resolves — so click_input()
        happily clicks empty desktop and the command never fires. That failure is
        silent, which makes it worth guarding explicitly: scroll first, and if the
        control still isn't within the window, drive the Invoke pattern instead of
        synthesising a mouse click at the wrong place.
        """
        control = self.element(auto_id, control_type)
        self._wait_ready(control)
        control = self._scroll_into_view(control, auto_id)

        if self._is_on_screen(control):
            try:
                control.click_input()
            except Exception:
                control.invoke()
        else:
            self._say(f"'{auto_id}' is outside the viewport — invoking it directly")
            try:
                control.invoke()
            except Exception:
                control.click_input()

        time.sleep(0.35)

    def text_of(self, auto_id: str, timeout: float | None = None) -> str:
        """
        Read a control's text.

        WPF surfaces a TextBlock's content as the element Name; a TextBox
        exposes it through the Value pattern instead, so both are tried.
        """
        control = self.element(auto_id, timeout=timeout)
        try:
            value = control.get_value()          # ValuePattern (TextBox)
            if value:
                return str(value).strip()
        except Exception:
            pass
        try:
            name = control.window_text()
            if name:
                return str(name).strip()
        except Exception:
            pass
        try:
            return " ".join(t.strip() for t in control.texts() if t and t.strip())
        except Exception:
            return ""

    def set_text(self, auto_id: str, value: str) -> None:
        """Clear a text box and type a new value, verifying it landed."""
        control = self.element(auto_id, control_type="Edit")
        self._wait_ready(control)
        control = self._scroll_into_view(control, auto_id)

        try:
            control.set_edit_text("")
            control.set_edit_text(value)
        except Exception:
            control.click_input()
            control.type_keys("^a{BACKSPACE}", pause=0.02)
            control.type_keys(value, with_spaces=True, pause=0.01)

        # Nudge the UI with a harmless keystroke so WPF's CommandManager
        # requeries CanExecute — a ValuePattern SetValue alone does not.
        try:
            control.type_keys("{END}", pause=0.01)
        except Exception:
            pass

        time.sleep(0.25)
        actual = self.text_of(auto_id)
        if actual.replace(" ", "") != value.replace(" ", ""):
            # One retry via keystrokes — set_edit_text can race WPF bindings.
            control.click_input()
            control.type_keys("^a{BACKSPACE}", pause=0.02)
            control.type_keys(value, with_spaces=True, pause=0.01)
            time.sleep(0.3)

    def toggle_state(self, auto_id: str) -> bool:
        control = self.element(auto_id)
        try:
            return bool(control.get_toggle_state())
        except Exception:
            return False

    def is_control_enabled(self, auto_id: str) -> bool:
        """Whether a control accepts input — the direct way to assert a Pro gate."""
        try:
            return bool(self.element(auto_id).is_enabled())
        except Exception:
            return False

    def set_toggle(self, auto_id: str, desired: bool) -> bool:
        """
        Drive a toggle to a state. Returns the state actually reached.

        Checks `is_enabled` before attempting anything. Without that, a
        Pro-gated toggle sitting below the fold would return the unchanged state
        because the click silently missed, and a test asserting "this stayed
        off" would pass for entirely the wrong reason.
        """
        control = self.element(auto_id)
        current = self.toggle_state(auto_id)
        if current == desired:
            return current

        if not control.is_enabled():
            self._say(f"'{auto_id}' is disabled — state stays {current}")
            return current

        control = self._scroll_into_view(control, auto_id)
        if self._is_on_screen(control):
            try:
                control.click_input()
            except Exception:
                control.toggle()
        else:
            self._say(f"'{auto_id}' is outside the viewport — toggling it directly")
            try:
                control.toggle()
            except Exception:
                control.click_input()

        time.sleep(0.45)
        return self.toggle_state(auto_id)

    # ------------------------------------------------------------ navigation

    def navigate_to_tab(self, tab_name: str) -> str:
        key = tab_name.strip().lower()
        auto_id = TAB_IDS.get(key)
        if auto_id is None:
            raise DesktopControllerError(
                f"unknown tab '{tab_name}' (known: {sorted(set(TAB_IDS))})"
            )

        self.focus()
        self.click(auto_id, control_type="Button")
        time.sleep(0.4)

        title = self.text_of("PageTitle")
        self._say(f"navigated to '{title}'")
        return title

    def current_page_title(self) -> str:
        return self.text_of("PageTitle")

    # ------------------------------------------------------------- licensing

    def click_get_pro_button(self) -> None:
        """Prefer the Settings-page button; fall back to the nav-rail one."""
        for auto_id in ("GetProButton", "GetProNavButton", "SleepGetProButton"):
            if self.exists(auto_id, timeout=1.5):
                self._say(f"clicking {auto_id}")
                self.click(auto_id)
                return
        raise DesktopControllerError("no Get Pro button is visible on this page")

    def enter_license_key(self, text: str) -> None:
        self.set_text("LicenseKeyInput", text)

    def enter_license_email(self, text: str) -> None:
        self.set_text("LicenseEmailInput", text)

    def click_activate_pro(self) -> None:
        self.click("ActivateProButton")

    def get_license_status_text(self) -> str:
        return self.text_of("LicenseStatusText")

    def get_license_detail_text(self) -> str:
        return self.text_of("LicenseDetailText")

    def wait_for_license_status(self, needle: str, timeout: float = 30.0) -> str:
        """Poll the status line until it contains `needle` (case-insensitive)."""
        deadline = time.time() + timeout
        seen = ""
        while time.time() < deadline:
            seen = self.get_license_status_text()
            if needle.lower() in seen.lower():
                return seen
            time.sleep(0.6)
        raise DesktopControllerError(
            f"license status never contained '{needle}' within {timeout}s (last: '{seen}')"
        )

    def is_pro(self) -> bool:
        return "pro active" in self.get_license_status_text().lower()

    def tier_badge(self) -> str:
        return self.text_of("TierBadge")

    # ---------------------------------------------------------- blocked apps

    def add_blocked_app(self, process_name: str) -> bool:
        """
        Type a process name and press Add.

        Returns False when the Add button is disabled — which is the correct app
        behaviour at the Free tier's three-app limit, not a driver failure, so it
        must not raise.
        """
        self.set_text("NewAppNameInput", process_name)

        button = self.element("AddAppButton")
        try:
            self._wait_ready(button, timeout=2.5)
        except DesktopControllerError:
            self._say(f"Add is disabled — '{process_name}' not added (limit or empty field)")
            return False

        self.click("AddAppButton")
        time.sleep(0.5)
        return True

    def blocked_app_names(self) -> list[str]:
        """Item names from the blocked-apps ListBox."""
        try:
            listbox = self.element("BlockedAppsList")
            names = []
            for item in listbox.children():
                text = " ".join(t for t in item.texts() if t)
                if text.strip():
                    names.append(text.strip())
            return names
        except Exception as exc:
            self._say(f"could not read blocked apps list: {exc}")
            return []

    def blocked_apps_status(self) -> str:
        return self.text_of("BlockedAppsStatusText")

    def remove_blocked_app(self, process_name: str) -> None:
        self.click(f"RemoveApp_{process_name}")

    # --------------------------------------------------------- sleep blocking

    def set_sleep_window(self, start: str, end: str) -> None:
        self.set_text("SleepStartInput", start)
        self.set_text("SleepEndInput", end)
        self.click("SaveSleepWindowButton")
        time.sleep(0.4)

    def sleep_status(self) -> str:
        return self.text_of("SleepStatusText")

    def sleep_window_text(self) -> str:
        return self.text_of("SleepWindowText")

    # ------------------------------------------------------------- sprints

    def start_sprint(self) -> None:
        self.click("StartSprintButton")

    def stop_sprint(self) -> None:
        self.click("StopSprintButton")

    def sprint_timer(self) -> str:
        return self.text_of("SprintTimerText")

    def session_state(self) -> str:
        return self.text_of("SessionStateText")

    def select_shield(self, level: str) -> None:
        self.click(f"Shield_{level.capitalize()}")

    def select_sprint_length(self, minutes: int) -> None:
        self.click(f"SprintLength_{minutes}")

    # ---------------------------------------------------------------- toast

    def toast_text(self, timeout: float = 4.0) -> str:
        """
        Read the transient toast if one is showing, else "".

        The toast auto-hides after four seconds, so it can disappear between
        the existence check and the read. That race is expected, not an error —
        never raise from here.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                text = self.text_of("ToastText", timeout=0.4)
                if text:
                    return text
            except Exception:
                pass
            time.sleep(0.25)
        return ""

    # ------------------------------------------------------------ app log

    @staticmethod
    def app_log_path() -> Path | None:
        """Newest FlowShield diagnostic log, or None."""
        import os

        log_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "FlowShield" / "logs"
        if not log_dir.is_dir():
            return None
        logs = sorted(log_dir.glob("flowshield-*.log"), key=lambda p: p.stat().st_mtime)
        return logs[-1] if logs else None

    def app_log_contains(self, needle: str, within_lines: int = 200) -> bool:
        """Assert on something the app recorded but does not surface in the UI."""
        path = self.app_log_path()
        if path is None:
            return False
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return False
        return any(needle.lower() in line.lower() for line in lines[-within_lines:])

    # -------------------------------------------------------------- dialogs

    def dismiss_dialog(self, timeout: float = 5.0) -> str | None:
        """
        Close any modal window the app raised (e.g. the crash MessageBox).
        Returns the dialog's text if one was found, else None.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                for win in Desktop(backend="uia").windows():
                    try:
                        if win.handle == self.hwnd:
                            continue
                        if win.element_info.control_type != "Window":
                            continue
                        if (win.process_id() if callable(getattr(win, "process_id", None))
                                else None) != self.pid:
                            continue

                        body = " ".join(t for t in win.texts() if t)
                        for label in ("OK", "Close", "Yes", "Cancel"):
                            try:
                                button = win.child_window(title=label, control_type="Button")
                                if button.exists(timeout=0.4):
                                    button.click_input()
                                    self._say(f"dismissed dialog: {body[:120]}")
                                    return body
                            except Exception:
                                continue
                    except Exception:
                        continue
            except Exception:
                pass
            time.sleep(0.4)
        return None

    # --------------------------------------------------------------- teardown

    def close_app(self, force: bool = True) -> None:
        """
        Terminate the app. Closing the window would only hide it to the tray
        (that is the shipped default), so the process is killed outright.
        """
        if self.pid:
            try:
                proc = psutil.Process(self.pid)
                proc.terminate()
                try:
                    proc.wait(timeout=6)
                except psutil.TimeoutExpired:
                    if force:
                        proc.kill()
                self._say(f"closed FlowShield (pid {self.pid})")
            except psutil.NoSuchProcess:
                pass
            except Exception as exc:
                self._say(f"close_app: {exc}")

        self.kill_stray_instances()
        self.window = None
        self.app = None
        self.pid = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close_app()
        return False
