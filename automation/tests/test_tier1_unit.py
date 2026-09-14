"""
Tier 1 — unit tests.

Pure logic, no app and no network. These exercise the same rules the desktop app
and the server enforce, using the Node modules directly (via a short-lived node
process) and Python re-implementations where the rule is shared.
"""

from __future__ import annotations

import json
import subprocess
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
