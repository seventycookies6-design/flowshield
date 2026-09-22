'use strict';

/**
 * FlowShield licence server.
 *
 * FlowShield is sold as a one-time purchase after a 7-day in-app trial. A
 * purchase is a Checkout Session in payment mode; its PaymentIntent carries the
 * licence key in metadata. Licences bought on the old monthly plan are
 * subscriptions and keep working through the same routes.
 *
 *   POST /create-checkout       -> { url, licenseKey, sessionId }
 *   POST /validate              -> { valid, isPro, status, ... }
 *   POST /webhook               -> Stripe event sink (signature verified)
 *   GET  /get-license           -> { licenseKey, ... } for a checkout session
 *   POST /create-portal-session -> { url } Stripe billing portal
 *   GET  /                      -> service descriptor
 *   GET  /health                -> liveness + configuration report
 */

const express = require('express');
const cors = require('cors');
const StripeLib = require('stripe');

const db = require('./db');
const licensekey = require('./licensekey');
const mail = require('./email');
const { loadKeys, describe, KEYS_PATH } = require('./keys');
const { createLimiter } = require('./ratelimit');

const PORT = Number(process.env.PORT || 3000);

/**
 * How many machines one licence may be activated on.
 *
 * Three is deliberately generous — a desktop, a laptop and a spare should not
 * inconvenience an honest customer — while still making a key posted publicly
 * useless to the fourth stranger who tries it. Set 0 to disable the cap.
 */
const DEVICE_LIMIT = Number(process.env.DEVICE_LIMIT ?? 3);
const WEBSITE_URL = (process.env.WEBSITE_URL || 'http://localhost:5500').replace(/\/$/, '');
const APP_NAME = 'FlowShield';

const keys = loadKeys();
const keyReport = describe(keys);

/**
 * Pinned so a future SDK bump can't silently change behaviour underneath us.
 *
 * Must be 2025-03-31.basil or later: newer Stripe accounts have Managed
 * Payments enabled by default, and it rejects older API versions outright.
 * From this version on, a subscription's current_period_end lives on the
 * subscription *item* rather than the subscription — periodEndOf() reads both.
 */
const STRIPE_API_VERSION = '2026-08-26.dahlia';

const stripe = keys.secret_key
  ? new StripeLib(keys.secret_key, {
      apiVersion: STRIPE_API_VERSION,
      appInfo: { name: `${APP_NAME} License Server`, version: '1.0.0' },
    })
  : null;

/*
 * CORS.
 *
 * ALLOWED_ORIGINS restricts which *browsers* may call this API. Requests with
 * no Origin header — the desktop app, curl, Stripe's webhooks — are always
 * allowed: the header is a browser mechanism and blocking its absence would
 * only break non-browser clients while stopping no attacker.
 *
 * Left unset, every origin is accepted. That is right for local development
 * and wrong in production, which is why render.yaml sets it explicitly.
 */
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || '')
  .split(',')
  .map((o) => o.trim().replace(/\/$/, ''))
  .filter(Boolean);

const app = express();
app.set('trust proxy', 1); // hosts terminate TLS upstream

app.use(
  cors({
    origin(origin, callback) {
      if (!origin || ALLOWED_ORIGINS.length === 0) return callback(null, true);
      const normalized = origin.replace(/\/$/, '');
      if (ALLOWED_ORIGINS.includes(normalized)) return callback(null, true);
      // Reject by withholding the header rather than erroring: the browser
      // blocks the response, and the log stays quiet under drive-by scans.
      return callback(null, false);
    },
  }),
);

// The webhook needs the untouched request body to verify the signature, so it
// is mounted with a raw parser *before* the global JSON parser.
app.use('/webhook', express.raw({ type: '*/*' }));
app.use(express.json({ limit: '256kb' }));

// Per-IP, per-route limit on the endpoints that answer questions about
// customers. See ratelimit.js; loopback (the test suite) is exempt.
const limiter = createLimiter({ limit: Number(process.env.RATE_LIMIT_PER_MINUTE ?? 30) });

/* ------------------------------------------------------------------ helpers */

const log = (...args) => console.log(`[${new Date().toISOString()}]`, ...args);

function requireStripe(res) {
  if (stripe && keys.price_id) return true;
  res.status(503).json({
    error: 'stripe_not_configured',
    message:
      `Stripe credentials are missing. Populate ${KEYS_PATH} (or the ` +
      'STRIPE_* environment variables) with your test-mode keys and restart.',
    missing: keyReport.missing,
  });
  return false;
}

