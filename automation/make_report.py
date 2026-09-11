"""
Generate FINAL_REPORT.md from the newest E2E and pytest reports.

    python automation/make_report.py

Reads reports/e2e-*.json and reports/pytest_report.json, and writes
FINAL_REPORT.md at the project root with an embedded screenshot gallery.
Secrets are redacted: only a key's prefix ever reaches the file.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    PROJECT_ROOT,
    REPORT_DIR,
    SCREENSHOT_DIR,
    load_stripe_keys,
    stripe_configured,
    stripe_missing,
)


def redact(value: str, keep: int = 12) -> str:
    """Show enough of a key to identify it, never enough to use it."""
    if not value:
        return "_(not configured)_"
    if len(value) <= keep:
        return "`" + "•" * len(value) + "`"
    return f"`{value[:keep]}{'•' * 18}` _(redacted)_"


def newest(pattern: str) -> Path | None:
    matches = sorted(REPORT_DIR.glob(pattern), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def load(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def relative(path: str | Path) -> str:
    try:
        return Path(path).relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


# ------------------------------------------------------------------ sections

def e2e_section(report: dict) -> str:
    if not report:
        return "_No E2E report found. Run `python automation/e2e_runner.py` first._\n"

    counts = report.get("counts", {})
    lines = [
        f"Run `{report.get('timestamp')}` · {report.get('duration_s', 0)}s · "
        f"**{counts.get('passed', 0)} passed, {counts.get('failed', 0)} failed, "
        f"{counts.get('skipped', 0)} skipped**",
        "",
        "| # | Step | Result | Time |",
        "| --: | --- | --- | --: |",
    ]
    glyph = {"passed": "✅", "failed": "❌", "skipped": "⏭️", "running": "⏳"}
    for step in report.get("steps", []):
        note = step.get("detail") or step.get("error") or ""
        note = note.replace("|", "\\|")[:110]
        lines.append(
            f"| {step['index']} | {step['name']} | {glyph.get(step['status'], '?')} "
            f"{step['status']}{(' — ' + note) if note else ''} | {step['duration_s']}s |"
        )
    return "\n".join(lines) + "\n"


def pytest_section(report: dict) -> str:
    if not report:
        return "_No pytest report found. Run the pytest command in section 6._\n"

    summary = report.get("summary", {})
    tiers = {
        "test_tier1_unit.py": ["Tier 1 — unit", 0, 0, 0],
        "test_tier2_integration.py": ["Tier 2 — server integration", 0, 0, 0],
        "test_tier3_e2e.py": ["Tier 3 — end-to-end UI", 0, 0, 0],
        "test_tier4_adversarial.py": ["Tier 4 — adversarial", 0, 0, 0],
        "test_tier5_regressions.py": ["Tier 5 — regressions", 0, 0, 0],
    }

    for test in report.get("tests", []):
        node = test.get("nodeid", "")
        for filename, row in tiers.items():
            if filename in node:
                outcome = test.get("outcome")
                if outcome == "passed":
                    row[1] += 1
                elif outcome == "failed":
                    row[2] += 1
                else:
                    row[3] += 1
                break

    lines = [
        "| Tier | Passed | Failed | Skipped |",
        "| --- | --: | --: | --: |",
    ]
    for _, (label, passed, failed, skipped) in tiers.items():
        lines.append(f"| {label} | {passed} | {failed} | {skipped} |")

    lines += [
        f"| **Total** | **{summary.get('passed', 0)}** | "
        f"**{summary.get('failed', 0)}** | **{summary.get('skipped', 0)}** |",
        "",
        f"Duration: {report.get('duration', 0):.1f}s · "
        f"{summary.get('total', 0)} tests collected",
    ]

    failures = [t["nodeid"] for t in report.get("tests", []) if t.get("outcome") == "failed"]
    if failures:
        lines += ["", "**Failing tests**", ""]
        lines += [f"- `{node}`" for node in failures]

    return "\n".join(lines) + "\n"


def gallery() -> str:
    # Newest run that actually captured images. Every logger creates a
    # screenshot directory, but the pytest run leaves its own empty — picking
    # purely by mtime lands on that one and reports "no screenshots".
    runs = sorted(
        (d for d in SCREENSHOT_DIR.iterdir() if d.is_dir() and any(d.glob("*.png"))),
        key=lambda p: p.stat().st_mtime,
    )
    if not runs:
        return "_No screenshots captured yet. Run `python automation/e2e_runner.py`._\n"

    # Prefer the newest e2e run; fall back to whatever else has images.
    e2e_runs = [d for d in runs if d.name.startswith("e2e-")]
    latest = (e2e_runs or runs)[-1]
    shots = sorted(latest.glob("*.png"))

    # Listed, not embedded. Screenshots are git-ignored on purpose — the
    # Blocked Apps capture shows the running-process list of the machine that
    # produced it, which has no business in a public repo. Embedding them would
    # also render as broken images for anyone reading this on GitHub.
    lines = [
        f"Captured locally in `{relative(latest)}` — {len(shots)} images, "
        "not committed to the repository.",
        "",
        "| Step | File |",
        "| --- | --- |",
    ]
    for shot in shots:
        label = shot.stem.split("-", 1)[-1].replace("-", " ").strip().capitalize()
        lines.append(f"| {label} | `{shot.name}` |")

    lines += [
        "",
        "Regenerate them any time with `python automation/e2e_runner.py`, or "
        "`python automation/smoke_ui.py` for a quick four-tab sweep.",
    ]
    return "\n".join(lines) + "\n"


def stripe_section() -> str:
    keys = load_stripe_keys()
    if not stripe_configured():
        return (
            "**Status: not configured.** Payment-path steps were skipped, not faked.\n\n"
            f"Missing: {', '.join(f'`{m}`' for m in stripe_missing())}\n\n"
            "Creating the Stripe account is the one step left to a human — registering a\n"
            "financial-services account under a generated identity breaks Stripe's terms,\n"
            "and the secret key never needs to pass through an assistant to be used.\n"
            "`STRIPE_SETUP.md` has the exact click-path; it takes about five minutes.\n\n"
            "Once `.stripe_keys.json` is populated, re-run:\n\n"
            "```\npython automation/e2e_runner.py\n```\n\n"
            "and every skipped step above becomes a real test-mode purchase.\n"
        )

    mode = "TEST" if keys.get("secret_key", "").startswith("sk_test_") else "⚠️ LIVE"
    return "\n".join([
        f"**Status: configured ({mode} mode).**",
        "",
        "| Credential | Value |",
        "| --- | --- |",
        f"| Publishable key | {redact(keys.get('publishable_key', ''))} |",
        f"| Secret key | {redact(keys.get('secret_key', ''), keep=10)} |",
        f"| Price ID | `{keys.get('price_id', '')}` |",
        f"| Webhook secret | {redact(keys.get('webhook_secret', ''), keep=8)} |",
        "",
        "Secret values are redacted here by design — this file is meant to be shareable.",
        "The real values live only in `.stripe_keys.json`, which is git-ignored.",
    ]) + "\n"


# ---------------------------------------------------------------------- main

TEMPLATE = """# FlowShield — build & test report

