# CONTEXT-MAP.md

Wappa is a multi-context library. Each bounded context owns its own language, invariants, and internal architecture. This map shows where each context lives and how they relate.

## Contexts

| Context | Path | CONTEXT.md | ARCHITECTURE.md | Responsibility |
|---------|------|------------|-----------------|----------------|
| **Root (Shared Kernel)** | `/` | [`CONTEXT.md`](./CONTEXT.md) | [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Cross-cutting terms, message flow overview, design patterns |
| **Webhooks** | `wappa/webhooks/` | [`CONTEXT.md`](./wappa/webhooks/CONTEXT.md) | [`ARCHITECTURE.md`](./wappa/webhooks/ARCHITECTURE.md) | Platform-specific webhook parsing into universal models |
| **Messaging** | `wappa/messaging/` | [`CONTEXT.md`](./wappa/messaging/CONTEXT.md) | [`ARCHITECTURE.md`](./wappa/messaging/ARCHITECTURE.md) | Platform-specific outbound message construction and delivery |
| **Persistence** | `wappa/persistence/` | [`CONTEXT.md`](./wappa/persistence/CONTEXT.md) | [`ARCHITECTURE.md`](./wappa/persistence/ARCHITECTURE.md) | Cache backends scoped by inbox and user identity |
| **SSE / PubSub** | `wappa/core/sse/`, `wappa/core/pubsub/` | [`CONTEXT.md`](./wappa/core/sse/CONTEXT.md) | [`ARCHITECTURE.md`](./wappa/core/sse/ARCHITECTURE.md) | Real-time event streaming and subscriber fan-out |
| **Expiry** | `wappa/core/expiry/` | [`CONTEXT.md`](./wappa/core/expiry/CONTEXT.md) | [`ARCHITECTURE.md`](./wappa/core/expiry/ARCHITECTURE.md) | Time-based automation via Redis keyspace notifications |
| **Plugins** | `wappa/core/plugins/` | [`CONTEXT.md`](./wappa/core/plugins/CONTEXT.md) | [`ARCHITECTURE.md`](./wappa/core/plugins/ARCHITECTURE.md) | Composable framework extensions (auth, CORS, rate limiting, Redis, DB) |
| **CLI** | `wappa/cli/` | [`CONTEXT.md`](./wappa/cli/CONTEXT.md) | [`ARCHITECTURE.md`](./wappa/cli/ARCHITECTURE.md) | Developer tooling: scaffolding, dev server, examples |

## Context Relationships

```
                         Host Application (Symphonai, etc.)
                                    │
                                    │ implements WappaEventHandler
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                            Wappa Framework                                │
│                                                                           │
│                    ┌─────────────────────────────────────┐                │
│                    │       WappaEventHandler (ABC)        │                │
│                    │                                     │                │
│                    │  process_message(webhook)      ◄────── IncomingMessageWebhook
│                    │  process_status(webhook)       ◄────── StatusWebhook
│                    │  process_error(webhook)        ◄────── ErrorWebhook
│                    │  process_system_webhook(webhook)◄────── SystemWebhook
│                    │  process_external_event(event) ◄────── ExternalEvent
│                    │  process_api_message(event)    ◄────── APIMessageEvent
│                    │  process_cron_event(event)     ◄────── CronEvent
│                    │                                     │                │
│                    │  Injected per-request:              │                │
│                    │    self.inbox_id                    │                │
│                    │    self.user_id                     │                │
│                    │    self.messenger  → IMessenger     │                │
│                    │    self.cache_factory → ICacheFactory│                │
│                    │    self.db / self.db_read           │                │
│                    └─────────────────────────────────────┘                │
│                              ▲                                            │
│                              │ dispatches to                              │
│                              │                                            │
│   ┌──────────────────────────┴───────────────────────────────────┐       │
│   │                    Core Event Dispatcher                      │       │
│   │  (routes parsed webhooks, API events, cron, external events) │       │
│   └──────────────────────────────────────────────────────────────┘       │
│              ▲                        ▲                  ▲                │
│              │                        │                  │                │
│   ┌──────────┐            ┌───────────────┐    ┌────────────────┐        │
│   │ Webhooks │            │  API Routes   │    │  CronPlugin /  │        │
│   │ (inbound │            │  (outbound    │    │  ExternalWebhook│        │
│   │  parsing)│            │   msg events) │    │  Processors    │        │
│   └──────────┘            └───────────────┘    └────────────────┘        │
│        │                                                                  │
│        │ parses platform payload into                                     │
│        ▼                                                                  │
│   ┌───────────────┐                                                       │
│   │Universal Models│  IncomingMessageWebhook, StatusWebhook,              │
│   │(InboxBase,     │  ErrorWebhook, SystemWebhook                         │
│   │ UserBase, etc.)│                                                      │
│   └───────────────┘                                                       │
│                                                                           │
│   ┌──────────────────────────────────────────────────────────────┐       │
│   │              Runtime Services (used by event handlers)         │       │
│   │                                                               │       │
│   │  ┌──────────────┐   ┌──────────────┐   ┌───────────────┐    │       │
│   │  │  Messaging   │   │  Persistence │   │  SSE / PubSub │    │       │
│   │  │  (outbound)  │   │  (cache/state)│   │  (realtime)   │    │       │
│   │  └──────────────┘   └──────────────┘   └───────────────┘    │       │
│   │                                                               │       │
│   │  ┌──────────────┐   ┌──────────────┐                        │       │
│   │  │   Expiry     │   │   Plugins    │                        │       │
│   │  │  (timers)    │   │  (extend)    │                        │       │
│   │  └──────────────┘   └──────────────┘                        │       │
│   └──────────────────────────────────────────────────────────────┘       │
│                                                                           │
│   ┌──────────┐                                                            │
│   │   CLI    │  (scaffolding, dev server — no runtime coupling)           │
│   └──────────┘                                                            │
└──────────────────────────────────────────────────────────────────────────┘
```

### WappaEventHandler Processor Summary

The Host Application implements `WappaEventHandler` and overrides these processors:

| Processor | Event Source | Input Type | When Fired |
|-----------|-------------|-----------|------------|
| `process_message()` | Platform webhook | `IncomingMessageWebhook` | User sends a message to the Inbox |
| `process_status()` | Platform webhook | `StatusWebhook` | Message delivery status changes (sent, delivered, read, failed) |
| `process_error()` | Platform webhook | `ErrorWebhook` | Platform reports an error |
| `process_system_webhook()` | Platform webhook | `SystemWebhook` | System events: phone number change, BSUID update, marketing preference |
| `process_external_event()` | External webhook | `ExternalEvent` | Third-party webhook (MercadoPago, Stripe, CRM, etc.) routed through Wappa |
| `process_api_message()` | Outbound API | `APIMessageEvent` | A message was sent via Wappa's REST API (tracking, DB writes, analytics) |
| `process_cron_event()` | CronPlugin | `CronEvent` | A scheduled cron fires (background tasks, reminders, reports) |

Each processor receives a **cloned handler instance** with per-request context already injected (`inbox_id`, `user_id`, `messenger`, `cache_factory`, `db`). The Template Method pattern ensures framework pre/post-processing (logging, metrics) runs automatically around the user's business logic.

## Relationship Types

- **Webhooks → Core Events**: Conformist. Webhooks parse raw platform payloads into universal models that Core Events consumes without transformation.
- **Core Events → WappaEventHandler**: Published Language. The event dispatcher publishes typed events; host applications implement handlers against the published interface.
- **WappaEventHandler → Messaging**: Customer/Supplier. Event handlers call the messaging interface to send replies; messaging owns the delivery contract.
- **WappaEventHandler → Persistence**: Customer/Supplier. Event handlers use cache factories for state; persistence owns backend selection and key structure.
- **SSE/PubSub ← Messaging**: Observer. The messenger pipeline notifies SSE/PubSub of outbound messages for real-time streaming.
- **Expiry → Messaging + Persistence**: Autonomous. Expiry reacts to Redis keyspace events and bootstraps its own messenger/cache instances.
- **Plugins → All**: Open Host Service. Plugins extend the framework by hooking into lifecycle events; they depend on core interfaces but core does not depend on them.
- **CLI → None (runtime)**: Separate Concern. CLI generates scaffolding and runs dev servers; it has no runtime coupling to other contexts.

## ADRs

System-wide decisions live in [`docs/adr/`](./docs/adr/).

Context-specific decisions live in `<context-path>/docs/adr/` when the decision is local to that context.