/**
 * Recover a licence from Stripe when the local database doesn't know it.
 *
 * The database is a cache, not the record. Free hosting tiers have ephemeral
 * disks, so licenses.db is wiped on every redeploy — and without this, every
 * existing customer would silently drop to "not_found" and lose Pro after a
 * routine deploy. Stripe holds the real state, so rebuild the row from it.
 *
 * Two routes in: the licence key stamped into payment (or, for the old monthly
 * plan, subscription) metadata, and the customer's email address.
 *
 * Returns { payment | subscription, licenseKey, customer? } or null.
 */
async function recoverFromStripe({ key, email }) {
  if (!stripe) return null;

  // 1. By licence key, which create-checkout and the minting path both stamp
  //    into metadata.
  if (key) {
    const query = `metadata['license_key']:'${key.replace(/'/g, '')}'`;
    try {
      const payments = await stripe.paymentIntents.search({
        query,
        limit: 1,
        expand: ['data.latest_charge'],
      });
      if (payments.data.length) return { payment: payments.data[0], licenseKey: key };

      const found = await stripe.subscriptions.search({ query, limit: 1 });
      if (found.data.length) return { subscription: found.data[0], licenseKey: key };
    } catch (err) {
      // Search is eventually consistent and unavailable on brand-new accounts.
      log(`recover by key failed: ${err.message}`);
    }
  }

  // 2. By email — the only thing a Payment Link buyer reliably has.
  if (email) {
    try {
      const customers = await stripe.customers.list({ email, limit: 5 });

      // Gather every purchase across every customer with this address before
      // choosing. One person can hold several — the same address can buy
      // twice, and Stripe creates a separate customer each time a Payment Link
      // is used. Returning whichever happened to be listed first made recovery
      // non-deterministic and could hand back a licence key the customer has
      // never seen.
      const candidates = [];
      for (const customer of customers.data) {
        const payments = await stripe.paymentIntents.list({
          customer: customer.id,
          limit: 20,
          expand: ['data.latest_charge'],
        });
        for (const payment of payments.data) {
          if (payment.status !== 'succeeded') continue;
          // Only FlowShield purchases: the same Stripe account may sell other things.
          if (payment.metadata?.app !== APP_NAME && !payment.metadata?.license_key) continue;
          candidates.push({ payment, customer });
        }

        const subs = await stripe.subscriptions.list({
          customer: customer.id,
          status: 'all',
          limit: 10,
        });
        for (const subscription of subs.data) candidates.push({ subscription, customer });
      }

      if (candidates.length === 0) return null;

      const keyOf = (c) =>
        licensekey.normalize((c.payment || c.subscription).metadata?.license_key || '');
      const isLive = (c) =>
        c.payment ? paymentStatusOf(c.payment) === 'active' : db.PRO_STATUSES.has(c.subscription.status);

      // Prefer the purchase that actually carries the presented key.
      const exact = key ? candidates.find((c) => keyOf(c) === key) : null;
      const live = candidates.find(isLive);
      const chosen = exact || live || candidates[0];

      return {
        payment: chosen.payment,
        subscription: chosen.subscription,
        licenseKey: keyOf(chosen) || null,
        customer: chosen.customer,
      };
    } catch (err) {
      log(`recover by email failed: ${err.message}`);
    }
  }

  return null;
}

/**
 * Write a recovered purchase back into the local cache, minting a licence key
 * if the purchase never carried one.
 */
async function rehydrate(found, fallbackEmail, preferredKey = '') {
  const { payment, subscription } = found;
  const target = payment || subscription;
  let { licenseKey } = found;

  // If the purchase carries no key but the caller presented a well-formed one,
  // adopt theirs. Minting a fresh key here would silently orphan the key the
  // customer already has written down. This grants nothing extra: whoever
  // supplied the email could already activate with it alone.
  if (!licenseKey && preferredKey && licensekey.isWellFormed(preferredKey)) {
    licenseKey = licensekey.normalize(preferredKey);
  }

  if (!licenseKey) {
    licenseKey = licensekey.generate();
    await stampLicenseKey({ payment, subscription }, licenseKey);
  }

  let email =
    found.customer?.email ||
    (typeof target.customer === 'object' ? target.customer?.email : null) ||
    fallbackEmail ||
    null;

  // Recovery by licence key returns `customer` as a bare id, so the address is
  // missing. Fetch it: without an email on the row the customer cannot
  // activate by email and no licence email can ever be sent to them — a silent
  // loss that only shows up after a redeploy wipes the cache.
  if (!email && typeof target.customer === 'string') {
    try {
      const customer = await stripe.customers.retrieve(target.customer);
      if (!customer.deleted) email = customer.email || null;
    } catch (err) {
      log(`could not resolve customer ${target.customer}: ${err.message}`);
    }
  }

  if (!db.findByKey(licenseKey)) db.createPending(licenseKey, email, null);

  const status = payment ? paymentStatusOf(payment) : subscription.status;
  const row = db.activate(licenseKey, {
    status,
    email,
    customerId: typeof target.customer === 'object' ? target.customer?.id : target.customer,
    subscriptionId: subscription ? subscription.id : null,
    paymentIntentId: payment ? payment.id : null,
    currentPeriodEnd: subscription ? periodEndOf(subscription) : null,
  });

  log(`rehydrated ${licenseKey} from Stripe (${status})`);
  return row;
}

