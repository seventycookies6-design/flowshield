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
        assert "NotificationPolicy.ShouldShow(kind, Settings, IsSprintRunning)" in notify, \
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
        assert 'Title = running ? $"FlowShield — {Vm?.Today.RemainingText}" : "FlowShield";' in update

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
        for words in ("licence server", "device ID", "user name", "privacy.html"):
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
        paragraphs = above.count("<p")
        assert paragraphs <= 3, (
            f"{paragraphs} paragraphs above the capture; keep it to the lede, the "
            "copy confirmation and the note")


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
             "Views/SettingsView.xaml")
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
        faq = html.split('id="faq"', 1)[1]
        assert html.count('class="chevron"') == 7, "expected one chevron icon per FAQ item"
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

    def test_glyph_file_exists_and_merges_tokens(self):
        assert self.GLYPHS.is_file(), (
            "DesktopApp/Styles/ShieldGlyphs.xaml is missing -- the shield glyphs must be "
            "built once, in a shared resource dictionary (UI-SPEC.md A4)")
        xml = self.GLYPHS.read_text(encoding="utf-8")
        assert '<ResourceDictionary Source="Tokens.xaml"/>' in xml, (
            "ShieldGlyphs.xaml must merge Tokens.xaml itself -- a StaticResource brush "
            "lookup only sees its own dictionary's merged dictionaries, not its "
            "sibling dictionaries in Theme.xaml")

    def test_theme_merges_the_glyph_dictionary(self):
        theme = self.THEME.read_text(encoding="utf-8")
        assert '<ResourceDictionary Source="ShieldGlyphs.xaml"/>' in theme, (
            "Theme.xaml must merge ShieldGlyphs.xaml or the glyph resources are never "
            "loaded into the app")

    def test_exactly_three_levels_are_defined(self):
        xml = self.GLYPHS.read_text(encoding="utf-8")
        for key in ("ShieldGlyphSoft", "ShieldGlyphFirm", "ShieldGlyphSealed"):
            assert xml.count(f'x:Key="{key}"') == 1, (
                f"expected exactly one {key} resource")

    def test_soft_is_outline_and_one_bar_in_text_muted(self):
        """§6: Soft is a shield outline with one bar, in text-muted (InkDim), never primary."""
        block = self._resource_block(self.GLYPHS.read_text(encoding="utf-8"), "ShieldGlyphSoft")
        assert "{StaticResource InkDim}" in block
        assert "{StaticResource Primary}" not in block, (
            "Soft must never use primary -- strength escalates through fill and bar "
            "count, not colour (§6)")
        assert block.count("M8.5,") == 1, "Soft should draw exactly one bar"

    def test_firm_is_outline_and_two_bars_in_primary(self):
        block = self._resource_block(self.GLYPHS.read_text(encoding="utf-8"), "ShieldGlyphFirm")
        assert block.count("{StaticResource Primary}") >= 1
        assert "{StaticResource InkDim}" not in block
        assert block.count("M8.5,") == 2, "Firm should draw exactly two bars"

    def test_sealed_is_solid_primary_with_three_bars_and_a_lock_notch_in_primary_ink(self):
        block = self._resource_block(self.GLYPHS.read_text(encoding="utf-8"), "ShieldGlyphSealed")
        assert 'Brush="{StaticResource Primary}"' in block, (
            "Sealed's shield shape must be a solid primary fill, not an outline")
        assert block.count("{StaticResource PrimaryInk}") >= 2, (
            "Sealed's bars and lock notch must be drawn in primary-ink for contrast "
            "against the solid fill")
        assert block.count("M8.5,") == 3, "Sealed should draw exactly three bars"

    def test_shield_chips_reference_the_shared_glyph_resource(self):
        xml = self.TODAY_VIEW.read_text(encoding="utf-8")
        for key in ("ShieldGlyphSoft", "ShieldGlyphFirm", "ShieldGlyphSealed"):
            assert f'Source="{{StaticResource {key}}}"' in xml, (
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
