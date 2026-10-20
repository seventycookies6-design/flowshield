# Automation — rules for tests and scripts

Read [the root CLAUDE.md](../CLAUDE.md) in full first; its repo-wide rules and
commands still apply. Paths and commands below are relative to the repo root.

Ports, the settings guard and which runs may share a machine are in the
root's **One test run per machine** section.

For UI automation, also read [DesktopApp/CLAUDE.md](../DesktopApp/CLAUDE.md)
for covered and clipped controls and AutomationIds on layout panels.

## Testing gotchas

Each of these cost real time once. Don't rediscover them.

- **Any script that launches the app** wraps its entry point in
  `preserve_user_settings()` — capture and one-off scripts included. The rule's
  test finds them by parsing for `launch_app`, so a new one cannot slip past a
  hand-written list (#141).

- **Wait for what happens, not for a duration.** A fixed sleep or probe
  timeout in the driver has twice caused failures that looked like product
  bugs: the terms-gate helper, and `start_sprint` probing for F7's open-apps
  question for a flat two seconds — which spends the whole three-second
  `--short-timers` cancel grace before a test can act (#146). Race the
  outcomes and return on the first one seen.

## Tiers and markers

The tier table in [README.md](../README.md#testing) describes the matching tier:
unit and model rules in tier 1, server integration in tier 2, UI in tier 3,
adversarial cases in tier 4, regressions in tier 5, email in tier 6, and device
limits in tier 7. Every behaviour change gets a test in the matching tier;
regressions go in tier 5 and must fail without the fix.

Markers describe what a test needs, independently of its tier. `ui` drives the
desktop app, `stripe` needs Stripe test credentials, and `e2e` marks a full
end-to-end path. `touches_user_state` identifies tests that read or change real
FlowShield user state. See `automation/pytest.ini` and
`automation/tests/conftest.py` for the marker definitions and settings guard.
The fast command in the root excludes both `ui` and `stripe`; it still queues
when a collected test can touch real state.
