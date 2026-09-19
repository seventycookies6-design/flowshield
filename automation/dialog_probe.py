"""Throwaway diagnostic: dump the Save As dialog's own descendants."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from desktop.app_controller import DesktopController  # noqa: E402

app = DesktopController()
app.launch_app(clean_state=True, extra_args=["--skip-first-run", "--accept-terms"])
app.connect_window()
app.navigate_to_tab("Settings")
app.click("ExportJournalButton")
time.sleep(4)

dialog = app.window.child_window(title="Save As", control_type="Window")
print(f"dialog exists: {dialog.exists(timeout=3)}", flush=True)

try:
    for d in dialog.descendants():
        try:
            info = d.element_info
            if info.control_type in ("Edit", "Button", "ComboBox", "Pane"):
                print(f"  {info.control_type!r} name={info.name!r} "
                      f"auto_id={info.automation_id!r}", flush=True)
        except Exception:
            continue
except Exception as exc:
    print(f"descendants failed: {exc}", flush=True)

app.close_app()
