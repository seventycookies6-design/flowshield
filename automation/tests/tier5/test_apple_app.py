"""Tier 5: promises the Mac app (AppleApps/, #426) must keep in step with Windows.

The Mac app's own behaviour is tested in Swift (BasaltCore's tests and
AppleApps/scripts/e2e_blocker.sh). These checks guard what the Windows-side
tests already promise customers: what leaves the machine and what an export
contains. They read the Swift source, so they run anywhere, without a Mac.
"""
from __future__ import annotations

import re
from pathlib import Path

from config import DESKTOP_DIR

ROOT = Path(DESKTOP_DIR).parent
CORE = ROOT / "AppleApps" / "BasaltCore" / "Sources" / "BasaltCore"


class TestTheMacAppSendsWhatThePolicySays:
    def test_the_licence_check_sends_the_same_four_fields_as_windows(self):
        """
        The privacy policy discloses exactly licenseKey, email, deviceId and
        deviceName (test_claims_privacy pins the Windows payload). A Mac client
        that sent one more field would break that promise silently.
        """
        client = (CORE / "LicenseClient.swift").read_text(encoding="utf-8")
        match = re.search(r'"/validate",.*?fields:\s*\[(.*?)\]', client, re.DOTALL)
        assert match, "could not find the /validate call in LicenseClient.swift; update this test"
        sent = set(re.findall(r'"(\w+)"\s*:', match.group(1)))
        assert sent == {"licenseKey", "email", "deviceId", "deviceName"}, (
            "the Mac licence check's fields changed; update the privacy copy on the "
            "site, in the app and in legal.html in the same PR"
        )

    def test_the_data_export_never_includes_the_licence_key(self):
        store = (CORE / "SettingsStore.swift").read_text(encoding="utf-8")
        export = store.split("public static func export(")[1].split("\n  }\n")[0]
        assert "licenseKey" not in export, "the Mac data export must never include the licence key"
        assert '"email": s.licenseEmail' in export, "the export's licence block moved; update this test"
