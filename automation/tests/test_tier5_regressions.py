"""
Tier 5 — regressions.

One test per bug found by reading the code rather than by running it. Each was
written to fail against the behaviour that shipped, so the suite would have
caught the bug had it existed first.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import psutil
import pytest
import requests

from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from core import state_verifier as verify

NODE = r"C:\Program Files\nodejs\node.exe"
NODE_EXE = NODE if Path(NODE).exists() else "node"


# ====================== the app uses one branded icon system everywhere

class TestBrandedAppIcon:
    REQUIRED_SIZES = {16, 20, 24, 32, 40, 48, 64, 128, 256}

    @staticmethod
    def icon_sizes(path: Path) -> set[int]:
        data = path.read_bytes()
        reserved, image_type, count = struct.unpack_from("<HHH", data)
        assert (reserved, image_type) == (0, 1), f"{path.name} is not a Windows icon"
        return {
            data[6 + index * 16] or 256
            for index in range(count)
        }

    def test_idle_and_running_icons_have_all_required_sizes(self):
        assets = Path(DESKTOP_DIR) / "Assets"
        idle = assets / "FlowShield.ico"
        running = assets / "FlowShield.Running.ico"

        assert self.icon_sizes(idle) == self.REQUIRED_SIZES
        assert self.icon_sizes(running) == self.REQUIRED_SIZES
        assert idle.read_bytes() != running.read_bytes(), \
            "the running tray state must be visually distinct"

    def test_app_window_and_installer_use_the_brand_icon(self):
        project = (Path(DESKTOP_DIR) / "FlowShield.csproj").read_text(encoding="utf-8")
        window = (Path(DESKTOP_DIR) / "MainWindow.xaml").read_text(encoding="utf-8-sig")
        pack = (Path(DESKTOP_DIR).parent / "tools" / "build_release.ps1").read_text(
            encoding="utf-8")

        assert r"<ApplicationIcon>Assets\FlowShield.ico</ApplicationIcon>" in project
        assert 'Icon="Assets/FlowShield.ico"' in window
        assert "--icon 'DesktopApp\\Assets\\FlowShield.ico'" in pack

    def test_tray_switches_to_the_running_variant_and_disposes_both(self):
        window = (Path(DESKTOP_DIR) / "MainWindow.xaml.cs").read_text(encoding="utf-8")

        assert 'LoadIcon("FlowShield.ico")' in window
        assert 'LoadIcon("FlowShield.Running.ico")' in window
        assert "Vm?.Today.IsRunning == true ? _trayRunningIcon : _trayIdleIcon" in window
        assert "nameof(TodayViewModel.IsRunning)" in window
        assert "_trayIdleIcon?.Dispose()" in window
        assert "_trayRunningIcon?.Dispose()" in window
        assert "SystemIcons.Shield" not in window


# ======================== Windows startup stays quiet and current

class TestStartWithWindowsSource:
    """The sign-in command used to promise --tray while startup ignored it."""

    def test_tray_argument_selects_hidden_startup(self):
        app = (Path(DESKTOP_DIR) / "App.xaml.cs").read_text(encoding="utf-8")

        assert 'a.Equals("--tray", StringComparison.OrdinalIgnoreCase)' in app
        assert "window.StartInTray()" in app
        assert "ShutdownMode.OnExplicitShutdown" in app

    def test_the_tray_icon_is_made_visible_without_showing_the_window(self):
        window = (Path(DESKTOP_DIR) / "MainWindow.xaml.cs").read_text(encoding="utf-8")
        start_in_tray = window.split("public bool StartInTray()", 1)[1].split(
            "\n    }", 1
        )[0]

        assert "_tray.Visible = true" in start_in_tray
        assert "Show();" not in start_in_tray

    def test_only_an_installed_copy_refreshes_an_enabled_run_value(self):
        app = (Path(DESKTOP_DIR) / "App.xaml.cs").read_text(encoding="utf-8")
        registration = (
            Path(DESKTOP_DIR) / "Services" / "StartupEntry.cs"
        ).read_text(encoding="utf-8")

        assert "StartupEntry.RefreshIfEnabled(" in app
        assert "ViewModel.Settings.StartWithWindows" in app
        assert "new UpdateService().IsSupported" in app
        refresh = registration.split("public static void RefreshIfEnabled")[1].split(
            "\n    }", 1
        )[0]
        assert "enabled && isInstalled" in refresh
        assert '$"\\"{executablePath}\\" --tray"' in registration


@pytest.mark.ui
class TestStartWithWindowsBehaviour:
    def test_tray_launch_has_an_icon_but_no_visible_window(self, logger):
        from desktop.app_controller import DesktopController

        ctrl = DesktopController(logger)
        try:
            ctrl.launch_app(clean_state=True, extra_args=["--tray"])
            time.sleep(2.0)

            assert ctrl.pid and psutil.pid_exists(ctrl.pid), \
                "FlowShield exited instead of staying available in the tray"
            assert not ctrl.main_window_is_visible(), \
                "--tray displayed FlowShield's main window"

            tray_icon = ctrl.find_tray_icon()
            assert tray_icon is not None, "FlowShield's notification-area icon is missing"

            tray_icon.double_click_input()
            ctrl.connect_window()
            assert ctrl.main_window_is_visible(), \
                "double-clicking the tray icon did not restore FlowShield"
        finally:
            ctrl.close_app()

    def test_a_dev_launch_leaves_an_installed_run_value_untouched(self, logger):
        import winreg

        from desktop.app_controller import DesktopController

        run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        dev_command = f'"{Path(APP_EXE).resolve()}" --tray'
        installed_command = r'"C:\Program Files\FlowShield\FlowShield.exe" --tray'

        first = DesktopController(logger)
        try:
            first.launch_app(clean_state=True)
            first.connect_window()
            first.navigate_to_tab("Settings")
            assert first.set_toggle("StartWithWindowsToggle", True) is True

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key) as key:
                assert winreg.QueryValueEx(key, "FlowShield")[0] == dev_command

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, run_key, access=winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(
                    key, "FlowShield", 0, winreg.REG_SZ,
                    installed_command,
                )
        finally:
            first.close_app()

        second = DesktopController(logger)
        try:
            second.launch_app(clean_state=False)
            second.connect_window()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key) as key:
                assert winreg.QueryValueEx(key, "FlowShield")[0] == installed_command
        finally:
            second.close_app()


# ====================== the site only sells implemented features

class _PricingFeatureParser(HTMLParser):
    """Collect checked features from every plan in the pricing section."""

    def __init__(self):
        super().__init__()
        self.in_pricing = False
        self.plan_stack = []
        self.checked_features = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "section" and attributes.get("id") == "pricing":
            self.in_pricing = True
        elif tag == "ul" and self.in_pricing:
            self.plan_stack.append(attributes.get("data-plan", "unnamed pricing list"))
        elif tag == "li" and self.plan_stack:
            classes = set(attributes.get("class", "").split())
            if "on" in classes:
                self.checked_features.append(
                    (self.plan_stack[-1], attributes.get("data-feature")))

    def handle_endtag(self, tag):
        if tag == "ul" and self.plan_stack:
            self.plan_stack.pop()
        elif tag == "section" and self.in_pricing:
            self.in_pricing = False

class TestWebsiteClaimsMatchTheApp:
    """Every checked pricing claim names code that implements it.

    Add a marker here when a new advertised feature ships. Keeping the registry
    beside the regression test makes changing marketing copy a deliberate,
    reviewable decision instead of an unchecked promise.
    """

    # Paths are relative to DesktopApp/; "../Server/..." reaches the licence server.
    FEATURE_MARKERS = {
        "seven-day-trial": (("Models/AppSettings.cs", "TrialDays = 7"),),
        "trial-unlocks-everything": (
            ("Models/AppSettings.cs", "IsPro || IsTrialActiveAt(nowUtc)"),
        ),
        "locks-after-trial": (
            ("MainWindow.xaml", 'AutomationProperties.AutomationId="TrialEndedPanel"'),
            ("ViewModels/TodayViewModel.cs", "if (_main.IsLocked)"),
        ),
        "one-time-purchase": (("../Server/server.js", "mode: 'payment'"),),
        "unlimited-blocked-apps": (
            ("ViewModels/BlockedAppsViewModel.cs", "CanAdd() => IsEditable && !_main.IsLocked &&"),
        ),
        "all-three-shields": (
            ("ViewModels/TodayViewModel.cs", "ShieldLevel.Soft, ShieldLevel.Firm, ShieldLevel.Sealed"),
        ),
        "sprint-lengths": (("ViewModels/TodayViewModel.cs", "{ 15, 25, 45, 60, 90 }"),),
        "momentum-and-streak": (
            ("Views/TodayView.xaml", 'AutomationProperties.AutomationId="MomentumValue"'),
            ("Views/TodayView.xaml", 'AutomationProperties.AutomationId="StreakText"'),
        ),
        "sleep-blocking": (("Services/AppBlockerService.cs", "IsWithinSleepWindow"),),
        "hard-kill-mode": (("Services/AppBlockerService.cs", "settings.HardKillModeEnabled"),),
        "three-devices": (("../Server/server.js", "DEVICE_LIMIT ?? 3"),),
    }

    def test_every_checked_pricing_feature_has_an_implementation_marker(self):
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        parser = _PricingFeatureParser()
        parser.feed(site)

        plans = {plan for plan, _ in parser.checked_features}
        assert {"trial", "full"}.issubset(plans)
        missing_ids = [plan for plan, feature in parser.checked_features if not feature]
        assert not missing_ids, (
            "every checked pricing item needs a data-feature id; missing on: "
            + ", ".join(missing_ids)
        )

        advertised = [feature for _, feature in parser.checked_features]

        undocumented = sorted(set(advertised) - self.FEATURE_MARKERS.keys())
        assert not undocumented, (
            "pricing claims have no implementation markers: " + ", ".join(undocumented)
        )

        for feature in advertised:
            for relative_path, marker in self.FEATURE_MARKERS[feature]:
                source = (Path(DESKTOP_DIR) / relative_path).read_text(encoding="utf-8")
                assert marker in source, (
                    f"{feature!r} is advertised, but {relative_path} has no "
                    f"implementation marker {marker!r}"
                )

    def test_future_pricing_plans_are_included(self):
        parser = _PricingFeatureParser()
        parser.feed(
            '<section id="pricing"><ul data-plan="annual">'
            '<li data-feature="annual-plan" class="featured on">Annual</li>'
            '<li class="on featured">Untagged claim</li>'
            '</ul></section>'
        )

        assert parser.checked_features == [
            ("annual", "annual-plan"),
            ("annual", None),
        ], "a future pricing plan or reordered attributes bypassed claim checks"

    def test_unshipped_claims_are_not_on_the_site(self):
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8").lower()
        # Remove an entry only when that feature ships and gains an implementation
        # marker above; deleting a phrase merely to weaken this test is not a fix.
        for claim in (
            "youtube.com", "momentum analytics",
            "journal export", "full-screen reminder", "can't unlock it early",
            "escape hatch is gone", "no three-second grace window",
            "months later", "nothing is uploaded", "dismissible reminder",
            "until the timer ends",
        ):
            assert claim not in site, f"the site still claims unshipped behaviour: {claim}"


class TestSoftShieldWording:
    """Public and developer-facing descriptions must match today's Soft mode."""

    def test_old_overlay_wording_is_gone(self):
        root = Path(DESKTOP_DIR).parent
        readme = (root / "README.md").read_text(encoding="utf-8")
        model = (Path(DESKTOP_DIR) / "Models" / "AppSettings.cs").read_text(
            encoding="utf-8")

        assert "dismissible full-screen nudge" not in readme
        assert "Full-screen nudge overlay" not in model
        assert "blocked app keeps running" in readme
        assert "blocked app keeps running" in model

    def test_legal_page_distinguishes_soft_from_closing_modes(self):
        source = (Path(WEBSITE_DIR) / "legal.html").read_text(encoding="utf-8")
        legal = " ".join(source.split())

        assert "Soft records the" in legal and "leaves the application running" in legal
        assert "Firm and Sealed close it" in legal
        assert "Any unsaved work in an application FlowShield closes may be lost" in legal

    def test_project_docs_describe_soft_and_sealed_accurately(self):
        """
        Ending a sprint early also unlocks a Sealed blocklist, so "until the timer
        ends" overstates it; Soft has no full-screen overlay. make_report.py is
        included because it regenerates FINAL_REPORT.md from its own template.
        """
        root = Path(DESKTOP_DIR).parent
        for name in ("README.md", "HANDOFF_PROMPT.md", "FINAL_REPORT.md",
                     "automation/make_report.py"):
            lines = (root / name).read_text(encoding="utf-8").splitlines()
            # FINAL_REPORT's results table quotes the app's own UI text verbatim
            # ("shield description='...'"); that is a record of a run, not a claim.
            prose = " ".join(" ".join(line.split()) for line in lines
                             if "description=" not in line)
            assert "locks until the timer ends" not in prose, \
                f"{name} says Sealed locks until the timer ends"
            assert "full-screen nudge" not in prose, \
                f"{name} still describes Soft as a full-screen nudge"


