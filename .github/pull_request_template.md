## What and why

<!-- One or two sentences. -->

Closes #

## Checks

- [ ] Rebased on the latest `main`
- [ ] `dotnet build -c Release` — 0 warnings
- [ ] Fast tests: `python -m pytest automation/tests -m "not ui and not stripe" -q` — passed / skipped / failed:
- [ ] UI tests run locally, if the app's behaviour or screens changed — result:
- [ ] New or changed behaviour has a test (regressions in tier 5, failing without the fix)

## Heads-up for the other person

- [ ] Changes `Server/` — needs *Manual Deploy* on Render after merge
- [ ] Changes customer-facing wording (site, app, emails) — new wording is true of the shipped build
- [ ] Needs a site publish or a release after merge
- [ ] Touches shared settings, ports, or test infrastructure

## Merging

Don't merge this yourself. The repo owner's Claude Code session reviews and merges it (see "Who merges" in `CLAUDE.md` / `AGENTS.md`). Agents merge only when a human directly asks them to in their own conversation.

## Screenshots

<!-- For anything visible. Never a Blocked Apps capture from a real machine — it lists running processes. -->
