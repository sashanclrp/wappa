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
| **Strategy** | `IInboxCredentialStore`, `ICacheFactory` backends | Swap implementations (settings vs DB lookup, Redis vs Memory vs JSON) without changing callers |
| **Adapter** | `wappa/messaging/whatsapp/`, `wappa/webhooks/whatsapp/` | Translate between platform-specific APIs and Wappa's universal interfaces |
| **Observer** | SSE/PubSub, Expiry keyspace notifications | Decouple event producers from consumers; fan-out without tight coupling |

## Message Flow — Inbound Webhook to Handler

```
Platform (WhatsApp, etc.)
    │
    │ POST /webhook/inboxes/{inbox_id}/{platform}
    ▼
┌─────────────────────────────────┐
│  API Layer (routes + controller)│
│                                 │
│  1. Parse JSON body             │
│  2. Validate platform enum      │
│  3. InboxMiddleware sets        │
│     inbox_id in request context │
│  4. Delegate to Inbound Runtime │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  Inbound Runtime                │
│                                 │
│  1. Validate routed inbox_id    │
│  2. Call platform processor     │
│  3. Validate payload inbox      │
│  4. Create Dispatch Context     │
│  5. Clone handler via           │
│     with_context(inbox_id,      │
│     user_id, messenger, cache)  │
│  6. Open SSE scope + dispatch   │
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

**Inbox authority:** The URL `inbox_id` is the routing authority and is validated
through the configured `IInboxCredentialStore`. If a platform payload also carries
an inbox identifier, Wappa validates that it matches the routed Inbox. For WhatsApp,
payload `metadata.phone_number_id` maps to `inbox_id`; `entry[].id` maps to
`platform_account_id` (WABA ID). Mismatches are rejected, not silently overridden.

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
5. **Inbox Credential Store** (`IInboxCredentialStore`): Resolves the credentials for a concrete `inbox_id`. The default `SettingsInboxCredentialStore` supports a single settings-backed WhatsApp Inbox; hosts that manage many Inboxes inject their own store, including the provided database-backed implementation.
6. **Adding a new platform** requires:
   - A webhook processor implementing the platform's payload → universal model mapping
   - A messenger implementing `IMessenger` for that platform's send API
   - A credential resolver for that platform's auth (implementing `IInboxCredentialStore`)
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
| CLI | [`wappa/cli/ARCHITECTURE.md`](./wappa/cli/ARCHITECTURE.md) | Commands, templates, example generation |

## Key Architectural Decisions

See [`docs/adr/`](./docs/adr/) for recorded decisions. Notable:

- [ADR-0001: inbox_id as runtime scope](./docs/adr/0001-inbox-id-runtime-scope.md) — replaces tenant_id
