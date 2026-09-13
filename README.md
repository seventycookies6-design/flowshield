# FlowShield

**[Download for Windows](https://github.com/seventycookies6-design/flowshield/releases/latest/download/FlowShield-win-Setup.exe)**
· **[Site](https://seventycookies6-design.github.io/flowshield/)**
· **[Licence server](https://flowshield-license-server.onrender.com)**

Buying on the site issues a real licence key, and the installed app activates
Pro against the deployed server. Stripe is in **test mode** — see
**[SELLING.md](SELLING.md)** for what's left before charging real customers.

A Windows focus timer and app blocker. Distractions go behind a shield whose
strength you pick per sprint, and finished sprints compound into momentum.

```
Shield I  · Soft    a brief notice inside FlowShield; the blocked app keeps running
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
python -m pip install -r automation/requirements.txt
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

Put your test keys in `.stripe_keys.json` (see **`STRIPE_SETUP.md`**), then
create the product, price and Payment Link in one command:

```bash
node tools/setup_stripe_store.js --site https://seventycookies6-design.github.io/flowshield
```

It is idempotent — everything it creates is tagged `metadata.app=flowshield` and
looked up before being created, so re-running never leaves duplicates behind. It
writes the price id back to `.stripe_keys.json` and the Payment Link to
`Website/config.js`, then refuses outright if handed a `sk_live_` key.

Until that runs, the server's payment routes return a `503` naming the missing
fields, and the site's Get Pro button says so plainly. Nothing else is blocked:
the app, the site and the whole non-payment test suite need no Stripe account.

### Two ways to check out

The site picks automatically, because the published build has no backend:

| Mode | When | What happens |
| --- | --- | --- |
| **Payment Link** | No license server configured — i.e. the public site | The button links to a Stripe-hosted checkout page. Real payments, zero backend. |
| **License server** | `config.licenseServerUrl` is set, or `?server=http://host:port` | `POST /create-checkout` reserves a licence key first, so the success page can hand it straight over. |

GitHub Pages is static hosting, so the published site uses the Payment Link —
a visitor's browser plainly cannot reach *your* `localhost:3000`. Automatic
licence-key issuance needs the Node server hosted somewhere public; deploy it
and set `licenseServerUrl` in `Website/config.js` to switch the live site over.

## The deployed licence server

GitHub Pages is static, so the site alone cannot issue licence keys. The server
runs on Render (`Dockerfile` + `render.yaml`); **`DEPLOY.md`** covers redeploys
and the trade-offs of the free plan.

The database is treated as a **cache of Stripe, not the record**. Free hosting
tiers have ephemeral disks, so `licenses.db` is wiped on every redeploy; rather
than silently revoking Pro for everyone who paid, the server rebuilds missing
rows from Stripe — by the licence key stamped into subscription metadata, or by
the customer's email. Tier 5 wipes a real row and asserts the customer keeps
Pro, and keeps the key they already had.

## Cutting a release

```bash
pwsh tools/build_release.ps1 -Version 1.0.1 -Publish
```

Builds a self-contained win-x64 copy (customers don't need the .NET runtime),
packages it with Velopack into an installer plus an update feed, and publishes
both to GitHub Releases. Installed copies find it via Settings → Check for
updates; an update is never applied mid-sprint, since restarting would drop the
shield a sealed session exists to hold.

Builds are **not code signed**, so SmartScreen warns every customer.
[SELLING.md](SELLING.md) covers that and the rest of the gap to real revenue.

## Publishing the site

```bash
pwsh tools/publish_site.ps1
```

Splits `Website/` onto the `gh-pages` branch that Pages serves, after refusing
to publish if any Stripe secret has crept into `Website/` or if
`.stripe_keys.json` has become tracked.

A GitHub Actions workflow would be the more modern route, but pushing one needs
the `workflow` OAuth scope the local `gh` token doesn't carry. To switch:
`gh auth refresh -s workflow`.

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
| 5 | `test_tier5_regressions.py` | One test per bug found by reading the code; each verified to fail against the commit before its fix. |
| 6 | `test_tier6_email.py` | Licence-key delivery, once-only sending, and the resend endpoint — run against a capture provider so a test can never email a customer. |
| 7 | `test_tier7_devices.py` | The three-device cap: that it holds, and equally that it can't trap a paying customer. |

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
