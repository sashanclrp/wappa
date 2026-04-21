# SSEEventsPlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the full plugin system overview.

## What it does

`SSEEventsPlugin` streams real-time events through Server-Sent Events (SSE) using FastAPI native support (`from fastapi.sse import EventSourceResponse`).

It publishes:

1. Incoming messages from webhooks
2. Outgoing messages sent via API routes
3. Outgoing bot messages sent through `self.messenger`
4. Message status events (sent/delivered/read/failed)
5. Webhook-level errors

This is a **Router + Hooks plugin** (Pattern 3) -- it registers SSE routes and startup/shutdown hooks at priority 24.

Source: `wappa/core/plugins/sse_events_plugin.py`

## How to activate

With `Wappa`:

```python
from wappa import Wappa
from wappa.core.plugins import SSEEventsPlugin

app = Wappa(cache="memory")
app.add_plugin(
    SSEEventsPlugin(
        publish_incoming=True,
        publish_outgoing_api=True,
        publish_bot_replies=True,
        publish_status=True,
        publish_webhook_errors=True,
        queue_size=200,
        metadata={"app_name": "my-bot"},  # optional, enriches all SSE events
    )
)
```

With `WappaBuilder`:

```python
from wappa.core.factory import WappaBuilder
from wappa.core.plugins import WappaCorePlugin, SSEEventsPlugin

builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin())
builder.add_plugin(SSEEventsPlugin())
app = builder.build()
```

All constructor parameters are optional and default to the values shown above.

## SSE endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/sse/events` | GET | Event stream |
| `/api/sse/status` | GET | Plugin health/status |

Optional query-string filters on `/api/sse/events`:

| Parameter | Example | Description |
|---|---|---|
| `tenant_id` | `mimeia` | Receive events for a specific tenant only |
| `user_id` | `573001112233` | Receive events for a specific user only |
| `event_types` | `incoming_message,status_change` | Comma-separated list of event types to subscribe to |

Supported `event_types` values:

- `incoming_message`
- `outgoing_api_message`
- `outgoing_bot_message`
- `status_change`
- `webhook_error`

## How the plugin works

**During `configure()`** (synchronous, before the app starts) the plugin:

