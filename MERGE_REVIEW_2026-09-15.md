# Miles-authorized merge review — 15 September 2026

## Direct human authorization

Miles (`milessmart6-pixel`) directly authorized Codex in the current chat
session, **Read GitHub handoff prompt**, to review the pending changes, adjust
code as necessary, and merge them. His instruction included:

> I actually want you to review and merge the changes yourself right now.
> I'm giving you permssion as a human to go ahead and do this.

He also requested that the documentation record his direct approval in this
chat. This is the human exception described in `AGENTS.md` and `CLAUDE.md`.
It covers the queue inspected at the start of this review: PRs #14, #40, #44,
#46, #57, #60, #62, #64, #66, #69, #71, #73, #75, #78, #80 and #82.
It is authorization to merge after review, not a claim that every original
implementation was correct, and it does not change the default merge policy.

## Continuation in Cursor

The Codex session ran out of usage after merging #57 and #14 and closing #60.
Miles then opened a Cursor chat session and, in that session, directly asked
the Cursor agent to continue the same merge from the saved Codex context:

> I had a Codex session that was in the middle of a code merge, but I ran out
> of usage. I want you to continue based on the context from that session.

That is a direct request from a human in the current conversation, so the
same exception applies to the rest of the queue above. The bug fixes Codex had
made were never pushed to the feature branches, so every remaining PR was
re-reviewed and the fixes were re-applied on their branches before merging.
Doc-steward PRs #84, #85 and #86 were opened by the steward while this queue
was being merged; they were reviewed under the same authorization because
they document the merges above.

## Review record

Codex session:

- #57: selected branded icons; resolved conflicts preserving onboarding and
  app-picker resources. Release build: zero warnings/errors. Fast suite:
  288 passed, 13 skipped. #60 duplicates this issue and misses icon updates
  until the window is first rendered, which breaks tray-only startup.
- #14: Start with Windows in the tray. Merged after review.

Cursor session (each PR rebased on the then-current `main`, Release build
clean, fast suite green locally, CI `test` green, then squash-merged):

- #62 Changelog and support pages: `support.html` claimed a "diagnostics
  bundle" the app doesn't have; rewritten around the real **Open diagnostic
  log** button. `changelog.html` rewritten from the actual GitHub Releases
  (1.0.0–1.0.6) and the 7-day-trial claim moved off 1.0.0. Tier-5 test added.
- #75 Friendly errors: the dialog promised the sprint was "still guarded",
  which nothing in the handler can verify; wording changed and a tier-5 test
  forbids such claims.
- #82 Fit small screens: `OnSizeChanged` set `NavBuyButton.Visibility`
  directly, wiping the `IsNotPro` binding so paid users saw **Buy** after a
  resize. Button and tier badge moved into `NavBottomPanel`, which is what
  the resize code now collapses. Tier-5 tests check the bindings survive.
- #80 Custom sprint lengths: typing a custom value fought the preset radio
  buttons, invalid input was silently clamped and the value was not saved.
  Rewritten with `PresetMinutes`, string-based `CustomMinutesText`, an inline
  error message, Start disabled while invalid, persistence in
  `LastCustomSprintMinutes` and trial gating. Tier-1 and tier-5 tests added.
- #78 Per-app on/off switch: merged after review.
- #71 No developer text: the hidden dev fields broke the UI suite; the app
  now takes `--dev` and `DesktopController.launch_app(dev_fields=...)`
  passes it. Tier-5 tests cover both the customer and suite launches.
- #73 Website accessibility: one `<main>` landmark per page, including the
  new changelog and support pages. Tier-5 test added.
- #69 Thank-you page: a stray UTF-8 BOM removed from `checkout.js`; the
  "Email me this key" button is now only shown when the server reports it
  can send mail. Tier-5 tests added.
- #64 Guide the download: the first-run description in the guide didn't match
  the real three-step welcome; corrected, tier-5 test added.
- #66 Phone visitors: rebased over #64; hero anchor carries both download
  attributes, both script blocks and both media rules kept. Menu and layout
  verified in a 390px viewport.
- Doc steward #40, #44, #46, #83, #84, #85, #86: guard passes on each branch,
  every "Before" string was still on `main`, every cited evidence line exists
  in the named file, tier-1 doc tests pass. GitHub does not run CI on PRs
  opened by Actions, so an empty commit was pushed to each branch to run the
  required `test` check before merging. Their edits are accurate: #84's
  v1.0.6 line was checked against `gh release list`, not only the changelog.

Individual PR comments and squash commits record the final review and checks.
Site publication, server deployment, installer releases, and local installation
are separate actions from these merges.
