"""Shared pytest fixtures for the FlowShield suite."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

AUTOMATION_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AUTOMATION_DIR))

from config import (  # noqa: E402
    APP_EXE,
    SERVER_PORT,
    SERVER_URL,
    stripe_configured,
    stripe_missing,
    stripe_webhooks_configured,
)
from core.diagnostics import DiagnosticLogger  # noqa: E402
from core.services import ServiceGroup, port_is_open  # noqa: E402
from core.settings_guard import preserve_user_settings  # noqa: E402
from desktop.app_controller import DesktopController  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "stripe: needs Stripe test credentials")
    config.addinivalue_line("markers", "ui: drives the desktop app (slow)")
    config.addinivalue_line("markers", "e2e: full end-to-end path")


@pytest.fixture(scope="session", autouse=True)
def user_settings():
    """The owner's real settings.json, set aside for the run and put back after."""
    with preserve_user_settings():
        yield


@pytest.fixture(scope="session")
def logger():
    return DiagnosticLogger("pytest")


@pytest.fixture(scope="session")
def services(logger):
    """License + website servers, started once for the whole session."""
    group = ServiceGroup(logger)
    group.start_all()
    yield group
    group.stop_all()


@pytest.fixture(scope="session")
def server(services):
    """The license server's base URL, once it is confirmed healthy."""
    if not port_is_open(SERVER_PORT):
        pytest.skip(f"license server is not reachable on port {SERVER_PORT}")
    return SERVER_URL


@pytest.fixture(scope="session")
def stripe_ready():
    return stripe_configured()


@pytest.fixture
def needs_stripe(stripe_ready):
    """Gate for anything that creates a charge — needs a secret key and price."""
    if not stripe_ready:
        pytest.skip(f"Stripe not configured (missing: {', '.join(stripe_missing())}) "
                    f"— see STRIPE_SETUP.md")


@pytest.fixture
def needs_webhook_secret():
    """
    Gate for webhook signature tests only.

    Deliberately separate from `needs_stripe`: the webhook secret is unrelated
    to whether a payment can be taken, and folding the two together meant one
    missing value silently skipped the entire payment suite.
    """
    if not stripe_webhooks_configured():
        pytest.skip("no webhook secret configured — see STRIPE_SETUP.md")


@pytest.fixture
def fresh_app(logger):
    """
    A throwaway FlowShield with settings wiped, torn down after each test.

    Deliberately function-scoped. A session-scoped instance would be cheaper
    (~15s per cold launch + UIA attach), but launch_app() clears stray
    FlowShield processes so that a crashed earlier run can't poison the next —
    which means the first per-test launch would silently kill a shared one, and
    every later test using it would fail for reasons unrelated to the code under
    test. Per-test isolation is worth the wall-clock.
    """
    if not Path(APP_EXE).exists():
        pytest.skip(f"{APP_EXE} not built")

    ctrl = DesktopController(logger)
    ctrl.launch_app(clean_state=True)
    ctrl.connect_window()
    time.sleep(1.0)
    ctrl.focus(force=True)
    yield ctrl
    ctrl.close_app()


@pytest.fixture
def schedule_app(logger):
    """
    `fresh_app` with --short-schedules (F6): the heads-up comes 15 seconds
    before a scheduled start instead of 5 minutes, a start up to 30 seconds
    late is offered instead of 30 minutes, and the tick is 1 second. Added
    here rather than to every launch, so no other test runs with a shrunken
    scheduler.
    """
    if not Path(APP_EXE).exists():
        pytest.skip(f"{APP_EXE} not built")

    ctrl = DesktopController(logger)
    ctrl.launch_app(clean_state=True, extra_args=["--short-schedules"])
    ctrl.connect_window()
    time.sleep(1.0)
    ctrl.focus(force=True)
    yield ctrl
    ctrl.close_app()


@pytest.fixture
def expired_app(logger):
    """A fresh FlowShield whose 7-day trial has already run out, with no licence."""
    if not Path(APP_EXE).exists():
        pytest.skip(f"{APP_EXE} not built")

    ctrl = DesktopController(logger)
    ctrl.launch_app(clean_state=True, extra_args=["--expire-trial"])
    ctrl.connect_window()
    time.sleep(1.0)
    ctrl.focus(force=True)
    yield ctrl
    ctrl.close_app()


@pytest.fixture
def app(fresh_app):
    """Readability alias — same isolation guarantees as `fresh_app`."""
    return fresh_app


@pytest.fixture
def trial_expiring_soon_app(logger):
    """
    A fresh FlowShield whose trial is still active at launch but runs out a
    short while later — for F20's "expires mid-sprint" scenario, where the
    lock must wait for the running sprint (and its summary card) rather than
    interrupting either.

    90 s, not the 8 s this used to pass (#243). Eight seconds is less than the
    fixture's own connect-and-focus plus a couple of clicks, so the trial was
    already over before the test had picked a sprint length: the app correctly
    refused the Pro-gated custom length (the log showed it opening the upgrade
    page instead), CustomMinutesInput never appeared, and the F20 scenario
    never got as far as starting a sprint. 90 s leaves the driver room to set
    up while still running out long before the 5-minute sprint ends.
    """
    if not Path(APP_EXE).exists():
        pytest.skip(f"{APP_EXE} not built")

    runway = 90
    ctrl = DesktopController(logger)
    ctrl.launch_app(clean_state=True, extra_args=[f"--expire-trial-in={runway}"])
    # When the trial runs out, on the same clock the test measures with, so the
    # test can wait for the real boundary instead of guessing at a sleep.
    ctrl.trial_ends_at = time.monotonic() + runway
    ctrl.connect_window()
    time.sleep(1.0)
    ctrl.focus(force=True)
    yield ctrl
    ctrl.close_app()
