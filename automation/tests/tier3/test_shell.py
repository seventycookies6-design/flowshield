# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 3: shell."""

from __future__ import annotations
import time
import pytest
from core.installed_apps import STEAM_INSTALLED
from core import state_verifier as verify
from ._helpers import current_terms_version, flowshield_pids, launch_again

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


class TestTermsGate:
    """A clean install must agree to the terms before Basalt can do anything."""

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
        assert title.startswith("Basalt —"), title
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


class TestOneInstance:
    def test_opening_it_again_brings_back_the_running_copy(self, fresh_app):
        import win32gui

        hwnd = fresh_app.window.handle             # UIA can't find a hidden window later
        fresh_app.window.close()                   # minimise-to-tray is on by default
        time.sleep(1.0)
        assert not win32gui.IsWindowVisible(hwnd), "closing didn't hide to the tray"

        launch_again()
        time.sleep(1.5)

        assert flowshield_pids() == [fresh_app.pid], "a second Basalt kept running"
        assert win32gui.IsWindowVisible(hwnd), "the running copy wasn't brought back"
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

    #: 0-255. The dark theme's bg is #141517 and its surfaces barely lighter;
    #: the light theme's bg is #ECEBE7. Nothing legitimate lands between these.
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
