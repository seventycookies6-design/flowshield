"""
Playwright automation of Stripe's hosted Checkout page.

Stripe ships several layouts (one-column, two-column, Link-first, accordion
payment methods) and A/B-tests them, so every field here is located by a set of
candidate selectors and the first one that is actually visible wins. Card inputs
live in cross-origin iframes; Playwright's frame-piercing locators handle that
transparently, but the fallback path walks frames explicitly.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeout,
    sync_playwright,
)


@dataclass
class CheckoutResult:
    ok: bool
    session_id: str | None = None
    final_url: str = ""
    message: str = ""
    screenshots: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.screenshots is None:
            self.screenshots = []


class StripeCheckoutAutomator:
    """Drives one hosted-checkout purchase end to end."""

    # Ordered candidates — first visible match is used.
    EMAIL = ["#email", "input[name='email']", "input[autocomplete='email']"]
    CARD_NUMBER = [
        "#cardNumber",
        "input[name='cardNumber']",
        "input[autocomplete='cc-number']",
        "input[placeholder*='1234']",
    ]
    CARD_EXPIRY = ["#cardExpiry", "input[name='cardExpiry']", "input[autocomplete='cc-exp']"]
    CARD_CVC = ["#cardCvc", "input[name='cardCvc']", "input[autocomplete='cc-csc']"]
    CARD_NAME = [
        "#billingName",
        "input[name='billingName']",
        "input[autocomplete='cc-name']",
        "input[name='name']",
    ]
    POSTAL = [
        "#billingPostalCode",
        "input[name='billingPostalCode']",
        "input[autocomplete='billing postal-code']",
        "input[name='postalCode']",
    ]
    COUNTRY = ["#billingCountry", "select[name='billingCountry']"]
    SUBMIT = [
        "button[data-testid='hosted-payment-submit-button']",
        ".SubmitButton",
        "button[type='submit']",
    ]
    CARD_TAB = [
        "button#card-tab",
        "[data-testid='card-accordion-item-button']",
        "button:has-text('Card')",
    ]
    LINK_OPT_OUT = [
        "input[name='enableStripePass']",
        "#enableStripePass",
        "input[data-testid='link-opt-in-checkbox']",
    ]

    def __init__(self, logger=None, headless: bool = False, slow_mo: int = 80,
                 shot_dir: Path | None = None):
        self.log = logger
        self.headless = headless
        self.slow_mo = slow_mo
        self.shot_dir = Path(shot_dir) if shot_dir else None
        self.screenshots: list[str] = []

    # ------------------------------------------------------------- helpers

    def _say(self, message: str) -> None:
        if self.log:
            self.log.info(message)
        else:
            print(f"    {message}")

    def _shot(self, page, label: str) -> None:
        if not self.shot_dir:
            return
        self.shot_dir.mkdir(parents=True, exist_ok=True)
        path = self.shot_dir / f"stripe-{label}.png"
        try:
            page.screenshot(path=str(path), full_page=False)
            self.screenshots.append(str(path))
        except PlaywrightError as exc:
            self._say(f"screenshot '{label}' failed: {exc}")

    @staticmethod
    def _first_visible(page, selectors: list[str], timeout_ms: int = 6000):
        """
        Return a locator for the first selector that resolves to a visible
        element, searching the main frame and then every child frame.
        """
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            for selector in selectors:
                try:
                    locator = page.locator(selector).first
                    if locator.is_visible(timeout=250):
                        return locator
                except (PlaywrightTimeout, PlaywrightError):
                    pass

            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                for selector in selectors:
                    try:
                        locator = frame.locator(selector).first
                        if locator.is_visible(timeout=200):
                            return locator
                    except (PlaywrightTimeout, PlaywrightError):
                        continue
            time.sleep(0.25)
        return None

    def _fill(self, page, selectors: list[str], value: str, label: str,
              required: bool = True, timeout_ms: int = 8000) -> bool:
        locator = self._first_visible(page, selectors, timeout_ms)
        if locator is None:
            level = "missing (required)" if required else "not present (optional)"
            self._say(f"field '{label}' {level}")
            return False
        try:
            locator.click()
            locator.fill("")
            locator.type(value, delay=45)
            self._say(f"filled {label}")
            return True
        except PlaywrightError as exc:
            self._say(f"could not fill '{label}': {exc}")
            return False

    @staticmethod
    def session_id_from_url(url: str) -> str | None:
        query = parse_qs(urlparse(url).query)
        for key in ("session_id", "checkout_session_id"):
            if query.get(key):
                return query[key][0]
        match = re.search(r"(cs_(?:test|live)_[A-Za-z0-9]+)", url)
        return match.group(1) if match else None

    # ------------------------------------------------------------ main flow

    def complete_checkout(
        self,
        checkout_url: str,
        email: str,
        card_number: str,
        expiry: str,
        cvc: str,
        postal_code: str,
        cardholder: str = "Test Buyer",
        timeout_ms: int = 120_000,
    ) -> CheckoutResult:
        self._say(f"opening checkout {checkout_url[:70]}…")

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless, slow_mo=self.slow_mo)
            context = browser.new_context(viewport={"width": 1280, "height": 900},
                                          locale="en-US")
            page = context.new_page()

            try:
                page.goto(checkout_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_load_state("networkidle", timeout=30_000)
                self._shot(page, "01-loaded")

                if "checkout.stripe.com" not in page.url:
                    return CheckoutResult(
                        False, None, page.url,
                        f"not a Stripe Checkout URL (landed on {page.url[:120]})",
                        self.screenshots,
                    )

                # Some layouts collapse card behind an accordion tab.
                tab = self._first_visible(page, self.CARD_TAB, timeout_ms=2500)
                if tab is not None:
                    try:
                        tab.click()
                        self._say("expanded the Card payment section")
                        page.wait_for_timeout(700)
                    except PlaywrightError:
                        pass

                # Email may be pre-filled from customer_email.
                existing = ""
                email_field = self._first_visible(page, self.EMAIL, timeout_ms=4000)
                if email_field is not None:
                    try:
                        existing = email_field.input_value()
                    except PlaywrightError:
                        existing = ""
                if not existing:
                    self._fill(page, self.EMAIL, email, "email", required=False)
                else:
                    self._say(f"email pre-filled as {existing}")

                if not self._fill(page, self.CARD_NUMBER, card_number, "card number"):
                    self._shot(page, "error-no-card-field")
                    return CheckoutResult(
                        False, None, page.url,
                        "card number field never appeared", self.screenshots,
                    )

                self._fill(page, self.CARD_EXPIRY, expiry, "expiry")
                self._fill(page, self.CARD_CVC, cvc, "CVC")
                self._fill(page, self.CARD_NAME, cardholder, "cardholder name", required=False)
                self._fill(page, self.POSTAL, postal_code, "postal code", required=False)

                # Don't enrol the test card in Link — the modal it opens after
                # payment blocks the redirect we need to observe.
                opt_out = self._first_visible(page, self.LINK_OPT_OUT, timeout_ms=1500)
                if opt_out is not None:
                    try:
                        if opt_out.is_checked():
                            opt_out.uncheck()
                            self._say("opted out of Stripe Link")
                    except PlaywrightError:
                        pass

                self._shot(page, "02-filled")

                submit = self._first_visible(page, self.SUBMIT, timeout_ms=8000)
                if submit is None:
                    self._shot(page, "error-no-submit")
                    return CheckoutResult(False, None, page.url,
                                          "submit button not found", self.screenshots)

                self._say("submitting payment…")
                submit.click()

                # Success is a redirect away from checkout.stripe.com.
                try:
                    page.wait_for_url(
                        lambda url: "checkout.stripe.com" not in url,
                        timeout=timeout_ms,
                    )
                except PlaywrightTimeout:
                    error_text = self._read_error(page)
                    self._shot(page, "error-not-redirected")
                    return CheckoutResult(
                        False, None, page.url,
                        error_text or "checkout did not redirect after submit",
                        self.screenshots,
                    )

                page.wait_for_load_state("domcontentloaded", timeout=30_000)
                final_url = page.url
                session_id = self.session_id_from_url(final_url)
                self._say(f"redirected to {final_url[:90]}")

                # Let the success page resolve the license before capturing it.
                try:
                    page.wait_for_function(
                        "() => document.body && document.body.getAttribute('data-license-key')",
                        timeout=45_000,
                    )
                except PlaywrightTimeout:
                    self._say("success page did not publish a license key attribute")

                page.wait_for_timeout(600)
                self._shot(page, "03-success")

                if not session_id:
                    return CheckoutResult(False, None, final_url,
                                          "no session_id in the redirect URL", self.screenshots)

                return CheckoutResult(True, session_id, final_url,
                                      "payment completed", self.screenshots)

            except PlaywrightTimeout as exc:
                self._shot(page, "error-timeout")
                return CheckoutResult(False, None, page.url,
                                      f"timeout: {exc}", self.screenshots)
            except PlaywrightError as exc:
                self._shot(page, "error-playwright")
                return CheckoutResult(False, None, page.url,
                                      f"playwright error: {exc}", self.screenshots)
            finally:
                context.close()
                browser.close()

    @staticmethod
    def _read_error(page) -> str:
        """Pull Stripe's inline decline/validation message, if there is one."""
        for selector in [
            "[data-testid='card-field-error']",
            ".FieldError",
            "[role='alert']",
            ".Notice-content",
        ]:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=400):
                    text = (locator.inner_text() or "").strip()
                    if text:
                        return text
            except PlaywrightError:
                continue
        return ""

    # -------------------------------------------------- license page helper

    def read_license_from_success_page(self, success_url: str,
                                       timeout_ms: int = 45_000) -> dict:
        """Open a success URL directly and read the license it resolves."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            page = browser.new_page()
            try:
                page.goto(success_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_function(
                    "() => document.body && document.body.getAttribute('data-license-key')",
                    timeout=timeout_ms,
                )
                return {
                    "licenseKey": page.evaluate(
                        "document.body.getAttribute('data-license-key')"),
                    "status": page.evaluate(
                        "document.body.getAttribute('data-license-status')"),
                }
            except (PlaywrightTimeout, PlaywrightError) as exc:
                return {"error": str(exc)}
            finally:
                browser.close()
