# FlowShield — build & test report

_Generated 2026-09-22 01:59_

---

## 1. What this is

**FlowShield** is a Windows focus-timer and app blocker. Distractions go behind a
shield whose strength you choose per sprint, and finished sprints compound into a
momentum score.

The twist is **escalating shield levels** plus **momentum instead of streaks**:

| Level | Name | Behaviour |
| --- | --- | --- |
| Shield I | Soft | A brief notice inside FlowShield; the blocked app keeps running. |
| Shield II | Firm | Blocked apps are closed on sight; the blocklist stays editable. |
| Shield III | Sealed | Closed on sight **and** the blocklist locks for the rest of the sprint. |

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

**Status: not configured.** Payment-path steps were skipped, not faked.

Missing: `secret_key`, `price_id`

Creating the Stripe account is the one step left to a human — registering a
financial-services account under a generated identity breaks Stripe's terms,
and the secret key never needs to pass through an assistant to be used.
`STRIPE_SETUP.md` has the exact click-path; it takes about five minutes.

Once `.stripe_keys.json` is populated, re-run:

```
python automation/e2e_runner.py
```

and every skipped step above becomes a real test-mode purchase.


---

## 3. End-to-end run

_No E2E report found. Run `python automation/e2e_runner.py` first._


---

## 4. Test suite

| Tier | Passed | Failed | Skipped |
| --- | --: | --: | --: |
| Tier 1 — unit | 380 | 0 | 0 |
| Tier 2 — server integration | 20 | 0 | 12 |
| Tier 3 — end-to-end UI | 82 | 13 | 2 |
| Tier 4 — adversarial | 40 | 0 | 2 |
| Tier 5 — regressions | 369 | 1 | 6 |
| Tier 6 — email delivery | 10 | 0 | 3 |
| Tier 7 — device limit | 6 | 0 | 11 |
| **Total** | **907** | **14** | **36** |

Duration: 6135.1s · 957 tests collected

**Failing tests**

- `tests/test_tier3_e2e.py::TestAppShell::test_settings_cannot_be_read_without_dpapi`
- `tests/test_tier3_e2e.py::TestSprintIntention::test_a_long_intention_is_capped_and_stays_on_one_line`
- `tests/test_tier3_e2e.py::TestSprintIntention::test_cancelling_a_sprint_clears_the_intention_input`
- `tests/test_tier3_e2e.py::TestShieldWording::test_today_shows_the_promise_and_scenario_for_each_shield`
- `tests/test_tier3_e2e.py::TestTrialExpiringDuringASprint::test_the_lock_waits_for_the_sprint_and_its_summary`
- `tests/test_tier3_e2e.py::TestEndingASprint::test_cancelling_in_the_grace_period_leaves_no_record`
- `tests/test_tier3_e2e.py::TestEndingASprint::test_firm_needs_a_confirmation_that_waits`
- `tests/test_tier3_e2e.py::TestEndingASprint::test_sealed_needs_the_countdown_and_the_phrase`
- `tests/test_tier3_e2e.py::TestFirstRun::test_completing_it_saves_every_choice_and_starts_the_sprint`
- `tests/test_tier3_e2e.py::TestSpaceStartsAndEndsASprint::test_space_starts_a_sprint_and_opens_the_firm_end_flow`
- `tests/test_tier3_e2e.py::TestSpaceStartsAndEndsASprint::test_space_typed_into_the_intention_field_stays_a_space`
- `tests/test_tier3_e2e.py::TestHistoryPage::test_history_is_reachable_and_empty_to_begin_with`
- `tests/test_tier3_e2e.py::TestHistoryPage::test_the_week_picks_up_a_sprint_run_on_today`
- `tests/test_tier5_regressions.py::TestStartWithWindowsBehaviour::test_tray_launch_has_an_icon_but_no_visible_window`


---

## 5. Screenshots

_No screenshots captured yet. Run `python automation/e2e_runner.py`._


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

- **The payment path was not executed in this run** because Stripe has no
  credentials configured. Those steps are reported as *skipped*, never as
  passed. Everything else below ran for real.
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