/**
 * Stamp the licence key onto the Stripe record so it can be recovered if this
 * database is ever lost. Payment Link purchases arrive without one. Never
 * throws: a failed stamp costs recoverability, not the purchase.
 */
async function stampLicenseKey({ payment, subscription }, licenseKey) {
  try {
    if (payment && payment.metadata?.license_key !== licenseKey) {
      await stripe.paymentIntents.update(payment.id, {
        metadata: { ...(payment.metadata || {}), license_key: licenseKey, app: APP_NAME },
      });
    } else if (subscription && subscription.metadata?.license_key !== licenseKey) {
      await stripe.subscriptions.update(subscription.id, {
        metadata: { ...(subscription.metadata || {}), license_key: licenseKey, app: APP_NAME },
      });
    }
  } catch (err) {
    log(`could not stamp licence key onto ${(payment || subscription).id}: ${err.message}`);
  }
}

/**
 * A one-time purchase's licence status.
 *
 * 'refunded' once the charge is fully refunded (a partial refund keeps the
 * licence), 'active' once paid, otherwise 'pending'. Needs latest_charge
 * expanded to see refunds; without it a paid purchase reads as active.
 */
function paymentStatusOf(payment) {
  if (!payment) return 'pending';
  const charge = payment.latest_charge && typeof payment.latest_charge === 'object'
    ? payment.latest_charge
    : null;
  if (charge && charge.refunded) return 'refunded';
  return payment.status === 'succeeded' ? 'active' : 'pending';
}

/**
 * Email a licence key to its owner, at most once.
 *
 * Called from both the webhook and the success-page lookup because either may
 * be the first to activate a licence — and Stripe retries webhooks. The claim
 * in the database decides who actually sends.
 *
 * Never throws: the purchase has already succeeded by this point, and a mail
 * failure must not turn a completed payment into a 500 that Stripe retries.
 */
async function deliverLicenseEmail(row, { force = false } = {}) {
  if (!row || !row.email || !db.isPro(row)) return { ok: false, skipped: true };

  if (!mail.isConfigured) {
    log(`email not configured; ${row.license_key} not sent to ${row.email}`);
    return { ok: false, skipped: true, error: 'email_not_configured' };
  }

  if (force) db.releaseEmailSend(row.license_key);
  if (!db.claimEmailSend(row.license_key)) {
    return { ok: false, skipped: true, error: 'already_sent' };
  }

  const result = await mail.sendLicenseEmail({
    to: row.email,
    licenseKey: row.license_key,
    status: row.status,
  });

  if (result.ok) {
    log(`emailed ${row.license_key} to ${row.email} via ${mail.providerName}`);
  } else {
    // Release the claim so it can be retried rather than silently lost.
    db.releaseEmailSend(row.license_key);
    log(`email failed for ${row.license_key}: ${result.error}`);
  }
  return result;
}

/** Pull a period end off a subscription across API-version shapes. */
function periodEndOf(subscription) {
  if (!subscription) return null;
  if (subscription.current_period_end) return subscription.current_period_end;
  const item = subscription.items && subscription.items.data && subscription.items.data[0];
  return (item && item.current_period_end) || null;
}

function publicView(row, extra = {}) {
  if (!row) return { valid: false, isPro: false, ...extra };
  return {
    valid: true,
    isPro: db.isPro(row),
    licenseKey: row.license_key,
    email: row.email || '',
    status: row.status,
    currentPeriodEnd: row.current_period_end || null,
    plan: db.isPro(row) ? 'pro' : 'free',
    purchase: row.stripe_subscription_id ? 'subscription' : 'one_time',
    ...extra,
  };
}

/** Why a known licence doesn't unlock the app, e.g. license_refunded. */
function inactiveReason(row) {
  return row.stripe_subscription_id ? `subscription_${row.status}` : `license_${row.status}`;
}

/**
 * Resolve a checkout session into an activated license.
 *
 * Webhooks cannot reach http://localhost without `stripe listen`, so this path
 * also acts as a self-healing fallback: it asks Stripe directly for the
 * session's true state and activates from that. The webhook and this function
 * converge on the same row, and both are idempotent.
 */
