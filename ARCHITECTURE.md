# ARCHITECTURE.md — Wappa Framework

## What Wappa Is

Wappa is a messaging runtime framework. It receives platform webhooks, parses them into universal models, dispatches events to user-defined handlers, and provides outbound messaging — all scoped by Inbox identity.

Today Wappa is **WhatsApp-opinionated**: the WhatsApp adapter is the only fully implemented platform. But the abstractions and design patterns are built for multi-platform: adding Telegram, Instagram, or Teams requires implementing platform-specific adapters without changing core dispatch, persistence, or event handler contracts.

## Design Patterns

| Pattern | Where Used | Why |
|---------|-----------|-----|
| **Template Method** | `WappaEventHandler.handle_*()` → `process_*()` | Framework guarantees pre/post-processing (logging, metrics) while host app owns business logic in `process_*()` |
| **Prototype (Clone)** | `WappaEventHandler.with_context()` | Thread-safe per-request handler instances. Base handler is a prototype; each request gets a shallow copy with injected context |
| **Factory** | `MessengerFactory`, `CacheFactory`, `WappaBuilder` | Decouple construction from use. Factories resolve credentials, build platform-specific clients, select cache backends |
| **Builder** | `WappaBuilder` | Assemble complex application configurations step-by-step with plugin composition |
| **Plugin** | `WappaPlugin`, `WappaBuilder.with_*()` | Open/Closed principle — extend framework behavior without modifying core |
| **Pipeline (Middleware)** | `MessengerPipeline` | Composable outbound message middleware (SSE lifecycle, PubSub notification) wrapping the messenger |
| **Strategy** | `IInboxCredentialResolver` (internal), `IIdentityResolver`, `ICacheFactory` backends | Swap the credential authority (legacy settings vs. Inbox Directory), Inbox-aware identity, and persistence implementations without changing callers |
| **Adapter** | `wappa/messaging/whatsapp/`, `wappa/webhooks/whatsapp/` | Translate between platform-specific APIs and Wappa's universal interfaces |
| **Observer** | SSE/PubSub, Expiry keyspace notifications | Decouple event producers from consumers; fan-out without tight coupling |

## Message Flow — Inbound Webhook to Handler

```
Platform (WhatsApp, etc.)
    │
    │ POST /webhook/inboxes/whatsapp
    ▼
┌─────────────────────────────────┐
│  API Layer (routes + controller)│
│                                 │
│  1. Read exact body bytes once  │
│  2. Verify X-Hub-Signature-256  │
│     with META_APP_SECRET (401)  │
│  3. Decode JSON, require object │
│  4. Delegate: routing + runtime │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  WhatsApp Payload Routing       │
│                                 │
│  1. Split every entry/change    │
│  2. InboxRef from phone_number_id│
│     or WABA fan-out via the     │
│     Platform Account Index      │
│  3. Resolve credentials through │
│     IInboxCredentialResolver    │
│  4. Prove Inbox ∈ entry[].id    │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Inbound Runtime                │
│                                 │
│  1. Call platform processor     │
│  2. Validate payload inbox      │
│  3. Build EVERY Dispatch Context│
│     (DispatchContextBuilder:    │
│     messenger, cache, db)       │
│  4. Only then schedule the batch│
│  5. Open SSE scope + dispatch   │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Platform Webhook Processor     │
│  (e.g., WhatsAppWebhookProcessor)
│                                 │
│  1. Parse raw payload into      │
│     Universal Webhook Models    │
│     (InboxBase, UserBase,       │
│      MessageBase, etc.)         │
│  2. Classify: message, status,  │
│     error, or system event      │
│  3. Return the Universal Model  │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  WappaEventDispatcher           │
│                                 │
│  Routes to handler.handle_*()   │
│  which calls process_*()        │
│  (Template Method)              │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Host's WappaEventHandler impl  │
│                                 │
│  process_message(webhook)       │
│  process_status(webhook)        │
│  process_error(webhook)         │
│  process_system_webhook(webhook)│
│                                 │
│  Has access to:                 │
│    self.inbox_id                │
│    self.user_id                 │
│    self.messenger (outbound)    │
│    self.cache_factory (state)   │
│    self.db / self.db_read       │
└─────────────────────────────────┘
```

