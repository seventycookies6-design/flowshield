"""
Tier 1 — unit tests.

Pure logic, no app and no network. These exercise the same rules the desktop app
and the server enforce, using the Node modules directly (via a short-lived node
process) and Python re-implementations where the rule is shared.
"""

from __future__ import annotations

import json
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

def resume_decision(started_min_ago: float, planned: int, last_seen_min_ago: float) -> str:
    """Mirror of RunningSprint.Decide, in minutes relative to now."""
    if planned <= 0:
        return "Discard"
    started = -started_min_ago
    ends = started + planned
    if 0 < ends:
        return "Resume"
    watched = min(-last_seen_min_ago, ends) - started
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
        server = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")
        assert "consent_collection: { terms_of_service: 'required' }" in server
        consent = server.split("custom_text: {")[1].split("},")[0].lower()
        assert "closes programs" in consent and "unsaved work" in consent


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

    def settle(self, today):
        if self.settled is None:
            self.settled = today
            if self.judge(today) == "counted":
                self.streak = max(self.streak, 1)
            return
        if today <= self.settled:
            if today == self.settled and self.judge(today) == "counted":
                self.streak = max(self.streak, 1)
            return

        day = self.settled + timedelta(days=1)
        while day <= today:
            verdict = self.judge(day)
            if day == today:
                if verdict == "counted":
                    self.streak += 1
                break
            if verdict == "counted":
                self.streak += 1
            elif verdict == "missed":
                self.streak = 0
            day += timedelta(days=1)
        self.settled = today


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
        assert 'AutomationProperties.AutomationId="DailyGoalPanel"' in xaml
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
    def _after(score, completed, minutes, sealed_=False):
        if completed:
            weight = min(max(minutes / 25.0, 0.5), 3.0)
            return round(score + 10 * weight, 1)
        return round(max(0.0, score * 0.7 - 5) if sealed_ else max(0.0, score * 0.85 - 2), 1)

    def _points(self, sessions, today, days=None):
        days = days or self.DAYS
        start = today - timedelta(days=days - 1)
        by_day, score = {}, 0.0
        for day, completed, minutes, sealed_ in sorted(sessions):
            score = self._after(score, completed, minutes, sealed_)
            by_day[day] = score
        running = 0.0
        for day, completed, minutes, sealed_ in sorted(sessions):
            if day < start:
                running = self._after(running, completed, minutes, sealed_)
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
        assert "TrendVisible = S.Sessions.Count > 0;" in vm
