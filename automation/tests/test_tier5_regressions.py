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
        panel = xaml.split('AutomationProperties.AutomationId="DailyGoalPanel"', 1)
        assert len(panel) == 2, "the daily goal panel must be present"
        before = panel[0][-400:]
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
