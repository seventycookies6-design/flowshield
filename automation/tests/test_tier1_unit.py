"""
Tier 1 — unit tests.

Pure logic, no app and no network. These exercise the same rules the desktop app
and the server enforce, using the Node modules directly (via a short-lived node
process) and Python re-implementations where the rule is shared.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import date, timedelta
from datetime import date
from pathlib import Path

import pytest

from config import SERVER_DIR

NODE = r"C:\Program Files\nodejs\node.exe"
NODE_EXE = NODE if Path(NODE).exists() else "node"


def node_eval(script: str) -> dict:
    """Run a snippet inside the server package and parse its JSON output."""
    result = subprocess.run(
        [NODE_EXE, "-e", script],
        cwd=str(SERVER_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise AssertionError(f"node failed: {result.stderr[:500]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


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


# ============================================================ sleep window

def within_sleep_window(now_minutes: int, start: int, end: int) -> bool:
    """Mirror of AppBlockerService.IsWithinSleepWindow (minutes since midnight)."""
    if start <= end:
        return start <= now_minutes < end
    return now_minutes >= start or now_minutes < end


class TestSleepWindow:
    def test_same_day_window_includes_its_middle(self):
        assert within_sleep_window(13 * 60, 9 * 60, 17 * 60) is True

    def test_same_day_window_excludes_outside(self):
        assert within_sleep_window(8 * 60, 9 * 60, 17 * 60) is False
        assert within_sleep_window(18 * 60, 9 * 60, 17 * 60) is False

    def test_window_crossing_midnight_includes_late_evening(self):
        assert within_sleep_window(23 * 60, 22 * 60, 6 * 60) is True

    def test_window_crossing_midnight_includes_early_morning(self):
        assert within_sleep_window(2 * 60, 22 * 60, 6 * 60) is True

    def test_window_crossing_midnight_excludes_daytime(self):
        assert within_sleep_window(12 * 60, 22 * 60, 6 * 60) is False

    def test_boundaries_are_half_open(self):
        # Start is inclusive, end exclusive — so a window can't double-count.
        assert within_sleep_window(22 * 60, 22 * 60, 6 * 60) is True
        assert within_sleep_window(6 * 60, 22 * 60, 6 * 60) is False


# ======================================================== time parsing rule

def parse_time(text: str) -> tuple[int, int] | None:
    """Mirror of SleepBlockingViewModel.TryParse for the formats it accepts."""
    import re

    text = (text or "").strip().lower()
    if not text:
        return None

    match = re.fullmatch(r"(\d{1,2}):(\d{2})\s*(am|pm)?", text)
    if not match:
        match = re.fullmatch(r"(\d{2})(\d{2})", text)
        if match:
            hour, minute, meridiem = int(match.group(1)), int(match.group(2)), None
            return (hour, minute) if hour < 24 and minute < 60 else None
        match = re.fullmatch(r"(\d{1,2})\s*(am|pm)", text)
        if not match:
            return None
        hour, minute, meridiem = int(match.group(1)), 0, match.group(2)
    else:
        hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(3)

    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    return (hour, minute) if hour < 24 and minute < 60 else None


class TestTimeParsing:
    @pytest.mark.parametrize("text,expected", [
        ("22:00", (22, 0)),
        ("06:45", (6, 45)),
        ("9:05", (9, 5)),
        ("2200", (22, 0)),
        ("10pm", (22, 0)),
        ("12am", (0, 0)),
    ])
    def test_accepted_formats(self, text, expected):
        assert parse_time(text) == expected

    @pytest.mark.parametrize("text", ["", "   ", "banana", "25:00", "12:99", "::"])
    def test_rejected_formats(self, text):
        assert parse_time(text) is None


# =================================================== blocked-app normalising

def normalize_process_name(value: str) -> str:
    """Mirror of BlockedAppsViewModel.NormalizeProcessName."""
    text = (value or "").strip().strip('"')
    if "\\" in text or "/" in text:
        text = text.replace("/", "\\").split("\\")[-1]
    if text.lower().endswith(".exe"):
        text = text[:-4]
    return text.strip()


class TestProcessNameNormalisation:
    @pytest.mark.parametrize("raw,expected", [
        ("slack", "slack"),
        ("Slack.exe", "Slack"),
        (r"C:\Users\me\AppData\Local\slack\slack.exe", "slack"),
        ('  "steam.EXE"  ', "steam"),
        ("C:/Program Files/App/thing.exe", "thing"),
    ])
    def test_normalisation(self, raw, expected):
        assert normalize_process_name(raw) == expected

    def test_protected_processes_list_covers_the_shell_and_the_app_itself(self):
        source = (Path(SERVER_DIR).parent / "DesktopApp" / "Services"
                  / "AppBlockerService.cs").read_text(encoding="utf-8")

        # Take the initialiser body only — splitting on the identifier alone
        # lands inside the doc comment above it.
        marker = "HashSet<string> CriticalProcesses"
        start = source.index(marker)
        block = source[source.index("{", start):source.index("};", start)].lower()

        for critical in ("explorer", "csrss", "winlogon", "lsass",
                         "flowshield", "powershell", "services", "lsass"):
            assert f'"{critical}"' in block, f"{critical} must never be terminable"


# ============================================================== free trial

TRIAL_DAYS = 7


def trial_active(start_days_ago: float | None, *, now_days: float = 0.0) -> bool:
    """Mirror of AppSettings.IsTrialActiveAt, in days relative to now."""
    if start_days_ago is None:
        return False
    start = now_days - start_days_ago
    return now_days >= start - 1 and now_days < start + TRIAL_DAYS


def trial_days_left(start_days_ago: float) -> int:
    """Mirror of AppSettings.TrialDaysLeftAt."""
    import math
    if not trial_active(start_days_ago):
        return 0
    return min(max(math.ceil(TRIAL_DAYS - start_days_ago), 1), TRIAL_DAYS)


class TestFreeTrial:
    """Seven days with everything unlocked, then locked until FlowShield is bought."""

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


# ==================================== a trial that never nags (F20, #9) =====

def maybe_notify_trial_ending(*, is_trial: bool, trial_days_left: int,
                               last_notified_date: date | None, today: date,
                               sprint_running: bool = False) -> tuple[bool, date | None]:
    """
    Mirror of MainViewModel.MaybeNotifyTrialEnding, folding in the sprint guard
    that Notify() applies through NotificationPolicy.ShouldShow. Returns
    (shown, the new value of TrialEndingNotifiedLocal).
    """
    if not is_trial or trial_days_left > 1:
        return False, last_notified_date
    if last_notified_date == today:
        return False, last_notified_date
    if sprint_running:
        # Suppressed by the sprint guard. Crucially, this must NOT be recorded
        # as sent — the whole point is that it is still owed afterwards.
        return False, last_notified_date
    return True, today


class TestTrialEndingNotice:
    """
    The only day FlowShield ever asks about the trial before it ends: one
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


# ================================================================== momentum

def apply_momentum(score: float, completed: bool, planned_minutes: int) -> float:
    """Mirror of TodayViewModel.ApplyMomentum."""
    if completed:
        weight = min(max(planned_minutes / 25.0, 0.5), 3.0)
        return round(score + 10 * weight, 1)
    return round(max(0.0, score * 0.85 - 2), 1)


class TestMomentum:
    def test_completing_a_standard_sprint_adds_ten(self):
        assert apply_momentum(0, True, 25) == 10.0

    def test_longer_sprints_are_worth_more_but_are_capped(self):
        assert apply_momentum(0, True, 50) == 20.0
        assert apply_momentum(0, True, 600) == 30.0, "weight should cap at 3x"

    def test_short_sprints_have_a_floor(self):
        assert apply_momentum(0, True, 1) == 5.0, "weight should floor at 0.5x"

    def test_abandoning_decays_rather_than_resets(self):
        after = apply_momentum(100, False, 25)
        assert 0 < after < 100, f"expected decay, got {after}"
        assert after == 83.0

    def test_momentum_never_goes_negative(self):
        assert apply_momentum(1, False, 25) == 0.0
        assert apply_momentum(0, False, 25) == 0.0

    def test_decay_is_recoverable_in_a_few_sprints(self):
        score = apply_momentum(50, False, 25)
        for _ in range(2):
            score = apply_momentum(score, True, 25)
        assert score > 50, "two good sprints should more than undo one lapse"


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


# ============================================================== doc steward

class TestDocSteward:
    """
    The doc steward lets a free model propose documentation edits, so its safety
    comes from these checks, not from the model: allowlisted Markdown only, text
    that occurs exactly once, and evidence that really exists in another file.
    No network — the provider call is faked.
    """

    @pytest.fixture
    def steward(self):
        import importlib
        import sys as _sys
        tool_dir = str(Path(SERVER_DIR).parent / "tools" / "doc_steward")
        if tool_dir not in _sys.path:
            _sys.path.insert(0, tool_dir)
        return importlib.import_module("steward")

    @pytest.fixture
    def repo(self, tmp_path):
        files = {
            "README.md": "Run `npm start` in Server.\nShield III locks until the timer ends.\n",
            "SELLING.md": "Price is $4.99.\n",
            "Server/package.json": '{"scripts": {"start": "node server.js"}}\n',
            "DesktopApp/App.xaml.cs": "var locked = \"for the rest of the sprint\";\n",
        }
        for path, text in files.items():
            (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / path).write_text(text, encoding="utf-8")
        return tmp_path, set(files)

    @staticmethod
    def reader(root):
        return lambda p: (root / p).read_text(encoding="utf-8")

    @staticmethod
    def edit(**overrides):
        edit = {
            "file": "README.md",
            "find": "locks until the timer ends",
            "replace": "locks for the rest of the sprint",
            "reason": "matches the app",
            "evidence": [{"file": "DesktopApp/App.xaml.cs", "quote": "for the rest of the sprint"}],
        }
        edit.update(overrides)
        return edit

    def test_a_well_evidenced_doc_edit_is_accepted_and_written(self, steward, repo):
        root, tracked = repo
        result = steward.apply({"edits": [self.edit()]}, steward.load_config(), tracked, root, dry_run=False)
        assert len(result.applied) == 1 and not result.rejected
        assert "locks for the rest of the sprint" in (root / "README.md").read_text(encoding="utf-8")

    def test_dry_run_writes_nothing(self, steward, repo):
        root, tracked = repo
        before = (root / "README.md").read_text(encoding="utf-8")
        steward.apply({"edits": [self.edit()]}, steward.load_config(), tracked, root, dry_run=True)
        assert (root / "README.md").read_text(encoding="utf-8") == before

    @pytest.mark.parametrize("overrides, why", [
        ({"file": "Server/package.json", "find": "server.js", "replace": "evil.js"}, "not an editable doc"),
        ({"file": "DesktopApp/App.xaml.cs", "find": "rest", "replace": "x"}, "not an editable doc"),
        ({"file": "../README.md"}, "unsafe path"),
        ({"file": "C:/Windows/win.ini"}, "unsafe path"),
        ({"find": "not in the file at all"}, "occurs 0 times"),
        ({"evidence": []}, "no evidence"),
        ({"evidence": [{"file": "DesktopApp/App.xaml.cs", "quote": "a quote the model made up"}]}, "not found"),
        ({"evidence": [{"file": "README.md", "quote": "Run `npm start` in Server."}]}, "at least one other"),
        ({"evidence": [{"file": "secrets/.stripe_keys.json", "quote": "anything at all here"}]}, "not a tracked file"),
        ({"evidence": [{"file": "DesktopApp/App.xaml.cs", "quote": "rest"}]}, "too short"),
        ({"replace": "locks until the timer ends"}, "identical"),
    ])
    def test_unsafe_or_unproven_edits_are_rejected(self, steward, repo, overrides, why):
        root, tracked = repo
        verdict = steward.validate_edit(self.edit(**overrides), steward.load_config(), tracked, self.reader(root))
        assert not verdict.ok and why in verdict.reason, verdict.reason

    def test_a_generated_snapshot_is_not_evidence_on_its_own(self, steward, repo):
        """Reproduces the first live run: it 'corrected' 200 tests to the report's stale 196."""
        root, tracked = repo
        (root / "HANDOFF_PROMPT.md").write_text("| Tests | 200 tests. |\n", encoding="utf-8")
        (root / "FINAL_REPORT.md").write_text("Duration: 1661.6s · 196 tests collected\n", encoding="utf-8")
        tracked = tracked | {"HANDOFF_PROMPT.md", "FINAL_REPORT.md"}
        stale = self.edit(file="HANDOFF_PROMPT.md", find="200 tests", replace="196 tests",
                          evidence=[{"file": "FINAL_REPORT.md", "quote": "196 tests collected"}])
        config = steward.load_config()
        assert "FINAL_REPORT.md" in config["historical"]
        verdict = steward.validate_edit(stale, config, tracked, self.reader(root))
        assert not verdict.ok and "non-historical" in verdict.reason, verdict.reason

    def test_find_text_must_be_unique(self, steward, repo):
        root, tracked = repo
        (root / "README.md").write_text("same line\nsame line\n", encoding="utf-8")
        verdict = steward.validate_edit(self.edit(find="same line"), steward.load_config(), tracked, self.reader(root))
        assert not verdict.ok and "occurs 2 times" in verdict.reason

    def test_evidence_survives_rewrapping(self, steward, repo):
        root, tracked = repo
        verdict = steward.check_evidence(
            [{"file": "README.md", "quote": "Run `npm start`\n   in Server."}],
            None, tracked, self.reader(root), 12)
        assert verdict.ok, verdict.reason

    def test_config_never_lets_it_edit_code_the_site_or_legal_text(self, steward):
        config = steward.load_config()
        assert config["editable"], "the allowlist is empty"
        assert all(p.endswith(".md") for p in config["editable"]), config["editable"]
        assert not set(config["editable"]) & set(config["report_only"])
        for protected in ("Website/index.html", "Website/legal.html", "FINAL_REPORT.md"):
            assert protected not in config["editable"]

    def test_globs_match_files_at_the_top_of_a_folder(self, steward):
        assert steward.matches_any("DesktopApp/App.xaml.cs", ["DesktopApp/**/*.cs"])
        assert steward.matches_any("DesktopApp/Services/Log.cs", ["DesktopApp/**/*.cs"])
        assert not steward.matches_any("Server/server.js", ["DesktopApp/**/*.cs"])

    def test_json_is_extracted_from_fenced_or_thinking_output(self, steward):
        text = '<think>hmm {not json}</think>Sure:\n```json\n{"edits": [], "reports": []}\n```'
        assert steward.extract_json(text) == {"edits": [], "reports": []}
        assert steward.extract_json('{"edits": []}')["reports"] == []

    def test_providers_fall_back_on_rate_limits_and_bad_output(self, steward, monkeypatch):
        import io
        import urllib.error
        config = steward.load_config()
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
        monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")
        calls = []

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(request, timeout):
            model = json.loads(request.data)["model"]
            calls.append(model)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 429, "rate limited", {}, None)
            if len(calls) == 2:
                return Response(json.dumps({"choices": [{"message": {"content": "no json here"}}]}).encode())
            return Response(json.dumps({"choices": [{"message": {"content": '{"edits": [], "reports": []}'}}]}).encode())

        monkeypatch.setattr(steward.urllib.request, "urlopen", fake_urlopen)
        data, label = steward.ask_model(config, "system", "user", log=lambda *_: None)
        assert data == {"edits": [], "reports": []}
        assert len(calls) == 3 and label.endswith(calls[2])

    def test_missing_keys_are_an_error_not_a_silent_pass(self, steward, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="not set"):
            steward.ask_model(steward.load_config(), "s", "u", log=lambda *_: None)

    def test_guard_flags_anything_but_editable_docs(self, steward, tmp_path):
        def git(*args):
            subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        (tmp_path / "README.md").write_text("a\n", encoding="utf-8")
        (tmp_path / "server.js").write_text("a\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-qm", "base")
        config = steward.load_config()

        (tmp_path / "README.md").write_text("b\n", encoding="utf-8")
        assert steward.guard("HEAD", config, root=tmp_path) == []

        (tmp_path / "server.js").write_text("b\n", encoding="utf-8")
        assert steward.guard("HEAD", config, root=tmp_path) == ["server.js"]


