"""
Drive one real test-mode checkout through the license-server flow and report.

    python automation/check_checkout.py [--headless]

Exists because the Stripe hosted-checkout page is A/B tested and changes shape
(Managed Payments moved the card fields behind a radio), and a 20-second run
here is a far faster way to re-tune selectors than a 40-minute full suite.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import requests

from browser.stripe_checkout import StripeCheckoutAutomator
from config import (SERVER_URL, TEST_CARD, TEST_CVC, TEST_EMAIL, TEST_EXPIRY,
                    TEST_NAME, TEST_ZIP, stripe_configured, stripe_missing)
from core.diagnostics import DiagnosticLogger
from core.services import ServiceGroup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    if not stripe_configured():
        print(f"Stripe not configured (missing: {', '.join(stripe_missing())})")
        return 2

    log = DiagnosticLogger("checkout-check")
    services = ServiceGroup(log)
    services.start_all()

    try:
        log.begin("POST /create-checkout")
        created = requests.post(f"{SERVER_URL}/create-checkout",
                                json={"email": TEST_EMAIL}, timeout=45).json()
        if "url" not in created:
            log.failed(str(created))
            return 1
        log.passed(f"key={created['licenseKey']} session={created['sessionId']}")

        log.begin("Complete the hosted checkout")
        automator = StripeCheckoutAutomator(
            logger=log, headless=args.headless, shot_dir=log.shot_dir)
        result = automator.complete_checkout(
            checkout_url=created["url"], email=TEST_EMAIL, card_number=TEST_CARD,
            expiry=TEST_EXPIRY, cvc=TEST_CVC, postal_code=TEST_ZIP,
            cardholder=TEST_NAME)

        if not result.ok:
            log.failed(result.message)
            log.summary()
            return 1
        log.passed(f"session={result.session_id}")

        log.begin("GET /get-license")
        deadline = time.time() + 60
        payload = {}
        while time.time() < deadline:
            response = requests.get(f"{SERVER_URL}/get-license",
                                    params={"session_id": result.session_id}, timeout=20)
            payload = response.json()
            if response.status_code == 200 and payload.get("isPro"):
                break
            time.sleep(2)

        if not payload.get("isPro"):
            log.failed(f"licence never activated: {payload}")
            log.summary()
            return 1

        log.passed(f"key={payload['licenseKey']} status={payload['status']} "
                   f"email={payload.get('email')}")
        print(f"\n  LICENCE KEY: {payload['licenseKey']}\n")

    finally:
        services.stop_all()

    log.write_report()
    return 0 if log.summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())