async function syncFromSession(sessionId) {
  const session = await stripe.checkout.sessions.retrieve(sessionId, {
    expand: ['subscription', 'customer', 'payment_intent.latest_charge'],
  });

  let licenseKey = licensekey.normalize(session.client_reference_id || '');

  if (!licenseKey) {
    /*
     * A Payment Link purchase has no client_reference_id — nobody called
     * /create-checkout, so no key was reserved up front. That is the published
     * site's main path (GitHub Pages can't run this server), so refusing here
     * would leave real paying customers with nothing.
     *
     * Mint a key now instead, keyed to the session id so that repeat calls,
     * a webhook and a page refresh all converge on the same one.
     */
    const existing = db.findBySession(sessionId);
    if (existing) {
      licenseKey = existing.license_key;
    } else {
      licenseKey = licensekey.generate();
      db.createPending(licenseKey, session.customer_details?.email || null, sessionId);
      log(`minted ${licenseKey} for payment-link session ${sessionId}`);
    }
  }

  let row = db.findByKey(licenseKey);
  if (!row) {
    // Session exists at Stripe but the local row is gone (fresh DB, etc.).
    row = db.createPending(licenseKey, session.customer_details?.email || null, sessionId);
  }
  if (!row.stripe_session_id) db.attachSession(licenseKey, sessionId);

  const paid = session.status === 'complete' || session.payment_status === 'paid';
  if (!paid) {
    return { row: db.findByKey(licenseKey), session, pending: true };
  }

  const subscription =
    session.subscription && typeof session.subscription === 'object' ? session.subscription : null;
  const payment =
    session.payment_intent && typeof session.payment_intent === 'object' ? session.payment_intent : null;

  const updated = db.activate(licenseKey, {
    status: subscription ? subscription.status : payment ? paymentStatusOf(payment) : 'active',
    email: session.customer_details?.email || session.customer_email || row.email,
    customerId: typeof session.customer === 'object' ? session.customer?.id : session.customer,
    subscriptionId: subscription ? subscription.id : null,
    paymentIntentId: payment ? payment.id : null,
    currentPeriodEnd: periodEndOf(subscription),
  });

  // Stamp the key onto Stripe so it can be recovered if this database is ever
  // lost. Payment Link purchases arrive without one.
  await stampLicenseKey({ payment, subscription }, licenseKey);

  return { row: updated, session };
}

/* ------------------------------------------------------------------- routes */

app.get('/', (_req, res) => {
  res.json({
    service: `${APP_NAME} License Server`,
    version: '1.0.0',
    status: 'ok',
    stripe: { configured: keyReport.configured, mode: keyReport.secret_key_mode },
    endpoints: [
      'POST /create-checkout',
      'POST /validate',
      'POST /webhook',
      'GET  /get-license?session_id=',
      'POST /create-portal-session',
      'POST /resend-license',
      'POST /devices',
      'GET  /health',
    ],
  });
});

app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    uptimeSeconds: Math.round(process.uptime()),
    database: { driver: db.driver, path: db.DB_PATH, licenses: db.statusCounts() },
    stripe: {
      configured: keyReport.configured,
      mode: keyReport.secret_key_mode,
      missing: keyReport.missing,
      priceId: keys.price_id ? `${keys.price_id.slice(0, 10)}…` : null,
    },
    // Never the API key or credentials — only whether sending is possible and
    // which backend would handle it.
    email: { configured: mail.isConfigured, provider: mail.providerName, from: mail.FROM },
    // null until the first checkout; false means Stripe refused the terms box.
    termsConsent: { working: tosConsent.working, lastError: tosConsent.lastError },
  });
});

/**
 * Whether Stripe is accepting the terms-acceptance box, reported by /health so
 * a missing terms-of-service URL on the account is visible rather than silent.
 */
const tosConsent = { working: null, lastError: null };

/** A Stripe rejection that means "no terms-of-service URL on this account". */
function isTermsConfigError(err) {
  const message = String(err?.message || '').toLowerCase();
  return message.includes('terms_of_service') || message.includes('terms of service');
}

