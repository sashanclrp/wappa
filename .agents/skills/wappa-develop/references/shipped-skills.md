# Keeping the shipped Host skills true

## Contents

- What ships
- When to update
- How to update
- Checks

## What ships

`wappa/cli/skills/` is package data. `wappa init` copies each folder into a new Host's `.claude/skills/` (real files) and links `.agents/skills/`, never overwriting an existing folder. In this repo, both lanes are symlinks to `wappa/cli/skills/<name>`, so there is one copy.

| Skill | Teaches |
| --- | --- |
| `wappa-apps` | The neutral core: lanes, Messengers, targets, results, limits, rate limits; references per topic and per Platform (`messaging`, `media-formats`, `whatsapp`, `instagram`, `connecting-accounts`, `meta-app-setup`, `testing-and-troubleshooting`) |
| `wappa-conversational-scores` | Scores and guided flows |
| `wappa-state-and-storage` | Caches, Redis, Postgres, isolation |
| `wappa-host-integration` | Multi-Inbox, plugins, runtime lanes, upgrades |

Maintainer skills (this one, `bump-version`) live in `.agents/skills/` with `.claude/skills/` symlinks and never ship.

## When to update

In the same change as any Host-visible behavior: a new, renamed or removed public API, a new limit or media rule, a new lane, a Platform added, or a known gap closed. A skill that teaches a removed name is a bug of the same severity as wrong docs. Never teach a proposed API, and keep "Known gaps" honest.

## How to update

1. Write or extend an eval in the skill's `evals/evals.json` that fails on the old text.
2. Edit the reference that owns the topic (one home per fact; link, don't copy). Keep SKILL.md for rules every branch needs.
3. Bump the reference's `checked_on` and `revision` when it copies an outside system (Meta pages, live results).
4. For a large rewrite, run a fresh agent on two or three evals.

## Checks

- `uv run pytest tests/test_shipped_skills.py -q`: every taught `from wappa… import` exists, every `self.messenger`/`self.whatsapp`/`self.instagram` method named exists, no `recipient=` in code, frontmatter names match folders, every reference is linked from SKILL.md, every skill named exists, and the isolation example runs.
- The skills linter, when installed: `lint_skill.py --professional <dir>` per skill and `--lanes .` for the repo.
