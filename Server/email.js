'use strict';

/**
 * Licence-key email delivery.
 *
 * Provider-agnostic, chosen by which environment variables are present:
 *
 *   RESEND_API_KEY                     -> Resend, over plain fetch (no dependency)
 *   SMTP_URL, or SMTP_HOST/USER/PASS   -> any SMTP server, via nodemailer
 *   neither                            -> disabled; sends are skipped, not failed
 *
 * The disabled case matters. Sending is a side effect of a purchase that has
 * already succeeded, so a missing or broken mail provider must never fail the
 * webhook — that would make Stripe retry a payment flow that actually worked.
 * Every failure path here returns a result object; none of them throw.
 */

const APP_NAME = 'FlowShield';

const FROM = process.env.EMAIL_FROM || 'FlowShield <onboarding@resend.dev>';
const REPLY_TO = process.env.EMAIL_REPLY_TO || '';
const SITE_URL = (process.env.WEBSITE_URL || 'https://seventycookies6-design.github.io/flowshield')
  .replace(/\/$/, '');

/* ------------------------------------------------------------------ template */

function escapeHtml(value) {
  return String(value == null ? '' : value).replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
}

/**
 * Build the licence email.
 *
 * Deliberately plain HTML with inline styles and a table-free layout: mail
 * clients strip <style> blocks, ignore most modern CSS, and Gmail clips long
 * messages. The key is repeated in the plain-text part so it survives clients
 * that render text only.
 */
function licenseEmail({ licenseKey, email, status }) {
  const subject = `Your ${APP_NAME} licence key`;

  const text = [
    `Thanks for buying ${APP_NAME}. It's yours to keep - no subscription.`,
    '',
    `Licence key: ${licenseKey}`,
    '',
    'To activate:',
    `  1. Open ${APP_NAME} and go to Settings.`,
    '  2. Paste the key into "License key".',
    '  3. Click "Activate licence".',
    '',
    `You can also activate with this email address (${email}) instead of the key.`,
    '',
    `${APP_NAME}: ${SITE_URL}`,
    REPLY_TO ? `Questions? Reply to this email or write to ${REPLY_TO}.` : '',
    '',
    `— ${APP_NAME}`,
  ]
    .filter((line) => line !== null)
    .join('\n');

  // The charset declaration is not optional. Without a <head> carrying it,
  // clients fall back to Latin-1 and every non-ASCII character in the message
  // renders as mojibake — an em dash becomes "â€”" in the first line the
  // customer reads.
  const html = `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(subject)}</title>
</head>
<body style="margin:0;padding:24px;background:#f4f4f7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1a1a2e">
  <div style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:12px;padding:32px">
    <p style="margin:0 0 4px;font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#6f6d8d">${escapeHtml(APP_NAME)}</p>
    <h1 style="margin:0 0 16px;font-size:22px;font-weight:600">Your licence key</h1>

    <p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:#44435c">
      Thanks for buying ${escapeHtml(APP_NAME)} — it is yours to keep, with no subscription. Here is the key — keep this email, it is the only copy we send.
    </p>

    <div style="margin:0 0 24px;padding:18px;background:#0e0e1a;border-radius:10px;text-align:center">
      <div style="font-family:Consolas,Menlo,monospace;font-size:19px;font-weight:700;letter-spacing:.08em;color:#ffffff">${escapeHtml(licenseKey)}</div>
    </div>

    <p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:#44435c"><strong>To activate</strong></p>
    <ol style="margin:0 0 24px;padding-left:20px;font-size:15px;line-height:1.7;color:#44435c">
      <li>Open ${escapeHtml(APP_NAME)} and go to <strong>Settings</strong>.</li>
      <li>Paste the key into <strong>License key</strong>.</li>
      <li>Click <strong>Activate licence</strong>.</li>
    </ol>

    <p style="margin:0 0 24px;font-size:14px;line-height:1.6;color:#6f6d8d">
      Lost the key? You can also activate with this email address
      (<strong>${escapeHtml(email || '')}</strong>) instead.
    </p>

    <p style="margin:0;font-size:13px;line-height:1.6;color:#8b89a3;border-top:1px solid #ececf2;padding-top:18px">
      ${escapeHtml(APP_NAME)}: <a href="${escapeHtml(SITE_URL)}" style="color:#6f5cff">${escapeHtml(SITE_URL)}</a>.
      ${REPLY_TO ? `Questions? Write to <a href="mailto:${escapeHtml(REPLY_TO)}" style="color:#6f5cff">${escapeHtml(REPLY_TO)}</a>.` : ''}
    </p>
  </div>
</body></html>`;

  return { subject, text, html };
}

