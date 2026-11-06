# Coding Standards

The one home for check gates, formatting, code and test conventions, documentation upkeep, and commits.

## Check gates

Install with `uv sync --group dev`. Every commit passes all five:

```bash
uv run ruff check .
uv run ruff format .          # --check to verify without rewriting
uv run mypy wappa
uv run pytest -q
git diff --check
```

CI (`.github/workflows/ci.yml`) runs the same gates, and `uv run pre-commit install` enables the local hook (`.pre-commit-config.yaml`). Tests need no `.env`: `tests/conftest.py` sets dummy credentials, and no test calls Meta. Redis-backed tests skip when no server answers; `docker run -d -p 6379:6379 redis:7-alpine` runs them.

While iterating, run `uv run pytest --lf -x` or the touched test files; run the full suite once before committing.

## Formatting

Ruff is the only linter and formatter. `black` is still a dev dependency, but its `[tool.black]` config (`skip-string-normalization`) disagrees with Ruff's double quotes, so running it churns the codebase. Keep Flake8, PyLint, and isort configuration out, and give every `# noqa` its reason on the same line.

Write Markdown prose one line per paragraph; hard line breaks only for list items, headings, table rows, and code blocks.

## Code

- Prefer deep modules: small interfaces with real behaviour behind them. A module that only forwards calls fails the deletion test.
- Validate at the boundaries: API routes, webhook parsing, cache adapters.
- Keep logs secret-free: no secrets, tokens, ciphertext, encryption keys, or raw webhook payloads.

## Tests

- New modules get unit tests; every fix gets a regression test that fails before the change.
- Tests run offline on fakes and fixtures.
- A contract several backends implement gets one parameterized suite over all of them; `tests/test_table_cache_transitions.py` and `tests/test_inbox_directory.py` show the pattern.
- Name tests after the behaviour they pin, not the function they call.

## Documentation in the same change

Update the documentation graph in the same change as the code it describes:

| File | When to update |
| --- | --- |
| `CONTEXT.md` (or a context's own, via `CONTEXT-MAP.md`) | A domain term is added, renamed, or resolved. Glossary only; implementation plans go in `docs/implementation-plans/`. |
| `ARCHITECTURE.md` and the nearest context `ARCHITECTURE.md` | A module responsibility, seam, adapter, interface, or folder rule changes. |
| `docs/public-contract.md` | A surface Host Applications import, call, configure, subscribe to, or scaffold changes. |
| `docs/adr/` | A decision is hard to reverse, surprising without context, and the result of a real trade-off. Each decision cluster has one ADR stating its full current decision: a change to a cluster updates that ADR in the same change, and a new cluster gets a new ADR. |
| `CHANGELOG.md` | Every user-visible change, under the version that ships it, with every break listed. |
| `wappa/cli/skills/` | A Host-visible behavior changes: a public API, limit, media rule, lane, Platform or known gap. The shipped skills must never teach a removed name (`tests/test_shipped_skills.py`). |

## Commits and pull requests

- Format: `[ACTION] [SCOPE] Short description`, imperative mood. `ACTION` is `ADD`, `MOD`, `FIX`, or `REL` (releases, cut by the `bump-version` skill).
- Scope each commit to one Wappa area: runtime, Platform adapter, API contract, persistence, CLI/templates, docs, or tests. Examples: `[MOD] [CONTRACT] Rename webhook runtime identity to inbox_id`, `[FIX] [WHATSAPP] Handle empty webhook payload`.
- Leave generated and local-only artifacts (`dist/`, `logs/`, and JSON-cache output under `cache/`) untracked unless the task asks to commit them. `.gitignore` covers all three.
- A pull request states what changed and why, links its issue, includes logs or screenshots when behaviour is visible, and confirms the check gates pass.
