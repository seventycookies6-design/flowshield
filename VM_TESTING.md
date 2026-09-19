# VM testing

Some things can only be judged on a machine that has never seen FlowShield: a
first install, the `flowshield://` handler, Start with Windows, an in-app
update, and what uninstall leaves behind. On a live machine those are either
destructive, unrepeatable, or both — you get one clean install per person, and
after that every run is polluted by the last one.

Miles runs a disposable Hyper-V VM for exactly this. It reverts to a clean
Windows with no FlowShield in under a minute, so the same test can be run over
and over, and a run that goes badly costs nothing.

**Miles is the only person with the VM.** Keenan's agent tests on a live
machine, which is fine for most work and wrong for anything in the table below.

## What belongs on the VM

| Test | Why not a live machine |
| --- | --- |
| Fresh install from `FlowShield-win-Setup.exe` | You only get one first install, and it changes the machine |
| First-run experience end to end | Once first run is done, it's done |
| `flowshield://` protocol registration and activation | Writing and removing `HKCU\Software\Classes\flowshield` on a machine you use |
| In-app update between two releases | Needs a real older install to update *from* |
| Start with Windows | Requires real logon and reboot cycles |
| Uninstall cleanup | Destructive, and only honest once per install |
| Trial expiry and the lock screen | Needs clock or state manipulation you don't want on a real machine |
| Anything that closes other programs for real | Self-explanatory |

Ordinary unit, integration and UI tests do **not** need the VM. Run them where
you are.

## Requesting a VM run

Open a comment on the standing **VM test bench** issue saying what you want
verified and against which build. A request is actionable when it names:

1. **The build** — a version tag, a branch, or a PR number.
2. **What to check** — the specific behavior, not "test the app".
3. **What a pass looks like** — the registry value, the log line, the visible
   state. If you can't say what a pass looks like, the result won't mean much.

Anyone can ask, including Keenan's agent. Miles runs it when he gets to it; the
bench is not a synchronous service.

## How results come back

Every run is written to `reports/vm/` as a dated file and linked from
`reports/vm/README.md`, so results are readable from any checkout without
calling the GitHub API. The same summary is posted as a comment on the standing
issue for people watching there.

Results record what was observed, including failures and anything that could not
be tested. A run that proves something is broken is worth as much as one that
proves it works — more, usually.

## What the bench cannot tell you

- **Code signing.** The VM sees the same unsigned build and the same SmartScreen
  warning as a customer, but clicking through it there says nothing about
  whether a real customer would.
- **Real payments.** Stripe stays in test mode, so activation is exercised with
  test cards only.
- **Other people's hardware.** One Windows 11 VM is not a compatibility matrix.
  A pass here means "works on a clean Windows 11", not "works everywhere".
- **Timing under real load.** The VM shares a host; don't read performance
  numbers from it.
