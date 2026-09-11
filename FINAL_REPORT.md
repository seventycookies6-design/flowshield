# FlowShield — build & test report

_Generated 2026-09-10 23:55_

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

**Status: not configured.** Payment-path steps were skipped, not faked.

Missing: `publishable_key`, `secret_key`, `price_id`, `webhook_secret`

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

Run `20260910-230606` · 130.26s · **10 passed, 0 failed, 7 skipped**

| # | Step | Result | Time |
| --: | --- | --- | --: |
| 1 | Build the desktop app | ✅ passed — FlowShield.exe built | 1.3s |
| 2 | Start the license server | ✅ passed — db=better-sqlite3 stripe=NOT configured (unset) | 1.13s |
| 3 | Start the website | ✅ passed — http://localhost:5500 serving 13222 bytes | 4.03s |
| 4 | Launch FlowShield (clean state) | ✅ passed — pid 25160 | 0.04s |
| 5 | Connect to the app window via UI Automation | ✅ passed — hwnd 6229942, title 'Today' | 17.69s |
| 6 | Navigate to Settings | ✅ passed — status='Free plan', badge='FREE' | 15.54s |
| 7 | Click ★ Get Pro (opens the website) | ✅ passed — upgrade page launched; toast='Opened the upgrade page in your browser.' | 11.88s |
| 8 | Website → POST /create-checkout | ⏭️ skipped — Stripe not configured (missing: publishable_key, secret_key, price_id, webhook_secret) | 0.0s |
| 9 | Stripe Checkout — pay with the 4242 test card | ⏭️ skipped — no checkout session to pay for | 0.0s |
| 10 | GET /get-license → retrieve the key | ⏭️ skipped — no completed checkout session | 0.0s |
| 11 | Activate Pro in the app | ⏭️ skipped — no license key available | 0.0s |
| 12 | Verify the UI reports Pro | ⏭️ skipped — activation did not run | 0.0s |
| 13 | Verify DPAPI settings.json has IsPro=true | ⏭️ skipped — activation did not run | 0.0s |
| 14 | Blocked Apps — add an app and verify it persists | ✅ passed — 1 in list; 'flowshield-test-target' persisted (list=['flowshield-test-target']) | 30.71s |
| 15 | Sleep Blocking — enable a schedule and verify it saves | ⏭️ skipped — no Pro licence — verified the feature stays gated instead | 15.66s |
| 16 | Pro gating — Shield III and the app limit | ✅ passed — shield description='Blocked apps are closed on sight.' (pro=False) | 19.59s |
| 17 | Capture final state and write the report | ✅ passed — state captured | 12.64s |


---

## 4. Test suite

| Tier | Passed | Failed | Skipped |
| --- | --: | --: | --: |
| Tier 1 — unit | 62 | 0 | 0 |
| Tier 2 — server integration | 13 | 0 | 9 |
| Tier 3 — end-to-end UI | 22 | 0 | 2 |
| Tier 4 — adversarial | 35 | 0 | 2 |
| **Total** | **132** | **0** | **13** |

Duration: 1174.3s · 145 tests collected


---

## 5. Screenshots

Captured locally in `screenshots/e2e-20260910-230606` — 7 images, not committed to the repository.

| Step | File |
| --- | --- |
| App launched | `05-app-launched.png` |
| Settings free | `06-settings-free.png` |
| After get pro | `07-after-get-pro.png` |
| Blocked app added | `14-blocked-app-added.png` |
| Sleep blocking gated | `15-sleep-blocking-gated.png` |
| Shield selection | `16-shield-selection.png` |
| Final settings | `17-final-settings.png` |

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
