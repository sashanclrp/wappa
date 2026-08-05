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
- `from wappa.webhooks import CallWebhook`
- `from wappa.webhooks.core.webhook_interfaces import InboundMessageWebhook`
- `from wappa.webhooks import StatusWebhook`
- `from wappa.webhooks import ErrorWebhook`
- `from wappa.webhooks import SystemWebhook`
- `from wappa.webhooks import CustomWebhook`
- `from wappa.webhooks import UniversalWebhook`
- `from wappa.webhooks.whatsapp import WhatsAppWebhook`
- `from wappa.webhooks.whatsapp.*` platform payload schemas

WhatsApp built-in payload schemas are strict (`extra="forbid"`).
`MessageContext.from_bsuid` maps Meta's `context.from_user_id` reply identifier.
Incoming WhatsApp models also retain optional portfolio-parent identifiers,
group identifiers, username-only contacts, and call-permission replies. Status
Universal Models expose portfolio and parent BSUIDs plus group participant
identity when Meta sends them.
For incoming group messages, `conversation_id` is the Meta `group_id` and
`conversation_type` is `group`; `sender_id` remains the participant's BSUID or
phone fallback. Group status `user_id` resolves from the participant identity,
not the group ID.
Consumer `edit` and `revoke` messages use `MessageType.EDIT` and
`MessageType.REVOKE`. Coexistence `history`, `smb_message_echoes`, and
`smb_app_state_sync` values dispatch through `SystemWebhook`; the validated
Meta value is retained at `event_detail.coexistence_payload`.
Unknown built-in fields remain HTTP 400 contract failures and emit the stable
critical log signature `WHATSAPP_WEBHOOK_CONTRACT_DRIFT`; production hosts are
expected to alert on that signature.

`InboundMessageWebhook` is the only public inbound-message Universal Model name. Wappa does not provide a compatibility alias for previous inbound-message model names.

`CallWebhook` dispatches WhatsApp Calling connect, terminate, and status events
to `WappaEventHandler.process_call(webhook)`. The default hook is a no-op because
hosts may deliberately ignore calling events.

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
- `from wappa import HMACSignatureVerifier`
- `from wappa import ExternalEventRegistry`, `from wappa import DispatchReport`
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

### Webhook Signature Verification

`HMACSignatureVerifier` verifies signed External Webhook Source requests. It is
used inside a processor's `parse_event()`; Wappa never calls it for you, because
only the processor knows which secret and header a source uses.

```python
verifier = HMACSignatureVerifier(
    secret=settings.stripe_webhook_secret,
    header="Stripe-Signature",
    algorithm="sha256",   # any hashlib algorithm
    prefix="",            # e.g. "sha256=" for GitHub-style headers
    encoding="hex",       # or "base64"
)

verifier.verify(raw_body, request.headers) -> bool
verifier.verify_signature(raw_body, signature_string) -> bool
verifier.sign(raw_body) -> str
```

`verify()` returns `False` — it does not raise — for a missing header, a wrong
prefix, an undecodable signature, or a digest mismatch. Header lookup is
case-insensitive. Hex casing and base64 padding variants do not affect the
verdict. Misconfiguration (empty secret, unknown algorithm or encoding) raises
`ValueError` at construction. Providers that sign something other than the raw
body build that string themselves and pass it as the payload.

### External Event Registry

`ExternalEventRegistry` routes `ExternalEvent` instances to async handlers by
`(source, event_type)`. It is transport-free and Host Application-driven: Wappa
does not install it into the External Webhook Runtime.

```python
registry = ExternalEventRegistry()

@registry.on("mercadopago", "payment.approved")
async def credit_wallet(event: ExternalEvent) -> None: ...

class MyHandler(WappaEventHandler):
    async def process_external_event(self, event):
        report = await registry.dispatch(event)
```

- `register(source, event_type, handler)` / `on(source, event_type="*")`
- `handlers_for(source, event_type) -> list[handler]`
- `dispatch(event) -> DispatchReport(matched, succeeded, errors, failed)`

Matching runs in three tiers, most specific first, and within a tier in
registration order: exact (`payment.approved`), prefix (`payment.*`, matching
any depth below it), then any (`*`). A handler matched by several tiers runs
once per event. Handlers must be async; sync callables are rejected at
registration.

