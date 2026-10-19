"""Shared pytest fixtures for the Basalt suite."""

from __future__ import annotations

import ast
import inspect
import sys
import textwrap
import time
from functools import lru_cache
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
from core.settings_guard import (  # noqa: E402
    preserve_user_settings,
    user_state_fingerprint,
)
from desktop.app_controller import DesktopController  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "stripe: needs Stripe test credentials")
    config.addinivalue_line("markers", "ui: drives the desktop app (slow)")
    config.addinivalue_line(
        "markers", "touches_user_state: reads or changes real FlowShield user state"
    )
    config.addinivalue_line("markers", "e2e: full end-to-end path")


_USER_STATE_FIXTURES = frozenset({
    "fresh_app",
    "schedule_app",
    "expired_app",
    "app",
    "trial_expiring_soon_app",
})
_USER_STATE_CALLS = frozenset({
    "launch_app",
    "launch_app_process",
    "run_app_process",
    "clear_trial_record",
    "preserve_user_settings",
})
@lru_cache(maxsize=None)
def _function_touches_user_state(function) -> bool:
    """Catch direct state access even when the test has not been marked yet."""
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    except (OSError, TypeError, IndentationError, SyntaxError):
        return False

    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and node.attr == "SETTINGS_PATH"
                or isinstance(node, ast.Name) and node.id == "SETTINGS_PATH"):
            return True
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in _USER_STATE_CALLS:
            return True
        if isinstance(func, ast.Attribute):
            if func.attr in _USER_STATE_CALLS:
                return True
            if (isinstance(func.value, ast.Name)
                    and func.value.id == "winreg"):
                return True
    return False


def _fixture_isolates_state(item) -> bool:
    """Recognize the tier 5 `guard` fixture that redirects file and registry access."""
    fixture_info = getattr(item, "_fixtureinfo", None)
    if fixture_info is None:
        return False
    definitions = fixture_info.name2fixturedefs.get("guard", ())
    for definition in definitions:
        try:
            source = inspect.getsource(definition.func)
        except (OSError, TypeError):
            continue
        if ('"SETTINGS_PATH"' in source and '"winreg"' in source
                and "tmp_path" in source and "monkeypatch" in source):
            return True
    return False


def _item_touches_user_state(item) -> bool:
    if (item.get_closest_marker("ui")
            or item.get_closest_marker("touches_user_state")
            or _USER_STATE_FIXTURES.intersection(item.fixturenames)):
        return True
    if _fixture_isolates_state(item):
        return False
    function = getattr(item, "obj", None)
    if function is not None:
        return _function_touches_user_state(getattr(function, "__func__", function))
    return False


def _session_needs_settings_guard(items) -> bool:
    """Whether a collected test can launch the app or change real user state."""
    return any(_item_touches_user_state(item) for item in items)


def _fingerprint_summary(fingerprint) -> str:
    settings_hash, run_value, trial_value = fingerprint
    settings = settings_hash or "absent"
    return (f"settings SHA-256={settings}; HKCU Run.FlowShield={run_value!r}; "
            f"HKCU Trial.StartedUtc={trial_value!r}")


@pytest.fixture(scope="session", autouse=True)
def user_settings(request):
    """Guard app/state tests; fingerprint fast-only sessions without backups."""
    if _session_needs_settings_guard(request.session.items):
        with preserve_user_settings():
            yield
        return

    before = user_state_fingerprint()
    yield
    after = user_state_fingerprint()
    if after != before:
        pytest.fail(
            "A fast test changed real FlowShield user state. "
            f"Before: {_fingerprint_summary(before)}. "
            f"After: {_fingerprint_summary(after)}.",
            pytrace=False,
        )


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
    A throwaway Basalt with settings wiped, torn down after each test.

    Deliberately function-scoped. A session-scoped instance would be cheaper
    (~15s per cold launch + UIA attach), but launch_app() clears stray
    Basalt processes so that a crashed earlier run can't poison the next —
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
    """A fresh Basalt whose 7-day trial has already run out, with no licence."""
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
    A fresh Basalt whose trial is still active at launch but runs out a
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
