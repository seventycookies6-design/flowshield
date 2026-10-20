# FlowShield — build & test report

_Generated 2026-09-22 06:22_

---

## 1. What this is

**FlowShield** is a Windows focus-timer and app blocker. Distractions go behind a
shield whose strength you choose per sprint, and finished sprints compound into a
momentum score.

The twist is **escalating shield levels** plus **momentum instead of streaks**:

| Level | Name | Behaviour |
| --- | --- | --- |
| Shield I | Soft | A full-screen notice on its own screen; the blocked app keeps running. |
| Shield II | Firm | Blocked apps are warned, then closed; the blocklist stays editable. |
| Shield III | Sealed | Warned, then closed, **and** the blocklist locks for the rest of the sprint. |

Momentum compounds on completed sprints and *decays* (×0.85 − 2, floored at zero)
on abandoned ones rather than resetting — one bad afternoon should not erase a
month. Every sprint ends with a one-line "what moved?" journal entry.

### Components

| Part | Stack | Location |
| --- | --- | --- |
| Desktop app | .NET 8 WPF, MVVM, DPAPI-encrypted settings | `DesktopApp/` |
| License server | Node.js + Express + SQLite + Stripe | `Server/` |
| Marketing site | Static HTML/CSS/JS, dark glassmorphism | `Website/` |
| Automation suite | Python, pywinauto + Playwright + pytest | `automation/` |

### Trial and purchase

| | 7-day free trial | Bought — $4.99 once |
| --- | --- | --- |
| Blocked apps | Unlimited | Unlimited |
| Shield levels | I, II, III | I, II, III |
| Sprint length | 15, 25, 45, 60 or 90 min | 15, 25, 45, 60 or 90 min |
| Sleep blocking | ✅ | ✅ |
| Hard kill mode | ✅ | ✅ |
| After day 7 | Locked until bought | Keeps working |

---

## 2. Stripe configuration

**Status: configured (TEST mode).**

| Credential | Value |
| --- | --- |
| Publishable key | `pk_test_51U8••••••••••••••••••` _(redacted)_ |
| Secret key | `sk_test_51••••••••••••••••••` _(redacted)_ |
| Price ID | `price_1UFQmZCcqk10eo83f6jDDOzp` |
| Webhook secret | `whsec_7u••••••••••••••••••` _(redacted)_ |

Secret values are redacted here by design — this file is meant to be shareable.
The real values live only in `.stripe_keys.json`, which is git-ignored.


---

## 3. End-to-end run

_No E2E report found. Run `python automation/e2e_runner.py` first._


---

## 4. Test suite

| Tier | Passed | Failed | Skipped |
| --- | --: | --: | --: |
| Tier 1 — unit | 476 | 0 | 0 |
| Tier 2 — server integration | 36 | 0 | 2 |
| Tier 3 — end-to-end UI | 106 | 9 | 1 |
| Tier 4 — adversarial | 42 | 0 | 0 |
| Tier 5 — regressions | 507 | 2 | 0 |
| Tier 6 — email delivery | 11 | 2 | 0 |
| Tier 7 — device limit | 24 | 0 | 0 |
| **Total** | **1202** | **13** | **3** |

Duration: 8514.0s · 1218 tests collected

**Failing tests**

- `tests/test_tier3_e2e.py::TestBlockedApps::test_there_is_no_blocked_app_limit`
- `tests/test_tier3_e2e.py::TestBlocklistProfiles::test_the_last_profile_cannot_be_deleted`
- `tests/test_tier3_e2e.py::TestBlocklistProfiles::test_sealed_locks_the_profile_switcher`
- `tests/test_tier3_e2e.py::TestSoftShowsTheNotice::test_a_blocked_app_in_front_gets_a_notice_that_closes_nothing`
- `tests/test_tier3_e2e.py::TestSoftShowsTheNotice::test_allow_five_minutes_keeps_it_quiet`
- `tests/test_tier3_e2e.py::TestPurchaseToActivation::test_full_flow`
- `tests/test_tier3_e2e.py::TestBreaksAndCycles::test_nothing_is_blocked_during_the_break`
- `tests/test_tier3_e2e.py::TestBreaksAndCycles::test_a_two_sprint_cycle_runs_itself`
- `tests/test_tier3_e2e.py::TestBreaksAndCycles::test_a_break_never_moves_momentum_or_the_goal`
- `tests/test_tier5_regressions.py::TestStartWithWindowsBehaviour::test_tray_launch_has_an_icon_but_no_visible_window`
- `tests/test_tier5_regressions.py::TestSurvivesDataLoss::test_a_wiped_row_is_rebuilt_from_stripe`
- `tests/test_tier6_email.py::TestDelivery::test_a_licence_is_emailed_once_and_only_once`
- `tests/test_tier6_email.py::TestDelivery::test_resend_is_explicitly_allowed_to_send_again`