_Generated {generated}_

---

## 1. What this is

**FlowShield** is a Windows focus-timer and app blocker. Distractions go behind a
shield whose strength you choose per sprint, and finished sprints compound into a
momentum score.

The twist is **escalating shield levels** plus **momentum instead of streaks**:

| Level | Name | Behaviour |
| --- | --- | --- |
| Shield I | Soft | A dismissible full-screen nudge. |
| Shield II | Firm | Blocked apps are closed on sight; the blocklist stays editable. |
| Shield III | Sealed *(Pro)* | Closed on sight **and** the blocklist locks until the timer ends. |

Momentum compounds on completed sprints and *decays* (×0.85 − 2, floored at zero)
on abandoned ones rather than resetting — one bad afternoon should not erase a
month. Every sprint ends with a one-line "what moved?" journal entry.

### Components

| Part | Stack | Location |
| --- | --- | --- |
| Desktop app | .NET 8 WPF, MVVM, DPAPI-encrypted settings | `DesktopApp/` |
| License server | Node.js + Express + SQLite + Stripe | `Server/` |
| Marketing site | Static HTML/CSS/JS, dark glassmorphism | `Website/` |
| Automation suite | Python, pywinauto + Playwright + pytest | `automation/` |

### Free vs Pro

| | Free | Pro — $4.99/mo |
| --- | --- | --- |
| Blocked apps | 3 | Unlimited |
| Shield levels | I, II | I, II, **III Sealed** |
| Sprint length | ≤ 25 min | Any |
| Sleep blocking | — | ✅ |
| Hard kill mode | — | ✅ |
| History | 7 days | Unlimited + momentum analytics |

---

## 2. Stripe configuration

{stripe}

---

## 3. End-to-end run

{e2e}

---

## 4. Test suite

{pytest}

---

## 5. Screenshots

{gallery}

---

## 6. Running it yourself

Start the two services:

```
cd Server && npm install && npm start
```

