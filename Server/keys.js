'use strict';

/**
 * Stripe credential loading.
 *
 * Resolution order (first hit wins per-field):
 *   1. Environment variables  (STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY,
 *                              STRIPE_PRICE_ID, STRIPE_WEBHOOK_SECRET)
 *   2. ../.stripe_keys.json
 *
 * The server deliberately starts even when keys are absent: every payment
 * route then answers 503 with an actionable message instead of the process
 * dying at boot. That keeps the non-payment surface testable.
 */

const fs = require('fs');
const path = require('path');

const KEYS_PATH = path.join(__dirname, '..', '.stripe_keys.json');

const FIELDS = {
  publishable_key: 'STRIPE_PUBLISHABLE_KEY',
  secret_key: 'STRIPE_SECRET_KEY',
  price_id: 'STRIPE_PRICE_ID',
  webhook_secret: 'STRIPE_WEBHOOK_SECRET',
};

// Values shipped in the template file that must not be treated as real.
const PLACEHOLDER = /^(|REPLACE_ME.*|pk_test_\.\.\.|sk_test_\.\.\.|price_\.\.\.|whsec_\.\.\.)$/;

function loadKeys() {
  let fileKeys = {};
  if (fs.existsSync(KEYS_PATH)) {
    try {
      fileKeys = JSON.parse(fs.readFileSync(KEYS_PATH, 'utf8'));
    } catch (err) {
      console.error(`[keys] ${KEYS_PATH} is not valid JSON: ${err.message}`);
    }
  }

  const out = {};
  for (const [field, envVar] of Object.entries(FIELDS)) {
    const raw = process.env[envVar] || fileKeys[field] || '';
    out[field] = PLACEHOLDER.test(String(raw).trim()) ? '' : String(raw).trim();
  }
  return out;
}

function describe(keys) {
  const missing = Object.keys(FIELDS).filter((f) => !keys[f]);
  return {
    configured: missing.length === 0,
    missing,
    // Never log or return a secret. Only shape confirmation.
    secret_key_mode: keys.secret_key.startsWith('sk_live_')
      ? 'live'
      : keys.secret_key.startsWith('sk_test_')
        ? 'test'
        : 'unset',
  };
}

module.exports = { loadKeys, describe, KEYS_PATH };