# ============================ payment-link purchases get a licence key

class TestPaymentLinkPurchase:
    """
    A Payment Link checkout carries no client_reference_id.

    The published site sells through a Payment Link (GitHub Pages cannot run
    the license server), so a buyer arriving at the success page had no
    reserved key. syncFromSession bailed out with `no_license_reference` and
    the customer got a 422 — having paid.
    """

    def test_sync_mints_a_key_when_there_is_no_reference(self):
        source = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")
        block = source.split("async function syncFromSession")[1].split("\n}")[0]

        assert "licensekey.generate()" in block, (
            "syncFromSession must mint a key for sessions without a "
            "client_reference_id — Payment Link buyers have no reserved key"
        )
        assert "findBySession" in block, (
            "minting must be keyed to the session id, or a refresh issues a "
            "second key for the same purchase"
        )

    def test_minting_is_idempotent_per_session(self, server, needs_stripe):
        """Two lookups of one session must never yield two different keys."""
        created = requests.post(f"{server}/create-checkout", json={}, timeout=45).json()
        session_id = created["sessionId"]

        first = requests.get(f"{server}/get-license",
                             params={"session_id": session_id}, timeout=25).json()
        second = requests.get(f"{server}/get-license",
                              params={"session_id": session_id}, timeout=25).json()

        assert first.get("licenseKey") == second.get("licenseKey"), \
            f"session produced two keys: {first.get('licenseKey')} / {second.get('licenseKey')}"


# ============================== blocklist is not enumerated across threads

class TestBlocklistThreadSafety:
    """
    The watcher ran on a timer thread and enumerated the same List<BlockedApp>
    the UI thread adds to and removes from. An enumeration racing a mutation
    throws "Collection was modified" from inside a timer callback.
    """

    def test_the_watcher_uses_a_private_snapshot(self):
        source = (Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs").read_text(
            encoding="utf-8")
        tick = source.split("private void Tick()")[1].split("\n    }")[0]

        assert "settings.BlockedApps" not in tick, (
            "Tick must not enumerate AppSettings.BlockedApps directly — the UI "
            "thread mutates that list"
        )
        assert "_targets" in tick, "Tick should read the snapshot rebuilt by UpdateSettings"

    def test_updating_settings_rebuilds_the_snapshot(self):
        source = (Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs").read_text(
            encoding="utf-8")
        update = source.split("public void UpdateSettings")[1].split("\n    }")[0]
        assert "_targets" in update and "ToList()" in update, \
            "UpdateSettings must refresh the snapshot, or the blocklist goes stale"

    @pytest.mark.ui
    def test_rapid_blocklist_edits_do_not_destabilise_the_app(self, fresh_app):
        """Churn the list while the watcher is running and confirm it survives."""
        fresh_app.navigate_to_tab("Today")
        fresh_app.start_sprint()          # watcher now enumerating every 2s
        time.sleep(1.0)

        fresh_app.navigate_to_tab("Blocked Apps")
        for index in range(3):
            fresh_app.add_blocked_app(f"churn-{index}")
            time.sleep(0.4)
        for index in range(3):
            fresh_app.remove_blocked_app(f"churn-{index}")
            time.sleep(0.4)

        assert fresh_app.current_page_title() == "Blocked Apps", "the app fell over"
        assert fresh_app.blocked_app_names() == [], fresh_app.blocked_app_names()

        fresh_app.navigate_to_tab("Today")
        fresh_app.stop_sprint()
        assert "early" in fresh_app.session_state().lower()


# ======================================= today's counters mean "today"

class TestTodayCounters:
    """
    "Distractions blocked" sat under a TODAY heading but summed every app's
    lifetime BlockCount, so it never reset and counted yesterday's blocks.
    """

    def test_blocks_today_is_not_a_lifetime_sum(self):
        source = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(
            encoding="utf-8")
        stats = source.split("public void RefreshStats()")[1].split("\n    }")[0]

        assert "Sum(a => a.BlockCount)" not in stats, \
            "a lifetime total must not be displayed as today's figure"
        assert "BlocksTodayCurrent" in stats

    def test_the_day_rolls_over(self):
        """RecordBlock must zero the tally when the date changes."""
        source = (Path(DESKTOP_DIR) / "Models" / "AppSettings.cs").read_text(
            encoding="utf-8")
        record = source.split("public void RecordBlock")[1].split("\n    }")[0]
        assert "BlocksToday = 0" in record, "the counter never resets at midnight"

    def test_a_sprint_records_its_own_block_count(self):
        source = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(
            encoding="utf-8")
        assert "_current.BlocksEnforced = _blocksThisSprint" in source, (
            "a session must record its own blocks, not the process-wide total "
            "since launch"
        )


# ================================= the blocked-app list updates on screen

class TestBlockedAppNotifies:
    """BlockCount changes while the list is visible; without INotifyPropertyChanged
    the "blocked N ×" label renders once and then never changes."""

    def test_blocked_app_raises_property_changed(self):
        source = (Path(DESKTOP_DIR) / "Models" / "AppSettings.cs").read_text(
            encoding="utf-8")
        assert "class BlockedApp : INotifyPropertyChanged" in source
        block = source.split("class BlockedApp")[1].split("public class")[0]
        assert "public int BlockCount" in block and "Raise()" in block, \
            "BlockCount must notify, or the count on screen goes stale"


