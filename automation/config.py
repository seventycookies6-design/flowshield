"""Shared configuration for the FlowShield automation suite."""

from __future__ import annotations

import json
import os
from pathlib import Path

# --------------------------------------------------------------------- paths

# Derived from this file's location so a clone works wherever it lives.
PROJECT_ROOT = Path(os.environ.get("FLOWSHIELD_ROOT", Path(__file__).resolve().parent.parent))

SERVER_DIR = PROJECT_ROOT / "Server"
WEBSITE_DIR = PROJECT_ROOT / "Website"
DESKTOP_DIR = PROJECT_ROOT / "DesktopApp"
AUTOMATION_DIR = PROJECT_ROOT / "automation"

LOG_DIR = PROJECT_ROOT / "logs"
SCREENSHOT_DIR = PROJECT_ROOT / "screenshots"
REPORT_DIR = PROJECT_ROOT / "reports"

for _d in (LOG_DIR, SCREENSHOT_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

STRIPE_KEYS_PATH = PROJECT_ROOT / ".stripe_keys.json"

APP_NAME = "FlowShield"
APP_EXE = DESKTOP_DIR / "bin" / "Release" / "net8.0-windows" / "FlowShield.exe"
APP_WINDOW_TITLE = "FlowShield"
APP_PROCESS_NAME = "FlowShield"

# Settings written by the app (DPAPI-encrypted envelope).
# Roaming AppData: %LOCALAPPDATA%\FlowShield is the installer's directory, so
# user data must not live there — an update or uninstall would take it.
SETTINGS_PATH = Path(os.environ.get("APPDATA", "")) / "FlowShield" / "settings.json"
DPAPI_ENTROPY = b"FlowShield.v1"

# ------------------------------------------------------------------ services

SERVER_PORT = int(os.environ.get("FLOWSHIELD_SERVER_PORT", 3000))
WEBSITE_PORT = int(os.environ.get("FLOWSHIELD_WEBSITE_PORT", 5500))
SERVER_URL = f"http://localhost:{SERVER_PORT}"
WEBSITE_URL = f"http://localhost:{WEBSITE_PORT}"

# -------------------------------------------------------------- test fixtures

TEST_EMAIL = "testbuyer@example.com"
TEST_CARD = "4242 4242 4242 4242"
TEST_EXPIRY = "12/34"
TEST_CVC = "123"
TEST_ZIP = "90210"
TEST_NAME = "Test Buyer"

# A harmless, always-available process used as the blocklist target so the
# suite never risks terminating something the user cares about.
TEST_BLOCK_APP = "flowshield-test-target"

# ------------------------------------------------------------------- timeouts

# Defender scanning can delay the first launch of a fresh executable.
WINDOW_CONNECT_TIMEOUT = 60.0
UI_ACTION_TIMEOUT = 12.0
CHECKOUT_TIMEOUT = 120_000  # Playwright milliseconds
MAX_RETRIES = 3


def load_stripe_keys() -> dict:
    """Read .stripe_keys.json, blanking out unreplaced placeholders."""
    if not STRIPE_KEYS_PATH.exists():
        return {}
    try:
        raw = json.loads(STRIPE_KEYS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    out = {}
    for key, value in raw.items():
        text = str(value or "").strip()
        if text.startswith("REPLACE_ME") or text.endswith("..."):
            text = ""
        out[key] = text
    return out


ALL_STRIPE_FIELDS = ("publishable_key", "secret_key", "price_id", "webhook_secret")

# Creating a Checkout Session needs only these two. The webhook secret is a
# separate concern, so the two are gated separately: bundling them meant a
# missing webhook secret silently skipped every checkout test as well.
PAYMENT_FIELDS = ("secret_key", "price_id")


def _have(field: str) -> bool:
    keys = load_stripe_keys()
    return bool(keys.get(field) or os.environ.get(f"STRIPE_{field.upper()}"))


def stripe_configured() -> bool:
    """True when the payment path can run (secret key + price)."""
    return all(_have(f) for f in PAYMENT_FIELDS)


def stripe_webhooks_configured() -> bool:
    """True when webhook signature verification can be exercised."""
    return _have("webhook_secret")


def stripe_fully_configured() -> bool:
    return all(_have(f) for f in ALL_STRIPE_FIELDS)


def stripe_missing() -> list[str]:
    """Fields still missing for the payment path."""
    return [f for f in PAYMENT_FIELDS if not _have(f)]


def stripe_missing_all() -> list[str]:
    return [f for f in ALL_STRIPE_FIELDS if not _have(f)]