**Inbound Runtime boundary:** The Inbound Runtime owns the Dispatch Context: `inbox_id`,
`user_id`, Messenger, Cache Factory, DB sessions, SSE identity, and cloned
`WappaEventHandler`. Platform processors are pure translators and must not mutate
ContextVars, build messengers, resolve cache factories, or clone handlers.

**Callback authentication:** The canonical Meta callback is `GET + POST /webhook/inboxes/whatsapp`. GET compares `hub.verify_token` with the Meta Application Configuration's verify token and reads nothing else. POST verifies the exact body bytes against `X-Hub-Signature-256` with `META_APP_SECRET` before JSON parsing, directory reads, payload logging, or scheduling; missing, malformed, and mismatched signatures all answer a generic 401. One Wappa application binds to one Meta App; there is no development bypass.

**Inbox authority:** Identity crossing Platforms is `InboxRef(platform, inbox_id)` and `PlatformAccountRef(platform, platform_account_id)`. `value.metadata.phone_number_id`, or a flat `value.phone_number_id`, maps to `InboxRef.whatsapp(...)`; `entry[].id` maps only to `PlatformAccountRef.whatsapp(...)` and is never an Inbox. A phone-scoped change must prove its active record belongs to that WABA (400 otherwise). A change without a phone number fans out to every validated member of the Platform Account Index; a stale index is repaired from the source once, and a failed repair is 503 with nothing dispatched. Wappa builds every Dispatch Context before scheduling any handler work.

