# Outbound: one messaging HTTP API, capability route groups, Template transport

Accepted, 2026-11-06. Consolidates the outbound decisions first recorded on 2026-08-03 (Inbox-scoped Template transport), 2026-08-05 (embedded route control and route capability groups), 2026-11-05 (one messaging HTTP API under `/api/{platform}`) and the 2026-11-06 architecture hardening (Templates as a capability, the WhatsApp extension router, failure statuses). This ADR states the whole current decision; the earlier ADRs it absorbed were deleted. Decisions 1-6 keep their earlier numbers so existing references stay valid.

## Context

Wappa's optional HTTP API lived under `/api/whatsapp` and built a raw `WhatsAppMessenger`, so an Instagram Inbox could not use it and API sends skipped the app's Messenger middleware. An embedding Host that owns an authenticated Operator boundary cannot expose routes that send, delete or rewrite state with only Wappa's Inbox credentials behind them, but it still needs uploads, reads and lookups under the same prefixes. Host Applications also need Template transport without constructing Wappa's client, handler and pipeline classes, and a send whose outcome is unknown must never look like a retryable failure.

## Decision

### One messaging HTTP API

1. **One router, mounted at `/api/{platform}`** (`create_messaging_router`). `{platform}` is an installed Platform of the app (`whatsapp`, `instagram`), validated against the app's Platform Registry and documented in OpenAPI; anything else is 404 before any Inbox lookup. `/api/whatsapp/...` URLs are unchanged; there is no per-Platform router and no `create_whatsapp_router`.
2. **The Inbox is `InboxRef(path Platform, X-Wappa-Inbox-ID)`.** The header selects scope and grants no permission; Host authentication runs first. The legacy single-Inbox default answers only for its own Platform, and a route without `{platform}` cannot resolve an Inbox.
3. **Send routes call the Inbox's own Messenger through `OutboundRuntime`**, reusing the credentials the request already resolved (one directory lookup per request) and applying app middleware like any Host-initiated send.
4. **Routes gate on capabilities; every Platform gap is 501.** A route asks the Inbox's Messenger for the capability it needs (`requires_capability(ICommentControls | IConversationContentReader | IConversationHistoryReader | IMediaLibrary | ITemplateMessaging | IUserDataRequests)`) and answers 501 `"<platform> does not provide <capability>"` when it is missing, so a Platform that gains a capability serves the route unchanged. Templates are the `ITemplateMessaging` capability, and the location and phone-number request routes (`/specialized/send-location-request`, `/send-contact-request`) the `IUserDataRequests` capability. The only Platform-name gate is `whatsapp_only`, the router-level dependency of the WhatsApp extension router, which mounts the WhatsApp operations with no capability interface (text, media and Template limits, validators, Template info, `/health`) and answers the same 501 under another Platform's path before resolving an Inbox. Status mapping lives in one decorator, `map_send_errors`: `UnsupportedOperationError` 501, a local rule `ValueError` 400, a failed `MessageResult` the 4xx its `error_code` maps to (default 400), any other exception 500; request validation stays 422. A failed send-text or mark-as-read therefore never answers 200.
5. **Send requests carry every known address.** `DeliveryRequest.addresses` complements `recipient` so the adapter can fall back between Delivery Addresses.
6. **Platform-only primitives get routes in the same tree.** Comment reply, hide, unhide, delete and comments-enabled are the `comment_controls` group; content and history reads are always mounted; the private reply belongs to outbound transport.

### Route capability groups

7. **Group routes by what an unauthenticated caller could do with them**, not by whether they send. Groups, each independently mountable:

| Group | Routes | `standalone` | `embedded` |
| --- | --- | --- | --- |
| `outbound_transport` | ordinary, interactive, contact, location and private-reply sends, mark-as-read | on | off |
| `template_transport` | Template sends | off | off |
| `media_management` | `DELETE /media/{id}` | on | off |
| `media_upload` | `POST /media/upload` | on | on |
| `state_handler_api` | `/state-handlers/*` (get included: it exposes any recipient's state) | on | off |
| `comment_controls` | comment mutations | on | off |
| everything else | reads, lookups, downloads, validation | on | on |

8. **Two named profiles set the groups together**, because getting one of several booleans wrong is a security bug; an explicitly named group overrides the profile. `Wappa(include_outbound_transport_api=False)` without a profile implies `embedded`. Template mutations default off because they were introduced opt-in; ordinary sends default on because they are the documented standalone surface. Media upload stays on under `embedded` (a create, not a destroy) and `include_media_upload_api=False` closes it. `Wappa(route_profile=..., include_<group>_api=...)` and `create_messaging_router(profile=..., include_<group>=...)` take the same choices. Each route picks its group at its decorator, in the module that owns it.

### Template transport

9. **`OutboundRuntime` is the deep public factory** (`wappa/messaging/outbound_runtime.py`). `OutboundRuntime.messenger(inbox_ref)` is the Inbox-bound, middleware-wrapped Messenger for Host-initiated sends, and `OutboundRuntime.templates(inbox_ref)` builds `InboxTemplateTransport` over that same Messenger. `send()` checks `capability(ITemplateMessaging)` before any I/O and returns `REJECTED` with `capability_unsupported` when absent.
10. **Requests are Platform-facing and closed.** A Template request rejects unknown fields and carries exactly one typed Delivery Address (phone or BSUID), serialized as Meta `to` or `recipient`; usernames are evidence, never addresses; no Host attribution, policy or state. Marketing Templates use `/marketing_messages`, utility and authentication `/messages`; the named `cloud_messages_fallback` policy may pick `/messages` for marketing before provider I/O, and no rejection triggers a cross-endpoint retry. Authentication Templates reject BSUIDs.
11. **Four conservative outcomes:** `accepted` (acceptance plus a Message ID proven), `rejected` (evidence of non-acceptance), `transport_unavailable` (no call started, including drain), `indeterminate` (neither provable; a success without a Message ID is indeterminate). Acceptance never means delivered, read, replied or committed, and an `indeterminate` result is never safe to resend automatically.

## Consequences

- Capability groups and profiles apply to every Platform at once; there is nothing per-Platform to mount.
- API sends run Messenger middleware; middleware that should not apply to operator sends keys on `SendInvocation`. API events and Pub/Sub notifications carry the sending Platform.
- An embedding Host reaches zero unauthenticated routes that send, delete or rewrite state, `POST /media/upload` aside. Route-composition tests assert the generated route table, not the flags: `EVERY_MUTATION & mounted == MEDIA_UPLOAD_ROUTES`.
- `/api/instagram/*/limits`, validators, Template info and `/health` answer 501; `/api/instagram/media/download/{id}` serves through `IMediaLibrary`.
- Hosts depend on shallow imports and cannot acquire internal transport components through `OutboundRuntime`.

## Alternatives rejected

- A router per Platform (two surfaces for one contract); 404 for a Platform gap (the URL exists, the capability does not); a deprecated `create_whatsapp_router` alias.
- Splitting routes into "send" and "service" (left state rewrites and media deletes open), and five unprofiled booleans.
- Hosts constructing `WhatsAppClient` and handlers; governance and lifecycle fields in Wappa requests; `success: bool` for every outcome; mounting Template routes by default.
- Gating Templates on the Platform name, or `whatsapp_only` scattered across individual routes.
