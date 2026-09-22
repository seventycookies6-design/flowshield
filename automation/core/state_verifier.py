"""
Independent verification of app state.

The UI saying "Licence active" only proves the label rendered. These checks read the
DPAPI-encrypted settings file straight off disk and confirm what was actually
persisted — so a cosmetic-only activation would fail the suite.
"""

from __future__ import annotations

import ctypes
import json
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

from config import DPAPI_ENTROPY, SETTINGS_PATH


# ------------------------------------------------------------------- DPAPI

class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> DATA_BLOB:
    buffer = ctypes.create_string_buffer(data, len(data))
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _blob_bytes(blob: DATA_BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def dpapi_unprotect(ciphertext: bytes, entropy: bytes = DPAPI_ENTROPY) -> bytes:
    """
    CryptUnprotectData under the current user.

    This only succeeds for the user account that encrypted the blob, which is
    itself part of what the test asserts: the settings really are user-scoped.
    """
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_blob = _blob(ciphertext)
    entropy_blob = _blob(entropy) if entropy else None
    out_blob = DATA_BLOB()

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(entropy_blob) if entropy_blob else None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError(f"CryptUnprotectData failed (GetLastError={kernel32.GetLastError()})")

    try:
        return _blob_bytes(out_blob)
    finally:
        kernel32.LocalFree(out_blob.pbData)


# ------------------------------------------------------------------ results

@dataclass
class VerificationResult:
    ok: bool
    detail: str
    data: dict | None = None

    def __bool__(self) -> bool:
        return self.ok


# ------------------------------------------------------------- settings file

def read_settings(path: Path | None = None) -> dict:
    """Decrypt and parse the app's settings file. Raises on any failure."""
    path = Path(path or SETTINGS_PATH)
    if not path.exists():
        raise FileNotFoundError(f"settings file not found at {path}")

    envelope = json.loads(_read_past_a_replace(path))
    payload = envelope.get("Data") or envelope.get("data") or ""
    if not payload:
        raise ValueError("settings envelope has no Data field")

    import base64

    raw = base64.b64decode(payload)
    protected = envelope.get("Protected", envelope.get("protected", True))
    plain = dpapi_unprotect(raw) if protected else raw
    return json.loads(plain.decode("utf-8"))


def _read_past_a_replace(path: Path, timeout: float = 2.0) -> str:
    """
    Read a file the app may be swapping out from under us.

    SettingsService.Save writes a .tmp and then File.Replace()s it over
    settings.json, which is the right way to write settings — but during the
    replace the destination cannot be opened, and Windows reports that to a
    reader as a sharing violation, which arrives here as PermissionError. A
    test that checks settings straight after an action is reading during the
    write by design, so retry for a moment before giving up.

    Bounded and short on purpose: a file that is still unreadable after two
    seconds is a real problem and should still fail loudly. A truncated read
    is covered too — File.Replace is atomic, so an empty or half-written file
    means we caught the window rather than that the settings are broken.
    """
    deadline = time.time() + timeout
    last: Exception | None = None
    while True:
        try:
            text = path.read_text(encoding="utf-8")
            if text.strip():
                return text
            last = ValueError("settings file was empty mid-write")
        except (PermissionError, OSError) as exc:
            last = exc
        if time.time() >= deadline:
            raise last if last else OSError(f"could not read {path}")
        time.sleep(0.05)


def settings_is_encrypted(path: Path | None = None) -> VerificationResult:
    """Confirm the settings file is not readable plaintext."""
    path = Path(path or SETTINGS_PATH)
    if not path.exists():
        return VerificationResult(False, f"no settings file at {path}")

    text = path.read_text(encoding="utf-8", errors="replace")
    envelope = json.loads(text)

    if not envelope.get("Protected", envelope.get("protected")):
        return VerificationResult(False, "envelope is not marked as protected")

    # Any of these appearing verbatim would mean the payload leaked in the clear.
    leaks = [token for token in ("LicenseKey", "IsPro", "BlockedApps", "FS-")
             if token in text.replace('"Data"', "")]
    if leaks:
        return VerificationResult(False, f"plaintext settings keys visible on disk: {leaks}")

    return VerificationResult(True, "settings file is a DPAPI-protected envelope")


def verify_dpapi_settings(expected_pro: bool = True,
                          path: Path | None = None) -> VerificationResult:
    """Decrypt settings.json and check the persisted IsPro flag."""
    try:
        settings = read_settings(path)
    except Exception as exc:                       # noqa: BLE001
        return VerificationResult(False, f"could not read settings: {exc}")

    actual = bool(settings.get("IsPro", False))
    if actual != expected_pro:
        return VerificationResult(
            False,
            f"IsPro is {actual}, expected {expected_pro} "
            f"(status={settings.get('LicenseStatus')!r})",
            settings,
        )

    if expected_pro and not settings.get("LicenseKey"):
        return VerificationResult(False, "IsPro is true but no LicenseKey was stored", settings)

    detail = f"IsPro={actual}"
    if settings.get("LicenseKey"):
        detail += f", key={settings['LicenseKey']}"
    if settings.get("LicenseStatus"):
        detail += f", status={settings['LicenseStatus']}"
    return VerificationResult(True, detail, settings)


def verify_blocked_app_persisted(process_name: str,
                                 path: Path | None = None) -> VerificationResult:
    try:
        settings = read_settings(path)
    except Exception as exc:                       # noqa: BLE001
        return VerificationResult(False, f"could not read settings: {exc}")

    names = [(a.get("ProcessName") or "").lower()
             for a in settings.get("BlockedApps", [])]
    if process_name.lower() in names:
        return VerificationResult(True, f"'{process_name}' persisted (list={names})", settings)
    return VerificationResult(False, f"'{process_name}' not in persisted list {names}", settings)


def verify_sleep_window(enabled: bool, start: str | None = None, end: str | None = None,
                        path: Path | None = None) -> VerificationResult:
    try:
        settings = read_settings(path)
    except Exception as exc:                       # noqa: BLE001
        return VerificationResult(False, f"could not read settings: {exc}")

    actual_enabled = bool(settings.get("IsSleepBlockEnabled", False))
    if actual_enabled != enabled:
        return VerificationResult(
            False, f"IsSleepBlockEnabled={actual_enabled}, expected {enabled}", settings)

    problems = []
    for label, expected, key in (("start", start, "SleepBlockStartTime"),
                                 ("end", end, "SleepBlockEndTime")):
        if expected is None:
            continue
        stored = str(settings.get(key, ""))
        # C# serialises TimeSpan as "HH:MM:SS".
        if not stored.startswith(expected):
            problems.append(f"{label}={stored!r} expected to start with {expected!r}")

    if problems:
        return VerificationResult(False, "; ".join(problems), settings)

    return VerificationResult(
        True,
        f"enabled={actual_enabled}, window={settings.get('SleepBlockStartTime')}"
        f" → {settings.get('SleepBlockEndTime')}",
        settings,
    )


# ------------------------------------------------------------------- UI side

def verify_ui_pro_status(desktop_ctrl, expected_pro: bool = True) -> VerificationResult:
    """Check what the Settings page is actually showing."""
    try:
        desktop_ctrl.navigate_to_tab("Settings")
        status = desktop_ctrl.get_license_status_text()
        badge = desktop_ctrl.tier_badge()
    except Exception as exc:                       # noqa: BLE001
        return VerificationResult(False, f"could not read the UI: {exc}")

    shows_pro = "licence active" in status.lower()
    # MainViewModel.TierBadge reads "PURCHASED" once IsPro is true (see also
    # test_tier3_e2e.py's test_a_licence_unlocks_the_locked_app, which already
    # asserts exactly that) — "PRO" was never the shipped word.
    badge_pro = badge.strip().upper() == "PURCHASED"

    if shows_pro != expected_pro:
        return VerificationResult(
            False,
            f"status line reads {status!r} (badge {badge!r}); expected Pro={expected_pro}",
            {"status": status, "badge": badge},
        )

    if expected_pro and not badge_pro:
        return VerificationResult(
            False, f"status says Pro but the tier badge reads {badge!r}",
            {"status": status, "badge": badge})

    return VerificationResult(True, f"status={status!r}, badge={badge!r}",
                              {"status": status, "badge": badge})


def verify_ui_matches_disk(desktop_ctrl) -> VerificationResult:
    """The UI and the encrypted file must agree about the tier."""
    ui = verify_ui_pro_status(desktop_ctrl, expected_pro=desktop_ctrl.is_pro())
    if not ui.ok:
        return ui

    ui_pro = desktop_ctrl.is_pro()
    disk = verify_dpapi_settings(expected_pro=ui_pro)
    if not disk.ok:
        return VerificationResult(
            False, f"UI says Pro={ui_pro} but disk disagrees: {disk.detail}")

    return VerificationResult(True, f"UI and disk agree: Pro={ui_pro}")
