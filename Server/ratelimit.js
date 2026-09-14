'use strict';

/**
 * A small fixed-window rate limiter, per client IP and per route.
 *
 * The licence endpoints answer questions about customers (is this key valid,
 * which devices hold it, open its billing portal). Without a limit, keys and
 * addresses can be tried as fast as the network allows. This isn't a WAF; it
 * just makes guessing slow.
 *
 * Loopback clients are exempt so the local test suite, which deliberately
 * hammers these routes, isn't throttled. On Render, `trust proxy` makes req.ip
 * the real client address, so the exemption never applies to the public.
 *
 * RATE_LIMIT_PER_MINUTE overrides the default; 0 disables limiting.
 */

const LOOPBACK = new Set(['127.0.0.1', '::1', '::ffff:127.0.0.1']);

function createLimiter({ limit, windowMs = 60_000, now = () => Date.now(), exemptLoopback = true } = {}) {
  const hits = new Map(); // `${route} ${ip}` -> { count, windowStart }

  function check(route, ip) {
    if (!limit || limit <= 0) return { allowed: true };
    if (exemptLoopback && LOOPBACK.has(ip)) return { allowed: true };

    const t = now();
    const id = `${route} ${ip}`;
    let entry = hits.get(id);
    if (!entry || t - entry.windowStart >= windowMs) {
      entry = { count: 0, windowStart: t };
      hits.set(id, entry);
    }
    entry.count += 1;

    // Keep memory bounded: drop expired windows once the map grows.
    if (hits.size > 10_000) {
      for (const [k, v] of hits) if (t - v.windowStart >= windowMs) hits.delete(k);
    }

    if (entry.count > limit) {
      return { allowed: false, retryAfterSeconds: Math.ceil((entry.windowStart + windowMs - t) / 1000) };
    }
    return { allowed: true };
  }

  function middleware(route) {
    return (req, res, next) => {
      const verdict = check(route, req.ip || '');
      if (verdict.allowed) return next();
      res.set('Retry-After', String(verdict.retryAfterSeconds));
      return res.status(429).json({
        error: 'rate_limited',
        message: 'Too many requests. Please wait a minute and try again.',
      });
    };
  }

  return { check, middleware };
}

module.exports = { createLimiter, LOOPBACK };
