"""
FlowShield issue hygiene check — finds issue state that has quietly stopped
being true.

Issue state here is maintained by hand, and nothing notices when it drifts.
Issue #38 spent six days telling Miles to build three features that had already
shipped, and F20 sat marked "blocked on F19" for a week after F19 merged. Both
were found by a human reading everything, which is not a mechanism.

This reads the open issues and `LAUNCH_FEATURE_CHECKLIST.md` and reports
contradictions between them. It **never edits an issue, a label or a file** —
it prints findings and, in CI, posts them to one standing issue. Everything a
person might disagree with stays a person's decision.

    python tools/issue_hygiene/check.py                 # print findings
    python tools/issue_hygiene/check.py --json          # machine-readable
    python tools/issue_hygiene/check.py --post <issue>  # also comment on an issue

Exit codes: 0 nothing to report, 10 findings, 2 could not run. Findings are
not a failure — a red tick for a stale label would teach people to ignore it.

Needs `gh` on PATH and authenticated. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CHECKLIST = ROOT / "LAUNCH_FEATURE_CHECKLIST.md"

EXIT_OK = 0
EXIT_FINDINGS = 10
EXIT_ERROR = 2

#: Trackers that carry a "reviewed <date>" line, and how long is too long.
TRACKERS = (37, 38)
TRACKER_STALE_DAYS = 14

#: Labels that every open issue should have at least one of. Kept in step with
#: the table in PLANNING.md.
KIND_LABELS = {
    "bug", "enhancement", "design", "infrastructure", "documentation",
    "security", "accessibility", "customer-experience",
    "owner-decision", "docs-steward",
}


@dataclass
class Finding:
    kind: str
    issue: int
    title: str
    detail: str
    fix: str

    def line(self) -> str:
        return f"- **#{self.issue}** — {self.detail}\n  - *{self.fix}*"


# ------------------------------------------------------------------ the checks
#
# Each takes plain data and returns findings, so they can be tested without a
# network or a repo. The gh calls live at the bottom.


def ticked_features(checklist: str) -> dict[str, str]:
    """
    Every feature in the launch checklist whose Done box is ticked, mapped to
    the text of that line (which names the pull request).

    Reads the per-feature sections, not the "Who builds what" table: the table
    is an assignment list and has no boxes.
    """
    ticked: dict[str, str] = {}
    current: str | None = None
    for raw in checklist.splitlines():
        heading = re.match(r"^###\s+(F\d+)\s+—", raw)
        if heading:
            current = heading.group(1)
            continue
        if current and raw.strip().startswith("- [x] Done"):
            ticked[current] = raw.strip()
            current = None
    return ticked


def features_named_in(title: str) -> set[str]:
    """
    Feature numbers a title claims to be about — "F7 (1.7): ..." or "F14: ...".

    Only the leading claim counts. A title that merely mentions F16 as a
    blocker is not about F16, and treating it as such produced noise.
    """
    match = re.match(r"^\s*(F\d+)\b", title)
    return {match.group(1)} if match else set()


def check_shipped_but_open(issues: list[dict], ticked: dict[str, str]) -> list[Finding]:
    """An open issue whose feature is ticked as shipped."""
    out = []
    for issue in issues:
        for feature in features_named_in(issue["title"]) & ticked.keys():
            out.append(Finding(
                kind="shipped-but-open",
                issue=issue["number"],
                title=issue["title"],
                detail=(f"open, but {feature} is ticked as done in the launch "
                        f"checklist: `{ticked[feature]}`"),
                fix=("close it, or retitle it to the part that is left — "
                     "PLANNING.md, 'retitle an issue to what is left'"),
            ))
    return out


def check_blocked_with_no_blocker(issues: list[dict],
                                  state_of: dict[int, str]) -> list[Finding]:
    """
    A `blocked` issue whose named blockers have all closed.

    Only issues referenced in the body count as blockers, and only when there
    is at least one — "blocked" with nothing named is a different finding.
    """
    out = []
    for issue in issues:
        if "blocked" not in issue["labels"]:
            continue
        referenced = {int(n) for n in re.findall(r"#(\d+)", issue.get("body") or "")}
        referenced -= {issue["number"]}
        known = {n: state_of[n] for n in referenced if n in state_of}
        if not known:
            out.append(Finding(
                kind="blocked-without-reason",
                issue=issue["number"],
                title=issue["title"],
                detail="labelled `blocked` but names no issue it waits on",
                fix="say what it waits on in the body, or drop the label",
            ))
        elif all(state == "CLOSED" for state in known.values()):
            names = ", ".join(f"#{n}" for n in sorted(known))
            out.append(Finding(
                kind="blocked-but-unblocked",
                issue=issue["number"],
                title=issue["title"],
                detail=f"labelled `blocked`, but everything it waits on has closed ({names})",
                fix="drop the `blocked` label and put it back in the order of work",
            ))
    return out


def check_tracker_freshness(issues: list[dict], now: datetime,
                            stale_days: int = TRACKER_STALE_DAYS) -> list[Finding]:
    """A tracker whose "reviewed <date>" line has gone stale, or is missing."""
    out = []
    for issue in issues:
        if issue["number"] not in TRACKERS:
            continue
        found = re.search(r"reviewed\s+(\d{1,2}\s+\w+\s+\d{4})",
                          issue.get("body") or "", re.IGNORECASE)
        if not found:
            out.append(Finding(
                kind="tracker-undated",
                issue=issue["number"],
                title=issue["title"],
                detail="has no 'reviewed <date>' line, so nobody can tell if it is current",
                fix="add one to the 'Next up' heading when you next review it",
            ))
            continue
        try:
            reviewed = datetime.strptime(found.group(1), "%d %B %Y").replace(
                tzinfo=timezone.utc)
        except ValueError:
            continue
        age = (now - reviewed).days
        if age > stale_days:
            out.append(Finding(
                kind="tracker-stale",
                issue=issue["number"],
                title=issue["title"],
                detail=f"last reviewed {age} days ago ({found.group(1)})",
                fix="re-read it against the launch checklist; the next-up list is what goes stale",
            ))
    return out


def check_metadata(issues: list[dict]) -> list[Finding]:
    """Open issues with no kind label, or launch work with nobody on it."""
    out = []
    for issue in issues:
        if not (set(issue["labels"]) & KIND_LABELS):
            out.append(Finding(
                kind="unlabelled",
                issue=issue["number"],
                title=issue["title"],
                detail="has no kind label",
                fix="label it — PLANNING.md has the set, and labels go on at claim time",
            ))
        if issue.get("milestone") == "Launch" and not issue["assignees"]:
            out.append(Finding(
                kind="launch-unassigned",
                issue=issue["number"],
                title=issue["title"],
                detail="is on the Launch milestone with nobody assigned",
                fix="assign it, or take it off the milestone if it is not launch-blocking",
            ))
    return out


def run_checks(issues: list[dict], checklist: str, state_of: dict[int, str],
               now: datetime) -> list[Finding]:
    ticked = ticked_features(checklist)
    return [
        *check_shipped_but_open(issues, ticked),
        *check_blocked_with_no_blocker(issues, state_of),
        *check_tracker_freshness(issues, now),
        *check_metadata(issues),
    ]


def report(findings: list[Finding]) -> str:
    """The comment body, grouped so the same kind of drift reads together."""
    if not findings:
        return "No issue-state drift found."

    groups: dict[str, list[Finding]] = {}
    for finding in findings:
        groups.setdefault(finding.kind, []).append(finding)

    headings = {
        "shipped-but-open": "Open, but the work is ticked as shipped",
        "blocked-but-unblocked": "Marked blocked, but nothing is blocking it",
        "blocked-without-reason": "Marked blocked without saying what by",
        "tracker-stale": "Trackers that have not been reviewed lately",
        "tracker-undated": "Trackers with no review date",
        "unlabelled": "No kind label",
        "launch-unassigned": "On the Launch milestone with nobody on it",
    }

    out = ["Automated check of issue state against `LAUNCH_FEATURE_CHECKLIST.md`.",
           "Nothing here has been changed for you — these are suggestions.", ""]
    for kind, items in groups.items():
        out.append(f"### {headings.get(kind, kind)}")
        out.extend(item.line() for item in items)
        out.append("")
    out.append("_`tools/issue_hygiene/check.py`. If a finding is wrong, the check "
               "is wrong — say so and it gets fixed._")
    return "\n".join(out)


# ------------------------------------------------------------------ github

def gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def fetch_issues() -> tuple[list[dict], dict[int, str]]:
    """Open issues in the shape the checks want, and every issue's state."""
    fields = "number,title,body,labels,assignees,milestone,state"
    raw = json.loads(gh("issue", "list", "--state", "all", "--limit", "300",
                        "--json", fields))
    state_of = {item["number"]: item["state"] for item in raw}
    issues = [
        {
            "number": item["number"],
            "title": item["title"],
            "body": item.get("body") or "",
            "labels": [label["name"] for label in item.get("labels") or []],
            "assignees": [a["login"] for a in item.get("assignees") or []],
            "milestone": (item.get("milestone") or {}).get("title"),
        }
        for item in raw if item["state"] == "OPEN"
    ]
    return issues, state_of


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    parser.add_argument("--post", metavar="ISSUE", type=int,
                        help="also comment the report on this issue")
    args = parser.parse_args(argv)

    try:
        issues, state_of = fetch_issues()
        checklist = CHECKLIST.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"could not read the repo's issues: {exc}", file=sys.stderr)
        return EXIT_ERROR

    findings = run_checks(issues, checklist, state_of, datetime.now(timezone.utc))

    if args.json:
        print(json.dumps([finding.__dict__ for finding in findings], indent=2))
    else:
        print(report(findings))

    if args.post and findings:
        try:
            gh("issue", "comment", str(args.post), "--body", report(findings))
            print(f"posted to #{args.post}", file=sys.stderr)
        except Exception as exc:
            print(f"could not post the report: {exc}", file=sys.stderr)
            return EXIT_ERROR

    return EXIT_FINDINGS if findings else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
