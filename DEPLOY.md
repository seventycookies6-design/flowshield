# Deploying the licence server

The site is live and takes payments. What it can't yet do is hand a buyer their
licence key, because issuing one needs the Node server and GitHub Pages only
serves static files. This is the step that closes that loop.

Everything is prepared — `Dockerfile`, `render.yaml`, health check, CORS, and
Stripe-backed recovery. The part left to you is creating the hosting account,
which I won't do on your behalf: signing up to a service under your name and
accepting its terms is your decision, not mine.

**Roughly ten minutes.** Free tier, no card.

---

## 1. Create the service

1. Sign in at <https://dashboard.render.com> with **GitHub** (you're already
   authenticated there).
2. **New → Blueprint**.
3. Pick the **`flowshield`** repository. Render reads `render.yaml` and
   proposes a service called `flowshield-license-server` — everything is
   already configured, so don't change anything.
4. It will prompt for four secrets, because they are deliberately not in the
   repo. Copy them from `.stripe_keys.json`:

   | Prompt | Value |
   | --- | --- |
   | `STRIPE_SECRET_KEY` | `sk_test_…` |
   | `STRIPE_PUBLISHABLE_KEY` | `pk_test_…` |
   | `STRIPE_PRICE_ID` | `price_…` |
   | `STRIPE_WEBHOOK_SECRET` | leave blank for now — step 3 replaces it |

5. **Apply**. First build takes 3–5 minutes.

You'll get a URL like `https://flowshield-license-server.onrender.com`.
Check it: `https://<your-url>/health` should report `"configured": true` and
`"mode": "test"`.

## 2. Tell me the URL

Paste it in chat and I'll do the rest:

- point `Website/config.js` at it and republish the site, so the success page
  issues real licence keys instead of asking buyers to self-activate
- set it as the desktop app's default `LicenseServerUrl` and rebuild
- register the webhook and store its signing secret
- run the suite against the deployed server to prove it end to end

## 3. Webhook (I'll do this once I have the URL)

Deployed, Stripe can finally reach the endpoint — which matters because it is
what records a Payment Link purchase when the buyer closes the tab before the
success page loads.

Developers → Webhooks → Add endpoint → `https://<your-url>/webhook`, events
`checkout.session.completed`, `customer.subscription.updated`,
`customer.subscription.deleted`. Then put the signing secret into Render's
`STRIPE_WEBHOOK_SECRET` environment variable.

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
