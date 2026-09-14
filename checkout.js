/* FlowShield — checkout + license retrieval glue.
   Talks to the license server; no Stripe.js needed since Checkout is hosted. */

(function () {
  'use strict';

  var CONFIG = window.FLOWSHIELD_CONFIG || {};
  var params = new URLSearchParams(window.location.search);

  /*
   * Two ways to take a payment, picked automatically:
   *
   *   1. License server (?server=, or config.licenseServerUrl) — POSTs
   *      /create-checkout, which reserves a license key before redirecting.
   *      Used for local development and for a deployed backend.
   *
   *   2. Stripe Payment Link — a Stripe-hosted page needing no backend at all.
   *      This is what the published static site uses, because GitHub Pages
   *      can't run a server and a visitor's browser can't reach localhost.
   *
   * An explicit ?server= always wins so the automation suite can force path 1.
   */
  /*
   * Served from localhost with nothing configured? Then this is a development
   * copy, and the license server is almost certainly running next to it. Assume
   * so rather than falling back to the Payment Link, which would hide the
   * licence-key flow exactly where it most needs testing. The published site is
   * never on localhost, so it is unaffected.
   */
  function localDefaultServer() {
    var host = window.location.hostname;
    var isLocal = host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
    return isLocal ? 'http://localhost:3000' : '';
  }

  var SERVER = (params.get('server') || CONFIG.licenseServerUrl || localDefaultServer())
    .replace(/\/$/, '');
  var PAYMENT_LINK = CONFIG.paymentLink || '';
  var HAS_SERVER = SERVER.length > 0;

  window.FlowShield = {
    SERVER: SERVER,
    PAYMENT_LINK: PAYMENT_LINK,
    mode: HAS_SERVER ? 'license-server' : PAYMENT_LINK ? 'payment-link' : 'unconfigured',
  };

  /* --------------------------------------------------------------- utilities */

  function showAlert(id, kind, html) {
    var el = document.getElementById(id);
    if (!el) return;
    el.className = 'alert ' + kind + ' show';
    el.innerHTML = html;
  }

  function hideAlert(id) {
    var el = document.getElementById(id);
    if (el) el.className = 'alert';
  }

  function friendlyError(err, payload) {
    if (payload && payload.error === 'stripe_not_configured') {
      return (
        '<div><b>Stripe is not configured yet.</b><br>The license server is running but has no ' +
        'test keys. Add them to <code>.stripe_keys.json</code> and restart it — see ' +
        '<b>STRIPE_SETUP.md</b>.' +
        (payload.missing && payload.missing.length
          ? '<code>missing: ' + payload.missing.join(', ') + '</code>'
          : '') +
        '</div>'
      );
    }
    if (payload && payload.message) {
      return '<div><b>Checkout could not start.</b><code>' + escapeHtml(payload.message) + '</code></div>';
    }
    var msg = err && err.message ? err.message : String(err);
    return (
      '<div><b>Could not reach the license server.</b><br>Expected it at <code>' +
      escapeHtml(SERVER) +
      '</code>. Start it with <code>cd Server &amp;&amp; npm start</code>.<code>' +
      escapeHtml(msg) +
      '</code></div>'
    );
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* ------------------------------------------------------------ create checkout */

  async function startCheckout(button) {
    var original = button ? button.innerHTML : null;
    hideAlert('checkout-alert');

    // No backend: hand off to the Stripe-hosted Payment Link directly.
    if (!HAS_SERVER) {
      if (!PAYMENT_LINK) {
        showAlert(
          'checkout-alert',
          'error',
          '<div><b>Checkout is not configured yet.</b><br>No Stripe Payment Link and no ' +
            'license server are set. Run <code>node tools/setup_stripe_store.js</code> to ' +
            'create the product and wire this button up.</div>',
        );
        return;
      }
      if (button) {
        button.disabled = true;
        button.innerHTML = 'Opening secure checkout…';
      }
      window.location.href = PAYMENT_LINK;
      return;
    }

    if (button) {
      button.disabled = true;
      button.innerHTML = 'Opening secure checkout…';
    }

    try {
      var res = await fetch(SERVER + '/create-checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });

      var payload = null;
      try {
        payload = await res.json();
      } catch (e) {
        /* non-JSON body */
      }

      if (!res.ok || !payload || !payload.url) {
        showAlert('checkout-alert', 'error', friendlyError(new Error('HTTP ' + res.status), payload));
        if (button) {
          button.disabled = false;
          button.innerHTML = original;
        }
        return;
      }

      // Keep the key locally too, so the success page can recover it even if
      // the session lookup hiccups.
      try {
        sessionStorage.setItem('flowshield_pending_key', payload.licenseKey || '');
      } catch (e) {
        /* private mode — non-fatal */
      }

      window.location.href = payload.url;
    } catch (err) {
      showAlert('checkout-alert', 'error', friendlyError(err, null));
      if (button) {
        button.disabled = false;
        button.innerHTML = original;
      }
    }
  }

  /* ------------------------------------------------------------- success page */

  /**
   * Poll /get-license — it answers 202 while Stripe still shows the session
   * unpaid. Reports progress on every attempt: a spinner with no changing text
   * is indistinguishable from a hung page, and the most likely reason to be
   * here for more than a second or two is that the server isn't running.
   */
  async function fetchLicense(sessionId, attempts, onProgress) {
    attempts = attempts || 10;
    var lastPayload = null;
    var unreachable = 0;

    for (var i = 0; i < attempts; i += 1) {
      try {
        var res = await fetch(SERVER + '/get-license?session_id=' + encodeURIComponent(sessionId));
        var payload = await res.json();
        lastPayload = payload;
        unreachable = 0;

        if (res.ok && payload.licenseKey && payload.isPro) return payload;

        // A hard error (404/422/502) will not improve by retrying.
        if (res.status >= 400 && res.status !== 202 && !payload.pending) {
          return { error: true, payload: payload, status: res.status };
        }
        if (onProgress) onProgress(i + 1, attempts, 'Payment is still settling');
      } catch (err) {
        lastPayload = { message: err.message, unreachable: true };
        unreachable += 1;
        if (onProgress) onProgress(i + 1, attempts, 'Cannot reach the license server');
        // No point retrying ten times against a server that isn't listening.
        if (unreachable >= 3) {
          return { error: true, payload: lastPayload, unreachable: true };
        }
      }
      await new Promise(function (r) {
        setTimeout(r, 1200);
      });
    }
    return { error: true, payload: lastPayload, timedOut: true };
  }

  async function initSuccessPage() {
    var sessionId = params.get('session_id');
    var seal = document.getElementById('seal');
    var title = document.getElementById('success-title');
    var blurb = document.getElementById('success-blurb');
    var keyVal = document.getElementById('license-value');
    var actions = document.getElementById('success-actions');

    function fail(headline, detail) {
      if (seal) seal.className = 'seal failed';
      if (seal) seal.innerHTML = iconAlert();
      if (title) title.textContent = headline;
      if (blurb) blurb.innerHTML = detail;
      if (keyVal) keyVal.textContent = '—';
    }

    if (!sessionId) {
      fail(
        'No checkout session',
        'This page expects a <code>session_id</code> in the URL. Start from the ' +
          '<a href="index.html" style="color:var(--cyan)">pricing section</a>.',
      );
      return;
    }

    /*
     * Payment Link build: the payment is real and already complete, but there is
     * no backend to exchange the session for a key. Say so plainly rather than
     * spinning on a server that was never going to answer — the buyer has paid
     * and needs to know what happens next.
     */
    if (!HAS_SERVER) {
      if (seal) {
        seal.className = 'seal';
        seal.innerHTML = iconCheck();
      }
      if (title) title.textContent = 'Payment received — thank you';
      if (blurb) {
        // Deliberately does not promise an email. Nothing in this build sends
        // one: issuing a key needs the licence service, and the published site
        // is static. Saying "check your inbox" would be a promise the system
        // cannot keep, and the buyer would wait for a message that never comes.
        blurb.innerHTML =
          // No receipt claim either: whether Stripe emails one depends on the
          // account's receipt settings, which this page can't see.
          'Your FlowShield Pro subscription is active. ' +
          'To unlock Pro, open <b>FlowShield → Settings</b>, enter the email address you ' +
          'used at checkout, and click <b>Activate Pro</b>.' +
          (CONFIG.supportEmail
            ? ' Trouble activating? Email <b>' + escapeHtml(CONFIG.supportEmail) +
              '</b> from the address you used at checkout.'
            : '');
      }
      if (keyVal) keyVal.textContent = 'activate with your email';
      document.body.setAttribute('data-license-status', 'paid-awaiting-key');
      document.body.setAttribute('data-checkout-session', sessionId);
      return;
    }

    var result = await fetchLicense(sessionId, 10, function (attempt, total, note) {
      if (blurb) {
        blurb.textContent = note + '… (checked ' + attempt + ' of ' + total + ')';
      }
    });

    if (result && result.licenseKey) {
      if (seal) {
        seal.className = 'seal';
        seal.innerHTML = iconCheck();
      }
      if (title) title.textContent = 'FlowShield Pro is yours';
      if (blurb) {
        // Only claim an email was sent when the server actually reports one.
        // The page must never promise delivery it cannot vouch for.
        // It never promises a receipt either: Stripe sends one only if the
        // account's receipt emails are switched on, which this page can't see.
        var mailed = result.emailSent
          ? ' A copy is on its way to <b>' + escapeHtml(result.email || 'your inbox') + '</b>.'
          : ' Save this key now — it isn’t emailed to you.';

        blurb.innerHTML =
          'Subscription <b>' +
          escapeHtml(result.status) +
          '</b>' +
          (result.email ? ' for <b>' + escapeHtml(result.email) + '</b>' : '') +
          '.' +
          mailed;
      }
      if (keyVal) keyVal.textContent = result.licenseKey;
      if (actions) actions.style.display = 'flex';

      // Expose for the automation suite to read deterministically.
      document.body.setAttribute('data-license-key', result.licenseKey);
      document.body.setAttribute('data-license-status', result.status);
      window.FlowShield.license = result;
      return;
    }

    // Fall back to the key we stashed before redirecting.
    var stashed = '';
    try {
      stashed = sessionStorage.getItem('flowshield_pending_key') || '';
    } catch (e) {
      /* ignore */
    }

    var payload = (result && result.payload) || {};
    var detail =
      payload.error === 'stripe_not_configured'
        ? 'The license server has no Stripe keys configured. See <b>STRIPE_SETUP.md</b>.'
        : result && result.unreachable
          ? 'The license server at <code>' + escapeHtml(SERVER) + '</code> is not responding. ' +
            'Start it with <code>cd Server &amp;&amp; npm start</code>, then reload this page.'
          : payload.message
            ? '<code>' + escapeHtml(payload.message) + '</code>'
            : 'The payment may still be settling. Refresh in a moment.';

    if (stashed) {
      fail('Still confirming your payment', detail);
      if (keyVal) keyVal.textContent = stashed;
      if (blurb) {
        blurb.innerHTML +=
          '<br><br>Your reserved key is shown below. It activates as soon as Stripe confirms the charge.';
      }
      if (actions) actions.style.display = 'flex';
      document.body.setAttribute('data-license-key', stashed);
      document.body.setAttribute('data-license-status', 'pending');
    } else {
      fail('Could not retrieve your license', detail);
    }
  }

  function iconCheck() {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>';
  }
  function iconAlert() {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 8v5"/><path d="M12 17h.01"/><circle cx="12" cy="12" r="9"/></svg>';
  }

  /* ------------------------------------------------------------------- wiring */

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-checkout]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        startCheckout(btn);
      });
    });

    if (params.get('checkout') === 'cancelled') {
      showAlert(
        'checkout-alert',
        'info',
        '<div><b>Checkout cancelled.</b> Nothing was charged — pick up where you left off whenever you like.</div>',
      );
    }

    var copyBtn = document.getElementById('copy-key');
    if (copyBtn) {
      copyBtn.addEventListener('click', async function () {
        var key = (document.getElementById('license-value') || {}).textContent || '';
        var note = document.getElementById('copy-note');
        try {
          await navigator.clipboard.writeText(key.trim());
          if (note) note.textContent = 'Copied to clipboard.';
        } catch (e) {
          if (note) note.textContent = 'Select the key above and copy it manually.';
        }
      });
    }

    var nav = document.querySelector('header.nav');
    if (nav) {
      var onScroll = function () {
        nav.classList.toggle('scrolled', window.scrollY > 8);
      };
      window.addEventListener('scroll', onScroll, { passive: true });
      onScroll();
    }

    if (document.body.classList.contains('success-page')) initSuccessPage();
  });

  window.FlowShield.startCheckout = startCheckout;
})();