Dispatch is best-effort per handler: a raising handler is logged and the
remaining handlers still run. `DispatchReport.errors` carries
`(handler_name, exception)` for callers that need to react.

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

## Request Correlation

`RequestIdMiddleware` is installed by `WappaCorePlugin` as Wappa's outermost
middleware, so every application built through `Wappa` or a builder that adds
the core plugin gets correlation IDs with no extra configuration.

Behavior:

- Reads the inbound `X-Request-ID` header when it is non-empty, printable, and
  at most 128 characters; otherwise generates a UUID4 hex value.
- Publishes the ID to `request.state.request_id` and to the request-scoped
  logging context for the duration of the request.
- Echoes the ID on the response under the same header.
- Adds `request_id` to `WappaJSONFormatter` records while a request scope is
  active, and omits the field outside one (background work, expiry handlers,
  cron jobs).
- Clears the context once the response is produced, including when the handler
  raises.

Configuration is per-instance, for hosts that install it themselves:

- `RequestIdMiddleware(app, header_name="X-Request-ID", trust_inbound=True)`
- `trust_inbound=False` always generates a fresh ID, for untrusted edges.

Public imports:

- `from wappa.api.middleware import RequestIdMiddleware, DEFAULT_REQUEST_ID_HEADER`
- `from wappa.core.logging import get_current_request_id, set_request_context`

`set_request_context(inbox_id=None, user_id=None, request_id=None)` remains the
way to populate context outside HTTP (background work, tests).

## Resilience

`wappa.resilience` provides transport-neutral retry helpers for transient
integration failures. They are reusable by transport adapters, webhook
processors, credential stores, and external platform clients.

```python
from wappa.resilience import RetryPolicy, retry_transient_http

@retry_transient_http(policy=RetryPolicy(attempts=5))
async def fetch_profile(client, url):
    response = await client.get(url)
    response.raise_for_status()
    return response.json()
```

Public surface:

- `RetryPolicy(attempts=3, initial_delay=0.2, max_delay=5.0, multiplier=2.0, jitter=0.25)`
  and `DEFAULT_RETRY_POLICY`
- `retry_async(policy=..., retry_on=predicate, operation=None)`
- `retry_transient_http(policy=..., operation=None)`
- `retry_transient_db(policy=..., operation=None)`
- `is_transient_http_error(error)`, `is_transient_db_error(error)`
- `TRANSIENT_HTTP_STATUS_CODES`, `TRANSIENT_DB_ERROR_TYPES`,
  `TRANSIENT_DB_ERROR_PATTERNS`

Classification contract:

- HTTP transient: timeouts, connect/read/write failures, remote protocol
  errors, pool timeouts, DNS and TLS failures, and responses with status
  `408`, `425`, `429`, `500`, `502`, `503`, `504`. Status retries require the
  wrapped function to raise `httpx.HTTPStatusError` (e.g. via
  `response.raise_for_status()`).
- HTTP non-transient: every other 4xx, and non-HTTP exceptions such as a
  payload `ValueError`.
- Database transient: connection refused/reset, dropped server connections,
  DNS failures, and OS-level socket errors.
- Database non-transient: SQLAlchemy pool checkout timeouts (the pool is
  already drained), integrity violations, and query errors.

`asyncio.CancelledError` is never retried. The final attempt's exception
propagates unchanged, so callers keep the original error and traceback. Only
async callables are supported. Retries are per-process and in-memory; Wappa
does not provide a distributed retry or circuit-breaker contract.

## Messenger

`IMessenger` is Wappa's public outbound message interface. Host applications use it to send text, media, interactive, template, and specialized messages through an Inbox.

**Stable surface:**

- `from wappa.domain.interfaces import IMessenger`
- All `send_*` methods and `mark_as_read` on the interface
- `MessageResult` as the uniform return type

`IMessenger.send_contact_request(body, recipient, reply_to_message_id=None)` is
the capability-aware contact-information request. WhatsApp implements it with
Meta's `request_contact_info` interactive payload; platforms that don't support
the feature raise `NotImplementedError` unless their Messenger overrides it.

**Design commitment:**

- The interface stays as a single seam until the split threshold documented in `wappa/messaging/ARCHITECTURE.md` is met.
- If a split is justified in the future, it will be a clean breaking change with no compatibility aliases.
- Internal handler composition (per message family) is not part of the public contract.

