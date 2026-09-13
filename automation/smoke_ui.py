"""
Quick UI smoke check: launch the app, visit every tab, capture each one.

Not part of the graded suite — it exists so a human (or Claude) can eyeball the
whole app in four screenshots after a UI change.

    python automation/smoke_ui.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import SCREENSHOT_DIR
from core.diagnostics import DiagnosticLogger
from core.settings_guard import preserve_user_settings
from desktop.app_controller import DesktopController


def main() -> int:
    log = DiagnosticLogger("smoke-ui")
    ctrl = DesktopController(log)

    try:
        log.begin("Launch and connect")
        ctrl.launch_app(clean_state=True)
        ctrl.connect_window()
        time.sleep(1.0)
        ctrl.focus()
        log.passed(f"hwnd {ctrl.hwnd}")

        for tab in ("Today", "Blocked Apps", "Sleep Blocking", "Settings"):
            log.begin(f"Tab: {tab}")
            title = ctrl.navigate_to_tab(tab)
            time.sleep(0.6)
            shot = log.shot(f"tab-{tab.replace(' ', '-').lower()}", ctrl.hwnd)
            log.passed(f"title='{title}' shot={Path(shot).name if shot else 'none'}")

        log.begin("Add a blocked app")
        ctrl.navigate_to_tab("Blocked Apps")
        ctrl.add_blocked_app("flowshield-test-target")
        time.sleep(0.6)
        log.shot("blocked-app-added", ctrl.hwnd)
        log.passed(f"list={ctrl.blocked_app_names()}")

        log.begin("Start a sprint")
        ctrl.navigate_to_tab("Today")
        ctrl.start_sprint()
        time.sleep(2.0)
        log.shot("sprint-running", ctrl.hwnd)
        log.passed(f"timer={ctrl.sprint_timer()} state={ctrl.session_state()}")

        log.begin("Stop the sprint")
        ctrl.stop_sprint()
        time.sleep(1.0)
        log.shot("sprint-stopped", ctrl.hwnd)
        log.passed(f"state={ctrl.session_state()}")

    except Exception as exc:                       # noqa: BLE001
        log.exception(exc)
        log.shot("failure", ctrl.hwnd)
    finally:
        ctrl.close_app()

    log.write_report()
    ok = log.summary()
    print(f"screenshots: {SCREENSHOT_DIR}")
    return 0 if ok else 1


if __name__ == "__main__":
    with preserve_user_settings():
        raise SystemExit(main())
