'use strict';

/**
 * FlowShield license keys.
 *
 * Format: FS-XXXX-XXXX-XXXX-XXXC
 *   - Crockford base32 alphabet (no I, L, O, U — avoids transcription errors)
 *   - 15 random payload symbols + 1 checksum symbol
 *
 * The checksum lets both the server and the desktop client reject obviously
 * malformed keys without a network round-trip, which keeps typo feedback fast
 * and stops garbage from reaching Stripe.
 */

const crypto = require('crypto');

const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
const PREFIX = 'FS';
const PAYLOAD_LEN = 15;

/**
 * Position-weighted checksum, mod 32.
 *
 * The weights must all be ODD. The alphabet size is 32, so a weight sharing a
 * factor with 32 leaves blind spots: changing symbol i by delta d shifts the
 * sum by d*w(i), and if d*w(i) ≡ 0 (mod 32) the checksum is unchanged. With
 * w(i) = i+1, position 3 has weight 4 and any delta of ±8 slips through. With
 * every weight odd, d*w ≡ 0 (mod 32) forces d ≡ 0 (mod 32) — impossible for a
 * single substitution, since |d| < 32. So every single-character typo is
 * caught, and most transpositions are too.
 */
function checksumSymbol(payload) {
  let sum = 0;
  for (let i = 0; i < payload.length; i += 1) {
    const v = ALPHABET.indexOf(payload[i]);
    if (v < 0) return null;
    sum += v * (2 * i + 1);
  }
  return ALPHABET[sum % ALPHABET.length];
}

function generate() {
  const bytes = crypto.randomBytes(PAYLOAD_LEN);
  let payload = '';
  for (let i = 0; i < PAYLOAD_LEN; i += 1) {
    payload += ALPHABET[bytes[i] % ALPHABET.length];
  }
  const body = payload + checksumSymbol(payload);
  const groups = body.match(/.{1,4}/g);
  return `${PREFIX}-${groups.join('-')}`;
}

/** Strip formatting and upper-case, so users can paste sloppily. */
function normalize(input) {
  if (typeof input !== 'string') return '';
  return input.trim().toUpperCase().replace(/[\s_]+/g, '');
}

function isWellFormed(input) {
  const normalized = normalize(input);
  if (!/^FS(-[0-9A-HJKMNP-TV-Z]{4}){4}$/.test(normalized)) return false;
  const body = normalized.slice(3).replace(/-/g, '');
  const payload = body.slice(0, PAYLOAD_LEN);
  const check = body.slice(PAYLOAD_LEN);
  return checksumSymbol(payload) === check;
}

module.exports = { generate, normalize, isWellFormed, ALPHABET, PREFIX };
