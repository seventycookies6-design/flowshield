# Stripe setup — the one manual step

Everything else in this project is automated. Creating the Stripe account and
reading its secret key are the two things I will not do on your behalf:
registering a financial-services account under a disposable identity breaks
Stripe's terms of service, and I never need to see an `sk_` value to write code
against it. Five minutes of clicking and the whole suite runs green.

Stay in **test mode** throughout. Nothing here touches real money.

---

## 1. Account

<https://dashboard.stripe.com/register> — real email, any password. Confirm the
email, then **skip** the "activate your account" business-details prompt; test
mode works without it. Check that the **Test mode** toggle (top right) is on:
every key you copy below must start with `pk_test_` / `sk_test_`.

## 2. API keys

Developers → **API keys** (<https://dashboard.stripe.com/test/apikeys>)

- Copy the **Publishable key** → `pk_test_…`
- **Reveal test key** → copy the **Secret key** → `sk_test_…`

## 3. Product and price

Product catalogue → **Add product** (<https://dashboard.stripe.com/test/products/create>)

| Field          | Value              |
| -------------- | ------------------ |
| Name           | `FlowShield Pro`   |
| Price          | `4.99`             |
| Currency       | USD                |
| Billing period | Monthly, recurring |

Save, then open the product and copy the **price** ID from the pricing table —
`price_…`, **not** the `prod_…` ID above it.

## 4. Webhook secret

Two options; either works.

**Option A — Stripe CLI (recommended, forwards real events to localhost):**

```bash
stripe login
```

```bash
stripe listen --forward-to http://localhost:3000/webhook
```

The command prints `whsec_…` — use that.

**Option B — dashboard endpoint.** Developers → Webhooks → Add endpoint, URL
`http://localhost:3000/webhook`, events `checkout.session.completed`,
`customer.subscription.updated`, `customer.subscription.deleted`. Copy the
signing secret. Note that Stripe cannot actually deliver to `localhost` from the
cloud, so the endpoint stays idle — that is fine. `GET /get-license` asks Stripe
for the session state directly, so activation does not depend on webhook
delivery. The E2E run passes either way; Option A additionally exercises the
live webhook path.

## 5. Paste the values

Edit `.stripe_keys.json` in this folder:

```json
{
  "publishable_key": "pk_test_51...",
  "secret_key": "sk_test_51...",
  "price_id": "price_1...",
  "webhook_secret": "whsec_..."
}
```

Environment variables override the file if you prefer not to have secrets on
disk: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_PRICE_ID`,
`STRIPE_WEBHOOK_SECRET`.

## 6. Verify and run

```bash
cd C:\Users\xBlah\Downloads\NewApp\Server && npm start
```

`http://localhost:3000/health` should report `"configured": true` and
`"mode": "test"`. Then:

```bash
python C:\Users\xBlah\Downloads\NewApp\automation\e2e_runner.py
```

## Test card

`4242 4242 4242 4242` · expiry `12/34` · CVC `123` · ZIP `90210`

---

`.stripe_keys.json` is listed in `.gitignore`. Keep it that way — a leaked
`sk_test_` key is low-stakes but still lets a stranger write to your test data.
