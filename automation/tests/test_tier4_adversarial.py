"""
Tier 4 — adversarial and edge cases.

The question here is not "does the happy path work" but "what happens when
someone lies to it, unplugs it, or hammers it". Anything that lets a non-paying
user reach Pro is a failure; so is losing a paying user's access because a
server blinked.
"""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import requests

from config import SERVER_DIR, SETTINGS_PATH
from core import state_verifier as verify

NODE = r"C:\Program Files\nodejs\node.exe"
NODE_EXE = NODE if Path(NODE).exists() else "node"


def new_key() -> str:
    result = subprocess.run(
        [NODE_EXE, "-e", "console.log(require('./licensekey').generate())"],
        cwd=str(SERVER_DIR), capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


def corrupt_key() -> str:
    """Right shape, deliberately broken checksum — derived, never hardcoded."""
    script = (
        "const k=require('./licensekey');"
        "const body=k.generate().replace(/-/g,'').slice(2);"
        "const a='0123456789ABCDEFGHJKMNPQRSTVWXYZ';"
        "const m=body.slice(0,14)+a[(a.indexOf(body[14])+1)%32];"
        "console.log('FS-'+m.match(/.{1,4}/g).join('-'));"
    )
    result = subprocess.run([NODE_EXE, "-e", script], cwd=str(SERVER_DIR),
                            capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


# ==================================================== forged / hostile input

class TestForgedLicenses:
    @pytest.mark.parametrize("forged", [
        "FS-AAAA-AAAA-AAAA-AAAA",
        "FS-0000-0000-0000-0000",
        "FS-ZZZZ-ZZZZ-ZZZZ-ZZZZ",
        "FS-9999-9999-9999-9999",
    ])
    def test_guessed_keys_do_not_grant_pro(self, server, forged):
        body = requests.post(f"{server}/validate",
                             json={"licenseKey": forged}, timeout=15).json()
        assert body["isPro"] is False, f"{forged} was accepted!"

    def test_a_checksum_valid_but_unissued_key_is_refused(self, server):
        """Passing the offline checksum must not be enough on its own."""
        body = requests.post(f"{server}/validate",
                             json={"licenseKey": new_key()}, timeout=15).json()
        assert body["isPro"] is False
        assert body["reason"] == "not_found"

    @pytest.mark.parametrize("payload", [
        {"licenseKey": None},
        {"licenseKey": 12345},
        {"licenseKey": ["FS-AAAA-AAAA-AAAA-AAAA"]},
        {"licenseKey": {"nested": "object"}},
        {"email": 42},
    ])
    def test_wrong_types_do_not_crash_the_server(self, server, payload):
        response = requests.post(f"{server}/validate", json=payload, timeout=15)
        assert response.status_code < 500, f"{payload} caused {response.status_code}"

    def test_sql_injection_in_the_key_is_inert(self, server):
        """Parameterised queries should make this a plain not-found."""
        for attack in ["' OR '1'='1", "'; DROP TABLE licenses; --",
                       "FS-AAAA-AAAA-AAAA-AAAA' OR 1=1 --"]:
            body = requests.post(f"{server}/validate",
                                 json={"licenseKey": attack}, timeout=15).json()
            assert body["isPro"] is False, f"{attack!r} granted Pro"

        # And the table is still there.
        health = requests.get(f"{server}/health", timeout=10).json()
        assert health["status"] == "ok"

    def test_sql_injection_via_email_is_inert(self, server):
        body = requests.post(f"{server}/validate",
                             json={"email": "x' OR '1'='1"}, timeout=15).json()
        assert body["isPro"] is False
        assert requests.get(f"{server}/health", timeout=10).json()["status"] == "ok"

    def test_a_very_long_key_is_handled(self, server):
        response = requests.post(f"{server}/validate",
                                 json={"licenseKey": "FS-" + "A" * 10_000}, timeout=20)
        assert response.status_code < 500
        assert response.json()["isPro"] is False

    def test_unicode_and_control_characters_are_handled(self, server):
        for nasty in ["FS-🙂🙂🙂🙂-AAAA-AAAA-AAAA", "FS-\x00\x01-AAAA-AAAA-AAAA",
                      "FS-‮AAAA-AAAA-AAAA-AAAA"]:
            response = requests.post(f"{server}/validate",
                                     json={"licenseKey": nasty}, timeout=15)
            assert response.status_code < 500
            assert response.json()["isPro"] is False


# ============================================================ malformed HTTP

class TestMalformedRequests:
    def test_invalid_json_body_is_a_400_not_a_500(self, server):
        response = requests.post(f"{server}/validate",
                                 data="{not json at all",
                                 headers={"Content-Type": "application/json"},
                                 timeout=15)
        assert 400 <= response.status_code < 500, response.status_code

    def test_empty_body_is_handled(self, server):
        response = requests.post(f"{server}/validate",
                                 headers={"Content-Type": "application/json"},
                                 timeout=15)
        assert response.status_code < 500

    def test_wrong_method_does_not_crash(self, server):
        response = requests.get(f"{server}/validate", timeout=10)
        assert response.status_code in (404, 405)

    def test_an_oversized_body_is_refused_cleanly(self, server):
        response = requests.post(f"{server}/validate",
                                 json={"licenseKey": "A" * 2_000_000}, timeout=30)
        assert response.status_code < 500, \
            "an oversized body should be rejected, not crash the process"


# ================================================================ webhooks

class TestWebhookSecurity:
    def test_no_signature_header_is_refused(self, server):
        response = requests.post(
            f"{server}/webhook",
            data=json.dumps({"id": "evt_x", "type": "checkout.session.completed"}),
            headers={"Content-Type": "application/json"}, timeout=10)
        assert response.status_code in (400, 503)

    @pytest.mark.parametrize("signature", [
        "", "garbage", "t=0,v1=0", "t=9999999999,v1=" + "f" * 64,
    ])
    def test_bogus_signatures_are_refused(self, server, signature):
        response = requests.post(
            f"{server}/webhook",
            data=json.dumps({"id": "evt_y", "type": "checkout.session.completed"}),
            headers={"Content-Type": "application/json", "Stripe-Signature": signature},
            timeout=10)
        assert response.status_code in (400, 503), \
            f"signature {signature!r} was not rejected"

    def test_a_forged_activation_event_cannot_grant_pro(self, server):
        """The whole point of signature verification."""
        key = new_key()
        requests.post(
            f"{server}/webhook",
            data=json.dumps({
                "id": f"evt_attack_{uuid.uuid4().hex[:12]}",
                "type": "checkout.session.completed",
                "data": {"object": {"id": "cs_test_forged",
                                    "client_reference_id": key,
                                    "status": "complete",
                                    "payment_status": "paid"}},
            }),
            headers={"Content-Type": "application/json",
                     "Stripe-Signature": "t=1,v1=forged"},
            timeout=15)

        body = requests.post(f"{server}/validate",
                             json={"licenseKey": key}, timeout=15).json()
        assert body["isPro"] is False, "a forged webhook activated a licence!"


# ============================================================== concurrency

class TestConcurrency:
    def test_parallel_validations_stay_consistent(self, server):
        key = corrupt_key()

        def call(_):
            return requests.post(f"{server}/validate",
                                 json={"licenseKey": key}, timeout=20).json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(call, range(24)))

        assert all(r["isPro"] is False for r in results)
        assert len({r["reason"] for r in results}) == 1, \
            "the same key produced different verdicts under load"

    def test_parallel_checkouts_get_distinct_keys(self, server, needs_stripe):
        def create(_):
            return requests.post(f"{server}/create-checkout", json={}, timeout=60).json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(create, range(4)))

        keys = [r["licenseKey"] for r in results]
        assert len(set(keys)) == len(keys), f"duplicate keys issued: {keys}"

    def test_the_server_survives_a_burst(self, server):
        def hit(_):
            return requests.get(f"{server}/health", timeout=20).status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            codes = list(pool.map(hit, range(60)))

        assert all(code == 200 for code in codes), f"non-200s under load: {set(codes)}"


