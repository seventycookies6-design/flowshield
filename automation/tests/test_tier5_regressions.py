"""
Tier 5 — regressions.

One test per bug found by reading the code rather than by running it. Each was
written to fail against the behaviour that shipped, so the suite would have
caught the bug had it existed first.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

import psutil
import pytest

from core.installed_apps import STEAM_INSTALLED
import requests

from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from core import state_verifier as verify

NODE = r"C:\Program Files\nodejs\node.exe"
NODE_EXE = NODE if Path(NODE).exists() else "node"


# ============================ the legal pages must match what the code does

class TestLegalPagesMatchTheProduct:
    """
    `LEGAL_CHECKLIST.md` lists how this product could be sued or fined. The
    items that can be checked by reading the code live here, so they fail CI
    instead of reaching a customer.
    """

    ROOT = Path(DESKTOP_DIR).parent
    LEGAL = Path(WEBSITE_DIR) / "legal.html"

    def checklist(self) -> str:
        return (self.ROOT / "LEGAL_CHECKLIST.md").read_text(encoding="utf-8")

    def test_the_privacy_policy_names_every_kind_of_data_the_app_sends(self):
        """
        The client sends a device id and device name with every licence check.
        Personal data that isn't in the policy is the classic privacy complaint.
        """
        client = (Path(DESKTOP_DIR) / "Services" / "LicenseService.cs").read_text(encoding="utf-8")
        sent = {field for field in ("email", "licenseKey", "deviceId", "deviceName")
                if f"{field} =" in client}
        assert {"deviceId", "deviceName"} <= sent, "the client stopped sending devices; update this test"

        policy = self.LEGAL.read_text(encoding="utf-8").lower()
        assert "device identifier" in policy and "device name" in policy, \
            "the privacy policy must disclose the device identifier and device name"
        assert "email address" in policy

    def test_no_placeholder_is_left_unflagged_on_a_customer_page(self):
        """
        `[operator name]` and friends are still on the site. That is a known gap
        (checklist 1.1), so the rule is: if a placeholder exists it must be
        flagged there; if it's filled in, the checklist must stop calling it a gap.
        """
        import re

        pages = {p.name: p.read_text(encoding="utf-8") for p in Path(WEBSITE_DIR).glob("*.html")}
        found = {m for text in pages.values() for m in re.findall(r"\[[a-z][a-z ]+\]", text)}
        checklist = self.checklist()

        for placeholder in found:
            assert placeholder in checklist, \
                f"{placeholder} is on the site but not flagged in LEGAL_CHECKLIST.md"
        if not found:
            assert "**GAP / OWNER** — `legal.html` still says" not in checklist, \
                "the placeholders are filled in; update checklist item 1.1"

    def test_the_site_does_not_promise_tax_handling_the_server_does_not_do(self):
        # "Plus sales tax where it applies" was on the pricing card while
        # Stripe Tax was off, so no tax was ever calculated or charged.
        server = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")
        index = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8").lower()
        if "automatic_tax" not in server:
            assert "sales tax" not in index and "vat" not in index, \
                "the site claims tax is handled at checkout, but Stripe Tax is not enabled"

    def test_the_terms_state_a_minimum_age(self):
        terms = self.LEGAL.read_text(encoding="utf-8").lower()
        assert "at least 13 years old" in terms, \
            "COPPA exposure: the terms must set a minimum age"

    def test_the_policy_names_its_subprocessors(self):
        policy = self.LEGAL.read_text(encoding="utf-8")
        for name in ("Stripe", "Render", "Resend"):
            assert name in policy, f"{name} processes customer data and must be named"

    def test_the_terms_gate_covers_every_other_panel(self):
        """
        A gate under the lock screen or the welcome could be worked around, and
        an agreement nobody had to pass is the browsewrap this replaced.
        """
        window = (Path(DESKTOP_DIR) / "MainWindow.xaml").read_text(encoding="utf-8-sig")
        gate = window.find('AutomationId="TermsGatePanel"')
        assert gate > 0
        for panel in ('AutomationId="TrialEndedPanel"', 'AutomationId="FirstRunPanel"',
                      "ActivationPromptVisible"):
            assert window.find(panel) < gate, f"{panel} is drawn after the terms gate"

    def test_nothing_starts_while_the_terms_are_unaccepted(self):
        # The overlay only stops a mouse; a covered button can still be invoked
        # by automation or a shortcut, so the refusal lives in the view model.
        today = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        start = today.split("private void StartSprint()")[1].split("\n    }")[0]
        assert "_main.TermsGateVisible" in start and "return;" in start

    def test_acceptance_is_recorded_before_the_gate_closes(self):
        main = (Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs").read_text(encoding="utf-8")
        accept = main.split("private void AcceptTerms()")[1].split("\n    }")[0]
        assert accept.index("SaveSettings()") < accept.index("TermsGateVisible = false"), \
            "a crash between accepting and saving would ask again with no record"
        assert "FirstRun.ShowIfNew()" in accept

    def test_the_test_flag_skips_the_screen_but_not_the_record(self):
        app = (Path(DESKTOP_DIR) / "App.xaml.cs").read_text(encoding="utf-8")
        flag = app.split('"--accept-terms"')[1].split("// The terms come first")[0]
        assert "LegalTerms.Accept(" in flag, \
            "the flag must record acceptance, not bypass the check"

    def test_the_checklist_is_reviewed_with_the_release_script(self):
        rules = (self.ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        assert "LEGAL_CHECKLIST.md" in rules, \
            "every agent must be told to re-check the legal list before a release or publish"


# =============================================== F23 — the privacy promise

class TestPrivacyClaimsMatchTheCode:
    """
    F23: every privacy sentence on the site's #privacy section, in the app's
    Settings -> Your data card, and in legal.html's privacy policy is tied to
    a code marker here. Add a marker when the copy changes; do not weaken a
    claim just to make the test pass.
    """

    SITE = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
    LEGAL = (Path(WEBSITE_DIR) / "legal.html").read_text(encoding="utf-8")
    SETTINGS_VIEW = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(encoding="utf-8")
    LICENSE_SERVICE = (Path(DESKTOP_DIR) / "Services" / "LicenseService.cs").read_text(encoding="utf-8")
    SETTINGS_SERVICE = (Path(DESKTOP_DIR) / "Services" / "SettingsService.cs").read_text(encoding="utf-8")
    DATA_PRIVACY = (Path(DESKTOP_DIR) / "Services" / "DataPrivacyService.cs").read_text(encoding="utf-8")
    SETTINGS_VM = (Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs").read_text(encoding="utf-8")

    def test_site_has_a_privacy_section_before_the_faq(self):
        assert '<section id="privacy">' in self.SITE
        assert self.SITE.index('<section id="privacy">') < self.SITE.index('<section id="faq"'), \
            "the privacy section must sit before the FAQ (F23 brief)"

    def test_site_claims_are_backed_by_code(self):
        assert "Your data stays on your PC" in self.SITE
        assert "encrypted with Windows DPAPI" in self.SITE
        assert "ProtectedData.Protect" in self.SETTINGS_SERVICE, \
            "the site claims DPAPI encryption, but settings are no longer protected with it"

    def test_app_card_claims_are_backed_by_code(self):
        assert 'AutomationId="WhatLeavesText"' in self.SETTINGS_VIEW
        assert "encrypted with Windows DPAPI" in self.SETTINGS_VIEW

        # Export and delete controls exist and are wired to real commands.
        assert 'AutomationId="ExportDataButton"' in self.SETTINGS_VIEW
        assert 'Command="{Binding ExportDataCommand}"' in self.SETTINGS_VIEW
        assert 'AutomationId="DeleteEverythingButton"' in self.SETTINGS_VIEW
        assert 'Command="{Binding DeleteEverythingCommand}"' in self.SETTINGS_VIEW
        assert 'Style="{StaticResource BtnDanger}"' in self.SETTINGS_VIEW.split(
            'AutomationId="DeleteEverythingButton"')[0][-400:], \
            "Delete everything must use the destructive button style (DESIGN_SYSTEM.md §7)"

    def test_legal_html_can_see_and_remove_devices_is_backed_by_code(self):
        """
        legal.html already promised "you can see and remove your own
        devices" before Roadmap 5.7 built that feature — rule #5 ("never
        claim a feature the shipped build doesn't have") means that promise
        had to become true in this PR, not just stay written down.
        """
        assert "see and remove your own devices" in self.LEGAL.lower()
        assert 'AutomationId="DevicesList"' in self.SETTINGS_VIEW
        assert 'Binding DataContext.ConfirmReleaseCommand' in self.SETTINGS_VIEW
        assert "ListDevicesAsync" in self.LICENSE_SERVICE
        assert "ReleaseDeviceAsync" in self.LICENSE_SERVICE

    def _what_leaves_text(self) -> str:
        """Just the WhatLeavesText control's own Text attribute, not the whole
        Settings page — "email" also appears in the unrelated LicenseEmailInput
        label, which would let an omission here pass unnoticed."""
        tag = re.search(
            r'<TextBlock\b[^>]*AutomationProperties\.AutomationId="WhatLeavesText"[^>]*/>',
            self.SETTINGS_VIEW)
        assert tag, "the WhatLeavesText control is missing from SettingsView.xaml"
        text = re.search(r'Text="([^"]*)"', tag.group(0))
        assert text, "WhatLeavesText has no Text attribute"
        return text.group(1).lower()

    def _privacy_section_body(self) -> str:
        """Just the #privacy section's own markup, not the whole page — "email"
        also appears in the pricing section's checkout copy."""
        section = re.search(r'<section id="privacy">(.*?)</section>', self.SITE, re.DOTALL)
        assert section, "the site's #privacy section is missing"
        return section.group(1).lower()

    def _legal_what_we_collect(self) -> str:
        """The "What we collect" block of the privacy policy, which is where
        the licence key, email, device identifier and device name are all
        actually disclosed — not the whole page."""
        block = re.search(r"<h3>What we collect</h3>(.*?)<h3>", self.LEGAL, re.DOTALL)
        assert block, 'legal.html\'s "What we collect" section is missing'
        return block.group(1).lower()

    def test_the_field_list_is_derived_from_the_code_and_disclosed_everywhere(self):
        """
        Reads the actual fields the client sends in POST /validate straight out
        of LicenseService.cs, then requires a phrase for every one of them —
        the mapping below has to be kept in step or this test itself fails —
        and checks each phrase appears on the site, in the app card and in the
        privacy policy. Each check is scoped to the disclosure text itself
        (the WhatLeavesText control, the #privacy section body, the "What we
        collect" block), not the whole file — the word "email" also shows up
        in LicenseEmailInput's label and the pricing section, and checking the
        whole page let a card that dropped "email" from WhatLeavesText still
        pass. Add a field to the payload without updating the copy anywhere
        this checks, and this is what catches it.
        """
        # Matched up to the anonymous object's own closing brace (it has no
        # nested braces), not a fixed "});" suffix — Roadmap 5.2 added a
        # per-attempt CancellationToken argument after the object literal,
        # so the call no longer ends in "});".
        match = re.search(
            r"_http\.PostAsJsonAsync\(url, new\s*\{(.*?)\}",
            self.LICENSE_SERVICE, re.DOTALL)
        assert match, "could not find the /validate PostAsJsonAsync call in LicenseService.cs"
        sent_fields = set(re.findall(r"(\w+)\s*=", match.group(1)))
        assert sent_fields == {"licenseKey", "email", "deviceId", "deviceName"}, (
            "the licence check's field list changed in LicenseService.cs; update the "
            "phrase map in this test and the privacy copy on the site, in the app "
            "card and in legal.html in the same PR"
        )

        phrase_for_field = {
            "licenseKey": "licence key",
            "email": "email",
            "deviceId": "device identifier",
            "deviceName": "device name",
        }
        assert set(phrase_for_field) == sent_fields, \
            "every field the client sends needs a disclosed phrase mapped here"

        surfaces = {
            "the site's #privacy section": self._privacy_section_body(),
            "the app's Your data card (WhatLeavesText)": self._what_leaves_text(),
            "legal.html's \"What we collect\" block": self._legal_what_we_collect(),
        }
        for surface_name, text in surfaces.items():
            for field, phrase in phrase_for_field.items():
                assert phrase in text, (
                    f"{surface_name} does not mention {phrase!r}, but the client sends "
                    f"{field!r} on every licence check"
                )

    def test_export_never_includes_the_licence_key(self):
        export_method = self.DATA_PRIVACY.split("public static void Export(")[1].split(
            "public static async Task DeleteEverythingAsync(")[0]
        assert "LicenseKey" not in export_method, \
            "the data export must never include the licence key"
        assert "licence key is deliberately not included" in export_method.lower() \
            or "licenseKey is deliberately not included" in export_method

    def test_delete_everything_releases_the_seat_first(self):
        delete_method = self.DATA_PRIVACY.split("DeleteEverythingAsync(")[-1]
        assert "DeactivateAsync" in delete_method
        assert "settingsService.Reset()" in delete_method

    def test_legal_privacy_policy_matches_the_same_fields(self):
        policy = self.LEGAL.lower()
        assert "device identifier" in policy and "device name" in policy
        assert "email address" in policy
        assert "dpapi" in policy
        assert "none of it is uploaded" in policy or "is stored locally" in policy

    def test_delete_everything_cannot_escape_a_running_sprint(self):
        """
        A sealed sprint locks the blocklist so it can't be escaped; relaunching
        the app to delete everything would drop the shield entirely, same as
        the update-restart path this mirrors. Checked in three places: the
        command's CanExecute, an inline refusal inside the handler (in case a
        covered or automation-invoked control bypasses CanExecute, per
        CLAUDE.md's "covered controls" gotcha), and a visible reason in the UI.
        """
        can_execute = self.SETTINGS_VM.split("DeleteEverythingCommand = new AsyncRelayCommand(")[1].split(";")[0]
        assert "_main.IsSprintRunning" in can_execute, \
            "DeleteEverythingCommand must refuse to run while a sprint is active"

        handler = self.SETTINGS_VM.split("private async Task DeleteEverythingAsync()")[1].split("\n    }")[0]
        assert "if (_main.IsSprintRunning)" in handler, \
            "the handler must also refuse inline, not rely on CanExecute alone"
        guard = handler.split("if (_main.IsSprintRunning)")[1].split("ConfirmDeleteDialog")[0]
        assert "return;" in guard, "the inline guard must actually stop execution"
        assert "ConfirmDeleteDialog" in handler, "the confirm dialog must still be shown otherwise"

        assert 'AutomationId="DeleteEverythingBlockedText"' in self.SETTINGS_VIEW
        caption = self.SETTINGS_VIEW.split('AutomationId="DeleteEverythingBlockedText"')[0][-800:]
        assert "IsSprintRunning" in caption, \
            "the caption must be bound to sprint state, not a static warning"


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
            # "journal export" came off this list when F17 shipped it — the site
            # now says "Export your journal to CSV or Markdown", which the build
            # backs (JournalExport + the Settings card).
            "youtube.com", "momentum analytics",
            "full-screen reminder", "can't unlock it early",
            "escape hatch is gone", "no three-second grace window",
            "months later", "nothing is uploaded", "dismissible reminder",
            "until the timer ends",
        ):
            assert claim not in site, f"the site still claims unshipped behaviour: {claim}"


class TestFirmWarnsBeforeItCloses:
    """
    F7 / roadmap 1.8. The site's legal page and the app have to agree about
    whether anything is closed without warning, because one of them is a
    promise to a customer.
    """

    SERVICE = Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs"

    def test_the_kill_is_never_the_first_thing_tried(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        sweep = source.split("private void Tick", 1)[1]
        graceful = sweep.split("if (!graceful)", 1)[1]
        # Inside the graceful branch, the ask must come before any Kill.
        ask = graceful.index("CloseMainWindow()")
        kill = graceful.index("KillAll(processes, shield);", ask)
        assert ask < kill

    def test_hard_kill_still_skips_the_warning(self):
        """
        The setting exists precisely so there is no window to slip through.
        Making it polite would quietly remove the feature people bought.
        """
        source = self.SERVICE.read_text(encoding="utf-8")
        assert "GracefulClose.IsGraceful(shield, hardKill)" in source
        model = (Path(DESKTOP_DIR) / "Models" / "GracefulClose.cs").read_text(
            encoding="utf-8")
        assert "!hardKill && shield >= ShieldLevel.Firm" in model

    def test_the_legal_page_describes_the_warning_and_its_limits(self):
        legal = (Path(WEBSITE_DIR) / "legal.html").read_text(encoding="utf-8")
        flat = " ".join(legal.split())
        assert "closed without warning" not in flat, (
            "the app warns now; the old blanket wording is no longer true"
        )
        assert "asks the application to close itself" in flat
        assert "Hard kill mode deliberately skips all of this" in flat
        assert "A warning is not a guarantee" in flat, (
            "an app that ignores the request can still lose work, and the page "
            "must not over-promise"
        )

    def test_the_warning_notification_can_be_turned_off_like_every_other(self):
        """F19's rule: everything FlowShield can interrupt with is switchable."""
        settings_xaml = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(
            encoding="utf-8")
        assert 'AutomationId="NotifyAppClosingToggle"' in settings_xaml

    def test_the_warning_is_allowed_to_interrupt_a_sprint(self):
        """
        Every other notice waits. This one cannot: a warning that arrives after
        the app has closed is not a warning.
        """
        notifications = (Path(DESKTOP_DIR) / "Models" / "Notifications.cs").read_text(
            encoding="utf-8")
        interrupts = notifications.split("public static bool InterruptsFocus", 1)[1]
        interrupts = interrupts.split(";", 1)[0]
        assert "AppClosing" not in interrupts, (
            "AppClosing must not be in the list of notices suppressed during a sprint"
        )


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
        # 1.0.10: the notice has a Close button, so the promise says who decides.
        assert "unless you choose to close it" in readme
        assert "unless you choose to close it" in model

    def test_legal_page_distinguishes_soft_from_closing_modes(self):
        source = (Path(WEBSITE_DIR) / "legal.html").read_text(encoding="utf-8")
        legal = " ".join(source.split())

        assert "Soft records the" in legal and "leaves the application running" in legal
        assert "unless you choose Close on its notice" in legal
        assert "Firm and Sealed close it" in legal
        assert "Any unsaved work in an application FlowShield closes may be lost" in legal

    def test_the_site_and_the_legal_page_name_every_button_on_the_notice(self):
        """
        Both pages told the reader to "choose Close" after listing only Back
        to work and Allow 5 minutes -- a button the sentence never named. The
        notice has three, and the one that can close something comes first.
        """
        for name in ("index.html", "legal.html"):
            page = " ".join((Path(WEBSITE_DIR) / name).read_text(encoding="utf-8").split())
            assert "with Close, Back to work and Allow 5 minutes" in page, (
                f"{name} must list the notice's three buttons, Close first"
            )

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

        # 1.0.10: the notice has Close, so the template that regenerates
        # FINAL_REPORT.md carries README's qualifier. The checked-in
        # FINAL_REPORT.md itself is a record of a past run and is left alone.
        template = (root / "automation" / "make_report.py").read_text(encoding="utf-8")
        assert "the blocked app keeps running unless you choose to close it" in template
        checklist = (root / "LAUNCH_FEATURE_CHECKLIST.md").read_text(encoding="utf-8")
        f7 = " ".join(checklist.split("### F7", 1)[1].split("\n### ", 1)[0].split())
        assert "It closes nothing" not in f7, "F7 still makes the pre-1.0.10 promise"
        assert "never closes anything on its own" in f7
        assert "1.0.10" in f7 and "Close" in f7, "F7 must record what 1.0.10 added to the notice"


# ============================ one shield wording, everywhere (F1, #93)

class TestShieldWordingIsCanonical:
    """
    F1 gave the shields a one-line promise and a "best for" scenario. The
    wording lives once, in Models/ShieldCopy.cs, and Today and the first
    run bind to it — so the two screens and the website can't drift apart.
    """

    PROMISES = (
        "Notes distractions and nudges you.",
        "Closes blocked apps.",
        "Closes apps and locks the list until the sprint ends.",
    )
    BEST_FOR = (
        "Best for classes or light work.",
        "Best for homework.",
        "Best for exams and deep work.",
    )

    def _shield_source(self) -> str:
        path = Path(DESKTOP_DIR) / "Models" / "ShieldCopy.cs"
        assert path.exists(), "ShieldCopy.cs is the single source for shield wording (F1)"
        return path.read_text(encoding="utf-8")

    def test_every_shield_has_a_promise_and_a_scenario(self):
        source = " ".join(self._shield_source().split())
        for phrase in (*self.PROMISES, *self.BEST_FOR):
            assert phrase in source, f"canonical shield wording lost {phrase!r}"

    def test_the_app_surfaces_bind_to_the_single_source(self):
        today_vm = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert "ShieldCopy.Promise(SelectedShield)" in " ".join(today_vm.split())
        first_vm = (Path(DESKTOP_DIR) / "ViewModels" / "FirstRunViewModel.cs").read_text(encoding="utf-8")
        for level in ("Soft", "Firm", "Sealed"):
            assert f"ShieldCopy.Promise(ShieldLevel.{level})" in " ".join(first_vm.split())
        for xaml in Path(DESKTOP_DIR).rglob("*.xaml"):
            text = xaml.read_text(encoding="utf-8")
            for old in ("Blocked apps get a nudge you can dismiss.",
                        "Blocked apps are closed on sight."):
                assert old not in text, f"{xaml.name} still carries its own shield wording"

    def test_the_scenarios_match_the_site(self):
        """The site's shield section is where the scenarios come from."""
        site = " ".join((Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8").split())
        source = " ".join(self._shield_source().split()).lower()
        for scenario in ("classes", "homework", "deep work"):
            assert scenario in source, f"the app's shield wording lost {scenario!r}"
            assert scenario in site.lower(), f"the site's shield section lost {scenario!r}"
        assert "until the sprint ends" in source
        assert "the blocklist locks until the sprint ends" in site


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


# ==================================== checkout works under Managed Payments

class TestCheckoutManagedPayments:
    """
    Stripe rejects `custom_text` outright once Managed Payments is enabled
    (on by default for newer accounts — see the tax-code comment in
    tools/setup_stripe_store.js for the same default hitting another field):
    every /create-checkout call returned a 500 for every buyer, "custom_text
    cannot be used with Managed Payments". Managed Payments is kept on rather
    than disabled per-request, matching that script's choice, so custom_text
    must simply never be sent — not merely toggled off with
    managed_payments[enabled]=false.

    Unit-by-source and stripe-key-free on purpose: this is exactly the class
    of bug CI cannot catch (CI has no keys) but that breaks every real
    checkout, so the regression test must not depend on keys either.
    """

    def test_create_checkout_never_sends_custom_text(self):
        source = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")
        create_checkout = source.split("app.post('/create-checkout'")[1].split("\napp.post(")[0]
        assert "custom_text:" not in create_checkout, (
            "custom_text cannot be used once Managed Payments is enabled; "
            "Stripe rejects the whole checkout session with a 500 for every buyer"
        )
        assert "consent_collection" in create_checkout, (
            "the terms-of-service consent checkbox must still be requested"
        )


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

    #197 widened this: the Firm floor used to be applied only when no sprint
    was running, so a Soft sprint through the night switched the nightly block
    off. The assertion now holds the floor itself rather than the one line that
    used to express it -- TestTheSleepWindowNeverDropsBelowFirm has the detail.
    """

    def test_sleep_window_closes_apps(self):
        source = (Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs").read_text(
            encoding="utf-8")
        tick = source.split("private void Tick()")[1].split("\n    }")[0]
        assert re.search(r"if \(sleepActive[^)]*\) shield = ShieldLevel\.Firm;", tick), \
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


# ============ Roadmap 5.2 — honest waiting while the licence server wakes

class TestHonestWaitingNeverClaimsInvalidKey:
    """
    A timeout while the Render free instance wakes up must never be worded
    like a rejected key. Before this fix, the UI's headline was always
    "❌ Not activated" regardless of whether the server rejected the key
    or was simply unreachable, and the retry loop gave up after one short,
    undelayed retry with no distinction between "the key is wrong" and
    "the host hasn't woken up yet".
    """

    def test_activate_view_model_treats_transport_failure_differently(self):
        source = (Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs").read_text(
            encoding="utf-8")
        activate = source.split("private async Task ActivateAsync")[1].split(
            "\n    private async Task DeactivateAsync")[0]

        assert "IsTransportFailure" in activate, (
            "ActivateAsync must branch on whether the failure was a transport "
            "problem before choosing its headline"
        )
        assert "Couldn't reach the licence server" in activate, (
            "a timeout/connection failure needs its own honest headline, "
            "distinct from a rejected key"
        )
        # The rejection headline must stay reachable, but only from the
        # non-transport branch.
        not_activated_index = activate.index('"❌ Not activated"')
        transport_index = activate.index("IsTransportFailure")
        assert transport_index < not_activated_index, (
            "the transport-failure branch must be checked before falling "
            "through to the generic rejection headline"
        )

    def test_license_service_never_maps_a_timeout_to_a_rejection_reason(self):
        source = (Path(DESKTOP_DIR) / "Services" / "LicenseService.cs").read_text(
            encoding="utf-8")
        validate = source.split("public async Task<LicenseResult> ValidateAsync")[1].split(
            "\n    /// <summary>Silent re-check")[0]

        # Every path that gives up on the transport (response stays null)
        # must return through LicenseResult.Failure, never construct a
        # definitive rejection.
        unreachable_branch = validate.split("if (response is null)")[1].split(
            "using var _ = response;")[0]
        assert "LicenseResult.Failure" in unreachable_branch
        assert "Definitive: true" not in unreachable_branch

    def test_retry_schedule_is_the_shared_pure_helper(self):
        """Tier 1 unit-tests LicenseWaitCopy directly; this pins that the
        retry loop actually uses it rather than duplicating its own numbers."""
        source = (Path(DESKTOP_DIR) / "Services" / "LicenseService.cs").read_text(
            encoding="utf-8")
        validate = source.split("public async Task<LicenseResult> ValidateAsync")[1].split(
            "\n    /// <summary>Silent re-check")[0]

        assert "LicenseWaitCopy.TotalAttempts" in validate
        assert "LicenseWaitCopy.TimeoutForAttempt" in validate
        assert "LicenseWaitCopy.RetryDelaysSeconds" in validate
        assert "LicenseWaitCopy.MessageFor" in validate


class TestActivateButtonStaysDisabledWhileBusy:
    """
    AsyncRelayCommand.CanExecute returns false while its task is in flight, so
    binding the button to it is what keeps it disabled during the (now much
    longer, retrying) activation wait. If a future change swapped
    ActivateCommand for a plain RelayCommand, or the button stopped binding to
    it, the disabled-while-busy guarantee would silently disappear.
    """

    def test_activate_command_is_the_reentrancy_safe_async_command(self):
        vm = (Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs").read_text(
            encoding="utf-8")
        assert "AsyncRelayCommand ActivateCommand" in vm, (
            "ActivateCommand must stay an AsyncRelayCommand, whose CanExecute "
            "is false for the whole duration of ActivateAsync"
        )

    def test_async_relay_command_disables_itself_while_running(self):
        mvvm = (Path(DESKTOP_DIR) / "Infrastructure" / "Mvvm.cs").read_text(
            encoding="utf-8")
        can_execute = mvvm.split("public bool CanExecute(object? parameter) => !_running")
        assert len(can_execute) == 2, (
            "AsyncRelayCommand.CanExecute must gate on !_running so a "
            "long-running Activate click can't be double-fired"
        )

    def test_activate_button_binds_to_the_async_command(self):
        xaml = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(
            encoding="utf-8")
        button = xaml.split('AutomationId="ActivateProButton"')[0][-400:]
        assert 'Command="{Binding ActivateCommand}"' in button

    def test_busy_state_is_visible_on_the_licence_card(self):
        xaml = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(
            encoding="utf-8")
        assert 'AutomationId="LicenseBusyText"' in xaml
        assert 'Visibility="{Binding IsBusy, Converter={StaticResource BoolVis}}"' in xaml


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

        automation = Path(__file__).resolve().parent.parent
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
        # Recovery only presented an email, not the wiped key, so it is free to
        # mint a fresh license_key rather than reuse the forgotten one — that
        # guarantee is test_recovery_keeps_the_key_the_customer_already_has's
        # job, which does present the key. Look the rebuilt row up by email.
        rebuilt = json.loads(_db_admin("by-email", row["email"]) or "null")
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

    def test_the_pricing_says_what_actually_happens_about_tax(self):
        """
        The card used to say "plus sales tax … shown at checkout" while Stripe
        Tax was off, so no tax was ever added: the price shown was the price
        charged. Whichever is true, the card has to say that one.
        """
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        pricing = site.split('<section id="pricing">', 1)[1].split("</section>", 1)[0].lower()
        server = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")

        if "automatic_tax" in server:
            assert "tax" in pricing, "Stripe Tax is on, so say tax is added at checkout"
        else:
            assert "the price you see is the price you pay" in pricing
            assert "sales tax" not in pricing

    def test_the_stripe_product_description_is_true_and_kept_current(self):
        script = (Path(DESKTOP_DIR).parent / "tools" / "setup_stripe_store.js").read_text(encoding="utf-8")
        description = script.split("const PRODUCT_DESCRIPTION =", 1)[1].split(";", 1)[0]
        assert "analytics" not in description and "unlimited history" not in description.lower()
        assert "existing.description !== PRODUCT_DESCRIPTION" in script, \
            "re-running the setup script must correct an existing product's description"

    def test_the_app_describes_sealed_accurately(self):
        desktop = Path(DESKTOP_DIR)
        sources = [p.read_text(encoding="utf-8")
                   for p in desktop.rglob("*.cs")]
        assert all("until the timer ends" not in source for source in sources)
        shields = (desktop / "Models" / "ShieldCopy.cs").read_text(encoding="utf-8")
        assert "until the sprint ends" in shields

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
        # F20 extended this to also hold off while the sprint's summary card
        # is still on screen — see TestTrialNeverNagsDuringASprint below.
        # F5 widened the guard again: IsFocusInProgress is a running sprint plus
        # the break that follows one.
        assert "if (IsFocusInProgress || Today.JournalPromptVisible) return;" in refresh

    def test_the_expire_trial_flag_only_takes_access_away(self):
        app = self.read("DesktopApp", "App.xaml.cs")
        block = app.split('"--expire-trial"')[1].split("\n        }")[0]
        assert "IsPro" not in block, "a command-line flag must never grant a licence"

    def test_the_expire_trial_in_flag_cannot_grant_or_extend_a_trial(self):
        # --expire-trial-in=<seconds> (added for F20's tier 3 coverage) must
        # hold the same invariant as --expire-trial: it may only pull the
        # trial's start earlier, never move it later. An unbounded seconds
        # value (e.g. --expire-trial-in=99999999) would otherwise compute a
        # start in the future and hand out a fresh trial.
        app = self.read("DesktopApp", "App.xaml.cs")
        block = app.split("var expireInArg = args.FirstOrDefault(")[1].split(
            "// The first-run welcome")[0]
        assert "IsPro" not in block, "a command-line flag must never grant a licence"
        assert "candidateStart < currentTrialStart" in block, \
            "the new start must only be applied when it is earlier than the current one"
        assert "ViewModel.Settings.TrialStartedUtc is { } currentTrialStart" in block, \
            "with no trial started yet, the flag must be ignored rather than starting one"

    @pytest.mark.parametrize("current_start_days_ago,seconds,expect_applied", [
        (0, 5, True),           # a few seconds into a fresh trial: pulls it in, as intended
        (0, 604_800, False),    # exactly TrialDays worth of seconds: start would equal "now", not earlier
        (0, 99_999_999, False), # a huge value: start would land far in the future — the reported bug
        (3, 500_000, False),    # already 3 days into the trial; this value would push the start later
        (6, 10, True),          # deep into the trial: still allowed to pull it in further
    ])
    def test_expire_trial_in_never_moves_the_start_later(self, current_start_days_ago, seconds, expect_applied):
        """Mirror of the fixed App.xaml.cs block: candidateStart is only ever applied when earlier."""
        trial_days = 7
        now = datetime.now(timezone.utc)
        current_start = now - timedelta(days=current_start_days_ago)
        candidate_start = now - timedelta(days=trial_days) + timedelta(seconds=seconds)
        applied = candidate_start < current_start
        assert applied is expect_applied
        if applied:
            assert candidate_start < current_start, "a bug here would let the trial restart or extend"

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
        """
        F21 moved the Tokens merge out of Theme.xaml and into App.xaml, so the
        dictionary can be swapped at run time; a second merge anywhere else
        would shadow the swapped one. Theme.xaml still must not define a colour
        of its own.
        """
        theme = (Path(DESKTOP_DIR) / "Styles" / "Theme.xaml").read_text(encoding="utf-8")
        app = (Path(DESKTOP_DIR) / "App.xaml").read_text(encoding="utf-8")
        assert '<ResourceDictionary Source="Styles/Tokens.xaml"/>' in app
        assert '<ResourceDictionary Source="Tokens.xaml"/>' not in theme, \
            "Theme.xaml must not merge the tokens itself -- it would shadow the swapped dictionary"
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
        end = self.today().split("private void EndSprint(bool completed, bool interrupted = false)")[1].split("\n    }")[0]
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


class TestQuitEndsAnyRunningSprint:
    """
    #204: closing FlowShield during a Soft sprint skipped RequestEnd and left
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
        assert "new UpdateService().IsSupported" in startup, \
            "App.OnStartup must use the Velopack installed-copy check"

    def test_velopack_install_and_update_hooks_still_register(self):
        program = self.read("Program.cs")
        assert ".OnAfterInstallFastCallback(_ => RegisterLink())" in program
        assert ".OnAfterUpdateFastCallback(_ => RegisterLink())" in program


# ============ FlowShield never nagged, and never told you anything either (F19, #95)

class TestNotificationsStayQuiet:
    """
    The only notification used to be "still guarding" on minimise. Adding them
    risks the opposite problem, so the quiet rules are pinned here.
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_nothing_about_buying_reaches_a_running_sprint(self):
        main = self.read("ViewModels", "MainViewModel.cs")
        notify = main.split("public bool Notify(")[1].split("\n    }")[0]
        # IsFocusInProgress is a running sprint plus the break that follows one
        # (F5); before breaks existed this passed IsSprintRunning.
        assert "NotificationPolicy.ShouldShow(kind, Settings, IsFocusInProgress)" in notify, \
            "every notification must go through the policy, with the sprint state"

    def test_the_trial_notice_happens_once_a_day_at_most(self):
        main = self.read("ViewModels", "MainViewModel.cs")
        trial = main.split("public void MaybeNotifyTrialEnding()")[1].split("\n    }")[0]
        assert "TrialEndingNotifiedLocal?.Date == today" in trial
        assert trial.index("if (!Notify(") < trial.index("TrialEndingNotifiedLocal = today"), \
            "a notice suppressed during a sprint must still be shown afterwards"

    def test_five_minutes_left_fires_once_per_sprint(self):
        today = self.read("ViewModels", "TodayViewModel.cs")
        assert "_endingSoonNotified = false;" in today.split("private void BeginRunning(")[1], \
            "the flag must reset when a sprint starts, or only the first sprint ever notifies"
        tick = today.split("private void OnTick()")[1].split("\n    }")[0]
        assert "!_endingSoonNotified" in tick and "_endingSoonNotified = true;" in tick

    def test_the_countdown_icon_frees_its_handle(self):
        window = self.read("MainWindow.xaml.cs")
        countdown = window.split("private static System.Drawing.Icon? CountdownIcon(")[1].split("\n    }")[0]
        assert "DestroyIcon(handle)" in countdown, \
            "GetHicon leaks a GDI handle every minute of every sprint without this"

    def test_the_tray_icon_and_title_follow_the_countdown(self):
        window = self.read("MainWindow.xaml.cs")
        changed = window.split("private void OnTodayChanged(")[1].split("\n    }")[0]
        assert "nameof(TodayViewModel.Remaining)" in changed
        update = window.split("private void UpdateTrayIcon()")[1].split("\n    }")[0]
        assert "NotificationPolicy.TrayIconText(remaining)" in update
        # F5 put a break ahead of the sprint countdown in the same expression:
        # "Break · 4:59" while one runs, the sprint's time left otherwise.
        assert 'running ? $"FlowShield — {Vm?.Today.RemainingText}"' in update
        assert ': "FlowShield";' in update
        assert 'onBreak ? $"FlowShield — {NotificationPolicy.BreakLabel(remaining)}"' in update

    def test_the_tray_search_only_trusts_explorer(self):
        # A Claude desktop session titled "FlowShield …" was double-clicked as
        # if it were the tray icon; any app can show a button with that name.
        controller = (Path(DESKTOP_DIR).parent / "automation" / "desktop" / "app_controller.py").read_text(
            encoding="utf-8")
        find = controller.split("def find_tray_icon(")[1].split("\n    def ")[0]
        assert "element.process_id in explorer" in find

    def test_the_test_driver_matches_the_countdown_title(self):
        controller = (Path(DESKTOP_DIR).parent / "automation" / "desktop" / "app_controller.py").read_text(
            encoding="utf-8")
        assert "WINDOW_TITLE_RE" in controller and "title_re=WINDOW_TITLE_RE" in controller


# ==================== a trial that never nags (F20, #9) =====================

class TestTrialNeverNagsDuringASprint:
    """
    The trial is reduced to exactly three surfaces (checklist F20): the
    sidebar tier badge, one "1 day left" notice on the last day, and the lock
    screen after the trial ends. None of the three may reach a running sprint,
    or the sprint's summary card, source-level — not just "the panel doesn't
    happen to render on top".
    """

    @staticmethod
    def read(*parts) -> str:
        return (Path(DESKTOP_DIR).joinpath(*parts)).read_text(encoding="utf-8")

    def test_every_notification_is_gated_on_sprint_state(self):
        # Belt-and-braces with TestNotificationsStayQuiet above: Notify() is
        # the single chokepoint every NotificationKind (including TrialEnding)
        # goes through, and it always passes the live sprint state in.
        main = self.read("ViewModels", "MainViewModel.cs")
        notify = main.split("public bool Notify(")[1].split("\n    }")[0]
        assert "NotificationPolicy.ShouldShow(kind, Settings, IsFocusInProgress)" in notify

        notifications = self.read("Models", "Notifications.cs")
        interrupts = notifications.split("public static bool InterruptsFocus(")[1].split(";")[0]
        assert "NotificationKind.TrialEnding" in interrupts, \
            "TrialEnding must be one of the kinds NotificationPolicy blocks during a sprint"

    def test_trial_ending_is_the_only_trial_notification_kind(self):
        # F20: "the only trial messages are the badge, one day-6 notice, and
        # the lock screen." If a second trial-related NotificationKind is ever
        # added, it must also be wired into InterruptsFocus — this test forces
        # that decision to be made, not skipped.
        notifications = self.read("Models", "Notifications.cs")
        kinds_block = notifications.split("public enum NotificationKind")[1].split("}")[0]
        # Exactly one enum member name contains "Trial".
        member_lines = [line.strip().rstrip(",") for line in kinds_block.splitlines()
                         if line.strip() and not line.strip().startswith("//")
                         and not line.strip().startswith("/*") and not line.strip().startswith("*")
                         and not line.strip().startswith("<")]
        trial_members = [m for m in member_lines if "Trial" in m]
        assert trial_members == ["TrialEnding"], trial_members

    def test_the_lock_screen_never_flips_on_mid_sprint(self):
        # RefreshAccess is the only place IsLocked can change after launch
        # (OnTierChanged only runs from inside it, from --expire-trial at
        # startup, or after a purchase/deactivation). The sprint guard has to
        # live at its top, before anything about access is read.
        main = self.read("ViewModels", "MainViewModel.cs")
        refresh = main.split("public void RefreshAccess()")[1].split("\n    }")[0]
        code_lines = [line.strip() for line in refresh.splitlines()
                      if line.strip() and not line.strip().startswith("//") and line.strip() != "{"]
        # IsFocusInProgress covers a running sprint and the break after one (F5).
        assert code_lines[0].startswith("if (IsFocusInProgress"), \
            "the sprint guard must be the first statement RefreshAccess runs"

    def test_the_lock_also_waits_out_the_summary_card(self):
        # A trial can end between the last tick of a sprint and the moment its
        # summary card is dismissed. The lock must wait for that dismissal too
        # (checklist F20's worked example), not just for IsSprintRunning to
        # flip false the instant the timer hits zero.
        main = self.read("ViewModels", "MainViewModel.cs")
        refresh = main.split("public void RefreshAccess()")[1].split("\n    }")[0]
        assert "Today.JournalPromptVisible" in refresh, \
            "RefreshAccess must also skip while the sprint summary/journal card is on screen"

        today = self.read("ViewModels", "TodayViewModel.cs")
        save_journal = today.split("private void SaveJournal()")[1].split("\n    }")[0]
        assert "_main.RefreshAccess()" in save_journal, \
            "dismissing the summary must re-check access immediately, not on the next minute's tick"

    def test_the_tier_badge_dot_follows_the_design_system(self):
        # DESIGN_SYSTEM.md §7 "Tier badge": primary while trialling, ok once
        # bought, warn once the trial has ended.
        main = self.read("ViewModels", "MainViewModel.cs")
        dot = main.split("public string TierBadgeDotKey =>")[1].split(";")[0]
        assert '"Green"' in dot and '"Primary"' in dot and '"Amber"' in dot
        assert dot.index("IsPro") < dot.index('"Green"')

    def test_no_gate_toast_fires_until_the_trial_has_actually_ended(self):
        # The per-feature "your trial has ended" toasts (Today, Blocked Apps,
        # Sleep Blocking, hard kill) are defence-in-depth behind the lock
        # screen (CLAUDE.md "Covered controls"), never a standalone nag — each
        # one is conditioned on _main.IsLocked, which is already false for the
        # whole trial and for the running sprint/summary window above.
        for file, guard in [
            ("ViewModels/TodayViewModel.cs", "if (_main.IsLocked)"),
            ("ViewModels/BlockedAppsViewModel.cs", "_main.IsLocked"),
            ("ViewModels/SleepBlockingViewModel.cs", "_main.IsLocked"),
            ("ViewModels/SettingsViewModel.cs", "_main.IsLocked"),
        ]:
            source = self.read(*file.split("/"))
            assert guard in source, f"{file} must gate its trial-ended toast on IsLocked"


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
        # Since F9 the top-up runs over every profile's list, not just the one
        # that happens to be active — a profile you switch to must not leak
        # through steamwebhelper either.
        assert "foreach (var profile in main.Settings.Profiles)" in ctor
        assert "UpgradeToFullSuggestions(profile.Apps)" in ctor
        assert ctor.index("UpgradeToFullSuggestions") < ctor.index("Apps = new ObservableCollection")

    def test_older_settings_files_still_load(self):
        model = self.read("Models", "AppSettings.cs")
        assert "public List<string> ExtraProcessNames { get; set; } = new();" in model

    @pytest.mark.ui
    @pytest.mark.skipif(not STEAM_INSTALLED, reason="the picker lists Steam only where it is installed")
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
        # maxsplit=1: since #271 a --reset launch retries TryAcquire, so the
        # region runs from the first attempt to the app starting.
        acquire = main.split("SingleInstance.TryAcquire()", 1)[1].split("new App")[0]
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


# ============================ deleting data survives the shutdown race (#271)

class TestDeleteEverythingRestartRegressions:
    """
    #271: deleting everything cleared the settings file and restarted FlowShield,
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

    def test_the_changelog_states_the_real_custom_length_range(self):
        # The 1.0.7 entry said "1 to 180 minutes"; the app accepts 5 to 240.
        import re

        page = (Path(WEBSITE_DIR) / "changelog.html").read_text(encoding="utf-8")
        today = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        low = re.search(r"CustomMinMinutes = (\d+);", today).group(1)
        high = re.search(r"CustomMaxMinutes = (\d+);", today).group(1)
        assert f"from {low} to {high} minutes" in page


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

# ===================== every colour is a token, and every token exists (§2)
class TestNoLegacyColourAliases:
    """
    DESIGN_SYSTEM.md §2: the app and the site name colours by token and by
    nothing else. The legacy aliases (Violet, Cyan, Glass*, Accent, WindowBg;
    --violet, --cyan, --grad) all pointed at the right teal, which is why they
    survived so long — the name lied and the pixel didn't.
    """

    XAML_ROOT = Path(DESKTOP_DIR)

    def _xaml_files(self):
        return [
            path for path in self.XAML_ROOT.rglob("*.xaml")
            if "obj" not in path.parts and "bin" not in path.parts
        ]

    def test_the_legacy_names_are_gone_from_the_app(self):
        banned = ("Violet", "VioletBright", "Cyan", "Glass", "GlassStrong",
                  "GlassFill", "WindowBg")
        for path in self._xaml_files():
            source = path.read_text(encoding="utf-8")
            for name in banned:
                assert f'x:Key="{name}"' not in source, f"{path.name} still defines {name}"
                assert f"{{StaticResource {name}}}" not in source, (
                    f"{path.name} still uses {name}"
                )

    def test_the_legacy_names_are_gone_from_the_site(self):
        css = (Path(WEBSITE_DIR) / "styles.css").read_text(encoding="utf-8")
        for name in ("--violet", "--violet-bright", "--cyan", "--grad",
                     "--glass", "--glass-strong"):
            assert f"{name}:" not in css, f"styles.css still defines {name}"
        for page in ("index.html", "legal.html", "success.html", "support.html",
                     "changelog.html", "checkout.js"):
            source = (Path(WEBSITE_DIR) / page).read_text(encoding="utf-8")
            for name in ("--violet", "--cyan", "--grad", "--glass"):
                assert f"var({name})" not in source, f"{page} still uses {name}"

    def test_every_static_resource_key_is_defined(self):
        """
        Deleting an alias that something still referenced would not fail the
        build — an unresolved StaticResource throws when the XAML loads, which
        is to say when the customer opens that screen. Resolve them here
        instead, where it costs a millisecond.
        """
        defined = set()
        for path in self._xaml_files():
            defined |= set(re.findall(r'x:Key="([^"]+)"',
                                      path.read_text(encoding="utf-8")))

        missing = {}
        for path in self._xaml_files():
            used = re.findall(r"\{StaticResource\s+([^}\s]+)\}",
                              path.read_text(encoding="utf-8"))
            for key in used:
                if key not in defined:
                    missing.setdefault(key, set()).add(path.name)

        assert not missing, "XAML references resources nothing defines: " + ", ".join(
            f"{key} (in {', '.join(sorted(files))})" for key, files in sorted(missing.items())
        )


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

# ============================ sprint summary card (F12)

class TestSprintSummaryCard:
    """The post-sprint card must appear and disappear with the journal prompt."""

    def test_the_card_sits_between_the_shield_and_the_journal(self):
        view = (Path(DESKTOP_DIR) / "Views" / "TodayView.xaml").read_text(encoding="utf-8")
        card = view[view.find("sprint summary"):]
        card = card[:card.find("journal prompt")]
        for name in ("SummaryTitle", "SummaryMinutesValue", "SummaryDistractionsValue",
                     "SummaryMomentumText", "SummaryStreakText"):
            assert f'AutomationProperties.AutomationId="{name}"' in card, \
                f"{name} is missing from the card"
        assert "JournalPromptVisible" in card, "the card must share the journal prompt's visibility"

    def test_the_abandoned_wording_stays_neutral(self):
        viewmodel = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert "It'll recover." in viewmodel
        assert "No distractions caught" in viewmodel


# ============================ sprint intention (F13)

class TestSummaryCardSeesTheSettledStreak:
    """
    F12's card shows the streak; F15 is what advances it. They were built
    separately, and the card was filled in before DailyGoal.Settle ran — so on
    the day a streak started, the line was collapsed and the person who had
    just earned "Day 1" saw a card with no streak on it.
    """

    VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"

    def test_stats_are_refreshed_before_the_card_is_built(self):
        source = self.VM.read_text(encoding="utf-8")
        end_sprint = source.split("_main.Blocker.StopEnforcing();", 1)[1]
        end_sprint = end_sprint.split("private void UpdateSummaryCard", 1)[0]

        refresh = end_sprint.find("RefreshStats();")
        card = end_sprint.find("UpdateSummaryCard(")
        assert refresh != -1, "EndSprint no longer refreshes stats"
        assert card != -1, "EndSprint no longer builds the summary card"
        assert refresh < card, (
            "the summary card is built before RefreshStats, so it reads a "
            "CurrentStreak that DailyGoal.Settle has not updated yet"
        )

    def test_the_streak_line_is_still_conditional(self):
        """
        Hiding the line at zero is right — "Day 0" is not a thing. The bug was
        the value being stale, not the condition.
        """
        source = self.VM.read_text(encoding="utf-8")
        assert "SummaryStreakVisible = S.CurrentStreak > 0;" in source

    def test_the_move_left_cancel_alone_and_refreshed_once(self):
        """
        The first version of this fix deleted the identical RefreshStats line
        in CancelSprint instead of EndSprint's later one, so a cancel stopped
        refreshing and a finished sprint refreshed twice.
        """
        source = self.VM.read_text(encoding="utf-8")
        cancel = source.split("private void CancelSprint()", 1)[1].split("\n    }", 1)[0]
        end = source.split("private void EndSprint(", 1)[1].split("private void UpdateSummaryCard", 1)[0]
        assert "RefreshStats();" in cancel, "CancelSprint no longer refreshes stats"
        assert end.count("RefreshStats();") == 1, "EndSprint should refresh stats exactly once"


class TestSprintIntentionGuard:
    """F13: the intention input, the ring line and the card line stay wired."""

    XAML = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"
    VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"

    def test_the_input_is_optional_and_locked_while_the_sprint_runs(self):
        view = self.XAML.read_text(encoding="utf-8")
        section = view[view.find("intention (F13)"):view.find("sprint summary")]
        assert 'AutomationProperties.AutomationId="IntentionInput"' in section
        assert 'IsEnabled="{Binding IsRunning, Converter={StaticResource InvBool}}"' in section

    def test_the_ring_and_the_card_each_show_the_intention(self):
        view = self.XAML.read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="SprintIntentionText"' in view
        card = view[view.find("sprint summary"):]
        card = card[:card.find("journal prompt")]
        assert 'AutomationProperties.AutomationId="SummaryIntentionText"' in card
        assert "SummaryIntentionVisible" in card

    def test_a_long_intention_cannot_break_the_timer_ring(self):
        # A long line wrapped to five lines inside the ring and pushed the
        # buttons down: the caption style wraps, so trimming never applied.
        view = self.XAML.read_text(encoding="utf-8")
        section = view[view.find("intention (F13)"):view.find("sprint summary")]
        assert 'MaxLength="80"' in section, "the input must cap what can be typed"

        viewmodel = self.VM.read_text(encoding="utf-8")
        assert "public const int MaxIntentionLength = 80;" in viewmodel
        assert "capped[..MaxIntentionLength]" in viewmodel, \
            "the cap must hold for pasted and programmatically set text too"

        ring = view[:view.find("SPRINT LENGTH")]
        line = ring[ring.find('AutomationId="SprintIntentionText"') - 600:]
        assert 'TextWrapping="NoWrap"' in line and 'TextTrimming="CharacterEllipsis"' in line, \
            "the line under the timer must stay on one line"

    def test_the_journal_prompt_title_is_bound_not_static(self):
        view = self.XAML.read_text(encoding="utf-8")
        journal = view[view.find("journal prompt"):]
        assert "JournalPromptTitle" in journal
        assert 'Text="What moved?"' not in journal, \
            "the prompt title must come from the viewmodel so it can repeat the intention"

    def test_cancelling_a_sprint_clears_the_intention_input(self):
        viewmodel = self.VM.read_text(encoding="utf-8")
        cancel = viewmodel[viewmodel.find("private void CancelSprint"):]
        cancel = cancel[:cancel.find("// ---------------------------------------------------------------- timer")]
        assert 'IntentionText = ""' in cancel, \
            "cancelling must clear the input so a stale intention is not captured by the next sprint"


class TestDistractionCountIsPerApp:
    """
    #138: "Distractions blocked" counts apps, not processes.

    The bug was invisible until a real multi-process app was put in front of
    the blocker — Steam runs seven, and closing it once read as seven
    distractions. The behaviour is covered end to end in tier 3; these guard
    the two halves that are easy to undo by accident.
    """

    SERVICE = Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs"

    def test_every_process_is_still_closed(self):
        """
        The dedupe covers *reporting*, never enforcement. An app whose helper
        survives because the count said "already seen" would be a far worse bug
        than the one being fixed.

        F7 moved the sweep from per-process to per-app, so this no longer reads
        as an ordering: enforcement now acts on the whole group at once, and
        what matters is that no kill sits behind the first-sighting check.
        """
        source = self.SERVICE.read_text(encoding="utf-8")
        body = source.split("private void Tick", 1)[1]
        for call in ("KillAll(processes, shield);",):
            for fragment in body.split(call)[:-1]:
                tail = fragment.rsplit("\n", 3)[-3:]
                assert not any("if (firstSighting)" in line for line in tail), (
                    "a kill must never be guarded by the first-sighting check, "
                    "or a second process of an already-counted app would survive"
                )
        assert "KillAll(processes, shield);" in body

    def test_reporting_is_what_the_first_sighting_check_guards(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        body = source.split("private void Tick", 1)[1]
        assert "if (firstSighting) Report(" in body, (
            "the first-sighting check exists to deduplicate reporting"
        )

    def test_an_app_that_goes_away_can_count_again(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        assert "_present.IntersectWith(running.Keys)" in source, (
            "entries with nothing running must be forgotten, or reopening a "
            "blocked app would never count as a fresh distraction"
        )

    def test_the_counter_is_reset_when_enforcement_starts_and_stops(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        for method in ("BeginEnforcing", "StopEnforcing"):
            body = source.split(f"public void {method}(", 1)[1]
            body = body.split("    }", 1)[0]
            assert "_present.Clear();" in body, f"{method} must clear the seen set"


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

# ================= the site says what FlowShield doesn't do (F26) and what it
# ================= costs compared with the category (F24)
class TestHonestLimitsAndPriceComparison:
    """
    F26 asks the site to state the limits plainly, in a FAQ and near the price,
    rather than letting a buyer discover them afterwards. F24 asks for one
    general price-comparison line.

    The limits are checked against the app rather than merely being present:
    a FAQ that still says "no website blocking" after F10 ships would be a
    worse lie than saying nothing, so these tests fail the day that changes.
    """

    def _site(self):
        return (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")

    def _faq(self):
        site = self._site()
        assert 'id="faq"' in site, "the site has no FAQ section"
        return site.split('id="faq"', 1)[1].split("</section>", 1)[0]

    def test_the_faq_is_reachable_from_the_nav_and_the_footer(self):
        site = self._site()
        assert site.count('href="#faq"') >= 2, (
            "the FAQ needs a link in the nav and in the footer; a section nobody "
            "can find answers nobody"
        )

    def test_every_faq_entry_is_a_question_with_an_answer(self):
        faq = self._faq()
        questions = faq.count("<summary>")
        assert questions >= 5, f"only {questions} FAQ entries"
        assert faq.count("</summary>") == questions
        assert faq.count("<details") == questions, "every answer needs its own details"

    def test_the_limits_are_stated_plainly(self):
        lower = self._faq().lower()
        for phrase in (
            "not today",          # websites inside the browser, and the platform
            "windows 10 and 11",  # the only platform
            "no mac app",
            "no browser extension",
        ):
            assert phrase in lower, f"the FAQ does not state the limit: {phrase!r}"

    def test_the_browser_limit_matches_what_the_blocker_does(self):
        """
        The claim "it doesn't block websites yet" has to stay true. The blocker
        works on processes; when it learns about URLs, this test should fail and
        the FAQ should be rewritten in the same change.
        """
        blocker = (Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs").read_text(
            encoding="utf-8")
        assert "ProcessName" in blocker
        assert "Url" not in blocker, (
            "the blocker now mentions URLs — update the FAQ's website answer"
        )

    def test_the_data_answer_names_what_activation_sends(self):
        """
        The first FAQ said only the payment provider receives anything, but
        activation sends the device ID and name to the licence server, which
        the privacy policy already disclosed. The FAQ must not say less.
        """
        license_service = (Path(DESKTOP_DIR) / "Services" / "LicenseService.cs").read_text(
            encoding="utf-8")
        assert "DeviceIdentity.Name" in license_service
        answer = self._site().split("Where does my data go?", 1)[1].split("</details>", 1)[0]
        # "legal.html#privacy", not "privacy.html" (#193): the answer linked to
        # a page that has never existed, so the one link a privacy-conscious
        # reader is most likely to follow 404'd. The policy is a section of
        # legal.html. This test asserted the broken spelling, which is why it
        # was never caught.
        for words in ("licence server", "device ID", "user name", "legal.html#privacy"):
            assert words in answer, f"the FAQ's data answer no longer mentions {words!r}"

    def test_the_price_comparison_is_a_range_and_names_nobody(self):
        site = self._site()
        assert "$30&ndash;$60 every year" in site or "$30–$60 every year" in site, (
            "F24 asks for a general comparison line near the price"
        )
        # Naming a competitor needs a re-checked price and a dated comment, so
        # the safe default is that none appear at all.
        lower = site.lower()
        for rival in ("cold turkey", "freedom.to", "blocksite", "opal", "focusme", "forest app"):
            assert rival not in lower, (
                f"{rival!r} is named on the site; F24 says an unnamed range only, "
                "unless the price was re-checked and dated in a comment"
            )

    def test_the_price_claim_agrees_with_the_rest_of_the_site(self):
        site = " ".join(self._site().split())
        assert "$4.99, once, for up to 3 PCs" in site
        assert "3 PCs" in site


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

    def test_the_email_button_is_only_offered_when_the_server_can_send(self):
        """
        /resend-license answers 503 when no mail provider is configured, so
        the button would fail every time on such a server. get-license reports
        emailConfigured; the page hides the button — and stops saying "have it
        emailed to you" — when that is false or the buyer's address is unknown.
        """
        js = (Path(WEBSITE_DIR) / "checkout.js").read_text(encoding="utf-8")
        assert "result.emailConfigured !== false" in js
        assert "emailKeyBtn.style.display = 'none'" in js
        assert "You can copy, email, or activate the key below." not in js

    def test_checkout_js_has_no_byte_order_mark(self):
        # A PowerShell edit once prepended U+FEFF; browsers tolerate it but
        # every later diff of the file shows a phantom first-line change.
        raw = (Path(WEBSITE_DIR) / "checkout.js").read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), "checkout.js starts with a UTF-8 BOM"


# ============ the download guide explains what happens next (roadmap 6.3)

class TestDownloadGuidePanel:
    """
    Clicking Download shows a short "What happens next" panel: the SmartScreen
    step (until the build is signed), running the installer, and the first-run
    welcome. The panel's own Download button must still reach the installer.
    """

    INSTALLER_URL = (
        "https://github.com/seventycookies6-design/flowshield/releases/latest/"
        "download/FlowShield-win-Setup.exe"
    )

    def test_download_guide_panel_mentions_setup_steps(self):
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        assert 'id="download-panel"' in site, "the download guide panel is missing"
        panel = site.split('id="download-panel"', 1)[1].split("</dialog>", 1)[0]
        lower = panel.lower()
        for phrase in ("smartscreen", "installer", "first run"):
            assert phrase in lower, f"the download guide must mention {phrase!r}"
        assert self.INSTALLER_URL in panel, (
            "the panel's Download button must point at the installer URL"
        )

    def test_the_first_run_step_describes_the_real_welcome(self):
        # The welcome (F18) has three steps — apps, strictness, first sprint —
        # and only starts a sprint if the user presses Start. The draft said it
        # "asks for your blocklist and default sprint, then starts the first
        # sprint", which skipped a step and promised an automatic start.
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        panel = site.split('id="download-panel"', 1)[1].split("</dialog>", 1)[0]
        vm = (Path(DESKTOP_DIR) / "ViewModels" / "FirstRunViewModel.cs").read_text(encoding="utf-8")
        assert 'StepText => $"Step {Step} of 3"' in vm
        assert "three-step welcome" in panel
        assert "then starts the first sprint" not in panel


# ============ phone visitors get a menu and a copyable download link (roadmap 6.4)

class TestProductCaptures:
    """
    F27: the site shows the real app. DESIGN_SYSTEM.md 10 sets the rules —
    real product only, a surface frame at radius 14 with a soft shadow, never a
    fake device frame — and 11 adds that the hero must render before any media.

    These check the markup and the asset budget. Whether the screenshots make
    the product look good is a human's call and always will be.
    """

    MEDIA = Path(WEBSITE_DIR) / "media"

    def _section(self):
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        assert 'id="see-it"' in site, "the captures section is missing"
        return site.split('id="see-it"', 1)[1].split("</section>", 1)[0]

    def test_every_capture_referenced_exists(self):
        import re
        for src in re.findall(r'src="(media/[^"]+)"', self._section()):
            assert (Path(WEBSITE_DIR) / src).exists(), f"{src} is referenced but missing"

    def test_every_image_has_real_alt_text(self):
        import re
        images = re.findall(r"<img[^>]*>", self._section(), re.S)
        assert images, "the section has no screenshots"
        for tag in images:
            alt = re.search(r'alt="([^"]*)"', tag, re.S)
            assert alt, f"an image has no alt attribute: {tag[:80]}"
            assert len(" ".join(alt.group(1).split())) > 25, (
                "alt text has to describe the screen, not just name it"
            )

    def test_images_are_lazy_and_reserve_their_space(self):
        import re
        for tag in re.findall(r"<img[^>]*>", self._section(), re.S):
            assert 'loading="lazy"' in tag, "captures must not block the page"
            assert "width=" in tag and "height=" in tag, (
                "give every image its size so the page does not jump"
            )

    def test_no_fake_device_frames(self):
        """
        Checks the markup, not the prose: the copy is allowed to say "not a
        mock-up", which is rather the point of the section.
        """
        import re
        section = self._section()
        attributes = " ".join(
            re.findall(r'(?:class|src|id)="([^"]*)"', section)
        ).lower()
        for banned in ("laptop", "macbook", "iphone", "device-frame", "mockup", "mock-up"):
            assert banned not in attributes, f"DESIGN_SYSTEM 10 forbids a {banned} frame"

    def test_the_frame_follows_the_design_system(self):
        css = (Path(WEBSITE_DIR) / "styles.css").read_text(encoding="utf-8")
        frame = css.split(".shot {", 1)[1].split("}", 1)[0]
        assert "var(--color-surface)" in frame
        assert "var(--radius)" in frame, "radius 14 comes from the token"
        assert "var(--shadow-soft)" in frame

    def test_the_captures_stay_within_a_sensible_budget(self):
        """
        DESIGN_SYSTEM 11: the hero renders before any media. Lazy loading does
        the work, but a page of multi-megabyte PNGs is still rude on a phone.
        """
        if not self.MEDIA.exists():
            pytest.skip("no media directory yet")
        total = 0
        for asset in self.MEDIA.glob("*.png"):
            size = asset.stat().st_size
            assert size < 900_000, f"{asset.name} is {size / 1000:.0f} kB; compress it"
            total += size
        assert total < 3_000_000, f"the captures total {total / 1000:.0f} kB"

    def test_the_recording_is_silent_looping_and_inline(self):
        """DESIGN_SYSTEM.md 10: muted, looping, a poster, playsinline."""
        section = self._section()
        video = section.split("<video", 1)[1].split(">", 1)[0]
        for attribute in ("muted", "loop", "playsinline", "poster="):
            assert attribute in video, f"the recording must set {attribute}"
        assert "controls" not in video, "a looping silent demo needs no controls by default"
        assert "<audio" not in section
        assert "autoplay" not in video, (
            "autoplay belongs to the reduced-motion script, not the markup"
        )

    def test_the_recording_honours_reduced_motion(self):
        """
        DESIGN_SYSTEM.md 8: with reduced motion on, the video shows its poster
        frame instead of playing. There is no HTML or CSS way to make autoplay
        conditional, so a script decides — and this checks the script exists and
        keys off the right query.
        """
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        assert "prefers-reduced-motion: reduce" in site
        script = site.split("prefers-reduced-motion: reduce", 1)[1][:600]
        assert ".pause()" in script, "reduced motion has to stop the video"

    def test_the_recording_is_described_for_people_who_cannot_see_it(self):
        section = self._section()
        assert "aria-describedby" in section
        described = section.split('id="shield-demo-description"', 1)[1].split("</p>", 1)[0]
        assert len(" ".join(described.split())) > 80, (
            "a silent demo needs a description that says what happens in it"
        )

    def test_the_recording_stays_inside_the_size_budget(self):
        """DESIGN_SYSTEM.md 10: about 2 MB on desktop, 1 MB on mobile."""
        if not self.MEDIA.exists():
            pytest.skip("no media directory yet")
        for clip in list(self.MEDIA.glob("*.webm")) + list(self.MEDIA.glob("*.mp4")):
            size = clip.stat().st_size
            assert size < 2_000_000, f"{clip.name} is {size / 1000:.0f} kB"

    def test_the_recording_does_not_load_before_the_page(self):
        video = self._section().split("<video", 1)[1].split(">", 1)[0]
        assert 'preload="none"' in video, (
            "DESIGN_SYSTEM.md 11: the hero renders before any media loads"
        )

    def test_the_hero_still_comes_first(self):
        """
        #147 §4 (issue #173, "B2") deliberately reverses part of #139: the
        hero itself now shows the real Today capture, full width, directly
        below the copy — it no longer sits beside a decorative day-mock, and
        the day timeline is promoted to its own `#day` section right after
        the hero instead. What #139 actually protected — that the hero's
        text and primary button render before any product media, and that
        the below-the-fold proof section never displaces the hero — still
        holds and is checked more precisely here, not weakened.
        """
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        hero_open = site.index('<section class="hero"')
        hero_close = site.index("</section>", hero_open)
        day = site.index('<section id="day"')
        captures = site.index('id="see-it"')

        assert hero_open < day < captures, (
            "the sections must run hero, then day, then the captures proof section"
        )
        assert "media/" not in site[:hero_open], "no product media above the hero"

        # The hero shows the real product now (§10/§0) — but text and the
        # primary CTA must still render before that image reaches the DOM,
        # which is what #139 actually guarded against.
        hero = site[hero_open:hero_close]
        assert "media/today.png" in hero, "the hero must lead with the real product capture"
        h1_at = hero.index("<h1")
        cta_at = hero.index("data-download-guide")
        img_at = hero.index("media/today.png")
        assert h1_at < cta_at < img_at, (
            "the headline and primary CTA must both precede the product image in source order"
        )

        # The day timeline used to be aria-hidden decoration squeezed beside
        # the hero copy (#139); it is now real, visible content in its own
        # section, not inside the hero at all.
        assert "timeline" not in hero, "the day timeline must not still be inside the hero"
        assert hero_close < day, "the day section must start after the hero ends"
        day_section = site[day:site.index("</section>", day)]
        assert 'aria-hidden="true"' not in day_section.split(">", 1)[0], (
            "the day section itself must not be hidden from assistive tech"
        )
        assert "<h2>" in day_section, "the day section needs a real, visible heading now"

    def test_the_product_is_not_pushed_below_the_fold(self):
        """
        Leading with the product (#147 §4) only works if the capture reaches
        the first screen. With the worked example and the stats row stacked
        above it, the capture started at 95% of a 1440x900 screen and fully
        below the fold at 1366x768. The copy above the capture stays short:
        eyebrow, headline, lede, calls to action and the note. The example
        and the numbers go below it.
        """
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        hero_open = site.index('<section class="hero"')
        hero = site[hero_open:site.index("</section>", hero_open)]
        img_at = hero.index("media/today.png")
        above = hero[:img_at]
        for marker in ('class="example"', 'class="trust"'):
            assert marker in hero, f"{marker} should still be in the hero"
            assert marker not in above, (
                f"{marker} sits above the product capture again, pushing it below the fold")
        # `"<p"` also matched every `<path>` in an inline SVG, so this counted
        # icon geometry as prose (#193). Count real paragraph tags instead.
        paragraphs = len(re.findall(r"<p[ >]", above))
        # Four, not three (#193): the SmartScreen note joins the lede, the copy
        # confirmation and the note. It is the one caveat that has to be read
        # before the click rather than after it — Microsoft's own advice for an
        # unsigned build is to warn people in advance, and SELLING.md calls this
        # the biggest install drop-off there is.
        #
        # Measured in a browser at the size this test was written for, before
        # the change and after it: at 1366x768 the capture's top moved from
        # 517px to 621px, so 147px of it still shows above the fold. That is
        # what the rule is actually for (NN/g's fold guidance: let the next
        # thing peek so people scroll), and the note is capped at 58ch so it
        # stays three lines at a desktop width.
        assert paragraphs <= 4, (
            f"{paragraphs} paragraphs above the capture; keep it to the lede, the "
            "copy confirmation, the note and the SmartScreen caveat")


class TestDesignReviewFixesB4:
    """
    #183: an external review of the site stack found these, and each was
    re-measured in a browser before the fix. Every test below fails on the
    markup and CSS as #178 left them.
    """

    SITE = Path(WEBSITE_DIR) / "index.html"
    CSS = Path(WEBSITE_DIR) / "styles.css"

    def _css(self) -> str:
        return self.CSS.read_text(encoding="utf-8")

    def _rule(self, selector: str) -> str:
        # Anchored to the start of a line, so ".shot-grid" can't match the
        # tail of a compound selector such as ".shot-demo + .shot-grid".
        css = self._css()
        match = re.search(r"^" + re.escape(selector) + r" \{", css, re.M)
        assert match, f"no top-level rule for {selector}"
        return css[match.start():css.index("}", match.start())]

    def test_the_mobile_menu_closes_when_a_destination_is_chosen(self):
        """At 390px, tapping a nav link scrolled to the section but left the
        open menu covering it."""
        site = self.SITE.read_text(encoding="utf-8")
        script = site[site.index("[data-menu-toggle]');"):]
        assert "#primary-nav a" in script and "setMenu(false)" in script, (
            "a nav link must close the menu when it is chosen")
        assert "'Escape'" in script, "Escape must close the open menu"
        assert "scroll-padding-top" in self._css(), (
            "in-page links must land below the sticky header, not under it")

    def test_explanations_are_body_size_not_label_size(self):
        """§3: the site's body text is 17px. The card explanations were set at
        the 13px label size."""
        for selector in (".feature p", ".level .scenario", ".behaviors li", ".plan li"):
            rule = self._rule(selector)
            assert "var(--text-label)" not in rule, f"{selector} is still label-sized"
            assert "var(--text-body)" in rule, f"{selector} should use the body size"

    def test_gallery_columns_cannot_outgrow_a_narrow_phone(self):
        """At 360px the grid was narrower than a 20rem column, so cards ran past
        the right gutter."""
        rule = self._rule(".shot-grid")
        assert "minmax(min(100%, 20rem), 1fr)" in rule, (
            "the column minimum must be capped at the grid's own width")

    def test_no_decorative_status_or_accent_colour(self):
        """§2: teal marks state, selection or progress, and status colours are
        for status only. Static icons, a quote rule and fake window dots were
        using them as decoration."""
        css = self._css()
        assert ".mock-bar i:first-child" not in css, "no red/amber/green window dots"
        site = self.SITE.read_text(encoding="utf-8")
        assert '<div class="mock-bar"><i>' not in site, "the window-dot markup is gone too"
        assert "var(--color-primary)" not in self._rule(".behaviors li svg")
        assert "color: var(--color-primary)" not in css[css.index(".feature-icon svg"):][:120]
        assert "solid var(--color-primary)" not in self._rule(".hero .example")

    def test_pricing_offers_phones_the_same_download_flow_as_the_hero(self):
        """On a phone the hero copied the download link, while pricing still
        offered the Windows installer."""
        site = self.SITE.read_text(encoding="utf-8")
        pricing = site[site.index('<section id="pricing"'):]
        pricing = pricing[:pricing.index("</section>")]
        assert "data-download-direct" in pricing, (
            "pricing's installer link must hide on phones like the hero's")
        assert "data-download-copy" in pricing, "pricing needs the phone copy button"
        assert "data-copy-confirm" in pricing, "and a confirmation beside it"
        assert "querySelectorAll('[data-download-copy]')" in site, (
            "every copy button must be wired, not just the first one")

    def test_eyebrows_keep_one_size(self):
        """Paragraph rules in .section-head and .shields-intro enlarged the
        eyebrow label to 18px, while every other eyebrow was 11px."""
        css = self._css()
        for unscoped in (".section-head p {", ".shields-intro p { margin: 0; font-size"):
            assert unscoped not in css, f"`{unscoped}` resizes the .label eyebrow inside it"


class TestLandingPageLengthB5:
    """
    #185: the external review found the page repeating itself before the
    decision point. Pricing started about 7,900px down on desktop and
    10,200px on a phone. The day was explained three times (the timeline,
    #how, and a strip in #shields), momentum four times, and the Today
    capture shown twice. These guard the cut against creeping back.
    """

    SITE = Path(WEBSITE_DIR) / "index.html"

    def _site(self) -> str:
        return self.SITE.read_text(encoding="utf-8")

    def test_the_page_runs_in_decision_order(self):
        site = self._site()
        order = ['<section class="hero"', '<section id="day"', '<section id="shields"',
                 '<section id="see-it"', '<section id="features"', '<section id="pricing"',
                 '<section id="faq"']
        at = [site.index(marker) for marker in order]
        assert at == sorted(at), (
            "hero, the day, the shields, one real demo, the benefits, then pricing and FAQ")
        assert '<section id="how"' not in site, "how-it-works lives inside #day now"

    def test_the_day_is_explained_once(self):
        site = self._site()
        day = site[site.index('<section id="day"'):]
        day = day[:day.index("</section>")]
        assert 'class="timeline"' in day and 'class="story-list' in day, (
            "#day carries both the timeline and the three steps")
        assert 'class="day-strip"' not in site, (
            "the shields section must not repeat the day as a strip")

    def test_the_today_capture_appears_once(self):
        assert self._site().count("media/today.png") == 1, (
            "the hero already shows Today; #see-it shows what the hero doesn't")

    def test_the_demo_leads_the_proof_section(self):
        site = self._site()
        see_it = site[site.index('<section id="see-it"'):]
        see_it = see_it[:see_it.index("</section>")]
        assert see_it.index("<video") < see_it.index('class="shot-grid"'), (
            "one real demonstration first, then the supporting captures")

    def test_benefits_do_not_restate_other_sections(self):
        site = self._site()
        features = site[site.index('<section id="features"'):site.index('<section id="pricing"')]
        for repeat in ("Escalating shield levels", "Momentum first", "Why it sticks"):
            assert repeat not in features, f"{repeat!r} restates another section"
        assert features.count('class="surface feature"') == 3


class TestSiteToneB6:
    """
    #187: "Pick how much you trust yourself today" and "when you do not trust
    yourself" framed the reader as untrustworthy. Miles chose to rewrite both
    and to keep "The 1 a.m. version of you doesn't get a vote", which sides
    with the reader against an impulse they chose to guard against
    (DESIGN_SYSTEM.md §9: kind, never guilty).
    """

    def _site(self) -> str:
        return " ".join((Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8").split())

    def test_the_site_does_not_call_the_reader_untrustworthy(self):
        site = self._site().lower()
        for phrase in ("trust yourself", "not trust yourself"):
            assert phrase not in site, f"{phrase!r} frames the reader as untrustworthy"

    def test_the_rewrites_and_the_kept_line_are_in_place(self):
        site = self._site()
        assert "Pick how hard it should be to quit today" in site
        assert "“just checking” Steam turns into an hour" in site
        assert "The 1 a.m. version of you doesn't get a vote." in site, (
            "Miles chose to keep this line (#187)")


class TestPhoneVisitorMarkup:
    """
    Roadmap 6.4: on small screens the nav collapses behind a hamburger and the
    hero's direct installer link is replaced by a "Get the download link" button
    that copies the URL, falling back to a mailto: link when the clipboard is
    unavailable. The desktop direct link must stay intact.
    """

    def test_phone_visitor_markup(self):
        site = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        css = (Path(WEBSITE_DIR) / "styles.css").read_text(encoding="utf-8")

        # A hamburger/menu control exists and is wired to the nav links.
        assert "data-menu-toggle" in site, "no hamburger/menu control on the page"
        assert 'aria-controls="primary-nav"' in site, "menu button is not wired to the nav"
        assert 'id="primary-nav"' in site, "the nav links have no id to toggle"

        # The direct installer link is still present somewhere in the page.
        assert "FlowShield-win-Setup.exe" in site, "the direct installer link was removed"

        # A copy button with a mailto fallback exists for mobile.
        assert "data-download-copy" in site, "no mobile copy-download button"
        assert "data-download-direct" in site, "no direct download link to copy from"
        assert "mailto:" in site, "no mailto fallback for phones without a clipboard"
        assert "navigator.clipboard" in site, "no clipboard copy path"

        # CSS hides the direct button on mobile and the copy button on desktop.
        assert "[data-download-copy]" in css, "copy button is not hidden on desktop"
        assert "data-download-direct" in css, "direct button is not hidden on mobile"

        # #193: the swap is deliberate, so the phone says why. Without it the
        # missing installer button reads as a broken page. It is shown by the
        # same breakpoint that hides the direct link, so the two cannot drift.
        assert 'class="phone-only"' in site, "phones get no reason for the copy button"
        assert ".hero-note .phone-only { display: inline; }" in css, (
            "the phone explanation must appear at the breakpoint that hides the installer link")


# ================================ the conversion pass from evidence (#193)

class TestSiteConversionPass:
    """
    #193. Three things the landing page owed a visitor, each backed by a
    source rather than taste:

    * The SmartScreen warning explained **before** the download click, not
      only inside the panel that opens after it. Microsoft's guidance for an
      unsigned build is to tell people in advance that they will see the
      prompt, and `SELLING.md` already calls it the biggest install drop-off.
    * The refund reachable from the decision point. It existed only in
      `legal.html` and a footer link.
    * Calls to action that name what the click does (NN/g, *"Get Started"
      Stops Users*, 2017: "a link is a promise").

    Every claim added here is one the shipped product can back: a refund
    policy that exists, no account, no telemetry. No testimonials, no user
    counts, no invented numbers.
    """

    INDEX = Path(WEBSITE_DIR) / "index.html"

    def _site(self) -> str:
        return self.INDEX.read_text(encoding="utf-8")

    def _copy(self) -> str:
        """The page with its HTML comments removed — what a visitor reads.

        The comments in this file quote the old wording and name the things
        being guarded against, so scanning the raw source for banned copy
        matches the explanation of the ban.
        """
        return re.sub(r"<!--.*?-->", "", self._site(), flags=re.S)

    def _hero(self) -> str:
        site = self._site()
        start = site.index('<section class="hero"')
        return site[start:site.index("</section>", start)]

    def test_the_smartscreen_note_sits_beside_the_download_button(self):
        hero = self._hero()
        assert "data-smartscreen-note" in hero, (
            "the SmartScreen caveat must be in the hero, not only in the download panel")
        note = hero.split("data-smartscreen-note", 1)[1].split("</p>", 1)[0]
        lower = note.lower()
        assert "windows protected your pc" in lower, (
            "name the dialog Windows actually shows, in its own words")
        assert "run anyway" in lower, "say which button gets past it"
        assert "code-signed" in lower, "say why the warning happens"
        # Before the click, not after it: the note has to precede the capture,
        # and the CTA it explains has to precede the note.
        assert hero.index("data-download-guide") < hero.index("data-smartscreen-note")
        assert hero.index("data-smartscreen-note") < hero.index("media/today.png")

    def test_the_smartscreen_note_goes_when_the_build_is_signed(self):
        """
        F25 buys a certificate and adds signing to `tools/build_release.ps1`.
        The day that lands, this note becomes a lie; fail then, loudly.
        """
        script = (Path(DESKTOP_DIR).parent / "tools" / "build_release.ps1").read_text(
            encoding="utf-8-sig")
        assert "NOT CODE SIGNED" in script, (
            "build_release.ps1 no longer warns that the build is unsigned — if F25 "
            "landed, delete the hero SmartScreen note, the FAQ paragraph about it "
            "and this test")

    def test_the_refund_is_offered_where_the_price_is(self):
        site = self._site()
        pricing = site.split('<section id="pricing">', 1)[1].split("</section>", 1)[0]
        assert "data-buy-reassure" in pricing, "nothing reassures beside the buy button"
        block = pricing.split("data-buy-reassure", 1)[1].split("</p>", 1)[0]
        assert 'href="legal.html#refunds"' in block, "link the policy, do not just assert it"
        assert "14-day refund" in block
        assert "No account" in block
        # And the promise has to match the policy it links to.
        legal = (Path(WEBSITE_DIR) / "legal.html").read_text(encoding="utf-8")
        assert "within 14 days" in legal, (
            "the refund window on the landing page no longer matches legal.html")

    def test_the_refund_is_a_question_in_the_faq_too(self):
        faq = self._site().split('id="faq"', 1)[1].split("</section>", 1)[0]
        answer = faq.split("don&rsquo;t like it?", 1)
        assert len(answer) == 2, "the FAQ has no refund question"
        answer = answer[1].split("</details>", 1)[0]
        assert "14 days" in answer and "legal.html#refunds" in answer

    def test_the_download_buttons_say_what_the_click_does(self):
        """
        NN/g (Harley & Flaherty, 20 Aug 2017): state precisely what users
        should expect. "Start free trial" never said an installer downloads.
        """
        copy = self._copy()
        assert "Start free trial" not in copy and "Start the free trial" not in copy, (
            "a download button must name the download")
        # Both offers — the hero and the pricing card — carry the same label.
        assert copy.count("Download for Windows") == 2

    def test_no_invented_trust_signals(self):
        """
        Zero customers means zero testimonials. The only honest trust signals
        are checkable facts, so guard against the usual substitutes.
        """
        lower = self._copy().lower()
        for banned in ("testimonial", "customers love", "trusted by", "5 stars",
                       "rated 5", "join thousands", "users worldwide", "money-back guarantee!"):
            assert banned not in lower, f"{banned!r} is not something this product can back"

    def test_every_relative_page_link_on_every_public_page_exists(self):
        """
        `TestFooterLinksPointToRealPages` only walks footers, so the FAQ's
        link to a `privacy.html` that has never existed survived for months.
        This walks every relative link on every public page.
        """
        pages = ("index.html", "legal.html", "success.html",
                 "changelog.html", "support.html")
        for name in pages:
            html = (Path(WEBSITE_DIR) / name).read_text(encoding="utf-8")
            for href in re.findall(r'href="([^"]+)"', html):
                if href.startswith(("http://", "https://", "//", "/", "#",
                                    "mailto:", "data:", "flowshield:")):
                    continue
                path, _, fragment = href.partition("#")
                if not path.endswith(".html"):
                    continue
                target = Path(WEBSITE_DIR) / path
                assert target.is_file(), f"{name} links to missing {href}"
                if fragment:
                    assert f'id="{fragment}"' in target.read_text(encoding="utf-8"), \
                        f"{name} links to {href}, but {path} has no id={fragment!r}"


# ==================================================== daily goal guards (F15)

class TestDailyGoalRegressions:
    """
    F15 added a daily goal, and with it a streak that has to settle itself.

    Two things could quietly break: the streak for the people who never set a
    goal, and the bar appearing for them at all.
    """

    MODEL = DESKTOP_DIR / "Models" / "DailyGoal.cs"
    TODAY_VM = DESKTOP_DIR / "ViewModels" / "TodayViewModel.cs"
    TODAY_XAML = DESKTOP_DIR / "Views" / "TodayView.xaml"

    def test_the_streak_settles_somewhere_that_runs_without_a_sprint(self):
        """
        The bug this guards: the streak was only ever recalculated inside
        ApplyMomentum, which runs when a sprint completes. A missed day was
        therefore invisible until the next completed sprint — so a week off
        still showed the old streak. With a goal, that becomes wrong rather
        than merely stale, because a day can now fail by falling short.
        """
        vm = self.TODAY_VM.read_text(encoding="utf-8")
        refresh = vm.split("public void RefreshStats()", 1)
        assert len(refresh) == 2, "RefreshStats must still exist"
        assert "DailyGoal.Settle" in refresh[1][:900], \
            "RefreshStats must settle the streak: it is the path that runs on launch " \
            "and when the day rolls over, with no sprint to trigger it"

    def test_the_goal_bar_is_bound_to_visibility_not_just_emptied(self):
        """
        A goal-less user must not see an empty bar. Hiding it by blanking the
        text would leave the track and the padding behind.
        """
        xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        # Anchored on the progress text, which UI Automation can actually
        # resolve. The panel's own id was removed in #134: an id on a layout
        # panel is never surfaced, so it could not fail.
        panel = xaml.split('AutomationProperties.AutomationId="DailyGoalProgressText"', 1)
        assert len(panel) == 2, "the daily goal panel must be present"
        before = panel[0][-800:]
        assert "GoalVisible" in before and "BoolVis" in before, \
            "the panel itself must collapse when no goal is set"

    def test_a_skipped_day_cannot_be_turned_into_a_counted_one(self):
        """
        Judge checks the skip first. Reversing that order would let a stray
        two-minute sprint on a planned day off consume the weekly allowance
        and count the day, which is the opposite of what the user asked for.
        """
        model = self.MODEL.read_text(encoding="utf-8")
        judge = model.split("public static DayVerdict Judge", 1)
        assert len(judge) == 2, "Judge must exist"
        body = judge[1][:400]
        skip_at = body.find("IsSkipped")
        met_at = body.find("MetOn")
        assert skip_at != -1 and met_at != -1
        assert skip_at < met_at, "a skip must be judged before the goal is measured"

    def test_the_weekly_allowance_is_not_a_calendar_week(self):
        """
        A fixed week boundary allows two days off back to back — Sunday and
        Monday — from an allowance that reads as one per week.
        """
        model = self.MODEL.read_text(encoding="utf-8")
        used = model.split("public static int SkipsUsedInWindow", 1)
        assert len(used) == 2
        assert "AddDays(-(SkipWindowDays - 1))" in used[1][:400], \
            "the window must be measured back from the day, not from a week boundary"

    def test_settling_is_idempotent_in_source(self):
        """
        Settle runs on launch, on rollover and after every sprint. If it did not
        record where it got to, each call would re-walk the same days and count
        them again.
        """
        model = self.MODEL.read_text(encoding="utf-8")
        assert "StreakSettledDayLocal = date" in model, \
            "Settle must record the day it settled through"

    def test_today_is_never_judged_as_missed(self):
        """
        Today is still in progress. Breaking the streak at 9am because the goal
        is not met yet would be absurd.
        """
        model = self.MODEL.read_text(encoding="utf-8")
        settle = model.split("public static bool Settle", 1)
        assert len(settle) == 2
        assert "if (day == date)" in settle[1][:1600], \
            "the loop must treat today specially: it can add to the streak, never break it"


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



def _path_points(data: str) -> list[tuple[float, float]]:
    """
    The on-curve points of a XAML path, for the icon geometry check.

    Only the commands Icons.xaml uses, absolute and space-separated: M, L, A
    and Z. An arc's leading radii, rotation and flags are not coordinates, so
    a plain scan for numbers would read a radius as a position — only the
    final x,y of each arc is a point.
    """
    tokens = re.findall(r"[MLAZmlaz]|-?\d+(?:\.\d+)?", data)
    counts = {"M": 2, "L": 2, "A": 7, "Z": 0}
    points: list[tuple[float, float]] = []
    i = 0
    while i < len(tokens):
        command = tokens[i].upper()
        assert command in counts, f"unhandled path command {tokens[i]!r}"
        assert tokens[i] == command, "the geometries are written absolute, not relative"
        i += 1
        size = counts[command]
        # A command repeats its arguments until the next command letter.
        while size and i + size <= len(tokens) and not tokens[i].isalpha():
            args = [float(v) for v in tokens[i:i + size]]
            points.append((args[-2], args[-1]))
            i += size
    return points

class TestNavigationUsesIconsNotUnicodeGlyphs:
    """
    Design system §5. The navigation used Unicode glyphs (U+25F7, U+2298,
    U+263E, U+2699), which render differently across Windows versions and did
    not match each other. They are now Lucide geometry in Styles/Icons.xaml.

    A font-dependent glyph reintroduced in a view would look fine on the
    machine that added it and wrong on a customer's, so it is caught here
    rather than by eye.
    """

    ICONS = Path(DESKTOP_DIR) / "Styles" / "Icons.xaml"
    VIEWS = ("MainWindow.xaml", "Views/BlockedAppsView.xaml",
             "Views/SleepBlockingView.xaml", "Views/TodayView.xaml",
             "Views/SettingsView.xaml", "Views/HistoryView.xaml")
    # The glyphs this replaced, plus the other symbol ranges a future one would
    # most likely come from. U+2192 (a typographic arrow between two fields) is
    # text, not an icon, and is deliberately allowed.
    BANNED = "◷⊘☾⚙↻✓✗⚠⭐★"

    def test_no_glyph_icons_left_in_the_views(self):
        offenders = []
        for name in self.VIEWS:
            path = Path(DESKTOP_DIR) / name
            if not path.exists():
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for ch in self.BANNED:
                    if ch in line:
                        offenders.append(f"{name}:{n} contains U+{ord(ch):04X}")
        assert not offenders, (
            "use a Path with the Icon style and a geometry from Icons.xaml:\n  "
            + "\n  ".join(offenders))

    def test_every_icon_covers_the_same_part_of_the_24_grid(self):
        """
        The Icon style stretches each geometry to fill its box, so an icon
        drawn smaller on the 24 grid renders oversized next to the others.
        Lucide's own icons mostly span 3..21; its arrows span 5..19, which is
        why one is not in the set.
        """
        xml = self.ICONS.read_text(encoding="utf-8")
        geometries = re.findall(
            r'<StreamGeometry x:Key="(\w+)">(.*?)</StreamGeometry>', xml, re.S)
        assert len(geometries) >= 4, "the icon geometries should be in Icons.xaml"

        for key, data in geometries:
            points = _path_points(data)
            assert points, f"{key} has no path data"
            values = [v for point in points for v in point]
            low, high = min(values), max(values)
            assert low >= 2.0 and high <= 22.0, (
                f"{key} runs from {low} to {high}; it should sit inside the 24 grid")
            assert high - low >= 15.0, (
                f"{key} only spans {high - low:.1f} of the 24 grid, so Stretch will "
                f"scale it up next to the others. Give it its own box size instead "
                f"of the shared Icon style.")

    def test_the_lucide_notice_is_kept(self):
        notice = Path(DESKTOP_DIR) / "Assets" / "Icons" / "LICENSE"
        assert notice.exists(), "Lucide is ISC-licensed; keep its notice with the icons"
        text = notice.read_text(encoding="utf-8")
        assert "ISC License" in text and "Lucide" in text


# ===================== Roadmap 5.7 — see and manage your devices (UI)

class TestDevicesListIsFetchedOnDemandOnly:
    """
    The device list must be fetched only when the card is expanded (the
    first time) or Refresh is pressed — never on a timer, never in the
    background. A regression here (e.g. a DispatcherTimer wired to
    LoadDevicesAsync, or a fetch in the constructor) would hit the licence
    server on every Settings open and on every tick, for no reason.
    """

    SETTINGS_VM = (Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs").read_text(
        encoding="utf-8")

    def test_no_timer_touches_the_device_loader(self):
        assert "DispatcherTimer" not in self.SETTINGS_VM, (
            "devices must never be polled; fetch only on expand or Refresh"
        )

    def test_the_constructor_does_not_call_the_loader_directly(self):
        """
        LoadDevicesAsync legitimately appears in the constructor as a command
        lambda (`() => LoadDevicesAsync(...)`, wired to RefreshDevicesCommand)
        — that's fine, it only runs when the button is clicked. What must not
        appear is an *immediate* call, i.e. `await LoadDevicesAsync` or
        `ListDevicesAsync` reached directly rather than through a command.
        """
        ctor = self.SETTINGS_VM.split("public SettingsViewModel(")[1].split(
            "\n    public AsyncRelayCommand ActivateCommand")[0]
        assert "await LoadDevicesAsync" not in ctor
        assert "await ListDevicesAsync" not in ctor
        assert "await _license.ListDevicesAsync" not in ctor

    def test_toggle_only_fetches_the_first_time_it_expands(self):
        toggle = self.SETTINGS_VM.split("private async Task ToggleDevicesAsync")[1].split(
            "\n    private async Task LoadDevicesAsync")[0]
        assert "_devicesLoadedOnce" in toggle, (
            "collapsing and re-expanding must not re-fetch; only the first "
            "expand (or an explicit Refresh) should hit the server"
        )

    def test_refresh_always_forces_a_fetch(self):
        assert "RefreshDevicesCommand = new AsyncRelayCommand(() => LoadDevicesAsync(force: true))" \
               in self.SETTINGS_VM


class TestDeviceReleaseNeedsConfirmation:
    """
    Release is a quiet button (DESIGN_SYSTEM.md §7), but it still removes a
    device's seat, so a single click must not do it. There has to be an
    explicit confirm/cancel step between the two, and the confirm control
    must be visually distinct (BtnDanger) from the initial Release click.
    """

    SETTINGS_VIEW = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(
        encoding="utf-8")
    SETTINGS_VM = (Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs").read_text(
        encoding="utf-8")

    def test_release_does_not_call_the_server_directly(self):
        """Clicking Release only requests confirmation; it must not itself
        call ReleaseDeviceAsync."""
        vm = self.SETTINGS_VM
        request = vm.split("RequestReleaseCommand = new RelayCommand(")[1].split(");")[0]
        assert "ReleaseDeviceAsync" not in request
        assert "IsConfirmingRelease = true" in request

    def test_a_second_explicit_step_is_required_to_actually_release(self):
        vm = self.SETTINGS_VM
        confirm = vm.split("ConfirmReleaseCommand = new AsyncRelayCommand(")[1].split(");")[0]
        assert "ReleaseDeviceAsync" in confirm

    def test_cancel_is_available_and_does_not_release(self):
        vm = self.SETTINGS_VM
        cancel = vm.split("CancelReleaseCommand = new RelayCommand(")[1].split(");")[0]
        assert "ReleaseDeviceAsync" not in cancel
        assert "IsConfirmingRelease = false" in cancel

    def test_the_confirm_button_uses_the_destructive_style(self):
        xaml = self.SETTINGS_VIEW
        confirm_button = xaml.split('Command="{Binding DataContext.ConfirmReleaseCommand')[0][-400:]
        assert 'Style="{StaticResource BtnDanger}"' in confirm_button

    def test_the_initial_release_button_uses_the_quiet_style(self):
        xaml = self.SETTINGS_VIEW
        release_button = xaml.split('Command="{Binding DataContext.RequestReleaseCommand')[0][-400:]
        assert 'Style="{StaticResource BtnQuiet}"' in release_button

    def test_a_device_can_never_release_its_own_seat_from_this_list(self):
        """CanRelease is false for the current device — that's Deactivate,
        not a row in this list."""
        vm = (Path(DESKTOP_DIR) / "ViewModels" / "DeviceRowViewModel.cs").read_text(
            encoding="utf-8")
        assert "CanRelease => !IsCurrent" in vm


class TestDeviceCapShowsTheListInline:
    """
    Hitting the 3-device cap during Activate must not be a dead end — the
    app shows the message right there and loads the list so the customer can
    release a seat without hunting for a separate control (Roadmap 5.7).
    """

    SETTINGS_VM = (Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs").read_text(
        encoding="utf-8")

    def test_activate_recognises_the_cap_reason(self):
        activate = self.SETTINGS_VM.split("private async Task ActivateAsync")[1].split(
            "\n    private async Task DeactivateAsync")[0]
        assert 'result.Status == "device_limit_reached"' in activate

    def test_the_cap_message_names_the_limit_and_the_fix(self):
        activate = self.SETTINGS_VM.split("private async Task ActivateAsync")[1].split(
            "\n    private async Task DeactivateAsync")[0]
        cap_branch = activate.split('result.Status == "device_limit_reached"')[1].split(
            "else")[0]
        assert "PCs" in cap_branch
        assert "Release one to activate here" in cap_branch

    def test_hitting_the_cap_loads_and_expands_the_device_list(self):
        activate = self.SETTINGS_VM.split("private async Task ActivateAsync")[1].split(
            "\n    private async Task DeactivateAsync")[0]
        cap_branch = activate.split('result.Status == "device_limit_reached"')[1].split(
            "else")[0]
        assert "LoadDevicesAsync" in cap_branch
        assert "IsDevicesExpanded = true" in cap_branch


# ============================ issue hygiene check (#158)

class TestIssueHygieneStaysAdvisory:
    """
    The check reports; it never edits. A tool that silently relabels or closes
    issues would be trusted for exactly as long as it takes to get one wrong,
    and the thing it is checking is judgement.
    """

    CHECK = Path(__file__).resolve().parent.parent.parent / "tools" / "issue_hygiene" / "check.py"
    WORKFLOW = (Path(__file__).resolve().parent.parent.parent / ".github" /
                "workflows" / "issue-hygiene.yml")

    def test_it_never_edits_an_issue(self):
        source = self.CHECK.read_text(encoding="utf-8")
        calls = re.findall(r'gh\("issue",\s*"(\w+)"', source)
        assert set(calls) <= {"list", "comment"}, (
            f"the check may only read issues and comment; it calls {sorted(set(calls))}"
        )
        for forbidden in ('"edit"', '"close"', '"reopen"', '"delete"'):
            assert f'gh("issue", {forbidden}' not in source

    def test_findings_do_not_fail_the_workflow(self):
        """
        Exit 10 means "found something", and the workflow must not treat it as
        a failure — only exit 2, "could not run", is a real error.
        """
        workflow = self.WORKFLOW.read_text(encoding="utf-8")
        assert 'if [ "$code" = "2" ]' in workflow
        assert "exit 10" not in workflow

    def test_it_runs_weekly_and_on_demand_only(self):
        """Not per merge: issue state drifts over days, not commits, and a
        report on every push is a report nobody reads."""
        workflow = self.WORKFLOW.read_text(encoding="utf-8")
        assert "schedule:" in workflow and "workflow_dispatch:" in workflow
        assert "on:\n  push:" not in workflow

    def test_the_label_set_matches_the_documented_one(self):
        """
        PLANNING.md's table is what people read; KIND_LABELS is what the check
        enforces. They drift apart silently otherwise.
        """
        planning = (Path(__file__).resolve().parent.parent.parent / "PLANNING.md"
                    ).read_text(encoding="utf-8")
        source = self.CHECK.read_text(encoding="utf-8")
        block = source.split("KIND_LABELS = {", 1)[1].split("}", 1)[0]
        for label in re.findall(r'"([a-z-]+)"', block):
            assert f"`{label}`" in planning, (
                f"the check knows the label {label!r}, but PLANNING.md does not list it"
            )

class TestThirdPartyNoticesShip:
    """
    The Lucide icons are ISC and the runtime, ProtectedData and Velopack are
    MIT; all of them require their notice to travel with the binary
    (LEGAL_CHECKLIST 8.2). A notice file that exists in the repo but is not
    copied to the output ships nothing.
    """

    NOTICES = Path(DESKTOP_DIR) / "THIRD-PARTY-NOTICES.txt"
    CSPROJ = Path(DESKTOP_DIR) / "FlowShield.csproj"

    def test_the_file_is_copied_next_to_the_exe(self):
        csproj = self.CSPROJ.read_text(encoding="utf-8")
        assert 'Include="THIRD-PARTY-NOTICES.txt"' in csproj
        assert "CopyToOutputDirectory" in csproj.split(
            'Include="THIRD-PARTY-NOTICES.txt"', 1)[1].split("/>", 1)[0], (
            "the notice is in the project but never reaches the output folder"
        )

    def test_it_names_every_component_the_app_actually_ships(self):
        notices = self.NOTICES.read_text(encoding="utf-8")
        csproj = self.CSPROJ.read_text(encoding="utf-8")
        for package in re.findall(r'PackageReference Include="([^"]+)"', csproj):
            assert package in notices, f"{package} ships with the app but is not in the notices"
        assert "Lucide" in notices and "ISC" in notices, (
            "the icon geometries are Lucide's and their ISC notice must ship"
        )

    def test_the_icons_licence_and_the_notices_agree(self):
        icons = (Path(DESKTOP_DIR) / "Assets" / "Icons" / "LICENSE").read_text(encoding="utf-8")
        notices = self.NOTICES.read_text(encoding="utf-8")
        for line in ("Copyright (c) for portions of Lucide are held by Cole Bemis",
                     "Permission to use, copy, modify, and/or distribute this software"):
            assert line in icons and line in notices

class TestTheSiteStaysOfflineForTheBeta:
    """
    The site is offline for the internal beta (#165): GitHub Pages' terms
    forbid selling from it, so it moves host before launch (#166). The
    publish script refuses without -BetaIsOver so that an agent following an
    older instruction cannot quietly put it back up.
    """

    SCRIPT = Path(__file__).resolve().parent.parent.parent / "tools" / "publish_site.ps1"

    def test_publishing_needs_an_explicit_switch(self):
        script = self.SCRIPT.read_text(encoding="utf-8")
        assert "param([switch]$BetaIsOver)" in script
        guard = script.split("if (-not $BetaIsOver)", 1)
        assert len(guard) == 2, "the refusal is gone"
        refusal = guard[1].split("}", 1)[0]
        assert "exit 1" in refusal, "refusing must stop the script, not just warn"

    def test_the_refusal_comes_before_anything_is_pushed(self):
        script = self.SCRIPT.read_text(encoding="utf-8")
        guard = script.index("if (-not $BetaIsOver)")
        # Everything before the guard is the help block and the param line:
        # no git call, no push, nothing that reaches gh-pages.
        before = script[:guard].split("#>", 1)[1]
        for command in ("git ", "Invoke-Git", "push", "Set-Location"):
            assert command not in before, (
                f"{command!r} runs before the beta guard, so it happens even when publishing is refused"
            )
        assert script.index("Invoke-Git", guard) > guard


# =================== the site self-hosts Inter, no third-party font host (B1)

class TestSiteFontsAreSelfHosted:
    """
    DESIGN_SYSTEM.md #147/#149: Inter replaces Syne + Source Sans 3, self-
    hosted under Website/fonts/ so the site never contacts Google Fonts.
    Written to fail against the pre-B1 site (Google Fonts <link>s in every
    page's <head>, no Website/fonts/ directory) before the fix landed.
    """

    FONTS_DIR = Path(WEBSITE_DIR) / "fonts"
    CSS = Path(WEBSITE_DIR) / "styles.css"
    PAGES = ["index.html", "support.html", "changelog.html", "legal.html", "success.html"]

    @pytest.mark.parametrize("page", PAGES)
    def test_no_page_references_a_third_party_font_host(self, page):
        html = (Path(WEBSITE_DIR) / page).read_text(encoding="utf-8")
        assert "fonts.googleapis.com" not in html, f"{page} still links Google Fonts"
        assert "fonts.gstatic.com" not in html, f"{page} still preconnects to Google Fonts"

    def test_every_font_face_src_file_exists_on_disk(self):
        css = self.CSS.read_text(encoding="utf-8")
        faces = re.findall(r"@font-face\s*{[^}]*}", css)
        assert faces, "styles.css has no @font-face rule — Inter isn't self-hosted"
        found_local_src = False
        checked_any_url = 0
        for face in faces:
            for url_match in re.finditer(r'url\(["\']?([^"\')]+)["\']?\)', face):
                checked_any_url += 1
                src_path = (Path(WEBSITE_DIR) / url_match.group(1)).resolve()
                assert src_path.is_file(), f"@font-face src file is missing: {url_match.group(1)}"
            if "local(" in face:
                found_local_src = True
        assert checked_any_url, "no @font-face rule has a url() src — nothing is actually self-hosted"
        assert found_local_src, "the size-adjusted local() fallback face is missing"

    def test_ofl_license_is_present(self):
        license_file = self.FONTS_DIR / "OFL.txt"
        assert license_file.is_file(), "Website/fonts/OFL.txt is missing"
        text = license_file.read_text(encoding="utf-8")
        assert "SIL OPEN FONT LICENSE" in text.upper()

    def test_fallback_face_is_size_adjusted_to_avoid_reflow(self):
        """
        §11: the hero must render text before any image loads, which only
        holds if the fallback-to-Inter swap doesn't visibly reflow it.
        """
        css = self.CSS.read_text(encoding="utf-8")
        fallback = css.split('font-family: "Inter Fallback";', 1)
        assert len(fallback) == 2, "the size-adjusted local fallback face is missing"
        block = fallback[1].split("}", 1)[0]
        for descriptor in ("size-adjust", "ascent-override", "descent-override"):
            assert descriptor in block, f"the Inter Fallback face is missing {descriptor}"

    def test_no_page_sets_swap_display_without_self_hosting(self):
        # font-display: swap only helps if the font is actually local — make
        # sure the primary Inter face uses it.
        css = self.CSS.read_text(encoding="utf-8")
        primary = css.split('font-family: "Inter";', 1)[1].split("}", 1)[0]
        assert "font-display: swap" in primary


# ==================================================== B3 — site system pass

class TestSiteSystemPassB3:
    """
    DESIGN_SYSTEM.md §5-§7 / UI-SPEC.md B3: the full §7 button set at 44px,
    the §6 shield glyph symbol set (echoing the app's A4
    DesktopApp/Styles/ShieldGlyphs.xaml), the missing 6px chip radius step,
    section rhythm on the 4-scale, and Lucide icons in place of the FAQ's
    Unicode +/- markers. Written to fail against the pre-B3 site (plain-text
    "Shield II" labels, no .btn-quiet/.btn-danger, no --radius-chip, 48/64px
    section padding, a "+"/mojibake "-" FAQ marker) before the fix landed.
    """

    CSS = Path(WEBSITE_DIR) / "styles.css"
    INDEX = Path(WEBSITE_DIR) / "index.html"
    # DesktopApp/Styles/ShieldGlyphs.xaml (A4, #147) landed on the app track's
    # own branch chain, not this site-track branch, so it isn't guaranteed to
    # exist on disk here — the crest path is copied verbatim (see B3's PR
    # body) rather than read cross-branch, which would make this test flaky
    # depending on which stack a checkout has.
    APP_SHIELD_CREST = (
        "M12,3 L19.5,6 L19.5,11.5 C19.5,16.2 16.3,19.8 12,21 "
        "C7.7,19.8 4.5,16.2 4.5,11.5 L4.5,6 Z"
    )

    def test_all_four_button_variants_are_44_high_radius_10(self):
        css = self.CSS.read_text(encoding="utf-8")
        base = css.split(".btn {", 1)[1].split("\n}", 1)[0]
        assert "height: 44px" in base, ".btn is not fixed at 44px tall"
        assert "border-radius: var(--radius-sm)" in base, ".btn does not use the 10px radius token"
        for variant in (".btn-primary", ".btn-ghost", ".btn-quiet", ".btn-danger"):
            assert re.search(re.escape(variant) + r"\s*{", css), f"{variant} is not defined in styles.css"

    def test_disabled_buttons_are_45_percent_opacity(self):
        css = self.CSS.read_text(encoding="utf-8")
        rule = css.split(".btn:disabled", 1)[1].split("}", 1)[0]
        assert "opacity: 0.45" in rule, ".btn:disabled is not at the §7 45% opacity"

    def test_shield_glyph_symbol_set_matches_the_apps_geometry(self):
        """
        The site's three <symbol>s must be the same crest path the app's A4
        ShieldGlyphs.xaml draws (not a hand-drawn approximation), and each
        must carry the right bar count — Soft 1, Firm 2, Sealed 3 plus the
        lock notch — the same escalation-through-fill-and-bars rule as §6.
        """
        html = self.INDEX.read_text(encoding="utf-8")

        assert html.count(self.APP_SHIELD_CREST) == 3, (
            "index.html's shield <symbol> set doesn't reuse the app's exact crest geometry "
            "in all three symbols"
        )

        soft = html.split('id="shield-soft-glyph"', 1)[1].split("</symbol>", 1)[0]
        firm = html.split('id="shield-firm-glyph"', 1)[1].split("</symbol>", 1)[0]
        sealed = html.split('id="shield-sealed-glyph"', 1)[1].split("</symbol>", 1)[0]

        assert soft.count("<path") == 2, "Soft glyph should be an outline plus exactly one bar"
        assert firm.count("<path") == 2, "Firm glyph should be an outline plus a two-bar path"
        assert 'fill="var(--color-primary)"' in sealed, "Sealed glyph isn't solid-filled"
        assert sealed.count("<path") >= 3, "Sealed glyph is missing its three-bar path and/or lock notch"
        assert "<circle" in sealed, "Sealed glyph is missing the lock notch"

    def test_shields_section_uses_the_glyphs_not_plain_text(self):
        html = self.INDEX.read_text(encoding="utf-8")
        shields = html.split('id="shields"', 1)[1].split('id="features"', 1)[0]
        assert '<div class="num">' not in shields, (
            "the shields section still has the old plain-text Shield II/III label "
            "instead of the glyph symbol set"
        )
        for glyph in ("#shield-soft-glyph", "#shield-firm-glyph", "#shield-sealed-glyph"):
            assert f'href="{glyph}"' in shields, f"the shields section never references {glyph}"

    def test_chip_radius_token_exists_and_is_used(self):
        css = self.CSS.read_text(encoding="utf-8")
        assert "--radius-chip: 6px;" in css, "the missing 6px chip radius step (REFERENCES gap #20) wasn't added"
        assert css.count("var(--radius-chip)") >= 2, (
            "the 6px chip token exists but nothing outside the token block actually uses it"
        )

    def test_section_rhythm_uses_composed_4_scale_multiples(self):
        css = self.CSS.read_text(encoding="utf-8")
        assert "--space-20: 80px;" in css and "--space-24: 96px;" in css, (
            "section-break spacing tokens (80/96, composed from the 32/48/64 steps) are missing"
        )
        rule = css.split("\nsection { padding:", 1)
        assert len(rule) == 2, "the base `section` rule is missing or was restructured"
        assert "var(--space-20)" in rule[1].split("}", 1)[0]

    def test_faq_uses_an_svg_chevron_not_a_unicode_marker(self):
        html = self.INDEX.read_text(encoding="utf-8")
        faq = html.split('id="faq"', 1)[1].split("</section>", 1)[0]
        # Counted against the FAQ's own entries rather than a hard-coded 7
        # (#193): adding a question should not have to edit this number, but
        # adding one *without* a chevron still has to fail.
        entries = faq.count("<summary>")
        assert entries >= 5, f"only {entries} FAQ entries"
        assert faq.count('class="chevron"') == entries, "expected one chevron icon per FAQ item"
        assert "summary::after" not in (self.CSS.read_text(encoding="utf-8")), (
            "styles.css still drives the FAQ marker from a ::after content glyph"
        )
        # The old marker was corrupted (\xc2\x91 + "2") mojibake for a minus
        # sign — make sure that byte sequence is gone for good, not just the
        # rule that displayed it.
        raw = self.CSS.read_bytes()
        assert b"\xc2\x91" not in raw, "the mojibake minus-sign byte is still in styles.css"

    def test_every_feature_card_has_a_lucide_icon(self):
        html = self.INDEX.read_text(encoding="utf-8")
        features = html.split('id="features"', 1)[1].split('id="pricing"', 1)[0]
        card_count = features.count('class="surface feature"')
        icon_count = features.count('class="feature-icon"')
        assert card_count == 3, (
            "fixture assumption changed: expected 3 feature cards (six until #185 cut the repeats)")
        assert icon_count == card_count, (
            f"{card_count} feature cards but only {icon_count} have a .feature-icon — "
            "every feature needs a Lucide icon, not just some of them"
        )

    def test_no_legacy_colour_aliases_reintroduced_by_this_pass(self):
        # TestNoLegacyColourAliases already covers the app and the general
        # site case; this just re-confirms the exact files B3 touched.
        css = self.CSS.read_text(encoding="utf-8")
        html = self.INDEX.read_text(encoding="utf-8")
        for name in ("--violet", "--cyan", "--grad"):
            assert f"{name}:" not in css
            assert f"var({name})" not in html

class TestTheSiteDescribesTheCloseTheAppDoes:
    """
    F7 (#146) made Firm and Sealed warn first, but the landing page kept
    saying they close apps "on sight" — a claim the build stopped making the
    day it merged, contradicting the legal page beside it. Nothing checked the
    marketing copy against GracefulClose, only the legal page.
    """

    def test_no_page_promises_an_instant_close_while_the_app_warns(self):
        model = (Path(DESKTOP_DIR) / "Models" / "GracefulClose.cs").read_text(encoding="utf-8")
        if "!hardKill && shield >= ShieldLevel.Firm" not in model:
            pytest.skip("Firm no longer warns; this claim test no longer applies")
        for page in sorted(Path(WEBSITE_DIR).glob("*.html")):
            text = " ".join(re.sub(r"<[^>]+>", " ", page.read_text(encoding="utf-8")).split()).lower()
            for claim in ("on sight", "hard close"):
                assert claim not in text, (
                    f"{page.name} says {claim!r}, but Firm and Sealed warn and wait "
                    f"before closing (GracefulClose.IsGraceful)"
                )

    def test_the_shields_section_says_it_warns(self):
        index = (Path(WEBSITE_DIR) / "index.html").read_text(encoding="utf-8")
        flat = " ".join(re.sub(r"<[^>]+>", " ", index).split())
        assert "Warns, then closes" in flat
        assert "Hard kill mode skips the warning" in flat, (
            "the page must not imply every user gets a warning — Hard kill gives none"
        )

class TestInterTypeScale:
    """
    DESIGN_SYSTEM.md §3: Inter, embedded, is the only face the app actually
    renders in (today's fallback chain put it third, behind two Segoe UI
    entries nobody's machine was missing). Embedded as a resource, with its
    OFL licence kept alongside, and its pack URI assembly-qualified so it
    also resolves when the render kit hosts the built DLL rather than
    launching FlowShield.exe.
    """

    FONTS_DIR = Path(DESKTOP_DIR) / "Assets" / "Fonts"
    CSPROJ = Path(DESKTOP_DIR) / "FlowShield.csproj"
    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"
    TODAY_VIEW = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"
    VIEWS = ("MainWindow.xaml", "Views/BlockedAppsView.xaml", "Views/FriendlyErrorDialog.xaml",
             "Views/SleepBlockingView.xaml", "Views/TodayView.xaml", "Views/SettingsView.xaml")

    EMBEDDED_WEIGHTS = ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf")

    # A view is allowed to reference the FontStack resource, or -- for
    # licence keys and anything the user must copy exactly, §3's own
    # exception -- the Cascadia Mono fallback. Nothing else.
    ALLOWED_FONT_FAMILY_VALUES = ("{StaticResource FontStack}", "Cascadia Mono, Consolas, monospace")

    def test_fonts_are_embedded_on_disk_and_in_the_csproj(self):
        csproj = self.CSPROJ.read_text(encoding="utf-8")
        for weight in self.EMBEDDED_WEIGHTS:
            font_path = self.FONTS_DIR / weight
            assert font_path.is_file(), (
                f"{font_path} is missing -- Inter must actually be embedded, not just "
                f"referenced")
            assert f'Assets\\Fonts\\{weight}' in csproj, (
                f"{weight} exists on disk but has no <Resource Include> entry in "
                f"FlowShield.csproj, so it won't ship in the build")

    def test_bold_is_not_embedded_unless_the_scale_uses_it(self):
        """
        §3's scale doesn't use weight 700 anywhere in the app (it's reserved
        for the site hero). UI-SPEC.md §2 is explicit: don't embed Inter-Bold
        unless a real in-app use is found. A stray Bold file would be dead
        weight nobody meant to ship.
        """
        assert not (self.FONTS_DIR / "Inter-Bold.ttf").exists(), (
            "Inter-Bold is embedded but nothing in the §3 app scale uses weight 700 -- "
            "either use it for something real and document why, or drop it")

    def test_the_ofl_licence_is_present(self):
        licence = self.FONTS_DIR / "OFL.txt"
        assert licence.is_file(), "Inter is OFL-licensed; its licence text must ship with it"
        text = licence.read_text(encoding="utf-8")
        assert "SIL Open Font License" in text

    def test_font_stack_is_an_assembly_qualified_pack_uri(self):
        """
        A relative pack URI resolves fine when FlowShield.exe launches itself,
        but silently falls back to a system font when the render kit hosts
        the built DLL directly -- the exact split this test guards against.
        """
        theme = self.THEME.read_text(encoding="utf-8")
        match = re.search(r'<FontFamily x:Key="FontStack">([^<]+)</FontFamily>', theme)
        assert match, "Theme.xaml should define the FontStack FontFamily resource"
        stack = match.group(1)
        assert stack.startswith("pack://application:,,,/FlowShield;component/Assets/Fonts/#Inter"), (
            f"FontStack is {stack!r} -- it must start with the assembly-qualified pack "
            f"URI form, or the render kit's hosted-DLL rendering falls back to Segoe")

    def test_no_view_sets_a_font_family_other_than_the_stack(self):
        offenders = []
        for name in self.VIEWS:
            path = Path(DESKTOP_DIR) / name
            if not path.exists():
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for value in re.findall(r'FontFamily="([^"]+)"', line):
                    if value not in self.ALLOWED_FONT_FAMILY_VALUES:
                        offenders.append(f"{name}:{n} sets FontFamily={value!r}")
        assert not offenders, (
            "a view should reference the FontStack resource (or, for licence keys "
            "only, the Cascadia Mono fallback), not set its own literal FontFamily:\n  "
            + "\n  ".join(offenders))

    def _tag_for(self, xml: str, automation_id: str) -> str:
        """The full opening tag (attributes only) that carries this AutomationId."""
        match = re.search(
            r'<(\w+)\b((?:(?!/?>).)*?AutomationId="' + re.escape(automation_id) + r'"(?:(?!/?>).)*?)/?>',
            xml, re.S)
        assert match, f"no element with AutomationId={automation_id!r} found"
        return match.group(2)

    def test_timer_and_stat_numbers_are_tabular(self):
        """
        §3: the timer, momentum, and every Today stat are tabular so the
        digits don't jiggle as they change. Checked by AutomationId, which
        survives a restyle better than matching on FontSize.
        """
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        tabular_ids = (
            "SprintTimerText", "MomentumValue", "SessionsTodayValue",
            "FocusMinutesValue", "BlocksTodayValue", "DailyGoalProgressText",
        )
        offenders = []
        for automation_id in tabular_ids:
            tag = self._tag_for(xml, automation_id)
            if 'Typography.NumeralAlignment="Tabular"' not in tag:
                offenders.append(automation_id)
        assert not offenders, (
            "these number displays are missing Typography.NumeralAlignment=\"Tabular\": "
            + ", ".join(offenders))

    def test_blocked_app_row_name_and_summary_do_not_wrap(self):
        """
        Regression (PR #171 review): Inter's wider metrics overflowed the
        blocked-app row's fixed-width name column, which fit under Segoe UI
        but, post-swap, wrapped "Minecraft Launcher" to two lines and its
        exe-name line ("minecraftlauncher.exe, Minecraft.Windows.exe") to
        three, with mid-word splits ("minecraftlauncher.ex" / "e"). Both
        TextBlocks must trim to a single line with an ellipsis instead of
        wrapping, so a long app or process name never breaks mid-word again
        regardless of how narrow the row gets.
        """
        view = Path(DESKTOP_DIR) / "Views" / "BlockedAppsView.xaml"
        xml = view.read_text(encoding="utf-8")

        name_match = re.search(
            r'<TextBlock Text="\{Binding DisplayName\}"(?:(?!/?>).)*?/>', xml, re.S)
        assert name_match, "expected the blocked-app row's name TextBlock bound to DisplayName"
        name_tag = name_match.group(0)
        assert 'TextWrapping="NoWrap"' in name_tag, (
            "the blocked-app row's name TextBlock must set TextWrapping=\"NoWrap\" -- "
            "otherwise a long app name wraps across lines under Inter's wider metrics")
        assert 'TextTrimming="CharacterEllipsis"' in name_tag, (
            "the blocked-app row's name TextBlock must set TextTrimming=\"CharacterEllipsis\" "
            "so a long name trims with an ellipsis instead of being clipped bare")

        summary_match = re.search(
            r'<TextBlock Style="\{StaticResource Caption\}"(?:(?!/?>).)*?>'
            r'\s*<Run Text="\{Binding ProcessSummary', xml, re.S)
        assert summary_match, (
            "expected the blocked-app row's process-summary TextBlock bound to "
            "ProcessSummary via a Run")
        summary_tag = summary_match.group(0)
        assert 'TextWrapping="NoWrap"' in summary_tag, (
            "the blocked-app row's process-summary TextBlock must set "
            "TextWrapping=\"NoWrap\" -- otherwise a single long exe name (no spaces) "
            "forces a mid-word break to fit the narrow column")
        assert 'TextTrimming="CharacterEllipsis"' in summary_tag, (
            "the blocked-app row's process-summary TextBlock must set "
            "TextTrimming=\"CharacterEllipsis\" so a long exe name trims with an "
            "ellipsis instead of breaking mid-word")


class TestShieldGlyphsA4:
    """
    DESIGN_SYSTEM.md §6: the three shields are built once, as XAML geometry,
    and reused everywhere a shield glyph appears. UI-SPEC.md A4 wires that
    resource into the Today page's shield chips and the timer ring.
    """

    GLYPHS = Path(DESKTOP_DIR) / "Styles" / "ShieldGlyphs.xaml"
    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"
    TODAY_VIEW = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"

    def _resource_block(self, xml: str, key: str) -> str:
        match = re.search(
            r'<DrawingImage x:Key="' + re.escape(key) + r'">.*?</DrawingImage>', xml, re.S)
        assert match, f"no ShieldGlyph{key.replace('ShieldGlyph', '')} DrawingImage resource found"
        return match.group(0)

    def test_glyph_file_exists_and_takes_its_brushes_from_the_tokens(self):
        """
        F21: the glyphs no longer merge Tokens.xaml themselves -- that copy
        would shadow the dictionary ThemeService swaps, and the glyphs would
        stay dark on a light background. They use DynamicResource instead, and
        App.xaml merges the tokens ahead of them.
        """
        assert self.GLYPHS.is_file(), (
            "DesktopApp/Styles/ShieldGlyphs.xaml is missing -- the shield glyphs must be "
            "built once, in a shared resource dictionary (UI-SPEC.md A4)")
        xml = self.GLYPHS.read_text(encoding="utf-8")
        assert '<ResourceDictionary Source="Tokens.xaml"/>' not in xml, (
            "ShieldGlyphs.xaml must not merge the tokens itself -- that copy shadows "
            "the dictionary F21 swaps at run time")
        assert "{DynamicResource" in xml and "{StaticResource" not in xml, (
            "the glyph brushes must be DynamicResource so a fresh load of this "
            "dictionary picks up the theme in force")

    def test_the_app_merges_the_glyph_dictionary(self):
        app = (Path(DESKTOP_DIR) / "App.xaml").read_text(encoding="utf-8")
        assert '<ResourceDictionary Source="Styles/ShieldGlyphs.xaml"/>' in app, (
            "App.xaml must merge ShieldGlyphs.xaml, after the tokens, or the glyph "
            "resources are never loaded into the app")

    def test_exactly_three_levels_are_defined(self):
        xml = self.GLYPHS.read_text(encoding="utf-8")
        for key in ("ShieldGlyphSoft", "ShieldGlyphFirm", "ShieldGlyphSealed"):
            assert xml.count(f'x:Key="{key}"') == 1, (
                f"expected exactly one {key} resource")

    def test_soft_is_outline_and_one_bar_in_text_muted(self):
        """§6: Soft is a shield outline with one bar, in text-muted (InkDim), never primary."""
        block = self._resource_block(self.GLYPHS.read_text(encoding="utf-8"), "ShieldGlyphSoft")
        assert "{DynamicResource InkDim}" in block
        assert "{DynamicResource Primary}" not in block, (
            "Soft must never use primary -- strength escalates through fill and bar "
            "count, not colour (§6)")
        assert block.count("M8.5,") == 1, "Soft should draw exactly one bar"

    def test_firm_is_outline_and_two_bars_in_primary(self):
        block = self._resource_block(self.GLYPHS.read_text(encoding="utf-8"), "ShieldGlyphFirm")
        assert block.count("{DynamicResource Primary}") >= 1
        assert "{DynamicResource InkDim}" not in block
        assert block.count("M8.5,") == 2, "Firm should draw exactly two bars"

    def test_sealed_is_solid_primary_with_three_bars_and_a_lock_notch_in_primary_ink(self):
        block = self._resource_block(self.GLYPHS.read_text(encoding="utf-8"), "ShieldGlyphSealed")
        assert 'Brush="{DynamicResource Primary}"' in block, (
            "Sealed's shield shape must be a solid primary fill, not an outline")
        assert block.count("{DynamicResource PrimaryInk}") >= 2, (
            "Sealed's bars and lock notch must be drawn in primary-ink for contrast "
            "against the solid fill")
        assert block.count("M8.5,") == 3, "Sealed should draw exactly three bars"

    def test_shield_chips_reference_the_shared_glyph_resource(self):
        """
        DynamicResource since F21: ThemeService reloads the glyph dictionary on
        a theme change, and a StaticResource would hold the old instance.
        """
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        for key in ("ShieldGlyphSoft", "ShieldGlyphFirm", "ShieldGlyphSealed"):
            assert f'Source="{{DynamicResource {key}}}"' in xml, (
                f"the {key} chip should render the shared glyph resource, not its own "
                f"re-derived geometry")

    def test_timer_ring_uses_the_glyph_via_a_converter(self):
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        assert 'Converter={StaticResource ShieldGlyph}' in xml, (
            "the timer ring should show the active shield's glyph via a level->glyph "
            "converter (one resource, reused, not a duplicate drawing)")


class TestTimerRingA4:
    """UI-SPEC.md A4, §1.7.2 doc amendment: 222px ring, 12px stroke, round cap."""

    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"
    TODAY_VIEW = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"

    def test_ring_is_222px_with_a_12px_round_capped_stroke(self):
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        ring_grid = re.search(r'<Grid Width="222" Height="222"[^>]*>', xml)
        assert ring_grid, "the timer ring's outer Grid must be 222x222 (§1.7.2 doc amendment)"
        strokes = re.findall(r'<Ellipse [^>]*StrokeThickness="(\d+)"', xml)
        assert strokes and all(s == "12" for s in strokes[:2]), (
            "both ring ellipses (track and progress) must use a 12px stroke")
        assert 'StrokeDashCap="Round"' in xml, "the progress arc must have a round cap"

    def test_progress_dash_radius_matches_the_ring_geometry(self):
        """
        The dash-array converter computes off the stroke's centreline: radius =
        (ellipse diameter - stroke thickness) / 2. A mismatch here would make the
        arc visibly overshoot or undershoot the track it's drawn over.
        """
        theme = self.THEME.read_text(encoding="utf-8")
        match = re.search(
            r'<inf:ProgressToDashConverter x:Key="ProgressDash" Radius="([\d.]+)" '
            r'Thickness="([\d.]+)"/>', theme)
        assert match, "expected the ProgressDash converter resource in Theme.xaml"
        radius, thickness = float(match.group(1)), float(match.group(2))

        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        ellipse_widths = {float(w) for w in re.findall(r'<Ellipse Width="([\d.]+)"', xml)}
        assert len(ellipse_widths) == 1, f"expected one consistent ring diameter, got {ellipse_widths}"
        diameter = next(iter(ellipse_widths))

        assert radius == pytest.approx((diameter - thickness) / 2), (
            f"ProgressDash Radius={radius} doesn't match the ring geometry "
            f"(diameter={diameter}, stroke={thickness} -> expected radius "
            f"{(diameter - thickness) / 2})")

    def test_long_times_shrink_to_fit_inside_the_ring(self):
        """
        At the 64 px timer size "45:00" fits inside the ring, but "1:29:59"
        (a running sprint of an hour or more) and "240:00" (the custom
        maximum, TodayViewModel.CustomMaxMinutes) ran across the 12 px stroke.
        The number sits in a Viewbox that only ever shrinks it, capped inside
        the ring's 198 px inner diameter.
        """
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        fit = re.search(r'<Viewbox x:Name="TimerFit"([^>]*)>(.*?)</Viewbox>', xml, re.S)
        assert fit, "the timer TextBlock must sit inside the TimerFit Viewbox"
        attrs, body = fit.group(1), fit.group(2)
        assert 'StretchDirection="DownOnly"' in attrs, (
            "the Viewbox must only shrink the number; enlarging short times would "
            "change the timer's size as it counts down")
        max_width = re.search(r'MaxWidth="([\d.]+)"', attrs)
        inner = 222 - 2 * 12
        assert max_width and float(max_width.group(1)) < inner, (
            f"the Viewbox needs a MaxWidth inside the ring's {inner} px inner diameter")
        assert 'AutomationProperties.AutomationId="SprintTimerText"' in body, (
            "SprintTimerText stays on the TextBlock itself, inside the Viewbox")

    def test_timer_and_stat_styles_use_inter_display(self):
        """
        UI-SPEC.md A4 / DESIGN_SYSTEM.md §3: the timer and stat numbers set
        Inter Display, the tighter optical size for display-scale digits.
        """
        theme = self.THEME.read_text(encoding="utf-8")
        for style_key in ("Timer", "Stat"):
            style_match = re.search(
                r'<Style x:Key="' + style_key + r'" TargetType="TextBlock">.*?</Style>',
                theme, re.S)
            assert style_match, f"expected the {style_key} style in Theme.xaml"
            assert '{StaticResource FontStackDisplay}' in style_match.group(0), (
                f"the {style_key} style should set FontFamily to FontStackDisplay")

    def test_inter_display_semibold_is_embedded(self):
        font_path = Path(DESKTOP_DIR) / "Assets" / "Fonts" / "InterDisplay-SemiBold.ttf"
        assert font_path.is_file(), "InterDisplay-SemiBold.ttf must be embedded on disk"
        csproj = (Path(DESKTOP_DIR) / "FlowShield.csproj").read_text(encoding="utf-8")
        assert r"Assets\Fonts\InterDisplay-SemiBold.ttf" in csproj, (
            "InterDisplay-SemiBold.ttf exists on disk but has no <Resource Include> "
            "entry in FlowShield.csproj, so it won't ship in the build")


class TestTodayAutomationIdsUnchangedA4:
    """
    Three past incidents put an AutomationId on a layout panel during a
    restyle (#134 and friends) -- UI Automation never surfaces it, so a test
    asking for it would pass whether the control was drawn or not. A4
    rebuilds the ring and the shield chips; every AutomationId that existed
    before must still exist, on a real control, not a Border/Grid/StackPanel/
    Image wrapper.
    """

    TODAY_VIEW = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"

    # The full set of AutomationIds TodayView.xaml carried before A4 touched it
    # (PR #171 / design/a1-inter-app). A4 must not remove or rename any of these.
    EXPECTED_IDS = {
        "SprintTimerText", "SessionStateText", "SprintIntentionText",
        "StartSprintButton", "StopSprintButton",
        "RunningAppsTitle", "RunningAppsExplanation", "RunningAppsList",
        "CloseThemNowButton", "StartAnywayButton",
        "EndSprintPanel", "EndPanelTitle", "EndPanelText", "EndPhraseInput",
        "EndCountdownText", "KeepGoingButton", "EndAnywayButton",
        "SprintLength_15", "SprintLength_25", "SprintLength_45", "SprintLength_60",
        "SprintLength_90", "SprintLength_Custom",
        "CustomMinutesInput", "CustomMinutesError",
        "Shield_Soft", "Shield_Firm", "Shield_Sealed",
        "ShieldDescriptionText", "ShieldBestForText",
        "SealedRestartHint", "SoftHardKillHint",
        "IntentionInput",
        "SummaryTitle", "SummaryMinutesValue", "SummaryDistractionsValue",
        "SummaryMomentumText", "SummaryStreakText", "SummaryIntentionText",
        "JournalPromptTitle", "JournalInput", "SaveJournalButton",
        "MomentumValue", "StreakText", "MomentumTrendRange", "MomentumTrendPeak",
        "MomentumExplainerButton", "MomentumExplainerText",
        "SessionsTodayValue", "FocusMinutesValue", "BlocksTodayValue",
        "DailyGoalProgressText", "DailyGoalBar", "DailyGoalNote",
    }

    # Elements UI Automation never surfaces -- an AutomationId here can never
    # be resolved, so it's not a legitimate handle for anything. Border and
    # ItemsControl are deliberately excluded here: two pre-existing ids
    # (EndSprintPanel, MomentumExplainerText) already sit on those element
    # types from before A4 and are out of this item's scope to relitigate.
    # This list guards the element types A4's own rebuild actually
    # introduces (the ring's Grid, the shield chips' wrapper StackPanel and
    # Image) against the same mistake.
    PANEL_ELEMENTS = ("Grid", "StackPanel", "WrapPanel", "DockPanel", "Image")

    def test_every_expected_automation_id_is_still_present(self):
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        found = set(re.findall(r'AutomationId="([^"]+)"', xml))
        missing = self.EXPECTED_IDS - found
        assert not missing, f"AutomationIds removed or renamed by A4: {sorted(missing)}"

    def test_no_automation_id_sits_on_a_layout_panel(self):
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        offenders = []
        for tag in re.finditer(r'<(\w+)\b((?:(?!/?>).)*?)/?>', xml, re.S):
            element, attrs = tag.group(1), tag.group(2)
            if element in self.PANEL_ELEMENTS and 'AutomationId="' in attrs:
                offenders.append(f"<{element}> has an AutomationId -- never surfaced to UI Automation")
        assert not offenders, "\n".join(offenders)


class TestMotionA4:
    """
    DESIGN_SYSTEM.md §8: 120/200/300ms, ease-out entering / ease-in leaving,
    honouring SystemParameters.ClientAreaAnimation everywhere. UI-SPEC.md A4
    asks for one shared duration provider rather than a per-animation check.
    """

    MOTION = Path(DESKTOP_DIR) / "Infrastructure" / "Motion.cs"
    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"

    def test_motion_helper_exists_and_defines_the_three_durations(self):
        assert self.MOTION.is_file(), (
            "DesktopApp/Infrastructure/Motion.cs is missing -- every Today-view "
            "animation must share one duration provider, not read "
            "SystemParameters.ClientAreaAnimation individually")
        src = self.MOTION.read_text(encoding="utf-8")
        assert "SystemParameters.ClientAreaAnimation" in src, (
            "Motion must read the live OS reduced-motion setting")
        for prop, ms in (("Hover", 120), ("Selection", 200), ("Page", 300)):
            pattern = re.search(
                r'Duration ' + prop + r' =>.*?Of\((\d+)\)', src)
            assert pattern, f"expected a {prop} duration property"
            assert pattern.group(1) == str(ms), (
                f"{prop} should be {ms}ms per DESIGN_SYSTEM.md §8, got {pattern.group(1)}ms")

    def test_durations_collapse_to_zero_when_animations_are_disabled(self):
        """
        Prove the reduced-motion branch actually exists: every duration must
        be computed as "AnimationsEnabled ? <ms> : 0", not a hardcoded
        millisecond value that ignores the setting.

        Proven to fail first: with the ternary replaced by a bare literal
        (e.g. `private static Duration Of(int ms) =>
        new(TimeSpan.FromMilliseconds(ms));`), this test fails, because the
        conditional this regex looks for is gone.
        """
        src = self.MOTION.read_text(encoding="utf-8")
        match = re.search(
            r'private static Duration Of\(int ms\) =>\s*'
            r'new\(TimeSpan\.FromMilliseconds\(AnimationsEnabled \? ms : 0\)\);', src)
        assert match, (
            "Motion.Of must compute its duration as \"AnimationsEnabled ? ms : 0\" so "
            "every duration in the app is exactly zero when Windows' Animation "
            "effects setting (or the test override) is off")

    def test_motion_has_a_test_seam_for_the_os_setting(self):
        src = self.MOTION.read_text(encoding="utf-8")
        assert "AnimationsEnabledOverride" in src, (
            "Motion needs an injectable override -- SystemParameters.ClientAreaAnimation "
            "reads the live host setting, which a test can't flip")

    def test_segment_and_field_styles_animate_through_shared_motion_durations(self):
        """
        The disabled-but-visible chip/field treatment (UI-SPEC.md A4: sprint
        length, shield level and intention all dim to 45% opacity while a
        sprint runs) must animate through Motion.Selection, not a hardcoded
        Storyboard duration that would ignore reduced motion.
        """
        theme = self.THEME.read_text(encoding="utf-8")
        for style_key in ("Segment", "SegmentShield", "Field"):
            style_match = re.search(
                r'<Style x:Key="' + style_key + r'".*?(?=<Style x:Key|\Z)', theme, re.S)
            assert style_match, f"expected the {style_key} style in Theme.xaml"
            block = style_match.group(0)
            assert 'Duration="{x:Static inf:Motion.Selection}"' in block, (
                f"{style_key}'s IsEnabled/IsChecked animations must bind Duration to "
                f"{{x:Static inf:Motion.Selection}}, not a literal duration")
            assert not re.search(r'Duration="0:0:0\.\d+"', block), (
                f"{style_key} has a hardcoded animation Duration instead of using "
                f"Motion.Selection")


class TestContrastAndTokensA3:
    """
    UI-SPEC.md A3 (#147, DESIGN_SYSTEM.md §2): text-faint and the light-theme
    ok/warn/danger values were measured below WCAG 2.1's 4.5:1 normal-text
    threshold. This computes the ratios straight from design/tokens.json --
    the single source of truth -- for every pair in DESIGN_SYSTEM.md's
    "Contrast" table, in both themes.

    Proven to fail first: run against the pre-fix values (text-faint dark
    #7E7B73 / light #8A867E; ok light #2F7D4A; warn light #9A6B1F; danger
    light #B33A4A) and text-faint on surface measures 4.07:1 (dark) / 3.27:1
    (light) -- both below 4.5, matching the doc's own "current" column -- and
    the light ok/warn pairs also fail. Restoring the pre-fix hex values below
    and rerunning reproduces that failure; the fixed values in tokens.json
    pass every pair.
    """

    ROOT = Path(DESKTOP_DIR).parent
    TOKENS = ROOT / "design" / "tokens.json"

    PRE_FIX_TEXT_FAINT = {"dark": "#7E7B73", "light": "#8A867E"}
    PRE_FIX_STATUS_LIGHT = {"ok": "#2F7D4A", "warn": "#9A6B1F", "danger": "#B33A4A"}

    # Every pair DESIGN_SYSTEM.md §2's "Contrast" table measures.
    PAIRS = [
        ("text", "bg"),
        ("text-muted", "bg"),
        ("text-faint", "surface"),
        ("primary", "bg"),
        ("primary-ink", "primary"),
        ("warn", "bg"),
        ("ok", "bg"),
        ("danger", "bg"),
    ]

    THRESHOLD = 4.5

    @staticmethod
    def _hex_to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

    @classmethod
    def _resolve(cls, theme: dict, name: str, seen: tuple = ()) -> tuple[int, int, int, float]:
        """A token as (r, g, b, alpha), following {"ref", "alpha"} references --
        the same resolution rule tools/build_tokens.py uses."""
        assert name not in seen, f"circular token reference: {seen + (name,)}"
        value = theme[name]
        if isinstance(value, str):
            r, g, b = cls._hex_to_rgb(value)
            return r, g, b, 1.0
        r, g, b, _ = cls._resolve(theme, value["ref"], seen + (name,))
        return r, g, b, float(value["alpha"])

    @staticmethod
    def _composite(fg: tuple[int, int, int, float], bg: tuple[int, int, int, float]) -> tuple[int, int, int]:
        """Alpha-composite fg over bg (both already resolved), for tokens defined as a ref+alpha."""
        fr, fg_, fb, fa = fg
        br, bgc, bb, _ba = bg
        return (
            round(fr * fa + br * (1 - fa)),
            round(fg_ * fa + bgc * (1 - fa)),
            round(fb * fa + bb * (1 - fa)),
        )

    @staticmethod
    def _luminance(rgb: tuple[int, int, int]) -> float:
        def lin(c: int) -> float:
            c = c / 255
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = rgb
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

    @classmethod
    def _contrast(cls, rgb1: tuple[int, int, int], rgb2: tuple[int, int, int]) -> float:
        l1, l2 = cls._luminance(rgb1), cls._luminance(rgb2)
        lighter, darker = max(l1, l2), min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    def _ratio(self, theme: dict, fg_name: str, bg_name: str) -> float:
        fg = self._resolve(theme, fg_name)
        bg = self._resolve(theme, bg_name)
        fg_rgb = self._composite(fg, bg) if fg[3] < 1.0 else fg[:3]
        bg_rgb = bg[:3]
        return self._contrast(fg_rgb, bg_rgb)

    def _themes(self) -> dict:
        return json.loads(self.TOKENS.read_text(encoding="utf-8"))["themes"]

    @pytest.mark.parametrize("theme_name", ["dark", "light"])
    def test_every_section_2_pair_meets_wcag_normal_text(self, theme_name):
        themes = self._themes()
        theme = themes[theme_name]
        failures = []
        for fg_name, bg_name in self.PAIRS:
            ratio = self._ratio(theme, fg_name, bg_name)
            if ratio < self.THRESHOLD:
                failures.append(f"{fg_name} on {bg_name} ({theme_name}): {ratio:.2f}:1")
        assert not failures, (
            "tokens.json pairs fail WCAG 2.1's 4.5:1 normal-text threshold: "
            + "; ".join(failures)
        )

    @pytest.mark.parametrize("theme_name", ["dark", "light"])
    def test_pre_fix_values_would_have_failed(self, theme_name):
        """Confirms this test is actually load-bearing: swap in the exact
        pre-fix hex values DESIGN_SYSTEM.md's "current" column measured, and
        the same computation must fail below 4.5:1."""
        themes = self._themes()
        theme = dict(themes[theme_name])
        theme["text-faint"] = self.PRE_FIX_TEXT_FAINT[theme_name]
        if theme_name == "light":
            theme.update(self.PRE_FIX_STATUS_LIGHT)

        ratio = self._ratio(theme, "text-faint", "surface")
        assert ratio < self.THRESHOLD, (
            f"expected the pre-fix text-faint/surface ratio to fail below 4.5:1, got {ratio:.2f}:1 "
            f"-- this test would no longer prove the fix does anything")

        if theme_name == "light":
            for status in ("ok", "warn"):
                ratio = self._ratio(theme, status, "bg")
                assert ratio < self.THRESHOLD, (
                    f"expected the pre-fix light {status}/bg ratio to fail below 4.5:1, got {ratio:.2f}:1")


class TestNoHardcodedColoursA3:
    """
    UI-SPEC.md A3 (#147, DESIGN_SYSTEM.md §2 "No hard-coded colours in
    views"): every colour in the restyled files must come from a
    design/tokens.json-generated resource, referenced by name -- never a
    literal #RRGGBB/#AARRGGBB in the markup itself.

    Proven to fail first: this test fails against the pre-A3 Theme.xaml
    (Card's DropShadowEffect Color="#FF000000", BtnDanger's
    Background="#22FF6B8B"/BorderBrush="#55FF6B8B", the scrollbar thumb's
    Background="#30FFFFFF") and the pre-A3 MainWindow.xaml (four scrim
    Background="#F2121110"/"#B3121110"/"#F7121110" occurrences).
    """

    ROOT = Path(DESKTOP_DIR).parent
    HEX = re.compile(r'#[0-9A-Fa-f]{6,8}\b')

    FILES = (
        [Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"]
        + sorted((Path(DESKTOP_DIR) / "Views").glob("*.xaml"))
        + [Path(DESKTOP_DIR) / "MainWindow.xaml"]
    )

    def test_no_hex_colour_literal_remains(self):
        offenders = []
        for path in self.FILES:
            text = path.read_text(encoding="utf-8")
            for match in self.HEX.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(self.ROOT)}:{line_no}: {match.group(0)}")
        assert not offenders, (
            "hard-coded hex colour literal(s) found -- reference a Tokens.xaml-generated "
            "brush resource instead:\n" + "\n".join(offenders)
        )

    def test_the_files_list_actually_covers_something(self):
        """A regex that silently matched zero files would pass for the wrong
        reason -- confirm the scan really walks a non-trivial set of XAML."""
        assert len(self.FILES) >= 5, "expected Theme.xaml, MainWindow.xaml and several Views/*.xaml"

    # ------------------------------------------------------------------ C#
    #
    # F21 (#236): the markup was the only thing checked, so a colour could
    # still be built in code and escape the tokens entirely -- and two were.
    # The tray's countdown icon was drawn in a literal teal and near-black
    # (Color.FromArgb(0xFF, 0x3A, 0xA8, 0x92) / (0xFF, 0x0E, 0x14, 0x12)) and
    # the heatmap ramp fell back to Color.FromRgb(0x18, 0x20, 0x1E) /
    # (0x3A, 0xA8, 0x92). All four are the dark theme's colours frozen into
    # code: in the light theme the tray icon stayed dark-theme teal on a
    # near-black disc. This test fails against each of them.

    CSHARP_FILES = tuple(
        path for path in Path(DESKTOP_DIR).rglob("*.cs")
        if "obj" not in path.parts and "bin" not in path.parts
    )

    #: A colour built from literals, rather than read from a token.
    LITERAL_COLOUR = re.compile(
        r"From(?:A?)[Rr]gb\(\s*(?:0[xX][0-9A-Fa-f]+|\d+)\s*(?:,\s*(?:0[xX][0-9A-Fa-f]+|\d+)\s*)+\)"
    )
    #: A colour taken from the framework's palette instead of the tokens.
    NAMED_COLOUR = re.compile(r"\bBrushes\.\w+|new SolidColorBrush\(Colors\.\w+")
    #: A hex literal in a string, e.g. ColorConverter.ConvertFromString("#3AA892").
    HEX_IN_CODE = re.compile(r'"#[0-9A-Fa-f]{6,8}"')

    def test_no_colour_is_built_from_literals_in_code(self):
        offenders = []
        for path in self.CSHARP_FILES:
            text = path.read_text(encoding="utf-8")
            for pattern in (self.LITERAL_COLOUR, self.NAMED_COLOUR, self.HEX_IN_CODE):
                for match in pattern.finditer(text):
                    line_no = text.count("\n", 0, match.start()) + 1
                    offenders.append(
                        f"{path.relative_to(self.ROOT)}:{line_no}: {match.group(0)}")
        assert not offenders, (
            "colours built in C# do not follow the theme -- read the token with "
            "ThemeService.TryColour instead:\n" + "\n".join(offenders))

    def test_the_csharp_scan_covers_the_app(self):
        assert len(self.CSHARP_FILES) >= 20, \
            f"expected the whole app to be scanned, got {len(self.CSHARP_FILES)} files"

    def test_the_patterns_catch_the_colours_that_were_there(self):
        """The four literals F21 removed, verbatim -- the regexes must match them."""
        assert self.LITERAL_COLOUR.search(
            "new System.Drawing.SolidBrush(System.Drawing.Color.FromArgb(0xFF, 0x3A, 0xA8, 0x92))")
        assert self.LITERAL_COLOUR.search("MediaColor.FromRgb(0x18, 0x20, 0x1E)")
        assert self.NAMED_COLOUR.search("new SolidColorBrush(Colors.HotPink)")
        assert self.HEX_IN_CODE.search('ColorConverter.ConvertFromString("#3AA892")')
        # And must not flag the ramp's computed mix, which is the correct shape.
        assert not self.LITERAL_COLOUR.search(
            "MediaColor.FromRgb((byte)Math.Round(from.R + (to.R - from.R) * mix), g, b)")


class TestCornerRadiusNormalisedA2:
    """
    UI-SPEC.md A2 (#147, DESIGN_SYSTEM.md §4): every CornerRadius in the app
    must be one of the four legal values -- 6 (small chips/tags), 10
    (buttons/inputs/toggles/interactive rows), 14 (cards/dialogs/surfaces),
    or "fully round" -- and every one of them must be a StaticResource
    reference to Theme.xaml's four named resources (RadiusChip/RadiusControl/
    RadiusCard), not a bare number repeated at each call site. Fully round
    elements use inf:Pill.IsRound instead of a radius (TestPillsAreComputed).

    Proven to fail first: the FIXTURE strings below are lifted verbatim from
    the pre-A2 XAML (CornerRadius="11" on NavButton, CornerRadius="7" on the
    FirstRun app-icon badge, <Setter Property="CornerRadius" Value="12"/> on
    RowCard) -- none of them are legal literals and none reference a
    resource, so test_fixture_of_known_pre_fix_values_is_rejected below
    fails against them, and passes only once every real call site is
    converted (test_every_cornerradius_is_a_named_resource).
    """

    ROOT = Path(DESKTOP_DIR).parent
    FILES = (
        [Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"]
        + sorted((Path(DESKTOP_DIR) / "Views").glob("*.xaml"))
        + [Path(DESKTOP_DIR) / "MainWindow.xaml"]
    )

    LEGAL_RESOURCE_KEYS = {"RadiusChip", "RadiusControl", "RadiusCard"}
    LEGAL_VALUES = {"RadiusChip": 6, "RadiusControl": 10, "RadiusCard": 14}

    # Matches both CornerRadius="X" (inline) and
    # <Setter Property="CornerRadius" Value="X"/> (style setters).
    INLINE = re.compile(r'CornerRadius="([^"]*)"')
    SETTER = re.compile(r'Property="CornerRadius"\s+Value="([^"]*)"')
    RESOURCE_REF = re.compile(r'^\{StaticResource (\w+)\}$')

    # Verbatim pre-A2 fragments (Theme.xaml/MainWindow.xaml as they existed
    # before this change): a bare literal on a Border, and a bare literal on
    # a style Setter. Neither is a StaticResource reference.
    PRE_FIX_FIXTURE = '\n'.join([
        '<Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="11"',
        '<Border CornerRadius="7" Background="{StaticResource PrimarySoft}"',
        '<Setter Property="CornerRadius" Value="12"/>',
    ])

    def _offenders(self, text: str) -> list[str]:
        bad = []
        for m in self.INLINE.finditer(text):
            bad.append(m.group(1))
        for m in self.SETTER.finditer(text):
            bad.append(m.group(1))
        offenders = []
        for val in bad:
            rm = self.RESOURCE_REF.match(val)
            if not rm or rm.group(1) not in self.LEGAL_RESOURCE_KEYS:
                offenders.append(val)
        return offenders

    def test_fixture_of_known_pre_fix_values_is_rejected(self):
        """This test's own checker must actually catch the bug: run it
        against verbatim pre-A2 fragments and confirm every one is flagged."""
        offenders = self._offenders(self.PRE_FIX_FIXTURE)
        assert len(offenders) == 3, (
            f"expected the checker to flag all 3 pre-fix fragments, flagged {len(offenders)}: {offenders}"
        )

    def test_every_cornerradius_is_a_named_resource(self):
        offenders = []
        for path in self.FILES:
            text = path.read_text(encoding="utf-8")
            for m in self.INLINE.finditer(text):
                val = m.group(1)
                rm = self.RESOURCE_REF.match(val)
                if not rm or rm.group(1) not in self.LEGAL_RESOURCE_KEYS:
                    line_no = text.count("\n", 0, m.start()) + 1
                    offenders.append(f"{path.relative_to(self.ROOT)}:{line_no}: CornerRadius=\"{val}\"")
            for m in self.SETTER.finditer(text):
                val = m.group(1)
                rm = self.RESOURCE_REF.match(val)
                if not rm or rm.group(1) not in self.LEGAL_RESOURCE_KEYS:
                    line_no = text.count("\n", 0, m.start()) + 1
                    offenders.append(f"{path.relative_to(self.ROOT)}:{line_no}: Setter CornerRadius Value=\"{val}\"")
        assert not offenders, (
            "CornerRadius value(s) that aren't a {StaticResource RadiusChip|RadiusControl|RadiusCard} "
            "reference found -- every corner radius must draw from Theme.xaml's three named resources, "
            "or the element must use inf:Pill.IsRound "
            "(DESIGN_SYSTEM.md §4, UI-SPEC.md A2):\n" + "\n".join(offenders)
        )

    def test_named_resources_hold_the_legal_scale_values(self):
        """The three resources themselves must equal the doc's own numbers --
        a passing test above would be meaningless if RadiusCard were
        silently redefined to something off-scale."""
        theme_text = (Path(DESKTOP_DIR) / "Styles" / "Theme.xaml").read_text(encoding="utf-8")
        for key, expected in self.LEGAL_VALUES.items():
            m = re.search(rf'<CornerRadius x:Key="{key}">(\d+)</CornerRadius>', theme_text)
            assert m, f"expected a <CornerRadius x:Key=\"{key}\"> resource definition in Theme.xaml"
            assert int(m.group(1)) == expected, (
                f"{key} is defined as {m.group(1)}, expected {expected}"
            )

    def test_the_files_list_actually_covers_something(self):
        assert len(self.FILES) >= 5, "expected Theme.xaml, MainWindow.xaml and several Views/*.xaml"


class TestPillsAreComputed:
    """
    A2 first expressed "fully round" as CornerRadius="9999", on the belief
    that WPF clips corner geometry to half the smaller side. It doesn't: CSS
    clamps an oversized border-radius, but WPF scales the curves, so the
    renders showed the tier badge as an ellipse and the 5 px scrollbar thumb
    as a spike. Pills now set inf:Pill.IsRound, which keeps the radius at half
    the element's smaller side as it resizes (Infrastructure/Pill.cs).
    """

    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"
    PILL = Path(DESKTOP_DIR) / "Infrastructure" / "Pill.cs"
    FILES = (
        [Path(DESKTOP_DIR) / "Styles" / "Theme.xaml", Path(DESKTOP_DIR) / "MainWindow.xaml"]
        + sorted((Path(DESKTOP_DIR) / "Views").glob("*.xaml"))
    )
    # Anything at or beyond this is "make it round" by brute force, which WPF
    # renders as an ellipse on any element that isn't square.
    BRUTE_FORCE = 100

    def test_no_corner_radius_is_large_enough_to_draw_an_ellipse(self):
        offenders = []
        for path in self.FILES:
            text = path.read_text(encoding="utf-8")
            values = re.findall(r'CornerRadius="([\d.,\s]+)"', text)
            values += re.findall(r'<CornerRadius x:Key="\w+">([\d.,\s]+)</CornerRadius>', text)
            values += re.findall(r'Property="CornerRadius"\s+Value="([\d.,\s]+)"', text)
            for v in values:
                if any(float(part) >= self.BRUTE_FORCE for part in v.split(",") if part.strip()):
                    offenders.append(f"{path.name}: {v}")
        assert not offenders, (
            "a huge CornerRadius draws an ellipse in WPF, not a pill; use "
            "inf:Pill.IsRound=\"True\":\n  " + "\n  ".join(offenders))

    def test_the_round_elements_use_the_pill_behaviour(self):
        theme = self.THEME.read_text(encoding="utf-8")
        chip = re.search(r'<Style x:Key="Chip" TargetType="Border">.*?</Style>', theme, re.S)
        assert chip and 'Property="inf:Pill.IsRound" Value="True"' in chip.group(0), (
            "the Chip style (the tier badge) must be fully round via inf:Pill.IsRound")
        # The nav bar, toggle track, scrollbar thumb, and both progress bar
        # borders, plus the Chip setter above.
        assert theme.count('inf:Pill.IsRound="True"') >= 5, (
            "expected the nav bar, toggle track, scrollbar thumb and progress "
            "bar borders to set inf:Pill.IsRound")

    def test_the_radius_is_half_the_smaller_side(self):
        source = self.PILL.read_text(encoding="utf-8")
        assert "Math.Min(width, height)" in source and "smaller / 2" in source, (
            "Pill.RadiusFor must use half the SMALLER side; half the larger side "
            "is exactly the ellipse this replaced")
        assert "SizeChanged" in source, "the radius must follow the element as it resizes"


class TestBlockedAppsRowSwitchNotClipped:
    """
    PR #182 review (§4): the per-app enable/disable switch in the Blocked
    Apps list (Steam/Discord/Minecraft Launcher rows) was clipped by the
    card's right edge. The row's Grid has one flexible column (app name,
    MinWidth 120) and four Auto columns -- icon, "blocked N x" stat, Remove
    button, switch -- inside a ListBox with
    ScrollViewer.HorizontalScrollBarVisibility="Disabled", which clips
    overflow instead of scrolling it. This PR's own spacing bumps (icon
    margin 13->12, "blocked N" margin 14->16, Remove button padding
    14,0->16,0, switch margin 14,0,0,0->16,0,0,0) pushed the row's required
    width past the card's available width (roughly 480px once the 1180px
    window's 240px nav rail, 32px page margins, 300px picker column, 16px
    gap, 24px Card padding and 16px RowCard padding are all subtracted), so
    the switch -- the last Auto column -- lost its right edge.

    The review fix pulled the Remove button's own padding and the switch's
    own margin back down to 12 (still on the §4 4/8/12/16/24/32/48/64
    scale), reclaiming 12px. This test sums the four literal spacing values
    straight from the live XAML rather than reimplementing WPF's
    text-measurement and layout engine -- those four numbers are the whole
    cause the review named, and BUDGET is the same arithmetic used to find
    and fix it.
    """

    VIEW = Path(DESKTOP_DIR) / "Views" / "BlockedAppsView.xaml"

    # 76 (pre-fix: 12+16+32+16) overflowed the card; 64 (post-fix:
    # 12+16+24+12) fits with margin to spare. Drawn at 70 so a future bump
    # of any one value by a single further 4px §4 step trips it again.
    BUDGET = 70

    ICON_MARGIN = re.compile(
        r'Grid\.Column="0" Width="34" Height="34".*?Margin="0,0,(\d+),0">', re.DOTALL
    )
    STAT_MARGIN = re.compile(
        r'Grid\.Column="2" VerticalAlignment="Center" Margin="0,0,(\d+),0"\s*\n\s*'
        r'Style="\{StaticResource Caption\}">\s*\n\s*<Run Text="blocked"'
    )
    BUTTON_PADDING = re.compile(
        r'Style="\{StaticResource BtnDanger\}" Content="Remove"\s*\n\s*Padding="(\d+),0"'
    )
    SWITCH_MARGIN = re.compile(
        r'Style="\{StaticResource Switch\}"\s*\n\s*VerticalAlignment="Center" Margin="(\d+),0,0,0"'
    )

    # Verbatim pre-fix fragment (this PR's own shipped numbers, before the
    # review caught the clip): proves the checker below actually rejects
    # the failing set rather than passing by construction.
    PRE_FIX_FIXTURE = (
        '<Border Grid.Column="0" Width="34" Height="34" CornerRadius="{StaticResource RadiusControl}"\n'
        '        Background="{StaticResource PrimarySoft}" BorderBrush="{StaticResource Primary}" BorderThickness="1"\n'
        '        Margin="0,0,12,0">\n'
        '<TextBlock Grid.Column="2" VerticalAlignment="Center" Margin="0,0,16,0"\n'
        '           Style="{StaticResource Caption}">\n'
        '    <Run Text="blocked"/>\n'
        '<Button Grid.Column="3" Style="{StaticResource BtnDanger}" Content="Remove"\n'
        '        Padding="16,0" VerticalAlignment="Center"\n'
        '<CheckBox Grid.Column="4" Style="{StaticResource Switch}"\n'
        '          VerticalAlignment="Center" Margin="16,0,0,0"\n'
    )

    def _total(self, text: str) -> int:
        icon = self.ICON_MARGIN.search(text)
        stat = self.STAT_MARGIN.search(text)
        button = self.BUTTON_PADDING.search(text)
        switch = self.SWITCH_MARGIN.search(text)
        assert icon and stat and button and switch, (
            "one of the Blocked Apps row's spacing patterns wasn't found -- "
            "has the row's XAML structure changed? update this test's regexes to match."
        )
        return (
            int(icon.group(1))
            + int(stat.group(1))
            + int(button.group(1)) * 2
            + int(switch.group(1))
        )

    def test_fixture_of_known_pre_fix_values_is_rejected(self):
        """Proves the checker catches the bug: the pre-fix numbers
        (12+16+32+16=76) must exceed BUDGET."""
        total = self._total(self.PRE_FIX_FIXTURE)
        assert total > self.BUDGET, (
            f"expected the pre-fix fixture ({total}) to exceed BUDGET ({self.BUDGET})"
        )

    def test_blocked_apps_row_spacing_fits_the_card(self):
        text = self.VIEW.read_text(encoding="utf-8")
        total = self._total(text)
        assert total <= self.BUDGET, (
            f"Blocked Apps row spacing (icon margin + stat margin + 2x Remove "
            f"button padding + switch margin = {total}) exceeds the "
            f"{self.BUDGET}px budget that keeps the switch from being "
            "clipped by the card's right edge (PR #182 review) -- pull one "
            "of these back to the next lower §4 scale step."
        )


class TestFontAndSiteIconNoticesShip:
    """
    Inter (OFL) is embedded in the app and Lucide (ISC) is drawn inline on the
    site. Both licences ask for their notice to travel with the copy. A file in
    the repo that never reaches the output, or a page with the icons and no
    notice beside it, distributes the work without the licence.
    """

    def test_the_font_licence_is_copied_next_to_the_app(self):
        csproj = (Path(DESKTOP_DIR) / "FlowShield.csproj").read_text(encoding="utf-8")
        entry = csproj.split('Include="Assets\\Fonts\\OFL.txt"', 1)
        assert len(entry) == 2, "Inter's OFL.txt is no longer in the project"
        assert "CopyToOutputDirectory" in entry[1].split("/>", 1)[0], (
            "OFL.txt is in the project but never reaches the output folder"
        )
        notices = (Path(DESKTOP_DIR) / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
        assert "Inter" in notices and "Open Font License" in notices

    def test_every_page_with_lucide_icons_links_the_notice(self):
        site = Path(WEBSITE_DIR)
        assert (site / "icons-LICENSE.txt").is_file(), "the site serves Lucide icons with no notice"
        for page in sorted(site.glob("*.html")):
            html = page.read_text(encoding="utf-8")
            if 'stroke="currentColor"' in html:
                assert 'rel="license" href="icons-LICENSE.txt"' in html, (
                    f"{page.name} draws Lucide icons but does not link their licence"
                )


# ======================================== #189: the app adapts to its window

class TestAppAdaptsToItsWindow:
    """
    #189. Miles saw clipped nav icons, and two pages (Sleep Blocking,
    Settings) that sat in a narrow centred column instead of using the window.
    A render-kit sweep of main at six sizes, 1920x1040 down to the 800x540
    minimum, found the rest: fixed side columns on Today and Blocked Apps,
    breakpoints read from the window instead of the view, a picker that cut
    app names short at every size, and Blocked Apps clipping its Remove
    buttons below about 780px. DESIGN_SYSTEM.md §4 now records the rules;
    these tests hold them.
    """

    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"
    VIEWS = Path(DESKTOP_DIR) / "Views"

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8-sig")

    def _style(self, key: str, path: Path | None = None) -> str:
        xaml = self._read(path or self.THEME)
        start = xaml.index(f'x:Key="{key}"')
        return xaml[start:xaml.index("</Style>", start)]

    def test_nav_rows_leave_room_for_their_icons(self):
        """BtnBase fixes Height=40; NavButton added Padding 16,12, leaving a
        16px box for a 20px icon, which clipped it at the top and bottom."""
        nav = self._style("NavButton")
        height = float(re.search(r'Property="Height" Value="([\d.]+)"', nav).group(1))
        padding = re.search(r'Property="Padding" Value="([\d.,]+)"', nav).group(1).split(",")
        vertical = float(padding[1]) if len(padding) >= 2 else float(padding[0])
        icons = Path(DESKTOP_DIR) / "Styles" / "Icons.xaml"
        icon = float(re.search(r'Property="Height" Value="([\d.]+)"', self._style("Icon", icons)).group(1))
        assert height - 2 * vertical >= icon, (
            f"a nav row {height}px tall with {vertical}px vertical padding has "
            f"{height - 2 * vertical}px for a {icon}px icon")

    def test_settings_like_pages_fill_the_window(self):
        for view in ("SleepBlockingView.xaml", "SettingsView.xaml"):
            xaml = self._read(self.VIEWS / view)
            assert "<inf:AdaptiveColumns" in xaml, f"{view} should flow its cards into columns"
            for cap in ('MaxWidth="700"', 'MaxWidth="720"'):
                assert cap not in xaml, f"{view} is back in a fixed {cap} column"

    def test_side_panes_are_proportional_not_fixed(self):
        today = self._read(self.VIEWS / "TodayView.xaml")
        assert re.search(r'x:Name="StatsColumn" Width="[\d.]+\*" MinWidth="\d+" MaxWidth="\d+"', today)
        blocked = self._read(self.VIEWS / "BlockedAppsView.xaml")
        assert re.search(r'x:Name="PickerColumn" Width="[\d.]+\*" MinWidth="\d+" MaxWidth="\d+"', blocked)
        for code in ("TodayView.xaml.cs", "BlockedAppsView.xaml.cs"):
            source = (self.VIEWS / code).read_text(encoding="utf-8")
            assert "new GridLength(320)" not in source and "new GridLength(300)" not in source, (
                f"{code} restores a fixed side column")

    def test_breakpoints_read_the_space_the_view_has(self):
        """Keyed on the window, a view couldn't respond to its own width."""
        window_xaml = self._read(Path(DESKTOP_DIR) / "MainWindow.xaml")
        assert '<Grid x:Name="RootGrid" SizeChanged="OnSizeChanged">' in window_xaml
        assert 'SizeChanged="OnSizeChanged"\n' not in window_xaml.split("<Grid", 1)[0], (
            "the rail breakpoint belongs on the root grid, not the window")
        for code in ("TodayView.xaml.cs", "BlockedAppsView.xaml.cs"):
            source = (self.VIEWS / code).read_text(encoding="utf-8")
            assert "e.NewSize.Width" in source, f"{code} should read its own new width"
            assert "Window.GetWindow" not in source, f"{code} still reads the window's width"

    def test_blocked_apps_stacks_and_scrolls_when_narrow(self):
        """Side by side below ~780px, the list clipped its Remove buttons; split
        into fixed halves, a short window showed no rows at all."""
        blocked = self._read(self.VIEWS / "BlockedAppsView.xaml")
        assert '<ScrollViewer x:Name="PageScroll"' in blocked
        source = (self.VIEWS / "BlockedAppsView.xaml.cs").read_text(encoding="utf-8")
        assert "StackPickerBelow" in source
        assert "ScrollBarVisibility.Auto" in source and "ScrollBarVisibility.Disabled" in source

    def test_the_adaptive_panel_counts_columns_by_width(self):
        """The panel's column count: as many as keep each at MinColumnWidth,
        between one and MaxColumns, and one for an unusable width."""
        source = (Path(DESKTOP_DIR) / "Infrastructure" / "AdaptiveColumns.cs").read_text(encoding="utf-8")
        assert "Math.Floor((width + spacing) / (minColumnWidth + spacing))" in source
        assert "Math.Clamp(fit, 1, Math.Max(1, maxColumns))" in source
        assert "double.IsInfinity(width)" in source, "an infinite width must fall back to one column"

    def test_today_stat_values_share_their_labels_line_height(self):
        """The numbers used the default style while their labels used Body, so
        they sat higher than the labels beside them."""
        today = self._read(self.VIEWS / "TodayView.xaml")
        for binding in ("SessionsToday", "FocusMinutesToday", "BlocksToday"):
            tag = re.search(r'<TextBlock Text="\{Binding ' + binding + r'\}"[^>]*>', today, re.S).group(0)
            assert 'Style="{StaticResource Body}"' in tag, f"{binding} should use the Body style"


# ===================================== bug hunt, 22 September 2026 (#194-#199)

DESKTOP = Path(DESKTOP_DIR)


class TestStreakCountsADayItAlreadySettled:
    """
    #194. DailyGoal.Settle could only add today to the streak inside its walk
    loop, which runs while StreakSettledDayLocal < today -- and then writes
    StreakSettledDayLocal = today whether or not the day counted. RefreshStats
    settles today from the TodayViewModel constructor, i.e. at launch, before
    the day's first sprint exists, so every later call that day fell into the
    "date <= settled" branch whose only move was Max(CurrentStreak, 1). A user
    meeting their goal daily stayed on the streak they arrived with; a new user
    stuck at "1 day" forever.

    The fix routes all three paths through CountDayIfNewlyCounted, which uses
    the GoalMetDayLocal marker that already existed to make it once-per-day.
    """

    MODEL = DESKTOP / "Models" / "DailyGoal.cs"

    # The shipped same-day branch, verbatim: proves the checker below rejects it
    # rather than passing by construction.
    PRE_FIX_FIXTURE = (
        "        if (date <= settled)\n"
        "        {\n"
        "            if (date == settled && Judge(s, date) == DayVerdict.Counted)\n"
        "                s.CurrentStreak = Math.Max(s.CurrentStreak, 1);\n"
        "            return s.CurrentStreak != streakBefore;\n"
        "        }\n"
    )

    def _same_day_branch(self, source: str) -> str:
        match = re.search(r"if \(date <= settled\)\s*\{(.*?)\n        \}", source, re.S)
        assert match, "Settle's clock-moved-backwards branch was not found; update this regex"
        return match.group(1)

    def test_the_fixture_of_the_shipped_branch_is_rejected(self):
        branch = self._same_day_branch(self.PRE_FIX_FIXTURE)
        assert "CountDayIfNewlyCounted" not in branch
        assert "Math.Max(s.CurrentStreak, 1)" in branch, (
            "the pre-fix branch clamps to 1 instead of counting the day"
        )

    def test_a_day_already_settled_goes_through_the_once_per_day_marker(self):
        source = self.MODEL.read_text(encoding="utf-8")
        branch = self._same_day_branch(source)
        assert "CountDayIfNewlyCounted" in branch, (
            "meeting the goal on a day Settle has already visited must still count it"
        )
        assert "Math.Max(s.CurrentStreak, 1)" not in source, (
            "clamping to 1 is what pinned every existing streak in place"
        )

    def test_the_marker_is_the_one_that_already_existed(self):
        source = self.MODEL.read_text(encoding="utf-8")
        counter = source.split("private static bool CountDayIfNewlyCounted(", 1)
        assert len(counter) == 2, "DailyGoal must expose the once-per-day counter"
        body = counter[1].split("\n    }", 1)[0]
        assert "s.GoalMetDayLocal?.Date == date" in body, (
            "GoalMetDayLocal is the field that makes this once a day, not once a sprint"
        )
        assert "s.CurrentStreak++" in body

    def test_every_path_that_can_count_today_uses_it(self):
        source = self.MODEL.read_text(encoding="utf-8")
        # First run, the already-settled branch, and the walk loop's today.
        assert source.count("CountDayIfNewlyCounted(s,") >= 3, (
            "first run, a re-settled today and the walk loop must all count today "
            "the same way, or one of them goes back to being unable to"
        )

    def test_note_progress_reads_the_marker_rather_than_setting_it_again(self):
        source = self.MODEL.read_text(encoding="utf-8")
        note = source.split("public static bool NoteProgress(", 1)[1].split("\n    }", 1)[0]
        assert "metBefore" in note and "Settle(s, date)" in note, (
            "NoteProgress must read GoalMetDayLocal either side of Settle"
        )
        assert "s.GoalMetDayLocal = date" not in note, (
            "two places setting the marker is how the toast and the streak drift apart"
        )


class TestTheGoalSeesTheSprintThatJustFinished:
    """
    #199. EndSprint called ApplyMomentum -- and through it
    DailyGoal.NoteProgress, which counts S.Sessions -- before adding the
    finished sprint to S.Sessions. So the goal was always judged one sprint
    behind: with a two-sprint goal the bar on Today read "2 / 2" (RefreshStats
    runs after the add) while the "Daily goal met" toast waited for a third
    sprint that may never come. ResumeInterruptedSprint had the same order.
    """

    VM = DESKTOP / "ViewModels" / "TodayViewModel.cs"

    def _order(self, body: str) -> tuple[int, int]:
        add = body.find("Sessions.Add(")
        momentum = body.find("ApplyMomentum(")
        assert add >= 0 and momentum >= 0, (
            "expected both the Sessions.Add and the ApplyMomentum call; update this test"
        )
        return add, momentum

    def test_end_sprint_records_before_it_judges(self):
        source = self.VM.read_text(encoding="utf-8")
        body = source.split("private void EndSprint(bool completed, bool interrupted = false)", 1)[1].split("\n    }", 1)[0]
        add, momentum = self._order(body)
        assert add < momentum, (
            "S.Sessions.Add must come before ApplyMomentum, or the daily goal and "
            "the streak are judged without the sprint that just finished"
        )

    def test_a_sprint_that_finished_while_closed_is_recorded_before_it_is_judged(self):
        source = self.VM.read_text(encoding="utf-8")
        body = source.split("case SprintResume.RecordCompleted:", 1)[1].split("break;", 1)[0]
        add, momentum = self._order(body)
        assert add < momentum, (
            "the RecordCompleted branch must add the session before ApplyMomentum too"
        )

    def test_the_pre_fix_order_is_rejected(self):
        add, momentum = self._order(
            "        ApplyMomentum(completed, _current);\n"
            "        S.Sessions.Add(_current);\n"
        )
        assert add > momentum, "the shipped order judged the goal before recording the sprint"


class TestTheTrendLeavesAnInterruptedSprintAlone:
    """
    #195. MomentumTrend.After branched on Completed alone, so a sprint recorded
    as Interrupted -- FlowShield was not running for most of it, nothing was
    enforced -- was charged the ended-early decay on replay. ApplyMomentum is
    never called for one, so the drawn line sank below the MomentumText printed
    beside it, and TrendDescription (the only thing a screen reader gets)
    described a shape that contradicted the number it quoted.
    """

    MODEL = DESKTOP / "Models" / "MomentumTrend.cs"
    VM = DESKTOP / "ViewModels" / "TodayViewModel.cs"

    def _after(self, source: str) -> str:
        body = source.split("private static double After(double score, FocusSession session)", 1)
        assert len(body) == 2, "MomentumTrend.After was not found; update this test"
        return body[1].split(";", 1)[0]

    def test_the_replay_carries_the_score_through_an_interrupted_sprint(self):
        after = self._after(self.MODEL.read_text(encoding="utf-8"))
        assert "session.Interrupted" in after, (
            "the replay must skip an interrupted sprint; Completed alone cannot "
            "tell 'gave up' from 'the app was not running'"
        )

    def test_the_pre_fix_body_is_rejected(self):
        after = self._after(
            "    private static double After(double score, FocusSession session) =>\n"
            "        session.Completed\n"
            "            ? Math.Round(score + 10 * Math.Clamp(session.PlannedMinutes / 25.0, 0.5, 3.0), 1)\n"
            "            : EndSprintPolicy.MomentumAfterEndingEarly(score, session.Shield);\n"
        )
        assert "session.Interrupted" not in after

    def test_the_live_score_still_never_moves_for_an_interrupted_sprint(self):
        """The rule the replay is being matched against."""
        vm = self.VM.read_text(encoding="utf-8")
        resume = vm.split("case SprintResume.RecordCompleted:", 1)[1].split("break;", 1)[0]
        assert "if (completed) ApplyMomentum" in resume, (
            "momentum is applied only when the sprint counts as finished"
        )


class TestEnforcementBookkeepingIsForgottenWhenTheWindowCloses:
    """
    #196. _present and _closingAt were only cleared by BeginEnforcing and
    StopEnforcing, which a sprint calls. The sleep window has no such moment:
    Tick returns at the "nothing to enforce" guard, which sits above the
    per-tick cleanup, so a close deadline written at 05:59 survived to 22:00 the
    next night. The first sweep of the new window then found now >= deadline and
    went straight to KillAll -- no warning, no ten seconds to save -- and
    _present kept the sighting from counting as a distraction.
    """

    SERVICE = DESKTOP / "Services" / "AppBlockerService.cs"

    def _idle_guard(self, source: str) -> str:
        match = re.search(r"if \(!enforcing && !sleepActive\)(.*?)\n        \}", source, re.S)
        if match is None:
            # The shipped one-liner form.
            match = re.search(r"if \(!enforcing && !sleepActive\)([^\n]*)", source)
        assert match, "Tick's nothing-to-enforce guard was not found; update this regex"
        return match.group(1)

    def test_the_guard_clears_what_the_last_window_saw(self):
        guard = self._idle_guard(self.SERVICE.read_text(encoding="utf-8"))
        assert "_present.Clear()" in guard and "_closingAt.Clear()" in guard, (
            "a deadline left over from the last window kills the app on sight when "
            "the next one opens"
        )

    def test_the_pre_fix_guard_is_rejected(self):
        guard = self._idle_guard(
            "        var sleepActive = IsWithinSleepWindow(settings);\n"
            "        if (!enforcing && !sleepActive) return;\n"
        )
        assert "_closingAt.Clear()" not in guard

    def test_the_grace_period_is_still_what_it_promises(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        assert "process.CloseMainWindow()" in source, "warn first"
        assert "now < deadline) continue" in source, "then wait out the grace period"
        grace = (DESKTOP / "Models" / "GracefulClose.cs").read_text(encoding="utf-8")
        assert "TimeSpan.FromSeconds(10)" in grace


class TestEmptyProfileForgetsEnforcementBookkeeping:
    """
    #269. During a sprint, switching to a profile with no enabled apps made
    Tick return before it forgot the old warning deadline and presence.
    Switching back after the grace period then killed a blocked app on its
    first sweep without a fresh warning.
    """

    SERVICE = DESKTOP / "Services" / "AppBlockerService.cs"

    def _empty_targets_branch(self, source: str) -> str:
        tick = source.split("private void Tick()", 1)
        assert len(tick) == 2, "AppBlockerService.Tick was not found; update this extraction"
        head = re.search(r"if\s*\(\s*targets\.Count\s*==\s*0\s*\)\s*", tick[1])
        assert head, "Tick's empty-targets return was not found; update this extraction"
        rest = tick[1][head.end():]
        if not rest.startswith("{"):
            return rest.split(";", 1)[0] + ";"          # the old one-line early return
        # Brace-match the block: it holds a nested lock (_gate) { ... }.
        depth = 0
        for i, ch in enumerate(rest):
            depth += ch == "{"
            depth -= ch == "}"
            if depth == 0:
                return rest[1:i]
        raise AssertionError("unbalanced braces after the empty-targets check")

    def test_empty_targets_clear_both_collections_under_the_lock(self):
        branch = self._empty_targets_branch(self.SERVICE.read_text(encoding="utf-8"))
        lock = re.search(r"lock\s*\(\s*_gate\s*\)\s*\{(?P<body>[^{}]*)\}", branch, re.S)
        assert lock, (
            "when the active profile has no enabled apps, Tick must clear its pending"
            " enforcement state under _gate before returning"
        )
        locked = lock.group("body")
        assert re.search(r"_present\s*\.\s*Clear\s*\(\s*\)", locked), (
            "an empty profile must forget which blocked apps were present"
        )
        assert re.search(r"_closingAt\s*\.\s*Clear\s*\(\s*\)", locked), (
            "an empty profile must forget old close deadlines so returning to it"
            " cannot kill an app without a fresh warning"
        )
        assert re.search(r"return\s*;", branch[lock.end():]), (
            "Tick must return after clearing pending enforcement state for an empty profile"
        )


class TestTheSleepWindowNeverDropsBelowFirm:
    """
    #197. The sleep window forced Firm only when no sprint was running
    ("sleepActive && !enforcing"), so starting a Soft sprint at 23:00 switched
    the nightly shield off for its whole length: blocked apps were noted and
    left running, which is strictly less enforcement than having no sprint at
    all. The floor belongs to the window, not to the sprint.
    """

    SERVICE = DESKTOP / "Services" / "AppBlockerService.cs"

    FLOOR = re.compile(r"if \(sleepActive[^)]*\) shield = ShieldLevel\.Firm;")

    def test_the_floor_does_not_depend_on_whether_a_sprint_is_running(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        match = self.FLOOR.search(source)
        assert match, "the sleep window's Firm floor was not found; update this regex"
        assert "!enforcing" not in match.group(0), (
            "a Soft sprint must not be able to lower the nightly shield below Firm"
        )
        assert "shield < ShieldLevel.Firm" in match.group(0), (
            "raise a weaker shield to Firm and leave Firm and Sealed alone"
        )

    def test_the_pre_fix_line_is_rejected(self):
        match = self.FLOOR.search(
            "        if (sleepActive && !enforcing) shield = ShieldLevel.Firm;\n"
        )
        assert match and "!enforcing" in match.group(0)

    def test_soft_outside_the_window_still_only_nudges(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        assert "var terminate = shield >= ShieldLevel.Firm || hardKill;" in source, (
            "Soft must still be notice-only when nothing else raises the floor"
        )


class TestResumingDoesNotCreditTimeFlowShieldWasClosed:
    """
    #198. F3 records a sprint whose time ran out while FlowShield was closed as
    finished only if FlowShield was watching for at least half of it -- but
    Decide measured that as LastSeenUtc minus StartedUtc, and
    ResumeInterruptedSprint refreshes LastSeenUtc. Reopening the app for one
    second near the end of a 60-minute sprint therefore counted all 60 minutes
    as watched: the sprint was recorded Completed, took +24 momentum and a
    streak day, having enforced nothing. RunningSprint now carries the watched
    total itself, added to on each heartbeat and deliberately not across the gap
    a resume spans.
    """

    SETTINGS = DESKTOP / "Models" / "AppSettings.cs"
    VM = DESKTOP / "ViewModels" / "TodayViewModel.cs"

    def _decide(self, source: str) -> str:
        return source.split("public SprintResume Decide(", 1)[1].split("\n    }", 1)[0]

    def test_the_decision_reads_an_accumulated_total(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        decide = self._decide(source)
        # Since #203 the preference lives in WatchedSoFar, which every
        # judgement of watched time reads; Decide must go through it.
        so_far = source.split("public double WatchedSoFar", 1)[1].split(";", 1)[0]
        assert "WatchedSoFar" in decide and "WatchedMinutes ??" in so_far, (
            "Decide must prefer the accumulated watched time over the two-timestamp "
            "estimate a resume invalidates"
        )
        assert "CompletedIfWatchedFraction" in decide, "the half-watched bar itself is unchanged"

    def test_the_pre_fix_decision_is_rejected(self):
        decide = self._decide(
            "    public SprintResume Decide(DateTime nowUtc)\n"
            "    {\n"
            "        if (PlannedMinutes <= 0) return SprintResume.Discard;\n"
            "        if (nowUtc < EndsUtc) return SprintResume.Resume;\n"
            "        var watched = (Min(LastSeenUtc, EndsUtc) - StartedUtc).TotalMinutes;\n"
            "        return watched >= PlannedMinutes * CompletedIfWatchedFraction\n"
            "            ? SprintResume.RecordCompleted\n"
            "            : SprintResume.RecordInterrupted;\n"
            "    }\n"
        )
        assert "WatchedMinutes" not in decide

    def test_old_settings_files_still_load(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        assert "public double? WatchedMinutes { get; set; }" in source, (
            "nullable, so a settings file written before this field falls back to "
            "the old estimate instead of being judged as never watched"
        )

    def test_only_the_heartbeat_adds_to_it(self):
        vm = self.VM.read_text(encoding="utf-8")
        assert "NoteStillWatching(now, WatchedStretchCap)" in vm, (
            "the heartbeat is the one place that records another watched stretch"
        )
        resume = vm.split("case SprintResume.Resume:", 1)[1].split("break;", 1)[0]
        assert "saved.LastSeenUtc = now;" in resume
        assert "NoteStillWatching" not in resume, (
            "resuming must not credit the sprint with the time FlowShield was closed "
            "-- that is the whole bug"
        )

    def test_a_suspended_machine_cannot_inflate_it(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        body = source.split("public void NoteStillWatching(", 1)[1].split("\n    }", 1)[0]
        assert "Min(stretch, cap)" in body, (
            "a DispatcherTimer does not tick while the machine sleeps, so an "
            "uncapped gap would credit time nothing was enforced for"
        )
        vm = self.VM.read_text(encoding="utf-8")
        assert "WatchedStretchCap = HeartbeatInterval * 2" in vm


class TestTimeUpAfterSleepUsesWatchedTime:
    """A lid-closed gap must not turn an expired sprint into full credit."""

    VM = DESKTOP / "ViewModels" / "TodayViewModel.cs"
    SETTINGS = DESKTOP / "Models" / "AppSettings.cs"

    def _block(self, source: str, marker: str) -> str:
        start = source.find(marker)
        assert start >= 0, f"could not find C# block starting at {marker!r}"
        opening = source.find("{", start)
        assert opening >= 0, f"could not find the opening brace for {marker!r}"
        depth = 0
        for index in range(opening, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[opening + 1:index]
        assert False, f"could not find the closing brace for {marker!r}"

    def test_time_up_notes_the_final_stretch_and_uses_the_active_sprint_decision(self):
        source = self.VM.read_text(encoding="utf-8")
        tick = self._block(source, "private void OnTick()")
        time_up = self._block(tick, "if (remaining <= TimeSpan.Zero)")
        note = time_up.find("NoteStillWatching(")
        decide = time_up.find(".Decide(now)")
        end = time_up.find("EndSprint(")
        assert note >= 0 and decide >= 0 and end >= 0 and note < decide < end, (
            "when time is up, OnTick must first cap and record the final watched "
            "stretch, then consult ActiveSprint.Decide(now), before ending the "
            "sprint; a sleeping PC or clock jump must not count the gap"
        )
        assert "WatchedStretchCap" in time_up[note:decide], (
            "the final stretch after the lid-closed gap must use the same watched-time cap"
        )
        assert "RecordInterrupted" in time_up and "interrupted: true" in time_up, (
            "a time-up decision below the watched fraction must end as interrupted"
        )
        assert "EndSprint(completed: true)" in time_up, (
            "a time-up decision at or above the watched fraction must still complete normally"
        )

    def test_interrupted_end_records_interruption_without_credit_or_break(self):
        source = self.VM.read_text(encoding="utf-8")
        signature = "private void EndSprint("
        assert signature in source, "EndSprint was not found"
        end = self._block(source, signature)
        header = source[source.find(signature):source.find("{", source.find(signature))]
        assert "interrupted" in header, (
            "EndSprint must accept an interrupted flag so time-up under-watching "
            "can be recorded separately from a user ending early"
        )
        assert "_current.Interrupted = interrupted" in end, (
            "the session saved after the lid-closed case must carry Interrupted = true"
        )
        assert "ApplyMomentum" in end and re.search(
            r"if\s*\(\s*!interrupted\s*\)[^{;]*ApplyMomentum\s*\(", end
        ), "an under-watched sprint must skip momentum gain and ended-early decay"
        assert re.search(r"if\s*\(\s*!interrupted\s*\)[^{;]*OfferBreakIfEarned\s*\(", end), (
            "an interrupted sprint after sleep must not offer or start a break"
        )

    def test_running_sprint_decide_uses_watched_so_far_helper(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        decide = self._block(source, "public SprintResume Decide(")
        assert "WatchedSoFar" in decide and "WatchedMinutes ??" not in decide, (
            "RunningSprint.Decide must use the shared clamped WatchedSoFar helper"
        )

    def test_resume_seeds_legacy_watched_minutes_before_advancing_last_seen(self):
        source = self.VM.read_text(encoding="utf-8")
        resume = self._block(source, "public void ResumeInterruptedSprint(")
        branch = resume.split("case SprintResume.Resume:", 1)[1].split(
            "case SprintResume.RecordCompleted:", 1
        )[0]
        advance = branch.find("saved.LastSeenUtc = now")
        seed_region = branch[:advance] if advance >= 0 else ""
        assert advance >= 0 and "WatchedMinutes" in seed_region and "WatchedSoFar" in seed_region, (
            "the Resume branch must seed missing WatchedMinutes from WatchedSoFar "
            "before LastSeenUtc advances, preserving 1.0.8 legacy time"
        )

    def _helper_ends_an_interruption_at_watched_time(self):
        """Since #300 both ends are worked out by RunningSprint.RecordedEnd."""
        helper = self._block(self.SETTINGS.read_text(encoding="utf-8"),
                             "public static DateTime RecordedEnd(")
        assert re.search(
            r"if\s*\(\s*interrupted\s*\)\s*return\s+startedUtc\s*\+\s*"
            r"TimeSpan\.FromMinutes\s*\(\s*watchedMinutes\s*\)",
            helper,
        ), "an interrupted sprint must end at its start plus the minutes watched"

    def test_startup_interruption_ends_at_watched_time(self):
        source = self.VM.read_text(encoding="utf-8")
        resume = self._block(source, "public void ResumeInterruptedSprint(")
        branch = resume.split("case SprintResume.RecordCompleted:", 1)[1]
        assert re.search(
            r"EndedUtc\s*=\s*RunningSprint\.RecordedEnd\(\s*saved\.StartedUtc\s*,\s*saved\.EndsUtc\s*,\s*"
            r"saved\.WatchedSoFar\s*,\s*now\s*,\s*completed\s*,\s*interrupted:\s*!completed\s*\)",
            branch,
        ), (
            "startup recovery must use EndsUtc only for completed sprints and "
            "StartedUtc + WatchedSoFar for interrupted sprints"
        )
        self._helper_ends_an_interruption_at_watched_time()

    def test_interrupted_end_uses_clamped_time_and_notifies_cycle_clear(self):
        source = self.VM.read_text(encoding="utf-8")
        end = self._block(source, "private void EndSprint(")
        assert re.search(
            r"_current\.EndedUtc\s*=\s*RunningSprint\.RecordedEnd\(\s*_current\.StartedUtc\s*,\s*"
            r"_endsAtUtc\s*,\s*S\.ActiveSprint\?\.WatchedSoFar\s*\?\?\s*0\s*,[^;]*,\s*interrupted\s*\)",
            end,
        ), "EndSprint must timestamp an interruption from clamped ActiveSprint.WatchedSoFar"
        self._helper_ends_an_interruption_at_watched_time()
        cleared = end.find("_cycle = interrupted ? CycleState.Nothing")
        text_raise = end.find("Raise(nameof(CycleProgressText))", cleared)
        visible_raise = end.find("Raise(nameof(CycleProgressVisible))", cleared)
        assert cleared >= 0 and text_raise > cleared and visible_raise > cleared, (
            "clearing the cycle on an interrupted EndSprint must notify both cycle "
            "progress bindings because OfferBreakIfEarned is skipped"
        )


# ================================= History is wired up and stays read-only (F16)

class TestHistoryPage:
    """
    F16 adds a fifth page, and three things about it are easy to break without
    noticing by eye.

    The nav entry: a page with a view model and no way to reach it is invisible
    (the tab is one Button among five, and #191's compact rail hides its label
    at narrow widths, so the rail's code must know about the new label).

    The AutomationIds: an id on a Border, Grid or ItemsControl is never
    surfaced to UI Automation, so a test asking for it passes whether the
    content was drawn or not (#134) — which is how the whole page could quietly
    stop rendering with every tier 3 test still green.

    And what it reads: the page is a projection of the sprints already on disk.
    If it ever starts writing settings, or reads the licence, the device list or
    anything that leaves the machine, the local-first promise and the privacy
    policy both stop being true.
    """

    DESKTOP = Path(DESKTOP_DIR)
    XAML = DESKTOP / "Views" / "HistoryView.xaml"
    VM = DESKTOP / "ViewModels" / "HistoryViewModel.cs"
    MAIN_XAML = DESKTOP / "MainWindow.xaml"
    MAIN_VM = DESKTOP / "ViewModels" / "MainViewModel.cs"
    MAIN_CODE = DESKTOP / "MainWindow.xaml.cs"
    MODEL = DESKTOP / "Models" / "HistoryStats.cs"

    def _read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8-sig")

    # ------------------------------------------------------------ the nav entry

    def test_the_nav_rail_has_a_history_tab(self):
        xaml = self._read(self.MAIN_XAML)
        assert 'AutomationProperties.AutomationId="Tab_History"' in xaml
        assert 'CommandParameter="History"' in xaml
        assert 'AutomationProperties.Name="History"' in xaml, \
            "the compact rail shows the name as a tooltip, so it has to exist"
        assert "{StaticResource IconHistory}" in xaml, \
            "the tab needs a Lucide geometry, like the other four"

    def test_the_tab_follows_the_same_pattern_as_the_other_four(self):
        xaml = self._read(self.MAIN_XAML)
        tabs = xaml.split('<StackPanel x:Name="NavTabs"', 1)[1].split("<Grid/>", 1)[0]
        ids = re.findall(r'AutomationProperties.AutomationId="(Tab_\w+)"', tabs)
        assert ids == ["Tab_Today", "Tab_History", "Tab_BlockedApps",
                       "Tab_SleepBlocking", "Tab_Settings"], \
            f"the rail's tabs are {ids}"
        for tab in tabs.split("<Button")[1:]:
            assert 'Style="{StaticResource NavButton}"' in tab, \
                "every tab uses NavButton, which is the 44px row (#191)"
            assert 'Tag="{Binding Is' in tab, "the active state binds through Tag"

    def test_the_compact_rail_hides_the_history_label_too(self):
        """
        Every other label is collapsed by name below 1000px. A label left out
        of that list stays visible in a 72px rail and overflows it.
        """
        code = self.MAIN_CODE.read_text(encoding="utf-8")
        labels = set(re.findall(r'(Nav\w+Label)\.Visibility = narrow', code))
        xaml = self._read(self.MAIN_XAML)
        declared = set(re.findall(r'<TextBlock x:Name="(Nav\w+Label)"', xaml))
        assert declared == labels, \
            f"these labels are never collapsed in the compact rail: {sorted(declared - labels)}"

    def test_navigation_reaches_the_page_and_refreshes_it(self):
        vm = self.MAIN_VM.read_text(encoding="utf-8")
        assert "AppPage.History" in vm
        assert "public bool IsHistoryPage" in vm
        assert "Raise(nameof(IsHistoryPage));" in vm, \
            "without this the page never becomes visible"
        assert "case AppPage.History: History.Refresh(); break;" in vm, \
            "sprints happen on another page, so History must refresh on entry"

        window = self._read(self.MAIN_XAML)
        assert "<views:HistoryView DataContext=\"{Binding History}\"" in window
        assert "DataContext.IsHistoryPage" in window

    # --------------------------------------------------- ids on real controls

    def test_every_automation_id_sits_on_a_control(self):
        xaml = self._read(self.XAML)
        for tag in ("<Grid", "<StackPanel", "<Border", "<ItemsControl",
                    "<UniformGrid", "<ScrollViewer", "<inf:AdaptiveColumns"):
            for element in xaml.split(tag)[1:]:
                head = element.split(">", 1)[0]
                assert "AutomationProperties.AutomationId" not in head, \
                    f"an AutomationId is on a {tag[1:]}, where nothing can find it"

    def test_the_week_stat_values_are_not_hidden_behind_a_name_override(self):
        """
        A TextBlock has no ValuePattern, so UI Automation surfaces its content
        through the element's Name — which is exactly what
        AutomationProperties.Name overrides. Setting an explicit Name on
        these three (as History briefly did) makes automation, and a screen
        reader, read the eyebrow label instead of the number: "Sprints
        completed this week" instead of "12". Regression for #222.
        """
        xaml = self._read(self.XAML)
        for automation_id in ("WeekFocusHours", "WeekSprintsValue", "WeekDistractionsValue"):
            block = xaml.split(f'AutomationProperties.AutomationId="{automation_id}"', 1)[1][:400]
            assert "AutomationProperties.Name" not in block.split("/>", 1)[0], \
                f"{automation_id} has a Name override hiding its bound value from automation"

    def test_the_page_offers_the_handles_a_test_needs(self):
        xaml = self._read(self.XAML)
        for automation_id in (
            "WeekFocusHours", "WeekRangeText", "WeekSprintsValue",
            "WeekDistractionsValue", "MostBlockedApp", "MostBlockedNote",
            "FocusHeatmap", "HeatmapLegend", "HeatmapRange", "HeatmapPeak",
            "MilestonesPlaceholder", "HistoryExportButton",
            "HistoryRowHeading", "HistoryRowOutcome", "HistoryRowJournal",
            "HistoryEmptyText",
        ):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml, \
                f"{automation_id} is missing from History"

    def test_the_heatmap_cells_are_focusable_controls_that_say_their_value(self):
        """
        DESIGN_SYSTEM.md §7: a heatmap never relies on colour alone, and
        hovering or focusing a cell shows the value. A Border does neither — it
        takes no focus and UI Automation does not surface it.
        """
        theme = self._read(self.DESKTOP / "Styles" / "Theme.xaml")
        style = theme[theme.index('x:Key="HeatCellItem"'):]
        style = style[:style.index("</Style>")]
        assert 'TargetType="ListBoxItem"' in style, "a cell has to be a real control"
        assert 'Property="AutomationProperties.Name" Value="{Binding Name}"' in style
        assert 'Property="ToolTip" Value="{Binding Name}"' in style
        assert 'Property="IsKeyboardFocused" Value="True"' in style, \
            "a focused cell has to show that it is focused"

        vm = self.VM.read_text(encoding="utf-8")
        assert "focus minutes" in vm, "a cell's name states its own value"

    def test_the_heatmap_has_a_legend_and_five_steps_from_surface_2_to_primary(self):
        xaml = self._read(self.XAML)
        assert 'AutomationProperties.AutomationId="HeatmapLegendLow"' in xaml
        assert 'AutomationProperties.AutomationId="HeatmapLegendHigh"' in xaml

        theme = self._read(self.DESKTOP / "Styles" / "Theme.xaml")
        assert '<inf:HeatStepToBrushConverter x:Key="HeatStep" Steps="5"/>' in theme

        converter = (self.DESKTOP / "Infrastructure" / "Converters.cs").read_text(encoding="utf-8")
        body = converter.split("class HeatStepToBrushConverter", 1)[1]
        assert '"Surface2Color"' in body and '"PrimaryColor"' in body, \
            "the ramp is mixed from the generated tokens, not hand-picked colours"
        hard_coded = re.findall(r'#[0-9A-Fa-f]{6}', body)
        assert not hard_coded, f"a colour is hard-coded in the converter: {hard_coded}"

    # ------------------------------------------------- what the page reads

    def test_history_reads_the_sprints_and_never_writes(self):
        """
        Read-only by construction. A page that saved settings could lose a
        running sprint's record just by being looked at, and the weekly figures
        would stop being a projection of what is stored.
        """
        vm = self.VM.read_text(encoding="utf-8")
        for forbidden in ("SaveSettings", "SettingsService.Save", "S.Sessions.Add",
                          "S.Sessions.Remove", "S.Sessions.Clear", "HttpClient",
                          "File.", "Process.Start"):
            assert forbidden not in vm, f"History must only read; it calls {forbidden}"

    def test_the_figures_come_from_sessions_alone(self):
        """
        Everything counted on this page is derived from AppSettings.Sessions
        through HistoryStats. The one exception is named out loud: the
        most-blocked app is the per-entry count FlowShield already keeps on the
        blocklist, because a sprint records how many distractions it caught and
        never which app they were — and the card says so rather than implying
        the count is this week's.
        """
        model = self.MODEL.read_text(encoding="utf-8")
        week = model.split("public static Week ForWeek", 1)[1].split("\n    }", 1)[0]
        heatmap = model.split("public static IReadOnlyList<Cell> Heatmap", 1)[1] \
                       .split("\n    }", 1)[0]
        for name, block in (("ForWeek", week), ("Heatmap", heatmap)):
            assert "sessions" in block, f"{name} should read the sessions it is handed"
            for forbidden in ("BlockedApps", "MomentumScore", "CurrentStreak",
                              "LicenseKey", "DeviceCount", "BlocksToday"):
                assert forbidden not in block, \
                    f"{name} reads {forbidden}; the week's figures come from Sessions"

        vm = self.VM.read_text(encoding="utf-8")
        touched = set(re.findall(r'\bS\.(\w+)', vm))
        # Profiles joined the list with F9: the most-blocked count is summed
        # across every profile, so the card's answer does not change when the
        # active blocklist does.
        assert touched <= {"Sessions", "BlockedApps", "Profiles"}, \
            f"History reads more of the settings than it should: {sorted(touched)}"
        assert "MostBlockedNoteText" in vm, \
            "the most-blocked card must state that its count is not this week's"

    def test_the_page_stays_local(self):
        """Nothing new leaves the PC, which is why F16 needs no privacy change."""
        for path in (self.VM, self.MODEL):
            text = path.read_text(encoding="utf-8")
            for forbidden in ("http://", "https://", "Upload", "PostAsync", "WebClient"):
                assert forbidden not in text, f"{path.name} mentions {forbidden}"

        # The view's only URLs are the two XAML namespace declarations.
        urls = re.findall(r'https?://\S+', self._read(self.XAML))
        assert all("schemas.microsoft.com" in url for url in urls), \
            f"History links out to {urls}"

    # --------------------------------------------------------- design and voice

    def test_the_page_uses_the_type_roles_and_the_radius_resources(self):
        xaml = self._read(self.XAML)
        for style in ("Eyebrow", "Stat", "Caption", "Body"):
            assert f'Style="{{StaticResource {style}}}"' in xaml, f"§3's {style} role is unused"
        assert 'Style="{StaticResource Card}"' in xaml
        assert not re.search(r'CornerRadius="\d', xaml), \
            "§4: radii come from the named resources, never a literal"

        # The heatmap's own squares are shaped in Theme.xaml, so check there too.
        theme = self._read(self.DESKTOP / "Styles" / "Theme.xaml")
        for key in ("HeatCellItem", "HeatLegendItem"):
            style = theme[theme.index(f'x:Key="{key}"'):]
            style = style[:style.index("</Style>")]
            assert 'CornerRadius="{StaticResource RadiusChip}"' in style, \
                f"{key} should use §4's chip radius"
        assert 'Typography.NumeralAlignment="Tabular"' in xaml, "§3: stats use tabular figures"
        assert "<inf:AdaptiveColumns" in xaml, \
            "the week's cards flow into columns rather than a fixed row (#191)"

    def test_the_outcome_wording_is_the_one_the_export_already_uses(self):
        """
        §9: "ended early", never "failed" or "gave up" — and one spelling, so
        the page and the exported file cannot drift apart.
        """
        vm = self.VM.read_text(encoding="utf-8")
        assert "JournalExport.Outcome(session)" in vm
        assert "JournalExport.ShieldName(session.Shield)" in vm

        # Only the strings the customer reads: no comments (which quote §9's
        # banned words in order to forbid them) and no code around them.
        lines = [line for line in vm.splitlines()
                 if not line.lstrip().startswith(("//", "///", "*"))]
        copy = " ".join(re.findall(r'"([^"\n]{4,})"', "\n".join(lines))).lower()
        # An interpolated {session.PlannedMinutes} is code, not words on screen.
        copy = re.sub(r"\{[^}]*\}", " ", copy)
        for forbidden in ("failed", "gave up", "broke your streak", "session",
                          "pomodoro", "blacklist", "!"):
            assert forbidden not in copy, f"§9 forbids {forbidden!r} in product copy"
        assert "sprint" in copy, "§9: sprints, not sessions"

    def test_a_poor_week_is_never_drawn_in_red(self):
        """§7 and §9: never `danger` for a momentum or focus drop."""
        xaml = self._read(self.XAML)
        for token in ("Rose", "Red", "Danger"):
            assert f"StaticResource {token}" not in xaml, \
                f"History colours something with {token}"

    def test_the_shield_glyph_is_the_shared_resource(self):
        xaml = self._read(self.XAML)
        assert "{StaticResource ShieldGlyph}" in xaml, \
            "§6: one glyph resource, not a per-page copy"

    def test_a_place_is_held_for_the_milestones(self):
        """F14's milestones (#133) are listed here; the slot exists already so
        adding them does not mean rearranging the page."""
        xaml = self._read(self.XAML)
        assert 'AutomationProperties.AutomationId="MilestonesPlaceholder"' in xaml
        assert "MILESTONES" in xaml

    def test_the_journal_export_stays_reachable_with_its_ids_intact(self):
        """
        F17's export card is still on Settings, with every AutomationId it
        shipped; History is a second way to it.
        """
        settings = self._read(self.DESKTOP / "Views" / "SettingsView.xaml")
        for automation_id in ("ExportFromDate", "ExportToDate", "ExportCsvRadio",
                              "ExportMarkdownRadio", "ExportJournalButton",
                              "ExportRangeText", "ExportStatusText"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in settings, \
                f"{automation_id} disappeared from the export card"

        xaml = self._read(self.XAML)
        button = xaml.split('AutomationProperties.AutomationId="HistoryExportButton"', 1)[0]
        button = button[button.rindex("<Button"):]
        assert 'Style="{StaticResource BtnGhost}"' in button, \
            "§7: the export is Secondary here, not the page's primary action"

        vm = self.VM.read_text(encoding="utf-8")
        assert "AppPage.Settings" in vm, "the button has to go somewhere"

    def test_the_sprint_list_reads_the_journal_back(self):
        """F17 promised the journal could be read again; F16 is where it is."""
        xaml = self._read(self.XAML)
        assert 'AutomationProperties.AutomationId="HistoryRowJournal"' in xaml
        assert 'AutomationProperties.AutomationId="HistoryRowIntention"' in xaml
        vm = self.VM.read_text(encoding="utf-8")
        assert "OrderByDescending(s => s.StartedUtc)" in vm, "newest first"


# ==================================== tray and keyboard reuse the F2 flow (F4)

class TestTrayAndKeyboardNeverBypassTheEndFlow:
    """
    F4 added a second and third way to end a sprint — the tray menu and the
    Space key — on top of the StopSprintButton. All three must resolve to the
    exact same RequestEnd() policy: a shortcut that ended a Firm or Sealed
    sprint immediately would silently undo F2's escape-hatch rules (#47).
    """

    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"
    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    MAIN_XAML = Path(DESKTOP_DIR) / "MainWindow.xaml"
    TODAY_XAML = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"

    def test_tray_end_sprint_and_space_drive_the_same_stopcommand_as_the_button(self):
        today_xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        assert 'Command="{Binding StopCommand}"' in today_xaml, \
            "StopSprintButton must still bind StopCommand — this test assumes that binding"

        window = self.WINDOW.read_text(encoding="utf-8")
        assert "vm.Today.StopCommand.Execute(null)" in window, \
            "the tray's End sprint must invoke StopCommand, the same RelayCommand as the button"

        today_vm = self.TODAY_VM.read_text(encoding="utf-8")
        # Space's command wraps TogglePrimary, which itself calls RequestEnd()
        # while running — not a separate, weaker end path.
        assert "ToggleOrEndCommand = new RelayCommand(TogglePrimary" in today_vm
        assert "StopCommand = new RelayCommand(() => RequestEnd()" in today_vm

    def test_no_new_entry_point_calls_endsprint_or_cancelsprint_directly(self):
        """
        RequestEnd() is the only door into EndSprint/CancelSprint — MainWindow
        and the Space/tray wiring must go through it, mirroring the existing
        rule for the old tray Quit and window-close paths (see
        TestNoOneClickEscape.test_tray_quit_and_window_close_use_the_end_flow).
        """
        window = self.WINDOW.read_text(encoding="utf-8")
        for method_name in ("BuildTrayMenu", "EndSprintFromTray", "WndProc"):
            body = window.split(f"private void {method_name}(", 1)
            if len(body) == 1:
                body = window.split(f"private IntPtr {method_name}(", 1)
            block = body[1].split("\n    }")[0]
            assert "EndSprint(" not in block, f"{method_name} must not end a sprint directly"
            assert "CancelSprint(" not in block, f"{method_name} must not cancel a sprint directly"

    def test_the_global_hotkey_only_ever_starts_not_ends(self):
        """The hotkey's one job is F4's 'start the last sprint' — it must never reach End."""
        window = self.WINDOW.read_text(encoding="utf-8")
        wnd_proc = window.split("private IntPtr WndProc(")[1].split("\n    }")[0]
        # Since #270 the hotkey goes through QuickStart(), which only starts.
        quick_start = window.split("private void QuickStart()")[1].split("\n    }")[0]
        assert "QuickStart()" in wnd_proc
        assert "StartCommand.Execute(null)" in quick_start
        for path in (wnd_proc, quick_start):
            assert "StopCommand" not in path
            assert "RequestEnd" not in path

    def test_page_ctrl_shortcuts_and_shield_shift_shortcuts_stay_disjoint(self):
        """
        Issue #37's settlement: Ctrl+1..5 is reserved for pages, Shift+1/2/3
        for shields. Sharing a digit (Ctrl+1 vs Shift+1) is fine — they are
        different combinations — but the same (modifier, key) pair must never
        be bound twice, and nothing may claim Ctrl+1..5 for a shield.
        """
        xaml = self.MAIN_XAML.read_text(encoding="utf-8")
        bindings = re.findall(r'<KeyBinding\s+(?:Modifiers="(\w+)"\s+)?Key="(\w+)"', xaml)
        combos = [(mods or "", key) for mods, key in bindings]
        assert len(combos) == len(set(combos)), f"duplicate KeyBinding combination(s) in {combos}"

        shield_lines = [line for line in xaml.splitlines() if "SelectShield" in line]
        assert shield_lines and all('Modifiers="Shift"' in line for line in shield_lines), \
            "every shield shortcut must use Shift, keeping Ctrl+1..5 free for page navigation"

    def test_ctrl_number_shortcuts_match_the_nav_rails_tab_order(self):
        """
        F16 added History as the rail's second tab (Today, History, Blocked
        Apps, Sleep Blocking, Settings), which used the fifth Ctrl+N slot F4
        left free. Ctrl+N must walk the tabs in the order they are drawn, or
        the shortcut a user memorises from looking at the rail stops matching
        what pressing it actually does.
        """
        xaml = self.MAIN_XAML.read_text(encoding="utf-8")
        tabs = xaml.split('<StackPanel x:Name="NavTabs"', 1)[1].split("<Grid/>", 1)[0]
        rail_order = re.findall(r'CommandParameter="(\w+)"', tabs)
        assert rail_order == ["Today", "History", "BlockedApps", "SleepBlocking", "Settings"], \
            f"the rail's own tab order is {rail_order}; update the expectation or the rail"

        ctrl_bindings = re.findall(
            r'<KeyBinding Modifiers="Ctrl" Key="D(\d)" Command="\{Binding NavigateCommand\}" '
            r'CommandParameter="(\w+)"/>', xaml)
        ctrl_order = [page for _, page in sorted(ctrl_bindings, key=lambda pair: int(pair[0]))]
        assert ctrl_order == rail_order, (
            f"Ctrl+1..{len(ctrl_order)} goes to {ctrl_order}, which does not match the rail's "
            f"own order {rail_order}"
        )


# ============================ Space cannot reach through the first-run wizard

class TestSpaceRefusedUnderFirstRun:
    """
    PR #214 review: the first-run wizard (F18) covers Today the same way the
    terms gate does, but nothing stopped Space — or a StartSprint() call from
    the tray or automation — from starting a sprint underneath it. The gate
    belongs in the view model, not only in the wizard's covering panel
    (CLAUDE.md's "a gate must refuse in the view model, not only by covering
    the screen").
    """

    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"

    def source(self) -> str:
        return self.TODAY_VM.read_text(encoding="utf-8")

    def test_the_space_shortcut_checks_first_run_is_not_showing(self):
        source = self.source()
        guard = source.split("private bool CanUseSpaceShortcut()")[1].split("\n\n")[0]
        assert "_main.FirstRun.IsVisible" in guard, \
            "Space must refuse while the first-run wizard is up, the same as the terms gate"

    def test_shift_shield_shortcuts_check_first_run_is_not_showing(self):
        source = self.source()
        guard = source.split("private bool CanChangeShield()")[1].split("\n\n")[0]
        assert "_main.FirstRun.IsVisible" in guard

    def test_startsprint_itself_refuses_under_the_wizard(self):
        """
        The view-model gate, not only the guard on the keyboard command:
        StartSprint() is also what the tray's "Start sprint (last settings)"
        and the global hotkey call directly, and neither goes through
        CanUseSpaceShortcut.
        """
        source = self.source()
        start = source.split("private void StartSprint()")[1].split("\n    private ")[0]
        assert "_main.FirstRun.IsVisible" in start, \
            "StartSprint must refuse while the first-run wizard hasn't finished, like the terms gate above it"
        # Must be checked, not just referenced in a comment.
        gate = re.search(r'if\s*\(\s*_main\.FirstRun\.IsVisible\s*\)', start)
        assert gate, "expected an explicit `if (_main.FirstRun.IsVisible)` guard in StartSprint"


# ==================================== the global hotkey hook never stacks up

class TestGlobalHotkeyHookIsNeverStacked:
    """
    PR #214 review: SetUpGlobalHotkey() re-runs every time the Settings toggle
    changes, and used to call HwndSource.AddHook without ever removing the
    previous one — so toggling the setting off and on stacked a WndProc hook
    per toggle, each one calling StartCommand again on the same key press.
    """

    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"

    def source(self) -> str:
        return self.WINDOW.read_text(encoding="utf-8")

    def test_a_single_hook_field_is_tracked(self):
        source = self.source()
        assert re.search(r'private\s+HwndSource\?\s+_hotkeySource;', source), \
            "expected a tracked HwndSource field so the hook can be removed later"

    def test_setup_removes_the_previous_hook_before_adding_a_new_one(self):
        source = self.source()
        setup = source.split("private void SetUpGlobalHotkey()")[1].split("\n    private ")[0]
        remove_index = setup.find("_hotkeySource.RemoveHook(WndProc)")
        add_index = setup.find(".AddHook(WndProc)")
        assert remove_index != -1, "SetUpGlobalHotkey must remove any hook it previously added"
        assert add_index != -1, "SetUpGlobalHotkey must (re)add the hook when the hotkey is enabled"
        assert remove_index < add_index, \
            "the old hook must be removed before a new one is added, or hooks stack on every toggle"
        # And the removal must not be conditional on _hotkeyRegistered alone —
        # it needs its own null check so a re-run after a failed RegisterHotKey
        # still tears down a hook left over from a previous success.
        assert "if (_hotkeySource is not null)" in setup

    def test_closing_removes_the_hook_alongside_unregistering(self):
        source = self.source()
        closing = source.split("protected override void OnClosing")[1]
        unregister_index = closing.find("UnregisterHotKey(")
        remove_hook_index = closing.find("_hotkeySource.RemoveHook(WndProc)")
        assert unregister_index != -1
        assert remove_hook_index != -1, "OnClosing must remove the WndProc hook, not just unregister the hotkey"


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


# ==================== the Soft notice stays a notice (F7 / roadmap 1.7, #143)

class TestSoftOverlayNeverCloses:
    """
    Soft's promise, on its own shield chip, is that it notes distractions and
    nudges. 1.7 gives that nudge a real screen — a topmost full-screen window
    over the blocked app — and the danger of a new surface with two buttons on
    it is that one of them quietly starts closing things.

    Everything here is read from the source, because the alternative is a UI
    test that can only prove the button exists, not what it does.
    """

    BLOCKER = Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs"
    POLICY = Path(DESKTOP_DIR) / "Models" / "SoftOverlayPolicy.cs"
    OVERLAY_XAML = Path(DESKTOP_DIR) / "Views" / "SoftOverlayWindow.xaml"
    OVERLAY_CS = Path(DESKTOP_DIR) / "Views" / "SoftOverlayWindow.xaml.cs"
    MAIN_VM = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    MAIN_WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"
    SETTINGS = Path(DESKTOP_DIR) / "Models" / "AppSettings.cs"
    SETTINGS_VIEW = Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml"

    def test_the_overlay_never_closes_or_kills_anything(self):
        for path in (self.OVERLAY_XAML, self.OVERLAY_CS, self.POLICY):
            source = path.read_text(encoding="utf-8")
            code = "\n".join(line for line in source.splitlines()
                             if not line.strip().startswith(("///", "//", "<!--", "*")))
            for forbidden in ("CloseMainWindow", ".Kill("):
                assert forbidden not in code, (
                    f"{path.name} can close the blocked app; Soft must not"
                )

    def test_the_soft_branch_of_the_sweep_still_closes_nothing(self):
        """The regression this guards: a foreground check that grew teeth."""
        source = self.BLOCKER.read_text(encoding="utf-8")
        soft = source.split("if (!terminate)", 1)[1].split("continue;", 1)[0]
        for forbidden in ("CloseMainWindow", "Kill(", "_closingAt["):
            assert forbidden not in soft, f"the Soft branch must not {forbidden}"

    def test_the_notice_is_only_looked_for_while_soft_is_the_shield(self):
        """
        Firm and Sealed close the blocked app. Putting a full-screen panel over
        a window that is about to disappear is noise, and it would also cover
        the seconds someone has to save.
        """
        source = self.BLOCKER.read_text(encoding="utf-8")
        assert "if (!terminate) ReportForeground(targets);" in source, (
            "the foreground check must sit behind the same !terminate gate that "
            "separates Soft from Firm, Sealed and hard kill"
        )

    def test_the_foreground_check_stays_timid(self):
        """
        CLAUDE.md: no hooks into other processes, no admin rights. Reading which
        window has focus and which process owns it is user-level and enough.
        """
        source = self.BLOCKER.read_text(encoding="utf-8")
        body = source.split("private void ReportForeground", 1)[1].split("\n    }", 1)[0]
        assert "GetForegroundWindow()" in body
        assert "GetWindowThreadProcessId(" in body
        for forbidden in ("SetWindowsHookEx", "WriteProcessMemory", "CreateRemoteThread",
                          "SetForegroundWindow", "OpenProcess"):
            assert forbidden not in source, f"the blocker must never call {forbidden}"

    def test_flowshields_own_windows_are_never_the_distraction(self):
        """
        Without this the notice takes focus, sees itself in the foreground, and
        closes itself — a box that flickers once and is gone.
        """
        source = self.BLOCKER.read_text(encoding="utf-8")
        body = source.split("private void ReportForeground", 1)[1].split("\n    }", 1)[0]
        assert "pid == (uint)Environment.ProcessId" in body

    def test_the_notice_never_opens_over_another_panel(self):
        source = self.MAIN_VM.read_text(encoding="utf-8")
        gate = source.split("public bool ModalPanelVisible =>", 1)[1].split(";", 1)[0]
        for panel in ("TermsGateVisible", "IsLocked", "FirstRun.IsVisible",
                      "ActivationPromptVisible", "Today.EndPanelVisible",
                      "Today.JournalPromptVisible", "Today.RunningAppsPanelVisible"):
            assert panel in gate, f"{panel} must keep the Soft notice away"

        handler = source.split("private void OnSoftForeground", 1)[1].split("\n    }", 1)[0]
        assert "if (ModalPanelVisible) return;" in handler
        assert "if (!Settings.ShowSoftOverlayEnabled) return;" in handler

    def test_back_to_work_brings_flowshield_forward_and_leaves_the_app_alone(self):
        source = self.MAIN_WINDOW.read_text(encoding="utf-8")
        block = source.split("overlay.BackToWork +=", 1)[1].split("};", 1)[0]
        assert "BringToFront()" in block
        assert "SoftOverlayBackToWork" in block
        for forbidden in ("Kill", "CloseMainWindow"):
            assert forbidden not in block

    def test_escape_is_back_to_work(self):
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        assert 'IsCancel="True"' in xaml
        code = self.OVERLAY_CS.read_text(encoding="utf-8")
        assert "Key.Escape" in code, (
            "this window is shown, not dialogued, so Escape is handled here too"
        )

    def test_the_window_is_topmost_full_screen_and_chromeless(self):
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        # DynamicResource since F21: the notice follows a theme change while
        # it is open, like every other window.
        for attribute in ('WindowStyle="None"', 'Topmost="True"',
                          'ShowInTaskbar="False"',
                          'Background="{DynamicResource Scrim}"'):
            assert attribute in xaml, f"the Soft notice is missing {attribute}"
        code = self.OVERLAY_CS.read_text(encoding="utf-8")
        assert "Screen.FromHandle(_anchor)" in code, (
            "it opens on the monitor the blocked app is on, not always the primary"
        )

    def test_it_covers_a_second_monitor_at_a_different_scale_factor(self):
        """
        WPF's Left/Top/Width/Height are device-independent units, scaled by the
        DPI of the monitor the window is on *at the time* -- before the move,
        whichever one Windows happened to open it on. On a 150%/100% pair that
        left the scrim over two thirds of the second screen with the desktop
        showing round the edges. Physical pixels need no conversion.
        """
        body = self.OVERLAY_CS.read_text(encoding="utf-8")
        body = body.split("private void PlaceOverTheDistraction", 1)[1].split("\n    }", 1)[0]
        assert "SetWindowPos(" in body, (
            "placement must go through SetWindowPos in the target monitor's own "
            "physical pixels"
        )
        assert "bounds.Width, bounds.Height" in body
        assert "TransformFromDevice" not in body, (
            "this is the bug: the current monitor's transform applied to another "
            "monitor's bounds"
        )
        for wpf_property in ("Left =", "Top =", "Width =", "Height ="):
            assert wpf_property not in body, (
                f"{wpf_property} is a device-independent unit and re-introduces the "
                f"mixed-DPI bug"
            )

    def test_it_fades_in_and_is_instant_under_reduced_motion(self):
        """DESIGN_SYSTEM.md §8: one shared duration provider, zero when animations are off."""
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        assert "{x:Static inf:Motion.Selection}" in xaml
        assert "EasingMode=\"EaseOut\"" in xaml
        assert "ScaleTransform" not in xaml and "RotateTransform" not in xaml, (
            "nothing bounces, spins or shakes"
        )

    def test_nothing_on_it_is_alarming(self):
        """§7: no red, no alarm icons. Strength never escalates through colour."""
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        for forbidden in ("Rose", "Amber", "Red", "IconWarning", "IconAlert"):
            assert forbidden not in xaml, f"the Soft notice must not use {forbidden}"
        assert "ShieldGlyphSoft" in xaml, "§7 asks for the shield glyph"

    def test_its_controls_carry_automation_ids_on_real_controls(self):
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        for automation_id in ("SoftOverlayText", "SoftOverlayTimeLeft",
                              "SoftOverlayBackToWorkButton", "SoftOverlayAllowButton",
                              "SoftOverlayCloseButton", "SoftOverlayIntention",
                              "SoftOverlayTryLine"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml

        # #134: an id on a layout panel is never surfaced, so it can never be found.
        for tag in re.finditer(r'<(\w+)\b((?:(?!/?>).)*?)/?>', xaml, re.S):
            element, attrs = tag.group(1), tag.group(2)
            if element in ("Grid", "StackPanel", "WrapPanel", "Border", "DockPanel", "Image") \
                    and 'AutomationId="' in attrs:
                raise AssertionError(
                    f"<{element}> has an AutomationId -- never surfaced to UI Automation")

    def test_the_setting_exists_and_is_on_by_default(self):
        settings = self.SETTINGS.read_text(encoding="utf-8")
        assert "public bool ShowSoftOverlayEnabled { get; set; } = true;" in settings, (
            "Soft's only visible intervention has to be on unless it is turned off"
        )
        view = self.SETTINGS_VIEW.read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="SoftOverlayToggle"' in view
        assert "Show a full-screen notice at Soft" in view

    def test_a_notice_cannot_outlive_the_sprint_that_raised_it(self):
        """
        The sighting is taken on the blocker's thread and handled on the
        dispatcher, so a sprint can be cancelled in between. Enforcement has
        stopped by then, so no later sighting arrives -- a notice shown here
        would stay on screen with nothing left to take it down, over whatever
        the user did next.
        """
        source = self.MAIN_VM.read_text(encoding="utf-8")
        handler = source.split("private void OnSoftForeground", 1)[1].split("\n    }", 1)[0]
        guard = " ".join(handler.split())
        assert "if (!IsSprintRunning || !Blocker.IsEnforcing)" in guard, (
            "the handler must re-check that the sprint is still running, on the "
            "dispatcher, before showing anything"
        )
        # And it has to come before the decision to show, not after it.
        assert handler.index("!Blocker.IsEnforcing") < handler.index("_softOverlay.ShouldShow")
        # The stale notice is closed, not merely skipped.
        stale = handler.split("!Blocker.IsEnforcing", 1)[1].split("return;", 1)[0]
        assert "SoftOverlayDismissRequested" in stale

    def test_an_allowance_does_not_outlive_the_sprint(self):
        source = self.MAIN_VM.read_text(encoding="utf-8")
        block = source.split("public void OnSprintStateChanged()", 1)[1].split("\n    }", 1)[0]
        assert "_softOverlay.Reset();" in block
        assert "SoftOverlayDismissRequested" in block, (
            "a notice must never outlive the shield that raised it"
        )

    def test_allowing_five_minutes_does_not_undo_the_distraction_count(self):
        """#140 counts one distraction per app per sighting; the notice changes nothing."""
        source = self.MAIN_VM.read_text(encoding="utf-8")
        block = source.split("public void SoftOverlayAllowFiveMinutes", 1)[1].split("\n    }", 1)[0]
        for forbidden in ("BlockCount", "RecordBlock", "BlocksToday"):
            assert forbidden not in block, (
                "the sighting was counted when it happened; the notice must not "
                "add to or subtract from it"
            )


class TestSoftCloseNeverKills:
    """
    1.0.10 gives Soft a Close button. Soft still never closes anything on its
    own, and a user-chosen close asks politely (CloseMainWindow) and never kills,
    so the app's own "save changes?" prompt still appears.
    """

    BLOCKER = Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs"

    def _ask_to_close(self) -> str:
        source = self.BLOCKER.read_text(encoding="utf-8")
        assert "public int AskToClose(string displayName, AppSettings settings)" in source
        return source.split("public int AskToClose(", 1)[1].split("\n    }", 1)[0]

    def test_it_only_asks(self):
        body = self._ask_to_close()
        assert "CloseMainWindow()" in body
        for forbidden in ("Kill(", "KillAll(", "_closingAt["):
            assert forbidden not in body, f"AskToClose must never {forbidden}"

    def test_it_never_touches_a_critical_process(self):
        assert "CriticalProcesses.Contains(" in self._ask_to_close()

    def test_it_is_only_reached_from_the_close_button(self):
        callers = [p for p in Path(DESKTOP_DIR).rglob("*.cs")
                   if "AskToClose(" in p.read_text(encoding="utf-8")]
        names = sorted(p.name for p in callers)
        assert names == ["AppBlockerService.cs", "MainViewModel.cs"], names

    def test_the_sweep_still_closes_nothing_at_soft(self):
        source = self.BLOCKER.read_text(encoding="utf-8")
        soft = source.split("if (!terminate)", 1)[1].split("continue;", 1)[0]
        assert "AskToClose" not in soft

    def test_zero_asked_is_explained_not_treated_as_a_failure(self):
        """
        AskToClose counts processes whose CloseMainWindow accepted the ask. An
        app hidden in the tray, or sitting behind its own save prompt, has no
        main window to close and gives 0, which is not a failure; the log says
        what it means, and a warning names the pid like the sibling lines do.
        """
        body = self._ask_to_close()
        assert "Safe(() => process.Id)" in body.split("catch (Exception ex)", 1)[1]
        caller = (Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs").read_text(encoding="utf-8") \
            .split("public void SoftOverlayCloseIt(string displayName)", 1)[1].split("\n    }", 1)[0]
        assert "asked == 0" in caller
        assert "nothing to ask" in caller


class TestSoftNoticeFriction:
    """
    1.0.10's notice (spec 4.1): Close first and primary, Back to work the
    default and keyboard action, and Allow only after a wait that grows with
    each try. The wait is enforced where the click lands, not only by how the
    button looks.
    """

    MAIN_VM = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    MAIN_WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"
    OVERLAY_XAML = Path(DESKTOP_DIR) / "Views" / "SoftOverlayWindow.xaml"
    OVERLAY_CS = Path(DESKTOP_DIR) / "Views" / "SoftOverlayWindow.xaml.cs"
    POLICY = Path(DESKTOP_DIR) / "Models" / "SoftOverlayPolicy.cs"

    def _button(self, automation_id: str) -> str:
        """The attributes of one button on the notice, up to its AutomationId."""
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        return xaml.split(f'AutomationProperties.AutomationId="{automation_id}"')[0].rsplit("<Button", 1)[1]

    def test_close_is_first_and_primary_but_never_the_keyboards_default(self):
        """
        The notice lands up to one blocker sweep (about 2 s) after the blocked
        app came to the front, while the user may still be typing in it. An
        Enter or Space meant for a game or a chat line must never become "the
        user chose to close it", so Close is reached by mouse or by Tab only.
        """
        row = self.OVERLAY_XAML.read_text(encoding="utf-8").split("<WrapPanel", 1)[1].split("</WrapPanel>", 1)[0]
        assert row.index('AutomationId="SoftOverlayCloseButton"') \
            < row.index('AutomationId="SoftOverlayBackToWorkButton"'), "Close stays first in the row"
        close = self._button("SoftOverlayCloseButton")
        assert "BtnPrimary" in close, "Close stays the primary action in colour"
        assert "IsDefault" not in close, "Enter must never be Close"
        assert "IsCancel" not in close

    def test_back_to_work_is_the_default_the_cancel_and_the_focused_button(self):
        """Enter, Space on the focused button and Escape all mean Back to work."""
        back = self._button("SoftOverlayBackToWorkButton")
        assert "BtnPrimary" not in back
        assert 'IsDefault="True"' in back, "Enter is Back to work"
        assert 'IsCancel="True"' in back, "Escape is still Back to work"
        opened = self.OVERLAY_CS.read_text(encoding="utf-8") \
            .split("protected override void OnSourceInitialized", 1)[1].split("\n    }", 1)[0]
        assert "BackToWorkButton.Focus();" in opened, "Back to work takes the initial focus"
        assert "CloseButton.Focus()" not in opened, "a focused Close would make Space close the app"

    def test_allow_waits_before_it_can_be_pressed(self):
        code = self.OVERLAY_CS.read_text(encoding="utf-8")
        assert "AllowButton.IsEnabled = false" in code
        assert "SoftOverlayCopy.AllowLabel(" in code
        assert "DispatcherTimer" in code
        # A gate refuses where the click lands, not only by how the button
        # looks (CLAUDE.md, "covered controls"), so the handler checks too.
        handler = code.split("private void OnAllowFiveMinutes", 1)[1].split("\n    }", 1)[0]
        assert handler.index("if (!AllowButton.IsEnabled) return;") < handler.index("Answer(AllowFiveMinutes)")

    def test_the_countdown_runs_on_the_monotonic_clock(self):
        """
        A deadline on DateTime.UtcNow moves with the wall clock: set back an
        hour during the wait and Allow stays disabled for an hour. The tick
        count only ever goes forward.
        """
        code = self.OVERLAY_CS.read_text(encoding="utf-8")
        countdown = code.split("public void Configure(", 1)[1].split("protected override void OnClosed", 1)[0]
        assert "Environment.TickCount64" in countdown
        for wall_clock in ("DateTime.UtcNow", "DateTime.Now"):
            assert wall_clock not in countdown, f"the Allow deadline must not follow {wall_clock}"

    def test_the_countdown_moves_nothing(self):
        """
        Sharing a WrapPanel with Close and Back to work, Allow jumped up a row
        (and the sentence re-wrapped) the moment its countdown ended and the
        label got shorter -- a button moving just as it becomes pressable.
        """
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        row = xaml.split("<WrapPanel", 1)[1].split("</WrapPanel>", 1)[0]
        assert 'AutomationId="SoftOverlayCloseButton"' in row
        assert 'AutomationId="SoftOverlayBackToWorkButton"' in row
        assert 'AutomationId="SoftOverlayAllowButton"' not in row, "Allow sits on a line of its own"

    def test_the_note_is_softs_promise_from_one_place(self):
        xaml = self.OVERLAY_XAML.read_text(encoding="utf-8")
        assert "{x:Static models:SoftOverlayCopy.CloseNote}" in xaml
        assert "Nothing has been closed" not in xaml, "the note from before Close existed"
        policy = self.POLICY.read_text(encoding="utf-8")
        assert 'CloseNote = "Nothing is closed unless you choose to.";' in policy

    def test_the_settings_switch_makes_the_same_promise(self):
        """
        The switch's caption said "Nothing is closed." -- untrue once the notice
        has Close. It now reads the notice's own note, so the two can't drift.
        """
        view = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(encoding="utf-8")
        caption = view.split('AutomationProperties.AutomationId="SoftOverlayToggle"', 1)[1] \
            .split("</CheckBox>", 1)[0]
        assert 'Text="{Binding SoftOverlayCaption}"' in caption
        assert "Nothing is closed" not in caption, "a typed copy of the note can drift from it"
        vm = (Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs").read_text(encoding="utf-8")
        assert re.search(r"public string SoftOverlayCaption\s*=>[^;]*SoftOverlayCopy\.CloseNote;", vm)

    def test_the_close_handler_asks_through_the_view_model_only(self):
        block = self.MAIN_WINDOW.read_text(encoding="utf-8").split("overlay.CloseIt +=", 1)[1].split("};", 1)[0]
        assert "SoftOverlayCloseIt" in block
        for forbidden in ("Kill", "CloseMainWindow", "Process"):
            assert forbidden not in block

    def test_the_view_model_counts_it_and_asks_the_blocker(self):
        source = self.MAIN_VM.read_text(encoding="utf-8")
        body = source.split("public void SoftOverlayCloseIt(string displayName)", 1)[1].split("\n    }", 1)[0]
        assert "_softOverlay.CloseIt(displayName, DateTime.UtcNow);" in body
        assert "Blocker.AskToClose(displayName, Settings)" in body

    def test_the_request_carries_intention_try_and_wait(self):
        handler = self.MAIN_VM.read_text(encoding="utf-8").split("private void OnSoftForeground", 1)[1].split("\n    }", 1)[0]
        for piece in ("SoftOverlayCopy.Intention(", "SoftOverlayCopy.TryLine(_softOverlay.Tries)",
                      "SoftOverlayPolicy.AllowWait(_softOverlay.Tries)",
                      "SoftOverlayCopy.Sentence(e.DisplayName, Today.EndsAtUtc.ToLocalTime(), _softOverlay.Tries)"):
            assert piece in handler, piece


# ============================ turned back, recorded and shown (1.0.10, spec 4.3)

class TestTurnedBackIsRecordedAndShown:
    """
    Close and Back to work on the Soft notice each count as one turned back
    (SoftOverlayPolicy.TurnedBack). The count is saved with the sprint, shown
    on its summary card and summed on History. It is a count and nothing else:
    which app was turned back from is never stored.
    """

    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    HISTORY_VM = Path(DESKTOP_DIR) / "ViewModels" / "HistoryViewModel.cs"
    MAIN_VM = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    SETTINGS = Path(DESKTOP_DIR) / "Models" / "AppSettings.cs"
    STATS = Path(DESKTOP_DIR) / "Models" / "HistoryStats.cs"
    TODAY_XAML = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"
    HISTORY_XAML = Path(DESKTOP_DIR) / "Views" / "HistoryView.xaml"

    RECORD = "_current.TurnedBack = _main.SoftTurnedBackThisSprint;"

    def _end_sprint(self) -> str:
        return self.TODAY_VM.read_text(encoding="utf-8") \
            .split("private void EndSprint(bool completed, bool interrupted = false)", 1)[1] \
            .split("\n    /// <summary>", 1)[0]

    def test_the_count_is_read_before_the_sprint_state_resets_it(self):
        """
        OnSprintStateChanged resets the Soft policy, count and all, so a read
        after it would save 0 for every sprint. Read before StopEnforcing too,
        with the other per-sprint counts, while the sprint is still the one
        that was running.
        """
        assert "_softOverlay.Reset();" in self.MAIN_VM.read_text(encoding="utf-8") \
            .split("public void OnSprintStateChanged()", 1)[1].split("\n    }", 1)[0], \
            "the reason for the order below has moved; re-check it"

        body = self._end_sprint()
        assert body.count(self.RECORD) == 1, "EndSprint must record TurnedBack exactly once"
        at = body.index(self.RECORD)
        assert at < body.index("_main.Blocker.StopEnforcing();")
        assert at < body.index("_main.OnSprintStateChanged();")
        assert at < body.index("S.Sessions.Add(_current);"), "read before the sprint is saved"

    def test_every_path_that_records_a_sprint_records_the_count(self):
        """
        Finished, ended early, and judged interrupted after a sleep (#203) all
        go through EndSprint; the count sits with the other per-sprint counts,
        before any branch, so none of them can skip it.
        """
        body = self._end_sprint()
        start = body.index("_current.Completed = completed;")
        between = body[start:body.index(self.RECORD)]
        assert "if (" not in between and "return" not in between, \
            "TurnedBack must be recorded unconditionally, on every path through EndSprint"

    def test_the_card_shows_the_line_only_above_zero(self):
        card = self.TODAY_VM.read_text(encoding="utf-8") \
            .split("private void UpdateSummaryCard(", 1)[1].split("\n    }", 1)[0]
        assert "SummaryTurnedBackText = HistoryStats.TurnedBackText(session.TurnedBack);" in card
        assert "SummaryTurnedBackVisible = session.TurnedBack > 0;" in card

    def test_history_sums_it_from_the_sessions_in_one_wording(self):
        stats = self.STATS.read_text(encoding="utf-8")
        week = stats.split("public static Week ForWeek", 1)[1].split("\n    }", 1)[0]
        assert "inWeek.Sum(s => s.TurnedBack)" in week
        vm = self.HISTORY_VM.read_text(encoding="utf-8")
        assert "WeekTurnedBackText = HistoryStats.TurnedBackText(week.TurnedBack);" in vm

    def test_only_a_count_is_stored_never_which_app(self):
        """
        The existing design choice in HistoryStats.MostBlocked: a sprint
        records how many, never which app. So TurnedBack is an int, and
        FocusSession gains no text or list that could hold an app's name.
        """
        model = self.SETTINGS.read_text(encoding="utf-8")
        session = model.split("public class FocusSession", 1)[1].split("\n}", 1)[0]
        assert "public int TurnedBack { get; set; }" in session
        stored = re.findall(r"public\s+([\w<>?,\[\] ]+?)\s+(\w+)\s*\{\s*get;", session)
        text_or_lists = {name for type_, name in stored
                         if re.search(r"string|List|\[\]|IEnumerable|Dictionary|Set<", type_)}
        assert text_or_lists == {"Intention", "Journal"}, (
            f"FocusSession stores text or a list beyond the intention and journal: {sorted(text_or_lists)}"
        )

    def test_both_lines_are_ids_on_real_text_blocks_and_hidden_at_zero(self):
        today = self.TODAY_XAML.read_text(encoding="utf-8")
        card = today[today.find("sprint summary"):]
        card = card[:card.find("journal prompt")]
        assert 'AutomationProperties.AutomationId="SummaryTurnedBackText"' in card, \
            "the summary card has no turned-back line"
        line = card.split('AutomationProperties.AutomationId="SummaryTurnedBackText"', 1)[0].rsplit("<", 1)[1]
        assert line.startswith("TextBlock"), "the id must sit on the TextBlock itself (#134)"
        assert 'Text="{Binding SummaryTurnedBackText}"' in line
        assert 'Visibility="{Binding SummaryTurnedBackVisible, Converter={StaticResource BoolVis}}"' in line
        assert card.index("SummaryDistractionsValue") < card.index("SummaryTurnedBackText"), \
            "the line sits under the distractions line"

        history = self.HISTORY_XAML.read_text(encoding="utf-8")
        distractions = history.split('Text="DISTRACTIONS CAUGHT"', 1)[1].split("</Border>", 1)[0]
        assert 'AutomationProperties.AutomationId="HistoryTurnedBackText"' in distractions, \
            "History's distractions card has no turned-back line"
        line = distractions.split('AutomationProperties.AutomationId="HistoryTurnedBackText"', 1)[0] \
            .rsplit("<", 1)[1]
        assert line.startswith("TextBlock"), "the id must sit on the TextBlock itself (#134)"
        assert 'Text="{Binding WeekTurnedBackText}"' in line
        assert 'Visibility="{Binding WeekTurnedBackText, Converter={StaticResource NonEmptyVis}}"' in line


# ================================== blocklist profiles must not break anything

class TestBlocklistProfilesKeepTheirPromises:
    """
    F9 turned the one blocklist into a list of named ones. Four things had to
    survive that: a settings file written before profiles existed, Sealed's
    lock (now over the switcher as well as the list), enforcement reading one
    profile and not the union of all of them, and every `AutomationId` the
    suite already drives.
    """

    APP_SETTINGS = (DESKTOP_DIR / "Models" / "AppSettings.cs").read_text(encoding="utf-8")
    BLOCKER = (DESKTOP_DIR / "Services" / "AppBlockerService.cs").read_text(encoding="utf-8")
    BLOCKED_VM = (DESKTOP_DIR / "ViewModels" / "BlockedAppsViewModel.cs").read_text(encoding="utf-8")
    TODAY_VM = (DESKTOP_DIR / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
    BLOCKED_XAML = (DESKTOP_DIR / "Views" / "BlockedAppsView.xaml").read_text(encoding="utf-8")
    TODAY_XAML = (DESKTOP_DIR / "Views" / "TodayView.xaml").read_text(encoding="utf-8")

    # ------------------------------------------ an old settings file still loads

    def test_the_old_settings_shape_still_has_a_home(self):
        """
        `BlockedApps` is the only blocklist a pre-F9 settings file has. It must
        still be a serialized property (not [JsonIgnore], not renamed), or every
        existing customer opens FlowShield to an empty blocklist.
        """
        blocked = self.APP_SETTINGS.split("public List<BlockedApp> BlockedApps")[1].split("\n    }")[0]
        assert "set => _legacyBlockedApps = value;" in blocked
        declaration = self.APP_SETTINGS.split("public List<BlockedApp> BlockedApps")[0]
        assert not declaration.rstrip().endswith("[JsonIgnore]"), \
            "BlockedApps must stay serializable, or an old settings file has nowhere to land"

    def test_the_old_name_still_answers_with_the_list_in_use(self):
        """
        Everything written before F9 — the first run, the privacy export, the
        UI tests reading settings["BlockedApps"] — asks for BlockedApps and must
        get the profile actually being enforced.
        """
        blocked = self.APP_SETTINGS.split("public List<BlockedApp> BlockedApps")[1].split("\n    }")[0]
        assert "get => ActiveProfile.Apps;" in blocked

    def test_a_settings_file_with_no_profiles_is_migrated_not_emptied(self):
        ensure = self.APP_SETTINGS.split("public bool EnsureProfiles()")[1].split("\n    }")[0]
        assert "_legacyBlockedApps ?? new List<BlockedApp>()" in ensure, \
            "the pre-F9 list becomes the Default profile; it is never dropped"

    # ------------------------------------------------ Sealed locks the switcher

    def test_sealed_refuses_a_profile_switch_in_the_view_model(self):
        """
        Not by disabling the chips alone: UI Automation can still invoke a
        disabled or covered control (#134), so the refusal has to be in the
        view model, the same as the list's own Sealed guard.
        """
        switch = self.BLOCKED_VM.split("private void SelectProfile(BlocklistProfile? profile)")[1].split(
            "\n    }")[0]
        assert "if (IsSealed)" in switch
        assert "SetActiveProfile" in switch
        assert switch.index("if (IsSealed)") < switch.index("SetActiveProfile"), \
            "the Sealed check must come before the switch, not after it"

    def test_the_switcher_is_also_disabled_while_sealed(self):
        assert "public bool CanSwitchProfile => !IsSealed;" in self.BLOCKED_VM
        assert 'IsEnabled="{Binding CanSwitchProfile}"' in self.BLOCKED_XAML
        assert 'IsEnabled="{Binding CanSwitchProfile}"' in self.TODAY_XAML

    def test_renaming_duplicating_and_deleting_are_sealed_too(self):
        """A Sealed sprint's blocklist cannot be renamed out from under it either."""
        guard = self.BLOCKED_VM.split("private bool GuardProfileEdit()")[1].split("\n    }")[0]
        assert "if (IsSealed)" in guard
        for command in ("RenameProfileCommand", "DuplicateProfileCommand", "DeleteProfileCommand"):
            line = self.BLOCKED_VM.split(f"{command} = new RelayCommand(")[1].split(";")[0]
            assert "CanEditProfiles" in line or "CanDeleteProfile" in line, \
                f"{command} must be refused while Sealed"
        assert "public bool CanEditProfiles => !IsSealed" in self.BLOCKED_VM
        assert "public bool CanDeleteProfile => CanEditProfiles" in self.BLOCKED_VM

    def test_a_resumed_sprint_comes_back_on_the_profile_it_started_with(self):
        """Otherwise a restart is a way round Sealed's lock (F3 + F9)."""
        assert "ActiveProfileId = S.ActiveProfile.Id," in self.TODAY_VM, \
            "the running sprint record must name the profile it is enforcing"
        resume = self.TODAY_VM.split("case SprintResume.Resume:")[1].split("break;")[0]
        assert "SetActiveProfile(saved.ActiveProfileId)" in resume

    # -------------------------------------- enforcement uses one profile only

    def test_the_blocker_enforces_the_active_profile_and_nothing_else(self):
        assert "_targets = settings.ActiveProfile.Apps.ToList();" in self.BLOCKER
        # The pre-sprint look reads one profile: the active one before Start
        # (F7), or a scheduled template's own list for its heads-up (F6),
        # which is the one that becomes active when the template starts.
        assert "RunningBlockedApps(settings.ActiveProfile);" in self.BLOCKER
        assert "foreach (var app in profile.Apps)" in self.BLOCKER
        assert "settings.Profiles" not in self.BLOCKER, \
            "the shield must never walk every profile — only the active one is enforced"

    def test_adds_and_removes_land_on_the_selected_profile_only(self):
        assert "ActiveApps.Add(app);" in self.BLOCKED_VM
        assert "ActiveApps.RemoveAll(a =>" in self.BLOCKED_VM
        assert "_main.Settings.BlockedApps.Add(" not in self.BLOCKED_VM

    def test_today_says_which_blocklist_the_next_sprint_uses(self):
        assert 'AutomationProperties.AutomationId="TodayProfileCaption"' in self.TODAY_XAML
        assert '$"Blocking: {ActiveProfile.Name}"' in self.BLOCKED_VM

    # ------------------------------------------------ the existing ids survive

    @pytest.mark.parametrize("auto_id", [
        "NewAppNameInput", "AddAppButton", "BlockedAppsList", "BlockedAppsStatusText",
        "BlockedAppsEmptyText", "AppSearchInput", "AppSearchNotice", "AppPickerList",
        "RefreshProcessesButton",
    ])
    def test_every_blocked_apps_id_the_suite_drives_is_still_there(self, auto_id):
        assert f'AutomationProperties.AutomationId="{auto_id}"' in self.BLOCKED_XAML

    def test_the_per_row_ids_keep_their_shape(self):
        assert "StringFormat=RemoveApp_{0}" in self.BLOCKED_XAML
        assert "StringFormat=AppEnabledSwitch_{0}" in self.BLOCKED_XAML

    @pytest.mark.parametrize("auto_id", [
        "ProfileNameInput", "RenameProfileButton", "NewProfileButton",
        "DuplicateProfileButton", "DeleteProfileButton",
        "ConfirmDeleteProfileButton", "CancelDeleteProfileButton",
    ])
    def test_the_new_profile_controls_are_all_addressable(self, auto_id):
        assert f'AutomationProperties.AutomationId="{auto_id}"' in self.BLOCKED_XAML

    def test_the_new_ids_sit_on_controls_not_layout_panels(self):
        """#134: an id on a Border or a StackPanel is never surfaced."""
        for marker, control in (
            ('AutomationId="ProfileNameInput"', "TextBox"),
            ('AutomationId="NewProfileButton"', "Button"),
            ('AutomationId="DeleteProfileButton"', "Button"),
        ):
            before = self.BLOCKED_XAML.split(marker)[0]
            opening = before.rstrip().rsplit("<", 1)[-1].split()[0]
            assert opening == control, f"{marker} sits on <{opening}>, not <{control}>"


# ============================== a break leaves the shield, and everything
# ============================== else, alone (F5)

class TestABreakStandsTheShieldDown:
    """
    F5's promise is that during a break blocked apps are allowed. The way that
    is kept is that nothing starts the blocker again: the sprint's end stops
    enforcing, and the break path never calls BeginEnforcing.

    Written as source tests because the alternative — a second "break mode" in
    AppBlockerService — is exactly what this must not become. A mode could be
    entered by mistake; no call at all cannot be.
    """

    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    BLOCKER = Path(DESKTOP_DIR) / "Services" / "AppBlockerService.cs"

    def vm(self) -> str:
        return self.TODAY_VM.read_text(encoding="utf-8")

    def break_region(self) -> str:
        source = self.vm()
        assert "breaks and cycles (F5)" in source, "the F5 code should be in one place"
        return source.split("breaks and cycles (F5)")[1].split("--------------- stats")[0]

    def test_ending_a_sprint_stops_enforcing_before_any_break_can_start(self):
        source = self.vm()
        end = source.split("private void EndSprint(bool completed, bool interrupted = false)")[1].split("\n    /// <summary>")[0]
        assert "_main.Blocker.StopEnforcing();" in end

    def test_nothing_in_the_break_path_starts_the_blocker(self):
        region = self.break_region()
        assert "BeginEnforcing" not in region, \
            "a break that enforces is not a break; the shield stays down for all of it"

    def test_the_blocker_gained_no_break_mode(self):
        blocker = self.BLOCKER.read_text(encoding="utf-8")
        for name in ("CycleState", "RunningBreak", "IsOnBreak", "BreakMode"):
            assert name not in blocker, \
                f"F5 uses the existing BeginEnforcing/StopEnforcing; {name} in the blocker is a second way to be wrong"

    def test_the_break_never_touches_momentum_the_streak_or_the_goal(self):
        region = self.break_region()
        for forbidden in ("MomentumScore", "ApplyMomentum", "CurrentStreak", "DailyGoal"):
            assert forbidden not in region, \
                f"a break must not reach {forbidden}; five minutes off is not progress and not a penalty"

    def test_only_a_completed_sprint_earns_a_break(self):
        source = self.vm()
        offer = source.split("private void OfferBreakIfEarned(bool completed)")[1].split("\n    }")[0]
        assert "CycleState.OffersBreak(completed)" in offer, \
            "ending early must not be rewarded with a break; the rule stays in the model"

    def test_a_break_starts_no_sprint_of_its_own_without_a_cycle(self):
        region = self.break_region()
        assert "StartsNextSprint" in region, \
            "only a cycle continues by itself; a single sprint's break ends quietly"


class TestBreakCopyTracksScheduledSleepWindow:
    """#272: during an F5 break in scheduled sleep hours, the sprint shield is
    down but the nightly shield still closes blocked apps; Today must say so."""

    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    BREAK_COPY = Path(DESKTOP_DIR) / "Models" / "BreakCopy.cs"

    def vm(self) -> str:
        return self.TODAY_VM.read_text(encoding="utf-8")

    def copy(self) -> str:
        """Since #301 the break's wording lives in one model, as ShieldCopy's does."""
        assert self.BREAK_COPY.exists(), "#301: the break's wording lives in Models/BreakCopy.cs"
        return self.BREAK_COPY.read_text(encoding="utf-8")

    def panel_text_getter(self) -> str:
        getter = re.search(
            r"public\s+string\s+BreakPanelText\s*=>\s*(.*?);",
            self.vm(),
            re.DOTALL,
        )
        assert getter, "could not find the BreakPanelText getter in TodayViewModel.cs"
        return " ".join(getter.group(1).split())

    def test_break_text_distinguishes_the_nightly_shield_from_an_open_break(self):
        # #301 moved the ternary #272 added into BreakCopy.PanelText; the view
        # model passes it the same sleep-window check.
        expression = self.panel_text_getter()
        assert "BreakCopy.PanelText(AppBlockerService.IsWithinSleepWindow(S)," in expression, (
            "#272: BreakPanelText must check the scheduled sleep window because "
            "blocked apps are still closed during a break then"
        )
        running = " ".join(self.copy().split("if (onBreak)")[1].split(";")[0].split())
        assert re.search(
            r"inSleepWindow\s*\?\s*"
            r"\$?\"[^\"]*sleep[^\"]*\"\s*:\s*"
            r"\"The shield is down\. Blocked apps are allowed until the break ends\.\"",
            running,
            re.IGNORECASE,
        ), (
            "#272: the sleep-window branch must say the nightly shield is still "
            "up and blocked apps will be closed; only its outside branch may say "
            "they are allowed until the break ends"
        )

    def test_each_break_tick_raises_the_sleep_aware_text(self):
        source = self.vm()
        tick = source.split("private void OnBreakTick()")[1].split("\n    }")[0]
        assert "Raise(nameof(BreakPanelText))" in tick, (
            "#272: a break that crosses into scheduled sleep hours must refresh "
            "BreakPanelText on that tick"
        )

    # ------------------------------------------------------------------ #301
    # #272 fixed the running break's line only. Inside the window the offer
    # before a break, the caption under the ring and Settings' description of
    # breaks still promised the shield was down.

    def test_the_offer_says_the_sleep_shield_is_still_up(self):
        """
        Replaces a test that only checked the IsOnBreak setter raised
        BreakPanelText, which it did before #272 too. This one fails whenever
        either offer, short or long, loses its sleep-window line.
        """
        assert "BreakCopy.PanelText(AppBlockerService.IsWithinSleepWindow(S)," in self.panel_text_getter()
        panel = self.copy().split("public static string PanelText(")[1].split("\n    }")[0]
        offer = " ".join(panel.split("if (onBreak)")[1].split(";", 1)[1].split())
        sleep_lines = re.findall(
            r"inSleepWindow\s*\?\s*\$\"[^\"]*nightly sleep shield stays up until "
            r"\{sleepEndsText\}, so blocked apps are still closed\.\"",
            offer,
        )
        assert len(sleep_lines) == 2, (
            "#301: the short and the long break offer must each say the nightly "
            f"sleep shield stays up inside the window; found {len(sleep_lines)}"
        )

    def test_the_ring_caption_follows_the_sleep_window_on_every_break_tick(self):
        tick = self.vm().split("private void OnBreakTick()")[1].split("\n    }")[0]
        assert re.search(
            r"SessionStateText\s*=\s*BreakCopy\.Caption\(\s*"
            r"AppBlockerService\.IsWithinSleepWindow\(S\)\s*,\s*_breakResumed\s*\)",
            tick,
        ), (
            "#301: the caption under the ring must be recomputed on every break "
            "tick, because the window can open or close mid-break"
        )
        caption = self.copy().split("public static string Caption(")[1]
        # #304: the resumed one is parallel again, on two lines.
        for line in ('"Break — sleep shield still up"',
                     '"Break resumed —\\nsleep shield still up"'):
            assert line in caption, f"#301: the caption needs {line} for the sleep window"

    def test_every_ring_caption_fits_inside_the_ring(self, theme_probe):
        """
        #301 and #304. The caption under the ring sat in a horizontal
        StackPanel, which measures it at unlimited width, so it never wrapped.
        A line wider than the ring at that height painted across the stroke,
        and one wider than the whole ring was clipped at both ends: #301's
        first wording showed as "eak resumed — the sleep shield is still u",
        and "Sprint finished while FlowShield was closed" (247.6 px) and
        "Break resumed — the shield is down" (206.5 px) still overran the
        ring's ~177 px at the caption line.

        Since #304 the caption wraps, centred, inside a MaxWidth. Whether that
        fits is a question about pixels, so the probe lays out the real
        TodayView with the app's own resources and embedded Inter: every
        caption RingCaption lists, with the shield glyph beside it when a
        sprint runs, and with nothing below it (the caption at its lowest,
        where the ring is narrowest) or with "Sprint 4 of 4" below it. Every
        box it reports must sit inside the ring's inner circle, corners
        included, and no caption may take more than two lines. (The timer's
        own box is not checked: its corners are empty line padding.)
        """
        entries = theme_probe["ringCaptions"]
        assert entries, "the probe measured no ring captions"
        for entry in entries:
            where = f"\"{entry['text']}\" ({entry['below']} below)"
            assert entry["styled"] and entry["fontSize"] == 12, entry
            assert (entry["font"] or "").lower() == "inter-regular.ttf", (
                f"{where} was measured in {entry['font']}, not the embedded Inter")
            # MM:SS in tabular digits is the widest the timer gets without
            # shrinking further, so it is also the tallest: the worst case.
            assert re.fullmatch(r"\d\d:\d\d", entry["timerText"]), entry["timerText"]
            assert entry["timer"][3] > 55, f"{where}: the timer line was not laid out: {entry['timer']}"
            assert entry["lines"] <= 2, f"#304: {where} takes {entry['lines']} lines"

            radius = entry["ringDiameter"] / 2 - entry["ringStroke"]
            centre = entry["ringDiameter"] / 2
            for name in ("caption", "glyph", "cycle"):
                box = entry[name]
                if box is None:
                    continue
                x, y, w, h = box
                for cx, cy in ((x, y), (x + w, y), (x, y + h), (x + w, y + h)):
                    reach = ((cx - centre) ** 2 + (cy - centre) ** 2) ** 0.5
                    assert reach <= radius, (
                        f"#304: {where}: the {name} box {box} reaches {reach:.1f} px from the "
                        f"centre, past the ring's {radius:.1f} px inner edge")

    def test_the_layout_probe_covers_both_sleep_states_and_the_glyph(self, theme_probe):
        entries = theme_probe["ringCaptions"]
        texts = {" ".join(e["text"].split()) for e in entries}
        for text in ("Break — the shield is down", "Break resumed — the shield is down",
                     "Break — sleep shield still up", "Break resumed — sleep shield still up",
                     "Sprint finished while FlowShield was closed", "Sprint resumed — shield III"):
            assert text in texts, f"#304: {text!r} was not laid out"
        assert {e["below"] for e in entries} == {"none", "cycle"}
        assert all((e["glyph"] is not None) == e["running"] for e in entries), (
            "the glyph shows beside a running sprint's caption and nowhere else")

    def test_the_view_model_hard_codes_no_line_about_the_shield_being_down(self):
        """Every break line comes from BreakCopy, which knows about the window."""
        code = re.sub(r"//.*", "", self.vm())
        literals = re.findall(r'"(?:[^"\\\n]|\\.)*"', code)
        claims = [s for s in literals if re.search(r"shield (is|stays|comes) down|shield down", s, re.I)]
        assert not claims, (
            f"#301: {claims} would promise the shield is down inside the sleep "
            "window too; take the line from BreakCopy instead"
        )

    def test_the_offer_is_re_raised_while_it_is_on_screen(self):
        """
        No clock runs while a break is on offer, so the window opening under it
        went unnoticed until the next sprint. The one timer keeps running for
        the offer, raises its text, and stops once nothing is on screen.
        """
        source = self.vm()
        offer = source.split("private void OfferBreakIfEarned(bool completed)")[1].split("\n    }")[0]
        shown = offer.split("BreakOfferVisible = true;")[1].split("BreakOfferVisible = false;")[0]
        assert "_tick.Start();" in shown, (
            "#301: the timer must keep running while a break offer waits on screen"
        )
        tick = source.split("private void OnTick()")[1].split("\n    }")[0]
        assert "if (!IsRunning)" in tick, (
            "#301: OnTick needs a path for when neither a sprint nor a break runs"
        )
        idle = tick.split("if (!IsRunning)")[1].split("var remaining")[0]
        assert re.search(
            r"if\s*\(\s*BreakOfferVisible\s*\)\s*Raise\(nameof\(BreakPanelText\)\);"
            r"\s*else\s+_tick\.Stop\(\);",
            idle,
        ), (
            "#301: while no sprint or break runs, a tick must refresh the offer's "
            "text if the offer is up, and stop the timer if it is not"
        )

    def test_settings_describes_breaks_without_promising_the_shield_is_down(self):
        xaml = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(encoding="utf-8")
        assert "The shield is down while one runs" not in xaml, (
            "#301: a nightly sleep window still closes blocked apps during a break"
        )
        assert ("The sprint's shield is down while one runs (a nightly sleep window "
                "still applies)") in xaml

    # ------------------------------------------------------------------ #304
    # #301's follow-up: the five-minutes-left notification still promised the
    # shield comes down, the ring's older captions overran the ring, and the
    # checklist and the site said the shield is down with no condition.

    RING_CAPTION = Path(DESKTOP_DIR) / "Models" / "RingCaption.cs"

    def code(self) -> str:
        """The view model with comments stripped, so a line left in a comment can't pass."""
        return re.sub(r"//.*", "", self.vm())

    def test_the_five_minutes_left_notification_asks_the_sleep_window(self):
        """
        The notification speaks about the moment the time is up, so the window
        is asked about that moment: a window opening or closing inside the
        last five minutes changes which shield is up then.
        """
        code = self.code()
        call = code.split("NotificationKind.FiveMinutesLeft", 1)[1].split(";", 1)[0]
        call = " ".join(call.split())
        assert re.search(
            r"BreakCopy\.EndingSoon\(\s*AppBlockerService\.IsWithinSleepWindow\(\s*S\s*,\s*"
            r"_endsAtUtc\.ToLocalTime\(\)\s*\)\s*,\s*"
            r"SleepBlockingViewModel\.Format\(\s*S\.SleepBlockEndTime\s*\)\s*\)",
            call,
        ), f"#304: the notification's words must come from BreakCopy.EndingSoon; got {call!r}"
        assert "comes down" not in call, "#304: no hand-typed copy of the line beside it"

    def test_every_ring_caption_comes_from_ring_caption_or_break_copy(self):
        """
        Tier 5's layout probe measures RingCaption's list. A caption typed
        straight into the view model would never be measured.
        """
        code = self.code()
        assignments = re.findall(r"SessionStateText\s*=(?!=)\s*([^;]*);", code)
        assignments += re.findall(r"(?<!void )BeginRunning\(([^;]*)\);", code)
        assignments += re.findall(r"_sessionStateText\s*=\s*([^;]*);", code)
        assert len(assignments) >= 9, assignments
        for rhs in assignments:
            rhs = " ".join(rhs.split())
            if rhs == "stateText":  # BeginRunning's own parameter
                continue
            assert '"' not in rhs, f"#304: {rhs!r} is typed into the view model; add it to RingCaption"
            assert "RingCaption." in rhs or "BreakCopy.Caption(" in rhs, rhs

    def test_ring_caption_lists_every_line_it_defines(self):
        assert self.RING_CAPTION.exists(), "#304: the ring's captions live in Models/RingCaption.cs"
        source = self.RING_CAPTION.read_text(encoding="utf-8")
        every = source.split("public static IReadOnlyList<(string Text, bool Running)> Every()")[1]
        members = re.findall(r"public const string (\w+)", source)
        members += re.findall(r"public static string (\w+)\(ShieldLevel", source)
        assert len(members) >= 9, members
        for member in members:
            assert re.search(rf"\b{member}\b", every), f"#304: RingCaption.Every() leaves out {member}"
        assert "BreakCopy.Caption(" in every, "and the four break captions"

    def test_the_caption_wraps_centred_inside_the_ring(self):
        xaml = (Path(DESKTOP_DIR) / "Views" / "TodayView.xaml").read_text(encoding="utf-8")
        block = xaml.split('AutomationProperties.AutomationId="SessionStateText"')[0]
        block = block[block.rindex("<TextBlock"):]
        assert 'TextWrapping="Wrap"' in block and 'TextAlignment="Center"' in block, block
        assert re.search(r'MaxWidth="\d+"', block), block

    def test_the_checklist_qualifies_the_shield_being_down_during_breaks(self):
        checklist = (Path(DESKTOP_DIR).parent / "LAUNCH_FEATURE_CHECKLIST.md").read_text(encoding="utf-8")
        line = next(l for l in checklist.splitlines() if "During breaks" in l)
        assert "sleep" in line, f"#304: F5 promises the shield is down with no condition: {line}"
        assert "Blocked apps are allowed and" not in line, line

    def test_the_site_never_says_the_shield_is_down_without_the_sleep_window(self):
        for page in sorted((Path(DESKTOP_DIR).parent / "Website").glob("*.html")):
            if page.name == "changelog.html":
                continue  # it describes the fixes to these claims
            for number, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"shield (is |comes |stays )?down", line, re.I):
                    assert "sleep" in line.lower(), (
                        f"#304: {page.name}:{number} says the shield is down with no word "
                        f"about a sleep window: {line.strip()}")


class TestNothingSellsOrLocksDuringABreak:
    """
    F20: the trial lock and anything about money wait for a sprint to end. A
    break is part of the same sitting — locking the app or offering to sell
    during the three minutes between two sprints breaks that promise just as
    surely, and until F5 the guard only knew about a running sprint.
    """

    MAIN_VM = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"

    def source(self) -> str:
        return self.MAIN_VM.read_text(encoding="utf-8")

    def test_focus_in_progress_includes_the_break(self):
        source = self.source()
        assert re.search(r"IsFocusInProgress\s*=>\s*Today\.IsRunning\s*\|\|\s*Today\.IsOnBreak", source), \
            "the guard must know a break is under way"

    def test_the_access_check_waits_for_the_break_too(self):
        source = self.source()
        refresh = source.split("public void RefreshAccess()")[1].split("\n    /// <summary>")[0]
        assert "IsFocusInProgress" in refresh, \
            "the lock screen must not appear between two sprints of a cycle"

    def test_a_notification_that_interrupts_focus_waits_for_the_break_too(self):
        source = self.source()
        notify = source.split("public bool Notify(")[1].split("\n    /// <summary>")[0]
        assert "NotificationPolicy.ShouldShow(kind, Settings, IsFocusInProgress)" in notify

    def test_the_break_over_notice_is_switchable_like_the_others(self):
        settings_vm = (Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs").read_text(encoding="utf-8")
        assert "NotificationKind.BreakOver" in settings_vm
        settings_xaml = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="NotifyBreakOverToggle"' in settings_xaml


class TestTheRingSaysWhichClockIsRunning:
    """
    DESIGN_SYSTEM §2: teal means state, selection or progress — through a
    sprint. A break drawn in the same teal arc would read as "the shield is up"
    at a glance, which is the one thing it is not (§7 timer ring).
    """

    XAML = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"

    def test_the_two_arcs_have_different_colours_and_never_show_together(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        assert 'Visibility="{Binding SprintRingVisible' in xaml
        assert 'Visibility="{Binding BreakRingVisible' in xaml
        # DynamicResource since F21: a colour reference has to re-resolve when
        # the light theme swaps the tokens dictionary under it.
        assert 'Stroke="{DynamicResource InkDim}" StrokeThickness="12"' in xaml, \
            "the break arc is text-muted, not primary"

    def test_the_view_model_keeps_them_exclusive(self):
        vm = (Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert re.search(r"SprintRingVisible\s*=>\s*!IsOnBreak", vm)
        assert re.search(r"BreakRingVisible\s*=>\s*IsOnBreak", vm)


class TestShortSprintsCannotBuyCredit:
    """
    PR #230 review: --short-sprints makes any sprint run five seconds, and it is
    an ordinary command-line flag — nothing stops a customer passing it. As
    first written, EndSprint still recorded the sprint at its *planned* length
    and ran ApplyMomentum on it, so `FlowShield.exe --short-sprints` with a
    90-minute sprint selected bought 30 points of momentum, a streak day and a
    day's goal every five seconds.

    The rule it now follows is --expire-trial's: a test flag may take something
    away, never hand it out. A shortened sprint records nothing and moves no
    score, exactly like a sprint cancelled inside the grace period.

    Proven to fail first: deleting the `if (CycleState.SprintCountsAsProgress)`
    guard in EndSprint (going back to an unconditional Sessions.Add +
    ApplyMomentum) fails the second and third assertions below.
    """

    MODEL = Path(DESKTOP_DIR) / "Models" / "CycleState.cs"
    TODAY_VM = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    APP = Path(DESKTOP_DIR) / "App.xaml.cs"

    def vm(self) -> str:
        return self.TODAY_VM.read_text(encoding="utf-8")

    def test_the_flag_has_a_named_invariant_of_its_own(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "public static bool SprintCountsAsProgress => !UseShortSprints;" in source, \
            "the rule must be one readable line, not a condition spread through the view model"

    def test_a_shortened_sprint_is_never_recorded(self):
        end = self.vm().split("private void EndSprint(bool completed, bool interrupted = false)")[1].split(
            "\n    /// <summary>")[0]
        guard = end.split("if (CycleState.SprintCountsAsProgress)")
        assert len(guard) == 2, "EndSprint must gate the record on the flag's invariant"
        body = guard[1].split("\n        }")[0]
        assert "S.Sessions.Add(_current);" in body, \
            "the session record must sit inside the guard, not outside it"
        assert "ApplyMomentum(completed, _current);" in body, \
            "momentum must sit inside the guard too"

        # Nothing may add a session or score outside that guard.
        outside = guard[0] + guard[1].split("\n        }", 1)[1]
        for forbidden in ("S.Sessions.Add(", "ApplyMomentum("):
            assert forbidden not in outside, \
                f"{forbidden} outside the guard lets --short-sprints buy credit again"

    def test_the_resume_path_cannot_be_used_to_get_round_it(self):
        """The other place a sprint is recorded and scored (F3's resume)."""
        resume = self.vm().split("public void ResumeInterruptedSprint(")[1].split(
            "\n    private void OnTick()")[0]
        assert "if (CycleState.SprintCountsAsProgress)" in resume
        recorded = resume.split("if (CycleState.SprintCountsAsProgress)")[1].split(
            "\n                }")[0]
        assert "S.Sessions.Add(session);" in recorded
        assert "ApplyMomentum(completed: true, session);" in recorded

    def test_the_daily_goal_and_streak_are_reached_only_through_that_record(self):
        """
        DailyGoal counts S.Sessions, and the streak only moves inside
        ApplyMomentum — so gating those two is gating all three kinds of credit.
        Nothing else in the view model may touch the goal or the streak.
        """
        vm = self.vm()
        apply_momentum = vm.split("private void ApplyMomentum(")[1].split("\n    private ")[0]
        assert "DailyGoal.NoteProgress" in apply_momentum
        assert "S.MomentumScore" in apply_momentum

        # RefreshStats settles the streak for the day, which must stay a
        # read-only settle — it may not count a sprint that was never recorded.
        elsewhere = vm.replace(apply_momentum, "")
        assert "DailyGoal.NoteProgress" not in elsewhere, \
            "goal credit must have exactly one route, and it is the gated one"

    def test_the_flag_is_documented_as_test_only_where_it_is_read(self):
        app = self.APP.read_text(encoding="utf-8")
        block = app.split('"--short-sprints"')[1].split("\n        }")[0]
        assert "Models.CycleState.UseShortSprints = true;" in block
        assert "IsPro" not in block and "TrialStartedUtc" not in block, \
            "a launch flag must never grant a licence or a trial"


class TestTheTrayFollowsTheBreak:
    """
    PR #230 review: during a break the tray still read "Start sprint (last
    settings)", which is the idle label. The break is not idle — the next thing
    is the next sprint, and that is what the row does.
    """

    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"

    def test_the_menu_names_the_next_sprint_during_a_break(self):
        build = self.WINDOW.read_text(encoding="utf-8").split(
            "private void BuildTrayMenu(")[1].split("\n    /// <summary>")[0]
        assert 'onBreak ? "Start next sprint" : "Start sprint (last settings)"' in build, \
            "the tray must say what it is about to do"
        assert "Vm?.Today.IsOnBreak == true" in build

    def test_it_is_still_the_same_start_command(self):
        """
        The label changed, not the action: starting a sprint cuts the break
        short through the same start flow as the Today button and Space use.
        """
        build = self.WINDOW.read_text(encoding="utf-8").split(
            "private void BuildTrayMenu(")[1].split("\n    /// <summary>")[0]
        assert "QuickStart()" in build
        assert "StartBreak" not in build, "the tray never reaches into the break itself"


class TestQuickStartBringsOpenAppQuestionForward:
    """
    Issue #270: when a blocked app is already open, StartSprint shows F7's
    open-apps question and returns. Starting from the tray or global hotkey
    must bring that question into view instead of silently leaving it hidden.
    """

    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"

    def source(self) -> str:
        return self.WINDOW.read_text(encoding="utf-8")

    def method(self, source: str, name: str) -> str:
        match = re.search(
            rf"\bprivate\s+(?:void|IntPtr)\s+{re.escape(name)}\s*\([^)]*\)\s*\{{",
            source,
        )
        assert match, f"MainWindow must define {name}() for issue #270 quick start handling"
        depth = 1
        for index in range(match.end(), len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[match.end():index]
        assert False, f"could not find the end of MainWindow.{name}()"

    def test_the_tray_start_item_uses_quickstart(self):
        source = self.source()
        tray = self.method(source, "BuildTrayMenu")
        assert re.search(r"QuickStart\s*\(\s*\)", tray), \
            "the tray start item must use QuickStart() so F7's open-apps question is shown"

    def test_the_global_hotkey_uses_quickstart(self):
        source = self.source()
        hotkey = self.method(source, "WndProc")
        assert re.search(r"QuickStart\s*\(\s*\)", hotkey), \
            "the global hotkey must use QuickStart() so F7's open-apps question is shown"

    def test_quickstart_restores_and_selects_today_for_the_open_apps_question(self):
        source = self.source()
        quick_start = self.method(source, "QuickStart")
        assert re.search(r"StartCommand\s*\.\s*Execute\s*\(\s*null\s*\)", quick_start), \
            "QuickStart() must still execute Today.StartCommand"
        assert re.search(r"if\s*\([^)]*Today\.RunningAppsPanelVisible", quick_start), \
            "QuickStart() must detect when StartSprint shows F7's open-apps question"
        assert re.search(r"\.CurrentPage\s*=\s*AppPage\.Today", quick_start), \
            "QuickStart() must select Today when the open-apps question appears"
        assert re.search(r"\b(?:RestoreFromTray|BringToFront)\s*\(\s*\)", quick_start), \
            "QuickStart() must restore or bring the window forward for the open-apps question"


# ================================= the light theme and the keyboard (F21, #236)

class TestLightThemeSwitchF21:
    """
    F21 / DESIGN_SYSTEM.md §12 "Theme": the app draws in dark, light, or
    whatever Windows is set to, and switches while it runs.

    Proven to fail first: before F21, App.xaml merged only Theme.xaml,
    Theme.xaml and ShieldGlyphs.xaml each merged Tokens.xaml themselves, every
    colour reference in every view was a StaticResource, and there was no
    ThemeService at all -- each assertion below fails against that tree.

    The arrangement is load-bearing and not obvious, which is why it is pinned
    here: WPF resolves a merged dictionary's keys nearest-last, so a *second*
    Tokens merge anywhere would shadow the one ThemeService swaps, and the app
    would silently stay dark for ever.
    """

    DESKTOP = Path(DESKTOP_DIR)
    SERVICE = Path(DESKTOP_DIR) / "Services" / "ThemeService.cs"

    def read(self, *parts) -> str:
        return self.DESKTOP.joinpath(*parts).read_text(encoding="utf-8")

    def _xaml_files(self):
        return [p for p in self.DESKTOP.rglob("*.xaml")
                if "obj" not in p.parts and "bin" not in p.parts]

    def test_app_merges_the_tokens_first_and_on_their_own(self):
        app = self.read("App.xaml")
        order = [app.find('Source="Styles/Tokens.xaml"'),
                 app.find('Source="Styles/ShieldGlyphs.xaml"'),
                 app.find('Source="Styles/Theme.xaml"')]
        assert all(position > 0 for position in order), \
            "App.xaml must merge Tokens.xaml, ShieldGlyphs.xaml and Theme.xaml itself"
        assert order == sorted(order), \
            "the tokens must be merged before the glyphs and the styles that reference them"

    def test_nothing_else_merges_a_tokens_dictionary(self):
        offenders = []
        for path in self._xaml_files():
            if path.name == "App.xaml":
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r'<ResourceDictionary Source="[^"]*Tokens(\.Light)?\.xaml"', text):
                offenders.append(path.name)
        assert not offenders, (
            "a second Tokens merge shadows the dictionary ThemeService swaps, pinning "
            "the app to one theme: " + ", ".join(offenders))

    def test_every_colour_reference_is_dynamic(self):
        """
        A StaticResource brush is resolved once, when the XAML loads. Swapping
        the dictionary under it changes nothing, so every colour token is
        referenced dynamically -- with one documented exception.
        """
        names = json.loads((Path(DESKTOP_DIR).parent / "design" / "tokens.json")
                           .read_text(encoding="utf-8"))["app_names"]
        keys = set(names.values()) | {value + "Color" for value in names.values()}

        # The Card style's drop shadow is a Freezable inside a sealed Style
        # setter, which cannot carry a DynamicResource. It is black in both
        # themes (design/tokens.json "shadow"), so it never needs to change.
        allowed = {("Theme.xaml", "ShadowColor")}

        offenders = []
        for path in self._xaml_files():
            if path.name.startswith("Tokens"):
                continue
            text = path.read_text(encoding="utf-8")
            for key in re.findall(r"\{StaticResource\s+([^}\s]+)\}", text):
                if key in keys and (path.name, key) not in allowed:
                    offenders.append(f"{path.name}: {key}")
        assert not offenders, (
            "colour tokens referenced with StaticResource will not follow a theme "
            "change: " + ", ".join(sorted(set(offenders))))

    def test_the_shield_glyphs_are_referenced_dynamically_too(self):
        """
        A DynamicResource inside a Freezable resolves once and never again, so
        ThemeService reloads the glyph dictionary instead. Anything holding the
        old DrawingImage by StaticResource would keep the old colours.
        """
        for path in self._xaml_files():
            text = path.read_text(encoding="utf-8")
            for key in ("ShieldGlyphSoft", "ShieldGlyphFirm", "ShieldGlyphSealed"):
                assert f"{{StaticResource {key}}}" not in text, \
                    f"{path.name} holds {key} statically; it will not be recoloured"

    def test_the_service_swaps_the_dictionary_and_follows_windows(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        assert "Tokens.Light.xaml" in source and "Tokens.xaml" in source, \
            "ThemeService must swap between the two generated token dictionaries"
        assert "MergedDictionaries" in source, "the swap happens in App.Resources"
        assert "AppsUseLightTheme" in source, \
            "System must follow Windows' own app theme"
        assert "SystemEvents.UserPreferenceChanged" in source, \
            "a Windows theme change must be picked up without a restart"
        assert "Registry.CurrentUser.OpenSubKey" in source, "HKCU, read-only"
        for write in ("SetValue", "CreateSubKey", "DeleteValue", "LocalMachine"):
            assert write not in source, \
                f"the Windows theme is read-only; ThemeService must not call {write}"

    def test_the_glyphs_are_reloaded_when_the_theme_changes(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        swap = source.split("private static void Swap(")[1].split("\n    private ")[0]
        assert "ShieldGlyphs" in swap, \
            "the swap must reload ShieldGlyphs.xaml -- its brushes are inside Freezables"
        assert "RefreshConverterBindings" in swap, \
            "converters that look colours up themselves must be re-run after the swap"

    def test_the_converters_that_read_colours_reread_them(self):
        converters = self.read("Infrastructure", "Converters.cs")
        for converter in ("HeatStepToBrushConverter", "ResourceKeyToBrushConverter",
                          "ShieldLevelToGlyphConverter"):
            assert converter in converters
        assert "TryFindResource" in converters or "TryColour" in converters, \
            "these converters must look the resource up each time, not cache it"

    def test_the_setting_defaults_to_following_windows_and_persists(self):
        settings = self.read("Models", "AppSettings.cs")
        assert "public AppTheme Theme { get; set; } = AppTheme.System;" in settings, \
            "the stored default must be System, so an upgrade keeps following Windows"
        theme = self.read("Models", "AppTheme.cs")
        assert "System = 0" in theme, \
            "System must serialise as 0 or every settings file written before F21 reads as Dark"

        view_model = self.read("ViewModels", "SettingsViewModel.cs")
        appearance = view_model.split("public AppTheme Theme")[1].split("\n    /// <summary>")[0]
        assert "ThemeService.Apply(value)" in appearance, "the choice applies immediately"
        assert "_main.SaveSettings()" in appearance, "and is saved"

    def test_settings_offers_the_three_choices_with_ids(self):
        xaml = self.read("Views", "SettingsView.xaml")
        assert "APPEARANCE" in xaml
        for automation_id, name in (("ThemeSystemRadio", "System theme"),
                                    ("ThemeDarkRadio", "Dark theme"),
                                    ("ThemeLightRadio", "Light theme")):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml
            assert f'AutomationProperties.Name="{name}"' in xaml

    def test_the_title_bar_and_the_tray_icon_follow_the_theme(self):
        window = self.read("MainWindow.xaml.cs")
        assert "ThemeService.IsLight ? 0 : 1" in window, \
            "DWM's dark title bar must be off in the light theme"
        assert "ThemeService.Changed += OnThemeChanged" in window, \
            "the window must redraw what it painted in code when the theme changes"
        countdown = window.split("private static System.Drawing.Icon? CountdownIcon(")[1]
        assert "ThemeService.TryColour(\"PrimaryColor\"" in countdown, \
            "the tray countdown icon must be drawn in the current theme's primary"


class TestKeyboardAndFocusF21:
    """
    DESIGN_SYSTEM.md §13: every interactive element is reachable and usable
    from the keyboard, with a visible 2px focus ring.

    Proven to fail first: before F21 the app set no FocusVisualStyle anywhere,
    so every control fell back to WPF's 1px dotted rectangle -- which on these
    surfaces is next to invisible -- and Escape did nothing on any dialog.
    """

    DESKTOP = Path(DESKTOP_DIR)
    THEME = Path(DESKTOP_DIR) / "Styles" / "Theme.xaml"

    #: Styles a customer operates, each of which must carry the focus ring.
    FOCUSABLE_STYLES = ("BtnBase", "Field", "Switch", "Segment", "SegmentShield",
                        "PlainItem", "PickerItem")

    def theme(self) -> str:
        return self.THEME.read_text(encoding="utf-8")

    @staticmethod
    def _style_block(xaml: str, key: str) -> str:
        blocks = [b for b in xaml.split("<Style ")[1:] if f'x:Key="{key}"' in b]
        assert blocks, f"no <Style x:Key=\"{key}\"> in Theme.xaml"
        return blocks[0]

    def test_the_focus_ring_is_two_pixels_of_the_focus_ring_token(self):
        block = self._style_block(self.theme(), "FocusVisual")
        assert 'StrokeThickness="2"' in block, "§13 asks for a 2px ring"
        assert "{DynamicResource FocusRing}" in block, \
            "the ring must use the focus-ring token, and follow the theme"

    @pytest.mark.parametrize("key", FOCUSABLE_STYLES)
    def test_every_operable_style_sets_the_focus_visual(self, key):
        block = self._style_block(self.theme(), key)
        assert '<Setter Property="FocusVisualStyle" Value="{StaticResource FocusVisual}"/>' in block, \
            f"{key} must show the shared 2px focus ring"

    def test_plain_radio_buttons_and_check_boxes_get_it_implicitly(self):
        xaml = self.theme()
        for target in ("RadioButton", "CheckBox"):
            blocks = [b for b in xaml.split("<Style ")[1:]
                      if b.startswith(f'TargetType="{target}">')]
            assert blocks, f"expected an implicit <Style TargetType=\"{target}\">"
            assert "FocusVisualStyle" in blocks[0], \
                f"unstyled {target}s must take the focus ring too"

    def test_the_heatmap_cells_take_focus(self):
        """
        §7: a heatmap must not rely on colour alone, and a cell has to be
        reachable to be read out. HeatCellItem inherits PlainItem's ring.
        """
        block = self._style_block(self.theme(), "HeatCellItem")
        assert 'BasedOn="{StaticResource PlainItem}"' in block
        assert '<Setter Property="Focusable" Value="True"/>' in block

    def test_focusable_false_is_only_on_decoration(self):
        """
        Focusable="False" on something a customer has to operate makes it
        unreachable from the keyboard. Each exception is listed here with its
        reason, so a new one has to be argued for rather than typed.
        """
        allowed_tags = {
            # The scrollbar's paging buttons: the ScrollViewer itself handles
            # Page Up/Down, and these are invisible (Opacity 0).
            "RepeatButton",
        }
        allowed_styles = {
            # The heatmap legend's five swatches are decoration beside the
            # "Less"/"More" captions, which carry the meaning.
            "HeatLegendItem",
        }
        allowed_ids = {
            # The same legend's own list: not hit-testable either, and every
            # cell it explains is focusable in its place (HeatCellItem).
            "HeatmapLegend",
            # The Schedule page's ScrollViewer: a container. Focusable, it took
            # a Tab stop of its own and drew a dashed rectangle round the whole
            # page. Every control inside keeps its tab stop, and Page Up/Down
            # from any of them still scrolls it.
            "SchedulePageScroll",
        }

        offenders = []
        for path in self.DESKTOP.rglob("*.xaml"):
            if "obj" in path.parts or "bin" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")

            for match in re.finditer(r'<(\w+)((?:[^<>]|\n)*?)Focusable="False"((?:[^<>])*?)>',
                                     text):
                element = match.group(2) + match.group(3)
                automation_id = re.search(r'AutomationProperties.AutomationId="([^"]+)"', element)
                if match.group(1) in allowed_tags:
                    continue
                if automation_id and automation_id.group(1) in allowed_ids:
                    continue
                offenders.append(f"{path.name}: <{match.group(1)}>")

            for match in re.finditer(
                    r'<Setter Property="Focusable" Value="False"\s*/>', text):
                key = re.findall(r'x:Key="([^"]+)"', text[:match.start()])
                if not key or key[-1] not in allowed_styles:
                    offenders.append(f"{path.name}: style {key[-1] if key else '?'}")

        assert not offenders, (
            "these are taken out of the tab order without a reason on record: "
            + ", ".join(sorted(set(offenders))))

    def test_escape_closes_the_dialogs_that_can_be_cancelled(self):
        for name in ("ConfirmDeleteDialog", "FriendlyErrorDialog"):
            xaml = (self.DESKTOP / "Views" / f"{name}.xaml").read_text(encoding="utf-8")
            assert 'IsCancel="True"' in xaml, \
                f"{name} must have a cancel button, so Escape closes it"

    def test_escape_closes_the_panels_that_can_be_cancelled(self):
        window = (self.DESKTOP / "MainWindow.xaml.cs").read_text(encoding="utf-8")
        handler = window.split("protected override void OnPreviewKeyDown(")[1] \
                        .split("\n    /// <summary>")[0]
        assert "Key.Escape" in handler
        assert "DismissActivationCommand" in handler, \
            "Escape must dismiss the activation prompt, which has a Cancel button"
        assert "FirstRun.SkipCommand" in handler, \
            "Escape must skip the welcome, which has a Skip button"

    def test_an_open_panel_keeps_the_keyboard_inside_it(self):
        """
        UI Automation can still reach controls under an overlay (CLAUDE.md,
        "Covered controls"), and so could Tab. Each overlay is a Cycle tab
        scope, and takes focus when it opens.
        """
        xaml = (self.DESKTOP / "MainWindow.xaml").read_text(encoding="utf-8")
        assert xaml.count('KeyboardNavigation.TabNavigation="Cycle"') >= 4, \
            "the lock screen, welcome, activation prompt and terms gate are each a tab scope"
        assert xaml.count('IsVisibleChanged="OnOverlayVisibleChanged"') >= 4


class TestAccessibleNamesF21:
    """
    DESIGN_SYSTEM.md §13: every control has an accessible name. A button whose
    content is a bound string or a TextBlock reads out as nothing useful, and a
    text box has no visible label to borrow from at all.

    Proven to fail first: SettingsView's "Skip today" button and TodayView's
    momentum explainer toggle both had an AutomationId and no name.
    """

    DESKTOP = Path(DESKTOP_DIR)
    TAGS = ("Button", "CheckBox", "RadioButton", "TextBox", "DatePicker",
            "ListBox", "PasswordBox", "ComboBox", "Slider")

    def _views(self):
        return [p for p in self.DESKTOP.rglob("*.xaml")
                if "obj" not in p.parts and "bin" not in p.parts
                and p.parent.name != "Styles"]

    def test_every_control_has_a_name_or_literal_content(self):
        element = re.compile(r"<(" + "|".join(self.TAGS) + r")(?=[\s/>])(.*?)(/>|>)", re.S)
        offenders = []
        for path in self._views():
            text = path.read_text(encoding="utf-8")
            for match in element.finditer(text):
                tag, attributes = match.group(1), match.group(2)
                if "AutomationProperties.Name=" in attributes:
                    continue
                # A literal Content is the control's own visible label, which
                # UI Automation already reads out; a bound one is not.
                if re.search(r'Content="([^"{]+)"', attributes):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.name}:{line} <{tag}>")
        assert not offenders, (
            "controls with no accessible name: " + ", ".join(offenders))

    def test_the_scan_actually_finds_controls(self):
        """A regex that matched nothing would pass for the wrong reason."""
        element = re.compile(r"<(" + "|".join(self.TAGS) + r")(?=[\s/>])", re.S)
        found = sum(len(element.findall(p.read_text(encoding="utf-8"))) for p in self._views())
        assert found > 50, f"expected the app's controls to be scanned, found {found}"

    def test_the_new_appearance_control_did_not_displace_an_existing_id(self):
        """Every AutomationId in the app is still unique to one control."""
        seen = {}
        for path in self._views():
            for automation_id in re.findall(r'AutomationProperties.AutomationId="([^"]+)"',
                                            path.read_text(encoding="utf-8")):
                # A bound id ({Binding AutomationId}) is one per row at run time.
                if automation_id.startswith("{"):
                    continue
                seen.setdefault(automation_id, []).append(path.name)
        duplicates = {k: v for k, v in seen.items() if len(set(v)) > 1}
        # A handful are deliberately shared between a page and the lock screen.
        allowed = {"LicenseKeyInput"}
        assert not (set(duplicates) - allowed), f"duplicate AutomationIds: {duplicates}"


#: Where the offscreen theme probe lives, and where it is run from.
THEME_PROBE = Path(DESKTOP_DIR).parent / "automation" / "probe" / "ThemeProbe"


@pytest.fixture(scope="module")
def theme_probe():
    """
    Runs `automation/probe/ThemeProbe` once and hands back its report.

    Module-scoped: it builds and runs the real app's resources, which costs a
    few seconds, and every assertion below reads the same three snapshots.
    """
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        pytest.skip("no .NET SDK on this machine")

    result = subprocess.run(
        [dotnet, "run", "--project", str(THEME_PROBE), "-c", "Release", "-v", "q", "--nologo"],
        cwd=str(Path(DESKTOP_DIR).parent), capture_output=True, text=True, timeout=600)

    assert result.returncode == 0, (
        "the theme probe did not run:\n" + result.stdout[-2000:] + result.stderr[-2000:])

    # The build writes to stdout too; the report is the last JSON line.
    lines = [line for line in result.stdout.splitlines() if line.startswith("{")]
    assert lines, "the probe printed no report:\n" + result.stdout[-2000:]
    return json.loads(lines[-1])


class TestTheThemeActuallySwitchesF21:
    """
    The one F21 test that is not source text.

    Every other test in this file reads the XAML and the C# and checks that the
    right words are in the right places. All of them passed against a
    ThemeService that did nothing at all: it looked for the merged dictionary
    with

        merged.FirstOrDefault(d => d.Source == DarkTokens)

    where DarkTokens is an absolute pack URI, while App.xaml merges the
    dictionary with a *relative* Source ("Styles/Tokens.xaml").
    ResourceDictionary.Source hands back exactly the Uri that was set on it, so
    the two never compared equal, the lookup found nothing, the swap logged
    "theme not switched" and returned, and Settings -> Appearance moved a radio
    button and changed no pixels. Source tests cannot see that, and neither can
    a probe that merges the dictionaries itself with pack URIs -- it builds the
    equality the app does not have.

    So this runs the real App.xaml. `automation/probe/ThemeProbe` creates the
    app's own Application subclass, calls InitializeComponent() to merge exactly
    what App.xaml merges in exactly the way it spells it, asks ThemeService to
    switch, and prints what each resource resolves to. No window is created and
    nothing is shown, so it is safe to run beside a UI suite.

    Proven to fail first: restoring the Uri-equality line above makes
    test_switching_to_light_changes_every_colour fail with Bg still #FF121110.
    """

    PROBE = THEME_PROBE

    #: A few tokens whose two themes are far apart, with their values from
    #: design/tokens.json. If these are right, the dictionary really was swapped.
    EXPECTED_DARK = {"Bg": "#FF121110", "Ink": "#FFF2F0EB", "Primary": "#FF3AA892"}
    EXPECTED_LIGHT = {"Bg": "#FFE6E4DF", "Ink": "#FF1A1917", "Primary": "#FF0C6B5C"}

    @pytest.fixture()
    def probe(self, theme_probe):
        return theme_probe

    def test_the_app_starts_dark(self, probe):
        assert probe["start"]["isLight"] is False
        for key, value in self.EXPECTED_DARK.items():
            assert probe["start"][key] == value, f"{key} is wrong before any switch"

    def test_switching_to_light_changes_every_colour(self, probe):
        """The check the whole feature rests on: the resources really change."""
        assert probe["light"]["isLight"] is True, \
            "ThemeService reported no switch -- it did not find the dictionary to replace"
        for key, value in self.EXPECTED_LIGHT.items():
            assert probe["light"][key] == value, (
                f"{key} is still {probe['light'][key]} after Apply(Light) -- the merged "
                f"Tokens dictionary was not swapped")

        changed = sum(1 for key, value in probe["start"].items()
                      if key != "isLight" and probe["light"][key] != value)
        assert changed >= 14, (
            f"only {changed} resources changed; the light theme redefines all of them")

    def test_switching_back_to_dark_restores_every_colour(self, probe):
        for key, value in probe["start"].items():
            assert probe["dark"][key] == value, \
                f"{key} did not come back to its dark value"

    def test_the_shield_glyphs_are_recoloured_too(self, probe):
        """
        The case a DynamicResource cannot serve: these brushes are inside
        DrawingImages, which are Freezables, so the dictionary is reloaded. If
        the reload is skipped the glyphs keep the dark theme's colours -- and a
        text-muted glyph on a light surface is close to invisible.
        """
        assert probe["start"]["glyphSoft"] == "#FFB0ADA5"
        assert probe["light"]["glyphSoft"] == "#FF5C5954", \
            "the Soft glyph kept its dark colour; ShieldGlyphs.xaml was not reloaded"
        assert probe["light"]["glyphFirm"] == "#FF0C6B5C"
        assert probe["dark"]["glyphSoft"] == "#FFB0ADA5"

    def test_the_heatmap_ramp_follows_the_theme(self, probe):
        """Mixed in code from surface-2 and primary, so it has to re-read them."""
        assert probe["start"]["heatTop"] == "#FF3AA892"
        assert probe["light"]["heatTop"] == "#FF0C6B5C", \
            "the heatmap's top step is still the dark theme's primary"

    def test_the_probe_shows_no_window(self):
        """
        It must stay safe to run while a UI suite owns the screen, so it may
        never create or show a window.
        """
        source = (self.PROBE / "Program.cs").read_text(encoding="utf-8")
        for forbidden in ("new Window", ".Show()", ".ShowDialog()", "app.Run("):
            assert forbidden not in source, \
                f"the theme probe must not {forbidden} -- it runs beside the UI suite"


# ================== what the first full UI-suite run taught us (#242-#245)

class TestTheUiSuiteCanObserveWhatItAsserts:
    """
    Four of the first full UI run's failures were the suite measuring itself
    rather than the product (#242, #243, #245). None of them could fail loudly:
    each looked exactly like a product bug. These are the source-level traps,
    so the same classes of mistake cannot come back quietly.
    """

    POLICY = Path(DESKTOP_DIR) / "Models" / "EndSprintPolicy.cs"
    CONTROLLER = Path(DESKTOP_DIR).parent / "automation" / "desktop" / "app_controller.py"
    TIER3 = Path(DESKTOP_DIR).parent / "automation" / "tests" / "test_tier3_e2e.py"

    def _short_seconds(self, name: str) -> float:
        source = self.POLICY.read_text(encoding="utf-8")
        match = re.search(
            name + r"\s*=>\s*UseShortTimers\s*\?\s*TimeSpan\.FromSeconds\((\d+(?:\.\d+)?)\)"
            r"\s*:\s*TimeSpan\.From(\w+)\((\d+(?:\.\d+)?)\)",
            source,
        )
        assert match, f"{name}'s short/real pair was not found; update this test"
        return float(match.group(1))

    def _real(self, name: str) -> tuple[str, float]:
        source = self.POLICY.read_text(encoding="utf-8")
        match = re.search(
            name + r"\s*=>\s*UseShortTimers\s*\?\s*TimeSpan\.FromSeconds\(\d+(?:\.\d+)?\)"
            r"\s*:\s*TimeSpan\.From(\w+)\((\d+(?:\.\d+)?)\)",
            source,
        )
        assert match, f"{name}'s short/real pair was not found; update this test"
        return match.group(1), float(match.group(2))

    # A UIA element lookup plus an IsEnabled read costs a second or more on
    # Today. #242's log showed End anyway unlocking 2.507 s after the panel
    # opened -- correct against a 2 s delay, and unobservable by the test that
    # was meant to catch it. Anything under this is a window the suite cannot
    # see into, so a test asserting on it is really asserting on its own speed.
    OBSERVABLE_SECONDS = 5.0

    def test_every_shortened_wait_is_long_enough_to_observe(self):
        for name in ("GracePeriod", "FirmConfirmDelay", "SealedCountdown"):
            seconds = self._short_seconds(name)
            assert seconds >= self.OBSERVABLE_SECONDS, (
                f"{name} is {seconds}s under --short-timers, shorter than a UIA "
                f"round trip; a test asserting the gate would fail on the app's "
                f"correct behaviour, as #242 did"
            )

    def test_shortening_never_touches_what_a_customer_gets(self):
        assert self._real("GracePeriod") == ("Minutes", 2.0)
        assert self._real("FirmConfirmDelay") == ("Seconds", 5.0)
        assert self._real("SealedCountdown") == ("Seconds", 30.0)

    def test_the_soft_allow_wait_is_observed_with_real_timers(self):
        """
        The Soft notice's Allow wait is three seconds under --short-timers
        (SoftOverlayPolicy.AllowWait; the 1.0.10 spec fixes it there), which
        is under OBSERVABLE_SECONDS: a tier 3 test asserting "Allow is still
        disabled" against it would be asserting on its own speed, #242's trap
        again. So the tier 3 test that observes the wait launches the app
        without --short-timers and watches the real five-second first try.
        """
        policy = (Path(DESKTOP_DIR) / "Models" / "SoftOverlayPolicy.cs").read_text(encoding="utf-8")
        match = re.search(r"if \(UseShortTimers\) return TimeSpan\.FromSeconds\((\d+(?:\.\d+)?)\);", policy)
        assert match, "SoftOverlayPolicy.AllowWait's --short-timers value was not found"
        shortened = float(match.group(1))

        tier3 = self.TIER3.read_text(encoding="utf-8")
        head = re.search(r"def test_allow_is_disabled_until_the_wait_runs_out\(self, (\w+)\)", tier3)
        assert head, "the tier 3 test that observes Allow's wait was not found"
        if shortened < self.OBSERVABLE_SECONDS:
            assert head.group(1) == "real_wait_app", (
                f"Allow's wait is {shortened:g}s under --short-timers, shorter than a UIA "
                f"round trip; the test must run on the real_wait_app fixture"
            )
        fixture = tier3.split("def real_wait_app(", 1)
        assert len(fixture) == 2, "the real_wait_app fixture was not found in tier 3"
        assert "short_timers=False" in fixture[1].split("yield", 1)[0], (
            "real_wait_app must launch without --short-timers"
        )

    def test_the_driver_agrees_with_the_shortened_grace_period(self):
        """
        #222 widened the grace period and left SHORT_GRACE_SECONDS at the old
        value with a comment naming timers that no longer existed. A stale
        mirror of a constant is worse than no mirror.
        """
        source = self.CONTROLLER.read_text(encoding="utf-8")
        match = re.search(r"SHORT_GRACE_SECONDS\s*=\s*(\d+(?:\.\d+)?)", source)
        assert match, "SHORT_GRACE_SECONDS was not found in the controller"
        assert float(match.group(1)) == self._short_seconds("GracePeriod"), (
            "the driver's idea of the shortened grace period must match "
            "EndSprintPolicy.cs"
        )

    def test_waiting_out_the_grace_period_outlasts_it(self):
        """
        wait_out_grace_period polls for the button to stop offering a free
        cancel, and 24 call sites trust it. Its own deadline therefore has to
        outlast the thing it is waiting for: at 15 s it was exactly the grace
        period, so a call made near the start of a sprint could time out before
        the flip and return as if the grace were over -- silently, because
        returning on the deadline is legitimate for callers that only want to
        be past it.
        """
        from desktop.app_controller import DesktopController

        grace = self._short_seconds("GracePeriod")
        assert DesktopController.SHORT_GRACE_SECONDS == grace
        assert DesktopController.GRACE_WAIT_TIMEOUT > grace, (
            f"wait_out_grace_period's default ({DesktopController.GRACE_WAIT_TIMEOUT}s) "
            f"must outlast the {grace}s grace period it waits for"
        )
        assert DesktopController.GRACE_WAIT_MARGIN_SECONDS >= 5.0, (
            "the margin must cover a label read landing just before the "
            "boundary plus the poll interval"
        )

        # And the default must stay derived, not written out beside the grace:
        # two literals is how they came to be equal in the first place.
        source = self.CONTROLLER.read_text(encoding="utf-8")
        assert "GRACE_WAIT_TIMEOUT = SHORT_GRACE_SECONDS + GRACE_WAIT_MARGIN_SECONDS" in source, (
            "derive the timeout from SHORT_GRACE_SECONDS rather than repeating a number"
        )
        assert not re.search(r"def wait_out_grace_period\(self, timeout: float = \d", source), (
            "a literal default here cannot follow the grace period when it changes"
        )

    def test_no_ui_test_sends_a_bare_space_to_type_keys(self):
        """
        pywinauto drops " " from type_keys unless with_spaces=True, so
        `type_keys(" ")` sends nothing at all -- which is why F4's Space
        shortcut tests failed against a shortcut that works (#245). {SPACE}
        is unambiguous and needs no flag.
        """
        # A real call, so the sentence above describing the trap is not itself
        # an offender.
        pattern = re.compile(r"\.type_keys\(\s*(['\"])( +)\1\s*\)")
        for path in (self.TIER3, self.CONTROLLER):
            text = path.read_text(encoding="utf-8")
            assert not pattern.search(text), (
                f"{path.name}: type_keys with a bare space sends no key; use "
                '"{SPACE}" or pass with_spaces=True'
            )

    def test_no_test_asserts_on_whitespace_text_of_strips(self):
        """
        text_of() strips both ends, so an assertion about a leading or trailing
        space can never pass however the app behaves -- #245's second test
        asserted exactly that and read as a product bug for a night.
        """
        text = self.TIER3.read_text(encoding="utf-8")
        offenders = re.findall(
            r"text_of\([^)]*\)\.(?:startswith|endswith)\(\s*(['\"]) +\1", text)
        assert not offenders, (
            "text_of() strips whitespace; assert on an interior space instead"
        )

    def test_the_trial_that_expires_mid_sprint_gets_a_usable_runway(self):
        """
        #243: --expire-trial-in=8 ran out before the driver had finished
        connecting, so the app correctly refused the Pro-gated custom sprint
        length and F20's scenario never started a sprint at all.
        """
        conftest = (Path(DESKTOP_DIR).parent / "automation" / "tests" / "conftest.py").read_text(
            encoding="utf-8")
        block = conftest.split("def trial_expiring_soon_app(", 1)
        assert len(block) == 2, "the trial_expiring_soon_app fixture was not found"
        match = re.search(r"runway\s*=\s*(\d+)", block[1])
        assert match, "the fixture should name its runway in one place"
        assert int(match.group(1)) >= 60, (
            "a trial shorter than the driver's own setup expires before the test "
            "can pick a Pro-gated sprint length"
        )
        assert "trial_ends_at" in block[1], (
            "the fixture must publish when the trial ends so the test can wait "
            "for the real boundary rather than sleeping a guess"
        )


class TestHeroExampleMatchesTheOtherBoxes:
    """The 5-7 PM example shares the SmartScreen note's border and corners."""

    CSS = Path(SERVER_DIR).parent / "Website" / "styles.css"

    def _rule(self, selector):
        css = self.CSS.read_text(encoding="utf-8")
        start = css.index(selector + " {")
        return css[start:css.index("}", start)]

    def test_rounded_like_the_smartscreen_note(self):
        rule = self._rule(".hero .example")
        assert "border-radius: var(--radius-sm)" in rule
        assert "border: 1px solid var(--color-border)" in rule
        assert "border-left: 3px" not in rule


class TestCycleTextFollowsTheSprintLength:
    """Choosing a sprint length after the cycle count left the cycle line
    saying the old length ("4 sprints of 90 minutes" with 25 min selected):
    SelectedMinutes never raised CycleDescription."""

    VM = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "TodayViewModel.cs"

    def test_changing_the_length_refreshes_the_cycle_line(self):
        source = self.VM.read_text(encoding="utf-8")
        start = source.index("public int SelectedMinutes")
        setter = source[start:source.index("\n    }\n", start)]
        assert "Raise(nameof(CycleDescription))" in setter

    def test_restoring_a_running_sprint_refreshes_it_too(self):
        source = self.VM.read_text(encoding="utf-8")
        restore = source.index("Raise(nameof(SelectedMinutes));\n                Raise(nameof(PresetMinutes));")
        assert "Raise(nameof(CycleDescription))" in source[restore:restore + 400]


class TestACompletedSprintDoesNotCountTheSleep300:
    """
    #300. A DispatcherTimer does not tick while the PC sleeps, so the first
    tick after waking reaches OnTick's time-up branch with the nap behind it.
    Since #203 a sprint FlowShield watched at least half of still finishes
    there, which is right -- but EndSprint stamped its end with DateTime.UtcNow,
    the moment of waking, and FocusSession.ActualMinutes is EndedUtc minus
    StartedUtc. Eight hours asleep became eight hours focused: on the summary
    card, the minutes goal and today's tile, History, the heatmap and the
    journal export. F3's startup path already ended a completed sprint at its
    planned end; both now go through RunningSprint.RecordedEnd.

    The cap is not tied to finishing. Input is dispatched ahead of the
    Background-priority timer, so an End click handled after waking but
    before that first tick ends the sprint early with now hours past its
    planned end; it is still recorded as ended early, momentum and all, but
    its minutes are capped the same way.
    """

    SETTINGS = DESKTOP / "Models" / "AppSettings.cs"
    VM = DESKTOP / "ViewModels" / "TodayViewModel.cs"

    # EndSprint's assignment as 1.0.9 shipped it, verbatim: proves the checker
    # below rejects it rather than passing by construction.
    PRE_FIX_END_SPRINT = (
        "        _current.EndedUtc = interrupted\n"
        "            ? _current.StartedUtc + TimeSpan.FromMinutes(S.ActiveSprint?.WatchedSoFar ?? 0)\n"
        "            : DateTime.UtcNow;\n"
    )

    @staticmethod
    def _code(source: str) -> str:
        """The source without its // comments, which describe the old behaviour."""
        return re.sub(r"(^|\s)//[^\n]*", r"\1", source)

    @staticmethod
    def _block(source: str, marker: str) -> str:
        start = source.find(marker)
        assert start >= 0, f"{marker!r} was not found; update this test"
        opening = source.find("{", start)
        depth = 0
        for index in range(opening, len(source)):
            depth += source[index] == "{"
            depth -= source[index] == "}"
            if depth == 0:
                return source[opening + 1:index]
        raise AssertionError(f"unbalanced braces after {marker!r}")

    def _problems(self, end_sprint: str) -> list[str]:
        """What is wrong with the end EndSprint records; empty when nothing is."""
        match = re.search(r"_current\.EndedUtc\s*=(.*?);", end_sprint, re.S)
        assert match, "EndSprint's EndedUtc assignment was not found; update this test"
        value = " ".join(match.group(1).split())
        call = re.search(r"RunningSprint\.RecordedEnd\(([^)]*)\)", value)
        outside = value.replace(call.group(0), "") if call else value

        problems = []
        if "DateTime.UtcNow" in outside:
            problems.append("the end is the bare DateTime.UtcNow, which after a sleep is the wake time")
        if call is None:
            problems.append("the end must come from RunningSprint.RecordedEnd")
        else:
            args = [arg.strip() for arg in call.group(1).split(",")]
            if args[1:2] != ["_endsAtUtc"]:
                problems.append(f"the planned end passed must be _endsAtUtc, not {args[1:2]}")
            if args[3:5] != ["DateTime.UtcNow", "completed"]:
                problems.append(f"now and completed must be passed as such, not {args[3:5]}")
        return problems

    def test_the_helper_caps_any_uninterrupted_end_at_the_planned_end(self):
        source = self._code(self.SETTINGS.read_text(encoding="utf-8"))
        assert re.search(
            r"public static DateTime RecordedEnd\(\s*DateTime startedUtc,\s*DateTime plannedEndUtc,\s*"
            r"double watchedMinutes,\s*DateTime nowUtc,\s*bool completed,\s*bool interrupted\)",
            source,
        ), "the call sites below are checked against this parameter order"
        helper = self._block(source, "public static DateTime RecordedEnd(")
        assert re.search(
            r"return\s+nowUtc\s*>\s*plannedEndUtc\s*\?\s*plannedEndUtc\s*:\s*nowUtc\s*;",
            helper,
        ), "any end but an interruption is now, and never after the planned end"

    def test_end_sprint_records_its_end_through_the_helper(self):
        end = self._block(self._code(self.VM.read_text(encoding="utf-8")), "private void EndSprint(")
        assert self._problems(end) == []

    def test_the_shipped_assignment_is_rejected(self):
        problems = self._problems(self.PRE_FIX_END_SPRINT)
        assert any("bare DateTime.UtcNow" in problem for problem in problems), problems


class TestSchedulePageKeepsTheSleepWindow:
    """F6 moves Sleep Blocking inside Schedule; nothing of the sleep window may be lost."""

    def test_the_sleep_view_is_embedded_not_rewritten(self):
        page = (Path(DESKTOP_DIR) / "Views" / "ScheduleView.xaml").read_text(encoding="utf-8")
        assert "<views:SleepBlockingView" in page and 'DataContext="{Binding Sleep}"' in page
        sleep = (Path(DESKTOP_DIR) / "Views" / "SleepBlockingView.xaml").read_text(encoding="utf-8")
        for automation_id in ("SleepBlockToggle", "SleepStartInput", "SleepEndInput",
                              "SaveSleepWindowButton", "SleepStatusText", "SleepWindowText"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in sleep

    def test_the_tab_keeps_its_id_and_shortcut(self):
        xaml = (Path(DESKTOP_DIR) / "MainWindow.xaml").read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="Tab_SleepBlocking"' in xaml
        assert 'Key="D4" Command="{Binding NavigateCommand}" CommandParameter="SleepBlocking"' in xaml
        assert 'Text="Schedule"' in xaml

    def test_every_new_id_is_on_a_real_control(self):
        xaml = (Path(DESKTOP_DIR) / "Views" / "ScheduleView.xaml").read_text(encoding="utf-8")
        for match in re.finditer(r"<(\w+)[^>]*AutomationProperties\.AutomationId=", xaml):
            assert match.group(1) not in ("Border", "Grid", "StackPanel", "WrapPanel"), (
                f"an AutomationId on a {match.group(1)} is never surfaced (#134)")


class TestSchedulePageRefusesInTheViewModel:
    """
    A Sealed sprint makes the Schedule page read-only. The buttons go grey, but
    a disabled or covered control can still be reached (CLAUDE.md, "Covered
    controls"), so every method that changes a schedule or a template refuses
    on its own, not only through its command's CanExecute.
    """

    VM = Path(DESKTOP_DIR) / "ViewModels" / "ScheduleViewModel.cs"

    def _body(self, source: str, signature: str) -> str:
        start = source.index(signature)
        return source[start:source.index("\n    }\n", start)]

    @staticmethod
    def _first_statement(body: str) -> str:
        """The first line of code inside the braces, blanks and comments skipped."""
        for line in body[body.index("{") + 1:].splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("//"):
                return stripped
        return ""

    def test_every_change_checks_can_edit_first(self):
        """
        First, not merely somewhere: a guard after the change, or in a comment,
        would satisfy a substring check and refuse nothing.
        """
        source = self.VM.read_text(encoding="utf-8")
        for signature in ("private void OpenScheduleEditor(", "private void SaveSchedule(",
                          "private void DeleteSchedule(", "private void SetScheduleEnabled(",
                          "private void OpenTemplateEditor(", "private void SaveTemplate(",
                          "private void DeleteTemplate(", "private void RestoreTemplates("):
            first = self._first_statement(self._body(source, signature))
            assert first.startswith("if (") and "!EnsureCanEdit()" in first, (
                f"{signature.strip('(')} must refuse during a Sealed sprint before it does "
                f"anything else; its first statement is {first!r}")


class TestSchedulePageNamesAndLabels:
    """
    After the PR A review: template names are unique because the page's
    AutomationIds are built from them, the range labels come from the constants
    Save checks, and the active-profile chip has an id no profile name can
    produce. The report's tier table must also know about the probe tests.
    """

    VM = Path(DESKTOP_DIR) / "ViewModels" / "ScheduleViewModel.cs"
    XAML = Path(DESKTOP_DIR) / "Views" / "ScheduleView.xaml"

    def test_the_editor_saves_a_unique_name(self):
        source = self.VM.read_text(encoding="utf-8")
        start = source.index("private void SaveTemplate(")
        body = source[start:source.index("\n    }\n", start)]
        assert "S.UniqueTemplateName(template.Name, except: template)" in body
        assert body.index("template.Normalize()") < body.index("UniqueTemplateName("), \
            "the number goes on the cleaned name, or a later Normalize could cut it off"

    def test_the_range_labels_are_bound_not_typed(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        assert 'Text="{Binding SprintMinutesLabel}"' in xaml
        assert 'Text="{Binding BreakMinutesLabel}"' in xaml
        assert "(5–240)" not in xaml and "(1–60)" not in xaml, "a typed limit can drift from the constant"
        vm = self.VM.read_text(encoding="utf-8")
        assert "Sprint minutes ({StudyTemplate.MinSprintMinutes}" in vm
        assert "{StudyTemplate.MaxSprintMinutes})" in vm
        assert "Break minutes ({CycleState.MinBreakMinutes}" in vm
        assert "{CycleState.MaxBreakMinutes})" in vm

    def test_the_active_profile_chip_has_an_id_no_profile_name_can_produce(self):
        vm = self.VM.read_text(encoding="utf-8")
        assert 'AutomationId = "TemplateProfileActive"' in vm
        assert 'AutomationId = $"TemplateProfile_{p.Name}"' in vm
        xaml = self.XAML.read_text(encoding="utf-8")
        assert "TemplateProfile_{0}" not in xaml, "the prefix form would let a profile named Active collide"
        assert xaml.count('AutomationProperties.AutomationId="{Binding AutomationId}"') == 3, \
            "every chip (template, day, profile) takes its whole id from the view model"

    def test_every_tier_file_has_a_row_in_the_report(self):
        """make_report.py counts tests per tier by filename; a file with no row leaves the rows short of the total."""
        root = Path(DESKTOP_DIR).parent
        report = (root / "automation" / "make_report.py").read_text(encoding="utf-8")
        for path in sorted((root / "automation" / "tests").glob("test_tier*.py")):
            assert f'"{path.name}":' in report, f"{path.name} has no tier row in make_report.py"


# ===================== scheduled sprints start through Start's gates (F6, PR C)

class TestScheduledSprintsGoThroughStart:
    """
    F6: a schedule starts a template by itself. That is a Start nobody pressed,
    so every rule a pressed Start obeys must hold for it too: terms, first run,
    the trial, one sprint at a time, and F7's open-apps question unless the
    heads-up already named the apps. Comments are stripped, so a call left only
    in a comment can't satisfy these.
    """

    TODAY = Path(DESKTOP_DIR) / "ViewModels" / "TodayViewModel.cs"
    MAIN = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"
    APP = Path(DESKTOP_DIR) / "App.xaml.cs"
    TODAY_XAML = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"

    @staticmethod
    def code(path: Path) -> str:
        return "\n".join(line.split("//")[0] for line in path.read_text(encoding="utf-8").splitlines())

    @staticmethod
    def member(code: str, signature: str) -> str:
        """One member's body, from its signature to the brace that closes it."""
        start = code.index(signature)
        depth = 0
        for index in range(code.index("{", start), len(code)):
            depth += {"{": 1, "}": -1}.get(code[index], 0)
            if depth == 0:
                return code[start:index + 1]
        raise AssertionError(f"no end to {signature}")

    def case(self, signature: str, kind: str) -> str:
        switch = self.member(self.code(self.MAIN), signature)
        return switch.split(f"case ScheduleActionKind.{kind}:", 1)[1].split("break;", 1)[0]

    def test_a_template_starts_through_start_sprint_not_a_copy_of_it(self):
        start = self.member(self.code(self.TODAY), "public bool StartTemplate(")
        assert "StartSprint();" in start
        for copied in ("TermsGateVisible", "FirstRun.IsVisible", "IsLocked", "S.ActiveSprint =",
                       "BeginRunning("):
            assert copied not in start, f"StartTemplate copies {copied}; it must go through StartSprint"

    def test_a_refused_template_start_leaves_nothing_for_the_next_start(self):
        """
        A gate can refuse inside StartSprint before F7's latch is spent. Left
        set, the next Start pressed by hand would skip the question and take
        the template's breaks.
        """
        start = self.member(self.code(self.TODAY), "public bool StartTemplate(")
        refused = start.split("if (!IsRunning && !RunningAppsPanelVisible)", 1)[1]
        assert "_runningAppsAnswered = false;" in refused
        assert "_startingTemplateBreak = null;" in refused
        assert "_startingAnnouncedName = null;" in refused, \
            "a hand Start afterwards would be announced as the template"

    def test_a_schedule_does_nothing_while_busy_or_behind_a_gate(self):
        on_action = self.member(self.code(self.MAIN), "private void OnScheduleAction(")
        guard = on_action.split("switch (action.Kind)", 1)[0]
        assert "if (IsSprintRunning" in guard, "OnScheduleAction must refuse before its switch"
        condition, block = guard[guard.index("if (IsSprintRunning"):].split("{", 1)
        assert "return;" in block
        for gate in ("IsSprintRunning", "Today.IsOnBreak", "IsLocked", "TermsGateVisible",
                     "FirstRun.IsVisible"):
            assert gate in condition, f"a schedule must do nothing while {gate}"

    def test_a_missed_start_is_only_ever_offered(self):
        """Spec 3.3: never start automatically after waking or launching."""
        missed = self.case("private void OnScheduleAction(", "OfferMissed")
        assert "Today.ShowHeadsUp(action, template);" in missed
        assert "StartTemplate(" not in missed

    def test_a_scheduled_start_asks_about_open_apps_unless_the_heads_up_named_them(self):
        """
        The heads-up names the open apps a Firm or Sealed template will close,
        so it stands in for F7's question. With no heads-up (Ask first off), or
        an app opened since, the question is asked as quick start asks it
        (#270): Today, brought to the front.
        """
        start = self.case("private void OnScheduleAction(", "Start")
        assert re.search(r"var named = Today\.HeadsUpNamedWhatWillClose\(action, template\);", start)
        assert "Today.StartTemplate(template, skipOpenAppsPanel: named," in start
        assert start.index("HeadsUpNamedWhatWillClose(") < start.index("Today.HideHeadsUp();"), \
            "read what the card named before the card goes"
        asked = start.split("&& Today.RunningAppsPanelVisible)", 1)[1]
        assert "CurrentPage = AppPage.Today;" in asked
        assert "OpenAppsQuestionRaised?.Invoke(this, EventArgs.Empty);" in asked
        window = self.code(self.WINDOW)
        assert "newVm.OpenAppsQuestionRaised += OnOpenAppsQuestionRaised;" in window
        assert "oldVm.OpenAppsQuestionRaised -= OnOpenAppsQuestionRaised;" in window
        assert "BringToFront()" in self.member(window, "private void OnOpenAppsQuestionRaised(")

    def test_a_scheduled_start_sends_one_notification(self):
        """
        Review of PR C: "Sprint started" is on by default, so a schedule with
        Ask first off sent it and then "Light study started", back to back.
        The named notice (spec 3.3) now stands in for the generic one, sent
        where the sprint starts, so a start that waited on F7's question and
        was answered names the template too. With the scheduled-sprint switch
        off, "Sprint started" still comes: Notify says whether it showed.
        """
        start_case = self.case("private void OnScheduleAction(", "Start")
        # Past the unasked offer (which starts nothing, see the next test),
        # the start's own notice is sent once, where the sprint starts.
        starting = start_case.split("return;", 1)[-1]
        assert "Notify(" not in starting, "a start's notice is sent once, where the sprint starts"
        assert "announceByName: !action.Schedule.AskFirst" in starting

        today = self.code(self.TODAY)
        assert "_startingAnnouncedName = announceByName ? template.Name : null;" in \
            self.member(today, "public bool StartTemplate(")

        start = self.member(today, "private void StartSprint()")
        taken = start.index("var announcedName = _startingAnnouncedName;")
        assert start.index("if (!_runningAppsAnswered)") < taken, \
            "kept while F7's question waits, so answering it names the template"
        assert "_startingAnnouncedName = null;" in start[taken:]
        assert re.search(r"var announced = announcedName is not null\s*&&\s*"
                         r"_main\.Notify\(NotificationKind\.ScheduledSprint, \$\"\{announcedName\} started\",",
                         start)
        assert re.search(r"if \(!announced\)\s*_main\.Notify\(NotificationKind\.SprintStarted,", start)
        assert start.count("_main.Notify(") == 2

    def test_an_ask_first_start_nobody_was_asked_about_is_offered_not_started(self):
        """
        Final review of PR C: the service remembers a heads-up as shown
        before the handler runs, and the handler refuses it while a sprint or
        break is running, so a 25-minute hand sprint ending between T-5 and T
        left the schedule's Start to pass the guard with no card up and no
        question asked. A clock set back past a start, or a westward zone
        change, reach the same place. Ask first is the one promise the switch
        makes: a Start with no card up for its schedule is offered on the
        card ("X is due now", Start now / Skip today), never taken.
        """
        start = self.case("private void OnScheduleAction(", "Start")
        assert "if (action.Schedule.AskFirst && !Today.HeadsUpIsFor(action))" in start
        assert "return;" in start, "the offer is the whole of that tick's work"
        offer, starting = start.split("return;", 1)
        assert offer.index("HeadsUpIsFor(") < offer.index("Today.ShowHeadsUp(action, template);")
        assert "NotifyHeadsUp($\"{template.Name} is due now\"," in offer
        assert "StartTemplate(" not in offer, "an unasked start is offered, never taken"
        assert "HideHeadsUp(" not in offer, "read whether a card is up before anything hides one"
        assert "Today.StartTemplate(template, skipOpenAppsPanel: named," in starting, \
            "a start whose card is up still starts as before"

        today = self.code(self.TODAY)
        # R23: the schedule and the start instant, so a card left up from an
        # earlier start of the same schedule never counts as asked.
        is_for = self.member(today, "public bool HeadsUpIsFor(ScheduleAction action)")
        assert "card.Schedule.Id == action.Schedule.Id" in is_for
        assert "card.StartUtc == action.StartUtc" in is_for
        show = self.member(today, "public void ShowHeadsUp(")
        assert "ScheduleActionKind.Start => $\"{template.Name} is due now\"" in show, \
            "the card says the start is due, not that it is coming"

    def test_the_heads_up_notification_names_what_will_close_and_opens_today(self):
        """
        Polish of PR C (R22a, item 7): with the window in the tray the card
        is the only place the apps were named and nobody saw it, so the
        notification's body carries the card's sentence ("Discord, Steam
        will be closed.") whenever there is one. Its title is the card's own
        time, not "in 5 minutes", which was untrue for a schedule saved two
        minutes ahead. Clicking any of the three opens Today, where the card
        is; the missed one says it was missed.
        """
        main = self.code(self.MAIN)
        assert "in 5 minutes" not in main
        notify = self.member(main, "private void NotifyHeadsUp(")
        assert "var closing = Today.HeadsUpClosingText;" in notify
        assert re.search(r"closing\.Length > 0 \? \$\"\{closing\} \{ask\}\" : ask", notify)
        assert "Notify(NotificationKind.ScheduledSprint, title, body, NotificationAction.OpenToday)" in notify
        assert re.search(r"if \(Notify\([^;]*\) && closing\.Length > 0\)\s*Today\.HeadsUpNamesWereNotified\(\);",
                         notify), "the names count as seen only when the notice with them was sent"

        heads_up = self.case("private void OnScheduleAction(", "HeadsUp")
        assert "NotifyHeadsUp($\"{template.Name} starts at {Today.HeadsUpTimeText}\"," in heads_up
        missed = self.case("private void OnScheduleAction(", "OfferMissed")
        assert "NotifyHeadsUp($\"You missed {template.Name}\"," in missed
        assert "It was due at {Today.HeadsUpTimeText}." in missed
        on_action = self.member(main, "private void OnScheduleAction(")
        assert on_action.count("NotifyHeadsUp(") == 3 and "Notify(NotificationKind" not in on_action, \
            "every card's notice goes through the one helper"

        notifications = Path(DESKTOP_DIR) / "Models" / "Notifications.cs"
        assert "OpenToday" in notifications.read_text(encoding="utf-8")
        clicked = self.member(self.code(self.WINDOW), "private void OnNotificationClicked(")
        assert re.search(r"case NotificationAction\.OpenToday:\s*Vm\.CurrentPage = AppPage\.Today;", clicked)

    def test_the_card_counts_as_having_named_the_apps_only_where_someone_could_see_it(self):
        """
        Polish of PR C (R22b): HeadsUpNamedWhatWillClose credited the card
        with naming the apps even when the window was in the tray and the
        notification named none, so an Ask-first Firm start could close an
        app the user never saw named. The card counts only if the window was
        up (not minimised or in the tray) when it was shown, or the
        notification with the names was actually sent; otherwise the start
        goes through F7's question as an unasked one does.
        """
        today = self.code(self.TODAY)
        show = self.member(today, "public void ShowHeadsUp(")
        assert "_headsUpNamesSeen = _main.IsWindowVisible;" in show
        named = self.member(today, "public bool HeadsUpNamedWhatWillClose(ScheduleAction action, StudyTemplate template)")
        assert "if (closing.Count == 0) return true;" in named
        assert re.search(r"return HeadsUpIsFor\(action\)\s*&&\s*_headsUpNamesSeen\s*&&", named)
        assert re.search(r"public void HeadsUpNamesWereNotified\(\)\s*=>\s*_headsUpNamesSeen = true;", today)
        hide = self.member(today, "public void HideHeadsUp(")
        assert "_headsUpNamesSeen = false;" in hide
        start_now = self.member(today, "private void StartNow(")
        assert start_now.index("_headsUpNamesSeen = true;") < start_now.index("HeadsUpNamedWhatWillClose("), \
            "Start now is pressed on the card itself, so what it names has been seen"

        main = self.code(self.MAIN)
        assert re.search(r"public bool IsWindowVisible\s*=>\s*WindowVisibility\?\.Invoke\(\) \?\? false;", main), \
            "with no window wired, nobody could have seen the card"
        window = self.code(self.WINDOW)
        assert "newVm.WindowVisibility = () => IsVisible && WindowState != WindowState.Minimized;" in window
        assert "oldVm.WindowVisibility = null;" in window

    def test_a_card_goes_when_its_start_is_handled_or_it_goes_stale(self):
        """
        Polish of PR C (R23): a heads-up card whose start was refused at the
        busy or gated guard stayed up saying "starts at 17:00"; a missed
        card never expired although a missed start is offered for 30
        minutes. Now a card is removed when its start is handled (started:
        BeginRunning; refused: the guard; skipped; its schedule switched off
        or deleted) and expires once LateWindow has passed since its start,
        checked on every scheduler tick.
        """
        on_action = self.member(self.code(self.MAIN), "private void OnScheduleAction(")
        guard = on_action.split("switch (action.Kind)", 1)[0]
        refused = guard[guard.index("if (IsSprintRunning"):]
        assert "if (action.Kind == ScheduleActionKind.Start && Today.HeadsUpIsFor(action)) Today.HideHeadsUp();" \
            in refused
        assert refused.index("Today.HideHeadsUp();") < refused.index("return;")

        ctor = self.member(self.code(self.MAIN), "public MainViewModel(")
        assert "Scheduler.Ticked += (_, now) => Today.DropStaleHeadsUp(now);" in ctor

        today = self.code(self.TODAY)
        drop = self.member(today, "public void DropStaleHeadsUp(DateTime nowUtc)")
        assert "SchedulePlanner.CardHasExpired(headsUp.StartUtc, nowUtc)" in drop
        assert "!headsUp.Schedule.Enabled" in drop and "!S.Schedules.Contains(headsUp.Schedule)" in drop
        assert "HideHeadsUp();" in drop

        schedule_vm = self.code(Path(DESKTOP_DIR) / "ViewModels" / "ScheduleViewModel.cs")
        for signature in ("private void DeleteSchedule(", "private void SetScheduleEnabled(",
                          "private void DeleteTemplate("):
            assert "_main.Today.DropStaleHeadsUp(DateTime.UtcNow);" in self.member(schedule_vm, signature), \
                f"{signature} must drop a card for a schedule that is off or gone"

    def test_the_missed_card_says_skip_like_its_button(self):
        """DESIGN_SYSTEM 9: one word for one thing. The button is Skip today; the toast and the page say skipped."""
        show = self.member(self.code(self.TODAY), "public void ShowHeadsUp(")
        assert "$\"It was due at {at}. Start it now, or skip it for today.\"" in show
        assert "leave it for today" not in show
        xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        assert re.search(r'<Button\b[^>]*Content="Skip today"[^>]*AutomationId="HeadsUpSkipButton"', xaml)

    def test_start_now_is_secondary_so_start_sprint_stays_the_one_primary(self):
        """
        DESIGN_SYSTEM 7 allows one Primary per view (Start sprint on Today).
        The card's Start now is Secondary (BtnGhost) and Skip today Quiet,
        mirroring the end panel's Keep going / End anyway pair.
        """
        xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        card = xaml.split("heads-up (F6)", 1)[1].split("timer card", 1)[0]
        assert "BtnPrimary" not in card
        assert re.search(r'<Button\b[^>]*Style="\{StaticResource BtnGhost\}"[^>]*AutomationId="HeadsUpStartNowButton"',
                         card)
        assert re.search(r'<Button\b[^>]*Style="\{StaticResource BtnQuiet\}"[^>]*AutomationId="HeadsUpSkipButton"',
                         card)

    def test_the_heads_up_names_what_the_templates_own_shield_and_list_will_close(self):
        today = self.code(self.TODAY)
        would_close = self.member(today, "private IReadOnlyList<string> AppsItWouldClose(")
        assert "_main.Blocker.RunningBlockedApps(S.ProfileFor(template))" in would_close
        assert "template.Shield >= ShieldLevel.Firm || S.HardKillModeEnabled" in would_close, \
            "the blocker's own rule for closing, so the card never promises less than happens"
        assert "AppsItWouldClose(template)" in self.member(today, "public void ShowHeadsUp(")

    def test_the_card_never_outlives_a_start(self):
        assert "HideHeadsUp();" in self.member(self.code(self.TODAY), "private void BeginRunning(")

    def test_skip_today_saves_the_starts_own_date(self):
        skip = self.member(self.code(self.TODAY), "private void SkipToday(")
        assert re.search(r"\.Skip\(TimeZoneInfo\.ConvertTimeFromUtc\(headsUp\.StartUtc, TimeZoneInfo\.Local\)\.Date\)", skip)
        assert "_main.SaveSettings();" in skip

    def test_short_schedules_is_a_launch_flag(self):
        app = self.code(self.APP)
        flag = app.split('"--short-schedules"', 1)[1].split("}", 1)[0]
        assert "Models.SchedulePlanner.UseShortSchedules = true;" in flag

    def test_the_scheduler_starts_after_the_resumed_sprint(self):
        ctor = self.member(self.code(self.MAIN), "public MainViewModel(")
        assert "Scheduler = new ScheduleService(Settings);" in ctor
        assert "Scheduler.Action += (_, action) => OnScheduleAction(action);" in ctor
        assert ctor.index("Today.ResumeInterruptedSprint();") < ctor.index("Scheduler.Start();")
        assert "Schedule.TemplatesChanged += (_, _) => Today.RefreshTemplates();" in ctor

    def test_the_templates_break_is_saved_restored_and_offered(self):
        today = self.code(self.TODAY)
        assert "TemplateBreakMinutes = _templateBreakMinutes," in self.member(today, "private void StartSprint()")
        resume = self.member(today, "public void ResumeInterruptedSprint(")
        assert "_templateBreakMinutes = saved.TemplateBreakMinutes;" in resume.split(
            "case SprintResume.Resume:", 1)[1].split("case SprintResume.RecordCompleted:", 1)[0]
        assert re.search(r"private int OfferedBreakMinutes\s*=>\s*_templateBreakMinutes\s*\?\?\s*"
                         r"CycleState\.BreakMinutes\(", today)
        assert today.count("CycleState.BreakMinutes(") == 1, "every break length goes through OfferedBreakMinutes"
        assert "var minutes = OfferedBreakMinutes;" in self.member(today, "private void StartBreak()")
        assert re.search(r"private bool OfferedBreakIsLong\s*=>\s*_templateBreakMinutes is null\s*&&", today), \
            "a template's break is its own length, not the fourth-in-a-row long one"

    def test_the_templates_break_rides_with_the_running_break_too(self):
        """
        PR C polish, item 8: a restart during a break inside a template cycle
        resumed the break but not the template's break length, so the cycle's
        later breaks fell back to Settings' lengths. RunningBreak carries it,
        written where the break starts and restored where it resumes.
        """
        today = self.code(self.TODAY)
        assert "TemplateBreakMinutes = _templateBreakMinutes," in self.member(today, "private void StartBreak()")
        resume = self.member(today, "public void ResumeInterruptedBreak(")
        assert "_templateBreakMinutes = saved.TemplateBreakMinutes;" in resume
        assert resume.index("_templateBreakMinutes = saved.TemplateBreakMinutes;") < resume.index("BeginBreakClock(")
        cycle_state = self.code(Path(DESKTOP_DIR) / "Models" / "CycleState.cs")
        assert "public int? TemplateBreakMinutes { get; set; }" in self.member(cycle_state, "public class RunningBreak")

    def test_a_chip_carries_the_templates_break_to_the_next_start(self):
        """
        PR C polish, item 9: a chip on Today fills in length, shield, cycle
        and profile, and now the template's break length with them, taken up
        by the next Start. A hand change of length, shield or cycle
        afterwards keeps it (the chip is a preset, and the rest of the preset
        survives such a change too); only another chip, or the start itself,
        replaces it.
        """
        today = self.code(self.TODAY)
        assert "_startingTemplateBreak = template.BreakMinutes;" in self.member(today, "public void ApplyTemplate(")
        assert "_startingTemplateBreak = template.BreakMinutes;" not in \
            self.member(today, "public bool StartTemplate("), "set once, where the chip and the schedule both go"
        # Set by the chip, consumed by the start, cleared by a refused template start; nowhere else.
        assert len(re.findall(r"_startingTemplateBreak = ", today)) == 3
        for setter in ("public int PresetMinutes", "public string CustomMinutesText", "public bool IsCustomSelected",
                       "public ShieldLevel SelectedShield", "public int CycleSprints"):
            assert "_startingTemplateBreak" not in self.member(today, setter), f"{setter} must keep the chip's break"

    def test_only_a_run_begun_from_a_template_takes_its_breaks(self):
        """
        A cycle's later sprints keep what the run began with; a run begun any
        other way (Start, Space, the tray) takes Settings' break lengths.
        """
        start = self.member(self.code(self.TODAY), "private void StartSprint()")
        after_cycle = start.split("_cycle = _cycle.OnSprintStarted(CycleSprints);", 1)[1]
        assert re.search(r"if \(_cycle\.SprintsDone == 0\)\s*_templateBreakMinutes = _startingTemplateBreak;",
                         after_cycle)
        assert "_startingTemplateBreak = null;" in after_cycle

    def test_the_card_and_the_chips_carry_ids_on_real_controls(self):
        xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        for control, automation_id in (("TextBlock", "HeadsUpCard"), ("TextBlock", "HeadsUpText"),
                                       ("Button", "HeadsUpStartNowButton"), ("Button", "HeadsUpSkipButton")):
            assert re.search(rf'<{control}\b[^>]*AutomationProperties\.AutomationId="{automation_id}"', xaml), \
                f"{automation_id} must sit on a {control} (#134)"
        assert re.search(r'<Button\b[^>]*AutomationProperties\.AutomationId="\{Binding Name, '
                         r'StringFormat=TemplateChip_\{0\}\}"', xaml)

    def test_the_chips_hide_while_a_sprint_or_break_runs(self):
        """Spec 3.5, and the card's twin: a chip mid-sprint would change a running sprint's settings."""
        today = self.code(self.TODAY)
        assert re.search(r"public bool TemplatesVisible\s*=>\s*!IsRunning && !IsOnBreak", today)
        assert "if (IsRunning || IsOnBreak || _main.IsLocked) return;" in \
            self.member(today, "public void ApplyTemplate(")
        assert 'Visibility="{Binding TemplatesVisible, Converter={StaticResource BoolVis}}"' in \
            self.TODAY_XAML.read_text(encoding="utf-8")

    def test_the_scheduled_sprint_notice_is_switchable_like_the_others(self):
        settings_vm = self.code(Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs")
        assert "NotificationKind.ScheduledSprint" in self.member(settings_vm, "public bool NotifyScheduledSprint")
        assert "Raise(nameof(NotifyScheduledSprint));" in self.member(settings_vm, "public bool NotificationsEnabled")
        xaml = (Path(DESKTOP_DIR) / "Views" / "SettingsView.xaml").read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="NotifyScheduledSprintToggle"' in xaml

    def test_the_schedule_page_scroller_is_not_a_tab_stop(self):
        """Controller note (PR A): it drew a dashed focus rectangle round the whole page."""
        xaml = (Path(DESKTOP_DIR) / "Views" / "ScheduleView.xaml").read_text(encoding="utf-8")
        scroller = xaml.split("<ScrollViewer", 1)[1].split(">", 1)[0]
        assert 'AutomationProperties.AutomationId="SchedulePageScroll"' in scroller
        assert 'Focusable="False"' in scroller

    def test_the_new_copy_keeps_to_the_house_voice(self):
        """DESIGN_SYSTEM 9: no exclamation marks, and ASCII-only C# literals."""
        today = self.TODAY.read_text(encoding="utf-8")
        region = today.split("templates and schedules (F6)", 1)[1].split("what is already running (F7)", 1)[0]
        on_action = self.member(self.MAIN.read_text(encoding="utf-8"), "private void OnScheduleAction(")
        # StartSprint sends a scheduled start's "Light study started".
        start = self.member(today, "private void StartSprint()")
        for text in (region, on_action, start):
            for literal in re.findall(r'"[^"\n]*"', text):
                assert "!" not in literal, literal
                assert literal.isascii(), literal


# ===================== F6's chip row moved Today's controls (PR C regressions)

class TestTodayGrewARowAndItsControlsStayReachable:
    """
    PR C's row of template chips made Today's idle page about 56 px taller.
    Two things that had been clear of each other at the default window height
    then overlapped, and two tier 3 tests that pass on main failed on the
    branch alone (test_sealed_locks_the_profile_switcher and
    test_cancelling_a_sprint_clears_the_intention_input):

    - the toast ("Profile "School" added, starting from...") lay over the
      Sealed chip of the shield picker for its four seconds, and an opaque
      Border takes the click, so the sprint started at the default shield
      (Firm) and the switcher stayed enabled;
    - with the page scrolled down to the intention field, Start collapsed the
      chips and itself, the page kept its scroll offset, and the ring with its
      Cancel button slid up under the page header, where no click could reach
      them: the cancel never happened and the intention was never cleared.

    Neither is a test problem. A notice must never take a click meant for the
    page, and a sprint that has just started must show its countdown and the
    way to end it.
    """

    WINDOW_XAML = Path(DESKTOP_DIR) / "MainWindow.xaml"
    TODAY_XAML = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml"
    TODAY_CS = Path(DESKTOP_DIR) / "Views" / "TodayView.xaml.cs"

    def test_the_toast_never_takes_a_click_meant_for_the_page(self):
        xaml = self.WINDOW_XAML.read_text(encoding="utf-8-sig")
        toast = xaml.split("<!-- toast -->", 1)[1].split("<Border", 1)[1].split(">", 1)[0]
        assert 'Visibility="{Binding ToastVisible' in toast, "the toast moved; update this test"
        assert 'IsHitTestVisible="False"' in toast, \
            "the toast must let the mouse (and UI Automation's hit test) through to the page under it"

    def test_a_sprint_starting_brings_the_ring_and_its_end_button_into_view(self):
        handler = TestScheduledSprintsGoThroughStart.member(
            TestScheduledSprintsGoThroughStart.code(self.TODAY_CS), "private void OnViewModelChanged(")
        assert "nameof(TodayViewModel.IsRunning)" in handler and "PageScroll.ScrollToTop()" in handler, \
            "Today must scroll back to the top when a sprint starts"
        assert '<ScrollViewer x:Name="PageScroll"' in self.TODAY_XAML.read_text(encoding="utf-8")

    @pytest.mark.ui
    def test_sealed_can_be_picked_while_the_profile_toast_is_up(self, fresh_app):
        fresh_app.navigate_to_tab("Blocked Apps")
        fresh_app.new_profile("School")          # "Profile "School" added..." for four seconds
        fresh_app.navigate_to_tab("Today")
        assert fresh_app.toast_text(timeout=1.0), "the toast is not up, so this proves nothing"
        fresh_app.select_shield("Sealed")
        assert fresh_app.is_selected("Shield_Sealed"), "the toast took the click meant for the shield picker"

    @pytest.mark.ui
    def test_starting_from_the_intention_field_leaves_the_countdown_and_cancel_in_view(self, fresh_app):
        fresh_app.navigate_to_tab("Today")
        # The field is below the fold at the default height, so this scrolls the page down.
        fresh_app.set_text("IntentionInput", "write the report")
        fresh_app.start_sprint()
        time.sleep(1.0)
        assert fresh_app.is_on_screen("SprintTimerText"), \
            "the countdown was left scrolled up under the page header"
        fresh_app.cancel_sprint()
        time.sleep(0.8)
        assert "cancelled" in fresh_app.session_state().lower(), \
            "Cancel sprint could not be clicked where it was left"


# ============================ the taskbar Jump List starts like the tray (1.0.10, 5)

class TestTheJumpListStartsLikeTheTray:
    """
    Spec 5: the Jump List runs FlowShield.exe --start-sprint or
    --start-sprint=<templateId>, handed over at startup or through the
    single-instance pipe. It is a Start nobody pressed on Today, so it must
    reach the same gates as the tray's start (F2, the trial, terms, first run,
    F7's open-apps question), and a template deleted since the list was built
    must start nothing. Comments are stripped, so a call left only in a
    comment can't satisfy these.
    """

    MAIN = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    WINDOW = Path(DESKTOP_DIR) / "MainWindow.xaml.cs"
    APP = Path(DESKTOP_DIR) / "App.xaml.cs"
    PROGRAM = Path(DESKTOP_DIR) / "Program.cs"
    SERVICE = Path(DESKTOP_DIR) / "Services" / "JumpListService.cs"
    ARG = Path(DESKTOP_DIR) / "Models" / "StartSprintArg.cs"

    @staticmethod
    def code(path: Path) -> str:
        return "\n".join(line.split("//")[0] for line in path.read_text(encoding="utf-8").splitlines())

    @staticmethod
    def member(code: str, signature: str) -> str:
        """One member's body, from its signature to the brace that closes it."""
        start = code.index(signature)
        depth = 0
        for index in range(code.index("{", start), len(code)):
            depth += {"{": 1, "}": -1}.get(code[index], 0)
            if depth == 0:
                return code[start:index + 1]
        raise AssertionError(f"no end to {signature}")

    def handler(self) -> str:
        return self.member(self.code(self.MAIN), "public void HandleStartSprintArg(IEnumerable<string> args)")

    def test_it_starts_only_through_quick_start_or_start_template(self):
        """
        No template: exactly the tray's "Start sprint (last settings)", which
        is MainWindow's QuickStart() since #270. A template: StartTemplate,
        which goes through StartSprint. Never a start of its own.
        """
        handler = self.handler()
        assert "StartSprintArg.TryFind(args, out var templateId)" in handler
        plain = handler.split("if (templateId is null)", 1)[1].split("return;", 1)[0]
        assert "QuickStartRequested?.Invoke(this, EventArgs.Empty);" in plain
        assert "Today.StartTemplate(template, skipOpenAppsPanel: false)" in handler
        for copied in ("StartCommand", "StartSprint(", "BeginRunning(", "ActiveSprint", "ApplyTemplate("):
            assert copied not in handler, f"HandleStartSprintArg uses {copied}; it must start like the tray"

        window = self.code(self.WINDOW)
        assert "newVm.QuickStartRequested += OnQuickStartRequested;" in window
        assert "oldVm.QuickStartRequested -= OnQuickStartRequested;" in window
        assert re.search(r"private void OnQuickStartRequested\(object\? sender, EventArgs e\)\s*=>\s*QuickStart\(\);",
                         window), "the Jump List's plain start is the tray's QuickStart(), not a copy"
        tray = self.member(window, "private void BuildTrayMenu(")
        assert "(_, _) => QuickStart());" in tray, "the tray's start item is the same QuickStart()"

    def test_a_template_waits_for_the_terms_and_the_welcome_and_brings_f7s_question_forward(self):
        """
        StartTemplate fills in Today (length, shield, profile) before Start's
        gates are asked, so under the terms gate or the welcome it would change
        what they are setting up. The guard sits before the template is even
        looked up: a stale entry after Delete everything must not switch the
        page and toast under the terms gate or the welcome either (review).
        And a start waiting on F7's question is brought forward the way quick
        start and a schedule bring it (#270).
        """
        handler = self.handler()
        guard = handler.index("if (TermsGateVisible || FirstRun.IsVisible)")
        assert guard < handler.index("Settings.FindTemplate("), "the gates come before the lookup"
        assert guard < handler.index("Today.StartTemplate(")
        assert "return;" in handler[guard:handler.index("Settings.FindTemplate(")]
        asked = handler.split("&& Today.RunningAppsPanelVisible)", 1)[1]
        assert "CurrentPage = AppPage.Today;" in asked
        assert "OpenAppsQuestionRaised?.Invoke(this, EventArgs.Empty);" in asked

    def test_a_template_that_is_gone_toasts_and_starts_nothing(self):
        """Review focus 5: a dangling Jump List entry falls back to Today with a calm toast."""
        handler = self.handler()
        assert "var template = Settings.FindTemplate(templateId);" in handler
        missing = handler.split("if (template is null)", 1)[1].split("return;", 1)[0]
        assert "CurrentPage = AppPage.Today;" in missing
        assert 'Toast("That template isn\'t here any more. Pick one on Today.");' in missing
        assert "StartTemplate(" not in missing and "QuickStart" not in missing

    def test_a_template_during_a_sprint_a_break_or_f7s_question_says_so_and_starts_nothing(self):
        """
        StartTemplate returns false while a sprint or a break runs, which left
        a taskbar click with nothing visible (review). A calm toast now says
        why. And with F7's question already up for a Start pressed by hand,
        the entry is refused as a schedule is (OnScheduleAction): the person
        is answering it, and a template would change what they asked for.
        The missing-template toast still comes first.
        """
        handler = self.handler()
        lookup, start = handler.index("var template = Settings.FindTemplate("), handler.index("Today.StartTemplate(")

        running = handler.split("if (IsSprintRunning)", 1)[1].split("return;", 1)[0]
        assert 'Toast("A sprint is already running.");' in running
        on_break = handler.split("if (Today.IsOnBreak)", 1)[1].split("return;", 1)[0]
        assert 'Toast("You\'re on a break. Start now from Today.");' in on_break
        asked = handler.split("if (Today.RunningAppsPanelVisible)", 1)[1].split("return;", 1)[0]
        assert "Log.Info(" in asked and "Toast(" not in asked, "refused quietly, as a schedule is"
        for block in (running, on_break, asked):
            assert "StartTemplate(" not in block and "QuickStart" not in block

        for check in ("if (IsSprintRunning)", "if (Today.IsOnBreak)", "if (Today.RunningAppsPanelVisible)"):
            assert lookup < handler.index(check) < start, f"{check} sits between the lookup and the start"

    def test_a_hand_over_mid_quit_cannot_reach_the_closed_window(self):
        """
        A second launch can arrive down the pipe while Quit is closing the
        window. OnClosing drops every handler a --start-sprint could reach:
        the quick start, F7's question (BringToFront, then Show on a closed
        window) and the start's notification (review).
        """
        closing = self.member(self.code(self.WINDOW), "protected override void OnClosing(CancelEventArgs e)")
        for handler in ("QuickStartRequested -= OnQuickStartRequested;",
                        "OpenAppsQuestionRaised -= OnOpenAppsQuestionRaised;",
                        "NotificationRequested -= OnNotificationRequested;"):
            assert f"currentVm.{handler}" in closing, handler
            assert closing.index(handler) < closing.index("base.OnClosing(e);")

    def test_app_hands_the_argument_over_at_startup_and_from_a_second_launch(self):
        app = self.code(self.APP)
        start = app.index("Instance?.Listen(") + len("Instance?.Listen")
        depth = 0
        for end in range(start, len(app)):
            depth += {"(": 1, ")": -1}.get(app[end], 0)
            if depth == 0:
                break
        listen, after = app[start:end], app[end:]
        assert "ViewModel.HandleStartSprintArg(launchArgs);" in listen, "a launch while FlowShield runs"
        assert "ViewModel.HandleStartSprintArg(args);" in after, "a cold launch from the Jump List"
        assert app.index("window.Show();") < app.index("ViewModel.RebuildJumpList();")
        # #275's retry is for --reset; every other argument, --start-sprint
        # included, goes down the pipe exactly as it came.
        program = self.code(self.PROGRAM)
        assert "SingleInstance.SendToRunningInstance(args)" in program

    def test_the_list_follows_the_templates(self):
        main = self.code(self.MAIN)
        ctor = self.member(main, "public MainViewModel(")
        assert "Schedule.TemplatesChanged += (_, _) => RebuildJumpList();" in ctor
        rebuild = self.member(main, "public void RebuildJumpList()")
        assert "JumpListService.Rebuild(Settings.Templates, exe);" in rebuild

    def test_the_list_is_wpfs_jump_list_and_never_the_registry(self):
        """
        A per-user shell feature: no registry, no admin, and a machine without
        a taskbar (or a shell that refuses) costs the shortcut, never the app.
        """
        service = self.SERVICE.read_text(encoding="utf-8")
        code = self.code(self.SERVICE)
        assert "using System.Windows.Shell;" in code
        assert "new JumpList" in code and "new JumpTask" in code
        # SetJumpList applies the list itself; a second Apply() was one more
        # shell round-trip per template change (review).
        assert "JumpList.SetJumpList(Application.Current, list);" in code
        assert ".Apply();" not in code, "SetJumpList already applies the list"
        for registry in ("Registry", "Microsoft.Win32"):
            assert registry not in service, f"the Jump List must never touch {registry}"
        rebuild = self.member(code, "public static void Rebuild(")
        assert rebuild.index("try") < rebuild.index("new JumpList")
        assert "catch (Exception ex)" in rebuild and "Log.Warn(" in rebuild
        # The argument is written by the class that reads it back.
        assert "Arguments = StartSprintArg.Flag," in code
        assert "StartSprintArg.For(t.Id)" in code

    def test_the_list_leaves_a_trace_and_a_rejected_entry_is_not_silent(self):
        """
        The shell drops an entry it refuses (a path it cannot resolve, a bad
        icon) through JumpItemsRejected, which nothing handled, so an empty
        list on some machine left no trace. Now it is a Warn naming how many
        and why, and a healthy apply logs its entry count, which tier 3 reads
        back (templates + 1).
        """
        rebuild = self.member(self.code(self.SERVICE), "public static void Rebuild(")
        applied = rebuild.index("JumpList.SetJumpList(Application.Current, list);")
        rejected = rebuild.index("list.JumpItemsRejected +=")
        assert rejected < applied, "subscribe before the one apply, or the first rejection is missed"
        handler = rebuild[rejected:applied]
        assert "Log.Warn(" in handler and "e.RejectedItems.Count" in handler and "e.RejectionReasons" in handler
        assert 'Log.Info($"jump list: {list.JumpItems.Count} entries");' in rebuild[applied:]

    def test_an_ampersand_in_a_template_name_is_not_a_mnemonic(self):
        """
        Titles are shell menu text: one & marks a mnemonic and is not drawn,
        so "Maths & Physics" showed as "Maths Physics" (review). The title
        comes from JumpListText, which tier 1 probes; the tooltip stays as typed.
        """
        code = self.code(self.SERVICE)
        assert "Title = JumpListText.Title(t.Name)," in code
        assert 'Description = $"{t.SprintMinutes} minutes at {t.Shield}",' in code
        text = self.code(Path(DESKTOP_DIR) / "Models" / "JumpListText.cs")
        assert 'Replace("&", "&&")' in self.member(text, "public static string Title(")

    def test_the_new_copy_keeps_to_the_house_voice(self):
        """DESIGN_SYSTEM 9: no exclamation marks, and ASCII-only C# literals."""
        texts = [self.handler(), self.SERVICE.read_text(encoding="utf-8"), self.ARG.read_text(encoding="utf-8"),
                 (Path(DESKTOP_DIR) / "Models" / "JumpListText.cs").read_text(encoding="utf-8")]
        for text in texts:
            for literal in re.findall(r'"[^"\n]*"', text):
                assert "!" not in literal, literal
                assert literal.isascii(), literal


# ================================ Delete everything clears the Jump List (#311)

class TestDeleteEverythingClearsTheJumpList:
    """
    #311: the Jump List puts each template's name and length in a file Windows
    keeps in the user profile, outside the encrypted settings. Delete
    everything removed the settings and logs and relaunched with --reset, so
    the old names went only if the relaunch rebuilt the list, and a relaunch
    can fail. Now the deleting process empties the list itself: after the
    delete, before the relaunch, and nothing rebuilds it from the in-memory
    settings before the process ends. Comments are stripped, so a call left
    only in a comment can't satisfy these.
    """

    SETTINGS_VM = Path(DESKTOP_DIR) / "ViewModels" / "SettingsViewModel.cs"
    MAIN = Path(DESKTOP_DIR) / "ViewModels" / "MainViewModel.cs"
    SERVICE = Path(DESKTOP_DIR) / "Services" / "JumpListService.cs"
    PRIVACY = Path(DESKTOP_DIR) / "Services" / "DataPrivacyService.cs"

    code = staticmethod(TestTheJumpListStartsLikeTheTray.code)
    member = staticmethod(TestTheJumpListStartsLikeTheTray.member)

    def test_the_delete_clears_the_list_after_the_files_go_and_before_the_relaunch(self):
        code = self.code(self.SETTINGS_VM)
        assert "JumpListService.Clear();" in code, "Delete everything must clear the Jump List"
        delete = self.member(code, "private async Task DeleteEverythingAsync()")
        assert delete.count("JumpListService.Clear();") == 1
        deleted = delete.index("await DataPrivacyService.DeleteEverythingAsync(")
        cleared = delete.index("JumpListService.Clear();")
        relaunch = delete.index("_main.RestartToFirstRun();")
        assert deleted < cleared < relaunch, "clear after the files are gone and before the relaunch"
        # Not in the catch: a failed delete keeps its list and says so, as before.
        failed = delete.index("catch (Exception ex)")
        assert delete.index("return;", failed) < cleared, "the clear runs only once the delete succeeded"
        # The WPF call stays out of the service that removes the files.
        privacy = self.code(self.PRIVACY)
        assert "System.Windows" not in privacy and "JumpList" not in privacy

    def test_the_clear_applies_an_empty_list_and_catches_its_own_failure(self):
        code = self.code(self.SERVICE)
        assert "public static void Clear()" in code, "JumpListService.Clear() is missing"
        clear = self.member(code, "public static void Clear()")
        applied = clear.index("JumpList.SetJumpList(Application.Current,")
        assert clear.index("try") < applied
        assert "new JumpList" in clear and "JumpItems" not in clear and "JumpTask" not in clear, \
            "the cleared list is empty"
        assert 'Log.Info("jump list: cleared");' in clear[applied:]
        failed = clear[clear.index("catch (Exception ex)"):]
        assert "Log.Warn(" in failed and "throw" not in clear, "a failure costs the shortcut, never the delete"

    def test_nothing_rebuilds_the_old_list_before_the_process_ends(self):
        """
        The list is rebuilt at startup and on TemplatesChanged, both through
        RebuildJumpList, which now refuses once local data is deleted.
        RestartToFirstRun sets that flag before asking WPF to shut down, and
        the clear and the relaunch run in one turn of the UI thread.
        """
        main = self.code(self.MAIN)
        rebuild = self.member(main, "public void RebuildJumpList()")
        assert "if (SkipSaveOnExit) return;" in rebuild, "no rebuild from the deleted settings"
        assert rebuild.index("if (SkipSaveOnExit) return;") < rebuild.index("JumpListService.Rebuild(")
        restart = self.member(main, "public void RestartToFirstRun()")
        assert restart.index("SkipSaveOnExit = true;") < restart.index("Application.Current.Shutdown();")

        # RebuildJumpList is the only way to Rebuild, so its guard covers them all.
        callers = [path.name for path in Path(DESKTOP_DIR).rglob("*.cs")
                   if not {"bin", "obj"} & set(path.relative_to(DESKTOP_DIR).parts)
                   and "JumpListService.Rebuild(" in self.code(path)]
        assert callers == ["MainViewModel.cs"], callers
        assert main.count("JumpListService.Rebuild(") == 1