## Inbox-scoped Template transport

Host Applications that send Templates use the shallow `wappa.messaging`
contract instead of constructing Wappa clients, handlers, factories, sessions,
or Messenger Pipelines:

- `OutboundRuntime.from_app(app).templates(inbox_id)`
- `InboxTemplateTransport.send(request)`
- `TextTemplateTransportRequest`, `MediaTemplateTransportRequest`,
  `LocationTemplateTransportRequest`
- `TemplateTransportMediaHeader`, `TemplateTransportLocationHeader`,
  `TemplateTransportRouting`, `TemplateTransportParameter`, `TemplateCategory`,
  `TemplateMediaType`, `TemplateAuthenticationMethod`
- `PhoneNumberTemplateRecipient`, `BsuidTemplateRecipient`, `TemplateAddressKind`
- `TemplateRoutingPolicy`, `TemplateEndpoint`, `TemplateRoutingReason`
- `TemplateTransportOutcome`, `TemplateTransportResult`

Requests reject unknown fields and contain only platform-facing values. Agent,
Campaign, authority, attribution, Conversation, Reply State, state-cache,
persistence, and arbitrary Host metadata do not cross this boundary.

Every request contains exactly one discriminated Delivery Address. Phone
numbers are normalized and sent in Meta's `to` field. Regular and parent
BSUIDs are normalized and sent in Meta's `recipient` field. Usernames are not
accepted as outbound addresses. Authentication Templates require their method
and reject BSUID addresses.

Category-default routing sends marketing Templates to `/marketing_messages`
and utility/authentication Templates to `/messages`. The only fallback is the
explicit `cloud_messages_fallback` policy for marketing. Wappa never retries a
rejection or ambiguous call through the other endpoint. Results report the
selected endpoint and routing reason.

Outcomes mean exactly:

- `accepted`: the platform accepted the call and returned a Message ID;
- `rejected`: a request or platform response proves the send was not accepted;
- `transport_unavailable`: Wappa could not start a platform call, including drain;
- `indeterminate`: Wappa cannot prove whether the platform accepted the call.

Acceptance does not claim delivery, read, reply, or Host Application commit.
Callers must not automatically resend an `indeterminate` result.

Wappa's standalone Template HTTP adapter is disabled by default. A standalone
host opts in with `Wappa(include_template_transport_api=True)`. Embedding hosts
receive no raw Template mutation routes unless they make that choice.

## HTTP route composition

Wappa's WhatsApp surface is grouped by **what an unauthenticated caller could
do**, not by which module a route lives in. See
[ADR-0007](adr/0007-embedded-outbound-route-control.md) and
[ADR-0009](adr/0009-route-capability-groups.md).

