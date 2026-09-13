"""
FlowShield doc steward — keeps the repo's documentation consistent with the code
and with itself.

It never changes code. A model proposes edits; this script only applies an edit
when every check passes:

  * the target file is on the `editable` allowlist in config.json (Markdown docs);
  * the text to replace occurs exactly once in that file;
  * the edit cites evidence — verbatim quotes — and each quote really exists in
    the cited tracked file, with at least one from a *different* file.

Anything else the model notices (in code, the site, the legal page or a
generated report) is carried as a report for a human, never edited.

    python tools/doc_steward/steward.py --since HEAD~1          # check a change
    python tools/doc_steward/steward.py --full                  # sweep everything
    python tools/doc_steward/steward.py --full --dry-run        # propose only
    python tools/doc_steward/steward.py --guard origin/main     # allowlist check

Needs OPENROUTER_API_KEY and/or NVIDIA_API_KEY (tried in config order, each
provider's models in order, falling back on errors and rate limits). Standard
library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CONFIG_PATH = HERE / "config.json"

EXIT_OK = 0          # ran; nothing applied
EXIT_CHANGED = 10    # ran; edits applied to the working tree
EXIT_ERROR = 2       # could not complete (no provider answered, bad config, ...)
EXIT_GUARD = 3       # --guard found a non-allowlisted change


# ------------------------------------------------------------------ helpers

def load_config(path: Path = CONFIG_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def git(*args: str, root: Path = ROOT) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def tracked_files(root: Path = ROOT) -> list[str]:
    return [p for p in git("ls-files", root=root).splitlines() if p]


def normalize(text: str) -> str:
    """Collapse all whitespace, so quotes survive re-wrapping and CRLF."""
    return " ".join(text.split())


def safe_relpath(path: str) -> str | None:
    """Repo-relative forward-slash path, or None if it tries to escape."""
    p = (path or "").replace("\\", "/").strip()
    if not p or p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        return None
    if any(part == ".." for part in p.split("/")):
        return None
    return p


def matches_any(path: str, patterns: list[str]) -> bool:
    """Glob match where `**/` may also match zero directories."""
    return any(fnmatch.fnmatchcase(path, variant)
               for pat in patterns
               for variant in {pat, pat.replace("**/", "")})


# --------------------------------------------------------------- validation

@dataclass
class Verdict:
    ok: bool
    reason: str = ""


def check_evidence(evidence, edited_file: str | None, tracked: set[str],
                   read, min_chars: int) -> Verdict:
    """Every quote must exist verbatim (whitespace-insensitive) in its file."""
    if not isinstance(evidence, list) or not evidence:
        return Verdict(False, "no evidence cited")
    other_file = False
    for item in evidence:
        if not isinstance(item, dict):
            return Verdict(False, "malformed evidence entry")
        path = safe_relpath(item.get("file", ""))
        quote = normalize(str(item.get("quote", "")))
        if path is None or path not in tracked:
            return Verdict(False, f"evidence file is not a tracked file: {item.get('file')!r}")
        if len(quote) < min_chars:
            return Verdict(False, f"evidence quote from {path} is too short to verify")
        if quote not in normalize(read(path)):
            return Verdict(False, f"evidence quote not found in {path}: {quote[:80]!r}")
        if path != edited_file:
            other_file = True
    if edited_file is not None and not other_file:
        return Verdict(False, "evidence must include at least one other file")
    return Verdict(True)


def validate_edit(edit, config: dict, tracked: set[str], read) -> Verdict:
    limits = config["limits"]
    if not isinstance(edit, dict):
        return Verdict(False, "malformed edit")
    path = safe_relpath(edit.get("file", ""))
    if path is None:
        return Verdict(False, f"unsafe path: {edit.get('file')!r}")
    if path not in config["editable"]:
        return Verdict(False, f"{path} is not an editable doc")
    if path not in tracked:
        return Verdict(False, f"{path} is not tracked")
    find, replace = edit.get("find"), edit.get("replace")
    if not isinstance(find, str) or not isinstance(replace, str) or not find.strip():
        return Verdict(False, "find/replace must be non-empty strings")
    if find == replace:
        return Verdict(False, "replacement is identical")
    if len(replace) > limits["max_replace_chars"]:
        return Verdict(False, "replacement is too long")
    count = read(path).count(find)
    if count != 1:
        return Verdict(False, f"text to replace occurs {count} times in {path} (must be exactly once)")
    return check_evidence(edit.get("evidence"), path, tracked, read,
                          limits["min_evidence_chars"])


def validate_report(report, tracked: set[str], read, config: dict) -> Verdict:
    if not isinstance(report, dict) or not str(report.get("problem", "")).strip():
        return Verdict(False, "malformed report")
    return check_evidence(report.get("evidence"), None, tracked, read,
                          config["limits"]["min_evidence_chars"])


def guard(base: str, config: dict, root: Path = ROOT, include_untracked: bool = True) -> list[str]:
    """Paths changed since `base` (committed or not) that aren't editable docs."""
    changed = set(git("diff", "--name-only", f"{base}...HEAD", root=root).split())
    changed |= set(git("diff", "--name-only", "HEAD", root=root).split())
    if include_untracked:
        changed |= set(git("ls-files", "--others", "--exclude-standard", root=root).split())
    return sorted(p for p in changed if p not in config["editable"])


