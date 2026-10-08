'use strict';

const crypto = require('crypto');

/**
 * Roadmap 5.7 ("see and manage your devices").
 *
 * A per-device token the app can send back to /devices to release a
 * *different* device's seat, without the list route ever handing back the
 * raw hashed device id it stores (see server.js's /devices handler: "Names
 * only, never the raw ids"). Deterministic per (licence key, device id) pair
 * — the same row gets the same token on every list — and one-way.
 *
 * Keyed with a server secret (HMAC-SHA256, #234). A plain hash of the licence
 * key and device id let anyone who ever saw a raw device id (support tooling,
 * a future log line) plus the key mint a valid token without the server.
 * With the secret, only the server can.
 *
 * The secret comes from DEVICE_TOKEN_SECRET. In production a missing or short
 * secret fails closed: list rows carry no token and releasing by token is
 * refused, while everything else (validation, self-release by device id,
 * release-all) keeps working. Outside production a fixed development secret
 * is used so local runs and the test suite need no setup.
 *
 * Changing the secret changes every token. That only invalidates device lists
 * the app is currently showing; it fetches a fresh list next time.
 *
 * A separate module (not a function inside server.js) so it can be unit
 * tested without starting the server or touching the database — server.js
 * unconditionally calls app.listen() at require time.
 */

const MIN_SECRET_LENGTH = 32;
const DEV_SECRET = 'development-only-device-token-secret-not-for-production';

function createDeviceTokens({ secret = '', production = false } = {}) {
  const trimmed = String(secret || '').trim();
  const usable = trimmed.length >= MIN_SECRET_LENGTH;
  const key = usable ? trimmed : production ? null : DEV_SECRET;
  const source = usable ? 'env' : key ? 'development' : 'missing';

  return {
    configured: key !== null,
    source,
    /** The token for one device row, or null when no secret is configured. */
    token(licenseKey, deviceId) {
      if (key === null) return null;
      return crypto.createHmac('sha256', key)
        .update(`devicetoken|${licenseKey}|${deviceId}`)
        .digest('hex')
        .slice(0, 16);
    },
  };
}

const fromEnv = createDeviceTokens({
  secret: process.env.DEVICE_TOKEN_SECRET,
  production: process.env.NODE_ENV === 'production',
});

module.exports = {
  createDeviceTokens,
  deviceToken: fromEnv.token,
  deviceTokensConfigured: fromEnv.configured,
  deviceTokenSource: fromEnv.source,
  MIN_SECRET_LENGTH,
};
