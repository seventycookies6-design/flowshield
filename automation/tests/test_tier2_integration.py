"""
Tier 2 — license server integration.

Hits the running HTTP server. Tests that need Stripe credentials are marked and
skip cleanly without them; everything else runs regardless.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import requests

from config import SERVER_DIR, load_stripe_keys

NODE = r"C:\Program Files\nodejs\node.exe"
NODE_EXE = NODE if Path(NODE).exists() else "node"


def new_key() -> str:
    """A freshly generated, checksum-valid key that the server has never seen."""
    result = subprocess.run(
        [NODE_EXE, "-e", "console.log(require('./licensekey').generate())"],
        cwd=str(SERVER_DIR), capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip()


def corrupt_key() -> str:
    """
    A key with the right shape but a deliberately broken checksum.

    Derived from a real key rather than hardcoded: roughly 1 in 32 arbitrary
    FS-shaped strings is checksum-valid by accident, so a literal fixture would
    quietly stop testing what it claims the moment the checksum changes.
    """
    script = (
        "const k=require('./licensekey');"
        "const body=k.generate().replace(/-/g,'').slice(2);"
        "const a='0123456789ABCDEFGHJKMNPQRSTVWXYZ';"
        "const m=body.slice(0,14)+a[(a.indexOf(body[14])+1)%32];"
        "console.log('FS-'+m.match(/.{1,4}/g).join('-'));"
    )
    result = subprocess.run([NODE_EXE, "-e", script], cwd=str(SERVER_DIR),
                            capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


# ================================================================ liveness

class TestServiceDescriptor:
    def test_root_describes_the_service(self, server):
        body = requests.get(f"{server}/", timeout=10).json()
        assert body["service"] == "FlowShield License Server"
        assert body["status"] == "ok"
        assert any("/create-checkout" in e for e in body["endpoints"])

    def test_health_reports_database_and_stripe_state(self, server):
        body = requests.get(f"{server}/health", timeout=10).json()
        assert body["status"] == "ok"
        assert body["database"]["driver"] in ("better-sqlite3", "node:sqlite")
        assert "configured" in body["stripe"]

    def test_health_never_leaks_a_secret_key(self, server):
        raw = requests.get(f"{server}/health", timeout=10).text
        assert "sk_test_" not in raw and "sk_live_" not in raw, \
            "the health endpoint must not echo the secret key"
        assert "whsec_" not in raw

    def test_unknown_route_is_a_clean_404(self, server):
        response = requests.get(f"{server}/nope", timeout=10)
        assert response.status_code == 404
        assert response.json()["error"] == "not_found"

    def test_server_is_in_test_mode_when_configured(self, server):
        body = requests.get(f"{server}/health", timeout=10).json()
        if not body["stripe"]["configured"]:
            pytest.skip("Stripe not configured")
        assert body["stripe"]["mode"] == "test", \
            "refusing to run the suite against live Stripe keys"


# ================================================================= validate

class TestValidate:
    def test_missing_credentials_is_a_400(self, server):
        response = requests.post(f"{server}/validate", json={}, timeout=10)
        assert response.status_code == 400
        assert response.json()["error"] == "missing_credentials"

    def test_malformed_key_is_rejected_without_touching_stripe(self, server):
        started = time.time()
        body = requests.post(f"{server}/validate",
                             json={"licenseKey": corrupt_key()},
                             timeout=10).json()
        assert body["valid"] is False
        assert body["reason"] == "malformed_key"
        assert body["isPro"] is False
        # A Stripe round-trip would be far slower than a local checksum check.
        assert time.time() - started < 3.0

    def test_well_formed_but_unknown_key_is_not_found(self, server):
        body = requests.post(f"{server}/validate",
                             json={"licenseKey": new_key()}, timeout=15).json()
        assert body["valid"] is False
        assert body["reason"] == "not_found"
        assert body["isPro"] is False

    def test_unknown_email_is_not_found(self, server):
        body = requests.post(
            f"{server}/validate",
            json={"email": f"nobody-{uuid.uuid4().hex[:8]}@example.com"},
            timeout=15).json()
        assert body["valid"] is False
        assert body["isPro"] is False

    def test_validate_accepts_snake_case_too(self, server):
        """The desktop app sends camelCase; keep the snake_case alias working."""
        body = requests.post(f"{server}/validate",
                             json={"license_key": corrupt_key()},
                             timeout=10).json()
        assert body["reason"] == "malformed_key"

    def test_key_normalisation_is_case_insensitive(self, server):
        key = new_key()
        lower = requests.post(f"{server}/validate",
                              json={"licenseKey": key.lower()}, timeout=15).json()
        upper = requests.post(f"{server}/validate",
                              json={"licenseKey": key.upper()}, timeout=15).json()
        assert lower["reason"] == upper["reason"] == "not_found", \
            "case should not change the verdict"


# ================================================================== webhook

class TestWebhook:
    def test_unsigned_webhook_is_rejected(self, server):
        response = requests.post(
            f"{server}/webhook",
            data=json.dumps({"id": "evt_test", "type": "checkout.session.completed"}),
            headers={"Content-Type": "application/json"},
            timeout=10)
        assert response.status_code in (400, 503)
        if response.status_code == 400:
            assert "Webhook Error" in response.text

    def test_forged_signature_is_rejected(self, server):
        keys = load_stripe_keys()
        if not keys.get("webhook_secret"):
            pytest.skip("no webhook secret configured")

        response = requests.post(
            f"{server}/webhook",
            data=json.dumps({"id": "evt_forged", "type": "checkout.session.completed"}),
            headers={"Content-Type": "application/json",
                     "Stripe-Signature": "t=1,v1=deadbeef"},
            timeout=10)
        assert response.status_code == 400, \
            "a forged signature must never be accepted"

    def test_valid_signature_is_accepted(self, server, needs_webhook_secret):
        """Sign a synthetic event exactly as Stripe would and post it."""
        keys = load_stripe_keys()
        event_id = f"evt_test_{uuid.uuid4().hex[:16]}"
        script = f"""
        const Stripe = require('stripe');
        const secret = {json.dumps(keys['webhook_secret'])};
        const payload = JSON.stringify({{
          id: {json.dumps(event_id)},
          object: 'event',
          type: 'customer.subscription.updated',
          data: {{ object: {{ id: 'sub_synthetic_test', status: 'active',
                              metadata: {{}}, items: {{ data: [] }} }} }}
        }});
        const header = Stripe.webhooks.generateTestHeaderString({{ payload, secret }});
        console.log(JSON.stringify({{ payload, header }}));
        """
        result = subprocess.run([NODE_EXE, "-e", script], cwd=str(SERVER_DIR),
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr[:400]
        signed = json.loads(result.stdout.strip().splitlines()[-1])

        response = requests.post(
            f"{server}/webhook",
            data=signed["payload"].encode(),
            headers={"Content-Type": "application/json",
                     "Stripe-Signature": signed["header"]},
            timeout=15)
        assert response.status_code == 200, response.text[:300]
        assert response.json()["received"] is True

    def test_replayed_event_is_ignored(self, server, needs_webhook_secret):
        """The same event id twice must not be processed twice."""
        keys = load_stripe_keys()
        event_id = f"evt_replay_{uuid.uuid4().hex[:16]}"
        script = f"""
        const Stripe = require('stripe');
        const secret = {json.dumps(keys['webhook_secret'])};
        const payload = JSON.stringify({{
          id: {json.dumps(event_id)}, object: 'event',
          type: 'customer.subscription.updated',
          data: {{ object: {{ id: 'sub_replay_test', status: 'active',
                              metadata: {{}}, items: {{ data: [] }} }} }}
        }});
        const header = Stripe.webhooks.generateTestHeaderString({{ payload, secret }});
        console.log(JSON.stringify({{ payload, header }}));
        """
        result = subprocess.run([NODE_EXE, "-e", script], cwd=str(SERVER_DIR),
                                capture_output=True, text=True, timeout=60)
        signed = json.loads(result.stdout.strip().splitlines()[-1])
        headers = {"Content-Type": "application/json",
                   "Stripe-Signature": signed["header"]}

        first = requests.post(f"{server}/webhook", data=signed["payload"].encode(),
                              headers=headers, timeout=15).json()
        second = requests.post(f"{server}/webhook", data=signed["payload"].encode(),
                               headers=headers, timeout=15).json()

        assert first.get("duplicate") is not True
        assert second.get("duplicate") is True, "replay guard did not fire"

    def test_a_refund_revokes_a_one_time_licence(self, server, needs_webhook_secret):
        """A signed charge.refunded for a paid purchase turns its licence off."""
        keys = load_stripe_keys()
        key = new_key()
        payment_id = f"pi_refund_probe_{uuid.uuid4().hex[:12]}"
        seed = (
            "const db=require('./db');"
            f"db.createPending({json.dumps(key)},'refund-probe@example.com',null);"
            f"db.activate({json.dumps(key)},{{status:'active',paymentIntentId:{json.dumps(payment_id)}}});"
            "console.log('{}');"
        )
        seeded = subprocess.run([NODE_EXE, "-e", seed], cwd=str(SERVER_DIR),
                                capture_output=True, text=True, timeout=30)
        assert seeded.returncode == 0, seeded.stderr[:400]

        script = f"""
        const Stripe = require('stripe');
        const payload = JSON.stringify({{
          id: 'evt_refund_{uuid.uuid4().hex[:16]}', object: 'event', type: 'charge.refunded',
          data: {{ object: {{ id: 'ch_refund_probe', object: 'charge', refunded: true,
                              payment_intent: {json.dumps(payment_id)} }} }}
        }});
        const header = Stripe.webhooks.generateTestHeaderString({{
          payload, secret: {json.dumps(keys['webhook_secret'])} }});
        console.log(JSON.stringify({{ payload, header }}));
        """
        result = subprocess.run([NODE_EXE, "-e", script], cwd=str(SERVER_DIR),
                                capture_output=True, text=True, timeout=60)
        signed = json.loads(result.stdout.strip().splitlines()[-1])
        response = requests.post(f"{server}/webhook", data=signed["payload"].encode(),
                                 headers={"Content-Type": "application/json",
                                          "Stripe-Signature": signed["header"]}, timeout=15)
        assert response.status_code == 200, response.text[:300]

        check = subprocess.run(
            [NODE_EXE, "-e", f"console.log(JSON.stringify(require('./db').findByKey({json.dumps(key)})))"],
            cwd=str(SERVER_DIR), capture_output=True, text=True, timeout=30)
        row = json.loads(check.stdout.strip().splitlines()[-1])
        assert row["status"] == "refunded", row


# ============================================================ get-license

class TestGetLicense:
    def test_missing_session_id_is_a_400(self, server):
        response = requests.get(f"{server}/get-license", timeout=10)
        assert response.status_code == 400
        assert response.json()["error"] == "missing_session_id"

    def test_unknown_session_is_not_a_500(self, server, needs_stripe):
        response = requests.get(f"{server}/get-license",
                                params={"session_id": "cs_test_does_not_exist"},
                                timeout=20)
        assert response.status_code in (404, 502), response.text[:200]
        assert response.status_code != 500


# ========================================================= billing portal

class TestPortal:
    def test_portal_for_an_unknown_license_is_a_404(self, server, needs_stripe):
        response = requests.post(f"{server}/create-portal-session",
                                 json={"licenseKey": new_key()}, timeout=20)
        assert response.status_code == 404
        assert response.json()["error"] == "no_customer"


# ========================================================== checkout (live)

class TestCreateCheckout:
    def test_without_keys_the_route_explains_itself(self, server, stripe_ready):
        if stripe_ready:
            pytest.skip("Stripe is configured; the 503 path does not apply")
        response = requests.post(f"{server}/create-checkout", json={}, timeout=15)
        assert response.status_code == 503
        body = response.json()
        assert body["error"] == "stripe_not_configured"
        assert body["missing"], "the error should name the missing fields"

    def test_creates_a_real_stripe_session(self, server, needs_stripe):
        response = requests.post(f"{server}/create-checkout",
                                 json={"email": "integration@example.com"}, timeout=45)
        assert response.status_code == 200, response.text[:300]
        body = response.json()

        assert body["url"].startswith("https://checkout.stripe.com/"), body["url"][:100]
        assert body["licenseKey"].startswith("FS-")
        assert body["sessionId"].startswith("cs_test_"), \
            "the session must be a test-mode session"

    def test_each_checkout_reserves_a_distinct_key(self, server, needs_stripe):
        keys = set()
        for _ in range(3):
            body = requests.post(f"{server}/create-checkout", json={}, timeout=45).json()
            keys.add(body["licenseKey"])
        assert len(keys) == 3, f"keys collided: {keys}"

    def test_reserved_license_starts_pending(self, server, needs_stripe):
        body = requests.post(f"{server}/create-checkout", json={}, timeout=45).json()
        check = requests.post(f"{server}/validate",
                              json={"licenseKey": body["licenseKey"]}, timeout=20).json()
        assert check["isPro"] is False, "an unpaid checkout must not grant a licence"
        assert check["reason"] == "license_pending"

    def test_checkout_is_a_one_time_payment(self, server, needs_stripe):
        """FlowShield is bought once; the session must not start a subscription."""
        body = requests.post(f"{server}/create-checkout", json={}, timeout=45).json()
        script = (
            "const {loadKeys}=require('./keys');const k=loadKeys();"
            "const s=require('stripe')(k.secret_key);"
            f"s.checkout.sessions.retrieve({json.dumps(body['sessionId'])},{{expand:['line_items']}})"
            ".then(x=>console.log(JSON.stringify({mode:x.mode,"
            "recurring:x.line_items.data[0].price.recurring,amount:x.amount_total})));"
        )
        result = subprocess.run([NODE_EXE, "-e", script], cwd=str(SERVER_DIR),
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr[:400]
        session = json.loads(result.stdout.strip().splitlines()[-1])
        assert session["mode"] == "payment", session
        assert session["recurring"] is None, "the configured price is still a subscription price"


# ========================================================= resend-license

class TestResendLicense:
    def test_missing_email_is_a_400(self, server):
        response = requests.post(f"{server}/resend-license",
                                 json={"sessionId": "cs_test_fake"}, timeout=10)
        assert response.status_code == 400
        assert response.json()["error"] == "missing_email"

    def test_missing_session_id_still_returns_generic_response(self, server):
        health = requests.get(f"{server}/health", timeout=10).json()
        if not health["email"]["configured"]:
            response = requests.post(f"{server}/resend-license",
                                     json={"email": "nobody@example.com"}, timeout=10)
            assert response.status_code == 503
            assert response.json()["error"] == "email_not_configured"
        else:
            response = requests.post(f"{server}/resend-license",
                                     json={"email": "nobody@example.com"}, timeout=10)
            assert response.status_code == 200
            body = response.json()
            assert body["ok"] is True

    def test_rate_limiting_is_applied(self):
        source = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")
        assert "'/resend-license', limiter.middleware('resend-license')" in source, \
            "/resend-license must be rate limited like other customer endpoints"

    def test_happy_path_with_email_configured(self, server):
        health = requests.get(f"{server}/health", timeout=10).json()
        if not health["email"]["configured"]:
            pytest.skip("email not configured on this server")
        response = requests.post(f"{server}/resend-license",
                                 json={"email": "testbuyer@example.com",
                                       "sessionId": "cs_test_nonexistent"},
                                 timeout=15)
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
