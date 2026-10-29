"""
Tier 1 -- the Get help diagnostics bundle (#400, Roadmap 4.3).

These run the real DiagnosticsService and HelpLinks through
`core.model_probe`, so what is proved is what .NET builds, not a Python copy.
Nothing here launches the app.
"""

from __future__ import annotations

import re

import pytest

from core.model_probe import probe

LICENSE_KEY = "FS-7QXK-M2RT-9WNB-4HPD"
EMAIL = "someone.private@example.org"
LOG_EMAIL = "other.person+tag@mail.example.com"
DEVICE_ID = "0123456789abcdef0123456789abcdef"
DEVICE_TOKEN = "f" * 16 + "a1b2c3d4e5f60718293a4b5c6d7e8f90"
JOURNAL = "Fought with my landlord about the deposit"
INTENTION = "Finish the secret cancer research chapter"
RUNNING_INTENTION = "Write the resignation letter"

ENVIRONMENT = {"version": "1.2.3", "windows": "Windows 10.0, build 26100 (64-bit)", "runtime": ".NET 8.0.11"}


def settings_with_secrets() -> dict:
    return {
        "LicenseKey": LICENSE_KEY,
        "LicenseEmail": EMAIL,
        "LicenseStatus": "active",
        "IsPro": True,
        "DefaultSprintMinutes": 40,
        "Sessions": [{
            "StartedUtc": "2026-10-01T09:00:00Z", "PlannedMinutes": 25, "Completed": True,
            "Intention": INTENTION, "Journal": JOURNAL,
        }],
        "ActiveSprint": {
            "StartedUtc": "2026-10-02T09:00:00Z", "PlannedMinutes": 25,
            "Intention": RUNNING_INTENTION,
        },
    }


def build(settings=None, lines=None, secrets=None, environment=ENVIRONMENT) -> str:
    request = {"cmd": "diagnostics", "settings": settings or {}, "log_lines": lines or []}
    if secrets:
        request["secrets"] = secrets
    if environment:
        request["environment"] = environment
    return probe(request)["text"]


class TestWhatTheBundleContains:
    def test_it_names_the_app_windows_and_runtime(self):
        text = build()
        assert "Basalt version: 1.2.3" in text
        assert "Windows 10.0, build 26100" in text
        assert ".NET runtime: .NET 8.0.11" in text

    def test_it_reports_this_pcs_real_windows_build_and_runtime(self):
        answer = probe({"cmd": "diagnostics", "settings": {}, "log_lines": [], "version": "7.8.9"})
        text = answer["text"]
        assert "Basalt version: 7.8.9" in text
        assert f"build {answer['os_build']}" in text
        assert answer["runtime"] in text

    def test_it_lists_ordinary_settings_as_they_are(self):
        text = build(settings_with_secrets())
        assert "DefaultSprintMinutes: 40" in text
        assert "IsPro: True" in text
        assert "LicenseStatus: active" in text

    def test_it_keeps_only_the_last_200_log_lines(self):
        lines = [f"2026-10-01 10:00:{i % 60:02d}.000 [INFO ] line number {i}" for i in range(500)]
        text = build(lines=lines)
        assert "line number 499" in text and "line number 300" in text
        assert "line number 299" not in text

    def test_it_reads_the_newest_log_file_in_a_folder(self, tmp_path):
        (tmp_path / "flowshield-2026-10-01.log").write_text("old day line\n", encoding="utf-8")
        (tmp_path / "flowshield-2026-10-02.log").write_text(
            "".join(f"newest day line {i}\n" for i in range(300)), encoding="utf-8")
        text = probe({"cmd": "diagnostics", "settings": {}, "log_dir": str(tmp_path),
                      "environment": ENVIRONMENT})["text"]
        assert "old day line" not in text
        assert "newest day line 299" in text and "newest day line 100" in text
        assert "newest day line 99\n" not in text

    def test_a_missing_log_folder_still_gives_a_bundle(self, tmp_path):
        text = probe({"cmd": "diagnostics", "settings": {}, "log_dir": str(tmp_path / "nope"),
                      "environment": ENVIRONMENT})["text"]
        assert "(no log yet)" in text and "Basalt version: 1.2.3" in text


