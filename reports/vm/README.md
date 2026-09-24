# VM test runs

Results from the disposable Hyper-V VM. See [VM_TESTING.md](../../VM_TESTING.md)
for what the bench is for, how to request a run, and what it cannot tell you.

Newest first. One file per run, named `YYYY-MM-DD-<build>-<subject>.md`.

| Date | Build | Subject | Outcome |
| --- | --- | --- | --- |
| 2026-09-23 | 1.0.10 RC (`9d1cc76`) | [Terms 1.1, Jump List, schedules, uninstall](2026-09-23-1.0.10-rc.md) | Pass for everything drivable; pinned-taskbar right-click not driven |
| 2026-09-22/23 | 1.0.9 RC (`3bccbca`, `2899835`), then published 1.0.9 (`07298ba`) | [Full suite, fresh install, uninstall](2026-09-22-1.0.9-rc-suite-and-fresh-install.md) | Pass; `flowshield://` bug found and fixed (#294), window overflow filed (#296); **in-app update 1.0.8 → 1.0.9 passes** |
| 2026-09-18 | main + 5 branches | [Overnight tier 3 sweep](2026-09-18-overnight-tier3.md) | Cascade fixed; two real bugs found |
| 2026-09-18 | 1.0.7 → 1.0.8 (local) | Fresh install; update path blocked | Partial — see below |
| 2026-09-15 | 1.0.7 | Fresh install, activation, uninstall (original #53 pass) | Steps 1–6, 8 pass; step 7 not runnable |

## Standing gap (closed)

**Step 7, the in-app update**, ran for the first time on 2026-09-23: a clean
1.0.8 updated itself to the published 1.0.9 through *Check for updates* and
*Restart to update*. See the 2026-09-22/23 report. Each release from now on
can be checked the same way, from the previous published version.
