# WebhookPlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the plugin system overview, lifecycle, and patterns.

## What it does

`WebhookPlugin` adds specialized webhook endpoints to Wappa applications for receiving HTTP callbacks from external services (payment providers, CRM systems, etc.).

It supports two modes:

- **Raw handler mode (v1)**: Pass a callable that receives the raw `Request`. Simple, no Wappa infrastructure access.
- **Processor mode (v2)**: Pass an `IWebhookProcessor` that gets full Wappa infrastructure (messenger, cache, database) injected automatically — same pipeline as WhatsApp webhooks.

Each plugin instance handles one provider. Compose multiple instances for different services.

## How to activate

### Processor mode (v2) — with full infrastructure

```python
from wappa import Wappa, WappaEventHandler, ExternalEvent
from wappa.core.plugins import WebhookPlugin

class MercadoPagoProcessor:
    def get_provider_name(self) -> str:
        return "mercadopago"

    async def parse_event(self, request, tenant_id):
        body = await request.json()
        return ExternalEvent(
            source="mercadopago",
            event_type=body.get("type", "unknown"),
            tenant_id=tenant_id,
            payload=body.get("data", {}),
            raw_data=body,
        )

    async def resolve_user_id(self, event, db):
        if not db:
            return None
        async with db() as session:
            sub = await get_subscription(session, event.payload["id"])
            return sub.user_phone if sub else None

class MyHandler(WappaEventHandler):
    async def process_message(self, webhook):
        await self.messenger.send_text(webhook.user.user_id, "Hello!")

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

### Raw handler mode (v1) — simple, no infrastructure

```python
from wappa.core.plugins import WebhookPlugin

async def wompi_webhook_handler(request, tenant_id, provider):
    body = await request.json()
    return {"status": "received", "provider": provider}

app.add_plugin(
    WebhookPlugin(
        provider="wompi",
        handler=wompi_webhook_handler,
        prefix="/webhook/payment",
    )
)
```

### Service webhook (no tenant ID)

```python
app.add_plugin(
    WebhookPlugin(
        provider="github",
        handler=github_webhook_handler,
        prefix="/webhook/services",
        include_tenant_id=False,
    )
)
```

## Configuration options

| Parameter | Type | Default | Description |
|---|---|---|---|
| `provider` | `str` | (required) | Provider name used in URL path and OpenAPI tags |
| `handler` | `Callable \| None` | `None` | Async callable for raw handler mode (v1) |
| `processor` | `IWebhookProcessor \| None` | `None` | Processor instance for infrastructure-injected mode (v2) |
| `event_handler` | `WappaEventHandler \| None` | `None` | Handler prototype for cloning (required with `processor`) |
| `prefix` | `str \| None` | `"/webhook/{provider}"` | URL prefix for the router |
| `methods` | `list[str] \| None` | `["POST"]` | HTTP methods the endpoint accepts |
| `include_tenant_id` | `bool` | `True` | Whether to include `{tenant_id}` as a path parameter |
| `**route_kwargs` | `Any` | -- | Additional keyword arguments forwarded to FastAPI `api_route` |

Either `handler` or `processor` must be provided. When `processor` is used, `event_handler` is also required.

## Processor mode pipeline (v2)

When a webhook arrives in processor mode:

```
POST /webhook/payment/{tenant_id}
    │
    ├── Returns {"status": "accepted"} immediately (200)
    │
    └── Background task:
        ├── processor.parse_event(request, tenant_id) → ExternalEvent
        │   (your Pydantic schema validates the raw payload HERE)
        ├── WappaContextFactory.create_context(tenant_id) → DB-only context
        ├── processor.resolve_user_id(event, db) → user_id
        ├── WappaContextFactory.create_context(tenant_id, user_id, messenger=True)
        │   → full context (messenger + cache + db)
        ├── handler.with_context(...) → cloned handler
        └── handler.process_external_event(event)
```

### Two-phase context

External webhooks identify a resource (payment, subscription), not a user. The processor resolves the user in two phases:

1. **Phase 1**: DB-only context to look up the user from the webhook payload
2. **Phase 2**: Full context with messenger + cache once the user is known

### IWebhookProcessor interface

```python
class IWebhookProcessor(Protocol):
    def get_provider_name(self) -> str: ...
    async def parse_event(self, request: Request, tenant_id: str) -> ExternalEvent: ...
    async def resolve_user_id(self, event: ExternalEvent, db: Callable | None) -> str | None: ...
```

| Method | Purpose |
|--------|---------|
| `get_provider_name()` | Provider identifier for logging |
| `parse_event()` | Validate raw request → typed `ExternalEvent` (your schema goes here) |
| `resolve_user_id()` | Optional: look up user from event payload via DB |

### ExternalEvent model

```python
class ExternalEvent(BaseModel):
    source: str              # "stripe", "mercadopago"
    event_type: str          # "payment.approved"
    tenant_id: str           # From URL path
    user_id: str | None      # Resolved by processor
    payload: dict[str, Any]  # Validated webhook data
    metadata: dict[str, Any] # Additional context
    timestamp: datetime      # When received
    raw_data: dict | None    # Original body (excluded from serialization)
```

### Handler method

```python
async def process_external_event(self, event: ExternalEvent) -> None:
    """Override in your WappaEventHandler subclass."""
    # Available when tenant-scoped:
    # self.messenger — send messages
    # self.cache_factory — access caches
    # self.db / self.db_read — database sessions
```

## Raw handler signature (v1)

```python
async def handler(request: Request, tenant_id: str | None, provider: str) -> dict
```

- **`request`** -- raw FastAPI/Starlette `Request` object
- **`tenant_id`** -- from URL path, or `None` when `include_tenant_id=False`
- **`provider`** -- provider name from plugin initialization

## URL patterns

**With tenant ID** (`include_tenant_id=True`, the default):

```
POST {prefix}/{tenant_id}
GET  {prefix}/{tenant_id}/status
```

**Without tenant ID** (`include_tenant_id=False`):

```
POST {prefix}/
GET  {prefix}/status
```

## Status endpoint

Every `WebhookPlugin` instance registers a GET status endpoint:

```json
{
    "status": "active",
    "provider": "mercadopago",
    "tenant_id": "tenant-123",
    "webhook_url": "https://example.com/webhook/payment/tenant-123",
    "methods": ["POST"],
    "mode": "processor"
}
```

The `mode` field shows `"processor"` (v2) or `"raw"` (v1).

## Multiple providers

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
