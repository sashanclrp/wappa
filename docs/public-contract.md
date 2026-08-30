# Public Contract

This file tracks Wappa surfaces that host applications may import, call, configure, subscribe to, or depend on.

## Inbox identity

Wappa's globally unique runtime identity is qualified by Platform. A raw `inbox_id` is unique only inside one Platform.

- `InboxRef(platform, inbox_id)` — for WhatsApp, `inbox_id` is Meta's exact `phone_number_id`. `InboxRef.whatsapp(phone_number_id)` is the shorthand.
- `PlatformAccountRef(platform, platform_account_id)` — for WhatsApp, the WABA ID (`entry[].id`).
- Both are frozen, hashable, orderable (Platform first, then native identifier), reject blank or unsafe values (`:`, glob characters, whitespace, `__`), and expose one Wappa-owned `cache_namespace`. WhatsApp keeps its raw `phone_number_id` as the namespace so existing keys stay readable; every other Platform is qualified as `<platform>__<inbox_id>`. Hosts never rebuild the namespace by concatenation.

Public imports: `from wappa import InboxRef, PlatformAccountRef` or `from wappa.domain.inbox import ...`.

## Inbox Routing Mode

`InboxRoutingMode` has exactly two members; an omitted mode is `legacy`. The modes never fall back to one another and a mixed configuration fails at build time with `InboxConfigurationError`.

| | `legacy` | `explicit` |
| --- | --- | --- |
| Selected by | default, `Wappa(inbox_routing="legacy")`, `SYSTEM_INBOX_ROUTING_MODE=legacy` | `Wappa(inbox_routing="explicit")`, `WappaBuilder.with_inbox_routing("explicit")`, `SYSTEM_INBOX_ROUTING_MODE=explicit` |
| Requires | the complete `WP_ACCESS_TOKEN` + `WP_PHONE_ID` + `WP_BID` bundle | an `IInboxDirectorySource` and `SYSTEM_TOKEN_ENC_KEY` |
| Rejects | any `IInboxDirectorySource` | any of `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, `WP_BID` |
| Inboxes | one: `WP_PHONE_ID`, with `WP_BID` as its Platform Account | every active record the source returns |
| HTTP default Inbox | `WP_PHONE_ID` when `X-Wappa-Inbox-ID` is absent | none; the header is required |

Only the legacy settings adapter built by Wappa's assembly reads the three `WP_*` variables. `WP_ACCESS_TOKEN` keeps its name as a legacy WhatsApp input; it is not renamed `META_ACCESS_TOKEN`.

Health (`/health`, `/health/detailed`) reports `inbox_routing_mode`, whether the Inbox Directory is configured (and, detailed, reachable), whether a legacy default Inbox exists and its `inbox_id`, and Meta callback readiness. It never returns tokens, envelopes, App Secrets, encryption keys, full records, or raw exception strings.

## Inbox Directory (explicit mode)

Wappa ships one mandatory `InboxDirectory` over `InboxDirectoryTable`, a Wappa-owned Table Cache under the System Scope. Hosts cannot replace its model, cache shape, TTL rules, indexes, or mutation behaviour. The Host's only adaptation point is the read-only source:

```python
class IInboxDirectorySource(Protocol):
    async def get_inbox(self, inbox_ref: InboxRef) -> InboxCredentialRecord | None: ...
    async def list_inboxes_for_platform_account(
        self, account_ref: PlatformAccountRef
    ) -> tuple[InboxCredentialRecord, ...]: ...
