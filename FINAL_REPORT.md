# FlowShield — build & test report

_Generated 2026-09-11 08:42_

---

## 1. What this is

**FlowShield** is a Windows focus-timer and app blocker. Distractions go behind a
shield whose strength you choose per sprint, and finished sprints compound into a
momentum score.

The twist is **escalating shield levels** plus **momentum instead of streaks**:

| Level | Name | Behaviour |
| --- | --- | --- |
| Shield I | Soft | A dismissible full-screen nudge. |
| Shield II | Firm | Blocked apps are closed on sight; the blocklist stays editable. |
| Shield III | Sealed *(Pro)* | Closed on sight **and** the blocklist locks until the timer ends. |

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

### Free vs Pro

| | Free | Pro — $4.99/mo |
| --- | --- | --- |
| Blocked apps | 3 | Unlimited |
| Shield levels | I, II | I, II, **III Sealed** |
| Sprint length | ≤ 25 min | Any |
| Sleep blocking | — | ✅ |
| Hard kill mode | — | ✅ |
| History | 7 days | Unlimited + momentum analytics |

---

## 2. Stripe configuration

**Status: configured (TEST mode).**

| Credential | Value |
| --- | --- |
| Publishable key | `pk_test_51U8••••••••••••••••••` _(redacted)_ |
| Secret key | `sk_test_51••••••••••••••••••` _(redacted)_ |
| Price ID | `price_1UEN5uCcqk10eo83Od3c7gCq` |
| Webhook secret | `whsec_7u••••••••••••••••••` _(redacted)_ |

Secret values are redacted here by design — this file is meant to be shareable.
The real values live only in `.stripe_keys.json`, which is git-ignored.


---

## 3. End-to-end run

Run `20260911-080256` · 325.16s · **17 passed, 0 failed, 0 skipped**

| # | Step | Result | Time |
| --: | --- | --- | --: |
| 1 | Build the desktop app | ✅ passed — FlowShield.exe built | 4.14s |
| 2 | Start the license server | ✅ passed — db=better-sqlite3 stripe=configured (test) | 0.03s |
| 3 | Start the website | ✅ passed — http://localhost:5500 serving 13352 bytes | 4.11s |
| 4 | Launch FlowShield (clean state) | ✅ passed — pid 24356 | 0.06s |
| 5 | Connect to the app window via UI Automation | ✅ passed — hwnd 4000342, title 'Today' | 19.83s |
| 6 | Navigate to Settings | ✅ passed — status='Free plan', badge='FREE' | 16.86s |
| 7 | Click ★ Get Pro (opens the website) | ✅ passed — upgrade page launched; toast='Opened the upgrade page in your browser.' | 13.29s |
| 8 | Website → POST /create-checkout | ✅ passed — key=FS-GJ2S-13GY-DB2H-2K8N session=cs_test_b1bb5iqbltJeADphMBWclfvJ1S2u2WA2VTPN4jcanuck8Nk31rlFYh9a1i | 0.96s |
| 9 | Stripe Checkout — pay with the 4242 test card | ✅ passed — session=cs_test_b1bb5iqbltJeADphMBWclfvJ1S2u2WA2VTPN4jcanuck8Nk31rlFYh9a1i | 107.47s |
| 10 | GET /get-license → retrieve the key | ✅ passed — key=FS-GJ2S-13GY-DB2H-2K8N status=active email=testbuyer@example.com | 0.26s |
| 11 | Activate Pro in the app | ✅ passed — status='✅ Pro Active' | 30.97s |
| 12 | Verify the UI reports Pro | ✅ passed — status='✅ Pro Active', badge='PRO' | 15.23s |
| 13 | Verify DPAPI settings.json has IsPro=true | ✅ passed — settings file is a DPAPI-protected envelope; IsPro=True, key=FS-GJ2S-13GY-DB2H-2K8N, status=active | 0.0s |
| 14 | Blocked Apps — add an app and verify it persists | ✅ passed — 1 in list; 'flowshield-test-target' persisted (list=['flowshield-test-target']) | 32.16s |
| 15 | Sleep Blocking — enable a schedule and verify it saves | ✅ passed — enabled=True, window=23:15:00 → 06:45:00; ui='Armed. The shield raises itself at 23:15.' | 44.03s |
| 16 | Pro gating — Shield III and the app limit | ✅ passed — shield description='Closed on sight, and the blocklist locks until the timer ends.' (pro=True) | 21.54s |
| 17 | Capture final state and write the report | ✅ passed — state captured | 14.16s |


---

## 4. Test suite

| Tier | Passed | Failed | Skipped |
| --- | --: | --: | --: |
| Tier 1 — unit | 62 | 0 | 0 |
| Tier 2 — server integration | 21 | 0 | 1 |
| Tier 3 — end-to-end UI | 24 | 0 | 0 |
| Tier 4 — adversarial | 37 | 0 | 0 |
| Tier 5 — regressions | 16 | 1 | 0 |
| Tier 6 — email delivery | 11 | 0 | 0 |
| **Total** | **171** | **1** | **1** |

Duration: 2033.4s · 173 tests collected

**Failing tests**

- `tests/test_tier5_regressions.py::TestSurvivesDataLoss::test_recovery_keeps_the_key_the_customer_already_has`


---

## 5. Screenshots

Captured locally in `screenshots/e2e-20260911-080256` — 12 images, not committed to the repository.

| Step | File |
| --- | --- |
| App launched | `05-app-launched.png` |
| Settings free | `06-settings-free.png` |
| After get pro | `07-after-get-pro.png` |
| License key entered | `11-license-key-entered.png` |
| Pro activated | `11-pro-activated.png` |
| Blocked app added | `14-blocked-app-added.png` |
| Sleep blocking saved | `15-sleep-blocking-saved.png` |
| Shield selection | `16-shield-selection.png` |
| Final settings | `17-final-settings.png` |
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
   boundary — toggle to live, create *FlowShield Pro* at $4.99/month, copy the
   new `price_...`.
3. **Swap the credentials** in `.stripe_keys.json` for the `pk_live_` /
   `sk_live_` pair, or set `STRIPE_SECRET_KEY` and friends in the environment
   instead so no secret sits on disk.
4. **Host the webhook somewhere reachable.** `http://localhost:3000/webhook`
   cannot receive live events. Deploy the server, register the public HTTPS URL
   under Developers → Webhooks for `checkout.session.completed`,
   `customer.subscription.updated` and `customer.subscription.deleted`, and use
   that endpoint's signing secret.
5. **Serve both server and site over HTTPS**, and set `WEBSITE_URL` on the
   server so success/cancel URLs point at the deployed site rather than
   localhost.
6. **Re-point the desktop app** — `LicenseServerUrl` and `WebsiteUrl` in
   `AppSettings` default to localhost; ship the production values.
7. **Guard the test suite.** `test_server_is_in_test_mode_when_configured`
   fails against live keys on purpose. Keep it that way; point the suite at a
   test-mode server instead of relaxing the assertion.

Before going live, confirm on a real card that the subscription appears under
Customers → Subscriptions and that a cancellation propagates back to `IsPro`
being cleared in the app within one validation cycle.
