# Where to look, and where to write things down

**Changed 20 September 2026.** Four documents were tracking progress and
disagreeing with each other. Now two do. This explains which is which, so
nobody has to guess where a tick belongs.

Written for Miles and his agents as much as for anyone here; nothing about how
work flows has changed, only where its state is recorded. `CLAUDE.md` (and
`AGENTS.md`, which points at it) still owns the rules.

## The two live places

| Where | What it holds | Who edits it |
| --- | --- | --- |
| **`LAUNCH_FEATURE_CHECKLIST.md`** | Every launch feature F1–F27: what it is, why, the build steps, and a `- [x] Done` ticked with the pull request that shipped it. Also "Who builds what". | Whoever ships the feature, in the same pull request |
| **Issues [#37](https://github.com/seventycookies6-design/flowshield/issues/37) (Keenan) and [#38](https://github.com/seventycookies6-design/flowshield/issues/38) (Miles)** | The live order of work per person, and the running conversation about it | Either person, or their agent |

If those two disagree, the checklist wins on *what shipped* and the issue wins
on *what is next*.

## What stopped being a tracker

- **`CUSTOMER_EXPERIENCE_PROMPT.md`** — the original audit of the product as a
  customer met it on 13 September 2026, and still the best explanation of *why*
  most of this work exists. Its Progress table is gone; what shipped before the
  launch checklist existed is kept frozen in a collapsed block, because those
  roadmap items have no F-number. Read it for reasoning, not for status.
- **Phase epics #1–#6** — closed, with a pointer to the two live places. They
  had drifted furthest: #1 showed 1 of 15 items ticked while most of that work
  had shipped and closed elsewhere. Their detail was always in
  `CUSTOMER_EXPERIENCE_PROMPT.md` anyway.
- **`ORG_PLANNING_GRADE.md`**, `ORG_PLANNING_GRADE_2026-09-21.md`,
  `FINAL_REPORT.md`, `MERGE_REVIEW_*.md` — dated snapshots. True of the day
  they were written, never updated after. The doc steward is configured to
  treat them as historical, so it will not cite them as evidence of the current
  state. Neither should you. Prefer the newest grade filename when one exists.

## Where a given thing goes

| You have | Put it |
| --- | --- |
| A feature that just shipped | Tick its box in `LAUNCH_FEATURE_CHECKLIST.md`, in the same pull request, naming the PR |
| A feature that partly shipped | Leave the box unticked and say what landed and what is waiting, as F14 does |
| A bug, or work that isn't a launch feature | Its own issue. Link it from #37 or #38 if it is next up |
| A decision only Keenan can make | `LEGAL_CHECKLIST.md` if it is legal, otherwise an issue labelled for him. Never guess it |
| Something you learned the hard way | `CLAUDE.md` — "Testing gotchas" for test traps, "Rules that always apply" for anything that could lose work |
| A status snapshot, a review, a grade | Its own dated file, and add it to `report_only` **and** `historical` in `tools/doc_steward/config.json` |

## The doc steward

It used to open a pull request after **every** merge to `main`, whether or not
the last one had been looked at. Eight piled up, all editing the same few files,
and each one needed rebasing past the others to review.

It now skips the per-merge run while a steward pull request is already open. The
Monday sweep and a manual run still go ahead, on the reasoning that a person
asking for one has seen the queue. So: **if the steward has gone quiet, check
whether one of its pull requests is waiting** — that is the mechanism working,
not the steward breaking.

## The short version

Two lists. Tick the checklist in the pull request that ships the thing. Keep
your own order on your own issue. Anything dated is history, not state.
