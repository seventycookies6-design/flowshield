"""
Throwaway diagnostic: click Export and report every top-level window that
appears, so a missing Save dialog can be told apart from one the finder cannot
see. Run inside the lab VM, in the interactive session.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pywinauto import Desktop  # noqa: E402

from desktop.app_controller import DesktopController  # noqa: E402


def dump(tag: str, pid: int) -> None:
    print(f"--- {tag} ---", flush=True)
    for win in Desktop(backend="uia").windows():
        try:
            wpid = win.process_id() if callable(getattr(win, "process_id", None)) else None
            if wpid != pid:
                continue
            texts = " | ".join(t for t in win.texts() if t)[:90]
            print(f"  ctrl={win.element_info.control_type!r} text={texts!r}", flush=True)
            for child in win.children():
                try:
                    print(f"      child ctrl={child.element_info.control_type!r} "
                          f"name={child.element_info.name!r}", flush=True)
                except Exception:
                    pass
        except Exception:
            continue


app = DesktopController()
app.launch_app(clean_state=True, extra_args=["--skip-first-run", "--accept-terms"])
app.connect_window()
print(f"pid={app.pid}", flush=True)

app.navigate_to_tab("Settings")
dump("before click", app.pid)

app.click("ExportJournalButton")
time.sleep(4)
dump("after click", app.pid)

app.close_app()
