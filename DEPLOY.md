# The licence server — deployed

**Live: <https://flowshield-license-server.onrender.com>**

| | |
| --- | --- |
| Host | Render, free plan, Docker, region `oregon` |
| Config | `render.yaml` (in git) + four secrets entered in the dashboard |
| Health | <https://flowshield-license-server.onrender.com/health> |
| Webhook | `/webhook`, enabled, signature-verified, delivering |
| Database | `node:sqlite` at `/data/licenses.db` — a cache of Stripe |

The full loop is verified end to end: a purchase on the published site issues a
licence key on the success page, and the shipped desktop binary activates Pro
against this server with no local services running.

## How it was connected

Render is pointed at the **public repository URL** rather than a linked GitHub
account, so Render holds no OAuth grant over the GitHub account. The trade-off
is that **auto-deploy on push does not work** — after pushing, click *Manual
Deploy → Deploy latest commit* in the Render dashboard. Connecting GitHub in
Render's settings would enable automatic deploys if that becomes annoying.

## Licence-key emails

The server emails the key on `checkout.session.completed`, which is the path
that fires even when the buyer closes the tab before the success page loads.
Delivery is claimed once per licence in the database, so the webhook, a Stripe
retry and the success-page lookup can't produce three copies.

**It is off until a provider is configured**, and that is deliberate — sending
happens after a payment has already succeeded, so a missing or broken provider
skips rather than failing the webhook and making Stripe retry a purchase that
worked. Check the current state at `/health` under `email`.

Pick one and add it in Render → Environment:

| Provider | Variables | Notes |
| --- | --- | --- |
| **Resend** | `RESEND_API_KEY` | Free 3,000/month. Until you verify a domain it can only send to your own account address — fine for testing, not for customers. |
| **SMTP** (incl. Gmail) | `SMTP_URL`, e.g. `smtps://you%40gmail.com:app-password@smtp.gmail.com:465` | Gmail needs 2FA plus an App Password, and caps at ~500/day. Sends to anyone. |

Also set `EMAIL_FROM` to an address on a domain the provider has verified, and
optionally `EMAIL_REPLY_TO` for support replies. Then **Manual Deploy** and
confirm `/health` reports `"email": {"configured": true}`.

`POST /resend-license {"email":"..."}` re-sends a key. It answers identically
whether or not the address has a subscription, so it can't be used to check who
your customers are.

### Testing without a provider

```bash
EMAIL_CAPTURE_DIR=./outbox npm start
```

Messages are written to `./outbox` as JSON instead of being sent. Capture takes
priority over real credentials specifically so a test run can never email an
actual customer — `tier6` relies on that.

## Redeploying

```bash
git push origin main
```

then **Manual Deploy** in Render. Verify with:

```bash
curl https://flowshield-license-server.onrender.com/health
```

```bash
python automation/verify_deployed.py FS-XXXX-XXXX-XXXX-XXXX
```

The last one launches the shipped binary with no overrides and activates a real
licence over the internet — the closest thing to being a customer.

---

## What to expect from the free tier

**It sleeps.** No traffic for 15 minutes and the instance spins down; the next
request takes ~50 seconds to wake it. The desktop app's HTTP timeout is 35
seconds and it retries up to twice on a timeout, so the first activation after
an idle period usually succeeds, just slowly — a customer can wait about a
minute. To remove the wait: a $7/month paid instance (never sleeps), or a cron
ping every 10 minutes.

**The disk is ephemeral.** `licenses.db` is wiped on every deploy. That is
survivable by design — the server treats the database as a cache of Stripe and
rebuilds any row it is missing, by licence key stamped into subscription
metadata or by the customer's email. `tier5` has tests that wipe a real row and
assert the customer keeps Pro. A paid plan with a persistent disk removes the
recovery round-trip; uncomment the `disk:` block in `render.yaml`.

## Other hosts

Nothing here is Render-specific beyond `render.yaml` — the `Dockerfile` is
plain Node. Fly.io, Railway and Google Cloud Run all work; set the same
environment variables (`WEBSITE_URL`, `ALLOWED_ORIGINS`, `STRIPE_*`) and point
the health check at `/health`.

## Before real money

- Swap the test keys for live ones and recreate the product in live mode
  (price IDs don't cross the test/live boundary).
- Note the activation model: **an email address alone unlocks Pro**, because a
  Payment Link buyer has nothing else. Anyone who knows a customer's email
  could activate with it — but, since #21, not obtain the key, open the billing
  portal, or touch devices; those need the licence key. If activation itself
  matters, the fix is to email the licence key at purchase and require the key.
- Email delivery is built (Resend or SMTP) but no provider is configured, so
  nothing is sent yet; `/health` reports `email: disabled`. Configuring one lets
  the success page stop telling buyers their key is shown only once.
- The customer-facing endpoints are rate limited per client IP
  (`RATE_LIMIT_PER_MINUTE`, default 30 per route; 0 disables).
