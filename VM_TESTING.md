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

## Gotchas the bench has already cost someone

- **The bridge serves one request at a time.** A long poll (waiting on a done
  flag inside the guest) holds the connection, and every other `lab.ps1` call
  during it fails with "lab bridge is down" — which is a lie. Check the bridge
  PID and `lab-bridge.log` before believing it; the process is usually alive and
  busy. Don't issue a second call while a wait is in flight.
- **`screenshot` used to photograph its own terminal.** Capture runs as an
  interactive scheduled task, which opens a console window and then captures
  the screen with that window on top of whatever mattered. Fixed in `lab.ps1`:
  the capture script minimises every terminal window and waits for the
  compositor before it shoots. Note that `GetConsoleWindow()` is *not* the
  window to minimise — with Windows Terminal as the default host it returns the
  hidden pseudo-console, and minimising that changes nothing on screen. Go for
  `WindowsTerminal.exe` and `conhost.exe` by process instead.
- **Give every wait a deadline.** A `while (-not (Test-Path $flag))` loop with
  no timeout, run through `guest`, holds the bridge's single connection until
  the flag appears — which, if the thing that writes it has already failed,
  is never. That cost a whole night of a blocked bench once. Write the done
  flag in a `finally`, and bound the wait on the host side too.
- **Write the runner from a host file.** `lab.ps1 stage -Path <host file> -As
  run-f15-ui.ps1` then copy it into place inside the guest. Building the runner
  with a nested here-string through `guest -Script` fails silently and the
  *previous* runner runs instead, which looks like a test that ignored your
  change.
- **The `F15UI` task has an interactive principal and no stored password.**
  `schtasks /IT` plus `/RP` registers but then fails to start with "Element not
  found". PS Direct has no desktop, so anything that draws or captures the
  screen has to go through that task.
- **A bare `StackPanel` is not surfaced to UI Automation.** `exists()` on one
  passes whether its content is there or not. Assert on a real control — a
  `ProgressBar`, a `Button`, a `TextBlock` with an AutomationId.
