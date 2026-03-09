# WebhookPlugin

> Part of the Wappa Plugin Architecture. See [Architecture](./Architecture.md) for the plugin system overview, lifecycle, and patterns.

## What it does

`WebhookPlugin` adds specialized webhook endpoints to Wappa applications using a Router + Hooks pattern. It registers a FastAPI `APIRouter` with POST endpoints for receiving webhooks and GET `/status` endpoints for health checks. Each plugin instance handles one provider, so you can compose multiple instances for different services.

It is designed for payment providers (Wompi, Stripe, PayPal) and third-party service integrations where you need a dedicated URL to receive incoming HTTP callbacks.

## How to activate

**Payment webhook:**

```python
from wappa import Wappa
from wappa.core.plugins import WebhookPlugin

async def wompi_webhook_handler(request, tenant_id, provider):
    body = await request.json()
    # Process Wompi payment event
    return {"status": "received", "provider": provider}

app = Wappa(cache="memory")
app.add_plugin(
    WebhookPlugin(
        provider="wompi",
        handler=wompi_webhook_handler,
        prefix="/webhook/payment",
    )
)
```

**Service webhook (no tenant ID):**

```python
from wappa.core.plugins import WebhookPlugin

async def github_webhook_handler(request, tenant_id, provider):
    body = await request.json()
    # tenant_id is None when include_tenant_id=False
    return {"status": "ok"}

app.add_plugin(
    WebhookPlugin(
        provider="github",
        handler=github_webhook_handler,
        prefix="/webhook/services",
        include_tenant_id=False,
    )
)
```

With `WappaBuilder`:

```python
from wappa.core.factory import WappaBuilder
from wappa.core.plugins import WappaCorePlugin, WebhookPlugin

builder = WappaBuilder()
builder.add_plugin(WappaCorePlugin())
builder.add_plugin(
    WebhookPlugin(
        provider="stripe",
        handler=stripe_webhook_handler,
        prefix="/webhook/payment",
    )
)
app = builder.build()
```

## Configuration options

| Parameter | Type | Default | Description |
|---|---|---|---|
| `provider` | `str` | (required) | Provider name used in URL path and OpenAPI tags (e.g. `"wompi"`, `"stripe"`) |
| `handler` | `Callable` | (required) | Async callable invoked when a webhook request arrives |
| `prefix` | `str \| None` | `"/webhook/{provider}"` | URL prefix for the router. Defaults to `/webhook/<provider>` if not set |
| `methods` | `list[str] \| None` | `["POST"]` | HTTP methods the webhook endpoint accepts |
| `include_tenant_id` | `bool` | `True` | Whether to include `{tenant_id}` as a path parameter |
| `**route_kwargs` | `Any` | -- | Additional keyword arguments forwarded to the FastAPI `api_route` decorator |

## Handler signature

The handler must be an async callable with the following signature:

```python
async def handler(request: Request, tenant_id: str | None, provider: str) -> dict
```

- **`request`** -- the raw FastAPI/Starlette `Request` object. Use `await request.json()` or `await request.body()` to read the payload.
- **`tenant_id`** -- the tenant identifier extracted from the URL path, or `None` when `include_tenant_id=False`.
- **`provider`** -- the provider name string passed during plugin initialization.

The return value should be a JSON-serializable `dict`.

## URL patterns

**With tenant ID** (`include_tenant_id=True`, the default):

```
POST {prefix}/{tenant_id}
GET  {prefix}/{tenant_id}/status
```

Example with `prefix="/webhook/payment"` and `provider="wompi"`:

```
POST /webhook/payment/{tenant_id}
GET  /webhook/payment/{tenant_id}/status
```

**Without tenant ID** (`include_tenant_id=False`):

```
POST {prefix}/
GET  {prefix}/status
```

Example with `prefix="/webhook/services"` and `provider="github"`:

```
POST /webhook/services/
GET  /webhook/services/status
```

## Status endpoint

Every `WebhookPlugin` instance automatically registers a GET status endpoint for health checks. The response includes:

```json
{
    "status": "active",
    "provider": "wompi",
    "tenant_id": "tenant-123",
    "webhook_url": "https://example.com/webhook/payment/tenant-123",
    "methods": ["POST"],
    "plugin": "WebhookPlugin"
}
```

When `include_tenant_id=False`, the `tenant_id` field is `null` and the `webhook_url` omits the tenant segment.

## Multiple webhooks example

Register several providers by adding one plugin per provider:

```python
from wappa import Wappa
from wappa.core.plugins import WebhookPlugin

app = Wappa(cache="memory")

# Payment providers -- share the same prefix, distinguished by tenant routing
app.add_plugin(
    WebhookPlugin(
        provider="wompi",
        handler=wompi_handler,
        prefix="/webhook/payment/wompi",
    )
)

app.add_plugin(
    WebhookPlugin(
        provider="stripe",
        handler=stripe_handler,
        prefix="/webhook/payment/stripe",
    )
)

# Third-party service -- no tenant ID needed
app.add_plugin(
    WebhookPlugin(
        provider="github",
        handler=github_handler,
        prefix="/webhook/services/github",
        include_tenant_id=False,
    )
)

# Custom methods -- accept both POST and PUT
app.add_plugin(
    WebhookPlugin(
        provider="custom",
        handler=custom_handler,
        prefix="/webhook/custom",
        methods=["POST", "PUT"],
    )
)
```

This produces the following endpoints:

```
POST /webhook/payment/wompi/{tenant_id}
GET  /webhook/payment/wompi/{tenant_id}/status

POST /webhook/payment/stripe/{tenant_id}
GET  /webhook/payment/stripe/{tenant_id}/status

POST /webhook/services/github/
GET  /webhook/services/github/status

POST /webhook/custom/{tenant_id}
PUT  /webhook/custom/{tenant_id}
GET  /webhook/custom/{tenant_id}/status
```

WebhookPlugin is a Router + Hooks plugin (Pattern 2 in the architecture). It creates endpoints during `configure()` via `builder.add_router()`, while `startup()` logs the active URL pattern and `shutdown()` is a no-op log statement.
