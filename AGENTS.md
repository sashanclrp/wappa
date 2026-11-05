# Repository Guidelines

Wappa is an open source framework for building smart workflows, agents, and full chat applications over messaging Platforms such as WhatsApp. It is a Platform-facing messaging runtime: it owns webhook intake, message sending, event dispatch, runtime cache scoping, and public contract stability, while Host Applications own business language and invariants.

## Where to read next

- **Committing, testing, formatting**: read `CODING_STANDARDS.md` (Check gates, Formatting, Commits) before your first commit or test run.
- **Extending the library, editing examples or templates**: read `CODING_STANDARDS.md` (Extending the library, Example apps and templates) for the module map, setup snippets, and environment variables.
- **Design discussion, domain naming, ADRs**: read `CODING_STANDARDS.md` (Design discussions and documentation upkeep) before proposing or recording a decision.

## Grounding before non-trivial changes

Start every non-trivial code, schema, architecture, public contract, or documentation change by grounding it in the repository language:

1. Read root `CONTEXT.md` for Wappa's canonical domain language.
2. Read `CONTEXT-MAP.md` to locate the target context.
3. Read root `ARCHITECTURE.md` and the nearest context `ARCHITECTURE.md` for the folder being touched.
4. Read relevant ADRs under `docs/adr/` and, when present, context-local `docs/adr/`.
5. Check `docs/public-contract.md` before changing any surface that host applications may import, call, configure, subscribe to, or depend on.

Leave the documentation graph consistent: when a change introduces or renames a domain concept, module responsibility, public contract, runtime seam, adapter, interface, or architectural rule, update the relevant docs and ADRs in the same change.

## Canonical runtime language

- **Inbox**: the Platform-facing message ingress/egress identity used to receive webhooks, send messages, scope runtime caches, and subscribe to event streams. `inbox_id` is its Platform-native identifier, unique only inside one Platform; use `InboxRef(platform, inbox_id)` when identity crosses Platform boundaries and keep raw `inbox_id` inside a known Platform boundary.
- **Platform**: an external messaging platform such as WhatsApp (canonical over the older "Provider", matching `PlatformType`).
- **Platform Account**: Platform-side account metadata such as WABA ID, identified globally by `PlatformAccountRef(platform, platform_account_id)`; it is metadata, not Wappa's runtime identity.
- **Inbox Routing Mode**: `legacy` (settings-backed single Inbox) or `explicit` (Wappa's encrypted Inbox Directory over the Host's `IInboxDirectorySource`).
- **User**: the end-user/contact identity inside a Platform conversation.
- **Host Application**: the application embedding Wappa and owning business concepts such as Owner, Channel, customer, or workflow.
- Speak in these terms and carry host metadata as optional opaque data. Wappa defines no business tenancy: `tenant`, `tenant_id`, and `multi-tenant` are never Wappa runtime language.

## Architecture defaults

Apply these unless an ADR says otherwise:

- Event-driven flow: webhooks → dispatcher → handler → messenger. Layering: domain/interfaces → adapters → API/CLI, wired by dependency injection through factories and builders.
- Select Inbox credentials by `InboxRoutingMode`, exactly `legacy` or `explicit`; never add an `auto` mode or a precedence rule. Only `wappa/core/factory/inbox_assembly.py` reads `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, `WP_BID`, and `SYSTEM_TOKEN_ENC_KEY`.
- The Inbox Directory is Wappa-owned. Hosts adapt only through `IInboxDirectorySource`; Wappa alone writes directory rows, builds envelopes, and decrypts them.
- Authenticate every Meta POST callback with `META_APP_SECRET` against the exact body bytes before anything else, in every environment including development; never add a bypass. `WP_WEBHOOK_VERIFY_TOKEN` is only the GET challenge value.
- Table Cache is the only cache family with a general `context_id` (System Scope, Host-defined scope, or Inbox namespace). Every other cache family keeps `inbox_id`; cache, SSE, expiry, and event modules use `InboxRef` when identity can cross Platforms.
- For WhatsApp, `inbox_id` maps to Meta `phone_number_id`. Keep that mapping explicit inside the WhatsApp adapter and use `inbox_id` everywhere else.
- API route modules only adapt HTTP to Wappa modules; Platform parsing, credential lookup, cache namespace rules, and dispatch policy live behind them.
- Platform adapters own SDK/client construction, credentials, request/response translation, Platform errors, and Platform-specific identity mapping.
- Prefer deep modules: small interfaces with real behavior behind them, so every module passes the deletion test.
- Treat the public import surface, CLI templates, webhook routes, event envelopes, cache namespace shape, and generated examples as Wappa's public contract.
