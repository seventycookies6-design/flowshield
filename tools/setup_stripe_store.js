#!/usr/bin/env node
'use strict';

/**
 * Set up the FlowShield store in Stripe and wire it to the website.
 *
 *   node tools/setup_stripe_store.js --site https://user.github.io/flowshield
 *
 * Creates (or reuses) the product, the $4.99/month price, and a Payment Link
 * whose confirmation page is the published success page. Then writes the price
 * id into .stripe_keys.json and the Payment Link into Website/config.js.
 *
 * Idempotent: everything is tagged with metadata.flowshield and looked up
 * before being created, so re-running never produces duplicates.
 *
 * Reads the secret key from .stripe_keys.json or STRIPE_SECRET_KEY. The key is
 * never printed, logged, or written anywhere it isn't already.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const KEYS_PATH = path.join(ROOT, '.stripe_keys.json');
const CONFIG_PATH = path.join(ROOT, 'Website', 'config.js');

const PRODUCT_NAME = 'FlowShield Pro';
const UNIT_AMOUNT = 499; // cents
const CURRENCY = 'usd';
const TAG = 'flowshield';

/**
 * Stripe tax code — required because Managed Payments is enabled by default on
 * newer accounts, and it refuses line items whose product has no tax code.
 *
 * txcd_10202000 = "Downloadable Software - personal use", which is what
 * FlowShield is: a desktop app you download and run locally, sold to
 * individuals on a subscription. It is NOT SaaS — nothing executes on a server.
 *
 * This classification only affects tax calculation, and in test mode it affects
 * nothing at all. Before going live, confirm it with whoever does your taxes —
 * a business-use or SaaS code may fit better depending on who buys it.
 * Alternatives: txcd_10202003 (downloadable, business use),
 * txcd_10103000 (SaaS, personal use), txcd_10103001 (SaaS, business use).
 */
const TAX_CODE = process.env.FLOWSHIELD_TAX_CODE || 'txcd_10202000';

// ------------------------------------------------------------------- helpers

function parseArgs(argv) {
  const out = { site: '', webhook: '', dryRun: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--site') out.site = (argv[++i] || '').replace(/\/$/, '');
    else if (arg === '--webhook') out.webhook = argv[++i] || '';
    else if (arg === '--dry-run') out.dryRun = true;
  }
  return out;
}

function readKeys() {
  let file = {};
  if (fs.existsSync(KEYS_PATH)) {
    try {
      file = JSON.parse(fs.readFileSync(KEYS_PATH, 'utf8'));
    } catch (err) {
      fail(`${KEYS_PATH} is not valid JSON: ${err.message}`);
    }
  }
  const clean = (v) => {
    const s = String(v || '').trim();
    return /^REPLACE_ME/.test(s) || s.endsWith('...') ? '' : s;
  };
  return {
    publishable_key: process.env.STRIPE_PUBLISHABLE_KEY || clean(file.publishable_key),
    secret_key: process.env.STRIPE_SECRET_KEY || clean(file.secret_key),
    price_id: clean(file.price_id),
    webhook_secret: process.env.STRIPE_WEBHOOK_SECRET || clean(file.webhook_secret),
    _file: file,
  };
}

function writeKeys(existing, updates) {
  const merged = { ...existing._file, ...updates };
  fs.writeFileSync(KEYS_PATH, JSON.stringify(merged, null, 2) + '\n', 'utf8');
}

function fail(message) {
  console.error(`\n  ✗ ${message}\n`);
  process.exit(1);
}

const ok = (m) => console.log(`  ✓ ${m}`);
const info = (m) => console.log(`    ${m}`);

// ---------------------------------------------------------------- operations

/** Find a product we previously created, by metadata tag then by exact name. */
async function findProduct(stripe) {
  try {
    const tagged = await stripe.products.search({
      query: `active:'true' AND metadata['app']:'${TAG}'`,
      limit: 10,
    });
    if (tagged.data.length) return tagged.data[0];
  } catch (err) {
    // Search is not available on brand-new accounts for a few minutes; the
    // list fallback below handles that.
    info(`product search unavailable (${err.message.slice(0, 60)}); listing instead`);
  }

  const list = await stripe.products.list({ active: true, limit: 100 });
  return list.data.find((p) => p.name === PRODUCT_NAME) || null;
}

