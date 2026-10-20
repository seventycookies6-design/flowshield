# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 1: licensing."""

from __future__ import annotations
import json
from datetime import date, timedelta
from datetime import date
from pathlib import Path
import pytest
from config import SERVER_DIR
from ._helpers import TRIAL_DAYS, activation_key, maybe_notify_trial_ending, node_eval, timeout_for_attempt, trial_active, trial_days_left, wait_message_for



# ======================================================= license key format

class TestLicenseKeyFormat:
    """Five checks on the key generator and its checksum."""

    def test_generated_key_matches_the_documented_shape(self):
        out = node_eval(
            "const k=require('./licensekey');"
            "console.log(JSON.stringify({key:k.generate()}))"
        )
        key = out["key"]
        assert key.startswith("FS-"), key
        assert len(key.split("-")) == 5, key
        assert all(len(part) == 4 for part in key.split("-")[1:]), key

    def test_generated_keys_validate(self):
        out = node_eval(
            "const k=require('./licensekey');"
            "const keys=Array.from({length:200},()=>k.generate());"
            "console.log(JSON.stringify({allValid:keys.every(k.isWellFormed),"
            "unique:new Set(keys).size}))"
        )
        assert out["allValid"] is True
        assert out["unique"] == 200, "generator produced duplicates"

    def test_checksum_rejects_every_single_character_typo(self):
        """
        Exhaustive: for 20 keys, every position × every other alphabet symbol.

        A weaker version of this test (one position, one substitution) passed
        against a checksum that had blind spots at positions whose weight shared
        a factor with 32. Sampling one case is not enough here.
        """
        out = node_eval(
            "const k=require('./licensekey');"
            "const alpha='0123456789ABCDEFGHJKMNPQRSTVWXYZ';"
            "let checked=0; const escaped=[];"
            "for (let n=0;n<20;n++){"
            "  const key=k.generate();"
            "  const body=key.replace(/-/g,'').slice(2);"
            "  for (let i=0;i<body.length;i++){"
            "    for (const c of alpha){"
            "      if (c===body[i]) continue;"
            "      const m=body.slice(0,i)+c+body.slice(i+1);"
            "      const bad='FS-'+m.match(/.{1,4}/g).join('-');"
            "      checked++;"
            "      if (k.isWellFormed(bad)) escaped.push({pos:i, from:body[i], to:c});"
            "    }"
            "  }"
            "}"
            "console.log(JSON.stringify({checked, escaped:escaped.slice(0,10),"
            " escapedCount:escaped.length}))"
        )
        assert out["checked"] > 9000, f"only checked {out['checked']} mutations"
        assert out["escapedCount"] == 0, (
            f"{out['escapedCount']} single-character typos passed validation, "
            f"e.g. {out['escaped']}"
        )

    def test_normalisation_tolerates_sloppy_input(self):
        out = node_eval(
            "const k=require('./licensekey');"
            "const key=k.generate();"
            "const messy='  '+key.toLowerCase().replace(/-/g,' - ')+'  ';"
            "console.log(JSON.stringify({"
            "  lower:k.isWellFormed(key.toLowerCase()),"
            "  spaced:k.isWellFormed(key.replace(/-/g,' -')),"
            "  normalised:k.normalize(messy).replace(/-/g,'')===key.replace(/-/g,'')}))"
        )
        assert out["lower"] is True, "lower-case keys should validate"
        assert out["normalised"] is True

    @pytest.mark.parametrize("bad", [
        "", "FS", "FS-", "not-a-key",
        "FS-IIII-IIII-IIII-IIII",     # I is excluded from the alphabet
        "FS-LLLL-OOOO-UUUU-IIII",     # so are L, O and U
        "FS-1234-1234-1234",          # too few groups
        "FS-1234-1234-1234-1234-1234",  # too many groups
        "FS-123-1234-1234-12345",     # wrong group lengths
        "XX-ABCD-ABCD-ABCD-ABCD",     # wrong prefix
        "FS-AB!D-ABCD-ABCD-ABCD",     # punctuation
    ])
    def test_structurally_invalid_keys_are_rejected(self, bad):
        out = node_eval(
            "const k=require('./licensekey');"
            f"console.log(JSON.stringify({{valid:k.isWellFormed({json.dumps(bad)})}}))"
        )
        assert out["valid"] is False, f"{bad!r} should not validate"

    def test_a_key_with_the_right_shape_but_a_wrong_checksum_is_rejected(self):
        """
        Derived, not hardcoded.

        A fixed string like FS-ZZZZ-ZZZZ-ZZZZ-ZZZZ is a poor negative fixture:
        roughly one in 32 such strings is a checksum-valid key by chance, so the
        test would silently start asserting the wrong thing whenever the
        checksum changes. Mutating a real key is always a genuine failure case.
        """
        out = node_eval(
            "const k=require('./licensekey');"
            "const key=k.generate();"
            "const body=key.replace(/-/g,'').slice(2);"
            "const alpha='0123456789ABCDEFGHJKMNPQRSTVWXYZ';"
            "const other=alpha[(alpha.indexOf(body[14])+1)%32];"
            "const m=body.slice(0,14)+other;"
            "const bad='FS-'+m.match(/.{1,4}/g).join('-');"
            "console.log(JSON.stringify({good:k.isWellFormed(key),bad:k.isWellFormed(bad),"
            " sample:bad}))"
        )
        assert out["good"] is True
        assert out["bad"] is False, f"{out['sample']} passed with a corrupted checksum"


