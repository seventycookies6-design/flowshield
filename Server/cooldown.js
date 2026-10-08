'use strict';

/**
 * A per-key cooldown: one action per key per window.
 *
 * /resend-license is limited per IP, but the email goes to the *buyer*, so an
 * attacker spreading requests over many IPs can still flood one inbox. This
 * limits by the address the mail goes to instead (#286).
 *
 * In memory, like the IP limiter: a restart forgets it, which at worst allows
 * one extra email per address. COOLDOWN is the window in milliseconds; 0
 * disables it.
 */

function createCooldown({ windowMs = 600_000, now = () => Date.now() } = {}) {
  const last = new Map(); // normalised key -> time of the last accepted action

  const norm = (key) => String(key).trim().toLowerCase();

  /** True and starts the window if the key is free; false while cooling down. */
  function tryAcquire(key) {
    if (!windowMs || windowMs <= 0) return true;
    const t = now();
    const id = norm(key);
    const prev = last.get(id);
    if (prev !== undefined && t - prev < windowMs) return false;
    last.set(id, t);

    // Keep memory bounded: drop expired entries once the map grows.
    if (last.size > 10_000) {
      for (const [k, v] of last) if (t - v >= windowMs) last.delete(k);
    }
    return true;
  }

  return { tryAcquire };
}

module.exports = { createCooldown };
