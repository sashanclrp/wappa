# Repository Guidelines

## Build, Test, and Development Commands
Install with `uv sync --group dev`. All four checks must pass before committing:

```bash
uv run ruff check .
uv run ruff format .
uv run mypy wappa
uv run pytest -q
```

## Security & Configuration Tips
- Example vars (from docs/examples): `META_APP_SECRET`, `WP_WEBHOOK_VERIFY_TOKEN`, and in legacy mode `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, `WP_BID`; explicit mode uses `SYSTEM_TOKEN_ENC_KEY` instead of the `WP_*` bundle.

## Architecture Notes
- Event-driven flow: webhooks → dispatcher → handler → messenger.
- Clean layering: domain/interfaces → adapters → API/CLI. Prefer dependency injection via factories/builders.

## DDD Grounding Workflow

Wappa is a Platform-facing messaging runtime, not a business-tenancy system. Every non-trivial code, schema, architecture, public contract, or documentation change must start by grounding the work in the repository language:

1. Read root `CONTEXT.md` for Wappa's canonical domain language.
2. Read `CONTEXT-MAP.md` to locate the target context.
3. Read root `ARCHITECTURE.md` and the nearest context `ARCHITECTURE.md` for the folder being touched. If missing and the change introduces or changes a module responsibility, seam, adapter, or folder rule, create or update the relevant architecture doc in the same change.
4. Read relevant ADRs under `docs/adr/` and, when present, context-local `docs/adr/`.
5. Check `docs/public-contract.md` before changing any surface that host applications may import, call, configure, subscribe to, or depend on.

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

- Wappa's core runtime identity is **Inbox**. Use `InboxRef(platform, inbox_id)` when identity crosses Platform boundaries; keep raw `inbox_id` inside a known Platform boundary. Platform Accounts follow the same rule through `PlatformAccountRef`.
- Inbox credentials have exactly two authorities, selected by `InboxRoutingMode` (`legacy` or `explicit`); never add an `auto` mode or a precedence rule. Only `wappa/core/factory/inbox_assembly.py` reads `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, `WP_BID`, and `SYSTEM_TOKEN_ENC_KEY`.
- The Inbox Directory is Wappa-owned. Hosts adapt through `IInboxDirectorySource` only; they never write directory rows, build envelopes, or decrypt them.
- Meta POST callbacks are authenticated with `META_APP_SECRET` against the exact body bytes before anything else; `WP_WEBHOOK_VERIFY_TOKEN` is only the GET challenge value. Never add a development bypass.
- Table Cache is the only cache family with a general `context_id` (System Scope, Host-defined scope, or Inbox namespace). Every other cache family keeps `inbox_id`.
- For WhatsApp, `inbox_id` maps to Meta `phone_number_id`. Keep that mapping explicit inside the WhatsApp adapter; do not let `phone_number_id` become generic Wappa vocabulary.
- Use **Platform** for an external messaging platform such as WhatsApp. Use **Platform Account** for Platform-side account metadata such as WABA ID.
- Do not use `tenant`, `tenant_id`, or `multi-tenant` as Wappa runtime language. Wappa may carry optional host metadata, but it does not define business tenancy, Owner, or Channel.
- Host applications own business language and business invariants. Wappa owns Platform webhook intake, message sending, event dispatch, runtime cache scoping, and public contract stability.
- API route modules adapt HTTP to Wappa modules; they should not own Platform parsing, credential lookup, cache namespace rules, or dispatch policy.
- Platform adapters own SDK/client construction, credentials, request/response translation, Platform errors, and Platform-specific identity mapping.
- Cache, SSE, expiry, and event modules use Inbox Reference when identity can cross Platforms. A Platform adapter may use raw `inbox_id` inside its known Platform boundary.
- Prefer deep modules: keep interfaces small and place behavior behind them for leverage and locality. Avoid pass-through modules that fail the deletion test.
- Treat the public import surface, CLI templates, webhook routes, event envelopes, cache namespace shape, and generated examples as Wappa's public contract.

## Commit Rules

- Keep commits scoped by Wappa area: runtime, Platform adapter, API contract, persistence, CLI/templates, docs, or tests.
- Use the repository commit format:
  `[ACTION] [SCOPE] Short description`
- Preferred workflow for generated or local-only artifacts: leave them untracked, visible in `git status`, and do not `git add` them unless the task explicitly requires committing generated artifacts.

Examples:

- `[MOD] [CONTRACT] Rename webhook runtime identity to inbox_id`
- `[MOD] [WHATSAPP] Map inbox_id to Meta phone_number_id`
- `[ADD] [ADR] Record Inbox as Wappa runtime scope`
