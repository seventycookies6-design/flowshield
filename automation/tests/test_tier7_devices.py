"""
Tier 7 — the per-licence device limit.

Two failure modes matter and they pull in opposite directions: a shared key
working on unlimited machines costs revenue, and a cap that locks out a paying
customer costs something worse. Both are tested here.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import requests

from config import DESKTOP_DIR, SERVER_DIR

LIMIT = 3  # DEVICE_LIMIT default in server.js


def device(tag: str = "") -> str:
    """A distinct machine identifier, shaped like the app's hashed one."""
    return (uuid.uuid4().hex + uuid.uuid4().hex)[:32] if not tag else tag


@pytest.fixture
def licence(server):
    """An active licence to attach devices to, with its seats cleared first."""
    body = requests.post(f"{server}/validate",
                         json={"email": "deployed-e2e@example.com"}, timeout=60).json()
    if not body.get("isPro"):
        pytest.skip("no active subscription available")

    requests.post(f"{server}/devices",
                  json={"licenseKey": body["licenseKey"], "action": "release-all"},
                  timeout=30)
    return body["licenseKey"]


def activate(server, key, device_id, name="Test PC"):
    return requests.post(
        f"{server}/validate",
        json={"licenseKey": key, "deviceId": device_id, "deviceName": name},
        timeout=60,
    ).json()


# ============================================================ the cap holds

@pytest.mark.stripe
class TestLimitEnforced:
    def test_devices_up_to_the_limit_are_accepted(self, server, licence):
        for index in range(LIMIT):
            body = activate(server, licence, device(), f"PC {index + 1}")
            assert body["isPro"] is True, f"device {index + 1} refused: {body}"
            assert body["deviceCount"] == index + 1

    def test_one_device_past_the_limit_is_refused(self, server, licence):
        for index in range(LIMIT):
            activate(server, licence, device(), f"PC {index + 1}")

        body = activate(server, licence, device(), "The one too many")

        assert body["isPro"] is False, "the seat limit did not hold"
        assert body["reason"] == "device_limit_reached"
        assert body["deviceCount"] == LIMIT
        assert body["deviceLimit"] == LIMIT

    def test_the_refusal_explains_what_to_do(self, server, licence):
        for _ in range(LIMIT):
            activate(server, licence, device())
        body = activate(server, licence, device())

        message = body.get("message", "").lower()
        assert "deactivate" in message, f"unhelpful refusal: {body.get('message')!r}"
        assert "device" in message

    def test_a_refused_device_is_not_a_payment_problem(self, server, licence):
        """The subscription is fine; only this machine is out of seats."""
        for _ in range(LIMIT):
            activate(server, licence, device())
        body = activate(server, licence, device())

        assert body["reason"] == "device_limit_reached"
        assert not body["reason"].startswith("subscription_")
        assert body.get("status") == "active", \
            "a seat problem must not be reported as a dead subscription"


# ===================================== the cap must not trap a paying customer

@pytest.mark.stripe
class TestLimitDoesNotLockOut:
    def test_the_same_device_never_consumes_a_second_seat(self, server, licence):
        """Reopening the app, or reinstalling, must not cost a slot."""
        mine = device()
        for attempt in range(6):
            body = activate(server, licence, mine)
            assert body["isPro"] is True, f"refused on attempt {attempt + 1}: {body}"
            assert body["deviceCount"] == 1, \
                f"one machine consumed {body['deviceCount']} seats"

    def test_releasing_a_seat_lets_a_new_machine_in(self, server, licence):
        used = [device() for _ in range(LIMIT)]
        for d in used:
            activate(server, licence, d)

        assert activate(server, licence, device())["isPro"] is False

        released = requests.post(
            f"{server}/devices",
            json={"licenseKey": licence, "action": "release", "deviceId": used[0]},
            timeout=30,
        ).json()
        assert released["deviceCount"] == LIMIT - 1

        body = activate(server, licence, device(), "Replacement laptop")
        assert body["isPro"] is True, "a freed seat was not reusable"

    def test_devices_can_be_listed(self, server, licence):
        activate(server, licence, device(), "Desktop")
        activate(server, licence, device(), "Laptop")

        body = requests.post(f"{server}/devices",
                             json={"licenseKey": licence}, timeout=30).json()

        assert body["deviceCount"] == 2
        assert {d["name"] for d in body["devices"]} == {"Desktop", "Laptop"}

    def test_listing_does_not_expose_raw_device_ids(self, server, licence):
        """Seat ids identify machines; the list is for naming, not tracking."""
        mine = device()
        activate(server, licence, mine, "Desktop")

        raw = requests.post(f"{server}/devices",
                            json={"licenseKey": licence}, timeout=30).text
        assert mine not in raw, "a raw device id was echoed back"

    def test_a_request_without_a_device_id_still_validates(self, server, licence):
        """curl, the test suite and support tooling have no machine identity."""
        body = requests.post(f"{server}/validate",
                             json={"licenseKey": licence}, timeout=60).json()
        assert body["isPro"] is True

    def test_a_request_without_a_device_id_claims_no_seat(self, server, licence):
        """...and therefore cannot be used to exhaust someone's allowance."""
        for _ in range(10):
            requests.post(f"{server}/validate", json={"licenseKey": licence}, timeout=60)

        body = requests.post(f"{server}/devices",
                             json={"licenseKey": licence}, timeout=30).json()
        assert body["deviceCount"] == 0, \
            f"{body['deviceCount']} phantom seats were consumed"