# ======================================================== network failures

@pytest.mark.ui
class TestNetworkFailure:
    def test_the_app_reports_an_unreachable_server_instead_of_hanging(self, fresh_app):
        """Point the app at a dead port and confirm it fails loudly but safely."""
        fresh_app.navigate_to_tab("Settings")
        fresh_app.set_text("LicenseServerUrlInput", "http://127.0.0.1:59999")
        # Commit the LostFocus binding.
        fresh_app.click("LicenseKeyInput")
        time.sleep(0.4)

        fresh_app.enter_license_key("FS-AAAA-AAAA-AAAA-AAAA")
        fresh_app.click_activate_pro()
        time.sleep(6)

        status = fresh_app.get_license_status_text()
        detail = fresh_app.get_license_detail_text()

        assert "pro active" not in status.lower(), \
            "a dead server must never result in Pro"
        assert status.strip() != "", "the status line went blank instead of explaining"
        assert any(word in (status + detail).lower()
                   for word in ("not activated", "couldn't reach", "could not",
                                "server", "format")), \
            f"unhelpful failure text: {status!r} / {detail!r}"

    def test_a_failed_activation_leaves_the_free_tier_intact_on_disk(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.enter_license_key("FS-AAAA-AAAA-AAAA-AAAA")
        fresh_app.click_activate_pro()
        time.sleep(4)

        result = verify.verify_dpapi_settings(expected_pro=False)
        assert result.ok, f"a rejected licence changed the stored tier: {result.detail}"


# ========================================================= tampered storage

@pytest.mark.ui
class TestTamperedSettings:
    def test_a_corrupt_settings_file_does_not_brick_the_app(self, logger):
        """Garbage on disk should start a clean session, not crash."""
        from desktop.app_controller import DesktopController

        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text("this is not json at all", encoding="utf-8")

        ctrl = DesktopController(logger)
        try:
            ctrl.launch_app(clean_state=False)
            ctrl.connect_window(timeout=30)
            time.sleep(1.2)
            assert ctrl.current_page_title() == "Today"

            ctrl.navigate_to_tab("Settings")
            assert "free" in ctrl.get_license_status_text().lower(), \
                "a corrupt file must not be readable as a Pro licence"
        finally:
            ctrl.close_app()

    def test_a_hand_edited_pro_flag_is_not_forgeable(self, logger):
        """
        Flip IsPro in the envelope without the DPAPI key and the app must
        reject the file rather than trust it.
        """
        from desktop.app_controller import DesktopController

        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps({
            "Version": 1,
            "Protected": True,
            "Entropy": "FlowShield.v1",
            "WrittenUtc": "2026-01-01T00:00:00.000Z",
            # Valid base64, but not a blob this user's DPAPI key can open.
            "Data": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQQ==",
        }), encoding="utf-8")

        ctrl = DesktopController(logger)
        try:
            ctrl.launch_app(clean_state=False)
            ctrl.connect_window(timeout=30)
            time.sleep(1.2)
            ctrl.navigate_to_tab("Settings")
            assert "pro active" not in ctrl.get_license_status_text().lower(), \
                "a forged settings envelope granted Pro"
        finally:
            ctrl.close_app()


