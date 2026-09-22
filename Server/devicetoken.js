'use strict';

const crypto = require('crypto');

/**
 * Roadmap 5.7 ("see and manage your devices").
 *
 * A per-device token the app can send back to /devices to release a
 * *different* device's seat, without the list route ever handing back the
 * raw hashed device id it stores (see server.js's /devices handler: "Names
 * only, never the raw ids"). Deterministic per (licence key, device id) pair
 * — the same row gets the same token on every list — and one-way: nothing
 * about the raw device id can be recovered from it without also knowing the
 * licence key, which only its owner holds.
 *
 * A separate module (not a function inside server.js) so it can be unit
 * tested without starting the server or touching the database — server.js
 * unconditionally calls app.listen() at require time.
 */
function deviceToken(licenseKey, deviceId) {
  return crypto.createHash('sha256')
    .update(`devicetoken|${licenseKey}|${deviceId}`)
    .digest('hex')
    .slice(0, 16);
}

module.exports = { deviceToken };
