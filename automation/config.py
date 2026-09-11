"""Shared configuration for the FlowShield automation suite."""

from __future__ import annotations

import json
import os
from pathlib import Path

# --------------------------------------------------------------------- paths

PROJECT_ROOT = Path(os.environ.get("FLOWSHIELD_ROOT", r"C:\Users\xBlah\Downloads\NewApp"))

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
SETTINGS_PATH = Path(os.environ.get("LOCALAPPDATA", "")) / "FlowShield" / "settings.json"
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

WINDOW_CONNECT_TIMEOUT = 25.0
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


def stripe_configured() -> bool:
    """True when every Stripe credential the payment flow needs is present."""
    keys = load_stripe_keys()
    if any(keys.get(f) for f in ("secret_key", "price_id")):
        # Env vars can supply the rest.
        pass
    required = ("publishable_key", "secret_key", "price_id", "webhook_secret")
    return all(keys.get(f) or os.environ.get(f"STRIPE_{f.upper()}") for f in required)


def stripe_missing() -> list[str]:
    keys = load_stripe_keys()
    required = ("publishable_key", "secret_key", "price_id", "webhook_secret")
    return [f for f in required if not (keys.get(f) or os.environ.get(f"STRIPE_{f.upper()}"))]
