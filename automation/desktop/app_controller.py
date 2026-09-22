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
from pywinauto.findwindows import ElementNotFoundError, find_elements
from pywinauto.timings import TimeoutError as PwaTimeoutError
from pywinauto.uia_defines import IUIA
from pywinauto.uia_element_info import UIAElementInfo

from config import (
    APP_EXE,
    APP_PROCESS_NAME,
    APP_WINDOW_TITLE,  # noqa: F401  (kept for callers; matching uses WINDOW_TITLE_RE)
    DESKTOP_DIR,
    SERVER_URL,
    SETTINGS_PATH,
    UI_ACTION_TIMEOUT,
    WEBSITE_URL,
    WINDOW_CONNECT_TIMEOUT,
)

# A running sprint puts the countdown in the title ("FlowShield — 14:32", F19),
# so windows are matched on the prefix rather than the exact title.
WINDOW_TITLE_RE = rf"^{APP_WINDOW_TITLE}( .*)?$"

TAB_IDS = {
    "today": "Tab_Today",
    "history": "Tab_History",
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

    def launch_app(
        self,
        clean_state: bool = True,
        extra_args: list[str] | None = None,
        use_defaults: bool = False,
        show_first_run: bool = False,
        dev_fields: bool = True,
    ) -> int:
        """
        Start the app.

        `use_defaults=True` omits the --server/--website overrides so the binary
        runs exactly as a downloaded copy would, against whatever endpoints it
        was built with. Without it every launch is pinned to localhost, which
        makes it impossible to test the shipped configuration.

        `dev_fields=True` passes --dev so Settings shows the developer-only
        controls (the licence-server URL box, the settings path) that several
        tests read or type into. Customers never see them (roadmap 1.15); pass
        False to check that.
        """
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

        if not use_defaults:
            args.append(f"--server={SERVER_URL}")
            args.append(f"--website={WEBSITE_URL}")
            # Shrinks the end-sprint grace period and countdowns (F2) to seconds.
            args.append("--short-timers")
        if not show_first_run:
            # A clean install opens the terms gate and then the first-run
            # welcome (F18) over every page.
            args.append("--skip-first-run")
            args.append("--accept-terms")
        if dev_fields:
            args.append("--dev")
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
                        title_re=WINDOW_TITLE_RE, timeout=2
                    )
                window = self.app.window(title_re=WINDOW_TITLE_RE, top_level_only=True)
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

    def main_window_is_visible(self) -> bool:
        """Whether this process currently exposes a visible main window."""
        if not self.pid:
            return False
        try:
            for window in Desktop(backend="uia").windows(
                title_re=WINDOW_TITLE_RE, visible_only=True
            ):
                try:
                    if window.process_id() == self.pid:
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    @staticmethod
    def _explorer_pids() -> set[int]:
        pids = set()
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                if (proc.info["name"] or "").lower() == "explorer.exe":
                    pids.add(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return pids

    def accept_terms_if_shown(self, timeout: float = 4.0) -> bool:
        """Clear the terms gate when a launch shows it. Returns True if it was there."""
        if not self.exists("AcceptTermsButton", timeout=timeout):
            return False
        self.click("AcceptTermsButton")
        time.sleep(0.6)
        return True

    def find_tray_icon(self, timeout: float = UI_ACTION_TIMEOUT):
        """Return FlowShield's real Windows notification-area button."""
        deadline = time.time() + timeout
        opened_overflow = False
        while time.time() < deadline:
            try:
                elements = find_elements(
                    title_re=r"^FlowShield(?:$|\s)",
                    control_type="Button",
                    backend="uia",
                    top_level_only=False,
                )
                # The notification icon belongs to Explorer. Any other app can
                # show a button whose name starts with "FlowShield" (a browser
                # tab, an editor, a chat title), so only Explorer's count.
                explorer = self._explorer_pids()
                for element in elements:
                    if element.process_id in explorer:
                        return UIAWrapper(element)

                # Windows 11 keeps less-frequently-used icons in a XAML
                # overflow panel. Its buttons are absent from the automation
                # tree until the panel is opened, so reveal it once and retry.
                #
                # Matched by prefix, not by exact title (#246): on Windows 11
                # the chevron's accessible name carries its current state, so
                # this machine's is "Show Hidden Icons Hide". The exact-title
                # lookup found nothing, the overflow was never opened, and an
                # icon Windows had decided to hide was invisible to the suite —
                # which is why the failure came and went with nothing changing.
                if not opened_overflow:
                    hidden_icons = find_elements(
                        title_re=r"^Show Hidden Icons",
                        control_type="Button",
                        backend="uia",
                        top_level_only=False,
                    )
                    if hidden_icons:
                        UIAWrapper(hidden_icons[0]).click_input()
                        opened_overflow = True
            except Exception:
                pass
            time.sleep(0.35)
        return None

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
        True only when a click at the control's centre would actually hit it.

        Containment must be total, not centre-based. A control clipped at the
        bottom edge of a ScrollViewer still reports a centre inside the window,
        but a synthesised click there lands on the clipped sliver and the
        command never fires — silently.

        Containment alone is not enough either. WPF reports a control's
        *layout* rectangle, which stays put when a ScrollViewer clips the
        control away: the Settings page's "Show the welcome again" button
        reported (217,701)-(378,730) inside a window ending at 740, while
        from_point on its centre returned the main window. The click landed on
        the window, the command never ran, and the failure surfaced three
        assertions later. So finish with a hit test — the thing under the
        centre point must be the control itself or part of it.
        """
        try:
            if not self._is_contained(control, margin):
                return False
            rect = control.rectangle()
            return self._hit_tests_to(control, (rect.left + rect.right) // 2,
                                      (rect.top + rect.bottom) // 2)
        except Exception:
            return False

    def _is_contained(self, control, margin: int = 2) -> bool:
        """
        Whether the control's whole rectangle sits inside the window.

        Scrolling is steered by this rather than by _is_on_screen: the scroll
        loop picks its direction from where the rectangle is relative to the
        window, so a control that is contained but clipped has no direction
        that helps, and asking it to keep scrolling walks the page the wrong
        way. Clipping is click()'s problem to solve, by invoking instead.
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

    def _hit_tests_to(self, control, x: int, y: int, levels: int = 4) -> bool:
        """
        Whether the element at (x, y) is `control`, or something inside it.

        A Button's centre often resolves to its own TextBlock, so walk a few
        parents up before giving up. When the hit test itself cannot run, say
        yes: the containment check has already passed, and refusing every click
        because an unrelated UIA call failed would be worse than the bug.
        """
        try:
            from pywinauto import Desktop

            target = control.element_info.runtime_id
            hit = Desktop(backend="uia").from_point(x, y)
        except Exception:
            return True

        for _ in range(levels):
            if hit is None:
                return False
            try:
                if hit.element_info.runtime_id == target:
                    return True
                hit = hit.parent()
            except Exception:
                return False
        return False

    def _scroll_into_view(self, control, auto_id: str | None = None, attempts: int = 24):
        """
        Bring a control fully into view the way a user would.

        Tries the ScrollItem pattern first (ListBox items implement it), then
        falls back to the mouse wheel over the window, re-resolving the control
        each time because scrolling moves its rectangle.

        The attempt budget is generous on purpose: at three lines a turn, six
        turns only moved 18 lines, which stopped reaching the foot of the
        Settings page as cards were added to it. Running out of attempts is
        silent — click() then clicks where the control would have been — so the
        cost of too few is a confusing failure somewhere else entirely, while
        the cost of too many is a few hundred milliseconds on a control that is
        already visible (the loop exits as soon as it is).
        """
        try:
            control.iface_scroll_item.ScrollIntoView()
            time.sleep(0.3)
            if auto_id:
                control = self.element(auto_id, timeout=3)
        except Exception:
            pass  # Not every element implements ScrollItem.

        if self._is_contained(control) or auto_id is None:
            return control

        window_rect = self.window.rectangle()
        centre = ((window_rect.left + window_rect.right) // 2,
                  (window_rect.top + window_rect.bottom) // 2)

        for _ in range(attempts):
            rect = control.rectangle()
            direction = "down" if rect.bottom > window_rect.bottom else "up"

            # Close the distance in pages while the control is far away, then
            # line by line, so a long page doesn't need dozens of turns but a
            # nearly-visible control doesn't overshoot past it.
            gap = (rect.top - window_rect.bottom if direction == "down"
                   else window_rect.top - rect.bottom)
            amount = "page" if gap > window_rect.height() else "line"

            try:
                self.window.scroll(direction, amount, 1 if amount == "page" else 3)
            except Exception:
                try:
                    import pywinauto.mouse as mouse
                    mouse.scroll(coords=centre, wheel_dist=-3 if direction == "down" else 3)
                except Exception:
                    break
            time.sleep(0.25)

            control = self.element(auto_id, timeout=3)
            if self._is_contained(control):
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

    def choose(self, auto_id: str) -> None:
        """
        Pick a radio button.

        click() cannot do this safely. A RadioButton exposes SelectionItem, not
        Invoke, so click()'s off-screen fallback (invoke, then click_input) has
        no working first branch: invoke raises, and the synthesised click lands
        wherever the control would be if the page were scrolled there. That is
        silent — the test then asserts against a setting nothing ever changed.
        Selecting through the pattern works regardless of scroll position.
        """
        control = self.element(auto_id)
        self._wait_ready(control)
        control = self._scroll_into_view(control, auto_id)
        try:
            control.iface_selection_item.Select()
        except Exception:
            control.click_input()
        time.sleep(0.35)

    def is_selected(self, auto_id: str) -> bool:
        """Whether a radio button is the chosen one. Radios have no toggle state."""
        try:
            return bool(self.element(auto_id).is_selected())
        except Exception:
            return False

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
        reached = self.toggle_state(auto_id)
        if reached != desired:
            # A click can land while the page is still settling after the scroll,
            # or on a row whose label doesn't reach the pointer. The toggle
            # pattern is the same action without the aim.
            self._say(f"'{auto_id}' didn't move on click — using the toggle pattern")
            try:
                self.element(auto_id).toggle()
                time.sleep(0.45)
                reached = self.toggle_state(auto_id)
            except Exception as exc:
                self._say(f"'{auto_id}' toggle pattern failed: {exc}")
        return reached

    # ------------------------------------------------------------ navigation

    def navigate_to_tab(self, tab_name: str, attempts: int = 3) -> str:
        """
        Switch tabs, confirming the page actually changed.

        A single click is an attempt, not an outcome: it can land while the
        window is still taking focus, or mid re-render, and be swallowed. That
        showed up as a rare "expected Sleep Blocking, got Today" failure with no
        other symptom. Verify the page title and press again if it didn't move.
        """
        key = tab_name.strip().lower()
        auto_id = TAB_IDS.get(key)
        if auto_id is None:
            raise DesktopControllerError(
                f"unknown tab '{tab_name}' (known: {sorted(set(TAB_IDS))})"
            )

        expected = tab_name.strip()
        title = ""

        for attempt in range(1, attempts + 1):
            self.focus()
            self.click(auto_id, control_type="Button")

            # The title is bound, so it updates a frame or two after the click.
            deadline = time.time() + 3.0
            while time.time() < deadline:
                title = self.text_of("PageTitle")
                if title.strip().lower() == expected.lower():
                    self._say(f"navigated to '{title}'")
                    return title
                time.sleep(0.2)

            if attempt < attempts:
                self._say(f"tab click did not take (still on '{title}'); retrying")
                time.sleep(0.5)

        raise DesktopControllerError(
            f"could not navigate to '{expected}' after {attempts} attempts "
            f"(page title is '{title}')"
        )

    def current_page_title(self) -> str:
        return self.text_of("PageTitle")

    # ------------------------------------------------------------- licensing

    def click_get_pro_button(self) -> None:
        """Prefer the Settings-page button; fall back to the nav rail and lock screen."""
        for auto_id in ("GetProButton", "GetProNavButton", "LockBuyButton", "SleepGetProButton"):
            if self.exists(auto_id, timeout=1.5):
                self._say(f"clicking {auto_id}")
                self.click(auto_id)
                return
        raise DesktopControllerError("no Buy FlowShield button is visible on this page")

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
        return "licence active" in self.get_license_status_text().lower()

    def tier_badge(self) -> str:
        return self.text_of("TierBadge")

    # ---------------------------------------------------------- blocked apps

    def add_blocked_app(self, process_name: str) -> bool:
        """
        Type a process name and press Add.

        Returns False when the Add button is disabled — which is the correct app
        behaviour for an empty name or a locked app, not a driver failure, so it
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

    # ------------------------------------------------- blocklist profiles (F9)

    def select_profile(self, name: str) -> None:
        """Switch the active blocklist profile from the Blocked Apps switcher."""
        self.click(f"Profile_{name}")
        time.sleep(0.4)

    def select_profile_on_today(self, name: str) -> None:
        """The same switch, from Today's chips before a sprint starts."""
        self.click(f"TodayProfile_{name}")
        time.sleep(0.4)

    def new_profile(self, name: str) -> None:
        """
        Add a profile that starts as a copy of the list on screen, which is what
        New profile does — a profile is a named blocklist, not an empty page.
        """
        self.set_text("ProfileNameInput", name)
        self.click("NewProfileButton")
        time.sleep(0.5)

    def rename_profile(self, name: str) -> None:
        self.set_text("ProfileNameInput", name)
        self.click("RenameProfileButton")
        time.sleep(0.5)

    def duplicate_profile(self) -> None:
        self.click("DuplicateProfileButton")
        time.sleep(0.5)

    def delete_profile(self, confirm: bool = True) -> None:
        self.click("DeleteProfileButton")
        if not confirm:
            return
        if self.exists("ConfirmDeleteProfileButton", timeout=2.0):
            self.click("ConfirmDeleteProfileButton")
            time.sleep(0.5)

    def today_profile_caption(self) -> str:
        return self.text_of("TodayProfileCaption")

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

    def start_sprint(self, confirm_open_apps: bool = True) -> None:
        """
        Get a sprint running.

        Since F7, pressing Start with a blocked app already open asks about it
        first rather than starting — so "click Start" and "a sprint is running"
        stopped being the same thing. Every test that just wants a sprint gets
        the question answered for it with "Start anyway", which is what those
        tests meant before the panel existed.

        Tests *about* the panel pass confirm_open_apps=False and drive the
        buttons themselves; answering it automatically would hide the very
        thing they are checking.
        """
        self.click("StartSprintButton")
        if not confirm_open_apps:
            return
        self.answer_open_apps_question()

    def answer_open_apps_question(self, timeout: float = 2.0) -> bool:
        """
        Answer F7's "blocked apps are open" question with "Start anyway", if it
        was asked. Returns True when it was.

        Split out of start_sprint because the Start button is not the only thing
        that starts a sprint: the first-run wizard's own "Start my first sprint"
        goes through the same TodayViewModel.StartSprint and therefore through
        the same question (#244 — the wizard pre-ticks the suggested apps found
        on this PC, so on a machine running any of them the panel always comes
        up and nothing starts until it is answered).

        Raced against the sprint actually starting, rather than waited out. A
        flat two-second probe spends most of the --short-timers cancel grace
        before the test can do anything, which broke every test that starts a
        sprint and then cancels it inside the grace period.

        Probed on the buttons, not the panel: the panel is a Border, which UI
        Automation does not surface at all. StopSprintButton appears only once a
        sprint is running, so it is the "no question was asked" signal.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.exists("StartAnywayButton", timeout=0.2):
                self._say("blocked apps were already open — answering with 'Start anyway'")
                self.click("StartAnywayButton")
                self.element("StopSprintButton", timeout=5)
                return True
            if self.exists("StopSprintButton", timeout=0.2):
                return False
        return False

    # Matches EndSprintPolicy with --short-timers: grace 15 s, Firm 6 s, Sealed 8 s.
    # Was 3.0 with a comment naming the pre-#222 values; tier 5 now checks this
    # against EndSprintPolicy.cs so the constant cannot drift again.
    SHORT_GRACE_SECONDS = 15.0

    def wait_until_control_enabled(self, auto_id: str, timeout: float = 20.0) -> float:
        """
        Block until a control reports enabled, and return how long that took.

        The direct way to assert a timed gate. Reading IsEnabled once and
        assuming the read lands inside the window does not work: a UIA round
        trip on a busy page costs a second or more, so a two-second countdown
        can elapse entirely between the click that opens a panel and the first
        read of its button (#242). Timing how long the control stays disabled
        tests the same rule without racing it.
        """
        started = time.time()
        deadline = started + timeout
        while time.time() < deadline:
            if self.is_control_enabled(auto_id):
                return time.time() - started
            time.sleep(0.2)
        raise DesktopControllerError(
            f"'{auto_id}' was still disabled after {timeout}s"
        )

    def end_button_label(self) -> str:
        try:
            return self.element("StopSprintButton", timeout=2).window_text()
        except Exception:                                  # noqa: BLE001
            return ""

    def cancel_sprint(self) -> None:
        """
        End a sprint inside its grace period: no penalty, nothing recorded.

        One element lookup, reused for both the label check and the click.
        Resolving it twice (#241) spent a second or more of the grace period
        between reading "Cancel sprint" and landing the click, so the click
        could arrive after the window shut: RequestEnd then took the Confirm
        branch, the sprint carried on, and the test saw an intention that was
        never cleared rather than the timing problem underneath.
        """
        control = self.element("StopSprintButton")
        label = (control.window_text() or "").lower()
        if "cancel" not in label:
            raise DesktopControllerError(f"the sprint is past its grace period (button reads {label!r})")
        self._wait_ready(control)
        try:
            control.click_input()
        except Exception:                                  # noqa: BLE001
            control.invoke()

    # How long wait_out_grace_period will wait, derived from the grace period
    # rather than written out beside it. A hardcoded 15.0 here would have been
    # exactly SHORT_GRACE_SECONDS, so a call made near the start of a sprint
    # could hit its own deadline before the button ever flipped and return as
    # if the grace were over — quietly, to 24 call sites. The margin has to
    # cover a label read landing just before the boundary (one to two seconds)
    # plus the poll interval; tier 5 fails if it is ever <= the grace.
    GRACE_WAIT_MARGIN_SECONDS = 5.0
    GRACE_WAIT_TIMEOUT = SHORT_GRACE_SECONDS + GRACE_WAIT_MARGIN_SECONDS

    def wait_out_grace_period(self, timeout: float | None = None) -> None:
        """
        Block until the end button stops offering a free cancel.

        Returning on the deadline rather than on the flip is not an error here —
        several callers use this simply to be past the grace — but it must not
        be able to happen *before* the grace could plausibly have ended, or the
        test that follows acts on a sprint that is still cancellable.
        """
        deadline = time.time() + (self.GRACE_WAIT_TIMEOUT if timeout is None else timeout)
        while time.time() < deadline and "cancel" in self.end_button_label().lower():
            time.sleep(0.4)

    def stop_sprint(self, *, phrase: str = "end my sprint") -> None:
        """
        End a running sprint early, going through whatever its shield requires
        (F2): wait out the grace period so it is recorded, then confirm Firm's
        countdown or type Sealed's phrase.
        """
        self.wait_out_grace_period()
        self.click("StopSprintButton")
        # The panel is a Border, invisible to UI Automation; its button isn't.
        if not self.exists("KeepGoingButton", timeout=1.5):
            return                                            # Soft ended straight away
        if self.exists("EndPhraseInput", timeout=0.8):
            self.set_text("EndPhraseInput", phrase)
        deadline = time.time() + 15
        while time.time() < deadline and not self.is_control_enabled("EndAnywayButton"):
            time.sleep(0.4)
        self.click("EndAnywayButton")

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

        log_dir = Path(os.environ.get("APPDATA", "")) / "FlowShield" / "logs"
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

    @staticmethod
    def _as_keystrokes(text: str) -> str:
        """Escape a literal string for type_keys, which reads +^%~(){} as syntax."""
        return "".join("{" + ch + "}" if ch in "+^%~(){}[]" else ch for ch in text)

    def save_dialog_to(self, path: str, timeout: float = 20.0) -> bool:
        """
        Drive the native Save As dialog to a path and confirm it.

        The export writes only where the customer chose, so there is no way to
        check the file's contents without going through the real dialog — and
        "tests check the files' contents" is the requirement (roadmap 3.5).

        Four things make this harder than it looks, each of which cost a
        separate debugging round (#117):

        1. WPF's SaveFileDialog is owned by the main window and UI Automation
           reports it as a *child* of it, not as a top-level window, so
           enumerating the desktop the way dismiss_dialog does never finds it.
        2. The file-name box is not the first Edit. The dialog also has the
           address bar, a search box and four column headers. A path typed into
           the address bar produces a Save that succeeds — writing the *default*
           name to the *default* folder — so the test then looks for a file
           nobody created. The Win32 common-dialog ids are stable: 1001 is the
           file-name box, 1 is Save, 2 is Cancel.
        3. The "Save As" lookup matches two elements and pywinauto raises rather
           than choosing, so found_index=0 settles it.
        4. **set_edit_text does not work here, and fails silently.** It puts the
           text in the Edit — reading control 1001 back afterwards returns the
           path — but the shell dialog keeps its own notion of the current file
           name, updated from input notifications the direct write never sends.
           Save then acts on the unchanged internal name and the dialog just
           sits there. Real keystrokes are what the dialog listens to, which is
           also what the customer does. Enter in the file-name box is Save.

        Deliberately not wrapped in one try/except: an earlier version reported
        "no Save dialog appeared" no matter which of these steps threw, which
        hid every one of them.
        """
        dialog = self.window.child_window(
            title="Save As", control_type="Window", found_index=0)
        if not dialog.exists(timeout=timeout):
            self._say("no Save dialog appeared")
            return False

        edit = dialog.child_window(auto_id="1001", control_type="Edit", found_index=0)
        edit.wait("ready", timeout=10)

        edit.click_input()
        edit.type_keys("^a{BACKSPACE}", pause=0.05)
        edit.type_keys(self._as_keystrokes(path), with_spaces=True, pause=0.01)
        time.sleep(0.4)

        # Read it back before committing. The dialog ignoring the name is the
        # failure this helper exists to avoid, and it is invisible otherwise.
        typed = ""
        try:
            typed = edit.legacy_properties().get("Value") or ""
        except Exception as exc:
            self._say(f"could not read the file-name box back: {exc}")
        if typed and typed != path:
            self._say(f"the file-name box holds {typed!r}, not {path!r}")
            return False

        edit.type_keys("{ENTER}")

        # The dialog closing is what says the name was accepted.
        for _ in range(40):
            if not dialog.exists(timeout=0.3):
                self._say(f"saved through the dialog to {path}")
                return True
            time.sleep(0.25)

        self._say("the Save dialog stayed open — the name was rejected")
        return False

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
