---
name: wappa-develop
description: Guides changes to the Wappa library itself — a Messenger method, message type, event lane, HTTP route, media rule, credential path or plugin; adding a new Platform such as Telegram; verifying behaviour live against Meta with the lab app and the scripts/ debug tools; and keeping the shipped Host skills, docs, ADRs and CHANGELOG in step with the code. Use when working inside the Wappa repository on its code, tests, docs or shipped skills, when asked to add or change a Platform, a send method, a webhook family or a format rule, to run or record a live gate, or to debug the dev server, Meta subscriptions or Redis. Not for building a Host app on Wappa (wappa-apps) or for releases (bump-version).
---

# Developing Wappa

Wappa is a Platform-facing runtime: it owns intake, sends, dispatch, cache scoping and its public contract; the Host owns every business concept. Every change keeps four promises: **WhatsApp first** (neutral contracts mirror WhatsApp; other Platforms emulate, ADR-0028), **no Platform branch in shared code** (only adapter folders and `wappa/platforms.py`), **clean cut** (no aliases or shims; every break listed in `CHANGELOG.md`), and **no media conversion** (Wappa enforces format rules before I/O; the Host converts).

## Workflow

```
Progress:
- [ ] 1. Read what the change touches (AGENTS.md reading order)
- [ ] 2. Design: grill-with-docs when it names, decides or breaks something
- [ ] 3. Walk the change chain for its kind, hop by hop
- [ ] 4. Gates green; docs graph and shipped skills updated in the same change
- [ ] 5. Live check when Meta behaviour is involved; record the evidence
- [ ] 6. Commit on main per CODING_STANDARDS.md
```

**1. Read.** `CONTEXT.md` for names (its Anti-Language table first), root `ARCHITECTURE.md` plus the nearest context `ARCHITECTURE.md`, the ADR cluster in `docs/adr/`, and `docs/public-contract.md` for anything a Host touches. Read large docs by headings (`rg -n '^#{1,3} ' FILE`), then only the section needed.

**2. Design.** A new name, a reversed decision or a public break goes through the `grill-with-docs` skill first; it updates `CONTEXT.md` and the ADR cluster inline. A pure fix inside one adapter skips this.

**3. Walk the chain.** Each kind of change has a written chain; follow it in order and treat each hop as an edit or a deliberate "no change":

| Change | Chain |
| --- | --- |
| A Messenger method or its parameters | `wappa/messaging/ARCHITECTURE.md` → "Changing a Messenger method" (8 hops, parity tests) |
| A message family or event lane | `wappa/webhooks/ARCHITECTURE.md` → "Adding a message family or event lane" |
| An HTTP route | `wappa/api/ARCHITECTURE.md` → "Adding a route" |
| A new Platform | `references/add-a-platform.md` |
| A media or format rule, a live gate, a Meta behaviour question, debugging the dev server, Meta or Redis | `references/live-verification.md` |
| A shipped Host skill, or any change a Host would code against | `references/shipped-skills.md` |

**4. Gates and docs.** All five gates from `CODING_STANDARDS.md` pass (`ruff check`, `ruff format`, `mypy wappa`, `pytest -q`, `git diff --check`). In the same change update, as touched: `CONTEXT.md`, the `ARCHITECTURE.md` files, `docs/public-contract.md`, the ADR cluster, `CHANGELOG.md` (every break), `docs/migration/` for a break, and the shipped skills under `wappa/cli/skills/` (`tests/test_shipped_skills.py` checks their imports and methods).

**5. Live.** Offline tests never prove Meta behaviour. Follow `references/live-verification.md`: the user runs live sends; you read logs, Meta state and Redis with the read-only `scripts/` tools; evidence goes into the PRD's live test plan before a rule changes.

**6. Commit.** `[ACTION] [SCOPE] description` on `main`, then `git branch -f dev main` and push both. Never commit `.env`, tokens, `logs/` or `cache/`. Releases are the `bump-version` skill.

## Hard rules

- Never print, log or commit a token, an app secret, an OAuth code or a real User ID; `scripts/env_keys.sh` shows which keys are set without values.
- Never start a server on the user's port (8000) or send a live message to a real account yourself; ask the user to run the send and read the result.
- Agent instructions live only in `AGENTS.md`; no `CLAUDE.md`.
- Shared modules never import a Platform adapter or branch on `PlatformType`; `tests/test_third_platform_contract.py` has a guard test for it.
- Never weaken a WhatsApp seam to fit another Platform; emulate, and raise `UnsupportedOperationError` only when emulation is impossible.
