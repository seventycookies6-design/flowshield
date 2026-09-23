# FlowShield — handoff prompt

Paste everything below the line into a new Claude Code session opened in a
clone of the repo — on a new computer, or for a new teammate. Last brought up
to date on 14 September 2026.

---

You're picking up **FlowShield**, a Windows focus timer and app blocker with a
7-day free trial, sold as a one-time $4.99 purchase (no subscription). It's built, released and live; two people now work on it, each
with an AI agent, often at the same time. The repo owner is
**seventycookies6-design** and the teammate is **milessmart6-pixel**. The owner
often talks to their agent from another computer through Remote Control.

Work through the phases below in order and report back briefly after each.
Don't redesign anything that already works.

**Read first:** `CLAUDE.md` (the working rules — Claude Code loads it
automatically, and it wins over anything here), then `README.md`, `DEPLOY.md`,
`SELLING.md` and `FINAL_REPORT.md`. They're accurate.

## What FlowShield is today

A Windows 10/11 x64 app. Pick a sprint length and a shield level, start the
timer, and apps on your blocklist are dealt with until it ends.

- **Shield levels:** Soft (a full-screen notice on the blocked app's screen,
  with Close ‹app›, Back to work and Allow 5 minutes; the app keeps running,
  unless you choose Close), Firm (blocked apps are warned to save their work,
  then closed), Sealed (warned then closed, and the blocklist locks for the
  rest of the sprint — ending the sprint early unlocks it).
- **Momentum score:** a finished sprint adds to it; an abandoned one decays it
  (×0.85 − 2) rather than resetting it. A day streak is shown too.