async function ensureProduct(stripe) {
  const existing = await findProduct(stripe);
  if (existing) {
    // A product created before the tax code was required would break every
    // checkout under Managed Payments, so backfill it rather than reuse as-is.
    if (!existing.tax_code) {
      const updated = await stripe.products.update(existing.id, { tax_code: TAX_CODE });
      ok(`product reused and tax code set to ${TAX_CODE}: ${updated.name} (${updated.id})`);
      return updated;
    }
    ok(`product reused: ${existing.name} (${existing.id})`);
    return existing;
  }

  const product = await stripe.products.create({
    name: PRODUCT_NAME,
    description:
      'Unlimited blocked apps, Shield III Sealed mode, sleep-blocking schedules, ' +
      'hard kill mode, and unlimited history with momentum analytics.',
    tax_code: TAX_CODE,
    metadata: { app: TAG },
  });
  ok(`product created: ${product.name} (${product.id})`);
  return product;
}

async function ensurePrice(stripe, product) {
  const prices = await stripe.prices.list({ product: product.id, active: true, limit: 100 });
  const match = prices.data.find(
    (p) =>
      p.unit_amount === UNIT_AMOUNT &&
      p.currency === CURRENCY &&
      p.recurring &&
      p.recurring.interval === 'month',
  );

  if (match) {
    ok(`price reused: ${(match.unit_amount / 100).toFixed(2)} ${match.currency.toUpperCase()}/month (${match.id})`);
    return match;
  }

  const price = await stripe.prices.create({
    product: product.id,
    unit_amount: UNIT_AMOUNT,
    currency: CURRENCY,
    recurring: { interval: 'month' },
    metadata: { app: TAG },
  });
  ok(`price created: $4.99/month (${price.id})`);
  return price;
}

async function ensurePaymentLink(stripe, price, siteUrl) {
  const links = await stripe.paymentLinks.list({ active: true, limit: 100 });
  const existing = links.data.find((l) => l.metadata && l.metadata.app === TAG);

  // A Payment Link's price cannot be edited after creation, and its redirect
  // can. Deactivate a stale one rather than leaving two live links around.
  if (existing) {
    const item = await stripe.paymentLinks.listLineItems(existing.id, { limit: 1 });
    const samePrice = item.data.length && item.data[0].price.id === price.id;

    if (samePrice) {
      if (siteUrl) {
        await stripe.paymentLinks.update(existing.id, {
          after_completion: {
            type: 'redirect',
            redirect: { url: `${siteUrl}/success.html?session_id={CHECKOUT_SESSION_ID}` },
          },
        });
        info('payment link redirect updated to the published success page');
      }
      ok(`payment link reused: ${existing.url}`);
      return existing;
    }

    await stripe.paymentLinks.update(existing.id, { active: false });
    info(`deactivated a payment link pointing at an old price (${existing.id})`);
  }

  const params = {
    line_items: [{ price: price.id, quantity: 1 }],
    metadata: { app: TAG },
    allow_promotion_codes: true,
    subscription_data: { metadata: { app: TAG } },
  };

  if (siteUrl) {
    params.after_completion = {
      type: 'redirect',
      redirect: { url: `${siteUrl}/success.html?session_id={CHECKOUT_SESSION_ID}` },
    };
  }

  const link = await stripe.paymentLinks.create(params);
  ok(`payment link created: ${link.url}`);
  return link;
}

async function ensureWebhook(stripe, webhookUrl) {
  if (!webhookUrl) return null;

  const endpoints = await stripe.webhookEndpoints.list({ limit: 100 });
  const existing = endpoints.data.find((e) => e.url === webhookUrl);
  if (existing) {
    ok(`webhook endpoint already registered: ${webhookUrl}`);
    info('Stripe only reveals a signing secret at creation — reuse the stored one.');
    return null;
  }

  const endpoint = await stripe.webhookEndpoints.create({
    url: webhookUrl,
    enabled_events: [
      'checkout.session.completed',
      'customer.subscription.updated',
      'customer.subscription.deleted',
    ],
    metadata: { app: TAG },
  });
  ok(`webhook endpoint created: ${webhookUrl}`);
  return endpoint.secret || null;
}

