"""
Tier 6 — licence-key email delivery.

Runs a second server instance in capture mode on its own port, so the pipeline
is exercised end to end without a provider account and with no possibility of
emailing a real customer.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import requests

from config import SERVER_DIR

NODE = r"C:\Program Files\nodejs\node.exe"
NODE_EXE = NODE if Path(NODE).exists() else "node"

CAPTURE_PORT = 3123


def _free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) != 0


@pytest.fixture(scope="module")
def capture_server(tmp_path_factory):
    """A server whose email provider writes messages to a directory."""
    outbox = tmp_path_factory.mktemp("outbox")
    db_path = tmp_path_factory.mktemp("db") / "capture.db"

    env = os.environ.copy()
    env.update({
        "PORT": str(CAPTURE_PORT),
        "EMAIL_CAPTURE_DIR": str(outbox),
        "FLOWSHIELD_DB": str(db_path),
        "EMAIL_FROM": "FlowShield <test@flowshield.invalid>",
    })

    if not _free(CAPTURE_PORT):
        pytest.skip(f"port {CAPTURE_PORT} is busy")

    process = subprocess.Popen(
        [NODE_EXE, "server.js"], cwd=str(SERVER_DIR), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    base = f"http://127.0.0.1:{CAPTURE_PORT}"
    deadline = time.time() + 30
    while time.time() < deadline:
        if process.poll() is not None:
            pytest.fail(f"capture server exited: {process.stdout.read()[:600]}")
        try:
            if requests.get(f"{base}/health", timeout=2).status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.4)
    else:
        process.kill()
        pytest.fail("capture server never became healthy")

    yield {"base": base, "outbox": outbox}

    process.terminate()
    try:
        process.wait(timeout=6)
    except subprocess.TimeoutExpired:
        process.kill()


def _emails(outbox: Path) -> list[dict]:
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(outbox.glob("*.json"))]


# ================================================================ template

class TestTemplate:
    def test_the_key_appears_in_both_html_and_plain_text(self):
        """Text-only clients must still show the key."""
        script = (
            "const m=require('./email');"
            "const e=m.licenseEmail({licenseKey:'FS-ABCD-ABCD-ABCD-ABCD',"
            " email:'a@b.com', status:'active'});"
            "console.log(JSON.stringify({subject:e.subject,"
            " inHtml:e.html.includes('FS-ABCD-ABCD-ABCD-ABCD'),"
            " inText:e.text.includes('FS-ABCD-ABCD-ABCD-ABCD'),"
            " hasStyleBlock:/<style/i.test(e.html)}));"
        )
        result = subprocess.run([NODE_EXE, "-e", script], cwd=str(SERVER_DIR),
                                capture_output=True, text=True, timeout=60)
        out = json.loads(result.stdout.strip().splitlines()[-1])

        assert out["inHtml"] is True
        assert out["inText"] is True, "a text-only client would see no key"
        assert out["hasStyleBlock"] is False, \
            "mail clients strip <style> blocks; styles must be inline"
        assert "licence key" in out["subject"].lower()

    def test_the_html_declares_utf8(self):
        """
        Without a charset declaration, clients assume Latin-1 and every
        non-ASCII character becomes mojibake — the em dash in the opening
        sentence rendered as "â€”" before this was added. Assertions on the
        key alone never caught it; looking at the rendered email did.
        """
        script = (
            "const m=require('./email');"
            "const e=m.licenseEmail({licenseKey:'FS-AAAA-AAAA-AAAA-AAAA',"
            " email:'a@b.com', status:'active'});"
            "console.log(JSON.stringify({"
            " hasCharset:/<meta[^>]+charset=[\"']?utf-8/i.test(e.html),"
            " nonAscii:/[^\\x00-\\x7F]/.test(e.html)}));"
        )
        result = subprocess.run([NODE_EXE, "-e", script], cwd=str(SERVER_DIR),
                                capture_output=True, text=True, timeout=60)
        out = json.loads(result.stdout.strip().splitlines()[-1])

        if out["nonAscii"]:
            assert out["hasCharset"] is True, (
                "the email contains non-ASCII characters but declares no charset; "
                "they will render as mojibake"
            )

    def test_the_template_escapes_its_inputs(self):
        script = (
            "const m=require('./email');"
            "const e=m.licenseEmail({licenseKey:'FS-AAAA-AAAA-AAAA-AAAA',"
            " email:'<script>alert(1)</script>@x.com', status:'active'});"
            "console.log(JSON.stringify({raw:e.html.includes('<script>alert(1)</script>')}));"
        )
        result = subprocess.run([NODE_EXE, "-e", script], cwd=str(SERVER_DIR),
                                capture_output=True, text=True, timeout=60)
        assert json.loads(result.stdout.strip().splitlines()[-1])["raw"] is False


# =========================================================== configuration

class TestConfiguration:
    def test_health_reports_email_state_without_leaking_credentials(self, capture_server):
        body = requests.get(f"{capture_server['base']}/health", timeout=10).json()
        assert body["email"]["configured"] is True
        assert body["email"]["provider"] == "capture"

        raw = requests.get(f"{capture_server['base']}/health", timeout=10).text
        for secret in ("RESEND_API_KEY", "re_", "SMTP_PASS"):
            assert secret not in raw, f"{secret} leaked from /health"

    def test_capture_beats_real_credentials(self):
        """A test run must never be able to email a real customer."""
        source = (Path(SERVER_DIR) / "email.js").read_text(encoding="utf-8")
        picker = source.split("function pickProvider()")[1].split("\n}")[0]
        assert picker.index("EMAIL_CAPTURE_DIR") < picker.index("RESEND_API_KEY"), \
            "capture must be checked before any real provider"

    def test_an_unconfigured_server_skips_rather_than_fails(self):
        """A missing provider must not fail a purchase that already succeeded."""
        script = (
            "const m=require('./email');"
            "m.sendLicenseEmail({to:'x@y.com',licenseKey:'FS-AAAA-AAAA-AAAA-AAAA'})"
            ".then(r=>console.log(JSON.stringify(r)));"
        )
        env = {k: v for k, v in os.environ.items()
               if k not in ("EMAIL_CAPTURE_DIR", "RESEND_API_KEY", "SMTP_URL", "SMTP_HOST")}
        result = subprocess.run([NODE_EXE, "-e", script], cwd=str(SERVER_DIR),
                                capture_output=True, text=True, timeout=60, env=env)
        out = json.loads(result.stdout.strip().splitlines()[-1])
        assert out["ok"] is False
        assert out["skipped"] is True, "an unconfigured provider must skip, not error"


# ================================================================ delivery

@pytest.mark.stripe
class TestDelivery:
    def _paid_license(self, base):
        """Reuse a real active subscription rather than buying another."""
        response = requests.post(f"{base}/validate",
                                 json={"email": "deployed-e2e@example.com"}, timeout=60)
        body = response.json()
        if not body.get("isPro"):
            pytest.skip("no active subscription available to deliver for")
        return body

    def test_a_licence_is_emailed_once_and_only_once(self, capture_server, needs_stripe):
        base, outbox = capture_server["base"], capture_server["outbox"]
        licence = self._paid_license(base)

        before = len(_emails(outbox))

        first = requests.post(f"{base}/resend-license",
                              json={"email": licence["email"]}, timeout=60)
        assert first.status_code == 200
        time.sleep(1.5)

        after_first = _emails(outbox)
        assert len(after_first) == before + 1, "no email was captured"

        sent = after_first[-1]
        assert sent["to"] == licence["email"]
        assert licence["licenseKey"] in sent["text"]
        assert licence["licenseKey"] in sent["html"]

        # The success page lookup must not duplicate what the webhook sent.
        requests.get(f"{base}/get-license",
                     params={"session_id": "cs_test_nonexistent"}, timeout=30)
        time.sleep(1.0)
        assert len(_emails(outbox)) == before + 1, "a duplicate email was sent"

    def test_resend_is_explicitly_allowed_to_send_again(self, capture_server, needs_stripe):
        """The once-only guard must not lock a customer out of their own key."""
        base, outbox = capture_server["base"], capture_server["outbox"]
        licence = self._paid_license(base)

        before = len(_emails(outbox))
        requests.post(f"{base}/resend-license", json={"email": licence["email"]}, timeout=60)
        time.sleep(1.5)
        assert len(_emails(outbox)) == before + 1


# ============================================================ resend safety

class TestResendEndpoint:
    def test_missing_email_is_a_400(self, capture_server):
        response = requests.post(f"{capture_server['base']}/resend-license",
                                 json={}, timeout=15)
        assert response.status_code == 400

    def test_it_does_not_reveal_whether_an_address_is_a_customer(self, capture_server):
        """Differing responses would make this an oracle for who has bought."""
        stranger = requests.post(
            f"{capture_server['base']}/resend-license",
            json={"email": f"nobody-{uuid.uuid4().hex[:8]}@example.com"},
            timeout=60,
        )
        assert stranger.status_code == 200
        assert "if that address" in stranger.json()["message"].lower()

    def test_no_email_is_sent_to_a_stranger(self, capture_server):
        outbox = capture_server["outbox"]
        before = len(_emails(outbox))

        address = f"nobody-{uuid.uuid4().hex[:8]}@example.com"
        requests.post(f"{capture_server['base']}/resend-license",
                      json={"email": address}, timeout=60)
        time.sleep(1.2)

        after = _emails(outbox)
        assert len(after) == before, "an email was sent for an address with no subscription"
        assert not any(m["to"] == address for m in after)
