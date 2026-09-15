"""
Keep the owner's real settings and Windows startup entry out of the suite's way.

The dev build and an installed FlowShield share one settings file in Roaming
AppData, and the suite wipes and rewrites it constantly — leaving it pointed at
http://localhost:3000. Without this, running the tests on a machine that also
has FlowShield installed quietly breaks that install's licence checks.

`preserve_user_settings()` copies the file aside before a run and puts it back
afterwards. The backup is written only once: if a previous run was killed before
restoring, the backup on disk is still the owner's file, so it is kept rather
than overwritten with whatever the dead run left behind.

The Start-with-Windows Run value receives the same treatment because Phase 1.2
tests deliberately enable and corrupt it before checking that launch repairs it.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

import psutil

try:
    import winreg
except ImportError:  # pragma: no cover - the desktop suite runs on Windows
    winreg = None

from config import APP_EXE, SETTINGS_PATH

BACKUP_PATH = SETTINGS_PATH.with_name(SETTINGS_PATH.name + ".pre-tests")
STARTUP_BACKUP_PATH = SETTINGS_PATH.with_name("startup-registration.pre-tests.json")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "FlowShield"

# A real settings file is a DPAPI envelope and never empty, so a zero-byte
# backup can safely mean "there was no settings file to begin with".
_NO_SETTINGS = b""

_depth = 0


def _stop_dev_build() -> None:
    """
    Close any copy of the dev build still running, so it can't save settings
    over the restored file on its way out. Only the dev build: an installed copy
    lives elsewhere and isn't ours to kill.
    """
    target = os.path.normcase(str(Path(APP_EXE).resolve()))
    stopped = False
    for proc in psutil.process_iter(["exe"]):
        try:
            if proc.info["exe"] and os.path.normcase(proc.info["exe"]) == target:
                proc.kill()
                stopped = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if stopped:
        time.sleep(1.2)


def back_up() -> None:
    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not BACKUP_PATH.exists():
        if SETTINGS_PATH.exists():
            shutil.copy2(SETTINGS_PATH, BACKUP_PATH)
        else:
            BACKUP_PATH.write_bytes(_NO_SETTINGS)

    _back_up_startup_registration()


def _back_up_startup_registration() -> None:
    """Persist the real Run value before a test is allowed to change it."""
    if winreg is None or STARTUP_BACKUP_PATH.exists():
        return

    backup = {"present": False, "value": None, "type": winreg.REG_SZ}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, value_type = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            backup = {"present": True, "value": value, "type": value_type}
    except FileNotFoundError:
        pass

    STARTUP_BACKUP_PATH.write_text(json.dumps(backup), encoding="utf-8")


def restore() -> None:
    _stop_dev_build()
    try:
        if BACKUP_PATH.exists():
            if BACKUP_PATH.stat().st_size == 0:
                SETTINGS_PATH.unlink(missing_ok=True)
                BACKUP_PATH.unlink()
            else:
                os.replace(BACKUP_PATH, SETTINGS_PATH)
    finally:
        _restore_startup_registration()


def _restore_startup_registration() -> None:
    """Restore the Run value even if a previous test run was interrupted."""
    if winreg is None or not STARTUP_BACKUP_PATH.exists():
        return

    backup = json.loads(STARTUP_BACKUP_PATH.read_text(encoding="utf-8"))
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, RUN_KEY, access=winreg.KEY_SET_VALUE
    ) as key:
        if backup["present"]:
            winreg.SetValueEx(
                key, RUN_VALUE_NAME, 0, int(backup["type"]), backup["value"]
            )
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE_NAME)
            except FileNotFoundError:
                pass
    STARTUP_BACKUP_PATH.unlink()


@contextmanager
def preserve_user_settings():
    """Back up user state on entry, restore on exit. Safe to nest."""
    global _depth
    if _depth == 0:
        back_up()
    _depth += 1
    try:
        yield
    finally:
        _depth -= 1
        if _depth == 0:
            restore()