app.post('/create-checkout', async (req, res) => {
  if (!requireStripe(res)) return;

  const email = typeof req.body?.email === 'string' ? req.body.email.trim() : '';
  const licenseKeyValue = licensekey.generate();

  try {
    db.createPending(licenseKeyValue, email || null, null);

    // A one-time purchase: payment mode against a one-time price. The key goes
    // on the PaymentIntent so it can be recovered from Stripe, and a customer
    // is always created so the purchase can also be found by email.
    const params = {
      mode: 'payment',
      line_items: [{ price: keys.price_id, quantity: 1 }],
      client_reference_id: licenseKeyValue,
      ...(email ? { customer_email: email } : {}),
      customer_creation: 'always',
      allow_promotion_codes: true,
      success_url: `${WEBSITE_URL}/success.html?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${WEBSITE_URL}/index.html?checkout=cancelled`,
      payment_intent_data: { metadata: { license_key: licenseKeyValue, app: APP_NAME } },
      metadata: { license_key: licenseKeyValue, app: APP_NAME },
      // The buyer ticks a box agreeing to the terms, and Stripe stores that
      // with the payment. A liability limit nobody agreed to is worth little
      // (legal checklist 2.2). The box links to the terms-of-service URL set
      // on the Stripe account (Dashboard → Settings → Checkout), which points
      // at legal.html#terms — and that page spells out the "closes programs /
      // unsaved work" warning in full (also stated up front in the app's own
      // first-run terms gate), so no per-request custom_text is needed to
      // carry it.
      //
      // custom_text itself cannot be used at all once Managed Payments is on
      // (enabled by default on newer accounts, same as the tax-code
      // requirement tools/setup_stripe_store.js works around) — Stripe
      // rejects the whole session with a 400 if it is present. Managed
      // Payments stays on (consistent with that script) and custom_text is
      // simply dropped rather than disabled per-request.
      consent_collection: { terms_of_service: 'required' },
    };

    // Stripe only accepts the consent box once a terms-of-service URL is set on
    // the account (Dashboard → Settings → Checkout). Until it is, take the
    // payment rather than lose the sale, and say loudly what is missing.
    let session;
    try {
      session = await stripe.checkout.sessions.create(params);
      tosConsent.working = true;
    } catch (err) {
      if (!isTermsConfigError(err)) throw err;
      tosConsent.working = false;
      tosConsent.lastError = err.message;
      log(`create-checkout: terms consent unavailable (${err.message}); `
        + 'set a terms-of-service URL in the Stripe Dashboard → Settings → Checkout');
      const { consent_collection: _c, ...withoutConsent } = params;
      session = await stripe.checkout.sessions.create(withoutConsent);
    }

    db.attachSession(licenseKeyValue, session.id);
    log(`create-checkout -> ${licenseKeyValue} session=${session.id}`);

    res.json({ url: session.url, licenseKey: licenseKeyValue, sessionId: session.id });
  } catch (err) {
    log(`create-checkout FAILED: ${err.message}`);
    res.status(502).json({ error: 'stripe_error', message: err.message });
  }
});

app.get('/get-license', limiter.middleware('get-license'), async (req, res) => {
  const sessionId = String(req.query.session_id || '').trim();
  if (!sessionId) {
    return res.status(400).json({ error: 'missing_session_id', message: 'session_id is required.' });
  }

  // Trust the local row first when it is already active (webhook got there).
  const local = db.findBySession(sessionId);
  if (local && db.isPro(local)) {
    return res.json(publicView(local, { source: 'database' }));
  }

  if (!requireStripe(res)) return;

  try {
    const result = await syncFromSession(sessionId);
    if (result.error) {
      return res.status(422).json({ error: result.error, message: 'Session has no license reference.' });
    }
    if (result.pending) {
      return res.status(202).json({
        ...publicView(result.row, { source: 'stripe' }),
        pending: true,
        message: 'Checkout has not completed payment yet.',
      });
    }
    log(`get-license -> ${result.row.license_key} status=${result.row.status}`);

    // The buyer is looking at the key right now, so this is a convenience copy
    // rather than the delivery mechanism. Don't make them wait for the SMTP
    // round-trip; the claim guard stops the webhook duplicating it.
    const emailed = await deliverLicenseEmail(result.row);

    return res.json(
      publicView(result.row, {
        source: 'stripe',
        emailSent: emailed.ok === true,
        emailConfigured: mail.isConfigured,
      }),
    );
  } catch (err) {
    log(`get-license FAILED: ${err.message}`);
    const status = err.statusCode === 404 ? 404 : 502;
    return res.status(status).json({ error: 'stripe_error', message: err.message });
  }
});

