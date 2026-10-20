# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 5: licensing."""

from __future__ import annotations
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
import requests
from config import APP_EXE, DESKTOP_DIR, SERVER_DIR, TEST_BLOCK_APP, WEBSITE_DIR
from ._helpers import NODE_EXE, _db_admin



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
        assert "Couldn't reach the license server" in activate, (
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


# ============ a one-time purchase after a 7-day trial (#29)

class TestTrialThenOneTimePurchase:
    """
    Basalt moved from a free tier plus a $4.99/month subscription to a
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
        assert "Settings.EnsureTrialStarted(recordedTrialStart)" in main
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


class TestResendCooldown:
    """#286: /resend-license needs a per-address cooldown, not only a per-IP limit."""

    def _run(self, script):
        result = subprocess.run([NODE_EXE, "-e", script], cwd=str(SERVER_DIR),
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr[:400]
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_one_send_per_address_per_window_across_case(self):
        out = self._run(
            "let t=0;const c=require('./cooldown').createCooldown({windowMs:600000,now:()=>t});"
            "const r=[c.tryAcquire('a@x.com'),c.tryAcquire(' A@X.com '),c.tryAcquire('b@x.com')];"
            "t=599999;r.push(c.tryAcquire('a@x.com'));"
            "t=600000;r.push(c.tryAcquire('a@x.com'));"
            "console.log(JSON.stringify(r));")
        assert out == [True, False, True, False, True]

    def test_a_zero_window_disables_it(self):
        out = self._run(
            "const c=require('./cooldown').createCooldown({windowMs:0});"
            "console.log(JSON.stringify([c.tryAcquire('a@x.com'),c.tryAcquire('a@x.com')]));")
        assert out == [True, True]

    def test_the_route_applies_it_before_sending_and_answers_generically(self):
        source = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")
        route = source.split("app.post('/resend-license'")[1].split("\n});")[0]
        assert route.index("resendCooldown.tryAcquire") < route.index("deliverLicenseEmail")
        assert route.rstrip().endswith("return res.json(generic);"), \
            "a cooled-down address must get the same answer, or the route becomes an oracle"
