'use strict';

/**
 * FlowShield license + subscription server.
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

const PORT = Number(process.env.PORT || 3000);
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
 * Two routes in: the licence key stamped into subscription metadata, and the
 * customer's email address.
 */
async function recoverFromStripe({ key, email }) {
  if (!stripe) return null;

  // 1. By licence key, which create-checkout and the minting path both stamp
  //    into subscription metadata.
  if (key) {
    try {
      const found = await stripe.subscriptions.search({
        query: `metadata['license_key']:'${key.replace(/'/g, '')}'`,
        limit: 1,
      });
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

      // Gather every subscription across every customer with this address
      // before choosing. One person can hold several — the same address can
      // buy twice, and Stripe creates a separate customer each time a Payment
      // Link is used. Returning whichever happened to be listed first made
      // recovery non-deterministic and could hand back a licence key the
      // customer has never seen.
      const candidates = [];
      for (const customer of customers.data) {
        const subs = await stripe.subscriptions.list({
          customer: customer.id,
          status: 'all',
          limit: 10,
        });
        for (const subscription of subs.data) candidates.push({ subscription, customer });
      }

      if (candidates.length === 0) return null;

      const keyOf = (c) => licensekey.normalize(c.subscription.metadata?.license_key || '');

      // Prefer the subscription that actually carries the presented key.
      const exact = key ? candidates.find((c) => keyOf(c) === key) : null;
      const live = candidates.find((c) => db.PRO_STATUSES.has(c.subscription.status));
      const chosen = exact || live || candidates[0];

      return {
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
 * Write a recovered subscription back into the local cache, minting a licence
 * key if the subscription never carried one.
 */
async function rehydrate(found, fallbackEmail, preferredKey = '') {
  let { subscription, licenseKey } = found;

  // If the subscription carries no key but the caller presented a well-formed
  // one, adopt theirs. Minting a fresh key here would silently orphan the key
  // the customer already has written down. This grants nothing extra: whoever
  // supplied the email could already activate with it alone.
  if (!licenseKey && preferredKey && licensekey.isWellFormed(preferredKey)) {
    licenseKey = licensekey.normalize(preferredKey);
  }

  if (!licenseKey) {
    licenseKey = licensekey.generate();
    try {
      await stripe.subscriptions.update(subscription.id, {
        metadata: { ...(subscription.metadata || {}), license_key: licenseKey, app: APP_NAME },
      });
    } catch (err) {
      log(`could not stamp licence key onto ${subscription.id}: ${err.message}`);
    }
  }

  let email =
    found.customer?.email ||
    (typeof subscription.customer === 'object' ? subscription.customer?.email : null) ||
    fallbackEmail ||
    null;

  // Recovery by licence key returns the subscription with `customer` as a bare
  // id, so the address is missing. Fetch it: without an email on the row the
  // customer cannot activate by email and no licence email can ever be sent to
  // them — a silent loss that only shows up after a redeploy wipes the cache.
  if (!email && typeof subscription.customer === 'string') {
    try {
      const customer = await stripe.customers.retrieve(subscription.customer);
      if (!customer.deleted) email = customer.email || null;
    } catch (err) {
      log(`could not resolve customer ${subscription.customer}: ${err.message}`);
    }
  }

  if (!db.findByKey(licenseKey)) db.createPending(licenseKey, email, null);

  const row = db.activate(licenseKey, {
    status: subscription.status,
    email,
    customerId:
      typeof subscription.customer === 'object' ? subscription.customer?.id : subscription.customer,
    subscriptionId: subscription.id,
    currentPeriodEnd: periodEndOf(subscription),
  });

  log(`rehydrated ${licenseKey} from Stripe (${subscription.status})`);
  return row;
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
    ...extra,
  };
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
    expand: ['subscription', 'customer'],
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

  const updated = db.activate(licenseKey, {
    status: subscription ? subscription.status : 'active',
    email: session.customer_details?.email || session.customer_email || row.email,
    customerId: typeof session.customer === 'object' ? session.customer?.id : session.customer,
    subscriptionId: subscription ? subscription.id : null,
    currentPeriodEnd: periodEndOf(subscription),
  });

  // Stamp the key onto the subscription so it can be recovered from Stripe if
  // this database is ever lost. Payment Link purchases arrive without one.
  if (subscription && subscription.metadata?.license_key !== licenseKey) {
    try {
      await stripe.subscriptions.update(subscription.id, {
        metadata: { ...(subscription.metadata || {}), license_key: licenseKey, app: APP_NAME },
      });
    } catch (err) {
      log(`could not stamp licence key onto ${subscription.id}: ${err.message}`);
    }
  }

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
  });
});

app.post('/create-checkout', async (req, res) => {
  if (!requireStripe(res)) return;

  const email = typeof req.body?.email === 'string' ? req.body.email.trim() : '';
  const licenseKeyValue = licensekey.generate();

  try {
    db.createPending(licenseKeyValue, email || null, null);

    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      line_items: [{ price: keys.price_id, quantity: 1 }],
      client_reference_id: licenseKeyValue,
      ...(email ? { customer_email: email } : {}),
      allow_promotion_codes: true,
      success_url: `${WEBSITE_URL}/success.html?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${WEBSITE_URL}/index.html?checkout=cancelled`,
      subscription_data: { metadata: { license_key: licenseKeyValue, app: APP_NAME } },
      metadata: { license_key: licenseKeyValue, app: APP_NAME },
    });

    db.attachSession(licenseKeyValue, session.id);
    log(`create-checkout -> ${licenseKeyValue} session=${session.id}`);

    res.json({ url: session.url, licenseKey: licenseKeyValue, sessionId: session.id });
  } catch (err) {
    log(`create-checkout FAILED: ${err.message}`);
    res.status(502).json({ error: 'stripe_error', message: err.message });
  }
});

app.get('/get-license', async (req, res) => {
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

app.post('/validate', async (req, res) => {
  const rawKey = req.body?.licenseKey ?? req.body?.license_key ?? '';
  const email = typeof req.body?.email === 'string' ? req.body.email.trim() : '';
  const key = licensekey.normalize(rawKey);

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
      message: 'No subscription found for those details.',
    });
  }

  // Re-confirm against Stripe so cancellations propagate even if the webhook
  // was missed. A Stripe outage must not revoke a known-good license, so any
  // error here leaves the cached status untouched.
  if (stripe && row.stripe_subscription_id) {
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
  log(`validate -> ${row.license_key} isPro=${view.isPro} status=${row.status}`);

  if (!view.isPro) {
    return res.json({ ...view, valid: false, reason: `subscription_${row.status}` });
  }
  return res.json(view);
});

/**
 * Re-send a licence key to the address that bought it.
 *
 * Always answers the same way whether or not the address has a subscription:
 * a different response would turn this into an oracle for checking who is a
 * customer. The email only ever goes to the address on the subscription, so
 * asking for someone else's key tells you nothing and sends you nothing.
 */
app.post('/resend-license', async (req, res) => {
  const email = typeof req.body?.email === 'string' ? req.body.email.trim() : '';
  const generic = {
    ok: true,
    message: 'If that address has a subscription, the licence key is on its way.',
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
    log(`resend requested for ${email} with no active subscription`);
  }

  return res.json(generic);
});

app.post('/create-portal-session', async (req, res) => {
  if (!requireStripe(res)) return;

  const key = licensekey.normalize(req.body?.licenseKey ?? req.body?.license_key ?? '');
  const email = typeof req.body?.email === 'string' ? req.body.email.trim() : '';
  const row = key ? db.findByKey(key) : email ? db.findByEmail(email) : null;

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
