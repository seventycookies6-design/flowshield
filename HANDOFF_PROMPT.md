# FlowShield — handoff prompt

Paste everything below the line into a new Claude Code session on the new
computer, opened in the project folder.

---

You're picking up an existing project called **FlowShield** on a new Windows
computer. An earlier Claude Code session on a different computer built all of
it. The owner will mostly talk to you **from that other computer through Remote
Control**, so part of your job is getting Remote Control set up. Work through
the phases below in order. Report back briefly after each one. Don't redesign
anything that already works.

## What FlowShield is

A Windows focus timer and app blocker, sold as a subscription.

- **Shield levels**: Soft (a nudge you can dismiss), Firm (blocked apps are closed), Sealed (Pro only: closed, and the blocklist is locked until the timer ends).
- **Momentum score**: an abandoned sprint lowers it instead of resetting it to zero.
- **Journal**: a one-line entry after each sprint.

| Part | Where | State |
| --- | --- | --- |
| Desktop app | `DesktopApp/`, .NET 8 WPF, MVVM | Released as **v1.0.1** on GitHub Releases. Velopack installer and auto-update. Settings are DPAPI-encrypted in `%APPDATA%\FlowShield`. |
| Licence server | `Server/`, Node 24 + Express + SQLite | Live at https://flowshield-license-server.onrender.com (Render free plan, Docker, `render.yaml`) |
| Website | `Website/`, static | Live at https://seventycookies6-design.github.io/flowshield/, served from the `gh-pages` branch |
| Payments | Stripe | **Test mode only.** The Stripe account is named FlowShield. |
| Tests | `automation/`, pytest + pywinauto + Playwright, tiers 1–7 | Last full run: **195 passed, 1 skipped, 0 failed**. E2E runner 17/17. |
| Tools | `tools/` | `setup_stripe_store.js`, `publish_site.ps1`, `build_release.ps1`, `db_admin.js`, `fix_mojibake.py` |

Read `README.md`, `DEPLOY.md`, `SELLING.md` and `FINAL_REPORT.md` before
changing anything. They are accurate and cover the design reasons.

Key design facts:

- **Stripe is the record; the server's database is only a cache.** Render's free disk is wiped on every deploy. The server rebuilds missing rows from Stripe (`recoverFromStripe` / `rehydrate`), matching on the licence key in subscription metadata or on the customer's email.
- **Licence keys** look like `FS-XXXX-XXXX-XXXX-XXXX`: Crockford base32 with an odd-weighted mod-32 checksum.
- **Device cap**: 3 machines per licence (`DEVICE_LIMIT`).
  - The app sends a salted SHA-256 device ID (`DeviceIdentity.cs`).
  - `POST /devices` lists or releases seats.
  - Deactivating in the app releases the seat *before* it clears the key.
- **Checkout**: the site uses the licence server when `Website/config.js` sets `licenseServerUrl`, and falls back to the Stripe Payment Link otherwise.
- **Email delivery**: code is done (Resend or SMTP), but **no provider is configured on Render yet**, so `/health` reports `email: disabled`.
- **Deploys**: Render uses the public repo URL, so **pushing does not auto-deploy**. The owner has to click *Manual Deploy → Deploy latest commit* in the Render dashboard.

## Rules that carried over (keep following them)

- **Stripe stays in test mode.** Never use or ask for `sk_live_` keys. `setup_stripe_store.js` refuses them on purpose.
- **Never type secrets into any field**, and never print them in chat. That covers Stripe keys, webhook secrets, Resend/SMTP credentials and passwords. When a secret has to go into a dashboard (Render, etc.), get the page ready and let the owner paste it. Secrets live only in `.stripe_keys.json` (gitignored) and in Render's environment settings.
- **Never commit `.stripe_keys.json`**, `*.db`, `node_modules/`, `bin/`, `obj/`, `dist/` or `screenshots/`. `publish_site.ps1` checks for leaked secrets before it publishes.
- **Don't archive or delete the old "Focus Unlock Pro" product** in Stripe. It has real subscription records.
- **Don't edit text files with PowerShell** `Get-Content`/`Set-Content`. It has corrupted UTF-8 in this repo several times. Use the file edit tools. If you see mojibake, `python tools/fix_mojibake.py <file>` repairs it.
- **Don't create accounts or sign in for the owner.** If a browser page needs a login, ask them to do it.
- **Before running a Stripe checkout test, confirm Stripe is in test mode.** Only use the test card: 4242 4242 4242 4242, 12/34, CVC 123, ZIP 90210.
- End commit messages with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. The git remote is `https://github.com/seventycookies6-design/flowshield.git`.

## Phase 1: Check the environment

1. Confirm you're in a clone of the repo:
   - `git remote -v` should show the URL above.
   - `git log -1` should be at or after "Refresh the report for v1.0.1".
   - If the folder isn't a clone yet, run `gh repo clone seventycookies6-design/flowshield .` in an empty folder.
2. Check which tools are installed. Install anything missing with `winget` only after the owner agrees:
   - `dotnet --list-sdks` (needs 8 or newer; 10 works)
   - `node -v` (needs 18 or newer; production uses 24)
   - `python --version` (needs 3.11 or newer)
   - `git --version`
   - `gh auth status`: if it isn't signed in, ask the owner to run `gh auth login` themselves, then `gh auth setup-git`. Pushing over SSH was denied before, so use HTTPS.