# ------------------------------------------------------------------ context

def build_context(config: dict, tracked: list[str], read, since: str | None) -> tuple[str, list[str]]:
    limits = config["limits"]
    docs = [p for p in config["editable"] + config["report_only"] if p in tracked]
    code = [p for p in tracked if matches_any(p, config["code"]) and p not in docs]

    sections: list[str] = []
    changed: list[str] = []
    if since:
        changed = [p for p in git("diff", "--name-only", f"{since}..HEAD").split() if p]
        diff = git("diff", f"{since}..HEAD")
        if len(diff) > limits["max_diff_chars"]:
            diff = diff[: limits["max_diff_chars"]] + "\n[diff truncated]\n"
        sections.append(f"## Recent change ({since}..HEAD)\n\nChanged files: {', '.join(changed) or 'none'}\n\n```diff\n{diff}\n```")

    for p in docs:
        sections.append(f"## FILE: {p}\n\n{read(p)}")

    # Code the docs mention, and code that just changed, goes first.
    doc_text = "\n".join(read(p) for p in docs)
    def priority(p: str) -> int:
        if p in changed:
            return 0
        if p in doc_text or Path(p).name in doc_text:
            return 1
        return 2
    # A per-change check stays small so free-tier quotas last: docs, the change,
    # and only the code the docs mention. The weekly sweep reads everything.
    total = limits["max_prompt_chars_since"] if since else limits["max_prompt_chars"]
    if since:
        code = [p for p in code if priority(p) < 2]
    budget = total - sum(len(s) for s in sections)
    omitted = []
    for p in sorted(code, key=priority):
        block = f"## FILE: {p}\n\n{read(p)}"
        if len(block) <= budget:
            sections.append(block)
            budget -= len(block)
        else:
            omitted.append(p)
    if omitted:
        sections.append("## Not included (over budget)\n\n" + "\n".join(omitted))
    return "\n\n".join(sections), changed


SYSTEM_PROMPT = """You are the FlowShield doc steward. Your only job is to keep the repository's documentation consistent with the code and with the other documents.

Rules:
- You may propose edits ONLY to these files: {editable}.
- These files are read-only for you; if something in them is wrong, add a report instead: {report_only}. Code files are also read-only; if code and docs disagree and the code looks wrong, report it — never "fix" docs to match a likely bug without saying so.
- Fix factual inconsistencies only: wrong commands, paths, names, numbers, versions, behaviour, statuses, or docs that contradict each other or the code. Do not restyle, reword for taste, reformat, or add new sections.
- Keep each edit minimal and in the document's existing voice. Never invent facts; if unsure, report instead of editing.
- Every edit and report must cite evidence: exact verbatim quotes (at least 12 characters, copied character for character) from the files that prove it. An edit must cite at least one file other than the one it edits.
- "find" must be copied exactly from the target file and occur exactly once in it.
- If everything is consistent, return empty lists.

Respond with a single JSON object and nothing else:
{{"edits": [{{"file": "...", "find": "...", "replace": "...", "reason": "...", "evidence": [{{"file": "...", "quote": "..."}}]}}],
  "reports": [{{"file": "...", "problem": "...", "evidence": [{{"file": "...", "quote": "..."}}]}}]}}"""


# ---------------------------------------------------------------- providers

def extract_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in response")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("response is not a JSON object")
    data.setdefault("edits", [])
    data.setdefault("reports", [])
    return data