---

## 5. Screenshots

Captured locally in `screenshots/pytest-20260922-061824` — 3 images, not committed to the repository.

| Step | File |
| --- | --- |
| 01 loaded | `stripe-01-loaded.png` |
| 02 filled | `stripe-02-filled.png` |
| 03 success | `stripe-03-success.png` |

Regenerate them any time with `python automation/e2e_runner.py`, or `python automation/smoke_ui.py` for a quick four-tab sweep.


---

## 6. Running it yourself

Start the two services:

```
cd Server && npm install && npm start
```

```
cd Website && python -m http.server 5500
```

Build and launch the app:

```
cd DesktopApp && dotnet build -c Release && dotnet run -c Release
```

Run the automation (it starts the services itself if they aren't already up):

```
python automation/e2e_runner.py
```

```
python -m pytest automation/tests -v --json-report --json-report-file=reports/pytest_report.json
```

Useful flags: `--headless` for the checkout browser, `--skip-build` to reuse the
existing binary. `python automation/smoke_ui.py` captures all four tabs in one pass.

---

## 7. Known limitations

- **The Stripe account is not created by the automation.** Registering a
  financial-services account under a disposable identity violates Stripe's
  terms, and the registration flow is gated by SMS and bot detection. This is a
  deliberate boundary, not a missing feature — `STRIPE_SETUP.md` covers the
  five-minute manual path.
- **Webhooks cannot reach `localhost` from Stripe's cloud.** `GET /get-license`
  therefore reconciles against the Stripe API directly, so activation does not
  depend on webhook delivery. Run `stripe listen --forward-to
  http://localhost:3000/webhook` to exercise the real webhook path as well; the
  two converge on the same row and both are idempotent.
- **`better-sqlite3` is pinned to v12, not the v9 originally specified.** npm 11
  blocks native install scripts by default; v9 has no prebuild for Node 24 and
  would need a compiler. `db.js` also falls back to the built-in `node:sqlite`
  if the native module is unavailable at all.
- **The blocker's enforcement is conservative by design.** It acts only while a
  sprint or sleep window is active, and never terminates a process on the
  hard-coded critical list (shells, `explorer`, `lsass`, the app itself, and
  common developer tooling). Letting a distraction through is a far cheaper
  failure than killing something that matters.
- **Sealed mode locks the blocklist, not the process.** A determined user can
  still quit FlowShield from Task Manager. Making that genuinely hard needs a
  Windows service and elevation, which is out of scope here.
- **UI tests are slow.** Each launches a clean instance (~15s cold start).
  That's deliberate: sharing an instance breaks isolation because `launch_app()`
  clears stray processes.

---

## 8. Switching to Stripe live mode

Do this only when you actually intend to charge real cards.

1. **Activate the account.** Live keys require completing Stripe's business and
   bank-details onboarding. Test mode needs none of that.
2. **Recreate the product in live mode.** Price IDs do not cross the test/live
   boundary — run `node tools/setup_stripe_store.js` against live mode (after
   deliberately lifting its test-key guard) to create *FlowShield* at a one-time
   $4.99, and copy the new `price_...`.
3. **Swap the credentials** in `.stripe_keys.json` for the `pk_live_` /
   `sk_live_` pair, or set `STRIPE_SECRET_KEY` and friends in the environment
   instead so no secret sits on disk.
4. **Host the webhook somewhere reachable.** `http://localhost:3000/webhook`
   cannot receive live events. Deploy the server, register the public HTTPS URL
   under Developers → Webhooks for `checkout.session.completed` and
   `charge.refunded` (plus the two `customer.subscription.*` events while any
   old monthly licences remain), and use
   that endpoint's signing secret.
5. **Serve both server and site over HTTPS**, and set `WEBSITE_URL` on the
   server so success/cancel URLs point at the deployed site rather than
   localhost.
6. **Re-point the desktop app** — `LicenseServerUrl` and `WebsiteUrl` in
   `AppSettings` default to localhost; ship the production values.
7. **Guard the test suite.** `test_server_is_in_test_mode_when_configured`
   fails against live keys on purpose. Keep it that way; point the suite at a
   test-mode server instead of relaxing the assertion.

Before going live, confirm on a real card that the payment appears under
Payments and that a refund propagates back to `IsPro` being cleared in the app
within one validation cycle.
