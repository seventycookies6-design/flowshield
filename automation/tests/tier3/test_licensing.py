# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 3: licensing."""

from __future__ import annotations
import time
import pytest
from core import state_verifier as verify
from ._helpers import LINK, LINK_KEY, flowshield_pids, launch_again

pytestmark = pytest.mark.ui



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

        # The shortest sprint Basalt offers (5 minutes) comfortably
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
        # "what moved?" is never interrupted by "buy Basalt".
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
        status = fresh_app.wait_for_license_status("License active", timeout=45)
        assert "license active" in status.lower()

        ui = verify.verify_ui_pro_status(fresh_app, expected_pro=True)
        assert ui.ok, ui.detail

        disk = verify.verify_dpapi_settings(expected_pro=True)
        assert disk.ok, disk.detail
        assert disk.data["LicenseKey"] == payload["licenseKey"]


@pytest.mark.stripe
@pytest.mark.e2e
class TestPurchaseUnlocksAnExpiredTrial:
    """Buying Basalt after the trial has ended must lift the lock."""

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
        assert "license active" in expired_app.get_license_status_text().lower()
        assert expired_app.tier_badge().upper() == "PURCHASED"


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
