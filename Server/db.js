'use strict';

/**
 * SQLite storage for FlowShield licenses.
 *
 * Prefers better-sqlite3; falls back to Node's built-in node:sqlite when the
 * native module is unavailable (no prebuild for the local Node ABI, no build
 * toolchain, etc.). Both expose a compatible prepare()/run()/get()/all()
 * surface, so all queries below use positional `?` parameters to stay portable.
 */

const path = require('path');

const DB_PATH = process.env.FLOWSHIELD_DB || path.join(__dirname, 'licenses.db');

function openDatabase() {
  // The container image installs dependencies with --ignore-scripts, so
  // better-sqlite3's native binding is never built there and node:sqlite is
  // used instead. Set FLOWSHIELD_DB_DRIVER=node-sqlite to exercise that exact
  // path locally rather than discovering a difference after deploying.
  const forced = (process.env.FLOWSHIELD_DB_DRIVER || '').toLowerCase();

  if (forced !== 'node-sqlite') {
    try {
      const Database = require('better-sqlite3');
      const db = new Database(DB_PATH);
      db.pragma('journal_mode = WAL');
      return { db, driver: 'better-sqlite3' };
    } catch (err) {
      console.warn(
        `[db] better-sqlite3 unavailable (${err.code || err.message}); using node:sqlite`,
      );
    }
  }

  const { DatabaseSync } = require('node:sqlite');
  const db = new DatabaseSync(DB_PATH);
  db.exec('PRAGMA journal_mode = WAL');
  return { db, driver: 'node:sqlite' };
}

const { db, driver } = openDatabase();

db.exec(`
  CREATE TABLE IF NOT EXISTS licenses (
    license_key            TEXT PRIMARY KEY,
    email                  TEXT,
    status                 TEXT NOT NULL DEFAULT 'pending',
    stripe_session_id      TEXT,
    stripe_customer_id     TEXT,
    stripe_subscription_id TEXT,
    current_period_end     INTEGER,
    created_at             INTEGER NOT NULL,
    updated_at             INTEGER NOT NULL,
    activation_count       INTEGER NOT NULL DEFAULT 0,
    last_validated_at      INTEGER
  );

  CREATE INDEX IF NOT EXISTS idx_licenses_session      ON licenses(stripe_session_id);
  CREATE INDEX IF NOT EXISTS idx_licenses_email        ON licenses(email);
  CREATE INDEX IF NOT EXISTS idx_licenses_subscription ON licenses(stripe_subscription_id);

  CREATE TABLE IF NOT EXISTS webhook_events (
    event_id   TEXT PRIMARY KEY,
    type       TEXT NOT NULL,
    created_at INTEGER NOT NULL
  );

  -- Machines a licence has been activated on. device_id is a salted hash
  -- computed by the app; no hardware identifier or user name reaches here.
  CREATE TABLE IF NOT EXISTS devices (
    license_key TEXT NOT NULL,
    device_id   TEXT NOT NULL,
    device_name TEXT,
    first_seen  INTEGER NOT NULL,
    last_seen   INTEGER NOT NULL,
    PRIMARY KEY (license_key, device_id)
  );

  CREATE INDEX IF NOT EXISTS idx_devices_license ON devices(license_key);
`);

// Migration. SQLite has no "ADD COLUMN IF NOT EXISTS", and re-running ALTER
// throws "duplicate column name" — which is the success case on a database
// that already has it. Swallow exactly that.
function addColumn(sql) {
  try {
    db.exec(sql);
  } catch (err) {
    if (!/duplicate column/i.test(err.message)) throw err;
  }
}

addColumn('ALTER TABLE licenses ADD COLUMN license_email_sent_at INTEGER');
// One-time purchases (the current model) are recorded by their PaymentIntent;
// licences bought on the old monthly plan keep stripe_subscription_id instead.
addColumn('ALTER TABLE licenses ADD COLUMN stripe_payment_intent_id TEXT');
db.exec('CREATE INDEX IF NOT EXISTS idx_licenses_payment_intent ON licenses(stripe_payment_intent_id)');

const now = () => Math.floor(Date.now() / 1000);