```
cd Website && python -m http.server 5500
```

Build and launch the app:

```
cd DesktopApp && dotnet build -c Release && dotnet run -c Release
```

Run the automation (it starts the services itself if they aren't already up):

```
python automation/e2e_runner.py
```

```
python -m pytest automation/tests -v --json-report --json-report-file=reports/pytest_report.json
```

Useful flags: `--headless` for the checkout browser, `--skip-build` to reuse the
existing binary. `python automation/smoke_ui.py` captures all four tabs in one pass.

---

## 7. Known limitations

{limitations}

---

## 8. Switching to Stripe live mode

Do this only when you actually intend to charge real cards.

1. **Activate the account.** Live keys require completing Stripe's business and
   bank-details onboarding. Test mode needs none of that.
2. **Recreate the product in live mode.** Price IDs do not cross the test/live
   boundary — toggle to live, create *FlowShield Pro* at $4.99/month, copy the
   new `price_...`.
3. **Swap the credentials** in `.stripe_keys.json` for the `pk_live_` /
   `sk_live_` pair, or set `STRIPE_SECRET_KEY` and friends in the environment
   instead so no secret sits on disk.
4. **Host the webhook somewhere reachable.** `http://localhost:3000/webhook`
   cannot receive live events. Deploy the server, register the public HTTPS URL
   under Developers → Webhooks for `checkout.session.completed`,
   `customer.subscription.updated` and `customer.subscription.deleted`, and use
   that endpoint's signing secret.
5. **Serve both server and site over HTTPS**, and set `WEBSITE_URL` on the
   server so success/cancel URLs point at the deployed site rather than
   localhost.
6. **Re-point the desktop app** — `LicenseServerUrl` and `WebsiteUrl` in
   `AppSettings` default to localhost; ship the production values.
7. **Guard the test suite.** `test_server_is_in_test_mode_when_configured`
   fails against live keys on purpose. Keep it that way; point the suite at a
   test-mode server instead of relaxing the assertion.

Before going live, confirm on a real card that the subscription appears under
Customers → Subscriptions and that a cancellation propagates back to `IsPro`
being cleared in the app within one validation cycle.
"""


LIMITATIONS_BASE = """- **The Stripe account is not created by the automation.** Registering a
  financial-services account under a disposable identity violates Stripe's
  terms, and the registration flow is gated by SMS and bot detection. This is a
  deliberate boundary, not a missing feature — `STRIPE_SETUP.md` covers the
  five-minute manual path.
- **Webhooks cannot reach `localhost` from Stripe's cloud.** `GET /get-license`
  therefore reconciles against the Stripe API directly, so activation does not
  depend on webhook delivery. Run `stripe listen --forward-to
  http://localhost:3000/webhook` to exercise the real webhook path as well; the
  two converge on the same row and both are idempotent.
- **`better-sqlite3` is pinned to v12, not the v9 originally specified.** npm 11
  blocks native install scripts by default; v9 has no prebuild for Node 24 and
  would need a compiler. `db.js` also falls back to the built-in `node:sqlite`
  if the native module is unavailable at all.
- **The blocker's enforcement is conservative by design.** It acts only while a
  sprint or sleep window is active, and never terminates a process on the
  hard-coded critical list (shells, `explorer`, `lsass`, the app itself, and
  common developer tooling). Letting a distraction through is a far cheaper
  failure than killing something that matters.
- **Sealed mode locks the blocklist, not the process.** A determined user can
  still quit FlowShield from Task Manager. Making that genuinely hard needs a
  Windows service and elevation, which is out of scope here.
- **UI tests are slow.** Each launches a clean instance (~15s cold start).
  That's deliberate: sharing an instance breaks isolation because `launch_app()`
  clears stray processes."""


def main() -> int:
    e2e = load(newest("e2e-*.json"))
    pytest_report = load(newest("pytest_report.json")) or load(newest("pytest*.json"))

    limitations = LIMITATIONS_BASE
    if not stripe_configured():
        limitations = (
            "- **The payment path was not executed in this run** because Stripe has no\n"
            "  credentials configured. Those steps are reported as *skipped*, never as\n"
            "  passed. Everything else below ran for real.\n" + limitations
        )

    content = TEMPLATE.format(
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        stripe=stripe_section(),
        e2e=e2e_section(e2e),
        pytest=pytest_section(pytest_report),
        gallery=gallery(),
        limitations=limitations,
    )

    out = PROJECT_ROOT / "FINAL_REPORT.md"
    out.write_text(content, encoding="utf-8")
    print(f"wrote {out} ({len(content):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
