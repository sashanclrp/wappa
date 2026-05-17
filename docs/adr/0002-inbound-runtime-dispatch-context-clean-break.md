# ADR-0002: Inbound Runtime, Dispatch Context, and Clean-Break Runtime Language

## Status

Accepted

## Context

Wappa's inbound path currently mixes several responsibilities under route/controller and processor language:

- HTTP routes accept platform webhooks.
- Processors parse platform payloads into Universal Models.
- The controller validates Inbox identity, creates Messenger and Cache Factory instances, opens DB seams, scopes SSE identity, clones `WappaEventHandler`, and dispatches the event.
- Some docs and code still use request-context, provider, compatibility-shim, and legacy import-path language.

This makes module boundaries harder to reason about and allows platform translators to drift into runtime orchestration.

## Decision

Use **Inbound Runtime** as the canonical term for the module that turns an accepted platform webhook into a context-bound handler dispatch.

Use **Dispatch Context** as the canonical term for the per-event runtime bundle containing:

- `inbox_id`
- `user_id`
- `messenger`
- `cache_factory`
- DB access
- SSE identity
- the cloned `WappaEventHandler`

Use **Processor** only for pure platform payload translation. A Processor parses a platform webhook payload into a Universal Model. It must not mutate ContextVars, build messengers, resolve cache factories, or clone handlers.

Use **`InboundMessageWebhook`** as the only public inbound-message Universal Model name. Do not preserve the old import path with a compatibility shim.

Treat URL `inbox_id` as the routing authority. The Inbound Runtime validates that
`inbox_id` through the configured `IInboxCredentialStore`; database-backed stores
may use DB/Redis as the source of truth for registered Inboxes. Platform payload
inbox metadata is then validated against the routed Inbox when present. For WhatsApp:

- `metadata.phone_number_id` maps to `inbox_id`
- `entry[].id` maps to `platform_account_id` (WABA ID)

Use **Platform** for messaging platforms. Use **External Webhook Source** for non-messaging webhook integrations. Payment-specific integrations may use **Payment Provider**.

Keep **Universal Model** as the canonical term for the platform-agnostic webhook representation that leaves `wappa/webhooks` and enters dispatch.

Universal Models are still Pydantic schemas. The clean architecture decision is
not "models instead of schemas"; it is one canonical inbound schema context with
no duplicate source of truth.

Do not accept Compatibility Shim as a Wappa architectural pattern. Wappa should prefer clean breaking changes over old import-path preservation.

Keep **Messenger** / `IMessenger` as the public outbound seam for Host Applications for this round. Defer public seam splits such as `TextMessenger` or `MediaMessenger` until multiple real platform adapters or concrete testing pressure justify the split. If that evidence appears later, prefer a clean breaking change over compatibility aliases.

## Consequences

- Existing host applications may break when names are cleaned up. That is intentional.
- The Inbound Runtime becomes the place to reason about handler dispatch and per-event infrastructure.
- Processors become easier to test because they are pure translators.
- Inbox mismatch handling becomes explicit instead of silently overriding URL identity from payload metadata.
- Future Telegram, Instagram, and Teams adapters must translate their platform schemas into the same Universal Models.
- Every Universal Model form must remain a Pydantic schema with explicit validation.
- Docs and PRDs must distinguish messaging Platform from External Webhook Source and Payment Provider.

## Alternatives Considered

1. **Keep "Webhook Service" as the orchestration name.** Rejected because it hides Messenger, Cache Factory, DB, SSE, handler cloning, and dispatch responsibilities.
2. **Use "Request Context" for handler dispatch state.** Rejected because webhook processing may run in a background task after the HTTP request has returned.
3. **Let Processors mutate runtime context.** Rejected because it couples pure payload translation to orchestration and makes platform adapters harder to test.
4. **Keep compatibility shims for old import paths.** Rejected because Wappa is intentionally doing a clean breaking upgrade.
5. **Split `IMessenger` now.** Rejected because the seam split is hypothetical until real platform adapters or tests prove the current interface is too wide.