app.post('/validate', limiter.middleware('validate'), async (req, res) => {
  const rawKey = req.body?.licenseKey ?? req.body?.license_key ?? '';
  const email = typeof req.body?.email === 'string' ? req.body.email.trim() : '';
  const key = licensekey.normalize(rawKey);

  // A salted hash computed by the app; no hardware id or user name is sent.
  const deviceId = typeof req.body?.deviceId === 'string' ? req.body.deviceId.trim().slice(0, 128) : '';
  const deviceName =
    typeof req.body?.deviceName === 'string' ? req.body.deviceName.trim().slice(0, 64) : '';

  if (!key && !email) {
    return res.status(400).json({
      valid: false,
      isPro: false,
      error: 'missing_credentials',
      message: 'Provide a license key or the email used at checkout.',
    });
  }

  // Reject malformed keys offline — no Stripe call, no DB hit.
  if (key && !licensekey.isWellFormed(key)) {
    return res.status(200).json({
      valid: false,
      isPro: false,
      reason: 'malformed_key',
      message: 'That license key is not in the expected FS-XXXX-XXXX-XXXX-XXXX format.',
    });
  }

  /*
   * Resolution order matters, most specific first.
   *
   * A licence key identifies one subscription; an email address may identify
   * several — the same person can buy twice, and every Payment Link purchase
   * creates a fresh Stripe customer. Falling back to the email before
   * exhausting the key meant a customer presenting key K, whose cached row had
   * been lost, was handed a *different* subscription's key.
   *
   * Each step also asks Stripe, because the database is only a cache and may
   * have been wiped by a redeploy.
   */
  const recover = async (criteria) => {
    const found = await recoverFromStripe(criteria);
    if (!found) return null;
    try {
      return await rehydrate(found, email, key);
    } catch (err) {
      log(`rehydrate failed: ${err.message}`);
      return null;
    }
  };

  let row = key ? db.findByKey(key) : null;
  if (!row && key) row = await recover({ key });
  if (!row && email) row = db.findByEmail(email);
  if (!row && email) row = await recover({ key, email });

  if (!row) {
    return res.json({
      valid: false,
      isPro: false,
      reason: 'not_found',
      message: 'No purchase found for those details.',
    });
  }

  // Re-confirm against Stripe so refunds and cancellations propagate even if
  // the webhook was missed. A Stripe outage must not revoke a known-good
  // license, so any error here leaves the cached status untouched.
  if (stripe && row.stripe_payment_intent_id) {
    try {
      const payment = await stripe.paymentIntents.retrieve(row.stripe_payment_intent_id, {
        expand: ['latest_charge'],
      });
      const status = paymentStatusOf(payment);
      if (status !== row.status) {
        log(`validate: ${row.license_key} status ${row.status} -> ${status}`);
        row = db.setStatus(row.license_key, status);
      }
    } catch (err) {
      log(`validate: Stripe re-check failed (serving cached status): ${err.message}`);
    }
  } else if (stripe && row.stripe_subscription_id) {
    try {
      const sub = await stripe.subscriptions.retrieve(row.stripe_subscription_id);
      if (sub.status !== row.status) {
        log(`validate: ${row.license_key} status ${row.status} -> ${sub.status}`);
        row = db.setStatus(row.license_key, sub.status);
      }
      db.setPeriodEnd(row.license_key, periodEndOf(sub));
      row = db.findByKey(row.license_key);
    } catch (err) {
      log(`validate: Stripe re-check failed (serving cached status): ${err.message}`);
    }
  }

  db.countActivation(row.license_key);
  const view = publicView(row);

  // Only a caller who already holds this licence key learns it (and the address
  // behind it). An email alone still answers "is this Pro?" — email activation
  // is roadmap item 5.5 — but must never be a way to obtain someone's key.
  if (key !== row.license_key) {
    delete view.licenseKey;
    delete view.email;
  }
  log(`validate -> ${row.license_key} isPro=${view.isPro} status=${row.status}`);

  if (!view.isPro) {
    return res.json({ ...view, valid: false, reason: inactiveReason(row) });
  }

  /*
   * Seat limit.
   *
   * Only applied once the purchase itself is known good, so a device
   * problem can never be confused with a payment problem. A request without a
   * device id still validates — the suite and curl have no machine identity —
   * but claims no seat, so it cannot be used to exhaust someone's allowance.
   *
   * This stops casual sharing, which is what actually costs revenue. It is not
   * DRM: anyone willing to send a fabricated device id per machine defeats it,
   * and hardening past this point punishes honest customers first.
   */
  if (deviceId && DEVICE_LIMIT > 0) {
    const seat = db.registerDevice(row.license_key, deviceId, deviceName, DEVICE_LIMIT);

    if (!seat.allowed) {
      log(`validate -> ${row.license_key} refused: ${seat.count}/${seat.limit} devices`);
      return res.json({
        ...view,
        valid: false,
        isPro: false,
        reason: 'device_limit_reached',
        deviceCount: seat.count,
        deviceLimit: seat.limit,
        message:
          `This licence is already active on ${seat.count} devices, the maximum per ` +
          `licence. Deactivate FlowShield on a machine you no longer use, then try again.`,
      });
    }

    return res.json({
      ...view,
      deviceCount: seat.count,
      deviceLimit: seat.limit,
      newDevice: seat.reason === 'registered',
    });
  }

  return res.json({ ...view, deviceLimit: DEVICE_LIMIT });
});

