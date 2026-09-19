# 2026-09-18 — overnight tier 3 sweep

Build: `origin/main` at 8ac2084, then five branches off it. Every run below
happened in the Hyper-V lab, reverted to `clean-baseline` beforehand where a
clean install mattered.

## Why this run happened

#114 said the tier 3 suite could not be trusted end to end: `TestFirstRun` left
the app on the welcome screen and ten later tests failed with
`could not navigate to 'Settings'`, only one of which had a problem of its own.
A suite in that state hides real regressions, so the first job was to make it
readable again and then find out what had been hiding in it.

## Results

| Branch | Scope | Outcome |
| --- | --- | --- |
| `origin/main` (8ac2084) | full tier 3 | `TestFirstRun` reproduced; `SummaryStreakText` failed |
| `fix/114-tier3-firstrun-cascade` | full tier 3 | **69 passed, 2 failed, 2 skipped** — first run green, no cascade |
| `fix/126-summary-streak-day-one` | `TestSprints` | **7 passed** (1 failed on `main`) |
| `chore/design-system-drop-legacy-aliases` | Today, Blocked Apps, Sleep Blocking, Settings | **12 passed, 1 failed** (the failure is #126, not in that branch) |
| `fix/117-save-as-dialog` | `TestJournalExport` | **5 passed**, including the four restored from #116 |

## What it found

Two real bugs, both of which the cascade had been hiding:

- **#126** — `UpdateSummaryCard` ran before `RefreshStats`, and since F15 only
  `DailyGoal.Settle` advances `CurrentStreak`. So the card was built while the
  streak was still zero and the line collapsed out of the tree: **the first
  sprint of a streak never showed "Day 1"**. Reproduced on plain `main`.
- **#127** — tier 3 read `settings.json` during the app's `File.Replace`, which
  Windows reports to a reader as a sharing violation. Intermittent: failed once,
  passed on the next run.

The cause of #114 itself was in the harness, not the first-run code:
`_is_on_screen` proved a control's rectangle sat inside the window, but WPF
reports a *layout* rectangle whether or not a `ScrollViewer` has clipped the
control away. A click on a clipped button landed on the window instead.

#117's cause was `set_edit_text`, which puts text in the Save dialog's file-name
box — reading it back returns the path — without sending the input notifications
the shell dialog updates its own state from. Real keystrokes work.

## What the bench cannot say about this run

- Only one Windows 11 VM, so a pass means "works on a clean Windows 11".
- **Step 7, the in-app update, still has not run** — see the standing gap in the
  README. Nothing here changes that.
- #127's fix cannot be proved by a green run, because the failure is
  intermittent and the run before the fix was green too.
