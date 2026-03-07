# Wappa Plugins

This folder contains Wappa plugins, including the `SSEEventsPlugin` for real-time event streaming to frontends.

## SSEEventsPlugin

### What it does

`SSEEventsPlugin` streams real-time events through Server-Sent Events (SSE) using FastAPI native support:

- `from fastapi.sse import EventSourceResponse`

It publishes:

1. Incoming messages from webhooks
2. Outgoing messages sent via API routes
3. Outgoing bot messages sent through `self.messenger`
4. Message status events (sent/delivered/read/failed)
5. Webhook-level errors

### How to activate

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
    )
)
```

You can also enable it with `WappaBuilder`:

```python
from wappa.core.factory import WappaBuilder
from wappa.core.plugins import WappaCorePlugin, SSEEventsPlugin

builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin())
builder.add_plugin(SSEEventsPlugin())
app = builder.build()
```

### SSE endpoints

- Stream: `GET /api/sse/events`
- Status: `GET /api/sse/status`

Optional filters in `/api/sse/events`:

- `tenant_id=<tenant>`
- `user_id=<user>`
- `event_types=incoming_message,status_change,...`

Supported `event_types`:

- `incoming_message`
- `outgoing_api_message`
- `outgoing_bot_message`
- `status_change`
- `webhook_error`

### How the plugin works

During startup, the plugin:

1. Creates an in-memory `SSEEventHub`
2. Registers SSE routes
3. Wraps default webhook handlers to publish SSE events
4. Hooks API outgoing event post-processing
5. Marks messenger wrapping in app state so webhook request handlers wrap `self.messenger`

During shutdown, it:

1. Restores original handlers
2. Closes SSE subscriptions cleanly
3. Clears plugin state from `app.state`

### Event envelope format

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
  "payload": {}
}
```

### Payload sent on each event

`incoming_message`

- `payload` is the normalized `IncomingMessageWebhook` model (`model_dump` JSON), not raw webhook JSON.

`status_change`

- `payload` is the normalized `StatusWebhook` model (`model_dump` JSON), not raw webhook JSON.

`webhook_error`

- `payload` is the normalized `ErrorWebhook` model (`model_dump` JSON), not raw webhook JSON.

`outgoing_api_message`

- `payload` is the normalized `APIMessageEvent` model (`model_dump` JSON).

`outgoing_bot_message`

- `payload` includes:
  - `message_type`: Wappa message type (`text`, `image`, `template`, etc.)
  - `request`: serialized send method input
  - `result`: serialized `MessageResult`

### Frontend EventSource receiver

Basic frontend receiver:

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
