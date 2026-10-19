"""Tier 1 repository policy checks for CI."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.fix_mojibake import _RUN, _decode_run  # noqa: E402

# VM bench results land in reports/vm/ on purpose ("Testing on a clean machine"
# in CLAUDE.md), so every report there is allowed, including future ones.
_ALLOWED_FORBIDDEN_PREFIXES = ("reports/vm/",)

# Lines that quote mojibake on purpose, to explain it. Each is pinned by file
# and a fragment of the line, so real damage elsewhere in the same file still
# fails, and editing the line brings the error back. Written with escapes so
# this file doesn't trip its own check.
_EM_DASH_MOJIBAKE = "\u00e2\u20ac\u201d"
_ALLOWED_MOJIBAKE_EXAMPLES = {
    ("Server/email.js", f'an em dash becomes "{_EM_DASH_MOJIBAKE}"'),
    ("automation/tests/test_tier6_email.py", f'sentence rendered as "{_EM_DASH_MOJIBAKE}"'),
    ("tools/fix_mojibake.py", f'three characters "{_EM_DASH_MOJIBAKE}"'),
}
_FORBIDDEN_DIRS = {"node_modules", "bin", "obj", "dist", "logs", "reports", "screenshots"}
_BINARY_EXTENSIONS = {
    ".7z", ".avi", ".bmp", ".dll", ".exe", ".gif", ".ico", ".jpeg", ".jpg",
    ".mp3", ".mp4", ".otf", ".pdf", ".png", ".so", ".ttf", ".wav", ".webm",
    ".woff", ".woff2", ".zip",
}
_PR_ISSUE_REFERENCE = re.compile(
    r"\b(?:closes|fixes|resolves)\s+#\d+\b|\bpart\s+of\s+#\d+\b",
    re.IGNORECASE,
)


def check_mojibake_text(path: str, text: str) -> list[str]:
    """Return one path:line diagnostic for every repairable damaged run."""
    normalized = path.replace("\\", "/")
    if normalized.startswith("design/mockups/") or normalized.startswith("docs/history/"):
        return []
    problems: list[str] = []
    for match in _RUN.finditer(text):
        suspicious = match.group(0)
        if _decode_run(suspicious) == suspicious:
            continue
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        line_text = text[line_start:line_end if line_end != -1 else len(text)]
        if any(normalized == allowed_path and fragment in line_text
               for allowed_path, fragment in _ALLOWED_MOJIBAKE_EXAMPLES):
            continue
        line = text.count("\n", 0, match.start()) + 1
        problems.append(
            f"{path}:{line}: suspicious CP1252 round-trip text {suspicious!r}; "
            f"run python tools/fix_mojibake.py {path}"
        )
    return problems


def _is_forbidden(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    if ".stripe_keys.json" in parts:
        return True
    if any(part.lower().endswith(".db") for part in parts):
        return True
    return any(part.lower() in _FORBIDDEN_DIRS for part in parts[:-1])


def find_forbidden_paths(tracked_paths: Iterable[str]) -> tuple[list[str], list[str]]:
    """Split tracked paths into forbidden and explicitly allowlisted paths."""
    forbidden: list[str] = []
    allowed: list[str] = []
    for path in tracked_paths:
        if not _is_forbidden(path):
            continue
        normalized = path.replace("\\", "/")
        if normalized.startswith(_ALLOWED_FORBIDDEN_PREFIXES):
            allowed.append(path)
        else:
            forbidden.append(path)
    return forbidden, allowed


def _tracked_paths(root: Path) -> list[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    return [p.decode("utf-8", errors="surrogateescape") for p in output.split(b"\0") if p]


def _is_binary(path: str, data: bytes) -> bool:
    return Path(path).suffix.lower() in _BINARY_EXTENSIONS or b"\0" in data


def run_repo_checks(root: Path = ROOT) -> list[str]:
    """Run tracked-file mojibake and forbidden-path checks."""
    root = Path(root).resolve()
    tracked = _tracked_paths(root)
    problems: list[str] = []
    for path in tracked:
        normalized = path.replace("\\", "/")
        if normalized.startswith(("design/mockups/", "docs/history/")):
            continue
        if Path(path).suffix.lower() in _BINARY_EXTENSIONS:
            continue
        full_path = root / Path(path)
        try:
            data = full_path.read_bytes()
        except OSError:
            continue
        if _is_binary(path, data):
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        problems.extend(check_mojibake_text(path, text))

    forbidden, _allowed = find_forbidden_paths(tracked)
    for path in forbidden:
        problems.append(f"{path}: forbidden tracked path")
    return problems


def pr_body_problem(body: str, head_ref: str) -> str | None:
    """Return a diagnostic when a pull request body does not link an issue."""
    if head_ref.startswith("docs-steward/") or _PR_ISSUE_REFERENCE.search(body):
        return None
    return "pull request body must include Closes/Fixes/Resolves #<n> or Part of #<n>"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr-body-file", type=Path)
    parser.add_argument("--head-ref")
    args = parser.parse_args(argv)

    problems = run_repo_checks()
    if args.pr_body_file is not None or args.head_ref is not None:
        if args.pr_body_file is None or args.head_ref is None:
            parser.error("--pr-body-file and --head-ref must be provided together")
        body = args.pr_body_file.read_text(encoding="utf-8")
        pr_problem = pr_body_problem(body, args.head_ref)
        if pr_problem:
            problems.append(pr_problem)

    if problems:
        print("\n".join(f"ERROR: {problem}" for problem in problems))
        return 1
    print("Repository checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
