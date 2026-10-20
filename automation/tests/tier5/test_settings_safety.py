# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: settings safety."""

from __future__ import annotations
import os
from pathlib import Path
import pytest
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from ._helpers import _FakeWinreg



# ============ user data must not live inside the install directory

class TestSettingsLocation:
    """
    The installer puts the application in %LOCALAPPDATA%\\FlowShield. Settings
    kept there would sit inside the install directory, where an update or
    uninstall could delete them — taking the customer's licence key with them.
    """

    def test_settings_are_not_in_the_install_directory(self):
        from config import SETTINGS_PATH

        local = os.environ.get("LOCALAPPDATA", "").lower()
        assert local, "LOCALAPPDATA is not set"
        assert not str(SETTINGS_PATH).lower().startswith(local), (
            f"settings live at {SETTINGS_PATH}, inside the installer's directory"
        )

    def test_the_app_writes_to_roaming_appdata(self):
        source = (Path(DESKTOP_DIR) / "Services" / "SettingsService.cs").read_text(
            encoding="utf-8")
        ctor = source.split("public SettingsService(")[1].split("\n    }")[0]
        assert "SpecialFolder.ApplicationData" in ctor, \
            "settings must be written to Roaming AppData, not Local"
        assert "LocalApplicationData" not in ctor, \
            "the constructor should no longer default to LocalAppData"

    def test_old_settings_are_migrated_not_abandoned(self):
        """An early adopter must not appear to lose their licence on upgrade."""
        source = (Path(DESKTOP_DIR) / "Services" / "SettingsService.cs").read_text(
            encoding="utf-8")
        assert "MigrateFromLegacyLocation" in source
        migrate = source.split("private void MigrateFromLegacyLocation()")[1].split("\n    }")[0]
        assert "File.Copy" in migrate, \
            "migration should copy, so a failure leaves the original intact"


# ============ a test run must not rewrite the owner's installed app

class TestSuiteLeavesUserSettingsAlone:
    """
    The dev build and an installed Basalt share one settings file. The
    suite wiped and rewrote it and never put it back, so after a run on the
    owner's machine their installed copy was pointed at http://localhost:3000.
    """

    @pytest.fixture
    def guard(self, tmp_path, monkeypatch):
        from core import settings_guard

        settings = tmp_path / "settings.json"
        monkeypatch.setattr(settings_guard, "SETTINGS_PATH", settings)
        monkeypatch.setattr(settings_guard, "BACKUP_PATH",
                            settings.with_name("settings.json.pre-tests"))
        monkeypatch.setattr(settings_guard, "_stop_dev_build", lambda: None)
        # These tests exercise file preservation in isolation; the session's
        # outer guard separately protects the real Windows Run value.
        monkeypatch.setattr(settings_guard, "winreg", None)
        return settings_guard

    def test_existing_settings_come_back_byte_for_byte(self, guard):
        guard.SETTINGS_PATH.write_bytes(b"owner's envelope")
        guard.back_up()
        guard.SETTINGS_PATH.write_bytes(b"left behind by a test")
        guard.restore()

        assert guard.SETTINGS_PATH.read_bytes() == b"owner's envelope"
        assert not guard.BACKUP_PATH.exists()

    def test_no_settings_before_means_none_after(self, guard):
        guard.back_up()
        guard.SETTINGS_PATH.write_bytes(b"left behind by a test")
        guard.restore()

        assert not guard.SETTINGS_PATH.exists()
        assert not guard.BACKUP_PATH.exists()

    def test_an_interrupted_run_does_not_overwrite_the_backup(self, guard):
        """A killed run never restored; the next run must not back up its debris."""
        guard.SETTINGS_PATH.write_bytes(b"owner's envelope")
        guard.back_up()
        guard.SETTINGS_PATH.write_bytes(b"left behind by a killed run")

        guard.back_up()
        guard.restore()

        assert guard.SETTINGS_PATH.read_bytes() == b"owner's envelope"

    def test_every_entry_point_that_launches_the_app_is_guarded(self):
        """
        Found by scanning, not by a list. The F27 capture scripts launched the
        app and seeded invented sample data straight into settings.json while
        this test was still naming four files by hand, so the rule missed them.
        """
        import ast

        def calls_launch_app(source: str) -> bool:
            """
            Parsed, not grepped: make_report.py explains launch_app() in a
            docstring without ever calling it.
            """
            try:
                tree = ast.parse(source)
            except SyntaxError:
                return False
            return any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "launch_app"
                for node in ast.walk(tree)
            )

        automation = Path(__file__).resolve().parents[2]
        launchers = sorted(
            path for path in automation.rglob("*.py")
            if "tests" not in path.parts
            and path.name != "app_controller.py"  # where launch_app is defined
            and calls_launch_app(path.read_text(encoding="utf-8"))
        )
        assert len(launchers) >= 4, "the scan found almost nothing — check it still works"
        for script in launchers:
            source = script.read_text(encoding="utf-8")
            assert "with preserve_user_settings():" in source, \
                f"{script.name} launches the app but doesn't preserve the owner's settings"
        conftest = (automation / "tests" / "conftest.py").read_text(encoding="utf-8")
        assert "autouse=True" in conftest and "preserve_user_settings()" in conftest

    def test_the_startup_entry_is_also_backed_up_and_restored(self):
        guard = (Path(__file__).resolve().parents[2] / "core" /
                 "settings_guard.py").read_text(encoding="utf-8")
        assert "_back_up_startup_registration()" in guard
        assert "_restore_startup_registration()" in guard
        assert 'RUN_VALUE_NAME = "FlowShield"' in guard