3. Check that `.stripe_keys.json` is in the repo root. It has to be copied over by hand; it is not in git.
   - Report only whether it exists and which **field names** it has (`secret_key`, `publishable_key`, `price_id`, `webhook_secret`). Never report the values.
   - If it's missing, say so. The Stripe test tiers will skip, which is expected.
4. Check whether the previous chat was carried over. It would be under `%USERPROFILE%\.claude\projects\<encoded project path>\06af84ff-9b8a-436b-93b0-a7039dbff65f.jsonl`. It's optional, and this prompt is enough either way.

## Phase 2: Install, build and test

```
cd Server; npm install
pip install pywinauto pyautogui playwright pillow requests psutil colorama pytest pytest-json-report
python -m playwright install chromium
cd DesktopApp; dotnet build -c Release
```

Then run the tests in this order and report the counts:

1. `python -m pytest automation/tests -m "not ui and not stripe" -q`: fast, needs nothing external.
2. `python -m pytest automation/tests -m "not ui" -q`: adds the Stripe tiers, if the keys are present.
3. `python -m pytest automation/tests -q`: the UI tiers drive the real desktop app. Warn the owner first, because this takes over the screen.

If something fails on this computer but passed before, look for a machine difference first: paths, DPI or scaling, a missing SDK, or a screen resolution that clips controls. The earlier baseline was 195 passed. Fix real bugs and say exactly what you changed.

Also check that the live services are up:

- `https://flowshield-license-server.onrender.com/health` should return `ok`. The first request after the server has been idle can take about 50 seconds.
- The site should return HTTP 200.
- `gh release view --repo seventycookies6-design/flowshield` should show v1.0.1.

## Phase 3: Remote Control

The owner wants to send you instructions from their other computer. You
**can't turn Remote Control on yourself**: it needs a one-time confirmation
from the owner and a claude.ai login. Walk them through it:

1. **Sign-in check.** Remote Control needs a claude.ai subscription login, not an API key.
   - If `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or a custom `ANTHROPIC_BASE_URL` is set, tell the owner it will block Remote Control.
   - Tell them to run `claude auth login` and choose the claude.ai option if they aren't signed in.
2. **Turn it on.** Explain the choices and recommend the first:
   - **Desktop app, simplest**: *Settings → Claude Code → Enable remote control by default*. After that, every session on this computer, including this one, can be reached from claude.ai/code.
   - **Terminal server mode**: in the project folder, run `claude remote-control` and answer `y`. It prints a session URL and a QR code; press space to show or hide the QR code. The window has to stay open. If it stops, `claude remote-control --continue` in the same folder brings the session back within about 4 hours.
   - **Inside an interactive CLI session**: type `/remote-control FlowShield` (or `/rc`). Typing it again shows the URL or disconnects.
3. **Connect from the other computer**: open https://claude.ai/code signed into the same account and pick the session from the list. The Claude desktop or mobile app also works.
4. **Keep this computer reachable.** Remote Control reconnects after sleep, but a sleeping PC can't do any work.
   - Ask the owner to set Windows *Power & battery → Screen and sleep → "When plugged in, put my device to sleep after"* to **Never** while they're working remotely. Changing system settings is theirs to do, not yours.
   - In the desktop app, you can also request keep-awake for long tasks.
5. **Test the connection**: ask the owner to send a message from the other computer, and confirm you received it.

UI tests and screenshots only work while this computer's desktop is unlocked
and showing on screen. Remind the owner of that before running tier 3 or the
E2E runner remotely.

## Phase 4: Report, then wait

Send a short status: environment, build, test counts, live services, and
Remote Control on or off. Then list what's still open. **Don't start these
yourself.** Each one needs the owner's input or credentials:

1. **Email delivery.** The owner creates a Resend API key or a Gmail app-password SMTP URL and pastes it into Render → Environment (`RESEND_API_KEY` or `SMTP_URL`, plus `EMAIL_FROM`). Then *Manual Deploy*. Confirm with `/health` that `email.configured` is `true`.
2. **Legal pages.** `Website/legal.html` still has placeholders: operator name, address, support email. Once the owner provides the details, fill them in and republish with `pwsh tools/publish_site.ps1`.
3. **Launch gates** (from `SELLING.md`): Stripe account activation, completed legal pages, a support email.
   - Recommended but not required: a code-signing certificate (removes the SmartScreen warning; biggest impact), a domain, and Render's paid plan (so the server doesn't sleep).
4. **Going live on Stripe** comes last, and only when the owner explicitly asks. `SELLING.md` → "Going live on Stripe" has the steps: recreate the product in live mode, re-register the webhook, swap the keys in Render.
5. **Known weaknesses** the owner may want tackled: an email address alone unlocks Pro; no crash reporting; tested only on one Windows 11 x64 machine. This new computer is a good chance to test the installer on a clean machine:
   - Download `FlowShield-win-Setup.exe` from the latest release.
   - Install it and activate it.
   - Report what SmartScreen shows.

## Useful commands

```
pwsh tools/build_release.ps1 -Version 1.0.2 -Publish   # new release + auto-update feed
pwsh tools/publish_site.ps1                            # publish Website/ to gh-pages
node tools/db_admin.js list                            # inspect the local licence DB
python automation/e2e_runner.py                        # full end-to-end run (headless; --headed to watch)
python automation/verify_deployed.py                   # check the live site + server
python automation/make_report.py                       # regenerate FINAL_REPORT.md
```

After any change to `Server/`: commit, push, and ask the owner to click Manual
Deploy on Render. Then re-run `python automation/verify_deployed.py`.