class TestFreeTrial:
    """Seven days with everything unlocked, then locked until Basalt is bought."""

    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"

    def test_the_trial_length_matches_the_app(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert f"TrialDays = {TRIAL_DAYS}" in source

    def test_the_free_tier_is_gone(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "FreeBlockedAppLimit" not in source and "FreeMaxSprintMinutes" not in source

    def test_access_is_a_purchase_or_a_running_trial(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "HasAccessAt(DateTime nowUtc) => IsPro || IsTrialActiveAt(nowUtc)" in source

    @pytest.mark.parametrize("start_days_ago,active", [
        (None, False),        # never started
        (0, True),            # first launch
        (6.9, True),          # last hours of day 7
        (7, False),           # exactly seven days
        (30, False),
        (-0.5, True),         # clock slightly behind the recorded start
        (-2, False),          # clock wound back to stretch the trial
    ])
    def test_trial_window(self, start_days_ago, active):
        assert trial_active(start_days_ago) is active

    @pytest.mark.parametrize("start_days_ago,days_left", [
        (0, 7), (0.5, 7), (1, 6), (6.2, 1), (6.99, 1), (7, 0),
    ])
    def test_days_left_rounds_up(self, start_days_ago, days_left):
        assert trial_days_left(start_days_ago) == days_left

    @pytest.mark.parametrize("bought,start_days_ago,has_access", [
        (False, 0, True), (False, 10, False), (True, 10, True), (True, None, True),
    ])
    def test_a_purchase_outlasts_the_trial(self, bought, start_days_ago, has_access):
        assert (bought or trial_active(start_days_ago)) is has_access


class TestTrialEndingNotice:
    """
    The only day Basalt ever asks about the trial before it ends: one
    notice, on the last day (TrialDaysLeft == 1, i.e. "day 6" of a 7-day
    trial), sent at most once and never during a sprint.
    """

    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "MainViewModel.cs"

    @pytest.mark.parametrize("start_days_ago,expect_days_left,expect_notice", [
        (0, 7, False),      # day 0: plenty of trial left
        (5, 2, False),      # day 5: two days left, still quiet
        (6, 1, True),       # day 6: "1 day left" — the one notice
        (6.9, 1, True),     # still day 6 in the small hours
    ])
    def test_the_notice_only_fires_on_the_last_day(self, start_days_ago, expect_days_left, expect_notice):
        days_left = trial_days_left(start_days_ago)
        assert days_left == expect_days_left
        shown, _ = maybe_notify_trial_ending(
            is_trial=trial_active(start_days_ago), trial_days_left=days_left,
            last_notified_date=None, today=date(2026, 1, 1))
        assert shown is expect_notice

    def test_it_is_sent_at_most_once(self):
        today = date(2026, 1, 1)
        shown_first, notified = maybe_notify_trial_ending(
            is_trial=True, trial_days_left=1, last_notified_date=None, today=today)
        assert shown_first is True
        assert notified == today

        # Checked again later the same day (e.g. the next access-timer tick):
        # the flag it just set must stop a second notice.
        shown_again, notified_again = maybe_notify_trial_ending(
            is_trial=True, trial_days_left=1, last_notified_date=notified, today=today)
        assert shown_again is False
        assert notified_again == today

    def test_a_sprint_delays_it_without_marking_it_sent(self):
        today = date(2026, 1, 1)
        shown, notified = maybe_notify_trial_ending(
            is_trial=True, trial_days_left=1, last_notified_date=None, today=today,
            sprint_running=True)
        assert shown is False
        assert notified is None, "a notice skipped for a running sprint is still owed afterwards"

        # The next check, sprint finished, delivers the notice that was owed.
        shown_after, notified_after = maybe_notify_trial_ending(
            is_trial=True, trial_days_left=1, last_notified_date=notified, today=today)
        assert shown_after is True
        assert notified_after == today

    def test_the_flag_persists_so_it_is_never_sent_a_second_trial(self):
        """Once IsTrial goes false the trial cannot restart, so the persisted
        TrialEndingNotifiedLocal date is enough to make the notice a
        once-ever event, not just once-per-day."""
        assert trial_active(8) is False  # the trial is long over
        shown, _ = maybe_notify_trial_ending(
            is_trial=trial_active(8), trial_days_left=0,
            last_notified_date=date(2025, 12, 20), today=date(2026, 1, 1))
        assert shown is False

    def test_the_mirror_matches_the_app(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        method = source.split("public void MaybeNotifyTrialEnding()")[1].split("\n    }")[0]
        assert "!IsTrial || TrialDaysLeft > 1" in method, "must only ever fire on the last day"
        assert "TrialEndingNotifiedLocal?.Date == today" in method, "must not repeat the same day"
        assert "Settings.TrialEndingNotifiedLocal = today;" in method, "must persist that it was sent"
        # It must go through Notify() — which applies the sprint guard — and
        # only record the send if Notify() actually delivered it.
        assert method.index("if (!Notify(") < method.index("TrialEndingNotifiedLocal = today")


# ============================================================= rate limiter

class TestRateLimiter:
    """Server/ratelimit.js: slows guessing of keys and addresses (#21)."""

    def run(self, body: str) -> dict:
        return node_eval(
            "const {createLimiter}=require('./ratelimit');let t=0;"
            "const L=createLimiter({limit:3,windowMs:60000,now:()=>t});"
            + body)

    def test_allows_up_to_the_limit_then_refuses(self):
        out = self.run(
            "const r=[];for(let i=0;i<4;i++)r.push(L.check('validate','203.0.113.9').allowed);"
            "console.log(JSON.stringify({r}));")
        assert out["r"] == [True, True, True, False]

    def test_the_window_resets(self):
        out = self.run(
            "for(let i=0;i<4;i++)L.check('validate','203.0.113.9');"
            "t=60000;console.log(JSON.stringify({ok:L.check('validate','203.0.113.9').allowed}));")
        assert out["ok"] is True

    def test_routes_and_addresses_are_counted_separately(self):
        out = self.run(
            "for(let i=0;i<4;i++)L.check('validate','203.0.113.9');"
            "console.log(JSON.stringify({route:L.check('devices','203.0.113.9').allowed,"
            "ip:L.check('validate','198.51.100.7').allowed}));")
        assert out == {"route": True, "ip": True}

    def test_refusal_says_when_to_retry(self):
        out = self.run(
            "for(let i=0;i<3;i++)L.check('validate','203.0.113.9');t=45000;"
            "console.log(JSON.stringify(L.check('validate','203.0.113.9')));")
        assert out == {"allowed": False, "retryAfterSeconds": 15}

    def test_loopback_is_exempt_and_zero_disables(self):
        out = self.run(
            "const a=[];for(let i=0;i<10;i++)a.push(L.check('validate','::1').allowed);"
            "const Z=createLimiter({limit:0});const b=[];for(let i=0;i<10;i++)b.push(Z.check('v','203.0.113.9').allowed);"
            "console.log(JSON.stringify({a:a.every(Boolean),b:b.every(Boolean)}));")
        assert out == {"a": True, "b": True}


class TestActivationLinkParsing:
    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Services" / "DeepLink.cs"

    @pytest.mark.parametrize("link,key", [
        ("flowshield://activate?key=FS-ABCD-EFGH-JKMN-PQR5", "FS-ABCD-EFGH-JKMN-PQR5"),
        ("flowshield://activate/?key=fs-abcd-efgh-jkmn-pqr5", "FS-ABCD-EFGH-JKMN-PQR5"),
        ("FLOWSHIELD://Activate?key=FS-ABCD-EFGH-JKMN-PQR5", "FS-ABCD-EFGH-JKMN-PQR5"),
        ("flowshield://activate?key=FS%2DABCD%2DEFGH%2DJKMN%2DPQR5", "FS-ABCD-EFGH-JKMN-PQR5"),
        ("flowshield://activate", None),
        ("flowshield://activate?key=", None),
        ("flowshield://activate?key=FS-ABCD-EFGH-JKMN-PQRI", None),     # I isn't in the alphabet
        ("flowshield://activate?key=FS-ABCD-EFGH-JKMN", None),
        ("flowshield://settings?key=FS-ABCD-EFGH-JKMN-PQR5", None),
        ("https://activate?key=FS-ABCD-EFGH-JKMN-PQR5", None),
        ("flowshield://activate?key=FS-ABCD-EFGH-JKMN-PQR5;calc", None),
    ])
    def test_only_activation_links_with_a_key_shaped_key(self, link, key):
        assert activation_key(link) == key

    def test_the_app_uses_the_same_alphabet_as_the_server(self):
        server = (Path(SERVER_DIR) / "licensekey.js").read_text(encoding="utf-8")
        assert "const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';" in server
        assert "[0-9A-HJKMNP-TV-Z]{4}" in self.SOURCE.read_text(encoding="utf-8")


class TestLicenseWaitCopy:
    """
    Pure helper (DesktopApp/Services/LicenseWaitCopy.cs) behind the honest
    waiting UI: the copy ladder shown while activation retries, and the
    backoff schedule the retries follow. No network, no app — this class
    mirrors its logic and cross-checks the constants against the source.
    """

    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Services" / "LicenseWaitCopy.cs"

    @pytest.mark.parametrize("elapsed,expected", [
        (0.0, "Contacting the license server…"),
        (7.9, "Contacting the license server…"),
        (8.0, "The server is waking up. This can take up to a minute."),
        (60.0, "The server is waking up. This can take up to a minute."),
    ])
    def test_message_ladder(self, elapsed, expected):
        assert wait_message_for(elapsed) == expected

    def test_message_never_says_invalid_for_a_wait(self):
        for elapsed in (0.0, 3.0, 8.0, 30.0, 74.0):
            message = wait_message_for(elapsed)
            assert "invalid" not in message.lower()
            assert "not activated" not in message.lower()

    @pytest.mark.parametrize("attempt,expected", [(1, 35.0), (2, 15.0), (3, 15.0)])
    def test_timeout_schedule(self, attempt, expected):
        assert timeout_for_attempt(attempt) == expected

    def test_total_budget_is_around_75_seconds(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "35.0" in source and "15.0" in source

        # first attempt + two retries, each with a short delay first
        total = timeout_for_attempt(1) + 2.0 + timeout_for_attempt(2) + 5.0 + timeout_for_attempt(3)
        assert 60.0 <= total <= 75.0, (
            f"retry budget is {total}s; roadmap 5.2 asks for backoff up to "
            "~75s total"
        )

    def test_retry_delays_match_the_source(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        delays = source.split("RetryDelaysSeconds = new[] {")[1].split("}")[0]
        assert "2.0" in delays and "5.0" in delays


# ========================= Roadmap 5.7 — see and manage your devices (token)

class TestDeviceToken:
    """
    Server/devicetoken.js: the opaque, per-(licence, device) token the
    /devices list hands back instead of the raw hashed device id, so
    Settings' "Your devices" list can target one *other* device for release
    without the server ever disclosing another machine's real identifier.

    Pure crypto, no database and no HTTP — split into its own module
    specifically so it is testable without starting the server (server.js
    calls app.listen() unconditionally at require time).
    """

    def _token(self, license_key: str, device_id: str) -> str:
        out = node_eval(
            "const {deviceToken}=require('./devicetoken');"
            f"console.log(JSON.stringify({{t:deviceToken({license_key!r},{device_id!r})}}))"
        )
        return out["t"]

    def test_deterministic_for_the_same_pair(self):
        a = self._token("FS-AAAA-BBBB-CCCC-DDDD", "device-1")
        b = self._token("FS-AAAA-BBBB-CCCC-DDDD", "device-1")
        assert a == b

    def test_distinct_for_different_devices(self):
        a = self._token("FS-AAAA-BBBB-CCCC-DDDD", "device-1")
        b = self._token("FS-AAAA-BBBB-CCCC-DDDD", "device-2")
        assert a != b

    def test_distinct_for_different_licences(self):
        """The same physical device on two licences must not share a token —
        that would let one customer's list fingerprint another's device."""
        a = self._token("FS-AAAA-BBBB-CCCC-DDDD", "device-1")
        b = self._token("FS-EEEE-FFFF-GGGG-HHHH", "device-1")
        assert a != b

    def test_never_equal_to_the_raw_device_id(self):
        device_id = "a" * 32
        token = self._token("FS-AAAA-BBBB-CCCC-DDDD", device_id)
        assert token != device_id
        assert device_id not in token

    def test_is_not_reversible_to_the_device_id(self):
        """Sanity check: it's a hash digest, not the id itself or a trivial
        transform of it (e.g. a prefix or suffix)."""
        device_id = "b" * 32
        token = self._token("FS-AAAA-BBBB-CCCC-DDDD", device_id)
        assert not device_id.startswith(token)
        assert not token.startswith(device_id[:16])

    # ---- keyed with a server secret (#234)

    def _keyed(self, secret: str, production: bool) -> dict:
        return node_eval(
            "const {createDeviceTokens}=require('./devicetoken');"
            f"const t=createDeviceTokens({{secret:{secret!r},production:{str(production).lower()}}});"
            "console.log(JSON.stringify({configured:t.configured,source:t.source,"
            "t:t.token('FS-AAAA-BBBB-CCCC-DDDD','device-1')}))"
        )

    def test_is_an_hmac_of_the_pair_under_the_server_secret(self):
        """Someone holding a raw device id and the licence key can no longer
        mint a token without the server's secret."""
        import hashlib
        import hmac

        secret = "s" * 40
        out = self._keyed(secret, production=True)
        expected = hmac.new(
            secret.encode(), b"devicetoken|FS-AAAA-BBBB-CCCC-DDDD|device-1", hashlib.sha256
        ).hexdigest()[:16]
        plain = hashlib.sha256(b"devicetoken|FS-AAAA-BBBB-CCCC-DDDD|device-1").hexdigest()[:16]
        assert out == {"configured": True, "source": "env", "t": expected}
        assert out["t"] != plain, "still the unkeyed hash anyone could compute"

    def test_a_different_secret_gives_a_different_token(self):
        assert self._keyed("a" * 40, True)["t"] != self._keyed("b" * 40, True)["t"]

    def test_production_without_a_secret_fails_closed(self):
        out = self._keyed("", production=True)
        assert out == {"configured": False, "source": "missing", "t": None}

    def test_production_refuses_a_short_secret(self):
        out = self._keyed("too-short", production=True)
        assert out["configured"] is False and out["t"] is None

    def test_development_falls_back_to_a_fixed_secret(self):
        out = self._keyed("", production=False)
        assert out["configured"] is True and out["source"] == "development"
        assert out["t"] == self._keyed("", production=False)["t"]