# ============================ sleep blocking actually blocks

class TestSleepBlockingEnforces:
    """
    Inside the sleep window the watcher previously dropped to the Soft shield
    unless hard-kill mode was on, so a scheduled block only wrote a log line.
    Nobody is at the keyboard at 2am to be nudged.
    """

    def test_sleep_window_closes_apps(self):
        source = (Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs").read_text(
            encoding="utf-8")
        tick = source.split("private void Tick()")[1].split("\n    }")[0]
        assert "sleepActive && !enforcing) shield = ShieldLevel.Firm" in tick, \
            "a scheduled sleep block must close apps, not merely nudge"


# ======================= a cancelled subscription actually loses Pro

class TestLicenseRevocation:
    """
    The startup re-check downgraded Pro only for a hardcoded list of statuses
    (not_found, canceled, unpaid). A subscription ending as incomplete_expired
    or paused kept Pro indefinitely.
    """

    def test_downgrade_is_not_a_hardcoded_status_list(self):
        source = (Path(DESKTOP_DIR) / "Services" / "LicenseService.cs").read_text(
            encoding="utf-8")
        refresh = source.split("public async Task RefreshAsync")[1].split("\n    }")[0]

        assert 'result.Status is "not_found"' not in refresh, (
            "matching specific bad statuses silently keeps Pro for any status "
            "not on the list"
        )
        assert "result.Definitive" in refresh and "!result.IsPro" in refresh, \
            "downgrade should follow the server's verdict"

    def test_an_unreachable_server_is_not_a_verdict(self):
        """A flaky connection must never revoke a paying user's licence."""
        source = (Path(DESKTOP_DIR) / "Services" / "LicenseService.cs").read_text(
            encoding="utf-8")
        failure = source.split("public static LicenseResult Failure")[1].split(";")[0]
        assert "Definitive: false" in failure, \
            "transport failures must be marked non-definitive"


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
    The dev build and an installed FlowShield share one settings file. The
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
        automation = Path(__file__).resolve().parent.parent
        for script in ("e2e_runner.py", "smoke_ui.py", "verify_blocking.py",
                       "verify_deployed.py"):
            source = (automation / script).read_text(encoding="utf-8")
            assert "with preserve_user_settings():" in source, \
                f"{script} launches the app but doesn't preserve the owner's settings"
        conftest = (automation / "tests" / "conftest.py").read_text(encoding="utf-8")
        assert "autouse=True" in conftest and "preserve_user_settings()" in conftest

    def test_the_startup_entry_is_also_backed_up_and_restored(self):
        guard = (Path(__file__).resolve().parent.parent / "core" /
                 "settings_guard.py").read_text(encoding="utf-8")
        assert "_back_up_startup_registration()" in guard
        assert "_restore_startup_registration()" in guard
        assert 'RUN_VALUE_NAME = "FlowShield"' in guard


# ============ a lost database must not revoke anyone's subscription

def _db_admin(*args) -> str:
    result = subprocess.run(
        [NODE_EXE, str(Path(SERVER_DIR).parent / "tools" / "db_admin.js"), *args],
        cwd=str(Path(SERVER_DIR).parent), capture_output=True, text=True, timeout=60,
    )
    return (result.stdout or "").strip().splitlines()[-1] if result.stdout.strip() else ""


# ============ an email address is not proof of identity (#21)