/* ----------------------------------------------------------------- providers */

function resendProvider(apiKey) {
  return {
    name: 'resend',
    async send({ to, subject, html, text }) {
      const response = await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          from: FROM,
          to: [to],
          subject,
          html,
          text,
          ...(REPLY_TO ? { reply_to: REPLY_TO } : {}),
        }),
      });

      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        // Resend's most common rejection: an unverified domain may only send
        // to the account owner's own address. Say so rather than "HTTP 403".
        const detail = body?.message || body?.error || `HTTP ${response.status}`;
        return { ok: false, error: detail };
      }
      return { ok: true, id: body.id };
    },
  };
}

function smtpProvider() {
  let nodemailer;
  try {
    nodemailer = require('nodemailer');
  } catch {
    return {
      name: 'smtp',
      async send() {
        return { ok: false, error: 'nodemailer is not installed; run npm install' };
      },
    };
  }

  const transport = process.env.SMTP_URL
    ? nodemailer.createTransport(process.env.SMTP_URL)
    : nodemailer.createTransport({
        host: process.env.SMTP_HOST,
        port: Number(process.env.SMTP_PORT || 587),
        secure: String(process.env.SMTP_SECURE || '') === 'true',
        auth:
          process.env.SMTP_USER || process.env.SMTP_PASS
            ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS }
            : undefined,
      });

  return {
    name: 'smtp',
    async send({ to, subject, html, text }) {
      const info = await transport.sendMail({
        from: FROM,
        to,
        subject,
        text,
        html,
        ...(REPLY_TO ? { replyTo: REPLY_TO } : {}),
      });
      return { ok: true, id: info.messageId };
    },
  };
}

/**
 * Writes each message to a directory instead of sending it.
 *
 * Lets the delivery pipeline — templating, the once-only claim, the resend
 * endpoint — be tested end to end without a provider account or a real inbox,
 * and gives a local developer something to open and look at.
 */
function captureProvider(directory) {
  const fs = require('fs');
  const path = require('path');
  fs.mkdirSync(directory, { recursive: true });

  return {
    name: 'capture',
    async send({ to, subject, html, text }) {
      const stamp = new Date().toISOString().replace(/[:.]/g, '-');
      const safe = String(to).replace(/[^a-zA-Z0-9@._-]/g, '_');
      const file = path.join(directory, `${stamp}-${safe}.json`);
      fs.writeFileSync(
        file,
        JSON.stringify({ to, from: FROM, subject, text, html, capturedAt: stamp }, null, 2),
        'utf8',
      );
      return { ok: true, id: path.basename(file), captured: file };
    },
  };
}

function disabledProvider() {
  return {
    name: 'disabled',
    async send({ to, subject }) {
      return { ok: false, skipped: true, error: `email not configured (would send "${subject}" to ${to})` };
    },
  };
}

function pickProvider() {
  // Capture wins so a test can force it even where real credentials exist —
  // a test run must never be able to email an actual customer.
  if (process.env.EMAIL_CAPTURE_DIR) return captureProvider(process.env.EMAIL_CAPTURE_DIR);
  if (process.env.RESEND_API_KEY) return resendProvider(process.env.RESEND_API_KEY);
  if (process.env.SMTP_URL || process.env.SMTP_HOST) return smtpProvider();
  return disabledProvider();
}

const provider = pickProvider();

/* -------------------------------------------------------------------- public */

const isConfigured = provider.name !== 'disabled';

/**
 * Send a licence key. Never throws — a purchase has already completed by the
 * time this runs, and no mail problem should turn that into a failure.
 */
async function sendLicenseEmail({ to, licenseKey, status }) {
  if (!to) return { ok: false, skipped: true, error: 'no email address on the subscription' };

  const message = licenseEmail({ licenseKey, email: to, status });

  try {
    return await provider.send({ to, ...message });
  } catch (err) {
    return { ok: false, error: err && err.message ? err.message : String(err) };
  }
}

module.exports = {
  sendLicenseEmail,
  licenseEmail,
  isConfigured,
  providerName: provider.name,
  FROM,
};
