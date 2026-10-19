"""
Keep the owner's real settings and Windows startup entry out of the suite's way.

The dev build and an installed Basalt share one settings file in Roaming
AppData, and the suite wipes and rewrites it constantly — leaving it pointed at
http://localhost:3000. Without this, running the tests on a machine that also
has Basalt installed quietly breaks that install's licence checks.

`preserve_user_settings()` copies the file aside before a run and puts it back
afterwards. The backup is written only once: if a previous run was killed before
restoring, the backup on disk is still the owner's file, so it is kept rather
than overwritten with whatever the dead run left behind.
All suite-launched and non-installed FlowShield processes must exit before
restore. Backups survive until the file hash and registry values stay verified
after settling; a failed restore leaves them available for recovery.

The Start-with-Windows Run value receives the same treatment because Phase 1.2
tests deliberately enable and corrupt it before checking that launch repairs it.
So does the trial record (`TrialRecord.cs`), the registry copy of the trial's
start date that outlives settings.json: clean launches delete it and
--expire-trial backdates it, and without a restore one test run would leave
the owner's own trial expired, or restarted.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
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
_launched_apps: dict[int, psutil.Process] = {}
_guard_lock_release = None
_EXIT_TIMEOUT = 10
_RESTORE_ATTEMPTS = 3
_RESTORE_SETTLE = 0.75


def launch_app_process(*args, **kwargs) -> subprocess.Popen:
    """Start and retain the identity of every suite-launched app, even mid-exit."""
    process = subprocess.Popen(*args, **kwargs)
    try:
        # Retaining Process also retains its creation time: a reused PID must
        # never turn into permission to kill an unrelated process later.
        _launched_apps[process.pid] = psutil.Process(process.pid)
    except psutil.NoSuchProcess:
        pass  # a short-lived second-instance/uninstall launch already exited
    return process


def run_app_process(args, *, timeout: float, **kwargs) -> subprocess.CompletedProcess:
    """The suite's synchronous app launches must be tracked too."""
    with launch_app_process(args, **kwargs) as process:
        try:
            returncode = process.wait(timeout=timeout)
        except BaseException:
            process.kill()
            process.wait()
            raise
    return subprocess.CompletedProcess(args, returncode)


def _is_installed(exe: str | None) -> bool:
    if not exe:
        return False
    path = Path(exe).resolve()
    roots = [Path(os.environ[name]) for name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")
             if os.environ.get(name)]
    if os.environ.get("LOCALAPPDATA"):
        roots.append(Path(os.environ["LOCALAPPDATA"]) / "FlowShield")
    return any(path.is_relative_to(root.resolve()) for root in roots)


def _stop_dev_build() -> None:
    """Stop all suite writers and confirm exit; never kill an installed copy."""
    target = os.path.normcase(str(Path(APP_EXE).resolve()))
    candidates = dict(_launched_apps)
    for proc in psutil.process_iter(["name", "exe"]):
        info = proc.info
        exe = info.get("exe")
        if ((info.get("name") or "").lower() == "flowshield.exe"
                or (exe and os.path.normcase(exe) == target)):
            candidates[proc.pid] = proc
    stopped = []
    for proc in candidates.values():
        try:
            try:
                info = getattr(proc, "info", None)
                exe = info.get("exe") if info is not None else proc.exe()
            except psutil.AccessDenied:
                exe = None
            if _is_installed(exe):
                continue
            proc.kill()
            stopped.append(proc)
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as exc:
            raise RuntimeError(f"Cannot stop app PID {proc.pid}; backups retained") from exc
    for proc in stopped:
        try:
            proc.wait(timeout=_EXIT_TIMEOUT)
        except psutil.NoSuchProcess:
            pass
        except (psutil.TimeoutExpired, psutil.AccessDenied) as exc:
            raise RuntimeError(f"Cannot confirm exit of app PID {proc.pid}; backups retained") from exc
    _launched_apps.clear()


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

    backup = _read_registry_value(subkey, name)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(json.dumps(backup), encoding="utf-8")


def _read_registry_value(subkey: str, name: str) -> dict:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
            value, value_type = winreg.QueryValueEx(key, name)
            return {"present": True, "value": value, "type": value_type}
    except FileNotFoundError:
        return {"present": False, "value": None, "type": winreg.REG_SZ}


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


def _back_up_startup_registration() -> None:
    """Persist the real Run value before a test is allowed to change it."""
    _back_up_registry_value(RUN_KEY, RUN_VALUE_NAME, STARTUP_BACKUP_PATH)


def _back_up_trial_record() -> None:
    """Persist the owner's real trial start before a test clears or backdates it."""
    _back_up_registry_value(TRIAL_KEY, TRIAL_VALUE_NAME, TRIAL_BACKUP_PATH)


