# Selling FlowShield to strangers

What's ready, what you have to buy, and what's still open. Written to be
accurate rather than encouraging.

---

## Ready now

| | |
| --- | --- |
| Installer | `FlowShield-win-Setup.exe`, 69.5 MB, self-contained — no .NET install needed |
| Download | <https://github.com/seventycookies6-design/flowshield/releases/latest> |
| Auto-update | In-app, from GitHub Releases; deferred while a sprint is running |
| Site | <https://seventycookies6-design.github.io/flowshield/> |
| Licence server | <https://flowshield-license-server.onrender.com> |
| Legal pages | `/legal.html` — terms, privacy, refunds (drafts, see below) |
| Payments | Stripe, **test mode** |

Cutting a new version:

```bash
pwsh tools/build_release.ps1 -Version 1.0.1 -Publish
```

Existing installs pick it up from Settings → Check for updates.

---

## What you have to buy

Nothing below can be done in code. Rough order of importance.

### 1. Code-signing certificate — £/$200–400 a year

**The biggest barrier to a stranger installing this.** Unsigned, Windows
SmartScreen shows "Windows protected your PC" and hides the Run button behind
*More info*. Most people stop there. For software whose job is closing other
programs, an "unknown publisher" warning is especially costly.

An OV certificate builds reputation over weeks; an EV certificate carries
SmartScreen reputation immediately and costs more. Once you have one:

```bash
vpk pack ... --signParams "/fd sha256 /f cert.pfx /p PASSWORD /tr http://timestamp.digicert.com /td sha256"
```

### 2. A domain — ~$15 a year

Three things currently look wrong to a buyer:

- The site is at `github.io`, which reads as a hobby project
- Your Stripe account is named **"Focus Unlock sandbox"** — that name appears
  on the checkout page while someone is buying *FlowShield*. Rename it in
  Stripe → Settings → Business details
- Licence emails would come from `onboarding@resend.dev` or a Gmail address,
  which hurts both credibility and deliverability

A domain fixes all three. Point it at GitHub Pages, verify it with your email
provider, and set `EMAIL_FROM` to something on it.

### 3. Paid hosting — $7 a month

The free Render instance sleeps after 15 minutes. The first activation after a
quiet spell takes ~50 seconds. The app retries, so it works, but a customer's
first impression is a spinner. The paid tier also gets a persistent disk, which
removes the Stripe recovery round-trip after each deploy.

### 4. Legal review

`Website/legal.html` is drafted and accurate about what the software does —
including that it closes programs and may lose unsaved work. It is not legal
advice. Consumer-subscription rules differ by country (UK/EU 14-day
cancellation, US state auto-renewal disclosure laws). Have someone qualified
read it, and fill in the placeholders: operator name, registered address,
support email.

---

## Going live on Stripe

Do this last, not first.

1. **Activate the account** — real business details, bank account, tax info.
2. **Recreate the product in live mode.** Price IDs do not cross the test/live
   boundary. `node tools/setup_stripe_store.js` with a live key builds the
   product, price and Payment Link — but it deliberately refuses `sk_live_`
   keys, so remove that guard consciously rather than by accident.
3. **Re-register the webhook** against the live endpoint and update
   `STRIPE_WEBHOOK_SECRET`.
4. **Swap the keys** in Render's environment.
5. Leave `test_server_is_in_test_mode_when_configured` failing as your reminder
   that the suite now points at live money. Point the suite at a test-mode
   server instead of deleting the assertion.

---

## Known weaknesses

**An email address alone unlocks Pro.** A Payment Link buyer has nothing else,
so this is a deliberate trade — but anyone who knows a customer's email can
activate with it. Closing it properly means requiring the licence key and
treating email activation as a support action rather than a self-service one.

**No device limit.** One key works on unlimited machines. `activation_count` is
recorded but never enforced. If FlowShield ever gets posted to a forum, one key
serves everyone. A per-licence device cap is a contained change to
`POST /validate` plus a device identifier from the app.

**Unsigned.** See above. This is the one that will cost you the most installs.

**No crash reporting.** If the app fails on someone else's machine you will not
hear about it unless they email you. There is a local diagnostic log at
`%APPDATA%\FlowShield\logs`, which support can ask for.

**Windows only, x64 only.** No ARM64 build, no macOS.

**Tested on one machine.** Windows 11, one hardware configuration. The installer
has never run on a clean machine without .NET or developer tooling present.

---

## Where user data lives

| Path | Contents | Survives uninstall |
| --- | --- | --- |
| `%APPDATA%\FlowShield\` | Settings, licence, sessions, logs | Yes |
| `%LOCALAPPDATA%\FlowShield\` | The application and update packages | No |

These are deliberately separate. The installer **deletes** its own directory on
install and uninstall — settings kept there would take the customer's licence
key with them. An earlier build did exactly that; `tier5` now guards it.
