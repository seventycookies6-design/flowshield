# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: desktop lifecycle."""

from __future__ import annotations
import re
import struct
import time
from pathlib import Path
import psutil
import pytest
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from core import state_verifier as verify



# =============================================== F23 — the privacy promise

class TestAutomaticUpdateWiring:
    ROOT = Path(DESKTOP_DIR)

    def test_automatic_update_network_request_is_disclosed(self):
        legal = (Path(WEBSITE_DIR) / "legal.html").read_text(encoding="utf-8")
        app = (self.ROOT / "Views" / "SettingsView.xaml").read_text(encoding="utf-8")
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        for text in (legal, app, site):
            for phrase in ("automatic update checks", "GitHub", "once a day", "IP address",
                           "blocklist", "sprints", "turned off in Settings"):
                assert phrase in text
        assert "The only thing that ever leaves this PC" not in app

    def test_feed_is_one_constant_with_the_host_migration_reminder(self):
        source = (self.ROOT / "Services" / "UpdateService.cs").read_text(encoding="utf-8")
        url = "https://github.com/seventycookies6-design/flowshield"
        assert sum(p.read_text(encoding="utf-8").count('"' + url + '"')
                   for p in self.ROOT.rglob("*.cs") if "obj" not in p.parts and "bin" not in p.parts) == 1
        assert re.search(r'const string ReleaseFeed\s*=\s*"' + re.escape(url) + '"', source)
        assert "#166" in source

    def test_local_update_feed_accepts_only_an_existing_absolute_local_directory(self):
        """VM updates must stay local; invalid overrides keep the production feed."""
        source = (self.ROOT / "Services" / "UpdateService.cs").read_text(encoding="utf-8")
        assert re.findall(r'Environment.GetEnvironmentVariable\("([^"]+)"\)', source) == [
            "FLOWSHIELD_UPDATE_FEED"
        ]
        assert 'const string ReleaseFeed = "https://github.com/seventycookies6-design/flowshield";' in source
        constructor = source.split("public UpdateService()", 1)[1].split("catch (Exception", 1)[0]
        assert 'var feedOverride = Environment.GetEnvironmentVariable("FLOWSHIELD_UPDATE_FEED");' in constructor
        selection = re.search(
            r'if\s*\((.*?)\)\s*\{\s*source = new SimpleFileSource\(new DirectoryInfo\(feedOverride\)\);(.*?)\}'
            r'\s*else\s*\{(.*?)\}', constructor, re.S,
        )
        assert selection, "local source must be guarded and have a GitHub fallback"
        condition, local, fallback = selection.groups()
        assert re.sub(r"\s+", " ", condition).strip() == (
            'feedOverride is not null && Path.IsPathFullyQualified(feedOverride) '
            r'&& !feedOverride.StartsWith(@"\", StringComparison.Ordinal) '
            '&& !feedOverride.StartsWith("/", StringComparison.Ordinal) '
            '&& Directory.Exists(feedOverride)'
        )
        assert local.count("Log.Info(") == 1 and "{feedOverride}" in local
        assert 'if (feedOverride is not null)' in fallback
        assert fallback.count("Log.Warn(") == 1
        assert 'source = new GithubSource(ReleaseFeed, null, false);' in fallback
        assert '_manager = new UpdateManager(source);' in constructor

    def test_new_automation_ids_are_on_controls(self):
        import xml.etree.ElementTree as ET
        ap = "{http://schemas.microsoft.com/winfx/2006/xaml/presentation}"
        expected = {"AutoUpdateToggle": "CheckBox", "RestartToUpdateButton": "Button",
                    "WhatsNewCard": "TextBlock", "WhatsNewDismiss": "Button"}
        found = {}
        for name in ("SettingsView.xaml", "TodayView.xaml"):
            for element in ET.parse(self.ROOT / "Views" / name).iter():
                auto_id = element.get("AutomationProperties.AutomationId")
                if auto_id in expected:
                    found[auto_id] = element.tag.removeprefix(ap)
        assert found == expected

    def test_both_apply_paths_are_guarded_by_the_policy(self):
        source = (self.ROOT / "Services" / "UpdateService.cs").read_text(encoding="utf-8")
        quit_path = source.split("public bool ApplyOnQuit(", 1)[1]
        assert quit_path.index("UpdatePolicy.CanApply(activity)") < quit_path.index("WaitExitThenApplyUpdates(")
        assert "silent: true, restart: false" in quit_path
        restart = source.split("public bool ApplyAndRestart(", 1)[1].split("public bool ApplyOnQuit(", 1)[0]
        assert restart.index("UpdatePolicy.CanApply(activity)") < restart.index("ApplyUpdatesAndRestart(")
        settings = (self.ROOT / "ViewModels" / "SettingsViewModel.cs").read_text(encoding="utf-8")
        assert "UpdateReady && _main.CanApplyUpdate" in settings
        assert "if (!_main.CanApplyUpdate)" in settings
        app = (self.ROOT / "App.xaml.cs").read_text(encoding="utf-8")
        assert "ApplyOnQuit(ViewModel.UpdateActivity)" in app.split("protected override void OnExit(", 1)[1]

    def test_a_failed_check_is_not_reported_as_up_to_date(self):
        """A manual check that couldn't reach the feed said the same thing as one
        that found nothing new, so someone offline was told they were current."""
        source = (self.ROOT / "Services" / "UpdateService.cs").read_text(encoding="utf-8")
        check = source.split("public async Task<string?> CheckAndDownloadAsync(", 1)[1]
        check = check.split("public bool ApplyAndRestart(", 1)[0]
        assert check.index("LastCheckFailed = false;") < check.index("CheckForUpdatesAsync()")
        assert "LastCheckFailed = true;" in check.split("catch (Exception", 1)[1]
        settings = (self.ROOT / "ViewModels" / "SettingsViewModel.cs").read_text(encoding="utf-8")
        manual = settings.split("private async Task CheckForUpdatesAsync()", 1)[1].split("finally", 1)[0]
        assert "Updates.LastCheckFailed" in manual
        assert "Couldn't reach the update server" in manual
        assert "You're on the latest version." in manual


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
        # F19 replaced the running icon with a per-minute countdown icon; the
        # branded running icon is still the fallback when drawing one fails.
        assert "_tray.Icon = _trayIdleIcon;" in window, "an idle tray must show the plain brand icon"
        assert "_tray.Icon = _trayRunningIcon;" in window, "the running variant is the countdown's fallback"
        assert "nameof(TodayViewModel.IsRunning)" in window
        assert "_trayIdleIcon?.Dispose()" in window
        assert "_trayRunningIcon?.Dispose()" in window
        assert "SystemIcons.Shield" not in window


