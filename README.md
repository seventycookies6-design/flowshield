# FlowShield

A Windows focus timer and app blocker. Distractions go behind a shield whose
strength you pick per sprint, and finished sprints compound into momentum.

```
Shield I  · Soft    a dismissible full-screen nudge
Shield II · Firm    blocked apps are closed on sight
Shield III· Sealed  closed on sight, and the blocklist locks until the timer ends  (Pro)
```

**Momentum, not streaks.** A completed sprint adds to a momentum score; an
abandoned one decays it (×0.85 − 2, floored at zero) rather than resetting it.
One bad afternoon shouldn't erase a month. Every sprint ends with a one-line
"what moved?" journal entry.

---

## Layout

| Path | What it is |
| --- | --- |
| `DesktopApp/` | .NET 8 WPF app (MVVM). Settings are DPAPI-encrypted per user. |
| `Server/` | Express + SQLite license server, real Stripe subscriptions. |
| `Website/` | Static marketing site and post-checkout license page. |
| `automation/` | pywinauto + Playwright + pytest suite that drives all of it. |
| `tools/` | Small maintenance scripts. |

## Prerequisites

.NET SDK 8+ (10 works — it builds `net8.0-windows`), Node 18+, Python 3.11+.

```bash
pip install pywinauto pyautogui playwright pillow requests psutil colorama pytest pytest-json-report
```

```bash
python -m playwright install chromium
```

## Running it

```bash
cd Server && npm install && npm start
```

```bash
cd Website && python -m http.server 5500
```

```bash
cd DesktopApp && dotnet build -c Release && dotnet run -c Release
```

The server answers on `http://localhost:3000` (`/health` reports its
configuration), the site on `http://localhost:5500`.

### Stripe

Payment routes return a `503` that names the missing fields until you add test
credentials. **`STRIPE_SETUP.md`** walks through it — about five minutes, one
time. Nothing else is blocked by this: the app, the site and the whole non-payment
test suite run without any Stripe account.

Creating that account is deliberately left to a human. Registering a
financial-services account under a generated identity breaks Stripe's terms, and
a secret key never needs to pass through an assistant to be used.

## Testing

```bash
python automation/e2e_runner.py
```

Builds, starts both services, launches the app, walks the purchase path through a
real Stripe test-mode checkout, activates the license, and verifies the result
against the encrypted settings file. Steps needing Stripe report as **skipped**,
never as passed, when it isn't configured.

```bash
python -m pytest automation/tests -v
```

| Tier | File | Scope |
| --- | --- | --- |
| 1 | `test_tier1_unit.py` | Key checksums, sleep windows, tier limits, momentum. No app, no network. |
| 2 | `test_tier2_integration.py` | Every server endpoint, webhook signatures, replay guard. |
| 3 | `test_tier3_e2e.py` | The real UI via UI Automation, cross-checked against disk. |
| 4 | `test_tier4_adversarial.py` | Forged keys, injection, concurrency, tampered storage, declined cards. |

Handy extras: `python automation/smoke_ui.py` captures all four tabs in one pass;
`python automation/make_report.py` regenerates `FINAL_REPORT.md`.

Markers: `-m "not stripe"` skips anything needing credentials, `-m "not ui"`
skips the slow desktop-driving tests.

## Notes on the design

**The blocker is deliberately timid.** It only acts while a sprint or sleep
window is running, and it will never terminate a process on a hard-coded
critical list (shells, `explorer`, `lsass`, common developer tooling, itself).
Letting one distraction through is a much cheaper mistake than killing something
that matters.

**Activation doesn't depend on webhook delivery.** Stripe's cloud can't reach
`localhost`, so `GET /get-license` reconciles against the Stripe API directly.
Run `stripe listen --forward-to http://localhost:3000/webhook` to exercise the
webhook path too — both paths converge on the same row and both are idempotent.

**Settings are encrypted, and the tests prove it.** `settings.json` is a DPAPI
envelope scoped to the current user. Tier 3 asserts that no plaintext value
appears on disk *and* that the value is recoverable through DPAPI, so the test
can't pass just because a write failed.

## Licence

Demonstration project. Stripe runs in test mode; no real money moves.