- **Journal:** a one-line "What moved?" entry after each sprint.
- **Sleep blocking:** a nightly window that closes blocked apps.
- **Trial, then buy once (#29):** every feature is unlocked for 7 days from the
  first launch (`AppSettings.TrialDays`). After that, a lock screen offers
  **Buy FlowShield — $4.99** and licence-key activation, and no sprint can
  start. Buying (a one-time Stripe payment) unlocks everything for good:
  unlimited apps, all three shields, 15–90-minute presets plus custom 5–240-minute
  sprints, sleep blocking, hard kill mode. A full refund revokes the licence. The trial start lives in the
  encrypted settings file, so deleting that file restarts it — accepted, like the
  device cap, as not worth DRM. Licences bought on the old $4.99/month plan keep
  working. `--expire-trial` backdates the trial for the UI tests.

| Part | Where | State |
| --- | --- | --- |
| Desktop app | `DesktopApp/`, .NET 8 WPF, MVVM | **v1.0.9** on GitHub Releases (23 September 2026). Velopack installer (per-user, no admin, self-contained — no .NET needed), in-app update check. Settings DPAPI-encrypted in `%APPDATA%\FlowShield`; the app installs to `%LOCALAPPDATA%\FlowShield`. |
| Licence server | `Server/`, Node 24 + Express + SQLite | Live at https://flowshield-license-server.onrender.com (Render free plan, Docker, `render.yaml`). Sleeps when idle; first request takes ~50 s. |
| Website | `Website/`, static | Live at https://seventycookies6-design.github.io/flowshield/ from the `gh-pages` branch. Redesigned in #27 (teal theme, light/dark toggle, Soft/Firm/Sealed explained through a student's day). Checkout goes through the licence server. |
| Payments | Stripe | **Test mode only.** Account named FlowShield. |
| Tests | `automation/`, pytest + pywinauto + Playwright, tiers 1–7 | 1000+ tests as of 22 September 2026 (`automation/tests -m "not ui and not stripe"` alone: 991 passed, 16 skipped). See Phase 2 for the current baselines. |
| Tools | `tools/` | `setup_stripe_store.js`, `publish_site.ps1`, `build_release.ps1`, `db_admin.js`, `fix_mojibake.py`, and `doc_steward/` (keeps the docs consistent with the code; see "Doc steward" in `CLAUDE.md`) |
| Roadmap | `CUSTOMER_EXPERIENCE_PROMPT.md`, issues #1–#6; `LAUNCH_FEATURE_CHECKLIST.md` and `DESIGN_SYSTEM.md` | A customer's-eye audit (31 problems) and six phases of fixes, plus a launch feature checklist and design system from competitor research (#35). The work is split evenly: Keenan with Claude Code (#37) and Miles with Codex and Cursor (#38); see "Who builds what" in the checklist. 1.1 (site claims) is done and live; 1.2 (Start with Windows in the tray) is done. The file's Progress table is the current status. |

### Installer, as a customer sees it

Tested on a real machine on 13 September 2026: the download is 69.5 MB and
unsigned, so SmartScreen shows **"Windows protected your PC"** with *Publisher:
Unknown publisher* and hides **Run anyway** behind *More info*. Past that, the
install takes about 3 seconds with no admin prompt, adds Start Menu and Desktop
shortcuts and an *Installed apps* entry, launches into the free trial (since #29), and points
at the live licence server.

### Key design facts

- **Stripe is the record; the server's database is only a cache.** Render's free
  disk is wiped on every deploy. The server rebuilds missing rows from Stripe
  (`recoverFromStripe` / `rehydrate`), matching on the licence key in
  the payment's metadata (subscription metadata for old monthly licences) or on
  the customer's email.
- **Licence keys** look like `FS-XXXX-XXXX-XXXX-XXXX`: Crockford base32 with an
  odd-weighted mod-32 checksum.
- **Device cap:** 3 machines per licence (`DEVICE_LIMIT`). The app sends a
  salted SHA-256 device ID (`DeviceIdentity.cs`); `POST /devices` lists or
  releases seats; deactivating releases the seat *before* clearing the key.
- **Email delivery:** code is done (Resend or SMTP), but **no provider is
  configured on Render**, so `/health` reports `email: disabled`.
- **Deploys:** Render uses the public repo URL, so **pushing does not
  auto-deploy**. The owner clicks *Manual Deploy → Deploy latest commit*.
- **The test suite finds the repo from its own location** (`automation/config.py`,
  overridable with `FLOWSHIELD_ROOT`), so a clone works in any folder.
- **Test runs protect the real settings file.** The dev build and an installed
  FlowShield share `%APPDATA%\FlowShield\settings.json`; the suite backs it up
  and restores it (`automation/core/settings_guard.py`). The UI tests still
  close every running FlowShield, including an installed copy.

## How the two of you work

`CLAUDE.md` has the full rules. In short:

1. Every piece of work has a GitHub issue. Claim it (assign yourself) first.
2. Branch from the latest `main` — a worktree per task if you run several —
   keep it small, rebase and run the fast tests before pushing.
3. Open a pull request that closes the issue and fill in the template. Nobody
   pushes straight to `main`.
   - **Only the owner's Claude Code session merges** (after reviewing, with
     *Squash and merge*). Miles's Codex agent — and any other agent — never
     merges unless a human directly asks for that specific merge in its own
     conversation. See "Who merges" in `CLAUDE.md`; Codex gets the same rule
     from `AGENTS.md`.
   - `.github/CODEOWNERS` requests the owner's review on every pull request.
4. One person at a time on things branches don't isolate: Render deploys, the
   `gh-pages` site, GitHub Releases, and the Stripe test account. Say so on the
   issue first.
5. `.stripe_keys.json` is shared privately between the two of you (a password
   manager), never through git or chat.
6. One test run per machine at a time — two runs share ports 3000 and 5500 and
   the app's settings file.

## Rules that always apply

These are in `CLAUDE.md` too; they're repeated because breaking them is costly.

- **Stripe stays in test mode.** Never use or ask for `sk_live_` keys.
  `setup_stripe_store.js` refuses them on purpose.
- **Never type secrets into any field, and never print them in chat.** That
  covers Stripe keys, webhook secrets, Resend/SMTP credentials and passwords.
  Get the page ready and let a person paste.
- **Never commit** `.stripe_keys.json`, `*.db`, `node_modules/`, `bin/`, `obj/`,
  `dist/`, `logs/`, `reports/` or `screenshots/`.
- **Don't archive or delete the old "Focus Unlock Pro" product** in Stripe.
- **Don't edit text files with PowerShell** `Get-Content`/`Set-Content`. Use the
  file edit tools; `python tools/fix_mojibake.py <file>` repairs damage.
- **Don't create accounts or sign in for anyone.** If a page needs a login, ask.
- **Before a Stripe checkout test, confirm test mode.** Test card only:
  4242 4242 4242 4242, 12/34, CVC 123, ZIP 90210.
- End commit messages with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
  (or the line for whichever agent wrote the change). The remote is
  `https://github.com/seventycookies6-design/flowshield.git`.

## Phase 1: Check the environment

1. **Confirm the clone.** `git remote -v` shows the URL above; `git log -1` is at
   or after "Put the owner's settings back after a test run". If the folder
   isn't a clone yet, run `gh repo clone seventycookies6-design/flowshield .` in
   an empty folder. **Don't sync the repo folder with OneDrive or Dropbox**, and
   don't keep several stray copies — work in one clone, with worktrees for
   parallel tasks.
2. **Check the tools.** Install anything missing with `winget` only after the
   person agrees:
   - `dotnet --list-sdks` (8 or newer)
   - `node -v` (18 or newer; production uses 24)
   - `python --version` (3.11 or newer)
   - `git --version`
   - `pwsh -v` (PowerShell 7 — the release and site-publishing scripts need it;
     `winget install Microsoft.PowerShell`)
   - `gh auth status`. If it isn't signed in, ask the person to run
     `gh auth login`, then run `gh auth setup-git`. Use HTTPS; SSH pushes were
     denied before.
3. **If a tool is installed but "not recognized":** it was probably installed
   per-user after the Claude app started, so this session has a stale `PATH`
   (and no `DOTNET_ROOT`, which makes the dev build say "You must install .NET
   Desktop Runtime"). Ask the person to restart the Claude app rather than
   working around it.
4. **Git identity.** If `git config user.name` is empty, ask the person which
   name and email to use — don't guess. The owner's commits use
   `seventycookies6-design <seventycookies6@gmail.com>`.
5. **Stripe keys.** Check whether `.stripe_keys.json` is in the repo root.
   Report only whether it exists and which **field names** it has
   (`secret_key`, `publishable_key`, `price_id`, `webhook_secret`), never the
   values. If it's missing, say so; the Stripe tests will skip, which is
   expected.
6. **Collaboration setup.** Report whether: you can see issues #1–#6
   (`gh issue list`); `main` is protected
   (`gh api repos/seventycookies6-design/flowshield/branches/main/protection`);
   `.github/workflows/ci.yml` exists on `main`; and the teammate has accepted
   the invitation (`gh api repos/seventycookies6-design/flowshield/collaborators --jq '.[].login'`).
   See "Still open" for what to do about each.

## Phase 2: Install, build and test

```bash
cd Server && npm ci
```

```bash
python -m pip install -r automation/requirements.txt
```

```bash
python -m playwright install chromium
```

```bash
cd DesktopApp && dotnet build -c Release
```

Then run the tests in this order and report the counts, with the reason for
every skip:

1. `python -m pytest automation/tests -m "not ui and not stripe" -q` — fast,
   needs nothing external. **Baseline (21 September 2026, with
   `Server/node_modules` installed via `npm ci`): 720 passed, 16 skipped.**
   The older "181 passed, 11 skipped" figure below is stale — the design
   system adoption and adaptive layout work (#171–#191) added several hundred
   tests since 14 September.
2. `python -m pytest automation/tests -m "not ui" -q` — adds the Stripe tiers if
   the keys are present.
3. `python -m pytest automation/tests -q` — the UI tiers drive the real desktop
   app. **Warn the person first: it takes over the mouse, keyboard and screen**
   for about six minutes, and closes any running FlowShield. Old baselines
   (14 September 2026, now well behind the current count): the last full run
   without Stripe keys was **164 passed, 32 skipped** (every skip was
   Stripe), before 51 more non-UI tests were added (settings backup, site
   claims, doc wording, the doc steward and the #21 security fix) — they pass
   in the fast run, so expect 215 passed. With keys, the last full run was 195 passed, 1 skipped,
   on the old computer. Re-baseline both after the next full UI run — with the
   fast-only count now at 720, these are no longer representative.

If something fails here but passed before, look for a machine difference first:
a stale `PATH`, a missing SDK, DPI or scaling, a screen resolution that clips
controls, or another test run or FlowShield already using ports 3000/5500. Fix
real bugs, add a test, and say exactly what you changed.

Also check the live services:

- `https://flowshield-license-server.onrender.com/health` returns `ok` (the first
  request after idle can take ~50 seconds).
- The site returns HTTP 200.
- `gh release view --repo seventycookies6-design/flowshield` shows v1.0.9.

## Phase 3: Remote Control

Only if the person wants to reach this session from another computer. It's
already confirmed working on the owner's current PC. You **can't turn it on
yourself**; walk them through it:

1. **Sign-in check.** `claude auth status` should show `"authMethod":
   "claude.ai"`. If `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` is set, it
   blocks Remote Control. (`ANTHROPIC_BASE_URL` set by the Claude app itself,
   pointing at `api.anthropic.com`, is harmless.)
2. **Turn it on** — recommend the first:
   - **Desktop app:** *Settings → Claude Code → Enable remote control by
     default*. It may only apply to sessions started afterwards.
   - **Terminal:** in the project folder run `claude remote-control` and answer
     `y`; it prints a link and QR code, and the window must stay open.
     `claude remote-control --continue` resumes within about 4 hours.
3. **Connect** from the other computer at https://claude.ai/code, signed into
   the **same account**, and pick the session. If it doesn't appear, refresh,
   and check the account on both sides.
4. **Keep this computer reachable:** ask the person to set *Power & battery →
   Screen and sleep → "When plugged in, put my device to sleep after"* to
   **Never** while working remotely. That's theirs to change, not yours.
5. **Test it:** ask them to send a message from the other computer.

UI tests and screenshots only work while this computer's desktop is unlocked
and on screen. Say so before running tier 3 or the E2E runner remotely.

## Phase 4: Report, then wait

Send a short status: environment, build, test counts, live services,
collaboration setup, and Remote Control on or off. Then list what's open.
**Don't start these yourself** — each needs a person's input, credentials or
go-ahead.

### Still open: collaboration setup

1. **`main` is protected** (done 13 September 2026): pull requests required
   (0 approvals), linear history, no force pushes or deletions, applied to
   admins too; squash merging only, head branches deleted after merge. Check
   with `gh api repos/seventycookies6-design/flowshield/branches/main/protection`.
   Miles has full collaborator access on purpose; the merge rule is followed by
   instruction, not enforced by GitHub.
2. **CI workflow** (on since 13 September 2026). `.github/workflows/ci.yml`
   builds the app and runs the fast tests on Windows for every pull request and
   push to `main`; its `test` check is required before merging. Pull requests
   opened by GitHub Actions (the doc steward's) don't trigger it — check those
   locally.
3. **Doc steward workflow** (on since 13 September 2026).
   `.github/workflows/doc-steward.yml` runs `tools/doc_steward/` after merges to
   `main`, weekly, and on demand. `NVIDIA_API_KEY` is set as an Actions repo
   secret; `OPENROUTER_API_KEY` isn't, so it currently uses NVIDIA's models only.
   Adding the OpenRouter key (`gh secret set OPENROUTER_API_KEY`, pasted by a
   human) enables the OpenRouter fallback. "Allow GitHub Actions to create and
   approve pull requests" is on; default workflow permissions stay read-only.
4. **Teammate access.** milessmart6-pixel accepted the invitation and is
   working in the repo (item 1.1 is pull request #9). The owner shares
   `.stripe_keys.json` with them privately.

### Still open: the product

1. **The roadmap.** `CUSTOMER_EXPERIENCE_PROMPT.md` (see its Progress table)
   and issues #1–#6, split between the owner (#37) and milessmart6-pixel (#38).
   The site no longer advertises unbuilt features (item 1.1, live since
   13 September 2026), and the three gaps once listed here have since shipped:
   F2's escape hatch now gets harder by shield level (#47), the journal can be
   read back (F17, #116), and roadmap 1.4 registers `flowshield://` so the
   thank-you page's "Activate in FlowShield" button works (#51). An overnight
   push (21–22 September 2026, #191 onward) shipped F4 (tray/keyboard start,
   #214), F5 (breaks and study cycles, #230), F7's remaining Soft overlay
   (#224), F9 (blocklist profiles, #233), F16 (history and a weekly view,
   #217), F20 and F23 (#213, #211), F21 (light theme, keyboard use and
   accessibility, #237), and the server roadmap's 5.2 (#225) and 5.7 (#229).
   What's genuinely still open, per #37/#38 (reviewed 22 September 2026): on
   the owner's side, F6 (templates/schedules), F14 (milestones, #133, now
   unblocked by F16), roadmap 4.1 (updates) and 5.1 (buy in-app); on Miles's
   side, F22 shipped (calm Settings, #253); still open there is
   roadmap 5.5 (email-only unlock, needs an
   email provider), 3.7 (sleep schedule, needs F6), 4.3 (in-app Get help),
   the #144 capture refresh (now that the visual language and features have
   landed), bugs #203/#204, #234 (device-token HMAC), History list
   virtualisation, and the F25/owner gates.
2. **Stripe business name** (owner; found in a test purchase on 13 September
   2026). Checkout and the billing portal show "Focus Unlock sandbox". The
   sandbox and its parent account are both named FlowShield (the parent was
   renamed from "Focus Unlock" the same day, which did not change checkout); the
   displayed name comes from the public business profile, which Stripe only
   lets you edit through its full business onboarding (Settings → Business →
   Business details → "Add business information"). Owner task. Already fixed the same day, and verified on a fresh checkout and
   billing portal: the portal's plan switching is off, so the old **Focus Unlock
   Pro** ($9.99) is no longer offered (the product itself is untouched), and the
   FlowShield Pro description now lists only shipped features.
3. **Email delivery.** The owner creates a Resend API key or a Gmail app-password
   SMTP URL and pastes it into Render → Environment (`RESEND_API_KEY` or
   `SMTP_URL`, plus `EMAIL_FROM`), then *Manual Deploy*. Confirm with `/health`
   that `email.configured` is `true`.
4. **Legal pages.** `Website/legal.html` still shows a draft banner and
   placeholders: operator name, address, support email. Once the owner provides
   them, fill them in and republish with `pwsh tools/publish_site.ps1`.
5. **Launch gates** (`SELLING.md`): Stripe account activation, completed legal
   pages, a support email. Recommended: a code-signing certificate (removes the
   SmartScreen wall — the biggest drop-off), a domain, and Render's paid plan.
6. **Going live on Stripe** comes last, and only when the owner explicitly asks.
   `SELLING.md` → "Going live on Stripe".
7. **Known weaknesses:** an email address alone activates a licence (but, since #21, no
   longer reveals the key, opens the billing portal or touches devices); no
   crash reporting; tested on one Windows 11 x64 machine.

## Useful commands

```
pwsh tools/build_release.ps1 -Version 1.0.4 -Publish   # new release + auto-update feed (one person, from main)
pwsh tools/publish_site.ps1                            # publish Website/ to gh-pages (one person, from main)
node tools/db_admin.js list                            # inspect the local licence DB
python automation/e2e_runner.py                        # full end-to-end run (headless; --headed to watch)
python automation/smoke_ui.py                          # screenshot every tab
python automation/verify_deployed.py                   # check the live site + server
python automation/make_report.py                       # regenerate FINAL_REPORT.md
```

After any change to `Server/`: merge the pull request, ask the owner to click
*Manual Deploy* on Render, then run `python automation/verify_deployed.py`.