/**
 * Re-send a licence key to the address that bought it.
 *
 * Always answers the same way whether or not the address has a purchase:
 * a different response would turn this into an oracle for checking who is a
 * customer. The email only ever goes to the address on the subscription, so
 * asking for someone else's key tells you nothing and sends you nothing.
 */
app.post('/resend-license', limiter.middleware('resend-license'), async (req, res) => {
  const email = typeof req.body?.email === 'string' ? req.body.email.trim() : '';
  const sessionId = typeof req.body?.sessionId === 'string' ? req.body.sessionId.trim() : '';
  const generic = {
    ok: true,
    message: 'If that address bought FlowShield, the licence key is on its way.',
  };

  if (!email) {
    return res.status(400).json({ error: 'missing_email', message: 'An email address is required.' });
  }
  if (!mail.isConfigured) {
    return res.status(503).json({
      error: 'email_not_configured',
      message: 'This server has no email provider configured.',
    });
  }

  let row = db.findByEmail(email);

  if (!row && sessionId) {
    const bySession = db.findBySession(sessionId);
    if (bySession && bySession.email === email) {
      row = bySession;
    }
  }

  if (!row && stripe) {
    const found = await recoverFromStripe({ email });
    if (found) {
      try {
        row = await rehydrate(found, email);
      } catch (err) {
        log(`resend rehydrate failed: ${err.message}`);
      }
    }
  }

  if (row && db.isPro(row)) {
    await deliverLicenseEmail(row, { force: true });
  } else {
    log(`resend requested for ${email} with no active licence`);
  }

  return res.json(generic);
});

/**
 * Release a device's seat, or list the seats in use.
 *
 * A cap without a way to release seats is a trap: replace your laptop three
 * times and you are locked out of software you are still paying for. The app
 * calls this when you deactivate, and it is also reachable by support.
 *
 * Requires the licence key. An email address used to be accepted too, which let
 * anyone who knew a customer's address read their key and device names and
 * release their seats (#21). The app always sends the key it holds.
 */
app.post('/devices', limiter.middleware('devices'), async (req, res) => {
  const key = licensekey.normalize(req.body?.licenseKey ?? req.body?.license_key ?? '');
  const action = String(req.body?.action || 'list').toLowerCase();
  const deviceId = typeof req.body?.deviceId === 'string' ? req.body.deviceId.trim() : '';

  if (!key) {
    return res.status(400).json({
      error: 'missing_license_key',
      message: 'A licence key is required to list or release devices.',
    });
  }

  let row = licensekey.isWellFormed(key) ? db.findByKey(key) : null;

  // Recover from Stripe like /validate does. Without this, deactivating just
  // after a redeploy has wiped the cache answers 404 and the seat is never
  // released — costing the customer a slot permanently, on the one path whose
  // whole job is giving slots back.
  if (!row && licensekey.isWellFormed(key)) {
    const found = await recoverFromStripe({ key });
    if (found) {
      try {
        row = await rehydrate(found, '', key);
      } catch (err) {
        log(`devices rehydrate failed: ${err.message}`);
      }
    }
  }

  if (!row) {
    return res.status(404).json({ error: 'not_found', message: 'No licence found for those details.' });
  }

  if (action === 'release') {
    if (!deviceId) {
      return res.status(400).json({ error: 'missing_device', message: 'deviceId is required.' });
    }
    const removed = db.removeDevice(row.license_key, deviceId);
    log(`device ${removed ? 'released' : 'not found'} for ${row.license_key}`);
  } else if (action === 'release-all') {
    db.removeAllDevices(row.license_key);
    log(`all devices released for ${row.license_key}`);
  }

  // Names only, never the raw ids — those are the client's to hold.
  const devices = db.listDevices(row.license_key).map((d) => ({
    name: d.device_name || 'Unnamed device',
    firstSeen: d.first_seen,
    lastSeen: d.last_seen,
    isCurrent: !!deviceId && d.device_id === deviceId,
  }));

  res.json({
    ok: true,
    licenseKey: row.license_key,
    deviceCount: devices.length,
    deviceLimit: DEVICE_LIMIT,
    devices,
  });
});

/**
 * Open the Stripe billing portal, where a customer can cancel, change plan or
 * update their card. Requires the licence key: an email address alone used to
 * be enough, which let anyone who knew it cancel someone else's subscription
 * (#21). Checked before Stripe so the refusal doesn't depend on configuration.
 */
