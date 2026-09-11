"""
Does the shield actually close a real running application?

    python automation/verify_blocking.py

Every other test exercises the blocklist with a process name that never runs,
which proves the bookkeeping and proves nothing about the core feature. This
launches a real program (Notepad — harmless and always present), blocks it,
starts a sprint, and checks the process is gone.

Also checks the guard list holds: a protected process must survive being added.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import psutil

from core.diagnostics import DiagnosticLogger
from desktop.app_controller import DesktopController

TARGET = "notepad"


def running_pids(name: str) -> list[int]:
    out = []
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            if (proc.info["name"] or "").lower() == f"{name}.exe".lower():
                out.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def kill_all(name: str) -> None:
    for pid in running_pids(name):
        try:
            psutil.Process(pid).kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def main() -> int:
    log = DiagnosticLogger("verify-blocking")
    ctrl = DesktopController(log)

    try:
        kill_all(TARGET)

        log.begin("Launch FlowShield")
        ctrl.launch_app(clean_state=True)
        ctrl.connect_window()
        time.sleep(1.2)
        ctrl.focus(force=True)
        log.passed(f"pid {ctrl.pid}")

        log.begin(f"Block {TARGET} and confirm it persists")
        ctrl.navigate_to_tab("Blocked Apps")
        if not ctrl.add_blocked_app(TARGET):
            raise AssertionError(f"could not add {TARGET} to the blocklist")
        time.sleep(0.8)
        names = ctrl.blocked_app_names()
        if not any(TARGET in n.lower() for n in names):
            raise AssertionError(f"{TARGET} not in the list: {names}")
        log.passed(str(names))

        log.begin("A protected process cannot be blocked")
        ctrl.add_blocked_app("explorer")
        time.sleep(0.8)
        if "explorer" in " ".join(ctrl.blocked_app_names()).lower():
            raise AssertionError("explorer was accepted onto the blocklist")
        log.passed("explorer refused, as it must be")

        log.begin(f"Start {TARGET} while no sprint is running")
        subprocess.Popen([f"{TARGET}.exe"])
        time.sleep(4)
        before = running_pids(TARGET)
        if not before:
            raise AssertionError(f"{TARGET} did not start")
        # Enforcement is scoped to a sprint; outside one it must be left alone.
        log.passed(f"{TARGET} running (pid {before[0]}) and untouched while idle")

        log.begin("Start a sprint — the shield should close it")
        ctrl.navigate_to_tab("Today")
        ctrl.select_shield("Firm")
        ctrl.start_sprint()

        deadline = time.time() + 25
        survived = before
        while time.time() < deadline:
            survived = running_pids(TARGET)
            if not survived:
                break
            time.sleep(1)

        elapsed = round(25 - (deadline - time.time()), 1)
        log.shot("after-enforcement", ctrl.hwnd)

        if survived:
            raise AssertionError(
                f"{TARGET} was still running after {elapsed}s of an active sprint "
                f"(pids {survived}) — the shield does not actually block anything"
            )
        log.passed(f"{TARGET} closed within {elapsed}s of the sprint starting")

        log.begin("Relaunching it during the sprint gets it closed again")
        subprocess.Popen([f"{TARGET}.exe"])
        time.sleep(1)
        deadline = time.time() + 25
        survived = running_pids(TARGET)
        while time.time() < deadline:
            survived = running_pids(TARGET)
            if not survived:
                break
            time.sleep(1)
        if survived:
            raise AssertionError(f"{TARGET} survived a relaunch mid-sprint: {survived}")
        log.passed("closed again on relaunch")

        log.begin("The block is counted in Today's stats")
        ctrl.stop_sprint()
        time.sleep(1.2)
        blocks = ctrl.text_of("BlocksTodayValue")
        log.shot("today-stats", ctrl.hwnd)
        if not blocks.strip().isdigit() or int(blocks) < 1:
            raise AssertionError(f"'Distractions blocked' shows {blocks!r}, expected at least 1")
        log.passed(f"distractions blocked today = {blocks}")

    except Exception as exc:                       # noqa: BLE001
        log.exception(exc)
        log.shot("failure", ctrl.hwnd)
    finally:
        kill_all(TARGET)
        ctrl.close_app()

    log.write_report()
    return 0 if log.summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())
