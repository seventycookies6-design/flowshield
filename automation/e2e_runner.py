"""
FlowShield end-to-end run.

Drives the real thing from a clean install to an activated Pro licence:
build → servers up → app launch → Buy FlowShield → website → real Stripe test checkout
→ licence key → activation in the app → verification against the encrypted
settings file → Pro-gated features.

    python automation/e2e_runner.py              # visible browser
    python automation/e2e_runner.py --headless   # CI-style

Steps that need Stripe are SKIPPED (not failed) when .stripe_keys.json has no
credentials, so the rest of the suite still reports honestly. Exit code is 0
only if nothing failed.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import requests

from config import (
    APP_EXE,
    MAX_RETRIES,
    SERVER_URL,
    STRIPE_KEYS_PATH,
    TEST_BLOCK_APP,
    TEST_CARD,
    TEST_CVC,
    TEST_EMAIL,
    TEST_EXPIRY,
    TEST_NAME,
    TEST_ZIP,
    WEBSITE_URL,
    stripe_configured,
    stripe_missing,
)
from browser.stripe_checkout import StripeCheckoutAutomator
from core import state_verifier as verify
from core.diagnostics import DiagnosticLogger
from core.services import ServiceGroup, server_health
from core.settings_guard import preserve_user_settings
from desktop.app_controller import DesktopController


SLEEP_START = "23:15"
SLEEP_END = "06:45"


class E2ERun:
    def __init__(self, headless: bool = False, skip_build: bool = False):
        self.log = DiagnosticLogger("e2e")
        self.headless = headless
        self.skip_build = skip_build
        self.ctrl = DesktopController(self.log)
        self.services = ServiceGroup(self.log)

        self.license_key: str | None = None
        self.session_id: str | None = None
        self.checkout_url: str | None = None
        self.stripe_ready = stripe_configured()
        self.extra: dict = {}

    # ------------------------------------------------------------- helpers

    def shot(self, label: str):
        return self.log.shot(label, self.ctrl.hwnd)

    def attempt(self, action, attempts: int = MAX_RETRIES, delay: float = 1.5):
        """Run a step body with retries; the last exception propagates."""
        last: Exception | None = None
        for number in range(1, attempts + 1):
            try:
                return action()
            except Exception as exc:               # noqa: BLE001
                last = exc
                if number < attempts:
                    self.log.warn(f"attempt {number}/{attempts} failed: {exc}")
                    time.sleep(delay)
        raise last  # type: ignore[misc]

    # ================================================================ steps

    def step_01_build(self) -> None:
        self.log.begin("Build the desktop app")
        if self.skip_build and Path(APP_EXE).exists():
            self.log.skipped("--skip-build and a binary already exists")
            return
        self.ctrl.build_app()
        self.log.passed(f"{Path(APP_EXE).name} built")

    def step_02_license_server(self) -> None:
        self.log.begin("Start the license server")
        if not self.services.server.start():
            raise RuntimeError(
                f"license server unhealthy:\n{self.services.server.tail_log()}")

        health = server_health()
        stripe = health.get("stripe", {})
        self.extra["server_health"] = health
        detail = (f"db={health.get('database', {}).get('driver')} "
                  f"stripe={'configured' if stripe.get('configured') else 'NOT configured'}"
                  f" ({stripe.get('mode')})")
        self.log.passed(detail)

    def step_03_website(self) -> None:
        self.log.begin("Start the website")
        if not self.services.website.start():
            raise RuntimeError("website server did not come up")
        response = requests.get(f"{WEBSITE_URL}/index.html", timeout=6)
        if "FlowShield" not in response.text:
            raise RuntimeError("index.html did not render the FlowShield landing page")
        self.log.passed(f"{WEBSITE_URL} serving {len(response.text)} bytes")

    def step_04_launch(self) -> None:
        self.log.begin("Launch FlowShield (clean state)")
        self.ctrl.launch_app(clean_state=True)
        self.log.passed(f"pid {self.ctrl.pid}")

    def step_05_connect(self) -> None:
        self.log.begin("Connect to the app window via UI Automation")
        self.attempt(lambda: self.ctrl.connect_window())
        time.sleep(1.0)
        self.ctrl.focus(force=True)
        self.shot("app-launched")
        self.log.passed(f"hwnd {self.ctrl.hwnd}, title '{self.ctrl.current_page_title()}'")

    def step_06_settings_tab(self) -> None:
        self.log.begin("Navigate to Settings")
        title = self.attempt(lambda: self.ctrl.navigate_to_tab("Settings"))
        status = self.ctrl.get_license_status_text()
        self.shot("settings-trial")
        if title != "Settings":
            raise AssertionError(f"expected the Settings page, got {title!r}")
        if "free trial" not in status.lower():
            raise AssertionError(f"a clean install should start the free trial, got {status!r}")
        self.log.passed(f"status={status!r}, badge={self.ctrl.tier_badge()!r}")

    def step_07_get_pro(self) -> None:
        self.log.begin("Click Buy FlowShield (opens the website)")
        self.attempt(lambda: self.ctrl.click_get_pro_button())
        time.sleep(1.5)
        toast = self.ctrl.toast_text(timeout=3)
        self.shot("after-get-pro")

        # The toast is transient and the browser steals focus, so assert on what
        # the app recorded rather than on catching the toast in time.
        if not self.ctrl.app_log_contains("opening upgrade page"):
            raise AssertionError(
                "the app did not log an upgrade-page launch after Buy FlowShield was clicked")

        self.log.passed(f"upgrade page launched; toast={toast!r}")

    def step_08_create_checkout(self) -> None:
        self.log.begin("Website → POST /create-checkout")
        if not self.stripe_ready:
            self.log.skipped(f"Stripe not configured (missing: {', '.join(stripe_missing())})")
            return

        response = requests.post(f"{SERVER_URL}/create-checkout",
                                 json={"email": TEST_EMAIL}, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")

        payload = response.json()
        self.checkout_url = payload["url"]
        self.license_key = payload["licenseKey"]
        self.extra["reserved_license_key"] = self.license_key

        if "checkout.stripe.com" not in self.checkout_url:
            raise AssertionError(f"unexpected checkout URL: {self.checkout_url[:120]}")
        self.log.passed(f"key={self.license_key} session={payload.get('sessionId')}")

    def step_09_stripe_checkout(self) -> None:
        self.log.begin("Stripe Checkout — pay with the 4242 test card")
        if not self.stripe_ready or not self.checkout_url:
            self.log.skipped("no checkout session to pay for")
            return

        automator = StripeCheckoutAutomator(
            logger=self.log, headless=self.headless, shot_dir=self.log.shot_dir)
        result = automator.complete_checkout(
            checkout_url=self.checkout_url,
            email=TEST_EMAIL,
            card_number=TEST_CARD,
            expiry=TEST_EXPIRY,
            cvc=TEST_CVC,
            postal_code=TEST_ZIP,
            cardholder=TEST_NAME,
        )

        if self.log.steps:
            self.log.steps[-1].screenshots.extend(result.screenshots)

        if not result.ok:
            raise RuntimeError(result.message)

        self.session_id = result.session_id
        self.extra["checkout_session_id"] = self.session_id
        self.log.passed(f"session={self.session_id}")

    def step_10_get_license(self) -> None:
        self.log.begin("GET /get-license → retrieve the key")
        if not self.stripe_ready or not self.session_id:
            self.log.skipped("no completed checkout session")
            return

        deadline = time.time() + 60
        payload: dict = {}
        while time.time() < deadline:
            response = requests.get(f"{SERVER_URL}/get-license",
                                    params={"session_id": self.session_id}, timeout=20)
            payload = response.json()
            if response.status_code == 200 and payload.get("isPro"):
                break
            self.log.info(f"waiting for activation (HTTP {response.status_code}, "
                          f"status={payload.get('status')})")
            time.sleep(2)
        else:
            raise RuntimeError(f"license never became active: {payload}")

        server_key = payload["licenseKey"]
        if self.license_key and server_key != self.license_key:
            raise AssertionError(
                f"key mismatch: reserved {self.license_key}, server returned {server_key}")

        self.license_key = server_key
        self.extra["license"] = payload
        self.log.passed(f"key={server_key} status={payload.get('status')} "
                        f"email={payload.get('email')}")

    def step_11_activate(self) -> None:
        self.log.begin("Activate the licence in the app")
        if not self.license_key:
            self.log.skipped("no license key available")
            return

        self.ctrl.focus(force=True)
        self.ctrl.navigate_to_tab("Settings")
        self.ctrl.enter_license_key(self.license_key)
        self.shot("license-key-entered")

        self.ctrl.click_activate_pro()
        status = self.ctrl.wait_for_license_status("Licence active", timeout=45)
        self.shot("pro-activated")
        self.log.passed(f"status={status!r}")

    def step_12_verify_ui(self) -> None:
        self.log.begin("Verify the UI reports the licence")
        if not self.license_key:
            self.log.skipped("activation did not run")
            return

        result = verify.verify_ui_pro_status(self.ctrl, expected_pro=True)
        if not result.ok:
            raise AssertionError(result.detail)
        self.log.passed(result.detail)

    def step_13_verify_dpapi(self) -> None:
        self.log.begin("Verify DPAPI settings.json has IsPro=true")
        if not self.license_key:
            self.log.skipped("activation did not run")
            return

        encrypted = verify.settings_is_encrypted()
        if not encrypted.ok:
            raise AssertionError(encrypted.detail)

        result = verify.verify_dpapi_settings(expected_pro=True)
        if not result.ok:
            raise AssertionError(result.detail)

        stored_key = (result.data or {}).get("LicenseKey", "")
        if stored_key.replace("-", "") != (self.license_key or "").replace("-", ""):
            raise AssertionError(
                f"stored key {stored_key!r} != activated key {self.license_key!r}")
        self.log.passed(f"{encrypted.detail}; {result.detail}")

    def step_14_blocked_apps(self) -> None:
        self.log.begin("Blocked Apps — add an app and verify it persists")
        self.ctrl.navigate_to_tab("Blocked Apps")
        before = self.ctrl.blocked_app_names()

        self.ctrl.add_blocked_app(TEST_BLOCK_APP)
        time.sleep(0.8)
        after = self.ctrl.blocked_app_names()
        self.shot("blocked-app-added")

        if len(after) <= len(before):
            raise AssertionError(f"list did not grow: {before} → {after}")
        if not any(TEST_BLOCK_APP.lower() in name.lower() for name in after):
            raise AssertionError(f"'{TEST_BLOCK_APP}' not visible in {after}")

        persisted = verify.verify_blocked_app_persisted(TEST_BLOCK_APP)
        if not persisted.ok:
            raise AssertionError(persisted.detail)

        self.log.passed(f"{len(after)} in list; {persisted.detail}")

    def step_15_sleep_blocking(self) -> None:
        self.log.begin("Sleep Blocking — enable a schedule and verify it saves")
        # The sleep window lives on the Schedule page since F6.
        self.ctrl.navigate_to_tab("Schedule")

        # Unlocked either way: by the licence, or by the free trial a clean
        # install is in.
        reached = self.ctrl.set_toggle("SleepBlockToggle", True)
        if not reached:
            raise AssertionError("the sleep-blocking toggle would not turn on during the trial or with a licence")

        self.ctrl.set_sleep_window(SLEEP_START, SLEEP_END)
        time.sleep(0.6)
        self.shot("sleep-blocking-saved")

        saved = verify.verify_sleep_window(enabled=True, start=SLEEP_START, end=SLEEP_END)
        if not saved.ok:
            raise AssertionError(saved.detail)
        self.log.passed(f"{saved.detail}; ui={self.ctrl.sleep_status()!r}")

    def step_16_pro_features(self) -> None:
        self.log.begin("Full access — Shield III is selectable")
        self.ctrl.navigate_to_tab("Today")
        self.ctrl.select_shield("Sealed")
        time.sleep(0.5)
        description = self.ctrl.text_of("ShieldDescriptionText")
        self.shot("shield-selection")

        if "locks" not in description.lower():
            raise AssertionError(
                f"Shield III — Sealed should be selectable, but description reads {description!r}")

        self.log.passed(f"shield description={description!r} (licensed={bool(self.license_key)})")

    def step_17_report(self) -> None:
        self.log.begin("Capture final state and write the report")
        self.ctrl.navigate_to_tab("Settings")
        time.sleep(0.5)
        self.shot("final-settings")

        try:
            settings = verify.read_settings()
            self.extra["final_settings"] = {
                "IsPro": settings.get("IsPro"),
                "LicenseStatus": settings.get("LicenseStatus"),
                "BlockedApps": [a.get("ProcessName") for a in settings.get("BlockedApps", [])],
                "IsSleepBlockEnabled": settings.get("IsSleepBlockEnabled"),
                "SleepWindow": f"{settings.get('SleepBlockStartTime')} → "
                               f"{settings.get('SleepBlockEndTime')}",
                "MomentumScore": settings.get("MomentumScore"),
            }
        except Exception as exc:                   # noqa: BLE001
            self.extra["final_settings_error"] = str(exc)

        self.log.passed("state captured")

    # ================================================================= run

    def run(self) -> int:
        self.log.note("\n" + "=" * 64)
        self.log.note("  FlowShield — end-to-end run")
        self.log.note("=" * 64)

        if not self.stripe_ready:
            self.log.note(
                f"\n  Stripe is not configured — missing: {', '.join(stripe_missing())}\n"
                f"  Payment steps will be SKIPPED, not failed.\n"
                f"  Add your test keys to {STRIPE_KEYS_PATH} (see STRIPE_SETUP.md)\n"
                f"  and re-run to exercise the full purchase path.\n")

        steps = [
            self.step_01_build,
            self.step_02_license_server,
            self.step_03_website,
            self.step_04_launch,
            self.step_05_connect,
            self.step_06_settings_tab,
            self.step_07_get_pro,
            self.step_08_create_checkout,
            self.step_09_stripe_checkout,
            self.step_10_get_license,
            self.step_11_activate,
            self.step_12_verify_ui,
            self.step_13_verify_dpapi,
            self.step_14_blocked_apps,
            self.step_15_sleep_blocking,
            self.step_16_pro_features,
            self.step_17_report,
        ]

        try:
            for step in steps:
                try:
                    step()
                except Exception as exc:           # noqa: BLE001
                    self.log.exception(exc)
                    self.shot(f"failure-{step.__name__}")
                    # A failed early step makes the rest meaningless; stop there.
                    if step.__name__ in {
                        "step_01_build", "step_02_license_server",
                        "step_04_launch", "step_05_connect",
                    }:
                        self.log.error("aborting: the run cannot continue past this step")
                        break
        finally:
            try:
                self.ctrl.close_app()
            finally:
                self.services.stop_all()

        self.extra["stripe_configured"] = self.stripe_ready
        if not self.stripe_ready:
            self.extra["stripe_missing"] = stripe_missing()

        self.log.write_report(self.extra)
        ok = self.log.summary()

        if not self.stripe_ready:
            self.log.note(
                "  Payment steps were skipped because Stripe has no keys.\n"
                "  See STRIPE_SETUP.md — it is a five-minute, one-time setup.\n")

        return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="FlowShield end-to-end run")
    # Headless by default. A visible browser is nicer to watch, but the E2E
    # drives the desktop app at the same time, and the checkout page submits
    # far more reliably headless — a visible window intermittently accepts the
    # submit click without acting on it.
    parser.add_argument("--headed", action="store_true",
                        help="show the checkout browser instead of running it headless")
    parser.add_argument("--headless", action="store_true",
                        help=argparse.SUPPRESS)   # accepted for compatibility
    parser.add_argument("--skip-build", action="store_true",
                        help="reuse the existing binary instead of rebuilding")
    args = parser.parse_args()

    return E2ERun(headless=not args.headed, skip_build=args.skip_build).run()


if __name__ == "__main__":
    with preserve_user_settings():
        raise SystemExit(main())