**Credential authority:** `wappa/core/factory/inbox_assembly.py` is the only code that reads `WP_ACCESS_TOKEN`, `WP_PHONE_ID`, `WP_BID`, and `SYSTEM_TOKEN_ENC_KEY`. It selects exactly one `InboxRoutingMode` — `legacy` (settings-backed single Inbox) or `explicit` (Inbox Directory over the Host's `IInboxDirectorySource`) — and rejects mixed configuration. Every runtime component then consumes the resulting `InboxRuntimeConfiguration` (`app.state.inbox_runtime`) through the internal `IInboxCredentialResolver`; none read those variables again.

**Inbox Directory dependency direction:**

```text
Host durable schema
  -> IInboxDirectorySource                 (Host adapter, read-only)
  -> InboxDirectory                        (wappa/domain/inbox/services.py: read-through,
                                            versions, index repair, refresh/deactivate)
  -> InboxDirectoryTable on ITableCache    (wappa/persistence/inbox_directory.py,
                                            context_id = SYSTEM_SCOPE)
  -> CredentialCodec                       (wappa/core/security: Fernet, context-bound)
  -> IInboxCredentialResolver              (internal read port)
  -> DispatchContextBuilder / InboxExecutionContext
  -> WhatsApp client and Messenger construction
```

The API layer receives an Inbox Execution Context and knows nothing about Table Cache names, source queries, encryption keys, or token values. The persistence class never imports Host repositories or WhatsApp clients.

**Outbound HTTP scope:** Inbox-dependent routes depend on `get_inbox_execution_context`, which reads `X-Wappa-Inbox-ID`, falls back to the legacy default only in legacy mode, resolves the active record once, and shares the `InboxExecutionContext` with every dependency in the route. Local-only routes (limits, local validation, root health, docs) never resolve an Inbox and never depend on directory health. The header selects scope; Host authentication and authorization decide permission and run first. `InboxMiddleware` only isolates the ambient logging context per request.

**Failure classes:** `InboxNotFoundError`, `InboxMembershipError`, `InboxDirectoryUnavailableError`, `InboxCredentialIntegrityError`, and `InboxMutationConflictError` are the stable categories. The callback maps them to 400/400/503/503/503; Wappa HTTP operations map unknown to 404 and unavailable to 503; programmatic entry points raise them unchanged. A directory outage during Messenger construction is never an unclassified 500.

## Message Flow — Outbound (Host sends a reply)

```
Host's process_message():
    await self.messenger.send_text("Hello!", recipient=user_id)
        │
        ▼
┌─────────────────────────────────┐
│  MessengerPipeline              │
│  (middleware stack)             │
│                                 │
│  → SSELifecycleMiddleware       │
│  → PubSubNotificationMiddleware │
│  → ... (composable)            │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  WhatsAppMessenger (IMessenger) │
│                                 │
│  Delegates to typed handlers:   │
│  - IMediaHandler                │
│  - IInteractiveHandler          │
│  - ITemplateHandler             │
│  - ISpecializedHandler          │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  WhatsAppClient (httpx)         │
│                                 │
│  Sends to Meta Graph API        │
│  phone_number_id = inbox_id     │
└─────────────────────────────────┘
```

## Message Flow — Inbox-scoped Template transport

Embedding hosts that only need Template delivery use a smaller public
capability. The capability and the general Messenger share the same internal
construction and pipeline; it is not a second delivery implementation.

```
Host Application
    │ OutboundRuntime.from_app(app).templates(inbox_id).send(request)
    ▼
InboxTemplateTransport
    │ validates Delivery Address, category, authentication method,
    │ and selects one endpoint before I/O
    ▼
MessengerFactory → MessengerPipeline → WhatsApp adapter → Meta
    │
    ▼
TemplateTransportResult
    accepted | rejected | transport_unavailable | indeterminate
```

The request contains platform-facing values only. The Host Application retains
governance, attribution, state, persistence, and durable commit. A result is
`accepted` only when Meta returns a platform Message ID. Wappa never performs an
automatic cross-endpoint retry.

## HTTP Client Lifecycle

Wappa manages two separate HTTP client pools, both owned by `SessionLifecycle`:

```
┌───────────────────────────────────────────────────────┐
│  SessionLifecycle                                     │
│                                                       │
│  Authenticated Client (get_session)                   │
│  ├── 100 max connections, 20 keepalive                │
│  ├── Bearer token injected by WhatsAppClient          │
│  ├── Used for: Meta Graph API calls                   │
│  └── ⚠️  NEVER used for third-party URLs              │
│                                                       │
│  Media Download Client (get_media_download_client)    │
│  ├── 20 max connections, 5 keepalive                  │
│  ├── No auth headers — credential isolation enforced  │
│  ├── Lazily created on first access                   │
│  └── Used for: public/third-party media downloads     │
│                                                       │
│  Lifecycle: startup → active → drain → close          │
│  Both clients closed during three-phase shutdown      │
└───────────────────────────────────────────────────────┘
```

**Credential isolation rule:** The authenticated client carries Meta/WhatsApp Bearer tokens. The media download client never carries auth headers. These clients must not be consolidated. This prevents accidental credential leakage to third-party hosts when downloading public media URLs for re-upload.

**Three-phase shutdown:**

| Phase | Priority | Action |
|-------|----------|--------|
| Drain mark | 90 | `SessionLifecycle.begin_drain()` + `BackgroundWorkTracker.begin_drain()` — reject new work |
| Background drain | 70 | `BackgroundWorkTracker.drain(timeout=30s)` — await in-flight tasks |
| Resource close | 10 | Stop memory cleanup, close both HTTP clients, clear app state |

## Layer Dependencies

```
   CLI (no runtime coupling)
    
   API Layer
     └── depends on → Core Events, Core Logging, Schemas
   
   Core Events (dispatch)
     └── depends on → Domain Interfaces, Webhooks (universal models)
   
   Webhooks (parsing)
     └── depends on → Shared Schema Primitives, Domain Models
   
   Messaging (outbound)
     └── depends on → Domain Interfaces, Platform SDKs (httpx)
   
   Persistence (cache backends)
     └── depends on → Domain Interfaces
   
   SSE / PubSub
     └── depends on → Core Logging
   
   Expiry
     └── depends on → Messaging, Persistence, Core Logging
   
   Plugins
     └── depends on → Core (any), Domain Interfaces
   
   Resilience (retry + transient-failure classification)
     └── depends on → Core Logging, httpx
   
   Domain Interfaces (pure abstractions)
     └── depends on → nothing
```

**Dependency rule:** Domain Interfaces is the innermost layer. Outer layers depend inward. No layer depends on the API layer except the application entry point.

## Multi-Platform Strategy

Wappa today is WhatsApp-only in implementation but multi-platform in design:

1. **Universal Webhook Models** (`wappa/webhooks/core/`): `InboxBase`, `UserBase`, `MessageBase`, `StatusBase`, `ErrorBase`, `SystemBase` — platform-agnostic.
2. **Platform Adapters** (`wappa/webhooks/whatsapp/`, `wappa/messaging/whatsapp/`): Parse WhatsApp-specific payloads into universal models; construct WhatsApp-specific API requests from universal send calls.
3. **Shared Schema Primitives** (`wappa/schemas/core/types.py`, `wappa/schemas/core/recipient.py`): Cross-cutting enums and outbound recipient normalization shared by inbound, outbound, API, and runtime modules. Inbound webhook schemas do not live here.
4. **PlatformType enum**: New platforms add a value here. The router, dispatcher, and factory resolve the correct adapter.
5. **Inbox Directory** (`wappa/domain/inbox/`): Wappa's canonical, Platform-discriminated credential records and the read-through directory that resolves them. Hosts supply only an `IInboxDirectorySource`; Wappa owns encryption, caching, versions, indexes, and Messenger eviction. The `InboxCredentialRecord` union grows one member per Platform.
6. **Adding a new platform** requires:
   - A webhook processor implementing the platform's payload → universal model mapping
   - A messenger implementing `IMessenger` for that platform's send API
   - A Platform member of `InboxCredentialRecord` naming the credential its adapter consumes, plus the Platform's `InboxRef.cache_namespace` encoding
   - Registration in `PlatformType` and the messenger/webhook factories

No changes to `WappaEventHandler`, `CacheFactory`, `SSE`, `Expiry`, or `Plugins` are needed.

## Deeper Architecture Docs

Each bounded context has its own `ARCHITECTURE.md` for internal details:

| Context | Doc | Covers |
|---------|-----|--------|
| Webhooks | [`wappa/webhooks/ARCHITECTURE.md`](./wappa/webhooks/ARCHITECTURE.md) | Payload parsing, universal model construction, platform processor interface |
| Messaging | [`wappa/messaging/ARCHITECTURE.md`](./wappa/messaging/ARCHITECTURE.md) | Handler composition, pipeline middleware, client construction |
| Persistence | [`wappa/persistence/ARCHITECTURE.md`](./wappa/persistence/ARCHITECTURE.md) | Backend selection, key namespace rules, cache interface contracts |
| SSE/PubSub | [`wappa/core/sse/ARCHITECTURE.md`](./wappa/core/sse/ARCHITECTURE.md) | Subscription model, fan-out, envelope structure |
| Expiry | [`wappa/core/expiry/ARCHITECTURE.md`](./wappa/core/expiry/ARCHITECTURE.md) | Key format, keyspace notification flow, handler registration |
| Plugins | [`wappa/core/plugins/ARCHITECTURE.md`](./wappa/core/plugins/ARCHITECTURE.md) | Plugin lifecycle, hook points, built-in plugins |
| External Webhooks | [`wappa/core/external_webhooks/ARCHITECTURE.md`](./wappa/core/external_webhooks/ARCHITECTURE.md) | External source runtime, signature verification, event registry |
| CLI | [`wappa/cli/ARCHITECTURE.md`](./wappa/cli/ARCHITECTURE.md) | Commands, templates, example generation |

## Key Architectural Decisions

See [`docs/adr/`](./docs/adr/) for recorded decisions. Notable:

- [ADR-0001: inbox_id as runtime scope](./docs/adr/0001-inbox-id-runtime-scope.md) — replaces tenant_id
- [ADR-0005: Runtime primitives for host platforms](./docs/adr/0005-runtime-primitives-for-host-platforms.md) — signature verification, external event routing, versioned caches, request IDs, retry classification
- [ADR-0007: Embedded outbound route control](./docs/adr/0007-embedded-outbound-route-control.md) — an embedding host omits Wappa's raw outbound mutation routes without losing media, read, or service routes
- [ADR-0008: Redis hash boolean encoding](./docs/adr/0008-redis-hash-boolean-encoding.md) — `"1"`/`"0"` is a compatibility contract, not an implementation detail
- [ADR-0009: Route capability groups](./docs/adr/0009-route-capability-groups.md) — "mutation" means every route that sends, deletes, or rewrites state, not only sends
- [ADR-0010: Authenticated, payload-routed WhatsApp webhook](./docs/adr/0010-payload-routed-whatsapp-webhook.md) — one callback, raw-body HMAC, qualified routing, WABA membership, all-or-nothing admission
- [ADR-0011: Encrypted Inbox Directory](./docs/adr/0011-encrypted-inbox-directory.md) — Wappa-owned directory on Table Cache under the System Scope, Host-owned schema through one source, encrypted records, TTL and version rules
