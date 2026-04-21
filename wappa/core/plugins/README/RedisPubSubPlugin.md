# RedisPubSubPlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the full plugin system overview.

## What it does

`RedisPubSubPlugin` publishes real-time event notifications through Redis PubSub channels whenever messages flow through the system. It covers the full message lifecycle:

1. Incoming messages received via webhooks
2. Outgoing messages sent via API routes
3. Bot replies sent through `self.messenger` in event handlers
4. Message status changes (sent, delivered, read, failed)

Notifications are fire-and-forget -- a failed publish is logged but never interrupts the main processing flow. This makes PubSub a safe observability layer that external services (dashboards, analytics, CRMs) can subscribe to without affecting message delivery.

This is a **Hook-Based plugin** (Pattern 2) -- it registers startup/shutdown hooks at priority 22.

Source: `wappa/core/plugins/redis_pubsub_plugin.py`

## How to activate

With `Wappa`:

```python
from wappa import Wappa
from wappa.core.plugins import RedisPubSubPlugin

app = Wappa(cache="redis", redis_url="redis://localhost:6379")
app.add_plugin(RedisPubSubPlugin())
```

With `WappaBuilder`:

```python
from wappa.core.factory import WappaBuilder
from wappa.core.plugins import WappaCorePlugin, RedisPlugin, RedisPubSubPlugin

builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin())
builder.add_plugin(RedisPlugin(redis_url="redis://localhost:6379"))
builder.add_plugin(RedisPubSubPlugin(
    publish_incoming=True,
    publish_outgoing=True,
    publish_bot_replies=True,
    publish_status=True,
))
app = builder.build()
```

All constructor parameters are optional and default to `True`.

## Configuration options

| Parameter | Type | Default | Description |
|---|---|---|---|
| `publish_incoming` | `bool` | `True` | Publish `incoming_message` events for webhook-received messages |
| `publish_outgoing` | `bool` | `True` | Publish `outgoing_message` events for API-sent messages |
| `publish_bot_replies` | `bool` | `True` | Publish `bot_reply` events for messages sent via `self.messenger` |
| `publish_status` | `bool` | `True` | Publish `status_change` events for delivery/read status updates |

To disable a specific event type, set its parameter to `False`:

```python
RedisPubSubPlugin(
    publish_incoming=True,
    publish_outgoing=True,
    publish_bot_replies=False,  # No bot reply notifications
    publish_status=False,       # No status change notifications
)
```

## Channel pattern and event types

All notifications are published to channels following this pattern:

```
wappa:notify:{tenant}:{user_id}:{event_type}
```

| Segment | Description | Example |
|---|---|---|
| `tenant` | Tenant key from webhook context | `mimeia` |
| `user_id` | WhatsApp phone number or user identifier | `5511999887766` |
| `event_type` | One of the four event types below | `incoming_message` |

### Event types

| Event Type | Trigger | Payload fields |
|---|---|---|
| `incoming_message` | User sends a message via WhatsApp | `message_id`, `message_type` |
| `outgoing_message` | Message sent through API routes (`POST /api/messages/*`) | `message_id`, `message_type`, `success` |
| `bot_reply` | Bot sends a message via `self.messenger` in an event handler | `message_id`, `message_type` |
| `status_change` | Delivery/read receipt arrives via webhook | `message_id`, `status` |

## How it works

The plugin intercepts events at each stage without modifying existing handler code. Outbound bot replies (`bot_reply`) are intercepted through the **messenger middleware pipeline**; inbound events (`incoming_message`, `status_change`) are intercepted by wrapping the default webhook handlers.

**During `configure()`** (synchronous, before the app starts) the plugin:

1. Registers startup/shutdown hooks at priority `22`
2. When `publish_bot_replies=True`, registers `PubSubNotificationMiddleware` via `builder.add_messenger_middleware(...)` at priority `30` (domain-notifications band) — this is what publishes `bot_reply` on every successful `self.messenger.send_*()` call

**During startup** the plugin:

1. Verifies that `RedisManager.is_initialized()` is `True` (raises `RuntimeError` if not)
2. Retrieves the event handler from `app.state.api_event_dispatcher`
3. Stores references to the original handlers for clean shutdown
4. Wraps the default message handler with `PubSubMessageHandler` (publishes `incoming_message` after the original handler runs)
5. Wraps the default status handler with `PubSubStatusHandler` (publishes `status_change` after the original handler runs)
6. Registers a post-process hook on `WappaEventHandler` via `add_api_post_process_hook` to call `publish_api_notification` after API sends (publishes `outgoing_message`)

