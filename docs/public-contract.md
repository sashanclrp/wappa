# Public Contract

This file tracks Wappa surfaces that host applications may import, call, configure, subscribe to, or depend on.

## Inbox Credentials

Host applications may configure the credential lookup strategy through:

- `WappaBuilder.with_inbox_credential_store(store)`
- `Wappa(inbox_credential_store=store)`
- `Wappa.set_inbox_credential_store(store)`

The store must implement `IInboxCredentialStore`:

- `get_credentials(inbox_id) -> InboxCredentials`
- `validate_inbox(inbox_id) -> bool`
- `invalidate_cache(inbox_id) -> None`

When no custom store is configured, Wappa uses `SettingsInboxCredentialStore`, which resolves the single configured Inbox from `WP_PHONE_ID`, `WP_ACCESS_TOKEN`, and `WP_BID`.

`DatabaseInboxCredentialStore` is provided for host-owned `wappa_inboxes` tables. Wappa reads the table but does not own inbox CRUD, migrations, token rotation, or encryption policy.

## Universal Webhooks

Host applications import inbound webhook schemas and Universal Models from
`wappa.webhooks`.

Canonical messaging webhook routes are:

- `GET /webhook/inboxes/{inbox_id}/{platform}` for platform verification at the
  same URL used for processing.
- `POST /webhook/inboxes/{inbox_id}/{platform}` for inbound platform webhook
  processing.
- `GET /webhook/messenger/{platform}/verify` for retained verify-only callbacks.

Wappa does not provide an inbox-scoped `/webhook/messenger/{inbox_id}/{platform}`
processing route.
Wappa also does not process platform webhooks on `/webhook/messenger/*` paths.

Public inbound imports include:

- `from wappa.webhooks import InboundMessageWebhook`
- `from wappa.webhooks.core.webhook_interfaces import InboundMessageWebhook`
- `from wappa.webhooks import StatusWebhook`
- `from wappa.webhooks import ErrorWebhook`
- `from wappa.webhooks import SystemWebhook`
- `from wappa.webhooks import CustomWebhook`
- `from wappa.webhooks import UniversalWebhook`
- `from wappa.webhooks.whatsapp import WhatsAppWebhook`
- `from wappa.webhooks.whatsapp.*` platform payload schemas

`InboundMessageWebhook` is the only public inbound-message Universal Model name. Wappa does not provide a compatibility alias for previous inbound-message model names.

The old inbound schema paths under `wappa.schemas.whatsapp`,
`wappa.schemas.factory`, and `wappa.schemas.core.base_*` are intentionally
removed. No compatibility import path is provided.

`wappa.schemas` remains public only for shared primitives such as:

- `wappa.schemas.core.types.PlatformType`
- `wappa.schemas.core.types.MessageType`
- `wappa.schemas.core.recipient.RecipientRequest`
- `wappa.schemas.core.recipient.apply_recipient_to_payload`

Webhook processors are translation-only adapters. They return Universal Models and do not mutate ContextVars, construct messengers, construct cache factories, open DB sessions, clone handlers, or dispatch events. Those responsibilities belong to the Inbound Runtime and its Dispatch Context.

## External Webhook Sources

Host applications may register non-messaging webhooks through `WebhookPlugin`
and an `IWebhookProcessor`. External Webhook Sources include payment systems,
CRMs, operational tools, and other systems that are not messaging Platforms.

Public imports include:

- `from wappa import ExternalEvent`
- `from wappa import IWebhookProcessor`
- `from wappa.core.plugins import WebhookPlugin`

An `IWebhookProcessor` must provide:

- `get_source_name() -> str`
- `parse_event(request, inbox_id) -> ExternalEvent`
- `resolve_user_id(event, db) -> str | None`

`WebhookPlugin` processor mode requires an `inbox_id`. With the default route
shape, external webhooks are accepted at:

- `POST {prefix}/{inbox_id}`
- `GET {prefix}/{inbox_id}/status`

`include_inbox_id=False` is not valid for processor mode and incoming webhooks
are rejected with HTTP 400. Wappa needs the Inbox to scope Dispatch Context,
Messenger, Cache Factory, SSE identity, and event handling.