class TestEmailIsNotAuthentication:
    """
    /create-portal-session and /devices accepted an email address in place of
    the licence key, and /validate echoed the key back to an email-only caller:
    anyone who knew a customer's address could cancel their subscription, list
    their PCs and release their seats, or obtain their key.
    """

    @staticmethod
    def route(name: str) -> str:
        source = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")
        return source.split(f"app.post('/{name}'")[1].split("\napp.")[0]

    def test_the_portal_and_devices_ignore_email(self):
        for name in ("create-portal-session", "devices"):
            body = self.route(name)
            assert "req.body?.email" not in body, f"/{name} still reads an email address"
            assert "findByEmail" not in body, f"/{name} still looks licences up by email"
            assert "missing_license_key" in body, f"/{name} must refuse a request without a key"

    def test_validate_redacts_the_key_unless_it_was_presented(self):
        body = self.route("validate")
        assert "key !== row.license_key" in body and "delete view.licenseKey" in body

    def test_the_customer_endpoints_are_rate_limited(self):
        source = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")
        for name in ("validate", "devices", "create-portal-session", "resend-license"):
            assert f"'/{name}', limiter.middleware('{name}')" in source, f"/{name} is not rate limited"

    def test_the_app_no_longer_opens_a_billing_portal(self):
        """There is no subscription to manage since the one-time purchase (#29)."""
        source = (Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs").read_text(encoding="utf-8")
        view = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(encoding="utf-8")
        assert "create-portal-session" not in source
        assert "Manage subscription" not in view


@pytest.mark.stripe
class TestSurvivesDataLoss:
    """
    Free hosting tiers have ephemeral disks, so licenses.db is wiped on every
    redeploy. Treating it as the record would silently drop every paying
    customer to "not_found" after a routine deploy — so Stripe is the record
    and the database is a cache that rebuilds itself.
    """

    def _pick_active(self):
        raw = _db_admin("pick-active")
        row = json.loads(raw) if raw and raw != "null" else None
        if not row or not row.get("email"):
            pytest.skip("no active licence with an email to exercise recovery against")
        return row

    def test_a_wiped_row_is_rebuilt_from_stripe(self, server, needs_stripe):
        row = self._pick_active()

        wiped = json.loads(_db_admin("forget", row["license_key"]))
        assert wiped["deleted"] is True, wiped

        body = requests.post(f"{server}/validate",
                             json={"email": row["email"]}, timeout=45).json()

        assert body["isPro"] is True, (
            f"a paying customer lost Pro when the database was wiped: {body}"
        )
        # An email alone no longer reveals the key (#21); the row is rebuilt all the same.
        assert "licenseKey" not in body, body
        rebuilt = json.loads(_db_admin("show", row["license_key"]) or "null")
        assert rebuilt and rebuilt["status"] == "active", rebuilt

    def test_recovery_keeps_the_key_the_customer_already_has(self, server, needs_stripe):
        """
        Minting a fresh key on recovery would orphan the one they wrote down.

        The presented key matters because one email address can hold several
        subscriptions — buying twice, or any Payment Link purchase, creates a
        separate Stripe customer each time. Recovery must return the key the
        customer actually presented, not whichever subscription Stripe happened
        to list first.
        """
        row = self._pick_active()
        original = row["license_key"]

        assert json.loads(_db_admin("forget", original))["deleted"] is True

        body = requests.post(
            f"{server}/validate",
            json={"licenseKey": original, "email": row["email"]},
            timeout=45,
        ).json()

        assert body["isPro"] is True, body
        assert body["licenseKey"] == original, (
            f"recovery issued {body.get('licenseKey')} instead of the customer's "
            f"existing key {original} — is it picking an arbitrary subscription "
            f"for this email?"
        )

    def test_recovery_is_stable_across_repeated_calls(self, server, needs_stripe):
        """Two recoveries of the same licence must not produce two keys."""
        row = self._pick_active()
        original = row["license_key"]

        keys = []
        for _ in range(2):
            _db_admin("forget", original)
            body = requests.post(
                f"{server}/validate",
                json={"licenseKey": original, "email": row["email"]},
                timeout=45,
            ).json()
            keys.append(body.get("licenseKey"))

        assert keys[0] == keys[1] == original, f"recovery churned keys: {keys}"

    def test_a_presented_key_is_not_shadowed_by_the_email(self, server, needs_stripe):
        """
        One address can hold several subscriptions — buying twice, and every
        Payment Link purchase, creates a separate Stripe customer. Resolving
        the email before exhausting the presented key handed the customer a
        *different* subscription's licence key.
        """
        row = self._pick_active()
        original = row["license_key"]
        email = row["email"]

        # Only meaningful when the address really does have more than one.
        others = requests.post(f"{server}/validate", json={"email": email}, timeout=45).json()
        if not others.get("isPro"):
            pytest.skip("no active subscription for this address")

        assert json.loads(_db_admin("forget", original))["deleted"] is True

        body = requests.post(
            f"{server}/validate",
            json={"licenseKey": original, "email": email},
            timeout=45,
        ).json()

        assert body["licenseKey"] == original, (
            f"the email lookup shadowed the presented key: asked for {original}, "
            f"got {body.get('licenseKey')}"
        )

    def test_a_recovered_row_keeps_the_customer_email(self, server, needs_stripe):
        """
        Recovery by key returns `customer` as a bare id, so the address has to
        be fetched. Without it the rebuilt row has no email — the customer
        cannot activate by email and no licence email can reach them, which
        only surfaces after a redeploy has already wiped the cache.
        """
        row = self._pick_active()
        assert json.loads(_db_admin("forget", row["license_key"]))["deleted"] is True

        body = requests.post(f"{server}/validate",
                             json={"licenseKey": row["license_key"]}, timeout=60).json()

        assert body["isPro"] is True, body
        assert body.get("email"), (
            "the recovered licence has no email address; licence emails and "
            "email activation would both silently stop working"
        )

    def test_the_server_stamps_keys_onto_stripe_for_recovery(self):
        source = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")
        assert "metadata: { ...(subscription.metadata || {}), license_key" in source, (
            "the licence key must be written onto the Stripe subscription, or it "
            "cannot be recovered after data loss"
        )


# ================== the success page promises only what it can deliver

class TestSuccessPageHonesty:
    """
    The Payment Link branch told buyers their key was emailed. Nothing in this
    build sends email, so that was a promise the system could not keep.
    """

    def test_it_does_not_claim_an_email_was_sent(self):
        source = (Path(SERVER_DIR).parent / "Website" / "checkout.js").read_text(
            encoding="utf-8")
        branch = source.split("if (!HAS_SERVER) {", 1)[1].split("var result =")[0]

        assert "on its way to the email" not in branch, \
            "the page must not promise a licence-key email that is never sent"
        assert "Activate licence" in branch, \
            "it should tell the buyer how to actually activate FlowShield"


# ============ what a buyer reads while paying is true (found in a test purchase)

class TestPurchaseFlowCopy:
    """
    A test-mode purchase on 13 September 2026 showed buyers claims the product
    couldn't back: a receipt "sent" that the page can't know about, a key
    "shown only once" that reloads fine, a Stripe product description promising
    momentum analytics, a price with no mention of the sales tax Stripe adds,
    and the app describing Sealed as locking "until the timer ends".
    """

    def test_the_success_page_makes_no_receipt_or_one_time_claims(self):
        source = (Path(WEBSITE_DIR) / "checkout.js").read_text(encoding="utf-8")
        assert "receipt sent to" not in source
        assert "Stripe has emailed your receipt" not in source
        assert "shown here only once" not in source

    def test_the_pricing_mentions_sales_tax(self):
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        pricing = site.split('<section id="pricing">', 1)[1].split("</section>", 1)[0]
        assert "sales tax" in pricing.lower()

    def test_the_stripe_product_description_is_true_and_kept_current(self):
        script = (Path(DESKTOP_DIR).parent / "tools" / "setup_stripe_store.js").read_text(encoding="utf-8")
        description = script.split("const PRODUCT_DESCRIPTION =", 1)[1].split(";", 1)[0]
        assert "analytics" not in description and "unlimited history" not in description.lower()
        assert "existing.description !== PRODUCT_DESCRIPTION" in script, \
            "re-running the setup script must correct an existing product's description"

    def test_the_app_describes_sealed_accurately(self):
        today = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert "until the timer ends" not in today
        assert "locks for the rest of the sprint" in today

    def test_the_report_table_lists_only_shipped_pro_features(self):
        root = Path(DESKTOP_DIR).parent
        for name in ("automation/make_report.py", "FINAL_REPORT.md"):
            text = (root / name).read_text(encoding="utf-8")
            assert "momentum analytics" not in text, f"{name} still promises momentum analytics"
            assert "| Sprint length | ≤ 25 min | Any |" not in text, f"{name} says Pro sprints can be any length"


# ==================================== settings survive a restart

@pytest.mark.ui
class TestPersistenceAcrossRestart:
    """State written by one run must be readable by the next."""

    def test_blocked_apps_survive_a_restart(self, logger):
        from desktop.app_controller import DesktopController

        first = DesktopController(logger)
        try:
            first.launch_app(clean_state=True)
            first.connect_window()
            time.sleep(1.0)
            first.navigate_to_tab("Blocked Apps")
            first.add_blocked_app(TEST_BLOCK_APP)
            time.sleep(1.0)
        finally:
            first.close_app()

        time.sleep(1.0)

        second = DesktopController(logger)
        try:
            # clean_state=False: the point is to read what the last run wrote.
            second.launch_app(clean_state=False)
            second.connect_window()
            time.sleep(1.2)
            second.navigate_to_tab("Blocked Apps")
            names = second.blocked_app_names()
            assert any(TEST_BLOCK_APP.lower() in n.lower() for n in names), names
        finally:
            second.close_app()


# ============ a one-time purchase after a 7-day trial (#29)

class TestTrialThenOneTimePurchase:
    """
    FlowShield moved from a free tier plus a $4.99/month subscription to a
    7-day trial with everything unlocked and a one-time $4.99 purchase. Each
    check here guards a way that change could silently come undone.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).parent.joinpath(*parts)).read_text(encoding="utf-8")

    def test_checkout_takes_a_one_time_payment(self):
        route = self.read("Server", "server.js").split("app.post('/create-checkout'")[1].split("\napp.")[0]
        assert "mode: 'payment'" in route and "mode: 'subscription'" not in route
        assert "payment_intent_data: { metadata: { license_key" in route, \
            "the key must go on the payment, or a lost database can't be rebuilt"
        assert "customer_creation: 'always'" in route, \
            "without a customer the purchase can't be found by email"

    def test_the_store_script_creates_a_one_time_price(self):
        script = self.read("tools", "setup_stripe_store.js")
        create = script.split("async function ensurePrice")[1].split("\n}")[0]
        assert "recurring: { interval" not in create
        assert "!p.recurring" in create, "a monthly price must never be reused as the purchase price"
        assert "'charge.refunded'" in script, "refunds must reach the webhook"

    def test_a_refund_revokes_the_licence(self):
        server = self.read("Server", "server.js")
        status = server.split("function paymentStatusOf")[1].split("\n}")[0]
        assert "charge.refunded" in status and "'refunded'" in status
        assert "case 'charge.refunded':" in server
        validate = server.split("app.post('/validate'")[1].split("\napp.")[0]
        assert "row.stripe_payment_intent_id" in validate, \
            "/validate must re-check a purchase, or a missed refund webhook keeps it active"

    def test_payments_are_recoverable_after_data_loss(self):
        recover = self.read("Server", "server.js").split("async function recoverFromStripe")[1].split("\n}")[0]
        assert "paymentIntents.search" in recover and "paymentIntents.list" in recover

    def test_the_trial_starts_on_first_launch_and_is_saved(self):
        main = self.read("DesktopApp", "ViewModels", "MainViewModel.cs")
        app = self.read("DesktopApp", "App.xaml.cs")
        assert "Settings.EnsureTrialStarted()" in main
        assert app.index("new MainViewModel(") < app.index("ViewModel.SaveSettings();"), \
            "the trial start must be persisted straight away"

    def test_a_locked_app_cannot_start_a_sprint_or_keep_blocking_at_night(self):
        today = self.read("DesktopApp", "ViewModels", "TodayViewModel.cs")
        start = today.split("private void StartSprint()")[1].split("\n    }")[0]
        assert "_main.IsLocked" in start
        sleep = self.read("DesktopApp", "ViewModels", "SleepBlockingViewModel.cs")
        tier = sleep.split("public void OnTierChanged()")[1].split("\n    }")[0]
        assert "IsLocked" in tier and "IsSleepBlockEnabled = false" in tier

    def test_the_trial_ending_mid_sprint_does_not_drop_the_shield(self):
        main = self.read("DesktopApp", "ViewModels", "MainViewModel.cs")
        refresh = main.split("public void RefreshAccess()")[1].split("\n    }")[0]
        assert "if (IsSprintRunning) return;" in refresh

    def test_the_expire_trial_flag_only_takes_access_away(self):
        app = self.read("DesktopApp", "App.xaml.cs")
        block = app.split('"--expire-trial"')[1].split("\n        }")[0]
        assert "IsPro" not in block, "a command-line flag must never grant a licence"

    def test_the_site_no_longer_sells_a_subscription(self):
        for name in ("index.html", "success.html", "checkout.js", "legal.html"):
            text = (Path(WEBSITE_DIR) / name).read_text(encoding="utf-8").lower()
            for phrase in ("/mo", "per month", "billed monthly", "renews automatically",
                           "get pro", "free forever", "subscription is active"):
                assert phrase not in text, f"{name} still says {phrase!r}"


# ============ app and site colours come from one file (DESIGN_SYSTEM.md §14)

class TestDesignTokensStayInSync:
    """
    Colours were typed twice, in Theme.xaml and styles.css, and drifted. They
    now come from design/tokens.json through tools/build_tokens.py; these tests
    fail when someone edits a generated file by hand or forgets to regenerate.
    """

    ROOT = Path(DESKTOP_DIR).parent

    def test_generated_token_files_are_current(self):
        result = subprocess.run(
            [sys.executable, str(self.ROOT / "tools" / "build_tokens.py"), "--check"],
            cwd=str(self.ROOT), capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_theme_takes_its_palette_from_the_tokens(self):
        theme = (Path(DESKTOP_DIR) / "Styles" / "Theme.xaml").read_text(encoding="utf-8")
        assert '<ResourceDictionary Source="Tokens.xaml"/>' in theme
        for key in ("Bg", "Surface", "Ink", "InkFaint", "Primary", "Edge", "Green", "Amber", "Rose"):
            assert f'x:Key="{key}"' not in theme, f"{key} is defined in Theme.xaml instead of the tokens"

    def test_a_token_change_reaches_both_the_app_and_the_site(self, tmp_path):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_tokens", self.ROOT / "tools" / "build_tokens.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)

        data = json.loads((self.ROOT / "design" / "tokens.json").read_text(encoding="utf-8"))
        data["themes"]["dark"]["primary"] = "#123456"
        css = (Path(WEBSITE_DIR) / "styles.css").read_bytes().decode("utf-8").replace("\r\n", "\n")

        assert '<Color x:Key="PrimaryColor">#FF123456</Color>' in build.xaml(data, "dark")
        # A referenced token follows the colour it points at.
        assert '<Color x:Key="PrimarySoftColor">#33123456</Color>' in build.xaml(data, "dark")
        dark_css = build.css(data, css).split('html[data-theme="dark"]')[1]
        assert "--color-primary: #123456;" in dark_css


# ============ a sprint can't be escaped by closing FlowShield (F3, #43)

class TestSprintSurvivesRestart:
    """
    A running sprint lived only in memory, so killing FlowShield from Task
    Manager, a crash or a reboot ended it silently, even a Sealed one.
    """

    @staticmethod
    def today() -> str:
        return (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")

    def test_the_sprint_is_saved_before_enforcement_starts(self):
        start = self.today().split("private void StartSprint()")[1].split("\n    }")[0]
        assert "S.ActiveSprint = new RunningSprint" in start
        assert start.index("_main.SaveSettings()") < start.index("BeginRunning("), \
            "a crash between starting and saving would lose the sprint"

    def test_ending_a_sprint_clears_it(self):
        end = self.today().split("private void EndSprint(bool completed)")[1].split("\n    }")[0]
        assert "S.ActiveSprint = null" in end

    def test_startup_resumes_after_the_defaults_are_applied(self):
        main = (Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs").read_text(encoding="utf-8")
        ctor = main.split("public MainViewModel(")[1].split("\n    }")[0]
        assert "Today.ResumeInterruptedSprint()" in ctor
        assert ctor.index("Today.SelectedShield = Settings.DefaultShield") < ctor.index("ResumeInterruptedSprint"), \
            "applying the default shield after resuming would replace a Sealed sprint's shield"

    def test_a_resumed_sprint_keeps_its_shield(self):
        resume = self.today().split("public void ResumeInterruptedSprint")[1].split("\n    }")[0]
        assert "Shield = saved.Shield" in resume and "BeginRunning(" in resume

    @pytest.mark.ui
    def test_killing_flowshield_mid_sprint_does_not_end_a_sealed_sprint(self, logger):
        from desktop.app_controller import DesktopController

        first = DesktopController(logger)
        try:
            first.launch_app(clean_state=True)
            first.connect_window()
            time.sleep(1.0)
            first.navigate_to_tab("Blocked Apps")
            first.add_blocked_app(TEST_BLOCK_APP)
            first.navigate_to_tab("Today")
            first.select_shield("Sealed")
            time.sleep(0.5)
            first.start_sprint()
            time.sleep(2.0)
            saved = verify.read_settings()
            assert saved.get("ActiveSprint"), "the running sprint was not saved"
        finally:
            first.close_app()          # a hard kill, like ending it from Task Manager

        second = DesktopController(logger)
        try:
            second.launch_app(clean_state=False)
            second.connect_window()
            time.sleep(1.5)
            second.navigate_to_tab("Today")
            assert "resumed" in second.session_state().lower(), second.session_state()
            assert second.exists("StopSprintButton", timeout=3), "the sprint is not running after relaunch"

            second.navigate_to_tab("Blocked Apps")
            time.sleep(0.6)
            assert second.is_control_enabled("NewAppNameInput") is False, \
                "a resumed Sealed sprint must keep the blocklist locked"
            assert second.is_control_enabled("AddAppButton") is False
        finally:
            second.close_app()


# ============ a sprint couldn't be escaped by one click (F2, #47)

class TestNoOneClickEscape:
    """
    End sprint was one click at every shield level, and the tray's Quit exited
    instantly mid-sprint, so neither Firm nor Sealed actually held.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_the_end_button_goes_through_the_policy(self):
        today = self.read("ViewModels", "TodayViewModel.cs")
        assert "StopCommand = new RelayCommand(() => RequestEnd()" in today
        assert "EndSprint(completed: false), () => IsRunning" not in today
        request = today.split("public bool RequestEnd()")[1].split("\n    }")[0]
        assert "EndSprintPolicy.FlowFor(" in request

    def test_end_anyway_rechecks_the_wait(self):
        today = self.read("ViewModels", "TodayViewModel.cs")
        end_anyway = today.split("private void EndAnyway()")[1].split("\n    }")[0]
        assert "!EndAnywayEnabled) return" in end_anyway, \
            "End anyway must refuse before the countdown and phrase are done, whatever invoked it"

    def test_tray_quit_and_window_close_use_the_end_flow(self):
        window = self.read("MainWindow.xaml.cs")
        assert 'menu.Items.Add("Quit", null, (_, _) => Quit());' in window
        quit_ = window.split("private void Quit()")[1].split("\n    }")[0]
        assert "RequestEnd()" in quit_
        closing = window.split("protected override void OnClosing")[1].split("\n    }")[0]
        assert "NeedsEndFlowToQuit" in closing

    def test_short_timers_only_shorten_waits(self):
        policy = self.read("Models", "EndSprintPolicy.cs")
        flow = policy.split("public static EndFlow FlowFor")[1].split(";")[0]
        assert "UseShortTimers" not in flow, "the test flag must not change which flow applies"

    @pytest.mark.ui
    def test_closing_the_window_mid_firm_sprint_goes_through_the_flow(self, fresh_app):
        import psutil

        fresh_app.navigate_to_tab("Settings")
        fresh_app.set_toggle("MinimizeToTrayToggle", False)   # close really exits
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Firm")
        time.sleep(0.4)
        fresh_app.start_sprint()
        fresh_app.wait_out_grace_period()

        fresh_app.window.close()                      # WM_CLOSE, like clicking X
        time.sleep(1.5)
        assert psutil.pid_exists(fresh_app.pid), "closing the window escaped a Firm sprint"
        assert fresh_app.exists("KeepGoingButton", timeout=3), "no end flow was shown"

        deadline = time.time() + 10
        while time.time() < deadline and not fresh_app.is_control_enabled("EndAnywayButton"):
            time.sleep(0.4)
        fresh_app.click("EndAnywayButton")

        deadline = time.time() + 10
        while time.time() < deadline and psutil.pid_exists(fresh_app.pid):
            time.sleep(0.4)
        assert not psutil.pid_exists(fresh_app.pid), "FlowShield didn't quit after the sprint ended"


# ============ the success page's Activate button did nothing (roadmap 1.4, #51)

class TestActivationLinkWorks:
    """
    success.html linked to flowshield://activate?key=… but nothing registered
    the scheme, so buyers had to copy the key by hand.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_install_and_update_register_and_uninstall_removes(self):
        program = self.read("Program.cs")
        assert ".OnAfterInstallFastCallback(_ => RegisterLink())" in program
        assert ".OnAfterUpdateFastCallback(_ => RegisterLink())" in program
        assert ".OnBeforeUninstallFastCallback(_ => Uninstall.CleanUp())" in program
        link = self.read("Services", "DeepLink.cs")
        assert r'@"Software\Classes\" + Scheme' in link, "must be per user (HKCU), never machine-wide"
        assert "Registry.LocalMachine" not in link
        assert '$"\\"{exePath}\\" \\"%1\\""' in link

    def test_a_link_never_activates_by_itself(self):
        main = self.read("ViewModels", "MainViewModel.cs")
        handle = main.split("public void HandleLink(")[1].split("\n    }")[0]
        assert "ActivateCommand" not in handle and "ValidateAsync" not in handle, \
            "a web page must not be able to activate without the user's click"
        confirm = main.split("private void ConfirmActivation()")[1].split("\n    }")[0]
        assert "ActivateCommand.Execute" in confirm

    def test_links_and_keys_stay_out_of_the_log(self):
        app = self.read("App.xaml.cs")
        assert '"<link>"' in app
        assert "string.Join(' ', launchArgs)" not in app

    def test_both_ways_in_handle_the_link(self):
        app = self.read("App.xaml.cs")
        assert "ViewModel.HandleLink(DeepLink.FindLink(args))" in app, "cold start"
        assert "ViewModel.HandleLink(DeepLink.FindLink(launchArgs))" in app, "already running"


# ============ a new user's first sprint blocked nothing (F18, #68)

class TestFirstRunNeverNags:
    """
    New installs opened on an empty Today page, so the first sprint blocked
    nothing. The welcome that fixes it must never reach existing users.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_existing_users_are_marked_done_instead_of_shown(self):
        vm = self.read("ViewModels", "FirstRunViewModel.cs")
        show_if_new = vm.split("public void ShowIfNew()")[1].split("\n    }")[0]
        assert show_if_new.index("IsExistingUser(s)") < show_if_new.index("ShouldShow(")
        assert "s.FirstRunCompleted = true;" in show_if_new

    def test_seen_counts_as_done(self):
        show = self.read("ViewModels", "FirstRunViewModel.cs").split("public void Show()")[1].split("IsVisible = true;")[0]
        assert "_main.Settings.FirstRunCompleted = true;" in show and "_main.SaveSettings();" in show

    def test_decided_after_the_trial_flags(self):
        app = self.read("App.xaml.cs")
        assert app.index("--expire-trial") < app.index("ViewModel.FirstRun.ShowIfNew()"), \
            "a trial expired by the flag would get the welcome over its lock screen"

    def test_the_ui_suite_skips_it_unless_asked(self):
        controller = (Path(DESKTOP_DIR).parent / "automation" / "desktop" / "app_controller.py").read_text(encoding="utf-8")
        assert 'args.append("--skip-first-run")' in controller


# ============ blocking Steam left steamwebhelper running (F8, #58)

class TestEveryProcessOfAnAppIsBlocked:
    """
    A blocklist entry held one process name, so blocking Steam closed steam.exe
    and left steamwebhelper (the store and chat windows) running.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_the_blocker_matches_every_process_of_an_entry(self):
        blocker = self.read("Services", "AppBlockerService.cs")
        assert "foreach (var processName in app.AllProcessNames) targets[processName] = app;" in blocker

    def test_old_single_process_entries_are_upgraded_on_load(self):
        vm = self.read("ViewModels", "BlockedAppsViewModel.cs")
        ctor = vm.split("public BlockedAppsViewModel(MainViewModel main)")[1].split("\n    }")[0]
        assert "UpgradeToFullSuggestions(main.Settings.BlockedApps)" in ctor
        assert ctor.index("UpgradeToFullSuggestions") < ctor.index("Apps = new ObservableCollection")

    def test_older_settings_files_still_load(self):
        model = self.read("Models", "AppSettings.cs")
        assert "public List<string> ExtraProcessNames { get; set; } = new();" in model

    @pytest.mark.ui
    def test_a_firm_sprint_closes_steams_helper_too(self, fresh_app, tmp_path):
        import shutil
        import subprocess

        import psutil

        # A harmless stand-in: Windows' own ping, renamed to Steam's helper.
        helper = tmp_path / "steamwebhelper.exe"
        shutil.copy(Path(r"C:\Windows\System32\PING.EXE"), helper)
        proc = subprocess.Popen([str(helper), "-n", "600", "127.0.0.1"],
                                stdout=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            fresh_app.navigate_to_tab("Blocked Apps")
            fresh_app.set_text("AppSearchInput", "steam")
            time.sleep(0.6)
            fresh_app.click("PickApp_steam")
            time.sleep(0.8)

            fresh_app.navigate_to_tab("Today")
            fresh_app.select_shield("Firm")
            time.sleep(0.4)
            fresh_app.start_sprint()

            deadline = time.time() + 15
            while time.time() < deadline and psutil.pid_exists(proc.pid) and proc.poll() is None:
                time.sleep(0.5)
            assert proc.poll() is not None, "steamwebhelper kept running during a Firm sprint on Steam"
        finally:
            if proc.poll() is None:
                proc.kill()


# ============ uninstalling left registry entries behind (roadmap 1.5, #54)

class TestUninstallCleansUp:
    """
    Velopack deletes the app folder but not the registry, so "Start with
    Windows" pointed at a missing exe on every sign-in, and flowshield:// at nothing.
    """

    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    LINK_KEY = r"Software\Classes\flowshield"

    def test_the_uninstall_hook_removes_both_entries(self):
        uninstall = (Path(DESKTOP_DIR) / "Services" / "StartupEntry.cs").read_text(encoding="utf-8")
        clean_up = uninstall.split("public static void CleanUp()")[1].split("\n    }")[0]
        assert "StartupEntry.Set(false)" in clean_up and "DeepLink.Unregister()" in clean_up
        assert "APPDATA" not in clean_up and "Directory.Delete" not in clean_up, \
            "uninstall must keep the user's licence and history"

    def test_running_the_real_uninstall_hook_removes_them(self):
        """Runs the built exe the way Velopack's uninstaller does, with the real registry restored after."""
        import subprocess
        import winreg

        from config import APP_EXE
        from core.settings_guard import preserve_user_settings

        if not Path(APP_EXE).exists():
            pytest.skip("build the app first")

        def read_run():
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
                    return winreg.QueryValueEx(k, "FlowShield")[0]
            except FileNotFoundError:
                return None

        def link_exists():
            try:
                winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.LINK_KEY))
                return True
            except FileNotFoundError:
                return False

        def link_command():
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.LINK_KEY + r"\shell\open\command") as k:
                    return winreg.QueryValueEx(k, "")[0]
            except FileNotFoundError:
                return None

        saved_run, saved_link = read_run(), link_command()
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
                winreg.SetValueEx(k, "FlowShield", 0, winreg.REG_SZ, f'"{APP_EXE}" --tray')
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.LINK_KEY + r"\shell\open\command") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{APP_EXE}" "%1"')

            with preserve_user_settings():
                result = subprocess.run([str(APP_EXE), "--veloapp-uninstall", "1.0.0"],
                                        cwd=str(Path(APP_EXE).parent), timeout=60)
            assert result.returncode == 0
            assert read_run() is None, "Start with Windows survived uninstall"
            assert not link_exists(), "flowshield:// survived uninstall"
        finally:
            if saved_run is not None:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
                    winreg.SetValueEx(k, "FlowShield", 0, winreg.REG_SZ, saved_run)
            if saved_link is not None:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.LINK_KEY + r"\shell\open\command") as k:
                    winreg.SetValueEx(k, "", 0, winreg.REG_SZ, saved_link)
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.LINK_KEY) as k:
                    winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:FlowShield")
                    winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")