/**
 * Statuses that entitle the holder to the full app. A paid one-time purchase is
 * 'active'; a refunded one becomes 'refunded'. 'trialing' is a legacy
 * subscription status — the app's own trial never touches the server.
 */
const PRO_STATUSES = new Set(['active', 'trialing']);

const q = {
  insert: db.prepare(`
    INSERT INTO licenses (license_key, email, status, stripe_session_id, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
  `),
  byKey: db.prepare('SELECT * FROM licenses WHERE license_key = ?'),
  bySession: db.prepare('SELECT * FROM licenses WHERE stripe_session_id = ?'),
  bySubscription: db.prepare('SELECT * FROM licenses WHERE stripe_subscription_id = ?'),
  byPaymentIntent: db.prepare('SELECT * FROM licenses WHERE stripe_payment_intent_id = ?'),
  byEmailActive: db.prepare(`
    SELECT * FROM licenses
    WHERE lower(email) = lower(?) AND status IN ('active', 'trialing')
    ORDER BY updated_at DESC LIMIT 1
  `),
  byEmailAny: db.prepare(`
    SELECT * FROM licenses WHERE lower(email) = lower(?)
    ORDER BY updated_at DESC LIMIT 1
  `),
  activate: db.prepare(`
    UPDATE licenses
       SET status = ?, email = COALESCE(?, email), stripe_customer_id = ?,
           stripe_subscription_id = ?, stripe_payment_intent_id = COALESCE(?, stripe_payment_intent_id),
           current_period_end = ?, updated_at = ?
     WHERE license_key = ?
  `),
  setStatus: db.prepare('UPDATE licenses SET status = ?, updated_at = ? WHERE license_key = ?'),
  setPeriodEnd: db.prepare('UPDATE licenses SET current_period_end = ?, updated_at = ? WHERE license_key = ?'),
  attachSession: db.prepare('UPDATE licenses SET stripe_session_id = ?, updated_at = ? WHERE license_key = ?'),
  countActivation: db.prepare(`
    UPDATE licenses
       SET activation_count = activation_count + 1, last_validated_at = ?
     WHERE license_key = ?
  `),
  markValidated: db.prepare('UPDATE licenses SET last_validated_at = ? WHERE license_key = ?'),
  markEmailed: db.prepare('UPDATE licenses SET license_email_sent_at = ? WHERE license_key = ?'),
  clearEmailed: db.prepare('UPDATE licenses SET license_email_sent_at = NULL WHERE license_key = ?'),
  seenEvent: db.prepare('SELECT event_id FROM webhook_events WHERE event_id = ?'),
  recordEvent: db.prepare('INSERT INTO webhook_events (event_id, type, created_at) VALUES (?, ?, ?)'),
  stats: db.prepare(`
    SELECT status, COUNT(*) AS n FROM licenses GROUP BY status
  `),

  deviceGet: db.prepare('SELECT * FROM devices WHERE license_key = ? AND device_id = ?'),
  deviceList: db.prepare('SELECT * FROM devices WHERE license_key = ? ORDER BY first_seen'),
  deviceCount: db.prepare('SELECT COUNT(*) AS n FROM devices WHERE license_key = ?'),
  deviceAdd: db.prepare(`
    INSERT INTO devices (license_key, device_id, device_name, first_seen, last_seen)
    VALUES (?, ?, ?, ?, ?)
  `),
  deviceTouch: db.prepare(`
    UPDATE devices SET last_seen = ?, device_name = COALESCE(?, device_name)
     WHERE license_key = ? AND device_id = ?
  `),
  deviceRemove: db.prepare('DELETE FROM devices WHERE license_key = ? AND device_id = ?'),
  deviceRemoveAll: db.prepare('DELETE FROM devices WHERE license_key = ?'),
};

