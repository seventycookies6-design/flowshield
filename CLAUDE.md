# FlowShield — rules for every agent and person working here

Two people work on this repo, each with their own AI agent, often at the same
time. These rules are what keep that from producing conflicting versions.
Read `README.md` for what the product is; `SELLING.md`, `DEPLOY.md` and
`FINAL_REPORT.md` are accurate background. `CUSTOMER_EXPERIENCE_PROMPT.md` is
the current roadmap.

## How work flows

1. **Claim before you start.** Every piece of work has a GitHub issue. Assign it
   to yourself (`gh issue edit <n> --add-assignee @me`) before writing code. If
   it's already assigned to someone else, pick something else or ask.
2. **Start from the latest `main`, on a branch.** Never commit to `main`; it is
   protected and only accepts pull requests.

   ```bash
   git fetch origin
   git switch -c feat/<short-name> origin/main
   ```

   Running several tasks at once on one machine? Give each its own worktree
   instead of switching branches under a running agent:

   ```bash
   git worktree add ../FlowShield-<short-name> -b feat/<short-name> origin/main
   ```

3. **Keep branches small and short-lived.** One issue, one pull request,
   merged the same day where possible. Long branches are where conflicts come
   from.
4. **Before pushing:** rebase on the latest `main`, build, and run the fast
   tests (commands below). Fix what breaks; don't push red.

   ```bash
   git fetch origin
   git rebase origin/main
   ```

5. **Open a pull request** that closes the issue (`Closes #<n>`) and fill in the
   template. CI must pass before merging. Merge with *Squash and merge*; the
   branch is deleted automatically.
6. **Hit a conflict?** Rebase, resolve it by keeping both people's intent, rerun
   the tests. Never resolve a conflict by discarding someone else's change, and
   never force-push to a branch you didn't create.

## Shared things that exist only once

Branches don't isolate these. Changing them affects both of you and every
customer, so **say so on the issue first and do one at a time**:

| Resource | Who acts | How |
| --- | --- | --- |
| Licence server on Render | The repo owner clicks *Manual Deploy* | Merge the `Server/` change first; pushing does not deploy |
| Published site (`gh-pages`) | One person per publish | `pwsh tools/publish_site.ps1` from an up-to-date `main` |
| GitHub Releases / auto-update feed | The repo owner, or whoever they name | `pwsh tools/build_release.ps1 -Version x.y.z -Publish` from an up-to-date `main` |
| Stripe test account | Anyone, test mode only | Don't rename or delete products; don't archive "Focus Unlock Pro" |

## Rules that always apply

- **Stripe stays in test mode.** Never use or ask for `sk_live_` keys.
- **Never commit secrets, and never print or type them.** `.stripe_keys.json`
  is shared between people privately (a password manager), never through git
  or chat. Dashboards that need a secret get prepared, then a person pastes it.
- **Never commit** `.stripe_keys.json`, `*.db`, `node_modules/`, `bin/`, `obj/`,
  `dist/`, `logs/`, `reports/` or `screenshots/`.
- **Don't edit text files with PowerShell** `Get-Content`/`Set-Content`; it has
  corrupted UTF-8 here before. Use file edit tools. `python tools/fix_mojibake.py
  <file>` repairs damage.
- **Don't create accounts or sign in for anyone.**
- **The blocker stays deliberately timid:** never close anything on
  `AppBlockerService.CriticalProcesses`, no admin rights, drivers, services or
  hosts-file edits.
- **Never claim a feature the shipped build doesn't have** — on the site, in the
  app or in emails.
- **Every behaviour change gets a test** in the matching tier; regressions go in
  tier 5 and must fail without the fix. Keep existing `AutomationId`s.
- End commit messages with a `Co-Authored-By:` line for the agent that wrote the
  change.

## Commands

```bash
cd Server && npm ci
```

```bash
python -m pip install -r automation/requirements.txt
```

```bash
cd DesktopApp && dotnet build -c Release
```

Fast tests — no screen takeover, no Stripe keys needed. CI runs exactly this:

```bash
python -m pytest automation/tests -m "not ui and not stripe" -q
```

Full suite — **takes over the mouse, keyboard and screen** for several minutes:

```bash
python -m pytest automation/tests -q
```

## One test run per machine

Two worktrees on the same PC share more than it looks: the licence server port
(3000), the site port (5500), and the app's settings in `%APPDATA%\FlowShield`.
The suite reuses a server already listening on port 3000 — which may be the
*other* worktree's code — and closes every running FlowShield before each UI
test. Run one suite at a time per machine.

Test runs back up and restore the real settings file through
`automation/core/settings_guard.py`. Any new script that launches the app must
wrap its entry point in `preserve_user_settings()`.

## Windows notes

- .NET, Node, Python and gh may be installed per-user. A shell or app opened
  before an install won't see them on `PATH` until it is restarted.
- `%APPDATA%\FlowShield` holds settings and logs; `%LOCALAPPDATA%\FlowShield` is
  the installed app. An installed copy and the dev build share the settings
  file.
