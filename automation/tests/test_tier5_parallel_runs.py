"""#382: fast runs avoid shared user state and do not adopt another checkout's ports."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from core import services, settings_guard
from tests import conftest


class CollectedItem:
    def __init__(self, *, markers=(), fixtures=(), function=None):
        self.markers = set(markers)
        self.fixturenames = list(fixtures)
        self.obj = function

    def get_closest_marker(self, name):
        return name if name in self.markers else None


def _fixture_generator(items):
    request = SimpleNamespace(session=SimpleNamespace(items=items))
    return conftest.user_settings.__wrapped__(request)


@contextmanager
def _recording_guard(events):
    events.append("guard-enter")
    try:
        yield
    finally:
        events.append("guard-exit")


def test_fast_only_session_skips_backup_restore_and_fingerprints(monkeypatch):
    events = []
    fingerprints = iter(("before", "before"))
    monkeypatch.setattr(conftest, "preserve_user_settings",
                        lambda: _recording_guard(events))
    monkeypatch.setattr(conftest, "user_state_fingerprint",
                        lambda: events.append("fingerprint") or next(fingerprints))

    fixture = _fixture_generator([CollectedItem()])
    next(fixture)
    assert events == ["fingerprint"]
    with pytest.raises(StopIteration):
        next(fixture)
    assert events == ["fingerprint", "fingerprint"]


@pytest.mark.parametrize("item", [
    CollectedItem(markers={"ui"}),
    CollectedItem(markers={"touches_user_state"}),
    CollectedItem(fixtures={"fresh_app"}),
])
def test_app_or_user_state_session_keeps_the_full_guard(monkeypatch, item):
    events = []
    monkeypatch.setattr(conftest, "preserve_user_settings",
                        lambda: _recording_guard(events))
    monkeypatch.setattr(conftest, "user_state_fingerprint",
                        lambda: pytest.fail("guarded sessions do not fingerprint"))

    fixture = _fixture_generator([item])
    next(fixture)
    assert events == ["guard-enter"]
    with pytest.raises(StopIteration):
        next(fixture)
    assert events == ["guard-enter", "guard-exit"]


def test_fast_only_session_fails_if_real_state_fingerprint_changes(monkeypatch):
    fingerprints = iter((("hash-before", None, None), ("hash-after", None, None)))
    monkeypatch.setattr(conftest, "user_state_fingerprint", lambda: next(fingerprints))
    monkeypatch.setattr(conftest, "preserve_user_settings",
                        lambda: pytest.fail("fast-only sessions do not back up state"))

    fixture = _fixture_generator([])
    next(fixture)
    with pytest.raises(pytest.fail.Exception, match="changed real FlowShield user state"):
        next(fixture)


def _registry_write_for_detector_test():
    winreg.SetValueEx(key, "FlowShield", 0, winreg.REG_SZ, "value")


def test_direct_registry_access_gets_the_full_guard_without_a_marker():
    item = CollectedItem(function=_registry_write_for_detector_test)
    assert conftest._session_needs_settings_guard([item])


class FakeRegistry:
    HKEY_CURRENT_USER = object()
    REG_SZ = 1

    def __init__(self):
        self.values = {}
        self.subkey = None

    def OpenKey(self, _root, subkey):
        self.subkey = subkey
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def QueryValueEx(self, _key, name):
        try:
            return self.values[self.subkey, name]
        except KeyError as exc:
            raise FileNotFoundError(name) from exc


def test_fingerprint_hashes_file_and_reads_only_the_two_registry_values(
    tmp_path, monkeypatch
):
    settings = tmp_path / "settings.json"
    content = b"encrypted envelope"
    settings.write_bytes(content)
    registry = FakeRegistry()
    registry.values[settings_guard.RUN_KEY, settings_guard.RUN_VALUE_NAME] = (
        r"C:\FlowShield\FlowShield.exe --start-with-windows", registry.REG_SZ
    )
    registry.values[settings_guard.TRIAL_KEY, settings_guard.TRIAL_VALUE_NAME] = (
        "2026-10-01T12:00:00Z", registry.REG_SZ
    )
    monkeypatch.setattr(settings_guard, "SETTINGS_PATH", settings)
    monkeypatch.setattr(settings_guard, "winreg", registry)

    before = settings_guard.user_state_fingerprint()
    assert before[0] == hashlib.sha256(content).hexdigest()
    assert before[1]["value"].endswith("--start-with-windows")
    assert before[2]["value"] == "2026-10-01T12:00:00Z"

    settings.write_bytes(b"another encrypted envelope")
    after = settings_guard.user_state_fingerprint()
    assert before != after


def test_custom_port_collision_fails_instead_of_adopting_another_service(
    tmp_path, monkeypatch
):
    service = services.ManagedService(
        name="license-server",
        args=[],
        cwd=tmp_path,
        port=3301,
        health_url="http://127.0.0.1:3301/health",
    )
    monkeypatch.setattr(services, "port_is_open", lambda _port: True)
    monkeypatch.setattr(service, "wait_healthy", lambda **_kwargs: True)

    with pytest.raises(RuntimeError, match="port 3301 is already in use"):
        service.start()
    assert not service.adopted
    assert service.process is None


def test_a_server_started_by_this_run_can_be_reused(tmp_path, monkeypatch):
    service = services.ManagedService(
        name="license-server",
        args=[],
        cwd=tmp_path,
        port=3301,
        health_url="http://127.0.0.1:3301/health",
    )

    class RunningProcess:
        returncode = None

        def poll(self):
            return None

    service.process = RunningProcess()
    monkeypatch.setattr(services, "port_is_open",
                        lambda _port: pytest.fail("same-run service is already tracked"))
    monkeypatch.setattr(service, "wait_healthy", lambda **_kwargs: True)

    assert service.start()


def test_manual_server_reuse_is_an_explicit_opt_in(monkeypatch):
    monkeypatch.setattr(services, "SERVER_PORT", 3000)
    monkeypatch.delenv("FLOWSHIELD_REUSE_EXISTING_SERVICES", raising=False)
    service = services.license_server()
    assert not service.allow_existing

    monkeypatch.setenv("FLOWSHIELD_REUSE_EXISTING_SERVICES", "1")
    service = services.license_server()
    monkeypatch.setattr(services, "port_is_open", lambda port: port == 3000)
    monkeypatch.setattr(service, "wait_healthy", lambda **_kwargs: True)

    assert service.allow_existing
    assert service.start()
    assert service.adopted