# ============ opening FlowShield twice ran two copies (roadmap 1.3, #49)

class TestOneInstanceOnly:
    """
    A second launch started a second blocker writing to the same settings file,
    so each copy could overwrite the other's sprint records.
    """

    @staticmethod
    def program() -> str:
        return (Path(DESKTOP_DIR) / "Program.cs").read_text(encoding="utf-8")

    def test_the_lock_is_taken_before_the_app_starts(self):
        main = self.program()
        assert main.index(".Run();") < main.index("SingleInstance.TryAcquire()"), \
            "Velopack's install and update runs must never be turned away"
        assert main.index("SingleInstance.TryAcquire()") < main.index("new App"), \
            "a second copy must exit before settings load or the blocker starts"
        acquire = main.split("SingleInstance.TryAcquire()")[1].split("new App")[0]
        assert "return;" in acquire

    def test_the_lock_is_per_user_and_survives_a_crash(self):
        single = (Path(DESKTOP_DIR) / "Services" / "SingleInstance.cs").read_text(encoding="utf-8")
        assert "Environment.UserName" in single
        assert "catch (AbandonedMutexException) { owned = true; }" in single, \
            "a copy killed from Task Manager would stop FlowShield ever opening again"

    @pytest.mark.ui
    def test_a_second_launch_mid_sprint_changes_nothing(self, fresh_app):
        import subprocess

        import psutil

        from config import APP_EXE

        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Sealed")
        time.sleep(0.4)
        fresh_app.start_sprint()
        time.sleep(1.5)
        before = verify.read_settings()
        assert before.get("ActiveSprint")

        # --reset is what would wipe a sprint if the second copy got that far.
        subprocess.run([str(APP_EXE), "--reset"], cwd=str(Path(APP_EXE).parent), timeout=30)
        time.sleep(1.5)

        names = [p.pid for p in psutil.process_iter(["name"])
                 if (p.info["name"] or "").lower() == "flowshield.exe"]
        assert names == [fresh_app.pid], "a second FlowShield kept running"
        after = verify.read_settings()
        # LastSeenUtc moves with the heartbeat, so compare what defines the sprint.
        assert after.get("ActiveSprint") and all(
            after["ActiveSprint"][k] == before["ActiveSprint"][k]
            for k in ("StartedUtc", "PlannedMinutes", "Shield")
        ), "the second launch touched the sprint"
        assert fresh_app.exists("StopSprintButton", timeout=3), "the sprint stopped"