Accepted external webhooks return `{"status": "accepted"}` after Wappa snapshots
the request body and submits tracked background work. This means the event was
accepted for local processing, not that the Host Application handler completed
successfully.

The External Webhook Runtime then:

- calls `processor.parse_event(request, inbox_id)`
- rejects dispatch when `event.inbox_id` does not match the routed Inbox
- creates a DB-capable Dispatch Context for identity lookup
- calls `processor.resolve_user_id(event, db)`
- creates a user-bound Dispatch Context with Messenger and Cache Factory when a
  `user_id` is resolved
- dispatches to `WappaEventHandler.process_external_event(event)`

If no `user_id` is resolved, Wappa still dispatches the event as an inbox-level
external event. In that path, `self.messenger` and `self.cache_factory` may be
`None`; Host Applications must check them before sending messages or writing
user-scoped cache data.

External webhook delivery is best-effort by default. Processor and handler
failures are logged after the accepted response. Wappa does not currently
provide a retry policy, dead-letter store, event delivery ledger, or duplicate
suppression contract for External Webhook Sources. Host Applications that need
payment-grade reliability should enforce idempotency and persistence in their
own processor or handler until those behaviors are promoted through a separate
public contract.

`ExternalWebhookRuntime.process()` returns an internal
`ExternalWebhookProcessResult` for tests and observability. Status values are:

- `accepted_dispatch`
- `inbox_mismatch`
- `parse_failure`
- `unresolved_user`
- `dispatch_failure`

The result does not change HTTP delivery semantics: an accepted route response
still means "queued locally", not "handled successfully".

## Server-Sent Events

`publish_sse_event()` is the public best-effort SSE publisher. Host
applications may publish built-in event types or custom event types registered
with `register_sse_event_type(event_type)`.

Built-in event types are:

- `incoming_message`
- `outgoing_api_message`
- `outgoing_bot_message`
- `status_change`
- `webhook_error`

Unknown event types are rejected by `publish_sse_event()`: the function returns
`0`, logs a warning, and does not deliver an envelope. Hub publish failures are
also best-effort: the function logs and returns `0`.

`SSEEventHub.publish()` remains a low-level fan-out primitive. It does not own
event-type validation; callers should use `publish_sse_event()` unless they are
inside Wappa internals.

SSE Event Envelopes preserve the active SSE identity scope:

- `inbox_id`
- `user_id`
- `bsuid`
- `phone_number`
- `platform`
- `metadata`

## Rate Limiting

Wappa provides local per-process route-level rate limiting through:

- `RateLimitProfile(name, limit, window_seconds, key_by="client_ip")`
- `RateLimitPlugin(profiles=[...])`
- `rate_limit(profile_name)`

Supported `key_by` values are:

- `client_ip`
- `inbox_id`
- `inbox_id_and_client_ip`

`RateLimitPlugin` stores an in-memory limiter on
`app.state.wappa_rate_limiter` during startup. Routes opt in explicitly with
FastAPI dependencies, for example:

```python
from fastapi import Depends
from wappa.core.plugins import rate_limit

@router.post(
    "/webhook/{inbox_id}",
    dependencies=[Depends(rate_limit("webhook"))],
)
async def webhook(inbox_id: str):
    ...
```

When the limit is exceeded, Wappa raises HTTP 429 with a `Retry-After` header.
An unknown profile or missing `RateLimitPlugin` is a configuration error, not
fail-open behavior. Wappa does not provide Redis-backed or distributed rate
limiting in this contract.

## Messenger

`IMessenger` is Wappa's public outbound message interface. Host applications use it to send text, media, interactive, template, and specialized messages through an Inbox.

**Stable surface:**

- `from wappa.domain.interfaces import IMessenger`
- All `send_*` methods and `mark_as_read` on the interface
- `MessageResult` as the uniform return type

**Design commitment:**

- The interface stays as a single seam until the split threshold documented in `wappa/messaging/ARCHITECTURE.md` is met.
- If a split is justified in the future, it will be a clean breaking change with no compatibility aliases.
- Internal handler composition (per message family) is not part of the public contract.

## Canonical Import Paths (SDK Surface)

