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
request takes ~50 seconds to wake it. The desktop app's HTTP timeout is 20
seconds, so the first activation after an idle period can fail and need a
retry. Fixes, in order of cost: retry once on timeout (I can do this), a
$7/month paid instance (never sleeps), or a cron ping every 10 minutes.

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
  could activate with it. That's a deliberate trade for a $4.99 tool, but if it
  matters, the fix is to email the licence key at purchase and require the key.
- Nothing currently sends email. Wiring the webhook to an email provider is the
  natural next step and would let the success page stop asking buyers to
  self-activate.