def user_state_fingerprint() -> tuple:
    """Hash real settings and read the two guarded HKCU values without changing them."""
    settings_hash = (hashlib.sha256(SETTINGS_PATH.read_bytes()).hexdigest()
                     if SETTINGS_PATH.exists() else None)
    if winreg is None:
        return settings_hash, None, None
    return (
        settings_hash,
        _read_registry_value(RUN_KEY, RUN_VALUE_NAME),
        _read_registry_value(TRIAL_KEY, TRIAL_VALUE_NAME),
    )


def _acquire_cross_process_lock():
    """Serialize guarded sessions across worktrees without leaving an AppData file."""
    identity = os.path.normcase(str(SETTINGS_PATH.resolve())).encode("utf-8")
    lock_name = hashlib.sha256(identity).hexdigest()

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
        kernel32.ReleaseMutex.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateMutexW(
            # Local\ is enough: the guarded state is per user. Global\ can need
            # SeCreateGlobalPrivilege, which a standard user doesn't have.
            None, False, rf"Local\FlowShield.SettingsGuard.{lock_name}"
        )
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())

        wait_result = kernel32.WaitForSingleObject(handle, 0)
        if wait_result == 0x00000102:  # WAIT_TIMEOUT
            print("Another guarded FlowShield test session is running; waiting.")
            wait_result = kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
        if wait_result not in (0x00000000, 0x00000080):  # OBJECT_0 / ABANDONED
            error = ctypes.WinError(ctypes.get_last_error())
            kernel32.CloseHandle(handle)
            raise error

        def release():
            try:
                if not kernel32.ReleaseMutex(handle):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                kernel32.CloseHandle(handle)

        return release

    import fcntl

    lock_dir = Path(tempfile.gettempdir()) / "FlowShield"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"settings-guard-{lock_name}.lock"
    handle = open(lock_path, "a+b")
    waiting = False
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if not waiting:
                print("Another guarded FlowShield test session is running; waiting.")
                waiting = True
            time.sleep(0.25)

    def release():
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    return release


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
    pending = [p for p in (BACKUP_PATH, STARTUP_BACKUP_PATH, TRIAL_BACKUP_PATH)
               if p.exists() and (p == BACKUP_PATH or winreg is not None)]
    expected_hash = (hashlib.sha256(BACKUP_PATH.read_bytes()).digest()
                     if BACKUP_PATH in pending and BACKUP_PATH.stat().st_size else None)
    last_error = None
    for _ in range(_RESTORE_ATTEMPTS):
        # A late relaunch must also be stopped before a retry. A stop/wait
        # failure aborts without touching the owner's backups or live state.
        _stop_dev_build()
        if not pending:
            return
        try:
            try:
                if BACKUP_PATH in pending:
                    if expected_hash is None:
                        SETTINGS_PATH.unlink(missing_ok=True)
                    else:
                        shutil.copy2(BACKUP_PATH, SETTINGS_PATH)
            finally:
                try:
                    _restore_startup_registration()
                finally:
                    _restore_trial_record()
            time.sleep(_RESTORE_SETTLE)
            file_matches = (BACKUP_PATH not in pending or
                            (not SETTINGS_PATH.exists() if expected_hash is None else
                             hashlib.sha256(SETTINGS_PATH.read_bytes()).digest() == expected_hash))
            registry_matches = all(
                _read_registry_value(subkey, name) == json.loads(path.read_text(encoding="utf-8"))
                for subkey, name, path in ((RUN_KEY, RUN_VALUE_NAME, STARTUP_BACKUP_PATH),
                                          (TRIAL_KEY, TRIAL_VALUE_NAME, TRIAL_BACKUP_PATH))
                if path in pending
            )
            if file_matches and registry_matches:
                for path in pending:
                    path.unlink()
                return
        except OSError as exc:
            last_error = exc
    raise RuntimeError(f"Restore verification failed after {_RESTORE_ATTEMPTS} attempts; "
                       f"backups retained in {BACKUP_PATH.parent}") from last_error


def _restore_startup_registration() -> None:
    """Restore the Run value even if a previous test run was interrupted."""
    _restore_registry_value(RUN_KEY, RUN_VALUE_NAME, STARTUP_BACKUP_PATH)


def _restore_trial_record() -> None:
    """Restore the owner's trial start even if a previous test run was interrupted."""
    _restore_registry_value(TRIAL_KEY, TRIAL_VALUE_NAME, TRIAL_BACKUP_PATH)


@contextmanager
def preserve_user_settings():
    """Back up user state on entry, restore on exit, and serialize guarded runs."""
    global _depth, _guard_lock_release
    if _depth == 0:
        release_lock = _acquire_cross_process_lock()
        try:
            back_up()
        except BaseException:
            release_lock()
            raise
        _guard_lock_release = release_lock
    _depth += 1
    try:
        yield
    finally:
        _depth -= 1
        if _depth == 0:
            try:
                restore()
            finally:
                release_lock = _guard_lock_release
                _guard_lock_release = None
                if release_lock is not None:
                    release_lock()
