# Split by tools/split_tests.py; edit this area directly after merge.
"""Tier 1: tooling."""

from __future__ import annotations
import json
import subprocess
from pathlib import Path
import pytest
from config import SERVER_DIR



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
        (root / "docs/history").mkdir(parents=True)
        (root / "README.md").write_text("| Tests | 200 tests. |\n", encoding="utf-8")
        (root / "docs/history/FINAL_REPORT.md").write_text("Duration: 1661.6s · 196 tests collected\n", encoding="utf-8")
        tracked = tracked | {"docs/history/FINAL_REPORT.md"}
        stale = self.edit(file="README.md", find="200 tests", replace="196 tests",
                          evidence=[{"file": "docs/history/FINAL_REPORT.md", "quote": "196 tests collected"}])
        config = steward.load_config()
        assert "docs/history/FINAL_REPORT.md" in config["historical"]
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
        for protected in ("Website/index.html", "Website/legal.html", "docs/history/FINAL_REPORT.md"):
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
        path = Path(__file__).resolve().parents[3] / "tools" / "issue_hygiene" / "check.py"
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


class TestReportHistory:
    def test_report_is_generated_under_history_not_at_root(self, tmp_path, monkeypatch):
        import make_report

        monkeypatch.setattr(make_report, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(make_report, "newest", lambda pattern: None)
        monkeypatch.setattr(make_report, "stripe_configured", lambda: False)
        monkeypatch.setattr(make_report, "stripe_section", lambda: "Test mode; not configured.")
        monkeypatch.setattr(make_report, "gallery", lambda: "No screenshots.")

        assert make_report.main() == 0
        report = tmp_path / "docs/history/FINAL_REPORT.md"
        assert "# Basalt" in report.read_text(encoding="utf-8")
        assert not (tmp_path / report.name).exists()
