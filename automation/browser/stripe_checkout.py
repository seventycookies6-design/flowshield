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
        "button:has-text('Subscribe')",
        "button:has-text('Pay')",
        "button[type='submit']",
    ]
    # Managed Payments (default on newer accounts) renders a Link-first page
    # where the card fields only exist after "Card" is selected. The older
    # accordion/tab selectors are kept so both layouts work.
    # Order matters. The radio input sits underneath an accordion button that
    # intercepts pointer events, so clicking the radio times out — the button
    # is the real target and must be tried first.
    CARD_TAB = [
        "[data-testid='card-accordion-item-button']",
        "button[aria-label='Pay with card']",
        "button#card-tab",
        "input[type='radio'][value='card']",
        "button:has-text('Card')",
    ]

    # Link enrolment. Leaving it ticked makes Stripe demand a phone number and
    # can interpose a verification step that swallows the success redirect.
    LINK_OPT_OUT = [
        "input[name='enableStripePass']",
        "#enableStripePass",
        "input[data-testid='link-opt-in-checkbox']",
        "input[type='checkbox'][name='save-my-info']",
        # Last resort: this page has exactly one checkbox, and it is this one.
        "input[type='checkbox']",
    ]

    # Billing address, shown as an autocomplete box until expanded.
    ADDRESS_MANUAL = [
        "text=Enter address manually",
        "button:has-text('Enter address manually')",
        "[data-testid='manual-address-entry']",
    ]
    ADDRESS_LINE1 = [
        "input[placeholder='Address line 1']",
        "input[name='billingAddressLine1']",
        "#billingAddressLine1",
    ]
    CITY = ["input[placeholder='City']", "input[name='billingLocality']", "#billingLocality"]
    STATE = ["select[name='billingAdministrativeArea']", "#billingAdministrativeArea"]

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
        """
        Set a field's value without synthesising a mouse click.

        Stripe's layout overlaps inputs with other controls (a country <select>
        sits over the city and postcode fields), so click() fails hit-testing
        and times out even though the field is perfectly writable. fill() and
        type() focus the element directly and sidestep that entirely.
        """
        locator = self._first_visible(page, selectors, timeout_ms)
        if locator is None:
            level = "missing (required)" if required else "not present (optional)"
            self._say(f"field '{label}' {level}")
            return False

        # Typed entry first — Stripe reformats card numbers and expiry as you
        # type, and some fields ignore a value set in one shot.
        try:
            locator.fill("", timeout=5000)
            locator.type(value, delay=40, timeout=10_000)
            self._say(f"filled {label}")
            return True
        except PlaywrightError:
            pass

        try:
            locator.fill(value, timeout=5000)
            self._say(f"filled {label} (direct)")
            return True
        except PlaywrightError:
            pass

        try:
            locator.click(force=True, timeout=5000)
            locator.type(value, delay=40, timeout=10_000)
            self._say(f"filled {label} (forced)")
            return True
        except PlaywrightError as exc:
            self._say(f"could not fill '{label}': {str(exc).splitlines()[0]}")
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

                # Email first — on the Managed Payments layout the payment
                # method list only renders once an email is present.
                existing = ""
                email_field = self._first_visible(page, self.EMAIL, timeout_ms=6000)
                if email_field is not None:
                    try:
                        existing = email_field.input_value()
                    except PlaywrightError:
                        existing = ""
                if not existing:
                    self._fill(page, self.EMAIL, email, "email", required=False)
                else:
                    self._say(f"email pre-filled as {existing}")
                page.wait_for_timeout(800)

                # Under Managed Payments the card inputs do not exist in the DOM
                # until Card is chosen, and the page opens on Link/Apple Pay.
                if self._first_visible(page, self.CARD_NUMBER, timeout_ms=3000) is None:
                    self._select_card_method(page)

                if not self._fill(page, self.CARD_NUMBER, card_number, "card number"):
                    self._shot(page, "error-no-card-field")
                    return CheckoutResult(
                        False, None, page.url,
                        "card number field never appeared (is the Card method selectable?)",
                        self.screenshots,
                    )

                self._fill(page, self.CARD_EXPIRY, expiry, "expiry")
                self._fill(page, self.CARD_CVC, cvc, "CVC")
                self._fill(page, self.CARD_NAME, cardholder, "cardholder name", required=False)

                # Billing address: a postcode-only field on the classic layout,
                # a full address block (behind a link) on the newer one.
                if self._first_visible(page, self.POSTAL, timeout_ms=1500) is None:
                    manual = self._first_visible(page, self.ADDRESS_MANUAL, timeout_ms=2500)
                    if manual is not None:
                        try:
                            manual.click()
                            self._say("expanded the manual address form")
                            page.wait_for_timeout(900)
                        except PlaywrightError:
                            pass

                self._fill(page, self.ADDRESS_LINE1, "1 Test Street", "address line 1",
                           required=False, timeout_ms=2500)
                self._fill(page, self.CITY, "Beverly Hills", "city",
                           required=False, timeout_ms=2500)
                self._fill(page, self.POSTAL, postal_code, "postal code", required=False)

                state = self._first_visible(page, self.STATE, timeout_ms=2000)
                if state is not None:
                    try:
                        state.select_option("CA")
                        self._say("selected state CA")
                    except PlaywrightError as exc:
                        self._say(f"could not select a state: {exc}")

                # Don't enrol the test card in Link — it demands a phone number
                # and can interpose a step that swallows the success redirect.
                opt_out = self._first_visible(page, self.LINK_OPT_OUT, timeout_ms=2000)
                if opt_out is not None:
                    try:
                        if opt_out.is_checked():
                            opt_out.uncheck()
                            self._say("opted out of Stripe Link")
                            page.wait_for_timeout(500)
                    except PlaywrightError:
                        pass

                self._shot(page, "02-filled")

                submit = self._first_visible(page, self.SUBMIT, timeout_ms=8000)
                if submit is None:
                    self._shot(page, "error-no-submit")
                    return CheckoutResult(False, None, page.url,
                                          "submit button not found", self.screenshots)

                self._say("submitting payment…")
                if not self._click(submit, "the submit button"):
                    self._shot(page, "error-submit-click")
                    return CheckoutResult(False, None, page.url,
                                          "could not click the submit button",
                                          self.screenshots)

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

    def _click(self, locator, label: str) -> bool:
        """
        Click something, scrolling it into view first.

        Order matters and the first step is not optional. Stripe's checkout
        column is taller than the viewport, and a click(force=True) on an
        off-screen element is dispatched at clamped coordinates — it lands on
        whatever happens to be there, the handler never runs, and the page sits
        silently in a half-submitted state. Scroll first, then hit-test for
        real; only fall back to force and a synthetic DOM click.
        """
        try:
            locator.scroll_into_view_if_needed(timeout=5000)
        except PlaywrightError:
            pass

        try:
            locator.click(timeout=8000)
            return True
        except PlaywrightError as exc:
            self._say(f"hit-tested click on {label} failed: {str(exc).splitlines()[0][:70]}")

        try:
            locator.click(force=True, timeout=5000)
            self._say(f"clicked {label} (forced)")
            return True
        except PlaywrightError:
            pass

        try:
            locator.evaluate("el => el.click()")
            self._say(f"clicked {label} (synthetic)")
            return True
        except PlaywrightError as exc:
            self._say(f"could not click {label}: {str(exc).splitlines()[0][:70]}")
            return False

    def _select_card_method(self, page) -> bool:
        """
        Choose the Card payment method, then wait for its fields to render.

        Tried in order: the accordion button, then the covered radio with a
        forced click (bypassing the interception check), then the visible label.
        Each attempt is confirmed by the card number field actually appearing —
        clicking something is not the same as having selected it.
        """
        for selector in self.CARD_TAB:
            locator = self._first_visible(page, [selector], timeout_ms=2500)
            if locator is None:
                continue
            if not self._click(locator, f"Card ({selector})"):
                continue
            page.wait_for_timeout(1200)
            if self._first_visible(page, self.CARD_NUMBER, timeout_ms=4000):
                self._say(f"selected the Card method via {selector}")
                return True

        # Some layouts respond to the label rather than the control.
        try:
            label = page.get_by_text("Card", exact=True).first
            if label.is_visible(timeout=1500):
                label.click(force=True, timeout=5000)
                page.wait_for_timeout(1200)
                if self._first_visible(page, self.CARD_NUMBER, timeout_ms=4000):
                    self._say("selected the Card method via its label")
                    return True
        except PlaywrightError:
            pass

        self._say("could not select the Card payment method")
        return False

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
