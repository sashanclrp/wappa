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
│  1. Validate platform enum      │
│  2. Parse JSON body             │
│  3. InboxMiddleware sets        │
│     inbox_id in request context │
│  4. Delegate to controller      │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  WebhookController              │
│                                 │
│  1. Resolve inbox credentials   │
│  2. Create Messenger (factory)  │
│  3. Create CacheFactory         │
│  4. Clone handler via           │
│     with_context(inbox_id,      │
│     user_id, messenger, cache)  │
│  5. Call platform processor     │
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
│  3. Dispatch to EventDispatcher │
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

## Layer Dependencies

```
   CLI (no runtime coupling)
    
   API Layer
     └── depends on → Core Events, Core Logging, Schemas
   
   Core Events (dispatch)
     └── depends on → Domain Interfaces, Webhooks (universal models)
   
   Webhooks (parsing)
     └── depends on → Schemas, Domain Models
   
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
3. **PlatformType enum**: New platforms add a value here. The router, dispatcher, and factory resolve the correct adapter.
4. **Inbox Credential Store** (`IInboxCredentialStore`): Resolves the credentials for a concrete `inbox_id`. The default `SettingsInboxCredentialStore` supports a single settings-backed WhatsApp Inbox; hosts that manage many Inboxes inject their own store, including the provided database-backed implementation.
5. **Adding a new platform** requires:
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