# ============================================================== input edges

@pytest.mark.ui
class TestUIInputEdges:
    def test_an_empty_activation_is_refused(self, fresh_app):
        fresh_app.navigate_to_tab("Settings")
        fresh_app.enter_license_key("")
        fresh_app.enter_license_email("")
        fresh_app.click_activate_pro()
        time.sleep(2.5)
        assert "pro active" not in fresh_app.get_license_status_text().lower()

    def test_whitespace_only_app_name_is_not_added(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        before = len(fresh_app.blocked_app_names())

        added = fresh_app.add_blocked_app("     ")
        time.sleep(0.8)

        assert added is False, "Add was clickable with a whitespace-only name"
        assert fresh_app.is_control_enabled("AddAppButton") is False
        assert len(fresh_app.blocked_app_names()) == before

    def test_the_sleep_window_cannot_be_edited_on_the_free_tier(self, fresh_app):
        """
        The whole schedule row is gated, not just the toggle.

        An earlier version of this test typed an invalid time into these fields
        and asserted it wasn't saved — but on Free the fields are disabled, so
        it was really just failing to type. Assert the gate that actually
        exists; the time-parsing rules are covered by tier 1.
        """
        fresh_app.navigate_to_tab("Sleep Blocking")

        for auto_id in ("SleepStartInput", "SleepEndInput"):
            assert fresh_app.is_control_enabled(auto_id) is False, \
                f"{auto_id} is editable without Pro"

        result = verify.verify_sleep_window(enabled=False)
        assert result.ok, result.detail

    def test_saving_a_sleep_window_without_pro_persists_nothing(self, fresh_app):
        fresh_app.navigate_to_tab("Sleep Blocking")
        before = verify.read_settings()

        # The Save button stays live so it can explain the gate; pressing it
        # must still change nothing on disk.
        if fresh_app.is_control_enabled("SaveSleepWindowButton"):
            fresh_app.click("SaveSleepWindowButton")
            time.sleep(1.0)

        after = verify.read_settings()
        assert after["IsSleepBlockEnabled"] is False
        assert after["SleepBlockStartTime"] == before["SleepBlockStartTime"]
        assert after["SleepBlockEndTime"] == before["SleepBlockEndTime"]

    def test_a_very_long_app_name_does_not_break_the_list(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.add_blocked_app("x" * 300)
        time.sleep(1.0)
        assert fresh_app.current_page_title() == "Blocked Apps", "the app fell over"


# ====================================================== declined test cards

@pytest.mark.stripe
class TestDeclinedCards:
    """Stripe's dedicated decline cards must not produce a licence."""

    DECLINED = "4000 0000 0000 0002"       # generic decline

    def test_a_declined_card_grants_nothing(self, server, needs_stripe, logger):
        from browser.stripe_checkout import StripeCheckoutAutomator
        from config import TEST_CVC, TEST_EMAIL, TEST_EXPIRY, TEST_NAME, TEST_ZIP

        created = requests.post(f"{server}/create-checkout", json={}, timeout=45).json()

        automator = StripeCheckoutAutomator(logger=logger, headless=True,
                                            shot_dir=logger.shot_dir)
        result = automator.complete_checkout(
            checkout_url=created["url"], email=TEST_EMAIL,
            card_number=self.DECLINED, expiry=TEST_EXPIRY, cvc=TEST_CVC,
            postal_code=TEST_ZIP, cardholder=TEST_NAME, timeout_ms=60_000)

        assert result.ok is False, "a declined card completed checkout"

        body = requests.post(f"{server}/validate",
                             json={"licenseKey": created["licenseKey"]}, timeout=20).json()
        assert body["isPro"] is False, "a declined payment still granted Pro"
