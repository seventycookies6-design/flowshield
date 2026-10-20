"""#376: exercise the real restore against late writers, without an app or screen."""

import psutil
import pytest

from core import settings_guard
from tests.tier5._helpers import _FakeWinreg


@pytest.fixture
def guard(tmp_path, monkeypatch):
    for name, filename in (
        ("SETTINGS_PATH", "settings.json"),
        ("BACKUP_PATH", "settings.json.pre-tests"),
        ("STARTUP_BACKUP_PATH", "startup.pre-tests.json"),
        ("TRIAL_BACKUP_PATH", "trial.pre-tests.json"),
    ):
        monkeypatch.setattr(settings_guard, name, tmp_path / filename)
    monkeypatch.setattr(settings_guard, "winreg", _FakeWinreg())
    monkeypatch.setattr(settings_guard, "_launched_apps", {}, raising=False)
    monkeypatch.setattr(settings_guard.psutil, "process_iter", lambda *a: iter(()))
    monkeypatch.setattr(settings_guard.time, "sleep", lambda seconds: None)
    settings_guard.SETTINGS_PATH.write_bytes(b'{"owner-marker":"unique-376"}\r\n')
    for subkey, name in registry_keys(settings_guard):
        settings_guard.winreg.values[subkey, name] = ("owner's " + name, 1)
    return settings_guard


def registry_keys(guard):
    return ((guard.TRIAL_KEY, guard.TRIAL_VALUE_NAME), (guard.RUN_KEY, guard.RUN_VALUE_NAME))


def backups(guard):
    return (guard.BACKUP_PATH, guard.TRIAL_BACKUP_PATH, guard.STARTUP_BACKUP_PATH)


class LateWriter:
    """kill requests exit; a queued save can finish until wait confirms exit."""

    pid = 376

    def __init__(self, guard, exe, name="FlowShield.exe"):
        self.guard = guard
        self.info = {"name": name, "exe": exe}
        self.killed = False
        self.exited = False

    def kill(self):
        self.killed = True

    def save(self):
        self.guard.SETTINGS_PATH.write_bytes(b"late test save")
        for key in registry_keys(self.guard):
            self.guard.winreg.values[key] = ("late test save", 1)

    def wait(self, timeout):
        assert timeout > 0
        assert self.killed, "must request exit before waiting"
        self.save()
        self.exited = True


@pytest.mark.parametrize("identity", ("exact", "other-worktree", "unreadable", "tracked-only"))
def test_restore_waits_for_every_suite_writer_before_copying_back(guard, monkeypatch, identity):
    exe = str(guard.APP_EXE.resolve()) if identity == "exact" else r"C:\other-checkout\FlowShield.exe"
    if identity == "unreadable":
        exe = None  # process_iter's default for an AccessDenied exe read
    writer = LateWriter(guard, exe)
    guard.back_up()
    owner = guard.SETTINGS_PATH.read_bytes()
    registry = guard.winreg.values.copy()
    writer.save()
    if identity == "tracked-only":
        guard._launched_apps[writer.pid] = writer
    else:
        monkeypatch.setattr(guard.psutil, "process_iter", lambda *a: iter((writer,)))

    guard.restore()
    if not writer.exited:
        writer.save()  # the old guard returned while this save could still land
    assert guard.SETTINGS_PATH.read_bytes() == owner
    assert guard.winreg.values == registry
    assert writer.exited, "restore must confirm process exit, not sleep and hope"
    assert all(not path.exists() for path in backups(guard))


@pytest.mark.parametrize("resource", ("settings", "trial", "run"))
@pytest.mark.parametrize("present", (True, False))
def test_restore_retries_late_changes_and_keeps_all_backups_until_verified(
    guard, monkeypatch, resource, present
):
    if not present:
        guard.SETTINGS_PATH.unlink()
        guard.winreg.values.clear()
    owner = guard.SETTINGS_PATH.read_bytes() if present else None
    registry = guard.winreg.values.copy()
    guard.back_up()
    snapshots = {p: p.read_bytes() for p in backups(guard)}
    settles = []

    def settle(seconds):
        settles.append(seconds)
        assert all(p.read_bytes() == data for p, data in snapshots.items()), "backup consumed before verification"
        if len(settles) == 1:
            corrupt(guard, resource)

    monkeypatch.setattr(guard.time, "sleep", settle)
    guard.restore()
    assert len(settles) == 2, "a late save must be detected and restored again"
    assert (guard.SETTINGS_PATH.read_bytes() if guard.SETTINGS_PATH.exists() else None) == owner
    assert guard.winreg.values == registry
    assert all(not path.exists() for path in backups(guard))


def corrupt(guard, resource):
    if resource == "settings":
        # Same length: comparing size instead of hashing must not pass.
        guard.SETTINGS_PATH.write_bytes(b"x" * len(b'{"owner-marker":"unique-376"}\r\n'))
    else:
        key = registry_keys(guard)[0 if resource == "trial" else 1]
        # Also check the registry type, not only the string contents.
        value = guard.winreg.values.get(key, ("late", 1))[0]
        guard.winreg.values[key] = (value, 2)