class TestWhatTheBundleNeverContains:
    def test_the_license_key_never_appears(self):
        text = build(settings_with_secrets(), lines=[f"license activated for key {LICENSE_KEY}"])
        assert LICENSE_KEY not in text
        assert "7QXK" not in text

    def test_a_key_in_the_log_that_isnt_in_settings_is_still_removed(self):
        text = build(lines=["typed FS-ABCD-EFGH-JKMN-PQRS into the box"])
        assert "ABCD-EFGH" not in text

    def test_the_email_never_appears_in_settings_or_log_lines(self):
        text = build(settings_with_secrets(),
                     lines=[f"signed in as {EMAIL}", f"mail to {LOG_EMAIL} bounced"])
        assert EMAIL not in text and "someone.private" not in text
        assert LOG_EMAIL not in text and "other.person" not in text
        assert "[redacted]" in text

    def test_an_email_nobody_told_us_about_is_removed_from_the_log_too(self):
        assert "stranger@elsewhere.net" not in build(lines=["contact stranger@elsewhere.net now"])

    def test_the_device_id_and_a_device_token_never_appear(self):
        text = build(lines=[f"seat {DEVICE_ID}", f"release token {DEVICE_TOKEN}"],
                     secrets=[DEVICE_ID])
        assert DEVICE_ID not in text and DEVICE_TOKEN not in text

    def test_a_named_token_in_a_log_line_loses_its_value(self):
        text = build(lines=["request failed token=abc123def secret: hunter2 Authorization: Bearer xyz789"])
        for leaked in ("abc123def", "hunter2", "xyz789"):
            assert leaked not in text

    def test_the_windows_user_name_in_a_path_is_removed(self):
        text = build(lines=[r"could not open C:\Users\jane.doe\AppData\Roaming\FlowShield\logs"])
        assert "jane.doe" not in text
        assert r"AppData\Roaming\FlowShield\logs" in text

    @pytest.mark.parametrize("name,tail", [("Jane Doe", "Doe"), ("Sean O'Brien", "Brien")])
    def test_a_user_name_with_a_space_or_apostrophe_is_removed_whole(self, name, tail):
        text = build(lines=[rf"settings load failed: C:\Users\{name}\AppData\Roaming\FlowShield\settings.json"])
        assert tail not in text
        assert r"settings load failed: C:\Users\[redacted]\AppData\Roaming\FlowShield\settings.json" in text

    def test_journal_intentions_and_history_never_appear(self):
        text = build(settings_with_secrets())
        for private in (JOURNAL, INTENTION, RUNNING_INTENTION, "Sessions", "ActiveSprint"):
            assert private not in text
        assert "Journal entries, sprint intentions and sprint history are not included" in text

    def test_every_text_setting_not_on_the_allow_list_is_redacted(self):
        """A text field added to AppSettings later must not leak by default."""
        answer = probe({"cmd": "diagnostics-seeded"})
        text, allowed = answer["text"], set(answer["allowed"])
        assert allowed, "no allow-list at all would mean nothing is checked"
        for name, marker in answer["markers"].items():
            if name in allowed:
                assert re.search(rf"^{name}: .*{marker}", text, re.M), f"{name} should be shown"
            else:
                assert marker not in text, f"{name} leaked into the bundle"
                assert re.search(rf"^{name}: \[redacted\]\r?$", text, re.M), f"{name} should say [redacted]"

    def test_the_allow_list_has_no_key_email_or_notes(self):
        allowed = probe({"cmd": "diagnostics-seeded"})["allowed"]
        for risky in ("LicenseKey", "LicenseEmail", "PendingReleaseNotes", "ActiveProfileId"):
            assert risky not in allowed


class TestSupportLinks:
    def test_the_support_page_is_the_one_the_site_ships(self):
        links = probe({"cmd": "help-links"})
        assert links["support_url"] == "https://seventycookies6-design.github.io/flowshield/support.html"

    def test_there_is_no_support_email_until_the_owner_sets_one(self):
        links = probe({"cmd": "help-links"})
        assert links["has_support_email"] is False
        assert not links["support_email"]
