# Notion Human Space Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FlowShield space in Notion: Start here, Ideas, How FlowShield works, Decisions, and Weekly digest. Add a small, tested helper on Miles's PC that reads GitHub and the repo so the weekly job and the idea-to-issue flow can keep Notion in step with GitHub.

**Architecture:** The work splits along one line. **A local Python helper (`flowsync`) does everything deterministic**: which explainer pages are stale, which PRs touched them, what happened on GitHub this week, which ideas have shipped, and whether a page was edited by a human. It only ever *reads* GitHub (via `gh`) and the repo (via `git`), and prints JSON. **Claude does everything that needs judgement or Notion access**: writing explainer prose, drafting issues, and creating and updating Notion pages through the Notion connector. Claude runs `flowsync` and acts on its JSON. The weekly job is a Claude desktop scheduled task whose prompt lives in a file next to the helper.

**Tech Stack:**
- Python 3.14 (standard library only) and pytest 9 for the helper
- `git` and `gh` 2.100 CLIs
- the Notion connector (claude.ai, already authorised to "Miles's Space")
- Claude desktop scheduled tasks

**Spec:** `docs/superpowers/specs/2026-09-21-notion-human-space-design.md` (issue #226, PR #227). Read it before starting.

## Global Constraints

- The GitHub repo is `seventycookies6-design/flowshield`. The local clone is `C:\Users\miles\Projects\FlowShield`.
- The helper lives **outside the repo**, at `C:\Users\miles\flowshield-notion\`. Logs go to `C:\Users\miles\flowshield-notion\logs\` and state to `C:\Users\miles\flowshield-notion\state.json`.
- **The helper never writes to GitHub, and never changes the working tree, index, or branches of the local clone.** Its only git side effect is `git fetch origin main`. It compares against `origin/main`.
- **The weekly job never writes to GitHub.** The only path that writes to GitHub is idea to issue, and it needs Miles's explicit yes to the drafts in chat.
- Everything in Notion sits under one top-level page, `FlowShield`, in "Miles's Space". Never move a FlowShield page out of it, and never restrict a sub-page.
- **Nothing sensitive goes into Notion:** no secrets, keys, tokens, customer data, licence keys, or `.stripe_keys.json` contents. Every block of text bound for Notion passes `flowsync scan` first.
- **Nothing is deleted automatically**, in Notion or anywhere else.
- **Ideas status values:** Raw, Discussing, Ready, Sent to GitHub, Shipped, Parked.
- **Ideas Area values:** App, Site, Server, Design, Business, Legal.
- **Explainer State values:** Current, Updated this week, Needs a human look.
- **Decisions Status values:** Active, Superseded, Proposed.
- **Weekly job schedule:** Mondays, 8 AM local (cron `0 8 * * 1`).
- **Explainer pages have two layers:** "The short version" (plain language, no code) and "Under the hood" (files, classes, connections, rules).
- The `CLAUDE.md` line goes in a **separate PR**, verbatim from the spec. Agents never merge.
- Keenan is invited by Miles, as a guest, using `mcmahonkeenan6@gmail.com`, at *Can edit*, on the `FlowShield` page only. Claude does not send invites.

## Review Focus

These are the inputs the spec implies but doesn't spell out, most likely to bite first. Each one gets a test in the task that owns the code.

1. **An explainer's "Checked at commit" is blank or no longer exists** (first run, or history rewritten). Expected: treat it as a full rewrite of that page, not a crash and not "nothing changed". *Test in Task 3.*
2. **A page's source path was renamed or deleted on `main`.** Expected: the page is flagged **Needs a human look** with the missing path named, not silently stamped Current. *Test in Task 3.*
3. **An idea's "GitHub issue" field holds something that isn't an issue in this repo** (a PR URL, another repo, a typo). Expected: that idea is skipped with a reason, and the other ideas still update. *Test in Task 4.*
4. **`gh` isn't signed in, or the network is down, at 8 AM.** Expected: non-zero exit, a log entry, and no partial JSON, so the job writes nothing to Notion that week. *Test in Task 5.*
5. **A week with no activity at all.** Expected: the digest is still produced, with empty lists marked `quiet: true`, so the week isn't silently missing. *Test in Task 5.*

---

## File Structure

All under `C:\Users\miles\flowshield-notion\`, a local git repo that is never pushed:

| File | Responsibility |
| --- | --- |
| `flowsync/__init__.py` | package marker |
| `flowsync/paths.py` | parse a page's Source paths; match changed files to pages |
| `flowsync/gitinfo.py` | read-only git: fetch, head SHA, commit exists, changed files, PR numbers in a range |
| `flowsync/refresh.py` | decide per explainer page: `stamp`, `rewrite`, or `human-look` |
| `flowsync/github.py` | read-only `gh`: weekly digest data, idea issue states |
| `flowsync/guard.py` | secret scan for text bound for Notion |
| `flowsync/state.py` | load and save `state.json` atomically; record the job's own writes |
| `flowsync/cli.py` | `python -m flowsync <command>`: JSON out, logging, exit codes |
| `flowsync/__main__.py` | entry point for `python -m flowsync` |
| `tests/test_*.py` | one test file per module |
| `prompts/weekly-job.md` | the weekly scheduled task's full prompt |
| `prompts/send-ready-ideas.md` | the on-request idea-to-issue procedure |
| `prompts/explainer-style.md` | how an explainer page is written (two layers) |

In the FlowShield repo: the plan (this file) goes on the `docs/notion-human-space` branch (PR #227). The `CLAUDE.md` line goes on a new branch in its own PR (Task 12).

---

### Task 1: Helper scaffold and source-path matching

**Files:**
- Create: `C:\Users\miles\flowshield-notion\flowsync\__init__.py`
- Create: `C:\Users\miles\flowshield-notion\flowsync\paths.py`
- Create: `C:\Users\miles\flowshield-notion\tests\test_paths.py`
- Create: `C:\Users\miles\flowshield-notion\.gitignore`

**Interfaces:**
- Produces:
  - `parse_source_paths(text: str) -> list[str]`
  - `path_matches(source: str, changed: str) -> bool`
  - `page_changes(sources: list[str], changed_files: list[str]) -> list[str]` (the changed files that fall under the page, sorted)

- [ ] **Step 1: Create the folder, local git repo, and ignore file**

```bash
mkdir -p /c/Users/miles/flowshield-notion/flowsync /c/Users/miles/flowshield-notion/tests /c/Users/miles/flowshield-notion/prompts /c/Users/miles/flowshield-notion/logs
cd /c/Users/miles/flowshield-notion && git init -q
printf 'logs/\nstate.json\n__pycache__/\n.pytest_cache/\n' > .gitignore
: > flowsync/__init__.py
```

- [ ] **Step 2: Write the failing tests**

`tests/test_paths.py`:

```python
from flowsync.paths import parse_source_paths, path_matches, page_changes


def test_parse_splits_on_commas_and_newlines_and_strips_backticks():
    text = "`Server/`, DesktopApp/Services/LicenseService.cs\n  README.md  "
    assert parse_source_paths(text) == [
        "Server/", "DesktopApp/Services/LicenseService.cs", "README.md"]


def test_parse_ignores_blanks():
    assert parse_source_paths(" , \n\n") == []


def test_folder_source_matches_anything_beneath_it():
    assert path_matches("Server/", "Server/db.js")
    assert path_matches("Server/", "Server/lib/x.js")


def test_folder_source_does_not_match_a_sibling_with_the_same_prefix():
    assert not path_matches("Server/", "ServerTools/run.js")


def test_file_source_matches_only_that_file():
    assert path_matches("README.md", "README.md")
    assert not path_matches("README.md", "README.md.bak")


def test_folder_given_without_trailing_slash_still_matches_as_folder():
    assert path_matches("Website", "Website/index.html")
    assert not path_matches("Website", "Websites/x")


def test_page_changes_returns_only_files_under_the_page_sorted():
    sources = ["Server/", "DesktopApp/Services/LicenseService.cs"]
    changed = ["Website/index.html", "Server/db.js",
               "DesktopApp/Services/LicenseService.cs", "Server/app.js"]
    assert page_changes(sources, changed) == [
        "DesktopApp/Services/LicenseService.cs", "Server/app.js", "Server/db.js"]
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd /c/Users/miles/flowshield-notion && python -m pytest tests/test_paths.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'flowsync.paths'`

- [ ] **Step 4: Implement**

`flowsync/paths.py`:

```python
"""Which explainer page a changed file belongs to."""
import re


def parse_source_paths(text: str) -> list[str]:
    parts = re.split(r"[,\n]", text or "")
    return [p.strip().strip("`").strip() for p in parts if p.strip().strip("`").strip()]


def path_matches(source: str, changed: str) -> bool:
    source = source.replace("\\", "/")
    changed = changed.replace("\\", "/")
    if source.endswith("/"):
        return changed.startswith(source)
    if changed == source:
        return True
    # A source without a dot in its last segment is treated as a folder.
    if "." not in source.rsplit("/", 1)[-1]:
        return changed.startswith(source + "/")
    return False


def page_changes(sources: list[str], changed_files: list[str]) -> list[str]:
    return sorted({f for f in changed_files if any(path_matches(s, f) for s in sources)})
```

- [ ] **Step 5: Run to verify they pass**

Run: `python -m pytest tests/test_paths.py -q`
Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -q -m "flowsync: source-path parsing and matching"
```

---

### Task 2: Read-only git information

**Files:**
- Create: `C:\Users\miles\flowshield-notion\flowsync\gitinfo.py`
- Create: `C:\Users\miles\flowshield-notion\tests\test_gitinfo.py`

**Interfaces:**
- Produces:
  - `class GitError(Exception)`
  - `fetch(repo: str) -> None` (runs `git fetch -q origin main`)
  - `head_sha(repo: str, ref: str = "origin/main") -> str`
  - `commit_exists(repo: str, sha: str) -> bool`
  - `changed_files(repo: str, base: str, head: str) -> list[str]`
  - `existing_paths(repo: str, head: str, paths: list[str]) -> dict[str, bool]`
  - `prs_touching(repo: str, base: str, head: str, files: list[str]) -> list[int]` (PR numbers parsed from `(#123)` in commit subjects, sorted, unique)

- [ ] **Step 1: Write the failing tests** (a throwaway repo per test; nothing touches the real clone)

`tests/test_gitinfo.py`:

```python
import subprocess
import pytest
from flowsync import gitinfo


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "Server").mkdir()
    (tmp_path / "Server" / "db.js").write_text("a")
    (tmp_path / "README.md").write_text("r")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "Initial (#1)")
    return tmp_path


def commit(repo, path, text, msg):
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def test_head_sha_and_commit_exists(repo):
    head = gitinfo.head_sha(str(repo), "HEAD")
    assert len(head) == 40
    assert gitinfo.commit_exists(str(repo), head)
    assert not gitinfo.commit_exists(str(repo), "0" * 40)
    assert not gitinfo.commit_exists(str(repo), "")


def test_changed_files_between_two_commits(repo):
    base = gitinfo.head_sha(str(repo), "HEAD")
    commit(repo, "Server/db.js", "b", "Fix db (#10)")
    head = commit(repo, "Website/index.html", "w", "Site (#11)")
    assert gitinfo.changed_files(str(repo), base, head) == [
        "Server/db.js", "Website/index.html"]


def test_prs_touching_only_counts_commits_that_touch_the_files(repo):
    base = gitinfo.head_sha(str(repo), "HEAD")
    commit(repo, "Server/db.js", "b", "Fix db (#10)")
    commit(repo, "Website/index.html", "w", "Site (#11)")
    head = commit(repo, "Server/db.js", "c", "Merge pull request #12 from x/y")
    assert gitinfo.prs_touching(str(repo), base, head, ["Server/db.js"]) == [10, 12]


def test_prs_touching_with_no_files_is_empty(repo):
    head = gitinfo.head_sha(str(repo), "HEAD")
    assert gitinfo.prs_touching(str(repo), head, head, []) == []


def test_existing_paths_reports_deleted_files_and_folders(repo):
    head = gitinfo.head_sha(str(repo), "HEAD")
    assert gitinfo.existing_paths(str(repo), head, ["Server/", "README.md", "Gone.cs"]) == {
        "Server/": True, "README.md": True, "Gone.cs": False}


def test_a_bad_ref_raises_giterror(repo):
    with pytest.raises(gitinfo.GitError):
        gitinfo.changed_files(str(repo), "nope", "HEAD")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_gitinfo.py -q`
Expected: FAIL with `ImportError: cannot import name 'gitinfo'`

- [ ] **Step 3: Implement**

`flowsync/gitinfo.py`:

```python
"""Read-only git. The only side effect anywhere in here is `git fetch`."""
import re
import subprocess


class GitError(Exception):
    pass


def _git(repo: str, *args: str) -> str:
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def fetch(repo: str) -> None:
    _git(repo, "fetch", "-q", "origin", "main")


def head_sha(repo: str, ref: str = "origin/main") -> str:
    return _git(repo, "rev-parse", ref).strip()


def commit_exists(repo: str, sha: str) -> bool:
    if not sha or not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        return False
    r = subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{sha}^{{commit}}"],
                       capture_output=True, text=True)
    return r.returncode == 0


def changed_files(repo: str, base: str, head: str) -> list[str]:
    out = _git(repo, "diff", "--name-only", f"{base}..{head}")
    return sorted(line for line in out.splitlines() if line)


def existing_paths(repo: str, head: str, paths: list[str]) -> dict[str, bool]:
    result = {}
    for p in paths:
        r = subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{head}:{p.rstrip('/')}"],
                           capture_output=True, text=True)
        result[p] = r.returncode == 0
    return result


_PR = re.compile(r"\(#(\d+)\)|pull request #(\d+)")


def prs_touching(repo: str, base: str, head: str, files: list[str]) -> list[int]:
    if not files:
        return []
    out = _git(repo, "log", "--format=%s", f"{base}..{head}", "--", *files)
    numbers = set()
    for line in out.splitlines():
        for a, b in _PR.findall(line):
            numbers.add(int(a or b))
    return sorted(numbers)
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_gitinfo.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "flowsync: read-only git queries"
```

---

### Task 3: Refresh decision per explainer page

**Files:**
- Create: `C:\Users\miles\flowshield-notion\flowsync\refresh.py`
- Create: `C:\Users\miles\flowshield-notion\tests\test_refresh.py`

**Interfaces:**
- Consumes: `paths.parse_source_paths`, `paths.page_changes`, and all of `gitinfo` (Task 2)
- Produces: `plan_refresh(repo: str, head: str, pages: list[dict], last_writes: dict[str, str], grace_seconds: int = 120) -> list[dict]`
  - Input page dict: `{"page_id": str, "area": str, "source_paths": str, "checked_at": str, "last_edited": str}` (ISO-8601 times)
  - Output, one per page: `{"page_id", "area", "action": "stamp"|"rewrite"|"human-look", "reason": str, "changed_files": list[str], "prs": list[int], "missing_paths": list[str], "head": str}`

The rules, in order:
1. A source path missing at `head` → `human-look`, reason `missing path`.
2. `checked_at` blank or not a known commit → `rewrite`, reason `no valid checked-at commit`, with `changed_files` = every file currently under the page.
3. No files under the page changed since `checked_at` → `stamp`, reason `no changes`. This applies even if a person edited the page, because stamping only touches Last checked.
4. Files changed, and the page was edited by a person since the job last wrote it (`last_edited` more than `grace_seconds` after `last_writes[page_id]`) → `human-look`, reason `edited by a person`.
5. Otherwise → `rewrite`, reason `code changed`.

- [ ] **Step 1: Write the failing tests** (they reuse the throwaway-repo helpers)

`tests/test_refresh.py`:

```python
import subprocess
import pytest
from flowsync.refresh import plan_refresh


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(repo, path, text, msg):
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    commit(tmp_path, "Server/db.js", "a", "Initial (#1)")
    commit(tmp_path, "Website/index.html", "w", "Site (#2)")
    return tmp_path


def page(checked_at, sources="Server/", last_edited="2026-09-21T10:00:00Z", pid="p1"):
    return {"page_id": pid, "area": "Server", "source_paths": sources,
            "checked_at": checked_at, "last_edited": last_edited}


def test_unchanged_page_is_only_stamped(repo):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, "Website/index.html", "w2", "Site again (#3)")
    [p] = plan_refresh(str(repo), head, [page(base)], {})
    assert p["action"] == "stamp"
    assert p["changed_files"] == []


def test_changed_page_is_rewritten_with_its_prs(repo):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, "Server/db.js", "b", "Fix db (#4)")
    [p] = plan_refresh(str(repo), head, [page(base)], {})
    assert p["action"] == "rewrite"
    assert p["changed_files"] == ["Server/db.js"]
    assert p["prs"] == [4]
    assert p["head"] == head


# Review Focus 1
@pytest.mark.parametrize("checked_at", ["", "deadbeef" * 5, "not-a-sha"])
def test_blank_or_unknown_checked_at_means_full_rewrite(repo, checked_at):
    head = git(repo, "rev-parse", "HEAD")
    [p] = plan_refresh(str(repo), head, [page(checked_at)], {})
    assert p["action"] == "rewrite"
    assert p["reason"] == "no valid checked-at commit"
    assert p["changed_files"] == ["Server/db.js"]


# Review Focus 2
def test_a_deleted_source_path_needs_a_human(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "rm", "-q", "Server/db.js")
    git(repo, "commit", "-q", "-m", "Drop server (#5)")
    head = git(repo, "rev-parse", "HEAD")
    [p] = plan_refresh(str(repo), head, [page(base, sources="Server/, Website/")], {})
    assert p["action"] == "human-look"
    assert p["reason"] == "missing path"
    assert p["missing_paths"] == ["Server/"]


def test_a_person_edited_page_with_changed_code_is_not_overwritten(repo):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, "Server/db.js", "b", "Fix db (#4)")
    edited = page(base, last_edited="2026-09-21T12:00:00Z")
    [p] = plan_refresh(str(repo), head, [edited], {"p1": "2026-09-21T10:00:00Z"})
    assert p["action"] == "human-look"
    assert p["reason"] == "edited by a person"


def test_the_jobs_own_write_is_not_mistaken_for_a_person(repo):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, "Server/db.js", "b", "Fix db (#4)")
    own = page(base, last_edited="2026-09-21T10:01:00Z")
    [p] = plan_refresh(str(repo), head, [own], {"p1": "2026-09-21T10:00:00Z"})
    assert p["action"] == "rewrite"


def test_a_person_edit_with_no_code_change_is_just_stamped(repo):
    base = git(repo, "rev-parse", "HEAD")
    head = commit(repo, "Website/index.html", "w2", "Site (#6)")
    edited = page(base, last_edited="2026-09-21T12:00:00Z")
    [p] = plan_refresh(str(repo), head, [edited], {"p1": "2026-09-21T10:00:00Z"})
    assert p["action"] == "stamp"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_refresh.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'flowsync.refresh'`

- [ ] **Step 3: Implement**

`flowsync/refresh.py`:

```python
"""Decide, per explainer page, whether to stamp it, rewrite it, or ask a human."""
from datetime import datetime, timedelta
from flowsync import gitinfo
from flowsync.paths import parse_source_paths, page_changes


def _when(iso: str):
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _edited_by_person(page: dict, last_writes: dict, grace: int) -> bool:
    edited = _when(page.get("last_edited", ""))
    wrote = _when(last_writes.get(page["page_id"], ""))
    if edited is None or wrote is None:
        return False
    return edited > wrote + timedelta(seconds=grace)


def _all_files_under(repo: str, head: str, sources: list[str]) -> list[str]:
    out = gitinfo._git(repo, "ls-tree", "-r", "--name-only", head)
    return page_changes(sources, out.splitlines())


def plan_refresh(repo, head, pages, last_writes, grace_seconds=120):
    plans = []
    for page in pages:
        sources = parse_source_paths(page["source_paths"])
        result = {"page_id": page["page_id"], "area": page["area"], "head": head,
                  "changed_files": [], "prs": [], "missing_paths": []}

        exists = gitinfo.existing_paths(repo, head, sources)
        missing = [p for p in sources if not exists[p]]
        if missing:
            result.update(action="human-look", reason="missing path", missing_paths=missing)
            plans.append(result)
            continue

        base = page.get("checked_at", "")
        if not gitinfo.commit_exists(repo, base):
            result.update(action="rewrite", reason="no valid checked-at commit",
                          changed_files=_all_files_under(repo, head, sources))
            plans.append(result)
            continue

        changed = page_changes(sources, gitinfo.changed_files(repo, base, head))
        if not changed:
            result.update(action="stamp", reason="no changes")
        elif _edited_by_person(page, last_writes, grace_seconds):
            result.update(action="human-look", reason="edited by a person",
                          changed_files=changed,
                          prs=gitinfo.prs_touching(repo, base, head, changed))
        else:
            result.update(action="rewrite", reason="code changed", changed_files=changed,
                          prs=gitinfo.prs_touching(repo, base, head, changed))
        plans.append(result)
    return plans
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_refresh.py -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "flowsync: per-page refresh decision"
```

---

### Task 4: Idea status from GitHub issues

**Files:**
- Create: `C:\Users\miles\flowshield-notion\flowsync\github.py`
- Create: `C:\Users\miles\flowshield-notion\tests\test_github_ideas.py`

**Interfaces:**
- Produces:
  - `REPO = "seventycookies6-design/flowshield"`
  - `class GhError(Exception)`
  - `Runner = Callable[[list[str]], str]`, with `default_runner(args) -> str` running `gh` and raising `GhError` on failure
  - `issue_number(url: str) -> int | None` (only issues in `REPO`)
  - `idea_updates(ideas: list[dict], run: Runner = default_runner) -> list[dict]`
    - Input: `{"page_id": str, "issue_url": str}`
    - Output, one per idea: `{"page_id", "new_status": "Shipped"|"Parked"|None, "note": str}`

- [ ] **Step 1: Write the failing tests**

`tests/test_github_ideas.py`:

```python
import json
from flowsync.github import issue_number, idea_updates


def fake(responses):
    def run(args):
        n = args[args.index("view") + 1]
        return json.dumps(responses[n])
    return run


def test_issue_number_accepts_this_repos_issues_in_any_case():
    assert issue_number("https://github.com/seventycookies6-design/flowshield/issues/226") == 226
    assert issue_number("https://github.com/seventycookies6-design/FlowShield/issues/7/") == 7


# Review Focus 3
def test_issue_number_rejects_prs_other_repos_and_junk():
    assert issue_number("https://github.com/seventycookies6-design/flowshield/pull/227") is None
    assert issue_number("https://github.com/someone/else/issues/3") is None
    assert issue_number("issue 12") is None
    assert issue_number("") is None


def test_closed_completed_is_shipped_not_planned_is_parked_open_is_unchanged():
    run = fake({"1": {"state": "CLOSED", "stateReason": "COMPLETED"},
                "2": {"state": "CLOSED", "stateReason": "NOT_PLANNED"},
                "3": {"state": "OPEN", "stateReason": ""}})
    base = "https://github.com/seventycookies6-design/flowshield/issues/"
    out = idea_updates([{"page_id": "a", "issue_url": base + "1"},
                        {"page_id": "b", "issue_url": base + "2"},
                        {"page_id": "c", "issue_url": base + "3"}], run)
    assert [o["new_status"] for o in out] == ["Shipped", "Parked", None]
    assert "not planned" in out[1]["note"]


# Review Focus 3
def test_a_bad_link_is_skipped_with_a_note_and_the_rest_still_update():
    run = fake({"1": {"state": "CLOSED", "stateReason": "COMPLETED"}})
    out = idea_updates([
        {"page_id": "bad", "issue_url": "https://github.com/seventycookies6-design/flowshield/pull/9"},
        {"page_id": "ok", "issue_url": "https://github.com/seventycookies6-design/flowshield/issues/1"}], run)
    assert out[0] == {"page_id": "bad", "new_status": None,
                      "note": "GitHub issue link is not an issue in this repo"}
    assert out[1]["new_status"] == "Shipped"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_github_ideas.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'flowsync.github'`

- [ ] **Step 3: Implement**

`flowsync/github.py`:

```python
"""Read-only GitHub, through the gh CLI. Nothing in here writes to GitHub."""
import json
import re
import subprocess
from typing import Callable

REPO = "seventycookies6-design/flowshield"
Runner = Callable[[list[str]], str]


class GhError(Exception):
    pass


def default_runner(args: list[str]) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise GhError(f"gh {' '.join(args[:2])}: {r.stderr.strip()}")
    return r.stdout


_ISSUE = re.compile(r"^https://github\.com/seventycookies6-design/flowshield/issues/(\d+)/?$",
                    re.IGNORECASE)


def issue_number(url: str) -> int | None:
    m = _ISSUE.match((url or "").strip())
    return int(m.group(1)) if m else None


def idea_updates(ideas: list[dict], run: Runner = default_runner) -> list[dict]:
    out = []
    for idea in ideas:
        n = issue_number(idea.get("issue_url", ""))
        if n is None:
            out.append({"page_id": idea["page_id"], "new_status": None,
                        "note": "GitHub issue link is not an issue in this repo"})
            continue
        data = json.loads(run(["issue", "view", str(n), "-R", REPO,
                               "--json", "state,stateReason"]))
        if data["state"] == "CLOSED" and data.get("stateReason") == "NOT_PLANNED":
            out.append({"page_id": idea["page_id"], "new_status": "Parked",
                        "note": f"Issue #{n} was closed as not planned"})
        elif data["state"] == "CLOSED":
            out.append({"page_id": idea["page_id"], "new_status": "Shipped",
                        "note": f"Issue #{n} was closed as completed"})
        else:
            out.append({"page_id": idea["page_id"], "new_status": None, "note": ""})
    return out
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_github_ideas.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "flowsync: idea status from issue state"
```

---

### Task 5: Weekly digest data

**Files:**
- Modify: `C:\Users\miles\flowshield-notion\flowsync\github.py` (append)
- Create: `C:\Users\miles\flowshield-notion\tests\test_github_digest.py`

**Interfaces:**
- Consumes: `REPO`, `Runner`, `default_runner`, `GhError` (Task 4)
- Produces: `digest(since: str, run: Runner = default_runner) -> dict` where `since` is an ISO date (`YYYY-MM-DD`) and the result is:
  `{"since", "merged": [pr], "opened": [pr], "issues_opened": [issue], "issues_closed": [issue], "waiting": {"unreviewed_prs": [pr], "conflicting_prs": [pr], "owner_decisions": [issue]}, "failed_runs": [run], "quiet": bool}`
  Each `pr` or `issue` is `{"number", "title", "url", "author"}`. Each `run` is `{"name", "branch", "url"}`.

- [ ] **Step 1: Write the failing tests**

`tests/test_github_digest.py`:

```python
import json
import pytest
from flowsync.github import digest, GhError

PR = {"number": 5, "title": "Fix", "url": "u5", "author": {"login": "keenan"},
      "reviewDecision": "", "mergeable": "MERGEABLE"}


def router(table):
    def run(args):
        key = " ".join(args[:2])
        for prefix, payload in table.items():
            if key.startswith(prefix) and all(t in args for t in payload.get("_needs", [])):
                return json.dumps(payload["rows"])
        return "[]"
    return run


def test_digest_sorts_activity_into_its_buckets():
    run = router({
        "pr list": {"rows": [PR]},
        "issue list": {"rows": [{"number": 9, "title": "Idea", "url": "u9",
                                  "author": {"login": "miles"}}]},
        "run list": {"rows": [{"name": "CI", "headBranch": "main", "url": "r1"}]},
    })
    d = digest("2026-09-14", run)
    assert d["merged"][0] == {"number": 5, "title": "Fix", "url": "u5", "author": "keenan"}
    assert d["failed_runs"] == [{"name": "CI", "branch": "main", "url": "r1"}]
    assert d["quiet"] is False


def test_conflicting_and_unreviewed_open_prs_are_waiting_on_a_human():
    conflicting = dict(PR, number=6, mergeable="CONFLICTING", reviewDecision="APPROVED")
    run = router({"pr list": {"rows": [PR, conflicting]}})
    d = digest("2026-09-14", run)
    assert [p["number"] for p in d["waiting"]["unreviewed_prs"]] == [5]
    assert [p["number"] for p in d["waiting"]["conflicting_prs"]] == [6]


# Review Focus 5
def test_a_quiet_week_still_produces_a_digest():
    d = digest("2026-09-14", lambda args: "[]")
    assert d["quiet"] is True
    assert d["merged"] == [] and d["failed_runs"] == []
    assert d["since"] == "2026-09-14"


# Review Focus 4
def test_gh_failing_raises_instead_of_returning_a_partial_digest():
    def broken(args):
        raise GhError("gh auth: not logged in")
    with pytest.raises(GhError):
        digest("2026-09-14", broken)


def test_since_must_be_a_plain_date():
    with pytest.raises(ValueError):
        digest("last week", lambda a: "[]")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_github_digest.py -q`
Expected: FAIL with `ImportError: cannot import name 'digest'`

- [ ] **Step 3: Implement** (append to `flowsync/github.py`)

```python
from datetime import date

_PR_FIELDS = "number,title,url,author,reviewDecision,mergeable"


def _item(row: dict) -> dict:
    author = row.get("author") or {}
    return {"number": row["number"], "title": row["title"], "url": row["url"],
            "author": author.get("login", "")}


def _json(run: Runner, args: list[str]) -> list[dict]:
    return json.loads(run(args) or "[]")


def digest(since: str, run: Runner = default_runner) -> dict:
    date.fromisoformat(since)  # raises ValueError for anything but YYYY-MM-DD
    base = ["-R", REPO, "--limit", "100"]
    merged = _json(run, ["pr", "list", *base, "--state", "merged",
                         "--search", f"merged:>={since}", "--json", _PR_FIELDS])
    opened = _json(run, ["pr", "list", *base, "--state", "all",
                         "--search", f"created:>={since}", "--json", _PR_FIELDS])
    open_prs = _json(run, ["pr", "list", *base, "--state", "open", "--json", _PR_FIELDS])
    issues_opened = _json(run, ["issue", "list", *base, "--state", "all",
                                "--search", f"created:>={since}",
                                "--json", "number,title,url,author"])
    issues_closed = _json(run, ["issue", "list", *base, "--state", "closed",
                                "--search", f"closed:>={since}",
                                "--json", "number,title,url,author"])
    owner = _json(run, ["issue", "list", *base, "--state", "open",
                        "--label", "owner-decision", "--json", "number,title,url,author"])
    failed = _json(run, ["run", "list", "-R", REPO, "--limit", "100", "--status", "failure",
                         "--created", f">={since}", "--json", "name,headBranch,url"])

    result = {
        "since": since,
        "merged": [_item(r) for r in merged],
        "opened": [_item(r) for r in opened],
        "issues_opened": [_item(r) for r in issues_opened],
        "issues_closed": [_item(r) for r in issues_closed],
        "waiting": {
            "unreviewed_prs": [_item(r) for r in open_prs if not r.get("reviewDecision")],
            "conflicting_prs": [_item(r) for r in open_prs if r.get("mergeable") == "CONFLICTING"],
            "owner_decisions": [_item(r) for r in owner],
        },
        "failed_runs": [{"name": r["name"], "branch": r["headBranch"], "url": r["url"]}
                        for r in failed],
    }
    result["quiet"] = not any([result["merged"], result["opened"], result["issues_opened"],
                               result["issues_closed"], result["failed_runs"]])
    return result
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_github_digest.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -q -m "flowsync: weekly digest data"
```

---

### Task 6: Secret guard, state file, and CLI

**Files:**
- Create: `C:\Users\miles\flowshield-notion\flowsync\guard.py`
- Create: `C:\Users\miles\flowshield-notion\flowsync\state.py`
- Create: `C:\Users\miles\flowshield-notion\flowsync\cli.py`
- Create: `C:\Users\miles\flowshield-notion\flowsync\__main__.py`
- Create: `C:\Users\miles\flowshield-notion\tests\test_guard.py`
- Create: `C:\Users\miles\flowshield-notion\tests\test_cli.py`

**Interfaces:**
- Consumes: `plan_refresh` (Task 3), `idea_updates` and `digest` (Tasks 4–5), and `gitinfo.fetch` and `gitinfo.head_sha` (Task 2)
- Produces:
  - `guard.find_secrets(text: str) -> list[str]` (names of the patterns found; empty means clean)
  - `state.load(path) -> dict`, `state.save(path, data) -> None` (atomic), `state.record_write(path, page_id, when_iso) -> None`
  - The CLI, `python -m flowsync <command>`, run from `C:\Users\miles\flowshield-notion`:
    - `head`: fetches, then prints `{"head": sha}`
    - `refresh-plan --pages FILE`: fetches, then prints the `plan_refresh` list
    - `digest [--since YYYY-MM-DD]`: prints the digest. `--since` defaults to `state.digest_since`, else 7 days ago.
    - `digest-done --until YYYY-MM-DD`: stores `digest_since`
    - `ideas --ideas FILE`: prints the `idea_updates` list
    - `scan --file FILE`: prints `{"clean": bool, "found": [...]}`, and exits 3 if not clean
    - `record-write --page ID`: stores now as that page's last write
  - Exit codes: 0 success; 2 any git or gh failure (logged, **nothing printed to stdout**); 3 secrets found.

- [ ] **Step 1: Write the failing tests**

`tests/test_guard.py`:

```python
from flowsync.guard import find_secrets


def test_clean_prose_passes():
    assert find_secrets("The licence server stores keys in SQLite and checks them on start.") == []


def test_stripe_and_other_keys_are_caught():
    text = "use sk_live_" + "a" * 24 + " and whsec_" + "b" * 24
    assert set(find_secrets(text)) >= {"stripe secret key", "stripe webhook secret"}


def test_github_tokens_and_private_keys_are_caught():
    assert "github token" in find_secrets("ghp_" + "x" * 36)
    assert "private key" in find_secrets("-----BEGIN RSA PRIVATE KEY-----")


def test_the_stripe_keys_file_contents_are_caught_by_name():
    assert "stripe keys file" in find_secrets('{"secret_key": "sk_test_' + "c" * 24 + '"}')
```

`tests/test_cli.py`:

```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cli(*args, cwd=ROOT, env=None):
    return subprocess.run([sys.executable, "-m", "flowsync", *args], cwd=cwd,
                          capture_output=True, text=True, env=env)


def test_scan_exits_3_and_names_what_it_found(tmp_path):
    f = tmp_path / "page.md"
    f.write_text("key: sk_live_" + "a" * 24)
    r = cli("scan", "--file", str(f))
    assert r.returncode == 3
    assert json.loads(r.stdout)["clean"] is False


def test_scan_of_clean_text_exits_0(tmp_path):
    f = tmp_path / "page.md"
    f.write_text("The blocker asks apps to close before it ever forces them.")
    r = cli("scan", "--file", str(f))
    assert r.returncode == 0 and json.loads(r.stdout) == {"clean": True, "found": []}


# Review Focus 4
def test_a_git_failure_exits_2_with_nothing_on_stdout_and_a_log(tmp_path, monkeypatch):
    import os
    env = dict(os.environ, FLOWSYNC_REPO=str(tmp_path / "not-a-repo"),
               FLOWSYNC_HOME=str(tmp_path))
    r = cli("head", env=env)
    assert r.returncode == 2
    assert r.stdout == ""
    assert any((tmp_path / "logs").glob("*.log"))


def test_record_write_then_digest_done_persist_in_state(tmp_path):
    import os
    env = dict(os.environ, FLOWSYNC_HOME=str(tmp_path))
    assert cli("record-write", "--page", "p1", env=env).returncode == 0
    assert cli("digest-done", "--until", "2026-09-21", env=env).returncode == 0
    data = json.loads((tmp_path / "state.json").read_text())
    assert "p1" in data["last_writes"]
    assert data["digest_since"] == "2026-09-21"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_guard.py tests/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'flowsync.guard'`

- [ ] **Step 3: Implement**

`flowsync/guard.py`:

```python
"""Last check before any text goes to Notion. Nothing secret leaves the machine."""
import re

_PATTERNS = {
    "stripe secret key": r"\b[sr]k_(live|test)_[A-Za-z0-9]{16,}",
    "stripe webhook secret": r"\bwhsec_[A-Za-z0-9]{16,}",
    "github token": r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "stripe keys file": r'"(secret_key|publishable_key|webhook_secret)"\s*:',
    "aws key": r"\bAKIA[0-9A-Z]{16}\b",
}


def find_secrets(text: str) -> list[str]:
    return [name for name, pat in _PATTERNS.items() if re.search(pat, text or "")]
```

`flowsync/state.py`:

```python
"""state.json: the job's own write times, and where the last digest ended."""
import json
import os
from pathlib import Path


def load(path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"last_writes": {}, "digest_since": ""}
    data = json.loads(p.read_text(encoding="utf-8"))
    data.setdefault("last_writes", {})
    data.setdefault("digest_since", "")
    return data


def save(path, data: dict) -> None:
    p = Path(path)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def record_write(path, page_id: str, when_iso: str) -> None:
    data = load(path)
    data["last_writes"][page_id] = when_iso
    save(path, data)
```

`flowsync/cli.py`:

```python
"""python -m flowsync <command>. JSON on stdout; failures logged, never half-printed."""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flowsync import gitinfo, state
from flowsync.github import GhError, digest, idea_updates
from flowsync.guard import find_secrets
from flowsync.refresh import plan_refresh

HOME = Path(os.environ.get("FLOWSYNC_HOME", r"C:\Users\miles\flowshield-notion"))
REPO = os.environ.get("FLOWSYNC_REPO", r"C:\Users\miles\Projects\FlowShield")
STATE = HOME / "state.json"


def _log(message: str) -> None:
    logs = HOME / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    with open(logs / f"{stamp}.log", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run(argv) -> tuple[int, object]:
    ap = argparse.ArgumentParser(prog="flowsync")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("head")
    p = sub.add_parser("refresh-plan"); p.add_argument("--pages", required=True)
    p = sub.add_parser("digest"); p.add_argument("--since", default="")
    p = sub.add_parser("digest-done"); p.add_argument("--until", required=True)
    p = sub.add_parser("ideas"); p.add_argument("--ideas", required=True)
    p = sub.add_parser("scan"); p.add_argument("--file", required=True)
    p = sub.add_parser("record-write"); p.add_argument("--page", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "scan":
        found = find_secrets(Path(a.file).read_text(encoding="utf-8"))
        return (3 if found else 0), {"clean": not found, "found": found}
    if a.cmd == "record-write":
        state.record_write(STATE, a.page, _now())
        return 0, {"recorded": a.page}
    if a.cmd == "digest-done":
        date.fromisoformat(a.until)
        data = state.load(STATE); data["digest_since"] = a.until; state.save(STATE, data)
        return 0, {"digest_since": a.until}
    if a.cmd == "head":
        gitinfo.fetch(REPO)
        return 0, {"head": gitinfo.head_sha(REPO)}
    if a.cmd == "refresh-plan":
        gitinfo.fetch(REPO)
        pages = json.loads(Path(a.pages).read_text(encoding="utf-8"))
        head = gitinfo.head_sha(REPO)
        return 0, plan_refresh(REPO, head, pages, state.load(STATE)["last_writes"])
    if a.cmd == "digest":
        since = a.since or state.load(STATE)["digest_since"] or \
            (date.today() - timedelta(days=7)).isoformat()
        return 0, digest(since)
    if a.cmd == "ideas":
        return 0, idea_updates(json.loads(Path(a.ideas).read_text(encoding="utf-8")))
    return 1, {"error": "unknown command"}


def main(argv=None) -> int:
    try:
        code, payload = run(argv if argv is not None else sys.argv[1:])
    except (gitinfo.GitError, GhError) as e:
        _log(f"FAILED {' '.join(argv or sys.argv[1:])}: {e}")
        print(f"flowsync: {e}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2))
    return code
```

`flowsync/__main__.py`:

```python
import sys
from flowsync.cli import main

sys.exit(main())
```

- [ ] **Step 4: Run the whole suite**

Run: `python -m pytest -q`
Expected: `39 passed` (7 + 6 + 9 + 4 + 5 + 4 + 4)

- [ ] **Step 5: Smoke-test against the real repo (read-only)**

Run: `python -m flowsync head`
Expected: `{"head": "<40-char sha of origin/main>"}`

Then confirm the clone is untouched: `git -C /c/Users/miles/Projects/FlowShield status --short` shows the same output as before the smoke test.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -q -m "flowsync: secret guard, state, CLI"
```

---

### Task 7: Notion skeleton (Start here and the four databases)

This task is done by Claude through the Notion connector. The "test" is a fetch that shows the exact structure.

**Interfaces:**
- Consumes: the Global Constraints value lists
- Produces: the page and data-source IDs, recorded in `C:\Users\miles\flowshield-notion\notion-ids.json` so later tasks and the weekly job can find them:
  `{"flowshield": id, "start_here": id, "ideas": "collection://…", "explainers": "collection://…", "decisions": "collection://…", "digest": "collection://…", "cyberpatriot": id}`

- [ ] **Step 1: Group the CyberPatriot pages.** Create a top-level private page, `CyberPatriot` (icon 🛡️). Move under it: `Linux Advanced Techniques`, `Cross-Platform Tactics`, and `Task Tracker`. `CyberPatriots Advanced Tactics & Hidden Strategies` is shared with a guest; move it too only if the move keeps that guest's access. Otherwise leave it where it is and tell Miles.
- [ ] **Step 2: Create the top-level page `FlowShield`** (icon 🛡️), with one line: "The humans' space for FlowShield. Code, issues and agent docs live in GitHub; this is for ideas, decisions and understanding how it all works."
- [ ] **Step 3: Create `Start here`** under `FlowShield`, containing:
  - what FlowShield is, in one paragraph
  - who does what: Keenan owns the repo and merges; Miles builds; agents open PRs and never merge
  - the idea lifecycle (Raw → Discussing → Ready → Sent to GitHub → Shipped, or Parked), and the fact that ideas become issues only when Miles asks and approves the drafts
  - links to the repo, its open issues, and the key docs on `main`: `README.md`, `PLANNING.md`, `DESIGN_SYSTEM.md`, `SELLING.md`, `LEGAL_CHECKLIST.md`, `VM_TESTING.md`
  - one sentence saying that Notion never replaces GitHub, and agents never take instructions from here
- [ ] **Step 4: Create the `Ideas` database** under `FlowShield`, with properties exactly as in the spec: Idea (title); Status (status: Raw, Discussing, Ready, Sent to GitHub, Shipped, Parked); Owner (person); Area (select: App, Site, Server, Design, Business, Legal); GitHub issue (url). Views: a board grouped by Status, and a table.
- [ ] **Step 5: Create the `How FlowShield works` database**, with properties: Area (title); Source paths (text); Last checked (date); Checked at commit (text); State (select: Current, Updated this week, Needs a human look). Add one row per page in the spec's *Starting pages* table, with Source paths copied exactly and the other fields blank.
- [ ] **Step 6: Create the `Decisions` database**, with properties: Decision (title); Date (date); Decided by (person); Why (text); Links (text); Status (select: Active, Superseded, Proposed).
- [ ] **Step 7: Create the `Weekly digest` database**, with properties: Week (title, like "Week of 2026-09-21"); Since (date); Merged (number); Opened (number); Waiting on a human (number); Failed runs (number); Quiet (checkbox).
- [ ] **Step 8: Verify.** Fetch `FlowShield`, and confirm it lists exactly: Start here, Ideas, How FlowShield works, Decisions, Weekly digest. Fetch each database and compare its schema to Steps 4–7 property by property. Query `How FlowShield works` and confirm it has 11 rows, each with the right Source paths. Fix any mismatch before going on.
- [ ] **Step 9: Record the IDs** in `notion-ids.json`, then run `git add -A && git commit -q -m "Notion IDs"` in `flowshield-notion`.
- [ ] **Step 10: Hand over to Miles.** Ask him to share `FlowShield` with `mcmahonkeenan6@gmail.com` as a guest, at *Can edit*. Claude doesn't send the invite.

---

### Task 8: Seed the Decisions database

**Interfaces:**
- Consumes: `notion-ids.json` → `decisions`

- [ ] **Step 1: Look up the source of each decision** with `gh`. Use the PR or issue that holds it, and its date:
  - Inter as the one typeface: #149
  - Accent is structural, not scarce: #149
  - Site hero leads with the product; timeline below: #174 (reverses part of #139)
  - Blocked apps counted per app, not per process: #138 / #140
  - Captures re-recorded only when the product is near complete: #144
  - Site offline for the internal beta: #168
  - Agents never merge: `CLAUDE.md` "Who merges"
  Run `gh pr view <n> -R seventycookies6-design/flowshield --json title,mergedAt,url` (or `gh issue view`) for each, and use the real date and URL.
- [ ] **Step 2: Write each row.** Status Active; Why in one or two plain sentences taken from the PR or issue; Links = the URL. Leave Decided by blank unless the source names the person, since Notion person fields can only hold workspace users and guests.
- [ ] **Step 3: Scan before writing.** Put all seven Why texts in one temp file and run `python -m flowsync scan --file <tmp>`. It must exit 0.
- [ ] **Step 4: Verify.** Query `Decisions`: 7 rows, all Active, every Links value is a working GitHub URL.

---

### Task 9: First explainer pass, watched by Miles

**Files:**
- Create: `C:\Users\miles\flowshield-notion\prompts\explainer-style.md`

**Interfaces:**
- Consumes: `python -m flowsync head`, `refresh-plan`, `scan`, and `record-write` (Task 6); `notion-ids.json` → `explainers`
- Produces: 11 explainer pages, each with State Current, Last checked set, Checked at commit = the current `origin/main` SHA, and a `last_writes` entry in `state.json`

- [ ] **Step 1: Write `prompts/explainer-style.md`:**

```markdown
# How an explainer page is written

Two sections, in this order.

## The short version
- Plain language. No code, no file names, no jargon without a one-line meaning.
- Say what this part of FlowShield does for the customer, then how it does it
  in everyday terms, then what could go wrong and how it's handled.
- 150–300 words. Someone who has never programmed should follow it.

## Under the hood
- The files and classes involved, each with one line on its job.
- How this area connects to the others. Link the other explainer pages by name.
- The rules that must not break. Quote the rule and name where it's enforced
  (for example "never closes CriticalProcesses: AppBlockerService").
- A code excerpt only where it explains something prose can't: 15 lines at most,
  and never configuration values, keys, or anything from .stripe_keys.json.
- Links to the repo docs that cover it (on main), never copies of them.

## Footer
- "Last checked against the code: <date> at <short sha>".
- A "What changed" section, newest first, added on refreshes, each entry linking
  the PRs.
```

- [ ] **Step 2: Build the page list and get the plan.** Query `How FlowShield works` into `C:\Users\miles\flowshield-notion\tmp\pages.json` as `[{"page_id","area","source_paths","checked_at":"","last_edited":""}]`. Then run `python -m flowsync refresh-plan --pages tmp\pages.json`. Expected: every page reports `rewrite`, with reason `no valid checked-at commit`. Any `human-look` with missing paths means the spec's table is wrong for that page: fix the Source paths row, then re-run.
- [ ] **Step 3: For each page, one at a time, in the spec's table order:**
  1. read every file in its `changed_files` from `origin/main` (`git -C <clone> show origin/main:<path>`)
  2. write the page to `tmp/<area>.md` following `explainer-style.md`
  3. run `python -m flowsync scan --file tmp/<area>.md`, which must exit 0
  4. show Miles the page and spot-check it together: every class or file named exists, and every rule quoted is actually in the code
  5. write it to Notion; set Last checked = today, Checked at commit = the plan's `head`, and State = Current
  6. run `python -m flowsync record-write --page <page_id>`
- [ ] **Step 4: Cover the gaps.** List the files under `DesktopApp/`, `Server/`, `Website/`, `automation/`, and `tools/` on `origin/main` that no page's Source paths cover (use `flowsync.paths.page_changes` in a one-off Python call). Either add each file to the right page's Source paths, or list it under a "Not covered yet" heading on **The map**.
- [ ] **Step 5: Verify.** Re-run `refresh-plan` with Checked at commit filled in. Expected: every page reports `stamp`.

---

### Task 10: Idea to issue, on request

**Files:**
- Create: `C:\Users\miles\flowshield-notion\prompts\send-ready-ideas.md`

- [ ] **Step 1: Write `prompts/send-ready-ideas.md`:**

```markdown
# Send the ready ideas to GitHub

Run only when Miles asks in chat. Never on a schedule.

1. Read C:\Users\miles\flowshield-notion\notion-ids.json. Query the Ideas data
   source for Status = Ready.
2. None ready: say so and stop.
3. For each idea, draft a GitHub issue for seventycookies6-design/flowshield:
   - Title: the idea, as a short imperative or problem statement.
   - Body: "Why" (from the idea's notes), "What done looks like" (concrete,
     checkable), "Notes from the discussion", and a last line:
     "From the Ideas board in Notion (idea by <Owner>)." Don't paste the
     Notion URL; the repo is for agents, who don't read Notion.
   - Label: enhancement, bug, design, or documentation, whichever fits. Add
     owner-decision if the idea needs Keenan to decide something.
4. Save all drafts to tmp/drafts.md and run
   `python -m flowsync scan --file tmp/drafts.md`. It must exit 0.
5. SHOW MILES EVERY DRAFT and wait for an explicit yes. He may edit, drop, or
   approve each one separately. Create nothing without that yes.
6. For each approved draft: `gh issue create -R seventycookies6-design/flowshield
   --title ... --body-file ... --label ...`. Put the returned URL into the idea's
   GitHub issue field, set Status = Sent to GitHub, and run
   `python -m flowsync record-write --page <idea page id>`.
7. Report which ideas became which issues.
```

- [ ] **Step 2: Dry run with Miles.** Ask Miles for one real idea, or add one he dictates, to `Ideas` with Status Ready. Follow the prompt **through step 5 only**. Confirm the draft reads correctly, then stop without creating the issue unless Miles says to go ahead.
- [ ] **Step 3: Commit.** Run `git add -A && git commit -q -m "Prompts: explainer style, send ready ideas"` in `flowshield-notion`.

---

### Task 11: The weekly job

**Files:**
- Create: `C:\Users\miles\flowshield-notion\prompts\weekly-job.md`

**Interfaces:**
- Consumes: every `flowsync` command, `notion-ids.json`, and `explainer-style.md`

- [ ] **Step 1: Write `prompts/weekly-job.md`:**

```markdown
# FlowShield weekly Notion job (Mondays, 8 AM)

Keep the FlowShield space in Notion in step with GitHub. Work in
C:\Users\miles\flowshield-notion. Read notion-ids.json for every Notion ID.

HARD RULES
- Never write to GitHub. Never run gh commands that create, edit, comment on,
  label, close, or merge anything. flowsync only reads.
- Never delete anything in Notion.
- Every block of text goes through `python -m flowsync scan --file <tmp>` before
  it is written to Notion. A non-zero exit means: don't write it; report it.
- If any flowsync command exits 2, stop at once. Write nothing more to Notion.
  Send a push notification: "FlowShield Notion job failed: <stderr line>. See
  flowshield-notion\logs." Then end.

STEPS
1. Digest. Run `python -m flowsync digest`. Create a Weekly digest row: Week =
   "Week of <today>", Since = digest.since, the counts, Quiet = digest.quiet.
   The page body has sections Merged, Opened, Issues opened, Issues closed,
   Waiting on a human, and Failed runs, each item linked. A quiet week gets one
   line: "Nothing moved this week." Then run
   `python -m flowsync digest-done --until <today>`.
2. Explainers. Query How FlowShield works into tmp/pages.json as
   [{page_id, area, source_paths, checked_at, last_edited}]. Run
   `python -m flowsync refresh-plan --pages tmp/pages.json`. For each result:
   - First set every page whose State is "Updated this week" back to "Current".
   - stamp: set Last checked = today. Leave everything else alone.
   - rewrite: read the changed files from origin/main, rewrite the page per
     prompts/explainer-style.md, keep the existing What changed entries, and add
     a new dated entry linking the PRs. Set Last checked, Checked at commit =
     head, State = Updated this week.
   - human-look: don't touch the page body. Add a dated "Needs a look" note at
     the top with the reason, the changed files, and the PRs (or the missing
     paths). Set State = Needs a human look.
   After each write to a page, run `python -m flowsync record-write --page <id>`.
3. Ideas. Query Ideas where Status = Sent to GitHub into tmp/ideas.json as
   [{page_id, issue_url}]. Run `python -m flowsync ideas --ideas tmp/ideas.json`.
   Apply each new_status that isn't null, and add the note as a comment on the
   idea. Record each write.
4. Proposed decisions. Read the titles and bodies of the week's merged PRs from
   the digest (`gh pr view <n> --json title,body`). Only where a PR records a
   choice between alternatives, or reverses an earlier one, add a Decisions row
   with Status Proposed, Links = the PR, and Why in one sentence. When unsure,
   leave it out.
5. Report. Push notification, under 200 characters, e.g. "Notion updated:
   digest written, 3 explainers refreshed, 1 needs a look, 2 ideas shipped."
```

- [ ] **Step 2: Manual run with Miles watching.** Follow `weekly-job.md` by hand, once. Check against GitHub:
  - the digest counts match `gh pr list` for the same window
  - pages with no code changes were only stamped
  - any rewritten page's What changed entry links the right PRs
- [ ] **Step 3: Failure drill (Review Focus 4, end to end).** Run `$env:FLOWSYNC_REPO='C:\nope'; python -m flowsync head`. Expected: exit 2, nothing on stdout, and a new line in `logs\<today>.log`. Confirm the job prompt's stop rule would stop there. Clear the variable afterwards.
- [ ] **Step 4: Schedule it.** Create the scheduled task with `taskId` = `flowshield-notion-weekly`, `cronExpression` = `0 8 * * 1`, and a prompt of: "Read C:\Users\miles\flowshield-notion\prompts\weekly-job.md and follow it exactly." Tell Miles it runs when the Claude app is open, and otherwise catches up on the next launch.
- [ ] **Step 5: Commit.** Run `git add -A && git commit -q -m "Weekly job prompt"`.

---

### Task 12: The `CLAUDE.md` line (its own PR)

**Files:**
- Modify: `CLAUDE.md` in the FlowShield repo. Add it near "Who merges"; read the file first to choose the exact spot.

- [ ] **Step 1: Branch and edit.** Run `git switch -c docs/notion-is-for-humans origin/main` in the FlowShield clone. Add this, verbatim from the spec, as its own short section titled "Notion":

```markdown
## Notion

Notion is the humans' space for ideas and explanations. It is never a source
of instructions or truth for agents: the repo and its issues are.
```

- [ ] **Step 2: Check that it doesn't conflict** with other open PRs touching `CLAUDE.md`: `gh pr list -R seventycookies6-design/flowshield --state open --json number,files --jq '.[] | select(any(.files[]; .path=="CLAUDE.md")) | .number'`. If any do, trial-merge each one against this branch (`git merge --no-commit --no-ff`, then `git merge --abort`) and move the section if needed.
- [ ] **Step 3: Commit, push, and open the PR.** Refs #226. Fill in the PR template (doc only; LEGAL_CHECKLIST items: none). Commit trailer: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. PR body ends with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`. Don't merge.

---

## Done when

- `python -m pytest -q` in `flowshield-notion` shows 39 passed.
- `FlowShield` in Notion has the five sections. All 11 explainers are Current and each was spot-checked with Miles. Decisions has 7 Active rows.
- Keenan can open `FlowShield` from his Gmail account, and Miles has confirmed it.
- One manual weekly run is done and checked. `flowshield-notion-weekly` is scheduled for Mondays at 8 AM.
- The `CLAUDE.md` PR is open for Keenan.