@pytest.mark.parametrize("resource", ("settings", "trial", "run"))
def test_restore_fails_loudly_with_intact_backups_if_a_writer_keeps_winning(guard, monkeypatch, resource):
    guard.back_up()
    snapshots = {p: p.read_bytes() for p in backups(guard)}
    monkeypatch.setattr(guard.time, "sleep", lambda seconds: corrupt(guard, resource))
    with pytest.raises(RuntimeError, match="(?i)backups.*(kept|retained)"):
        guard.restore()
    assert all(p.read_bytes() == data for p, data in snapshots.items())


@pytest.mark.parametrize("failure", (psutil.TimeoutExpired(1, pid=376), psutil.AccessDenied(pid=376)))
def test_unconfirmed_exit_aborts_restore_and_retains_backups(guard, monkeypatch, failure):
    writer = LateWriter(guard, str(guard.APP_EXE.resolve()))
    guard.back_up()
    snapshots = {p: p.read_bytes() for p in backups(guard)}
    writer.save()
    monkeypatch.setattr(guard.psutil, "process_iter", lambda *a: iter((writer,)))

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(writer, "wait" if isinstance(failure, psutil.TimeoutExpired) else "kill", fail)
    with pytest.raises(RuntimeError, match="(?i)backups.*(kept|retained)"):
        guard.restore()
    assert guard.SETTINGS_PATH.read_bytes() == b"late test save", "must not restore while a writer can still run"
    assert all(p.read_bytes() == data for p, data in snapshots.items())


@pytest.mark.parametrize("root", ("LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)"))
def test_installed_copies_are_never_killed(guard, monkeypatch, tmp_path, root):
    monkeypatch.setenv(root, str(tmp_path / root))
    install = tmp_path / root
    if root == "LOCALAPPDATA":
        install /= "FlowShield"
    writer = LateWriter(guard, str(install / "current" / "FlowShield.exe"))
    monkeypatch.setattr(guard.psutil, "process_iter", lambda *a: iter((writer,)))
    guard._stop_dev_build()
    assert not writer.killed


def test_launches_are_tracked_even_when_the_process_scan_cannot_find_them(guard, monkeypatch):
    writer = LateWriter(guard, None, name=None)
    monkeypatch.setattr(guard.psutil, "Process", lambda pid: writer)
    monkeypatch.setattr(guard.subprocess, "Popen", lambda *a, **kw: writer)
    process = guard.launch_app_process([str(guard.APP_EXE)])
    assert process.pid == writer.pid
    guard._stop_dev_build()
    assert writer.killed and writer.exited


def test_controller_launch_registers_the_process_without_touching_the_screen(guard, monkeypatch, tmp_path):
    from desktop import app_controller

    exe = tmp_path / "FlowShield.exe"
    exe.touch()
    monkeypatch.setattr(app_controller, "APP_EXE", exe)
    writer = LateWriter(guard, None)
    monkeypatch.setattr(guard.psutil, "Process", lambda pid: writer)
    monkeypatch.setattr(guard.subprocess, "Popen", lambda *a, **kw: writer)
    ctrl = app_controller.DesktopController()
    monkeypatch.setattr(ctrl, "kill_stray_instances", lambda: 0)
    assert ctrl.launch_app(clean_state=False) == writer.pid
    guard._stop_dev_build()
    assert writer.killed and writer.exited


@pytest.mark.parametrize("times_out", (False, True))
def test_synchronous_launches_are_tracked_and_timeouts_are_reaped(guard, monkeypatch, times_out):
    import subprocess

    writer = LateWriter(guard, None)

    class Child:
        pid = writer.pid
        waits = 0
        killed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def wait(self, timeout=None):
            self.waits += 1
            if times_out and self.waits == 1:
                raise subprocess.TimeoutExpired("fake-app", timeout)
            return 17

        def kill(self):
            self.killed = True

    child = Child()
    monkeypatch.setattr(guard.psutil, "Process", lambda pid: writer)
    monkeypatch.setattr(guard.subprocess, "Popen", lambda *a, **kw: child)
    if times_out:
        with pytest.raises(subprocess.TimeoutExpired):
            guard.run_app_process([str(guard.APP_EXE)], timeout=1)
        assert child.killed and child.waits == 2
    else:
        assert guard.run_app_process([str(guard.APP_EXE)], timeout=1).returncode == 17
    assert guard._launched_apps[child.pid] is writer


def test_installed_directory_prefixes_do_not_exempt_another_dev_copy(guard, monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    writer = LateWriter(guard, str(tmp_path / "FlowShield-dev" / "FlowShield.exe"))
    monkeypatch.setattr(guard.psutil, "process_iter", lambda *a: iter((writer,)))
    guard._stop_dev_build()
    assert writer.killed and writer.exited


def test_direct_app_launches_cannot_bypass_tracking():
    """Cover the controller and synchronous second-instance/uninstall paths."""
    import ast
    from pathlib import Path

    automation = Path(__file__).resolve().parent.parent
    found = []
    for path in automation.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess"
                    and node.func.attr in ("Popen", "run", "call", "check_call", "check_output")
                    and any(isinstance(n, ast.Name) and n.id == "APP_EXE"
                            for arg in node.args for n in ast.walk(arg))):
                found.append(f"{path.name}:{node.lineno}")
    assert not found, f"app launches bypass process tracking: {found}"
