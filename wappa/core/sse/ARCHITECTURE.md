# SSE / PubSub — Architecture

Covers `wappa/core/sse/` and `wappa/core/pubsub/` as one bounded context, plus
the two Messenger Pipeline middleware files in `wappa/core/messaging/middleware/`
that belong to it.

---

## Responsibilities

- Maintain the request-scoped identity context (`SSEEventContext`) so every
  publisher in a request scope produces coherent Event Envelopes without
  per-call identity plumbing.
- Depend on the public `SSEHub` contract for subscription, envelope creation,
  local delivery, shutdown, and metrics.
- Provide `SSEEventHub` as the default in-memory `SSEHub`; Hosts may inject a
  broker-neutral adapter or decorator through `SSEEventsPlugin`.
- Guarantee `incoming_message` is emitted before `outgoing_bot_message` within
  a single request, using the staged-flush (Pending Incoming) mechanism.
- Validate public SSE event types in the best-effort `publish_sse_event()`
  wrapper before events reach the low-level hub.
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
├── event_hub.py          # SSEHub protocol, typed envelope/results/metrics, and
│                         # SSEEventHub default in-memory implementation
└── handlers.py           # publish_sse_event, publish_api_sse_event;
                          # SSEMessageHandler, SSEStatusHandler, SSEErrorHandler
                          # (decorator pattern over DefaultXxxHandler)

wappa/core/pubsub/
└── handlers.py           # publish_notification, publish_api_notification;
                          # PubSubMessageHandler, PubSubStatusHandler

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
| `SSEEventContext` | Per-request state bag. Holds `inbox_id`, `user_id`, `bsuid`, `phone_number`, `platform`, `metadata`, and the staged Pending Incoming payload. |
| `sse_event_scope` | Async context manager that installs and clears `SSEEventContext` via `ContextVar`. Used by every framework entry point. |
| `update_identity` / `update_metadata` | Enrich the active context and trigger a Pending Incoming flush as a side-effect. Called from pipeline middleware after a cache lookup resolves `user_id`. |
| `SSEHub` | Public structural contract. `publish` creates an `SSEEventEnvelope`; `deliver_envelope` performs local fan-out of an existing envelope without rebroadcasting it. |
| `SSEEventHub` | Default in-memory `SSEHub`. It closes a slow Subscription on its first queue overflow with `backpressure_gap`; it never silently drops data and leaves the stream open. |
| `SSEHubMetrics` | Typed process-local snapshot of active/filter counts plus published, locally delivered, dropped, overflow-close, and shutdown-close counters. |
| `publish_sse_event` | Public best-effort publisher. Rejects unknown event types, logs hub failures, and returns `0` instead of affecting the caller's main flow. |
| `SSESubscription` | Immutable dataclass: `subscriber_id`, bounded `asyncio.Queue`, and optional filters (`platform`, `inbox_id`, `user_id`, `event_types`). An Inbox filter always carries a Platform, so native identifiers cannot cross-deliver. |
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
- **Protocol / dependency inversion** — routes, middleware, handlers, lifecycle,
  and health depend on `SSEHub`, never the concrete default implementation.
- **Decorator adapter** — a Host broker adapter may publish the exact envelope
  returned by `publish()` externally and call `deliver_envelope()` for remote
  envelopes. Local delivery never triggers another broadcast.
- **Loss-aware backpressure** — a full queue is a Delivery Gap, not a
  drop-oldest optimization. The affected stream receives a private close
  control and reconnects; SSE remains non-durable and higher layers reconcile.
- **Validated public publisher** — `publish_sse_event()` owns public event-type
  validation and best-effort failure handling. `SSEHub.publish()` stays a
  low-level envelope-and-fan-out primitive for already-validated events.
- **Decorator / inner-handler** — `SSEMessageHandler`, `SSEStatusHandler`, and
  their PubSub counterparts wrap existing `DefaultXxxHandler` instances,
  preserving all logging stats and strategies while adding publication as a
  side-effect.
- **Middleware pipeline** — `SSELifecycleMiddleware` and
  `PubSubNotificationMiddleware` sit in the `MessengerPipeline` at fixed priority
  bands (70 and 30 respectively). The legacy wrapper classes were removed by
  the clean-break compatibility cleanup; middleware is the only supported
  outbound integration point.

---

## Data Flow

### Webhook path (incoming message)

```
Webhook controller
  └─ sse_event_scope(inbox_id, user_id, ...)     # installs SSEEventContext
       └─ SSEMessageHandler.log_incoming_message  # stages Pending Incoming
            └─ pipeline middleware / cache lookup
                 └─ update_identity(user_id=...)  # flush fires here (or later)
                      └─ SSEHub.publish(incoming_message)
                           └─ matching SSESubscription queues
```

### Outgoing bot message path

```
Host handler calls self.messenger.send_text(...)
  └─ MessengerPipeline._invoke
       └─ SSELifecycleMiddleware.handle
            ├─ flush_incoming_sse()               # ordering guard
            ├─ call_next → ... → raw messenger
            └─ SSEHub.publish(outgoing_bot_message)
```

### Redis PubSub (bot reply)

```
MessengerPipeline._invoke
  └─ PubSubNotificationMiddleware.handle
       ├─ call_next → result
       └─ result.success → RedisPubSubPublisher.publish(bot_reply)
                           channel: wappa:notify:{inbox_id}:{user_id}:bot_reply
```

## Hub Injection and Delivery Gaps

`SSEEventsPlugin()` creates one `SSEEventHub` by default. A Host may supply one
protocol-compatible instance or a factory, but never both:

```python
from wappa.core.plugins import SSEEventsPlugin
from wappa.sse import SSEHub

plugin = SSEEventsPlugin(
    event_hub_factory=lambda queue_size: BrokeredSSEHub(queue_size=queue_size)
)
```

The plugin creates the hub before it registers Messenger middleware, then gives
the same object to routes, inbound wrappers, outbound API hooks, lifecycle, and
health. A broker adapter uses `publish()` to obtain Wappa's envelope and uses
`deliver_envelope(envelope)` for broker-received events. It must not inspect or
mutate Wappa private attributes.

The default hub is process-local and non-durable. On a queue overflow it marks
the Subscription with `backpressure_gap`, clears queued payloads only to enqueue
a private close control, and terminates the HTTP stream. EventSource reconnects;
the frontend reconciles its durable state. `snapshot_metrics()` exposes the
process-local counters needed to observe those gaps.