| Capability | `standalone` (default) | `embedded` |
| --- | --- | --- |
| Ordinary + interactive outbound sends | mounted | **omitted** |
| Template outbound sends | omitted | omitted |
| `DELETE /media/{id}` (destroys a platform asset) | mounted | **omitted** |
| `POST /media/upload` (creates a platform asset) | mounted | mounted |
| `/state-handlers/*` (any recipient's cached state) | mounted | **omitted** |
| Media download / info / limits | mounted | mounted |
| Health, limits, validation, Template info | mounted | mounted |
| `wappa.messaging` services | available | available |

```python
Wappa(route_profile="embedded")            # the whole group, one argument
Wappa(route_profile="embedded", include_media_upload_api=False)   # and close upload
```

Individual capabilities are also settable on their own and always win over the
profile: `include_outbound_transport_api`, `include_template_transport_api`,
`include_media_management_api`, `include_media_upload_api`,
`include_state_handler_api`. Each defaults to `None`, meaning "take it from the
profile".

**Ejecting sends implies the embedded profile.** Passing
`include_outbound_transport_api=False` without naming a profile also omits
media management and the state-handler API, because a host that owns its send
boundary owns the rest of the mutation surface too.

Under `embedded`, the only mounted route that reaches the platform or rewrites
stored state is `POST /media/upload`; one flag closes it. The
`/specialized/validate-*` routes are `POST` because they take a body, but they
perform no I/O and change nothing.

Route composition never gates sending. `IMessenger`, `OutboundRuntime`, and
`InboxTemplateTransport` behave identically under every profile; what a profile
removes is the *unauthenticated HTTP path* to them.

`create_whatsapp_router(profile=..., include_*=...)` is the underlying
composition function for hosts assembling routers directly.

**Upgrade note.** Standalone applications need no action. Hosts already passing
`include_outbound_transport_api=False` get the wider gating automatically and
should confirm they did not depend on Wappa serving `/state-handlers/*` or
`DELETE /media/{id}` over an unauthenticated route.

## Outbound payload classification

`classify_outbound_payload(payload)` names the transport family of any
validated Wappa outbound schema. It is pure, has no I/O, and reads nothing but
the payload's own shape.

- `OutboundClassification(family, subkind)` with `family` in `text`, `media`,
  `interactive`, `location`, `contact`, `template`, `read_receipt`
- `subkind` names the variant where a family has several: `image` / `video` /
  `audio` / `document` / `sticker`, `button` / `list` / `cta` /
  `location_request`, and `text_header` / `media_header` / `location_header`
- `is_template` — whether the payload is a Template envelope
- `message_type` — the label Wappa reports in outbound API events. Media and
  interactive sends report their variant (`"image"`, `"button"`); every
  Template reports `"template"`, because which header it carries does not
  change what kind of send it was.
- `UnsupportedOutboundPayloadError` for anything that is not an outbound send
  schema, including a base class that names no concrete transport

All three Template envelope variants classify as one `template` family and keep
their header as a subkind. A Host Application subclass of a concrete schema
classifies as the schema it extends.

**Classification is transport shape, not product authority.** A payload is a
Template because it is a Template envelope — never because of who is sending
it, which Conversation or Campaign it belongs to, or what metadata rides along.
Whether a given send is *permitted* is a Host Application question, and this
function is deliberately unable to answer it.

## Canonical Import Paths (SDK Surface)

Host applications should prefer these shallow imports over deep internal paths.
Internal module paths (`wappa.core.*`, `wappa.persistence.redis.redis_handler.*`) are implementation details and may change without notice.

### Top-level (`from wappa import ...`)

- `Wappa`, `WappaBuilder`, `WappaPlugin`, `WappaEventHandler`
- `ExternalEvent`, `CronEvent`, `ExpiryPlugin`, `expiry_registry`
- `IIdentityResolver`, `PassthroughIdentityResolver`, `IWebhookProcessor`
- `HMACSignatureVerifier`, `ExternalEventRegistry`, `DispatchReport`
- `CustomWebhook`, `WappaContext`

### SSE (`from wappa.sse import ...`)

- `publish_sse_event`, `publish_api_sse_event`
- `sse_event_scope`, `get_sse_context`, `classify_meta_identifier`
- `update_identity`, `update_metadata`, `flush_incoming_sse`, `derive_identifiers`
- `SSEEventHub`, `SSESubscription`, `SSEEventType`, `register_sse_event_type`

### Messaging (`from wappa.messaging import ...`)

- `IMessenger`
- `MessengerMiddleware`, `MessengerPipeline`, `SendInvocation`, `SendNext`, `PRIORITY_CACHE`
- `classify_outbound_payload`, `OutboundClassification`, `OutboundTransportFamily`,
  `OutboundTransportSubkind`, `UnsupportedOutboundPayloadError`
- `OutboundRuntime`, `InboxTemplateTransport`
- `TextTemplateTransportRequest`, `MediaTemplateTransportRequest`, `LocationTemplateTransportRequest`
- `TemplateTransportMediaHeader`, `TemplateTransportLocationHeader`, `TemplateTransportRouting`
- `TemplateTransportParameter`, `TemplateCategory`, `TemplateMediaType`, `TemplateAuthenticationMethod`
- `PhoneNumberTemplateRecipient`, `BsuidTemplateRecipient`, `TemplateAddressKind`
- `TemplateRoutingPolicy`, `TemplateEndpoint`, `TemplateRoutingReason`
- `TemplateTransportOutcome`, `TemplateTransportResult`

`WhatsAppClient`, `WhatsAppMessenger`, their handlers, `MessengerFactory`, and
session lifecycle classes are implementation details. Host Applications do not
construct or import them.

### Persistence (`from wappa.persistence import ...`)

- `create_cache_factory`, `get_cache_factory`, `ICacheFactory`
- `TypedTableCache`, `VersionedTableCache`, `ITableCache`, `build_table_name`
- `TableRowTransition`, `TableTransitionResult`, `TypedRowTransition`
- `RedisCacheFactory`, `RedisClient`, `redis_ops`
- `IUserCache`, `IStateCache`, `IExpiryCache`, `ITableCache`

`TypedTableCache[T]` is a convenience wrapper over an existing `ITableCache`:

- `TypedTableCache(cache, table_name, model, default_ttl=None)`
- `get(pkid) -> T | None`
- `upsert(pkid, data, ttl=None) -> bool`
- `delete(pkid) -> int`
- `exists(pkid) -> bool`
- `update_field(pkid, field, value, ttl=None) -> bool`
- `create_if_absent(pkid, data, ttl=None) -> TypedRowTransition[T]`
- `replace_if(pkid, data, expected, ttl=None) -> TypedRowTransition[T]`

- `renew_ttl(pkid, ttl=None) -> bool`

Inbox scoping still comes from the `ICacheFactory` / `ITableCache` that creates
the underlying table cache.

#### Atomic row transitions

`create_if_absent` and `replace_if` each perform their condition and their
write as one backend operation. Redis does it in a single server-side script;
the memory and JSON backends do it under the lock that guards the namespace or
the cache file. No backend reads, decides, and writes as separate steps, so a
transition cannot be lost to an interleaved writer. The same two operations
exist on `ITableCache` (untyped rows) and on `VersionedTableCache[T]`.

`TableRowTransition` names the one thing a call proves:

- `created` — this call created the row; no other caller had it
- `replaced` — this call replaced the row, and `expected` still held
- `already_exists` — another caller created it first
- `condition_not_met` — the row exists but no longer matches `expected`
- `missing` — there is no row to replace

`written` is `True` for exactly `created` and `replaced`. On the two refusals
that have something to report, `row` carries the state the backend actually
holds — the winning row, or the row that moved on — so a caller does not need a
follow-up read whose answer could already be stale. `TypedTableCache` validates
that row against the configured model, exactly like every other read.

`expected` maps field names to scalar values; every listed field must be
present and equal. Values are compared through one canonical encoding, so
`Status.PENDING` and `"pending"` match the same stored row on every backend.
Containers are rejected: their encoded form depends on ordering, which no
backend guarantees. An empty `expected` is rejected — that is `upsert`.

A refused transition writes nothing and leaves the row's TTL untouched. A
successful one applies the call's `ttl`, or the wrapper's `default_ttl`, or the
backend default, in that order. Replacement is a whole-row write on every
backend: fields the new row omits are gone, not merged.

Wappa does not interpret the fields a caller conditions on. Status names,
revision counters, and owner identifiers are Host Application concepts; this
contract only guarantees that the comparison and the write cannot be separated.

#### Stored value round trip

Read a row through a Pydantic model and it round-trips losslessly on every
backend — that is what `TypedTableCache[T]` and the `models=` parameter are
for, and it is the supported path.

Untyped dict reads are best-effort. On Redis a top-level boolean is stored as
`"1"`/`"0"`, which an integer `1` and the string `"1"` also spell, so an
untyped read of any of the three returns `True`. This is a deliberate
compatibility contract, not a defect — Host Applications read these fields
directly from outside Wappa. [ADR-0008](adr/0008-redis-hash-boolean-encoding.md)
records the decision, the mitigation, and one hard rule: **never store `"1"` or
`"0"` as a string value**, because a `str` field will then reject the `True` it
reads back.

#### Enumeration and identifier safety

Bulk operations (`delete_table`, `list_pkids`, `get_all`, `find_by_field`,
`delete_all_by_pkid`, `list_handlers`, `delete_by_handler_prefix`,
`delete_all_by_identifier`) match the identifiers you gave them literally.
An `inbox_id`, `cache_space`, table name, `pkid`, `user_id`, handler name, or
trigger identifier containing `*`, `?`, `[`, `]`, or `\` is matched as those
characters, not as pattern syntax. `:` is still folded to `_` inside a segment,
as it always was.

`IExpiryCache` has no `delete_all_for_user()`. A trigger key carries an action
and an identifier, never a user, so the interface cannot know which triggers a
user caused. Callers that use the user id as the trigger identifier say so:
`delete_all_by_identifier(user_id)`. The identically named methods on
`IStateCache` and `IAIStateCache` remain — their keys really are user-scoped.

`cache_space` is an optional host-owned namespace segment folded into the table
name as `"{cache_space}:{table_name}"`. Wappa never assigns one; omitting it
leaves key shapes unchanged. `build_table_name(table_name, cache_space=None)` is
the public composition helper. Both segments must be non-empty and must not
contain `:` or `@`.

`VersionedTableCache[T]` adds bump-to-invalidate semantics on top of the same
`ITableCache`:

- `VersionedTableCache(cache, table_name, model, default_ttl, cache_space=None)`
- the same row API as `TypedTableCache` (`get`, `upsert`, `delete`, `exists`,
  `update_field`, `renew_ttl`)
- `current_version() -> int` (starts at `1`)
- `bump_version() -> int` — invalidates every row in one operation
- `current_table_name() -> str` — e.g. `"crm:agents@v2"`

Rows live under a generation-suffixed table, so a bump makes every row
unreachable without enumerating keys, and is immediately visible to other
processes sharing the backend. Generations are per logical table and per cache
space: bumping one table does not affect its neighbours. `default_ttl` is
required and must be positive — orphaned generations are reclaimed only by TTL.
The generation counter is stored with its own longer TTL, refreshed on each
bump, so it always outlives the rows a bump orphans. Each operation reads the
counter first, costing one extra cache read.

### Webhooks (`from wappa.webhooks import ...`)

- `InboundMessageWebhook`, `StatusWebhook`, `ErrorWebhook`, `SystemWebhook`, `CustomWebhook`
- `CallWebhook`
- `BaseMessage`, `InboxBase`, `SystemEventDetail`
- `WhatsAppWebhook`, `WhatsAppMetadata`, `PlatformType`, `SystemEventType`

`SystemEventType` members: `NUMBER_CHANGE`, `USER_ID_CHANGE`, `MARKETING_PREFERENCE`,
and the account-scoped coexistence events `ACCOUNT_OFFBOARDED`, `ACCOUNT_RECONNECTED`.
Account-scoped events populate `SystemEventDetail.waba_id` (and `phone_number_id` /
`reason` where applicable) and dispatch with `SystemWebhook.user is None` — they target a
Platform Account (WABA), not a User. Consumers handle them in `process_system_webhook`.

`USER_ACTION` covers Meta's `user_actions` payload — user interaction events such as marketing message link clicks, delivered on the `messages` field with no `messages` and no `contacts`. It populates `SystemEventDetail.action_type` (Meta's action name, e.g. `marketing_messages_link_click`) and `SystemEventDetail.user_action` (the full action entry serialized, including any action-specific `<action_type>_data` object). Like account-scoped events it dispatches with `SystemWebhook.user is None` — the payload carries no user identity. Action entries validate permissively: an `action_type` Wappa has not seen keeps its extra keys and still dispatches, rather than failing the delivery. Unknown keys elsewhere in the change `value` remain strict contract drift.

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
- `get_current_inbox_context`, `get_current_user_context`, `get_current_request_id`
- `set_request_context`, `clear_request_context`, `get_context_info`

### Resilience (`from wappa.resilience import ...`)

- `RetryPolicy`, `DEFAULT_RETRY_POLICY`
- `retry_async`, `retry_transient_http`, `retry_transient_db`
- `is_transient_http_error`, `is_transient_db_error`
- `TRANSIENT_HTTP_STATUS_CODES`, `TRANSIENT_DB_ERROR_TYPES`, `TRANSIENT_DB_ERROR_PATTERNS`

### Middleware (`from wappa.api.middleware import ...`)

- `RequestIdMiddleware`, `DEFAULT_REQUEST_ID_HEADER`

### Core Expiry (`from wappa.core.expiry import ...`)

- `expiry_registry`, `run_expiry_listener`
- `get_app_context`, `AppContext`
- `create_expiry_messenger`, `create_expiry_cache_factory`, `parse_inbox_from_expired_key`

### Migration Notes (v0.13.0)

- `from wappa.core.expiry.listener import get_fastapi_app` is removed. Use `from wappa.core.expiry import get_app_context` then `get_app_context().get_app()`.
- Deep paths under `wappa.schemas.whatsapp`, `wappa.schemas.factory`, and `wappa.schemas.core.base_*` are removed. Use `wappa.webhooks` instead.
