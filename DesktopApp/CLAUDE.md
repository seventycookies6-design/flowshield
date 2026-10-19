# Desktop app — rules for WPF and the blocker

Read [the root CLAUDE.md](../CLAUDE.md) in full first; its repo-wide rules and
commands still apply. Paths and commands below are relative to the repo root.

## Safety and automation

- **The blocker stays deliberately timid:** never close anything on
  `AppBlockerService.CriticalProcesses`, no admin rights, drivers, services or
  hosts-file edits.

Keep existing `AutomationId`s.

## Testing gotchas

Each of these cost real time once. Don't rediscover them.

- **Covered controls:** UI Automation still lists buttons underneath an
  overlay, and can invoke them. Prove that a panel blocks something by what
  happens (no sprint starts, nothing saved), not by whether a control exists.
  The same goes for the app itself: a gate must refuse in the view model, not
  only by covering the screen.

- **Clipped controls:** WPF reports a control's *layout* rectangle even when a
  `ScrollViewer` has clipped it away, so "inside the window" does not mean
  clickable. Hit-test the centre point before synthesising a click (#125).

- **An `AutomationId` on a layout panel is never surfaced**, so a test asking
  for it passes whether the thing is drawn or not. Put ids on the controls
  themselves (#134).

See [automation/CLAUDE.md](../automation/CLAUDE.md) for the rules for scripts
and tests that launch the app, including `preserve_user_settings()`.