app.post('/create-portal-session', limiter.middleware('create-portal-session'), async (req, res) => {
  const key = licensekey.normalize(req.body?.licenseKey ?? req.body?.license_key ?? '');
  if (!key) {
    return res.status(400).json({
      error: 'missing_license_key',
      message: 'A licence key is required to manage a subscription.',
    });
  }

  if (!requireStripe(res)) return;

  const row = licensekey.isWellFormed(key) ? db.findByKey(key) : null;

  if (!row || !row.stripe_customer_id) {
    return res.status(404).json({
      error: 'no_customer',
      message: 'No Stripe customer is linked to that license yet.',
    });
  }

  try {
    const session = await stripe.billingPortal.sessions.create({
      customer: row.stripe_customer_id,
      return_url: `${WEBSITE_URL}/index.html`,
    });
    res.json({ url: session.url });
  } catch (err) {
    log(`create-portal-session FAILED: ${err.message}`);
    res.status(502).json({ error: 'stripe_error', message: err.message });
  }
});

app.post('/webhook', async (req, res) => {
  if (!stripe) {
    return res.status(503).json({ error: 'stripe_not_configured' });
  }

  const signature = req.headers['stripe-signature'];
  let event;

  try {
    if (!keys.webhook_secret) throw new Error('webhook secret not configured');
    event = stripe.webhooks.constructEvent(req.body, signature, keys.webhook_secret);
  } catch (err) {
    log(`webhook signature rejected: ${err.message}`);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  if (!db.claimEvent(event.id, event.type)) {
    log(`webhook ${event.type} ${event.id} already processed`);
    return res.json({ received: true, duplicate: true });
  }

  try {
    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object;
        const result = await syncFromSession(session.id);
        log(`webhook checkout.session.completed ${session.id}`);

        // The reliable delivery path: this fires even when the buyer closes
        // the tab before the success page loads.
        if (result?.row) await deliverLicenseEmail(result.row);
        break;
      }

      // A refund revokes a one-time licence. Only a full refund: Stripe sets
      // charge.refunded once the whole amount has been returned.
      case 'charge.refunded': {
        const charge = event.data.object;
        const paymentId =
          typeof charge.payment_intent === 'string' ? charge.payment_intent : charge.payment_intent?.id;
        const row = paymentId ? db.findByPaymentIntent(paymentId) : null;
        if (row && charge.refunded) {
          db.setStatus(row.license_key, 'refunded');
          log(`webhook charge.refunded ${row.license_key} -> refunded`);
        }
        break;
      }

      // The two subscription events below only concern licences bought on
      // the old monthly plan.
      case 'customer.subscription.updated': {
        const sub = event.data.object;
        const row =
          db.findBySubscription(sub.id) ||
          (sub.metadata?.license_key ? db.findByKey(licensekey.normalize(sub.metadata.license_key)) : null);
        if (row) {
          db.setStatus(row.license_key, sub.status);
          db.setPeriodEnd(row.license_key, periodEndOf(sub));
          log(`webhook subscription.updated ${row.license_key} -> ${sub.status}`);
        }
        break;
      }

      case 'customer.subscription.deleted': {
        const sub = event.data.object;
        const row =
          db.findBySubscription(sub.id) ||
          (sub.metadata?.license_key ? db.findByKey(licensekey.normalize(sub.metadata.license_key)) : null);
        if (row) {
          db.setStatus(row.license_key, 'canceled');
          log(`webhook subscription.deleted ${row.license_key} -> canceled`);
        }
        break;
      }

      default:
        log(`webhook ignored event type ${event.type}`);
    }
  } catch (err) {
    log(`webhook handler error for ${event.type}: ${err.message}`);
    // 500 asks Stripe to retry; the event id guard makes that safe.
    return res.status(500).json({ error: 'handler_failed', message: err.message });
  }

  res.json({ received: true });
});

app.use((_req, res) => res.status(404).json({ error: 'not_found' }));

/* -------------------------------------------------------------------- boot */

const server = app.listen(PORT, () => {
  log(`${APP_NAME} license server listening on http://localhost:${PORT}`);
  log(`database: ${db.driver} @ ${db.DB_PATH}`);
  if (keyReport.configured) {
    log(`Stripe: ${keyReport.secret_key_mode} mode, price ${keys.price_id}`);
  } else {
    log(`Stripe NOT configured — missing: ${keyReport.missing.join(', ')}`);
    log(`Populate ${KEYS_PATH} and restart to enable payment routes.`);
  }
});

for (const sig of ['SIGINT', 'SIGTERM']) {
  process.on(sig, () => {
    log(`${sig} received, shutting down`);
    server.close(() => process.exit(0));
  });
}

module.exports = app;
