#!/usr/bin/env node
'use strict';

/**
 * Small maintenance utility for the licence database.
 *
 *   node tools/db_admin.js list [n]        newest rows
 *   node tools/db_admin.js show <key>       one row as JSON
 *   node tools/db_admin.js by-email <email> newest row for that address as JSON
 *   node tools/db_admin.js pick-active      newest active row as JSON
 *   node tools/db_admin.js forget <key>     delete a row (cache only)
 *   node tools/db_admin.js count
 *
 * `forget` is safe: the database is a cache of Stripe, and the server rebuilds
 * any row it is missing. The regression suite uses it to simulate the disk
 * loss that a free-tier redeploy causes.
 */

const path = require('path');

const SERVER_DIR = path.join(__dirname, '..', 'Server');
const db = require(path.join(SERVER_DIR, 'db.js'));

function openRaw() {
  try {
    const Database = require(path.join(SERVER_DIR, 'node_modules', 'better-sqlite3'));
    return new Database(db.DB_PATH);
  } catch {
    const { DatabaseSync } = require('node:sqlite');
    return new DatabaseSync(db.DB_PATH);
  }
}

const raw = openRaw();
const [command, argument] = process.argv.slice(2);

switch (command) {
  case 'list': {
    const limit = Number(argument || 10);
    const rows = raw
      .prepare('SELECT license_key, email, status, updated_at FROM licenses ORDER BY updated_at DESC LIMIT ?')
      .all(limit);
    for (const r of rows) {
      console.log(`${r.license_key}  ${String(r.status).padEnd(9)}  ${r.email || '(no email)'}`);
    }
    break;
  }

  case 'show':
    console.log(JSON.stringify(raw.prepare('SELECT * FROM licenses WHERE license_key = ?').get(argument) || null));
    break;

  case 'by-email':
    // Recovery by email alone (no key presented) is free to mint a fresh
    // license_key rather than reuse a forgotten one (server.js's /validate:
    // a presented key is preserved, an email alone is not a promise about
    // which key comes back) — so a test proving Stripe recovery worked has
    // to look the rebuilt row up by email, not by the key it wiped.
    console.log(
      JSON.stringify(
        raw
          .prepare('SELECT * FROM licenses WHERE email = ? ORDER BY updated_at DESC LIMIT 1')
          .get(argument) || null,
      ),
    );
    break;

  case 'pick-active':
    console.log(
      JSON.stringify(
        raw
          .prepare(
            "SELECT license_key, email, stripe_subscription_id FROM licenses " +
              "WHERE status = 'active' AND email IS NOT NULL " +
              'ORDER BY updated_at DESC LIMIT 1',
          )
          .get() || null,
      ),
    );
    break;

  case 'forget': {
    const before = raw.prepare('SELECT COUNT(*) AS c FROM licenses WHERE license_key = ?').get(argument).c;
    raw.prepare('DELETE FROM licenses WHERE license_key = ?').run(argument);
    const after = raw.prepare('SELECT COUNT(*) AS c FROM licenses WHERE license_key = ?').get(argument).c;
    console.log(JSON.stringify({ key: argument, before, after, deleted: before > 0 && after === 0 }));
    break;
  }

  case 'count':
    console.log(JSON.stringify(db.statusCounts()));
    break;

  default:
    console.log(require('fs').readFileSync(__filename, 'utf8').split('*/')[0].split('/**')[1]);
    process.exit(2);
}
