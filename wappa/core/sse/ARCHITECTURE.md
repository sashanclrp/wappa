# SSE / PubSub — Architecture

Covers `wappa/core/sse/` and `wappa/core/pubsub/` as one bounded context, plus
the two Messenger Pipeline middleware files in `wappa/core/messaging/middleware/`
that belong to it.

---

## Responsibilities

- Maintain the request-scoped identity context (`SSEEventContext`) so every
  publisher in a request scope produces coherent Event Envelopes without
  per-call identity plumbing.
- Fan out SSE Event Envelopes to in-process Subscribers via the `SSEEventHub`.
- Guarantee `incoming_message` is emitted before `outgoing_bot_message` within
  a single request, using the staged-flush (Pending Incoming) mechanism.
- Publish compact Redis PubSub Notifications for lightweight inter-process
  wakeups after outgoing sends and incoming webhooks.
- Register custom SSE event types for host-application events.

## Explicit Non-Responsibilities

- HTTP streaming (SSE transport layer) — owned by API route handlers.
- Redis connection lifecycle — owned by the Redis persistence layer.
- Webhook parsing and event dispatch — owned by `core/events/`.
- Business logic reacting to events — owned by host applications.
- Deciding which Subscriptions are authorized — owned by the API layer.

---

## Module Structure

```
wappa/core/sse/
├── context.py            # SSEEventContext dataclass + ContextVar; update_identity,
│                         # update_metadata, flush_incoming_sse, sse_event_scope
├── event_hub.py          # SSEEventHub — in-process async fan-out bus; SSESubscription
├── handlers.py           # publish_sse_event, publish_api_sse_event;
│                         # SSEMessageHandler, SSEStatusHandler, SSEErrorHandler
│                         # (decorator pattern over DefaultXxxHandler)
└── messenger_wrapper.py  # SSEMessengerWrapper — DEPRECATED since v0.5.x;
                          # superseded by SSELifecycleMiddleware

wappa/core/pubsub/
├── handlers.py           # publish_notification, publish_api_notification;
│                         # PubSubMessageHandler, PubSubStatusHandler
└── messenger_wrapper.py  # PubSubMessengerWrapper — DEPRECATED since v0.5.x;
                          # superseded by PubSubNotificationMiddleware

wappa/core/messaging/middleware/
├── sse_lifecycle.py      # SSELifecycleMiddleware (priority 70) — canonical SSE
│                         # outgoing-message integration point
└── pubsub_notification.py # PubSubNotificationMiddleware (priority 30) — canonical
                           # PubSub outgoing-message integration point
```

---

## Key Classes and Roles

| Class / Function | Role |
|---|---|
| `SSEEventContext` | Per-request state bag. Holds `inbox_id` (as `tenant_id`), `user_id`, `bsuid`, `phone_number`, `platform`, `metadata`, and the staged Pending Incoming payload. |
| `sse_event_scope` | Async context manager that installs and clears `SSEEventContext` via `ContextVar`. Used by every framework entry point. |
| `update_identity` / `update_metadata` | Enrich the active context and trigger a Pending Incoming flush as a side-effect. Called from pipeline middleware after a cache lookup resolves `user_id`. |
| `SSEEventHub` | Singleton async fan-out bus. `subscribe` / `unsubscribe` manage Subscriptions; `publish` fans out to matching ones using a drop-oldest queue policy. |
| `SSESubscription` | Immutable dataclass: `subscriber_id`, bounded `asyncio.Queue`, and optional filters (`inbox_id`, `user_id`, `event_types`). |
| `SSEMessageHandler` | Decorator over `DefaultMessageHandler`. Stages the `incoming_message` envelope as a Pending Incoming on the context rather than publishing immediately. |
| `SSEStatusHandler` / `SSEErrorHandler` | Decorators over their Default counterparts. Publish `status_change` / `webhook_error` envelopes directly (no staging needed). |
| `SSELifecycleMiddleware` | Messenger Pipeline middleware (priority 70). Flush → send → publish `outgoing_bot_message`. App-scoped singleton; identity comes from `SSEEventContext`. |
| `PubSubNotificationMiddleware` | Messenger Pipeline middleware (priority 30). Publishes `bot_reply` notification after a successful send; reads identity from `SSEEventContext`. |
| `PubSubMessageHandler` / `PubSubStatusHandler` | Decorators over Default handlers. Publish `incoming_message` / `status_change` notifications directly to Redis after logging. |

---

## Design Patterns

- **ContextVar scope** — `SSEEventContext` is propagated through Python's async
  task context, not threaded through call arguments. Entry points open a scope;
  publishers read it. This eliminates the "null identity" class of bugs that
  existed prior to v0.3.4.
- **Staged flush** — `incoming_message` is held as a Pending Incoming and emitted
  on the first enrichment call or outgoing send, guaranteeing event ordering
  without requiring the webhook handler to know when identity will be resolved.
- **Decorator / inner-handler** — `SSEMessageHandler`, `SSEStatusHandler`, and
  their PubSub counterparts wrap existing `DefaultXxxHandler` instances,
  preserving all logging stats and strategies while adding publication as a
  side-effect.
- **Middleware pipeline** — `SSELifecycleMiddleware` and
  `PubSubNotificationMiddleware` sit in the `MessengerPipeline` at fixed priority
  bands (70 and 30 respectively). This replaces the deprecated wrapper classes
  and allows both concerns to be composed independently.

---

## Data Flow

### Webhook path (incoming message)

```
Webhook controller
  └─ sse_event_scope(inbox_id, user_id, ...)     # installs SSEEventContext
       └─ SSEMessageHandler.log_incoming_message  # stages Pending Incoming
            └─ pipeline middleware / cache lookup
                 └─ update_identity(user_id=...)  # flush fires here (or later)
                      └─ SSEEventHub.publish(incoming_message)
                           └─ matching SSESubscription queues
```

### Outgoing bot message path

```
Host handler calls self.messenger.send_text(...)
  └─ MessengerPipeline._invoke
       └─ SSELifecycleMiddleware.handle
            ├─ flush_incoming_sse()               # ordering guard
            ├─ call_next → ... → raw messenger
            └─ SSEEventHub.publish(outgoing_bot_message)
```

### Redis PubSub (bot reply)

```
MessengerPipeline._invoke
  └─ PubSubNotificationMiddleware.handle
       ├─ call_next → result
       └─ result.success → RedisPubSubPublisher.publish(bot_reply)
                           channel: wappa:notify:{inbox_id}:{user_id}:bot_reply
```
