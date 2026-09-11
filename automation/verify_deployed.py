"""
Verify the shipped desktop app against the DEPLOYED licence server.

    python automation/verify_deployed.py FS-XXXX-XXXX-XXXX-XXXX

No --server override and no local services: the app uses its built-in default,
which is exactly what a downloaded copy would do. That is the point — it proves
the binary a customer would run can activate over the internet.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import requests

from core import state_verifier as verify
from core.diagnostics import DiagnosticLogger
from desktop.app_controller import DesktopController

DEPLOYED = "https://flowshield-license-server.onrender.com"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    key = sys.argv[1].strip()

    log = DiagnosticLogger("verify-deployed")
    ctrl = DesktopController(log)

    try:
        log.begin("Deployed server is reachable")
        health = requests.get(f"{DEPLOYED}/health", timeout=60).json()
        if not health["stripe"]["configured"]:
            raise RuntimeError(f"server not configured: {health}")
        log.passed(f"driver={health['database']['driver']} mode={health['stripe']['mode']}")

        log.begin("Launch the app with its shipped defaults")
        # clean_state wipes settings so the built-in default URL is used;
        # use_defaults omits the --server override the suite normally injects.
        ctrl.launch_app(clean_state=True, use_defaults=True)
        ctrl.connect_window()
        time.sleep(1.5)
        ctrl.focus(force=True)
        log.passed(f"pid {ctrl.pid}")

        log.begin("Confirm it points at the deployed server by default")
        ctrl.navigate_to_tab("Settings")
        configured = ctrl.text_of("LicenseServerUrlInput")
        if DEPLOYED not in configured:
            raise AssertionError(f"app points at {configured!r}, expected {DEPLOYED}")
        log.passed(configured)

        log.begin("Activate Pro over the internet")
        ctrl.enter_license_key(key)
        log.shot("key-entered", ctrl.hwnd)
        ctrl.click_activate_pro()
        # Generous: a sleeping free-tier host can take ~50s to wake.
        status = ctrl.wait_for_license_status("Pro Active", timeout=120)
        log.shot("pro-active", ctrl.hwnd)
        log.passed(f"status={status!r} badge={ctrl.tier_badge()!r}")

        log.begin("Verify it persisted to the encrypted settings file")
        result = verify.verify_dpapi_settings(expected_pro=True)
        if not result.ok:
            raise AssertionError(result.detail)
        log.passed(result.detail)

        log.begin("Pro features unlocked")
        ctrl.navigate_to_tab("Sleep Blocking")
        if not ctrl.set_toggle("SleepBlockToggle", True):
            raise AssertionError("sleep blocking still gated after activation")
        ctrl.navigate_to_tab("Today")
        ctrl.select_shield("Sealed")
        time.sleep(0.6)
        description = ctrl.text_of("ShieldDescriptionText")
        if "locks" not in description.lower():
            raise AssertionError(f"Shield III not available: {description!r}")
        log.shot("pro-features", ctrl.hwnd)
        log.passed(f"sleep blocking on; shield III = {description!r}")

    except Exception as exc:                       # noqa: BLE001
        log.exception(exc)
        log.shot("failure", ctrl.hwnd)
    finally:
        ctrl.close_app()

    log.write_report({"deployed_server": DEPLOYED})
    return 0 if log.summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())