# ============== Windows on ARM gets its own build and its own update feed

class TestReleaseShipsAnArm64Build:
    """
    `build_release.ps1` published win-x64 only, so a Snapdragon laptop ran the
    blocker under x64 emulation. It now publishes win-arm64 too, each on its
    own Velopack channel: the updater reads `releases.<channel>.json`, so the
    two builds must never share one, and x64 must keep the default "win"
    channel or every copy installed before ARM64 existed loses its updates.
    """

    def _script(self) -> str:
        return (Path(DESKTOP_DIR).parent / "tools" / "build_release.ps1").read_text(
            encoding="utf-8-sig")

    def test_both_processors_are_published_and_packed(self):
        script = self._script()
        assert "Runtime = 'win-x64'" in script
        assert "Runtime = 'win-arm64'" in script, "no ARM64 build is published"
        assert "-r $t.Runtime" in script, "dotnet publish ignores the target list"
        assert "--runtime $t.Runtime" in script and "--channel $t.Channel" in script, \
            "vpk must pack each build for its own processor and channel"

    def test_x64_keeps_the_channel_existing_installs_update_from(self):
        targets = re.findall(r"Runtime = '([\w-]+)';\s*Channel = '([\w-]+)'", self._script())
        channels = dict(targets)
        assert channels.get("win-x64") == "win", \
            "x64 left the default channel; installed copies would stop finding updates"
        assert channels.get("win-arm64") not in (None, "win"), \
            "ARM64 shares x64's update feed, so one would install the other's build"

    def test_publishing_uploads_both_update_feeds(self):
        publish = self._script().split("gh release create", 1)[1]
        for asset in ("FlowShield-win-Setup.exe", "releases.win.json", "RELEASES'",
                      "FlowShield-$Version-full.nupkg",
                      "FlowShield-win-arm64-Setup.exe", "releases.win-arm64.json",
                      "RELEASES-win-arm64", "FlowShield-$Version-win-arm64-full.nupkg"):
            assert asset in publish, f"{asset} is never uploaded to the release"

    def test_ci_builds_the_arm64_app(self):
        ci = (Path(DESKTOP_DIR).parent / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8")
        assert "-r win-arm64" in ci, "nothing checks that the ARM64 build still compiles"


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
        assert "var isInstalled = ViewModel.Updates.IsSupported;" in app
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
                "Basalt exited instead of staying available in the tray"
            assert not ctrl.main_window_is_visible(), \
                "--tray displayed Basalt's main window"

            tray_icon = ctrl.find_tray_icon()
            assert tray_icon is not None, "FlowShield's notification-area icon is missing"

            tray_icon.double_click_input()
            ctrl.connect_window()
            assert ctrl.main_window_is_visible(), \
                "double-clicking the tray icon did not restore Basalt"
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


class TestQuitEndsAnyRunningSprint:
    """
    #204: closing Basalt during a Soft sprint skipped RequestEnd and left
    the saved sprint active, so the next launch resumed it.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_quit_end_flow_does_not_depend_on_shield_level(self):
        """A Soft sprint must reach RequestEnd when the user quits too."""
        window = self.read("MainWindow.xaml.cs")
        needs_end_flow = window.split("private static bool NeedsEndFlowToQuit", 1)[1].split(";", 1)[0]
        assert "ShieldLevel" not in needs_end_flow, \
            "NeedsEndFlowToQuit must not gate the end flow on ShieldLevel"

        quit_ = window.split("private void Quit()", 1)[1].split("\n    }", 1)[0]
        assert "RequestEnd()" in quit_, "tray Quit must still go through RequestEnd"

    @pytest.mark.ui
    def test_closing_soft_sprint_after_grace_records_it_and_quits(self, fresh_app):
        """A Soft sprint past grace should end early instead of resuming on next launch."""
        fresh_app.navigate_to_tab("Settings")
        fresh_app.set_toggle("MinimizeToTrayToggle", False)   # close really exits
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Soft")
        time.sleep(0.4)
        fresh_app.start_sprint()
        # --short-timers uses EndSprintPolicy.GracePeriod (15 s); the driver's
        # wait includes its five-second margin, so the close is safely past it.
        fresh_app.wait_out_grace_period()

        fresh_app.window.close()                      # WM_CLOSE, like clicking X
        deadline = time.time() + 10
        while time.time() < deadline and psutil.pid_exists(fresh_app.pid):
            time.sleep(0.2)
        assert not psutil.pid_exists(fresh_app.pid), "closing a Soft sprint didn't quit"
        assert not fresh_app.exists("KeepGoingButton", timeout=0.5), \
            "Soft should end immediately without showing the end panel"

        saved = verify.read_settings()
        assert not saved.get("ActiveSprint"), "the ended Soft sprint remained active on disk"
        sessions = saved.get("Sessions", [])
        assert sessions, "the ended Soft sprint was not recorded"
        newest = sessions[-1]
        assert newest.get("Completed") is False, "quitting early must not mark the sprint complete"
        assert newest.get("Interrupted") is False, "a deliberate quit is not an interrupted sprint"
        assert newest.get("EndedUtc"), "the ended-early session needs an EndedUtc timestamp"

    @pytest.mark.ui
    def test_closing_soft_sprint_inside_grace_cancels_and_quits(self, fresh_app):
        """A Soft sprint closed during grace should leave no session to resume or review."""
        fresh_app.navigate_to_tab("Settings")
        fresh_app.set_toggle("MinimizeToTrayToggle", False)   # close really exits
        before = verify.read_settings()
        before_sessions = before.get("Sessions", [])
        fresh_app.navigate_to_tab("Today")
        fresh_app.select_shield("Soft")
        time.sleep(0.4)
        fresh_app.start_sprint()

        fresh_app.window.close()                      # WM_CLOSE, like clicking X
        deadline = time.time() + 10
        while time.time() < deadline and psutil.pid_exists(fresh_app.pid):
            time.sleep(0.2)
        assert not psutil.pid_exists(fresh_app.pid), "closing a Soft sprint inside grace didn't quit"

        saved = verify.read_settings()
        assert not saved.get("ActiveSprint"), "the cancelled Soft sprint remained active on disk"
        assert saved.get("Sessions", []) == before_sessions, \
            "cancelling inside grace must not add a session"


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


# ============ flowshield:// registration must recover after a slow install (#294)

class TestDeepLinkRegistrationRecovery:
    """
    Velopack kills an install hook after 30 seconds. On a slow first cold start
    the hook can miss flowshield:// registration, and nothing retries it. The
    velopack.log line is '[ERROR] Process timed out after 30s and was killed.'.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_refresh_registers_only_when_installed(self):
        link = self.read("Services", "DeepLink.cs")
        match = re.search(
            r"public static void RefreshIfInstalled\(bool isInstalled\)\s*\{(?P<body>.*?)\n    \}",
            link,
            re.DOTALL,
        )
        assert match is not None, "DeepLink must define RefreshIfInstalled(bool isInstalled)"
        body = match.group("body")
        assert re.search(r"if\s*\(\s*!isInstalled\b[^)]*\)\s*return\s*;", body), \
            "RefreshIfInstalled must leave the link registration alone for dev builds"
        assert "Environment.ProcessPath" in body and re.search(r"\bRegister\(", body), \
            "an installed launch must register the current process path"
        # Every start runs this, so a link already pointing here is left as it is:
        # no registry write and no log line on every launch.
        assert "shell\\open\\command" in body and "return;" in body.split("Register(")[0], \
            "RefreshIfInstalled must skip re-registering a link that already points here"

    def test_app_startup_retries_registration_for_installed_copies(self):
        app = self.read("App.xaml.cs")
        startup = app.split("protected override void OnStartup(", 1)[1]
        assert re.search(
            r"DeepLink\.RefreshIfInstalled\(\s*(?:new UpdateService\(\)\.IsSupported|isInstalled)\s*\)",
            startup,
        ), "App.OnStartup must refresh the link registration using the installed-copy check"
        assert "var isInstalled = ViewModel.Updates.IsSupported;" in startup, \
            "App.OnStartup must use the Velopack installed-copy check"

    def test_velopack_install_and_update_hooks_still_register(self):
        program = self.read("Program.cs")
        assert ".OnAfterInstallFastCallback(_ => RegisterLink())" in program
        assert ".OnAfterUpdateFastCallback(_ => RegisterLink())" in program


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
        import winreg

        from config import APP_EXE
        from core.settings_guard import preserve_user_settings, run_app_process

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
                result = run_app_process([str(APP_EXE), "--veloapp-uninstall", "1.0.0"],
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


# ============ opening Basalt twice ran two copies (roadmap 1.3, #49)

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
        # maxsplit=1: since #271 a --reset launch retries TryAcquire, so the
        # region runs from the first attempt to the app starting.
        acquire = main.split("SingleInstance.TryAcquire()", 1)[1].split("new App")[0]
        assert "return;" in acquire

    def test_the_lock_is_per_user_and_survives_a_crash(self):
        single = (Path(DESKTOP_DIR) / "Services" / "SingleInstance.cs").read_text(encoding="utf-8")
        assert "Environment.UserName" in single
        assert "catch (AbandonedMutexException) { owned = true; }" in single, \
            "a copy killed from Task Manager would stop Basalt ever opening again"

    @pytest.mark.ui
    def test_a_second_launch_mid_sprint_changes_nothing(self, fresh_app):
        from core.settings_guard import run_app_process

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
        run_app_process([str(APP_EXE), "--reset"], cwd=str(Path(APP_EXE).parent), timeout=30)
        time.sleep(1.5)

        names = [p.pid for p in psutil.process_iter(["name"])
                 if (p.info["name"] or "").lower() == "flowshield.exe"]
        assert names == [fresh_app.pid], "a second Basalt kept running"
        after = verify.read_settings()
        # LastSeenUtc moves with the heartbeat, so compare what defines the sprint.
        assert after.get("ActiveSprint") and all(
            after["ActiveSprint"][k] == before["ActiveSprint"][k]
            for k in ("StartedUtc", "PlannedMinutes", "Shield")
        ), "the second launch touched the sprint"
        assert fresh_app.exists("StopSprintButton", timeout=3), "the sprint stopped"


# ============================ deleting data survives the shutdown race (#271)

class TestDeleteEverythingRestartRegressions:
    """
    #271: deleting everything cleared the settings file and restarted Basalt,
    but shutdown could save the old in-memory settings back over the deletion,
    and the new --reset process could lose the mutex race with the old process.
    """

    @staticmethod
    def main_method() -> str:
        source = (Path(DESKTOP_DIR) / "Program.cs").read_text(encoding="utf-8")
        return source.split("public static void Main(string[] args)", 1)[1].split(
            "private static void RegisterLink()", 1
        )[0]

    @staticmethod
    def closing_method() -> str:
        source = (Path(DESKTOP_DIR) / "MainWindow.xaml.cs").read_text(encoding="utf-8")
        return source.split("protected override void OnClosing(CancelEventArgs e)", 1)[1].split(
            "base.OnClosing(e);", 1
        )[0]

    def test_delete_restart_does_not_save_the_old_settings_on_close(self):
        """
        In #271, Delete everything removed the settings file and set
        SkipSaveOnExit, but with minimise-to-tray off OnClosing still saved the
        old in-memory settings over the deletion before the reset launch.
        """
        closing = self.closing_method()
        assert re.search(
            r"if\s*\([^)]*SkipSaveOnExit[^)]*\)\s*(?:\{\s*)?"
            r"(?:\w+\??\.)?SaveSettings\s*\(",
            closing,
            re.DOTALL,
        ), "OnClosing must guard its settings save with SkipSaveOnExit after Delete everything"

    def test_reset_launch_retries_the_mutex_before_forwarding_args(self):
        """
        In #271, Delete everything started a fresh --reset process just before
        the old process released its mutex. A single failed attempt forwarded
        --reset to the still-running app and exited, so the reset never ran.
        """
        main = self.main_method()
        reset_index = main.find('"--reset"')
        assert reset_index >= 0, "Program.Main must recognize --reset as a fresh-install launch"

        send_index = main.find("SingleInstance.SendToRunningInstance(args)")
        assert send_index >= 0, "Program.Main must keep forwarding normal second-launch arguments"

        retry_loop = re.search(r"\b(?:for|while)\s*\(", main)
        retry_acquire = (main.find("SingleInstance.TryAcquire()", retry_loop.end())
                         if retry_loop else -1)
        assert retry_loop and retry_acquire >= 0, (
            "Program.Main must retry SingleInstance.TryAcquire in a bounded loop for --reset "
            "while the exiting copy releases its mutex"
        )
        assert reset_index < retry_loop.start() < retry_acquire < send_index, \
            "the --reset mutex retry must run before forwarding arguments to the old instance"


# ============ a crash shows a friendly dialog, not a raw exception dump (roadmap 1.14)

class TestFriendlyErrorDialog:
    """
    An unhandled UI exception used to pop a raw MessageBox with the exception
    message and a log path. It now shows a calm dialog that copies the details
    and links to support.

    The first draft of the dialog said "Basalt is still guarding your
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

        assert "Basalt hit an unexpected error" not in app, \
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
