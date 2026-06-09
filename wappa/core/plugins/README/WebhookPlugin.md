# WebhookPlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the plugin system overview, lifecycle, and patterns.

## What it does

`WebhookPlugin` adds endpoints for External Webhook Sources such as payment systems, CRMs, or operational tools. It is not for messaging platforms; messaging platform webhooks belong to the Inbound Runtime.

Each plugin instance handles one External Webhook Source and uses an `IWebhookProcessor` to translate the raw HTTP request into an `ExternalEvent`.

## How to activate

```python
from wappa import ExternalEvent, Wappa, WappaEventHandler
from wappa.core.plugins import WebhookPlugin


class MercadoPagoProcessor:
    def get_source_name(self) -> str:
        return "mercadopago"

    async def parse_event(self, request, inbox_id):
        body = await request.json()
        return ExternalEvent(
            source="mercadopago",
            event_type=body.get("type", "unknown"),
            inbox_id=inbox_id,
            payload=body.get("data", {}),
            raw_data=body,
        )

    async def resolve_user_id(self, event, db):
        if not db:
            return None
        async with db() as session:
            sub = await get_subscription(session, event.payload["id"])
            return sub.user_id if sub else None


class MyHandler(WappaEventHandler):
    async def process_external_event(self, event: ExternalEvent):
        if event.source == "mercadopago" and event.event_type == "payment.approved":
            cache = self.cache_factory.create_user_cache()
            await cache.update({"subscription": "active"})
            await self.messenger.send_text(
                text="Payment confirmed!",
                recipient=event.user_id,
            )


handler = MyHandler()
app = Wappa(cache="redis", ...)
app.register_handler(handler)

app.add_plugin(
    WebhookPlugin(
        "mercadopago",
        processor=MercadoPagoProcessor(),
        event_handler=handler,
        prefix="/webhook/payment",
    )
)
```

## Configuration options

| Parameter | Type | Default | Description |
|---|---|---|---|
| `external_source` | `str` | (required) | External source name used in URL path, status output, and OpenAPI tags |
| `processor` | `IWebhookProcessor` | (required) | Processor that validates the request and creates an `ExternalEvent` |
| `event_handler` | `WappaEventHandler` | (required) | Handler prototype cloned for dispatch |
| `prefix` | `str \| None` | `"/webhook/{external_source}"` | URL prefix for the router |
| `methods` | `list[str] \| None` | `["POST"]` | HTTP methods the endpoint accepts |
| `include_inbox_id` | `bool` | `True` | Whether to include `{inbox_id}` as a path parameter |
| `**route_kwargs` | `Any` | -- | Additional keyword arguments forwarded to FastAPI `api_route` |

## Processing pipeline

When a webhook arrives:

```
POST /webhook/payment/{inbox_id}
    │
    ├── Reads and snapshots the request body
    ├── Returns {"status": "accepted"} immediately (200)
    │
    └── Background task:
        ├── ExternalWebhookRuntime.process(snapshot, inbox_id)
        ├── processor.parse_event(request, inbox_id) → ExternalEvent
        │   (your Pydantic schema validates the raw payload here)
        ├── validate event.inbox_id matches the routed Inbox
        ├── WappaContextFactory.create_context(inbox_id) → DB-only context
        ├── processor.resolve_user_id(event, db) → user_id
        ├── WappaContextFactory.create_context(inbox_id, user_id, include_messenger=True)
        │   → full context (messenger + cache + db)
        ├── handler.with_context(...) → cloned handler
        └── handler.process_external_event(event)
```

External webhooks identify an external resource such as a payment, subscription, or ticket. The processor resolves the Wappa `user_id` in two phases:

1. DB-only context to look up the user from the external payload.
2. Full context with Messenger and Cache Factory once the user is known.

If `include_inbox_id=False`, processor mode rejects incoming webhooks with
HTTP 400. External Webhook Source processing needs an Inbox because Wappa scopes
Messenger, Cache Factory, SSE, and dispatch identity by `inbox_id`.

## IWebhookProcessor interface

```python
class IWebhookProcessor(Protocol):
    def get_source_name(self) -> str: ...
    async def parse_event(self, request: Request, inbox_id: str) -> ExternalEvent: ...
    async def resolve_user_id(self, event: ExternalEvent, db: Callable | None) -> str | None: ...
```

| Method | Purpose |
|--------|---------|
| `get_source_name()` | External source identifier for logging |
| `parse_event()` | Validate raw request and return a typed `ExternalEvent` |
| `resolve_user_id()` | Optional lookup from external payload to Wappa `user_id` |

## ExternalEvent model

```python
class ExternalEvent(BaseModel):
    source: str              # "stripe", "mercadopago"
    event_type: str          # "payment.approved"
    inbox_id: str            # From URL path
    user_id: str | None      # Resolved by processor
    payload: dict[str, Any]  # Validated webhook data
    metadata: dict[str, Any] # Additional context
    timestamp: datetime      # When received
    raw_data: dict | None    # Original body (excluded from serialization)
```

## URL patterns

**With Inbox ID** (`include_inbox_id=True`, the default):

```
POST {prefix}/{inbox_id}
GET  {prefix}/{inbox_id}/status
```

**Without Inbox ID** (`include_inbox_id=False`):

```
POST {prefix}/
GET  {prefix}/status
```

## Status endpoint

```json
{
  "status": "active",
  "external_source": "mercadopago",
  "inbox_id": "508386009032748",
  "webhook_url": "https://example.com/webhook/payment/508386009032748",
  "methods": ["POST"]
}
```

## Multiple External Webhook Sources

```python
app.add_plugin(
    WebhookPlugin("stripe", processor=StripeProcessor(),
                  event_handler=handler, prefix="/webhook/payment")
)
app.add_plugin(
    WebhookPlugin("mercadopago", processor=MPProcessor(),
                  event_handler=handler, prefix="/webhook/payment")
)
app.add_plugin(
    WebhookPlugin("hubspot", processor=HubspotProcessor(),
                  event_handler=handler, prefix="/webhook/crm")
)
```

Dispatch by `event.source` in your handler:

```python
async def process_external_event(self, event: ExternalEvent):
    match event.source:
        case "stripe": ...
        case "mercadopago": ...
        case "hubspot": ...
```

## Imports

```python
from wappa import ExternalEvent, IWebhookProcessor, WappaContext
from wappa.core.plugins import WebhookPlugin
```
