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
So does the trial record (`TrialRecord.cs`), the registry copy of the trial's
start date that outlives settings.json: clean launches delete it and
--expire-trial backdates it, and without a restore one test run would leave
the owner's own trial expired, or restarted.
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
TRIAL_BACKUP_PATH = SETTINGS_PATH.with_name("trial-record.pre-tests.json")
TRIAL_KEY = r"Software\FlowShield\Trial"
TRIAL_VALUE_NAME = "StartedUtc"

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
    _back_up_trial_record()


def _back_up_registry_value(subkey: str, name: str, backup_path: Path) -> None:
    """Persist one HKCU value before a test may change it; a kept backup wins."""
    if winreg is None or backup_path.exists():
        return

    backup = {"present": False, "value": None, "type": winreg.REG_SZ}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
            value, value_type = winreg.QueryValueEx(key, name)
            backup = {"present": True, "value": value, "type": value_type}
    except FileNotFoundError:
        pass

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(json.dumps(backup), encoding="utf-8")


def _restore_registry_value(subkey: str, name: str, backup_path: Path) -> None:
    """Put one HKCU value back, or remove it if there was none before."""
    if winreg is None or not backup_path.exists():
        return

    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, subkey, access=winreg.KEY_SET_VALUE
    ) as key:
        if backup["present"]:
            winreg.SetValueEx(key, name, 0, int(backup["type"]), backup["value"])
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
    backup_path.unlink()


def _back_up_startup_registration() -> None:
    """Persist the real Run value before a test is allowed to change it."""
    _back_up_registry_value(RUN_KEY, RUN_VALUE_NAME, STARTUP_BACKUP_PATH)


def _back_up_trial_record() -> None:
    """Persist the owner's real trial start before a test clears or backdates it."""
    _back_up_registry_value(TRIAL_KEY, TRIAL_VALUE_NAME, TRIAL_BACKUP_PATH)


def clear_trial_record() -> None:
    """
    Remove the trial record, for a launch that must look like a clean install.
    Only ever called inside preserve_user_settings(), which puts it back.
    """
    if winreg is None:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TRIAL_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, TRIAL_VALUE_NAME)
    except FileNotFoundError:
        pass


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
        try:
            _restore_startup_registration()
        finally:
            _restore_trial_record()


def _restore_startup_registration() -> None:
    """Restore the Run value even if a previous test run was interrupted."""
    _restore_registry_value(RUN_KEY, RUN_VALUE_NAME, STARTUP_BACKUP_PATH)


def _restore_trial_record() -> None:
    """Restore the owner's trial start even if a previous test run was interrupted."""
    _restore_registry_value(TRIAL_KEY, TRIAL_VALUE_NAME, TRIAL_BACKUP_PATH)


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
