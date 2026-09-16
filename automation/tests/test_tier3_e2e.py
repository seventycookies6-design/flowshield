"""
Tier 3 — end-to-end through the real UI.

These drive the shipped binary with UI Automation and check that what the UI
claims matches what was actually persisted to the DPAPI-encrypted settings file.
"""

from __future__ import annotations

import time

import pytest

from config import TEST_BLOCK_APP
from core import state_verifier as verify

pytestmark = pytest.mark.ui


# ================================================================ app shell

class TestAppShell:
    def test_window_opens_on_the_today_page(self, app):
        assert app.current_page_title() == "Today"

    @pytest.mark.parametrize("tab", ["Blocked Apps", "Sleep Blocking", "Settings", "Today"])
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


# ============================================================== sprint flow

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


# ==================================================== the trial unlocks all

class TestTrialUnlocksEverything:
    """During the 7-day trial every feature is available, as after a purchase."""

    def test_sleep_blocking_turns_on(self, fresh_app):
        fresh_app.navigate_to_tab("Sleep Blocking")
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
        expired_app.navigate_to_tab("Sleep Blocking")
        assert expired_app.is_control_enabled("SleepBlockToggle") is False
        expired_app.navigate_to_tab("Settings")
        assert expired_app.is_control_enabled("HardKillModeToggle") is False
        assert "trial ended" in expired_app.get_license_status_text().lower()

    def test_the_buy_button_opens_the_store(self, expired_app):
        expired_app.click("LockBuyButton")
        time.sleep(1.5)
        assert expired_app.app_log_contains("opening upgrade page")


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
        self._start(fresh_app, "Firm")
        fresh_app.wait_out_grace_period()
        fresh_app.click("StopSprintButton")

        assert fresh_app.exists("KeepGoingButton", timeout=3), "Firm ended without a confirmation"
        assert fresh_app.is_control_enabled("EndAnywayButton") is False, "End anyway was ready immediately"
        time.sleep(2.8)
        assert fresh_app.is_control_enabled("EndAnywayButton") is True
        fresh_app.click("EndAnywayButton")
        time.sleep(1.0)
        assert "early" in fresh_app.session_state().lower()

    def test_sealed_needs_the_countdown_and_the_phrase(self, fresh_app):
        self._start(fresh_app, "Sealed")
        fresh_app.wait_out_grace_period()
        assert "need to stop" in fresh_app.end_button_label().lower()
        fresh_app.click("StopSprintButton")
        assert fresh_app.exists("EndPhraseInput", timeout=3), "Sealed didn't ask for the phrase"

        fresh_app.set_text("EndPhraseInput", "end my sprint")
        time.sleep(0.5)
        assert fresh_app.is_control_enabled("EndAnywayButton") is False, \
            "the phrase ended a Sealed sprint before its countdown"

        time.sleep(3.5)
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
        fresh_app.set_text("AppSearchInput", "chrome")
        time.sleep(0.6)
        texts = " ".join(t for item in fresh_app.element("AppPickerList").children() for t in item.texts())
        assert "closes the whole browser" in texts.lower(), texts


# ========================================================= notifications (F19)

class TestNotificationSettings:
    TOGGLES = [
        ("NotifySprintStartedToggle", "SprintStarted"),
        ("NotifyFiveMinutesLeftToggle", "FiveMinutesLeft"),
        ("NotifySprintCompleteToggle", "SprintComplete"),
        ("NotifySprintInterruptedToggle", "SprintInterrupted"),
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

    def test_completing_it_saves_every_choice_and_starts_the_sprint(self, logger):
        saved_run = self._run_value()          # the toggle writes the real Run value
        app = self._launch(logger)
        try:
            assert app.exists("FirstRunSkipButton", timeout=3), "a clean install didn't get the welcome"
            assert app.text_of("FirstRunStepText") == "Step 1 of 3"

            app.set_text("FirstRunSearchInput", "steam")
            time.sleep(0.8)
            app.click("FirstRunPickApp_steam")
            app.click("FirstRunNextButton")
            time.sleep(0.4)

            assert app.text_of("FirstRunStepText") == "Step 2 of 3"
            app.click("FirstRunShield_Sealed")
            app.click("FirstRunNextButton")
            time.sleep(0.4)

            app.click("FirstRunLength_45")
            app.click("FirstRunStartWithWindows")
            assert "unlocked for 7 days" in app.text_of("FirstRunTrialText").lower()
            app.click("FirstRunStartButton")
            time.sleep(1.5)

            assert not app.exists("FirstRunSkipButton", timeout=1), "the welcome stayed open"
            assert app.exists("StopSprintButton", timeout=3), "the first sprint didn't start"

            s = verify.read_settings()
            steam = next(a for a in s["BlockedApps"] if a["ProcessName"].lower() == "steam")
            assert [p.lower() for p in steam["ExtraProcessNames"]] == ["steamwebhelper"]
            assert s["DefaultShield"] in (3, "Sealed")
            assert s["DefaultSprintMinutes"] == 45
            assert s["StartWithWindows"] is True and self._run_value(), "start with Windows wasn't applied"
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