function writeSiteConfig({ paymentLink, licenseServerUrl, supportEmail }) {
  const contents = `/*
 * FlowShield site configuration.
 *
 * Only PUBLIC values belong in this file — it is committed and served to every
 * visitor. A Stripe Payment Link URL is public by design; secret keys never
 * appear here and live only in .stripe_keys.json, which is git-ignored.
 *
 * Generated by \`node tools/setup_stripe_store.js\` on ${new Date().toISOString()}.
 */
window.FLOWSHIELD_CONFIG = {
  /*
   * Stripe Payment Link — a Stripe-hosted checkout page that needs no backend.
   * This is what the published, static site uses: GitHub Pages cannot run the
   * license server, and a visitor's browser obviously cannot reach ours.
   */
  paymentLink: ${JSON.stringify(paymentLink || '')},

  /*
   * License server base URL. Empty on the public build.
   *
   * When set, the site prefers it over the Payment Link because that flow also
   * reserves a license key up front and can hand it straight back on the
   * success page. Override per-visit with ?server=http://host:port.
   */
  licenseServerUrl: ${JSON.stringify(licenseServerUrl || '')},

  /* Shown on the success page so buyers know where their key comes from. */
  supportEmail: ${JSON.stringify(supportEmail || '')},
};
`;
  fs.writeFileSync(CONFIG_PATH, contents, 'utf8');
  ok(`wrote ${path.relative(ROOT, CONFIG_PATH)}`);
}

// --------------------------------------------------------------------- main

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const keys = readKeys();

  console.log('\n  FlowShield — Stripe store setup\n');

  if (!keys.secret_key) {
    fail(
      `No Stripe secret key found.\n` +
        `    Put it in ${KEYS_PATH} as "secret_key", or set STRIPE_SECRET_KEY.\n` +
        `    See STRIPE_SETUP.md for where to copy it from.`,
    );
  }

  if (keys.secret_key.startsWith('sk_live_')) {
    fail(
      'That is a LIVE secret key. This script is for test mode.\n' +
        '    Switch the Stripe dashboard to Test mode and copy the sk_test_ key instead.',
    );
  }
  if (!keys.secret_key.startsWith('sk_test_')) {
    fail('The secret key does not look like a Stripe test key (expected sk_test_…).');
  }

  let Stripe;
  try {
    Stripe = require(path.join(ROOT, 'Server', 'node_modules', 'stripe'));
  } catch (err) {
    fail('The stripe package is missing. Run `npm install` inside Server/ first.');
  }

  // Managed Payments (on by default for newer accounts) rejects API versions
  // older than 2025-03-31.basil, so this must stay current with server.js.
  const stripe = Stripe(keys.secret_key, { apiVersion: '2026-08-26.dahlia' });

  let account;
  try {
    account = await stripe.accounts.retrieve();
  } catch (err) {
    fail(`Stripe rejected the key: ${err.message}`);
  }
  ok(`connected to Stripe account ${account.id}${account.settings?.dashboard?.display_name ? ` (${account.settings.dashboard.display_name})` : ''} — TEST mode`);

  if (args.dryRun) {
    info('--dry-run: stopping before any changes are made');
    return;
  }

  const product = await ensureProduct(stripe);
  const price = await ensurePrice(stripe, product);
  const link = await ensurePaymentLink(stripe, price, args.site);

  const webhookSecret = await ensureWebhook(stripe, args.webhook);

  const updates = { price_id: price.id };
  if (webhookSecret) updates.webhook_secret = webhookSecret;
  writeKeys(keys, updates);
  ok(`price id saved to ${path.basename(KEYS_PATH)}`);

  writeSiteConfig({
    paymentLink: link.url,
    licenseServerUrl: '', // public build has no backend
    supportEmail: process.env.FLOWSHIELD_SUPPORT_EMAIL || '',
  });

  console.log('\n  Store is set up.\n');
  console.log(`    product      ${product.id}`);
  console.log(`    price        ${price.id}  ($4.99/month)`);
  console.log(`    payment link ${link.url}`);
  if (args.site) console.log(`    success page ${args.site}/success.html`);
  console.log('\n  Test card 4242 4242 4242 4242 · 12/34 · 123 · 90210\n');
}

main().catch((err) => {
  fail(err && err.message ? err.message : String(err));
});
