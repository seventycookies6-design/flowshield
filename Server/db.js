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
`);

const now = () => Math.floor(Date.now() / 1000);

/** Statuses that entitle the holder to Pro features. */
const PRO_STATUSES = new Set(['active', 'trialing']);

const q = {
  insert: db.prepare(`
    INSERT INTO licenses (license_key, email, status, stripe_session_id, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?)
  `),
  byKey: db.prepare('SELECT * FROM licenses WHERE license_key = ?'),
  bySession: db.prepare('SELECT * FROM licenses WHERE stripe_session_id = ?'),
  bySubscription: db.prepare('SELECT * FROM licenses WHERE stripe_subscription_id = ?'),
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
           stripe_subscription_id = ?, current_period_end = ?, updated_at = ?
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
  seenEvent: db.prepare('SELECT event_id FROM webhook_events WHERE event_id = ?'),
  recordEvent: db.prepare('INSERT INTO webhook_events (event_id, type, created_at) VALUES (?, ?, ?)'),
  stats: db.prepare(`
    SELECT status, COUNT(*) AS n FROM licenses GROUP BY status
  `),
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

  findByEmail(email) {
    return q.byEmailActive.get(email) || q.byEmailAny.get(email) || null;
  },

  attachSession(licenseKey, sessionId) {
    q.attachSession.run(sessionId, now(), licenseKey);
  },

  activate(licenseKey, { status, email, customerId, subscriptionId, currentPeriodEnd }) {
    q.activate.run(
      status,
      email || null,
      customerId || null,
      subscriptionId || null,
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
};