```

Both reads use the Host's primary database path by default. A Host that serves them from a replica accepts the stale-credential risk itself.

### Canonical records

`from wappa.domain.inbox import ...`

- `WhatsAppActiveInboxCredentialRecord`: `schema_version=1`, `platform="whatsapp"`, `status="active"`, `inbox_id`, `platform_account_id`, `access_token: EncryptedSecretEnvelope`, `credential_version` (positive, monotonic across the Inbox's lifetime), `updated_at` (timezone-aware).
- `WhatsAppInactiveInboxCredentialRecord`: the same fields without `access_token`. An inactive record cannot carry credential material.
- `InboxCredentialRecord`: the Platform- and status-discriminated union (v0.27 ships only WhatsApp members). `parse_inbox_credential_record(data)` validates any object into it; `dump_record_for_storage(record)` is the only dump that carries ciphertext. Every other `model_dump`, `repr`, or log masks it, and a masked envelope cannot be re-loaded.
- `EncryptedSecretEnvelope(format_version=1, ciphertext)`: Wappa's authenticated, context-bound secret. Hosts persist and return it, never construct, alter, or decrypt it.
- `PlatformAccountActiveIndexRecord` / `PlatformAccountEmptyIndexRecord`: the cached reverse index rows. They are projections, never authority.

### Wappa-owned commands

`runtime = app.state.inbox_runtime` after build exposes `credential_service` (`InboxCredentialService`) and `directory` (`InboxDirectory`) in explicit mode.

- `create_active_record(inbox_ref=, account_ref=, access_token=SecretStr, credential_version=1)` → active record. Call it before persisting; store what it returns.
- `rotate_active_record(previous, access_token=SecretStr, account_ref=None)` → version + 1.
- `create_inactive_record(previous)` → version + 1, no token.
- `rotate_encrypted_record(record)` → the same record re-encrypted under the active key, without exposing plaintext.
- `await directory.refresh_inbox(inbox_ref)` → reloads through the source after the Host commits, validates, updates the primary row and both affected account indexes, evicts cached Messengers, returns the record (or `None` when the source confirms absence). Idempotent; raises on failure.
- `await directory.deactivate_inbox(inbox_ref)` → the same, requiring the source to report the Inbox inactive; raises `InboxMutationConflictError` if it is still active and `InboxNotFoundError` if it is absent.

There is no `upsert(record)`, no Host-written cache row, and no normal hard-delete command.

### Freshness, versions, and repair

| Record | TTL | Read behaviour |
| --- | --- | --- |
| Active Inbox primary row | 60 min | renewed on every validated hit |
| Active Platform Account index | 60 min | renewed on every validated hit |
| Inactive Inbox row | fixed 60 min | never renewed |
| Confirmed absent Inbox row | fixed 60 min | never renewed |
| Confirmed empty account index | fixed 60 min | never renewed |

A cache miss makes one source call. Source or cache failures raise `InboxDirectoryUnavailableError` and never create a negative record. A higher `credential_version` wins; a lower one is stale (`InboxMutationConflictError`); an equal version is accepted only for an identical record, and that retry still repairs indexes and evicts Messengers. Primary rows are written before indexes; retrying the same command repairs partial work. TTL is never the revocation mechanism: call `deactivate_inbox`.

The Platform Account index is validated on every use: each listed member must be active, be the same `InboxRef`, and belong to the requested `PlatformAccountRef`. Any corruption triggers one synchronous source reload and repair; repair failure is unavailable (503). A valid index cannot detect an omitted member, so Hosts must call `refresh_inbox` after onboarding, rotation, WABA reassignment, and deactivation.

### Encryption boundary and key rotation

```text
SYSTEM_TOKEN_ENC_KEY=<active Fernet key>
SYSTEM_TOKEN_ENC_PREVIOUS_KEYS=<optional, ordered, comma-separated older keys>
```

Wappa encrypts a document binding `format_version`, `platform`, `inbox_id`, the credential field name, and the plaintext. Decryption re-checks those bindings, so ciphertext copied into another Inbox or field fails with `InboxCredentialIntegrityError`. Reads try the active key first and then the previous keys; a cache read that only succeeds under a previous key is rewritten under the active key. Durable rows are migrated with `rotate_encrypted_record`. Remove an old key only after every durable record is re-encrypted and committed, every deployment reads the active key, at least the 60-minute directory TTL has passed since the last old-key cache write, and the deployment overlap window has ended. Losing every accepted key makes stored credentials unrecoverable. Startup rejects a missing or malformed key without echoing key material.

Tokens are never hashed. Wappa has to reproduce the exact bearer value to place it in Meta's `Authorization` header, and a cryptographic hash is intentionally irreversible, so a hashed token could never authenticate an outbound call. The only valid representations for a stored Inbox credential are Wappa's reversible `EncryptedSecretEnvelope` or an external secret manager; plaintext is never a valid durable or cache value, and `SecretStr` alone is not storage protection because it masks representations without encrypting anything.

`CredentialCodec` and `SecretBinding` (`from wappa.core.security import ...`) are the codec surface; Hosts do not need them beyond `CredentialCodec.generate_key()`.

### Typed failures

`from wappa.domain.inbox import ...` — all subclass `InboxDirectoryError`:

| Error | Meaning |
| --- | --- |
| `InboxConfigurationError` | startup cannot select one credential authority or Meta configuration |
| `InboxNotFoundError` | a healthy lookup confirmed the Inbox unknown or inactive |
| `InboxMembershipError` | known identities contradict the required Platform Account relation |
| `InboxDirectoryUnavailableError` | cache, source, or another required dependency failed |
| `InboxCredentialIntegrityError` | the record or envelope failed validation and cannot be used |
| `InboxMutationConflictError` | a mutation lost to a newer or conflicting version |

Messages may name qualified identity; they never contain tokens, ciphertext, keys, payloads, or source queries. Programmatic entry points raise these; HTTP boundaries map them as documented below.

## Meta Application Configuration

One Wappa application binds to one Meta App. `MetaApplicationConfig(app_secret, whatsapp_webhook_verify_token, graph_api_version="v26.0", graph_base_url="https://graph.facebook.com/")` is supplied explicitly (`Wappa(meta_application_config=...)`, `WappaBuilder.with_meta_application_config`) **or** built from the environment:

| Variable | Meaning |
| --- | --- |
| `META_APP_SECRET` | the Meta App's HMAC secret for POST callbacks |
| `WP_WEBHOOK_VERIFY_TOKEN` | the shared value for the GET challenge only |
| `META_API_VERSION` | Graph API version |
| `META_BASE_URL` | Graph API base URL |

Supplying an explicit object while either environment secret is set fails startup; there is no precedence. Mounting the WhatsApp callback requires both secrets in every environment with no development bypass. An outbound-only application that mounts no callback needs neither. `META_APP_SECRET` is application-scoped: it never enters an Inbox record and `SYSTEM_TOKEN_ENC_KEY` does not encrypt it.

## Inbox Execution Context (`X-Wappa-Inbox-ID`)

Wappa's own HTTP operations have no Meta payload to route from, so an authorized caller selects the Inbox with `X-Wappa-Inbox-ID: <phone_number_id>`. **The header selects runtime scope and proves only that Wappa knows an active Inbox. It is not a credential and grants no permission.** Host authentication and authorization (for example `AuthPlugin`) decide whether the caller may operate that Inbox, and they run before Inbox resolution.

Resolution happens once per request through `get_inbox_execution_context` (`from wappa.api.dependencies import ...`): Host auth → read the header → combine with the route's Platform (WhatsApp) → legacy default when the header is absent → resolve the active record through the credential resolver → build the required capabilities → share the `InboxExecutionContext` with every dependency in the route. The context exposes `inbox_ref`, `inbox_id`, `account_ref`, `platform_account_id`, and `routing_mode`; it never exposes the decrypted token.

| Operation family | Inbox required |
| --- | ---: |
| Send text; mark read or typing | yes |
| Send image, video, audio, document, sticker | yes |
| Send buttons, list, CTA | yes |
| Send contact, location, location request | yes |
| Send text-, media-, or location-header Template | yes |
| Upload, inspect, download, or delete media | yes (download resolves the media object with the selected token first) |
| Get Template by ID/name, list Templates, get namespace | yes (WABA comes from the record; no caller-supplied WABA) |
| Inbox-specific WhatsApp health (`/api/whatsapp/health`) | yes |
| State Handler set, get, delete | yes |
| Validate contact or coordinates | no |
| Text, media, interactive, Template limits | no |
| Root health, docs, OpenAPI | no |

Local-only routes ignore a supplied header entirely: they do not validate it, bind it, or read the directory, so an unknown header or an unavailable directory cannot make them fail.

| Condition | Status |
| --- | ---: |
| Inbox-dependent route, no header, no legacy default | 400 |
| Header format invalid (checked before any directory call) | 400 |
| Healthy directory confirms unknown or inactive Inbox | 404 |
| Directory, source, cache, or decrypt unavailable | 503 |
| Host authentication or authorization failure | the Auth plugin's status |
| Local-only route with any header | normal local response |

In legacy mode the header may repeat the configured `WP_PHONE_ID`; any other value answers 404. No Inbox context leaks between sequential requests on one worker.

The former demonstration routes `/interactive/send-complex-buttons` and `/interactive/send-menu-list` are not part of the HTTP contract; their code lives in the full example.

## Dispatch Context, `db`, and `db_read`

Webhook, API-message, cron, and External Webhook Source paths bind handler clones through one `DispatchContextBuilder` (`from wappa.core.dispatch import ...`). Each background task binds its own Inbox and User context before handler work and resets it afterwards.

- `db` is the Primary Session Factory: writes and primary-consistent reads.
- `db_read` is the Read-Intent Session Factory: eventual consistency; may use a replica or the current fallback behaviour.
- Both stay optional `SessionFactory | None`. Wappa never installs a fake session. `WappaEventHandler.require_database()` turns `None` into one direct `RuntimeError`.
- Wappa supplies sessions only. It adds no Inbox predicates, Owner authorization, row-level security, or Host repository invariants. A Host that writes and must read its write uses `db`, preferably in one transaction.
- v0.27 does **not** claim database-enforced read-only `db_read`, replica cooldown, or configurable primary fallback; that is separate PostgreSQL plugin work.

## Inbox-aware identity resolution

Host applications may register `IIdentityResolver` through `WappaBuilder.with_identity_resolver(resolver)` or `Wappa.set_identity_resolver(resolver)`. Its public contract is `resolve(recipient, *, inbox_id) -> str`.

`inbox_id` is required for every resolution. A resolver must scope its lookup by both the transport recipient and the Inbox, so the same recipient can resolve to different canonical Users in different Inboxes. `PassthroughIdentityResolver` accepts the same contract and returns the recipient unchanged.

Wappa passes the active Inbox to identity resolution from the Inbox-scoped cache factory or the current outbound API context. API event construction fails when the runtime has no Inbox context; it does not create an event with an `"unknown"` Inbox.

## Universal Webhooks

Host applications import inbound webhook schemas and Universal Models from
`wappa.webhooks`.

The canonical and only Meta WhatsApp callback is `GET + POST /webhook/inboxes/whatsapp`. GET answers Meta's challenge with `MetaApplicationConfig.whatsapp_webhook_verify_token` and reads nothing else. POST is authenticated before it is parsed:

1. Wappa reads the exact body bytes once and requires `X-Hub-Signature-256: sha256=<hex HMAC-SHA256>` computed with `META_APP_SECRET`. A missing, malformed, or mismatched signature answers the same generic `401` before any JSON decoding, directory read, payload logging, or work scheduling. `MetaCallbackAuthenticator(app_secret).sign(body)` (`from wappa.core.inbound import ...`) produces the header for tests and local tools.
2. Only then is JSON decoded; a non-object root is `400`.
3. Each `entry[].changes[]` is routed: `value.metadata.phone_number_id` (or a flat `value.phone_number_id`) becomes `InboxRef.whatsapp(...)`, whose active record must belong to `PlatformAccountRef.whatsapp(entry[].id)` — a mismatch rejects the whole callback with `400`. A change without a phone number fans out to every validated active member of that WABA, sorted and duplicate-free. `entry[].id` is never an Inbox; a flat `value.waba_id` must match it.
4. Every Dispatch Context in the batch is built before any delivery is scheduled. A failure at item N schedules none of items 1..N-1.

| Condition | Status |
| --- | ---: |
| Missing, malformed, or invalid Meta POST signature | 401 |
| Invalid GET verify token | 403 |
| Malformed JSON or non-object root | 400 |
| Invalid Inbox identifier format in the authenticated payload | 400 |
| Confirmed unknown or inactive payload Inbox | 400 |
| Inbox and WABA membership mismatch | 400 |
| Confirmed WABA with no active Inboxes | 400 |
| Other structurally unroutable authenticated payload | 400 |
| Directory, cache, source, decrypt, or runtime dependency unavailable | 503 |
| Unexpected Wappa defect | 500 |

The removed `/webhook/inboxes/{inbox_id}/whatsapp` and `/webhook/messenger/{platform}/verify` routes return 404. There is no alias, redirect, flag, or deprecation route.

### Callback cutover and rollback

Deploy the version that answers `/webhook/inboxes/whatsapp` with `META_APP_SECRET`, change the Meta callback URL, complete GET verification, then send one real message to every active Inbox. Rollback needs both the previous package and the previous callback URL; reverting one alone stops delivery.

### Delivery semantics

Wappa delivers Platform events **at least once**. It does not deduplicate them, and it does not guarantee ordering across the deliveries derived from a single HTTP request.

One Platform event can reach a handler more than once through three independent multipliers:

1. Meta retries a callback it considers unacknowledged or failed.
2. Batch splitting turns one HTTP request into one delivery per entry/change pair.
3. WABA fan-out turns one account-scoped change into one delivery per active Inbox under that Platform Account.

The third multiplier is the one that changes host obligations. A WABA carrying `N` active Inboxes multiplies every account-level change by `N`, so an account-event handler that mutates shared, Inbox-independent state — a WABA-level counter, a shared billing record, an operator notification — performs that work `N` times per change.

Wappa guarantees that each delivery carries exactly one Platform change, is scoped to exactly one Inbox whose active record and WABA membership were proven, and is emitted in a deterministic Inbox order, so replaying the same payload behaves identically.

Host applications must make account-scoped handlers idempotent, key side effects on a Platform-supplied identifier rather than on arrival, and never assume one handler invocation equals one Platform event. Wappa does not supply a delivery fingerprint; deduplication is the host's responsibility.

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
Click-to-WhatsApp referrals accept an omitted `ctwa_clid`, as Meta does not send that field for WhatsApp Status ad placements. The universal `AdReferralBase` retains those referrals with `click_id=None`.
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
- `InboxRef`, `PlatformAccountRef`, `InboxRoutingMode`, `IInboxDirectorySource`, `InboxCredentialService`, `MetaApplicationConfig`

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
- `SYSTEM_SCOPE`, `create_system_table_cache`, `validate_context_id`
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

#### Table Cache Scope (`context_id`)

Table Cache is the one cache family whose namespace is a general `context_id`:
the reserved System Scope (`SYSTEM_SCOPE == "__system__"`), a Host-defined
business scope (for example an Owner identifier), or an Inbox namespace
(`InboxRef.cache_namespace`). The scopes are siblings: nothing falls back or
cascades between them. `ICacheFactory.create_table_cache(context_id=None)`
defaults to the factory's Inbox namespace; `create_system_table_cache(cache_type)`
builds a System-Scope table on the configured backend. `RedisTable`,
`MemoryTable`, and `JSONTable` take `context_id` positionally or by keyword.
This is a naming change only: `context_id="123"` builds exactly the key that
`inbox_id="123"` built before, and no Redis data migration is needed. The old
`inbox_id=` / `inbox=` keywords raise `TypeError` at construction; there is no
alias. User, State, AI State, Expiry, PubSub, and SSE caches remain
Inbox-scoped and keep `inbox_id`.

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
- `IIdentityResolver`, `PassthroughIdentityResolver`

### Inbox identity and directory (`from wappa.domain.inbox import ...`)

- `InboxRef`, `PlatformAccountRef`, `InboxRoutingMode`
- `IInboxDirectorySource`, `InboxCredentialService`, `InboxDirectory`
- `EncryptedSecretEnvelope`, `InboxCredentialRecord`, `InboxCredentialStatus`, `WhatsAppActiveInboxCredentialRecord`, `WhatsAppInactiveInboxCredentialRecord`, `PlatformAccountActiveIndexRecord`, `PlatformAccountEmptyIndexRecord`, `parse_inbox_credential_record`, `dump_record_for_storage`
- `InboxDirectoryError`, `InboxConfigurationError`, `InboxNotFoundError`, `InboxMembershipError`, `InboxDirectoryUnavailableError`, `InboxCredentialIntegrityError`, `InboxMutationConflictError`
- `MetaApplicationConfig` (`from wappa import ...` or `wappa.core.config.meta_application`), `CredentialCodec` / `SecretBinding` (`from wappa.core.security import ...`), `InboxDirectoryTable` (`wappa.persistence.inbox_directory`)
- `INBOX_ID_HEADER`, `InboxExecutionContext`, `get_inbox_execution_context` (`from wappa.api.dependencies import ...`); `SIGNATURE_HEADER`, `MetaCallbackAuthenticator`, `route_whatsapp_payload`, `RoutedWebhookDelivery` (`from wappa.core.inbound import ...`)

### API (`from wappa.api import ...`)

- `TemplateStateService`
- `convert_body_parameters`, `raise_for_failed_result`, `require_inbox_context`
- `dispatch_message_event`, `fire_api_event`, `resolve_event_user_id(recipient, explicit_user_id, fastapi_request, *, inbox_id)`

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

### Migration Notes (v0.27.0)

See [`docs/migration/v0.27.0-multi-inbox.md`](migration/v0.27.0-multi-inbox.md) for the ordered legacy and explicit Host paths, the breaking public imports, the key rotation runbook, and the callback cutover.

### Migration Notes (v0.13.0)

- `from wappa.core.expiry.listener import get_fastapi_app` is removed. Use `from wappa.core.expiry import get_app_context` then `get_app_context().get_app()`.
- Deep paths under `wappa.schemas.whatsapp`, `wappa.schemas.factory`, and `wappa.schemas.core.base_*` are removed. Use `wappa.webhooks` instead.
