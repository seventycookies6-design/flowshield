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

    def test_a_clean_install_is_on_the_free_tier(self, app):
        app.navigate_to_tab("Settings")
        assert "free" in app.get_license_status_text().lower()
        assert app.tier_badge().upper() == "FREE"

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

    def test_free_tier_stops_at_three_apps(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        for index in range(5):
            fresh_app.add_blocked_app(f"limit-probe-{index}")
            time.sleep(0.5)

        names = fresh_app.blocked_app_names()
        assert len(names) == 3, f"Free tier allowed {len(names)} apps: {names}"
        assert "upgrade" in fresh_app.blocked_apps_status().lower()

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


# ============================================================ free-tier gates

class TestFreeTierGating:
    def test_sleep_blocking_will_not_turn_on(self, fresh_app):
        fresh_app.navigate_to_tab("Sleep Blocking")

        # Assert the gate directly as well as its effect: a toggle that merely
        # failed to receive the click would also "stay off".
        assert fresh_app.is_control_enabled("SleepBlockToggle") is False, \
            "the sleep-blocking toggle is interactive on the Free tier"

        reached = fresh_app.set_toggle("SleepBlockToggle", True)
        assert reached is False, "sleep blocking unlocked without Pro"

        result = verify.verify_sleep_window(enabled=False)
        assert result.ok, result.detail

    def test_shield_three_snaps_back_to_firm(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Sealed")
        time.sleep(0.8)
        description = fresh_app.text_of("ShieldDescriptionText")
        assert "locks" not in description.lower(), \
            f"Free tier reached Shield III (description: {description!r})"

    def test_hard_kill_mode_is_disabled(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")

        assert fresh_app.is_control_enabled("HardKillModeToggle") is False, \
            "hard kill mode is interactive on the Free tier"

        reached = fresh_app.set_toggle("HardKillModeToggle", True)
        assert reached is False, "hard kill mode unlocked without Pro"

        settings = verify.read_settings()
        assert settings["HardKillModeEnabled"] is False


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
        status = fresh_app.wait_for_license_status("Pro Active", timeout=45)
        assert "pro active" in status.lower()

        ui = verify.verify_ui_pro_status(fresh_app, expected_pro=True)
        assert ui.ok, ui.detail

        disk = verify.verify_dpapi_settings(expected_pro=True)
        assert disk.ok, disk.detail
        assert disk.data["LicenseKey"] == payload["licenseKey"]


@pytest.mark.stripe
@pytest.mark.e2e
class TestProFeaturesAfterActivation:
    """Pro-gated surfaces must open up once a licence is active."""

    def test_pro_unlocks_sleep_blocking_and_shield_three(self, fresh_app, server,
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

        fresh_app.navigate_to_tab("Settings")
        fresh_app.enter_license_key(created["licenseKey"])
        fresh_app.click_activate_pro()
        fresh_app.wait_for_license_status("Pro Active", timeout=45)

        # Sleep blocking now opens.
        fresh_app.navigate_to_tab("Sleep Blocking")
        assert fresh_app.set_toggle("SleepBlockToggle", True) is True
        fresh_app.set_sleep_window("23:15", "06:45")
        time.sleep(0.8)
        saved = verify.verify_sleep_window(enabled=True, start="23:15", end="06:45")
        assert saved.ok, saved.detail

        # Shield III sticks.
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Sealed")
        time.sleep(0.6)
        assert "locks" in fresh_app.text_of("ShieldDescriptionText").lower()

        # And the blocked-app limit is gone.
        fresh_app.navigate_to_tab("Blocked Apps")
        for index in range(5):
            fresh_app.add_blocked_app(f"pro-probe-{index}")
            time.sleep(0.45)
        assert len(fresh_app.blocked_app_names()) == 5