# ============ footer links point at pages that exist (roadmap 6.6)

class _FooterLinkParser(HTMLParser):
    """Collect href values from every <a> inside <footer>."""

    def __init__(self):
        super().__init__()
        self.in_footer = False
        self.footer_links = []

    def handle_starttag(self, tag, attrs):
        if tag == "footer":
            self.in_footer = True
        elif tag == "a" and self.in_footer:
            href = dict(attrs).get("href")
            if href:
                self.footer_links.append(href)

    def handle_endtag(self, tag):
        if tag == "footer":
            self.in_footer = False


class TestFooterLinksPointToRealPages:
    """
    A footer link that 404s is worse than no link. The changelog and support
    pages are new, so this guards them and every other relative page link the
    three public pages advertise.
    """

    PAGES = ("index.html", "legal.html", "success.html")
    NEW_PAGES = ("changelog.html", "support.html")

    @classmethod
    def footer_links(cls, name: str) -> list[str]:
        parser = _FooterLinkParser()
        parser.feed((Path(WEBSITE_DIR) / name).read_text(encoding="utf-8"))
        return parser.footer_links

    def test_every_relative_html_link_exists(self):
        for name in self.PAGES:
            for href in self.footer_links(name):
                path = href.split("#", 1)[0]
                if not path.endswith(".html"):
                    continue
                if path.startswith(("http://", "https://", "//", "/")):
                    continue
                assert (Path(WEBSITE_DIR) / path).is_file(), \
                    f"{name} footer links to missing {href}"

    def test_changelog_and_support_are_linked_from_every_footer(self):
        for name in self.PAGES:
            paths = {href.split("#", 1)[0] for href in self.footer_links(name)}
            for page in self.NEW_PAGES:
                assert page in paths, f"{name} footer has no link to {page}"


