# Stripe setup

The store is **already set up** for the account currently in
`.stripe_keys.json`. This document records how it was done and what to change
before taking real money.

Stay in **test mode** throughout. Nothing here moves real money.

---

## Current state

| Thing | Value |
| --- | --- |
| Product | `FlowShield` (`metadata.edition = one_time`) |
| Price | `$4.99`, one-time |
| Tax code | `txcd_10202000` — Downloadable Software, personal use |
| Payment Link | `https://buy.stripe.com/test_…` (in `Website/config.js`) |
| Confirmation page | `https://seventycookies6-design.github.io/flowshield/success.html` |

Everything is tagged `metadata.app = flowshield`, which is how the setup script
finds it again instead of creating duplicates.

FlowShield used to be a $4.99/month subscription on the product `FlowShield
Pro`. That product and its monthly price are left in place, untouched, for the
licences bought on it; the setup script now looks only for the one-time product
and deactivates the old monthly Payment Link.

---

## Re-running the setup

```bash
node tools/setup_stripe_store.js --site https://seventycookies6-design.github.io/flowshield
```

Idempotent — it reuses the existing product, price and Payment Link, only
creating what is missing. It refuses outright if handed a `sk_live_` key.

Useful flags:

- `--dry-run` — connect and report, change nothing.
- `--webhook <https url>` — also register a webhook endpoint and capture its
  signing secret. Pointless for `localhost`; see below.

---

## Getting the keys yourself

<https://dashboard.stripe.com/test/apikeys> with **Test mode** on:

- **Publishable key** → `pk_test_…`
- **Reveal test key** → **Secret key** → `sk_test_…`

Put them in `.stripe_keys.json`. Environment variables override the file if you
would rather keep secrets off disk: `STRIPE_SECRET_KEY`,
`STRIPE_PUBLISHABLE_KEY`, `STRIPE_PRICE_ID`, `STRIPE_WEBHOOK_SECRET`.

`.stripe_keys.json` is in `.gitignore` and the publish script refuses to run if
it ever becomes tracked. Keep it that way.

---

## About the webhook secret

> **The `webhook_secret` currently in `.stripe_keys.json` is a locally
> generated development value, not a real Stripe secret.** Replace it before
> relying on webhook delivery.

Stripe's servers cannot reach `http://localhost:3000/webhook`, so there is no
real endpoint to get a secret from yet. A local value still exercises the whole
signature path for real — the server verifies every incoming event against it,
and the test suite signs synthetic events with the same secret — it simply
isn't the secret Stripe would sign with.

Activation does **not** depend on webhooks. `GET /get-license` asks Stripe for
the session's true state directly, so a missed webhook cannot strand a paying
customer. The webhook exists to catch later changes (refunds, and cancellations
of old monthly licences) promptly; `/validate` re-checks a purchase with Stripe
as well, so a missed refund webhook is caught on the next check.

To use the real thing, either:

**Stripe CLI** — forwards live events to your machine:

```bash
stripe listen --forward-to http://localhost:3000/webhook
```

It prints a `whsec_…`; put that in `.stripe_keys.json` and restart the server.

**Deployed endpoint** — once the server is hosted somewhere public, register
`https://your-host/webhook` under Developers → Webhooks for
`checkout.session.completed`, `charge.refunded`, `customer.subscription.updated`
and `customer.subscription.deleted` (the last two only matter for old monthly
licences), then copy that endpoint's signing secret. Re-running the setup
script with `--webhook <url>` adds any missing events to an existing endpoint
without changing its secret.

---

## About the tax code

Managed Payments is enabled by default on newer Stripe accounts, and it refuses
line items whose product has no tax code. The product is set to
`txcd_10202000` — *Downloadable Software, personal use* — because FlowShield is
a desktop app you download and run locally, sold to individuals. It is not SaaS;
nothing executes on a server.

This only affects tax calculation — but that calculation runs in test mode too:
a test purchase with ZIP 90210 was charged 8.25% sales tax ($5.40 for the
$4.99 plan). The site says the price is plus sales tax where it applies.
**Confirm it with whoever does your taxes before going live.** Plausible
alternatives:

| Code | Meaning |
| --- | --- |
| `txcd_10202003` | Downloadable Software — business use |
| `txcd_10103000` | SaaS — personal use |
| `txcd_10103001` | SaaS — business use |

Change it with `FLOWSHIELD_TAX_CODE=txcd_… node tools/setup_stripe_store.js`,
or in the dashboard on the product.

---

## Test card

`4242 4242 4242 4242` · expiry `12/34` · CVC `123` · ZIP `90210`

More cards, including declines: <https://docs.stripe.com/testing>

---

## Verifying

```bash
cd Server && npm start
```

`http://localhost:3000/health` should report `"configured": true` and
`"mode": "test"`. Then:

```bash
python automation/e2e_runner.py
```
