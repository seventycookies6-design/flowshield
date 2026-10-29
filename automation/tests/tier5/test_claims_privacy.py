# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: claims privacy."""

from __future__ import annotations
import re
import time
from pathlib import Path
import pytest
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from ._helpers import _PricingFeatureParser, customer_copy_surface_paths



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

    def test_the_privacy_policy_discloses_the_lost_key_lookup(self):
        """
        #287: an address typed into Lost your key is sent to the licence server
        and looked up in Stripe, even if it never bought anything, and an
        unmatched one is logged. The policy must say so.
        """
        server = (self.ROOT / "Server" / "server.js").read_text(encoding="utf-8")
        assert "recoverFromStripe({ email })" in server, "the lookup moved; update this test"

        policy = " ".join(self.LEGAL.read_text(encoding="utf-8").lower().split())
        assert "lost your key" in policy
        assert "looks it up in stripe" in policy
        assert "never bought anything" in policy
        assert "written to the server's log" in policy

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
        policy = " ".join(self.LEGAL.read_text(encoding="utf-8").lower().split())
        subprocessors = {
            "stripe": "payment processing and receipts",
            "render": "hosts the license service",
            "resend": "delivers your license key email",
            "github": "hosts releases and receives update checks",
        }
        for name, role in subprocessors.items():
            assert name in policy, f"{name} processes customer data and must be named"
            assert role in policy, f"{name} must be named with its role: {role}"

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
            "licenseKey": "license key",
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
        """F19's rule: everything Basalt can interrupt with is switchable."""
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
        assert "Any unsaved work in an application Basalt closes may be lost" in legal

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
        included because it regenerates docs/history/FINAL_REPORT.md from its own template.
        """
        root = Path(DESKTOP_DIR).parent
        for name in ("README.md", "docs/history/HANDOFF_PROMPT.md", "docs/history/FINAL_REPORT.md",
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
        # docs/history/FINAL_REPORT.md carries README's qualifier. The checked-in
        # docs/history/FINAL_REPORT.md itself is a record of a past run and is left alone.
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
        assert "Activate license" in branch, \
            "it should tell the buyer how to actually activate Basalt"


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
        for name in ("automation/make_report.py", "docs/history/FINAL_REPORT.md"):
            text = (root / name).read_text(encoding="utf-8")
            assert "momentum analytics" not in text, f"{name} still promises momentum analytics"
            assert "| Sprint length | ≤ 25 min | Any |" not in text, f"{name} says Pro sprints can be any length"


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

# ================= the site says what Basalt doesn't do (F26) and what it
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
        for words in ("license server", "device ID", "user name", "legal.html#privacy"):
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
        assert "$4.99, once, for up to 3 devices" in site
        assert "up to 3 devices" in site

    def test_customer_seat_copy_uses_devices_instead_of_pcs_or_computers(self):
        """A customer must not be told that a licence covers only PCs."""
        stale_seat_copy = re.compile(
            r"(?:\b(?:3|three)|\{\w*limit\w*\})[\s-]+(?:pcs?|computers?)\b|"
            r"\b(?:per|each)[\s-]+(?:pc|computer)\b",
            re.IGNORECASE,
        )
        matches = []
        for path in customer_copy_surface_paths():
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if stale_seat_copy.search(line):
                    matches.append(f"{path}:{line_number}: {line.strip()}")
        assert not matches, "stale PC/computer seat wording reached customer surfaces:\n" + "\n".join(matches)

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
