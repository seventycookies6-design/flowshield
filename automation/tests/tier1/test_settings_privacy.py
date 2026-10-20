# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 1: settings privacy."""

from __future__ import annotations
from pathlib import Path
import pytest
from config import SERVER_DIR
from ._helpers import first_run_shows, notification_allowed, terms_accepted



class TestNotificationPolicy:
    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "Notifications.cs"

    @pytest.mark.parametrize("kind,kwargs,allowed", [
        ("SprintStarted", {}, True),
        ("SprintComplete", {"sprint_running": True}, True),      # about the sprint itself
        ("FiveMinutesLeft", {"sprint_running": True}, True),
        ("TrialEnding", {}, True),
        ("TrialEnding", {"sprint_running": True}, False),        # never sell during a sprint (F20)
        ("SprintStarted", {"kind_on": False}, False),
        ("SprintComplete", {"master": False}, False),
    ])
    def test_when_flowshield_may_interrupt(self, kind, kwargs, allowed):
        assert notification_allowed(kind, **kwargs) is allowed

    def test_the_mirror_matches_the_app(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        interrupts = source.split("public static bool InterruptsFocus(")[1].split(";")[0]
        assert "NotificationKind.TrialEnding" in interrupts
        for other in ("SprintStarted", "SprintComplete", "FiveMinutesLeft", "SprintInterrupted"):
            assert other not in interrupts
        should = source.split("public static bool ShouldShow(")[1].split(";")[0]
        assert "settings.IsNotificationOn(kind)" in should
        assert "!(sprintRunning && InterruptsFocus(kind))" in should

    def test_notifications_are_on_until_switched_off(self):
        settings = (Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs").read_text(encoding="utf-8")
        assert "public bool NotificationsEnabled { get; set; } = true;" in settings
        is_on = settings.split("public bool IsNotificationOn(")[1].split(";")[0]
        assert "!NotificationKinds.TryGetValue(kind.ToString(), out var on) || on" in is_on

    @pytest.mark.parametrize("minutes,left,text", [
        (25, 25 * 60, "25"), (25, 90, "2"), (25, 61, "2"), (25, 59, "1"), (25, 0, "0"),
        (180, 180 * 60, "3h"), (90, 90 * 60, "90"),
    ])
    def test_the_tray_icon_shows_minutes_left(self, minutes, left, text):
        # Mirror of NotificationPolicy.TrayIconText: minutes, rounded up; hours past 99.
        import math

        got = "0" if left <= 0 else (
            f"{math.ceil(left / 60) // 60}h" if math.ceil(left / 60) >= 100 else str(math.ceil(left / 60)))
        assert got == text

    def test_five_minutes_left_is_skipped_on_a_short_sprint(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        too_short = source.split("public static bool TooShortForEndingSoon(")[1].split(";")[0]
        assert "EndingSoon.TotalMinutes + 1" in too_short, "a 5-minute sprint would notify the moment it starts"


class TestTermsAcceptance:
    """The agreement that makes the liability limit worth something (legal 2.2-2.4)."""

    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "LegalTerms.cs"
    LEGAL = Path(SERVER_DIR).parent / "Website" / "legal.html"

    def version(self) -> str:
        source = self.SOURCE.read_text(encoding="utf-8")
        return source.split('public const string Version = "')[1].split('"')[0]

    @pytest.mark.parametrize("recorded,accepted", [
        ("1.0 (17 September 2026)", True),
        ("", False),
        ("0.9 (1 January 2026)", False),      # older wording: ask again
        ("1.0 (17 september 2026)", False),   # exact match only
    ])
    def test_only_the_current_version_counts(self, recorded, accepted):
        assert terms_accepted(recorded, "1.0 (17 September 2026)") is accepted

    def test_the_gate_states_the_risk_that_matters(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        warning = source.split("DataLossWarning =")[1].split(";")[0].lower()
        assert "closes programs" in warning and "unsaved work" in warning, \
            "the one thing that can cost a customer must be on the gate, not only in the terms"
        assert "system processes" in warning

    def test_the_recorded_version_is_on_the_legal_page(self):
        # A recorded acceptance is meaningless if nobody can tell which wording
        # it refers to, so the page carries the same version string.
        assert f"Version {self.version()}" in self.LEGAL.read_text(encoding="utf-8")

    def test_the_terms_cover_what_1_0_10_added(self):
        # 1.1 of the terms (#309): a schedule can start a sprint, and so close
        # apps, without anyone pressing Start; Soft closes an app only when
        # Close is chosen; template names reach Windows' own Jump List file.
        # Each is on the page everyone agrees to, or the recorded acceptance
        # doesn't cover it.
        page = " ".join(self.LEGAL.read_text(encoding="utf-8").split())
        terms = page.split('id="terms"')[1].split('id="privacy"')[0]
        privacy = page.split('id="privacy"')[1].split('id="refunds"')[0]
        assert "start a focus session by itself" in terms
        assert "Ask five minutes before" in terms
        assert "offered, never started by itself" in terms
        assert "unless you choose Close on its notice" in terms
        assert "templates, schedules and preferences" in privacy
        assert "Jump List" in privacy and "outside Basalt's encrypted settings" in privacy
        assert self.version() != "1.0 (17 September 2026)", \
            "these changes are material: the version must move so everyone is asked again"

    def test_accepting_records_the_version_and_the_time(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        accept = source.split("public static void Accept(")[1].split("\n    }")[0]
        assert "TermsAcceptedVersion = Version" in accept
        assert "TermsAcceptedUtc" in accept

    def test_checkout_asks_the_buyer_to_agree(self):
        # custom_text cannot be used once Managed Payments is enabled (Stripe
        # rejects the whole session with it present, #192), so the checkbox no
        # longer carries its own custom message per request — it links to the
        # terms-of-service URL configured on the Stripe account itself
        # (Dashboard -> Settings -> Checkout), which points at
        # legal.html#terms. That page carries the "closes programs / unsaved
        # work" warning in full (checked against the legal page in tier 5,
        # and stated up front by the app's own first-run terms gate above).
        server = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")
        assert "consent_collection: { terms_of_service: 'required' }" in server
        assert "custom_text:" not in server, \
            "custom_text cannot be used once Managed Payments is enabled"


class TestFirstRunPolicy:
    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "FirstRunPolicy.cs"

    @pytest.mark.parametrize("kwargs,shows", [
        ({}, True),                                   # a brand-new install
        ({"completed": True}, False),                 # finished or skipped before
        ({"blocked": 2}, False),                      # an existing user after an update
        ({"sessions": 5}, False),
        ({"active": True}, False),
        ({"has_access": False}, False),               # never over the lock screen
        ({"running": True}, False),                   # never over a resumed sprint
        ({"skip_flag": True}, False),
    ])
    def test_who_sees_it(self, kwargs, shows):
        assert first_run_shows(**kwargs) is shows

    def test_the_mirror_matches_the_app(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        should = source.split("public static bool ShouldShow(")[1].split(";")[0]
        for part in ("!SkipForTests", "!settings.FirstRunCompleted", "!IsExistingUser(settings)",
                     "hasAccess", "!sprintRunning"):
            assert part in should
        existing = source.split("public static bool IsExistingUser(")[1].split(";")[0]
        assert "BlockedApps.Count > 0" in existing and "Sessions.Count > 0" in existing
        assert "ActiveSprint is not null" in existing

    def test_browsers_are_never_preticked(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        preticked = source.split("public static bool PreTicked(")[1].split(";")[0]
        assert "PickerSource.Suggested" in preticked and "ExePath is not null" in preticked
        assert '!entry.Group.Equals("Browsers"' in preticked

    def test_firm_is_the_default_and_lengths_are_25_and_45(self):
        vm = (Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "FirstRunViewModel.cs").read_text(encoding="utf-8")
        assert "private ShieldLevel _shield = ShieldLevel.Firm;" in vm
        assert "SprintLengths = { 25, 45 }" in self.SOURCE.read_text(encoding="utf-8")


# ================================================= #202 settings save race

class TestSettingsSaveDoesNotRaceItsMutators:
    """
    #202: SettingsService.Save serialized the live, shared AppSettings
    instance while another thread could still be mutating its List<>s
    (TodayViewModel.EndSprint's Sessions.Add racing a background license
    refresh's Save). The _gate lock only ever serialized writers against each
    other, never a reader (Save) against a mutator.

    No dotnet test project exists in this repo (see CLAUDE.md — the automation
    suite is the test suite), and the actual failure mode is a genuine data
    race that only reproduces under real thread contention, not something a
    Python harness can drive against C# source. These pin the two guards the
    fix relies on by reading the source directly, the same "unit-by-source"
    approach the rest of this file uses for pure C# logic.
    """

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    SETTINGS_SERVICE = DESKTOP / "Services" / "SettingsService.cs"
    LICENSE_SERVICE = DESKTOP / "Services" / "LicenseService.cs"
    APP_SETTINGS = DESKTOP / "Models" / "AppSettings.cs"

    def test_clone_is_a_deep_copy_not_a_shallow_one(self):
        """
        Save's snapshot-before-the-slow-part guard (below) is only a guard if
        Clone() actually deep-copies the object — a MemberwiseClone would
        still hand Save a shared reference to the same Sessions/BlockedApps/
        ActiveSprint/SkipDatesLocal/NotificationKinds instances the live
        settings object points at, so a concurrent structural mutation of any
        of them would still be visible to (and could still crash) the
        serializer, exactly as if Clone() were never called.

        Pinned as the JSON round-trip Clone() actually uses: serializing the
        whole graph and deserializing a fresh instance is what guarantees
        every nested list and dictionary comes back as a new instance, not a
        shared reference. MemberwiseClone would pass every other test in this
        file untouched, since none of them execute the C# — there's no dotnet
        test project here (CLAUDE.md) — so this has to pin it by source.
        """
        source = self.APP_SETTINGS.read_text(encoding="utf-8")
        clone = source.split("public AppSettings Clone()")[1].split("\n    }")[0]

        assert "MemberwiseClone" not in clone, (
            "MemberwiseClone copies reference fields (Sessions, BlockedApps, "
            "ActiveSprint, SkipDatesLocal, NotificationKinds, ...) rather than "
            "the objects they point at, so it would not actually snapshot "
            "anything Save is protecting against"
        )
        assert "JsonSerializer.Serialize(this)" in clone, \
            "Clone must serialize the whole object graph, not a subset of fields"
        assert "JsonSerializer.Deserialize<AppSettings>(" in clone, \
            "Clone must deserialize into a brand-new AppSettings, so every " \
            "nested collection is a new instance rather than a shared reference"

    def test_save_snapshots_before_the_slow_part(self):
        """
        Save must clone the live settings object into a private copy before
        the DPAPI encrypt and file write — the only part of Save that can't
        finish instantly, and so the only part where a concurrent mutation on
        another thread would matter.
        """
        source = self.SETTINGS_SERVICE.read_text(encoding="utf-8")
        save = source.split("public void Save(AppSettings settings)")[1].split(
            "\n    public ")[0]

        clone_line = save.index("settings.Clone()")
        lock_line = save.index("lock (_gate)")
        assert clone_line < lock_line, (
            "Save must snapshot the live settings object with Clone() before "
            "entering the slow, locked section — cloning inside the lock "
            "still races a mutator that never takes _gate"
        )

        # The bytes that get encrypted and written must come from the
        # snapshot, not from `settings` directly.
        after_clone = save[clone_line:]
        assert "JsonSerializer.Serialize(snapshot, JsonOpts)" in after_clone
        assert "JsonSerializer.Serialize(settings, JsonOpts)" not in save, (
            "the live settings object must never be handed to the serializer "
            "directly; something else may be mutating it"
        )

    def test_save_still_writes_atomically(self):
        """The temp-file-then-replace guarantee from #202's neighbouring fix
        must survive: snapshotting must not have replaced it with a direct
        write."""
        source = self.SETTINGS_SERVICE.read_text(encoding="utf-8")
        assert 'var temp = SettingsPath + ".tmp";' in source
        assert "File.Replace(temp, SettingsPath, null)" in source

    def test_save_coalesces_an_unchanged_write(self):
        """
        A save that would write exactly what's already on disk should not
        pay for a fresh DPAPI encrypt and file replace every time — cheap
        insurance against the flood of near-identical saves a heartbeat and a
        background refresh both produce.
        """
        source = self.SETTINGS_SERVICE.read_text(encoding="utf-8")
        save = source.split("public void Save(AppSettings settings)")[1].split(
            "\n    public ")[0]
        assert "_lastWrittenPlain" in save
        assert "SequenceEqual(_lastWrittenPlain)" in save
        assert "return;" in save.split("SequenceEqual(_lastWrittenPlain)")[1].split(
            "\n\n")[0], "an unchanged save must return before touching disk"

    def test_reset_clears_the_coalesce_cache(self):
        """
        Otherwise Reset() (used by --reset and F23's delete-everything) could
        leave a stale cached copy that makes the very next Save() think
        nothing changed, and skip writing the file Reset() just deleted.
        """
        source = self.SETTINGS_SERVICE.read_text(encoding="utf-8")
        reset = source.split("public void Reset()")[1].split("\n    }")[0]
        assert "_lastWrittenPlain = null" in reset

    def test_license_service_never_saves_settings_directly(self):
        """
        Every mutate-then-save in LicenseService must go through
        MutateAndSave, which marshals onto the UI thread before touching the
        shared settings object — the same thread TodayViewModel and friends
        already own it from. A direct `_settings.Save(settings)` call here
        would be exactly the #202 regression: a background verdict racing a
        foreground mutation.
        """
        source = self.LICENSE_SERVICE.read_text(encoding="utf-8")
        method = source.split("private void MutateAndSave(")[1].split("\n    }")[0]
        outside = source.replace(method, "")
        assert "_settings.Save(settings)" not in outside, (
            "every direct call to _settings.Save must live inside "
            "MutateAndSave, not scattered across ValidateAsync/RefreshAsync/"
            "DeactivateAsync"
        )
        assert source.count("_settings.Save(settings)") == 2, (
            "MutateAndSave's two branches (marshalled and already-on-thread) "
            "are the only places settings should be saved directly"
        )
        assert "MutateAndSave(settings," in source

    def test_mutate_and_save_marshals_onto_the_ui_thread(self):
        source = self.LICENSE_SERVICE.read_text(encoding="utf-8")
        method = source.split("private void MutateAndSave(")[1].split("\n    }")[0]
        assert "Application.Current?.Dispatcher" in method
        assert "dispatcher.Invoke(" in method
        assert "dispatcher.CheckAccess()" in method, (
            "must not double-marshal (or deadlock) when already on the UI thread"
        )

    def test_every_licence_verdict_goes_through_mutate_and_save(self):
        """
        ValidateAsync's activation branch, RefreshAsync's downgrade, and
        DeactivateAsync must each route their settings mutation through the
        one race-safe helper, not touch settings fields and Save
        independently.
        """
        source = self.LICENSE_SERVICE.read_text(encoding="utf-8")
        validate = source.split("public async Task<LicenseResult> ValidateAsync(")[1].split(
            "public async Task RefreshAsync(")[0]
        refresh = source.split("public async Task RefreshAsync(")[1].split(
            "public async Task DeactivateAsync(")[0]
        deactivate = source.split("public async Task DeactivateAsync(")[1]

        for name, block in (("ValidateAsync", validate), ("RefreshAsync", refresh),
                             ("DeactivateAsync", deactivate)):
            assert "MutateAndSave(settings," in block, \
                f"{name} must save through MutateAndSave"


# ==================================== F23 — Your data export and delete

class TestDataPrivacyExport:
    """
    Mirrors DesktopApp/Services/DataPrivacyService.cs Export(): the shape of
    the JSON a customer gets from Settings -> Your data -> Export everything.

    A regression test, unit-by-source like the journal export tests above:
    it reads the C# rather than running it, and fails if the export method
    ever starts writing the licence key back out.
    """

    SERVICE = Path(SERVER_DIR).parent / "DesktopApp" / "Services" / "DataPrivacyService.cs"

    def _export_method(self) -> str:
        source = self.SERVICE.read_text(encoding="utf-8")
        return source.split("public static void Export(")[1].split(
            "public static async Task DeleteEverythingAsync(")[0]

    def test_the_licence_key_is_never_in_the_export_payload(self):
        method = self._export_method()
        assert "LicenseKey" not in method, \
            "settings.LicenseKey must never be written into the export payload"

    def test_the_export_shape_covers_everything_local(self):
        """Every category the app and site claim is stored locally must be in
        the export, or the export is not actually "everything"."""
        method = self._export_method()
        for field in ("blockedApps", "sessions", "momentumScore", "currentStreak",
                      "dailyGoal", "sleepBlocking", "licence", "studyTemplates", "sprintSchedules",
                      "earnedMilestones"):
            assert f"{field} =" in method, f"the export is missing {field!r}"

    def test_the_licence_section_only_has_non_secret_fields(self):
        method = self._export_method()
        licence_block = method.split("licence = new")[1].split("};")[0]
        assert "email" in licence_block and "status" in licence_block and "isPro" in licence_block
        assert "LicenseKey" not in licence_block

    def test_the_export_only_writes_where_the_user_chose(self):
        method = self._export_method()
        assert "File.WriteAllText(path" in method
        assert "GetTempPath" not in method and "Upload" not in method, \
            "nothing may leave the machine; the privacy policy says so"

    def test_delete_everything_frees_the_seat_and_wipes_settings(self):
        source = self.SERVICE.read_text(encoding="utf-8")
        delete_method = source.split("DeleteEverythingAsync(")[-1]
        assert "DeactivateAsync" in delete_method, \
            "a licensed device's seat must be released before local data is wiped"
        assert "settingsService.Reset()" in delete_method


class TestYourDataSettingsCard:
    """Settings -> Your data (F23) exposes the ids the export/delete tests
    above, and the automation suite below, rely on."""

    XAML = Path(SERVER_DIR).parent / "DesktopApp" / "Views" / "SettingsView.xaml"
    VM = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "SettingsViewModel.cs"

    def test_the_card_has_export_and_delete_controls(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        for automation_id in ("WhatLeavesText", "ExportDataButton", "DeleteEverythingButton",
                              "DataStatusText"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml

    def test_delete_everything_uses_the_destructive_style(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        button = xaml.split('AutomationProperties.AutomationId="DeleteEverythingButton"')[0][-500:]
        assert "BtnDanger" in button

    def test_the_viewmodel_confirms_before_deleting(self):
        vm = self.VM.read_text(encoding="utf-8")
        method = vm.split("private async Task DeleteEverythingAsync()")[1].split("\n    }")[0]
        assert "ConfirmDeleteDialog" in method and "ShowDialog()" in method
        assert "RestartToFirstRun()" in method