class TestSettingsReadRacesTheAtomicWrite:
    """
    SettingsService writes a .tmp and File.Replace()s it into place. During the
    replace the destination cannot be opened, and a test reading settings right
    after an action is reading inside that window by design. The reader retries;
    the writer stays atomic.
    """

    def test_the_writer_still_replaces_atomically(self):
        service = (Path(DESKTOP_DIR) / "Services" / "SettingsService.cs").read_text(
            encoding="utf-8")
        assert "File.Replace(temp, SettingsPath, null)" in service, (
            "settings must still be written atomically; the reader's retry is "
            "not a licence to write in place"
        )

    def test_a_locked_file_is_retried_then_raises(self, tmp_path, monkeypatch):
        from core import state_verifier

        target = tmp_path / "settings.json"
        target.write_text("{}", encoding="utf-8")

        calls = {"n": 0}
        real = Path.read_text

        def flaky(self, *args, **kwargs):
            if self == target:
                calls["n"] += 1
                if calls["n"] < 3:
                    raise PermissionError(13, "Permission denied")
            return real(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", flaky)
        assert state_verifier._read_past_a_replace(target) == "{}"
        assert calls["n"] == 3, "the read should have been retried, not passed through"

    def test_it_gives_up_rather_than_hanging(self, tmp_path, monkeypatch):
        target = tmp_path / "settings.json"
        target.write_text("{}", encoding="utf-8")

        from core import state_verifier

        monkeypatch.setattr(
            Path, "read_text",
            lambda self, *a, **k: (_ for _ in ()).throw(PermissionError(13, "denied")))
        with pytest.raises(PermissionError):
            state_verifier._read_past_a_replace(target, timeout=0.2)


# ==================================================== #202 settings save race

class TestSettingsSaveRaceRegression:
    """
    #202: SettingsService.Save serialized the live, shared AppSettings
    instance straight from whichever thread called it. The `_gate` lock only
    ever kept two writers from interleaving each other's file I/O; it did
    nothing about a *reader* of `settings.Sessions` (Save's own serializer)
    racing a writer of it. The concrete path: App.OnStartup fires
    `licenseService.RefreshAsync(...)` without awaiting it, and its eventual
    `_settings.Save(settings)` could reach `JsonSerializer.Serialize` at the
    same moment `TodayViewModel.EndSprint` ran `S.Sessions.Add(_current)` on
    the UI thread -- a `List<T>` mutated during enumeration throws
    "Collection was modified", which both `ValidateAsync` and `RefreshAsync`
    swallow in a general catch, so the file is never written and the
    just-finished sprint (its momentum, its streak day) is lost silently.

    There is no dotnet test project in this repo (CLAUDE.md: the pytest suite
    *is* the test suite), and a genuine cross-thread data race is not
    something this harness can drive deterministically against C# without
    running the compiled app for minutes under contrived timing -- exactly
    what the UI-test ban this repo has (see CLAUDE.md "Never run the UI
    tests") rules out here. So this pins the fix by source: every path that
    used to call `_settings.Save(settings)` straight from a background
    continuation must now go through the single, UI-thread-marshalling
    choke point, and Save itself must never hand the live object to the
    serializer.

    Proven to fail first: reverting LicenseService.cs's three call sites to
    their pre-fix form --
        settings.IsPro = true; ...; _settings.Save(settings);
    -- with no MutateAndSave wrapper (and/or reverting SettingsService.Save
    to `JsonSerializer.Serialize(settings, JsonOpts)` with no snapshot)
    fails every assertion below; the current source passes all of them.
    """

    LICENSE_SERVICE = (Path(DESKTOP_DIR) / "Services" / "LicenseService.cs").read_text(
        encoding="utf-8")
    SETTINGS_SERVICE = (Path(DESKTOP_DIR) / "Services" / "SettingsService.cs").read_text(
        encoding="utf-8")
    TODAY_VM = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(
        encoding="utf-8")

    def test_the_sprint_that_exposed_the_race_is_still_saved_before_the_add(self):
        """
        Sanity check on the scenario itself: EndSprint really does add to the
        live, shared Sessions list on the UI thread, which is what makes a
        concurrent background Save dangerous in the first place.
        """
        assert "S.Sessions.Add(_current)" in self.TODAY_VM

    def test_no_settings_mutation_reaches_save_without_going_through_the_guard(self):
        """
        The three places a background license verdict used to mutate
        `settings` and save it inline (activation, a downgrade on refresh,
        deactivation) must all route through MutateAndSave, which marshals
        onto the UI thread first -- the same thread every other mutator of
        AppSettings already runs on.
        """
        assert "private void MutateAndSave(AppSettings settings, Action<AppSettings> mutate)" \
            in self.LICENSE_SERVICE

        # None of the three verdict paths may set settings.IsPro and then
        # save without going through the guard in between.
        for marker in (
            "s.IsPro = true;",      # ValidateAsync: activation
            "s.IsPro = false;",     # RefreshAsync's downgrade / DeactivateAsync
        ):
            assert marker in self.LICENSE_SERVICE, \
                f"expected mutation {marker!r} inside a MutateAndSave callback"

        # And the old inline pattern -- mutate settings.* directly, then call
        # _settings.Save(settings) in the same block -- must be gone.
        assert "settings.IsPro = true;" not in self.LICENSE_SERVICE, \
            "IsPro must be set inside MutateAndSave's callback (on `s`), " \
            "not on the live `settings` reference outside it"

    def test_the_dispatcher_marshal_actually_blocks_until_saved(self):
        """
        Dispatcher.Invoke (not BeginInvoke/PostAsJsonAsync-style fire-and-
        forget) is required: the code right after MutateAndSave reads
        settings.LicenseStatus/DeviceCount back out for logging and the
        returned LicenseResult, which only works if the save has already
        happened by the time MutateAndSave returns.
        """
        method = self.LICENSE_SERVICE.split("private void MutateAndSave(")[1].split(
            "\n    }")[0]
        assert "dispatcher.Invoke(" in method
        assert "BeginInvoke" not in method, \
            "a fire-and-forget marshal would let ValidateAsync read " \
            "settings.LicenseStatus before the mutation actually happened"

    def test_save_never_serializes_the_live_object_directly(self):
        save = self.SETTINGS_SERVICE.split("public void Save(AppSettings settings)")[1]
        assert "settings.Clone()" in save.split("lock (_gate)")[0], \
            "Save must snapshot with Clone() before the locked section, so " \
            "nothing after this point ever reads the object another thread " \
            "might still be mutating"
        assert "JsonSerializer.Serialize(settings, JsonOpts)" not in save


class TestTheSuiteLeavesTheOwnersTrialAlone:
    """
    Clean launches delete the trial record and --expire-trial backdates it.
    Without a restore, one test run would leave the owner's real trial
    expired, or restarted.
    """

    @pytest.fixture
    def guard(self, tmp_path, monkeypatch):
        from core import settings_guard

        settings = tmp_path / "settings.json"
        monkeypatch.setattr(settings_guard, "SETTINGS_PATH", settings)
        monkeypatch.setattr(settings_guard, "BACKUP_PATH", tmp_path / "settings.json.pre-tests")
        monkeypatch.setattr(settings_guard, "STARTUP_BACKUP_PATH", tmp_path / "startup.pre-tests.json")
        monkeypatch.setattr(settings_guard, "TRIAL_BACKUP_PATH", tmp_path / "trial.pre-tests.json")
        monkeypatch.setattr(settings_guard, "_stop_dev_build", lambda: None)
        fake = _FakeWinreg()
        monkeypatch.setattr(settings_guard, "winreg", fake)
        return settings_guard, fake

    def key(self, guard):
        return (guard.TRIAL_KEY, guard.TRIAL_VALUE_NAME)

    def test_the_owners_trial_start_comes_back(self, guard):
        guard, fake = guard
        fake.values[self.key(guard)] = ("2026-09-30T10:00:00.0000000Z", fake.REG_SZ)
        guard.back_up()
        guard.clear_trial_record()
        assert self.key(guard) not in fake.values
        fake.values[self.key(guard)] = ("2026-09-01T00:00:00.0000000Z", fake.REG_SZ)  # --expire-trial
        guard.restore()
        assert fake.values[self.key(guard)] == ("2026-09-30T10:00:00.0000000Z", fake.REG_SZ)
        assert not guard.TRIAL_BACKUP_PATH.exists()

    def test_no_record_before_means_none_after(self, guard):
        guard, fake = guard
        guard.back_up()
        fake.values[self.key(guard)] = ("2026-10-05T00:00:00.0000000Z", fake.REG_SZ)
        guard.restore()
        assert self.key(guard) not in fake.values

    def test_an_interrupted_run_keeps_the_first_backup(self, guard):
        guard, fake = guard
        fake.values[self.key(guard)] = ("owner's", fake.REG_SZ)
        guard.back_up()
        fake.values[self.key(guard)] = ("left by a killed run", fake.REG_SZ)
        guard.back_up()
        guard.restore()
        assert fake.values[self.key(guard)] == ("owner's", fake.REG_SZ)