def ask_model(config: dict, system: str, user: str, log=print) -> tuple[dict, str]:
    """Try each configured provider and model in order. Returns (data, 'provider/model')."""
    limits = config["limits"]
    attempts = []
    for provider in config["providers"]:
        key = os.environ.get(provider["key_env"], "").strip()
        if not key:
            attempts.append(f"{provider['name']}: {provider['key_env']} not set")
            continue
        for model in provider["models"]:
            body = json.dumps({
                "model": model,
                "temperature": 0.1,
                "max_tokens": limits["max_output_tokens"],
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
            }).encode("utf-8")
            request = urllib.request.Request(
                provider["base_url"].rstrip("/") + "/chat/completions", data=body,
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {key}", **provider.get("headers", {})})
            label = f"{provider['name']}/{model}"
            try:
                with urllib.request.urlopen(request, timeout=limits["request_timeout_seconds"]) as res:
                    payload = json.loads(res.read().decode("utf-8"))
                content = payload["choices"][0]["message"]["content"] or ""
                data = extract_json(content)
                log(f"answered by {label}")
                return data, label
            except urllib.error.HTTPError as exc:
                # Never echo the response body: some providers reflect headers.
                attempts.append(f"{label}: HTTP {exc.code}")
            except Exception as exc:                        # noqa: BLE001
                attempts.append(f"{label}: {type(exc).__name__}: {str(exc)[:120]}")
            log(f"falling back after {attempts[-1]}")
    raise RuntimeError("no provider produced a usable answer:\n  " + "\n  ".join(attempts))


# ---------------------------------------------------------------------- run

@dataclass
class Result:
    model: str = ""
    applied: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    reports: list = field(default_factory=list)


def apply(data: dict, config: dict, tracked: set[str], root: Path, dry_run: bool) -> Result:
    cache: dict[str, str] = {}

    def read(path: str) -> str:
        if path not in cache:
            cache[path] = (root / path).read_text(encoding="utf-8", errors="replace")
        return cache[path]

    result = Result()
    for edit in (data.get("edits") or [])[: config["limits"]["max_edits"]]:
        verdict = validate_edit(edit, config, tracked, read)
        if not verdict.ok:
            result.rejected.append({"edit": edit, "reason": verdict.reason})
            continue
        path = safe_relpath(edit["file"])
        before = read(path)
        cache[path] = before.replace(edit["find"], edit["replace"], 1)
        if not dry_run:
            # Preserve the file's existing newline style.
            with open(root / path, "w", encoding="utf-8", newline="") as fh:
                fh.write(cache[path])
        result.applied.append(edit)

    for report in data.get("reports") or []:
        verdict = validate_report(report, tracked, read, config)
        (result.reports if verdict.ok else result.rejected).append(
            report if verdict.ok else {"report": report, "reason": verdict.reason})
    return result


def summary_markdown(result: Result, since: str | None, dry_run: bool) -> str:
    scope = f"changes in `{since}..HEAD`" if since else "a full sweep"
    lines = [f"Doc steward run over {scope}, answered by `{result.model}`."
             + (" **Dry run — nothing was written.**" if dry_run else ""), ""]
    lines.append(f"## Edits applied ({len(result.applied)})")
    if not result.applied:
        lines.append("None.")
    for e in result.applied:
        lines += ["", f"### `{e['file']}`", "", e.get("reason", "").strip(), "",
                  "Before:", "```", e["find"], "```", "After:", "```", e["replace"], "```",
                  "Evidence:"]
        lines += [f"- `{ev['file']}`: “{normalize(ev['quote'])[:200]}”" for ev in e["evidence"]]
    lines += ["", f"## Reports for a human ({len(result.reports)})"]
    if not result.reports:
        lines.append("None.")
    for r in result.reports:
        lines += ["", f"- **{r.get('file', '(general)')}**: {r['problem'].strip()}"]
        lines += [f"  - `{ev['file']}`: “{normalize(ev['quote'])[:200]}”" for ev in r["evidence"]]
    lines += ["", f"## Discarded by the steward's checks ({len(result.rejected)})"]
    lines += [f"- {r['reason']}" for r in result.rejected] or ["None."]
    lines += ["", "Originals: every change above is in git history; revert this PR to restore them."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--since", metavar="REF", help="check docs against changes since REF")
    mode.add_argument("--full", action="store_true", help="sweep all docs against the code")
    mode.add_argument("--guard", metavar="BASE", help="fail if anything but editable docs changed since BASE")
    parser.add_argument("--dry-run", action="store_true", help="propose edits without writing them")
    parser.add_argument("--out-dir", default=str(ROOT / "logs" / "doc-steward"))
    args = parser.parse_args(argv)

    config = load_config()

    if args.guard:
        offending = guard(args.guard, config)
        if offending:
            print("doc steward guard: changes outside the editable docs:\n  " + "\n  ".join(offending))
            return EXIT_GUARD
        print("doc steward guard: only editable docs changed")
        return EXIT_OK

    if not args.dry_run and git("diff", "--name-only", "HEAD").strip():
        print("refusing: tracked files have uncommitted changes; commit or stash them "
              "first so the steward's own edits can be told apart")
        return EXIT_ERROR

    tracked_list = tracked_files()
    tracked = set(tracked_list)

    def read(path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8", errors="replace")

    context, _ = build_context(config, tracked_list, read, args.since)
    system = SYSTEM_PROMPT.format(editable=", ".join(config["editable"]),
                                  report_only=", ".join(config["report_only"]))
    try:
        data, model = ask_model(config, system, context)
    except RuntimeError as exc:
        print(str(exc))
        return EXIT_ERROR

    result = apply(data, config, tracked, ROOT, args.dry_run)
    result.model = model

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text(summary_markdown(result, args.since, args.dry_run), encoding="utf-8")
    (out / "result.json").write_text(json.dumps({
        "model": model, "applied": result.applied, "reports": result.reports,
        "rejected": result.rejected}, indent=2), encoding="utf-8")
    print(f"applied {len(result.applied)}, reports {len(result.reports)}, "
          f"discarded {len(result.rejected)} — see {out / 'summary.md'}")

    if args.dry_run:
        return EXIT_OK
    # Belt and braces: the allowlist check above should make this impossible.
    # Untracked files are the machine's own business, not something this run wrote.
    offending = guard("HEAD", config, include_untracked=False)
    if offending:
        print("refusing: non-doc files changed:\n  " + "\n  ".join(offending))
        return EXIT_GUARD
    return EXIT_CHANGED if result.applied else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
