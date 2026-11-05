# One messaging HTTP API for every Platform, under `/api/{platform}`

Accepted, 2026-11-05. Extends [ADR-0007](0007-embedded-outbound-route-control.md) and [ADR-0009](0009-route-capability-groups.md) (route capability groups) to every Platform; builds on [ADR-0016](0016-one-messenger-method-per-action.md) (one Messenger method per action).

## Context

Wappa's optional HTTP API lived under `/api/whatsapp`. Its Inbox dependency built `InboxRef.whatsapp(header)` and its send routes constructed a raw `WhatsAppMessenger`, so an Instagram Inbox could not use it at all. Building the Messenger by hand also skipped the app's Messenger middleware (window guards, Pub/Sub `bot_reply`), which every other send path applies.

Since ADR-0016 each action has exactly one `IMessenger` method on every Platform, so the send routes map onto Platform-neutral methods. Two options were weighed: a second router per Platform (`/api/instagram/...` duplicating every route), or one router with the Platform in the path.

## Decision

1. **One router, mounted at `/api/{platform}`** (`create_messaging_router`). `{platform}` is `whatsapp` or `instagram`, validated and documented in OpenAPI. Every existing `/api/whatsapp/...` URL is unchanged. `create_whatsapp_router` is removed (clean cut, no alias).
2. **The Inbox is `InboxRef(path Platform, X-Wappa-Inbox-ID)`.** The legacy single-Inbox default answers only for its own Platform. A route without a `{platform}` path parameter cannot resolve an Inbox (no implicit WhatsApp).
3. **Send routes call the Inbox's own Messenger through `OutboundRuntime`**, reusing the credentials the request already resolved (one directory lookup per request) and applying app middleware like any Host-initiated send.
4. **Routes gate on capabilities, and every Platform gap is 501.** A route asks the Inbox's Messenger for the capability it needs (`requires_capability(ICommentControls)`, `IConversationContentReader`, `IConversationHistoryReader`, `IMediaLibrary`) and answers 501 `"<platform> does not provide <capability>"` when it is missing, so a Platform that gains a capability serves the route unchanged. Routes with no capability interface yet (Templates, Template info, the WhatsApp Media API, limits, validators, Inbox health) are WhatsApp-only and answer the same 501. An action the Messenger cannot perform (`UnsupportedOperationError`) answers 501; a local rule violation (`ValueError`, e.g. a non-WebP WhatsApp sticker) answers 400.
5. **Send requests carry every known address.** `DeliveryRequest.addresses` complements `recipient` so WhatsApp can fall back between phone and BSUID (ADR-0019).
6. **Platform-only primitives get routes in the same tree.** Comment reply/hide/unhide/delete and comments-enabled form their own capability group (`comment_controls`: on under `standalone`, off under `embedded`, ADR-0009); content and history reads are always mounted; the private reply belongs to outbound transport.

## Consequences

- Capability groups and profiles (ADR-0007, ADR-0009) apply to every Platform at once; there is nothing per-Platform to mount.
- API sends now run Messenger middleware. A Host whose middleware should not apply to operator sends must say so in the middleware, keyed on `SendInvocation`.
- API events and Pub/Sub notifications carry the Platform that sent.
- Rejected: a router per Platform (two surfaces for one contract, drifting route by route); 404 for Platform gaps (the URL exists, the Platform lacks the capability); a deprecated `create_whatsapp_router` alias (0.34 is a clean cut).