module.exports = {
  driver,
  DB_PATH,
  PRO_STATUSES,
  now,

  isPro: (row) => !!row && PRO_STATUSES.has(row.status),

  createPending(licenseKey, email, sessionId) {
    const t = now();
    q.insert.run(licenseKey, email || null, 'pending', sessionId || null, t, t);
    return q.byKey.get(licenseKey);
  },

  findByKey: (key) => q.byKey.get(key) || null,
  findBySession: (sessionId) => q.bySession.get(sessionId) || null,
  findBySubscription: (subId) => q.bySubscription.get(subId) || null,
  findByPaymentIntent: (piId) => q.byPaymentIntent.get(piId) || null,

  findByEmail(email) {
    return q.byEmailActive.get(email) || q.byEmailAny.get(email) || null;
  },

  attachSession(licenseKey, sessionId) {
    q.attachSession.run(sessionId, now(), licenseKey);
  },

  activate(licenseKey, { status, email, customerId, subscriptionId, paymentIntentId, currentPeriodEnd }) {
    q.activate.run(
      status,
      email || null,
      customerId || null,
      subscriptionId || null,
      paymentIntentId || null,
      currentPeriodEnd || null,
      now(),
      licenseKey,
    );
    return q.byKey.get(licenseKey);
  },

  setStatus(licenseKey, status) {
    q.setStatus.run(status, now(), licenseKey);
    return q.byKey.get(licenseKey);
  },

  setPeriodEnd(licenseKey, periodEnd) {
    q.setPeriodEnd.run(periodEnd || null, now(), licenseKey);
  },

  countActivation(licenseKey) {
    q.countActivation.run(now(), licenseKey);
  },

  markValidated(licenseKey) {
    q.markValidated.run(now(), licenseKey);
  },

  /**
   * Claim the right to email this licence key, once.
   *
   * Returns true only for the caller that wins. The webhook and the
   * success-page lookup both activate a licence and both want to send, and
   * Stripe retries webhooks — without this the buyer gets the same key three
   * times. Marked before sending rather than after: a duplicate email is worse
   * than a missed one, and /resend-license covers the miss.
   */
  claimEmailSend(licenseKey) {
    const row = q.byKey.get(licenseKey);
    if (!row || row.license_email_sent_at) return false;
    q.markEmailed.run(now(), licenseKey);
    return true;
  },

  /** Undo the claim so a failed send can be retried. */
  releaseEmailSend(licenseKey) {
    q.clearEmailed.run(licenseKey);
  },

  markEmailed(licenseKey) {
    q.markEmailed.run(now(), licenseKey);
  },

  /** Idempotency guard: returns true the first time an event id is seen. */
  claimEvent(eventId, type) {
    if (!eventId) return true;
    if (q.seenEvent.get(eventId)) return false;
    q.recordEvent.run(eventId, type || 'unknown', now());
    return true;
  },

  statusCounts() {
    const out = {};
    for (const row of q.stats.all()) out[row.status] = Number(row.n);
    return out;
  },

  /* ------------------------------------------------------------- devices */

  deviceCount(licenseKey) {
    return Number(q.deviceCount.get(licenseKey)?.n || 0);
  },

  listDevices(licenseKey) {
    return q.deviceList.all(licenseKey);
  },

  knowsDevice(licenseKey, deviceId) {
    return !!q.deviceGet.get(licenseKey, deviceId);
  },

  /**
   * Record a machine against a licence, enforcing the seat limit.
   *
   * Returns { allowed, reason, count, limit }. A device already on the licence
   * is always allowed and never consumes a second seat — reinstalling, or
   * simply reopening the app, must not cost the customer a slot.
   */
  registerDevice(licenseKey, deviceId, deviceName, limit) {
    const t = now();

    if (q.deviceGet.get(licenseKey, deviceId)) {
      q.deviceTouch.run(t, deviceName || null, licenseKey, deviceId);
      return { allowed: true, reason: 'known_device', count: this.deviceCount(licenseKey), limit };
    }

    const count = this.deviceCount(licenseKey);
    if (limit > 0 && count >= limit) {
      return { allowed: false, reason: 'device_limit_reached', count, limit };
    }

    q.deviceAdd.run(licenseKey, deviceId, deviceName || null, t, t);
    return { allowed: true, reason: 'registered', count: count + 1, limit };
  },

  removeDevice(licenseKey, deviceId) {
    const existed = !!q.deviceGet.get(licenseKey, deviceId);
    q.deviceRemove.run(licenseKey, deviceId);
    return existed;
  },

  removeAllDevices(licenseKey) {
    q.deviceRemoveAll.run(licenseKey);
  },
};
