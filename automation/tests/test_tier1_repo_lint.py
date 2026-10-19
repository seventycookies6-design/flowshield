"""Tests for the Tier 1 repository policy checker."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.repo_lint.check import (  # noqa: E402
    check_mojibake_text,
    find_forbidden_paths,
    pr_body_problem,
    run_repo_checks,
)


def test_mojibake_flags_only_repairable_cp1252_damage_with_line_number():
    text = "first line\ncaf\u00e9 and na\u00efve\nthis is damaged \u00e2\u20ac\u201d text\n"
    problems = check_mojibake_text("sample.txt", text)
    assert len(problems) == 1
    assert "sample.txt:3" in problems[0]
    assert "\u00e2\u20ac\u201d" in problems[0]


def test_genuine_accents_and_unrepairable_suspicious_text_are_clean():
    assert check_mojibake_text("sample.txt", "caf\u00e9 na\u00efve \u00e9l\u00e8ve") == []
    assert check_mojibake_text("sample.txt", "x \u00e2\u0081 y") == []


def test_mojibake_scan_skips_frozen_paths():
    assert check_mojibake_text("design/mockups/sample.txt", "\u00e2\u20ac\u201d") == []
    assert check_mojibake_text("docs/history/sample.txt", "\u00e2\u20ac\u201d") == []


def test_forbidden_paths_and_explicit_allowlist():
    tracked = [
        "nested/.stripe_keys.json", "state.db", "vendor/node_modules/a.js",
        "bin/app.exe", "obj/a.o", "dist/site.js", "logs/run.log",
        "reports/out.txt", "screenshots/cap.png", "src/ok.py",
    ]
    forbidden, allowed = find_forbidden_paths(tracked)
    assert set(forbidden) == set(tracked[:-1])
    assert allowed == []
    vm_reports = ["reports/vm/README.md", "reports/vm/2027-01-01-a-future-run.md"]
    forbidden, allowed = find_forbidden_paths(vm_reports)
    assert forbidden == []
    assert allowed == vm_reports


def test_a_quoted_mojibake_example_is_allowed_only_on_its_own_line():
    damaged = "â€”"
    example = f'  // renders as mojibake, an em dash becomes "{damaged}" in the first line\n'
    assert check_mojibake_text("Server/email.js", example) == []
    # The same quote in another file, or real damage elsewhere in the file, still fails.
    assert len(check_mojibake_text("Server/other.js", example)) == 1
    problems = check_mojibake_text("Server/email.js", example + f"const dash = '{damaged}';\n")
    assert len(problems) == 1 and "Server/email.js:2" in problems[0]


def test_pr_body_requires_numbered_issue_and_exempts_steward():
    assert pr_body_problem("Closes #383", "feature/checker") is None
    assert pr_body_problem("Part of #12", "feature/checker") is None
    assert pr_body_problem("closes #9", "feature/checker") is None
    assert pr_body_problem("Closes #", "feature/checker") is not None
    assert pr_body_problem("plain body", "feature/checker") is not None
    assert pr_body_problem("plain body", "docs-steward/run-123") is None


def test_real_repository_has_no_lint_problems():
    assert run_repo_checks(ROOT) == []