class TestSupportPageDescribesTheShippedApp:
    """
    The first draft of support.html told customers to send a "diagnostics
    bundle" built from the Settings screen. No such feature exists; Settings has
    an "Open diagnostic log" button. Support instructions must name controls
    that are actually in the app.
    """

    def test_no_diagnostics_bundle_is_promised(self):
        page = (Path(WEBSITE_DIR) / "support.html").read_text(encoding="utf-8")
        assert "diagnostics bundle" not in page.lower()
        assert "build one for you" not in page

    def test_the_named_settings_control_exists(self):
        page = (Path(WEBSITE_DIR) / "support.html").read_text(encoding="utf-8")
        settings = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(
            encoding="utf-8-sig")
        assert "Open diagnostic log" in page
        assert 'Content="Open diagnostic log"' in settings

    def test_the_changelog_dates_the_first_release_correctly(self):
        # v1.0.0 was published on 11 September 2026; the draft said the 14th.
        page = (Path(WEBSITE_DIR) / "changelog.html").read_text(encoding="utf-8")
        assert "1.0.0 <span class=\"date\">11 September 2026</span>" in page


# ============ a crash shows a friendly dialog, not a raw exception dump (roadmap 1.14)

class TestFriendlyErrorDialog:
    """
    An unhandled UI exception used to pop a raw MessageBox with the exception
    message and a log path. It now shows a calm dialog that copies the details
    and links to support.

    The first draft of the dialog said "FlowShield is still guarding your
    sprint" and "Your sprint and blocklist are safe". Nothing in the handler
    can verify either after an arbitrary exception, so the dialog may not
    promise it (CLAUDE.md: never claim what the build can't back up).
    """

    def test_the_friendly_dialog_replaced_the_raw_message(self):
        app = (Path(DESKTOP_DIR) / "App.xaml.cs").read_text(encoding="utf-8")
        dialog = (Path(DESKTOP_DIR) / "Views" / "FriendlyErrorDialog.xaml").read_text(
            encoding="utf-8")
        code_behind = (Path(DESKTOP_DIR) / "Views" / "FriendlyErrorDialog.xaml.cs").read_text(
            encoding="utf-8")

        assert "FlowShield hit an unexpected error" not in app, \
            "the raw exception MessageBox must be gone"
        assert "FriendlyErrorDialog" in app, \
            "App.xaml.cs must show the friendly dialog on an unhandled exception"
        assert 'Text="Something went wrong."' in dialog
        assert "seventycookies6-design.github.io/flowshield/support.html" in code_behind, \
            "the friendly dialog must link to the support page"

    def test_the_dialog_does_not_promise_what_it_cannot_verify(self):
        dialog = (Path(DESKTOP_DIR) / "Views" / "FriendlyErrorDialog.xaml").read_text(
            encoding="utf-8").lower()
        for claim in ("still guarding", "are safe", "is safe", "protected"):
            assert claim not in dialog, f"the error dialog claims '{claim}' but cannot verify it"


# ============ the app must fit small screens (roadmap 1.13)

