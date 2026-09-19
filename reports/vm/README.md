# VM test runs

Results from the disposable Hyper-V VM. See [VM_TESTING.md](../../VM_TESTING.md)
for what the bench is for, how to request a run, and what it cannot tell you.

Newest first. One file per run, named `YYYY-MM-DD-<build>-<subject>.md`.

| Date | Build | Subject | Outcome |
| --- | --- | --- | --- |
| 2026-09-18 | main + 5 branches | [Overnight tier 3 sweep](2026-09-18-overnight-tier3.md) | Cascade fixed; two real bugs found |
| 2026-09-18 | 1.0.7 → 1.0.8 (local) | Fresh install; update path blocked | Partial — see below |
| 2026-09-15 | 1.0.7 | Fresh install, activation, uninstall (original #53 pass) | Steps 1–6, 8 pass; step 7 not runnable |

## Standing gap

**Step 7, the in-app update**, has never been run. `UpdateService` reads its
feed from the public GitHub repo, so updating *from* 1.0.7 requires a real
published release to update *to*. It stays open until the next release is cut
for its own reasons — cutting one purely to unblock this test spends a public
unsigned release on a test.
