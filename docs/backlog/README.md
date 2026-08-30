# Backlog

This directory stores implementation backlogs for work that is planned but not yet completed.

**Master index / ordering:** [`BACKLOG-EXECUTION-PLAN.md`](./BACKLOG-EXECUTION-PLAN.md) is the source of truth for what to attack next and in what order. The individual files below are the implementation detail.

**Completed work = delete the file.** There is no `done/` or `archive/` folder — git history is the archive. Recover a deleted backlog with `git log --diff-filter=D -- backlog/`. A plan with *mixed* done/pending items is updated in place (add a "Code reality" note) rather than deleted until everything closes.

## The three folders

A backlog item lives in exactly one of three folders. The folder answers one question — *how much is settled?* — and nothing else. Urgency stays on the filename, blocking stays in the file's `status:`.

| Folder | Meaning | Test |
|---|---|---|
| `drafts/` | An idea. Not yet explored deeply enough to build from. | Could someone else start implementing from this file alone? If no, it is a draft. |
| `pending/` | Explored and ready. Scope, approach, and exit criteria are settled; no code has landed. | Is the design settled *and* is the first line of implementation still unwritten? |
| `in_progress/` | Already moving. Code for at least one slice of this item exists in the repo. | Can you point at a merged commit or a file in the tree that this item produced? |

Rules for the transitions:

- **`drafts/` → `pending/`** happens when the design stops changing: the file gains a scope, an approach, and exit criteria a second person could execute. A grill session usually is that transition.
- **`pending/` → `in_progress/`** happens on the **first landed slice**, not on the first line of thinking. Deciding to build it next week does not move it; merging the first commit does.
- **`in_progress/` → deleted** happens when everything in the file is shipped and every completion gate is satisfied. Partial completion is recorded *inside* the file, not by moving it back.

Two things the folder deliberately does **not** encode:

- **Blocked is not a folder.** An item waiting on an external clock, a Meta approval, or another PRD keeps its folder and says so in `status:`. `260803-high-template-meta-live-certification` is `pending` and blocked; `260805-mid-automation-builder-steering-step` is `pending` and blocked. Neither is in progress, because no code has landed for them.
- **Urgency is not a folder.** `-low` / `-mid` / `-high` stay on the filename in every folder.

## Two ways to create a backlog item

**1. Standalone PRD** — one file directly in the folder, named `YYMMDD-{urgency}-{backlog-title}.md`. The default for any single deliverable or tightly-related group of deliverables.

**2. Feature PRD series** — a major feature that decomposes into several PRDs gets its own directory, `YYMMDD-{feature}/`, containing:

- `plan.md` — the execution plan: fixed design constraints, the PRD inventory table with per-PRD status, dependency graph, implementation order, resource budget, and any external clocks or completion gates that are not PRDs.
- one `.md` per PRD, grouped in ownership subdirectories when the work spans surfaces (e.g. `symphonai/`, `wappa/`, `consumers/`), each file named `YYMMDD-{urgency}-{prd-title}.md`.

Examples: `in_progress/260812-symphonai-booking/`, `in_progress/260817-meta-capi-consumer-rollout/`.

A series directory moves as a unit. It reaches `in_progress/` when its first PRD lands and is deleted only once **every** PRD inside it is done and `plan.md`'s completion gates (external clocks, certification activities, doc obligations) are satisfied. Until then, flip individual PRD statuses in `plan.md`'s inventory table and update files in place. Git history remains the archive for the whole directory.

## Rules

- Standalone files use `YYMMDD-{urgency}-{backlog-title}.md`; series directories use `YYMMDD-{feature}/` with urgency carried on the individual PRD filenames.
  - `-low` — no user impact, purely internal quality/debt
  - `-mid` — affects DX or future velocity but not live behaviour
  - `-high` — blocks a feature, causes user-facing risk, or must land before next release
- Keep each file focused on one deliverable or tightly-related group of deliverables.
- Include context, scope, proposed approach, open questions, and clear exit criteria. A file in `drafts/` may be missing several of these — that is what makes it a draft.
- Update the file while the work is active so it stays useful as the current source of truth. An item in `in_progress/` should record what already landed, so the next session does not rebuild it.
- Delete the file (or directory, per the rule above) once the work is fully implemented and no pending action remains.

Recommended sections:
- `Context`
- `Scope`
- `Out of Scope`
- `Implementation Notes`
- `Open Questions`
- `Exit Criteria`