1. Creates the in-memory `SSEEventHub` (the router and the middleware both need a reference to it, and it owns only asyncio primitives, so it's safe to build eagerly)
2. Registers the SSE HTTP routes
3. Registers `SSELifecycleMiddleware(event_hub)` via `builder.add_messenger_middleware(...)` at priority `70` (lifecycle band) — this is what publishes `outgoing_bot_message` when `publish_bot_replies=True`
4. Registers startup/shutdown hooks at priority `24`

**During startup** the plugin:

1. Publishes the event hub to `app.state.sse_event_hub` so the SSE router can reach it at request time
2. Wraps the default webhook handlers (`SSEMessageHandler`, `SSEStatusHandler`, `SSEErrorHandler`) to publish `incoming_message`, `status_change`, and `webhook_error` events — these react to the inbound side of the framework, which does not yet have a middleware pipeline of its own
3. Registers a post-process hook on `WappaEventHandler` for API outgoing events (via `add_api_post_process_hook`)

**During shutdown** it:

1. Restores the original webhook handlers
2. Removes the API post-process hook (via `remove_api_post_process_hook`)
3. Closes SSE subscriptions cleanly
4. Clears plugin state from `app.state`

### Why messenger wrapping is now middleware

Pre-v0.4.0 the plugin set `app.state.sse_wrap_messenger = True` and the webhook controller branched on that flag to wrap `self.messenger` with an `SSEMessengerWrapper`. That wrapper re-implemented all 18 `IMessenger` methods just to intercept each one. Downstream apps that needed a cache write to complete before the SSE publish had to drill `messenger._inner` and `sse_wrapper._event_hub` to reassemble the stack manually.

In v0.4.0 that wrapper was rewritten as a ~50 LOC `SSELifecycleMiddleware` inside the general messenger pipeline. Ordering with any other concern (cache, pub/sub, retry) is now declarative via priority; there are no private attributes to drill. See [MessengerMiddleware.md](./MessengerMiddleware.md) for the full picture.

The legacy `SSEMessengerWrapper` is kept as a deprecation shim through v0.5.0 and will be removed in v0.6.0.

## Event envelope format

Every SSE message uses this envelope:

```json
{
  "event_id": "uuid",
  "event_type": "incoming_message",
  "timestamp": "2026-03-06T23:10:11.123456+00:00",
  "tenant_id": "mimeia",
  "user_id": "573001112233",
  "platform": "whatsapp",
  "source": "webhook",
  "payload": {},
  "metadata": null
}
```

The `metadata` field is always present. It is `null` when no metadata was configured, or a `dict` with app-level context when provided (see [Metadata](#metadata) below).

## Payload details

**`incoming_message`** -- `payload` is the normalized `IncomingMessageWebhook` model (`model_dump` JSON), not raw webhook JSON.

**`status_change`** -- `payload` is the normalized `StatusWebhook` model (`model_dump` JSON), not raw webhook JSON.

**`webhook_error`** -- `payload` is the normalized `ErrorWebhook` model (`model_dump` JSON), not raw webhook JSON.

**`outgoing_api_message`** -- `payload` is the normalized `APIMessageEvent` model (`model_dump` JSON).

**`outgoing_bot_message`** -- `payload` includes:

- `message_type`: Wappa message type (`text`, `image`, `template`, etc.)
- `request`: serialized send method input
- `result`: serialized `MessageResult`

## Metadata

All SSE events support an optional `metadata` field in the envelope. This allows applications to enrich events with domain context (conversation IDs, run IDs, etc.) without modifying Wappa internals.

Wappa treats metadata as **opaque** -- it never validates or transforms the contents. The application owns the schema.

### Setting metadata at construction time

Pass `metadata` when creating the plugin. It flows to all handler wrappers and the messenger wrapper automatically:

```python
SSEEventsPlugin(
    metadata={
        "conversation_id": str(conversation_id),
        "chat_id": str(chat_id),
        "run_id": None,
    }
)
```

### Updating metadata at runtime

Use `update_metadata()` to merge new values into the existing metadata dict. This updates all active SSE handlers (incoming, status, error) at once:

```python
# On the plugin instance
sse_plugin.update_metadata(run_id=str(run_id))
```

Individual SSE wrappers also expose `update_metadata()`:

```python
# On the messenger wrapper directly
messenger.update_metadata(run_id=str(run_id))
```

### Resulting envelope

```json
{
  "event_id": "...",
  "event_type": "outgoing_bot_message",
  "timestamp": "...",
  "tenant_id": "mimeia",
  "user_id": "573001112233",
  "platform": "whatsapp",
  "source": "bot_messenger",
  "payload": {
    "message_type": "text",
    "request": {},
    "result": {}
  },
  "metadata": {
    "conversation_id": "uuid",
    "chat_id": "uuid",
    "run_id": "uuid"
  }
}
```

Without metadata configured, `"metadata": null` is always present in the envelope (backward compatible).

## Frontend EventSource receiver

Basic receiver:

```javascript
const url = new URL("/api/sse/events", window.location.origin);
url.searchParams.set(
  "event_types",
  "incoming_message,outgoing_api_message,outgoing_bot_message,status_change,webhook_error"
);

const source = new EventSource(url.toString());

source.addEventListener("incoming_message", (event) => {
  const message = JSON.parse(event.data);
  console.log("Incoming message", message.payload);
});

source.addEventListener("outgoing_api_message", (event) => {
  const apiEvent = JSON.parse(event.data);
  console.log("Outgoing API message", apiEvent.payload);
});

source.addEventListener("outgoing_bot_message", (event) => {
  const botEvent = JSON.parse(event.data);
  console.log("Outgoing bot message", botEvent.payload);
});

source.addEventListener("status_change", (event) => {
  const statusEvent = JSON.parse(event.data);
  console.log("Status change", statusEvent.payload);
});

source.addEventListener("webhook_error", (event) => {
  const errorEvent = JSON.parse(event.data);
  console.error("Webhook error", errorEvent.payload);
});

source.onerror = (err) => {
  // Browser will auto-reconnect for EventSource
  console.error("SSE connection error", err);
};

// Later, when needed:
// source.close();
```

Filter by tenant/user from frontend:

```javascript
const scoped = new URL("/api/sse/events", window.location.origin);
scoped.searchParams.set("tenant_id", "mimeia");
scoped.searchParams.set("user_id", "573001112233");
const source = new EventSource(scoped.toString());
```
