# FlowShield — organization & planning grade (regrade)

**For:** Keenan (`seventycookies6-design`) and Miles (`milessmart6-pixel`)  
**Date:** 21 September 2026  
**Previous:** [`ORG_PLANNING_GRADE.md`](ORG_PLANNING_GRADE.md) (20 Sep 2026, #152 / #153)  
**Author:** Miles’s Cursor agent (Composer), from `origin/main` plus open GitHub issues/PRs  
**Tracking:** #158

A second snapshot after the planning cleanup (#155) and the design / F7 landings
that followed. Same dimensions as the first grade. Not a live checklist —
`PLANNING.md` names the two places that are.

---

## Scores

| Dimension | 20 Sep | **21 Sep** | Delta | Notes |
| --- | ---: | ---: | --- | --- |
| Code layout | 8.5 | **9.0** | +0.5 | `PLANNING.md` makes “where does this go?” obvious |
| Agent process | 9.5 | **9.5** | — | Unchanged; still best-in-class dual-agent rules |
| Planning content | 8.5 | **9.0** | +0.5 | One live tracker + audit kept as reasoning, not status |
| Planning freshness | 5.5 | **8.0** | +2.5 | P0 fixed; person issues #37/#38 still lag the checklist |
| Issue hygiene | 6.5 | **7.0** | +0.5 | Phase epics closed; labels / Launch milestone still missing |
| Test & CI structure | 9.0 | **9.0** | — | Tiers, PR template, claims tests still strong |

**Overall:** organization remains A-grade. Planning freshness jumped from the
weakest dimension to a clear strength. Remaining drag is issue metadata and
keeping #37/#38 in step with the checklist.

---

## What is working well

- Top-level split unchanged and clear: `DesktopApp/` · `Server/` · `Website/` · `automation/` · `tools/` · `design/`.
- Claim → branch → PR → owner-merge rules still prevent dual-agent collisions.
- **`PLANNING.md`** (shipped in #155) is the missing map: two live places, what
  stopped being a tracker, where each kind of change goes.
- Launch checklist remains the feature source of truth; CX prompt is correctly
  demoted to audit / reasoning with a frozen pre-checklist block.
- Phase epics #1–#6 are **closed**, with pointers to the live trackers.
- Doc steward **waits** while a steward PR is open; the eight-deep queue was
  drained rather than ignored (only #157 open at regrade time).
- Design system moved from “doc ahead of code” toward adoption: Inter as one
  family + structural accent (#149), Lucide nav icons (#151).
- Product progress since the first grade: F7 1.8 graceful close (#146), F14
  explainer + trend (#132), F24/F26 (#124), F27 captures (#139), capture-kit
  hygiene (#141/#145).
- Individual work issues remain high quality when opened (#147, #143).

---

## What still hurts

1. **Person trackers lag** — #38’s body still lists Syne, unticked F24/F26/F27,
   and an outdated “next up” list after those items shipped. Checklist wins on
   *what shipped*; the issue is supposed to win on *what is next* — today it
   does neither cleanly.
2. **No labels / no Launch milestone** — open work issues are still mostly
   unlabeled; GitHub milestones remain empty. Filtering “what’s left for
   launch” still means reading Markdown.
3. **Partial-ship issues stay open with old titles** — e.g. #143 still reads as
   full F7 (1.8) after 1.8 landed in #146; Soft overlay is what remains.
4. **Historical root docs** — still present (correctly marked historical); fine
   if agents read `PLANNING.md` first, costly if they don’t.
5. **One steward PR in flight** — mechanism working; still needs human review
   so the skip doesn’t look like silence forever.

---

## Improvements

### Fixed since the 20 Sep grade (do not re-open)

| Was (P0/P1) | What landed | Evidence |
| --- | --- | --- |
| Four overlapping trackers | Two live places only | `PLANNING.md`; CX Progress table removed; #1–#6 closed |
| Stale phase / Progress checklists | Epics closed; CX is audit-only | #154 / #155 |
| Doc-steward PR pile-up | Per-merge run skips while a steward PR is open; queue drained | #155; closed steward PRs #101–#142; one open (#157) |
| Grade invisible to Keenan | First grade on `main` | #153 → `ORG_PLANNING_GRADE.md` |

### Still worth doing (priority)

| Priority | Improvement | Why now | Suggested owner |
| --- | --- | --- | --- |
| **P0** | Refresh #37 and #38 against the checklist | “What is next” is wrong on #38; agents will follow the stale list | Miles (own issue); Keenan for #37 |
| **P1** | Labels + a **Launch** milestone | Filtering launch work still requires opening Markdown | Either; one-time setup |
| **P1** | Retitle / retarget partial issues (#143 → Soft overlay only; #133 → milestones only) | Titles that describe shipped work confuse claim/assign | Whoever owns the leftover |
| **P2** | Tick design-system adoption boxes that #149/#151 actually closed | Checklist “Who builds what” still says Syne for §3 | Miles, in the next design PR |
| **P2** | Point README “latest grade” at this file | Avoid agents citing the 20 Sep scores as current | This PR |
| **P3** | Optional `docs/archive/` for `FINAL_REPORT` / `MERGE_REVIEW_*` | Only if root clutter keeps confusing agents after `PLANNING.md` | Keenan call |

### Product / process improvements the grade surfaces (not org debt)

These are not folder/process problems, but they are what the open queue says
launch still needs:

1. **Finish F7** — Soft overlay (#143), sequenced after design refinement (#147).
2. **F14 milestones** — wait on Keenan’s F16 History (#133).
3. **Capture refresh (#144)** — after remaining visual language lands.
4. **Owner gates** — F25 code signing, Stripe activation, legal placeholders
   (`SELLING.md` / `LEGAL_CHECKLIST.md`); no agent can close these alone.
5. **Keenan queue** — F4–F6, F9, F16, purchase-flow 5.x still the long pole for
   “sprints worth coming back to.”

---

## Model routing (September 2026 — unchanged advice)

| Role | Model | Use on FlowShield |
| --- | --- | --- |
| Default coding | **Claude Opus 5** | Most WPF / blocker / server / PR work |
| Hard escalate | **Claude Fable 5.1** | Multi-day / whole-app agent runs |
| Codex flagship | **GPT-6 Astra** | Harder autonomous Codex PRs when on the seat |
| Codex workhorse | **GPT-5.6 Sol** | Volume site / tests / bugs |
| Cheap bulk | **Gemini 3.8 Flash** | Sync / strategy drafts |
| Visual loop | **Composer 2.5 + Sonnet 5** | Icons, layout, “does this look right?” |

Ownership split (Keenan = Claude Code, Miles = Codex + Cursor) still matches.

---

## Bottom line

The 20 Sep P0s were the right call and they shipped within a day. Planning is
no longer the soft spot — **keeping the person issues honest** and **adding
light GitHub metadata** are the next cheap wins. Do not invent a third tracker.

This file is a dated snapshot. Tick boxes live in `LAUNCH_FEATURE_CHECKLIST.md`
and order-of-work on #37 / #38. See `PLANNING.md`.
