# VM test runs

Results from the disposable Hyper-V VM. See [VM_TESTING.md](../../VM_TESTING.md)
for what the bench is for, how to request a run, and what it cannot tell you.

Newest first. One file per run, named `YYYY-MM-DD-<build>-<subject>.md`.

| Date | Build | Subject | Outcome |
| --- | --- | --- | --- |
| 2026-10-22 | #372 (`8acd78a`), supplied local 1.0.90 → 1.0.91 | [Automatic updates, round 4](2026-10-22-372-auto-updates-r4.md) | **Partial**: updates-off fresh install passes (62-minute app log, no checks or downloads). Firm-sprint deferral and apply-on-Quit NOT TESTED: the guest was starved by host Disk 1 contention (0.3–1.6 s latency, single-digit IOPS) and the UI runner timed out. No `disk` 153/7 or `Ntfs` 50/55 event. VM left Off at the required checkpoint |
| 2026-10-20 | #372 (`8acd78a`), local 1.0.90 → 1.0.91 | [Automatic updates, round 3](2026-10-20-372-auto-updates-r3.md) | **Partial**: automatic staging with one notification, and What's new with lasting dismissal, pass. Sprint deferral, apply-on-Quit and updates-off not tested: the VM's USB drive failed mid-run. Those three must pass before the release that ships #372 |
| 2026-10-19 | #372 (`8acd78a`), local 1.0.90 → 1.0.91 | [Automatic updates](2026-10-19-372-auto-updates.md) | **Blocked, nothing tested**: guest automation and PS Direct failed after a bench repair; no product result. Superseded by round 3 |
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