**During shutdown** it:

1. Removes the API post-process hook (via `remove_api_post_process_hook`)
2. Removes `app.state.redis_pubsub_plugin`
3. Logs shutdown completion

### Why bot_reply is now middleware

Pre-v0.4.0 the plugin flipped `app.state.pubsub_wrap_messenger = True` and the webhook controller branched on that flag to wrap `self.messenger` with a `PubSubMessengerWrapper` — a ~300 LOC class that re-implemented all 18 `IMessenger` methods purely to emit a `bot_reply` notification after each send. Adding a sibling concern (a cache write, a metrics probe) forced the same copy-paste.

In v0.4.0 that wrapper was rewritten as a ~60 LOC `PubSubNotificationMiddleware` on the general messenger pipeline. It reads tenant + user identity from the active `SSEEventContext` (set once per request by the framework entry point), so the middleware is app-scoped and shared across requests. Adding another outbound concern is a single `add_messenger_middleware` call at the right priority — no new `app.state` flags, no controller changes, no private-attribute drilling.

`mark_as_read()` still bypasses the pipeline (it is not a user-visible message), matching legacy behaviour.

The legacy `PubSubMessengerWrapper` is kept as a deprecation shim through v0.5.0 and will be removed in v0.6.0. See [MessengerMiddleware.md](./MessengerMiddleware.md) for the full design.

## Subscription examples

### Redis CLI

```bash
# All events for a specific user
redis-cli PSUBSCRIBE "wappa:notify:mimeia:5511999887766:*"

# All incoming messages for a tenant
redis-cli PSUBSCRIBE "wappa:notify:mimeia:*:incoming_message"

# All bot replies for a tenant
redis-cli PSUBSCRIBE "wappa:notify:mimeia:*:bot_reply"

# All status changes across all tenants
redis-cli PSUBSCRIBE "wappa:notify:*:*:status_change"

# Everything
redis-cli PSUBSCRIBE "wappa:notify:*"
```

### Python (redis-py async)

```python
import redis.asyncio as redis

r = redis.from_url("redis://localhost:6379")
pubsub = r.pubsub()

await pubsub.psubscribe("wappa:notify:mimeia:*:incoming_message")

async for message in pubsub.listen():
    if message["type"] == "pmessage":
        channel = message["channel"].decode()
        data = message["data"].decode()
        print(f"{channel}: {data}")
```

### Programmatic channel pattern

The plugin exposes a helper to build channel patterns:

```python
plugin = RedisPubSubPlugin()

# Specific user, all events
pattern = plugin.get_channel_pattern("mimeia", "5511999887766")
# -> "wappa:notify:mimeia:5511999887766:*"

# All users, specific event
pattern = plugin.get_channel_pattern("mimeia", event_type="bot_reply")
# -> "wappa:notify:mimeia:*:bot_reply"
```

## Dependencies

| Dependency | Required | Why |
|---|---|---|
| `RedisPlugin` | Yes | Must be added **before** `RedisPubSubPlugin`. The plugin checks `RedisManager.is_initialized()` at startup and raises `RuntimeError` if Redis is not available. |
| `WappaCorePlugin` | Yes | Provides the event dispatcher and handler infrastructure that PubSub wraps. |

Plugin ordering matters. Always register `RedisPlugin` before `RedisPubSubPlugin` in the builder:

```python
builder.add_plugin(RedisPlugin(redis_url="redis://localhost:6379"))  # First
builder.add_plugin(RedisPubSubPlugin())                              # Second
```

## Health monitoring

The plugin exposes an async `get_health_status()` method for monitoring:

```python
status = await plugin.get_health_status(app)
```

Returns a dictionary with:

```json
{
  "plugin": "RedisPubSubPlugin",
  "healthy": true,
  "config": {
    "publish_incoming": true,
    "publish_outgoing": true,
    "publish_bot_replies": true,
    "publish_status": true
  },
  "handlers_wrapped": {
    "message_handler": true,
    "status_handler": true,
    "api_post_process": true,
    "messenger_wrapper": true
  }
}
```

- `healthy` reflects whether `RedisManager.is_initialized()` returns `True` at the time of the check.
- `handlers_wrapped` shows which handlers were successfully wrapped during startup. If a handler is `false`, the corresponding event type is not being published. `messenger_wrapper` reflects whether the outbound `PubSubNotificationMiddleware` is active (controlled by the `publish_bot_replies` constructor flag).