Host applications should prefer these shallow imports over deep internal paths.
Internal module paths (`wappa.core.*`, `wappa.persistence.redis.redis_handler.*`) are implementation details and may change without notice.

### Top-level (`from wappa import ...`)

- `Wappa`, `WappaBuilder`, `WappaPlugin`, `WappaEventHandler`
- `ExternalEvent`, `CronEvent`, `ExpiryPlugin`, `expiry_registry`
- `IIdentityResolver`, `PassthroughIdentityResolver`, `IWebhookProcessor`
- `CustomWebhook`, `WappaContext`

### SSE (`from wappa.sse import ...`)

- `publish_sse_event`, `publish_api_sse_event`
- `sse_event_scope`, `get_sse_context`, `classify_meta_identifier`
- `update_identity`, `update_metadata`, `flush_incoming_sse`, `derive_identifiers`
- `SSEEventHub`, `SSESubscription`, `SSEEventType`, `register_sse_event_type`

### Messaging (`from wappa.messaging import ...`)

- `IMessenger`, `WhatsAppMessenger`, `WhatsAppClient`
- `WhatsAppMediaHandler`, `WhatsAppInteractiveHandler`, `WhatsAppTemplateHandler`, `WhatsAppSpecializedHandler`
- `MessengerMiddleware`, `MessengerPipeline`, `SendInvocation`, `SendNext`, `PRIORITY_CACHE`

### Persistence (`from wappa.persistence import ...`)

- `create_cache_factory`, `get_cache_factory`, `ICacheFactory`
- `TypedTableCache`, `ITableCache`
- `RedisCacheFactory`, `RedisClient`, `redis_ops`
- `IStateRepository`, `IUserRepository`, `IExpiryRepository`, `ISharedStateRepository`

`TypedTableCache[T]` is a convenience wrapper over an existing `ITableCache`:

- `TypedTableCache(cache, table_name, model, default_ttl=None)`
- `get(pkid) -> T | None`
- `upsert(pkid, data, ttl=None) -> bool`
- `delete(pkid) -> int`
- `exists(pkid) -> bool`
- `update_field(pkid, field, value, ttl=None) -> bool`

Inbox scoping still comes from the `ICacheFactory` / `ITableCache` that creates
the underlying table cache. Wappa does not expose `cache_space` or versioned
table cache semantics.

### Webhooks (`from wappa.webhooks import ...`)

- `InboundMessageWebhook`, `StatusWebhook`, `ErrorWebhook`, `SystemWebhook`, `CustomWebhook`
- `BaseMessage`, `InboxBase`, `SystemEventDetail`
- `WhatsAppWebhook`, `WhatsAppMetadata`, `PlatformType`, `SystemEventType`

### Domain Interfaces (`from wappa.domain.interfaces import ...`)

- `IMessenger`, `IMediaHandler`, `ICacheFactory`
- `IExpiryCache`, `IStateCache`, `ITableCache`, `IUserCache`
- `IInboxCredentialStore`, `InboxCredentials`, `InboxNotFoundError`
- `IIdentityResolver`, `PassthroughIdentityResolver`

### API (`from wappa.api import ...`)

- `TemplateStateService`
- `convert_body_parameters`, `raise_for_failed_result`, `require_inbox_context`
- `dispatch_message_event`, `fire_api_event`, `resolve_event_user_id`

### Schemas (`from wappa.schemas import ...`)

- `looks_like_bsuid`

### Core Logging (`from wappa.core.logging import ...`)

- `get_logger`, `get_app_logger`, `setup_app_logging`
- `get_current_inbox_context`, `set_request_context`

### Core Expiry (`from wappa.core.expiry import ...`)

- `expiry_registry`, `run_expiry_listener`
- `get_app_context`, `AppContext`
- `create_expiry_messenger`, `create_expiry_cache_factory`, `parse_inbox_from_expired_key`

### Migration Notes (v0.13.0)

- `from wappa.core.expiry.listener import get_fastapi_app` is removed. Use `from wappa.core.expiry import get_app_context` then `get_app_context().get_app()`.
- Deep paths under `wappa.schemas.whatsapp`, `wappa.schemas.factory`, and `wappa.schemas.core.base_*` are removed. Use `wappa.webhooks` instead.
