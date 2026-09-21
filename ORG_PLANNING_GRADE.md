# FlowShield — organization & planning grade

**For:** Keenan (`seventycookies6-design`) and Miles (`milessmart6-pixel`)  
**Date:** 20 September 2026  
**Author:** Miles’s Cursor agent (Composer), from a live checkout of `main` plus open GitHub issues/PRs  
**Tracking:** #152

A snapshot grade of how the repo is organized and how planning is kept — not a
product roadmap rewrite. Scores are judgement calls against what a two-person,
dual-agent team needs to ship without stepping on each other.

---

## Scores

| Dimension | Score | Notes |
| --- | --- | --- |
| Code layout | **8.5 / 10** | Clear product folders; small Server surface; design tokens pipeline |
| Agent process | **9.5 / 10** | Best-in-class dual-agent rules in `CLAUDE.md` / `AGENTS.md` |
| Planning content | **8.5 / 10** | Launch checklist, CX audit, design system, selling/legal honesty |
| Planning freshness | **5.5 / 10** | Multiple overlapping trackers; phase epics and CX Progress drift |
| Issue hygiene | **6.5 / 10** | Excellent issue bodies when written; weak labels/milestones |
| Test & CI structure | **9.0 / 10** | Tiers 1–7, fast vs UI split, PR template, claims tests |

**Overall:** organization and agent process are A-grade. Planning *content* is
strong; planning *freshness* and issue hygiene are where agent time is wasted.

---

## What is working well

- Top-level split is clean: `DesktopApp/` · `Server/` · `Website/` · `automation/` · `tools/` · `design/`.
- Claim → branch from `main` → PR → owner-merge rules keep two agents from colliding.
- `LAUNCH_FEATURE_CHECKLIST.md` → “Who builds what” matches tools to work (Claude Code vs Codex/Cursor) with effort balance.
- Tiered tests, PR template, token generator, legal/selling honesty, deliberate timid blocker.
- Individual work issues (e.g. #143, #147) are unusually precise: problem, scope exclusions, sequencing, acceptance.

---

## Where improvement matters

1. **Four overlapping trackers** — `CUSTOMER_EXPERIENCE_PROMPT.md`, the launch checklist, phase epics #1–#6, and person trackers #37/#38. They disagree on what’s done.
2. **Stale phase / Progress checklists** — Phase #1 still shows 1.2–1.15 unchecked while many of those items are done and closed elsewhere. The CX Progress table still says “Everything else · Not started” despite substantial shipped work.
3. **Doc-steward PR pile-up** — multiple open PRs titled the same (“Keep docs consistent with the code”). The steward invents work faster than it is reviewed.
4. **Labels and milestones** — most active work issues have no labels; no Launch milestone on GitHub.
5. **Historical root docs** — agents can treat `FINAL_REPORT.md` / old handoffs as current unless told otherwise.

---

## Recommended improvements (priority)

| Priority | Change | Why |
| --- | --- | --- |
| **P0** | Pick one live tracker | Make #37/#38 + `LAUNCH_FEATURE_CHECKLIST.md` the only checklists. Close or archive phase epics #1–#6 once items are mirrored, or auto-sync them when child issues close. |
| **P0** | Drain the doc-steward PR queue | Close duplicates; merge one green steward PR; raise the bar so a new run cannot open while previous ones sit open. |
| **P1** | Labels + a Launch milestone | Require `bug` / `design` / `feature` / `blocked` / `owner-decision` on every work issue. |
| **P1** | CX Progress as a pointer or generated table | Stop hand-maintaining a second progress list that goes stale. |
| **P2** | Park historical root docs | Move `FINAL_REPORT.md`, `MERGE_REVIEW_*`, stale handoff copies into something like `docs/archive/` so agents stop treating them as current. |
| **P2** | Model hint on issues | One-line “Preferred agent/model” on new issues (already implied in Who builds what — make it per-issue). |

---

## Model routing note (September 2026)

Ownership in “Who builds what” still fits. Update the model *inside* each toolkit:

| Role | Model | Use on FlowShield |
| --- | --- | --- |
| Default coding | **Claude Opus 5** | Most WPF / blocker / server / PR work (Claude Code default) |
| Hard escalate | **Claude Fable 5.1** | Multi-day / whole-app runs (design-system adoption, F16+F14) |
| Codex flagship | **GPT-6 Astra** | Harder autonomous Codex PRs once rolled out to the seat |
| Codex workhorse | **GPT-5.6 Sol** | Volume site / tests / bugs until Astra is everywhere |
| Cheap bulk | **Gemini 3.8 Flash** | Checklist sync, strategy drafts — Gemini 4 is still pre-training |
| Visual loop | **Composer 2.5 + Sonnet 5** | Icons, charts, “does this look right?” |

March 2026 names (Opus 4.6, GPT-5.3 Codex, Gemini 3.1 Pro) are obsolete for routing.

---

## Bottom line

Do not add more process docs until the single source of truth and the
doc-steward pile-up are fixed. The rules and folder layout are already good
enough to ship; freshness is the soft spot.

This file is a dated snapshot. It is not the launch checklist and should not
be edited to track feature progress — tick boxes live in
`LAUNCH_FEATURE_CHECKLIST.md` and issues #37 / #38.