class TestSmallScreenLayout:
    """
    The window's minimum size was 900x620, which didn't fit on small laptops
    or split-screen layouts. The adaptive layout must collapse the nav rail to
    icons and move the stats rail below the timer at narrow widths.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_main_window_min_size_allows_small_screens(self):
        xaml = self.read("MainWindow.xaml")
        assert 'MinHeight="540"' in xaml, "MinHeight must be 540 to fit small screens"
        assert 'MinWidth="800"' in xaml, "MinWidth must be 800 to fit small screens"
        assert 'MinHeight="620"' not in xaml, "old MinHeight 620 must be replaced"
        assert 'MinWidth="900"' not in xaml, "old MinWidth 900 must be replaced"

    def test_today_view_has_adaptive_layout_elements(self):
        xaml = self.read("Views", "TodayView.xaml")
        assert 'x:Name="StatsRail"' in xaml, "stats rail must be named for adaptive layout"
        assert 'x:Name="StatsColumn"' in xaml, "stats column must be named for adaptive layout"
        assert 'x:Name="StatsRow"' in xaml, "stats row must be named for adaptive layout"
        assert 'x:Name="TimerCard"' in xaml, "timer card must be named for adaptive layout"

    def test_today_view_code_behind_handles_size_changes(self):
        cs = self.read("Views", "TodayView.xaml.cs")
        assert "OnSizeChanged" in cs, "TodayView must handle SizeChanged for adaptive layout"
        assert "StatsColumn" in cs and "StatsRail" in cs, \
            "TodayView must adjust stats column and rail position on size change"
        assert "Grid.SetRow" in cs or "SetRow" in cs, \
            "TodayView must move the stats rail between rows for narrow/wide layout"

    def test_nav_rail_has_icon_only_state(self):
        xaml = self.read("MainWindow.xaml")
        assert 'x:Name="NavTodayLabel"' in xaml, "nav labels must be named for icon-only state"
        assert 'x:Name="NavBlockedAppsLabel"' in xaml
        assert 'x:Name="NavBrandText"' in xaml, "brand text must be named for icon-only state"
        assert 'x:Name="NavColumn"' in xaml, "nav column must be named for width adjustment"

        cs = self.read("MainWindow.xaml.cs")
        assert "OnSizeChanged" in cs, "MainWindow must handle SizeChanged for nav rail adaptation"
        assert "NavColumn" in cs, "MainWindow must adjust nav column width on size change"
        assert "NavTodayLabel" in cs and "Visibility" in cs, \
            "MainWindow must hide nav labels in narrow mode"

    @pytest.mark.parametrize("view", ["MainWindow", "Views/TodayView"])
    def test_resizing_never_overwrites_a_visibility_binding(self, view):
        """
        The first draft set NavBuyButton.Visibility from OnSizeChanged. A local
        value replaces the element's {Binding IsNotPro} binding, so after one
        resize a paying customer saw "Buy FlowShield" again. Code-behind may
        only toggle Visibility on elements whose Visibility isn't data-bound.
        """
        import re

        xaml = self.read(*f"{view}.xaml".split("/")).replace("\ufeff", "")
        cs = self.read(*f"{view}.xaml.cs".split("/"))

        toggled = set(re.findall(r"\b(\w+)\.Visibility\s*=", cs))
        if view == "MainWindow":
            assert toggled, "MainWindow.xaml.cs no longer toggles visibility; update this test"

        for name in toggled:
            start = xaml.find(f'x:Name="{name}"')
            assert start >= 0, f"{view}.xaml.cs toggles {name}, which isn't in the XAML"
            element = xaml[xaml.rfind("<", 0, start):xaml.find(">", start)]
            assert "Visibility=\"{Binding" not in element, \
                f"{name} has a Visibility binding that {view}.xaml.cs overwrites"

    def test_the_buy_button_keeps_its_paid_user_binding(self):
        xaml = self.read("MainWindow.xaml").replace("\ufeff", "")
        start = xaml.find('AutomationId="GetProNavButton"')
        element = xaml[xaml.rfind("<", 0, start):xaml.find(">", start)]
        assert "{Binding IsNotPro" in element


# ============ custom sprint lengths must be wired up (roadmap 2.3)

class TestCustomSprintLengthsWired:
    """The Custom option must exist in the view and be bound to the viewmodel."""

    def test_the_view_has_a_custom_sprint_option(self):
        view = (Path(DESKTOP_DIR) / "Views" / "TodayView.xaml").read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="SprintLength_Custom"' in view
        assert "Custom…" in view

    def test_the_custom_input_is_bound(self):
        view = (Path(DESKTOP_DIR) / "Views" / "TodayView.xaml").read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="CustomMinutesInput"' in view
        assert "{Binding CustomMinutes" in view

    def test_the_existing_presets_are_still_present(self):
        view = (Path(DESKTOP_DIR) / "Views" / "TodayView.xaml").read_text(encoding="utf-8")
        for length in (15, 25, 45, 60, 90):
            assert f'SprintLength_{length}' in view, f"preset {length} min was removed"

    def test_presets_do_not_bind_to_the_live_length(self):
        """
        Presets bind to PresetMinutes, which is 0 while Custom is selected.
        Bound to SelectedMinutes, typing "15" on the way to "150" lit the
        15-minute preset and WPF's radio group unchecked Custom mid-keystroke.
        """
        view = (Path(DESKTOP_DIR) / "Views" / "TodayView.xaml").read_text(encoding="utf-8")
        assert "{Binding SelectedMinutes, Converter={StaticResource IntEq}" not in view
        assert view.count("{Binding PresetMinutes, Converter={StaticResource IntEq}") == 5


class TestCustomSprintLengthBehaviour:
    """
    Merge review of the first draft found: typing a value never saved it
    (only clicking the radio did), an out-of-range value silently kept the
    previous length, and Start stayed enabled. These drive the real window.
    """

    @pytest.mark.ui
    def test_typing_a_custom_length_sets_saves_and_validates(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        fresh_app.click("SprintLength_Custom")
        assert fresh_app.exists("CustomMinutesInput", timeout=3)

        fresh_app.set_text("CustomMinutesInput", "150")
        time.sleep(0.5)
        assert fresh_app.sprint_timer() == "150:00", "the typed length didn't become the sprint length"
        assert verify.read_settings().get("LastCustomSprintMinutes") == 150, \
            "the typed length was not saved"
        assert fresh_app.is_control_enabled("StartSprintButton")

        fresh_app.set_text("CustomMinutesInput", "300")
        time.sleep(0.5)
        assert fresh_app.exists("CustomMinutesError", timeout=3), "no message for an out-of-range value"
        assert fresh_app.sprint_timer() == "150:00", "an invalid value changed the sprint length"
        assert not fresh_app.is_control_enabled("StartSprintButton"), \
            "Start must be disabled while the custom value is invalid"
        assert verify.read_settings().get("LastCustomSprintMinutes") == 150

        fresh_app.set_text("CustomMinutesInput", "abc")
        time.sleep(0.5)
        assert fresh_app.exists("CustomMinutesError", timeout=3)
        assert not fresh_app.is_control_enabled("StartSprintButton")

        # A preset click leaves custom mode and takes over cleanly.
        fresh_app.click("SprintLength_25")
        time.sleep(0.5)
        assert fresh_app.sprint_timer() == "25:00"
        assert not fresh_app.exists("CustomMinutesInput", timeout=1)
        assert fresh_app.is_control_enabled("StartSprintButton")


# ============ the per-app switch must not unlock a Sealed blocklist (roadmap 2.4)

class TestPerAppSwitchGuard:
    """
    The per-app on/off switch is a second way to edit the blocklist, so it must
    be disabled while a Sealed sprint holds the list shut — the same guard the
    Add box and Remove button already obey.
    """

    XAML = Path(DESKTOP_DIR) / "Views" / "BlockedAppsView.xaml"
    VM = Path(DESKTOP_DIR) / "ViewModels" / "BlockedAppsViewModel.cs"

    def test_the_switch_binds_is_enabled_to_a_guard_property(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        assert 'IsEnabled="{Binding DataContext.CanEditApps' in xaml, (
            "the switch must bind IsEnabled to a guard property on the viewmodel"
        )

    def test_the_guard_depends_on_the_sealed_state(self):
        vm = self.VM.read_text(encoding="utf-8")
        assert "CanEditApps => !IsSealed" in vm, (
            "CanEditApps must be false while a Sealed sprint is running"
        )
        assert "Raise(nameof(CanEditApps))" in vm, (
            "CanEditApps must notify when sprint state changes"
        )


# ============ developer-only text must not reach customer surfaces (roadmap 1.15)

class TestNoDeveloperTextOnCustomerSurfaces:
    """
    Customer-facing surfaces (the website checkout flow and the Settings UI)
    previously leaked developer commands, file paths, and setup-doc references.
    A buyer should never see ``cd Server && npm start``, ``STRIPE_SETUP.md``,
    ``node tools/setup_stripe_store.js``, ``.stripe_keys.json``, the raw
    license-server URL, or the DPAPI settings-file path.
    """

    BANNED_WEBSITE_STRINGS = (
        "STRIPE_SETUP.md",
        "cd Server && npm start",
        "cd Server &amp;&amp; npm start",
        "node tools/setup_stripe_store.js",
        ".stripe_keys.json",
    )

    def test_checkout_js_has_no_developer_strings(self):
        source = (Path(WEBSITE_DIR) / "checkout.js").read_text(encoding="utf-8")
        for banned in self.BANNED_WEBSITE_STRINGS:
            assert banned not in source, (
                f"checkout.js still contains developer string {banned!r}"
            )

    def test_index_html_has_no_developer_strings(self):
        source = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        for banned in self.BANNED_WEBSITE_STRINGS:
            assert banned not in source, (
                f"index.html still contains developer string {banned!r}"
            )

    def test_settings_xaml_hides_license_server_from_normal_view(self):
        source = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(
            encoding="utf-8")
        dev_container = 'x:Name="DevOnlyFields"'
        assert dev_container in source, (
            "the developer-only fields must be wrapped in a named container "
            "so they can be hidden from normal users"
        )
        dev_block = source.split(dev_container)[1].split("</StackPanel>")[0]
        assert "License server" in dev_block, (
            "the License server label should live inside the dev-only container"
        )
        assert "DPAPI-encrypted" in dev_block, (
            "the DPAPI settings-path text should live inside the dev-only container"
        )

    def test_settings_code_behind_gates_dev_fields(self):
        source = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml.cs").read_text(
            encoding="utf-8")
        assert "DevMode" in source, (
            "the code-behind must check App.DevMode before showing dev fields"
        )
        assert "DevOnlyFields" in source, (
            "the code-behind must toggle the DevOnlyFields container"
        )
        assert "Collapsed" in source, (
            "dev fields must be Collapsed by default, not merely hidden"
        )

    def test_app_parses_dev_flag(self):
        source = (Path(DESKTOP_DIR) / "App.xaml.cs").read_text(encoding="utf-8")
        assert '"--dev"' in source, "App.xaml.cs must recognise the --dev flag"
        assert "DevMode" in source, "App must expose a DevMode property"

    @pytest.mark.ui
    def test_a_customer_launch_hides_the_dev_fields_but_keeps_the_log_button(self, logger):
        """Launched the way a customer does (no --dev), Settings shows no
        licence-server box or settings path, but Open diagnostic log — which
        support.html tells people to use — is still there."""
        from desktop.app_controller import DesktopController

        ctrl = DesktopController(logger)
        try:
            ctrl.launch_app(clean_state=True, dev_fields=False)
            ctrl.connect_window()
            time.sleep(1.0)
            ctrl.focus(force=True)
            ctrl.navigate_to_tab("Settings")
            assert not ctrl.exists("LicenseServerUrlInput", timeout=1.5), \
                "the licence-server URL box is visible to customers"
            assert ctrl.exists("OpenLogButton", timeout=3), \
                "Open diagnostic log disappeared with the dev fields"
        finally:
            ctrl.close_app()

    @pytest.mark.ui
    def test_the_suite_launch_still_reaches_the_dev_fields(self, fresh_app):
        # tier 4 types a dead URL into this box; verify_deployed.py reads it.
        fresh_app.navigate_to_tab("Settings")
        assert fresh_app.exists("LicenseServerUrlInput", timeout=3), \
            "the controller must pass --dev so tests can reach the URL box"


# ============ the site is keyboard-accessible and motion-safe (roadmap 6.7)

class TestWebsiteAccessibilityStyles:
    """
    Roadmap 6.7: interactive elements need a visible keyboard focus style, and
    non-essential motion must be disabled for users who ask for reduced motion.
    """

    def test_website_has_focus_and_reduced_motion_styles(self):
        css = (Path(WEBSITE_DIR) / "styles.css").read_text(encoding="utf-8")

        assert ":focus-visible" in css or ":focus" in css, (
            "styles.css must define a keyboard focus style for interactive elements"
        )
        assert "@media (prefers-reduced-motion: reduce)" in css, (
            "styles.css must disable non-essential motion for reduced-motion users"
        )

    @pytest.mark.parametrize("page", [
        "index.html", "legal.html", "success.html", "changelog.html", "support.html",
    ])
    def test_every_public_page_has_one_main_landmark(self, page):
        html = (Path(WEBSITE_DIR) / page).read_text(encoding="utf-8")
        assert html.count("<main>") == 1 and html.count("</main>") == 1, \
            f"{page} needs exactly one <main> landmark for screen-reader navigation"
        assert html.index("</main>") < html.index("<footer>"), \
            f"{page}: the footer must sit outside <main>"


# ============ the success page must always offer key recovery actions

class TestSuccessPageKeyRecovery:
    """
    Roadmap 5.3: the Stripe checkout success page must never lose the license
    key. Once the key resolves, the page must offer Copy, Email, Activate, and
    Download actions so the buyer can always recover it.
    """

    def test_success_page_offers_key_recovery_actions(self):
        source = (Path(WEBSITE_DIR) / "success.html").read_text(encoding="utf-8")
        assert 'id="copy-key"' in source, "the Copy license key button is missing"
        assert 'id="email-key"' in source, "the Email me this key button is missing"
        assert 'id="activate-link"' in source, "the Activate in FlowShield button is missing"
        assert 'id="download-link"' in source, "the Download FlowShield button is missing"
        assert "resend-license" not in source or "checkout.js" in source, \
            "the email handler must live in checkout.js, not inline in the HTML"
