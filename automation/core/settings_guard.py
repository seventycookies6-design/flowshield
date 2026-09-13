"""
Keep the owner's real settings out of the suite's way.

The dev build and an installed FlowShield share one settings file in Roaming
AppData, and the suite wipes and rewrites it constantly — leaving it pointed at
http://localhost:3000. Without this, running the tests on a machine that also
has FlowShield installed quietly breaks that install's licence checks.

`preserve_user_settings()` copies the file aside before a run and puts it back
afterwards. The backup is written only once: if a previous run was killed before
restoring, the backup on disk is still the owner's file, so it is kept rather
than overwritten with whatever the dead run left behind.
"""

from __future__ import annotations

import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

import psutil

from config import APP_EXE, SETTINGS_PATH

BACKUP_PATH = SETTINGS_PATH.with_name(SETTINGS_PATH.name + ".pre-tests")

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
    if BACKUP_PATH.exists():
        return
    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SETTINGS_PATH.exists():
        shutil.copy2(SETTINGS_PATH, BACKUP_PATH)
    else:
        BACKUP_PATH.write_bytes(_NO_SETTINGS)


def restore() -> None:
    if not BACKUP_PATH.exists():
        return
    _stop_dev_build()
    if BACKUP_PATH.stat().st_size == 0:
        SETTINGS_PATH.unlink(missing_ok=True)
        BACKUP_PATH.unlink()
    else:
        os.replace(BACKUP_PATH, SETTINGS_PATH)


@contextmanager
def preserve_user_settings():
    """Back up settings on entry, restore on exit. Safe to nest."""
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