# ===================================================== sprints survive restarts

def resume_decision(started_min_ago: float, planned: int, last_seen_min_ago: float,
                    watched_minutes: float | None = None) -> str:
    """
    Mirror of RunningSprint.Decide, in minutes relative to now.

    watched_minutes is the accumulated WatchedMinutes; None stands for a
    settings file written before that field existed, where Decide falls back to
    the LastSeenUtc-minus-StartedUtc estimate.
    """
    if planned <= 0:
        return "Discard"
    started = -started_min_ago
    ends = started + planned
    if 0 < ends:
        return "Resume"
    watched = watched_minutes if watched_minutes is not None else min(-last_seen_min_ago, ends) - started
    return "RecordCompleted" if watched >= planned * 0.5 else "RecordInterrupted"


class TestSprintResume:
    """F3: what happens to a sprint that was running when FlowShield closed."""

    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"

    def test_the_threshold_matches_the_app(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "CompletedIfWatchedFraction = 0.5" in source

    @pytest.mark.parametrize("started,planned,last_seen,expected", [
        (10, 25, 0.2, "Resume"),              # crashed mid-sprint, relaunched quickly
        (10, 25, 9.5, "Resume"),              # closed almost immediately, still time left
        (24.9, 25, 24, "Resume"),             # seconds left
        (30, 25, 6, "RecordCompleted"),       # ran 24 of 25 minutes, then closed
        (60, 25, 47.5, "RecordCompleted"),    # watched exactly half
        (60, 25, 50, "RecordInterrupted"),    # watched 10 of 25 minutes
        (120, 90, 119, "RecordInterrupted"),  # closed a minute in, reopened much later
        (5, 0, 0, "Discard"),                 # unreadable record
    ])
    def test_decision(self, started, planned, last_seen, expected):
        assert resume_decision(started, planned, last_seen) == expected

    @pytest.mark.parametrize("started,planned,last_seen,watched,expected", [
        # #198: the 60-minute sprint FlowShield watched 2 minutes of, reopened
        # near the end so LastSeenUtc sits a minute before the finish line.
        (65, 60, 6, 2, "RecordInterrupted"),
        # The same timestamps with the app genuinely up the whole time.
        (65, 60, 6, 59, "RecordCompleted"),
        (65, 60, 6, 30, "RecordCompleted"),        # exactly half
        (65, 60, 6, 29.9, "RecordInterrupted"),
    ])
    def test_the_decision_uses_watched_time_not_two_timestamps(
            self, started, planned, last_seen, watched, expected):
        assert resume_decision(started, planned, last_seen, watched) == expected
        assert resume_decision(started, planned, last_seen) == "RecordCompleted", \
            "the old estimate cannot tell these apart; that is the bug"

    def test_a_settings_file_without_the_field_falls_back_to_the_old_estimate(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "public double? WatchedMinutes" in source, \
            "WatchedMinutes must be nullable so pre-existing settings files still load"
        decide = source.split("public SprintResume Decide(")[1].split("}", 1)[0]
        assert "WatchedMinutes ??" in decide, \
            "Decide must prefer WatchedMinutes and fall back when it is null"


# ============================================== ending a sprint early (F2)

GRACE_SECONDS = 120


def end_flow(shield: str, elapsed_seconds: float) -> str:
    """Mirror of EndSprintPolicy.FlowFor with the real timers."""
    if elapsed_seconds < GRACE_SECONDS:
        return "Cancel"
    return {"Soft": "Immediate", "Firm": "Confirm"}.get(shield, "Sealed")


def momentum_after_ending(score: float, shield: str) -> float:
    """Mirror of EndSprintPolicy.MomentumAfterEndingEarly."""
    if shield == "Sealed":
        return round(max(0.0, score * 0.7 - 5), 1)
    return round(max(0.0, score * 0.85 - 2), 1)


def phrase_matches(typed: str) -> bool:
    """Mirror of EndSprintPolicy.PhraseMatches."""
    return " ".join((typed or "").split()).lower() == "end my sprint"


def notification_allowed(kind: str, *, master=True, kind_on=True, sprint_running=False) -> bool:
    """Mirror of NotificationPolicy.ShouldShow."""
    interrupts_focus = {"TrialEnding"}
    return master and kind_on and not (sprint_running and kind in interrupts_focus)


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


class TestAppSuggestions:
    """The picker's built-in suggestions (F8)."""

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"

    @classmethod
    def data(cls) -> dict:
        import json

        return json.loads((cls.DESKTOP / "Data" / "app_suggestions.json").read_text(encoding="utf-8"))

    @classmethod
    def critical(cls) -> set[str]:
        import re

        source = (cls.DESKTOP / "Services" / "AppBlockerService.cs").read_text(encoding="utf-8")
        block = source.split("CriticalProcesses = new(")[1].split("};")[0]
        return {name.lower() for name in re.findall(r'"([^"]+)"', block)}

    def apps(self):
        return [(g, a) for g in self.data()["groups"] for a in g["apps"]]

    def test_the_groups_the_checklist_asks_for(self):
        names = [g["name"] for g in self.data()["groups"]]
        assert names[:2] == ["Chat", "Games & launchers"]
        assert "Browsers" in names

    def test_every_app_has_a_name_and_processes(self):
        for _, app in self.apps():
            assert app["name"].strip(), app
            assert app["processes"], f"{app['name']} has no processes"
            assert isinstance(app["verified"], bool), app["name"]
            for process in app["processes"]:
                assert process == process.strip() and process, app["name"]
                assert not process.lower().endswith(".exe"), f"{process}: no .exe suffix"
                assert "\\" not in process and "/" not in process

    def test_nothing_protected_is_ever_suggested(self):
        critical = self.critical()
        assert "explorer" in critical and "flowshield" in critical   # the parse worked
        for _, app in self.apps():
            for process in app["processes"]:
                assert process.lower() not in critical, f"{app['name']} suggests protected {process}"

    def test_no_process_belongs_to_two_apps(self):
        seen = {}
        for _, app in self.apps():
            for process in app["processes"]:
                assert process.lower() not in seen, f"{process} is in {seen.get(process.lower())} and {app['name']}"
                seen[process.lower()] = app["name"]

    def test_app_names_are_unique(self):
        names = [a["name"].lower() for _, a in self.apps()]
        assert len(names) == len(set(names))

    def test_steam_covers_its_helper(self):
        steam = next(a for _, a in self.apps() if a["name"] == "Steam")
        assert {p.lower() for p in steam["processes"]} == {"steam", "steamwebhelper"}

    def test_xbox_uses_the_names_seen_on_a_clean_install(self):
        # Checked on Miles's VM in #53: the Xbox app runs as XboxPcApp with an XboxPcTray helper.
        # XboxPcAppAdminServer is left out: it runs elevated, and the timid blocker can't close it.
        xbox = next(a for _, a in self.apps() if a["name"] == "Xbox app")
        assert xbox["processes"] == ["XboxPcApp", "XboxPcTray"] and xbox["verified"] is True

    def test_browsers_warn_that_the_whole_browser_closes(self):
        browsers = next(g for g in self.data()["groups"] if g["name"] == "Browsers")
        assert "whole browser" in browsers["note"].lower()
        assert {"chrome", "msedge", "firefox"} <= {p for a in browsers["apps"] for p in a["processes"]}

    def test_the_file_is_built_into_the_app(self):
        project = (self.DESKTOP / "FlowShield.csproj").read_text(encoding="utf-8")
        assert 'EmbeddedResource Include="Data\\app_suggestions.json"' in project
        picker = (self.DESKTOP / "Models" / "AppPicker.cs").read_text(encoding="utf-8")
        assert '"FlowShield.app_suggestions.json"' in picker


def picker_filter(entries: list[dict], query: str) -> list[str]:
    """Mirror of AppPicker.Filter: name-prefix first, then suggested, installed, running."""
    q = query.strip()
    if q.lower().endswith(".exe"):
        q = q[:-4]
    order = {"Suggested": 0, "Installed": 1, "Running": 2}
    ql = q.lower()
    matches = [e for e in entries if not q
               or ql in e["name"].lower() or any(ql in p.lower() for p in e["processes"])]
    matches.sort(key=lambda e: (0 if q and e["name"].lower().startswith(ql) else 1,
                                order[e["source"]],
                                "" if e["source"] == "Suggested" else e["name"].lower()))
    return [e["name"] for e in matches]


class TestPickerSearch:
    ENTRIES = [
        {"name": "Discord", "processes": ["Discord"], "source": "Suggested"},
        {"name": "Steam", "processes": ["steam", "steamwebhelper"], "source": "Suggested"},
        {"name": "Microsoft Edge", "processes": ["msedge"], "source": "Suggested"},
        {"name": "Obsidian", "processes": ["Obsidian"], "source": "Installed"},
        {"name": "Adobe Reader", "processes": ["AcroRd32"], "source": "Running"},
    ]

    @pytest.mark.parametrize("query,expected", [
        ("", ["Discord", "Steam", "Microsoft Edge", "Obsidian", "Adobe Reader"]),
        ("steam", ["Steam"]),
        ("webhelper", ["Steam"]),                  # finds an app by any of its processes
        ("msedge.exe", ["Microsoft Edge"]),
        ("o", ["Obsidian", "Discord", "Microsoft Edge", "Adobe Reader"]),
        ("zzz", []),
    ])
    def test_matches_and_order(self, query, expected):
        assert picker_filter(self.ENTRIES, query) == expected

    def test_the_mirror_matches_the_app(self):
        source = (Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppPicker.cs").read_text(encoding="utf-8")
        filt = source.split("public static List<PickerEntry> Filter(")[1]
        assert "e.Name.StartsWith(q, StringComparison.OrdinalIgnoreCase) ? 0 : 1" in filt
        assert ".ThenBy(e => e.Source)" in filt
        assert "e.Processes.Any(p => p.Contains(q, StringComparison.OrdinalIgnoreCase))" in filt


def first_run_shows(*, completed=False, blocked=0, sessions=0, active=False,
                    has_access=True, running=False, skip_flag=False) -> bool:
    """Mirror of FirstRunPolicy.ShouldShow."""
    existing = blocked > 0 or sessions > 0 or active
    return not skip_flag and not completed and not existing and has_access and not running


def terms_accepted(recorded: str, current: str) -> bool:
    """Mirror of LegalTerms.Accepted: an exact version match, nothing looser."""
    return recorded == current


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


def activation_key(link: str) -> str | None:
    """Mirror of DeepLink.ParseActivationKey."""
    import re
    from urllib.parse import unquote, urlsplit

    try:
        parts = urlsplit(link.strip())
    except ValueError:
        return None
    if parts.scheme.lower() != "flowshield":
        return None
    if (parts.netloc + parts.path).strip("/").lower() != "activate":
        return None
    key = None
    for pair in filter(None, parts.query.split("&")):
        name, _, value = pair.partition("=")
        if _ and name.lower() == "key":
            key = unquote(value).strip().upper()
    shape = r"^FS-(?:[0-9A-HJKMNP-TV-Z]{4}-){3}[0-9A-HJKMNP-TV-Z]{4}$"
    return key if key and re.match(shape, key) else None


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


class TestEndSprintPolicy:
    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "EndSprintPolicy.cs"

    def test_the_owner_decisions_are_in_the_app(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "TimeSpan.FromMinutes(2)" in source, "grace period is 2 minutes"
        assert "TimeSpan.FromSeconds(5)" in source, "Firm confirmation waits 5 s"
        assert "TimeSpan.FromSeconds(30)" in source, "Sealed countdown is 30 s"
        assert 'SealedPhrase = "end my sprint"' in source
        assert "score * 0.7 - 5" in source and "score * 0.85 - 2" in source

    @pytest.mark.parametrize("shield,elapsed,flow", [
        ("Soft", 5, "Cancel"), ("Firm", 119, "Cancel"), ("Sealed", 0, "Cancel"),
        ("Soft", 120, "Immediate"), ("Firm", 121, "Confirm"), ("Sealed", 3600, "Sealed"),
    ])
    def test_flow(self, shield, elapsed, flow):
        assert end_flow(shield, elapsed) == flow

    @pytest.mark.parametrize("score,shield,after", [
        (100, "Soft", 83.0), (100, "Firm", 83.0), (100, "Sealed", 65.0),
        (5, "Sealed", 0.0), (0, "Firm", 0.0),
    ])
    def test_sealed_costs_more(self, score, shield, after):
        assert momentum_after_ending(score, shield) == after

    @pytest.mark.parametrize("typed,ok", [
        ("end my sprint", True), ("  End  My Sprint ", True), ("END MY SPRINT", True),
        ("end my sprint.", False), ("end sprint", False), ("", False),
    ])
    def test_phrase(self, typed, ok):
        assert phrase_matches(typed) is ok


# ================= Roadmap 5.2 — honest waiting while the licence server wakes

def wait_message_for(elapsed_seconds: float) -> str:
    """Mirror of LicenseWaitCopy.MessageFor."""
    waking_up_after = 8.0
    if elapsed_seconds < waking_up_after:
        return "Contacting the licence server…"
    return "The server is waking up. This can take up to a minute."


def timeout_for_attempt(attempt: int) -> float:
    """Mirror of LicenseWaitCopy.TimeoutForAttempt."""
    first, retry = 35.0, 15.0
    return first if attempt <= 1 else retry


class TestLicenseWaitCopy:
    """
    Pure helper (DesktopApp/Services/LicenseWaitCopy.cs) behind the honest
    waiting UI: the copy ladder shown while activation retries, and the
    backoff schedule the retries follow. No network, no app — this class
    mirrors its logic and cross-checks the constants against the source.
    """

    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Services" / "LicenseWaitCopy.cs"

    @pytest.mark.parametrize("elapsed,expected", [
        (0.0, "Contacting the licence server…"),
        (7.9, "Contacting the licence server…"),
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


# ============================================= sprint summary card (F12)

def summary_title(completed: bool, start_momentum: float, end_momentum: float) -> str:
    """Mirror of TodayViewModel.UpdateSummaryCard's title rule."""
    if completed:
        return "Sprint complete"
    delta = round(end_momentum - start_momentum)
    if delta < 0:
        return f"Ended early — momentum −{abs(delta)}. It'll recover."
    return "Ended early. It'll recover."


def distraction_summary(closed: int, nudged: int, total: int) -> str:
    """Mirror of TodayViewModel.DistractionSummary."""
    if closed or nudged:
        nudges = "1 nudge" if nudged == 1 else f"{nudged} nudges"
        return f"{closed} closed · {nudges}"
    if total:
        word = "1 distraction" if total == 1 else f"{total} distractions"
        return f"{word} caught"
    return "No distractions caught"


class TestSprintSummaryCard:
    """The card (F12) reads per-sprint numbers the session must now remember."""
    MODEL = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"
    VIEWMODEL = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "TodayViewModel.cs"

    def test_the_session_remembers_the_split_and_start_momentum(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "public int AppsClosed { get; set; }" in source
        assert "public int NudgesSent { get; set; }" in source
        assert "public double MomentumAtStart { get; set; }" in source

    def test_blocks_are_counted_as_closed_or_nudged(self):
        source = self.VIEWMODEL.read_text(encoding="utf-8")
        assert "public void RecordBlock(bool terminated)" in source
        assert "_closedThisSprint++" in source and "_nudgesThisSprint++" in source
        assert "MomentumAtStart = S.MomentumScore" in source

    def test_the_card_is_fresh_for_every_sprint(self):
        source = self.VIEWMODEL.read_text(encoding="utf-8")
        assert "_closedThisSprint = 0" in source
        assert "_nudgesThisSprint = 0" in source
        assert "UpdateSummaryCard(completed, _current)" in source

    def test_a_saved_sprint_remembers_its_start_momentum(self):
        model = self.MODEL.read_text(encoding="utf-8")
        viewmodel = self.VIEWMODEL.read_text(encoding="utf-8")
        assert model.count("public double MomentumAtStart { get; set; }") == 2, \
            "both FocusSession and RunningSprint must remember the start momentum"
        assert "MomentumAtStart = saved.MomentumAtStart" in viewmodel, \
            "a resumed sprint must keep the momentum it started with"

    @pytest.mark.parametrize("start,end", [(0, 5), (40, 45)])
    def test_completed_title(self, start, end):
        assert summary_title(True, start, end) == "Sprint complete"

    @pytest.mark.parametrize("start,end,title", [
        (10, 0, "Ended early — momentum −10. It'll recover."),
        (2.4, 0, "Ended early — momentum −2. It'll recover."),
        (0.5, 0, "Ended early. It'll recover."),   # a small loss must not print "−0"
        (0, 0, "Ended early. It'll recover."),
    ])
    def test_abandoned_title(self, start, end, title):
        assert summary_title(False, start, end) == title

    @pytest.mark.parametrize("closed,nudged,total,expected", [
        (0, 0, 0, "No distractions caught"),
        (2, 1, 3, "2 closed · 1 nudge"),
        (0, 3, 3, "0 closed · 3 nudges"),
        (1, 0, 1, "1 closed · 0 nudges"),
        (0, 0, 4, "4 distractions caught"),
        (0, 0, 1, "1 distraction caught"),
    ])
    def test_distraction_wording(self, closed, nudged, total, expected):
        assert distraction_summary(closed, nudged, total) == expected


# ================================================== sprint intention (F13)

def journal_prompt_title(intention: str | None) -> str:
    """Mirror of TodayViewModel.JournalPromptTitle."""
    if intention is None or not intention.strip():
        return "What moved?"
    return f"You planned: {intention.strip()}. What moved?"


class TestSprintIntention:
    """F13: the optional one-line intention travels with the sprint it started."""
    MODEL = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"
    VIEWMODEL = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "TodayViewModel.cs"

    def test_the_session_and_the_saved_sprint_both_remember_it(self):
        model = self.MODEL.read_text(encoding="utf-8")
        assert model.count('public string Intention { get; set; } = "";') == 2, \
            "both FocusSession and RunningSprint must carry the intention"

    def test_the_intention_is_captured_when_the_sprint_starts(self):
        viewmodel = self.VIEWMODEL.read_text(encoding="utf-8")
        assert "Intention = intention" in viewmodel
        assert "Intention = saved.Intention" in viewmodel, \
            "a resumed sprint must keep the intention it started with"

    def test_a_sprint_recorded_while_closed_keeps_its_intention_and_momentum(self):
        viewmodel = self.VIEWMODEL.read_text(encoding="utf-8")
        assert viewmodel.count("Intention = saved.Intention") == 2, \
            "the resume path and the recorded-while-closed path must both carry the intention"
        assert viewmodel.count("MomentumAtStart = saved.MomentumAtStart") == 2, \
            "both saved-sprint paths must restore the start momentum"

    def test_the_prompt_repeats_the_intention(self):
        assert journal_prompt_title(None) == "What moved?"
        assert journal_prompt_title("   ") == "What moved?"
        assert journal_prompt_title("finish chapter 3") == \
            "You planned: finish chapter 3. What moved?"


# ============================================ custom sprint lengths (roadmap 2.3)

CUSTOM_MIN = 5
CUSTOM_MAX = 240


def custom_minutes_valid(value: int) -> bool:
    """Mirror of TodayViewModel.IsCustomMinutesValid."""
    return CUSTOM_MIN <= value <= CUSTOM_MAX


class TestCustomSprintLengths:
    SOURCE = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"

    def test_settings_round_trips_last_custom_sprint_minutes(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        assert "public int LastCustomSprintMinutes { get; set; } = 30;" in source

    @pytest.mark.parametrize("minutes", [5, 30, 120, 240])
    def test_validation_accepts_values_in_range(self, minutes):
        assert custom_minutes_valid(minutes) is True

    @pytest.mark.parametrize("minutes", [0, 1, 4, 241, 300, -5])
    def test_validation_rejects_values_outside_range(self, minutes):
        assert custom_minutes_valid(minutes) is False

    def test_the_viewmodel_exposes_the_bounds(self):
        vm = (Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels"
              / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert "CustomMinMinutes = 5" in vm
        assert "CustomMaxMinutes = 240" in vm

    @staticmethod
    def viewmodel_member(name: str) -> str:
        vm = (Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels"
              / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert name in vm, f"TodayViewModel no longer has {name}"
        return vm.split(name, 1)[1].split("\n    }", 1)[0]

    def test_selecting_custom_without_access_opens_the_upgrade_page(self):
        # The radio's two-way IsChecked binding writes the property before any
        # command fires, so the gate has to be in the setter itself. The first
        # draft put it in a command and the locked user got the feature anyway.
        setter = self.viewmodel_member("public bool IsCustomSelected")
        assert "_main.IsLocked" in setter
        assert "_main.OpenUpgradePage()" in setter

    def test_a_valid_custom_value_is_persisted_when_typed(self):
        # The first draft only saved when the Custom radio was clicked, never
        # when the number was typed — so the value was lost on restart.
        apply = self.viewmodel_member("private void ApplyCustomMinutes()")
        assert "S.LastCustomSprintMinutes = _customMinutes" in apply
        assert "_main.SaveSettings()" in apply
        text_setter = self.viewmodel_member("public string CustomMinutesText")
        assert "ApplyCustomMinutes()" in text_setter

    def test_start_is_refused_while_the_custom_value_is_invalid(self):
        vm = (Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels"
              / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert "StartCommand = new RelayCommand(StartSprint, CanStart)" in vm
        can_start = vm.split("private bool CanStart()")[1].split("\n", 1)[0]
        assert "IsCustomMinutesValid" in can_start

    def test_the_input_is_bound_as_text_so_garbage_is_rejected(self):
        # An int-typed binding swallows "abc" as a silent binding error and
        # leaves the previous length in place with no message.
        view = (Path(SERVER_DIR).parent / "DesktopApp" / "Views"
                / "TodayView.xaml").read_text(encoding="utf-8-sig")
        assert "{Binding CustomMinutesText, UpdateSourceTrigger=PropertyChanged}" in view
        assert 'AutomationProperties.AutomationId="CustomMinutesError"' in view


# ====================================================== per-app on/off switch

class TestPerAppSwitch:
    """Roadmap 2.4: each blocked-app row has an on/off switch wired to ToggleApp."""

    XAML = Path(SERVER_DIR).parent / "DesktopApp" / "Views" / "BlockedAppsView.xaml"
    VM = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "BlockedAppsViewModel.cs"

    def test_the_switch_automation_id_is_in_the_xaml(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        assert "AppEnabledSwitch" in xaml, \
            "each blocked-app row must expose an AppEnabledSwitch AutomationId"

    def test_toggle_app_exists_in_the_viewmodel(self):
        vm = self.VM.read_text(encoding="utf-8")
        assert "ToggleApp" in vm, "BlockedAppsViewModel must expose ToggleApp"
        assert "ToggleAppCommand" in vm, "ToggleApp must be reachable as a command"


# ============================================================ daily goal (F15)

GOAL_NONE, GOAL_MINUTES, GOAL_SPRINTS = 0, 1, 2

SKIPS_PER_WEEK = 1
SKIP_WINDOW_DAYS = 7


class Goal:
    """
    Mirror of DesktopApp/Models/DailyGoal.cs.

    Days are plain date objects; sessions are (date, minutes, completed).
    """

    def __init__(self, kind=GOAL_NONE, target=0, sessions=None, skips=None,
                 streak=0, settled=None, met_day=None):
        self.kind = kind
        self.target = target
        self.sessions = sessions or []
        self.skips = set(skips or [])
        self.streak = streak
        self.settled = settled
        self.met_day = met_day

    # ---- rules

    def is_set(self) -> bool:
        return self.kind != GOAL_NONE and self.target > 0

    def progress_on(self, day):
        if not self.is_set():
            return (0, 0)
        todays = [s for s in self.sessions if s[0] == day]
        if self.kind == GOAL_MINUTES:
            done = round(sum(s[1] for s in todays))
        else:
            done = sum(1 for s in todays if s[2])
        return (done, self.target)

    def met_on(self, day) -> bool:
        if not self.is_set():
            return False
        done, target = self.progress_on(day)
        return done >= target

    def had_completed_sprint_on(self, day) -> bool:
        return any(s[0] == day and s[2] for s in self.sessions)

    def is_skipped(self, day) -> bool:
        return day in self.skips

    def skips_used_in_window(self, day) -> int:
        start = day - timedelta(days=SKIP_WINDOW_DAYS - 1)
        return sum(1 for d in self.skips if start <= d <= day)

    def can_skip(self, day) -> bool:
        return (self.is_set() and not self.is_skipped(day)
                and self.skips_used_in_window(day) < SKIPS_PER_WEEK)

    def judge(self, day) -> str:
        if self.is_skipped(day):
            return "skipped"
        counted = self.met_on(day) if self.is_set() else self.had_completed_sprint_on(day)
        return "counted" if counted else "missed"

    def count_day_if_newly_counted(self, day) -> bool:
        """Mirror of DailyGoal.CountDayIfNewlyCounted: once per day, ever."""
        if self.met_day == day:
            return False
        if self.judge(day) != "counted":
            return False
        self.met_day = day
        self.streak += 1
        return True

    def settle(self, today):
        if self.settled is None:
            self.settled = today
            self.count_day_if_newly_counted(today)
            return
        if today <= self.settled:
            if today == self.settled:
                self.count_day_if_newly_counted(today)
            return

        day = self.settled + timedelta(days=1)
        while day <= today:
            verdict = self.judge(day)
            if day == today:
                self.count_day_if_newly_counted(today)
                break
            if verdict == "counted":
                self.streak += 1
            elif verdict == "missed":
                self.streak = 0
            day += timedelta(days=1)
        self.settled = today

    def note_progress(self, today) -> bool:
        """Mirror of DailyGoal.NoteProgress."""
        met_before = self.met_day
        self.settle(today)
        return met_before != today and self.met_day == today


DAY = date(2026, 9, 18)


class TestDailyGoalProgress:
    """F15: progress counts the right thing for each kind of goal."""

    def test_no_goal_means_no_progress_and_no_bar(self):
        g = Goal(sessions=[(DAY, 50, True)])
        assert not g.is_set()
        assert g.progress_on(DAY) == (0, 0)

    def test_a_zero_target_is_not_a_goal(self):
        g = Goal(kind=GOAL_MINUTES, target=0)
        assert not g.is_set(), "a kind without a target must not switch the feature on"

    def test_minutes_count_time_actually_focused(self):
        g = Goal(GOAL_MINUTES, 90, [(DAY, 25, True), (DAY, 20, False)])
        assert g.progress_on(DAY) == (45, 90)

    def test_minutes_include_a_sprint_ended_early(self):
        g = Goal(GOAL_MINUTES, 30, [(DAY, 30, False)])
        assert g.met_on(DAY), "those minutes happened, even though the sprint was abandoned"

    def test_sprints_count_completed_ones_only(self):
        g = Goal(GOAL_SPRINTS, 2, [(DAY, 25, True), (DAY, 25, False)])
        assert g.progress_on(DAY) == (1, 2)
        assert not g.met_on(DAY)

    def test_overshooting_still_counts_as_met(self):
        g = Goal(GOAL_SPRINTS, 2, [(DAY, 25, True)] * 5)
        assert g.met_on(DAY)

    def test_yesterdays_sessions_do_not_count_towards_today(self):
        g = Goal(GOAL_SPRINTS, 1, [(DAY - timedelta(days=1), 25, True)])
        assert not g.met_on(DAY)


class TestDailyGoalSkips:
    """F15: a planned day off, at most once in any seven days."""

    def test_one_skip_is_allowed(self):
        g = Goal(GOAL_SPRINTS, 2)
        assert g.can_skip(DAY)

    def test_a_second_skip_in_the_same_week_is_refused(self):
        g = Goal(GOAL_SPRINTS, 2, skips=[DAY - timedelta(days=2)])
        assert not g.can_skip(DAY), "the allowance is one in seven days"

    def test_the_window_is_rolling_not_a_calendar_week(self):
        g = Goal(GOAL_SPRINTS, 2, skips=[DAY - timedelta(days=6)])
        assert not g.can_skip(DAY), "six days ago is still inside the seven-day window"
        g2 = Goal(GOAL_SPRINTS, 2, skips=[DAY - timedelta(days=7)])
        assert g2.can_skip(DAY), "seven days ago has left the window"

    def test_a_day_cannot_be_skipped_twice(self):
        g = Goal(GOAL_SPRINTS, 2, skips=[DAY])
        assert not g.can_skip(DAY)

    def test_skipping_needs_a_goal(self):
        g = Goal()
        assert not g.can_skip(DAY), "a day off is meaningless without a goal to miss"


class TestDailyGoalStreak:
    """F15: the streak counts days that met the goal, and settles without a sprint."""

    def test_meeting_the_goal_counts_the_day(self):
        g = Goal(GOAL_SPRINTS, 1, [(DAY, 25, True)], settled=DAY - timedelta(days=1), streak=3)
        g.settle(DAY)
        assert g.streak == 4

    def test_falling_short_does_not_count_today_but_does_not_break_it_either(self):
        g = Goal(GOAL_SPRINTS, 3, [(DAY, 25, True)], settled=DAY - timedelta(days=1), streak=3)
        g.settle(DAY)
        assert g.streak == 3, "today is not over; a short day so far must not break the streak"

    def test_a_missed_yesterday_breaks_the_streak_with_no_sprint_to_notice(self):
        g = Goal(GOAL_SPRINTS, 1, [], settled=DAY - timedelta(days=3), streak=9)
        g.settle(DAY)
        assert g.streak == 0, "the whole point of settling: nothing ran on those days"

    def test_a_skipped_day_holds_the_streak_without_adding_to_it(self):
        g = Goal(GOAL_SPRINTS, 1, [], skips=[DAY - timedelta(days=1)],
                 settled=DAY - timedelta(days=2), streak=5)
        g.settle(DAY)
        assert g.streak == 5, "a day off keeps the streak; it is not a day of focus"

    def test_a_skip_wins_over_a_stray_sprint_on_the_same_day(self):
        g = Goal(GOAL_SPRINTS, 1, [(DAY, 25, True)], skips=[DAY])
        assert g.judge(DAY) == "skipped", \
            "otherwise a two-minute sprint on a rest day spends the skip for nothing"

    def test_settling_twice_changes_nothing(self):
        g = Goal(GOAL_SPRINTS, 1, [(DAY, 25, True)], settled=DAY - timedelta(days=1), streak=2)
        g.settle(DAY)
        first = g.streak
        g.settle(DAY)
        assert g.streak == first, "settle runs on launch, at midnight and after every sprint"

    def test_a_clock_moved_backwards_does_not_walk_backwards(self):
        g = Goal(GOAL_SPRINTS, 1, [], settled=DAY, streak=4)
        g.settle(DAY - timedelta(days=3))
        assert g.streak == 4, "a corrected clock must not silently destroy a streak"

    def test_without_a_goal_the_old_rule_still_applies(self):
        g = Goal(sessions=[(DAY, 5, True)], settled=DAY - timedelta(days=1), streak=2)
        g.settle(DAY)
        assert g.streak == 3, "no goal set: any completed sprint counts the day, as before"

    def test_without_a_goal_a_missed_day_still_breaks_it(self):
        g = Goal(sessions=[], settled=DAY - timedelta(days=2), streak=6)
        g.settle(DAY)
        assert g.streak == 0

    def test_a_day_already_settled_can_still_be_counted_when_the_goal_lands(self):
        """
        #194: RefreshStats settles today at launch, before the day's first
        sprint. Meeting the goal afterwards has to count that day.
        """
        g = Goal(GOAL_SPRINTS, 1, [], settled=DAY, streak=5)
        g.settle(DAY)                              # launch: nothing yet
        assert g.streak == 5
        g.sessions.append((DAY, 25, True))         # the day's sprint completes
        g.settle(DAY)
        assert g.streak == 6, "a settled day must still be able to join the streak"

    def test_a_day_is_counted_once_however_many_sprints_it_takes(self):
        g = Goal(GOAL_SPRINTS, 1, [(DAY, 25, True)], settled=DAY, streak=5)
        for _ in range(4):
            g.settle(DAY)
            g.sessions.append((DAY, 25, True))
        assert g.streak == 6, "the streak counts days, not sprints"

    def test_note_progress_reports_the_one_moment_the_goal_lands(self):
        g = Goal(GOAL_SPRINTS, 2, [(DAY, 25, True)], settled=DAY, streak=0)
        assert g.note_progress(DAY) is False, "one of two sprints is not a met goal"
        g.sessions.append((DAY, 25, True))
        assert g.note_progress(DAY) is True, "the toast fires on the sprint that meets it"
        g.sessions.append((DAY, 25, True))
        assert g.note_progress(DAY) is False, "and not again on every later sprint"
        assert g.streak == 1

    def test_a_first_run_takes_the_existing_streak_as_given(self):
        g = Goal(GOAL_SPRINTS, 1, [], streak=11, settled=None)
        g.settle(DAY)
        assert g.streak == 11, "an upgrade must not recompute history that is not in Sessions"
        assert g.settled == DAY


class TestDailyGoalSource:
    """The C# the mirror above stands in for."""

    MODEL = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "DailyGoal.cs"
    SETTINGS = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"
    TODAY_VM = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "TodayViewModel.cs"
    TODAY_XAML = Path(SERVER_DIR).parent / "DesktopApp" / "Views" / "TodayView.xaml"
    SETTINGS_XAML = Path(SERVER_DIR).parent / "DesktopApp" / "Views" / "SettingsView.xaml"

    def test_the_settings_carry_the_goal_and_its_bookkeeping(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        for field in ("DailyGoalKind", "DailyGoalTarget", "StreakSettledDayLocal",
                      "GoalMetDayLocal", "SkipDatesLocal"):
            assert field in source, f"AppSettings must persist {field}"

    def test_the_allowance_is_one_day_off_per_rolling_week(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "SkipsPerWeek = 1" in source
        assert "SkipWindowDays = 7" in source

    def test_the_streak_is_settled_rather_than_nudged(self):
        vm = self.TODAY_VM.read_text(encoding="utf-8")
        assert "DailyGoal.Settle" in vm, "RefreshStats must settle the streak"
        assert "DailyGoal.NoteProgress" in vm, "a finished sprint must settle the day"
        assert "gap switch" not in vm, "the old gap-based streak must be gone"

    def test_the_bar_is_hidden_when_no_goal_is_set(self):
        xaml = self.TODAY_XAML.read_text(encoding="utf-8")
        # The panel carries no id of its own (#134): one on a layout panel is
        # not surfaced to UI Automation. Its children are the handles.
        assert 'AutomationProperties.AutomationId="DailyGoalPanel"' not in xaml
        assert 'AutomationProperties.AutomationId="DailyGoalProgressText"' in xaml
        assert "GoalVisible" in xaml, "the panel must bind its visibility to GoalVisible"

    def test_the_settings_page_offers_both_kinds_and_a_day_off(self):
        xaml = self.SETTINGS_XAML.read_text(encoding="utf-8")
        for automation_id in ("GoalOffRadio", "GoalMinutesRadio", "GoalSprintsRadio",
                              "GoalTargetInput", "SkipTodayButton"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml


# ======================================================= journal export (F17)

def defuse(value: str) -> str:
    """Mirror of JournalExport.Defuse."""
    if not value:
        return value
    return "'" + value if value[0] in "=+-@\t\r" else value


def escape_csv(value: str) -> str:
    """Mirror of JournalExport.EscapeCsv."""
    text = defuse(value or "")
    if not any(c in text for c in ',"\r\n'):
        return text
    return '"' + text.replace('"', '""') + '"'


def escape_markdown(value: str) -> str:
    """Mirror of JournalExport.EscapeMarkdown."""
    text = (value or "").replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return text
    return "\\" + text if text[0] in "#-*>+|`" else text


def suggested_name(start: date, end: date, fmt: str) -> str:
    """Mirror of JournalExport.SuggestedFileName."""
    if end < start:
        start, end = end, start
    ext = "csv" if fmt == "csv" else "md"
    return f"FlowShield journal {start:%Y-%m-%d} to {end:%Y-%m-%d}.{ext}"


class TestJournalExportFormulaInjection:
    """
    F17: a journal line is free text, and a spreadsheet runs a cell that starts
    with =, +, -, @, tab or carriage return. That is the one way an export can
    hurt the person who opens it.
    """

    @pytest.mark.parametrize("payload", [
        "=cmd|'/c calc'!A1",
        "+1+1",
        "-2+3",
        "@SUM(A1:A9)",
        "\tsneaky",
        "\rsneaky",
    ])
    def test_a_formula_is_defused(self, payload):
        assert defuse(payload).startswith("'"), payload

    def test_ordinary_text_is_left_alone(self):
        for safe in ("finished chapter 3", "10am standup", "a - b", "x = y"):
            assert defuse(safe) == safe, safe

    def test_defusing_happens_before_quoting(self):
        # Otherwise the apostrophe lands outside the quotes and does nothing.
        assert escape_csv('=HYPERLINK("http://x","click")').startswith('"\'=')

    def test_an_empty_cell_stays_empty(self):
        assert defuse("") == ""
        assert escape_csv("") == ""


class TestJournalExportCsv:
    """F17: the CSV has to survive journal lines that contain anything."""

    def test_a_comma_is_quoted(self):
        assert escape_csv("read, then wrote") == '"read, then wrote"'

    def test_a_quote_is_doubled(self):
        assert escape_csv('he said "no"') == '"he said ""no"""'

    def test_a_newline_is_quoted_not_stripped(self):
        assert escape_csv("line one\nline two") == '"line one\nline two"'

    def test_plain_text_is_not_quoted(self):
        assert escape_csv("shipped the parser") == "shipped the parser"


class TestJournalExportMarkdown:
    """F17: a journal line must not become document structure."""

    @pytest.mark.parametrize("payload", ["# done", "- fixed it", "* starred",
                                         "> quoted", "| table", "`code"])
    def test_structure_characters_are_escaped(self, payload):
        assert escape_markdown(payload).startswith("\\"), payload

    def test_a_newline_inside_a_journal_line_is_flattened(self):
        assert "\n" not in escape_markdown("first\nsecond")

    def test_ordinary_text_is_untouched(self):
        assert escape_markdown("wrote the export") == "wrote the export"


class TestJournalExportFileName:
    """F17: the file says what it is and what it covers."""

    def test_the_name_carries_both_dates(self):
        assert suggested_name(date(2026, 9, 1), date(2026, 9, 18), "csv") == \
            "FlowShield journal 2026-09-01 to 2026-09-18.csv"

    def test_markdown_gets_the_md_extension(self):
        assert suggested_name(date(2026, 9, 1), date(2026, 9, 18), "md").endswith(".md")

    def test_a_backwards_range_is_put_in_order(self):
        assert suggested_name(date(2026, 9, 18), date(2026, 9, 1), "csv") == \
            "FlowShield journal 2026-09-01 to 2026-09-18.csv"


class TestJournalExportSource:
    """The C# behind the mirrors above."""

    MODEL = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "JournalExport.cs"
    SERVICE = Path(SERVER_DIR).parent / "DesktopApp" / "Services" / "JournalExportService.cs"
    SETTINGS_XAML = Path(SERVER_DIR).parent / "DesktopApp" / "Views" / "SettingsView.xaml"

    def test_the_csv_names_the_outcome_not_just_completed(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert '"ended early"' in source and '"interrupted"' in source, \
            "completed=false alone hides giving up versus losing the sprint to a crash"

    def test_the_csv_is_written_with_a_bom_and_markdown_without(self):
        service = self.SERVICE.read_text(encoding="utf-8")
        assert "encoderShouldEmitUTF8Identifier: true" in service, \
            "Excel needs the BOM or it mangles accents and emoji"
        assert "encoderShouldEmitUTF8Identifier: false" in service, \
            "a BOM shows up as stray characters in Markdown renderers"

    def test_the_csv_uses_crlf(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert '"\\r\\n"' in source, "Excel on Windows expects CRLF"

    def test_dates_are_local_and_say_so(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "date (local)" in source and "start (local)" in source
        assert "ToLocalTime()" in source, \
            "the customer picked the dates off a local calendar"

    def test_the_export_only_writes_where_the_user_chose(self):
        service = self.SERVICE.read_text(encoding="utf-8")
        assert "File.WriteAllText(path" in service
        assert "GetTempPath" not in service and "Upload" not in service, \
            "nothing may leave the machine; the privacy policy says so"

    def test_settings_offers_a_range_a_format_and_a_button(self):
        xaml = self.SETTINGS_XAML.read_text(encoding="utf-8")
        for automation_id in ("ExportFromDate", "ExportToDate", "ExportCsvRadio",
                              "ExportMarkdownRadio", "ExportJournalButton"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml


# ================================= momentum trend and explainer (F14 / 3.2)

class TestMomentumTrend:
    """
    Python mirror of Models/MomentumTrend.cs. Momentum is event-driven, so the
    trend is a replay of the sessions rather than a second record of the score.
    """

    DAYS = 30
    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    MODEL = DESKTOP / "Models" / "MomentumTrend.cs"

    @staticmethod
    def _after(score, completed, minutes, sealed_=False, interrupted=False):
        # An interrupted sprint leaves the score alone, exactly as
        # TodayViewModel.ApplyMomentum does — it is never called for one.
        if interrupted:
            return score
        if completed:
            weight = min(max(minutes / 25.0, 0.5), 3.0)
            return round(score + 10 * weight, 1)
        return round(max(0.0, score * 0.7 - 5) if sealed_ else max(0.0, score * 0.85 - 2), 1)

    @staticmethod
    def _unpack(session):
        """Sessions are (day, completed, minutes, sealed) with optional interrupted."""
        day, completed, minutes, sealed_ = session[:4]
        return day, completed, minutes, sealed_, (len(session) > 4 and session[4])

    def _points(self, sessions, today, days=None):
        days = days or self.DAYS
        start = today - timedelta(days=days - 1)
        by_day, score = {}, 0.0
        for session in sorted(sessions):
            day, completed, minutes, sealed_, interrupted = self._unpack(session)
            score = self._after(score, completed, minutes, sealed_, interrupted)
            by_day[day] = score
        running = 0.0
        for session in sorted(sessions):
            day, completed, minutes, sealed_, interrupted = self._unpack(session)
            if day < start:
                running = self._after(running, completed, minutes, sealed_, interrupted)
        out = []
        for i in range(days):
            day = start + timedelta(days=i)
            if day in by_day:
                running = by_day[day]
            out.append((day, running))
        return out

    def test_a_quiet_day_carries_the_score_forward(self):
        today = date(2026, 9, 18)
        points = self._points([(date(2026, 9, 16), True, 25, False)], today)
        assert len(points) == self.DAYS
        assert points[-1][1] == 10.0
        assert points[-2][1] == 10.0, "a day with no sprints must not drop the line to zero"

    def test_days_before_the_window_still_count(self):
        """The first point is the score as it stood then, not zero."""
        today = date(2026, 9, 18)
        old = date(2026, 1, 1)
        points = self._points([(old, True, 25, False)], today)
        assert points[0][1] == 10.0

    def test_ending_early_shows_as_a_dip_not_a_reset(self):
        today = date(2026, 9, 18)
        points = self._points([
            (date(2026, 9, 10), True, 50, False),
            (date(2026, 9, 11), False, 25, True),
        ], today)
        after_finish = round(0 + 10 * 2.0, 1)
        assert after_finish == 20.0
        assert points[-1][1] == round(max(0.0, 20.0 * 0.7 - 5), 1) == 9.0
        assert points[-1][1] > 0, "momentum decays, it does not reset"

    def test_sprints_that_were_all_ended_early_leave_nothing_to_draw(self):
        """
        Momentum only moves when a sprint is *finished*. Someone who started
        three and ended them all early has sessions and a score of zero, and a
        line pinned to the bottom gridline reads as broken rather than as
        "nothing yet" — so the chart stays hidden.
        """
        today = date(2026, 9, 18)
        points = self._points([
            (date(2026, 9, 16), False, 25, False),
            (date(2026, 9, 17), False, 25, False),
            (date(2026, 9, 18), False, 25, True),
        ], today)
        assert all(score == 0.0 for _, score in points)
        assert not any(score > 0 for _, score in points),             "nothing above zero means nothing worth drawing"

    def test_the_series_is_always_the_full_window(self):
        points = self._points([], date(2026, 9, 18))
        assert len(points) == self.DAYS
        assert {score for _, score in points} == {0.0}

    def test_the_explanation_matches_the_numbers_in_the_code(self):
        """
        The explainer states the rule in points and percentages. If the rule
        changes and the words don't, the app is lying to the customer in the
        one place that claims to be authoritative.
        """
        source = self.MODEL.read_text(encoding="utf-8")
        policy = (self.DESKTOP / "Models" / "EndSprintPolicy.cs").read_text(
            encoding="utf-8")
        today_vm = (self.DESKTOP / "ViewModels" / "TodayViewModel.cs").read_text(
            encoding="utf-8")

        assert "Math.Clamp(session.PlannedMinutes / 25.0, 0.5, 3.0)" in today_vm
        assert "S.MomentumScore + 10 * weight" in today_vm
        assert "score * 0.7 - 5" in policy and "score * 0.85 - 2" in policy

        explanation = source.split("Explanation =", 1)[1]
        assert "10 points for a 25-minute one" in explanation
        assert "5 points at the least, 30 at the most" in explanation, \
            "0.5 and 3.0 times 10 points"
        assert "15% and 2 points at Soft or Firm" in explanation
        assert "30% and 5 at Sealed" in explanation
        assert "never goes below zero" in explanation
        assert "does not decay overnight" in explanation

    def test_an_interrupted_sprint_does_not_move_the_line(self):
        """
        #195: momentum is only ever changed by a finished sprint or a deliberate
        early end, so the replay must leave an interrupted one alone — otherwise
        the chart drifts below the score printed beside it.
        """
        today = date(2026, 9, 18)
        points = self._points([
            (date(2026, 9, 16), True, 25, False, False),
            (date(2026, 9, 17), False, 25, False, True),   # interrupted
        ], today)
        assert points[-1][1] == 10.0, "an interrupted sprint enforces nothing and costs nothing"

    def test_the_trend_replays_rather_than_recording(self):
        """
        A stored daily sample would start the day the feature shipped and could
        disagree with MomentumScore. The model must derive from Sessions.
        """
        source = self.MODEL.read_text(encoding="utf-8")
        assert "settings.Sessions.OrderBy" in source
        settings = (self.DESKTOP / "Models" / "AppSettings.cs").read_text(
            encoding="utf-8")
        assert "MomentumHistory" not in settings, \
            "the trend must not add a second copy of the score to settings"


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


class TestMomentumTrendView:
    """The chart and explainer exist on Today and follow the chart rules."""

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    XAML = DESKTOP / "Views" / "TodayView.xaml"

    def _momentum_card(self):
        """Just the part F14 added, so this says nothing about older screens."""
        xaml = self.XAML.read_text(encoding="utf-8")
        return xaml.split("F14: the 30-day trend", 1)[1].split("</Border>", 1)[0]

    def test_today_has_the_chart_and_the_explainer(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        for automation_id in ("MomentumTrendRange", "MomentumTrendPeak",
                              "MomentumExplainerButton", "MomentumExplainerText"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml

    def test_no_automation_id_sits_on_a_layout_panel(self):
        """
        A Grid or StackPanel is not surfaced to UI Automation, so an id on one
        can never be found — and exists() on it answers the same whether the
        content is there or not, which is how a passing test can mean nothing.
        """
        block = self._momentum_card()
        for tag in ("<Grid", "<StackPanel"):
            for element in block.split(tag)[1:]:
                head = element.split(">", 1)[0]
                assert "AutomationProperties.AutomationId" not in head,                     f"an AutomationId is on a {tag[1:]}, where nothing can find it"

    def test_the_chart_is_described_where_a_screen_reader_can_hear_it(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        vm = (self.DESKTOP / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert 'AutomationProperties.Name="{Binding TrendDescription}"' in xaml
        assert "public string TrendDescription" in vm

    def test_the_chart_follows_the_design_system(self):
        """
        DESIGN_SYSTEM.md "Charts": one series in primary at 2 px, no area fill,
        horizontal gridlines in border.
        """
        xaml = self.XAML.read_text(encoding="utf-8")
        chart = xaml.split('<Grid Height="64"', 1)[1].split("</Grid>", 1)[0]

        assert 'Stroke="{StaticResource Primary}"' in chart
        assert 'StrokeThickness="2"' in chart
        assert "Fill=" not in chart, "a line chart has no area fill"
        assert chart.count("<Polyline") == 1, "no more than one series"
        assert 'Stroke="{StaticResource Edge}"' in chart, "gridlines use the border token"

        for line in chart.split("<Line")[1:]:
            head = line.split("/>", 1)[0]
            y1 = head.split('Y1="', 1)[1].split('"', 1)[0]
            y2 = head.split('Y2="', 1)[1].split('"', 1)[0]
            assert y1 == y2, "gridlines are horizontal only"

    def test_the_chart_hides_itself_when_there_is_nothing_to_draw(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        assert "{Binding TrendVisible, Converter={StaticResource BoolVis}}" in xaml
        vm = (self.DESKTOP / "ViewModels" / "TodayViewModel.cs").read_text(encoding="utf-8")
        assert "TrendVisible = points.Any(p => p.Score > 0);" in vm,             "the chart hides until there is momentum, not merely until there is a sprint"


# ===================================== History and the weekly view (F16 / 3.1, 3.6)

class TestHistoryStats:
    """
    Python mirror of Models/HistoryStats.cs.

    History is a projection of AppSettings.Sessions, not a second record, so
    every rule it applies — where a week starts, which day a sprint counts on,
    how a heatmap cell picks its step — is pinned here against the source.
    """

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    MODEL = DESKTOP / "Models" / "HistoryStats.cs"

    HEATMAP_DAYS = 30
    STEPS = 5

    # --------------------------------------------------------- the rules again

    @staticmethod
    def _week_start(day):
        """Monday of that week. The C# uses DayOfWeek, where Sunday is 0."""
        back = 6 if day.weekday() == 6 else day.weekday()
        return day - timedelta(days=back)

    @classmethod
    def _week_end(cls, day):
        return cls._week_start(day) + timedelta(days=6)

    @classmethod
    def _for_week(cls, sessions, now):
        """sessions are (local day, actual minutes, completed, blocks)."""
        start, end = cls._week_start(now), cls._week_end(now)
        inside = [s for s in sessions if start <= s[0] <= end]
        return {
            "start": start,
            "end": end,
            "minutes": round(sum(s[1] for s in inside), 1),
            "completed": sum(1 for s in inside if s[2]),
            "blocks": sum(s[3] for s in inside),
        }

    @classmethod
    def _step(cls, minutes, peak):
        import math
        if minutes <= 0:
            return 0
        if peak <= 0:
            return 1
        share = math.ceil(minutes / peak * (cls.STEPS - 1))
        return min(max(share, 1), cls.STEPS - 1)

    @classmethod
    def _heatmap(cls, sessions, today, days=None):
        days = days or cls.HEATMAP_DAYS
        start = today - timedelta(days=days - 1)
        by_day = {}
        for day, minutes, _completed, _blocks in sessions:
            if start <= day <= today:
                by_day[day] = by_day.get(day, 0) + minutes
        by_day = {day: round(m) for day, m in by_day.items()}
        peak = max(by_day.values()) if by_day else 0
        return [
            (start + timedelta(days=i),
             by_day.get(start + timedelta(days=i), 0),
             cls._step(by_day.get(start + timedelta(days=i), 0), peak))
            for i in range(days)
        ]

    # ------------------------------------------------------- week boundaries

    def test_the_week_runs_monday_to_sunday(self):
        # 21 September 2026 is a Monday.
        monday = date(2026, 9, 21)
        assert monday.weekday() == 0
        assert self._week_start(monday) == monday
        assert self._week_end(monday) == date(2026, 9, 27)

    def test_every_day_of_one_week_agrees_on_its_monday(self):
        monday = date(2026, 9, 21)
        for offset in range(7):
            day = monday + timedelta(days=offset)
            assert self._week_start(day) == monday, f"{day} fell outside its own week"
            assert self._week_end(day) == monday + timedelta(days=6)

    def test_sunday_belongs_to_the_week_that_just_ended(self):
        """
        The one boundary that is easy to get wrong: .NET numbers Sunday 0, so a
        naive DayOfWeek - 1 would send Sunday back to the *next* Monday and
        silently move a Sunday evening's sprints into next week's total.
        """
        sunday = date(2026, 9, 27)
        assert sunday.weekday() == 6
        assert self._week_start(sunday) == date(2026, 9, 21)
        assert self._week_end(sunday) == sunday

        source = self.MODEL.read_text(encoding="utf-8")
        assert "DayOfWeek.Sunday ? 6" in source, \
            "Sunday needs the full six days back, not DayOfWeek - 1"

    def test_monday_starts_a_new_week_rather_than_extending_the_old_one(self):
        assert self._week_start(date(2026, 9, 28)) == date(2026, 9, 28)
        assert self._week_start(date(2026, 9, 27)) == date(2026, 9, 21)

    def test_the_week_is_monday_first_whatever_the_regional_format_says(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "CurrentCulture" not in source and "FirstDayOfWeek" not in source, \
            "a culture-dependent week would move last week's hours when the format changes"

    # ------------------------------------------------------- the week's figures

    def test_the_week_counts_only_its_own_sprints(self):
        now = date(2026, 9, 23)          # Wednesday
        week = self._for_week([
            (date(2026, 9, 20), 60.0, True, 4),     # the Sunday before: last week
            (date(2026, 9, 21), 25.0, True, 1),
            (date(2026, 9, 23), 12.0, False, 2),
            (date(2026, 9, 28), 45.0, True, 9),     # next Monday
        ], now)
        assert week["minutes"] == 37.0
        assert week["completed"] == 1
        assert week["blocks"] == 3

    def test_minutes_count_whatever_the_outcome_but_completed_does_not(self):
        """
        A sprint ended after 12 of its 25 minutes really was 12 minutes of
        focus, and Today's card already sums every sprint's minutes for one day
        — the week must agree with it. "Sprints completed" is the finished ones.
        """
        now = date(2026, 9, 23)
        week = self._for_week([
            (date(2026, 9, 21), 25.0, True, 0),
            (date(2026, 9, 22), 12.0, False, 0),
        ], now)
        assert week["minutes"] == 37.0
        assert week["completed"] == 1

    def test_an_empty_week_is_zero_rather_than_missing(self):
        week = self._for_week([], date(2026, 9, 23))
        assert (week["minutes"], week["completed"], week["blocks"]) == (0, 0, 0)
        assert week["start"] == date(2026, 9, 21)

    def test_a_sprint_counts_on_the_local_day_it_started(self):
        """A sprint begun at 11:30pm belongs to that evening, not to tomorrow."""
        source = self.MODEL.read_text(encoding="utf-8")
        body = source.split("DayOf(FocusSession session) =>", 1)[1].split(";", 1)[0]
        assert "StartedUtc.ToLocalTime().Date" in body
        assert "EndedUtc" not in body, "the day a sprint ended is not the day it counts on"

    # ------------------------------------------------------ heatmap bucketing

    def test_no_focus_at_all_is_its_own_step(self):
        """One minute must look different from none; step 0 means nothing."""
        assert self._step(0, 120) == 0
        assert self._step(1, 120) == 1

    def test_the_busiest_day_takes_the_darkest_step(self):
        assert self._step(120, 120) == self.STEPS - 1 == 4

    def test_the_four_used_steps_split_the_range_evenly(self):
        peak = 100
        assert self._step(1, peak) == 1
        assert self._step(25, peak) == 1
        assert self._step(26, peak) == 2
        assert self._step(50, peak) == 2
        assert self._step(51, peak) == 3
        assert self._step(75, peak) == 3
        assert self._step(76, peak) == 4
        assert self._step(100, peak) == 4

    def test_the_scale_follows_the_window_not_a_fixed_minute_count(self):
        """
        25-minute sprints and three-hour days must both read; scaling against a
        fixed target would flatten one of them into a single block.
        """
        assert self._step(25, 25) == 4, "a light week still shows its best day dark"
        assert self._step(25, 200) == 1, "a heavy week puts the same 25 minutes low"

    def test_a_day_that_is_the_only_one_with_any_focus_is_still_readable(self):
        assert self._step(5, 5) == 4

    def test_a_peak_of_zero_never_divides_by_it(self):
        assert self._step(0, 0) == 0
        assert self._step(3, 0) == 1

    def test_the_grid_is_always_the_full_window(self):
        cells = self._heatmap([], date(2026, 9, 23))
        assert len(cells) == self.HEATMAP_DAYS
        assert {step for _day, _m, step in cells} == {0}
        assert cells[0][0] == date(2026, 9, 23) - timedelta(days=29)
        assert cells[-1][0] == date(2026, 9, 23)

    def test_days_outside_the_window_are_left_out_of_the_scale(self):
        """An old marathon day must not flatten the last 30 days against it."""
        today = date(2026, 9, 23)
        cells = self._heatmap([
            (date(2026, 1, 1), 600.0, True, 0),
            (date(2026, 9, 22), 30.0, True, 0),
        ], today)
        by_day = {day: (minutes, step) for day, minutes, step in cells}
        assert by_day[date(2026, 9, 22)] == (30, 4), \
            "the busiest day inside the window is the top of the scale"

    def test_several_sprints_on_one_day_add_up_in_one_cell(self):
        today = date(2026, 9, 23)
        cells = self._heatmap([
            (today, 25.0, True, 0),
            (today, 25.0, True, 0),
        ], today)
        assert cells[-1][1] == 50

    def test_the_heatmap_has_five_steps_and_thirty_days(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert f"HeatmapDays = {self.HEATMAP_DAYS}" in source
        assert f"Steps = {self.STEPS}" in source, \
            'DESIGN_SYSTEM.md §7: "five steps from surface-2 to primary"'

    # ------------------------------------------------- the most-blocked app

    @staticmethod
    def _most_blocked(apps):
        """apps are (display name, block count)."""
        ranked = sorted(
            (a for a in apps if a[1] > 0),
            key=lambda a: (-a[1], a[0].lower()))
        return ranked[0][0] if ranked else ""

    def test_the_app_blocked_most_often_wins(self):
        assert self._most_blocked([("Discord", 3), ("Steam", 9), ("Slack", 1)]) == "Steam"

    def test_a_tie_breaks_on_the_name_so_the_card_stays_still(self):
        """
        Two apps on the same count must not swap places between one draw and the
        next, which is what list order would do.
        """
        assert self._most_blocked([("Steam", 4), ("Discord", 4)]) == "Discord"
        assert self._most_blocked([("Discord", 4), ("Steam", 4)]) == "Discord"

    def test_a_tie_ignores_case(self):
        assert self._most_blocked([("brave", 2), ("Ableton", 2)]) == "Ableton"

    def test_apps_that_have_never_been_blocked_are_not_named(self):
        assert self._most_blocked([("Discord", 0), ("Steam", 0)]) == ""
        assert self._most_blocked([]) == ""

    def test_the_tie_break_is_the_one_in_the_source(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "OrderByDescending(a => a.BlockCount)" in source
        assert "ThenBy(a => a.DisplayName, StringComparer.OrdinalIgnoreCase)" in source

    # ------------------------------------------------------------ the shape

    def test_the_aggregation_is_pure(self):
        """
        No clock, no file system and no view: the page's rules have to be
        testable on their own, and the same numbers have to come out twice.
        """
        source = self.MODEL.read_text(encoding="utf-8")
        for forbidden in ("DateTime.Now", "DateTime.UtcNow", "File.", "SettingsService",
                          "HttpClient", "using System.Windows"):
            assert forbidden not in source, \
                f"HistoryStats must stay pure; it mentions {forbidden}"

    def test_history_adds_nothing_to_what_is_stored(self):
        """
        Same reasoning as the momentum trend: a stored weekly roll-up would
        start the day this shipped and could disagree with the sessions it
        claims to summarise.
        """
        settings = (self.DESKTOP / "Models" / "AppSettings.cs").read_text(encoding="utf-8")
        for forbidden in ("WeeklyStats", "HistoryCache", "FocusMinutesByDay"):
            assert forbidden not in settings


# ============================== graceful close at Firm (F7 / roadmap 1.8)

class TestGracefulClose:
    """
    Python mirror of Models/GracefulClose.cs.

    Firm used to call Kill() the instant it saw a blocked app. It now asks the
    app to close itself, waits, and only forces it if it is still there — which
    is the difference between losing an essay and being told to save it.
    """

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    MODEL = DESKTOP / "Models" / "GracefulClose.cs"

    GRACE_SECONDS = 10
    SHORT_GRACE_SECONDS = 2

    @staticmethod
    def _is_graceful(shield, hard_kill):
        return not hard_kill and shield >= 2      # 2 = Firm, 3 = Sealed

    def test_soft_never_warns_about_closing_because_it_never_closes(self):
        assert not self._is_graceful(1, False)

    def test_firm_and_sealed_warn_first(self):
        assert self._is_graceful(2, False)
        assert self._is_graceful(3, False)

    def test_hard_kill_stays_instant_at_every_shield(self):
        """
        Someone who turned hard kill on asked for no way round it, and ten
        seconds to alt-tab and save is a way round it.
        """
        for shield in (1, 2, 3):
            assert not self._is_graceful(shield, True)

    def test_the_warning_says_the_app_the_delay_and_what_to_do(self):
        source = self.MODEL.read_text(encoding="utf-8")
        warning = source.split("public static string Warning", 1)[1]
        warning = warning.split("return ", 1)[1].split(";", 1)[0]
        assert "is blocked" in warning
        assert "closing in {seconds} s" in warning
        assert "Save your work." in warning

    def test_the_grace_period_is_ten_seconds_and_two_under_short_timers(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert f"TimeSpan.FromSeconds({self.SHORT_GRACE_SECONDS})" in source
        assert f"TimeSpan.FromSeconds({self.GRACE_SECONDS})" in source
        assert "UseShortTimers" in source, "the UI suite cannot wait ten seconds a time"

    def test_the_short_timer_flag_is_wired_to_the_command_line(self):
        app = (self.DESKTOP / "App.xaml.cs").read_text(encoding="utf-8")
        assert "Models.GracefulClose.UseShortTimers = true;" in app

    def test_closing_is_asked_for_before_it_is_forced(self):
        """
        CloseMainWindow is the same request the window's own close button
        sends; Kill is not. The order is the whole feature.
        """
        service = (self.DESKTOP / "Services" / "AppBlockerService.cs").read_text(
            encoding="utf-8")
        sweep = service.split("private void Tick", 1)[1]
        asked = sweep.index("CloseMainWindow()")
        forced = sweep.index("_closingAt.Remove(key)")
        assert asked < forced, "the app must be asked to close before the deadline kills it"

    def test_a_blocked_app_that_goes_away_forgets_its_deadline(self):
        service = (self.DESKTOP / "Services" / "AppBlockerService.cs").read_text(
            encoding="utf-8")
        assert "_closingAt.Remove(gone)" in service, (
            "a half-finished close must not outlive the app it was closing"
        )


# ===================== what is already open, before a sprint (F7 / 1.8)

class TestPreSprintRunningApps:
    """
    Roadmap 1.8: before a sprint starts, if blocked apps are running, list them
    and offer Close them now or Start anyway.

    The point is the chance to save, so the wording has to be honest about what
    each shield will actually do — promising a close at Soft, which closes
    nothing, would be worse than saying nothing.
    """

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    VM = DESKTOP / "ViewModels" / "TodayViewModel.cs"
    SERVICE = DESKTOP / "Services" / "AppBlockerService.cs"
    XAML = DESKTOP / "Views" / "TodayView.xaml"

    def test_the_list_names_each_app_once(self):
        """
        Steam runs seven processes. "Steam, Steam, Steam, Steam" is not a list,
        and it is the same reason #138 counts apps rather than processes.
        """
        source = self.SERVICE.read_text(encoding="utf-8")
        body = source.split("public IReadOnlyList<string> RunningBlockedApps", 1)[1]
        body = body.split("\n    }", 1)[0]
        assert "seen.Add(app.DisplayName)" in body

    def test_looking_is_not_enforcing(self):
        """It runs before the sprint does; it must not close anything."""
        source = self.SERVICE.read_text(encoding="utf-8")
        body = source.split("public IReadOnlyList<string> RunningBlockedApps", 1)[1]
        body = body.split("\n    }", 1)[0]
        for forbidden in ("Kill(", "CloseMainWindow(", "BeginEnforcing"):
            assert forbidden not in body, f"the pre-sprint look must not {forbidden}"

    def test_soft_does_not_promise_a_close_it_will_not_do(self):
        source = self.VM.read_text(encoding="utf-8")
        explanation = source.split("RunningAppsExplanation =>", 1)[1].split(";", 1)[0]
        assert "ShieldLevel.Soft" in explanation
        assert "they stay open" in explanation
        assert "asked to close" in explanation, "Firm and above say what happens"

    def test_the_panel_offers_both_answers(self):
        xaml = self.XAML.read_text(encoding="utf-8")
        for automation_id in ("RunningAppsTitle", "RunningAppsList",
                              "CloseThemNowButton", "StartAnywayButton"):
            assert f'AutomationProperties.AutomationId="{automation_id}"' in xaml

    def test_the_panel_puts_no_id_where_nothing_can_find_it(self):
        """
        A Border is not surfaced to UI Automation. An id on one can never be
        resolved, which cost a whole VM run: the panel opened, exists() said it
        had not, and the driver never answered it.
        """
        xaml = self.XAML.read_text(encoding="utf-8")
        panel = xaml.split("What is already open, before the shield goes up", 1)[1]
        panel = panel.split("</Border>", 1)[0]
        for tag in ("<Border", "<StackPanel", "<ItemsControl"):
            for element in panel.split(tag)[1:]:
                head = element.split(">", 1)[0]
                assert "AutomationProperties.AutomationId" not in head, (
                    f"an AutomationId is on a {tag[1:]}, where nothing can find it"
                )

    def test_answering_does_not_ask_again(self):
        """
        Both answers call back into StartSprint. Without the latch that is a
        loop: panel, answer, panel, answer.
        """
        source = self.VM.read_text(encoding="utf-8")
        assert "if (!_runningAppsAnswered)" in source
        assert "_runningAppsAnswered = false;" in source, (
            "the latch has to reset, or the next sprint is never checked"
        )

# ==================== when the Soft notice appears (F7 / roadmap 1.7)

class SoftOverlayPolicy:
    """
    Python mirror of Models/SoftOverlayPolicy.cs.

    Times are plain seconds here; the C# version takes UTC instants. Only the
    two rules matter: once per sighting, and a per-app quiet window.
    """

    ALLOW_WINDOW = 5 * 60
    BACK_TO_WORK_QUIET = 5

    def __init__(self):
        self.quiet_until: dict[str, float] = {}
        self.sighting: str | None = None
        self.showing = False

    def should_show(self, app: str, now: float) -> bool:
        is_new = self.sighting is None or self.sighting.lower() != app.lower()
        self.sighting = app
        if not is_new:
            return False
        if self.is_quiet(app, now):
            return False
        self.showing = True
        return True

    def left_the_foreground(self) -> bool:
        self.sighting = None
        was_showing = self.showing
        self.showing = False
        return was_showing

    def allow_five_minutes(self, app: str, now: float) -> None:
        self._quieten(app, now, self.ALLOW_WINDOW)

    def back_to_work(self, app: str, now: float) -> None:
        self._quieten(app, now, self.BACK_TO_WORK_QUIET)

    def _quieten(self, app: str, now: float, window: float) -> None:
        self.quiet_until[app.lower()] = now + window
        self.sighting = None
        self.showing = False

    def is_quiet(self, app: str, now: float) -> bool:
        return now < self.quiet_until.get(app.lower(), float("-inf"))

    def reset(self) -> None:
        self.quiet_until.clear()
        self.sighting = None
        self.showing = False


class TestSoftOverlayPolicy:
    """
    Roadmap 1.7: at Soft, a blocked app coming to the front gets a full-screen
    notice — once, not on every sweep of the blocker, and not at all for five
    minutes after "Allow 5 minutes".
    """

    DESKTOP = Path(SERVER_DIR).parent / "DesktopApp"
    MODEL = DESKTOP / "Models" / "SoftOverlayPolicy.cs"
    BACK_TO_WORK_QUIET_SECONDS = 5

    def test_a_blocked_app_coming_to_the_front_is_shown_once(self):
        """
        The blocker sweeps every two seconds. Showing the notice on every sweep
        while Discord is still in front would be a flashing box, not a nudge.
        """
        policy = SoftOverlayPolicy()
        assert policy.should_show("Discord", 0)
        for tick in range(1, 20):
            assert not policy.should_show("Discord", tick * 2), (
                "the notice must appear once per sighting, not once per sweep"
            )

    def test_going_away_and_coming_back_is_a_new_sighting(self):
        policy = SoftOverlayPolicy()
        assert policy.should_show("Discord", 0)
        assert policy.left_the_foreground() is True, "a notice was up and must come down"
        assert policy.should_show("Discord", 60)

    def test_nothing_to_take_down_when_no_notice_was_up(self):
        policy = SoftOverlayPolicy()
        assert policy.left_the_foreground() is False

    def test_another_blocked_app_gets_its_own_notice(self):
        policy = SoftOverlayPolicy()
        assert policy.should_show("Discord", 0)
        assert policy.should_show("Steam", 2)
        assert not policy.should_show("Steam", 4)

    def test_allow_five_minutes_is_five_minutes_for_that_app_only(self):
        policy = SoftOverlayPolicy()
        assert policy.should_show("Discord", 0)
        policy.allow_five_minutes("Discord", 0)

        # Returning inside the window says nothing.
        assert not policy.should_show("Discord", 1)
        assert policy.left_the_foreground() is False
        assert not policy.should_show("Discord", 299)

        # Another blocked app is not covered by Discord's allowance.
        assert policy.should_show("Steam", 10)

        policy.left_the_foreground()
        assert policy.should_show("Discord", 301), (
            "five minutes is five minutes, not the rest of the sprint"
        )

    def test_back_to_work_goes_quiet_just_long_enough_to_get_out_of_the_way(self):
        """
        Bringing FlowShield forward takes a moment. Without the quiet window the
        notice reappears in the gap, over the window it just asked for.
        """
        policy = SoftOverlayPolicy()
        assert policy.should_show("Discord", 0)
        policy.back_to_work("Discord", 0)
        assert not policy.should_show("Discord", 1)
        policy.left_the_foreground()
        assert policy.should_show("Discord", 30), (
            "going back to the distraction later must nudge again"
        )

    def test_a_quiet_window_expiring_does_not_interrupt_what_you_are_doing(self):
        """
        The notice appears when you go to the blocked app, not while you are in
        it. Someone who asked for five minutes and is still in Discord at minute
        six gets nothing until they leave and come back — a panel appearing over
        a window they are typing in would be the worst moment for it.
        """
        policy = SoftOverlayPolicy()
        policy.should_show("Discord", 0)
        policy.allow_five_minutes("Discord", 0)
        for tick in range(1, 400, 2):
            assert not policy.should_show("Discord", tick)

    def test_app_names_are_matched_without_case(self):
        policy = SoftOverlayPolicy()
        policy.allow_five_minutes("Discord", 0)
        assert not policy.should_show("discord", 10)

    def test_an_allowance_does_not_outlive_its_sprint(self):
        policy = SoftOverlayPolicy()
        policy.allow_five_minutes("Discord", 0)
        policy.reset()
        assert policy.should_show("Discord", 10), (
            "a new sprint starts with no allowances carried over"
        )

    # ---- the mirror above proves the rules are right; these prove the C# has
    # them. Without this half, `if (false && !isNewSighting)` in ShouldShow
    # left every Python test passing while the notice flashed on every sweep.

    def _model(self) -> str:
        return " ".join(self.MODEL.read_text(encoding="utf-8").split())

    def _body(self, signature: str) -> str:
        source = self.MODEL.read_text(encoding="utf-8")
        assert signature in source, f"{signature} is gone from SoftOverlayPolicy.cs"
        return " ".join(source.split(signature, 1)[1].split("\n    }", 1)[0].split())

    def test_the_windows_in_the_model_match_this_mirror(self):
        source = self.MODEL.read_text(encoding="utf-8")
        assert "TimeSpan.FromMinutes(5)" in source, "Allow 5 minutes has to be five minutes"
        assert f"TimeSpan.FromSeconds({self.BACK_TO_WORK_QUIET_SECONDS})" in source

    def test_the_model_returns_early_for_a_sighting_it_has_already_answered(self):
        body = self._body("public bool ShouldShow(string displayName, DateTime nowUtc)")
        assert ("var isNewSighting = !string.Equals(_sighting, displayName, "
                "StringComparison.OrdinalIgnoreCase);") in body, (
            "the same-sighting test has to compare the remembered app with this one, "
            "without case"
        )
        assert "if (!isNewSighting) return false;" in body, (
            "once per sighting is this line; short-circuiting it (false && ...) "
            "makes the notice appear on every two-second sweep"
        )
        assert "if (IsQuiet(displayName, nowUtc)) return false;" in body, (
            "an allowance has to be checked where the notice is decided"
        )
        for dead in ("false &&", "true ||", "&& false", "|| true"):
            assert dead not in body, f"{dead} disables a rule while leaving it in the source"

    def test_the_sighting_is_remembered_even_when_nothing_is_drawn(self):
        """
        Otherwise a suppressed app is a new sighting every sweep, and the moment
        its five minutes are up the notice lands on a window mid-sentence.
        """
        body = self._body("public bool ShouldShow(string displayName, DateTime nowUtc)")
        assert body.index("_sighting = displayName;") < body.index("if (!isNewSighting)")

    def test_each_answer_maps_to_its_own_window(self):
        source = self._model()
        assert ("public void AllowFiveMinutes(string displayName, DateTime nowUtc) => "
                "Quieten(displayName, nowUtc, AllowWindow);") in source
        assert ("public void BackToWork(string displayName, DateTime nowUtc) => "
                "Quieten(displayName, nowUtc, BackToWorkQuiet);") in source
        assert "AllowWindow = TimeSpan.FromMinutes(5)" in source
        assert (f"BackToWorkQuiet = TimeSpan.FromSeconds"
                f"({self.BACK_TO_WORK_QUIET_SECONDS})") in source

    def test_a_quiet_window_is_recorded_per_app_and_read_back(self):
        quieten = self._body(
            "private void Quieten(string displayName, DateTime nowUtc, TimeSpan window)")
        assert "_quietUntil[displayName] = nowUtc + window;" in quieten, (
            "the window has to be stored against the app, or it silences everything"
        )
        assert "_sighting = null;" in quieten, (
            "clearing the sighting is what makes coming back later a new one"
        )
        assert "_showing = false;" in quieten

        is_quiet = self._model()
        assert ("_quietUntil.TryGetValue(displayName, out var until) && nowUtc < until"
                in is_quiet), "a window that is never compared against the clock never ends"

    def test_the_notice_is_taken_down_only_when_one_was_up(self):
        body = self._body("public bool LeftTheForeground()")
        assert "var wasShowing = _showing;" in body
        assert "_showing = false;" in body
        assert "return wasShowing;" in body, (
            "returning true unconditionally would ask MainWindow to close a "
            "notice that was never opened"
        )

    def test_reset_forgets_every_allowance(self):
        body = self._body("public void Reset()")
        assert "_quietUntil.Clear();" in body
        assert "_sighting = null;" in body
        assert "_showing = false;" in body

    def test_the_policy_decides_nothing_about_closing_anything(self):
        """Soft notes distractions. A policy that could close one is the wrong shape."""
        source = self.MODEL.read_text(encoding="utf-8")
        for forbidden in ("Kill(", "CloseMainWindow(", "Process"):
            assert forbidden not in source, f"the Soft notice policy must not mention {forbidden}"

    def test_the_sentence_names_the_app_and_when_the_blocklist_holds_until(self):
        """DESIGN_SYSTEM.md §7's own example: "Discord is on your blocklist until 5:45 PM"."""
        source = self.MODEL.read_text(encoding="utf-8")
        sentence = source.split("public static string Sentence", 1)[1]
        sentence = sentence.split("=>", 1)[1].split(";", 1)[0]
        assert "{displayName} is on your blocklist until" in sentence

    def test_the_time_left_is_specific(self):
        source = self.MODEL.read_text(encoding="utf-8")
        body = source.split("public static string TimeLeft", 1)[1].split("\n    }", 1)[0]
        assert "1 minute left in this sprint" in body
        assert "minutes left in this sprint" in body

    def test_the_copy_keeps_to_the_house_voice(self):
        """DESIGN_SYSTEM.md §9: no exclamation marks, no emoji, no scolding."""
        source = self.MODEL.read_text(encoding="utf-8")
        quoted = re.findall(r'"([^"]*)"', source)
        for text in quoted:
            assert "!" not in text, f"exclamation mark in product copy: {text!r}"
            assert text.isascii(), f"non-ascii (emoji?) in product copy: {text!r}"


# ============================ issue hygiene check (#158)

class TestIssueHygieneChecks:
    """
    The checks in tools/issue_hygiene/check.py, on made-up issues.

    Written against data rather than the live repo on purpose: a test that
    asks GitHub what it thinks today passes or fails for reasons that have
    nothing to do with the code, and cannot be run offline.
    """

    @staticmethod
    def _now():
        """A fixed clock, so "stale" means the same thing in a year."""
        from datetime import datetime, timezone
        return datetime(2026, 9, 21, tzinfo=timezone.utc)

    @staticmethod
    def _module():
        import importlib.util
        path = Path(__file__).resolve().parent.parent.parent / "tools" / "issue_hygiene" / "check.py"
        spec = importlib.util.spec_from_file_location("issue_hygiene_check", path)
        module = importlib.util.module_from_spec(spec)
        # Registered before exec: @dataclass looks its own module up in
        # sys.modules while the class body runs, and gets None otherwise.
        import sys as _sys
        _sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    CHECKLIST = """
### F7 — Soft shows a real overlay · **Launch** · M

- [ ] Done — half of it shipped

### F12 — A sprint summary worth reading · **Launch** · S

- [x] Done — shipped in #100

**Assigned:** somebody
"""

    def test_it_reads_only_ticked_features(self):
        check = self._module()
        ticked = check.ticked_features(self.CHECKLIST)
        assert set(ticked) == {"F12"}, "an unticked feature must not read as shipped"
        assert "#100" in ticked["F12"]

    def test_an_issue_for_shipped_work_is_reported(self):
        """The #143 case: a title describing work that has landed."""
        check = self._module()
        issues = [{"number": 9, "title": "F12: sprint summary card", "body": "",
                   "labels": ["enhancement"], "assignees": ["someone"], "milestone": None}]
        found = check.run_checks(issues, self.CHECKLIST, {}, self._now())
        assert [f.kind for f in found] == ["shipped-but-open"]

    def test_a_feature_mentioned_as_a_blocker_is_not_the_subject(self):
        """
        "F14: milestones (waiting on F12)" is about F14, not F12. Reading every
        mention as the subject made the first version report its own trackers.
        """
        check = self._module()
        issues = [{"number": 9, "title": "F14: quiet milestones (waiting on F12's list)",
                   "body": "", "labels": ["enhancement"], "assignees": ["someone"],
                   "milestone": None}]
        found = check.run_checks(issues, self.CHECKLIST, {}, self._now())
        assert not [f for f in found if f.kind == "shipped-but-open"]

    def test_blocked_by_something_closed_is_reported(self):
        """The F20 case: blocked on F19 for a week after F19 merged."""
        check = self._module()
        issues = [{"number": 9, "title": "A trial that never nags", "body": "waits on #96",
                   "labels": ["enhancement", "blocked"], "assignees": ["someone"],
                   "milestone": None}]
        found = check.run_checks(issues, self.CHECKLIST, {96: "CLOSED"},
                                 self._now())
        assert [f.kind for f in found] == ["blocked-but-unblocked"]

    def test_blocked_by_something_still_open_is_left_alone(self):
        check = self._module()
        issues = [{"number": 9, "title": "A trial that never nags", "body": "waits on #96",
                   "labels": ["enhancement", "blocked"], "assignees": ["someone"],
                   "milestone": None}]
        found = check.run_checks(issues, self.CHECKLIST, {96: "OPEN"},
                                 self._now())
        assert not found, "an issue waiting on open work is not drift"

    def test_a_stale_tracker_is_reported_and_a_fresh_one_is_not(self):
        check = self._module()
        now = self._now()
        stale = [{"number": 38, "title": "Launch work", "body": "Next up (reviewed 1 September 2026)",
                  "labels": ["documentation"], "assignees": ["someone"], "milestone": None}]
        fresh = [{"number": 38, "title": "Launch work", "body": "Next up (reviewed 20 September 2026)",
                  "labels": ["documentation"], "assignees": ["someone"], "milestone": None}]
        assert [f.kind for f in check.run_checks(stale, self.CHECKLIST, {}, now)] == ["tracker-stale"]
        assert not check.run_checks(fresh, self.CHECKLIST, {}, now)

    def test_metadata_gaps_are_reported(self):
        check = self._module()
        issues = [{"number": 9, "title": "Something", "body": "", "labels": [],
                   "assignees": [], "milestone": "Launch"}]
        kinds = {f.kind for f in check.run_checks(issues, self.CHECKLIST, {},
                                                  self._now())}
        assert kinds == {"unlabelled", "launch-unassigned"}

    def test_a_clean_repo_reports_nothing(self):
        check = self._module()
        issues = [{"number": 9, "title": "F7: the Soft overlay", "body": "",
                   "labels": ["design"], "assignees": ["someone"], "milestone": None}]
        found = check.run_checks(issues, self.CHECKLIST, {}, self._now())
        assert not found
        assert "No issue-state drift" in check.report([])

# ==================== configured ports reach the server (fix/test-ports)

class TestConfiguredPortsReachTheServer:
    """
    Two agents on the same machine each set FLOWSHIELD_SERVER_PORT /
    FLOWSHIELD_WEBSITE_PORT and expect the license server they spawn to
    actually listen there. Before this fix, `license_server()` spawned
    `node server.js` with no PORT in its environment, so `Server/server.js`
    (`process.env.PORT || 3000`) always bound port 3000 regardless of what
    config.py had resolved — and conftest.py's `server` fixture probed the
    literal port 3000 as well, so it never noticed.
    """

    SERVICES = SERVER_DIR.parent / "automation" / "core" / "services.py"
    CONFTEST = SERVER_DIR.parent / "automation" / "tests" / "conftest.py"

    def test_license_server_env_sets_the_configured_port(self):
        source = self.SERVICES.read_text(encoding="utf-8")
        assert 'env["PORT"] = os.environ.get("PORT", str(SERVER_PORT))' in source, (
            "the node process must be told SERVER_PORT, or it falls back to "
            "server.js's own default of 3000"
        )
        assert 'env=_server_env()' in source, (
            "license_server() must pass the port-aware environment to the "
            "node child process, not the bare _npm_env()"
        )

    def test_license_server_env_sets_website_url_too(self):
        source = self.SERVICES.read_text(encoding="utf-8")
        assert 'env["WEBSITE_URL"] = WEBSITE_URL' in source, (
            "server.js builds checkout success/cancel URLs from WEBSITE_URL; "
            "without it, checkout tests point at the wrong site port"
        )

    def test_conftest_reads_the_port_from_config_not_a_literal(self):
        source = self.CONFTEST.read_text(encoding="utf-8")
        assert "port_is_open(3000)" not in source, (
            "a hardcoded 3000 here defeats FLOWSHIELD_SERVER_PORT: the "
            "server fixture would skip (or wrongly pass) based on the "
            "default port instead of the one actually configured"
        )
        assert "port_is_open(SERVER_PORT)" in source
        assert "SERVER_PORT" in source.split("from config import")[1].split(")")[0], (
            "SERVER_PORT must be imported from config, the single source of "
            "truth for FLOWSHIELD_SERVER_PORT"
        )


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
                      "dailyGoal", "sleepBlocking", "licence"):
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


# ======================================= tray and keyboard start a sprint (F4)

class TestSpaceShortcutSource:
    """
    Space on Today must start or end a sprint like the buttons do, but never
    while a text box (the intention field, the sealed phrase, the custom
    length) has focus — otherwise typing a space anywhere also toggled the
    sprint underneath the user.
    """

    TODAY_VM = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "TodayViewModel.cs"
    MAIN_XAML = Path(SERVER_DIR).parent / "DesktopApp" / "MainWindow.xaml"

    def source(self) -> str:
        return self.TODAY_VM.read_text(encoding="utf-8")

    def test_space_is_ignored_with_focus_in_a_text_box(self):
        source = self.source()
        guard = source.split("private bool CanUseSpaceShortcut()")[1].split("\n\n")[0]
        assert "Keyboard.FocusedElement is not TextBox" in guard, \
            "the Space shortcut must refuse while a text box has focus"

    def test_space_only_fires_on_today(self):
        source = self.source()
        guard = source.split("private bool CanUseSpaceShortcut()")[1].split("\n\n")[0]
        assert "AppPage.Today" in guard

    def test_space_reuses_the_same_toggle_as_the_buttons(self):
        source = self.source()
        assert "ToggleOrEndCommand = new RelayCommand(TogglePrimary, CanUseSpaceShortcut)" in source
        # TogglePrimary is exactly what StartSprintButton/StopSprintButton drive
        # (RequestEnd while running, StartSprint otherwise) — not a shortcut
        # around either.
        toggle = source.split("public void TogglePrimary()")[1].split("\n    }")[0]
        assert "RequestEnd()" in toggle and "StartSprint()" in toggle

    def test_the_window_binds_space_and_shift_shields_not_a_global_hook(self):
        xaml = self.MAIN_XAML.read_text(encoding="utf-8")
        assert '<KeyBinding Key="Space" Command="{Binding Today.ToggleOrEndCommand}"/>' in xaml
        for n in (1, 2, 3):
            assert f'Modifiers="Shift" Key="D{n}"' in xaml
        # Ctrl+1..5 is reserved for page navigation (issue #37, one slot per
        # nav-rail tab since F16 added History); Shift must never collide with it.
        for n in (1, 2, 3, 4, 5):
            assert f'Modifiers="Ctrl" Key="D{n}"' in xaml
        assert "RegisterWindowsHookEx" not in xaml
        assert "SetWindowsHookEx" not in (Path(SERVER_DIR).parent / "DesktopApp" / "MainWindow.xaml.cs").read_text(
            encoding="utf-8"), "keyboard shortcuts must be WPF KeyBindings, not a global hook"


class TestGlobalHotkeySource:
    """The optional Ctrl+Alt+F hotkey (F4): off by default, per-user, no admin rights."""

    SETTINGS = Path(SERVER_DIR).parent / "DesktopApp" / "Models" / "AppSettings.cs"
    WINDOW = Path(SERVER_DIR).parent / "DesktopApp" / "MainWindow.xaml.cs"
    SETTINGS_VM = Path(SERVER_DIR).parent / "DesktopApp" / "ViewModels" / "SettingsViewModel.cs"
    SETTINGS_XAML = Path(SERVER_DIR).parent / "DesktopApp" / "Views" / "SettingsView.xaml"

    def test_the_setting_defaults_to_off(self):
        source = self.SETTINGS.read_text(encoding="utf-8")
        field = source.split("public bool GlobalHotkeyEnabled")[1].split("\n")[0]
        assert "= true" not in field, "the global hotkey must be off until the user turns it on"

    def test_registration_uses_registerhotkey_not_admin_rights(self):
        window = self.WINDOW.read_text(encoding="utf-8")
        assert 'DllImport("user32.dll"' in window
        assert "RegisterHotKey(" in window
        assert "UnregisterHotKey(" in window
        assert "runas" not in window.lower()

    def test_a_taken_combination_turns_the_setting_back_off(self):
        window = self.WINDOW.read_text(encoding="utf-8")
        setup = window.split("private void SetUpGlobalHotkey()")[1].split("\n    private ")[0]
        assert "if (RegisterHotKey(" in setup
        failure = setup.split("else")[1]
        assert "GlobalHotkeyEnabled = false" in failure
        assert "vm.Toast(" in failure, "a taken hotkey must tell the user, not fail silently"

    def test_the_hotkey_is_unregistered_on_close(self):
        window = self.WINDOW.read_text(encoding="utf-8")
        closing = window.split("protected override void OnClosing")[1]
        assert "UnregisterHotKey(" in closing

    def test_the_setting_persists_through_the_normal_settings_pipeline(self):
        vm = self.SETTINGS_VM.read_text(encoding="utf-8")
        assert "public bool GlobalHotkeyEnabled" in vm
        assert "_main.SaveSettings();" in vm.split("public bool GlobalHotkeyEnabled")[1].split("}\n    }")[0]

        xaml = self.SETTINGS_XAML.read_text(encoding="utf-8")
        assert 'AutomationProperties.AutomationId="GlobalHotkeyToggle"' in xaml
        assert "{Binding GlobalHotkeyEnabled}" in xaml


class TestTrayMenuSource:
    """
    The tray menu (F4): start with last settings, start via the window, and —
    while running — the time left plus an End sprint that goes through the F2
    flow rather than ending the sprint directly.
    """

    WINDOW = Path(SERVER_DIR).parent / "DesktopApp" / "MainWindow.xaml.cs"

    def source(self) -> str:
        return self.WINDOW.read_text(encoding="utf-8")

    def test_the_menu_is_rebuilt_before_it_opens(self):
        source = self.source()
        assert "menu.Opening += (_, _) => BuildTrayMenu(menu);" in source

    def test_idle_offers_last_settings_and_start(self):
        source = self.source()
        build = source.split("private void BuildTrayMenu(")[1].split("\n    private ")[0]
        assert '"Start sprint (last settings)"' in build
        assert "Vm?.Today.StartCommand.Execute(null)" in build
        assert '"Start…"' in build

    def test_running_shows_time_left_and_end_sprint(self):
        source = self.source()
        build = source.split("private void BuildTrayMenu(")[1].split("\n    private ")[0]
        assert "RemainingText" in build
        assert "Enabled = false" in build, "the time-left row must not be clickable"
        assert '"End sprint"' in build
        assert "EndSprintFromTray()" in build

    def test_end_sprint_from_tray_goes_through_the_f2_flow(self):
        source = self.source()
        end = source.split("private void EndSprintFromTray()")[1].split("\n    }")[0]
        assert "BringToFront()" in end
        assert "vm.Today.StopCommand.Execute(null)" in end, \
            "the tray must trigger the same StopCommand as the Today button, not end the sprint directly"
        assert "EndSprint(" not in end
