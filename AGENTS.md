# Repository Guidelines

## Project Structure & Module Organization
- `wappa/`: Core package.
  - `core/`: app core, config, plugins, events, logging.
  - `api/`: FastAPI routes, middleware, dependencies.
  - `messaging/`: WhatsApp client, handlers, models.
  - `persistence/`: cache backends (`memory/`, `json/`, `redis/`).
  - `schemas/`: Pydantic models (core + WhatsApp).
  - `cli/`: CLI entrypoint and project templates.
- `dist/`: build artifacts. `logs/`: local logs.

## Build, Test, and Development Commands
```bash
# Install dev deps (Python 3.12+)
uv sync --group dev

# Lint, format, types
uv run ruff check .
uv run ruff format .
uv run mypy wappa

# Tests (pytest + pytest-asyncio)
uv run pytest -q

# CLI help (local)
uv run wappa --help
```

## Coding Style & Naming Conventions
- Indent 4 spaces; line length 88; double quotes (ruff format).
- Use type hints everywhere; pass `mypy` with strict settings.
- Naming: `snake_case` functions/vars, `PascalCase` classes, modules in `lower_snake_case`.
- Keep modules focused; prefer small, composable functions.
- Run `ruff` before commits; avoid disabling rules unless justified.

## Testing Guidelines
- Framework: `pytest` with `pytest-asyncio` for async code.
- Location: `tests/` with files named `test_*.py`; functions `test_*`.
- Write unit tests for new modules and regression tests for fixes.
- Use factories/fixtures; avoid external network calls in tests.

## Commit & Pull Request Guidelines
- Commit style: prefix with tags seen in history, e.g. `[ADD]`, `[FIX]`, `[MILESTONE]`.
  - Imperative mood, concise scope: "[FIX] Handle empty webhook payload".
- PRs: include description, linked issues, rationale, and screenshots/logs if relevant.
- Required: code formatted, `ruff`/`mypy`/`pytest` pass locally; update README/docs when behavior changes.

## Security & Configuration Tips
- Never commit secrets. Use `.env` (see `wappa/core/config/settings.py`).
- Example vars (from docs/examples): `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, `WP_BID`.
- Validate inputs at boundaries (API routes, webhook parsing) and log safely.

## Architecture Notes
- Event-driven flow: webhooks → dispatcher → handler → messenger.
- Clean layering: domain/interfaces → adapters → API/CLI. Prefer dependency injection via factories/builders.

## DDD Grounding Workflow

Wappa is a provider-facing messaging runtime, not a business-tenancy system. Every non-trivial code, schema, architecture, public contract, or documentation change must start by grounding the work in the repository language:

1. Read root `CONTEXT.md` for Wappa's canonical domain language. If it does not exist yet, treat the current task as documentation bootstrap and create it before making broad terminology changes.
2. Read `CONTEXT-MAP.md` if present to locate the target context. If absent, assume Wappa is a single-context repo until a real second context exists.
3. Read root `ARCHITECTURE.md` and the nearest context `ARCHITECTURE.md` for the folder being touched. If missing and the change introduces or changes a module responsibility, seam, adapter, or folder rule, create or update the relevant architecture doc in the same change.
4. Read relevant ADRs under `docs/adr/` and, when present, context-local `docs/adr/`.
5. Check `docs/public-contract.md` before changing any surface that host applications may import, call, configure, subscribe to, or depend on. If the file does not exist and the change affects Wappa's public interface, create it or update the nearest public-contract documentation.

If the user asks for architecture work, refactoring, DDD, domain naming, SOLID cleanup, or a design discussion, follow the `grill-with-docs` discipline:

- Challenge ambiguous or conflicting terms against `CONTEXT.md`.
- Prefer canonical Wappa terms already defined there.
- Cross-check claims against code before treating them as true.
- Ask one design question at a time when the answer cannot be discovered from the codebase, and include the recommended answer.
- Update `CONTEXT.md` immediately when a domain term is resolved. Keep `CONTEXT.md` a glossary only; do not put implementation plans there.
- Update `ARCHITECTURE.md` when a module responsibility, seam, adapter, interface, or folder rule changes.
- Create or update an ADR only when the decision is hard to reverse, surprising without context, and the result of a real trade-off.

New work must leave the documentation graph consistent. If a change introduces or renames a domain concept, module responsibility, public contract, runtime seam, adapter, interface, or architectural rule, update the relevant docs and ADRs in the same change.

Use these Wappa architectural defaults unless an ADR says otherwise:

- Wappa's core runtime identity is **Inbox**. Use `inbox_id` for the stable provider-facing ingress/egress identity.
- For WhatsApp, `inbox_id` maps to Meta `phone_number_id`. Keep that mapping explicit inside the WhatsApp adapter; do not let `phone_number_id` become generic Wappa vocabulary.
- Use **Provider** for an external messaging platform such as WhatsApp. Use **Provider Account** for provider-side account metadata such as WABA ID.
- Do not use `tenant`, `tenant_id`, or `multi-tenant` as Wappa runtime language. Wappa may carry optional host metadata, but it does not define business tenancy, Owner, or Channel.
- Host applications own business language and business invariants. Wappa owns provider webhook intake, message sending, event dispatch, runtime cache scoping, and public contract stability.
- API route modules adapt HTTP to Wappa modules; they should not own provider parsing, credential lookup, cache namespace rules, or dispatch policy.
- Provider adapters own SDK/client construction, credentials, request/response translation, provider errors, and provider-specific identity mapping.
- Cache, SSE, expiry, and event modules must scope runtime data by `inbox_id` where provider-facing identity is required.
- Prefer deep modules: keep interfaces small and place behavior behind them for leverage and locality. Avoid pass-through modules that fail the deletion test.
- Treat the public import surface, CLI templates, webhook routes, event envelopes, cache namespace shape, and generated examples as Wappa's public contract.

## Commit Rules

- Keep commits scoped by Wappa area: runtime, provider adapter, API contract, persistence, CLI/templates, docs, or tests.
- Use the repository commit format:
  `[ACTION] [SCOPE] Short description`
- Preferred workflow for generated or local-only artifacts: leave them untracked, visible in `git status`, and do not `git add` them unless the task explicitly requires committing generated artifacts.

Examples:

- `[MOD] [CONTRACT] Rename webhook runtime identity to inbox_id`
- `[MOD] [WHATSAPP] Map inbox_id to Meta phone_number_id`
- `[ADD] [ADR] Record Inbox as Wappa runtime scope`