# ================================================================= the app

class TestAppSide:
    def test_the_app_sends_a_hash_not_a_machine_identifier(self):
        source = (Path(DESKTOP_DIR) / "Services" / "DeviceIdentity.cs").read_text(
            encoding="utf-8")

        assert "SHA256" in source, "the device id must be hashed"
        compute = source.split("private static string Compute()")[1]
        assert "Convert.ToHexString" in compute

        # The raw MachineGuid must be an input to the hash, never the value sent.
        assert "return guid" not in compute, "the raw MachineGuid must not be returned"

    def test_the_identifier_is_salted_to_this_app(self):
        source = (Path(DESKTOP_DIR) / "Services" / "DeviceIdentity.cs").read_text(
            encoding="utf-8")
        assert "Salt" in source, \
            "without a salt the same hash could be correlated across applications"

    def test_deactivating_releases_the_seat_before_forgetting_the_key(self):
        """
        Clearing the key first would leave the seat stranded — nobody would know
        which licence to free, and the customer loses a slot permanently.
        """
        source = (Path(DESKTOP_DIR) / "Services" / "LicenseService.cs").read_text(
            encoding="utf-8")
        body = source.split("public async Task DeactivateAsync")[1].split("\n    }")[0]

        release = body.index('action = "release"')
        clear = body.index("settings.LicenseKey = \"\"")
        assert release < clear, "the seat must be released before the key is cleared"

    def test_a_failed_release_still_deactivates_locally(self):
        """Deactivation must work offline."""
        source = (Path(DESKTOP_DIR) / "Services" / "LicenseService.cs").read_text(
            encoding="utf-8")
        body = source.split("public async Task DeactivateAsync")[1].split("\n    }")[0]
        assert "catch" in body, "a network failure must not block local deactivation"


@pytest.mark.stripe
class TestSeatReleaseSurvivesDataLoss:
    """
    A redeploy wipes the cached database. If /devices answered 404 in that
    window, a customer deactivating would never free their seat — losing a slot
    permanently, on the one endpoint whose whole job is giving slots back.
    """

    def test_releasing_works_after_the_cache_is_lost(self, server, licence):
        import json as _json
        import subprocess as _sp

        mine = device()
        assert activate(server, licence, mine, "My PC")["isPro"] is True

        # Simulate the redeploy: the licence row disappears from the cache.
        result = _sp.run(
            [NODE_EXE, str(Path(SERVER_DIR).parent / "tools" / "db_admin.js"),
             "forget", licence],
            cwd=str(Path(SERVER_DIR).parent), capture_output=True, text=True, timeout=60,
        )
        assert _json.loads(result.stdout.strip().splitlines()[-1])["deleted"] is True

        body = requests.post(
            f"{server}/devices",
            json={"licenseKey": licence, "action": "release", "deviceId": mine},
            timeout=90,
        )

        assert body.status_code == 200, (
            f"releasing a seat after cache loss returned {body.status_code}; "
            f"the customer's slot would be stranded"
        )


NODE_EXE = __import__("shutil").which("node") or r"C:\Program Files\nodejs\node.exe"


class TestServerConfiguration:
    def test_the_limit_is_configurable(self):
        source = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")
        assert "process.env.DEVICE_LIMIT" in source
        assert "?? 3" in source, "the default should be 3 seats"

    def test_seats_are_only_checked_after_the_subscription_passes(self):
        """Otherwise a seat problem would be indistinguishable from an unpaid one."""
        source = (Path(SERVER_DIR) / "server.js").read_text(encoding="utf-8")
        validate = source.split("app.post('/validate'")[1].split("app.post(")[0]

        not_pro = validate.index("if (!view.isPro)")
        seat_check = validate.index("db.registerDevice")
        assert not_pro < seat_check, \
            "the subscription check must come before the seat check"
