# Contributing to Wappa

Thanks for wanting to improve Wappa. This guide covers the setup, the checks a change has to pass, and the conventions the codebase actually follows. `AGENTS.md` carries the same rules in the condensed form automated contributors read.

## Getting set up

Wappa targets **Python 3.12+** and uses [uv](https://docs.astral.sh/uv/) for dependency management and process launch. Prefer `uv run <cmd>` over `python -m` so everything executes against the locked environment.

```bash
git clone https://github.com/sashanclrp/wappa.git
cd wappa
uv sync --group dev
```

Copy `.env.example` to `.env` and fill in the values you need. Anything that mounts the WhatsApp callback requires `META_APP_SECRET` and `WP_WEBHOOK_VERIFY_TOKEN` in every environment, including development — Wappa verifies the exact webhook body bytes and has no bypass. `.env.example` explains the two Inbox Routing Modes; do not mix their variables in one process.

Some persistence tests exercise a live Redis. They skip themselves when no server answers, so a local Redis is optional but recommended:

```bash
docker run -d -p 6379:6379 redis:7-alpine
```

## The checks every change must pass

```bash
uv run ruff check .          # lint
uv run ruff format .         # format (use --check in CI)
uv run mypy wappa            # types, strict settings
uv run pytest -q             # full suite
git diff --check             # no whitespace damage
```

All five must be clean before you open a pull request. Ruff is the only linter and formatter — do not add Flake8, PyLint, or isort configuration, and avoid `# noqa` unless you say why in the same line.

## Code conventions

- 4-space indent, 88-column line length, double quotes (Ruff format decides; do not hand-wrap to fight it).
- Type hints everywhere; the code must pass `mypy` under the strict settings in `pyproject.toml`.
- `snake_case` functions and variables, `PascalCase` classes, `lower_snake_case` modules.
- Prefer built-in generics (`list[str]`, `dict[str, int]`) and modern Python 3.12 syntax over `typing.List` / `typing.Dict`.
- Prefer deep modules: small interfaces with real behaviour behind them. A module that only forwards calls fails the deletion test and should not exist.
- Validate at the boundaries — API routes, webhook parsing, cache adapters — and never log secrets, tokens, ciphertext, encryption keys, or raw webhook payloads.

## Tests

- `pytest` with `pytest-asyncio` in auto mode. Files are `tests/test_*.py`, functions `test_*`.
- New modules need unit tests; fixes need a regression test that fails before the change.
- No external network calls. Use fakes and fixtures; the suite must run offline.
- A contract that several backends implement gets **one** parameterized suite over all of them, not three copies. See `tests/test_table_cache_transitions.py` and `tests/test_inbox_directory.py` for the pattern.
- Name tests after the behaviour they pin, not the function they call.

## Documentation is part of the change

Wappa keeps a documentation graph that must stay consistent with the code. Before non-trivial work, read the relevant pieces; after it, update them in the same change:

| File | When to update |
| --- | --- |
| [`CONTEXT.md`](CONTEXT.md) | A domain term is added, renamed, or resolved. Glossary only — no implementation plans. |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) and the nearest context `ARCHITECTURE.md` | A module responsibility, seam, adapter, interface, or folder rule changes. |
| [`docs/public-contract.md`](docs/public-contract.md) | Any surface host applications import, call, configure, subscribe to, or depend on changes. |
| [`docs/adr/`](docs/adr/) | A decision is hard to reverse, surprising without context, and the result of a real trade-off. Supersede an ADR with a banner; never rewrite history. |
| [`CHANGELOG.md`](CHANGELOG.md) | Every user-visible change, under the version that ships it. |

Wappa is a Platform-facing messaging runtime. It owns webhook intake, message sending, event dispatch, runtime cache scoping, and public contract stability. It does **not** define business tenancy: `tenant`, `tenant_id`, `multi-tenant`, `Owner`, and `Channel` are not Wappa runtime language. Use **Platform** (not "provider") for external messaging platforms, **Inbox** for the Platform-facing identity, and `InboxRef(platform, inbox_id)` wherever identity can cross Platform boundaries.

In Markdown, write one long line per paragraph and let editors soft-wrap. Hard line breaks are for real structure only: list items, headings, table rows, code blocks.

## Commits and pull requests

Commit messages use `[ACTION] [SCOPE] Short description` in the imperative mood, scoped by area — runtime, Platform adapter, API contract, persistence, CLI/templates, docs, or tests:

```text
[FIX] [WHATSAPP] Handle empty webhook payload
[MOD] [CONTRACT] Rename webhook runtime identity to inbox_id
[ADD] [ADR] Record Inbox as Wappa runtime scope
```

Pull requests should include what changed and why, the linked issue, and logs or screenshots when behaviour is visible. Confirm in the description that lint, types, and tests pass locally. Keep generated artifacts (`dist/`, `logs/`, `cache/`) untracked.

## Backlog and planning

Larger work is planned in [`docs/backlog/`](docs/backlog/README.md); [`BACKLOG-EXECUTION-PLAN.md`](docs/backlog/BACKLOG-EXECUTION-PLAN.md) orders it. A backlog item lives in `drafts/`, `pending/`, or `in_progress/` depending on how settled it is, and completed items are **deleted** — git history is the archive.

## Security

Never commit secrets. Report a suspected vulnerability privately to the maintainers rather than opening a public issue, and describe the class of problem rather than a working exploit.

## Community and license

- 🐛 Bugs: [GitHub Issues](https://github.com/sashanclrp/wappa/issues)
- 💡 Ideas and questions: [GitHub Discussions](https://github.com/sashanclrp/wappa/discussions)
- 🔰 New here: [good first issues](https://github.com/sashanclrp/wappa/labels/good%20first%20issue)

By contributing you agree that your contributions are licensed under the [Apache License 2.0](LICENSE), the same license that covers Wappa.
